import io, os, json

ROOT = r"R:\songji\programfile"

def w(path, text):
    full = os.path.join(ROOT, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with io.open(full, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    print("WROTE", path, len(text))

R2 = r"""

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

1. `scy-test/` 是否授权为证据来源 —— **待用户拍板**；未授权前 Results 案例小节与 Figure S1 保持 `[TO FILL]`。
2. 仓库 URL / Zenodo 版本 DOI / accession / keywords —— **待用户提供**。
3. Notes S1（成文稿）与 Notes S2（`.ggi` v1 规格）—— 尚未成文，由 master 另开条目。
4. 主文图 1-6、Figure S1、图形摘要的美术稿 —— 未绘制（本链路只出清单、图注与表体）。
5. 三份稿件文件（`PAPER_DRAFT.md` / `PAPER_METHODS_DRAFT.md` / `PAPER_RESULTS_DRAFT.md`）尚未合成单一投稿稿，
   也未按 NAR 版式组装 figure/table/back matter —— 建议作为后续任务 `manuscript-v2`（合稿与投稿要件收尾）。

## 5. 结论

round 2 **通过**：D1/D2/D3 三项必修与 §8.1-4 必修项全部落地，N1/N2 与 §8.1-5 可选项亦已落地；
改动范围最小、可逐条追溯、DOI 经独立通道反查无误、无越界改动。
`state.json` 置 `done`。7 个受改文件自本条核验起冻结；后续改动需新开任务。
"""

STATE = json.loads(io.open(os.path.join(ROOT, "docs/handoff/manuscript-v1/state.json"), encoding="utf-8").read())
STATE.update({
    "status": "done",
    "round": 2,
    "updated": "2026-09-19 15:00",
    "verdict": "pass",
    "verdict_by": "master",
    "round2_verdict": "pass",
    "round2_verified": [
        "D1 SEED_PLAN_ANALYSIS.md:128 -> 67（k=8）与 66（k=10），与 JSON/自身表格一致",
        "D2 PAPER_FIGURE_CAPTIONS.md 三处路径改 docs/，无残留",
        "D3 [27]-[30] 四条 DOI 经 master 用 Crossref 独立反查，标题/期刊/年卷期页逐字段一致",
        "D3 正文打分小节与 Table S4 的引用已补（DeepCpf1 以 Notes 句形式挂 [29]）",
        "§8.1-4 PAPER_BACK_MATTER.md:34 Notes S1 描述已与 Methods S1 实际内容对齐",
        "可选 N1（ALLEGRO 截断引文）、N2（复杂度句补排序项）、§8.1-5（A/C/G/T 限定三处落点）均落地",
        "diff 与 report 自报 hunk 数一致；无范围外改动；PAPER_METHODS_DRAFT.md 冻结未被触碰",
        "master 复跑 servant 自检探针：ALL PASS (0 failing checks)",
    ],
    "user_decisions_pending": [
        "scy-test/ 是否授权为证据来源（决定 Results 案例小节与 Figure S1 能否填数）",
        "仓库 URL / Zenodo 版本 DOI / accession / keywords",
    ],
    "followups": [
        "Notes S1 成文稿与 Notes S2（.ggi v1 规格）尚未撰写",
        "主文图 1-6、Figure S1、图形摘要未绘制",
        "建议后续任务 manuscript-v2：PAPER_DRAFT + PAPER_METHODS_DRAFT + PAPER_RESULTS_DRAFT 合稿，并按 NAR 版式组装 figure/table/back matter",
    ],
    "followup_owner": "master",
    "frozen": True,
})
w("docs/handoff/manuscript-v1/state.json", json.dumps(STATE, ensure_ascii=False, indent=2) + "\n")

rv = os.path.join(ROOT, "docs/handoff/manuscript-v1/review.md")
cur = io.open(rv, encoding="utf-8").read()
if "核验报告：manuscript-v1（round 2）" in cur:
    print("SKIP review.md (round 2 already present)")
else:
    w("docs/handoff/manuscript-v1/review.md", cur.rstrip("\n") + "\n" + R2)