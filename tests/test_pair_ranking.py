import os
import sys
import tempfile
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "shared"))

from scoring.pair_ranking import (  # noqa: E402
    PairRankingConfigError,
    normalize_pair_rank_policy,
    rank_prediction_only,
)
from scoring.pair_ranking_adapter import (  # noqa: E402
    apply_pair_rank_outputs,
    build_pair_compatibility,
    build_pair_input,
    build_side_input,
    collect_on_target_models,
    write_pair_rank_policy_file,
)


def policy(**overrides):
    values = {
        "e_high": 0.80,
        "e_min": 0.50,
        "e_fail": 0.20,
        "delta_default": 0.05,
        "b_low": 0.40,
        "b_high": 0.80,
        "m_low": 0.20,
        "m_high": 0.45,
        "h_risk": 0.70,
        "h_max": 1,
    }
    values.update(overrides)
    return values


def model(name, score, calibrated=True, applicable=True,
          is_fallback=False, reference_only=False):
    return {
        "name": name,
        "score": score,
        "applicable": applicable,
        "calibrated": calibrated,
        "is_fallback": is_fallback,
        "reference_only": reference_only,
    }


def hit(locus, score=None, upper=None, forbidden=False, is_bulge=False,
        bulge_calibrated=False):
    return {
        "locus_id": locus,
        "score": score,
        "upper": upper,
        "forbidden": forbidden,
        "is_bulge": is_bulge,
        "bulge_calibrated": bulge_calibrated,
    }


def side(models, hits=None, valid=True, search_complete=True,
         aggregate_specificity=None):
    return {
        "valid": valid,
        "search_complete": search_complete,
        "on_models": models,
        "off_hits": [] if hits is None else hits,
        "aggregate_specificity": aggregate_specificity,
    }


def pair(pair_id, left, right, hard_fail=False, soft_warnings=None,
         search_complete=True):
    return {
        "pair_id": pair_id,
        "left": left,
        "right": right,
        "compatibility": {
            "hard_fail": hard_fail,
            "soft_warnings": soft_warnings or [],
        },
        "search_complete": search_complete,
    }


class PolicyTests(unittest.TestCase):
    def test_policy_must_be_complete(self):
        with self.assertRaises(PairRankingConfigError):
            normalize_pair_rank_policy({"e_high": 0.8})

    def test_delta_default_must_not_be_zero(self):
        with self.assertRaises(PairRankingConfigError):
            normalize_pair_rank_policy(policy(delta_default=0))

    def test_policy_order_is_validated(self):
        with self.assertRaises(PairRankingConfigError):
            normalize_pair_rank_policy(policy(e_min=0.9))
        with self.assertRaises(PairRankingConfigError):
            normalize_pair_rank_policy(policy(b_low=0.9))


class PredictionOnlyRankingTests(unittest.TestCase):
    def test_upper_fallback_and_aggregate_unknowns(self):
        rows = rank_prediction_only([
            pair(
                "upper",
                side(
                    [model("m1", 0.9), model("m2", 0.85)],
                    [hit("a", score=0.2, upper=0.1), hit("b", score=0.6)],
                ),
                side(
                    [model("m1", 0.8), model("m2", 0.9)],
                    [],
                    aggregate_specificity=1.0,
                ),
            ),
        ], policy())
        self.assertEqual(rows[0]["pair_rank_status"], "pass")
        self.assertAlmostEqual(rows[0]["pair_offtarget_burden"], 0.75)
        self.assertIsNone(rows[0]["pair_max_offtarget_upper"])
        self.assertIsNone(rows[0]["pair_high_risk_count"])

    def test_side_hard_gates_reject(self):
        cases = [
            pair(
                "invalid",
                side([model("m1", 0.9), model("m2", 0.9)], valid=False),
                side([model("m1", 0.9), model("m2", 0.9)]),
            ),
            pair(
                "incomplete",
                side([model("m1", 0.9), model("m2", 0.9)],
                     search_complete=False),
                side([model("m1", 0.9), model("m2", 0.9)]),
            ),
            pair(
                "fallback",
                side([model("m1", 0.9, is_fallback=True)]),
                side([model("m1", 0.9), model("m2", 0.9)]),
            ),
            pair(
                "reference",
                side([model("m1", 0.9), model("m2", 0.9)]),
                side([model("m1", 0.9, reference_only=True)]),
            ),
            pair(
                "inapplicable",
                side([model("m1", 0.9, applicable=False)]),
                side([model("m1", 0.9), model("m2", 0.9)]),
            ),
            pair(
                "forbidden",
                side([model("m1", 0.9), model("m2", 0.9)],
                     [hit("bad", score=0.1, forbidden=True)]),
                side([model("m1", 0.9), model("m2", 0.9)]),
            ),
            pair(
                "bulge",
                side([model("m1", 0.9), model("m2", 0.9)]),
                side([model("m1", 0.9), model("m2", 0.9)],
                     [hit("b", score=0.1, is_bulge=True)]),
            ),
            pair(
                "hard-fail",
                side([model("m1", 0.9), model("m2", 0.9)]),
                side([model("m1", 0.9), model("m2", 0.9)]),
                hard_fail=True,
            ),
        ]
        rows = rank_prediction_only(cases, policy())
        self.assertTrue(all(
            row["pair_rank_status"] == "rejected" for row in rows
        ))
        self.assertTrue(all(row["pair_rank"] is None for row in rows))

    def test_activity_tiers_and_pair_minimum(self):
        rows = rank_prediction_only([
            pair(
                "tier-a",
                side([model("m1", 0.9), model("m2", 0.85)]),
                side([model("m1", 0.9), model("m2", 0.85)]),
            ),
            pair(
                "tier-b",
                side([model("m1", 0.9), model("m2", 0.85)]),
                side([model("m1", 0.6), model("m2", 0.2)]),
            ),
            pair(
                "tier-c",
                side([model("m1", 0.9), model("m2", 0.85)]),
                side([model("m1", 0.4), model("m2", 0.3)]),
            ),
        ], policy())
        statuses = {row["pair_id"]: row["pair_rank_status"] for row in rows}
        self.assertEqual(statuses["tier-a"], "pass")
        self.assertEqual(statuses["tier-b"], "pass")
        self.assertEqual(statuses["tier-c"], "conditional")
        by_id = {row["pair_id"]: row for row in rows}
        self.assertEqual(by_id["tier-a"]["pair_activity_tier"], "A")
        self.assertEqual(by_id["tier-b"]["pair_activity_tier"], "B")
        self.assertEqual(by_id["tier-c"]["pair_activity_tier"], "C")
        self.assertIn("tier_c", by_id["tier-c"]["pair_gate_reasons"])

    def test_uncalibrated_models_use_candidate_pool_percentiles(self):
        rows = rank_prediction_only([
            pair(
                "one",
                side([model("u", 0.2, calibrated=False)]),
                side([model("u", 0.2, calibrated=False)]),
            ),
            pair(
                "two",
                side([model("u", 0.8, calibrated=False)]),
                side([model("u", 0.8, calibrated=False)]),
            ),
        ], policy(e_min=0.75, e_high=0.9))
        by_id = {row["pair_id"]: row for row in rows}
        self.assertEqual(by_id["one"]["pair_activity_tier"], "C")
        self.assertEqual(by_id["one"]["pair_rank_status"], "conditional")
        self.assertEqual(by_id["two"]["pair_activity_tier"], "B")
        self.assertEqual(by_id["two"]["pair_rank_status"], "pass")

    def test_activity_disagreement_is_within_each_side(self):
        rows = rank_prediction_only([
            pair(
                "one",
                side([model("m1", 0.1), model("m2", 0.9)]),
                side([model("m1", 0.5), model("m2", 0.5)]),
            ),
            pair(
                "two",
                side([model("m1", 0.9), model("m2", 0.1)]),
                side([model("m1", 0.5), model("m2", 0.5)]),
            ),
        ], policy())
        by_id = {row["pair_id"]: row for row in rows}
        self.assertAlmostEqual(
            by_id["one"]["pair_activity_disagreement"], 0.75
        )
        self.assertAlmostEqual(
            by_id["two"]["pair_activity_disagreement"], 0.75
        )

    def test_uncalibrated_model_without_pool_is_not_rankable(self):
        rows = rank_prediction_only([
            pair(
                "single",
                side([model("u", 0.99, calibrated=False)]),
                side([]),
            ),
        ], policy())
        self.assertEqual(rows[0]["left_eligible_model_count"], 0)
        self.assertEqual(rows[0]["right_eligible_model_count"], 0)
        self.assertEqual(rows[0]["pair_activity_tier"], "C")
        self.assertEqual(rows[0]["pair_rank_status"], "conditional")

    def test_risk_two_and_high_threshold_rows_are_conditional(self):
        rows = rank_prediction_only([
            pair(
                "risk-two",
                side([model("m1", 0.9), model("m2", 0.9)],
                     [hit("a", upper=0.9)]),
                side([model("m1", 0.9), model("m2", 0.9)]),
            ),
        ], policy())
        row = rows[0]
        self.assertEqual(row["pair_rank_status"], "conditional")
        self.assertIn("risk_2", row["pair_gate_reasons"])
        self.assertIn("burden_above_b_high", row["pair_gate_reasons"])
        self.assertIn("max_offtarget_above_m_high", row["pair_gate_reasons"])

    def test_sort_key_and_competition_ranking(self):
        left = side([model("m1", 0.9), model("m2", 0.85)])
        right = side([model("m1", 0.9), model("m2", 0.85)])
        rows = rank_prediction_only([
            pair("b", left, right),
            pair("a", left, right),
            pair(
                "better",
                side([model("m1", 0.9), model("m2", 0.9)],
                     [hit("x", upper=0.1)]),
                right,
            ),
        ], policy())
        self.assertEqual([row["pair_id"] for row in rows], ["a", "b", "better"])
        self.assertEqual(rows[0]["pair_rank"], 1)
        self.assertEqual(rows[1]["pair_rank"], 1)
        self.assertEqual(rows[2]["pair_rank"], 3)
        self.assertNotIn("combined_score", rows[0])

    def test_compatibility_warnings_break_ties(self):
        left = side([model("m1", 0.9), model("m2", 0.85)])
        right = side([model("m1", 0.9), model("m2", 0.85)])
        rows = rank_prediction_only([
            pair("warned", left, right, soft_warnings=["delivery"]),
            pair("clean", left, right),
        ], policy())
        self.assertEqual(rows[0]["pair_id"], "clean")
        self.assertEqual(rows[1]["pair_compatibility_penalty"], 1)


class PairRankingAdapterTests(unittest.TestCase):
    def test_side_adapter_reads_model_flags_and_aggregate(self):
        row = {
            "left_on_target_score_cropsr": "0.9",
            "left_on_target_model_cropsr": "cropsr",
            "left_on_target_score_rules": "0.6",
            "left_on_target_model_rules": "rules_fallback",
            "left_off_target_specificity": "0.8",
            "left_calibration_status": "calibrated_reference",
            "left_reference_only": "false",
        }
        side_input = build_side_input(row, "left")
        self.assertEqual(side_input["aggregate_specificity"], 0.8)
        self.assertEqual(len(side_input["on_models"]), 2)
        self.assertTrue(side_input["on_models"][0]["calibrated"])
        self.assertTrue(side_input["on_models"][1]["is_fallback"])

    def test_pair_adapter_and_output_application(self):
        left = {
            "on_target_score_cropsr": "0.9",
            "off_target_specificity": "1.0",
            "calibration_status": "calibrated_reference",
        }
        right = {
            "on_target_score_cropsr": "0.85",
            "off_target_specificity": "1.0",
            "calibration_status": "calibrated_reference",
        }
        pair_input = build_pair_input("p1", left, right)
        ranked = rank_prediction_only([pair_input], policy())
        rows = apply_pair_rank_outputs(
            [dict(left, pair_id="p1"), dict(right, pair_id="p1")],
            ranked,
        )
        self.assertEqual(rows[0]["pair_rank_mode"], "prediction_only")
        self.assertEqual(rows[0]["pair_rank"], 1)

    def test_fallback_and_reference_follow_actual_model_result(self):
        row = {
            "left_on_target_score_cropsr": "0.9",
            "left_on_target_model_cropsr": "heuristic",
            "left_calibration_status": "calibrated_reference",
            "left_reference_only": "false",
        }
        models = collect_on_target_models(row, "left")
        self.assertEqual(len(models), 1)
        self.assertTrue(models[0]["is_fallback"])
        self.assertFalse(models[0]["calibrated"])

        row["left_on_target_model_cropsr"] = "cropsr_reference_only"
        models = collect_on_target_models(row, "left")
        self.assertTrue(models[0]["reference_only"])
        self.assertFalse(models[0]["calibrated"])

    def test_side_and_pair_search_state_are_inferred(self):
        left = {
            "left_guide_seq": "ACGTACGT",
            "left_search_complete": "false",
        }
        pair_input = build_pair_input("p1", left, None)
        self.assertTrue(pair_input["left"]["valid"])
        self.assertFalse(pair_input["left"]["search_complete"])
        self.assertFalse(pair_input["right"]["valid"])
        self.assertFalse(pair_input["right"]["search_complete"])
        self.assertFalse(pair_input["search_complete"])

        empty = {"left_guide_seq": ""}
        side_input = build_side_input(empty, "left")
        self.assertFalse(side_input["valid"])

    def test_pair_compatibility_surfaces_warnings_and_hard_failures(self):
        left = {
            "left_nuclease": "cas9",
            "nuclease": "cas9",
            "left_side": "upstream",
            "left_strand": "plus",
            "gap": "5",
            "distance": "25",
            "y_chrom": "chr1",
            "y_start": "10",
            "y_end": "20",
            "y_strand": "+",
        }
        right = {
            "right_nuclease": "cas12a",
            "nuclease": "cas12a",
            "right_side": "downstream",
            "right_strand": "plus",
            "distance": "30",
            "y_chrom": "chr1",
            "y_start": "10",
            "y_end": "20",
            "y_strand": "+",
        }
        compatibility = build_pair_compatibility(
            left,
            right,
            left_nuclease="cas9",
            right_nuclease="cas12a",
            gap_min=10,
            gap_max=20,
            expected_left_side="upstream",
            expected_right_side="downstream",
            left_distance_range=(0, 20),
            right_distance_range=(0, 40),
            require_same_locus=True,
            require_same_strand=True,
        )
        self.assertTrue(compatibility["hard_fail"])
        self.assertIn("gap_below_min:5.0", compatibility["hard_reasons"])
        self.assertIn(
            "distance_above_max:left:25.0",
            compatibility["hard_reasons"],
        )
        self.assertTrue(any(
            reason.startswith("nuclease_mismatch:left_right")
            for reason in compatibility["soft_warnings"]
        ))

        right["distance"] = "15"
        compatibility = build_pair_compatibility(
            left,
            right,
            left_distance_range=(30, 40),
            right_distance_range=(0, 20),
        )
        self.assertTrue(compatibility["hard_fail"])
        self.assertIn("distance_below_min:left:25.0",
                      compatibility["hard_reasons"])

    def test_policy_file_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "policy.json")
            write_pair_rank_policy_file(path, policy())
            from scoring.pair_ranking_adapter import (
                load_pair_rank_policy_file,
            )
            loaded = load_pair_rank_policy_file(path)
        self.assertEqual(loaded["e_high"], 0.8)


if __name__ == "__main__":
    unittest.main()
