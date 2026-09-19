# 核验报告：webapp-single-page-layout

- round: 1
- verdict: **pass**
- updated: 2026-09-16 18:45
- 依据：`report.md`（round 1）+ `backup/20260916_webapp_single_page/` + master 自建探针
  `assets/master_verify_backfill.js` 与自跑端到端（HTTP job `2fdc86d48be2` / `fcb663997976`）

## 逐条核验

| 任务项 | 结论 | 证据 |
| --- | --- | --- |
| P0-0 | 通过 | `docs/handoff/webapp-designer-port/state.json` = `ready_for_review`；`shared/design/workbench_form.py`(24145 B)、`webapp/jobs.py`(15617 B)、`schema.py`(14383 B)、`services/{designer,dataprep,models}.py`、`static/{app.js,styles.css}` 均存在；我的端到端跑通了 `services/designer.py` → `workbench_form` → `PatternRunner` 全链路 |
| P0-1 | 通过 | 代码：`webapp/jobs.py:55`(STATUS_FIELDS)、`:107`(JobContext.outputs)、`:169-193`(`_resolve_output` 只收存在的路径 + `<prefix>.*` 兄弟判定)、`:195-203`(`set_outputs` 过滤后写 status.json)、`:241-249`(`read_status` 用 `setdefault` 且不回写)、`:316`(create_job 初值 `{}`)；`services/dataprep.py` 6 处写入(339/377/402/431/448/476)、`services/designer.py:246-251`。我自己的作业：`GET /api/jobs/fcb663997976` → `outputs={"search_fasta":…,"output_dir":…,"extract_output":…}`，三个路径 `Test-Path` 全 True，且 `webapp/jobs/fcb663997976/status.json:12-16` 已持久化；旧作业 `d32ec809fc08` 的 `status.json` 里**没有** `outputs` 键而 API 返回 `{}`，证明兼容读法没有回写文件；servant 的 dataprep 作业 `e8de2d324141` 的 `outputs.target_fasta` 经我 `Test-Path` 属实 |
| P0-2 | 通过 | `GET /` → HTTP 200(9311 B)，含 `id="drawer"` / `id="workspace"` / `id="candidates-block"` / `id="designer-loaded-hint"` / `class="topbar"` / `class="designer-columns"` / `class="lower-block"`，`role="tablist"` 为 False；`rg 'switchPanel\|initTabs\|data-panel'` 无命中；`styles.css:394-395`(1399px 叠列)、`:399-422`(1199px 固定定位覆盖式抽屉，`transform` 滑入且后面的 `visibility: visible` 覆盖掉前一行的 `hidden`，窄屏可用) |
| P0-3 | 通过 | 我自写探针 `node docs/handoff/webapp-single-page-layout/assets/master_verify_backfill.js` → 16/16 PASS（从 `app.js` 现场抽取 `backfillPlan`/两张映射表/`cleanText`，不含任何副本逻辑），覆盖 8 条字段映射、`annotation` 只进抽屉、主区手填不被覆盖、**抽屉手填阻止主区写入**（servant 后补的联合判定）、`skip_mask`、空值跳过、未知键 `ignored`；DOM 接线：`app.js:941` 在作业成功后调 `applyJobOutputs`，`:415` 回填后 `renderDesigner()` 重绘，hint 元素 id 与 HTML 一致 |
| P0-4 | 通过 | `docs/WEBAPP.md` 含单页工作区描述(5)、抽屉章节(81-88)、回填表(92-108)、`已带入 / Loaded:` 文案(108)、`outputs` 说明；`README.md:30` 已改为“本地 Web UI：单页工作区（Designer 主区 + 数据准备抽屉）”；`README.md:97` 启动命令未变 |

## master 独立验证

- 变更范围（mtime 扫描 2026-09-16 15:58 之后，排除 `backup/`、`docs/handoff/`、`webapp/jobs/`、`__pycache__`）：仅
  `webapp/jobs.py`、`webapp/services/{dataprep,designer}.py`、`webapp/index.html`、
  `webapp/static/{app.js,styles.css}`、`docs/WEBAPP.md`、`README.md` — 与报告改动清单逐项吻合；
  `shared/**`、`tests/**`、`main.py`、`unified_gui.py`、`designer_workbench.py`、
  `requirements-windows.txt`(mtime 2026-09-07) 均未被触碰。
- 基线比对：`backup/20260916_webapp_single_page/`(16:00:34) 内 8 个文件与当前全部 `DIFF`，
  说明快照确实是改前状态而非改后；快照体积与报告 P0-0 的改前尺寸逐字节一致
  (`jobs.py` 15617、`dataprep.py` 19332、`designer.py` 13208、`app.js` 40394、
  `styles.css` 6190、`index.html` 7530、`docs/WEBAPP.md` 5795)。
- 探针：见 P0-3。另用 `curl.exe` 自造请求复现（我第一版 `-d` 的 JSON 转义写错，服务端按默认值
  回落成 `csv`，属**我探针的缺陷**；改用 `--data-binary @file` 后正常）：
  `format=tsv` → `{"written":1,"file":"export/SpCas9_target_candidates_20260916_183728.tsv","format":"tsv"}`；
  `format=nope` → HTTP 400 `Unsupported export format: nope (choose from csv, tsv, fasta, bed, xlsx, unique_guides, library)`；
  空选择 → HTTP 400 `No candidate rows selected for export`；下载链接 → HTTP 200 且内容是导出的 TSV；
  白名单：`?file=../../main.py` 与 `?file=evil.tsv` 均 HTTP 400 `file is not in the download whitelist`。
- 端到端：自造 2 行 FASTA + `example/engine_benchmark/synthetic_genome.fa`，`POST /api/designer/jobs`
  (stage=find, single_motif_flank) → `2fdc86d48be2`(无命中，`candidates.total=0`)；含 motif 的 fixture →
  `fcb663997976`(`total=1`，`query_id=uniq_0 … positions_json`)，`extracted_seqs.tsv` 内容正确。
- 测试：`python -m unittest tests.test_webapp tests.test_workbench_form -v` → `Ran 77 tests in 42.805s / OK`
  （与报告一致，且 `tests/` 未被本任务改动）。
- 离线/无新依赖：`index.html`/`app.js`/`styles.css` 中 `cdn|unpkg|jsdelivr|googleapis|bootstrap|jquery`
  命中数 0；`requirements-windows.txt` 未改。
- 残留限制：本轮没有真实浏览器渲染验证，`renderDesigner()` 重绘后的最终 DOM 观感（抽屉滑入、
  “已带入”提示排版）只有代码级证据，没有截图/像素证据（见新发现 P2）。

## 归属判定（既有失败 vs 本次引入）

- 中文日志乱码（`job.log` 与作业 `message` 里的 `ͳ������`）— **既有**，属前置任务
  `webapp-designer-port` 的范围：`webapp/jobs.py:265,274` 用 `encoding="utf-8", errors="replace"`
  读子进程 stdout，而 Windows 子进程按 GBK 输出。本任务改动清单未触及这两行，I/O 修复归前置任务。
- 我第一版导出探针报出的 `format=csv` — **我探针的 JSON 转义错误**，不是产品缺陷；修正后正常。
- `tests/test_webapp.py` 命名过时、`build-index` 仅给 prefix 时无 `output_dir` — servant 已作为
  “附带发现”上报，我复核属实，归为既有/规格一致，不算本次引入。

## 新发现

- `webapp/jobs.py:265,274`（及 `:303` 的日志文件句柄）— 子进程中文输出乱码，且会污染用户可见的
  `message`/进度文字（我实测 `status=running` 时 `message` 已是 `ͳ������`）。修复方向：spawn 子进程时
  注入 `PYTHONIOENCODING=utf-8`（必要时 `PYTHONUTF8=1`），与 `main.py:139-148` 对
  `add_utrs_to_gff.py` 的处理一致。等级 **P1**（可见性缺陷，不影响结果正确性）。
- `tests/test_webapp.py:581` — 用例名 `test_index_page_has_the_four_tabs` 与单页布局不符
  （断言内容仍是四个字符串，故仍有效）。等级 P2。
- `webapp/services/dataprep.py:457-479` — 只传 `prefix` 调 `build-index` 时 `outputs` 里没有
  `output_dir`（与 1.4“只包含存在的路径”一致，非缺陷）。等级 P2。
- `webapp/services/designer.py:246-251` — 单靶提取产物的列只有 `qid/sequence/positions`，而候选表列
  取自 `PatternSpec.candidate_columns()`，因此 `motif_seq/flank_seq/side/flank_length` 在本例中是空列
  （桌面端同源同表现）。等级 P2，属前置任务的表现，建议在前置任务核验时确认是否为期望。
- 本轮未做浏览器渲染核验（无截图证据）。等级 P2。

## 下一步

- 通过：P0-0 ~ P0-4 全部核验通过，`state.json` 置 `done`，无需返工。
- 建议（按优先级）：
  1. 对 `docs/handoff/webapp-designer-port/`（仍为 `ready_for_review`、`review.md` 仍是空模板）补一次
     正式核验 —— 它的 `report.md` 有 34.6 KB 证据待独立复核；本轮的测试/探针/端到端已顺带覆盖其
     `workbench_form`、候选、导出与白名单部分。
  2. 若需要，把 P1 乱码修复开成一个小任务（规格：`jobs.py` 子进程 env 注入 + 一条用中文输出的最小复现断言）。
  3. 若需要视觉确认，可让 servant 起服务抓一张单页 + 抽屉展开的渲染截图。

---

## 追加（2026-09-16 21:2x，核验完成之后）

本轮的 verdict 保持 `pass`（当时的核验逐条成立），但**核验范围有漏**：只覆盖了回填
**规则**（`assets/probe_backfill_rule.js` 抽函数跑）与 HTTP 契约，**没有**覆盖渲染后的
DOM，导致一个真实回归溜过：

- `renderPattern()` 清空的 slot 容器里，`left` 指向 `#designer-common-col`
  （`app.js:738-742`），而这个容器同时装着静态的 `<details id="common-inputs-wrap">`
  与 `#designer-loaded-hint`（`index.html:152-158`）→ 首次渲染就把它们删掉，
  之后每次 `renderDesigner()` 都在 `renderCommon()`（`app.js:702-703`）抛
  `TypeError: Cannot set properties of null`，**切模式、切输入模式、模型下拉、回填重绘全部冻结**。
- 复现证据（真实 Edge + CDP）与最小修复清单已写入
  `docs/handoff/webapp-big-prep-panel/task.md` §8（P0-0），由后续任务修复。
- 教训（对 master）：涉及“渲染结果”的契约，必须用真实浏览器验证 DOM，
  不能只用“抽出函数 + HTTP 探针”。

state.json 不回到 `needs_rework`（本轮交付物未变，修复已由 `webapp-big-prep-panel` 承接）。