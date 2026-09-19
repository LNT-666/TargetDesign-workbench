#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Seed-plan cost sweep, determinism probe, and W(s) reproduction.

Only the native indexed engine CLI is driven here
(``offtarget-engine build-index`` / ``offtarget-engine search``).  On top of
that this file carries an independent Python transcription of the seed-plan
cost model implemented in ``native/offtarget_engine/src/seed_plan.cpp``; the
transcription annotates and cross-checks every sweep record and is the W(s)
reproduction required by the paper analysis.

Usage
-----
Grid sweep (16 configurations, C3):

    python tools/seed_plan_sweep.py \
        --engine-exe native/bin/offtarget-engine.exe \
        --genome example/engine_benchmark_small/synthetic_genome.fa \
        --guides example/engine_benchmark_small/guides.tsv \
        --out docs/seed_plan_sweep.json --repeats 3

Plan / W(s) table (C5):

    python tools/seed_plan_sweep.py --plan-table

Determinism probe (C4, fixed M=2, B=0, k=10):

    python tools/seed_plan_sweep.py \
        --engine-exe native/bin/offtarget-engine.exe \
        --genome example/engine_benchmark_small/synthetic_genome.fa \
        --guides example/engine_benchmark_small/guides.tsv --determinism
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# --- constants mirrored from the C++ sources -------------------------------

DEFAULT_MAX_SEED_VARIANTS = 500000      # seed_plan.hpp:11
UINT64_MAX = (1 << 64) - 1              # seed_plan.cpp:108-109
DEFAULT_GRID_MISMATCH = (0, 1, 2, 3)    # C3
DEFAULT_GRID_BULGE = (0, 1)             # C3
DEFAULT_GRID_K = (8, 10)                # C3
DEFAULT_DET_MISMATCH = 2                # C4
DEFAULT_DET_BULGE = 0                   # C4
DEFAULT_DET_K = 10                      # C4
DEFAULT_DET_THREADS = (1, 4, 8, 32)     # C4
HIT_TAG = '"type":"hit"'                # C4

# --- C5: Python transcription of seed_plan.cpp -----------------------------


def capped_add(left: int, right: int, cap: int) -> int:
    """seed_plan.cpp:14-20."""
    if left > cap or right > cap or left > cap - right:
        return cap + 1
    return left + right


def capped_mul(left: int, right: int, cap: int) -> int:
    """seed_plan.cpp:22-31."""
    if left == 0 or right == 0:
        return 0
    if left > cap // right:
        return cap + 1
    return left * right


def binomial(n: int, k: int, cap: int) -> int:
    """seed_plan.cpp:33-44."""
    if k > n:
        return 0
    k = min(k, n - k)
    result = 1
    for index in range(1, k + 1):
        result = capped_mul(result, n - k + index, cap) // index
    return result


def power_three(exponent: int, cap: int) -> int:
    """seed_plan.cpp:46-52."""
    result = 1
    for _ in range(exponent):
        result = capped_mul(result, 3, cap)
    return result


def partition_lengths(length: int, count: int) -> list[int]:
    """seed_plan.cpp:54-61 (remainder is spread over the leading seeds)."""
    sizes = [length // count] * count
    remainder = length % count
    for index in range(remainder):
        sizes[index] += 1
    return sizes


def variant_count(seed_len: int, max_mismatch: int) -> int:
    """seed_plan.cpp:105-121 -- V(k, m) = sum_c C(k, c) * 3**c."""
    seed_len = max(0, seed_len)
    max_mismatch = max(0, min(max_mismatch, seed_len))
    cap = UINT64_MAX
    count = 0
    for changes in range(max_mismatch + 1):
        combinations = binomial(seed_len, changes, cap)
        substitutions = power_three(changes, cap)
        count = capped_add(count, capped_mul(combinations, substitutions, cap),
                           cap)
    return count


def segmented_variant_work(segment_len: int, kmer_size: int,
                           max_mismatch: int) -> int:
    """seed_plan.cpp:63-69 -- windows * variants, no cap applied."""
    window_count = max(1, segment_len - kmer_size + 1)
    return window_count * variant_count(kmer_size, max_mismatch)


def build_seed_plan(probe_len: int, max_mismatch: int, max_bulge: int,
                    seed_len: int, kmer_size: int,
                    max_variants: int = DEFAULT_MAX_SEED_VARIANTS) -> dict:
    """seed_plan.cpp:123-206 (seed_len is parsed and then ignored)."""
    del seed_len                                   # seed_plan.cpp:126
    probe_len = max(0, probe_len)
    max_mismatch = max(0, max_mismatch)
    max_bulge = max(0, max_bulge)
    minimum_seed_len = max(1, kmer_size)           # seed_plan.cpp:130
    max_seed_count = probe_len // minimum_seed_len  # seed_plan.cpp:131
    minimum_seed_count = max(1, max_bulge + 1)     # seed_plan.cpp:132

    if max_seed_count < minimum_seed_count:        # seed_plan.cpp:134-143
        return {
            "guaranteed": False,
            "estimated_variants": 0,
            "segments": [{"start": 0, "length": probe_len,
                          "allowed_mismatches": max_mismatch}],
            "reason": ("need at least %d non-overlapping %d-nt seeds to cover "
                       "max_bulge=%d, but the guide only fits %d"
                       % (minimum_seed_count, minimum_seed_len, max_bulge,
                          max_seed_count)),
        }

    found = False
    best_variants = 0
    best_count = 0
    best_segments: list[dict] = []
    for seed_count in range(minimum_seed_count, max_seed_count + 1):
        denominator = seed_count - max_bulge       # seed_plan.cpp:151
        if denominator <= 0:                       # seed_plan.cpp:152-154
            continue
        allowed = max_mismatch // denominator      # seed_plan.cpp:155
        sizes = partition_lengths(probe_len, seed_count)
        total_variants = 0
        over_cap = False
        for size in sizes:                         # seed_plan.cpp:160-169
            total_variants = capped_add(
                total_variants,
                segmented_variant_work(size, minimum_seed_len, allowed),
                max_variants)
            if max_variants != 0 and total_variants > max_variants:
                over_cap = True
                break
        if over_cap:                               # seed_plan.cpp:170-172
            continue

        segments = []
        cursor = 0
        for size in sizes:                         # seed_plan.cpp:174-179
            segments.append({"start": cursor, "length": size,
                             "allowed_mismatches": allowed})
            cursor += size
        if not found or (total_variants, seed_count) < (best_variants,
                                                       best_count):
            found = True                           # seed_plan.cpp:181-187
            best_variants = total_variants
            best_count = seed_count
            best_segments = segments

    if not found:                                  # seed_plan.cpp:190-199
        return {
            "guaranteed": False,
            "estimated_variants": 0,
            "segments": [{"start": 0, "length": probe_len,
                          "allowed_mismatches": max_mismatch}],
            "reason": ("the exhaustive seed variants for max_mismatch=%d, "
                       "max_bulge=%d exceed the configured cap %d"
                       % (max_mismatch, max_bulge, max_variants)),
        }

    return {                                       # seed_plan.cpp:201-205
        "guaranteed": True,
        "estimated_variants": best_variants,
        "seed_count": best_count,
        "segments": best_segments,
        "reason": "",
    }


def render_plan(plan: dict) -> str:
    """Compact one-line rendering of a seed plan for the printed table."""
    if not plan["guaranteed"]:
        return "UNGARANTEED"
    segments = plan["segments"]
    lengths = {segment["length"] for segment in segments}
    allowed = {segment["allowed_mismatches"] for segment in segments}
    if len(lengths) == 1 and len(allowed) == 1:
        return "%dx%dbp@%d" % (len(segments), lengths.pop(), allowed.pop())
    return "+".join("%d:%d@%d" % (segment["start"], segment["length"],
                                  segment["allowed_mismatches"])
                    for segment in segments)


# --- engine drivers --------------------------------------------------------


def run_engine(command: list[str]) -> str:
    """Run one engine invocation and return its stdout, or fail loudly."""
    started = time.perf_counter()
    process = subprocess.run(command, capture_output=True)
    elapsed = time.perf_counter() - started
    stdout = process.stdout.decode("utf-8", "replace")
    stderr = process.stderr.decode("utf-8", "replace")
    if process.returncode != 0:
        raise SystemExit("engine failed (exit %d, %.3fs): %s\n--- stdout ---\n%s"
                         "--- stderr ---\n%s"
                         % (process.returncode, elapsed, " ".join(command),
                            stdout, stderr))
    return stdout


def parse_json_object(text: str) -> dict:
    start = text.find("{")
    if start < 0:
        raise SystemExit("no JSON object in engine output:\n%s" % text)
    return json.loads(text[start:])


def build_index(exe: str, genome: Path, prefix: Path, k: int,
                threads: int) -> dict:
    """C1 build verb; returns the manifest the engine prints."""
    stdout = run_engine([exe, "build-index", "--genome", str(genome),
                         "--prefix", str(prefix), "--k", str(k),
                         "--threads", str(threads), "--force"])
    manifest = parse_json_object(stdout)
    on_disk = Path(str(prefix) + ".json")
    if on_disk.exists():
        manifest["manifest_bytes"] = on_disk.stat().st_size
    return manifest


def search_index(exe: str, genome: Path, prefix: Path, guides: Path,
                 output: Path, max_mismatch: int, max_bulge: int, seed_len: int,
                 threads: int) -> dict:
    """C1 search verb; returns the JSONL summary line plus the hit lines."""
    run_engine([exe, "search", "--genome", str(genome), "--index", str(prefix),
                "--guides", str(guides), "--output", str(output),
                "--max-mismatch", str(max_mismatch), "--max-bulge",
                str(max_bulge), "--seed-len", str(seed_len), "--threads",
                str(threads), "--progress-every", "0"])
    summary = None
    hit_lines: list[str] = []
    for line in output.read_text(encoding="utf-8").splitlines():
        if HIT_TAG in line:
            hit_lines.append(line)
        elif '"type":"summary"' in line:
            summary = json.loads(line)
    if summary is None:
        raise SystemExit("no summary line in %s" % output)
    summary["hit_lines"] = hit_lines
    return summary


def count_guides(guides: Path) -> tuple[int, int]:
    """Return (guide_count, longest_guide_len) using the TSV header."""
    rows = guides.read_text(encoding="utf-8").splitlines()
    sequences = [row.split("\t")[1] for row in rows[1:] if "\t" in row]
    sequences = [sequence.strip() for sequence in sequences if sequence.strip()]
    if not sequences:
        raise SystemExit("no guide_seq values in %s" % guides)
    return len(sequences), max(len(sequence) for sequence in sequences)


def sha256_of_hits(hit_lines: list[str]) -> str:
    """C4: SHA-256 over the grep-extracted hit lines, newline joined."""
    payload = "\n".join(hit_lines).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


# --- modes -----------------------------------------------------------------


def run_sweep(args) -> int:
    exe = str(Path(args.engine_exe).resolve())
    genome = Path(args.genome).resolve()
    guides = Path(args.guides).resolve()
    out_path = Path(args.out)
    guide_count, guide_len = count_guides(guides)

    work_root = (Path(args.work_dir).resolve() if args.work_dir
                 else Path(tempfile.mkdtemp(prefix="seed_plan_sweep_")))
    work_root.mkdir(parents=True, exist_ok=True)

    version = run_engine([exe, "--version"]).strip()
    capabilities = parse_json_object(
        run_engine([exe, "capabilities", "--json"]))

    records = []
    builds = []
    try:
        for k in args.ks:
            prefix = work_root / ("idx_k%d" % k)
            build = build_index(exe, genome, prefix, k, args.threads)
            builds.append({
                "k": k,
                "threads": args.threads,
                "build_time_s": build.get("build_time_s"),
                "index_bytes": build.get("index_bytes"),
                "total_bases": build.get("total_bases"),
                "position_dtype": build.get("position_dtype"),
            })
            for max_mismatch in args.mismatches:
                for max_bulge in args.bulges:
                    times = []
                    summaries = []
                    for repeat in range(args.repeats):
                        output = work_root / ("hits_k%d_m%d_b%d_r%d.jsonl"
                                              % (k, max_mismatch, max_bulge,
                                                 repeat))
                        summary = search_index(
                            exe, genome, prefix, guides, output, max_mismatch,
                            max_bulge, k, args.threads)
                        times.append(summary["search_time_s"])
                        summaries.append(summary)
                    first = summaries[0]
                    consistent = all(
                        (item["hits"], item["candidates"],
                         item["seed_plan_guaranteed"],
                         item["exhaustive_seed_plan"]) ==
                        (first["hits"], first["candidates"],
                         first["seed_plan_guaranteed"],
                         first["exhaustive_seed_plan"])
                        for item in summaries)
                    plan = build_seed_plan(guide_len, max_mismatch, max_bulge, k,
                                           k)
                    records.append({
                        "M": max_mismatch,
                        "B": max_bulge,
                        "k": k,
                        "seed_len": k,
                        "threads": args.threads,
                        "repeats": args.repeats,
                        "median_search_time_s": round(statistics.median(times),
                                                      4),
                        "search_time_s_all": [round(value, 4)
                                              for value in times],
                        "candidates": first["candidates"],
                        "hits": first["hits"],
                        "guides": first["guides"],
                        "seed_plan_guaranteed": first["seed_plan_guaranteed"],
                        "exhaustive_seed_plan": first["exhaustive_seed_plan"],
                        "build_time_s": build.get("build_time_s"),
                        "memory_peak_mb": first["memory_peak_mb"],
                        "repeats_consistent": consistent,
                        "py_plan_guaranteed": plan["guaranteed"],
                        "py_plan_variants": plan["estimated_variants"],
                        "py_plan_segments": render_plan(plan),
                    })
                    print("k=%d M=%d B=%d median=%.4fs plan=%s"
                          % (k, max_mismatch, max_bulge,
                             statistics.median(times), render_plan(plan)),
                          flush=True)
    finally:
        if not args.keep_work_dir and not args.work_dir:
            import shutil
            shutil.rmtree(work_root, ignore_errors=True)

    document = {
        "task": "engine-bench",
        "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "engine": {"path": exe, "version": version,
                   "capabilities": capabilities},
        "fixture": {"genome": str(genome), "guides": str(guides),
                    "guide_count": guide_count, "guide_len": guide_len},
        "protocol": {
            "grid": {"max_mismatch": list(args.mismatches),
                     "max_bulge": list(args.bulges), "k": list(args.ks)},
            "repeats": args.repeats,
            "threads": args.threads,
            "build_policy": "one index per k, reused for every M/B pair",
            "seed_len_policy": ("--seed-len is set to the index k; "
                                "seed_plan.cpp:126 ignores it"),
            "cost_model": ("W(s) = sum_i max(1, L_i - k + 1) * V(k, a), "
                           "V(k, a) = sum_c C(k, c) * 3**c, "
                           "a = M // (N_seeds - B)"),
        },
        "index_builds": builds,
        "records": records,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes((json.dumps(document, ensure_ascii=False, indent=2)
                          + "\n").encode("utf-8"))

    header = ("k  M  B  reps  median_time_s  candidates  hits  "
              "guaranteed  exhaustive  build_time_s  plan")
    print("")
    print(header)
    print("-" * len(header))
    for record in records:
        print("%-2d %-2d %-2d %-5d %-14.4f %-11d %-5d %-11s %-11s %-13s %s"
              % (record["k"], record["M"], record["B"], record["repeats"],
                 record["median_search_time_s"], record["candidates"],
                 record["hits"],
                 str(record["seed_plan_guaranteed"]).lower(),
                 str(record["exhaustive_seed_plan"]).lower(),
                 ("" if record["build_time_s"] is None
                  else "%.3f" % record["build_time_s"]),
                 record["py_plan_segments"]))
    print("")
    print("wrote %s (%d records)" % (out_path, len(records)))
    return 0


def run_plan_table(args) -> int:
    guide_len = args.probe_len
    print("V(k, m) = sum_c C(k, c) * 3**c  [variant_count, seed_plan.cpp:105]")
    ks = sorted(set(args.ks) | {args.det_k})
    print("k  m  V(k, m)")
    for k in ks:
        for m in range(0, max(list(args.mismatches) + [args.det_mismatch]) + 1):
            print("%-2d %-2d %d" % (k, m, variant_count(k, m)))
    print("")
    print("seed plan / W(s) for probe_len=%d, kmer_size=k, "
          "cap=%d [build_seed_plan, seed_plan.cpp:123]"
          % (guide_len, DEFAULT_MAX_SEED_VARIANTS))
    print("k  M  B  N  seg_len  allowed  W(s)  guaranteed  segments")
    for k in args.ks:
        for m in args.mismatches:
            for b in args.bulges:
                plan = build_seed_plan(guide_len, m, b, k, k)
                segments = plan["segments"]
                lengths = {segment["length"] for segment in segments}
                allowed = {segment["allowed_mismatches"] for segment in segments}
                print("%-2d %-2d %-2d %-2d %-7s %-8s %-5d %-11s %s"
                      % (k, m, b, len(segments),
                         (str(lengths.pop()) if len(lengths) == 1 else "mixed"),
                         (str(allowed.pop()) if len(allowed) == 1 else "mixed"),
                         plan["estimated_variants"],
                         str(plan["guaranteed"]).lower(),
                         render_plan(plan)))
    return 0


def run_determinism(args) -> int:
    exe = str(Path(args.engine_exe).resolve())
    genome = Path(args.genome).resolve()
    guides = Path(args.guides).resolve()
    k = args.det_k
    work_root = (Path(args.work_dir).resolve() if args.work_dir
                 else Path(tempfile.mkdtemp(prefix="seed_plan_det_")))
    work_root.mkdir(parents=True, exist_ok=True)
    rows = []
    try:
        prefix = work_root / ("idx_k%d" % k)
        build_index(exe, genome, prefix, k, args.threads)
        for threads in args.det_threads:
            output = work_root / ("hits_threads%d.jsonl" % threads)
            summary = search_index(exe, genome, prefix, guides, output,
                                   args.det_mismatch, args.det_bulge, k,
                                   threads)
            digest = sha256_of_hits(summary["hit_lines"])
            rows.append({"threads": threads, "hits": summary["hits"],
                         "sha256": digest,
                         "candidates": summary["candidates"],
                         "search_time_s": summary["search_time_s"]})
            print("threads=%d hits=%d sha256=%s" % (threads, summary["hits"],
                                                    digest), flush=True)
    finally:
        if not args.keep_work_dir and not args.work_dir:
            import shutil
            shutil.rmtree(work_root, ignore_errors=True)

    digests = {row["sha256"] for row in rows}
    print("")
    print("M=%d B=%d k=%d threads=%s"
          % (args.det_mismatch, args.det_bulge, k, list(args.det_threads)))
    print("hits per thread count: %s"
          % [row["hits"] for row in rows])
    print("sha256_all_equal: %s (%d distinct values)"
          % (str(len(digests) == 1).lower(), len(digests)))
    if args.det_out:
        document = {
            "task": "engine-bench",
            "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
            "engine": exe,
            "max_mismatch": args.det_mismatch,
            "max_bulge": args.det_bulge,
            "k": k,
            "hit_line_filter": HIT_TAG,
            "sha256_all_equal": len(digests) == 1,
            "rows": rows,
        }
        Path(args.det_out).write_bytes(
            (json.dumps(document, ensure_ascii=False, indent=2)
             + "\n").encode("utf-8"))
        print("wrote %s" % args.det_out)
    return 0 if len(digests) == 1 else 1


def parse_csv(value: str, cast):
    return [cast(item) for item in value.replace(" ", "").split(",") if item]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--engine-exe", default="native/bin/offtarget-engine.exe",
                        help="path to the native engine executable")
    parser.add_argument("--genome", default="example/engine_benchmark_small/synthetic_genome.fa")
    parser.add_argument("--guides", default="example/engine_benchmark_small/guides.tsv")
    parser.add_argument("--out", default="docs/seed_plan_sweep.json",
                        help="grid sweep output JSON")
    parser.add_argument("--repeats", type=int, default=3, help="C3: repeats per grid cell")
    parser.add_argument("--threads", type=int, default=8,
                        help="threads for build and search")
    parser.add_argument("--mismatches", default="0,1,2,3", help="C3 grid M values")
    parser.add_argument("--bulges", default="0,1", help="C3 grid B values")
    parser.add_argument("--ks", default="8,10", help="C3 grid index k values")
    parser.add_argument("--work-dir", default=None,
                        help="reuse this directory for indexes and JSONL outputs")
    parser.add_argument("--keep-work-dir", action="store_true",
                        help="keep the temporary work directory")
    parser.add_argument("--plan-table", action="store_true",
                        help="print the C5 plan / W(s) table and exit")
    parser.add_argument("--probe-len", type=int, default=20,
                        help="guide length used by --plan-table")
    parser.add_argument("--determinism", action="store_true",
                        help="run the C4 determinism probe instead of the sweep")
    parser.add_argument("--det-mismatch", type=int, default=DEFAULT_DET_MISMATCH)
    parser.add_argument("--det-bulge", type=int, default=DEFAULT_DET_BULGE)
    parser.add_argument("--det-k", type=int, default=DEFAULT_DET_K)
    parser.add_argument("--det-threads", default="1,4,8,32")
    parser.add_argument("--det-out", default=None,
                        help="optional JSON sidecar for the determinism probe")
    args = parser.parse_args(argv)

    args.mismatches = parse_csv(args.mismatches, int)
    args.bulges = parse_csv(args.bulges, int)
    args.ks = parse_csv(args.ks, int)
    args.det_threads = parse_csv(args.det_threads, int)

    if args.repeats < 1:
        raise SystemExit("--repeats must be >= 1")
    if args.plan_table:
        return run_plan_table(args)
    if args.determinism:
        return run_determinism(args)
    return run_sweep(args)


if __name__ == "__main__":
    sys.exit(main())
