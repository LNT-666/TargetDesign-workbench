# Off-target engine benchmark

Tested on a Linux workstation with a synthetic 1,000,000 bp genome, 12 guides of
20 nt, 8 threads for external tools, and the median of 3 repeated searches.

The fixture contains one sampled exact target, one reverse-complement exact
target, and one one-mismatch target per guide. The main comparison uses
`max_mismatch=0, max_bulge=0` so every engine starts from the same 24 exact
planted hits.

## Exact-match benchmark

| engine | build/index time | warm search median | build + warm search | hits |
| --- | ---: | ---: | ---: | ---: |
| native-indexed | 0.107 s | 0.048 s | 0.155 s | 24 |
| blast | 0.060 s | 0.518 s | 0.578 s | 24 |
| bowtie2 | 0.902 s | 0.176 s | 1.078 s | 24 |
| indexed, Python | 0.178 s | 0.990 s | 1.168 s | 24 |
| casoffinder | no persistent build | 1.547 s | 1.547 s | 24 |
| exact | no persistent build | 2.156 s | 2.156 s | 24 |

`exact` builds an in-memory search structure on every call, so its search
time is not comparable to a warm persistent-index search.

## Bulge overhead

Same fixture and `max_mismatch=0`, but with `max_bulge=1`. Cas-OFFinder is
excluded because the current backend rejects bulge requests.

| engine | build/index time | warm search median | build + warm search |
| --- | ---: | ---: | ---: |
| native-indexed | 0.095 s | 0.183 s | 0.278 s |
| blast | 0.099 s | 0.565 s | 0.664 s |
| bowtie2 | 0.886 s | 0.176 s | 1.062 s |
| exact | no persistent build | 2.617 s | 2.617 s |
| indexed, Python | 0.182 s | 8.729 s | 8.911 s |

This fixture does not plant a true bulge hit. These numbers measure the cost
of enabling bulge search, not bulge recall.

## Notes

- Auto rule derived from this benchmark: explicit `--blastdb` selects BLAST;
  explicit `--index-path` selects indexed. With neither resource and at most
  200 Mbp, use native indexed when available. Without native indexed,
  `max_bulge=0` tries BLAST, Bowtie2, Python indexed, Cas-OFFinder, then
  exact; `max_bulge=1` tries BLAST, Bowtie2, exact, then Python indexed.
  Above 200 Mbp, prefer BLAST over automatically building a very large index.
  If `max_bulge` is not explicit, auto defaults to `max_bulge=0`.
- `GGGenome` searches remote prebuilt genome databases and cannot be compared
  against this custom FASTA fixture.
- A separate 1-mismatch stress run returned 36/36 hits from exact, indexed,
  native-indexed, and Cas-OFFinder. BLAST returned 31/36 because its local
  alignment extension truncated some one-mismatch 20 nt alignments. BLAST
  speed should therefore be interpreted together with that recall difference.
- Raw results are in `results_mm0.json`, `results_bulge1.json`, and
  `results_bulge0.json`.

Reproduce with:

```bash
python tools/benchmark_all_engines.py \
  --fixture-dir example/engine_benchmark_small \
  --genome-mb 1 --guides 12 --max-mismatch 0 --max-bulge 0 \
  --index-k 8 --threads 8 --repeats 3
```
