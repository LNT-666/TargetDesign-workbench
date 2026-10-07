#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Helpers for dropping table columns that are empty across every row.

The score/library TSV writers include several optional columns (e.g. on-target
or off-target model outputs, rule notes) that can be blank for the whole table
when the relevant model is not available.  Hiding these all-empty columns keeps
the result files readable instead of leaving an unused column behind.
"""


def is_blank(value):
    """Return True for values that should count as an empty cell."""
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    return False


def nonempty_columns(rows, columns, value_getter=None):
    """Return the subset of ``columns`` that has at least one non-blank cell.

    ``rows`` is a sequence of row mappings.  ``columns`` is the preferred
    order.  ``value_getter``, when provided, extracts a cell as
    ``value_getter(row, column)``; otherwise ``row.get(column)`` is used.  A
    column is kept whenever at least one row holds a real value, so numeric
    zero columns are kept while fully blank columns (including typo/unused
    keys) are removed.
    """
    getter = value_getter or (lambda row, col: row.get(col))
    keep = []
    for col in columns:
        for row in rows:
            if not is_blank(getter(row, col)):
                keep.append(col)
                break
    return keep


def nonempty_indices(row_values):
    """Return indices of columns that are non-blank in at least one row.

    ``row_values`` is an iterable of per-row cell lists that are parallel to
    the header list (each cell already formatted as a string, with ``""`` for
    an empty cell).  Used by the hand-written f-string TSV writers so they can
    reuse the regular ``csv`` writers' column filtering behaviour.
    """
    rows = list(row_values)
    if not rows:
        return []
    width = len(rows[0])
    keep = []
    for idx in range(width):
        if any(not is_blank(row[idx]) for row in rows):
            keep.append(idx)
    return keep


def mismatch_bucket_limit(max_mismatch, default=4):
    """Return a non-negative MM bucket limit."""
    try:
        limit = int(max_mismatch)
    except (TypeError, ValueError):
        limit = int(default)
    return max(0, limit)


def mismatch_bucket_columns(max_mismatch):
    """Return MM columns from MM0 through the configured mismatch budget."""
    limit = mismatch_bucket_limit(max_mismatch)
    return ["MM%d" % value for value in range(limit + 1)]


def mismatch_bucket_values(mm_counts, max_mismatch):
    """Collapse per-mismatch counts into columns matching the search budget.

    The final bucket is cumulative and represents ``>= max_mismatch``.  This
    preserves the historical MM3 meaning when the budget is 3 while allowing
    MM4 to be reported separately for a four-mismatch search.
    """
    limit = mismatch_bucket_limit(max_mismatch)
    counts = list(mm_counts or [])
    values = []
    for value in range(limit):
        values.append(counts[value] if value < len(counts) else 0)
    if limit == 0:
        final_count = counts[0] if counts else 0
    else:
        final_count = sum(counts[limit:])
    values.append(final_count)
    return values
