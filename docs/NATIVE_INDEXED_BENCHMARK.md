# Native Indexed Engine Benchmark

Measured on `ms01` on 2026-09-14 with a Release build:

```text
logical CPUs: 256
memory: 1007 GiB
workspace: /home/apool/songji/programfile
binary: native/bin/offtarget-engine
```

The fixture is `example/engine_benchmark/synthetic_genome.fa`: four contigs,
5,000,000 bp total, index `k=10`. The index was rebuilt from that FASTA into
`/tmp` before the measurements.

## Mismatch-only parallel search

This run used `max_mismatch=2`, `max_bulge=0`, `--require-pam --pam NGG`,
`--cache-genome true`, and 2,400 guides formed by repeating the 24 fixture
guides 100 times with unique qids. All thread counts returned 1,000 hits; the
hit-only JSON Lines files had the same SHA-256 digest. The 1, 8, and 32 thread
rows are medians of three warm runs; the 4 and 16 thread rows are single warm
runs.

| threads | wall time | engine search time | process peak RSS | hits |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 1.37 s | 1.348 s | 34.0 MiB | 1000 |
| 4 | 0.41 s | 0.382 s | 50.0 MiB | 1000 |
| 8 | 0.26 s | 0.225 s | 70.0 MiB | 1000 |
| 16 | 0.20 s | 0.154 s | 107.0 MiB | 1000 |
| 32 | 0.16 s | 0.111 s | 204.0 MiB | 1000 |

The 32-thread warm run is 8.6x faster than one thread in this small-cache
workload. The exact speedup depends on guide count, cache policy, storage,
and CPU availability.

## Bulge stress search

This run used `max_mismatch=2`, `max_bulge=1`, `--require-pam --pam NGG`,
`--cache-genome true`, and 240 guides formed by repeating the 24 fixture
guides 10 times. All thread counts returned 160 hits with the same hit-only
digest. These are single warm runs; this configuration is intentionally
expensive because it combines a two-mismatch budget with gapped alignment.

| threads | wall time | engine search time | process peak RSS | hits |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 81.14 s | 81.128 s | 32.0 MiB | 160 |
| 4 | 20.43 s | 20.419 s | 50.0 MiB | 160 |
| 8 | 10.33 s | 10.322 s | 70.0 MiB | 160 |
| 16 | 5.43 s | 5.412 s | 120.0 MiB | 160 |
| 32 | 2.85 s | 2.834 s | 212.0 MiB | 160 |

The 32-thread run is 28.5x faster than one thread on this stress fixture.
The thread-local alignment workspace is reused within each worker; the
`max_bulge=0` path remains the direct substitution scan without DP.

## FASTA cache policy

The same 2,400-guide mismatch-only search with `--cache-genome false` showed
the positional-reader path limiting parallel scaling:

| threads | median wall time | process peak RSS |
| ---: | ---: | ---: |
| 1 | 13.53 s | 28.0 MiB |
| 2 | 7.20 s | 28.0 MiB |
| 4 | 6.19 s | 24.0 MiB |
| 8 | 6.14 s | 24.0 MiB |
| 16 | 6.32 s | 22.0 MiB |
| 32 | 6.41 s | 20.0 MiB |

For small genomes whose complete sequence fits the configured cache policy,
`--cache-genome true` or `auto` is therefore much faster. For large genomes,
each worker cache has a memory cost. The `auto` policy therefore reserves
2 GiB, estimates one full genome copy plus 16 MiB of overhead per effective
worker, and enables caching only when that estimate fits half of the currently
available memory. Explicit `--cache-genome true` bypasses this guard and is
the caller's memory-risk decision.

## Reproduce

```bash
cd /home/apool/songji/programfile

awk 'NR==1 {print; next} {for (i=1; i<=100; i++) \
  print $1 "_" i "\t" $2}' example/engine_benchmark/guides.tsv \
  > /tmp/native_guides_2400.tsv

./native/bin/offtarget-engine build-index \
  --genome example/engine_benchmark/synthetic_genome.fa \
  --prefix /tmp/native_bench_index --k 10 --threads 32 --force

for threads in 1 32; do
  /usr/bin/time -f 'wall_s=%e maxrss_kb=%M' \
    ./native/bin/offtarget-engine search \
    --genome example/engine_benchmark/synthetic_genome.fa \
    --index /tmp/native_bench_index \
    --guides /tmp/native_guides_2400.tsv \
    --output "/tmp/native_hits_${threads}.jsonl" \
    --max-mismatch 2 --max-bulge 0 --seed-len 10 \
    --require-pam --pam NGG --pam-side 3prime \
    --threads "$threads" --cache-genome true --progress-every 0
  grep '"type":"hit"' "/tmp/native_hits_${threads}.jsonl" \
    > "/tmp/native_hits_${threads}.hits"
done
```

Compare deterministic hit output after removing summary timing fields:

```bash
cmp /tmp/native_hits_1.hits /tmp/native_hits_32.hits
```

## Hot-path container decision

The candidate hot path still uses the existing `std::unordered_set` and
`std::function` APIs. No isolated A/B comparison established a reliable gain
from replacing them, so this phase keeps that implementation rather than
expanding the behavioral change surface. The measured gains above come from
guide parallelism, direct position decoding from the already-fetched offset
span, first-discovery candidate deduplication, and reusable gapped-alignment
workspace.
