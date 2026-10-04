#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Batch service (multi search scope x multi pattern) for the local web UI.

The web layer only translates a payload into a :class:`BatchSpec` and wraps the
shared :class:`BatchRunner`; validation, ordering and execution all live in
``shared/design`` (see ``docs/BATCH.md`` and ``docs/WEBAPP.md``).
"""

from __future__ import annotations

import csv
import os
import shutil
import sys
from datetime import datetime
from typing import Any, Callable, Dict, List

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WEBAPP = os.path.join(ROOT, "webapp")
SHARED = os.path.join(ROOT, "shared")
for _path in (WEBAPP, SHARED):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import schema  # noqa: E402
from design.batch_runner import BatchRunner, batch_root  # noqa: E402
from design.batch_spec import (  # noqa: E402
    DEFAULT_FASTA_SUFFIXES,
    BatchGroup,
    BatchSpec,
    PatternVariant,
    ScopeSpec,
    normalize_units,
    validate_spec,
)
from design.pattern_spec import PatternKind  # noqa: E402
from design.workbench_form import coerce_bool  # noqa: E402
from services import designer as designer_service  # noqa: E402


SIDES = ("target", "left", "right")

#: Plain form keys that belong to each pattern mode (derived from the schema).
PATTERN_KEYS_BY_MODE: Dict[str, tuple] = {
    mode: tuple(
        field["key"]
        for group in form.values()
        for field in group["fields"]
        if "key" in field
    )
    for mode, form in schema.PATTERN_FORMS.items()
}

#: Payload ``struct`` keys carried into ``shared`` and every pattern overlay.
STRUCT_KEYS = (
    "nuclease",
    "tnpb_subtype",
    "require_pam",
    "active_side",
    "side_presets",
    "side_on_target_models",
    "side_off_target_models",
)

#: Keys the batch kernel or the scope owns; never copied into ``shared``.
_SHARED_DROP = frozenset(
    ("search_fasta", "bed_regions", "input_mode", "result_label", "output_dir")
)

_BED_SUFFIXES = (".bed.gz", ".bed")


# --------------------------------------------------------------- payload
def collect_values(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Collect Designer form values exactly like ``designer.state_from_payload``."""

    payload = payload or {}
    values: Dict[str, Any] = dict(schema.DESIGNER_DEFAULTS)
    for key in schema.DESIGNER_FIELD_KEYS:
        if payload.get(key) is not None:
            values[key] = payload[key]
    incoming = payload.get("values")
    if isinstance(incoming, dict):
        for key, value in incoming.items():
            if value is not None:
                values[key] = value
    return values


def _string_map(raw, defaults) -> Dict[str, str]:
    merged = dict(defaults)
    if isinstance(raw, dict):
        for side, value in raw.items():
            if value is None or str(side) not in SIDES:
                continue
            merged[str(side)] = str(value)
    return merged


def struct_from_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """The Designer struct fields (``nuclease``, side maps, ...)."""

    payload = payload or {}
    values = collect_values(payload)

    def pick(key: str, default: str) -> str:
        raw = payload.get(key)
        if raw is None:
            raw = values.get(key)
        return str(raw) if raw not in (None, "") else default

    require_raw = payload.get("require_pam")
    if require_raw is None:
        require_raw = values.get("require_pam")
    return {
        "nuclease": pick("nuclease", "cas9"),
        "tnpb_subtype": pick("tnpb_subtype", "unknown"),
        "require_pam": coerce_bool(require_raw, True),
        "active_side": pick("active_side", "target"),
        "side_presets": _string_map(
            payload.get("side_presets"), designer_service.DEFAULT_SIDE_PRESETS
        ),
        "side_on_target_models": _string_map(
            payload.get("side_on_target_models"),
            designer_service.DEFAULT_ON_TARGET_MODELS,
        ),
        "side_off_target_models": _string_map(
            payload.get("side_off_target_models"),
            designer_service.DEFAULT_OFF_TARGET_MODELS,
        ),
    }


def _strip_suffix(name: str, suffixes) -> str:
    lowered = name.lower()
    for suffix in sorted(suffixes, key=len, reverse=True):
        if lowered.endswith(suffix):
            return name[: len(name) - len(suffix)]
    return name


def _derive_scope_id(path: str, is_bed: bool) -> str:
    base = os.path.basename(str(path or "").strip())
    suffixes = _BED_SUFFIXES if is_bed else DEFAULT_FASTA_SUFFIXES
    stem = _strip_suffix(base, suffixes)
    return stem or "scope"


def scopes_from_payload(payload: Dict[str, Any]) -> List[ScopeSpec]:
    """Parse the required ``scopes`` array; derive ids and de-duplicate names."""

    raw = (payload or {}).get("scopes")
    if not isinstance(raw, list) or not raw:
        raise ValueError("scopes must be a non-empty array")
    scopes: List[ScopeSpec] = []
    used: Dict[str, int] = {}
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            raise ValueError("scope %d must be an object" % index)
        search_fasta = str(item.get("search_fasta") or "").strip()
        regions = str(item.get("regions") or "").strip()
        if search_fasta and regions:
            raise ValueError("scope %d sets both search_fasta and regions" % index)
        if not search_fasta and not regions:
            raise ValueError(
                "scope %d needs search_fasta or regions" % index
            )
        is_bed = bool(regions)
        path = regions if is_bed else search_fasta
        scope_id = str(item.get("scope_id") or "").strip()
        if not scope_id:
            scope_id = _derive_scope_id(path, is_bed)
        count = used.get(scope_id, 0) + 1
        used[scope_id] = count
        if count > 1:
            scope_id = "%s_%d" % (scope_id, count)
            used.setdefault(scope_id, 0)
        scopes.append(
            ScopeSpec(
                scope_id=scope_id,
                search_fasta=search_fasta,
                regions=regions,
            )
        )
    return scopes


def pattern_from_designer(
    payload: Dict[str, Any], pattern_id: str
) -> PatternVariant:
    """Split a Designer payload into one pattern overlay."""

    payload = payload or {}
    pattern_id = str(pattern_id or "").strip()
    if not pattern_id:
        raise ValueError("pattern_id is required")
    mode = str(payload.get("mode") or PatternKind.SINGLE_MOTIF_FLANK.value)
    keys = PATTERN_KEYS_BY_MODE.get(mode)
    if keys is None:
        raise ValueError("unknown pattern mode: %s" % mode)
    values = collect_values(payload)
    overlay = {key: values[key] for key in keys if key in values}
    overlay.update(struct_from_payload(payload))
    return PatternVariant(pattern_id=pattern_id, mode=mode, overlay=overlay)


def _build_pattern(item: Dict[str, Any]) -> PatternVariant:
    if not isinstance(item, dict):
        raise ValueError("pattern must be an object")
    pattern_id = str(item.get("pattern_id") or "").strip()
    if not pattern_id:
        raise ValueError("pattern_id is required")
    overlay = item.get("overlay")
    if isinstance(overlay, dict):
        mode = str(item.get("mode") or PatternKind.SINGLE_MOTIF_FLANK.value)
        if mode not in PATTERN_KEYS_BY_MODE:
            raise ValueError("unknown pattern mode: %s" % mode)
        return PatternVariant(
            pattern_id=pattern_id, mode=mode, overlay=dict(overlay)
        )
    return pattern_from_designer(item, pattern_id)


def patterns_from_payload(payload: Dict[str, Any]) -> List[PatternVariant]:
    raw = (payload or {}).get("patterns")
    if not isinstance(raw, list) or not raw:
        raise ValueError("patterns must be a non-empty array")
    seen = set()
    patterns: List[PatternVariant] = []
    for item in raw:
        variant = _build_pattern(item)
        if variant.pattern_id in seen:
            raise ValueError("duplicate pattern_id: %s" % variant.pattern_id)
        seen.add(variant.pattern_id)
        patterns.append(variant)
    return patterns


def _groups_from_assignments(payload, patterns, scopes) -> List[BatchGroup]:
    raw = (payload or {}).get("assignments")
    assignments = raw if isinstance(raw, dict) else {}
    known = {scope.scope_id for scope in scopes}
    groups: List[BatchGroup] = []
    for pattern in patterns:
        selected = assignments.get(pattern.pattern_id)
        if selected is None:
            scope_ids = [scope.scope_id for scope in scopes]
        else:
            if not isinstance(selected, list):
                raise ValueError(
                    "assignments[%s] must be an array" % pattern.pattern_id
                )
            scope_ids = [str(item) for item in selected]
            unknown = [item for item in scope_ids if item not in known]
            if unknown:
                raise ValueError(
                    "assignments[%s] references unknown scope: %s"
                    % (pattern.pattern_id, unknown[0])
                )
        groups.append(
            BatchGroup(
                group_id="G_%s" % pattern.pattern_id,
                scope_ids=scope_ids,
                pattern_ids=[pattern.pattern_id],
            )
        )
    return groups


def groups_from_payload(payload, patterns, scopes) -> List[BatchGroup]:
    """UI path: one group per pattern from ``assignments``; else ``groups``."""

    raw = (payload or {}).get("groups")
    if raw is None:
        return _groups_from_assignments(payload, patterns, scopes)
    if not isinstance(raw, list) or not raw:
        raise ValueError("groups must be a non-empty array")
    groups: List[BatchGroup] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("group must be an object")
        groups.append(
            BatchGroup(
                group_id=str(item.get("group_id") or ""),
                scope_ids=[str(x) for x in (item.get("scope_ids") or [])],
                pattern_ids=[
                    str(x) for x in (item.get("pattern_ids") or [])
                ],
            )
        )
    return groups


def _shared_keys() -> List[str]:
    keys = [field["key"] for field in schema.COMMON_FIELDS]
    keys += [field["key"] for field in schema.RUN_FIELDS]
    keys += [
        "pair_rank_%s" % name for name in schema.PAIR_RANK_POLICY_FIELDS
    ]
    return keys


def shared_from_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Non-pattern Designer values plus the struct fields."""

    values = collect_values(payload)
    struct = struct_from_payload(payload)
    shared: Dict[str, Any] = {}
    for key in _shared_keys():
        if key in _SHARED_DROP:
            continue
        if key in values:
            shared[key] = values[key]
    for key in STRUCT_KEYS:
        shared[key] = struct[key]
    return shared


def _default_label() -> str:
    return "web-batch-%s" % datetime.now().strftime("%Y%m%d-%H%M%S")


def build_spec(payload: Dict[str, Any]) -> BatchSpec:
    payload = payload or {}
    label = str(payload.get("batch_label") or "").strip() or _default_label()
    scopes = scopes_from_payload(payload)
    patterns = patterns_from_payload(payload)
    groups = groups_from_payload(payload, patterns, scopes)
    return BatchSpec(
        batch_label=label,
        shared=shared_from_payload(payload),
        scopes=scopes,
        patterns=patterns,
        groups=groups,
    )


def preview(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Validate a batch without running it (missing files are warnings)."""

    try:
        spec = build_spec(payload)
    except ValueError as exc:
        return {
            "batch_label": "",
            "batch_root": "",
            "units": [],
            "errors": [str(exc)],
            "warnings": [],
        }
    errors, warnings = validate_spec(spec, dry_run=True)
    root = ""
    try:
        root = batch_root(spec.batch_label)
    except ValueError as exc:
        errors.append(str(exc))
    units = [
        {
            "unit_id": unit.unit_id,
            "scope_id": unit.scope_id,
            "pattern_id": unit.pattern_id,
        }
        for unit in normalize_units(spec)
    ]
    return {
        "batch_label": spec.batch_label,
        "batch_root": root,
        "units": units,
        "errors": errors,
        "warnings": warnings,
    }


def _resume(payload: Dict[str, Any]) -> bool:
    return coerce_bool((payload or {}).get("resume"), True)


def copy_artifacts(runner: BatchRunner, ctx) -> Dict[str, str]:
    """Copy the manifest and summary into ``<job_dir>/export/``."""

    export_dir = os.path.join(ctx.job_dir, "export")
    os.makedirs(export_dir, exist_ok=True)
    artifacts = {
        "batch_root": os.path.abspath(runner.batch_root_dir),
        "manifest": os.path.abspath(runner.manifest_path),
        "summary": os.path.abspath(runner.summary_path),
        "download_manifest": "export/manifest.tsv",
        "download_summary": "export/batch_scores.tsv",
    }
    for source, name in (
        (runner.manifest_path, "manifest.tsv"),
        (runner.summary_path, "batch_scores.tsv"),
    ):
        if os.path.isfile(source):
            shutil.copyfile(source, os.path.join(export_dir, name))
    return artifacts


def _manifest_counts(runner: BatchRunner) -> Dict[str, int]:
    counts = {"total": 0, "ok": 0, "failed": 0, "skipped": 0, "stopped": 0}
    try:
        with open(runner.manifest_path, "r", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                counts["total"] += 1
                status = (row.get("status") or "").strip()
                if status in counts:
                    counts[status] += 1
    except (OSError, ValueError):
        pass
    return counts


def job_body(payload: Dict[str, Any]) -> Callable[[Any], int]:
    """Return the lazy callable the job manager runs for a batch."""

    payload = payload or {}

    def run(ctx) -> int:
        spec = build_spec(payload)
        units = normalize_units(spec)
        runner = BatchRunner(
            spec,
            units,
            batch_root(spec.batch_label),
            on_line=ctx.line,
            resume=_resume(payload),
        )
        ctx.set_stop_hook(runner.stop)
        try:
            returncode = runner.run()
        except Exception as exc:  # keep the job from dying without a record
            ctx.line("Batch failed: %s" % exc)
            returncode = 1
        try:
            artifacts = copy_artifacts(runner, ctx)
        except Exception as exc:
            ctx.line("Could not copy batch artifacts: %s" % exc)
            artifacts = {}
        counts = _manifest_counts(runner)
        ctx.set_result({
            "batch_label": spec.batch_label,
            "batch_root": runner.batch_root_dir,
            "returncode": returncode,
            "units_total": counts["total"],
            "units_ok": counts["ok"],
            "units_failed": counts["failed"],
            "units_skipped": counts["skipped"],
        })
        ctx.set_outputs(artifacts)
        return returncode

    return run


def submit(payload: Dict[str, Any], manager) -> Dict[str, Any]:
    """Validate the payload and queue one batch job."""

    spec = build_spec(payload)
    errors, _warnings = validate_spec(spec, dry_run=False)
    if errors:
        raise ValueError(errors[0])
    root = batch_root(spec.batch_label)
    units = normalize_units(spec)
    if not units:
        raise ValueError("batch expands to zero units")
    title = "Batch %s (%d units)" % (spec.batch_label, len(units))
    params = {
        "batch_label": spec.batch_label,
        "batch_root": root,
        "unit_count": len(units),
        "request": payload,
    }
    job_id = manager.create_job("batch", title, job_body(payload), params)
    return {
        "job_id": job_id,
        "title": title,
        "batch_label": spec.batch_label,
        "batch_root": root,
        "unit_count": len(units),
    }
