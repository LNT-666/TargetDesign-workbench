import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from email.message import Message
from unittest import mock


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEBAPP = os.path.join(ROOT, "webapp")
SHARED = os.path.join(ROOT, "shared")
for _path in (ROOT, WEBAPP, SHARED):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import app  # noqa: E402
import jobs as job_module  # noqa: E402
import services.batch as batch  # noqa: E402
from design.batch_spec import (  # noqa: E402
    normalize_units,
    scope_input_keys,
    validate_spec,
)
from utils import run_index  # noqa: E402


def designer_snapshot(motif="TTAG", genome="g.fa"):
    return {
        "mode": "single_motif_flank",
        "nuclease": "cas9",
        "tnpb_subtype": "unknown",
        "require_pam": True,
        "active_side": "target",
        "values": {
            "motif": motif,
            "flank": "20",
            "side": "downstream",
            "genome_fasta": genome,
            "mask_fasta": "",
            "engine": "auto",
            "max_mismatch": "4",
            "gc_min": "40",
            "gc_max": "70",
        },
    }


def batch_payload(**overrides):
    payload = dict(designer_snapshot())
    payload.update({
        "batch_label": "web-test-batch",
        "resume": True,
        "scopes": [
            {"scope_id": "s1", "search_fasta": "a.fa"},
            {"scope_id": "s2", "regions": "b.bed"},
        ],
        "patterns": [
            dict(designer_snapshot(), pattern_id="P1"),
        ],
    })
    payload.update(overrides)
    return payload


class ConversionTests(unittest.TestCase):
    def test_pattern_keys_are_derived_from_schema(self):
        self.assertIn("motif", batch.PATTERN_KEYS_BY_MODE["single_motif_flank"])
        self.assertIn("flank", batch.PATTERN_KEYS_BY_MODE["single_motif_flank"])
        self.assertIn("motif_gap_motif", batch.PATTERN_KEYS_BY_MODE)
        self.assertIn("min_gap", batch.PATTERN_KEYS_BY_MODE["motif_gap_motif"])
        self.assertIn("y_sequence", batch.PATTERN_KEYS_BY_MODE["y_centered_motifs"])

    def test_collect_values_prefers_values_block(self):
        payload = {"motif": "AAAA", "values": {"motif": "TTTT"}}
        self.assertEqual(batch.collect_values(payload)["motif"], "TTTT")

    def test_scope_ids_are_derived_and_de_duplicated(self):
        payload = {
            "scopes": [
                {"search_fasta": "/x/a.fa"},
                {"search_fasta": "/y/a.fasta"},
                {"regions": "/z/regions.bed"},
            ]
        }
        scopes = batch.scopes_from_payload(payload)
        self.assertEqual([s.scope_id for s in scopes], ["a", "a_2", "regions"])

    def test_shared_has_no_pattern_keys(self):
        spec = batch.build_spec(batch_payload())
        self.assertEqual(spec.shared["genome_fasta"], "g.fa")
        self.assertEqual(spec.shared["engine"], "auto")
        self.assertIn("nuclease", spec.shared)
        for key in ("motif", "flank", "side", "search_fasta",
                    "bed_regions", "result_label"):
            self.assertNotIn(key, spec.shared)

    def test_overlay_has_only_mode_and_struct_keys(self):
        spec = batch.build_spec(batch_payload())
        overlay = spec.patterns[0].overlay
        self.assertEqual(overlay["motif"], "TTAG")
        self.assertEqual(overlay["flank"], "20")
        self.assertIn("nuclease", overlay)
        self.assertNotIn("genome_fasta", overlay)
        self.assertNotIn("engine", overlay)

    def test_assignments_make_one_group_per_pattern(self):
        payload = batch_payload(
            patterns=[
                dict(designer_snapshot("TTAG"), pattern_id="P1"),
                dict(designer_snapshot("TCAA"), pattern_id="P2"),
            ],
            assignments={"P1": ["s2", "s1"], "P2": ["s1"]},
        )
        spec = batch.build_spec(payload)
        self.assertEqual(
            [group.group_id for group in spec.groups], ["G_P1", "G_P2"]
        )
        units = normalize_units(spec)
        self.assertEqual(
            [unit.unit_id for unit in units],
            ["s2__P1", "s1__P1", "s1__P2"],
        )

    def test_missing_assignment_defaults_to_all_scopes(self):
        spec = batch.build_spec(batch_payload())
        self.assertEqual(spec.groups[0].scope_ids, ["s1", "s2"])

    def test_advanced_groups_are_used(self):
        payload = batch_payload(
            groups=[
                {
                    "group_id": "G1",
                    "scope_ids": ["s1"],
                    "pattern_ids": ["P1"],
                }
            ]
        )
        spec = batch.build_spec(payload)
        self.assertEqual(len(spec.groups), 1)
        self.assertEqual(spec.groups[0].scope_ids, ["s1"])

    def test_default_batch_label(self):
        payload = batch_payload()
        payload.pop("batch_label")
        spec = batch.build_spec(payload)
        self.assertTrue(spec.batch_label.startswith("web-batch-"))

    def test_structural_errors_raise(self):
        with self.assertRaises(ValueError):
            batch.build_spec(batch_payload(scopes=[]))
        with self.assertRaises(ValueError):
            batch.build_spec(batch_payload(patterns=[]))
        with self.assertRaises(ValueError):
            batch.build_spec(batch_payload(patterns=[
                {"pattern_id": "P1", "mode": "nope", "overlay": {}}
            ]))
        with self.assertRaises(ValueError):
            batch.build_spec(batch_payload(
                assignments={"P1": ["missing"]}
            ))

    def test_reserved_overlay_key_is_a_validation_error(self):
        payload = batch_payload(patterns=[
            {
                "pattern_id": "P1",
                "mode": "single_motif_flank",
                "overlay": {"motif": "TTAG", "output_dir": "/tmp/x"},
            }
        ])
        errors, _warnings = validate_spec(batch.build_spec(payload), dry_run=True)
        self.assertTrue(
            any("output_dir" in message for message in errors), errors
        )

    def test_missing_pattern_id_uses_default_name(self):
        payload = batch_payload(patterns=[
            {
                "mode": "single_motif_flank",
                "overlay": {"motif": "TTAG"},
            }
        ])
        patterns = batch.patterns_from_payload(payload)
        self.assertEqual([item.pattern_id for item in patterns], ["TTAG"])

    def test_auto_generated_ids_are_deduplicated(self):
        payload = batch_payload(patterns=[
            designer_snapshot("TTAG"),
            designer_snapshot("TTAG"),
        ])
        patterns = batch.patterns_from_payload(payload)
        self.assertEqual(
            [item.pattern_id for item in patterns], ["TTAG", "TTAG_2"]
        )

    def test_auto_generated_id_avoids_an_explicit_existing_id(self):
        payload = batch_payload(patterns=[
            {
                "pattern_id": "TTAG",
                "mode": "single_motif_flank",
                "overlay": {"motif": "TCAA"},
            },
            {
                "mode": "single_motif_flank",
                "overlay": {"motif": "TTAG"},
            },
        ])
        patterns = batch.patterns_from_payload(payload)
        self.assertEqual(
            [item.pattern_id for item in patterns], ["TTAG", "TTAG_2"]
        )

    def test_explicit_duplicate_pattern_id_still_raises(self):
        payload = batch_payload(patterns=[
            {
                "pattern_id": "custom",
                "mode": "single_motif_flank",
                "overlay": {"motif": "TTAG"},
            },
            {
                "pattern_id": "custom",
                "mode": "single_motif_flank",
                "overlay": {"motif": "TCAA"},
            },
        ])
        with self.assertRaisesRegex(
            ValueError, "duplicate pattern_id: custom"
        ):
            batch.patterns_from_payload(payload)

    def test_explicit_pattern_id_is_not_rewritten(self):
        payload = batch_payload(patterns=[
            {
                "pattern_id": "My.Pattern-1",
                "mode": "single_motif_flank",
                "overlay": {"motif": "TTAG"},
            }
        ])
        patterns = batch.patterns_from_payload(payload)
        self.assertEqual(patterns[0].pattern_id, "My.Pattern-1")


    def test_scopes_parse_scope_level_mask(self):
        payload = {
            "scopes": [
                {"scope_id": "s1", "search_fasta": "a.fa",
                 "mask_same_as_target": True},
                {"scope_id": "s2", "search_fasta": "b.fa",
                 "mask_fasta": "b_mask.fa"},
            ]
        }
        scopes = batch.scopes_from_payload(payload)
        self.assertTrue(scopes[0].mask_same_as_target)
        self.assertEqual(scopes[0].mask_fasta, "")
        self.assertEqual(scopes[1].mask_fasta, "b_mask.fa")
        self.assertFalse(scopes[1].mask_same_as_target)

    def test_shared_drops_mask_keys(self):
        spec = batch.build_spec(batch_payload())
        self.assertNotIn("mask_fasta", spec.shared)
        self.assertNotIn("mask_same_as_target", spec.shared)

    def test_batch_scope_masks_are_isolated_end_to_end(self):
        payload = batch_payload(scopes=[
            {"scope_id": "A", "search_fasta": "a.fa",
             "mask_same_as_target": True},
            {"scope_id": "B", "search_fasta": "b.fa",
             "mask_fasta": "mask_b.fa"},
        ])
        spec = batch.build_spec(payload)
        by_id = {scope.scope_id: scope for scope in spec.scopes}
        self.assertTrue(by_id["A"].mask_same_as_target)
        self.assertEqual(by_id["A"].mask_fasta, "")
        self.assertEqual(by_id["B"].mask_fasta, "mask_b.fa")
        self.assertFalse(by_id["B"].mask_same_as_target)
        self.assertNotIn("mask_fasta", spec.shared)
        self.assertNotIn("mask_same_as_target", spec.shared)

    def test_scope_mask_conflict_is_a_validation_error(self):
        payload = batch_payload(scopes=[
            {"scope_id": "A", "search_fasta": "a.fa",
             "mask_fasta": "m.fa", "mask_same_as_target": True},
        ])
        errors, _warnings = validate_spec(
            batch.build_spec(payload), dry_run=True
        )
        self.assertTrue(
            any("mask_fasta and mask_same_as_target" in m for m in errors),
            errors,
        )

    def test_scope_mask_can_be_explicitly_disabled(self):
        payload = {
            "scopes": [
                {"scope_id": "s1", "search_fasta": "a.fa",
                 "mask_fasta": "", "mask_same_as_target": False},
            ]
        }
        scopes = batch.scopes_from_payload(payload)
        self.assertEqual(scopes[0].mask_fasta, "")
        self.assertFalse(scopes[0].mask_same_as_target)
        self.assertEqual(
            scope_input_keys(scopes[0]),
            {
                "input_mode": "sequence",
                "search_fasta": "a.fa",
                "mask_same_as_target": False,
            },
        )


class PreviewTests(unittest.TestCase):
    def test_preview_missing_files_are_warnings(self):
        result = batch.preview(batch_payload())
        self.assertEqual(result["errors"], [])
        self.assertTrue(result["warnings"])
        self.assertEqual(
            [unit["unit_id"] for unit in result["units"]], ["s1__P1", "s2__P1"]
        )

    def test_preview_invalid_label_is_an_error(self):
        result = batch.preview(batch_payload(batch_label="../evil"))
        self.assertTrue(result["errors"])
        self.assertEqual(result["batch_root"], "")

    def test_preview_bad_structure_returns_error(self):
        result = batch.preview(batch_payload(scopes=[]))
        self.assertTrue(result["errors"])
        self.assertEqual(result["units"], [])


class SubmitTests(unittest.TestCase):
    def test_submit_validation_error_raises(self):
        manager = mock.Mock()
        with self.assertRaises(ValueError):
            batch.submit(batch_payload(), manager)
        manager.create_job.assert_not_called()

    def test_submit_queues_a_batch_job(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name in ("a.fa", "b.bed", "g.fa"):
                open(os.path.join(tmp, name), "w", encoding="utf-8").close()
            payload = batch_payload(scopes=[
                {"scope_id": "s1", "search_fasta": os.path.join(tmp, "a.fa")},
                {"scope_id": "s2", "regions": os.path.join(tmp, "b.bed")},
            ])
            payload["values"] = {"genome_fasta": os.path.join(tmp, "g.fa")}
            manager = mock.Mock()
            manager.create_job.return_value = "abcdefabcdef"
            with mock.patch.object(
                batch, "default_output_dir", return_value=tmp
            ):
                result = batch.submit(payload, manager)
        self.assertEqual(manager.create_job.call_args[0][0], "batch")
        params = manager.create_job.call_args[0][3]
        self.assertEqual(params["batch_label"], "web-test-batch")
        self.assertRegex(params["run_id"], r"^\d{8}-\d{4}$")
        self.assertEqual(
            params["batch_root"], os.path.join(tmp, params["run_id"])
        )
        self.assertEqual(params["unit_count"], 2)
        self.assertEqual(result["job_id"], "abcdefabcdef")
        self.assertEqual(result["run_id"], params["run_id"])
        self.assertEqual(result["unit_count"], 2)
        self.assertIn("2 units", result["title"])


class FakeBatchRunner:
    last = None
    returncode = 0

    def __init__(
        self, spec, units, batch_root_dir, on_line=None, resume=True,
        run_meta=None,
    ):
        self.spec = spec
        self.units = units
        self.batch_root_dir = batch_root_dir
        self.on_line = on_line
        self.resume = resume
        self.run_meta = run_meta
        self.manifest_path = os.path.join(batch_root_dir, "manifest.tsv")
        self.summary_path = os.path.join(
            batch_root_dir, "summary", "batch_scores.tsv"
        )
        self.log_path = os.path.join(batch_root_dir, "run.log")
        self.stopped = False
        FakeBatchRunner.last = self

    def stop(self):
        self.stopped = True

    def run(self):
        os.makedirs(os.path.dirname(self.summary_path), exist_ok=True)
        with open(self.manifest_path, "w", encoding="utf-8", newline="") as handle:
            handle.write(
                "unit_id\tscope_id\tpattern_id\tstatus\treturncode\t"
                "started\tfinished\tunit_dir\tmain_table\tmessage\n"
            )
            handle.write("s1__P1\ts1\tP1\tok\t0\t\t\t\t\t\n")
        with open(self.summary_path, "w", encoding="utf-8", newline="") as handle:
            handle.write("batch_id\tunit_id\tqid\nweb-test-batch\ts1__P1\tq\n")
        if self.on_line:
            self.on_line("PROGRESS_TARGET: 1/1")
        return FakeBatchRunner.returncode


class JobBodyTests(unittest.TestCase):
    def _run(self, returncode=0):
        tmp = tempfile.mkdtemp()
        job_dir = os.path.join(tmp, "job")
        workdir = os.path.join(tmp, "work")
        os.makedirs(job_dir, exist_ok=True)
        FakeBatchRunner.returncode = returncode
        ctx = mock.Mock(job_dir=job_dir)
        payload = batch_payload()
        with mock.patch.object(batch, "BatchRunner", FakeBatchRunner):
            body = batch.job_body(payload, workdir)
            result = body(ctx)
        return result, ctx, job_dir

    def test_job_body_wires_runner_artifacts_and_outputs(self):
        result, ctx, job_dir = self._run()
        self.assertEqual(result, 0)
        ctx.set_stop_hook.assert_called_once_with(FakeBatchRunner.last.stop)
        self.assertIs(FakeBatchRunner.last.on_line, ctx.line)
        self.assertTrue(
            os.path.isfile(os.path.join(job_dir, "export", "manifest.tsv"))
        )
        self.assertTrue(
            os.path.isfile(
                os.path.join(job_dir, "export", "batch_scores.tsv")
            )
        )
        result_payload = ctx.set_result.call_args[0][0]
        self.assertEqual(result_payload["units_total"], 1)
        self.assertEqual(result_payload["units_ok"], 1)
        self.assertEqual(result_payload["units_failed"], 0)
        self.assertEqual(result_payload["returncode"], 0)
        outputs = ctx.set_outputs.call_args[0][0]
        for key in ("batch_root", "run_dir", "manifest", "summary", "log",
                    "download_manifest", "download_summary", "download_log"):
            self.assertIn(key, outputs)
        self.assertEqual(outputs["run_dir"], outputs["batch_root"])
        self.assertEqual(outputs["download_manifest"], "export/manifest.tsv")
        self.assertEqual(outputs["download_summary"], "export/batch_scores.tsv")

    def test_job_body_passes_the_returncode_through(self):
        result, _ctx, _job_dir = self._run(returncode=3)
        self.assertEqual(result, 3)


class BatchRunLookupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.run = run_index.allocate_run(self.tmp)
        run_index.write_meta(self.run.path, {
            "run_id": self.run.run_id,
            "day": self.run.day,
            "label": self.run.label,
            "batch_label": "lookup-test",
            "created": "2026-10-06 09:30:00",
            "unit_count": 2,
        })
        with open(
            os.path.join(self.run.path, "manifest.tsv"),
            "w", encoding="utf-8", newline="",
        ) as handle:
            handle.write(
                "unit_id\tscope_id\tpattern_id\tstatus\treturncode\t"
                "started\tfinished\tunit_dir\tmain_table\tmessage\n"
            )
            handle.write("s1__P1\ts1\tP1\tok\t0\t\t\t\t\t\n")
            handle.write("s2__P1\ts2\tP1\tfailed\t1\t\t\t\t\tboom\n")
        with open(run_index.log_path(self.run.path), "w", encoding="utf-8") as handle:
            handle.write("hello\n")
        os.makedirs(os.path.join(self.run.path, "summary"), exist_ok=True)
        with open(
            os.path.join(self.run.path, "summary", "batch_scores.tsv"),
            "w", encoding="utf-8",
        ) as handle:
            handle.write("qid\n")
        self._patch = mock.patch.object(
            batch, "default_output_dir", return_value=self.tmp
        )
        self._patch.start()
        self.addCleanup(self._patch.stop)

    def test_run_detail_reports_manifest_and_files(self):
        data = batch.run_detail(self.run.label)
        self.assertEqual(data["run_id"], self.run.label)
        self.assertEqual(data["batch_label"], "lookup-test")
        self.assertEqual(data["unit_count"], 2)
        self.assertEqual(data["units"]["ok"], 1)
        self.assertEqual(data["units"]["failed"], 1)
        names = [item["name"] for item in data["files"]]
        self.assertIn("manifest.tsv", names)
        self.assertIn("run.log", names)
        self.assertIn("summary/batch_scores.tsv", names)
        self.assertEqual(
            data["columns"],
            ["unit_id", "scope_id", "pattern_id", "status", "returncode"],
        )
        self.assertEqual(
            [row["unit_id"] for row in data["rows"]], ["s1__P1", "s2__P1"]
        )
        self.assertEqual(data["rows"][0]["status"], "ok")
        self.assertEqual(data["rows"][0]["returncode"], "0")
        self.assertEqual(data["rows"][1]["status"], "failed")

    def test_run_detail_without_manifest_has_no_rows(self):
        os.remove(os.path.join(self.run.path, "manifest.tsv"))
        data = batch.run_detail(self.run.label)
        self.assertEqual(data["rows"], [])
        self.assertEqual(data["units"]["total"], 0)

    def test_manifest_rows_reads_statuses_and_survives_missing(self):
        rows = batch.manifest_rows(os.path.join(self.run.path, "manifest.tsv"))
        self.assertEqual([row["status"] for row in rows], ["ok", "failed"])
        self.assertEqual(batch.manifest_rows(os.path.join(self.run.path, "nope.tsv")), [])

    def test_run_detail_accepts_a_bare_id(self):
        data = batch.run_detail(self.run.run_id)
        self.assertEqual(data["run_id"], self.run.label)

    def test_run_detail_missing_raises_not_found(self):
        with self.assertRaises(FileNotFoundError):
            batch.run_detail("9999")

    def test_list_runs_newest_first(self):
        data = batch.list_runs(limit=5)
        self.assertEqual(data["output_root"], self.tmp)
        self.assertEqual([item["run_id"] for item in data["runs"]], [self.run.label])

    def test_run_file_path_rejects_escapes(self):
        path = batch.run_file_path(self.run.label, "manifest.tsv")
        self.assertTrue(os.path.isfile(path))
        for bad in ("", "..\\outside.txt", "../outside.txt", "summary/../../x"):
            with self.assertRaises(ValueError):
                batch.run_file_path(self.run.label, bad)
        with self.assertRaises(FileNotFoundError):
            batch.run_file_path(self.run.label, "summary/nope.tsv")


class RouteTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="webapp_batch_")
        self.addCleanup(self.tmp.cleanup)
        self.manager = job_module.JobManager(
            jobs_root=os.path.join(self.tmp.name, "jobs")
        )
        app.set_manager(self.manager)
        self.addCleanup(app.set_manager, None)

    def call(self, path, method="GET", body=None):
        raw = b"" if body is None else json.dumps(body).encode("utf-8")
        handler = object.__new__(app.Handler)
        handler.path = path
        handler.rfile = io.BytesIO(raw)
        handler.wfile = io.BytesIO()
        handler.headers = Message()
        handler.headers["Content-Length"] = str(len(raw))
        calls = []

        def record_json(payload, status=200):
            calls.append(("json", status, payload))

        def record_bytes(data, ctype, status=200, headers=None):
            calls.append(("bytes", status, data, ctype, headers))

        handler._send_json = record_json
        handler._send_bytes = record_bytes
        bound = app.Handler.do_POST if method == "POST" else app.Handler.do_GET
        bound.__get__(handler, app.Handler)()
        return calls


class RouteTests(RouteTestCase):
    def test_batch_preview_route(self):
        with mock.patch.object(
            app.batch,
            "preview",
            return_value={"batch_label": "b", "units": [], "errors": [],
                          "warnings": []},
        ) as preview:
            calls = self.call("/api/batch/preview", method="POST", body={})
        self.assertEqual(calls[0][0], "json")
        self.assertEqual(calls[0][1], 200)
        self.assertIn("units", calls[0][2])
        preview.assert_called_once()

    def test_batch_jobs_route_success(self):
        with mock.patch.object(
            app.batch, "submit", return_value={"job_id": "abcdefabcdef"}
        ) as submit:
            calls = self.call("/api/batch/jobs", method="POST", body={})
        self.assertEqual(calls[0][0], "json")
        self.assertEqual(calls[0][1], 200)
        self.assertEqual(calls[0][2]["job_id"], "abcdefabcdef")
        submit.assert_called_once()

    def test_batch_jobs_route_value_error_is_400(self):
        with mock.patch.object(
            app.batch, "submit", side_effect=ValueError("bad batch")
        ):
            calls = self.call("/api/batch/jobs", method="POST", body={})
        self.assertEqual(calls[0][0], "json")
        self.assertEqual(calls[0][1], 400)

    def test_index_page_has_batch_ids(self):
        calls = self.call("/")
        html = calls[0][2].decode("utf-8")
        for element_id in (
            "batch-wrap",
            "batch-label",
            "batch-resume",
            "batch-scope-add",
            "batch-scope-table",
            "batch-pattern-id",
            "batch-pattern-scopes",
            "batch-pattern-add",
            "batch-pattern-table",
            "batch-preview",
            "batch-units",
            "batch-preview-note",
            "batch-run",
            "batch-job-box",
            "batch-artifacts",
            "batch-code-group",
            "batch-current-code",
            "batch-code-copy",
            "batch-code-input",
            "batch-code-load",
            "batch-code-recent",
            "batch-run-list",
            "batch-runs-table",
            "batch-run-detail",
            "batch-run-files",
        ):
            self.assertIn('id="%s"' % element_id, html)
        self.assertIn("<th>Applies to</th>", html)

    def test_app_js_calls_init_batch(self):
        calls = self.call("/static/app.js")
        script = calls[0][2].decode("utf-8")
        self.assertIn("initBatch();", script)
        self.assertIn("function initBatch()", script)
        self.assertIn("loadBatchRun", script)
        self.assertIn("/api/batch/runs/", script)
        self.assertIn("renderBatchRunRows", script)
        self.assertIn("renderRunArtifacts", script)
        self.assertIn("renderArtifactButtons", script)
        self.assertIn("RUN_EXPORT_FILES", script)

    def test_index_has_batch_mask_column(self):
        calls = self.call("/")
        html = calls[0][2].decode("utf-8")
        self.assertIn("<th>Mask</th>", html)

    def test_app_js_emits_scope_mask_payload(self):
        calls = self.call("/static/app.js")
        script = calls[0][2].decode("utf-8")
        self.assertIn("mask_same_as_target", script)
        self.assertIn("mask_fasta", script)
        self.assertIn("Same as scope", script)
        self.assertIn("mask_same_as_target = false", script)

    def test_app_js_derives_missing_scope_ids(self):
        calls = self.call("/static/app.js")
        script = calls[0][2].decode("utf-8")
        self.assertIn("batchEffectiveScopeIds", script)
        self.assertIn("batchDeriveScopeId", script)
        self.assertIn("scope_id: scopeIds[index]", script)

    def test_app_js_applies_presets_on_selection(self):
        """Selecting a System Preset must apply it immediately (nuclease
        included), so a TnpB side can never keep the SpCas9 nuclease until
        the user presses ``Apply``."""
        calls = self.call("/static/app.js")
        script = calls[0][2].decode("utf-8")
        self.assertIn("applySidePreset(side, {activate: false})", script)
        self.assertIn("/api/designer/preset", script)


class BatchRunRouteTests(RouteTestCase):
    def test_runs_list_route(self):
        payload = {"output_root": "/tmp/out", "runs": [{"run_id": "20261006-0114"}]}
        with mock.patch.object(
            app.batch, "list_runs", return_value=payload
        ) as called:
            calls = self.call("/api/batch/runs?limit=5")
        self.assertEqual(calls[0][0], "json")
        self.assertEqual(calls[0][1], 200)
        self.assertEqual(calls[0][2], payload)
        called.assert_called_once_with(limit="5", day=None)

    def test_run_detail_route(self):
        with mock.patch.object(
            app.batch, "run_detail", return_value={"run_id": "20261006-0114"}
        ) as called:
            calls = self.call("/api/batch/runs/20261006-0114")
        self.assertEqual(calls[0][1], 200)
        self.assertEqual(calls[0][2]["run_id"], "20261006-0114")
        called.assert_called_once_with("20261006-0114")

    def test_run_detail_missing_is_404(self):
        with mock.patch.object(
            app.batch, "run_detail", side_effect=FileNotFoundError("no run")
        ):
            calls = self.call("/api/batch/runs/9999")
        self.assertEqual(calls[0][1], 404)

    def test_run_download_route(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "manifest.tsv")
            with open(path, "w", encoding="utf-8", newline="") as handle:
                handle.write("a\tb\n")
            with mock.patch.object(
                app.batch, "run_file_path", return_value=path
            ) as called:
                calls = self.call(
                    "/api/batch/runs/20261006-0114/download?file=manifest.tsv"
                )
        self.assertEqual(calls[0][0], "bytes")
        self.assertEqual(calls[0][1], 200)
        self.assertEqual(calls[0][2], b"a\tb\n")
        called.assert_called_once_with("20261006-0114", "manifest.tsv")

    def test_run_download_escape_is_400(self):
        with mock.patch.object(
            app.batch, "run_file_path", side_effect=ValueError("invalid file")
        ):
            calls = self.call(
                "/api/batch/runs/20261006-0114/download?file=../x"
            )
        self.assertEqual(calls[0][1], 400)


if __name__ == "__main__":
    unittest.main()
