# 核验报告：manuscript-v1（round 1）

- verdict: **needs_rework**（round 2，四项最小修复；其余全部通过）
- updated: 2026-09-19
- 依据：servant `report.md`（round 1，13:59）+ master 独立复跑与文件级核验（本轮全部探针可复现）
- 核验尺度：纯文档任务，故采用「master 复跑 + 逐锚点抽查 + 与备份/源产物逐值比对」；无代码改动，不需要服务器复跑。
  唯一的实测项（引擎确定性）由 master 在本地重跑并逐字节比对 digest。

## 1. 逐条核验（task.md §3）

| 条目 | 结论 | 关键证据 |
| --- | --- | --- |
| P0-1 `docs/SEED_PLAN_ANALYSIS.md` | **通过（有 1 处必修，见 D1）** | 220 行；§1 W(s) 复现含 `seed_plan.cpp` 真实行号；§2 网格表 16 行与 JSON **逐值一致（0 处不符）**；§3 确定性表 4 个 digest 由 master 重跑复现；§4 复杂度引两个 extract 脚本真实行；§5 写明「未发现差异」 |
| P0-2 `docs/PAPER_DRAFT.md` | 通过 | Title=候选 A；Abstract 单段 221 词（`[A-Za-z][A-Za-z-]*`），无引用编号，`15 published design tools` 已改，含「no experimental validation」句；Introduction 按 P1/P2/P3；缺口 (a) 引 ALLEGRO 原文（master 在 `ALLEGRO-2025-nar.txt` 中逐词命中，含去连字符还原）；Discussion 6 条局限 + C7 声明齐备 |
| P0-3 `docs/PAPER_RESULTS_DRAFT.md` | 通过 | 8 个小节按 C8 顺序、无编号；每个数字带出处；案例小节保留标题 + `[TO FILL]` 令牌，未用别的位点凑数 |
| P0-4 `docs/PAPER_FIGURE_CAPTIONS.md` | **通过（有 1 处必修，见 D2）** | Figure 1-6 + S1 齐备，每张含 Content/Source/Scope；Figure 3 图注写明 `unknown` 不等于 `no`；但 3 处出处路径写错目录（D2） |
| P0-5 `docs/PAPER_TABLES_SUPP.md` | 通过 | Table S1 与 `docs/expressiveness_matrix.tsv` **逐行逐格一致（16 行 × 前 8 列 0 处不符，行序相同）**；S2 16 数据行与 JSON 一致；S3 = REPORT.md 两表合并；S4/S5 分别溯至 `MODELS.md` / `OUTPUTS.md` |
| P0-6 `docs/PAPER_REFERENCES.md` | **通过（有 1 处补强，见 D3）** | [1]-[20] 的 DOI 与大纲 §2.1 先例表**逐条一致**；1..20 全部被正文引用；无越界编号；但 4 个被复刻模型的原始论文缺位（D3） |
| P1-1 `docs/FIGURE_TABLE_PLAN.md` | 通过 | 编号改为 C5 固定值（6 主文图 + Figure S1 + Table S1-S5）；「7 个能力列」已改 6；删除「破例」条款；引用位置列齐备 |
| P1-2 `docs/EXPRESSIVENESS_MATRIX.md` | 通过 | 与备份 diff = **仅第 1 行** `Table 3` -> `Figure 3` |
| P1-3 `docs/PAPER_BACK_MATTER.md` | 通过 | 与备份 diff = 6 处，逐一对应 wiki->`docs/`、S2/S3 序号对调、`6 个能力列`、Figure S1 固定化；无多余改动 |
| P1-4 `docs/PAPER_FRONT_MATTER.md` | 通过 | 与备份 diff = 2 处（摘要 `16`->`15`、§5 口径对齐）；禁词命中为**原稿既有规则陈述行**，本轮未新增（diff 证实） |

## 2. master 独立验证（原文）

### 2.1 文件与编码

```text
docs/SEED_PLAN_ANALYSIS.md        13177 B  220 行  BOM=False CR=0 repl=0
docs/PAPER_DRAFT.md                9669 B  129 行  BOM=False CR=0 repl=0
docs/PAPER_RESULTS_DRAFT.md       14438 B  225 行  BOM=False CR=0 repl=0
docs/PAPER_FIGURE_CAPTIONS.md      7708 B  142 行  BOM=False CR=0 repl=0
docs/PAPER_TABLES_SUPP.md         14384 B  146 行  BOM=False CR=0 repl=0
docs/PAPER_REFERENCES.md          12263 B  128 行  BOM=False CR=0 repl=0
```

禁词扫描（word-boundary，含中文词）：6 个新增件与 `FIGURE_TABLE_PLAN.md`/`EXPRESSIVENESS_MATRIX.md`/`BACK_MATTER.md` 全为 0 命中；
`PAPER_FRONT_MATTER.md` 命中 3 个中文词，经与 `backup/2026-09-19_manuscript-v1/` 逐行 diff 证实为**上一任务原稿既有**（禁用词清单行与自检声明行），本轮未引入。

### 2.2 边界核验（未越界改动）

```text
backup/2026-09-19_manuscript-v1/ 存在 4 个文件（mtime 与开工前一致）
10:55 之后在 docs/ tools/ native/ shared/ example/ 及仓库根下的改动 =
  docs/SEED_PLAN_ANALYSIS.md, docs/PAPER_DRAFT.md, docs/PAPER_RESULTS_DRAFT.md,
  docs/PAPER_FIGURE_CAPTIONS.md, docs/PAPER_TABLES_SUPP.md, docs/PAPER_REFERENCES.md,
  docs/FIGURE_TABLE_PLAN.md, docs/EXPRESSIVENESS_MATRIX.md, docs/PAPER_BACK_MATTER.md,
  docs/PAPER_FRONT_MATTER.md
  （另有 methods-draft 任务自己的 docs/PAPER_METHODS_DRAFT.md 11:03 与 docs/handoff/methods-draft/* —— 属另一会话，非本任务）
仓库根无残留临时文件（servant 自述的 seed_plan_refs_tmp.json / _tmp_edit_manuscript.py 已删，核实通过）
tools/ native/ shared/ example/ 零改动
```

### 2.3 确定性证据（master 重跑，逐字节）

```text
python tools\seed_plan_sweep.py --determinism
threads=1  hits=36 sha256=0549c426662a2fa2994b8696971c51366f330456ed7392adaa58d7be62cbf499
threads=4  hits=36 sha256=0549c426662a2fa2994b8696971c51366f330456ed7392adaa58d7be62cbf499
threads=8  hits=36 sha256=0549c426662a2fa2994b8696971c51366f330456ed7392adaa58d7be62cbf499
threads=32 hits=36 sha256=0549c426662a2fa2994b8696971c51366f330456ed7392adaa58d7be62cbf499
sha256_all_equal: true (1 distinct values)
```

与 `docs/SEED_PLAN_ANALYSIS.md:142-150`、`docs/PAPER_RESULTS_DRAFT.md:147-150` 的记载**逐字符一致**。

### 2.4 数据一致性（以源产物逐值比对）

```text
SEED_PLAN_ANALYSIS.md §2 网格表：16 行全部比对，0 处不符
  （列：k/M/B/s*/W(s)/guaranteed/segments/median/candidates/hits/RSS/repeats-consistent）
PAPER_TABLES_SUPP.md Table S1：16 数据行，行名与顺序 = TSV 完全一致，前 8 列 0 处不符
k=8  (M,B)=(3,1)：W=10734, median=12.404 s, hits=67, cand=67   [seed_plan_sweep.json]
k=10 (M,B)=(3,1)：W=7352,  median=1.082 s,  hits=66, cand=66   [seed_plan_sweep.json]
全部 16 条：seed_plan_guaranteed / exhaustive_seed_plan / py_plan_guaranteed / repeats_consistent 均为 true；candidates == hits 恒成立
k=8 median 区间 0.202-12.404 s；k=10 median 区间 0.205-1.082 s（与 Results 正文一致）
```

MODELS.md 抽查：`0.6321092247962952`(:26)、`2.98e-7`(:47)、`561/947` + `0.993` + `0.0073`(:80-81)、
`55.699318/53.469837` -> `55.699310/53.469837`(:56-57) 全部命中，行号锚点正确。
REPORT.md 行号抽查：`:15` = native-indexed 行、`:16-20` = 其余引擎行、`:22-23` = exact 不可比说明、
`:32-36` = bulge 表、`:38-39` = bulge 限定句、`:43-48` = 200 Mbp 自动规则、`:52-54` = 1-mismatch 召回，全部正确。
NATIVE_INDEXED_BENCHMARK.md 抽查：1.37->0.16 s(8.6x)、81.14->2.85 s(28.5x)、34.0->204.0 MiB、32.0->212.0 MiB、1000 命中、160 命中，全部命中。

### 2.5 源码锚点抽查（`SEED_PLAN_ANALYSIS.md` 的信任基础）

```text
seed_plan.cpp:33-44 binomial ✓ | :46-52 power_three ✓ | :54-61 partition_lengths（余数给前段）✓
            :63-69 segmented_variant_work（含窗口因子）✓ | :105-121 variant_count ✓
            :123 build_seed_plan ✓ | :126 (void)seed_len; ✓ | :130-132 seed_count 区间 ✓
            :151,155 denominator/allowed ✓ | :158-172 超上限跳过 ✓ | :180-187 (W(s), s) 择优 ✓
            :190-199 退化整段 + guaranteed=false ✓ | :239-246 for_each_seed_variant ✓
extract_complex_queries.py:51-52 反向互补 ✓ | :84-91 表头含 left/right_target_start,end ✓
            :103-108 四种链向 ✓ | :118-125 bisect 窗口 ✓ | :140-143 去重键 ✓
extract_motifs.py:11-12 距离语义 ✓ | :37-58 Y 双链 + 回文去重 ✓ | :136-137 L/R ✓
            :144-145 min_left/min_right ✓ | :149-160 校验并 exit 1 ✓
shared/search/iupac.py:33 find_all_iupac_matches ✓ | :40 find_all_iupac_positions ✓
```

### 2.6 图表编号与引用顺序（C5）

```text
docs/PAPER_DRAFT.md         : Figure 1, Figure 2（Introduction，位于 Results 之前）
docs/PAPER_RESULTS_DRAFT.md : Figure 2, Figure 3, Table S1, Figure 4, Figure 5, Table S2,
                              Figure 6, Table S3, Table S4, Figure S1, Table S1->Table S5 末位
判定：Figure 1->6 升序、Table S1->S5 升序、Figure S1 落在案例小节 —— 全部满足 C5 的升序要求。
      Methods（PAPER_METHODS_DRAFT.md）当前无图表引用，故「Methods 只引 Figure 1/2」自动满足（servant 已记录）。
```

### 2.7 参考文献溯源

```text
PAPER_REFERENCES.md 条目数 26；[1]-[20] 与大纲 §2.1 先例表逐条对齐（DOI 20/20 命中，顺序一致）
正文引用编号集合 = 1..26 全覆盖，1..20 无一遗漏；越界编号 0（`[0]` 系 `index_builds[0]` 锚点误匹配，见 servant 附带发现 5，已确认）
```

## 3. 归属判定（既有问题 vs 本次引入）

- 四个修改件全部有 `backup/2026-09-19_manuscript-v1/` 基线：diff 显示只含规格要求的改动，**未引入无关变更**。
- `PAPER_FRONT_MATTER.md` 的禁词命中为**上一任务既有**，非本次引入（diff 证实），不计缺陷。
- 仓库根临时文件已清理，**无残留**。
- 本任务未触碰 `tools/`、`native/`、`shared/`、`example/` 与任何代码；`docs/seed_plan_sweep.json` 只读未被改写（内容与 master 核验值一致）。

## 4. 缺陷清单

### D1 [P1，必修] `docs/SEED_PLAN_ANALYSIS.md:128` 与自身表格及 JSON 矛盾

- 现存文字：`命中数随预算单调上升：(0,0) 为 24，(3,1) 为 66（k=8 与 k=10 同值）`
- 事实：`docs/seed_plan_sweep.json` 中 k=8 的 `(M,B)=(3,1)` 命中共 **67** 个（k=10 才是 66）；
  同一文件 `:103` 的表格行写的正是 `... | 12.404 | 67 | 67 | ...`，`:111` 写 66；
  `docs/PAPER_RESULTS_DRAFT.md:113` 与 `docs/PAPER_TABLES_SUPP.md:56` 也都写 67（k=8）/ 66（k=10）。
- 判定：证据文档内部自相矛盾 + 与源数据不符，属**事实性错误**，必须修。
- 修法：把 `:128` 改为「`(0,0)` 为 24，`(3,1)` 为 67（k=8）与 66（k=10）」，与 `:103`/`:111`、Results、Table S2 口径统一。

### D2 [P2，必修] `docs/PAPER_FIGURE_CAPTIONS.md` 3 处出处路径目录写错

- `:50`、`:58`、`:62` 写作 `[tools/expressiveness_matrix.tsv:...]`，而该文件实际位于 `docs/expressiveness_matrix.tsv`
  （`tools/` 下无此文件，master 已用路径存在性扫描确认）。
- 修法：三处改为 `docs/expressiveness_matrix.tsv`（或统一用与 `docs/PAPER_DRAFT.md` 一致的短名 `expressiveness_matrix.tsv`），
  行号 `1-17` / `3,8,9,15` / `9-17` 经核对正确，保留。

### D3 [P2，必修] 被复刻模型的原始论文缺位（C4 由 master 定向放宽）

- `docs/PAPER_RESULTS_DRAFT.md` 的打分小节与 `Table S4` 描述了 DeepCRISPR / Azimuth / DeepCpf1 / CRISPR-M
  四个已发表模型的复刻与复现误差，但 `docs/PAPER_REFERENCES.md` 只收了 TnpB 侧（[14][25][26]），
  这四个模型的原始论文没有编号 —— NAR 审稿人核对「复刻了谁的模型」时必然要引。
- 原因：C4 把可引文献限定为仓库内已有来源，而这四篇的 DOI 不在仓库中 → servant 依约未引，处理正确。
- master 裁定：**定向放宽 C4**，只允许新增下列 4 篇（其余仍受 C4 约束），由 servant 经 Europe PMC 解析书目字段：
  ① Azimuth（Doench 等，Nat Biotechnol 2016，期望标题含 `Optimized sgRNA design to maximize activity and minimize off-target effects`）
  ② DeepCRISPR（Chuai 等，Genome Biol 2018，期望标题含 `DeepCRISPR: optimized CRISPR guide RNA design by deep learning`）
  ③ DeepCpf1（Kim 等，Nat Biotechnol 2018，期望标题含 `Deep learning improves prediction of CRISPR-Cpf1 guide RNA activity`）
  ④ CRISPR-M（以 `docs/MODELS.md` / `docs/SCORING_GUIDE.md` 记录的来源为准；若仓库未记录，按同一方式解析标题）
- 要求：每条必须写明 DOI 与「DOI 来源」，并在正文打分小节与 `Table S4` 相应位置补引用；
  **解析不到就写 `[TO FILL]`，不得编造**。master 将在 round 2 用 DOI 反查核对。

## 5. master 对 report「待明确」7 条的裁定

1. **标题**：确认候选 A（`CRISPR-Motif Workbench: a constraint-driven guide design platform with a native indexed off-target engine`）。
   工具名待定后同步 `[TO FILL 工具名]` 的位置清单由 master 维护，本轮不动。
2. **参考文献条数**：§5 的 45-70 是**推荐值不是契约**，C4 才是契约。本轮维持 26 条 + D3 的 4 篇（共 30 条），
   不因条数少打回；后续需要扩引时由 master 提供定向 DOI 清单（与 D3 同法处理）。
3. **`scy-test/` 是否授权**：**本轮不授权**，Results 案例小节与 Figure S1 继续保留 `[TO FILL]`。
   理由：该目录的数据由更早的代码状态产生，若要写进论文需先确定「生成命令 + 版本」的溯源说法；
   这是**用户决策**，由 master 在核验回复中向用户提出，不要求 servant 猜。
4. **wiki 措辞**：维持改写为仓库 `docs/` 路径（依据 `nar-format-pack/review.md` 第 5 条），无需回改。
5. **仓库 URL / Zenodo DOI / accession / keywords**：一律保持 `[TO FILL]`，属外部信息，由 master 向用户索取。
6. **Notes S1 / Notes S2**：本轮不做。S1（源码对照说明）由 methods-draft round 2 移入；S2（`.ggi` v1 规格）
   待 master 另开条目，不在本轮范围。
7. **摘要数字**：维持「不补基准数字」，两篇范本摘要均为定性表述。

## 6. 冒烟级正面确认（供后续使用）

- `docs/PAPER_DRAFT.md` + `docs/PAPER_RESULTS_DRAFT.md` + `docs/PAPER_METHODS_DRAFT.md` 三件已可顺序通读为
  「Introduction -> Materials and Methods -> Results -> Discussion」的完整稿（缺 Figure/Table 美术稿与 Supplementary Notes）。
- 论文两个头号贡献均已落在正文：C1 的表达力矩阵（Figure 3 + Table S1）与 C2 的种子计划完备性/确定性
  （Figure 5 + Table S2 + `0549c426...` digest），且都有可复跑的出处。
- Pattern A/B 的差异表述落在布局语义（`Target-xbp-Target` vs `Target-xbp-Motif-ybp-Target`，`:136-137,144-145` 双侧独立区间），
  未退化成「我们有两个模式」这类已被 ALLEGRO 覆盖的说法 —— C2 措辞红线守住。

## 7. 下一步（round 2 只做这 3 件 + 2 个可选项）

1. D1：`docs/SEED_PLAN_ANALYSIS.md:128` 改为「`(3,1)` 为 67（k=8）与 66（k=10）」。
2. D2：`docs/PAPER_FIGURE_CAPTIONS.md:50,58,62` 的 `tools/expressiveness_matrix.tsv` 改为 `docs/expressiveness_matrix.tsv`。
3. D3：按 §4 的定向清单给 `docs/PAPER_REFERENCES.md` 补 4 篇模型原始论文（[27]-[30]），
   并同步 `docs/PAPER_RESULTS_DRAFT.md` 打分小节与 `docs/PAPER_TABLES_SUPP.md` 的 Table S4。

可选（不阻塞）：
- N1 `docs/PAPER_DRAFT.md` 的 ALLEGRO 第二处引文为截断引用，句末建议加省略号或改用完整句。
- N2 `docs/PAPER_RESULTS_DRAFT.md` 的 `O(n_left log n_right + P)` 建议补半句，说明右位点数组的排序
  （`extract_complex_queries.py:118` 的组合内 `sorted`）也计入代价。

round 2 自检下限：D1 改后重跑一次「`SEED_PLAN_ANALYSIS.md` 表格 + 正文数字 vs `docs/seed_plan_sweep.json`」的逐值比对；
D2 改后重跑一次出处路径存在性扫描（每种 `[path:...]` 锚点必须落到真实文件）。命令可沿用 servant 本轮已写的方式。
交付：`state.json` 置回 `ready_for_review`（`round: 2`），`report.md` **追加** round 2 小节；核验仍归 master。


---

# 核验报告：manuscript-v1（round 2）

- verdict: **pass**
- updated: 2026-09-19 15:00
- 依据：`report.md` round 2 小节（14:37）+ master 独立复核（与 `backup/2026-09-19_manuscript-v1-r2/` 逐行 diff、
  自写探针、以及 **Crossref 反查 4 篇新增文献的 DOI**）

## 1. 逐条核验

| 条目 | 结论 | master 证据 |
| --- | --- | --- |
| D1 `SEED_PLAN_ANALYSIS.md:128` | 通过 | diff 唯一 1 个 hunk：`(3,1) 为 66（k=8 与 k=10 同值）` -> `(3,1) 为 67（k=8）与 66（k=10）`；与 JSON（k=8=67 / k=10=66）及同文件 `:103`/`:111` 表格行一致 |
| D2 `PAPER_FIGURE_CAPTIONS.md:50,58,62` | 通过 | diff 恰好 3 个 hunk，`tools/expressiveness_matrix.tsv` -> `docs/expressiveness_matrix.tsv`；行号段未动；全仓已无 `tools/expressiveness_matrix.tsv` 残留 |
| D3 补 4 篇模型原论文 | 通过（DOI 已反查） | [27]-[30] 已入表并在正文打分小节与 Table S4 引用；master 用 Crossref 逐条反查，标题/期刊/年/卷/期/页与条目**逐字段一致** |
| §8.1-4 Notes S1 描述对齐 | 通过 | `PAPER_BACK_MATTER.md:34` diff 唯一 1 个 hunk，改为「…详细数学表述，含实现与规格写法的对应说明（source correspondence）；主文只留结论与引用」，与 `PAPER_METHODS_DRAFT.md` 文末 S1 的实际内容一致 |
| 可选 N1 ALLEGRO 截断引文 | 通过 | `PAPER_DRAFT.md:52` 句末补 ` ...`；该引文其余部分 master 已在 `ALLEGRO-2025-nar.txt` 中逐词命中 |
| 可选 N2 复杂度句补排序项 | 通过 | `PAPER_RESULTS_DRAFT.md:71-74` 补「The bound also carries the one-off cost of sorting the right-position array before those binary searches [extract_complex_queries.py:118]」；`:118` 的 `right_sorted = sorted(right_positions)` 已回读确认 |
| 可选 §8.1-5 A/C/G/T 限定 | 通过 | 三处落点齐备：Abstract（`:28`）、Introduction C2 段（`:86-90`）、Results 种子计划小节（`:108-112`，引 `[PAPER_METHODS_DRAFT.md:2.5]`）；措辞与引理 1 的新假设及 `NATIVE_INDEXED_ENGINE_DESIGN.md:378-379` 一致 |

## 2. master 独立验证（原文）

### 2.1 D3 的四条 DOI 反查（Crossref REST，master 自跑；servant 与 master 走的是**不同**的文献通道）

```text
10.1038/nbt.3437
   title: Optimized sgRNA design to maximize activity and minimize off-target effects of CRISPR-Cas9
   journal: Nature Biotechnology | year: 2016 | vol 34 issue 2 page 184-191
   [27] 条目原文: Nat Biotechnol 2016;34(2):184-191   -> 一致

10.1186/s13059-018-1459-4
   title: DeepCRISPR: optimized CRISPR guide RNA design by deep learning
   journal: Genome Biology | year: 2018 | vol 19 issue 1
   [28] 条目原文: Genome Biol 2018;19(1):80                -> 一致（80 为文章号）

10.1038/nbt.4061
   title: Deep learning improves prediction of CRISPR-Cpf1 guide RNA activity
   journal: Nature Biotechnology | year: 2018 | vol 36 issue 3 page 239-241
   [29] 条目原文: Nat Biotechnol 2018;36(3):239-241     -> 一致

10.1371/journal.pcbi.1011972
   title: CRISPR-M: Predicting sgRNA off-target effect using a multi-view deep learning network
   journal: PLOS Computational Biology | year: 2024 | vol 20 issue 3 page e1011972
   [30] 条目原文: PLoS Comput Biol 2024;20(3):e1011972 -> 一致
```

[30] 的溯源链另行核实：`shared/scoring/model_registry.py` 的 `MODELS["crispr_m"]` 记录
`"name": "CRISPR-M"`、`"file": "tcrispr_model.h5"`、`"url": .../lyotvincent/CRISPR-M/master/test/7visualization/tcrispr_model.h5`，
与 [30] 条目注记的 DOI 来源一致；该 DOI 反查回来的标题正是 CRISPR-M 论文。**无编造。**

### 2.2 改动范围（与 round 2 开工快照逐行 diff）

```text
SEED_PLAN_ANALYSIS.md        old 220 -> new 220  hunks 1  +1 -1
PAPER_FIGURE_CAPTIONS.md     old 142 -> new 142  hunks 3  +3 -3
PAPER_REFERENCES.md          old 128 -> new 151  hunks 6  +34 -11
PAPER_RESULTS_DRAFT.md       old 225 -> new 230  hunks 3  +23 -18
PAPER_TABLES_SUPP.md         old 146 -> new 150  hunks 4  +8 -4
PAPER_BACK_MATTER.md         old  61 -> new  61  hunks 1  +1 -1
PAPER_DRAFT.md               old 129 -> new 130  hunks 3  +7 -6
```

hunk 数与 `report.md` 自报**完全一致**；逐 hunk 回读内容均落在规格要求内，无范围外改动
（未动案例小节、未动 `[TO FILL]` 字段、未动 round 1 已通过的任何句段）。

### 2.3 编码与结构性检查（master 自写探针）

```text
7 个受改文件: BOM=False, CR=0, U+FFFD=0
C2 禁词扫描: 全部 0 命中（first / never / unprecedented / novel / 首创 / 首次 / 从未）
摘要: 232 词、单段、无引用编号（区间 170-250，含新增的 A/C/G/T 限定；round 1 的 15-tools 修订仍在）
参考文献: 条目恰为 [1]-[30] 每行一条；正文引用覆盖 1..30 无缺失、无越界
锚点存在性: 除 SEED_PLAN_ANALYSIS §4 的短名（`extract_*_py`，该节开头已给全路径，属既有写法）外全部解析成功
行号锚点: 无越界；受改稿件之间不存在互相引用的数字行号，故不存在行号漂移
```

### 2.4 边界核验

```text
14:20 之后被写入的文件 = 7 个受改稿件 + assets/servant_round2_selfcheck.py + report.md + state.json
tools/ shared/ example/ native/ 零改动
docs/PAPER_METHODS_DRAFT.md mtime 仍为 11:03:08（methods-draft round 2 交付时间）—— 冻结件未被触碰
开工快照 backup/2026-09-19_manuscript-v1-r2/ 含 7 个文件的改动前副本，内容与 diff 的 old 侧逐行吻合
servant 自检探针 assets/servant_round2_selfcheck.py 由 master 复跑：RESULT: ALL PASS (0 failing checks)
```

## 3. 非缺陷的观察（记录，不需改）

1. `SEED_PLAN_ANALYSIS.md:159` 有中文词「digest 唯一」，语境是「四个线程数命中行逐字节相同，digest 唯一」，
   属技术描述而非新颖性主张；该词也不在本任务 C2 的禁用清单内。可接受。
2. Table S4 未新增 DeepCpf1 行，而在 Notes 里用一句话把 DeepCpf1 与 [29] 挂上 —— 理由是 S4 的行集合是
   `docs/MODELS.md` 清单表的逐字快照，加行会改变口径。master 认可这一处置。
3. `PAPER_BACK_MATTER.md:34` 的「来源」列仍指向 `PAPER_METHODS_DRAFT.md` 2.4 / 2.5，规格只要求改内容描述；
   该列的「待撰写」状态维持不变（Notes S1 的具体文稿尚未成文，属后续工作）。

## 4. 剩余未决（不属本轮缺陷）

1. Results 案例小节与 Figure S1 的取舍 —— **master 14:50 更正框定**：`scy-test/` 里唯一的「数据」是公共参考序列
   （`scy-test/blastdb/GCF_000001405.40_GRCh38.p14_genomic.blastdb`，787 MB），其余约 66 GB / 10,389 个文件
   （122 个 `*_scores.tsv`、123 个 `*_offtargets.tsv`、112 个 `*_blast_results.tsv`、9,739 个 `.fa` 中间件）
   全部是程序自身输出，跨 9/2-9/19 多次运行、命名不一致且无生成命令/版本记录；位点 FASTA 头只有 `>PPP1R12C-intron1`，
   无坐标与基因组版本，仓库文档中亦无坐标记录（grep 0 命中）。故它不是「第三方数据源」，不能作独立验证，
   只能作 use-case demonstration。真正待用户拍板的是：删掉该小节（方案 A），或按记录在案的命令重跑一次（方案 B）。
   **结论（用户 2026-09-19 拍板）：方案 A** —— 删除案例小节与 Figure S1，`scy-test/` 不作为任何来源；
   落地任务为 `docs/handoff/manuscript-v2/`（task.md 的 P0-1..P0-4）。
2. 仓库 URL / Zenodo 版本 DOI / accession / keywords —— **待用户提供**。
3. Notes S1（成文稿）与 Notes S2（`.ggi` v1 规格）—— 尚未成文，由 master 另开条目。
4. 主文图 1-6、Figure S1、图形摘要的美术稿 —— 未绘制（本链路只出清单、图注与表体）。
5. 三份稿件文件（`PAPER_DRAFT.md` / `PAPER_METHODS_DRAFT.md` / `PAPER_RESULTS_DRAFT.md`）尚未合成单一投稿稿，
   也未按 NAR 版式组装 figure/table/back matter —— 建议作为后续任务 `manuscript-v2`（合稿与投稿要件收尾）。

## 5. 结论

round 2 **通过**：D1/D2/D3 三项必修与 §8.1-4 必修项全部落地，N1/N2 与 §8.1-5 可选项亦已落地；
改动范围最小、可逐条追溯、DOI 经独立通道反查无误、无越界改动。
`state.json` 置 `done`。7 个受改文件自本条核验起冻结；后续改动需新开任务。

## 6. master 追加复核（本轮独立复跑，结论不变：pass）

第 1-5 节写就后，本轮再次独立复跑，不采信任何转述：

```text
master 自写探针 assets/master_recheck_r2.py（difflib 与 round-2 快照逐行比对）
  SEED_PLAN_ANALYSIS.md   1 hunk  +1 -1       PAPER_FIGURE_CAPTIONS.md 3 hunks  +3 -3
  PAPER_REFERENCES.md     6 hunks +34 -11     PAPER_RESULTS_DRAFT.md   3 hunks +23 -18
  PAPER_TABLES_SUPP.md    4 hunks  +8 -4      PAPER_BACK_MATTER.md     1 hunk   +1 -1
  PAPER_DRAFT.md          3 hunks  +7 -6      TOTAL 21 hunks —— 与 report.md 自报一致
复跑 servant 探针 assets/servant_round2_selfcheck.py -> RESULT: ALL PASS (0 failing checks), exit 0
Crossref 独立反查 [27]-[30]：标题/期刊/年/卷/页逐字段命中
  （DeepCRISPR 条目 Crossref 无 page 字段，条目标 19(1):80，与 Europe PMC 一致）
规格点回读：SEED_PLAN_ANALYSIS.md:128、PAPER_FIGURE_CAPTIONS.md:50,58,62、PAPER_BACK_MATTER.md:34
  N1 省略号、N2 排序项、A/C/G/T 限定三处落点（PAPER_DRAFT.md:28/:87、PAPER_RESULTS_DRAFT.md:109）全部命中
边界：tools/ shared/ native/ example/ Target_xbp_*/ webapp/ 与仓库根文件在 14:20 后改动数均为 0；
  docs/PAPER_METHODS_DRAFT.md mtime 仍为 11:03:08（冻结件未被触碰）
```

新增两条观察（不改变本轮判定）：

1. `docs/PAPER_REFERENCES.md` 全部 30 条参考文献均带 `<!-- ... -->` 溯源注释（共 30 处）。这是工作稿的溯源约定，
   非本轮引入的问题；但投稿稿必须剥离，已列为 `manuscript-v2` 的必做项。
2. [27]-[30] 的编号顺序沿用 master 给定的模型清单顺序（Azimuth / DeepCRISPR / DeepCpf1 / CRISPR-M）；
   与正文首次引用顺序的对应关系留待合稿时统一。
