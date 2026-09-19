# Manuscript draft, version 1 (no-experiment version)

Draft of the manuscript body for the `manuscript-v1` handoff (round 1). It contains
the Title, the Abstract, the Introduction and the Discussion. The Materials and
Methods section is maintained separately in `docs/PAPER_METHODS_DRAFT.md` and is not
reproduced here; the Results section is in `docs/PAPER_RESULTS_DRAFT.md`.

Two annotation conventions are used in this file and are to be removed before
submission:

- An integer in square brackets, such as `[7]`, is a literature citation. The
  reference list is `docs/PAPER_REFERENCES.md`.
- A `file:line` token in square brackets, such as `[REPORT.md:15]`, is a provenance
  marker that points at the repository artefact the adjacent number came from. It is
  a drafting aid, not part of the manuscript text.

Figure and table cross-references follow the fixed numbering of
`docs/FIGURE_TABLE_PLAN.md`. Findings are stated so that no claim depends on an
experiment performed in this study.

## Title

CRISPR-Motif Workbench: a constraint-driven guide design platform with a native
indexed off-target engine

## Abstract

CRISPR guide design is usually specified as a query against a genomic interval or a gene identifier, so the choices that actually define a design intent - protospacer or target adjacent motif sequence, guide length, strand orientation, and the relative placement of two guides - can only be expressed indirectly, if at all. We present CRISPR-Motif Workbench, a constraint-driven design platform in which a design intent is stated as a set of orthogonal parameters over user-supplied IUPAC motifs, and the resulting design space is defined as the complete set of its solutions. The platform enumerates every genomic occurrence of the anchoring motifs, together with all four strand-orientation combinations of a paired layout, including a three-element layout whose left and right distance ranges are independent. Candidate sites are then evaluated with a native C++20 persistent index engine that synthesizes its seed plan at runtime, reports whether the resulting search is guaranteed to be exhaustive for target windows composed only of A, C, G and T, and returns hits in an order that does not depend on the number of threads. In a capability matrix covering 15 published design tools, none is documented as expressing a sequence-level middle-element constraint together with independent per-side distance ranges. The software offers a desktop interface, a local web interface and a test suite; model scores are reported with an explicit calibration status, and no experimental validation was performed in this study.

## Introduction

Guide design tools can be grouped by what they take as their input. Region- and
gene-centred tools accept a sequence, a gene identifier or a genomic interval and
return scored single guides: Cas-Designer [6], FlashFry [7], CHOPCHOP v3 [9],
CRISPOR [22], CRISPRitz [8], Breaking-Cas [23], EuPaGDT [24], CaSilico [11] and
crisprVerse [10]. Paired-guide tools also start from a genomic interval that is to
be deleted or spanned, and then select a pair inside it: CRISPETa [1], pgRNAFinder
[2], GT-Scan [4], DECKO [5], GuideScan [3] and GuideScan2 [21]. A third family
addresses library-scale design, in which many guides must jointly cover many
targets: CRISPR multitargeter [15], CRISPys [19], MINORg [18], multicrispr [20],
ALLEGRO [17] and CRISPR-COPIES [16]. Off-target search itself is served by dedicated
engines such as Cas-OFFinder [12] and Off-Spotter [13]. Across these families the
design intent is expressed indirectly: the user names a locus or a gene, and the
sequence parameters that determine the outcome are fixed by the tool, by a preset
nuclease, or by defaults.

Two gaps follow. One is parameter expressiveness, and it is a recognised need
rather than our own assertion. The 2025 NAR library-design tool ALLEGRO closes its
Discussion by noting that, in prokaryotic genomes, "additional considerations may
include overlapping genes, operon structures, and organism-specific PAM recognition
(e.g. for Cas12a or other non-Cas9 effectors)", and that "adapting ALLEGRO for
bacterial systems may therefore involve customizing PAM constraints ..." [17]. A tool
published in the same journal and the same year therefore records PAM
customisation as work that remains to be done - for Cas12a and for non-Cas9
effectors such as TnpB, whose TAM is sequence-level and effector-specific [25][26]
and for which efficiency predictors such as TEEP are trained per effector [14].
Even where a tool exposes partial sequence-level freedom, PAM/TAM sequence,
protospacer length, strand orientation and the relative placement of two guides
cannot be combined orthogonally, and the placement of a third, sequence-constrained
element between two guides cannot be stated at all.

Prior paired-guide tools specify a genomic interval to be deleted or spanned
[1][2][4][5]; the guide pair is then chosen inside that interval. We instead
specify a sequence-level layout: the design space is the set of genomic placements
of user-supplied IUPAC motifs subject to per-side orientation and independent
distance constraints. To our knowledge, this motif-anchored specification model,
and in particular the three-element layout with independent left and right distance
ranges, has not been described.

The second gap is in the engine layer. Off-target search is where a candidate is
accepted or rejected, yet the search strategy is usually fixed when the index is
built, the memory footprint is not contractually bounded, and the order of the
reported hits can depend on how many worker threads happen to be used, which makes
downstream selection, caching and comparison across runs fragile. Approximate
nearest-neighbour search deliberately trades recall for throughput [16], while
tools built on external aligners inherit the aligner's calibration [12][13].

We present CRISPR-Motif Workbench, a constraint-driven design platform that
separates the specification of a design from its evaluation (Figure 1). Its two
primary contributions are as follows. C1 makes the design intent an explicit object: a request is a set of orthogonal parameters over user-supplied IUPAC
motifs, the design space is defined as the complete set of its solutions, three
layout kinds are supported, and the paired layouts are enumerated over all four
strand-orientation combinations, including a three-element layout whose left and
right distance ranges are independent (Figure 2). C2 is a native C++20 persistent
index engine that synthesises its seed plan at run time, reports whether the
resulting search is guaranteed to be exhaustive for target windows composed only of
A, C, G and T, merges hits in input order so that the emitted sequence does not
depend on the thread count, and enforces hard memory and timeout ceilings instead of
degrading silently. Two supporting components complete the platform: C3, a
conservative pair-ranking scheme for paired layouts,
and C4, portable NumPy re-implementations of published deep models whose scores
carry an explicit calibration status.

## Discussion

Two comparisons are worth stating explicitly. One is with the paired-guide
tools that came before. CRISPETa [1] and pgRNAFinder [2] each design a guide pair
for a genomic interval supplied by the user and rank the resulting candidates with
scoring functions of their own; the difference here is not the ranking, it is the
design space. In this platform the design space is defined by genomic occurrences of
user-supplied IUPAC motifs subject to per-side orientation and distance constraints,
and the three-element layout with independent left and right distance ranges (Pattern
B) has no counterpart among the tools surveyed in the capability matrix. The second
comparison is with the indexed design and off-target tools. GuideScan2 [21] and
CRISPRitz [8] accept configurable PAM and target length and search at scale, but
their seed strategy is fixed by the implementation; here the seed plan is synthesised
per request, its completeness is stated and marked at run time, the hit sequence is
independent of the thread count, and memory and time are hard ceilings rather than
best-effort targets.

Several limitations should be read together with the results. The most important is
that this study is a computational tool paper: no experimental validation was
performed in this study, and no model score or ranking reported here has been
validated experimentally here, so every claim is confined to what can be specified,
enumerated and searched. A further limitation is that the pair-ranking mode used
throughout is the conservative `prediction_only` mode, which orders pairs but does
not output calibrated probabilities; the `experiment_calibrated` mode is specified
but not implemented. Bulge hits are scored with the versioned conservative penalty
`conservative_bulge_v1` and are labelled `uncalibrated`, so they express relative
risk rather than measured activity. Model ports also inherit their runtime
dependencies: the TIGER Cas13d port requires TensorFlow, and the TEEP TnpB path calls
an online service. Genomes above 200 Mbp are preferentially searched with BLAST
rather than by automatically building a very large index [REPORT.md:43-48]. The
benchmarks reported here rest mainly on synthetic genomes and a limited number of
real loci, so the timings are relative comparisons under a controlled fixture rather
than absolute throughput on production genomes. Finally, the capability matrix
records `unknown` for 19 tool-column cells because no public documentation was
located for them [expressiveness_matrix.tsv:9-17]; `unknown` is not the same as
`no`, and the comparison should be re-checked as vendor documentation evolves.
