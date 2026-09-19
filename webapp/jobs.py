#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""File-backed job store and single-slot executor for the local web app.

Every job lives in ``<repo>/webapp/jobs/<job_id>/`` and owns four things:

``params.json``   the request payload the job was created from
``status.json``   the record served by ``/api/jobs/<id>`` (see ``STATUS_FIELDS``)
``job.log``       the child/step output, streamed to the browser
``out/``          everything the job wrote on disk

At most ``max_concurrent`` heavy jobs run at a time (default: 1, matching the
desktop workbench, which runs one pipeline at a time). Jobs left behind by a
previous server process are marked ``interrupted`` instead of pretending to
still run.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
import uuid
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional


WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_JOBS_ROOT = os.path.join(WORKSPACE, "webapp", "jobs")

JOB_ID_RE = re.compile(r"^[a-z0-9-]{12}$")

QUEUED = "queued"
RUNNING = "running"
SUCCEEDED = "succeeded"
FAILED = "failed"
CANCELLED = "cancelled"
INTERRUPTED = "interrupted"
TERMINAL_STATUSES = (SUCCEEDED, FAILED, CANCELLED, INTERRUPTED)
ACTIVE_STATUSES = (QUEUED, RUNNING)

STATUS_FIELDS = (
    "job_id",
    "kind",
    "title",
    "status",
    "progress",
    "message",
    "returncode",
    "created",
    "started",
    "finished",
    "outputs",
)

LOG_TAIL_LINES = 40
INTERRUPTED_MESSAGE = "Interrupted by a server restart; submit it again to run."


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def valid_job_id(job_id: str) -> bool:
    return bool(JOB_ID_RE.match(str(job_id or "")))


def parse_progress_line(line: str):
    """Parse a child progress line.

    Returns ``("target", "i/n")`` for ``PROGRESS_TARGET: i/n``,
    ``("progress", percent, label)`` for ``PROGRESS: <label> <pct>`` and
    ``None`` for anything else.
    """
    text = (line or "").strip()
    if text.startswith("PROGRESS_TARGET:"):
        counter = text.split(":", 1)[1].strip()
        if re.fullmatch(r"\d+/\d+", counter):
            return ("target", counter)
        return None
    if not text.startswith("PROGRESS:"):
        return None
    parts = text.split()
    if len(parts) < 3:
        return None
    try:
        value = int(parts[-1])
    except ValueError:
        return None
    label = " ".join(parts[1:-1]) or parts[1]
    return ("progress", value, label)


class JobContext:
    """Handle a job body uses to log, report progress and stop itself."""

    def __init__(self, manager: "JobManager", job_id: str):
        self._manager = manager
        self._job_id = job_id
        self._job_dir = manager.job_dir(job_id)
        self._lock = threading.Lock()
        self._stop_hook: Optional[Callable[[], None]] = None
        self.cancelled = False
        self.result: Optional[Dict[str, Any]] = None
        self.outputs: Dict[str, Any] = {}

    @property
    def job_id(self) -> str:
        return self._job_id

    @property
    def job_dir(self) -> str:
        return self._job_dir

    @property
    def out_dir(self) -> str:
        return os.path.join(self._job_dir, "out")

    def set_stop_hook(self, hook: Callable[[], None]) -> None:
        """Register how to stop this job (child process or pipeline)."""
        with self._lock:
            self._stop_hook = hook
            already_cancelled = self.cancelled
        if already_cancelled:
            self._fire_stop(hook)

    def request_stop(self) -> None:
        with self._lock:
            self.cancelled = True
            hook = self._stop_hook
        if hook is not None:
            self._fire_stop(hook)

    @staticmethod
    def _fire_stop(hook: Callable[[], None]) -> None:
        try:
            hook()
        except Exception:
            pass

    def line(self, text: str) -> None:
        """Append one log line and mirror any progress protocol line."""
        text = "" if text is None else str(text)
        self._manager.append_log(self._job_dir, text.rstrip("\n") + "\n")
        parsed = parse_progress_line(text)
        if parsed is None:
            return
        if parsed[0] == "target":
            self.update(message="Analyzing target %s" % parsed[1])
        else:
            self.update(progress=int(parsed[1]), message=parsed[2])

    def progress(self, percent: int, message: Optional[str] = None) -> None:
        fields: Dict[str, Any] = {"progress": int(percent)}
        if message:
            fields["message"] = message
        self.update(**fields)

    def update(self, **fields) -> None:
        self._manager.update_status(self._job_dir, **fields)

    def set_result(self, payload: Dict[str, Any]) -> None:
        self.result = payload
        self._manager.write_json(
            os.path.join(self._job_dir, "result.json"), payload)

    @staticmethod
    def _resolve_output(value) -> Optional[str]:
        """Absolute path of one artefact, or ``None`` when it was not written."""
        text = str(value or "").strip()
        if not text:
            return None
        if os.path.exists(text):
            return os.path.abspath(text)
        # ``build-index`` reports its output prefix while the files on disk are
        # ``<prefix>.ggi`` / ``<prefix>.json`` (see search/genome_index.py:330),
        # so keep the prefix when a sibling artefact exists.
        parent = os.path.dirname(os.path.abspath(text))
        base_name = os.path.basename(text)
        try:
            names = os.listdir(parent)
        except OSError:
            return None
        for name in names:
            if name.startswith(base_name + "."):
                return os.path.abspath(text)
        return None

    def set_outputs(self, outputs) -> None:
        """Record the artefacts this job produced (task 1.4 ``outputs``)."""
        cleaned: Dict[str, str] = {}
        for key, value in dict(outputs or {}).items():
            resolved = self._resolve_output(value)
            if resolved:
                cleaned[str(key)] = resolved
        self.outputs = cleaned
        self._manager.update_status(self._job_dir, outputs=cleaned)

class JobManager:
    """Create, run, list and stop the local web jobs."""

    def __init__(self, jobs_root: Optional[str] = None, max_concurrent: int = 1):
        self.jobs_root = jobs_root or DEFAULT_JOBS_ROOT
        self.max_concurrent = max(1, int(max_concurrent))
        self._lock = threading.RLock()
        self._queue: List[str] = []
        self._pending: Dict[str, Dict[str, Any]] = {}
        self._contexts: Dict[str, JobContext] = {}
        self._dispatcher: Optional[threading.Thread] = None
        os.makedirs(self.jobs_root, exist_ok=True)
        self.mark_interrupted_jobs()

    # ---------------------------------------------------------------- paths

    def job_dir(self, job_id: str) -> str:
        if not valid_job_id(job_id):
            raise ValueError("invalid job id")
        return os.path.join(self.jobs_root, job_id)

    @staticmethod
    def _status_path(job_dir: str) -> str:
        return os.path.join(job_dir, "status.json")

    @staticmethod
    def _read_json(path: str):
        try:
            with open(path, "r", encoding="utf-8") as handle:
                return json.load(handle)
        except (OSError, ValueError):
            return None

    @staticmethod
    def write_json(path: str, payload) -> None:
        temp_path = path + ".tmp"
        with open(temp_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        os.replace(temp_path, path)

    def read_status(self, job_dir: str) -> Optional[Dict[str, Any]]:
        payload = self._read_json(self._status_path(job_dir))
        if not isinstance(payload, dict):
            return None
        if not payload.get("kind"):
            # Written by the retired library-only web app; leave it untouched.
            return None
        payload.setdefault("outputs", {})
        return payload

    def _write_status(self, job_dir: str, payload: Dict[str, Any]) -> None:
        self.write_json(self._status_path(job_dir), payload)

    def update_status(self, job_dir: str, **fields) -> Dict[str, Any]:
        with self._lock:
            status = self.read_status(job_dir) or {}
            status.update(fields)
            self._write_status(job_dir, status)
            return status

    @staticmethod
    def append_log(job_dir: str, text: str) -> None:
        try:
            with open(os.path.join(job_dir, "job.log"), "a",
                      encoding="utf-8", errors="replace") as handle:
                handle.write(text)
        except OSError:
            pass

    @staticmethod
    def read_log_text(job_dir: str) -> str:
        try:
            with open(os.path.join(job_dir, "job.log"), "r",
                      encoding="utf-8", errors="replace") as handle:
                return handle.read()
        except OSError:
            return ""

    def _log_tail(self, job_dir: str, lines: int = LOG_TAIL_LINES) -> str:
        text = self.read_log_text(job_dir)
        if not text:
            return ""
        return "\n".join(text.rstrip("\n").split("\n")[-lines:])

    # ----------------------------------------------------------------- jobs

    def create_job(
        self,
        kind: str,
        title: str,
        runner: Callable[[JobContext], int],
        params: Optional[Dict[str, Any]] = None,
        job_id: Optional[str] = None,
    ) -> str:
        """Persist a queued job and schedule its runner."""
        job_id = job_id or uuid.uuid4().hex[:12]
        job_dir = self.job_dir(job_id)
        os.makedirs(os.path.join(job_dir, "out"), exist_ok=True)
        payload = dict(params or {})
        payload["kind"] = kind
        payload["title"] = title
        self.write_json(os.path.join(job_dir, "params.json"), payload)
        with open(os.path.join(job_dir, "job.log"), "w", encoding="utf-8"):
            pass
        self._write_status(job_dir, {
            "job_id": job_id,
            "kind": kind,
            "title": title,
            "status": QUEUED,
            "progress": 1,
            "message": "Queued",
            "returncode": None,
            "created": _now(),
            "started": None,
            "finished": None,
            "outputs": {},
        })
        with self._lock:
            self._pending[job_id] = {"runner": runner}
            self._queue.append(job_id)
        self._ensure_dispatcher()
        return job_id

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        job_dir = self.job_dir(job_id)
        status = self.read_status(job_dir)
        if status is None:
            return None
        status = dict(status)
        status["log_tail"] = self._log_tail(job_dir)
        result = self._read_json(os.path.join(job_dir, "result.json"))
        if result is not None:
            status["result"] = result
        return status

    def job_params(self, job_id: str) -> Dict[str, Any]:
        job_dir = self.job_dir(job_id)
        payload = self._read_json(os.path.join(job_dir, "params.json"))
        return payload if isinstance(payload, dict) else {}

    def list_jobs(self) -> List[Dict[str, Any]]:
        jobs: List[Dict[str, Any]] = []
        try:
            names = os.listdir(self.jobs_root)
        except OSError:
            return jobs
        for name in names:
            if not valid_job_id(name):
                continue
            status = self.read_status(os.path.join(self.jobs_root, name))
            if status is None:
                continue
            jobs.append(status)
        jobs.sort(key=lambda item: (item.get("created") or "", item["job_id"]),
                  reverse=True)
        return jobs

    def read_log(self, job_id: str, offset: int = 0) -> Dict[str, Any]:
        job_dir = self.job_dir(job_id)
        text = self.read_log_text(job_dir)
        try:
            start = max(0, int(offset))
        except (TypeError, ValueError):
            start = 0
        if start > len(text):
            start = len(text)
        return {"offset": len(text), "text": text[start:]}

    def wait(self, job_id: str, timeout: Optional[float] = None,
             interval: float = 0.05) -> Optional[Dict[str, Any]]:
        """Block until a job reaches a terminal status (test helper)."""
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            status = self.get_job(job_id)
            if status is None or status.get("status") in TERMINAL_STATUSES:
                return status
            if deadline is not None and time.monotonic() >= deadline:
                return status
            time.sleep(interval)

    def cancel(self, job_id: str) -> Optional[Dict[str, Any]]:
        job_dir = self.job_dir(job_id)
        status = self.read_status(job_dir)
        if status is None:
            return None
        current = status.get("status")
        if current == QUEUED:
            with self._lock:
                self._queue = [item for item in self._queue if item != job_id]
                self._pending.pop(job_id, None)
            return self.update_status(
                job_dir,
                status=CANCELLED,
                message="Cancelled before it started",
                returncode=None,
                finished=_now(),
            )
        if current == RUNNING:
            with self._lock:
                context = self._contexts.get(job_id)
            if context is not None:
                context.request_stop()
            return self.update_status(job_dir, message="Stopping...")
        return status

    def mark_interrupted_jobs(self) -> int:
        """Flag jobs a previous server process left behind."""
        marked = 0
        try:
            names = os.listdir(self.jobs_root)
        except OSError:
            return 0
        for name in names:
            if not valid_job_id(name):
                continue
            job_dir = os.path.join(self.jobs_root, name)
            status = self.read_status(job_dir)
            if status is None:
                continue
            if status.get("status") not in ACTIVE_STATUSES:
                continue
            self.update_status(
                job_dir,
                status=INTERRUPTED,
                message=INTERRUPTED_MESSAGE,
                finished=_now(),
            )
            marked += 1
        return marked

    # ------------------------------------------------------------ execution

    def _ensure_dispatcher(self) -> None:
        with self._lock:
            if self._dispatcher is not None and self._dispatcher.is_alive():
                return
            self._dispatcher = threading.Thread(
                target=self._dispatch_loop,
                name="webapp-job-dispatch",
                daemon=True,
            )
            self._dispatcher.start()

    def _dispatch_loop(self) -> None:
        while True:
            with self._lock:
                if not self._queue:
                    return
                job_id = self._queue.pop(0)
                entry = self._pending.pop(job_id, None)
            if entry is None:
                continue
            try:
                self._run_job(job_id, entry["runner"])
            except Exception:
                # Never let one broken job kill the dispatcher.
                continue

    def _run_job(self, job_id: str, runner: Callable[[JobContext], int]) -> None:
        job_dir = self.job_dir(job_id)
        context = JobContext(self, job_id)
        with self._lock:
            self._contexts[job_id] = context
        self.update_status(
            job_dir,
            status=RUNNING,
            started=_now(),
            progress=max(2, int((self.read_status(job_dir) or {}).get("progress") or 2)),
            message="Running",
        )
        returncode: Optional[int] = None
        failure = ""
        try:
            returncode = int(runner(context) or 0)
        except Exception as exc:
            failure = str(exc)
            context.line("ERROR: %s" % failure)
            returncode = 1
        finally:
            with self._lock:
                self._contexts.pop(job_id, None)
        if context.cancelled:
            self.update_status(
                job_dir, status=CANCELLED, message="Cancelled",
                returncode=returncode, finished=_now())
            return
        if returncode == 0:
            self.update_status(
                job_dir, status=SUCCEEDED, progress=100,
                message="Complete", returncode=0, finished=_now())
            return
        self.update_status(
            job_dir,
            status=FAILED,
            message=failure or ("Failed with return code %s" % returncode),
            returncode=returncode,
            finished=_now(),
        )