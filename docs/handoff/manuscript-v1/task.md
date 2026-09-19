# 任务：论文 v1 全稿（无实验版）+ 遗留证据文档收尾

- task-slug: `manuscript-v1`
- round: 1
- master: 会话 M（master）
- servant: 会话 S（servant）
- repo: `R:\songji\programfile`
- 本地环境：`python` = 3.14.7；`native\bin\offtarget-engine.exe` 本地可直接运行（master 已实测）
- 基线：本任务**新增 6 个文件、修改 4 个文件**。开工前把这 4 个待改文件复制到
  `backup/2026-09-19_manuscript-v1/`（只复制这 4 个文件，不要整仓复制）
- 上位文档：`docs/PAPER_OUTLINE.md`（无实验版大纲）、`docs/PAPER_METHODS_DRAFT.md`（Methods 初稿，只读）、
  `docs/ALLEGRO_REFERENCE_ANALYSIS.md`（2025 主范本分析）、`docs/handoff/nar-format-pack/task.md`（格式契约 r2）

## 0. 目标与边界

把现有大纲与前置件推进成**可通读的英文 v1 全稿**，并补交一份被前序任务遗留的证据文档。

- 只写**无实验版**：用户已确认本研究不做湿实验（`docs/PAPER_OUTLINE.md:276`）。
  `docs/PAPER_OUTLINE_WITH_EXPERIMENTS.md` 定义的「有实验版」不在本任务范围。
- 不做实验、不跑大型计算、不改任何代码。

## 1. 规则 / 契约（唯一权威版本，servant 不必重新调研）

```text
C1  格式（沿用 nar-format-pack r2）：摘要 170-250 词、单段、无引用编号；主文表 = 0 张；主文图 = 6 张；
    子标题用无编号描述性短语；back matter 顺序 = Acknowledgements(含 Author contributions)
    -> Supplementary data -> Conflict of interest -> Funding -> Data availability。
C2  禁词：全文（含图注、表注）不得出现 first / never / unprecedented / 首创 / 首次 / 从未。
    新颖性表述只能用 docs/PAPER_OUTLINE.md:111-118 的推荐句式：承认先例，差异落在布局语义
    （以 IUPAC motif 的基因组出现为锚 + 每侧独立距离区间 + Y 序列约束），不能落在「我们有两个模式」。
C3  数字纪律：正文与图表里的每个数字都必须可追溯到仓库内已有实测产物，并在其后用方括号给出短出处
    （例：0.048 s [REPORT.md:12]）。允许来源：docs/seed_plan_sweep.json、
    example/engine_benchmark_small/REPORT.md、docs/NATIVE_INDEXED_BENCHMARK.md、
    docs/expressiveness_matrix.tsv、docs/MODELS.md、docs/OUTPUTS.md、以及本文件第 2 节的 master 实测值。
    除此之外一律写 [TO FILL]。禁止估算、禁止「约 N 倍」式模糊表述。
C4  引用纪律：参考文献只能取自 docs/PAPER_OUTLINE.md 第 2.1 节先例表（20 条，含 DOI）、第 2.2 节、
    第六节证据索引，以及仓库内已出现的文献。禁止编造。先例表 20 条必须全部在正文被引用。
C5  图表编号（master 裁定，固定，不得改号）：
    主文 Figure 1 架构与数据流 / Figure 2 三类 pattern 形式化 + 四种链向组合 /
    Figure 3 参数表达力矩阵 / Figure 4 索引内存布局（偏移表 + 位置数组 + u4/u8 分界）/
    Figure 5 种子计划划分（含 bulge 抽屉原理）/ Figure 6 线程扩展曲线。
    原「案例位点候选分布与 PairRank 分层」移出主文，作 Figure S1（内容不删，只改位置）。
    Supplementary 表按正文首次引用顺序：Table S1 表达力矩阵全表 / Table S2 种子计划网格 /
    Table S3 跨引擎基准 / Table S4 模型清单与校准状态 / Table S5 输出字段契约。
    正文引用必须按编号升序出现；为满足升序：Methods 只引用 Figure 1 与 Figure 2，
    Figure 4 的首次引用放在 Results 的「完备枚举与剪枝」小节。
C6  口径修正（master 核查发现的既有错误，本任务必须改）：
    ① 表达力矩阵 = 16 个数据行 = 15 个已发表工具 + 本文工作（docs/expressiveness_matrix.tsv 实测
       17 行 = 表头 + 16 行数据；工具名见第 2.6 节）。
    ② 矩阵能力列 = 6 个（custom_pam_tam / custom_target_length / custom_orientation /
       middle_element_constraint / enumerates_all_occurrences / pair_side_independent），
       另有 3 个元数据列（tool / year / input_model）与 1 个 evidence 列，共 10 列。
       docs/PAPER_BACK_MATTER.md:29 与 docs/FIGURE_TABLE_PLAN.md 里的「7 个能力列」是错的，改 6。
    ③ docs/EXPRESSIVENESS_MATRIX.md:1 标题的「Table 3」改为「Figure 3」。
    ④ 摘要「covering 16 published design tools」改为「covering 15 published design tools」。
C7  诚实性声明：Abstract 与 Discussion 各有一处明确声明本研究为计算工具、未在本研究中进行实验验证。
    Abstract 现稿已含该句（不必改），Discussion 的 Limitations 必须再写一条。
C8  Results 小节顺序（正文用无编号描述性短语）：
    ① motif 锚定设计空间与表达力（C1；引 Figure 2/3、Table S1）
    ② 成对布局的完备枚举与剪枝（C1；引 Figure 4）
    ③ 种子计划代价曲线与完备性（C2；引 Figure 5、Table S2）
    ④ 跨引擎基准与召回诚实性（C2；引 Figure 6、Table S3）
    ⑤ 确定性与资源边界（C2）
    ⑥ 打分、校准状态与 PairRank（C3/C4；引 Table S4）
    ⑦ 案例：AAVS1 / TRAC / PDCD1（引 Figure S1）
    ⑧ 实现、界面与测试（引 Table S5）
    依据：docs/PAPER_OUTLINE.md:302「先做表达力矩阵 - 它决定 C1 的成败」；C1 是头号贡献，故 Results 领起。
```

## 2. 现状证据（master 已实测，可直接引用，不必重跑）

### 2.1 引擎自述

```text
native\bin\offtarget-engine.exe --version
-> offtarget-engine 0.1.0 index-format=1

native\bin\offtarget-engine.exe capabilities --json
-> {"engine":"indexed","implementation":"native-cpp","index_format":1,"max_build_k":12,"threads":true,
    "max_memory_mb":true,"indels":"dna_rna","pam_sides":["3prime","5prime"]}
```

### 2.2 确定性

master 于 methods-draft 核验时实测：同一 fixture、M=2/B=0/k=10 下，`--threads 1` 与 `--threads 8` 的命中行
逐字节相同，sha256 前缀 `84ae1a985df44d8cd7db25276df45358`。本任务 P0-1 要求你用第 6 节的命令重跑 4 个线程数
并留下完整 digest（这是论文里「命中序列与线程数无关」的唯一证据来源）。

### 2.3 W(s) 复现（master 复跑 `python tools\seed_plan_sweep.py --plan-table`）

```text
V(k, m) = sum_c C(k, c) * 3**c        [native/offtarget_engine/src/seed_plan.cpp:105 variant_count]
k=8 : m=0/1/2/3 -> 1 / 25 / 277 / 1789
k=10: m=0/1/2/3 -> 1 / 31 / 436 / 3676
probe_len=20 的 s* 与 W（全部 guaranteed=true，分段恒为 2x10bp@allowed）：
k=8 : (M,B)=(0,0) W=6 | (1,1) 150 | (2,1) 1662 | (3,1) 10734
k=10: (M,B)=(0,0) W=2 | (1,1)  62 | (2,1)  872 | (3,1)  7352
```

关键源码锚点：`segmented_variant_work` = `max(1, segment_len - kmer_size + 1) * variant_count(kmer_size, m)`
（`seed_plan.cpp:63-68`，**含窗口因子**）；`build_seed_plan` 起于 `seed_plan.cpp:123`，其 `:126` 为 `(void)seed_len;`。

### 2.4 `docs/seed_plan_sweep.json`（engine-bench 产出，master 已核验，**只读**）

- `records` = 16 条，覆盖 M{0,1,2,3} x B{0,1} x k{8,10}；`repeats=3`、`threads=8`、逐条 `repeats_consistent=true`。
- fixture = 1,000,000 bp、12 guides x 20 nt；`build_policy` = 每个 k 建一次索引并复用到所有 M/B 组合。
- `index_builds`：k=8 -> 0.955 s / 4,524,314 B；k=10 -> 0.316 s / 12,388,602 B；`position_dtype` = u4。
- 首条记录 M0/B0/k8：median 0.207 s、candidates 24、hits 24、`py_plan_variants` 6。
- 末条记录 M3/B1/k10：median 1.082 s、candidates 66、hits 66、`py_plan_variants` 7352。
- `cost_model` 原文：`W(s) = sum_i max(1, L_i - k + 1) * V(k, a), V(k, a) = sum_c C(k, c) * 3**c, a = M // (N_seeds - B)`
- `seed_len_policy` 原文：`--seed-len is set to the index k; seed_plan.cpp:126 ignores it`

### 2.5 跨引擎基准（`example/engine_benchmark_small/REPORT.md` 原文，**不要改写数字**）

exact-match：native-indexed 0.107 s build / 0.048 s warm / 24 hits；blast 0.060 / 0.518；bowtie2 0.902 / 0.176；
indexed-Python 0.178 / 0.990；casoffinder 无持久索引 / 1.547；exact 无持久索引 / 2.156。

bulge 开销（M=0、B=1）：native-indexed 0.095 / 0.183；blast 0.099 / 0.565；bowtie2 0.886 / 0.176；
exact 无持久索引 / 2.617；indexed-Python 0.182 / 8.729。

该 fixture **未植入真实 bulge 命中**，故上表是「启用 bulge 的代价」而非召回率——写稿必须保留这一限定句。

1-mismatch 压力测试：exact / indexed / native-indexed / Cas-OFFinder 均 36/36；BLAST 31/36（HSP 截断）。

### 2.6 表达力矩阵现状

16 数据行 = 15 个已发表工具 + 本文工作。已发表工具（共 15）：CHOPCHOP v3、CRISPOR、FlashFry、CRISPRitz、
GuideScan2、CRISPETa、pgRNAFinder、GT-Scan、Cas-Designer、Breaking-Cas、EuPaGDT、CaSilico、crisprVerse、
DECKO、CRISPR multitargeter。`unknown` 格共 19 个：DECKO 6、GT-Scan 5、EuPaGDT 3、Cas-Designer 2、
CRISPR multitargeter 2、pgRNAFinder 1；其余工具行无 unknown。

### 2.7 已定稿的前置件（可直接搬运，不要重写）

`docs/PAPER_FRONT_MATTER.md`（标题候选 A、摘要现稿、作者块模板）、`docs/PAPER_BACK_MATTER.md`（back matter 模板）、
`docs/GRAPHICAL_ABSTRACT_SPEC.md`（图形摘要规格）、`docs/PAPER_METHODS_DRAFT.md`（Methods 初稿，本任务只读）。

### 2.8 前序核验结论（master review，作为写作输入）

- `docs/handoff/expr-matrix/review.md` F2：论文须补一句 limitation，说明「未检索到公开文档」不等于「确定不支持」。
- `docs/handoff/nar-format-pack/review.md`：主文图 6 张、Supplementary 按引用顺序、wiki 措辞改写为仓库 `docs/`。
- `docs/handoff/engine-bench/review.md`：该任务由 master 接管，剩余项即本任务 P0-1。

## 3. 必做改动

- [ ] P0-1 `docs/SEED_PLAN_ANALYSIS.md`（新增，补交 engine-bench 遗留件）
  - 四节：① W(s) 复现（引用 `seed_plan.cpp` 真实行号，至少覆盖 `build_seed_plan` / `partition_lengths` /
    `segmented_variant_work` / `binomial` / `power_three`）② 16 组网格表（含 `s*`、`W`、guaranteed 标记）
    ③ 确定性表（`--determinism` 实跑的 4 个线程数 hits 与 sha256）④ 组合复杂度与剪枝
    （引用 `Target_xbp_Target/extract_complex_queries.py` 与 `Target_xbp_Y_zbp_Target/extract_motifs.py` 的真实行为）
  - 每个结论后跟命令或 `文件:行`。
  - 若源码与第 2.4 节的 `cost_model` 摘要有差异，单列一节写明；无差异也要写「未发现差异」。
- [ ] P0-2 `docs/PAPER_DRAFT.md`（新增）：Title / Abstract / Introduction / Discussion
  - Abstract 搬 `docs/PAPER_FRONT_MATTER.md` 现稿，只做 C6④ 一处改动；词数仍在 170-250。
  - Introduction 按 `docs/PAPER_OUTLINE.md:143-147` 的 P1/P2/P3 写；缺口段 (a) 必须引用 ALLEGRO 的 Discussion
    原文作外部佐证（出处 `R:/songji/论文/3/ALLEGRO-2025-nar.txt:662-665`，解释见
    `docs/ALLEGRO_REFERENCE_ANALYSIS.md` 第 3 节）——这是「参数化 PAM/TAM 是尚未被满足的需求」最有力的外部证据。
  - Discussion 按 `docs/PAPER_OUTLINE.md:187-195` 写，6 条局限逐条落下，一条不许删；并加 C7 的声明。
- [ ] P0-3 `docs/PAPER_RESULTS_DRAFT.md`（新增）：Results，按 C8 的 8 个小节
  - 每节必须有可追溯数字（C3）。案例小节若仓库内无数据，整节写 `[TO FILL: 案例数据未在仓库中]`，
    保留小节标题与 Figure S1 引用；不要删节、不要用别的位点凑数。
- [ ] P0-4 `docs/PAPER_FIGURE_CAPTIONS.md`（新增）：Figure 1-6 与 Figure S1 的英文图注
  - 每张含：内容、数据来源、样本量/口径。Figure 3 图注必须写明 `unknown` 不等于 `no`（第 2.8 节第一条）。
- [ ] P0-5 `docs/PAPER_TABLES_SUPP.md`（新增）：Table S1-S5 的 Markdown 全表
  - S1 由 `docs/expressiveness_matrix.tsv` 直转（保留 `evidence` 列）；S2 由 `docs/seed_plan_sweep.json` 的
    16 条记录生成；S3 由 `REPORT.md` 两个表合并；S4 由 `docs/MODELS.md`；S5 由 `docs/OUTPUTS.md`。
- [ ] P0-6 `docs/PAPER_REFERENCES.md`（新增）：编号参考文献表（C4），先例表 20 条全部引用。
- [ ] P1-1 `docs/FIGURE_TABLE_PLAN.md`（修改）：按 C5/C6 更新编号与口径，状态列按实际状态改写
- [ ] P1-2 `docs/EXPRESSIVENESS_MATRIX.md`（修改）：第 1 行标题 `Table 3` -> `Figure 3`
- [ ] P1-3 `docs/PAPER_BACK_MATTER.md`（修改）：① wiki 措辞改为仓库 `docs/` 路径 ② Supplementary 表序号与
  `FIGURE_TABLE_PLAN.md` 对齐 ③「7 个能力列」->「6 个能力列」
- [ ] P1-4 `docs/PAPER_FRONT_MATTER.md`（修改）：摘要 `16 published design tools` -> `15 published design tools`；
  第 5 节的 16/17 口径一并对齐

## 4. 不要做的事

- 不写任何实验、湿实验或回顾性验证的 Results（本稿为无实验版）
- 不改 `docs/PAPER_METHODS_DRAFT.md`（methods-draft 任务 round 2 正在改该文件）
- 不改 `docs/PAPER_OUTLINE.md` / `docs/PAPER_OUTLINE_WITH_EXPERIMENTS.md` / `docs/ALLEGRO_REFERENCE_ANALYSIS.md`
- 不改任何代码、`tools/`、`native/`、`shared/`、`example/`；`docs/seed_plan_sweep.json` 只读
- 不改 C5 的编号；不编造数字与文献；不写禁词
- 不跑全量测试套件、不跑 benchmark、不建大 fixture

## 5. 决策项（未确认则按推荐执行）

- 标题：推荐沿用候选 A（`docs/PAPER_FRONT_MATTER.md` 第 1 节），servant 不另造标题
- 案例数据缺失时：推荐保留小节 + `[TO FILL]` 标记，不删节（见 P0-3）
- Table S2 是否列全 16 行：推荐列全
- 参考文献条数：推荐 45-70 条，先例表 20 条必引
- 摘要词数口径：推荐不改现稿措辞（除 C6④），统计口径写 `[A-Za-z][A-Za-z-]*`

## 6. 轻量自检（servant 的检验上限）

```powershell
cd R:\songji\programfile
python tools\seed_plan_sweep.py --determinism
python -c "import io,re;d=io.open('docs/PAPER_DRAFT.md',encoding='utf-8').read();print('forbidden',re.findall(r'(?i)\b(first|never|unprecedented)\b',d),[w for w in ['首创','首次','从未'] if w in d]);print('abstract_words',len(re.findall(r'[A-Za-z][A-Za-z-]*',d)))"
```

预期：determinism 四行 sha256 全相同；禁词列表为空；新增 6 个文件均无 BOM、无 `\r`。

## 7. 交付要求

- 完成后 `state.json` 置 `ready_for_review` 并更新 `updated`，写 `report.md`
- `report.md` 必填：改动文件+行号表格（新增/修改分开）、每条自检命令原文与输出、未做项及原因、
  附带发现（只记录不修）、待明确项
- 不要自己裁定「通过」；核验归 master


## 8. round 2 补充（master，2026-09-19 14:20 核验后）

round 1 的 10 个交付件全部存在且与契约一致（逐条结论与证据见 `review.md`）。本轮**只做 review.md §7 的 3 件必修**，
不扩大范围、不重写任何已通过的内容。

1. **D1** `docs/SEED_PLAN_ANALYSIS.md:128` —— 该行写「`(3,1)` 为 66（k=8 与 k=10 同值）」，
   与同文件 `:103` 的表格行（k=8 为 **67**）、`:111`（k=10 为 66）以及 `docs/seed_plan_sweep.json` 矛盾。
   改为「`(0,0)` 为 24，`(3,1)` 为 67（k=8）与 66（k=10）」。
2. **D2** `docs/PAPER_FIGURE_CAPTIONS.md:50,58,62` —— `tools/expressiveness_matrix.tsv` 目录写错，
   实际文件在 `docs/expressiveness_matrix.tsv`。三处改路径，行号 `1-17` / `3,8,9,15` / `9-17` 经核对正确、保留。
3. **D3** `docs/PAPER_REFERENCES.md` —— 补 4 篇被复刻模型的原始论文为 `[27]-[30]`。
   本项属 **C4 的定向放宽**（master 授权，仅限这 4 篇，其余仍受 C4 约束）：
   ① Azimuth（Doench 等，Nat Biotechnol 2016）② DeepCRISPR（Chuai 等，Genome Biol 2018）
   ③ DeepCpf1（Kim 等，Nat Biotechnol 2018）④ CRISPR-M（以 `docs/MODELS.md` / `docs/SCORING_GUIDE.md`
   记录的来源为准）。字段经 Europe PMC 解析，每条写明 DOI 与 DOI 来源；**解析不到写 `[TO FILL]`，不得编造**。
   同时更新 `docs/PAPER_RESULTS_DRAFT.md` 的打分小节与 `docs/PAPER_TABLES_SUPP.md` 的 Table S4 相应引用。

可选（不阻塞、不做也不打回）：
- N1 `docs/PAPER_DRAFT.md` 的 ALLEGRO 第二处引文是截断引用，句末加省略号或改用完整句。
- N2 `docs/PAPER_RESULTS_DRAFT.md` 的 `O(n_left log n_right + P)` 补半句，说明右位点数组的排序也计入代价。

不要做的事（本轮新增）：
- 不要授权或取用 `scy-test/` 的数据（用户尚未拍板）
- 不要改动 `[TO FILL]` 的 URL / DOI / accession / keywords 字段（外部信息）
- 不要为凑参考文献条数扩引 C4 之外的文献（D3 的 4 篇是唯一例外）

round 2 自检下限：D1 改后重跑「SEED_PLAN_ANALYSIS 数字 vs `docs/seed_plan_sweep.json`」逐值比对；
D2 改后重跑出处路径存在性扫描。交付：`state.json` 置回 `ready_for_review`（`round: 2`），
`report.md` **追加** round 2 小节（不覆盖 round 1）。


### 8.1 master 追加（2026-09-19 14:35，methods-draft round 2 核验后）

methods-draft round 2 已通过核验（见 `docs/handoff/methods-draft/review.md` 的 round 2 小节），其产物使 round 2 清单多出两条：

4. **（必做，很小）** `docs/PAPER_BACK_MATTER.md:34` 的 `Notes S1` 描述目前写「种子计划代价方程与完备性引理的详细数学表述」，
   而 `docs/PAPER_METHODS_DRAFT.md` 文末的 S1 实际内容是 source correspondence 说明（实现与规格的 W(s) 写法对应）。
   把该行描述改成同时覆盖两者，例如「种子计划代价方程与完备性引理的详细数学表述，含实现与规格写法的对应说明（source correspondence）」，
   使两份文件对 S1 的定义一致。
5. **（可选）** `docs/PAPER_METHODS_DRAFT.md` 的引理 1 假设已显式限定「target k-mer 窗口仅由 A/C/G/T 组成」；
   论文中凡出现「完备性 / exhaustive」表述的位置（`docs/PAPER_DRAFT.md` 的 Abstract 与 Introduction、
   `docs/PAPER_RESULTS_DRAFT.md` 的种子计划小节），建议补半句同口径限定，避免审稿人把不完备情形算作反例。

另：`docs/PAPER_METHODS_DRAFT.md` 已定稿并冻结（round 2 通过）。若 round 2 的正文需要引用 Methods 的具体小节号，
可直接按 `2.1`-`2.8` 与文末 `Supplementary note S1` 引用，不再改动该文件。
