# Materials and Methods - draft of Section 2

Draft produced for the `methods-draft` handoff (round 1). The body text is
English; the only Chinese text in this file is in the notes column of the
Anchor table at the end. Superscript numbers in the body refer to that table.

Placeholder convention: `[TIME]`, `[RATIO]` and `[N]` denote measurements that
are reported in the Results section. No performance figures are asserted in
this section.

## 2. Materials and Methods

### 2.1 Design specification

A guide-design request is expressed as a tuple

    S = (L, P, l, o, s)

in which `L` is the protospacer (target) length in nucleotides, `P` is the
PAM/TAM motif written as an IUPAC nucleotide string and allowed to be empty, `l`
is the layout kind, `o` groups the placement parameters (position of the target
relative to the PAM/TAM, PAM side `3prime` or `5prime`, and genomic strand),
and `s` groups the sequence constraints (IUPAC motif sequences, flank length,
flank side `upstream` or `downstream`, and the distance intervals that separate
adjacent elements) [1][2][3][11].

The layout kind takes one of three values: `single_motif_flank` (one motif with
its flanking target), `motif_gap_motif` (two motifs separated by a gap
interval), and `y_centered_motifs` (a sequence-constrained middle element `Y`
flanked by two independent distance intervals) [5][11]. Motif and `Y` sequences
are drawn from the IUPAC alphabet `ACGTUNRYSWKMBDHV` [4][10], and a flank is
attached either upstream or downstream of its element [3].

A specification is admitted only if it passes validation, which enforces the
pattern-specific requirements: `single_motif_flank` requires its motif,
`motif_gap_motif` requires both flanking motifs together with a gap interval,
and `y_centered_motifs` requires a `Y` sequence and both distance intervals
[6][7][8]. Every distance interval must provide both endpoints and satisfy
0 <= min <= max [9]. Admissible specifications therefore form a well-defined
set, and for each admitted specification `S` the design space

    D(S)

is the set of all genomic realisations - guide candidates, or candidate pairs
for the paired layouts - that satisfy every constraint in `S`. The designer
emits `D(S)` as a complete solution set: scoring and ranking order the members
of `D(S)` but do not add or remove members [1].

### 2.2 Motif-anchored layouts and strand enumeration

Designs are anchored on genomic occurrences of an IUPAC motif rather than on
user-supplied coordinate intervals [11]. Two paired layouts are defined. In
pattern A (`motif_gap_motif`) the layout is

    Target -- gap[x_min, x_max] -- Target

where each of the two elements is a motif with its own PAM/TAM motif, target
length and target position, and a single interval `[x_min, x_max]` bounds the
gap between them [7][11]. In pattern B (`y_centered_motifs`) the layout is

    Target -- [x_min, x_max] -- Y -- [y_min, y_max] -- Target

where `Y` is a sequence constraint matched without mismatches and the two
distance intervals are independent of each other [8][11].

For the paired layouts the left and right motifs are matched on both genomic
strands independently, so the four strand combinations `++`, `+-`, `-+` and
`--` are all enumerated [12]. Each extracted candidate records the orientation
of its two anchors in `left_strand` and `right_strand`; the row-level `strand`
field is `plus` for the two cross-strand combinations and `minus` only when
both anchors lie on the minus strand [13]. Each candidate also reports its two
target intervals as 0-based half-open `left_target_start` / `left_target_end`
and `right_target_start` / `right_target_end`; these columns, together with the
per-side strand fields, belong to the candidate table produced by the
specification layer [14][15].

PAM/TAM motifs are matched with the same IUPAC alphabet [4]: each pattern
character is expanded to a bit mask over `A`, `C`, `G` and `T` (with `U`
treated as `T`), and a match requires a non-empty intersection at every
position [59][60]. On the plus strand the checked span lies either 3-prime or
5-prime of the target; on the minus strand the reverse-complemented motif is
matched against the corresponding span on the opposite side [61]. The PAM
sequence reported with a hit is returned in the orientation of the guide, so a
minus-strand hit reports the reverse complement of the genomic span [62].

### 2.3 Index format

Off-target search uses a persistent position index in the `CRISPRGGI` format,
version 1, whose magic string and version constant are fixed by both the reader
and the writer [16]. The file is little-endian and consists of a fixed header
(magic, format version, `k`, contig count, total bases), a contig table (name,
start and length per contig), the number of valid k-mer positions, an offsets
table of `4^k + 1` 64-bit entries, and a positions table [17][18]. Contig
starts are stored in ascending order and re-checked on load [20]. The positions
table uses 4-byte entries when the indexed genome has fewer than `2^32` bases
and 8-byte entries otherwise, so the index width follows the genome rather than
a fixed choice [19]. Only k-mer windows over `A`, `C`, `G` and `T` are indexed;
windows containing any other character are excluded when the index is built
[21].

A JSON sidecar records the format name, the version, `k`, the genome path, the
genome fingerprint, the genome size, the total base count, the number of valid
k-mer positions and the contig table [22][23]. The fingerprint is a SHA-256
digest computed over the prefix and the suffix of the FASTA file and is
re-checked at load time: an index whose stored fingerprint differs from the
current genome is reported as stale rather than used [24][25]. Index and
metadata files are written to temporary paths and published by rename, so a
partially written index is not visible under its final name [28]. The `.ggi`
payload is mapped read-only and shared between worker threads [26], and
structural inconsistencies (bad magic, unsupported version, truncated offsets
or positions, non-monotonic offsets, unsorted contigs) are reported as explicit
errors instead of being tolerated [27]. The version 1 layout is read and
written by both the Python and the C++ implementations, so an index built by
either side loads on the other [30], and native builds accept `k = 8..12` [29].

### 2.4 Seed-plan synthesis

Candidate generation uses a segmented seed plan synthesised at search time from
the guide length and the search budgets. The contract the plan must satisfy
allows substitutions and small DNA/RNA bulges, both PAM sides and both strands,
reports 0-based genomic coordinates, and requires exhaustive behaviour within
the plan [32]. Unless overridden, a search runs with four substitutions
(`M = 4`), no bulges (`B = 0`) and a 3-prime PAM check [58].

Let `L` be the guide (probe) length, `M` the maximum number of substitutions,
`B` the maximum number of bulges, `k` the k-mer size of the index, which is the
effective seed length [33], and `s` the seed count. The plan partitions the
guide into `s` consecutive segments, and the admissible plans are those with

    s >= B + 1,        s <= floor(L / k),                                  (1)

    allowed = floor(M / (s - B)),                                          (2)

where `allowed` is the substitution allowance granted to every segment
[34][35][33]. The segment lengths come from

    partition_lengths(L, s):  len_i = floor(L / s) + 1   for i < L mod s,  (3)
                              len_i = floor(L / s)       otherwise,

so the partition is as even as possible and every segment contains at least one
k-mer window [39].

The enumeration work of a plan is the sum, over segments, of the number of
k-mer windows in the segment and the number of seed variants enumerated for
each of those windows,

    W(s) = sum_i max(1, len_i - k + 1) * sum_{c=0..allowed} C(k, c) * 3^c,  (4)

that is, the variant budget is applied to every k-mer window of a segment
[40][41]. All arithmetic saturates: additions and multiplications are capped so
that a cost above the cap is reported as `cap + 1` instead of wrapping [42],
and the cap is 500 000 variants by default [36]. Among the plans that satisfy
(1)-(3) and stay within the cap, synthesis selects the plan that minimises the
pair `(W(s), s)` lexicographically, so the plan with the smallest enumeration
work is chosen and the seed count serves as the tie-break [37]. Algorithm 1
states the procedure.

```text
Algorithm 1  Seed-plan synthesis
Input:  L            guide (probe) length in nt
        M            maximum substitutions (max_mismatch)
        B            maximum bulges (max_bulge)
        k            k-mer size of the index (effective seed length)
        V            variant cap (500 000 by default)
Output: segments     list of (start, length, allowed_mismatches)
        guaranteed   true when a plan within the cap was found
        estimate     the selected plan's W(s)

 1  kmin <- max(1, k)
 2  smax <- floor(L / kmin)
 3  smin <- max(1, B + 1)
 4  if smax < smin then
 5      return { (0, L, M) }, guaranteed <- false,
 6             reason <- "need at least smin non-overlapping kmin-nt seeds ..."
 7  found <- false; bestW <- 0; bestS <- 0; best <- {}
 8  for s <- smin to smax do
 9      d <- s - B
10      if d <= 0 then continue
11      allowed <- floor(M / d)
12      sizes <- partition_lengths(L, s)                # equation (3)
13      W <- 0; over_cap <- false
14      for each size in sizes do
15          W <- capped_add(W, segmented_variant_work(size, k, allowed), V)
16          if V != 0 and W > V then over_cap <- true; break
17      if over_cap then continue
18      cursor <- 0; segments <- {}
19      for each size in sizes do
20          segments <- segments + { (cursor, size, allowed) }
21          cursor <- cursor + size
22      if not found or (W, s) < (bestW, bestS) then
23          found <- true; bestW <- W; bestS <- s; best <- segments
24  if not found then
25      return { (0, L, M) }, guaranteed <- false,
26             reason <- "the exhaustive seed variants for max_mismatch and
27                        max_bulge exceed the configured cap"
28  return best, guaranteed <- true, estimate <- bestW
```

The two helper costs are

    segmented_variant_work(len, k, allowed)
        = max(1, len - k + 1) * variant_count(k, allowed),                  (5)

    variant_count(k, allowed) = sum_{c=0..allowed} C(k, c) * 3^c.           (6)

Search enumerates exactly these variants: for every segment and every k-mer
window inside it, all k-mers within Hamming distance `allowed` of the probe
window are generated, every genomic occurrence of such a k-mer yields a
candidate position, and each candidate is then verified by the alignment stage
against `M` substitutions and `B` bulges [45][46][43].

Note on source correspondence: the per-segment cost evaluated by the
implementation is the number of k-mer windows in the segment multiplied by the
number of variants of a single k-mer of length `k`, as in equations (5) and
(6), rather than a binomial sum over the full segment length. Because a segment
that carries at most `allowed` substitutions in total also carries at most
`allowed` substitutions in each of its k-mer windows, the completeness argument
of Section 2.5 is unaffected. The Anchor table records the anchors and notes
the wording difference from the draft specification.

### 2.5 Lemma 1 (completeness) and proof

**Lemma 1 (seed-plan completeness).** Let `L`, `M`, `B` and `k` be as above,
let `s` be an integer with `max(1, B + 1) <= s <= floor(L / k)`, let
`len_1, ..., len_s` be the balanced partition of the guide given by equation
(3), and let every segment receive the allowance
`allowed = floor(M / (s - B))`. Consider a placement of the guide in the genome
that has at most `B` bulges and at most `M` substitutions. Then at least one
segment is free of bulges, and that segment contains at least one k-mer window
whose target counterpart differs from the corresponding guide window by at most
`allowed` substitutions. Algorithm 1 enumerates that window with exactly that
allowance, so the placement is reached by the plan's variant enumeration and is
then accepted by the alignment stage.

**Proof.** Fix a placement with at most `B` bulges and at most `M`
substitutions, and consider the monotone correspondence between guide positions
and target positions induced by the alignment used by the search.

(i) The bulges split the alignment into at most `B + 1` gap-free blocks:
between two consecutive bulges, guide and target are matched position for
position, with substitutions only. A bulge lies between two guide positions and
can therefore fall inside the interior of at most one segment of the partition,
and the segments are disjoint. Hence at most `B` of the `s` segments contain a
bulge, and at least `s - B >= 1` segments are gap-free: for each of them the
guide substring aligns to a contiguous target substring, position for position.

(ii) The total number of substitutions of the placement is at most `M`, so the
sum of the substitution counts of the `s - B` gap-free segments is at most `M`.
By the pigeonhole principle, at least one of those segments has at most
`floor(M / (s - B)) = allowed` substitutions.

(iii) Let that segment have length `len >= k`; it contains
`max(1, len - k + 1) >= 1` k-mer windows. Because the segment is gap-free, each
of its windows aligns to a contiguous target window, and because the segment
carries at most `allowed` substitutions in total, each of its windows carries at
most `allowed` substitutions as well. For every offset, the target window is
therefore within Hamming distance `allowed` of the corresponding guide window.

(iv) By construction, Algorithm 1 enumerates that segment with exactly the
allowance `allowed` (line 11) and enumerates every k-mer within Hamming distance
`allowed` of the probe window, as in equations (5) and (6). The position index
stores every genomic occurrence of every valid k-mer, so the occurrence used by
this placement is retrieved, the corresponding guide start is reconstructed,
and the alignment stage is run on that candidate. The placement satisfies both
acceptance tests, namely at most `M` substitutions and at most `B` bulges, so
it is reported as a hit. Since the placement was arbitrary, every hit permitted
by the search contract is reachable under the plan, and the search performed
under the plan is complete. QED

Algorithm 1 sets `guaranteed` to true exactly when at least one admissible seed
count stayed within the variant cap, and it records the selected plan's
estimated variant count [44]. Two run-level markers expose this state. The
`seed_plan_guaranteed` field reports the flag computed for the longest guide in
the run, and `exhaustive_seed_plan` is the conjunction of the per-guide flags
over all guides in the run [49]; both markers are emitted in the summary object
of the JSON Lines output [50]. When no admissible plan is found, the plan
degrades to a single whole-guide segment carrying the full substitution budget
`M`, `guaranteed` remains false, and a human-readable reason string records why
[38][43]. The degradation is not silent: for genomes of at most 50 000 000
bases the engine runs a whole-genome candidate scan with the same substitution
and bulge acceptance tests, and for larger genomes it terminates with the
unsupported-parameter exit status together with the reason string [38][56].

### 2.6 Deterministic parallelism

Search parallelises over guides. A fixed worker pool consumes guides from a
bounded queue, each worker records the input ordinal of the guide it took, and
completed per-guide results are buffered and emitted in input order [51]. The
memory-mapped index is shared read-only between workers, while each worker
opens its own positional FASTA reader and an optional sequence cache [47].
Because merging follows the input order and the hits of each guide are then
deduplicated and sorted with a deterministic comparator [48], the emitted hit
sequence is identical for every value of `--threads`; the design records the
same requirement as an explicit decision [31][47]. Measured thread scaling and
the thread-independence digest are reported in the Results section ([TIME],
[RATIO]).

### 2.7 Resource bounds

The build and search commands accept an explicit process memory ceiling
(`--max-memory-mb`); an omitted value or zero means no ceiling, and the
command-line value overrides the environment variable [52]. A search performs a
preflight estimate before running and then checks the resident set size at
regular candidate-check intervals; on an over-limit observation all workers are
cancelled and no JSON Lines output is emitted until the complete result set is
ready [53][58]. A memory-limited outcome is not downgraded to an unrestricted
run of the fallback implementation [54]. An optional candidate cap raises the
candidate-guard error rather than emitting a partial result set [55]. Sequence
caching under the `auto` policy is enabled only when one full genome copy per
effective worker, plus per-worker overhead and a reserved margin, fits within
half of the currently available memory [57].

Build and search report outcomes through a fixed exit-status contract
(0 success; 2 command-line usage error; 3 unsupported search parameters or seed
plan; 4 input/output, index or FASTA error; 5 internal error) and propagate a
non-zero status to the caller [56]. Complete resource measurements are reported
in the Results section ([TIME], [N]).

### 2.8 Calibration-state propagation and pair ranking

Every score carries an explicit calibration state. Substitution-only hits scored
by a published reference model are labelled `calibrated_reference`, whereas
bulge hits are scored with the versioned conservative penalty
`conservative_bulge_v1` and labelled `uncalibrated`, as are scores produced by
the generic heuristics; the state is propagated together with the score into
the result tables so that reference-model output can be distinguished from
uncalibrated output [66][65]. For a single guide the specificity of an
off-target set is aggregated as
`off_target_specificity = 1 / (1 + sum(CFD))`, with the perfect-match
contribution removed when a single primary target is assumed, so that the value
expresses residual risk beyond the intended site [63]; mismatch counts are
reported as `MM0 ... MMn` buckets, whose leading bucket counts full-length
query matches only [64].

Paired layouts are ranked as pairs rather than as independently ranked guides,
and both members of a pair are required to succeed [68]. Two ranking modes are
defined, `prediction_only` and `experiment_calibrated` [67]. In the
prediction-only mode, which is the mode used for the layouts described above
[71], the off-target burden of a pair is bounded conservatively by
`B_pair+ = B_L+ + B_R+` [69], the worst single-locus risk by
`M_pair+ = max(M_L+, M_R+)`, and the number of high-risk loci `H_pair` is gated
against a policy threshold [70]. The experiment-calibrated mode is specified
but not implemented in the current pipeline; its fields are a documented target
contract rather than produced output, and policy thresholds default to
`policy_status = uncalibrated` when no matched paired experiment is available
[72][73].

## Anchor table

Each numbered row lists the artifact that supports the corresponding
superscript in the body. `file:line` refers to the revision used for this draft
(`R:\songji\programfile`). The notes column is the only Chinese text in this
file.

| # | Statement | Anchor (`file:line`) | 说明 |
| --- | --- | --- | --- |
| [1] | Design request `S = (L, P, l, o, s)`; output is the complete solution set | `docs/PAPER_OUTLINE.md:123` | 大纲 2.1 条原文：形式化与完备解集 |
| [2] | `MotifSpec(sequence, flank_length, side)` | `shared/design/pattern_spec.py:23-26` | 三个字段定义 |
| [3] | Flank side is `upstream` or `downstream` | `shared/design/pattern_spec.py:14-16, 36` | `Side` 枚举与校验 |
| [4] | IUPAC alphabet `ACGTUNRYSWKMBDHV` | `shared/design/pattern_spec.py:19` | `_IUPAC_BASES` |
| [5] | Three layout kinds | `shared/design/pattern_spec.py:8-11` | `PatternKind` 三个取值 |
| [6] | Validation is the admission gate | `shared/design/pattern_spec.py:56-60` | `validate()` 入口 |
| [7] | Pattern A requires both motifs and a gap interval | `shared/design/pattern_spec.py:65-68` | `motif_gap_motif` 分支 |
| [8] | Pattern B requires `y_sequence` and both intervals | `shared/design/pattern_spec.py:71-84` | `y_centered_motifs` 分支 |
| [9] | Distance intervals need both endpoints and `0 <= min <= max` | `shared/design/pattern_spec.py:89-96` | `_validate_distance_range` |
| [10] | Motif and `Y` sequences are checked against the IUPAC set | `shared/design/pattern_spec.py:31-32, 74-75` | 非法字符即报错 |
| [11] | Layout elements: PAM/TAM, target length, target position, distances | `docs/design_patterns_en.md:1-22` | 三种布局的英文定义 |
| [12] | Four strand combinations `++ / +- / -+ / --` | `docs/design_patterns_en.md:24-26` | 左右 motif 双链独立匹配 |
| [13] | `left_strand` / `right_strand` and row-level `strand` | `docs/design_patterns_en.md:26-29` | 跨链组合记为 plus |
| [14] | 0-based half-open target intervals | `docs/design_patterns_en.md:29-30` | `left/right_target_start/end` |
| [15] | Candidate table carries the interval columns | `shared/design/pattern_spec.py:147-160` | `candidate_columns()` Pattern A 分支 |
| [16] | Index magic `CRISPRGGI` and format version 1 | `native/offtarget_engine/include/offtarget/genome_index.hpp:15-17` | 常量定义 |
| [17] | Version 1 byte layout | `docs/NATIVE_INDEXED_ENGINE_DESIGN.md:355-371` | 头 + contig 表 + offsets + positions |
| [18] | Offsets table has `4^k + 1` 64-bit entries | `native/offtarget_engine/include/offtarget/genome_index.hpp:78-80` | `offset_count()` |
| [19] | 4-byte or 8-byte position entries by genome size | `native/offtarget_engine/include/offtarget/genome_index.hpp:75-77, 94-96` | `u4` / `u8` 自适应 |
| [20] | Contig records and sorted contig starts | `native/offtarget_engine/include/offtarget/genome_index.hpp:19-23`; `native/offtarget_engine/src/genome_index.cpp:483-487` | 加载时校验递增 |
| [21] | Only `ACGT` k-mer windows are indexed | `docs/NATIVE_INDEXED_ENGINE_DESIGN.md:378-379` | 非法窗口被排除 |
| [22] | Metadata sidecar is UTF-8 JSON | `docs/NATIVE_INDEXED_ENGINE_DESIGN.md:381-382` | 允许额外键 |
| [23] | Metadata field list | `native/offtarget_engine/src/build_index.cpp:628-642` | `format`/`version`/`k`/指纹/contigs |
| [24] | Stored fingerprint is compared with the current genome | `native/offtarget_engine/src/genome_index.cpp:605, 619` | `metadata_fingerprint` + `is_valid_for` |
| [25] | Fingerprint = SHA-256 over FASTA prefix and suffix | `native/offtarget_engine/src/genome_index.cpp:631, 646` | `sha256_file_prefix_suffix` |
| [26] | Index payload is mapped read-only and shared | `native/offtarget_engine/include/offtarget/genome_index.hpp:25-29, 91-93`; `native/offtarget_engine/src/genome_index.cpp:450` | `MappedFile` / `index_bytes()` |
| [27] | Malformed index diagnostics | `native/offtarget_engine/src/genome_index.cpp:452-462, 499-500, 520-521` | `BAD_MAGIC` 等显式错误 |
| [28] | Temp file + rename publication | `native/offtarget_engine/src/build_index.cpp:453-462, 685` | 不暴露半成品索引 |
| [29] | Native builds accept `k = 8..12` | `native/offtarget_engine/README.md:97-98`; `docs/NATIVE_INDEXED_ENGINE_DESIGN.md:179` | 支持范围 |
| [30] | Version 1 is read and written by Python and C++ | `docs/NATIVE_INDEXED_ENGINE_DESIGN.md:54-56` | 双向兼容 |
| [31] | Output ordering is independent of worker scheduling | `docs/NATIVE_INDEXED_ENGINE_DESIGN.md:61` | 设计决策 7 |
| [32] | Search contract: substitutions, bulges, both PAM sides, both strands, 0-based, exhaustive within plan | `docs/NATIVE_INDEXED_ENGINE_DESIGN.md:13-20` | 契约清单 |
| [33] | Minimum seed length is the index `k` | `docs/NATIVE_INDEXED_ENGINE_DESIGN.md:438`; `native/offtarget_engine/src/seed_plan.cpp:130` | 有效种子长度 |
| [34] | Minimum seed count `max_bulge + 1`; range up to `floor(L / k)` | `docs/NATIVE_INDEXED_ENGINE_DESIGN.md:439-440`; `native/offtarget_engine/src/seed_plan.cpp:131-132` | 约束 (1) |
| [35] | `allowed = max_mismatch / (seed_count - max_bulge)` | `docs/NATIVE_INDEXED_ENGINE_DESIGN.md:441`; `native/offtarget_engine/src/seed_plan.cpp:151, 155` | 整除，约束 (2) |
| [36] | Default variant cap is 500 000 | `docs/NATIVE_INDEXED_ENGINE_DESIGN.md:442`; `native/offtarget_engine/include/offtarget/seed_plan.hpp:10` | `kDefaultMaxSeedVariants` |
| [37] | Plan minimises `(estimated_variants, seed_count)` | `docs/NATIVE_INDEXED_ENGINE_DESIGN.md:443`; `native/offtarget_engine/src/seed_plan.cpp:180-190` | 字典序最小 |
| [38] | Behaviour when no guaranteed plan exists | `docs/NATIVE_INDEXED_ENGINE_DESIGN.md:445-452`; `native/offtarget_engine/src/seed_plan.cpp:134-143, 192-197`; `native/offtarget_engine/src/search.cpp:46, 454-462` | 小基因组整段扫描，大基因组退出码 3 |
| [39] | `partition_lengths` | `native/offtarget_engine/src/seed_plan.cpp:54-61` | 尽量均分，余数给前面的段 |
| [40] | `segmented_variant_work` = 窗口数 x `variant_count(k, allowed)` | `native/offtarget_engine/src/seed_plan.cpp:63-69` | 与任务文本 W(s) 写法的差异点 |
| [41] | `variant_count` = sum C(k, c) * 3^c | `native/offtarget_engine/src/seed_plan.cpp:105-121` | 单 k-mer 变体数 |
| [42] | Saturating add/multiply at the cap | `native/offtarget_engine/src/seed_plan.cpp:14-31, 33-44, 46-52` | 溢出返回 `cap + 1` |
| [43] | Variant enumeration over k-mer windows | `native/offtarget_engine/src/seed_plan.cpp:71-95, 239-247` | `visit_variants` / `for_each_seed_variant` |
| [44] | `guaranteed = true` and `estimated_variants` | `native/offtarget_engine/src/seed_plan.cpp:201-205` | 计划成功时置位 |
| [45] | Each segment window is enumerated with the segment allowance | `native/offtarget_engine/src/search.cpp:538-552` | 段内 k-mer 窗口 + `allowed_mismatches` |
| [46] | Candidates are verified against `max_bulge` and `max_mismatch` | `native/offtarget_engine/src/search.cpp:607-625` | 对齐验收门槛 |
| [47] | Worker pool, input-order merge, thread-independent hits | `native/offtarget_engine/README.md:83-86` | 只读共享索引 + 每 worker 独立读取器 |
| [48] | Results assembled by qid, then deduplicated and sorted | `native/offtarget_engine/src/search.cpp:1009-1048` | 确定性合并与排序 |
| [49] | `seed_plan_guaranteed` / `exhaustive_seed_plan` computation | `native/offtarget_engine/src/search.cpp:879, 1015-1016, 1050-1055` | 最长 guide 标记 + 全 guide 合取 |
| [50] | Both markers are emitted in the summary object | `native/offtarget_engine/src/search.cpp:1102-1105` | JSONL summary 字段 |
| [51] | Fixed worker pool, input ordinal, buffered emission in input order | `docs/NATIVE_INDEXED_ENGINE_DESIGN.md:556-563` | 并行规格 |
| [52] | `--max-memory-mb` ceiling and precedence | `native/offtarget_engine/README.md:70-71`; `native/offtarget_engine/include/offtarget/search.hpp:39` | 0 或省略表示无上限 |
| [53] | Preflight estimate + runtime RSS checks + cancellation + no partial JSONL | `native/offtarget_engine/README.md:94-96`; `native/offtarget_engine/include/offtarget/search.hpp:46-50` | 资源边界实现 |
| [54] | Memory-limited outcome cannot fall back to an unrestricted run | `native/offtarget_engine/README.md:72-73` | 显式约束 |
| [55] | Candidate guard error | `native/offtarget_engine/src/search.cpp:1018-1024`; `native/offtarget_engine/include/offtarget/search.hpp:38` | `CANDIDATE_GUARD` / `max_candidates` |
| [56] | Exit-status contract 0/2/3/4/5 | `docs/NATIVE_INDEXED_ENGINE_DESIGN.md:128-132` | CLI 契约 |
| [57] | `auto` sequence-cache criterion | `native/offtarget_engine/README.md:87-91`; `native/offtarget_engine/include/offtarget/search.hpp:61` | 可用内存一半以内才开启 |
| [58] | Search option defaults | `native/offtarget_engine/include/offtarget/search.hpp:22-39` | `max_mismatch=4`、`max_bulge=0`、`pam_side=3prime` |
| [59] | IUPAC PAM bit masks | `native/offtarget_engine/src/pam.cpp:30-67` | A/C/G/T/U/R/Y/S/W/K/M/D/H/V/B/N |
| [60] | `iupac_match` requires a non-empty intersection at every position | `native/offtarget_engine/src/pam.cpp:71-81` | 逐位掩码匹配 |
| [61] | `pam_ok_span` covers both PAM sides and both strands | `native/offtarget_engine/src/pam.cpp:85-110` | 负链匹配反向互补 motif |
| [62] | `pam_sequence_span` reports the PAM in guide orientation | `native/offtarget_engine/src/pam.cpp:112-145` | 负链返回反向互补 |
| [63] | `off_target_specificity = 1 / (1 + sum(CFD))` | `docs/SCORING_GUIDE.md:71` | GuideScan2 风格聚合 |
| [64] | `MM0 ... MMn` bucket semantics | `docs/SCORING_GUIDE.md:20, 219` | 只统计完整 query 长度匹配 |
| [65] | CFD definition and PAM weight handling | `docs/SCORING_GUIDE.md:39, 44` | 错配位置权重 x PAM 权重 |
| [66] | `calibrated_reference` vs `uncalibrated` | `docs/SCORING_GUIDE.md:53-54, 66` | 校准状态传播 |
| [67] | Two PairRank modes | `docs/PAIR_RANKING.md:9-14` | `prediction_only` / `experiment_calibrated` |
| [68] | Pair is the ranking unit; both sides must succeed | `docs/PAIR_RANKING.md:59-61` | 核心原则 1、2 |
| [69] | Conservative pair off-target bound `B_pair+ = B_L+ + B_R+` | `docs/PAIR_RANKING.md:191-194` | 默认保守上界 |
| [70] | `M_pair+ = max(M_L+, M_R+)` and high-risk locus count `H_pair` | `docs/PAIR_RANKING.md:206-215, 228` | 最大单点风险与硬门槛 |
| [71] | `rank_mode = prediction_only` | `docs/PAIR_RANKING.md:132` | 本文使用的模式 |
| [72] | `experiment_calibrated` is not implemented in code | `docs/PAIR_RANKING.md:447` | 仅作为目标契约 |
| [73] | Default `policy_status = uncalibrated` | `docs/PAIR_RANKING.md:485` | 无匹配实验时的标记 |
