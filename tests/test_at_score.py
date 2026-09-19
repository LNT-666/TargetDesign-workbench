#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for shared AT-score helpers and the Y-ZBP occurrence adapter."""

import importlib.util
import os
import sys
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHARED = os.path.join(ROOT, "shared")
if SHARED not in sys.path:
    sys.path.insert(0, SHARED)

from scoring.at_score import (  # noqa: E402
    compute_at_score,
    compute_at_score_from_flank,
    should_output_at_score,
)


def _load_blast_combined():
    path = os.path.join(ROOT, "Target_xbp_Y_zbp_Target", "blast_combined.py")
    spec = importlib.util.spec_from_file_location("blast_combined_at_score", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class AtScoreTests(unittest.TestCase):
    def test_legacy_query_window_score(self):
        self.assertEqual(
            compute_at_score("AAGGGG", "upstream", "plus", "GGG", "CCC", 3),
            3,
        )
        self.assertEqual(
            compute_at_score("GGGAAG", "upstream", "minus", "GGG", "CCC", 3),
            1,
        )

    def test_side_preset_controls_output(self):
        self.assertTrue(should_output_at_score("preset", "tnpb"))
        self.assertFalse(should_output_at_score("free", "tnpb"))
        self.assertTrue(
            should_output_at_score("free", "custom", side_preset="tnpb"))
        self.assertFalse(
            should_output_at_score("preset", "tnpb", side_preset="cas9"))

    def test_y_occurrence_adapter_uses_motif_side_and_strand(self):
        mod = _load_blast_combined()
        self.assertEqual(
            mod._at_score_from_occurrence(
                "AAGTTGAT", [["chr1", "plus", 0, 8, 3, 8]]),
            3,
        )
        self.assertEqual(
            mod._at_score_from_occurrence(
                "TTGATAAG", [["chr1", "plus", 0, 8, 0, 5]]),
            1,
        )
        self.assertEqual(
            mod._at_score_from_occurrence(
                "ATCAAAAG", [["chr1", "minus", 0, 8, 0, 5]]),
            3,
        )


if __name__ == "__main__":
    unittest.main()
