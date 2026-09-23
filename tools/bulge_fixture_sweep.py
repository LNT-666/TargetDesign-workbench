#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Bulge ground-truth fixture sweep for the native indexed engine.

``tools/seed_plan_sweep.py`` plants no gapped target, so its 16 cells cannot say
whether the acceptance stage ever rejects a candidate: the ``candidates``
counter of the indexed engine counts accepted probe hits (search.cpp:688, the
per-guide sum over the guide and its reverse complement) while ``hits`` is the
same set after cross-strand deduplication (search.cpp:1045-1047), so the two
numbers can differ only through deduplication.  This script plants a known
ground truth into a small synthetic genome instead:

* one exact target per guide (positive control, plus and minus strand);
* placements whose only deviation is a 1 nt or 2 nt bulge, i.e. one or two gaps
  in the guide-to-target alignment, so that recall can be checked against the
  ``--max-bulge`` budget;
* placements whose only deviation is one or two substitutions, so that recall
  can be checked against the ``--max-mismatch`` budget.

Each configuration is recorded with its own ``candidates`` and ``hits`` count
plus the per-plant recall, so a recorded cell can be read as "in-budget
placement recalled / over-budget placement rejected".  The Python transcription
of the seed-plan cost model is imported from ``tools/seed_plan_sweep.py`` so
that both scripts share one transcription of ``seed_plan.cpp``.

Usage
-----
    python tools/bulge_fixture_sweep.py \
        --engine-exe native/bin/offtarget-engine.exe \
        --out-dir example/engine_benchmark_bulge \
        --json docs/bulge_fixture_sweep.json

The fixture is regenerated deterministically on every run (fixed RNG seed), so
the FASTA bytes are a function of the parameters alone.  Over-budget
placements are reported as not recalled; the script never edits the fixture to
make a configuration agree with its expectation.
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import seed_plan_sweep as sps  # noqa: E402  (shared cost-model transcription)

HIT_TAG = '"type":"hit"'
BASES = "ACGT"
COMPLEMENT = {"A": "T", "C": "G", "G": "C", "T": "A"}

DEFAULT_FIXTURE_SEED = 20260922
DEFAULT_CONTIGS = 4
DEFAULT_CONTIG_BASES = 12000
DEFAULT_GUIDE_LEN = 20
MUTATION_SITE = 10

# guide index, plant kind, strand, contig index, position inside the contig
PLANT_LAYOUT = (
    (0, "exact", "+", 0, 2000),
    (1, "exact", "-", 1, 2000),
    (2, "insertion1", "+", 2, 2000),
    (3, "insertion2", "+", 3, 2000),
    (4, "deletion1", "-", 0, 6000),
    (5, "deletion2", "-", 1, 6000),
    (6, "substitution1", "+", 2, 6000),
    (7, "substitution2", "-", 3, 6000),
)

PLANTED_LAYOUT_TEXT = (
    "one exact target per guide on both strands, one 1 nt insertion, one 2 nt "
    "insertion, one 1 nt deletion, one 2 nt deletion, one single substitution "
    "and one double substitution, all at a fixed site of a random background"
)


# --- fixture construction --------------------------------------------------


def reverse_complement(sequence: str) -> str:
    return "".join(COMPLEMENT[base] for base in reversed(sequence))


def other_base(reference: str, avoid: str = "") -> str:
    for base in BASES:
        if base != reference and base not in avoid:
            return base
    raise AssertionError("no alternative base available")


def build_target(guide: str, kind: str) -> tuple[str, int, int]:
    """Return (target, expected mismatches, expected bulges) for one plant."""
    site = MUTATION_SITE
    if kind == "exact":
        return guide, 0, 0
    if kind == "substitution1":
        target = guide[:site] + other_base(guide[site]) + guide[site + 1:]
        return target, 1, 0
    if kind == "substitution2":
        letters = list(guide)
        letters[site - 2] = other_base(letters[site - 2])
        letters[site + 4] = other_base(letters[site + 4])
        return "".join(letters), 2, 0
    if kind == "insertion1":
        inserted = other_base(guide[site])
        return guide[:site] + inserted + guide[site:], 0, 1
    if kind == "insertion2":
        first = other_base(guide[site])
        second = other_base(guide[site + 1], first)
        return guide[:site] + first + second + guide[site:], 0, 2
    if kind == "deletion1":
        return guide[:site] + guide[site + 1:], 0, 1
    if kind == "deletion2":
        return guide[:site] + guide[site + 2:], 0, 2
    raise AssertionError("unknown plant kind %s" % kind)


def build_fixture(seed: int, contigs: int, contig_bases: int,
                  guide_len: int) -> dict:
    """Deterministically build the genome, the guides and the ground truth."""
    rng = random.Random(seed)
    sequences = ["".join(rng.choice(BASES) for _ in range(contig_bases))
                 for _ in range(contigs)]
    guides = ["".join(rng.choice(BASES) for _ in range(guide_len))
              for _ in PLANT_LAYOUT]

    plants = []
    for index, (guide_index, kind, strand, contig_index, offset) in enumerate(
            PLANT_LAYOUT):
        guide = guides[guide_index]
        target, mismatches, bulges = build_target(guide, kind)
        planted = target if strand == "+" else reverse_complement(target)
        sequence = sequences[contig_index]
        assert offset + len(planted) <= len(sequence), "plant runs off contig"
        sequences[contig_index] = (sequence[:offset] + planted
                                   + sequence[offset + len(planted):])
        plants.append({
            "qid": "g%02d" % (guide_index + 1),
            "guide": guide,
            "type": kind,
            "strand": strand,
            "contig": "chr%d" % (contig_index + 1),
            "start": offset,
            "end": offset + len(planted),
            "target": target,
            "planted_sequence": planted,
            "expected_mismatches": mismatches,
            "expected_bulges": bulges,
            "min_mismatch_budget": mismatches,
            "min_bulge_budget": bulges,
            "plant_index": index,
        })

    return {
        "genome_bases": sum(len(sequence) for sequence in sequences),
        "contigs": contigs,
        "contig_bases": contig_bases,
        "guide_length": guide_len,
        "guides_count": len(PLANT_LAYOUT),
        "rng_seed": seed,
        "mutation_site": MUTATION_SITE,
        "planted_layout": PLANTED_LAYOUT_TEXT,
        "plants": plants,
        "sequences": sequences,
    }


def write_fixture(out_dir: Path, fixture: dict, width: int = 60) -> dict:
    genome = out_dir / "synthetic_genome.fa"
    guides = out_dir / "guides.tsv"
    header = ">chr%d"
    lines = []
    for index, sequence in enumerate(fixture["sequences"]):
        lines.append(header % (index + 1))
        for start in range(0, len(sequence), width):
            lines.append(sequence[start:start + width])
    genome.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))

    guide_lines = ["qid\tguide_seq"]
    seen = set()
    for plant in fixture["plants"]:
        if plant["qid"] in seen:
            continue
        seen.add(plant["qid"])
        guide_lines.append("%s\t%s" % (plant["qid"], plant["guide"]))
    guides.write_bytes(("\n".join(guide_lines) + "\n").encode("utf-8"))

    document = {
        "genome": str(genome).replace("\\", "/"),
        "guides": str(guides).replace("\\", "/"),
        "genome_bases": fixture["genome_bases"],
        "contigs": fixture["contigs"],
        "contig_bases": fixture["contig_bases"],
        "guides_count": fixture["guides_count"],
        "guide_length": fixture["guide_length"],
        "rng_seed": fixture["rng_seed"],
        "mutation_site": fixture["mutation_site"],
        "planted_layout": fixture["planted_layout"],
        "plants": [{key: value for key, value in plant.items()}
                   for plant in fixture["plants"]],
    }
    (out_dir / "fixture.json").write_bytes(
        (json.dumps(document, ensure_ascii=False, indent=2) + "\n")
        .encode("utf-8"))
    return document


# --- engine drivers (same CLI contract as tools/seed_plan_sweep.py) --------


def run_engine(command: list[str]) -> str:
    process = subprocess.run(command, capture_output=True)
    stdout = process.stdout.decode("utf-8", "replace")
    stderr = process.stderr.decode("utf-8", "replace")
    if process.returncode != 0:
        raise SystemExit("engine failed (exit %d): %s\n--- stdout ---\n%s"
                         "--- stderr ---\n%s"
                         % (process.returncode, " ".join(command), stdout,
                            stderr))
    return stdout


def parse_json_object(text: str) -> dict:
    start = text.find("{")
    if start < 0:
        raise SystemExit("no JSON object in engine output:\n%s" % text)
    return json.loads(text[start:])


def build_index(exe: str, genome: Path, prefix: Path, k: int,
                threads: int) -> dict:
    stdout = run_engine([exe, "build-index", "--genome", str(genome),
                         "--prefix", str(prefix), "--k", str(k),
                         "--threads", str(threads), "--force"])
    return parse_json_object(stdout)


def search_index(exe: str, genome: Path, prefix: Path, guides: Path,
                 output: Path, max_mismatch: int, max_bulge: int, seed_len: int,
                 threads: int) -> dict:
    command = [exe, "search", "--genome", str(genome), "--index", str(prefix),
               "--guides", str(guides), "--output", str(output),
               "--max-mismatch", str(max_mismatch), "--max-bulge",
               str(max_bulge), "--seed-len", str(seed_len), "--threads",
               str(threads), "--progress-every", "0"]
    run_engine(command)
    summary = None
    hits = []
    for line in output.read_text(encoding="utf-8").splitlines():
        if HIT_TAG in line:
            hits.append(json.loads(line))
        elif '"type":"summary"' in line:
            summary = json.loads(line)
    if summary is None:
        raise SystemExit("no summary line in %s" % output)
    summary["hit_records"] = hits
    summary["command"] = " ".join(command)
    return summary


def count_guides(guides: Path) -> tuple[int, int]:
    rows = guides.read_text(encoding="utf-8").splitlines()
    sequences = [row.split("\t")[1].strip() for row in rows[1:] if "\t" in row]
    sequences = [sequence for sequence in sequences if sequence]
    return len(sequences), max(len(sequence) for sequence in sequences)


# --- per-configuration evaluation -----------------------------------------


def seed_plan_note(guide_len: int, k: int, max_mismatch: int,
                   max_bulge: int) -> dict:
    plan = sps.build_seed_plan(guide_len, max_mismatch, max_bulge, k, k)
    seed_count = len(plan["segments"])
    allowed = (plan["segments"][0]["allowed_mismatches"] if seed_count else 0)
    return {
        "guaranteed": plan["guaranteed"],
        "seed_count": seed_count,
        "allowed_mismatches_per_seed": allowed,
        "segments": sps.render_plan(plan),
        "estimated_variants": plan["estimated_variants"],
        "reason": plan.get("reason", ""),
        "max_seed_count": max(0, guide_len // k),
    }


def expected_recall(plant: dict, max_mismatch: int, max_bulge: int) -> bool:
    return (max_mismatch >= plant["min_mismatch_budget"]
            and max_bulge >= plant["min_bulge_budget"])


def evaluate_plants(plants: list[dict], hits: list[dict], max_mismatch: int,
                    max_bulge: int) -> list[dict]:
    by_qid: dict[str, list[dict]] = {}
    for hit in hits:
        by_qid.setdefault(hit["qid"], []).append(hit)
    rows = []
    for plant in plants:
        candidates = by_qid.get(plant["qid"], [])
        located = [hit for hit in candidates
                   if hit["target"] == plant["contig"]
                   and int(hit["start"]) == plant["start"]
                   and int(hit["target_end"]) == plant["end"]]
        best = None
        for hit in located:
            key = (int(hit["mismatch"]), int(hit["indel"]))
            if best is None or key < best[0]:
                best = (key, hit)
        overlapping = [hit for hit in candidates
                       if hit["target"] == plant["contig"]
                       and int(hit["start"]) < plant["end"]
                       and int(hit["target_end"]) > plant["start"]]
        alternatives = [hit for hit in overlapping if hit not in located]
        elsewhere = [hit for hit in candidates if hit not in overlapping]
        rows.append({
            "qid": plant["qid"],
            "type": plant["type"],
            "strand": plant["strand"],
            "contig": plant["contig"],
            "start": plant["start"],
            "end": plant["end"],
            "expected_mismatches": plant["expected_mismatches"],
            "expected_bulges": plant["expected_bulges"],
            "expected_recalled": expected_recall(plant, max_mismatch,
                                                max_bulge),
            "observed_recalled": bool(located),
            "observed_any_hit": bool(candidates),
            "hits_at_locus": len(located),
            "alternative_spans_at_locus": [
                "%d-%d %s" % (int(hit["start"]), int(hit["target_end"]),
                              hit["cigar"]) for hit in alternatives],
            "hits_elsewhere": [{
                "target": hit["target"],
                "start": int(hit["start"]),
                "end": int(hit["target_end"]),
                "mismatch": int(hit["mismatch"]),
                "indel": int(hit["indel"]),
                "cigar": hit["cigar"],
            } for hit in elsewhere],
            "observed": None if best is None else {
                "mismatch": int(best[1]["mismatch"]),
                "indel": int(best[1]["indel"]),
                "rna_bulges": int(best[1]["rna_bulges"]),
                "dna_bulges": int(best[1]["dna_bulges"]),
                "cigar": best[1]["cigar"],
                "target": best[1]["target"],
                "start": int(best[1]["start"]),
                "end": int(best[1]["target_end"]),
            },
        })
    return rows


def run_sweep(args) -> int:
    exe = str(Path(args.engine_exe).resolve())
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    fixture = build_fixture(args.fixture_seed, args.contigs,
                           args.contig_bases, args.guide_len)
    document_fixture = write_fixture(out_dir, fixture)
    genome = (out_dir / "synthetic_genome.fa").resolve()
    guides = (out_dir / "guides.tsv").resolve()
    guide_count, guide_len = count_guides(guides)
    plants = fixture["plants"]

    version = run_engine([exe, "--version"]).strip()
    capabilities = parse_json_object(run_engine([exe, "capabilities",
                                                 "--json"]))

    records = []
    builds = []
    departures = []
    for k in args.ks:
        prefix = out_dir / ("index_k%d" % k)
        started = time.perf_counter()
        build = build_index(exe, genome, prefix, k, args.threads)
        builds.append({
            "k": k,
            "threads": args.threads,
            "wall_time_s": round(time.perf_counter() - started, 4),
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
                    output = out_dir / ("hits_k%d_m%d_b%d_r%d.jsonl"
                                        % (k, max_mismatch, max_bulge, repeat))
                    summary = search_index(exe, genome, prefix, guides, output,
                                           max_mismatch, max_bulge, k,
                                           args.threads)
                    times.append(summary["search_time_s"])
                    summaries.append(summary)
                first = summaries[0]
                plan = seed_plan_note(guide_len, k, max_mismatch, max_bulge)
                plants_table = evaluate_plants(plants,
                                               first["hit_records"],
                                               max_mismatch, max_bulge)
                consistent = (
                    [(item["hits"], item["candidates"],
                      item["seed_plan_guaranteed"],
                      item["exhaustive_seed_plan"]) for item in summaries]
                    == [(first["hits"], first["candidates"],
                         first["seed_plan_guaranteed"],
                         first["exhaustive_seed_plan"])])
                record = {
                    "k": k,
                    "M": max_mismatch,
                    "B": max_bulge,
                    "threads": args.threads,
                    "repeats": args.repeats,
                    "seed_len": k,
                    "median_search_time_s": round(statistics.median(times), 4),
                    "search_time_s_all": [round(value, 4)
                                          for value in times],
                    "candidates": first["candidates"],
                    "hits": first["hits"],
                    "guides": first["guides"],
                    "seed_plan_guaranteed": first["seed_plan_guaranteed"],
                    "exhaustive_seed_plan": first["exhaustive_seed_plan"],
                    "memory_peak_mb": first["memory_peak_mb"],
                    "repeats_consistent": consistent,
                    "py_seed_plan": plan,
                    "plants": plants_table,
                    "plants_expected_recalled": sum(
                        1 for row in plants_table if row["expected_recalled"]),
                    "plants_observed_recalled": sum(
                        1 for row in plants_table if row["observed_recalled"]),
                    "hits_at_planted_loci": sum(
                        row["hits_at_locus"] for row in plants_table),
                    "hits_elsewhere": sum(
                        len(row["hits_elsewhere"]) for row in plants_table),
                    "departures": [
                        "%s %s expected_recalled=%s observed_recalled=%s "
                        "hits_at_locus=%d observed=%s"
                        % (row["qid"], row["type"], row["expected_recalled"],
                           row["observed_recalled"], row["hits_at_locus"],
                           row["observed"])
                        for row in plants_table
                        if row["expected_recalled"] != row["observed_recalled"]
                        or (row["observed_recalled"]
                            and row["observed"] is not None
                            and (row["observed"]["mismatch"]
                                 != row["expected_mismatches"]
                                 or row["observed"]["indel"]
                                 != row["expected_bulges"]))],
                    "command": first["command"],
                    "hit_jsonl": str(output).replace("\\", "/"),
                }
                departures.extend("%s M=%d B=%d: %s" % (k, max_mismatch,
                                                        max_bulge, item)
                                  for item in record["departures"])
                records.append(record)
                print("k=%d M=%d B=%d candidates=%d hits=%d plants=%d/%d "
                      "guaranteed=%s exhaustive=%s"
                      % (k, max_mismatch, max_bulge, record["candidates"],
                         record["hits"], record["plants_observed_recalled"],
                         record["plants_expected_recalled"],
                         str(record["seed_plan_guaranteed"]).lower(),
                         str(record["exhaustive_seed_plan"]).lower()),
                      flush=True)

    document = {
        "task": "bulge-fixture-sweep",
        "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "engine": {"path": exe, "version": version,
                   "capabilities": capabilities},
        "fixture": document_fixture,
        "protocol": {
            "grid": {"max_mismatch": list(args.mismatches),
                     "max_bulge": list(args.bulges), "k": list(args.ks)},
            "repeats": args.repeats,
            "threads": args.threads,
            "build_policy": "one index per k, reused for every M/B pair",
            "seed_len_policy": ("--seed-len is set to the index k; "
                                "seed_plan.cpp:126 ignores it"),
            "expected_recall_rule": ("a placement is expected to be recalled "
                                     "when M >= its substitution count and "
                                     "B >= its gap count"),
            "candidates_note": ("the indexed engine counts accepted probe hits "
                                "per guide and strand (search.cpp:688) and "
                                "deduplicates afterwards (search.cpp:1045), so "
                                "candidates >= hits and equality does not by "
                                "itself show that acceptance never rejects"),
        },
        "index_builds": builds,
        "records": records,
        "departures": departures,
    }
    json_path = Path(args.json)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_bytes((json.dumps(document, ensure_ascii=False, indent=2)
                           + "\n").encode("utf-8"))

    print("")
    header = ("k   M  B  seeds  allowed  candidates  hits  guaranteed  "
              "exhaustive  median_s  plants")
    print(header)
    print("-" * len(header))
    for record in records:
        print("%-3d %-2d %-2d %-6d %-8d %-11d %-5d %-11s %-11s %-9.4f %d/%d"
              % (record["k"], record["M"], record["B"],
                 record["py_seed_plan"]["seed_count"],
                 record["py_seed_plan"]["allowed_mismatches_per_seed"],
                 record["candidates"], record["hits"],
                 str(record["seed_plan_guaranteed"]).lower(),
                 str(record["exhaustive_seed_plan"]).lower(),
                 record["median_search_time_s"],
                 record["plants_observed_recalled"],
                 record["plants_expected_recalled"]))

    print("")
    print("per-plant recall (expected / observed; type in the header)")
    qids = [plant["qid"] for plant in plants]
    kinds = {plant["qid"]: plant["type"] for plant in plants}
    print("%-3s %-2s %-2s  %s" % ("k", "M", "B",
                                  "  ".join("%s" % qid for qid in qids)))
    print("%-3s %-2s %-2s  %s" % ("", "", "",
                                  "  ".join("%-6s" % kinds[qid][:6]
                                            for qid in qids)))
    for record in records:
        rows = {row["qid"]: row for row in record["plants"]}
        expected = "  ".join("%-6s" % ("Y" if rows[qid]["expected_recalled"]
                                       else "-") for qid in qids)
        observed = "  ".join("%-6s" % ("Y" if rows[qid]["observed_recalled"]
                                       else "-") for qid in qids)
        print("%-3d %-2d %-2d  %s" % (record["k"], record["M"], record["B"],
                                      expected))
        print("%-3s %-2s %-2s  %s" % ("", "", "", observed))

    print("")
    if departures:
        print("DEPARTURES from the expected in-budget recall:")
        for item in departures:
            print("  " + item)
    else:
        print("no departures from the expected in-budget recall")
    print("wrote %s (%d records)" % (json_path, len(records)))
    return 1 if departures else 0


def parse_csv(value: str, cast):
    return [cast(item) for item in value.replace(" ", "").split(",") if item]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--engine-exe",
                        default="native/bin/offtarget-engine.exe",
                        help="path to the native engine executable")
    parser.add_argument("--out-dir", default="example/engine_benchmark_bulge",
                        help="fixture and run outputs")
    parser.add_argument("--json", default="docs/bulge_fixture_sweep.json",
                        help="sweep output JSON")
    parser.add_argument("--fixture-seed", type=int,
                        default=DEFAULT_FIXTURE_SEED)
    parser.add_argument("--contigs", type=int, default=DEFAULT_CONTIGS)
    parser.add_argument("--contig-bases", type=int,
                        default=DEFAULT_CONTIG_BASES)
    parser.add_argument("--guide-len", type=int, default=DEFAULT_GUIDE_LEN)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--mismatches", default="0,1,2")
    parser.add_argument("--bulges", default="0,1,2",
                        help="B=2 drops the seed plan below the minimum seed count "
                             "for a 20 nt guide and exercises the whole-genome "
                             "fallback path instead")
    parser.add_argument("--ks", default="8,10")
    args = parser.parse_args(argv)
    args.mismatches = parse_csv(args.mismatches, int)
    args.bulges = parse_csv(args.bulges, int)
    args.ks = parse_csv(args.ks, int)
    if args.repeats < 1:
        raise SystemExit("--repeats must be >= 1")
    return run_sweep(args)


if __name__ == "__main__":
    sys.exit(main())