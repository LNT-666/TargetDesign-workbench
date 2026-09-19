#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared engine choices and preflight checks for library workflows.

The desktop GUIs, the local web app and the CLI pipeline all use this module
so that the engine list and the "what will actually run" checks stay in sync.
"""

import os

from search.offtarget_backend import (
    MAX_EXACT_GENOME_BYTES, SearchParameterError, SearchParams, get_backend,
    resolve_engine, validate_search_params,
)

try:
    import scoring.model_registry as model_registry
except ImportError:  # pragma: no cover - import-time guard
    model_registry = None


# Full engine list exposed by the library pipeline. Order matters for UIs.
ENGINE_CHOICES = ["exact", "indexed", "blast", "gggenome", "auto"]

# Engines retired in 2026-09; kept only to raise a clear error for stale input.
REMOVED_ENGINES = ("bowtie2", "casoffinder")

# Older launchers (the legacy Library tab) keep a smaller, conservative list.
LEGACY_ENGINE_CHOICES = ["exact", "indexed", "blast", "auto"]

MODEL_KEYS = {
    "crispr_m": "crispr_m",
    "deepcrispr": "deepcrispr",
    "deepcpf1": "deepcpf1",
    "tiger": "tiger",
}

def validate_engine(name):
    """Raise ValueError unless name is one of the supported engines."""
    key = (name or "").lower()
    if key in REMOVED_ENGINES:
        raise ValueError(
            "Off-target engine %s was removed; choose from %s"
            % (key, ", ".join(ENGINE_CHOICES)))
    if key not in ENGINE_CHOICES:
        raise ValueError("Unknown off-target engine: %s (choose from %s)"
                         % (name, ", ".join(ENGINE_CHOICES)))
    return key


def _model_ready(key):
    if model_registry is None:
        return True, "model registry unavailable"
    try:
        status = model_registry.get_model_status(key)
    except Exception as exc:
        return False, str(exc)
    if status == "ready":
        return True, ""
    if status == "web_api":
        return True, "web API"
    if status == "size_mismatch":
        return False, "文件大小与预期不符"
    if status == "not_downloaded":
        return False, "模型文件未下载"
    return False, "模型状态: %s" % status


def preflight_library(engine, genome=None, index_path=None, blastdb=None,
                      on_target_model=None, off_target_model=None,
                      search_params=None):
    """Return (errors, warnings) for a library run.

    ``errors`` are hard failures that should stop the run; ``warnings`` are
    conditions the user should see but that the pipeline can still handle,
    usually by falling back or by building resources automatically.
    """
    errors = []
    warnings = []

    try:
        requested_engine = validate_engine(engine)
    except ValueError as exc:
        return [str(exc)], []
    search_params = search_params or SearchParams(max_bulge=0)
    genome_bytes = None
    if genome and os.path.isfile(genome):
        genome_bytes = os.path.getsize(genome)
    try:
        engine = resolve_engine(
            requested_engine, search_params, genome_size=genome_bytes)
        validate_search_params(engine, search_params)
    except SearchParameterError as exc:
        errors.append(str(exc))

    if genome and not os.path.isfile(genome):
        errors.append("基因组 FASTA 不存在: %s" % genome)

    if genome_bytes is not None and genome_bytes > MAX_EXACT_GENOME_BYTES:
        if engine == "exact":
            errors.append(
                "exact 引擎不适合大型基因组（当前文件 %.1f GB），"
                "请改用 BLAST、单染色体 exact 或先构建 indexed 索引"
                % (genome_bytes / 1024.0 ** 3))

    if engine == "indexed":
        if index_path:
            base = index_path
            for ext in (".ggi", ".json"):
                if base.endswith(ext):
                    base = base[:-len(ext)]
            ggi = base + ".ggi"
            meta = base + ".json"
            if not os.path.isfile(ggi) or not os.path.isfile(meta):
                warnings.append(
                    "索引不存在，出库时会自动构建（大基因组可能耗时且占用内存）")
        else:
            warnings.append("未指定索引前缀，出库时会按 FASTA 名在输出目录自动构建索引")
    elif engine == "blast":
        if blastdb:
            from search.blast_utils import (
                _blastdb_files_exist, blastdb_is_current,
            )
            prefix = blastdb
            for ext in (".nin", ".nsq", ".nhr", ".nal", ".nog"):
                if prefix.endswith(ext):
                    prefix = prefix[:-len(ext)]
            missing = [prefix + ext for ext in (".nin", ".nsq")
                       if not os.path.isfile(prefix + ext)]
            if missing:
                errors.append("BLAST 数据库不完整，缺少: %s" % ", ".join(missing))
            elif genome and os.path.isfile(genome) and \
                    not blastdb_is_current(genome, prefix):
                warnings.append(
                    "BLAST 数据库缺少有效 source manifest 或 FASTA 已变化，"
                    "运行前会自动重建"
                )
            elif _blastdb_files_exist(prefix) and not genome:
                warnings.append(
                    "无法校验 BLAST 数据库来源 manifest：未提供基因组 FASTA"
                )
        elif requested_engine == "auto":
            warnings.append(
                "auto 在大型基因组下回退到 BLAST，未提供 BLAST db，"
                "出库时会先构建数据库")
        else:
            warnings.append("未指定 BLAST db，出库时会先构建数据库")
    elif requested_engine == "auto":
        warnings.append(
            "auto 将按 auto_engine_candidates 的顺序"
            "在可用引擎中选择。")

    if not errors:
        backend = get_backend(engine)
        ok, reason = backend.available()
        if not ok:
            errors.append(reason)

    for model_name in (on_target_model, off_target_model):
        key = MODEL_KEYS.get((model_name or "").lower())
        if not key:
            continue
        ready, note = _model_ready(key)
        if not ready:
            warnings.append(
                "%s 模型未就绪（%s），评分将回退到内置规则" % (model_name, note))

    return errors, warnings
