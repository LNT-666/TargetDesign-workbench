#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Compatibility helpers for legacy tuple and rich hit records."""

from collections.abc import Mapping

from search.alignment import reverse_complement_gapped


def as_hit_dict(match):
    """Return a hit dictionary while accepting legacy tuple records."""
    if isinstance(match, Mapping):
        return dict(match)
    if isinstance(match, (tuple, list)):
        if len(match) >= 4:
            target, start, mismatch, strand = match[:4]
        elif len(match) >= 3:
            target, start, mismatch = match[:3]
            strand = "+"
        else:
            raise ValueError("invalid match record: %r" % (match,))
        return {
            "target": target,
            "start": int(start),
            "mismatch": int(mismatch),
            "strand": strand,
            "indel": 0,
        }
    raise ValueError("invalid match record: %r" % (match,))


def hit_target(match):
    return as_hit_dict(match)["target"]


def hit_start(match):
    hit = as_hit_dict(match)
    return int(hit.get("target_start", hit.get("start", 0)))


def hit_mismatch(match):
    return int(as_hit_dict(match).get("mismatch", 0))


def hit_strand(match):
    return as_hit_dict(match).get("strand", "+")


def hit_indel(match):
    hit = as_hit_dict(match)
    return max(
        int(hit.get("indel") or 0),
        int(hit.get("rna_bulges") or 0)
        + int(hit.get("dna_bulges") or 0),
    )


def has_alignment(match):
    hit = as_hit_dict(match)
    return bool(
        hit.get("aligned_guide")
        and hit.get("aligned_target")
    )


def orient_rich_hit(match, guide_strand):
    """Orient a search-query alignment to the candidate guide strand."""
    hit = as_hit_dict(match)
    if not has_alignment(hit):
        return hit
    if str(guide_strand or "+").lower() in ("minus", "-"):
        hit["aligned_guide"] = reverse_complement_gapped(
            hit.get("aligned_guide") or "")
        hit["aligned_target"] = reverse_complement_gapped(
            hit.get("aligned_target") or "")
        if hit.get("pam"):
            hit["pam"] = reverse_complement_gapped(hit["pam"])
        hit["query_start"] = 0
        hit["query_end"] = len(
            (hit.get("aligned_guide") or "").replace("-", ""))
    return hit
