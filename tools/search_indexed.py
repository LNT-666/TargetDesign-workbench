#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Standalone off-target search against a local genome index."""

import argparse
import csv
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "shared"))

from search.offtarget_backend import (  # noqa: E402
    HIT_FIELDS, PYTHON_FALLBACK_ENV, IndexedBackend, SearchParams,
    apply_engine_defaults,
)


def main():
    parser = argparse.ArgumentParser(
        description="Search guides against a reusable local genome index")
    parser.add_argument("guides_tsv", help="Guide TSV with a guide_seq column")
    parser.add_argument("genome_fasta", help="Genome FASTA")
    parser.add_argument("output_dir", help="Output directory")
    parser.add_argument("--index-path", default=None,
                        help="Index prefix; built when missing or stale")
    parser.add_argument("--max-mismatch", type=int, default=4)
    parser.add_argument(
        "--max-bulge", type=int, choices=[0, 1], default=None,
        help="Maximum bulge events. Defaults to 1 for small genomes and 0 "
             "for large-genome indexed searches.")
    parser.add_argument("--seed-len", type=int, default=12)
    parser.add_argument("--require-pam", action="store_true")
    parser.add_argument("--pam", default="NGG")
    parser.add_argument("--pam-side", choices=["3prime", "5prime"],
                        default="3prime")
    parser.add_argument(
        "--max-memory-mb", type=int, default=None,
        help="Explicit process RSS limit in MiB; omitted or 0 is unlimited")
    parser.add_argument(
        "--timeout-s", type=float, default=None,
        help="Wall-clock budget for the search, in seconds; default is no "
             "timeout")
    parser.add_argument(
        "--python-fallback", default=None, choices=["ask", "allow", "deny"],
        help="Pure-Python index fallback policy; defaults to ask, or the "
             "value of the %s environment variable" % PYTHON_FALLBACK_ENV)
    cache_group = parser.add_mutually_exclusive_group()
    cache_group.add_argument(
        "--cache-genome", dest="cache_genome", action="store_true",
        default=None,
        help="Load the FASTA into memory for window reads")
    cache_group.add_argument(
        "--no-cache-genome", dest="cache_genome", action="store_false",
        help="Keep random-access FASTA reads during search")
    args = parser.parse_args()

    if not os.path.isfile(args.guides_tsv) or \
            not os.path.isfile(args.genome_fasta):
        print("Error: input files not found.")
        sys.exit(2)
    os.makedirs(args.output_dir, exist_ok=True)
    with open(args.guides_tsv, encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    if not rows or "guide_seq" not in rows[0]:
        print("Error: guides_tsv must contain a guide_seq column.")
        sys.exit(2)
    guides = []
    for i, row in enumerate(rows):
        guides.append({
            "qid": row.get("qid") or row.get("id") or "g%d" % i,
            "guide_seq": row["guide_seq"],
        })

    extra = {
        key: value for key, value in (
            ("cache_genome", args.cache_genome),
            ("max_memory_mb", args.max_memory_mb),
            ("timeout_s", args.timeout_s),
        )
        if value is not None
    }
    extra["python_fallback"] = (
        args.python_fallback or os.environ.get(PYTHON_FALLBACK_ENV) or "ask")
    params = SearchParams(
        max_mismatch=args.max_mismatch,
        max_bulge=1 if args.max_bulge is None else args.max_bulge,
        max_bulge_explicit=args.max_bulge is not None,
        seed_len=args.seed_len,
        pam=args.pam if args.require_pam else None,
        pam_side=args.pam_side,
        require_pam=args.require_pam,
        index_path=args.index_path,
        output_dir=args.output_dir,
        extra=extra,
    )
    apply_engine_defaults(
        "indexed", params, os.path.getsize(args.genome_fasta))
    backend = IndexedBackend()
    try:
        matches = backend.search(
            guides, args.genome_fasta, params,
            log=lambda msg: print(msg, flush=True))
    except RuntimeError as exc:
        print("Off-target search failed: %s" % exc)
        sys.exit(3)

    out_path = os.path.join(args.output_dir, "top_offtargets.tsv")
    with open(out_path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=HIT_FIELDS,
                                delimiter="\t", extrasaction="ignore")
        writer.writeheader()
        for qid in sorted(matches):
            for hit in matches[qid]:
                writer.writerow(hit)

    report_path = os.path.join(args.output_dir, "index_report.json")
    with open(report_path, "w", encoding="utf-8") as handle:
        json.dump(backend.last_report, handle, indent=2, ensure_ascii=False)

    total = sum(len(v) for v in matches.values())
    print("Wrote %d hits to %s" % (total, out_path))
    print("Report: %s" % report_path)


if __name__ == "__main__":
    main()
