import csv
import json
import os
import sys
import tempfile
import unittest
from unittest import mock


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET_DIR = os.path.join(ROOT, "Target_xbp_Y_zbp_Target")
sys.path.insert(0, TARGET_DIR)


class SortByDistanceTests(unittest.TestCase):
    def test_partial_occurrence_is_rejected_and_kept(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "input.tsv")
            output = os.path.join(tmp, "output.tsv")
            with open(source, "w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle, delimiter="\t")
                writer.writerow([
                    "occurrence", "side", "distance",
                    "off_target_specificity",
                    "on_target_score_cropsr",
                    "calibration_status",
                ])
                writer.writerow([
                    "1", "left", "10", "0.9", "0.9",
                    "calibrated_reference",
                ])
                writer.writerow([
                    "1", "right", "5", "0.8", "0.85",
                    "calibrated_reference",
                ])
                writer.writerow([
                    "2", "right", "7", "1.0", "0.95",
                    "calibrated_reference",
                ])

            policy_path = os.path.join(tmp, "policy.json")
            with open(policy_path, "w", encoding="utf-8") as handle:
                json.dump({
                    "e_high": 0.8,
                    "e_min": 0.5,
                    "e_fail": 0.2,
                    "delta_default": 0.05,
                    "b_low": 0.4,
                    "b_high": 0.8,
                    "m_low": 0.2,
                    "m_high": 0.45,
                    "h_risk": 0.7,
                    "h_max": 1,
                }, handle)

            with mock.patch.object(
                    sys, "argv", [
                        "sort_by_distance.py",
                        source,
                        output,
                        "--pair-rank-policy",
                        policy_path,
                    ]):
                from sort_by_distance import main
                main()

            with open(output, "r", encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle, delimiter="\t"))
            self.assertEqual([row["occurrence"] for row in rows],
                             ["1", "1", "2"])
            by_occurrence = {
                row["occurrence"]: row for row in rows
            }
            self.assertEqual(by_occurrence["1"]["pair_rank_status"], "pass")
            self.assertEqual(
                by_occurrence["2"]["pair_rank_status"], "rejected")
            self.assertEqual(by_occurrence["2"]["pair_rank"], "")
            self.assertEqual(rows[0]["pair_rank_mode"], "prediction_only")
            self.assertNotIn("combined_score", rows[0])

    def test_forbidden_hit_rejects_pair(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "input.tsv")
            output = os.path.join(tmp, "output.tsv")
            forbidden = json.dumps([
                {
                    "locus_id": "chr1:20:+",
                    "score": None,
                    "upper": 1.0,
                    "forbidden": True,
                    "is_bulge": False,
                    "bulge_calibrated": False,
                }
            ], separators=(",", ":"))
            with open(source, "w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle, delimiter="\t")
                writer.writerow([
                    "occurrence", "side", "distance",
                    "on_target_score_cropsr", "calibration_status",
                    "forbidden_hits",
                ])
                writer.writerow([
                    "1", "left", "10", "0.9",
                    "calibrated_reference", forbidden,
                ])
                writer.writerow([
                    "1", "right", "5", "0.85",
                    "calibrated_reference", "",
                ])

            policy_path = os.path.join(tmp, "policy.json")
            _write_policy(policy_path)
            with mock.patch.object(
                    sys, "argv", [
                        "sort_by_distance.py",
                        source,
                        output,
                        "--pair-rank-policy",
                        policy_path,
                    ]):
                from sort_by_distance import main
                main()

            with open(output, "r", encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle, delimiter="\t"))
            self.assertEqual(rows[0]["pair_rank_status"], "rejected")
            self.assertIn(
                "forbidden_offtarget:left:chr1:20:+",
                rows[0]["pair_gate_reasons"],
            )

    def test_distance_bounds_are_compatibility_hard_failures(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "input.tsv")
            output = os.path.join(tmp, "output.tsv")
            with open(source, "w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle, delimiter="\t")
                writer.writerow([
                    "occurrence", "side", "distance",
                    "on_target_score_cropsr", "calibration_status",
                ])
                writer.writerow([
                    "1", "left", "25", "0.9",
                    "calibrated_reference",
                ])
                writer.writerow([
                    "1", "right", "5", "0.85",
                    "calibrated_reference",
                ])

            policy_path = os.path.join(tmp, "policy.json")
            _write_policy(policy_path)
            with mock.patch.object(
                    sys, "argv", [
                        "sort_by_distance.py",
                        source,
                        output,
                        "--left-min-distance", "0",
                        "--left-max-distance", "20",
                        "--right-min-distance", "0",
                        "--right-max-distance", "20",
                        "--pair-rank-policy",
                        policy_path,
                    ]):
                from sort_by_distance import main
                main()

            with open(output, "r", encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle, delimiter="\t"))
            self.assertEqual(rows[0]["pair_rank_status"], "rejected")
            self.assertIn(
                "compatibility_hard_fail",
                rows[0]["pair_gate_reasons"],
            )


def _write_policy(path):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({
            "e_high": 0.8,
            "e_min": 0.5,
            "e_fail": 0.2,
            "delta_default": 0.05,
            "b_low": 0.4,
            "b_high": 0.8,
            "m_low": 0.2,
            "m_high": 0.45,
            "h_risk": 0.7,
            "h_max": 1,
        }, handle)


if __name__ == "__main__":
    unittest.main()
