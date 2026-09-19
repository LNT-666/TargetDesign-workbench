# 任务：Data prep / Models 改成近满屏大面板（“prep 大抽屉”）

- round: 1
- status: assigned
- 追加：**§8 是 round 1 的补充项（P0-0「切模式不刷新」回归），优先级高于 §0-§7，必须一起做完**
- updated: 2026-09-16 20:40
- 前置任务：`docs/handoff/webapp-designer-port/`（master 核验 pass）、
  `docs/handoff/webapp-single-page-layout/`（master 核验 done）
- 起始快照：`backup/20260916_webapp_single_page/`、`backup/20260916_webapp_designer_port/`

**servant 开工前必读**：本文件全文 + `docs/handoff/webapp-single-page-layout/task.md` 的
§1.2（单页工作区形态）、§1.3（抽屉与回填）、§1.4（`outputs` 字段）——这些原文继续生效。

## 0. 用户原话与本轮目标

- 「我觉得你把 data prep 做的太小了」
- 「我建议 prep 和 design 分成左右两个大抽屉，或者就左边的是大抽屉，点一边的时候
  几乎完全占据屏幕。不许用考虑另一边」

用户给了两个可接受方案，master 已选定 **方案 B**：

> 只把 `Data prep / Models` 做成“大抽屉”：一个从左侧滑出的**近满屏面板**
> （默认宽度 `min(1800px, 视口宽 − 48px)`）。点开时它几乎完全占据屏幕，
> 右侧只留 48px 缝。Designer 仍是唯一的常驻底层主区，**不做**左右双面板、
> **不做**两个面板并排同看。

理由：任务 `webapp-single-page-layout` 的 §1.2 要求“候选表与日志始终留在页面下部、
不折叠掉”，Designer 作为常驻底层正好满足；做成两个滑出面板需要额外的可见性/状态
同步，收益低、回归面大。方案 A 明确不做（见 §4）。

本轮**只改布局几何 + 抽屉内字段排布 + 回填提示的可视性 + 编码/文档**，
不改任何 API、字段名、默认值、作业语义。

## 1. 契约（本任务的形态定义）

### 1.1 冻结的前置契约（不得改动）

- 任务 1 / 2 的 §1.x 全部继续生效：表单字段与默认值、Run Settings、预设/切侧/模型
  下拉、genome gz 规则、进度与 confirm 协议、候选与导出契约、安全边界
  （`docs/WEBAPP.md` 的“安全边界”一节）、回填规则（只填空字段、`skip_mask` 生效、
  不允许静默带参）。
- 顶部固定条上的控件集合、`#designer-*` / `dp-*` / `models-*` 的 id 都不变。
- `/api/**` 的路径、方法与响应键都不变。
- `docs/WEBAPP.md:34-35` 的静态资源约定（LF、无 BOM、无外链）继续生效。

### 1.2 面板几何（P0-1）

现状（要改掉的）：

- `.drawer` 是与主区并排的 CSS grid 一列，宽 `var(--drawer-width)`：`webapp/static/styles.css:103-110`。
- 只有 `<1200px` 才切成覆盖式抽屉：`styles.css:429-455`（整块 `@media (max-width:1199px)`）。
- `#drawer-resizer` 是 `.workspace` 的第 2 个子元素（grid 的一列）：
  `webapp/index.html:146-148`。
- 旧尺寸：`styles.css:12-14`（`--drawer-width-default: 460px`、`--resizer-width: 6px`）。

目标形态（**所有视口统一**，不再有“宽屏并排 / 窄屏覆盖”的二分）：

1. `.workspace` 只留主区：`grid-template-columns` 不再有抽屉列（保留 `display:grid`
   单列或改成 `display:block` 都行）；删掉 `.workspace:not(.drawer-open)` 那条
   “把抽屉压成 0 宽”的规则（`styles.css:110`）。
2. `.drawer` 变成**左侧滑出面板**：
   - `position: fixed; top: 0; left: 0; bottom: 0; z-index: 40; width: var(--drawer-width);`
     `max-height: none; overflow-y: auto; border-right: 1px solid var(--line);`
     `box-shadow: 2px 0 18px rgba(16, 24, 40, .20);`
   - 关闭态 `transform: translateX(-102%)`；打开态 `transform: none`；
     过渡 `transform .18s ease`。
   - **可见性必须跟着一起走**：关闭态 `visibility: hidden`，
     `transition: transform .18s ease, visibility 0s linear .18s`；
     打开态（`.drawer.open`）`visibility: visible; transition-delay: 0s;`。
     理由：只靠 transform 隐藏时，抽屉里的输入框仍会被 Tab 聚焦；现在宽屏用的是
     `visibility: hidden`（`styles.css:132,135-140`），这个语义不能丢。
   - 删掉旧 grid 时代的 `min-height / max-height: calc(100vh - …)` 写法
     （`styles.css:137-138`）。
3. 删掉整块 `@media (max-width: 1199px)`（`styles.css:429-455`）。
   保留 `@media (max-width: 1399px)` 的三列纵向堆叠。
4. 宽度（JS 计算，见 `app.js:177-198`）：
   - `drawerDefaultWidth()` = `min(1800, window.innerWidth - 48)`；
   - `drawerMaxWidth()` = `max(380, window.innerWidth - 48)`；
   - `DRAWER_MIN_WIDTH` 从 320 改成 **380**；`DRAWER_MAX_RATIO` 常量删除。
   - CSS 侧只保留一个兜底默认值，供 JS 执行前首屏使用：
     `--drawer-width: min(1800px, calc(100% - 48px));`
     删掉 `--drawer-width-default` 与 `--resizer-width`。
   - `localStorage` 的 key 不变：`crispr.drawerWidth` / `crispr.drawerOpen`。
5. 拖动条：`#drawer-resizer` 从 `.workspace` 里移到 `<aside class="drawer">`
   **内部、作为最后一个子元素**（`index.html:144` 的 `</aside>` 之前），
   样式改成贴在面板右边缘：
   `position: absolute; top: 0; right: -3px; bottom: 0; width: 6px;`
   （`fixed` 定位的 `.drawer` 就是它的包含块）。
   删掉旧的 `align-self: stretch; min-height: calc(100vh - 120px)` 与
   `.workspace:not(.drawer-open) .drawer-resizer { visibility: hidden }`
   （关闭态的隐藏由面板自身的 `visibility` 统一接管）。`body.resizing` 保留。
6. `initDrawerGeometry()`（`app.js:202-268`）：删掉两处
   `window.innerWidth < 1200` 的提前返回（`app.js:215`、`app.js:264`），
   让拖拽与窗口 resize 夹取在所有宽度都生效；拖拽步进（16px / Shift 48px）、
   双击复位、`writeStorage` 都保持。
7. 遮罩：新增 `<div id="drawer-scrim" class="scrim hidden"></div>`，
   `position: fixed; inset: 0; z-index: 35; background: rgba(16, 24, 40, .16);`
   打开面板时显示（去掉 `hidden`），关闭时加回 `hidden`；
   点击遮罩 = `setDrawer(false)`。
   目的：面板几乎占满屏幕后，防止用户点到它背后 Designer 的按钮。
   面板 `z-index: 40` 在遮罩之上，所以面板自身仍可交互。
8. 打开/关闭入口保持现状、共 4 条：顶部条 `#drawer-toggle`（`aria-expanded`）、
   面板内 `#drawer-close`、`Esc`（`app.js:362-366`）、遮罩点击。
   **不要**新增页签，**不要**把 Designer 做成滑出面板。

**期望行为（可截图/可手验）**：1600×1000 视口下点开 `Data prep / Models`，
面板宽度 = 1552px（1600−48），右侧只露出 48px 主区；面板内可上下滚动；
点 `Close` / 遮罩 / `Esc` 都能回到 Designer，且 Designer 的滚动位置、表单值、
候选表内容一律不变（面板只是隐藏，不重建、不清空）。

### 1.3 抽屉内的字段排布（P0-2）

现状：抽屉里的手写表单沿用全局 `.grid`（`styles.css:189-194`：
`grid-template-columns: minmax(140px,220px) minmax(220px,1fr)`，即“标签一列 + 控件一列”
配对成行）。master 已在 `styles.css:158-170` 加了一条临时的
`.drawer .grid { grid-template-columns: minmax(0,1fr) }` 单列覆盖。
面板变宽后单列会让每个输入框宽到 1500px，既难看也浪费；必须改成
**“标签在上、控件在下”的多列自适应**。

要改的 15 对字段（4 个 `<div class="grid">`）：

| 位置 | 分组 | 对数 |
| --- | --- | --- |
| `index.html:59-64` | Download | 2（`dp-species`、`dp-download-output`） |
| `index.html:72-83` | Genome / annotation | 5（`dp-genome`、`dp-annotation`、`dp-output`、`dp-blastdb`、`dp-index-prefix`） |
| `index.html:89-98` | Search scope | 4（`dp-target-id`、`dp-target-id-type`、`dp-target-region`、`dp-target-num`） |
| `index.html:108-117` | Mask gene | 4（`dp-mask-id`、`dp-mask-id-type`、`dp-mask-region`、`dp-mask-num`） |

要求：

1. 把每一对 `<label>…</label>` + 控件**按原顺序**包成 `<div class="field">…</div>`，
   外层容器仍是 `<div class="grid">`。控件本身（id、`type`、`placeholder`、
   `checked` 等）一个字符都不改。
   - 抽屉里共 4 个 `.grid`、18 个 `<label>`（其中 3 个是 `label.inline` 复选框：
     `dp-build-blastdb`(84)、`dp-skip-mask`(106)、`dp-mask-same`(107)，**不在**
     `.grid` 内，保持原样不动）、13 个 `<input>` + 5 个 `<select>`。
   - 包完之后 `.drawer .grid` 的直接子元素**只能**是 `.field`；
     `.drawer .grid > label`、`.drawer .grid > input`、`.drawer .grid > select`
     的数都必须为 0。
2. CSS：把 `styles.css:158-170` 那段换成

   ```css
   /* 面板很宽：字段“标签在上、控件在下”，按列自适应。 */
   .drawer .grid {
     grid-template-columns: repeat(auto-fit, minmax(330px, 1fr));
     gap: 10px 20px;
     align-items: start;
   }

   .drawer .field { margin-bottom: 0; }
   ```

   `.field` 的既有定义（`styles.css:196-205`：`label` 在上、`font-size:12.5px`、
   `color: var(--muted)`）直接复用，不要另造一套类名。
   `.field` 在 Designer 主区由 `app.js:590-604` 的 `renderField()` 生成，
   改全局 `.field` 会波及主区，所以本条**只允许**用 `.drawer .` 前缀写。
3. 不许动主区 `.designer-columns` 的三列布局，也不许动 `renderField()` 的产物。
4. 期望：1600px 面板下 `.grid` 排 4 列（每列 ≥ 330px），输入框宽度约为
   (面板宽 − 内边距 − 间距) / 4；面板被拖窄到 380px 时自动退化成 1 列；
   长绝对路径仍能看见大部分内容。

### 1.4 回填提示在面板打开时也要看得见（P0-3）

`webapp-single-page-layout/task.md` §1.3 要求“回填后就地在公共输入区显示一行提示，
**不允许静默带参**”。面板变成近满屏之后，主区那行提示（`#designer-loaded-hint`）
被面板盖住，用户看不到——契约破了一半。必须补上。

要求：

1. 在 `#drawer-dataprep` 内、`#dp-job`（`index.html:132`）**上方**加
   `<div id="dp-loaded-hint" class="loaded-hint hidden"></div>`
   （`loaded-hint` 是 `styles.css:298-308` 已有的样式）。
2. `applyJobOutputs()`（`app.js:480-530`）完成回填后，除了更新主区的
   `#designer-loaded-hint`，也要把**同一段文案**写进 `#dp-loaded-hint` 并去掉
   `hidden`；若本次作业没有任何字段可带入（`plan.updates` 与
   `plan.drawerUpdates` 都空），两个提示都保持/回到 `hidden`。
3. 文案与 `title`（完整路径）与主区**完全一致**：复用
   `app.js:462-478` 那段拼串（`已带入 / Loaded: …` + `· kept your values: …`），
   不要复制出新的一份规则。
4. 主区原有行为、`skip_mask` 跳过、只填空字段的判定，一律不变。

### 1.5 编码与格式（P0-4）

`docs/WEBAPP.md:34-35` 写的是“`webapp/index.html` + `webapp/static/app.js` +
`webapp/static/styles.css`（LF、无 BOM、无外链）”。

实际：这三个文件**现在都是 UTF-8 with BOM**（首三字节 `ef bb bf`），
而 16:00 的快照 `backup/20260916_webapp_single_page/webapp/{index.html,static/app.js,static/styles.css}`
是无 BOM 的（首三字节分别是 `3c 21 64` / `27 75 73` / `3a 72 6f`）。
（master 已判定这不是本轮之前那次交付引入的，属于要一并修掉的历史遗留。）

要求：这三个文件改完后必须是 **UTF-8 无 BOM + LF（全文无 `\r`）**；
`docs/WEBAPP.md`、`README.md` 同样写成 UTF-8 无 BOM + LF。

自检（输出贴进 `report.md`）：

```powershell
python -c "p=[r'webapp\index.html',r'webapp\static\app.js',r'webapp\static\styles.css']; [print(f, open(f,'rb').read(3)==b'\xef\xbb\xbf', b'\r' in open(f,'rb').read()) for f in p]"
```

期望三行都是 `False False`。

（Windows PowerShell 5.1 的 `Set-Content -Encoding utf8` 与 `Out-File` 都会写 BOM；
用 `[System.IO.File]::WriteAllText($path, $text, (New-Object System.Text.UTF8Encoding($false)))`
或 Python 的 `io.open(..., newline='')` 才能保证无 BOM。）

### 1.6 文档（P0-5）

- `docs/WEBAPP.md`：第 1-6 行（“Data prep / Models 在左侧抽屉”）、
  37-69 行（“## 单页工作区”的 ASCII 图与要点）、81-88 行（“## 抽屉”）按新形态改写：
  - ASCII 图画出“面板盖住主区、右侧留 48px”的形态；
  - 抽屉一节写清：默认宽度 `min(1800px, 视口宽 − 48px)`、最小 380px、
    右边缘可拖拽（双击复位）、宽度记在 `localStorage` 的 `crispr.drawerWidth`、
    关闭方式有 4 种（顶部条按钮 / Close / `Esc` / 点遮罩）；
  - 补一句 §1.3 的多列字段排布与 §1.4 的抽屉内提示。
- `README.md:30` 的描述同步（现在写的是“单页工作区（Designer 主区 + 数据准备抽屉）”）。
- `docs/WEBAPP.md` 里 API / 回填规则 / 安全边界 / 启动 这些实质内容不要动。

## 2. 现状证据（master 已核实，可直接引用）

**当前工作区已经有一版 master 自己做的半成品改动（2026-09-16 20:04 落盘）**，
它是本任务的起点，**请在这版之上继续改，不要回退成“没有 resizer”的旧样子**。
`node --check webapp\static\app.js` 现在是 exit 0。

| 文件:行 | 现状 |
| --- | --- |
| `webapp/index.html:146-148` | `#drawer-resizer`（`role="separator"`、`aria-orientation="vertical"`、`tabindex="0"`、中英双语 title）已加，但位置仍在 `.workspace` 里、`</aside>` 与 `<main>` 之间 |
| `webapp/static/styles.css:12-14` | `--drawer-width-default: 460px; --drawer-width: var(--drawer-width-default); --resizer-width: 6px;` |
| `styles.css:103-110` | `.workspace` 三列 `var(--drawer-width) var(--resizer-width) minmax(0,1fr)`；`:not(.drawer-open)` 时 `0 0 minmax(0,1fr)` |
| `styles.css:112-125` | `.drawer-resizer` 拖动条 + `body.resizing` |
| `styles.css:158-170` | `.drawer .grid` 单列 + `.drawer .grid > label` 的临时覆盖 |
| `styles.css:429-455` | `@media (max-width:1199px)` 覆盖式抽屉分支 + `.drawer-resizer { display: none }` |
| `webapp/static/app.js:136-152` | `setDrawer()` 已加 `writeStorage(DRAWER_OPEN_KEY, …)` |
| `app.js:154-268` | `DRAWER_WIDTH_KEY` / `DRAWER_OPEN_KEY` / `DRAWER_MIN_WIDTH = 320` / `DRAWER_MAX_RATIO = 0.72` / `readStorage` / `writeStorage` / `drawerDefaultWidth` / `drawerMaxWidth` / `applyDrawerWidth` / `drawerWidth` / `initDrawerGeometry` |
| `app.js:353-355` | `initLayout()` 开头：`initDrawerGeometry(); setDrawer(readStorage(DRAWER_OPEN_KEY) === '1');` |

其余现状：

- 抽屉手写表单：`index.html:47-143`（`#drawer-dataprep` = 47-133，`#drawer-models` = 135-143），
  4 个 `.grid`、15 对 label/控件、3 个 `label.inline` 复选框。
- 抽屉开关：`app.js:353-366`（toggle / close / Esc）、`app.js:149-151`（打开时 `loadModels()`）。
- 回填实现：`app.js:387-530`（`OUTPUT_FIELD_MAP` 388-398、`DRAWER_FIELD_MAP` 400-412、
  `backfillPlan()` 416-460、提示拼串 462-478、`applyJobOutputs()` 480-530）；
  主区提示元素 id 是 `designer-loaded-hint`，样式类 `loaded-hint`。
- 主区三列：`index.html:151`（`designer-columns`）；`styles.css:283-295`；
  `<1400px` 堆叠在 `styles.css:425-428`。
- 后端本轮**不需要**任何 Python 改动。
- 环境：`python` = `C:\Users\ASUS\AppData\Local\Programs\Python\Python314\python.exe`；
  node 在 `C:\Users\ASUS\.cache\codex-runtimes\...\bin\node.exe`；
  Edge = `C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe`
  （支持 `--headless --screenshot`）。仓库在 Samba 盘上，单条命令几十秒是正常的。

## 3. 交付要求

1. 开工前先建快照 `backup/20260916_webapp_big_prep_panel/`，把**改动前**的这 5 个文件
   按相对路径复制进去：`webapp/index.html`、`webapp/static/app.js`、
   `webapp/static/styles.css`、`docs/WEBAPP.md`、`README.md`。
2. 只改这 5 个文件。
3. §6 的轻量自检全部通过后写 `report.md`，把 `state.json` 置 `ready_for_review`。
4. 完成后给用户一句可直接转发的话：
   `本会话是 master，核验 R:\songji\programfile\docs\handoff\webapp-big-prep-panel\。`

## 4. 不要做的事

- **不做方案 A**：不把 Designer 改成滑出面板，不做左右双抽屉，不做两个面板并排。
- 不改 `/api/**`、`webapp/app.py`、`webapp/schema.py`、`webapp/jobs.py`、
  `webapp/services/**`、`webapp/job_store.py`、`shared/**`、`tests/**`（只允许跑）。
- 不改 `docs/handoff/webapp-designer-port/**`、`docs/handoff/webapp-single-page-layout/**`
  （历史记录，只读）。
- 不改 `CRISPR-Motif-Workbench.exe`、`tools/launcher/**`；**不要**顺手把启动器写进文档。
- 不引入前端框架 / CDN / 打包器 / web font / 新图片。
- 不删除任何文件。
- 不改字段 id、字段顺序、字段文案、默认值；不改 `#designer-*` 的 id。
- 不改作业语义与回填判定规则本身（`backfillPlan` 的判定逻辑不动，只在 §1.4 增一个
  输出位置）。
- 不改 `docs/WEBAPP.md` 的 API / 安全边界 / 启动 章节内容。

## 5. 决策项（未确认则按推荐执行）

| 编号 | 决策 | 推荐值 | 说明 |
| --- | --- | --- | --- |
| D1 | 采用哪个方案 | B：只把 prep 做成近满屏面板 | 见 §0 |
| D2 | 面板默认宽度 | `min(1800, 视口宽 − 48)` px | “几乎完全占据屏幕”，右侧留 48px 缝作为返回锚点 |
| D3 | 最小宽度 | 380px | 用户明确“不用考虑另一边”，所以不强制并排 |
| D4 | 遮罩 | 有：`rgba(16,24,40,.16)`，点击即关闭 | 防止点到背后的 Designer 按钮 |
| D5 | 双击拖动条 | 复位到 D2 的默认宽度 | 沿用现有实现 |
| D6 | 关闭面板后 | 面板内容 / 滚动位置 / 表单值全部保留；Designer 的滚动位置也保留 | 面板只是隐藏，不重建 |
| D7 | 编码 | 三个前端文件恢复 UTF-8 无 BOM + LF | §1.5 |
| D8 | 窄视口 | 与宽视口同一套行为（面板 = 视口宽 − 48，最小 380） | 不再有 `1199px` 分支 |

## 6. 轻量自检（servant 的检验上限）

按顺序跑，把**命令原文 + 输出原文**贴进 `report.md`：

1. `node --check webapp\static\app.js` → exit 0。
2. `python -m py_compile webapp\app.py webapp\schema.py webapp\jobs.py` → exit 0
   （本轮不该改 Python，跑一遍确认没被顺手改坏）。
3. `python -m unittest tests.test_webapp tests.test_workbench_form -v` → 必须仍是 `OK`。
   这两个测试覆盖 webapp 与表单契约；若失败，是代码把契约改坏了，
   **不要改测试**，改代码。
4. §1.5 的 BOM/LF 一行命令 → 三行都是 `False False`。
5. 结构探针（起服务：新开一个持久终端跑 `python webapp\app.py --port 8349`）：
   - `Invoke-WebRequest http://127.0.0.1:8349/ -UseBasicParsing` → 200；
   - 页面文本里 `id="drawer-resizer"` 出现在 `</aside>` **之前**；
   - 每个 `<div class="grid">` 块内没有裸 `<label>` / `<input>` / `<select>` 直接子元素；
   - `id="drawer-scrim"`、`id="dp-loaded-hint"` 都存在；
   - 抓 `GET /api/schema` → 200（确认没顺手动到后端）。
   - 跑完记得停服务（`Ctrl-C` 那个终端会话）。
6. 截图（可选，能跑就跑）：
   `msedge.exe --headless --disable-gpu --window-size=1600,1000 --screenshot=out\big_panel_closed.png http://127.0.0.1:8349/`
   —— headless 不会点按钮，抽屉开关状态存在 `localStorage` 里，
   **不许**为截图往产品代码里加 `?drawer=1` 之类的调试开关；截关闭态即可，
   开态形状判断交给 master。
7. **不要**跑全量测试套件（`python -m unittest discover`），那是 master 的事。

## 7. 报告格式

照 `report.md` 模板，并保证包含：

- 改动清单表：`文件:行` + 一句话 + 对应 P0 项；
- §6 第 1-6 条的命令原文与输出原文（含 HTTP 状态码与各项计数）；
- 未做项与原因；
- 附带发现（只记录不修）；
- 待明确（若有）。
---

## 8. 追加（round 1 补充，2026-09-16）：P0-0 切换 Design Pattern 不刷新界面（回归，优先级最高）

### 8.1 用户报告

> 「目前切换模式不会刷新界面，这个bug也得修一下」

### 8.2 master 的复现证据（真实浏览器，非推断）

环境：`python webapp\app.py --port 8351` + Edge 153 headless
（`--headless=new --remote-debugging-port=9333 --user-data-dir=<空目录>`）+ Node 24 通过 CDP 驱动
**真实页面**（探针即 `assets/probe_browser_cdp.js` + `assets/probe_mode_switch.js`）。

探针返回原文（节选）：

```json
{
  "modes": ["single_motif_flank", "motif_gap_motif", "y_centered_motifs"],
  "before": {"mode": "single_motif_flank", "hasCommonInputsWrap": false, "hasCommonFields": false,
             "hasLoadedHint": false, "leftHeads": ["Target TAM"], "middleHeads": [], "rightHeads": []},
  "switchedTo": "y_centered_motifs",
  "after":  {"mode": "y_centered_motifs", "hasCommonInputsWrap": false, "hasCommonFields": false,
             "hasLoadedHint": false, "leftHeads": ["Target TAM"], "middleHeads": [], "rightHeads": []},
  "windowErrors": ["window.error: Uncaught TypeError: Cannot set properties of null (setting 'innerHTML')"]
}
```

CDP 抓到的未捕获异常原文：

```text
TypeError: Cannot set properties of null (setting 'innerHTML')
    at renderCommon (http://127.0.0.1:8351/static/app.js:703:23)
    at renderDesigner (http://127.0.0.1:8351/static/app.js:813:3)
    at HTMLSelectElement.<anonymous> (http://127.0.0.1:8351/static/app.js:1410:5)
```

即：下拉的 value 已经改成 `y_centered_motifs`，但左/中/右三列的标题一个字都没变，
且 change handler 里抛了未捕获异常 —— 用户看到的就是“点了没反应”。

### 8.3 根因（三处联动，master 已定位）

1. `webapp/static/app.js:738-742`：`SLOT_CONTAINERS.left = 'designer-common-col'`。
2. `webapp/index.html:152-158`：`#designer-common-col` 这个容器**同时**装着两个**静态**元素
   —— `<details id="common-inputs-wrap">`（内含 `#designer-common-fields`）与
   `#designer-loaded-hint`。
3. `webapp/static/app.js:765-771`：`renderPattern()` 对三个 slot 容器一律执行
   `container.innerHTML = ''`。于是**第一次** `renderDesigner()`（`app.js:547`，schema 加载完成后）
   就把 Common Inputs 的整个 `<details>` 与 `#designer-loaded-hint` 从 DOM 里删掉了，
   只留下它自己新追加的 Target TAM 组。
4. 第二次及以后的 `renderDesigner()`（`app.js:809-816`）会先跑 `renderCommon()`，
   而 `app.js:702-703` 是 `const container = $('designer-common-fields'); container.innerHTML = '';`
   —— 元素已不存在 → **TypeError** → 异常从 change handler 抛出 →
   `renderPattern()` / `renderRun()` 根本没机会执行 → 界面冻结。

同一根因造成两个可见缺陷：

- **A（用户报告的）**：切模式失效；连带失效的还有 `app.js:715` 的输入模式单选、
  `app.js:916` / `app.js:932` 的模型下拉、`app.js:534` 的回填重绘
  （它们都走 `renderDesigner()`）。
- **B（顺带）**：页面加载后 Common Inputs 整块消失，`#designer-loaded-hint` 不存在
  → 前置任务 §1.3 的“回填后就地显示提示、不允许静默带参”在**运行时**根本不成立
  （值只写进 `state.values`，主区看不到）。本任务 §1.4 依赖同一段文案函数，必须先有 A 的修复。

归属：**回归，由前置任务 `webapp-single-page-layout` 引入**（是那次把 Designer 搬进主页、
引入 `SLOT_CONTAINERS` 才产生的）。master 在那一轮的核验只覆盖了回填**规则**
（抽出函数跑探针）与 HTTP 契约，**没有**覆盖渲染后的 DOM，属核验漏检；
已在 `docs/handoff/webapp-single-page-layout/review.md` 追加记录，不返工那一轮。

### 8.4 必做修复（P0-0）

1. **根因修复**：让 slot 容器只装 slot 渲染出来的东西。推荐做法——在
   `webapp/index.html:152` 的 `#designer-common-col` 内**新增专用子容器**
   `<div id="designer-left-col"></div>`（放在 `<details id="common-inputs-wrap">` 与
   `#designer-loaded-hint` **之后**），并把 `app.js:739` 的
   `left: 'designer-common-col'` 改成 `left: 'designer-left-col'`。
2. 修复后 `#designer-common-col` 的直接子元素必须**恒为**这 3 个、顺序不变：
   `#common-inputs-wrap`、`#designer-loaded-hint`、`#designer-left-col`；
   `renderPattern()` 只允许清空 `#designer-left-col` / `#designer-middle-col` /
   `#designer-right-col`。
3. 可以在 `renderCommon()` / `renderPattern()` / `renderRun()` 里补
   `if (!container) { return; }` 守卫，防止将来再次整页冻结；但**守卫不能代替根因修复**，
   也不许用它把本次异常吞掉。
4. **不许**用 `try/catch` 包住 change handler 来“消掉报错”；不许把 Common Inputs 挪进 slot
   渲染；不许改 `webapp/schema.py` 的 `PATTERN_FORMS` 或字段 key。
5. 修复后 `#designer-loaded-hint` 必须重新存在于 DOM 中（§1.4 依赖它）。

### 8.5 期望行为

- 页面加载完成后，左列自上而下是：Common Inputs（`<details>`，内含 `#designer-common-fields`）、
  `#designer-loaded-hint`（默认 `hidden`）、当前模式的左 slot 组。
- 三种模式（`webapp/schema.py:111-224`）的切换结果：
  - `single_motif_flank`：只有左列有组，标题 `Target TAM`；中、右列为空。
  - `motif_gap_motif`：左 `Left TAM`、中 `Middle`（Minimum/Maximum Distance）、右 `Right TAM`。
  - `y_centered_motifs`：左 `Left TAM`、中 `Middle`（Middle Motif = `y_sequence`）、
    右 `Right TAM`，且左右两侧多出各自的 min/max distance 字段。
- 切模式**不清空**已填字段（`state.values` 不变，切回去值还在）。
- 全程浏览器控制台**零未捕获异常**。
- 输入模式单选（Sequence/BED）、System Preset 的 `Apply`、模型下拉改动后同样能看到界面刷新。

### 8.6 回归探针（必须跑，输出原文贴进 `report.md`）

`assets/probe_browser_cdp.js`（Node 驱动）与 `assets/probe_mode_switch.js`（页面内表达式）
就是 master 复现用的脚本，原样复用：

```powershell
# 1) 起服务（一个持久终端）
python webapp\app.py --port 8351
# 2) 起 headless Edge 并开 CDP（另一个终端；这条命令会一直占着，不要等它返回）
& 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe' --headless=new --disable-gpu --no-first-run --user-data-dir="$env:TEMP\edgeprobe_servant" --remote-debugging-port=9333 about:blank
# 3) 跑探针（第三个终端）
$env:CDP_PORT='9333'; $env:APP_URL='http://127.0.0.1:8351/'; $env:WAIT_MS='9000'
& 'C:\Users\ASUS\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe' docs\handoff\webapp-big-prep-panel\assets\probe_browser_cdp.js docs\handoff\webapp-big-prep-panel\assets\probe_mode_switch.js
```

修复前（master 实测）：`before.hasCommonInputsWrap == false`、`cdpExceptionsTotal == 1`、
`after.leftHeads == before.leftHeads`。

修复后必须同时满足：

- `before.hasCommonInputsWrap == true`、`before.hasCommonFields == true`、
  `before.hasLoadedHint == true`、`before.leftHeads == ["Target TAM"]`；
- `cdpExceptionsTotal == 0`；
- 切到 `y_centered_motifs` 后 `after.leftHeads == ["Left TAM"]`、
  `after.middleHeads == ["Middle"]`、`after.rightHeads == ["Right TAM"]`（与 `before` 不同）。