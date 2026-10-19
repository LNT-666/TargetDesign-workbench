#!/usr/bin/env python3
"""Focused tests for the release metadata consistency check."""

from __future__ import annotations

import re
import shutil
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


if __name__ == "__main__":
    unittest.main()
