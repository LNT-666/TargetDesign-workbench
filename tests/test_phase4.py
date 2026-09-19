#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Phase 4 tests: ViennaRNA wrappers, Cas13 RNA scoring and rule tables."""

import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHARED = os.path.join(ROOT, "shared")
sys.path.insert(0, SHARED)

import scoring.cas13_scoring as cas13_scoring  # noqa: E402
import scoring.non_cas9_rules as non_cas9_rules  # noqa: E402
import scoring.rna_utils as rna_utils  # noqa: E402
from scoring.scoring import compute_guide_scores  # noqa: E402


class _FakeTempDir:
    def __init__(self, path):
        self.path = path

    def __enter__(self):
        return self.path

    def __exit__(self, *args):
        return False


class NonCas9RuleTests(unittest.TestCase):
    def test_rules_are_traceable(self):
        for key in ("cas12a", "cas12b", "cas14a", "cas13", "tnpb"):
            rules = non_cas9_rules.get_rules(key)
            self.assertIsNotNone(rules)
            self.assertTrue(rules["source"])
            self.assertTrue(rules["source_url"].startswith("https://"))

        self.assertIsNone(non_cas9_rules.get_rules("crispri"))

    def test_cas9_and_custom_have_no_rule_table(self):
        self.assertIsNone(non_cas9_rules.get_rules("cas9"))
        self.assertIsNone(non_cas9_rules.get_rules("custom"))

    def test_summary_includes_source(self):
        summary = non_cas9_rules.rule_summary_text("cas12a")
        self.assertIn("seed 1-6", summary)
        self.assertIn("Zetsche", summary)


class RnaUtilsTests(unittest.TestCase):
    def test_missing_vienna_returns_none(self):
        ok, _mode = rna_utils.vienna_available()
        if not ok:
            self.assertIsNone(rna_utils.rnafold_mfe("ACGUACGUACGU"))
            self.assertIsNone(rna_utils.rna_duplex_mfe("ACGU", "ACGU"))
            self.assertIsNone(rna_utils.sequence_accessibility("ACGUACGUACGU"))

    def test_parse_rnafold_output(self):
        output = "ACGUACGU\n((((....)))) (-5.40)\n"
        with mock.patch.object(rna_utils, "_run_vienna",
                               return_value=output):
            self.assertAlmostEqual(rna_utils.rnafold_mfe("ACGUACGU"), -5.40)
            self.assertEqual(rna_utils.rnafold_structure("ACGUACGU"),
                             "((((....))))")

    def test_parse_rnaplfold_output(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        with open(os.path.join(tmp, "plfold_lunp"), "w",
                  encoding="utf-8") as handle:
            handle.write("1 1 0.90\n2 2 0.80\n3 3 0.70\n")
        with mock.patch.object(rna_utils, "_run_vienna",
                               return_value="ok"), \
                mock.patch("tempfile.TemporaryDirectory",
                           return_value=_FakeTempDir(tmp)):
            probs = rna_utils.rnaplfold_unpaired("ACGUACGUACGU")
        self.assertEqual(probs, [0.9, 0.8, 0.7])

    def test_parse_duplex_and_cofold_output(self):
        with mock.patch.object(rna_utils, "_run_vienna",
                               return_value="-6.50  &...&  \n"):
            self.assertAlmostEqual(rna_utils.rna_duplex_mfe("ACGU", "ACGU"),
                                   -6.50)
        with mock.patch.object(rna_utils, "_run_vienna",
                               return_value="ACGU&ACGU\n..((..)) ( -8.20)\n"):
            self.assertAlmostEqual(rna_utils.rna_cofold_mfe("ACGU", "ACGU"),
                                   -8.20)


class Cas13ScoringTests(unittest.TestCase):
    def test_fallback_contract(self):
        score, model, features = cas13_scoring.cas13_on_target_score(
            "UUUAAAUUAAAUUAAAUUAA", "cas13")
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 1.0)
        self.assertIn(model, ("cas13_u_rich", "vienna_rna"))
        for key in ("guide_mfe", "guide_accessibility",
                    "target_accessibility", "dr_spacer_duplex_mfe",
                    "dr_spacer_penalty", "perturbation_mfe"):
            self.assertIn(key, features)
        self.assertTrue(features["dr_source"])

    def test_vienna_path_returns_features(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        with open(os.path.join(tmp, "plfold_lunp"), "w",
                  encoding="utf-8") as handle:
            handle.write("1 1 0.90\n2 2 0.85\n3 3 0.80\n")

        def fake_run(tool, args, input_text=None, cwd=None, timeout=60):
            if tool == "RNAfold":
                return "ACGUACGU\n((((....)))) (-5.40)\n"
            if tool == "RNAplfold":
                return "ok"
            if tool == "RNAduplex":
                return "-4.00  &...&  \n"
            if tool == "RNAcofold":
                return "ACGU&ACGU\n..((..)) ( -8.20)\n"
            return None

        with mock.patch.object(rna_utils, "_run_vienna",
                               side_effect=fake_run), \
                mock.patch.object(rna_utils, "vienna_available",
                                  return_value=(True, "command-line")), \
                mock.patch("tempfile.TemporaryDirectory",
                           return_value=_FakeTempDir(tmp)):
            score, model, features = cas13_scoring.cas13_on_target_score(
                "ACGUACGUACGUACGUACGU", "cas13")
        self.assertEqual(model, "vienna_rna")
        self.assertIsNotNone(features["guide_mfe"])
        self.assertIsNotNone(features["dr_spacer_duplex_mfe"])
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 1.0)


class ScoringIntegrationTests(unittest.TestCase):
    def test_cas13_output_contract(self):
        result = compute_guide_scores(
            "UUUAAAUUAAAUUAAAUUAA", [],
            nuclease="cas13", preset_key="cas13", target_type="rna")
        self.assertIn(result["on_target_model"],
                      ("cas13_u_rich", "vienna_rna"))
        self.assertIn("rule_source", result)
        self.assertIn("CHOPCHOP", result["rule_source"])
        self.assertIn("rna_features", result)
        self.assertIn("guide_mfe", result["rna_features"])

    def test_cas12a_rule_traceability(self):
        result = compute_guide_scores(
            "TAGCTAGCTAGCTAACGGTT", [],
            nuclease="cas12a", preset_key="cas12a")
        self.assertIn("Zetsche", result["rule_source"])
        self.assertTrue(result["rule_reference"].startswith("https://"))


if __name__ == "__main__":
    unittest.main()
