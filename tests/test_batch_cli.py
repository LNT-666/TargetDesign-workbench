import contextlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODULE_PATH = os.path.join(ROOT, "tools", "batch_run.py")

_spec = importlib.util.spec_from_file_location("batch_run_cli", MODULE_PATH)
cli = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cli)


BATCH = {
    "batch_label": "cli-test",
    "shared": {},
    "scopes": [{"scope_id": "s1", "search_fasta": "a.fa"}],
    "patterns": [
        {"pattern_id": "P1", "mode": "single_motif_flank", "overlay": {}}
    ],
    "groups": [
        {"group_id": "G1", "scope_ids": ["s1"], "pattern_ids": ["P1"]}
    ],
}


class RecordingRunner:
    last = None

    def __init__(self, spec, units, batch_root_dir, on_line=None, resume=True,
                 run_meta=None):
        self.units = units
        self.batch_root_dir = batch_root_dir
        self.on_line = on_line
        self.run_meta = run_meta
        RecordingRunner.last = self

    def run(self):
        return 0


class BatchCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.spec_path = os.path.join(self.tmp, "batch.json")
        with open(self.spec_path, "w", encoding="utf-8") as handle:
            json.dump(BATCH, handle)
        self.output = os.path.join(self.tmp, "output")

    def _run(self, argv):
        out = io.StringIO()
        patches = [
            mock.patch.object(cli, "validate_spec", return_value=([], [])),
            mock.patch.object(cli, "BatchRunner", RecordingRunner),
            mock.patch.object(
                cli, "default_output_dir", return_value=self.output
            ),
        ]
        with contextlib.ExitStack() as stack:
            for patcher in patches:
                stack.enter_context(patcher)
            with contextlib.redirect_stdout(out):
                code = cli.main(argv)
        return code, out.getvalue()

    def test_allocates_run_folder_and_passes_meta(self):
        code, text = self._run(["--spec", self.spec_path])
        self.assertEqual(code, 0)
        self.assertIn("RUN_ID: ", text)
        run_id = [
            line.split(":", 1)[1].strip()
            for line in text.splitlines()
            if line.startswith("RUN_ID:")
        ][0]
        self.assertRegex(run_id, r"^\d{8}-\d{4}$")
        run_dir = os.path.join(self.output, run_id)
        self.assertTrue(os.path.isdir(run_dir))
        self.assertEqual(RecordingRunner.last.batch_root_dir, run_dir)
        self.assertEqual(RecordingRunner.last.run_meta["run_id"], run_id.split("-")[1])
        self.assertEqual(RecordingRunner.last.run_meta["batch_label"], "cli-test")

    def test_run_id_reuses_an_existing_folder(self):
        code, text = self._run(["--spec", self.spec_path])
        self.assertEqual(code, 0)
        first = RecordingRunner.last.batch_root_dir
        code, _text = self._run(
            ["--spec", self.spec_path, "--run-id", os.path.basename(first)]
        )
        self.assertEqual(code, 0)
        self.assertEqual(RecordingRunner.last.batch_root_dir, first)

    def test_unknown_run_id_errors(self):
        code, text = self._run(
            ["--spec", self.spec_path, "--run-id", "9999"]
        )
        self.assertEqual(code, 2)
        self.assertIn("no run", text)

    def test_first_run_of_a_day_is_reserved(self):
        code, text = self._run(["--spec", self.spec_path])
        self.assertEqual(code, 0)
        self.assertIn("-0114", text)


if __name__ == "__main__":
    unittest.main()
