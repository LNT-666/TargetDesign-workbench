#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Assemble the upload staging tree: journal submission bundle + supplementary data + release set.

The staging tree lives OUTSIDE the working repository, so the development tree is
never modified: the script only reads from the repository and writes copies to
``--out`` (default ``<repo parent>/upload``).

    python tools/build_release_stage.py                 # rebuild the stage (manuscript short)
    python tools/build_release_stage.py --version v4    # stage the long archival manuscript
    python tools/build_release_stage.py --version v1    # stage the previous manuscript
    python tools/build_release_stage.py --check-only    # leak-scan an existing stage
    python tools/build_release_stage.py --no-clean      # keep existing subdirs

Layout produced::

    <out>/MANIFEST.md              inventory + pre-upload leak scan
    <out>/submission/              files for the journal submission system
    <out>/supplementary-data/      executable + docs, plus the assembled zip
    <out>/repo/                    evidence set for the public release (plus file list)

Exit code 1 if the leak scan finds a blocking match.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_OUT = REPO.parent / "upload"
ZIP_NAME = "TargetDesign-workbench_supplementary.zip"
ZIP_STAMP = (2026, 9, 23, 0, 0, 0)

VERSIONS = ("v1", "v2", "v4", "short")
#: "short" (SUBMISSION_SHORT_v1) is the Web Server Issue submission; v4 is the long
#: archival version, so the default stage follows the submission.
DEFAULT_VERSION = "short"
#: Manuscript stem per version, mirroring docs/submission/build_submission_docx.py.
STEM = {
    "v1": "SUBMISSION_MAIN_v1",
    "v2": "SUBMISSION_MAIN_v2",
    "v4": "SUBMISSION_MAIN_v4",
    "short": "SUBMISSION_SHORT_v1",
}


def submission_files(version: str) -> list:
    """Journal-submission files for one manuscript version."""
    stem = STEM[version]
    return [
        f"docs/submission/{stem}.docx",
        f"docs/submission/{stem}.md",
        "docs/submission/SUPPLEMENTARY_v1.md",
        "docs/submission/SUPPLEMENTARY_v1.pdf",
    ]
SUBMISSION_FIGURES = [
    *(f"docs/figures/fig{i}_{slug}_v1.{ext}"
      for i, slug in ((1, "architecture"), (2, "layouts"), (3, "capability_matrix"),
                      (4, "index_layout"), (5, "seed_plan"), (6, "thread_scaling"),
                      (7, "interface"), (8, "output_table"))
      for ext in ("pdf", "png")),
    "docs/figures/graphical_abstract.pdf",
    "docs/figures/graphical_abstract.png",
]
#: The short paper drops the two engine-internals figures and numbers the art that
#: remains in the order the text cites it, mirroring SHORT_FIGURES in
#: docs/submission/build_submission_docx.py.
SUBMISSION_FIGURES_SHORT = [
    *(f"docs/figures/{name}.{ext}"
      for name in ("fig1_architecture_v1", "fig2_layouts_v1", "fig3_interface_v1",
                   "fig4_output_table_v1", "fig5_capability_matrix_v1",
                   "fig6_thread_scaling_v1")
      for ext in ("pdf", "png")),
    "docs/figures/graphical_abstract.pdf",
    "docs/figures/graphical_abstract.png",
]
SUBMISSION_FIGURES_BY_VERSION = {"short": SUBMISSION_FIGURES_SHORT}
SUPPLEMENTARY_DATA = [
    ("native/bin/offtarget-engine.exe", "bin/offtarget-engine.exe"),
    ("native/bin/offtarget-engine", "bin/offtarget-engine"),
    ("native/offtarget_engine/README.md", "docs/README.md"),
    ("docs/NATIVE_INDEXED_ENGINE_DESIGN.md", "docs/NATIVE_INDEXED_ENGINE_DESIGN.md"),
    ("docs/OUTPUTS.md", "docs/OUTPUTS.md"),
    ("docs/MODELS.md", "docs/MODELS.md"),
]
# Mirrors docs/RELEASE_CONTENTS.md section 3.1 (12 items as of 2026-09-23).
RELEASE_SET = [
    "docs/expressiveness_matrix.tsv",
    "docs/seed_plan_sweep.json",
    "docs/bulge_fixture_sweep.json",
    "docs/NATIVE_INDEXED_ENGINE_DESIGN.md",
    "tools/expressiveness_probe.py",
    "tools/bulge_fixture_sweep.py",
    "example/engine_benchmark_small/REPORT.md",
    "example/engine_benchmark_small/fixture.json",
    "example/engine_benchmark_small/guides.tsv",
    "example/engine_benchmark_small/results_mm0.json",
    "example/engine_benchmark_small/results_bulge0.json",
    "example/engine_benchmark_small/results_bulge1.json",
    ".gitignore",
]
LEAK_PATTERNS = [
    ("drive letter", re.compile(r"\b[A-Za-z]:\\")),
    ("UNC path", re.compile(r"\\\\[A-Za-z0-9._-]+\\")),
    ("windows user dir", re.compile(r"(?i)C:\\Users")),
    ("linux home", re.compile(r"/home/[a-z]")),
    ("env var path", re.compile(r"%(TEMP|USERPROFILE)%")),
]
BINARY_NEEDLES = [
    ("windows user dir", b"C:\\Users"),
    ("linux home", b"/home/"),
]
# The site-specific half of the gate (host names, account names, workflow-role
# wording) lives in an untracked local file, so this script and every staged
# copy stay free of it.  See tools/release_scan_denylist.local.txt.
DENYLIST = REPO / "tools" / "release_scan_denylist.local.txt"
BINARY_EXT = {".exe", ".dll", ".so", ".bin", ""}
TEXT_EXT = {".md", ".txt", ".json", ".tsv", ".py", ".cff", ".yml", ".yaml", ".cfg", ".toml", ""}
TEXT_NAMES = {".gitignore"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def copy_file(src: Path, dest: Path, rows: list, edit=None) -> None:
    if not src.is_file():
        raise SystemExit(f"missing source file: {src}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    if edit is None:
        shutil.copyfile(src, dest)
    else:
        dest.write_text(edit(src.read_text(encoding="utf-8")), encoding="utf-8", newline="")
    rows.append((src.relative_to(REPO).as_posix(), dest, dest.stat().st_size, sha256(dest)))


def git_tracked() -> list[str]:
    try:
        out = subprocess.run(["git", "-C", str(REPO), "ls-files"],
                             capture_output=True, text=True, check=True).stdout
    except Exception as exc:  # git missing or repo unreadable
        return [f"<git ls-files failed: {exc}>"]
    return [line.strip() for line in out.splitlines() if line.strip()]


def build_zip(stage_data: Path, dest: Path) -> int:
    members = sorted(p for p in stage_data.rglob("*") if p.is_file() and p.name != ZIP_NAME)
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in members:
            info = zipfile.ZipInfo(path.relative_to(stage_data).as_posix(), date_time=ZIP_STAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, path.read_bytes())
    return dest.stat().st_size


def docx_text(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as zf:
            xml = zf.read("word/document.xml").decode("utf-8", "replace")
    except Exception:
        return ""
    return re.sub(r"<[^>]+>", " ", xml)


def json_strings(path: Path) -> str:
    """String values of a JSON document, so escaped backslashes cannot be read as UNC."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return f"<unparsable json: {exc}>"
    out: list = []

    def walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                out.append(str(key))
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)
        elif isinstance(node, str):
            out.append(node)

    walk(data)
    return "\n".join(out)


def denylist() -> tuple:
    """Untracked local half of the gate: (text patterns, binary needles)."""
    if not DENYLIST.is_file():
        raise SystemExit(f"missing local denylist: {DENYLIST} (untracked; one label<TAB>pattern per line)")
    text_patterns: list = []
    binary_needles: list = []
    for lineno, raw in enumerate(DENYLIST.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        fields = [field.strip() for field in raw.split("\t") if field.strip()]
        if fields[0] == "binary":
            if len(fields) != 3:
                raise SystemExit(f"{DENYLIST}:{lineno}: expected binary<TAB>label<TAB>literal")
            binary_needles.append((fields[1], fields[2].encode("utf-8")))
        else:
            if len(fields) != 2:
                raise SystemExit(f"{DENYLIST}:{lineno}: expected label<TAB>pattern")
            text_patterns.append((fields[0], re.compile(fields[1])))
    if not text_patterns and not binary_needles:
        raise SystemExit(f"local denylist holds no entry: {DENYLIST}")
    return text_patterns, binary_needles


def staged_gitignore(text: str, text_patterns: list) -> str:
    """Drop the .gitignore lines naming local-only tooling before it is published."""
    return "".join(line for line in text.splitlines(True)
                   if not any(pattern.search(line) for _label, pattern in text_patterns))


def scan(root: Path, local: tuple) -> list:
    hits = []
    local_text, local_binary = local
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(root).as_posix()
        suffix = path.suffix.lower()
        text = None
        if suffix == ".docx":
            text = docx_text(path)
        elif suffix == ".json":
            text = json_strings(path)
        elif suffix in TEXT_EXT and (suffix or path.name in TEXT_NAMES):
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                text = None
        if text is not None:
            for label, pattern in LEAK_PATTERNS + local_text:
                found = pattern.findall(text)
                if found:
                    sample = sorted({f if isinstance(f, str) else f[0] for f in found})[:3]
                    hits.append((rel, label, len(found), sample))
        if suffix in BINARY_EXT:
            data = path.read_bytes()
            for label, needle in BINARY_NEEDLES + local_binary:
                count = data.count(needle)
                if count:
                    hits.append((rel, f"binary {label}", count, [needle.decode("latin-1")]))
    return hits


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--version", choices=VERSIONS, default=DEFAULT_VERSION,
                    help="manuscript version to stage (default: %(default)s; short = Web Server Issue submission)")
    ap.add_argument("--check-only", action="store_true")
    ap.add_argument("--no-clean", action="store_true")
    args = ap.parse_args()
    local = denylist()
    stage = Path(args.out).expanduser().resolve()
    if stage == REPO or REPO in stage.parents:
        raise SystemExit(f"refusing a stage inside the repository (keeps the working tree untouched): {stage}")

    if args.check_only:
        hits = scan(stage, local)
        print(f"scanned: {stage}")
        for path, label, count, sample in hits:
            print(f"  ! {path}: {label} x{count} {sample}")
        print("leak hits:", len(hits))
        return 1 if hits else 0

    rows: list = []
    if not args.no_clean:
        for name in ("submission", "supplementary-data", "repo", "MANIFEST.md"):
            target = (stage / name).resolve()
            if target.exists() and stage in target.parents:
                print(f"clean: {target}")
                shutil.rmtree(target) if target.is_dir() else target.unlink()
    (stage / "submission" / "figures").mkdir(parents=True, exist_ok=True)
    (stage / "supplementary-data" / "bin").mkdir(parents=True, exist_ok=True)
    (stage / "supplementary-data" / "docs").mkdir(parents=True, exist_ok=True)
    (stage / "repo").mkdir(parents=True, exist_ok=True)

    for rel in submission_files(args.version):
        copy_file(REPO / rel, stage / "submission" / Path(rel).name, rows)
    for rel in SUBMISSION_FIGURES_BY_VERSION.get(args.version, SUBMISSION_FIGURES):
        copy_file(REPO / rel, stage / "submission" / "figures" / Path(rel).name, rows)
    for rel, dest in SUPPLEMENTARY_DATA:
        copy_file(REPO / rel, stage / "supplementary-data" / dest, rows)
    zip_path = stage / "supplementary-data" / ZIP_NAME
    zip_bytes = build_zip(stage / "supplementary-data", zip_path)
    for rel in RELEASE_SET:
        edit = (lambda text: staged_gitignore(text, local[0])) if rel == ".gitignore" else None
        copy_file(REPO / rel, stage / "repo" / rel, rows, edit)

    tracked = git_tracked()
    list_lines = ["# Files that the public repository would contain", "",
                  f"# git ls-files: {len(tracked)} entries", *tracked, "",
                  "# Added by the release decision (docs/RELEASE_CONTENTS.md section 3.1):",
                  *(f"{rel}  (untracked before the release)" for rel in RELEASE_SET if rel != ".gitignore")]
    (stage / "repo" / "RELEASE_FILE_LIST.txt").write_text("\n".join(list_lines) + "\n", encoding="utf-8", newline="")

    stem = STEM[args.version]
    main_md = (REPO / f"docs/submission/{stem}.md").read_text(encoding="utf-8")
    placeholders = len(re.findall(r"\[TO FILL", main_md))
    placeholder_lines = sum(1 for line in main_md.splitlines() if "[TO FILL" in line)
    hits = scan(stage, local)

    manifest = [
        "# Upload staging tree", "",
        f"- built from the working repository (read-only source), paths below are repository-relative",
        f"- journal submission bundle: `submission/` (manuscript `{stem}`)",
        f"- supplementary data bundle: `supplementary-data/` (zip: `{ZIP_NAME}`, {zip_bytes:,} B)",
        f"- public release set: `repo/` (12 evidence items + `.gitignore` + `RELEASE_FILE_LIST.txt`)",
        f"- files staged: {len(rows)}", "",
        "## Pending before upload", "",
        "- `SUPPLEMENTARY_v1.pdf` is the supplementary file to upload (NAR: supplementary"
        " data preferably PDF); `SUPPLEMENTARY_v1.md` is its source.",
        f"- `[TO FILL]` placeholders still present in the manuscript: {placeholders} occurrence(s) on {placeholder_lines} line(s).",
        "- `submission/figures/` carries PDF (print) and PNG (preview), numbered in the"
        " order the text cites them; the artwork-format check is recorded in"
        " `docs/NAR_FORMAT_CHECKLIST.md` section 6.",
        "- `repo/.gitignore` is the working copy with the lines naming local-only tooling removed;"
        " the development copy is unchanged.",
        "", "## Leak scan (pre-upload gate)", "",
        "- generic text patterns: drive letter, UNC path, Windows user directory, POSIX home,"
        " environment-variable path",
        "- generic binary needles: Windows user directory, POSIX home",
        "- site-specific entries come from the untracked local denylist, matched in text and in binaries",
        f"- result: **{len(hits)} hit(s)**", "",
    ]
    for path, label, count, sample in hits:
        manifest.append(f"  - `{path}`: {label} x{count} {sample}")
    manifest += ["", "## Inventory", "", "| destination | size (B) | sha256 | source (repo-relative) |", "| --- | ---: | --- | --- |"]
    for rel, dest, size, digest in rows:
        manifest.append(f"| `{dest.relative_to(stage).as_posix()}` | {size:,} | `{digest[:16]}` | `{rel}` |")
    manifest += ["", f"| `supplementary-data/{ZIP_NAME}` | {zip_bytes:,} | `{sha256(zip_path)[:16]}` | (assembled from `supplementary-data/`) |"]
    (stage / "MANIFEST.md").write_text("\n".join(manifest) + "\n", encoding="utf-8", newline="")

    print(f"stage: {stage}")
    print(f"manuscript: {stem}.md")
    print(f"files staged: {len(rows)}  zip: {zip_bytes:,} B")
    print(f"leak hits: {len(hits)}")
    for path, label, count, sample in hits:
        print(f"  ! {path}: {label} x{count} {sample}")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
