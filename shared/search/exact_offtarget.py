#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Exact and indel-aware off-target search for short guide sequences.

This is an optional alternative to NCBI BLAST. It uses a k-mer seed index
and extends candidates with Levenshtein alignment, so it can report
mismatches plus small bulges/indels.

The index is intended for small genomes, bacterial genomes, target regions
or transcriptomes. For full mammalian genomes, prefer BLAST mode.
"""

import argparse
import csv
import os
import re
import sys
from collections import defaultdict

try:
    from Bio import SeqIO
except ImportError:
    SeqIO = None

try:
    from pyfaidx import Fasta
except ImportError:
    Fasta = None

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from search.iupac import iupac_to_regex
from search.alignment import (
    AlignmentRecord, best_alignment, cigar_from_operations,
    reverse_complement_gapped,
)
from search.seed_plan import build_seed_plan, iter_seed_variants


_COMPLEMENT = str.maketrans("ACGTUN", "TGCAAN")


def reverse_complement(seq):
    return seq.upper().translate(_COMPLEMENT)[::-1]


def _valid_dna(seq):
    return not (set(seq.upper()) - set("ACGT"))


def levenshtein(a, b):
    """Levenshtein distance; substitutions and indels each cost one edit."""
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        cur = [i]
        for j, cb in enumerate(b, start=1):
            cur.append(min(prev[j] + 1, cur[-1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _edit_counts(a, b):
    """Return substitution and indel counts for the best short alignment."""
    if not a:
        return 0, len(b)
    if not b:
        return len(a), 0

    # Entries are (edit cost, indel count). The tuple ordering keeps the
    # existing preference for substitutions when two alignments tie.
    prev = [(j, j) for j in range(len(b) + 1)]
    for i, char_a in enumerate(a, start=1):
        cur = [(i, i)]
        for j, char_b in enumerate(b, start=1):
            diagonal = (
                prev[j - 1][0] + (char_a != char_b),
                prev[j - 1][1],
            )
            deletion = (prev[j][0] + 1, prev[j][1] + 1)
            insertion = (cur[-1][0] + 1, cur[-1][1] + 1)
            cur.append(min(diagonal, deletion, insertion))
        prev = cur

    cost, indels = prev[-1]
    return cost - indels, indels


class KmerIndex:
    """K-mer index over the plus strand of a FASTA genome."""

    def __init__(self, fasta_path, k=10, max_records=None):
        if SeqIO is None:
            raise RuntimeError("Biopython is required to build the exact index")
        self.k = int(k)
        self.kmers = defaultdict(list)
        self.sequences = {}
        self.seq_lengths = {}
        self.order = []
        with open(fasta_path, "r", encoding="utf-8") as handle:
            for i, record in enumerate(SeqIO.parse(handle, "fasta")):
                if max_records is not None and i >= max_records:
                    break
                seq = str(record.seq).upper()
                self.order.append(record.id)
                self.sequences[record.id] = seq
                self.seq_lengths[record.id] = len(seq)
                for pos in range(0, len(seq) - self.k + 1):
                    kmer = seq[pos:pos + self.k]
                    if _valid_dna(kmer):
                        self.kmers[kmer].append((record.id, pos))

    def __len__(self):
        return sum(len(v) for v in self.kmers.values())


def _seed_variants(seed, max_mm=1):
    """Compatibility wrapper for the shared exact variant generator."""
    return set(iter_seed_variants(seed, max_mm))


def _fetch(genome, seqid, start, end):
    if Fasta is None:
        return None
    try:
        chrom = genome[seqid]
        start = max(0, int(start))
        end = min(len(chrom), int(end))
        if start >= end:
            return None
        return str(chrom[start:end]).upper()
    except Exception:
        return None


def _pam_ok_span(genome, seqid, target_start, target_end, strand,
                 pam, pam_side, fetch_func=None):
    """Check PAM using the alignment's actual target span."""
    if not pam:
        return True
    pam_re = re.compile(iupac_to_regex(pam))
    pam_len = len(pam)
    fetch = fetch_func or _fetch
    if strand == "+":
        if pam_side == "5prime":
            seq = fetch(genome, seqid, target_start - pam_len, target_start)
            return seq is not None and bool(pam_re.fullmatch(seq))
        seq = fetch(genome, seqid, target_end, target_end + pam_len)
        return seq is not None and bool(pam_re.fullmatch(seq))
    rc_pam = reverse_complement(pam)
    rc_re = re.compile(iupac_to_regex(rc_pam))
    if pam_side == "5prime":
        seq = fetch(genome, seqid, target_end, target_end + pam_len)
        return seq is not None and bool(rc_re.fullmatch(seq))
    seq = fetch(genome, seqid, target_start - pam_len, target_start)
    return seq is not None and bool(rc_re.fullmatch(seq))


def _pam_sequence_span(genome, seqid, target_start, target_end, strand,
                       pam, pam_side, fetch_func=None):
    """Fetch the PAM in guide/query orientation, or return an empty string."""
    if not pam:
        return ""
    pam_len = len(pam)
    fetch = fetch_func or _fetch
    if strand == "+":
        start, end = (
            (target_start - pam_len, target_start)
            if pam_side == "5prime"
            else (target_end, target_end + pam_len)
        )
    else:
        start, end = (
            (target_end, target_end + pam_len)
            if pam_side == "5prime"
            else (target_start - pam_len, target_start)
        )
    sequence = fetch(genome, seqid, start, end) or ""
    if strand == "-":
        sequence = reverse_complement(sequence)
    return sequence


def _pam_ok(genome, seqid, start, guide_len, strand, pam, pam_side):
    """Compatibility wrapper for callers that still pass a guide length."""
    target_end = start + int(guide_len)
    return _pam_ok_span(
        genome, seqid, start, target_end, strand, pam, pam_side)


def _best_alignment(window, probe, center, max_bulge, max_mismatch=None):
    """Compatibility wrapper returning the legacy tuple representation."""
    alignment = best_alignment(window, probe, center, max_bulge)
    if alignment is None:
        return len(probe) + max_bulge + 1, 0, 0, 0
    return (
        alignment.mismatches,
        alignment.indels,
        alignment.target_start,
        alignment.target_end,
    )


def _alignment_to_hit(alignment, seqid, genomic_start, strand):
    """Convert a window-relative alignment to the normalized hit fields."""
    target_start = genomic_start + alignment.target_start
    target_end = genomic_start + alignment.target_end
    query_aligned = alignment.query_aligned
    target_aligned = alignment.target_aligned
    if strand == "-":
        query_aligned = reverse_complement_gapped(query_aligned)
        target_aligned = reverse_complement_gapped(target_aligned)
    operations = []
    mismatches = 0
    for query_base, target_base in zip(query_aligned, target_aligned):
        if query_base == "-" and target_base != "-":
            operations.append("D")
        elif target_base == "-" and query_base != "-":
            operations.append("I")
        elif query_base == target_base:
            operations.append("M")
        else:
            operations.append("X")
            mismatches += 1
    rna_bulges = operations.count("I")
    dna_bulges = operations.count("D")
    cigar = cigar_from_operations(operations)
    query_len = len(query_aligned.replace("-", ""))
    return {
        "target": seqid,
        "start": target_start,
        "strand": strand,
        "mismatch": mismatches,
        "indel": rna_bulges + dna_bulges,
        "rna_bulges": rna_bulges,
        "dna_bulges": dna_bulges,
        "cigar": cigar,
        "target_start": target_start,
        "target_end": target_end,
        "query_start": 0,
        "query_end": query_len,
        "aligned_guide": query_aligned,
        "aligned_target": target_aligned,
        "bitscore": round(
            max(0.0, 100.0 - alignment.mismatches * 12.0
                - alignment.indels * 18.0), 2),
    }


def _search_sequence_exhaustive(seqid, sequence, probe, target_strand,
                                max_mismatch, max_bulge, pam, pam_side,
                                genome, seen):
    hits = []
    probe_len = len(probe)
    for start in range(
            0, max(0, len(sequence) - probe_len + max_bulge + 1)):
        window_start = max(0, start - max_bulge)
        window_end = min(
            len(sequence), start + probe_len + max_bulge)
        window = sequence[window_start:window_end]
        alignment = best_alignment(
            window, probe, start - window_start, max_bulge,
            max_mismatch=max_mismatch,
            accept_alignment=lambda local_start, local_end: _pam_ok_span(
                genome, seqid, window_start + local_start,
                window_start + local_end, target_strand, pam, pam_side),
        )
        if alignment is None:
            continue
        if (alignment.mismatches > max_mismatch
                or alignment.indels > max_bulge):
            continue
        genomic_start = window_start
        hit = _alignment_to_hit(
            alignment, seqid, genomic_start, target_strand)
        key = (seqid, hit["target_start"], hit["target_end"], target_strand)
        if key in seen:
            continue
        if not _pam_ok_span(
                genome, seqid, hit["target_start"], hit["target_end"],
                target_strand, pam, pam_side):
            continue
        hit["pam"] = _pam_sequence_span(
            genome, seqid, hit["target_start"], hit["target_end"],
            target_strand, pam, pam_side)
        seen.add(key)
        hits.append(hit)
    return hits


def search_probe(probe, index, genome, max_mismatch=4, max_bulge=1,
                 seed_len=10, seed_mm=1, pam=None, pam_side="3prime",
                 context=40, target_strand="+"):
    """Search one probe (guide or its reverse complement) on the plus strand."""
    hits = []
    seen = set()
    probe_len = len(probe)
    plan = build_seed_plan(
        probe_len, max_mismatch, max_bulge, seed_len, index.k)
    if not plan.guaranteed:
        for seqid in index.order:
            sequence = index.sequences.get(seqid)
            if sequence is None:
                continue
            hits.extend(_search_sequence_exhaustive(
                seqid, sequence, probe, target_strand, max_mismatch,
                max_bulge, pam, pam_side, genome, seen))
        return hits

    for segment in plan.segments:
        seed = probe[segment.start:segment.end]
        for offset in range(0, len(seed) - index.k + 1):
            seed_kmer = seed[offset:offset + index.k]
            for kmer in iter_seed_variants(
                    seed_kmer, segment.allowed_mismatches):
                for seqid, kpos in index.kmers.get(kmer, []):
                    candidate_start = kpos - segment.start - offset
                    if candidate_start < 0:
                        continue
                    key = (seqid, candidate_start, target_strand)
                    if key in seen:
                        continue
                    fetch_start = max(0, candidate_start - context)
                    window = _fetch(
                        genome, seqid, fetch_start,
                        candidate_start + probe_len + context)
                    if window is None:
                        continue
                    center = candidate_start - fetch_start
                    alignment = best_alignment(
                        window, probe, center, max_bulge,
                        max_mismatch=max_mismatch,
                        accept_alignment=lambda local_start, local_end: (
                            _pam_ok_span(
                                genome, seqid, fetch_start + local_start,
                                fetch_start + local_end, target_strand,
                                pam, pam_side)
                        ),
                    )
                    if alignment is None:
                        continue
                    if (alignment.mismatches > max_mismatch
                            or alignment.indels > max_bulge):
                        continue
                    hit = _alignment_to_hit(
                        alignment, seqid, fetch_start, target_strand)
                    hit_key = (
                        seqid, hit["target_start"], hit["target_end"],
                        target_strand,
                    )
                    if hit_key in seen:
                        continue
                    if not _pam_ok_span(
                            genome, seqid, hit["target_start"],
                            hit["target_end"], target_strand, pam,
                            pam_side):
                        continue
                    hit["pam"] = _pam_sequence_span(
                        genome, seqid, hit["target_start"],
                        hit["target_end"], target_strand, pam, pam_side)
                    seen.add(hit_key)
                    hits.append(hit)
    return hits


def search_guides(guides, genome_fasta, max_mismatch=4, max_bulge=1,
                  seed_len=10, seed_mm=1, pam=None, pam_side="3prime",
                  kmer_size=10, max_records=None, progress_callback=None):
    """Search a list of guide dicts/strings and return match dicts."""
    if Fasta is None:
        raise RuntimeError("pyfaidx is required for exact off-target search")
    if not guides:
        return {}
    index = KmerIndex(genome_fasta, k=kmer_size, max_records=max_records)
    genome = Fasta(genome_fasta)
    out = {}
    try:
        for i, guide_item in enumerate(guides):
            if isinstance(guide_item, dict):
                seq = guide_item.get("guide_seq") or guide_item.get("spacer_seq") or ""
                qid = guide_item.get("qid") or guide_item.get("seq_id") or "guide_%d" % i
            else:
                seq = guide_item
                qid = "guide_%d" % i
            if progress_callback:
                progress_callback(i + 1, len(guides))
            seq = seq.upper().replace("U", "T")
            if not seq:
                continue
            for probe, strand in ((seq, "+"), (reverse_complement(seq), "-")):
                hits = search_probe(probe, index, genome,
                                    max_mismatch=max_mismatch, max_bulge=max_bulge,
                                    seed_len=seed_len, seed_mm=seed_mm,
                                    pam=pam, pam_side=pam_side, target_strand=strand)
                for hit in hits:
                    hit["qid"] = qid
                    hit["guide"] = seq
                    out.setdefault(qid, []).append(hit)
    finally:
        close = getattr(genome, "close", None)
        if callable(close):
            close()
    # Deduplicate identical genomic hits per guide.
    for qid, hits in out.items():
        unique = {}
        for hit in hits:
            key = (
                hit["target"], hit.get("target_start", hit["start"]),
                hit.get("target_end", hit["start"] + len(hit["guide"])),
                hit["strand"],
            )
            rank = (hit["mismatch"], hit.get("indel", 0))
            if key not in unique:
                unique[key] = hit
                continue
            old = unique[key]
            if rank < (old["mismatch"], old.get("indel", 0)):
                unique[key] = hit
        out[qid] = sorted(
            unique.values(),
            key=lambda x: (
                x["mismatch"], x.get("indel", 0),
                x["target"], x["start"], x.get("target_end", 0),
            ),
        )
    return out


def main():
    parser = argparse.ArgumentParser(description="Exact/indel-aware off-target search")
    parser.add_argument("guides_tsv", help="Guide TSV with a guide_seq column")
    parser.add_argument("genome_fasta", help="Genome FASTA used as the search target")
    parser.add_argument("output_tsv", help="Output TSV")
    parser.add_argument("--max-mismatch", type=int, default=4)
    parser.add_argument("--max-bulge", type=int, default=1)
    parser.add_argument("--seed-len", type=int, default=10)
    parser.add_argument("--seed-mismatch", type=int, default=1)
    parser.add_argument("--kmer-size", type=int, default=10)
    parser.add_argument("--pam", default=None)
    parser.add_argument("--pam-side", choices=["3prime", "5prime"], default="3prime")
    parser.add_argument("--max-records", type=int, default=None)
    args = parser.parse_args()

    if not os.path.isfile(args.guides_tsv) or not os.path.isfile(args.genome_fasta):
        print("Error: input files not found.")
        sys.exit(2)
    with open(args.guides_tsv, encoding="utf-8") as handle:
        guides = list(csv.DictReader(handle, delimiter="\t"))
    if not guides or "guide_seq" not in guides[0]:
        print("Error: guides_tsv must contain a guide_seq column.")
        sys.exit(2)
    print(f"Indexing {args.genome_fasta} ...")
    results = search_guides(guides, args.genome_fasta,
                            max_mismatch=args.max_mismatch,
                            max_bulge=args.max_bulge,
                            seed_len=args.seed_len,
                            seed_mm=args.seed_mismatch,
                            pam=args.pam,
                            pam_side=args.pam_side,
                            kmer_size=args.kmer_size,
                            max_records=args.max_records)
    os.makedirs(os.path.dirname(os.path.abspath(args.output_tsv)), exist_ok=True)
    fields = ["qid", "guide", "target", "start", "strand", "mismatch", "indel", "bitscore"]
    with open(args.output_tsv, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", extrasaction="ignore")
        writer.writeheader()
        for qid in sorted(results):
            for hit in results[qid]:
                writer.writerow(hit)
    print(f"Wrote {sum(len(v) for v in results.values())} hits to {args.output_tsv}")


if __name__ == "__main__":
    main()
