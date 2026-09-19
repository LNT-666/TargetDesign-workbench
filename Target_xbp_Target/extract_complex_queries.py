#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import bisect
from Bio import SeqIO
from Bio.Seq import Seq
from Bio.SeqRecord import SeqRecord

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "shared"))
from search.iupac import find_all_iupac_positions, iupac_to_regex


def reverse_complement(seq):
    return str(Seq(seq).reverse_complement())


def flank_interval(seq_len, pos, motif_len, side, flank_len, strand):
    if strand == "minus":
        side = "downstream" if side == "upstream" else "upstream"
    if side == "upstream":
        start = max(0, pos - flank_len)
        return start, pos
    start = pos + motif_len
    end = min(seq_len, pos + motif_len + flank_len)
    return start, end


def get_flank(seq_str, pos, motif_len, side, flank_len, strand):
    start, end = flank_interval(
        len(seq_str), pos, motif_len, side, flank_len, strand
    )
    return seq_str[start:end]

def main():
    if len(sys.argv) != 11:
        print("""Usage: python extract_complex_queries.py <input.fasta> <left_motif> <right_motif>
                 <min_gap> <max_gap> <left_side> <left_len> <right_side> <right_len> <output.tsv>
        Motif sequences may contain IUPAC degenerate bases (e.g., R, Y, N).
        left_side/right_side: upstream or downstream
        Left and right motifs are each matched on plus and minus, so all four
        strand combinations are considered.
        Example: python extract_complex_queries.py rRNA.fa TTAT CCGG 5 20 upstream 10 downstream 15 queries.tsv
        """)
        sys.exit(1)

    input_fasta = sys.argv[1]
    left_motif = sys.argv[2].upper()
    right_motif = sys.argv[3].upper()
    left_motif_minus = reverse_complement(left_motif)
    right_motif_minus = reverse_complement(right_motif)
    min_gap = int(sys.argv[4])
    max_gap = int(sys.argv[5])
    left_side = sys.argv[6].lower()
    if left_side not in ("upstream", "downstream"):
        print("Error: left_side must be 'upstream' or 'downstream'")
        sys.exit(2)
    left_len = int(sys.argv[7])
    right_side = sys.argv[8].lower()
    if right_side not in ("upstream", "downstream"):
        print("Error: right_side must be 'upstream' or 'downstream'")
        sys.exit(2)
    right_len = int(sys.argv[9])
    out_tsv = sys.argv[10]
    query_sidecar = os.path.splitext(out_tsv)[0] + ".queries.fa"

    print(f"Left motif '{left_motif}' regex: {iupac_to_regex(left_motif)}")
    print(f"Right motif '{right_motif}' regex: {iupac_to_regex(right_motif)}")
    print(f"Left motif (-) regex: {iupac_to_regex(left_motif_minus)}")
    print(f"Right motif (-) regex: {iupac_to_regex(right_motif_minus)}")

    # 读取输入序列（不展开）
    original_records = list(SeqIO.parse(input_fasta, "fasta"))
    if not original_records:
        print("Error: no sequences in input.")
        sys.exit(1)
    print(f"Read {len(original_records)} sequences from input (no IUPAC expansion applied).")

    qid_by_query = {}
    sidecar_lines = []

    with open(out_tsv, 'w') as f:
        header = ["qid", "seq_id", "strand", "left_strand", "right_strand",
                  "left_pos", "right_pos", "gap",
                  "compound_start", "compound_end",
                  "left_target_start", "left_target_end",
                  "right_target_start", "right_target_end",
                  "left_motif_seq", "right_motif_seq",
                  "left_flank_seq", "right_flank_seq",
                  "left_side", "left_len", "right_side", "right_len"]
        f.write("\t".join(header) + "\n")

        total_combo = 0
        total_records = len(original_records)
        for rec_idx, rec in enumerate(original_records):
            if rec_idx % max(1, total_records // 10) == 0 or rec_idx == total_records - 1:
                print(f"PROGRESS: 提取中 {int(rec_idx / total_records * 100)}", flush=True)
            seq_str = str(rec.seq).upper()
            seq_id = rec.id
            seen_pairs = set()

            for left_strand, right_strand, l_motif, r_motif in (
                ("plus", "plus", left_motif, right_motif),
                ("plus", "minus", left_motif, right_motif_minus),
                ("minus", "plus", left_motif_minus, right_motif),
                ("minus", "minus", left_motif_minus, right_motif_minus),
            ):
                compound_strand = (
                    "minus"
                    if left_strand == "minus" and right_strand == "minus"
                    else "plus"
                )
                left_positions = set(find_all_iupac_positions(seq_str, l_motif))
                right_positions = set(find_all_iupac_positions(seq_str, r_motif))
                if not left_positions or not right_positions:
                    continue
                right_sorted = sorted(right_positions)
                for lpos in sorted(left_positions):
                    r_start = lpos + len(l_motif) + min_gap
                    r_end = lpos + len(l_motif) + max_gap
                    lo = bisect.bisect_left(right_sorted, r_start)
                    hi = bisect.bisect_right(right_sorted, r_end)
                    for j in range(lo, hi):
                        rpos = right_sorted[j]
                        gap = rpos - (lpos + len(l_motif))
                        comp_start = lpos
                        comp_end = rpos + len(r_motif)

                        left_seq = seq_str[lpos:lpos + len(l_motif)]
                        right_seq = seq_str[rpos:rpos + len(r_motif)]
                        left_t_start, left_t_end = flank_interval(
                            len(seq_str), lpos, len(l_motif),
                            left_side, left_len, left_strand,
                        )
                        right_t_start, right_t_end = flank_interval(
                            len(seq_str), rpos, len(r_motif),
                            right_side, right_len, right_strand,
                        )
                        pair_key = (seq_id, lpos, rpos, left_seq, right_seq)
                        if pair_key in seen_pairs:
                            continue
                        seen_pairs.add(pair_key)
                        left_flank = get_flank(seq_str, lpos, len(l_motif),
                                               left_side, left_len, left_strand)
                        right_flank = get_flank(seq_str, rpos, len(r_motif),
                                                right_side, right_len, right_strand)
                        query_seq = left_flank + seq_str[comp_start:comp_end] + right_flank
                        qid = qid_by_query.get(query_seq)
                        if qid is None:
                            qid = "uniq_%d" % len(qid_by_query)
                            qid_by_query[query_seq] = qid
                            sidecar_lines.append(">%s\n%s\n" % (qid, query_seq))

                        row = [qid, seq_id, compound_strand, left_strand, right_strand,
                               str(lpos), str(rpos), str(gap),
                               str(comp_start), str(comp_end),
                               str(left_t_start), str(left_t_end),
                               str(right_t_start), str(right_t_end),
                               left_seq, right_seq,
                               left_flank, right_flank,
                               left_side, str(left_len), right_side, str(right_len)]
                        f.write("\t".join(row) + "\n")
                        total_combo += 1

    with open(query_sidecar, 'w') as f:
        f.writelines(sidecar_lines)
    print(f"Extracted {total_combo} compound combinations. TSV written to {out_tsv}")
    print("PROGRESS: 完成 100", flush=True)

if __name__ == "__main__":
    main()
