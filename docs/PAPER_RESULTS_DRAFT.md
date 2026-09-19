# Results draft, version 1 (no-experiment version)

Draft of the Results section for the `manuscript-v1` handoff (round 1). Subsection
headings are unnumbered descriptive phrases in the order fixed by the round-1
contract. The Materials and Methods section is `docs/PAPER_METHODS_DRAFT.md`; the
Title, Abstract, Introduction and Discussion are `docs/PAPER_DRAFT.md`.

Annotation conventions, to be removed before submission:

- An integer in square brackets is a literature citation
  (`docs/PAPER_REFERENCES.md`); a `file:line` token in square brackets is a
  provenance marker for the adjacent number.
- Figure and table references follow the fixed numbering of
  `docs/FIGURE_TABLE_PLAN.md`: main-text figures, one supplementary figure, and
  supplementary tables.

Every number below is traceable to an authorised source. No claim depends on an
experiment performed in this study.

## Motif-anchored design space and expressiveness

The three layout kinds supported here, including the paired layouts with per-side
orientation, are the formalisations shown in Figure 2. Their specification model is
compared with 15 published design tools in a capability matrix (Figure 3, Table S1).
Each row is scored on six capability columns: custom PAM/TAM input, custom target
length, custom orientation, a middle-element constraint, enumeration of all
occurrences, and independent per-side settings for a pair. The matrix holds 16 data
rows, namely the 15 published tools plus this work
[expressiveness_matrix.tsv:1-17].

This work is recorded as `yes` on all six capability columns
[expressiveness_matrix.tsv:2], and the same six values are asserted against the
production code paths by a probe that reports 19 of 19 checks passed
[expressiveness_matrix.tsv:2]. Among the 15 published tools, none is documented as
`yes` on both the middle-element constraint and independent per-side settings: four
tools (CHOPCHOP v3 [9], CRISPETa [1], pgRNAFinder [2] and crisprVerse [10]) are
documented as `partial` on the middle-element constraint, and only two (pgRNAFinder
[2] and crisprVerse [10]) are documented as `partial` on independent per-side
settings, with no published tool recorded as `yes` on either column
[expressiveness_matrix.tsv:3,8,9,15]. Eight of the fifteen published tools are
documented as accepting freely written PAM/TAM input, but for the paired-guide
families the middle element is either absent or a coordinate interval rather than a
sequence constraint [expressiveness_matrix.tsv:3-17].

Coverage of the published tools is uneven and the matrix records this explicitly:
19 of the 90 published-tool cells are `unknown`, concentrated in DECKO [5] (6 cells),
GT-Scan [4] (5), EuPaGDT [24] (3), Cas-Designer [6] (2) and CRISPR multitargeter
[15] (2), with one in pgRNAFinder [2] [expressiveness_matrix.tsv:9-17]. `unknown` means that no public
documentation was located for that cell; it does not mean that the capability is
absent [task.md §2.8].

## Complete enumeration and pruning for paired layouts

Paired layouts are enumerated by anchoring on genomic occurrences of the two motifs
rather than on a user-supplied interval. Each of the two motifs is matched on both
strands independently, so all four strand-orientation combinations (`++`, `+-`,
`-+`, `--`) are produced
[Target_xbp_Target/extract_complex_queries.py:103-108]; in the three-element layout
the core `Y` sequence is located on both strands with palindrome de-duplication
[Target_xbp_Y_zbp_Target/extract_motifs.py:37-58]. Every candidate row records its
two orientation fields and its two 0-based half-open target intervals
[Target_xbp_Target/extract_complex_queries.py:84-91].

The distance between the anchors is an interval, and it drives the pruning: for each
left position the admissible right positions form a key range derived from the
minimum and maximum gap, and that range is recovered from a sorted position array by
binary search instead of by scanning every pair
[Target_xbp_Target/extract_complex_queries.py:118-125]. The unpruned pairwise cost is
O(n_left x n_right); with this pruning it becomes O(n_left log n_right + P), where P
is the number of pairs that actually fall inside the interval and therefore
P <= n_left x n_right. The bound also carries the one-off cost of sorting the
right-position array before those binary searches
[Target_xbp_Target/extract_complex_queries.py:118]. The effective cost is thus
governed by the width of the interval rather than by the number of motif occurrences
[Target_xbp_Target/extract_complex_queries.py:118-125]. In the three-element layout
the two intervals are independent parameters, so the same pruning is applied twice,
once per side [Target_xbp_Y_zbp_Target/extract_motifs.py:136-137,144-145].

The positions that feed this enumeration are served by the persistent index whose
memory layout is shown in Figure 4: an offsets table over all k-mers together with a
positions table that uses 4-byte entries while the indexed genome stays below 2^32
bases and 8-byte entries above that boundary [PAPER_METHODS_DRAFT.md:2.3]. On the
1,000,000 bp fixture the k = 8 index occupies 4524314 bytes and the k = 10 index
occupies 12388602 bytes, both with a 4-byte position type
[seed_plan_sweep.json:index_builds[0],index_builds[1]].

## Seed-plan cost curve and completeness

The seed plan is synthesised at request time from the guide length, the substitution
budget M, the bulge budget B and the index k-mer size k. How a guide is partitioned
and how each segment allowance follows from the two budgets is shown in Figure 5. Its enumeration cost is
W(s) = sum_i max(1, L_i - k + 1) * V(k, a), with a = M // (s - B) and
V(k, a) = sum_{c <= a} C(k, c) * 3^c [docs/SEED_PLAN_ANALYSIS.md:sec.1;
native/offtarget_engine/src/seed_plan.cpp:105-121]. For a 20 nt guide the synthesis
selects a two-segment plan, i.e. s* = 2 with two 10 bp segments, in every one of the
16 configurations of the sweep [docs/SEED_PLAN_ANALYSIS.md:sec.2].

The cost stays small while the bulge budget is zero and rises steeply once it is not.
For k = 10 the selected plan enumerates 2 variants at (M, B) = (0, 0) and 7352 at
(3, 1); for k = 8 the same two cells enumerate 6 and 10734 variants
[docs/SEED_PLAN_ANALYSIS.md:sec.2]. The measured search time follows the same shape.
The eight k = 8 configurations have median search times of 0.202 s to 12.404 s, and
the eight k = 10 configurations have median search times of 0.205 s to 1.082 s; the
slowest cells in both grids are the ones with both a substitution and a bulge budget,
namely 12.404 s at (3, 1) for k = 8 and 1.082 s at (3, 1) for k = 10
[seed_plan_sweep.json:records].

Completeness is asserted at run time rather than assumed, and it is claimed for
placements whose target k-mer windows consist of A, C, G and T only - a window
containing any other character is not stored in the index and is therefore not
enumerated [PAPER_METHODS_DRAFT.md:2.5]. All 16 configurations report
`seed_plan_guaranteed` and `exhaustive_seed_plan`, and the independent Python
transcription of the cost model reports `guaranteed` for the same 16 cells; the three
repeats of every cell agree on hits, candidate count and both markers
[seed_plan_sweep.json:records]. The candidate set is equal to the hit set in every
cell, so no candidate was withdrawn by the alignment acceptance tests on this fixture
[seed_plan_sweep.json:records]. The number of hits grows with the search budget, from
24 at (0, 0) to 66 at (3, 1) for k = 10 and 67 at (3, 1) for k = 8
[seed_plan_sweep.json:records]. Table S2 lists the grid with s*, W(s) and the
guarantee flags.

## Cross-engine benchmark and recall honesty

On the 1,000,000 bp fixture with 12 guides of 20 nt and 24 planted exact hits, the
native indexed engine returned all 24 hits with a warm search median of 0.048 s after
an index build of 0.107 s [REPORT.md:15]. The same 24 hits took 0.518 s with BLAST,
0.176 s with Bowtie2, 0.990 s with the Python indexed backend, 1.547 s with
Cas-OFFinder and 2.156 s with the in-memory exact backend, the last two having no
persistent index to build [REPORT.md:16-20]. The exact backend builds an in-memory
search structure on every call, so its search time is not comparable to a warm
persistent-index search [REPORT.md:22-23].

Enabling bulge search costs more in every backend at max_mismatch 0 and max_bulge 1:
0.183 s here, against 0.565 s with BLAST, 0.176 s with Bowtie2, 2.617 s with the
exact backend and 8.729 s with the Python indexed backend [REPORT.md:32-36]. This
fixture does not plant a true bulge hit, so those numbers measure the cost of
enabling bulge search and not bulge recall [REPORT.md:38-39]. Recall is reported
separately, and unfavourably for one backend: in a 1-mismatch stress run the exact,
indexed, native-indexed and Cas-OFFinder backends each returned 36 of 36 hits, while
BLAST returned 31 of 36 because its local alignment extension truncated some
one-mismatch 20 nt alignments [REPORT.md:52-54].

Thread scaling was measured on the larger fixture (5,000,000 bp in four contigs, 2400
guides, max_mismatch 2, max_bulge 0, 1000 hits). Search time fell from 1.37 s at one
thread to 0.16 s at 32 threads, a factor of 8.6
[NATIVE_INDEXED_BENCHMARK.md:12-13,19,27-33]; on the bulge stress configuration
(240 guides, 160 hits) it fell from 81.14 s to 2.85 s, a factor of 28.5
[NATIVE_INDEXED_BENCHMARK.md:40-41,47-53]. Both scaling curves are plotted in Figure 6, and Table S3 collects the cross-engine measurements.

## Determinism and resource bounds

Hit output does not depend on the thread count. On the 1,000,000 bp fixture with
max_mismatch 2, max_bulge 0 and k = 10, the four thread counts 1, 4, 8 and 32 each
returned 36 hits and produced one and the same SHA-256 digest over the hit lines,
`0549c426662a2fa2994b8696971c51366f330456ed7392adaa58d7be62cbf499`
[docs/SEED_PLAN_ANALYSIS.md:sec.3]. The larger fixture repeats the observation: the
1, 4, 8, 16 and 32 thread runs all returned 1000 hits with the same hit-only digest,
and the bulge stress run likewise returned 160 identical hits at every thread count
[NATIVE_INDEXED_BENCHMARK.md:19-21,27-31,41,47-51].

Resource use is bounded rather than best-effort. Peak resident memory grew with the
thread count, from 34.0 MiB at one thread to 204.0 MiB at 32 threads on the
mismatch-only run [NATIVE_INDEXED_BENCHMARK.md:27-31], and from 32.0 MiB to 212.0 MiB
on the stress run [NATIVE_INDEXED_BENCHMARK.md:47-51]. A memory ceiling, a candidate
cap and a timeout are explicit options; an over-limit outcome is reported through the
exit-status contract instead of being downgraded to an unrestricted run
[PAPER_METHODS_DRAFT.md:2.7]. The sequence cache under the auto policy is enabled
only when one full genome copy per effective worker, plus per-worker overhead and a
reserved margin, fits within half of the currently available memory
[PAPER_METHODS_DRAFT.md:2.7].

## Scoring, calibration status and pair ranking

Scores are reported together with an explicit calibration state, and each portable
model port is checked against its published reference where a reference exists. The
DeepCRISPR port [28] reproduces the TensorFlow reference graph with a maximum output
error of 2.98e-7 over 100 official examples [MODELS.md:47]. The Azimuth port [27]
agrees with the official 1000-guide reference at Spearman 0.993 and MAE 0.0073, with
561 of 947 compared rows identical [MODELS.md:80-81]. The CRISPR-M port [30]
reproduces its sample pair with output 0.6321092247962952 [MODELS.md:26]. The DeepCpf1
port [29] reproduces the two official sample outputs 55.699318 and 53.469837 as
55.699310 and 53.469837, within floating-point rounding [MODELS.md:56-57]. The TnpB
path is served either by the local omegaRNA rules or by the online TEEP predictor
[MODELS.md:137-148], whose reference method is the deep-learning TnpB study [14] and
whose effector biology is described by the TnpB and IS200/IS605 literature [25][26].
Substitution-only hits scored by a reference model are labelled
`calibrated_reference`, whereas bulge hits carry the versioned conservative penalty
and are labelled `uncalibrated` [PAPER_METHODS_DRAFT.md:2.8]. Table S4 lists the
models, their file formats, their registry status and their calibration state.

Paired layouts are ranked as pairs rather than as independently ranked guides, and
both members of a pair must pass [PAPER_METHODS_DRAFT.md:2.8]. The mode used
throughout is the conservative `prediction_only` mode, which bounds the off-target
burden of a pair by the sum of the two per-side bounds, bounds the worst single-locus
risk by the larger of the two per-side maxima, and gates the number of high-risk loci
against a policy threshold [PAPER_METHODS_DRAFT.md:2.8].

## Case sites: AAVS1, TRAC and PDCD1

[TO FILL: 案例数据未在仓库中] Candidate distributions and PairRank tiers for
the three case sites are specified as Figure S1. The repository contains case
outputs under `scy-test/` (AAVS1, TRAC, TRAC-exon3, PDCD1), but `scy-test/` is not
among the evidence sources authorised for the numbers in this draft, so no counts,
scores or rankings for these sites are reported here [task.md §1 C3]. This
subsection keeps its place and its Figure S1 reference pending a decision on whether
`scy-test/` becomes an authorised source, so that the case evidence is added rather
than reconstructed.

## Implementation, interface and test suite

The platform is a Python application with a native C++20 indexed engine. The engine
reports version `offtarget-engine 0.1.0` with index format 1, accepts an indexed build
up to k = 12, exposes both `3prime` and `5prime` PAM sides, and advertises thread
support and a process memory ceiling [task.md §2.1]. Three surfaces expose the same
specification model: a desktop interface, a local web interface and a command-line
layer, all of which drive the same design, search, scoring and export stages.

Table S5 records the output field contract. Result tables are organised into common
statistic columns, specificity and on-target columns, bulge and calibration columns,
and the TnpB and RNA sub-feature columns, where each group is written only when the
run selects the corresponding models or inputs [OUTPUTS.md:84-165]. Mismatch counts
are written as `MM0` to `MMn` buckets whose leading bucket counts only full-length
query matches, and each model contributes its own
`on_target_score_<model>` / `off_target_specificity_<model>` columns rather than a
single combined score [OUTPUTS.md:84-118]. Columns for fields that no longer belong
to the contract, such as `combined_score` and the per-side rank columns, are not
emitted [OUTPUTS.md:173-193]. The suite covers the design, search, scoring, export
and control layers; the engine's exit-status contract and its parameter handling are
documented in `docs/NATIVE_INDEXED_ENGINE_DESIGN.md`.
