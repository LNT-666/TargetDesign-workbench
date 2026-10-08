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

#: Bundled sample data, repo-relative (NAR :138). ``GET /api/sample`` reports
#: these paths plus the Designer overlay of ``sample_data/demo_batch.json`` so
#: the front end can load a runnable example without typing paths by hand.
SAMPLE_GENOME = "sample_data/demo_genome.fa"
SAMPLE_TARGET = "sample_data/demo_target.fa"
SAMPLE_BATCH = "sample_data/demo_batch.json"
SAMPLE_FILES = (SAMPLE_GENOME, SAMPLE_TARGET, SAMPLE_BATCH)

#: Help pages rendered by ``/help`` and ``/help/tutorial`` (NAR :139).
HELP_DIR = os.path.join(ROOT, "docs", "help_en")
HELP_SAMPLE_DIR = os.path.join(HELP_DIR, "sample_output")
HELP_PAGES = {
    "/help": "index.md",
    "/help/": "index.md",
    "/help/tutorial": "tutorial.md",
    "/help/tutorial/": "tutorial.md",
}

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


def batch_run_route(path: str):
    """Split ``/api/batch/runs/<ref>[/<action>]`` into (ref, action)."""

    prefix = "/api/batch/runs/"
    if not path.startswith(prefix):
        return (None, None)
    parts = [part for part in path[len(prefix):].split("/") if part]
    if not parts or len(parts) > 2:
        return (None, None)
    return (parts[0], parts[1] if len(parts) > 1 else None)


# ------------------------------------------------------------------- help

_HTML_ESCAPES = (("&", "&amp;"), ("<", "&lt;"), (">", "&gt;"),
                 ('"', "&quot;"))

_INLINE_RE = re.compile(
    r"`(?P<code>[^`]+)`"
    r"|\[(?P<label>[^\]]+)\]\((?P<href>[^)\s]+)\)"
    r"|\*\*(?P<bold>[^*]+)\*\*"
)

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_ORDERED_RE = re.compile(r"^\s*\d+\.\s+(.*)$")
_UNORDERED_RE = re.compile(r"^\s*[-*]\s+(.*)$")
_CONTINUATION_RE = re.compile(r"^[ \t]+\S")
_TABLE_SEP_RE = re.compile(r"^\|?\s*:?-{2,}:?\s*(?:\|\s*:?-{2,}:?\s*)*\|?$")


def html_escape(text: str) -> str:
    """Escape the characters that matter for the help pages' HTML."""
    for needle, replacement in _HTML_ESCAPES:
        text = text.replace(needle, replacement)
    return text


def inline_markdown(text: str) -> str:
    """Expand the inline Markdown the help pages use (code, links, bold)."""

    def replace(match):
        if match.group("code") is not None:
            return "<code>%s</code>" % match.group("code")
        if match.group("label") is not None:
            label = _INLINE_RE.sub(replace, match.group("label"))
            return '<a href="%s">%s</a>' % (match.group("href"), label)
        return "<strong>%s</strong>" % match.group("bold")

    return _INLINE_RE.sub(replace, text)


def _table_cells(line: str):
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def render_markdown(source: str) -> str:
    """Minimal Markdown -> HTML for the bundled help pages.

    Handles exactly the constructs ``docs/help_en/*.md`` use -- ATX headings,
    fenced code, pipe tables, blockquotes, ordered/unordered lists, horizontal
    rules and paragraphs -- with inline code, links and bold. No external
    dependency, so the container keeps running on the standard library alone.
    """
    lines = source.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    html = []
    paragraph = []
    code = []
    in_code = False

    def flush_paragraph():
        if paragraph:
            text = html_escape(" ".join(paragraph).strip())
            html.append("<p>%s</p>" % inline_markdown(text))
            paragraph[:] = []

    index = 0
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if in_code:
            if stripped.startswith("```"):
                html.append("<pre><code>%s</code></pre>"
                            % html_escape("\n".join(code)))
                code[:] = []
                in_code = False
            else:
                code.append(line)
            index += 1
            continue
        if stripped.startswith("```"):
            flush_paragraph()
            in_code = True
            index += 1
            continue
        if not stripped or stripped.startswith("<!--"):
            flush_paragraph()
            index += 1
            continue
        heading = _HEADING_RE.match(stripped)
        if heading:
            flush_paragraph()
            level = len(heading.group(1))
            html.append("<h%d>%s</h%d>" % (
                level, inline_markdown(html_escape(heading.group(2))), level))
            index += 1
            continue
        if stripped in ("---", "***", "___"):
            flush_paragraph()
            html.append("<hr>")
            index += 1
            continue
        if (stripped.startswith("|") and index + 1 < len(lines)
                and _TABLE_SEP_RE.match(lines[index + 1].strip())):
            flush_paragraph()
            table = [stripped]
            index += 2
            while index < len(lines) and lines[index].strip().startswith("|"):
                table.append(lines[index].strip())
                index += 1
            body = ["<table>", "<thead><tr>"]
            body += ["<th>%s</th>" % inline_markdown(html_escape(cell))
                     for cell in _table_cells(table[0])]
            body.append("</tr></thead>")
            if len(table) > 1:
                body.append("<tbody>")
                for row in table[1:]:
                    body.append("<tr>")
                    body += ["<td>%s</td>" % inline_markdown(html_escape(cell))
                             for cell in _table_cells(row)]
                    body.append("</tr>")
                body.append("</tbody>")
            body.append("</table>")
            html.append("".join(body))
            continue
        if stripped.startswith(">"):
            flush_paragraph()
            quote = []
            while index < len(lines) and lines[index].strip().startswith(">"):
                quote.append(lines[index].strip().lstrip(">").strip())
                index += 1
            html.append("<blockquote><p>%s</p></blockquote>"
                        % inline_markdown(html_escape(" ".join(quote))))
            continue
        ordered = _ORDERED_RE.match(line)
        unordered = _UNORDERED_RE.match(line)
        if ordered or unordered:
            flush_paragraph()
            ordered_list = bool(ordered)
            entries = []
            matcher = _ORDERED_RE if ordered_list else _UNORDERED_RE
            while index < len(lines):
                item = matcher.match(lines[index])
                if item:
                    entries.append([html_escape(item.group(1))])
                    index += 1
                    continue
                # An indented, non-blank line continues the previous item
                # (the help pages wrap long list items this way).
                if entries and _CONTINUATION_RE.match(lines[index]):
                    entries[-1].append(html_escape(lines[index].strip()))
                    index += 1
                    continue
                break
            tag = "ol" if ordered_list else "ul"
            html.append("<%s>%s</%s>" % (
                tag, "".join(
                    "<li>%s</li>" % inline_markdown(" ".join(parts))
                    for parts in entries), tag))
            continue
        paragraph.append(stripped)
        index += 1

    flush_paragraph()
    if in_code and code:
        html.append("<pre><code>%s</code></pre>"
                    % html_escape("\n".join(code)))
    return "\n".join(html)


_HELP_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>%(title)s</title>
<style>
 body { font-family: system-ui, sans-serif; max-width: 52rem;
        margin: 2rem auto; padding: 0 1rem; line-height: 1.5; color: #1b1b1b; }
 nav { border-bottom: 1px solid #ddd; padding-bottom: .5rem;
       margin-bottom: 1.5rem; }
 nav a { margin-right: 1rem; }
 pre { background: #f5f5f5; padding: .75rem; overflow-x: auto; }
 code { background: #f5f5f5; padding: 0 .2rem; }
 pre code { background: none; padding: 0; }
 table { border-collapse: collapse; }
 th, td { border: 1px solid #ccc; padding: .25rem .5rem; text-align: left; }
 blockquote { border-left: 3px solid #ddd; margin-left: 0;
              padding-left: 1rem; color: #444; }
</style>
</head>
<body>
<nav>
  <a href="/help">Help index</a>
  <a href="/help/tutorial">Tutorial</a>
  <a href="/help/sample_output/README.md">Sample output</a>
  <a href="/">Workbench</a>
</nav>
%(body)s
</body>
</html>
"""


def render_help_document(title: str, source: str) -> str:
    """Render one help Markdown page as a standalone HTML document."""
    body = render_markdown(source)
    # The pages link to their neighbours with repo-relative paths; point those
    # at the routes this server actually serves.
    body = body.replace('href="tutorial.md"', 'href="/help/tutorial"')
    body = body.replace('href="sample_output/"',
                        'href="/help/sample_output/README.md"')
    return _HELP_TEMPLATE % {"title": title, "body": body}


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
            if path in HELP_PAGES:
                self._serve_help_page(HELP_PAGES[path])
                return
            if path.startswith("/help/sample_output/"):
                self._serve_help_sample(path[len("/help/sample_output/"):])
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
            if path == "/api/sample":
                self._api_sample()
                return
            if path == "/api/batch/runs":
                limit = (query.get("limit") or ["20"])[0]
                day = (query.get("day") or [""])[0] or None
                self._send_json(batch.list_runs(limit=limit, day=day))
                return
            run_ref, run_action = batch_run_route(path)
            if run_ref is not None and run_action == "download":
                self._api_batch_run_download(run_ref, query)
                return
            if run_ref is not None and run_action is None:
                self._send_json(batch.run_detail(run_ref))
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
                if action == "results":
                    self._api_job_results(job_id)
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

    def _api_job_results(self, job_id: str):
        """The run's deliverable table, used by the ``full`` results view."""
        manager = get_manager()
        if manager.get_job(job_id) is None:
            self._send_error_json("job not found", 404)
            return
        self._send_json(designer.results(job_id, manager))

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

    def _api_batch_run_download(self, ref: str, query):
        """Download one file from a batch run folder (path stays inside it)."""

        filename = (query.get("file") or [""])[0] or ""
        path = batch.run_file_path(ref, filename)
        with open(path, "rb") as handle:
            body = handle.read()
        self._send_bytes(
            body,
            "application/octet-stream",
            headers={
                "Content-Disposition":
                    'attachment; filename="%s"' % os.path.basename(path)
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

    def _serve_help_page(self, name):
        """Render one Markdown page of ``docs/help_en`` as HTML."""
        full = os.path.join(HELP_DIR, name)
        try:
            with open(full, "r", encoding="utf-8") as handle:
                source = handle.read()
        except OSError:
            self._send_error_json("help page not found: %s" % name, 404)
            return
        stem = os.path.splitext(name)[0]
        title = "TargetDesign-workbench help"
        if stem != "index":
            title = "TargetDesign-workbench - %s" % stem
        document = render_help_document(title, source)
        self._send_bytes(document.encode("utf-8"),
                         "text/html; charset=utf-8")

    def _serve_help_sample(self, relative):
        """Serve a file under ``docs/help_en/sample_output`` as plain text."""
        relative = relative.strip().strip("/")
        root = os.path.normpath(HELP_SAMPLE_DIR)
        target = os.path.normpath(os.path.join(root, relative))
        if (not relative or not target.startswith(root + os.sep)
                or not os.path.isfile(target)):
            self._send_error_json(
                "sample output not found: %s" % relative, 404)
            return
        with open(target, "rb") as handle:
            body = handle.read()
        self._send_bytes(body, "text/plain; charset=utf-8")

    def _api_sample(self):
        """Report the bundled sample data and its Designer form overlay.

        NAR :138 asks for a simple, visible way to try the authors' sample
        data, and for the data itself to be reachable so the formatting
        requirements can be checked. The paths are repo-relative on purpose:
        the bundled batch spec uses them the same way, so either entry point
        (web or CLI) reads the same files.
        """
        missing = [name for name in SAMPLE_FILES
                   if not os.path.isfile(os.path.join(ROOT, name))]
        if missing:
            self._send_error_json(
                "sample data is incomplete; missing: %s" % ", ".join(missing),
                404)
            return
        self._send_json({
            "genome_fasta": SAMPLE_GENOME,
            "target_fasta": SAMPLE_TARGET,
            "batch_spec": SAMPLE_BATCH,
            "mode": "single_motif_flank",
            "input_mode": "sequence",
            "nuclease": "cas9",
            "run": {
                "engine": "auto",
                "pam_mode": "custom",
                "max_mismatch": "3",
                "gc_min": "40",
                "gc_max": "70",
            },
            "fields": {
                "genome_fasta": SAMPLE_GENOME,
                "search_fasta": SAMPLE_TARGET,
                # The batch spec masks the scope with itself
                # (``mask_same_as_target: true``). The Designer has no such
                # switch, so it gets the same file as an explicit mask;
                # without it the web run counts the on-target loci as
                # off-targets and no longer matches the sample output.
                "mask_fasta": SAMPLE_TARGET,
                "motif": "NGG",
                "flank": "20",
                "side": "downstream",
            },
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
