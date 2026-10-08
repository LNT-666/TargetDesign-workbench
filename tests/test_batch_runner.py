import csv
import glob
import json
import os
import sys
import tempfile
import unittest
from unittest import mock


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "shared"))

from design import batch_runner  # noqa: E402
from design.batch_runner import (  # noqa: E402
    MANIFEST_COLUMNS,
    BatchRunner,
    main_scores_path,
)
from design.batch_spec import (  # noqa: E402
    BatchGroup,
    BatchSpec,
    PatternVariant,
    ScopeSpec,
    normalize_units,
)
from design.pattern_runner import RunnerConfig  # noqa: E402
from design.pattern_spec import MotifSpec, PatternKind, PatternSpec  # noqa: E402


class FakePatternRunner:
    """Stand-in for PatternRunner: writes the main table and returns a code."""

    behavior = {}
    write_table = True
    calls = []
    stopped = False
    on_unit = None

    def __init__(self, spec, config):
        self.spec = spec
        self.config = config

    def stop(self):
        FakePatternRunner.stopped = True

    def run_pipeline(self, on_line=None, start=0, end=None):
        unit_id = os.path.basename(self.config.output_dir)
        FakePatternRunner.calls.append(unit_id)
        returncode = FakePatternRunner.behavior.get(unit_id, 0)
        if on_line:
            on_line("PROGRESS: unit 50")
        if FakePatternRunner.on_unit is not None:
            FakePatternRunner.on_unit(unit_id)
        if FakePatternRunner.stopped:
            return 130
        if FakePatternRunner.write_table and returncode == 0:
            path = main_scores_path(self.spec.kind, self.config.output_dir)
            os.makedirs(self.config.output_dir, exist_ok=True)
            with open(path, "w", encoding="utf-8", newline="") as handle:
                handle.write("qid\tscore\n%s\t1.5\n" % unit_id)
        return returncode


def _spec():
    return BatchSpec(
        batch_label="unit-test-batch",
        shared={"genome_fasta": "g.fa"},
        scopes=[
            ScopeSpec("s1", search_fasta="a.fa"),
            ScopeSpec("s2", search_fasta="b.fa"),
        ],
        patterns=[
            PatternVariant("P1", "single_motif_flank", {"motif": "TTAG"})
        ],
        groups=[BatchGroup("G1", ["s1", "s2"], ["P1"])],
    )


def _spec3():
    return BatchSpec(
        batch_label="unit-test-batch",
        shared={"genome_fasta": "g.fa"},
        scopes=[
            ScopeSpec(name, search_fasta="%s.fa" % name)
            for name in ("s1", "s2", "s3")
        ],
        patterns=[
            PatternVariant("P1", "single_motif_flank", {"motif": "TTAG"})
        ],
        groups=[BatchGroup("G1", ["s1", "s2", "s3"], ["P1"])],
    )


def _read_tsv(path):
    with open(path, "r", encoding="utf-8", newline="") as handle:
        return list(csv.reader(handle, delimiter="\t"))


class BatchRunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(self._cleanup)
        self._patches = []

    def _cleanup(self):
        for patcher in getattr(self, "_patches", []):
            patcher.stop()

    def _start_patches(self):
        FakePatternRunner.stopped = False
        FakePatternRunner.on_unit = None
        self._patches = [
            mock.patch.object(
                batch_runner, "build_unit_form_state", return_value=object()
            ),
            mock.patch.object(
                batch_runner,
                "build_pattern_spec",
                return_value=PatternSpec(
                    kind=PatternKind.SINGLE_MOTIF_FLANK,
                    motif=MotifSpec("TTAG", 0),
                ),
            ),
            mock.patch.object(
                batch_runner,
                "build_runner_config",
                side_effect=lambda *a, **k: RunnerConfig(
                    output_dir="ignored", run_label="ignored"
                ),
            ),
            mock.patch.object(
                batch_runner, "PatternRunner", FakePatternRunner
            ),
        ]
        for patcher in self._patches:
            patcher.start()

    def _make_runner(self, resume=True, on_line=None):
        spec = _spec()
        units = normalize_units(spec)
        return spec, units, BatchRunner(
            spec, units, self.tmp, on_line=on_line, resume=resume
        )

    def test_manifest_rows_and_summary_columns(self):
        self._start_patches()
        FakePatternRunner.behavior = {}
        FakePatternRunner.calls = []
        _spec_obj, units, runner = self._make_runner()

        self.assertEqual(runner.run(), 0)
        self.assertEqual(FakePatternRunner.calls, ["s1__P1", "s2__P1"])

        manifest = _read_tsv(runner.manifest_path)
        self.assertEqual(manifest[0], MANIFEST_COLUMNS)
        self.assertEqual(len(manifest), 3)
        self.assertEqual([row[0] for row in manifest[1:]], ["s1__P1", "s2__P1"])
        self.assertEqual([row[3] for row in manifest[1:]], ["ok", "ok"])
        self.assertEqual(manifest[1][8], "s1__P1/query_scores_sorted.tsv")

        summary = _read_tsv(runner.summary_path)
        self.assertEqual(
            summary[0],
            [
                "batch_id",
                "unit_id",
                "scope_id",
                "pattern_id",
                "qid",
                "score",
            ],
        )
        self.assertEqual(len(summary), 3)
        self.assertEqual(summary[1][:4], ["unit-test-batch", "s1__P1", "s1", "P1"])
        self.assertEqual(summary[2][:4], ["unit-test-batch", "s2__P1", "s2", "P1"])

    def test_summary_renames_clashing_key_columns(self):
        self._start_patches()

        def clashing(self, on_line=None, start=0, end=None):
            unit_id = os.path.basename(self.config.output_dir)
            FakePatternRunner.calls.append(unit_id)
            path = main_scores_path(self.spec.kind, self.config.output_dir)
            os.makedirs(self.config.output_dir, exist_ok=True)
            with open(path, "w", encoding="utf-8", newline="") as handle:
                handle.write("unit_id\tscore\n%s\t1.5\n" % unit_id)
            return 0

        FakePatternRunner.behavior = {}
        FakePatternRunner.calls = []
        with mock.patch.object(FakePatternRunner, "run_pipeline", clashing):
            _spec_obj, units, runner = self._make_runner()
            self.assertEqual(runner.run(), 0)

        summary = _read_tsv(runner.summary_path)
        self.assertEqual(
            summary[0][:4],
            ["batch_id", "batch_unit_id", "scope_id", "pattern_id"],
        )
        self.assertIn("unit_id", summary[0])

    def test_resume_skips_finished_units(self):
        self._start_patches()
        FakePatternRunner.behavior = {}
        FakePatternRunner.calls = []
        _spec_obj, units, runner = self._make_runner()
        runner.run()

        FakePatternRunner.calls = []
        _spec_obj, units, runner = self._make_runner()
        self.assertEqual(runner.run(), 0)
        self.assertEqual(FakePatternRunner.calls, [])
        manifest = _read_tsv(runner.manifest_path)
        self.assertEqual([row[3] for row in manifest[1:]], ["skipped", "skipped"])

    def test_no_resume_reruns_and_backs_up_manifest(self):
        self._start_patches()
        FakePatternRunner.behavior = {}
        FakePatternRunner.calls = []
        _spec_obj, units, runner = self._make_runner()
        runner.run()

        FakePatternRunner.calls = []
        _spec_obj, units, runner = self._make_runner(resume=False)
        self.assertEqual(runner.run(), 0)
        self.assertEqual(FakePatternRunner.calls, ["s1__P1", "s2__P1"])
        backups = glob.glob(os.path.join(self.tmp, "manifest.*.tsv"))
        self.assertEqual(len(backups), 1)

    def test_single_unit_failure_does_not_stop_the_batch(self):
        self._start_patches()
        FakePatternRunner.behavior = {"s1__P1": 3}
        FakePatternRunner.calls = []
        _spec_obj, units, runner = self._make_runner()

        self.assertEqual(runner.run(), 1)
        self.assertEqual(FakePatternRunner.calls, ["s1__P1", "s2__P1"])
        manifest = _read_tsv(runner.manifest_path)
        self.assertEqual(manifest[1][3], "failed")
        self.assertEqual(manifest[1][4], "3")
        self.assertEqual(manifest[2][3], "ok")

    def test_stopped_return_code_stops_immediately(self):
        self._start_patches()
        FakePatternRunner.behavior = {"s1__P1": 130}
        FakePatternRunner.calls = []
        _spec_obj, units, runner = self._make_runner()

        self.assertEqual(runner.run(), 130)
        self.assertEqual(FakePatternRunner.calls, ["s1__P1"])
        manifest = _read_tsv(runner.manifest_path)
        self.assertEqual(len(manifest), 2)
        self.assertEqual(manifest[1][3], "stopped")

    def test_progress_lines_are_emitted(self):
        self._start_patches()
        FakePatternRunner.behavior = {}
        FakePatternRunner.calls = []
        lines = []
        _spec_obj, units, runner = self._make_runner(
            on_line=lines.append
        )
        runner.run()
        self.assertIn("PROGRESS_TARGET: 1/2", lines)
        self.assertIn("PROGRESS_TARGET: 2/2", lines)
        self.assertIn("PROGRESS: batch 50", lines)
        self.assertIn("PROGRESS: batch 100", lines)

    def test_run_writes_log_and_meta(self):
        self._start_patches()
        FakePatternRunner.behavior = {}
        FakePatternRunner.calls = []
        spec, units, _runner = self._make_runner()
        runner = BatchRunner(
            spec,
            units,
            self.tmp,
            run_meta={"run_id": "0114", "label": "20261006-0114"},
        )
        self.assertEqual(runner.run(), 0)

        with open(runner.log_path, "r", encoding="utf-8") as handle:
            log = handle.read()
        self.assertIn("INFO: batch unit-test-batch | run 0114", log)
        self.assertIn("PROGRESS_TARGET: 1/2", log)
        self.assertIn("PROGRESS: batch 100", log)

        with open(
            os.path.join(self.tmp, "run.json"), "r", encoding="utf-8"
        ) as handle:
            meta = json.load(handle)
        self.assertEqual(meta["run_id"], "0114")
        self.assertEqual(meta["label"], "20261006-0114")

    def test_bad_on_line_handler_does_not_abort(self):
        self._start_patches()
        FakePatternRunner.behavior = {}
        FakePatternRunner.calls = []

        def explode(_line):
            raise RuntimeError("handler boom")

        _spec_obj, units, runner = self._make_runner(on_line=explode)
        self.assertEqual(runner.run(), 0)

    def test_main_scores_path_mapping(self):
        self.assertTrue(
            main_scores_path(
                PatternKind.SINGLE_MOTIF_FLANK, "d"
            ).endswith(os.path.join("d", "query_scores_sorted.tsv"))
        )
        self.assertTrue(
            main_scores_path(
                PatternKind.MOTIF_GAP_MOTIF, "d"
            ).endswith(os.path.join("d", "query_scores_sorted.tsv"))
        )
        self.assertTrue(
            main_scores_path(
                PatternKind.Y_CENTERED_MOTIFS, "d"
            ).endswith(os.path.join("d", "scores.sorted.tsv"))
        )

    def test_stop_before_first_unit_skips_everything(self):
        self._start_patches()
        FakePatternRunner.behavior = {}
        FakePatternRunner.calls = []
        _spec_obj, units, runner = self._make_runner()
        runner.stop()
        self.assertEqual(runner.run(), 130)
        self.assertEqual(FakePatternRunner.calls, [])
        self.assertTrue(os.path.isfile(runner.manifest_path))

    def test_stop_during_first_unit_stops_the_batch(self):
        self._start_patches()
        FakePatternRunner.behavior = {}
        FakePatternRunner.calls = []
        holder = {}
        FakePatternRunner.on_unit = lambda _unit_id: holder["runner"].stop()
        _spec_obj, units, runner = self._make_runner()
        holder["runner"] = runner
        self.assertEqual(runner.run(), 130)
        self.assertEqual(FakePatternRunner.calls, ["s1__P1"])
        rows = _read_tsv(runner.manifest_path)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1][3], "stopped")

    def test_partial_run_preserves_other_manifest_rows(self):
        self._start_patches()
        FakePatternRunner.behavior = {}
        FakePatternRunner.calls = []
        spec = _spec3()
        units = normalize_units(spec)
        full = BatchRunner(spec, units, self.tmp)
        self.assertEqual(full.run(), 0)
        self.assertEqual(len(_read_tsv(full.manifest_path)), 4)

        FakePatternRunner.calls = []
        partial = BatchRunner(
            spec, [u for u in units if u.unit_id == "s2__P1"], self.tmp
        )
        self.assertEqual(partial.run(), 0)
        rows = _read_tsv(partial.manifest_path)
        self.assertEqual(len(rows), 4)
        self.assertEqual(
            [row[0] for row in rows[1:]],
            ["s2__P1", "s1__P1", "s3__P1"],
        )
        self.assertEqual(rows[1][3], "skipped")

        FakePatternRunner.calls = []
        again = BatchRunner(spec, units, self.tmp)
        self.assertEqual(again.run(), 0)
        self.assertEqual(FakePatternRunner.calls, [])
        rows = _read_tsv(again.manifest_path)
        self.assertEqual([row[3] for row in rows[1:]],
                         ["skipped", "skipped", "skipped"])

    def test_partial_run_preserves_other_summary_rows(self):
        self._start_patches()
        FakePatternRunner.behavior = {}
        FakePatternRunner.calls = []
        spec = _spec3()
        units = normalize_units(spec)
        full = BatchRunner(spec, units, self.tmp)
        self.assertEqual(full.run(), 0)
        self.assertEqual(len(_read_tsv(full.summary_path)), 4)

        partial = BatchRunner(
            spec, [u for u in units if u.unit_id == "s2__P1"], self.tmp
        )
        self.assertEqual(partial.run(), 0)
        summary = _read_tsv(partial.summary_path)
        self.assertEqual(len(summary), 4)
        self.assertEqual(
            [row[1] for row in summary[1:]],
            ["s2__P1", "s1__P1", "s3__P1"],
        )


if __name__ == "__main__":
    unittest.main()
