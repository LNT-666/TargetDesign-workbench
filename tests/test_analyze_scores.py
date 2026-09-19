#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regression tests for basic/analyze_scores.py position records."""

import csv
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "basic", "analyze_scores.py")


def _load_module():
    spec = importlib.util.spec_from_file_location("analyze_scores_mod", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class AnalyzeScoresPositionTests(unittest.TestCase):
    def test_rich_bulge_match_keeps_stats_and_cigar(self):
        with tempfile.TemporaryDirectory() as tmp:
            guide = "ACGTTGCAAGTCCTAGGATC"
            query = guide + "AGG"
            aligned_target = "ACGTTGCAAG-CCTAGGATCAGG"
            genome = os.path.join(tmp, "genome.fa")
            with open(genome, "w", encoding="utf-8") as handle:
                handle.write(">chr1\n%s\n" % aligned_target.replace("-", ""))

            fieldnames = [
                "qid", "sequence", "positions", "matches",
                "motif_plus", "motif_minus", "flank_len", "side",
                "rdna_intervals", "genome_file",
            ]
            blast_results = os.path.join(tmp, "blast_results.tsv")
            rich_hit = {
                "target": "chr1",
                "start": 0,
                "target_start": 0,
                "target_end": 22,
                "strand": "+",
                "mismatch": 0,
                "indel": 1,
                "rna_bulges": 1,
                "dna_bulges": 0,
                "cigar": "10M1I9M3M",
                "aligned_guide": query,
                "aligned_target": aligned_target,
                "pam": "AGG",
                "engine": "exact",
            }
            rows = [
                {
                    "qid": "metadata",
                    "sequence": "",
                    "positions": "",
                    "matches": "",
                    "motif_plus": "NGG",
                    "motif_minus": "CCN",
                    "flank_len": "20",
                    "side": "upstream",
                    "rdna_intervals": "{}",
                    "genome_file": genome,
                },
                {
                    "qid": "uniq_0",
                    "sequence": query,
                    "positions": json.dumps([["chr1", "plus", 0, 0]]),
                    "matches": json.dumps([rich_hit]),
                    "motif_plus": "",
                    "motif_minus": "",
                    "flank_len": "",
                    "side": "",
                    "rdna_intervals": "",
                    "genome_file": "",
                },
            ]
            with open(blast_results, "w", encoding="utf-8",
                      newline="") as handle:
                writer = csv.DictWriter(
                    handle, fieldnames=fieldnames, delimiter="\t")
                writer.writeheader()
                writer.writerows(rows)

            outdir = os.path.join(tmp, "out")
            result = subprocess.run(
                [sys.executable, SCRIPT, blast_results, outdir,
                 "--max-mismatch", "0", "--no-require-pam"],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace")
            self.assertEqual(result.returncode, 0,
                             result.stdout + result.stderr)
            with open(
                    os.path.join(outdir, "query_scores_sorted.tsv"),
                    encoding="utf-8") as handle:
                scored = list(csv.DictReader(handle, delimiter="\t"))
            self.assertEqual(scored[0]["valid_matches"], "1")
            self.assertEqual(scored[0]["bulge_hits"], "1")
            self.assertEqual(scored[0]["scored_bulge_hits"], "1")

    def test_four_field_position_records_are_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            genome = os.path.join(tmp, "genome.fa")
            with open(genome, "w", encoding="utf-8") as handle:
                handle.write(">chr1\n")
                handle.write("A" * 120 + "\n")

            fieldnames = [
                "qid", "sequence", "positions", "matches",
                "motif_plus", "motif_minus", "flank_len", "side",
                "rdna_intervals", "genome_file",
            ]
            blast_results = os.path.join(tmp, "blast_results.tsv")
            rows = [
                {
                    "qid": "metadata",
                    "sequence": "",
                    "positions": "",
                    "matches": "",
                    "motif_plus": "NGG",
                    "motif_minus": "CCN",
                    "flank_len": "20",
                    "side": "upstream",
                    "rdna_intervals": "{}",
                    "genome_file": genome,
                },
                {
                    "qid": "uniq_0",
                    "sequence": "C" * 20 + "GGG",
                    "positions": json.dumps([["chr1", "plus", 20, 0]]),
                    "matches": json.dumps([["chr1", 20, 1, "+"]]),
                    "motif_plus": "",
                    "motif_minus": "",
                    "flank_len": "",
                    "side": "",
                    "rdna_intervals": "",
                    "genome_file": "",
                },
                {
                    "qid": "uniq_1",
                    "sequence": "G" * 23,
                    "positions": json.dumps([["chr1", "minus", 50]]),
                    "matches": "[]",
                    "motif_plus": "",
                    "motif_minus": "",
                    "flank_len": "",
                    "side": "",
                    "rdna_intervals": "",
                    "genome_file": "",
                },
            ]
            with open(blast_results, "w", encoding="utf-8",
                      newline="") as handle:
                writer = csv.DictWriter(
                    handle, fieldnames=fieldnames, delimiter="\t")
                writer.writeheader()
                writer.writerows(rows)

            outdir = os.path.join(tmp, "out")
            result = subprocess.run(
                [sys.executable, SCRIPT, blast_results, outdir,
                 "--max-mismatch", "0", "--no-require-pam"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(
                os.path.isfile(os.path.join(outdir, "query_scores_sorted.tsv"))
            )
            with open(
                os.path.join(outdir, "query_scores_sorted.tsv"),
                encoding="utf-8",
            ) as handle:
                reader = csv.DictReader(handle, delimiter="\t")
                scored = list(reader)
                fieldnames = reader.fieldnames
            self.assertEqual(len(scored), 2)
            self.assertIn("MM0", fieldnames)
            self.assertNotIn("MM1", fieldnames)
            self.assertNotIn("MM2", fieldnames)
            self.assertNotIn("MM3", fieldnames)
            self.assertNotIn("MM4", fieldnames)
            self.assertTrue(
                all(row["total_matches"] == "0" for row in scored))
            self.assertTrue(
                all(row["valid_matches"] == "0" for row in scored))

    def test_window_motif_slice(self):
        mod = _load_module()
        # upstream windows are [spacer][motif] -> motif at the end.
        self.assertEqual(mod.window_motif_slice(23, 3, "upstream"), (20, 23))
        # downstream windows are [motif][spacer] -> motif at the start.
        self.assertEqual(mod.window_motif_slice(23, 3, "downstream"), (0, 3))

    def test_guide_spacer(self):
        mod = _load_module()
        spacer20 = "CAGTCAGTCAGTCAGTCAGT"
        # upstream window = [spacer(20)][motif(3)] -> spacer is the leading 20.
        self.assertEqual(
            mod.guide_spacer(spacer20 + "TGG", 3, "upstream"), spacer20)
        # downstream window = [motif(3)][spacer(20)] -> spacer is the trailing 20.
        self.assertEqual(
            mod.guide_spacer("TGG" + spacer20, 3, "downstream"), spacer20)

    def test_at_score_only_uses_tnpb_preset(self):
        mod = _load_module()
        self.assertFalse(mod.should_output_at_score("preset", "cas9"))
        self.assertFalse(mod.should_output_at_score("free", "tnpb"))
        self.assertTrue(mod.should_output_at_score("preset", "tnpb"))
        self.assertTrue(mod.should_output_at_score("free", "custom", "tnpb"))
        self.assertFalse(mod.should_output_at_score("preset", "tnpb", "cas9"))
        self.assertEqual(
            mod.compute_at_score_from_flank("AAG", "upstream", "plus"), 3)
        self.assertEqual(
            mod.compute_at_score_from_flank("AAG", "upstream", "minus"), 1)
        self.assertEqual(
            mod.compute_at_score_from_flank("AAG", "downstream", "plus"), 1)
        self.assertEqual(
            mod.compute_at_score_from_flank("AAG", "downstream", "minus"), 3)

        with tempfile.TemporaryDirectory() as tmp:
            query = "ATGCATGCATGCATGCATGC" + "TTGAT"
            genome = os.path.join(tmp, "genome.fa")
            with open(genome, "w", encoding="utf-8") as handle:
                handle.write(">chr1\n%s\n" % query)

            fieldnames = [
                "qid", "sequence", "positions", "matches",
                "motif_plus", "motif_minus", "flank_len", "side",
                "rdna_intervals", "genome_file",
            ]
            blast_results = os.path.join(tmp, "blast_results.tsv")
            rows = [
                {
                    "qid": "metadata",
                    "sequence": "",
                    "positions": "",
                    "matches": "",
                    "motif_plus": "TTGAT",
                    "motif_minus": "ATCAA",
                    "flank_len": "20",
                    "side": "upstream",
                    "rdna_intervals": "{}",
                    "genome_file": genome,
                },
                {
                    "qid": "uniq_0",
                    "sequence": query,
                    "positions": json.dumps([["chr1", "plus", 0, 0]]),
                    "matches": "[]",
                    "motif_plus": "",
                    "motif_minus": "",
                    "flank_len": "",
                    "side": "",
                    "rdna_intervals": "",
                    "genome_file": "",
                },
            ]
            with open(blast_results, "w", encoding="utf-8",
                      newline="") as handle:
                writer = csv.DictWriter(
                    handle, fieldnames=fieldnames, delimiter="\t")
                writer.writeheader()
                writer.writerows(rows)

            for preset, expected in (("cas9", False), ("tnpb", True)):
                with self.subTest(preset=preset):
                    outdir = os.path.join(tmp, preset)
                    result = subprocess.run(
                        [
                            sys.executable, SCRIPT, blast_results, outdir,
                            "--mode", "preset", "--preset", preset,
                            "--nuclease", "tnpb" if preset == "tnpb" else "cas9",
                            "--on-target-model",
                            "omega" if preset == "tnpb" else "cropsr",
                            "--off-target-model",
                            "identity" if preset == "tnpb" else "cfd",
                            "--no-require-pam",
                        ],
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                    )
                    self.assertEqual(
                        result.returncode, 0, result.stdout + result.stderr)
                    with open(
                        os.path.join(outdir, "query_scores_sorted.tsv"),
                        encoding="utf-8",
                    ) as handle:
                        reader = csv.DictReader(handle, delimiter="\t")
                        scored = list(reader)
                    self.assertEqual(("AT_score" in reader.fieldnames), expected)
                    if expected:
                        self.assertGreater(int(scored[0]["AT_score"]), 0)

    def test_apply_crispai_scores_overrides_rows(self):
        mod = _load_module()
        from scoring import crispai_runtime as cr
        spacer20 = "CAGTCAGTCAGTCAGTCAGT"
        sgrna = spacer20 + "NGG"
        aggregate = 2.0
        cr.run_crispai_aggregate = lambda *a, **k: {sgrna: aggregate}
        expected_spec = 1.0 / (1.0 + aggregate)
        for nuclease in ("cas9", "custom"):
            with self.subTest(nuclease=nuclease):
                rows = [{
                    "query_seq": spacer20 + "TGG",
                    "strand": "plus",
                    "on_target_score": 0.5,
                    "off_target_specificity": 0.9,
                    "off_target_model": "cfd",
                    "crispai_off_target": "",
                }]
                ok = mod.apply_crispai_scores(
                    rows, "NGG", "upstream", nuclease,
                    tempfile.mkdtemp())
                self.assertTrue(ok)
                self.assertAlmostEqual(
                    rows[0]["off_target_specificity"], expected_spec)
                self.assertEqual(rows[0]["off_target_model"], "crispai")
                self.assertAlmostEqual(
                    rows[0]["crispai_off_target"], expected_spec)
                self.assertAlmostEqual(
                    rows[0]["off_target_specificity_crispai"], expected_spec)
                self.assertEqual(
                    rows[0]["off_target_model_crispai"], "crispai")
                self.assertEqual(rows[0]["crispai_aggregate_score"], aggregate)

    def test_pam_gating_drops_non_pam_offtargets(self):
        with tempfile.TemporaryDirectory() as tmp:
            genome = os.path.join(tmp, "genome.fa")
            # [20 bp spacer][NGG] style windows; the PAM motif is embedded at
            # the end of the window, not downstream of it.
            spacer = "CAGTCAGTCAGTCAGTCAGTA"
            on_target = spacer + "TGG"
            valid_target = "CAGTCAGTCAGTCAGTCAGGG" + "TGG"  # 1 mm, valid NGG
            invalid_target = spacer + "CCT"                  # 1 mm, NOT a PAM
            genome_seq = (
                "A" * 3
                + on_target
                + "C" * 2
                + valid_target
                + "C" * 2
                + invalid_target
                + "C" * 50
            )
            with open(genome, "w", encoding="utf-8") as handle:
                handle.write(">chr1\n")
                handle.write(genome_seq + "\n")

            on_start = 3
            valid_start = 3 + len(on_target) + 2
            invalid_start = valid_start + len(valid_target) + 2
            fieldnames = [
                "qid", "sequence", "positions", "matches",
                "motif_plus", "motif_minus", "flank_len", "side",
                "rdna_intervals", "genome_file",
            ]
            blast_results = os.path.join(tmp, "blast_results.tsv")
            rows = [
                {
                    "qid": "metadata",
                    "sequence": "",
                    "positions": "",
                    "matches": "",
                    "motif_plus": "NGG",
                    "motif_minus": "CCN",
                    "flank_len": "20",
                    "side": "upstream",
                    "rdna_intervals": "{}",
                    "genome_file": genome,
                },
                {
                    "qid": "uniq_0",
                    "sequence": on_target,
                    "positions": json.dumps([["chr1", "plus", 23, on_start]]),
                    "matches": json.dumps([
                        ["chr1", on_start, 0, "+"],
                        ["chr1", valid_start, 1, "+"],
                        ["chr1", invalid_start, 1, "+"],
                    ]),
                    "motif_plus": "",
                    "motif_minus": "",
                    "flank_len": "",
                    "side": "",
                    "rdna_intervals": "",
                    "genome_file": "",
                },
            ]
            with open(blast_results, "w", encoding="utf-8",
                      newline="") as handle:
                writer = csv.DictWriter(
                    handle, fieldnames=fieldnames, delimiter="\t")
                writer.writeheader()
                writer.writerows(rows)

            outdir = os.path.join(tmp, "out")
            result = subprocess.run(
                [sys.executable, SCRIPT, blast_results, outdir,
                 "--nuclease", "cas9", "--off-target-model", "cfd"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            with open(
                os.path.join(outdir, "query_scores_sorted.tsv"),
                encoding="utf-8",
            ) as handle:
                scored = list(csv.DictReader(handle, delimiter="\t"))
            self.assertEqual(len(scored), 1)
            row = scored[0]
            # The invalid (non-NGG) off-target must not count as a valid match
            # or appear in the MM buckets.
            self.assertEqual(row["valid_matches"], "2")   # on-target + valid off
            self.assertEqual(row["MM1"], "1")             # only the valid 1-mm
            self.assertEqual(row["MM2"], "0")
            self.assertEqual(row["MM4"], "0")
            # The valid 1-mm off-target carries a real NGG, so CFD must detect it
            # instead of saturating specificity to 1.0 when the PAM is read from
            # the bases after the window.
            self.assertLess(float(row["off_target_specificity_cfd"]), 1.0)
            self.assertNotIn("cfd_specificity", row)


if __name__ == "__main__":
    unittest.main()
