# 核验报告：expr-matrix

- round: 1
- verdict: pass_with_followups
- updated: 2026-09-19 10:52
- 依据：`report.md`（round 1）+ master 独立复跑（本机 Python 3.14.7）
- 核验方式：纯新增文件，无既有代码改动，故不用备份 diff；改为「master 复跑探针 + 文件级一致性比对」。

## 逐条核验

| 任务项 | 结论 | 证据 |
| --- | --- | --- |
| P0-1 探针 `tools/expressiveness_probe.py` | 通过 | master 复跑：`python tools/expressiveness_probe.py` -> `19/19 checks passed`，exit 0；`--json` -> exit 0，JSON 可解析 |
| P0-2 `docs/expressiveness_matrix.tsv` | 通过 | 16 数据行 x 10 列，首行为 `This work (CRISPR-Motif Workbench)` |
| P0-3 `docs/EXPRESSIVENESS_MATRIX.md` | 通过 | Markdown 表 17 行 = 表头 + 16；与 TSV 的工具集合逐位相同（`tool_sets_equal True`） |
| P1-1 锚点与来源列 | 通过 | 矩阵单元格均为 DOI / 官方文档 URL / 仓库 `文件:行`；`unknown` 格已在 report 中显式列举 |

master 独立复跑原文：

```text
capabilities: custom_pam_tam=True, custom_target_length=True, custom_orientation=True,
middle_element_constraint=True, enumerates_all_occurrences=True, pair_side_independent=True
19/19 checks passed

{"tool": "This work (CRISPR-Motif Workbench)", "custom_pam_tam": true, "custom_target_length": true,
 "custom_orientation": true, "middle_element_constraint": true, "enumerates_all_occurrences": true,
 "pair_side_independent": true, "checks_passed": 19, "checks_total": 19, "ok": true}

tsv_rows 16 tsv_cols 10
md_table_rows 17
tool_sets_equal True
```

编码：三个产物均无 BOM、无 `\r`、无替换字符。

## 归属判定（既有失败 vs 本次引入）

- 三个文件均为本轮新增（mtime 均为 2026-09-19），未触碰 `shared/`、`basic/`、`tools/` 既有文件。
- 不存在「本次引入的既有功能失败」。

## 新发现（转下个任务，不在本轮修）

- **F1 [P3] 编号口径** `docs/EXPRESSIVENESS_MATRIX.md:1` 标题写「/ Table 3」，而 `docs/FIGURE_TABLE_PLAN.md`
  已按 r2 契约把矩阵定为主文 **Figure 3**。归属：master 的编号决策变化（expr-matrix 交付时按旧口径），
  不是 servant 的错。处置：交 `manuscript-v1` 任务统一改（该任务已获该文件写权限）。
- **F2 [P3] 证据强度** 16 个已发表工具行中有 `unknown` 格（DECKO 6 格、GT-Scan 5 格、EuPaGDT 3 格、
  Cas-Designer 2 格、CRISPR multitargeter 2 格、pgRNAFinder 1 格）。Abstract 现用
  `none is documented as expressing ...` 规避绝对化，写法正确；但论文应补一句 limitation，
  说明「未检索到公开文档」不等于「确定不支持」。处置：交 `manuscript-v1`。
- **F3 [P3] 行数与口径** 矩阵 17 行 = 16 个已发表工具 + 本文工作；Abstract 写 `16 published design tools`，
  正文/图注口径需统一，避免审稿人误读。处置：交 `manuscript-v1`。

## 下一步

- 通过。F1-F3 三条 follow-up 已并入新任务 `docs/handoff/manuscript-v1/task.md`。
- 该文件写权限自本条核验起对该任务开放；除此以外不再接受其他改动。
