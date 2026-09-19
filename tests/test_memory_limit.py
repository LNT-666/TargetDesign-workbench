#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Focused tests for process memory-limit resolution and propagation."""

import os
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHARED = os.path.join(ROOT, "shared")
sys.path.insert(0, ROOT)
sys.path.insert(0, SHARED)

from design.pattern_runner import PatternRunner, RunnerConfig  # noqa: E402
from design.pattern_spec import (  # noqa: E402
    MotifSpec,
    PatternKind,
    PatternSpec,
    Side,
)
from gui.gui_common import Workspace  # noqa: E402
from search import native_offtarget  # noqa: E402
from search.offtarget_backend import IndexedBackend, SearchParams  # noqa: E402
from utils import system_memory  # noqa: E402


class FakeVar:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class FakeEntry(FakeVar):
    def configure(self, **_kwargs):
        pass

    def delete(self, *_args):
        self.value = ""

    def insert(self, _index, value):
        self.value = value


class FakeGrid:
    def grid(self):
        return None


class SystemMemoryTests(unittest.TestCase):
    def test_auto_formula_and_boundaries(self):
        self.assertEqual(system_memory.resolve_auto_limit_mb(0, 0), 0)
        self.assertEqual(system_memory.resolve_auto_limit_mb(1, 1), 0)
        self.assertEqual(
            system_memory.resolve_auto_limit_mb(1024, 256), 192)
        self.assertEqual(
            system_memory.resolve_auto_limit_mb(64000, 42000), 31500)
        self.assertEqual(system_memory.format_memory_mb(32256), "31.5 GiB")
        self.assertEqual(system_memory.format_memory_mb(512), "512 MiB")

    def test_remote_memory_query_does_not_require_remote_pythonpath(self):
        completed = SimpleNamespace(
            returncode=0,
            stdout='{"total_mb": 64000, "available_mb": 42000}',
            stderr="",
        )
        with mock.patch(
                "utils.system_memory.subprocess.run",
                return_value=completed) as run:
            snapshot = system_memory.resolve_remote_memory("lab-host")
        self.assertEqual(
            snapshot, {"total_mb": 64000, "available_mb": 42000})
        command = run.call_args.args[0]
        self.assertIn("/proc/meminfo", command[-1])
        self.assertNotIn("shared.utils.system_memory", command[-1])


class NativeMemoryPropagationTests(unittest.TestCase):
    def test_native_adapter_adds_build_and_search_flags(self):
        def fake_build_streaming(command, on_line, **kwargs):
            on_line('{"ok":true}')
            return 0, ""

        with mock.patch(
                "search.native_offtarget._run_streaming",
                side_effect=fake_build_streaming) as run:
            native_offtarget.build_index(
                "offtarget-engine", "genome.fa", "idx",
                max_memory_mb=2048)
        build_cmd = run.call_args.args[0]
        self.assertEqual(
            build_cmd[build_cmd.index("--max-memory-mb") + 1], "2048")

        events = (
            '{"type":"summary","guides":1,"hits":0,'
            '"memory_limit_mb":2048,"estimated_peak_mb":512,'
            '"observed_peak_mb":128}\n'
        )
        def fake_streaming(command, on_line, **kwargs):
            for line in events.splitlines():
                on_line(line)
            return 0, ""

        with mock.patch(
                "search.native_offtarget._run_streaming",
                side_effect=fake_streaming) as run:
            _hits, report = native_offtarget.search(
                "offtarget-engine", "genome.fa", "idx",
                [{"qid": "g0", "guide_seq": "ACGT"}],
                max_memory_mb=2048)
        search_cmd = run.call_args.args[0]
        self.assertEqual(
            search_cmd[search_cmd.index("--max-memory-mb") + 1], "2048")
        self.assertEqual(report["memory_limit_mb"], 2048)
        self.assertEqual(report["estimated_peak_mb"], 512)
        self.assertEqual(report["observed_peak_mb"], 128)

    def test_memory_limit_error_never_falls_back_to_python(self):
        params = SearchParams(
            max_mismatch=1,
            max_bulge=0,
            extra={"max_memory_mb": 1024, "k": 10},
        )
        backend = IndexedBackend()
        error = native_offtarget.NativeEngineError(
            ["offtarget-engine", "search"], 6,
            "[MEMORY_LIMIT_EXCEEDED] injected memory failure")
        with mock.patch(
                "search.native_offtarget.native_enabled",
                return_value=True), mock.patch(
                "search.native_offtarget.probe_binary",
                return_value=(True, "offtarget-engine")), mock.patch(
                "search.offtarget_backend.os.path.getsize",
                return_value=1000), mock.patch.object(
                backend, "_search_native", side_effect=error), mock.patch.object(
                backend, "_search_python") as python_search:
            with self.assertRaises(native_offtarget.MemoryLimitExceededError):
                backend.search(
                    [{"qid": "g0", "guide_seq": "ACGT"}],
                    "genome.fa",
                    params,
                )
        python_search.assert_not_called()


class PatternRunnerMemoryTests(unittest.TestCase):
    def _runner(self, **overrides):
        config = RunnerConfig(
            search_fasta="input.fa",
            genome_fasta="genome.fa",
            output_dir="out",
            engine="indexed",
            **overrides,
        )
        spec = PatternSpec(
            kind=PatternKind.SINGLE_MOTIF_FLANK,
            motif=MotifSpec("TTAT", 10, Side.UPSTREAM),
        )
        return PatternRunner(spec, config)

    def test_custom_and_unlimited_limits_reach_commands(self):
        custom = self._runner(
            max_memory_mode="custom", max_memory_mb=2048)
        custom_cmd = custom.build_pipeline()[1].command
        self.assertEqual(
            custom_cmd[custom_cmd.index("--max-memory-mb") + 1], "2048")

        unlimited = self._runner(max_memory_mode="unlimited")
        unlimited_cmd = unlimited.build_pipeline()[1].command
        self.assertEqual(
            unlimited_cmd[unlimited_cmd.index("--max-memory-mb") + 1], "0")

    def test_auto_uses_resolved_value_without_changing_mode(self):
        runner = self._runner(
            max_memory_mode="auto", max_memory_mb=4096)
        command = runner.build_pipeline()[1].command
        self.assertEqual(
            command[command.index("--max-memory-mb") + 1], "4096")
        self.assertEqual(runner.config.max_memory_mode, "auto")

    def test_small_custom_limit_is_rejected(self):
        runner = self._runner(
            max_memory_mode="custom", max_memory_mb=128)
        with self.assertRaisesRegex(ValueError, "at least 512"):
            runner.build_pipeline()


class MainWorkspaceMemoryTests(unittest.TestCase):
    def _app(self, workspace):
        from main import MainApp

        app = MainApp.__new__(MainApp)
        app.workspace = workspace
        app.combo_library_memory_mode = FakeVar("Auto (50% RAM)")
        app.entry_library_memory = FakeEntry("32768")
        app.memory_resolved_var = FakeVar()
        app._memory_snapshot = lambda: {
            "total_mb": 64000,
            "available_mb": 42000,
        }
        return app

    def test_workspace_round_trip_for_all_modes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "workspace.json")
            workspace = Workspace(tmp, path)
            app = self._app(workspace)

            auto = app.collect_workspace({})
            self.assertEqual(auto["max_memory_mode"], "auto")
            self.assertIsNone(auto["max_memory_mb"])
            workspace.update(auto)
            workspace.save()

            app.combo_library_memory_mode.set("Custom")
            app.entry_library_memory.set("2048")
            custom = app.collect_workspace({})
            self.assertEqual(custom["max_memory_mode"], "custom")
            self.assertEqual(custom["max_memory_mb"], 2048)

            app.combo_library_memory_mode.set("Unlimited")
            unlimited = app.collect_workspace({})
            self.assertEqual(unlimited["max_memory_mode"], "unlimited")
            self.assertEqual(unlimited["max_memory_mb"], 0)

            workspace.data = custom
            workspace.save()
            loaded = Workspace(tmp, path)
            restored = self._app(loaded)
            restored.apply_workspace({})
            self.assertEqual(
                restored.combo_library_memory_mode.get(), "Custom")
            self.assertEqual(restored.entry_library_memory.get(), "2048")


class MainCommandMemoryTests(unittest.TestCase):
    def _app(self):
        from main import MainApp

        app = MainApp.__new__(MainApp)
        app._resolved_memory_limit = lambda: 4096
        app._log_memory_limit = lambda _limit: None
        app.progress_frame = FakeGrid()
        app.progress_var = FakeVar()
        app.progress_label = FakeVar()
        return app

    def test_build_index_and_library_commands_include_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            genome = os.path.join(tmp, "genome.fa")
            bed = os.path.join(tmp, "regions.bed")
            with open(genome, "w", encoding="utf-8") as handle:
                handle.write(">chr1\nACGTACGTACGT\n")
            with open(bed, "w", encoding="utf-8") as handle:
                handle.write("chr1\t0\t12\tregion1\n")

            app = self._app()
            app.entry_library_genome = FakeEntry(genome)
            app.entry_library_output = FakeEntry(tmp)
            app.entry_library_index = FakeEntry("")
            with mock.patch("main.run_subprocess") as run:
                app.build_library_index()
            build_cmd = run.call_args.args[1]
            self.assertEqual(
                build_cmd[build_cmd.index("--max-memory-mb") + 1], "4096")

            app.entry_library_bed = FakeEntry(bed)
            app.entry_library_spacer = FakeEntry("20")
            app.entry_library_pam = FakeEntry("NGG")
            app.combo_library_preset = FakeVar("cas9")
            app.combo_library_pam_side = FakeVar("3prime")
            app.combo_library_search = FakeVar("indexed")
            app.entry_library_max_mismatch = FakeEntry("4")
            app.combo_library_on_target = FakeVar("cropsr")
            app.combo_library_off_target = FakeVar("cfd")
            app.entry_library_blastdb = FakeEntry("")
            with mock.patch("main.run_subprocess") as run:
                app.run_library_pipeline()
            library_cmd = run.call_args.args[1]
            self.assertEqual(
                library_cmd[library_cmd.index("--max-memory-mb") + 1],
                "4096",
            )


if __name__ == "__main__":
    unittest.main()
