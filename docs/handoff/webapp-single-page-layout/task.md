# 任务：把 Designer 整合进主页（去掉同级页签，Data prep/Models 降为抽屉）

- task-slug: `webapp-single-page-layout`
- round: 1
- master: 本会话（Codex master，工作目录 `R:\songji\programfile`）
- servant: 待指定（另一个 Codex 会话）
- repo: `R:\songji\programfile`
- 前置任务：`docs/handoff/webapp-designer-port/`（**必须先交付并核验通过**）

## 0. 目标与边界

`webapp-designer-port` 交付的版本是「`Data prep` / `Models` / `Designer` /
`Results / Output` 四个**同级页签**」。本任务把它改成**单主页面工作区**：

```text
┌─ 顶部固定条 ───────────────────────────────────────────────────────────┐
│ Design Pattern [模式下拉]   [Find Targets] [Score & Off-target]         │
│                            状态 Ready / Missing: …     进度条           │
├───────────────┬──────────────────────────────┬────────────────────────┤
│ 公共输入(可折叠) │ Middle（min/max gap 或 y_sequence） │ Right TAM             │
│ + Left TAM       │ + Structure Preview                │                       │
├───────────────┴──────────────────────────────┴────────────────────────┤
│ Run Log（可折叠）                                                       │
│ 候选表（隐藏 query_seq/gap_seq） + 导出格式下拉 + 导出按钮                  │
└───────────────────────────────────────────────────────────────────────┘
左侧「准备数据」抽屉按钮 → 展开 Data prep / Models 两块（默认收起）
```

**为什么**（用户已确认此方向）：

1. 桌面端 Designer 是独立窗口，那是 Tkinter 面板的局限，不是设计意图；网页里“再开
   一个窗口”只会带来弹窗拦截与状态共享问题。
2. 桌面端靠 `unified_gui.py:249-298` 的 `_designer_defaults()` 把
   genome/output/blastdb/target/mask 静默带进 Designer。同一页里可以**显示**这次带入，
   出问题时一眼能看出来。
3. `Find Targets` / `Score & Off-target` 是长任务，日志与进度必须常驻可见，不能因为
   切页签就“丢了后台”。
4. 候选表本来就属于 Designer 的循环（设计 → 运行 → 看结果 → 改参数再跑），
   `designer_workbench.py:469-546` 把它和三列表单放在同一窗口里。

**明确不做**：

- 不改 `docs/handoff/webapp-designer-port/` 下的任何文件（那是前置任务的记录）。
- 不改 API 的路径与语义（唯一例外：见 P0-1 新增的 `outputs` 字段）。
- 不改 `shared/**`、`designer_workbench.py`、`main.py`、`unified_gui.py`、
  `tests/test_designer_workbench.py`、`tests/test_workbench_form.py`。
- 不引入前端框架/CDN；仍是原生 JS + CSS，离线可用。
- 不删除任何文件（共享盘的删除/移动常被策略拦截）。

## 1. 契约

### 1.1 冻结的前置契约

`docs/handoff/webapp-designer-port/task.md` 的 §1.4（表单字段与默认值）、§1.5
（Run Settings）、§1.6（预设/切侧/模型下拉）、§1.7（genome gz）、§1.8（进度与
confirm）、§1.9（候选与导出）、§1.2（安全边界）**全部继续生效**；本任务只改布局、
加一个状态字段。开工前必须先读该文件。

### 1.2 主页面布局（本任务的唯一形态定义）

- 顶部固定条（不随滚动消失）：模式下拉（三个 `MODE_LABELS`）、`Find Targets`、
  `Score & Off-target`、就绪状态、进度条。
- 主区三列：左 = 公共输入（可折叠，默认展开）+ Left TAM；中 = Middle + Structure
  Preview；右 = Right TAM。
- 下部常驻：Run Log（可折叠）+ 候选表 + 导出控件。
- 模式切换导致的字段显隐规则不变（`designer_workbench.py:737-880` 的三种布局）。
- 响应式：视口 < 1400px 时三列纵向堆叠（顺序：公共输入/Left → Middle+预览 → Right）；
  候选表与日志始终留在页面下部，不折叠掉。
- 不再存在同级页签；`Results / Output` 的内容（输出目录、结果摘要、输出文件列表与
  下载）并入页面下部；`Data prep` / `Models` 只存在于抽屉中。

### 1.3 Data prep / Models 抽屉与回填

- 抽屉默认收起，展开宽度 ≥ 360px；宽屏时以 CSS grid 增加一列（不覆盖主区），
  视口 < 1200px 时改为覆盖式抽屉。
- 抽屉内容顺序与桌面端一致：先 `Data prep`（对齐 `main.py:1430-1486` 的
  Data preparation、`main.py:1487-1552` 的 Search scope、`main.py:1553-1635` 的
  Mask gene），后 `Models`（对齐 `main.py:1095-1260` 的分组状态与下载/删除）。
- **回填规则**（等价于 `unified_gui.py:249-298` 的 `_designer_defaults`）：抽屉里任一
  作业成功后，用该作业的 `outputs` 填入主区公共输入，且**只填当前为空的字段、值为空
  则跳过**（不得覆盖用户已手填的内容）。字段对应关系：

| `outputs` 键 | 主区字段 |
| --- | --- |
| `genome_fasta` | `genome_fasta` |
| `annotation` | （仅记录，回填抽屉里的注释输入框） |
| `target_fasta` | `search_fasta` |
| `mask_fasta` | `mask_fasta`（`skip_mask` 生效时留空） |
| `output_dir` | `output_dir` |
| `blastdb` | `blastdb` |
| `index_path` | `index_path`（Run Settings） |

- 回填后必须在公共输入区就地显示一行提示，例如
  `已带入：genome_fasta, search_fasta, output_dir`；悬停可看到具体路径。
  **不允许静默带参。**

### 1.4 新增的 `outputs` 状态契约（P0-1）

作业的 `status.json` 增加 `"outputs": {<键>: <绝对路径>}`（无产物时为 `{}`），
`GET /api/jobs/<id>` 与 `GET /api/jobs` 的响应必须带该字段。各作业成功时写入：

| 作业 | `outputs` |
| --- | --- |
| `dataprep.download` | `genome_fasta`、`annotation`、`output_dir`（取自 `download_info.json`，见 `main.py:264-284`） |
| `dataprep.prepare` | `genome_fasta`、`annotation`、`target_fasta`、`mask_fasta`、`output_dir`，有则加 `blastdb` |
| `dataprep.extract-target` | `target_fasta`、`output_dir` |
| `dataprep.extract-mask` | `mask_fasta`、`output_dir` |
| `dataprep.build-blastdb` | `blastdb`、`output_dir` |
| `dataprep.build-index` | `index_path`、`output_dir` |
| `designer.find` / `designer.score` | `search_fasta`（sequence 模式）或 `bed_regions`（bed 模式）、`output_dir`、`extract_output`（等于 `PatternRunner.extract_output_path()`） |

路径一律写绝对路径；产物命名沿用前置任务实现，不要另起新命名。

## 2. 现状证据（master 已核实）

- `docs/handoff/webapp-designer-port/task.md` §3 P0-3 定义的后端文件与 API 表。
- `unified_gui.py:249-298` — `_designer_defaults()`：桌面端的带入规则（本任务 1.3 的
  行为来源）。
- `unified_gui.py:111-122` — 桌面端用 `Open Pattern Designer` / `Open BED Designer`
  两个按钮打开独立窗口；本任务用“单页 + 输入模式单选”取代这两个按钮。
- `unified_gui.py:91-147` — 桌面端三个页签的顺序，是本任务主区分区的参照。
- `designer_workbench.py:400-448` — 公共输入字段；`:469-546` — 三列 + 预览 + 候选表；
  `:571-668` — Run Settings；`:712-735` — Run Log。
- `main.py:1095-1260` — Models 分组/状态/下载/删除的桌面实现。
- 前置交付前提：`docs/handoff/webapp-designer-port/state.json` 的 `status` 应为
  `ready_for_review` 或 `done`；`shared/design/workbench_form.py`、`webapp/jobs.py`、
  `webapp/schema.py`、`webapp/services/*`、`webapp/static/*` 应已存在。

## 3. 必做改动

### P0-0 开工前置检查（必做，先做）

- 读 `docs/handoff/webapp-designer-port/task.md` 与
  `docs/handoff/webapp-designer-port/state.json`。
- 检查前置交付物是否存在：`shared/design/workbench_form.py`、`webapp/jobs.py`、
  `webapp/schema.py`、`webapp/services/designer.py`、`webapp/services/dataprep.py`、
  `webapp/services/models.py`、`webapp/static/app.js`、`webapp/static/styles.css`。
- **若前置未就绪**：不要动任何 `webapp/` 文件；在 `report.md` 顶部写明
  `依赖未就绪：webapp-designer-port 当前 status=<值>`，`state.json` 保持
  `status: assigned` 后停下，等 master 裁决。

### P0-1 `outputs` 状态字段（后端小改）

- 位置：`webapp/jobs.py`（`status.json` 写入与 `GET /api/jobs*` 响应）、
  `webapp/services/dataprep.py`、`webapp/services/designer.py`。
- 期望行为：按 1.4 的表格写入；无产物的作业为 `{}`；`outputs` 只包含存在的路径。
- 证据要求：提交一个 `dataprep.extract-target` 作业，贴 `GET /api/jobs/<id>` 原文，
  `outputs.target_fasta` 必须等于实际写入的 FASTA 路径。

### P0-2 前端改为单主页面 + 抽屉

- 位置：`webapp/index.html`、`webapp/static/app.js`、`webapp/static/styles.css`。
- 期望行为：按 1.2 / 1.3 实现；页签导航整体移除；`Find Targets` 与
  `Score & Off-target` 放在顶部固定条；候选表与 Run Log 常驻下部；抽屉含
  Data prep 与 Models；公共输入区显示“已带入”提示。
- 证据要求：`GET /` 返回的 HTML 含顶部固定条、三列容器、抽屉容器与候选表容器；
  贴出这些标记片段。

### P0-3 回填交互

- 位置：`webapp/static/app.js`。
- 期望行为：抽屉内作业成功后按 1.3 的表格与“只填空字段”规则回填并显示提示行；
  用户手填过的字段不被覆盖；`skip_mask` 勾选时不回填 `mask_fasta`。
- 证据要求：写一个探针脚本放 `docs/handoff/webapp-single-page-layout/assets/`
  （或给出手工步骤原文）：先手填 `output_dir`，再跑一次 `extract-target`，
  验证 `output_dir` 未被覆盖、`search_fasta` 被填入。

### P0-4 文档

- `docs/WEBAPP.md` 改为主页面 + 抽屉的说明（含 ASCII 布局图、回填规则、`outputs` 字段）。
- `README.md:30` 的描述行同步改为“单页工作区（Designer 主区 + 数据准备抽屉）”；
  `README.md:97` 的启动命令不变。

## 4. 不要做的事

- 不要改 `docs/handoff/webapp-designer-port/` 下的文件。
- 不要改 API 路径、请求/响应字段（除 P0-1 的 `outputs`）、状态机取值。
- 不要改 `shared/**`、`designer_workbench.py`、`main.py`、`unified_gui.py`。
- 不要为了“更好看”引入 CSS 框架、icon 字体或任何外链资源。
- 不要把抽屉做成模态弹窗（会挡住正在跑的日志）；宽屏必须与主区并排。
- 不要删除旧文件；不要跑全量测试套件并宣称通过（那是 master 的动作）。
- 不要为了迁就新布局去改前置任务留下的测试；它们必须原样全绿。
- 不要顺手修前置任务遗留的问题，只写进 `report.md` 的“附带发现”。

## 5. 决策项（未确认则按推荐执行）

- 抽屉默认状态 → 推荐：**收起**。理由：Designer 是日常主区，数据准备是一次性动作。
- 抽屉位置 → 推荐：**左侧**，宽屏并排、窄屏覆盖。理由：与三列布局的行文方向一致。
- 回填时机 → 推荐：**自动 + 就地提示**（不是让用户点一次“带入”）。理由：桌面端也是
  自动带入，但要补上可见性；用户已手填的字段跳过。
- 三列折叠断点 → 推荐：`1400px` 叠列、`1200px` 抽屉改覆盖式。
- 模式切换是否清空字段 → 推荐：**不清空**（与桌面端一致，字段保留）。
- 主区是否显示“最近一次作业”摘要 → 推荐：**显示**，放进度条右侧一行
  （`<kind> · <status> · <耗时>`），点击可跳到下部日志。

## 6. 轻量自检（servant 的检验上限）

```powershell
# 1) 语法
python -m py_compile webapp\app.py webapp\jobs.py webapp\schema.py `
  webapp\services\designer.py webapp\services\dataprep.py webapp\services\models.py

# 2) 聚焦单测（前置任务的测试必须仍然全绿）
python -m unittest tests.test_webapp tests.test_workbench_form -v

# 3) 启动并检查主页面结构（另开一个终端）
python webapp\app.py --port 8123
curl.exe -s http://127.0.0.1:8123/ | Select-String -Pattern "drawer","workspace","candidates"
curl.exe -s http://127.0.0.1:8123/api/schema

# 4) outputs 契约：提交提取作业后检查 status.json
#    Search FASTA 自己造 2 行 FASTA；genome 用 example\engine_benchmark\synthetic_genome.fa
curl.exe -s http://127.0.0.1:8123/api/jobs/<job_id>
```

通过标准：2) 全绿；3) 返回 200 且含主区/抽屉/候选表标记；4) 响应里
`outputs.target_fasta` 是真实存在的绝对路径。**不要**跑全基因组搜索或建索引。

## 7. 交付要求

- 改前把受影响文件快照到 `backup\20260916_webapp_single_page\`（至少
  `webapp\index.html`、`webapp\static\app.js`、`webapp\static\styles.css`、
  `webapp\jobs.py`、`webapp\services\dataprep.py`、`webapp\services\designer.py`、
  `docs\WEBAPP.md`、`README.md`）。
- 完成后：`state.json` 置 `ready_for_review`；`report.md` 写改动文件 + 行号、
  第 6 节每条命令的原文与输出、未做项、附带发现、待明确项。
- 不要修改本 `task.md`。
