# 种子计划分析（Seed Plan Analysis）

- 任务：`docs/handoff/engine-bench/task.md` 遗留件（该任务由 master 接管），本文件为其交付物 `docs/SEED_PLAN_ANALYSIS.md`。
- 输入（只读）：`docs/seed_plan_sweep.json`（engine-bench 实测产物，16 条记录）、`native/offtarget_engine/src/seed_plan.cpp`、
  `tools/seed_plan_sweep.py`、`Target_xbp_Target/extract_complex_queries.py`、`Target_xbp_Y_zbp_Target/extract_motifs.py`。
- 环境：本机 Windows，`python` = 3.14.7；引擎 `native/bin/offtarget-engine.exe` 本地可运行。
- fixture：`example/engine_benchmark_small/synthetic_genome.fa`（1,000,000 bp）、`guides.tsv`（12 条 20 nt 引导）
  [seed_plan_sweep.json:fixture]。
- 口径：本文件所有数字均取自上述实测产物并在其后给出短出处；不重跑大型计算。

## 1. W(s) 复现

种子计划在运行期由 `build_seed_plan` 合成，其代价模型为

```text
W(s) = sum_i max(1, L_i - k + 1) * V(k, a),
V(k, a) = sum_c C(k, c) * 3**c,
a = M // (N_seeds - B)
```

上述三行为 `docs/seed_plan_sweep.json` 的 `protocol.cost_model` 原文 [seed_plan_sweep.json:protocol.cost_model]；
其中 `N_seeds` 即段数 `s`，`L_i` 为第 i 段的长度。

源码锚点（逐项对应）：

| 模型要素 | 源码位置 | 行为 |
| --- | --- | --- |
| `build_seed_plan` | `native/offtarget_engine/src/seed_plan.cpp:123-206` | 入口；枚举 `seed_count = s`，择优并置 `guaranteed` |
| `seed_len` 被忽略 | `native/offtarget_engine/src/seed_plan.cpp:126`（`(void)seed_len;`） | `--seed-len` 不参与计划；k-mer 大小即有效种子长度 |
| `partition_lengths` | `native/offtarget_engine/src/seed_plan.cpp:54-61` | `L_i = L/s`，余数分给前 `L mod s` 段（尽量均分） |
| `segmented_variant_work` | `native/offtarget_engine/src/seed_plan.cpp:63-69` | `max(1, len - k + 1) * variant_count(k, allowed)`，含窗口因子 |
| `allowed = M // (s - B)` | `native/offtarget_engine/src/seed_plan.cpp:151,155` | 每段错配预算；`denominator = seed_count - max_bulge` |
| `binomial` | `native/offtarget_engine/src/seed_plan.cpp:33-44` | 饱和式二项式系数，溢出返回 `cap + 1` |
| `power_three` | `native/offtarget_engine/src/seed_plan.cpp:46-52` | 饱和式 `3^c` |
| `variant_count` | `native/offtarget_engine/src/seed_plan.cpp:105-121` | `V(k, m) = sum_{c<=m} C(k, c) * 3^c` |
| `visit_variants` / `for_each_seed_variant` | `native/offtarget_engine/src/seed_plan.cpp:71-101,239-246` | 逐窗口枚举 Hamming 距离 `<= allowed` 的全部变体 |
| 段选择键 | `native/offtarget_engine/src/seed_plan.cpp:180-187` | 按 `(W(s), s)` 字典序取最小 |

复现命令（本机实跑）：

```powershell
cd R:\songji\programfile
python tools\seed_plan_sweep.py --plan-table
```

输出原文：

```text
V(k, m) = sum_c C(k, c) * 3**c  [variant_count, seed_plan.cpp:105]
k  m  V(k, m)
8  0  1
8  1  25
8  2  277
8  3  1789
10 0  1
10 1  31
10 2  436
10 3  3676

seed plan / W(s) for probe_len=20, kmer_size=k, cap=500000 [build_seed_plan, seed_plan.cpp:123]
k  M  B  N  seg_len  allowed  W(s)  guaranteed  segments
8  0  0  2  10      0        6     true        2x10bp@0
8  0  1  2  10      0        6     true        2x10bp@0
8  1  0  2  10      0        6     true        2x10bp@0
8  1  1  2  10      1        150   true        2x10bp@1
8  2  0  2  10      1        150   true        2x10bp@1
8  2  1  2  10      2        1662  true        2x10bp@2
8  3  0  2  10      1        150   true        2x10bp@1
8  3  1  2  10      3        10734 true        2x10bp@3
10 0  0  2  10      0        2     true        2x10bp@0
10 0  1  2  10      0        2     true        2x10bp@0
10 1  0  2  10      0        2     true        2x10bp@0
10 1  1  2  10      1        62    true        2x10bp@1
10 2  0  2  10      1        62    true        2x10bp@1
10 2  1  2  10      2        872   true        2x10bp@2
10 3  0  2  10      1        62    true        2x10bp@1
10 3  1  2  10      3        7352  true        2x10bp@3
```

要点：

- `V(k, m)`：k=8 时 m=0..3 为 1 / 25 / 277 / 1789；k=10 时为 1 / 31 / 436 / 3676 [上表；seed_plan.cpp:105-121]。
- `probe_len=20` 时全部 16 组的最优段数均为 `s* = 2`，且分段恒为 `2x10bp@allowed`（即两段各 10 bp）[上表]。
- 只有当 `s - B >= 1` 时 `allowed` 才非零；故 `B=1` 把 `allowed` 从 `M//2` 抬到 `M//1`，`W(s)` 随之上升
  （k=10：`(M,B)=(0,0)` 为 2，`(3,1)` 为 7352）[上表]。
- 语料中的 `cap=500000` 即 `DEFAULT_MAX_SEED_VARIANTS` [tools/seed_plan_sweep.py:49]，与 C++ 默认值一致。

## 2. 16 组网格表（seed_plan_sweep.json）

协议：`M x B x k` = {0,1,2,3} x {0,1} x {8,10} = 16 组；每组重复 3 次，`threads=8`；每个 k 只建一次索引并复用到
该 k 的全部 M/B 组合 [seed_plan_sweep.json:protocol]。本表 `s*` 与 `W(s)` 取自记录中的 Python 复算字段
（`py_plan_segments` 的首段数、`py_plan_variants`），与引擎侧 `seed_plan_guaranteed` / `exhaustive_seed_plan` 并列。

| k | M | B | s* | W(s) | guaranteed | segments | median search (s) | candidates | hits | peak RSS (MB) | repeats consistent |
| ---: | ---: | ---: | ---: | ---: | --- | --- | ---: | ---: | ---: | ---: | --- |
| 8 | 0 | 0 | 2 | 6 | true | `2x10bp@0` | 0.207 | 24 | 24 | 16.05 | true |
| 8 | 0 | 1 | 2 | 6 | true | `2x10bp@0` | 0.219 | 26 | 26 | 16.1 | true |
| 8 | 1 | 0 | 2 | 6 | true | `2x10bp@0` | 0.202 | 36 | 36 | 16.45 | true |
| 8 | 1 | 1 | 2 | 150 | true | `2x10bp@1` | 0.414 | 37 | 37 | 18.95 | true |
| 8 | 2 | 0 | 2 | 150 | true | `2x10bp@1` | 0.213 | 36 | 36 | 18.58 | true |
| 8 | 2 | 1 | 2 | 1662 | true | `2x10bp@2` | 2.366 | 38 | 38 | 32.3 | true |
| 8 | 3 | 0 | 2 | 150 | true | `2x10bp@1` | 0.398 | 36 | 36 | 18.81 | true |
| 8 | 3 | 1 | 2 | 10734 | true | `2x10bp@3` | 12.404 | 67 | 67 | 93.09 | true |
| 10 | 0 | 0 | 2 | 2 | true | `2x10bp@0` | 0.212 | 24 | 24 | 15.42 | true |
| 10 | 0 | 1 | 2 | 2 | true | `2x10bp@0` | 0.205 | 26 | 26 | 15.68 | true |
| 10 | 1 | 0 | 2 | 2 | true | `2x10bp@0` | 0.219 | 36 | 36 | 23.59 | true |
| 10 | 1 | 1 | 2 | 62 | true | `2x10bp@1` | 0.219 | 37 | 37 | 24.04 | true |
| 10 | 2 | 0 | 2 | 62 | true | `2x10bp@1` | 0.209 | 36 | 36 | 16.99 | true |
| 10 | 2 | 1 | 2 | 872 | true | `2x10bp@2` | 0.306 | 38 | 38 | 26.37 | true |
| 10 | 3 | 0 | 2 | 62 | true | `2x10bp@1` | 0.207 | 36 | 36 | 23.93 | true |
| 10 | 3 | 1 | 2 | 7352 | true | `2x10bp@3` | 1.082 | 66 | 66 | 31.8 | true |

```text
records=16, 全部 seed_plan_guaranteed=true, 全部 exhaustive_seed_plan=true, 全部 py_plan_guaranteed=true, 全部 repeats_consistent=true
首条 M0/B0/k8 : median 0.207 s, candidates 24, hits 24, py_plan_variants 6 [seed_plan_sweep.json:records[0]]
末条 M3/B1/k10: median 1.082 s, candidates 66, hits 66, py_plan_variants 7352 [seed_plan_sweep.json:records[15]]
```

索引构建（每个 k 一次）[seed_plan_sweep.json:index_builds]：

| k | threads | build time (s) | index bytes | total bases | position dtype |
| ---: | ---: | ---: | ---: | ---: | --- |
| 8 | 8 | 0.955 | 4524314 | 1000000 | `u4` |
| 10 | 8 | 0.316 | 12388602 | 1000000 | `u4` |

- 16 组全部落在变体上限内并置 `guaranteed=true`；`candidates == hits` 恒成立（该 fixture 无被拒候选）
  [seed_plan_sweep.json:records]。
- 命中数随预算单调上升：`(0,0)` 为 24，`(3,1)` 为 67（k=8）与 66（k=10）[seed_plan_sweep.json:records]。

## 3. 确定性表（--determinism 实跑）

命令（本机实跑，`probe_len=20` 的 fixture，`M=2, B=0, k=10`）：

```powershell
cd R:\songji\programfile
python tools\seed_plan_sweep.py --determinism
```

输出原文：

```text
threads=1 hits=36 sha256=0549c426662a2fa2994b8696971c51366f330456ed7392adaa58d7be62cbf499
threads=4 hits=36 sha256=0549c426662a2fa2994b8696971c51366f330456ed7392adaa58d7be62cbf499
threads=8 hits=36 sha256=0549c426662a2fa2994b8696971c51366f330456ed7392adaa58d7be62cbf499
threads=32 hits=36 sha256=0549c426662a2fa2994b8696971c51366f330456ed7392adaa58d7be62cbf499

M=2 B=0 k=10 threads=[1, 4, 8, 32]
hits per thread count: [36, 36, 36, 36]
sha256_all_equal: true (1 distinct values)
```

| threads | hits | sha256 (hit 行，换行连接) |
| ---: | ---: | --- |
| 1 | 36 | `0549c426662a2fa2994b8696971c51366f330456ed7392adaa58d7be62cbf499` |
| 4 | 36 | `0549c426662a2fa2994b8696971c51366f330456ed7392adaa58d7be62cbf499` |
| 8 | 36 | `0549c426662a2fa2994b8696971c51366f330456ed7392adaa58d7be62cbf499` |
| 32 | 36 | `0549c426662a2fa2994b8696971c51366f330456ed7392adaa58d7be62cbf499` |

- 四个线程数命中行逐字节相同，digest 唯一 [上表；tools/seed_plan_sweep.py:sha256_of_hits]。
- 独立佐证（另一 fixture：5,000,000 bp、2,400 条引导、`M=2/B=0/k=10`）：1/4/8/16/32 线程均返回 1000 命中且
  hit-only digest 相同 [docs/NATIVE_INDEXED_BENCHMARK.md:19-21,27-31]。
- 前序 methods-draft 核验在另一 fixture 上实测的 digest 前缀为 `84ae1a985df44d8cd7db25276df45358`
  [docs/handoff/manuscript-v1/task.md §2.2]；digest 取决于 fixture 与 guide 集合，两处不可直接比较，但都满足
  「同一 fixture 内线程数无关」。

## 4. 组合复杂度与剪枝

配对提取（Pattern A，`Target_xbp_Target/extract_complex_queries.py`）：

- 左右 motif 各自在双链匹配：先取反向互补 `left_motif_minus` / `right_motif_minus`
  [extract_complex_queries.py:51-52]，再对四种链向组合逐个枚举
  （`plus/plus`、`plus/minus`、`minus/plus`、`minus/minus`）[extract_complex_queries.py:103-108]。
- 距离约束剪枝：对每个左位点 `lpos` 计算允许区间
  `[lpos + len(l_motif) + min_gap, lpos + len(l_motif) + max_gap]`，再在**已排序**的右位点数组上用
  `bisect_left` / `bisect_right` 取窗口，只遍历窗口内的右位点 [extract_complex_queries.py:118-125]。
- 去重键为 `(seq_id, lpos, rpos, left_seq, right_seq)` [extract_complex_queries.py:140-143]。
- 复杂度：朴素两两配对为 `O(n_L * n_R)`（核对 `PAPER_OUTLINE.md` 第五节第 3 项的表述）；
  经上述二分剪枝后为 `O(n_L log n_R + P)`，`P` 为真正落在距离区间内的配对数，`P <= n_L * n_R`。
  即最坏情形仍是二次，但实际代价由 `gap` 区间宽度（而非位点总数）主导。

Y 锚定提取（Pattern B，`Target_xbp_Y_zbp_Target/extract_motifs.py`）：

- `Y` 在双链用 `str.find` 穷举出现位置；回文 `Y` 在同一坐标不重复计数（按 `(chrom, start, end)` 去重，
  优先保留正链）[extract_motifs.py:37-58]。
- 左右 motif 各在 `[search_start, search_end)` 内匹配，负链用反向互补，且 `side` 在负链上翻转
  [extract_motifs.py:77-115]。
- 左右距离约束**相互独立**：`max_left=L`、`max_right=R`、`min_left`、`min_right` 为四个独立参数
  [extract_motifs.py:136-137,144-145]，并校验 `min < max`（否则以退出码 1 终止）
  [extract_motifs.py:149-160]。
- 距离语义：左侧 motif 在 Y 上游时为 `y_start - motif_end`，在下游时为 `motif_start - y_end`
  [extract_motifs.py:11-12]。
- 复杂度同 Pattern A：`O(n_L log n_R + P)`，两侧区间独立意味着两次独立的窗口剪枝。

说明：`Target_xbp_Target/extract_complex_queries.py` 负责 Pattern A 的区间剪枝，
`Target_xbp_Y_zbp_Target/extract_motifs.py` 负责 Pattern B 的独立双侧剪枝；
两者都由 `shared/search/iupac.py:40`（`find_all_iupac_positions`）与
`shared/search/iupac.py:33`（`find_all_iupac_matches`）承担 IUPAC 匹配。

## 5. 与 task.md §2.4 cost_model 摘要的差异核查

结论：**未发现差异**。逐项对照如下。

| 摘要（task.md §2.4 / seed_plan_sweep.json:protocol.cost_model） | 源码 | 是否一致 |
| --- | --- | --- |
| `W(s) = sum_i max(1, L_i - k + 1) * V(k, a)` | `segmented_variant_work` = `max(1, segment_len - kmer_size + 1) * variant_count(kmer_size, m)`，逐段累加 [seed_plan.cpp:63-69,158-169] | 一致 |
| `a = M // (N_seeds - B)` | `denominator = seed_count - max_bulge; allowed = max_mismatch / denominator` [seed_plan.cpp:151-155] | 一致 |
| `V(k, a) = sum_c C(k, c) * 3**c` | `variant_count`：`sum_{changes<=max_mismatch} binomial(k, changes) * power_three(changes)` [seed_plan.cpp:105-121] | 一致 |
| `L_i`（段长） | `partition_lengths(L, s)`，余数分给前面的段 [seed_plan.cpp:54-61] | 一致 |
| `N_seeds`（段数） | `seed_count`，取值区间 `[max(1,B+1), L//k]` [seed_plan.cpp:130-132,149-150] | 一致 |

两处**表述层面**的补充（不构成差异，摘要未涵盖而已）：

1. 摘要未写出变体上限：`total_variants` 逐段累加时以 `max_variants` 饱和（默认 500000），超限的段数被跳过；
   若没有任何段数可行，则退化为整段方案并保持 `guaranteed=false` [seed_plan.cpp:158-172,190-199；tools/seed_plan_sweep.py:49]。
2. 摘要未写出择优规则：在可行方案中按 `(W(s), s)` 字典序取最小 [seed_plan.cpp:180-187]。

另记：`--seed-len` 被解析后忽略，实际有效种子长度即索引 k
（`seed_plan.cpp:126`；`docs/seed_plan_sweep.json` 的 `protocol.seed_len_policy` 原文同义）。

