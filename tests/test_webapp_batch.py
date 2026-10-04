import io
import json
import os
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
from design.batch_spec import normalize_units, validate_spec  # noqa: E402


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
            result = batch.submit(payload, manager)
        self.assertEqual(manager.create_job.call_args[0][0], "batch")
        params = manager.create_job.call_args[0][3]
        self.assertEqual(params["batch_label"], "web-test-batch")
        self.assertTrue(params["batch_root"].endswith("web-test-batch"))
        self.assertEqual(params["unit_count"], 2)
        self.assertEqual(result["job_id"], "abcdefabcdef")
        self.assertEqual(result["unit_count"], 2)
        self.assertIn("2 units", result["title"])


class FakeBatchRunner:
    last = None
    returncode = 0

    def __init__(self, spec, units, batch_root_dir, on_line=None, resume=True):
        self.spec = spec
        self.units = units
        self.batch_root_dir = batch_root_dir
        self.on_line = on_line
        self.resume = resume
        self.manifest_path = os.path.join(batch_root_dir, "manifest.tsv")
        self.summary_path = os.path.join(
            batch_root_dir, "summary", "batch_scores.tsv"
        )
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
        with mock.patch.object(batch, "BatchRunner", FakeBatchRunner), \
                mock.patch.object(batch, "batch_root", return_value=workdir):
            body = batch.job_body(payload)
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
        for key in ("batch_root", "manifest", "summary",
                    "download_manifest", "download_summary"):
            self.assertIn(key, outputs)
        self.assertEqual(outputs["download_manifest"], "export/manifest.tsv")
        self.assertEqual(outputs["download_summary"], "export/batch_scores.tsv")

    def test_job_body_passes_the_returncode_through(self):
        result, _ctx, _job_dir = self._run(returncode=3)
        self.assertEqual(result, 3)


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
            "batch-pattern-add",
            "batch-pattern-table",
            "batch-preview",
            "batch-units",
            "batch-preview-note",
            "batch-run",
            "batch-job-box",
            "batch-artifacts",
        ):
            self.assertIn('id="%s"' % element_id, html)

    def test_app_js_calls_init_batch(self):
        calls = self.call("/static/app.js")
        script = calls[0][2].decode("utf-8")
        self.assertIn("initBatch();", script)
        self.assertIn("function initBatch()", script)


if __name__ == "__main__":
    unittest.main()
