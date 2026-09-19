# 论文大纲（Nucleic Acids Research 投稿）— 无实验版

检查日期：2026-09-19。本文是投 NAR 正刊的写作大纲、新颖性边界与证据索引。
事实来源为本仓库代码与 `docs/`；文献核查渠道为 Europe PMC（2026-09-19）。
配套文件：有实验版见 `docs/PAPER_OUTLINE_WITH_EXPERIMENTS.md`（两版差异对照见该文件 §0）。

## 零、投稿决策

- 赛道：**NAR Methods**（在线专发，e-locator），不投 Web Server 专刊。
  参照对象：CRISPR-COPIES（NAR 2024, 52, e30, doi:10.1093/nar/gkae062）——同为带 web
  界面的工具类工作，即按 Methods 栏目发表。格式规范见第九节。
  理由：Web Server 专刊篇幅极短，C2（原生索引引擎）只能压成一段；且专刊要求
  公网可访问并承诺长期维护的服务器。`webapp/` 作为可用性 artifact 附带即可。
- 投稿前必须核对官网的待确认项（本次 OUP 站点对自动访问返回 403，未能核实）：
  - Abstract 字数上限
  - 页数／图表数限制
  - 订阅路线是否收费，OA 路线 APC 数额
  - 若改投 Web Server 专刊：截止日期与篇幅上限
- 时间参考：正刊无截止。若改投 Web Server 专刊，窗口约为每年 2 月中旬截止、
  7 月 1 日见刊。

## 一、贡献定位

| 编号 | 贡献 | 定位 | 新颖性 |
| --- | --- | --- | --- |
| C1 | 声明式的引导定义空间：正交自由参数 + motif 锚定 + 三元件布局，输出完备解集 | 头号 | 分层，见 1.1 |
| C2 | 原生 C++20 持久化索引引擎：自动种子计划合成（含完备性引理）、确定性并行、硬资源边界 | 头号 | 算法层新颖 |
| C3 | PairRank：双侧必成约束下的保守排序（prediction_only / experiment_calibrated） | 支撑 | 未找到先例 |
| C4 | 已发表深度模型的可移植 NumPy 复刻 + 校准状态显式传播 | 支撑 | 工程与复现性 |

### 1.1 C1 的三层拆解（本论文最关键的一处措辞）

| 层次 | 内容 | 先例 |
| --- | --- | --- |
| 参数层 | PAM/TAM × 靶长度 × 方向 正交自由 | **有先例**，必须承认（Cas-Designer、FlashFry、CRISPRitz、sgRNA Scorer 2.0） |
| 锚定层 | 以 IUPAC motif 的基因组出现为锚，而非坐标区间 | 未找到先例 |
| 布局层 | 三元件 motif 锚定布局 + 左右独立距离区间（Pattern B） | 未找到先例 |

三层一起说才站得住：审稿人可以接受参数自由有先例，但锚定层与布局层是新的。

## 二、新颖性边界与措辞规范

### 2.1 已有先例（必须引用，不得声称首创）

| 工具 | 文献 | 已覆盖的能力 |
| --- | --- | --- |
| CRISPETa | PLoS Comput Biol 2017 · 10.1371/journal.pcbi.1005341 | 成对 gRNA 删除指定区域（坐标输入） |
| pgRNAFinder | Bioinformatics 2017 · 10.1093/bioinformatics/btx472 | 距离无关的成对 gRNA 设计 |
| GuideScan | Nat Biotechnol 2017 · 10.1038/nbt.3804 | 单／成对设计与特异性聚合 |
| GT-Scan | Bioinformatics 2014 · 10.1093/bioinformatics/btu354 | 区域型设计 + paired nickase |
| DECKO | BMC Genomics 2015 · 10.1186/s12864-015-2086-z | 双 CRISPR 删除基因组元件 |
| Cas-Designer | Bioinformatics 2015 · 10.1093/bioinformatics/btv537 | 多种 Cas9 变体与 PAM 选择 |
| FlashFry | BMC Biol 2018 · 10.1186/s12915-018-0545-0 | 任意 PAM、大规模脱靶设计 |
| CRISPRitz | Bioinformatics 2020 · 10.1093/bioinformatics/btz867 | 多核酸酶 PAM、bulge、变异感知 |
| CHOPCHOP v3 | NAR 2019 · 10.1093/nar/gkz365 | 多效应器端到端 web 工具箱 |
| crisprVerse | Nat Commun 2022 · 10.1038/s41467-022-34320-7 | 跨核酸酶统一设计框架 |
| CaSilico | Front Bioeng Biotechnol 2022 · 10.3389/fbioe.2022.957131 | Cas12/13/14 一体化 in silico 设计 |
| Cas-OFFinder | Bioinformatics 2014 · 10.1093/bioinformatics/btu048 | 脱靶搜索引擎 |
| Off-Spotter | Biol Direct 2015 · 10.1186/s13062-015-0035-z | 穷尽式 lookalike 枚举 |
| TEEP / TnpBmax | Nat Methods 2024 · 10.1038/s41592-024-02418-z | TnpB omegaRNA 效率预测（本程序 teep 路径上游） |
| CRISPR multitargeter | PLoS One 2015 · 10.1371/journal.pone.0119372 | 相似序列集合的共有／独有 guide |
| CRISPR-COPIES | NAR 2024, 52, e30 · 10.1093/nar/gkae062 | 整合位点筛选；ScaNN 近似最近邻脱靶搜索；带 web 界面 |
| ALLEGRO | NAR 2025, 53, gkaf783 · 10.1093/nar/gkaf783 | 跨物种最小 guide 文库（ILP 集合覆盖）；用户可选 track（any/each）× 倍数 m；候选削减「不影响最优性」 |
| MINORg | NAR 2023, 51, e43 · 10.1093/nar/gkad142 | 每个输入序列求最小 guide 集以覆盖多靶标（ALLEGRO 视其为该问题当时最强基线） |
| CRISPys | J Mol Biol 2018, 430, 2184-95 · 10.1016/j.jmb.2018.03.019 | 基因家族多成员编辑的最优 sgRNA 设计 |
| multicrispr | Life Sci Alliance 2020, 3, e202000757 · 10.26508/lsa.202000757 | 单基因组内多重编辑 / prime editing 的 gRNA 设计（可上千靶标） |


**ALLEGRO（NAR 2025, gkaf783）单独说明（2026-09-19 增补）**

它把「用最少的 guide 覆盖多物种的一组基因」建模为集合覆盖问题并用整数线性规划求解，与本项目同属
「设计规模与布局」这一大类；但它以物种集合与基因/直系同源组为输入，不涉及 motif 锚定、多元件间距、
PAM/TAM 自由输入或脱靶索引。有两点必须落到论文里：

1. 它用 **track（A = any / E = each）× 倍数 m** 提供「用户可选的设计策略」。因此「本工具提供多种设计模式」
   这件事本身不新 —— 我们的新颖性只能落在**布局语义**（以 IUPAC motif 的基因组出现为锚 + 每侧独立距离
   区间 + Y 序列约束），不能落在「我们有两个模式」这个说法上。
2. 它的 Discussion 明确写：非 Cas9 效应子（如 Cas12a）的 PAM 识别需要另行定制 PAM 约束
   （`R:/songji/论文/3/ALLEGRO-2025-nar.txt:662-665`）。这是「参数化 PAM/TAM 是尚未被满足的需求」
   最有力的外部佐证，Introduction 缺口段 (a) 应直接引用它，而不是只由我们自述。

完整分析见 `docs/ALLEGRO_REFERENCE_ANALYSIS.md`。

### 2.2 未找到先例（可写 to our knowledge）

1. 以 IUPAC 序列 motif 的**基因组出现**为设计锚，而非坐标区间。
2. 三元件 motif 锚定布局 `Target -[x_min,x_max]- Y -[y_min,y_max]- Target`，
   左右距离区间相互独立，Y 为序列约束。
3. 上述布局中左右引导各自在双链独立匹配，`++/+-/-+/--` 四种链向组合全部枚举。
4. 自动种子计划合成 + 运行期完备性标记（`seed_plan_guaranteed`）。
5. 线程数无关的命中输出确定性（同 digest）。

检索覆盖：Europe PMC 的 dual nickase、inversion、tandem duplication、three-part、
gRNA pair + distance/spacing、DECKO、inter-guide distance 等组合均无命中。
**未覆盖 Google Scholar 全文、bioRxiv、会议摘要与专利**，投稿前应补扫。

### 2.3 措辞对照

禁用：

> Paired and three-element guide layouts have never been described.
> Our tool is the first to allow custom PAM/TAM input.
> Our tool is the first to provide multiple user-selectable design strategies.
> Our approach is the first to reduce candidate enumeration without loss.

（后两句已被 ALLEGRO 2025 推翻：它的 track 机制与「不影响最优性」的候选削减都构成先例；
详见 `docs/ALLEGRO_REFERENCE_ANALYSIS.md` 第 3、5 节。）

推荐：

> Prior paired-guide tools specify a genomic interval to be deleted (CRISPETa,
> pgRNAFinder, GT-Scan, DECKO); the guide pair is then selected inside that
> interval. We instead specify a sequence-level layout: the design space is the
> set of genomic placements of user-supplied IUPAC motifs subject to per-side
> orientation and independent distance constraints. To our knowledge, this
> motif-anchored specification model - and in particular the three-element
> layout with independent left/right distance ranges (Pattern B) - has not been
> described.

数值措辞（不要写成最高效）：

> 索引引擎的表述限定为“在受测集合中 warm search 延迟最低、内存有界、
> 结果可复现”，不要写 best/fastest without qualification。
## 三、正文大纲

### Title

建议：`CRISPR-Motif Workbench: a constraint-driven guide design platform with
a native indexed off-target engine`

### Abstract（NAR 惯例：单段，不分区；实测 2024 副范本 206 词、2025 主范本 173 词；目标 170-250 词，硬上限 250）

1. 现有工具以基因或坐标区间为中心枚举 guide，无法直接表达设计意图。
2. 我们把引导定义抽象为一组正交自由参数，并把设计空间形式化为其完备解集。
3. 配套原生 C++20 持久化索引引擎，含自动种子计划合成与完备性保证。
4. 结果 1：计划内搜索完备；warm search 0.048 s vs BLAST 0.518 s；
   32 线程 8.6x／28.5x 扩展；命中输出与线程数无关。
5. 结果 2：参数表达力矩阵显示 N 个已发表系统中 M 个现有工具无法表达。
6. 可用性：桌面 GUI、本地 web 界面、完整测试套件。

### 1 Introduction

- P1 工具谱系与分类：区域型、基因型、成对型、跨核酸酶型（引用 2.1 表）。
- P2 两个缺口：
  (a) 参数表达力 - PAM/TAM、长度、方向、布局无法正交组合；
  (b) 引擎层 - 种子策略写死、并行结果不可复现、无内存边界。
- P3 贡献列表 C1-C4，C1/C2 加粗。

### 2 Materials and Methods

- 2.1 设计规格形式化：`S = (L, P, l, o, s)` 与解空间 `D(S)` 定义，说明输出是完备解集。
- 2.2 三元件布局与链向组合枚举；`left_target_start/end` 等区间语义。
- 2.3 索引结构：`CRISPRGGI` v1 两层布局、u4/u8 自适应、contig 表、
      FASTA 指纹失效检测、mmap 只读共享、Python/C++ 双向兼容。
- 2.4 **种子计划合成**（核心算法）：
      `allowed = floor(M / (s - B))`，
      `W(s) = sum_i sum_{c <= allowed} C(len_i, c) * 3^c`，
      `s* = argmin (W(s), s)`，约束 `s >= B+1`、`s <= L/k`。
- 2.5 **引理 1（完备性）与证明**：`s >= B+1` 且每段预算 `floor(M/(s-B))` 时，
      任意含 <=B 个 bulge、<=M 个错配的命中至少留下 `s-B` 个无 bulge 种子；
      其错配分布在这 `s-B` 段上，由抽屉原理必有一段错配数不超过
      `floor(M/(s-B))`，即被该段变体枚举覆盖。故该计划下搜索完备。
      运行期由 `seed_plan_guaranteed` / `exhaustive_seed_plan` 标记。
- 2.6 退化行为：超出变体上限时回退整段方案并不置 guaranteed 标记，附原因字符串。
- 2.7 确定性并行：worker pool over guides、按输入序合并、线程数无关的命中序列。
- 2.8 硬资源边界：预检估算 + 运行期 RSS 检查 + `MEMORY_LIMIT_EXCEEDED`
      不静默回退；`--timeout-s` 同语义。
- 2.9 IUPAC PAM/TAM 在引擎内的 3prime/5prime 双链匹配。
- 2.10 打分模型、校准状态传播与 PairRank。
- 2.11 实现与测试：Python 3.13 / C++20，32 个测试模块，`.ggi` 双语言互操作。

### 3 Results

- 3.1 种子计划代价与完备性：`W(s)` 随 `(M, B, L)` 的曲线与 `s*` 分布。
- 3.2 跨引擎基准：六引擎表（`example/engine_benchmark_small/REPORT.md`）
      + 线程扩展表（`docs/NATIVE_INDEXED_BENCHMARK.md`）。
- 3.3 召回诚实性：1-mismatch 压力测试 BLAST 31/36，其余引擎 36/36（HSP 截断）。
      这条把自建索引从偏好变成实证，必须写。
- 3.4 确定性：线程数 x 命中 digest 一致性。
- 3.5 参数表达力矩阵：已发表系统 x 工具 x 四个参数维度（见第五节第 1 项）。
- 3.6 案例：AAVS1(TTR-TTAA-TTR)、TRAC、PDCD1，展示现有工具无法端到端重现的设计。
- 3.7 模型复刻等价性：DeepCRISPR、Azimuth、DeepCpf1、CRISPR-M、TIGER。
- 3.8 回顾性验证：用已公开发表的实测数据集评估预测相关性（见第七节）。

### 4 Discussion

- 与 pgRNAFinder / CRISPETa 的差别在**设计空间**，不在排序精度。
- 与 GuideScan2 / CRISPRitz 的差别在**可证完备的种子计划、并行确定性、硬资源边界**。
- 局限（主动写，不要等审稿人问）：
  - 本研究不做湿实验：所有模型分数与排序均未经本研究实验验证。
  - `prediction_only` 模式只给保守排序，不给概率。
  - bulge 走 `conservative_bulge_v1`，标注 `uncalibrated`。
  - TIGER 依赖 TensorFlow；TEEP 依赖网络。
  - 超过约 200 MB 的基因组自动首选 BLAST。
  - 基准以合成基因组与有限真实位点为主。

### 5 Data Availability / Funding / Conflict of Interest

- NAR 强制 Data Availability：建议 GitHub release tag + Zenodo DOI，不要只给仓库地址。
- `.ggi` v1 格式规范作为 Supplementary 提供。
## 四、图表清单

| 编号 | 类型 | 内容 |
| --- | --- | --- |
| Fig 1 | 图 | 总体架构与数据流（定义 pattern -> 提取候选 -> 脱靶 -> 评分 -> 导出） |
| Fig 2 | 图 | 三类 pattern 的形式化示意，含四种链向组合 |
| Fig 3 | 图 | 索引内存布局（偏移表 + 位置数组 + u4/u8 分界） |
| Fig 4 | 图 | 种子计划划分示意（含 bulge 抽屉原理） |
| Fig 5 | 图 | 线程扩展曲线 |
| Fig 6 | 图 | 案例位点候选分布与 PairRank 分层 |
| Table 1 | 表 | 种子计划在不同 (M, B, L) 下的 s* 与 W |
| Table 2 | 表 | 跨引擎基准 |
| Table 3 | 表 | 参数表达力矩阵（C1 的核心证据） |
| Table 4 | 表 | 模型清单、校准状态与复刻误差 |
| Table 5 | 表 | 输出字段契约 |

## 五、待补数据

1. **参数表达力矩阵**（最高优先级，C1 能否立住的关键）
   行：已发表系统（SpCas9 NGG、非 NGG 变体、Cas12a/b/k、Cas13、TnpB/TAM 等）。
   列：能否自定义 PAM/TAM、能否自定义靶长度、能否自定义方向、
   能否表达中间元件约束、能否枚举全部出现位点。
   对象工具：CHOPCHOP v3、CRISPOR、FlashFry、CRISPRitz、GuideScan2、CRISPETa、pgRNAFinder。
2. **头对头引擎基准**：扩展现有 `tools/benchmark_all_engines.py`，
   加入 GuideScan2 / CRISPRitz / FlashFry，报告召回 + 时间 + 峰值内存。
3. **组合复杂性与剪枝**：`O(n_left x n_right)` 的复杂度分析与距离约束剪枝说明。
   审稿风险最高的一点，务必写进 Methods。
4. **真实基因组端到端运行**：不要只有合成基因组。
5. **`.ggi` v1 格式规范**（Supplementary）。
6. **release tag + Zenodo DOI**。

7. **回顾性验证**（不做湿实验后的替代方案）：选取 1-2 个公开实测数据集
   （如 DeepCpf1 的 Cas12a 数据、Azimuth 的 SpCas9 数据），评估本程序预测与
   实测效率的相关性，写进 Results。
## 六、证据索引（仓库内位置）

### 设计空间与参数（C1）

| 位置 | 内容 |
| --- | --- |
| `shared/design/pattern_spec.py` | PatternKind 三类、MotifSpec(sequence, flank_length, side)、IUPAC 字符集、距离区间校验 |
| `shared/design/guide_design.py` | find_guides(sequence, spacer_len, pam, pam_side, motif, allow_reverse)，自由输入语义 |
| `shared/search/iupac.py` | iupac_to_regex / find_all_iupac_matches / find_all_iupac_positions |
| `Target_xbp_Target/extract_complex_queries.py` | 左右 motif 双链独立匹配、四种链向组合、min_gap/max_gap |
| `Target_xbp_Y_zbp_Target/extract_motifs.py` | Y 锚定 + 左右独立 min/max distance |
| `Target_xbp_Y_zbp_Target/sort_by_distance.py` | 距离剪枝与排序 |
| `designer_workbench.py` | UI 暴露 PAM/TAM Motif、Target Length、Target Position |
| `docs/design_patterns_en.md` | 四种链向组合与区间字段的正式说明 |

### 原生引擎（C2）

| 位置 | 内容 |
| --- | --- |
| `native/offtarget_engine/src/seed_plan.cpp` | build_seed_plan、allowed、变体代价、guaranteed 标记 |
| `native/offtarget_engine/src/pam.cpp` | IUPAC 位掩码、3prime/5prime、双链 |
| `native/offtarget_engine/include/offtarget/genome_index.hpp` | kIndexFormatVersion=1、CRISPRGGI magic、u4/u8、contig 表 |
| `native/offtarget_engine/src/search.cpp` | 并行搜索与确定性合并 |
| `native/offtarget_engine/README.md` | 确定性声明、内存边界、k=8..12 |
| `docs/NATIVE_INDEXED_ENGINE_DESIGN.md` | 设计决策、退出码、CLI 契约 |
| `docs/NATIVE_INDEXED_BENCHMARK.md` | 线程扩展与 cache 策略数据 |
| `example/engine_benchmark_small/REPORT.md` | 六引擎基准与 BLAST 召回差异 |

### 打分与排序（C3/C4）

| 位置 | 内容 |
| --- | --- |
| `docs/MODELS.md` | 模型清单、SHA256、复刻误差（DeepCRISPR 2.98e-7、Azimuth Spearman 0.993） |
| `docs/SCORING_GUIDE.md` | MM 桶语义、特异性聚合、校准状态 |
| `docs/PAIR_RANKING.md` | PairRank 双模式与保守上界 |
| `docs/TNPB.md` | TnpB/omegaRNA 路径与文献 |
| `scy-test/` | AAVS1(TTR-TTAA-TTR)、TRAC、TRAC-exon3、PDCD1、Tyr、rDNA 实际运行数据 |
| `tests/` | 32 个测试模块 |

## 七、实验验证策略（已定：不做湿实验）

用户已于 2026-09-19 确认本研究不做湿实验，因此分支 A 关闭，全文按纯计算工具定位。

1. **期刊定位不变**。同类工具论文绝大多数是纯计算工作：CHOPCHOP v3（NAR 2019）、
   CRISPOR（NAR 2018）、FlashFry（BMC Biol 2018）、CRISPRitz（Bioinformatics 2020）、
   GuideScan2（Genome Biol 2025）、crisprVerse（Nat Commun 2022）、pgRNAFinder、
   CRISPETa、GT-Scan。NAR 正刊不要求湿实验。
2. **C1 的举证责任加重**。原先指望用实验佐证“设计意图可实现”，现在必须完全依靠
   参数表达力矩阵 + 案例研究 + 与竞品的可表达性对比。第五节第 1 项
   （表达力矩阵）从“重要”升级为“决定成败”，是当前的关键路径。
3. **C3（PairRank）停留在 prediction_only**。`experiment_calibrated` 模式在本文中
   无法演示，因此 PairRank 保持支撑位，不得列为首要贡献，并须在 Limitations
   主动说明其保守上界未经实验校准。
4. **案例章的权重上升**。AAVS1 / TRAC / PDCD1 案例必须证明端到端可用，
   建议增加与 CHOPCHOP / CRISPOR 在同一批位点上的候选集对比（找回率）。
5. **用回顾性验证替代前瞻性实验（推荐）**。用已公开发表的实测数据集评估本程序的
   on-target / off-target 预测，无需新做湿实验。候选数据集：
   - DeepCpf1 / deepCAS12A 原论文的 Cas12a 实测效率数据
   - Azimuth / Doench 2016 的 SpCas9 实测效率数据
   - TIGER 原论文的 Cas13d 数据
   - TEEP 原论文的 TnpB ωRNA 数据
   这一步把“没有实验”补成“使用独立公开实测数据做了回顾性评估”，是本分支
   性价比最高的补强。
6. **措辞红线**：不得出现任何暗示本研究做过实验的表述；Abstract 与 Discussion
   必须明确声明本工作为计算工具、未在本研究中进行实验验证。
## 八、写作顺序建议

1. 先做第五节第 1 项（表达力矩阵）- 它决定 C1 的成败。
2. 再补第 2、3 项（头对头基准、复杂度分析）- 决定 C2 的成败。
3. 然后写 Materials and Methods（含引理证明），这是最难也最值钱的一节。
4. 最后写 Introduction 与 Abstract，避免过早锁定表述。
## 九、格式规范（双范本：ALLEGRO NAR 2025 53 gkaf783 为主范本，CRISPR-COPIES NAR 2024 52 e30 为副范本）

- 主范本：ALLEGRO（NAR 2025, 53, gkaf783, doi:10.1093/nar/gkaf783, 栏目 Methods），抽取文本
  `R:/songji/论文/3/ALLEGRO-2025-nar.txt`；量化数据为本文档 2026-09-19 用 `pdftotext -layout -enc UTF-8` 统计所得。
来源：`R:\songji\论文\3\gkae062.pdf` —— CRISPR-COPIES，
`https://doi.org/10.1093/nar/gkae062`。该文是带 web 界面的工具类工作，栏目为
**Methods**，采用 e-locator 在线专发，与本项目形态最接近，故作格式范本。

下列数字均由 PDF 抽取统计得出（`pdftotext -layout -enc UTF-8`，共 17 页）。

| 项目 | 参考值 | 备注 |
| --- | --- | --- |
| 栏目 | Methods | 既非 Standard Article，也非 Web Server 专刊 |
| 篇幅 | 17 页 | 含图、表与参考文献 |
| 摘要 | **206 词**，单段、无小标题 | 本轮把目标区间定为 170-250 词 |
| Graphical abstract | 有，独立小节，紧随摘要 | 需新做，我们目前没有 |
| 参考文献 | 78 条 | 规模参考 |
| 图 | 19 处 Figure 出现（含正文引用与图注） | 图是主要证据载体 |
| 表 | 主文未出现 Table 引用 | 该文完全不用主文表 |
| 章节顺序 | Abstract → Graphical abstract → Introduction → Materials and methods → Results → Discussion → Data availability → Supplementary data → Acknowledgements → Funding → Conflict of interest statement → References | Methods 在 Results 之前 |
| 子标题 | 无编号描述性短语 | 如 `CRISPR-COPIES architecture` |
| Discussion | 连续散文，无子标题 | |
| Data availability | `The data supporting the findings of this study are available within the article and its Supplementary Data files or uploaded through public repositories.` | 可直接套用句式 |
| Supplementary data | `Supplementary Data are available at NAR Online.` | 固定句式 |
| 制图工具 | BioRender，并在 Acknowledgements 中声明 | |

#### 9.0.1 2025 主范本（ALLEGRO）增量对照

| 项目 | 2025 主范本 | 2024 副范本 | 本项目的处置 |
| --- | --- | --- | --- |
| 摘要词数 | 173 词 | 206 词 | 区间放宽为 **170-250 词** |
| 主文图 | Figure 1-5 | 19 处 Figure 引用 | 主文 5-6 张可行，其余进 Supplementary |
| 主文表 | 无（表一律 Supplementary Table Sn） | 无 | 维持主文不加表 |
| Back matter 顺序 | Acknowledgements（含 Author contributions:） -> Supplementary data -> Conflict of interest -> Funding -> Data availability -> References | Data availability -> Supplementary data -> Acknowledgements -> Funding -> Conflict of interest | **改用 2025 顺序**；Back matter 需增 Author contributions 段 |
| Supplementary data 句式 | `Supplementary data is available at NAR online.` | `Supplementary Data are available at NAR Online.` | 以 2025 句式为主，两种都被接受 |
| Data availability 写法 | 仓库 URL + Zenodo DOI + 文档地址 + NCBI accession | 通用句式（within the article and its Supplementary Data files...） | 采用 2025 写法：仓库 URL + 版本 DOI + 文档；未定项写 [TO FILL] |
| 数学表述位置 | 详细数学放 **Supplementary Notes** | 无此惯例 | 支持把「源码对照说明」移入 Supplementary note 的裁定 |
| 竞品比较 | 与 MINORg 比文库大小 / RAM / 时间 | 与既有工具比 | 与 engine-bench 任务的基准曲线同级做法 |

### 9.1 对本项目的直接约束

1. 摘要按 **170-250 词** 写，取消原先「300 词量级」的假设。
2. 需要准备 **Graphical abstract**（当前没有，属新增工作量）。
3. 主文以**图**为主。第六节原计划 5 张表，建议把「输出字段契约」这类大表移到
   Supplementary，主文只保留必要的 1-2 张表。
4. 子标题改为**无编号描述性短语**（第一节到第九节里的 `3.1 / 3.2` 只是规划编号，
   正式稿要去掉编号）。
5. 必须写 `Data availability` 与 `Supplementary data` 两小节，句式参照上表。

### 9.2 竞争性提示（重要）

CRISPR-COPIES 用 **ScaNN**（近似最近邻）做脱靶搜索。这与本项目的原生索引引擎
是同类问题，但性质不同：

- ScaNN：**近似**搜索，追求吞吐。
- 本引擎：**完备枚举** + 运行期 `seed_plan_guaranteed` 完备性标记 +
  线程数无关的确定性输出 + 硬内存/超时边界。

这三点正好是可以在论文里正面区分的差异，因此 **CRISPR-COPIES 必须引用**，
并已在 §2.1 先例表中占一行。

### 9.3 同为范本的证据差距

该参考文包含完整湿实验验证（*S. cerevisiae*、*C. necator*、HEK293T；
流式分析、HDR 整合、多组学位点特征）。也就是说，即使同在 Methods 栏目，
带实验的文章证据链更完整。

本项目当前按**无实验版**撰写，需在 Discussion 主动声明未做实验验证，
并用回顾性验证（第五节第 7 项）与表达力矩阵补强。
若将来补齐实验，切到 `docs/PAPER_OUTLINE_WITH_EXPERIMENTS.md`。