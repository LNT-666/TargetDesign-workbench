#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Focused tests for the new preset, guide design and scoring modules."""

import os
import sys
import tempfile
import unittest
import argparse
from unittest import mock

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHARED = os.path.join(ROOT, "shared")
sys.path.insert(0, SHARED)

from design.system_presets import (  # noqa: E402
    apply_preset,
    get_preset,
    resolve_preset_pam,
    rule_summary,
)
from design.guide_design import find_guides, filter_guides  # noqa: E402
from scoring.scoring import (  # noqa: E402
    ALL_OFF_TARGET_MODELS, ALL_ON_TARGET_MODELS,
    TRADITIONAL_MODELS,
    aggregate_off_target_specificity, compute_guide_scores,
    compute_off_target_activities,
    apply_guide_feature_columns, GUIDE_FEATURE_COLUMNS,
    MODEL_NAME_COLUMNS,
    OUTPUT_GUIDE_FEATURE_COLUMNS,
    model_choices_for_preset,
)
from design.library_utils import deduplicate_guides  # noqa: E402
from design.library_pipeline import enforce_preset_pam_requirement  # noqa: E402
from search.exact_offtarget import reverse_complement, levenshtein  # noqa: E402
from search.exact_offtarget import search_guides  # noqa: E402
from scoring.deep_models import (make_24mer, encode_base_pair, encode_single_base,
                         CrisprMPredictor, crispr_m_status)  # noqa: E402
import scoring.deep_models as deep_models  # noqa: E402
import scoring.model_registry as model_registry  # noqa: E402


class PresetTests(unittest.TestCase):
    def test_cas12a_metadata(self):
        preset = get_preset("cas12a")
        self.assertEqual(preset["pam"], "TTTN")
        self.assertEqual(preset["spacer_len"], 24)
        self.assertEqual(preset["pam_side"], "5prime")
        self.assertEqual(preset["seed_start"], 1)
        self.assertEqual(preset["seed_end"], 6)

    def test_apply_preset_keeps_user_value(self):
        merged = apply_preset("cas12a", {"spacer_len": 25})
        self.assertEqual(merged["spacer_len"], 25)
        self.assertEqual(merged["pam"], "TTTN")

    def test_rule_summary(self):
        self.assertIn("seed 1-6", rule_summary("cas12a"))

    def test_tnpb_preset_does_not_assume_a_tam(self):
        preset = get_preset("tnpb")
        self.assertEqual(preset["tnpb_subtype"], "unknown")
        self.assertEqual(preset["pam"], "")
        self.assertFalse(preset["pam_required"])

    def test_tnpb_isdra2_subtype_turns_on_the_classic_tam(self):
        # ISDra2 is a subtype option inside the single ``tnpb`` preset, not a
        # second preset; selecting it enables the classic 5' TTGAT TAM.
        self.assertEqual(
            resolve_preset_pam("tnpb", "isdra2"),
            ("TTGAT", "5prime", True),
        )
        self.assertEqual(
            resolve_preset_pam("tnpb", "unknown"), ("", "", False)
        )

    def test_pam_required_preset_forces_hard_filter(self):
        args = argparse.Namespace(mode="preset", pam="TTTN", require_pam=False)
        enforce_preset_pam_requirement(args, get_preset("cas12a"))
        self.assertTrue(args.require_pam)

    def test_free_mode_keeps_manual_pam_choice(self):
        args = argparse.Namespace(mode="free", pam="NGG", require_pam=False)
        enforce_preset_pam_requirement(args, get_preset("custom"))
        self.assertFalse(args.require_pam)


class GuideDesignTests(unittest.TestCase):
    def test_cas12a_guide(self):
        seq = "AAATTTGTAGCTAGCTAGCTAACGGTTTT"
        guides = find_guides(seq, spacer_len=20, pam="TTTV",
                             pam_side="5prime", motif="TAGCT")
        self.assertEqual(len(guides), 1)
        self.assertEqual(guides[0]["guide_seq"], "TAGCTAGCTAGCTAACGGTT")
        self.assertEqual(guides[0]["motif_overlap"], 5)

    def test_no_pam_windows(self):
        seq = "A" * 20
        guides = find_guides(seq, spacer_len=20, pam=None, allow_reverse=False)
        self.assertEqual(len(guides), 1)

    def test_gc_filter(self):
        seq = "AAATTTGTAGCTAGCTAGCTAACGGTTTT"
        guides = find_guides(seq, spacer_len=20, pam="TTTV", pam_side="5prime")
        filtered = filter_guides(guides, gc_min=50, gc_max=70)
        self.assertLessEqual(len(filtered), len(guides))


class ScoringTests(unittest.TestCase):
    def test_model_registry_roles_and_runtime(self):
        self.assertIn("crispai", model_registry.MODELS)
        self.assertEqual(model_registry.MODELS["deepcrispr"]["role"],
                         "off_target")
        self.assertEqual(model_registry.MODELS["crispai"]["runtime"],
                         "pytorch")
        self.assertIn("deepcas12a", model_registry.MODELS)
        self.assertEqual(model_registry.MODELS["deepcas12a"]["role"],
                         "on_target")
        self.assertEqual(model_registry.MODELS["deepcas12a"]["runtime"],
                         "pytorch")
        self.assertIn("deepcpf1", model_registry.MODELS)
        self.assertEqual(model_registry.MODELS["deepcpf1"]["role"],
                         "on_target")
        self.assertEqual(model_registry.MODELS["deepcpf1"]["runtime"],
                         "numpy_h5py")
        self.assertTrue(model_registry.runtime_available("crispr_m"))
        self.assertIn(
            "crispai",
            model_registry.models_by_role("off_target", visible_only=True))

    def test_compute_guide_scores_output_contract(self):
        seq = "GAACACAAAGCATAGACTGC"
        off_pairs = [("GAACACAAAGCATAGACTGA", "NGG")]
        result = compute_guide_scores(
            seq, off_pairs, nuclease="cas9", off_target_model="cfd")
        expected_keys = {
            "off_target_specificity", "off_target_model",
            "off_target_model_note", "on_target_score", "on_target_model",
            "reference_only", "reference_note",
            "preset", "preset_label", "target_type",
        }
        self.assertTrue(expected_keys.issubset(result))
        for key in ("off_target_specificity", "on_target_score"):
            self.assertGreaterEqual(result[key], 0.0)
            self.assertLessEqual(result[key], 1.0)
        self.assertIsInstance(result["reference_only"], bool)
        self.assertIsInstance(result["reference_note"], str)
        self.assertIsInstance(result["off_target_model_note"], str)
        self.assertIn("cfd_specificity", result)
        self.assertIn("crispr_m_off_target", result)
        self.assertIn("deepcrispr_off_target", result)
        self.assertIn("crispai_off_target", result)
        again = compute_guide_scores(
            seq, off_pairs, nuclease="cas9", off_target_model="cfd")
        self.assertEqual(result, again)

    def test_compute_guide_scores_supports_multiple_on_target_models(self):
        seq = "GAACACAAAGCATAGACTGC"
        off_pairs = [("GAACACAAAGCATAGACTGA", "NGG")]
        result = compute_guide_scores(
            seq, off_pairs, nuclease="cas9",
            on_target_model="cropsr,rules", off_target_model="cfd")
        self.assertEqual(
            result["on_target_score_cropsr"], result["on_target_score"])
        self.assertIn("on_target_score_rules", result)
        self.assertIn("on_target_model_rules", result)

    def test_compute_guide_scores_supports_multiple_off_target_models(self):
        seq = "GAACACAAAGCATAGACTGC"
        off_pairs = [("GAACACAAAGCATAGACTGA", "NGG")]

        def fake_deep_result(_seq, _off_pairs, choice, _assume):
            if choice == "crispr_m":
                return 0.42, "crispr_m", ""
            return None

        with mock.patch(
            "scoring.scoring._deep_off_target_score",
            side_effect=fake_deep_result,
        ):
            result = compute_guide_scores(
                seq, off_pairs, nuclease="cas9",
                on_target_model="cropsr",
                off_target_model="cfd,crispr_m")
        self.assertEqual(
            result["off_target_specificity_cfd"],
            result["off_target_specificity"])
        self.assertEqual(result["off_target_specificity_crispr_m"], 0.42)
        self.assertEqual(result["off_target_model_crispr_m"], "crispr_m")

    def test_multiple_tnpb_models_keep_omega_and_teep_separate(self):
        with mock.patch(
            "scoring.scoring.teep_on_target_score",
            return_value=0.8,
        ):
            result = compute_guide_scores(
                "TTATTATTATTATTATTATT",
                [],
                nuclease="tnpb",
                tnpb_subtype="isdra2",
                reference_only_model="teep",
                on_target_model="omega,teep",
                off_target_model="identity")
        self.assertIn("on_target_score_omega", result)
        self.assertEqual(result["on_target_score_teep"], 0.8)
        self.assertEqual(result["on_target_model_teep"], "teep_reference_only")
        self.assertIn("on_target_score_teep", result)

    @mock.patch("scoring.deep_models.crispr_m_status", return_value="ready")
    @mock.patch("scoring.deep_models.DeepCrisprPredictor.available",
                return_value=True)
    def test_deep_model_columns_filled_when_no_offtargets(
            self, _available, _status):
        seq = "GAACACAAAGCATAGACTGC"
        result = compute_guide_scores(
            seq, [], nuclease="cas9", off_target_model="crispr_m")
        self.assertEqual(result["off_target_model"], "crispr_m")
        self.assertEqual(result["off_target_specificity"], 1.0)
        self.assertEqual(result["crispr_m_off_target"], 1.0)
        self.assertEqual(result["deepcrispr_off_target"], "")

    def test_auto_models_report_concrete_model_columns(self):
        # A caller that leaves the models unset (batch default, CLI "auto")
        # must still surface the score columns under the concrete default
        # names; ``_auto`` is not a declared column, so it would be dropped.
        # The active preset wins over the nuclease, matching the scorer's
        # branch order for a TAM side whose preset differs from the run.
        for nuclease, preset_key, on_key, off_key in (
            ("cas9", None, "on_target_score_cropsr",
             "off_target_specificity_cfd"),
            ("tnpb", None, "on_target_score_omega",
             "off_target_specificity_identity"),
            ("cas9", "tnpb", "on_target_score_omega",
             "off_target_specificity_identity"),
        ):
            result = compute_guide_scores(
                "GAACACAAAGCATAGACTGC",
                [],
                nuclease=nuclease,
                preset_key=preset_key,
                on_target_model="auto",
                off_target_model="auto",
            )
            label = "%s/%s" % (nuclease, preset_key)
            self.assertIn(on_key, result, label)
            self.assertIn(off_key, result, label)
            self.assertNotIn("on_target_score_auto", result, label)
            self.assertNotIn("off_target_specificity_auto", result, label)

    def test_apply_guide_feature_columns_attaches_library_columns(self):
        seq = "GAACACAAAGCATAGACTGC"
        off_pairs = [("GAACACAAAGCATAGACTGA", "NGG")]
        scores = compute_guide_scores(
            seq,
            off_pairs,
            nuclease="cas9",
            on_target_model="cropsr,rules",
            off_target_model="cfd,crispr_m",
        )
        row = apply_guide_feature_columns({}, scores)
        self.assertTrue(
            all(key in row for key in GUIDE_FEATURE_COLUMNS))
        self.assertIn("on_target_score_cropsr", row)
        self.assertIn("off_target_specificity_cfd", row)
        self.assertIn("on_target_score_rules", row)
        self.assertIn("off_target_specificity_crispr_m", row)
        self.assertEqual(row["cfd_specificity"], scores["cfd_specificity"])
        self.assertEqual(
            row["crispr_m_off_target"], scores["crispr_m_off_target"])
        self.assertEqual(
            row["deepcrispr_off_target"], scores["deepcrispr_off_target"])
        self.assertEqual(row["rule_source"], scores.get("rule_source", ""))
        rna = scores.get("rna_features") or {}
        self.assertEqual(row["rna_model"], rna.get("rna_model", ""))

    def test_output_feature_columns_hide_internal_and_legacy_columns(self):
        hidden = {
            "reference_only",
            "reference_note",
            "rule_source",
            "rule_reference",
            "rule_summary",
            "subtype_note",
            "rna_model",
            "omega_model",
            "cfd_specificity",
            "crispr_m_off_target",
            "deepcrispr_off_target",
            "crispai_off_target",
            "deepcas12a_on_target",
            "deepcpf1_on_target",
            "tiger_on_target",
            "tiger_off_target",
        } | set(MODEL_NAME_COLUMNS)
        self.assertTrue(hidden.isdisjoint(OUTPUT_GUIDE_FEATURE_COLUMNS))

    def test_side_prefixed_model_columns_do_not_mix(self):
        seq = "GAACACAAAGCATAGACTGC"
        off_pairs = [("GAACACAAAGCATAGACTGA", "NGG")]
        left_scores = compute_guide_scores(
            seq,
            off_pairs,
            nuclease="cas9",
            on_target_model="cropsr",
            off_target_model="cfd",
        )
        right_scores = compute_guide_scores(
            seq,
            off_pairs,
            nuclease="cas12a",
            on_target_model="rules",
            off_target_model="rules",
        )
        item = {
            "left_%s" % key: value
            for key, value in apply_guide_feature_columns(
                {}, left_scores
            ).items()
        }
        item.update({
            "right_%s" % key: value
            for key, value in apply_guide_feature_columns(
                {}, right_scores
            ).items()
        })
        self.assertIn("left_off_target_specificity_cfd", item)
        self.assertIn("right_off_target_specificity_rules", item)
        self.assertEqual(item["left_off_target_specificity_rules"], "")
        self.assertEqual(item["right_off_target_specificity_cfd"], "")

    @mock.patch("scoring.deep_models.crispr_m_status", return_value="not_downloaded")
    @mock.patch("scoring.deep_models.DeepCrisprPredictor.available", return_value=False)
    def test_auto_fallback_when_models_missing(self, _available, _status):
        seq = "GAACACAAAGCATAGACTGC"
        off_pairs = [("GAACACAAAGCATAGACTGA", "NGG")]
        result = compute_guide_scores(seq, off_pairs, nuclease="cas9")
        self.assertEqual(result["off_target_model"], "cfd")
        self.assertEqual(result["off_target_model_note"], "")
        self.assertAlmostEqual(
            result["cfd_specificity"],
            aggregate_off_target_specificity(seq, off_pairs))
        self.assertAlmostEqual(
            result["off_target_specificity"],
            aggregate_off_target_specificity(seq, off_pairs))

    @mock.patch("scoring.deep_models.crispr_m_status", return_value="load_error")
    def test_explicit_crispr_m_fallback(self, _status):
        result = compute_guide_scores(
            "GAACACAAAGCATAGACTGC",
            [("GAACACAAAGCATAGACTGA", "NGG")],
            nuclease="cas9", off_target_model="crispr_m")
        self.assertEqual(result["off_target_model"], "crispr_m_unavailable")
        self.assertTrue(result["off_target_model_note"])

    @mock.patch("scoring.deep_models.DeepCrisprPredictor.available", return_value=False)
    def test_explicit_deepcrispr_fallback(self, _available):
        result = compute_guide_scores(
            "GAACACAAAGCATAGACTGC",
            [("GAACACAAAGCATAGACTGA", "NGG")],
            nuclease="cas9", off_target_model="deepcrispr")
        self.assertEqual(result["off_target_model"], "deepcrispr_unavailable")
        self.assertTrue(result["off_target_model_note"])

    def test_deep_off_target_activities_are_batched(self):
        seq = "GAACACAAAGCATAGACTGC"
        off_pairs = [
            ("GAACACAAAGCATAGACTGA", "NGG"),
            ("GAACACAAAGCATAGACTGT", "NGG"),
            ("GAACACAAAGCATAGACTGG", "NGG"),
        ]
        calls = []

        class FakeCrisprM:
            def predict_pairs(self, guide, off_spacers, pam=None):
                calls.append((guide, tuple(off_spacers), pam))
                return [0.2, 0.3, 0.4][:len(off_spacers)]

        with mock.patch(
            "scoring.deep_models.crispr_m_status",
            return_value="ready",
        ), mock.patch(
            "scoring.deep_models.CrisprMPredictor.get",
            return_value=FakeCrisprM(),
        ):
            result = compute_off_target_activities(
                seq, off_pairs,
                nuclease="cas9",
                off_target_model="crispr_m",
            )

        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][1], tuple(
            target for target, _pam in off_pairs
        ))
        self.assertEqual(result["activities"], [0.2, 0.3, 0.4])
        self.assertEqual(result["model"], "crispr_m")
        expected_specificity = 1.0 / (1.0 + 0.9)
        self.assertAlmostEqual(
            result["specificity"], expected_specificity)

    def test_deepcrispr_activities_batch_within_each_pam(self):
        seq = "GAACACAAAGCATAGACTGC"
        off_pairs = [
            ("GAACACAAAGCATAGACTGA", "AGG"),
            ("GAACACAAAGCATAGACTGT", "AGG"),
            ("GAACACAAAGCATAGACTGG", "CGG"),
        ]
        calls = []

        class FakeDeepCrispr:
            @classmethod
            def available(cls):
                return True

            def predict_pairs(self, guide, off_spacers, pam=None):
                calls.append((tuple(off_spacers), pam))
                return [0.1] * len(off_spacers)

        with mock.patch(
            "scoring.deep_models.DeepCrisprPredictor",
            FakeDeepCrispr,
        ):
            result = compute_off_target_activities(
                seq, off_pairs,
                nuclease="cas9",
                off_target_model="deepcrispr",
            )

        self.assertEqual(
            calls,
            [(
                (
                    "GAACACAAAGCATAGACTGA",
                    "GAACACAAAGCATAGACTGT",
                ),
                "AGG",
            ), (("GAACACAAAGCATAGACTGG",), "CGG")],
        )
        self.assertEqual(result["activities"], [0.1, 0.1, 0.1])
        self.assertEqual(result["model"], "deepcrispr")

    def test_cfd_scoring_does_not_probe_unselected_deep_models(self):
        seq = "GAACACAAAGCATAGACTGC"
        off_pairs = [("GAACACAAAGCATAGACTGA", "NGG")]
        with mock.patch(
            "scoring.deep_models.crispr_m_status",
        ) as crispr_status, mock.patch(
            "scoring.deep_models.DeepCrisprPredictor.available",
        ) as deepcrispr_available:
            result = compute_guide_scores(
                seq, off_pairs,
                nuclease="cas9",
                off_target_model="cfd",
            )
        self.assertEqual(result["off_target_model"], "cfd")
        crispr_status.assert_not_called()
        deepcrispr_available.assert_not_called()

    def test_precomputed_deep_activities_skip_model_inference(self):
        seq = "GAACACAAAGCATAGACTGC"
        off_pairs = [("GAACACAAAGCATAGACTGA", "NGG")]
        activity_data = {
            "activities": [0.2],
            "primary": [False],
            "specificity": 1.0 / 1.2,
            "model": "crispr_m",
            "reference_only": False,
        }
        with mock.patch(
            "scoring.scoring._deep_off_target_score",
        ) as deep_score:
            result = compute_guide_scores(
                seq, off_pairs,
                nuclease="cas9",
                off_target_model="crispr_m",
                precomputed_off_target_activities={
                    "crispr_m": activity_data,
                },
            )
        deep_score.assert_not_called()
        self.assertAlmostEqual(
            result["off_target_specificity"], activity_data["specificity"])
        self.assertEqual(result["off_target_model"], "crispr_m")

    def test_cas12a_preset_model(self):
        result = compute_guide_scores(
            "TAGCTAGCTAGCTAACGGTT",
            [("TAGCTAGCTAGCTAACGGTC", "GG")],
            nuclease="cas12a", preset_key="cas12a",
            seed_start=1, seed_end=6)
        self.assertEqual(result["preset"], "cas12a")
        self.assertIn("preset_", result["off_target_model"])

    def test_deepcas12a_registry_and_encoding(self):
        from scoring.deep_models import encode_deepcas12a_inputs
        seq = "CCCTTTTATAACTCCCAATTCCCCCCAATTCCTT"
        encoded = encode_deepcas12a_inputs(seq)
        self.assertEqual(encoded.shape, (6, 34))
        self.assertIsNone(encode_deepcas12a_inputs("ACGT"))

    def test_deepcas12a_fallback_when_model_missing(self):
        with mock.patch(
            "scoring.deep_models.deepcas12a_status", return_value="not_downloaded"
        ):
            result = compute_guide_scores(
                "TAGCTAGCTAGCTAACGGTT",
                [("TAGCTAGCTAGCTAACGGTC", "GG")],
                nuclease="cas12a", preset_key="cas12a",
                on_target_model="deepcas12a")
        self.assertEqual(result["on_target_model"], "deepcas12a_fallback")
        self.assertEqual(result["deepcas12a_on_target"], "")
        self.assertIn("deepcas12a_on_target", result)

    def test_deepcpf1_registry_and_encoding(self):
        from scoring.deepcpf1_forward import encode_seq
        encoded = encode_seq("TGACTTTGAATGGAGTCGTGAGCGCAAGAACGCT")
        self.assertEqual(encoded.shape, (34, 4))
        with self.assertRaises(ValueError):
            encode_seq("ACGT")

    def test_deepcpf1_fallback_when_model_missing(self):
        with mock.patch(
            "scoring.deep_models.deepcpf1_status", return_value="not_downloaded"
        ):
            result = compute_guide_scores(
                "TAGCTAGCTAGCTAACGGTT",
                [("TAGCTAGCTAGCTAACGGTC", "GG")],
                nuclease="cas12a", preset_key="cas12a",
                on_target_model="deepcpf1")
        self.assertEqual(result["on_target_model"], "deepcpf1_fallback")
        self.assertEqual(result["deepcpf1_on_target"], "")
        self.assertIn("deepcpf1_on_target", result)

    def test_cas13_uses_rna_bias(self):
        result = compute_guide_scores(
            "UUUAAAUUAAAUUAAAUUAA",
            [],
            nuclease="cas13", preset_key="cas13", target_type="rna")
        self.assertIn(result["on_target_model"],
                      ("cas13_u_rich", "vienna_rna"))

    def test_custom_nuc_auto_uses_generic_unverified_false(self):
        result = compute_guide_scores(
            "TAGCTAGCTAGCTAACGGTT",
            [("TAGCTAGCTAGCTAACGGTC", "GG")],
            nuclease="custom", preset_key="custom",
            on_target_model="auto", off_target_model="auto")
        self.assertEqual(result["on_target_model"], "nuc_features")
        self.assertEqual(result["off_target_model"], "identity_heuristic")
        self.assertFalse(result["reference_only"])
        self.assertEqual(result["reference_note"], "")

    def test_custom_rules_row_is_not_calibrated_reference(self):
        result = compute_guide_scores(
            "TAGCTAGCTAGCTAACGGTT",
            [("TAGCTAGCTAGCTAACGGTC", "GG")],
            nuclease="custom", preset_key="custom",
            on_target_model="rules", off_target_model="rules")
        self.assertEqual(result["off_target_model"], "identity_heuristic")
        self.assertEqual(result["calibration_status"], "uncalibrated")

    def test_custom_cfd_row_keeps_calibrated_reference(self):
        result = compute_guide_scores(
            "TAGCTAGCTAGCTAACGGTT",
            [("TAGCTAGCTAGCTAACGGTC", "GG")],
            nuclease="custom", preset_key="custom",
            on_target_model="rules", off_target_model="cfd")
        self.assertEqual(result["off_target_model"], "cfd_reference_only")
        self.assertEqual(result["calibration_status"], "calibrated_reference")

    def test_cas9_cfd_row_keeps_calibrated_reference(self):
        result = compute_guide_scores(
            "GAACACAAAGCATAGACTGC",
            [("GAACACAAAGCATAGACTGA", "NGG")],
            nuclease="cas9")
        self.assertEqual(result["off_target_model"], "cfd")
        self.assertEqual(result["calibration_status"], "calibrated_reference")

    def test_custom_nuc_cropsr_applied_as_reference_only(self):
        # 30mer so CROPSR can score it; the custom nuc makes it reference-only.
        seq = "CCCTTTTATAACTCCCAATTCCCCCCAATTCCTT"
        result = compute_guide_scores(
            seq, [], nuclease="custom", preset_key="custom",
            on_target_model="cropsr", off_target_model="rules")
        self.assertTrue(result["on_target_model"].endswith("_reference_only"))
        self.assertTrue(result["reference_only"])
        self.assertTrue(result["reference_note"])

    def test_custom_nuclease_overrides_pattern_preset_for_pair_sides(self):
        seq = "CCCTTTTATAACTCCCAATTCCCCCCAATTCCTT"
        result = compute_guide_scores(
            seq, [], nuclease="custom", preset_key="cas9",
            on_target_model="cropsr", off_target_model="crispai")
        self.assertEqual(result["preset"], "custom")
        self.assertEqual(
            result["on_target_model"], "CROPSR_reference_only")
        self.assertTrue(result["reference_only"])

    def test_custom_nuc_deepcpf1_fallback_reference_only(self):
        with mock.patch(
            "scoring.deep_models.deepcpf1_status", return_value="not_downloaded"
        ):
            result = compute_guide_scores(
                "TAGCTAGCTAGCTAACGGTT",
                [("TAGCTAGCTAGCTAACGGTC", "GG")],
                nuclease="custom", preset_key="custom",
                on_target_model="deepcpf1", off_target_model="cfd")
        self.assertEqual(result["on_target_model"], "deepcpf1_fallback")
        self.assertEqual(result["deepcpf1_on_target"], "")
        self.assertEqual(result["off_target_model"], "cfd_reference_only")
        self.assertTrue(result["reference_only"])
        self.assertTrue(result["reference_note"])

    def test_custom_nuc_crispr_m_fallback_cfd_reference_only(self):
        with mock.patch(
            "scoring.deep_models.crispr_m_status", return_value="not_downloaded"
        ):
            result = compute_guide_scores(
                "TAGCTAGCTAGCTAACGGTT",
                [("TAGCTAGCTAGCTAACGGTC", "GG")],
                nuclease="custom", preset_key="custom",
                on_target_model="rules", off_target_model="crispr_m")
        self.assertEqual(result["off_target_model"],
                         "crispr_m_unavailable_reference_only")
        self.assertTrue(result["reference_only"])

    def test_custom_model_catalog_contains_every_preset_model(self):
        custom_on = set(model_choices_for_preset("custom", "on_target"))
        custom_off = set(model_choices_for_preset("custom", "off_target"))
        self.assertEqual(custom_on, set(ALL_ON_TARGET_MODELS))
        self.assertEqual(custom_off, set(ALL_OFF_TARGET_MODELS))
        self.assertIn(
            "crispai", model_choices_for_preset("cas9", "off_target"))
        self.assertTrue({"cfd", "pfs", "rules"}.issubset(
            TRADITIONAL_MODELS))

    def test_custom_can_call_cas13_on_target_model(self):
        features = {"rna_model": "tiger13"}
        with mock.patch(
            "scoring.scoring._cas13_on_target_score",
            return_value=(0.72, "tiger13", features),
        ):
            result = compute_guide_scores(
                "UUUAAAUUAAAUUAAAUUAAAUU",
                [],
                nuclease="custom",
                preset_key="custom",
                on_target_model="tiger",
                off_target_model="identity")
        self.assertEqual(result["on_target_score"], 0.72)
        self.assertEqual(
            result["on_target_model"], "tiger13_reference_only")
        self.assertTrue(result["reference_only"])
        self.assertEqual(result["rna_features"], features)

    def test_custom_can_call_tnpb_omega_model(self):
        result = compute_guide_scores(
            "TTATTATTATTATTATTATT",
            [],
            nuclease="custom",
            preset_key="custom",
            on_target_model="omega",
            off_target_model="identity")
        self.assertEqual(
            result["on_target_model"], "omega_rna_rules_reference_only")
        self.assertTrue(result["reference_only"])
        self.assertEqual(
            result["tnpb_features"]["omega_model"], "omega_rna_rules")

    def test_custom_can_call_tnpb_teep_model(self):
        with mock.patch(
            "scoring.scoring.teep_on_target_score",
            return_value=0.66,
        ):
            result = compute_guide_scores(
                "TTATTATTATTATTATTATT",
                [],
                nuclease="custom",
                preset_key="custom",
                on_target_model="teep",
                off_target_model="identity")
        self.assertEqual(result["on_target_score"], 0.66)
        self.assertEqual(
            result["on_target_model"], "teep_reference_only")
        self.assertTrue(result["reference_only"])

    def test_custom_can_call_cas13_off_target_model(self):
        with mock.patch(
            "scoring.scoring._cas13_off_target_score",
            return_value=(0.41, "tiger13"),
        ):
            result = compute_guide_scores(
                "UUUAAAUUAAAUUAAAUUAAAUU",
                [],
                nuclease="custom",
                preset_key="custom",
                on_target_model="rules",
                off_target_model="tiger")
        self.assertEqual(
            result["off_target_model"], "tiger13_reference_only")
        self.assertEqual(result["off_target_specificity"], 0.41)
        self.assertEqual(result["tiger_off_target"], 0.41)
        self.assertTrue(result["reference_only"])

    def test_rules_are_default_and_cas13_pfs_is_explicit(self):
        cas9 = compute_guide_scores(
            "GAACACAAAGCATAGACTGC",
            [("GAACACAAAGCATAGACTGA", "NGG")],
            nuclease="cas9")
        self.assertEqual(cas9["on_target_model"], "rules_heuristic")
        self.assertEqual(cas9["off_target_model"], "cfd")

        cas13 = compute_guide_scores(
            "UUUAAAUUAAAUUAAAUUAAAUU",
            [],
            nuclease="cas13",
            preset_key="cas13",
            off_target_model="pfs")
        self.assertEqual(cas13["off_target_model"], "cas13_pfs")

    def test_subtype_note_annotates_subtype_only_models(self):
        seq = "UUUAAAUUAAAUUAAAUUAA"
        cas = compute_guide_scores(
            seq, [], nuclease="cas13", preset_key="cas13",
            target_type="rna")
        self.assertTrue(cas["subtype_note"])
        self.assertIn("cas13", cas["subtype_note"])

        tnp = compute_guide_scores(
            seq, [], nuclease="tnpb", tnpb_subtype="isdra2",
            preset_key="custom")
        self.assertTrue(tnp["subtype_note"])
        self.assertIn("TnpB", tnp["subtype_note"])
        self.assertIn("isdra2", tnp["subtype_note"])

        generic = compute_guide_scores(
            seq, [], nuclease="cas13/tnpb", preset_key="custom")
        self.assertTrue(generic["subtype_note"])

        cas9 = compute_guide_scores(seq, [], nuclease="cas9")
        self.assertEqual(cas9["subtype_note"], "")

class ExactOfftargetTests(unittest.TestCase):
    def test_reverse_complement(self):
        self.assertEqual(reverse_complement("ACGT"), "ACGT")
        self.assertEqual(reverse_complement("AACC"), "GGTT")

    def test_levenshtein(self):
        self.assertEqual(levenshtein("ACGT", "ACGT"), 0)
        self.assertEqual(levenshtein("ACGT", "ACGA"), 1)

    def test_max_mismatch_excludes_substitution_with_bulge_budget(self):
        guide = "AAAACCCCGGGGTTTTAAAA"
        off_target = "AAAACCCCGGGGTTTTAATA"
        with tempfile.NamedTemporaryFile(
                "w", suffix=".fa", delete=False, encoding="utf-8") as handle:
            handle.write(
                ">chr1\n"
                + "A" * 30 + guide + "TGG"
                + "A" * 20 + off_target + "TGG"
                + "A" * 30 + "\n"
            )
            fasta = handle.name
        try:
            hits = search_guides(
                [{"guide_seq": guide, "qid": "g0"}], fasta,
                max_mismatch=0, max_bulge=1, seed_len=12, seed_mm=1)
            observed = [
                (hit["start"], hit["mismatch"], hit["indel"])
                for hit in hits["g0"]
            ]
            self.assertIn((30, 0, 0), observed)
            self.assertTrue(all(mismatch == 0 for _, mismatch, _ in observed))
        finally:
            os.unlink(fasta)

    def test_search_guides_seed_longer_than_kmer(self):
        with tempfile.NamedTemporaryFile(
                "w", suffix=".fa", delete=False, encoding="utf-8") as handle:
            handle.write(">chr1\n")
            handle.write("A" * 30 + "GAACACAAAGCATAGACTGC" + "T" * 30 + "\n")
            fasta = handle.name
        try:
            hits = search_guides(
                [{"guide_seq": "GAACACAAAGCATAGACTGC", "qid": "g0"}],
                fasta, max_mismatch=1, seed_len=12, seed_mm=1)
            self.assertIn("g0", hits)
            self.assertEqual(hits["g0"][0]["mismatch"], 0)
        finally:
            os.unlink(fasta)


class DeepModelTests(unittest.TestCase):
    def test_model_statuses_are_fast(self):
        statuses = deep_models.model_statuses(load=False)
        self.assertIn("crispr_m", statuses)
        self.assertIn("deepcrispr", statuses)
        self.assertIn(statuses["crispr_m"],
                      ("not_downloaded", "ready", "load_error"))

    @unittest.skipUnless(
        deep_models.DeepCrisprPredictor.status() == "ready",
        "DeepCRISPR portable model not available")
    def test_deepcrispr_predictor_returns_score(self):
        predictor = deep_models.DeepCrisprPredictor.get()
        score = predictor.predict(
            "GCCTCTTTCCCACCCACCTT", "GTCTCTTTCCCAGCGACCTGG",
            pam="GGG", off_pam="GGG")
        self.assertTrue(np.isfinite(score))

    def test_24mer_and_encoding(self):
        on = make_24mer("GAACACAAAGCATAGACTGC", "NGG")
        off = make_24mer("GAACACAAAGCATAGACTGA", "NGG")
        self.assertEqual(len(on), 24)
        self.assertEqual(len(off), 24)
        self.assertEqual(encode_base_pair(on, off).shape, (24,))
        self.assertEqual(encode_single_base(on).shape, (24,))

    @unittest.skipUnless(crispr_m_status() == "ready",
                         "CRISPR-M model not available")
    def test_predictor_returns_probability(self):
        predictor = CrisprMPredictor.get()
        score = predictor.predict(
            "GAACACAAAGCATAGACTGC",
            "GAACACAAAGCATAGACTGA",
            "NGG")
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 1.0)


class HelperTests(unittest.TestCase):
    def test_deduplicate_guides(self):
        guides = [
            {"guide_seq": "A" * 20, "region": "r1"},
            {"guide_seq": "A" * 20, "region": "r2"},
            {"guide_seq": "C" * 20, "region": "r1"},
        ]
        unique = deduplicate_guides(guides)
        self.assertEqual(len(unique), 2)
        self.assertEqual(unique[0]["occurrence_count"], 2)


if __name__ == "__main__":
    unittest.main()
