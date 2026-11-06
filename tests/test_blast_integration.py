#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Real NCBI BLAST+ regressions for full-query candidate realignment."""

import contextlib
import os
import random
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHARED = os.path.join(ROOT, "shared")
sys.path.insert(0, SHARED)


GUIDE = "ACGTCAGTGCATGACTAGCT"
PAM_WINDOW = "TTGAT" + GUIDE
BLAST_TOOLS = ("blastn", "makeblastdb")


def _blast_versions():
    versions = {}
    for command in BLAST_TOOLS:
        path = shutil.which(command)
        if path is None:
            return None, "tool unavailable: %s" % command
        try:
            result = subprocess.run(
                [command, "-version"], capture_output=True, text=True)
        except OSError as exc:
            return None, "version/command failure: %s (%s)" % (
                command, exc)
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            return None, "version/command failure: %s (%s)" % (
                command, detail or "exit %d" % result.returncode)
        text = (result.stdout or result.stderr or "").strip()
        versions[command] = text.splitlines()[0] if text else path
    return versions, ""


def _reverse_complement(sequence):
    return sequence.translate(str.maketrans("ACGT", "TGCA"))[::-1]


class RealBlastRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        versions, reason = _blast_versions()
        if versions is None:
            raise unittest.SkipTest(reason)
        cls.blast_versions = versions
        try:
            from pyfaidx import Fasta  # noqa: F401
            from search import blast_utils, exact_offtarget  # noqa: F401
        except ImportError as exc:
            raise RuntimeError(
                "required Python search dependencies are missing: %s" % exc)

    @staticmethod
    def _random_sequence(length, seed):
        rng = random.Random(seed)
        return "".join(rng.choice("ACGT") for _ in range(length))

    @classmethod
    @contextlib.contextmanager
    def _reference(cls, sequence, tmp):
        from pyfaidx import Fasta
        from search.blast_utils import reverse_complement

        fasta_path = os.path.join(tmp, "genome.fa")
        db_prefix = os.path.join(tmp, "blastdb", "genome")
        os.makedirs(os.path.dirname(db_prefix), exist_ok=True)
        with open(fasta_path, "w", encoding="utf-8") as handle:
            handle.write(">chr1\n%s\n" % sequence)
        result = subprocess.run(
            ["makeblastdb", "-in", fasta_path, "-dbtype", "nucl",
             "-out", db_prefix],
            capture_output=True, text=True)
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            raise AssertionError(
                "version/command failure: makeblastdb (%s)"
                % (detail or "exit %d" % result.returncode))
        genome = Fasta(fasta_path)
        try:
            yield fasta_path, db_prefix, genome
        finally:
            close = getattr(genome, "close", None)
            if callable(close):
                close()

    @staticmethod
    def _query_fasta(tmp, sequences):
        path = os.path.join(tmp, "query.fa")
        with open(path, "w", encoding="utf-8") as handle:
            for qid, sequence in sequences.items():
                handle.write(">%s\n%s\n" % (qid, sequence))
        return path

    def _run_blast(self, tmp, db_prefix, genome, sequences, **kwargs):
        from search.blast_utils import run_blastn

        query_path = self._query_fasta(tmp, sequences)
        hits = run_blastn(
            query_path, db_prefix, task="blastn-short", word_size=4,
            evalue=1000, genome=genome, **kwargs)
        return hits

    def test_real_blast_matches_exact_spans_on_a_confirmed_fixture(self):
        from search.offtarget_backend import ExactBackend, SearchParams

        sequence = list(self._random_sequence(420, seed=17))
        sequence[120:140] = list(GUIDE)
        with tempfile.TemporaryDirectory() as tmp:
            with self._reference("".join(sequence), tmp) as (
                    fasta_path, db_prefix, genome):
                blast = self._run_blast(
                    tmp, db_prefix, genome, {"g0": GUIDE},
                    max_mismatch=0, max_bulge=0)
                exact = ExactBackend().search(
                    [{"qid": "g0", "guide_seq": GUIDE}],
                    fasta_path, SearchParams(
                        max_mismatch=0, max_bulge=0, require_pam=False))
        blast_spans = {
            (hit["target"], hit["target_start"], hit["target_end"],
             hit["strand"])
            for hit in blast.get("g0", [])
        }
        if not blast_spans:
            self.fail("candidate miss: BLAST returned no HSP for the fixture")
        exact_spans = {
            (hit["target"], hit["target_start"], hit["target_end"],
             hit["strand"])
            for hit in exact.get("g0", [])
        }
        self.assertEqual(
            blast_spans, exact_spans,
            "coordinate/set mismatch: BLAST=%r exact=%r"
            % (sorted(blast_spans), sorted(exact_spans)))

    def test_real_blast_rebuilds_strands_edits_bulges_and_end_gaps(self):
        sequence = list(self._random_sequence(1120, seed=29))
        sequence[100:120] = list(GUIDE)
        sequence[200:220] = list(_reverse_complement(GUIDE))

        first_mutated = list(GUIDE)
        first_mutated[0] = "A" if first_mutated[0] != "A" else "C"
        sequence[300:320] = first_mutated

        last_mutated = list(GUIDE)
        last_mutated[-1] = "A" if last_mutated[-1] != "A" else "C"
        sequence[400:420] = last_mutated

        multi_bulge = GUIDE[:4] + "G" + GUIDE[4:14] + "G" + GUIDE[14:]
        sequence[500:522] = list(multi_bulge)
        sequence[600:619] = list(GUIDE[1:])
        sequence[700:719] = list(GUIDE[:-1])
        sequence[800:825] = list(PAM_WINDOW)

        with tempfile.TemporaryDirectory() as tmp:
            with self._reference("".join(sequence), tmp) as (
                    _fasta_path, db_prefix, genome):
                hits = self._run_blast(
                    tmp, db_prefix, genome, {"g0": GUIDE},
                    max_mismatch=1, max_bulge=2)
                pam_hits = self._run_blast(
                    tmp, db_prefix, genome, {"pam": PAM_WINDOW},
                    max_mismatch=0, max_bulge=0, require_pam=True,
                    pam_motif="TTGAT", pam_side="5prime",
                    window_motif="TTGAT", window_side="downstream",
                    seed_mismatch_max=0, seed_len=5)
        spans = {
            (hit["target"], hit["target_start"], hit["target_end"],
             hit["strand"])
            for hit in hits.get("g0", [])
        }
        expected = {
            ("chr1", 100, 120, "+"),
            ("chr1", 200, 220, "-"),
            ("chr1", 300, 320, "+"),
            ("chr1", 400, 420, "+"),
            ("chr1", 500, 522, "+"),
            ("chr1", 600, 619, "+"),
            ("chr1", 700, 719, "+"),
        }
        missing = expected - spans
        if missing:
            self.fail(
                "candidate miss/coordinate/set mismatch: missing %r "
                "from BLAST spans %r"
                % (sorted(missing), sorted(spans)))
        for hit in hits["g0"]:
            self.assertEqual(hit["query_start"], 0)
            self.assertEqual(hit["query_end"], len(GUIDE))
            self.assertEqual(
                hit["aligned_guide"].replace("-", ""), GUIDE)
        self.assertIn(("chr1", 800, 825, "+"), {
            (hit["target"], hit["target_start"], hit["target_end"],
             hit["strand"])
            for hit in pam_hits.get("pam", [])
        })


if __name__ == "__main__":
    unittest.main()
