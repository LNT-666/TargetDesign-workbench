#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import subprocess
import tempfile
import json
import csv
import io
import argparse
import time
import re
from collections import defaultdict
from Bio import SeqIO
from Bio.Seq import Seq

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "shared"))
from search.blast_utils import (ensure_blastdb, load_genome_and_prepare_fasta,
                                reverse_complement, build_exclusion_intervals,
                                is_in_excluded, queries_embed_pam)
from search.blast_utils import run_blastn as shared_run_blastn
from search.offtarget_backend import (
    ENGINE_FALLBACK_ENV, MAX_EXACT_GENOME_BYTES, PYTHON_FALLBACK_ENV,
    SearchParameterError,
    SearchParams, apply_engine_defaults, ask_python_fallback_on_stdin,
    print_search_progress, resolve_engine, run_backend,
    validate_search_params,
)

# 强制刷新输出的辅助函数
def log(msg):
    print(msg)
    sys.stdout.flush()



def make_python_fallback_confirm():
    """Return a callback that asks before degrading to the Python search."""

    def confirm(reason):
        log("WARNING: the native off-target engine is unavailable; the "
            "indexed search would degrade to the pure-Python implementation.")
        log("Python fallback reason: %s" % reason)
        prompt = ""
        try:
            interactive = sys.stdin is not None and sys.stdin.isatty()
        except (AttributeError, ValueError):
            interactive = False
        if interactive:
            prompt = ("Continue with the pure-Python implementation? "
                      "This can take hours on a whole genome. [y/N] ")
        approved = ask_python_fallback_on_stdin(reason, prompt=prompt)
        log("Python fallback %s by user."
            % ("approved" if approved else "declined"))
        return approved

    return confirm


def build_search_extra(args):
    """Build SearchParams.extra, including the Python fallback policy."""
    extra = {}
    if args.max_memory_mb is not None:
        extra["max_memory_mb"] = args.max_memory_mb
    if getattr(args, "timeout_s", None):
        extra["timeout_s"] = float(args.timeout_s)
    policy = args.python_fallback or os.environ.get(PYTHON_FALLBACK_ENV) \
        or "ask"
    extra["python_fallback"] = policy
    extra["python_fallback_confirm"] = make_python_fallback_confirm()
    engine_policy = getattr(args, "engine_fallback", None) \
        or os.environ.get(ENGINE_FALLBACK_ENV) or "ask"
    extra["engine_fallback"] = engine_policy
    return extra

# ---------- Off-target search 相关 ----------
def check_blast_installed():
    for cmd in ["blastn", "makeblastdb"]:
        try:
            subprocess.run([cmd, "-h"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except FileNotFoundError:
            log(f"错误：未找到 {cmd}，请安装 NCBI BLAST+。")
            sys.exit(3)
def run_blastn(query_fasta, db_name, evalue, word_size, task, genome=None,
               max_mismatch=None, require_pam=False, pam_motif="GG",
               seed_mismatch_max=None, seed_len=12, repeat_intervals=None,
               pam_side="3prime", max_bulge=0):
    return {
        qid: [
            (m["target"], m["start"], m["mismatch"],
             m.get("strand", "+"))
            for m in match_list
        ]
        for qid, match_list in shared_run_blastn(
            query_fasta, db_name, task=task, word_size=word_size, evalue=evalue,
            max_mismatch=max_mismatch, max_bulge=max_bulge,
            require_pam=require_pam,
            pam_motif=pam_motif, seed_mismatch_max=seed_mismatch_max,
            seed_len=seed_len, genome=genome, repeat_intervals=repeat_intervals,
            pam_side=pam_side
        ).items()
    }


def read_tsv_and_get_metadata(tsv_file):
    with open(tsv_file, 'r') as f:
        lines = f.readlines()
    if not lines:
        raise ValueError("TSV 文件为空")
    first = lines[0].strip()
    metadata = {}
    start = 0
    if first.startswith('#'):
        parts = first[1:].split()
        for part in parts:
            if '=' in part:
                k, v = part.split('=', 1)
                metadata[k] = v
        start = 1
    return metadata, lines[start:]

def main():
    parser = argparse.ArgumentParser(description="对提取的序列进行 Off-target search")
    parser.add_argument("tsv_file", help="extract.py 输出的 TSV 文件")
    parser.add_argument("genome_file", help="Genome file (FASTA or GenBank)")
    parser.add_argument("--屏蔽基因", help="屏蔽基因 FASTA (可选)")
    parser.add_argument("--输出目录", default=".", help="输出目录 (默认当前)")
    parser.add_argument("--evalue", type=float, default=1000, help="Off-target search evalue (默认 1000)")
    parser.add_argument("--word_size", type=int, default=4, help="Off-target search word_size (默认 4)")
    parser.add_argument("--task", default="blastn-short", help="Off-target search task (默认 blastn-short)")
    parser.add_argument("--motif", help="原始 motif 序列 (如 TTAT)，若 TSV 有元数据则可省略")
    parser.add_argument("--flank_len", "--flanking_len", type=int,
                        help="Flanking sequence length (bp)，若 TSV 有元数据则可省略")
    parser.add_argument("--side", choices=["upstream", "downstream"], help="方向: upstream 或 downstream，若 TSV 有元数据则可省略")
    parser.add_argument("--blastdb", help="直接使用已有的 Genome database 前缀路径（跳过构建）")
    parser.add_argument("--engine", default="blast",
                        choices=["exact", "indexed", "blast", "gggenome",
                                 "auto"])
    parser.add_argument("--index-path", default="",
                        help="Local genome index prefix (.ggi/.json)")
    parser.add_argument("--genome-build", default="",
                        help="Genome build name for GGGenome, e.g. hg38")
    parser.add_argument("--max-mismatch", type=int, choices=[0, 1, 2, 3, 4], default=4,
                        help="最大允许错配数（默认 4）")
    parser.add_argument("--max-bulge", type=int, choices=[0, 1], default=None,
                        help="最大 bulge 数；未指定时按 engine 使用默认值")
    parser.add_argument("--require-pam", action="store_true",
                        help="要求匹配位点存在 PAM（默认 3' 侧，可用 --pam-side 调整）")
    parser.add_argument("--pam-motif", default="GG", help="PAM motif，默认 GG")
    parser.add_argument("--pam-side", choices=["3prime", "5prime"], default="3prime",
                        help="PAM 位置，默认 3prime")
    parser.add_argument("--seed-mismatch-max", type=int, default=None,
                        help="PAM 近端 seed 区域最大错配数（默认不限制）")
    parser.add_argument("--seed-len", type=int, default=12,
                        help="PAM 近端 seed 区域长度（默认 12）")
    parser.add_argument("--max-memory-mb", type=int, default=None,
                        help="Explicit process RSS limit in MiB")
    parser.add_argument("--timeout-s", type=float, default=None,
                        help="Wall-clock budget for one indexed search, in "
                             "seconds; default is no timeout")
    parser.add_argument("--python-fallback", default=None,
                        choices=["ask", "allow", "deny"],
                        help="Pure-Python index fallback policy; "
                             "defaults to ask, or the value of the "
                             "%s environment variable" % PYTHON_FALLBACK_ENV)
    parser.add_argument("--engine-fallback", default=None,
                        choices=["ask", "allow", "deny"],
                        help="Cross-engine fallback policy for --engine auto; "
                             "defaults to ask, or the value of the "
                             "%s environment variable" % ENGINE_FALLBACK_ENV)
    parser.add_argument("--repeat-fasta", help="重复序列 FASTA，匹配位置落在这些区间内时过滤")
    args = parser.parse_args()

    log("=== 开始 Off-target search 流程 ===")
    os.makedirs(args.输出目录, exist_ok=True)

    # ---- 读取 TSV ----
    log(f"正在读取 TSV 文件: {args.tsv_file}")
    metadata, data_lines = read_tsv_and_get_metadata(args.tsv_file)

    motif = args.motif if args.motif is not None else metadata.get('motif')
    flank_len = args.flank_len if args.flank_len is not None else None
    if flank_len is None:
        meta_flank = metadata.get('flanking_len') or metadata.get('flank_len')
        if meta_flank is not None:
            flank_len = int(meta_flank)
    side = args.side if args.side is not None else metadata.get('side')

    if motif is None or flank_len is None or side is None:
        log("错误：必须提供 motif、flank_len 和 side，可在 TSV 元数据中指定或通过命令行参数提供")
        sys.exit(2)

    tsv_data = ''.join(data_lines)
    if not tsv_data.strip():
        log("错误：TSV 数据行为空")
        sys.exit(6)

    reader = csv.DictReader(io.StringIO(tsv_data), delimiter='\t')
    qid_to_seq = {}
    qid_to_positions = defaultdict(list)
    for row in reader:
        qid = row['qid']
        seq = row['sequence']
        positions = json.loads(row['positions'])
        qid_to_seq[qid] = seq
        qid_to_positions[qid] = positions

    if not qid_to_seq:
        log("错误：TSV 中无有效序列。")
        sys.exit(1)

    log(f"读取到 {len(qid_to_seq)} 个唯一序列")
    log("PROGRESS: 读取TSV 10")

    # extract.py returns windows of the form <flank><motif> or
    # <motif><flank>. When the motif is the same PAM motif passed to the
    # engine, every query already carries its PAM, so checking for another
    # PAM outside the hit drops every real match.
    embeds_pam = queries_embed_pam(
        qid_to_seq.values(), motif, args.pam_motif, flank_len)
    effective_require_pam = args.require_pam and not embeds_pam
    if embeds_pam:
        log("Query windows already contain the PAM motif; "
            "redundant PAM filtering is skipped.")

    # ---- 加载基因组 ----
    genome_records, genome_fasta_for_blast, temp_genome = load_genome_and_prepare_fasta(args.genome_file)
    log("PROGRESS: 加载基因组 30")
    genome_file_path = args.genome_file

    # ---- 构建屏蔽区间 ----
    rdna_intervals = {}
    if args.屏蔽基因:
        rdna_intervals = build_exclusion_intervals(args.屏蔽基因, genome_records)
        log("PROGRESS: 构建屏蔽 40")
    repeat_intervals = {}
    if args.repeat_fasta:
        repeat_intervals = build_exclusion_intervals(args.repeat_fasta, genome_records)
        log(f"重复序列区间: {sum(len(v) for v in repeat_intervals.values())} 条")

    # ---- 按所选 engine 运行 Off-target search ----
    engine = args.engine or "blast"
    genome_size = os.path.getsize(genome_fasta_for_blast)
    if (engine == "exact"
            and genome_size > MAX_EXACT_GENOME_BYTES):
        log("exact 引擎不适合大型基因组，自动回退到 blast")
        engine = "blast"

    guides = [
        {"qid": qid, "guide_seq": seq}
        for qid, seq in qid_to_seq.items()
    ]
    params = SearchParams(
        max_mismatch=args.max_mismatch,
        max_bulge=1 if args.max_bulge is None else args.max_bulge,
        max_bulge_explicit=args.max_bulge is not None,
        seed_len=args.seed_len,
        seed_mismatch_max=args.seed_mismatch_max,
        pam=args.pam_motif if effective_require_pam else None,
        pam_side=args.pam_side,
        require_pam=effective_require_pam,
        blastdb=args.blastdb or None,
        index_path=args.index_path or None,
        output_dir=args.输出目录,
        genome_build=args.genome_build or None,
        extra=build_search_extra(args),
    )
    apply_engine_defaults(
        engine, params, genome_size)
    try:
        requested_engine = engine
        engine = resolve_engine(engine, params, genome_size=genome_size)
        validate_search_params(engine, params)
    except SearchParameterError as exc:
        log("Off-target engine contract error: %s" % exc)
        sys.exit(3)
    if requested_engine == "auto" and engine != "auto":
        log(f"auto 引擎已解析为 {engine}")
    log(f"PROGRESS: Off-target search ({engine}) 70")
    try:
        results = run_backend(
            requested_engine, guides, genome_fasta_for_blast, params,
            genome=genome_records,
            progress_callback=print_search_progress,
            log=log,
        )
    except RuntimeError as exc:
        log("Off-target search failed: %s" % exc)
        sys.exit(3)
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
    log("PROGRESS: 保存结果 90")

    if temp_genome is not None:
        os.unlink(temp_genome.name)

    # ---- 保存结果到 TSV ----
    log("正在保存 Off-target search 结果到 TSV ...")
    fieldnames = ['qid', 'sequence', 'positions', 'matches',
                  'motif_plus', 'motif_minus', 'flank_len', 'side',
                  'rdna_intervals', 'genome_file']

    rows = []
    meta_row = {
        'qid': 'metadata',
        'sequence': '',
        'positions': '',
        'matches': '',
        'motif_plus': motif,
        'motif_minus': reverse_complement(motif),
        'flank_len': str(flank_len),
        'side': side,
        'rdna_intervals': json.dumps(rdna_intervals),
        'genome_file': genome_file_path
    }
    rows.append(meta_row)

    for qid, seq in qid_to_seq.items():
        pos_list = qid_to_positions[qid]
        matches = blast_matches.get(qid, [])
        row = {
            'qid': qid,
            'sequence': seq,
            'positions': json.dumps(pos_list),
            'matches': json.dumps(matches),
            'motif_plus': '',
            'motif_minus': '',
            'flank_len': '',
            'side': '',
            'rdna_intervals': '',
            'genome_file': ''
        }
        rows.append(row)

    tsv_out = os.path.join(args.输出目录, "blast_results.tsv")
    with open(tsv_out, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter='\t')
        writer.writeheader()
        writer.writerows(rows)

    log(f"\nOff-target search 结果及中间数据已保存至 {tsv_out}")
    log("=== 全部流程完成 ===")

if __name__ == "__main__":
    main()
