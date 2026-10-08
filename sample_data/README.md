# Sample data

A small, self-contained data set for trying the workbench without downloading a genome.
Everything here is synthetic and small enough to be committed to the repository.

## Contents

| File | Size | What it is |
| --- | --- | --- |
| `demo_genome.fa` | 5.0 MB | 5,000,000 bp in four contigs, written by the synthetic fixture builder of `tools/benchmark_all_engines.py`. Sequence is uniform random A/C/G/T with no repeats, so every reported hit can be checked by hand. |
| `demo_target.fa` | 200 kB | The first 200,000 bp of `chr1`, sliced out of `demo_genome.fa`. It is the **scope** of the demo: guides are designed from here while the off-target search runs over the whole genome. |
| `demo_guides.tsv` | <1 kB | 24 twenty-nucleotide guides used by the engine benchmark; for each guide the fixture contains one exact target, one reverse-complement exact target and one one-mismatch target. |
| `demo_batch.json` | <1 kB | A batch specification with one scope (the 200 kb target region) and one pattern (an `NGG` anchor, 20 nt target, downstream side) under the SpCas9 rules. The scope keeps `mask_same_as_target: true`, so on-target loci are excluded from the off-target table. |

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

then open <http://127.0.0.1:5000> and click **Load sample data** in the top bar: it fills the
Designer with the genome, the target region, the mask and the `NGG` / 20 nt / downstream values,
and never starts a run. The result is the `demo_batch.json` configuration, so the run matches the
sample output; the walkthrough in `../docs/help_en/tutorial.md` describes each step by hand.

## Provenance

The genome and the guide set are the fixture written by `tools/benchmark_all_engines.py`;
`demo_target.fa` is a plain slice of that genome. They contain no third-party sequence and carry
the same MIT licence as the rest of the repository.

## What a demo run produces

Measured with `sample_data/demo_batch.json`, one unit, no resume:

| Quantity | Value |
| --- | --- |
| Extracted candidates (`extracted_seqs.tsv`) | 24,211 unique sequences covering 25,024 positions |
| Scored rows (`query_scores_sorted.tsv`) | 25,024 |
| Off-target rows (`top_offtargets.tsv`) | 180 |
| Wall clock | 16 s on a local disk |
| Manifest status | `ok`, return code 0 |
| Output size | ~54 MB |
| Warnings | 1: `no mm=0 flanking sequence found for chr1; skipped` |

Outputs land in `output/<date>-<id>/`: `manifest.tsv`, `run.json`, `run.log`, `batch.json`,
`summary/batch_scores.tsv`, and per unit a candidate table, `top_offtargets.tsv`,
`query_scores.bed`, the built index under `genome_index/`, and the extracted candidate list.

The scope is already limited to the 200 kb target region; to go faster still, narrow it with a BED
region file, lower `max_mismatch`, or tighten `gc_min` / `gc_max` in `demo_batch.json`.
