# 本地网页版（Web 工作台）

网页版默认监听 `0.0.0.0:5000`（局域网内其他机器也能访问），不依赖
CDN 或前端框架。它把桌面的 **Data prep / Models / Pattern Designer** 收进同一个
单页工作区（Designer 是常驻主区，Data prep / Models 是左侧滑出的**近满屏面板**），
并且与桌面端、命令行复用同一套 `shared/` 实现：

- 表单 → `PatternSpec` / `RunnerConfig`：`shared/design/workbench_form.py`
  （桌面 `designer_workbench.py` 与 `webapp/services/designer.py` 共用，两边只
  负责各自的控件，不再各自实现一份映射）；
- 搜索/评分/输出：`shared/design/pattern_runner.py`、`shared/search/*`、
  `shared/scoring/*`、`shared/output/*`。

因此同一组表单值在网页端提交与在桌面端运行得到相同结果。

## 启动

```powershell
python webapp\app.py
```

默认地址（监听所有网卡，端口 5000）：

```text
http://<本机 IP>:5000
```

只允许本机访问：

```powershell
python webapp\app.py --host 127.0.0.1
```

指定端口：

```powershell
python webapp\app.py --port 8765
```

后台常驻与重启（Linux/macOS）：

```bash
bash tools/serve_webapp.sh start     # 默认 0.0.0.0:5000；等首页返回 200 才报成功
bash tools/serve_webapp.sh status    # PID、占用端口的进程、HTTP 状态码、日志路径
bash tools/serve_webapp.sh restart   # 改完代码后换上新代码
bash tools/serve_webapp.sh stop
```

脚本用 `nohup` 起后台进程，PID 写进 `logs/webapp.pid`，输出追加到
`logs/webapp.log`（`logs/` 在 `.gitignore` 内，不进仓库）。`stop`/`restart` 会先结束
**当前占用该端口的进程**：手工 `nohup` 起的老进程没有 PID 文件也能停掉，否则端口被
旧进程占着、新代码会静默不生效。`--host` / `--port` 覆盖默认值，
`PYTHON=/path/to/python` 指定解释器，`WEBAPP_WAIT_SECONDS` 调整启动等待上限。

页面静态资源来自 `webapp/index.html` + `webapp/static/app.js` +
`webapp/static/styles.css`（LF、无 BOM、无外链）；只有 `app.js` 与`styles.css` 这两个文件名在服务端白名单内。

## 单页工作区

页面只有一个常驻主工作区（Designer），`Data prep` 与 `Models` 收进左侧的**近满屏
面板**（默认宽度 `min(1800px, 视口宽 − 48px)`），不再是同级页签，也没有左右双面板：

```text
面板收起（默认）——Designer 占满整屏
┌─ 顶部固定条（sticky）───────────────────────────────────────────────────┐
│ [准备数据/模型] Design Pattern [模式下拉] [Find Targets] [Score & Off-target]│
│ 就绪状态 Ready / Missing: …   进度条   最近作业 <kind> · <status> · <耗时>  │
├───────────────┬──────────────────────────────┬──────────────────────────┤
│ 公共输入       │ Middle（min/max gap 或        │ Right TAM                │
│ （可折叠，默认展开）│ y_sequence）                  │                          │
│ + Left TAM     │ + Structure Preview           │                          │
├───────────────┴──────────────────────────────┴──────────────────────────┤
│ Run Settings（可折叠）                                                    │
│ Run Log（可折叠，默认展开）                                                │
│ 结果表（完整=输出表 / 精简=候选列）+ 表/格式下拉 + 导出按钮                    │
│ Results / Output（可折叠：作业列表、作业详情、输出目录文件列表）                 │
└──────────────────────────────────────────────────────────────────────────┘

面板展开——几乎盖住主区，右侧只留 48px 缝（缝里那块仍可点击，回到 Designer）
┌──────────────────────────────────────────────────────┐ ┌────┐
│ Data prep & Models                              Close│ │ 48 │
│ ── Data prep ─────────────────────────────────────── │ │ px │
│  Download / Genome+annotation / Search scope /        │ │ 主 │
│  Mask gene / Prepare（字段标签在上、控件在下，多列自适应）│ │ 区 │
│ ── Models ─────────────────────────────────────────── │ │    │
│  分组状态与下载/删除                                   │ │    │
│                                    ┌ 拖动条（面板右缘）│ │    │
└──────────────────────────────────────────────────────┘ └────┘
点遮罩 / Close / Esc / 顶部条按钮 → 面板滑出，Designer 的表单值与滚动位置不变
```

- 面板几何：`position: fixed` 从左侧滑入，宽度 `min(1800px, 视口宽 − 48px)`，
  最小 380px，右边缘有拖动条（`role="separator"`，支持方向键，双击复位到默认宽度），
  宽度记在 `localStorage` 的 `crispr.drawerWidth`；打开状态记在 `crispr.drawerOpen`。
- 关闭方式共 4 种：顶部条按钮、面板里的 `Close`、`Esc`、点击面板背后的遮罩。
  面板只是隐藏（`transform` + `visibility`），不重建、不清空，Designer 的滚动位置与
  表单值都保留。
- 面板内的表单用多列自适应：`.drawer .grid` 是
  `repeat(auto-fit, minmax(330px, 1fr))`，每对“标签在上、控件在下”，面板收窄到
  380px 时自动退化成单列。

- 顶部固定条不随滚动消失：模式下拉（三个 `MODE_LABELS`）、`Find Targets`、
  `Score & Off-target`、就绪状态、进度条，以及进度条右侧的
  “最近一次作业”摘要（`<kind> · <status> · <耗时>`，点击跳到下部 Run Log）。
- 顶部条另有两个入口（NAR `:138` / `:139`）：`Load sample data` 调 `GET /api/sample`，
  把 `sample_data/` 的示例基因组、示例目标 FASTA 与 `NGG` / 20 / downstream 等表单值
  填进 Designer（只填值、不自动运行，重复点击幂等）；`Help` 链接指向 `/help`。
- 主区三列：左 = 公共输入（可折叠，默认展开）+ Left TAM；中 = Middle + Structure
  Preview；右 = Right TAM。
- 下部常驻：Run Settings、Run Log、结果表与导出控件、`Results / Output`
  的内容（作业列表、作业详情、输出目录文件列表）都在页面下部，不折叠掉。
- 模式切换导致的字段显隐规则与桌面端一致（`designer_workbench.py:737-880` 的三种
  布局），切换模式**不清空**已填字段。
- 响应式：视口 < `1400px` 时三列纵向堆叠（顺序：公共输入/Left → Middle+预览 →
  Right）。所有视口上面板都是同一套行为（宽度 = 视口宽 − 48，最小 380px），不再是「宽屏并排 / 窄屏覆盖」的二分；面板不是模态弹窗，关闭后 Designer 的状态不变。

Designer 的三种 pattern 与桌面端一致：

- `SINGLE_MOTIF_FLANK`：Single target design，
- `MOTIF_GAP_MOTIF`：Paired-target design Pattern A: Target-xbp-Target，
- `Y_CENTERED_MOTIFS`：Paired-target design Pattern B: Target-xbp-Motif-ybp-Target。

- 每侧的 On-target / Off-target 模型控件是**多选**（Ctrl/Cmd-click 多选，第一个选中项是
  primary）：选项文本用 `shared/design/workbench_form.py:model_display_name` 的显示名
  （`[Cas9] cropsr`、`[Cas9] [rule] cfd`），由 `/api/schema` 的 `model_labels` 下发，
  网页不另存一份、不自己拼前缀；用户改动后 primary 项的选项文本加 `[P] ` 前缀，hint 追加
  `Primary: …`（与桌面 `designer_workbench.py` 的 picker 同义）。表单值仍是逗号分隔的
  注册表 key 串（`split_model_selection` 解析）。

`Find Targets` 只跑抽取阶段（`start=0, end=1`），`Score & Off-target` 从抽取结果
继续（`start=1`），如果没有抽取结果会返回
`Extracted targets not found. Run Find Targets first.`

## 批量（Batch）

`Batch` 区块把一次提交展开成多个单元（unit = 一个 search scope × 一份 pattern 配置）并串行跑完 `PatternRunner`；内核、manifest 与汇总契约见 `docs/BATCH.md`，这里只讲 web 入口。

流程：填 `Batch label`（留空则用 `web-batch-<YYYYmmdd-HHMMSS>`）→ `Add scope` 加若干范围（`scope_id` 可留空，服务端按文件名去后缀派生；路径可用 Browse）→ 每个 scope 行的 `Mask` 列默认勾选 `Same as scope`，取消勾选后可键入或 Browse 一个独立 mask FASTA → 在 Designer 里配好 pattern，`pattern id` 可留空（此时使用当前 Designer pattern 的默认名，输入框 placeholder 会显示该名字）或显式填写 → 在 `Add current Designer pattern` 旁边的 `Applies to` 勾选框里勾选这个 pattern 要覆盖的 scope（默认全选；勾选框名即该 scope 的有效 `scope_id`，`scope_id` 留空时按文件名去后缀显示）→ 点 `Add current Designer pattern`（把**当前 Designer 表单**原样快照成该 pattern 的配置，并带上刚才勾选的 scope）→ 添加后仍可在 Patterns 表的 `Applies to` 列增删 scope → `Preview units` → `Run batch`；日志/进度走同一 JobManager，产物可下载。

payload 字段（`POST /api/batch/preview` 与 `POST /api/batch/jobs` 共用）：

- `batch_label`（可选）、`run_id`（可选，复用已有运行编号）、`resume`（可选布尔，默认 true）。
- `scopes`（必填、非空）：每项 `{scope_id?, search_fasta}` 或 `{scope_id?, regions}`，可再带 scope-owned 的 mask：`mask_same_as_target?`（默认 `true`，用该 scope 的有效 search FASTA 自掩码）或 `mask_fasta?`（显式 mask，与 `mask_same_as_target` 互斥）。序列 scope 的默认 mask 是 `search_fasta`，BED scope 的默认 mask 是从 `regions + genome_fasta` 抽出的 window FASTA。
- `patterns`（必填、非空）：每项 `{pattern_id?, mode, overlay}`，或直接给一份 Designer 表单快照（`mode` + `values` + `struct` 键），服务按该 mode 的 schema 字段切出 overlay。省略 `pattern_id` 时按 `docs/BATCH.md` 的默认命名规则生成；自动名撞车追加 `_2`、`_3`，显式重复仍报错。
- `assignments`（UI 路径）：`{pattern_id: [scope_id, ...]}`；由 `Applies to` 勾选框生成，某 pattern 缺省 → 指派给全部 scopes。想表达 `ab用1, c用2` 就是 pattern 1 只勾 a/b、pattern 2 只勾 c，预览会得到 `a__1`、`b__1`、`c__2`。
- `groups`（高级路径）：给了就直接用（忽略 `assignments`）。
- 顶层也可带当轮 Designer 表单值（与 `/api/designer/jobs` 的 `values` 同义），服务把非 pattern 键放进 `shared`。

转换规则：`shared` 只收 `COMMON_FIELDS + RUN_FIELDS + pair_rank_*`（去掉 `search_fasta`/`bed_regions`/`mask_fasta`/`mask_same_as_target`/`result_label`）加 `struct` 键；pattern 的 `overlay` 只收该 mode 的 pattern 键加 `struct`/`side_*` 键。保留键（`search_fasta`/`bed_regions`/`input_mode`/`result_label`/`output_dir`/`mask_fasta`/`mask_same_as_target`）出现在 `shared`/`overlay` 会直接报错；每个 scope 的 mask 独立留在自己的 `ScopeSpec` 上，不进入批次级 `shared`。

units 顺序：`assignments` 生成 **每个 pattern 一个组**（`group_id = G_<pattern_id>`，顺序同 `patterns`），所以 UI 路径下是 **pattern 主序 → scope 次序**（与 CLI 示例的 scope 主序不同）。

产物与取消：批次根目录仍是 `output/<YYYYMMDD>-<ID>/（提交时分配运行编号，规则见 `docs/BATCH.md`「运行编号」）`；作业结束后把 `manifest.tsv` 与 `batch_scores.tsv`（来自 `summary/batch_scores.tsv`）复制到 `<job_dir>/export/`（含 `manifest.tsv`、`batch_scores.tsv`、`run.log`、`run.json`） 供下载。`Cancel job` 调 `BatchRunner.stop()`：当前 unit 的 `PatternRunner` 被停、整批返回 130。

页面 Batch 区块顶部新增「Task code (Run id)」小组：跑完一次 batch 会显示并填入本次任务码（一次 batch 共享同一个码），可点 `Copy` 复制；输入任意任务码（`20261006-0114` 或四位 `0114`）点 `View` 查看那一次运行的 batch label、路径、unit 状态统计与可下载文件；查看时会像刚跑完一样把结果表（按 manifest 填 `unit_id`/`scope_id`/`pattern_id`/`status`/`returncode`）和下方导出按钮按该次运行重新填满，点 `Recent runs` 列出最近 20 次运行。

## 面板：Data prep / Models

- 面板默认收起；展开时从左侧滑入并覆盖主区（几何与 4 种关闭方式见上）。
- 内容顺序与桌面端一致：先 `Data prep`（下载、基因组/注释、Search scope、
  Mask gene、Prepare/BLAST/索引），后 `Models`（分组状态与下载/删除）。
- 面板里的作业与主区共用同一个作业队列（同一时刻最多 1 个重作业），日志与进度
  显示在面板内的作业框中；面板收起也不影响作业继续运行。
- 回填后的「已带入」提示同时出现在**两处**：主区的 `#designer-loaded-hint` 与面板内的
  `#dp-loaded-hint`（面板打开时主区那行被盖住）。两处文案与 tooltip 完全一致，由
  `webapp/static/app.js` 的同一段拼串生成，不存在第二份规则。
- 面板内的字段排布：每组 `.grid` 用 `repeat(auto-fit, minmax(330px, 1fr))`，
  每对「标签在上、控件在下」，面板收窄到 380px 时自动退化成单列。
- Models 面板每行在 `Path` 之后显示该模型的 `description`，文本直接来自
  `shared/scoring/model_registry.py` 的 `MODELS[key]["description"]`（唯一来源，网页不翻译、
  不另存）；没有本地文件的模型（如 `teep`）在 `Path` 列显示其 `url`
  （对齐 `main.py:1170-1173`）。

### 回填规则

抽屉里任一作业成功后，页面用该作业的 `outputs`（见下）回填**主区**的空白字段，
等价于桌面端 `unified_gui.py:249-298` 的 `_designer_defaults()`：

| `outputs` 键 | 回填位置 |
| --- | --- |
| `genome_fasta` | 主区 `genome_fasta` |
| `annotation` | 主区 `annotation`（注释 GFF3，决定 `Annotation` 等四列） |
| `target_fasta` | 主区 `search_fasta` |
| `mask_fasta` | 主区 `mask_fasta`（勾选 `skip_mask` 时不回填，留空） |
| `blastdb` | 主区 `blastdb` |
| `index_path` | 主区 `index_path`（Run Settings 内） |

- **只填空字段**：值为空则跳过；用户已经手填（主区输入框或抽屉输入框）的字段一律
  不覆盖，不允许静默带参。
- 回填后就地在公共输入区显示一行提示，例如
  `已带入 / Loaded: genome_fasta, search_fasta`；鼠标悬停可看到具体
  路径，被跳过的字段以 `· kept your values: …` 标出。
- 字段对应关系与判定逻辑只有一份实现（`webapp/static/app.js` 的
  `backfillPlan()`）。
## 作业模型

- 作业目录：`webapp/jobs/<job_id>/`（`job_id` 形如 `^[a-z0-9-]{12}$`），包含
  `params.json`、`status.json`、`job.log`、`out/`、导出时的 `export/`。
- 全局最多 1 个重作业运行，其余排队（基因组级搜索/建索引内存占用大）。
- 状态：`queued` → `running` → `succeeded` / `failed` / `cancelled`；
  服务重启后遗留的 `queued` / `running` 作业会被标为 `interrupted`（并显示
  “已中断”文案），不会谎报仍在运行；`webapp/jobs/87499fe93868/` 这类旧实现留下
  的目录（`status.json` 缺 `kind`）被新实现忽略，也不会被改写。
- `CONFIRM_REQUIRED` 请求默认自动同意，并在日志中写 `[auto-confirm] <kind>|<reason>`。
- 进度来自子进程的 `PROGRESS:` / `PROGRESS_TARGET:` 行，页面用
  `/api/jobs/<id>/log?offset=` 增量拉取日志并显示 `Analyzing target i/n`。
- 导出写入 `<job_dir>/export/<文件名>`，再通过
  `/api/jobs/<id>/download?file=export/<文件名>` 下载；浏览器不写任意本地路径。
- 结果表有两种视图，导出与页面显示的表格始终一致（所见即所得）：

  | `Table` | 数据源 | 列 | 可用格式 |
  | --- | --- | --- | --- |
  | `Full (output table)`（默认） | 本次运行落在 `<output_dir>` 的交付表（`<label>_scores.tsv`，Y-ZBP 为 `<label>_scores.sorted.tsv`），取自 `GET /api/jobs/<id>/results` | 文件原样的全部列与列序（含 `query_seq`、评分列、注释列） | `csv` / `tsv` / `xlsx` |
  | `Concise (candidates)` | `read_extract_candidates()` 的候选行，隐藏 `query_seq` / `gap_seq`（历史行为） | 候选列 | 全部 `SUPPORTED_FORMATS` |

  `Full` 与 `output/<label>_scores.tsv` 逐列逐行相同，导出文件名以 `_results_`
  区分（例如 `<label>_results_<时间戳>.csv`）；尚未跑 `Score & Off-target`
  （没有 `scores` 产物）时自动回落到 `Concise` 并在表上方说明。
  用户手动改过 `Table` 后按用户选择，不再自动切换。
- `status.json` 带 `"outputs": {<键>: <绝对路径>}`（无产物时为 `{}`），
  `GET /api/jobs` 与 `GET /api/jobs/<id>` 都会返回该字段；旧作业目录缺这个键时
  读接口按 `{}` 补上，不写回文件。各作业写入的键：

  | 作业 | `outputs` |
  | --- | --- |
  | `dataprep.download` | `genome_fasta`、`annotation`、`output_dir` |
  | `dataprep.prepare` | `genome_fasta`、`annotation`、`target_fasta`、`mask_fasta`、`output_dir`，有则加 `blastdb` |
  | `dataprep.extract-target` | `target_fasta`、`output_dir` |
  | `dataprep.extract-mask` | `mask_fasta`、`output_dir` |
  | `dataprep.build-blastdb` | `blastdb`、`output_dir` |
  | `dataprep.build-index` | `index_path`、`output_dir` |
  | `designer.find` / `designer.score` | `search_fasta`（sequence 模式）或 `bed_regions`（bed 模式）、`output_dir`、`extract_output`、`run_dir`、`params_file`，有则加 `scores` / `guides` / `offtargets` / `blast_results` |

  只写绝对路径，且只写实际存在的产物（`build-index` 的前缀按其
  `<prefix>.ggi` / `<prefix>.json` 兄弟文件判断）。`result` 里的 `run_dir` /
  `params_file` / 交付文件键同样只写存在的路径；`run_dir` 是本次运行子目录，
  未填 run-label 时等于 `output_dir`。

## API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/` | 单页外壳（`webapp/index.html`） |
| `GET` | `/static/<app.js\|styles.css>` | 白名单静态资源 |
| `GET` | `/help`、`/help/tutorial` | 把 `docs/help_en/index.md` / `tutorial.md` 渲染成 HTML（标准库最小 Markdown，不引外部依赖）；文件缺失返回 404 |
| `GET` | `/help/sample_output/<file>` | 以 `text/plain` 返回 `docs/help_en/sample_output/` 下已存在的文件（只放行该目录） |
| `GET` | `/api/schema` | 表单选项：pattern、预设、引擎、模型分组、模型显示名 `model_labels`、Data prep 选项等（全部来自 `shared/`） |
| `GET` | `/api/jobs` | 作业列表（新的在前，含 `outputs`） |
| `GET` | `/api/jobs/<id>` | 作业状态、进度、`log_tail`、`result`、`outputs` |
| `GET` | `/api/jobs/<id>/log?offset=N` | 从第 N 个字符起的日志增量 |
| `GET` | `/api/jobs/<id>/candidates` | Designer 候选表（隐藏 `query_seq` / `gap_seq`） |
| `GET` | `/api/jobs/<id>/results` | 本次运行的交付表（`outputs.scores`，即 `output/<label>_scores.tsv`）：`{columns, rows, total, available, file}`；无产物时 `available=false` |
| `GET` | `/api/jobs/<id>/download?file=export/...\|out/...` | 下载作业内的白名单文件 |
| `GET` | `/api/models` | 模型分组、状态、路径、`description`、`url` |
| `GET` | `/api/outputs?dir=<绝对路径>` | 列出目录内允许扩展名的文件 |
| `GET` | `/api/fs/list?dir=<绝对路径>&kind=<kind>&hidden=1` | 只读列目录（kind 过滤、strip 剥离表、roots 根模式；`hidden=1` 才列隐藏项） |
| `GET` | `/api/sample` | 示例数据入口：仓库相对路径（`sample_data/demo_genome.fa`、`sample_data/demo_target.fa`、`sample_data/demo_batch.json`）加该样本的 Designer 表单值（mode、motif/flank/side、nuclease、run 值）；文件缺失返回 404，不 500 |
| `POST` | `/api/designer/preview` | 描述当前 pattern、返回 `errors` / `warnings` / `pattern_name`（不可用时为空串） |
| `POST` | `/api/designer/preset` | 单个 TAM 侧的系统预设：返回字段更新（含运行级 `nuclease`）和模型候选；页面选中预设即调用（不改变 `Use for Run` 生效侧），`Apply` 按钮用于重复应用并切到该侧 |
| `POST` | `/api/designer/active-side` | `Use for Run`：切换生效侧并返回规则更新 |
| `POST` | `/api/designer/jobs` | 提交 Designer 阶段（`stage`: `find` / `score`） |
| `POST` | `/api/batch/preview` | 预览批量：返回 `batch_label`、`batch_root`（预览时为输出目录，提交后为当次运行目录）、`units`、`errors`、`warnings`（缺文件降级为 warning） |
| `POST` | `/api/batch/jobs`（响应含 `run_id`） | 提交批量作业（kind=`batch`）；校验失败返回 400 |
| `GET` | `/api/batch/runs?limit=&day=` | 最近的批量运行（一次 batch = 一个任务码），每条含 `run_id`、`batch_label`、`unit_count`、`units`、`created`、`path`、`files` |
| `GET` | `/api/batch/runs/<run_id>` | 按任务码查看一次运行；`<run_id>` 可用 `20261006-0114`，也可用四位 `0114`（跨天取最近一天）；返回 `units` 统计、`columns`+`rows`（manifest 结果表）与 `files`；找不到返回 404 |
| `GET` | `/api/batch/runs/<run_id>/download?file=<相对路径>` | 下载该运行目录内的文件（`manifest.tsv`、`summary/batch_scores.tsv`、`run.log`、`run.json` 等）；路径越界或非法返回 400 |
| `POST` | `/api/dataprep/download` | 下载基因组与注释 |
| `POST` | `/api/dataprep/prepare` | 基因组 + 注释 + Search scope + Mask 一步准备（不再自动建 BLAST 库，需要时用 `build-blastdb`） |
| `POST` | `/api/dataprep/extract-target` | 抽取 Search scope FASTA |
| `POST` | `/api/dataprep/extract-mask` | 抽取 Mask FASTA |
| `POST` | `/api/dataprep/build-blastdb` | 构建 BLAST 库 |
| `POST` | `/api/dataprep/build-index` | 构建基因组索引 |
| `POST` | `/api/models/<key>/download` | 下载模型权重 |
| `POST` | `/api/models/<key>/delete` | 删除模型本地文件 |
| `POST` | `/api/jobs/<id>/cancel` | 取消作业 |
| `POST` | `/api/jobs/<id>/export` | 导出选中行（`format`、`rows`、`filename`、`columns`）；`columns=concise` 为候选列（历史行为），`columns=full` 写出 `results` 交付表，仅支持 `csv` / `tsv` / `xlsx` |

表单校验失败返回 `400` + `{"error": "..."}`，路径或文件不存在返回 `404`。

## 路径浏览选取器

网页版里所有路径字段要的都是**服务端绝对路径**，而浏览器原生控件给不出来：
`<input type="file">` 只给文件名，File System Access API 的 `showDirectoryPicker()`
只给文件句柄。所以这里既不用原生文件框、也不做上传（上传还会把几十 GB 的基因组
再复制一份、后续路径指向副本）。浏览由服务端的只读列目录接口
`GET /api/fs/list` 加页面内自绘的弹层完成。

字段与 `kind` 的对应关系：

| 字段（key 或元素 id） | kind | 位置 |
| --- | --- | --- |
| `search_fasta` | `fasta` | Common Inputs |
| `bed_regions` | `bed` | Common Inputs（BED 模式） |
| `genome_fasta` | `fasta` | Common Inputs |
| `mask_fasta` | `fasta` | Common Inputs |
| `blastdb` | `db` | Common Inputs |
| `annotation` | `annotation` | Common Inputs |
| `index_path` | `index` | Run Settings |
| `dp-download-output` | `dir` | Data prep 抽屉 |
| `dp-genome` | `fasta` | Data prep 抽屉 |
| `dp-annotation` | `annotation` | Data prep 抽屉 |
| `dp-output` | `dir` | Data prep 抽屉 |
| `dp-blastdb` | `db` | Data prep 抽屉 |
| `dp-index-prefix` | `index` | Data prep 抽屉 |
| `outputs-dir` | `dir` | Results / Output |

`kind` 只决定列表里出现哪些**文件**，目录永远列出（`dir` 例外：它把文件全滤掉）。
`fasta` / `annotation` / `bed` / `db` / `index` 按 `shared/` 认得的后缀匹配，
`any` 不过滤；列表先目录后文件，各组按名字小写升序。

弹层的行为（资源管理器式，只有一份实现，所有路径字段共用）：

- 每个路径字段旁的 `Browse...` 按钮打开同一个弹层（`#picker`）。
- 打开时起始目录依次尝试：字段当前值 → 它的上一级 → 上次用过的目录
  （`localStorage['crispr.pickerDir']`）→ `home` → 根模式；前面的候选不是目录就
  静默跳过，第一次打开不会白屏。字段为空时没有「当前目录」可定位，于是跳过
  `home`、直接落到根模式（列表上方的盘符按钮；`Home` 在位置栏里始终可点，
  见下）。确认成功后才记住当前目录（同时 push 进 `crispr.pickerRecent`，
  去重、只留最近 5 条）。
- 打开后若字段当前值能在列表里对上号（`db` / `index` 存的是前缀，按
  `prefix.nin` / `prefix.ggi` 这类成员文件反查），那一行会被选中并滚动到可见处。
- 路径行下方是面包屑 `#picker-crumbs`（`>` 分隔、每段可点、末段即当前目录）；
  地址栏 `#picker-path` 保留，回车或 `#picker-go` 列举手输路径，`#picker-up`
  上一级，`#picker-back` / `#picker-forward` 走历史（最多 50 条，无历史时置灰）。
  `#picker-roots` 仍是根模式的盘符按钮，`#picker-places` 是位置栏
  （`Home` + 最近 5 个目录）。
- 列表有列头 `Name` / `Size` / `Modified`（排序固定：先目录后文件、各自按名字
  小写升序，表头不可点）；列表上方右侧 `#picker-count` 显示条目数
  （`3 folders, 12 files`，被截断时追加 ` (listing truncated)`）。
- 单击行 = 选中，双击目录 = 进入，双击文件 = 直接确认；`#picker-ok` 确认，
  `#picker-cancel` / `#picker-close` / `Esc` / 点遮罩取消且字段值不变。
  键盘：↑/↓ 移动选中（到顶/到底停住，不循环）、`Enter`（选中目录则进入、
  选中文件则写回）、`Backspace` 上一级、`Esc` 关弹层；焦点在地址栏时只处理
  `Esc`（那里的 `Enter` 是「列举这个路径」）。
- 文件类 kind 没有选中行时 `#picker-ok` 置灰、`#picker-selected` 显示
  `Select a file`；`dir` 类字段的 `OK` 始终可用，无选中时写回**当前正在浏览的
  目录**，也可以点 `Use this folder`（`#picker-here`，只对 `dir` 类字段显示）。
- 确认永远有回应：可确认时写回并关闭；没有可确认的对象（正在列举、列举失败、文件类字段还没选中行）时弹层保持打开，并把原因写进 `#picker-selected`，不会出现点了 `OK` 毫无反应的情况。
- 弹层高度受窗口限制（`min(80vh, 100vh - 60px)`），只有列表 `#picker-list` 会伸缩并自带滚动；`OK` / `Use this folder` / `Cancel` 一行始终留在弹层内，不会被挤到窗口外（窗口很矮时列表收缩到 0 也不外溢）。
- 确认时按 `strip` 剥后缀：`db` 字段要的是 BLAST 库前缀（`blastn -db <prefix>`，
  成员为 `<prefix>.nin` / `.nsq` 等，侧车为 `<prefix>.source.json`），所以剥掉
  `.source.json` / `.nin` / … 后写回；`index` 字段要的是索引前缀
  （`<prefix>.ggi` + `<prefix>.json`），剥掉 `.ggi` / `.json`。其它 kind 的 `strip`
  为空表，原样写回。剥离表由服务端下发（响应里的 `strip`，已按长度降序排好），
  前端命中即返回，只剥一层。
- 写回方式和手输完全一致：`input.value = picked` 后派发 `input` 事件，
  这样 `state.values` 与预览都会同步更新。
- 默认不列隐藏项：名字以 `.` 开头、或（Windows）带隐藏属性的条目由服务端过滤掉；
  勾选 `Show hidden`（`#picker-hidden`，记忆在 `localStorage['crispr.pickerHidden']`）
  后带 `hidden=1` 重新列举当前目录才会出现。
- 弹层 `z-index` 高于 Data prep 抽屉（抽屉里也能打开它）；抽屉自己的 `Esc`
  处理会先判断弹层是否打开，所以 `Esc` 只关弹层、不关抽屉。

## 安全边界

- 服务默认绑定 `0.0.0.0`（所有网卡，端口 5000）；如需限制本机访问，
  用 `--host 127.0.0.1`。对外暴露时请自行确认网络与防火墙策略。
- 静态资源与下载文件均使用白名单；下载路径再做一次 `commonpath` 校验，
  `..`、绝对路径和未知扩展名都会被拒绝。
- `job_id` 只允许 `[a-z0-9-]{12}`。
- `/api/fs/list` 只读：只返回名字、大小与修改时间，不读文件内容、不写盘；
  `dir` 必须是已存在的目录（否则 `400`）。
  隐藏项（`.` 开头或 Windows 隐藏属性）默认不列出，`hidden=1` 才会带上。
- 子进程通过参数列表调用，不经过 shell。
- 页面只使用原生 JS 与 `fetch`，无 CDN、无构建步骤、离线可用。
