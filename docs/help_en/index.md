# TargetDesign-workbench - help page

This page explains what the software does, how to install and start it, what
every field of the design form means, and how to read the result files. For a
worked example with expected output at every step, see
[`tutorial.md`](tutorial.md); the real output files it quotes are under
[`sample_output/`](sample_output/).

## 1. What the software does

TargetDesign-workbench designs CRISPR guides from a **motif-first** description.
Instead of searching a fixed PAM, you describe the sequence layout you want and
the tool enumerates every genomic site that fits it:

1. **Define a pattern.** A pattern is a set of PAM/TAM motifs plus target
   lengths and relative positions (Section 5.2).
2. **Extract candidates.** Every motif match in the search scope is turned into
   a candidate window.
3. **Off-target search.** All candidate windows are searched against the genome
   with a mismatch (and optionally bulge) budget, using one of several engines.
4. **Score, filter and rank.** Published on-target and off-target models (plus
   published rule sets) score every candidate; GC, self-complementarity and
   annotation hints are added; rows are ranked by the specificity of the
   off-target set.
5. **Read and export.** The candidate table is shown in the web interface and
   can be exported as TSV/CSV/FASTA/BED/XLSX, as a unique-guide table, or as a
   library.

Supported effectors are SpCas9, Cas12a/LbCpf1, Cas12b/AapCas12b, Cas13 and
TnpB/omegaRNA, plus a `custom` mode in which nothing is assumed.

## 2. Installation

### 2.1 Container (recommended for reviewers)

The container image **is** the distributed stand-alone application: it starts
the web workbench on port 5000 and bundles the native C++20 indexed off-target
engine, so no Python or third-party installation is needed on the host.

Requirements: Docker Engine 24 or newer (or Podman with the equivalent
`build`/`run` commands) and about 4 GB of free disk space.

```bash
docker build -t targetdesign-workbench:0.2.0 .
docker run --rm -p 127.0.0.1:5000:5000 -v targetdesign-data:/data targetdesign-workbench:0.2.0
```

Then open <http://localhost:5000>. The port is published on the loopback
interface only; publish `-p 5000:5000` instead if other machines should reach
it. With Compose, `docker compose up --build` uses the same defaults and keeps
run data in `./data`.

Genomes, indexes and exported runs live in the volume mounted at `/data` (the
`TARGETDESIGN_DATA` environment variable), so a rebuilt image never discards a
genome index. The default image target is `core`; `--target full` adds
ViennaRNA, Cas-OFFinder, R + NuPoP and a CPU PyTorch build.

Full build details, including the two image targets and what is deliberately
not shipped inside the image (model weights, third-party trees, genomes), are
in [`../CONTAINER.md`](../CONTAINER.md).

### 2.2 From source

The source tree needs Python 3.13 and the pinned requirements. NCBI BLAST+
(`blastn`, `makeblastdb`) is optional and only needed for the `blast` engine.

Windows:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements-windows.txt
```

Linux/macOS:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

Third-party model weights are not redistributed with the software; runs that
use published rule sets need no weights. See [`../MODELS.md`](../MODELS.md) for
how to obtain them and where to place them.

## 3. Starting the workbench

### 3.1 Local web interface

```bash
python webapp/app.py                 # serves on 0.0.0.0:5000
python webapp/app.py --host 127.0.0.1   # loopback only
python webapp/app.py --port 8080     # different port
```

The page answers on <http://127.0.0.1:5000>. Long steps (index builds, searches,
batches) run as queued background jobs; only one heavy job runs at a time and
progress is streamed to the Run Log panel.

The same pipeline can be driven from the desktop workbench
(`python designer_workbench.py`). The web interface and the desktop workbench
share the `shared/` modules, so their results are identical.

### 3.2 Command line

```bash
python tools/batch_run.py --spec my_batch.json          # run a batch
python tools/batch_run.py --spec my_batch.json --dry-run   # validate and print the plan
```

A batch combines *scopes* (search regions) with *patterns* (design layouts) and
finishes with a manifest and a combined score table. Useful flags are
`--label`, `--no-resume`, `--only SCOPE,PATTERN` and `--run-id`. The batch
format is specified in [`../BATCH.md`](../BATCH.md).

### 3.3 Trying the bundled sample data

The repository ships a synthetic data set that needs no download:

```bash
python tools/batch_run.py --spec sample_data/demo_batch.json --dry-run
python tools/batch_run.py --spec sample_data/demo_batch.json
```

The equivalent web run is described step by step in
[`tutorial.md`](tutorial.md). `sample_data/README.md` documents the data and
their provenance.

## 4. The interface at a glance

| Area | What it is for |
| --- | --- |
| **Data prep / Models** (drawer) | Download a genome and annotation, extract a target or mask region, build a BLAST database or a genome index, and inspect model availability. A successful job back-fills empty Designer inputs; values you typed yourself are never overwritten. |
| **Design Pattern** (top bar) | Chooses the layout to design: single target, Pattern A or Pattern B. |
| **Find Targets** | Extracts the candidate windows of the current pattern from the search scope. |
| **Score & Off-target** | Runs the off-target search and scores, filters and ranks the candidates. |
| **Structure Preview** | Human-readable summary of the current pattern, e.g. `[downstream flank 20 bp] + [NGG]`. |
| **Run Settings** | Engine, search budget, PAM mode, GC hints and memory limits (Section 5.9). |
| **Run Log** | Streamed output of the current or last job. |
| **Results Table** | The candidate table with the export controls. |
| **Results / Output** | Past jobs, their logs, and a file browser for an output directory. |

## 5. The Designer form, field by field

### 5.1 Common Inputs

| Field | Meaning |
| --- | --- |
| **Search FASTA** | The sequence(s) to design against: the sequence whose sites are turned into candidates. Use this for a single gene or an amplicon. |
| **BED Regions** | Alternative scope input. Instead of whole FASTA records, only the intervals of a BED file are searched. |
| **Genome FASTA** | The genome used for the off-target search. It may be a different file from the search scope (design in a gene, search the whole genome). A `.fna.gz` path is decompressed next to the file. |
| **Mask FASTA** | Optional. Regions present in this file are excluded from off-target counting and from the off-target flank extraction. Get this wrong and the "off-target" columns become meaningless: if the mask covers the whole search scope, every hit is excluded (see the note in [`tutorial.md`](tutorial.md)). A `.fna.gz` path is decompressed next to the file, like the genome. |
| **BLAST DB Prefix** | Optional pre-built BLAST database prefix (`<prefix>.nin`/`.nsq` plus the `.source.json` sidecar) for the `blast` engine. Empty means it is built on demand. |
| **Annotation GFF3** | Optional GFF/GTF annotation. It adds the `Annotation`, `Nearest-TSS`, `Isoforms` and `Downstream-ATG` columns to the score table, so candidates can be judged by where they sit. Without it those columns are omitted. |
| **Result Label** | Name of this run. Blank derives a name from system and target (`<system>-<target>`), which is also the prefix of the delivered files. |

### 5.2 Design Pattern and the pattern form

Three layouts are available; the form to the right of the pattern selector
changes with the choice.

| Pattern | Layout | Typical use |
| --- | --- | --- |
| **Single target design** (`single_motif_flank`) | `[flank][motif]` | One guide next to one PAM/TAM. This is the classic single-guide design and the pattern used by the tutorial. |
| **Paired-target design Pattern A** (`motif_gap_motif`) | `[flank][motif] ... gap ... [motif][flank]` | Two guides flanking a short gap, so both cut the same locus. Ranked as pairs by PairRank. |
| **Paired-target design Pattern B** (`y_centered_motifs`) | left motif, a mandatory middle motif, right motif, each with its own distance window | Two guides surrounding a required central motif. |

For each target side the form offers:

| Field | Meaning |
| --- | --- |
| **System Preset** | The effector whose recommended values fill the side (Section 5.3). |
| **PAM/TAM Motif** | The motif to anchor on, in IUPAC notation (Section 5.4). |
| **Target Length** | The length of the target sequence taken from the window (Section 5.5). |
| **Target Position** | Which side of the motif the target lies on (Section 5.6). |
| **Require PAM** | Paired patterns only. Requires the PAM/TAM to be present during scoring, not just during extraction. |
| **Use for Run** | Which side of a paired pattern drives the pipeline when one side is being edited. |
| **Side Models** | On-target and off-target models for that side (Section 5.8). |

Pattern A additionally has **Minimum Distance** and **Maximum Distance** (gap
between the two motifs, measured to the left PAM/TAM), and Pattern B has a
**Middle Motif** plus one distance pair per side. Paired patterns also require
the PairRank policy fields under Run Settings; a paired run stops instead of
quietly falling back to a different ranking when a threshold is missing.

### 5.3 System Preset (nuclease)

The preset fills recommended values for one effector. It never locks the
fields: you can edit any value afterwards.

| Preset | Spacer | PAM/TAM | PAM side | Notes |
| --- | --- | --- | --- | --- |
| `SpCas9` | 20 nt | `NGG` | 3' | PAM-proximal seed; the default preset. |
| `Cas12a / LbCpf1` | 24 nt | `TTTN` | 5' | Seed positions 1-6. |
| `Cas12b / AapCas12b` | 20 nt | `TTN` | 5' | Mismatches broadly tolerated. |
| `Cas13 (CHOPCHOP)` | 27 nt | `H` | 5' | RNA target; 5' non-G flanking site. |
| `TnpB / omegaRNA` | - | - | - | No TAM is assumed by default; pick the ISDra2 subtype to require the classic 5' `TTGAT` TAM. |
| `Custom / free input` | - | - | - | No system rules are applied. |

The preset also decides which scoring rule set is used and which on-target and
off-target models are offered for that side.

### 5.4 PAM/TAM motif and IUPAC notation

Motifs are written as a short DNA string in IUPAC notation. Every letter is one
position, and a position may stand for several bases:

| Code | Bases | Code | Bases |
| --- | --- | --- | --- |
| `A` | A | `M` | A or C |
| `C` | C | `K` | G or T |
| `G` | G | `R` | A or G |
| `T` / `U` | T (U is read as T) | `Y` | C or T |
| `W` | A or T | `S` | G or C |
| `B` | C, G or T | `D` | A, G or T |
| `H` | A, C or T | `V` | A, C or G |
| `N` | any base | | |

So `NGG` matches all four SpCas9 PAMs (`AGG`, `CGG`, `GGG`, `TGG`), `NRG`
matches `NGG` **and** `NAG` (the GuideScan2-compatible set), and `TTTN` matches
the four Cas12a PAMs. The complementary strand is searched automatically, so
you write each motif once in its plus-strand orientation.

The **PAM Mode** setting under Run Settings is a convenience that fills this
motif for Cas9: `Strict NGG` (search only `NGG`), `GuideScan2 NRG (NGG + NAG)`
(search `NRG`), or `Custom PAM` (use the motif exactly as typed). The mode also
selects which two PAM-proximal bases the CFD weights are taken from, so `NAG`
is never scored with `NGG` weights.

### 5.5 Target Length

The number of bases taken next to the motif to form the guide. The default is
the effector's spacer length (20 nt for SpCas9). The extracted query window
includes the motif as well: for SpCas9 with a downstream target, the window is
motif (3 nt) + target (20 nt) = 23 nt, which is the `query_seq` shown in the
results.

### 5.6 Target Position

`downstream` or `upstream` - which side of the motif the target occupies in the
extracted window. Together with the motif it defines the layout that the
Structure Preview prints, e.g. `[downstream flank 20 bp] + [NGG]`. Both strands
are searched, so the same setting also produces the reverse-complement layout
on the minus strand.

### 5.7 Paired-pattern fields

| Field | Meaning |
| --- | --- |
| **Require PAM** | Requires the motif to be present when a hit is scored. Leave it on unless you deliberately want PAM-less similar sites counted. |
| **Minimum / Maximum Distance** | The allowed distance between the two motifs (Pattern A), or between the middle motif and each side (Pattern B). Both bounds are inclusive and are written as `min_gap` / `max_gap` in the batch spec. |
| **Middle Motif** (Pattern B) | A short motif that must be present in the gap between the two targets with no mismatch. |

### 5.8 Side Models

Each side selects one or more on-target and off-target models. Defaults follow
the effectors: SpCas9 → on-target `cropsr`, off-target `cfd`; Cas12a/Cas12b →
rules; Cas13 → RNA rules; TnpB → `omega`/`identity`.

Every selected model writes its own column,
`on_target_score_<model>` / `off_target_specificity_<model>`. The first
selected off-target model also drives the plain `off_target_specificity`
column and therefore the row order of a single-target table; the remaining
models add columns without changing the order.

### 5.9 Run Settings

| Field | Meaning and default |
| --- | --- |
| **Engine** | How hits are found: `exact` (in-memory), `indexed` (the local `.ggi` index, native C++ engine when available), `blast` (NCBI BLAST+), `gggenome` (remote), or `auto` (default; picks a working engine and falls back if one is unavailable). |
| **Max Mismatch** | The mismatch budget, `0`-`4` (default `4`). It sets both the search budget and how many mismatch-bucket columns are written (`MM0` ... `MMn`, see Section 6.2). |
| **Max Bulge** | Bulge budget: empty (engine default, no bulge scoring), `0`, or `1`. With `0` or `1`, bulge hits are searched and scored with the conservative, explicitly uncalibrated penalty. |
| **PAM Mode** | `Strict NGG`, `GuideScan2 NRG (NGG + NAG)` or `Custom PAM` (Section 5.4). |
| **Seed Length** | Informational only: the engine uses the index k-mer length as the seed length. Changing this value does not change the search. |
| **Index Prefix** | Path prefix of a pre-built genome index (`<prefix>.ggi` + `<prefix>.json`). Supplying it re-uses that index instead of building one; blank builds an index under the run directory. |
| **GC Min / GC Max** | Bounds of the GC hint, default 40 and 70 percent. A candidate below `GC Min` is hinted `low` and above `GC Max` `high`; both are hints only unless Hard Filter is on. |
| **Genome Build** | Free-text label recorded with the run (for example `GRCh38`). Purely descriptive. |
| **Hard Filter** | When on, candidates that fail the GC or self-complementarity hint are dropped instead of merely flagged. |
| **Memory Limit** | `auto` (derive the limit from the machine), `custom` (use **Custom MiB**) or `unlimited`. The limit is applied to the off-target search step. |
| **Custom MiB** | The memory limit used when Memory Limit is `custom`, default 32768 MiB. |
| **Search timeout (s)** | Optional wall-clock limit for the off-target search step. |

## 6. Interpreting the results

### 6.1 Result files

A single-target run writes, per run unit:

| File | Content |
| --- | --- |
| `extracted_seqs.tsv` | Candidates extracted from the scope: `qid`, `sequence`, `positions`. One row per unique sequence; the first line is a `# motif=... flanking_len=... side=...` comment. |
| `query_scores_sorted.tsv` | The deliverable table: one row per candidate position, ranked (Section 6.2). |
| `top_offtargets.tsv` | The ranked off-target loci behind the score (Section 6.3). |
| `query_scores.bed` | The candidate intervals as BED. |
| `unique_guides.tsv` | The same columns de-duplicated by guide, with `position_count` (written when unique-guide output is requested). |
| `blast_results.tsv` | The raw search hits (intermediate; large). |

A batch adds `manifest.tsv`, `run.json`, `run.log`, `batch.json` and
`summary/batch_scores.tsv` (Section 6.4). Columns that are empty in every row
are dropped before writing, so the exact set of columns depends on the models
and options of the run - always read the header rather than assuming a fixed
layout.

### 6.2 `query_scores_sorted.tsv`, column by column

The columns below are the contract; those in the first group are always
present, the rest appear when the corresponding option or model is used.

| Column | Meaning |
| --- | --- |
| `rank` | Row order of this table: single-target and unique-guide tables are sorted by `off_target_specificity` descending. |
| `nuclease` | The effector used for scoring (`cas9`, `cas12a`, `cas12b`, `cas13`, `tnpb`). |
| `pos_id`, `seq_id`, `strand`, `motif_pos` | Where the candidate came from: an identifier for the occurrence, the sequence record, the strand, and the 0-based start of the motif. |
| `qid`, `query_seq` | The candidate identifier and the extracted query window (motif plus target, Section 5.5). |
| `total_matches` | Hits returned by the search backend for this query. |
| `valid_matches` | Hits that survive masking and repeat filtering and are used for scoring. |
| `sum_mismatch` | Total mismatches over the valid hits. |
| `MM0` ... `MMn` | Mismatch buckets. `MM0` counts hits with zero mismatches, and the last column is the merged `>= n` bucket where `n` is **Max Mismatch**. The number of columns follows the budget: budget 0 writes only `MM0`, budget 2 writes `MM0`-`MM2`. `MM0` counts only hits that cover the whole query, so a gene with genuine repeat structure shows a high `MM0`; a large `MM0` with a single-copy target is a signal to check the PAM setting and the mask. |
| `GC-content`, `GC-hint` | GC percentage of the query and the `low` / `pass` / `high` hint from **GC Min/Max**. |
| `Self-complementarity`, `Self-comp-hint` | Length of the longest reverse-complement stretch inside the query and the `pass` / `warn` hint. |
| `off_target_specificity` | The main score: higher is more specific, `1.0` means no additional similar site beyond the intended one. It is aggregated as `1 / (1 + sum(model scores))` with the perfect-match contribution removed. |
| `legacy_total_score` | The "matching pressure" score used before `off_target_specificity` existed, kept for continuity: `10*MM0 + 1*(MM0+MM1) + 0.1*(MM0+MM1+MM2) + 0.01*(...)`. Every run writes it. It is not a 0-1 score, it must not be compared with `off_target_specificity`, and this tool does not rank by it. |
| `off_target_specificity_<model>` | The same quantity for each selected off-target model (for example `off_target_specificity_cfd`). |
| `on_target_score_<model>` | The predicted on-target activity of each selected on-target model (for example `on_target_score_cropsr`). Not a column of its own: a model only ever writes a suffixed column. |
| `calibration_status` | How the score was calibrated, not how it was validated (Section 6.5). |
| `bulge_score_method` | `conservative_bulge_v1` when bulge hits were scored, `not_applicable` when the run used no bulge budget or found none. |
| `input_offtargets`, `substitution_offtargets` | Sites entering scoring, and how many of them are substitution-type. |
| `bulge_hits`, `scored_bulge_hits`, `unscored_bulge_hits` | Bulge hits; always `bulge_hits = scored + unscored`. |
| `bulge_risk_sum` | The conservative sum of bulge risk folded into the specificity. |
| `Annotation`, `Nearest-TSS`, `Isoforms`, `Downstream-ATG` | Annotation columns, present only when an annotation file was given. |
| `left_*`, `right_*` | Paired patterns score the two sides independently and write them side by side; Pattern A adds the PairRank columns described in [`../OUTPUTS.md`](../OUTPUTS.md). |

### 6.3 `top_offtargets.tsv`

Columns: `qid`, `position_count`, `rank`, `target`, `start`, `mismatch`,
`annotation`. One row per ranked off-target locus: which candidate it belongs
to, that candidate's occurrence count, its internal rank, the sequence record,
the 0-based start, the mismatch count and the overlapping annotation if any.
This is the table to spot-check: a good candidate has few rows, at high
mismatch, far from a TSS. In a run where the mask removes every hit the file
contains only its header, which means "no site survived masking", not "no
off-target was found" (see the note in [`tutorial.md`](tutorial.md)).

### 6.4 Batch files

| File | Content |
| --- | --- |
| `manifest.tsv` | One row per run unit: `unit_id`, `scope_id`, `pattern_id`, `status`, `returncode`, `started`, `finished`, `unit_dir`, `main_table`, `message`. `status` is `ok` for a unit that finished; a non-zero `returncode` and the message explain failures. |
| `summary/batch_scores.tsv` | Every unit's candidate table concatenated, with `batch_id`, `unit_id`, `scope_id` and `pattern_id` prepended so rows stay attributable. |
| `run.json` | Run identity: `run_id`, `day`, `label`, `batch_label`, `created`, `unit_count`, `resume`, `source`. |
| `run.log` | The full streamed log, including per-unit warnings. |
| `batch.json` | The expanded specification that was actually executed (including the resolved unit list). |

Runs land under `output/<date>-<id>/`; the folder name is the "task code" you
can quote to re-open a run in the web interface.

### 6.5 What the calibration labels mean, and their limits

`calibration_status` records **how a score was calibrated**, not how well it
was validated experimentally:

| Value | Meaning |
| --- | --- |
| `calibrated_reference` | Substitution-only hits scored by a published reference model (for example CFD for SpCas9). This is the strongest label. |
| `uncalibrated` | Everything else: scores from generic sequence-composition heuristics, the Cas12a/Cas12b/TnpB paths, and any run in which bulge hits were scored. |

Related labels to watch for:

- `bulge_score_method` = `conservative_bulge_v1` marks bulge hits. They are
  folded into the specificity with a deliberately conservative penalty and are
  always labelled `uncalibrated`.
- Every model score is a **relative** ranking aid. It is not an absolute
  editing efficiency, and the interface and this page never claim otherwise.
- A paired run additionally carries `pair_rank_status` (`pass` /
  `conditional` / `rejected`) and the PairRank policy fields. The
  `experiment_calibrated` PairRank mode is specified but not implemented in the
  current pipeline; its fields are a target contract, not produced output.

### 6.6 How to choose candidates

1. Check the run used the effector and models you intended; models you did not
   select produce no columns.
2. Prefer candidates whose `off_target_specificity` is close to `1`, and
   compare `off_target_specificity_<model>` where several models were run.
3. Inspect `MM0`: with PAM filtering on it is normally small. A large `MM0`
   points at repeats, a wrong PAM setting, or a stale search result.
4. Among candidates with similar specificity, compare `on_target_score_<model>`.
5. Open `top_offtargets.tsv` for the candidates you are about to pick and check
   how many loci, at what mismatch, and where they fall.
6. For paired patterns, start from `pair_rank_status`, then `pair_rank`,
   `pair_activity_tier`, and finally the burden and risk columns.

## 7. Licence and feedback

MIT licence, see [`LICENSE`](../../LICENSE). Free access for non-commercial
use. Bug reports and questions: <https://github.com/LNT-666/TargetDesign-workbench/issues>.

Further reference material: [`../OUTPUTS.md`](../OUTPUTS.md) (result contract),
[`../SCORING_GUIDE.md`](../SCORING_GUIDE.md) (scoring models and aggregation),
[`../BATCH.md`](../BATCH.md) (batch specification), [`../WEBAPP.md`](../WEBAPP.md)
and [`../GUI.md`](../GUI.md) (interface details; Chinese).
