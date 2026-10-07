# Sample data

A small, self-contained data set for trying the workbench without downloading a genome.
Everything here is synthetic and small enough to be committed to the repository.

## Contents

| File | Size | What it is |
| --- | --- | --- |
| `demo_genome.fa` | 5.0 MB | 5,000,000 bp in four contigs, written by the synthetic fixture builder of `tools/benchmark_all_engines.py`. Sequence is uniform random A/C/G/T with no repeats, so every reported hit can be checked by hand. |
| `demo_guides.tsv` | <1 kB | 24 twenty-nucleotide guides used by the engine benchmark; for each guide the fixture contains one exact target, one reverse-complement exact target and one one-mismatch target. |
| `demo_batch.json` | <1 kB | A batch specification that runs one scope (the demo genome) against one pattern (an `NGG` anchor, 20 nt target, downstream side) with the SpCas9 rules. |

## Running it

Batch entry point (writes to `output/<date>-<id>/`):

```bash
python tools/batch_run.py --spec sample_data/demo_batch.json --dry-run   # check the plan first
python tools/batch_run.py --spec sample_data/demo_batch.json
```

Local web workbench:

```bash
python webapp/app.py --host 127.0.0.1
```

then open <http://127.0.0.1:5000>, load `sample_data/demo_genome.fa` as the genome and use the
same pattern values as `demo_batch.json`.

## Provenance

The genome and the guide set are the fixture written by `tools/benchmark_all_engines.py`; they contain
no third-party sequence and carry the same MIT licence as the rest of the repository.
## What a demo run produces

Measured on a Linux host (256 cores) with `sample_data/demo_batch.json`, one unit, no resume:

| Quantity | Value |
| --- | --- |
| Extracted candidates (`extracted_seqs.tsv`) | 604,376 |
| Scored rows (`query_scores_sorted.tsv`) | 623,743 |
| Wall clock | 3 min 49 s |
| Manifest status | `ok`, return code 0 |
| Output size | ~134 MB |
| Warnings | 4, one per contig: `no mm=0 flanking sequence found for chrN; skipped` |

Outputs land in `output/<date>-<id>/`: `manifest.tsv`, `run.json`, `run.log`, `batch.json`,
`summary/batch_scores.tsv`, and per unit a candidate table, `top_offtargets.tsv`,
`query_scores.bed`, the built index under `genome_index/`, and the extracted candidate list.

To make a demo run finish quickly, restrict the scope with a BED region file instead of the whole
genome, or tighten `gc_min` / `gc_max` in `demo_batch.json`.