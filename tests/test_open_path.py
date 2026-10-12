#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the cross-platform desktop handler.

The "open output directory" and "open log" buttons used to call
``os.startfile`` unconditionally, which works on Windows and raises
``AttributeError`` on macOS and Linux.  These tests pin the mapping for all
three platforms from every host, and scan the shipped modules so a raw
launcher call cannot come back.
"""

import os
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHARED = os.path.join(ROOT, "shared")
sys.path.insert(0, SHARED)

from utils.open_path import open_path, platform_launcher  # noqa: E402


def _forbidden(*_args, **_kwargs):
    raise AssertionError("os.startfile is a Windows-only API")


class _RecordingPopen:
    """Record the argv of every launcher spawn instead of starting it."""

    calls = []
    fail = False

    def __init__(self, argv, *args, **kwargs):
        if type(self).fail:
            raise OSError("no such helper")
        type(self).calls.append(list(argv))


class PlatformLauncherTests(unittest.TestCase):
    def test_windows_needs_no_external_command(self):
        self.assertIsNone(platform_launcher("win32"))

    def test_macos_uses_open(self):
        self.assertEqual(platform_launcher("darwin"), "open")

    def test_the_other_platforms_use_xdg_open(self):
        for name in ("linux", "freebsd13", "openbsd7", "sunos5"):
            self.assertEqual(platform_launcher(name), "xdg-open", name)

    def test_default_follows_the_running_platform(self):
        name = sys.platform
        if name == "win32":
            expected = None
        elif name == "darwin":
            expected = "open"
        else:
            expected = "xdg-open"
        self.assertEqual(platform_launcher(), expected)


class OpenPathTests(unittest.TestCase):
    def setUp(self):
        _RecordingPopen.calls = []
        _RecordingPopen.fail = False
        self._real_popen = subprocess.Popen
        subprocess.Popen = _RecordingPopen

    def tearDown(self):
        subprocess.Popen = self._real_popen

    def test_macos_opens_with_open(self):
        self.assertTrue(open_path("/tmp/out", platform="darwin"))
        self.assertEqual(_RecordingPopen.calls, [["open", "/tmp/out"]])

    def test_linux_opens_with_xdg_open(self):
        self.assertTrue(open_path("/tmp/out", platform="linux"))
        self.assertEqual(_RecordingPopen.calls, [["xdg-open", "/tmp/out"]])

    def test_macos_never_calls_startfile(self):
        self._swap_startfile(_forbidden)
        try:
            self.assertTrue(open_path("/tmp/out", platform="darwin"))
        finally:
            self._restore_startfile()

    def test_windows_calls_startfile_and_no_launcher(self):
        seen = []
        self._swap_startfile(seen.append)
        try:
            self.assertTrue(open_path(r"C:\out", platform="win32"))
        finally:
            self._restore_startfile()
        self.assertEqual(seen, [r"C:\out"])
        self.assertEqual(_RecordingPopen.calls, [])

    def test_a_missing_launcher_is_reported_not_raised(self):
        _RecordingPopen.fail = True
        self.assertFalse(open_path("/tmp/out", platform="darwin"))

    def _swap_startfile(self, replacement):
        self._original_startfile = getattr(os, "startfile", None)
        os.startfile = replacement

    def _restore_startfile(self):
        if self._original_startfile is None:
            del os.startfile
        else:
            os.startfile = self._original_startfile


class NoRawLauncherTests(unittest.TestCase):
    """Only the helper module may name a platform launcher.

    A raw call is the defect this module removes: it works on the machine the
    author tested on and breaks silently on the other two.
    """

    ALLOWED = {os.path.join("shared", "utils", "open_path.py")}
    SKIP_DIRS = {
        ".codex", ".codex_tmp", ".git", ".venv", ".venv310", "backup",
        "build", "build-windows", "example", "external_tools", "genome_index",
        "logs", "models", "native", "node_modules", "out", "output",
        "resource", "scy-test", "tests", "__pycache__",
    }
    NEEDLES = ("os.startfile", '"xdg-open"', "'xdg-open'")

    def test_no_raw_launcher_outside_the_helper(self):
        offenders = []
        for base, dirs, files in os.walk(ROOT):
            dirs[:] = [d for d in dirs if d not in self.SKIP_DIRS]
            for name in files:
                if not name.endswith(".py"):
                    continue
                path = os.path.join(base, name)
                rel = os.path.relpath(path, ROOT)
                if rel in self.ALLOWED:
                    continue
                with open(path, encoding="utf-8", errors="replace") as handle:
                    text = handle.read()
                if any(needle in text for needle in self.NEEDLES):
                    offenders.append(rel)
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
