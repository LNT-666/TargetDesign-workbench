import io, os, json

ROOT = r"R:\songji\programfile"

def w(path, text):
    full = os.path.join(ROOT, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with io.open(full, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    print("WROTE", path, len(text))

REVIEW_R2 = r"""

---

# 核验报告：methods-draft（round 2）

- verdict: **pass**（round 2 三条必修 + 两条可选全部落地并通过；无遗留必修项）
- updated: 2026-09-19 14:35
- 依据：`report.md` round 2 小节（11:06）+ master 独立复跑（`assets/master_verify_text.py`、`assets/master_verify_anchors.py`）
  + 与 `assets/round1_baseline_PAPER_METHODS_DRAFT.md` 的逐行 diff + 新增锚点的原文回读

## 1. 逐条核验

| 条目 | 结论 | master 证据 |
| --- | --- | --- |
| D1 [40] 行「陈述」列中文 -> 英文 | 通过 | diff：`segmented_variant_work = 窗口数 x variant_count(k, allowed)` -> `= k-mer window count x variant_count(k, allowed)`（:390）；复跑 `rows_with_cjk_outside_note=[]` |
| D2 [1] 行锚点行号 + 补 guide_design.py | 通过（行号偏离已裁定，见 §3） | diff：`docs/PAPER_OUTLINE.md:123` -> `:151`，并补 `shared/design/guide_design.py:54-67, 183-192`（:351）；两处锚点原文已回读，均支持该行陈述 |
| N3 「Note on source correspondence」移出正文 | 通过 | 该段在当前文件中**出现 1 次**（仅在文末 `## Supplementary note S1 (source correspondence)`），与基线块**逐字节相同**，且不再出现在 Anchor table 之前的正文中 |
| 可选 N1 PAM 措辞 | 通过 | `:123-124` `a 3-prime PAM check [58]` -> `PAM side `3prime`; PAM enforcement is opt-in through an explicit flag [58]`；[58] 行补 `native/offtarget_engine/src/main.cpp:256-257`，原文实测为 `--require-pam -> options.require_pam = true`，与 `search.hpp:32` 的 `require_pam = false` 默认值共同支持「默认关闭、显式开启」 |
| 可选 N2 引理作用域 | 通过 | `:220-222` 在假设中加「target k-mer windows 仅由 A/C/G/T 组成，含其它字符的窗口不入索引因而不被枚举 [21]」；[21] 锚点 `docs/NATIVE_INDEXED_ENGINE_DESIGN.md:378-379` 原文 = `Invalid k-mer windows are excluded. A valid k-mer contains only A, C, G, and T after uppercasing the FASTA sequence.`，支持该句 |

## 2. master 独立复跑（原文）

```text
$ python docs\handoff\methods-draft\assets\master_verify_text.py
bytes 30595 chars 29797
bom False cr 0 repl 0
sections 8
    2.1 Design specification
    2.2 Motif-anchored layouts and strand enumeration
    2.3 Index format
    2.4 Seed-plan synthesis
    2.5 Lemma 1 (completeness) and proof
    2.6 Deterministic parallelism
    2.7 Resource bounds
    2.8 Calibration-state propagation and pair ranking
forbidden first/never/unprecedented/novel/首创/首次/唯一  count=0
cjk_in_body 0
rows_with_cjk_outside_note []
placeholders TIME/RATIO/N: 3 2 2
absclaim 全 0

$ python docs\handoff\methods-draft\assets\master_verify_anchors.py
TABLE_ROWS=73  min=1  max=73
MISSING_ROWS_FOR_CITED=[]
ROWS_NEVER_CITED=[]
TABLE_NUMBER_GAPS=[]
PROBLEMS=[]
```

与 `report.md` round 2 小节贴出的输出逐行一致。

## 3. 修法实现与范围核验

- 基线：`assets/round1_baseline_PAPER_METHODS_DRAFT.md` 与 `backup/20260919_methods_draft_round1/PAPER_METHODS_DRAFT.md`
  **逐字节相同**（30072 B，sha1 前缀 `158d88f6afe2`），可作为 round 1 交付的权威快照。
- diff（基线 -> 现行）**只有 6 个 hunk**：`:123` PAM 措辞、`:212-220` 删除说明段、`:228-233` 引理假设扩写、
  `:351` [1] 行、`:390` [40] 行、`:408` [58] 行，加文末插入 S1。行数 430 -> 435（+5）。
  **无任何范围外改动**（未动 2.5 证明正文、公式、占位符、2.6-2.8，未动代码与 fixture）。
- 边界：11:00-11:15 窗口内本任务只写了 5 个文件 —— `docs/PAPER_METHODS_DRAFT.md`、
  `assets/round1_baseline_PAPER_METHODS_DRAFT.md`、`backup/20260919_methods_draft_round1/PAPER_METHODS_DRAFT.md`、
  `state.json`、`report.md`；`tools/`、`shared/`、`example/`、`native/` 零改动。
- **关于 [1] 行行号偏离（servant「待明确」1）**：`review.md` 写的 `:126` 是**master 自己的失效值** ——
  master 在 10:36:51 写完 round 1 核验后，又于 10:40:40 改写了 `docs/PAPER_OUTLINE.md`（增补 ALLEGRO 等），
  行号整体下移，现行 `:126` 已是 `### Title`，而 2.1 形式化原文落在 `:151`（master 已回读确认）。
  servant 按「锚点必须指向支持该陈述的行」写 `:151` 是**正确处理**，原因为 master 侧变更，不计 servant 缺陷。

## 4. 残留观察（不阻塞，转出）

1. `assets/master_anchors.txt` 是 master 脚本的转储，每次复跑都会覆盖上一轮 —— master 侧约定改为按轮次命名
   （如 `master_anchors_round2.txt`），避免历史证据被覆盖。
2. 跨文档一致性（转 `docs/handoff/manuscript-v1/task.md` §8 追加项）：
   `docs/PAPER_BACK_MATTER.md:34` 把 `Notes S1` 描述为「种子计划代价方程与完备性引理的详细数学表述」，
   而 `docs/PAPER_METHODS_DRAFT.md` 当前的 S1 实际内容是 source correspondence 说明；两处描述需对齐。
3. 可选（转 `manuscript-v1`）：引理 1 的假设现在显式限定「target 窗口仅 A/C/G/T」，
   论文中凡出现「保证完备」的表述处，建议补半句同口径的限定（含 N 等非法字符的窗口不入索引）。

## 5. 结论

round 2 **通过**（三条必修 + 两条可选均落地，独立复跑与基线 diff 均一致，无越界改动）。
`state.json` 置 `done`。该文件自本条核验起冻结；后续改动需新开任务。
"""

STATE = json.loads(io.open(os.path.join(ROOT, "docs/handoff/methods-draft/state.json"), encoding="utf-8").read())
STATE.update({
    "status": "done",
    "round": 2,
    "updated": "2026-09-19 14:35",
    "verdict": "pass",
    "verdict_by": "master",
    "next_round": None,
    "open_question": None,
    "round2_verdict": "pass",
    "round2_verified": [
        "D1 [40] 行陈述列已改英文（:390）",
        "D2 [1] 行锚点 :151 + guide_design.py:54-67, 183-192（:351），master 回读两处锚点原文确认支持陈述",
        "N3 说明段逐字节移入文末 Supplementary note S1，正文本体已无残留",
        "N1 PAM 措辞 opt-in + [58] 行补 main.cpp:256-257",
        "N2 引理作用域补 ACGT 窗口限定（[21] 锚点 NATIVE_INDEXED_ENGINE_DESIGN.md:378-379 已回读）",
        "master_verify_text.py / master_verify_anchors.py 复跑与 report 逐行一致（PROBLEMS=[]）",
        "基线快照两份逐字节相同（30072 B）；diff 仅 6 个 hunk，无范围外改动",
    ],
    "followups": [
        "master 侧：master_anchors.txt 按轮次命名，避免覆盖历史转储",
        "manuscript-v1：PAPER_BACK_MATTER.md 的 Notes S1 描述与 PAPER_METHODS_DRAFT.md 的 S1 实际内容对齐",
        "manuscript-v1（可选）：完备性表述处补 ACGT 窗口限定半句",
    ],
    "followup_owner": "manuscript-v1",
    "frozen": True,
})
w("docs/handoff/methods-draft/state.json", json.dumps(STATE, ensure_ascii=False, indent=2) + "\n")

mk = os.path.join(ROOT, "docs/handoff/methods-draft/review.md")
cur = io.open(mk, encoding="utf-8").read()
if "核验报告：methods-draft（round 2）" in cur:
    print("SKIP methods-draft/review.md (round 2 already present)")
else:
    w("docs/handoff/methods-draft/review.md", cur.rstrip("\n") + "\n" + REVIEW_R2)

APPEND = r"""

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
"""

tk = os.path.join(ROOT, "docs/handoff/manuscript-v1/task.md")
cur = io.open(tk, encoding="utf-8").read()
if "### 8.1 master 追加" in cur:
    print("SKIP manuscript-v1/task.md (8.1 already present)")
else:
    w("docs/handoff/manuscript-v1/task.md", cur.rstrip("\n") + "\n" + APPEND)