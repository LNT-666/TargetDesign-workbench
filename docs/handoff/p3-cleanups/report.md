# 交付报告：p3-cleanups

- round: 1
- status: ready_for_review
- updated: 2026-09-16 13:22
- 交付：会话 B（servant）；核验：会话 A（master）

## 0. 环境与前提核对

- 权威环境：ms01（`hostname`=ms01，`nproc`=256），`/home/apool/songji/programfile/.venv/bin/python` = Python 3.12.3，`PATH` 含 `/opt/bin`（blastn / makeblastdb 可用；§5.3 的 BLAST 用例确实跑了 blastn）。
- `R:\songji\programfile` 与服务器 `/home/apool/songji/programfile` 是同一份文件（共享盘镜像）：改动写在本机路径后，直接在服务器上 `grep` 复核已生效（§5.0）。下面所有命令都在 ms01 上执行。
- 基线 `backup/p3_cleanups_20260916_131402/`（5 文件）：只读引用，未重建、未修改；§4 的 diff 以它为对照。

## 1. 三项完成情况

- **P1-1 完成**：`preflight_library()` 在 `try` 内调用 `validate_engine()`，命中 `ValueError` 时 `return [str(exc)], []`。探针四种输入无一抛异常（§6）；10 个合法输入与基线逐字一致（§7）。
- **P1-2 完成**：补回 `matrix["gggenome"]["unknown_gap_type"] == True`（紧接原有 `blast` 断言），并新增独立用例 `test_mismatch_only_engine_rejects_bulge_via_a_stub_backend`，用 `mock.patch.dict(..., clear=False)` 可逆注册 stub，覆盖此前零覆盖的 mismatch-only 守卫。
- **P2-1 完成**：`main.py` 工作区映射键 `combo_library_engine` → `combo_library_search`（真实控件 `main.py:734`），字典其余 12 个键的名称与顺序、`_workspace_mapping()` 返回结构均未动；新增 Tk-free 用例锁定。

## 2. 改动清单（文件 + 行号，含改前 / 改后各一行）

| 文件 | 行（改后） | 改前 | 改后 | 任务项 |
| --- | --- | --- | --- | --- |
| `shared/design/library_preflight.py` | 81-84 | `    requested_engine = validate_engine(engine)` | `    try:`<br>`        requested_engine = validate_engine(engine)`<br>`    except ValueError as exc:`<br>`        return [str(exc)], []` | P1-1 |
| `tests/test_library_preflight.py` | 85-89 | `    def test_invalid_engine_raises(self):`<br>`        with self.assertRaises(ValueError):`<br>`            preflight_library("bad-engine")` | `    def test_invalid_engine_is_reported_as_an_error(self):`<br>`        errors, warnings = preflight_library("bad-engine")`<br>`        self.assertTrue(any("Unknown off-target engine" in item`<br>`                            for item in errors))`<br>`        self.assertFalse(warnings)` | P1-1 |
| `tests/test_library_preflight.py` | 91-96 | （无） | `    def test_removed_engine_is_reported_as_an_error(self):`<br>`        for name in ("bowtie2", "casoffinder"):`<br>`            with self.subTest(engine=name):`<br>`                errors, warnings = preflight_library(name)`<br>`                self.assertTrue(any("was removed" in item for item in errors))`<br>`                self.assertFalse(warnings)` | P1-1 |
| `tests/test_offtarget_backend.py` | 18-28 | `from search.offtarget_backend import (  # noqa: E402`<br>`    PYTHON_FALLBACK_ENV, BlastBackend,`<br>`    ExactBackend, GGGenomeBackend, PythonFallbackDeclined,`<br>`    ...`<br>`    resolve_python_fallback_policy, run_backend,`<br>`)`<br>（无模块本身导入） | 同一 import 元组补入 `OffTargetBackend`、`validate_search_params`（按字母序归位），其后新增：<br>`import search.offtarget_backend as offtarget_backend  # noqa: E402` | P1-2 |
| `tests/test_offtarget_backend.py` | 171 | （无） | `        self.assertEqual(matrix["gggenome"]["unknown_gap_type"], True)` | P1-2 (a) |
| `tests/test_offtarget_backend.py` | 213-229 | （无） | 新增 `test_mismatch_only_engine_rejects_bulge_via_a_stub_backend`：`StubBackend(OffTargetBackend)`（`name="stub_none"`，能力沿用基类 `indels="none"`）+ `mock.patch.dict(offtarget_backend.BACKENDS, {"stub_none": StubBackend}, clear=False)`，`with` 块内断言 `validate_search_params("stub_none", SearchParams(max_bulge=1))` 抛 `SearchParameterError`，块外断言 `"stub_none" not in offtarget_backend.BACKENDS` | P1-2 (b) |
| `main.py` | 575 | `            "combo_library_engine": "engine",` | `            "combo_library_search": "engine",` | P2-1 |
| `tests/test_gui_common.py` | 82-108 | （无） | 新增 `class MainAppWorkspaceMappingTests` + `test_library_engine_key_matches_the_real_widget`（`MainApp.__new__(MainApp)`，假 `combo_library_search` / `combo_library_memory_mode`，断言 ① mapping 含 `combo_library_search -> "engine"` 且不含旧键 `combo_library_engine`；② `MainApp.collect_workspace(app, mapping)["engine"] == "blast"`） | P2-1 |

改动文件共 5 个，与基线快照同集合；未新增/删除文件。

## 3. P2-1 行为变化与兼容性（必填）

- **行为变化（改前 → 改后）**：改前映射键 `combo_library_engine` 在 `MainApp` 实例上不存在。`shared/gui/gui_common.py:150-152`（`apply_workspace`）与 `:166-168`（`collect_workspace`）都用 `getattr(self, attr, None)`，取不到就 `continue`，所以引擎一栏**既不写入工作区文件、也不在加载工作区时回填，而且完全静默**。改后键名指向真实控件 `main.py:734` 的 `self.combo_library_search`：**保存方向立即生效**——`_save_workspace_fields()`（`gui_common.py:131-136`）会把 `engine` 写进 `workspace.json`，下次 `apply_workspace()` 会据此回填。
- **兼容性 1（旧工作区）**：`combo_library_search` 的候选是 `LEGACY_ENGINE_CHOICES = ["exact", "indexed", "blast", "auto"]`（`main.py:18` 导入，`main.py:735` 使用），历史上从不含已下线的 bowtie2 / casoffinder，因此**任何旧工作区都不可能出现触发“已下线/非法引擎”报错路径的值**。
- **兼容性 2（改前写出的工作区文件）**：文件里从来没有 `engine` 键，`apply_workspace` 对 `None`/`""` 直接 `continue`（`gui_common.py:148-149`），与改前行为一致，不会清空控件。
- **兼容性 3（改后写出的工作区文件被旧版本读）**：只是多出一个 `engine` 键，旧版本忽略未知键，不会报错。
- **兼容性 4（非 GUI 链路）**：该键只在 `MainApp` 内使用；`_build_library_command` 直接从控件取值（`main.py:1042`），与工作区映射解耦。webapp / unified_gui / library_pipeline 都不经过 `MainApp`，不受影响。
- **恢复方向的既有先例**：`gui_common.apply_workspace` 对 `ttk.Combobox` 会走 `delete()/insert()` 分支（Combobox 两者都有，不会落到 `.set()` 回退）。`combo_library_search` 是 `state="readonly"`（`main.py:734-737`），与它同类型、且**早已在映射表内**的 `combo_library_on_target`（`main.py:799-806`）和 `combo_library_off_target`（`main.py:813-820`）走的是同一条代码路径。即本次改动让引擎键与这两个长期有效的键完全同构。ms01 无 Xvfb（`which xvfb-run Xvfb` 无输出），readonly 状态下程序化 `insert` 的最终可见性无法在 headless 下确认，已列入 §10。

## 4. 与基线快照的逐文件 diff

对照 `backup/p3_cleanups_20260916_131402/`（`difflib.unified_diff`，`n=2`）。

```diff
======================================================================
## main.py
--- baseline/main.py
+++ current/main.py
@@ -573,5 +573,5 @@
             "entry_library_index": "index_path",
             "entry_library_blastdb": "library_blastdb",
-            "combo_library_engine": "engine",
+            "combo_library_search": "engine",
             "combo_library_on_target": "on_target_model",
             "combo_library_off_target": "off_target_model",

======================================================================
## shared/design/library_preflight.py
--- baseline/shared/design/library_preflight.py
+++ current/shared/design/library_preflight.py
@@ -79,5 +79,8 @@
     warnings = []
 
-    requested_engine = validate_engine(engine)
+    try:
+        requested_engine = validate_engine(engine)
+    except ValueError as exc:
+        return [str(exc)], []
     search_params = search_params or SearchParams(max_bulge=0)
     genome_bytes = None

======================================================================
## tests/test_gui_common.py
--- baseline/tests/test_gui_common.py
+++ current/tests/test_gui_common.py
@@ -80,4 +80,33 @@
 
 
+class MainAppWorkspaceMappingTests(unittest.TestCase):
+    """The legacy GUI mapping must name the widgets that really exist."""
+
+    def test_library_engine_key_matches_the_real_widget(self):
+        from main import MainApp
+
+        class FakeVar:
+            def __init__(self, value=""):
+                self.value = value
+
+            def get(self):
+                return self.value
+
+            def set(self, value):
+                self.value = value
+
+        app = MainApp.__new__(MainApp)
+        app.workspace = Workspace(tempfile.gettempdir())
+        app.combo_library_search = FakeVar("blast")
+        app.combo_library_memory_mode = FakeVar("Auto (50% RAM)")
+
+        mapping = MainApp._workspace_mapping(app)
+        self.assertEqual(mapping.get("combo_library_search"), "engine")
+        self.assertNotIn("combo_library_engine", mapping)
+
+        collected = MainApp.collect_workspace(app, mapping)
+        self.assertEqual(collected.get("engine"), "blast")
+
+
 if __name__ == "__main__":
     unittest.main()

======================================================================
## tests/test_library_preflight.py
--- baseline/tests/test_library_preflight.py
+++ current/tests/test_library_preflight.py
@@ -83,7 +83,16 @@
                                 for item in warnings))
 
-    def test_invalid_engine_raises(self):
-        with self.assertRaises(ValueError):
-            preflight_library("bad-engine")
+    def test_invalid_engine_is_reported_as_an_error(self):
+        errors, warnings = preflight_library("bad-engine")
+        self.assertTrue(any("Unknown off-target engine" in item
+                            for item in errors))
+        self.assertFalse(warnings)
+
+    def test_removed_engine_is_reported_as_an_error(self):
+        for name in ("bowtie2", "casoffinder"):
+            with self.subTest(engine=name):
+                errors, warnings = preflight_library(name)
+                self.assertTrue(any("was removed" in item for item in errors))
+                self.assertFalse(warnings)
 
     @mock.patch("design.library_preflight.MAX_EXACT_GENOME_BYTES", 100)

======================================================================
## tests/test_offtarget_backend.py
--- baseline/tests/test_offtarget_backend.py
+++ current/tests/test_offtarget_backend.py
@@ -18,10 +18,13 @@
 from search.offtarget_backend import (  # noqa: E402
     PYTHON_FALLBACK_ENV, BlastBackend,
-    ExactBackend, GGGenomeBackend, PythonFallbackDeclined,
-    SearchParameterError, SearchParams, approve_python_fallback,
-    ask_python_fallback_on_stdin, auto_engine_candidates, compare_engines,
-    engine_capability_matrix, get_backend, resolve_engine,
-    resolve_python_fallback_policy, run_backend,
+    ExactBackend, GGGenomeBackend, OffTargetBackend,
+    PythonFallbackDeclined, SearchParameterError, SearchParams,
+    approve_python_fallback, ask_python_fallback_on_stdin,
+    auto_engine_candidates, compare_engines, engine_capability_matrix,
+    get_backend, resolve_engine, resolve_python_fallback_policy,
+    run_backend, validate_search_params,
 )
+
+import search.offtarget_backend as offtarget_backend  # noqa: E402
 
 
@@ -166,4 +169,5 @@
         matrix = engine_capability_matrix()
         self.assertEqual(matrix["blast"]["indels"], "basic")
+        self.assertEqual(matrix["gggenome"]["unknown_gap_type"], True)
         with mock.patch(
                 "search.offtarget_backend.native_indexed_available",
@@ -206,4 +210,22 @@
                     genome_size=201 * 1024 * 1024),
                 "indexed")
+
+    def test_mismatch_only_engine_rejects_bulge_via_a_stub_backend(self):
+        # A mismatch-only engine must refuse max_bulge>0. The base class
+        # already declares indels="none", so a stub is enough and the real
+        # engines keep their production capability declarations.
+        class StubBackend(OffTargetBackend):
+            name = "stub_none"
+            display_name = "Stub (mismatch only)"
+
+        with mock.patch.dict(
+                offtarget_backend.BACKENDS, {"stub_none": StubBackend},
+                clear=False):
+            with mock.patch.object(
+                    StubBackend, "available", return_value=(True, "")):
+                with self.assertRaises(SearchParameterError):
+                    validate_search_params(
+                        "stub_none", SearchParams(max_bulge=1))
+        self.assertNotIn("stub_none", offtarget_backend.BACKENDS)
 
     def test_auto_engine_candidates_full_matrix(self):

diff_exit=0
```

## 5. 轻量自检（命令原文 + 输出原文）

### 5.0 前置核对：改动在服务器上已生效

```text
$ grep -n "combo_library_search" main.py
575:            "combo_library_search": "engine",
734:        self.combo_library_search = ttk.Combobox(
737:        self.combo_library_search.set("exact")
738:        self.combo_library_search.grid(
1042:            "--engine", self.combo_library_search.get(),

$ grep -n -A3 "except ValueError as exc:" shared/design/library_preflight.py | head -20
83:    except ValueError as exc:
84-        return [str(exc)], []
85-    search_params = search_params or SearchParams(max_bulge=0)
86-    genome_bytes = None

$ grep -n "OffTargetBackend,\|validate_search_params" tests/test_offtarget_backend.py
20:    ExactBackend, GGGenomeBackend, OffTargetBackend,
25:    run_backend, validate_search_params,
227:                    validate_search_params(

$ grep -n "test_invalid_engine_is_reported_as_an_error\|test_removed_engine_is_reported" tests/test_library_preflight.py
85:    def test_invalid_engine_is_reported_as_an_error(self):
91:    def test_removed_engine_is_reported_as_an_error(self):

$ grep -n "MainAppWorkspaceMappingTests" tests/test_gui_common.py
82:class MainAppWorkspaceMappingTests(unittest.TestCase):
```

### 5.1 py_compile + 三模块单测

命令原文：

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

输出原文：

```text
pycompile_exit=0
unittest_exit=0
16:Ran 57 tests in 2.304s
18:OK
(no failures)
```

### 5.2 回归检查（4 模块）

命令原文：

```bash
cd /home/apool/songji/programfile
/home/apool/songji/programfile/.venv/bin/python -m unittest \
  tests.test_offtarget_backend tests.test_offtarget_hardening \
  tests.test_library_preflight tests.test_webapp > /tmp/ut_p3_reg.log 2>&1
echo "regression_exit=$?"
grep -n -E "^(Ran |OK|FAILED)" /tmp/ut_p3_reg.log
```

输出原文（基线为 `Ran 91 tests` → `OK`；本次 +2 条新用例 = 93）：

```text
regression_exit=0
22:Ran 93 tests in 5.982s
24:OK
(no failures)
```

### 5.3 逐模块 -v 输出

`tests.test_library_preflight -v`：

```text
test_full_engine_list (tests.test_library_preflight.EngineChoicesTests.test_full_engine_list) ... ok
test_validate_engine (tests.test_library_preflight.EngineChoicesTests.test_validate_engine) ... ok
test_preflight_only_fails_fast (tests.test_library_preflight.PipelinePreflightTests.test_preflight_only_fails_fast) ... ok
test_preflight_only_ok (tests.test_library_preflight.PipelinePreflightTests.test_preflight_only_ok) ... ok
test_blast_missing_db_is_error (tests.test_library_preflight.PreflightTests.test_blast_missing_db_is_error) ... ok
test_blast_without_db_is_warning (tests.test_library_preflight.PreflightTests.test_blast_without_db_is_warning) ... ok
test_indexed_missing_index_is_warning (tests.test_library_preflight.PreflightTests.test_indexed_missing_index_is_warning) ... ok
test_invalid_engine_is_reported_as_an_error (tests.test_library_preflight.PreflightTests.test_invalid_engine_is_reported_as_an_error) ... ok
test_large_genome_blocks_exact (tests.test_library_preflight.PreflightTests.test_large_genome_blocks_exact) ... ok
test_missing_genome_is_error (tests.test_library_preflight.PreflightTests.test_missing_genome_is_error) ... ok
test_model_missing_warns (tests.test_library_preflight.PreflightTests.test_model_missing_warns) ... ok
test_removed_engine_is_reported_as_an_error (tests.test_library_preflight.PreflightTests.test_removed_engine_is_reported_as_an_error) ... ok

----------------------------------------------------------------------
Ran 12 tests in 0.928s

OK
lp_exit=0
```

`tests.test_gui_common -v`：

```text
test_collect_and_apply_workspace (tests.test_gui_common.CommonGUIMixinTests.test_collect_and_apply_workspace) ... ok
test_library_engine_key_matches_the_real_widget (tests.test_gui_common.MainAppWorkspaceMappingTests.test_library_engine_key_matches_the_real_widget) ... ok
test_load_missing_file_is_empty (tests.test_gui_common.WorkspaceTests.test_load_missing_file_is_empty) ... ok
test_round_trip (tests.test_gui_common.WorkspaceTests.test_round_trip) ... ok

----------------------------------------------------------------------
Ran 4 tests in 0.116s

OK
gc_exit=0
```

`tests.test_offtarget_backend -v`（新增用例在倒数第几条，逐条 `ok`）：

```text
test_annotation_input_uses_sibling_fasta (tests.test_offtarget_backend.BackendTests.test_annotation_input_uses_sibling_fasta) ... Annotation file given; using matching genome FASTA: /tmp/tmplz153ymb/GCF_example_genomic.fna
ok
test_auto_and_large_indexed_apply_mismatch_only_defaults (tests.test_offtarget_backend.BackendTests.test_auto_and_large_indexed_apply_mismatch_only_defaults) ... ok
test_auto_engine_candidates_full_matrix (tests.test_offtarget_backend.BackendTests.test_auto_engine_candidates_full_matrix) ... ok
test_auto_engine_candidates_with_an_explicit_resource (tests.test_offtarget_backend.BackendTests.test_auto_engine_candidates_with_an_explicit_resource) ... ok
test_auto_engine_candidates_without_a_genome_size (tests.test_offtarget_backend.BackendTests.test_auto_engine_candidates_without_a_genome_size) ... ok
test_blast_backend_reports_chunk_progress (tests.test_offtarget_backend.BackendTests.test_blast_backend_reports_chunk_progress) ... ok
test_compare_engines_recall (tests.test_offtarget_backend.BackendTests.test_compare_engines_recall) ... ok
test_engine_capability_matrix_and_preflight_rejection (tests.test_offtarget_backend.BackendTests.test_engine_capability_matrix_and_preflight_rejection) ... ok
test_exact_backend_unified_hits (tests.test_offtarget_backend.BackendTests.test_exact_backend_unified_hits) ... ok
test_find_existing_blastdb (tests.test_offtarget_backend.BackendTests.test_find_existing_blastdb) ... ok
test_indexed_backend_applies_large_genome_default_directly (tests.test_offtarget_backend.BackendTests.test_indexed_backend_applies_large_genome_default_directly) ... ok
test_indexed_backend_auto_reduces_k_for_bulge_search (tests.test_offtarget_backend.BackendTests.test_indexed_backend_auto_reduces_k_for_bulge_search) ... ok
test_mismatch_only_engine_rejects_bulge_via_a_stub_backend (tests.test_offtarget_backend.BackendTests.test_mismatch_only_engine_rejects_bulge_via_a_stub_backend) ... ok
test_missing_external_tools_report_clear_errors (tests.test_offtarget_backend.BackendTests.test_missing_external_tools_report_clear_errors) ... ok
test_missing_or_stale_blastdb_manifest_is_not_reused (tests.test_offtarget_backend.BackendTests.test_missing_or_stale_blastdb_manifest_is_not_reused) ... ok
test_single_engine_publishes_its_report_through_params (tests.test_offtarget_backend.BackendTests.test_single_engine_publishes_its_report_through_params) ... ok
test_single_engine_without_a_report_stores_nothing (tests.test_offtarget_backend.BackendTests.test_single_engine_without_a_report_stores_nothing) ... ok
test_stale_manifest_triggers_automatic_rebuild (tests.test_offtarget_backend.BackendTests.test_stale_manifest_triggers_automatic_rebuild) ... Building genome database: /tmp/tmpr5nyl9gv/genome.blastdb ...
Database built.
Genome database /tmp/tmpr5nyl9gv/genome.blastdb already exists, skipping.
Genome database /tmp/tmpr5nyl9gv/genome.blastdb is stale (FASTA changed or manifest does not match); rebuilding.
Building genome database: /tmp/tmpr5nyl9gv/genome.blastdb ...
Database built.
ok
test_unknown_engine (tests.test_offtarget_backend.BackendTests.test_unknown_engine) ... ok
test_pam_ok_expands_iupac_pattern (tests.test_offtarget_backend.BlastPamTests.test_pam_ok_expands_iupac_pattern) ... ok
test_queries_embed_pam (tests.test_offtarget_backend.BlastPamTests.test_queries_embed_pam) ... ok
test_blastn_command_uses_threads (tests.test_offtarget_backend.BlastThreadTests.test_blastn_command_uses_threads) ... Running blastn ...
blastn complete, 0 valid matches.
ok
test_blastn_gapped_mode_and_alignment_parsing (tests.test_offtarget_backend.BlastThreadTests.test_blastn_gapped_mode_and_alignment_parsing) ... Running blastn ...
blastn complete, 2 valid matches.
ok
test_blastn_rejects_partial_query_hits (tests.test_offtarget_backend.BlastThreadTests.test_blastn_rejects_partial_query_hits) ... Running blastn ...
blastn complete, 1 valid matches.
ok
test_filters_mismatch_separately_from_indel_budget (tests.test_offtarget_backend.GGGGenomeTests.test_filters_mismatch_separately_from_indel_budget) ... ok
test_parse_tsv (tests.test_offtarget_backend.GGGGenomeTests.test_parse_tsv) ... ok
test_search_prepends_pam_for_5prime (tests.test_offtarget_backend.GGGGenomeTests.test_search_prepends_pam_for_5prime) ... ok
test_search_uses_api (tests.test_offtarget_backend.GGGGenomeTests.test_search_uses_api) ... ok
test_allow_and_deny_policies (tests.test_offtarget_backend.PythonFallbackApprovalTests.test_allow_and_deny_policies) ... ok
test_ask_policy_uses_the_registered_callback (tests.test_offtarget_backend.PythonFallbackApprovalTests.test_ask_policy_uses_the_registered_callback) ... ok
test_ask_policy_without_callback_uses_stdin_protocol (tests.test_offtarget_backend.PythonFallbackApprovalTests.test_ask_policy_without_callback_uses_stdin_protocol) ... ok
test_environment_sets_the_policy (tests.test_offtarget_backend.PythonFallbackApprovalTests.test_environment_sets_the_policy) ... ok
test_explicit_param_wins_over_environment (tests.test_offtarget_backend.PythonFallbackApprovalTests.test_explicit_param_wins_over_environment) ... ok
test_indexed_search_refuses_a_declined_python_fallback (tests.test_offtarget_backend.PythonFallbackApprovalTests.test_indexed_search_refuses_a_declined_python_fallback) ... ok
test_indexed_search_runs_python_when_approved (tests.test_offtarget_backend.PythonFallbackApprovalTests.test_indexed_search_runs_python_when_approved) ... ok
test_policy_defaults_to_allow (tests.test_offtarget_backend.PythonFallbackApprovalTests.test_policy_defaults_to_allow) ... ok
test_stdin_protocol_defaults_to_refusal (tests.test_offtarget_backend.PythonFallbackApprovalTests.test_stdin_protocol_defaults_to_refusal) ... ok
test_stdin_protocol_emits_marker_and_honours_the_answer (tests.test_offtarget_backend.PythonFallbackApprovalTests.test_stdin_protocol_emits_marker_and_honours_the_answer) ... ok
test_unknown_policy_falls_back_to_allow (tests.test_offtarget_backend.PythonFallbackApprovalTests.test_unknown_policy_falls_back_to_allow) ... ok
test_from_args (tests.test_offtarget_backend.SearchParamsTests.test_from_args) ... ok
test_zero_mismatch_is_preserved (tests.test_offtarget_backend.SearchParamsTests.test_zero_mismatch_is_preserved) ... ok

----------------------------------------------------------------------
Ran 41 tests in 1.495s

OK
ob_exit=0
```

## 6. 探针输出

命令原文：

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

输出原文（下面是落盘后的 UTF-8 原文；同一段文字经 SSH 回显到 Windows 终端时中文会被显示成乱码，那只是显示问题，故 §7 另给 ASCII 安全形式）：

```text
preflight_library('bowtie2'    ) -> (['Off-target engine bowtie2 was removed; choose from exact, indexed, blast, gggenome, auto'], [])
preflight_library('casoffinder') -> (['Off-target engine casoffinder was removed; choose from exact, indexed, blast, gggenome, auto'], [])
preflight_library('bad-engine' ) -> (['Unknown off-target engine: bad-engine (choose from exact, indexed, blast, gggenome, auto)'], [])
preflight_library('auto'       ) -> ([], ['未指定索引前缀，出库时会按 FASTA 名在输出目录自动构建索引'])
validate_engine('bowtie2'    ) -> ValueError: Off-target engine bowtie2 was removed; choose from exact, indexed, blast, gggenome, auto
validate_engine('bad-engine' ) -> ValueError: Unknown off-target engine: bad-engine (choose from exact, indexed, blast, gggenome, auto)
BACKENDS            : ['blast', 'exact', 'gggenome', 'indexed']
probe_exit=0
```

## 7. 基线等价性比对：10 个合法输入，基线模块 vs 当前模块

做法：用 `importlib` 从 `backup/p3_cleanups_20260916_131402/shared/design/library_preflight.py` 加载基线模块，与当前模块跑同一批输入，逐例比较返回值 / 异常。

输出原文：

```text
exact      vs baseline: IDENTICAL
indexed    vs baseline: IDENTICAL
blast      vs baseline: IDENTICAL
gggenome   vs baseline: IDENTICAL
auto       vs baseline: IDENTICAL
INDEXED    vs baseline: IDENTICAL
exact      vs baseline: IDENTICAL
indexed    vs baseline: IDENTICAL
exact      vs baseline: IDENTICAL
auto       vs baseline: IDENTICAL
ALL_SAME = True
ascii-safe auto: [[], ["\u672a\u6307\u5b9a\u7d22\u5f15\u524d\u7f00\uff0c\u51fa\u5e93\u65f6\u4f1a\u6309 FASTA \u540d\u5728\u8f93\u51fa\u76ee\u5f55\u81ea\u52a8\u6784\u5efa\u7d22\u5f15"]]
ascii-safe bowtie2: [["Off-target engine bowtie2 was removed; choose from exact, indexed, blast, gggenome, auto"], []]
cmp_exit=0
```

## 8. 未做项及原因

三项必做项**全部完成**，无未做项。以下按规格明确"不做"的项，列出以免误解：

- 未重新引入 bowtie2 / casoffinder；未改 `ENGINE_CHOICES` / `REMOVED_ENGINES` / `BACKENDS` 内容（探针里 `BACKENDS` 仍是 4 项：blast / exact / gggenome / indexed）。
- 未改 `validate_search_params` 的 `max_bulge > 0 and not supports_bulges()` 守卫（`shared/search/offtarget_backend.py:1031-1037`）、`EngineCapabilities.supports_bulges()`（`:267-268`）、`OffTargetBackend` 基类 `indels="none"`（`:318-323`）—— P1-2 只补覆盖，没删守卫。
- 未改 `validate_engine` 自身的抛错行为；`tests/test_library_preflight.py:28-31` 的 `test_validate_engine` 原样保留（仍要求抛 `ValueError`）。
- 未改 `webapp/**`（`app.py:508-516` 的 `except ValueError`、`job_store.py:138` 保持现状）。
- 未改 `unified_gui.py` / `library_pipeline.py` / `designer_workbench.py`。
- 未改 `shared/gui/gui_common.py` 的 `apply_workspace` / `collect_workspace` 语义，也没把 mapping 改成动态反射。
- 未做"全量核对其它映射键"（决策项推荐不做）：那需要 `tk.Tk()`，headless 跑不了。
- 未跑全量套件（`run_tests.py`）：servant 的检验上限是聚焦单测，全量归 master。
- 未动 `backup/**`；`docs/handoff/p3-cleanups/` 下只写了本文件与 `state.json`。
- 未新增第三方依赖，未新增需要 `tk.Tk()` 的用例（新用例用 `MainApp.__new__(MainApp)` + 假控件，与 `tests/test_memory_limit.py:198-200` 同法）。

## 9. 附带发现（只记录，未修）

1. `webapp/app.py:508-516` 的 `except ValueError` 在 P1-1 之后已成"死分支"——引擎名非法时 `preflight_library` 不再抛，而是返回 `errors`，于是走到其后的 `if errors:` 分支。对外行为逐字不变（同一段文案、同样 400）。C4 要求保留，未动。
2. `unified_gui.py:679-691` 没有 try/except：P1-1 之后，非法/已下线引擎名从"未捕获 traceback"变成走 `if errors:` 的 messagebox 报错，属改善。该处 `combo_engine` 是 `state="readonly"` + `values=ENGINE_CHOICES`（`unified_gui.py:384-386`），UI 上选不到已下线名，与 task.md §2 的暴露面结论一致。
3. `shared/design/library_pipeline.py:342` 也调用 `preflight_library`，但其入参 engine 已经过 `resolve_engine()`；非法名更早在 `resolve_engine` / `get_backend` 抛错（`shared/search/offtarget_backend.py:1162-1171` 对已下线名同样抛带 "was removed" 的 `ValueError`）。因此本项改动**不改变**该 CLI 的行为。
4. `tests/test_gui_common.py` 现在会 `from main import MainApp`，而 `main.py:29` 顶层有 `os.chdir(os.path.dirname(os.path.abspath(__file__)))`——导入该模块会把进程 CWD 切到仓库根目录。这是既有惯例（`tests/test_memory_limit.py:198` 早已如此），本模块 4 条用例与 4 模块回归全部通过；`WorkspaceTests` 用的是绝对临时路径，未受影响。
5. `shared/design/library_preflight.py` 的模块 docstring 与 `preflight_library` docstring 本就承诺 "(errors, warnings)"；P1-1 是让实现与文档一致，未改文档。

## 10. 待明确

1. **readonly Combobox 的"恢复"方向**（唯一不敢断言的点）：`gui_common.apply_workspace` 对 `ttk.Combobox` 走 `delete() + insert()`，而 `combo_library_search` 是 `state="readonly"`（`main.py:734-737`）。ms01 无 Xvfb（`which xvfb-run Xvfb` 无输出），无法在 headless 下确认 readonly 状态下程序化 `insert` 是否真的落到控件可见值上。可依赖的证据只有：同一条代码路径已在服务 `combo_library_on_target` / `combo_library_off_target`（同为 readonly Combobox，`main.py:799-806` / `813-820`）。**保存方向（写入工作区文件）已确定修复**；"恢复方向是否需要一次带显示的人工冒烟"请 master 定。
2. 新增的 `import search.offtarget_backend as offtarget_backend  # noqa: E402` 是否符合仓库既有的 import 排序 / `noqa` 习惯（我按 `:18-25` 既有 `# noqa: E402` 风格处理）。若仓库有 linter 约定，请 master 指正。

核验归 master；本报告不自行裁定"通过"。
