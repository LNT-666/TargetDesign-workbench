# -*- coding: utf-8 -*-
"""Selection rules for the hand-off bundle builder."""

import os
import sys
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import build_release_bundle as bundle  # noqa: E402

SUBMISSION_DIR = ROOT / "docs" / "submission"
FIGURES_DIR = ROOT / "docs" / "figures"
SUBMISSION_AVAILABLE = SUBMISSION_DIR.is_dir() and FIGURES_DIR.is_dir()

#: The native engine is built in place, with a .exe suffix on Windows runners.
ENGINE_BINS = {"native/bin/offtarget-engine", "native/bin/offtarget-engine.exe"}

#: Built on this machine or not -- decides skip versus fail, so an engine that
#: exists on disk but is missing from the selection still fails the check.
ENGINE_ON_DISK = any((ROOT / rel).is_file() for rel in ENGINE_BINS)


class CodeSelectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rels = {item[0] for item in bundle._code_files()}

    def test_includes_pending_release_sources(self):
        for rel in (
            "shared/scoring/deepcrispr_convert.py",
            "webapp/services/models.py",
            "tools/build_release_bundle.py",
        ):
            self.assertIn(rel, self.rels)
        if not ENGINE_ON_DISK:
            raise unittest.SkipTest("native offtarget-engine binary is not built")
        self.assertTrue(ENGINE_BINS & self.rels, sorted(ENGINE_BINS - self.rels))
        launcher = ROOT / "TargetDesign-workbench.exe"
        if launcher.is_file():
            self.assertIn("TargetDesign-workbench.exe", self.rels)

    def test_excludes_weights_artifacts_and_internal_material(self):
        banned_prefixes = (
            "models/",
            "logs/",
            "output/",
            "backup/",
            "docs/submission/",
            "docs/figures/",
            "docs/qa/",
            "docs/handoff/",
            "external_tools/",
        )
        for rel in self.rels:
            self.assertFalse(rel.startswith(banned_prefixes), rel)
            self.assertFalse(rel.endswith(bundle.EXCLUDE_SUFFIXES), rel)
        self.assertNotIn("external_tools", bundle.CODE_DIRS)


class BundleContentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rels = {item[0] for item in bundle._code_files()}

    def test_runtime_source_package_and_release_metadata_are_included(self):
        for rel in (
            "shared/output/__init__.py",
            "shared/output/candidate_export.py",
            "shared/output/output_columns.py",
            "shared/output/xlsx_utils.py",
            ".gitignore",
            ".github/workflows/container.yml",
            ".github/workflows/portability.yml",
            "requirements-test.txt",
        ):
            self.assertIn(rel, self.rels)

    def test_local_only_files_and_build_trees_are_excluded(self):
        for rel in (
            "docs/SSH_ACCESS.md",
            "tools/release_scan_denylist.local.txt",
        ):
            self.assertNotIn(rel, self.rels)
        self.assertFalse(
            [rel for rel in self.rels if rel.startswith("native/build")], self.rels)

    def test_launcher_and_shell_scripts_keep_their_executable_bit(self):
        for rel in (
            "tools/serve_webapp.sh",
            "tools/server_build_index.sh",
            "tools/build_crispai_env.sh",
        ):
            self.assertIn(rel, bundle.EXECUTABLE_PATHS)
            self.assertIn(rel, self.rels)
        self.assertIn("native/bin/offtarget-engine", bundle.EXECUTABLE_PATHS)
        # The native unit-test binary is shipped and must stay runnable on Unix,
        # where the build machine's permission bits are not represented.
        self.assertIn("native/bin/offtarget-engine-tests", bundle.EXECUTABLE_PATHS)
        if not ENGINE_ON_DISK:
            raise unittest.SkipTest("native offtarget-engine binary is not built")
        self.assertTrue(ENGINE_BINS & self.rels, sorted(ENGINE_BINS - self.rels))


VENDORED_AVAILABLE = any(
    rel.startswith(bundle.VENDORED_DIR + "/")
    for rel in {item[0] for item in bundle._code_files(include_vendored=True)})


class VendoredPolicyTests(unittest.TestCase):
    """Each build must say in the delivered text which vendored policy it used."""

    def test_default_selection_excludes_vendored_sources(self):
        self.assertNotIn(bundle.VENDORED_DIR, bundle.CODE_DIRS)
        rels = {item[0] for item in bundle._code_files()}
        self.assertFalse([rel for rel in rels
                          if rel.startswith(bundle.VENDORED_DIR + "/")])

    @unittest.skipUnless(VENDORED_AVAILABLE,
                         "no upstream sources are installed under %s/"
                         % bundle.VENDORED_DIR)
    def test_include_vendored_adds_only_that_tree(self):
        default = {item[0] for item in bundle._code_files()}
        included = {item[0] for item in bundle._code_files(include_vendored=True)}
        added = included - default
        self.assertTrue(added)
        self.assertTrue(all(rel.startswith(bundle.VENDORED_DIR + "/")
                            for rel in added), sorted(added))
        self.assertTrue(any(rel.endswith("LICENSE") for rel in added),
                        sorted(added))
        # Vendoring must not smuggle weights past the suffix gate.
        self.assertFalse([rel for rel in added
                          if rel.endswith(bundle.EXCLUDE_SUFFIXES)],
                         sorted(added))

    def test_package_contents_documents_the_chosen_policy(self):
        for section in (bundle._vendored_section(True),
                        bundle._vendored_section(False)):
            self.assertIn("## 第三方 vendored 源码", section)
            self.assertIn(bundle.VENDORED_DIR, section)
            self.assertIn("docs/CRISPAI.md", section)
            self.assertNotIn("%(", section)
            text = bundle.PACKAGE_CONTENTS.format(
                day="2026-01-01", submission="x", vendored=section)
            self.assertNotIn("{vendored}", text)
            self.assertEqual(1, text.count("## Windows 快速启动"))
        self.assertIn("--include-vendored` 构建", bundle._vendored_section(True))
        self.assertIn("不携带", bundle._vendored_section(False))

    def test_manifest_records_the_vendored_line(self):
        excluded = bundle._manifest_text("2026-01-01", "h" * 7, "main", [], [],
                                         [], Path("."))
        included = bundle._manifest_text("2026-01-01", "h" * 7, "main", [], [],
                                         [], Path("."), vendored_included=True)
        self.assertIn("excluded (default policy)", excluded)
        self.assertIn("included (--include-vendored)", included)


@unittest.skipUnless(ENGINE_ON_DISK and VENDORED_AVAILABLE,
                     "needs a built native engine and installed upstream sources")
class VendoredBuildTests(unittest.TestCase):
    """The delivered text must match what the build really copied."""

    def _build(self, extra_args):
        # mkdtemp + addCleanup, not TemporaryDirectory: the context manager
        # deletes the bundle as soon as _build returns, so every assertion
        # would run against a directory that no longer exists.
        tmp = tempfile.mkdtemp(prefix="tdw-bundle-")
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        argv = ["--out", tmp, "--date", "stamp", "--skip-submission",
                "--skip-lineage", "--skip-import-smoke", "--skip-leak-scan",
                "--no-zip"]
        self.assertEqual(0, bundle.main(argv + extra_args))
        folder = Path(tmp) / ("%s_stamp" % bundle.PREFIX)
        self.assertTrue(folder.is_dir())
        return (folder,
                (folder / "MANIFEST.md").read_text(encoding="utf-8"),
                (folder / "PACKAGE_CONTENTS.md").read_text(encoding="utf-8"))

    def test_default_build_ships_no_vendored_sources_and_says_so(self):
        folder, manifest, contents = self._build([])
        self.assertTrue((folder / "code" / "shared").is_dir())
        self.assertFalse((folder / "code" / bundle.VENDORED_DIR).exists())
        self.assertIn("excluded (default policy)", manifest)
        self.assertIn("- 本包不携带", contents)

    def test_include_vendored_build_ships_sources_and_says_so(self):
        folder, manifest, contents = self._build(["--include-vendored"])
        self.assertTrue((folder / "code" / bundle.VENDORED_DIR
                         / "crispAI-main" / "LICENSE").is_file())
        self.assertIn("included (--include-vendored)", manifest)
        self.assertIn("--include-vendored` 构建", contents)
        self.assertFalse(any((folder / "code").glob("models/**")))


@unittest.skipUnless(SUBMISSION_AVAILABLE,
                     "internal manuscript material is not shipped with the code bundle")
class SubmissionSelectionTests(unittest.TestCase):
    def test_manuscript_supplementary_and_figures_are_present(self):
        rels = {item[0] for item in bundle._submission_files()}
        for rel in (
            "SUBMISSION_SHORT_v1.docx",
            "SUBMISSION_SHORT_v1.md",
            "SUPPLEMENTARY_v1.md",
            "SUPPLEMENTARY_v1.pdf",
            "figures/fig1_architecture_v1.pdf",
            "figures/graphical_abstract.png",
        ):
            self.assertIn(rel, rels)

    def test_every_submission_source_exists(self):
        for rel, path, _size, _mtime in bundle._submission_files():
            self.assertTrue(path.is_file(), rel)


class ExclusionTests(unittest.TestCase):
    def test_prefix_and_suffix_rules(self):
        self.assertTrue(bundle._excluded("docs/PAPER_DRAFT.md"))
        self.assertTrue(bundle._excluded("docs/submission/SUBMISSION_SHORT_v1.docx"))
        self.assertTrue(bundle._excluded("external_tools/DeepCas12a-main/trained_model/fold1.pth"))
        self.assertFalse(bundle._excluded("docs/MODELS.md"))
        self.assertFalse(bundle._excluded("shared/scoring/deepcrispr_convert.py"))


class ZipLayoutTests(unittest.TestCase):
    def test_entries_keep_their_bundle_prefix(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "bundle.zip"
            staged = {
                "code/a.txt": (b"alpha", 0),
                "submission/b.txt": (b"beta", 0),
            }
            bundle._zip_entries("BUNDLE", staged, archive)
            names = zipfile.ZipFile(archive).namelist()
        self.assertEqual(names, ["BUNDLE/code/a.txt", "BUNDLE/submission/b.txt"])

    def test_entries_preserve_executable_bits(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "bundle.zip"
            staged = {
                "code/tool.sh": (b"#!/bin/sh\n", 0, True),
                "code/readme.md": (b"text\n", 0, False),
            }
            bundle._zip_entries("BUNDLE", staged, archive)
            with zipfile.ZipFile(archive) as zf:
                modes = {
                    info.filename: (info.external_attr >> 16) & 0o777
                    for info in zf.infolist()
                }
        self.assertEqual(modes["BUNDLE/code/tool.sh"], 0o755)
        self.assertEqual(modes["BUNDLE/code/readme.md"], 0o644)


class ManifestTests(unittest.TestCase):
    def test_fences_are_balanced(self):
        text = bundle._manifest_text(
            "2026-11-06", "abc1234", "main", [" M a.py"], [], [], Path("out"))
        fences = [line for line in text.splitlines() if line.startswith("```")]
        self.assertEqual(len(fences) % 2, 0, fences)
        self.assertEqual(fences[:2], ["```diff", "```"])
        self.assertIn("python code/tools/check_bundle_inventory.py .", text)

    def test_absolute_build_paths_are_redacted(self):
        text = bundle._manifest_text(
            "2026-11-06", "abc1234", "main", [], [], [],
            Path("C:/Users/example/release"))
        self.assertEqual(text.count("<redacted build-machine path>"), 2)
        self.assertNotIn("C:/Users", text)

    def test_relative_output_path_is_kept(self):
        self.assertEqual(bundle._redact_site_path("release/out"), "release/out")

    def test_inventory_digest_anchors_the_rows(self):
        rows = [("b.py", 2, "0" * 64), ("a.py", 11, "1" * 64)]
        text = bundle._manifest_text(
            "2026-11-06", "abc1234", "main", [], rows, [], Path("out"),
            submission_skipped=True)
        self.assertIn(
            "- inventory digest: `%s`" % bundle._inventory_digest(rows, []), text)
        # Order of the tables must not change the anchor.
        self.assertEqual(bundle._inventory_digest(rows, []),
                         bundle._inventory_digest(list(reversed(rows)), []))

    def test_unknown_head_is_explained_and_a_known_head_is_not(self):
        unknown = bundle._manifest_text(
            "2026-11-06", "unknown", "unknown", [], [], [], Path("out"),
            submission_skipped=True)
        self.assertIn("did not run inside a git working tree", unknown)
        self.assertIn("build official releases from a git checkout", unknown)
        known = bundle._manifest_text(
            "2026-11-06", "abc1234", "main", [], [], [], Path("out"),
            submission_skipped=True)
        self.assertNotIn("did not run inside a git working tree", known)

    def test_manifest_rows_round_trip_through_the_checker(self):
        import check_bundle_inventory as checker

        code = [("b.py", 2, "0" * 64), ("a.py", 11, "1" * 64)]
        submission = [("manuscript.docx", 7, "2" * 64)]
        text = bundle._manifest_text(
            "2026-11-06", "abc1234", "main", [], code, submission, Path("out"))
        rows = checker._read_rows(text)
        self.assertEqual(rows, [
            ("code", "b.py", 2, "0" * 64),
            ("code", "a.py", 11, "1" * 64),
            ("submission", "manuscript.docx", 7, "2" * 64),
        ])
        self.assertEqual(checker._digest_of(rows),
                         bundle._inventory_digest(code, submission))


@unittest.skipUnless(ENGINE_ON_DISK, "needs a built native engine binary")
class BundleInventoryVerificationTests(unittest.TestCase):
    """A recipient must be able to re-verify the bundle without a git anchor."""

    def setUp(self):
        import check_bundle_inventory as checker

        self.checker = checker
        tmp = tempfile.mkdtemp(prefix="tdw-inventory-")
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        argv = ["--out", tmp, "--date", "stamp", "--skip-submission",
                "--skip-lineage", "--skip-import-smoke", "--skip-leak-scan"]
        stdout = sys.stdout
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
        try:
            self.assertEqual(0, bundle.main(argv))
        finally:
            sys.stdout.close()
            sys.stdout = stdout
        self.root = Path(tmp)
        self.folder = self.root / ("%s_stamp" % bundle.PREFIX)
        self.archive = self.root / ("%s_stamp.zip" % bundle.PREFIX)

    def test_sidecar_digests_the_delivered_zip(self):
        sidecar = Path(str(self.archive) + ".sha256")
        self.assertTrue(sidecar.is_file())
        recorded, _, name = sidecar.read_text(encoding="utf-8").partition("  ")
        self.assertEqual(name.strip(), self.archive.name)
        self.assertEqual(recorded, bundle._sha256(self.archive))

    def test_checker_accepts_the_folder_and_the_zip(self):
        self.assertEqual(0, self.checker.check(self.folder))
        self.assertEqual(0, self.checker.check(self.archive))

    def test_checker_rejects_a_modified_file(self):
        victim = sorted(self.checker._read_rows(
            (self.folder / "MANIFEST.md").read_text(encoding="utf-8")))[0]
        path = self.folder / victim[0] / victim[1]
        original = path.read_bytes()
        self.addCleanup(path.write_bytes, original)
        path.write_bytes(original + b"\n# tampered\n")
        self.assertEqual(1, self.checker.check(self.folder))

    def test_checker_rejects_a_dropped_file(self):
        victim = sorted(self.checker._read_rows(
            (self.folder / "MANIFEST.md").read_text(encoding="utf-8")))[0]
        path = self.folder / victim[0] / victim[1]
        original = path.read_bytes()
        self.addCleanup(path.write_bytes, original)
        path.unlink()
        self.assertEqual(1, self.checker.check(self.folder))

    def test_manifest_records_the_digest_the_checker_recomputes(self):
        text = (self.folder / "MANIFEST.md").read_text(encoding="utf-8")
        rows = self.checker._read_rows(text)
        self.assertTrue(rows)
        self.assertEqual(
            self.checker._digest_of(rows),
            self.checker.DIGEST_RE.search(text).group(1))


class LineEndingTests(unittest.TestCase):
    def test_normalize_lf_folds_text_but_leaves_binaries(self):
        self.assertEqual(bundle._normalize_lf(b"a\r\nb\rc\n"), b"a\nb\nc\n")
        self.assertEqual(bundle._normalize_lf(b"a\nb\n"), b"a\nb\n")
        self.assertEqual(bundle._normalize_lf(b"\x00\r\n\x00"), b"\x00\r\n\x00")

    def test_staged_text_is_lf_and_containers_are_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "src"
            source.mkdir()
            text = source / "guides.tsv"
            text.write_bytes(b"tool\tyear\r\nCHOPCHOP\t2023\r\n")
            blob = source / "figure.pdf"
            blob.write_bytes(b"%PDF-1.4\r\n\x00\x00")
            items = [
                ("example/guides.tsv", text, 28, 1000),
                ("docs/figure.pdf", blob, 12, 1000),
            ]
            _rows, staged = bundle._copy_items(items, Path(tmp) / "out", jobs=1)
        self.assertEqual(staged["example/guides.tsv"][0],
                         b"tool\tyear\nCHOPCHOP\t2023\n")
        self.assertEqual(staged["docs/figure.pdf"][0], b"%PDF-1.4\r\n\x00\x00")

    def test_byte_for_byte_fixture_paths_are_declared(self):
        attributes = (ROOT / ".gitattributes").read_text(encoding="utf-8")
        for rule in ("tests/data/** -text", "example/** -text"):
            self.assertIn(rule, attributes)


if __name__ == "__main__":
    unittest.main()
