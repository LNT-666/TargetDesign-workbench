#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Re-verify a hand-off bundle against the inventory recorded in its MANIFEST.md.

``build_release_bundle.py`` can only name a commit when it runs inside a git
working tree; outside one, ``git HEAD`` is ``unknown`` and the bundle carries no
commit anchor.  The inventory digest and the per-file rows written next to it are
computed from the delivered bytes alone, so this checker can still answer "is this
bundle exactly what was built?"

    python tools/check_bundle_inventory.py /path/to/TargetDesign-workbench_2026-11-13
    python tools/check_bundle_inventory.py TargetDesign-workbench_2026-11-13.zip

Accepts the bundle folder, its ``MANIFEST.md`` or the ``.zip`` (extracted to a
temporary directory; a ``<zip>.sha256`` sidecar next to it is verified first).
Exit code 0 only when the recorded digest is self-consistent and every listed
file is present on disk with the recorded size and SHA256.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

DIGEST_RE = re.compile(r"^- inventory digest: `([0-9a-f]{64})`", re.M)
HEAD_RE = re.compile(r"^- git HEAD: `([^`]*)`", re.M)
SECTION_RE = re.compile(r"^## (Code|Submission) inventory$", re.M)
ROW_RE = re.compile(r"^\| `(?P<path>[^`]+)` \| (?P<size>\d+) \| "
                    r"`(?P<sha>[0-9a-f]{64})` \|$")


def _read_rows(text):
    """Return ``[(section, path, size, sha256), ...]`` in manifest order."""
    rows = []
    section = None
    for line in text.splitlines():
        header = SECTION_RE.match(line)
        if header:
            section = header.group(1).lower()
            continue
        if line.startswith("## "):
            section = None
            continue
        if section is None:
            continue
        row = ROW_RE.match(line)
        if row:
            rows.append((section, row.group("path"), int(row.group("size")),
                         row.group("sha")))
    return rows


def _digest_of(rows) -> str:
    """Rebuild the packer's digest: sorted ``section/path/size/sha256`` lines."""
    lines = ["%s\t%s\t%d\t%s\n" % row for row in rows]
    return hashlib.sha256("".join(sorted(lines)).encode("utf-8")).hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _bundle_root(target: Path):
    """Resolve the input to ``(bundle folder, cleanup callables)``."""
    if target.is_dir():
        if (target / "MANIFEST.md").is_file():
            return target, []
        nested = sorted(target.glob("*/MANIFEST.md"))
        if not nested:
            raise SystemExit("no MANIFEST.md in %s or its immediate subfolders"
                             % target)
        return nested[0].parent, []
    if target.suffix.lower() == ".zip":
        sidecar = Path(str(target) + ".sha256")
        if sidecar.is_file():
            expected, _, name = sidecar.read_text(encoding="utf-8").partition("  ")
            if expected and expected.strip() != _sha256(target):
                raise SystemExit("zip digest does not match %s" % sidecar.name)
            print("sidecar: OK (%s)" % sidecar.name)
        tmp = Path(tempfile.mkdtemp(prefix="tdw-bundle-check-"))
        with zipfile.ZipFile(target) as zf:
            zf.extractall(tmp)
        found = sorted(tmp.glob("*/MANIFEST.md"))
        if not found:
            shutil.rmtree(tmp, ignore_errors=True)
            raise SystemExit("no MANIFEST.md at the top level of %s" % target)
        return found[0].parent, [lambda: shutil.rmtree(tmp, ignore_errors=True)]
    if target.suffix.lower() == ".md":
        return target.parent, []
    raise SystemExit("not a bundle folder, .zip or MANIFEST.md: %s" % target)


def check(target: Path) -> int:
    root, cleanups = _bundle_root(Path(target).expanduser().resolve())
    # The zip branch extracts into a fresh temp directory that is not resolved
    # yet; on macOS /var/folders and on Windows short 8.3 temp names are links,
    # so every entry would look like it escaped once _within() resolves it.
    root = root.resolve()
    try:
        manifest_path = root / "MANIFEST.md"
        if not manifest_path.is_file():
            raise SystemExit("missing MANIFEST.md in %s" % root)
        text = manifest_path.read_text(encoding="utf-8")
        rows = _read_rows(text)
        recorded = DIGEST_RE.search(text)
        head = HEAD_RE.search(text)
        if not rows or not recorded:
            raise SystemExit("MANIFEST.md has no inventory table or digest: %s"
                             % manifest_path)

        recomputed = _digest_of(rows)
        if recomputed != recorded.group(1):
            print("digest  : MISMATCH (recorded %s, recomputed from the table %s)"
                  % (recorded.group(1), recomputed))
            return 1
        print("bundle  : %s" % root)
        print("git HEAD: %s" % (head.group(1) if head else "not recorded"))
        print("digest  : OK (%s)" % recorded.group(1))

        missing, bad = [], []
        for section, rel, size, sha in rows:
            path = root / section / rel
            label = "%s/%s" % (section, rel)
            if not _within(path, root):
                bad.append((label, "path escapes the bundle"))
                continue
            if not path.is_file():
                missing.append(label)
                continue
            actual = path.stat().st_size
            if actual != size:
                bad.append((label, "size %d != %d" % (actual, size)))
                continue
            if _sha256(path) != sha:
                bad.append((label, "sha256 mismatch"))
        print("rows    : %d checked, %d missing, %d mismatched"
              % (len(rows), len(missing), len(bad)))
        for rel in missing:
            print("  missing   : %s" % rel)
        for item in bad:
            print("  mismatched: %s (%s)" % (item[0], item[1]))
        ok = not missing and not bad
        print("result  : %s" % ("OK" if ok else "FAILED"))
        return 0 if ok else 1
    finally:
        for cleanup in cleanups:
            cleanup()


def _within(path: Path, root: Path) -> bool:
    try:
        resolved = path.resolve()
    except OSError:
        return False
    return resolved == root or root in resolved.parents


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify a release bundle against the inventory in its MANIFEST.md.")
    parser.add_argument("bundle", help="bundle folder, MANIFEST.md, or bundle .zip")
    args = parser.parse_args(argv)
    if not os.path.exists(args.bundle):
        parser.error("no such path: %s" % args.bundle)
    return check(Path(args.bundle))


if __name__ == "__main__":
    sys.exit(main())
