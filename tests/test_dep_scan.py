#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Focused tests for dependency-scan file discovery."""

import contextlib
import io
import os
import subprocess
import sys
import unittest
from unittest import mock


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tools import dep_scan  # noqa: E402


class FileSetTests(unittest.TestCase):
    def test_git_failure_falls_back_to_filesystem_walk(self):
        def fake_expand(path, found):
            self.assertEqual(path, ".")
            found.extend(["z.py", "a.py"])

        failure = subprocess.CalledProcessError(
            128, ["git", "ls-files"], stderr=b"fatal: not a git repository")
        stderr = io.StringIO()
        with mock.patch.object(dep_scan, "git", side_effect=failure), \
                mock.patch.object(dep_scan, "_expand",
                                  side_effect=fake_expand) as expand, \
                contextlib.redirect_stderr(stderr):
            tracked, untracked = dep_scan.file_sets()

        self.assertEqual(tracked, ["a.py", "z.py"])
        self.assertEqual(untracked, [])
        expand.assert_called_once()
        self.assertEqual(
            stderr.getvalue().strip(),
            "not a git checkout; falling back to filesystem walk",
        )

    def test_successful_git_keeps_tracked_and_untracked_semantics(self):
        def fake_expand(path, found):
            self.assertEqual(path, "new.py")
            found.append("new.py")

        with mock.patch.object(
                dep_scan, "git", side_effect=["tracked.py\0", "?? new.py\n"]), \
                mock.patch.object(dep_scan, "_expand", side_effect=fake_expand):
            tracked, untracked = dep_scan.file_sets()

        self.assertEqual(tracked, ["tracked.py"])
        self.assertEqual(untracked, ["new.py"])


class ModuleMapTests(unittest.TestCase):
    def test_bare_namespace_package_name_is_local(self):
        mapping = dep_scan.module_map(["tools/dep_scan.py"])
        self.assertIn("tools", mapping)

    def test_import_name_is_mapped_to_distribution_name(self):
        self.assertEqual(dep_scan.dist_name("docx"), "python-docx")


if __name__ == "__main__":
    unittest.main()
