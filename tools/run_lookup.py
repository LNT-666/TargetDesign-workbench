#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Look up a batch run by its four digit index.

    python tools/run_lookup.py               # list the latest runs
    python tools/run_lookup.py 0114          # newest run 0114
    python tools/run_lookup.py 20261006-0114 # one specific day
    python tools/run_lookup.py --day 20261006

Every run lives in ``output/<YYYYMMDD>/<ID>/`` and owns ``run.json``,
``run.log``, ``batch.json``, ``manifest.tsv``, ``summary/batch_scores.tsv``
and one folder per unit.
"""

import argparse
import csv
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "shared"))

from utils.paths import default_output_dir  # noqa: E402
from utils.run_index import (  # noqa: E402
    RunIndex,
    list_runs,
    read_meta,
    parse_run_ref,
    find_run,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run_lookup.py",
        description="Show batch runs by their per-day four digit index.",
    )
    parser.add_argument(
        "run", nargs="?", help="run id (0114) or day-id (20261006-0114)"
    )
    parser.add_argument("--root", help="output root (default: the program output dir)")
    parser.add_argument("--day", help="restrict a listing to one YYYYMMDD day")
    parser.add_argument(
        "--limit", type=int, default=20, help="max runs in a listing (default 20)"
    )
    parser.add_argument("--json", action="store_true", help="emit JSON")
    return parser


def manifest_counts(path: str) -> dict:
    counts = {"ok": 0, "failed": 0, "skipped": 0, "stopped": 0}
    if not os.path.isfile(path):
        return counts
    try:
        with open(path, "r", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                status = (row.get("status") or "").strip()
                if status in counts:
                    counts[status] += 1
    except OSError:
        pass
    return counts


def describe(index: RunIndex) -> dict:
    meta = read_meta(index.path)
    counts = manifest_counts(os.path.join(index.path, "manifest.tsv"))
    unit_count = counts["ok"] + counts["failed"] + counts["stopped"] + counts["skipped"]
    return {
        "run_id": index.run_id,
        "day": index.day,
        "label": index.label,
        "path": index.path.replace("\\", "/"),
        "batch_label": meta.get("batch_label", ""),
        "unit_count": meta.get("unit_count", unit_count),
        "created": meta.get("created", ""),
        "units": counts,
    }


def _print_run(info: dict) -> None:
    units = info["units"]
    print("%s  %s" % (info["label"], info["path"]))
    print(
        "  batch: %s | units: %s | created: %s"
        % (info["batch_label"] or "-", info["unit_count"], info["created"] or "-")
    )
    print(
        "  manifest: ok=%d failed=%d skipped=%d stopped=%d"
        % (units["ok"], units["failed"], units["skipped"], units["stopped"])
    )
    for name in (
        "run.json",
        "run.log",
        "batch.json",
        "manifest.tsv",
        "summary/batch_scores.tsv",
    ):
        path = os.path.join(info["path"], name.replace("/", os.sep))
        print("  %-24s %s" % (name, "present" if os.path.isfile(path) else "missing"))


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    args = build_parser().parse_args(argv)
    output_root = args.root or default_output_dir()

    if args.run:
        try:
            parse_run_ref(args.run)
        except ValueError as exc:
            print("ERROR: %s" % exc)
            return 2
        index = find_run(output_root, args.run)
        if index is None:
            print("ERROR: no run %r under %s" % (args.run, output_root))
            return 1
        infos = [describe(index)]
        if args.json:
            print(json.dumps(infos[0], ensure_ascii=False, indent=2))
        else:
            _print_run(infos[0])
        return 0

    runs = list_runs(output_root, day=args.day, limit=args.limit)
    infos = [describe(index) for index in runs]
    if args.json:
        print(json.dumps(infos, ensure_ascii=False, indent=2))
        return 0
    if not infos:
        print("No runs under %s" % output_root)
        return 0
    for info in infos:
        _print_run(info)
    return 0


if __name__ == "__main__":
    sys.exit(main())
