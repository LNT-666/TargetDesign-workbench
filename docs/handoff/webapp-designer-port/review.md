# 核验报告：webapp-designer-port

- round: 1
- verdict: **pass**（P0-1..P0-6 全部成立；无返工项）
- updated: 2026-09-16 20:35
- 依据：`report.md`（round 1，34,594 B）+ 基线快照 `backup/20260916_webapp_designer_port/`（8 文件）
  + master 自写探针 `assets/master_verify_equivalence.py`、`assets/master_verify_http.py`

## 逐条核验

| 任务项 | 结论 | 证据（master 独立复现） |
| --- | --- | --- |
| P0-1 抽取 `shared/design/workbench_form.py` | 通过 | 文件存在且无 `tkinter`；`assets/master_verify_equivalence.py` 用 `object.__new__` + 桩变量实例化**备份版** `designer_workbench.py` 的 `PatternDesignerWorkbench`，与 `shared/design/workbench_form.py` 逐调用比对 10 个方法（`_current_spec` / `_current_config` / `_readiness_errors` / `_default_run_label` / `_resolved_memory_limit` / `_search_timeout_s` / `_pair_rank_policy_values` / `_prepare_genome_fasta` / `_resolve_side_models` / `_auto_memory_limit`）+ 24 case × 预设/切侧/模型下拉 + 静态检查（无 `PatternSpec(` / `MotifSpec(` / `RunnerConfig(` 残留）→ **403/403 PASS** |
| P0-2 `designer_workbench.py` 改薄包装 | 通过 | `tests/test_designer_workbench.py` 与基线**逐字节相同**；`python -m unittest tests.test_designer_workbench` OK |
| P0-3 重做 webapp 后端 | 通过 | `assets/master_verify_http.py` → **88/88 PASS**：`/api/schema` 与 `shared/` 全量一致（modes/presets/engines/export_formats/pair_rank_fields + 48 字段）；真实 `find` 作业 `b1150f5ebc1e` succeeded / 16 候选 / 导出 tsv + 下载；4 类预检 400 文案；`score` 未提取时的 400 精确文案；取消路径；日志 offset 增量；`/static/..%2fapp.py` 拒绝；下载白名单与路径穿越拒绝；`GET /api/jobs` 形状 |
| P0-4 重做前端 | 通过 | `GET /` 200 且含工作区标记；静态资源只有 `app.js` / `styles.css`（在服务端白名单内）、无 CDN 外链；`node --check webapp/static/app.js` OK |
| P0-5 测试 | 通过 | `python -m unittest tests.test_webapp tests.test_workbench_form tests.test_designer_workbench tests.test_pattern_runner` → `Ran 133 tests ... OK` |
| P0-6 文档 | 通过 | `docs/WEBAPP.md`（启动、安全边界、`outputs` 表、回填表）；`README.md:30` 指向 web UI |

## master 独立验证

- 代码比对：`backup/20260916_webapp_designer_port/` 8 文件逐一 diff —— `tests/test_designer_workbench.py` 未改；其余均为本任务预期变更（`designer_workbench.py` 变薄、`webapp/{app.py,schema.py,jobs.py,services/**,static/**,index.html}` 重写、`docs/WEBAPP.md`、`README.md`）。
- 探针或端到端：见上表 P0-1 / P0-3 两条，均为 master 自己写的脚本、自己跑的进程（服务端口 8341）。
- 测试：见上表 P0-5（133 tests OK）。若把 `.venv310` 当解释器会挂，本机权威解释器是 `C:\Users\ASUS\AppData\Local\Programs\Python\Python314\python.exe`。

## 归属判定（既有失败 vs 本次引入）

- 无失败用例。

## 已知偏差（非缺陷，任务书未规定到这一层，已由 master 判定可接受）

- `designer_field_keys` 48 个；`GET /api/jobs` 返回 `{"jobs":[...]}` 包了一层的形状；`/api/models` 多一列 `teep`。
- `single_motif_flank` 的 `pattern_forms` 只有一个 `left` slot（candidates 由 `webapp/services/designer.py` 服务端过滤 `query_seq`/`gap_seq`）。
- malformed job id → 400，未知 id → 404（任务书未规定，行为合理）。

## 新发现（等级 / 归属）

- `webapp/jobs.py:265,274,303` 读子进程 stdout 用 UTF-8，但子进程在 GBK 控制台下会输出 GBK → 日志乱码 — **P1** — 归属：本任务实现选择，非回归。缓解：`CRISPR-Motif-Workbench.exe` 启动时注入 `PYTHONIOENCODING=utf-8`；`python webapp\app.py` 直起仍会乱码，已另案（`webapp-subprocess-encoding`，未开工）。
- `tests/test_webapp.py::test_index_page_has_the_four_tabs` 名称过时（页签已在后续任务中移除），断言当前仍通过 — **P2**。
- `dataprep.build-index` 只给 prefix 时 `outputs` 无 `output_dir` — **P2**。
- 前端三文件在 16:00 之后出现 UTF-8 BOM（违反 `docs/WEBAPP.md:34-35` 的“LF、无 BOM”）— **P2** — 归属：`backup/20260916_webapp_single_page/` 里同样三个文件无 BOM，故**非本任务引入**；已作为 P0-4 列入 `docs/handoff/webapp-big-prep-panel/task.md` 修复。

以上 4 条均已写进各自的后续任务/记录，不在本任务返工。

## 下一步

- 通过。剩余可选项：(1) 修 `webapp/jobs.py` 的子进程编码（另案）；(2) `test_index_page_has_the_four_tabs` 改名（P2）；(3) `build-index` 的 `output_dir`（P2）。
- 后续任务：`docs/handoff/webapp-single-page-layout/`（done）、`docs/handoff/webapp-big-prep-panel/`（assigned）。