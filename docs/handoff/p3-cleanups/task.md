# 任务：drop-bowtie2-casoffinder 的三条 P3 收尾（返回契约 / 测试覆盖 / 失效映射）

- task-slug: `p3-cleanups`
- round: 1
- master: 会话 A（master）
- servant: 会话 B（servant）
- repo: `R:\songji\programfile`（镜像服务器 `/home/apool/songji/programfile`）
- 权威运行环境：ms01 服务器 `/home/apool/songji/programfile/.venv/bin/python`（Python 3.12.3），`PATH` 需含 `/opt/bin`
- 本地环境：`python` = Python 3.14.7（无 numpy/biopython，且**没有** blastn/makeblastdb）
- 基线快照（master 已建，servant 直接引用，不要重建/修改）：`backup/p3_cleanups_20260916_131402/`
  - 内容：`main.py`、`shared/design/library_preflight.py`、`tests/test_gui_common.py`、`tests/test_library_preflight.py`、`tests/test_offtarget_backend.py`
- 前置任务（已完成、已核验，属背景）：`docs/handoff/drop-bowtie2-casoffinder/`（bowtie2 与 casoffinder 两个脱靶搜索引擎已下线）

## 0. 目标与边界

来源：上一任务 `drop-bowtie2-casoffinder` 的 `review.md`「最终结论 → 记录不修（P3）」与「可选的后续」，用户于 2026-09-16 说"整理吧"。

要做到（三项，互相独立，可分开做完再一起交）：

1. **P1-1**：把 `preflight_library()` 的返回契约补严 —— 引擎名非法时返回 `(errors, [])`，不再抛异常（现状是抛 `ValueError`）。
2. **P1-2**：把上一任务删掉的**两处能力断言覆盖**补回来（用仍然存在的等价引擎 + 一个临时 stub backend）。
3. **P2-1**：修正 `main.py` 工作区映射里一个长期失效的键名，让 legacy GUI 的引擎真正被保存/恢复。

不在范围内（不要做）：

- 不重新引入 bowtie2 / casoffinder；不改 `ENGINE_CHOICES` / `REMOVED_ENGINES` / `BACKENDS` 的内容。
- 不改 crispAI 链路（`shared/scoring/**`、`tools/build_crispai_env.sh`、`tools/score_crispai.py`、`requirements*.txt`、`external_tools/**`）。
- 不改 `validate_search_params` 的守卫逻辑，不改 `EngineCapabilities` 或 `supports_bulges()`。
- 不改 `webapp/**`（该层已优雅处理，见 §2）。
- 不动 `backup/**`、`docs/handoff/**`（除本任务的 `report.md` 与 `state.json`）。
- 不引入任何需要 Tk root（`tk.Tk()`）的新测试 —— ms01 是 headless，跑不了。

## 1. 规则 / 契约（唯一权威版本，servant 不需要也不允许重新调研）

```text
C1  preflight_library（shared/design/library_preflight.py:69）不得因引擎名非法而抛异常：
    把 :81 的 validate_engine(engine) 包进 try/except ValueError，命中时
    return [str(exc)], []（errors 承载消息、warnings 为空）并立即返回。
    这正是该函数 docstring（:72-77）承诺的 "Return (errors, warnings)" 契约。
C2  报错文案不改：直接复用 validate_engine / REMOVED_ENGINES 抛出的原文
    （已下线名 -> "Off-target engine <name> was removed; choose from ..."；
     其它非法名 -> "Unknown off-target engine: <name> (choose from ...)"）。
C3  preflight_library 的其余行为一律不变：errors / warnings 的其它来源、返回类型、
    以及"engine 合法时"的既有判定顺序都与改前逐字一致。
C4  不要删除或改动 webapp 侧的两处防御：webapp/app.py:508-516 的 except ValueError、
    webapp/job_store.py:138（其异常被 webapp/app.py:520-524 的 except Exception 兜住）。
    它们本来就优雅，保持现状即可。
C5  tests/test_library_preflight.py:85-87 的 test_invalid_engine_raises 必须改为
    断言"返回 errors 且不抛"（可改名为 test_invalid_engine_is_reported_as_an_error），
    因为 C1 之后它就再也不抛了。另补一条断言：preflight_library("bowtie2") 与
    preflight_library("casoffinder") 返回的 errors 里含 "was removed"。
C6  tests/test_offtarget_backend.py:165 起的
    test_engine_capability_matrix_and_preflight_rejection 恢复两处覆盖：
    (a) 把原 matrix["bowtie2"]["unknown_gap_type"] == True 平移到仍然存在、
        且 capabilities 等价的 matrix["gggenome"]["unknown_gap_type"] == True；
    (b) 用一个临时注册的 stub backend（capabilities 的 indels="none"）覆盖
        "mismatch-only 引擎拒绝 max_bulge=1" 这条守卫。
    注册方式必须可逆：mock.patch.dict(offtarget_backend.BACKENDS, {"<name>": Stub}, clear=False)，
    并在用例内断言退出后 "<name>" not in BACKENDS。
C7  main.py:575 的键名 "combo_library_engine" 改为 "combo_library_search"
    （真实控件见 main.py:734）；同一字典里其余 12 个键的名称与顺序、以及
    _workspace_mapping 的返回结构都不动。
C8  以下一律保留、不得删除或"清理"：validate_search_params 的
    "max_bulge > 0 and not supports_bulges()" 守卫（shared/search/offtarget_backend.py:1031-1037）、
    EngineCapabilities.supports_bulges()（:267-268）、OffTargetBackend 基类的
    indels="none" 默认能力（:318-323）。它们是给未来引擎用的保护。
C9  除本任务点名的文件外不得改动任何文件；不要顺手修其它既有问题。
## 2. 现状证据（master 已核实，可直接引用，不必重新调研）

### P1-1 相关

- `shared/design/library_preflight.py:78-81`：

```text
78:    errors = []
79:    warnings = []
80:
81:    requested_engine = validate_engine(engine)
```

  `validate_engine` 在 try 之外，所以它抛出的 `ValueError` 会直接穿出 `preflight_library`。
- master 在 ms01 实测（上一任务核验时）：

```text
preflight_library('bowtie2')     -> RAISED ValueError: Off-target engine bowtie2 was removed; choose from exact, indexed, blast, gggenome, auto
preflight_library('casoffinder') -> RAISED ValueError: Off-target engine casoffinder was removed; choose from exact, indexed, blast, gggenome, auto
preflight_library('auto')        -> ([], ['未指定索引前缀…'])
```

  改动前（两个引擎还在 `ENGINE_CHOICES` 里时）等价输入是**返回 errors**（"缺少 Bowtie2…"），不是抛异常。
- `validate_engine` 的全部调用点（ms01 `grep -rn validate_engine --include=*.py`，已排除 `.venv/`、`backup/`）：
  - `shared/design/library_preflight.py:38` 定义；`:81` —— 本项要保护的点
  - `webapp/job_store.py:138` —— 其异常被上层 `webapp/app.py:520-524` 的 `except Exception` 兜住，已优雅
  - `tests/test_library_preflight.py:28-31` —— `test_validate_engine`，**仍应继续抛**，不要改
  - `tests/test_library_preflight.py:85-87` —— 本项要改的断言
- 唯一未加保护的 GUI 调用点：`unified_gui.py:679-691`。**暴露面评估（master 结论，不要据此扩范围）**：`combo_engine` 是 `state="readonly"` + `values=ENGINE_CHOICES`（`unified_gui.py:384-386`），UI 上选不到已下线名；且 `unified_gui.py:64-67` 的 `_workspace_mapping()` 只有 `entry_output`，引擎不会被持久化。所以本项是"把契约补严"，不是线上故障。

### P1-2 相关

- `tests/test_offtarget_backend.py:165-172` 现在只剩 `matrix["blast"]["indels"] == "basic"` 和一段 `resolve_engine` 断言；被删掉的两条是 `matrix["casoffinder"]["indels"] == "none"` 与 `matrix["bowtie2"]["unknown_gap_type"] == True`。
- ms01 `grep -rn "BACKENDS" tests/` **无任何输出** → 没有任何用例注册/替换 `BACKENDS`，即 `validate_search_params` 的 mismatch-only 守卫当前**零覆盖**。
- 等价引擎：`GGGenomeBackend.capabilities`（`shared/search/offtarget_backend.py:781-786`）也是 `unknown_gap_type=True`，可平移 (a)。
- 基类默认：`OffTargetBackend.capabilities`（`shared/search/offtarget_backend.py:318-323`）本身就是 `indels="none", unknown_gap_type=False`，stub 直接继承基类即可满足 (b)。

### P2-1 相关

- `main.py:575`：`"combo_library_engine": "engine"`；真实控件是 `main.py:734` 的 `self.combo_library_search`（`values=LEGACY_ENGINE_CHOICES`）。
- `shared/gui/gui_common.py:144-160`（`apply_workspace`）与 `:162-176`（`collect_workspace`）都用 `getattr(self, attr, None)`，取不到就 `continue` → 引擎当前**既不保存也不恢复**，且不报错（静默失效）。
- `main.py:18`、`:735` 用的是 `LEGACY_ENGINE_CHOICES` = `exact/indexed/blast/auto`，历史上从不含 bowtie2 / casoffinder。
- 既有 Tk-free 测试写法可参照（都是 `MainApp.__new__(MainApp)` + 手工挂属性）：`tests/test_memory_limit.py:198-200`、`tests/test_fasta_gz.py:135-137`、`tests/test_gff_gz.py:62-64`。

### 环境提醒

- 本仓库没有 git 历史，基线一律用 `backup/` 快照；读写含中文的文件必须显式 UTF-8（`PYTHONUTF8=1`、`PYTHONIOENCODING=utf-8`、`Get-Content -Encoding UTF8`）。
- 共享盘 I/O 慢：命令要聚焦，避免全仓扫描。

## 3. 必做改动

- [ ] P1-1 `preflight_library()` 不再因引擎名非法而抛异常
  - 位置：`shared/design/library_preflight.py:81`
  - 期望行为：C1 + C2 + C3。建议写法（保持缩进与风格一致）：

```python
    try:
        requested_engine = validate_engine(engine)
    except ValueError as exc:
        return [str(exc)], []
```

  - 证据要求：贴一段 `python` 探针的输出，覆盖四种输入：`"bowtie2"`、`"casoffinder"`、`"bad-engine"`、`"auto"`；前三个必须返回 `(['…'], [])` 形态（不抛），`"auto"` 必须与改前一致。另贴 `python -m unittest tests.test_library_preflight -v` 的完整输出。

- [ ] P1-2 恢复两处能力断言覆盖
  - 位置：`tests/test_offtarget_backend.py:165`（`test_engine_capability_matrix_and_preflight_rejection`）
  - 期望行为：C6。
    - (a) 新增 `self.assertEqual(matrix["gggenome"]["unknown_gap_type"], True)`。
    - (b) 新增一条独立用例（不要塞进上面那个用例，便于定位），例如
      `test_mismatch_only_engine_rejects_bulge_via_a_stub_backend`：定义一个继承 `OffTargetBackend` 的 stub（`name = "stub_none"`，`capabilities` 沿用基类默认即可），用
      `mock.patch.dict(offtarget_backend.BACKENDS, {"stub_none": Stub}, clear=False)` 临时注册，
      断言 `validate_search_params("stub_none", SearchParams(max_bulge=1))` 抛 `SearchParameterError`；
      并在 `with` 块之后断言 `"stub_none" not in offtarget_backend.BACKENDS`（证明可逆）。
      需要时可用 `mock.patch.object(Stub, "available", return_value=(True, ""))`。
    - import 注意：该文件顶部（`:18-25`）用的是 `from search.offtarget_backend import (...)`，目前**没有**导入模块本身，也没有导入 `OffTargetBackend` / `validate_search_params`。请把 `OffTargetBackend`、`validate_search_params` 加进那个已有的 import 元组，并给模块本身加一行 `import search.offtarget_backend as offtarget_backend`（放在 `:25` 之后、`GUIDE = ...` 之前）；或者改用字符串形式的 `mock.patch.dict("search.offtarget_backend.BACKENDS", ...)`。不要新增第三方依赖。
  - 证据要求：`python -m unittest tests.test_offtarget_backend -v` 的完整输出（含新增用例逐条 `ok`）。

- [ ] P2-1 修正工作区映射里失效的引擎键
  - 位置：`main.py:575`
  - 期望行为：C7 —— 键名改为 `"combo_library_search"`，字典其余键与顺序、以及 `_workspace_mapping()` 的结构都不动。
  - 行为变化（必须写进 `report.md` 的显眼处）：改后 legacy GUI 会开始把引擎写入工作区并在加载时回填；因为该 GUI 的列表是 `LEGACY_ENGINE_CHOICES`（从不含已下线引擎），旧工作区不可能触发 C9/退役报错路径。
  - 新增测试：在 `tests/test_gui_common.py` 追加一条 Tk-free 用例：
    用 `MainApp.__new__(MainApp)` 构造（沿用 `tests/test_memory_limit.py:198-200` 的写法），手工挂一个假的 `combo_library_search`（用该文件里已有的 `FakeVar` 风格），
    断言 ① `MainApp._workspace_mapping(app)` 含 `combo_library_search -> "engine"`；② 用该 mapping 调 `collect_workspace` 时返回值里出现 `engine` 且值等于假控件的值。
    不要引入需要 `tk.Tk()` 的新用例；也不要新增 `import tkinter` 之外的依赖。
  - 证据要求：`python -m unittest tests.test_gui_common -v` 的完整输出。
## 4. 不要做的事

- 不要重新引入 bowtie2 / casoffinder；不要改 `ENGINE_CHOICES`、`REMOVED_ENGINES`、`BACKENDS` 的内容。
- 不要改 `validate_search_params` 的守卫（`shared/search/offtarget_backend.py:1031-1037`）、`EngineCapabilities.supports_bulges()`（`:267-268`）、`OffTargetBackend` 基类的 `indels="none"`（`:318-323`）。P1-2 只是补测试覆盖，不是删守卫。
- 不要改 `validate_engine` 自身的抛错行为 —— `tests/test_library_preflight.py:28-31` 的 `test_validate_engine` 仍要求它对非法名字抛 `ValueError`。只在 `preflight_library` 的边界上接住它。
- 不要改 `webapp/**`（`app.py:508-516` 的 `except ValueError`、`job_store.py:138` 都保持现状）。
- 不要改 `unified_gui.py`、`library_pipeline.py`、`designer_workbench.py`。
- 不要改 `shared/gui/gui_common.py` 的 `apply_workspace` / `collect_workspace` 语义；不要为了"顺手"把 mapping 改成动态反射。
- 不要动 `backup/**`、`docs/handoff/**`（除本任务的 `report.md` 与 `state.json`）。
- 不要引入需要 `tk.Tk()` 的新测试；不要新增第三方依赖。
- 不要顺手修其它既有问题（发现就写进 `report.md` 的「附带发现」）。

## 5. 决策项（未确认则按推荐执行）

- P1-1 的返回形态 → 推荐 `return [str(exc)], []`（消息放进 errors、warnings 留空），与 docstring 的 "(errors, warnings)" 契约一致。备选是把非法引擎名当成 warning 后继续跑，但那会让后续代码拿到一个不存在的引擎，**不采用**。
- P1-1 是否把已下线名回落到 `auto` → **不采用**。保持显式报错（上一任务 C9 已定），静默换引擎会让用户失去结果可追溯性。
- P1-2 的 (b) 是否改成"给 gggenome 造一个假 capabilities" → 推荐用独立 stub backend。理由：改真实引擎的能力声明会污染生产语义，而 stub 只在该用例内可逆注册。
- P2-1 是否顺手核对其它映射键 → 推荐**不做**。本次只修这一个已知失效键；"每个映射键都必须存在"的全量守卫需要 `tk.Tk()`，headless 下跑不了。
- `report.md` 是否要贴基线 diff → 推荐贴每个改动文件的 `文件:行` + 改前/改后各一行，不需要整段 diff。

## 6. 轻量自检（servant 的检验上限，不要跑全量套件）

权威环境（ms01）：

```bash
cd /home/apool/songji/programfile
export PYTHONUTF8=1 PYTHONIOENCODING=utf-8 PYTHONUNBUFFERED=1
export PATH=/opt/bin:$PATH
PY=/home/apool/songji/programfile/.venv/bin/python
$PY -m py_compile main.py shared/design/library_preflight.py \
  tests/test_gui_common.py tests/test_library_preflight.py tests/test_offtarget_backend.py
echo "pycompile_exit=$?"
$PY -m unittest tests.test_library_preflight tests.test_offtarget_backend \
  tests.test_gui_common > /tmp/ut_p3.log 2>&1
echo "unittest_exit=$?"
grep -n -E "^(Ran |OK|FAILED)" /tmp/ut_p3.log
grep -n -E "^(ERROR|FAIL):" /tmp/ut_p3.log || echo "(no failures)"
```

注意：unittest 输出必须**落盘后再 grep**，不要用 `2>&1 | tail -6`。本仓库有些用例会打印大量 stdout，管道下 stdout 的块缓冲会把 stderr 的汇总行顶到前面，`tail` 会抓不到 `Ran ... / OK`（上一任务 master 就踩过这个坑）。

回归检查（证明没碰坏上一任务的成果）：

```bash
cd /home/apool/songji/programfile
/home/apool/songji/programfile/.venv/bin/python -m unittest \
  tests.test_offtarget_backend tests.test_offtarget_hardening \
  tests.test_library_preflight tests.test_webapp > /tmp/ut_p3_reg.log 2>&1
echo "regression_exit=$?"
grep -n -E "^(Ran |OK|FAILED)" /tmp/ut_p3_reg.log
```

基线对照（master 已测）：这 4 个模块改前是 `Ran 91 tests in 7.321s` → `OK`。改动会新增用例/断言，所以总数应比 91 多；只要 `OK` 且无 `ERROR:` / `FAIL:` 即可。

探针（贴进 report）：

```bash
cat > /tmp/probe_p3.py <<'PY'
import sys
sys.path.insert(0, "/home/apool/songji/programfile/shared")
from design.library_preflight import preflight_library, validate_engine
from search.offtarget_backend import BACKENDS
for name in ("bowtie2", "casoffinder", "bad-engine", "auto"):
    try:
        print("preflight_library(%-13r) -> %r" % (name, preflight_library(name)))
    except Exception as exc:
        print("preflight_library(%-13r) -> RAISED %s: %s"
              % (name, type(exc).__name__, exc))
for name in ("bowtie2", "bad-engine"):
    try:
        validate_engine(name)
        print("validate_engine(%r) -> no raise (UNEXPECTED)" % name)
    except ValueError as exc:
        print("validate_engine(%-13r) -> ValueError: %s" % (name, exc))
print("BACKENDS            :", sorted(BACKENDS))
PY
/home/apool/songji/programfile/.venv/bin/python /tmp/probe_p3.py
```

预期：四条 `preflight_library` 全部返回 `(errors, warnings)` 形态、无一 RAISED；`validate_engine` 对两个非法名仍抛；`BACKENDS` 仍是 4 项。

若确实连不上服务器，就用本机 `python` 跑同样命令，并在 report 里写明跑在哪台机器上。本机没有 blastn/makeblastdb，部分用例可能因此失败 —— 遇到这种失败先在 ms01 复跑确认，按「既有环境性失败」记录，**不要改代码去迁就**。

## 7. 交付要求

- 改前快照：master 已建 `backup/p3_cleanups_20260916_131402/`（5 个文件，保持相对路径）。直接引用，不要重建、不要修改。
- 完成后：把 `state.json` 置 `ready_for_review`（并更新 `updated`），写 `report.md`。
- `report.md` 必填：改动文件+行号表格（含改前/改后各一行）、命令原文与输出原文、未做项及原因、附带发现（只记录不修）、待明确项。
- 特别要在 `report.md` 里显式写出 P2-1 的**行为变化**（引擎从此会被持久化）与兼容性评估。
- 不要自己裁定"通过"；核验归 master。