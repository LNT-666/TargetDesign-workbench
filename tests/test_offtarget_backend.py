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

    def test_compare_engines_recall(self):
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

    def test_blast_backend_reports_chunk_progress(self):
        guides = [
            {"qid": "g%d" % i, "guide_seq": GUIDE}
            for i in range(25)
        ]
        progress = []
        with mock.patch.object(
                BlastBackend, "available",
                return_value=(True, "")), mock.patch(
                    "search.blast_utils._blastdb_files_exist",
                    return_value=True), mock.patch(
                    "search.blast_utils.blastdb_is_current",
                    return_value=True):
            with mock.patch(
                    "search.blast_utils.run_blastn",
                    return_value={}) as run_blastn:
                BlastBackend().search(
                    guides, "genome.fa",
                    SearchParams(blastdb="db", max_bulge=0),
                    progress_callback=lambda done, total: progress.append(
                        (done, total)
                    ),
                )
        self.assertEqual(run_blastn.call_count, 3)
        self.assertEqual(progress, [(10, 25), (20, 25), (25, 25)])


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

        def fake_popen(cmd, **kwargs):
            out_path = cmd[cmd.index("-out") + 1]
            with open(out_path, "w", encoding="utf-8"):
                pass
            return proc

        try:
            with mock.patch(
                    "subprocess.Popen", side_effect=fake_popen) as popen:
                run_blastn(query_fasta, "test_db", num_threads=8,
                           perc_identity=80.0)
            cmd = popen.call_args[0][0]
            self.assertIn("-num_threads", cmd)
            self.assertEqual(cmd[cmd.index("-num_threads") + 1], "8")
            self.assertIn("-perc_identity", cmd)
            self.assertEqual(cmd[cmd.index("-perc_identity") + 1], "80.0000")
            self.assertIn("-ungapped", cmd)
            self.assertIn("qseq sseq", cmd[cmd.index("-outfmt") + 1])
        finally:
            os.unlink(query_fasta)

    def test_blastn_gapped_mode_and_alignment_parsing(self):
        from search.blast_utils import run_blastn

        with tempfile.NamedTemporaryFile(
                "w", suffix=".fa", delete=False, encoding="utf-8") as handle:
            handle.write(">g0\n%s\n" % GUIDE)
            query_fasta = handle.name

        def fake_popen(cmd, **kwargs):
            out_path = cmd[cmd.index("-out") + 1]
            with open(out_path, "w", encoding="utf-8") as blast_out:
                for sstart, send in ((101, 121), (121, 101)):
                    blast_out.write(
                        "g0\tchr1\t95.238\t21\t0\t1\t1\t20\t"
                        "%d\t%d\t0.001\t30\t"
                        "ACGTTGCAAG-TCCTAGGATC\t"
                        "ACGTTGCAAGTTCCTAGGATC\n"
                        % (sstart, send)
                    )
            proc = mock.Mock()
            proc.returncode = 0
            return proc

        try:
            with mock.patch(
                    "subprocess.Popen", side_effect=fake_popen) as popen:
                matches = run_blastn(
                    query_fasta, "test_db", num_threads=2,
                    max_mismatch=0, max_bulge=1)
            cmd = popen.call_args[0][0]
            self.assertNotIn("-ungapped", cmd)
            self.assertEqual(len(matches["g0"]), 2)
            for hit in matches["g0"]:
                self.assertEqual(hit["mismatch"], 0)
                self.assertEqual(hit["indel"], 1)
                self.assertEqual(hit["rna_bulges"], 0)
                self.assertEqual(hit["dna_bulges"], 1)
                self.assertEqual(hit["cigar"], "10M1D10M")
                self.assertEqual(hit["target_start"], 100)
                self.assertEqual(hit["target_end"], 121)
        finally:
            os.unlink(query_fasta)

    def test_blastn_rejects_partial_query_hits(self):
        from search.blast_utils import run_blastn

        with tempfile.NamedTemporaryFile(
                "w", suffix=".fa", delete=False, encoding="utf-8") as handle:
            handle.write(">g0\n%s\n" % GUIDE)
            query_fasta = handle.name

        def fake_popen(cmd, **kwargs):
            out_path = cmd[cmd.index("-out") + 1]
            with open(out_path, "w", encoding="utf-8") as blast_out:
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

        try:
            with mock.patch(
                    "subprocess.Popen", side_effect=fake_popen):
                matches = run_blastn(
                    query_fasta, "test_db", num_threads=2)
            self.assertEqual(len(matches["g0"]), 1)
            self.assertEqual(matches["g0"][0]["mismatch"], 0)
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
