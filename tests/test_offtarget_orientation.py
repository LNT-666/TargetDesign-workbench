#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for plus/minus strand off-target scoring orientation."""

import os
import sys
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "shared"))

from search.blast_utils import (  # noqa: E402
    orient_off_target_pair,
    reverse_complement,
)


QUERY = "CCTAAAAAAAAAAAAAAAAAAAA"
RAW = QUERY
PAM = "GG"


class OffTargetOrientationTests(unittest.TestCase):
    def test_plus_guide_uses_plus_hit_as_is(self):
        off, pam = orient_off_target_pair(RAW, PAM, "+", "plus")
        self.assertEqual(off, QUERY)
        self.assertEqual(pam, "GG")

    def test_minus_guide_reverses_plus_hit(self):
        off, pam = orient_off_target_pair(RAW, PAM, "+", "minus")
        self.assertEqual(off, reverse_complement(QUERY))
        self.assertEqual(pam, reverse_complement("GG"))

    def test_plus_guide_reverses_minus_hit(self):
        off, pam = orient_off_target_pair(RAW, PAM, "-", "plus")
        self.assertEqual(off, reverse_complement(QUERY))
        self.assertEqual(pam, reverse_complement("GG"))

    def test_minus_guide_uses_minus_hit_as_is(self):
        off, pam = orient_off_target_pair(RAW, PAM, "-", "minus")
        self.assertEqual(off, QUERY)
        self.assertEqual(pam, "GG")


if __name__ == "__main__":
    unittest.main()
