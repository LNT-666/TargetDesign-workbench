#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Cas13 guide scoring using ViennaRNA features plus deterministic fallbacks.

The combined score is built from guide RNA accessibility, self-structure
penalty, direct-repeat/spacer interaction, target accessibility, target
structure perturbation and the established U/A-rich sequence bias. When
ViennaRNA is missing the score degrades to the deterministic bias only.
"""

import scoring.rna_utils as rna_utils


_PREFER = {
    "cas13": "u_rich",
}


def _max_homopolymer_run(seq):
    best = 1
    current = 1
    for i in range(1, len(seq)):
        if seq[i] == seq[i - 1]:
            current += 1
            best = max(best, current)
        else:
            current = 1
    return best


def _heuristic_score(seq):
    seq = seq.upper()
    if not seq:
        return 0.0
    length = len(seq)
    gc = (seq.count("G") + seq.count("C")) / length
    gc_score = max(0.0, 1.0 - abs(gc - 0.50) / 0.30)
    seed_len = min(8, length)
    seed = seq[-seed_len:]
    seed_gc = (seed.count("G") + seed.count("C")) / seed_len
    seed_score = max(0.0, 1.0 - abs(seed_gc - 0.50) / 0.50)
    run_score = max(0.0, 1.0 - (_max_homopolymer_run(seq) - 3) / 6.0)
    if length >= 2:
        kmer_count = len({seq[i:i + 2] for i in range(length - 1)})
        complexity = min(1.0, kmer_count / min(16, length - 1))
    else:
        complexity = 1.0
    return max(0.0, min(1.0, 0.35 * gc_score + 0.25 * seed_score +
                        0.20 * run_score + 0.20 * complexity))


def _bias_score(seq, prefer):
    seq = seq.upper().replace("T", "U")
    if not seq:
        return 0.0
    length = len(seq)
    if prefer == "a_rich":
        target_base = "A"
        preferred_pairs = {"AA", "UA"}
    else:
        target_base = "U"
        preferred_pairs = {"UU", "AU"}
    content = seq.count(target_base) / length
    content_score = max(0.0, min(1.0, (content - 0.20) / 0.20))
    pair_score = 0.0
    if length > 1:
        preferred = sum(1 for i in range(length - 1)
                        if seq[i:i + 2] in preferred_pairs)
        pair_score = min(1.0, preferred / max(1, length - 1) * 2.0)
    return max(0.0, min(1.0, 0.35 * content_score + 0.15 * pair_score +
                        0.50 * _heuristic_score(seq)))


def _combine(features, bias):
    weights = []
    values = []
    accessibility = features.get("guide_accessibility")
    if accessibility is not None:
        weights.append(0.45)
        values.append(max(0.0, min(1.0, accessibility)))
    mfe = features.get("guide_mfe")
    if mfe is not None:
        structure_penalty = max(0.0, min(1.0, (-mfe - 2.0) / 10.0))
        weights.append(0.25)
        values.append(1.0 - structure_penalty)
    dr_penalty = features.get("dr_spacer_penalty")
    if dr_penalty is not None:
        weights.append(0.15)
        values.append(1.0 - dr_penalty)
    weights.append(0.15)
    values.append(bias)
    return sum(v * w for v, w in zip(values, weights)) / sum(weights)


def cas13_on_target_score(guide_seq, nuclease="cas13", direct_repeat=None,
                          target_rna=None, target_start=0):
    """Return (score, model, features) for one Cas13 guide.

    ``features`` always contains the Phase 4 contract keys; values are None
    when ViennaRNA or the optional target/DR input is unavailable.
    """
    seq = (guide_seq or "").upper().replace("T", "U")
    nuc = (nuclease or "cas13").lower()
    prefer = _PREFER.get(nuc, "u_rich")
    dr_info = rna_utils.CAS13_DR.get(nuc, {})
    dr = (direct_repeat or dr_info.get("seq") or "").upper().replace("T", "U")

    features = {
        "guide_mfe": None,
        "guide_structure": None,
        "guide_accessibility": None,
        "target_accessibility": None,
        "dr_spacer_duplex_mfe": None,
        "dr_spacer_penalty": None,
        "perturbation_mfe": None,
        "rna_model": "heuristic",
        "rna_note": "ViennaRNA not available; deterministic fallback",
        "dr_source": dr_info.get("source", ""),
        "prefer": prefer,
    }

    ok, mode = rna_utils.vienna_available()
    if not ok:
        return _bias_score(seq, prefer), "cas13_u_rich", features

    mfe = rna_utils.rnafold_mfe(seq)
    structure = rna_utils.rnafold_structure(seq)
    accessibility = rna_utils.sequence_accessibility(seq)
    features["guide_mfe"] = mfe
    features["guide_structure"] = structure
    features["guide_accessibility"] = accessibility
    features["rna_model"] = "vienna_%s" % mode
    features["rna_note"] = ""

    if dr and len(dr) >= 4:
        duplex = rna_utils.rna_duplex_mfe(dr, seq)
        features["dr_spacer_duplex_mfe"] = duplex
        if duplex is not None:
            features["dr_spacer_penalty"] = max(
                0.0, min(1.0, -duplex / 8.0))

    if target_rna:
        target = (target_rna or "").upper().replace("T", "U")
        start = max(0, int(target_start or 0))
        end = start + len(seq)
        features["target_accessibility"] = rna_utils.sequence_accessibility(
            target, start, end)
        target_mfe = rna_utils.rnafold_mfe(target)
        co_mfe = rna_utils.rna_cofold_mfe(seq, target)
        if target_mfe is not None and co_mfe is not None:
            features["perturbation_mfe"] = co_mfe - target_mfe

    score = _combine(features, _bias_score(seq, prefer))
    return score, "vienna_rna", features


def _pfs_penalty(flank_base, allowed="H"):
    """Deterministic PFS (protospacer flanking site) weight in [0, 1].

    The Cas13 preset requires a 5' non-G flank (``H`` = A/C/U).  A conforming
    base scores 1.0, ``G`` is strongly penalised, and an unknown flank returns a
    neutral 0.5 so the caller can still produce a score without the target
    sequence.
    """
    if not flank_base:
        return 0.5
    base = str(flank_base).upper().replace("T", "U")
    allowed = (allowed or "H").upper()
    if allowed == "N":
        return 1.0
    if allowed == "H" or allowed == "H/U":  # H = A/C/U (non-G)
        return 1.0 if base in ("A", "C", "U") else (0.25 if base == "G" else 0.5)
    if allowed == "U/A":
        return 1.0 if base in ("A", "U") else 0.5
    if allowed and base in allowed:
        return 1.0
    return 0.25


def cas13_pfs_on_target_score(seq, flank_base=None, prefer="u_rich",
                              nuclease="cas13"):
    """Deterministic PFS + U/A-rich Cas13 on-target fallback (no model).

    This is the CFD-style stand-in used when a deep Cas13 model (e.g. TIGER) is
    not available.  It combines the deterministic PFS penalty with the U/A-rich
    sequence bias so it can rank guides without a learned model or ViennaRNA.
    """
    seq = seq.upper().replace("T", "U")
    nuc = (nuclease or "cas13").lower()
    pfs = _pfs_penalty(flank_base)
    bias = _bias_score(seq, prefer)
    score = max(0.0, min(1.0, 0.35 * pfs + 0.65 * bias))
    features = {
        "rna_model": "cas13_pfs",
        "rna_note": "PFS + U/A-rich deterministic fallback; deep model unavailable",
        "guide_mfe": None,
        "guide_structure": None,
        "guide_accessibility": None,
        "target_accessibility": None,
        "dr_spacer_duplex_mfe": None,
        "dr_spacer_penalty": None,
        "perturbation_mfe": None,
        "dr_source": "",
        "pfs_base": flank_base or "",
        "prefer": prefer,
    }
    return score, "cas13_pfs", features


def cas13_pfs_off_target_specificity(guide, off_pairs, assume_one_primary=True):
    """PFS-weighted identity aggregation, the Cas13 analogue of CFD.

    Each off-target contributes ``identity * PFS_weight`` (using the flanking
    base from ``pam`` when supplied); a perfect match is treated as the primary
    site and can be subtracted, mirroring ``aggregate_off_target_specificity``.
    """
    if not off_pairs:
        return 1.0
    guide_t = guide.upper().replace("U", "T")
    total = 0.0
    has_primary = False
    for off_spacer, pam in off_pairs:
        off = (off_spacer or "").upper().replace("U", "T")
        n = min(len(guide_t), len(off))
        if n == 0:
            continue
        matches = sum(1 for a, b in zip(guide_t[:n], off[:n]) if a == b)
        identity = matches / n
        pfs_w = _pfs_penalty(pam)
        pair_score = identity * pfs_w
        if identity >= 0.999999:
            has_primary = True
        total += pair_score
    if assume_one_primary and has_primary:
        total = max(0.0, total - 1.0)
    return 1.0 / (1.0 + total)
