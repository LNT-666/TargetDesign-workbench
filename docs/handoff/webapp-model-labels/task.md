# 任务：网页版模型选择器显示对齐 GUI（多选语义不变）+ Models 面板补模型描述文本

- task-slug: `webapp-model-labels`
- round: 1
- status: assigned
- updated: 2026-09-17 11:10
- master: codex-master（repo R:\songji\programfile, 2026-09-17）
- servant: codex-servant
- repo: R:\songji\programfile
- 起始快照：`backup/20260917_webapp_model_labels/`（**由 servant 开工前创建**，见 §7）
- 前置任务（已核验）：`webapp-designer-port`、`webapp-single-page-layout`、`webapp-big-prep-panel`、`webapp-file-picker`

**servant 开工前必读**：本文件全文 + `docs/WEBAPP.md` 的「单页工作区」「API」两节。前置任务已生效的形态契约（单页工作区、抽屉几何、字段 key、回填规则、作业模型、文件选取器）本任务**一律不动**。

## 0. 用户原话与 master 结论

用户原话：

1. 「在网页版本中，选择模型的下拉菜单中能否进行多选？如果能，那应该是显示错误？」
2. 「同时，让每个模型的描述文本与 gui 版本同步在一个文件中」

master 结论（已定，不再讨论方案）：

1. **多选是规格内行为，不是功能 bug。** 依据：网页端移植规格 `docs/handoff/webapp-designer-port/task.md:97`（侧模型行 = 多选）、桌面端 `docs/GUI.md:41-48`、`README.md:225-238`；桌面端同类控件也是多选（`designer_workbench.py:56-220` 的复选框弹层，`:193-209` 标 primary）。
2. 用户看到的「像显示错误」是**显示层与 GUI 不一致**：网页用原生 `<select multiple size=2..5>`，选项文本是**裸注册表 key**（`cropsr`），而桌面显示 `model_display_name()` 的 `[Cas9] cropsr` / `[Cas9] [rule] cfd`，并标出 primary。→ 本轮把网页端**文本**对齐桌面端；多选语义、表单值格式、控件类型保持不变。
3. 「每个模型的描述文本」= 桌面 Models 页每行下方的 `description`（`main.py:1174-1176`；文本来自 `shared/scoring/model_registry.py:29-142` 的 `MODELS[key]["description"]`）。网页 Models 面板当前**完全不显示**它（`app.js:1219` 表头只有 Model/Status/Path）。→ 本轮补显示，且文本**只能**来自上述唯一来源文件。

本轮交付：`webapp/schema.py` 下发模型显示文本；`webapp/static/app.js` 两个显示点（侧模型选择器 + Models 面板）；`tests/test_webapp.py` 聚焦用例；`docs/WEBAPP.md` 文档。不碰多选语义、表单值格式、API 端点结构、桌面端文件、布局几何。

## 1. 契约（唯一权威版本，servant 不要重新调研）

### 1.1 多选语义（不得回退）

- 每侧 On-target / Off-target 模型都是**多选**；表单值 = 逗号分隔的**注册表 key** 串（分号也当分隔符、去重保序）：`shared/design/workbench_form.py:106-117` 的 `split_model_selection`。
- 顺序有意义：**第一个**选中项是 primary。桌面端 `designer_workbench.py:193-209`（`_sync_display`）：弹层里 primary 项加 `[P] ` 前缀并加粗，控件关闭态显示 `Primary: <label>, <label>`。
- 网页端现状（已核验，本轮保持不变）：`app.js:694-721` 的 `modelSelect()` 建 `<select multiple>`；`change` 时把 `selectedOptions` 的 value 以 `,` 连接写进 `state.side_on_target_models[side]` / `state.side_off_target_models[side]`。

### 1.2 模型「显示文本」（桌面 picker 用的那套，网页本轮对齐）

- 唯一来源：`shared/design/workbench_form.py:120-127` 的 `model_display_name(model)`：
  `[<PROTEIN_GROUP_LABELS[蛋白]>]` +（传统规则模型再加 `[rule]`）+ 原始 key。
- master 实测输出（直调该函数，命令见 §2）：cas9 on-target → `[Cas9] cropsr`；cas9 off-target → `[Cas9] [rule] cfd`、`[Cas9] crispr_m`、`[Cas9] deepcrispr`、`[Cas9] crispai`；custom off-target 前 6 项 → `[Cas9] [rule] cfd`、`[Cas9] crispr_m`、`[Cas9] deepcrispr`、`[Cas9] crispai`、`[General] [rule] rules`、`[Cas13] [rule] pfs`。
- 硬规则：网页端**不得**自己拼这些文本、不得新增/复制映射表；必须由服务端经 `/api/schema` 下发（见 §3 P0-1）。

### 1.3 模型「描述文本」（桌面 Models 页用的那套，网页本轮补显示）

- 唯一来源：`shared/scoring/model_registry.py:29-142` 的 `MODELS[key]["description"]`（7 个模型：`crispr_m`、`deepcrispr`、`crispai`、`deepcpf1`、`deepcas12a`、`tiger`、`teep`）。
- 桌面渲染：`main.py:1174-1176`（`ttk.Label(text=info["description"], foreground="gray", wraplength=420)`）；同一行的「本地文件 / URL」列用 `path if path else info["url"]`（`main.py:1170-1173`）。
- 网页现状（已核验）：`/api/models` **已经**每个模型都带 `description` 与 `url`（`webapp/schema.py:310-319` 生出，`webapp/services/models.py:82-89` 合并进响应），但前端 `app.js:1219-1233` 只渲染 名字/状态/路径，**既不显示 description，也不回退 url**。
- 硬规则：网页端**不得**翻译或改写这些描述，也不得在 JS/HTML/文档里再抄一份（唯一来源 = 上述 py 文件）。

## 2. 现状证据（master 已核实，可直接引用）

| 位置 | 现状 |
| --- | --- |
| `webapp/static/app.js:694-699` | `modelSelect()` 建 `<select multiple size=String(min(max(len,2),5))>` |
| `webapp/static/app.js:703-708` | `el('option', {value: model, text: model})` — 选项文本 = 裸 key |
| `webapp/static/app.js:710-719` | `change` → `selectedOptions` 以 `,` 连接写入 `state.side_*_models[side]` |
| `webapp/static/app.js:723-731` | `renderSideModels()`；hint = `Ctrl/Cmd-click to select several models; the first selection is primary.` |
| `webapp/static/app.js:1219` | 表头 `['Model','Status','Path','']` — **无 Description 列** |
| `webapp/static/app.js:1225-1233` | 行 = `model.name` / 状态徽章 / `model.path`（空就是空，**不回退 url**） |
| `webapp/schema.py:303-329` | `model_catalog()` 每项已带 `url`（`:317`）与 `description`（`:318`） |
| `webapp/services/models.py:72-95` | `list_models()` = `dict(entry, status=…, status_label=…, path=…, has_file=…, is_ready=…)`（描述随之透传） |
| `designer_workbench.py:56-220`、`:193-209` | 桌面 `ModelPicker`：多选复选框弹层；文本 `_model_display_name`、primary 加 `[P] `、关闭态 `Primary: …` |
| `main.py:1170-1176` | 桌面 Models 行：`path if path else url`；`info["description"]` |
| `README.md:225-238`、`docs/GUI.md:41-48`、`docs/handoff/webapp-designer-port/task.md:97,144-149` | 多选是规格内行为；模型显示名带 `[Cas9]` / `[rule]` 前缀 |

master 实测命令与输出：

```powershell
# 1) 运行态探针（headless Edge + CDP）：多选控件确实存在、选项文本是裸 key、Models 面板缺描述列
#    服务：python webapp\app.py --port 8361   （启动到可访问约 20-25 秒）
$env:CDP_PORT='9343'; $env:APP_URL='http://127.0.0.1:8361/'; $env:WAIT_MS='12000'
& 'C:\Users\ASUS\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe' `
  docs\handoff\webapp-model-labels\assets\probe_browser_cdp.js `
  docs\handoff\webapp-model-labels\assets\probe_master_multiselect.js
```

```text
{"multiSelectCount":2,"multiple":true,"size":2,"optionLabels":["cropsr"],"optionValues":["cropsr"],
 "labelsEqualValues":true,"stateAfter":"{\"target\":\"cropsr\",\"left\":\"cropsr\",\"right\":\"cropsr\"}",
 "hintText":"Ctrl/Cmd-click to select several models; the first selection is primary.",
 "modelsTableExists":true,"modelsHeaderCells":["Model","Status","Path",""],
 "modelsFirstRowCells":["CRISPR-M","Ready (scoring)","R:\\songji\\programfile\\models\\tcrispr_model.h5","DownloadDelete"]}
```

```powershell
# 2) 共享层：显示文本本来就存在，只是网页没用
cd R:\songji\programfile; $env:PYTHONUTF8='1'
python -c "import sys; sys.path.insert(0,'shared'); from design.workbench_form import side_model_options, model_display_name; o=side_model_options('cas9'); print([model_display_name(m) for m in o['on_target']]); print([model_display_name(m) for m in o['off_target']])"
```

```text
['[Cas9] cropsr']
['[Cas9] [rule] cfd', '[Cas9] crispr_m', '[Cas9] deepcrispr', '[Cas9] crispai']
```

```powershell
# 3) /api/models 实测：7 个模型全部带 description；teep 的 path 为空字符串、url 为 https://www.tnpb.app
$j = (Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:8361/api/models' -TimeoutSec 60).Content | ConvertFrom-Json
$j.groups.models | Select-Object key, name, status_label, path, url, description
```

探针文件已放进 `docs/handoff/webapp-model-labels/assets/`：`probe_browser_cdp.js`（与 `webapp-file-picker` 版**逐字节相同**，不要改）、`probe_master_multiselect.js`（master 的现状探针，可当 servant 探针的起点）。

## 3. 必做改动

- [ ] P0-1 `/api/schema` 下发模型显示文本（唯一来源 `model_display_name`）
  - 位置：`webapp/schema.py`（`build_schema()`，`:332-396`；模型选项来自 `:356` 的 `side_model_options("cas9")` 与 `:367-369` 的 `preset_models`）
  - 期望行为：
    1. 顶层**新增**一个键（推荐名 `model_labels`），值 = `{model_key: model_display_name(model_key)}`，覆盖**所有** preset 的全部 on/off-target 选项：至少 `side_model_options(k)["on_target"] ∪ ["off_target"]`，k 取 `PRESET_KEYS`（master 实测 = `['custom','cas9','cas12a','cas12b','cas13','tnpb']`，已含 custom）。
    2. 必须 import 并使用 `shared/design/workbench_form.py` 的 `model_display_name`；不得在 `webapp/` 里复制其规则。
  - 证据要求：`python -c` 断言 `build_schema()['model_labels']` 与直调 `model_display_name` 一致（贴命令与输出）。

- [ ] P0-2 侧模型选择器显示桌面文本 + 标出 primary
  - 位置：`webapp/static/app.js:694-721`（`modelSelect`）、`:723-731`（`renderSideModels` 的 hint）
  - 期望行为：
    1. `<option>` 的 `value` 保持注册表 key（**不变**），`text` 改为 `state.schema.model_labels[model] || model`。
    2. primary = 选择顺序第一位：已选中的 option 文本加 `[P] ` 前缀（其余不加），并在 hint 里追加一句 `Primary: <label>, <label>`（label 用同一份 `model_labels`；无选择时不追加）。**原有** `Ctrl/Cmd-click …` 文案必须保留。
    3. `change` 写进 `state.side_on_target_models[side]` / `state.side_off_target_models[side]` 的**逗号分隔 key 串**不得改变（必须仍能被 `split_model_selection` 解析）。
    4. 控件仍是多选：`multiple` 与 `size` 规则（`Math.min(Math.max(len,2),5)`）不变；文本更新不得重排 option 顺序、不得改变选中集。
  - 证据要求：DOM 探针（§6）证明 `optionLabels` == `model_labels` 的值、`select.multiple === true`、连选两项后 `state.side_on_target_models.target === "<key1>,<key2>"`。

- [ ] P0-3 Models 面板补 Description 列与 URL 回退
  - 位置：`webapp/static/app.js:1219`（表头数组）、`:1223-1251`（行渲染）
  - 期望行为：
    1. 表头变为 `['Model','Status','Path','Description','']`（描述列在动作列之前）。
    2. 路径单元格文本 = `model.path || model.url || ''`（对齐 `main.py:1170-1173`；`teep` 这类无本地文件必须显示 URL）。
    3. 描述单元格文本 = `model.description || ''`（**原样**，不翻译、不截断）；用既有 `class="muted"`，可不加新 CSS。
    4. 后端不动（`/api/models` 已带这两个字段）。
  - 证据要求：探针断言表头含 `Description`；每行描述 === `/api/models` 同 key 的 `description`（等价于 `shared/scoring/model_registry.py` 的原文）；`teep` 行路径 === 其 `url`。

- [ ] P0-4 文档同步
  - 位置：`docs/WEBAPP.md`（面板章节 `:103-115`；API 表 `:184`）
  - 期望行为：写明 ①侧模型选择器是**多选**、选项显示 `[Cas9]`-风格显示名（来自 `shared/design/workbench_form.py:model_display_name`）并标出 primary；②Models 面板每行显示模型的 `description`，文本来自 `shared/scoring/model_registry.py`（**唯一来源**，网页不另存一份）；③API 表 `/api/models` 一行注明响应含 `description` 与 `url`。
  - 不改 `README.md` 的模型章节（那里是模型能力说明，内容正确）。

- [ ] P1-1 聚焦用例（`tests/test_webapp.py`）
  - 位置：`SchemaTests`（`:208-256`）与 `ModelServiceTests`（`:531-556`）
  - 期望行为（建议用例名）：
    1. `test_model_labels_match_the_shared_display_names`：`doc["model_labels"][key] == workbench_form.model_display_name(key)`，key 至少覆盖 `side_model_options("cas9")` 的 on/off 全量 + 一个 custom 专属项（如 `[General] [rule] rules`）。
    2. `test_model_descriptions_come_from_the_registry`：`list_models()` 每个模型 `description` 非空且等于 `model_registry.MODELS[key]["description"]`；`teep` 的 `path == ""` 且 `url` 非空。
  - 证据要求：`python -m unittest tests.test_webapp -v` 输出原文（含新用例名与 `OK`）。

## 4. 不要做的事

- 不改多选语义：不换成单选、不改 `state.side_on_target_models` / `side_off_target_models` 的「逗号分隔 key 串」格式、不改 `shared/design/workbench_form.py` 与 `shared/scoring/*`。
- 不动桌面端：`main.py`、`designer_workbench.py`、`unified_gui.py` 一律不改（本轮只是让网页**对齐**它们）。
- 不改 `/api/models` 响应与 `/api/schema` 既有键名/语义（只**新增** `model_labels`）；不动路由与作业模型。
- 不在 `webapp/` 里新增任何 per-model 文本（不抄描述、不写死 `[Cas9]` 前缀、不做中文翻译）。
- 不新增静态文件、不引入 CDN/框架；不改布局几何、不碰其它面板、不改文件选取器。
- 不跑全量测试套件、不做 ms01 服务器跑批（那是 master 的核验）。

## 5. 决策项（未确认则按推荐执行）

- D1 网页选择器是否重写成桌面那种「单行显示 + 弹层勾选」？→ **推荐：不改**，保留原生多选列表框，只补文本与 primary 提示。理由：用户看到的是「显示像错误」，根因是裸 key + 无 primary 语义；自绘弹层属于范围外的重写。
- D2 描述列位置 → **推荐**：`Path` 之后、动作之前；列头英文 `Description`。
- D3 primary 的表达 → **推荐**：已选 option 文本加 `[P] ` 前缀 + hint 追加 `Primary: …`（与桌面 `designer_workbench.py:193-209` 同义）。
- D4 无本地文件的模型（`teep`）→ **推荐**：Path 列回退显示 `url`（对齐 `main.py:1170-1173`）。
- D5 描述文本语言 → **推荐**：原样使用 registry 英文文本（翻译会制造第二份文本）。
- D6 `custom` 预设的模型是否都进 `model_labels` → **推荐**：进（custom 候选是全体并集，桌面也显示 `[General]` 等前缀）。

## 6. 轻量自检（servant 的检验上限，全部要贴原文）

```powershell
# 1) 语法
python -m py_compile webapp\schema.py
& 'C:\Users\ASUS\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe' --check webapp\static\app.js

# 2) 聚焦单测（改动前先跑一次记基线，改动后再跑）
python -m unittest tests.test_webapp -v

# 3) DOM 级探针（本任务唯一「真跑界面」证据，必须跑；跑不起来就停下报告）
#    终端 A：python webapp\app.py --port 8361
#    终端 B（一直占着，别等它返回）：
#    & 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe' --headless=new --disable-gpu --no-first-run --user-data-dir="$env:TEMP\edgeprobe_models" --remote-debugging-port=9343 about:blank
#    终端 C：
$env:CDP_PORT='9343'; $env:APP_URL='http://127.0.0.1:8361/'; $env:WAIT_MS='12000'
& 'C:\Users\ASUS\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe' `
  docs\handoff\webapp-model-labels\assets\probe_browser_cdp.js `
  docs\handoff\webapp-model-labels\assets\probe_servant_model_labels.js
```

- `assets/probe_browser_cdp.js` 已就位（逐字节等同 `webapp-file-picker` 版），**不要改**。
- servant 新写 `assets/probe_servant_model_labels.js`（页面内 async IIFE，`return JSON.stringify(...)`），必须包含并输出以下键：
  - `optionLabels`：第一个 `select[multiple]` 的选项文本数组；`expectedLabels`：由 `await (await fetch('/api/schema')).json()` 的 `model_labels` 按同一 option 顺序映射的值 → 两者必须相等（贴两侧数组）。
  - `selectMultipleStillTrue` = `true`；`sizeAfter` = 该控件的 `size`。
  - 连选前两项后：`stateAfterTwoPicks` == `"<key1>,<key2>"`，且 `primaryMarkedInLabels` = `true`（第一项文本以 `[P] ` 开头、第二项不以它开头），`hintHasPrimaryLine` = `true`（hint 文本里出现 `Primary:`）。
  - Models 面板（先 `await loadModels()`）：`modelsHeaderCells` 含 `"Description"`；`eachRowDescriptionMatchesRegistry` = `true`（前端单元格文本 === `/api/models` 同 key 的 `description`，全 7 行）；`teepPathCell` === `teep` 的 `url`。
  - `windowErrors` == `[]`（页面内收集 `window.addEventListener('error', …)`）。
- 探针跑不起来（Edge/CDP 起不来）时，把失败原文写进 `report.md` 并停下，不许用「静态检查代替」。

## 7. 交付要求

- 改前快照到 `backup/20260917_webapp_model_labels/`（保相对路径）：`webapp/schema.py`、`webapp/static/app.js`、`tests/test_webapp.py`、`docs/WEBAPP.md`；若还改了 `webapp/index.html` / `webapp/static/styles.css`，一并快照。
- 编码安全：改动文件保持 **UTF-8 无 BOM + LF**；`docs/WEBAPP.md` 含中文，改它用 `apply_patch` 技能或 `encoding-safe-editing` 的写法，**不要**用 `Get-Content`/`Set-Content` 直接改写带中文的文件。
- 完成后：`state.json` 置 `ready_for_review`（`round` 保持 1），写 `report.md`（改动文件+行号、命令原文与输出、未做项、附带发现、待明确）。
- 交付后给用户这句可转发的话：`本会话是 master，核验 R:\songji\programfile\docs\handoff\webapp-model-labels\。`

## 8. master 已实测的补充（避免误判）

- 本机权威解释器：`python`（3.14.7）；`.venv` / `.venv310` 在本机不可用。webapp 用系统 `python` 直起。
- `python webapp\app.py --port 8361` 启动到可访问约 **20-25 秒**（R: 网络盘 import 慢）；前端首屏不依赖外网。
- `/api/models` 实测：7 个模型全部带非空 `description`；`teep` 的 `path == ""`、`url == "https://www.tnpb.app"`；`tiger` 的 `path` 是目录 `R:\songji\programfile\models\tiger`。
- 桌面 `main.py:1174` 的 `info["description"]` 与 `/api/models` 的 `description` **逐字相同**（同源于 `model_registry.MODELS`）——所以本轮网页端不需要任何新文本。
- master 的探针进程已全部关闭（Edge `:9343`、服务 `:8361`），端口留给 servant 使用。