#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Assemble a hand-off bundle: current working tree plus journal submission files.

Unlike :mod:`build_release_stage`, which stages only the evidence files named by
the manuscript, this tool copies the *whole working tree* of the code so the
bundle matches the state that is about to be released, including uncommitted
edits and new untracked modules.  Large or generated material (models, example
genomes, logs, job state, the virtualenv, Git metadata) stays out.

    python tools/build_release_bundle.py
    python tools/build_release_bundle.py --out D:\\handoff
    python tools/build_release_bundle.py --no-zip
    python tools/build_release_bundle.py --skip-submission

Layout produced under ``<out>/TargetDesign-workbench_<YYYY-MM-DD>/``::

    MANIFEST.md              git state, inventory, exclusions, size/sha256
    PACKAGE_CONTENTS.md      what is inside and how to start it
    code/                    the working tree subset plus native binaries
    submission/              manuscript, supplementary file and figures
                             (omitted with --skip-submission)

The folder is also written as ``<out>/TargetDesign-workbench_<YYYY-MM-DD>.zip``
unless ``--no-zip`` is given.  Exit code 1 when a required path is missing.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_OUT = REPO.parent / "release"
PREFIX = "TargetDesign-workbench"
MAX_FILE_BYTES = 25 * 1024 * 1024

#: Already-compressed payloads: storing them beats re-deflating over SMB.
STORED_SUFFIXES = {
    ".docx", ".xlsx", ".pptx", ".pdf", ".png", ".jpg", ".jpeg",
    ".gz", ".tgz", ".zip", ".whl",
}

#: Files kept at the bundle root of ``code/``.
ROOT_FILES = (
    "README.md",
    "README.zh-CN.md",
    "LICENSE",
    "CITATION.cff",
    "GLOSSARY.md",
    "pyproject.toml",
    "requirements.txt",
    "requirements-linux.txt",
    "requirements-windows.txt",
    "requirements-models-linux.txt",
    "requirements-crispai.txt",
    "run_tests.py",
    "main.py",
    "designer_workbench.py",
    "unified_gui.py",
    "Dockerfile",
    "docker-compose.yml",
    ".dockerignore",
    ".gitignore",
    ".gitattributes",
    ".zenodo.json",
    ".github/workflows/container.yml",
    ".github/workflows/portability.yml",
    "TargetDesign-workbench.exe",
)

#: Directories copied wholesale into ``code/``.
CODE_DIRS = (
    "basic",
    "shared",
    "webapp",
    "tools",
    "tests",
    "native",
    "requirements",
    "sample_data",
    "external_tools",
    "Target_xbp_Target",
    "Target_xbp_Y_zbp_Target",
    "docs",
)

#: Only these example trees travel with the bundle; the rest is multi-GB data.
EXAMPLE_DIRS = (
    "example/engine_benchmark_small",
    "example/batch",
)

EXCLUDE_DIR_NAMES = {
    "__pycache__",
    ".git",
    ".venv",
    ".venv310",
    ".codex",
    ".codex_tmp",
    "models",
    "build",
    ".mypy_cache",
    ".pytest_cache",
}

#: Repository-relative prefixes that never enter the hand-off bundle.
EXCLUDE_PREFIXES = (
    "backup/",
    "build/",
    "jobs/",
    "logs/",
    "out/",
    "output/",
    "native/build/",
    "docs/submission/",
    "docs/figures/",
    "docs/qa/",
    "docs/handoff/",
    "docs/archive/",
    "docs/PAPER_",
    "external_tools/DeepCas12a",
    "example/engine_benchmark/",
    "example/engine_benchmark_bulge/",
    "example/engine_benchmark_small/genome_index/",
    "example/engine_benchmark_small/run_blast/",
    "example/engine_benchmark_small/run_bowtie2/",
    "example/engine_benchmark_small/run_indexed/",
    "example/engine_benchmark_small/run_native-indexed/",
    "example/grch38",
    "example/GRCh38",
    "example/GCF_",
    "example/chr21",
    "basic/out/",
    "shared/logs/",
    "webapp/jobs/",
)

EXCLUDE_NAMES = {
    "docs/SSH_ACCESS.md",
    "docs/FIGURE_TABLE_PLAN.md",
    "docs/GRAPHICAL_ABSTRACT_SPEC.md",
    "docs/NAR_FORMAT_CHECKLIST.md",
    "docs/RELEASE_CONTENTS.md",
    "docs/SKILLS_APPLICABILITY_AUDIT.md",
    "docs/SUBMISSION_SHORT_r9_markup_view.docx",
    "tools/release_scan_denylist.local.txt",
}

EXCLUDE_SUFFIXES = (
    ".pyc", ".pyo", ".part", ".lock", ".log",
    ".pth", ".pt", ".h5", ".npz", ".ckpt", ".tar.gz", ".tgz",
)

REQUIRED_CODE = (
    "shared/output/__init__.py",
    "shared/output/candidate_export.py",
    "shared/output/output_columns.py",
    "shared/output/xlsx_utils.py",
    ".gitignore",
    ".github/workflows/container.yml",
    ".github/workflows/portability.yml",
    "shared/scoring/deepcrispr_convert.py",
    "webapp/services/models.py",
)

#: The native engine is built in place; Windows runners use the .exe suffix.
REQUIRED_ENGINE_BINS = (
    "native/bin/offtarget-engine",
    "native/bin/offtarget-engine.exe",
)

#: Local-only launcher (`*.exe` is ignored), required only when it exists.
CONDITIONAL_REQUIRED_CODE = ("TargetDesign-workbench.exe",)

#: Files that stay executable in the zip even when the build machine cannot
#: represent POSIX permission bits (Windows).
EXECUTABLE_PATHS = {
    "native/bin/offtarget-engine",
    "tools/serve_webapp.sh",
    "tools/server_build_index.sh",
    "tools/build_crispai_env.sh",
}

#: Site-identity leak classes that must stop a release.  The remaining local
#: rules (agent branding, skill names, sample Windows paths) stay report-only.
BLOCKING_LEAK_LABELS = {
    "internal host",
    "internal path",
    "linux home",
    "windows user dir",
    "UNC path",
    "env var path",
}

REQUIRED_SUBMISSION = (
    "SUBMISSION_SHORT_v1.docx",
    "SUBMISSION_SHORT_v1.md",
    "SUPPLEMENTARY_v1.md",
    "SUPPLEMENTARY_v1.pdf",
    "figures/fig1_architecture_v1.pdf",
)

PACKAGE_CONTENTS = """# TargetDesign-workbench 交付包

生成日期：{day}

## 目录

- `code/`：当前工作区的完整代码（含尚未提交的改动），可直接运行。
- `submission/`：{submission}
- `MANIFEST.md`：构建时的 Git 状态、文件清单与 SHA256。

## Windows 快速启动

双击 `code/TargetDesign-workbench.exe`，程序会用本机 Python 3 启动 Web
工作台并打开浏览器，默认监听 `0.0.0.0:5000`。

首次运行前请确认已安装 Python 3，并可导入 `numpy`、`Biopython`、`pyfaidx`。
缺少依赖时启动器会询问是否自动安装（`--install` 可非交互执行）。

命令行方式：

```powershell
cd code
python -m pip install -r requirements-windows.txt
python main.py                      # 桌面工作台
python webapp/app.py                # Web 工作台，默认 http://0.0.0.0:5000/
```

Linux 服务器把依赖文件换成 `requirements-linux.txt`，其余命令相同。

## 不包含

- `models/`：深度学习权重，需在 Model setup 页按需下载。
- `example/` 中的大基因组与中间结果，仅保留 `engine_benchmark_small` 和 `batch`。
- 运行产物：`logs/`、`output/`、`out/`、`backup/`、`jobs/`、`webapp/jobs/`。
- 内部材料：`docs/submission/` 原始草稿、`docs/figures/` 源图、`docs/qa/`、
  `docs/handoff/`、`docs/PAPER_*`。
- `.git`、虚拟环境和缓存文件。
- 本机专用文件：`docs/SSH_ACCESS.md`、`tools/release_scan_denylist.local.txt`。
- `native/build*/`：CMake 配置树与编译中间产物（含 `build/`、`build-windows/`、`build-x86_64/` 等）。

## 说明

- `shared/output/` 是随包发布的 Python 源码包，不是运行产物；`webapp/schema.py`、
  `designer_workbench.py` 和 `webapp/app.py` 都依赖它。
- 包内保留 `.gitignore` 与 `.github/workflows/container.yml`、
  `.github/workflows/portability.yml`；`tests/test_constraints.py` 和
  `tests/test_container_workflow.py` 会读取这些文件。
- `native/bin/offtarget-engine` 与 `tools/*.sh` 的可执行位已保留。若用不保留权限的
  工具解包，请手工执行 `chmod 755 native/bin/offtarget-engine tools/*.sh`；
  否则 `index_backend=auto` 会静默退回纯 Python 实现。
- `run_tests.py` 的稿件密封检查（`tests/test_manuscript_lineage.py`）需要
  `python-docx`；未安装时该测试模块会明确 skip，不是收集期报错。

模型状态与获取方式见 `code/docs/MODELS.md`；服务器部署见
`code/docs/SERVER_DEPLOY.md`。
"""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _redact_site_path(value) -> str:
    """Replace absolute build-machine paths; keep relative paths as written."""
    text = str(value)
    if re.match(r"^(?:[A-Za-z]:[\\/]|\\\\|/)", text):
        return "<redacted build-machine path>"
    return text


_GIT_EXEC_CACHE = None


def _git_executable_paths() -> set:
    """Repository paths whose tracked mode is 100755 (works on Windows too)."""
    global _GIT_EXEC_CACHE
    if _GIT_EXEC_CACHE is not None:
        return _GIT_EXEC_CACHE
    try:
        result = subprocess.run(
            ["git", "ls-files", "-s"], cwd=str(REPO), capture_output=True,
            text=True, timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        _GIT_EXEC_CACHE = set()
        return _GIT_EXEC_CACHE
    paths = set()
    for line in result.stdout.splitlines():
        if line.startswith("100755 "):
            _meta, _sep, rel = line.partition("\t")
            if rel.strip():
                paths.add(rel.strip())
    _GIT_EXEC_CACHE = paths
    return paths


def _source_is_executable(rel: str, source: Path, git_exec: set) -> bool:
    try:
        mode = source.stat().st_mode
    except OSError:
        mode = 0
    return bool(mode & 0o111) or rel in EXECUTABLE_PATHS or rel in git_exec


def _excluded(rel: str) -> bool:
    rel = rel.strip("/")
    if rel in EXCLUDE_NAMES:
        return True
    if rel.endswith(EXCLUDE_SUFFIXES):
        return True
    # Every CMake tree under native/ is a build artifact, whatever suffix the
    # target gave it (native/build, native/build-windows, native/build-x86_64).
    if rel == "native/build" or rel.startswith("native/build-"):
        return True
    for prefix in EXCLUDE_PREFIXES:
        if rel == prefix.rstrip("/") or rel.startswith(prefix):
            return True
    return False


def _walk(top: str):
    base = REPO / top
    if not base.exists():
        return
    stack = [str(base)]
    while stack:
        current = stack.pop()
        try:
            entries = list(os.scandir(current))
        except OSError:
            continue
        for entry in entries:
            rel = Path(entry.path).relative_to(REPO).as_posix()
            try:
                if entry.is_dir(follow_symlinks=False):
                    if entry.name in EXCLUDE_DIR_NAMES or _excluded(rel):
                        continue
                    stack.append(entry.path)
                    continue
            except OSError:
                continue
            if _excluded(rel):
                continue
            try:
                stat = entry.stat(follow_symlinks=False)
            except OSError:
                continue
            if stat.st_size > MAX_FILE_BYTES:
                print("skip (too large): %s (%d B)" % (rel, stat.st_size))
                continue
            yield rel, Path(entry.path), stat.st_size, stat.st_mtime


def _code_files():
    for name in ROOT_FILES:
        path = REPO / name
        try:
            stat = path.stat()
        except OSError:
            print("missing root file: %s" % name)
            continue
        yield name, path, stat.st_size, stat.st_mtime
    for top in CODE_DIRS:
        yield from _walk(top)
    for top in EXAMPLE_DIRS:
        yield from _walk(top)


def _submission_files():
    sys.path.insert(0, str(REPO / "tools"))
    import build_release_stage as stage  # noqa: WPS433 (deliberate sibling import)

    submission = list(stage.submission_files(stage.DEFAULT_VERSION))
    figures = list(stage.SUBMISSION_FIGURES_SHORT)
    missing = [rel for rel in submission + figures if not (REPO / rel).is_file()]
    if missing:
        raise SystemExit(
            "submission material is local-only; add --skip-submission for a "
            "code-only bundle (missing: %s)" % ", ".join(missing[:5]))

    for rel in submission:
        path = REPO / rel
        stat = path.stat()
        yield rel.replace("docs/submission/", "", 1), path, stat.st_size, stat.st_mtime
    for rel in figures:
        path = REPO / rel
        stat = path.stat()
        yield rel.replace("docs/figures/", "figures/", 1), path, stat.st_size, stat.st_mtime


def _git_state():
    def run(*args):
        try:
            return subprocess.run(
                ["git", *args], cwd=str(REPO), capture_output=True,
                text=True, timeout=60,
            ).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return ""

    head = run("rev-parse", "--short", "HEAD") or "unknown"
    branch = run("rev-parse", "--abbrev-ref", "HEAD") or "unknown"
    status = run("status", "--porcelain")
    changes = [line for line in status.splitlines() if line.strip()]
    return head, branch, changes


def _copy_items(items, target: Path, jobs: int, materialize: bool = True):
    """Copy items with one read per file and hash the bytes while in memory."""
    if materialize:
        target.mkdir(parents=True, exist_ok=True)
    dir_lock = threading.Lock()
    git_exec = _git_executable_paths()

    staged = {}

    def work(item):
        rel, source, _size, mtime = item
        data = source.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        executable = _source_is_executable(rel, source, git_exec)
        if materialize:
            destination = target / rel
            with dir_lock:
                destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
            if executable:
                try:
                    os.chmod(destination, 0o755)
                except OSError:
                    pass
            try:
                os.utime(destination, (mtime, mtime))
            except OSError:
                pass
        with dir_lock:
            staged[rel] = (data, mtime, executable)
        return rel, len(data), digest

    with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        rows = list(pool.map(work, items))
    rows.sort()
    return rows, staged


def _manifest_text(day: str, head: str, branch: str, changes,
                   code_rows, submission_rows, out_dir: Path,
                   submission_skipped: bool = False):
    total = sum(row[1] for row in code_rows + submission_rows)
    lines = [
        "# Release bundle manifest",
        "",
        "- built: %s" % day,
        "- repository: `%s`" % _redact_site_path(REPO),
        "- git HEAD: `%s` (branch `%s`)" % (head, branch),
        "- pending changes included: %d" % len(changes),
        "- files: %d code + %d submission%s"
        % (len(code_rows), len(submission_rows),
           " (skipped)" if submission_skipped else ""),
        "- size before zip: %d B" % total,
        "- output: `%s`" % _redact_site_path(out_dir),
        "",
        "## Pending working-tree changes",
        "",
    ]
    if changes:
        lines.append("```diff")
        lines.extend(changes)
        lines.append("```")
    else:
        lines.append("Working tree clean at build time.")
    sections = [("code", code_rows)]
    if not submission_skipped:
        sections.append(("submission", submission_rows))
    for title, rows in sections:
        lines.extend([
            "",
            "## %s inventory" % title.capitalize(),
            "",
            "| path | size (B) | sha256 |",
            "| --- | ---: | --- |",
        ])
        for rel, size, digest in rows:
            lines.append("| `%s` | %d | `%s` |" % (rel, size, digest))
    return "\n".join(lines) + "\n"


def _zip_entries(folder_name: str, staged, archive: Path):
    """Zip the bytes already read for the folder copy (no second disk pass)."""
    with zipfile.ZipFile(archive, "w") as zf:
        for rel in sorted(staged):
            value = staged[rel]
            if len(value) == 3:
                data, mtime, executable = value
            else:
                data, mtime = value
                executable = rel in EXECUTABLE_PATHS
            info = zipfile.ZipInfo(
                filename=(Path(folder_name) / rel).as_posix(),
                date_time=time.localtime(mtime)[:6] if mtime else (2026, 1, 1, 0, 0, 0),
            )
            info.create_system = 3
            info.external_attr = (0o755 if executable else 0o644) << 16
            if Path(rel).suffix.lower() in STORED_SUFFIXES:
                info.compress_type = zipfile.ZIP_STORED
                zf.writestr(info, data)
            else:
                info.compress_type = zipfile.ZIP_DEFLATED
                zf.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED,
                            compresslevel=6)


def _import_smoke(code_dir: Path) -> None:
    """Import the three entry surfaces from the copied tree, not the source tree."""
    script = (
        "import sys\n"
        "sys.path[:0] = ['.', 'shared', 'webapp']\n"
        "import schema\n"
        "import designer_workbench\n"
        "import webapp.app\n"
        "print('ok')\n"
    )
    try:
        result = subprocess.run(
            [sys.executable, "-c", script], cwd=str(code_dir),
            capture_output=True, text=True, timeout=180,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise SystemExit("import smoke could not run: %s" % exc)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise SystemExit("import smoke failed:\n%s" % detail)
    print("import smoke: ok")


def _leak_scan(root: Path) -> list:
    """Scan the assembled bundle with the project's own site-identity rules."""
    sys.path.insert(0, str(REPO / "tools"))
    import build_release_stage as stage

    local = stage.denylist()
    hits = stage.scan(root, local)
    blocking = []
    for rel, label, count, sample in hits:
        print("leak   : %s: %s x%d %s" % (rel, label, count, sample))
        base = label[7:] if label.startswith("binary ") else label
        if base in BLOCKING_LEAK_LABELS:
            blocking.append((rel, label, count, sample))
    print("leak scan: %d blocking / %d report-only hit(s)"
          % (len(blocking), len(hits) - len(blocking)))
    return blocking


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default=str(DEFAULT_OUT),
                        help="output directory (default: %(default)s)")
    parser.add_argument("--date", default=date.today().isoformat(),
                        help="bundle date stamp (default: today)")
    parser.add_argument("--no-zip", action="store_true",
                        help="keep the folder only, do not write the zip")
    parser.add_argument("--zip-only", action="store_true",
                        help="write only the zip; skip materialising the folder")
    parser.add_argument("--keep", action="store_true",
                        help="reuse an existing bundle folder instead of rebuilding")
    parser.add_argument("--jobs", type=int, default=8,
                        help="parallel copy workers (default: %(default)s)")
    parser.add_argument("--skip-submission", action="store_true",
                        help="omit submission/ when the local manuscript material is absent")
    parser.add_argument("--skip-lineage", action="store_true",
                        help="do not require the sealed manuscript head")
    parser.add_argument("--skip-import-smoke", action="store_true",
                        help="do not import the copied entry modules before packaging")
    parser.add_argument("--skip-leak-scan", action="store_true",
                        help="do not run the site-identity leak gate")
    args = parser.parse_args(argv)
    if args.no_zip and args.zip_only:
        parser.error("--no-zip and --zip-only are mutually exclusive")

    sys.path.insert(0, str(REPO / "tools"))
    import manuscript_lineage

    if args.skip_lineage:
        print("lineage: skipped")
    else:
        errors = manuscript_lineage.check()
        if errors:
            for error in errors:
                print("FAIL: %s" % error, file=sys.stderr)
            print("refusing to package; run tools/manuscript_lineage.py seal after "
                  "fixing the manuscript", file=sys.stderr)
            return 1

    day = args.date
    name = "%s_%s" % (PREFIX, day)
    out_dir = Path(args.out).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    folder = out_dir / name
    materialize = not args.zip_only
    if materialize and folder.exists() and not args.keep:
        shutil.rmtree(folder)
    if materialize:
        folder.mkdir(parents=True, exist_ok=True)

    started = time.perf_counter()
    code_rows, code_staged = _copy_items(
        list(_code_files()), folder / "code", args.jobs, materialize)
    code_done = time.perf_counter()
    if args.skip_submission:
        submission_rows, submission_staged = [], {}
        print("submission: skipped")
    else:
        submission_rows, submission_staged = _copy_items(
            list(_submission_files()), folder / "submission", args.jobs, materialize)
    submission_done = time.perf_counter()

    for rel in REQUIRED_CODE:
        if (materialize and not (folder / "code" / rel).is_file()) \
                or rel not in code_staged:
            raise SystemExit("bundle is missing code/%s" % rel)
    if not any(rel in code_staged for rel in REQUIRED_ENGINE_BINS):
        raise SystemExit("bundle is missing a native engine binary (%s)"
                         % " or ".join(REQUIRED_ENGINE_BINS))
    for rel in CONDITIONAL_REQUIRED_CODE:
        if (REPO / rel).is_file() and rel not in code_staged:
            raise SystemExit("bundle is missing code/%s" % rel)
    if not args.skip_submission:
        for rel in REQUIRED_SUBMISSION:
            if (materialize and not (folder / "submission" / rel).is_file()) \
                    or rel not in submission_staged:
                raise SystemExit("bundle is missing submission/%s" % rel)

    contents = PACKAGE_CONTENTS.format(
        day=day,
        submission=("未包含（使用 --skip-submission 构建的纯代码包）。"
                    if args.skip_submission else
                    "投稿用稿件、补充材料和图件。"))
    if materialize:
        (folder / "PACKAGE_CONTENTS.md").write_text(contents, encoding="utf-8")

    head, branch, changes = _git_state()
    manifest = _manifest_text(day, head, branch, changes,
                              code_rows, submission_rows, out_dir,
                              submission_skipped=args.skip_submission)
    if materialize:
        (folder / "MANIFEST.md").write_text(manifest, encoding="utf-8")

    def run_gates(root: Path) -> None:
        if not args.skip_import_smoke:
            _import_smoke(root / "code")
        if not args.skip_leak_scan:
            blocking = _leak_scan(root)
            if blocking:
                raise SystemExit(
                    "leak scan refused the bundle: %d blocking hit(s)" % len(blocking))

    if materialize:
        run_gates(folder)

    staged = {"code/" + rel: value for rel, value in code_staged.items()}
    staged.update({"submission/" + rel: value
                   for rel, value in submission_staged.items()})
    stamped = time.time()
    staged["PACKAGE_CONTENTS.md"] = (contents.encode("utf-8"), stamped)
    staged["MANIFEST.md"] = (manifest.encode("utf-8"), stamped)

    archive = out_dir / (name + ".zip")
    if not args.no_zip:
        if archive.exists():
            archive.unlink()
        _zip_entries(folder.name, staged, archive)
        if archive.stat().st_size == 0:
            raise SystemExit("zip is empty: %s" % archive)
        if not materialize and not (args.skip_import_smoke and args.skip_leak_scan):
            with tempfile.TemporaryDirectory() as tmp:
                with zipfile.ZipFile(archive) as zf:
                    zf.extractall(tmp)
                try:
                    run_gates(Path(tmp) / folder.name)
                except SystemExit:
                    archive.unlink()
                    raise

    total = sum(row[1] for row in code_rows + submission_rows)
    print("bundle : %s" % (folder if materialize else "(zip only)"))
    print("files  : %d code + %d submission" % (len(code_rows), len(submission_rows)))
    print("size   : %.2f MB (folder), %.2f MB (zip)"
          % (total / 1e6, archive.stat().st_size / 1e6 if archive.exists() else 0))
    print("git    : %s (%s), %d pending change(s)" % (head, branch, len(changes)))
    print("zip    : %s" % (archive if archive.exists() else "(skipped)"))
    print("timing : code %.1fs, submission %.1fs, gates/zip %.1fs, total %.1fs"
          % (code_done - started, submission_done - code_done,
             time.perf_counter() - submission_done,
             time.perf_counter() - started))
    return 0


if __name__ == "__main__":
    sys.exit(main())
