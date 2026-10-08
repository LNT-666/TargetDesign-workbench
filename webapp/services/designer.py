#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Pattern Designer service for the local web UI.

Nothing here re-implements the form mapping: specs and runner configs come from
``shared/design/workbench_form.py``, the same module ``designer_workbench.py``
wraps, so a web run and a desktop run of the same form values are identical.
"""

from __future__ import annotations

import csv
import os
import re
import sys
import time
import urllib.parse
from typing import Any, Dict, List, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WEBAPP = os.path.join(ROOT, "webapp")
SHARED = os.path.join(ROOT, "shared")
for _path in (WEBAPP, SHARED):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import schema  # noqa: E402
from design.pattern_runner import PatternRunner, RunnerConfig  # noqa: E402
from design.pattern_spec import PatternKind, default_pattern_name  # noqa: E402
from design.workbench_form import (  # noqa: E402
    WorkbenchFormState,
    active_side_updates,
    build_pattern_spec,
    build_runner_config,
    coerce_bool,
    default_run_label,
    readiness_errors,
    resolved_memory_limit,
    side_model_options,
    side_preset_updates,
)
from output.candidate_export import (  # noqa: E402
    SUPPORTED_FORMATS,
    export_selected,
)
from utils import system_memory  # noqa: E402
from utils.paths import default_output_dir  # noqa: E402


HIDDEN_COLUMNS = tuple(schema.HIDDEN_CANDIDATE_COLUMNS)
EXTRACT_MISSING_MESSAGE = "Extracted targets not found. Run Find Targets first."
STAGES = ("find", "score")
SIDES = ("target", "left", "right")
CONFIRM_POLICIES = ("yes", "no")

_CAS9_MODELS = side_model_options("cas9")
DEFAULT_SIDE_PRESETS = {side: "cas9" for side in SIDES}
DEFAULT_ON_TARGET_MODELS = {
    side: _CAS9_MODELS["on_target_default"] for side in SIDES
}
DEFAULT_OFF_TARGET_MODELS = {
    side: _CAS9_MODELS["off_target_default"] for side in SIDES
}

EXPORT_FORMATS = tuple(SUPPORTED_FORMATS)
_EXPORT_BASE_NAMES = {
    "csv": "candidates",
    "tsv": "candidates",
    "fasta": "candidates",
    "bed": "candidates",
    "xlsx": "candidates",
    "unique_guides": "unique_guides",
    "library": "library_input",
}

#: Table the browser shows and exports. ``concise`` is the historical
#: candidate-column view; ``full`` is the run's deliverable table, the same
#: file the pipeline lands under ``output_dir`` (``<label>_scores.tsv``).
RESULT_VIEWS = ("concise", "full")
#: Formats that make sense for the full deliverable table; ``fasta`` / ``bed``
#: / ``unique_guides`` / ``library`` only reinterpret candidate rows.
FULL_EXPORT_FORMATS = ("csv", "tsv", "xlsx")
RESULTS_MISSING_MESSAGE = "Output table not found. Run Score & Off-target first."
_FULL_EXPORT_BASE_NAME = "results"


def _string_map(raw, defaults):
    merged = dict(defaults)
    if isinstance(raw, dict):
        for side, value in raw.items():
            if value is None or str(side) not in SIDES:
                continue
            merged[str(side)] = str(value)
    return merged


def state_from_payload(payload: Dict[str, Any]) -> WorkbenchFormState:
    """Build the shared form state from a web request body.

    Pattern fields may be sent at the top level (``{"motif": "TTAT"}``) or
    inside ``values``; ``values`` wins when both are present.
    """
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
    mode = str(payload.get("mode") or PatternKind.SINGLE_MOTIF_FLANK.value)
    return WorkbenchFormState(
        values=values,
        mode=mode,
        input_mode=str(payload.get("input_mode") or "sequence"),
        nuclease=str(payload.get("nuclease") or "cas9"),
        tnpb_subtype=str(payload.get("tnpb_subtype") or "unknown"),
        require_pam=coerce_bool(payload.get("require_pam"), True),
        active_side=str(payload.get("active_side") or "target"),
        side_presets=_string_map(
            payload.get("side_presets"), DEFAULT_SIDE_PRESETS),
        side_on_target_models=_string_map(
            payload.get("side_on_target_models"), DEFAULT_ON_TARGET_MODELS),
        side_off_target_models=_string_map(
            payload.get("side_off_target_models"), DEFAULT_OFF_TARGET_MODELS),
    )


def preview(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Describe the pattern and report everything that blocks a run."""
    state = state_from_payload(payload)
    result: Dict[str, Any] = {
        "mode": state.mode,
        "describe": "",
        "errors": [],
        "warnings": [],
        "memory_resolved": None,
        "run_label": "",
        "pattern_name": "",
    }
    try:
        result["memory_resolved"] = resolved_memory_limit(state)
    except ValueError as exc:
        result["warnings"].append("Memory limit: %s" % exc)
    try:
        spec = build_pattern_spec(state)
        spec.validate()
        result["describe"] = spec.describe()
        result["pattern_name"] = default_pattern_name(spec)
        result["run_label"] = (
            state.value("result_label").strip()
            or default_run_label(state, spec)
        )
    except Exception as exc:
        result["warnings"].append("Pattern: %s" % exc)
    result["errors"] = list(readiness_errors(state))
    return result


def preset_update(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Per-side ``Apply``: the field values plus the model candidates."""
    side = str(payload.get("side") or "target")
    if side not in SIDES:
        raise ValueError("unknown side: %s" % side)
    preset = str(payload.get("preset") or "custom")
    return {
        "side": side,
        "preset": preset,
        "updates": side_preset_updates(preset, side),
        "models": side_model_options(preset),
    }


def active_side_update(payload: Dict[str, Any]) -> Dict[str, Any]:
    """``Use for Run``: the rules the newly active side imposes."""
    state = state_from_payload(payload)
    side = str(payload.get("active_side") or state.active_side)
    if side not in SIDES:
        raise ValueError("unknown side: %s" % side)
    state.active_side = side
    return {
        "side": side,
        "updates": active_side_updates(state),
        "models": side_model_options(state.side_preset(side)),
    }


def build_runner(payload: Dict[str, Any]) -> PatternRunner:
    state = state_from_payload(payload)
    spec = build_pattern_spec(state)
    spec.validate()
    config = build_runner_config(state, spec)
    return PatternRunner(spec, config)


def require_extract_output(runner: PatternRunner) -> None:
    """Raise unless ``Find Targets`` already produced extraction output."""
    path = runner.extract_output_path()
    if runner.spec.kind is PatternKind.Y_CENTERED_MOTIFS:
        found = os.path.isdir(path)
    else:
        found = os.path.isfile(path)
    if not found:
        raise ValueError(EXTRACT_MISSING_MESSAGE)


def extract_reader(payload: Dict[str, Any]) -> PatternRunner:
    """Runner used only to read extraction output (no genome preparation)."""
    state = state_from_payload(payload)
    spec = build_pattern_spec(state)
    spec.validate()
    return PatternRunner(spec, RunnerConfig(output_dir=default_output_dir()))

def _memory_log_line(config) -> Optional[str]:
    if config.max_memory_mode == "auto":
        snapshot = system_memory.memory_snapshot()
        return (
            "Memory limit: auto, resolved=%d MiB (50%% total, 75%% available "
            "guard; total=%d MiB, available=%d MiB)"
            % (config.max_memory_mb, snapshot["total_mb"],
               snapshot["available_mb"])
        )
    if config.max_memory_mode == "custom":
        return "Memory limit: custom, resolved=%d MiB" % config.max_memory_mb
    return "Memory limit: unlimited"


def job_body(payload: Dict[str, Any], start: int, end: Optional[int],
             confirm_policy: str = "yes"):
    """Return the callable the job manager runs for a designer stage."""

    def run(ctx) -> int:
        runner = build_runner(payload)
        ctx.set_stop_hook(runner.stop)
        memory_line = _memory_log_line(runner.config)
        if memory_line:
            ctx.line(memory_line)
        ctx.line("Run label: %s" % runner.config.run_label)

        def on_prompt(request):
            kind = str((request or {}).get("kind") or "unknown")
            reason = str((request or {}).get("reason") or "")
            ctx.line("[auto-confirm] %s|%s" % (kind, reason))
            return confirm_policy != "no"

        returncode = runner.run_pipeline(
            on_line=ctx.line,
            start=start,
            end=end,
            on_prompt=on_prompt,
        )
        if returncode == 0:
            result = {
                "run_label": runner.config.run_label,
                "output_dir": runner.config.output_dir,
                "extract_output": runner.extract_output_path(),
            }
            outputs = {
                "search_fasta": runner.config.search_fasta,
                "bed_regions": runner.config.regions,
                "output_dir": runner.config.output_dir,
                "extract_output": runner.extract_output_path(),
            }
            extra_paths: Dict[str, Any] = {}
            run_dir = str(runner.run_dir() or "").strip()
            if run_dir:
                extra_paths["run_dir"] = run_dir
                extra_paths["params_file"] = os.path.join(run_dir, "params.json")
            for key, value in runner.deliverable_paths().items():
                extra_paths[str(key)] = value
            for key, value in extra_paths.items():
                path = str(value or "").strip()
                if not path or not os.path.exists(path):
                    continue
                result[key] = path
                outputs[key] = path
            ctx.set_result(result)
            ctx.set_outputs(outputs)
        return returncode

    return run


def submit(payload: Dict[str, Any], manager) -> Dict[str, Any]:
    """Validate the form and queue one pipeline stage."""
    stage = str(payload.get("stage") or "find").lower()
    if stage not in STAGES:
        raise ValueError("Unknown stage: %s (use find or score)" % stage)
    confirm_policy = str(payload.get("confirm_policy") or "yes").lower()
    if confirm_policy not in CONFIRM_POLICIES:
        raise ValueError("Unknown confirm policy: %s" % confirm_policy)

    state = state_from_payload(payload)
    errors = readiness_errors(state)
    if errors:
        raise ValueError(errors[0])
    spec = build_pattern_spec(state)
    spec.validate()
    config = build_runner_config(state, spec)

    if stage == "find":
        start, end, title = 0, 1, "Find Targets"
    else:
        start, end, title = 1, None, "Score & Off-target"
        require_extract_output(PatternRunner(spec, config))

    params = {
        "stage": stage,
        "title": title,
        "run_label": config.run_label,
        "output_dir": config.output_dir,
        "confirm_policy": confirm_policy,
        "request": payload,
    }
    job_id = manager.create_job(
        "designer", title,
        job_body(payload, start, end, confirm_policy), params)
    return {
        "job_id": job_id,
        "stage": stage,
        "title": title,
        "run_label": config.run_label,
        "output_dir": config.output_dir,
    }


def job_request(manager, job_id: str) -> Dict[str, Any]:
    """Return the designer request a job was created from."""
    params = manager.job_params(job_id)
    request = params.get("request")
    if not isinstance(request, dict):
        raise ValueError("job %s has no designer parameters" % job_id)
    return request


def candidates(job_id: str, manager) -> Dict[str, Any]:
    """Candidate table for a job, from ``read_extract_candidates()``."""
    runner = extract_reader(job_request(manager, job_id))
    rows = runner.read_extract_candidates()
    columns = [
        column for column in runner.spec.candidate_columns()
        if column not in HIDDEN_COLUMNS
    ]
    for row in rows:
        for key in row:
            if key not in columns and key not in HIDDEN_COLUMNS:
                columns.append(key)
    rendered = [
        {column: str(row.get(column, "")) for column in columns}
        for row in rows
    ]
    return {"columns": columns, "rows": rendered, "total": len(rendered)}


def _read_delimited_table(path: str) -> Dict[str, Any]:
    """Read a TSV deliverable into an ordered ``{columns, rows}`` table."""
    with open(path, "r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        columns = [str(name) for name in (reader.fieldnames or [])]
        rows = [
            {
                column: "" if raw.get(column) is None else str(raw.get(column))
                for column in columns
            }
            for raw in reader
        ]
    return {"columns": columns, "rows": rows, "total": len(rows)}


def results(job_id: str, manager) -> Dict[str, Any]:
    """The run's deliverable table, i.e. the file landed under ``output_dir``.

    ``job.outputs['scores']`` is the path the pipeline actually wrote, so the
    browser shows the same table as the command line (``<label>_scores.tsv``,
    or ``<label>_scores.sorted.tsv`` for Y-ZBP runs).
    """
    status = manager.get_job(job_id) or {}
    outputs = status.get("outputs") or {}
    path = str(outputs.get("scores") or "").strip()
    if not path or not os.path.isfile(path):
        return {
            "columns": [], "rows": [], "total": 0,
            "available": False, "file": None,
        }
    data = _read_delimited_table(path)
    data["available"] = True
    data["file"] = path
    return data


def sanitize_label(label: str) -> str:
    """Same file-name rules as designer_workbench._export_selected."""
    label = re.sub(r"[/\\]+", "-", str(label or ""))
    label = re.sub(r"[^A-Za-z0-9._-]+", "_", label).strip("._-")
    return label or "results"


def export_filename(label: str, fmt: str, stamp: Optional[str] = None,
                    base_name: Optional[str] = None) -> str:
    extension = ".tsv" if fmt in ("unique_guides", "library") else ".%s" % fmt
    base_name = base_name or _EXPORT_BASE_NAMES.get(fmt, "export")
    stamp = stamp or time.strftime("%Y%m%d_%H%M%S")
    return "%s_%s_%s%s" % (sanitize_label(label), base_name, stamp, extension)


def export_rows(job_id: str, payload: Dict[str, Any], manager) -> Dict[str, Any]:
    """Write selected candidate rows (concise) or the run output table (full).

    ``full`` reproduces the deliverable table the pipeline wrote under
    ``output_dir`` -- the same table the web UI shows in the ``full`` view --
    while ``concise`` keeps the historical candidate-column export.
    """
    fmt = str(payload.get("format") or "csv").lower()
    if fmt not in EXPORT_FORMATS:
        raise ValueError(
            "Unsupported export format: %s (choose from %s)"
            % (fmt, ", ".join(EXPORT_FORMATS)))
    view = str(
        payload.get("columns") or payload.get("view") or "concise").lower()
    if view not in RESULT_VIEWS:
        raise ValueError(
            "Unsupported table: %s (choose from %s)"
            % (view, ", ".join(RESULT_VIEWS)))
    if view == "full":
        if fmt not in FULL_EXPORT_FORMATS:
            raise ValueError(
                "The full output table can only be exported as %s"
                % ", ".join(FULL_EXPORT_FORMATS))
        data = results(job_id, manager)
        if not data.get("available"):
            raise ValueError(RESULTS_MISSING_MESSAGE)
    else:
        data = candidates(job_id, manager)
    selection = payload.get("rows", "all")
    if selection in (None, "all", "All", ""):
        rows = list(data["rows"])
    elif isinstance(selection, list):
        rows = []
        for index in selection:
            try:
                position = int(index)
            except (TypeError, ValueError):
                continue
            if 0 <= position < len(data["rows"]):
                rows.append(data["rows"][position])
    else:
        raise ValueError('rows must be "all" or a list of row indexes')
    if not rows:
        raise ValueError("No rows selected for export")

    params = manager.job_params(job_id)
    label = payload.get("label") or params.get("run_label") or "results"
    base_name = _FULL_EXPORT_BASE_NAME if view == "full" else None
    filename = os.path.basename(str(
        payload.get("filename") or export_filename(label, fmt, None, base_name)))
    export_dir = os.path.join(manager.job_dir(job_id), "export")
    os.makedirs(export_dir, exist_ok=True)
    path = os.path.join(export_dir, filename)
    written = export_selected(rows, path, fmt)
    relative = "export/" + filename
    return {
        "written": written,
        "file": relative,
        "format": fmt,
        "download_url": "/api/jobs/%s/download?file=%s"
        % (job_id, urllib.parse.quote(relative)),
    }
