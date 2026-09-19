import io, json

def w(p, s):
    io.open(p, "w", encoding="utf-8", newline="\n").write(s)

rv1 = """# 核验报告：expr-matrix

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

编码：三个产物均无 BOM、无 `\\r`、无替换字符。

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
"""

rv2 = """# 核验报告：nar-format-pack

- round: 1
- verdict: pass_with_followups
- updated: 2026-09-19 10:52
- 依据：`report.md`（round 1，契约 r2）+ master 独立探针（`assets/master_verify_pack.py`）
- 特别说明：本任务开工时为 r1 契约，master 在 10:40:06 发布 r2。servant 主动识别并**按 r2 全量重写**，
  master 已复验无 r1 残留（见「契约版本核验」）。

## 逐条核验

| 任务项 | 结论 | 证据 |
| --- | --- | --- |
| C1 摘要 170-250 词、单段、无引用编号、无禁词 | 通过 | master 复测：`ABSTRACT words=221 paragraphs=1 citations=0 forbidden=[]` |
| C2 back matter 2025 顺序 + Author contributions | 通过 | 小节顺序实测 = Acknowledgements -> Supplementary data -> Conflict of interest -> Funding -> Data availability；`Author contributions` 段存在，CRediT 模板齐备 |
| C2 Data availability / Supplementary data 句式 | 通过 | 含 `is available at NAR online`（2025 句式）、含 `Zenodo`、含 `[TO FILL]`；未混用 2024 句式 |
| C3 主文表 = 0、矩阵为主文图 | 通过 | `FIGURE_TABLE_PLAN.md` 明写「主文表：无」并把原 Table 1-5 全部移 Supplementary；矩阵定为 Figure 3 |
| C4 合规对照表 | 通过 | 表体 30 数据行 = 16 项合规 + 13 项待补登记 + 表头行；`[TO FILL]` 登记表可逐条追溯 |
| C5 图形摘要规格 + 草稿 | 通过 | `GRAPHICAL_ABSTRACT_SPEC.md` 含三要素/版式/尺寸/配色/与 Figure 1 区分度/制作方式；SVG 用 ElementTree 解析成功，`viewBox=0 0 941 388` |
| C6 措辞与两篇范本一致 | 通过 | 五个交付件禁词扫描全为空列表 |

## master 独立验证

契约版本核验（r1 残留排查）：

```text
170-250 出现次数 3 ；180-250 出现次数 0
back matter 顺序 = 2025 顺序（见上）
主文表 = 0（FIGURE_TABLE_PLAN.md 第 2 节）
```

图形摘要尺寸的第二数据点（master 用主范本 PDF 自测）：

```text
pdfimages -list ALLEGRO-2025-nar.pdf -> 首页只有 424x514 / 293x448 / 140x385 等 logo 级索引位图
结论：ALLEGRO 的图形摘要为矢量图，无法给出像素尺寸；941x388 仍是唯一实测值（副范本 CRISPR-COPIES）
```

## 归属判定

- 六个文件均为本轮新增；未改任何既有文件。master 复验 mtime 与内容一致。
- 报告「附带发现」里指出的 `task.md` C3 与 §5 冲突，责任在 master（task.md 由我写），已在本次核验中修正。

## master 对 report「待明确」7 条的裁定

1. **主文表 0 还是 1** -> **0 张**。理由：两篇范本均无主文表；servant 按 C3 执行正确（契约优先于 §5 的旧推荐），
   master 已修正 task.md §5 的矛盾句。破例条款保留在 `FIGURE_TABLE_PLAN.md` 备查。
2. **主文图是否压缩** -> **定为 6 张**：Figure 1-6 留主文；Figure 7（案例位点候选分布与 PairRank 分层）
   移入 Supplementary 作为 `Supplementary Figure S1`（内容不删，只改位置）。理由：主范本主文 5 张，
   6 张覆盖 C1/C2 两个头号贡献 + 系统总览，案例图属支撑性证据。
3. **Figure 编号** -> 采纳 `FIGURE_TABLE_PLAN.md` 现有映射（矩阵 = Figure 3，原 Fig 3-6 顺延）；
   Supplementary 侧必须**按正文引用顺序重排**（建议：S1 案例图、S2 跨引擎基准表、S3 种子计划 sweep 表、
   S4-S5 其余表），最终以 engine-bench 交付后的引用顺序为准。
4. **图形摘要尺寸** -> 维持 **941x388（约 2.43:1）**。主范本为矢量图，无量测值可交叉验证；
   「最终尺寸与格式需向期刊确认」的登记保持不变。
5. **wiki 措辞** -> **改写**。本项目没有 wiki：Data availability 的文档地址改为仓库 `docs/` 路径 +
   Supplementary Notes 表述。作为 follow-up 交 `manuscript-v1`。
6. **关键词** -> 保留为可选块并保持 `[TO FILL]`；两篇范本均无该小节，投稿系统若强制再填。
7. **摘要是否补基准数字** -> **不补**。两篇范本摘要均为定性表述；数字进 Results。

## 下一步

- 通过。第 2/3/5 条的落地与 follow-up 全部并入新任务 `docs/handoff/manuscript-v1/task.md`。
"""

w(r"R:\songji\programfile\docs\handoff\expr-matrix\review.md", rv1)
w(r"R:\songji\programfile\docs\handoff\nar-format-pack\review.md", rv2)

def st(slug, status, extra, title):
    d = {
        "task": slug,
        "title": title,
        "status": status,
        "status_values": ["assigned", "implementing", "ready_for_review", "verifying", "needs_rework", "done", "master_takeover"],
        "round": 1,
        "master": "会话 M（master）",
        "servant": "会话 S（servant）",
        "repo": "R:\\songji\\programfile",
        "server_repo": "/home/apool/songji/programfile",
        "local_python": "Python 3.14.7",
        "created": "2026-09-19 09:57",
        "updated": "2026-09-19 10:52",
    }
    d.update(extra)
    return json.dumps(d, ensure_ascii=False, indent=2) + "\n"

w(r"R:\songji\programfile\docs\handoff\expr-matrix\state.json",
  st("expr-matrix", "done",
     {"verdict": "pass_with_followups", "verdict_by": "master",
      "followups": ["F1 EXPRESSIVENESS_MATRIX.md 标题 Table 3 -> Figure 3",
                    "F2 unknown 格需在论文补 limitation 句",
                    "F3 16 vs 17 行口径统一"],
      "followup_owner": "manuscript-v1"}, "参数表达力矩阵（论文 C1 的核心证据）"))

w(r"R:\songji\programfile\docs\handoff\nar-format-pack\state.json",
  st("nar-format-pack", "done",
     {"verdict": "pass_with_followups", "verdict_by": "master",
      "task_md_revision": "r2 (2026-09-19 10:40, master)",
      "contract_r2_reverified": True,
      "followups": ["主文图定 6 张（F7 -> Supplementary S1）", "wiki 措辞改写为仓库 docs/", "Supplementary 按引用顺序重排"],
      "followup_owner": "manuscript-v1"}, "NAR Methods 投稿要件打包（格式规范落地）"))

print("reviews + state written")