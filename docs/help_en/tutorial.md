# Tutorial: a first run on the bundled sample data

This tutorial takes you from an empty installation to a finished result table
using the sample data committed in the repository. It follows the same run
twice: first in the web workbench, then from the command line. Every step lists
what you should see, and the numbers quoted here come from the reference run
copied into `sample_output/`, so you can check each of them against a real file.

The run takes seconds to a few minutes, depending on how fast the disk is (the
off-target search re-reads the genome once per candidate); the files it
produces are listed in Section 5.

## 0. What the run will do

Design guides inside a 200 kb target region cut from a 5 Mb synthetic genome,
with the SpCas9 pattern: an `NGG` PAM with a 20 nt target on the downstream
side, at most 3 mismatches, GC between 40% and 70%. The off-target search then
runs over the whole genome. The batch specification is
`sample_data/demo_batch.json`:

```json
{
  "batch_label": "sample-batch",
  "shared": {
    "genome_fasta": "sample_data/demo_genome.fa",
    "nuclease": "cas9",
    "pam_mode": "custom",
    "engine": "auto",
    "index_path": "",
    "max_mismatch": 3,
    "memory_mode": "auto",
    "gc_min": 40,
    "gc_max": 70
  },
  "scopes": [
    {"scope_id": "demo", "search_fasta": "sample_data/demo_target.fa", "mask_same_as_target": true}
  ],
  "patterns": [
    {"pattern_id": "NGG", "mode": "single_motif_flank",
     "overlay": {"motif": "NGG", "flank": 20, "side": "downstream"}}
  ],
  "groups": [{"group_id": "G1", "scope_ids": ["demo"], "pattern_ids": ["NGG"]}]
}
```

## 1. The sample data

| File | What it is |
| --- | --- |
| `sample_data/demo_genome.fa` | 5,000,000 bp in four contigs (`chr1`-`chr4`), uniform random A/C/G/T with no repeats, so any reported hit can be checked by hand. |
| `sample_data/demo_target.fa` | The first 200,000 bp of `chr1`; the scope guides are designed from. |
| `sample_data/demo_batch.json` | The one-unit batch specification above: scope `demo` (the 200 kb target region) with pattern `NGG`. |
| `sample_data/demo_guides.tsv` | 24 guides with a known exact and one-mismatch target, used by the engine benchmark. |

The data are synthetic and carry the repository's MIT licence. Nothing has to
be downloaded. `sample_data/README.md` documents them in more detail.

## 2. Start the software

### 2.1 Container

```bash
docker build -t targetdesign-workbench:0.1.0 .
docker run --rm -p 127.0.0.1:5000:5000 -v targetdesign-data:/data targetdesign-workbench:0.1.0
```

**Expected:** the build finishes and the run prints the web address. Open
<http://localhost:5000>. The image already contains Python, the native indexed
engine and the pre-flight checks, so no host installation is required.

### 2.2 From source

```bash
python -m venv .venv
. .venv/bin/activate               # Windows: .\.venv\Scripts\activate
pip install -r requirements.txt    # Windows: requirements-windows.txt
python webapp/app.py --host 127.0.0.1
```

**Expected:** the server prints its address and stays in the foreground:

```text
Serving on: http://127.0.0.1:5000
```

The default is port 5000 on host `0.0.0.0`; pass `--port` to change the port and
`--host 127.0.0.1` to keep the interface on the local machine.

## 3. Web walkthrough

Open <http://127.0.0.1:5000>. You should see the title
**TargetDesign-workbench**, a **Design Pattern** selector, the buttons
**Find Targets** and **Score & Off-target**, and a **Data prep / Models**
drawer button.

### Step 1 - point the workbench at the genome

Open the **Data prep / Models** drawer and fill in the **Genome / annotation**
group:

| Field | Value |
| --- | --- |
| Genome file (FASTA) | `sample_data/demo_genome.fa` |
| Annotation file (GTF/GFF3) | leave empty (the synthetic genome has no gene annotation) |
| Output directory | a directory you can write to, for example `output` |
| Existing Genome database path | leave empty |
| Index prefix / index output directory | leave empty (the search builds an index on demand) |

Then click **Build genome index**. **Expected:** the job builds a `.ggi` index
and, when it finishes, back-fills the Designer's **Index Prefix** (the hint
reads `Loaded: index_path`). Pre-building the index is optional: the search
builds the same index on demand if you skip this step.

> **What the "Prepare data" button is for.** It prepares or downloads a genome,
> extracts a **Target FASTA** (from a gene symbol, an ENSEMBL id or
> coordinates) and a **Mask FASTA**, and back-fills **Genome FASTA**,
> **Search FASTA** and **Mask FASTA**. It needs a **Search scope** to extract,
> and the synthetic demo genome carries no annotation, so that button cannot be
> used here: the demo designs over the whole genome instead. The next steps
> therefore set the Designer fields directly, which is exactly what the
> command-line run in Section 4 does.

### Step 2 - describe the pattern

In the Designer, set **Design Pattern** to **Single target design** and fill the
**Target TAM** column:

| Field | Value |
| --- | --- |
| System Preset | `SpCas9` |
| PAM/TAM Motif | `NGG` |
| Target Length | `20` |
| Target Position | `downstream` |
| Side Models | on-target `cropsr`, off-target `cfd` |

**Expected:** the **Structure Preview** prints
`[downstream flank 20 bp] + [NGG]`, and the run's nuclease becomes `cas9`.

### Step 3 - set the common inputs

In **Common Inputs**:

| Field | Value |
| --- | --- |
| Genome FASTA | `sample_data/demo_genome.fa` |
| Search FASTA | `sample_data/demo_target.fa` |
| Mask FASTA | `sample_data/demo_target.fa` |
| Annotation GFF3 | leave empty |
| Result Label | `sample-batch` (optional; a blank label is derived for you) |

> **Why are there two different FASTA files?** **Search FASTA** is the region
> guides are designed from; the off-target search itself runs over
> **Genome FASTA**. Setting **Mask FASTA** to the same 200 kb file reproduces
> `demo_batch.json`, whose scope sets `mask_same_as_target: true`: hits inside
> the target region are excluded from off-target counting (which is why
> `valid_matches` is `0` for the candidates that sit in it), while hits
> elsewhere in the genome are counted and land in `top_offtargets.tsv`.
> Masking the *whole* genome instead leaves that table with nothing but its
> header, and clearing **Mask FASTA** additionally counts the on-target loci as
> off-targets.

### Step 4 - run settings

Open **Run Settings** and check:

| Field | Value |
| --- | --- |
| Engine | `auto` |
| Max Mismatch | `3` |
| Max Bulge | leave empty (no bulge budget) |
| PAM Mode | `Custom PAM` (the motif is typed explicitly) |
| GC Min / GC Max | `40` / `70` |
| Memory Limit | `auto` |

**Expected:** no validation error appears and the action buttons are enabled.

### Step 5 - find the candidates

Click **Find Targets**. **Expected:** the Run Log reports the extraction and the
result table fills with candidates:

```text
motif (+) regex: [ACGT]GG
motif (-) regex: CC[ACGT]
Loaded 1 input sequences
Extracted 25024 positions merged into 24211 unique sequences
```

So the pattern finds **24,211 distinct candidate sequences** covering
**25,024 motif positions** in the target region.

### Step 6 - score and search off-targets

Click **Score & Off-target**. **Expected:** the progress bar advances through
the search and then the scoring, the Run Log ends with the scoring summary and
the warning of Section 5, and the Results Table is ranked. The reference run
copied into `sample_output/` (find, search and score) takes **16 seconds** on a
local disk; from a network share expect much longer, because the search
re-reads the genome once per candidate.

### Step 7 - read the table

The **Results Table** now holds the ranked candidates. The first data row of the
reference run is (columns shown abbreviated with `...`):

```text
rank  nuclease  off_target_specificity  legacy_total_score  pos_id       seq_id  strand  motif_pos  qid     query_seq                 total_matches  valid_matches  sum_mismatch  GC-content  GC-hint  Self-complementarity  Self-comp-hint  calibration_status     bulge_score_method  ...  on_target_score_cropsr  off_target_specificity_cfd  MM0  MM1  MM2  MM3
1     cas9      1.000000                0.00                chr1_plus_0  chr1    plus    3          uniq_0  AGGCGAGCGCAAGGTTATACGCT   1              0              0             56.52       pass     4                     pass            calibrated_reference   not_applicable      ...  0.8572463768115942      1.0                         0    0    0    0
```

Reading it: the candidate starts at `chr1` position `3` on the `plus` strand,
its 23 nt query window is the `NGG` motif (`AGG`) followed by the 20 nt target,
GC is `56.52%` (`pass`), the predicted on-target activity is `0.857` and the
off-target specificity is `1.0`. `valid_matches` is `0` because the mask of
Step 3 removes every hit. Section 6.2 of `index.md` explains every column, and
`sample_output/` holds the first rows of this table in full.

### Step 8 - export

Choose a **Table** view (**Full** or **Concise**), a **Format** (`CSV`, `TSV`,
`FASTA`, `BED`, `XLSX`, `unique_guides` or `library`), optionally a file name,
and click **Export Selected** (or **Export All**). **Expected:** the file is
written next to the job and offered as a download. The full table can be
exported as CSV, TSV or XLSX; the remaining formats reinterpret candidate rows
and are therefore offered for the concise view.

## 4. The same run from the command line

The command-line entry point takes the specification directly, so there is
nothing to type into a form.

### 4.1 Validate the plan

```bash
python tools/batch_run.py --spec sample_data/demo_batch.json --dry-run
```

**Expected output** (the unit table is tab-separated):

```text
RUN_DIR: <repo>/output/<YYYYMMDD>-<ID> (id assigned when the run starts)
unit_id   scope_id   pattern_id
demo__NGG  demo      NGG
```

`--dry-run` validates the specification and prints the units without running
anything. Use it to confirm that a batch expands to the units you expect.

### 4.2 Run it

```bash
python tools/batch_run.py --spec sample_data/demo_batch.json
```

**Expected:** the run allocates `output/<date>-<id>/`, prints its id, and runs
the single unit `demo__NGG` to completion:

```text
RUN_ID: 20261008-0114
RUN_DIR: <repo>/output/20261008-0114
...
RUN_LOG: <repo>/output/20261008-0114/run.log
```

The `<id>` is assigned when the run starts, so your directory name will differ
from the one above; `sample_output/` records the reference run used on this
page. The exit code is `0`. The search and scoring are the same code the web
interface uses, so `query_scores_sorted.tsv` is identical to what the interface
showed in Step 7.

Useful flags: `--label NAME` to name the run, `--no-resume` to re-run units that
already finished, `--only demo,NGG` to run a subset, and `--run-id ID` to
re-enter an existing run folder.

## 5. What the run produces

Reference numbers for exactly this command (`output/20261008-0114/`, one unit,
no resume):

| Quantity | Value |
| --- | --- |
| Extracted candidates (`extracted_seqs.tsv`) | 24,211 unique sequences covering 25,024 positions |
| Scored rows (`query_scores_sorted.tsv`) | 25,024 |
| Wall clock | 16 s on a local disk |
| Manifest status | `ok`, return code 0 |
| Output size | about 54 MB |
| Warnings | 1: `Warning: no mm=0 flanking sequence found for chr1; skipped` |

**The single warning is expected here.** The scope covers only `chr1`, and the
mask of Step 3 removes the zero-mismatch hits inside it, so no off-target flank
file is written for that contig. With the mask cleared the warning disappears.
`top_offtargets.tsv` is *not* affected: this run reports **180** ranked
off-target rows (10 at two mismatches and 170 at three) spread over all four
contigs, which is what makes the sample output usable as a worked example.

The batch writes:

```text
output/20261008-0114/
  manifest.tsv                  one row per unit: status, return code, timings
  run.json                      run identity and source specification
  run.log                       full streamed log
  batch.json                    the expanded specification that ran
  summary/batch_scores.tsv      every unit's rows, with batch/unit/scope/pattern ids
  demo__NGG/
    extracted_seqs.tsv          the candidates
    query_scores_sorted.tsv     the deliverable table
    top_offtargets.tsv          ranked off-target loci
    query_scores.bed            candidate intervals
    blast_results.tsv           raw search hits (intermediate)
    genome_index/               the built .ggi index and its metadata
```

The scope is already restricted to a 200 kb region; to go faster still, narrow
it with a BED region file, lower **Max Mismatch**, or tighten **GC Min** /
**GC Max**.

## 6. The sample output files

`sample_output/` holds trimmed copies of the files above so you can check these
numbers without running anything:

| File | What it is |
| --- | --- |
| `query_scores_sorted.head20.tsv` | Header plus the first 20 rows of the deliverable table. |
| `extracted_seqs.head20.tsv` | Header plus the first 20 extracted candidates. |
| `summary.batch_scores.head20.tsv` | Header plus the first 20 rows of the combined batch table. |
| `top_offtargets.tsv` | The off-target table in full: all 180 ranked rows. |
| `manifest.tsv` | The batch manifest in full. |
| `run.json` | The run identity file in full. |

Only rows were removed: no value was recalculated or edited.
`sample_output/README.md` records the exact truncation and the run the copies
come from.

## 7. Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| `Extracted 0 positions` and an empty result table | The motif does not occur in the scope, or **Search FASTA** is not the file you think. Check the `motif (+)/(-) regex:` lines in the Run Log. |
| A very large `MM0` | Repeats or low-complexity sequence, `Require PAM` turned off, or a search result file left over from an earlier run. |
| `top_offtargets.tsv` empty | No hit survived masking. A mask that covers the whole search scope excludes everything; see the note in Step 3. |
| `no mm=0 flanking sequence found for chrN; skipped` | Normal when the mask removes every zero-mismatch hit of a contig; see Section 5. |
| The search is very slow | The cost scales with the number of candidates and the mismatch budget; narrow the scope, lower **Max Mismatch**, or run on a multi-core host. |
| `engine not available` or a fallback message | The requested engine is not usable here (for example `blast` without BLAST+ installed, or a missing native engine). `auto` selects a working engine; see the engine documentation under `docs/`. |
