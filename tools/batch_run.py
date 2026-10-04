#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Command-line batch entry point: many search scopes x many pattern configs."""

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "shared"))

from design.batch_runner import BatchRunner, batch_root  # noqa: E402
from design.batch_spec import (  # noqa: E402
    load_batch_json,
    load_units_tsv,
    normalize_units,
    validate_spec,
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

    if args.dry_run:
        _print_units(units)
        return 0

    try:
        root = batch_root(spec.batch_label)
    except ValueError as exc:
        print("ERROR: %s" % exc)
        return 2

    runner = BatchRunner(
        spec,
        units,
        root,
        on_line=lambda line: print(line, flush=True),
        resume=args.resume,
    )
    return runner.run()


if __name__ == "__main__":
    sys.exit(main())
