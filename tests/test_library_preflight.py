#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for shared engine choices and library preflight checks."""

import os
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHARED = os.path.join(ROOT, "shared")
sys.path.insert(0, SHARED)

from design.library_preflight import (  # noqa: E402
    ENGINE_CHOICES, LEGACY_ENGINE_CHOICES, preflight_library,
    validate_engine,
)


class EngineChoicesTests(unittest.TestCase):
    def test_full_engine_list(self):
        self.assertEqual(
            ENGINE_CHOICES,
            ["exact", "indexed", "blast", "gggenome", "auto"])
        self.assertTrue(set(LEGACY_ENGINE_CHOICES).issubset(ENGINE_CHOICES))

    def test_validate_engine(self):
        self.assertEqual(validate_engine("Indexed"), "indexed")
        with self.assertRaises(ValueError):
            validate_engine("not_an_engine")


class PreflightTests(unittest.TestCase):
    def test_missing_genome_is_error(self):
        errors, _ = preflight_library("exact", genome="missing.fa")
        self.assertTrue(any("does not exist" in item for item in errors))

    def test_indexed_missing_index_is_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            genome = os.path.join(tmp, "genome.fa")
            with open(genome, "w", encoding="utf-8") as handle:
                handle.write(">chr1\nACGT\n")
            errors, warnings = preflight_library(
                "indexed", genome=genome, index_path="idx/prefix")
            self.assertFalse(errors)
            self.assertTrue(any("built automatically" in item for item in warnings))

    @mock.patch("design.library_preflight.get_backend")
    def test_blast_missing_db_is_error(self, _get_backend):
        _get_backend.return_value.available.return_value = (True, "")
        with tempfile.TemporaryDirectory() as tmp:
            genome = os.path.join(tmp, "genome.fa")
            with open(genome, "w", encoding="utf-8") as handle:
                handle.write(">chr1\nACGT\n")
            errors, warnings = preflight_library(
                "blast", genome=genome, blastdb="db/prefix")
            self.assertTrue(any("BLAST database is incomplete" in item
                                for item in errors))
            self.assertFalse(warnings)

    @mock.patch("design.library_preflight.get_backend")
    def test_blast_without_db_is_warning(self, _get_backend):
        _get_backend.return_value.available.return_value = (True, "")
        with tempfile.TemporaryDirectory() as tmp:
            genome = os.path.join(tmp, "genome.fa")
            with open(genome, "w", encoding="utf-8") as handle:
                handle.write(">chr1\nACGT\n")
            errors, warnings = preflight_library(
                "blast", genome=genome)
            self.assertFalse(errors)
            self.assertTrue(any("built first on export" in item for item in warnings))

    @mock.patch("design.library_preflight._model_ready", return_value=(False, "not downloaded"))
    def test_model_missing_warns(self, _ready):
        with tempfile.TemporaryDirectory() as tmp:
            genome = os.path.join(tmp, "genome.fa")
            with open(genome, "w", encoding="utf-8") as handle:
                handle.write(">chr1\nACGT\n")
            _, warnings = preflight_library(
                "exact", genome=genome, off_target_model="crispr_m")
            self.assertTrue(any("crispr_m" in item and "fall back" in item
                                for item in warnings))

    def test_invalid_engine_is_reported_as_an_error(self):
        errors, warnings = preflight_library("bad-engine")
        self.assertTrue(any("Unknown off-target engine" in item
                            for item in errors))
        self.assertFalse(warnings)

    def test_removed_engine_is_reported_as_an_error(self):
        for name in ("bowtie2", "casoffinder"):
            with self.subTest(engine=name):
                errors, warnings = preflight_library(name)
                self.assertTrue(any("was removed" in item for item in errors))
                self.assertFalse(warnings)

    @mock.patch("design.library_preflight.MAX_EXACT_GENOME_BYTES", 100)
    @mock.patch("design.library_preflight.get_backend")
    def test_large_genome_blocks_exact(self, _get_backend):
        _get_backend.return_value.available.return_value = (True, "")
        with tempfile.TemporaryDirectory() as tmp:
            genome = os.path.join(tmp, "large.fa")
            with open(genome, "wb") as handle:
                handle.write(b">chr1\n" + b"A" * 200)
            errors, _ = preflight_library("exact", genome=genome)
            self.assertTrue(any("not suitable for large genomes" in item
                                for item in errors))


class PipelinePreflightTests(unittest.TestCase):
    def test_preflight_only_fails_fast(self):
        import subprocess
        script = os.path.join(SHARED, "design", "library_pipeline.py")
        result = subprocess.run(
            [sys.executable, script, "missing.fa", "out",
             "--engine", "exact", "--preflight-only"],
            capture_output=True, text=True, cwd=ROOT)
        self.assertEqual(result.returncode, 3)
        self.assertIn("genome FASTA does not exist", result.stdout)

    def test_preflight_only_ok(self):
        import subprocess
        with tempfile.TemporaryDirectory() as tmp:
            genome = os.path.join(tmp, "genome.fa")
            with open(genome, "w", encoding="utf-8") as handle:
                handle.write(">chr1\nACGTACGTACGT\n")
            script = os.path.join(SHARED, "design", "library_pipeline.py")
            result = subprocess.run(
                [sys.executable, script, genome, tmp,
                 "--engine", "exact", "--preflight-only"],
                capture_output=True, text=True, cwd=ROOT)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Preflight OK", result.stdout)


if __name__ == "__main__":
    unittest.main()
