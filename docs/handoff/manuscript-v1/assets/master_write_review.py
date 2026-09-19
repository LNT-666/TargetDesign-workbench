import io, os, json

ROOT = r"R:\songji\programfile"

def w(path, text):
    full = os.path.join(ROOT, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with io.open(full, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    print("WROTE", path, len(text))

REVIEW = r"""# 核验报告：manuscript-v1（round 1）

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
"""

STATE_ADD = {
    "status": "needs_rework",
    "round": 2,
    "updated": "2026-09-19 14:20",
    "verdict": "needs_rework",
    "verdict_by": "master",
    "reviewed_at": "2026-09-19 14:20",
    "round1_result": "全部 10 个交付件存在且与契约一致；发现 3 处必修（D1 数字自相矛盾 / D2 出处路径目录 / D3 模型原论文缺位）",
    "must_fix": [
        "D1 docs/SEED_PLAN_ANALYSIS.md:128 -> (3,1) 为 67（k=8）与 66（k=10）",
        "D2 docs/PAPER_FIGURE_CAPTIONS.md:50,58,62 -> tools/expressiveness_matrix.tsv 改 docs/",
        "D3 docs/PAPER_REFERENCES.md 补 4 篇模型原始论文 [27]-[30]（C4 定向放宽，master 授权）",
    ],
    "optional": ["N1 ALLEGRO 截断引文加省略号", "N2 复杂度句补排序项"],
    "master_verified": [
        "--determinism 重跑：4 线程数 hits=36，sha256 0549c426... 全等（与记载逐字符一致）",
        "SEED_PLAN_ANALYSIS.md §2 网格表 16 行与 seed_plan_sweep.json 逐值比对 0 处不符",
        "Table S1 与 expressiveness_matrix.tsv 行序一致、前 8 列 0 处不符",
        "seed_plan.cpp / extract_complex_queries.py / extract_motifs.py / iupac.py 全部源码锚点抽查命中",
        "4 个修改件与 backup/2026-09-19_manuscript-v1 的 diff 仅含规格要求改动",
        "[1]-[20] DOI 与大纲 §2.1 先例表 20/20 一致；正文引用 1..26 全覆盖",
    ],
    "user_decisions_pending": [
        "scy-test/ 是否授权为证据来源（影响 Results 案例小节与 Figure S1）",
        "仓库 URL / Zenodo 版本 DOI / accession / keywords",
    ],
}

TASK_APPENDIX = r"""

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
"""

w("docs/handoff/manuscript-v1/review.md", REVIEW)

st = json.loads(io.open(os.path.join(ROOT, "docs/handoff/manuscript-v1/state.json"), encoding="utf-8").read())
st.update(STATE_ADD)
w("docs/handoff/manuscript-v1/state.json", json.dumps(st, ensure_ascii=False, indent=2) + "\n")

tk = os.path.join(ROOT, "docs/handoff/manuscript-v1/task.md")
cur = io.open(tk, encoding="utf-8").read()
if "## 8. round 2 补充" in cur:
    print("SKIP task.md appendix (already present)")
else:
    w("docs/handoff/manuscript-v1/task.md", cur.rstrip("\n") + "\n" + TASK_APPENDIX)