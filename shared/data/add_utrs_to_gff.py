#!/usr/bin/env python3
"""
add_utrs_to_gff.py - 为 GFF3 添加 5' 和 3' UTR 特征（支持 NCBI RefSeq 格式）
用法: python add_utrs_to_gff.py input.gff3 > output.gff3

功能：
- 识别 gene, pseudogene, ncRNA_gene 等基因类型
- 识别 mRNA, transcript, primary_transcript 等转录本类型
- 对每个转录本的外显子和 CDS 按坐标排序（确保正负链计算正确）
- 生成 UTR 行，输出所有原始行 + 新增 UTR 行
- 如果输入已含 UTR，则跳过添加，直接输出原文件
"""

import os
import sys
import re
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from annotation_utils import open_annotation_text

# ---------- 属性解析 ----------
def parse_attributes(attr_str):
    attrs = {}
    if attr_str == ".":
        return attrs
    # 支持 GFF3 的 key=value 格式
    for item in attr_str.split(";"):
        if "=" in item:
            k, v = item.split("=", 1)
            attrs[k.strip()] = v.strip()
    return attrs

# ---------- 构建数据结构 ----------
def read_gff(input_file):
    """
    返回：
        lines: 所有非注释行（按原顺序）
        genes: dict {seqid: {gene_id: {'strand': strand, 'record': line}}}
        mrnas: dict {mrna_id: {'gene_id': gid, 'seqid': seqid, 'strand': strand,
                                'exons': [(start,end,line), ...],
                                'cds': [(start,end,line), ...],
                                'record': line}}
        has_utr: bool
    """
    lines = []
    genes = defaultdict(dict)
    mrnas = {}
    has_utr = False

    # 用于临时存储未归属的 exon/CDS，稍后通过 Parent 关联
    exon_list = []   # 元素: (seqid, start, end, strand, line)
    cds_list = []

    with open_annotation_text(input_file) as f:
        for line in f:
            if line.startswith('#'):
                lines.append(line)   # 注释行保留
                continue
            parts = line.strip().split('\t')
            if len(parts) < 9:
                lines.append(line)   # 格式不完整仍保留
                continue
            seqid, source, feat, start, end, score, strand, phase, attr_str = parts
            start, end = int(start), int(end)
            attrs = parse_attributes(attr_str)

            # 检查是否已有 UTR
            if feat in ('five_prime_UTR', 'three_prime_UTR', "5'UTR", "3'UTR"):
                has_utr = True

            # 保留原始行（非注释行）
            lines.append(line.rstrip('\n'))

            # 处理基因行
            if feat in ('gene', 'pseudogene', 'ncRNA_gene', 'rRNA_gene', 'tRNA_gene'):
                gid = attrs.get('ID')
                if gid:
                    genes[seqid][gid] = {
                        'strand': strand,
                        'record': line.rstrip('\n')
                    }

            # 处理转录本行
            elif feat in ('mRNA', 'transcript', 'primary_transcript',
                          'C_gene_segment', 'V_gene_segment', 'D_gene_segment', 'J_gene_segment'):
                tid = attrs.get('ID')
                parents = attrs.get('Parent', '').split(',')
                if tid and parents:
                    # 找到父基因
                    for p in parents:
                        if p in genes.get(seqid, {}):
                            mrnas[tid] = {
                                'gene_id': p,
                                'seqid': seqid,
                                'strand': strand,
                                'exons': [],
                                'cds': [],
                                'record': line.rstrip('\n')
                            }
                            break

            # 处理外显子
            elif feat == 'exon':
                parents = attrs.get('Parent', '').split(',')
                if parents:
                    # 先暂存，稍后关联到转录本
                    exon_list.append((seqid, start, end, strand, line.rstrip('\n'), parents))

            # 处理 CDS
            elif feat == 'CDS':
                parents = attrs.get('Parent', '').split(',')
                if parents:
                    cds_list.append((seqid, start, end, strand, line.rstrip('\n'), parents))

    # 将外显子和 CDS 关联到对应的转录本
    for seqid, start, end, strand, line, parents in exon_list:
        for p in parents:
            if p in mrnas:
                mrnas[p]['exons'].append((start, end, line))
                break

    for seqid, start, end, strand, line, parents in cds_list:
        for p in parents:
            if p in mrnas:
                mrnas[p]['cds'].append((start, end, line))
                break

    return lines, genes, mrnas, has_utr


# ---------- 生成 UTR 行 ----------
def generate_utr_lines(mrna_id, mrna_data, source='BestRefSeq', score='.', phase='.'):
    """
    根据转录本数据生成 UTR 行列表
    """
    seqid = mrna_data['seqid']
    strand = mrna_data['strand']
    exons = mrna_data['exons']
    cds = mrna_data['cds']

    # 强制排序（关键步骤）
    exons_sorted = sorted(exons, key=lambda x: x[0])   # 按起始位点排序
    cds_sorted = sorted(cds, key=lambda x: x[0])

    if not exons_sorted or not cds_sorted:
        return []  # 无外显子或 CDS，无法计算 UTR

    utr_lines = []

    # 获取坐标
    first_exon_start, first_exon_end = exons_sorted[0][0], exons_sorted[0][1]
    last_exon_start, last_exon_end = exons_sorted[-1][0], exons_sorted[-1][1]
    first_cds_start, first_cds_end = cds_sorted[0][0], cds_sorted[0][1]
    last_cds_start, last_cds_end = cds_sorted[-1][0], cds_sorted[-1][1]

    # 根据链方向计算 UTR 区间
    if strand == '+':
        # 5' UTR: 从第一个外显子起始到第一个 CDS 起始前
        if first_exon_start < first_cds_start:
            utr5_start = first_exon_start
            utr5_end = first_cds_start - 1
            if utr5_start <= utr5_end:
                utr_lines.append((
                    seqid, source, 'five_prime_UTR',
                    utr5_start, utr5_end, score, strand, phase,
                    f"ID=utr5_{mrna_id};Parent={mrna_id}"
                ))
        # 3' UTR: 从最后一个 CDS 结束到最后一个外显子结束
        if last_cds_end < last_exon_end:
            utr3_start = last_cds_end + 1
            utr3_end = last_exon_end
            if utr3_start <= utr3_end:
                utr_lines.append((
                    seqid, source, 'three_prime_UTR',
                    utr3_start, utr3_end, score, strand, phase,
                    f"ID=utr3_{mrna_id};Parent={mrna_id}"
                ))
    elif strand == '-':
        # 负链：注意坐标方向与基因方向相反
        # 5' UTR 位于最右侧（坐标最大端）
        if last_cds_end < last_exon_end:
            utr5_start = last_cds_end + 1
            utr5_end = last_exon_end
            if utr5_start <= utr5_end:
                utr_lines.append((
                    seqid, source, 'five_prime_UTR',
                    utr5_start, utr5_end, score, strand, phase,
                    f"ID=utr5_{mrna_id};Parent={mrna_id}"
                ))
        # 3' UTR 位于最左侧（坐标最小端）
        if first_exon_start < first_cds_start:
            utr3_start = first_exon_start
            utr3_end = first_cds_start - 1
            if utr3_start <= utr3_end:
                utr_lines.append((
                    seqid, source, 'three_prime_UTR',
                    utr3_start, utr3_end, score, strand, phase,
                    f"ID=utr3_{mrna_id};Parent={mrna_id}"
                ))
    else:
        # 链未知，不处理
        pass

    return utr_lines


# ---------- 主函数 ----------
def add_utrs(input_file):
    lines, genes, mrnas, has_utr = read_gff(input_file)

    # 如果已有 UTR，直接输出原文件并退出
    if has_utr:
        sys.stdout.write('\n'.join(lines) + '\n')
        return

    # 收集所有 UTR 行
    new_utr_lines = []
    for mrna_id, mrna_data in mrnas.items():
        utrs = generate_utr_lines(mrna_id, mrna_data)
        for utr in utrs:
            new_utr_lines.append('\t'.join(map(str, utr)))

    # 输出所有原始行（包括注释和特征行）
    output = '\n'.join(lines)
    if output and not output.endswith('\n'):
        output += '\n'
    sys.stdout.write(output)

    # 输出新增的 UTR 行（放在最后，顺序不影响使用）
    if new_utr_lines:
        sys.stdout.write('\n'.join(new_utr_lines) + '\n')


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python add_utrs_to_gff.py input.gff3 > output.gff3", file=sys.stderr)
        sys.exit(6)
    add_utrs(sys.argv[1])
