# Programfile Refactor Plan

## Current State

The current toolkit contains three independent Tkinter GUIs:

1. `basic/gui.py`: single motif plus one flanking region.
2. `Target_xbp_Target/gui.py`: left motif, gap range, right motif.
3. `Target_xbp_Y_zbp_Target/gui.py`: Y sequence with left and right motif search windows.

All three GUIs repeat the same general pipeline:

```text
load genome/target/mask
extract candidate queries
search off-targets with BLAST or exact k-mer index
score and filter
sort and export
```

They differ mainly in how the structural pattern is defined. The current implementation puts pattern-specific fields directly into each `gui.py`, and the pipeline is controlled by tabs and buttons. This works, but it mixes design definition, execution, and result review in one form-oriented interface.

## Refactor Direction

The new interface should center on candidate results instead of command steps:

```text
describe pattern -> run once -> review/filter candidates -> export selected rows
```

The three existing tools become three pattern definitions that share one execution pipeline, one result table, and one detail/export panel.

## Planned Stages

### Stage 1: Core Pattern Model

- Add a small declarative pattern model under `shared/design/pattern_spec.py`.
- Model the three structures:
  - `SINGLE_MOTIF_FLANK`
  - `MOTIF_GAP_MOTIF`
  - `Y_CENTERED_MOTIFS`
- Add validation for motif text, integer ranges, and side values.
- Add a text preview method for showing the structural formula.
- Add unit tests.

Status: done.

### Stage 2: Pattern Runner Adapter

- Add `shared/design/pattern_runner.py`.
- Convert a validated `PatternSpec` into the existing extraction command for each mode.
- Return a common candidate record structure with the fields shared by all three modes.
- Keep the existing scripts as the execution backend.

Status: done for command construction, extraction output reading, and pipeline execution.

### Stage 3: Result-Centric GUI

- Add a new `designer_workbench.py` at the repository root.
- Use one window with:
  - top mode selector
  - left pattern editor
  - center structural preview and candidate table
  - right candidate detail and export panel
- Keep advanced scoring and filter settings in collapsible sections.
- Use `PatternRunner` for execution.

Status: initial workbench scaffold added. It includes mode switching, pattern preview, pipeline settings, run log, extracted candidate table, and CSV export.

### Stage 4: Selection-Based Export

- Replace directory-wide output assumptions with selected-row export.
- Support generating FASTA, BED, TSV, XLSX, unique guides, and library input from selected candidates.
- Keep compatibility with existing scripts until the new path is verified.

Status: selected-row export is implemented for CSV, TSV, FASTA, BED, XLSX, unique guides, and library input TSV. The new workbench is also available from the unified launcher.

### Stage 5: Cleanup and Verification

- Run existing tests.
- Add integration tests for each pattern mode.
- Remove or deprecate duplicated GUI code only after the new workbench covers the same flows.

Status: the local web UI now uses the new mode/pattern/candidate-table layout and exposes a candidate rows endpoint. The old desktop GUI entry files have been removed while preserving the extraction/search/scoring scripts used by the new workbench. Targeted tests pass; the full discovery run remains slow and can exceed the current timeout.
