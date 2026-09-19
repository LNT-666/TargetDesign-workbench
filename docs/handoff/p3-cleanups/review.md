# 核验报告：p3-cleanups

- round: 1
- verdict: pass_with_followups
- updated: 2026-09-16 13:31
- 依据：`report.md`（round 1）+ `backup/p3_cleanups_20260916_131402/`（5 文件基线）+ master 独立复跑
  （ms01 `/home/apool/songji/programfile/.venv/bin/python`，Python 3.12.3；本机 Windows 真实 Tk 冒烟）

## 逐条核验

| 任务项 | 结论 | 证据 |
| --- | --- | --- |
| P1-1 | 通过 | 自建 difflib 基线 diff：`shared/design/library_preflight.py` 仅一处 hunk（`:81-84` try/except → `return [str(exc)], []`）；ms01 探针 8 个输入无一 RAISED：`'bowtie2'/'casoffinder'/'bad-engine'/'bad engine'/''` → `([<原文>], [])`，`'auto'/'AUTO'` → `([], [<既有中文 warn>])`，`'exact'` → `([], [])`；`validate_engine('bowtie2')` 的抛错原文与 `preflight_library('bowtie2')[0][0]` 逐字相等（True）；`Ran 12 tests / OK` |
| P1-2 | 通过 | 基线 diff：import 元组补 `OffTargetBackend, validate_search_params` + 新增 `import search.offtarget_backend as offtarget_backend  # noqa: E402`；`:171` 新增 gggenome 断言；`:210-229` 新增独立 stub 用例（`patch.dict(..., clear=False)` + 块外 `assertNotIn`）；`tests.test_offtarget_backend -v` → `Ran 41 / OK`，新用例逐条 `ok`；变异检验见下 |
| P2-1 | 规格项通过；行为描述需修正（F1/F2） | 基线 diff：`main.py:575` 仅键名一处变化，其余 12 键名称与顺序、返回结构未动；静态审计 13/13 键都有对应 `self.<attr>`（`combo_library_search` 4 处）；新增 `tests/test_gui_common.py:82-108` 用例 `ok`；保存方向实测生效、恢复方向失效（详见 F1） |

## master 独立验证

- 代码比对（本机，非转述）：自建 `difflib.unified_diff(baseline, current, n=2)`，5 个文件、5 个 hunk，与 `report.md` §4 的贴文逐字同形；无任何规格外 hunk。
- 写入面核查（mtime 扫描，排除 `backup/`、`docs/handoff/`、`__pycache__`）：本轮只有这 5 个文件被改（13:17:28–13:17:48）；`README.md` / `docs/*.md`（12:48）属上一任务，`scy-test/rDNA/*`（13:20–13:26，含 12.5 GB 索引与结果表）是数据产物、非源码，不影响契约。
- ms01 复跑（命令与输出原文见下）：`py_compile` 5 文件 `exit=0`；聚焦 3 模块 `Ran 57 tests / OK`；4 模块回归 `Ran 93 tests / OK`（基线 91 + 本次新增 2 条，与预期完全一致）；4 条新用例在 `-v` 日志中均存在且 `ok`。
- 基线等价性（我自己写的探针，`importlib` 加载 `backup/.../library_preflight.py` 为独立模块名）：6 引擎 × {genome=None, 临时小 FASTA} × {params=None, `SearchParams(max_bulge=1)`} = **24/24 IDENTICAL**（`preflight_library` 返回值与异常逐例相同）→ C3 成立。
- 变异检验 1（P1-2 的守卫是否真被覆盖）：把 `EngineCapabilities.supports_bulges` 临时置为 `lambda self: True`（不动源码），新用例立刻 `FAIL: SearchParameterError not raised`；未变异时 `OK`。→ 该用例确实绑定那条守卫，不是空覆盖。
- 变异检验 2（P1-1 的新断言是否真绑定修复）：把基线 `library_preflight.py` 以 `design.library_preflight` 之名载入后再导入测试模块，`test_invalid_engine_is_reported_as_an_error` 与 `test_removed_engine_is_reported_as_an_error` 双双 ERROR（基线 `:81` 抛 `ValueError`），当前代码下则 `ok`。→ 新断言是真回归测试。
- C6(a) 等价性：`backup/drop_bowtie2_casoffinder_20260916_095125/shared/search/offtarget_backend.py` 里原 `Bowtie2Backend.capabilities` 与当前 `GGGenomeBackend.capabilities` 逐字相同（`substitutions=True, indels="basic", unknown_gap_type=True, pam_sides=("3prime","5prime")`）→ 平移成立。
- 守卫独立复现（不依赖 servant 代码）：基类 `capabilities` 为 `indels='none'` 的临时 stub 注册后，`validate_search_params("stub_none", max_bulge=0)` 不抛，`max_bulge=1/2` 抛 `SearchParameterError: ... does not support max_bulge=N; set max_bulge=0 or choose an engine with basic indel support`；块后 `'stub_none' not in BACKENDS` 且 `BACKENDS` 仍为 `['blast','exact','gggenome','indexed']` → C8 未被触碰，注册可逆。
- 逐模块复跑（我自己跑的 5 个模块，`-v` 日志落盘后再 grep）：`tests.test_library_preflight` `Ran 12 / OK`、`tests.test_offtarget_backend` `Ran 41 / OK`、`tests.test_gui_common` `Ran 4 / OK`、`tests.test_offtarget_hardening` `Ran 26 / OK`、`tests.test_webapp` `Ran 14 / OK`（12+41+4=57 与聚焦合计一致；41+26+12+14=93 与回归合计一致）。
- 关键命令与输出：

```text
$ python -m unittest tests.test_library_preflight tests.test_offtarget_backend tests.test_gui_common   # ms01
Ran 57 tests in 2.441s / OK   (focused_exit=0)

$ python -m unittest tests.test_offtarget_backend tests.test_offtarget_hardening tests.test_library_preflight tests.test_webapp
Ran 93 tests in 5.909s / OK   (regression_exit=0; 基线 91)

$ python /tmp/mut_guard2.py          # supports_bulges 置 True 的变异检验
UNMUTATED_ok=True
FAIL: test_mismatch_only_engine_rejects_bulge_via_a_stub_backend ... AssertionError: SearchParameterError not raised
MUTATED_ok=False expected_False

$ python /tmp/probe_master.py        # 基线等价性 + 守卫复现
identical=24/24  ALL_SAME=True
max_bulge=0 -> no raise ; max_bulge=1 -> SearchParameterError: ... does not support max_bulge=1 ...
reversible: True | BACKENDS: ['blast', 'exact', 'gggenome', 'indexed']
```

## 归属判定（既有失败 vs 本次引入）

- 本轮**没有**任何新增失败：4 模块回归 `OK`，无 `ERROR:` / `FAIL:`。
- F1（readonly Combobox 恢复失效）判为**既有缺陷**，依据三条：① `shared/gui/gui_common.py` 不在本轮改动集内（mtime 未变）；② 同一路径上的 `combo_library_on_target`（`main.py:805`）/`combo_library_off_target`（`:819`）在基线里就已是活键；③ 缺陷成因是 `state="readonly"` + `delete/insert`（与本次键名无关）。
- `report.md` §9 的 4 条"附带发现"抽查复核：`webapp/app.py:508-516` 在 P1-1 之后确为死分支（无害，C4 要求保留）；`unified_gui.py:679-691` 的改善判断成立；`library_pipeline.py:342` 入参已过 `resolve_engine`，行为不变；`from main import MainApp` 触发 `main.py:29` 的 `os.chdir` 属既有惯例。以上均无需动作。

## 新发现

- `shared/gui/gui_common.py:143-155`（`apply_workspace`）— **P3**：对 `state="readonly"` 的 `ttk.Combobox`，`delete(0, tk.END)` / `insert(0, str(value))` 是静默空操作，而 `except AttributeError` 分支（`target.set(...)`）永远不会命中，于是三个 Combobox 键都恢复不了：`combo_library_search`（`main.py:736`，本轮刚被"点亮"）、`combo_library_on_target`（`:805`）、`combo_library_off_target`（`:819`）。真实 Tk 探针（本机，`Python 3.13 + Tk 8.6` 与 `Python 3.14 + Tk 9.0` 两次结果一致）：

```text
[readonly] after set('exact') get()='exact'
[readonly] delete(0,END) -> ok, get()='exact'      # 空操作
[readonly] insert(0,'blast') -> ok, get()='exact'  # 空操作
[readonly] after set('indexed') get()='indexed'    # .set() 生效
[normal]   delete/insert -> get()='blast'          # 仅 normal 态可用
[disabled] delete/insert -> 空操作；.set() 生效
gui_common path, readonly combobox -> get()='exact'  (expected 'indexed')
```

  同文件内已有正确写法可对照：`main.py:610` 对 `combo_library_memory_mode` 用的是 `combo.set(label)`，所以内存模式能正常回填。影响面：保存方向正常（引擎会被持久化），加载后控件停在上次默认值、且不报错，用户需手动重选。ms01 无 Xvfb/`DISPLAY`（`which Xvfb`、`which xvfb-run` 皆无输出），headless 无法跑真实 Tk 用例，故只能在 Windows 侧验证（已做）。
- `report.md` §3/§10.1 的表述 — **P3（文档）**：§3 写"下次 `apply_workspace()` 会据此回填"偏乐观，按 F1 应改为"保存方向已修复；恢复方向受既有 `gui_common` 缺陷阻塞"。servant 已在 §10.1 主动标注不确定并要求 master 定夺，故只作结论修正，不要求重写本轮报告。
- `tests/test_offtarget_backend.py:224-225`（`mock.patch.object(StubBackend, "available", ...)`）— **P3（干净度）**：`validate_search_params` 不查 `available`（`shared/search/offtarget_backend.py:1019-1042`），该 patch 对断言无作用，无害但冗余。
- 无其它失效映射键：13/13 键都能在仓库里找到对应的 `self.<attr>`，`_workspace_mapping` 未留第二个"死键"。

## 下一步

- 结论：**通过**（3 项规格全部达成、无回归、证据可复现），附加 F1~F3 三条可选后续。
- 推荐（可选后续 1，需用户拍板是否开 round 2，新 task-slug 建议 `gui-combobox-restore`）：修 `shared/gui/gui_common.py:143-155`，最小改法：

```python
        if isinstance(target, ttk.Combobox):
            target.set(str(value))
            continue
        try:
            target.delete(0, tk.END)
            target.insert(0, str(value))
        except AttributeError:
            ...
```

  `ttk` 已在 `gui_common.py:16` 导入；三种 state 下 `.set()` 都经真机验证有效，故对 `normal` 态也安全。测试要求：Tk-free 假控件（`delete`/`insert` 空操作、`set()` 生效）断言 `apply_workspace` 后值生效，覆盖 `combo_library_search` / `on_target` / `off_target` 三键；真实 Tk 冒烟只在有显示器的 Windows 上做（ms01 headless）。注意该文件属本任务"不要改"清单，故必须另开一轮并明确授权。
- 可选后续 2：不动代码，把 F1 作为已知问题记录（用户手动重选即可，功能不瘫痪）。
- 可选后续 3（低价值）：清掉 F3 的冗余 patch 与 F2 的两处表述，可并入 round 2 顺手做。
