#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the off-target engine hardening tasks.

These cover the off-target engine hardening work, plus the one
gap left open originally (the CONFIRM_REQUIRED handshake over a real child).

* Task 1 - native search progress must stream while the engine runs.
* Task 2 - no orphaned engine processes; an opt-in timeout that does not
  silently degrade to the pure-Python implementation.
* Task 3 - index paths are namespaced by k and index builds are serialized.
* Task 4 - GGGenome puts the mismatch budget in the URL path (a ``?mismatch=``
  query parameter is ignored by the service) and surfaces API errors instead
  of reporting "no off-targets".
* Task 5 - entry points report a silent pure-Python fallback on stdout.
* Auto rules - a failing ``--engine auto`` candidate moves on to the next
  candidate engine (and never into the pure-Python index).
"""

import ast
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.parse
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHARED = os.path.join(ROOT, "shared")
sys.path.insert(0, SHARED)

from design.pattern_runner import (  # noqa: E402
    PatternRunner, PipelineStep, RunnerConfig,
)
from design.pattern_spec import (  # noqa: E402
    MotifSpec, PatternKind, PatternSpec, Side,
)
from search import native_offtarget, offtarget_backend  # noqa: E402
from search.offtarget_backend import (  # noqa: E402
    GGGenomeBackend, IndexedBackend, SearchParams, index_build_lock,
    run_backend,
)
from utils import child_process  # noqa: E402


GUIDE = "GCCTCTTTCCCACCCACCTT"

# A stand-in native engine: it reports one progress event and then blocks
# until the test creates the gate file. That makes the callback observable
# while the child is provably still running.
GATED_CHILD = r"""
import os, sys, time
print('{"type":"progress","done":1,"total":2,"qid":"g0"}', flush=True)
sentinel = sys.argv[1]
deadline = time.time() + 120
while not os.path.exists(sentinel) and time.time() < deadline:
    time.sleep(0.05)
print('{"type":"summary","guides":2,"hits":0}', flush=True)
"""

SLEEPING_CHILD = "import time; time.sleep(120)"


def gated_command(sentinel):
    return [sys.executable, "-u", "-c", GATED_CHILD, sentinel]


def sleeping_command():
    return [sys.executable, "-u", "-c", SLEEPING_CHILD]


def process_state(pid):
    """Return the /proc state letter, or None when the pid is gone."""
    try:
        with open("/proc/%d/stat" % pid, "r", encoding="utf-8") as handle:
            return handle.read().rsplit(")", 1)[1].split()[0]
    except (OSError, IndexError):
        return None


class NativeStreamingTests(unittest.TestCase):
    """Task 1: progress reaches the caller before the engine exits."""

    def test_progress_callback_runs_while_the_child_is_alive(self):
        workdir = tempfile.mkdtemp(prefix="oft-stream-")
        sentinel = os.path.join(workdir, "gate")
        lines = []
        alive_during_callback = []

        def on_line(line):
            lines.append(line)
            alive_during_callback.extend(child_process.active_children())
            if not os.path.exists(sentinel):
                with open(sentinel, "w", encoding="utf-8") as handle:
                    handle.write("go")

        returncode, stderr_text = native_offtarget._run_streaming(
            gated_command(sentinel), on_line)

        self.assertEqual(returncode, 0, stderr_text)
        self.assertTrue(
            any("progress" in line for line in lines),
            "no progress event reached the callback: %r" % (lines,))
        self.assertTrue(
            alive_during_callback,
            "the callback only ran after the engine had already exited")
        self.assertEqual(child_process.active_children(), [])

    def test_heartbeat_fires_while_an_index_build_is_silent(self):
        # build-index prints nothing until it finishes, so the adapter emits
        # its own heartbeat to keep the process observable.
        heartbeats = []
        returncode, _stderr = native_offtarget._run_streaming(
            [sys.executable, "-u", "-c", "import time; time.sleep(1.5)"],
            lambda line: None,
            heartbeat_s=0.25,
            on_heartbeat=heartbeats.append)
        self.assertEqual(returncode, 0)
        self.assertTrue(heartbeats, "no heartbeat was emitted")
        self.assertEqual(child_process.active_children(), [])


class ProcessLifetimeTests(unittest.TestCase):
    """Task 2: a timed-out or aborted engine must not survive the parent."""

    def test_timeout_raises_and_is_not_a_python_fallback(self):
        started = time.monotonic()
        with self.assertRaises(native_offtarget.NativeEngineTimeout) as caught:
            native_offtarget._run_streaming(
                sleeping_command(), lambda line: None, timeout_s=1.0)
        self.assertLess(time.monotonic() - started, 60)
        self.assertEqual(caught.exception.error_code, "TIMEOUT")
        # IndexedBackend only falls back on NativeEngineError, so a timeout
        # must not be one: the pure-Python retry would be far slower.
        self.assertNotIsInstance(
            caught.exception, native_offtarget.NativeEngineError)
        self.assertEqual(child_process.active_children(), [])

    def test_indexed_backend_propagates_a_timeout(self):
        workdir = tempfile.mkdtemp(prefix="oft-timeout-")
        params = SearchParams(
            max_mismatch=1, max_bulge=0, extra={"k": 12}, output_dir=workdir)
        backend = IndexedBackend()
        timeout_error = native_offtarget.NativeEngineTimeout(
            ["offtarget-engine", "search"], 1.0)
        with mock.patch(
                "search.native_offtarget.native_enabled",
                return_value=True), mock.patch(
                "search.native_offtarget.probe_binary",
                return_value=(True, "offtarget-engine")), mock.patch(
                "search.offtarget_backend.os.path.getsize",
                return_value=1000), mock.patch.object(
                backend, "_search_native", side_effect=timeout_error), \
                mock.patch.object(backend, "_search_python") as fallback:
            with self.assertRaises(native_offtarget.NativeEngineTimeout):
                backend.search(
                    [{"qid": "g0", "guide_seq": GUIDE}], "genome.fa", params)
        fallback.assert_not_called()

    def test_failing_consumer_stops_and_reaps_the_engine(self):
        sentinel = os.path.join(tempfile.mkdtemp(prefix="oft-abort-"), "gate")
        children = []
        real_register = child_process.register_child

        def record(proc):
            children.append(proc)
            return real_register(proc)

        def explode(_line):
            raise RuntimeError("consumer failed")

        with mock.patch(
                "search.native_offtarget.register_child",
                side_effect=record):
            with self.assertRaises(RuntimeError) as caught:
                native_offtarget._run_streaming(
                    gated_command(sentinel), explode)
        self.assertEqual(str(caught.exception), "consumer failed")
        self.assertTrue(children)
        self.assertIsNotNone(children[0].poll())
        self.assertEqual(child_process.active_children(), [])

    @unittest.skipIf(os.name == "nt", "PR_SET_PDEATHSIG is Linux-only")
    def test_parent_death_kills_the_engine(self):
        workdir = tempfile.mkdtemp(prefix="oft-orphan-")
        pidfile = os.path.join(workdir, "engine.pid")
        parent = (
            "import sys\n"
            "sys.path.insert(0, sys.argv[1])\n"
            "from search import native_offtarget\n"
            "child = [sys.executable, '-u', '-c',\n"
            "         'import os,sys,time\\n'\n"
            "         'open(sys.argv[1], \"w\").write(str(os.getpid()))\\n'\n"
            "         'time.sleep(120)', sys.argv[2]]\n"
            "native_offtarget._run_streaming(child, lambda line: None)\n"
        )
        supervisor = subprocess.Popen(
            [sys.executable, "-u", "-c", parent, SHARED, pidfile],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            deadline = time.time() + 60
            while not os.path.exists(pidfile) and time.time() < deadline:
                time.sleep(0.05)
            self.assertTrue(
                os.path.exists(pidfile), "the engine never reported its pid")
            with open(pidfile, "r", encoding="utf-8") as handle:
                engine_pid = int(handle.read().strip())
            supervisor.kill()
            supervisor.wait(timeout=30)
            deadline = time.time() + 30
            state = "?"
            while time.time() < deadline:
                state = process_state(engine_pid)
                if state is None or state == "Z":
                    break
                time.sleep(0.1)
            self.assertIn(
                state, (None, "Z"),
                "engine %d outlived its parent (state %r)" % (engine_pid, state))
        finally:
            if supervisor.poll() is None:
                supervisor.kill()
                supervisor.wait(timeout=30)


class IndexNamespaceTests(unittest.TestCase):
    """Task 3: index files are k-specific and builds are serialized."""

    def test_index_prefix_is_namespaced_by_k(self):
        workdir = tempfile.mkdtemp(prefix="oft-index-")
        backend = IndexedBackend()
        params = SearchParams(max_mismatch=1, max_bulge=0, output_dir=workdir)
        prefix_12 = backend._index_prefix("genome.fa", params, k=12)
        prefix_13 = backend._index_prefix("genome.fa", params, k=13)
        self.assertTrue(prefix_12.endswith("genome.k12"), prefix_12)
        self.assertTrue(prefix_13.endswith("genome.k13"), prefix_13)
        self.assertNotEqual(prefix_12, prefix_13)
        self.assertEqual(
            os.path.dirname(prefix_12), os.path.join(workdir, "genome_index"))

    def test_explicit_index_path_overrides_the_k_namespace(self):
        workdir = tempfile.mkdtemp(prefix="oft-index-")
        backend = IndexedBackend()
        params = SearchParams(
            output_dir=workdir,
            index_path=os.path.join(workdir, "shared.ggi"))
        self.assertEqual(
            backend._index_prefix("genome.fa", params, k=12),
            os.path.join(workdir, "shared"))

    def test_second_build_waits_for_the_first(self):
        workdir = tempfile.mkdtemp(prefix="oft-lock-")
        prefix = os.path.join(workdir, "genome.k12")
        with index_build_lock(prefix, timeout_s=1.0):
            with self.assertRaises(RuntimeError) as caught:
                with index_build_lock(prefix, timeout_s=0.3):
                    pass
            self.assertIn("being built by another run", str(caught.exception))
        # The lock is released, so the next run can build normally.
        with index_build_lock(prefix, timeout_s=1.0):
            pass

    def test_a_valid_index_is_reused_instead_of_rebuilt(self):
        workdir = tempfile.mkdtemp(prefix="oft-reuse-")
        prefix = os.path.join(workdir, "genome.k12")
        params = SearchParams(
            max_mismatch=1, max_bulge=0, extra={"k": 12}, output_dir=workdir)
        backend = IndexedBackend()
        with mock.patch(
                "search.native_offtarget.probe_binary",
                return_value=(True, "offtarget-engine")), mock.patch(
                "search.native_offtarget.inspect_index",
                return_value={"valid": True, "k": 12}) as inspect, mock.patch(
                "search.native_offtarget.build_index") as build, mock.patch(
                "search.native_offtarget.search",
                return_value=({}, {})) as search:
            hits = backend._search_native(
                [{"qid": "g0", "guide_seq": GUIDE}], "genome.fa", params,
                prefix, 12)
        inspect.assert_called_once()
        build.assert_not_called()
        search.assert_called_once()
        self.assertEqual(hits, {})
        self.assertTrue(backend.last_report["reused"])


class GGGenomeBudgetTests(unittest.TestCase):
    """Task 4: the mismatch budget must reach the API, errors must surface."""

    @staticmethod
    def _response(body):
        response = mock.Mock()
        response.read.return_value = body.encode("utf-8")
        response.__enter__ = mock.Mock(return_value=response)
        response.__exit__ = mock.Mock(return_value=False)
        return response

    def _search(self, body, params, capture=None):
        def fake_urlopen(request, timeout=None):
            if capture is not None:
                capture["url"] = request.full_url
            return self._response(body)

        backend = GGGenomeBackend()
        with mock.patch(
                "search.offtarget_backend.urllib.request.urlopen",
                side_effect=fake_urlopen):
            backend.search(
                [{"qid": "g0", "guide_seq": GUIDE}], "unused.fa", params)
        return backend

    def test_mismatch_budget_is_a_url_path_segment(self):
        capture = {}
        backend = self._search(
            "", SearchParams(max_mismatch=2, max_bulge=1, genome_build="hg38"),
            capture)
        self.assertEqual(
            urllib.parse.urlparse(capture["url"]).path,
            "/hg38/3/%s.txt" % GUIDE)
        self.assertNotIn("mismatch=", capture["url"])
        self.assertEqual(backend.last_report["mismatch_budget"], 3)
        self.assertFalse(backend.last_report["exact_only"])

    def test_exact_searches_are_flagged_exact_only(self):
        capture = {}
        backend = self._search(
            "", SearchParams(max_mismatch=0, max_bulge=0, genome_build="hg38"),
            capture)
        self.assertEqual(
            urllib.parse.urlparse(capture["url"]).path,
            "/hg38/0/%s.txt" % GUIDE)
        self.assertTrue(backend.last_report["exact_only"])

    def test_api_error_raises_instead_of_reporting_no_hits(self):
        with self.assertRaises(RuntimeError) as caught:
            self._search(
                "### ERROR : number of mismatches/gaps should be 25% or "
                "less ###\n",
                SearchParams(max_mismatch=4, max_bulge=4, genome_build="hg38"))
        self.assertIn("25% or less", str(caught.exception))
        self.assertIn("g0", str(caught.exception))


class FallbackReportingTests(unittest.TestCase):
    """Task 5: a silent pure-Python fallback must reach stdout/stderr."""

    CALLER_FILES = (
        "basic/blast.py",
        "shared/design/library_pipeline.py",
        "tools/benchmark_all_engines.py",
        "tools/benchmark_search.py",
        "tools/search_indexed.py",
        "Target_xbp_Target/analyze_complex_scores.py",
        "Target_xbp_Y_zbp_Target/blast_combined.py",
    )

    def test_engine_entry_points_pass_a_log_callback(self):
        missing = []
        for relative in self.CALLER_FILES:
            path = os.path.join(ROOT, relative)
            with open(path, encoding="utf-8") as handle:
                tree = ast.parse(handle.read(), path)
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                if not isinstance(func, ast.Attribute) or \
                        func.attr != "search":
                    continue
                keywords = node.keywords
                if any(keyword.arg == "log" for keyword in keywords):
                    continue
                # ``**kwargs`` forwarding is accepted: library_pipeline.py
                # carries ``log`` in ``search_kwargs`` for the only engine
                # that can fall back (indexed).
                if any(keyword.arg is None for keyword in keywords):
                    continue
                missing.append("%s:%d" % (relative, node.lineno))
        self.assertEqual(
            missing, [], "engine callers without a log= callback")

    def test_search_indexed_prints_a_refused_fallback_reason(self):
        workdir = tempfile.mkdtemp(prefix="oft-cli-")
        fasta = os.path.join(workdir, "genome.fa")
        with open(fasta, "w", encoding="utf-8") as handle:
            handle.write(">chr1\n" + "ACGT" * 80 + "\n")
        guides = os.path.join(workdir, "guides.tsv")
        with open(guides, "w", encoding="utf-8") as handle:
            handle.write("qid\tguide_seq\ng0\t%s\n" % GUIDE)
        env = dict(os.environ)
        env["PROGRAMFILE_NATIVE_INDEXED"] = "0"
        env["CRISPR_OFFTARGET_PYTHON_FALLBACK"] = "deny"
        completed = subprocess.run(
            [sys.executable, os.path.join(ROOT, "tools", "search_indexed.py"),
             guides, fasta, os.path.join(workdir, "out"),
             "--max-mismatch", "1", "--max-bulge", "0"],
            cwd=ROOT, env=env, capture_output=True, text=True, timeout=600)
        output = completed.stdout + completed.stderr
        self.assertEqual(completed.returncode, 3, output)
        self.assertIn("python fallback", output.lower())
        self.assertIn("native off-target engine is unavailable", output)


class ConfirmHandshakeEndToEndTests(unittest.TestCase):
    """Section 2 gap: CONFIRM_REQUIRED answered over a real child process."""

    CHILD = r"""
import sys
print('CONFIRM_REQUIRED: python_fallback|stub engine missing', flush=True)
answer = sys.stdin.readline().strip().lower()
print('ANSWER:%s' % answer, flush=True)
sys.exit(0 if answer in ('y', 'yes', '1', 'true') else 4)
"""

    def _run(self, decision):
        spec = PatternSpec(
            kind=PatternKind.SINGLE_MOTIF_FLANK,
            motif=MotifSpec("TTAT", 10, Side.UPSTREAM),
        )
        config = RunnerConfig(
            search_fasta="input.fa",
            genome_fasta="genome.fa",
            output_dir=tempfile.mkdtemp(prefix="oft-confirm-"),
        )
        runner = PatternRunner(spec, config)
        step = PipelineStep(
            name="stub off-target search",
            command=[sys.executable, "-u", "-c", self.CHILD],
        )
        lines = []
        with mock.patch.object(
                PatternRunner, "build_pipeline", return_value=[step]):
            code = runner.run_pipeline(on_line=lines.append, on_prompt=decision)
        return code, lines

    def test_approved_confirmation_is_written_to_the_child(self):
        prompts = []

        def approve(request):
            prompts.append(request)
            return True

        code, lines = self._run(approve)
        self.assertEqual(code, 0, lines)
        self.assertEqual(prompts[0]["kind"], "python_fallback")
        self.assertEqual(prompts[0]["reason"], "stub engine missing")
        self.assertIn("ANSWER:yes", lines)

    def test_declined_confirmation_reaches_the_child_as_no(self):
        code, lines = self._run(lambda request: False)
        self.assertEqual(code, 4, lines)
        self.assertIn("ANSWER:no", lines)


class AutoEngineChainTests(unittest.TestCase):
    """Auto rules: a failing candidate moves on to the next engine."""

    def setUp(self):
        self.workdir = tempfile.mkdtemp(prefix="oft-auto-")
        self.genome = os.path.join(self.workdir, "genome.fa")
        with open(self.genome, "w", encoding="utf-8") as handle:
            handle.write(">chr1\nACGTACGTACGTACGT\n")
        self.guides = [{"qid": "g0", "guide_seq": GUIDE}]

    def _backends(self, behaviours):
        class FakeBackend:
            def __init__(self, name, behaviour):
                self.name = name
                self.behaviour = behaviour
                self.last_report = {"engine": name}
                self.used_params = []
                self.calls = 0

            def available(self):
                return True, ""

            def search(self, guides, genome_fasta, params, genome=None,
                       log=None, progress_callback=None, **kwargs):
                self.calls += 1
                self.used_params.append(params)
                if isinstance(self.behaviour, Exception):
                    raise self.behaviour
                return {"g0": [{"qid": "g0", "engine": self.name}]}

        return {
            name: FakeBackend(name, behaviour)
            for name, behaviour in behaviours.items()
        }

    def _run(self, behaviours, order=("indexed", "blast"), params=None):
        backends = self._backends(behaviours)
        params = params or SearchParams(max_mismatch=4, max_bulge=0)
        lines = []
        result = None
        error = None
        with mock.patch.object(
                offtarget_backend, "auto_engine_candidates",
                return_value=list(order)), mock.patch.object(
                offtarget_backend, "get_backend",
                side_effect=lambda name: backends[name]):
            try:
                result = run_backend("auto", self.guides, self.genome, params,
                                     log=lines.append)
            except Exception as exc:  # noqa: BLE001 - reported to the caller
                error = exc
        return result, error, lines, backends

    def test_a_failed_engine_moves_on_to_the_next_candidate(self):
        error = native_offtarget.NativeEngineError(["x"], 1, "build failed")
        result, raised, lines, backends = self._run(
            {"indexed": error, "blast": None},
            params=SearchParams(max_mismatch=4, max_bulge=0,
                                extra={"engine_fallback": "allow"}))
        self.assertIsNone(raised)
        self.assertEqual(result["g0"][0]["engine"], "blast")
        self.assertEqual(backends["indexed"].calls, 1)
        self.assertEqual(backends["blast"].calls, 1)
        text = "\n".join(lines)
        self.assertIn("auto engine: running indexed", text)
        self.assertIn("auto engine: indexed failed:", text)
        self.assertIn("build failed", text)
        self.assertIn("auto engine: running blast", text)
        report = backends["blast"].last_report
        self.assertEqual(report["engine_used"], "blast")
        self.assertEqual(report["fallback_from"], "indexed")
        self.assertIn("build failed", report["fallback_reason"])

    def test_the_successful_candidate_publishes_params_extra_report(self):
        error = native_offtarget.NativeEngineError(["x"], 1, "build failed")
        params = SearchParams(max_mismatch=4, max_bulge=0,
                              extra={"engine_fallback": "allow"})
        result, raised, lines, backends = self._run(
            {"indexed": error, "blast": None}, params=params)
        self.assertIsNone(raised)
        self.assertEqual(result["g0"][0]["engine"], "blast")
        report = params.extra["engine_run_report"]
        self.assertIs(report, backends["blast"].last_report)
        self.assertEqual(report["engine_used"], "blast")
        self.assertEqual(report["fallback_from"], "indexed")
        self.assertEqual(report["fallback_attempts"][0]["engine"], "indexed")
        self.assertTrue(report["fallback_attempts"][0]["started"])

    def test_the_chain_stops_when_the_switch_is_refused(self):
        error = native_offtarget.NativeEngineError(["x"], 1, "build failed")
        result, raised, lines, backends = self._run(
            {"indexed": error, "blast": None},
            params=SearchParams(max_mismatch=4, max_bulge=0,
                                extra={"engine_fallback": "deny"}))
        self.assertIsNone(result)
        self.assertIsInstance(raised, RuntimeError)
        self.assertIn("could not run an off-target search",
                      str(raised))
        self.assertEqual(backends["blast"].calls, 0)
        self.assertIn("refused by policy", "\n".join(lines))

    def test_the_indexed_candidate_never_degrades_to_python(self):
        error = native_offtarget.NativeEngineError(["x"], 1, "no engine")
        params = SearchParams(max_mismatch=4, max_bulge=0,
                              extra={"engine_fallback": "allow"})
        self._run({"indexed": error, "blast": None}, params=params)
        attempted = None
        # The chain hands the engine a copy, never the caller's params object.
        _, _, _, backends = self._run({"indexed": error, "blast": None},
                                      params=params)
        attempted = backends["indexed"].used_params[0]
        self.assertEqual(attempted.extra["python_fallback"], "deny")
        self.assertNotIn("python_fallback", params.extra)
        self.assertNotIn("python_fallback_confirm", attempted.extra)

    def test_a_memory_limit_stops_the_chain(self):
        class MemoryLimit(RuntimeError):
            error_code = "MEMORY_LIMIT_EXCEEDED"

        result, raised, lines, backends = self._run(
            {"indexed": MemoryLimit("over budget"), "blast": None},
            params=SearchParams(max_mismatch=4, max_bulge=0,
                                extra={"engine_fallback": "allow"}))
        self.assertIsNone(result)
        self.assertIsInstance(raised, MemoryLimit)
        self.assertEqual(backends["blast"].calls, 0)
        self.assertIn("memory limit", "\n".join(lines))

    def _chain_backends(self, attempted):
        """Fake backends that record the attempt order and then fail."""

        def make_search(name, backend):
            def search(guides, genome_fasta, params, genome=None, log=None,
                       progress_callback=None, **kwargs):
                attempted.append(name)
                raise backend.behaviour

            return search

        backends = {}
        for name in ("exact", "blast", "indexed"):
            backend = self._backends(
                {name: RuntimeError("forced failure")})[name]
            backend.search = make_search(name, backend)
            backends[name] = backend
        return backends

    def _run_real_chain(self, params, native_available):
        """Run the chain with only the engine backends faked out.

        ``auto_engine_candidates`` is deliberately left in place: the
        assertion is about the order the runtime chain really asks for.
        """
        attempted = []
        backends = self._chain_backends(attempted)
        with mock.patch.object(
                offtarget_backend, "get_backend",
                side_effect=lambda name: backends[name]), \
                mock.patch.object(
                    offtarget_backend, "native_indexed_available",
                    return_value=native_available):
            with self.assertRaises(RuntimeError):
                run_backend("auto", self.guides, self.genome, params,
                            log=lambda message: None)
        return attempted

    def test_the_runtime_chain_follows_the_documented_order(self):
        params = SearchParams(max_mismatch=4, max_bulge=0,
                              extra={"engine_fallback": "allow"})
        self.assertEqual(
            self._run_real_chain(params, native_available=False),
            ["blast", "indexed", "exact"])
        self.assertEqual(
            self._run_real_chain(params, native_available=True),
            ["indexed", "blast", "exact"])
        bulged = SearchParams(max_mismatch=4, max_bulge=1,
                              max_bulge_explicit=True,
                              extra={"engine_fallback": "allow"})
        self.assertEqual(
            self._run_real_chain(bulged, native_available=False),
            ["blast", "exact", "indexed"])
        self.assertEqual(
            self._run_real_chain(bulged, native_available=True),
            ["indexed", "blast", "exact"])

    def test_default_params_are_ranked_with_the_auto_bulge_default(self):
        # SearchParams() defaults to max_bulge=1 without marking it explicit.
        # auto documents max_bulge=0, so the chain must both rank and run
        # with the mismatch-only order instead of the bulge order.
        params = SearchParams(extra={"engine_fallback": "allow"})
        self.assertEqual(params.max_bulge, 1)
        self.assertFalse(params.max_bulge_explicit)
        self.assertEqual(
            self._run_real_chain(params, native_available=False),
            ["blast", "indexed", "exact"])
        self.assertEqual(params.max_bulge, 0)
        self.assertIn("max_bulge_default_reason", params.extra)

    def test_an_explicit_resource_reports_why_nothing_else_was_tried(self):
        attempted = []
        backends = self._chain_backends(attempted)
        params = SearchParams(max_mismatch=4, max_bulge=0,
                              index_path="idx/prefix",
                              extra={"engine_fallback": "allow"})
        with mock.patch.object(
                offtarget_backend, "get_backend",
                side_effect=lambda name: backends[name]), \
                mock.patch.object(
                    offtarget_backend, "native_indexed_available",
                    return_value=False):
            with self.assertRaises(RuntimeError) as raised:
                run_backend("auto", self.guides, self.genome, params,
                            log=lambda message: None)
        self.assertEqual(attempted, ["indexed"])
        message = str(raised.exception)
        self.assertIn("--index-path was given", message)
        self.assertIn("--engine", message)

    def test_explicit_engines_do_not_enter_the_chain(self):
        backends = self._backends({"blast": None, "indexed": None})
        with mock.patch.object(
                offtarget_backend, "auto_engine_candidates",
                side_effect=AssertionError("the chain must not be used")), \
                mock.patch.object(
                offtarget_backend, "get_backend",
                side_effect=lambda name: backends[name]):
            result = run_backend("blast", self.guides, self.genome,
                                 SearchParams(max_mismatch=4, max_bulge=0))
        self.assertEqual(result["g0"][0]["engine"], "blast")
        self.assertEqual(backends["indexed"].calls, 0)


if __name__ == "__main__":
    unittest.main()
