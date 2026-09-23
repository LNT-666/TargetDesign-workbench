# Native Indexed Off-target Engine Design

## 1. Purpose

Build a native C++ implementation of the local `indexed` off-target engine,
exposed as a standalone command-line program and called by the existing Python
backend.

The first goal is performance and predictable memory use for repeated searches
against a persistent local genome index. This design does not replace BLAST as
the recommended engine for one-off short-guide searches on GRCh38.

The implementation must preserve the current search contract:

- substitutions and small DNA/RNA bulges
- 3-prime and 5-prime PAM checks, including IUPAC PAM motifs
- plus-strand and reverse-complement searches
- 0-based genomic start coordinates
- unified hit fields consumed by scoring and export
- exhaustive behavior within the existing seed-plan contract

## 2. Scope

### In scope

- A C++ implementation of `build-index`, `inspect-index`, and `search` for the
  existing persistent `.ggi` index.
- Binary compatibility with the current Python index format version 1.
- A streaming, versioned CLI protocol that does not require a CPython
  extension.
- A Python adapter behind the existing public engine name `indexed`.
- Differential tests against `shared/search/genome_index.py` and
  `shared/search/exact_offtarget.py`.
- Linux support first, followed by Windows support.

### Out of scope

- Replacing `blast` or `gggenome`.
- Implementing the `exact` backend in C++.
- Moving scoring, filtering, GUI, web, or export logic into C++.
- Changing the public engine list or adding a user-visible
  `native-indexed` engine.
- Changing `auto` so that it silently builds a multi-gigabyte index for
  GRCh38. Large-genome `auto` remains BLAST-first unless the user provides
  `--index-path` or explicitly selects `indexed`.

## 3. Key Decisions

1. Use C++20 rather than C. The implementation needs RAII, containers,
   string views, threads, and file mapping. C is not a meaningful advantage
   here.
2. Build a standalone executable first. Do not start with `pybind11`,
   `nanobind`, or a CPython extension.
3. Reuse the current `.ggi` version 1 layout. Python-built indexes must be
   readable by C++, and native-built indexes must be readable by Python.
4. Keep Python as the orchestration and fallback layer.
5. Match the current Python indexed semantics exactly before optimizing the
   algorithm.
6. Prefer memory-mapped index files and streaming output. Do not reproduce
   Python's `dict[str, list[tuple]]` design in C++.
7. Keep deterministic output ordering independent of worker scheduling.

## 4. Repository Layout

Add the native source under a new top-level directory:

```text
native/
  offtarget_engine/
    CMakeLists.txt
    README.md
    include/offtarget/
      alignment.hpp
      fasta.hpp
      genome_index.hpp
      hit.hpp
      json_writer.hpp
      pam.hpp
      seed_plan.hpp
      search.hpp
    src/
      main.cpp
      alignment.cpp
      fasta.cpp
      genome_index.cpp
      pam.cpp
      seed_plan.cpp
      search.cpp
    tests/
      ...
```

Build output on Linux:

```text
native/bin/offtarget-engine
```

Build output on Windows:

```text
native/bin/offtarget-engine.exe
```

The binary directory must be configurable with `CMAKE_RUNTIME_OUTPUT_DIRECTORY`.

## 5. Build Requirements

- CMake 3.20 or newer
- C++20
- Linux: GCC 11+ or Clang 14+
- Windows: MSVC 2022
- Standard library threads
- No mandatory third-party runtime dependency

Third-party source dependencies are allowed only when vendored and pinned.
The preferred first version needs no JSON parser because guide input is TSV
and only JSON output needs to be encoded.

## 6. CLI Contract

The executable name is `offtarget-engine`.

All commands use exit codes:

| Code | Meaning |
| --- | --- |
| 0 | success |
| 2 | command-line usage error |
| 3 | unsupported search parameters or seed plan |
| 4 | input/output, index, or FASTA error |
| 5 | internal error |

Human-readable diagnostics go to stderr. Machine-readable data goes to stdout
or to the path selected by `--output`.

### 6.1 Version and capabilities

```bash
offtarget-engine --version
offtarget-engine capabilities --json
```

`--version` must print one line:

```text
offtarget-engine 0.1.0 index-format=1
```

`capabilities` returns:

```json
{
  "engine": "indexed",
  "implementation": "native-cpp",
  "index_format": 1,
  "max_build_k": 12,
  "threads": true,
  "indels": "dna_rna",
  "pam_sides": ["3prime", "5prime"]
}
```

### 6.2 Build index

```bash
offtarget-engine build-index \
  --genome /path/genome.fa \
  --prefix /path/genome_index/genome \
  --k 12 \
  --threads 8
```

Options:

- `--genome PATH`, required.
- `--prefix PREFIX`, required. The command writes `PREFIX.ggi` and
  `PREFIX.json`.
- `--k INT`, default `12`. The first release accepts `8..12`.
- `--threads INT`, default the number of available CPUs, capped by the
  implementation.
- `--contigs FILE`, optional one-contig-name-per-line filter.
- `--force`, rebuild even when a valid index exists.
- `--output PATH`, optional JSON summary path. Without it, the JSON summary
  goes to stdout.

The build is atomic:

1. Write `PREFIX.ggi.tmp`.
2. Write `PREFIX.json.tmp`.
3. fsync when supported.
4. Rename both files into place, index first and metadata second.

The JSON summary must preserve the existing keys:

```text
format, version, k, genome, genome_fingerprint, genome_bytes,
total_bases, valid_kmer_positions, contig_count, contigs,
position_dtype, build_time_s, memory_peak_mb, index_bytes
```

Native builds may add:

```text
producer, producer_version, threads, counts_time_s, fill_time_s
```

### 6.3 Inspect index

```bash
offtarget-engine inspect-index \
  --genome /path/genome.fa \
  --index /path/genome_index/genome \
  --json
```

Return:

```json
{
  "valid": true,
  "reason": "",
  "index_format": 1,
  "k": 12,
  "index_bytes": 13500000000,
  "position_dtype": "u4"
}
```

Validation must use the same fingerprint as Python:

- SHA256 over `size:mtime_ns`
- first 64 KiB of the FASTA
- last 64 KiB of the FASTA

### 6.4 Search

```bash
offtarget-engine search \
  --genome /path/genome.fa \
  --index /path/genome_index/genome \
  --guides guides.tsv \
  --output hits.jsonl \
  --max-mismatch 4 \
  --max-bulge 0 \
  --seed-len 12 \
  --require-pam \
  --pam TTGAT \
  --pam-side 5prime \
  --threads 8
```

Options:

- `--genome PATH`, required.
- `--index PREFIX`, required. `.ggi` and `.json` suffixes are accepted.
- `--guides PATH`, required. Use `-` for stdin.
- `--output PATH`, optional. Use `-` or omit for stdout.
- `--max-mismatch INT`, default `4`.
- `--max-bulge INT`, default `0`.
- `--seed-len INT`, default `12`.
- `--seed-mismatch INT`, optional. If omitted, use the indexed-backend
  precedence described below.
- `--seed-mismatch-max INT`, optional compatibility argument.
- `--require-pam`, optional.
- `--pam MOTIF`, required when `--require-pam` is set.
- `--pam-side 3prime|5prime`, default `3prime`.
- `--threads INT`, default the available CPU count, capped.
- `--cache-genome auto|true|false`, default `auto`.
- `--progress-every INT`, default `1`.
- `--max-candidates INT`, diagnostic guard only. The default is unlimited.
  This must never silently change exhaustive search semantics.

Guide input is a TSV with a header containing at least:

```text
qid	guide_seq
```

Additional columns are ignored. Guide sequences are uppercased and `U` is
converted to `T`.

## 7. Search Output Protocol

The search command writes JSON Lines. Every line is one complete JSON object.
The first line is metadata:

```json
{"type":"meta","schema_version":1,"engine":"indexed","implementation":"native-cpp","index_k":12}
```

Progress lines are optional:

```json
{"type":"progress","done":10,"total":100,"qid":"g9"}
```

Hit lines use the unified hit schema:

```json
{
  "type": "hit",
  "qid": "g0",
  "guide": "GCCTCTTTCCCACCCACCTT",
  "target": "chr1",
  "start": 12345,
  "strand": "+",
  "mismatch": 2,
  "indel": 0,
  "rna_bulges": 0,
  "dna_bulges": 0,
  "pam": "TTGAT",
  "bitscore": 76.0,
  "target_start": 12345,
  "target_end": 12365,
  "query_start": 0,
  "query_end": 20,
  "cigar": "20M",
  "aligned_guide": "GCCTCTTTCCCACCCACCTT",
  "aligned_target": "GCCTCTTTCCCACCCACCTT",
  "engine": "indexed"
}
```

The final line is a summary:

```json
{
  "type": "summary",
  "guides": 100,
  "hits": 12345,
  "candidates": 234567,
  "search_time_s": 12.345,
  "memory_peak_mb": 512.0,
  "seed_plan_guaranteed": true,
  "exhaustive_seed_plan": true
}
```

If a fatal error occurs before any hit is emitted, write an error object when
possible and exit with the documented code:

```json
{"type":"error","code":"STALE_INDEX","message":"index fingerprint does not match genome"}
```

JSON strings must escape backslash, double quote, newline, carriage return,
tab, and other control characters. Output files must be UTF-8.

## 8. Existing Index Format Version 1

The native implementation must read and write the layout below. All integers
are little-endian.

```text
magic                9 bytes   "CRISPRGGI"
format_version       1 byte    uint8, value 1
k                    4 bytes   uint32
contig_count         4 bytes   uint32
total_bases          8 bytes   uint64

for each contig:
  name_length        4 bytes   uint32
  name               N bytes   UTF-8
  start              8 bytes   uint64
  length             8 bytes   uint64

valid_count          8 bytes   uint64
offsets              8 * (4^k + 1) bytes, uint64 little-endian
positions            valid_count * position_width bytes
```

`position_width` is:

- 4 bytes when `total_bases < 2^32`
- 8 bytes otherwise

Invalid k-mer windows are excluded. A valid k-mer contains only `A`, `C`, `G`,
and `T` after uppercasing the FASTA sequence.

The metadata sidecar `PREFIX.json` is UTF-8 JSON. Extra keys are allowed.
Python's current loader ignores unknown metadata keys.

## 9. Index Build Algorithm

The target is bounded memory, not a direct translation of the NumPy builder.

### Pass 1

1. Scan FASTA records and build contig metadata in input order.
2. Count valid k-mers into `uint64 counts[4^k]`.
3. Compute `offsets[0..4^k]` from the counts.

For `k=12`, the offsets/counts tables are a few hundred MiB at most.

### Pass 2

1. Create a writable temporary positions file sized from `valid_count`.
2. Memory-map it and fill positions using a cursor table initialized from
   `offsets`.
3. For each valid k-mer window, write the 0-based global position into its
   bucket.
4. Use thread-local work chunks and atomic cursors. Contention is acceptable
   for the first version. Optimize only after profiling.
5. Bucket contents do not need to be sorted for correctness, because search
   deduplicates and sorts hits after candidate validation. If deterministic
   index bytes are required, sort each bucket before finalizing.

### Finalization

1. Write the v1 header, contig table, offsets, and positions to
   `PREFIX.ggi.tmp`.
2. Write metadata to `PREFIX.json.tmp`.
3. Rename atomically.

For GRCh38 with `k=12`, expected core storage is approximately:

- offsets: `(4^12 + 1) * 8` bytes, about 128 MiB
- positions: about 3.34 billion `uint32`, about 12.4 GiB

The build process must not allocate a second full `(code, position)` array.

## 10. Search Algorithm

### 10.1 Guide preparation

For each guide:

1. Uppercase and replace `U` with `T`.
2. Search the guide as the plus-strand probe.
3. Search its reverse complement as the minus-strand probe.
4. Skip empty or invalid guides using the same rules as Python.

### 10.2 Seed plan

Port `shared/search/seed_plan.py` exactly:

- minimum seed length is the index `k`
- minimum non-overlapping seed count is `max_bulge + 1`
- seed count ranges from that minimum through `probe_len / k`
- allowed mismatches per seed is `max_mismatch / (seed_count - max_bulge)`
- total variant work must stay under `DEFAULT_MAX_SEED_VARIANTS`
- the selected plan minimizes `(estimated_variants, seed_count)`

If no guaranteed plan exists:

- `index.total_bases <= 50,000,000`: perform the same exhaustive fallback
  scan as Python.
- larger genome: fail with `SearchParameterError` equivalent behavior and
  exit code 3.

Do not silently reduce sensitivity.

### 10.3 Seed mismatch precedence

Match the current indexed backend:

```text
seed_mm = params.seed_mismatch
if seed_mm is None:
    seed_mm = 0 if params.seed_mismatch_max is not None else 1
seed_mm = max(seed_mm, max_mismatch // 3)
```

The effective seed length is:

```text
max(params.seed_len or 12, index.k)
```

### 10.4 Candidate lookup

For each seed segment:

1. Iterate each k-mer window in the segment.
2. Enumerate all base-4 k-mer codes within the segment mismatch budget.
3. Look up the code bucket through `offsets[code]` and
   `offsets[code + 1]`.
4. Convert the global position to `(contig, local_start)`.
5. Skip duplicate candidates using `(contig, local_start, strand)`.

Enumerating base-4 codes is preferred over constructing Python-style strings.
The enumeration order does not affect the final sorted result, but it must
produce no fewer variants than Python.

### 10.5 Alignment

For each candidate, fetch:

```text
fetch_start = max(0, local_start - 40)
fetch_end = local_start + probe_len + 40
```

Call an alignment routine equivalent to
`shared/search/alignment.py::best_alignment`.

The scoring and tie-breaking rules are part of the contract:

- mismatch cost: 2
- gap cost: 3
- `I` means a query base against a target gap: RNA bulge
- `D` means a target base against a query gap: DNA bulge
- choose by:
  `(edit_cost, mismatches, indels, length_drift, center_distance, target_start, target_end)`

The native implementation may use a banded or SIMD-accelerated alignment
engine only after the simple port passes differential tests.

### 10.6 PAM

Port the behavior in `shared/search/exact_offtarget.py`:

- `_pam_ok_span`
- `_pam_sequence_span`
- IUPAC matching from `shared/search/iupac.py`

For minus-strand hits, compare against the reverse complement of the requested
PAM. Return the PAM in guide/query orientation in the hit record.

### 10.7 Hit conversion

Port `_alignment_to_hit` exactly. In particular:

- `start` is the 0-based genomic start of the aligned target span.
- `target_start` and `target_end` describe the actual alignment span.
- `query_start` and `query_end` are relative to the full guide.
- CIGAR uses `I` for RNA bulges and `D` for DNA bulges.
- `aligned_guide` and `aligned_target` describe the selected alignment.

### 10.8 Deduplication and ordering

Per `qid`, deduplicate by:

```text
(target, target_start, target_end, strand)
```

If duplicates exist, keep the one with:

```text
(mismatch, indel)
```

Sort final hits by:

```text
(mismatch, indel, target, start, target_end)
```

Emit guides in input-file order. Worker scheduling must not change output
ordering.

## 11. Parallelism and Memory

Parallelize at guide granularity first:

- fixed worker pool
- bounded input queue
- store the input ordinal with each guide
- buffer completed guide results
- emit them in input order

This preserves deterministic output. If a single guide produces an enormous
hit list, later work may need a per-guide temporary spill file. Do not add
spill logic until a real benchmark shows it is required.

The native engine removes Python object overhead for the index and candidate
search. It does not automatically solve accumulation of final hits in the
Python `IndexedBackend.search()` return dictionary. Benchmark hit count before
claiming a complete memory fix.

## 12. FASTA Access

Build a standard `<genome_fasta>.fai` sidecar when it does not exist. Reuse an
existing pyfaidx-compatible `.fai` when its contents validate.

The sidecar stores:

```text
contig	name_length	offset	line_bases	line_width
```

Use positional reads for alignment windows. If `.fai` creation fails, fall back
to loading the genome into memory only when the FASTA is below a configurable
limit, initially 2 GiB. Otherwise fail with a clear error.

The sequence exposed to search must be uppercased. `U` may be normalized to
`T` for probes; genome windows keep the same invalid-base behavior as Python.

## 13. Python Integration

Add:

```text
shared/search/native_offtarget.py
```

Responsibilities:

- locate `offtarget-engine`
- validate `--version` and index format compatibility
- run `inspect-index`
- run `build-index` when the current Python backend would rebuild
- run `search`
- parse JSONL
- group hit events by `qid`
- fill `IndexedBackend.last_report`

Binary search order:

1. `PROGRAMFILE_OFFTARGET_NATIVE`
2. `native/bin/offtarget-engine[.exe]`
3. `offtarget-engine` from `PATH`

Feature flag:

```text
PROGRAMFILE_NATIVE_INDEXED=auto|0|1
```

Rollout state:

- default: `auto`
- emergency rollback: `PROGRAMFILE_NATIVE_INDEXED=0`

Fallback policy:

- Native binary absent or incompatible: use Python.
- Native fails before emitting a hit: Python fallback is allowed by default;
  set `PROGRAMFILE_NATIVE_INDEXED_FALLBACK=0` to disable it.
- Native fails after emitting a hit: do not silently rerun unless the caller
  explicitly enables fallback.

Do not add a new public engine. `IndexedBackend` remains the integration
point. `last_report["implementation"]` must be `native-cpp` or `python`.

## 14. Error Mapping

Map native errors to Python exceptions before invoking the backend:

| Native condition | Python result |
| --- | --- |
| unsupported parameter | `SearchParameterError` |
| stale or missing index | build index, then retry once |
| malformed index | `RuntimeError` with index path |
| missing FASTA or guide file | `FileNotFoundError` |
| native runtime failure | `RuntimeError` with stderr tail |

Never swallow a nonzero exit code. Include the command name, exit code, and
last 4 KiB of stderr in the Python error.

## 15. Verification

### 15.1 Unit tests

- FASTA parser and `.fai` access
- base-4 encoding for all `A/C/G/T` combinations
- invalid-base boundary handling
- seed-plan golden cases from `tests/test_offtarget_backend.py` and
  `shared/search/seed_plan.py`
- global alignment and tie-breaking
- CIGAR construction
- IUPAC PAM matching on both strands and both PAM sides
- JSON escaping

### 15.2 Index compatibility tests

1. Build a small index with Python, search and inspect it with native.
2. Build the same index with native, load it with Python `load_index`.
3. Compare contig metadata, k, total bases, offsets, and every position bucket.
4. Modify the FASTA and verify both implementations mark the index stale.
5. Corrupt the magic, version, offsets, and positions and verify clear errors.

### 15.3 Differential search tests

Generate small random genomes and compare native and Python indexed results for:

- mismatch-only and bulge-enabled searches
- 3-prime and 5-prime PAM
- plus and minus strand hits
- IUPAC PAMs
- hits near contig boundaries
- duplicate and palindromic candidates
- guides containing `U`
- invalid genome bases
- guaranteed and non-guaranteed seed plans

Compare the complete hit set after applying the canonical sort order. Compare
every unified field, not only coordinates.

### 15.4 Integration tests

- `IndexedBackend.search()` with native enabled
- automatic native build and retry for a missing index
- fallback to Python with native disabled
- fallback to Python after an early native failure
- `last_report` fields and progress output

### 15.5 Performance benchmark

Use:

- `example/chr21_22.fa` for correctness and quick benchmarks
- GRCh38 `GCF_000001405.40_GRCh38.p14_genomic.fna` for final measurements

Record:

- index build wall time
- index bytes
- peak RSS
- search wall time
- guides per second
- candidates per guide
- final hits per guide
- seed-plan variant estimate

The native search result must be compared against the Python result for the
same guide subset before any performance conclusion.

## 16. Delivery Phases

### Phase 1: Native search over Python-built index

- Implement FASTA random access.
- Implement index reader.
- Implement seed plan, candidate lookup, alignment, PAM, and JSONL output.
- Pass differential tests on small fixtures.

This isolates the search semantics before adding index construction.

### Phase 2: Native index builder

- Implement memory-bounded v1 writer.
- Add atomic replacement and metadata generation.
- Prove byte-level or semantic compatibility with Python indexes.

### Phase 3: Python adapter

- Add `native_offtarget.py`.
- Integrate behind `IndexedBackend`.
- Keep Python fallback and feature flag.
- Keep the Python indexed implementation as a supported fallback rather than
  deleting it, so Windows, missing-binary, incompatible-binary, and explicit
  rollback paths remain usable.

### Phase 4: Parallelism and profiling

- Add deterministic guide-level workers.
- Profile index build and candidate alignment separately.
- Optimize only measured bottlenecks.

### Phase 5: Rollout

- Run chr21/22 and GRCh38 benchmarks.
- Enable native `indexed` by default only when:
  - differential tests pass
  - hit output is identical
  - peak memory is bounded
  - rollback remains available

## 17. Required Handoff Artifacts

The implementation session must leave:

- native source and CMake build
- Linux and Windows build instructions
- native unit and differential tests
- Python adapter and fallback tests
- a benchmark report checked into `docs/`
- updated `docs/OFFTARGET_ENGINES.md`
- a clear statement of remaining limitations, especially final-hit memory

## 18. Final Recommendation

Implement the native engine as a C++20 standalone CLI for the persistent
`indexed` backend. Reuse `.ggi` version 1, match Python semantics exactly, and
integrate through `IndexedBackend` only after differential tests pass.

Do not port `exact`. On GRCh38, exhaustive short-guide search with four
mismatches remains computationally expensive even after removing Python
overhead. BLAST remains the recommended default for one-off large-genome
searches.
