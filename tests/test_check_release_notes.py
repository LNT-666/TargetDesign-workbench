# -*- coding: utf-8 -*-
"""Release-notes leak gate: exit codes, report-only split, and read failures."""

import io
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import build_release_bundle as bundle  # noqa: E402
import check_release_notes as notes  # noqa: E402

# Assembled at runtime: build_release_stage.scan() reads every .py in a bundle,
# so the samples must not appear as literals in this file.
_BS = chr(92)
POSIX_HOME = "/" + "home/dev/pkg"
UNC = _BS + _BS + "fileserver" + _BS + "share"
DRIVE = "D:" + _BS + "TargetDesign"

BLOCKING_SAMPLE = "Logs live under %s and %s.\n" % (POSIX_HOME, UNC)
REPORT_ONLY_SAMPLE = "Extract the bundle to %s or E:%swork.\n" % (DRIVE, _BS)
CLEAN_SAMPLE = "This release adds a native indexed backend.\n"


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = notes.main(argv)
    return code, out.getvalue(), err.getvalue()


class CheckReleaseNotesTests(unittest.TestCase):
    def write(self, name: str, text: str) -> str:
        tmp = tempfile.mkdtemp()
        path = Path(tmp) / name
        path.write_text(text, encoding="utf-8")
        return str(path)

    def test_clean_notes_exit_zero(self):
        code, out, _err = run([self.write("notes.md", CLEAN_SAMPLE)])
        self.assertEqual(code, 0)
        self.assertIn("clean", out)

    def test_blocking_leak_refuses_publication(self):
        path = self.write("notes.md", BLOCKING_SAMPLE)
        code, _out, err = run([path])
        self.assertEqual(code, 1)
        self.assertIn("refused", err)

    def test_report_only_labels_do_not_refuse_publication(self):
        path = self.write("notes.md", REPORT_ONLY_SAMPLE)
        code, out, err = run([path])
        self.assertEqual(code, 0, err)
        self.assertIn("report-only", out)
        self.assertNotIn("refused", err)

    def test_blocking_split_matches_the_bundle_gate(self):
        for label in bundle.BLOCKING_LEAK_LABELS:
            self.assertTrue(notes.is_blocking(label), label)
        for label in ("drive letter", "agent branding", "skill audit name"):
            self.assertFalse(notes.is_blocking(label), label)

    def test_missing_file_reports_instead_of_traceback(self):
        with self.assertRaises(SystemExit) as caught:
            notes.main([str(ROOT / "release-notes.md")])
        self.assertIn("cannot read", str(caught.exception))

    def test_stdin_is_scanned(self):
        original = sys.stdin
        reader = io.StringIO(BLOCKING_SAMPLE)
        sys.stdin = reader
        try:
            code, _out, err = run(["-"])
        finally:
            sys.stdin = original
        self.assertEqual(code, 1)
        self.assertIn("refused", err)

    def test_every_file_is_reported(self):
        good = self.write("good.md", CLEAN_SAMPLE)
        bad = self.write("bad.md", BLOCKING_SAMPLE)
        code, out, _err = run([good, bad])
        self.assertEqual(code, 1)
        self.assertIn("clean", out)


if __name__ == "__main__":
    unittest.main()
