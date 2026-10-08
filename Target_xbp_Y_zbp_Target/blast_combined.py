#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
blast_combined.py
对 occurrence 候选执行左右 motif 组合评分
执行 Off-target search 并输出 per-side TSV
"""

import sys
import os
import re
import json
import csv
import io
import tempfile
import argparse
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "shared"))
from search.blast_utils import (
    check_blast_installed, ensure_blastdb, load_genome_and_prepare_fasta, fetch_sequence,
    reverse_complement, orient_off_target_pair, max_inverted_repeat_len,
    build_exclusion_intervals, is_in_excluded
)
from search.blast_utils import run_blastn as shared_run_blastn
from search.offtarget_backend import (
    SearchParams, apply_engine_defaults, print_search_progress,
    run_backend,
)
from search.hit_utils import has_alignment, orient_rich_hit
from design.library_preflight import MAX_EXACT_GENOME_BYTES
from scoring.scoring import (
    compute_guide_scores, apply_guide_feature_columns, rank_rows,
    filter_hints, passes_filter, OUTPUT_GUIDE_FEATURE_COLUMNS,
)
from scoring.at_score import (
    compute_at_score_from_flank, should_output_at_score,
)
from design.system_presets import get_preset
from data.candidate_annotation import (
    build_annotation_index, annotate_interval, nearest_tss,
    find_downstream_atg, format_annotation, format_tss,
)
from output.output_columns import (
    mismatch_bucket_columns,
    mismatch_bucket_values,
    nonempty_columns,
)
from output.xlsx_utils import tsv_to_xlsx

csv.field_size_limit(sys.maxsize)


def parse_occurrence_tsv(filepath):
    """读取 left/right occurrence TSV，返回 {qid: {sequence, positions}}"""
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = [line for line in f if not line.startswith('#')]
    if not lines:
        return {}
    reader = csv.DictReader(io.StringIO(''.join(lines)), delimiter='\t')
    result = {}
    for row in reader:
        qid = row['qid']
        result[qid] = {
            'sequence': row['sequence'],
            'positions': json.loads(row['positions'])
        }
    return result


def _guide_from_window(sequence, positions):
    """Return the spacer (guide) portion of a Y-ZBP occurrence window.

    extract_motifs.py stores ``guide + motif`` for ``upstream`` and
    ``motif + guide`` for ``downstream``. The motif coordinates in
    ``positions`` tell us which side the spacer is on.
    """
    if not sequence or not positions:
        return sequence
    pos0 = positions[0]
    full_start = int(pos0[2]) if len(pos0) >= 3 else 0
    full_end = int(pos0[3]) if len(pos0) >= 4 else len(sequence)
    motif_start = int(pos0[4]) if len(pos0) >= 6 else full_start
    motif_end = int(pos0[5]) if len(pos0) >= 6 else full_end
    if motif_start > full_start:
        return sequence[:motif_start - full_start]
    guide_len = full_end - motif_end
    if guide_len <= 0:
        return sequence
    return sequence[len(sequence) - guide_len:]


def _at_score_from_occurrence(sequence, positions):
    """Return the AT score for the flank stored in an occurrence window."""
    if not sequence or not positions:
        return 0
    pos0 = positions[0]
    if len(pos0) < 6:
        return 0
    full_start = int(pos0[2])
    motif_start = int(pos0[4])
    motif_end = int(pos0[5])
    motif_strand = pos0[1]
    if motif_start > full_start:
        flank = sequence[:motif_start - full_start]
        flank_side = "upstream"
    else:
        flank = sequence[motif_end - full_start:]
        flank_side = "downstream"
    return compute_at_score_from_flank(flank, flank_side, motif_strand)


def _fetch_guide_and_pam(genome, target, start, guide_len, hit_strand, pam_side,
                         pam_len=2):
    """Fetch a hit's spacer and its immediately adjacent PAM on the plus strand."""
    hit_strand = hit_strand or "+"
    pam_side = (pam_side or "3prime").lower()
    raw_off = fetch_sequence(genome, target, start, start + guide_len)
    if not raw_off or len(raw_off) < guide_len:
        return None, None
    if hit_strand == "+":
        pam_before = pam_side == "5prime"
    else:
        pam_before = pam_side == "3prime"
    if pam_before:
        raw_pam = fetch_sequence(genome, target, start - pam_len, start) or ""
    else:
        raw_pam = fetch_sequence(
            genome, target, start + guide_len, start + guide_len + pam_len
        ) or ""
    return raw_off, raw_pam


def compute_match_score(match_list, exclusion_intervals):
    """按 basic 工具的评分规则计算匹配分数"""
    valid_mms = []
    for m in match_list:
        if not is_in_excluded(m["target"], m["start"], exclusion_intervals):
            valid_mms.append(m["mismatch"])
    mm_counts = [0] * 6
    for mm in valid_mms:
        if mm <= 5:
            mm_counts[mm] += 1
    score = 0.0
    cumulative = 0
    for k in range(6):
        cumulative += mm_counts[k]
        weight = 10 ** (-k + 1)
        score += cumulative * weight
    return score, mm_counts


def main():
    parser = argparse.ArgumentParser(description="Run motif combination and Off-target search on occurrence candidates, writing per-side results")
    parser.add_argument('--input_dir', required=True, help='occurrence input directory')
    parser.add_argument('--genome', required=True, help='genome FASTA file')
    parser.add_argument('--blast_db', required=False, help='genome database prefix')
    parser.add_argument('--target-fasta', default=None,
                        help='Target FASTA used to display Y/region sequences')
    parser.add_argument('--engine', default='blast',
                        choices=['exact', 'indexed', 'blast', 'gggenome',
                                 'auto'])
    parser.add_argument('--index-path', default='',
                        help='Local genome index prefix (.ggi/.json)')
    parser.add_argument('--genome-build', default='',
                        help='Genome build name for GGGenome, e.g. hg38')
    parser.add_argument('--mask', default=None, help='mask gene FASTA file (optional)')
    parser.add_argument('-o', '--output', default='scores.tsv', help='output TSV file')
    parser.add_argument('--evalue', type=float, default=None)
    parser.add_argument('--word_size', type=int, default=None)
    parser.add_argument('--task', default=None)
    parser.add_argument('--nuclease', choices=['custom', 'cas9', 'cas12', 'cas12a', 'cas12b',
                                               'cas13', 'cas14a', 'tnpb'],
                        default='cas9', help='Nuclease system used for scoring')
    parser.add_argument('--tnpb-subtype', choices=['isdra2', 'other', 'unknown'],
                        default='unknown', help='TnpB subtype used when nuclease=tnpb')
    parser.add_argument('--left-nuclease', choices=['custom', 'cas9', 'cas12', 'cas12a', 'cas12b',
                                                    'cas13', 'cas14a', 'tnpb'], default=None,
                        help='Nuclease for the left side (defaults to --nuclease)')
    parser.add_argument('--right-nuclease', choices=['custom', 'cas9', 'cas12', 'cas12a', 'cas12b',
                                                     'cas13', 'cas14a', 'tnpb'], default=None,
                        help='Nuclease for the right side (defaults to --nuclease)')
    parser.add_argument('--left-tnpb-subtype', choices=['isdra2', 'other', 'unknown'], default=None)
    parser.add_argument('--right-tnpb-subtype', choices=['isdra2', 'other', 'unknown'], default=None)
    parser.add_argument('--left-preset', default=None)
    parser.add_argument('--right-preset', default=None)
    parser.add_argument('--reference-only-model', choices=['none', 'cas9', 'teep'],
                        default='none', help='Force an unvalidated model for unsupported systems')
    parser.add_argument('--left-reference-only-model', choices=['none', 'cas9', 'teep'],
                        default=None, help='Reference-only model for the left side')
    parser.add_argument('--right-reference-only-model', choices=['none', 'cas9', 'teep'],
                        default=None, help='Reference-only model for the right side')
    parser.add_argument('--on-target-model', default='cropsr',
                        help='On-target model(s), comma-separated for multiple selections')
    parser.add_argument('--off-target-model', default='rules',
                        help='Off-target model(s), comma-separated for multiple selections')
    parser.add_argument('--left-off-target-model', default=None,
                        help='Off-target model(s) for the left side, comma-separated')
    parser.add_argument('--right-off-target-model', default=None,
                        help='Off-target model(s) for the right side, comma-separated')
    parser.add_argument('--left-on-target-model', default=None,
                        help='On-target model(s) for the left side, comma-separated')
    parser.add_argument('--right-on-target-model', default=None,
                        help='On-target model(s) for the right side, comma-separated')
    parser.add_argument('--max-mismatch', type=int, choices=[0, 1, 2, 3, 4], default=4)
    parser.add_argument('--max-bulge', type=int, choices=[0, 1], default=None)
    parser.add_argument('--require-pam', action='store_true')
    parser.add_argument('--pam-motif', default=None)
    parser.add_argument('--left-require-pam', action='store_true', default=None)
    parser.add_argument('--right-require-pam', action='store_true', default=None)
    parser.add_argument('--left-pam-motif', default=None)
    parser.add_argument('--right-pam-motif', default=None)
    parser.add_argument('--left-pam-side', choices=['3prime', '5prime'], default=None)
    parser.add_argument('--right-pam-side', choices=['3prime', '5prime'], default=None)
    parser.add_argument('--seed-mismatch-max', type=int, default=None)
    parser.add_argument('--seed-len', type=int, default=12)
    parser.add_argument('--max-memory-mb', type=int, default=None,
                        help='Explicit process RSS limit in MiB')
    parser.add_argument('--timeout-s', type=float, default=None,
                        help='Wall-clock budget for one indexed search, in '
                             'seconds; default is no timeout')
    parser.add_argument('--repeat-fasta', default=None, help='Repeat sequence FASTA to mask')
    parser.add_argument('--gc-min', type=float, default=40.0)
    parser.add_argument('--gc-max', type=float, default=70.0)
    parser.add_argument('--self-comp-max', type=int, default=4)
    parser.add_argument('--filter-hard', action='store_true')
    parser.add_argument('--crispai', action='store_true',
                        help='Backfill crispAI specificity for Cas9 sides')
    parser.add_argument('--crispai-samples', type=int, default=200)
    parser.add_argument('--crispai-gpu', type=int, default=-1)
    parser.add_argument('--unique-guides', action='store_true')
    parser.add_argument('--top-offtargets', type=int, default=5,
                        help='Write the top N off-targets per unique query to top_offtargets.tsv')
    parser.add_argument('--annotation', default=None,
                        help='NCBI GFF3 annotation file used to annotate candidates')
    parser.add_argument('--xlsx', action='store_true',
                        help='Also write XLSX versions of the main TSV outputs')
    parser.add_argument('--mode', choices=['free', 'preset'], default='free')
    parser.add_argument('--preset', default='custom')
    parser.add_argument('--spacer-len', type=int, default=None)
    parser.add_argument('--seed-start', type=int, default=None)
    parser.add_argument('--seed-end', type=int, default=None)
    parser.add_argument('--target-type', choices=['dna', 'rna', 'ssdna'], default='dna')
    parser.add_argument('--exact-offtarget', action='store_true',
                        help='Use the local exact k-mer search instead of BLAST')
    parser.add_argument('--pam-side', choices=['3prime', '5prime'], default=None)
    parser.add_argument('--seed-mismatch', type=int, default=None)
    args = parser.parse_args()

    left_nuclease = args.left_nuclease or args.nuclease
    right_nuclease = args.right_nuclease or args.nuclease
    left_tnpb = args.left_tnpb_subtype or args.tnpb_subtype
    right_tnpb = args.right_tnpb_subtype or args.tnpb_subtype
    left_at_score_enabled = should_output_at_score(
        args.mode, args.preset, args.left_preset)
    right_at_score_enabled = should_output_at_score(
        args.mode, args.preset, args.right_preset)
    left_otm = args.left_off_target_model or args.off_target_model
    right_otm = args.right_off_target_model or args.off_target_model
    left_on_otm = args.left_on_target_model or args.on_target_model
    right_on_otm = args.right_on_target_model or args.on_target_model
    left_ref = args.left_reference_only_model or args.reference_only_model
    right_ref = args.right_reference_only_model or args.reference_only_model

    preset = get_preset(args.preset if args.mode == 'preset' else 'custom')
    if args.pam_motif is None:
        args.pam_motif = preset.get('pam') or ''
    if args.pam_side is None:
        args.pam_side = preset.get('pam_side') or ''
    if args.mode == 'preset' and preset.get('pam_required') and args.pam_motif:
        args.require_pam = True

    left_pam_motif = args.left_pam_motif if args.left_pam_motif is not None else args.pam_motif
    right_pam_motif = args.right_pam_motif if args.right_pam_motif is not None else args.pam_motif
    left_pam_side = args.left_pam_side if args.left_pam_side is not None else args.pam_side
    right_pam_side = args.right_pam_side if args.right_pam_side is not None else args.pam_side
    left_require = args.left_require_pam if args.left_require_pam is not None else args.require_pam
    right_require = args.right_require_pam if args.right_require_pam is not None else args.require_pam

    input_dir = args.input_dir
    if not os.path.isdir(input_dir):
        print(f"Error: input directory {input_dir} does not exist")
        sys.exit(1)

    # ---- 读取 occurrence_info.tsv ----
    info_path = os.path.join(input_dir, 'occurrence_info.tsv')
    if not os.path.isfile(info_path):
        print(f"Error: cannot find {info_path}")
        sys.exit(2)
    occ_map = {}  # {num: (chrom, y_start, y_end, strand)}
    with open(info_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter='\t')
        for row in reader:
            num = int(row['occurrence'])
            strand = row.get('strand', '+')
            occ_map[num] = (row['chrom'], int(row['y_start']), int(row['y_end']), strand)

    print(f"Loaded occurrence info: {len(occ_map)} Y occurrence sites")
    print("PROGRESS: reading 5", flush=True)

    # ---- 加载 Genome ----
    if not os.path.isfile(args.genome):
        print(f"Error: genome file {args.genome} does not exist")
        sys.exit(2)
    genome, _, temp_genome = load_genome_and_prepare_fasta(args.genome)
    target_genome = None
    target_temp = None
    if args.target_fasta:
        if not os.path.isfile(args.target_fasta):
            print("Error: target FASTA not found: %s" % args.target_fasta)
            sys.exit(2)
        target_genome, _, target_temp = load_genome_and_prepare_fasta(
            args.target_fasta)
        print("Loaded target FASTA: %s records" % len(target_genome.keys()))
    print(f"Loaded genome: {len(genome.keys())} chromosomes/scaffolds")

    annotation_index = None
    if args.annotation and os.path.isfile(args.annotation):
        annotation_index = build_annotation_index(args.annotation)
        print(f"Loaded annotation: {annotation_index.gene_count} genes, "
              f"{annotation_index.transcript_count} transcripts")

    # ---- 构建 Mask gene 屏蔽区间 ----
    exclusion_intervals = {}
    if args.mask:
        if os.path.isfile(args.mask):
            exclusion_intervals = build_exclusion_intervals(args.mask, genome)
            print(f"Masked regions: {len(exclusion_intervals)} records with excluded regions")
    else:
        print(f"Warning: mask gene file {args.mask} does not exist; skipping mask filtering")

    repeat_intervals = {}
    if args.repeat_fasta and os.path.isfile(args.repeat_fasta):
        repeat_intervals = build_exclusion_intervals(args.repeat_fasta, genome)
        print(f"Repeat regions: {sum(len(v) for v in repeat_intervals.values())}")

    print("PROGRESS: reading 10", flush=True)

    # ---- 收集 occurrence 候选 ----
    # per_side[(occurrence, side, qid)] = {sequence, positions}
    # global_seqs[qid] = sequence (????)
    pattern = re.compile(r'^(left|right)_occurrence_(\d+)\.tsv$')
    per_side = {}   # key: (occurrence, side, qid)
    global_seqs = {}  # key: qid
    guide_by_qid = {}  # key: qid
    seq_to_global_qid = {'left': {}, 'right': {}}

    for fname in sorted(os.listdir(input_dir)):
        m = pattern.match(fname)
        if not m:
            continue
        side = m.group(1)
        num = int(m.group(2))
        if num not in occ_map:
            continue
        filepath = os.path.join(input_dir, fname)
        tsv_data = parse_occurrence_tsv(filepath)
        for qid, info in tsv_data.items():
            seq = info['sequence']
            global_qid = seq_to_global_qid[side].get(seq)
            if global_qid is None:
                global_qid = f"{side}_g{len(global_seqs)}"
                seq_to_global_qid[side][seq] = global_qid
                global_seqs[global_qid] = seq
                guide_by_qid[global_qid] = _guide_from_window(
                    seq, info.get('positions', [])
                )
            per_side[(num, side, global_qid)] = info

    unique_count = len(global_seqs)
    total_entries = len(per_side)
    print(f"Collected {total_entries} candidates ({unique_count} unique sequences)")

    if not global_seqs:
        print("No candidate sequences found, exiting")
        sys.exit(0)

    # ---- 按所选 engine 运行 Off-target search ----
    # 自动设置参数
    max_len = max(len(s) for s in global_seqs.values())
    if args.task is None:
        args.task = 'blastn-short' if max_len <= 30 else 'blastn'
    if args.word_size is None:
        args.word_size = 4 if max_len <= 30 else 11
    if args.evalue is None:
        args.evalue = 1000
    print(f"Auto-configured Off-target search parameters: task={args.task}, word_size={args.word_size}, evalue={args.evalue} (max query length={max_len})")

    engine = args.engine or (
        "exact" if args.exact_offtarget else "blast"
    )
    genome_fasta_for_search = (
        temp_genome.name if temp_genome is not None else args.genome
    )
    if (engine == "exact"
            and os.path.getsize(genome_fasta_for_search)
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
            blastdb=args.blast_db or None,
            index_path=args.index_path or None,
            output_dir=os.path.dirname(os.path.abspath(args.output)),
            genome_build=args.genome_build or None,
            extra={
                key: value for key, value in (
                    ('max_memory_mb', args.max_memory_mb),
                    ('timeout_s', args.timeout_s),
                )
                if value is not None
            },
        )
        apply_engine_defaults(engine, params, os.path.getsize(args.genome))
        return params

    left_guides = [
        {"qid": qid, "guide_seq": guide_by_qid.get(qid, global_seqs[qid])}
        for qid in global_seqs
        if qid.startswith("left_")
    ]
    right_guides = [
        {"qid": qid, "guide_seq": guide_by_qid.get(qid, global_seqs[qid])}
        for qid in global_seqs
        if qid.startswith("right_")
    ]

    def report_line(message):
        """Forward engine notes (fallback reasons, progress) to stdout."""
        print(message, flush=True)

    matches = {}
    print(f"PROGRESS: Off-target search ({engine}) 40", flush=True)
    try:
        if left_guides:
            left_matches = run_backend(
                engine, left_guides, genome_fasta_for_search,
                make_search_params(left_pam_motif, left_pam_side, left_require),
                genome=genome,
                progress_callback=print_search_progress,
                log=report_line,
            )
            matches.update(left_matches)
        if right_guides:
            right_matches = run_backend(
                engine, right_guides, genome_fasta_for_search,
                make_search_params(right_pam_motif, right_pam_side, right_require),
                genome=genome,
                progress_callback=print_search_progress,
                log=report_line,
            )
            matches.update(right_matches)
    except RuntimeError as exc:
        print("Off-target search failed: %s" % exc)
        sys.exit(3)

    forbidden_hits_by_qid = defaultdict(list)
    for qid, hits in matches.items():
        seen_loci = set()
        for hit in hits:
            target = hit.get("target")
            start = hit.get("start")
            if target is None or start is None:
                continue
            if not (
                is_in_excluded(target, start, exclusion_intervals)
                or is_in_excluded(target, start, repeat_intervals)
            ):
                continue
            strand = hit.get("strand") or "+"
            locus = "%s:%s:%s" % (target, start, strand)
            if locus in seen_loci:
                continue
            seen_loci.add(locus)
            forbidden_hits_by_qid[qid].append({
                "locus_id": locus,
                "score": None,
                "upper": 1.0,
                "forbidden": True,
                "is_bulge": False,
                "bulge_calibrated": False,
            })
    if repeat_intervals:
        matches = {
            qid: [
                hit for hit in hits
                if not is_in_excluded(
                    hit["target"], hit["start"], repeat_intervals
                )
            ]
            for qid, hits in matches.items()
        }
    if temp_genome is not None:
        os.unlink(temp_genome.name)

    total_hits = sum(len(v) for v in matches.values())
    print(f"Off-target search complete, {total_hits} valid matches")

    print("PROGRESS: Analyzing targets 70", flush=True)

    # ---- 输出 per-side TSV ----
    mm_columns = mismatch_bucket_columns(args.max_mismatch)
    out_fieldnames = [
        'occurrence', 'side',
        'y_chrom', 'y_start', 'y_end', 'y_strand', 'y_seq',
        'qid', 'motif_seq', 'distance',
        'GC-content', 'GC-hint', 'Self-complementarity', 'Self-comp-hint',
        'AT_score',
        'Annotation', 'Nearest-TSS', 'Isoforms', 'Downstream-ATG',
        'nuclease',
        'valid', 'search_complete', 'forbidden_hits',
        'score',
        *OUTPUT_GUIDE_FEATURE_COLUMNS,
        *mm_columns,
        'region_seq'
    ]

    out_rows = []
    bed_rows = []
    filtered_count = 0
    total = len(per_side)
    for idx, ((num, side, qid), info) in enumerate(sorted(per_side.items())):
        if idx % max(1, total // 10) == 0 or idx == total - 1:
            pct = 70 + int(idx / total * 25)
            print(
                f"PROGRESS: Analyzing target {idx + 1}/{total} {pct}",
                flush=True,
            )

        chrom, y_start, y_end, strand = occ_map[num]
        seq = info['sequence']
        positions = info['positions']
        if not positions:
            continue
        pos0 = positions[0]
        motif_strand = pos0[1] if len(pos0) >= 2 else strand
        full_start = pos0[2]
        full_end = pos0[3]
        motif_start = pos0[4] if len(pos0) >= 6 else full_start
        motif_end = pos0[5] if len(pos0) >= 6 else full_end
        guide = guide_by_qid.get(qid, seq)
        guide_seq = (
            reverse_complement(guide)
            if motif_strand == 'minus' else guide
        )
        at_score_enabled = (
            left_at_score_enabled if side == 'left' else right_at_score_enabled
        )
        at_score = (
            _at_score_from_occurrence(seq, positions)
            if at_score_enabled else ""
        )

        # ??
        if side == 'left':
            distance = motif_start - y_end if strand == '-' else y_start - motif_end
        else:
            distance = y_start - motif_end if strand == '-' else motif_start - y_end

        # GC / IR
        if seq:
            gc = (seq.count('G') + seq.count('C')) / len(seq) * 100.0
            ir = max_inverted_repeat_len(seq)
        else:
            gc = 0.0
            ir = 0

        hints = filter_hints(gc, ir, args.gc_min, args.gc_max, args.self_comp_max)
        if not passes_filter(hints, args.filter_hard):
            filtered_count += 1
            continue

        ann = None
        tss = None
        atg_text = ""
        if annotation_index is not None:
            ann = annotate_interval(annotation_index, chrom, full_start, full_end)
            tss = nearest_tss(annotation_index, chrom, full_start, full_end)
            atg = find_downstream_atg(genome, chrom, full_start, full_end,
                                      strand, window=500)
            if atg is not None:
                if strand == "+":
                    atg_text = f"{atg - full_end}bp"
                else:
                    atg_text = f"{full_start - atg}bp"

        # 获取 Off-target search 匹配
        match_list = [
            match for match in matches.get(qid, [])
            if int(match.get("mismatch", 0)) <= args.max_mismatch
        ]
        score, mm_counts = compute_match_score(match_list, exclusion_intervals)
        off_pairs = []
        side_pam_side = left_pam_side if side == 'left' else right_pam_side
        for m in match_list:
            if is_in_excluded(m["target"], m["start"], exclusion_intervals):
                continue
            if has_alignment(m):
                off_pairs.append(orient_rich_hit(m, motif_strand))
                continue
            raw_off, raw_pam = _fetch_guide_and_pam(
                genome, m["target"], m["start"], len(guide),
                m.get("strand", "+"), side_pam_side,
            )
            if raw_off and len(raw_off) >= len(guide):
                off_seq, pam_seq = orient_off_target_pair(
                    raw_off, raw_pam, m.get("strand", "+"), motif_strand
                )
                off_pairs.append((off_seq, pam_seq))
        side_nuclease = left_nuclease if side == 'left' else right_nuclease
        side_tnpb = left_tnpb if side == 'left' else right_tnpb
        side_otm = left_otm if side == 'left' else right_otm
        side_on_otm = left_on_otm if side == 'left' else right_on_otm
        side_ref = left_ref if side == 'left' else right_ref
        guide_scores = compute_guide_scores(guide_seq, off_pairs,
                                            nuclease=side_nuclease,
                                            tnpb_subtype=side_tnpb,
                                            reference_only_model=side_ref,
                                            on_target_model=side_on_otm,
                                            off_target_model=side_otm,
                                            preset_key=args.preset if args.mode == "preset" else "custom",
                                            seed_start=args.seed_start,
                                            seed_end=args.seed_end,
                                            target_type=args.target_type)

        # Y ??
        display_genome = target_genome if target_genome is not None else genome
        y_seq = fetch_sequence(display_genome, chrom, y_start, y_end) or ""
        if strand == '-':
            y_seq = reverse_complement(y_seq)

        # region_seq?Y ?????
        region_seq = ""
        rs = min(full_start, y_start)
        region_end = max(full_end, y_end)
        full = fetch_sequence(display_genome, chrom, rs, region_end)
        if full:
            y_off_s = y_start - rs
            y_off_e = y_end - rs
            if 0 <= y_off_s < y_off_e <= len(full):
                region_seq = (full[:y_off_s] +
                              full[y_off_s:y_off_e].lower() +
                              full[y_off_e:])
            else:
                region_seq = full

        mm_out = mismatch_bucket_values(mm_counts, args.max_mismatch)
        row_out = {
            'occurrence': num,
            'side': side,
            'y_chrom': chrom,
            'y_start': y_start,
            'y_end': y_end,
            'y_strand': strand,
            'y_seq': y_seq,
            'qid': qid,
            'motif_seq': seq,
            'distance': distance,
            'GC-content': f"{gc:.2f}",
            'GC-hint': hints['gc_hint'],
            'Self-complementarity': ir,
            'Self-comp-hint': hints['self_comp_hint'],
            'AT_score': at_score,
            'Annotation': format_annotation(ann),
            'Nearest-TSS': format_tss(tss),
            'Isoforms': ann['isoforms'] if ann else '',
            'Downstream-ATG': atg_text,
            'nuclease': side_nuclease,
            'valid': bool(guide_seq),
            'search_complete': True,
            'forbidden_hits': json.dumps(
                forbidden_hits_by_qid.get(qid, []),
                separators=(",", ":"),
            ),
            'guide_seq': guide_seq,
            'off_target_specificity': f"{guide_scores['off_target_specificity']:.6f}",
            'off_target_model': guide_scores['off_target_model'],
            'on_target_score': f"{guide_scores['on_target_score']:.6f}",
            'on_target_model': guide_scores['on_target_model'],
            'reference_only': str(guide_scores['reference_only']),
            'reference_note': guide_scores['reference_note'],
            'score': f"{score:.2f}",
            **dict(zip(mm_columns, mm_out)),
            'region_seq': region_seq
        }
        apply_guide_feature_columns(row_out, guide_scores)
        out_rows.append(row_out)
        bed_rows.append((chrom, full_start, full_end, f"{num}_{side}_{qid}",
                         1.0 / (
                             1.0 + max(
                                 0.0,
                                 1.0 / max(
                                     float(
                                         guide_scores[
                                             "off_target_specificity"
                                         ]
                                     ),
                                     1e-12,
                                 ) - 1.0,
                             )
                         ), strand))

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
            out_dir = os.path.dirname(os.path.abspath(args.output))
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
                side_rows = {}
                for idx, row in enumerate(out_rows):
                    if row.get("side") != side:
                        continue
                    sgrna = make_sgrna((row.get("guide_seq") or "").strip())
                    if sgrna:
                        side_rows.setdefault(sgrna, []).append(idx)
                if not side_rows:
                    continue
                mapping = run_crispai_aggregate(
                    side_rows.keys(), out_dir,
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
                        row = out_rows[i]
                        row["crispai_off_target"] = specificity
                        row["crispai_aggregate_score"] = aggregate
                        row["off_target_specificity_crispai"] = specificity
                        row["off_target_model_crispai"] = "crispai"
                        if as_primary:
                            row["off_target_specificity"] = f"{specificity:.6f}"
                            row["off_target_model"] = "crispai"
                        filled += 1
                print("crispAI backfilled %s-side %d/%d candidates (%s)"
                      % (side, filled, len(out_rows),
                         "as primary score" if as_primary else "additional columns only"))

    out_fieldnames = nonempty_columns(out_rows, out_fieldnames)
    with open(args.output, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=out_fieldnames, delimiter='\t', extrasaction='ignore')
        writer.writeheader()
        writer.writerows(out_rows)

    print(f"Wrote {len(out_rows)} rows to {args.output}")
    print("PROGRESS: done 100", flush=True)

    if args.unique_guides:
        unique_by_seq = {}
        for row in out_rows:
            seq = row['motif_seq']
            if seq not in unique_by_seq:
                unique_by_seq[seq] = [row, 0]
            unique_by_seq[seq][1] += 1
        unique_rows = []
        for row, count in unique_by_seq.values():
            unique_item = dict(row)
            unique_item['occurrence_count'] = count
            unique_rows.append(unique_item)
        rank_rows(unique_rows, combined_key="off_target_specificity")
        unique_dir = os.path.dirname(os.path.abspath(args.output))
        unique_path = os.path.join(unique_dir, "unique_guides.tsv")
        unique_fields = [
            'rank', 'occurrence_count', 'occurrence', 'side', 'y_chrom',
            'y_start', 'y_end', 'y_strand', 'qid', 'motif_seq', 'distance',
            'GC-content', 'GC-hint', 'Self-complementarity', 'Self-comp-hint',
            'AT_score',
            'Annotation', 'Nearest-TSS', 'Isoforms', 'Downstream-ATG',
            'nuclease', 'score',
            *OUTPUT_GUIDE_FEATURE_COLUMNS,
            *mm_columns,
        ]
        unique_fields = nonempty_columns(unique_rows, unique_fields)
        with open(unique_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=unique_fields, delimiter='\t', extrasaction='ignore')
            writer.writeheader()
            writer.writerows(unique_rows)
        print(f"Unique guides written to {unique_path}")

    top_rows = []
    for qid, match_list in matches.items():
        valid = [m for m in match_list
                 if int(m.get("mismatch", 0)) <= args.max_mismatch
                 and not is_in_excluded(
                     m["target"], m["start"], exclusion_intervals)]
        valid.sort(key=lambda m: (m["mismatch"], -float(m.get("bitscore", 0)),
                                  m["target"], m["start"]))
        for rank, m in enumerate(valid[:args.top_offtargets], start=1):
            query_len = max(1, len(guide_by_qid.get(qid, global_seqs.get(qid, ""))))
            ann = (annotate_interval(annotation_index, m["target"], m["start"],
                                     m["start"] + query_len)
                   if annotation_index is not None else None)
            top_rows.append({
                "qid": qid,
                "rank": rank,
                "target": m["target"],
                "start": m["start"],
                "mismatch": m["mismatch"],
                "bitscore": m.get("bitscore", ""),
                "annotation": format_annotation(ann),
            })
    top_file = os.path.join(os.path.dirname(os.path.abspath(args.output)), "top_offtargets.tsv")
    os.makedirs(os.path.dirname(top_file), exist_ok=True)
    with open(top_file, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=["qid", "rank", "target", "start", "mismatch", "bitscore", "annotation"],
                                delimiter='\t')
        writer.writeheader()
        writer.writerows(top_rows)
    print(f"Top off-targets written to {top_file}")

    bed_file = os.path.splitext(args.output)[0] + ".bed"
    os.makedirs(os.path.dirname(os.path.abspath(bed_file)), exist_ok=True)
    with open(bed_file, 'w', encoding='utf-8', newline='') as f:
        for chrom, start, end, name, score, strand in bed_rows:
            strand_bed = "+" if strand == "+" else "-"
            f.write(f"{chrom}\t{start}\t{end}\t{name}\t{score:.6f}\t{strand_bed}\n")
    print(f"BED written to {bed_file}")

    if args.xlsx:
        try:
            tsv_to_xlsx(args.output, os.path.splitext(args.output)[0] + ".xlsx")
            unique_path = os.path.join(os.path.dirname(os.path.abspath(args.output)),
                                       "unique_guides.tsv")
            if os.path.isfile(unique_path):
                tsv_to_xlsx(unique_path, os.path.join(os.path.dirname(unique_path),
                                                      "unique_guides.xlsx"))
            top_path = os.path.join(os.path.dirname(os.path.abspath(args.output)),
                                    "top_offtargets.tsv")
            if os.path.isfile(top_path):
                tsv_to_xlsx(top_path, os.path.join(os.path.dirname(top_path),
                                                   "top_offtargets.xlsx"))
            print("XLSX outputs written")
        except RuntimeError as exc:
            print(f"Warning: {exc}")


if __name__ == '__main__':
    main()
