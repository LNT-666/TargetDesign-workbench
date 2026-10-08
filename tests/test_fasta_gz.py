#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for gzip-compressed genome FASTA inputs (data preparation + extraction)."""

import gzip
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHARED = os.path.join(ROOT, "shared")
sys.path.insert(0, ROOT)
sys.path.insert(0, SHARED)

ASSETS = os.path.join(ROOT, "tests", "data", "fasta_gz")
MINI_FNA = os.path.join(ASSETS, "mini.fna")
MINI_FNA_GZ = os.path.join(ASSETS, "mini.fna.gz")
MINI_GFF = os.path.join(ASSETS, "mini.gff")

from data.annotation_utils import ensure_plain_fasta  # noqa: E402
from search.blast_utils import build_exclusion_intervals, load_genome_and_prepare_fasta  # noqa: E402


class FakeEntry:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value


def stage_fixtures(tmp, with_plain=True):
    """Copy the fixtures into a temp directory; return (plain, gz, gff)."""
    plain = os.path.join(tmp, "mini.fna")
    gz = os.path.join(tmp, "mini.fna.gz")
    gff = os.path.join(tmp, "mini.gff")
    if with_plain:
        shutil.copyfile(MINI_FNA, plain)
    shutil.copyfile(MINI_FNA_GZ, gz)
    shutil.copyfile(MINI_GFF, gff)
    return plain, gz, gff


def read_bytes(path):
    with open(path, "rb") as handle:
        return handle.read()


class EnsurePlainFastaTests(unittest.TestCase):
    # 1. plain input is returned untouched, nothing new appears next to it
    def test_plain_input_returned_untouched(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            plain, _gz, _gff = stage_fixtures(tmp)
            before = sorted(os.listdir(tmp))
            logs = []

            prepared = ensure_plain_fasta(plain, logs.append)

            self.assertEqual(prepared, plain)
            self.assertEqual(sorted(os.listdir(tmp)), before)
            self.assertEqual(logs, [])

    # 2. gz input -> <tmp>/mini.fna, byte-identical to the plain fixture
    def test_gz_input_is_decompressed_next_to_source(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            plain, gz, _gff = stage_fixtures(tmp, with_plain=False)
            logs = []

            prepared = ensure_plain_fasta(gz, logs.append)

            self.assertEqual(prepared, plain)
            self.assertTrue(os.path.isfile(prepared))
            self.assertEqual(read_bytes(prepared), read_bytes(MINI_FNA))
            self.assertNotEqual(read_bytes(prepared)[:2], b"\x1f\x8b")
            self.assertEqual(logs, ["Decompressed genome FASTA: %s" % prepared])

    # 3. second call reuses the existing product (same path, same mtime)
    def test_second_call_reuses_existing_plain_fasta(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            _plain, gz, _gff = stage_fixtures(tmp, with_plain=False)
            logs = []

            first = ensure_plain_fasta(gz, logs.append)
            stamp = os.path.getmtime(first)
            second = ensure_plain_fasta(gz, logs.append)

            self.assertEqual(second, first)
            self.assertEqual(os.path.getmtime(second), stamp)
            self.assertEqual(logs[-1], "Using existing plain FASTA: %s" % first)

    # 4. ".gz" extension with plain-text payload -> returned as is (magic bytes rule)
    def test_plain_text_behind_gz_extension_is_returned_as_is(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            decoy = os.path.join(tmp, "decoy.fna.gz")
            with open(decoy, "w", encoding="ascii", newline="\n") as handle:
                handle.write(">not really compressed\nACGT\n")
            logs = []

            self.assertEqual(ensure_plain_fasta(decoy, logs.append), decoy)
            self.assertEqual(logs, [])
            self.assertFalse(os.path.exists(os.path.join(tmp, "decoy.fna")))

    # 5. corrupt gz -> None, no half-written target, one failure log line
    def test_corrupt_gz_fails_without_leaving_partial_target(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            broken = os.path.join(tmp, "broken.fna.gz")
            with open(broken, "wb") as handle:
                handle.write(b"\x1f\x8b" + b"garbage payload, not deflate data")
            logs = []

            self.assertIsNone(ensure_plain_fasta(broken, logs.append))
            self.assertFalse(os.path.exists(os.path.join(tmp, "broken.fna")))
            self.assertFalse(os.path.exists(os.path.join(tmp, "broken.fna.part")))
            self.assertEqual(len(logs), 1)
            self.assertTrue(
                logs[0].startswith("Failed to prepare FASTA (%s)" % broken), logs[0])

    # 6. "genome.gz" (FASTA payload) -> "<tmp>/genome.fna"
    def test_missing_fasta_extension_is_extended_with_fna(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            source = os.path.join(tmp, "genome.gz")
            shutil.copyfile(MINI_FNA_GZ, source)

            prepared = ensure_plain_fasta(source)

            self.assertEqual(prepared, os.path.join(tmp, "genome.fna"))
            self.assertEqual(read_bytes(prepared), read_bytes(MINI_FNA))


class MainAppGenomeGzTests(unittest.TestCase):
    @staticmethod
    def _app(genome, gtf, output_dir):
        from main import MainApp

        app = MainApp.__new__(MainApp)
        app.entry_genome = FakeEntry(genome)
        app.entry_gtf = FakeEntry(gtf)
        app.entry_output = FakeEntry(output_dir)
        app.entry_target_id = FakeEntry("A")
        app.entry_target_num = FakeEntry("")
        app.combo_target_region = FakeEntry("Coding region")
        app.combo_target_id_type = FakeEntry("gene_name")
        app._gtf_cache = {}
        app._genome_cache = {}
        app.log_messages = []
        app.log = app.log_messages.append
        return app

    # 7. end-to-end: gz genome behaves exactly like the plain one
    def test_gz_and_plain_genome_extract_identically(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            plain, gz, gff = stage_fixtures(tmp)
            plain_out = os.path.join(tmp, "plain_out")
            gz_out = os.path.join(tmp, "gz_out")

            plain_app = self._app(plain, gff, plain_out)
            gz_app = self._app(gz, gff, gz_out)

            prepared = gz_app._get_prepared_genome()
            self.assertTrue(prepared)
            self.assertEqual(prepared, plain)
            with open(prepared, "r", encoding="ascii") as handle:
                self.assertEqual(handle.read(1), ">")

            gz_parts = gz_app._extract_sequences(
                "A", "Coding region", None, "gene_name", gff)
            plain_parts = plain_app._extract_sequences(
                "A", "Coding region", None, "gene_name", gff)
            self.assertEqual(gz_parts, plain_parts)
            self.assertEqual(len(gz_parts[0][1].replace("\n", "")), 1000)

            gz_target = gz_app._extract_target_fasta(gff, gz_out)
            plain_target = plain_app._extract_target_fasta(gff, plain_out)
            self.assertEqual(read_bytes(gz_target), read_bytes(plain_target))

    # 8. round 2: a newer source refreshes the plain copy even with a warm cache
    def test_source_replaced_while_cache_warm_is_refreshed(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            _plain, gz, gff = stage_fixtures(tmp, with_plain=False)
            app = self._app(gz, gff, os.path.join(tmp, "out"))
            prepared = app._get_prepared_genome()
            self.assertTrue(prepared)
            before = read_bytes(prepared)

            replacement = ">NC_000001.11 synthetic\nTTTT\n"
            with open(gz, "wb") as raw:
                with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as handle:
                    handle.write(replacement.encode("ascii"))
            newer = os.path.getmtime(gz) + 10
            os.utime(gz, (newer, newer))

            refreshed = app._get_prepared_genome()

            self.assertEqual(refreshed, prepared)
            self.assertEqual(read_bytes(refreshed), replacement.encode("ascii"))
            self.assertNotEqual(read_bytes(refreshed), before)

    # 9. round 2: a deleted plain copy is rebuilt (cache must not resurrect it)
    def test_deleted_plain_copy_is_rebuilt(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            _plain, gz, gff = stage_fixtures(tmp, with_plain=False)
            app = self._app(gz, gff, os.path.join(tmp, "out"))
            prepared = app._get_prepared_genome()
            os.remove(prepared)

            again = app._get_prepared_genome()

            self.assertEqual(again, prepared)
            self.assertTrue(os.path.isfile(again))
            self.assertEqual(read_bytes(again), read_bytes(MINI_FNA))


class FakeWorkbench:
    """Minimal stand-in for PatternDesignerWorkbench (no Tk root needed)."""

    def __init__(self, values):
        self.values = values
        self.logs = []

    def _value(self, key, default=""):
        return self.values.get(key, default)

    def _log_line(self, line):
        self.logs.append(line)

    def _form_state(self):
        from design.workbench_form import WorkbenchFormState

        return WorkbenchFormState(values=dict(self.values), log=self._log_line)


class EngineGenomeGzTests(unittest.TestCase):
    """Engine / workbench genome entry points must accept .fna.gz too."""

    def test_engine_load_genome_accepts_gz(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            _plain, gz, _gff = stage_fixtures(tmp, with_plain=False)

            index, resolved, temp_file = load_genome_and_prepare_fasta(gz)

            self.assertIsNone(temp_file)
            self.assertEqual(os.path.basename(resolved), "mini.fna")
            self.assertEqual(read_bytes(resolved), read_bytes(MINI_FNA))
            self.assertEqual(str(index["NC_000001.11"][0:10]), "ACGTTGCAAC")

    def test_workbench_genome_row_prepares_gz(self):
        from designer_workbench import PatternDesignerWorkbench

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            plain, gz, _gff = stage_fixtures(tmp, with_plain=False)
            stub = FakeWorkbench({"genome_fasta": gz, "output_dir": tmp})

            prepared = PatternDesignerWorkbench._prepare_genome_fasta(stub)

            self.assertEqual(prepared, plain)
            self.assertEqual(read_bytes(prepared), read_bytes(MINI_FNA))
            self.assertTrue(
                any("Decompressed genome FASTA" in line for line in stub.logs),
                stub.logs)

            plain_stub = FakeWorkbench({"genome_fasta": plain, "output_dir": tmp})
            self.assertEqual(
                PatternDesignerWorkbench._prepare_genome_fasta(plain_stub), plain)
            self.assertEqual(plain_stub.logs, [])

            self.assertEqual(
                PatternDesignerWorkbench._prepare_genome_fasta(FakeWorkbench({})), "")


def _fake_genome(sequences):
    """Return a pyfaidx-like genome object for build_exclusion_intervals."""

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

        def keys(self):
            return list(self._records.keys())

        def __getitem__(self, key):
            return _Record(self._records[key])

    return _Genome(dict(sequences))


class ExclusionMaskGzTests(unittest.TestCase):
    """Exclusion masks may be gzip-compressed; results must match the plain run."""

    GENOME = {"chr1": "TTTTGATTACACCCCGATTACAGGGG"}
    MASK = b">mask_a\nGATTACA\n>mask_b\nGATTAC\n"
    EXPECTED = {"chr1": [(4, 11), (15, 22)]}

    @staticmethod
    def _intervals(mask_path):
        genome = _fake_genome(ExclusionMaskGzTests.GENOME)
        return build_exclusion_intervals(mask_path, genome)

    def _write(self, tmp):
        plain = os.path.join(tmp, "mask_plain.fna")
        gz = os.path.join(tmp, "mask_gz.fna.gz")
        with open(plain, "wb") as handle:
            handle.write(self.MASK)
        with open(gz, "wb") as raw:
            with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as handle:
                handle.write(self.MASK)
        return plain, gz

    # 10. a plain mask is read in place and nothing is written next to it
    def test_plain_mask_matches_expected_and_writes_nothing(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            plain, _gz = self._write(tmp)
            before = sorted(os.listdir(tmp))

            self.assertEqual(self._intervals(plain), self.EXPECTED)
            self.assertEqual(sorted(os.listdir(tmp)), before)

    # 11. a gz mask is decompressed first and yields the same intervals
    def test_gz_mask_is_decompressed_and_matches_plain(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            plain, gz = self._write(tmp)

            self.assertEqual(self._intervals(gz), self.EXPECTED)
            self.assertEqual(self._intervals(gz), self._intervals(plain))
            sibling = os.path.join(tmp, "mask_gz.fna")
            self.assertTrue(os.path.isfile(sibling))
            self.assertEqual(read_bytes(sibling), self.MASK)
            self.assertFalse(os.path.exists(sibling + ".part"))

    # 12. an unreadable gz mask fails loudly instead of raising UnicodeDecodeError
    def test_corrupt_gz_mask_raises_clear_error(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            broken = os.path.join(tmp, "mask_broken.fna.gz")
            with open(broken, "wb") as handle:
                handle.write(b"\x1f\x8b" + b"not deflate data")

            with self.assertRaises(ValueError) as caught:
                self._intervals(broken)
            self.assertIn("Could not decompress mask FASTA", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
