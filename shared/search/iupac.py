#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""IUPAC-aware regex helpers for motif search."""

import re


IUPAC_REGEX = {
    "A": "A",
    "C": "C",
    "G": "G",
    "T": "T",
    "U": "T",
    "R": "[AG]",
    "Y": "[CT]",
    "S": "[GC]",
    "W": "[AT]",
    "K": "[GT]",
    "M": "[AC]",
    "D": "[AGT]",
    "H": "[ACT]",
    "V": "[ACG]",
    "B": "[CGT]",
    "N": "[ACGT]",
}


def iupac_to_regex(pattern):
    """Convert an IUPAC motif to a regex character class string."""
    return "".join(IUPAC_REGEX.get(base, re.escape(base)) for base in pattern.upper())


def find_all_iupac_matches(sequence, pattern):
    """Yield (start, matched_sequence) for all matches, including overlaps."""
    regex = iupac_to_regex(pattern)
    for match in re.finditer(f"(?=({regex}))", sequence.upper()):
        yield match.start(), match.group(1)


def find_all_iupac_positions(sequence, pattern):
    """Return all 0-based start positions for an IUPAC motif."""
    return [start for start, _ in find_all_iupac_matches(sequence, pattern)]
