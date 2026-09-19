# 核验报告：nar-format-pack

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
