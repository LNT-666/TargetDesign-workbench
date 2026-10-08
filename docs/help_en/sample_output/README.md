# Sample output

Real output files of the tutorial run, trimmed so that they can be committed.
Every file is a verbatim copy of the corresponding file of run
`output/20261008-0114`; only whole rows were removed.

## Source run

| Property | Value |
| --- | --- |
| Command | `python tools/batch_run.py --spec sample_data/demo_batch.json` |
| Run directory | `output/20261008-0114/` |
| Batch label | `sample-batch` |
| Unit | `demo__NGG` (scope `demo`, pattern `NGG`) |
| Scope / mask | `sample_data/demo_target.fa` (the first 200 kb of `chr1`), mask same as target |
| Genome searched | `sample_data/demo_genome.fa` |
| Manifest status | `ok`, return code 0 |
| Started / finished | 2026-10-08 09:37:26 / 2026-10-08 09:37:42 (16 s) |
| Host | Windows; the wall clock depends on disk speed and this run reads from a local disk |

## Files

| File | Source | Truncation |
| --- | --- | --- |
| `query_scores_sorted.head20.tsv` | `demo__NGG/query_scores_sorted.tsv` | Header plus the first 20 data rows (of 25,024). |
| `extracted_seqs.head20.tsv` | `demo__NGG/extracted_seqs.tsv` | The `# motif=...` comment, the header and the first 20 data rows (of 24,211 unique sequences). |
| `summary.batch_scores.head20.tsv` | `summary/batch_scores.tsv` | Header plus the first 20 data rows (of 25,024). |
| `top_offtargets.tsv` | `demo__NGG/top_offtargets.tsv` | Complete file: all 180 ranked off-target rows. |
| `manifest.tsv` | `manifest.tsv` | Complete file (one row per unit). |
| `run.json` | `run.json` | Complete file. |

The full tables are not reproduced here: the untrimmed output of this run is
about 54 MB. Re-running the command above regenerates all of it.

## Column layout

The column names are in the header of each file. `docs/help_en/index.md`
Section 6 explains them one by one; note that only the columns used by this run
are present, because the writer drops columns that are empty in every row.
