#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Offline TnpB / omegaRNA scoring rules.

The online TEEP service remains available as an explicit reference model, but
the default path now uses deterministic omegaRNA rules so library design works
without network access.
"""

import scoring.rna_utils as rna_utils


def _gc(seq):
    if not seq:
        return 0.0
    return (seq.count("G") + seq.count("C")) / len(seq)


def _spacer_len_score(seq):
    length = len(seq)
    if 14 <= length <= 18:
        return 1.0
    if 12 <= length <= 20:
        return 0.75
    return max(0.0, 1.0 - abs(length - 16) / 16.0)


def omega_rna_features(guide_seq, direct_repeat=None):
    """Return omegaRNA rule features and sub-scores for one guide."""
    seq = (guide_seq or "").upper().replace("T", "U")
    repeat = (direct_repeat or "").upper().replace("T", "U")
    length = len(seq)
    length_score = _spacer_len_score(seq)
    gc = _gc(seq)
    gc_score = max(0.0, min(1.0, 1.0 - abs(gc - 0.50) / 0.30))

    guide_hairpin = rna_utils.max_inverted_repeat_len(seq)
    structure_penalty = max(0.0, min(1.0, (guide_hairpin - 3) / 6.0))

    repeat_hairpin = rna_utils.max_inverted_repeat_len(repeat) if repeat else 0
    repeat_score = min(1.0, repeat_hairpin / 6.0) if repeat else None

    weights = [0.30, 0.25, 0.20, 0.25]
    values = [length_score, 1.0 - structure_penalty, gc_score]
    if repeat_score is None:
        weights.pop()
    else:
        values.append(repeat_score)
    score = sum(v * w for v, w in zip(values, weights)) / sum(weights)

    return {
        "spacer_len": length,
        "spacer_len_score": round(length_score, 4),
        "gc": round(gc, 4),
        "gc_score": round(gc_score, 4),
        "guide_hairpin_len": guide_hairpin,
        "guide_structure_penalty": round(structure_penalty, 4),
        "repeat_hairpin_len": repeat_hairpin,
        "repeat_hairpin_score": (
            round(repeat_score, 4) if repeat_score is not None else None),
        "omega_model": "omega_rna_rules",
    }, max(0.0, min(1.0, score))


def omega_rna_on_target_score(guide_seq, direct_repeat=None):
    """Return (score, model, features) using local omegaRNA rules."""
    features, score = omega_rna_features(guide_seq, direct_repeat)
    return score, "omega_rna_rules", features
