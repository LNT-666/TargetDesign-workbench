# -*- coding: utf-8 -*-
"""Selection rules for the hand-off bundle builder."""

import sys
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
        self.assertTrue(ENGINE_BINS & self.rels, self.rels)
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
            "external_tools/DeepCas12a",
        )
        for rel in self.rels:
            self.assertFalse(rel.startswith(banned_prefixes), rel)
            self.assertFalse(rel.endswith(bundle.EXCLUDE_SUFFIXES), rel)


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
        self.assertTrue(ENGINE_BINS & self.rels, self.rels)


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
        self.assertEqual(fences, ["```diff", "```"])

    def test_absolute_build_paths_are_redacted(self):
        text = bundle._manifest_text(
            "2026-11-06", "abc1234", "main", [], [], [],
            Path("C:/Users/example/release"))
        self.assertEqual(text.count("<redacted build-machine path>"), 2)
        self.assertNotIn("C:/Users", text)

    def test_relative_output_path_is_kept(self):
        self.assertEqual(bundle._redact_site_path("release/out"), "release/out")


if __name__ == "__main__":
    unittest.main()
