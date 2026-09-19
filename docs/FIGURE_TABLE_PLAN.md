# 主文图/表最终清单（Figure & Table Plan）

- 约束来源：`docs/handoff/manuscript-v1/task.md` 的 C5/C6（round 1，master 裁定编号，**不得改号**）；沿用 `docs/handoff/nar-format-pack/task.md` 的 C3「主文表 = 0」与「表达力矩阵是主文图」；`docs/ALLEGRO_REFERENCE_ANALYSIS.md` 第 6 节。
- 更新日期：2026-09-19（manuscript-v1 round 1：编号由暂定值改为固定值，状态列按实际交付状态改写）。
- 编号权威性：本清单是主文图与 Supplementary 图表的编号唯一权威。`docs/PAPER_OUTLINE.md` 第四节的旧编号仅作历史对照，见下方映射表。
- 两条硬约束：**主文表 = 0**；**表达力矩阵是主文图 Figure 3，不是表**。
- 状态口径：`数据就绪`；`内容就绪`（正文/图注已写，仅差绘制）；`绘制待做`；`[TO FILL]`。

## 1. 主文图清单（6 张）

Figure 1 — 总体架构与数据流（pattern 定义 -> 候选提取 -> 脱靶搜索 -> 评分 -> 导出） — 来源：`docs/PAPER_METHODS_DRAFT.md` 2.1-2.3、2.8 — 状态：内容就绪，绘制待做 — 引用位置：`docs/PAPER_DRAFT.md` Introduction
Figure 2 — 三类 pattern 的形式化示意与四种链向组合（++ / +- / -+ / --） — 来源：`docs/design_patterns_en.md`、`Target_xbp_Target/extract_complex_queries.py:103-108` — 状态：内容就绪，绘制待做 — 引用位置：`docs/PAPER_DRAFT.md` Introduction
Figure 3 — 参数表达力矩阵（16 数据行 = 15 个已发表工具 + 本文工作；6 个能力列 + 3 个元数据列 + 1 个 evidence 列 = 10 列） — 来源：expr-matrix（`docs/expressiveness_matrix.tsv`、`docs/EXPRESSIVENESS_MATRIX.md`） — 状态：数据就绪，绘制待做 — 引用位置：`docs/PAPER_RESULTS_DRAFT.md` 第 1 小节
Figure 4 — 原生索引内存布局（偏移表 + 位置数组 + u4/u8 分界） — 来源：`native/offtarget_engine/include/offtarget/genome_index.hpp`、`docs/NATIVE_INDEXED_ENGINE_DESIGN.md`、`docs/PAPER_METHODS_DRAFT.md` 2.3 — 状态：内容就绪，绘制待做 — 引用位置：`docs/PAPER_RESULTS_DRAFT.md` 第 2 小节（C5 规定：Figure 4 的引用位置放在 Results 的「完备枚举与剪枝」小节）
Figure 5 — 种子计划划分示意（含 bulge 抽屉原理） — 来源：engine-bench（`docs/seed_plan_sweep.json`、`docs/SEED_PLAN_ANALYSIS.md`）、`native/offtarget_engine/src/seed_plan.cpp:123-206` — 状态：数据就绪，绘制待做 — 引用位置：`docs/PAPER_RESULTS_DRAFT.md` 第 3 小节
Figure 6 — 线程扩展曲线 — 来源：`docs/NATIVE_INDEXED_BENCHMARK.md` — 状态：数据就绪，绘制待做 — 引用位置：`docs/PAPER_RESULTS_DRAFT.md` 第 4 小节

Supplementary 图：Figure S1 — 案例位点候选分布与 PairRank 分层 — 来源：`scy-test/`（当前不在 C3 授权来源内，数据口径 `[TO FILL]`） — 状态：内容就绪，数据 `[TO FILL]`，绘制待做 — 引用位置：`docs/PAPER_RESULTS_DRAFT.md` 第 7 小节

主文图规模说明：定为 **6 张**。主范本 ALLEGRO（NAR 2025）主文为 Figure 1-5，`docs/ALLEGRO_REFERENCE_ANALYSIS.md:82` 记「主文图 5-6 张可用」。原第 7 张（案例位点候选分布与 PairRank 分层）按 C5 移出主文，作为 `Supplementary Figure S1`（内容不删，只改位置）。

编号映射（对照 `docs/PAPER_OUTLINE.md` 第四节，旧编号只作历史对照）：

| 原编号 | 现编号 | 变化 |
| --- | --- | --- |
| Fig 1 | Figure 1 | 不变 |
| Fig 2 | Figure 2 | 不变 |
| （新增） | Figure 3 | 表达力矩阵由「原 Table 3」改为图，插在 Figure 2 之后 |
| Fig 3 | Figure 4 | 顺延 |
| Fig 4 | Figure 5 | 顺延 |
| Fig 5 | Figure 6 | 顺延 |
| Fig 6 | Supplementary Figure S1 | 移出主文，内容不删 |

正文引用顺序（C5 要求按编号升序出现）：

| 编号 | 引用位置 |
| --- | --- |
| Figure 1 | `docs/PAPER_DRAFT.md` Introduction |
| Figure 2 | `docs/PAPER_DRAFT.md` Introduction |
| Figure 3 | `docs/PAPER_RESULTS_DRAFT.md` 第 1 小节「Motif-anchored design space and expressiveness」 |
| Figure 4 | `docs/PAPER_RESULTS_DRAFT.md` 第 2 小节「Complete enumeration and pruning for paired layouts」 |
| Figure 5 | `docs/PAPER_RESULTS_DRAFT.md` 第 3 小节「Seed-plan cost curve and completeness」 |
| Figure 6 | `docs/PAPER_RESULTS_DRAFT.md` 第 4 小节「Cross-engine benchmark and recall honesty」 |
| Figure S1 | `docs/PAPER_RESULTS_DRAFT.md` 第 7 小节「Case sites: AAVS1, TRAC and PDCD1」 |

Methods 引用约束：C5 规定 Methods 只引用 Figure 1 与 Figure 2。`docs/PAPER_METHODS_DRAFT.md`（本任务只读，未改）当前不含任何图表引用，故该约束在现状下自动满足；Figure 1 与 Figure 2 的引用位置落在 Introduction，升序不受影响。

## 2. 主文表清单（主文表 = 0）

主文表：无。依据 C5（沿用 nar-format-pack C3；两篇范本均无主文表）与 `docs/ALLEGRO_REFERENCE_ANALYSIS.md:83`。破例条款已关闭：C5 维持 0 张，不设破例。

原计划的主文表全部移入 Supplementary，编号按正文引用顺序固定（C5）：

Table S1 — 参数表达力矩阵全表（16 数据行 x 10 列，保留 `evidence` 列） — 来源：`docs/expressiveness_matrix.tsv`；表体见 `docs/PAPER_TABLES_SUPP.md` — 状态：数据就绪，待排版 — 引用位置：Results 第 1 小节
Table S2 — 种子计划网格（16 组 `(k, M, B)` 的 s*、W(s)、guaranteed 与实测时间） — 来源：engine-bench（`docs/seed_plan_sweep.json`、`docs/SEED_PLAN_ANALYSIS.md`） — 状态：数据就绪，待排版 — 引用位置：Results 第 3 小节
Table S3 — 跨引擎基准（exact-match 与 bulge 两表合并，附 1-mismatch 召回） — 来源：`example/engine_benchmark_small/REPORT.md` — 状态：数据就绪，待排版 — 引用位置：Results 第 4 小节
Table S4 — 模型清单、校准状态与复刻误差 — 来源：`docs/MODELS.md` — 状态：数据就绪，待排版 — 引用位置：Results 第 6 小节
Table S5 — 输出字段契约 — 来源：`docs/OUTPUTS.md` — 状态：数据就绪，待排版 — 引用位置：Results 第 8 小节

## 3. 原 Table 1-5 逐条判定（现编号已按 C5 固定）

| 原编号 | 原内容（`docs/PAPER_OUTLINE.md` 第四节） | 判定 | 现编号 | 依据 |
| --- | --- | --- | --- | --- |
| Table 1 | 种子计划在不同 (M, B, L) 下的 s* 与 W | 移 Supplementary | Table S2 | C5 固定的 Supplementary 表顺序 |
| Table 2 | 跨引擎基准 | 移 Supplementary | Table S3 | C5 固定的 Supplementary 表顺序 |
| Table 3 | 参数表达力矩阵 | 改为主文图；全表明细进 Supplementary | Figure 3 + Table S1 | C5：表达力矩阵为主文图 |
| Table 4 | 模型清单、校准状态与复刻误差 | 移 Supplementary | Table S4 | C5 |
| Table 5 | 输出字段契约 | 移 Supplementary | Table S5 | C5 |

合并项：无。Supplementary 表与图的完整清单见 `docs/PAPER_BACK_MATTER.md` 的 Supplementary data 小节；表体由 `docs/PAPER_TABLES_SUPP.md` 提供，图注由 `docs/PAPER_FIGURE_CAPTIONS.md` 提供。

## 4. 边界与依赖

- 本轮只出清单、图注与表体，不绘图、不生成最终美术稿。
- Figure 3 的口径写死为 `docs/expressiveness_matrix.tsv`：16 数据行 = 15 个已发表工具 + 本文工作；6 个能力列（`custom_pam_tam` / `custom_target_length` / `custom_orientation` / `middle_element_constraint` / `enumerates_all_occurrences` / `pair_side_independent`），另有 3 个元数据列（`tool` / `year` / `input_model`）与 1 个 `evidence` 列，共 10 列。图注必须写明 `unknown` 不等于 `no`（已在 `docs/PAPER_FIGURE_CAPTIONS.md` 的 Figure 3 写明）。
- Figure 4、Figure 5、Figure 6 与 Table S2、Table S3 的数字口径以 `docs/seed_plan_sweep.json`、`docs/SEED_PLAN_ANALYSIS.md`、`docs/NATIVE_INDEXED_BENCHMARK.md`、`example/engine_benchmark_small/REPORT.md` 为准；engine-bench 遗留件已由 `docs/SEED_PLAN_ANALYSIS.md` 补交。
- Figure S1 的数据来源 `scy-test/` 不在 C3 的授权来源内，图注与 Results 对应小节均以 `[TO FILL]` 标记，待 master 裁定是否授权该来源。
- 图形摘要不计入 Figure 编号，其规格见 `docs/GRAPHICAL_ABSTRACT_SPEC.md`。
