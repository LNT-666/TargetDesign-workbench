#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the local web workbench: jobs, services and HTTP routes.

Everything here is mock-based: no browser, no real child process and no
network. The routes are exercised through ``object.__new__(app.Handler)`` so
the request/response plumbing can be checked without opening a socket.
"""

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
import design.workbench_form as workbench_form  # noqa: E402
import jobs as job_module  # noqa: E402
import schema as schema_module  # noqa: E402
import scoring.model_registry as model_registry  # noqa: E402
import services.dataprep as dataprep  # noqa: E402
import services.designer as designer  # noqa: E402
import services.models as models_service  # noqa: E402
from design.pattern_spec import PatternKind  # noqa: E402
from utils.paths import default_output_dir, default_resource_dir  # noqa: E402


def write_file(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)
    return path


class JobManagerTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="webapp_jobs_")
        self.addCleanup(self.tmp.cleanup)
        self.jobs_root = os.path.join(self.tmp.name, "jobs")
        self.manager = job_module.JobManager(jobs_root=self.jobs_root)

    def start(self, runner, kind="dataprep", title="Test job", params=None,
              timeout=30.0):
        job_id = self.manager.create_job(kind, title, runner, params)
        status = self.manager.wait(job_id, timeout=timeout)
        self.assertIsNotNone(status, "job %s did not finish" % job_id)
        return job_id, status


class JobManagerTests(JobManagerTestCase):
    def test_create_job_records_params_status_log_and_result(self):
        def runner(ctx):
            ctx.line("PROGRESS_TARGET: 1/2")
            ctx.line("PROGRESS: scoring 50")
            ctx.set_result({"written": 3})
            return 0

        job_id, status = self.start(runner, params={"genome": "g.fa"})
        self.assertRegex(job_id, r"^[a-z0-9-]{12}$")
        self.assertEqual(status["status"], "succeeded")
        self.assertEqual(status["kind"], "dataprep")
        self.assertEqual(status["title"], "Test job")
        self.assertEqual(status["progress"], 100)
        self.assertEqual(self.manager.job_params(job_id)["genome"], "g.fa")

        job = self.manager.get_job(job_id)
        self.assertEqual(job["result"], {"written": 3})
        self.assertIn("PROGRESS_TARGET: 1/2", job["log_tail"])
        self.assertIn("PROGRESS: scoring 50", job["log_tail"])
        self.assertEqual(job["message"], "Complete")
        self.assertTrue(os.path.isdir(os.path.join(self.jobs_root, job_id, "out")))

    def test_progress_target_line_only_touches_the_message(self):
        seen = {}

        def runner(ctx):
            ctx.line("PROGRESS_TARGET: 3/9")
            seen["message"] = self.manager.get_job(ctx.job_id)["message"]
            seen["progress"] = self.manager.get_job(ctx.job_id)["progress"]
            return 0

        _job_id, status = self.start(runner)
        self.assertEqual(seen["message"], "Analyzing target 3/9")
        self.assertEqual(seen["progress"], 2)
        self.assertEqual(status["message"], "Complete")

    def test_failing_runner_is_recorded(self):
        def runner(ctx):
            raise RuntimeError("boom")

        job_id, status = self.start(runner)
        self.assertEqual(status["status"], "failed")
        self.assertIn("boom", status["message"])
        self.assertEqual(status["returncode"], 1)
        self.assertIn("ERROR: boom", self.manager.get_job(job_id)["log_tail"])

    def test_nonzero_return_code_fails_the_job(self):
        _job_id, status = self.start(lambda ctx: 2)
        self.assertEqual(status["status"], "failed")
        self.assertIn("return code 2", status["message"])

    def test_request_stop_marks_the_job_cancelled(self):
        def runner(ctx):
            ctx.request_stop()
            return 0

        _job_id, status = self.start(runner)
        self.assertEqual(status["status"], "cancelled")

    def test_cancel_and_lookup_of_unknown_jobs(self):
        self.assertIsNone(self.manager.cancel("aaaaaaaaaaaa"))
        self.assertIsNone(self.manager.get_job("aaaaaaaaaaaa"))
        with self.assertRaises(ValueError):
            self.manager.job_dir("not-an-id")

    def test_list_jobs_newest_first_and_read_log_offsets(self):
        def runner(ctx):
            ctx.line("hello")
            return 0

        first, _ = self.start(runner)
        second, _ = self.start(runner)
        jobs = self.manager.list_jobs()
        ids = [item["job_id"] for item in jobs]
        self.assertEqual(sorted(ids), sorted([first, second]))
        expected = [item["job_id"] for item in sorted(
            jobs, key=lambda item: (item.get("created") or "", item["job_id"]),
            reverse=True)]
        self.assertEqual(ids, expected)

        chunk = self.manager.read_log(second, 0)
        self.assertEqual(chunk["text"], "hello\n")
        self.assertEqual(chunk["offset"], len("hello\n"))
        empty = self.manager.read_log(second, chunk["offset"])
        self.assertEqual(empty["text"], "")
        self.assertEqual(empty["offset"], chunk["offset"])
        clamped = self.manager.read_log(second, 9999)
        self.assertEqual(clamped["text"], "")
        self.assertEqual(clamped["offset"], len("hello\n"))

    def test_read_log_ignores_bad_offsets(self):
        job_id, _ = self.start(lambda ctx: 0)
        self.assertEqual(self.manager.read_log(job_id, -5)["offset"], 0)
        self.assertEqual(self.manager.read_log(job_id, "junk")["offset"], 0)

    def test_interrupted_recovery_ignores_legacy_job_dirs(self):
        running = os.path.join(self.jobs_root, "aaaaaaaaaaaa")
        write_file(os.path.join(running, "status.json"), json.dumps({
            "job_id": "aaaaaaaaaaaa", "kind": "dataprep",
            "status": "running", "progress": 42,
        }))
        legacy = os.path.join(self.jobs_root, "87499fe93868")
        write_file(os.path.join(legacy, "status.json"), json.dumps({
            "job_id": "87499fe93868", "status": "done", "progress": 100,
        }))
        os.makedirs(os.path.join(self.jobs_root, "BAD-ID"), exist_ok=True)

        manager = job_module.JobManager(jobs_root=self.jobs_root)
        self.assertEqual(
            manager.read_status(running)["status"], job_module.INTERRUPTED)
        self.assertEqual(
            manager.read_status(running)["message"],
            job_module.INTERRUPTED_MESSAGE)
        self.assertIsNone(manager.read_status(legacy))
        self.assertEqual([job["job_id"] for job in manager.list_jobs()],
                         ["aaaaaaaaaaaa"])
        self.assertEqual(manager.mark_interrupted_jobs(), 0)

    def test_mark_interrupted_only_touches_active_statuses(self):
        done = os.path.join(self.jobs_root, "bbbbbbbbbbbb")
        write_file(os.path.join(done, "status.json"), json.dumps({
            "job_id": "bbbbbbbbbbbb", "kind": "model",
            "status": "succeeded", "progress": 100,
        }))
        self.assertEqual(self.manager.mark_interrupted_jobs(), 0)
        self.assertEqual(self.manager.read_status(done)["status"], "succeeded")


class ProgressLineTests(unittest.TestCase):
    def test_target_lines(self):
        self.assertEqual(
            job_module.parse_progress_line("PROGRESS_TARGET: 4/10"),
            ("target", "4/10"))
        self.assertIsNone(job_module.parse_progress_line("PROGRESS_TARGET: x/10"))

    def test_progress_lines(self):
        self.assertEqual(
            job_module.parse_progress_line("PROGRESS: scoring candidates 40"),
            ("progress", 40, "scoring candidates"))
        self.assertIsNone(job_module.parse_progress_line("PROGRESS: 40"))

    def test_other_lines_are_ignored(self):
        for line in ("", "hello", "PROGRESS:", "PROGRESS: label abc",
                     "PROGRESS: 40"):
            self.assertIsNone(job_module.parse_progress_line(line))

class SchemaTests(unittest.TestCase):
    def setUp(self):
        self.doc = schema_module.build_schema()

    def test_engine_and_format_lists_come_from_shared(self):
        self.assertEqual(self.doc["engines"], list(schema_module.ENGINE_CHOICES))
        self.assertEqual(
            self.doc["export_formats"], list(schema_module.SUPPORTED_FORMATS))
        self.assertEqual(self.doc["hidden_candidate_columns"],
                         ["query_seq", "gap_seq"])

    def test_modes_and_presets(self):
        modes = [item["value"] for item in self.doc["modes"]]
        self.assertEqual(modes, [kind.value for kind in PatternKind])
        presets = {item["value"] for item in self.doc["presets"]}
        self.assertIn("cas9", presets)
        self.assertIn("cas12a", presets)
        for item in self.doc["presets"]:
            self.assertIn("spacer_len", item)
            self.assertIn("pam_required", item)

    def test_model_labels_match_the_shared_display_names(self):
        labels = self.doc["model_labels"]
        expected_keys = set()
        for preset_key in workbench_form.PRESET_KEYS:
            options = workbench_form.side_model_options(preset_key)
            expected_keys.update(options["on_target"])
            expected_keys.update(options["off_target"])
        self.assertEqual(set(labels), expected_keys)
        for key, label in labels.items():
            self.assertEqual(label, workbench_form.model_display_name(key), key)
        self.assertEqual(labels["cropsr"], "[Cas9] cropsr")
        self.assertEqual(labels["cfd"], "[Cas9] [rule] cfd")
        self.assertIn("[General] [rule] rules", labels.values())

    def test_pattern_form_field_keys_exist(self):
        designer_doc = self.doc["designer"]
        known = set(designer_doc["field_keys"])
        for form in designer_doc["pattern_forms"].values():
            for group in form.values():
                for field in group["fields"]:
                    if field["type"] in ("side_preset", "use_for_run",
                                         "side_models"):
                        continue
                    self.assertIn(field["key"], known)
        self.assertTrue(set(designer_doc["defaults"]).issubset(known))

    def test_dataprep_choices(self):
        dataprep_doc = self.doc["dataprep"]
        self.assertTrue(dataprep_doc["species"])
        self.assertIn("Coding region", dataprep_doc["region_types"])
        self.assertIn("gene_name", dataprep_doc["id_types"])
        self.assertTrue(dataprep_doc["output_dir"])
        self.assertEqual(dataprep_doc["output_dir"], default_output_dir())
        self.assertTrue(dataprep_doc["resource_dir"])
        self.assertEqual(dataprep_doc["resource_dir"], default_resource_dir())

    def test_path_fields_carry_a_browse_kind(self):
        designer_doc = self.doc["designer"]
        fields = list(designer_doc["common_fields"]) + list(
            designer_doc["run_fields"])
        seen = set()
        for field in fields:
            if field["type"] not in ("file", "dir"):
                continue
            seen.add(field["key"])
            self.assertIn("kind", field, field["key"])
            self.assertIn(field["kind"], schema_module.FS_KINDS, field["key"])
        self.assertEqual(seen, {"search_fasta", "bed_regions", "genome_fasta",
                                "mask_fasta", "blastdb", "annotation",
                                "index_path"})


class DesignerFormTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="webapp_designer_")
        self.addCleanup(self.tmp.cleanup)
        self.output_dir = os.path.join(self.tmp.name, "out")
        os.makedirs(self.output_dir, exist_ok=True)
        self.search_fasta = write_file(
            os.path.join(self.tmp.name, "target.fa"), ">t1\n" + "ACGT" * 20 + "\n")
        self.genome_fasta = write_file(
            os.path.join(self.tmp.name, "genome.fa"), ">chr1\n" + "ACGT" * 100 + "\n")

    def payload(self, **overrides):
        values = {
            "search_fasta": self.search_fasta,
            "genome_fasta": self.genome_fasta,
            "output_dir": self.output_dir,
            "motif": "TTAT",
            "flank": "5",
            "side": "upstream",
        }
        values.update(overrides)
        return {"active_side": "target", "values": values}


class DesignerServiceTests(DesignerFormTestCase):
    def test_preview_reports_missing_inputs(self):
        result = designer.preview({})
        self.assertEqual(result["describe"], "")
        self.assertIn("Search FASTA is required", result["errors"])
        self.assertEqual(result["mode"], "single_motif_flank")
        self.assertEqual(result["pattern_name"], "")

    def test_preview_describes_a_valid_pattern(self):
        result = designer.preview(self.payload())
        self.assertEqual(result["errors"], [])
        self.assertTrue(result["describe"])
        self.assertEqual(result["pattern_name"], "TTAT")
        self.assertTrue(result["run_label"])

    def test_preset_and_active_side_updates(self):
        result = designer.preset_update({"side": "target", "preset": "cas12a"})
        self.assertEqual(result["updates"]["motif"], "TTTN")
        self.assertIn("rules", result["models"]["on_target"])
        side = designer.active_side_update(
            dict(self.payload(), active_side="target"))
        self.assertEqual(side["side"], "target")
        self.assertIn("require_pam", side["updates"])
        with self.assertRaises(ValueError):
            designer.preset_update({"side": "middle", "preset": "cas9"})

    def test_build_runner_matches_the_shared_form_layer(self):
        runner = designer.build_runner(self.payload())
        self.assertEqual(runner.config.output_dir, default_output_dir())
        self.assertEqual(runner.config.search_fasta, self.search_fasta)
        self.assertEqual(runner.config.mode, "preset")

    def test_submit_rejects_bad_stage_and_bad_policy(self):
        manager = mock.Mock()
        with self.assertRaises(ValueError):
            designer.submit({"stage": "nope"}, manager)
        with self.assertRaises(ValueError):
            designer.submit(
                dict(self.payload(), stage="find", confirm_policy="maybe"),
                manager)
        manager.create_job.assert_not_called()

    def test_submit_rejects_incomplete_forms(self):
        manager = mock.Mock()
        with self.assertRaises(ValueError) as caught:
            designer.submit({"stage": "find"}, manager)
        self.assertIn("Search FASTA is required", str(caught.exception))
        manager.create_job.assert_not_called()

    def test_submit_find_queues_one_job(self):
        manager = mock.Mock()
        manager.create_job.return_value = "abcdefabcdef"
        result = designer.submit(self.payload(), manager)
        self.assertEqual(result["job_id"], "abcdefabcdef")
        self.assertEqual(result["stage"], "find")
        self.assertEqual(result["title"], "Find Targets")
        kind, title, body, params = manager.create_job.call_args[0]
        self.assertEqual(kind, "designer")
        self.assertEqual(title, "Find Targets")
        self.assertTrue(callable(body))
        self.assertEqual(params["stage"], "find")
        self.assertEqual(params["request"]["active_side"], "target")

    def test_submit_score_requires_find_targets_output(self):
        manager = mock.Mock()
        with mock.patch(
            "design.workbench_form.default_output_dir",
            return_value=self.output_dir,
        ):
            with self.assertRaises(ValueError) as caught:
                designer.submit(dict(self.payload(), stage="score"), manager)
        self.assertEqual(str(caught.exception), designer.EXTRACT_MISSING_MESSAGE)
        manager.create_job.assert_not_called()

    def test_job_body_wires_the_runner_and_auto_confirms(self):
        runner = mock.Mock()
        runner.config = mock.Mock(run_label="run1", output_dir=self.output_dir,
                                  max_memory_mode="unlimited", max_memory_mb=0)
        runner.run_pipeline.return_value = 0
        runner.extract_output_path.return_value = os.path.join(
            self.output_dir, "x.tsv")
        runner.run_dir.return_value = self.output_dir
        runner.deliverable_paths.return_value = {}
        ctx = mock.Mock(out_dir=self.output_dir)
        with mock.patch.object(designer, "build_runner", return_value=runner):
            body = designer.job_body(self.payload(), 0, 1, "yes")
            self.assertEqual(body(ctx), 0)
        ctx.set_stop_hook.assert_called_once_with(runner.stop)
        kwargs = runner.run_pipeline.call_args[1]
        self.assertEqual(kwargs["start"], 0)
        self.assertEqual(kwargs["end"], 1)
        self.assertTrue(
            kwargs["on_prompt"]({"kind": "engine", "reason": "fallback"}))
        self.assertTrue(any("auto-confirm" in str(call)
                            for call in ctx.line.call_args_list))
        ctx.set_result.assert_called_once()
        self.assertEqual(ctx.set_result.call_args[0][0]["run_label"], "run1")

    def test_job_body_reports_run_dir_and_deliverables(self):
        run_label = "Run-A"
        run_dir = os.path.join(self.output_dir, run_label)
        params_file = write_file(
            os.path.join(run_dir, "params.json"), "{}")
        scores = write_file(
            os.path.join(self.output_dir, run_label + "_scores.tsv"), "x\n")
        missing = os.path.join(self.output_dir, run_label + "_offtargets.tsv")
        runner = mock.Mock()
        runner.config = mock.Mock(run_label=run_label, output_dir=self.output_dir,
                                  max_memory_mode="unlimited", max_memory_mb=0)
        runner.run_pipeline.return_value = 0
        runner.extract_output_path.return_value = os.path.join(
            run_dir, "extracted_seqs.tsv")
        runner.run_dir.return_value = run_dir
        runner.deliverable_paths.return_value = {
            "scores": scores,
            "guides": None,
            "offtargets": missing,
            "blast_results": None,
        }
        ctx = mock.Mock(out_dir=self.output_dir)
        with mock.patch.object(designer, "build_runner", return_value=runner):
            body = designer.job_body(self.payload(), 0, None, "yes")
            self.assertEqual(body(ctx), 0)
        result = ctx.set_result.call_args[0][0]
        outputs = ctx.set_outputs.call_args[0][0]
        self.assertEqual(result["run_dir"], run_dir)
        self.assertEqual(result["params_file"], params_file)
        self.assertEqual(result["scores"], scores)
        self.assertEqual(outputs["run_dir"], run_dir)
        self.assertEqual(outputs["params_file"], params_file)
        self.assertEqual(outputs["scores"], scores)
        for key in ("guides", "offtargets", "blast_results"):
            self.assertNotIn(key, result)
            self.assertNotIn(key, outputs)

    def test_job_body_omits_params_and_deliverables_without_a_label(self):
        runner = mock.Mock()
        runner.config = mock.Mock(run_label="", output_dir=self.output_dir,
                                  max_memory_mode="unlimited", max_memory_mb=0)
        runner.run_pipeline.return_value = 0
        runner.extract_output_path.return_value = os.path.join(
            self.output_dir, "occurrence")
        runner.run_dir.return_value = self.output_dir
        runner.deliverable_paths.return_value = {
            "scores": None,
            "guides": None,
            "offtargets": None,
            "blast_results": None,
        }
        ctx = mock.Mock(out_dir=self.output_dir)
        with mock.patch.object(designer, "build_runner", return_value=runner):
            body = designer.job_body(self.payload(), 0, None, "yes")
            self.assertEqual(body(ctx), 0)
        result = ctx.set_result.call_args[0][0]
        self.assertEqual(result["run_dir"], self.output_dir)
        for key in ("params_file", "scores", "guides", "offtargets",
                    "blast_results"):
            self.assertNotIn(key, result)

    def test_job_body_honours_the_no_confirm_policy(self):
        runner = mock.Mock()
        runner.config = mock.Mock(run_label="run1", output_dir=self.output_dir,
                                  max_memory_mode="custom", max_memory_mb=1024)
        runner.run_pipeline.return_value = 1
        ctx = mock.Mock(out_dir=self.output_dir)
        with mock.patch.object(designer, "build_runner", return_value=runner):
            body = designer.job_body(self.payload(), 1, None, "no")
            self.assertEqual(body(ctx), 1)
        kwargs = runner.run_pipeline.call_args[1]
        self.assertIsNone(kwargs["end"])
        self.assertFalse(
            kwargs["on_prompt"]({"kind": "engine", "reason": "asking"}))
        ctx.set_result.assert_not_called()

    def test_candidates_hide_internal_columns(self):
        runner = mock.Mock()
        runner.spec.candidate_columns.return_value = [
            "query_seq", "guide", "gap_seq", "score"]
        runner.read_extract_candidates.return_value = [
            {"query_seq": "AAA", "guide": "GGG", "gap_seq": "", "score": 0.5,
             "extra": "kept"}]
        manager = mock.Mock()
        manager.job_params.return_value = {"request": self.payload()}
        with mock.patch.object(designer, "extract_reader", return_value=runner):
            data = designer.candidates("abcdefabcdef", manager)
        self.assertEqual(data["columns"], ["guide", "score", "extra"])
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["rows"][0]["guide"], "GGG")
        self.assertNotIn("query_seq", data["rows"][0])

    def test_results_reads_the_deliverable_table(self):
        scores = write_file(
            os.path.join(self.output_dir, "run1_scores.tsv"),
            "rank\tseq_id\tqid\tquery_seq\ttotal_matches\n"
            "1\tchr1\tuniq_0\tACGT\t0\n"
            "2\tchr1\tuniq_1\tTTTT\t3\n")
        manager = mock.Mock()
        manager.get_job.return_value = {
            "job_id": "abcdefabcdef",
            "outputs": {"scores": scores, "guides": None},
        }
        data = designer.results("abcdefabcdef", manager)
        self.assertTrue(data["available"])
        self.assertEqual(data["file"], scores)
        self.assertEqual(
            data["columns"],
            ["rank", "seq_id", "qid", "query_seq", "total_matches"])
        self.assertEqual(data["total"], 2)
        self.assertEqual(data["rows"][1]["qid"], "uniq_1")
        self.assertEqual(data["rows"][0]["total_matches"], "0")

    def test_results_is_unavailable_without_a_scores_file(self):
        manager = mock.Mock()
        manager.get_job.return_value = {"outputs": {}}
        data = designer.results("abcdefabcdef", manager)
        self.assertFalse(data["available"])
        self.assertEqual(data["columns"], [])
        self.assertEqual(data["total"], 0)
        self.assertIsNone(data["file"])

    def test_export_rows_full_reproduces_the_output_table(self):
        scores = write_file(
            os.path.join(self.output_dir, "run1_scores.tsv"),
            "rank\tseq_id\tqid\ttotal_matches\n"
            "1\tchr1\tuniq_0\t0\n"
            "2\tchr1\tuniq_1\t3\n")
        manager = mock.Mock()
        manager.job_dir.return_value = self.output_dir
        manager.job_params.return_value = {"run_label": "run1"}
        manager.get_job.return_value = {"outputs": {"scores": scores}}
        result = designer.export_rows(
            "abcdefabcdef",
            {"format": "csv", "columns": "full", "rows": [1]}, manager)
        self.assertTrue(result["file"].startswith("export/run1_results_"))
        self.assertTrue(result["file"].endswith(".csv"))
        path = os.path.join(self.output_dir, "export",
                            os.path.basename(result["file"]))
        with open(path, "r", encoding="utf-8", newline="") as handle:
            text = handle.read()
        self.assertEqual(text.splitlines()[0], "rank,seq_id,qid,total_matches")
        self.assertIn("uniq_1", text)
        self.assertNotIn("uniq_0", text)
        self.assertEqual(result["written"], 1)

    def test_export_rows_full_validates_format_and_view(self):
        manager = mock.Mock()
        manager.job_dir.return_value = self.output_dir
        manager.job_params.return_value = {"run_label": "run1"}
        manager.get_job.return_value = {"outputs": {}}
        with self.assertRaises(ValueError) as missing:
            designer.export_rows(
                "abcdefabcdef", {"format": "csv", "columns": "full"}, manager)
        self.assertIn("Run Score & Off-target first", str(missing.exception))
        with self.assertRaises(ValueError) as fmt:
            designer.export_rows(
                "abcdefabcdef", {"format": "fasta", "columns": "full"},
                manager)
        self.assertIn("csv", str(fmt.exception))
        with self.assertRaises(ValueError) as view:
            designer.export_rows(
                "abcdefabcdef", {"format": "csv", "columns": "wide"}, manager)
        self.assertIn("Unsupported table", str(view.exception))

    def test_export_rows_writes_into_the_job_export_dir(self):
        manager = mock.Mock()
        manager.job_dir.return_value = self.output_dir
        manager.job_params.return_value = {"run_label": "run1"}
        fake = {"columns": ["guide"], "rows": [{"guide": "GGG"}], "total": 1}
        with mock.patch.object(designer, "candidates", return_value=fake):
            result = designer.export_rows(
                "abcdefabcdef", {"format": "csv", "filename": "picked.csv"},
                manager)
        path = os.path.join(self.output_dir, "export", "picked.csv")
        self.assertTrue(os.path.isfile(path))
        with open(path, "r", encoding="utf-8") as handle:
            self.assertIn("GGG", handle.read())
        self.assertEqual(result["file"], "export/picked.csv")
        self.assertEqual(result["written"], 1)
        self.assertEqual(
            result["download_url"],
            "/api/jobs/abcdefabcdef/download?file=export/picked.csv")

    def test_export_rows_validates_format_and_selection(self):
        manager = mock.Mock()
        manager.job_dir.return_value = self.output_dir
        manager.job_params.return_value = {}
        fake = {"columns": ["guide"], "rows": [{"guide": "GGG"}], "total": 1}
        with mock.patch.object(designer, "candidates", return_value=fake):
            with self.assertRaises(ValueError):
                designer.export_rows("abcdefabcdef", {"format": "pdf"}, manager)
            with self.assertRaises(ValueError):
                designer.export_rows(
                    "abcdefabcdef", {"format": "csv", "rows": [5]}, manager)

    def test_sanitize_label_and_export_filename(self):
        self.assertEqual(designer.sanitize_label("a/b\\c d"), "a-b-c_d")
        self.assertEqual(designer.sanitize_label(""), "results")
        name = designer.export_filename("run 1", "unique_guides", "20260101_000000")
        self.assertEqual(name, "run_1_unique_guides_20260101_000000.tsv")

class DataPrepServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="webapp_dataprep_")
        self.addCleanup(self.tmp.cleanup)
        self.genome = write_file(os.path.join(self.tmp.name, "g.fa"), ">c1\nACGT\n")
        self.annotation = write_file(
            os.path.join(self.tmp.name, "a.gff"), "##gff-version 3\n")
        self.output_dir = os.path.join(self.tmp.name, "out")

    def test_resolve_fixed_dirs_and_file(self):
        self.assertEqual(dataprep.resolve_prep_dir(), default_output_dir())
        self.assertEqual(dataprep.resolve_resource_dir({}),
                         default_resource_dir())
        self.assertEqual(
            dataprep.resolve_resource_dir({"output_dir": self.output_dir}),
            self.output_dir)
        with self.assertRaises(ValueError):
            dataprep.require_file("", "Genome FASTA")
        with self.assertRaises(ValueError):
            dataprep.require_file("missing.fa", "Genome FASTA")
        self.assertEqual(
            dataprep.require_file(self.genome, "Genome FASTA"), self.genome)

    def test_submit_prepare_validates_before_queueing(self):
        manager = mock.Mock()
        with self.assertRaises(ValueError) as caught:
            dataprep.submit_prepare({}, manager)
        self.assertIn("Genome FASTA is required", str(caught.exception))
        with self.assertRaises(ValueError) as caught:
            dataprep.submit_prepare(
                {"output_dir": self.output_dir, "genome": self.genome}, manager)
        self.assertIn("Annotation file is required", str(caught.exception))
        manager.create_job.assert_not_called()

    def test_submit_prepare_queues_a_dataprep_job(self):
        manager = mock.Mock()
        manager.create_job.return_value = "abcdefabcdef"
        result = dataprep.submit_prepare({
            "genome": self.genome, "annotation": self.annotation,
            "output_dir": self.output_dir, "target_id": "GENE1",
        }, manager)
        self.assertEqual(result["job_id"], "abcdefabcdef")
        self.assertEqual(manager.create_job.call_args[0][0], "dataprep")

    def test_submit_extract_mask_needs_a_mask_identifier(self):
        manager = mock.Mock()
        base = {"genome": self.genome, "annotation": self.annotation,
                "output_dir": self.output_dir}
        with self.assertRaises(ValueError) as caught:
            dataprep.submit_extract_mask(
                dict(base, mask_same_as_target=False), manager)
        self.assertIn("Mask gene identifier", str(caught.exception))
        with self.assertRaises(ValueError) as caught:
            dataprep.submit_extract_mask(
                dict(base, mask_same_as_target=True), manager)
        self.assertIn("Search scope", str(caught.exception))
        manager.create_job.assert_not_called()

    def test_submit_build_index_uses_the_fixed_resource_dir(self):
        manager = mock.Mock()
        manager.create_job.return_value = "abcdefabcdef"
        with self.assertRaises(ValueError) as caught:
            dataprep.submit_build_index({}, manager)
        self.assertIn("Genome FASTA is required", str(caught.exception))
        result = dataprep.submit_build_index({"genome": self.genome}, manager)
        self.assertEqual(result["job_id"], "abcdefabcdef")
        self.assertEqual(manager.create_job.call_args[0][0], "dataprep")

    def test_submit_download_requires_species(self):
        manager = mock.Mock()
        manager.create_job.return_value = "abcdefabcdef"
        with self.assertRaises(ValueError) as caught:
            dataprep.submit_download({"output_dir": "x"}, manager)
        self.assertIn("Organism is required", str(caught.exception))
        result = dataprep.submit_download({"species": "human"}, manager)
        self.assertEqual(result["job_id"], "abcdefabcdef")

    def test_bodies_are_lazy_callables(self):
        for body in (dataprep.download_body({"species": "human"}),
                     dataprep.prepare_body({}),
                     dataprep.extract_target_body({}),
                     dataprep.extract_mask_body({}),
                     dataprep.build_blastdb_body({}),
                     dataprep.build_index_body({})):
            self.assertTrue(callable(body))

    def test_publish_file_copies_into_the_job_out_dir(self):
        source = write_file(os.path.join(self.tmp.name, "target.fa"), ">t1\nACGT\n")
        ctx = mock.Mock(out_dir=os.path.join(self.tmp.name, "job", "out"))
        self.assertEqual(dataprep.publish_file(source, ctx), "out/target.fa")
        self.assertTrue(os.path.isfile(os.path.join(ctx.out_dir, "target.fa")))
        self.assertEqual(dataprep.publish_file("", ctx), "")


class ModelServiceTests(unittest.TestCase):
    def test_check_key_rejects_unknown_and_external_models(self):
        with self.assertRaises(ValueError) as caught:
            models_service._check_key("nope")
        self.assertIn("unknown model", str(caught.exception))
        with self.assertRaises(ValueError) as caught:
            models_service._check_key("teep")
        self.assertIn("cannot be downloaded or deleted", str(caught.exception))
        self.assertIsInstance(models_service._check_key("crispr_m"), dict)

    def test_list_models_reports_status_labels_and_paths(self):
        data = models_service.list_models()
        self.assertTrue(data["groups"])
        self.assertIn("models_dir", data)
        keys = []
        for group in data["groups"]:
            self.assertTrue(group["label"])
            self.assertTrue(group["protein"])
            for model in group["models"]:
                keys.append(model["key"])
                self.assertTrue(model["name"])
                self.assertIn("downloadable", model)
                self.assertIn("status_label", model)
                self.assertIn("is_ready", model)
                self.assertIn("path", model)
        self.assertIn("crispr_m", keys)

    def test_model_descriptions_come_from_the_registry(self):
        data = models_service.list_models()
        keys = []
        for group in data["groups"]:
            for model in group["models"]:
                key = model["key"]
                keys.append(key)
                info = model_registry.MODELS[key]
                self.assertTrue(model["description"], key)
                self.assertEqual(model["description"], info["description"], key)
                self.assertEqual(model["url"], info.get("url") or "", key)
        self.assertIn("teep", keys)
        teep = next(
            model for group in data["groups"] for model in group["models"]
            if model["key"] == "teep"
        )
        self.assertEqual(teep["path"], "")
        self.assertTrue(teep["url"])

    def test_submit_download_and_delete_queue_model_jobs(self):
        manager = mock.Mock()
        manager.create_job.return_value = "abcdefabcdef"
        result = models_service.submit_download("crispr_m", manager)
        self.assertEqual(result["model"], "crispr_m")
        self.assertEqual(manager.create_job.call_args[0][0], "model")
        self.assertEqual(manager.create_job.call_args[0][3]["action"], "download")
        models_service.submit_delete("crispr_m", manager)
        self.assertEqual(manager.create_job.call_args[0][3]["action"], "delete")

class HandlerRouteTests(JobManagerTestCase):
    def setUp(self):
        super().setUp()
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

    def test_index_page_has_the_four_tabs(self):
        calls = self.call("/")
        self.assertEqual(len(calls), 1)
        kind, status, body, content_type, _headers = calls[0]
        self.assertEqual((kind, status), ("bytes", 200))
        self.assertIn("text/html", content_type)
        html = body.decode("utf-8")
        for tab in ("Data prep", "Models", "Designer", "Results / Output"):
            self.assertIn(tab, html)
        self.assertIn("/static/app.js", html)
        self.assertIn("/static/styles.css", html)

    def test_static_whitelist_blocks_everything_else(self):
        calls = self.call("/static/app.js")
        self.assertEqual(calls[0][0], "bytes")
        self.assertIn("javascript", calls[0][3])
        self.assertEqual(self.call("/static/styles.css")[0][3],
                         "text/css; charset=utf-8")
        for path in ("/static/app.py", "/static/../app.py", "/static/nope.js"):
            calls = self.call(path)
            self.assertEqual(calls[0][0], "json", path)
            self.assertEqual(calls[0][1], 404, path)

    def test_schema_route(self):
        kind, status, payload = self.call("/api/schema")[0]
        self.assertEqual((kind, status), ("json", 200))
        self.assertEqual(payload["engines"], list(schema_module.ENGINE_CHOICES))

    def test_jobs_and_job_detail_routes(self):
        def runner(ctx):
            ctx.line("done")
            return 0

        job_id, _ = self.start(runner)
        listing = self.call("/api/jobs")[0][2]
        self.assertEqual([job["job_id"] for job in listing["jobs"]], [job_id])

        detail = self.call("/api/jobs/" + job_id)[0]
        self.assertEqual(detail[1], 200)
        self.assertEqual(detail[2]["status"], "succeeded")

        log = self.call("/api/jobs/%s/log?offset=0" % job_id)[0][2]
        self.assertEqual(log["text"], "done\n")
        log2 = self.call("/api/jobs/%s/log?offset=%d" % (job_id, log["offset"]))[0][2]
        self.assertEqual(log2["text"], "")

        self.assertEqual(self.call("/api/jobs/aaaaaaaaaaaa")[0][1], 404)
        bad = self.call("/api/jobs/zzz")[0]
        self.assertEqual(bad[1], 400)
        self.assertIn("invalid job id", bad[2]["error"])

    def test_job_download_whitelist_and_traversal(self):
        job_id, _ = self.start(lambda ctx: 0)
        job_dir = self.manager.job_dir(job_id)
        write_file(os.path.join(job_dir, "export", "rows.csv"), "guide\nGGG\n")
        served = self.call(
            "/api/jobs/%s/download?file=export/rows.csv" % job_id)[0]
        self.assertEqual(served[0], "bytes")
        self.assertEqual(served[2], b"guide\nGGG\n")
        self.assertIn("rows.csv", served[4]["Content-Disposition"])
        for bad in ("params.json", "../params.json", "export/../params.json",
                    "export/%2E%2E/params.json", "nope/rows.csv",
                    "export/missing.csv"):
            calls = self.call("/api/jobs/%s/download?file=%s" % (job_id, bad))
            self.assertIn(calls[0][1], (400, 404), bad)

    def test_outputs_route(self):
        self.assertEqual(self.call("/api/outputs")[0][1], 400)
        unknown = self.call(
            "/api/outputs?dir=" + os.path.join(self.tmp.name, "nope"))
        self.assertEqual(unknown[0][1], 400)
        listed = os.path.join(self.tmp.name, "listed")
        write_file(os.path.join(listed, "kept.tsv"), "a\tb\n")
        write_file(os.path.join(listed, "skipped.bin"), "x")
        payload = self.call("/api/outputs?dir=" + listed)[0][2]
        self.assertEqual([item["name"] for item in payload["files"]],
                         ["kept.tsv"])

    def test_fs_list_route(self):
        root = self.call("/api/fs/list")[0]
        self.assertEqual(root[1], 200)
        self.assertIsNone(root[2]["dir"])
        self.assertIsNone(root[2]["parent"])
        self.assertTrue(root[2]["roots"])
        self.assertEqual(root[2]["entries"], [])
        self.assertEqual(root[2]["kind"], "any")
        self.assertFalse(root[2]["truncated"])

        missing = self.call(
            "/api/fs/list?dir=" + os.path.join(self.tmp.name, "nope"))[0]
        self.assertEqual(missing[1], 400)
        self.assertIn("not found", missing[2]["error"])

        base = os.path.join(self.tmp.name, "fsroot")
        write_file(os.path.join(base, "sub", "inner.gtf"), "x\n")
        write_file(os.path.join(base, "mini.fna"), ">a\n")
        write_file(os.path.join(base, "notes.txt"), "x\n")
        write_file(os.path.join(base, "mini.blastdb.nin"), "x\n")
        write_file(os.path.join(base, "miniindex.ggi"), "x\n")

        def listing(kind):
            calls = self.call("/api/fs/list?dir=%s&kind=%s" % (base, kind))
            self.assertEqual(calls[0][1], 200, kind)
            return calls[0][2]

        def names(kind):
            return [item["name"] for item in listing(kind)["entries"]]

        self.assertEqual(names("fasta"), ["sub", "mini.fna"])
        self.assertEqual(names("dir"), ["sub"])
        self.assertEqual(names("any"), ["sub", "mini.blastdb.nin", "mini.fna",
                                        "miniindex.ggi", "notes.txt"])
        database = listing("db")
        self.assertIn("mini.blastdb.nin",
                      [item["name"] for item in database["entries"]])
        self.assertNotIn("mini.fna",
                         [item["name"] for item in database["entries"]])
        self.assertEqual(database["strip"][0], ".source.json")

        payload = listing("any")
        self.assertEqual(payload["dir"], os.path.abspath(base))
        self.assertEqual(payload["parent"], self.tmp.name)
        self.assertFalse(payload["truncated"])
        for entry in payload["entries"]:
            self.assertTrue(os.path.isabs(entry["path"]))
            self.assertEqual(entry["path"],
                             os.path.join(payload["dir"], entry["name"]))
            if entry["type"] == "dir":
                self.assertIsNone(entry["size"])

    def test_fs_list_hidden_filter(self):
        """Dot-prefixed entries are only listed when ``hidden=1`` asks for them."""
        base = os.path.join(self.tmp.name, "fshidden")
        write_file(os.path.join(base, "sub", "deep.gtf"), "x\n")
        write_file(os.path.join(base, "plain.fna"), ">a\n")
        write_file(os.path.join(base, ".dotfile.fna"), ">b\n")

        def names(kind, **extra):
            query = "dir=%s&kind=%s" % (base, kind)
            for key, value in extra.items():
                query += "&%s=%s" % (key, value)
            calls = self.call("/api/fs/list?" + query)
            self.assertEqual(calls[0][1], 200, query)
            return [item["name"] for item in calls[0][2]["entries"]]

        self.assertEqual(names("fasta"), ["sub", "plain.fna"])
        self.assertEqual(names("fasta", hidden="1"),
                         ["sub", ".dotfile.fna", "plain.fna"])
        self.assertEqual(names("any"), ["sub", "plain.fna"])
        self.assertEqual(names("any", hidden="0"), ["sub", "plain.fna"])
        self.assertEqual(names("any", hidden="true"),
                         ["sub", ".dotfile.fna", "plain.fna"])

    @unittest.skipUnless(os.name == "nt", "needs the Windows hidden attribute")
    def test_fs_list_hidden_attribute_filter(self):
        """The Windows hidden attribute hides an entry until ``hidden=1``."""
        import ctypes

        base = os.path.join(self.tmp.name, "fsattrs")
        write_file(os.path.join(base, "plain.fna"), ">a\n")
        tagged = write_file(os.path.join(base, "tagged.fna"), ">b\n")
        if not ctypes.windll.kernel32.SetFileAttributesW(str(tagged), 0x02):
            self.skipTest("the filesystem does not keep file attributes here")

        def names(**extra):
            query = "dir=%s&kind=fasta" % base
            for key, value in extra.items():
                query += "&%s=%s" % (key, value)
            calls = self.call("/api/fs/list?" + query)
            self.assertEqual(calls[0][1], 200, query)
            return [item["name"] for item in calls[0][2]["entries"]]

        self.assertEqual(names(), ["plain.fna"])
        self.assertEqual(names(hidden="1"), ["plain.fna", "tagged.fna"])

    def test_unknown_routes_return_404(self):
        self.assertEqual(self.call("/api/nope")[0][1], 404)
        self.assertEqual(self.call("/api/nope", method="POST", body={})[0][1], 404)

    def test_post_designer_preview_forwards_the_payload(self):
        with mock.patch.object(designer, "preview",
                               return_value={"describe": "ok", "errors": []}) as preview:
            calls = self.call("/api/designer/preview", method="POST",
                              body={"mode": "single_motif_flank"})
        self.assertEqual(calls[0][1], 200)
        self.assertEqual(calls[0][2], {"describe": "ok", "errors": []})
        preview.assert_called_once_with({"mode": "single_motif_flank"})

    def test_post_designer_jobs_uses_the_shared_manager(self):
        manager = mock.Mock()
        manager.create_job.return_value = "abcdefabcdef"
        app.set_manager(manager)
        with mock.patch.object(designer, "submit",
                               return_value={"job_id": "abcdefabcdef"}) as submit:
            calls = self.call("/api/designer/jobs", method="POST",
                              body={"stage": "find"})
        self.assertEqual(calls[0][1], 200)
        self.assertEqual(calls[0][2]["job_id"], "abcdefabcdef")
        self.assertIs(submit.call_args[0][1], manager)

    def test_post_designer_jobs_reports_validation_errors(self):
        manager = mock.Mock()
        app.set_manager(manager)
        calls = self.call("/api/designer/jobs", method="POST",
                          body={"stage": "find", "values": {}})
        self.assertEqual(calls[0][1], 400)
        self.assertIn("Search FASTA is required", calls[0][2]["error"])
        manager.create_job.assert_not_called()

    def test_post_job_cancel_and_export(self):
        job_id, _ = self.start(lambda ctx: 0)
        cancelled = self.call(
            "/api/jobs/%s/cancel" % job_id, method="POST", body={})[0]
        self.assertEqual(cancelled[1], 200)
        self.assertEqual(cancelled[2]["job_id"], job_id)
        self.assertEqual(self.call("/api/jobs/aaaaaaaaaaaa/cancel",
                                   method="POST", body={})[0][1], 404)
        with mock.patch.object(designer, "export_rows",
                               return_value={"file": "export/x.csv"}) as export:
            calls = self.call("/api/jobs/%s/export" % job_id, method="POST",
                              body={"format": "csv", "columns": "full"})
        self.assertEqual(calls[0][2], {"file": "export/x.csv"})
        self.assertEqual(export.call_args[0][0], job_id)
        self.assertEqual(export.call_args[0][1]["columns"], "full")

    def test_get_job_results_route(self):
        job_id, _ = self.start(lambda ctx: 0)
        fake = {"columns": ["rank"], "rows": [{"rank": "1"}], "total": 1,
                "available": True, "file": "/tmp/run1_scores.tsv"}
        with mock.patch.object(designer, "results",
                               return_value=fake) as results:
            calls = self.call("/api/jobs/%s/results" % job_id)
        self.assertEqual(calls[0][1], 200)
        self.assertEqual(calls[0][2]["columns"], ["rank"])
        self.assertTrue(calls[0][2]["available"])
        self.assertEqual(results.call_args[0][0], job_id)
        self.assertEqual(
            self.call("/api/jobs/aaaaaaaaaaaa/results")[0][1], 404)

    def test_post_models_routes(self):
        manager = mock.Mock()
        manager.create_job.return_value = "abcdefabcdef"
        app.set_manager(manager)
        calls = self.call("/api/models/crispr_m/download", method="POST", body={})
        self.assertEqual(calls[0][1], 200)
        self.assertEqual(calls[0][2]["model"], "crispr_m")
        self.assertEqual(manager.create_job.call_args[0][0], "model")

        self.assertEqual(self.call("/api/models/teep/download",
                                   method="POST", body={})[0][1], 400)
        self.assertEqual(self.call("/api/models/nope/delete",
                                   method="POST", body={})[0][1], 400)
        self.assertEqual(self.call("/api/models/crispr_m/nope",
                                   method="POST", body={})[0][1], 404)

    def test_post_dataprep_routes_validate_before_queueing(self):
        manager = mock.Mock()
        app.set_manager(manager)
        for path in ("/api/dataprep/prepare", "/api/dataprep/extract-target",
                     "/api/dataprep/extract-mask", "/api/dataprep/build-blastdb",
                     "/api/dataprep/build-index"):
            calls = self.call(path, method="POST", body={})
            self.assertEqual(calls[0][1], 400, path)
        calls = self.call("/api/dataprep/download", method="POST", body={})
        self.assertEqual(calls[0][1], 400)
        self.assertIn("Organism is required", calls[0][2]["error"])
        manager.create_job.assert_not_called()

    def test_route_helpers(self):
        self.assertEqual(app.job_route("/api/jobs/abc/log"), ("abc", "log"))
        self.assertEqual(app.job_route("/api/jobs/abc"), ("abc", None))
        self.assertEqual(app.job_route("/api/jobs/a/b/c"), (None, None))
        self.assertEqual(app.job_route("/api/models/x"), (None, None))
        self.assertEqual(app.model_action_route("/api/models/crispr_m/download"),
                         ("crispr_m", "download"))
        self.assertEqual(app.model_action_route("/api/models/crispr_m"), (None, None))


class SampleAndHelpRouteTests(JobManagerTestCase):
    """Routes for the sample-data button and the NAR-required help pages."""

    def setUp(self):
        super().setUp()
        app.set_manager(self.manager)
        self.addCleanup(app.set_manager, None)

    # reuse the HTTP plumbing of HandlerRouteTests without inheriting its tests
    call = HandlerRouteTests.call

    def test_sample_route_serves_the_bundled_files(self):
        kind, status, payload = self.call("/api/sample")[0]
        self.assertEqual((kind, status), ("json", 200))
        self.assertEqual(payload["genome_fasta"], app.SAMPLE_GENOME)
        self.assertEqual(payload["target_fasta"], app.SAMPLE_TARGET)
        self.assertEqual(payload["batch_spec"], app.SAMPLE_BATCH)
        for name in app.SAMPLE_FILES:
            self.assertTrue(os.path.isfile(os.path.join(app.ROOT, name)), name)

    def test_sample_route_masks_the_target_like_the_batch_spec(self):
        # The Designer form has no "mask same as target" switch, so the payload
        # must pass the mask explicitly; without it the on-target loci are
        # counted as off-targets and the run stops matching sample_output/.
        spec_path = os.path.join(app.ROOT, app.SAMPLE_BATCH)
        with open(spec_path, "r", encoding="utf-8") as handle:
            scope = json.load(handle)["scopes"][0]
        self.assertTrue(scope["mask_same_as_target"])

        fields = self.call("/api/sample")[0][2]["fields"]
        self.assertEqual(fields["search_fasta"], scope["search_fasta"])
        self.assertEqual(fields["mask_fasta"], scope["search_fasta"])

    def test_sample_route_reports_missing_files_as_404(self):
        absent = app.SAMPLE_FILES + ("sample_data/absent.fa",)
        with mock.patch.object(app, "SAMPLE_FILES", absent):
            kind, status, payload = self.call("/api/sample")[0]
        self.assertEqual((kind, status), ("json", 404))
        self.assertIn("absent.fa", payload["error"])

    def test_help_pages_are_served_as_html(self):
        for path in ("/help", "/help/", "/help/tutorial", "/help/tutorial/"):
            calls = self.call(path)
            self.assertEqual(calls[0][0], "bytes", path)
            self.assertEqual(calls[0][1], 200, path)
            self.assertIn("text/html", calls[0][3], path)
        html = self.call("/help")[0][2].decode("utf-8")
        self.assertIn('href="/help/tutorial"', html)
        self.assertIn('href="/help/sample_output/README.md"', html)
        self.assertIn("<h1", self.call("/help/tutorial")[0][2].decode("utf-8"))

    def test_every_sample_output_file_is_reachable_as_text(self):
        names = sorted(os.listdir(app.HELP_SAMPLE_DIR))
        self.assertTrue(names)
        for name in names:
            calls = self.call("/help/sample_output/" + name)
            self.assertEqual(calls[0][0], "bytes", name)
            self.assertEqual(calls[0][1], 200, name)
            self.assertIn("text/plain", calls[0][3], name)
            self.assertTrue(calls[0][2], name)

    def test_help_sample_output_rejects_traversal_and_missing(self):
        for bad in ("", "nope.tsv", "../README.md", "..%2FREADME.md",
                    "%2E%2E/README.md", "./../README.md"):
            calls = self.call("/help/sample_output/" + bad)
            self.assertEqual(calls[0][0], "json", bad)
            self.assertEqual(calls[0][1], 404, bad)


if __name__ == "__main__":
    unittest.main()
