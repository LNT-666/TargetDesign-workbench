# Figure captions (main text and Supplementary)

English captions for the six main-text figures and the one Supplementary figure of
`manuscript-v1` (round 1). Numbering is fixed by `docs/FIGURE_TABLE_PLAN.md`: the
capability matrix is a main-text figure (Figure 3), and the case-site figure is
Supplementary Figure S1.

Each entry gives the caption text, then the artefact the panel is drawn from
(`Source`) and the sample size or scope that the caption is allowed to claim
(`Scope`). Bracketed `file:line` tokens are provenance markers for the drafting
stage, not part of the caption text. Figure 3 must state that `unknown` is not
`no`; no caption asserts a result that was not measured.

## Figure 1

**Architecture and data flow of CRISPR-Motif Workbench.** A design request is
stated as a set of orthogonal parameters over user-supplied IUPAC motifs; the
specification layer validates the request and emits the complete solution set for
the chosen layout; the search layer evaluates each candidate against the genome
with the native indexed engine; the scoring layer attaches model scores with an
explicit calibration state; the export layer writes the result tables and the
sequence sidecar.

- Content: the five stages of the pipeline and the artefacts exchanged between them.
- Source: `docs/PAPER_METHODS_DRAFT.md` (sections 2.1-2.3, 2.8) and the stage
  entry points named there.
- Scope: schematic. No measurement is plotted, so no sample size applies.

## Figure 2

**The three supported layout kinds and the four strand-orientation combinations of
a paired layout.** From top to bottom: a single motif with its flanking target; two
motifs separated by a single gap interval; and a three-element layout in which a
sequence-constrained middle element `Y` is flanked by two independent distance
intervals. The lower panels show how the left and right anchors are matched on
either genomic strand, giving the four combinations `++`, `+-`, `-+` and `--`, and
how each candidate row records the two per-side orientations and the two 0-based
half-open target intervals.

- Content: layout semantics, the distance-interval notation, and the strand
  enumeration.
- Source: `docs/design_patterns_en.md` and
  `Target_xbp_Target/extract_complex_queries.py:103-108`.
- Scope: schematic. No measurement is plotted, so no sample size applies.

## Figure 3

**Capability matrix of 15 published CRISPR guide-design tools and this work.** The
matrix has 16 data rows (the 15 published tools plus this work) and 10 columns
[docs/expressiveness_matrix.tsv:1-17]. Six of the columns are capability columns:
custom PAM/TAM input, custom target length, custom orientation, a middle-element
constraint, enumeration of all occurrences, and independent per-side settings for a
pair; the remaining columns give the tool, the year, the input model and an evidence
cell. A capability cell is `yes`, `partial`, `no` or `unknown`. This work is `yes`
on all six capability columns; among the published tools, four are `partial` on the
middle-element constraint and two are `partial` on independent per-side settings,
while none is `yes` on either column
[docs/expressiveness_matrix.tsv:3,8,9,15]. Nineteen published-tool cells are
`unknown`, which records that no public documentation was located for the cell; it
is not a statement that the tool does not support the capability, and those cells
are to be re-checked as documentation changes
[docs/expressiveness_matrix.tsv:9-17].

- Content: per-tool capability profile, with the evidence cell naming the DOI,
  official documentation page or repository location behind each row.
- Source: `docs/expressiveness_matrix.tsv` and `docs/EXPRESSIVENESS_MATRIX.md`.
- Scope: 15 published tools plus this work, 6 capability columns, 19 `unknown`
  cells. Capability values were read from each tool's paper, official documentation
  or public repository; no competitor tool was executed and no competitor
  dependency was installed.

## Figure 4

**Memory layout of the persistent index.** The index is a fixed header, a contig
table, an offsets table with one entry per k-mer plus a terminal entry, and a
positions table. The positions table stores 4-byte entries while the indexed genome
stays below 2^32 bases and 8-byte entries above that boundary, so the width follows
the genome rather than a fixed choice; the payload is mapped read-only and shared
between worker threads.

- Content: the two-layer layout, the offsets-to-positions indirection, and the
  place where the entry width changes.
- Source: `docs/PAPER_METHODS_DRAFT.md` (section 2.3),
  `native/offtarget_engine/include/offtarget/genome_index.hpp` and
  `docs/NATIVE_INDEXED_ENGINE_DESIGN.md`.
- Scope: annotated with one measured build per index size on the 1,000,000 bp
  fixture, namely 4524314 bytes at k = 8 and 12388602 bytes at k = 10, both with a
  4-byte position type [docs/seed_plan_sweep.json:index_builds[0],index_builds[1]].

## Figure 5

**Seed-plan synthesis: balanced partitioning of a guide and the bulge
pigeonhole.** The upper panel shows a guide of length L divided into `s` balanced
segments, with the substitution allowance `floor(M / (s - B))` applied to every
segment; the lower panel shows why `s >= B + 1` is required, namely that at most `B`
segments can contain a bulge, so at least `s - B` segments are gap-free and at least
one of them carries no more than the per-segment allowance. The panel also marks the
degraded plan, in which the guide is left whole and the run is not marked
`guaranteed`.

- Content: the partition rule, the allowance rule, the pigeonhole argument, and the
  degraded case.
- Source: `native/offtarget_engine/src/seed_plan.cpp:123-206` and
  `docs/SEED_PLAN_ANALYSIS.md` (sections 1-2).
- Scope: drawn for a 20 nt guide, k-mer sizes 8 and 10, `M` in 0-3 and `B` in 0-1;
  in all 16 cells the selected plan is `s* = 2` with two 10 bp segments and the
  reported plan cost ranges from 2 to 10734 variant enumerations
  [docs/SEED_PLAN_ANALYSIS.md:sec.2].

## Figure 6

**Thread scaling of the native indexed engine.** Search time and peak resident
memory as a function of the worker-thread count, for a mismatch-only configuration
and for a bulge stress configuration, with the thread count on a logarithmic axis.

- Content: wall time and peak RSS against thread count, separately for the two
  configurations.
- Source: `docs/NATIVE_INDEXED_BENCHMARK.md`.
- Scope: 5,000,000 bp in four contigs with `k = 10`. Mismatch-only: 2400 guides,
  `max_mismatch 2`, `max_bulge 0`, 1000 hits, search time 1.37 s at 1 thread and
  0.16 s at 32 threads (factor 8.6); 1, 8 and 32 thread rows are medians of three
  warm runs and the 4 and 16 thread rows are single warm runs
  [docs/NATIVE_INDEXED_BENCHMARK.md:19,27-33]. Bulge stress: 240 guides,
  `max_mismatch 2`, `max_bulge 1`, 160 hits, 81.14 s at 1 thread and 2.85 s at 32
  threads (factor 28.5), single warm runs
  [docs/NATIVE_INDEXED_BENCHMARK.md:40-41,47-53].

## Figure S1

**Candidate distribution and PairRank tiers for the case sites.** The intended panel
shows, for each case site, the distribution of extracted candidates over the
distance intervals and the tier assigned to each pair by the conservative
`prediction_only` ranking.

- Content: per-site candidate distribution and pair tiers.
- Source: `scy-test/` (AAVS1, TRAC, TRAC-exon3, PDCD1).
- Scope: `[TO FILL: 案例数据未在仓库中]`. The case outputs exist in the repository
  but are not among the evidence sources authorised for this draft, so no counts,
  scores or rankings are asserted here and the panel's sample size is left to be
  filled once the source decision is made [docs/handoff/manuscript-v1/task.md
  section 1, C3].
