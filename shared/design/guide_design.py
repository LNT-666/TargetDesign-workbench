#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sgRNA / crRNA candidate generation with system-specific rules.

This module keeps the existing free-input behavior: callers can pass any
spacer length, PAM and strand. System presets are only used to fill defaults.
"""

import re

try:
    from Bio import SeqIO
except ImportError:
    SeqIO = None

from search.iupac import iupac_to_regex


_COMPLEMENT = str.maketrans("ACGTUN", "TGCAAN")


def reverse_complement(seq):
    return seq.upper().translate(_COMPLEMENT)[::-1]


def _gc(seq):
    if not seq:
        return 0.0
    return (seq.count("G") + seq.count("C")) / len(seq)


def _motif_overlap(sequence, start, end, motif):
    if not motif:
        return 0
    window = sequence[start:end]
    motif_plus = motif.upper().replace("U", "T")
    motif_minus = reverse_complement(motif_plus)
    best = 0
    for probe in (motif_plus, motif_minus):
        if not probe:
            continue
        for i in range(len(window) - len(probe) + 1):
            if window[i:i + len(probe)] == probe:
                best = max(best, len(probe))
    return best


def _make_regex(pattern):
    if not pattern:
        return None
    return re.compile("(?=(" + iupac_to_regex(pattern) + "))")


def find_guides(sequence, spacer_len=20, pam=None, pam_side="3prime",
                motif=None, allow_reverse=True, seq_id=None):
    """Enumerate guide candidates in a single sequence.

    Parameters use the same conventions as the GUI:
      pam_side='3prime' -> [spacer][PAM] on the scanned strand
      pam_side='5prime' -> [PAM][spacer] on the scanned strand
    Returns a list of candidate dicts sorted by genomic position.
    """
    seq = sequence.upper().replace("U", "T")
    n = len(seq)
    spacer_len = int(spacer_len) if spacer_len else 20
    if spacer_len <= 0 or n < spacer_len:
        return []

    pam_re = _make_regex(pam) if pam else None
    candidates = []
    strands = ["+", "-"] if allow_reverse else ["+"]

    for strand in strands:
        source = seq if strand == "+" else reverse_complement(seq)
        source_len = len(source)
        if pam_re is None:
            starts = range(0, source_len - spacer_len + 1)
            for start in starts:
                spacer = source[start:start + spacer_len]
                if set(spacer) - set("ACGT"):
                    continue
                if strand == "+":
                    orig_start, orig_end = start, start + spacer_len
                    pam_seq = ""
                    pam_start = pam_end = -1
                else:
                    orig_start = n - start - spacer_len
                    orig_end = n - start
                    pam_seq = ""
                    pam_start = pam_end = -1
                overlap = _motif_overlap(seq, orig_start, orig_end, motif)
                guide = spacer if strand == "+" else reverse_complement(spacer)
                candidates.append({
                    "seq_id": seq_id or "",
                    "strand": strand,
                    "guide_seq": guide,
                    "spacer_seq": guide,
                    "pam_seq": pam_seq,
                    "spacer_start": orig_start,
                    "spacer_end": orig_end,
                    "pam_start": pam_start,
                    "pam_end": pam_end,
                    "motif_overlap": overlap,
                    "gc": round(_gc(guide), 4),
                    "system_pam_side": pam_side,
                })
            continue

        if pam_side == "3prime":
            regex = re.compile(
                "(?=([ACGTN]{" + str(spacer_len) + "}" + iupac_to_regex(pam) + "))"
            )
            for match in regex.finditer(source):
                full = match.group(1)
                spacer = full[:spacer_len]
                pam_seq = full[spacer_len:]
                if set(spacer) - set("ACGT"):
                    continue
                if strand == "+":
                    orig_start, orig_end = match.start(), match.start() + spacer_len
                    pam_start = orig_end
                    pam_end = pam_start + len(pam_seq)
                else:
                    orig_start = n - match.start() - len(full)
                    orig_end = orig_start + spacer_len
                    pam_end = n - match.start()
                    pam_start = pam_end - len(pam_seq)
                overlap = _motif_overlap(seq, orig_start, orig_end, motif)
                guide = spacer if strand == "+" else reverse_complement(spacer)
                candidates.append({
                    "seq_id": seq_id or "",
                    "strand": strand,
                    "guide_seq": guide,
                    "spacer_seq": guide,
                    "pam_seq": pam_seq,
                    "spacer_start": orig_start,
                    "spacer_end": orig_end,
                    "pam_start": pam_start,
                    "pam_end": pam_end,
                    "motif_overlap": overlap,
                    "gc": round(_gc(guide), 4),
                    "system_pam_side": pam_side,
                })
        else:
            regex = re.compile(
                "(?=(" + iupac_to_regex(pam) + "[ACGTN]{" + str(spacer_len) + "}))"
            )
            for match in regex.finditer(source):
                full = match.group(1)
                pam_len = len(pam)
                pam_seq = full[:pam_len]
                spacer = full[pam_len:pam_len + spacer_len]
                if set(spacer) - set("ACGT"):
                    continue
                if strand == "+":
                    pam_start = match.start()
                    pam_end = pam_start + pam_len
                    orig_start = pam_end
                    orig_end = orig_start + spacer_len
                else:
                    orig_start = n - match.start() - len(full)
                    orig_end = orig_start + spacer_len
                    pam_end = n - match.start()
                    pam_start = pam_end - pam_len
                overlap = _motif_overlap(seq, orig_start, orig_end, motif)
                guide = spacer if strand == "+" else reverse_complement(spacer)
                candidates.append({
                    "seq_id": seq_id or "",
                    "strand": strand,
                    "guide_seq": guide,
                    "spacer_seq": guide,
                    "pam_seq": pam_seq,
                    "spacer_start": orig_start,
                    "spacer_end": orig_end,
                    "pam_start": pam_start,
                    "pam_end": pam_end,
                    "motif_overlap": overlap,
                    "gc": round(_gc(guide), 4),
                    "system_pam_side": pam_side,
                })

    seen = set()
    unique = []
    for item in candidates:
        key = (item["seq_id"], item["strand"], item["spacer_start"], item["spacer_end"],
               item["pam_start"], item["pam_end"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    unique.sort(key=lambda x: (x["spacer_start"], x["spacer_end"], x["strand"]))
    return unique


def find_guides_in_fasta(fasta_path, spacer_len=20, pam=None, pam_side="3prime",
                         motif=None, allow_reverse=True, max_records=None):
    """Enumerate guides across all records of a FASTA file."""
    if SeqIO is None:
        raise RuntimeError("Biopython is required for FASTA input")
    out = []
    for i, record in enumerate(SeqIO.parse(fasta_path, "fasta")):
        if max_records is not None and i >= max_records:
            break
        out.extend(find_guides(str(record.seq), spacer_len=spacer_len, pam=pam,
                               pam_side=pam_side, motif=motif,
                               allow_reverse=allow_reverse, seq_id=record.id))
    return out


def filter_guides(guides, min_overlap=1, gc_min=None, gc_max=None, seed_start=None,
                  seed_end=None, seed_min_gc=None):
    """Filter generated guides without changing their order."""
    result = []
    for guide in guides:
        seq = guide["guide_seq"]
        if min_overlap and guide.get("motif_overlap", 0) < min_overlap:
            continue
        if gc_min is not None and guide["gc"] < gc_min / 100.0:
            continue
        if gc_max is not None and guide["gc"] > gc_max / 100.0:
            continue
        if seed_start and seed_end:
            seed = seq[seed_start - 1:seed_end]
            if seed_min_gc is not None and seed:
                seed_gc = (seed.count("G") + seed.count("C")) / len(seed)
                if seed_gc < seed_min_gc / 100.0:
                    continue
        result.append(guide)
    return result


def guides_to_tsv(guides, path, extra_fields=None):
    """Write candidates as a TSV compatible with downstream tools."""
    fields = ["seq_id", "strand", "guide_seq", "pam_seq", "spacer_start", "spacer_end",
              "pam_start", "pam_end", "motif_overlap", "gc", "system_pam_side"]
    if extra_fields:
        for field in extra_fields:
            if field not in fields:
                fields.append(field)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write("\t".join(fields) + "\n")
        for guide in guides:
            handle.write("\t".join(str(guide.get(field, "")) for field in fields) + "\n")
