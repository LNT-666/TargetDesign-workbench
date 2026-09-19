#!/usr/bin/env bash
# Bootstrap the crispAI runtime environment (Linux server, e.g. ms01).
#
# Usage:  bash tools/build_crispai_env.sh
#
# Creates the server .venv, installs requirements-linux.txt, installs R + NuPoP
# (via Bioconductor, into a user-writable R library), and finishes with the
# crispAI preflight so you can see exactly what is still missing.
#
# Idempotent: safe to re-run whenever requirements*.txt change.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$HERE")"
cd "$ROOT" || exit 1

VENV="${ROOT}/.venv"
PY="${VENV}/bin/python"
REQ="${ROOT}/requirements-linux.txt"

echo "==> 1/4  Python venv + requirements"
if [ ! -x "${PY}" ]; then
  python3 -m venv "${VENV}" || { echo "error: failed to create ${VENV}"; exit 1; }
fi
"${PY}" -m pip install --upgrade pip >/dev/null 2>&1 || true
"${PY}" -m pip install -r "${REQ}" || { echo "error: pip install -r requirements-linux.txt"; exit 1; }

echo "==> 2/4  R + NuPoP (user-writable library)"
RSCRIPT="$(command -v Rscript || true)"
if [ -z "${RSCRIPT}" ]; then
  echo "WARNING: Rscript not found; install R (e.g. 'conda install -c r r-base') and re-run." >&2
else
  # NuPoP is not published on CRAN for R >= 4.3, so install it via Bioconductor.
  RLIB="$("${RSCRIPT}" -e 'cat(file.path(Sys.getenv("HOME"), "R", "library"))')"
  mkdir -p "${RLIB}"
  RENV="${HOME}/.Renviron"
  touch "${RENV}"
  if ! grep -q "^R_LIBS_USER=" "${RENV}"; then
    printf 'R_LIBS_USER=%s\n' "${RLIB}" >> "${RENV}"
  fi
  export R_LIBS_USER="${RLIB}"
  echo "   R user library: ${RLIB}"
  "${RSCRIPT}" -e \
    'if(!requireNamespace("BiocManager", quietly=TRUE)) install.packages("BiocManager", lib=Sys.getenv("R_LIBS_USER"), repos="https://cloud.r-project.org")' \
    || { echo "error: BiocManager install failed"; exit 1; }
  "${RSCRIPT}" -e \
    'BiocManager::install("NuPoP", lib=Sys.getenv("R_LIBS_USER"), ask=FALSE, update=FALSE)' \
    || { echo "error: NuPoP install failed (see messages above)"; exit 1; }
fi

echo "==> 3/4  Cas-OFFinder (install via micromamba if missing) + UCSC chroms"
CAS_DIR="${ROOT}/external_tools/crispAI-main/crispAI_score/casoffinder"
export HOME="${HOME:?}"
MICRO_DIR="${HOME}/.cache/micromamba"
CAS_ENV="${HOME}/.cache/casoffinder-env"
if [ ! -x "${CAS_DIR}/cas-offinder" ] && ! command -v cas-offinder >/dev/null 2>&1; then
  echo "   cas-offinder not found; installing via micromamba + bioconda..."
  if [ ! -x "${MICRO_DIR}/bin/micromamba" ]; then
    mkdir -p "${MICRO_DIR}/bin"
    curl -fL -o /tmp/micromamba.tar.bz2 \
      https://github.com/mamba-org/micromamba-releases/releases/latest/download/micromamba-linux-64 \
      || { echo "error: micromamba download failed"; exit 1; }
    cp /tmp/micromamba.tar.bz2 "${MICRO_DIR}/bin/micromamba"
    chmod +x "${MICRO_DIR}/bin/micromamba"
  fi
  export MAMBA_ROOT_PREFIX="${HOME}/.cache/mamba"
  if [ ! -x "${CAS_ENV}/bin/cas-offinder" ]; then
    "${MICRO_DIR}/bin/micromamba" create -y -p "${CAS_ENV}" \
      -c conda-forge -c bioconda cas-offinder -q \
      || { echo "error: cas-offinder env creation failed"; exit 1; }
  fi
  mkdir -p "${CAS_DIR}"
  ln -sf "${CAS_ENV}/bin/cas-offinder" "${CAS_DIR}/cas-offinder"
fi
if [ -x "${CAS_DIR}/cas-offinder" ] || command -v cas-offinder >/dev/null 2>&1; then
  echo "   cas-offinder: OK (${CAS_DIR}/cas-offinder)"
else
  echo "   cas-offinder: MISSING -> put the binary at ${CAS_DIR}/cas-offinder, or export CRISPAI_CASOFFINDER_DIR to its directory" >&2
fi
if [ -d "${CAS_DIR}/ucsc_chroms" ]; then
  echo "   ucsc_chroms:  OK"
else
  echo "   ucsc_chroms:  MISSING -> put UCSC per-chrom FASTA under ${CAS_DIR}/ucsc_chroms/ (or let genomepy download GRCh38 on first run)" >&2
fi

echo "==> 4/4  crispAI preflight"
cat > /tmp/crispai_preflight.py <<'PY'
import sys
sys.path.insert(0, sys.argv[1])
from scoring.crispai_runtime import preflight
errors, warnings = preflight()
print("ERRORS(%d):" % len(errors))
for e in errors:
    print("  -", e)
print("WARNINGS(%d):" % len(warnings))
for w in warnings:
    print("  -", w)
print("READY" if not errors else "NOT_READY")
PY
"${PY}" /tmp/crispai_preflight.py "${ROOT}/shared"

echo "done. If a step above flagged something missing, fix it and re-run this script."
