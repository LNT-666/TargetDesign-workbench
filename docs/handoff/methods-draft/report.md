# 交付报告：methods-draft

- round: 1
- status: ready_for_review
- updated: 2026-09-19 10:14

## 改动清单

| 文件 | 行 | 改了什么 | 对应任务项 |
| --- | --- | --- | --- |
| `docs/PAPER_METHODS_DRAFT.md` | 1-430（新增） | 新增 NAR Methods 英文初稿：2.1-2.8 共 8 小节 + Algorithm 1 + Lemma 1 与证明 + 73 条 Anchor table | P0-1 / P0-2 / P0-3 / P1-1 |
| `docs/PAPER_METHODS_DRAFT.md` | 13-48 | 2.1 Design specification：`S = (L,P,l,o,s)` 与 `D(S)`、三类布局、IUPAC 字符集、区间校验 | P1-1 |
| `docs/PAPER_METHODS_DRAFT.md` | 49-85 | 2.2 Motif-anchored layouts and strand enumeration：Pattern A/B 布局、`++/+-/-+/--` 四链向、0-based half-open 区间、IUPAC PAM 位掩码匹配 | P1-1（四链向） |
| `docs/PAPER_METHODS_DRAFT.md` | 86-115 | 2.3 Index format：CRISPRGGI v1 布局、`4^k+1` offsets、u4/u8 自适应、metadata 指纹失效检测、mmap 只读共享、临时文件+rename 发布 | P0-1 |
| `docs/PAPER_METHODS_DRAFT.md` | 116-220 | 2.4 Seed-plan synthesis：约束 (1)(2)、partition_lengths (3)、W(s) (4)、饱和算术、`(W(s), s)` 字典序最小，含 Algorithm 1（27 行伪码） | P0-2 |
| `docs/PAPER_METHODS_DRAFT.md` | 221-283 | 2.5 Lemma 1（假设—结论—证明三段式，抽屉原理四步）＋ `seed_plan_guaranteed` / `exhaustive_seed_plan` 语义与退化行为 | P0-3 |
| `docs/PAPER_METHODS_DRAFT.md` | 284-297 | 2.6 Deterministic parallelism：worker pool over guides、输入序合并、线程数无关的命中序列 | P0-1 |
| `docs/PAPER_METHODS_DRAFT.md` | 298-318 | 2.7 Resource bounds：`--max-memory-mb`、预检+RSS 检查、候选上限、退出码 0/2/3/4/5 | P0-1 |
| `docs/PAPER_METHODS_DRAFT.md` | 319-347 | 2.8 Calibration-state propagation and pair ranking：校准状态标签、特异性聚合、PairRank 两模式与 `B_pair+`/`M_pair+`/`H_pair` | P0-1 |
| `docs/PAPER_METHODS_DRAFT.md` | 348-430 | Anchor table：73 行，每行 `文件:行`；中文仅出现在「说明」列 | C3 |
| `docs/handoff/methods-draft/state.json` | 4, 13 | status: assigned -> implementing -> ready_for_review；updated 时间戳 | §7 |

未改动任何既有代码/文档/fixture：`git status` 之外的核对方式见下（本仓库为共享盘，未使用 git 历史，改用「改动文件清单 + 目标文件是否新建」判定）。

## 轻量自检结果

命令 1（任务 §6 原文）：

`ash
cd R:\songji\programfile
python -c "d=open(r'docs\PAPER_METHODS_DRAFT.md',encoding='utf-8').read();print('chars',len(d));print('sections',d.count('### 2.'));print('anchor_rows',d.count('| ['))"
`

输出原文：

`	ext
chars 29328
sections 8
anchor_rows 73
`

命令 2（禁令词 + 中文位置 + 编码 + 编号闭合）：

`ash
python -c "
import re
d=open(r'docs\PAPER_METHODS_DRAFT.md',encoding='utf-8').read()
print('chars',len(d));print('sections',d.count('### 2.'));print('anchor_rows',d.count('| ['))
print('first',d.lower().count('first'),'never',d.lower().count('never'))
body,table=d.split('## Anchor table')
rows=set(int(m) for m in re.findall(r'^\| \[(\d+)\]',table,re.M))
refs=set(int(m) for m in re.findall(r'\[(\d+)\]',body))
print('rows',len(rows),'min',min(rows),'max',max(rows))
print('refs_missing_row',sorted(refs-rows))
print('rows_never_cited',sorted(rows-refs))
"
`

输出原文：

`	ext
chars 29328
sections 8
anchor_rows 73
first 0 never 0
rows 73 min 1 max 73
refs_missing_row []
rows_never_cited []
`

命令 3（中文只出现在 Anchor table 之后、无 BOM、小节标题列表）：

`	ext
first_cjk_index 19602
anchor_table_index 19311
bom b'# M'
sections_list ['### 2.1 Design specification', '### 2.2 Motif-anchored layouts and strand enumeration', '### 2.3 Index format', '### 2.4 Seed-plan synthesis', '### 2.5 Lemma 1 (completeness) and proof', '### 2.6 Deterministic parallelism', '### 2.7 Resource bounds', '### 2.8 Calibration-state propagation and pair ranking']
`

结论：8 个小节顺序与 C2 一致；anchor_rows 73 >= 25；无 `first` / `never` / `unprecedented` / `首创`；中文首个字符位置（19602）大于 `## Anchor table` 位置（19311），即中文只出现在说明列；无 BOM。以上仅为本人可做的轻量自检，不构成核验结论。

## 未做项

- 无跳过的必做项。以下为按 C2/规则做的范围收束，记录备查（不是漏做）：
  - 大纲 §2.9（IUPAC PAM 3prime/5prime 双链匹配）未单列小节，按 C2 的固定 8 小节并入 2.2 末尾一段（正文第 80-85 行，锚点 [59]-[62]）。
  - 大纲 §2.6（种子计划退化行为）并入 2.5 末尾（第 269-283 行，锚点 [38][43][56]）。
  - 大纲 §2.11（实现与测试）未写入：C2 未列该小节，且「32 个测试模块」「Python 3.13」不属于本轮可核验范围，写入会引入 §2 未列行为。
  - 未写 Introduction / Results / Discussion / Abstract（§0 边界）。
  - 未使用任何性能数字；Results 相关处一律占位 `[TIME]` / `[RATIO]` / `[N]`，并在文首统一说明。

## 附带发现（不在本次范围，未修）

- `native/offtarget_engine/src/seed_plan.cpp:129` — `build_seed_plan` 第一行是 `(void)seed_len;`，即 `seed_len` 参数被忽略；CLI 的 `--seed-len`（`native/offtarget_engine/src/main.cpp:247-249`）因此不影响计划合成，实际种子长度恒为索引 `k`（同 `docs/NATIVE_INDEXED_ENGINE_DESIGN.md:434-443` 的「minimum seed length is the index k」）。建议：或删除该参数，或在文档中明确标注为保留参数。本次未写入正文（§2 未列该行为），仅在 2.4 用「k 是有效种子长度」表达。
- `native/offtarget_engine/src/seed_plan.cpp:63-69` — `segmented_variant_work` 实际为 `max(1, len - k + 1) * variant_count(k, allowed)`，与 task.md C4 写的 `sum_{c<=allowed} C(size, c) * 3^c`（按段长、无窗口因子）不一致。本次以源码为准，正文方程 (4)(5)(6) 采用源码写法，并在 2.4 末尾加了 "Note on source correspondence" 一段（英文）；Anchor table 的 [40] 行说明列注明此处为差异点。
- `native/offtarget_engine/src/search.cpp:46` — `kMaxExhaustiveFallbackBases = 50000000` 与 `search.cpp:454-533` 的「未保证计划时的整段扫描回退」不在 task.md §2 的清单内；因 P0-3 要求说明 `seed_plan_guaranteed` / `exhaustive_seed_plan` 语义，正文 2.5 末尾引用了该行为（锚点 [38][56]）。请 master 判定是否保留。
- 引理的抽屉原理在「段」粒度成立，而实现把 `allowed` 预算施加在段内每个 k-mer 窗口上；正文 2.4 的 note 与 Lemma 步骤 (iii) 显式搭了这座桥（段无 bulge 且段内总错配 <= allowed => 每个窗口错配 <= allowed）。若 master 认为该桥不必写进论文正文，可在 review 中指出，我再收束。
- `docs/PAIR_RANKING.md:447` 明确写「本模式尚未在代码中实现」（指 `experiment_calibrated`）。正文 2.8 据此写成「specified but not implemented in the current pipeline」，以免审稿人误以为有实测校准数据。请确认该措辞是否保留。

## 待明确

- 「Note on source correspondence」段落（2.4 末尾，正文第 213-220 行）是工程对照说明，是否保留在论文正文？推荐：正文删除，移入 Supplementary 或 Implementation 附录，由 master 决定。
- 正文公式目前用 ASCII（`W(s) = sum_i ...`），NAR 投稿通常用 LaTeX/Word 公式。是否需要在下一轮改写成 LaTeX 记号（如 `\sum_{i}`）？
- 是否把 `[1]` 锚定的「`D(S)` 为完备解集」改为代码级锚点（例如 `shared/design/guide_design.py` 的枚举入口）；该文件不在 task.md §2 的证据清单内，故本轮先锚在大纲 `docs/PAPER_OUTLINE.md:123`。
- `[TIME]` / `[RATIO]` / `[N]` 三个占位符的最终处理方式（由 Results 回填数字，还是改成「see Results」交叉引用）。

---

## round 2（2026-09-19 11:04）

- status: ready_for_review
- 依据：`review.md`「下一步（最小修复清单，round 2 只做这三件）」+ `task.md` §8
- 改前快照：`docs/handoff/methods-draft/assets/round1_baseline_PAPER_METHODS_DRAFT.md` 与
  `backup/20260919_methods_draft_round1/PAPER_METHODS_DRAFT.md`
  （同一份 round 1 交付的 copy：29328 字符 / 30072 字节，逐字未改）
- 改动方式：一次性 Python 脚本（`%TEMP%\servant_round2_edit.py`，未入库），每处替换都先断言「唯一命中」再改写；含中文的说明列改写只经由 UTF-8 显式读写，未用 PowerShell 回写。

### 改动清单（round 2）

| 文件 | 改前行号 | 改后行号 | 改了什么 | 对应条目 |
| --- | --- | --- | --- | --- |
| `docs/PAPER_METHODS_DRAFT.md` | 396 | 390 | [40] 行「陈述」列 `窗口数` -> `k-mer window count`，与其余行同语种 | §8-1 / D1 |
| `docs/PAPER_METHODS_DRAFT.md` | 357 | 351 | [1] 行锚点 `docs/PAPER_OUTLINE.md:123` -> `docs/PAPER_OUTLINE.md:151`，并补 `shared/design/guide_design.py:54-67, 183-192`；「说明」列同步 | §8-2 / D2（行号有偏离，见「待明确」1） |
| `docs/PAPER_METHODS_DRAFT.md` | 212-220 | 425-434 | 2.4 末尾「Note on source correspondence」整段（正文 8 行 + 其后空行）移出正文，逐字不变，落到文末 `## Supplementary note S1 (source correspondence)`；[40] 行「说明」列改为指向 S1 | §8-3 / N3 |
| `docs/PAPER_METHODS_DRAFT.md` | 123 | 123-124 | 可选 N1：`a 3-prime PAM check [58]` -> `PAM side 3prime; PAM enforcement is opt-in through an explicit flag [58]` | §8 可选项 |
| `docs/PAPER_METHODS_DRAFT.md` | 414 | 408 | 可选 N1：[58] 行补 `native/offtarget_engine/src/main.cpp:256-257` 锚点，「说明」列补 `require_pam 默认关闭` | §8 可选项 |
| `docs/PAPER_METHODS_DRAFT.md` | 228-233 | 220-227 | 可选 N2：Lemma 1 假设里加作用域一句（target windows 只取 `A/C/G/T`，含其它字符的窗口不入索引 [21]） | §8 可选项 |
| `docs/handoff/methods-draft/report.md` | 末尾 | 末尾 | 追加本小节（round 1 内容原样保留） | §7 / §8 |
| `docs/handoff/methods-draft/state.json` | - | - | `status` -> `ready_for_review`、`round` -> 2、`updated` | §8 |
| `backup/20260919_methods_draft_round1/PAPER_METHODS_DRAFT.md` | 新增 | 新增 | 改前快照，按仓库 `backup/<date>_<slug>/` 约定 | 交接约定 |
| `docs/handoff/methods-draft/assets/round1_baseline_PAPER_METHODS_DRAFT.md` | 新增 | 新增 | 同一份快照，放在交接目录便于 master 直接 diff | 交接约定 |

除上表所列，未写入任何既有文件；`docs/PAPER_METHODS_DRAFT.md` 的内容行数 429 -> 434（按 `\n` 计数，改前 = Get-Content 行数 429，改后 = 434）。

### 自检命令与输出原文

命令 1（round 2 下限 A，master 脚本原样复跑）：

```text
cd R:\songji\programfile
$env:PYTHONIOENCODING='utf-8'; python docs\handoff\methods-draft\assets\master_verify_text.py
```

输出原文：

```text
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
forbidden first          count=0
forbidden never          count=0
forbidden unprecedented  count=0
forbidden novel          count=0
forbidden 首创             count=0
forbidden 首次             count=0
forbidden 唯一             count=0
cjk_in_body 0
table_rows_with_cjk 62
rows_with_cjk_outside_note []
placeholders TIME/RATIO/N: 3 2 2
absclaim \bwe (show|demonstrate|prove)\b 0
absclaim \boutperform 0
absclaim \bbetter than\b 0
absclaim \bfaster than\b 0
```

命令 2（round 2 下限 B，master 脚本原样复跑）：

```text
cd R:\songji\programfile
$env:PYTHONIOENCODING='utf-8'; python docs\handoff\methods-draft\assets\master_verify_anchors.py
```

输出原文：

```text
written R:\songji\programfile\docs\handoff\methods-draft\assets\master_anchors.txt lines 953
TABLE_ROWS=73  min=1  max=73
MISSING_ROWS_FOR_CITED=[]
ROWS_NEVER_CITED=[]
TABLE_NUMBER_GAPS=[]
PROBLEMS=[]
```

命令 3（与基线快照逐行 diff + 回读被引用锚点原文）：

```text
baseline_file_bytes 30072 current_bytes 30595
--- hunks (old->new line numbers) ---
replace  old 123-123  new 123-124
delete   old 212-220  new 213-212
replace  old 228-233  new 220-227
replace  old 357-357  new 351-351
replace  old 396-396  new 390-390
replace  old 414-414  new 408-408
insert   old 431-430  new 425-435
--- key lines in the current file ---
[1] row        [351]
        351: | [1] | Design request `S = (L, P, l, o, s)`; output is the complete solution set | `docs/PAPER_OUTLINE.md:151`; `shared/design/guide_design.py:54-67, 183-192` | 大纲 2.1 条原文（形式化与完备解集）；代码级：枚举、按身份键去重、按位置排序 |
[40] row       [390]
        390: | [40] | `segmented_variant_work` = k-mer window count x `variant_count(k, allowed)` | `native/offtarget_engine/src/seed_plan.cpp:63-69` | 与任务文本 W(s) 写法的差异说明见文末 Supplementary note S1 |
[58] row       [408]
        408: | [58] | Search option defaults | `native/offtarget_engine/include/offtarget/search.hpp:22-39`; `native/offtarget_engine/src/main.cpp:256-257` | `max_mismatch=4`、`max_bulge=0`、`pam_side=3prime`、`require_pam` 默认关闭 |
S1 heading     [425]
        425: ## Supplementary note S1 (source correspondence)
PAM wording    [123]
        123: (`M = 4`), no bulges (`B = 0`) and PAM side `3prime`; PAM enforcement is
Lemma scope    [221]
        221: k-mer windows consist of `A`, `C`, `G` and `T` only: a window containing any
2.5 heading    [213]
        213: ### 2.5 Lemma 1 (completeness) and proof
--- read back the anchors cited by the changed rows ---
docs/PAPER_OUTLINE.md:149-152 (file lines=375)
     149| ### 2 Materials and Methods
     150| 
     151| - 2.1 设计规格形式化：`S = (L, P, l, o, s)` 与解空间 `D(S)` 定义，说明输出是完备解集。
     152| - 2.2 三元件布局与链向组合枚举；`left_target_start/end` 等区间语义。
shared/design/guide_design.py:54-56 (file lines=243)
      54| def find_guides(sequence, spacer_len=20, pam=None, pam_side="3prime",
      55|                 motif=None, allow_reverse=True, seq_id=None):
      56|     """Enumerate guide candidates in a single sequence.
shared/design/guide_design.py:183-192 (file lines=243)
     183|     unique = []
     184|     for item in candidates:
     185|         key = (item["seq_id"], item["strand"], item["spacer_start"], item["spacer_end"],
     186|                item["pam_start"], item["pam_end"])
     187|         if key in seen:
     188|             continue
     189|         seen.add(key)
     190|         unique.append(item)
     191|     unique.sort(key=lambda x: (x["spacer_start"], x["spacer_end"], x["strand"]))
     192|     return unique
native/offtarget_engine/src/main.cpp:256-257 (file lines=422)
     256|         } else if (argument == "--require-pam") {
     257|             options.require_pam = true;
native/offtarget_engine/src/seed_plan.cpp:63-69 (file lines=248)
      63| std::uint64_t segmented_variant_work(int segment_len, int kmer_size,
      64|                                      int max_mismatch) {
      65|     const std::int64_t window_count =
      66|         std::max<std::int64_t>(1, segment_len - kmer_size + 1);
      67|     const std::uint64_t variants = variant_count(kmer_size, max_mismatch);
      68|     return static_cast<std::uint64_t>(window_count) * variants;
      69| }
PROBE_DONE
```

命令 4（锚点 [1] 在 master 锚点转储里的展开原文）：

```text
=== [1] Design request `S = (L, P, l, o, s)`; output is the complete solution set
    note: 大纲 2.1 条原文（形式化与完备解集）；代码级：枚举、按身份键去重、按位置排序
    docs/PAPER_OUTLINE.md:151
       151| - 2.1 设计规格形式化：`S = (L, P, l, o, s)` 与解空间 `D(S)` 定义，说明输出是完备解集。
    shared/design/guide_design.py:54-67
        54| def find_guides(sequence, spacer_len=20, pam=None, pam_side="3prime",
        55| motif=None, allow_reverse=True, seq_id=None):
        56| """Enumerate guide candidates in a single sequence.
        57| 
        58| Parameters use the same conventions as the GUI:
        59| pam_side='3prime' -> [spacer][PAM] on the scanned strand
        60| pam_side='5prime' -> [PAM][spacer] on the scanned strand
        61| Returns a list of candidate dicts sorted by genomic position.
        62| """
        63| seq = sequence.upper().replace("U", "T")
        64| n = len(seq)
        65| spacer_len = int(spacer_len) if spacer_len else 20
        66| if spacer_len <= 0 or n < spacer_len:
        67| return []
    shared/design/guide_design.py:183-192
       183| unique = []
       184| for item in candidates:
       185| key = (item["seq_id"], item["strand"], item["spacer_start"], item["spacer_end"],
       186| item["pam_start"], item["pam_end"])
       187| if key in seen:
       188| continue
       189| seen.add(key)
       190| unique.append(item)
       191| unique.sort(key=lambda x: (x["spacer_start"], x["spacer_end"], x["strand"]))
       192| return unique
```

命令 5（改后说明列的码点核验，避免「看着对、其实坏」）：

```text
replacement_char_present False question_marks 0
--- formatting around the moved note / 2.5 heading ---
 208| window inside it, all k-mers within Hamming distance `allowed` of the probe
 209| window are generated, every genomic occurrence of such a k-mer yields a
 210| candidate position, and each candidate is then verified by the alignment stage
 211| against `M` substitutions and `B` bulges [45][46][43].
 212| 
 213| ### 2.5 Lemma 1 (completeness) and proof
 214| 
 215| **Lemma 1 (seed-plan completeness).** Let `L`, `M`, `B` and `k` be as above,
 216| let `s` be an integer with `max(1, B + 1) <= s <= floor(L / k)`, let
--- S1 tail ---
 424| 
 425| ## Supplementary note S1 (source correspondence)
 426| 
 427| Note on source correspondence: the per-segment cost evaluated by the
 428| implementation is the number of k-mer windows in the segment multiplied by the
 429| number of variants of a single k-mer of length `k`, as in equations (5) and
 430| (6), rather than a binomial sum over the full segment length. Because a segment
 431| that carries at most `allowed` substitutions in total also carries at most
 432| `allowed` substitutions in each of its k-mer windows, the completeness argument
 433| of Section 2.5 is unaffected. The Anchor table records the anchors and notes
 434| the wording difference from the draft specification.
 435| 
note_verbatim_in_S1_and_absent_from_body True True
--- codepoints of the changed note cells (ascii repr) ---
| [1] | Design request -> '\u5927\u7eb2 2.1 \u6761\u539f\u6587\uff08\u5f62\u5f0f\u5316\u4e0e\u5b8c\u5907\u89e3\u96c6\uff09\uff1b\u4ee3\u7801\u7ea7\uff1a\u679a\u4e3e\u3001\u6309\u8eab\u4efd\u952e\u53bb\u91cd\u3001\u6309\u4f4d\u7f6e\u6392\u5e8f'
| [40] | -> '\u4e0e\u4efb\u52a1\u6587\u672c W(s) \u5199\u6cd5\u7684\u5dee\u5f02\u8bf4\u660e\u89c1\u6587\u672b Supplementary note S1'
| [58] | -> '`max_mismatch=4`\u3001`max_bulge=0`\u3001`pam_side=3prime`\u3001`require_pam` \u9ed8\u8ba4\u5173\u95ed'
baseline [1] note cell -> '\u5927\u7eb2 2.1 \u6761\u539f\u6587\uff1a\u5f62\u5f0f\u5316\u4e0e\u5b8c\u5907\u89e3\u96c6'
CHECK_DONE
```

结论（仅本人可做的轻量自检，不构成核验）：三条必做 + 两条可选均落地；`PROBLEMS=[]`、`rows_with_cjk_outside_note=[]`、`cjk_in_body=0`、八个 `### 2.x` 顺序不变、73 行编号无缺口、无 BOM/CR/替换字符。

### 未做项

- 无漏做的必做项。范围收束说明：未改 2.5 的证明正文、未改公式（仍 ASCII）、未动 `[TIME]`/`[RATIO]`/`[N]` 占位符、未动 2.6-2.8、未改任何代码或 fixture。

### 附带发现（只记录，不修）

- `docs/PAPER_OUTLINE.md` 的 mtime 是 2026-09-19 10:40:40，晚于 `review.md`（10:36:51），行号整体下移：review 给的 `:126` 现在是 `### Title`，现行 2.1 形式化原文在 `:151`（同一时刻 `docs/PAPER_OUTLINE_WITH_EXPERIMENTS.md` 也是 10:40:40）。见「待明确」1。
- round 1「附带发现」三条（`--seed-len` 空转、`segmented_variant_work` 与任务文本差异、整段扫描回退）本轮无新证据，仍以 round 1 记录为准。
- 本轮给 Lemma 1 加了 `[21]` 引用；[21] 本就在锚点表内，编号闭合检查仍为 `ROWS_NEVER_CITED=[]` / `TABLE_NUMBER_GAPS=[]`。
- 复跑 master 脚本会重写 master 自己的转储 `assets/master_anchors.txt`（本轮已变为 round 2 的转储，44617 字节，11:04；round 1 的转储已被覆盖）。如需保留各轮转储，建议下一轮改名或加轮次后缀。

### 待明确

1. `[1]` 行锚点行号：本轮按「锚点必须指向支持该陈述的行」写成 `docs/PAPER_OUTLINE.md:151`；review.md 写的是 `:126`，但 `:126` 在当前文件里是 `### Title`（`docs/PAPER_OUTLINE_WITH_EXPERIMENTS.md` 之外无第二份大纲可对照）。若 master 判定必须用 `:126`，本轮改回只涉及 [1] 行一处锚点与说明列。
2. N1/N2 为 review 与 task.md §8 明列的可选项，本轮已做；若 master 要求正文严格等于「最小修复清单」三条，可回退这两处，回退原文在基线快照内（改前 123 行、228-233 行、414 行）。

