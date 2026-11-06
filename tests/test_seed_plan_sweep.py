import contextlib
import hashlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
SUPPLEMENT = ROOT / "docs" / "submission" / "SUPPLEMENTARY_v1.md"
sys.path.insert(0, str(TOOLS))

import benchmark_all_engines  # noqa: E402
import seed_plan_sweep  # noqa: E402


GENOME_SHA256 = (
    "b9196a5857dbc12dab4c032b445c8602b006c0c984b6aa189b0e096dc2093299"
)
GUIDES_SHA256 = (
    "5728148559dbddfed66b5f32a08e3780dd1e1d61cda880dfa43ffee700693531"
)


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class FixtureGenerationTests(unittest.TestCase):
    def test_generate_only_reproduces_default_fixture(self):
        with tempfile.TemporaryDirectory() as fixture_dir:
            output = io.StringIO()
            with mock.patch.object(
                benchmark_all_engines,
                "load_guides",
                side_effect=AssertionError("generate-only entered benchmark"),
            ):
                with contextlib.redirect_stdout(output):
                    exit_code = benchmark_all_engines.main([
                        "--fixture-dir", fixture_dir,
                        "--genome-mb", "1",
                        "--guides", "12",
                        "--generate-only",
                    ])

            self.assertEqual(exit_code, 0)
            self.assertIn("generated fixture", output.getvalue())
            fixture_path = Path(fixture_dir)
            genome_path = fixture_path / "synthetic_genome.fa"
            guides_path = fixture_path / "guides.tsv"
            self.assertEqual(file_sha256(genome_path), GENOME_SHA256)
            self.assertEqual(file_sha256(guides_path), GUIDES_SHA256)

            metadata = json.loads(
                (fixture_path / "fixture.json").read_text(encoding="utf-8")
            )
            self.assertEqual(metadata["generator"],
                             "tools/benchmark_all_engines.py")
            self.assertEqual(metadata["seed"], 20260914)
            self.assertEqual(metadata["genome_bases"], 1000000)
            self.assertEqual(metadata["contigs"], 4)
            self.assertEqual(metadata["guides_count"], 12)
            self.assertEqual(metadata["genome_sha256"], GENOME_SHA256)
            self.assertEqual(metadata["guides_sha256"], GUIDES_SHA256)
            self.assertEqual(metadata["genome_size_bytes"],
                             genome_path.stat().st_size)
            self.assertEqual(metadata["guides_size_bytes"],
                             guides_path.stat().st_size)
            self.assertIn("--seed 20260914", metadata["command"])
            self.assertIn("--generate-only", metadata["command"])

    def test_published_provenance_matches_fixture_files(self):
        genome = ROOT / "example" / "engine_benchmark_small" / (
            "synthetic_genome.fa")
        guides = ROOT / "example" / "engine_benchmark_small" / "guides.tsv"
        actual = seed_plan_sweep.fixture_provenance(genome, guides, 12, 20)
        fixture_metadata = json.loads(
            (ROOT / "example" / "engine_benchmark_small" / "fixture.json")
            .read_text(encoding="utf-8")
        )
        sweep_metadata = json.loads(
            (ROOT / "docs" / "seed_plan_sweep.json").read_text(
                encoding="utf-8")
        )["fixture"]

        for key in (
            "generator", "seed", "genome_bases", "contigs", "command",
            "genome_sha256", "guides_sha256", "genome_size_bytes",
            "guides_size_bytes",
        ):
            self.assertEqual(fixture_metadata[key], actual[key])
            self.assertEqual(sweep_metadata[key], actual[key])
        self.assertEqual(fixture_metadata["guides_count"],
                         actual["guide_count"])
        self.assertEqual(fixture_metadata["guide_length"],
                         actual["guide_len"])
        self.assertEqual(sweep_metadata["guide_count"],
                         actual["guide_count"])
        self.assertEqual(sweep_metadata["guide_len"], actual["guide_len"])


class SeedPlanCliTests(unittest.TestCase):
    def test_missing_fixture_exits_before_engine(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                exit_code = seed_plan_sweep.main([
                    "--genome", str(temp_path / "missing.fa"),
                    "--guides", str(temp_path / "missing.tsv"),
                    "--engine-exe", str(temp_path / "missing-engine.exe"),
                    "--out", str(temp_path / "out.json"),
                ])

        message = stderr.getvalue()
        self.assertEqual(exit_code, 2)
        self.assertIn("fixture file not found", message)
        self.assertIn("python tools/benchmark_all_engines.py", message)
        self.assertIn("--generate-only", message)
        self.assertNotIn("missing-engine.exe", message)

    def test_plan_table_rejects_out(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                with self.assertRaises(SystemExit) as raised:
                    seed_plan_sweep.main([
                        "--plan-table",
                        "--out", str(Path(temp_dir) / "out.json"),
                    ])

        self.assertEqual(raised.exception.code, 2)
        self.assertIn("cannot be used with --out", stderr.getvalue())

    def test_plan_table_still_succeeds_alone(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exit_code = seed_plan_sweep.main(["--plan-table"])
        self.assertEqual(exit_code, 0)
        self.assertIn("V(k, m)", output.getvalue())

    @unittest.skipUnless(SUPPLEMENT.is_file(),
                         "internal manuscript material is not shipped with the code bundle")
    def test_supplement_table_values_match_sweep_records(self):
        document = json.loads(
            (ROOT / "docs" / "seed_plan_sweep.json").read_text(
                encoding="utf-8")
        )
        lines = (
            ROOT / "docs" / "submission" / "SUPPLEMENTARY_v1.md"
        ).read_text(encoding="utf-8").splitlines()
        required_headers = ("| k |", "| M |", "| B |", "segments", "peak RSS")
        header_index = next(
            index for index, line in enumerate(lines)
            if all(token in line for token in required_headers)
        )
        self.assertIn("peak RSS (MiB)", lines[header_index])
        self.assertNotIn("peak RSS (MB)", lines[header_index])

        table_rows = []
        for line in lines[header_index + 2:]:
            if not line.startswith("|"):
                break
            table_rows.append([
                cell.strip() for cell in line.strip().strip("|").split("|")
            ])

        self.assertEqual(len(table_rows), len(document["records"]))
        for cells, record in zip(table_rows, document["records"]):
            segments = record["py_plan_segments"]
            expected = [
                str(record["k"]),
                str(record["M"]),
                str(record["B"]),
                segments.split("x", 1)[0],
                str(record["py_plan_variants"]),
                str(record["seed_plan_guaranteed"]).lower(),
                "`%s`" % segments,
                str(record["median_search_time_s"]),
                str(record["candidates"]),
                str(record["hits"]),
                str(record["memory_peak_mb"]),
                str(record["threads"]),
                str(record["repeats"]),
                str(record["repeats_consistent"]).lower(),
            ]
            self.assertEqual(cells, expected)


if __name__ == "__main__":
    unittest.main()
