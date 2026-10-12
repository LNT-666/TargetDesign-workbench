#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read-only identifier candidates for the web Data prep Target/Mask inputs.

The desktop builds a combobox from an annotation file with a "load list" button;
the web panel has no such button. This module answers that need without any job
and without writing files: it parses the annotation once per file identity and
reuses the shared ``load_gene_list`` implementation, then applies the same
filter/sort rule as the desktop ``filter_combobox_by_input``.
"""

from __future__ import annotations

import os
import sys
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WEBAPP = os.path.join(ROOT, "webapp")
SHARED = os.path.join(ROOT, "shared")
for _path in (WEBAPP, SHARED):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import schema  # noqa: E402
from data.annotation_utils import load_gene_list  # noqa: E402

#: Default and bounds for the number of identifiers returned (task D3).
DEFAULT_LIMIT = 50
MIN_LIMIT = 1
MAX_LIMIT = 500
#: Fallback identifier type when the request omits or misspells one (task D2).
DEFAULT_ID_TYPE = "gene_name"

#: Shared ``gene_cache`` in the sense of ``load_gene_list``: it maps a path to
#: ``{"attrs_list": [...]}``, so all four id types are served by one parse.
CACHE = {}
#: File identity per path: ``(st_mtime_ns, st_size)``; a change invalidates it.
_STAT = {}
#: Guards ``CACHE``/``_STAT`` only; parsing happens outside the lock so a slow
#: first parse never queues other requests (task B3).
_LOCK = threading.Lock()


def _stat_key(path):
    try:
        info = os.stat(path)
    except OSError:
        return None
    return (info.st_mtime_ns, info.st_size)


def _normalise_limit(limit):
    """Task D3: default 50, clamp to [1, 500]; bad input silently defaults."""
    if limit is None:
        return DEFAULT_LIMIT
    text = str(limit).strip()
    if not text:
        return DEFAULT_LIMIT
    try:
        value = int(text)
    except ValueError:
        return DEFAULT_LIMIT
    return max(MIN_LIMIT, min(MAX_LIMIT, value))


def filter_genes(values, query, limit=None):
    """Filter/sort identifiers like the desktop ``filter_combobox_by_input``.

    Empty ``query`` returns the alphabetically first ``limit`` items; otherwise
    items containing ``query`` (case-insensitive) are kept, sorted so prefix
    matches come first and the rest follow alphabetically.
    """
    limit = _normalise_limit(limit)
    items = list(values)
    text = (query or "").strip()
    if text:
        lowered = text.lower()
        items = [item for item in items if lowered in item.lower()]
        items.sort(key=lambda item: (not item.lower().startswith(lowered), item))
    else:
        items.sort()
    matched = len(items)
    return {
        "matched": matched,
        "truncated": matched > limit,
        "genes": items[:limit],
    }


def _load_values(path, id_type):
    """Return the deduped identifier list for ``id_type``, parsing at most once."""
    key = _stat_key(path)
    with _LOCK:
        fresh = key is not None and path in CACHE and _STAT.get(path) == key
        if not fresh:
            # Drop a stale entry so ``load_gene_list`` re-parses the file.
            CACHE.pop(path, None)
            _STAT.pop(path, None)
    values = load_gene_list(path, id_type, None, CACHE, None)
    with _LOCK:
        if key is not None:
            _STAT[path] = key
    return values


def suggest(annotation, id_type=None, query=None, limit=None):
    """Return contract A1: candidates for one annotation file and id type."""
    raw = (annotation or "").strip()
    if not raw:
        raise ValueError("Annotation file is required")
    path = os.path.abspath(raw)
    if not os.path.isfile(path):
        raise ValueError("Annotation file not found: %s" % path)
    kind = (id_type or "").strip()
    if kind not in schema.ID_TYPES:
        kind = DEFAULT_ID_TYPE
    values = _load_values(path, kind)
    result = filter_genes(values, query, limit)
    return {
        "annotation": path,
        "id_type": kind,
        "total": len(values),
        "matched": result["matched"],
        "truncated": result["truncated"],
        "genes": result["genes"],
    }
