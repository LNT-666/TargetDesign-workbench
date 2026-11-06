#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Guard the packaging path: only the sealed, lineage-correct manuscript may ship.

The rule has two halves:

* a seal file, ``docs/submission/manuscript_lineage.json``, records the baseline
  (r9 rev22), the current head (``SUBMISSION_SHORT_v1``) and every byte hash;
* a check run by both packaging tools re-verifies the seal and the structural
  rules before anything is copied.

    python tools/manuscript_lineage.py status
    python tools/manuscript_lineage.py check
    python tools/manuscript_lineage.py seal --note "what changed"

``check`` fails when

1. the seal is missing or has an unknown schema;
2. the baseline, head ``.docx``, head ``.md`` or supplementary file no longer
   matches its recorded SHA256;
3. ``docs/submission/`` holds more than one manuscript stem, or any ``.docx``
   other than the head (old drafts must live under ``docs/archive/``);
4. the head ``.docx`` is older than the head ``.md`` (not rebuilt after an edit);
5. the ``.md`` -> ``.docx`` block coverage drops below the sealed threshold;
6. the head no longer retains enough of the baseline, or adds nothing new.

Every intentional manuscript update therefore requires ``seal``; the seal
appends a revision record instead of silently overwriting history.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SEAL = "docs/submission/manuscript_lineage.json"
BASELINE = "docs/submission/branch_base/SUBMISSION_SHORT_r9_markup_view.docx"
SCHEMA = "manuscript-lineage/1"

#: ``min_baseline_retention`` is a similarity floor, not an edit budget: the head
#: is a condensed short paper, so legitimate rewrites of individual paragraphs
#: (audit fixes, renumbered references) cost a point or two.  The gate is meant
#: to reject a *different manuscript*, which lands far below this floor.
DEFAULT_RULES = {
    "min_md_docx_coverage": 0.90,
    "min_baseline_retention": 0.88,
    "docx_mtime_tolerance_s": 2,
}

def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _norm(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[`*_#>\[\]()|]", " ", text)
    return re.sub(r"\s+", "", text)


def docx_text(path: Path) -> str:
    import docx

    document = docx.Document(str(path))
    parts = [paragraph.text for paragraph in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                parts.append(cell.text)
    return "\n".join(parts)


def md_blocks(path: Path) -> list:
    blocks = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if len(line) < 60 or line.startswith(("|", "```", "![")):
            continue
        blocks.append(line)
    return blocks


def docx_blocks(path: Path, drop_alt_text: bool = False) -> list:
    blocks = []
    for line in docx_text(path).splitlines():
        line = line.strip()
        if len(line) < 60:
            continue
        if drop_alt_text and line.lower().startswith("alt text"):
            continue
        blocks.append(line)
    return blocks


def coverage(blocks, haystack: str) -> float:
    if not blocks:
        return 0.0
    target = _norm(haystack)
    found = sum(1 for block in blocks if _norm(block)[:60] in target)
    return found / len(blocks)


def _rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def load_seal(root: Path) -> dict:
    path = root / SEAL
    if not path.is_file():
        raise ValueError("missing manuscript seal: %s (run seal first)" % SEAL)
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != SCHEMA:
        raise ValueError("unknown seal schema: %r" % data.get("schema"))
    return data


def _seal_files(data: dict) -> list:
    files = [data["baseline"]["path"], data["head"]["docx"]["path"],
             data["head"]["md"]["path"]]
    files.extend(item["path"] for item in data["head"].get("supplementary", []))
    return files


def _active_docx(root: Path) -> list:
    """Every .docx outside docs/archive/ and the baseline folder."""
    found = []
    docs = root / "docs"
    for path in docs.rglob("*.docx"):
        rel = _rel(root, path)
        if rel.startswith(("docs/archive/", "docs/submission/branch_base/")):
            continue
        found.append(rel)
    return sorted(found)


def check(root: Path = REPO) -> list:
    """Return a list of blocking errors; empty means the bundle may ship."""
    try:
        data = load_seal(root)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [str(exc)]

    errors = []
    rules = dict(DEFAULT_RULES)
    rules.update(data.get("rules", {}))

    for rel in _seal_files(data):
        path = root / rel
        if not path.is_file():
            errors.append("sealed file is missing: %s" % rel)
    if errors:
        return errors

    expected = {
        data["baseline"]["path"]: data["baseline"]["sha256"],
        data["head"]["docx"]["path"]: data["head"]["docx"]["sha256"],
        data["head"]["md"]["path"]: data["head"]["md"]["sha256"],
    }
    for item in data["head"].get("supplementary", []):
        expected[item["path"]] = item["sha256"]
    for rel, digest in expected.items():
        actual = sha256(root / rel)
        if actual != digest:
            errors.append("file changed after sealing: %s" % rel)

    head_docx = data["head"]["docx"]["path"]
    head_md = data["head"]["md"]["path"]
    errors.extend(_structure_errors(
        root, head_docx, head_md, data["baseline"]["path"], rules))
    return errors


def _structure_errors(root: Path, head_docx: str, head_md: str,
                      baseline: str, rules: dict) -> list:
    errors = []
    active = _active_docx(root)
    if active != [head_docx]:
        errors.append(
            "docs/submission must hold exactly one manuscript docx (%s); found: %s"
            % (head_docx, active or "none"))

    docx_mtime = (root / head_docx).stat().st_mtime
    md_mtime = (root / head_md).stat().st_mtime
    if docx_mtime + rules["docx_mtime_tolerance_s"] < md_mtime:
        errors.append("docx is older than md; rebuild it, then seal")

    md_cov = coverage(md_blocks(root / head_md), docx_text(root / head_docx))
    if md_cov < rules["min_md_docx_coverage"]:
        errors.append("md -> docx coverage %.1f%% is below %.0f%%"
                      % (md_cov * 100, rules["min_md_docx_coverage"] * 100))

    head_blocks = docx_blocks(root / head_docx, drop_alt_text=True)
    base_blocks = docx_blocks(root / baseline, drop_alt_text=True)
    head_text = "\n".join(head_blocks)
    retention = coverage(base_blocks, head_text)
    if retention < rules["min_baseline_retention"]:
        errors.append("baseline retention %.1f%% is below %.0f%% (wrong lineage?)"
                      % (retention * 100, rules["min_baseline_retention"] * 100))
    base_text = _norm("\n".join(base_blocks))
    if not any(_norm(block)[:60] not in base_text for block in head_blocks):
        errors.append("head adds nothing over the baseline; not a modification branch")

    return errors


def seal(root: Path = REPO, note: str = "") -> dict:
    """Record the current head/baseline hashes after the structural checks pass."""
    active = _active_docx(root)
    if len(active) != 1:
        raise SystemExit(
            "cannot seal: docs/submission needs exactly one manuscript docx; found: %s"
            % (active or "none"))
    head_docx = active[0]
    head_md = Path(head_docx).with_suffix(".md").as_posix()
    for rel in (BASELINE, head_docx, head_md,
                "docs/submission/SUPPLEMENTARY_v1.md",
                "docs/submission/SUPPLEMENTARY_v1.pdf"):
        if not (root / rel).is_file():
            raise SystemExit("cannot seal: missing %s" % rel)

    rules = DEFAULT_RULES
    errors = _structure_errors(root, head_docx, head_md, BASELINE, rules)
    if errors:
        raise SystemExit("cannot seal:\n  " + "\n  ".join(errors))

    previous = {}
    try:
        previous = load_seal(root)
    except (OSError, ValueError, json.JSONDecodeError):
        previous = {}

    def record(rel):
        path = root / rel
        return {"path": rel, "bytes": path.stat().st_size, "sha256": sha256(path)}

    data = {
        "schema": SCHEMA,
        "sealed_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "baseline": {**record(BASELINE),
                     "note": "r9 rev22, 2026-10-12 22:40, the only accepted base"},
        "head": {
            "stem": Path(head_docx).stem,
            "docx": record(head_docx),
            "md": record(head_md),
            "supplementary": [
                record("docs/submission/SUPPLEMENTARY_v1.md"),
                record("docs/submission/SUPPLEMENTARY_v1.pdf"),
            ],
        },
        "rules": dict(DEFAULT_RULES),
        "revisions": previous.get("revisions", []),
    }
    entry = {
        "sealed_at": data["sealed_at"],
        "head_sha256": data["head"]["docx"]["sha256"],
        "note": note,
    }
    if not data["revisions"] or data["revisions"][-1]["head_sha256"] != entry["head_sha256"]:
        data["revisions"].append(entry)

    path = root / SEAL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    return data


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("action", choices=("check", "status", "seal"),
                        nargs="?", default="check")
    parser.add_argument("--root", default=str(REPO), help=argparse.SUPPRESS)
    parser.add_argument("--note", default="", help="seal: what changed")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()

    if args.action == "seal":
        data = seal(root, args.note)
        print("sealed: %s" % (root / SEAL))
        print("head  : %s %s" % (data["head"]["stem"],
                                 data["head"]["docx"]["sha256"][:16]))
        return 0

    errors = check(root)
    if args.action == "status":
        try:
            data = load_seal(root)
            print("baseline: %s" % data["baseline"]["path"])
            print("head    : %s" % data["head"]["docx"]["path"])
            print("sealed  : %s" % data["sealed_at"])
            print("revisions: %d" % len(data.get("revisions", [])))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print("seal    : %s" % exc)

    if errors:
        for error in errors:
            print("FAIL: %s" % error, file=sys.stderr)
        return 1
    print("lineage OK: only the sealed head is active")
    return 0


if __name__ == "__main__":
    sys.exit(main())
