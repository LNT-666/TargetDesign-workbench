#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the external crispAI adapter helpers (no external runtime)."""

import os
import sys
import tempfile
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "shared"))

from scoring.crispai_runtime import (  # noqa: E402
    backfill_candidates,
    collect_sgrnas,
    make_sgrna,
    parse_aggregate_output,
    specificity_from_aggregate,
)


class CrispAIRuntimeTests(unittest.TestCase):
    def test_make_sgrna_20mer_always_uses_ngg(self):
        self.assertEqual(
            make_sgrna("GAACACAAAGCATAGACTGC", "AGG"),
            "GAACACAAAGCATAGACTGCNGG",
        )

    def test_make_sgrna_accepts_23mer_ngg(self):
        self.assertEqual(
            make_sgrna("GAACACAAAGCATAGACTGCNGG"),
            "GAACACAAAGCATAGACTGCNGG",
        )

    def test_make_sgrna_rejects_wrong_length(self):
        self.assertIsNone(make_sgrna("ACGT"))
        self.assertIsNone(make_sgrna("A" * 21))

    def test_specificity_conversion(self):
        self.assertAlmostEqual(specificity_from_aggregate(0.0), 1.0)
        self.assertAlmostEqual(specificity_from_aggregate(1.0), 0.5)

    def test_collect_backfill_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            candidates = os.path.join(tmp, "library_scores.tsv")
            with open(candidates, "w", encoding="utf-8", newline="") as handle:
                handle.write(
                    "rank\tqid\tguide_seq\tpam_seq\tcrispai_off_target\n"
                    "1\tg0\tGAACACAAAGCATAGACTGC\tAGG\t\n"
                    "2\tg1\tGAACACAAAGCATAGACTGC\tAGG\t\n"
                )
            records = collect_sgrnas(candidates)
            self.assertEqual(len(records), 1)
            self.assertEqual(
                records[0]["sgrna"], "GAACACAAAGCATAGACTGCNGG"
            )

            aggregate = os.path.join(tmp, "agg.tsv")
            with open(aggregate, "w", encoding="utf-8", newline="") as handle:
                handle.write(
                    "sgRNA\taggregate_score_mean\taggregate_score_median\t"
                    "aggregate_score_std\t200-samples\n"
                    "GAACACAAAGCATAGACTGCNGG\t1.0\t1.0\t0.2\t1.0\n"
                )
            mapping = parse_aggregate_output(aggregate)
            self.assertEqual(mapping["GAACACAAAGCATAGACTGCNGG"], 1.0)

            matched, written = backfill_candidates(candidates, aggregate)
            self.assertEqual((matched, written), (2, 2))
            with open(candidates, "r", encoding="utf-8") as handle:
                content = handle.read()
            self.assertIn("crispai_off_target", content)
            self.assertIn("crispai_aggregate_score", content)
            self.assertIn("0.500000", content)


if __name__ == "__main__":
    unittest.main()
