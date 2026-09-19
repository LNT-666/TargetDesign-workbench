#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Small gapped alignments with explicit RNA/DNA bulge classification.

Coordinates in :class:`AlignmentRecord` are relative to the supplied target
window. Search backends convert them to genomic coordinates before exporting a
hit. A gap in the target (an extra query/guide base) is an RNA bulge; a gap in
the query (an extra target/DNA base) is a DNA bulge.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Optional


_COMPLEMENT = str.maketrans("ACGTN-", "TGCAN-")


def reverse_complement_gapped(seq: str) -> str:
    """Reverse-complement a sequence while preserving alignment gaps."""
    return str(seq or "").upper().translate(_COMPLEMENT)[::-1]


@dataclass(frozen=True)
class AlignmentRecord:
    """One full-query alignment against a target substring."""

    target_start: int
    target_end: int
    query_start: int
    query_end: int
    mismatches: int
    rna_bulges: int
    dna_bulges: int
    cigar: str
    query_aligned: str
    target_aligned: str

    @property
    def indels(self) -> int:
        return int(self.rna_bulges) + int(self.dna_bulges)

    @property
    def edit_cost(self) -> int:
        return 2 * int(self.mismatches) + 3 * self.indels

    def as_dict(self) -> dict:
        out = asdict(self)
        out["indel"] = self.indels
        return out


def cigar_from_operations(operations: list[str]) -> str:
    if not operations:
        return ""
    parts = []
    current = operations[0]
    count = 1
    for operation in operations[1:]:
        if operation == current:
            count += 1
            continue
        parts.append("%d%s" % (count, current))
        current = operation
        count = 1
    parts.append("%d%s" % (count, current))
    return "".join(parts)


def _cigar(operations: list[str]) -> str:
    """Backward-compatible alias for older internal imports."""
    return cigar_from_operations(operations)


def _better(candidate: tuple, current: Optional[tuple]) -> bool:
    """Lower score wins; ordering is deterministic for exact ties."""
    if current is None:
        return True
    return candidate < current


def align_global(query: str, target: str) -> AlignmentRecord:
    """Return a deterministic global alignment of ``query`` to ``target``.

    Cost is ``2 * mismatch + 3 * gap``. This deliberately prefers a
    substitution over a single-base bulge when both describe the same local
    change. Gap orientation follows the project convention:

    * ``I``: query base aligned to a target gap -> RNA bulge
    * ``D``: target base aligned to a query gap -> DNA bulge
    """
    query = str(query or "").upper().replace("U", "T")
    target = str(target or "").upper().replace("U", "T")
    q_len = len(query)
    t_len = len(target)

    # Cell values are (score, gaps, mismatches). Backtrace stores one of
    # D/M/X/I; the operation is interpreted when reconstructing the CIGAR.
    scores = [[None] * (t_len + 1) for _ in range(q_len + 1)]
    back = [[""] * (t_len + 1) for _ in range(q_len + 1)]
    scores[0][0] = (0, 0, 0)
    for j in range(1, t_len + 1):
        scores[0][j] = (3 * j, j, 0)
        back[0][j] = "D"
    for i in range(1, q_len + 1):
        scores[i][0] = (3 * i, i, 0)
        back[i][0] = "I"

    for i in range(1, q_len + 1):
        query_base = query[i - 1]
        for j in range(1, t_len + 1):
            target_base = target[j - 1]
            diagonal = scores[i - 1][j - 1]
            mismatch = int(query_base != target_base)
            diag_value = (
                diagonal[0] + 2 * mismatch,
                diagonal[1],
                diagonal[2] + mismatch,
            )
            up = scores[i - 1][j]
            up_value = (up[0] + 3, up[1] + 1, up[2])
            left = scores[i][j - 1]
            left_value = (left[0] + 3, left[1] + 1, left[2])

            choices = (
                (diag_value, "M" if not mismatch else "X"),
                (up_value, "I"),
                (left_value, "D"),
            )
            best_value, best_op = choices[0]
            best_key = (best_value, 0)
            for choice_index, (value, operation) in enumerate(choices[1:], 1):
                key = (value, choice_index)
                if key < best_key:
                    best_value, best_op, best_key = value, operation, key
            scores[i][j] = best_value
            back[i][j] = best_op

    i, j = q_len, t_len
    operations = []
    query_aligned = []
    target_aligned = []
    while i > 0 or j > 0:
        operation = back[i][j]
        if operation in ("M", "X"):
            query_aligned.append(query[i - 1])
            target_aligned.append(target[j - 1])
            i -= 1
            j -= 1
        elif operation == "I":
            # Query consumes a base while target has a gap.
            query_aligned.append(query[i - 1])
            target_aligned.append("-")
            i -= 1
        elif operation == "D":
            query_aligned.append("-")
            target_aligned.append(target[j - 1])
            j -= 1
        else:  # pragma: no cover - defensive guard
            raise RuntimeError("alignment traceback is incomplete")
        operations.append(operation)

    operations.reverse()
    query_aligned.reverse()
    target_aligned.reverse()
    return AlignmentRecord(
        target_start=0,
        target_end=t_len,
        query_start=0,
        query_end=q_len,
        mismatches=int(scores[q_len][t_len][2]),
        rna_bulges=sum(1 for op in operations if op == "I"),
        dna_bulges=sum(1 for op in operations if op == "D"),
        cigar=_cigar(operations),
        query_aligned="".join(query_aligned),
        target_aligned="".join(target_aligned),
    )


def best_alignment(
        window: str,
        query: str,
        center: int,
        max_bulge: int,
        max_mismatch: Optional[int] = None,
        accept_alignment=None,
) -> Optional[AlignmentRecord]:
    """Compare all non-gap and gapped target substrings near ``center``.

    The previous implementation returned a substitution-only alignment as soon
    as it met the mismatch budget. This routine always evaluates both classes
    and selects by ``(2*mismatch + 3*bulge, mismatch, bulge, length drift,
    distance from center)``.
    """
    window = str(window or "").upper().replace("U", "T")
    query = str(query or "").upper().replace("U", "T")
    query_len = len(query)
    if query_len == 0 or not window:
        return None

    center = max(0, min(int(center), max(0, len(window) - query_len)))
    max_bulge = max(0, int(max_bulge))
    best = None
    best_key = None
    min_len = max(1, query_len - max_bulge)
    max_len = min(len(window), query_len + max_bulge)
    start_lo = max(0, center - max_bulge)
    start_hi = min(len(window), center + max_bulge)

    for target_start in range(start_lo, start_hi + 1):
        for target_end in range(
                target_start + min_len,
                min(len(window), target_start + max_len) + 1):
            target = window[target_start:target_end]
            if not target:
                continue
            alignment = align_global(query, target)
            if alignment.indels > max_bulge:
                continue
            if max_mismatch is not None and \
                    alignment.mismatches > int(max_mismatch):
                continue
            if accept_alignment is not None and not accept_alignment(
                    target_start, target_end):
                continue
            key = (
                alignment.edit_cost,
                alignment.mismatches,
                alignment.indels,
                abs(len(target) - query_len),
                abs(target_start - center),
                target_start,
                target_end,
            )
            if _better(key, best_key):
                best_key = key
                best = AlignmentRecord(
                    target_start=target_start,
                    target_end=target_end,
                    query_start=0,
                    query_end=query_len,
                    mismatches=alignment.mismatches,
                    rna_bulges=alignment.rna_bulges,
                    dna_bulges=alignment.dna_bulges,
                    cigar=alignment.cigar,
                    query_aligned=alignment.query_aligned,
                    target_aligned=alignment.target_aligned,
                )
    return best
