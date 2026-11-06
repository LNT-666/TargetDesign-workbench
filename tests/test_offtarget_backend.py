#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the unified off-target backend layer."""

import argparse
import io
import os
import sys
import tempfile
import unittest
import urllib.parse
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHARED = os.path.join(ROOT, "shared")
sys.path.insert(0, SHARED)

from search.offtarget_backend import (  # noqa: E402
    PYTHON_FALLBACK_ENV, BlastBackend,
    ExactBackend, GGGenomeBackend, OffTargetBackend,
    PythonFallbackDeclined, SearchParameterError, SearchParams,
    approve_python_fallback, ask_python_fallback_on_stdin,
    auto_engine_candidates, compare_engines, engine_capability_matrix,
    get_backend, resolve_engine, resolve_python_fallback_policy,
    run_backend, validate_search_params,
)

import search.offtarget_backend as offtarget_backend  # noqa: E402


GUIDE = "GCCTCTTTCCCACCCACCTT"
FLANK = "A" * 30
PAIRED_FASTA = FLANK + GUIDE + "GGG" + FLANK + "\n"


def _write_genome(path):
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(">chr1\n")
        handle.write(PAIRED_FASTA)


def _fake_genome(sequences):
    """Return a pyfaidx-like genome object that only needs slice access."""
    class _Record:
        def __init__(self, sequence):
            self._sequence = sequence

        def __len__(self):
            return len(self._sequence)

        def __getitem__(self, item):
            return self._sequence[item]

    class _Genome:
        def __init__(self, records):
            self._records = records

        def __getitem__(self, key):
            return _Record(self._records[key])

    return _Genome(dict(sequences))


class SearchParamsTests(unittest.TestCase):
    def test_from_args(self):
        args = argparse.Namespace(
            max_mismatch=3, seed_len=12, seed_mismatch=None,
            seed_mismatch_max=1, pam="NGG", pam_side="3prime",
            require_pam=True, blastdb="", output_dir="/tmp/out",
            genome_build="hg38")
        params = SearchParams.from_args(args)
        self.assertEqual(params.max_mismatch, 3)
        self.assertEqual(params.seed_mismatch_max, 1)
        self.assertTrue(params.require_pam)
        self.assertEqual(params.genome_build, "hg38")

    def test_zero_mismatch_is_preserved(self):
        args = argparse.Namespace(max_mismatch=0, max_bulge=0)
        params = SearchParams.from_args(args)
        self.assertEqual(params.max_mismatch, 0)
        self.assertEqual(params.max_bulge, 0)


class BlastPamTests(unittest.TestCase):
    def test_queries_embed_pam(self):
        from search.blast_utils import queries_embed_pam

        windows = [
            "GGCAGCTTTGGTGCCTTCGCAGG",
            "GCAGGCTGTTTCCTTGCTTCAGG",
        ]
        self.assertTrue(queries_embed_pam(windows, "NGG", "NGG", 20))
        self.assertFalse(queries_embed_pam(windows, "NGG", "NGG", 19))
        self.assertFalse(
            queries_embed_pam(windows, "NGG", "GG", 20))

    def test_pam_ok_expands_iupac_pattern(self):
        from search.blast_utils import _pam_ok_blast

        genome = object()
        with mock.patch(
                "search.blast_utils.fetch_sequence",
                return_value="AGG") as fetch:
            self.assertTrue(_pam_ok_blast(
                genome, "chr1", 10, 30, "+", "NGG", "3prime"))
        fetch.assert_called_once_with(genome, "chr1", 30, 33)

        with mock.patch(
                "search.blast_utils.fetch_sequence",
                return_value="AAA"):
            self.assertFalse(_pam_ok_blast(
                genome, "chr1", 10, 30, "+", "NGG", "3prime"))


class PamWindowAnchorTests(unittest.TestCase):
    """PAMs live inside an extracted window instead of beyond its far edge."""

    def test_downstream_plus_window_anchors_the_pam_at_its_five_prime_edge(self):
        from search.blast_utils import pam_span_in_window

        window = "TTGAT" + "A" * 20
        self.assertEqual(
            pam_span_in_window(window, "TTGAT", "TTGAT", "downstream"),
            ((0, 5), "TTGAT"))

    def test_degenerate_motif_anchors_the_full_pam(self):
        from search.blast_utils import pam_span_in_window

        window = "TTGAT" + "A" * 20
        self.assertEqual(
            pam_span_in_window(window, "TTR", "TTGAT", "downstream"),
            ((0, 5), "TTGAT"))
        # A relaxed anchor still points at the strict PAM span, which is what
        # makes the TTR/TTGAT TnpB configuration usable.
        relaxed = "TTAGT" + "A" * 20
        self.assertEqual(
            pam_span_in_window(relaxed, "TTR", "TTGAT", "downstream"),
            ((0, 5), "TTGAT"))

    def test_downstream_minus_window_anchors_the_pam_at_its_three_prime_edge(self):
        from search.blast_utils import pam_span_in_window, reverse_complement

        window = "A" * 20 + reverse_complement("TTGAT")
        self.assertEqual(
            pam_span_in_window(window, "TTGAT", "TTGAT", "downstream"),
            ((20, 25), reverse_complement("TTGAT")))

    def test_upstream_plus_window_anchors_the_pam_at_its_three_prime_edge(self):
        from search.blast_utils import pam_span_in_window

        window = "A" * 20 + "TTGAT"
        self.assertEqual(
            pam_span_in_window(window, "TTGAT", "TTGAT", "upstream"),
            ((20, 25), "TTGAT"))

    def test_upstream_minus_window_anchors_the_pam_at_its_five_prime_edge(self):
        from search.blast_utils import pam_span_in_window, reverse_complement

        window = reverse_complement("TTGAT") + "A" * 20
        self.assertEqual(
            pam_span_in_window(window, "TTGAT", "TTGAT", "upstream"),
            ((0, 5), reverse_complement("TTGAT")))

    def test_guide_only_query_has_no_embedded_pam(self):
        from search.blast_utils import pam_span_in_window

        self.assertIsNone(pam_span_in_window("A" * 20, None, "TTGAT"))
        self.assertIsNone(pam_span_in_window("A" * 20, "TTGAT", "TTGAT"))

class BackendTests(unittest.TestCase):
    def test_find_existing_blastdb(self):
        from search.blast_utils import find_existing_blastdb

        with tempfile.TemporaryDirectory() as tmp:
            fasta = os.path.join(tmp, "GCF_genome.fna")
            prefix = os.path.join(tmp, "GCF_genome.blastdb")
            with open(fasta, "w", encoding="utf-8") as handle:
                handle.write(">chr1\nACGTACGTACGT\n")
            with open(prefix + ".nin", "w", encoding="utf-8"):
                pass
            with open(prefix + ".nsq", "w", encoding="utf-8"):
                pass
            from search.blast_utils import write_blastdb_manifest
            write_blastdb_manifest(fasta, prefix)
            self.assertEqual(
                find_existing_blastdb(fasta), prefix)

    def test_missing_or_stale_blastdb_manifest_is_not_reused(self):
        from search.blast_utils import (
            blastdb_is_current, find_existing_blastdb,
            write_blastdb_manifest,
        )

        with tempfile.TemporaryDirectory() as tmp:
            fasta = os.path.join(tmp, "genome.fa")
            prefix = os.path.join(tmp, "genome.blastdb")
            with open(fasta, "w", encoding="utf-8") as handle:
                handle.write(">chr1\n" + "A" * 50 + "\n")
            for extension in (".nin", ".nsq"):
                with open(prefix + extension, "w", encoding="utf-8"):
                    pass
            self.assertIsNone(find_existing_blastdb(fasta))
            self.assertEqual(
                find_existing_blastdb(fasta, trust_existing=True), prefix)
            write_blastdb_manifest(fasta, prefix)
            self.assertTrue(blastdb_is_current(fasta, prefix))
            with open(fasta, "r+", encoding="utf-8") as handle:
                content = handle.read()
                handle.seek(0)
                handle.write(content[:28] + "C" + content[29:])
            self.assertFalse(blastdb_is_current(fasta, prefix))

    def test_stale_manifest_triggers_automatic_rebuild(self):
        from search.blast_utils import build_blastdb

        with tempfile.TemporaryDirectory() as tmp:
            fasta = os.path.join(tmp, "genome.fa")
            prefix = os.path.join(tmp, "genome.blastdb")
            with open(fasta, "w", encoding="utf-8") as handle:
                handle.write(">chr1\n" + "A" * 100 + "\n")
            build_calls = []

            def fake_run(cmd, **kwargs):
                if cmd[:2] == ["makeblastdb", "-version"]:
                    return mock.Mock(
                        returncode=0, stdout="makeblastdb: 2.15", stderr="")
                build_calls.append(list(cmd))
                for extension in (".nin", ".nsq"):
                    with open(prefix + extension, "w", encoding="utf-8"):
                        pass
                return mock.Mock(returncode=0, stdout="", stderr="")

            with mock.patch(
                    "search.blast_utils.subprocess.run",
                    side_effect=fake_run):
                build_blastdb(fasta, prefix)
                build_blastdb(fasta, prefix)
                with open(fasta, "r+", encoding="utf-8") as handle:
                    content = handle.read()
                    handle.seek(0)
                    handle.write(content[:55] + "C" + content[56:])
                build_blastdb(fasta, prefix)
            self.assertEqual(len(build_calls), 2)

    def test_engine_capability_matrix_and_preflight_rejection(self):
        matrix = engine_capability_matrix()
        self.assertEqual(matrix["blast"]["indels"], "basic")
        self.assertEqual(matrix["gggenome"]["unknown_gap_type"], True)
        with mock.patch(
                "search.offtarget_backend.native_indexed_available",
                return_value=True), mock.patch(
                    "search.offtarget_backend.IndexedBackend.available",
                    return_value=(True, "")):
            self.assertEqual(
                resolve_engine("auto", SearchParams(max_bulge=0),
                               genome_size=1000000),
                "indexed")
        with mock.patch(
                "search.offtarget_backend.native_indexed_available",
                return_value=False), mock.patch.object(
                    BlastBackend, "available", return_value=(True, "")):
            self.assertEqual(
                resolve_engine("auto", SearchParams(max_bulge=1),
                               genome_size=1000000),
                "blast")
            self.assertEqual(
                resolve_engine(
                    "auto", SearchParams(max_bulge=1),
                    genome_size=201 * 1024 * 1024),
                "blast")
        with mock.patch.object(
                BlastBackend, "available", return_value=(True, "")):
            self.assertEqual(
                resolve_engine(
                    "auto",
                    SearchParams(
                        max_bulge=1, max_bulge_explicit=True,
                        blastdb="existing_db")),
                "blast")
        with mock.patch(
                "search.offtarget_backend.IndexedBackend.available",
                return_value=(True, "")):
            self.assertEqual(
                resolve_engine(
                    "auto",
                    SearchParams(max_bulge=0, index_path="idx/prefix"),
                    genome_size=201 * 1024 * 1024),
                "indexed")

    def test_mismatch_only_engine_rejects_bulge_via_a_stub_backend(self):
        # A mismatch-only engine must refuse max_bulge>0. The base class
        # already declares indels="none", so a stub is enough and the real
        # engines keep their production capability declarations.
        class StubBackend(OffTargetBackend):
            name = "stub_none"
            display_name = "Stub (mismatch only)"

        with mock.patch.dict(
                offtarget_backend.BACKENDS, {"stub_none": StubBackend},
                clear=False):
            with mock.patch.object(
                    StubBackend, "available", return_value=(True, "")):
                with self.assertRaises(SearchParameterError):
                    validate_search_params(
                        "stub_none", SearchParams(max_bulge=1))
        self.assertNotIn("stub_none", offtarget_backend.BACKENDS)

    def test_auto_engine_candidates_full_matrix(self):
        small = 20_000_000
        large = 201 * 1024 * 1024
        cases = [
            (True, 0, small, ["indexed", "blast", "exact"]),
            (True, 1, small, ["indexed", "blast", "exact"]),
            (True, 0, large, ["blast", "indexed"]),
            (True, 1, large, ["blast", "indexed"]),
            (False, 0, small, ["blast", "indexed", "exact"]),
            (False, 1, small, ["blast", "exact", "indexed"]),
            (False, 0, large, ["blast", "indexed"]),
            (False, 1, large, ["blast", "indexed"]),
        ]
        for native, bulge, size, expected in cases:
            params = SearchParams(
                max_bulge=bulge, max_bulge_explicit=bool(bulge))
            with self.subTest(native_available=native, max_bulge=bulge,
                              genome_size=size):
                self.assertEqual(
                    auto_engine_candidates(
                        params, size, native_available=native),
                    expected)

    def test_auto_engine_candidates_with_an_explicit_resource(self):
        # An explicitly named resource pins auto to that single engine
        # instead of ranking it as a first preference.
        small = 20_000_000
        for native in (True, False):
            with self.subTest(native_available=native, resource="blastdb"):
                self.assertEqual(
                    auto_engine_candidates(
                        SearchParams(max_bulge=0, blastdb="existing_db"),
                        small, native_available=native),
                    ["blast"])
            with self.subTest(native_available=native,
                              resource="index_path"):
                self.assertEqual(
                    auto_engine_candidates(
                        SearchParams(max_bulge=0, index_path="idx/prefix"),
                        small, native_available=native),
                    ["indexed"])

    def test_auto_engine_candidates_without_a_genome_size(self):
        # An unreadable genome cannot be shown to exceed the exact limit, so
        # it follows the small-genome branch.
        for native in (True, False):
            for bulge in (0, 1):
                params = SearchParams(
                    max_bulge=bulge, max_bulge_explicit=bool(bulge))
                with self.subTest(native_available=native, max_bulge=bulge):
                    self.assertEqual(
                        auto_engine_candidates(
                            params, None, native_available=native),
                        auto_engine_candidates(
                            params, 20_000_000, native_available=native))

    def test_auto_and_large_indexed_apply_mismatch_only_defaults(self):
        from search.offtarget_backend import apply_engine_defaults

        auto_params = SearchParams(
            max_bulge=1, blastdb="existing_db",
            max_bulge_explicit=False)
        apply_engine_defaults("auto", auto_params)
        self.assertEqual(auto_params.max_bulge, 0)
        # An existing database keeps auto on BLAST; the BLAST+ executables are
        # not installed on every machine that runs this suite, so the
        # availability probe is pinned instead of skipped.
        with mock.patch.object(
                BlastBackend, "available", return_value=(True, "")):
            self.assertEqual(resolve_engine("auto", auto_params), "blast")

        small_auto_params = SearchParams(max_bulge=1)
        apply_engine_defaults(
            "auto", small_auto_params, genome_size=1000000)
        self.assertEqual(small_auto_params.max_bulge, 0)

        indexed_params = SearchParams(
            max_bulge=1, max_bulge_explicit=False)
        apply_engine_defaults(
            "indexed", indexed_params, genome_size=100000000)
        self.assertEqual(indexed_params.max_bulge, 0)

    def test_indexed_backend_applies_large_genome_default_directly(self):
        with tempfile.TemporaryDirectory() as tmp:
            fasta = os.path.join(tmp, "large.fa")
            with open(fasta, "wb") as handle:
                handle.seek(50000000)
                handle.write(b"\0")
            params = SearchParams(
                max_bulge=1, max_bulge_explicit=False,
                output_dir=tmp)
            with mock.patch(
                    "search.genome_index.load_index",
                    side_effect=FileNotFoundError), mock.patch(
                    "search.genome_index.build_index",
                    side_effect=RuntimeError("stop after defaults")):
                with self.assertRaises(RuntimeError):
                    run_backend(
                        "indexed",
                        [{"qid": "g0", "guide_seq": GUIDE}],
                        fasta, params)
            self.assertEqual(params.max_bulge, 0)

    def test_indexed_backend_auto_reduces_k_for_bulge_search(self):
        with tempfile.TemporaryDirectory() as tmp:
            fasta = os.path.join(tmp, "large.fa")
            with open(fasta, "wb") as handle:
                handle.seek(150000000)
                handle.write(b"\0")
            params = SearchParams(
                max_mismatch=4,
                max_bulge=1,
                max_bulge_explicit=True,
                output_dir=tmp,
            )
            backend = get_backend("indexed")
            with mock.patch.object(
                    backend, "_search_python", return_value={}) as search:
                backend.search(
                    [{"qid": "g0", "guide_seq": GUIDE}],
                    fasta,
                    params,
                )
            self.assertEqual(params.extra["k"], 10)
            self.assertEqual(params.extra["k_auto_reduced_from"], 12)
            self.assertEqual(search.call_args.args[4], 10)

    def test_annotation_input_uses_sibling_fasta(self):
        from search.blast_utils import load_genome_and_prepare_fasta

        with tempfile.TemporaryDirectory() as tmp:
            fna = os.path.join(tmp, "GCF_example_genomic.fna")
            gff3 = os.path.join(
                tmp, "GCF_example_genomic_with_utrs.gff3")
            with open(fna, "w", encoding="utf-8") as handle:
                handle.write(">chr1\n%s\n" % (FLANK + GUIDE + "GGG"))
            with open(gff3, "w", encoding="utf-8") as handle:
                handle.write("##gff-version 3\n")
            genome, resolved, temp_file = load_genome_and_prepare_fasta(gff3)
            try:
                self.assertEqual(resolved, fna)
                self.assertIsNone(temp_file)
            finally:
                genome.close()

    def test_exact_backend_unified_hits(self):
        with tempfile.NamedTemporaryFile(
                "w", suffix=".fa", delete=False, encoding="utf-8") as handle:
            _write_genome(handle.name)
            fasta = handle.name
        try:
            params = SearchParams(max_mismatch=1, require_pam=True, pam="NGG")
            matches = run_backend(
                "exact",
                [{"qid": "g0", "guide_seq": GUIDE}],
                fasta, params)
            self.assertIn("g0", matches)
            hit = matches["g0"][0]
            for key in ("qid", "guide", "target", "start", "strand",
                        "mismatch", "indel", "pam", "bitscore", "engine"):
                self.assertIn(key, hit)
            self.assertEqual(hit["engine"], "exact")
            self.assertEqual(hit["target"], "chr1")
            self.assertEqual(hit["mismatch"], 0)

            progress = []
            ExactBackend().search(
                [{"qid": "g0", "guide_seq": GUIDE}],
                fasta, params,
                progress_callback=lambda done, total: progress.append(
                    (done, total)
                ),
            )
            self.assertEqual(progress, [(1, 1)])
        finally:
            os.unlink(fasta)

    def test_single_engine_publishes_its_report_through_params(self):
        params = SearchParams(max_mismatch=1, max_bulge=0)
        backend = mock.Mock()
        backend.last_report = {"engine": "blast", "hits": 1}
        backend.search.return_value = {"g0": []}
        with mock.patch("search.offtarget_backend.get_backend",
                        return_value=backend):
            result = run_backend("blast", [], "genome.fa", params)
        self.assertEqual(result, {"g0": []})
        self.assertIs(params.extra["engine_run_report"], backend.last_report)
        self.assertEqual(params.extra["engine_run_report"]["engine_used"],
                         "blast")

    def test_single_engine_without_a_report_stores_nothing(self):
        params = SearchParams(max_mismatch=1, max_bulge=0)
        backend = mock.Mock(spec=["available", "search"])
        backend.search.return_value = {}
        with mock.patch("search.offtarget_backend.get_backend",
                        return_value=backend):
            run_backend("exact", [], "genome.fa", params)
        self.assertNotIn("engine_run_report", params.extra)

    def test_unknown_engine(self):
        with self.assertRaises(ValueError):
            get_backend("not_an_engine")

    def test_missing_external_tools_report_clear_errors(self):
        for backend in (BlastBackend(),):
            ok, reason = backend.available()
            if ok:
                continue
            self.assertTrue(reason)
            with self.assertRaises(RuntimeError):
                backend.search([{"qid": "g0", "guide_seq": GUIDE}],
                               "genome.fa", SearchParams())

    def test_compare_engines_recall_with_mocked_blast_backend(self):
        with tempfile.NamedTemporaryFile(
                "w", suffix=".fa", delete=False, encoding="utf-8") as handle:
            _write_genome(handle.name)
            fasta = handle.name
        try:
            params = SearchParams(max_mismatch=1, max_bulge=0)
            guides = [{"qid": "g0", "guide_seq": GUIDE}]
            with mock.patch.object(
                    BlastBackend, "search",
                    lambda self, g, f, p, genome=None, **kw:
                    ExactBackend().search(g, f, p, genome=genome)):
                result = compare_engines(
                    guides, fasta, params,
                    engine_names=["exact", "blast"], reference="exact")
            self.assertEqual(result["summary"]["g0"]["exact_recall"], 1.0)
            self.assertEqual(result["summary"]["g0"]["blast_recall"], 1.0)
        finally:
            os.unlink(fasta)

    def test_compare_engines_recall_uses_target_end_in_hit_identity(self):
        guides = [{"qid": "g0", "guide_seq": GUIDE}]
        params = SearchParams(max_mismatch=1, max_bulge=0)

        def fake_run_backend(name, guides_arg, genome_fasta, params_arg,
                             genome=None, **kwargs):
            target_end = 120 if name == "exact" else 121
            return {
                "g0": [{
                    "target": "chr1", "start": 100,
                    "target_end": target_end, "strand": "+",
                }]
            }

        with mock.patch("search.offtarget_backend.run_backend",
                        side_effect=fake_run_backend):
            result = compare_engines(
                guides, "unused.fa", params,
                engine_names=["exact", "blast"], reference="exact")

        self.assertEqual(result["summary"]["g0"]["blast_recall"], 0.0)

    def test_blast_backend_reports_chunk_progress(self):
        guides = [
            {"qid": "g%d" % i, "guide_seq": GUIDE}
            for i in range(25)
        ]
        genome = _fake_genome({"chr1": "A" * 100})
        progress = []
        with mock.patch.object(
                BlastBackend, "available",
                return_value=(True, "")), mock.patch(
                    "search.blast_utils._blastdb_files_exist",
                    return_value=True), mock.patch(
                    "search.blast_utils.blastdb_is_current",
                    return_value=True), mock.patch(
                    "search.blast_utils.prepare_genome_fasta",
                    return_value=("genome.fa", None)):
            with mock.patch(
                    "search.blast_utils.run_blastn",
                    return_value={}) as run_blastn:
                BlastBackend().search(
                    guides, "genome.fa",
                    SearchParams(blastdb="db", max_bulge=0),
                    genome=genome,
                    progress_callback=lambda done, total: progress.append(
                        (done, total)
                    ),
                )
        self.assertEqual(run_blastn.call_count, 3)
        self.assertIs(run_blastn.call_args.kwargs["genome"], genome)
        self.assertEqual(progress, [(10, 25), (20, 25), (25, 25)])

    def test_blast_backend_lazy_loads_effective_reference(self):
        genome = _fake_genome({"chr1": "A" * 100})
        genome.close = mock.Mock()
        params = SearchParams(blastdb="db", max_bulge=0)
        with mock.patch.object(
                BlastBackend, "available", return_value=(True, "")), \
                mock.patch(
                    "search.blast_utils.load_genome_and_prepare_fasta",
                    return_value=(genome, "prepared.fa", None)) as loader, \
                mock.patch(
                    "search.blast_utils._blastdb_files_exist",
                    return_value=True), mock.patch(
                    "search.blast_utils.blastdb_is_current",
                    return_value=True) as is_current, mock.patch(
                    "search.blast_utils.run_blastn",
                    return_value={}) as run_blastn:
            BlastBackend().search(
                [{"qid": "g0", "guide_seq": GUIDE}],
                "source.fa.gz", params)
        loader.assert_called_once_with("source.fa.gz")
        is_current.assert_called_once_with("prepared.fa", "db")
        self.assertIs(run_blastn.call_args.kwargs["genome"], genome)
        genome.close.assert_called_once_with()

    def test_blast_backend_does_not_close_caller_reference(self):
        genome = _fake_genome({"chr1": "A" * 100})
        genome.close = mock.Mock()
        params = SearchParams(blastdb="db", max_bulge=0)
        with mock.patch.object(
                BlastBackend, "available", return_value=(True, "")), \
                mock.patch(
                    "search.blast_utils.prepare_genome_fasta",
                    return_value=("prepared.fa", None)), mock.patch(
                    "search.blast_utils._blastdb_files_exist",
                    return_value=True), mock.patch(
                    "search.blast_utils.blastdb_is_current",
                    return_value=True), mock.patch(
                    "search.blast_utils.run_blastn",
                    return_value={}):
            BlastBackend().search(
                [{"qid": "g0", "guide_seq": GUIDE}],
                "source.fa.gz", params, genome=genome)
        genome.close.assert_not_called()

    def test_blast_backend_missing_reference_fails_explicitly(self):
        with mock.patch.object(
                BlastBackend, "available", return_value=(True, "")), \
                mock.patch(
                    "search.blast_utils.load_genome_and_prepare_fasta",
                    side_effect=SystemExit(6)):
            with self.assertRaisesRegex(
                    RuntimeError, "readable reference FASTA/genome"):
                BlastBackend().search(
                    [{"qid": "g0", "guide_seq": GUIDE}],
                    "missing.fa", SearchParams(max_bulge=0))


class GGGGenomeTests(unittest.TestCase):
    def test_parse_tsv(self):
        text = (
            "# name\tstrand\tstart\tend\tsnippet\tsnippet_pos\t"
            "snippet_end\tquery\tsbjct\talign\tedit\tmatch\tmis\tdel\tins\n"
            "chr1\t+\t101\t120\tACGT\t1\t20\t%s\t%s\t"
            "||||||||||||||||||||\t=======================\t20\t0\t0\t0\n"
            % (GUIDE, GUIDE)
        )
        hits = GGGenomeBackend()._parse_tsv(text, SearchParams(max_mismatch=2))
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["target"], "chr1")
        self.assertEqual(hits[0]["start"], 100)
        self.assertEqual(hits[0]["strand"], "+")
        self.assertEqual(hits[0]["engine"], "gggenome")

    def test_search_uses_api(self):
        text = (
            "# name\tstrand\tstart\tend\tsnippet\tsnippet_pos\t"
            "snippet_end\tquery\tsbjct\talign\tedit\tmatch\tmis\tdel\tins\n"
            "chr1\t+\t101\t120\tACGT\t1\t20\t%s\t%s\t"
            "||||||||||||||||||||\t=======================\t20\t0\t0\t0\n"
            % (GUIDE, GUIDE)
        )
        response = mock.Mock()
        response.read.return_value = text.encode("utf-8")
        response.__enter__ = mock.Mock(return_value=response)
        response.__exit__ = mock.Mock(return_value=False)
        with mock.patch("urllib.request.urlopen", return_value=response) as patch:
            backend = GGGenomeBackend()
            matches = backend.search(
                [{"qid": "g0", "guide_seq": GUIDE}],
                "unused.fa", SearchParams(max_mismatch=1, genome_build="hg38"))
        self.assertIn("g0", matches)
        self.assertEqual(matches["g0"][0]["start"], 100)
        self.assertIn("gggenome.dbcls.jp/hg38/",
                      patch.call_args[0][0].full_url)

    def test_search_prepends_pam_for_5prime(self):
        response = mock.Mock()
        response.read.return_value = b""
        response.__enter__ = mock.Mock(return_value=response)
        response.__exit__ = mock.Mock(return_value=False)
        params = SearchParams(
            max_mismatch=0, max_bulge=0, require_pam=True,
            pam="NGG", pam_side="5prime", genome_build="hg38")
        with mock.patch(
                "urllib.request.urlopen", return_value=response) as patch:
            GGGenomeBackend().search(
                [{"qid": "g0", "guide_seq": GUIDE}],
                "unused.fa", params)
        url = patch.call_args[0][0].full_url
        path = urllib.parse.urlparse(url).path
        self.assertIn("NGG" + GUIDE, urllib.parse.unquote(path))

    def test_filters_mismatch_separately_from_indel_budget(self):
        text = (
            "# name\tstrand\tstart\tend\tsnippet\tsnippet_pos\t"
            "snippet_end\tquery\tsbjct\talign\tedit\tmatch\tmis\tdel\tins\n"
            "chr1\t+\t101\t120\tACGT\t1\t20\t%s\t%s\t"
            "||||||||||||||||||||\t=======================\t20\t1\t0\t0\n"
            % (GUIDE, GUIDE)
        )
        hits = GGGenomeBackend()._parse_tsv(
            text, SearchParams(max_mismatch=0, max_bulge=1))
        self.assertEqual(hits, [])


class BlastThreadTests(unittest.TestCase):
    def test_blastn_command_uses_threads(self):
        from search.blast_utils import run_blastn

        with tempfile.NamedTemporaryFile(
                "w", suffix=".fa", delete=False, encoding="utf-8") as handle:
            handle.write(">g0\n%s\n" % GUIDE)
            query_fasta = handle.name

        class FakeStream:
            def __iter__(self):
                return iter(())

            def read(self):
                return ""

        proc = mock.Mock()
        proc.returncode = 0
        proc.stdout = FakeStream()
        proc.stderr = FakeStream()
        genome = _fake_genome({"chr1": "A" * 100})

        def fake_popen(cmd, **kwargs):
            out_path = cmd[cmd.index("-out") + 1]
            with open(out_path, "w", encoding="utf-8"):
                pass
            return proc

        try:
            with mock.patch(
                    "subprocess.Popen", side_effect=fake_popen) as popen:
                run_blastn(query_fasta, "test_db", num_threads=8,
                           genome=genome)
            cmd = popen.call_args[0][0]
            self.assertIn("-num_threads", cmd)
            self.assertEqual(cmd[cmd.index("-num_threads") + 1], "8")
            self.assertNotIn("-perc_identity", cmd)
            self.assertIn("-ungapped", cmd)
            self.assertIn("qseq sseq", cmd[cmd.index("-outfmt") + 1])
        finally:
            os.unlink(query_fasta)

    def test_blastn_gapped_mode_and_alignment_parsing(self):
        from search.blast_utils import reverse_complement, run_blastn

        with tempfile.NamedTemporaryFile(
                "w", suffix=".fa", delete=False, encoding="utf-8") as handle:
            handle.write(">g0\n%s\n" % GUIDE)
            query_fasta = handle.name

        target_plus = GUIDE[:10] + "T" + GUIDE[10:]
        target_minus = reverse_complement(target_plus)
        sequence = list("A" * 320)
        sequence[100:121] = list(target_plus)
        sequence[200:221] = list(target_minus)
        genome = _fake_genome({"chr1": "".join(sequence)})

        def fake_popen(cmd, **kwargs):
            out_path = cmd[cmd.index("-out") + 1]
            with open(out_path, "w", encoding="utf-8") as blast_out:
                for sstart, send in ((101, 121), (221, 201)):
                    blast_out.write(
                        "g0\tchr1\t95.238\t21\t0\t1\t1\t20\t"
                        "%d\t%d\t0.001\t30\t"
                        "%s\t%s\n"
                        % (sstart, send, GUIDE, target_plus)
                    )
            proc = mock.Mock()
            proc.returncode = 0
            return proc

        try:
            with mock.patch(
                    "subprocess.Popen", side_effect=fake_popen) as popen:
                matches = run_blastn(
                    query_fasta, "test_db", num_threads=2,
                    max_mismatch=0, max_bulge=1, genome=genome)
            cmd = popen.call_args[0][0]
            self.assertNotIn("-ungapped", cmd)
            self.assertEqual(len(matches["g0"]), 2)
            expected_starts = {"+": 100, "-": 200}
            for hit in matches["g0"]:
                self.assertEqual(hit["mismatch"], 0)
                self.assertEqual(hit["indel"], 1)
                self.assertEqual(hit["rna_bulges"], 0)
                self.assertEqual(hit["dna_bulges"], 1)
                self.assertEqual(hit["cigar"], "10M1D10M")
                expected_start = expected_starts[hit["strand"]]
                self.assertEqual(hit["target_start"], expected_start)
                self.assertEqual(hit["target_end"], expected_start + 21)
                self.assertEqual(hit["query_start"], 0)
                self.assertEqual(hit["query_end"], len(GUIDE))
                self.assertEqual(
                    hit["aligned_guide"].replace("-", ""), GUIDE)
                self.assertEqual(hit["aligned_target"], target_plus)
                self.assertEqual(set(hit["hsp"]), {
                    "pident", "length", "mismatch", "gapopen",
                    "qstart", "qend", "sstart", "send", "evalue",
                    "bitscore", "query_aligned", "target_aligned",
                })
        finally:
            os.unlink(query_fasta)

    def test_pam_rebuilt_rejects_gaps_inside_the_pam_span(self):
        from search.blast_utils import _pam_ok_rebuilt

        self.assertFalse(_pam_ok_rebuilt(
            "TT-GAT", "TTTGAT", (0, 5), "TTGAT"))
        self.assertFalse(_pam_ok_rebuilt(
            "TTGAT", "TT-AT", (0, 5), "TTGAT"))
        self.assertTrue(_pam_ok_rebuilt(
            "TTGAT", "TTGAT", (0, 5), "TTGAT"))
        self.assertTrue(_pam_ok_rebuilt(
            "TTGAT-C", "TTGATCC", (0, 5), "TTGAT"))

    def test_blastn_rebuilds_trimmed_hsp_using_the_full_query(self):
        from search.blast_utils import run_blastn

        with tempfile.NamedTemporaryFile(
                "w", suffix=".fa", delete=False, encoding="utf-8") as handle:
            handle.write(">g0\n%s\n" % GUIDE)
            query_fasta = handle.name

        def fake_popen(cmd, **kwargs):
            out_path = cmd[cmd.index("-out") + 1]
            with open(out_path, "w", encoding="utf-8") as blast_out:
                # A 16/20 nt local HSP: blastn trimmed the last four query
                # bases, which are unaligned rather than matched.
                blast_out.write(
                    "g0\tchr1\t100.0\t16\t0\t0\t1\t16\t"
                    "101\t116\t0.001\t30\n"
                )
                blast_out.write(
                    "g0\tchr1\t100.0\t20\t0\t0\t1\t20\t"
                    "1\t20\t0.001\t40\n"
                )
            proc = mock.Mock()
            proc.returncode = 0
            return proc

        mutated = list(GUIDE)
        mutated[16:] = list("AAAA")
        sequence = list("A" * 220)
        sequence[0:20] = list(GUIDE)
        sequence[100:120] = mutated
        genome = _fake_genome({"chr1": "".join(sequence)})
        try:
            with mock.patch(
                    "subprocess.Popen", side_effect=fake_popen):
                matches = run_blastn(
                    query_fasta, "test_db", num_threads=2, max_mismatch=4,
                    genome=genome)
            by_start = {hit["start"]: hit for hit in matches["g0"]}
            self.assertEqual(sorted(by_start), [0, 100])
            self.assertEqual(by_start[0]["mismatch"], 0)
            self.assertEqual(by_start[100]["mismatch"], 4)
            self.assertEqual(by_start[100]["target_start"], 100)
            self.assertEqual(by_start[100]["target_end"], 120)
            self.assertEqual(by_start[100]["cigar"], "16M4X")
            self.assertEqual(by_start[100]["aligned_guide"], GUIDE)
            self.assertEqual(by_start[100]["hsp"]["qend"], 16)

            with mock.patch(
                    "subprocess.Popen", side_effect=fake_popen):
                strict = run_blastn(
                    query_fasta, "test_db", num_threads=2, max_mismatch=3,
                    genome=genome)
            self.assertEqual(len(strict["g0"]), 1)
            self.assertEqual(strict["g0"][0]["start"], 0)
        finally:
            os.unlink(query_fasta)

    def test_blastn_requires_a_reference_for_realignment(self):
        from search.blast_utils import run_blastn

        with self.assertRaisesRegex(
                RuntimeError, "requires a reference FASTA/genome"):
            run_blastn("query.fa", "test_db")

    def test_blastn_repeat_interval_filters_hit_at_rebuilt_start(self):
        from pyfaidx import Fasta
        from search.blast_utils import run_blastn

        with tempfile.NamedTemporaryFile(
                "w", suffix=".fa", delete=False, encoding="utf-8") as query:
            query.write(">g0\n%s\n" % GUIDE)
            query_fasta = query.name
        with tempfile.NamedTemporaryFile(
                "w", suffix=".fa", delete=False, encoding="utf-8") as genome_file:
            genome_file.write(
                ">chr1\n%s%s%s\n" % ("A" * 100, GUIDE, "A" * 100))
            genome_path = genome_file.name

        def fake_popen(cmd, **kwargs):
            out_path = cmd[cmd.index("-out") + 1]
            with open(out_path, "w", encoding="utf-8") as blast_out:
                blast_out.write(
                    "g0\tchr1\t100.0\t20\t0\t0\t1\t20\t"
                    "101\t120\t0.0\t40\n")
            proc = mock.Mock()
            proc.returncode = 0
            return proc

        genome = Fasta(genome_path)
        try:
            with mock.patch(
                    "subprocess.Popen", side_effect=fake_popen):
                hits = run_blastn(
                    query_fasta, "test_db", max_mismatch=0, max_bulge=0,
                    genome=genome,
                    repeat_intervals={"chr1": [(100, 120)]})
            self.assertEqual(hits.get("g0", []), [])
        finally:
            genome.close()
            os.unlink(query_fasta)
            os.unlink(genome_path)

    def test_blastn_repeat_interval_outside_rebuilt_start_is_retained(self):
        from pyfaidx import Fasta
        from search.blast_utils import run_blastn

        with tempfile.NamedTemporaryFile(
                "w", suffix=".fa", delete=False, encoding="utf-8") as query:
            query.write(">g0\n%s\n" % GUIDE)
            query_fasta = query.name
        with tempfile.NamedTemporaryFile(
                "w", suffix=".fa", delete=False, encoding="utf-8") as genome_file:
            genome_file.write(
                ">chr1\n%s%s%s\n" % ("A" * 100, GUIDE, "A" * 100))
            genome_path = genome_file.name

        def fake_popen(cmd, **kwargs):
            out_path = cmd[cmd.index("-out") + 1]
            with open(out_path, "w", encoding="utf-8") as blast_out:
                blast_out.write(
                    "g0\tchr1\t100.0\t20\t0\t0\t1\t20\t"
                    "101\t120\t0.0\t40\n")
            proc = mock.Mock()
            proc.returncode = 0
            return proc

        genome = Fasta(genome_path)
        try:
            with mock.patch(
                    "subprocess.Popen", side_effect=fake_popen):
                hits = run_blastn(
                    query_fasta, "test_db", max_mismatch=0, max_bulge=0,
                    genome=genome,
                    repeat_intervals={"chr1": [(90, 100)]})
            self.assertEqual(
                [hit["start"] for hit in hits["g0"]], [100])
        finally:
            genome.close()
            os.unlink(query_fasta)
            os.unlink(genome_path)

    def test_blastn_seed_uses_the_rebuilt_pam_proximal_interval(self):
        from search.blast_utils import run_blastn

        first_mutated = list(GUIDE)
        first_mutated[0] = "A" if first_mutated[0] != "A" else "C"
        last_mutated = list(GUIDE)
        last_mutated[-1] = "A" if last_mutated[-1] != "A" else "C"
        sequence = list("C" * 260)
        sequence[100:120] = first_mutated
        sequence[200:220] = last_mutated
        genome = _fake_genome({"chr1": "".join(sequence)})

        with tempfile.NamedTemporaryFile(
                "w", suffix=".fa", delete=False, encoding="utf-8") as handle:
            handle.write(">g0\n%s\n" % GUIDE)
            query_fasta = handle.name

        def fake_popen(cmd, **kwargs):
            out_path = cmd[cmd.index("-out") + 1]
            with open(out_path, "w", encoding="utf-8") as blast_out:
                blast_out.write(
                    "g0\tchr1\t95.0\t20\t1\t0\t1\t20\t"
                    "101\t120\t0.0\t30\n")
                blast_out.write(
                    "g0\tchr1\t95.0\t20\t1\t0\t1\t20\t"
                    "201\t220\t0.0\t30\n")
            proc = mock.Mock()
            proc.returncode = 0
            return proc

        try:
            with mock.patch(
                    "subprocess.Popen", side_effect=fake_popen):
                three_prime = run_blastn(
                    query_fasta, "test_db", max_mismatch=1,
                    max_bulge=0, genome=genome,
                    seed_mismatch_max=0, seed_len=5, pam_side="3prime")
            self.assertEqual(
                [hit["start"] for hit in three_prime["g0"]], [100])

            with mock.patch(
                    "subprocess.Popen", side_effect=fake_popen):
                five_prime = run_blastn(
                    query_fasta, "test_db", max_mismatch=1,
                    max_bulge=0, genome=genome,
                    seed_mismatch_max=0, seed_len=5, pam_side="5prime")
            self.assertEqual(
                [hit["start"] for hit in five_prime["g0"]], [200])
        finally:
            os.unlink(query_fasta)

    def test_seed_gap_budget_uses_query_positions(self):
        from search.blast_utils import (
            _count_seed_mismatches_aligned, _seed_interval,
        )

        self.assertEqual(
            _count_seed_mismatches_aligned("ACGT", "AC-T", 2, 2), 1)
        self.assertEqual(
            _count_seed_mismatches_aligned("AC-GT", "ACTGA", 2, 2), 1)
        self.assertEqual(
            _seed_interval(25, 5, "3prime", ((0, 5), "TTGAT")),
            (5, 10))

    def test_blastn_pam_toggle_keeps_embedded_seed_interval(self):
        from search.blast_utils import _seed_interval, run_blastn

        window = "TTGAT" + GUIDE
        sequence = list("C" * 200)
        sequence[100:125] = list(window)
        genome = _fake_genome({"chr1": "".join(sequence)})

        with tempfile.NamedTemporaryFile(
                "w", suffix=".fa", delete=False, encoding="utf-8") as handle:
            handle.write(">g0\n%s\n" % window)
            query_fasta = handle.name

        def fake_popen(cmd, **kwargs):
            out_path = cmd[cmd.index("-out") + 1]
            with open(out_path, "w", encoding="utf-8") as blast_out:
                blast_out.write(
                    "g0\tchr1\t100.0\t25\t0\t0\t1\t25\t"
                    "101\t125\t0.0\t40\n")
            proc = mock.Mock()
            proc.returncode = 0
            return proc

        try:
            with mock.patch(
                    "subprocess.Popen", side_effect=fake_popen), mock.patch(
                    "search.blast_utils._seed_interval",
                    wraps=_seed_interval) as seed_interval:
                for require_pam in (False, True):
                    hits = run_blastn(
                        query_fasta, "test_db", max_mismatch=0,
                        max_bulge=0, genome=genome,
                        require_pam=require_pam, pam_motif="TTGAT",
                        pam_side="5prime", window_motif="TTGAT",
                        window_side="downstream", seed_mismatch_max=0,
                        seed_len=5)
                    self.assertEqual(
                        [hit["start"] for hit in hits["g0"]], [100])

            self.assertEqual(seed_interval.call_args_list, [
                mock.call(25, 5, "5prime", ((0, 5), "TTGAT")),
                mock.call(25, 5, "5prime", ((0, 5), "TTGAT")),
            ])
        finally:
            os.unlink(query_fasta)

    def test_blastn_rejects_dna_gap_inside_embedded_pam(self):
        from search.blast_utils import run_blastn

        window = "TTGAT" + GUIDE
        sequence = list("C" * 200)
        sequence[100:126] = list("TTTGAT" + GUIDE)
        genome = _fake_genome({"chr1": "".join(sequence)})

        with tempfile.NamedTemporaryFile(
                "w", suffix=".fa", delete=False, encoding="utf-8") as handle:
            handle.write(">g0\n%s\n" % window)
            query_fasta = handle.name

        def fake_popen(cmd, **kwargs):
            out_path = cmd[cmd.index("-out") + 1]
            with open(out_path, "w", encoding="utf-8") as blast_out:
                blast_out.write(
                    "g0\tchr1\t96.0\t25\t0\t1\t1\t25\t"
                    "101\t126\t0.0\t38\n")
            proc = mock.Mock()
            proc.returncode = 0
            return proc

        try:
            with mock.patch(
                    "subprocess.Popen", side_effect=fake_popen):
                hits = run_blastn(
                    query_fasta, "test_db", max_mismatch=0,
                    max_bulge=1, genome=genome, require_pam=True,
                    pam_motif="TTGAT", pam_side="5prime",
                    window_motif="TTGAT", window_side="downstream")
            spans = {
                (hit["target_start"], hit["target_end"])
                for hit in hits.get("g0", [])
            }
            self.assertNotIn((100, 126), spans)
        finally:
            os.unlink(query_fasta)

    def test_blastn_rebuilds_multiple_bulges_and_terminal_gaps(self):
        from search.blast_utils import run_blastn

        probe = "ACGTCAGTGCATGACTAGCT"
        multi_bulge = probe[:4] + "G" + probe[4:14] + "G" + probe[14:]
        five_prime_gap = probe[1:]
        three_prime_gap = probe[:-1]
        sequence = list("C" * 450)
        sequence[100:122] = list(multi_bulge)
        sequence[300:319] = list(five_prime_gap)
        sequence[400:419] = list(three_prime_gap)
        genome = _fake_genome({"chr1": "".join(sequence)})

        with tempfile.NamedTemporaryFile(
                "w", suffix=".fa", delete=False, encoding="utf-8") as handle:
            handle.write(">g0\n%s\n" % probe)
            query_fasta = handle.name

        def fake_popen(cmd, **kwargs):
            out_path = cmd[cmd.index("-out") + 1]
            with open(out_path, "w", encoding="utf-8") as blast_out:
                blast_out.write(
                    "g0\tchr1\t90.0\t22\t0\t2\t1\t20\t"
                    "101\t122\t0.0\t30\n")
                blast_out.write(
                    "g0\tchr1\t100.0\t19\t0\t0\t2\t20\t"
                    "301\t319\t0.0\t28\n")
                blast_out.write(
                    "g0\tchr1\t100.0\t19\t0\t0\t1\t19\t"
                    "401\t419\t0.0\t28\n")
            proc = mock.Mock()
            proc.returncode = 0
            return proc

        try:
            with mock.patch(
                    "subprocess.Popen", side_effect=fake_popen):
                matches = run_blastn(
                    query_fasta, "test_db", max_mismatch=0,
                    max_bulge=2, genome=genome)
            by_span = {
                (hit["target_start"], hit["target_end"]): hit
                for hit in matches["g0"]
            }
            canonical = {(100, 122), (300, 319), (400, 419)}
            self.assertTrue(canonical.issubset(by_span))
            self.assertGreaterEqual(len(by_span), 3)
            self.assertEqual(by_span[(100, 122)]["indel"], 2)
            self.assertEqual(by_span[(300, 319)]["indel"], 1)
            self.assertEqual(by_span[(300, 319)]["rna_bulges"], 1)
            self.assertTrue(
                by_span[(300, 319)]["aligned_target"].startswith("-"))
            self.assertEqual(by_span[(400, 419)]["indel"], 1)
            self.assertEqual(by_span[(400, 419)]["rna_bulges"], 1)
            self.assertTrue(
                by_span[(400, 419)]["aligned_target"].endswith("-"))
            for hit in matches["g0"]:
                self.assertEqual(hit["query_start"], 0)
                self.assertEqual(hit["query_end"], len(probe))
                self.assertEqual(
                    hit["aligned_guide"].replace("-", ""), probe)
        finally:
            os.unlink(query_fasta)

    def test_blastn_checks_a_pam_that_is_inside_the_query_window(self):
        from search.blast_utils import reverse_complement, run_blastn

        window = "TTGAT" + GUIDE
        with tempfile.NamedTemporaryFile(
                "w", suffix=".fa", delete=False, encoding="utf-8") as handle:
            handle.write(">g0\n%s\n" % window)
            query_fasta = handle.name

        def fake_popen(cmd, **kwargs):
            out_path = cmd[cmd.index("-out") + 1]
            with open(out_path, "w", encoding="utf-8") as blast_out:
                # plus strand with a valid PAM
                blast_out.write(
                    "g0\tchr1\t100.0\t25\t0\t0\t1\t25\t"
                    "101\t125\t0.0\t40\n")
                # plus strand with a mutated PAM
                blast_out.write(
                    "g0\tchr1\t96.0\t25\t1\t0\t1\t25\t"
                    "201\t225\t0.0\t38\n")
                # minus strand: the plus strand has to read the rc PAM
                blast_out.write(
                    "g0\tchr1\t100.0\t25\t0\t0\t1\t25\t"
                    "500\t476\t0.0\t40\n")
                # blastn trimmed the PAM end away
                blast_out.write(
                    "g0\tchr1\t95.0\t23\t1\t0\t3\t25\t"
                    "303\t325\t0.0\t36\n")
            proc = mock.Mock()
            proc.returncode = 0
            return proc

        sequence = list("C" * 600)
        sequence[100:125] = list(window)
        sequence[200:225] = list("TTGAC" + GUIDE)
        sequence[300:325] = list(window)
        sequence[475:500] = list(reverse_complement(window))
        genome = _fake_genome({"chr1": "".join(sequence)})
        try:
            with mock.patch(
                    "subprocess.Popen", side_effect=fake_popen):
                matches = run_blastn(
                    query_fasta, "test_db", max_mismatch=4, require_pam=True,
                    pam_motif="TTGAT", pam_side="5prime", genome=genome,
                    window_motif="TTGAT", window_side="downstream")
            self.assertEqual(
                sorted(hit["start"] for hit in matches["g0"]),
                [100, 300, 475])

            # Without the window context the legacy outside-the-window check
            # runs instead, and the same hits are all rejected.
            with mock.patch(
                    "subprocess.Popen", side_effect=fake_popen):
                legacy = run_blastn(
                    query_fasta, "test_db", max_mismatch=4, require_pam=True,
                    pam_motif="TTGAT", pam_side="5prime", genome=genome)
            self.assertEqual(legacy.get("g0", []), [])
        finally:
            os.unlink(query_fasta)


class PythonFallbackApprovalTests(unittest.TestCase):
    """The pure-Python degrade must never happen without an approval."""

    def test_policy_defaults_to_allow(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(PYTHON_FALLBACK_ENV, None)
            self.assertEqual(
                resolve_python_fallback_policy(SearchParams()), "allow")

    def test_explicit_param_wins_over_environment(self):
        params = SearchParams(extra={"python_fallback": "deny"})
        with mock.patch.dict(os.environ, {PYTHON_FALLBACK_ENV: "allow"}):
            self.assertEqual(resolve_python_fallback_policy(params), "deny")

    def test_environment_sets_the_policy(self):
        with mock.patch.dict(os.environ, {PYTHON_FALLBACK_ENV: "ask"}):
            self.assertEqual(
                resolve_python_fallback_policy(SearchParams()), "ask")

    def test_unknown_policy_falls_back_to_allow(self):
        params = SearchParams(extra={"python_fallback": "nonsense"})
        self.assertEqual(resolve_python_fallback_policy(params), "allow")

    def test_allow_and_deny_policies(self):
        log_lines = []
        allow = SearchParams(extra={"python_fallback": "allow"})
        self.assertTrue(approve_python_fallback(
            allow, "no binary", log=log_lines.append))
        deny = SearchParams(extra={"python_fallback": "deny"})
        self.assertFalse(approve_python_fallback(
            deny, "no binary", log=log_lines.append))
        joined = "\n".join(log_lines)
        self.assertIn("python fallback reason: no binary", joined)
        self.assertIn("refused by policy", joined)

    def test_ask_policy_uses_the_registered_callback(self):
        seen = []

        def confirm(reason):
            seen.append(reason)
            return True

        params = SearchParams(extra={
            "python_fallback": "ask", "python_fallback_confirm": confirm})
        self.assertTrue(approve_python_fallback(params, "no native engine"))
        self.assertEqual(seen, ["no native engine"])

    def test_ask_policy_without_callback_uses_stdin_protocol(self):
        params = SearchParams(extra={"python_fallback": "ask"})
        with mock.patch(
                "search.offtarget_backend.ask_python_fallback_on_stdin",
                return_value=False) as prompt:
            self.assertFalse(approve_python_fallback(params, "no binary"))
        prompt.assert_called_once_with("no binary")

    def test_stdin_protocol_emits_marker_and_honours_the_answer(self):
        with mock.patch("builtins.print") as printer, \
                mock.patch("builtins.input", return_value="yes"):
            self.assertTrue(ask_python_fallback_on_stdin("no\nbinary"))
        printed = [call.args[0] for call in printer.call_args_list]
        self.assertIn("CONFIRM_REQUIRED: python_fallback|no binary", printed)

    def test_stdin_protocol_defaults_to_refusal(self):
        with mock.patch("builtins.print"), \
                mock.patch("builtins.input", side_effect=EOFError):
            self.assertFalse(ask_python_fallback_on_stdin("no binary"))

    def test_indexed_search_refuses_a_declined_python_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            fasta = os.path.join(tmp, "large.fa")
            with open(fasta, "wb") as handle:
                handle.seek(150000000)
                handle.write(b"\0")
            params = SearchParams(
                max_mismatch=4, max_bulge=1, max_bulge_explicit=True,
                output_dir=tmp, extra={"python_fallback": "deny"})
            backend = get_backend("indexed")
            with mock.patch(
                    "search.native_offtarget.native_enabled",
                    return_value=True), mock.patch(
                        "search.native_offtarget.probe_binary",
                        return_value=(False, "offtarget-engine is missing")), \
                    mock.patch.object(
                        backend, "_search_python",
                        side_effect=AssertionError("must not run")):
                with self.assertRaises(PythonFallbackDeclined) as caught:
                    backend.search(
                        [{"qid": "g0", "guide_seq": GUIDE}], fasta, params)
            self.assertIn("offtarget-engine is missing", str(caught.exception))
            self.assertEqual(
                backend.last_report["native_fallback_reason"],
                "offtarget-engine is missing")

    def test_indexed_search_runs_python_when_approved(self):
        with tempfile.TemporaryDirectory() as tmp:
            fasta = os.path.join(tmp, "large.fa")
            with open(fasta, "wb") as handle:
                handle.seek(150000000)
                handle.write(b"\0")
            params = SearchParams(
                max_mismatch=4, max_bulge=1, max_bulge_explicit=True,
                output_dir=tmp, extra={"python_fallback": "allow"})
            backend = get_backend("indexed")
            with mock.patch(
                    "search.native_offtarget.native_enabled",
                    return_value=True), mock.patch(
                        "search.native_offtarget.probe_binary",
                        return_value=(False, "offtarget-engine is missing")), \
                    mock.patch.object(
                        backend, "_search_python",
                        return_value={"g0": []}) as search:
                result = backend.search(
                    [{"qid": "g0", "guide_seq": GUIDE}], fasta, params)
            self.assertEqual(result, {"g0": []})
            search.assert_called_once()
            self.assertEqual(
                backend.last_report["native_fallback_reason"],
                "offtarget-engine is missing")


if __name__ == "__main__":
    unittest.main()
