#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the persistent local genome index (Phase 3)."""

import json
import os
import random
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHARED = os.path.join(ROOT, "shared")
sys.path.insert(0, SHARED)

from search.exact_offtarget import reverse_complement  # noqa: E402
from search.genome_index import (  # noqa: E402
    MemoryLimitExceededError,
    build_index,
    load_index,
    search_indexed,
)
from search.iupac import iupac_to_regex  # noqa: E402
from search.offtarget_backend import (  # noqa: E402
    IndexedBackend, SearchParams, get_backend, run_backend,
)


GUIDE = "GCCTCTTTCCCACCCACCTT"


def _write_genome(path, sequences):
    with open(path, "w", encoding="utf-8") as handle:
        for seqid, seq in sequences.items():
            handle.write(">%s\n%s\n" % (seqid, seq))


def _random_genome(seed=1):
    rng = random.Random(seed)
    seq_a = "".join(rng.choice("ACGT") for _ in range(900))
    seq_a = seq_a[:150] + GUIDE + "GGG" + seq_a[173:]
    seq_b = "".join(rng.choice("ACGT") for _ in range(700))
    seq_b = seq_b[:80] + "CCG" + reverse_complement(GUIDE) + seq_b[103:]
    return {"chrA": seq_a, "chrB": seq_b}


def _hamming(a, b):
    return sum(x != y for x, y in zip(a, b))


def _pam_ok(seq, start, guide_len, pam, pam_side, strand):
    pam_re = re.compile(iupac_to_regex(pam))
    pam_len = len(pam)
    if strand == "+":
        window = seq[start + guide_len:start + guide_len + pam_len] \
            if pam_side == "3prime" else \
            seq[start - pam_len:start]
        return bool(pam_re.fullmatch(window))
    rc_re = re.compile(iupac_to_regex(reverse_complement(pam)))
    window = seq[start - pam_len:start] if pam_side == "3prime" else \
        seq[start + guide_len:start + guide_len + pam_len]
    return bool(rc_re.fullmatch(window))


def _brute_force(seqs, guide, max_mismatch, pam="NGG", pam_side="3prime"):
    hits = set()
    for seqid, seq in seqs.items():
        seq = seq.upper()
        guide_len = len(guide)
        for start in range(0, len(seq) - guide_len + 1):
            plus = seq[start:start + guide_len]
            mm_plus = _hamming(plus, guide)
            if mm_plus <= max_mismatch and \
                    _pam_ok(seq, start, guide_len, pam, pam_side, "+"):
                hits.add((seqid, start, "+", mm_plus))
            minus = reverse_complement(plus)
            mm_minus = _hamming(minus, guide)
            if mm_minus <= max_mismatch and \
                    _pam_ok(seq, start, guide_len, pam, pam_side, "-"):
                hits.add((seqid, start, "-", mm_minus))
    return hits


class GenomeIndexTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.genomes = _random_genome()
        self.fasta = os.path.join(self.tmp.name, "tiny.fa")
        _write_genome(self.fasta, self.genomes)
        self.prefix = os.path.join(self.tmp.name, "tiny_index")

    def test_build_load_and_report(self):
        meta = build_index(self.fasta, self.prefix, k=12, chunk_size=500)
        self.assertTrue(os.path.isfile(self.prefix + ".ggi"))
        self.assertTrue(os.path.isfile(self.prefix + ".json"))
        for field in ("total_bases", "valid_kmer_positions", "build_time_s",
                      "memory_peak_mb", "genome_fingerprint", "k"):
            self.assertIn(field, meta)
        index = load_index(self.prefix)
        self.assertEqual(index.k, 12)
        self.assertEqual(len(index.contigs), 2)
        self.assertTrue(index.is_valid_for(self.fasta))

    def test_build_memory_limit_success_and_clean_failure(self):
        bounded_prefix = os.path.join(self.tmp.name, "bounded_index")
        meta = build_index(
            self.fasta, bounded_prefix, k=10, max_memory_mb=1024)
        self.assertEqual(meta["memory_limit_mb"], 1024)
        self.assertLessEqual(meta["estimated_peak_mb"], 1024)
        self.assertTrue(os.path.isfile(bounded_prefix + ".ggi"))

        limited_prefix = os.path.join(self.tmp.name, "too_small_index")
        with self.assertRaises(MemoryLimitExceededError):
            build_index(
                self.fasta, limited_prefix, k=10, max_memory_mb=1)
        for suffix in (".ggi.tmp", ".json.tmp"):
            self.assertFalse(os.path.exists(limited_prefix + suffix))

    def test_exhaustive_mismatch_search(self):
        meta = build_index(self.fasta, self.prefix, k=12)
        index = load_index(self.prefix)
        matches, report = search_indexed(
            index, [{"qid": "g0", "guide_seq": GUIDE}], self.fasta,
            max_mismatch=2, max_bulge=0, seed_len=12, seed_mm=1,
            pam="NGG", pam_side="3prime")
        found = {
            (h["target"], h["start"], h["strand"], h["mismatch"])
            for h in matches.get("g0", [])
        }
        expected = _brute_force(self.genomes, GUIDE, 2, "NGG", "3prime")
        self.assertEqual(found, expected)
        self.assertGreaterEqual(len(found), 2)
        self.assertIn("search_time_s", report)
        self.assertIn("search_memory_peak_mb", report)

    def test_max_mismatch_excludes_substitution_with_bulge_budget(self):
        guide = "AAAACCCCGGGGTTTTAAAA"
        off_target = "AAAACCCCGGGGTTTTAATA"
        fasta = os.path.join(self.tmp.name, "mismatch_boundary.fa")
        prefix = os.path.join(self.tmp.name, "mismatch_boundary_index")
        _write_genome(fasta, {
            "chr1": "A" * 30 + guide + "TGG"
            + "A" * 20 + off_target + "TGG" + "A" * 30
        })
        build_index(fasta, prefix, k=12)
        matches, _report = search_indexed(
            load_index(prefix),
            [{"qid": "g0", "guide_seq": guide}],
            fasta,
            max_mismatch=0,
            max_bulge=1,
            seed_len=12,
            seed_mm=1,
        )
        self.assertIn(
            (30, 0, 0),
            [(hit["start"], hit["mismatch"], hit["indel"])
             for hit in matches["g0"]],
        )
        self.assertTrue(all(hit["mismatch"] == 0 for hit in matches["g0"]))

    def test_search_finds_indel_and_both_strands(self):
        guide = "ACGTTGCAAGTCCTAGGATC"
        plus_target = guide + "AGG"
        minus_target = reverse_complement(guide[1:]) + "AGG"
        fasta = os.path.join(self.tmp.name, "indel_strands.fa")
        prefix = os.path.join(self.tmp.name, "indel_strands_index")
        _write_genome(fasta, {
            "plus": "C" * 20 + plus_target + "G" * 20,
            "minus": "C" * 20 + minus_target + "G" * 20,
        })
        build_index(fasta, prefix, k=10)
        matches, _report = search_indexed(
            load_index(prefix),
            [{"qid": "g0", "guide_seq": guide}],
            fasta,
            max_mismatch=0, max_bulge=1, seed_len=10, seed_mm=1,
            pam="NGG", pam_side="3prime")
        strands = {h["strand"] for h in matches["g0"]}
        self.assertEqual(strands, {"+", "-"})
        self.assertTrue(any(h["indel"] > 0 for h in matches["g0"]))

    def test_backend_contract_and_reuse(self):
        params = SearchParams(max_mismatch=2, require_pam=True, pam="NGG",
                              output_dir=self.tmp.name)
        guides = [{"qid": "g0", "guide_seq": GUIDE}]
        backend = IndexedBackend()
        first = backend.search(guides, self.fasta, params)
        self.assertTrue(backend.last_report["built"])
        second = backend.search(guides, self.fasta, params)
        self.assertTrue(backend.last_report["reused"])
        self.assertEqual(
            {(h["target"], h["start"], h["strand"])
             for h in first["g0"]},
            {(h["target"], h["start"], h["strand"])
             for h in second["g0"]})
        for hit in first["g0"]:
            self.assertEqual(hit["engine"], "indexed")
            self.assertIn("target", hit)

    def test_stale_index_is_rebuilt(self):
        params = SearchParams(max_mismatch=2, output_dir=self.tmp.name)
        guides = [{"qid": "g0", "guide_seq": GUIDE}]
        backend = IndexedBackend()
        backend.search(guides, self.fasta, params)
        with open(self.fasta, "a", encoding="utf-8") as handle:
            handle.write(">chrC\nACGTACGTACGTACGTACGT\n")
        backend.search(guides, self.fasta, params)
        self.assertTrue(backend.last_report["built"])
        self.assertFalse(backend.last_report["reused"])

    def test_registered_engine(self):
        self.assertIsInstance(get_backend("indexed"), IndexedBackend)
        with tempfile.NamedTemporaryFile(
                "w", suffix=".fa", delete=False,
                encoding="utf-8") as handle:
            handle.write(">chr1\n")
            handle.write("A" * 30 + GUIDE + "GGG" + "A" * 30 + "\n")
            fasta = handle.name
        try:
            params = SearchParams(max_mismatch=1, require_pam=True,
                                  pam="NGG", output_dir=self.tmp.name)
            matches = run_backend(
                "indexed",
                [{"qid": "g0", "guide_seq": GUIDE}],
                fasta, params)
            self.assertEqual(matches["g0"][0]["mismatch"], 0)
            self.assertEqual(matches["g0"][0]["engine"], "indexed")
        finally:
            os.unlink(fasta)

    def test_build_cli(self):
        script = os.path.join(ROOT, "tools", "build_genome_index.py")
        out_dir = os.path.join(self.tmp.name, "cli")
        result = subprocess.run(
            [sys.executable, script, self.fasta, "--output-dir", out_dir,
             "--k", "10", "--max-memory-mb", "1024"],
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        base = os.path.splitext(os.path.basename(self.fasta))[0]
        prefix = os.path.join(out_dir, base)
        self.assertTrue(os.path.isfile(prefix + ".ggi"))
        self.assertTrue(os.path.isfile(prefix + ".json"))
        with open(prefix + ".json", "r", encoding="utf-8") as handle:
            report = json.load(handle)
        self.assertEqual(report["k"], 10)
        self.assertEqual(report["memory_limit_mb"], 1024)
        self.assertLessEqual(report["estimated_peak_mb"], 1024)

    def test_build_selected_contigs(self):
        prefix = os.path.join(self.tmp.name, "chrB_only")
        meta = build_index(self.fasta, prefix, k=10, contigs=["chrB"])
        self.assertEqual(meta["contig_count"], 1)
        self.assertEqual(meta["contigs"][0]["id"], "chrB")
        index = load_index(prefix)
        self.assertEqual(len(index.contigs), 1)


if __name__ == "__main__":
    unittest.main()
