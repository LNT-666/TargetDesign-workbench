#!/usr/bin/env python3
"""Focused tests for the release metadata consistency check."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.check_release_metadata import check_metadata  # noqa: E402


class ReleaseMetadataTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        for name in ("pyproject.toml", "CITATION.cff", ".zenodo.json"):
            shutil.copy2(ROOT / name, self.root / name)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_repository_metadata_is_consistent(self) -> None:
        self.assertEqual(check_metadata(self.root), [])

    def test_version_mismatch_is_reported(self) -> None:
        path = self.root / "pyproject.toml"
        text = path.read_text(encoding="utf-8")
        text = re.sub(
            r'^version = ".*"$', 'version = "9.9.9"', text,
            count=1, flags=re.MULTILINE)
        path.write_text(text,
                        encoding="utf-8", newline="")
        errors = check_metadata(self.root)
        self.assertTrue(any(error.startswith("version mismatch:") for error in errors))

    def write_cff(self, text: str) -> None:
        (self.root / "CITATION.cff").write_text(text, encoding="utf-8", newline="")

    def read_cff(self) -> str:
        return (self.root / "CITATION.cff").read_text(encoding="utf-8")

    def test_shipped_metadata_carries_no_doi_placeholder(self) -> None:
        self.assertEqual(check_metadata(self.root), [])

    def test_unresolved_placeholder_comment_is_rejected(self) -> None:
        text = re.sub(
            r"^# Zenodo concept DOI.*(?:\n#.*\n)*",
            '# Concept DOI. Replace with the version DOI after archiving.\n',
            self.read_cff(), count=1, flags=re.MULTILINE)
        self.write_cff(text)
        errors = check_metadata(self.root)
        self.assertTrue(any("unresolved placeholder" in error for error in errors), errors)

    def test_malformed_doi_is_rejected(self) -> None:
        self.write_cff(self.read_cff().replace(
            'doi: "10.5281/zenodo.23231712"', 'doi: "not-a-doi"'))
        errors = check_metadata(self.root)
        self.assertTrue(any("not a Zenodo DOI" in error for error in errors), errors)

    @unittest.skipUnless(shutil.which("git"), "git is not available")
    def test_tagged_version_must_not_cite_the_concept_doi(self) -> None:
        version = re.search(r'^version: "(.*)"$', self.read_cff(),
                            re.MULTILINE).group(1)

        def git(*args: str) -> subprocess.CompletedProcess:
            return subprocess.run(
                ["git", "-c", "user.name=gate",
                 "-c", "user.email=gate@example.invalid", *args],
                cwd=str(self.root), capture_output=True, text=True)

        for command in (("init", "-q"),
                        ("commit", "-q", "--allow-empty", "-m", "seed"),
                        ("tag", f"v{version}")):
            self.assertEqual(git(*command).returncode, 0, command)

        errors = check_metadata(self.root)
        self.assertTrue(
            any("still cites the concept DOI" in error for error in errors), errors)

        self.write_cff(self.read_cff().replace(
            "10.5281/zenodo.23231712", "10.5281/zenodo.24026181"))
        self.assertEqual(check_metadata(self.root), [])


if __name__ == "__main__":
    unittest.main()
