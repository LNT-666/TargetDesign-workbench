#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""External crispAI adapter for the library pipeline.

crispAI's aggregate mode is not an in-process scorer: it needs a prepared
external environment (R + NuPoP, Cas-OFFinder, GRCh38/UCSC chroms, pybdm and
genomepy) to annotate every off-target site.  This module keeps the adapter in
one place:

1. collect the unique sgRNA 23-mers from a scored candidate TSV;
2. preflight the crispAI installation;
3. call the vendored upstream ``crispAI.py --mode agg-score``;
4. convert ``aggregate_score_mean`` to a 0-1 ``crispai_off_target`` value and
   backfill the candidate TSV.

The conversion ``specificity = 1 / (1 + aggregate)`` keeps the same direction
as the other off-target columns (higher is more specific) while preserving the
monotone ranking implied by crispAI's aggregate activity.
"""

from __future__ import annotations

import csv
import gzip
import math
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CRISPAI_DIR = (
    PROJECT_ROOT / "external_tools" / "crispAI-main" / "crispAI_score"
)
MODEL_PATH = PROJECT_ROOT / "models" / "crispai.pt"
DEFAULT_GENOME = "GRCh38"

VENDORED_ENTRY_FILES = (
    "crispAI.py",
    "annotate_pi.py",
    "model.py",
    "loss_functions.py",
    "_negative_binomial.py",
    "utils.py",
    "encoding.py",
    "nupop.R",
)

PYTHON_DEPENDENCIES = (
    "torch",
    "pandas",
    "numpy",
    "pybdm",
    "genomepy",
    "jax",
    "numpyro",
    "tqdm",
    "seaborn",
)


def vendor_dir() -> Path:
    """Return the vendored crispAI source directory used by this adapter."""
    return Path(os.environ.get("CRISPAI_VENDOR_DIR") or CRISPAI_DIR)


def checkpoint_path() -> Path:
    """Return the checkpoint path, honouring the adapter override."""
    return Path(os.environ.get("CRISPAI_CHECKPOINT") or MODEL_PATH)


def _checkpoint_present() -> bool:
    path = checkpoint_path()
    try:
        return path.is_file() and path.stat().st_size > 0
    except OSError:
        return False


def genome_name() -> str:
    """Return the genomepy genome name or FASTA path used by upstream."""
    return os.environ.get("CRISPAI_GENOME") or DEFAULT_GENOME


def _casoffinder_dir() -> Path:
    override = os.environ.get("CRISPAI_CASOFFINDER_DIR")
    return Path(override) if override else vendor_dir() / "casoffinder"


def _casoffinder_binary(cas_dir: Optional[Path] = None) -> Optional[str]:
    cas_dir = cas_dir or _casoffinder_dir()
    candidates = (
        str(cas_dir / "cas-offinder"),
        str(cas_dir / "cas-offinder.exe"),
    )
    for candidate in candidates:
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return shutil.which("cas-offinder")


def _module_available(name: str) -> bool:
    try:
        import importlib.util

        return importlib.util.find_spec(name) is not None
    except (ImportError, AttributeError, ValueError):
        return False


def _compact_output(value: Any, limit: int = 240) -> str:
    text = " ".join(str(value or "").split())
    return text[:limit] + ("..." if len(text) > limit else "")


def nupop_probe() -> Tuple[bool, str]:
    """Probe NuPoP and return ``(available, actionable_error)``."""
    rscript = shutil.which("Rscript")
    if not rscript:
        return False, "Rscript not found on PATH (required by NuPoP)"
    try:
        proc = subprocess.run(
            [
                rscript,
                "-e",
                'cat(as.character(requireNamespace("NuPoP", quietly=TRUE)))',
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=30,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False, "NuPoP probe timed out after 30 seconds"
    except OSError as exc:
        return False, "NuPoP probe could not start Rscript: %s" % exc
    output = (proc.stdout or "").strip()
    if proc.returncode != 0:
        detail = _compact_output(output)
        return False, "NuPoP probe failed with exit code %s%s" % (
            proc.returncode, (": " + detail) if detail else "")
    if output != "TRUE":
        detail = _compact_output(output)
        return False, "NuPoP probe did not return TRUE%s" % (
            (": " + detail) if detail else "")
    return True, ""


def _nupop_available() -> bool:
    available, _ = nupop_probe()
    return available


def _is_fasta(path: Path) -> bool:
    lowered = path.name.lower()
    return lowered.endswith(
        (".fa", ".fasta", ".fna", ".fa.gz", ".fasta.gz", ".fna.gz"))


def _fasta_is_parseable(path: Path) -> bool:
    """Check a FASTA header and first sequence line without loading the genome."""
    try:
        opener = gzip.open if path.name.lower().endswith(".gz") else open
        with opener(path, "rt", encoding="utf-8", errors="replace") as handle:
            saw_header = False
            for line in handle:
                text = line.strip()
                if not text:
                    continue
                if not saw_header:
                    if not text.startswith(">"):
                        return False
                    saw_header = True
                    continue
                return text.startswith(">") or any(
                    base.isalpha() or base in "*.-" for base in text)
    except (OSError, UnicodeError):
        return False
    return False


def _genome_search_dirs() -> List[Path]:
    configured = os.environ.get("CRISPAI_GENOME_DIR")
    if configured:
        return [Path(configured)]
    candidates = [
        Path.home() / ".local" / "share" / "genomepy",
        Path.home() / ".local" / "share" / "genomepy" / "genomes",
    ]
    try:
        import genomepy  # type: ignore

        config = getattr(genomepy, "config", None)
        for attr in ("genome_dir", "genomes_dir"):
            value = getattr(config, attr, None)
            if callable(value):
                value = value()
            if value:
                candidates.insert(0, Path(value))
    except (ImportError, AttributeError, TypeError, ValueError):
        pass
    unique: List[Path] = []
    for path in candidates:
        if path not in unique:
            unique.append(path)
    return unique


def genome_resource_path() -> Optional[Path]:
    """Locate a parseable genomepy FASTA without triggering a download."""
    value = genome_name()
    direct = Path(value).expanduser()
    if direct.is_file() and _fasta_is_parseable(direct):
        return direct
    if direct.is_dir():
        try:
            children = sorted(direct.iterdir())
        except OSError:
            children = []
        for child in children:
            if (child.is_file() and _is_fasta(child)
                    and _fasta_is_parseable(child)):
                return child
        return None

    candidates: List[Path] = []
    for root in _genome_search_dirs():
        candidates.extend((
            root / value,
            root / ("%s.fa" % value),
            root / ("%s.fasta" % value),
            root / ("%s.fna" % value),
            root / value / ("%s.fa" % value),
            root / value / ("%s.fasta" % value),
            root / value / ("%s.fna" % value),
        ))
    seen = set()
    for candidate in candidates:
        key = str(candidate).lower()
        if key in seen:
            continue
        seen.add(key)
        if candidate.is_file() and _fasta_is_parseable(candidate):
            return candidate
    return None


def _ucsc_fasta_files(cas_dir: Path) -> List[Path]:
    ucsc = cas_dir / "ucsc_chroms"
    if not ucsc.is_dir():
        return []
    try:
        files = [
            child for child in ucsc.iterdir()
            if child.is_file() and child.suffix.lower() in (".fa", ".fasta", ".fna")
        ]
        return [child for child in files if _fasta_is_parseable(child)]
    except OSError:
        return []


def preflight() -> Tuple[List[str], List[str]]:
    """Return (errors, warnings) for the external crispAI environment."""
    errors: List[str] = []
    warnings: List[str] = []
    vendor = vendor_dir()
    checkpoint = checkpoint_path()

    if not _checkpoint_present():
        errors.append("crispAI checkpoint missing: %s" % checkpoint)
    if not vendor.is_dir():
        errors.append("vendored crispAI code missing: %s" % vendor)
    else:
        for name in VENDORED_ENTRY_FILES:
            entry = vendor / name
            if not entry.is_file():
                errors.append("vendored crispAI entry missing: %s" % entry)

    for module in PYTHON_DEPENDENCIES:
        if not _module_available(module):
            errors.append(
                "Python dependency %r missing (pip install %s)"
                % (module, module)
            )

    nupop_ready, nupop_error = nupop_probe()
    if not nupop_ready:
        errors.append(
            "%s (install NuPoP, e.g. via Bioconductor; see docs/CRISPAI.md)"
            % nupop_error
        )

    cas_dir = _casoffinder_dir()
    if not _casoffinder_binary(cas_dir):
        errors.append(
            "cas-offinder binary not found under %s "
            "(set CRISPAI_CASOFFINDER_DIR to the directory containing it)"
            % cas_dir
        )

    ucsc = cas_dir / "ucsc_chroms"
    if not _ucsc_fasta_files(cas_dir):
        errors.append(
            "UCSC chromosome FASTA files missing under %s "
            "(set CRISPAI_CASOFFINDER_DIR to the directory containing "
            "cas-offinder and ucsc_chroms)" % ucsc
        )

    genome = genome_resource_path()
    if genome is None:
        errors.append(
            "genomepy genome resource %r is not installed/parseable "
            "(set CRISPAI_GENOME to a FASTA path or installed genome name, "
            "and optionally CRISPAI_GENOME_DIR)" % genome_name()
        )
    return errors, warnings


def model_status() -> str:
    """Return the status implied by the complete crispAI runtime preflight."""
    if not _checkpoint_present():
        return "not_downloaded"
    errors, _ = preflight()
    return "dependency_missing" if errors else "ready"


def model_status_details() -> Dict[str, Any]:
    """Return status plus actionable preflight evidence for UI/CLI consumers."""
    errors, warnings = preflight()
    if not _checkpoint_present():
        status = "not_downloaded"
    elif errors:
        status = "dependency_missing"
    else:
        status = "ready"
    genome = genome_resource_path()
    return {
        "status": status,
        "errors": errors,
        "warnings": warnings,
        "paths": {
            "checkpoint": str(checkpoint_path()),
            "vendor": str(vendor_dir()),
            "casoffinder": str(_casoffinder_dir()),
            "genome": genome_name(),
            "genome_resource": str(genome) if genome else "",
        },
    }


def make_sgrna(guide_seq: str, pam_seq: str = "NGG") -> Optional[str]:
    """Build the 23-nt sgRNA string expected by the crispAI aggregate mode."""
    guide = (guide_seq or "").upper().replace("U", "T")
    if len(guide) == 23 and guide.endswith("GG") and guide[-3] == "N":
        return guide
    if len(guide) == 20:
        # crispAI aggregate is a SpCas9/NGG scorer; the N keeps the Cas-OFFinder
        # search open to every NGG PAM base, matching the upstream sgRNA format.
        return guide + "NGG"
    return None


def collect_sgrnas(candidates_path: str) -> List[Dict[str, str]]:
    """Read one row per unique guide and return sgRNA records."""
    seen = set()
    records: List[Dict[str, str]] = []
    with open(candidates_path, "r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row in reader:
            guide_seq = (row.get("guide_seq") or "").strip()
            sgrna = make_sgrna(guide_seq, row.get("pam_seq", "NGG"))
            if not sgrna or sgrna in seen:
                continue
            seen.add(sgrna)
            records.append(
                {
                    "qid": (row.get("qid") or "").strip(),
                    "guide_seq": guide_seq,
                    "sgrna": sgrna,
                }
            )
    return records


def write_aggregate_input(sgrnas: Iterable[Dict[str, str]], path: str) -> int:
    """Write the headerless sgRNA list accepted by crispAI agg-score."""
    count = 0
    with open(path, "w", encoding="utf-8", newline="") as handle:
        for record in sgrnas:
            handle.write(record["sgrna"] + "\n")
            count += 1
    return count


@dataclass
class CrispAIRunResult:
    """Structured result returned by the external aggregate adapter."""

    scores: Dict[str, float]
    requested_model: str
    effective_model: str
    fallback_reason: str
    score_scope: str
    run_dir: str = ""
    aggregate_output_path: str = ""
    log_path: str = ""

    @property
    def succeeded(self) -> bool:
        return self.effective_model == self.requested_model and not self.fallback_reason

    def metadata(self) -> Dict[str, Any]:
        return {
            "requested_model": self.requested_model,
            "effective_model": self.effective_model,
            "fallback_reason": self.fallback_reason,
            "score_scope": self.score_scope,
            "success": self.succeeded,
            "score_count": len(self.scores),
            "run_dir": self.run_dir,
            "aggregate_output_path": self.aggregate_output_path,
            "log_path": self.log_path,
        }


def _link_or_copy(source: Path, target: Path, is_dir: bool = False) -> None:
    try:
        os.symlink(
            str(source.resolve()),
            str(target),
            target_is_directory=is_dir,
        )
        return
    except OSError as exc:
        if not is_dir:
            try:
                shutil.copy2(str(source), str(target))
                return
            except OSError:
                pass
        raise RuntimeError(
            "cannot stage %s at %s; symlink support is required for this "
            "resource: %s" % (source, target, exc)
        )


def _stage_vendor(vendor: Path, run_dir: Path) -> Path:
    staged = run_dir / "vendor"
    staged.mkdir(parents=True, exist_ok=False)
    for name in VENDORED_ENTRY_FILES:
        shutil.copy2(str(vendor / name), str(staged / name))

    annotate = staged / "annotate_pi.py"
    text = annotate.read_text(encoding="utf-8")
    marker = "genomepy.Genome('GRCh38')"
    replacement = (
        "genomepy.Genome(os.environ.get('CRISPAI_GENOME', 'GRCh38'))"
    )
    if text.count(marker) != 1:
        raise RuntimeError(
            "vendored annotate_pi.py does not contain the expected GRCh38 "
            "genome call; refusing to run an unpinned copy")
    annotate.write_text(text.replace(marker, replacement), encoding="utf-8")

    checked_helper = '''import subprocess

def _crispai_checked_system(command):
    completed = subprocess.run(command, shell=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(
            "crispAI external command failed with exit code %s: %s"
            % (completed.returncode, command))
    return completed.returncode

'''
    for name in ("crispAI.py", "annotate_pi.py"):
        path = staged / name
        source = path.read_text(encoding="utf-8")
        calls = source.count("os.system(")
        if not calls:
            raise RuntimeError(
                "vendored %s has no expected external command calls" % name)
        source = source.replace("os.system(", "_crispai_checked_system(")
        path.write_text(checked_helper + source, encoding="utf-8")
    return staged


def _stage_casoffinder(source_dir: Path, run_dir: Path) -> Path:
    binary = _casoffinder_binary(source_dir)
    if not binary:
        raise RuntimeError("cas-offinder binary is unavailable")
    staged = run_dir / "casoffinder"
    staged.mkdir(parents=True, exist_ok=False)
    _link_or_copy(Path(binary), staged / "cas-offinder", is_dir=False)
    _link_or_copy(source_dir / "ucsc_chroms", staged / "ucsc_chroms", is_dir=True)
    return staged


def run_aggregate(
    input_path: str,
    output_path: str,
    log_path: Optional[str] = None,
    n_samples: int = 200,
    gpu: int = -1,
    cwd: Optional[str] = None,
    casoffinder_dir: Optional[Path] = None,
    timeout: Optional[float] = None,
) -> int:
    """Invoke a staged crispAI aggregate pipeline and return its exit code."""
    vendor = Path(cwd) if cwd else vendor_dir()
    cas_dir = Path(casoffinder_dir) if casoffinder_dir else _casoffinder_dir()
    env = dict(os.environ)
    env["CRISPAI_CHECKPOINT"] = str(checkpoint_path().resolve())
    env["CRISPAI_CASOFFINDER_DIR"] = str(cas_dir.resolve())
    env["CRISPAI_VENDOR_DIR"] = str(vendor.resolve())
    env["CRISPAI_GENOME"] = genome_name()
    command = [
        sys.executable,
        "crispAI.py",
        "--mode",
        "agg-score",
        "--input_file",
        os.path.abspath(input_path),
        "--N_samples",
        str(n_samples),
        "--gpu",
        str(gpu),
        "--O",
        os.path.abspath(output_path),
    ]
    if log_path:
        with open(log_path, "w", encoding="utf-8") as log_handle:
            proc = subprocess.run(
                command,
                cwd=str(vendor),
                env=env,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                timeout=timeout,
            )
    else:
        proc = subprocess.run(
            command,
            cwd=str(vendor),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=timeout,
        )
        if proc.stdout:
            sys.stdout.write(proc.stdout)
    return proc.returncode


def parse_aggregate_output(
    output_path: str,
    strict: bool = False,
) -> Dict[str, float]:
    """Map each sgRNA to ``aggregate_score_mean``.

    ``strict`` rejects missing columns, malformed/non-finite rows and duplicate
    sgRNAs instead of silently producing a partial mapping.
    """
    mapping: Dict[str, float] = {}
    if not os.path.isfile(output_path):
        return mapping
    with open(output_path, "r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle, delimiter="\t")
        header = next(reader, None)
        if header is None:
            if strict:
                raise ValueError("aggregate output is empty")
            return mapping
        value_col = None
        for index, name in enumerate(header):
            if "aggregate_score_mean" in name:
                value_col = index
                break
        if value_col is None:
            if strict:
                raise ValueError("aggregate output has no aggregate_score_mean column")
            return mapping
        for row_number, row in enumerate(reader, start=2):
            if len(row) <= value_col or not row[0].strip():
                if strict:
                    raise ValueError(
                        "aggregate output row %d is incomplete" % row_number)
                continue
            sgrna = row[0].strip()
            try:
                value = float(row[value_col])
            except ValueError:
                if strict:
                    raise ValueError(
                        "aggregate output row %d has a non-numeric score"
                        % row_number) from None
                continue
            if not math.isfinite(value):
                if strict:
                    raise ValueError(
                        "aggregate output row %d has a non-finite score"
                        % row_number)
                continue
            if strict and sgrna in mapping:
                raise ValueError(
                    "aggregate output contains duplicate sgRNA %s" % sgrna)
            mapping[sgrna] = value
    return mapping


def validate_aggregate_guides(
    expected_sgrnas: Iterable[str],
    mapping: Dict[str, float],
) -> None:
    """Require the aggregate result key set to equal the requested guide set."""
    expected = {sgrna for sgrna in expected_sgrnas if sgrna}
    actual = set(mapping)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing or extra:
        parts = []
        if missing:
            parts.append("missing %d (%s)" % (
                len(missing), ", ".join(missing[:5])))
        if extra:
            parts.append("extra %d (%s)" % (
                len(extra), ", ".join(extra[:5])))
        raise ValueError("crispAI guide set mismatch: " + "; ".join(parts))


def specificity_from_aggregate(aggregate: float) -> float:
    """Convert crispAI log activity to a 0-1 specificity value."""
    return 1.0 / (1.0 + max(0.0, aggregate))


def _failed_result(
    reason: str,
    fallback_model: str,
    run_dir: str = "",
    aggregate_path: str = "",
    log_path: str = "",
) -> CrispAIRunResult:
    return CrispAIRunResult(
        scores={},
        requested_model="crispai",
        effective_model=fallback_model or "none",
        fallback_reason=reason or "crispAI aggregate scoring failed",
        score_scope="aggregate",
        run_dir=run_dir,
        aggregate_output_path=aggregate_path,
        log_path=log_path,
    )


def run_crispai_aggregate(
    sgrnas: Iterable[str],
    output_dir: str,
    n_samples: int = 200,
    gpu: int = -1,
    fallback_model: str = "none",
    timeout: Optional[float] = None,
) -> CrispAIRunResult:
    """Run crispAI in an isolated directory and return a structured result."""
    unique_sgrnas = sorted({s for s in sgrnas if s})
    if not unique_sgrnas:
        return _failed_result("no usable sgRNA was supplied", fallback_model)

    checkpoint = checkpoint_path()
    if not _checkpoint_present():
        reason = "crispAI checkpoint missing: %s" % checkpoint
        print("Warning: %s" % reason)
        return _failed_result(reason, fallback_model)

    errors, warnings = preflight()
    if errors:
        reason = "crispAI preflight failed: " + "; ".join(errors)
        print("Warning: %s" % reason)
        return _failed_result(reason, fallback_model)
    for warning in warnings:
        print("Warning: %s" % warning)

    os.makedirs(output_dir, exist_ok=True)
    run_dir = Path(tempfile.mkdtemp(prefix="crispai-run-", dir=output_dir))
    input_path = run_dir / "sgrnas.txt"
    aggregate_path = run_dir / "crispAI.aggregate.tsv"
    log_path = run_dir / "crispAI.log.tsv"
    if aggregate_path.exists() or log_path.exists():
        return _failed_result(
            "refusing to reuse pre-existing aggregate output",
            fallback_model,
            str(run_dir),
            str(aggregate_path),
            str(log_path),
        )
    write_aggregate_input(
        [{"sgrna": sgrna} for sgrna in unique_sgrnas], str(input_path))
    try:
        staged_vendor = _stage_vendor(vendor_dir(), run_dir)
        staged_cas = _stage_casoffinder(_casoffinder_dir(), run_dir)
        returncode = run_aggregate(
            str(input_path),
            str(aggregate_path),
            log_path=str(log_path),
            n_samples=n_samples,
            gpu=gpu,
            cwd=str(staged_vendor),
            casoffinder_dir=staged_cas,
            timeout=timeout,
        )
    except Exception as exc:
        reason = "crispAI runtime error: %s" % exc
        print("Warning: %s" % reason)
        return _failed_result(
            reason, fallback_model, str(run_dir), str(aggregate_path),
            str(log_path))

    if returncode != 0:
        reason = "crispAI aggregate exited with code %s; log: %s" % (
            returncode, log_path)
        print("Warning: %s" % reason)
        return _failed_result(
            reason, fallback_model, str(run_dir), str(aggregate_path),
            str(log_path))
    if not aggregate_path.is_file():
        reason = "crispAI aggregate output is missing: %s" % aggregate_path
        print("Warning: %s" % reason)
        return _failed_result(
            reason, fallback_model, str(run_dir), str(aggregate_path),
            str(log_path))
    try:
        mapping = parse_aggregate_output(str(aggregate_path), strict=True)
        if not mapping:
            raise ValueError("crispAI returned no aggregate scores")
        validate_aggregate_guides(unique_sgrnas, mapping)
    except ValueError as exc:
        reason = "crispAI aggregate output rejected: %s" % exc
        print("Warning: %s" % reason)
        return _failed_result(
            reason, fallback_model, str(run_dir), str(aggregate_path),
            str(log_path))
    return CrispAIRunResult(
        scores=mapping,
        requested_model="crispai",
        effective_model="crispai",
        fallback_reason="",
        score_scope="aggregate",
        run_dir=str(run_dir),
        aggregate_output_path=str(aggregate_path),
        log_path=str(log_path),
    )


def run_crispai_scores(
    sgrnas: Iterable[str],
    output_dir: str,
    n_samples: int = 200,
    gpu: int = -1,
) -> Dict[str, float]:
    """Backward-compatible score-only wrapper."""
    return run_crispai_aggregate(
        sgrnas, output_dir, n_samples=n_samples, gpu=gpu).scores


def backfill_candidates(
    candidates_path: str,
    aggregate_output_path: str,
    out_path: Optional[str] = None,
) -> Tuple[int, int]:
    """Validate the complete guide set, then atomically add crispAI columns."""
    expected = {record["sgrna"] for record in collect_sgrnas(candidates_path)}
    mapping = parse_aggregate_output(aggregate_output_path, strict=True)
    if not mapping:
        raise ValueError("crispAI aggregate output contains no scores")
    validate_aggregate_guides(expected, mapping)

    out_path = out_path or candidates_path
    with open(candidates_path, "r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        fieldnames = list(reader.fieldnames or [])
        for column in ("crispai_aggregate_score", "crispai_off_target"):
            if column not in fieldnames:
                fieldnames.append(column)
        rows = list(reader)

    out_dir = os.path.dirname(os.path.abspath(out_path))
    fd, temp_path = tempfile.mkstemp(
        prefix=".crispai-backfill-", suffix=".tsv", dir=out_dir)
    os.close(fd)
    written = 0
    matched = 0
    try:
        with open(temp_path, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle, fieldnames=fieldnames, delimiter="\t",
                extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                sgrna = make_sgrna(
                    (row.get("guide_seq") or "").strip(),
                    row.get("pam_seq", "NGG"),
                )
                aggregate = mapping.get(sgrna or "")
                if aggregate is not None:
                    row["crispai_aggregate_score"] = "%.6f" % aggregate
                    row["crispai_off_target"] = "%.6f" % (
                        specificity_from_aggregate(aggregate))
                    matched += 1
                writer.writerow(row)
                written += 1
        os.replace(temp_path, out_path)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
    return matched, written
