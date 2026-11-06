#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Helpers for result-table columns and consistent numeric formatting.

The score/library TSV writers include several optional columns (e.g. on-target
or off-target model outputs, rule notes) that can be blank for the whole table
when the relevant model is not available.  Hiding these all-empty columns keeps
the result files readable instead of leaving an unused column behind.
"""

import math
import numbers
import re


DEFAULT_DECIMAL_PLACES = 2
_DECIMAL_TEXT = re.compile(
    r"^[+-]?(?:\d+\.\d*|\.\d+|\d+[eE][+-]?\d+|\d+\.\d*[eE][+-]?\d+)$"
)


def format_output_value(value, decimals=DEFAULT_DECIMAL_PLACES):
    """Format a result-table value, keeping counts and labels unchanged.

    Integral values stay integral so ranks, positions, and mismatch counts do
    not grow a meaningless ``.00`` suffix.  Real values are rendered with a
    fixed number of decimal places.  Text, ``None``, and non-finite values are
    returned as their normal string form.
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, numbers.Integral):
        return str(int(value))
    if isinstance(value, numbers.Real):
        number = float(value)
        if math.isfinite(number):
            if number == 0:
                number = 0.0
            return f"{number:.{decimals}f}"
        return str(value)
    return str(value)


def format_display_value(value, decimals=DEFAULT_DECIMAL_PLACES):
    """Format a value for a GUI/Web table cell.

    Besides native numeric values, this also handles decimal-looking strings
    read back from an older TSV file.  Integer-looking strings are left alone
    so identifiers with leading zeros are not rewritten.
    """
    if isinstance(value, str):
        text = value.strip()
        if _DECIMAL_TEXT.match(text):
            try:
                return format_output_value(float(text), decimals)
            except ValueError:
                return value
        return value
    return format_output_value(value, decimals)


def format_output_row(row, decimals=DEFAULT_DECIMAL_PLACES):
    """Return a copy of a row with numeric cells formatted for output."""
    return {
        key: format_output_value(value, decimals)
        for key, value in row.items()
    }


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
