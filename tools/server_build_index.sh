#!/usr/bin/env bash
# Build the full GRCh38 index on a Linux server, then optionally search guides.
#
# Usage:
#   bash tools/server_build_index.sh GENOME_FASTA OUTPUT_DIR [GUIDES_TSV] [K]
#
# The server needs Python 3.10+ and enough RAM for the requested genome.
# For full GRCh38, 64 GB+ RAM is recommended with the current implementation.

set -euo pipefail

if [ "$#" -lt 2 ]; then
  echo "usage: bash tools/server_build_index.sh GENOME_FASTA OUTPUT_DIR [GUIDES_TSV] [K]" >&2
  exit 2
fi

GENOME="$1"
OUT="$2"
GUIDES="${3:-}"
K="${4:-12}"

if [ ! -f "$GENOME" ]; then
  echo "error: genome FASTA not found: $GENOME" >&2
  exit 2
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
mkdir -p "$OUT/genome_index"

if [ ! -x ".venv_server/bin/python" ]; then
  echo "creating server virtualenv ..."
  python3 -m venv .venv_server
  .venv_server/bin/pip install --upgrade pip
  .venv_server/bin/pip install numpy biopython pyfaidx
fi

PY="$ROOT/.venv_server/bin/python"
echo "building index for $GENOME (k=$K) ..."
"$PY" tools/build_genome_index.py "$GENOME" \
  --output-dir "$OUT/genome_index" --k "$K"

PREFIX="$OUT/genome_index/$(basename "$GENOME")"
echo "INDEX_READY $PREFIX.ggi"
echo "REPORT_JSON $PREFIX.json"

if [ -n "$GUIDES" ]; then
  if [ ! -f "$GUIDES" ]; then
    echo "error: guides TSV not found: $GUIDES" >&2
    exit 2
  fi
  echo "searching guides ..."
  "$PY" tools/search_indexed.py "$GUIDES" "$GENOME" "$OUT/search" \
    --index-path "$PREFIX" --max-mismatch 4 --require-pam
fi

echo "done. results are under $OUT"
