#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Model registry service: status list, download and delete jobs.

Statuses mirror ``main.py``'s Models tab, including the deep-model loadability
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


#: Labels shown by the desktop Models tab (main.py:1213-1230).
STATUS_LABELS = {
    "ready": "Ready",
    "ready_loaded": "Ready (scoring)",
    "ready_unavailable": "Ready (not loadable)",
    "ready_runtime_missing": "Downloaded (runtime missing)",
    "dependency_missing": "Downloaded (runtime missing)",
    "needs_conversion": "Downloaded (needs conversion)",
    "not_downloaded": "Not downloaded",
    "size_mismatch": "Size mismatch",
    "web_api": "Online API",
    "external": "External repository",
}

READY_STATUSES = (
    "ready",
    "ready_loaded",
    "ready_unavailable",
    "ready_runtime_missing",
    "dependency_missing",
)


def adjust_status(key: str, status: str) -> str:
    """Deep-model loadability correction, copied from main.py:1203-1210."""
    if key == "crispr_m" and status == "ready":
        loaded = deep_models.crispr_m_status(load=False) == "ready"
        return "ready_loaded" if loaded else "ready_unavailable"
    if key == "deepcrispr" and status == "ready":
        available = deep_models.DeepCrisprPredictor.available()
        return "ready" if available else "ready_runtime_missing"
    if key == "deepcas12a" and status == "ready":
        available = deep_models.DeepCas12aPredictor.available()
        return "ready" if available else "ready_runtime_missing"
    return status


def deep_statuses() -> Dict[str, Any]:
    try:
        return dict(deep_models.model_statuses(load=False))
    except Exception:
        return {}


def list_models() -> Dict[str, Any]:
    """Model groups with status, path and actions for the Models tab."""
    statuses = model_registry.get_all_statuses()
    groups = []
    for group in schema.model_catalog():
        models = []
        for entry in group["models"]:
            key = entry["key"]
            status = adjust_status(key, statuses.get(key, "not_downloaded"))
            path = model_registry.get_model_path(key) or ""
            models.append(dict(
                entry,
                status=status,
                status_label=STATUS_LABELS.get(status, status),
                path=path,
                has_file=bool(path) and os.path.isfile(path),
                is_ready=status in READY_STATUSES,
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
        raise ValueError("%s cannot be downloaded or deleted" % key)
    return info


def download_body(key: str):
    info = model_registry.MODELS.get(key) or {}
    name = info.get("name") or key

    def run(ctx) -> int:
        ctx.line("Downloading model: %s (%s)" % (key, name))
        last_percent = {"value": -1}

        def progress(downloaded, total):
            if not total:
                return
            percent = int(100 * downloaded / total)
            if percent != last_percent["value"]:
                last_percent["value"] = percent
                ctx.progress(percent, "Downloading %s" % name)

        def status(state, downloaded, total):
            ctx.line("model %s: %s (%s/%s bytes)"
                     % (key, state, downloaded, total or 0))

        path = model_registry.download_model(
            key, progress_callback=progress, status_callback=status)
        ctx.line("Model ready: %s" % path)
        ctx.set_result({"model": key, "path": path, "action": "download"})
        return 0

    return run


def delete_body(key: str):
    def run(ctx) -> int:
        model_registry.delete_model(key)
        ctx.line("Deleted local files for model: %s" % key)
        ctx.set_result({"model": key, "action": "delete"})
        return 0

    return run


def submit_download(key: str, manager) -> Dict[str, Any]:
    info = _check_key(key)
    title = "Download %s" % (info.get("name") or key)
    job_id = manager.create_job(
        "model", title, download_body(key),
        {"model": key, "action": "download", "title": title})
    return {"job_id": job_id, "title": title, "model": key}


def submit_delete(key: str, manager) -> Dict[str, Any]:
    info = _check_key(key)
    title = "Delete %s" % (info.get("name") or key)
    job_id = manager.create_job(
        "model", title, delete_body(key),
        {"model": key, "action": "delete", "title": title})
    return {"job_id": job_id, "title": title, "model": key}