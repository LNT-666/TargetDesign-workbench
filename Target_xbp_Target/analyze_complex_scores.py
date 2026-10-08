#!/usr/bin/env python3

# -*- coding: utf-8 -*-



import sys

import os

import argparse

import subprocess

import tempfile

import csv

from collections import defaultdict

from Bio import SeqIO

from Bio.Seq import Seq

from Bio.SeqRecord import SeqRecord



sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "shared"))

from search.blast_utils import check_blast_installed, ensure_blastdb, load_genome_and_prepare_fasta, fetch_sequence, reverse_complement, orient_off_target_pair, max_inverted_repeat_len, build_exclusion_intervals, is_in_excluded
from search.hit_utils import (
    as_hit_dict, has_alignment, hit_mismatch, hit_start, hit_strand,
    hit_target, orient_rich_hit,
)
from search.blast_utils import run_blastn as shared_run_blastn
from search.offtarget_backend import (
    SearchParams, apply_engine_defaults, print_search_progress,
    run_backend,
)
from design.library_preflight import MAX_EXACT_GENOME_BYTES
from scoring.scoring import (
    compute_guide_scores, apply_guide_feature_columns, rank_rows,
    filter_hints, passes_filter, OUTPUT_GUIDE_FEATURE_COLUMNS,
    compute_off_target_activities,
    specificity_from_off_target_activities,
)
from scoring.pair_ranking import (
    PREDICTION_ONLY_OUTPUT_FIELDS, rank_prediction_only,
)
from scoring.pair_ranking_adapter import (
    apply_pair_rank_outputs, build_pair_compatibility, build_pair_input,
    load_pair_rank_policy_file, pair_id_for_row,
)
from scoring.at_score import (
    compute_at_score_from_flank, should_output_at_score,
)
from design.system_presets import get_preset, resolve_run_nuclease
from data.candidate_annotation import (
    build_annotation_index, annotate_interval, nearest_tss,
    find_downstream_atg, format_annotation, format_tss,
)
from output.output_columns import (
    mismatch_bucket_columns,
    mismatch_bucket_values,
    nonempty_indices,
)
from output.xlsx_utils import tsv_to_xlsx





# ---------- 复合 motif 分析：Off-target search 与评分 ----------

def find_all_positions(seq, pattern):

    positions = []

    start = 0

    while True:

        pos = seq.find(pattern, start)

        if pos == -1:

            break

        positions.append(pos)

        start = pos + 1

    return positions




def run_blastn(query_fasta, db_name, genome=None, max_mismatch=None,
               require_pam=False, pam_motif="GG", seed_mismatch_max=None,
               seed_len=12, repeat_intervals=None, pam_side="3prime",
               max_bulge=0):
    return {
        qid: [(m["target"], m["start"], m["mismatch"]) for m in match_list]
        for qid, match_list in shared_run_blastn(
            query_fasta, db_name, task="blastn-short", word_size=4, evalue=1000,
            max_mismatch=max_mismatch, max_bulge=max_bulge,
            require_pam=require_pam,
            pam_motif=pam_motif, seed_mismatch_max=seed_mismatch_max,
            seed_len=seed_len, genome=genome, repeat_intervals=repeat_intervals,
            pam_side=pam_side
        ).items()
    }


def match_mismatch(match):
    """Return the mismatch count from a compact match record."""
    return hit_mismatch(match)


def hits_from_engine(results, engine_name):
    """Return True when ``results`` is non-empty and every hit came from it.

    The requested engine can differ from the engine that actually ran: ``auto``
    resolves to a runtime chain, and a fallback can switch engines mid-run.
    Every hit records the engine that produced it, so post-processing follows
    the engine that really ran instead of the requested name.
    """
    engines = {
        str(as_hit_dict(hit).get("engine") or "").lower()
        for hits in results.values()
        for hit in hits
    }
    return engines == {(engine_name or "").lower()}


def first_model_choice(value, default="rules"):
    """Return the primary model from a CLI comma-separated model list."""
    for item in str(value or "").replace(";", ",").split(","):
        item = item.strip().lower()
        if item:
            return item
    return default



# ---------- 主流程 ----------

def main():
    parser = argparse.ArgumentParser(description="Compound motif Off-target search and scoring")
    parser.add_argument("tsv_file", help="query TSV from extract_complex_queries.py")
    parser.add_argument("mask_fasta", help="Mask gene FASTA (use empty string to skip)")
    parser.add_argument("genome_file", help="Genome FASTA/GenBank")
    parser.add_argument("output_dir", help="Output directory")
    parser.add_argument("--blastdb", default=None, help="Existing Genome database prefix")
    parser.add_argument("--engine", default="blast",
                        choices=["exact", "indexed", "blast", "gggenome",
                                 "auto"])
    parser.add_argument("--index-path", default="",
                        help="Local genome index prefix (.ggi/.json)")
    parser.add_argument("--genome-build", default="",
                        help="Genome build name for GGGenome, e.g. hg38")
    parser.add_argument("--nuclease", choices=["custom", "cas9", "cas12", "cas12a", "cas12b",
                                               "cas13", "cas14a", "tnpb"], default="cas9")
    parser.add_argument("--tnpb-subtype", choices=["isdra2", "other", "unknown"], default="unknown")
    parser.add_argument("--left-nuclease", choices=["custom", "cas9", "cas12", "cas12a", "cas12b",
                                                    "cas13", "cas14a", "tnpb"], default=None,
                        help="Nuclease for the left flank (defaults to --nuclease)")
    parser.add_argument("--right-nuclease", choices=["custom", "cas9", "cas12", "cas12a", "cas12b",
                                                     "cas13", "cas14a", "tnpb"], default=None,
                        help="Nuclease for the right flank (defaults to --nuclease)")
    parser.add_argument("--left-tnpb-subtype", choices=["isdra2", "other", "unknown"], default=None)
    parser.add_argument("--right-tnpb-subtype", choices=["isdra2", "other", "unknown"], default=None)
    parser.add_argument("--left-preset", default=None)
    parser.add_argument("--right-preset", default=None)
    parser.add_argument("--reference-only-model", choices=["none", "cas9", "teep"], default="none")
    parser.add_argument("--left-reference-only-model", choices=["none", "cas9", "teep"], default=None)
    parser.add_argument("--right-reference-only-model", choices=["none", "cas9", "teep"], default=None)
    parser.add_argument("--on-target-model", default="cropsr",
                        help="On-target model(s), comma-separated for multiple selections")
    parser.add_argument("--off-target-model", default="rules",
                        help="Off-target model(s), comma-separated for multiple selections")
    parser.add_argument("--left-off-target-model", default=None,
                        help="Off-target model(s) for the left flank, comma-separated")
    parser.add_argument("--right-off-target-model", default=None,
                        help="Off-target model(s) for the right flank, comma-separated")
    parser.add_argument("--left-on-target-model", default=None,
                        help="On-target model(s) for the left flank, comma-separated")
    parser.add_argument("--right-on-target-model", default=None,
                        help="On-target model(s) for the right flank, comma-separated")
    parser.add_argument("--max-mismatch", type=int, choices=[0, 1, 2, 3, 4], default=4)
    parser.add_argument("--max-bulge", type=int, choices=[0, 1], default=None)
    parser.add_argument("--require-pam", action="store_true")
    parser.add_argument("--pam-motif", default=None)
    parser.add_argument("--left-require-pam", action="store_true", default=None)
    parser.add_argument("--right-require-pam", action="store_true", default=None)
    parser.add_argument("--left-pam-motif", default=None)
    parser.add_argument("--right-pam-motif", default=None)
    parser.add_argument("--left-pam-side", choices=["3prime", "5prime"], default=None)
    parser.add_argument("--right-pam-side", choices=["3prime", "5prime"], default=None)
    parser.add_argument("--seed-mismatch-max", type=int, default=None)
    parser.add_argument("--seed-len", type=int, default=12)
    parser.add_argument("--max-memory-mb", type=int, default=None,
                        help="Explicit process RSS limit in MiB")
    parser.add_argument("--timeout-s", type=float, default=None,
                        help="Wall-clock budget for one indexed search, in "
                             "seconds; default is no timeout")
    parser.add_argument("--repeat-fasta", default=None, help="Repeat sequence FASTA to mask")
    parser.add_argument("--gc-min", type=float, default=40.0)
    parser.add_argument("--gc-max", type=float, default=70.0)
    parser.add_argument("--self-comp-max", type=int, default=4)
    parser.add_argument("--filter-hard", action="store_true")
    parser.add_argument("--crispai", action="store_true",
                        help="Backfill crispAI specificity for Cas9 flanks")
    parser.add_argument("--crispai-samples", type=int, default=200)
    parser.add_argument("--crispai-gpu", type=int, default=-1)
    parser.add_argument("--unique-guides", action="store_true")
    parser.add_argument("--top-offtargets", type=int, default=5,
                        help="Write the top N off-targets per unique query to top_offtargets.tsv")
    parser.add_argument("--annotation", default=None,
                        help="NCBI GFF3 annotation file used to annotate candidates")
    parser.add_argument("--xlsx", action="store_true",
                        help="Also write XLSX versions of the main TSV outputs")
    parser.add_argument("--pair-rank-policy", required=True,
                        help="JSON file containing pair_rank_policy")
    parser.add_argument("--min-gap", type=int, default=None,
                        help="Expected minimum motif gap for compatibility checks")
    parser.add_argument("--max-gap", type=int, default=None,
                        help="Expected maximum motif gap for compatibility checks")
    parser.add_argument("--left-side", choices=["upstream", "downstream"],
                        default=None)
    parser.add_argument("--right-side", choices=["upstream", "downstream"],
                        default=None)
    parser.add_argument("--mode", choices=["free", "preset"], default="free")
    parser.add_argument("--preset", default="custom")
    parser.add_argument("--spacer-len", type=int, default=None)
    parser.add_argument("--seed-start", type=int, default=None)
    parser.add_argument("--seed-end", type=int, default=None)
    parser.add_argument("--target-type", choices=["dna", "rna", "ssdna"], default="dna")
    parser.add_argument("--exact-offtarget", action="store_true",
                        help="Use the local exact k-mer search instead of BLAST")
    parser.add_argument("--pam-side", choices=["3prime", "5prime"], default=None)
    parser.add_argument("--seed-mismatch", type=int, default=None)
    args = parser.parse_args()
    pair_rank_policy = load_pair_rank_policy_file(args.pair_rank_policy)

    preset = get_preset(args.preset if args.mode == "preset" else "custom")
    if args.pam_motif is None:
        args.pam_motif = preset.get("pam") or ""
    if args.pam_side is None:
        args.pam_side = preset.get("pam_side") or ""
    if args.mode == "preset" and preset.get("pam_required") and args.pam_motif:
        args.require_pam = True

    tsv_file = args.tsv_file
    mask_fasta = args.mask_fasta
    genome_file = args.genome_file
    output_dir = args.output_dir
    # ``--mode preset --preset tnpb`` (etc.) without ``--nuclease`` must not
    # keep the cas9 default in the reported ``nuclease`` column.
    nuclease = resolve_run_nuclease(
        args.nuclease, args.preset if args.mode == "preset" else "custom")
    tnpb_subtype = args.tnpb_subtype
    left_nuclease = args.left_nuclease or nuclease
    right_nuclease = args.right_nuclease or nuclease
    left_tnpb = args.left_tnpb_subtype or tnpb_subtype
    right_tnpb = args.right_tnpb_subtype or tnpb_subtype
    left_at_score_enabled = should_output_at_score(
        args.mode, args.preset, args.left_preset)
    right_at_score_enabled = should_output_at_score(
        args.mode, args.preset, args.right_preset)
    left_otm = args.left_off_target_model or args.off_target_model
    right_otm = args.right_off_target_model or args.off_target_model
    left_on_otm = args.left_on_target_model or args.on_target_model
    right_on_otm = args.right_on_target_model or args.on_target_model
    reference_only_model = args.reference_only_model
    left_ref = args.left_reference_only_model or reference_only_model
    right_ref = args.right_reference_only_model or reference_only_model
    on_target_model = args.on_target_model
    left_pam_motif = args.left_pam_motif if args.left_pam_motif is not None else args.pam_motif
    right_pam_motif = args.right_pam_motif if args.right_pam_motif is not None else args.pam_motif
    left_pam_side = args.left_pam_side if args.left_pam_side is not None else args.pam_side
    right_pam_side = args.right_pam_side if args.right_pam_side is not None else args.pam_side
    left_require = args.left_require_pam if args.left_require_pam is not None else args.require_pam
    right_require = args.right_require_pam if args.right_require_pam is not None else args.require_pam

    os.makedirs(output_dir, exist_ok=True)



    # ---- 读取查询 TSV ----

    rows = []

    with open(tsv_file, 'r') as f:

        header = f.readline().strip().split('\t')

        for line in f:

            fields = line.strip().split('\t')

            if len(fields) != len(header):

                continue

            row = dict(zip(header, fields))

            # 将 TSV 中的数字字段转换为整数

            numeric_keys = ["left_pos", "right_pos", "gap", "compound_start", "compound_end",

                            "left_len", "right_len",
                            "left_target_start", "left_target_end",
                            "right_target_start", "right_target_end"]

            for key in numeric_keys:

                if key in row:

                    row[key] = int(row[key])

            row.setdefault("left_strand", row.get("strand", "plus"))

            row.setdefault("right_strand", row.get("strand", "plus"))

            for side_key, strand_key, pos_key, motif_key, start_key, end_key, flank_key in (
                ("left_side", "left_strand", "left_pos", "left_motif_seq",
                 "left_target_start", "left_target_end", "left_flank_seq"),
                ("right_side", "right_strand", "right_pos", "right_motif_seq",
                 "right_target_start", "right_target_end", "right_flank_seq"),
            ):
                if start_key in row and end_key in row:
                    continue
                flank_seq = row.get(flank_key, "")
                side = row.get(side_key, "upstream")
                strand = row[strand_key]
                if (side == "upstream") == (strand == "plus"):
                    target_start = row[pos_key] - len(flank_seq)
                else:
                    target_start = row[pos_key] + len(row.get(motif_key, ""))
                row[start_key] = target_start
                row[end_key] = target_start + len(flank_seq)

            rows.append(row)



    if not rows:

        print("No data found in TSV.")

        sys.exit(0)

    for idx, row in enumerate(rows):
        row.setdefault("qid", "pair_%d" % idx)
        row.setdefault("left_flank_seq", "")
        row.setdefault("right_flank_seq", "")



    # ---- 把左右 flank 分别作为独立 guide ----

    flank_qid_to_seq = {}
    flank_qid_by_seq = {"left": {}, "right": {}}

    for row in rows:
        for side, seq_key in (
            ("left", "left_flank_seq"),
            ("right", "right_flank_seq"),
        ):
            seq = row.get(seq_key, "")
            if not seq:
                row[f"{side}_flank_qid"] = ""
                continue
            flank_qid = flank_qid_by_seq[side].get(seq)
            if flank_qid is None:
                flank_qid = "%s_flank_%d" % (side, len(flank_qid_to_seq))
                flank_qid_by_seq[side][seq] = flank_qid
                flank_qid_to_seq[flank_qid] = seq
            row[f"{side}_flank_qid"] = flank_qid

    qid_to_seq = flank_qid_to_seq



    print(f"Loaded {len(rows)} compound positions, "
          f"{len(qid_to_seq)} unique flank sequences.")

    print("PROGRESS: reading 5", flush=True)



    # ---- 加载 Genome、屏蔽区间并准备 Genome database ----

    genome_records, genome_fasta_for_blast, temp_genome = load_genome_and_prepare_fasta(genome_file)
    print(f"Loaded {len(genome_records.keys())} chromosomes/scaffolds from indexed FASTA")

    annotation_index = None
    if args.annotation and os.path.isfile(args.annotation):
        annotation_index = build_annotation_index(args.annotation)
        print(f"Loaded annotation: {annotation_index.gene_count} genes, "
              f"{annotation_index.transcript_count} transcripts")

    exclusion_intervals = {}
    if mask_fasta and os.path.isfile(mask_fasta):
        exclusion_intervals = build_exclusion_intervals(mask_fasta, genome_records)
        print(f"Built exclusion intervals for {len(exclusion_intervals)} records.")
    else:
        print("No Mask gene FASTA provided, skipping masking.")

    repeat_intervals = {}
    if args.repeat_fasta and os.path.isfile(args.repeat_fasta):
        repeat_intervals = build_exclusion_intervals(args.repeat_fasta, genome_records)
        print(f"Repeat intervals: {sum(len(v) for v in repeat_intervals.values())}")



    # ---- 按所选 engine 运行 Off-target search ----
    engine = args.engine or ("exact" if args.exact_offtarget else "blast")
    if (engine == "exact"
            and os.path.getsize(genome_fasta_for_blast)
            > MAX_EXACT_GENOME_BYTES):
        print("Exact engine is not suitable for large genomes; falling back to blast")
        engine = "blast"

    def make_search_params(pam, pam_side, require):
        params = SearchParams(
            max_mismatch=args.max_mismatch,
            max_bulge=1 if args.max_bulge is None else args.max_bulge,
            max_bulge_explicit=args.max_bulge is not None,
            seed_len=args.seed_len,
            seed_mismatch=args.seed_mismatch,
            seed_mismatch_max=args.seed_mismatch_max,
            pam=pam if require else None,
            pam_side=pam_side,
            require_pam=require,
            blastdb=args.blastdb or None,
            index_path=args.index_path or None,
            output_dir=output_dir,
            genome_build=args.genome_build or None,
            extra={
                key: value for key, value in (
                    ("max_memory_mb", args.max_memory_mb),
                    ("timeout_s", args.timeout_s),
                )
                if value is not None
            },
        )
        apply_engine_defaults(
            engine, params, os.path.getsize(genome_fasta_for_blast))
        return params

    left_guides = [
        {"qid": qid, "guide_seq": seq}
        for qid, seq in qid_to_seq.items()
        if qid.startswith("left_")
    ]
    right_guides = [
        {"qid": qid, "guide_seq": seq}
        for qid, seq in qid_to_seq.items()
        if qid.startswith("right_")
    ]
    results = {}
    left_search_complete = False
    right_search_complete = False

    def report_line(message):
        """Forward engine notes (fallback reasons, progress) to stdout."""
        print(message, flush=True)

    print(f"PROGRESS: Off-target search ({engine}) 30", flush=True)
    try:
        if left_guides:
            left_results = run_backend(
                engine, left_guides, genome_fasta_for_blast,
                make_search_params(left_pam_motif, left_pam_side, left_require),
                genome=genome_records,
                progress_callback=print_search_progress,
                log=report_line,
            )
            results.update(left_results)
            left_search_complete = True
        if right_guides:
            right_results = run_backend(
                engine, right_guides, genome_fasta_for_blast,
                make_search_params(right_pam_motif, right_pam_side, right_require),
                genome=genome_records,
                progress_callback=print_search_progress,
                log=report_line,
            )
            results.update(right_results)
            right_search_complete = True
    except RuntimeError as exc:
        print("Off-target search failed: %s" % exc)
        sys.exit(3)

    forbidden_hits_by_qid = defaultdict(list)
    for qid, hits in results.items():
        seen_loci = set()
        for hit in hits:
            match = as_hit_dict(hit)
            rec_id = hit_target(match)
            start = hit_start(match)
            if not (
                is_in_excluded(rec_id, start, exclusion_intervals)
                or is_in_excluded(rec_id, start, repeat_intervals)
            ):
                continue
            locus = "%s:%s:%s" % (
                rec_id, start, hit_strand(match) or "+"
            )
            if locus in seen_loci:
                continue
            seen_loci.add(locus)
            forbidden_hits_by_qid[qid].append({
                "locus_id": locus,
                "target": rec_id,
                "start": start,
                "score": None,
                "upper": 1.0,
                "forbidden": True,
                "is_bulge": False,
                "bulge_calibrated": False,
            })
    if repeat_intervals:
        results = {
            qid: [
                hit for hit in hits
                if not is_in_excluded(
                    hit["target"], hit["start"], repeat_intervals
                )
            ]
            for qid, hits in results.items()
        }
    blast_matches = results
    exact_matches_by_qid = (
        results if hits_from_engine(results, "exact") else None
    )
    print("Off-target search complete: "
          "%d hits" % sum(len(v) for v in blast_matches.values()))

    if temp_genome is not None:

        os.unlink(temp_genome.name)



    # ---- 计算每个 query 的评分 ----

    def _no_flank_score():
        return (0.0, 0, 0, 0, [0] * 6, {
            "off_target_specificity": 1.0,
            "off_target_model": "no_flank",
            "on_target_score": 0.0,
            "on_target_model": "no_flank",
            "reference_only": False,
            "reference_note": "",
        }, "", [])



    score_cache = {}
    scan_cache = {}

    def compute_flank_score(flank_qid, strand, nuc, subtype, otm, onotm, ref,
                            expected_target=None):
        base_cache_key = (flank_qid, strand, nuc, subtype, otm, onotm, ref)
        cache_key = (base_cache_key, expected_target)
        if cache_key in score_cache:
            return score_cache[cache_key]

        if flank_qid not in blast_matches:
            result = (0.0, 0, 0, 0, [0] * 6, {
                "off_target_specificity": 1.0,
                "off_target_model": "no_matches",
                "on_target_score": 0.0,
                "on_target_model": "no_matches",
                "reference_only": False,
                "reference_note": "",
            }, "", [])
            score_cache[cache_key] = result
            return result

        if base_cache_key not in scan_cache:
            matches = [
                match for match in blast_matches[flank_qid]
                if match_mismatch(match) <= args.max_mismatch
            ]
            query_seq = qid_to_seq[flank_qid]
            guide_seq = (
                reverse_complement(query_seq)
                if strand == "minus" else query_seq
            )
            total = len(matches)
            valid_mms = []
            off_pairs = []
            scan_hit_records = []

            for match in matches:
                match_hit = as_hit_dict(match)
                rec_id = hit_target(match_hit)
                start = hit_start(match_hit)
                mm = hit_mismatch(match_hit)
                hit_target_strand = hit_strand(match_hit)
                locus_id = "%s:%s:%s" % (
                    rec_id, start, hit_target_strand or "+"
                )
                if is_in_excluded(rec_id, start, exclusion_intervals):
                    scan_hit_records.append({
                        "locus_id": locus_id,
                        "target": rec_id,
                        "start": start,
                        "pair_index": None,
                        "score": None,
                        "upper": 1.0,
                        "forbidden": True,
                        "is_bulge": False,
                        "bulge_calibrated": False,
                    })
                    continue

                valid_mms.append(mm)
                off_pair = None
                hit_meta = match_hit
                if has_alignment(match_hit):
                    off_pair = orient_rich_hit(match_hit, strand)
                else:
                    off = fetch_sequence(
                        genome_records, rec_id, start,
                        start + len(query_seq) + 2
                    )
                    if off and len(off) >= len(query_seq):
                        raw_off = off[:len(query_seq)]
                        raw_pam = off[len(query_seq):len(query_seq) + 2]
                        off_pair = orient_off_target_pair(
                            raw_off, raw_pam, hit_target_strand, strand
                        )
                        hit_meta = {
                            "target": rec_id,
                            "start": start,
                            "strand": hit_target_strand,
                            "mismatch": mm,
                            "indel": 0,
                        }
                if off_pair is None:
                    continue

                pair_index = len(off_pairs)
                off_pairs.append(off_pair)
                is_bulge = bool(
                    int(hit_meta.get("indel") or 0)
                    or int(hit_meta.get("rna_bulges") or 0)
                    or int(hit_meta.get("dna_bulges") or 0)
                )
                scan_hit_records.append({
                    "locus_id": locus_id,
                    "target": rec_id,
                    "start": start,
                    "pair_index": pair_index,
                    "score": None,
                    "upper": None,
                    "forbidden": False,
                    "is_bulge": is_bulge,
                    "bulge_calibrated": False,
                })

            seen_forbidden = {
                hit.get("locus_id") for hit in scan_hit_records
                if hit.get("forbidden")
            }
            for forbidden in forbidden_hits_by_qid.get(flank_qid, []):
                if forbidden.get("locus_id") in seen_forbidden:
                    continue
                item = dict(forbidden)
                item["pair_index"] = None
                scan_hit_records.append(item)
                seen_forbidden.add(item.get("locus_id"))

            primary_off_model = first_model_choice(otm)
            activity_data = compute_off_target_activities(
                guide_seq, off_pairs,
                nuclease=nuc,
                tnpb_subtype=subtype,
                reference_only_model=ref,
                preset_key=(
                    args.preset if args.mode == "preset" else "custom"
                ),
                seed_start=args.seed_start,
                seed_end=args.seed_end,
                off_target_model=primary_off_model,
            )
            for index, hit in enumerate(scan_hit_records):
                pair_index = hit.get("pair_index")
                if pair_index is None or hit.get("forbidden"):
                    continue
                activity = min(
                    1.0, max(0.0, float(
                        activity_data["activities"][pair_index])))
                if activity_data["primary"][pair_index]:
                    activity = 0.0
                hit["score"] = activity

            valid = len(valid_mms)
            sum_mismatch = sum(valid_mms)
            mm_counts = [0] * 6
            for mm in valid_mms:
                if mm <= 5:
                    mm_counts[mm] += 1

            score = 0.0
            for k in range(6):
                cnt = sum(1 for mm in valid_mms if mm <= k)
                weight = 10 ** (-k + 1)
                score += cnt * weight

            scan_cache[base_cache_key] = (
                score, total, valid, sum_mismatch, mm_counts, guide_seq,
                off_pairs, scan_hit_records, activity_data,
            )

        (score, total, valid, sum_mismatch, mm_counts, guide_seq,
         all_off_pairs, all_hit_records, all_activity_data) = \
            scan_cache[base_cache_key]

        def is_expected_hit(hit):
            if expected_target is None:
                return False
            target = hit.get("target")
            start = hit.get("start")
            if target is None or start is None:
                return False
            try:
                return (target, int(start)) == expected_target
            except (TypeError, ValueError):
                return False

        kept_hit_records = [
            hit for hit in all_hit_records if not is_expected_hit(hit)
        ]
        pair_indexes = [
            hit["pair_index"] for hit in kept_hit_records
            if hit.get("pair_index") is not None
        ]
        off_pairs = [all_off_pairs[index] for index in pair_indexes]
        activities = [
            all_activity_data["activities"][index]
            for index in pair_indexes
        ]
        primary_flags = [
            all_activity_data["primary"][index]
            for index in pair_indexes
        ]
        substitution_flags = [
            all_activity_data["substitution"][index]
            for index in pair_indexes
        ]
        row_activity_data = dict(all_activity_data)
        row_activity_data.update({
            "activities": activities,
            "primary": primary_flags,
            "substitution": substitution_flags,
            "specificity": specificity_from_off_target_activities(
                [
                    activity for activity, is_substitution in zip(
                        activities, substitution_flags
                    ) if is_substitution
                ],
                [
                    primary for primary, is_substitution in zip(
                        primary_flags, substitution_flags
                    ) if is_substitution
                ],
            ),
        })
        primary_off_model = first_model_choice(otm)
        guide_scores = compute_guide_scores(
            guide_seq, off_pairs,
            nuclease=nuc,
            tnpb_subtype=subtype,
            reference_only_model=ref,
            on_target_model=onotm,
            off_target_model=otm,
            preset_key=args.preset if args.mode == "preset" else "custom",
            seed_start=args.seed_start,
            seed_end=args.seed_end,
            target_type=args.target_type,
            precomputed_off_target_activities={
                primary_off_model: row_activity_data,
            },
        )
        off_hit_records = [
            {
                key: value
                for key, value in hit.items()
                if key != "pair_index"
            }
            for hit in kept_hit_records
        ]
        result = (score, total, valid, sum_mismatch, mm_counts,
                  guide_scores, guide_seq, off_hit_records)
        score_cache[cache_key] = result
        return result



    def score_flank(row, side):
        flank_qid = row.get(f"{side}_flank_qid")
        strand = row.get(f"{side}_strand", "plus")
        if not flank_qid:
            return _no_flank_score()
        expected_target = (
            row.get("seq_id"),
            int(row.get(f"{side}_target_start", -1)),
        )
        if side == "left":
            return compute_flank_score(flank_qid, strand, left_nuclease,
                                       left_tnpb, left_otm, left_on_otm,
                                       left_ref, expected_target)
        return compute_flank_score(flank_qid, strand, right_nuclease,
                                   right_tnpb, right_otm, right_on_otm,
                                   right_ref, expected_target)



    def sequence_stats(seq):
        if not seq:
            return 0.0, 0, filter_hints(
                0.0, 0, args.gc_min, args.gc_max, args.self_comp_max
            )
        gc = (seq.count("G") + seq.count("C")) / len(seq) * 100.0
        self_comp = max_inverted_repeat_len(seq)
        hints = filter_hints(
            gc, self_comp, args.gc_min, args.gc_max, args.self_comp_max
        )
        return gc, self_comp, hints



    # ---- 逐条按左右 flank 分别评分 ----

    scored_rows = []

    filtered_count = 0

    total_rows = len(rows)

    for row_idx, row in enumerate(rows):

        if row_idx % max(1, total_rows // 10) == 0 or row_idx == total_rows - 1:

            pct = 40 + int(row_idx / total_rows * 40)
            print(
                f"PROGRESS: Analyzing target {row_idx + 1}/{total_rows} {pct}",
                flush=True,
            )

        left_result = score_flank(row, "left")
        right_result = score_flank(row, "right")

        left_seq = row.get("left_flank_seq", "")
        right_seq = row.get("right_flank_seq", "")
        left_at_score = (
            compute_at_score_from_flank(
                left_seq, row.get("left_side", ""),
                row.get("left_strand", "plus"))
            if left_at_score_enabled else None
        )
        right_at_score = (
            compute_at_score_from_flank(
                right_seq, row.get("right_side", ""),
                row.get("right_strand", "plus"))
            if right_at_score_enabled else None
        )
        left_gc, left_ir, left_hints = sequence_stats(left_seq)
        right_gc, right_ir, right_hints = sequence_stats(right_seq)

        if args.filter_hard and (
            not passes_filter(left_hints, True)
            or not passes_filter(right_hints, True)
        ):
            filtered_count += 1
            continue

        ann = None
        tss = None
        atg_text = ""
        if annotation_index is not None:
            ann = annotate_interval(annotation_index, row['seq_id'],
                                    row['compound_start'], row['compound_end'])
            tss = nearest_tss(annotation_index, row['seq_id'],
                              row['compound_start'], row['compound_end'])
            atg = find_downstream_atg(genome_records, row['seq_id'],
                                      row['compound_start'], row['compound_end'],
                                      row['strand'], window=500)
            if atg is not None:
                if row['strand'] == 'plus':
                    atg_text = f"{atg - row['compound_end']}bp"
                else:
                    atg_text = f"{row['compound_start'] - atg}bp"

        (left_legacy, left_total, left_valid, left_mm_sum, left_mm,
         left_gs, left_guide_seq, left_off_hits) = left_result
        (right_legacy, right_total, right_valid, right_mm_sum, right_mm,
         right_gs, right_guide_seq, right_off_hits) = right_result

        item = {
            "rank": 0,
            "pair_id": (
                f"{row['seq_id']}_{row['strand']}_"
                f"L{row['left_pos']}_R{row['right_pos']}_G{row['gap']}"
            ),
            "qid": row.get("qid", ""),
            "seq_id": row["seq_id"],
            "strand": row["strand"],
            "left_strand": row["left_strand"],
            "right_strand": row["right_strand"],
            "left_pos": row["left_pos"],
            "right_pos": row["right_pos"],
            "gap": row["gap"],
            "compound_start": row["compound_start"],
            "compound_end": row["compound_end"],
            "left_target_start": row["left_target_start"],
            "left_target_end": row["left_target_end"],
            "right_target_start": row["right_target_start"],
            "right_target_end": row["right_target_end"],
            "left_motif_seq": row["left_motif_seq"],
            "right_motif_seq": row["right_motif_seq"],
            "left_flank_seq": left_seq,
            "right_flank_seq": right_seq,
            "left_guide_seq": left_guide_seq,
            "right_guide_seq": right_guide_seq,
            "left_side": row.get("left_side", ""),
            "left_len": row.get("left_len", 0),
            "right_side": row.get("right_side", ""),
            "right_len": row.get("right_len", 0),
            "left_legacy_score": left_legacy,
            "left_total_matches": left_total,
            "left_valid_matches": left_valid,
            "left_sum_mismatch": left_mm_sum,
            "left_at_score": left_at_score,
            "left_off_target_specificity": left_gs["off_target_specificity"],
            "left_off_target_model": left_gs["off_target_model"],
            "left_on_target_score": left_gs["on_target_score"],
            "left_on_target_model": left_gs["on_target_model"],
            "left_reference_only": left_gs["reference_only"],
            "left_reference_note": left_gs["reference_note"],
            "left_gc_content": left_gc,
            "left_self_complementarity": left_ir,
            "left_gc_hint": left_hints["gc_hint"],
            "left_self_comp_hint": left_hints["self_comp_hint"],
            "left_mm_counts": left_mm,
            "right_legacy_score": right_legacy,
            "right_total_matches": right_total,
            "right_valid_matches": right_valid,
            "right_sum_mismatch": right_mm_sum,
            "right_at_score": right_at_score,
            "right_off_target_specificity": right_gs["off_target_specificity"],
            "right_off_target_model": right_gs["off_target_model"],
            "right_on_target_score": right_gs["on_target_score"],
            "right_on_target_model": right_gs["on_target_model"],
            "right_reference_only": right_gs["reference_only"],
            "right_reference_note": right_gs["reference_note"],
            "right_gc_content": right_gc,
            "right_self_complementarity": right_ir,
            "right_gc_hint": right_hints["gc_hint"],
            "right_self_comp_hint": right_hints["self_comp_hint"],
            "right_mm_counts": right_mm,
            "left_nuclease": left_nuclease,
            "right_nuclease": right_nuclease,
            "left_valid": bool(left_seq),
            "right_valid": bool(right_seq),
            "left_search_complete": left_search_complete,
            "right_search_complete": right_search_complete,
            "search_complete": (
                left_search_complete and right_search_complete
            ),
            "legacy_score": left_legacy + right_legacy,
            "annotation": format_annotation(ann),
            "nearest_tss": format_tss(tss),
            "isoforms": ann["isoforms"] if ann else "",
            "downstream_atg": atg_text,
            "_left_off_hits": left_off_hits,
            "_right_off_hits": right_off_hits,
        }

        # Surface the library-exclusive per-guide columns for each side.
        for side, side_gs in (("left", left_gs), ("right", right_gs)):
            feature_row = apply_guide_feature_columns({}, side_gs)
            for key, value in feature_row.items():
                item["%s_%s" % (side, key)] = value

        scored_rows.append(item)



    if args.filter_hard:
        print(f"Hard filter removed {filtered_count} candidates")

    selected_off_models = {
        "left": [
            model.strip().lower()
            for model in str(left_otm or "rules").replace(";", ",").split(",")
            if model.strip()
        ],
        "right": [
            model.strip().lower()
            for model in str(right_otm or "rules").replace(";", ",").split(",")
            if model.strip()
        ],
    }
    if args.crispai or any(
            "crispai" in models for models in selected_off_models.values()):
        try:
            from scoring.crispai_runtime import (
                run_crispai_aggregate, make_sgrna, specificity_from_aggregate)
        except Exception as exc:
            print("crispAI dependency import failed: %s" % exc)
        else:
            for side in ("left", "right"):
                side_nuc = left_nuclease if side == "left" else right_nuclease
                if (side_nuc or "").lower() not in ("cas9", "custom"):
                    continue
                side_models = selected_off_models.get(side, [])
                if "crispai" not in side_models and not args.crispai:
                    continue
                as_primary = bool(side_models) and side_models[0] == "crispai"
                if (args.crispai and not as_primary
                        and side_models[:1] in (["rules"], ["auto"])):
                    as_primary = True
                key = "%s_guide_seq" % side
                side_rows = {}
                for idx, item in enumerate(scored_rows):
                    sgrna = make_sgrna((item.get(key) or "").strip())
                    if sgrna:
                        side_rows.setdefault(sgrna, []).append(idx)
                if not side_rows:
                    continue
                mapping = run_crispai_aggregate(
                    side_rows.keys(), output_dir,
                    n_samples=args.crispai_samples, gpu=args.crispai_gpu)
                if not mapping:
                    continue
                filled = 0
                for sgrna, indexes in side_rows.items():
                    aggregate = mapping.get(sgrna)
                    if aggregate is None:
                        continue
                    specificity = specificity_from_aggregate(aggregate)
                    for i in indexes:
                        item = scored_rows[i]
                        item["%s_crispai_off_target" % side] = specificity
                        item["%s_crispai_aggregate_score" % side] = aggregate
                        item["%s_off_target_specificity_crispai" % side] = specificity
                        item["%s_off_target_model_crispai" % side] = "crispai"
                        if as_primary:
                            item["%s_off_target_specificity" % side] = specificity
                            item["%s_off_target_model" % side] = "crispai"
                        filled += 1
                print("crispAI backfilled %s-side %d/%d candidates (%s)"
                      % (side, filled, len(scored_rows),
                         "as primary score" if as_primary else "additional columns only"))
    pair_inputs = []
    for item in scored_rows:
        compatibility = build_pair_compatibility(
            item, item,
            left_nuclease=left_nuclease,
            right_nuclease=right_nuclease,
            gap_min=args.min_gap,
            gap_max=args.max_gap,
            expected_left_side=args.left_side,
            expected_right_side=args.right_side,
        )
        pair_inputs.append(build_pair_input(
            pair_id_for_row(item),
            item,
            item,
            left_off_hits=item.get("_left_off_hits", []),
            right_off_hits=item.get("_right_off_hits", []),
            compatibility=compatibility,
            search_complete=item.get("search_complete", False),
        ))
    ranked_pairs = rank_prediction_only(pair_inputs, pair_rank_policy)
    scored_rows = apply_pair_rank_outputs(
        scored_rows,
        ranked_pairs,
        lambda row, index: pair_id_for_row(row),
    )
    for rank, item in enumerate(scored_rows, start=1):
        item["rank"] = rank

    # ---- 输出排序后的 TSV ----

    out_tsv = os.path.join(output_dir, "query_scores_sorted.tsv")
    mm_columns = mismatch_bucket_columns(args.max_mismatch)
    header_out = [
        "rank", "nuclease", "qid", "pos_id", "seq_id",
        "strand", "left_strand", "right_strand",
        *PREDICTION_ONLY_OUTPUT_FIELDS,
        "conditional_rank",
        "left_pos", "right_pos", "gap",
        "compound_start", "compound_end",
        "left_target_start", "left_target_end",
        "right_target_start", "right_target_end",
        "left_motif_seq", "right_motif_seq",
        "left_flank_seq", "right_flank_seq",
        "left_side", "left_len", "right_side", "right_len",
        "left_legacy_score", "left_total_matches", "left_valid_matches",
        "left_sum_mismatch", "left_AT_score",
        "left_gc_content", "left_self_complementarity",
        "left_gc_hint", "left_self_comp_hint",
        *["left_%s" % column.lower() for column in mm_columns],
        *["left_%s" % key for key in OUTPUT_GUIDE_FEATURE_COLUMNS],
        "right_legacy_score", "right_total_matches", "right_valid_matches",
        "right_sum_mismatch", "right_AT_score",
        "right_gc_content", "right_self_complementarity",
        "right_gc_hint", "right_self_comp_hint",
        *["right_%s" % column.lower() for column in mm_columns],
        *["right_%s" % key for key in OUTPUT_GUIDE_FEATURE_COLUMNS],
        "legacy_score",
        "Annotation", "Nearest-TSS", "Isoforms", "Downstream-ATG",
    ]

    def _complex_row(item):
        pos_id = f"{item['seq_id']}_{item['strand']}_L{item['left_pos']}_R{item['right_pos']}_G{item['gap']}"
        left_mm_out = mismatch_bucket_values(
            item["left_mm_counts"], args.max_mismatch)
        right_mm_out = mismatch_bucket_values(
            item["right_mm_counts"], args.max_mismatch)
        return [
            str(item["rank"]), nuclease, str(item["qid"]),
            pos_id, item["seq_id"], item["strand"],
            item["left_strand"], item["right_strand"],
            *[
                item.get(field, "")
                for field in PREDICTION_ONLY_OUTPUT_FIELDS
            ],
            item.get("conditional_rank", ""),
            str(item["left_pos"]), str(item["right_pos"]), str(item["gap"]),
            str(item["compound_start"]), str(item["compound_end"]),
            str(item["left_target_start"]), str(item["left_target_end"]),
            str(item["right_target_start"]), str(item["right_target_end"]),
            item["left_motif_seq"], item["right_motif_seq"],
            item["left_flank_seq"], item["right_flank_seq"],
            item["left_side"], str(item["left_len"]),
            item["right_side"], str(item["right_len"]),
            f"{item['left_legacy_score']:.2f}",
            str(item["left_total_matches"]), str(item["left_valid_matches"]),
            str(item["left_sum_mismatch"]),
            "" if item["left_at_score"] is None else str(item["left_at_score"]),
            f"{item['left_gc_content']:.2f}",
            str(item["left_self_complementarity"]),
            item["left_gc_hint"], item["left_self_comp_hint"],
            *(str(cnt) for cnt in left_mm_out),
            *[
                item.get("left_%s" % key, "")
                for key in OUTPUT_GUIDE_FEATURE_COLUMNS
            ],
            f"{item['right_legacy_score']:.2f}",
            str(item["right_total_matches"]), str(item["right_valid_matches"]),
            str(item["right_sum_mismatch"]),
            "" if item["right_at_score"] is None else str(item["right_at_score"]),
            f"{item['right_gc_content']:.2f}",
            str(item["right_self_complementarity"]),
            item["right_gc_hint"], item["right_self_comp_hint"],
            *(str(cnt) for cnt in right_mm_out),
            *[
                item.get("right_%s" % key, "")
                for key in OUTPUT_GUIDE_FEATURE_COLUMNS
            ],
            f"{item['legacy_score']:.2f}",
            item["annotation"], item["nearest_tss"],
            item["isoforms"], item["downstream_atg"],
        ]

    complex_rows = [_complex_row(item) for item in scored_rows]
    kept_complex = nonempty_indices(complex_rows)
    with open(out_tsv, "w") as f:
        f.write("\t".join(header_out[i] for i in kept_complex) + "\n")
        for row in complex_rows:
            f.write("\t".join(str(row[i]) for i in kept_complex) + "\n")
    print(f"Sorted scores written to {out_tsv}")


    if args.unique_guides:
        occurrence_counts = defaultdict(int)
        unique_rows = []
        seen_flanks = set()
        for item in scored_rows:
            for side in ("left", "right"):
                seq = item.get(f"{side}_flank_seq", "")
                if not seq:
                    continue
                occurrence_counts[(side, seq)] += 1
                key = (side, seq)
                if key in seen_flanks:
                    continue
                seen_flanks.add(key)
                mm_counts = item[f"{side}_mm_counts"]
                mm_out = mismatch_bucket_values(
                    mm_counts, args.max_mismatch)
                unique_rows.append({
                    "side": side,
                    "qid": "%s_%s" % (item["qid"], side[0]),
                    "position_count": 0,
                    "seq_id": item["seq_id"],
                    "strand": item[f"{side}_strand"],
                    "target_start": item[f"{side}_target_start"],
                    "target_end": item[f"{side}_target_end"],
                    "flank_seq": seq,
                    "total_matches": item[f"{side}_total_matches"],
                    "valid_matches": item[f"{side}_valid_matches"],
                    "sum_mismatch": item[f"{side}_sum_mismatch"],
                    "at_score": item.get(f"{side}_at_score"),
                    "off_target_specificity": item[f"{side}_off_target_specificity"],
                    "off_target_model": item[f"{side}_off_target_model"],
                    "on_target_score": item[f"{side}_on_target_score"],
                    "on_target_model": item[f"{side}_on_target_model"],
                    "gc_content": item[f"{side}_gc_content"],
                    "self_complementarity": item[f"{side}_self_complementarity"],
                    "gc_hint": item[f"{side}_gc_hint"],
                    "self_comp_hint": item[f"{side}_self_comp_hint"],
                    "annotation": item["annotation"],
                    "nearest_tss": item["nearest_tss"],
                    "isoforms": item["isoforms"],
                    "downstream_atg": item["downstream_atg"],
                    "mm_out": mm_out,
                    **{
                        key: item.get("%s_%s" % (side, key), "")
                        for key in OUTPUT_GUIDE_FEATURE_COLUMNS
                    },
                })
        for row in unique_rows:
            row["position_count"] = occurrence_counts[(row["side"], row["flank_seq"])]
        rank_rows(unique_rows, combined_key="off_target_specificity")
        unique_tsv = os.path.join(output_dir, "unique_guides.tsv")
        unique_header = [
            "rank", "nuclease", "side", "qid",
            "position_count", "seq_id", "strand", "target_start",
            "target_end", "flank_seq",
            "total_matches", "valid_matches", "sum_mismatch",
            "AT_score",
            "gc_content", "self_complementarity", "gc_hint",
            "self_comp_hint", "Annotation", "Nearest-TSS", "Isoforms",
            "Downstream-ATG",
            *OUTPUT_GUIDE_FEATURE_COLUMNS,
            *mm_columns,
        ]

        def _unique_row(item):
            return [
                str(item["rank"]), nuclease, item["side"],
                str(item["qid"]), str(item["position_count"]), item["seq_id"],
                item["strand"], str(item["target_start"]), str(item["target_end"]),
                item["flank_seq"], str(item["total_matches"]),
                str(item["valid_matches"]), str(item["sum_mismatch"]),
                "" if item["at_score"] is None else str(item["at_score"]),
                f"{item['gc_content']:.2f}",
                item["self_complementarity"], item["gc_hint"],
                item["self_comp_hint"], item["annotation"],
                item["nearest_tss"], item["isoforms"],
                item["downstream_atg"],
                *[
                    item.get(key, "")
                    for key in OUTPUT_GUIDE_FEATURE_COLUMNS
                ],
                *(str(x) for x in item["mm_out"]),
            ]

        complex_unique_cells = [_unique_row(item) for item in unique_rows]
        kept_unique = nonempty_indices(complex_unique_cells)
        with open(unique_tsv, "w", newline="") as f:
            writer = csv.writer(f, delimiter="\t")
            writer.writerow([unique_header[i] for i in kept_unique])
            for vals in complex_unique_cells:
                writer.writerow([vals[i] for i in kept_unique])
        print(f"Unique guides written to {unique_tsv}")




    qid_counts = defaultdict(int)
    for row in rows:
        for side in ("left", "right"):
            flank_qid = row.get(f"{side}_flank_qid")
            if flank_qid:
                qid_counts[flank_qid] += 1

    top_rows = []
    for qid, matches in blast_matches.items():
        if exact_matches_by_qid is not None:
            source = exact_matches_by_qid.get(qid, [])
            valid = [m for m in source
                     if not is_in_excluded(m["target"], m["start"], exclusion_intervals)]
            valid.sort(key=lambda m: (m["mismatch"], m["target"], m["start"]))
            for rank, m in enumerate(valid[:args.top_offtargets], start=1):
                target, start, mismatch = m["target"], m["start"], m["mismatch"]
                query_len = max(1, len(qid_to_seq.get(qid, "")))
                ann = (annotate_interval(annotation_index, target, start,
                                         start + query_len)
                       if annotation_index is not None else None)
                top_rows.append({
                    "qid": qid,
                    "position_count": qid_counts.get(qid, 0),
                    "rank": rank,
                    "target": target,
                    "start": start,
                    "mismatch": mismatch,
                    "annotation": format_annotation(ann),
                })
        else:
            normalized = [as_hit_dict(match) for match in matches]
            valid = [
                match for match in normalized
                if not is_in_excluded(
                    hit_target(match), hit_start(match), exclusion_intervals)
            ]
            valid.sort(key=lambda match: (
                hit_mismatch(match), hit_target(match), hit_start(match)))
            for rank, match in enumerate(
                    valid[:args.top_offtargets], start=1):
                target = hit_target(match)
                start = hit_start(match)
                mismatch = hit_mismatch(match)
                query_len = max(1, len(qid_to_seq.get(qid, "")))
                ann = (annotate_interval(annotation_index, target, start,
                                         start + query_len)
                       if annotation_index is not None else None)
                top_rows.append({
                    "qid": qid,
                    "position_count": qid_counts.get(qid, 0),
                    "rank": rank,
                    "target": target,
                    "start": start,
                    "mismatch": mismatch,
                    "annotation": format_annotation(ann),
                })
    top_file = os.path.join(output_dir, "top_offtargets.tsv")
    with open(top_file, 'w', newline='') as f:
        writer = csv.writer(f, delimiter='\t')
        writer.writerow(["qid", "position_count", "rank", "target", "start", "mismatch", "annotation"])
        for row in top_rows:
            writer.writerow([row["qid"], row["position_count"], row["rank"],
                             row["target"], row["start"], row["mismatch"], row["annotation"]])
    print(f"Top off-targets written to {top_file}")

    bed_file = os.path.join(output_dir, "query_scores.bed")
    with open(bed_file, 'w', newline='') as f:
        for item in scored_rows:
            strand_bed = "+" if item["strand"] == "plus" else "-"
            burden = float(item.get("pair_offtarget_burden") or 0.0)
            bed_score = 1.0 / (1.0 + max(0.0, burden))
            f.write(f"{item['seq_id']}\t{item['compound_start']}\t{item['compound_end']}\t"
                    f"{item['seq_id']}_{item['strand']}_L{item['left_pos']}_R{item['right_pos']}_G{item['gap']}\t"
                    f"{bed_score:.6f}\t{strand_bed}\n")
    print(f"BED written to {bed_file}")

    if args.xlsx:
        try:
            tsv_to_xlsx(out_tsv, os.path.join(output_dir, "query_scores_sorted.xlsx"))
            unique_path = os.path.join(output_dir, "unique_guides.tsv")
            if os.path.isfile(unique_path):
                tsv_to_xlsx(unique_path, os.path.join(output_dir, "unique_guides.xlsx"))
            top_path = os.path.join(output_dir, "top_offtargets.tsv")
            if os.path.isfile(top_path):
                tsv_to_xlsx(top_path, os.path.join(output_dir, "top_offtargets.xlsx"))
            print("XLSX outputs written")
        except RuntimeError as exc:
            print(f"Warning: {exc}")



    # ---- 为完美匹配的 flank 提取两侧各 100 bp 的 flanking sequence ----

    flank_extract = 100

    print("PROGRESS: generating 85", flush=True)

    for qid, flank_seq in qid_to_seq.items():
        if qid not in blast_matches:
            continue
        records = []
        for match in blast_matches[qid]:
            rec_id = hit_target(match)
            start = hit_start(match)
            mm = hit_mismatch(match)
            if mm == 0 and not is_in_excluded(
                    rec_id, start, exclusion_intervals):
                frag = fetch_sequence(
                    genome_records, rec_id,
                    start - flank_extract,
                    start + len(flank_seq) + flank_extract,
                )
                if frag:
                    records.append(SeqRecord(
                        Seq(frag),
                        id="%s_pos%d" % (rec_id, start - flank_extract),
                        description="",
                    ))
        if records:
            main_dir = os.path.join(output_dir, "target_flanks")
            os.makedirs(main_dir, exist_ok=True)
            out_file = os.path.join(main_dir, "%s.fa" % qid)
            SeqIO.write(records, out_file, "fasta")
            print(f"  Written {out_file} with {len(records)} flanking sequences")

    print("\nAnalysis complete.")



if __name__ == "__main__":

    main()
