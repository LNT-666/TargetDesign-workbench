# English help materials

This directory holds the English help page and the step-by-step tutorial for
**TargetDesign-workbench**. They are the English help material required by the
NAR Web Server issue guidelines for stand-alone applications:

> contain help pages and/or a tutorial with links to sample output in English
> ... The help pages must include information on how to interpret the results
> returned by the applications.
>
> include a simple mechanism to try out sample data provided by the authors
> ... Sample data must be accessible to users so that they can confirm data
> formatting requirements.

## Contents

| Document | What it gives you |
| --- | --- |
| [`index.md`](index.md) | Help page. What the software does, how to install and start it, a field-by-field description of the Designer form, and a column-by-column guide to interpreting the result files. |
| [`tutorial.md`](tutorial.md) | Tutorial. A full worked example on the bundled sample data, with the expected output of every step, both in the web workbench and from the command line. |
| [`sample_output/`](sample_output/) | Links-target. Real output of the tutorial run, trimmed to small files so every number quoted in the tutorial can be checked against an actual result file. |

## Where the sample data live

The tutorial uses the data set committed under [`sample_data/`](../../sample_data/):

| File | What it is |
| --- | --- |
| `sample_data/demo_genome.fa` | 5,000,000 bp synthetic genome in four contigs. |
| `sample_data/demo_batch.json` | A one-unit batch specification (one scope, one pattern). |
| `sample_data/demo_guides.tsv` | The 24 guides used by the engine benchmark. |

`sample_data/README.md` describes the data set and its provenance in full. The
sample data are plain files in the repository, so they can be inspected and
re-used without a download. In the web workbench the same run is reproduced by
loading `sample_data/demo_genome.fa` in the **Data prep** panel and entering the
pattern values of `demo_batch.json` in the Designer.

## Licence

MIT, see [`LICENSE`](../../LICENSE) at the repository root. The licence allows
free access and re-use for non-commercial purposes. The sample genome and the
sample guides are synthetic and carry the same MIT licence; they contain no
third-party sequence.

## Reporting problems

Questions, bug reports and feature requests go to the project issue tracker:

<https://github.com/LNT-666/TargetDesign-workbench/issues>

## Provenance of `sample_output/`

Every file under `sample_output/` is a trimmed copy of a real run of the
tutorial command:

```bash
python tools/batch_run.py --spec sample_data/demo_batch.json
```

The reference copies come from run `output/20261007-0514` (batch label
`sample-batch`, unit `demo__NGG`, manifest status `ok`, return code 0). Only
the file sizes were reduced: rows were cut down to a head, nothing was
recalculated or hand-edited. `sample_output/README.md` lists the exact
truncation applied to each file.
