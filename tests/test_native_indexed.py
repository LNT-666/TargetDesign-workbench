#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Differential and compatibility tests for the native indexed engine."""

import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHARED = os.path.join(ROOT, "shared")
sys.path.insert(0, SHARED)

from search.exact_offtarget import reverse_complement  # noqa: E402
from search.genome_index import build_index, load_index, search_indexed  # noqa: E402
from search.offtarget_backend import (  # noqa: E402
    IndexedBackend, SearchParams,
)


GUIDE = "GCCTCTTTCCCACCCACCTT"


def _native_path():
    configured = os.environ.get("PROGRAMFILE_OFFTARGET_NATIVE")
    if configured:
        return configured
    suffix = ".exe" if os.name == "nt" else ""
    candidate = os.path.join(
        ROOT, "native", "bin", "offtarget-engine" + suffix)
    if os.path.isfile(candidate):
        return candidate
    return shutil.which("offtarget-engine")


def _write_fasta(path, sequences):
    with open(path, "w", encoding="utf-8") as handle:
        for seqid, sequence in sequences.items():
            handle.write(">%s\n%s\n" % (seqid, sequence))


def _write_guides(path, guides):
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write("qid\tguide_seq\n")
        for qid, sequence in guides:
            handle.write("%s\t%s\n" % (qid, sequence))


def _run_native(binary, fasta, prefix, guides, extra=None):
    command = [
        binary,
        "search",
        "--genome", fasta,
        "--index", prefix,
        "--guides", guides,
        "--progress-every", "0",
    ]
    command.extend(extra or [])
    result = subprocess.run(
        command, capture_output=True, text=True, encoding="utf-8")
    if result.returncode != 0:
        raise AssertionError(
            "native search failed (%d): %s"
            % (result.returncode, result.stderr))
    hits = {}
    meta = None
    summary = None
    for line in result.stdout.splitlines():
        event = json.loads(line)
        if event["type"] == "hit":
            hits.setdefault(event["qid"], []).append(event)
        elif event["type"] == "meta":
            meta = event
        elif event["type"] == "summary":
            summary = event
    return hits, meta, summary


def _assert_hits_equal(testcase, expected, observed):
    expected_qids = {
        qid: hits for qid, hits in expected.items() if hits
    }
    testcase.assertEqual(set(expected_qids), set(observed))
    for qid, expected_hits in expected_qids.items():
        observed_hits = observed[qid]
        testcase.assertEqual(len(expected_hits), len(observed_hits), qid)
        for expected_hit, observed_hit in zip(
                expected_hits, observed_hits):
            for field in (
                    "qid", "guide", "target", "start", "strand",
                    "mismatch", "indel", "rna_bulges", "dna_bulges",
                    "pam", "target_start", "target_end", "query_start",
                    "query_end", "cigar", "aligned_guide",
                    "aligned_target"):
                testcase.assertEqual(
                    expected_hit[field], observed_hit[field],
                    "%s field %s" % (qid, field))
            testcase.assertAlmostEqual(
                expected_hit["bitscore"], observed_hit["bitscore"],
                places=2)
            testcase.assertEqual("indexed", observed_hit["engine"])


class NativeIndexedDifferentialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.binary = _native_path()
        if not cls.binary or not os.path.isfile(cls.binary):
            raise unittest.SkipTest(
                "native offtarget-engine binary is not built")

    def test_mismatch_only_matches_python_fields(self):
        guide = GUIDE
        target_plus = "A" * 20 + guide + "AGG" + "C" * 20
        target_minus = (
            "G" * 20
            + reverse_complement(guide[1:])
            + "AGG"
            + "T" * 20
        )
        with tempfile.TemporaryDirectory() as tmp:
            fasta = os.path.join(tmp, "genome.fa")
            prefix = os.path.join(tmp, "index")
            guides = os.path.join(tmp, "guides.tsv")
            _write_fasta(
                fasta, {"chrPlus": target_plus, "chrMinus": target_minus})
            _write_guides(guides, [("g0", guide)])
            build_index(fasta, prefix, k=12)
            index = load_index(prefix)
            expected, _report = search_indexed(
                index, [{"qid": "g0", "guide_seq": guide}], fasta,
                max_mismatch=2, max_bulge=0, seed_len=12, seed_mm=1,
                pam="NGG", pam_side="3prime")
            observed, meta, summary = _run_native(
                self.binary, fasta, prefix, guides,
                ["--max-mismatch", "2", "--max-bulge", "0",
                 "--seed-len", "12", "--require-pam", "--pam", "NGG",
                 "--pam-side", "3prime"])
            self.assertEqual(12, meta["index_k"])
            self.assertEqual(1, summary["guides"])
            _assert_hits_equal(self, expected, observed)

    def test_bulges_iupac_u_and_5prime_pam_match_python(self):
        guide = "ACGTTGCAAGTCCTAGGATC"
        guide_u = guide[:10] + "U" + guide[11:]
        normalized = guide_u.replace("U", "T")
        target = normalized[:10] + normalized[11:] + "TTT"
        minus_target = reverse_complement(target)
        with tempfile.TemporaryDirectory() as tmp:
            fasta = os.path.join(tmp, "genome.fa")
            prefix = os.path.join(tmp, "index")
            guides = os.path.join(tmp, "guides.tsv")
            _write_fasta(
                fasta,
                {
                    "chrPlus": "C" * 25 + target + "G" * 25,
                    "chrMinus": "A" * 25 + minus_target + "T" * 25,
                })
            _write_guides(guides, [("bulge", guide_u)])
            build_index(fasta, prefix, k=10)
            index = load_index(prefix)
            expected, _report = search_indexed(
                index,
                [{"qid": "bulge", "guide_seq": guide_u}],
                fasta,
                max_mismatch=1,
                max_bulge=1,
                seed_len=10,
                seed_mm=1,
                pam="TTV",
                pam_side="5prime")
            observed, _meta, _summary = _run_native(
                self.binary, fasta, prefix, guides,
                ["--max-mismatch", "1", "--max-bulge", "1",
                 "--seed-len", "10", "--require-pam", "--pam", "TTV",
                 "--pam-side", "5prime"])
            _assert_hits_equal(self, expected, observed)

    def test_thread_counts_and_repeated_candidates_match(self):
        guides = [
            ("g0", "GCCTCTTTCCCACCCACCTT"),
            ("g1", "ACGTTGCAAGTCCTAGGATC"),
            ("g2", "AAAACCCCGGGGTTTTAAAA"),
            ("g3", "GATTACAGTTACCAGATTAC"),
        ]
        sequences = {}
        for index, (qid, guide) in enumerate(guides):
            sequences["forward%d" % index] = (
                "T" + guide + "AGG" + "C" + "A" * 12)
            sequences["reverse%d" % index] = (
                "G" + reverse_complement(guide + "AGG") + "A" + "T" * 12)
        sequences["repeat2"] = (
            "C" + guides[2][1] + "AGG" + guides[2][1] + "AGG"
            + "G" + "A" * 12)
        sequences["bulge3"] = (
            "A" + guides[3][1][:10] + "A" + guides[3][1][10:]
            + "TGG" + "C" + "A" * 12)

        with tempfile.TemporaryDirectory() as tmp:
            fasta = os.path.join(tmp, "genome.fa")
            prefix = os.path.join(tmp, "index")
            guide_path = os.path.join(tmp, "guides.tsv")
            _write_fasta(fasta, sequences)
            _write_guides(guide_path, guides)
            build_index(fasta, prefix, k=10)
            index = load_index(prefix)

            for max_bulge in (0, 1):
                for require_pam in (False, True):
                    pam = "NGG" if require_pam else None
                    expected, _report = search_indexed(
                        index,
                        [{"qid": qid, "guide_seq": seq}
                         for qid, seq in guides],
                        fasta,
                        max_mismatch=2,
                        max_bulge=max_bulge,
                        seed_len=10,
                        seed_mm=1,
                        pam=pam,
                        pam_side="3prime",
                    )
                    repeated = [
                        hit for hit in expected.get("g2", [])
                        if hit["target"] == "repeat2"
                    ]
                    self.assertGreaterEqual(len(repeated), 2)
                    self.assertEqual(
                        {"+", "-"},
                        {hit["strand"]
                         for qid_hits in expected.values()
                         for hit in qid_hits},
                    )

                    baseline = None
                    for threads in (1, 2, 4):
                        extra = [
                            "--max-mismatch", "2",
                            "--max-bulge", str(max_bulge),
                            "--seed-len", "10",
                            "--threads", str(threads),
                        ]
                        if require_pam:
                            extra.extend([
                                "--require-pam", "--pam", "NGG",
                                "--pam-side", "3prime",
                            ])
                        observed, meta, summary = _run_native(
                            self.binary, fasta, prefix, guide_path, extra)
                        _assert_hits_equal(self, expected, observed)
                        self.assertEqual(10, meta["index_k"])
                        self.assertEqual(
                            sum(len(hits) for hits in observed.values()),
                            summary["hits"])
                        if baseline is None:
                            baseline = observed
                        else:
                            self.assertEqual(baseline, observed)

    def test_randomized_genomes_match_python(self):
        rng = random.Random(20260914)
        for case_index in range(5):
            with self.subTest(case=case_index):
                guide = "".join(rng.choice("ACGT") for _ in range(20))
                sequences = {}
                for contig_index in range(2):
                    sequence = list(
                        "".join(rng.choice("ACGT") for _ in range(500)))
                    if contig_index == 0:
                        replacement = list(guide)
                        for position in rng.sample(range(20), 2):
                            replacement[position] = rng.choice("ACGT")
                        start = rng.randrange(20, 450)
                        sequence[start:start + 20] = replacement
                        sequence[start + 20:start + 23] = list("AGG")
                    sequences["chr%d" % (contig_index + 1)] = "".join(
                        sequence)
                with tempfile.TemporaryDirectory() as tmp:
                    fasta = os.path.join(tmp, "genome.fa")
                    prefix = os.path.join(tmp, "index")
                    guides = os.path.join(tmp, "guides.tsv")
                    _write_fasta(fasta, sequences)
                    _write_guides(guides, [("g0", guide)])
                    build_index(fasta, prefix, k=12)
                    expected, _report = search_indexed(
                        load_index(prefix),
                        [{"qid": "g0", "guide_seq": guide}],
                        fasta,
                        max_mismatch=2,
                        max_bulge=0,
                        seed_len=12,
                        seed_mm=1,
                        pam="NGG",
                        pam_side="3prime")
                    observed, _meta, _summary = _run_native(
                        self.binary, fasta, prefix, guides,
                        ["--max-mismatch", "2", "--max-bulge", "0",
                         "--seed-len", "12", "--require-pam",
                         "--pam", "NGG", "--pam-side", "3prime"])
                    _assert_hits_equal(self, expected, observed)

    def test_small_genome_fallback_invalid_bases_and_boundaries(self):
        guide = "AAAACCCCGGGGTTTTAAAA"
        sequences = {
            "left": guide + "AGG",
            "right": "TTT" + reverse_complement(guide),
            "invalid": "N" * 5 + guide[:8] + "N" + guide[9:] + "TGG",
        }
        with tempfile.TemporaryDirectory() as tmp:
            fasta = os.path.join(tmp, "genome.fa")
            prefix = os.path.join(tmp, "index")
            guides = os.path.join(tmp, "guides.tsv")
            _write_fasta(fasta, sequences)
            _write_guides(guides, [("g0", guide)])
            build_index(fasta, prefix, k=12)
            expected, _report = search_indexed(
                load_index(prefix),
                [{"qid": "g0", "guide_seq": guide}],
                fasta,
                max_mismatch=0,
                max_bulge=1,
                seed_len=12,
                seed_mm=1)
            observed, _meta, summary = _run_native(
                self.binary, fasta, prefix, guides,
                ["--max-mismatch", "0", "--max-bulge", "1",
                 "--seed-len", "12"])
            _assert_hits_equal(self, expected, observed)
            self.assertFalse(summary["seed_plan_guaranteed"])
            self.assertFalse(summary["exhaustive_seed_plan"])


class NativeIndexCompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.binary = _native_path()
        if not cls.binary or not os.path.isfile(cls.binary):
            raise unittest.SkipTest(
                "native offtarget-engine binary is not built")

    def test_native_build_is_readable_by_python(self):
        guide = GUIDE
        sequences = {
            "chr1": "A" * 30 + guide + "AGG" + "C" * 30,
            "chr2": reverse_complement(guide[2:]) + "AGG" + "G" * 40,
        }
        with tempfile.TemporaryDirectory() as tmp:
            fasta = os.path.join(tmp, "genome.fa")
            py_prefix = os.path.join(tmp, "python_index")
            native_prefix = os.path.join(tmp, "native_index")
            _write_fasta(fasta, sequences)
            build_index(fasta, py_prefix, k=8)
            result = subprocess.run(
                [self.binary, "build-index", "--genome", fasta,
                 "--prefix", native_prefix, "--k", "8"],
                capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(0, result.returncode, result.stderr)
            py_index = load_index(py_prefix)
            native_index = load_index(native_prefix)
            self.assertEqual(py_index.k, native_index.k)
            self.assertEqual(py_index.total_bases, native_index.total_bases)
            self.assertEqual(py_index.contigs, native_index.contigs)
            self.assertTrue(
                (py_index.offsets == native_index.offsets).all())
            self.assertTrue(
                (py_index.positions == native_index.positions).all())

    def test_native_build_stale_and_corrupt_diagnostics(self):
        with tempfile.TemporaryDirectory() as tmp:
            fasta = os.path.join(tmp, "genome.fa")
            prefix = os.path.join(tmp, "index")
            _write_fasta(
                fasta, {"chr1": "A" * 40 + GUIDE + "AGG" + "C" * 40})
            result = subprocess.run(
                [self.binary, "build-index", "--genome", fasta,
                 "--prefix", prefix, "--k", "8"],
                capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(0, result.returncode, result.stderr)
            inspected = subprocess.run(
                [self.binary, "inspect-index", "--genome", fasta,
                 "--index", prefix, "--json"],
                capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(0, inspected.returncode, inspected.stderr)
            self.assertTrue(json.loads(inspected.stdout)["valid"])

            with open(fasta, "a", encoding="utf-8") as handle:
                handle.write(">chr2\nACGTACGTACGT\n")
            stale = subprocess.run(
                [self.binary, "inspect-index", "--genome", fasta,
                 "--index", prefix, "--json"],
                capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(0, stale.returncode, stale.stderr)
            self.assertFalse(json.loads(stale.stdout)["valid"])

            with open(prefix + ".ggi", "r+b") as handle:
                handle.seek(9)
                handle.write(b"\x02")
            bad_version = subprocess.run(
                [self.binary, "inspect-index", "--genome", fasta,
                 "--index", prefix, "--json"],
                capture_output=True, text=True, encoding="utf-8")
            self.assertNotEqual(0, bad_version.returncode)
            self.assertIn("Unsupported index version",
                          bad_version.stderr)

            with open(prefix + ".ggi", "r+b") as handle:
                handle.seek(9)
                handle.write(b"\x01")
                handle.truncate(
                    max(10, os.path.getsize(prefix + ".ggi") - 4))
            truncated = subprocess.run(
                [self.binary, "inspect-index", "--genome", fasta,
                 "--index", prefix, "--json"],
                capture_output=True, text=True, encoding="utf-8")
            self.assertNotEqual(0, truncated.returncode)
            self.assertIn("truncated", truncated.stderr.lower())

            with open(prefix + ".ggi", "r+b") as handle:
                handle.seek(0)
                handle.write(b"BROKEN!!")
            corrupt = subprocess.run(
                [self.binary, "inspect-index", "--genome", fasta,
                 "--index", prefix, "--json"],
                capture_output=True, text=True, encoding="utf-8")
            self.assertNotEqual(0, corrupt.returncode)
            self.assertIn("Not a CRISPR genome index",
                          corrupt.stderr)


class NativeBackendIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.binary = _native_path()
        if not cls.binary or not os.path.isfile(cls.binary):
            raise unittest.SkipTest(
                "native offtarget-engine binary is not built")

    def test_backend_uses_native_and_reuses_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            fasta = os.path.join(tmp, "genome.fa")
            _write_fasta(
                fasta, {"chr1": "A" * 25 + GUIDE + "AGG" + "C" * 25})
            prefix = os.path.join(tmp, "native_index")
            params = SearchParams(
                max_mismatch=1,
                max_bulge=0,
                seed_len=12,
                require_pam=True,
                pam="NGG",
                index_path=prefix,
                extra={"k": 12},
            )
            progress = []
            with mock.patch.dict(
                    os.environ,
                    {
                        "PROGRAMFILE_OFFTARGET_NATIVE": self.binary,
                        "PROGRAMFILE_NATIVE_INDEXED": "auto",
                        "PROGRAMFILE_NATIVE_INDEXED_FALLBACK": "1",
                    },
                    clear=False):
                backend = IndexedBackend()
                first = backend.search(
                    [{"qid": "g0", "guide_seq": GUIDE}],
                    fasta,
                    params,
                    progress_callback=lambda done, total: progress.append(
                        (done, total)),
                )
                self.assertEqual("native-cpp",
                                 backend.last_report["implementation"])
                self.assertTrue(backend.last_report["built"])
                self.assertEqual([(1, 1)], progress)
                second = backend.search(
                    [{"qid": "g0", "guide_seq": GUIDE}], fasta, params)
                self.assertTrue(backend.last_report["reused"])
            self.assertEqual(
                {(h["target"], h["start"], h["strand"])
                 for h in first["g0"]},
                {(h["target"], h["start"], h["strand"])
                 for h in second["g0"]})

    def test_default_auto_uses_native_when_available(self):
        with tempfile.TemporaryDirectory() as tmp:
            fasta = os.path.join(tmp, "genome.fa")
            _write_fasta(
                fasta, {"chr1": "A" * 25 + GUIDE + "AGG" + "C" * 25})
            params = SearchParams(
                max_mismatch=1,
                max_bulge=0,
                seed_len=12,
                require_pam=True,
                pam="NGG",
                output_dir=tmp,
                extra={"k": 12},
            )
            with mock.patch.dict(
                    os.environ,
                    {"PROGRAMFILE_OFFTARGET_NATIVE": self.binary},
                    clear=False):
                os.environ.pop("PROGRAMFILE_NATIVE_INDEXED", None)
                backend = IndexedBackend()
                backend.search(
                    [{"qid": "g0", "guide_seq": GUIDE}], fasta, params)
            self.assertEqual("native-cpp",
                             backend.last_report["implementation"])

    def test_default_auto_uses_python_without_binary(self):
        with tempfile.TemporaryDirectory() as tmp:
            fasta = os.path.join(tmp, "genome.fa")
            _write_fasta(
                fasta, {"chr1": "A" * 25 + GUIDE + "AGG" + "C" * 25})
            params = SearchParams(
                max_mismatch=1,
                max_bulge=0,
                seed_len=12,
                require_pam=True,
                pam="NGG",
                output_dir=tmp,
                extra={"k": 12},
            )
            with mock.patch.dict(os.environ, {}, clear=False), mock.patch(
                    "search.native_offtarget.find_binary",
                    return_value=None):
                os.environ.pop("PROGRAMFILE_NATIVE_INDEXED", None)
                os.environ.pop("PROGRAMFILE_OFFTARGET_NATIVE", None)
                backend = IndexedBackend()
                backend.search(
                    [{"qid": "g0", "guide_seq": GUIDE}], fasta, params)
            self.assertEqual("python",
                             backend.last_report["implementation"])

    def test_explicit_disable_uses_python(self):
        with tempfile.TemporaryDirectory() as tmp:
            fasta = os.path.join(tmp, "genome.fa")
            _write_fasta(
                fasta, {"chr1": "A" * 25 + GUIDE + "AGG" + "C" * 25})
            params = SearchParams(
                max_mismatch=1,
                max_bulge=0,
                seed_len=12,
                require_pam=True,
                pam="NGG",
                output_dir=tmp,
                extra={"k": 12},
            )
            with mock.patch.dict(
                    os.environ,
                    {
                        "PROGRAMFILE_OFFTARGET_NATIVE": self.binary,
                        "PROGRAMFILE_NATIVE_INDEXED": "0",
                    },
                    clear=False):
                backend = IndexedBackend()
                backend.search(
                    [{"qid": "g0", "guide_seq": GUIDE}], fasta, params)
            self.assertEqual("python",
                             backend.last_report["implementation"])

    def test_early_native_failure_falls_back_to_python(self):
        with tempfile.TemporaryDirectory() as tmp:
            fasta = os.path.join(tmp, "genome.fa")
            _write_fasta(
                fasta, {"chr1": "A" * 25 + GUIDE + "AGG" + "C" * 25})
            params = SearchParams(
                max_mismatch=1,
                max_bulge=0,
                seed_len=12,
                require_pam=True,
                pam="NGG",
                output_dir=tmp,
                extra={"k": 12},
            )
            from search import native_offtarget

            def fail(*_args, **_kwargs):
                raise native_offtarget.NativeEngineError(
                    ["offtarget-engine", "search"], 4, "injected failure")

            with mock.patch.dict(
                    os.environ,
                    {
                        "PROGRAMFILE_OFFTARGET_NATIVE": self.binary,
                        "PROGRAMFILE_NATIVE_INDEXED": "1",
                    },
                    clear=False), mock.patch(
                        "search.native_offtarget.search",
                        side_effect=fail):
                os.environ.pop("PROGRAMFILE_NATIVE_INDEXED_FALLBACK", None)
                backend = IndexedBackend()
                hits = backend.search(
                    [{"qid": "g0", "guide_seq": GUIDE}], fasta, params)
            self.assertIn("g0", hits)
            self.assertEqual("python",
                             backend.last_report["implementation"])
            self.assertIn("native_fallback_reason",
                          backend.last_report)

    def test_cli_memory_limit_build_success_and_clean_failures(self):
        with tempfile.TemporaryDirectory() as tmp:
            fasta = os.path.join(tmp, "genome.fa")
            guides = os.path.join(tmp, "guides.tsv")
            prefix = os.path.join(tmp, "bounded_index")
            _write_fasta(
                fasta, {"chr1": "A" * 25 + GUIDE + "AGG" + "C" * 25})
            _write_guides(guides, [("g0", GUIDE)])

            build = subprocess.run(
                [
                    self.binary, "build-index",
                    "--genome", fasta,
                    "--prefix", prefix,
                    "--k", "10",
                    "--max-memory-mb", "1024",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(build.returncode, 0, build.stderr)
            report = json.loads(build.stdout)
            self.assertEqual(report["memory_limit_mb"], 1024)
            self.assertLessEqual(report["estimated_peak_mb"], 1024)

            output = os.path.join(tmp, "must_not_exist.jsonl")
            search = subprocess.run(
                [
                    self.binary, "search",
                    "--genome", fasta,
                    "--index", prefix,
                    "--guides", guides,
                    "--output", output,
                    "--max-memory-mb", "1",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(search.returncode, 6)
            self.assertIn("MEMORY_LIMIT_EXCEEDED", search.stderr)
            self.assertFalse(os.path.exists(output))

            failed_prefix = os.path.join(tmp, "failed_index")
            failed_build = subprocess.run(
                [
                    self.binary, "build-index",
                    "--genome", fasta,
                    "--prefix", failed_prefix,
                    "--k", "10",
                    "--max-memory-mb", "1",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(failed_build.returncode, 6)
            self.assertFalse(os.path.exists(failed_prefix + ".ggi"))
            self.assertFalse(os.path.exists(failed_prefix + ".ggi.tmp"))
            self.assertFalse(os.path.exists(failed_prefix + ".json.tmp"))


if __name__ == "__main__":
    unittest.main()
