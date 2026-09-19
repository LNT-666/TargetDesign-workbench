# 任务：Materials and Methods 章节英文初稿（含引理与证明）

- task-slug: `methods-draft`
- round: 1
- master: 会话 M（master）
- servant: 会话 S（servant）
- repo: `R:\songji\programfile`
- 本地环境：`python` = Python 3.14.7（本任务不需要运行代码，只需读源码）
- 基线快照：本任务只新增一个文件，无需快照
- 上位文档：`docs/PAPER_OUTLINE.md` 第三节「2 Materials and Methods」

## 0. 目标与边界

背景：论文需要一节可直接使用的英文 Methods，其中最值钱的是**种子计划合成的完备性引理**。
目标期刊 Nucleic Acids Research 正刊（结构固定：Methods 在 Results 之前）。

要做到：新增 `docs/PAPER_METHODS_DRAFT.md`，英文、可直接进论文的 Methods 初稿，
每条技术陈述可回溯到本仓库的 `文件:行`。

不做：不改任何代码/文档/fixture；不写 Introduction / Results / Discussion / Abstract；
不编造性能数字；不声称首创。

## 1. 规则 / 契约（唯一权威版本，servant 不需要重新调研规则）

```text
C1  语言：正文英文。中文只允许出现在文末「Anchor table」的说明列。
C2  必含小节，顺序固定：
    2.1 Design specification
    2.2 Motif-anchored layouts and strand enumeration
    2.3 Index format
    2.4 Seed-plan synthesis（含 Algorithm 1 伪码块）
    2.5 Lemma 1 (completeness) and proof
    2.6 Deterministic parallelism
    2.7 Resource bounds
    2.8 Calibration-state propagation and pair ranking
C3  每条技术陈述后加上标编号 [n]；文末 Anchor table 逐条给出 文件:行。
C4  引理的陈述必须与 native/offtarget_engine/src/seed_plan.cpp 的实际实现一致。
    master 已读源码，关键事实如下（servant 必须逐条回读源码核对再落笔；
    若与源码不符，以源码为准并在文中标注差异）：
      - minimum_seed_len = kmer_size（即 k）
      - max_seed_count     = probe_len / k
      - minimum_seed_count = max(1, max_bulge + 1)
      - 对每个候选 seed_count s：allowed = max_mismatch / (s - max_bulge)（整除）
      - 分段长度来自 partition_lengths(probe_len, s)
      - 单段代价 segmented_variant_work(size, k, allowed)
          = sum_{c=0..allowed} C(size, c) * 3^c
      - 以 (total_variants, seed_count) 字典序最小者为最优方案
      - 找不到可行方案时回退为「整段 + 全预算」，且不置 guaranteed，附原因字符串
C5  禁止出现：first / never / 首创 / unprecedented 等独创性主张；
    禁止编造或估算性能数字——需要数字处写占位符 [TIME] / [RATIO] / [N]，
    并在文首统一说明这些占位符来自 Results 章节。
C6  输出文件只有一个：docs/PAPER_METHODS_DRAFT.md
```

## 2. 现状证据（master 已核实，可直接引用）

- `native/offtarget_engine/src/seed_plan.cpp` — `build_seed_plan`、`capped_add`、`capped_mul`、
  `binomial`、`power_three`、`segmented_variant_work`、`partition_lengths`、`encode_kmer`、`for_each_seed_variant`
- `native/offtarget_engine/include/offtarget/genome_index.hpp` — `kIndexFormatVersion = 1`、
  `kIndexMagic = "CRISPRGGI"`、`ContigRecord`、`offset_count() = (1 << (2k)) + 1`、
  `position_dtype()` 返回 `"u4"` / `"u8"`、`index_bytes()`、`metadata_fingerprint()`
- `native/offtarget_engine/include/offtarget/search.hpp` — `SearchOptions`（max_mismatch、max_bulge、seed_len、
  require_pam、pam、pam_side、threads、cache_genome、max_memory_mb）、`SearchSummary`
  （guides/hits/candidates/search_time_s/memory_peak_mb/estimated_peak_mb/observed_peak_mb/
  seed_plan_guaranteed/exhaustive_seed_plan/sequence_cache）、`auto_sequence_cache_fits`
- `native/offtarget_engine/src/pam.cpp` — `iupac_mask` 位掩码（A/C/G/T/U/R/Y/S/W/K/M/D/H/V/B/N）、
  `iupac_match`、`pam_ok_span`、`pam_sequence_span`（3prime/5prime × 双链）
- `native/offtarget_engine/README.md` — 原文：`Results are merged in input order, so the hit sequence is
  deterministic and identical across --threads values`；`k=8..12` 支持范围；
  `A native MEMORY_LIMIT_EXCEEDED result is never allowed to fall back to an unrestricted Python run`
- `docs/NATIVE_INDEXED_ENGINE_DESIGN.md` — 退出码表（0/2/3/4/5）、CLI 契约、7 条设计决策
- `shared/design/pattern_spec.py` — `PatternKind` 三类、`MotifSpec(sequence, flank_length, side)`、
  `_IUPAC_BASES = set("ACGTUNRYSWKMBDHV")`、距离区间校验
- `docs/design_patterns_en.md` — 四种链向组合 `++ / +- / -+ / --`、`left_target_start/end` 与
  `right_target_start/end` 的 0-based half-open 语义
- `docs/PAIR_RANKING.md` — `prediction_only` / `experiment_calibrated`、`B_pair+ = B_L+ + B_R+`
- `docs/SCORING_GUIDE.md` — 特异性聚合 `1 / (1 + sum(CFD))`、MM 桶语义、
  `calibrated_reference` 与 `uncalibrated` 的判定
- master 实测：search 的 summary 行确实带 `seed_plan_guaranteed` 与 `exhaustive_seed_plan` 布尔字段

## 3. 必做改动

- [ ] P0-1 `docs/PAPER_METHODS_DRAFT.md`（新增）：按 C2 的 8 个小节写英文初稿
  - 证据要求：文末 Anchor table 覆盖每一个上标编号
- [ ] P0-2 Algorithm 1（Seed-plan synthesis）伪码块，与 `seed_plan.cpp` 逐行对应
- [ ] P0-3 Lemma 1 的「假设—结论—证明」三段式，证明用抽屉原理，并说明
  `seed_plan_guaranteed` / `exhaustive_seed_plan` 两个标记的语义
- [ ] P1-1 2.2 节形式化 `S = (L, P, l, o, s)` 与设计空间 `D(S)`，并说明四链向组合

## 4. 不要做的事

- 不改任何代码、文档、fixture（本任务只新增一个文件）
- 不写 Introduction / Results / Discussion / Abstract
- 不编造或估算性能数字（一律用占位符）
- 不使用 first / never / 首创 / unprecedented 类措辞
- 不引用 task.md §2 未列出的代码行为（若需引用新行为，先在 report 的「待明确」提出）

## 5. 决策项（未确认则按推荐执行）

- 引理的严格程度 → 推荐三段式「假设—结论—证明」，只用抽屉原理，不做更复杂的组合论证
- 符号 → 推荐 L = guide length、M = max substitutions、B = max bulges、
  k = k-mer size、s = seed count、W(s) = enumeration work
- 占位符 → 推荐 `[TIME]` / `[RATIO]` / `[N]`，并在文首加一行统一说明
- 是否写 2.8 的 PairRank 公式 → 推荐只写定义与保守上界，不展开实验校准细节

## 6. 轻量自检（servant 的检验上限）

```powershell
cd R:\songji\programfile
python -c "d=open(r'docs\PAPER_METHODS_DRAFT.md',encoding='utf-8').read();print('chars',len(d));print('sections',d.count('### 2.'));print('anchor_rows',d.count('| ['))"
```

预期：`sections` 为 8；`anchor_rows` >= 25；无 `first`/`never` 字样。

## 7. 交付要求

- 完成后：`state.json` 置 `ready_for_review` 并更新 `updated`，写 `report.md`
- `report.md` 必填：改动文件+行号表格、自检命令原文与输出、未做项及原因、附带发现（只记录不修）、待明确项
- 不要自己裁定「通过」；核验归 master


## 8. round 2 补充（master，2026-09-19 10:55）

本轮**只做 `review.md`「下一步（最小修复清单）」的三条**，不扩大范围：

1. `docs/PAPER_METHODS_DRAFT.md:396` —— [40] 行「陈述」列的中文写法改英文（与其余行同语种）。
2. `docs/PAPER_METHODS_DRAFT.md:357` —— [1] 行锚点 `docs/PAPER_OUTLINE.md:123` 改为
   `docs/PAPER_OUTLINE.md:126`，并补 `shared/design/guide_design.py:54-67, 183-192`，同步该行说明列。
3. `docs/PAPER_METHODS_DRAFT.md:212-219` —— 「Note on source correspondence」整段移出正文，
   放到文末新开的 `## Supplementary note S1`，并把 [40] 行的说明列改为指向 S1。

可选（不阻塞）：N1 PAM 措辞（enforcement 是 opt-in，`native/offtarget_engine/include/offtarget/search.hpp:32`
的 `require_pam=false`，由 `main.cpp:256` 在 CLI 层开启）、N2 引理作用域加一句。

round 2 自检下限：重跑 `assets/master_verify_anchors.py` 与 `assets/master_verify_text.py`，要求
`PROBLEMS=[]`、`rows_with_cjk_outside_note=[]`、`cjk_in_body=0`，八个 `### 2.x` 顺序不变。

交付：改完把 `state.json` 置 `ready_for_review`（`round: 2`、更新 `updated`），在 `report.md` **追加** round 2 小节
（不覆盖 round 1 内容）。核验仍归 master。
