#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Check drafted release notes or tag messages for site-identity leaks.

The bundle leak scan only walks the staged tree, so text published through the
GitHub Release API has no gate of its own.  This check reuses the tracked
generic rules plus the untracked local denylist from ``build_release_stage.py``.

    python tools/check_release_notes.py release-notes.md
    python tools/check_release_notes.py v0.3.4-notes.md v0.3.4-tag-message.txt
    Get-Content notes.md -Raw | python tools/check_release_notes.py -

Exit code 1 when any rule matches.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import build_release_stage as stage  # noqa: E402


def read_text(name: str) -> str:
    if name == "-":
        return sys.stdin.read()
    return Path(name).read_text(encoding="utf-8")


def scan_text(text: str, local: tuple) -> list:
    hits = []
    for label, pattern in stage.LEAK_PATTERNS + local[0]:
        found = pattern.findall(text)
        if found:
            samples = sorted({item if isinstance(item, str) else item[0]
                              for item in found})[:3]
            hits.append((label, len(found), samples))
    return hits


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("files", nargs="+", metavar="FILE",
                        help='release notes or tag message file; "-" reads stdin')
    args = parser.parse_args(argv)

    local = stage.denylist()
    failed = False
    for name in args.files:
        hits = scan_text(read_text(name), local)
        if not hits:
            print("%s: clean" % name)
            continue
        failed = True
        for label, count, samples in hits:
            print("%s: %s x%d %s" % (name, label, count, samples))

    if failed:
        print("release notes refused: site-identity leak(s) found", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
