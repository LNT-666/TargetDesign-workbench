#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Adapter for the standalone native indexed off-target engine."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Dict, Optional

from utils.child_process import (
    TERMINATE_GRACE_S, popen_kwargs, register_child, terminate_process_tree,
    unregister_child,
)


SUPPORTED_INDEX_FORMAT = 1
SUPPORTED_VERSION_PREFIX = "offtarget-engine 0.1.0"

# Wall-clock budget for one native command, in seconds. Off by default: a
# whole-genome bulge search can legitimately run for hours.
TIMEOUT_ENV = "PROGRAMFILE_OFFTARGET_TIMEOUT_S"

# ``build-index`` prints nothing until it finishes, so the adapter emits its
# own heartbeat while a build runs.
BUILD_HEARTBEAT_S = 60.0

# How often the streaming loop wakes up to check the clock.
POLL_INTERVAL_S = 0.25


class NativeEngineError(RuntimeError):
    """A native command failed before its caller could accept the result."""

    def __init__(self, command, returncode, stderr, emitted_hits=False):
        self.command = list(command or [])
        self.returncode = int(returncode)
        self.stderr = str(stderr or "")
        self.emitted_hits = bool(emitted_hits)
        match = re.search(r"\[([A-Z0-9_]+)\]", self.stderr)
        self.error_code = match.group(1) if match else ""
        message = (
            "native offtarget-engine failed during %s (exit %d): %s"
            % (
                self.command[1] if len(self.command) > 1 else "command",
                self.returncode,
                self.stderr[-4096:].strip() or "(no stderr)",
            )
        )
        super().__init__(message)

    @property
    def is_memory_limit(self):
        return self.error_code in (
            "MEMORY_LIMIT_EXCEEDED",
            "MEMORY_LIMIT_CANCELLED",
        )


class NativeEngineTimeout(RuntimeError):
    """Raised when a native command exceeds its configured timeout.

    This is deliberately not a ``NativeEngineError``: a timed-out search must
    not be silently retried by the much slower pure-Python implementation.
    """

    error_code = "TIMEOUT"

    def __init__(self, command, timeout_s):
        self.command = list(command or [])
        self.timeout_s = float(timeout_s or 0.0)
        name = self.command[1] if len(self.command) > 1 else "command"
        super().__init__(
            "native offtarget-engine %s exceeded its %.0f s timeout; raise "
            "the timeout or disable it for long whole-genome runs"
            % (name, self.timeout_s))


class MemoryLimitExceededError(RuntimeError):
    """Raised when a native memory limit must not trigger Python fallback."""

    error_code = "MEMORY_LIMIT_EXCEEDED"


def _root_dir():
    return Path(__file__).resolve().parents[2]


def _binary_name():
    return "offtarget-engine.exe" if os.name == "nt" else "offtarget-engine"


def find_binary():
    """Return the configured or bundled native binary path, if present."""
    configured = os.environ.get("PROGRAMFILE_OFFTARGET_NATIVE")
    if configured:
        path = Path(configured).expanduser()
        if path.is_file():
            return str(path)
        found = shutil.which(str(path))
        if found:
            return found
        return None
    bundled = _root_dir() / "native" / "bin" / _binary_name()
    if bundled.is_file():
        return str(bundled)
    return shutil.which(_binary_name())


def _mode():
    return (
        os.environ.get("PROGRAMFILE_NATIVE_INDEXED") or "auto"
    ).strip().lower()


def native_enabled(binary=None):
    """Resolve the native-indexed feature flag.

    ``auto`` is the default and enables native when a binary is discoverable.
    Set ``PROGRAMFILE_NATIVE_INDEXED=0`` to force the Python implementation.
    """
    mode = _mode()
    if mode in ("0", "false", "off", "no", "disabled"):
        return False
    if mode in ("1", "true", "on", "yes", "enabled"):
        return True
    if mode == "auto":
        return bool(binary or find_binary())
    return False


def native_fallback_enabled():
    """Return whether an early native failure may retry Python."""
    value = (
        os.environ.get("PROGRAMFILE_NATIVE_INDEXED_FALLBACK") or "1"
    ).strip().lower()
    return value in ("1", "true", "on", "yes", "enabled")


def probe_binary(binary=None):
    """Return ``(ok, path_or_reason)`` after checking version capabilities."""
    binary = binary or find_binary()
    if not binary:
        return False, "native offtarget-engine binary not found"
    try:
        result = subprocess.run(
            [binary, "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=15,
        )
    except Exception as exc:
        return False, "cannot run native offtarget-engine: %s" % exc
    if result.returncode != 0:
        return False, "native offtarget-engine --version failed: %s" % (
            result.stderr.strip() or result.stdout.strip()
        )
    version = result.stdout.strip()
    if not version.startswith(SUPPORTED_VERSION_PREFIX):
        return False, "unsupported native offtarget-engine version: %s" % (
            version
        )
    if "index-format=%d" % SUPPORTED_INDEX_FORMAT not in version:
        return False, "native engine does not support index format 1"
    return True, binary


def resolve_timeout_s(timeout_s=None):
    """Resolve the effective timeout: explicit value, env var, or ``None``."""
    raw = os.environ.get(TIMEOUT_ENV) if timeout_s is None else timeout_s
    if raw is None or raw == "":
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


class _LineReader(threading.Thread):
    """Drain one text pipe line by line into ``sink``."""

    def __init__(self, stream, sink, label):
        super().__init__(name="offtarget-%s" % label, daemon=True)
        self.stream = stream
        self.sink = sink
        self.error = None
        self.done = threading.Event()

    def run(self):
        try:
            for line in self.stream:
                if self.sink is None:
                    continue
                try:
                    self.sink(line)
                except BaseException as exc:
                    # A failing consumer aborts the command instead of
                    # silently dropping the rest of the stream.
                    self.error = exc
                    break
        except Exception:
            # A broken pipe just means the engine died; the exit code and
            # stderr carry the real error.
            pass
        finally:
            try:
                self.stream.close()
            except Exception:
                pass
            self.done.set()


def _run_streaming(command, on_line, timeout_s=None, heartbeat_s=None,
                   on_heartbeat=None):
    """Run ``command``, feeding stdout lines to ``on_line`` while it runs.

    Returns ``(returncode, stderr_text)``. stdout is handed to the callback as
    it arrives, so a caller can report progress during a multi-hour search
    instead of after it ends. stderr is drained on a reader thread so a chatty
    engine cannot deadlock on a full pipe. The child runs in its own process
    group and is terminated on every exit path, including exceptions raised by
    ``on_line`` or ``on_heartbeat``.
    """
    try:
        proc = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            **popen_kwargs()
        )
    except OSError as exc:
        raise NativeEngineError(
            command, 127, "cannot start native engine: %s" % exc) from exc
    register_child(proc)
    stdout_reader = _LineReader(proc.stdout, on_line, "stdout")
    stderr_lines = []
    stderr_reader = _LineReader(proc.stderr, stderr_lines.append, "stderr")
    stdout_reader.start()
    stderr_reader.start()
    started = time.monotonic()
    last_heartbeat = started
    deadline = None if timeout_s is None else started + float(timeout_s)
    timed_out = False
    stalled = False
    aborted = False
    try:
        while not stdout_reader.done.wait(POLL_INTERVAL_S):
            now = time.monotonic()
            if deadline is not None and now >= deadline:
                timed_out = True
                break
            if on_heartbeat is not None and heartbeat_s and \
                    now - last_heartbeat >= heartbeat_s:
                last_heartbeat = now
                on_heartbeat(now - started)
        if stdout_reader.error is not None:
            aborted = True
    finally:
        try:
            if proc.poll() is None:
                if not timed_out and not aborted:
                    try:
                        proc.wait(timeout=TERMINATE_GRACE_S)
                    except subprocess.TimeoutExpired:
                        stalled = True
                if proc.poll() is None:
                    terminate_process_tree(proc)
        finally:
            stdout_reader.join(timeout=TERMINATE_GRACE_S)
            stderr_reader.join(timeout=TERMINATE_GRACE_S)
            unregister_child(proc)
    stderr_text = "".join(stderr_lines)
    if aborted:
        raise stdout_reader.error
    if timed_out:
        raise NativeEngineTimeout(command, timeout_s)
    if stalled:
        raise NativeEngineError(
            command, -1,
            "native engine did not exit after closing stdout: %s"
            % (stderr_text[-4096:] or "(no stderr)"))
    return proc.returncode, stderr_text


def _run_json_command(command, emitted_hits=False, timeout_s=None):
    lines = []
    returncode, stderr_text = _run_streaming(
        command, lines.append, timeout_s=resolve_timeout_s(timeout_s))
    if returncode != 0:
        raise NativeEngineError(command, returncode, stderr_text, emitted_hits)
    try:
        return json.loads("".join(lines))
    except json.JSONDecodeError as exc:
        raise NativeEngineError(
            command, returncode,
            "invalid JSON output: %s" % exc, emitted_hits)


def inspect_index(binary, genome_path, index_prefix, timeout_s=None):
    """Validate ``index_prefix`` against a FASTA using the native reader."""
    return _run_json_command([
        binary,
        "inspect-index",
        "--genome", os.path.abspath(genome_path),
        "--index", os.path.abspath(index_prefix),
        "--json",
    ], timeout_s=timeout_s)


def build_index(binary, genome_path, index_prefix, k=12, threads=None,
                force=False, max_memory_mb=None, log=None,
                progress_callback=None, timeout_s=None):
    """Build a v1 index with the native producer.

    ``build-index`` prints its report only when it finishes, so an optional
    heartbeat is emitted while it runs: without one a whole-genome build looks
    hung for the ~25 minutes it takes.
    """
    command = [
        binary,
        "build-index",
        "--genome", os.path.abspath(genome_path),
        "--prefix", os.path.abspath(index_prefix),
        "--k", str(int(k)),
    ]
    if threads:
        command.extend(["--threads", str(int(threads))])
    if force:
        command.append("--force")
    if max_memory_mb is not None:
        command.extend(["--max-memory-mb", str(int(max_memory_mb))])
    lines = []

    def on_heartbeat(elapsed):
        if log:
            log("index build: %.0f s elapsed" % elapsed)
        if progress_callback is not None:
            progress_callback(elapsed)

    heartbeat = on_heartbeat if (log or progress_callback) else None
    returncode, stderr_text = _run_streaming(
        command, lines.append, timeout_s=resolve_timeout_s(timeout_s),
        heartbeat_s=BUILD_HEARTBEAT_S if heartbeat else None,
        on_heartbeat=heartbeat)
    if returncode != 0:
        raise NativeEngineError(command, returncode, stderr_text)
    try:
        return json.loads("".join(lines))
    except json.JSONDecodeError as exc:
        raise NativeEngineError(
            command, returncode, "invalid JSON output: %s" % exc)


def search(binary, genome_path, index_prefix, guides, max_mismatch=4,
           max_bulge=0, seed_len=12, seed_mismatch=None,
           seed_mismatch_max=None, pam=None, pam_side="3prime",
           threads=None, cache_genome=None, progress=False,
           max_memory_mb=None, progress_callback=None, timeout_s=None):
    """Run the native search and return ``(hits_by_qid, report)``.

    ``progress_callback(done, total, qid)`` is invoked for every JSONL
    ``progress`` event while the engine is still running, so a front end can
    show live progress instead of waiting for the process to exit.
    """
    guide_file = tempfile.NamedTemporaryFile(
        mode="w", suffix=".tsv", delete=False, encoding="utf-8",
        newline="")
    try:
        guide_file.write("qid\tguide_seq\n")
        for index, guide in enumerate(guides):
            qid = guide.get("qid") or guide.get("seq_id") or \
                "guide_%d" % index
            sequence = guide.get("guide_seq") or \
                guide.get("spacer_seq") or ""
            guide_file.write("%s\t%s\n" % (qid, sequence))
        guide_file.close()

        command = [
            binary,
            "search",
            "--genome", os.path.abspath(genome_path),
            "--index", os.path.abspath(index_prefix),
            "--guides", guide_file.name,
            "--max-mismatch", str(int(max_mismatch)),
            "--max-bulge", str(int(max_bulge)),
            "--seed-len", str(int(seed_len)),
            "--pam-side", str(pam_side or "3prime"),
            "--progress-every", "1" if progress else "0",
        ]
        if seed_mismatch is not None:
            command.extend(["--seed-mismatch", str(int(seed_mismatch))])
        if seed_mismatch_max is not None:
            command.extend(
                ["--seed-mismatch-max", str(int(seed_mismatch_max))])
        if pam:
            command.extend(["--require-pam", "--pam", str(pam)])
        if threads:
            command.extend(["--threads", str(int(threads))])
        if cache_genome is True:
            command.extend(["--cache-genome", "true"])
        elif cache_genome is False:
            command.extend(["--cache-genome", "false"])
        if max_memory_mb is not None:
            command.extend(["--max-memory-mb", str(int(max_memory_mb))])

        hits: Dict[str, list] = {}
        meta = {}
        summary = {}
        progress_events = []
        engine_errors = []
        parse_errors = []
        saw_hits = []

        def handle_event(line):
            text = line.strip()
            if not text:
                return
            try:
                event = json.loads(text)
            except json.JSONDecodeError as exc:
                parse_errors.append("invalid JSONL output: %s" % exc)
                return
            event_type = event.get("type")
            if event_type == "hit":
                saw_hits.append(True)
                hits.setdefault(event["qid"], []).append(event)
            elif event_type == "meta":
                meta.update(event)
            elif event_type == "summary":
                summary.update(event)
            elif event_type == "progress":
                progress_events.append(event)
                if progress_callback is not None:
                    progress_callback(
                        int(event.get("done") or 0),
                        int(event.get("total") or 0),
                        event.get("qid") or "")
            elif event_type == "error":
                engine_errors.append(
                    str(event.get("message") or "native search failed"))

        returncode, stderr_text = _run_streaming(
            command, handle_event, timeout_s=resolve_timeout_s(timeout_s))
        emitted_hits = bool(saw_hits)
        if engine_errors:
            raise NativeEngineError(
                command, returncode or 5, engine_errors[0], emitted_hits)
        if returncode != 0:
            raise NativeEngineError(
                command, returncode, stderr_text, emitted_hits)
        if parse_errors:
            raise NativeEngineError(
                command, returncode, parse_errors[0], emitted_hits)
        report = {
            "search_time_s": summary.get("search_time_s", 0.0),
            "search_memory_peak_mb": summary.get("memory_peak_mb", 0.0),
            "memory_limit_mb": int(
                summary.get("memory_limit_mb") or max_memory_mb or 0),
            "estimated_peak_mb": summary.get("estimated_peak_mb", 0.0),
            "observed_peak_mb": summary.get(
                "observed_peak_mb",
                summary.get("memory_peak_mb", 0.0),
            ),
            "guides": summary.get("guides", len(guides)),
            "hits": summary.get("hits", sum(len(v) for v in hits.values())),
            "candidates": summary.get("candidates", 0),
            "seed_len": int(seed_len),
            "seed_mm": seed_mismatch,
            "seed_plan_guaranteed": bool(
                summary.get("seed_plan_guaranteed", False)),
            "exhaustive_seed_plan": bool(
                summary.get("exhaustive_seed_plan", False)),
            "sequence_cache": bool(
                summary.get("sequence_cache", cache_genome is True)),
            "implementation": "native-cpp",
            "native_index_k": meta.get("index_k"),
            "progress_events": progress_events,
        }
        return hits, report
    finally:
        try:
            os.unlink(guide_file.name)
        except OSError:
            pass
