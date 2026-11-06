#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run the external crispAI aggregate scorer and backfill a candidate TSV.

Example:

    python tools\\score_crispai.py outdir\\library_scores.tsv --samples 200

The command preflights the crispAI environment (R + NuPoP, Cas-OFFinder,
UCSC chroms, pybdm/genomepy), invokes the vendored upstream aggregate mode,
and adds ``crispai_aggregate_score`` + ``crispai_off_target`` columns to the
candidate TSV.
"""

import argparse
import json
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "shared"))

from scoring.crispai_runtime import (  # noqa: E402
    backfill_candidates,
    collect_sgrnas,
    model_status_details,
    run_crispai_aggregate,
    specificity_from_aggregate,
)


def _default_output(path: str, suffix: str) -> str:
    directory = os.path.dirname(os.path.abspath(path))
    name = os.path.splitext(os.path.basename(path))[0]
    return os.path.join(directory, "%s.%s.tsv" % (name, suffix))


def _write_metadata(path: str, metadata: dict) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(metadata, handle, indent=2, ensure_ascii=False)


def _publish(source: str, target: str) -> str:
    parent = os.path.dirname(os.path.abspath(target))
    if not os.path.isdir(parent):
        raise ValueError("output directory does not exist: %s" % parent)
    shutil.copy2(source, target)
    return target


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Score guides with the external crispAI aggregate model")
    parser.add_argument("candidates_tsv",
                        help="Scored TSV with guide_seq (e.g. library_scores.tsv)")
    parser.add_argument("--samples", type=int, default=200,
                        help="Posterior sample count (100-2000; default 200)")
    parser.add_argument("--gpu", type=int, default=-1,
                        help="CUDA device for crispAI/Cas-OFFinder (-1 = CPU)")
    parser.add_argument("--out", default=None,
                        help="Raw crispAI aggregate output TSV")
    parser.add_argument("--log", default=None,
                        help="Log file for the crispAI subprocess")
    parser.add_argument("--check-only", action="store_true",
                        help="Only check the crispAI environment and exit")
    parser.add_argument("--no-backfill", action="store_true",
                        help="Write raw aggregate scores without touching input TSV")
    args = parser.parse_args()

    if not os.path.isfile(args.candidates_tsv):
        print("Error: candidate TSV not found: %s" % args.candidates_tsv)
        return 2

    if args.check_only:
        status_detail = model_status_details()
        print("crispAI status: %s" % status_detail["status"])
        for name, path in status_detail.get("paths", {}).items():
            print("  %s: %s" % (name, path))
        for warning in status_detail.get("warnings", []):
            print("Warning: %s" % warning)
        for error in status_detail.get("errors", []):
            print("Error: %s" % error)
        if status_detail["status"] != "ready":
            print("crispAI environment is not ready.")
            return 3
        print("crispAI environment is ready.")
        return 0

    records = collect_sgrnas(args.candidates_tsv)
    if not records:
        print("Error: no 20-nt guide_seq rows found in %s" % args.candidates_tsv)
        return 2
    print("Collected %d unique Cas9 sgRNA(s)." % len(records))

    output_dir = os.path.dirname(os.path.abspath(args.candidates_tsv))
    print("Running vendored crispAI aggregate pipeline...")
    result = run_crispai_aggregate(
        (record["sgrna"] for record in records),
        output_dir,
        n_samples=args.samples,
        gpu=args.gpu,
        fallback_model="none",
    )
    if not result.succeeded:
        print("Error: %s" % result.fallback_reason)
        if result.log_path:
            print("Log: %s" % result.log_path)
        return 1

    default_aggregate = _default_output(
        args.candidates_tsv, "crispai.aggregate")
    default_log = _default_output(args.candidates_tsv, "crispai.log")
    try:
        aggregate_path = _publish(
            result.aggregate_output_path, args.out or default_aggregate)
        log_path = _publish(
            result.log_path, args.log or default_log)
    except (OSError, ValueError) as exc:
        print("Error: could not publish crispAI outputs: %s" % exc)
        return 1
    metadata = result.metadata()
    metadata["published_aggregate"] = aggregate_path
    metadata["published_log"] = log_path
    metadata_path = _default_output(args.candidates_tsv, "crispai.run")
    metadata_path = os.path.splitext(metadata_path)[0] + ".json"
    _write_metadata(metadata_path, metadata)
    print("Parsed crispAI aggregate scores for %d sgRNA(s)." % len(result.scores))

    if args.no_backfill:
        print("Raw aggregate output: %s" % aggregate_path)
        return 0

    try:
        matched, written = backfill_candidates(
            args.candidates_tsv, aggregate_path)
    except ValueError as exc:
        print("Error: %s" % exc)
        return 1
    print(
        "Backfilled crispai_off_target for %d/%d row(s); "
        "specificity = 1 / (1 + aggregate)." % (matched, written)
    )
    print("Updated TSV: %s" % args.candidates_tsv)
    print("Raw aggregate output: %s" % aggregate_path)
    print("Log: %s" % log_path)
    sample = next(iter(result.scores.items()))
    print(
        "Example: %s aggregate=%.4f specificity=%.4f"
        % (sample[0], sample[1], specificity_from_aggregate(sample[1]))
    )
    print("Run metadata: %s" % metadata_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
