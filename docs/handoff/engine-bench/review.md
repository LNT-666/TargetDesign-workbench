# 核验 / 处置报告：engine-bench（master 接管）

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

## 5. 遗留项结清（2026-09-19 14:43）

本任务接管时留下的两项（`docs/SEED_PLAN_ANALYSIS.md` 与 `--determinism` 实跑证据）已作为
`docs/handoff/manuscript-v1/task.md` 的 P0-1 交付并通过核验：

- `docs/SEED_PLAN_ANALYSIS.md`：220 行，四节齐备；§2 的 16 行网格表与 `docs/seed_plan_sweep.json` 逐值一致（master 比对 0 处不符）。
- 确定性证据：master 亲自重跑 `python tools\seed_plan_sweep.py --determinism`，四个线程数 hits=36 且 sha256 全等
  `0549c426662a2fa2994b8696971c51366f330456ed7392adaa58d7be62cbf499`。
- round 1 核验发现的 `SEED_PLAN_ANALYSIS.md:128` 命中数口径错误（66 vs 67）已于 manuscript-v1 round 2 修正并通过复核。

至此本任务无未结项；`tools/seed_plan_sweep.py` 与 `docs/seed_plan_sweep.json` 维持只读冻结。
