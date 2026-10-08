#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the shared PROGRESS line parser."""

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHARED = os.path.join(ROOT, "shared")
sys.path.insert(0, ROOT)
sys.path.insert(0, SHARED)

from utils.log_utils import parse_progress_line  # noqa: E402


class ProgressParseTests(unittest.TestCase):
    def test_single_word_label(self):
        self.assertEqual(parse_progress_line("PROGRESS: reading 10"), (10, "reading"))

    def test_multi_word_label(self):
        self.assertEqual(
            parse_progress_line("PROGRESS: Off-target search (blast) 70"),
            (70, "Off-target search (blast)"))

    def test_surrounding_whitespace(self):
        self.assertEqual(parse_progress_line("  PROGRESS: writing 90 \n"), (90, "writing"))

    def test_missing_label_is_none(self):
        self.assertIsNone(parse_progress_line("PROGRESS: 40"))

    def test_non_numeric_percent_is_none(self):
        self.assertIsNone(parse_progress_line("PROGRESS: reading x"))

    def test_target_line_is_not_progress(self):
        self.assertIsNone(parse_progress_line("PROGRESS_TARGET: 1/2"))

    def test_plain_line_is_none(self):
        self.assertIsNone(parse_progress_line("plain log line"))
        self.assertIsNone(parse_progress_line(""))
        self.assertIsNone(parse_progress_line(None))


if __name__ == "__main__":
    unittest.main()
