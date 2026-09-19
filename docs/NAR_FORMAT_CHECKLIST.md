# NAR 投稿格式合规对照表（Methods 栏目）

- 规范来源：`docs/PAPER_OUTLINE.md` 第九节（双范本）+ `docs/ALLEGRO_REFERENCE_ANALYSIS.md` 第 6 节。
  主范本 ALLEGRO（NAR 2025, 53, gkaf783，Methods，在线专发）；副范本 CRISPR-COPIES（NAR 2024, 52, e30，17 页）。
- 本表产出任务：`docs/handoff/nar-format-pack/task.md`（round 1；契约版本 r2，2026-09-19 10:40）。
- 更新日期：2026-09-19 10:46。
- 状态口径：`done` = 已有可交付件；`pending` = 待补，但路径已明确；`blocked` = 依赖外部信息或第三方回复；`n/a` = 本项目不适用。
- 占位符口径：`[TO FILL]` = 信息尚未确定，禁止编造；逐项登记见本文件第 2 节。

## 1. 逐条对照（覆盖 PAPER_OUTLINE.md 第九节表格 13 项 + 3 条 2025 主范本增量规则）

| 要求 | 现状 | 归属（任务或 master） | 状态 |
| --- | --- | --- | --- |
| 栏目为 Methods（e-locator 在线专发，非 Standard Article，非 Web Server 专刊） | 已在 `docs/PAPER_OUTLINE.md:9`-`:11` 定案；投稿系统内的栏目选择与提交动作未做 | master | done |
| 篇幅 17 页（含图、表与参考文献，2024 副范本参考值） | 全文尚未成稿，无逐节页数预算；本轮不产生正文 | master | pending |
| 摘要 170-250 词、单段、无小标题、无引用编号 | 草稿见 `docs/PAPER_FRONT_MATTER.md` 的 Abstract 小节，实测 221 词，落在区间内；词数统计命令与输出记于 `docs/handoff/nar-format-pack/report.md` | nar-format-pack | done |
| Graphical abstract（独立小节，紧随摘要） | 规格见 `docs/GRAPHICAL_ABSTRACT_SPEC.md`，草稿见 `docs/assets/graphical_abstract_draft.svg`；最终美术稿与最终尺寸未定 | nar-format-pack（规格与草稿）+ master（最终稿与尺寸确认） | pending |
| 参考文献约 78 条（2024 副范本规模参考） | 尚未建立参考文献表 | master | pending |
| 图是主要证据载体（2024 副范本 19 处 Figure 引用；主范本 2025 主文 Figure 1-5 + Supplementary Fig S1-S10） | 主文图清单见 `docs/FIGURE_TABLE_PLAN.md`（暂定 Figure 1-7，另加图形摘要）；是否压缩到 5-6 张待 master 决定 | nar-format-pack（清单）+ master（绘制与压缩裁定） | pending |
| 主文表 = 0（两篇范本均无主文表；确有需要时最多 1 张，其余一律进 Supplementary） | `docs/FIGURE_TABLE_PLAN.md` 判定原 Table 1-5 全部移 Supplementary；若 master 破例保留 1 张，首选原 Table 1（见该文件§2 的冲突说明） | nar-format-pack | done |
| 章节顺序 Abstract -> Graphical abstract -> Introduction -> Materials and methods -> Results -> Discussion -> ... | `docs/PAPER_OUTLINE.md:325`（第九节章节顺序行）已给出该顺序，Materials and methods 在 Results 之前；本轮不产生正文 | master | done |
| 子标题为无编号描述性短语 | 约束已记于 `docs/PAPER_OUTLINE.md:351`-`:352`（9.1 第 4 条）；`docs/PAPER_METHODS_DRAFT.md` 仍在 round 2 修订，编号清理尚未验收 | methods-draft | pending |
| Discussion 连续散文、无子标题 | 正文未成稿 | master | pending |
| Data availability 采用 2025 主范本写法（GitHub 仓库 URL + Zenodo 版本 DOI + 文档地址 + 数据来源句） | `docs/PAPER_BACK_MATTER.md` 的 Data availability 段已套用四句结构，未定项记 `[TO FILL]`；`Author contributions` 归入 Acknowledgements | nar-format-pack | done |
| Supplementary data 固定句式（2025 主范本：`Supplementary data is available at NAR online.`） | `docs/PAPER_BACK_MATTER.md` 已用 2025 句式，并列出 Supplementary 清单；与 2024 句式不得混用 | nar-format-pack | done |
| 制图工具 BioRender 并在 Acknowledgements 声明 | 本项目不使用 BioRender：图形摘要草稿为自绘 SVG，无外部依赖；若最终改用第三方制图服务，须在 Acknowledgements 补声明 | nar-format-pack（现状记录）+ master（最终决定） | n/a |
| 【2025 增量】Back matter 顺序改用主范本顺序 Acknowledgements（含 Author contributions）-> Supplementary data -> Conflict of interest -> Funding -> Data availability -> References | 本包按该顺序书写（`docs/PAPER_BACK_MATTER.md`）；2024 副范本顺序为 Data availability 在前、Acknowledgements 在后，NAR 两种都接受 —— **本行即为该选择的书面注明** | nar-format-pack | done |
| 【2025 增量】Acknowledgements 必须含 `Author contributions:` 段，按 CRediT 角色逐位写 | `docs/PAPER_BACK_MATTER.md` 的 Acknowledgements 段已给出 CRediT 模板，作者未知处记 `[TO FILL]` | nar-format-pack（模板）+ master（补齐） | pending |
| 【2025 增量】数学表述（如种子计划代价方程与引理证明）放 Supplementary Notes，主文只留结论与引用 | 已写入 `docs/PAPER_BACK_MATTER.md` 的 Supplementary 清单（Notes S1）；`docs/PAPER_METHODS_DRAFT.md` 的相关安排归 methods-draft | methods-draft | pending |

## 2. 待补项登记（`[TO FILL]` 清单）

| 待补项 | 出现位置 | 归属（任务或 master） | 状态 |
| --- | --- | --- | --- |
| 作者名单与署名顺序 | `docs/PAPER_FRONT_MATTER.md` 作者与单位块 | master（需用户提供） | blocked |
| 单位全称与地址 | `docs/PAPER_FRONT_MATTER.md` 作者与单位块 | master（需用户提供） | blocked |
| 通讯作者、邮箱、电话/传真、ORCID | `docs/PAPER_FRONT_MATTER.md` 作者与单位块 | master（需用户提供） | blocked |
| 工具正式名称（Data availability 句首 `<工具名>`） | `docs/PAPER_BACK_MATTER.md` Data availability | master（与标题候选一起定） | blocked |
| 基金机构与基金编号 | `docs/PAPER_BACK_MATTER.md` Funding | master（需用户提供） | blocked |
| GitHub 仓库 URL 与 release tag | `docs/PAPER_BACK_MATTER.md` Data availability | master（需用户提供） | blocked |
| Zenodo 版本 DOI | `docs/PAPER_BACK_MATTER.md` Data availability | master（需用户提供） | blocked |
| 文档地址（wiki 或仓库 `docs/` 路径） | `docs/PAPER_BACK_MATTER.md` Data availability | master（需用户确认 wiki 措辞是否保留） | blocked |
| 公开数据集 accession（若适用） | `docs/PAPER_BACK_MATTER.md` Data availability | master（判定是否适用） | blocked |
| Author contributions 逐位 CRediT 角色 | `docs/PAPER_BACK_MATTER.md` Acknowledgements | master（需用户提供） | blocked |
| 图形摘要最终尺寸与文件格式 | `docs/GRAPHICAL_ABSTRACT_SPEC.md` 尺寸小节 | master（需向期刊确认；主范本 PDF 不在本机） | blocked |
| 摘要字数上限与页数/图表数上限 | `docs/PAPER_FRONT_MATTER.md` 摘要自检小节 | master（OUP 站点 2026-09-19 返回 403，未能核实） | blocked |
| 关键词是否必需 | `docs/PAPER_FRONT_MATTER.md` 关键词小节 | master（需向期刊确认） | blocked |

## 3. 本轮边界

- 本轮只新增格式类文档与图形摘要草稿，不改任何代码、不改既有 `.md`（见 `task.md` 第 0 节的占用清单）。
- 本表只登记状态，不代替 master 的核验结论；核验见 `docs/handoff/nar-format-pack/review.md`。
