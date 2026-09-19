#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the TIGER Cas13d predictor and its scoring integration.

These tests are runtime-independent: they exercise the two-channel one-hot
encoding, the score calibration mapping, the Cas13 off-target aggregation and
the ``compute_guide_scores`` fallback/use wiring without requiring TensorFlow.
"""

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))

import numpy as np  # noqa: E402

import scoring.model_registry as model_registry  # noqa: E402
import scoring.tiger_model as tiger_model  # noqa: E402
from scoring.scoring import compute_guide_scores  # noqa: E402


GUIDE = "ACCGCCACGTTCTCCGCGTCCTG"  # 23 nt


class TigerEncodingTests(unittest.TestCase):
    def test_input_vector_shape_and_padding(self):
        vec = tiger_model.build_input_vector(GUIDE)
        self.assertEqual(vec.shape, (208,))
        self.assertEqual(vec.dtype, np.float32)
        target_ch = vec[:104].reshape(26, 4)
        guide_ch = vec[104:].reshape(26, 4)
        # The 3 N-context positions are all-zero (OOV -> no one-hot).
        self.assertEqual(float(target_ch[:3].sum()), 0.0)
        self.assertEqual(float(guide_ch[:3].sum()), 0.0)
        # Only the 23 real nucleotides carry a one-hot.
        self.assertEqual(float(target_ch.sum()), 23.0)
        self.assertEqual(float(guide_ch.sum()), 23.0)
        # TIGER encodes the guide channel as the complement of the protospacer
        # (the kit stores the forward protospacer, not the biological crRNA).
        expected_guide = "NNN" + tiger_model._complement(GUIDE)
        self.assertTrue(np.allclose(guide_ch.reshape(-1),
                                    tiger_model._one_hot(expected_guide).reshape(-1)))

    def test_length_guard(self):
        with self.assertRaises(ValueError):
            tiger_model.build_input_vector("ACGT")

    def test_scores_map_into_unit_interval(self):
        predictor = tiger_model.TigerPredictor.__new__(tiger_model.TigerPredictor)
        class _Row:
            def __getitem__(self, name):
                if name == "a":
                    return -9.499261558421303
                return 5.692586365383111

        class _Iloc:
            def __getitem__(self, _index):
                return _Row()

        class _Params:
            iloc = _Iloc()

        predictor.scoring_params = _Params()
        # Directly exercise the affine + sigmoid score mapping with a stub LFC.
        scores = predictor._score(np.array([-3.0, 0.0, 3.0]))
        for value in scores:
            self.assertGreaterEqual(float(value), 0.0)
            self.assertLessEqual(float(value), 1.0)


class TigerOffTargetTests(unittest.TestCase):
    def test_returns_none_when_unavailable(self):
        with mock.patch.object(
                tiger_model.TigerPredictor, "available", return_value=False):
            result = tiger_model.cas13_off_target_specificity(GUIDE, [("A", "")])
        self.assertIsNone(result)

    def test_no_off_targets_is_perfect(self):
        with mock.patch.object(
                tiger_model.TigerPredictor, "available", return_value=True):
            result = tiger_model.cas13_off_target_specificity(GUIDE, [])
        self.assertEqual(result, 1.0)

    def test_aggregation_uses_zero_mismatch_as_primary(self):
        off_pairs = [
            (GUIDE, ""),                      # 0 mm -> primary
            (GUIDE[:22] + "A", ""),           # 1 mm -> off-target
        ]

        class _StubPredictor:
            def predict_lfc_for_targets(self, guide, target_windows):
                return np.array([1.0, 1.0], dtype=np.float32)

            def _calibrate(self, lfc, num_mismatches):
                return np.asarray(lfc, dtype=np.float64)

            def _score(self, calibrated):
                return np.array([0.9, 0.8], dtype=np.float32)

        with mock.patch.object(
                tiger_model.TigerPredictor, "available", return_value=True):
            with mock.patch.object(
                    tiger_model.TigerPredictor, "get",
                    return_value=_StubPredictor()):
                result = tiger_model.cas13_off_target_specificity(
                    GUIDE, off_pairs, assume_one_primary=True)
        # total = 0.9 + 0.8 - 1.0 (primary removed) = 0.7 -> 1/(1+0.7)
        self.assertAlmostEqual(result, 1.0 / 1.7, places=6)


class TigerScoringIntegrationTests(unittest.TestCase):
    def test_registry_entry(self):
        self.assertIn("tiger", model_registry.MODELS)
        info = model_registry.MODELS["tiger"]
        self.assertEqual(info["type"], "savedmodel_dir")
        self.assertEqual(info["role"], "on_target")
        self.assertEqual(info["runtime"], "tensorflow")
        self.assertEqual(info["protein"], "cas13")
        self.assertTrue(model_registry.is_downloadable(info))

    def test_falls_back_when_tiger_unavailable(self):
        with mock.patch.object(
                tiger_model.TigerPredictor, "available", return_value=False):
            result = compute_guide_scores(
                GUIDE, [("ACCGCCACGTTCTCCGCGTCCTA", "")],
                nuclease="cas13", preset_key="cas13", target_type="rna",
                on_target_model="tiger", off_target_model="tiger")
        # The CFD-style PFS rule replaces the deep model when it is unavailable.
        self.assertEqual(result["on_target_model"], "cas13_pfs")
        self.assertEqual(result["off_target_model"], "cas13_pfs")
        self.assertEqual(result["tiger_on_target"], "")
        self.assertEqual(result["tiger_off_target"], "")

    def test_pfs_fallback_is_deterministic(self):
        from scoring.cas13_scoring import (cas13_pfs_on_target_score,
                                           cas13_pfs_off_target_specificity)
        score, model, features = cas13_pfs_on_target_score(
            "UUUAAAUUAAAUUAAAUUAAA", flank_base="A")
        self.assertEqual(model, "cas13_pfs")
        self.assertAlmostEqual(score, cas13_pfs_on_target_score(
            "UUUAAAUUAAAUUAAAUUAAA", flank_base="A")[0], places=6)
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 1.0)
        # A 5' G PFS is penalised relative to a non-G (H) PFS.
        good = cas13_pfs_on_target_score("UUUAAAUUAAAUUAAAUUAAA", flank_base="A")[0]
        bad = cas13_pfs_on_target_score("UUUAAAUUAAAUUAAAUUAAA", flank_base="G")[0]
        self.assertGreater(good, bad)
        # Off-target: perfect match is the primary and is subtracted.
        off_pairs = [(GUIDE, "A"), (GUIDE[:22] + "A", "A")]
        spec = cas13_pfs_off_target_specificity(GUIDE, off_pairs)
        self.assertGreater(spec, 0.0)
        self.assertLessEqual(spec, 1.0)

    def test_uses_tiger_when_available(self):
        stub = type("Stub", (), {
            "score_guide": lambda self, s, window=None: 0.8})()
        with mock.patch.object(
                tiger_model.TigerPredictor, "available", return_value=True):
            with mock.patch.object(
                    tiger_model.TigerPredictor, "get", return_value=stub):
                with mock.patch.object(
                        tiger_model, "cas13_off_target_specificity",
                        return_value=0.6):
                    result = compute_guide_scores(
                        GUIDE, [("ACCGCCACGTTCTCCGCGTCCTA", "")],
                        nuclease="cas13", preset_key="cas13", target_type="rna",
                        on_target_model="tiger", off_target_model="tiger")
        self.assertEqual(result["on_target_model"], "tiger13")
        self.assertEqual(result["off_target_model"], "tiger13")
        self.assertAlmostEqual(result["on_target_score"], 0.8, places=6)
        self.assertAlmostEqual(result["off_target_specificity"], 0.6, places=6)
        self.assertAlmostEqual(float(result["tiger_on_target"]), 0.8, places=6)
        self.assertAlmostEqual(float(result["tiger_off_target"]), 0.6, places=6)


if __name__ == "__main__":
    unittest.main()
