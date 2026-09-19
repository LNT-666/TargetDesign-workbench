# 交付报告 — webapp-designer-port（round 1 / servant）

- 日期：2026-09-16
- servant：codex-servant（repo `R:\songji\programfile`）
- 备份快照：`backup\20260916_webapp_designer_port\`（改动前：`designer_workbench.py`、
  `webapp\app.py`、`webapp\job_store.py`、`webapp\index.html`、`tests\test_webapp.py`、
  `docs\WEBAPP.md`、`README.md`）
- 结论：P0-1 ~ P0-6 全部实现；第 6 节 5 条自检全部通过（另附 `--help` 检查）。

## 1. 改动文件与行号

| 文件 | 行数 | 说明（关键行号） |
| --- | --- | --- |
| `shared/design/workbench_form.py` | 706（新增） | P0-1：从 `designer_workbench.py` 搬出的表单层，不 import tkinter。常量 `PRESET_KEYS:33`、`MODE_LABELS:36`、`PAIR_RANK_POLICY_FIELDS:46`、`SIDE_FIELD_KEYS:69`、`DEFAULT_ON_TARGET_MODELS:60`；`coerce_bool:89`、`split_model_selection:106`、`model_display_name:120`、`to_side:130`、`side_to_pam_side:135`、`pam_side_to_side:144`、`active_side_keys:153`、`auto_memory_limit:163`；`WorkbenchFormState:173`；`resolved_memory_limit:254`、`search_timeout_s:272`、`pair_rank_policy_values:286`、`prepare_genome_fasta:303`、`resolve_side_models:322`、`build_pattern_spec:349`、`default_run_label:402`、`build_runner_config:441`、`readiness_errors:575`、`side_preset_updates:633`、`side_model_options:656`、`resolve_side_model_selection:678`、`active_side_updates:692` |
| `designer_workbench.py` | 2314 | P0-2：薄包装。新增 `_form_state:1370`、`_apply_field_updates:1395`；`_refresh_side_model_options:1409`、`_apply_side_preset:1434`、`_sync_active_side_rules:1453` 改为调用 `workbench_form.*`；`_value:1544`、`_int_value:1614`、`_bool_value:1618`、`_current_spec:1753`、`_current_config:1766`、`_readiness_errors:1881` 全部委托；`imports:18-86` 删除已下沉的重复实现。Tk 控件、进度条动画、`_on_close` 未动，方法名/签名保持原样。 |
| `webapp/app.py` | 369（重写） | P0-3：`HOST/DEFAULT_PORT:44-45`、`STATIC_WHITELIST:56`、`DOWNLOAD_WHITELIST_RE:62`、`OUTPUT_EXTENSIONS:65`、`get_manager/set_manager:73-86`、`render_index:89`、`job_route:96`、`model_action_route:107`、`Handler:118`（`_send_json:130`、`_read_json:141`、`do_GET:150`、`do_POST:196`）、`_serve_static:243`、`_api_job:256`、`_api_job_log:264`、`_api_job_candidates:277`、`_api_job_download:285`、`_api_outputs:307`、`main:337` |
| `webapp/jobs.py` | 461（新增） | `parse_progress_line:69`、`JobContext:95`、`JobManager:167`（`create_job:252`、`get_job:288`、`job_params:300`、`list_jobs:305`、`read_log:322`、`wait:333`、`cancel:345`、`mark_interrupted_jobs:370`、`_run_job:423`），`JOB_ID_RE = ^[a-z0-9-]{12}$`（`:65`） |
| `webapp/schema.py` | 376（新增） | `REGION_TYPES/ID_TYPES:40-49`、`COMMON_FIELDS/RUN_FIELDS/PATTERN_FORMS`（与 Tk 控件同源）、`designer_field_keys:231`、`designer_defaults:246`、`species_choices:263`、`model_catalog:275`、`build_schema:304` |
| `webapp/services/__init__.py` | 1（新增） | 包声明 |
| `webapp/services/designer.py` | 375（新增） | `state_from_payload:85`、`preview:119`、`preset_update:148`、`active_side_update:162`、`build_runner:176`、`require_extract_output:184`、`job_body:216`（自动应答并写 `[auto-confirm] kind|reason`）、`submit:251`、`candidates:303`、`sanitize_label:322`、`export_filename:329`、`export_rows:336` |
| `webapp/services/dataprep.py` | 516（新增） | `require_output_dir:63`、`require_file:70`、`_run_command:79`（流式进日志 + stop hook）、`prepare_genome:112`、`prepare_annotation:122`、`extract_sequences:187`、`publish_file:226`、`extract_target_fasta:240`、`extract_mask_fasta:265`、`download_body:310`、`prepare_body:344`、`extract_target_body:377`、`extract_mask_body:394`、`build_blastdb_body:419`、`build_index_body:432`、`submit_*:463-515` |
| `webapp/services/models.py` | 160（新增） | `adjust_status:51`、`deep_statuses:65`、`list_models:72`、`_check_key:98`、`download_body:107`、`delete_body:136`、`submit_download:146`、`submit_delete:155` |
| `webapp/job_store.py` | 1（作废） | 内容替换为一句说明；文件保留 |
| `webapp/index.html` | 206（重写） | 4 个页签；Designer 三栏 + 预览/进度/日志/候选表/导出；Models 面板；Results 面板（作业表、详情、输出目录） |
| `webapp/static/app.js` | 1230（新增） | 原生 JS：schema 拉取、Designer 表单/预览/预设/模型、`find`/`score` 提交与轮询、候选勾选与导出、Data prep 提交与轮询、Models、Results/Outputs |
| `webapp/static/styles.css` | 280（新增） | 样式（状态色、进度条、表格、日志 `<pre>`、响应式三栏） |
| `tests/test_workbench_form.py` | 370（新增） | P0-5：21 个用例（三种 pattern 的 spec/config、readiness 错误分支、内存/超时/PairRank 策略、预设与模型选项） |
| `tests/test_webapp.py` | 747（重写） | P0-5：56 个用例（JobManager、进度行解析、schema、designer/dataprep/models 服务、HTTP 路由；全部 mock，无子进程、无浏览器） |
| `docs/WEBAPP.md` | 107（重写） | 启动、四个页签、作业模型、API 表、安全边界、与桌面端一致性说明 |
| `README.md` | 288 | 仅第 30 行表格行改为 `本地 Web UI：Data prep / Models / Designer / Results`；第 97 行命令未改 |

`unified_gui.py`、`main.py`、`shared/design/pattern_runner.py`、`pattern_spec.py`、
`system_presets.py`、`shared/search|scoring|output|data|utils/*` 均未改动。

## 2. 第 6 节自检命令原文与输出

### 2.1 语法检查

```powershell
python -m py_compile webapp\app.py webapp\jobs.py webapp\schema.py `
  webapp\services\designer.py webapp\services\dataprep.py webapp\services\models.py `
  shared\design\workbench_form.py designer_workbench.py `
  tests\test_workbench_form.py tests\test_webapp.py
```

输出：无（`py_compile` 成功时不打印内容），`$LASTEXITCODE = 0`。

### 2.2 聚焦单测（mock，无真实子进程、无浏览器）

```powershell
python -m unittest tests.test_webapp tests.test_workbench_form -v
```

```text
test_bodies_are_lazy_callables (tests.test_webapp.DataPrepServiceTests.test_bodies_are_lazy_callables) ... ok
test_publish_file_copies_into_the_job_out_dir (tests.test_webapp.DataPrepServiceTests.test_publish_file_copies_into_the_job_out_dir) ... ok
test_require_output_dir_and_file (tests.test_webapp.DataPrepServiceTests.test_require_output_dir_and_file) ... ok
test_submit_build_index_needs_a_destination (tests.test_webapp.DataPrepServiceTests.test_submit_build_index_needs_a_destination) ... ok
test_submit_download_requires_species_and_output (tests.test_webapp.DataPrepServiceTests.test_submit_download_requires_species_and_output) ... ok
test_submit_extract_mask_needs_a_mask_identifier (tests.test_webapp.DataPrepServiceTests.test_submit_extract_mask_needs_a_mask_identifier) ... ok
test_submit_prepare_queues_a_dataprep_job (tests.test_webapp.DataPrepServiceTests.test_submit_prepare_queues_a_dataprep_job) ... ok
test_submit_prepare_validates_before_queueing (tests.test_webapp.DataPrepServiceTests.test_submit_prepare_validates_before_queueing) ... ok
test_build_runner_matches_the_shared_form_layer (tests.test_webapp.DesignerServiceTests.test_build_runner_matches_the_shared_form_layer) ... ok
test_candidates_hide_internal_columns (tests.test_webapp.DesignerServiceTests.test_candidates_hide_internal_columns) ... ok
test_export_rows_validates_format_and_selection (tests.test_webapp.DesignerServiceTests.test_export_rows_validates_format_and_selection) ... ok
test_export_rows_writes_into_the_job_export_dir (tests.test_webapp.DesignerServiceTests.test_export_rows_writes_into_the_job_export_dir) ... ok
test_job_body_honours_the_no_confirm_policy (tests.test_webapp.DesignerServiceTests.test_job_body_honours_the_no_confirm_policy) ... ok
test_job_body_wires_the_runner_and_auto_confirms (tests.test_webapp.DesignerServiceTests.test_job_body_wires_the_runner_and_auto_confirms) ... ok
test_preset_and_active_side_updates (tests.test_webapp.DesignerServiceTests.test_preset_and_active_side_updates) ... ok
test_preview_describes_a_valid_pattern (tests.test_webapp.DesignerServiceTests.test_preview_describes_a_valid_pattern) ... ok
test_preview_reports_missing_inputs (tests.test_webapp.DesignerServiceTests.test_preview_reports_missing_inputs) ... ok
test_sanitize_label_and_export_filename (tests.test_webapp.DesignerServiceTests.test_sanitize_label_and_export_filename) ... ok
test_submit_find_queues_one_job (tests.test_webapp.DesignerServiceTests.test_submit_find_queues_one_job) ... ok
test_submit_rejects_bad_stage_and_bad_policy (tests.test_webapp.DesignerServiceTests.test_submit_rejects_bad_stage_and_bad_policy) ... ok
test_submit_rejects_incomplete_forms (tests.test_webapp.DesignerServiceTests.test_submit_rejects_incomplete_forms) ... ok
test_submit_score_requires_find_targets_output (tests.test_webapp.DesignerServiceTests.test_submit_score_requires_find_targets_output) ... ok
test_index_page_has_the_four_tabs (tests.test_webapp.HandlerRouteTests.test_index_page_has_the_four_tabs) ... ok
test_job_download_whitelist_and_traversal (tests.test_webapp.HandlerRouteTests.test_job_download_whitelist_and_traversal) ... ok
test_jobs_and_job_detail_routes (tests.test_webapp.HandlerRouteTests.test_jobs_and_job_detail_routes) ... ok
test_outputs_route (tests.test_webapp.HandlerRouteTests.test_outputs_route) ... ok
test_post_dataprep_routes_validate_before_queueing (tests.test_webapp.HandlerRouteTests.test_post_dataprep_routes_validate_before_queueing) ... ok
test_post_designer_jobs_reports_validation_errors (tests.test_webapp.HandlerRouteTests.test_post_designer_jobs_reports_validation_errors) ... ok
test_post_designer_jobs_uses_the_shared_manager (tests.test_webapp.HandlerRouteTests.test_post_designer_jobs_uses_the_shared_manager) ... ok
test_post_designer_preview_forwards_the_payload (tests.test_webapp.HandlerRouteTests.test_post_designer_preview_forwards_the_payload) ... ok
test_post_job_cancel_and_export (tests.test_webapp.HandlerRouteTests.test_post_job_cancel_and_export) ... ok
test_post_models_routes (tests.test_webapp.HandlerRouteTests.test_post_models_routes) ... ok
test_route_helpers (tests.test_webapp.HandlerRouteTests.test_route_helpers) ... ok
test_schema_route (tests.test_webapp.HandlerRouteTests.test_schema_route) ... ok
test_static_whitelist_blocks_everything_else (tests.test_webapp.HandlerRouteTests.test_static_whitelist_blocks_everything_else) ... ok
test_unknown_routes_return_404 (tests.test_webapp.HandlerRouteTests.test_unknown_routes_return_404) ... ok
test_cancel_and_lookup_of_unknown_jobs (tests.test_webapp.JobManagerTests.test_cancel_and_lookup_of_unknown_jobs) ... ok
test_create_job_records_params_status_log_and_result (tests.test_webapp.JobManagerTests.test_create_job_records_params_status_log_and_result) ... ok
test_failing_runner_is_recorded (tests.test_webapp.JobManagerTests.test_failing_runner_is_recorded) ... ok
test_interrupted_recovery_ignores_legacy_job_dirs (tests.test_webapp.JobManagerTests.test_interrupted_recovery_ignores_legacy_job_dirs) ... ok
test_list_jobs_newest_first_and_read_log_offsets (tests.test_webapp.JobManagerTests.test_list_jobs_newest_first_and_read_log_offsets) ... ok
test_mark_interrupted_only_touches_active_statuses (tests.test_webapp.JobManagerTests.test_mark_interrupted_only_touches_active_statuses) ... ok
test_nonzero_return_code_fails_the_job (tests.test_webapp.JobManagerTests.test_nonzero_return_code_fails_the_job) ... ok
test_progress_target_line_only_touches_the_message (tests.test_webapp.JobManagerTests.test_progress_target_line_only_touches_the_message) ... ok
test_read_log_ignores_bad_offsets (tests.test_webapp.JobManagerTests.test_read_log_ignores_bad_offsets) ... ok
test_request_stop_marks_the_job_cancelled (tests.test_webapp.JobManagerTests.test_request_stop_marks_the_job_cancelled) ... ok
test_check_key_rejects_unknown_and_external_models (tests.test_webapp.ModelServiceTests.test_check_key_rejects_unknown_and_external_models) ... ok
test_list_models_reports_status_labels_and_paths (tests.test_webapp.ModelServiceTests.test_list_models_reports_status_labels_and_paths) ... ok
test_submit_download_and_delete_queue_model_jobs (tests.test_webapp.ModelServiceTests.test_submit_download_and_delete_queue_model_jobs) ... ok
test_other_lines_are_ignored (tests.test_webapp.ProgressLineTests.test_other_lines_are_ignored) ... ok
test_progress_lines (tests.test_webapp.ProgressLineTests.test_progress_lines) ... ok
test_target_lines (tests.test_webapp.ProgressLineTests.test_target_lines) ... ok
test_dataprep_choices (tests.test_webapp.SchemaTests.test_dataprep_choices) ... ok
test_engine_and_format_lists_come_from_shared (tests.test_webapp.SchemaTests.test_engine_and_format_lists_come_from_shared) ... ok
test_modes_and_presets (tests.test_webapp.SchemaTests.test_modes_and_presets) ... ok
test_pattern_form_field_keys_exist (tests.test_webapp.SchemaTests.test_pattern_form_field_keys_exist) ... ok
test_bed_mode_reports_missing_regions (tests.test_workbench_form.ErrorBranchTests.test_bed_mode_reports_missing_regions) ... ok
test_empty_inputs_report_required_fields (tests.test_workbench_form.ErrorBranchTests.test_empty_inputs_report_required_fields) ... ok
test_memory_limit_modes (tests.test_workbench_form.ErrorBranchTests.test_memory_limit_modes) ... ok
test_missing_and_unreadable_inputs_are_reported_in_order (tests.test_workbench_form.ErrorBranchTests.test_missing_and_unreadable_inputs_are_reported_in_order) ... ok
test_output_dir_pointing_at_a_file (tests.test_workbench_form.ErrorBranchTests.test_output_dir_pointing_at_a_file) ... ok
test_pattern_errors_are_reported_last (tests.test_workbench_form.ErrorBranchTests.test_pattern_errors_are_reported_last) ... ok
test_search_timeout_values (tests.test_workbench_form.ErrorBranchTests.test_search_timeout_values) ... ok
test_gap_pair_requires_every_policy_value (tests.test_workbench_form.PairModeTests.test_gap_pair_requires_every_policy_value) ... ok
test_gap_pair_spec_and_config (tests.test_workbench_form.PairModeTests.test_gap_pair_spec_and_config) ... ok
test_partial_policy_is_reported_field_by_field (tests.test_workbench_form.PairModeTests.test_partial_policy_is_reported_field_by_field) ... ok
test_y_centered_spec_and_config (tests.test_workbench_form.PairModeTests.test_y_centered_spec_and_config) ... ok
test_active_side_updates (tests.test_workbench_form.PresetAndModelTests.test_active_side_updates) ... ok
test_cas12a_preset_updates_the_target_side (tests.test_workbench_form.PresetAndModelTests.test_cas12a_preset_updates_the_target_side) ... ok
test_cas9_preset_updates_the_left_side (tests.test_workbench_form.PresetAndModelTests.test_cas9_preset_updates_the_left_side) ... ok
test_helpers (tests.test_workbench_form.PresetAndModelTests.test_helpers) ... ok
test_resolve_side_model_selection (tests.test_workbench_form.PresetAndModelTests.test_resolve_side_model_selection) ... ok
test_side_model_options_follow_the_nuclease (tests.test_workbench_form.PresetAndModelTests.test_side_model_options_follow_the_nuclease) ... ok
test_bed_mode_moves_the_search_input_to_regions (tests.test_workbench_form.SingleModeTests.test_bed_mode_moves_the_search_input_to_regions) ... ok
test_default_run_label_is_system_and_target_name (tests.test_workbench_form.SingleModeTests.test_default_run_label_is_system_and_target_name) ... ok
test_result_label_overrides_the_default (tests.test_workbench_form.SingleModeTests.test_result_label_overrides_the_default) ... ok
test_spec_and_config_use_the_form_values (tests.test_workbench_form.SingleModeTests.test_spec_and_config_use_the_form_values) ... ok

----------------------------------------------------------------------
Ran 77 tests in 46.198s

OK
```

### 2.3 桌面端回归

```powershell
python -m unittest tests.test_designer_workbench tests.test_pattern_runner -v
```

```text
test_browse_directory_uses_designer_as_parent (tests.test_designer_workbench.DesignerFileDialogTests.test_browse_directory_uses_designer_as_parent) ... ok
test_browse_file_uses_designer_as_parent (tests.test_designer_workbench.DesignerFileDialogTests.test_browse_file_uses_designer_as_parent) ... ok
test_bed_input_mode_config (tests.test_designer_workbench.DesignerWorkbenchTests.test_bed_input_mode_config) ... ok
test_crispai_is_a_normal_off_target_model (tests.test_designer_workbench.DesignerWorkbenchTests.test_crispai_is_a_normal_off_target_model) ... ok
test_crispai_is_only_listed_for_cas9 (tests.test_designer_workbench.DesignerWorkbenchTests.test_crispai_is_only_listed_for_cas9) ... ok
test_custom_model_options_include_all_preset_models (tests.test_designer_workbench.DesignerWorkbenchTests.test_custom_model_options_include_all_preset_models) ... ok
test_left_and_right_presets_independent (tests.test_designer_workbench.DesignerWorkbenchTests.test_left_and_right_presets_independent) ... ok
test_max_mismatch_default_and_zero_are_consistent (tests.test_designer_workbench.DesignerWorkbenchTests.test_max_mismatch_default_and_zero_are_consistent) ... ok
test_mode_labels_match_design_patterns (tests.test_designer_workbench.DesignerWorkbenchTests.test_mode_labels_match_design_patterns) ... ok
test_model_display_names_include_protein_group (tests.test_designer_workbench.DesignerWorkbenchTests.test_model_display_names_include_protein_group) ... ok
test_model_dropdown_stays_open_after_selection (tests.test_designer_workbench.DesignerWorkbenchTests.test_model_dropdown_stays_open_after_selection) ... ok
test_pair_config_crispai_any_side (tests.test_designer_workbench.DesignerWorkbenchTests.test_pair_config_crispai_any_side) ... ok
test_pair_config_includes_pair_rank_policy (tests.test_designer_workbench.DesignerWorkbenchTests.test_pair_config_includes_pair_rank_policy) ... ok
test_pair_config_uses_per_side_nuclease_and_model (tests.test_designer_workbench.DesignerWorkbenchTests.test_pair_config_uses_per_side_nuclease_and_model) ... ok
test_pipeline_failure_shows_popup_with_output_tail (tests.test_designer_workbench.DesignerWorkbenchTests.test_pipeline_failure_shows_popup_with_output_tail) ... ok
test_primary_model_marker_follows_selection_order (tests.test_designer_workbench.DesignerWorkbenchTests.test_primary_model_marker_follows_selection_order) ... ok
test_progress_bar_falls_back_to_indeterminate (tests.test_designer_workbench.DesignerWorkbenchTests.test_progress_bar_falls_back_to_indeterminate) ... ok
test_python_fallback_prompt_asks_and_logs_the_reason (tests.test_designer_workbench.DesignerWorkbenchTests.test_python_fallback_prompt_asks_and_logs_the_reason) ... ok
test_python_fallback_prompt_can_be_declined (tests.test_designer_workbench.DesignerWorkbenchTests.test_python_fallback_prompt_can_be_declined) ... ok
test_readiness_tracks_missing_and_ready_states (tests.test_designer_workbench.DesignerWorkbenchTests.test_readiness_tracks_missing_and_ready_states) ... ok
test_score_targets_requires_find_first (tests.test_designer_workbench.DesignerWorkbenchTests.test_score_targets_requires_find_first) ... ok
test_side_model_options_follow_nuclease (tests.test_designer_workbench.DesignerWorkbenchTests.test_side_model_options_follow_nuclease) ... ok
test_side_model_options_support_multiple_selections (tests.test_designer_workbench.DesignerWorkbenchTests.test_side_model_options_support_multiple_selections) ... ok
test_single_off_target_model_default_cfd (tests.test_designer_workbench.DesignerWorkbenchTests.test_single_off_target_model_default_cfd) ... ok
test_single_side_preset_fills_config (tests.test_designer_workbench.DesignerWorkbenchTests.test_single_side_preset_fills_config) ... ok
test_switching_to_cas13_sets_pfs (tests.test_designer_workbench.DesignerWorkbenchTests.test_switching_to_cas13_sets_pfs) ... ok
test_target_counter_line_updates_label (tests.test_designer_workbench.DesignerWorkbenchTests.test_target_counter_line_updates_label) ... ok
test_unknown_prompt_kind_is_refused_without_a_dialog (tests.test_designer_workbench.DesignerWorkbenchTests.test_unknown_prompt_kind_is_refused_without_a_dialog) ... ok
test_bed_regions_builds_window_fasta (tests.test_pattern_runner.PatternRunnerTests.test_bed_regions_builds_window_fasta) ... ok
test_engine_selection_reaches_offtarget_commands (tests.test_pattern_runner.PatternRunnerTests.test_engine_selection_reaches_offtarget_commands) ... ok
test_gap_preset_forces_pam_hard_filter (tests.test_pattern_runner.PatternRunnerTests.test_gap_preset_forces_pam_hard_filter) ... ok
test_labeled_outputs_rename_after_run (tests.test_pattern_runner.PatternRunnerTests.test_labeled_outputs_rename_after_run) ... ok
test_max_bulge_and_pam_mode_reach_offtarget_commands (tests.test_pattern_runner.PatternRunnerTests.test_max_bulge_and_pam_mode_reach_offtarget_commands) ... ok
test_motif_gap_motif_extract_command (tests.test_pattern_runner.PatternRunnerTests.test_motif_gap_motif_extract_command) ... ok
test_output_path_is_mode_specific (tests.test_pattern_runner.PatternRunnerTests.test_output_path_is_mode_specific) ... ok
test_pair_pam_settings_are_split_per_side (tests.test_pattern_runner.PatternRunnerTests.test_pair_pam_settings_are_split_per_side) ... ok
test_pair_runner_passes_multiple_model_choices_per_side (tests.test_pattern_runner.PatternRunnerTests.test_pair_runner_passes_multiple_model_choices_per_side) ... ok
test_read_gap_extract_candidates (tests.test_pattern_runner.PatternRunnerTests.test_read_gap_extract_candidates) ... ok
test_read_gap_extract_candidates_uses_query_sidecar (tests.test_pattern_runner.PatternRunnerTests.test_read_gap_extract_candidates_uses_query_sidecar) ... ok
test_read_single_extract_candidates (tests.test_pattern_runner.PatternRunnerTests.test_read_single_extract_candidates) ... ok
test_read_single_extract_candidates_accepts_target_start (tests.test_pattern_runner.PatternRunnerTests.test_read_single_extract_candidates_accepts_target_start) ... ok
test_read_y_extract_candidates (tests.test_pattern_runner.PatternRunnerTests.test_read_y_extract_candidates) ... ok
test_run_pipeline_supports_find_and_score_split (tests.test_pattern_runner.PatternRunnerTests.test_run_pipeline_supports_find_and_score_split) ... ok
test_single_motif_pipeline_shape (tests.test_pattern_runner.PatternRunnerTests.test_single_motif_pipeline_shape) ... ok
test_single_preset_forces_pam_hard_filter (tests.test_pattern_runner.PatternRunnerTests.test_single_preset_forces_pam_hard_filter) ... ok
test_single_score_step_does_not_pass_exact_flag_to_analyze (tests.test_pattern_runner.PatternRunnerTests.test_single_score_step_does_not_pass_exact_flag_to_analyze) ... ok
test_y_centered_extract_command (tests.test_pattern_runner.PatternRunnerTests.test_y_centered_extract_command) ... ok
test_y_preset_forces_pam_hard_filter (tests.test_pattern_runner.PatternRunnerTests.test_y_preset_forces_pam_hard_filter) ... ok
test_y_sort_requires_both_sides (tests.test_pattern_runner.PatternRunnerTests.test_y_sort_requires_both_sides) ... ok
test_y_sorted_output_uses_motif_label (tests.test_pattern_runner.PatternRunnerTests.test_y_sorted_output_uses_motif_label) ... ok
test_fallback_env_defaults_to_ask (tests.test_pattern_runner.PipelineConfirmationTests.test_fallback_env_defaults_to_ask) ... ok
test_parse_confirm_request (tests.test_pattern_runner.PipelineConfirmationTests.test_parse_confirm_request) ... ok
test_pipeline_answers_confirmation_from_the_front_end (tests.test_pattern_runner.PipelineConfirmationTests.test_pipeline_answers_confirmation_from_the_front_end) ... ok
test_pipeline_can_be_declined_by_the_front_end (tests.test_pattern_runner.PipelineConfirmationTests.test_pipeline_can_be_declined_by_the_front_end) ... ok
test_pipeline_refuses_when_the_handler_raises (tests.test_pattern_runner.PipelineConfirmationTests.test_pipeline_refuses_when_the_handler_raises) ... ok
test_pipeline_refuses_without_a_handler (tests.test_pattern_runner.PipelineConfirmationTests.test_pipeline_refuses_without_a_handler) ... ok

----------------------------------------------------------------------
Ran 56 tests in 67.962s

OK
```

### 2.4 最小端到端（另开终端）

```powershell
python webapp\app.py --port 8123
```

服务端 stdout（`R:` 网络盘 import 较重，约 100 秒后开始监听）：

```text
Local interface: http://127.0.0.1:8123
```

```powershell
curl.exe -s http://127.0.0.1:8123/api/schema
```

原始 JSON（节选；完整内容与 §4 一致，仅长度截断）：

```json
{"modes": [{"value": "single_motif_flank", "label": "Single target design"}, {"value": "motif_gap_motif", "label": "Paired-target design Pattern A: Target-xbp-Target"}, {"value": "y_centered_motifs", "label": "Paired-target design Pattern B: Target-xbp-Motif-ybp-Target"}], "input_modes": [{"value": "sequence", "label": "Sequence (FASTA)"}, {"value": "bed", "label": "BED Regions"}], "presets": [{"value": "custom", "label": "Custom / free input", "nuclease": "custom", "tnpb_subtype": "unknown", "pam": "", "spacer_len": null, "pam_side": "", "pam_mode": "custom", "pam_required": false}, {"value": "cas9", "label": "SpCas9", "nuclease": "cas9", "tnpb_subtype": "unknown", "pam": "NGG", "spacer_len": 20, "pam_side": "3prime", "pam_mode": "strict_ngg", "pam_required": true}, {"value": "cas12a", "label": "Cas12a / LbCpf1", "nuclease": "cas12a", "tnpb_subtype": "unknown", "pam": "TTTN", "spacer_le ...(截断)
```

关键字段：`engines = exact, indexed, blast, gggenome, auto`；
`modes = single_motif_flank, motif_gap_motif, y_centered_motifs`；
`presets = custom, cas9, cas12a, cas12b, cas13, tnpb`；
`export_formats = csv, tsv, fasta, bed, xlsx, unique_guides, library`；
`model_groups = 4 组`；`designer.field_keys = 48`。

```powershell
curl.exe -s http://127.0.0.1:8123/ | Select-String -Pattern "Data prep","Models","Designer"
```

```text
  <button class="tab active" data-panel="dataprep">Data prep</button>
  <button class="tab" data-panel="models">Models</button>
  <button class="tab" data-panel="designer">Designer</button>
    <h2>Data prep</h2>
  <section id="panel-models" class="panel hidden">
    <h2>Models</h2>
  <section id="panel-designer" class="panel hidden">
    <h2>Designer</h2>
```

附加的静态资源/白名单检查：

```text
GET /static/app.js        -> 200, 40394 bytes
GET /static/styles.css    -> 200, 6190 bytes
GET /static/..%2fapp.py   -> 404
```

### 2.5 preview + 最小作业

`out\webapp_smoke\target.fa`（按第 6 节示例手工创建：`>t1` + 一行 40 bp）、
`genome_fasta = R:\songji\programfile\example\engine_benchmark\synthetic_genome.fa`、
`output_dir = R:\songji\programfile\out\webapp_smoke`，全部绝对路径。

```powershell
curl.exe -s -X POST http://127.0.0.1:8123/api/designer/preview -H "Content-Type: application/json" --data-binary "@preview.json"
```

```json
{"mode": "single_motif_flank", "describe": "[upstream flank 5 bp] + [TTAT]", "errors": [], "warnings": [], "memory_resolved": 14065, "run_label": "SpCas9_target"}
```

提交 `Find Targets`（motif 改成 `TACG`，使其在 `ACGTACGT...` 模板上真实命中）：

```text
POST /api/designer/jobs
  -> {"job_id": "d32ec809fc08", "stage": "find", "title": "Find Targets",
      "run_label": "SpCas9_target", "output_dir": "R:\\songji\\programfile\\out\\webapp_smoke"}
轮询 /api/jobs/d32ec809fc08：queued 1% -> running 2% -> running 90% (下载基因组) -> succeeded 100% Complete
job.log（ASCII 行逐字）：
  Memory limit: auto, resolved=14088 MiB (50% total, 75% available guard; total=32386 MiB, available=18779 MiB)
  Run label: SpCas9_target
  [extract] C:\Users\ASUS\AppData\Local\Programs\Python\Python314\python.exe \\smb.tnlab.cn\apool\songji\programfile\basic\extract.py R:\songji\programfile\out\webapp_smoke\target.fa TACG 5 upstream R:\songji\programfile\out\webapp_smoke\extracted_seqs.tsv
  PROGRESS: <中文行，网页日志中显示为替换字符，见 §4-2>
result.json: {"run_label": "SpCas9_target", "output_dir": "...\out\webapp_smoke", "extract_output": "...\out\webapp_smoke\extracted_seqs.tsv"}
```

候选表与导出：

```text
GET /api/jobs/d32ec809fc08/candidates
  columns = query_id, seq_id, strand, start, end, motif_seq, flank_seq, side, flank_length, positions_json
  total   = 16   （query_seq / gap_seq 已隐藏）
POST /api/jobs/d32ec809fc08/export  {"format": "csv", "rows": [0, 1], "filename": "smoke_selected.csv"}
  -> {"written": 2, "file": "export/smoke_selected.csv", "format": "csv",
      "download_url": "/api/jobs/d32ec809fc08/download?file=export/smoke_selected.csv"}
GET 该 download_url -> HTTP 200, 586 bytes, CSV 表头 + 2 行候选
GET /api/outputs?dir=R%3A%5Csongji%5Cprogramfile%5Cout%5Cwebapp_smoke
  -> extracted_seqs.tsv (488 B), target.fa (45 B)
```

`Score & Off-target`（`stage=score`，同一表单）：

```text
POST /api/designer/jobs -> {"job_id": "62b081ed1e05", "stage": "score", "title": "Score & Off-target", ...}
轮询：queued 1% -> running 2% -> running 30% (下载基因组) -> running 70% (Off-target search (exact))
      -> "Analyzing target 1/2" 持续
POST /api/jobs/62b081ed1e05/cancel -> {"status": "running", "message": "Stopping...", ...}
下一次轮询：cancelled 70% Cancelled
GET /api/jobs（新的在前）：
job_id       kind     title              status    progress created
62b081ed1e05 designer Score & Off-target cancelled       70 2026/9/16 15:49:52
d32ec809fc08 designer Find Targets       succeeded      100 2026/9/16 15:48:32
cc287cd61c1b designer Find Targets       succeeded      100 2026/9/16 15:48:03
```

（`cc287cd61c1b` 是第一次 motif=TTAT 的尝试，目标序列里没有 TTAT，抽取结果为空 TSV，
作业仍 `succeeded`，与桌面端行为一致。）

附加：

```powershell
python webapp\app.py --port 8123 --help
```

```text
usage: app.py [-h] [--port PORT] [--host HOST]

Local-only CRISPR motif workbench

options:
  -h, --help   show this help message and exit
  --port PORT
  --host HOST  Bind address; keep 127.0.0.1 for local use
```

## 3. 未做项及原因

1. **`Score & Off-target` 没有跑到结束**：冒烟时观察到 `Analyzing target 1/2` 后
   主动取消（`blast.py` 的 exact 搜索在 5 MB 合成基因组上 4 分钟未完成，且每次
   轮询都要读 `R:` 网络盘）。阶段守卫、进度上报、取消与 stop hook 已在这一段
   验证完毕。
2. **没有实现 `CONFIRM_REQUIRED` 的人工确认入口**（P1）：按第 5 节决策默认自动
   同意，并把请求写进日志 `[auto-confirm] <kind>|<reason>`。
3. **没有做面板/表单持久化**（P1）：刷新页面丢未提交的表单值；Designer 表单值
   仅在内存中保持。
4. **没有移植 Library 出库流程**（明确不做；`job_store.py` 随之作废）。
5. **没有跑完整 `run_tests.py`**（任务边界：只跑第 6 节列出的命令）。
6. **`model_catalog()` 未加 `visible_only` 过滤**：与 `main.py` 的 Models 页签相比，
   网页版会多列出 `teep`（不可下载的在线模型，下载/删除接口返回 400）。目的是让
   所有可下载模型在网页端都可达，属有意偏差。
7. **未做浏览器手工点击验证**（本机没有受控浏览器会话）：用 HTTP 层自检（§2.4/§2.5）
   加静态引用一致性脚本代替（见 §4-6）。

## 4. 附带发现（只记录，不修复）

1. 仓库根目录**没有 `.git`**，无法生成 diff；改动前后用
   `backup\20260916_webapp_designer_port\` 快照对照。
2. 子进程（`basic\extract.py`、`basic\blast.py` 等）在 Windows 上按 GBK 输出中文，
   作业日志按 UTF-8 读取，网页日志里这些行显示为 `U+FFFD` 替换字符（例：
   `PROGRESS: ͳ������ 0`）。属可读性问题，未改。
3. `webapp/jobs/87499fe93868/`（旧 library 实现的遗留目录，`status.json` 无 `kind`）
   被新 `JobManager.read_status` 判为 `None`：不出现在 `/api/jobs`，也不会被
   `mark_interrupted_jobs` 改写，`LastWriteTime` 仍是 `2026/8/15 15:50:05`。
4. `webapp/job_store.py` 现在只剩一句说明；全仓库已无模块 import 它
   （`shared/design/library_pipeline.py` 也不再 import）。
5. `designer_workbench.py` 里仍有既存死代码（`GUI_SCRIPTS` 分支等）与多个 `.venv`
   残留目录，本次未触碰。
6. 前端没有构建/测试框架，因此加了一次性引用一致性检查（临时脚本，未入库）：
   `app.js` 中 `$('id')` 用到的 67 个 id 全部存在于 `index.html`；`index.html` 里
   未被 `$(...)` 直接引用的 id 只有面板容器（`panel-*`、`tabs`、`dp-job`、
   `designer-log-wrap`，前两者由 `switchPanel` 用字符串拼接访问）。
7. 本次冒烟在 `webapp/jobs/` 新增 3 个作业目录（`cc287cd61c1b`、`d32ec809fc08`、
   `62b081ed1e05`），并生成 `out/webapp_smoke/`（`target.fa`、`extracted_seqs.tsv`、
   `export/smoke_selected.csv`）。按“不删除任何文件”的约束保留。
8. `python -m py_compile` 会生成 `__pycache__`（`webapp/`、`webapp/services/`、
   `shared/design/`、`tests/`）。
9. `R:` 网络盘 I/O 很慢（首次 import 20~100 秒）；在 `R:` 上并行跑全仓搜索会严重
   拖慢后续命令（实测残留的 `rg` / `rglob` 进程让单测多花十几分钟）。建议 master
   核验时避免并行全仓搜索。
10. 本次自检的中间产物放在 `R:\songji\programfile\.codex_tmp\`（`check2.txt`、
    `check3.txt`、`check4_schema.json`、`candidates.json`、若干 `*.json` 请求体、
    `server_*.txt`、上一轮遗留的 `patch_designer_workbench.py` / `app_chunk_*.js`），
    都是脚本/证据文件，不是产品代码；按“不删除任何文件”保留。

## 5. 待明确

1. `POST /api/designer/active-side` 是我按桌面端 `Use for Run` 语义**新增**的便利
   端点（任务书的 API 列表未列出）。若希望严格只保留任务书里的端点，可删除它并让
   前端本地合成字段更新。
2. `webapp/schema.py` 的 `model_catalog()` 是否恢复 `visible_only=True`（隐藏
   `teep`），需要 master 拍板（见 §3-6）。
3. 导出文件名默认带时间戳（`<run_label>_<base>_<YYYYmmdd_HHMMSS>.<ext>`），可由
   `filename` 字段覆盖；网页端没有系统保存对话框。如需固定命名策略请明确。
4. 页面静态文案为英文、`docs/WEBAPP.md` 为中文（遵循第 5 节“页面语言英文，
   说明性文字可中文”）。若希望文档也改英文请说明。
