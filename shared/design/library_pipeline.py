#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""One-command guide library pipeline for BED-like target regions.

DEPRECATED：本管线已废弃，不再开发也不再维护。保留代码只是为了让调用它的入口
（`main.py` 的 Library 标签页、`unified_gui.py`、`webapp/`）继续可用、不影响其它
功能；不要在这里修 bug、补测试或做重构。

The pipeline designs guides, runs exact or BLAST off-target search, scores the
library with the shared scoring rules, and writes TSV/BED/summary files.
"""

import argparse
import csv
import json
import os
import sys
import tempfile

try:
    from Bio import SeqIO
except ImportError:
    SeqIO = None

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from design.guide_design import find_guides, filter_guides
from design.library_utils import (load_regions, extract_region_sequences,
                                  deduplicate_guides, library_summary,
                                  parse_region_description)
from design.system_presets import (
    get_preset, normalize_pam_mode, pam_motif_for_mode,
)
from output.output_columns import nonempty_columns
from scoring.scoring import (
    MODEL_SCORE_COLUMNS,
    compute_guide_scores,
    filter_hints,
    passes_filter,
    rank_rows,
)

from search.blast_utils import (check_blast_installed, ensure_blastdb,
                         load_genome_and_prepare_fasta, fetch_sequence,
                         reverse_complement, is_in_excluded,
                         build_exclusion_intervals,
                         max_inverted_repeat_len)
from search.blast_utils import run_blastn as shared_run_blastn
from design.library_preflight import ENGINE_CHOICES, preflight_library
from search.offtarget_backend import (
    SearchParameterError, SearchParams, apply_engine_defaults, get_backend,
    run_backend, print_search_progress, resolve_engine,
    validate_search_params,
)
from search.alignment import best_alignment
from search.exact_offtarget import _alignment_to_hit
from search.seed_plan import build_seed_plan


def _pam_sequence(genome, target, target_start, target_end, strand,
                  pam, pam_side):
    if not pam:
        return ""
    pam_len = len(pam)
    if strand == "+":
        fetch_start, fetch_end = (
            (target_start - pam_len, target_start)
            if pam_side == "5prime"
            else (target_end, target_end + pam_len)
        )
    else:
        fetch_start, fetch_end = (
            (target_end, target_end + pam_len)
            if pam_side == "5prime"
            else (target_start - pam_len, target_start)
        )
    sequence = fetch_sequence(
        genome, target, fetch_start, fetch_end) or ""
    if strand == "-":
        sequence = reverse_complement(sequence)
    return sequence


def _scoring_hits(matches, genome, guide_seq, exclusion_intervals,
                  pam=None, pam_side="3prime"):
    """Return rich scoring hits without collapsing gapped alignments."""
    hits = []
    skipped = 0
    for match in matches:
        target = match["target"]
        start = int(match.get("target_start", match["start"]))
        strand = match.get("strand", "+")
        if is_in_excluded(target, start, exclusion_intervals):
            skipped += 1
            continue
        guide_len = len(guide_seq)
        target_end = int(match.get("target_end", start + guide_len))
        aligned_guide = match.get("aligned_guide") or ""
        aligned_target = match.get("aligned_target") or ""
        if not aligned_guide or not aligned_target:
            probe = guide_seq if strand == "+" else reverse_complement(guide_seq)
            context = 2
            fetch_start = max(0, start - context)
            fetch_end = start + guide_len + context + 2
            window = fetch_sequence(genome, target, fetch_start, fetch_end)
            if not window:
                skipped += 1
                continue
            alignment = best_alignment(
                window, probe, start - fetch_start,
                int(match.get("indel") or 0),
                max_mismatch=int(match.get("mismatch") or 0),
            )
            if alignment is None:
                skipped += 1
                continue
            enriched = _alignment_to_hit(
                alignment, target, fetch_start, strand)
            for key, value in match.items():
                enriched.setdefault(key, value)
            match = enriched
            start = int(match.get("target_start", start))
            target_end = int(match.get("target_end", target_end))
            aligned_guide = match.get("aligned_guide") or ""
            aligned_target = match.get("aligned_target") or ""
        rich = dict(match)
        rich["aligned_guide"] = aligned_guide
        rich["aligned_target"] = aligned_target
        rich["target_start"] = start
        rich["target_end"] = target_end
        rich["pam"] = (
            match.get("pam")
            or _pam_sequence(
                genome, target, start, target_end, strand, pam, pam_side)
        )
        hits.append(rich)
    return hits, skipped


def _exact_search(guides, genome_path, args):
    from search.exact_offtarget import search_guides
    seed_mm = args.seed_mismatch
    if seed_mm is None:
        seed_mm = 0 if args.seed_mismatch_max is not None else 1
    return search_guides(
        guides, genome_path,
        max_mismatch=args.max_mismatch,
        max_bulge=args.max_bulge or 0,
        seed_len=args.seed_len,
        seed_mm=seed_mm,
        pam=args.pam if args.require_pam else None,
        pam_side=args.pam_side,
    )


def _blast_search(guides, genome_fasta, db_prefix, genome, args):
    if db_prefix:
        db_name = db_prefix
    else:
        db_name = ensure_blastdb(genome_fasta, output_dir=args.output_dir)
    temp_query = tempfile.NamedTemporaryFile(
        mode="w", suffix=".fa", delete=False, encoding="utf-8")
    for guide in guides:
        temp_query.write(">%s\n%s\n" % (guide["qid"], guide["guide_seq"]))
    temp_query.close()
    try:
        return shared_run_blastn(
            temp_query.name, db_name,
            task="blastn-short" if max(len(g["guide_seq"]) for g in guides) <= 30
            else "blastn",
            word_size=4,
            evalue=1000,
            max_mismatch=args.max_mismatch,
            max_bulge=args.max_bulge or 0,
            require_pam=args.require_pam,
            pam_motif=args.pam,
            seed_mismatch_max=args.seed_mismatch_max,
            seed_len=args.seed_len,
            genome=genome,
        )
    finally:
        try:
            os.unlink(temp_query.name)
        except OSError:
            pass


def enforce_preset_pam_requirement(args, preset):
    """Preset systems with a required PAM always hard-filter off-targets."""
    if args.mode == "preset" and preset.get("pam_required") and args.pam:
        args.require_pam = True
    return args


def main():
    parser = argparse.ArgumentParser(
        description="Design, search and score a guide library from BED regions")
    parser.add_argument("regions", nargs="?", default=None,
                        help="BED-like TSV: seqid, start0, end0, name "
                             "(not needed with --fasta)")
    parser.add_argument("genome", help="Genome FASTA")
    parser.add_argument("output_dir", help="Output directory")
    parser.add_argument("--mode", choices=["free", "preset"], default="preset")
    parser.add_argument("--preset", default="cas9")
    parser.add_argument("--spacer-len", type=int, default=None)
    parser.add_argument("--pam", default=None)
    parser.add_argument("--pam-side", choices=["3prime", "5prime"], default=None)
    parser.add_argument(
        "--pam-mode",
        choices=["strict_ngg", "guidescan2_nrg", "custom"],
        default=None,
        help="Cas9 PAM compatibility mode; NRG includes NGG and NAG")
    parser.add_argument("--motif", default="")
    parser.add_argument("--gc-min", type=float, default=None)
    parser.add_argument("--gc-max", type=float, default=None)
    parser.add_argument("--min-overlap", type=int, default=1)
    parser.add_argument("--pad", type=int, default=0)
    parser.add_argument("--max-regions", type=int, default=None)
    parser.add_argument("--fasta", action="append", default=None,
                        help="Input FASTA file(s); design guides directly "
                             "from each sequence record")
    parser.add_argument("--queries-tsv", default=None,
                        help="Motif query TSV (query_seq/sequence column) "
                             "to design guides from")
    parser.add_argument("--no-reverse", action="store_true")
    parser.add_argument("--search", choices=["exact", "blast", "auto"],
                        default="auto")
    parser.add_argument("--engine", choices=ENGINE_CHOICES,
                        default=None,
                        help="Off-target search engine (default: use --search)")
    parser.add_argument("--genome-build", default=None,
                        help="Genome build name for GGGenome, e.g. hg38")
    parser.add_argument("--blastdb", default="")
    parser.add_argument("--index-path", default="",
                        help="Reusable local genome index prefix "
                             "(.ggi/.json); built automatically when missing")
    parser.add_argument("--index-k", type=int, default=None,
                        help="k-mer seed size for the local genome index")
    cache_group = parser.add_mutually_exclusive_group()
    cache_group.add_argument(
        "--cache-genome", dest="cache_genome", action="store_true",
        default=None,
        help="Load the FASTA into memory for indexed searches")
    cache_group.add_argument(
        "--no-cache-genome", dest="cache_genome", action="store_false",
        help="Keep random-access FASTA reads during indexed searches")
    parser.add_argument(
        "--threads", type=int, default=None,
        help="blastn/native threads (default: auto up to 32)")
    parser.add_argument("--max-mismatch", type=int, choices=[0, 1, 2, 3, 4],
                        default=4)
    parser.add_argument(
        "--max-bulge", type=int, choices=[0, 1], default=None,
        help="Maximum RNA/DNA bulge events (default: 1 for exact/indexed, "
             "0 for mismatch-only engines)")
    parser.add_argument("--require-pam", action="store_true")
    parser.add_argument("--seed-mismatch-max", type=int, default=None)
    parser.add_argument("--seed-len", type=int, default=10)
    parser.add_argument("--seed-mismatch", type=int, default=None)
    parser.add_argument(
        "--max-memory-mb", type=int, default=None,
        help="Explicit process RSS limit in MiB; omitted or 0 is unlimited")
    parser.add_argument("--nuclease", default="cas9")
    parser.add_argument("--tnpb-subtype", default="unknown")
    parser.add_argument("--reference-only-model", default="none")
    parser.add_argument(
        "--on-target-model", default="cropsr",
        help="On-target model(s), comma-separated for multiple selections")
    parser.add_argument(
        "--off-target-model", default="rules",
        help="Off-target model(s), comma-separated for multiple selections")
    parser.add_argument("--crispai", action="store_true",
                        help="Also compute and write crispAI columns even when it is not the primary off-target model")
    parser.add_argument("--annotation", default=None,
                        help="NCBI GFF3 annotation file used to annotate "
                             "designed guides")
    parser.add_argument("--direct-repeat", default=None,
                        help="Cas13 direct repeat sequence (RNA/U or DNA/T)")
    parser.add_argument("--target-rna", default=None,
                        help="Target RNA sequence for accessibility and "
                             "structure-perturbation scoring")
    parser.add_argument("--tss-distance", type=float, default=None,
                        help="Signed distance from guide site to TSS")
    parser.add_argument("--filter-hard", action="store_true")
    parser.add_argument("--self-comp-max", type=int, default=4)
    parser.add_argument("--preflight-only", action="store_true",
                        help="Check configuration and exit without running")
    parser.add_argument(
        "--trust-existing-blastdb", action="store_true",
        help="Reuse an existing BLAST db without validating its source "
             "manifest (dangerous; prints a warning)")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    preset = get_preset(args.preset if args.mode == "preset" else "custom")
    spacer_len = args.spacer_len if args.spacer_len is not None else preset.get("spacer_len")
    pam_mode = args.pam_mode
    if pam_mode is None:
        if args.pam:
            pam_mode = normalize_pam_mode(None, args.pam)
        elif args.mode == "preset":
            pam_mode = preset.get("pam_mode") or normalize_pam_mode(
                None, preset.get("pam"))
        else:
            pam_mode = normalize_pam_mode(None)
    if args.pam_mode in ("strict_ngg", "guidescan2_nrg"):
        pam = pam_motif_for_mode(
            args.pam_mode, args.pam or preset.get("pam") or "")
    elif args.pam is not None:
        pam = args.pam
    elif args.mode == "preset":
        pam = pam_motif_for_mode(pam_mode, preset.get("pam") or "")
        if not preset.get("pam_required"):
            pam = preset.get("pam") or None
    else:
        pam = pam_motif_for_mode(pam_mode) or None
    pam_side = args.pam_side or preset.get("pam_side") or "3prime"
    if spacer_len is None:
        spacer_len = 20
    if pam is None and args.mode != "preset":
        pam = "GG"
    args.pam = pam
    args.pam_mode = pam_mode
    args.pam_side = pam_side
    enforce_preset_pam_requirement(args, preset)

    params = SearchParams.from_args(args)
    params.max_bulge_explicit = args.max_bulge is not None
    requested_engine = args.engine or args.search
    genome_size = (
        os.path.getsize(args.genome)
        if os.path.isfile(args.genome) else None
    )
    apply_engine_defaults(requested_engine, params, genome_size)
    try:
        engine = resolve_engine(
            requested_engine, params, genome_size=genome_size)
        validate_search_params(engine, params)
    except SearchParameterError as exc:
        print("Error: %s" % exc)
        sys.exit(3)
    errors, warnings = preflight_library(
        engine,
        genome=args.genome,
        index_path=args.index_path,
        blastdb=args.blastdb,
        on_target_model=args.on_target_model,
        off_target_model=args.off_target_model,
        search_params=params,
    )
    for warning in warnings:
        print("PREFLIGHT_WARN: %s" % warning)
    if errors:
        for error in errors:
            print("Error: %s" % error)
        print("Preflight failed; fix the errors above and retry.")
        sys.exit(3)
    if args.preflight_only:
        print("Preflight OK: engine=%s genome=%s" % (engine, args.genome))
        sys.exit(0)

    fasta_inputs = list(args.fasta or [])
    if args.queries_tsv:
        from design.library_utils import queries_to_fasta
        fasta_path = os.path.join(args.output_dir, "input_queries.fa")
        try:
            count = queries_to_fasta(args.queries_tsv, fasta_path)
        except Exception as exc:
            print("Error: cannot read query TSV: %s" % exc)
            sys.exit(2)
        print("Loaded %d query sequences" % count)
        fasta_inputs.append(fasta_path)
    sequences = []
    regions = []
    fasta_mode = bool(fasta_inputs)
    if fasta_inputs:
        if SeqIO is None:
            print("Error: Biopython is required for --fasta input.")
            sys.exit(2)
        print("PROGRESS: load fasta 5")
        for fasta_path in fasta_inputs:
            if not os.path.isfile(fasta_path):
                print("Error: FASTA file not found: %s" % fasta_path)
                sys.exit(2)
            for record in SeqIO.parse(fasta_path, "fasta"):
                seq = str(record.seq).upper()
                if not seq:
                    continue
                region_info = parse_region_description(record.description)
                sequences.append({
                    "seq_id": record.id,
                    "region": record.id,
                    "start": region_info["start"] if region_info else 0,
                    "end": region_info["end"] if region_info else len(seq),
                    "strand": region_info["strand"] if region_info else "+",
                    "sequence": seq,
                    "genomic_seq_id": (
                        region_info["chrom"] if region_info else record.id),
                    "target_local_start": (
                        region_info["target_start"] if region_info else 0),
                    "region_tagged": region_info is not None,
                })
        if not sequences:
            print("Error: no sequences found in FASTA input.")
            sys.exit(2)
        print("Loaded %d sequences" % len(sequences))
    else:
        if not args.regions:
            print("Error: BED regions file or --fasta input is required.")
            sys.exit(2)
        print("PROGRESS: load regions 5")
        regions = load_regions(args.regions)
        if args.max_regions:
            regions = regions[:args.max_regions]
        if not regions:
            print("Error: no valid regions found.")
            sys.exit(2)
        print(f"Loaded {len(regions)} regions")
        print("PROGRESS: design guides 20")
        sequences = extract_region_sequences(args.genome, regions, pad=args.pad)

    print("PROGRESS: design guides 20")
    all_guides = []
    for seq_info in sequences:
        found = find_guides(
            seq_info["sequence"],
            spacer_len=spacer_len,
            pam=pam,
            pam_side=pam_side,
            motif=args.motif or None,
            allow_reverse=not args.no_reverse,
            seq_id=seq_info["seq_id"],
        )
        for guide in found:
            guide["region"] = seq_info["region"]
            guide["region_start"] = seq_info["start"]
            guide["region_end"] = seq_info["end"]
            guide["preset"] = args.preset
            guide["pam_mode"] = pam_mode
            if fasta_mode and not seq_info.get("region_tagged"):
                guide["source_sequence"] = seq_info["sequence"]
            else:
                target_start = int(seq_info.get("target_local_start", 0) or 0)
                target_len = len(seq_info["sequence"])
                g_start = guide.get("spacer_start", 0)
                g_end = guide.get("spacer_end", 0)
                if guide.get("strand") == "-":
                    local_start = target_start + target_len - g_end
                    local_end = target_start + target_len - g_start
                else:
                    local_start = target_start + g_start
                    local_end = target_start + g_end
                guide["genomic_start"] = seq_info["start"] + local_start
                guide["genomic_end"] = seq_info["start"] + local_end
                guide["genomic_strand"] = guide.get("strand", "+")
                if seq_info.get("region_tagged"):
                    guide["seq_id"] = seq_info.get(
                        "genomic_seq_id", seq_info["seq_id"]
                    )
        all_guides.extend(found)
    all_guides = filter_guides(
        all_guides,
        min_overlap=args.min_overlap if args.motif else 0,
        gc_min=args.gc_min,
        gc_max=args.gc_max,
    )
    unique_guides = deduplicate_guides(all_guides)
    print(f"Designed {len(unique_guides)} unique guides")

    if not unique_guides:
        print("No guides found.")
        sys.exit(0)

    genome, genome_fasta, temp_genome = load_genome_and_prepare_fasta(args.genome)
    exclusion_intervals = {}
    annotation_index = None
    if args.annotation and os.path.isfile(args.annotation):
        from data.candidate_annotation import build_annotation_index
        annotation_index = build_annotation_index(args.annotation)
        print("Loaded annotation: %d genes, %d transcripts" % (
            annotation_index.gene_count,
            annotation_index.transcript_count))

    guides_for_search = []
    for index, guide in enumerate(unique_guides):
        guide["qid"] = "g%d" % index
        guides_for_search.append({
            "qid": guide["qid"],
            "guide_seq": guide["guide_seq"],
        })

    print("PROGRESS: off-target search 45")
    if args.index_k:
        params.extra["k"] = args.index_k
    params.extra["trust_existing_blastdb"] = bool(
        args.trust_existing_blastdb)
    if engine == "indexed" and params.max_bulge > 0:
        guide_lengths = sorted({len(g["guide_seq"]) for g in guides_for_search})
        from search.genome_index import select_index_k, suggest_k
        suggested_k = args.index_k or suggest_k(os.path.getsize(genome_fasta))
        planned_k = select_index_k(
            os.path.getsize(genome_fasta),
            guide_lengths,
            params.max_mismatch,
            params.max_bulge,
            requested_k=args.index_k,
        )
        params.extra["k"] = planned_k
        if planned_k != suggested_k:
            print(
                "indexed seed plan: 自动将 index k 从 %d 调整为 %d，"
                "以支持 max_bulge=%d 和 guide 长度 %s"
                % (
                    suggested_k,
                    planned_k,
                    params.max_bulge,
                    ",".join(map(str, guide_lengths)),
                )
            )
        invalid = [
            length for length in guide_lengths
            if not build_seed_plan(
                length, params.max_mismatch, params.max_bulge,
                planned_k, planned_k,
            ).guaranteed
        ]
        if invalid:
            print(
                "Error: indexed搜索无法为 guide 长度 %s 构造可保证的 "
                "max_bulge=%d seed plan（k=%d）。请使用 --max-bulge 0，"
                "或为小 guide 指定更小的 --index-k（例如 10），"
                "或改用 exact。"
                % (",".join(map(str, invalid)), params.max_bulge, planned_k)
            )
            sys.exit(3)
    def _search_log(message):
        print(message, flush=True)

    try:
        matches = run_backend(
            requested_engine, guides_for_search, genome_fasta, params,
            genome=genome,
            progress_callback=print_search_progress,
            log=_search_log)
    except Exception as exc:
        if getattr(exc, "error_code", "") == "MEMORY_LIMIT_EXCEEDED":
            print("Error: %s" % exc)
            sys.exit(6)
        raise
    run_report = params.extra.get("engine_run_report") or {}
    if engine == "indexed":
        index_report = run_report
        index_report_path = os.path.join(args.output_dir, "index_report.json")
        with open(index_report_path, "w", encoding="utf-8") as handle:
            json.dump(index_report, handle, indent=2, ensure_ascii=False)
        print("Index report: %s" % index_report_path)

    scored = []
    total_scoring = len(unique_guides)
    for guide_idx, guide in enumerate(unique_guides):
        if (
            guide_idx % max(1, total_scoring // 10) == 0
            or guide_idx == total_scoring - 1
        ):
            pct = 70 + int(guide_idx / total_scoring * 29)
            print(
                f"PROGRESS: Analyzing target {guide_idx + 1}/{total_scoring} "
                f"{pct}",
                flush=True,
            )
        qid = guide["qid"]
        scoring_hits, excluded_hits = _scoring_hits(
            matches.get(qid, []), genome, guide["guide_seq"],
            exclusion_intervals, pam=args.pam, pam_side=args.pam_side)
        scores = compute_guide_scores(
            guide["guide_seq"], scoring_hits,
            nuclease=args.nuclease,
            tnpb_subtype=args.tnpb_subtype,
            reference_only_model=args.reference_only_model,
            on_target_model=args.on_target_model,
            off_target_model=args.off_target_model,
            preset_key=args.preset if args.mode == "preset" else "custom",
            target_type=preset.get("target_type", "dna"),
            direct_repeat=args.direct_repeat,
            target_rna=args.target_rna,
            tss_distance=args.tss_distance,
            guide_strand=guide.get("strand"),
            spacer_start=guide.get("spacer_start"),
        )
        scores["search_hits"] = len(matches.get(qid, []))
        scores["scoring_hits_received"] = len(scoring_hits) + excluded_hits
        scores["scoring_hits_excluded"] = excluded_hits
        guide.update(scores)
        rna = guide.get("rna_features") or {}
        for key in ("rna_model", "guide_mfe", "guide_accessibility",
                    "target_accessibility", "dr_spacer_duplex_mfe",
                    "dr_spacer_penalty", "perturbation_mfe", "dr_source"):
            guide.setdefault(key, rna.get(key, ""))
        tnpb = guide.get("tnpb_features") or {}
        for key in ("omega_model", "spacer_len_score",
                    "guide_structure_penalty", "repeat_hairpin_score"):
            guide.setdefault(key, tnpb.get(key, ""))
        source = guide.get("source_sequence")
        if source:
            context_start = max(0, guide.get("spacer_start", 0) - 300)
            context_end = min(
                len(source), guide.get("spacer_end", 0) + 300)
            guide["context_seq"] = source[context_start:context_end]
            guide["context_spacer_start"] = (
                guide.get("spacer_start", 0) - context_start)
            guide["context_spacer_end"] = (
                guide.get("spacer_end", 0) - context_start)
        else:
            context_start = max(0, guide.get("genomic_start", 0) - 300)
            context_end = guide.get("genomic_end", 0) + 300
            guide["context_seq"] = fetch_sequence(
                genome, guide.get("seq_id"), context_start,
                context_end) or ""
            guide["context_spacer_start"] = (
                guide.get("genomic_start", 0) - context_start)
        guide["context_spacer_end"] = (
            guide.get("genomic_end", 0) - context_start)
        guide["annotation"] = ""
        guide["nearest_tss"] = ""
        if annotation_index is not None and not source:
            try:
                from data.candidate_annotation import (
                    annotate_interval, format_annotation, format_tss,
                    nearest_tss)
                start = guide.get("genomic_start", 0)
                end = guide.get("genomic_end", 0)
                ann = annotate_interval(
                    annotation_index, guide.get("seq_id"), start, end)
                tss = nearest_tss(
                    annotation_index, guide.get("seq_id"), start, end)
                guide["annotation"] = format_annotation(ann)
                guide["nearest_tss"] = format_tss(tss)
            except Exception:
                pass
        guide["gc"] = (guide["guide_seq"].count("G") +
                       guide["guide_seq"].count("C")) / len(guide["guide_seq"])
        ir = max_inverted_repeat_len(guide["guide_seq"])
        hints = filter_hints(
            guide["gc"] * 100.0,
            ir,
            args.gc_min or 0.0,
            args.gc_max or 100.0,
            args.self_comp_max,
        )
        if args.filter_hard and not passes_filter(hints, True):
            continue
        scored.append(guide)

    off_models = [
        model.strip().lower()
        for model in str(args.off_target_model or "rules")
        .replace(";", ",").split(",")
        if model.strip()
    ]
    primary_off_model = off_models[0] if off_models else "rules"
    if (("crispai" in off_models or args.crispai)
            and str(args.nuclease or "").lower() in ("cas9", "custom")):
        as_primary = (
            primary_off_model == "crispai"
            or (args.crispai and primary_off_model in ("rules", "auto"))
        )
        try:
            from scoring.crispai_runtime import (
                run_crispai_aggregate, make_sgrna, specificity_from_aggregate)
        except Exception as exc:
            print("crispAI 依赖导入失败: %s" % exc)
        else:
            sgrna_rows = {}
            for i, guide in enumerate(scored):
                sgrna = make_sgrna(
                    (guide.get("guide_seq") or "").strip(),
                    guide.get("pam_seq", "NGG"),
                )
                if sgrna:
                    sgrna_rows.setdefault(sgrna, []).append(i)
            if sgrna_rows:
                mapping = run_crispai_aggregate(
                    sgrna_rows.keys(), args.output_dir)
                if mapping:
                    filled = 0
                    for sgrna, indexes in sgrna_rows.items():
                        aggregate = mapping.get(sgrna)
                        if aggregate is None:
                            continue
                        specificity = specificity_from_aggregate(aggregate)
                        for i in indexes:
                            guide = scored[i]
                            guide["crispai_off_target"] = specificity
                            guide["crispai_aggregate_score"] = aggregate
                            guide["off_target_specificity_crispai"] = specificity
                            guide["off_target_model_crispai"] = "crispai"
                            if as_primary:
                                guide["off_target_specificity"] = specificity
                                guide["off_target_model"] = "crispai"
                            filled += 1
                    print("crispAI 已回填 %d/%d 条 guide（%s）。"
                          % (filled, len(scored),
                             "作为主分" if as_primary else "仅补充列"))
            else:
                print("没有可用的 20nt Cas9 spacer 供 crispAI 评分。")

    rank_rows(scored)
    fields = ["rank", "qid", "region", "seq_id", "strand", "guide_seq",
              "pam_seq", "pam_mode",
              "spacer_start", "spacer_end", "genomic_start", "genomic_end",
              "genomic_strand", "motif_overlap", "gc",
              "crispai_aggregate_score",
              "rna_model", "guide_mfe", "guide_accessibility",
              "target_accessibility", "dr_spacer_duplex_mfe",
              "dr_spacer_penalty", "perturbation_mfe", "dr_source",
              "omega_model", "spacer_len_score",
              "guide_structure_penalty", "repeat_hairpin_score",
              "annotation", "nearest_tss",
              "total_matches", "occurrence_count", "regions",
              "genomic_positions", "search_hits",
              "scoring_hits_received", "scoring_hits_excluded",
              "input_offtargets", "substitution_offtargets",
              "bulge_hits", "scored_bulge_hits", "unscored_bulge_hits",
              "calibration_status", "bulge_score_method"] \
        + list(MODEL_SCORE_COLUMNS)
    for guide in scored:
        guide["total_matches"] = len(matches.get(guide["qid"], []))
        if "occurrence_count" not in guide:
            guide["occurrence_count"] = 1
        if "regions" not in guide:
            guide["regions"] = guide.get("region", "")
        genomic_positions = guide.get("genomic_positions") or []
        guide["genomic_positions"] = (
            json.dumps(genomic_positions) if genomic_positions else "")

    fields = nonempty_columns(scored, fields)
    score_path = os.path.join(args.output_dir, "library_scores.tsv")
    with open(score_path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t",
                                extrasaction="ignore")
        writer.writeheader()
        writer.writerows(scored)

    summary = library_summary(scored)
    summary["region_count"] = len(regions)
    summary["off_target_model"] = scored[0]["off_target_model"] if scored else "none"
    summary["off_target_model_note"] = (
        scored[0].get("off_target_model_note", "") if scored else "")
    summary["rule_source"] = scored[0].get("rule_source", "") if scored else ""
    summary["rule_reference"] = (
        scored[0].get("rule_reference", "") if scored else "")
    summary["subtype_note"] = (
        scored[0].get("subtype_note", "") if scored else "")
    summary["omega_model"] = (
        scored[0].get("omega_model", "") if scored else "")
    summary["off_target_model_note"] = (
        scored[0].get("off_target_model_note", "") if scored else "")
    executed_engine = str(run_report.get("engine_used") or engine)
    hit_engines = {
        str(hit.get("engine"))
        for hits in matches.values() for hit in hits
        if isinstance(hit, dict) and hit.get("engine")
    }
    if len(hit_engines) == 1:
        hit_engine = hit_engines.pop()
        if hit_engine != executed_engine:
            print("Note: the hits came from the %s engine, not %s; "
                  "the summary follows the hits."
                  % (hit_engine, executed_engine))
            executed_engine = hit_engine
    summary["search_mode"] = executed_engine
    summary["engine"] = executed_engine
    summary["requested_engine"] = args.engine or args.search or "auto"
    summary["pam_mode"] = pam_mode
    summary["pam_motif"] = pam
    summary["max_mismatch"] = params.max_mismatch
    summary["max_bulge"] = params.max_bulge
    backend = get_backend(executed_engine)
    summary["engine_capabilities"] = {
        "substitutions": backend.capabilities.substitutions,
        "indels": backend.capabilities.indels,
        "unknown_gap_type": backend.capabilities.unknown_gap_type,
        "pam_sides": list(backend.capabilities.pam_sides),
    }
    summary["bulge_statistics"] = {
        "search_hits": sum(len(hits) for hits in matches.values()),
        "scoring_input_offtargets": sum(
            int(row.get("input_offtargets") or 0) for row in scored),
        "scored_bulge_hits": sum(
            int(row.get("scored_bulge_hits") or 0) for row in scored),
        "unscored_bulge_hits": sum(
            int(row.get("unscored_bulge_hits") or 0) for row in scored),
    }
    if fasta_mode:
        summary["note"] = (
            "FASTA 输入不映射回基因组坐标，annotation/nearest_tss 为空；"
            "需要注释列请使用 BED 区域输入。")
        print("PREFLIGHT_WARN: %s" % summary["note"])
    summary_path = os.path.join(args.output_dir, "library_summary.json")
    with open(summary_path, "w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, ensure_ascii=False)

    top_rows = []
    for qid in sorted(matches):
        hit_list = sorted(
            matches[qid],
            key=lambda hit: (hit.get("mismatch", 0),
                             -float(hit.get("bitscore") or 0.0),
                             hit.get("target", ""),
                             int(hit.get("start", 0))))
        for rank, hit in enumerate(hit_list[:5], start=1):
            hit_start = int(hit.get("target_start", hit["start"]))
            hit_end = int(
                hit.get("target_end", hit_start + len(hit.get("guide", ""))))
            hit_pam = hit.get("pam") or _pam_sequence(
                genome, hit["target"], hit_start, hit_end,
                hit.get("strand", "+"), args.pam, args.pam_side)
            top_rows.append({
                "qid": qid,
                "rank": rank,
                "guide": hit.get("guide", ""),
                "target": hit["target"],
                "start": hit["start"],
                "strand": hit.get("strand", "+"),
                "mismatch": hit.get("mismatch", ""),
                "indel": hit.get("indel", ""),
                "rna_bulges": hit.get("rna_bulges", ""),
                "dna_bulges": hit.get("dna_bulges", ""),
                "pam": hit_pam,
                "cigar": hit.get("cigar", ""),
                "target_start": hit_start,
                "target_end": hit_end,
                "bitscore": hit.get("bitscore", ""),
                "engine": hit.get("engine", engine),
            })
    top_path = os.path.join(args.output_dir, "top_offtargets.tsv")
    with open(top_path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "qid", "rank", "guide", "target", "start", "strand",
            "mismatch", "indel", "rna_bulges", "dna_bulges", "pam",
            "cigar", "target_start", "target_end", "bitscore", "engine"],
            delimiter="\t")
        writer.writeheader()
        writer.writerows(top_rows)

    bed_path = os.path.join(args.output_dir, "library_scores.bed")
    with open(bed_path, "w", encoding="utf-8", newline="") as handle:
        for guide in scored:
            strand = "+" if guide["strand"] == "+" else "-"
            bed_score = guide.get("off_target_specificity")
            if bed_score is None or bed_score == "":
                bed_score = guide.get("off_target_specificity", 0.0)
            handle.write("%s\t%d\t%d\t%s\t%.6f\t%s\n" % (
                guide["seq_id"],
                guide.get("genomic_start", 0),
                guide.get("genomic_end", 0),
                guide.get("qid", ""),
                bed_score,
                strand,
            ))

    if temp_genome is not None:
        try:
            os.unlink(temp_genome.name)
        except OSError:
            pass
    print("Library summary: %s" % summary)
    print("PROGRESS: complete 100")


if __name__ == "__main__":
    main()
