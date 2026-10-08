#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Command-line batch entry point: many search scopes x many pattern configs."""

import argparse
import datetime
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "shared"))

from design.batch_runner import (  # noqa: E402
    BatchRunner,
    validate_batch_label,
)
from design.batch_spec import (  # noqa: E402
    load_batch_json,
    load_units_tsv,
    normalize_units,
    validate_spec,
)
from utils.paths import default_output_dir  # noqa: E402
from utils.run_index import (  # noqa: E402
    RUN_LOG_NAME,
    allocate_run,
    find_run,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="batch_run.py",
        description=(
            "Run every unit of a batch (search scope x pattern configuration) "
            "through the PatternRunner pipeline, serially."
        ),
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--spec", help="batch.json describing shared values, scopes, patterns, groups"
    )
    source.add_argument(
        "--units-tsv", help="advanced TSV with one unit per row (scope_id, pattern_id, ...)"
    )
    parser.add_argument("--label", help="override batch_label from the spec")
    parser.add_argument(
        "--resume",
        dest="resume",
        action="store_true",
        default=True,
        help="skip units already finished ok (default)",
    )
    parser.add_argument(
        "--no-resume",
        dest="resume",
        action="store_false",
        help="re-run every unit (backs up the old manifest)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print validation and the units table, then exit without running",
    )
    parser.add_argument(
        "--run-id",
        dest="run_id",
        metavar="ID",
        help=(
            "reuse an existing run folder instead of allocating a new one; "
            "accepts 0114, 20261006-0114 or 20261006/0114"
        ),
    )
    parser.add_argument(
        "--only",
        action="append",
        default=[],
        metavar="SCOPE,PATTERN",
        help="keep only units matching this pair (repeatable)",
    )
    return parser


def _parse_only(values) -> set:
    pairs = set()
    for raw in values:
        text = (raw or "").strip()
        if not text:
            continue
        scope_id, separator, pattern_id = text.partition(",")
        if not separator or not scope_id.strip() or not pattern_id.strip():
            raise ValueError(
                "--only expects scope_id,pattern_id, got: %r" % raw
            )
        pairs.add((scope_id.strip(), pattern_id.strip()))
    return pairs


def _print_units(units) -> None:
    print("unit_id\tscope_id\tpattern_id")
    for unit in units:
        print("%s\t%s\t%s" % (unit.unit_id, unit.scope_id, unit.pattern_id))


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    args = build_parser().parse_args(argv)
    try:
        if args.spec:
            spec = load_batch_json(args.spec)
        else:
            spec = load_units_tsv(args.units_tsv)
    except (OSError, ValueError) as exc:
        print("ERROR: %s" % exc)
        return 2

    if args.label:
        spec.batch_label = args.label

    errors, warnings = validate_spec(spec, dry_run=args.dry_run)
    for message in warnings:
        print("WARN: %s" % message)
    for message in errors:
        print("ERROR: %s" % message)
    if errors:
        return 2

    units = normalize_units(spec)
    try:
        pairs = _parse_only(args.only)
    except ValueError as exc:
        print("ERROR: %s" % exc)
        return 2
    if pairs:
        units = [
            unit
            for unit in units
            if (unit.scope_id, unit.pattern_id) in pairs
        ]
        if not units:
            print("ERROR: --only filter selected no units")
            return 2
    if not units:
        print("ERROR: batch expands to zero units")
        return 2

    try:
        label = validate_batch_label(spec.batch_label)
    except ValueError as exc:
        print("ERROR: %s" % exc)
        return 2

    output_root = default_output_dir()
    if args.dry_run:
        print(
            "RUN_DIR: %s%s<YYYYMMDD>-<ID> (id assigned when the run starts)"
            % (output_root, os.sep)
        )
        _print_units(units)
        return 0

    if args.run_id:
        index = find_run(output_root, args.run_id)
        if index is None:
            print(
                "ERROR: no run %r under %s" % (args.run_id, output_root)
            )
            return 2
    else:
        index = allocate_run(output_root)

    spec.batch_label = label
    run_meta = {
        "run_id": index.run_id,
        "day": index.day,
        "label": index.label,
        "batch_label": label,
        "created": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "unit_count": len(units),
        "resume": bool(args.resume),
        "source": args.spec or args.units_tsv,
    }
    print("RUN_ID: %s" % index.label, flush=True)
    print("RUN_DIR: %s" % index.path, flush=True)

    runner = BatchRunner(
        spec,
        units,
        index.path,
        on_line=lambda line: print(line, flush=True),
        resume=args.resume,
        run_meta=run_meta,
    )
    returncode = runner.run()
    print("RUN_LOG: %s" % os.path.join(index.path, RUN_LOG_NAME), flush=True)
    return returncode


if __name__ == "__main__":
    sys.exit(main())
