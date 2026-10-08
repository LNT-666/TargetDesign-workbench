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
from design.batch_runner import (  # noqa: E402
    BatchRunner,
    validate_batch_label,
)
from design.batch_spec import (  # noqa: E402
    DEFAULT_FASTA_SUFFIXES,
    BatchGroup,
    BatchSpec,
    PatternVariant,
    ScopeSpec,
    normalize_units,
    validate_spec,
)
from design.pattern_spec import PatternKind, default_pattern_name  # noqa: E402
from design.workbench_form import build_pattern_spec, coerce_bool  # noqa: E402
from services import designer as designer_service  # noqa: E402
from utils.paths import default_output_dir  # noqa: E402
from utils.run_index import (  # noqa: E402
    RUN_LOG_NAME,
    RUN_META_NAME,
    allocate_run,
    find_run,
    list_runs as list_run_indexes,
    meta_path,
    read_meta,
    write_meta as write_run_meta,
)


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
    (
        "search_fasta",
        "bed_regions",
        "input_mode",
        "result_label",
        "output_dir",
        "mask_fasta",
        "mask_same_as_target",
    )
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
        mask_fasta = str(item.get("mask_fasta") or "").strip()
        raw_same = item.get("mask_same_as_target")
        if raw_same is None or (
            isinstance(raw_same, str) and not raw_same.strip()
        ):
            mask_same_as_target = not mask_fasta
        else:
            mask_same_as_target = coerce_bool(raw_same, not mask_fasta)
        scopes.append(
            ScopeSpec(
                scope_id=scope_id,
                search_fasta=search_fasta,
                regions=regions,
                mask_fasta=mask_fasta,
                mask_same_as_target=mask_same_as_target,
            )
        )
    return scopes


def _default_pattern_id(item: Dict[str, Any]) -> str:
    """Name an id-less pattern from the spec its payload describes."""

    overlay = item.get("overlay")
    if isinstance(overlay, dict):
        state_payload = {
            "mode": str(
                item.get("mode") or PatternKind.SINGLE_MOTIF_FLANK.value
            ),
            "values": dict(overlay),
        }
    else:
        state_payload = item
    try:
        state = designer_service.state_from_payload(state_payload)
        return default_pattern_name(build_pattern_spec(state))
    except Exception as exc:
        raise ValueError("pattern_id is required") from exc


def pattern_from_designer(
    payload: Dict[str, Any], pattern_id: str
) -> PatternVariant:
    """Split a Designer payload into one pattern overlay."""

    payload = payload or {}
    pattern_id = str(pattern_id or "").strip()
    if not pattern_id:
        pattern_id = _default_pattern_id(payload)
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
    overlay = item.get("overlay")
    if isinstance(overlay, dict):
        if not pattern_id:
            pattern_id = _default_pattern_id(item)
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
        explicit_id = (
            isinstance(item, dict)
            and bool(str(item.get("pattern_id") or "").strip())
        )
        variant = _build_pattern(item)
        if explicit_id:
            if variant.pattern_id in seen:
                raise ValueError(
                    "duplicate pattern_id: %s" % variant.pattern_id
                )
        else:
            base = variant.pattern_id
            suffix = 2
            while variant.pattern_id in seen:
                variant.pattern_id = "%s_%d" % (base, suffix)
                suffix += 1
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
        validate_batch_label(spec.batch_label)
        root = default_output_dir()
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
    """Copy the manifest, summary, run log and metadata into ``export/``."""

    export_dir = os.path.join(ctx.job_dir, "export")
    os.makedirs(export_dir, exist_ok=True)
    log_path = getattr(
        runner, "log_path", os.path.join(runner.batch_root_dir, RUN_LOG_NAME)
    )
    artifacts = {
        "run_dir": os.path.abspath(runner.batch_root_dir),
        "batch_root": os.path.abspath(runner.batch_root_dir),
        "manifest": os.path.abspath(runner.manifest_path),
        "summary": os.path.abspath(runner.summary_path),
        "log": os.path.abspath(log_path),
        "download_manifest": "export/manifest.tsv",
        "download_summary": "export/batch_scores.tsv",
        "download_log": "export/" + RUN_LOG_NAME,
        "download_meta": "export/" + RUN_META_NAME,
    }
    for source, name in (
        (runner.manifest_path, "manifest.tsv"),
        (runner.summary_path, "batch_scores.tsv"),
        (log_path, RUN_LOG_NAME),
        (meta_path(runner.batch_root_dir), RUN_META_NAME),
    ):
        if source and os.path.isfile(source):
            shutil.copyfile(source, os.path.join(export_dir, name))
    return artifacts


def manifest_counts(manifest_path: str) -> Dict[str, int]:
    """Status counts of one run's manifest (all zero when it is missing)."""

    counts = {"total": 0, "ok": 0, "failed": 0, "skipped": 0, "stopped": 0}
    if not os.path.isfile(manifest_path):
        return counts
    try:
        with open(manifest_path, "r", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                counts["total"] += 1
                status = (row.get("status") or "").strip()
                if status in counts:
                    counts[status] += 1
    except (OSError, ValueError):
        pass
    return counts


#: Manifest columns echoed into a run detail table (subset of the manifest).
RUN_TABLE_COLUMNS: tuple = ("unit_id", "scope_id", "pattern_id", "status", "returncode")


def manifest_rows(manifest_path: str) -> List[Dict[str, str]]:
    'One manifest as row dicts (missing or unreadable file -> empty list).'

    if not os.path.isfile(manifest_path):
        return []
    rows: List[Dict[str, str]] = []
    try:
        with open(manifest_path, "r", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                if not (row.get("unit_id") or "").strip():
                    continue
                rows.append(
                    {
                        column: (row.get(column) or "").strip()
                        for column in RUN_TABLE_COLUMNS
                    }
                )
    except (OSError, ValueError):
        return rows
    return rows


def job_body(
    payload: Dict[str, Any],
    run_root: str,
    run_meta: Dict[str, Any] = None,
    batch_label: str = "",
) -> Callable[[Any], int]:
    """Return the lazy callable the job manager runs for a batch."""

    payload = payload or {}
    run_meta = dict(run_meta or {})

    def run(ctx) -> int:
        spec = build_spec(payload)
        if batch_label:
            spec.batch_label = batch_label
        units = normalize_units(spec)
        runner = BatchRunner(
            spec,
            units,
            run_root,
            on_line=ctx.line,
            resume=_resume(payload),
            run_meta=run_meta or None,
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
        counts = manifest_counts(runner.manifest_path)
        result = {
            "batch_label": spec.batch_label,
            "batch_root": runner.batch_root_dir,
            "run_id": run_meta.get("label", ""),
            "returncode": returncode,
            "units_total": counts["total"],
            "units_ok": counts["ok"],
            "units_failed": counts["failed"],
            "units_skipped": counts["skipped"],
        }
        ctx.set_result(result)
        ctx.set_outputs(artifacts)
        return returncode

    return run


def resolve_run(
    payload: Dict[str, Any], unit_count: int, batch_label: str
) -> Dict[str, Any]:
    """Allocate (or reuse) the run folder and return its metadata."""

    payload = payload or {}
    output_root = default_output_dir()
    ref = str(payload.get("run_id") or "").strip()
    if ref:
        index = find_run(output_root, ref)
        if index is None:
            raise ValueError("no run %r under %s" % (ref, output_root))
    else:
        index = allocate_run(output_root)
    meta = {
        "run_id": index.run_id,
        "day": index.day,
        "label": index.label,
        "batch_label": batch_label,
        "created": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "unit_count": unit_count,
        "resume": _resume(payload),
        "source": "webapp",
    }
    try:
        write_run_meta(index.path, meta)
    except OSError:
        pass
    return {"index": index, "meta": meta}


def submit(payload: Dict[str, Any], manager) -> Dict[str, Any]:
    """Validate the payload, allocate a run id and queue one batch job."""

    spec = build_spec(payload)
    errors, _warnings = validate_spec(spec, dry_run=False)
    if errors:
        raise ValueError(errors[0])
    validate_batch_label(spec.batch_label)
    units = normalize_units(spec)
    if not units:
        raise ValueError("batch expands to zero units")
    resolved = resolve_run(payload, len(units), spec.batch_label)
    index = resolved["index"]
    run_meta = resolved["meta"]
    title = "Batch %s (%d units)" % (spec.batch_label, len(units))
    params = {
        "batch_label": spec.batch_label,
        "run_id": index.label,
        "batch_root": index.path,
        "unit_count": len(units),
        "request": payload,
    }
    job_id = manager.create_job(
        "batch",
        title,
        job_body(payload, index.path, run_meta, spec.batch_label),
        params,
    )
    return {
        "job_id": job_id,
        "title": title,
        "batch_label": spec.batch_label,
        "run_id": index.label,
        "batch_root": index.path,
        "unit_count": len(units),
    }


#: Files offered for download and shown in a run detail view.
RUN_DOWNLOAD_FILES: tuple = (
    "run.json",
    "run.log",
    "batch.json",
    "manifest.tsv",
    "summary/batch_scores.tsv",
)


def _run_payload(index) -> Dict[str, Any]:
    """One run as JSON: identity, metadata, manifest counts and files."""

    meta = read_meta(index.path)
    counts = manifest_counts(os.path.join(index.path, "manifest.tsv"))
    files = []
    for name in RUN_DOWNLOAD_FILES:
        path = os.path.join(index.path, name.replace("/", os.sep))
        if not os.path.isfile(path):
            continue
        try:
            size = os.path.getsize(path)
        except OSError:
            size = 0
        files.append({"name": name, "path": path, "size": size})
    return {
        "run_id": index.label,
        "day": index.day,
        "id": index.run_id,
        "path": index.path,
        "batch_label": meta.get("batch_label", ""),
        "created": meta.get("created", ""),
        "unit_count": meta.get("unit_count", counts["total"]),
        "units": counts,
        "columns": list(RUN_TABLE_COLUMNS),
        "rows": manifest_rows(os.path.join(index.path, "manifest.tsv")),
        "files": files,
    }


def list_runs(limit=20, day=None) -> Dict[str, Any]:
    """Recent runs (one batch = one run id), newest day first."""

    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = 20
    limit = max(1, min(200, limit))
    day = (day or "").strip() or None
    indexes = list_run_indexes(default_output_dir(), day=day, limit=limit)
    return {
        "output_root": default_output_dir(),
        "runs": [_run_payload(index) for index in indexes],
    }


def run_detail(ref) -> Dict[str, Any]:
    """One run by code; raises FileNotFoundError so the route returns 404."""

    index = find_run(default_output_dir(), str(ref or "").strip())
    if index is None:
        raise FileNotFoundError("run not found: %s" % ref)
    return _run_payload(index)


def run_file_path(ref, relative: str) -> str:
    """Resolve a download inside one run folder, rejecting path escapes."""

    index = find_run(default_output_dir(), str(ref or "").strip())
    if index is None:
        raise FileNotFoundError("run not found: %s" % ref)
    rel = str(relative or "").strip().replace("\\", "/")
    parts = [part for part in rel.split("/") if part]
    if not parts or any(part in (".", "..") for part in parts):
        raise ValueError("invalid file: %r" % relative)
    base = os.path.abspath(index.path)
    path = os.path.abspath(os.path.join(base, *parts))
    if os.path.commonpath([path, base]) != base:
        raise ValueError("invalid file: %r" % relative)
    if not os.path.isfile(path):
        raise FileNotFoundError("file not found: %s" % rel)
    return path
