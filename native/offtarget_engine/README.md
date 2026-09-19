# Native Indexed Off-target Engine

This directory contains the standalone C++20 implementation of the
`indexed` off-target search contract. It reads and writes the existing
CRISPRGGI version 1 format and does not replace the `exact`, BLAST, or
Python fallback paths.

## Build

Linux:

```bash
cmake -S native/offtarget_engine -B native/build \
  -DCMAKE_BUILD_TYPE=Release \
  -DOFFTARGET_BUILD_TESTS=ON
cmake --build native/build -j
```

Windows with MSVC 2022:

```powershell
cmake -S native/offtarget_engine -B native/build `
  -DOFFTARGET_BUILD_TESTS=ON
cmake --build native/build --config Release
```

The executable is written to `native/bin/offtarget-engine` (`.exe` on
Windows). Override the output directory with
`-DOFFTARGET_RUNTIME_OUTPUT_DIRECTORY=...`.

## Commands

```bash
offtarget-engine --version
offtarget-engine capabilities --json
offtarget-engine inspect-index \
  --genome genome.fa --index genome_index/genome --json
offtarget-engine build-index \
  --genome genome.fa --prefix genome_index/genome --k 12 --threads 8 \
  --max-memory-mb 32768
offtarget-engine search \
  --genome genome.fa --index genome_index/genome \
  --guides guides.tsv --output hits.jsonl \
  --max-mismatch 4 --max-bulge 0 --seed-len 12 \
  --require-pam --pam NGG --pam-side 3prime \
  --max-memory-mb 32768
```

`search` emits JSON Lines: one metadata object, ordered hit objects,
optional progress objects, and one summary object.

## Python Integration

The Python adapter is `shared/search/native_offtarget.py`. It uses
auto-discovery by default:

```text
PROGRAMFILE_NATIVE_INDEXED=0|auto|1
PROGRAMFILE_OFFTARGET_NATIVE=/path/to/offtarget-engine
PROGRAMFILE_NATIVE_INDEXED_FALLBACK=0|1
PROGRAMFILE_MAX_MEMORY_MB=32768
```

`IndexedBackend` remains the only public integration point. When native is
enabled and a usable binary is present, missing or stale indexes are built
with native `build-index`; otherwise the existing Python implementation is
used. Set `PROGRAMFILE_NATIVE_INDEXED=0` to force Python. An early native
failure falls back to Python by default; set
`PROGRAMFILE_NATIVE_INDEXED_FALLBACK=0` to disable that fallback.
`--max-memory-mb N` sets an explicit process RSS ceiling for either command;
omitted or `0` means unlimited. The CLI value overrides
`PROGRAMFILE_MAX_MEMORY_MB`. A native `MEMORY_LIMIT_EXCEEDED` result is never
allowed to fall back to an unrestricted Python run.

Native is the preferred implementation; the Python backend is intentionally
retained as a supported fallback for missing or incompatible binaries,
Windows portability, explicit rollback, and differential testing. Current
benchmark results and the derived `auto` order are documented in
`example/engine_benchmark_small/REPORT.md`.

## Current Limits

- Search uses a worker pool over guides. The memory-mapped `GenomeIndex` is
  shared read-only, while each worker opens its own positional FASTA reader
  and optional sequence cache. Results are merged in input order, so the hit
  sequence is deterministic and identical across `--threads` values.
- `--cache-genome true` loads each requested contig into the calling worker's
  cache; peak memory therefore grows with the number of workers. `auto`
  estimates one full genome copy per effective worker, adds per-worker
  overhead, reserves 2 GiB, and enables caching only when the estimate fits
  half of the currently available memory.
- Final hits are accumulated in memory by qid, matching the current Python
  backend contract.
- Search and build preflight estimates plus runtime RSS checks are bounded by
  `--max-memory-mb`. Search cancels all workers after an over-limit
  observation and emits no JSONL until the complete result set is ready.
- `k=8..12` is supported for native builds. Search can read any valid v1
  index produced by Python.
