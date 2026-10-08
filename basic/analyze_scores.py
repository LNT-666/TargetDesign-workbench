#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import csv
import io
import json
import argparse
from collections import defaultdict
from Bio import SeqIO
from Bio.Seq import Seq
from Bio.SeqRecord import SeqRecord

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "shared"))
from search.blast_utils import load_genome_and_prepare_fasta, fetch_sequence, reverse_complement, orient_off_target_pair, max_inverted_repeat_len, is_in_excluded, _pam_matches
from search.hit_utils import (
    as_hit_dict, has_alignment, hit_mismatch, hit_start, hit_strand,
    hit_target, orient_rich_hit,
)
from scoring.scoring import (
    compute_guide_scores, apply_guide_feature_columns, rank_rows,
    filter_hints, passes_filter,
    OUTPUT_GUIDE_FEATURE_COLUMNS,
)
from scoring.at_score import (
    compute_at_score,
    compute_at_score_from_flank,
    should_output_at_score,
)
from design.system_presets import resolve_run_nuclease
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

# ????????? CSV ??????????????????????????????????????????????????????????????
csv.field_size_limit(sys.maxsize)

# ---------- ????????????????????????????----------
def window_motif_slice(query_len, motif_len, side):
    """Return the (start, end) slice of the design motif inside a guide-oriented window.

    The extraction stores the motif/PAM at one end of the window: at the end for
    ``side == 'upstream'`` ([spacer][motif]) and at the start for
    ``side == 'downstream'`` ([motif][spacer]).  Working in the guide-oriented
    window makes this independent of the recorded strand.
    """
    if side == "upstream":
        return query_len - motif_len, query_len
    return 0, motif_len


def guide_spacer(guide_seq, motif_len, side):
    """Return the spacer part of a guide-oriented window (the non-motif part)."""
    motif_start, motif_end = window_motif_slice(len(guide_seq), motif_len, side)
    return guide_seq[:motif_start] + guide_seq[motif_end:]


def apply_crispai_scores(query_rows, motif_plus, side, nuclease, output_dir,
                         samples=200, gpu=-1, as_primary=True):
    """Run crispAI aggregate over all candidates and backfill crispAI columns.

    crispAI is a batch external scorer, so it runs once over the unique sgRNAs
    instead of inside the per-candidate scoring loop.  Any preflight/run failure
    (or a row without a usable 20 nt Cas9 spacer) skips the backfill.  When
    ``as_primary`` is True it also replaces ``off_target_specificity``;
    otherwise it only fills the crispAI columns.
    """
    if nuclease not in ("cas9", "custom"):
        print("crispAI applies only to SpCas9 (current nucleicase=%s; ignored)" % nuclease)
        return False
    try:
        from scoring.crispai_runtime import (
            run_crispai_aggregate, make_sgrna, specificity_from_aggregate)
    except Exception as exc:
        print("crispAI dependency import failed: %s" % exc)
        return False
    motif_len = len(motif_plus)
    sgrna_rows = {}
    for i, row in enumerate(query_rows):
        guide_seq = (reverse_complement(row["query_seq"])
                     if row["strand"] == "minus" else row["query_seq"])
        spacer = guide_spacer(guide_seq, motif_len, side)
        sgrna = make_sgrna(spacer)
        if sgrna:
            sgrna_rows.setdefault(sgrna, []).append(i)
    if not sgrna_rows:
        print("No usable 20 nt Cas9 spacer available for crispAI scoring")
        return False
    mapping = run_crispai_aggregate(
        sgrna_rows.keys(), output_dir, n_samples=samples, gpu=gpu)
    if not mapping:
        return False
    filled = 0
    for sgrna, indexes in sgrna_rows.items():
        aggregate = mapping.get(sgrna)
        if aggregate is None:
            continue
        specificity = specificity_from_aggregate(aggregate)
        for i in indexes:
            row = query_rows[i]
            row["crispai_off_target"] = specificity
            row["crispai_aggregate_score"] = aggregate
            row["off_target_specificity_crispai"] = specificity
            row["off_target_model_crispai"] = "crispai"
            if as_primary:
                row["off_target_specificity"] = specificity
                row["off_target_model"] = "crispai"
            filled += 1
    print("crispAI backfilled %d/%d candidates (%s)"
          % (filled, len(query_rows), "as primary score" if as_primary else "additional columns only"))
    return True


def split_position(entry):
    """Return (seq_id, strand, motif_pos) from a 3- or 4-field position record."""
    if len(entry) < 3:
        raise ValueError(f"invalid position record: {entry!r}")
    return entry[0], entry[1], entry[2]


def match_mismatch(match):
    """Return the mismatch count from a compact match record."""
    return hit_mismatch(match)


# ---------- ?????????????----------
def main():
    parser = argparse.ArgumentParser(description="Score basic motif Off-target search results")
    parser.add_argument("tsv_file", help="Off-target search result TSV file produced by blast.py (.tsv)")
    parser.add_argument("output_dir", help="output directory")
    parser.add_argument("--flanking_extract", type=int, default=100,
                        help="Extract flanking sequence on both sides of perfect matches (default 100)")
    parser.add_argument("--nuclease", choices=["custom", "cas9", "cas12", "cas12a", "cas12b",
                                               "cas13", "cas14a", "tnpb"],
                        default="cas9", help="Nuclease system used for scoring (default cas9)")
    parser.add_argument("--tnpb-subtype", choices=["isdra2", "other", "unknown"],
                        default="unknown", help="TnpB subtype (only used when nuclease=tnpb)")
    parser.add_argument("--reference-only-model", choices=["none", "cas9", "teep"],
                        default="none", help="Force an unvalidated model for unsupported systems")
    parser.add_argument(
        "--on-target-model", default="cropsr",
        help="On-target model(s), comma-separated for multiple selections")
    parser.add_argument(
        "--off-target-model", default="rules",
        help="Off-target model(s), comma-separated for multiple selections")
    parser.add_argument("--max-mismatch", type=int, choices=[0, 1, 2, 3, 4],
                        default=4,
                        help="Maximum mismatch budget represented in MM columns")
    parser.add_argument("--crispai", action="store_true",
                        help="Also compute and write crispAI columns even when it is not the primary off-target model")
    parser.add_argument("--crispai-samples", type=int, default=200,
                        help="crispAI posterior sample count (default 200)")
    parser.add_argument("--crispai-gpu", type=int, default=-1,
                        help="CUDA device for crispAI/Cas-OFFinder (-1 = CPU)")
    parser.add_argument("--gc-min", type=float, default=40.0, help="GC hint lower bound (default 40)")
    parser.add_argument("--gc-max", type=float, default=70.0, help="GC hint upper bound (default 70)")
    parser.add_argument("--self-comp-max", type=int, default=4,
                        help="Self-complementarity hint threshold (default 4)")
    parser.add_argument("--filter-hard", action="store_true",
                        help="Actually drop candidates that fail GC/self-complementarity hints")
    parser.add_argument("--unique-guides", action="store_true",
                        help="Also write one row per unique query sequence to unique_guides.tsv")
    parser.add_argument("--top-offtargets", type=int, default=5,
                        help="Write the top N off-targets per unique query to top_offtargets.tsv (default 5)")
    parser.add_argument("--annotation", default=None,
                        help="NCBI GFF3 annotation file used to annotate candidates")
    parser.add_argument("--xlsx", action="store_true",
                        help="Also write XLSX versions of the main TSV outputs")
    parser.add_argument("--mode", choices=["free", "preset"], default="free",
                        help="Design mode: free input or preset system rules")
    parser.add_argument("--preset", default="custom",
                        help="System preset key used in preset mode")
    parser.add_argument("--pam-motif", default=None,
                        help="PAM motif used for PAM-aware scoring")
    parser.add_argument("--spacer-len", type=int, default=None,
                        help="Expected spacer length from the selected system")
    parser.add_argument("--seed-start", type=int, default=None,
                        help="1-based start of the seed region")
    parser.add_argument("--seed-end", type=int, default=None,
                        help="1-based end of the seed region")
    parser.add_argument("--target-type", choices=["dna", "rna", "ssdna"], default="dna",
                        help="Target nucleic acid type used by the preset")
    parser.add_argument("--require-pam", dest="require_pam", action="store_true", default=None,
                        help="Require a valid PAM site for each off-target; auto-on for Cas9/Cas12")
    parser.add_argument("--no-require-pam", dest="require_pam", action="store_false",
                        help="Turn off PAM gating for off-targets")
    args = parser.parse_args()

    # ``--mode preset --preset tnpb`` (etc.) without ``--nuclease`` must not
    # keep the cas9 default in the scored/exported ``nuclease`` column.
    args.nuclease = resolve_run_nuclease(
        args.nuclease, args.preset if args.mode == "preset" else "custom")

    tsv_file = args.tsv_file
    output_dir = args.output_dir
    flank_len_extract = args.flanking_extract

    if not os.path.isfile(tsv_file):
        # [fixed] print(f"????????????...
        sys.exit(2)

    os.makedirs(output_dir, exist_ok=True)

    # ---- ????????? TSV ?????????????????? ----
    with open(tsv_file, 'r') as f:
        reader = csv.DictReader(f, delimiter='\t')
        rows = list(reader)

    # ?????????????????????????????????????????????
    meta_row = None
    data_rows = []
    for row in rows:
        if row['qid'] == 'metadata':
            meta_row = row
        else:
            data_rows.append(row)

    if meta_row is None:
        print("Error: missing metadata row (qid='metadata')")
        sys.exit(2)

    # ??????????????????????
    motif_plus = meta_row['motif_plus']
    motif_minus = meta_row['motif_minus']
    flank_len = int(meta_row['flank_len'])
    side = meta_row['side']
    rdna_intervals = json.loads(meta_row['rdna_intervals'])
    include_at_score = should_output_at_score(args.mode, args.preset)
    if args.require_pam is None:
        args.require_pam = args.nuclease in ("cas9", "cas12", "cas12a", "cas12b")

    # ---- ????????????????????????????????????????----
    if 'genome_file' in meta_row and meta_row['genome_file']:
        genome_file = meta_row['genome_file']
        genome_index, _, temp_genome = load_genome_and_prepare_fasta(genome_file)
        print(f"Loaded {len(genome_index.keys())} chromosomes/scaffolds from indexed FASTA")
    else:
        print("Error: genome_file missing from Off-target search metadata.")
        sys.exit(2)

    annotation_index = None
    if args.annotation and os.path.isfile(args.annotation):
        annotation_index = build_annotation_index(args.annotation)
        print(f"Loaded annotation: {annotation_index.gene_count} genes, "
              f"{annotation_index.transcript_count} transcripts")

    # ???????????????????????????
    qid_to_seq = {}
    qid_to_positions = defaultdict(list)
    blast_matches = {}
    for row in data_rows:
        qid = row['qid']
        qid_to_seq[qid] = row['sequence']
        qid_to_positions[qid] = json.loads(row['positions'])
        blast_matches[qid] = json.loads(row['matches'])

    # [fixed] print(f"????????????...
    print("PROGRESS: reading 10", flush=True)
    # [fixed] print(f"????????????...
    # [fixed] print(f"????????????...

    # ??????????????????????????????????????????????????? ID????????????????????????????????????
    all_seq_ids = set()
    for pos_list in qid_to_positions.values():
        for entry in pos_list:
            seq_id, _, _ = split_position(entry)
            all_seq_ids.add(seq_id)

    if annotation_index is not None and annotation_index.seqids:
        unknown_ids = sorted(
            seq_id for seq_id in all_seq_ids
            if seq_id not in annotation_index.seqids
        )
        if unknown_ids:
            sample = ", ".join(unknown_ids[:5])
            if len(unknown_ids) > 5:
                sample += ", ..."
            print(
                "Warning: the annotation describes none of the %d query "
                "sequence id(s) (%s); annotation columns stay empty. Use the "
                "annotation's chromosome names as the search input."
                % (len(unknown_ids), sample)
            )

    # ===== ????????????????????????????????????????=====
    positions = []
    for qid, pos_list in qid_to_positions.items():
        for entry in pos_list:
            seq_id, strand, motif_pos = split_position(entry)
            positions.append((seq_id, strand, motif_pos, qid))

    score_cache = {}

    def compute_query_score(qid, strand):
        cache_key = (qid, strand)
        if cache_key in score_cache:
            return score_cache[cache_key]
        if qid not in blast_matches:
            result = (0.0, 0, 0, 0, [0]*6, {
                "off_target_specificity": 1.0,
                "off_target_model": "no_matches",
                "on_target_score": 0.0,
                "on_target_model": "no_matches",
                "reference_only": False,
                "reference_note": "",
            })
            score_cache[cache_key] = result
            return result
        matches = [
            match for match in blast_matches[qid]
            if match_mismatch(match) <= args.max_mismatch
        ]
        query_seq = qid_to_seq[qid]
        guide_seq = (
            reverse_complement(query_seq)
            if strand == "minus" else query_seq
        )
        total = len(matches)
        valid_mms = []
        off_pairs = []
        for match in matches:
            match_hit = as_hit_dict(match)
            rec_id = hit_target(match_hit)
            start = hit_start(match_hit)
            mm = hit_mismatch(match_hit)
            hit_target_strand = hit_strand(match_hit)
            if has_alignment(match_hit):
                if not is_in_excluded(rec_id, start, rdna_intervals):
                    off_pairs.append(
                        orient_rich_hit(match_hit, strand))
                    valid_mms.append(mm)
                continue
            if not is_in_excluded(rec_id, start, rdna_intervals):
                end = start + len(query_seq) + 2
                off = fetch_sequence(genome_index, rec_id, start, end)
                if off and len(off) >= len(query_seq):
                    raw_off = off[:len(query_seq)]
                    raw_pam = off[len(query_seq):len(query_seq) + 2]
                    off_seq, pam_seq = orient_off_target_pair(
                        raw_off, raw_pam, hit_target_strand, strand
                    )
                    if args.require_pam:
                        # The guide window carries its PAM motif inside the
                        # window (e.g. [20 bp spacer][NGG]); read the PAM there
                        # instead of from the bases after the window.
                        motif_start, motif_end = window_motif_slice(
                            len(query_seq), len(motif_plus), side)
                        hit_pam = off_seq[motif_start:motif_end]
                        pam_pattern = motif_plus if strand == "plus" else (
                            motif_minus or reverse_complement(motif_plus))
                        if not _pam_matches(
                                hit_pam, pam_pattern):
                            # Not a real PAM site for this nuclease: skip it so
                            # it never enters valid_matches/MM/off_pairs.
                            continue
                        # CFD and PAM_SCORES expect the 2-base PAM (the 'GG' of NGG).
                        pam_seq = hit_pam[-2:]
                    off_pairs.append((off_seq, pam_seq))
                    valid_mms.append(mm)
        valid = len(valid_mms)
        sum_mismatch = sum(valid_mms)
        mm_counts = [0]*6
        for mm in valid_mms:
            if mm <= 5:
                mm_counts[mm] += 1
        # ???????????????????????????????????????????????????????????????????????
        score = 0.0
        cumulative = 0
        for k in range(6):
            cumulative += mm_counts[k]   # ?????????????<= k ?????????????
            weight = 10 ** (-k + 1)
            score += cumulative * weight
        guide_scores = compute_guide_scores(guide_seq, off_pairs,
                                            nuclease=args.nuclease,
                                            tnpb_subtype=args.tnpb_subtype,
                                            reference_only_model=args.reference_only_model,
                                            on_target_model=args.on_target_model,
                                            off_target_model=args.off_target_model,
                                            preset_key=args.preset if args.mode == "preset" else "custom",
                                            seed_start=args.seed_start,
                                            seed_end=args.seed_end,
                                            target_type=args.target_type)
        result = (score, total, valid, sum_mismatch, mm_counts, guide_scores)
        score_cache[cache_key] = result
        return result

    query_rows = []
    total_positions = len(positions)
    filtered_count = 0
    for idx, (seq_id, strand, motif_pos, qid) in enumerate(positions):
        if idx % max(1, total_positions // 10) == 0 or idx == total_positions - 1:
            pct = 10 + int(idx / total_positions * 40)
            print(
                f"PROGRESS: Analyzing target {idx + 1}/{total_positions} {pct}",
                flush=True,
            )
        score, total, valid, sum_mismatch, mm_counts, guide_scores = compute_query_score(
            qid, strand
        )
        pos_id = f"{seq_id}_{strand}_{idx}"
        query_seq = qid_to_seq[qid]
        at_score = None
        if include_at_score:
            at_score = compute_at_score(
                query_seq, side, strand, motif_plus, motif_minus, flank_len)
        gc_count = query_seq.count('G') + query_seq.count('C')
        gc_content = (gc_count / len(query_seq)) * 100.0
        inv_rep = max_inverted_repeat_len(query_seq, min_len=3)
        hints = filter_hints(gc_content, inv_rep, args.gc_min, args.gc_max, args.self_comp_max)
        if not passes_filter(hints, args.filter_hard):
            filtered_count += 1
            continue

        ann = None
        tss = None
        atg_text = ""
        if annotation_index is not None:
            ann = annotate_interval(annotation_index, seq_id, motif_pos,
                                    motif_pos + len(query_seq))
            tss = nearest_tss(annotation_index, seq_id, motif_pos,
                              motif_pos + len(query_seq))
            atg = find_downstream_atg(genome_index, seq_id, motif_pos,
                                      motif_pos + len(query_seq), strand, window=500)
            if atg is not None:
                if strand == "plus":
                    atg_text = f"{atg - (motif_pos + len(query_seq))}bp"
                else:
                    atg_text = f"{motif_pos - atg}bp"
        row = {
            "pos_id": pos_id,
            "seq_id": seq_id,
            "strand": strand,
            "motif_pos": motif_pos,
            "qid": qid,
            "query_seq": query_seq,
            "total_score": score,
            "off_target_specificity": guide_scores["off_target_specificity"],
            "off_target_model": guide_scores["off_target_model"],
            "on_target_score": guide_scores["on_target_score"],
            "on_target_model": guide_scores["on_target_model"],
            "reference_only": guide_scores["reference_only"],
            "reference_note": guide_scores["reference_note"],
            "total_matches": total,
            "valid_matches": valid,
            "sum_mismatch": sum_mismatch,
            "at_score": at_score,
            "gc_content": gc_content,
            "inv_rep": inv_rep,
            "gc_hint": hints["gc_hint"],
            "self_comp_hint": hints["self_comp_hint"],
            "annotation": format_annotation(ann),
            "nearest_tss": format_tss(tss),
            "isoforms": ann["isoforms"] if ann else "",
            "downstream_atg": atg_text,
            "mm_counts": mm_counts,
        }
        apply_guide_feature_columns(row, guide_scores)
        query_rows.append(row)

    if args.filter_hard:
        print(f"Hard filter removed {filtered_count} candidates")

    off_models = [
        model.strip().lower()
        for model in str(args.off_target_model or "rules")
        .replace(";", ",").split(",")
        if model.strip()
    ]
    primary_off_model = off_models[0] if off_models else "rules"
    if "crispai" in off_models or args.crispai:
        apply_crispai_scores(
            query_rows, motif_plus, side, args.nuclease, output_dir,
            samples=args.crispai_samples, gpu=args.crispai_gpu,
            as_primary=(
                primary_off_model == "crispai"
                or (primary_off_model in ("rules", "auto") and args.crispai)))

    rank_rows(query_rows)

    print("PROGRESS: writing 95", flush=True)
    query_header = [
        "rank", "nuclease",
        "off_target_specificity", "legacy_total_score", "pos_id", "seq_id", "strand",
        "motif_pos", "qid", "query_seq", "total_matches", "valid_matches",
        "sum_mismatch",
    ]
    if include_at_score:
        query_header.append("AT_score")
    query_header += [
        "GC-content", "GC-hint",
        "Self-complementarity", "Self-comp-hint", "Annotation", "Nearest-TSS",
        "Isoforms", "Downstream-ATG",
    ] + list(OUTPUT_GUIDE_FEATURE_COLUMNS) + [
        "crispai_aggregate_score",
        *mismatch_bucket_columns(args.max_mismatch),
    ]

    def _cell(value):
        return "" if value is None else str(value)

    def query_cells(row):
        mm_out = mismatch_bucket_values(
            row["mm_counts"], args.max_mismatch)
        values = [
            str(row["rank"]), args.nuclease,
            f"{row['off_target_specificity']:.6f}", f"{row['total_score']:.2f}",
            _cell(row["pos_id"]), _cell(row["seq_id"]), _cell(row["strand"]),
            _cell(row["motif_pos"]), _cell(row["qid"]), _cell(row["query_seq"]),
            _cell(row["total_matches"]), _cell(row["valid_matches"]),
            _cell(row["sum_mismatch"]),
        ]
        if include_at_score:
            values.append(_cell(row["at_score"]))
        values += [
            f"{row['gc_content']:.2f}", _cell(row["gc_hint"]),
            _cell(row["inv_rep"]), _cell(row["self_comp_hint"]),
            _cell(row["annotation"]), _cell(row["nearest_tss"]),
            _cell(row["isoforms"]), _cell(row["downstream_atg"]),
        ]
        values += [
            _cell(row.get(key, ""))
            for key in OUTPUT_GUIDE_FEATURE_COLUMNS
        ]
        values.append(_cell(row.get("crispai_aggregate_score", "")))
        values += [_cell(cnt) for cnt in mm_out]
        return values

    query_cell_rows = [query_cells(row) for row in query_rows]
    kept_columns = nonempty_indices(query_cell_rows)
    out_file = os.path.join(output_dir, "query_scores_sorted.tsv")
    with open(out_file, "w") as f:
        f.write("\t".join(query_header[i] for i in kept_columns) + "\n")
        for vals in query_cell_rows:
            f.write("\t".join(vals[i] for i in kept_columns) + "\n")
    print(f"\nSorted scores written to: {out_file}")
    print("Top 5 highest-scoring results:")
    for row in query_rows[:5]:
        print(f"  {row['pos_id']}: spec={row['off_target_specificity']:.4f}, "
              f"on={row['on_target_score']:.4f}, query={row['query_seq']}")

    qid_position_count = {qid: len(pos_list) for qid, pos_list in qid_to_positions.items()}

    if args.unique_guides:
        unique_rows = []
        seen_qids = set()
        for row in query_rows:
            if row["qid"] in seen_qids:
                continue
            seen_qids.add(row["qid"])
            unique_row = dict(row)
            unique_row["position_count"] = qid_position_count[row["qid"]]
            unique_rows.append(unique_row)
        rank_rows(unique_rows)
        unique_header = [
            "rank", "nuclease",
            "off_target_specificity", "legacy_total_score", "qid", "position_count",
            "query_seq", "total_matches", "valid_matches", "sum_mismatch",
        ]
        if include_at_score:
            unique_header.append("AT_score")
        unique_header += [
            "GC-content", "GC-hint", "Self-complementarity", "Self-comp-hint",
            "Annotation", "Nearest-TSS", "Isoforms", "Downstream-ATG",
        ] + list(OUTPUT_GUIDE_FEATURE_COLUMNS) + [
            "crispai_aggregate_score",
            *mismatch_bucket_columns(args.max_mismatch),
        ]

        def unique_cells(row):
            mm_out = mismatch_bucket_values(
                row["mm_counts"], args.max_mismatch)
            values = [
                str(row["rank"]), args.nuclease,
                f"{row['off_target_specificity']:.6f}", f"{row['total_score']:.2f}",
                _cell(row["qid"]), _cell(row["position_count"]), _cell(row["query_seq"]),
                _cell(row["total_matches"]), _cell(row["valid_matches"]),
                _cell(row["sum_mismatch"]),
            ]
            if include_at_score:
                values.append(_cell(row["at_score"]))
            values += [
                f"{row['gc_content']:.2f}", _cell(row["gc_hint"]),
                _cell(row["inv_rep"]), _cell(row["self_comp_hint"]),
                _cell(row["annotation"]), _cell(row["nearest_tss"]),
                _cell(row["isoforms"]), _cell(row["downstream_atg"]),
            ]
            values += [
                _cell(row.get(key, ""))
                for key in OUTPUT_GUIDE_FEATURE_COLUMNS
            ]
            values.append(_cell(row.get("crispai_aggregate_score", "")))
            values += [_cell(cnt) for cnt in mm_out]
            return values

        unique_cell_rows = [unique_cells(row) for row in unique_rows]
        kept_unique = nonempty_indices(unique_cell_rows)
        unique_file = os.path.join(output_dir, "unique_guides.tsv")
        with open(unique_file, "w", newline="") as f:
            writer = csv.writer(f, delimiter="\t")
            writer.writerow([unique_header[i] for i in kept_unique])
            for vals in unique_cell_rows:
                writer.writerow([vals[i] for i in kept_unique])
        print(f"Unique guides written to {unique_file}")

    top_rows = []
    for qid, matches in blast_matches.items():
        valid = [
            match for match in matches
            if match_mismatch(match) <= args.max_mismatch
            and not is_in_excluded(
                hit_target(match), hit_start(match), rdna_intervals)
        ]
        valid.sort(
            key=lambda m: (
                hit_mismatch(m), hit_target(m), hit_start(m)))
        for rank, match in enumerate(valid[:args.top_offtargets], start=1):
            target = hit_target(match)
            start = hit_start(match)
            mismatch = hit_mismatch(match)
            query_len = max(1, len(qid_to_seq.get(qid, "")))
            ann = (annotate_interval(annotation_index, target, start, start + query_len)
                   if annotation_index is not None else None)
            top_rows.append({
                "qid": qid,
                "position_count": qid_position_count.get(qid, 0),
                "rank": rank,
                "target": target,
                "start": start,
                "mismatch": mismatch,
                "annotation": format_annotation(ann),
            })
    top_file = os.path.join(output_dir, "top_offtargets.tsv")
    with open(top_file, "w", newline="") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(["qid", "position_count", "rank", "target", "start", "mismatch", "annotation"])
        for row in top_rows:
            writer.writerow([row["qid"], row["position_count"], row["rank"],
                             row["target"], row["start"], row["mismatch"], row["annotation"]])
    print(f"Top off-targets written to {top_file}")

    bed_file = os.path.join(output_dir, "query_scores.bed")
    with open(bed_file, "w", newline="") as f:
        for row in query_rows:
            strand_bed = "+" if row["strand"] == "plus" else "-"
            bed_score = 1.0 / max(
                1e-12, float(row["off_target_specificity"])
            )
            f.write(f"{row['seq_id']}\t{row['motif_pos']}\t"
                    f"{row['motif_pos'] + len(row['query_seq'])}\t{row['pos_id']}\t"
                    f"{bed_score:.6f}\t{strand_bed}\n")
    print(f"BED written to {bed_file}")

    if args.xlsx:
        try:
            tsv_to_xlsx(out_file, os.path.join(output_dir, "query_scores_sorted.xlsx"))
            unique_path = os.path.join(output_dir, "unique_guides.tsv")
            if os.path.isfile(unique_path):
                tsv_to_xlsx(unique_path, os.path.join(output_dir, "unique_guides.xlsx"))
            if os.path.isfile(top_file):
                tsv_to_xlsx(top_file, os.path.join(output_dir, "top_offtargets.xlsx"))
            print("XLSX outputs written")
        except RuntimeError as exc:
            print(f"Warning: {exc}")

    # ===== ?????????????????????????????????????????????????????????mm=0???????????????????????????????????? =====
    flank_len_extract = args.flanking_extract
    qid_to_seq_ids = defaultdict(set)
    for qid, pos_list in qid_to_positions.items():
        for entry in pos_list:
            seq_id, _, _ = split_position(entry)
            qid_to_seq_ids[qid].add(seq_id)

    flank_groups = defaultdict(list)

    total_qids = len(qid_to_seq)
    for qid_idx, (qid, seq_20) in enumerate(qid_to_seq.items()):
        if qid_idx % max(1, total_qids // 10) == 0 or qid_idx == total_qids - 1:
            print(
                f"PROGRESS: Extracting off-target flanks "
                f"{60 + int(qid_idx / total_qids * 30)}",
                flush=True,
            )
        if qid not in blast_matches:
            continue
        records = []
        for match in blast_matches[qid]:
            rec_id = hit_target(match)
            start = hit_start(match)
            mm = hit_mismatch(match)
            if mm == 0 and not is_in_excluded(rec_id, start, rdna_intervals):
                frag = fetch_sequence(genome_index, rec_id, start - flank_len_extract,
                                      start + len(seq_20) + flank_len_extract)
                if frag:
                    record = SeqRecord(Seq(frag), id=f"{rec_id}_pos{start}", description="")
                    records.append(record)
        if records:
            for seq_id in qid_to_seq_ids[qid]:
                flank_groups[(seq_id, qid)].extend(records)

    for (seq_id, qid), records in flank_groups.items():
        main_dir = os.path.join(output_dir, f"{seq_id}_flanks")
        os.makedirs(main_dir, exist_ok=True)
        query_seq = qid_to_seq[qid]
        filename = f"{query_seq}.fa"
        out_file = os.path.join(main_dir, filename)
        SeqIO.write(records, out_file, "fasta")
        # [fixed] print(f"  ????????? ...

    written_seq_ids = {group_key[0] for group_key in flank_groups}
    for seq_id in all_seq_ids:
        if seq_id not in written_seq_ids:
            print(
                f"  Warning: no mm=0 flanking sequence found for "
                f"{seq_id}; skipped"
            )

    # [fixed] print("\n???????????...

if __name__ == "__main__":
    main()
