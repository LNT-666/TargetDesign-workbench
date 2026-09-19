# 交付报告：drop-bowtie2-casoffinder

- round: 1
- status: ready_for_review（servant 已完工；是否通过由 master 裁定）
- updated: 2026-09-16 12:56
- servant: 会话 B（servant）
- 权威环境：ms01 `/home/apool/songji/programfile/.venv/bin/python`（Python 3.12.3，`PATH` 含 `/opt/bin`）
- 基线快照：`backup/drop_bowtie2_casoffinder_20260916_095125/`（只读引用，未重建、未修改）

## 0. 本轮（round 1 收尾）完成内容

上一轮中断在 P0-6 文档、ms01 权威自检、报告补全三件事。本轮完成这三件，**代码与测试未再改动**：

1. **P0-6 文档**：`README.md`、`docs/OFFTARGET_ENGINES.md`、`docs/GUI.md`（P0）+ `docs/NATIVE_INDEXED_ENGINE_DESIGN.md`、`docs/UPGRADE_REPORT.md`（P1）按 C10 收敛引擎清单/能力表/`auto` 顺序；crispAI 段落一律保留。
2. **ms01 权威自检**：§6 三条命令 + crispAI `preflight()` + 引擎探针 + 「round 1 补充」A1/A2 审计（原文见 §2）。
3. **收尾**：本文件补全为正式交付报告；`state.json` 置 `ready_for_review` 并更新时间戳。

## 1. 改动清单（文件 + 行号）

### 1.1 本轮：P0-6 文档（行号均为改后行号；删除项标注原行号）

| 文件 | 行号 | 改了什么 |
| --- | --- | --- |
| `README.md` | 原 156-157 删除 | 「脱靶搜索引擎」表删掉 `bowtie2` / `casoffinder` 两行，剩 exact / indexed / blast / gggenome / auto |
| `README.md` | 190 | `blast → indexed → bowtie2` 改为 `blast → indexed` |
| `docs/OFFTARGET_ENGINES.md` | 原 34-35 删除 | 「实现」表删两行 |
| `docs/OFFTARGET_ENGINES.md` | 原 49-50 删除 | 「能力矩阵」表删两行，剩 exact / indexed / blast / gggenome |
| `docs/OFFTARGET_ENGINES.md` | 原 57-58 删除 | 删「`casoffinder` 声明为 mismatch-only…」段 |
| `docs/OFFTARGET_ENGINES.md` | 57 | `bowtie2` / `gggenome` 的 unknown gap 说明收为只讲 `gggenome` |
| `docs/OFFTARGET_ENGINES.md` | 原 64 删除 | 删「`auto` 存在 bulge 约束时不选 `casoffinder`」（已无此引擎） |
| `docs/OFFTARGET_ENGINES.md` | 87-90 | 重写「不超过 `MAX_EXACT_GENOME_BYTES`」分支，对齐 C3：native 可用 indexed→blast→exact；native 不可用 bulge=0 blast→indexed→exact、bulge=1 blast→exact→indexed |
| `docs/OFFTARGET_ENGINES.md` | 91-92 | 重写「超过 `MAX_EXACT_GENOME_BYTES`」分支为 blast→indexed（bulge 开关不改变顺序） |
| `docs/OFFTARGET_ENGINES.md` | 150 | `blast → indexed → bowtie2` 改为 `blast → indexed` |
| `docs/OFFTARGET_ENGINES.md` | 原 186-188 删除 | 「约束处理」删 Cas-OFFinder mismatch-only 与 Bowtie2 解析 SAM 两条 |
| `docs/GUI.md` | 38 | 脱靶引擎清单 → exact、indexed、blast、gggenome、auto |
| `docs/GUI.md` | 114 | 两步脱靶搜索的引擎清单 → exact / indexed / blast / gggenome / auto |
| `docs/GUI.md` | 144 | 「Library 出库」可用引擎 → exact / indexed / blast / gggenome |
| `docs/GUI.md` | 154 | 出库设置对话框引擎清单 → exact / indexed / blast / gggenome / auto |
| `docs/NATIVE_INDEXED_ENGINE_DESIGN.md` | 38 | out-of-scope 项 `Replacing blast, bowtie2, casoffinder, or gggenome.` → `Replacing blast or gggenome.` |
| `docs/UPGRADE_REPORT.md` | 3（新增） | 标题下加一行退役说明；正文一字未改（§5 决策项：历史报告保持可追溯） |

有意保留的引擎名出现处（C10/§4）：`README.md:143`（crispAI 依赖 Cas-OFFinder）、
`docs/CRISPAI.md`（6 处）、`docs/SCORING_GUIDE.md`（2 处）、`docs/UPGRADE_REPORT.md:3`（本轮新增的退役说明）与 `:50`（历史正文）。

### 1.2 上一轮：代码与测试（本轮未改动；master 已在 `review.md` 逐条核验通过）

| 文件 | 行（改后） | 改了什么 | 任务项 |
| --- | --- | --- | --- |
| `shared/search/offtarget_backend.py` | 原 488-777 整段删除（现 487 起为 `GGGenomeBackend`） | 删除 `Bowtie2Backend`、`CasOFFinderBackend` 两个类 | P0-1 |
| `shared/search/offtarget_backend.py` | 180-188 | `default_engine_threads()` 只读 `SEARCH_NUM_THREADS`，回落值 `max(1, min(cpu,32))` 不变 | P0-2/C5 |
| `shared/search/offtarget_backend.py` | 1052-1060 | `apply_engine_defaults()` 删除 `elif key == "casoffinder"` 分支；docstring 删掉 “Cas-OFFinder is mismatch-only.” 半句 | P0-2/C4 |
| `shared/search/offtarget_backend.py` | 1095-1112 | `auto_engine_candidates()` 候选表按 C3 收敛；因删名而重复的 bulge 分支已合并 | P0-2/C3 |
| `shared/search/offtarget_backend.py` | 1150-1155 | `BACKENDS` 删两行，保留 exact/blast/gggenome/indexed 及顺序 | P0-2/C2 |
| `shared/search/offtarget_backend.py` | 1157-1159 | 新增 `REMOVED_ENGINES`（供已下线引擎报错用） | P1-1/C9 |
| `shared/search/offtarget_backend.py` | 1162-1171 | `get_backend()`：已下线名字抛含 “was removed” + 可用引擎列表的 ValueError；其它未知名字走原路径 | P1-1/C9 |
| `shared/design/library_preflight.py` | 23、25-26 | `ENGINE_CHOICES` 收敛为 5 项；新增 `REMOVED_ENGINES`；`LEGACY_ENGINE_CHOICES`(29) 未动 | P0-3/C6 |
| `shared/design/library_preflight.py` | 38-47 | `validate_engine()`：已下线名字抛含 “was removed” + 可用引擎列表的 ValueError | P1-1/C9 |
| `basic/blast.py` | 137-139 | `--engine choices` 删去两个名字 | P0-4/C7 |
| `Target_xbp_Target/analyze_complex_scores.py` | 156-158 | 同上 | P0-4/C7 |
| `Target_xbp_Y_zbp_Target/blast_combined.py` | 161-163 | 同上（单引号写法） | P0-4/C7 |
| `webapp/index.html` | 59-65 | `<select id="engine">` 删除两个 `<option>`（`webapp/app.py` 未动） | P0-4/C8 |
| `tests/test_offtarget_backend.py` | 19 | import 去掉 `Bowtie2Backend, CasOFFinderBackend` | P0-5 |
| `tests/test_offtarget_backend.py` | 原 168-175 删除 | 删 casoffinder/bowtie2 能力断言与依赖 `CasOFFinderBackend.available` 的 `SearchParameterError` 断言 | P0-5 |
| `tests/test_offtarget_backend.py` | 209-221 | `test_auto_engine_candidates_full_matrix` 8 组期望改为 C3 新表 | P0-5 |
| `tests/test_offtarget_backend.py` | 408 | `(BlastBackend(), Bowtie2Backend(), CasOFFinderBackend())` → `(BlastBackend(),)` | P0-5 |
| `tests/test_offtarget_backend.py` | 原 663-728 删除 | 删除 `Bowtie2ThreadTests`、`CasOFFinderTests` 两个测试类 | P0-5 |
| `tests/test_offtarget_hardening.py` | 598 | 引擎名元组 → `("exact", "blast", "indexed")` | P0-5 |
| `tests/test_offtarget_hardening.py` | 624-641、643-652 | 四条 auto 链期望值改为新顺序 | P0-5 |
| `tests/test_library_preflight.py` | 23-25 | `ENGINE_CHOICES` 断言 → 新 5 项列表 | P0-5 |
| `tests/test_webapp.py` | 185 | 引擎元组删两个名字 | P0-5 |
| `tools/benchmark_all_engines.py` | 原 280-319 删除 | 删除 `benchmark_bowtie2` 整个函数（保留 `benchmark_simple` 给 exact） | P1-2 |
| `tools/benchmark_all_engines.py` | 296 | `--engines` 默认 → `"exact,indexed,native-indexed,blast"` | P1-2 |
| `tools/benchmark_all_engines.py` | 305 | 删除 `BOWTIE2_NUM_THREADS` 的 `setdefault` | P1-2 |
| `tools/benchmark_all_engines.py` | 原 375-384 删除 | 删除 `bowtie2` / `casoffinder` 两个运行分支 | P1-2 |
| `shared/design/library_pipeline.py` | 249 | help 文本 → `"blastn/native threads (default: auto up to 32)"` | P2-1 |
## 2. ms01 命令原文与输出原文

全部命令在 `/home/apool/songji/programfile` 下用 `/home/apool/songji/programfile/.venv/bin/python` 执行（Python 3.12.3）。

### 2.1 §6 第一条：py_compile

```bash
cd /home/apool/songji/programfile
/home/apool/songji/programfile/.venv/bin/python -m py_compile \
  shared/search/offtarget_backend.py shared/design/library_preflight.py \
  shared/design/library_pipeline.py tools/benchmark_all_engines.py \
  basic/blast.py Target_xbp_Target/analyze_complex_scores.py \
  Target_xbp_Y_zbp_Target/blast_combined.py \
  tests/test_offtarget_backend.py tests/test_offtarget_hardening.py \
  tests/test_library_preflight.py tests/test_webapp.py
```

```text
py_compile exit=0
```

### 2.2 §6 第二条：unittest（4 模块）

```bash
/home/apool/songji/programfile/.venv/bin/python -m unittest \
  tests.test_offtarget_backend tests.test_offtarget_hardening \
  tests.test_library_preflight tests.test_webapp -v
```

```text
Ran 91 tests in 6.453s

OK
unittest exit=0
```

`-v` 的完整输出（stdout/stderr 合并；部分用例自身的打印与用例名交错，共 110 行）：

```text
test_annotation_input_uses_sibling_fasta (tests.test_offtarget_backend.BackendTests.test_annotation_input_uses_sibling_fasta) ... Annotation file given; using matching genome FASTA: /tmp/tmppq9rz3_9/GCF_example_genomic.fna
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
test_missing_external_tools_report_clear_errors (tests.test_offtarget_backend.BackendTests.test_missing_external_tools_report_clear_errors) ... ok
test_missing_or_stale_blastdb_manifest_is_not_reused (tests.test_offtarget_backend.BackendTests.test_missing_or_stale_blastdb_manifest_is_not_reused) ... ok
test_single_engine_publishes_its_report_through_params (tests.test_offtarget_backend.BackendTests.test_single_engine_publishes_its_report_through_params) ... ok
test_single_engine_without_a_report_stores_nothing (tests.test_offtarget_backend.BackendTests.test_single_engine_without_a_report_stores_nothing) ... ok
test_stale_manifest_triggers_automatic_rebuild (tests.test_offtarget_backend.BackendTests.test_stale_manifest_triggers_automatic_rebuild) ... Building genome database: /tmp/tmpx1l92yks/genome.blastdb ...
Database built.
Genome database /tmp/tmpx1l92yks/genome.blastdb already exists, skipping.
Genome database /tmp/tmpx1l92yks/genome.blastdb is stale (FASTA changed or manifest does not match); rebuilding.
Building genome database: /tmp/tmpx1l92yks/genome.blastdb ...
Database built.
ok
test_unknown_engine (tests.test_offtarget_backend.BackendTests.test_unknown_engine) ... ok
test_pam_ok_expands_iupac_pattern (tests.test_offtarget_backend.BlastPamTests.test_pam_ok_expands_iupac_pattern) ... ok
test_queries_embed_pam (tests.test_offtarget_backend.BlastPamTests.test_queries_embed_pam) ... ok
test_blastn_command_uses_threads (tests.test_offtarget_backend.BlastThreadTests.test_blastn_command_uses_threads) ... ok
test_blastn_gapped_mode_and_alignment_parsing (tests.test_offtarget_backend.BlastThreadTests.test_blastn_gapped_mode_and_alignment_parsing) ... ok
test_blastn_rejects_partial_query_hits (tests.test_offtarget_backend.BlastThreadTests.test_blastn_rejects_partial_query_hits) ... ok
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
test_a_failed_engine_moves_on_to_the_next_candidate (tests.test_offtarget_hardening.AutoEngineChainTests.test_a_failed_engine_moves_on_to_the_next_candidate) ... ok
test_a_memory_limit_stops_the_chain (tests.test_offtarget_hardening.AutoEngineChainTests.test_a_memory_limit_stops_the_chain) ... ok
test_an_explicit_resource_reports_why_nothing_else_was_tried (tests.test_offtarget_hardening.AutoEngineChainTests.test_an_explicit_resource_reports_why_nothing_else_was_tried) ... ok
test_default_params_are_ranked_with_the_auto_bulge_default (tests.test_offtarget_hardening.AutoEngineChainTests.test_default_params_are_ranked_with_the_auto_bulge_default) ... ok
test_explicit_engines_do_not_enter_the_chain (tests.test_offtarget_hardening.AutoEngineChainTests.test_explicit_engines_do_not_enter_the_chain) ... ok
test_the_chain_stops_when_the_switch_is_refused (tests.test_offtarget_hardening.AutoEngineChainTests.test_the_chain_stops_when_the_switch_is_refused) ... ok
test_the_indexed_candidate_never_degrades_to_python (tests.test_offtarget_hardening.AutoEngineChainTests.test_the_indexed_candidate_never_degrades_to_python) ... ok
test_the_runtime_chain_follows_the_documented_order (tests.test_offtarget_hardening.AutoEngineChainTests.test_the_runtime_chain_follows_the_documented_order) ... ok
test_the_successful_candidate_publishes_params_extra_report (tests.test_offtarget_hardening.AutoEngineChainTests.test_the_successful_candidate_publishes_params_extra_report) ... ok
test_approved_confirmation_is_written_to_the_child (tests.test_offtarget_hardening.ConfirmHandshakeEndToEndTests.test_approved_confirmation_is_written_to_the_child) ... ok
test_declined_confirmation_reaches_the_child_as_no (tests.test_offtarget_hardening.ConfirmHandshakeEndToEndTests.test_declined_confirmation_reaches_the_child_as_no) ... ok
test_engine_entry_points_pass_a_log_callback (tests.test_offtarget_hardening.FallbackReportingTests.test_engine_entry_points_pass_a_log_callback) ... ok
test_search_indexed_prints_a_refused_fallback_reason (tests.test_offtarget_hardening.FallbackReportingTests.test_search_indexed_prints_a_refused_fallback_reason) ... ok
test_api_error_raises_instead_of_reporting_no_hits (tests.test_offtarget_hardening.GGGenomeBudgetTests.test_api_error_raises_instead_of_reporting_no_hits) ... ok
test_exact_searches_are_flagged_exact_only (tests.test_offtarget_hardening.GGGenomeBudgetTests.test_exact_searches_are_flagged_exact_only) ... ok
test_mismatch_budget_is_a_url_path_segment (tests.test_offtarget_hardening.GGGenomeBudgetTests.test_mismatch_budget_is_a_url_path_segment) ... ok
test_a_valid_index_is_reused_instead_of_rebuilt (tests.test_offtarget_hardening.IndexNamespaceTests.test_a_valid_index_is_reused_instead_of_rebuilt) ... ok
test_explicit_index_path_overrides_the_k_namespace (tests.test_offtarget_hardening.IndexNamespaceTests.test_explicit_index_path_overrides_the_k_namespace) ... ok
test_index_prefix_is_namespaced_by_k (tests.test_offtarget_hardening.IndexNamespaceTests.test_index_prefix_is_namespaced_by_k) ... ok
test_second_build_waits_for_the_first (tests.test_offtarget_hardening.IndexNamespaceTests.test_second_build_waits_for_the_first) ... ok
test_heartbeat_fires_while_an_index_build_is_silent (tests.test_offtarget_hardening.NativeStreamingTests.test_heartbeat_fires_while_an_index_build_is_silent) ... ok
test_progress_callback_runs_while_the_child_is_alive (tests.test_offtarget_hardening.NativeStreamingTests.test_progress_callback_runs_while_the_child_is_alive) ... ok
test_failing_consumer_stops_and_reaps_the_engine (tests.test_offtarget_hardening.ProcessLifetimeTests.test_failing_consumer_stops_and_reaps_the_engine) ... ok
test_indexed_backend_propagates_a_timeout (tests.test_offtarget_hardening.ProcessLifetimeTests.test_indexed_backend_propagates_a_timeout) ... ok
test_parent_death_kills_the_engine (tests.test_offtarget_hardening.ProcessLifetimeTests.test_parent_death_kills_the_engine) ... /usr/lib/python3.12/unittest/case.py:589: ResourceWarning: unclosed file <_io.TextIOWrapper name=3 encoding='UTF-8'>
  if method() is not None:
ResourceWarning: Enable tracemalloc to get the object allocation traceback
/usr/lib/python3.12/unittest/case.py:589: ResourceWarning: unclosed file <_io.TextIOWrapper name=5 encoding='UTF-8'>
  if method() is not None:
ResourceWarning: Enable tracemalloc to get the object allocation traceback
ok
test_timeout_raises_and_is_not_a_python_fallback (tests.test_offtarget_hardening.ProcessLifetimeTests.test_timeout_raises_and_is_not_a_python_fallback) ... ok
test_full_engine_list (tests.test_library_preflight.EngineChoicesTests.test_full_engine_list) ... ok
test_validate_engine (tests.test_library_preflight.EngineChoicesTests.test_validate_engine) ... ok
test_preflight_only_fails_fast (tests.test_library_preflight.PipelinePreflightTests.test_preflight_only_fails_fast) ... ok
test_preflight_only_ok (tests.test_library_preflight.PipelinePreflightTests.test_preflight_only_ok) ... ok
test_blast_missing_db_is_error (tests.test_library_preflight.PreflightTests.test_blast_missing_db_is_error) ... ok
test_blast_without_db_is_warning (tests.test_library_preflight.PreflightTests.test_blast_without_db_is_warning) ... ok
test_indexed_missing_index_is_warning (tests.test_library_preflight.PreflightTests.test_indexed_missing_index_is_warning) ... ok
test_invalid_engine_raises (tests.test_library_preflight.PreflightTests.test_invalid_engine_raises) ... ok
test_large_genome_blocks_exact (tests.test_library_preflight.PreflightTests.test_large_genome_blocks_exact) ... ok
test_missing_genome_is_error (tests.test_library_preflight.PreflightTests.test_missing_genome_is_error) ... ok
test_model_missing_warns (tests.test_library_preflight.PreflightTests.test_model_missing_warns) ... ok
test_app_imports_without_network (tests.test_webapp.AppImportTests.test_app_imports_without_network) ... ok
test_page_engine_options_match_shared_list (tests.test_webapp.AppImportTests.test_page_engine_options_match_shared_list) ... ok
test_page_has_motif_analysis_options (tests.test_webapp.AppImportTests.test_page_has_motif_analysis_options) ... ok
test_post_rejects_preflight_errors (tests.test_webapp.AppImportTests.test_post_rejects_preflight_errors) ... ok
test_basic_fasta_without_motif_uses_fasta_flag (tests.test_webapp.JobStoreTests.test_basic_fasta_without_motif_uses_fasta_flag) ... ok
test_build_command (tests.test_webapp.JobStoreTests.test_build_command) ... ok
test_candidate_rows_reads_library_scores (tests.test_webapp.JobStoreTests.test_candidate_rows_reads_library_scores) ... ok
test_create_and_status (tests.test_webapp.JobStoreTests.test_create_and_status) ... ok
test_download_whitelist (tests.test_webapp.JobStoreTests.test_download_whitelist) ... ok
test_list_jobs_order (tests.test_webapp.JobStoreTests.test_list_jobs_order) ... ok
test_motif_commands_chain_extraction_and_pipeline (tests.test_webapp.JobStoreTests.test_motif_commands_chain_extraction_and_pipeline) ... ok
test_retry_rejects_active_job (tests.test_webapp.JobStoreTests.test_retry_rejects_active_job) ... ok
test_retry_resets_status (tests.test_webapp.JobStoreTests.test_retry_resets_status) ... ok
test_yzbp_extract_includes_min_distance_flags (tests.test_webapp.JobStoreTests.test_yzbp_extract_includes_min_distance_flags) ... ok

----------------------------------------------------------------------
Ran 91 tests in 6.453s

OK
Running blastn ...
blastn complete, 0 valid matches.
Running blastn ...
blastn complete, 2 valid matches.
Running blastn ...
blastn complete, 1 valid matches.
```

### 2.3 「round 1 补充」A1：`bowtie2` 审计（实测恰好 2 行）

```bash
grep -rn -i "bowtie2" --include=*.py --include=*.html --include=*.js . \
  | grep -v -e "/backup/" -e "/.venv/" -e "/.codex_tmp/" -e "/docs/"
```

```text
./shared/design/library_preflight.py:26:REMOVED_ENGINES = ("bowtie2", "casoffinder")
./shared/search/offtarget_backend.py:1159:REMOVED_ENGINES = ("bowtie2", "casoffinder")
A1_bowtie2_lines=2
```

与 A1 预期一致：**恰好 2 行**，两行都是有意保留的退役报错字面量 `REMOVED_ENGINES`（C9/P1-1 要求）。
搜索引擎实现侧、测试侧、`webapp/index.html` 侧为零命中；`backup/`、`.venv/`、`.codex_tmp/`、`docs/` 按 A1 的过滤条件排除。

另有两条辅助证据：

```bash
grep -rn "_parse_sam\|Bowtie2Backend\|CasOFFinderBackend" tests/     # 无输出（P0-5 证据要求）
grep -n "bowtie2\|casoffinder" tools/benchmark_all_engines.py        # 无输出（P1-2 证据要求）
```

### 2.4 「round 1 补充」A2：`casoffinder` / `cas-offinder` 审计

```bash
grep -rn -i -e "casoffinder" -e "cas-offinder" --include=*.py --include=*.html --include=*.js . \
  | grep -v -e "/backup/" -e "/.venv/" -e "/.codex_tmp/" -e "/docs/" \
  | cut -d: -f1 | sort | uniq -c
```

```text
      1 ./basic/analyze_scores.py
     17 ./external_tools/crispAI-main/crispAI_score/crispAI.py
      1 ./shared/design/library_preflight.py
     15 ./shared/scoring/crispai_runtime.py
      1 ./shared/search/offtarget_backend.py
      2 ./tools/score_crispai.py
```

逐行核对（含 `.sh`，`shared/design/library_preflight.py:26` 与 `shared/search/offtarget_backend.py:1159` 之外的命中全部落在 crispAI 链路）：

```text
shared/search/offtarget_backend.py:1159:REMOVED_ENGINES = ("bowtie2", "casoffinder")
shared/design/library_preflight.py:26:REMOVED_ENGINES = ("bowtie2", "casoffinder")
external_tools/crispAI-main/crispAI_score/crispAI.py:103,108,109,116,117,118,120,121,123,126,127,129,131,132,133,134,138
shared/scoring/crispai_runtime.py:6,52,53,56,59,60,62,63,68,127,128,130,131,160,208
basic/analyze_scores.py:161:  help="CUDA device for crispAI/Cas-OFFinder (-1 = CPU)"
tools/score_crispai.py:9,48
tools/build_crispai_env.sh:51,52,55,56,57,67,69,70,73,75,76,78
```

结论：**搜索引擎侧零命中**；其余全部是 §4 明令冻结的 crispAI 链路，加同样那 2 处 `REMOVED_ENGINES`。
### 2.5 §6 证明 §4 守住：crispAI `preflight()`

```bash
cat > /tmp/ck_crispai.py <<'PY'
import sys
sys.path.insert(0, "/home/apool/songji/programfile/shared")
from scoring.crispai_runtime import preflight
e, w = preflight()
print("ERRORS:", e)
print("WARNINGS:", w)
PY
/home/apool/songji/programfile/.venv/bin/python /tmp/ck_crispai.py
```

```text
ERRORS: []
WARNINGS: ['UCSC chroms directory /home/apool/songji/programfile/external_tools/crispAI-main/crispAI_score/casoffinder/ucsc_chroms not found; genomepy may download GRCh38 on first run']
```

`ERRORS: []`，与改动前一致；warning 只剩既有的 `ucsc_chroms` 一条。

### 2.6 引擎探针（`BACKENDS` / `auto` 八组 / 退役报错 / 线程）

```bash
env -u SEARCH_NUM_THREADS -u BOWTIE2_NUM_THREADS \
  /home/apool/songji/programfile/.venv/bin/python /tmp/ck_probe.py
```

```text
sorted(BACKENDS): ['blast', 'exact', 'gggenome', 'indexed']
capability_keys: ['blast', 'exact', 'gggenome', 'indexed']
ENGINE_CHOICES: ['exact', 'indexed', 'blast', 'gggenome', 'auto']
LEGACY_ENGINE_CHOICES: ['exact', 'indexed', 'blast', 'auto']
default_engine_threads(): 32
blastdb   mb=0 -> ['blast']
indexpath mb=0 -> ['indexed']
blastdb   mb=1 -> ['blast']
indexpath mb=1 -> ['indexed']
small native=True mb=0 -> ['indexed', 'blast', 'exact']
small native=True mb=1 -> ['indexed', 'blast', 'exact']
small native=False mb=0 -> ['blast', 'indexed', 'exact']
small native=False mb=1 -> ['blast', 'exact', 'indexed']
big       mb=0 -> ['blast', 'indexed']
big       mb=1 -> ['blast', 'indexed']
get_backend('casoffinder') -> ValueError: Off-target engine casoffinder was removed; choose from blast, exact, gggenome, indexed
get_backend('bowtie2') -> ValueError: Off-target engine bowtie2 was removed; choose from blast, exact, gggenome, indexed
get_backend('typod') -> ValueError: Unknown off-target engine: typod (choose from blast, exact, gggenome, indexed)
validate_engine('bowtie2') -> ValueError: Off-target engine bowtie2 was removed; choose from exact, indexed, blast, gggenome, auto
validate_engine('casoffinder') -> ValueError: Off-target engine casoffinder was removed; choose from exact, indexed, blast, gggenome, auto
validate_engine('typod') -> ValueError: Unknown off-target engine: typod (choose from exact, indexed, blast, gggenome, auto)
validate_engine('Indexed') -> indexed
```

逐条对照 C3 结果表（八组）：

| 条件（bulge 两态都跑） | C3 要求 | 实测 |
| --- | --- | --- |
| `--blastdb` 非空 | `["blast"]` | 一致 |
| `--index-path` 非空 | `["indexed"]` | 一致 |
| `genome_size > MAX_EXACT_GENOME_BYTES` | `["blast", "indexed"]` | 一致 |
| `native_available` 为真 | `["indexed", "blast", "exact"]` | 一致 |
| 其余、bulge 开启 | `["blast", "exact", "indexed"]` | 一致 |
| 其余、bulge 关闭 | `["blast", "indexed", "exact"]` | 一致 |

C9 报错文本同时满足：含 “was removed”、列出当前可用引擎、不静默回落；`typod` 仍走原有 “Unknown off-target engine” 路径。

### 2.7 三处 CLI 的 `--engine` 行（C7 证据）

```bash
for s in basic/blast.py Target_xbp_Target/analyze_complex_scores.py Target_xbp_Y_zbp_Target/blast_combined.py; do
  echo "--- $s"
  /home/apool/songji/programfile/.venv/bin/python "$s" --help 2>&1 | grep -n -e "--engine"
done
```

```text
--- basic/blast.py
5:                [--engine {exact,indexed,blast,gggenome,auto}]
13:                [--engine-fallback {ask,allow,deny}]
37:  --engine {exact,indexed,blast,gggenome,auto}
62:  --engine-fallback {ask,allow,deny}
63:                        Cross-engine fallback policy for --engine auto;
--- Target_xbp_Target/analyze_complex_scores.py
2:                                 [--engine {exact,indexed,blast,gggenome,auto}]
67:  --engine {exact,indexed,blast,gggenome,auto}
--- Target_xbp_Y_zbp_Target/blast_combined.py
3:                         [--engine {exact,indexed,blast,gggenome,auto}]
57:  --engine {exact,indexed,blast,gggenome,auto}
```

三处都与 `ENGINE_CHOICES` 一致，且仍是字面量列表（未改成 `import ENGINE_CHOICES`）。

### 2.8 P0-6 文档 grep（P0-6 证据要求）

```bash
grep -rn -i "bowtie2" README.md docs/
```

```text
docs/UPGRADE_REPORT.md:3:> 注：bowtie2 与 casoffinder 两个脱靶搜索引擎已于 2026-09 下线，下文相关描述仅作历史记录。
docs/UPGRADE_REPORT.md:50:- 统一引擎接口：exact、BLAST、Bowtie2、Cas-OFFinder、GGGenome、
（其余命中全部位于 docs/handoff/**：本任务自己的交接件，规格明令不动、不属于交付文档）
```

| 命中 | 处理 |
| --- | --- |
| `docs/UPGRADE_REPORT.md:3` | **有意保留/新增**：本轮按 §5 决策项加的退役说明，点名两个引擎已下线 |
| `docs/UPGRADE_REPORT.md:50` | **有意保留**：历史报告正文，§5 决策项要求不改正文以保持可追溯 |
| `docs/handoff/**` | **有意保留**：本任务交接件（task/review/report/state 及既有 handoff 记录） |
| `README.md`、`docs/OFFTARGET_ENGINES.md`、`docs/GUI.md`、`docs/NATIVE_INDEXED_ENGINE_DESIGN.md` | **已删除**：本轮改动后零命中 |

```bash
grep -rn -i -e "casoffinder" -e "cas-offinder" README.md docs/
```

```text
README.md:143（crispAI 行：需要 R/NuPoP、Cas-OFFinder、GRCh38；见 docs/CRISPAI.md）
docs/CRISPAI.md:13,29,31,32,37,38,127
docs/SCORING_GUIDE.md:92,149
docs/UPGRADE_REPORT.md:3（本轮新增的退役说明）
（其余命中为 docs/handoff/**）
```

`README.md:143`、`docs/CRISPAI.md`、`docs/SCORING_GUIDE.md` 都是 crispAI 打分依赖，按 §4 原样保留；搜索引擎文档侧已清零。

### 2.9 §4 冻结证据（只读 mtime 取证）

```bash
ls -l --time-style=long-iso shared/scoring/crispai_runtime.py tools/build_crispai_env.sh \
  tools/score_crispai.py requirements.txt requirements-linux.txt requirements-windows.txt \
  basic/analyze_scores.py docs/CRISPAI.md docs/SCORING_GUIDE.md \
  external_tools/crispAI-main/crispAI_score/casoffinder/cas-offinder
```

```text
basic/analyze_scores.py                                            2026-09-13 12:24
docs/CRISPAI.md                                                    2026-09-13 18:05
docs/SCORING_GUIDE.md                                              2026-09-13 22:45
external_tools/crispAI-main/crispAI_score/casoffinder/cas-offinder -> /home/users/songji/.cache/casoffinder-env/bin/cas-offinder   2026-09-07 15:32
requirements-linux.txt                                             2026-09-07 15:33
requirements.txt                                                   2026-09-06 17:37
requirements-windows.txt                                           2026-09-07 15:33
shared/scoring/crispai_runtime.py                                  2026-09-07 14:23
tools/build_crispai_env.sh                                         2026-09-07 15:33
tools/score_crispai.py                                             2026-09-06 17:31
```

全部早于本次会话基线时刻（2026-09-16 09:51），符号链接仍指向 `~/.cache/casoffinder-env/bin/cas-offinder`：
§4 的冻结链路一个字节未动。

### 2.10 服务器二进制现状（说明为何本次下线无行为回归）

```text
which bowtie2       -> MISSING
which bowtie2-build -> MISSING
which cas-offinder  -> MISSING
which blastn        -> /opt/bin/blastn
which makeblastdb   -> /opt/bin/makeblastdb
```

两个已下线引擎在本机与 ms01 都不可用，其 `available()` 一直是 False，`auto` 本来就跳过它们。本机 Windows 同样为 MISSING。

### 2.11 本机（Windows，Python 3.14.7）跑过的自检

```powershell
cd R:\songji\programfile
python -m py_compile shared/search/offtarget_backend.py shared/design/library_preflight.py shared/design/library_pipeline.py basic/blast.py Target_xbp_Target/analyze_complex_scores.py Target_xbp_Y_zbp_Target/blast_combined.py
python -m py_compile tools/benchmark_all_engines.py tests/test_offtarget_backend.py tests/test_offtarget_hardening.py tests/test_library_preflight.py tests/test_webapp.py
python -m unittest tests.test_offtarget_backend tests.test_offtarget_hardening tests.test_library_preflight tests.test_webapp -v
```

```text
PYCOMPILE_EXIT=0
Ran 91 tests in 130.774s
FAILED (errors=1, skipped=1)

ERROR: test_auto_and_large_indexed_apply_mismatch_only_defaults
  ... SearchParameterError: auto could not find an engine compatible with max_bulge=0; choose exact or indexed explicitly
skipped: tests.test_offtarget_hardening.ProcessLifetimeTests.test_parent_death_kills_the_engine
         ('PR_SET_PDEATHSIG is Linux-only')
```

唯一 error 是**既有环境性失败**：本机无 NCBI BLAST+（`shutil.which("blastn")` / `makeblastdb` 均为 `None`），
该用例断言 `resolve_engine("auto", blastdb="existing_db") == "blast"`。用脚本对基线快照逐字比对，
`resolve_engine` 与该用例与基线完全相同；在 ms01（`/opt/bin/blastn` 可用）通过。
详细归属分析见 `review.md` 的「归属判定」。

## 3. 未做项及原因

- **无 P0/P1/P2 未做项**：P0-1 ~ P0-6、P1-1、P1-2、P2-1 全部完成。
- 刻意未做（规格明令）：不新增/替换引擎；不动 exact/indexed/blast/gggenome 的实现与能力声明；不改 `auto` 的解析/回落机制；
  不改 `LEGACY_ENGINE_CHOICES`；不动 `webapp/app.py`；不给三处 CLI 加 import；不动 `backup/**` 与 `docs/handoff/**`（本文件与 `state.json` 除外）；
  不动 crispAI 链路（§4 清单）。
- **P3-1 记录不修**（master 已在「round 1 补充」A3 裁定）：`shared/design/library_preflight.py:81` 的 `validate_engine()` 在 `try` 之外，
  故传已下线引擎名时抛 `ValueError`，而不是像改动前那样把 “缺少 Bowtie2…” 放进 `errors` 返回。
  调用点 `webapp/app.py:508-516` 有 `except ValueError`（优雅），`unified_gui.py:679-691` 没有 try。
  `tests/test_library_preflight.py:85-87` 本就断言无效引擎名要抛，属既有契约。
- **P3-2 记录不修**：`tests/test_offtarget_backend.py` 原 165-175 中「mismatch-only 引擎拒绝 `max_bulge=1`」的断言无法平移
  （剩余引擎无 `indels == "none"`：exact/indexed 为 `dna_rna`，blast/gggenome 为 `basic`），规格 P0-5 已预判并允许直接删除。

## 4. 附带发现（只记录、未修）

- `main.py:575` 的工作区映射 `"combo_library_engine": "engine"` 与真实控件名 `combo_library_search`（`main.py:734`）不一致，
  疑为长期失效映射；`main.py` 用的是 `LEGACY_ENGINE_CHOICES`，与本任务无交集。
- P3-1 / P3-2 两条（见 §3）。
- `docs/handoff/fasta-gz-prep/report.md:267` 提到的 `test_core` RSS 既有失败与本任务无关。
- 本轮所有改动集中在 5 个文档；除这些文档与 `report.md` / `state.json` 外未触碰任何文件。

## 5. 待明确项（已闭环，无遗留）

- **原「C9 与 §6 第三条 grep 冲突」**：master 已在 `task.md` 的「round 1 补充」A1 裁定 —— C9 优先，`REMOVED_ENGINES` 字面量保留，
  grep 预期改为「除这 2 处退役报错字面量外不得有其它命中」。本轮按 A1 执行，实测恰好 2 行（§2.3），A2 同口径审计通过（§2.4）。
- **无新增待明确项**：本轮不需要用户或 master 再补充决策。