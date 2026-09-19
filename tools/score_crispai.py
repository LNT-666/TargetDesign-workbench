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
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "shared"))

from scoring.crispai_runtime import (  # noqa: E402
    backfill_candidates,
    collect_sgrnas,
    parse_aggregate_output,
    preflight,
    run_aggregate,
    specificity_from_aggregate,
    write_aggregate_input,
)


def _default_output(path: str, suffix: str) -> str:
    directory = os.path.dirname(os.path.abspath(path))
    name = os.path.splitext(os.path.basename(path))[0]
    return os.path.join(directory, "%s.%s.tsv" % (name, suffix))


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

    errors, warnings = preflight()
    if args.check_only:
        for warning in warnings:
            print("Warning: %s" % warning)
        for error in errors:
            print("Error: %s" % error)
        if errors:
            print("crispAI environment is not ready.")
            return 3
        print("crispAI environment is ready.")
        return 0

    if errors:
        for error in errors:
            print("Error: %s" % error)
        print(
            "crispAI environment is not ready; see docs/CRISPAI.md "
            "for the dependency checklist."
        )
        return 3
    for warning in warnings:
        print("Warning: %s" % warning)

    records = collect_sgrnas(args.candidates_tsv)
    if not records:
        print("Error: no 20-nt guide_seq rows found in %s" % args.candidates_tsv)
        return 2
    print("Collected %d unique Cas9 sgRNA(s)." % len(records))

    output_dir = os.path.dirname(os.path.abspath(args.candidates_tsv))
    temp_dir = tempfile.mkdtemp(prefix="crispai_input_", dir=output_dir)
    input_path = os.path.join(temp_dir, "sgrnas.txt")
    aggregate_path = args.out or _default_output(
        args.candidates_tsv, "crispai.aggregate"
    )
    log_path = args.log or _default_output(args.candidates_tsv, "crispai.log")
    try:
        write_aggregate_input(records, input_path)
        print("Running vendored crispAI aggregate pipeline...")
        returncode = run_aggregate(
            input_path,
            aggregate_path,
            log_path=log_path,
            n_samples=args.samples,
            gpu=args.gpu,
        )
        if returncode != 0:
            print("Error: crispAI aggregate exited with code %d." % returncode)
            print("Log: %s" % log_path)
            return returncode
    finally:
        try:
            os.rmdir(temp_dir)
        except OSError:
            pass

    mapping = parse_aggregate_output(aggregate_path)
    print("Parsed crispAI aggregate scores for %d sgRNA(s)." % len(mapping))
    if not mapping:
        print("Error: no aggregate rows found in %s" % aggregate_path)
        return 1

    if args.no_backfill:
        print("Raw aggregate output: %s" % aggregate_path)
        return 0

    matched, written = backfill_candidates(
        args.candidates_tsv, aggregate_path
    )
    print(
        "Backfilled crispai_off_target for %d/%d row(s); "
        "specificity = 1 / (1 + aggregate)." % (matched, written)
    )
    print("Updated TSV: %s" % args.candidates_tsv)
    print("Raw aggregate output: %s" % aggregate_path)
    print("Log: %s" % log_path)
    sample = next(iter(mapping.items()))
    print(
        "Example: %s aggregate=%.4f specificity=%.4f"
        % (sample[0], sample[1], specificity_from_aggregate(sample[1]))
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
