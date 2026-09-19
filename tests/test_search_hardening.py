#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regression tests for exhaustive seeds, gapped alignment and score handoff."""

import os
import random
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHARED = os.path.join(ROOT, "shared")
sys.path.insert(0, SHARED)

from design.guide_design import find_guides  # noqa: E402
from search.alignment import align_global  # noqa: E402
from search.exact_offtarget import (  # noqa: E402
    _pam_ok_span, reverse_complement, search_guides,
)
from search.genome_index import (  # noqa: E402
    build_index, load_index, search_indexed, select_index_k,
)
from search.seed_plan import build_seed_plan  # noqa: E402
from scoring.scoring import cfd_score, compute_guide_scores  # noqa: E402


PAM = "NGG"


def _write_genome(path, sequences):
    with open(path, "w", encoding="utf-8") as handle:
        for seqid, sequence in sequences.items():
            handle.write(">%s\n%s\n" % (seqid, sequence))


def _candidate_key(hit):
    aligned_guide = hit.get("aligned_guide") or ""
    aligned_target = hit.get("aligned_target") or ""
    leading_dna = len(aligned_guide) - len(aligned_guide.lstrip("-"))
    leading_rna = len(aligned_target) - len(aligned_target.lstrip("-"))
    return (
        hit["target"],
        int(hit.get("target_start", hit["start"]))
        + leading_dna - leading_rna,
        hit["strand"],
    )


def _brute_force(genome, guide, max_mismatch, max_bulge):
    """Exhaustive hit search independent of any seed or backend."""
    found = {}
    guide_len = len(guide)
    for target, sequence in genome.items():
        sequence = sequence.upper()
        for strand, probe in (
                ("+", guide),
                ("-", reverse_complement(guide))):
            for target_start in range(0, len(sequence)):
                for target_end in range(
                        target_start + max(1, guide_len - max_bulge),
                        min(
                            len(sequence),
                            target_start + guide_len + max_bulge,
                        ) + 1):
                    alignment = align_global(
                        probe, sequence[target_start:target_end])
                    if alignment.mismatches > max_mismatch or \
                            alignment.indels > max_bulge:
                        continue
                    if not _pam_ok_span(
                            None, target, target_start, target_end, strand,
                            PAM, "3prime",
                            fetch_func=lambda _g, _t, start, end:
                            sequence[start:end]):
                        continue
                    leading_dna = len(alignment.query_aligned) - len(
                        alignment.query_aligned.lstrip("-"))
                    leading_rna = len(alignment.target_aligned) - len(
                        alignment.target_aligned.lstrip("-"))
                    canonical_start = (
                        target_start + leading_dna - leading_rna)
                    key = (target, canonical_start, strand)
                    value = (
                        alignment.mismatches,
                        alignment.indels,
                        alignment.rna_bulges,
                        alignment.dna_bulges,
                    )
                    if key not in found or value < found[key]:
                        found[key] = value
    return found


def _normalized_hits(hits):
    normalized = {}
    for hit in hits:
        key = _candidate_key(hit)
        value = (
            hit["mismatch"],
            hit.get("indel", 0),
            hit.get("rna_bulges", 0),
            hit.get("dna_bulges", 0),
        )
        if key not in normalized or value < normalized[key]:
            normalized[key] = value
    return normalized


class ExhaustiveSeedTests(unittest.TestCase):
    def test_high_k_bulge_plan_reports_unavailable(self):
        k12_bulge = build_seed_plan(20, 4, 1, 12, 12)
        self.assertFalse(k12_bulge.guaranteed)
        k10_bulge = build_seed_plan(20, 4, 1, 10, 10)
        self.assertTrue(k10_bulge.guaranteed)
        k12_mismatch = build_seed_plan(20, 4, 0, 12, 12)
        self.assertTrue(k12_mismatch.guaranteed)
        self.assertGreater(k12_mismatch.estimated_variants, 100000)

    def test_index_k_adapts_to_guide_and_bulge_budget(self):
        self.assertEqual(
            select_index_k(
                200000000, [20], max_mismatch=4, max_bulge=1),
            10,
        )
        self.assertEqual(
            select_index_k(
                200000000, [20], max_mismatch=4, max_bulge=1,
                requested_k=12),
            12,
        )

    def test_exact_and_indexed_match_bruteforce_for_all_budgets(self):
        rng = random.Random(20260913)
        guide = "".join(rng.choice("ACGT") for _ in range(20))
        genome = {
            "chr1": (
                "C" * 12
                + guide
                + "AGG"
                + "T" * 8
                + guide[:8]
                + "A"
                + guide[9:]
                + "TGG"
                + "G" * 12
            ),
            "chr2": (
                "A" * 10
                + reverse_complement(guide[1:])
                + "AGG"
                + "C" * 10
            ),
        }
        with tempfile.TemporaryDirectory() as tmp:
            fasta = os.path.join(tmp, "genome.fa")
            prefix = os.path.join(tmp, "index")
            _write_genome(fasta, genome)
            build_index(fasta, prefix, k=8)
            index = load_index(prefix)
            for max_mismatch in range(5):
                for max_bulge in range(2):
                    with self.subTest(
                            mismatch=max_mismatch, bulge=max_bulge):
                        expected = _brute_force(
                            genome, guide, max_mismatch, max_bulge)
                        exact = search_guides(
                            [{"qid": "g0", "guide_seq": guide}],
                            fasta,
                            max_mismatch=max_mismatch,
                            max_bulge=max_bulge,
                            seed_len=8,
                            pam=PAM,
                            pam_side="3prime",
                        )["g0"]
                        indexed, _report = search_indexed(
                            index,
                            [{"qid": "g0", "guide_seq": guide}],
                            fasta,
                            max_mismatch=max_mismatch,
                            max_bulge=max_bulge,
                            seed_len=8,
                            pam=PAM,
                            pam_side="3prime",
                        )
                        self.assertEqual(
                            _normalized_hits(exact), expected)
                        self.assertEqual(
                            _normalized_hits(indexed["g0"]), expected)

    def test_two_mismatches_in_each_half_are_found(self):
        guide = "AAAACCCCGGGGTTTTAAAA"
        off_target = "AATAACCCGGAGTTTTAATA"
        fasta_path = None
        with tempfile.NamedTemporaryFile(
                "w", suffix=".fa", delete=False,
                encoding="utf-8") as handle:
            handle.write(">chr1\n")
            handle.write("C" * 20 + off_target + "AGG" + "C" * 20 + "\n")
            fasta_path = handle.name
        try:
            hits = search_guides(
                [{"qid": "g0", "guide_seq": guide}],
                fasta_path,
                max_mismatch=4,
                max_bulge=0,
                seed_len=8,
            )["g0"]
            self.assertTrue(any(
                hit["start"] == 20
                and hit["mismatch"] == 4
                and hit["indel"] == 0
                for hit in hits
            ))
        finally:
            os.unlink(fasta_path)


class AlignmentCoordinateTests(unittest.TestCase):
    def _search_case(self, guide, target, strand):
        genome_sequence = "C" * 20 + target + "G" * 8
        if strand == "-":
            genome_sequence = "C" * 20 + reverse_complement(target) + "G" * 8
        with tempfile.NamedTemporaryFile(
                "w", suffix=".fa", delete=False,
                encoding="utf-8") as handle:
            handle.write(">chr1\n%s\n" % genome_sequence)
            fasta = handle.name
        try:
            hits = search_guides(
                [{"qid": "g0", "guide_seq": guide}],
                fasta,
                max_mismatch=0,
                max_bulge=1,
                seed_len=8,
                pam=PAM,
                pam_side="3prime",
            ).get("g0", [])
        finally:
            os.unlink(fasta)
        return [hit for hit in hits if hit["strand"] == strand]

    def test_rna_and_dna_bulges_have_real_coordinates(self):
        guide = "ACGTTGCAAGTCCTAGGATC"
        cases = (
            ("rna_5", guide[:1] + guide[2:] + "AGG", "I", "rna"),
            ("rna_mid", guide[:10] + guide[11:] + "AGG", "I", "rna"),
            ("rna_3", guide[:-2] + guide[-1:] + "AGG", "I", "rna"),
            ("dna_mid", guide[:10] + "T" + guide[10:] + "AGG", "D", "dna"),
            ("dna_3", guide[:-1] + "T" + guide[-1:] + "AGG", "D", "dna"),
        )
        for name, target, operator, gap_type in cases:
            for strand in ("+", "-"):
                with self.subTest(name=name, strand=strand):
                    hits = self._search_case(guide, target, strand)
                    self.assertTrue(hits, name)
                    hit = hits[0]
                    self.assertEqual(hit["mismatch"], 0)
                    self.assertIn(operator, hit["cigar"])
                    self.assertEqual(hit["rna_bulges"], int(gap_type == "rna"))
                    self.assertEqual(hit["dna_bulges"], int(gap_type == "dna"))
                    self.assertEqual(hit["query_start"], 0)
                    self.assertEqual(hit["query_end"], len(guide))
                    expected_start = 20 if strand == "+" else 23
                    expected_end = (
                        expected_start + (19 if gap_type == "rna" else 21)
                    )
                    self.assertEqual(hit["target_start"], expected_start)
                    self.assertEqual(hit["target_end"], expected_end)

    def test_near_5prime_dna_bulge_on_both_strands(self):
        guide = "CCGTAATGCCTTTCCCTAAC"
        target = guide[:2] + "A" + guide[2:] + "AGG"
        for strand in ("+", "-"):
            with self.subTest(strand=strand):
                hits = self._search_case(guide, target, strand)
                self.assertTrue(hits)
                hit = hits[0]
                self.assertFalse(hit["rna_bulges"])
                self.assertEqual(hit["dna_bulges"], 1)
                self.assertIn("D", hit["cigar"])


class PamModeTests(unittest.TestCase):
    def test_strict_ngg_and_guidescan2_nrg(self):
        ng_guide = "ACGTTGCAAGTCCTAGGATC"
        na_guide = "TGCATGCATGCATGCATGCA"
        sequence = ng_guide + "AGG" + "TTTT" + na_guide + "TAG"
        strict = find_guides(
            sequence, spacer_len=20, pam="NGG",
            pam_side="3prime", allow_reverse=False)
        nrg = find_guides(
            sequence, spacer_len=20, pam="NRG",
            pam_side="3prime", allow_reverse=False)
        self.assertEqual([g["guide_seq"] for g in strict], [ng_guide])
        self.assertEqual(
            {g["guide_seq"] for g in nrg}, {ng_guide, na_guide})
        self.assertAlmostEqual(cfd_score(ng_guide, ng_guide, "NGG"), 1.0)
        self.assertAlmostEqual(
            cfd_score(na_guide, na_guide, "NAG"), 0.259259259)


class ScoreHandoffTests(unittest.TestCase):
    def test_mismatch_only_hit_does_not_gain_a_bulge(self):
        from design.library_pipeline import _scoring_hits
        from pyfaidx import Fasta

        guide = "ACGTTGCAAGTCCTAGGATC"
        with tempfile.NamedTemporaryFile(
                "w", suffix=".fa", delete=False,
                encoding="utf-8") as handle:
            handle.write(">chr1\n%sAGG\n" % guide)
            fasta = handle.name
        genome = Fasta(fasta)
        try:
            hits, skipped = _scoring_hits(
                [{
                    "target": "chr1",
                    "start": 0,
                    "strand": "+",
                    "mismatch": 0,
                    "indel": 0,
                    "engine": "blast",
                }],
                genome,
                guide,
                {},
            )
        finally:
            genome.close()
            os.unlink(fasta)
        self.assertEqual(skipped, 0)
        self.assertEqual(hits[0]["indel"], 0)
        self.assertEqual(hits[0]["rna_bulges"], 0)
        self.assertEqual(hits[0]["dna_bulges"], 0)

    def test_bulge_hit_is_not_flattened_before_scoring(self):
        guide = "ACGTTGCAAGTCCTAGGATC"
        genome_sequence = (
            "C" * 20
            + guide[:10] + guide[11:] + "AGG"
            + "G" * 20
        )
        with tempfile.NamedTemporaryFile(
                "w", suffix=".fa", delete=False,
                encoding="utf-8") as handle:
            handle.write(">chr1\n%s\n" % genome_sequence)
            fasta = handle.name
        try:
            hits = search_guides(
                [{"qid": "g0", "guide_seq": guide}],
                fasta,
                max_mismatch=0,
                max_bulge=1,
                seed_len=8,
                pam=PAM,
                pam_side="3prime",
            )["g0"]
            scores = compute_guide_scores(
                guide, hits, nuclease="cas9", off_target_model="cfd")
        finally:
            os.unlink(fasta)
        self.assertEqual(scores["input_offtargets"], 1)
        self.assertEqual(scores["bulge_hits"], 1)
        self.assertEqual(scores["scored_bulge_hits"], 1)
        self.assertEqual(scores["unscored_bulge_hits"], 0)
        self.assertEqual(scores["calibration_status"], "uncalibrated")
        self.assertEqual(
            scores["bulge_score_method"], "conservative_bulge_v1")


if __name__ == "__main__":
    unittest.main()
