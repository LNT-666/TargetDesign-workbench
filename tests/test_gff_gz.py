#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for gzip-compressed GFF/GTF annotation inputs."""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHARED = os.path.join(ROOT, "shared")
sys.path.insert(0, ROOT)
sys.path.insert(0, SHARED)

ASSETS = os.path.join(ROOT, "tests", "data", "gff_gz")
MINI_GFF = os.path.join(ASSETS, "mini.gff")
MINI_GZ = os.path.join(ASSETS, "mini.gff.gz")

from data.add_utrs_to_gff import read_gff  # noqa: E402
from data.annotation_utils import load_gene_list  # noqa: E402


class FakeEntry:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value


class GffGzipScriptTests(unittest.TestCase):
    def test_read_gff_gz_matches_plain(self):
        plain_lines, plain_genes, plain_mrnas, plain_has_utr = read_gff(MINI_GFF)
        gz_lines, gz_genes, gz_mrnas, gz_has_utr = read_gff(MINI_GZ)

        self.assertEqual(len(gz_lines), len(plain_lines))
        self.assertEqual(len(gz_genes), len(plain_genes))
        self.assertEqual(len(gz_mrnas), len(plain_mrnas))
        self.assertEqual(gz_has_utr, plain_has_utr)

    def test_utr_script_stdout_matches_plain(self):
        plain = self._run_script(MINI_GFF)
        gz = self._run_script(MINI_GZ)

        self.assertEqual(plain.returncode, 0, plain.stderr)
        self.assertEqual(gz.returncode, 0, gz.stderr)
        self.assertEqual(gz.stdout, plain.stdout)
        self.assertIn("five_prime_UTR", gz.stdout)

    @staticmethod
    def _run_script(path):
        cmd = [sys.executable, os.path.join("shared", "data", "add_utrs_to_gff.py"), path]
        return subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", cwd=ROOT)


class GffGzipPreparedTests(unittest.TestCase):
    def _app(self, output_dir):
        from main import MainApp

        app = MainApp.__new__(MainApp)
        app.entry_output = FakeEntry(output_dir)
        app._gtf_cache = {}
        app.log_messages = []
        app.log = app.log_messages.append
        return app

    def test_prepared_gtf_from_gz_is_plain_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            prepared = self._app(tmp)._get_prepared_gtf(MINI_GZ)

            self.assertTrue(prepared)
            self.assertEqual(os.path.dirname(prepared), tmp)
            self.assertTrue(os.path.basename(prepared).endswith("mini_with_utrs.gff3"))
            self.assertTrue(os.path.exists(prepared))
            with open(prepared, "r", encoding="utf-8") as handle:
                text = handle.read()
            self.assertIn("five_prime_UTR", text)

    def test_load_gene_list_from_gz_matches_plain(self):
        # The task spec (P0-5.4) predicted ["AAA", "BBB"], but the fixture carries
        # Name=A;gene=AAA and _load_gene_attributes prefers "Name" over "gene"
        # (existing fallback order, untouched by this change), so the plain input
        # already yields ["A", "B"]. See report.md for the pre/post evidence.
        plain_values = load_gene_list(MINI_GFF, "gene_name", None, {}, None)
        gz_values = load_gene_list(MINI_GZ, "gene_name", None, {}, None)

        self.assertEqual(plain_values, ["A", "B"])
        self.assertEqual(gz_values, plain_values)

    def test_utr_product_is_refreshed_when_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "mini.gff")
            shutil.copyfile(MINI_GFF, source)
            app = self._app(tmp)

            first = app._get_prepared_gtf(source)
            self.assertTrue(first)
            reused = app._get_prepared_gtf(source)
            self.assertEqual(reused, first)
            stamp = os.path.getmtime(first)
            self.assertEqual(os.path.getmtime(reused), stamp)
            logged = len(app.log_messages)

            # Age the product like a source annotation update would: the warm
            # cache must notice and rebuild instead of serving the stale copy.
            stale = os.path.getmtime(source) - 60
            os.utime(first, (stale, stale))
            refreshed = app._get_prepared_gtf(source)

            self.assertEqual(refreshed, first)
            self.assertGreater(os.path.getmtime(refreshed), stale)
            self.assertGreater(len(app.log_messages), logged)
            self.assertTrue(
                any("stale" in line for line in app.log_messages[logged:]),
                app.log_messages[logged:])

            again = app._get_prepared_gtf(source)
            self.assertEqual(os.path.getmtime(again), os.path.getmtime(refreshed))

    def test_utr_product_keeps_non_ascii_text(self):
        # The UTR child writes the product on stdout: on Windows that defaults
        # to cp936, so non-ASCII attributes would land as GBK bytes in a file
        # we read back as UTF-8. Clear the UTF-8 env vars to reproduce a plain
        # GUI launch and check the product is still valid UTF-8.
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("PYTHONUTF8", None)
            os.environ.pop("PYTHONIOENCODING", None)
            gene_name = "测试基因A"
            source = os.path.join(tmp, "nonascii.gff")
            rows = [
                "##gff-version 3",
                "NC_000001.11\tRefSeq\tgene\t1001\t2000\t.\t+\t.\tID=gene-A;Name=%s" % gene_name,
                "NC_000001.11\tRefSeq\tmRNA\t1001\t2000\t.\t+\t.\tID=rna-A;Parent=gene-A",
                "NC_000001.11\tRefSeq\texon\t1001\t1200\t.\t+\t.\tID=exon-A1;Parent=rna-A",
                "NC_000001.11\tRefSeq\texon\t1501\t2000\t.\t+\t.\tID=exon-A2;Parent=rna-A",
                "NC_000001.11\tRefSeq\tCDS\t1101\t1200\t.\t+\t0\tID=cds-A;Parent=rna-A",
                "NC_000001.11\tRefSeq\tCDS\t1501\t1800\t.\t+\t0\tID=cds-A;Parent=rna-A",
            ]
            with open(source, "w", encoding="utf-8", newline="\n") as handle:
                handle.write("\n".join(rows) + "\n")

            prepared = self._app(tmp)._get_prepared_gtf(source)

            self.assertTrue(prepared)
            with open(prepared, "rb") as handle:
                raw = handle.read()
            self.assertIn(gene_name.encode("utf-8"), raw)
            self.assertNotIn(gene_name.encode("gbk"), raw)
            with open(prepared, "r", encoding="utf-8") as handle:
                self.assertIn(gene_name, handle.read())


if __name__ == "__main__":
    unittest.main()
