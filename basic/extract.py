#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import json
from collections import defaultdict
from Bio import SeqIO
from Bio.Seq import Seq

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "shared"))
from search.iupac import find_all_iupac_matches, iupac_to_regex

def reverse_complement(seq):
    return str(Seq(seq).reverse_complement())

def main():
    if len(sys.argv) != 6:
        print("用法: python extract.py <输入.fasta> <motif> <Flanking sequence length> <方向> <输出.tsv>")
        print("  方向: upstream 或 downstream")
        sys.exit(1)

    input_fasta = sys.argv[1]
    motif_plus = sys.argv[2].upper()
    try:
        flanking_len = int(sys.argv[3])
    except ValueError:
        print("错误：Flanking sequence length must be an integer")
        sys.exit(2)
    # 校验 Flanking sequence length 必须为正整数
    if flanking_len <= 0:
        print("错误：Flanking sequence length must be a positive integer")
        sys.exit(1)

    side = sys.argv[4].lower()
    if side not in ("upstream", "downstream"):
        print("错误：方向必须是 upstream 或 downstream")
        sys.exit(6)
    out_tsv = sys.argv[5]

    motif_minus = reverse_complement(motif_plus)

    print(f"motif (+) 正则: {iupac_to_regex(motif_plus)}")
    print(f"motif (-) 正则: {iupac_to_regex(motif_minus)}")

    # 用于存储去重后的序列及其对应的位置信息
    unique_seq_to_positions = defaultdict(list)

    # 逐条读取 FASTA 序列，避免一次性加载全部到内存
    # 先统计记录数，便于输出真实进度
    print("PROGRESS: 统计序列 0", flush=True)
    total_records = sum(1 for _ in SeqIO.parse(input_fasta, "fasta"))
    if total_records == 0:
        print("错误：输入 FASTA 文件中没有序列")
        sys.exit(6)

    seq_count = 0
    for rec in SeqIO.parse(input_fasta, "fasta"):
        seq_count += 1
        if seq_count % max(1, total_records // 10) == 0 or seq_count == total_records:
            print(f"PROGRESS: 提取中 {int(seq_count / total_records * 100)}", flush=True)
        seq_str = str(rec.seq).upper()
        seq_id = rec.id

        if side == "upstream":
            for pos, motif in find_all_iupac_matches(seq_str, motif_plus):
                if pos >= flanking_len:
                    up = seq_str[pos - flanking_len : pos]
                    full = up + motif
                    unique_seq_to_positions[full].append(
                        (seq_id, 'plus', pos, pos - flanking_len))
            for pos, motif in find_all_iupac_matches(seq_str, motif_minus):
                if pos + len(motif) + flanking_len <= len(seq_str):
                    down = seq_str[pos + len(motif) : pos + len(motif) + flanking_len]
                    full = motif + down
                    unique_seq_to_positions[full].append(
                        (seq_id, 'minus', pos, pos))
        else:  # downstream
            for pos, motif in find_all_iupac_matches(seq_str, motif_plus):
                if pos + len(motif) + flanking_len <= len(seq_str):
                    down = seq_str[pos + len(motif) : pos + len(motif) + flanking_len]
                    full = motif + down
                    unique_seq_to_positions[full].append(
                        (seq_id, 'plus', pos, pos))
            for pos, motif in find_all_iupac_matches(seq_str, motif_minus):
                if pos >= flanking_len:
                    up = seq_str[pos - flanking_len : pos]
                    full = up + motif
                    unique_seq_to_positions[full].append(
                        (seq_id, 'minus', pos, pos - flanking_len))

    print(f"输入序列共 {seq_count} 条")
    if not unique_seq_to_positions:
        print("警告：未提取到任何序列，输出空 TSV")
        with open(out_tsv, 'w') as f:
            f.write("# motif={} flanking_len={} side={}\n".format(motif_plus, flanking_len, side))
            f.write("qid\tsequence\tpositions\n")
        sys.exit(0)

    unique_seqs = list(unique_seq_to_positions.keys())
    qid_to_seq = {}
    for idx, seq in enumerate(unique_seqs):
        qid = f"uniq_{idx}"
        qid_to_seq[qid] = seq
        # 注意：seq_to_qid 已删除，不再使用

    print(f"共提取到 {sum(len(v) for v in unique_seq_to_positions.values())} 个位置，合并后为 {len(unique_seqs)} 个唯一序列")
    print("PROGRESS: 写入结果 90", flush=True)

    with open(out_tsv, 'w') as f:
        f.write(f"# motif={motif_plus} flanking_len={flanking_len} side={side}\n")
        f.write("qid\tsequence\tpositions\n")
        for qid, seq in qid_to_seq.items():
            pos_list = unique_seq_to_positions[seq]
            positions_json = json.dumps(pos_list)
            f.write(f"{qid}\t{seq}\t{positions_json}\n")

    print(f"提取结果已保存至 {out_tsv}")

if __name__ == "__main__":
    main()
