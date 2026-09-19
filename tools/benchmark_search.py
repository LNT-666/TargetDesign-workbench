#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Small reproducible benchmark for exact/indexed off-target searches."""

import argparse
import csv
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "shared"))

from search.genome_index import (  # noqa: E402
    DEFAULT_K, _MemTracker, suggest_k,
)
from search.offtarget_backend import (  # noqa: E402
    SearchParams, apply_engine_defaults, get_backend,
)
from search.seed_plan import build_seed_plan  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("guides_tsv")
    parser.add_argument("genome_fasta")
    parser.add_argument("--engine", choices=["exact", "indexed"],
                        default="indexed")
    parser.add_argument("--index-path", default=None)
    parser.add_argument("--index-k", type=int, default=None)
    parser.add_argument("--max-mismatch", type=int, default=4)
    parser.add_argument("--max-bulge", type=int, choices=[0, 1],
                        default=None)
    parser.add_argument("--seed-len", type=int, default=12)
    parser.add_argument("--pam", default=None)
    parser.add_argument("--pam-side", choices=["3prime", "5prime"],
                        default="3prime")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    with open(args.guides_tsv, encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    guides = [
        {
            "qid": row.get("qid") or "g%d" % index,
            "guide_seq": row.get("guide_seq") or "",
        }
        for index, row in enumerate(rows)
    ]
    guides = [guide for guide in guides if guide["guide_seq"]]
    if args.limit:
        guides = guides[:args.limit]
    if not guides:
        raise SystemExit("No guide_seq rows found")

    k = args.index_k or (
        suggest_k(os.path.getsize(args.genome_fasta))
        if args.engine == "indexed" else DEFAULT_K
    )
    params = SearchParams(
        max_mismatch=args.max_mismatch,
        max_bulge=1 if args.max_bulge is None else args.max_bulge,
        max_bulge_explicit=args.max_bulge is not None,
        seed_len=args.seed_len,
        pam=args.pam,
        pam_side=args.pam_side,
        require_pam=bool(args.pam),
        index_path=args.index_path,
        extra={"k": k},
    )
    apply_engine_defaults(
        args.engine, params, os.path.getsize(args.genome_fasta))
    longest_guide = max(len(guide["guide_seq"]) for guide in guides)
    plan = build_seed_plan(
        longest_guide,
        params.max_mismatch,
        params.max_bulge,
        k,
        k,
    )
    tracker = _MemTracker()
    started = time.perf_counter()
    results = get_backend(args.engine).search(
        guides, args.genome_fasta, params,
        log=lambda message: print(message, flush=True))
    elapsed = time.perf_counter() - started
    tracker.sample()
    hits = sum(len(items) for items in results.values())
    report = {
        "engine": args.engine,
        "guides": len(guides),
        "longest_guide": longest_guide,
        "k": k,
        "max_mismatch": params.max_mismatch,
        "max_bulge": params.max_bulge,
        "seed_plan_guaranteed": plan.guaranteed,
        "seed_plan_reason": plan.reason,
        "seed_plan_variants": plan.estimated_variants,
        "elapsed_seconds": round(elapsed, 4),
        "guides_per_second": round(len(guides) / max(elapsed, 1e-9), 2),
        "hits": hits,
        "memory_peak_mb": round(tracker.peak, 2),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
