import json, pathlib

repo = pathlib.Path(r"R:\songji\programfile")
d = repo / "docs" / "handoff" / "manuscript-v2"
d.mkdir(parents=True, exist_ok=True)
(d / "assets").mkdir(parents=True, exist_ok=True)

task = """# 任务：manuscript-v2 —— 合稿为单一投稿稿 + NAR 版式组装（含裁定 A 落地）

- 任务目录：`docs/handoff/manuscript-v2/`
- 上游：`docs/handoff/manuscript-v1/`（round 2 已 pass，10 个交付件冻结，**只读**）
- 用户裁定（2026-09-19，master 记录于 `docs/handoff/manuscript-v1/review.md` 第 4 节）：**方案 A** —— 删除 Results 案例小节与 Supplementary Figure S1；`scy-test/` 不得作为任何证据或数据来源
- 本文件只有 master 能写；servant 只改第 4 节点名的文件，其余一律只读
- 开工第一件事：按第 4 节做改前快照 `backup/2026-09-19_manuscript-v2/`，再动笔

## 0. 目标与边界

目标只有三件：

1. 落地裁定 A：删除案例小节、Figure S1 及其全部登记与调用点；
2. 把三份分节稿（`docs/PAPER_DRAFT.md` + `docs/PAPER_METHODS_DRAFT.md` + `docs/PAPER_RESULTS_DRAFT.md`）与前/后置件合成**一份可直接投稿的主文稿**与**一份 Supplementary**；
3. 剥离全部排版脚手架与溯源标记，产出 `[TO FILL]` 登记表。

不包含：绘图、补数据、写新科学内容、写 Notes S2、改代码、碰 `scy-test/`。

## 1. 规则 / 契约（唯一权威，servant 不必重新调研）

C1 章节顺序（主范本 ALLEGRO，NAR 2025, 53, gkaf783，见 `docs/PAPER_BACK_MATTER.md:3`-`:4`）：

`Title -> Authors and affiliations -> Abstract -> Graphical abstract -> Introduction -> Materials and Methods -> Results -> Discussion -> Acknowledgements（含 Author contributions:）-> Supplementary data -> Conflict of interest -> Funding -> Data availability -> References -> Figure legends`

C2 子标题：无编号的描述性短语；Discussion 为单块连续散文、无子标题（`docs/NAR_FORMAT_CHECKLIST.md:22`-`:23`）。

C3 主文表 = 0；Supplementary 表固定为 Table S1-S5，编号与顺序不得改（`docs/FIGURE_TABLE_PLAN.md:48`-`:58`）。Supplementary 图：**无**（裁定 A）。

C4 摘要：170-250 词、单段、无小标题、无引用编号；**唯一权威文本是 `docs/PAPER_DRAFT.md:28`**（master 实测 232 词）。

C5 裁定 A：删除 Results 的案例小节与 Supplementary Figure S1；不得新增案例数据、不得用其它数据补一张替代图；`scy-test` 字样不得出现在任何成品文件里。

C6 禁止编造：`[TO FILL]` 一律保留为占位符，不得填值，不得编造作者/单位/DOI/URL/accession。已由 master 定稿的两个名字：标题用前置件候选 A；工具名用 `CRISPR-Motif Workbench`。

C7 脚手架剥离规则（成品文件里一律不得出现）：

1. `[path:line]` / `[file:line]` 形态的溯源标记 —— 删掉整个方括号 token，且删后句子必须仍通顺；
2. `<!-- ... -->` 注释（`docs/PAPER_REFERENCES.md` 共 30 处）；
3. 图注草稿里的 `- Content:` / `- Source:` / `- Scope:` 行 —— 只保留加粗的图注段；
4. 稿件开头的 draft / annotation 说明块：`docs/PAPER_DRAFT.md:3`-`:15`、`docs/PAPER_RESULTS_DRAFT.md:3`-`:18`、`docs/PAPER_METHODS_DRAFT.md:3`-`:9`、`docs/PAPER_TABLES_SUPP.md:3`-`:10`；
5. `docs/PAPER_REFERENCES.md:117`-`:150`（引用位置表 / coverage checks / open item）。

C8 成品文件语言：英文；**除占位符外 0 个 CJK 字符**；占位符统一写成 `[TO FILL: <short English description>]`（即占位符内部也不得用中文）。

C9 禁用措辞不得出现，也不得因改写而引入：`first` / `never` / `unprecedented` / `novel` / 首创 / 首次 / 从未。

C10 编码：UTF-8 无 BOM、LF 换行、无 U+FFFD。

## 2. 现状证据（master 2026-09-19 实测，可直接引用，不必重跑）

### 2.1 相关文件与行数（`docs/` 下）

| 文件 | 行数 | 本任务角色 |
| --- | --- | --- |
| `PAPER_DRAFT.md` | 129 | 只读（Title / Abstract / Introduction / Discussion 源） |
| `PAPER_METHODS_DRAFT.md` | 434 | 只读（Methods 源 + Note S1 源） |
| `PAPER_RESULTS_DRAFT.md` | 229 | **改**（删案例小节） |
| `PAPER_TABLES_SUPP.md` | 149 | 只读（Table S1-S5 表体源） |
| `PAPER_REFERENCES.md` | 150 | 只读（30 条条目 + 脚手架） |
| `PAPER_FIGURE_CAPTIONS.md` | 141 | **改**（删 Figure S1 块） |
| `PAPER_BACK_MATTER.md` | 60 | **改**（删 Figure S1 行） |
| `PAPER_FRONT_MATTER.md` | 65 | **改**（同步陈旧摘要） |
| `FIGURE_TABLE_PLAN.md` | 78 | **改**（S1 取消登记） |
| `NAR_FORMAT_CHECKLIST.md` | 52 | **改**（只改 4 处） |

### 2.2 分节行号锚点

- `PAPER_RESULTS_DRAFT.md`：保留的 7 个小节标题在 `:20`（Motif-anchored design space and expressiveness）、`:52`（Complete enumeration and pruning for paired layouts）、`:87`（Seed-plan cost curve and completeness）、`:122`（Cross-engine benchmark and recall honesty）、`:150`（Determinism and resource bounds）、`:172`（Scoring, calibration status and pair ranking）、`:209`（Implementation, interface and test suite）；**待删除**的案例小节标题在 `:198`，其正文为 `:200`-`:207`。
- `PAPER_METHODS_DRAFT.md`：`:11` 是父标题 `## 2. Materials and Methods`；子节 `2.1`:`13`、`2.2`:`49`、`2.3`:`86`、`2.4`:`116`、`2.5`:`213`（含 Lemma 1）、`2.6`:`278`、`2.7`:`292`、`2.8`:`313`；`:342`-`:424` 是 Anchor table（脚手架，不进成品）；`:425`-`:434` 是 Supplementary note S1。
- `PAPER_DRAFT.md`：`:21` Title、`:26` Abstract（正文在 `:28`）、`:30` Introduction（至 `:93`）、`:94` Discussion（至 `:129`）。
- `PAPER_BACK_MATTER.md`：`:11` Acknowledgements、`:20` Supplementary data、`:38` Conflict of interest、`:44` Funding、`:49` Data availability；`:58` 起的中文「边界」块不进成品。
- `PAPER_FRONT_MATTER.md`：`:12`-`:16` 标题候选（A 为推荐，master 已定稿）、`:22`-`:34` 作者与单位块模板、`:50`-`:52` Abstract、`:54`-`:58` 关键词。

### 2.3 Figure S1 的全部落点（删净这些即无悬空引用）

`docs/PAPER_RESULTS_DRAFT.md:198`-`:207`；`docs/PAPER_FIGURE_CAPTIONS.md:3`-`:6`（文件头计数句）与 `:128`-`:141`；`docs/PAPER_BACK_MATTER.md:36`；`docs/FIGURE_TABLE_PLAN.md:18`、`:20`、`:32`、`:44`、`:77`。

被删段落**不含任何数字引用**（只有一处 `[task.md §1 C3]` 说明性引用），故 `[1]`-`[30]` 的正文覆盖不受影响。

主文图调用点现状（升序、无需改动）：Introduction 引 Figure 1（`PAPER_DRAFT.md:79`）与 Figure 2（`:84`）；Results 第 1 小节引 Figure 2、Figure 3（`PAPER_RESULTS_DRAFT.md:23`-`:24`）；第 2 小节引 Figure 4（`:80`）；第 3 小节引 Figure 5（`:91`）；第 4 小节引 Figure 6（`:148`）。

### 2.4 摘要分叉（必须先修，否则合稿会带走旧文本）

`docs/PAPER_DRAFT.md:28` 实测 232 词；`docs/PAPER_FRONT_MATTER.md:52` 实测 221 词。逐词比对只有一处差异：前端件仍是旧写法 `exhaustive,`，分节稿是 round 2 修订后的 `exhaustive for target windows composed only of A, C, G and T,`。**以 `PAPER_DRAFT.md:28` 为准**。

### 2.5 脚手架计数（master 实测，供自检对账）

`PAPER_REFERENCES.md`：30 条文献、30 处 `<!-- -->`；CJK 字符数：`PAPER_METHODS_DRAFT.md` 386、`PAPER_TABLES_SUPP.md` 74、`PAPER_RESULTS_DRAFT.md` 9（含待删行）、`PAPER_DRAFT.md` 0、`PAPER_REFERENCES.md` 0。

### 2.6 裁定 A 的依据

`scy-test/` 实测 10,389 个文件 / 67 GB：122 个 `*_scores.tsv`、123 个 `*_offtargets.tsv`、112 个 `*_blast_results.tsv`、9,739 个 `.fa` 中间件；唯一属输入数据的只有 `scy-test/blastdb/GCF_000001405.40_GRCh38.p14_genomic.blastdb`（787 MB）。位点 FASTA 头只有 `>PPP1R12C-intron1` 一类名字，无坐标、无基因组版本，仓库任何文档都没有坐标记录，也没有生成命令与版本记录。故它不构成可复核的证据来源，案例小节整体删除。

### 2.7 已冻结、本任务不得改的实测数字

`docs/SEED_PLAN_ANALYSIS.md:128` 的 `(3,1)` 命中数 = 67（k=8）与 66（k=10）；`[27]`-`[30]` 四条 DOI 已由 master 用 Crossref 反查一致。合稿时逐字搬运，不得重算、不得改数。

## 3. 必做改动

P0-1 删除 `docs/PAPER_RESULTS_DRAFT.md:198`-`:207` 的案例小节（标题行 + 正文），Results 由 8 小节变 7 小节；不得留空标题、不得留 `[TO FILL: 案例数据未在仓库中]`。

P0-2 删除 `docs/PAPER_FIGURE_CAPTIONS.md:128`-`:141` 的 Figure S1 图注块；把文件头 `:3`-`:6` 的「the six main-text figures and the one Supplementary figure」改为只讲 6 张主文图、无 Supplementary 图。

P0-3 删除 `docs/PAPER_BACK_MATTER.md:36` 的 Figure S1 清单行。

P0-4 `docs/FIGURE_TABLE_PLAN.md`：`:`18`、`:`20`、`:`32`、`:`44`、`:`77` 改为「已按 master 裁定 A 取消（用户 2026-09-19 拍板）」；主文图仍为 6 张、编号不变；`Figure S1` 不得再作为在编条目出现。

P0-5 `docs/PAPER_FRONT_MATTER.md`：`:52` 改成与 `docs/PAPER_DRAFT.md:28` 逐字一致；`:43` 的「221」改为「232」，并注明「master 裁定以 `docs/PAPER_DRAFT.md:28` 为准（2026-09-19）」。

P0-6 新建 `docs/submission/SUBMISSION_MAIN_v1.md`，按 C1 顺序组装：

- Title：`CRISPR-Motif Workbench: a constraint-driven guide design platform with a native indexed off-target engine`（`PAPER_FRONT_MATTER.md:14` 候选 A）
- Authors and affiliations：照 `PAPER_FRONT_MATTER.md:22`-`:34` 的块，占位符按 C8 改写为英文
- Abstract：`PAPER_DRAFT.md:28`（逐字）
- Graphical abstract：一段说明 + `[TO FILL: final art file and figure size]`，并指向 `docs/assets/graphical_abstract_draft.svg`
- Introduction：`PAPER_DRAFT.md:30`-`:93`
- Materials and Methods：`PAPER_METHODS_DRAFT.md:11`-`:341`，标题去编号（`### 2.1 Design specification` -> `### Design specification`；父标题去掉 `2.`）
- Results：`PAPER_RESULTS_DRAFT.md` 保留下来的 7 小节
- Discussion：`PAPER_DRAFT.md:94`-`:129`
- Back matter：`PAPER_BACK_MATTER.md` 的英文正文段，按 C1 顺序
- References：`PAPER_REFERENCES.md:1`-`:116` 的 30 条条目（去掉 `<!-- -->`）
- Figure legends：`PAPER_FIGURE_CAPTIONS.md` 的 6 条加粗图注段，节标题 `## Figure legends`

全文按 C7 剥离脚手架；不得改动任何数字。

P0-7 新建 `docs/submission/SUPPLEMENTARY_v1.md`：Table S1-S5 表体（来自 `docs/PAPER_TABLES_SUPP.md`，去溯源标记与中文说明）+ `Note S1`（来自 `docs/PAPER_METHODS_DRAFT.md:425`-`:434`，标题写 `Note S1. Source correspondence of the seed-plan cost model`）。

P0-8 新建 `docs/submission/FILL_REGISTER.md`：逐条登记两份成品里的每个占位符（文件 + 行号 + 原文 + 归属：用户提供 / master 裁定 / 期刊确认 / 待撰写），并与成品内的占位符数量精确对账。

P0-9 `docs/NAR_FORMAT_CHECKLIST.md` 只改这 4 处：`:19`（主文图固定 6 张、Supplementary 图 = 无）、`:22`（投稿稿标题已去编号）、`:29`（Note S1 已成稿并入 Supplementary）、第 2 节表格新增一行「案例小节与 Figure S1：按 master 裁定 A 删除（用户 2026-09-19）」。其它行不得改。

## 4. 写集与改前快照

写集（只有这些）：

- 新建：`docs/submission/SUBMISSION_MAIN_v1.md`、`docs/submission/SUPPLEMENTARY_v1.md`、`docs/submission/FILL_REGISTER.md`、`docs/handoff/manuscript-v2/assets/servant_selfcheck.py`
- 修改：`docs/PAPER_RESULTS_DRAFT.md`、`docs/PAPER_FIGURE_CAPTIONS.md`、`docs/PAPER_BACK_MATTER.md`、`docs/FIGURE_TABLE_PLAN.md`、`docs/PAPER_FRONT_MATTER.md`、`docs/NAR_FORMAT_CHECKLIST.md`
- 只读（合稿时逐字搬运，不得改动）：`docs/PAPER_DRAFT.md`、`docs/PAPER_METHODS_DRAFT.md`、`docs/PAPER_TABLES_SUPP.md`、`docs/PAPER_REFERENCES.md`、`docs/SEED_PLAN_ANALYSIS.md`、`docs/EXPRESSIVENESS_MATRIX.md`、`docs/expressiveness_matrix.tsv`、`docs/seed_plan_sweep.json`、`example/engine_benchmark_small/REPORT.md`、`docs/NATIVE_INDEXED_BENCHMARK.md`

改前快照：把上面 6 个「修改」文件复制到 `backup/2026-09-19_manuscript-v2/`（同名副本，与改动前逐字节一致），并在 `report.md` 报告快照文件数。

## 5. 不要做的事

- 不绘图、不生成图片/PDF/SVG、不改 `docs/assets/graphical_abstract_draft.svg`
- 不填任何 `[TO FILL]`（作者、单位、基金、URL、DOI、accession 一律留空）
- 不写 Note S2（`.ggi` v1 规格由 master 另开任务）
- 不改 `docs/PAPER_DRAFT.md`、`docs/PAPER_METHODS_DRAFT.md`、`docs/PAPER_TABLES_SUPP.md`、`docs/PAPER_REFERENCES.md` 正文（P0-6/P0-7 只做搬运与剥离）
- 不改 `docs/PAPER_OUTLINE.md`、`docs/PAPER_OUTLINE_WITH_EXPERIMENTS.md`、`docs/ALLEGRO_REFERENCE_ANALYSIS.md`
- 不改任何代码：`tools/`、`native/`、`shared/`、`webapp/`、`Target_xbp_*`；不读不写 `scy-test/`
- 不重排 Table S1-S5、不改数字、不改 DOI、不重算基准
- 不改 `docs/handoff/` 下其它任务的任何文件
- 不做全仓扫描、不跑基准、不做长时间命令

## 6. 决策项（未确认则按推荐执行）

D1 标题与工具名已由 master 定稿：候选 A + `CRISPR-Motif Workbench`；按此执行，不要再选。
D2 Methods 去编号只在成品里做；`PAPER_METHODS_DRAFT.md` 保留 `2.x` 编号（推荐：其它文档按 `:2.4` 一类引用）。
D3 图注放在 References 之后，节标题 `## Figure legends`（推荐）。
D4 参考文献条目保留原 `[n]` 前缀（推荐：便于与正文引用对账；投稿系统会重排）。
D5 `FILL_REGISTER.md` 用中文书写（推荐）；两份成品文件用英文（C8）。
D6 关键词按 `PAPER_FRONT_MATTER.md:57` 的建议串保留一行，并附 `[TO FILL: confirm whether the journal requires keywords]`（推荐）。

## 7. 轻量自检（servant 的检验上限）

自写 `docs/handoff/manuscript-v2/assets/servant_selfcheck.py`，用一条命令运行：

```powershell
$env:PYTHONUTF8=1; python docs\\handoff\\manuscript-v2\\assets\\servant_selfcheck.py
```

覆盖以下 8 组即可：

1. P0-1 到 P0-5 逐条：目标字符串已消失、新字符串已出现、行数变化与预期一致；
2. 两份成品文件：CJK 计数 = 0、无 `<!--`、无 `[path:line]` 形态标记（正则 `\\[[A-Za-z_][^\\]\\s]*\\.(md|py|cpp|hpp|json|tsv|txt):`）、无 `Figure S1`、无 `scy-test`、无 `case site`、无 `AAVS1`、无 `TRAC`、无 `PDCD1`；
3. 编码：两份成品 + 6 个改后文件均为 BOM=False、CR=0、U+FFFD=0；
4. 摘要：`SUBMISSION_MAIN_v1.md` 里 Abstract 词数落在 170-250，且与 `PAPER_DRAFT.md:28` 逐字一致；
5. 参考文献：条目数 = 30，正文引用编号落在 `[1]`-`[30]` 内且 `1`-`30` 全覆盖；
6. 占位符对账：两份成品内 `[TO FILL` 出现次数 = `FILL_REGISTER.md` 的数据行数；
7. 禁用词：C9 的七项在成品与 6 个改后文件中 0 命中；
8. Table S1 表体数据行 = 16。

不做全仓扫描、不跑基准、不改代码。

## 8. 交付要求

- `report.md`：逐条对应 P0-1 到 P0-9；给出改动文件 + 行号、新建文件的行数与字节数、命令原文与输出、未做项与原因、附带发现、待明确项；另附「占位符对账」与「快照文件数」两个小节。
- `state.json`：置 `ready_for_review`，`round: 1`。
- 完成后给用户一句可转发的话：`本会话是 master，核验 R:\\songji\\programfile\\docs\\handoff\\manuscript-v2\\。`
"""
(d / "task.md").write_text(task, encoding="utf-8", newline="\n")
print("task.md bytes =", (d / "task.md").stat().st_size)

state = {
    "task": "manuscript-v2",
    "title": "合稿为单一投稿稿 + NAR 版式组装（含裁定 A 落地：删除案例小节与 Figure S1）",
    "status": "assigned",
    "status_values": ["assigned", "implementing", "ready_for_review", "verifying", "needs_rework", "done", "master_takeover"],
    "round": 1,
    "master": "会话 M（master）",
    "servant": "会话 S（servant）",
    "repo": "R:\\songji\\programfile",
    "created": "2026-09-19 15:05",
    "updated": "2026-09-19 15:05",
    "upstream": "docs/handoff/manuscript-v1/ (round 2 pass, 10 deliverables frozen)",
    "user_decision": "A — 删除 Results 案例小节与 Supplementary Figure S1；scy-test/ 不作为任何证据来源（用户 2026-09-19 拍板）",
    "deliverables_new": [
        "docs/submission/SUBMISSION_MAIN_v1.md",
        "docs/submission/SUPPLEMENTARY_v1.md",
        "docs/submission/FILL_REGISTER.md"
    ],
    "deliverables_edited": [
        "docs/PAPER_RESULTS_DRAFT.md (P0-1 删案例小节 :198-:207)",
        "docs/PAPER_FIGURE_CAPTIONS.md (P0-2 删 Figure S1 :128-:141，改文件头计数句)",
        "docs/PAPER_BACK_MATTER.md (P0-3 删 :36 Figure S1 行)",
        "docs/FIGURE_TABLE_PLAN.md (P0-4 五处 S1 登记改为已取消)",
        "docs/PAPER_FRONT_MATTER.md (P0-5 同步陈旧摘要 :52 与词数 :43)",
        "docs/NAR_FORMAT_CHECKLIST.md (P0-9 只改 :19 :22 :29 与第 2 节新增一行)"
    ],
    "snapshot_required": "backup/2026-09-19_manuscript-v2/ (6 pre-edit copies)",
    "open_for_user": [
        "仓库 URL / Zenodo 版本 DOI / accession",
        "作者名单、单位、通讯作者、ORCID、基金",
        "关键词是否必需（期刊确认）",
        "图形摘要最终尺寸与格式"
    ]
}
(d / "state.json").write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
print("state.json bytes =", (d / "state.json").stat().st_size)