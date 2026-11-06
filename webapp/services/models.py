#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Model registry service: status list, setup and delete jobs.

Statuses mirror ``main.py``'s Model setup tab, including the deep-model loadability
correction (``crispr_m`` / ``deepcrispr`` / ``deepcas12a``), so the web tab and
the desktop tab never disagree.
"""

from __future__ import annotations

import os
import sys
from typing import Any, Dict

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WEBAPP = os.path.join(ROOT, "webapp")
SHARED = os.path.join(ROOT, "shared")
for _path in (WEBAPP, SHARED):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import schema  # noqa: E402
import scoring.deep_models as deep_models  # noqa: E402
import scoring.model_registry as model_registry  # noqa: E402


#: Labels shown by the desktop Model setup tab (main.py:1213-1230).
STATUS_LABELS = {
    "ready": "Ready",
    "ready_loaded": "Ready (scoring)",
    "ready_unavailable": "Set up (not loadable)",
    "ready_runtime_missing": "Runtime missing",
    "dependency_missing": "Runtime missing",
    "needs_conversion": "Needs conversion",
    "not_downloaded": "Not set up",
    "size_mismatch": "Size mismatch",
    "web_api": "Online API",
    "external": "External repository",
}

READY_STATUSES = ("ready", "ready_loaded")


adjust_status = deep_models.adjust_model_status


def deep_statuses() -> Dict[str, Any]:
    try:
        return dict(deep_models.model_statuses(load=False))
    except Exception:
        return {}


def list_models() -> Dict[str, Any]:
    """Model groups with status, path and actions for the Model setup tab."""
    status_details = model_registry.get_all_status_details()
    statuses = {
        key: detail["status"] for key, detail in status_details.items()
    }
    groups = []
    for group in schema.model_catalog():
        models = []
        for entry in group["models"]:
            key = entry["key"]
            status = adjust_status(key, statuses.get(key, "not_downloaded"))
            status_detail = status_details.get(key) or {
                "status": status,
                "errors": [],
                "warnings": [],
                "paths": {"model": model_registry.get_model_path(key) or ""},
            }
            path = model_registry.get_model_path(key) or ""
            models.append(dict(
                entry,
                status=status,
                status_label=STATUS_LABELS.get(status, status),
                path=path,
                has_file=bool(path) and os.path.isfile(path),
                is_ready=status in READY_STATUSES,
                status_detail=status_detail,
            ))
        groups.append(dict(group, models=models))
    return {
        "groups": groups,
        "models_dir": model_registry.models_dir(),
        "deep_statuses": deep_statuses(),
    }


def _check_key(key: str) -> Dict[str, Any]:
    info = model_registry.MODELS.get(key)
    if info is None:
        raise ValueError("unknown model: %s" % key)
    if not model_registry.is_downloadable(info):
        raise ValueError("%s cannot be set up or deleted" % key)
    return info


def setup_body(key: str):
    info = model_registry.MODELS.get(key) or {}
    name = info.get("name") or key

    def run(ctx) -> int:
        ctx.line("Setting up model: %s (%s)" % (key, name))
        last_percent = {"value": -1}

        def progress(downloaded, total):
            if not total:
                return
            percent = int(100 * downloaded / total)
            if percent != last_percent["value"]:
                last_percent["value"] = percent
                ctx.progress(percent, "Setting up %s" % name)

        def status(state, downloaded, total):
            ctx.line("model %s: %s (%s/%s bytes)"
                     % (key, state, downloaded, total or 0))

        path = model_registry.setup_model(
            key, progress_callback=progress, status_callback=status)
        ctx.line("Model ready: %s" % path)
        ctx.set_result({"model": key, "path": path, "action": "setup"})
        return 0

    return run


def download_body(key: str):
    """Backward-compatible alias for :func:`setup_body`."""
    return setup_body(key)


def delete_body(key: str):
    def run(ctx) -> int:
        model_registry.delete_model(key)
        ctx.line("Deleted local files for model: %s" % key)
        ctx.set_result({"model": key, "action": "delete"})
        return 0

    return run


def submit_setup(key: str, manager) -> Dict[str, Any]:
    info = _check_key(key)
    title = "Set up %s" % (info.get("name") or key)
    job_id = manager.create_job(
        "model", title, setup_body(key),
        {"model": key, "action": "setup", "title": title})
    return {"job_id": job_id, "title": title, "model": key}


def submit_download(key: str, manager) -> Dict[str, Any]:
    """Backward-compatible alias for :func:`submit_setup`."""
    return submit_setup(key, manager)


def submit_delete(key: str, manager) -> Dict[str, Any]:
    info = _check_key(key)
    title = "Delete %s" % (info.get("name") or key)
    job_id = manager.create_job(
        "model", title, delete_body(key),
        {"model": key, "action": "delete", "title": title})
    return {"job_id": job_id, "title": title, "model": key}
