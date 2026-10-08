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
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CRISPAI_DIR = (
    PROJECT_ROOT / "external_tools" / "crispAI-main" / "crispAI_score"
)
MODEL_PATH = PROJECT_ROOT / "models" / "crispai.pt"

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


def _casoffinder_dir() -> Path:
    override = os.environ.get("CRISPAI_CASOFFINDER_DIR")
    if override:
        return Path(override)
    return CRISPAI_DIR / "casoffinder"


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
    except (ImportError, AttributeError):
        return False


def _nupop_available() -> bool:
    rscript = shutil.which("Rscript")
    if not rscript:
        return False
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
        return "TRUE" in (proc.stdout or "")
    except (OSError, subprocess.TimeoutExpired):
        return False


def preflight() -> Tuple[List[str], List[str]]:
    """Return (errors, warnings) for the external crispAI environment."""
    errors: List[str] = []
    warnings: List[str] = []

    if not os.path.isfile(str(MODEL_PATH)):
        errors.append("crispAI checkpoint missing: %s" % MODEL_PATH)
    if not os.path.isdir(str(CRISPAI_DIR)):
        errors.append("vendored crispAI code missing: %s" % CRISPAI_DIR)

    for module in PYTHON_DEPENDENCIES:
        if not _module_available(module):
            errors.append(
                "Python dependency %r missing (pip install %s)"
                % (module, module)
            )

    if shutil.which("Rscript") is None:
        errors.append("Rscript not found on PATH (required by NuPoP)")
    elif not _nupop_available():
        errors.append(
            "R package NuPoP not available "
            "(run: Rscript -e 'install.packages(\"NuPoP\")')"
        )

    cas_dir = _casoffinder_dir()
    if not _casoffinder_binary(cas_dir):
        errors.append(
            "cas-offinder binary not found under %s "
            "(set CRISPAI_CASOFFINDER_DIR to the directory containing it)"
            % cas_dir
        )

    ucsc = cas_dir / "ucsc_chroms"
    if not os.path.isdir(str(ucsc)):
        warnings.append(
            "UCSC chroms directory %s not found; "
            "genomepy may download GRCh38 on first run" % ucsc
        )
    return errors, warnings


def model_status() -> str:
    """Return a coarse status for the Models tab and preflight code."""
    if not os.path.isfile(str(MODEL_PATH)):
        return "not_downloaded"
    errors, _ = preflight()
    if errors:
        return "dependency_missing"
    return "ready"


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


def run_aggregate(
    input_path: str,
    output_path: str,
    log_path: Optional[str] = None,
    n_samples: int = 200,
    gpu: int = -1,
) -> int:
    """Invoke the vendored crispAI aggregate pipeline as a subprocess."""
    env = dict(os.environ)
    env["CRISPAI_CHECKPOINT"] = str(MODEL_PATH)
    env["CRISPAI_CASOFFINDER_DIR"] = str(_casoffinder_dir())
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
                cwd=str(CRISPAI_DIR),
                env=env,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
    else:
        proc = subprocess.run(
            command,
            cwd=str(CRISPAI_DIR),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if log_path is None and proc.stdout:
            sys.stdout.write(proc.stdout)
    return proc.returncode


def parse_aggregate_output(output_path: str) -> Dict[str, float]:
    """Map each sgRNA to the crispAI aggregate_score_mean value."""
    mapping: Dict[str, float] = {}
    if not os.path.isfile(output_path):
        return mapping
    with open(output_path, "r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle, delimiter="\t")
        header = next(reader, None)
        if header is None:
            return mapping
        value_col = 1
        for index, name in enumerate(header):
            if "aggregate_score_mean" in name:
                value_col = index
                break
        for row in reader:
            if len(row) <= value_col:
                continue
            sgrna = row[0].strip()
            try:
                mapping[sgrna] = float(row[value_col])
            except ValueError:
                continue
    return mapping


def specificity_from_aggregate(aggregate: float) -> float:
    """Convert crispAI log activity to a 0-1 specificity value."""
    return 1.0 / (1.0 + max(0.0, aggregate))


def run_crispai_aggregate(
    sgrnas: Iterable[str],
    output_dir: str,
    n_samples: int = 200,
    gpu: int = -1,
) -> Optional[Dict[str, float]]:
    """Run the crispAI aggregate pipeline for a set of sgRNAs.

    ``sgrnas`` is the deduplicated list of 23-nt SpCas9 strings.  On success it
    returns ``{sgrna: aggregate_score_mean}``; on any preflight/run failure it
    prints a warning and returns ``None`` so callers can fall back to CFD.
    """
    unique_sgrnas = sorted({s for s in sgrnas if s})
    if not unique_sgrnas:
        return None
    errors, warnings = preflight()
    if errors:
        for error in errors:
            print("Warning: %s" % error)
        print("crispAI environment not ready; off-target fell back to CFD scoring")
        return None
    for warning in warnings:
        print("Warning: %s" % warning)

    temp_dir = tempfile.mkdtemp(prefix="crispai_", dir=output_dir)
    input_path = os.path.join(temp_dir, "sgrnas.txt")
    write_aggregate_input(
        [{"sgrna": sgrna} for sgrna in unique_sgrnas], input_path)
    aggregate_path = os.path.join(output_dir, "crispai.aggregate.tsv")
    log_path = os.path.join(output_dir, "crispai.log.tsv")
    try:
        returncode = run_aggregate(
            input_path, aggregate_path, log_path=log_path,
            n_samples=n_samples, gpu=gpu,
        )
    except Exception as exc:
        print("crispAI runtime error: %s" % exc)
        returncode = -1
    finally:
        try:
            os.rmdir(temp_dir)
        except OSError:
            pass
    if returncode != 0:
        print("crispAI call failed (exit %s); fell back to CFD; log: %s"
              % (returncode, log_path))
        return None
    mapping = parse_aggregate_output(aggregate_path)
    if not mapping:
        print("crispAI returned no valid aggregate score; fell back to CFD")
        return None
    return mapping


def backfill_candidates(
    candidates_path: str,
    aggregate_output_path: str,
    out_path: Optional[str] = None,
) -> Tuple[int, int]:
    """Add crispAI columns to the scored candidate TSV in place."""
    mapping = parse_aggregate_output(aggregate_output_path)
    if not mapping:
        return 0, 0

    out_path = out_path or candidates_path
    written = 0
    matched = 0
    with open(candidates_path, "r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        fieldnames = list(reader.fieldnames or [])
        for column in ("crispai_aggregate_score", "crispai_off_target"):
            if column not in fieldnames:
                fieldnames.append(column)
        rows = list(reader)

    with open(out_path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=fieldnames, delimiter="\t", extrasaction="ignore"
        )
        writer.writeheader()
        for row in rows:
            sgrna = make_sgrna(
                (row.get("guide_seq") or "").strip(),
                row.get("pam_seq", "NGG"),
            )
            aggregate = mapping.get(sgrna or "")
            if aggregate is not None:
                row["crispai_aggregate_score"] = "%.6f" % aggregate
                row["crispai_off_target"] = "%.6f" % specificity_from_aggregate(
                    aggregate
                )
                matched += 1
            writer.writerow(row)
            written += 1
    return matched, written
