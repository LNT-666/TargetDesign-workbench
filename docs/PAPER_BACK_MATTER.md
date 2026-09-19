# 投稿后置要件（Back Matter）

- 小节与顺序（采用 2025 主范本 ALLEGRO，NAR 2025, 53, gkaf783）：
  **Acknowledgements（含 `Author contributions:`）-> Supplementary data -> Conflict of interest -> Funding -> Data availability -> References**。
- 依据：`docs/handoff/nar-format-pack/task.md` 的 C2（round 1 契约 r2，2026-09-19 10:40）；`docs/ALLEGRO_REFERENCE_ANALYSIS.md:85`。
- 顺序选择说明：2024 副范本（CRISPR-COPIES）为 Data availability 在前、Acknowledgements 在后；NAR 两种都接受，
  本包统一按 2025 顺序书写，该选择已在 `docs/NAR_FORMAT_CHECKLIST.md` 第 1 节注明。
- 句式纪律：Supplementary 句只用 2025 写法，不得与 2024 写法混用。
- 更新日期：2026-09-19 10:46；占位符 `[TO FILL]` 表示信息未确定，禁止编造，登记见 `docs/NAR_FORMAT_CHECKLIST.md` 第 2 节。

## Acknowledgements

Author contributions: [TO FILL 按 CRediT 角色逐位填写]

- CRediT 模板（每位作者一行）：`[TO FILL 作者]: Conceptualization, Methodology, Software, Validation, Writing - original draft, Writing - review and editing.`
- 作者信息未定时，整段保持 `[TO FILL]`，不得先填占位姓名。
- 其他致谢（个人、平台、算力支持）：[TO FILL]
- 制图声明：本轮图形摘要为自绘 SVG，不使用 BioRender 等第三方制图服务，因此无需该声明；若最终稿改用第三方服务，须在此补声明并更新 `docs/NAR_FORMAT_CHECKLIST.md` 第 1 节「制图工具」行。

## Supplementary data

Supplementary data is available at NAR online.

- 上述为 2025 主范本句式（task.md C2）。2024 副范本写法 `Supplementary Data are available at NAR Online.` 同样被接受，但两者不得混用；本文件统一使用 2025 写法。
- Supplementary 清单（表号与图号已按 C5 固定，权威清单见 `docs/FIGURE_TABLE_PLAN.md`；状态列待相关交付件定稿）：

| 编号 | 内容 | 来源 | 状态 |
| --- | --- | --- | --- |
| Table S1 | 参数表达力矩阵全表（16 数据行 x 10 列 = 3 个元数据列 tool / year / input_model + 6 个能力列 + 1 个证据列，含判定口径） | `docs/EXPRESSIVENESS_MATRIX.md`、`docs/expressiveness_matrix.tsv`（expr-matrix） | 数据就绪，待排版 |
| Table S2 | 种子计划网格（16 组 `(k, M, B)` 的 `s*`、`W(s)`、guaranteed 与实测时间；原主文 Table 1） | `docs/seed_plan_sweep.json`（engine-bench）、`docs/SEED_PLAN_ANALYSIS.md` | 数据就绪，待排版 |
| Table S3 | 跨引擎基准（exact-match 与 bulge 两表合并，附 1-mismatch 召回） | `example/engine_benchmark_small/REPORT.md` | 数据就绪，待排版 |
| Table S4 | 模型清单、校准状态与复刻误差 | `docs/MODELS.md` | 待排版 |
| Table S5 | 输出字段契约 | `docs/OUTPUTS.md` | 待排版 |
| Notes S1 | 种子计划代价方程与完备性引理的详细数学表述，含实现与规格写法的对应说明（source correspondence）；主文只留结论与引用 | `docs/PAPER_METHODS_DRAFT.md` 2.4 / 2.5 | 待撰写 |
| Notes S2 | `.ggi` v1 索引格式规范 | `docs/NATIVE_INDEXED_ENGINE_DESIGN.md` 及相关源码 | 待撰写 |
| Figure S1 | 案例位点候选分布与 PairRank 分层（原主文 Fig 6 移出主文，内容不删、只改位置） | `scy-test/`（不在 C3 授权来源内，口径 `[TO FILL]`） | 内容就绪，数据 `[TO FILL]`，绘制待做 |

## Conflict of interest

The authors declare that they have no known competing financial interests or personal relationships that could have appeared to influence the work reported in this paper.

- 状态：标准冲突声明，须由全体作者确认后方可定稿；作者名单本身亦为 `[TO FILL]`（见 `docs/PAPER_FRONT_MATTER.md` 作者与单位块）。

## Funding

- Funding body and grant number: [TO FILL]
- 若无外部资助，按主范本惯例替换为：`This research received no external funding.`（选用哪一句由 master 决定，未定前保持 `[TO FILL]`）。

## Data availability

[TO FILL 工具名] is freely available on GitHub at https://github.com/LNT-666/TargetDesign-workbench and on Zenodo at [TO FILL version DOI]. Documentation is provided in the repository under the `docs/` directory. All data used in this study can be obtained from the repository and the Supplementary Data.

- 上述四句结构沿用 task.md C2（2025 主范本写法：GitHub 仓库 URL + Zenodo 版本 DOI + 文档地址 + 数据来源句）；第 3 句的文档地址按本项目仓库形态改写为 `docs/` 路径，见下条。
- 仓库 URL 已确定并核验：`https://github.com/LNT-666/TargetDesign-workbench`（2026-09-19 推送，随后按 master 决定改名；默认分支 `main`，远端树已复核不含大件数据与内部文件）。仓库当前为 **private**，计划论文发表后再转 public 并归档 Zenodo，故 release tag 与版本 DOI 均待届时一并完成，本行另两处仍为 `[TO FILL]`。
- **口径冲突提示**：本句固定句式是 `freely available`，而仓库当前 private；投稿前必须转为 public（或改用受控访问措辞），否则本句与事实不符。
- `<工具名>`：与 `docs/PAPER_FRONT_MATTER.md` 的标题候选一起由 master 定（候选名 `CRISPR-Motif Workbench`）。
- ``Documentation is provided in the repository under the `docs/` directory.``：本项目文档即仓库内 `docs/`（如 `docs/WEBAPP.md`、`docs/GUI.md`、`docs/OUTPUTS.md`），仓库内无独立 wiki，故不保留 wiki 措辞（对应 `docs/handoff/nar-format-pack/review.md` 的改写要求）；若 master 决定另建 wiki，需回改第 3 句。
- 若使用公开基因组或外部数据集，按 2025 惯例补 accession：[TO FILL]（是否适用由 master 判定）。

## 边界

- 本文件只给模板与固定句式，不填任何未知信息，不代替 master 的核验结论。
