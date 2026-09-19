# 投稿前置要件（Front Matter）

- 目标：NAR Methods 栏目（e-locator 在线专发）。范本 CRISPR-COPIES（NAR 2024, 52, e30）。
- 依据：`docs/PAPER_OUTLINE.md` 第二、三、九节；`docs/ALLEGRO_REFERENCE_ANALYSIS.md`（2025 主范本）；`docs/handoff/nar-format-pack/task.md` 的 C1 与 C6（契约版本 r2，2026-09-19 10:40）。
- 更新日期：2026-09-19 10:46。
- 占位符：`[TO FILL]` 表示信息未确定，禁止编造；登记见 `docs/NAR_FORMAT_CHECKLIST.md` 第 2 节。

## 1. 标题候选

范本标题结构为 `名称: 一句话平台定位`（`CRISPR-COPIES: an in silico platform for discovery of ...`），下列候选沿用该结构。

| 候选 | 标题 | 说明 | 状态 |
| --- | --- | --- | --- |
| A（推荐） | `CRISPR-Motif Workbench: a constraint-driven guide design platform with a native indexed off-target engine` | 沿用 `docs/PAPER_OUTLINE.md:128`-`:129`（第三节 Title 小节）的建议句，前半句给设计空间，后半句给引擎 | 待 master 确认 |
| B | `From coordinate queries to motif anchors: a complete design space for CRISPR guide layouts, with an exhaustive-search engine` | 把与既有工具的差别（锚点是 motif 而非坐标区间）提到主标题 | 待 master 确认 |
| C | `CRISPR-Motif Workbench: expressing, enumerating and ranking paired guide layouts from IUPAC motif anchors` | 强调「表达 - 枚举 - 排序」三段流水线，弱化引擎 | 待 master 确认 |

标题规则：禁用「首创 / 首次 / 从未」一类中英文措辞（英文禁用词见 `docs/handoff/nar-format-pack/task.md` 的 C1），也不写实验性结论；物种与工具名大小写沿用 `docs/PAPER_OUTLINE.md` 的写法。

## 2. 作者与单位块（模板）

```text
[TO FILL 作者 1]^1,^[#], [TO FILL 作者 2]^1,2, [TO FILL 作者 3]^2, [TO FILL 作者 4]^1,*

^1[TO FILL 单位全称]，[TO FILL 城市]，[TO FILL 邮编]，[TO FILL 国家]
^2[TO FILL 单位全称]，[TO FILL 城市]，[TO FILL 邮编]，[TO FILL 国家]

^#Present address: [TO FILL 如无则删除本条]

*To whom correspondence should be addressed. Tel: [TO FILL]; Fax: [TO FILL];
Email: [TO FILL]

ORCID iD: [TO FILL 逐位作者按需列出]
```

说明：

- 署名顺序、单位归属、通讯作者、ORCID 均为外部信息，本轮不填、不猜，统一由 master 向用户索取。
- 范本在同一页给通讯作者的联系方式（电话、传真、邮箱），照此保留三个字段。

## 3. 摘要自检（对应 task.md C1）

- 词数：221（统计口径 `[A-Za-z][A-Za-z-]*`），区间按 task.md C1 的 **170-250 词** 判定为通过；命令与输出见 `docs/handoff/nar-format-pack/report.md`。
  同一区间亦见 `docs/PAPER_OUTLINE.md:347` 与 `docs/ALLEGRO_REFERENCE_ANALYSIS.md:81`（2025 主范本摘要 173 词）。
- 结构：单段、无小标题、无引用编号。
- 立场：主张止于「设计空间可表达、可完备枚举」，不含任何暗示做过实验的表述；并显式声明本研究未做实验验证（对应 `docs/PAPER_OUTLINE.md:298`-`:299` 的措辞红线）。
- 禁用措辞：C1 列出的三个英文禁用词与「首创」类中文措辞均未出现（核验命令见 `docs/handoff/nar-format-pack/report.md`）。
- 措辞与 `docs/PAPER_OUTLINE.md` 第二、三节一致：不写「最高效」，引擎表述限定为可证完备、确定性、资源有界。

## Abstract

CRISPR guide design is usually specified as a query against a genomic interval or a gene identifier, so the choices that actually define a design intent - protospacer or target adjacent motif sequence, guide length, strand orientation, and the relative placement of two guides - can only be expressed indirectly, if at all. We present CRISPR-Motif Workbench, a constraint-driven design platform in which a design intent is stated as a set of orthogonal parameters over user-supplied IUPAC motifs, and the resulting design space is defined as the complete set of its solutions. The platform enumerates every genomic occurrence of the anchoring motifs, together with all four strand-orientation combinations of a paired layout, including a three-element layout whose left and right distance ranges are independent. Candidate sites are then evaluated with a native C++20 persistent index engine that synthesizes its seed plan at runtime, reports whether the resulting search is guaranteed to be exhaustive, and returns hits in an order that does not depend on the number of threads. In a capability matrix covering 15 published design tools, none is documented as expressing a sequence-level middle-element constraint together with independent per-side distance ranges. The software offers a desktop interface, a local web interface and a test suite; model scores are reported with an explicit calibration status, and no experimental validation was performed in this study.

## 4. 关键词

- NAR 正刊不要求关键词小节（范本 CRISPR-COPIES 未设该小节）。
- 若投稿系统强制填写，建议：`CRISPR guide design; motif-anchored design space; off-target search; indexed genome engine; design-space expressiveness`。
- 是否必需：[TO FILL]（向期刊确认，登记于 `docs/NAR_FORMAT_CHECKLIST.md` 第 2 节）。

## 5. 与其他交付件的接口

- 摘要中「15 个已发表工具」的口径与证据：`docs/expressiveness_matrix.tsv` 实测 17 行 = 表头 + 16 行数据，即 16 数据行 = 15 个已发表工具 + 本文工作（见 `docs/EXPRESSIVENESS_MATRIX.md`、`docs/expressiveness_matrix.tsv`，expr-matrix 任务产出）。该矩阵在本文中作为主文图 Figure 3（全表明细为 Table S1），编号见 `docs/FIGURE_TABLE_PLAN.md`。
- 摘要中「native C++20 persistent index engine」的措辞若要展开为具体数字，须等 engine-bench 任务交付后由 master 决定；本摘要不写运行时间数字，避免锁定未定稿数据。
- 图形摘要紧随摘要之后，规格见 `docs/GRAPHICAL_ABSTRACT_SPEC.md`。
- 后置要件按 2025 主范本顺序书写（Acknowledgements 含 Author contributions -> Supplementary data -> Conflict of interest -> Funding -> Data availability），见 `docs/PAPER_BACK_MATTER.md`。
