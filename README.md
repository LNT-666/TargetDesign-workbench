# TargetDesign-workbench

[English](README.md) | [简体中文](README.zh-CN.md)

TargetDesign-workbench is a motif-first workbench for CRISPR guide design,
genome-wide off-target search, candidate scoring, and reproducible batch
analysis. It provides a desktop application, a local web interface, and
command-line tools backed by the same design and search modules.

The workbench is intended for research use. It supports SpCas9, Cas12a,
Cas12b, Cas13, TnpB, and user-defined PAM/TAM layouts without assuming a fixed
design template.

## What it does

The analysis follows one explicit pipeline:

```text
define a motif-based pattern
  -> extract candidate regions
  -> search the genome for off-targets
  -> score, filter, and rank candidates
  -> export the selected results
```

Core capabilities:

- Motif-first patterns, including single-motif flanking layouts, motif-gap-motif
  layouts, and Y-centered paired motifs.
- Configurable target length, motif position, strand orientation, and IUPAC
  PAM/TAM definitions.
- Exact, indexed, BLAST, GGGenome, and automatic off-target engine selection.
  The indexed backend has a native C++20 implementation with a Python fallback.
- Published on-target and off-target rule sets, model adapters, mismatch and
  bulge handling, and pair-ranking workflows.
- Batch execution with resumable runs, manifests, combined score tables, and
  command-line or web entry points.
- Export to TSV, CSV, FASTA, BED, and XLSX.
- Reproducible examples using the synthetic data bundled in `sample_data/`.

The legacy Library export workflow is deprecated and is not part of the active
product surface. See the Chinese documentation for current module-level status
details.

## Installation

Python >=3.12,<3.14 is supported; recommended version: Python 3.12. The
commands below use compatible dependency ranges, not pinned versions. Formal
CPU/CUDA snapshots are documented in docs/ENVIRONMENT.md using
requirements/constraints-linux-cpu.txt with
requirements/requirements-linux-cpu.txt, and
requirements/constraints-linux-cuda.txt with
requirements/requirements-linux-cuda.txt.

### Windows

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements-windows.txt
```

### Linux or macOS

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-linux.txt
```

NCBI BLAST+ is optional. Install it only when using the `blast` engine and make
sure `blastn` and `makeblastdb` are available on `PATH`.

Third-party model weights are not redistributed with the repository. Runs that
use only published rule sets do not require model downloads. Model setup and
conversion are described in [`docs/MODELS.md`](docs/MODELS.md) and
[`docs/ENVIRONMENT.md`](docs/ENVIRONMENT.md).

## Quick start

### Local web interface

```bash
python webapp/app.py --host 127.0.0.1
```

Open <http://127.0.0.1:5000>. Long-running index builds, searches, and batches
are queued and report progress in the run log.

### Desktop workbench

```bash
python designer_workbench.py
```

On Windows, `TargetDesign-workbench.exe` is the packaged launcher.

### Container

```bash
docker run --rm -p 127.0.0.1:5000:5000 \
  ghcr.io/lnt-666/targetdesign-workbench:latest
```

Pin a release tag instead of `latest` for reproducible analysis. Container
targets, persistence, and versioned images are documented in
[`docs/CONTAINER.md`](docs/CONTAINER.md).

## Reproducible example

The repository includes a small synthetic genome, target region, guide set, and
batch specification. No download is required.

Validate the batch plan first:

```bash
python tools/batch_run.py --spec sample_data/demo_batch.json --dry-run
```

Run the example:

```bash
python tools/batch_run.py --spec sample_data/demo_batch.json
```

The run writes to `output/<YYYYMMDD>-<ID>/` and produces:

```text
manifest.tsv
run.json
run.log
summary/batch_scores.tsv
demo__NGG/extracted_seqs.tsv
demo__NGG/query_scores_sorted.tsv
demo__NGG/top_offtargets.tsv
demo__NGG/query_scores.bed
```

For the bundled specification, the reference run extracts 24,211 unique
candidate sequences covering 25,024 positions, writes 25,024 scored rows and
180 ranked off-target rows, and produces about 54 MB of output. Wall-clock time
depends on the machine and storage; the recorded local-disk run took about 16
seconds.

Trimmed reference outputs and their provenance are in
[`docs/help_en/sample_output/`](docs/help_en/sample_output/). The step-by-step
walkthrough is in [`docs/help_en/tutorial.md`](docs/help_en/tutorial.md).

## Main interfaces

| Entry point | Purpose |
| --- | --- |
| `webapp/app.py` | Local web workbench with queued runs and result browsing |
| `designer_workbench.py` | Current desktop workbench organized around the result table |
| `unified_gui.py` | Unified pattern and candidate-table desktop interface |
| `main.py` | Legacy launcher and data-preparation entry points |
| `tools/batch_run.py` | Batch CLI using the same shared analysis modules |

Supported pattern kinds are defined in `shared/design/pattern_spec.py`:
`SINGLE_MOTIF_FLANK`, `MOTIF_GAP_MOTIF`, and `Y_CENTERED_MOTIFS`.

## Repository layout

```text
basic/             single-motif command-line workflows
docs/              public guides, references, and English help
example/           small reproducibility and benchmark examples
native/            C++20 indexed-engine source and build instructions
sample_data/       synthetic quick-start data
shared/            design, search, scoring, data, and output modules
tests/             Python regression suite
tools/             index, search, batch, benchmark, and release tools
webapp/            local web service and run storage
CITATION.cff       citation metadata
Dockerfile         container image
README.md          English overview
README.zh-CN.md    Chinese overview
```

Large genome indexes, model weights, and run products are intentionally kept
out of the repository.

## Documentation

English:

- [`docs/help_en/index.md`](docs/help_en/index.md) - complete help page,
  interface fields, result layout, and troubleshooting.
- [`docs/help_en/tutorial.md`](docs/help_en/tutorial.md) - worked example with
  expected output at each step.
- [`docs/help_en/sample_output/README.md`](docs/help_en/sample_output/README.md)
  - source run and truncation rules for the committed reference tables.
- [`docs/design_patterns_en.md`](docs/design_patterns_en.md) - pattern notation.

Chinese mirror and reference documentation:

- [`README.zh-CN.md`](README.zh-CN.md) - Chinese project overview.
- [`docs/OUTPUTS.md`](docs/OUTPUTS.md) - result files and output columns.
- [`docs/OFFTARGET_ENGINES.md`](docs/OFFTARGET_ENGINES.md) - engine capabilities
  and fallback behavior.
- [`docs/SCORING_GUIDE.md`](docs/SCORING_GUIDE.md) - scoring fields and rules.
- [`docs/PAIR_RANKING.md`](docs/PAIR_RANKING.md) - paired-target ranking.
- [`docs/TNPB.md`](docs/TNPB.md) - TnpB and TEEP details.
- [`GLOSSARY.md`](GLOSSARY.md) - project terminology.

## Tests and release checks

Run the Python regression suite:

```bash
python run_tests.py
```

Run the suite with branch coverage:

```bash
python -m pip install -r requirements-test.txt
python -m coverage run run_tests.py
python -m coverage report
```

Optional release checks:

```bash
python tools/check_release_metadata.py
python tools/dep_scan.py --check
python tools/batch_run.py --spec sample_data/demo_batch.json --dry-run
```

The release bundle builder is documented in
[`docs/PACKAGING.md`](docs/PACKAGING.md).

## Citation

Release v0.3.4 is archived at
<https://doi.org/10.5281/zenodo.24026181>. The concept DOI covering all
versions is <https://doi.org/10.5281/zenodo.23231712>. Citation metadata is
maintained in [`CITATION.cff`](CITATION.cff).

## License

TargetDesign-workbench is released under the MIT License. See
[`LICENSE`](LICENSE).
