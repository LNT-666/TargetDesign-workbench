#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Phase 5 tests: offline TnpB/omegaRNA rules and CROPSR."""

import os
import sys
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHARED = os.path.join(ROOT, "shared")
sys.path.insert(0, SHARED)

import scoring.tnpb_scoring as tnpb_scoring  # noqa: E402
from scoring.scoring import compute_guide_scores  # noqa: E402


class TnpbOfflineTests(unittest.TestCase):
    def test_omega_rna_rules_contract(self):
        score, model, features = tnpb_scoring.omega_rna_on_target_score(
            "TAGCTAGCTAGCTAACG",
            direct_repeat="AACCCTACCAACTGGTCGGGGTTTGAAC")
        self.assertEqual(model, "omega_rna_rules")
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 1.0)
        for key in ("spacer_len", "spacer_len_score", "gc",
                    "guide_hairpin_len", "guide_structure_penalty",
                    "repeat_hairpin_len", "repeat_hairpin_score",
                    "omega_model"):
            self.assertIn(key, features)

    def test_offline_default_in_scoring(self):
        result = compute_guide_scores(
            "TAGCTAGCTAGCTAACG", [],
            nuclease="tnpb", tnpb_subtype="isdra2",
            preset_key="tnpb")
        self.assertEqual(result["on_target_model"], "omega_rna_rules")
        self.assertIn("tnpb_features", result)
        self.assertEqual(
            result["tnpb_features"]["omega_model"], "omega_rna_rules")
        self.assertIn("Karvelis", result["rule_source"])

    def test_teep_selection_overrides_offline_default(self):
        with mock.patch(
                "scoring.scoring.teep_on_target_score", return_value=0.42):
            result = compute_guide_scores(
                "TAGCTAGCTAGCTAACG", [],
                nuclease="tnpb", tnpb_subtype="isdra2",
                reference_only_model="teep", preset_key="tnpb")
        self.assertEqual(result["on_target_model"], "teep_reference_only")
        self.assertEqual(result["on_target_score"], 0.42)
        self.assertTrue(result["reference_only"])

    def test_teep_falls_back_when_online_model_unavailable(self):
        with mock.patch(
                "scoring.scoring.teep_on_target_score", return_value=None):
            result = compute_guide_scores(
                "TAGCTAGCTAGCTAACG", [],
                nuclease="tnpb", tnpb_subtype="isdra2",
                reference_only_model="teep", preset_key="tnpb")
        self.assertEqual(result["on_target_model"], "teep_fallback")
        self.assertTrue(result["reference_only"])


class CropsrTests(unittest.TestCase):
    def test_model_note_and_determinism(self):
        first = compute_guide_scores(
            "GAACACAAAGCATAGACTGC", [],
            nuclease="cas9", on_target_model="cropsr")
        second = compute_guide_scores(
            "GAACACAAAGCATAGACTGC", [],
            nuclease="cas9", on_target_model="cropsr")
        self.assertIn("cropsr_model_note", first)
        self.assertIn("published CROPSR", first["cropsr_model_note"])
        self.assertEqual(first["on_target_score"], second["on_target_score"])


if __name__ == "__main__":
    unittest.main()
