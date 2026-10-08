#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Per-day run index for batch outputs.

Every batch run owns one flat folder named ``<YYYYMMDD>-<ID>``::

    output/<YYYYMMDD>-<ID>/
        run.json      run metadata (id, day, batch label, unit count, ...)
        run.log       the full console log of the run
        batch.json    normalised spec (reproduction input)
        manifest.tsv  one row per unit
        summary/batch_scores.tsv
        <unit_id>/    per-unit results

The four digit id is allocated within its calendar day, so every day gets its
own 0001..9999 space (9999 runs a day).  The first four runs of a day are the
reserved ids in :data:`RESERVED_IDS`; later runs continue from ``0005`` and
skip any reserved number they would hit.  A folder that exists already counts
as taken, so an id is never reused on the same day.
"""

from __future__ import annotations

import datetime
import json
import os
import re
import threading
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

#: Four digit run id (``0001`` .. ``9999``).
RUN_ID_RE = re.compile(r"^\d{4}$")

#: Eight digit day key (``YYYYMMDD``).
DAY_RE = re.compile(r"^\d{8}$")

#: ``<YYYYMMDD>-<ID>`` run folder name.
RUN_DIR_RE = re.compile(r"^(\d{8})-(\d{4})$")

#: strftime format of the day part of a run folder.
DAY_FORMAT = "%Y%m%d"

#: First four ids of every day (a little private joke: dates and a clock).
RESERVED_IDS: Tuple[str, ...] = ("0114", "0514", "1919", "0810")

#: Highest allocatable number; ``9999`` fits in four digits.
MAX_RUN_NUMBER = 9999

#: File names inside a run folder.
RUN_META_NAME = "run.json"
RUN_LOG_NAME = "run.log"

_ALLOC_LOCK = threading.Lock()


@dataclass(frozen=True)
class RunIndex:
    """One allocated run folder: its day, its id and its absolute path."""

    day: str
    run_id: str
    path: str

    @property
    def label(self) -> str:
        """``<YYYYMMDD>-<id>``; the folder name and the log/lookup handle."""

        return run_name(self.day, self.run_id)

    def to_dict(self) -> Dict[str, object]:
        return {"day": self.day, "run_id": self.run_id, "path": self.path}


def _as_datetime(when: Optional[object] = None) -> datetime.datetime:
    if when is None:
        return datetime.datetime.now()
    if isinstance(when, datetime.datetime):
        return when
    if isinstance(when, datetime.date):
        return datetime.datetime(when.year, when.month, when.day)
    raise TypeError("when must be a datetime/date or None, got %r" % (when,))


def day_key(when: Optional[object] = None) -> str:
    """Return the ``YYYYMMDD`` key of ``when`` (default: now)."""

    return _as_datetime(when).strftime(DAY_FORMAT)


def run_name(day: str, run_id: str) -> str:
    """Return the flat folder name of one run, ``<YYYYMMDD>-<ID>``."""

    return "%s-%s" % (day, run_id)


def run_dir(output_root: str, day: str, run_id: str) -> str:
    """Return the folder of one run (no existence check)."""

    return os.path.join(output_root, run_name(day, run_id))


def _scan_runs(output_root: str) -> List[Tuple[str, str]]:
    """Every ``(day, id)`` pair present under ``output_root``."""

    if not os.path.isdir(output_root):
        return []
    try:
        names = os.listdir(output_root)
    except OSError:
        return []
    found = []
    for name in names:
        match = RUN_DIR_RE.match(name)
        if match and os.path.isdir(os.path.join(output_root, name)):
            found.append((match.group(1), match.group(2)))
    return found


def existing_ids(output_root: str, day: str) -> set:
    """The run ids already present for one day."""

    return {run_id for found_day, run_id in _scan_runs(output_root) if found_day == day}


def existing_days(output_root: str) -> List[str]:
    """Every day that has at least one run folder (ascending)."""

    return sorted({day for day, _run_id in _scan_runs(output_root)})


def next_run_id(
    taken: Iterable[str], reserved: Sequence[str] = RESERVED_IDS
) -> str:
    """Pick the next free id given the ids already used that day.

    The first ``len(reserved)`` allocations of a day use the reserved ids in
    order; afterwards the counter continues from ``len(reserved) + 1`` and
    skips numbers that are already taken or reserved.
    """

    used = {str(item) for item in taken}
    reserved_list = [str(item) for item in reserved]
    if len(used) < len(reserved_list):
        candidate = reserved_list[len(used)]
        if candidate not in used:
            return candidate
    number = len(reserved_list) + 1
    while number <= MAX_RUN_NUMBER:
        candidate = "%04d" % number
        if candidate not in used and candidate not in reserved_list:
            return candidate
        number += 1
    raise RuntimeError(
        "no free run id left for the day (all four digit ids are used)"
    )


def allocate_run(
    output_root: str,
    when: Optional[object] = None,
    reserved: Sequence[str] = RESERVED_IDS,
) -> RunIndex:
    """Create and claim ``output_root/<YYYYMMDD>-<id>`` and return it.

    The folder is created with ``os.makedirs(..., exist_ok=False)`` so two
    concurrent allocations can never claim the same id.
    """

    day = day_key(when)
    os.makedirs(output_root, exist_ok=True)
    with _ALLOC_LOCK:
        for _ in range(MAX_RUN_NUMBER + 1):
            run_id = next_run_id(existing_ids(output_root, day), reserved)
            path = run_dir(output_root, day, run_id)
            try:
                os.makedirs(path)
            except FileExistsError:
                continue
            return RunIndex(day=day, run_id=run_id, path=path)
    raise RuntimeError("could not allocate a run id under %s" % output_root)


def parse_run_ref(ref: str) -> Tuple[str, str]:
    """Split a run reference into ``(day, run_id)``.

    Accepts ``<id>``, ``<day>-<id>``, ``<day>/<id>`` and ``<day>_<id>``.
    An empty day means "any day" (see :func:`find_run`).
    """

    text = str(ref or "").strip().replace("\\", "-")
    if not text:
        raise ValueError("empty run reference")
    for separator in ("/", "_"):
        text = text.replace(separator, "-")
    day, sep, run_id = text.partition("-")
    if sep:
        day = day.strip()
        run_id = run_id.strip()
        if not DAY_RE.match(day):
            raise ValueError("bad day in run reference: %r" % ref)
        if not RUN_ID_RE.match(run_id):
            raise ValueError("bad run id in run reference: %r" % ref)
        return day, run_id
    if DAY_RE.match(text):
        raise ValueError("run reference needs a four digit id: %r" % ref)
    if RUN_ID_RE.match(text):
        return "", text
    raise ValueError("bad run reference: %r" % ref)


def find_run(output_root: str, ref: str) -> Optional[RunIndex]:
    """Locate a run by id, newest day first when no day is given."""

    day, run_id = parse_run_ref(ref)
    if day:
        path = run_dir(output_root, day, run_id)
        if os.path.isdir(path):
            return RunIndex(day=day, run_id=run_id, path=path)
        return None
    for name in reversed(existing_days(output_root)):
        path = run_dir(output_root, name, run_id)
        if os.path.isdir(path):
            return RunIndex(day=name, run_id=run_id, path=path)
    return None


def list_runs(
    output_root: str, day: Optional[str] = None, limit: Optional[int] = None
) -> List[RunIndex]:
    """All runs under ``output_root``, newest day first, ids ascending."""

    runs = [
        RunIndex(
            day=found_day,
            run_id=run_id,
            path=run_dir(output_root, found_day, run_id),
        )
        for found_day, run_id in _scan_runs(output_root)
        if day is None or found_day == day
    ]
    runs.sort(key=lambda item: item.run_id)
    runs.sort(key=lambda item: item.day, reverse=True)
    if limit is not None and limit >= 0:
        runs = runs[:limit]
    return runs


def meta_path(run_path: str) -> str:
    return os.path.join(run_path, RUN_META_NAME)


def log_path(run_path: str) -> str:
    return os.path.join(run_path, RUN_LOG_NAME)


def write_meta(run_path: str, meta: Dict[str, object]) -> str:
    """Write ``run.json`` atomically and return its path."""

    path = meta_path(run_path)
    os.makedirs(run_path, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as handle:
        json.dump(meta, handle, ensure_ascii=False, indent=2, sort_keys=False)
        handle.write("\n")
    os.replace(tmp, path)
    return path


def read_meta(run_path: str) -> Dict[str, object]:
    """Read ``run.json``; an empty dict when missing or unreadable."""

    try:
        with open(meta_path(run_path), "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}
