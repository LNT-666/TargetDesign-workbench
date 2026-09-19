# 核验报告：methods-draft

- round: 1
- verdict: needs_rework
- updated: 2026-09-19 10:36
- 依据：`report.md`（round 1）+ 逐行源码复核 + 本地端到端复跑
- 核验方式：本次为纯文档交付，无既有代码改动，故不使用备份 diff；
  改为「锚点逐条回读源码」+「文本规则码点级复核」+「原生引擎端到端复跑」。

## 逐条核验

| 任务项 | 结论 | 证据 |
| --- | --- | --- |
| P0-1 初稿 8 小节 | 通过 | `docs/PAPER_METHODS_DRAFT.md` 29328 字符；`### 2.1`-`### 2.8` 共 8 个，顺序与 C2 完全一致 |
| P0-2 Algorithm 1 | 通过 | 伪码 1-28 行与 `native/offtarget_engine/src/seed_plan.cpp:127-205` 逐行对应：`kmin/smax/smin`（130-132）、`d<=0 continue`（149-153）、`allowed`（155）、`partition_lengths`（155/54-61）、`capped_add` 上限判定（157-163）、`(W,s)` 字典序（180-190）、两条回退原因串（134-143 / 192-197） |
| P0-3 Lemma 1 | 通过 | 三段式齐备（正文 223-268）；抽屉原理四步 (i)-(iv) 均成立，见下「引理数学复核」 |
| P1-1 形式化与四链向 | 通过 | `S=(L,P,l,o,s)`、`D(S)`（15-47）；四链向 66-68 与 `docs/design_patterns_en.md:24-29` 一致 |
| C1 语言（中文仅限说明列） | **不通过** | 锚点表第 [40] 行**陈述列**含中文「窗口数」；全表仅此一处越界（脚本按列扫描：`rows_with_cjk_outside_note=['40']`） |
| C2 小节与顺序 | 通过 | 同上，8/8 |
| C3 上标-锚点双向闭合 | 通过 | 表格 73 行，编号 1-73 无缺口；`MISSING_ROWS_FOR_CITED=[]`、`ROWS_NEVER_CITED=[]`、`TABLE_NUMBER_GAPS=[]` |
| C4 引理与源码一致 | 通过（服务方判断正确） | 7 条关键事实逐条回读源码核对无误；`segmented_variant_work` 窗口因子差异确为服务方指出的那样，按 C4「以源码为准」处理正确 |
| C5 禁词与数字 | 通过 | `first/never/unprecedented/novel/首创/首次/唯一` 计数均为 0；全文无实测性能数字，出现的数字全是源码常量（500000、8..12、50000000）且均有锚点 |
| C6 只新增一个文件 | 通过 | 交付清单只有 `docs/PAPER_METHODS_DRAFT.md`（另有 servant 对 `state.json` 的状态更新） |
| §7 交付物齐备 | 通过 | `state.json` 已置 `ready_for_review`、`report.md` 五段齐备 |

## master 独立验证

### 1. 锚点机械校验（脚本 `assets/master_verify_anchors.py`，输出 `assets/master_anchors.txt`）

原文输出：

```text
TABLE_ROWS=73  min=1  max=73
MISSING_ROWS_FOR_CITED=[]
ROWS_NEVER_CITED=[]
TABLE_NUMBER_GAPS=[]
PROBLEMS=[]
```

`PROBLEMS=[]` 的含义：73 行里所有 `file:line` 引用（含同一反引号内用逗号分隔的多段行号，
如 `pattern_spec.py:14-16, 36`）指向的文件都存在、行号都在文件范围内。

说明：首轮脚本只按「每反引号一引用」解析，漏展开逗号多段引用，误报 14 行 `NO_REF`；
修正解析器后 73 行全部展开，无 `NO_REF`。此项为核验脚本自身缺陷，不是交付缺陷。

### 2. 锚点语义抽检与全量复核

逐条比对「陈述 / 引用内容」是否互相支撑，73 条全部对上。抽查要点：

- `[16]` `CRISPRGGI` + version 1 → `genome_index.hpp:15-17` 常量齐备。
- `[18]` `4^k + 1` → `offset_count()` 原文 `(1 << (2*k_)) + 1`。
- `[19]` u4/u8 → `position_dtype()` 与 `position_width()` 两处阈值都是 `2^32`，与正文 95-96 行「fewer than 2^32 bases」一致。
- `[27]` `BAD_MAGIC` 等显式错误 → 452-462、499-500、520-521 三处异常原文齐全。
- `[33]` 有效种子长度 = 索引 k → `offtarget_engine/README.md`/设计文档 + `seed_plan.cpp:130` `minimum_seed_len = max(1, kmer_size)`。
- `[38]` 退化行为 → 设计文档 445-452「小基因组整段扫描 / 大基因组退出码 3 / 不静默降敏」+
  `seed_plan.cpp:134-143,192-197` + `search.cpp:46`（50000000 常量）+ `search.cpp:454-462`（守卫）。
- `[55]` `CANDIDATE_GUARD` → `search.cpp:1018-1024` 抛错位置在 `results` 组装阶段，早于任何 JSONL 输出。
- `[63]`-`[66]` 评分与校准状态 → `docs/SCORING_GUIDE.md:71, 20, 219, 39, 44, 53-54, 66` 逐条对上。
- `[72]` 「specified but not implemented」→ `docs/PAIR_RANKING.md:447` 原文「本模式尚未在代码中实现……只作为后续实现的目标契约」。

### 3. 引理数学复核（master 自行推导，非转述）

- (i) 段粒度成立：B 个 bulge 至多影响 B 个段的**内部**连续性，边界处的 bulge 不破坏两侧段内部连续，
  故至少 `s - B >= 1` 个段内部无 bulge。✓
- (ii) 抽屉原理：这 `s-B` 个无 bulge 段的替换数之和 <= `M`，故有一点 <= `floor(M/(s-B)) = allowed`。✓
- (iii) 段->窗口桥：段内总替换数 <= allowed，则段内每个 k-mer 窗口替换数 <= allowed。✓
  服务方在 2.4 末尾主动补了这座桥，判断正确（否则引理在实现口径下不闭合）。
- 额外自查（服务方未写、我补验）：约束 (1) `s <= floor(L/k)` 能保证每段长度 `len_i >= floor(L/s) >= k`，
  即每段至少含一个 k-mer 窗口，与正文 140-141 行的断言一致；`smax = floor(L/k)` 时仍成立。✓
- 与实现的落差已闭合：实现把预算按**窗口**施加（`search.cpp:538-552` 对段内每个 offset 调
  `for_each_seed_variant(..., segment.allowed_mismatches, ...)`），而候选起点是反推出来的
  （`search.cpp:569-572` `candidate_global = global_position - (segment.start + offset)`），
  无 bulge 段内逐位对齐，故反推得到的起点即真实起点，放置必然被枚举到。✓

### 4. 文本规则（脚本 `assets/master_verify_text.py`）

原文输出：

```text
bytes 30072 chars 29328
bom False cr 0 repl 0
sections 8
forbidden first          count=0
forbidden never          count=0
forbidden unprecedented  count=0
forbidden novel          count=0
forbidden 首创       count=0
forbidden 首次       count=0
forbidden 唯一       count=0
cjk_in_body 0
table_rows_with_cjk 62
rows_with_cjk_outside_note ['40']
placeholders TIME/RATIO/N: 3 2 2
absclaim \bwe (show|demonstrate|prove)\b 0
absclaim \boutperform 0
absclaim \bbetter than\b 0
absclaim \bfaster than\b 0
```

结论：正文 0 个中文字符；无 BOM、无 `\r`、无替换字符；无独创性主张；无「outperform / faster than」类比较句。

### 5. 端到端复跑（`native/bin/offtarget-engine.exe`，本机 Windows）

```text
build-index --genome example/engine_benchmark_small/synthetic_genome.fa --prefix out/master_methods_verify/index/synth --k 12
  -> build_exit=0

search --genome ... --index out/master_methods_verify/index/synth --guides example/engine_benchmark_small/guides.tsv --max-mismatch 4 --threads 1
  -> exit 0
     {"type":"summary","guides":12,"hits":43,"candidates":43,"search_time_s":60.390,"memory_peak_mb":140.16,
      "memory_limit_mb":0,"estimated_peak_mb":319.00,"observed_peak_mb":140.16,
      "seed_plan_guaranteed":true,"exhaustive_seed_plan":true,"sequence_cache":true}

search ... --max-mismatch 4 --threads 8
  -> exit 0
     {"type":"summary","guides":12,"hits":43,"candidates":43,"search_time_s":0.325,"memory_peak_mb":155.06,
      "memory_limit_mb":0,"estimated_peak_mb":501.00,"observed_peak_mb":155.06,
      "seed_plan_guaranteed":true,"exhaustive_seed_plan":true,"sequence_cache":true}

HIT_LINES_IDENTICAL: True     （--threads 1 与 --threads 8 的非 summary 行逐字节相同，
                               sha256 前缀 84ae1a985df44d8cd7db25276df45358）

search ... --max-mismatch 2 --max-bulge 1 --threads 8 （L=20, k=12 -> floor(20/12)=1 < B+1=2，无可行计划）
  -> fallback_exit=0，16 行输出
     {"type":"summary","guides":2,"hits":12,"candidates":12,"search_time_s":86.683,...,
      "seed_plan_guaranteed":false,"exhaustive_seed_plan":false,"sequence_cache":true}
```

对应结论：正文 2.5 节 270-282 行对两个标记的语义描述、2.6 节「hit sequence is identical for every value of
`--threads`」、以及 2.7 节退出码契约，均在真实二进制上复现。

附带验证：`example/engine_benchmark_small/run_native-indexed/...` 里的旧索引对当前 FASTA 直接报
`[STALE_INDEX] index fingerprint does not match genome`、退出码 4 —— 顺带复现了锚点 `[24][25]`
（指纹失效检测）与 `[56]`（退出码 4 = io 错误）。

## 归属判定（既有失败 vs 本次引入）

- 本任务为纯新增文档，未触碰任何既有代码/文档，不存在「本次引入的既有功能失败」。
- 两处缺陷（C1 越界、`[1]` 行号）均产生于本次交付，属本次引入，需本轮修复。
- `report.md` 记的 `seed_plan.cpp:129 (void)seed_len` 与 `search.cpp:46` 等，经复核都是**既有**源码行为
  （非本次改动），归属为仓库既有状况，已在下文「附加跟踪」登记。

## 新发现

- **D1 [P2] C1 越界（必修）** `docs/PAPER_METHODS_DRAFT.md:396`（锚点表 [40] 行）陈述列写了中文「窗口数」，
  违反 C1「中文只允许出现在说明列」。修法：把该行陈述列里的「窗口数」换成英文
  `k-mer window count`，其余文本与反引号保持不变。
- **D2 [P2] 锚点 [1] 行号错（必修）** `docs/PAPER_METHODS_DRAFT.md:357` 引 `docs/PAPER_OUTLINE.md:123`，
  但该行是**空行**；2.1 的形式化原文在 `docs/PAPER_OUTLINE.md:126`。同时建议补代码级锚点：
  `shared/design/guide_design.py:54-67, 183-192`（`find_guides` 枚举 + 按身份键去重 + 按位置排序，
  正是正文 45-47 行「complete solution set，只有排序不增删成员」的依据）。master 已回读该文件确认。
- **N1 [P3] PAM 语义偏强** 正文 122-123 行「a 3-prime PAM check」容易被读成「默认强制 PAM」，
  但 `search.hpp:32` `require_pam = false`、`main.cpp:256-257` 是显式 `--require-pam` 才开启。
  建议改为「and PAM side `3prime` (PAM enforcement is opt-in)」。
- **N2 [P3] 引理作用域** 引理未声明「目标窗口是合法 ACGT k-mer」。索引只收录 ACGT 窗口（正文 2.3 [21]），
  基因组含 N 的窗口不会被枚举，故 (iv) 的「every valid k-mer」是唯一边界条件。
  建议在引理假设里加一句，把作用域写死，避免审稿人追问。
- **N3 [P3] 对照说明应移出正文** 212-219 行「Note on source correspondence」是对大纲旧写法的差异说明，
  属内部溯源，不宜出现在 NAR 正文。裁定见下 § 待决项 1。
- **O1 [仓库问题，不在本任务范围]** `--seed-len` 是 CLI 可见参数（`main.cpp:243-249`），
  但 `build_seed_plan` 首行即 `(void)seed_len`（`seed_plan.cpp:126`），即该参数**完全无效**。
  这不是论文问题（正文未声明该参数生效），但属用户可见的空转开关，建议单独开一个仓库任务：
  要么删除该参数，要么在 README/设计文档标注为保留参数。master 已复核源码，结论与 report 一致。

## 待决项裁定（report「待明确」6 条）

1. **「Note on source correspondence」** -> **移出正文**。做法：整段（212-219 行）搬到文末 Anchor table
   之后，新开 `## Supplementary note S1 (source correspondence)`；正文只保留方程 (4)(5)(6) 的**实现口径**表述，
   不出现「draft specification」这类内部语境。理由：投稿正文应读作最终方法，不读作与草稿的 diff；
   且该桥接论证已由引理步骤 (iii) 承担。
2. **公式 ASCII 还是 LaTeX** -> **本轮保持 ASCII**，不改。理由：本文件是 markdown 源，改为 LaTeX 会破坏
   现有自检脚本且此刻无收益；转换发生在套用期刊模板的环节，登记到 `NAR_FORMAT_CHECKLIST` 的待办。
3. **`[1]` 是否改代码级锚点** -> **两者都锚**（大纲行号修正为 `:126`，并补 `guide_design.py:54-67, 183-192`）。
   理由：论文的「完备解集」是设计层承诺，只用大纲锚点证据不足；代码锚点 master 已核验通过。
4. **`[TIME]`/`[RATIO]`/`[N]` 占位符** -> **保持占位**，并在 `NAR_FORMAT_CHECKLIST` 登记
   「投稿前 7 处占位必须由 Results 回填或改为交叉引用」。
5. **`search.cpp:46` 与整段扫描回退是否留在正文** -> **保留**。理由：这是可实现性/敏感度承诺的一部分
   （「Do not silently reduce sensitivity」），且本轮已端到端复现 `seed_plan_guaranteed=false` 路径。
6. **`experiment_calibrated` 的「specified but not implemented」措辞** -> **保留**。
   理由：`docs/PAIR_RANKING.md:447` 原文即如此，且该措辞能防止审稿人误以为有实测校准数据。

## 下一步（最小修复清单，round 2 只做这三件）

1. `docs/PAPER_METHODS_DRAFT.md:396` —— [40] 行陈述列改英文（见 D1 修法）。
2. `docs/PAPER_METHODS_DRAFT.md:357` —— [1] 行锚点改为
   `docs/PAPER_OUTLINE.md:126`; `shared/design/guide_design.py:54-67, 183-192`，
   并同步更新该行说明列。
3. `docs/PAPER_METHODS_DRAFT.md:212-219` —— 整段移到文末新开的 `## Supplementary note S1`，
   并把 [40] 行说明列改为指向 S1。

可选（同一轮内顺手做，不做也不阻塞）：N1（PAM 措辞）、N2（引理作用域加一句）。

round 2 自检下限：重跑 `assets/master_verify_anchors.py` 与 `assets/master_verify_text.py`，
要求仍为 `PROBLEMS=[]`、`rows_with_cjk_outside_note=[]`、`cjk_in_body=0`、八个 `### 2.x` 顺序不变。
修完把 `state.json` 置回 `ready_for_review` 并写 round 2 的 `report.md`；核验仍归 master。


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
