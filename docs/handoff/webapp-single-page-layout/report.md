# 交付报告：webapp-single-page-layout

- round: 1
- status: ready_for_review
- updated: 2026-09-16 16:40
- depends_on: `webapp-designer-port`（已 `ready_for_review`，round 1）

## P0-0 开工前置检查（已通过）

```text
docs/handoff/webapp-designer-port/state.json -> "status": "ready_for_review"
shared/design/workbench_form.py              24145 B  OK
webapp/jobs.py                               15617 B  OK
webapp/schema.py                             14383 B  OK
webapp/services/designer.py                  13208 B  OK
webapp/services/dataprep.py                  19332 B  OK
webapp/services/models.py                     5401 B  OK
webapp/static/app.js                         40394 B  OK
webapp/static/styles.css                      6190 B  OK
READY
```

改前快照：`backup\20260916_webapp_single_page\`（`webapp\index.html`、
`webapp\static\{app.js,styles.css}`、`webapp\jobs.py`、
`webapp\services\{dataprep,designer}.py`、`docs\WEBAPP.md`、`README.md`）。
所有改动文件均为 LF、无 BOM。

## 改动清单

| 文件 | 行 | 改了什么 | 对应任务项 |
| --- | --- | --- | --- |
| `webapp/jobs.py` | 55 | `STATUS_FIELDS` 增加 `"outputs"` | P0-1 |
| `webapp/jobs.py` | 107 | `JobContext.outputs` 初值 `{}` | P0-1 |
| `webapp/jobs.py` | 169-199 | 新增 `JobContext._resolve_output()`（只接受存在的路径；`build-index` 前缀按 `<prefix>.*` 兄弟文件判定）与 `JobContext.set_outputs()`（过滤不存在路径后写 `status.json`） | P0-1 |
| `webapp/jobs.py` | 248 | `read_status()` 用 `setdefault("outputs", {})`，旧作业目录也返回 `{}`（不回写文件） | P0-1 |
| `webapp/jobs.py` | 316 | `create_job()` 初始状态写 `"outputs": {}` | P0-1 |
| `webapp/services/dataprep.py` | 339-343 | `download`：`genome_fasta` / `annotation` / `output_dir` | P0-1 |
| `webapp/services/dataprep.py` | 377-384 | `prepare`：`genome_fasta` / `annotation` / `target_fasta` / `mask_fasta` / `output_dir` / 有则 `blastdb` | P0-1 |
| `webapp/services/dataprep.py` | 402-405 | `extract-target`：`target_fasta` / `output_dir` | P0-1 |
| `webapp/services/dataprep.py` | 431-434 | `extract-mask`：`mask_fasta` / `output_dir` | P0-1 |
| `webapp/services/dataprep.py` | 448 | `build-blastdb`：`blastdb` / `output_dir` | P0-1 |
| `webapp/services/dataprep.py` | 472-479 | `build-index`：先算 `index_path`（`prefix` 或 `output_dir/<genome 名>`）写进 `result.index_prefix`，再写 `index_path` / `output_dir` | P0-1 |
| `webapp/services/designer.py` | 246-251 | `find` / `score`：`search_fasta`（sequence）/ `bed_regions`（bed）/ `output_dir` / `extract_output` | P0-1 |
| `webapp/index.html` | 20-37 | 顶部固定条：抽屉按钮、模式下拉、`Find Targets`、`Score & Off-target`、就绪徽标、进度条、最近作业摘要 | P0-2 |
| `webapp/index.html` | 39-46 | `#workspace` grid + `#drawer` 抽屉容器（`aria-hidden`、`aria-label`、关闭按钮） | P0-2 |
| `webapp/index.html` | 47-142 | 抽屉内容：先 Data prep（下载 / 基因组注释 / Search scope / Mask gene / Prepare），后 Models | P0-2、§1.3 |
| `webapp/index.html` | 147-163 | 主区三列：公共输入（`<details open>` 可折叠）+ Left TAM、Middle + Structure Preview、Right TAM | P0-2、§1.2 |
| `webapp/index.html` | 153 | `#designer-loaded-hint`（公共输入区的“已带入”提示行） | P0-3、§1.3 |
| `webapp/index.html` | 165-232 | 下部常驻块：Run Settings、Run Log、候选表 + 导出控件、`Results / Output`（作业表、作业详情、`#job-outputs`、输出目录文件列表） | P0-2、§1.2 |
| `webapp/index.html` | 225 | `#job-outputs`：作业详情面板里的 `outputs` 容器（便于核对回填来源） | P0-1 |
| `webapp/static/app.js` | 1398-1411 | `pollJobDetail()` 渲染 `outputs` 键值对到 `#job-outputs`（函数体 1363-1424） | P0-1 |
| `webapp/static/app.js` | 13-41 | `state` 增加 `drawerOpen` / `loadedHint` / `recentJob` | P0-2 |
| `webapp/static/app.js` | 134-266 | 移除页签导航（`switchPanel` / `initTabs` / `.tabs`），改为 `setDrawer()`、`shortKind()`、`formatDuration()`、`renderRecentJob()`、`setRecentJob()`、`resetRecentJob()`、`scrollToRunLog()`、`initLayout()` | P0-2、§5 |
| `webapp/static/app.js` | 269-419 | 回填：`OUTPUT_FIELD_MAP` / `DRAWER_FIELD_MAP` / `cleanText()` / `backfillPlan()`（只填空字段、`skip_mask`、手填不被覆盖）/ `renderLoadedHint()` / `applyJobOutputs()`（含重绘） | P0-3 |
| `webapp/static/app.js` | 582-590 | `renderCommon()` 渲染到 `#designer-common-fields`（折叠容器内） | P0-2 |
| `webapp/static/app.js` | 619-660 | `SLOT_CONTAINERS` + `renderPatternSlot()` + `renderPattern()`：left → 公共列、middle → 中间列、right → 右列，不再用 `#designer-pattern-col` | P0-2 |
| `webapp/static/app.js` | 662-668 | `renderRun()` 去掉重复的 `Run Settings` 标题（`<details>` 的 summary 已承担） | P0-2 |
| `webapp/static/app.js` | 924-957 | `pollJobInto()`：终态时 `setRecentJob()` + `applyJobOutputs()` | P0-1、P0-3、§5 |
| `webapp/static/app.js` | 960-967 | `startDataPrepJob()` 提交后 `resetRecentJob()` | §5 |
| `webapp/static/app.js` | 1115-1123 | `startModelAction()` 提交后 `resetRecentJob()` | §5 |
| `webapp/static/app.js` | 1154-1163 / 1177-1195 | `startDesignerJob()` / `pollDesignerJob()` 更新最近作业摘要 | §5 |
| `webapp/static/app.js` | 1349-1361 | `showJobDetail()` 清空 `#job-outputs` | P0-1 |
| `webapp/static/app.js` | 1520-1523 | `init()` 只调 `initLayout()` + `loadSchema()`（`initLayout()` 内部再调各 init 与 `loadJobs()`） | P0-2 |
| `webapp/static/styles.css` | 1-480 | 全部重写：`.topbar` 吸顶、`.workspace` grid 抽屉列、`.drawer`、`.main-area`、`.designer-columns` 三列、`.loaded-hint`、`.lower-block`、媒体查询 | P0-2、§1.2 |
| `webapp/static/styles.css` | 394-397 | `@media (max-width: 1399px)`：三列纵向堆叠 | §1.2、§5 |
| `webapp/static/styles.css` | 399-431 | `@media (max-width: 1199px)`：抽屉改为左侧覆盖式（`transform` 滑入，非模态） | §1.3、§5 |
| `docs/WEBAPP.md` | 36-100 | “四个页签”改为“单页工作区”（ASCII 布局图、断点、模式切换不清空） | P0-4 |
| `docs/WEBAPP.md` | 101-140 | 新增“抽屉：Data prep / Models”与“回填规则”表（只填空字段、`skip_mask`、就地提示、探针） | P0-4 |
| `docs/WEBAPP.md` | 186-206 | 作业模型补 `status.json` 的 `outputs` 字段与各作业的键 | P0-1、P0-4 |
| `docs/WEBAPP.md` | 33-35 | 静态资源说明补“LF、无 BOM、无外链” | P0-4 |
| `README.md` | 30 | 描述行改为“本地 Web UI：单页工作区（Designer 主区 + 数据准备抽屉）” | P0-4 |
| `docs/handoff/webapp-single-page-layout/assets/probe_backfill_rule.js` | 1-137 | 新探针：从 `app.js` 抽出真实 `backfillPlan()` 跑规则回归 | P0-3 |
| `docs/handoff/webapp-single-page-layout/assets/probe_backfill_http.py` | 1-161 | 新探针：真实作业验证 `outputs` 契约与“手填 `output_dir` 不被覆盖” | P0-1、P0-3 |

未改：`shared/**`、`designer_workbench.py`、`main.py`、`unified_gui.py`、
`webapp/schema.py`、`webapp/app.py`、`webapp/services/models.py`、
`tests/**`、`docs/handoff/webapp-designer-port/**`。

## 轻量自检结果

### 1) 语法

```powershell
python -m py_compile webapp\app.py webapp\jobs.py webapp\schema.py `
  webapp\services\designer.py webapp\services\dataprep.py webapp\services\models.py
```

```text
（无输出）
exit=0
```

另外 `node --check webapp\static\app.js`：

```text
node --check app.js: OK
```

### 2) 聚焦单测（前置任务的测试原样全绿）

```powershell
python -m unittest tests.test_webapp tests.test_workbench_form -v
```

```text
.............................................................................
----------------------------------------------------------------------
Ran 77 tests in 41.533s

OK
```

（`tests/test_webapp.py` 未做任何修改；`test_index_page_has_the_four_tabs`
断言 `Data prep` / `Models` / `Designer` / `Results / Output` 四个字符串仍在
HTML 中——新布局里它们分别是抽屉两块标题、抽屉说明里的 "Designer inputs" 与
`<summary>Results / Output</summary>`，因此该测试仍按原样通过。）

### 3) 启动并检查主页面结构

```powershell
python webapp\app.py --port 8123
curl.exe -s http://127.0.0.1:8123/ | Select-String -Pattern "drawer","workspace","candidates"
curl.exe -s http://127.0.0.1:8123/api/schema
```

```text
HTTP /200

    <button id="drawer-toggle" class="drawer-toggle" type="button"
            aria-expanded="false" aria-controls="drawer">Data prep / Models</button>
<div class="workspace" id="workspace">
  <aside class="drawer" id="drawer" aria-hidden="true"
    <div class="drawer-head">
      <button id="drawer-close" type="button">Close</button>
    <section class="drawer-block" id="drawer-dataprep">
    <section class="drawer-block" id="drawer-models">
    <section class="lower-block" id="candidates-block">
        <h3>Extracted Candidates</h3>
        <span id="designer-candidates-info" class="muted"></span>
        <table id="designer-candidates">
        <div id="job-candidates"></div>
HTTP 200
```

`GET /api/schema` 返回 15181 B，键为
`modes, input_modes, presets, preset_models, engines, pam_modes, memory_modes,
nucleases, tnpb_subtypes, export_formats, pair_rank_fields,
hidden_candidate_columns, model_groups, designer, dataprep`（与前置任务一致，
未新增/删除）。

任务 P0-2 要求贴出的四类标记（原文见 `webapp/index.html`）：

```html
<!-- 顶部固定条 -->
<div class="topbar" id="designer-topbar"> ... <span id="designer-ready" class="ready-badge"> ... </div>

<!-- 三列容器 -->
<div class="designer-columns" id="designer-columns">
  <div class="col" id="designer-common-col"> ... </div>
  <div class="col"> <div id="designer-middle-col"></div> ... </div>
  <div class="col" id="designer-right-col"></div>
</div>

<!-- 抽屉容器 -->
<div class="workspace" id="workspace">
  <aside class="drawer" id="drawer" aria-hidden="true" aria-label="Data prep and Models"> ... </aside>

<!-- 候选表容器 -->
<section class="lower-block" id="candidates-block">
  ...
  <div class="table-wrap"><table id="designer-candidates">...</table></div>
</section>
```

### 4) `outputs` 契约 + 回填（真实作业）

```powershell
python docs\handoff\webapp-single-page-layout\assets\probe_backfill_http.py
```

```text
PASS synthetic genome fixture exists
POST /api/dataprep/extract-target
  output_dir (typed by the user) = R:\songji\programfile\out\probe_backfill\hand_typed_output
  search_fasta (left empty)      -> outputs.target_fasta
  job_id = e8de2d324141
GET /api/jobs/e8de2d324141 -> status=succeeded message=Complete
PASS job succeeded
outputs = {
  "target_fasta": "R:\\songji\\programfile\\out\\probe_backfill\\hand_typed_output\\PROBE1-gene.fa",
  "output_dir": "R:\\songji\\programfile\\out\\probe_backfill\\hand_typed_output"
}
PASS outputs is present and non-empty
PASS outputs.output_dir is an existing absolute path
PASS outputs.target_fasta is an existing absolute path
PASS outputs.output_dir equals what the user typed (not overwritten)
PASS outputs has target_fasta (feeds the empty search_fasta field)
PASS target_fasta points at the extracted FASTA
  target_fasta head: >PROBE1-gene | TCAGGAGTAAGATTTAGGTTGCCAGCGCATGGGATCGCTCTTCGTTGTGGAAAGGTTTGT | TGCTGC
PASS GET /api/jobs lists the job
PASS GET /api/jobs carries outputs
jobs without outputs (legacy dirs must still expose {}): 3
PASS status.json on disk carries outputs

probe_backfill_http.py: all checks passed
```

`GET /api/jobs/<id>` 原文（节选）：

```json
{"job_id": "e8de2d324141", "kind": "dataprep", "title": "Extract Target FASTA",
 "status": "succeeded", "progress": 100, "message": "Complete", "returncode": 0,
 "outputs": {
   "target_fasta": "R:\\songji\\programfile\\out\\probe_backfill\\hand_typed_output\\PROBE1-gene.fa",
   "output_dir": "R:\\songji\\programfile\\out\\probe_backfill\\hand_typed_output"}}
```

说明：探针把用户“手填的 `output_dir`”先固定下来再跑作业，作业返回的
`outputs.output_dir` 与用户值逐字符相同（`equal`，未被覆盖），而用户留空的
Search FASTA 字段可以拿到 `outputs.target_fasta`（真实存在的绝对路径）去填。
浏览器侧把这套规则写成纯函数，探针直接抽取该函数回归：

```powershell
node docs\handoff\webapp-single-page-layout\assets\probe_backfill_rule.js
```

```text
PASS target_fasta -> search_fasta
PASS genome_fasta -> genome_fasta
PASS mask_fasta -> mask_fasta
PASS output_dir -> output_dir
PASS blastdb -> blastdb
PASS index_path -> index_path
PASS annotation stays out of the main area (recorded in the drawer only)
PASS nothing ignored for the documented keys
PASS empty field is filled
PASS user value is never overwritten
PASS overwritten field is reported as skipped
PASS skip_mask leaves mask_fasta alone
PASS skip_mask still fills the other keys
PASS blank value is skipped
PASS unknown key is recorded as ignored
PASS typed drawer value is kept

probe_backfill_rule.js: all checks passed
```

### 4b) 旧作业目录的兼容读法（`setdefault`）

```powershell
curl.exe -s http://127.0.0.1:8123/api/jobs/d32ec809fc08
curl.exe -s http://127.0.0.1:8123/api/jobs/e8de2d324141
```

```text
{"job_id": "d32ec809fc08", "kind": "designer", "title": "Find Targets", "status": "succeeded",
 "progress": 100, "message": "Complete", "returncode": 0, ..., "outputs": {}, "log_tail": "..."}

{"job_id": "e8de2d324141", "kind": "dataprep", "title": "Extract Target FASTA", "status": "succeeded",
 "progress": 100, "message": "Complete", "returncode": 0, ...,
 "outputs": {"target_fasta": "R:\\songji\\programfile\\out\\probe_backfill\\hand_typed_output\\PROBE1-gene.fa",
             "output_dir": "R:\\songji\\programfile\\out\\probe_backfill\\hand_typed_output"},
 "log_tail": "...", "result": {...}}
```

前置任务留下的 `d32ec809fc08`（`status.json` 里没有 `outputs` 键）读出来是 `{}`，
文件本身没有被改写（`read_status()` 只做 `setdefault`）。

### 5) 结构一致性（补充检查，非任务要求）
`python .codex_tmp\check_layout.py`（本地临时脚本，未入库）：

```text
html tags closed: OK
duplicate ids: none
js id refs: 68 | missing from HTML: none
index contains drawer:      True
index contains workspace:   True
index contains candidates:  True
css braces balanced: True
css has .topbar / .workspace / .drawer / .designer-columns / .loaded-hint /
        .lower-block / @media (max-width: 1399px) / @media (max-width: 1199px)  True
```

## 决策项落实（§5）

- 抽屉默认收起：`index.html` 的 `#drawer` 无 `open`、`aria-hidden="true"`，
  `state.drawerOpen = false`。
- 抽屉位置：左侧；宽屏是 `.workspace` 的 grid 一列（`380px`），
  `< 1200px` 变 `position: fixed` 覆盖式（`transform` 滑入），不是模态。
- 回填时机：自动 + 就地提示（`#designer-loaded-hint`），手填字段跳过。
- 断点：`1400px` 叠列、`1200px` 抽屉改覆盖式。
- 模式切换不清空字段：`state.values` 跨模式保留（`renderDesigner()` 只重画控件）。
- 最近作业摘要：进度条右侧 `#designer-recent`，显示
  `<kind> · <status> · <耗时>`，点击展开并滚动到 `#designer-log-wrap`。

## 未做项

- 无任务项遗漏。P0-0 ~ P0-4 全部完成。
- 任务禁止的项（全基因组搜索、建索引、全量测试套件、改前置测试）按约定未做。

## 附带发现（不在本次范围，未修）

- `webapp/services/dataprep.py:457-479` — 只用 `prefix` 调 `build-index` 时
  `output_dir` 为空串，`outputs` 里就只会有 `index_path`（`set_outputs()` 会丢掉
  不存在的空值）。这与任务 1.4“只包含存在的路径”一致，但若以后要求
  `build-index` 恒有 `output_dir`，需要额外约定；本次未改前端/后端行为。
- `tests/test_webapp.py:581` 的用例名仍叫
  `test_index_page_has_the_four_tabs`，断言的是四个字符串而非页签，名字已过时。
  按“不要为了迁就新布局去改前置测试”的要求保持原样。
- 子进程的中文日志在 `job.log` / `log_tail` 里是乱码（例如
  `motif (+) ����: TACG`），来自 `shared/` 或 `basic/extract.py` 的 stdout 编码
  与 `jobs.py` 的 `errors="replace"` 组合；前置任务已有，本次未动。
- `webapp/jobs.py:245-247` 会把缺 `kind` 的历史目录（如  `webapp/jobs/87499fe93868/`）整体忽略；因此它对 `/api/jobs` 不可见，
  本次新增的 `outputs` 兼容逻辑对它没有影响。

## 待明确

- 无。若 master 希望“最近作业摘要”显示本地时间而不是 `<kind> · <status> ·
  <耗时>`，或希望抽屉宽度随窗口自适应，请给出规格，我再调。