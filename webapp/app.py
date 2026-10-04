#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Web workbench: Data prep / Models / Designer / Results.

Run from the repository root:

    python webapp/app.py [--port 5000]

The server listens on all interfaces (0.0.0.0:5000) by default, so it is
reachable from other machines on the network; pass ``--host 127.0.0.1`` to
restrict it to the local machine. Nothing is re-implemented here: the Designer
form, specs, runner configs, candidate reading and exports all come from
``shared/`` (through ``webapp/services/*``), so web results match the desktop
and CLI results.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEBAPP = os.path.dirname(os.path.abspath(__file__))
SHARED = os.path.join(ROOT, "shared")
for _path in (SHARED, WEBAPP):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import jobs as job_module  # noqa: E402
import schema  # noqa: E402
import services.batch as batch  # noqa: E402
import services.dataprep as dataprep  # noqa: E402
import services.designer as designer  # noqa: E402
import services.models as models  # noqa: E402


HOST = "0.0.0.0"
DEFAULT_PORT = 5000
INDEX_FILE = os.path.join(WEBAPP, "index.html")
STATIC_DIR = os.path.join(WEBAPP, "static")

#: Static files the server will hand out; anything else is refused.
STATIC_WHITELIST = {
    "app.js": "application/javascript; charset=utf-8",
    "styles.css": "text/css; charset=utf-8",
}

#: Downloadable job files: only the job's own export/ and out/ directories.
DOWNLOAD_WHITELIST_RE = re.compile(r"^(?:export|out)/[A-Za-z0-9._-]+$")

#: Extensions ``GET /api/outputs`` is willing to list.
OUTPUT_EXTENSIONS = (
    ".tsv", ".csv", ".bed", ".fa", ".fasta", ".fna", ".fai", ".xlsx",
    ".json", ".txt", ".log", ".ggi", ".idx", ".meta",
)

#: Most entries ``GET /api/fs/list`` returns for one directory. Directories are
#: kept first, so truncation only ever drops files off the end.
FS_ENTRY_LIMIT = 2000

_MANAGER: job_module.JobManager | None = None


def get_manager() -> job_module.JobManager:
    """Return the process-wide job manager, creating it on first use."""
    global _MANAGER
    if _MANAGER is None:
        _MANAGER = job_module.JobManager()
    return _MANAGER


def set_manager(manager) -> None:
    """Install a job manager (used by the tests)."""
    global _MANAGER
    _MANAGER = manager


def render_index() -> str:
    """Return the single-page shell."""
    with open(INDEX_FILE, "r", encoding="utf-8") as handle:
        return handle.read()


def filesystem_roots():
    """Roots the path picker may jump to (drive letters on Windows, ``/``)."""
    if os.name == "nt":
        return ["%s:\\" % letter for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                if os.path.exists("%s:\\" % letter)]
    return ["/"]


def hidden_entry(path: str, name: str) -> bool:
    """True when the path picker should treat one directory entry as hidden.

    The only rule, used by ``_api_fs_list``: a dot-prefixed name is hidden
    everywhere, and on Windows the ``FILE_ATTRIBUTE_HIDDEN`` bit counts too
    (``$Recycle.Bin``, ``pagefile.sys``, ...). A failed ``stat`` is not
    hidden, so such an entry is only dropped by the regular listing rules.
    """
    if name.startswith("."):
        return True
    if os.name != "nt":
        return False
    try:
        attributes = os.stat(path).st_file_attributes
    except OSError:
        return False
    return bool(attributes & stat.FILE_ATTRIBUTE_HIDDEN)


def job_route(path: str):
    """Split ``/api/jobs/<id>[/<action>]`` into (job_id, action)."""
    if not path.startswith("/api/jobs/"):
        return (None, None)
    parts = [part for part in path[len("/api/jobs/"):].split("/") if part]
    if not parts:
        return (None, None)
    job_id = parts[0]
    action = parts[1] if len(parts) > 1 else None
    if len(parts) > 2:
        return (None, None)
    return (job_id, action)


def model_action_route(path: str):
    """Split ``/api/models/<key>/<action>`` into (key, action)."""
    if not path.startswith("/api/models/"):
        return (None, None)
    parts = [part for part in path[len("/api/models/"):].split("/") if part]
    if len(parts) != 2:
        return (None, None)
    return (parts[0], parts[1])


class Handler(BaseHTTPRequestHandler):
    server_version = "CrisprWorkbenchLocal/2.0"

    # ------------------------------------------------------------- plumbing

    def _send_bytes(self, body: bytes, content_type: str, status: int = 200,
                    headers=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, payload, status: int = 200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send_bytes(body, "application/json; charset=utf-8", status)

    def _send_error_json(self, message: str, status: int = 400):
        self._send_json({"error": message}, status)

    def _read_json(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except (TypeError, ValueError):
            length = 0
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def log_message(self, fmt, *args):  # keep the console quiet
        pass

    # ---------------------------------------------------------------- routes

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)
        try:
            if path in ("/", "/index.html"):
                self._send_bytes(
                    render_index().encode("utf-8"),
                    "text/html; charset=utf-8")
                return
            if path.startswith("/static/"):
                self._serve_static(path[len("/static/"):])
                return
            if path == "/api/schema":
                self._send_json(schema.build_schema())
                return
            if path == "/api/jobs":
                self._send_json({"jobs": get_manager().list_jobs()})
                return
            if path == "/api/models":
                self._send_json(models.list_models())
                return
            if path == "/api/outputs":
                self._api_outputs(query)
                return
            if path == "/api/fs/list":
                self._api_fs_list(query)
                return
            job_id, action = job_route(path)
            if job_id is not None:
                if action is None:
                    self._api_job(job_id)
                    return
                if action == "log":
                    self._api_job_log(job_id, query)
                    return
                if action == "candidates":
                    self._api_job_candidates(job_id)
                    return
                if action == "download":
                    self._api_job_download(job_id, query)
                    return
            self._send_error_json("not found", 404)
        except ValueError as exc:
            self._send_error_json(str(exc), 400)
        except FileNotFoundError as exc:
            self._send_error_json(str(exc), 404)
        except Exception as exc:  # pragma: no cover - defensive
            self._send_error_json("internal error: %s" % exc, 500)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        payload = self._read_json()
        manager = get_manager()
        try:
            if path == "/api/designer/preview":
                self._send_json(designer.preview(payload))
                return
            if path == "/api/designer/preset":
                self._send_json(designer.preset_update(payload))
                return
            if path == "/api/designer/active-side":
                self._send_json(designer.active_side_update(payload))
                return
            if path == "/api/designer/jobs":
                self._send_json(designer.submit(payload, manager))
                return
            if path == "/api/batch/preview":
                self._send_json(batch.preview(payload))
                return
            if path == "/api/batch/jobs":
                self._send_json(batch.submit(payload, manager))
                return
            if path == "/api/dataprep/download":
                self._send_json(dataprep.submit_download(payload, manager))
                return
            if path == "/api/dataprep/prepare":
                self._send_json(dataprep.submit_prepare(payload, manager))
                return
            if path == "/api/dataprep/extract-target":
                self._send_json(
                    dataprep.submit_extract_target(payload, manager))
                return
            if path == "/api/dataprep/extract-mask":
                self._send_json(dataprep.submit_extract_mask(payload, manager))
                return
            if path == "/api/dataprep/build-blastdb":
                self._send_json(dataprep.submit_build_blastdb(payload, manager))
                return
            if path == "/api/dataprep/build-index":
                self._send_json(dataprep.submit_build_index(payload, manager))
                return
            key, action = model_action_route(path)
            if key is not None:
                if action == "download":
                    self._send_json(models.submit_download(key, manager))
                    return
                if action == "delete":
                    self._send_json(models.submit_delete(key, manager))
                    return
            job_id, job_action = job_route(path)
            if job_id is not None:
                if job_action == "cancel":
                    status = manager.cancel(job_id)
                    if status is None:
                        self._send_error_json("job not found", 404)
                    else:
                        self._send_json(status)
                    return
                if job_action == "export":
                    self._send_json(
                        designer.export_rows(job_id, payload, manager))
                    return
            self._send_error_json("not found", 404)
        except ValueError as exc:
            self._send_error_json(str(exc), 400)
        except FileNotFoundError as exc:
            self._send_error_json(str(exc), 404)
        except Exception as exc:  # pragma: no cover - defensive
            self._send_error_json("internal error: %s" % exc, 500)
    # ----------------------------------------------------------- API parts

    def _serve_static(self, name: str):
        content_type = STATIC_WHITELIST.get(name)
        if not content_type:
            self._send_error_json("not found", 404)
            return
        path = os.path.join(STATIC_DIR, name)
        if not os.path.isfile(path):
            self._send_error_json("not found", 404)
            return
        with open(path, "rb") as handle:
            self._send_bytes(handle.read(), content_type)

    def _api_job(self, job_id: str):
        status = get_manager().get_job(job_id)
        if status is None:
            self._send_error_json("job not found", 404)
            return
        self._send_json(status)

    def _api_job_log(self, job_id: str, query):
        manager = get_manager()
        if manager.get_job(job_id) is None:
            self._send_error_json("job not found", 404)
            return
        try:
            offset = int((query.get("offset") or ["0"])[0])
        except (TypeError, ValueError):
            offset = 0
        self._send_json(manager.read_log(job_id, offset))

    def _api_job_candidates(self, job_id: str):
        manager = get_manager()
        if manager.get_job(job_id) is None:
            self._send_error_json("job not found", 404)
            return
        self._send_json(designer.candidates(job_id, manager))

    def _api_job_download(self, job_id: str, query):
        manager = get_manager()
        filename = (query.get("file") or [""])[0] or ""
        if not DOWNLOAD_WHITELIST_RE.match(filename):
            raise ValueError("file is not in the download whitelist")
        job_dir = manager.job_dir(job_id)
        path = os.path.abspath(os.path.join(job_dir, filename))
        base = os.path.abspath(job_dir)
        if os.path.commonpath([path, base]) != base:
            raise ValueError("invalid download path")
        if not os.path.isfile(path):
            raise FileNotFoundError("file not found: %s" % filename)
        with open(path, "rb") as handle:
            body = handle.read()
        self._send_bytes(
            body,
            "application/octet-stream",
            headers={
                "Content-Disposition":
                    'attachment; filename="%s"' % os.path.basename(filename)
            },
        )

    def _api_outputs(self, query):
        target = (query.get("dir") or [""])[0]
        if not target:
            raise ValueError("dir is required")
        if not os.path.isdir(target):
            raise ValueError("Directory not found: %s" % target)
        try:
            names = sorted(os.listdir(target))
        except OSError as exc:
            raise ValueError("Cannot read directory: %s" % exc)
        files = []
        for name in names:
            full = os.path.join(target, name)
            if not os.path.isfile(full):
                continue
            if not name.lower().endswith(OUTPUT_EXTENSIONS):
                continue
            try:
                files.append({
                    "name": name,
                    "path": full,
                    "size": os.path.getsize(full),
                    "modified": os.path.getmtime(full),
                })
            except OSError:
                continue
        self._send_json({"dir": target, "files": files})

    def _api_fs_list(self, query):
        """Read-only directory listing for the in-page path picker.

        No ``dir`` means "root mode": report the roots to start from instead of
        listing anything. A listed directory always reports its own ``parent``
        (``None`` at a drive root) so the picker can walk upwards. Hidden
        entries (dot-prefixed, or the Windows hidden attribute) are filtered
        out unless ``hidden=1`` asks for them.
        """
        target = (query.get("dir") or [""])[0].strip()
        kind = (query.get("kind") or [""])[0].strip()
        if kind not in schema.FS_KINDS:
            kind = "any"
        hidden = (query.get("hidden") or [""])[0].strip().lower()
        show_hidden = hidden in ("1", "true", "yes")
        strip = sorted(schema.FS_STRIP.get(kind, ()), key=len, reverse=True)
        home = os.path.expanduser("~")
        if not target:
            self._send_json({
                "dir": None,
                "parent": None,
                "roots": filesystem_roots(),
                "home": home,
                "kind": kind,
                "strip": strip,
                "entries": [],
                "truncated": False,
            })
            return
        if not os.path.isdir(target):
            raise ValueError("Directory not found: %s" % target)
        directory = os.path.abspath(target)
        try:
            names = os.listdir(directory)
        except OSError as exc:
            raise ValueError("Cannot read directory: %s" % exc)
        extensions = schema.FS_KINDS[kind]
        directories, files = [], []
        for name in names:
            full = os.path.join(directory, name)
            try:
                is_dir = os.path.isdir(full)
                if not is_dir and kind == "dir":
                    continue
                if (not is_dir and extensions
                        and not name.lower().endswith(extensions)):
                    continue
                if not show_hidden and hidden_entry(full, name):
                    continue
                entry = {
                    "name": name,
                    "path": full,
                    "type": "dir" if is_dir else "file",
                    "size": None if is_dir else os.path.getsize(full),
                    "modified": os.path.getmtime(full),
                }
            except OSError:
                continue
            (directories if is_dir else files).append(entry)
        directories.sort(key=lambda item: item["name"].lower())
        files.sort(key=lambda item: item["name"].lower())
        entries = directories + files
        truncated = len(entries) > FS_ENTRY_LIMIT
        if truncated:
            entries = entries[:FS_ENTRY_LIMIT]
        parent = os.path.dirname(directory)
        self._send_json({
            "dir": directory,
            "parent": None if parent == directory else parent,
            "roots": [],
            "home": home,
            "kind": kind,
            "strip": strip,
            "entries": entries,
            "truncated": truncated,
        })


def main():
    parser = argparse.ArgumentParser(
        description="TargetDesign-workbench web UI")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--host", default=HOST,
                        help="Bind address; 0.0.0.0 exposes all interfaces")
    args = parser.parse_args()
    set_manager(job_module.JobManager())
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print("Serving on: http://%s:%d" % (args.host, args.port),
          flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
