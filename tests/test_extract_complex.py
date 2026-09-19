#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regression tests for optimized Pattern A extraction."""

import csv
import os
import subprocess
import sys
import tempfile
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(
    ROOT, "Target_xbp_Target", "extract_complex_queries.py"
)


class ExtractComplexTests(unittest.TestCase):
    def _run(self, fasta, out, min_gap, max_gap):
        return self._run_motifs(
            fasta, out, "TTAT", "CCGG", min_gap, max_gap
        )

    def _run_motifs(
        self, fasta, out, left_motif, right_motif, min_gap, max_gap
    ):
        cmd = [
            sys.executable, SCRIPT,
            fasta, left_motif, right_motif,
            str(min_gap), str(max_gap),
            "upstream", "0", "upstream", "0",
            out,
        ]
        proc = subprocess.run(
            cmd, capture_output=True, text=True,
            encoding="utf-8", errors="replace",
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        return out

    def test_gap_range_still_filters_pairs(self):
        with tempfile.TemporaryDirectory() as tmp:
            fasta = os.path.join(tmp, "input.fa")
            with open(fasta, "w", encoding="utf-8") as handle:
                handle.write(">chr1\nTTATAACCGG\n")
            out = os.path.join(tmp, "queries.tsv")
            self._run(fasta, out, 2, 2)
            with open(out, "r", encoding="utf-8") as handle:
                rows = handle.read().splitlines()
            self.assertEqual(len(rows), 2)
            self.assertNotIn("gap_seq", rows[0].split("\t"))
            self.assertNotIn("query_seq", rows[0].split("\t"))
            with open(
                os.path.splitext(out)[0] + ".queries.fa",
                "r", encoding="utf-8",
            ) as handle:
                self.assertIn("TTATAACCGG", handle.read())

    def test_out_of_range_pairs_are_not_emitted(self):
        with tempfile.TemporaryDirectory() as tmp:
            fasta = os.path.join(tmp, "input.fa")
            with open(fasta, "w", encoding="utf-8") as handle:
                handle.write(">chr1\nTTATAACCGG\n")
            out = os.path.join(tmp, "queries.tsv")
            self._run(fasta, out, 5, 5)
            with open(out, "r", encoding="utf-8") as handle:
                rows = handle.read().splitlines()
            self.assertEqual(len(rows), 1)

    def test_four_strand_combinations_are_emitted(self):
        with tempfile.TemporaryDirectory() as tmp:
            fasta = os.path.join(tmp, "input.fa")
            with open(fasta, "w", encoding="utf-8") as handle:
                handle.write(
                    ">pp\nTTATNNNNACGG\n"
                    ">pm\nTTATNNNNCCGT\n"
                    ">mp\nATAANNNNACGG\n"
                    ">mm\nATAANNNNCCGT\n"
                )
            out = os.path.join(tmp, "queries.tsv")
            self._run_motifs(fasta, out, "TTAT", "ACGG", 4, 4)
            with open(out, "r", encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle, delimiter="\t"))
            self.assertIn("left_target_start", rows[0])
            self.assertIn("right_target_end", rows[0])
            self.assertNotIn("gap_seq", rows[0])
            self.assertNotIn("query_seq", rows[0])
            orientations = {
                (row["seq_id"], row["left_strand"], row["right_strand"])
                for row in rows
            }
            self.assertEqual(
                orientations,
                {
                    ("pp", "plus", "plus"),
                    ("pm", "plus", "minus"),
                    ("mp", "minus", "plus"),
                    ("mm", "minus", "minus"),
                },
            )

    def test_target_coordinates_follow_side_and_strand(self):
        with tempfile.TemporaryDirectory() as tmp:
            fasta = os.path.join(tmp, "input.fa")
            with open(fasta, "w", encoding="utf-8") as handle:
                handle.write(">chr1\nTTATNNNNACGGNNNN\n")
            out = os.path.join(tmp, "queries.tsv")
            cmd = [
                sys.executable, SCRIPT,
                fasta, "TTAT", "ACGG",
                "4", "4",
                "downstream", "4", "downstream", "4",
                out,
            ]
            proc = subprocess.run(
                cmd, capture_output=True, text=True,
                encoding="utf-8", errors="replace",
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            with open(out, "r", encoding="utf-8", newline="") as handle:
                row = next(csv.DictReader(handle, delimiter="\t"))
            self.assertEqual(
                (
                    row["left_target_start"],
                    row["left_target_end"],
                    row["right_target_start"],
                    row["right_target_end"],
                ),
                ("4", "8", "12", "16"),
            )


if __name__ == "__main__":
    unittest.main()
