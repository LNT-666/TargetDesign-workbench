# 交付报告 — manuscript-v1（servant，round 1）

- 任务书：`docs/handoff/manuscript-v1/task.md`
- 执行者：会话 S（servant）；执行日期：2026-09-19
- 基线：新增 6 个文件、修改 4 个文件。开工前已把 4 个待改文件复制到 `backup/2026-09-19_manuscript-v1/`（只这 4 个，无整仓复制）。
- 说明：本报告只陈述改动与证据，**不做「通过」裁定**（核验归 master）。

## 1. 新增文件

| 文件 | 条目 | 行数 | 内容摘要 |
| --- | --- | --- | --- |
| `docs/SEED_PLAN_ANALYSIS.md` | P0-1 | 220 | 5 节：① W(s) 复现（引用 `seed_plan.cpp` 真实行号，覆盖 `build_seed_plan` / `partition_lengths` / `segmented_variant_work` / `binomial` / `power_three`）② 16 组 `(k, M, B)` 网格表（`s*`、`W`、guaranteed 标记，由 `docs/seed_plan_sweep.json` 程序化生成）③ 确定性表（`--determinism` 实跑 4 线程数 hits 与 sha256）④ 组合复杂度与剪枝（引用 `Target_xbp_Target/extract_complex_queries.py`、`Target_xbp_Y_zbp_Target/extract_motifs.py`）⑤ 与 task.md §2.4 `cost_model` 逐项对照，结论「未发现差异」（另记 2 处展开说明：variant 上限、tie-break 规则） |
| `docs/PAPER_DRAFT.md` | P0-2 | 129 | Title（候选 A）/ Abstract / Introduction / Discussion。Abstract 搬 `docs/PAPER_FRONT_MATTER.md` 现稿，仅按 C6④ 改 1 处；Introduction 按 `docs/PAPER_OUTLINE.md:143-147` 的 P1/P2/P3，缺口段 (a) 引 ALLEGRO Discussion 原文作外部佐证（[17]）；Discussion 6 条局限逐条落下并含 C7 声明 |
| `docs/PAPER_RESULTS_DRAFT.md` | P0-3 | 225 | C8 的 8 个无编号描述性小节，顺序照录；第 7 节内容为令牌 `[TO FILL: 案例数据未在仓库中]` + 说明（保留小节标题与 Figure S1 引用，未删节、未用别的位点凑数） |
| `docs/PAPER_FIGURE_CAPTIONS.md` | P0-4 | 142 | Figure 1-6 与 Figure S1 英文图注，每张含 内容 / 数据来源 / 样本量与口径；Figure 3 图注写明 `unknown` 不等于 `no` |
| `docs/PAPER_TABLES_SUPP.md` | P0-5 | 146 | Table S1（`docs/expressiveness_matrix.tsv` 直转，16 数据行 x 10 列，保留 `evidence` 列）/ S2（`docs/seed_plan_sweep.json` 16 条记录 + `index_builds` 表）/ S3（`REPORT.md` 两表合并，附 1-mismatch 召回）/ S4（`docs/MODELS.md`）/ S5（`docs/OUTPUTS.md` 分组） |
| `docs/PAPER_REFERENCES.md` | P0-6 | 128 | 26 条编号文献：[1]-[20] = `docs/PAPER_OUTLINE.md` 第 2.1 节先例表顺序，[21]-[24] = 表达力矩阵独有工具（GuideScan2 / CRISPOR / Breaking-Cas / EuPaGDT），[25]-[26] = TnpB 相关；附覆盖表 |

## 2. 修改文件（行号为改后编号）

| 文件 | 行号 | 改动 | 条目 |
| --- | --- | --- | --- |
| `docs/FIGURE_TABLE_PLAN.md` | 全文重写（79 行） | 编号由暂定值改为 C5 固定值：11-16 行 Figure 1-6；18 行 Figure S1；24-32 行旧->新编号映射；36-44 行正文引用顺序表；46 行 Methods 引用约束；48-58 行「主文表 = 0」与 Table S1-S5（按首次引用顺序）；62-68 行原 Table 1-5 逐条判定；75 行 Figure 3 口径（6 个能力列 / 10 列）；状态列按实际状态改写；删除「破例」条款与「首次」措辞 | P1-1 |
| `docs/EXPRESSIVENESS_MATRIX.md` | 1 | 标题 `Table 3` -> `Figure 3` | P1-2（C6③） |
| `docs/PAPER_BACK_MATTER.md` | 25 | Supplementary 清单抬头：改「编号已按 C5 固定，权威清单见 `docs/FIGURE_TABLE_PLAN.md`」 | P1-3② |
| `docs/PAPER_BACK_MATTER.md` | 29 | Table S1 描述「7 个能力列」->「16 数据行 x 10 列 = 3 个元数据列 + 6 个能力列 + 1 个证据列」 | P1-3③（C6②） |
| `docs/PAPER_BACK_MATTER.md` | 30-31 | Supplementary 表序号重排：S2 = 种子计划网格、S3 = 跨引擎基准（原文件为 S2 跨引擎 / S3 种子计划，与 C5 相反）；状态列对齐 `docs/FIGURE_TABLE_PLAN.md` | P1-3② |
| `docs/PAPER_BACK_MATTER.md` | 36 | Figure S1 行：由「Figure S1 起 / 如需 / 待 master 决定」改为固定内容「案例位点候选分布与 PairRank 分层」，来源 `scy-test/` 标 `[TO FILL]` | P1-3② |
| `docs/PAPER_BACK_MATTER.md` | 51 | Data availability 第 3 句 wiki 措辞 -> 仓库 `docs/` 路径：``Documentation is provided in the repository under the `docs/` directory.`` | P1-3① |
| `docs/PAPER_BACK_MATTER.md` | 53 | 第 53 行由「逐词照录」改为「沿用 + 第 3 句按仓库形态改写」，与上一行改动一致 | P1-3① |
| `docs/PAPER_BACK_MATTER.md` | 55 | 同一条款的说明 bullet 同步改写（记录改写理由与回改条件） | P1-3① |
| `docs/PAPER_FRONT_MATTER.md` | 52 | Abstract：`covering 16 published design tools` -> `covering 15 published design tools` | P1-4（C6④） |
| `docs/PAPER_FRONT_MATTER.md` | 62 | 第 5 节口径对齐：改为「15 个已发表工具」，并写明 `docs/expressiveness_matrix.tsv` 实测 17 行 = 表头 + 16 行数据 = 15 个已发表工具 + 本文工作；矩阵为主文 Figure 3（全表为 Table S1） | P1-4 |

## 3. 自检（task.md §6 原文执行，工作目录 `R:\songji\programfile`）

### 3.1 determinism

命令：

```powershell
cd R:\songji\programfile
python tools\seed_plan_sweep.py --determinism
```

输出：

```text
threads=1 hits=36 sha256=0549c426662a2fa2994b8696971c51366f330456ed7392adaa58d7be62cbf499
threads=4 hits=36 sha256=0549c426662a2fa2994b8696971c51366f330456ed7392adaa58d7be62cbf499
threads=8 hits=36 sha256=0549c426662a2fa2994b8696971c51366f330456ed7392adaa58d7be62cbf499
threads=32 hits=36 sha256=0549c426662a2fa2994b8696971c51366f330456ed7392adaa58d7be62cbf499

M=2 B=0 k=10 threads=[1, 4, 8, 32]
hits per thread count: [36, 36, 36, 36]
sha256_all_equal: true (1 distinct values)
```

### 3.2 禁词与词数

命令：

```powershell
python -c "import io,re;d=io.open('docs/PAPER_DRAFT.md',encoding='utf-8').read();print('forbidden',re.findall(r'(?i)\b(first|never|unprecedented)\b',d),[w for w in ['首创','首次','从未'] if w in d]);print('abstract_words',len(re.findall(r'[A-Za-z][A-Za-z-]*',d)))"
```

输出：

```text
forbidden [] []
abstract_words 1419
```

说明：该命令的 `abstract_words` 统计对象是整份 `docs/PAPER_DRAFT.md`（含题名、Introduction、Discussion），故为 1419，不是摘要词数。摘要词数按摘要单段另测（见下）。

### 3.3 摘要词数（摘要单段，附加检查）

命令：

```powershell
python -c "import io,re;d=io.open('docs/PAPER_DRAFT.md',encoding='utf-8').read();p=[x for x in d.split(chr(10)*2) if 'covering 15 published design tools' in x];print('abstract_paragraph_words',len(re.findall(r'[A-Za-z][A-Za-z-]*',p[0])))"
python -c "import io,re;d=io.open('docs/PAPER_FRONT_MATTER.md',encoding='utf-8').read();p=[x for x in d.split(chr(10)*2) if 'covering 15 published design tools' in x];print('front_matter_abstract_words',len(re.findall(r'[A-Za-z][A-Za-z-]*',p[0])))"
```

输出：

```text
abstract_paragraph_words 221
front_matter_abstract_words 221
```

### 3.4 新增 6 个文件与 4 个改动文件：无 BOM、无 `\r`，禁词为空（附加检查）

命令：

```powershell
python -c "
import io,re
files=['docs/SEED_PLAN_ANALYSIS.md','docs/PAPER_DRAFT.md','docs/PAPER_RESULTS_DRAFT.md','docs/PAPER_FIGURE_CAPTIONS.md','docs/PAPER_TABLES_SUPP.md','docs/PAPER_REFERENCES.md','docs/FIGURE_TABLE_PLAN.md','docs/EXPRESSIVENESS_MATRIX.md','docs/PAPER_BACK_MATTER.md','docs/PAPER_FRONT_MATTER.md']
for p in files:
    b=io.open(p,'rb').read(); d=b.decode('utf-8')
    fw=re.findall(r'(?i)\b(first|never|unprecedented)\b',d)
    zh=[w for w in ['首创','首次','从未'] if w in d]
    print(p, 'BOM' if b[:3]==b'\xef\xbb\xbf' else 'noBOM', 'CR=%d'%b.count(b'\r'), 'forbidden=',fw, zh)
"
```

输出：

```text
docs/SEED_PLAN_ANALYSIS.md noBOM CR=0 forbidden= [] []
docs/PAPER_DRAFT.md noBOM CR=0 forbidden= [] []
docs/PAPER_RESULTS_DRAFT.md noBOM CR=0 forbidden= [] []
docs/PAPER_FIGURE_CAPTIONS.md noBOM CR=0 forbidden= [] []
docs/PAPER_TABLES_SUPP.md noBOM CR=0 forbidden= [] []
docs/PAPER_REFERENCES.md noBOM CR=0 forbidden= [] []
docs/FIGURE_TABLE_PLAN.md noBOM CR=0 forbidden= [] []
docs/EXPRESSIVENESS_MATRIX.md noBOM CR=0 forbidden= [] []
docs/PAPER_BACK_MATTER.md noBOM CR=0 forbidden= [] []
docs/PAPER_FRONT_MATTER.md noBOM CR=0 forbidden= [] ['首创', '首次', '从未']
```

`docs/PAPER_FRONT_MATTER.md` 的两处命中见第 5 节第 1 条（规则陈述行，非正文，且与备份原稿逐字相同）。

### 3.5 图表引用顺序与文献覆盖（附加检查）

```text
docs/PAPER_DRAFT.md         ['Figure 1', 'Figure 2']
docs/PAPER_RESULTS_DRAFT.md ['Figure 2', 'Figure 3', 'Table S1', 'Figure 4', 'Figure 5', 'Table S2', 'Figure 6', 'Table S3', 'Table S4', 'Figure S1', 'Figure S1', 'Table S5']
docs/PAPER_METHODS_DRAFT.md []   （本任务只读，未改）
cited numbers in body: 1..26（其中 [0] 系 `index_builds[0]` 误匹配，见第 5 节）
missing 1..20: []
bracket refs in docs/PAPER_REFERENCES.md: 26
```

## 4. 未做项及原因

| 未做项 | 原因 |
| --- | --- |
| 案例小节数据与 Figure S1 数据 | 案例数据仅存在于 `scy-test/`，不在 C3 授权来源列表内；按 task.md §5 决策项保留小节 + `[TO FILL]` |
| 作者 / 单位 / 通讯作者 / ORCID / Funding / accession 填写 | 外部信息，task.md 与前置件均要求不得编造，由 master 向用户索取 |
| 图形绘制（Figure 1-6、Figure S1、图形摘要） | 本轮范围只出清单、图注与表体（`docs/FIGURE_TABLE_PLAN.md` 第 4 节） |
| 参考文献扩到 §5 推荐的 45-70 条 | C4 限定文献只能取自先例表 / 第 2.2 节 / 第六节证据索引与仓库已出现文献；未擅自扩源，实际 26 条（待明确项第 2 条） |
| Notes S1 / Notes S2 撰写 | task.md §3 未列为必做条目 |
| 全量测试套件 / benchmark / 大 fixture | task.md §4 明令禁止 |
| 修改 `docs/PAPER_METHODS_DRAFT.md`、`docs/PAPER_OUTLINE*.md`、`docs/ALLEGRO_REFERENCE_ANALYSIS.md`、任何代码与 `tools/` / `native/` / `shared/` / `example/` | task.md §4 明令禁止 |

## 5. 附带发现（只记录，未修）

1. `docs/PAPER_FRONT_MATTER.md:18` 与 `:47` 出现「首创 / 首次 / 从未」：两行均为**规则陈述行**（禁用词清单与自检声明），不是正文文本，且与 `backup/2026-09-19_manuscript-v1/PAPER_FRONT_MATTER.md` 逐字相同（上一任务原稿既有）。本轮按「最小改动」未动这两行。
2. 本报告与 `docs/handoff/manuscript-v1/task.md` 本身包含三个英文禁用词（自检命令原文与契约条文），任何全仓禁词扫描都会命中，属预期。
3. `docs/PAPER_METHODS_DRAFT.md` 当前不含任何图表引用，C5「Methods 只引用 Figure 1 与 Figure 2」在现状下为自动满足；该文件的改动权属 methods-draft round 2，本轮未动。
4. `scy-test/` 内确实存在 AAVS1 / TRAC / PDCD1 相关数据，但不在 C3 授权来源内，故 Results 第 7 节与 Figure S1 保持 `[TO FILL]`，未取用。
5. `docs/PAPER_RESULTS_DRAFT.md:83` 的 `index_builds[0]` 会被 `\[(\d+)\]` 类引用正则误判为引用 `[0]`；该处是出处锚点，不是引用。
6. `example/engine_benchmark_small/REPORT.md` 的 bulge 表未植入真实 bulge 命中，相关文字（S3、Results 第 4 节）均保留「启用 bulge 的代价而非召回率」限定句。
7. 我在仓库根临时创建过 `seed_plan_refs_tmp.json`（文献 DOI 解析用）与 `_tmp_edit_manuscript.py`（编辑脚本），**均已删除**，未留在交付物中。

## 6. 待明确项

1. 标题：候选 A 待 master 确认；工具名待定后需同步 `docs/PAPER_FRONT_MATTER.md` 与 `docs/PAPER_BACK_MATTER.md` 的 `[TO FILL 工具名]`。
2. 参考文献条数 26 低于 §5 推荐的 45-70：是否放宽 C4 的来源集合由 master 裁定（放宽后我可补引）。
3. `scy-test/` 是否授权为 C3 来源；授权后 Results 第 7 节与 Figure S1 可填数。
4. Data availability 第 3 句已按 `docs/handoff/nar-format-pack/review.md` 的改写要求改为仓库 `docs/` 路径；若 master 决定保留 wiki 措辞，需回改该句与本文件第 55 行说明。
5. GitHub 仓库 URL 与 Zenodo 版本 DOI、keywords 是否必需、accession 是否适用：均为 `[TO FILL]`。
6. `Notes S1` / `Notes S2` 是否纳入本轮或后续轮次。

## 7. 状态

- 本会话已完成 task.md §3 的 P0-1..P0-6 与 P1-1..P1-4 全部条目；未自行裁定「通过」。
- `state.json` 已置 `ready_for_review` 并更新 `updated`。

---

# 交付报告 — manuscript-v1（servant，round 2）

- 依据：`review.md` 第 7 节（3 件必修）+ `task.md` 第 8、8.1 节（必修 D1/D2/D3、§8.1-4；可选 N1、N2、§8.1-5）
- 本轮为**最小修复**：不重写任何 round 1 已通过的内容，不做无关重构
- 开工快照：`backup/2026-09-19_manuscript-v1-r2/`（7 个待改文件的改动前副本，mtime 14:29 前后）

## 8. 修改文件与行号（行号为改后编号；本轮无新增稿件文件）

| 文件 | 改后行号 | 改动 | 规格依据 |
| --- | --- | --- | --- |
| `docs/SEED_PLAN_ANALYSIS.md` | 128 | 「`(3,1)` 为 66（k=8 与 k=10 同值）」→「`(3,1)` 为 67（k=8）与 66（k=10）」 | D1 |
| `docs/PAPER_FIGURE_CAPTIONS.md` | 50 / 58 / 62 | `tools/expressiveness_matrix.tsv` → `docs/expressiveness_matrix.tsv`（行号段 `1-17` / `3,8,9,15` / `9-17` 保留） | D2 |
| `docs/PAPER_REFERENCES.md` | 7-9 / 15-26 / 87-94 / 127-130 / 140-141 / 146-150 | 新增 [27]-[30]（含 DOI 与 DOI 来源注记）；同步总述段、引用纪律段（写明 C4 定向放宽）、引用覆盖表、覆盖检查项、Open item 计数 26→30 | D3 |
| `docs/PAPER_RESULTS_DRAFT.md` | 71-74 / 108-112 / 176-189 | 打分小节四个模型端口各补引用 [27][28][29][30]；复杂度句补「右位点数组排序的一次性代价」；完备性表述补 A/C/G/T 限定 | D3 / N2 / §8.1-5 |
| `docs/PAPER_TABLES_SUPP.md` | 107 / 109 / 111 / 115-119 | Table S4 的 `crispr_m`/`deepcrispr (portable)`/`azimuth (portable)` 三行分别补 [30]/[28]/[27]；Notes 补 DeepCpf1 与 [29] 的说明（该模型不在 MODELS.md 清单表内） | D3 |
| `docs/PAPER_BACK_MATTER.md` | 34 | Notes S1 描述改为「…详细数学表述，含实现与规格写法的对应说明（source correspondence）；主文只留结论与引用」 | §8.1-4 |
| `docs/PAPER_DRAFT.md` | 28 / 52 / 86-90 | Abstract 与 Introduction 的 exhaustive 表述补 A/C/G/T 限定（并重排该段换行）；ALLEGRO 第二处截断引文句末加 ` ...` | §8.1-5 / N1 |

新增的非稿件资产（仅供复跑，非交付稿）：

| 文件 | 说明 |
| --- | --- |
| `docs/handoff/manuscript-v1/assets/servant_round2_selfcheck.py` | 本轮自检探针（D1/D2/C2/编码/文献覆盖一次性复跑，失败即非零退出） |

改动规模（相对 `backup/2026-09-19_manuscript-v1-r2/`，`difflib` 逐行统计）：

| 文件 | 新增行 | 删除行 | 改动块（旧行 → 新行） |
| --- | ---: | ---: | --- |
| `docs/SEED_PLAN_ANALYSIS.md` | 1 | 1 | 128 → 128 |
| `docs/PAPER_FIGURE_CAPTIONS.md` | 3 | 3 | 50/58/62 → 50/58/62 |
| `docs/PAPER_REFERENCES.md` | 34 | 11 | 7 → 7-9；13-18 → 15-26；79 处插入 87-94；111 处插入 127-130；120 处插入 140-141；124-127 → 146-150 |
| `docs/PAPER_RESULTS_DRAFT.md` | 23 | 18 | 71-72 → 71-74；106-107 → 108-112；171-184 → 176-189 |
| `docs/PAPER_TABLES_SUPP.md` | 8 | 4 | 107/109/111 → 同行；115 → 115-119 |
| `docs/PAPER_BACK_MATTER.md` | 1 | 1 | 34 → 34 |
| `docs/PAPER_DRAFT.md` | 7 | 6 | 28 → 28；52 → 52；86-89 → 86-90 |

## 9. D3 新增文献（[27]-[30]，逐条含 DOI 与 DOI 来源）

| 编号 | 短名 | 书目（Europe PMC 解析字段） | DOI | DOI 来源 |
| --- | --- | --- | --- | --- |
| [27] | Azimuth | Doench JG, …, Root DE. Optimized sgRNA design to maximize activity and minimize off-target effects of CRISPR-Cas9. Nat Biotechnol 2016;34(2):184-191. | `10.1038/nbt.3437` | `task.md` §8 D3 给定标题 → Europe PMC REST 检索（2026-09-19） |
| [28] | DeepCRISPR | Chuai G, …, Liu Q. DeepCRISPR: optimized CRISPR guide RNA design by deep learning. Genome Biol 2018;19(1):80. | `10.1186/s13059-018-1459-4` | 同上；作者表另用 Crossref 复核（见 §11 第 3 条） |
| [29] | DeepCpf1 | Kim HK, …, Kim HH. Deep learning improves prediction of CRISPR-Cpf1 guide RNA activity. Nat Biotechnol 2018;36(3):239-241. | `10.1038/nbt.4061` | 同上 |
| [30] | CRISPR-M | Sun J, Guo J, Liu J. CRISPR-M: Predicting sgRNA off-target effect using a multi-view deep learning network. PLoS Comput Biol 2024;20(3):e1011972. | `10.1371/journal.pcbi.1011972` | `shared/scoring/model_registry.py` 的 `MODELS["crispr_m"]["url"]`（GitHub `lyotvincent/CRISPR-M`，其仓库描述与该方法学一致）→ Europe PMC 检索（2026-09-19） |

> master 可反查：四条 DOI 均已写入 `docs/PAPER_REFERENCES.md:87-93`，并在同文件 `:127-130` 的引用覆盖表登记「正文位置 + Table S4 位置」。未解析到的字段一律未编造（本轮四条全部解析成功，故无 `[TO FILL]`）。

## 10. 自检（命令原文与输出）

命令（工作目录 `R:\songji\programfile`，`PYTHONUTF8=1`）：

```powershell
python docs\handoff\manuscript-v1\assets\servant_round2_selfcheck.py
```

输出原文（末行 `RESULT: ALL PASS`，进程退出码 0）：

```text
== A. D1: SEED_PLAN_ANALYSIS.md grid vs seed_plan_sweep.json ==
PASS  data rows == 16   got 16
PASS  (k,M,B) keys == json keys   sym-diff=[]
PASS  16 rows x 9 columns match json value by value
PASS  all 16 records candidates == hits
PASS  all 16 records keep the four guarantee flags

== B. D1: prose numbers vs json ==
PASS  hit-growth prose line found exactly once   n=1
PASS  prose carries '(0,0) = 24'
PASS  prose carries '(3,1) = 67 (k=8) and 66 (k=10)'
PASS  stale 'same value' claim is gone
PASS  json k=8 (3,1) hits == 67   67
PASS  json k=10 (3,1) hits == 66   66
PASS  json (0,0) hits == 24 for both k

== C. D2: [path:...] anchor existence scan ==
   OK  MODELS.md                              -> docs\MODELS.md   (PAPER_RESULTS_DRAFT.md, PAPER_TABLES_SUPP.md)
   OK  NATIVE_INDEXED_BENCHMARK.md            -> docs\NATIVE_INDEXED_BENCHMARK.md   (PAPER_RESULTS_DRAFT.md)
   OK  OUTPUTS.md                             -> docs\OUTPUTS.md   (PAPER_RESULTS_DRAFT.md, PAPER_TABLES_SUPP.md)
   OK  PAPER_METHODS_DRAFT.md                 -> docs\PAPER_METHODS_DRAFT.md   (PAPER_RESULTS_DRAFT.md, PAPER_TABLES_SUPP.md)
   OK  REPORT.md                              -> example/engine_benchmark_small\REPORT.md   (PAPER_DRAFT.md, PAPER_RESULTS_DRAFT.md, PAPER_TABLES_SUPP.md)
   OK  Target_xbp_Target/extract_complex_queries.py -> Target_xbp_Target/extract_complex_queries.py   (PAPER_RESULTS_DRAFT.md)
   OK  Target_xbp_Y_zbp_Target/extract_motifs.py -> Target_xbp_Y_zbp_Target/extract_motifs.py   (PAPER_RESULTS_DRAFT.md)
   OK  docs/NATIVE_INDEXED_BENCHMARK.md       -> docs/NATIVE_INDEXED_BENCHMARK.md   (PAPER_FIGURE_CAPTIONS.md, SEED_PLAN_ANALYSIS.md)
   OK  docs/SEED_PLAN_ANALYSIS.md             -> docs/SEED_PLAN_ANALYSIS.md   (PAPER_FIGURE_CAPTIONS.md, PAPER_RESULTS_DRAFT.md)
   OK  docs/expressiveness_matrix.tsv         -> docs/expressiveness_matrix.tsv   (PAPER_FIGURE_CAPTIONS.md)
   OK  docs/seed_plan_sweep.json              -> docs/seed_plan_sweep.json   (PAPER_FIGURE_CAPTIONS.md, PAPER_TABLES_SUPP.md)
   OK  expressiveness_matrix.tsv              -> docs\expressiveness_matrix.tsv   (PAPER_DRAFT.md, PAPER_RESULTS_DRAFT.md)
   OK  extract_complex_queries.py             -> Target_xbp_Target\extract_complex_queries.py   (SEED_PLAN_ANALYSIS.md)
   OK  extract_motifs.py                      -> Target_xbp_Y_zbp_Target\extract_motifs.py   (SEED_PLAN_ANALYSIS.md)
   OK  seed_plan.cpp                          -> native/offtarget_engine/src\seed_plan.cpp   (SEED_PLAN_ANALYSIS.md)
   OK  seed_plan_sweep.json                   -> docs\seed_plan_sweep.json   (PAPER_RESULTS_DRAFT.md, SEED_PLAN_ANALYSIS.md)
   OK  tools/seed_plan_sweep.py               -> tools/seed_plan_sweep.py   (SEED_PLAN_ANALYSIS.md)
PASS  all distinct [path:...] anchors resolve (17 paths)   []
PASS  every numeric [path:line] anchor lies inside its file

== D. C2 forbidden words ==
   SEED_PLAN_ANALYSIS.md              hits=[]
   PAPER_DRAFT.md                     hits=[]
   PAPER_RESULTS_DRAFT.md             hits=[]
   PAPER_FIGURE_CAPTIONS.md           hits=[]
   PAPER_TABLES_SUPP.md               hits=[]
   PAPER_REFERENCES.md                hits=[]
   PAPER_BACK_MATTER.md               hits=[]
PASS  no forbidden word in any touched document

== E. encoding / structure ==
   SEED_PLAN_ANALYSIS.md              bytes= 13177 BOM=False CR=False U+FFFD=False lines=219
   PAPER_DRAFT.md                     bytes=  9773 BOM=False CR=False U+FFFD=False lines=129
   PAPER_RESULTS_DRAFT.md             bytes= 14836 BOM=False CR=False U+FFFD=False lines=229
   PAPER_FIGURE_CAPTIONS.md           bytes=  7705 BOM=False CR=False U+FFFD=False lines=141
   PAPER_TABLES_SUPP.md               bytes= 14665 BOM=False CR=False U+FFFD=False lines=149
   PAPER_REFERENCES.md                bytes= 14761 BOM=False CR=False U+FFFD=False lines=150
   PAPER_BACK_MATTER.md               bytes=  5302 BOM=False CR=False U+FFFD=False lines=60
PASS  no BOM, no CR, no U+FFFD in any touched document   []

== F. abstract and reference coverage ==
PASS  abstract word count inside 170-250   n=232
PASS  abstract carries no citation number
PASS  every reference [1]-[30] is cited in the draft body   missing=[]
PASS  reference list is exactly [1]-[30], one line each   n=30
PASS  every reference entry carries a DOI   dois=30
PASS  no stale tools/expressiveness_matrix.tsv anchor

RESULT: ALL PASS (0 failing checks)
```

补充说明（口径，供 master 复核探针本身）：

- A 段的 `s*` 列取 `py_plan_segments`（形如 `2x10bp@3`）的前导段数，而非 JSON 的 `seed_len`（该字段等于索引 `k`）；这是本探针第一版唯一的口径错误，更正后 16 行 × 9 列 0 处不符。
- F 段的参考文献行用 `^\[(\d+)\] `（强制括号后跟空格）匹配，避免把本文件第 8 行的说明句 `[27]-[30]` 计入条目数。
- C 段的 `[path:...]` 锚点只匹配「方括号 + 路径串 + 冒号」形式；`[task.md §2.8]`（无冒号）与 `index_builds[0]` 这类嵌套下标不参与存在性判定（后者的引用正则误匹配见 §11 第 6 条）。

## 11. 未做项及原因

1. 未按 `§8.1-5`「凡出现完备性/exhaustive 的位置都补限定」的字面范围去改 `docs/PAPER_METHODS_DRAFT.md` 之外的其它文件（该文件已冻结、本轮禁改）；实际落点严格限定为 task.md 点名的三处（Abstract、Introduction、Results 种子计划小节）。
2. 未给 `docs/PAPER_TABLES_SUPP.md` 的 Table S4 增加 `deepcpf1` 数据行：该表的行集合是 `docs/MODELS.md` 清单表的逐字快照，而 MODELS.md 清单本身无该行；加行会改变 S4 口径且需同步 MODELS.md（不在本轮范围）。改以 Notes 一句话把 [29] 与 DeepCpf1 挂上。
3. 未改 `docs/PAPER_BACK_MATTER.md:34` 的「来源」列（仍为 `docs/PAPER_METHODS_DRAFT.md` 2.4 / 2.5）：规格只要求改「内容」描述。见 §12 第 4 条与 §13 第 3 条。
4. 未跑 `python tools\seed_plan_sweep.py --determinism`（引擎确定性属 master 核验尺度，且本轮改动不含引擎与 fixture；round 1 的四个 sha256 与文件记载一致，本轮未触碰 `docs/seed_plan_sweep.json`）。
5. 未授权/取用 `scy-test/`；未改任何 `[TO FILL]` 的 URL / Zenodo DOI / accession / keywords / 工具名（task.md §8 明令）。
6. 未新增 C4 之外的任何文献：本轮新增严格限于 [27]-[30] 四条。

## 12. 附带发现（只记录，未修）

1. `shared/scoring/model_registry.py` 记录了 `crispr_m` 的上游 `url`（`https://raw.githubusercontent.com/lyotvincent/CRISPR-M/...`），这是仓库内唯一能锚定 CRISPR-M 出处的记录；`docs/MODELS.md` 全篇未记录任何模型原始论文的 DOI。
2. `docs/MODELS.md` 的清单表（第 5-12 行）不含 `seq_deepcpf1_weights.h5`，而该文件实际存在于 `models/`（428168 B，与 registry 的 `expected_bytes` 一致）；Table S4 因此天然缺 DeepCpf1 行。
3. Europe PMC 对 DOI `10.1186/s13059-018-1459-4` 返回的作者串有 16 项，其中 `Yan J` 重复；Crossref 同一 DOI 返回 15 人（Chuai G, Ma H, Yan J, Chen M, Hong N, Xue D, Zhou C, Zhu C, Chen K, Duan B, Gu F, Qu S, Huang D, Wei J, Liu Q），[28] 采用 15 人版本。
4. `docs/PAPER_BACK_MATTER.md:34` 的「来源」列写 `docs/PAPER_METHODS_DRAFT.md` 2.4 / 2.5，而该文件真正的 S1 正文位于 `docs/PAPER_METHODS_DRAFT.md:425`（标题 `## Supplementary note S1 (source correspondence)`）。
5. 仓库根存在 `_probe_ok_flows.js`、`_probe_page_state.js`、`_srv.err.txt`、`_srv.out.txt` 等文件，均非本轮产物（mtime 早于本轮开工），本轮未动、未删。
6. round 1 review 已记录的 `[0]` 误匹配仍在：`docs/PAPER_RESULTS_DRAFT.md` 的 `index_builds[0]` 会被 `\[(\d+)\]` 类引用正则当成引用 `[0]`（现位于该文件 83 行附近）。
7. `docs/SEED_PLAN_ANALYSIS.md` 的正文段落换行宽度与表格行不统一（既有风格），本轮只改 1 行数字，未做排版归一。

## 13. 待明确项（请 master 裁定）

1. `[27]-[30]` 的编号顺序：本轮按 task.md §8 D3 的 ①-④ 顺序（Azimuth / DeepCRISPR / DeepCpf1 / CRISPR-M）编号，这与正文首次引用顺序（打分小节里首先出现的是 DeepCRISPR）不一致。若要求「编号 = 正文首次出现顺序」，则应为 DeepCRISPR=[27]、Azimuth=[28]、DeepCpf1=[29]、CRISPR-M=[30]；需要改号请明示，我按新号同步 REFERENCES/RESULTS/TABLES 三处。
2. Table S4 是否补 `deepcpf1` 行（需连带决定是否更新 `docs/MODELS.md` 清单表）；若补行，表内 `size` / `registry status` 可取自 `shared/scoring/model_registry.py` 与 `models/` 实文件。
3. `docs/PAPER_BACK_MATTER.md:34` 的「来源」列是否补 `docs/PAPER_METHODS_DRAFT.md:425`（S1 实际位置）锚点。
4. 其余沿用 round 1 §6：`scy-test/` 授权、仓库 URL / Zenodo DOI / accession / keywords、工具名。

## 14. 状态

- 本轮完成：D1、D2、D3（含 RESULTS 与 Table S4 同步）、task.md §8.1-4 必修；可选 N1、N2、§8.1-5 亦已完成。
- 未自行裁定「通过」；核验归 master。
- `state.json` 已置 `ready_for_review`（`round: 2`）并更新 `updated`。
