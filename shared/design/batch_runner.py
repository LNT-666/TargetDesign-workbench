#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Serial batch execution over a :class:`BatchSpec`.

``BatchRunner`` expands a validated batch into units (one search scope x one
pattern configuration), runs each unit through the existing ``PatternRunner``
pipeline one after another, records a manifest, and concatenates the per-unit
score tables into a single summary.  See ``docs/BATCH.md``.
"""

from __future__ import annotations

import csv
import datetime
import os
import re
from typing import Any, Dict, List, Optional

from design.batch_spec import (
    BatchSpec,
    BatchUnit,
    build_unit_form_state,
    write_batch_json,
)
from design.pattern_runner import (
    STOPPED_RETURN_CODE,
    PatternRunner,
)
from design.pattern_spec import PatternKind
from design.workbench_form import build_pattern_spec, build_runner_config
from utils.paths import default_output_dir


_BATCH_LABEL_RE = re.compile(r"^[A-Za-z0-9._-]+$")

#: Fixed manifest column order (see ``docs/BATCH.md``).
MANIFEST_COLUMNS: List[str] = [
    "unit_id",
    "scope_id",
    "pattern_id",
    "status",
    "returncode",
    "started",
    "finished",
    "unit_dir",
    "main_table",
    "message",
]

#: Columns prepended to each summary row.
SUMMARY_KEY_COLUMNS: List[str] = [
    "batch_id",
    "unit_id",
    "scope_id",
    "pattern_id",
]

#: Manifest statuses whose main table may be concatenated into the summary.
_SUMMARY_STATUSES = ("ok", "skipped")


def batch_root(batch_label: str) -> str:
    """Return ``default_output_dir()/<batch_label>`` after validating the label."""

    label = (batch_label or "").strip()
    if (
        not label
        or label in (".", "..")
        or not _BATCH_LABEL_RE.match(label)
    ):
        raise ValueError(
            "illegal batch_label: %r (allowed: A-Za-z0-9._-, no paths)"
            % batch_label
        )
    return os.path.join(default_output_dir(), label)


def main_scores_path(kind: Any, unit_dir: str) -> str:
    """Map a pattern kind to its canonical main score table inside ``unit_dir``."""

    resolved = kind if isinstance(kind, PatternKind) else PatternKind(kind)
    if resolved is PatternKind.Y_CENTERED_MOTIFS:
        name = "scores.sorted.tsv"
    else:
        name = "query_scores_sorted.tsv"
    return os.path.join(unit_dir, name)


def _rel_posix(path: str, root: str) -> str:
    rel = os.path.relpath(os.path.abspath(path), os.path.abspath(root))
    return rel.replace("\\", "/")


def _read_tsv(path: str):
    with open(path, "r", encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle, delimiter="\t"))
    if not rows:
        return [], []
    return rows[0], rows[1:]


class BatchRunner:
    """Run a batch serially and aggregate the results."""

    def __init__(
        self,
        spec: BatchSpec,
        units: List[BatchUnit],
        batch_root_dir: str,
        on_line: Optional[Any] = None,
        resume: bool = True,
    ) -> None:
        self.spec = spec
        self.units = list(units or [])
        self.batch_root_dir = batch_root_dir
        self._on_line = on_line
        self.resume = bool(resume)
        self._rows: List[Dict[str, str]] = []
        self._prior_rows: List[Dict[str, str]] = []
        self._stop = False
        self._current: Optional[PatternRunner] = None
        self.manifest_path = os.path.join(batch_root_dir, "manifest.tsv")
        self.summary_path = os.path.join(
            batch_root_dir, "summary", "batch_scores.tsv"
        )
        self.batch_json_path = os.path.join(batch_root_dir, "batch.json")

    # -- output ---------------------------------------------------------
    def _emit(self, line: Any) -> None:
        """Forward one progress line, never letting a bad handler abort the run."""

        if self._on_line is None:
            return
        try:
            self._on_line(str(line))
        except Exception:
            pass

    @staticmethod
    def _now() -> str:
        return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def stop(self) -> None:
        """Ask the batch to stop; safe between units and during the current one."""

        self._stop = True
        runner = self._current
        if runner is not None:
            try:
                runner.stop()
            except Exception:
                pass

    # -- run ------------------------------------------------------------
    def run(self) -> int:
        os.makedirs(self.batch_root_dir, exist_ok=True)
        write_batch_json(self.spec, self.units, self.batch_json_path)

        self._prior_rows = self._load_prior_manifest()
        prior = {row["unit_id"]: row for row in self._prior_rows}
        if not self.resume and os.path.isfile(self.manifest_path):
            self._backup_manifest()
            self._prior_rows = []
            prior = {}

        total = len(self.units)
        self._rows = []
        stopped = False
        for index, unit in enumerate(self.units, start=1):
            if self._stop:
                stopped = True
                break
            self._emit("PROGRESS_TARGET: %d/%d" % (index, total))
            row = self._run_one(unit, prior)
            self._rows.append(row)
            self._write_manifest()
            percent = int(round(index * 100.0 / total)) if total else 100
            self._emit("PROGRESS: batch %d" % percent)
            if row["status"] == "stopped":
                stopped = True
                break

        self._write_manifest()
        self._write_summary()
        if stopped or self._stop:
            return STOPPED_RETURN_CODE
        if any(row["status"] == "failed" for row in self._rows):
            return 1
        return 0

    def _run_one(
        self, unit: BatchUnit, prior: Dict[str, Dict[str, str]]
    ) -> Dict[str, str]:
        started = self._now()
        unit_dir = os.path.join(self.batch_root_dir, unit.unit_id)
        unit_rel = _rel_posix(unit_dir, self.batch_root_dir)

        if self.resume:
            old = prior.get(unit.unit_id)
            if old and (old.get("status") or "") in ("ok", "skipped"):
                main_rel = old.get("main_table") or ""
                main_abs = os.path.join(
                    self.batch_root_dir, main_rel.replace("/", os.sep)
                )
                if main_rel and os.path.isfile(main_abs):
                    return self._row(
                        unit,
                        "skipped",
                        old.get("returncode", ""),
                        started,
                        self._now(),
                        unit_rel,
                        main_rel,
                        "resumed",
                    )

        os.makedirs(unit_dir, exist_ok=True)
        try:
            state = build_unit_form_state(self.spec, unit)
            pattern_spec = build_pattern_spec(state)
            config = build_runner_config(state, pattern_spec)
            config.output_dir = unit_dir
            config.run_label = ""
            runner = PatternRunner(pattern_spec, config)
            self._current = runner
            try:
                returncode = runner.run_pipeline(
                    on_line=self._emit, start=0, end=None
                )
            finally:
                self._current = None
        except Exception as exc:  # noqa: BLE001 - isolate each unit
            return self._row(
                unit,
                "failed",
                "",
                started,
                self._now(),
                unit_rel,
                "",
                "%s: %s" % (type(exc).__name__, exc),
            )

        main_path = main_scores_path(pattern_spec.kind, unit_dir)
        main_rel = _rel_posix(main_path, self.batch_root_dir)
        if returncode == STOPPED_RETURN_CODE:
            return self._row(
                unit,
                "stopped",
                str(returncode),
                started,
                self._now(),
                unit_rel,
                main_rel,
                "stopped by user",
            )
        if returncode != 0:
            return self._row(
                unit,
                "failed",
                str(returncode),
                started,
                self._now(),
                unit_rel,
                main_rel,
                "pipeline returned %s" % returncode,
            )
        if not os.path.isfile(main_path):
            self._emit(
                "WARN: %s finished but main table missing: %s"
                % (unit.unit_id, main_rel)
            )
        return self._row(
            unit,
            "ok",
            str(returncode),
            started,
            self._now(),
            unit_rel,
            main_rel,
            "",
        )

    def _row(
        self,
        unit: BatchUnit,
        status: str,
        returncode: Any,
        started: str,
        finished: str,
        unit_rel: str,
        main_rel: str,
        message: str,
    ) -> Dict[str, str]:
        return {
            "unit_id": unit.unit_id,
            "scope_id": unit.scope_id,
            "pattern_id": unit.pattern_id,
            "status": status,
            "returncode": str(returncode),
            "started": started,
            "finished": finished,
            "unit_dir": unit_rel,
            "main_table": main_rel,
            "message": message,
        }

    # -- persistence ----------------------------------------------------
    def _load_prior_manifest(self) -> List[Dict[str, str]]:
        rows: List[Dict[str, str]] = []
        if not os.path.isfile(self.manifest_path):
            return rows
        try:
            with open(self.manifest_path, "r", encoding="utf-8", newline="") as handle:
                for row in csv.DictReader(handle, delimiter="\t"):
                    unit_id = (row.get("unit_id") or "").strip()
                    if unit_id:
                        rows.append(row)
        except OSError:
            return []
        return rows

    def _backup_manifest(self) -> None:
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        target = os.path.join(
            self.batch_root_dir, "manifest.%s.tsv" % stamp
        )
        try:
            os.replace(self.manifest_path, target)
        except OSError:
            return
        self._emit(
            "INFO: previous manifest backed up to %s" % os.path.basename(target)
        )

    def _merged_rows(self) -> List[Dict[str, str]]:
        """This run's rows, then prior-manifest rows not seen this run.

        Keeps the manifest and the summary complete after a partial
        (``--only``) run, where ``self._rows`` only covers the selected
        units.
        """
        merged: List[Dict[str, str]] = list(self._rows)
        seen = {row.get("unit_id", "") for row in self._rows}
        for old in self._prior_rows:
            unit_id = (old.get("unit_id") or "").strip()
            if not unit_id or unit_id in seen:
                continue
            seen.add(unit_id)
            merged.append(
                {column: old.get(column, "") for column in MANIFEST_COLUMNS}
            )
        return merged

    def _write_manifest(self) -> None:
        merged = self._merged_rows()
        tmp = self.manifest_path + ".tmp"
        with open(tmp, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=MANIFEST_COLUMNS,
                delimiter="\t",
                lineterminator="\n",
            )
            writer.writeheader()
            for row in merged:
                writer.writerow(
                    {column: row.get(column, "") for column in MANIFEST_COLUMNS}
                )
        os.replace(tmp, self.manifest_path)

    def _write_summary(self) -> None:
        os.makedirs(os.path.dirname(self.summary_path), exist_ok=True)
        tables = []
        headers = []
        for row in self._merged_rows():
            if row["status"] not in _SUMMARY_STATUSES or not row["main_table"]:
                continue
            path = os.path.join(
                self.batch_root_dir, row["main_table"].replace("/", os.sep)
            )
            if not os.path.isfile(path):
                self._emit(
                    "WARN: summary skipped missing table for %s: %s"
                    % (row["unit_id"], row["main_table"])
                )
                continue
            header, data = _read_tsv(path)
            tables.append((row, header, data))
            headers.append(header)

        key_columns = list(SUMMARY_KEY_COLUMNS)
        source_columns = {name for header in headers for name in header}
        renamed = {}
        for index, name in enumerate(key_columns):
            if name in source_columns:
                renamed[name] = "batch_%s" % name
                key_columns[index] = renamed[name]
        if renamed:
            self._emit(
                "INFO: summary key columns renamed to avoid clashes: %s"
                % ", ".join(
                    "%s->%s" % (old, new) for old, new in renamed.items()
                )
            )

        union: List[str] = []
        seen = set()
        for header in headers:
            for name in header:
                if name not in seen:
                    seen.add(name)
                    union.append(name)

        tmp = self.summary_path + ".tmp"
        with open(tmp, "w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
            writer.writerow(key_columns + union)
            for row, header, data in tables:
                keys = [
                    self.spec.batch_label,
                    row["unit_id"],
                    row["scope_id"],
                    row["pattern_id"],
                ]
                for values in data:
                    source = dict(zip(header, values))
                    writer.writerow(
                        keys + [source.get(name, "") for name in union]
                    )
        os.replace(tmp, self.summary_path)
