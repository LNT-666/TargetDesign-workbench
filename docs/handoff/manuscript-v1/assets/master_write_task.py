import io, os, json

ROOT = r"R:\songji\programfile"

def w(path, text):
    full = os.path.join(ROOT, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with io.open(full, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    print("WROTE", path, len(text))

TASK = r"""# 任务：论文 v1 全稿（无实验版）+ 遗留证据文档收尾

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
"""

STATE = {
    "task": "manuscript-v1",
    "title": "论文 v1 全稿（无实验版）+ 遗留证据文档收尾",
    "status": "assigned",
    "status_values": ["assigned", "implementing", "ready_for_review", "verifying",
                      "needs_rework", "done", "master_takeover"],
    "round": 1,
    "master": "会话 M（master）",
    "servant": "会话 S（servant）",
    "repo": r"R:\songji\programfile",
    "server_repo": "/home/apool/songji/programfile",
    "local_python": "Python 3.14.7",
    "upstream_doc": "docs/PAPER_OUTLINE.md 第三、二节；docs/FIGURE_TABLE_PLAN.md；docs/handoff/nar-format-pack/task.md (r2)",
    "created": "2026-09-19 10:55",
    "updated": "2026-09-19 10:55",
    "inputs_from_done_tasks": [
        "expr-matrix: docs/EXPRESSIVENESS_MATRIX.md, docs/expressiveness_matrix.tsv, tools/expressiveness_probe.py",
        "nar-format-pack: docs/PAPER_FRONT_MATTER.md, docs/PAPER_BACK_MATTER.md, docs/FIGURE_TABLE_PLAN.md, docs/NAR_FORMAT_CHECKLIST.md",
        "engine-bench (master_takeover): docs/seed_plan_sweep.json, tools/seed_plan_sweep.py",
    ],
    "absorbs_engine_bench_deliverable": "docs/SEED_PLAN_ANALYSIS.md (P0-1)",
}

EB_REVIEW = r"""# 核验 / 处置报告：engine-bench（master 接管）

- round: 1
- verdict: master_takeover（servant 未交付完整件）
- updated: 2026-09-19 10:55
- 依据：文件 mtime + master 独立复跑（`python tools\seed_plan_sweep.py --plan-table`）+ JSON 结构核验

## 1. 事实（以文件为准）

| 时间 | 事件 |
| --- | --- |
| 2026-09-19 10:11 | `state.json` 置 `implementing` |
| 2026-09-19 10:12 | `tools/seed_plan_sweep.py` 写出（24308 B） |
| 2026-09-19 10:17 | `docs/seed_plan_sweep.json` 写出（10751 B） |
| 之后 | servant 停止；**未**写 `docs/SEED_PLAN_ANALYSIS.md`，**未**写 `report.md` |

`report.md` 仍为 2026-09-15 的起始模板（500 B），`state.json` 停在 `implementing`。

## 2. master 对已交付部分的独立核验

| 项 | 结论 | 证据 |
| --- | --- | --- |
| P0-1 网格完整性 | 通过 | JSON `records` = 16 条，覆盖 M{0,1,2,3} x B{0,1} x k{8,10}；`repeats=3`；逐条 `repeats_consistent=true` |
| P0-1 W(s) 独立复现 | 通过 | master 复跑 `--plan-table`：k=10 的 m=0/1/2/3 -> 1/31/436/3676；W：M3/B1 -> 7352，与 JSON 的 `py_plan_variants` 逐值一致 |
| P0-2 确定性证据 | **未交付** | JSON 内无 determinism 段；`--determinism` 子命令存在（`seed_plan_sweep.py:462`）但无运行输出可核 |
| P1-1 分析文档 | **未交付** | `docs/SEED_PLAN_ANALYSIS.md` 不存在 |
| P1-2 差异小节 | **未交付** | 随 P1-1 缺失 |

结论：已交付的数据产物**可信、可复用**（master 已逐项核验），但任务的两项交付缺失。

## 3. 处置

- 本任务状态置 `master_takeover`，不再等待 servant；本会话（master）不替 servant 补写。
- 剩余交付项（`docs/SEED_PLAN_ANALYSIS.md` + `--determinism` 实跑证据）**并入新任务**
  `docs/handoff/manuscript-v1/task.md` 的 P0-1。
- `tools/seed_plan_sweep.py` 与 `docs/seed_plan_sweep.json` 自本报告起冻结：后续任务只读。

## 4. 附带发现（转出，不在本任务修）

1. `native/offtarget_engine/src/seed_plan.cpp:126` 的 `(void)seed_len;` 使 CLI `--seed-len` 完全无效，
   实际种子长度由索引 `k` 决定（JSON `seed_len_policy` 字段同此说明）。论文按实际行为描述；
   代码修复需单独开任务，不属论文链路。
2. `native/offtarget_engine/include/offtarget/search.hpp:32` 的 `require_pam = false` 表示 3-prime PAM 校验
   默认关闭、由 `main.cpp:256` 在 CLI 层开启。论文措辞须写成 enforcement 是 opt-in（见 methods-draft review N1）。
"""

EB_STATE = {
    "task": "engine-bench",
    "title": "种子计划代价曲线 + 完备性 + 确定性 + 组合复杂度",
    "status": "master_takeover",
    "status_values": ["assigned", "implementing", "ready_for_review", "verifying",
                      "needs_rework", "done", "master_takeover"],
    "round": 1,
    "master": "会话 M（master）",
    "servant": "会话 S（servant）",
    "repo": r"R:\songji\programfile",
    "server_repo": "/home/apool/songji/programfile",
    "upstream_doc": "docs/PAPER_OUTLINE.md 第五节第 2、3 项",
    "local_python": "Python 3.14.7",
    "created": "2026-09-19 09:57",
    "updated": "2026-09-19 10:55",
    "verdict": "master_takeover",
    "verdict_by": "master",
    "reason": "servant 在 10:17 生成 docs/seed_plan_sweep.json 后停止，未交付 docs/SEED_PLAN_ANALYSIS.md 与 report.md",
    "verified_artifacts": ["tools/seed_plan_sweep.py", "docs/seed_plan_sweep.json"],
    "artifacts_frozen": True,
    "open_items": ["docs/SEED_PLAN_ANALYSIS.md", "--determinism 实跑证据"],
    "followup_owner": "manuscript-v1",
}

MD_APPENDIX = r"""

## 8. round 2 补充（master，2026-09-19 10:55）

本轮**只做 `review.md`「下一步（最小修复清单）」的三条**，不扩大范围：

1. `docs/PAPER_METHODS_DRAFT.md:396` —— [40] 行「陈述」列的中文写法改英文（与其余行同语种）。
2. `docs/PAPER_METHODS_DRAFT.md:357` —— [1] 行锚点 `docs/PAPER_OUTLINE.md:123` 改为
   `docs/PAPER_OUTLINE.md:126`，并补 `shared/design/guide_design.py:54-67, 183-192`，同步该行说明列。
3. `docs/PAPER_METHODS_DRAFT.md:212-219` —— 「Note on source correspondence」整段移出正文，
   放到文末新开的 `## Supplementary note S1`，并把 [40] 行的说明列改为指向 S1。

可选（不阻塞）：N1 PAM 措辞（enforcement 是 opt-in，`native/offtarget_engine/include/offtarget/search.hpp:32`
的 `require_pam=false`，由 `main.cpp:256` 在 CLI 层开启）、N2 引理作用域加一句。

round 2 自检下限：重跑 `assets/master_verify_anchors.py` 与 `assets/master_verify_text.py`，要求
`PROBLEMS=[]`、`rows_with_cjk_outside_note=[]`、`cjk_in_body=0`，八个 `### 2.x` 顺序不变。

交付：改完把 `state.json` 置 `ready_for_review`（`round: 2`、更新 `updated`），在 `report.md` **追加** round 2 小节
（不覆盖 round 1 内容）。核验仍归 master。
"""

w("docs/handoff/manuscript-v1/task.md", TASK)
w("docs/handoff/manuscript-v1/state.json", json.dumps(STATE, ensure_ascii=False, indent=2) + "\n")
w("docs/handoff/engine-bench/review.md", EB_REVIEW)
w("docs/handoff/engine-bench/state.json", json.dumps(EB_STATE, ensure_ascii=False, indent=2) + "\n")

md_task = os.path.join(ROOT, "docs/handoff/methods-draft/task.md")
cur = io.open(md_task, encoding="utf-8").read()
if "## 8. round 2 补充" in cur:
    print("SKIP methods-draft/task.md (round 2 section already present)")
else:
    w("docs/handoff/methods-draft/task.md", cur.rstrip("\n") + "\n" + MD_APPENDIX)