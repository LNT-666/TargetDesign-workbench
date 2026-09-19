#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the FASTA input mode of the library pipeline."""

import csv
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHARED = os.path.join(ROOT, "shared")
sys.path.insert(0, SHARED)

from design.library_preflight import ENGINE_CHOICES  # noqa: E402


GUIDE = "GAACACAAAGCATAGACTGC"


class LibraryFastaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.genome = os.path.join(self.tmp.name, "genome.fa")
        self.fasta = os.path.join(self.tmp.name, "targets.fa")
        self.outdir = os.path.join(self.tmp.name, "out")
        with open(self.genome, "w", encoding="utf-8") as handle:
            handle.write(">chr1\n")
            handle.write("A" * 50 + GUIDE + "GGG" + "T" * 50 + "\n")
        with open(self.fasta, "w", encoding="utf-8") as handle:
            handle.write(">tx1\n")
            handle.write("C" * 30 + GUIDE + "AGG" + "G" * 30 + "\n")
            handle.write(">tx2\n")
            handle.write("T" * 20 + GUIDE + "TGG" + "A" * 20 + "\n")

    def _run(self, extra_args=None):
        script = os.path.join(SHARED, "design", "library_pipeline.py")
        command = [
            sys.executable, script, self.genome, self.outdir,
            "--fasta", self.fasta, "--preset", "cas9",
            "--engine", "exact", "--max-mismatch", "2",
        ]
        command.extend(extra_args or [])
        return subprocess.run(
            command,
            capture_output=True, text=True, cwd=ROOT)

    def test_fasta_mode_produces_library(self):
        result = self._run()
        self.assertEqual(result.returncode, 0, result.stderr)
        score_path = os.path.join(self.outdir, "library_scores.tsv")
        self.assertTrue(os.path.isfile(score_path))
        with open(score_path, "r", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle, delimiter="\t"))
        self.assertTrue(rows)
        self.assertIn(GUIDE, {row["guide_seq"] for row in rows})
        self.assertTrue(
            os.path.isfile(os.path.join(self.outdir,
                                        "top_offtargets.tsv")))
        top_path = os.path.join(self.outdir, "top_offtargets.tsv")
        with open(top_path, "r", encoding="utf-8") as handle:
            top_rows = list(csv.DictReader(handle, delimiter="\t"))
        if top_rows:
            self.assertIn("guide", top_rows[0])
            self.assertIn("strand", top_rows[0])
            self.assertIn("indel", top_rows[0])
            self.assertIn("engine", top_rows[0])
            by_qid = {}
            for row in top_rows:
                by_qid.setdefault(row["qid"], []).append(row)
            for rows in by_qid.values():
                mismatches = [int(row["mismatch"]) for row in rows]
                self.assertEqual(mismatches, sorted(mismatches))
        summary_path = os.path.join(self.outdir, "library_summary.json")
        with open(summary_path, "r", encoding="utf-8") as handle:
            summary = json.load(handle)
        self.assertEqual(summary["requested_engine"], "exact")
        self.assertEqual(summary["engine"], "exact")
        self.assertEqual(summary["search_mode"], "exact")
        self.assertTrue(summary["engine_capabilities"])

    def test_memory_limit_error_exits_without_library_output(self):
        index_prefix = os.path.join(self.tmp.name, "bounded_index")
        result = self._run([
            "--engine", "indexed",
            "--index-path", index_prefix,
            "--max-memory-mb", "1",
        ])
        self.assertEqual(result.returncode, 6, result.stderr)
        self.assertIn("MEMORY_LIMIT_EXCEEDED", result.stdout)
        self.assertFalse(
            os.path.exists(os.path.join(self.outdir, "library_scores.tsv")))

    def test_indexed_engine_writes_a_nonempty_index_report(self):
        outdir = os.path.join(self.tmp.name, "out_indexed")
        index_dir = os.path.join(self.tmp.name, "idx")
        os.makedirs(index_dir, exist_ok=True)
        script = os.path.join(SHARED, "design", "library_pipeline.py")
        result = subprocess.run(
            [sys.executable, script, self.genome, outdir,
             "--fasta", self.fasta, "--preset", "cas9",
             "--engine", "indexed",
             "--index-path", os.path.join(index_dir, "prefix"),
             "--max-mismatch", "2", "--max-bulge", "0"],
            capture_output=True, text=True, cwd=ROOT)
        self.assertEqual(result.returncode, 0, result.stderr)
        with open(os.path.join(outdir, "index_report.json"),
                  "r", encoding="utf-8") as handle:
            report = json.load(handle)
        self.assertTrue(report)
        self.assertEqual(report["engine"], "indexed")
        self.assertEqual(report["engine_used"], "indexed")
        with open(os.path.join(outdir, "library_summary.json"),
                  "r", encoding="utf-8") as handle:
            summary = json.load(handle)
        self.assertEqual(summary["engine"], "indexed")
        self.assertEqual(summary["requested_engine"], "indexed")
        self.assertTrue(summary["engine_capabilities"])

    def test_auto_engine_summary_reports_the_engine_that_really_ran(self):
        outdir = os.path.join(self.tmp.name, "out_auto")
        script = os.path.join(SHARED, "design", "library_pipeline.py")
        env = dict(os.environ)
        env["CRISPR_OFFTARGET_ENGINE_FALLBACK"] = "allow"
        result = subprocess.run(
            [sys.executable, script, self.genome, outdir,
             "--fasta", self.fasta, "--preset", "cas9",
             "--engine", "auto", "--max-mismatch", "2", "--max-bulge", "0"],
            capture_output=True, text=True, cwd=ROOT, env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        with open(os.path.join(outdir, "library_summary.json"),
                  "r", encoding="utf-8") as handle:
            summary = json.load(handle)
        self.assertEqual(summary["requested_engine"], "auto")
        executed = summary["engine"]
        self.assertNotEqual(executed, "auto")
        self.assertIn(executed, ENGINE_CHOICES)
        self.assertEqual(summary["search_mode"], executed)
        self.assertTrue(summary["engine_capabilities"])
        with open(os.path.join(outdir, "top_offtargets.tsv"),
                  "r", encoding="utf-8") as handle:
            hit_engines = {row["engine"] for row in csv.DictReader(
                handle, delimiter="\t")}
        if hit_engines:
            self.assertEqual(hit_engines, {executed})

    def test_fasta_mode_writes_every_selected_model_score(self):
        result = self._run([
            "--on-target-model", "cropsr,rules",
            "--off-target-model", "cfd,crispr_m",
        ])
        self.assertEqual(result.returncode, 0, result.stderr)
        score_path = os.path.join(self.outdir, "library_scores.tsv")
        with open(score_path, "r", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle, delimiter="\t"))
        self.assertTrue(rows)
        self.assertIn("on_target_score_cropsr", rows[0])
        self.assertIn("on_target_score_rules", rows[0])
        self.assertIn("off_target_specificity_cfd", rows[0])
        self.assertIn("off_target_specificity_crispr_m", rows[0])
        for key in (
            "on_target_model_cropsr",
            "on_target_model_rules",
            "off_target_model_cfd",
            "off_target_model_crispr_m",
            "on_target_score",
            "on_target_model",
            "off_target_specificity",
            "off_target_model",
            "rna_model",
            "omega_model",
            "reference_only",
            "reference_note",
            "rule_source",
            "rule_reference",
            "rule_summary",
            "subtype_note",
            "cfd_specificity",
            "crispr_m_off_target",
            "deepcrispr_off_target",
            "crispai_off_target",
            "deepcas12a_on_target",
            "deepcpf1_on_target",
            "tiger_on_target",
            "tiger_off_target",
        ):
            self.assertNotIn(key, rows[0])

    def test_bed_mode_writes_annotation_columns(self):
        bed = os.path.join(self.tmp.name, "regions.bed")
        gff = os.path.join(self.tmp.name, "ann.gff")
        outdir = os.path.join(self.tmp.name, "out_ann")
        with open(bed, "w", encoding="utf-8") as handle:
            handle.write("chr1\t0\t120\tregion1\n")
        with open(gff, "w", encoding="utf-8") as handle:
            handle.write("##gff-version 3\n")
            handle.write("chr1\t.\tgene\t1\t120\t.\t+\t.\t"
                         "ID=gene1;Name=GENE1\n")
            handle.write("chr1\t.\tmRNA\t1\t120\t.\t+\t.\t"
                         "ID=tx1;Parent=gene1\n")
        script = os.path.join(SHARED, "design", "library_pipeline.py")
        result = subprocess.run(
            [sys.executable, script, bed, self.genome, outdir,
             "--preset", "cas9", "--engine", "exact",
             "--max-mismatch", "2", "--annotation", gff],
            capture_output=True, text=True, cwd=ROOT)
        self.assertEqual(result.returncode, 0, result.stderr)
        score_path = os.path.join(outdir, "library_scores.tsv")
        with open(score_path, "r", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle, delimiter="\t"))
        self.assertTrue(rows)
        # BED regions keep their genomic coordinates, so the annotation columns
        # are populated and kept (blank columns are still dropped by default).
        self.assertIn("guide_seq", rows[0])
        self.assertIn("off_target_specificity_rules", rows[0])
        self.assertNotIn("off_target_specificity", rows[0])
        self.assertIn("annotation", rows[0])
        self.assertIn("nearest_tss", rows[0])

    def test_queries_tsv_mode(self):
        tsv = os.path.join(self.tmp.name, "queries.tsv")
        outdir = os.path.join(self.tmp.name, "out_tsv")
        with open(tsv, "w", encoding="utf-8") as handle:
            handle.write("qid\tquery_seq\nq1\t%s\n"
                         % ("C" * 30 + GUIDE + "AGG" + "G" * 30))
        script = os.path.join(SHARED, "design", "library_pipeline.py")
        result = subprocess.run(
            [sys.executable, script, self.genome, outdir,
             "--queries-tsv", tsv, "--preset", "cas9",
             "--engine", "exact", "--max-mismatch", "2"],
            capture_output=True, text=True, cwd=ROOT)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(
            os.path.isfile(os.path.join(outdir, "library_scores.tsv")))

    def test_region_description_threads_coordinates(self):
        from design.library_utils import (
            _region_description, parse_region_description, queries_to_fasta)
        row = {
            "qid": "uniq_0",
            "sequence": "ACGTACGT",
            "positions": json.dumps(
                [["chr1:0-120:+:region1", "plus", 50, 60]]
            ),
        }
        desc = _region_description(row)
        self.assertEqual(desc, "region:chr1:0:120:+:60")
        parsed = parse_region_description("uniq_0 %s" % desc)
        self.assertEqual(
            parsed,
            {"chrom": "chr1", "start": 0, "end": 120, "strand": "+",
             "target_start": 60},
        )

        tsv = os.path.join(self.tmp.name, "queries.tsv")
        with open(tsv, "w", encoding="utf-8") as handle:
            handle.write("# motif=TTAT flanking_len=5 side=upstream\n")
            handle.write("qid\tsequence\tpositions\n")
            handle.write(
                "uniq_0\tACGTACGT\t%s\n"
                % json.dumps([["chr1:0-120:+:region1", "plus", 50, 60]])
            )
        fasta = os.path.join(self.tmp.name, "queries.fa")
        count = queries_to_fasta(tsv, fasta)
        self.assertEqual(count, 1)
        with open(fasta, "r", encoding="utf-8") as handle:
            header = handle.readline().strip()
        self.assertIn("region:chr1:0:120:+:60", header)


if __name__ == "__main__":
    unittest.main()
