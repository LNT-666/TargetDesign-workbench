# ALLEGRO（NAR 2025）参考分析

- 来源：`C:\Users\ASUS\Desktop\ALLEGRO-2025-nar.pdf`
- 抽取文本：`R:\songji\论文\3\ALLEGRO-2025-nar.txt`（`pdftotext -layout -enc UTF-8`，99690 字节）
- 文献：Mohseni A, Ghorbani Nia R, Tafrishi A, León López M, Liu X-Z, Stajich JE, Lonardi S, Wheeldon I.
  *Kingdom-wide CRISPR guide design with ALLEGRO.* **Nucleic Acids Research 2025;53:gkaf783.**
  doi:10.1093/nar/gkaf783（栏目 Methods，2025-07-29 接收）
- 抽文本行号引用均为 `ALLEGRO-2025-nar.txt` 的行号

## 1. 它是什么

跨物种最小 sgRNA 文库设计工具：把「用最少的 guide 覆盖多种物种的一组基因」建模为集合覆盖
问题，用整数线性规划（ILP）求解；先经 DIAMOND 求直系同源组，可选 uCRISPR 效率分，
最终给出最小文库（正文 L111-135 的 Computational arrangement）。

它的「策略」是 **track**：`A`（any，每物种任一基因被覆盖 m 次即可）与 `E`（each，每物种每个基因都要被覆盖 m 次），
倍数因子 m 由用户选（L139-150）。

## 2. 它不是什么（对我们最重要的一节）

逐项检索抽文本，以下关键词在全文出现 **0 次**：`IUPAC`、`5′/5-prime`、`k-mer`、`index`、
`suffix array`、`FM-index`、`seed-and-extend`、`command line`。

即：ALLEGRO **没有**自由 PAM/TAM、没有 5′ PAM、没有多长度设计、没有 motif 锚定布局、
没有配对/三元件布局、没有持久化 k-mer 索引、没有种子计划与完备性证明。
它的 PAM 面是单一的 Cas9 体系（另在 Discussion 承认非 Cas9 效应子的 PAM 需要另行定制，见 §4.2）。

## 3. 与我们 C1-C4 的重叠矩阵

| 我们的主张 | ALLEGRO 是否构成先例 | 结论 |
| --- | --- | --- |
| C1 参数层：PAM/TAM、长度、方向自由可配 | 否（单一 Cas9 PAM；且把 PAM 定制写成未做之事） | 维持原有「参数层有先例」判定，先例表本就不靠它 |
| C1 锚定层：以 IUPAC motif 的基因组出现为锚 | 否（它的输入是物种集合与基因/直系同源组，不是 motif 锚点） | 维持「未找到先例」 |
| C1 布局层：三元件 + 左右独立距离区间（Pattern B） | 否 | 维持「未找到先例」 |
| **「提供多种用户可选设计策略」这件事本身** | **是**（track A / track E + 倍数 m） | **必须改写**：新颖性只能落在布局语义，不能落在「有两个模式」 |
| C2 原生索引引擎、种子计划合成 | 否 | 维持 |
| C2「可证无损的候选削减」叙事 | **同类**（L650-654：为避开十亿级候选常驻内存，设计了不影响最优性的启发式） | 可写，但不得写成领域首创；引用它作为同类先例 |
| C2 线程无关确定性、硬内存边界 | 否（它有内存压力叙述，但无确定性/界限契约） | 维持 |
| C3/C4 打分、PairRank | 否（用 uCRISPR 效率分，无脱靶特异性聚合与 pair 排序） | 维持 |

## 4. 三处应当引用它的地方

### 4.1 Introduction 的工具谱系（可用其自带综述）

ALLEGRO 的 Introduction 本身就是一份「多靶点/文库设计」工具小综述，可直接借用其线索并回溯原文：
Endo et al. 2015（利用 PAM-distal 错配容忍做同源基因打靶）、**CRISPR MultiTargeter** [7]、
**CRISPys** [8]、**MINORg** [9]（该文认为当时最有效者）、multiplexed CRISPR 一组 [10-13]。
这些都属「相邻家族」，应补进大纲 §2.1 的先例表。

### 4.2 用它的 Discussion 支撑我们的 gap（顺风引用）

原文 L662-665：

> ... additional considerations may include overlapping genes, operon structures, and
> **organism-specific PAM recognition (e.g. for Cas12a or other non-Cas9 effectors)**.
> Adapting ALLEGRO for bacterial systems may therefore involve **customizing PAM constraints** ...

同一篇 2025 年 NAR 工具把「PAM 需要定制」列为尚未满足的需求 —— 这是我们 C1 缺口表述最有力的外部佐证，
建议在 Introduction 缺口段（a）直接引用。

### 4.3 支撑「可证无损削减」这类叙事的分量

原文 L650-654：为避开十亿级候选常驻内存而设计的启发式「without affecting the optimality of the solution」。
引用它可以让我们的种子计划完备性引理读起来是该领域**公认有价值的一类贡献**，而不是作者自说自话。

## 5. 措辞红线（本文件的核心结论）

- 不得写：`Our tool is the first to provide multiple user-selectable design strategies.`
  / `两个模式从未有过` —— ALLEGRO 的 track 机制已构成反例。
- 可以写：新颖性在**布局层**——「以序列级布局（motif 锚点 + 每侧独立距离区间 + Y 约束）而非坐标区间
  来描述成对设计」，并沿用大纲 §2.3 已定的 to our knowledge 句式。
- 不得写：`first to reduce candidate enumeration without loss`；可写 `we prove completeness of the
  enumerated seed plan`（有引理撑腰，见 `docs/PAPER_METHODS_DRAFT.md` 2.4/2.5）。

## 6. 格式规范增量（相对 CRISPR-COPIES / gkae062，NAR 2024）

同为 Methods 栏目、含 Graphical abstract，但 2025 这一篇给出了更细的落点：

| 项目 | ALLEGRO (2025) | CRISPR-COPIES (2024) | 我们的处置 |
| --- | --- | --- | --- |
| 摘要词数 | **173**（抽文本统计） | 206 | 区间放宽为 **170-250** |
| 主文图 | Figure 1-5（正文 25 处 Figure 引用） | 19 处 Figure 引用 | 主文图 5-6 张可用 |
| 主文表 | 无；表一律 `Supplementary Table Sn` | 无 | 维持「主文不加表」 |
| 章节顺序 | Abstract → Graphical abstract → Introduction → Materials and methods → Results → Discussion → ... | 同 | 同 |
| Back matter 顺序 | Acknowledgements（含 **Author contributions:**） → Supplementary data → Conflict of interest → Funding → Data availability → References | Data availability → Supplementary data → Acknowledgements → Funding → Conflict of interest | **改用 2025 顺序**；`PAPER_BACK_MATTER.md` 需增 Author contributions 段 |
| Supplementary data 句式 | `Supplementary data is available at NAR online.` | `Supplementary Data are available at NAR Online.` | 两种都可用，按 2025 句式为主 |
| Data availability 写法 | **给出 GitHub + Zenodo DOI + 文档地址 + NCBI accession** | 通用句式（within the article and its Supplementary Data files...） | 采用 2025 写法：仓库 URL + 版本 DOI + 文档，未定项 `[TO FILL]` |
| 数学公式放置 | 详细数学表述放 **Supplementary Notes**（L149、L324 提到 Notes S1.6） | 无此惯例 | 支撑我们把「源码对照说明」移入 Supplementary note S1 的裁定 |
| 竞品比较 | 与 MINORg 比文库大小/RAM/时间（L660-662） | 与既有工具比 | 我们的引擎基准（engine-bench 任务）同级做法 |

## 7. 落地动作

- `docs/PAPER_OUTLINE.md`：§2.1 先例表增 ALLEGRO/MINORg/CRISPys/multicrispr；增设 2.1.1「ALLEGRO 定位」；
  §2.3 增一条被否措辞；§9 改为双范本并更新表与规则。
- `docs/handoff/nar-format-pack/task.md`：摘要词数改 170-250；back matter 改 2025 顺序并增
  Author contributions；Data availability 改仓库+DOI 句式；自检阈值同步。
- `docs/handoff/methods-draft/review.md` 的裁定不受影响（对照说明移入 Supplementary 反而得到 2025 先例支持）。