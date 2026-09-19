#!/usr/bin/env python3
"""Benchmark the available off-target engines on a synthetic fixture."""

import argparse
import csv
import json
import os
import random
import shutil
import statistics
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "shared"))

from search.blast_utils import build_blastdb  # noqa: E402
from search.offtarget_backend import (  # noqa: E402
    SearchParams, get_backend,
)


def reverse_complement(sequence):
    return sequence.translate(str.maketrans("ACGT", "TGCA"))[::-1]


def choose_position(rng, length, reserved, width=20):
    for _ in range(1000):
        position = rng.randrange(0, length - width)
        if all(
            position + width + 50 < start or position > end + 50
            for start, end in reserved
        ):
            reserved.append((position, position + width))
            return position
    raise RuntimeError("Could not place synthetic sequence")


def generate_fixture(fixture_dir, total_bases=5000000, contig_count=4,
                     guide_count=24):
    os.makedirs(fixture_dir, exist_ok=True)
    genome_path = os.path.join(fixture_dir, "synthetic_genome.fa")
    guides_path = os.path.join(fixture_dir, "guides.tsv")
    metadata_path = os.path.join(fixture_dir, "fixture.json")

    rng = random.Random(20260914)
    contig_length = total_bases // contig_count
    sequences = [
        "".join(rng.choice("ACGT") for _ in range(contig_length))
        for _ in range(contig_count)
    ]
    reserved = [[] for _ in range(contig_count)]
    guides = []
    seen = set()
    while len(guides) < guide_count:
        contig_index = len(guides) % contig_count
        sequence = sequences[contig_index]
        position = choose_position(
            rng, len(sequence), reserved[contig_index])
        guide = sequence[position:position + 20]
        if guide in seen:
            continue
        seen.add(guide)
        guides.append({
            "qid": "g%02d" % (len(guides) + 1),
            "guide_seq": guide,
        })

    for index, guide in enumerate(guides):
        guide_seq = guide["guide_seq"]

        rc_contig = (index + 1) % contig_count
        rc_pos = choose_position(
            rng, len(sequences[rc_contig]), reserved[rc_contig])
        rc = reverse_complement(guide_seq)
        sequences[rc_contig] = (
            sequences[rc_contig][:rc_pos] + rc +
            sequences[rc_contig][rc_pos + len(rc):]
        )

        mismatch_contig = (index + 2) % contig_count
        mismatch_pos = choose_position(
            rng, len(sequences[mismatch_contig]),
            reserved[mismatch_contig])
        mismatch_pos_in_guide = rng.randrange(len(guide_seq))
        replacement = rng.choice([
            base for base in "ACGT"
            if base != guide_seq[mismatch_pos_in_guide]
        ])
        mutated = list(guide_seq)
        mutated[mismatch_pos_in_guide] = replacement
        mutated = "".join(mutated)
        sequences[mismatch_contig] = (
            sequences[mismatch_contig][:mismatch_pos] + mutated +
            sequences[mismatch_contig][mismatch_pos + len(mutated):]
        )

    with open(genome_path, "w", encoding="ascii", newline="") as handle:
        for index, sequence in enumerate(sequences, start=1):
            handle.write(">chr%d\n" % index)
            for start in range(0, len(sequence), 80):
                handle.write(sequence[start:start + 80] + "\n")
    with open(guides_path, "w", encoding="ascii", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["qid", "guide_seq"], delimiter="\t")
        writer.writeheader()
        writer.writerows(guides)
    metadata = {
        "genome": genome_path,
        "guides": guides_path,
        "genome_bases": contig_length * contig_count,
        "contigs": contig_count,
        "guides_count": len(guides),
        "guide_length": 20,
        "planted_layout": (
            "one sampled exact target plus one reverse-complement exact "
            "target plus one one-mismatch target per guide"
        ),
    }
    with open(metadata_path, "w", encoding="utf-8") as handle:
        json.dump(metadata, handle, indent=2)
    return genome_path, guides_path


def load_guides(path):
    with open(path, encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    return [
        {"qid": row["qid"], "guide_seq": row["guide_seq"]}
        for row in rows
    ]


def remove_paths(*paths):
    for path in paths:
        if os.path.isdir(path):
            shutil.rmtree(path)
        elif os.path.exists(path):
            os.unlink(path)


def remove_index(prefix):
    remove_paths(prefix + ".ggi", prefix + ".json")


def make_params(workdir, threads, max_mismatch, max_bulge,
                index_path=None, blastdb=None, index_k=None):
    extra = {"threads": threads}
    if index_k is not None:
        extra["k"] = index_k
    return SearchParams(
        max_mismatch=max_mismatch,
        max_bulge=max_bulge,
        max_bulge_explicit=True,
        seed_len=12,
        output_dir=workdir,
        index_path=index_path,
        blastdb=blastdb,
        extra=extra,
    )


def run_search(engine, guides, genome_path, params):
    backend = get_backend(engine)
    started = time.perf_counter()
    results = backend.search(
        guides, genome_path, params,
        log=lambda message: print(message, flush=True))
    elapsed = time.perf_counter() - started
    hits = sum(len(items) for items in results.values())
    report = dict(getattr(backend, "last_report", {}) or {})
    return elapsed, hits, report


def summarize_times(times):
    values = sorted(float(value) for value in times)
    return {
        "runs": [round(value, 4) for value in values],
        "median": round(statistics.median(values), 4),
        "best": round(values[0], 4),
    }


def benchmark_simple(engine, guides, genome_path, workdir, threads,
                     max_mismatch, max_bulge, repeats, index_k=None):
    cold_params = make_params(
        workdir, threads, max_mismatch, max_bulge, index_k=index_k)
    cold, hits, report = run_search(
        engine, guides, genome_path, cold_params)
    search_times = []
    for _ in range(repeats):
        params = make_params(
            workdir, threads, max_mismatch, max_bulge, index_k=index_k)
        elapsed, hit_count, current_report = run_search(
            engine, guides, genome_path, params)
        search_times.append(elapsed)
        hits = hit_count
        report = current_report or report
    return {
        "status": "ok",
        "cold_total_s": round(cold, 4),
        "build_s": 0.0,
        "search": summarize_times(search_times),
        "search_plus_build_s": round(
            statistics.median(search_times), 4),
        "hits": hits,
        "backend_report": report,
    }


def benchmark_indexed(engine, guides, genome_path, workdir, threads,
                      max_mismatch, max_bulge, repeats, native,
                      index_k=None):
    os.environ["PROGRAMFILE_NATIVE_INDEXED"] = "1" if native else "0"
    os.environ["PROGRAMFILE_NATIVE_INDEXED_FALLBACK"] = "0"
    prefix = os.path.join(workdir, "genome_index", "synthetic_genome")
    remove_index(prefix)
    cold_params = make_params(
        workdir, threads, max_mismatch, max_bulge, index_path=prefix,
        index_k=index_k)
    cold, hits, report = run_search(
        engine, guides, genome_path, cold_params)
    build_s = float(report.get("build_time_s") or 0.0)
    search_times = []
    for _ in range(repeats):
        params = make_params(
            workdir, threads, max_mismatch, max_bulge, index_path=prefix,
            index_k=index_k)
        elapsed, hit_count, current_report = run_search(
            engine, guides, genome_path, params)
        search_times.append(elapsed)
        hits = hit_count
        report = current_report or report
    return {
        "status": "ok",
        "cold_total_s": round(cold, 4),
        "build_s": round(build_s, 4),
        "search": summarize_times(search_times),
        "search_plus_build_s": round(
            build_s + statistics.median(search_times), 4),
        "hits": hits,
        "backend_report": report,
    }


def benchmark_blast(guides, genome_path, workdir, threads,
                    max_mismatch, max_bulge, repeats, index_k=None):
    db_prefix = os.path.join(workdir, "blastdb", "synthetic_genome.blastdb")
    remove_paths(
        db_prefix + ".nin", db_prefix + ".nsq", db_prefix + ".nhr",
        db_prefix + ".ndb", db_prefix + ".not", db_prefix + ".ntf",
        db_prefix + ".nto", db_prefix + ".nos", db_prefix + ".nog",
        db_prefix + ".nal", db_prefix + ".source.json",
    )
    started = time.perf_counter()
    build_blastdb(genome_path, db_prefix, log=lambda _message: None)
    build_s = time.perf_counter() - started
    search_times = []
    hits = 0
    for _ in range(repeats):
        params = make_params(
            workdir, threads, max_mismatch, max_bulge,
            blastdb=db_prefix, index_k=index_k)
        elapsed, hit_count, _report = run_search(
            "blast", guides, genome_path, params)
        search_times.append(elapsed)
        hits = hit_count
    return {
        "status": "ok",
        "cold_total_s": round(build_s + search_times[0], 4),
        "build_s": round(build_s, 4),
        "search": summarize_times(search_times),
        "search_plus_build_s": round(
            build_s + statistics.median(search_times), 4),
        "hits": hits,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fixture-dir",
        default=os.path.join(ROOT, "example", "engine_benchmark"))
    parser.add_argument("--genome-mb", type=float, default=5.0)
    parser.add_argument("--guides", type=int, default=24)
    parser.add_argument("--max-mismatch", type=int, default=2)
    parser.add_argument("--max-bulge", type=int, choices=[0, 1], default=0)
    parser.add_argument(
        "--index-k", type=int, default=None,
        help="Explicit indexed k-mer size (default: automatic)")
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--output", default=None)
    parser.add_argument(
        "--engines", default="exact,indexed,native-indexed,blast")
    args = parser.parse_args()

    genome_path, guides_path = generate_fixture(
        args.fixture_dir,
        total_bases=int(args.genome_mb * 1000000),
        guide_count=args.guides,
    )
    guides = load_guides(guides_path)
    os.environ.setdefault("SEARCH_NUM_THREADS", str(args.threads))

    engines = [item.strip() for item in args.engines.split(",") if item.strip()]
    results = {}
    for engine in engines:
        workdir = os.path.join(args.fixture_dir, "run_" + engine)
        os.makedirs(workdir, exist_ok=True)
        try:
            if engine == "exact":
                result = benchmark_simple(
                    engine, guides, genome_path, workdir, args.threads,
                    args.max_mismatch, args.max_bulge, args.repeats,
                    index_k=args.index_k)
            elif engine == "indexed":
                result = benchmark_indexed(
                    engine, guides, genome_path, workdir, args.threads,
                    args.max_mismatch, args.max_bulge, args.repeats,
                    native=False, index_k=args.index_k)
            elif engine == "native-indexed":
                result = benchmark_indexed(
                    "indexed", guides, genome_path, workdir, args.threads,
                    args.max_mismatch, args.max_bulge, args.repeats,
                    native=True, index_k=args.index_k)
            elif engine == "blast":
                result = benchmark_blast(
                    guides, genome_path, workdir, args.threads,
                    args.max_mismatch, args.max_bulge, args.repeats,
                    index_k=args.index_k)
            elif engine == "gggenome":
                result = {
                    "status": "not_comparable",
                    "reason": (
                        "GGGenome searches its remote prebuilt genome "
                        "databases, not a custom synthetic FASTA"
                    ),
                }
            else:
                result = {
                    "status": "error",
                    "reason": "unknown engine",
                }
        except Exception as exc:
            result = {
                "status": "error",
                "reason": "%s: %s" % (type(exc).__name__, exc),
            }
        results[engine] = result
        print("%s: %s" % (engine, json.dumps(result, ensure_ascii=False)))

    payload = {
        "fixture": {
            "genome_bases": int(args.genome_mb * 1000000),
            "guides": len(guides),
            "guide_length": 20,
            "max_mismatch": args.max_mismatch,
            "max_bulge": args.max_bulge,
            "index_k": args.index_k,
            "threads_for_external_engines": args.threads,
            "repeats": args.repeats,
        },
        "results": results,
    }
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
