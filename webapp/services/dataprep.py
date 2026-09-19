#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Data preparation service: the desktop "Data prep" workflow on the web.

Genome/annotation preparation, Search-scope (Target) and Mask extraction, BLAST
database build and genome index build. Heavy steps run as children of the job
executor, so their stdout (including ``PROGRESS:`` lines) streams into the job
log exactly like the desktop progress bar.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WEBAPP = os.path.join(ROOT, "webapp")
SHARED = os.path.join(ROOT, "shared")
for _path in (WEBAPP, SHARED):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from data.annotation_utils import (  # noqa: E402
    ensure_plain_fasta,
    is_gzip_file,
    open_annotation_text,
    plain_fasta_is_current,
)
from data.local_extract import get_region_sequence  # noqa: E402
from search.blast_utils import ensure_blastdb  # noqa: E402
from utils.child_process import (  # noqa: E402
    popen_kwargs,
    register_child,
    terminate_process_tree,
    unregister_child,
)


DOWNLOAD_SCRIPT = os.path.join("shared", "data", "download_data.py")
UTR_SCRIPT = os.path.join("shared", "data", "add_utrs_to_gff.py")
INDEX_SCRIPT = os.path.join("tools", "build_genome_index.py")

UTR_TYPES = ("five_prime_UTR", "three_prime_UTR", "5'UTR", "3'UTR")
REGION_NUMBER_TYPES = ("Specific exon", "Specific intron")


def _clean(value) -> str:
    return str(value or "").strip()


def _read_json(path: str) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def require_output_dir(payload: Dict[str, Any]) -> str:
    output_dir = _clean(payload.get("output_dir"))
    if not output_dir:
        raise ValueError("Output Directory is required")
    return output_dir


def require_file(value, label: str) -> str:
    path = _clean(value)
    if not path:
        raise ValueError("%s is required" % label)
    if not os.path.isfile(path):
        raise ValueError("%s not found: %s" % (label, path))
    return path


def _run_command(cmd: List[str], ctx, cwd: Optional[str] = None,
                 env: Optional[Dict[str, str]] = None) -> int:
    """Run a child process, streaming its output into the job log."""
    ctx.line("$ " + " ".join(str(part) for part in cmd))
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=cwd,
        env=env,
        **popen_kwargs()
    )
    register_child(proc)
    ctx.set_stop_hook(lambda: terminate_process_tree(proc))
    try:
        assert proc.stdout is not None
        for raw_line in proc.stdout:
            ctx.line(raw_line.rstrip("\n"))
        returncode = proc.wait()
    finally:
        unregister_child(proc)
        terminate_process_tree(proc)
        try:
            if proc.stdout is not None:
                proc.stdout.close()
        except Exception:
            pass
    return returncode


def prepare_genome(raw_genome, output_dir: str, ctx) -> str:
    """Plain-text Genome FASTA path for a possibly gzipped input."""
    path = require_file(raw_genome, "Genome FASTA")
    prepared = ensure_plain_fasta(
        path, log_func=ctx.line, fallback_dir=output_dir or None)
    if not prepared:
        raise ValueError("Genome FASTA could not be prepared: %s" % path)
    return prepared


def prepare_annotation(raw_annotation, output_dir: str, ctx) -> str:
    """Add UTRs to a GTF/GFF3 when needed; mirrors main.py's cache rules."""
    path = require_file(raw_annotation, "Annotation file")
    os.makedirs(output_dir, exist_ok=True)
    is_gz = is_gzip_file(path)

    base = os.path.basename(path)
    while True:
        lowered = base.lower()
        for suffix in (".gz", ".gff", ".gff3", ".gtf"):
            if lowered.endswith(suffix):
                base = base[: -len(suffix)]
                break
        else:
            break

    if "_with_utrs" in base and not is_gz:
        ctx.line("Annotation file already carries UTRs: %s" % path)
        return path

    has_utr = False
    try:
        with open_annotation_text(path) as handle:
            for _ in range(100):
                line = handle.readline()
                if not line:
                    break
                if line.startswith("#"):
                    continue
                columns = line.split("\t")
                if len(columns) >= 3 and columns[2] in UTR_TYPES:
                    has_utr = True
                    break
    except Exception:
        pass

    if has_utr and not is_gz:
        ctx.line("Annotation file already contains UTR, no need to add")
        return path

    utr_path = os.path.join(output_dir, "%s_with_utrs.gff3" % base)
    if plain_fasta_is_current(utr_path, path):
        ctx.line("Using existing UTR file: %s" % utr_path)
        return utr_path
    if os.path.exists(utr_path):
        ctx.line("UTR file is stale, re-generating: %s" % utr_path)
    ctx.line("Adding UTR (file: %s) ..." % path)
    with open(utr_path, "w", encoding="utf-8") as handle:
        result = subprocess.run(
            [sys.executable, UTR_SCRIPT, path],
            stdout=handle,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
    if result.returncode != 0:
        ctx.line("Failed to add UTR: %s" % result.stderr)
        if os.path.exists(utr_path):
            os.remove(utr_path)
        raise ValueError("GTF preprocessing failed")
    ctx.line("UTR added: %s" % utr_path)
    return utr_path


def extract_sequences(genome: str, annotation: str, identifier: str,
                      region_type: str, region_num, id_type: str):
    """Return ``[(header, formatted_sequence), ...]`` for one identifier."""
    genome = _clean(genome)
    if not genome or not os.path.exists(genome):
        raise ValueError("Genome FASTA file not specified or not found")
    annotation = _clean(annotation)
    if not annotation or not os.path.exists(annotation):
        raise ValueError("GTF file not specified or not found")
    identifier = _clean(identifier)
    if not identifier:
        raise ValueError("Please specify Search scope")
    ids = (
        [item.strip() for item in identifier.split(",") if item.strip()]
        if "," in identifier else [identifier]
    )
    results = []
    for gene_id in ids:
        header, sequence = get_region_sequence(
            genome, annotation, gene_id, region_type, region_num,
            id_type=id_type,
        )
        formatted = "\n".join(
            sequence[index:index + 60]
            for index in range(0, len(sequence), 60)
        )
        results.append((header, formatted))
    return results


def _write_fasta(output_dir: str, filename: str, content: str, ctx) -> str:
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, filename)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)
    ctx.line("FASTA written to: %s" % path)
    return path


def publish_file(path: str, ctx) -> str:
    """Copy an extraction result into the job's ``out/`` for download."""
    if not path or not os.path.isfile(path):
        return ""
    name = os.path.basename(path)
    target = os.path.join(ctx.out_dir, name)
    try:
        os.makedirs(ctx.out_dir, exist_ok=True)
        with open(path, "rb") as source, open(target, "wb") as destination:
            destination.write(source.read())
    except OSError:
        return ""
    return "out/" + name

def extract_target_fasta(payload: Dict[str, Any], genome: str,
                         annotation: str, output_dir: str, ctx) -> str:
    """Write the Search-scope FASTA; mirrors main.py's _extract_target_fasta."""
    target_id = _clean(payload.get("target_id"))
    if not target_id:
        raise ValueError("Please specify Search scope")
    region = _clean(payload.get("target_region")) or "Coding region"
    region_num = (
        _clean(payload.get("target_num"))
        if region in REGION_NUMBER_TYPES else None
    )
    id_type = _clean(payload.get("target_id_type")) or "gene_name"
    parts = extract_sequences(
        genome, annotation, target_id, region, region_num, id_type)
    if not parts:
        raise ValueError("No sequences extracted")
    if len(parts) == 1:
        base_name = parts[0][0].lstrip(">").replace(" ", "_").replace("/", "_")
        filename = "%s.fa" % base_name
    else:
        filename = "target_sequences.fa"
    content = "\n".join("%s\n%s" % (header, seq) for header, seq in parts)
    return _write_fasta(output_dir, filename, content, ctx)


def extract_mask_fasta(payload: Dict[str, Any], genome: str, annotation: str,
                       output_dir: str, ctx,
                       target_fasta: Optional[str] = None) -> Optional[str]:
    """Write the Mask FASTA; mirrors main.py's _extract_mask_fasta."""
    target_id = _clean(payload.get("target_id"))
    if payload.get("skip_mask"):
        ctx.line("Skip mask is enabled, no Mask gene FASTA will be generated")
        return None
    if payload.get("mask_same_as_target", True):
        ctx.line(
            "Mask gene is the same as Target, using Target sequence as Mask "
            "gene sequence")
        return target_fasta
    mask_id = _clean(payload.get("mask_id"))
    if not mask_id:
        ctx.line("No Mask gene identifier provided, no Mask FASTA generated")
        return None
    if mask_id == target_id and target_fasta:
        ctx.line("Reusing Target sequence file as Mask gene sequence")
        return target_fasta
    region = _clean(payload.get("mask_region")) or "Coding region"
    region_num = (
        _clean(payload.get("mask_num"))
        if region in REGION_NUMBER_TYPES else None
    )
    id_type = _clean(payload.get("mask_id_type")) or "gene_name"
    parts = extract_sequences(
        genome, annotation, mask_id, region, region_num, id_type)
    if not parts:
        raise ValueError("No Mask gene sequences extracted")
    if len(parts) == 1:
        base_name = parts[0][0].lstrip(">").replace(" ", "_").replace("/", "_")
        filename = "%s.fa" % base_name
    else:
        filename = "mask_sequences.fa"
    content = "\n".join("%s\n%s" % (header, seq) for header, seq in parts)
    return _write_fasta(output_dir, filename, content, ctx)


def _prepare_inputs(payload: Dict[str, Any], output_dir: str, ctx):
    genome = prepare_genome(payload.get("genome"), output_dir, ctx)
    annotation = prepare_annotation(payload.get("annotation"), output_dir, ctx)
    return genome, annotation


def download_body(payload: Dict[str, Any]):
    """Download a genome + annotation pair via shared/data/download_data.py."""

    def run(ctx) -> int:
        species = _clean(payload.get("species"))
        if not species:
            raise ValueError("Organism is required")
        output_dir = _clean(payload.get("output_dir"))
        if not output_dir:
            raise ValueError("Download output directory is required")
        os.makedirs(output_dir, exist_ok=True)
        returncode = _run_command(
            [sys.executable, DOWNLOAD_SCRIPT, "--species", species,
             "--output", output_dir],
            ctx, cwd=ROOT)
        if returncode != 0:
            return returncode
        info = _read_json(os.path.join(output_dir, "download_info.json"))
        genome = _clean(info.get("genome_fasta"))
        annotation = _clean(info.get("gtf"))
        if not genome or not annotation:
            ctx.line(
                "Download info file not found; specify Genome and "
                "Annotation paths manually.")
        ctx.set_result({
            "download_output": output_dir,
            "genome": genome,
            "annotation": annotation,
        })
        ctx.set_outputs({
            "genome_fasta": genome,
            "annotation": annotation,
            "output_dir": output_dir,
        })
        return 0

    return run


def prepare_body(payload: Dict[str, Any]):
    """Genome + annotation preparation, extractions and optional BLAST DB."""

    def run(ctx) -> int:
        output_dir = require_output_dir(payload)
        os.makedirs(output_dir, exist_ok=True)
        genome, annotation = _prepare_inputs(payload, output_dir, ctx)
        if not _clean(payload.get("target_id")):
            raise ValueError("Please specify Search scope")
        target_fasta = extract_target_fasta(
            payload, genome, annotation, output_dir, ctx)
        mask_fasta = extract_mask_fasta(
            payload, genome, annotation, output_dir, ctx, target_fasta)
        blastdb = _clean(payload.get("blastdb"))
        if not blastdb and payload.get("build_blastdb"):
            blastdb = ensure_blastdb(genome, output_dir=output_dir,
                                     log=ctx.line)
            ctx.line("Genome database ready: %s" % blastdb)
        ctx.set_result({
            "output_dir": output_dir,
            "genome": genome,
            "annotation": annotation,
            "target_fasta": target_fasta or "",
            "mask_fasta": mask_fasta or "",
            "blastdb": blastdb,
            "target_download": publish_file(target_fasta, ctx),
            "mask_download": publish_file(mask_fasta, ctx),
        })
        ctx.set_outputs({
            "genome_fasta": genome,
            "annotation": annotation,
            "target_fasta": target_fasta or "",
            "mask_fasta": mask_fasta or "",
            "output_dir": output_dir,
            "blastdb": blastdb,
        })
        return 0

    return run


def extract_target_body(payload: Dict[str, Any]):
    def run(ctx) -> int:
        output_dir = require_output_dir(payload)
        os.makedirs(output_dir, exist_ok=True)
        genome, annotation = _prepare_inputs(payload, output_dir, ctx)
        target_fasta = extract_target_fasta(
            payload, genome, annotation, output_dir, ctx)
        ctx.set_result({
            "output_dir": output_dir,
            "target_fasta": target_fasta,
            "target_download": publish_file(target_fasta, ctx),
        })
        ctx.set_outputs({
            "target_fasta": target_fasta,
            "output_dir": output_dir,
        })
        return 0

    return run


def extract_mask_body(payload: Dict[str, Any]):
    def run(ctx) -> int:
        output_dir = require_output_dir(payload)
        os.makedirs(output_dir, exist_ok=True)
        genome, annotation = _prepare_inputs(payload, output_dir, ctx)
        target_fasta = None
        if payload.get("mask_same_as_target", True) and _clean(
                payload.get("target_id")):
            target_fasta = extract_target_fasta(
                payload, genome, annotation, output_dir, ctx)
        mask_fasta = extract_mask_fasta(
            payload, genome, annotation, output_dir, ctx, target_fasta)
        if not mask_fasta:
            ctx.line("No Mask gene FASTA generated")
        ctx.set_result({
            "output_dir": output_dir,
            "target_fasta": target_fasta or "",
            "mask_fasta": mask_fasta or "",
            "mask_download": publish_file(mask_fasta, ctx),
        })
        ctx.set_outputs({
            "mask_fasta": mask_fasta or "",
            "output_dir": output_dir,
        })
        return 0

    return run


def build_blastdb_body(payload: Dict[str, Any]):
    def run(ctx) -> int:
        output_dir = require_output_dir(payload)
        os.makedirs(output_dir, exist_ok=True)
        genome = prepare_genome(payload.get("genome"), output_dir, ctx)
        prefix = ensure_blastdb(genome, output_dir=output_dir, log=ctx.line)
        ctx.line("Genome database built: %s" % prefix)
        ctx.set_result({"blastdb": prefix, "output_dir": output_dir})
        ctx.set_outputs({"blastdb": prefix, "output_dir": output_dir})
        return 0

    return run


def build_index_body(payload: Dict[str, Any]):
    def run(ctx) -> int:
        genome = require_file(payload.get("genome"), "Genome FASTA")
        prefix = _clean(payload.get("prefix"))
        output_dir = _clean(payload.get("output_dir"))
        if not prefix and not output_dir:
            raise ValueError("Index output directory or prefix is required")
        cmd = [sys.executable, INDEX_SCRIPT, genome]
        if prefix:
            cmd += ["--prefix", prefix]
        else:
            os.makedirs(output_dir, exist_ok=True)
            cmd += ["--output-dir", output_dir]
        if payload.get("k"):
            cmd += ["--k", str(int(payload["k"]))]
        if payload.get("max_memory_mb"):
            cmd += ["--max-memory-mb", str(int(payload["max_memory_mb"]))]
        returncode = _run_command(cmd, ctx, cwd=ROOT)
        if returncode == 0:
            index_path = prefix or os.path.join(
                output_dir, os.path.splitext(os.path.basename(genome))[0])
            ctx.set_result({"index_prefix": index_path})
            ctx.set_outputs({
                "index_path": index_path,
                "output_dir": output_dir,
            })
        return returncode

    return run

def _submit(manager, title, body, payload, params=None):
    job_id = manager.create_job(
        "dataprep", title, body, params or dict(payload, title=title))
    return {"job_id": job_id, "title": title}


def submit_download(payload: Dict[str, Any], manager) -> Dict[str, Any]:
    if not _clean(payload.get("species")):
        raise ValueError("Organism is required")
    if not _clean(payload.get("output_dir")):
        raise ValueError("Download output directory is required")
    return _submit(manager, "Download genome and annotation",
                   download_body(payload), payload)


def submit_prepare(payload: Dict[str, Any], manager) -> Dict[str, Any]:
    require_output_dir(payload)
    require_file(payload.get("genome"), "Genome FASTA")
    require_file(payload.get("annotation"), "Annotation file")
    if not _clean(payload.get("target_id")):
        raise ValueError("Please specify Search scope")
    return _submit(manager, "Prepare data", prepare_body(payload), payload)


def submit_extract_target(payload: Dict[str, Any], manager) -> Dict[str, Any]:
    require_output_dir(payload)
    require_file(payload.get("genome"), "Genome FASTA")
    require_file(payload.get("annotation"), "Annotation file")
    if not _clean(payload.get("target_id")):
        raise ValueError("Please specify Search scope")
    return _submit(manager, "Extract Target FASTA",
                   extract_target_body(payload), payload)


def submit_extract_mask(payload: Dict[str, Any], manager) -> Dict[str, Any]:
    require_output_dir(payload)
    require_file(payload.get("genome"), "Genome FASTA")
    require_file(payload.get("annotation"), "Annotation file")
    if payload.get("mask_same_as_target", True):
        if not _clean(payload.get("target_id")):
            raise ValueError("Please specify Search scope first")
    elif not _clean(payload.get("mask_id")):
        raise ValueError("Mask gene identifier is required")
    return _submit(manager, "Extract Mask FASTA",
                   extract_mask_body(payload), payload)


def submit_build_blastdb(payload: Dict[str, Any], manager) -> Dict[str, Any]:
    require_output_dir(payload)
    require_file(payload.get("genome"), "Genome FASTA")
    return _submit(manager, "Build BLAST DB", build_blastdb_body(payload),
                   payload)


def submit_build_index(payload: Dict[str, Any], manager) -> Dict[str, Any]:
    require_file(payload.get("genome"), "Genome FASTA")
    if not _clean(payload.get("prefix")) and not _clean(
            payload.get("output_dir")):
        raise ValueError("Index output directory or prefix is required")
    return _submit(manager, "Build genome index", build_index_body(payload),
                   payload)