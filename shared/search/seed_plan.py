#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared exhaustive seed planning for exact and indexed search."""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass
from typing import Iterable, Tuple


DEFAULT_MAX_SEED_VARIANTS = 500000


@dataclass(frozen=True)
class SeedSegment:
    start: int
    length: int
    allowed_mismatches: int

    @property
    def end(self) -> int:
        return self.start + self.length


@dataclass(frozen=True)
class SeedPlan:
    segments: Tuple[SeedSegment, ...]
    guaranteed: bool
    reason: str = ""
    estimated_variants: int = 0


def variant_count(seed_len: int, max_mismatch: int) -> int:
    """Number of sequences within ``max_mismatch`` substitutions."""
    count = 0
    for changes in range(0, max(0, int(max_mismatch)) + 1):
        count += math.comb(seed_len, changes) * (3 ** changes)
    return count


def _segmented_variant_work(segment_len: int, kmer_size: int,
                            max_mismatch: int) -> int:
    """Variant lookups needed for every k-mer window in one seed segment."""
    window_count = max(1, int(segment_len) - int(kmer_size) + 1)
    return window_count * variant_count(int(kmer_size), max_mismatch)


def iter_seed_variants(seed: str, max_mismatch: int) -> Iterable[str]:
    """Yield all sequence variants within an exact substitution budget."""
    seed = str(seed or "").upper()
    max_mismatch = max(0, min(int(max_mismatch), len(seed)))
    if max_mismatch == 0:
        yield seed
        return
    indexes = range(len(seed))
    for changes in range(0, max_mismatch + 1):
        for positions in itertools.combinations(indexes, changes):
            if changes == 0:
                yield seed
                continue
            for alternatives in itertools.product("ACGT", repeat=changes):
                chars = list(seed)
                for position, base in zip(positions, alternatives):
                    chars[position] = base
                yield "".join(chars)


def _partition(length: int, count: int) -> Tuple[int, ...]:
    base, remainder = divmod(length, count)
    return tuple(
        base + (1 if index < remainder else 0)
        for index in range(count)
    )


def build_seed_plan(
        probe_len: int,
        max_mismatch: int,
        max_bulge: int,
        seed_len: int,
        kmer_size: int,
        max_variants: int = DEFAULT_MAX_SEED_VARIANTS,
) -> SeedPlan:
    """Choose non-overlapping seeds with the pigeonhole guarantee ``N > B``.

    A missing guaranteed plan is never silently downgraded. Callers must either
    use an exhaustive backend or fail with ``plan.reason``.
    """
    probe_len = int(probe_len)
    max_mismatch = max(0, int(max_mismatch))
    max_bulge = max(0, int(max_bulge))
    # The stored k-mer length is the hard constraint. ``seed_len`` is only a
    # legacy preferred length; using it as a lower bound would make valid
    # indexed plans impossible (for example 20 nt guide, k=10, seed_len=12).
    minimum_seed_len = max(1, int(kmer_size))
    max_seed_count = probe_len // minimum_seed_len
    minimum_seed_count = max(1, max_bulge + 1)

    if max_seed_count < minimum_seed_count:
        return SeedPlan(
            segments=(SeedSegment(0, probe_len, max_mismatch),),
            guaranteed=False,
            reason=(
                "need at least %d non-overlapping %d-nt seeds to cover "
                "max_bulge=%d, but the guide only fits %d"
                % (minimum_seed_count, minimum_seed_len,
                   max_bulge, max_seed_count)
            ),
        )

    candidates = []
    for seed_count in range(minimum_seed_count, max_seed_count + 1):
        denominator = seed_count - max_bulge
        allowed = max_mismatch // denominator
        sizes = _partition(probe_len, seed_count)
        total_variants = sum(
            _segmented_variant_work(size, minimum_seed_len, allowed)
            for size in sizes
        )
        if max_variants and total_variants > max_variants:
            continue
        cursor = 0
        segments = []
        for size in sizes:
            segments.append(SeedSegment(cursor, size, allowed))
            cursor += size
        candidates.append((
            total_variants,
            allowed,
            seed_count,
            tuple(segments),
        ))

    if not candidates:
        return SeedPlan(
            segments=(SeedSegment(0, probe_len, max_mismatch),),
            guaranteed=False,
            reason=(
                "the exhaustive seed variants for max_mismatch=%d, "
                "max_bulge=%d exceed the configured cap %d"
                % (max_mismatch, max_bulge, max_variants)
            ),
        )

    total_variants, _allowed, _count, segments = min(
        candidates, key=lambda item: (item[0], item[2]))
    return SeedPlan(
        segments=segments,
        guaranteed=True,
        estimated_variants=total_variants,
    )
