# 任务：网页版加“浏览选择文件/目录”组件（`/api/fs/list` + 页面内选取器）

- task-slug: `webapp-file-picker`
- round: 1
- round: 2（新增内容见 §9；§0–§8 为 round 1 原文，未改动）
- status: assigned
- updated: 2026-09-16 22:05
- 前置任务（已核验）：`webapp-designer-port`、`webapp-single-page-layout`、`webapp-big-prep-panel`
- 起始快照：`backup/20260916_webapp_file_picker/`（**由 servant 开工前创建**，见 §7）

**servant 开工前必读**：本文件全文 + `docs/WEBAPP.md` 的「单页工作区」「API」「安全边界」三节。
前置任务已经生效的形态契约（单页工作区、prep 大抽屉几何、字段 key、回填规则、作业模型）
本任务**一律不动**。

## 0. 用户原话与本轮目标

- 「在网页版中，如何输入文件地址」
- 「有没有办法有一种浏览选择文件的组件」

结论（master 已定，不再讨论方案）：**做，按“服务端只读列目录 + 页面内自绘选取器”实现**。

理由（写进规格，servant 不需要重新调研）：

1. 浏览器原生 `<input type="file">` 与 File System Access API 的 `showDirectoryPicker()`
   **都拿不到绝对路径**（只给文件名 / 文件句柄），而网页版所有路径字段要的正是**服务端
   绝对路径**，所以纯前端方案不可能实现。
2. “上传文件再落到服务器目录”能通，但会把基因组（几十 GB）复制一份，且后续路径指向副本，
   与本工具“就地读用户已有文件”的语义冲突，明确**不做**（见 §4）。
3. 网页版已经是本机工具、只绑 `127.0.0.1`（`webapp/app.py:39`），进程本来就在读这些路径，
   再加一个**只读列目录**接口不引入新的数据暴露面。

本轮交付：`GET /api/fs/list`、页面内 picker 弹层、每个路径字段旁一个 `Browse...` 按钮、
`docs/WEBAPP.md` 文档、`tests/test_webapp.py` 用例。不碰运行语义、字段 key、默认值、
回填规则、作业模型、布局几何，不新增静态文件。

## 1. 契约（唯一权威版本）

### 1.1 后端：`GET /api/fs/list?dir=<绝对路径>&kind=<kind>`

- `dir` 缺省或空 → **根模式**；`kind` 缺省或未知 → `any`。
- 成功一律 `200`，响应体（键**必须**齐全，缺一不可）：

```json
{
  "dir": "R:\\songji\\programfile\\docs\\handoff\\webapp-file-picker\\assets\\fixture",
  "parent": "R:\\songji\\programfile\\docs\\handoff\\webapp-file-picker\\assets",
  "roots": [],
  "home": "C:\\Users\\ASUS",
  "kind": "fasta",
  "strip": [],
  "entries": [
    {"name": "sub", "path": "...\\fixture\\sub", "type": "dir", "size": null, "modified": 1758000000.0},
    {"name": "mini.fna", "path": "...\\fixture\\mini.fna", "type": "file", "size": 28, "modified": 1758000000.0}
  ],
  "truncated": false
}
```

- **根模式**：`dir`/`parent` 为 `null`，`roots` 非空（Windows：枚举 `A:\`..`Z:\` 中
  `os.path.exists` 为真的盘符，保持字母序；POSIX：`["/"]`），`entries` 为 `[]`。
- **目录模式**：`dir` = 实际列举的**绝对规范化**路径；`parent` = 上一级绝对路径，
  当该目录本身就是根（`os.path.dirname(dir) == dir`，例如 `R:\` 或 `/`）时 `parent` 必须是 `null`。
- `home` = `os.path.expanduser("~")`（两种模式都返回）。
- `kind` **回显**请求里解析后的 kind（非法值回显 `any`）。
- `strip` = 该 kind 的后缀剥离表（见 1.3），非 `db`/`index` 一律 `[]`。
- `entries` 元素：`type` 只能是 `"dir"` / `"file"`；目录 `size` 为 `null`；
  `path` 是绝对路径（`os.path.join(dir, name)` 的绝对形式）；`modified` 取 `os.path.getmtime`，
  取不到时允许为 `null`。
- **排序（必须确定）**：先目录、后文件；两组内部按 `name.lower()` 升序。
- **上限**：总条目最多 `2000`；被截断时 `truncated: true`，且**先保目录、再保文件**
  （即截断只可能发生在文件尾部）。
- 错误（沿用 `webapp/app.py:187-192` 的既有映射，**不要**改映射）：
  - `dir` 给了但不是已存在的目录 → 抛 `ValueError("Directory not found: <dir>")` → `400`。
  - 目录读不了 → 抛 `ValueError("Cannot read directory: <异常文本>")` → `400`。
  - 单个条目 `stat` 失败 → 跳过该条目（与 `webapp/app.py:345-346` 同风格），不影响整体。

### 1.2 kind 过滤表（唯一版本，放在 `webapp/schema.py`）

```python
FS_KINDS = {
    "any": (),
    "dir": (),          # 只列目录：文件一律不进 entries
    "fasta": (".fa", ".fasta", ".fna", ".fas", ".ffn", ".faa",
              ".fa.gz", ".fasta.gz", ".fna.gz", ".fas.gz"),
    "annotation": (".gtf", ".gff", ".gff3", ".gtf.gz", ".gff.gz", ".gff3.gz"),
    "bed": (".bed", ".bed.gz"),
    "db": (".nin", ".nhr", ".nsq", ".ndb", ".nog", ".nos", ".not",
           ".ntf", ".nto", ".njs", ".source.json"),
    "index": (".ggi", ".json"),
}
```

- 匹配方式：`name.lower().endswith(ext)`；`any` 不过滤；`dir` 只列目录。
- 目录**永远**列出（除 `any` 外任何 kind 都不许把目录过滤掉；`dir` 只是额外过滤掉文件）。

### 1.3 前缀剥离表（`FS_STRIP`，放在 `webapp/schema.py`，经接口 `strip` 字段下发给前端）

```python
FS_STRIP = {
    "db": (".source.json", ".nin", ".nhr", ".nsq", ".ndb", ".nog", ".nos",
           ".not", ".ntf", ".nto", ".njs"),
    "index": (".ggi", ".json"),
}
```

为什么会需要：`blastdb` 字段要的是 **BLAST 库前缀**（`blastn -db <prefix>`，
库文件是 `prefix.nin/.nsq/...` + 侧车 `prefix.source.json`，见
`shared/search/blast_utils.py:72-80`）；`index_path` 要的是**索引前缀**
（索引文件是 `prefix.ggi` + `prefix.json`，见 `shared/search/genome_index.py:330`）。
用户点中的是成员文件，写回字段时要把后缀剥掉。
剥离规则：按 `FS_STRIP[kind]` **从长到短**依次 `endswith` 检查，命中就剥掉一层、立即返回；
没有命中就原样写回（用户选的就是前缀本身，例如目录）。`strip` 必须是**已按长度降序排好的列表**。

### 1.4 前端：picker 弹层（id / class 契约，探针与 master 核验按此驱动）

静态 DOM 放在 `webapp/index.html` 的 `#drawer-scrim`（`webapp/index.html:179`）之后、`<script>` 之前：

- `#picker-scrim`（沿用现有 `.scrim` + `.hidden` 语义）
- `#picker`（`role="dialog"`、`aria-modal="true"`、`aria-labelledby="picker-title"`、初始带 `.hidden`）
- `#picker-title`、`#picker-path`（`type=text`，可手输/粘贴路径）、`#picker-go`、`#picker-up`、
  `#picker-close`、`#picker-roots`、`#picker-list`、`#picker-selected`、`#picker-cancel`、`#picker-ok`
- 列表行：`#picker-list .picker-row`，带 `data-path`、`data-type`（`dir` / `file`）属性，
  名称文本放在子元素 `.picker-name`；选中行加 class `selected`；根按钮用 class `.picker-root`。

行为（逐条必须实现）：

1. `openPicker(kind, currentValue, onPick)`：候选起始目录按顺序试
   `[currentValue, dirname(currentValue), localStorage['crispr.pickerDir'], 根模式]`，
   第一个返回 200 的胜出；前面的候选 400 时**静默**跳到下一个（首次打开不能白屏）。
2. 打开时 `#picker` 去掉 `.hidden`、`#picker-scrim` 去掉 `.hidden`，并把焦点放到 `#picker-path`。
3. `#picker-go` 或 `#picker-path` 里回车 → 列举该路径；失败时把错误文本写进 `#picker-list`
   （风格照 `webapp/static/app.js:1656-1658`），**不要**用 `showBanner`。
4. `#picker-up` → 进入 `parent`；`parent` 为 `null` 时点击无效果。
5. `#picker-roots` 里按 `roots` 生成按钮，点击即列举该根；`roots` 为空时该容器必须留空/隐藏。
6. 单击行 = 选中（高亮 + `#picker-selected` 显示该 `data-path`）；双击目录行 = 进入该目录；
   双击文件行 = 直接确认（等价于点 `#picker-ok`）。
7. `#picker-ok` 确认：`kind === 'dir'` → 写回选中目录的 `path`；没有选中行时，
   `kind === 'dir'` 写回**当前正在浏览的目录**，文件类 kind **什么都不做**（字段保持原值）。
   文件类 kind → 写回「选中文件 path 按 `strip` 剥掉后缀」的结果。
8. `#picker-cancel` / `#picker-close` / `Esc` / 点 `#picker-scrim` → 关闭且**字段值不变**。
9. 写回方式必须是：`input.value = picked;` 然后
   `input.dispatchEvent(new Event('input', {bubbles: true}));`
   —— 依赖 `webapp/static/app.js:638` 既有的 input 监听把值送进 `state.values` 并触发
   `schedulePreview()`。**不发这个事件等于没写回**（预览与提交都拿不到）。
10. 确认成功后把「当前列举目录」写进 `localStorage['crispr.pickerDir']`
    （复用 `readStorage`/`writeStorage`，`webapp/static/app.js:165-179`）。
11. **Esc 冲突（必须修）**：现有抽屉 Esc 处理在 `webapp/static/app.js:365-369`，
    它与 picker 都挂在 `document` 且注册在前，会先跑。必须把它改成
    `if (event.key === 'Escape' && state.drawerOpen && !isPickerOpen())`，
    保证 picker 打开时按 Esc **只关 picker、不关抽屉**。
12. 单实例：picker 逻辑只写一份，所有字段共用；不许每个字段各复制一套。

### 1.5 字段与 kind 的映射（每处都要有 `Browse...` 按钮）

`webapp/schema.py` 的路径字段用 `_field(..., kind=...)` 标注（`kind` 是**新增的字段属性**，
`build_schema()` 原样透传，`webapp/schema.py:351-356`，无严格 key 断言，见 §2）：

| 字段 key | kind | 位置 |
| --- | --- | --- |
| `search_fasta` | `fasta` | `webapp/schema.py:64` |
| `bed_regions` | `bed` | `webapp/schema.py:66` |
| `genome_fasta` | `fasta` | `webapp/schema.py:67` |
| `mask_fasta` | `fasta` | `webapp/schema.py:69` |
| `output_dir` | `dir` | `webapp/schema.py:70` |
| `blastdb` | `db` | `webapp/schema.py:71` |
| `index_path` | `index` | `webapp/schema.py:86` |

`webapp/index.html` 里手写的路径输入框（`schema` 不生成，需要 JS 侧一张表接上）：

| 元素 id | kind | 位置 |
| --- | --- | --- |
| `dp-download-output` | `dir` | `webapp/index.html:66` |
| `dp-genome` | `fasta` | `webapp/index.html:79` |
| `dp-annotation` | `annotation` | `webapp/index.html:83` |
| `dp-output` | `dir` | `webapp/index.html:87` |
| `dp-blastdb` | `db` | `webapp/index.html:91` |
| `dp-index-prefix` | `index` | `webapp/index.html:95` |
| `outputs-dir` | `dir` | `webapp/index.html:267` |

按钮文案固定 `Browse...`（ASCII，和现有界面一致），class `browse-btn`，
`type="button"`，并带 `data-kind`。

## 2. 现状证据（master 已核实，可直接引用）

后端：

- `webapp/app.py:39` — `HOST = "127.0.0.1"`，只绑本机。
- `webapp/app.py:44-48` — `STATIC_WHITELIST` 只放行 `app.js` / `styles.css`；
  **新增静态文件必须同时登记白名单**，所以本任务把样式/脚本追加到现有两个文件里。
- `webapp/app.py:53-57` — `OUTPUT_EXTENSIONS`（`/api/outputs` 的白名单）。
- `webapp/app.py:160-171` — `do_GET` 的分发点，`/api/outputs` 在 `:169-171`；
  新路由插在它后面。
- `webapp/app.py:187-192` — 错误映射：`ValueError`→400、`FileNotFoundError`→404、
  其它→500。`_api_fs_list` 用 `ValueError` 即可拿到 400。
- `webapp/app.py:321-347` — `_api_outputs` 是现成模板（校验 `isdir`、`os.listdir`、
  跳过 `stat` 失败项、返回 `{"dir": ..., "files": [...]}`）。
- `webapp/app.py:350-356` — `main()` 的 `--port` / `--host`。
- 实测（master，2026-09-16）：`python -m unittest tests.test_webapp -v`
  → `Ran 56 tests in 47.508s` / `OK`（Python 3.14.7）。这是**基线绿**，
  改完必须仍是 56+新增 全绿。

字段定义：

- `webapp/schema.py:57-60` — `_field(key, label, **extra)`，`extra` 直接并入字段字典，
  所以加 `kind=` 不用改这个函数。
- `webapp/schema.py:63-74` — `COMMON_FIELDS`（7 个字段，含 5 个 `type="file"`/`"dir"`）。
- `webapp/schema.py:86` — `RUN_FIELDS` 的 `index_path`（`type="file"`）。
- `webapp/schema.py:351-356` — `build_schema()` 把 `common_fields` / `run_fields`
  **原样**放进 `designer`，字段多一个键不会影响任何消费方。
- `tests/test_webapp.py:225-235`（`test_pattern_form_field_keys_exist`）只校验
  `field["key"]` 属于 `field_keys`，**没有**对字段字典做严格等于断言 → 加 `kind` 安全。

前端：

- `webapp/static/app.js:47-64` — `el(tag, attrs, children)` 工具。
- `webapp/static/app.js:82-102` — `api(path, options)`：非 2xx 抛 `Error(体里的 error)`。
- `webapp/static/app.js:165-179` — `readStorage` / `writeStorage`（`localStorage` 包装）。
- `webapp/static/app.js:365-369` — 抽屉的 `keydown` Esc 处理（见 1.4 第 11 条的冲突点）。
- `webapp/static/app.js:612-645` — `renderField(field)`：`check` / `combo` 之外走
  `el('input', {type: 'text'})` + `input` 监听（`:636-639`），是本任务要挂按钮的地方。
- `webapp/static/app.js:723-759` — `renderCommon()` 用 `renderField` 渲染 `common_fields`。
- `webapp/static/app.js:808-819` — `renderRun()` 用 `renderField` 渲染 `run_fields`
  （`index_path` 会走到同一处）。
- `webapp/static/app.js:1625-1659` — `loadOutputs()`：`api('/api/outputs?...')` 的
  调用/错误文本风格模板（`:1656-1658`）。
- `webapp/static/app.js:1661-1665` — `initResults()`；`:1669-1672` — `init()`（挂新初始化函数）。
- `webapp/index.html:66,79,83,87,91,95,267` — 7 个手写路径输入框（见 1.5 表）。
- `webapp/index.html:179` — `#drawer-scrim`；`:275-277` — `<script>`/`</body>`。
- `webapp/static/styles.css:29` — `.hidden { display: none !important; }`（弹层显隐统一用它）。
- `webapp/static/styles.css:152-157` — `.scrim`（fixed + inset + z-index）。
- `webapp/static/styles.css:210-219` — `.field`；`:245` — `.row`（`display:flex; gap:8px`）；
  `:247` — `.actions`。

外部依赖的事实（写 `strip` 用）：

- `shared/search/blast_utils.py:72-80` — BLAST 库判存在看 `.nin`/`.nsq`，侧车是 `<prefix>.source.json`。
- `shared/search/genome_index.py:330` — 索引是 `<prefix>.ggi` + `<prefix>.json`。

现成探针骨架（master 复现用，servant 直接复用）：

- `docs/handoff/webapp-big-prep-panel/assets/probe_browser_cdp.js`
  （Node + CDP 驱动 headless Edge，`node probe_browser_cdp.js <页面内表达式文件>`，
  支持 `awaitPromise`，环境变量 `CDP_PORT` / `APP_URL` / `WAIT_MS`）。
- 本机实测路径：node = `C:\Users\ASUS\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe`（v24.19.0）；
  Edge = `C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe`。

## 3. 必做改动

- [ ] P0-1 后端列目录接口
  - 位置：`webapp/schema.py` 新增 `FS_KINDS` / `FS_STRIP`（1.2、1.3 表）；
    `webapp/app.py` 新增 `FS_ENTRY_LIMIT = 2000` 与 `_api_fs_list(query)`，
    并在 `do_GET` 的 `webapp/app.py:171` 之后加 `if path == "/api/fs/list": self._api_fs_list(query); return`。
  - 期望行为：严格按 §1.1 / §1.2 / §1.3。响应键齐全，排序与 `parent` 规则按 §1.1。
  - 证据要求：`report.md` 贴 `test_fs_list_route` 的完整输出。

- [ ] P0-2 字段标注 kind
  - 位置：`webapp/schema.py:64,66,67,69,70,71,86`（1.5 表）。
  - 期望行为：每个 `type` 为 `file`/`dir` 的字段都带 `kind`，取值必须属于 `FS_KINDS`。

- [ ] P0-3 picker 弹层与按钮
  - 位置：`webapp/index.html`（`#drawer-scrim` 之后插 DOM）、
    `webapp/static/app.js`（`renderField` 挂按钮、新增 picker 模块、`init()` 挂初始化、
    改 `:366` 的 Esc 条件）、`webapp/static/styles.css`（新增 `.browse-btn` / `.picker*`）。
  - 期望行为：§1.4 的 12 条 + §1.5 的两张映射表。`renderField` 只对
    `field.type === 'file' || field.type === 'dir'` 加按钮，其它类型渲染结果**不许变**。
  - 注意（已知坑）：`#dp-*` / `#outputs-dir` 的输入框在 `.field` 里，按钮要用一个
    `.row` 把「输入框 + 按钮」包起来；`.row` 是 `flex-wrap: wrap`（`styles.css:245`），
    必须同时给 `.row > input[type=text]` 补 `flex: 1 1 220px; min-width: 0;`，
    否则抽屉收窄到 380px 时输入框会被按钮挤扁（见 §6 的 DOM 断言）。
  - 证据要求：`report.md` 贴 §6 的探针 JSON 原文。

- [ ] P0-4 测试
  - 位置：`tests/test_webapp.py`，在 `test_outputs_route`（`:647-657`）附近新增
    `HandlerRouteTests.test_fs_list_route`；在 `SchemaTests`（`:204-241`）新增
    `test_path_fields_carry_a_browse_kind`。
  - 期望行为（`test_fs_list_route` 至少要覆盖）：
    1. `GET /api/fs/list`（无参数）→ 200，`dir is None`、`parent is None`、`roots` 非空、`entries == []`；
    2. `dir` 指向不存在路径 → 400；
    3. 自建目录（`self.tmp.name` 下，含 `sub/`、`mini.fna`、`notes.txt`、`mini.blastdb.nin`、`miniindex.ggi`）：
       - `kind=fasta` → 名字顺序恰为 `["sub", "mini.fna"]`；
       - `kind=dir` → `["sub"]`；
       - `kind=any` → `["sub", "mini.blastdb.nin", "mini.fna", "miniindex.ggi", "notes.txt"]`；
       - `kind=db` → 含 `mini.blastdb.nin`、不含 `mini.fna`，且 `strip[0] == ".source.json"`；
       - 每个 `entry["path"]` 都是绝对路径且等于 `join(dir, name)`；`truncated is False`；
       - `parent` 等于 `self.tmp.name`（子目录再上一层）。
    4. 错误信息用 `assertIn`，别断言整句（便于以后改文案）。
  - 期望行为（`test_path_fields_carry_a_browse_kind`）：`common_fields` + `run_fields` 里
    所有 `type in ("file", "dir")` 的字段都有 `kind` 且 `kind in schema_module.FS_KINDS`。
  - 证据要求：`report.md` 贴 `python -m unittest tests.test_webapp -v` 原文与计数。

- [ ] P1-1 文档
  - 位置：`docs/WEBAPP.md:185`（API 表）加一行
    `| GET | /api/fs/list?dir=<绝对路径>&kind=<kind> | 只读列目录（kind 过滤、strip 剥离表、roots 根模式） |`；
    在「API」表之后（`docs/WEBAPP.md:201` 附近）加一小节「路径浏览选取器」写清：
    字段→kind 映射表、picker 的 id/行为要点、`strip` 语义、以及
    「浏览器原生文件框拿不到服务端绝对路径，所以不用 `<input type="file">`、不上传」的理由；
    在「安全边界」（`docs/WEBAPP.md:203-210`）加一句：`/api/fs/list` 只读、只返回名字/大小/时间，
    不读文件内容、不写盘，服务仍只绑 `127.0.0.1`。
  - 期望行为：中文说明与实现一致，行号锚点不必写进文档。

- [ ] P1-2 断言不回归
  - `webapp/app.py:53-57` 的 `OUTPUT_EXTENSIONS` 与 `_api_outputs`（`:321-347`）**行为不变**
    （`test_outputs_route` 必须继续绿）。
  - 三种模式的字段渲染、回填规则、作业模型、抽屉几何都不变。

## 4. 不要做的事

- 不要用 `<input type="file">` / `showDirectoryPicker()` / `webkitdirectory` 当实现。
- 不要新增上传接口、不要往磁盘写任何用户文件、不要改 `_api_outputs` 的行为或白名单。
- 不要新增 `.js` / `.css` 文件（`webapp/app.py:44-48` 白名单）；样式脚本追加进现有两个文件。
- 不要改字段 key、默认值、`MODE_LABELS`、预设、Run Settings 的取值集合。
- 不要改 `/api/**` 已有路径的方法/响应键；新接口只加不删。
- 不要改 `webapp/index.html` 里已有的 `dp-*` / `outputs-*` 控件 id 与结构（只允许在文件末尾追加 picker DOM）。
- 不要动 `shared/` 下任何文件、不要动 `docs/WEBAPP.md` 与 `tests/test_webapp.py` 之外的文件（README 也不动）。
- 不要在 `report.md` 之外的地方记录「已完成」；不要跑全量套件（`run_tests.py`）或大规模服务器跑批。
- 不要用 `Get-Content`/`Set-Content` 改带中文的文件（编码安全，见 §7）。
- 不要顺手修其它 bug（写进 `report.md` 的「附带发现」）。

## 5. 决策项（未确认则按推荐执行）

- D1（已锁）方案 = 服务端只读列目录 + 页面内自绘弹层；不做上传、不用原生文件框。
- D2（已锁）接口形态 = `GET /api/fs/list`，响应键与 §1.1 完全一致。
- D3（已锁）kind 取值 = `any|dir|fasta|annotation|bed|db|index`，表在 `webapp/schema.py`。
- D4（已锁）`strip` 由服务端下发，`db` = `.source.json` + BLAST 成员后缀，`index` = `.ggi/.json`。
- D5（已锁）条目上限 2000，先目录后文件，超限 `truncated: true`。
- D6（已锁）picker 的 DOM id/class 按 §1.4，供探针与核验驱动，**不许改名**。
- D7 弹层是否复用现有 `.scrim` 样式 → 推荐：新写 `#picker-scrim` 复用 `.scrim` 这个 class，
  z-index 高于抽屉（抽屉是 40，遮罩 35）→ 推荐 `.picker` 用 60、`#picker-scrim` 用 55，
  理由：picker 可能从抽屉内部打开，必须压在抽屉上面。
- D8 起始目录顺序（§1.4 第 1 条）未确认也按推荐执行，不要问用户。

## 6. 轻量自检（servant 的检验上限）

按顺序做，全部要贴原文：

```powershell
# 1) 语法
python -m py_compile webapp\app.py webapp\schema.py
& 'C:\Users\ASUS\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe' --check webapp\static\app.js

# 2) 聚焦单测（基线：56 tests OK）
python -m unittest tests.test_webapp -v

# 3) DOM 级探针（必须跑；这是本任务唯一的“真跑一遍界面”证据）
#    终端 A：起服务
python webapp\app.py --port 8351
#    终端 B：headless Edge + CDP（这条会一直占着，别等它返回）
& 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe' --headless=new --disable-gpu --no-first-run --user-data-dir="$env:TEMP\edgeprobe_picker" --remote-debugging-port=9333 about:blank
#    终端 C：跑探针
$env:CDP_PORT='9333'; $env:APP_URL='http://127.0.0.1:8351/'; $env:WAIT_MS='9000'
& 'C:\Users\ASUS\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe' docs\handoff\webapp-file-picker\assets\probe_browser_cdp.js docs\handoff\webapp-file-picker\assets\probe_picker_flow.js
```

- `probe_browser_cdp.js` **已在 `assets/probe_browser_cdp.js` 就位**（与 big-prep-panel 版本逐字节相同），不要改它。
- `assets/probe_picker_flow.js` 由 servant 新写，是**页面内表达式**
  （async IIFE，`return JSON.stringify(...)`），固定目录用本任务自带的
  `R:\songji\programfile\docs\handoff\webapp-file-picker\assets\fixture`
  （JS 里写成 `'R:\\songji\\...\\fixture'`）。
- 探针必须断言并输出（键名照抄，便于 master 比对）：
  - `genomeFastaHasBrowseButton`（`Common Inputs` 的 `genome_fasta` 字段内有 `.browse-btn`）= `true`；
  - 点该按钮后 `pickerOpenAfterClick` = `true`、`pickerPathFocused`（软断言，只记录）；
  - 把 `#picker-path` 设为 fixture 目录 → 点 `#picker-go` → `fastaRowNames`
    （`#picker-list .picker-row .picker-name` 文本数组，`kind=fasta`）== `["sub", "mini.fna"]`，
    且 `fastaHidesNotesTxt`（`notes.txt` 不出现）= `true`；
  - 双击 `mini.fna` 行后：`pickerClosedAfterPick` = `true`、
    `genomeFastaValue` == `R:\songji\programfile\docs\handoff\webapp-file-picker\assets\fixture\mini.fna`、
    `inputEventFired`（探针自己先挂一个 `input` 监听计数）= `true`；
  - `blastdb` 字段（`Run Settings` 的 `Index Prefix` 与抽屉的 `dp-blastdb` 至少验一个）：
    浏览 fixture、选 `mini.blastdb.nin` → 写回值以 `...\fixture\mini.blastdb` 结尾（**后缀已剥离**）；
  - `escKeepsDrawerOpen`：抽屉打开 → 开 picker → 派发 `Escape` → picker 关、抽屉仍开；
  - `windowErrors` == `[]`（页面内 `window.addEventListener('error', ...)` 收集）。
- 探针跑不起来（Edge/CDP 起不来）时**必须**在 `report.md` 里写明失败原文并停下报告，
  不许跳过、不许用「静态检查代替」。

## 7. 交付要求

- 改前快照：把 `webapp/app.py`、`webapp/schema.py`、`webapp/index.html`、
  `webapp/static/app.js`、`webapp/static/styles.css`、`tests/test_webapp.py`、
  `docs/WEBAPP.md` 复制到 `backup/20260916_webapp_file_picker/`（保相对路径）。
- 编码安全：所有改动文件保持 **UTF-8 无 BOM + LF**；`app.js` / `styles.css` / `*.md` 里
  不要引入 CRLF；不要用 `Get-Content`/`Set-Content` 读写带中文的文件
  （见 `encoding-safe-editing` 技能：中文 Windows 的 PowerShell 会静默毁掉 UTF-8）。
- 完成后：`state.json` 置 `ready_for_review`（`round` 保持 1），写 `report.md`
  （改动文件+行号、命令原文与输出、未做项、附带发现、待明确）。
- 交付后给用户这句可转发的话：
  `本会话是 master，核验 <repo>/docs/handoff/webapp-file-picker/。`
## 8. 补充说明（master 实测，避免误判）

- 本任务自带的 fixture 目录
  `docs/handoff/webapp-file-picker/assets/fixture/` 实际内容：
  `mini.fna`(28B)、`notes.txt`(12B)、`regions.bed`(11B)、`mini.blastdb.nin`(9B)、
  `mini.blastdb.nsq`(9B)、`mini.blastdb.source.json`(20B)、`miniindex.ggi`(9B)、
  `miniindex.json`(31B)、`sub/inner.gtf`(40B)。
- master 已用与 §1.2 相同的规则实测该目录的列举结果（目录在前，文件按 `name.lower()` 升序）：
  - `kind=any` → `sub`, `mini.blastdb.nin`, `mini.blastdb.nsq`, `mini.blastdb.source.json`,
    `mini.fna`, `miniindex.ggi`, `miniindex.json`, `notes.txt`, `regions.bed`
  - `kind=fasta` → `sub`, `mini.fna`
  - `kind=annotation` → `sub`（`inner.gtf` 在 `sub/` 内，顶层没有注释文件）
  - `kind=bed` → `sub`, `regions.bed`
  - `kind=db` → `sub`, `mini.blastdb.nin`, `mini.blastdb.nsq`, `mini.blastdb.source.json`
  - `kind=index` → `sub`, `mini.blastdb.source.json`, `miniindex.ggi`, `miniindex.json`
    （`.source.json` 也以 `.json` 结尾，**会**被 `index` 列出；这是预期行为，不要为它加特例）
- 所以探针里 `kind=index` 只按名字精确挑 `miniindex.ggi`，不要断言「列表里只有 ggi/json 成员」。
- `#picker-path` 是手输框：探针直接给它赋 `value` 再点 `#picker-go` 即可，不需要模拟键盘输入。
- 探针是页面内表达式，`return` 的必须是字符串（`JSON.stringify(...)`）；要驱动异步流程就用
  `(async function () { ... return JSON.stringify(out, null, 2); })()`，
  runner 已开 `awaitPromise: true`。

## 9. Round 2 追加：把选取器做成「资源管理器式」

- round: 2（本节由 master 追加；§0–§8 是 round 1 原文，保持原样）
- 用户原话：「现在的浏览太简陋了，能否一点开显示当前目录，然后可以像文件资源管理器那样选择」
- 本轮目标：**只改选取器（picker）的交互与呈现，外加 `/api/fs/list` 增加一个 `hidden` 查询参数**。字段映射、写回语义、`strip` 规则、Esc 规则、错误映射、排序与 2000 上限一律不变。
- **兼容门槛（硬性）**：round 1 的 6 个探针必须继续全绿 —— `assets/probe_picker_flow.js`（round 1 servant 写的）、`assets/probe_master_picker.js`、`probe_master_picker2.js`、`probe_master_picker3.js`、`probe_master_picker4.js`、`probe_master_picker5.js`（master 的回归探针）。为满足它，以下约束不可违反：
  - `#picker-list` 里**只有数据行**用 class `picker-row`；表头必须换 class（建议 `.picker-head-row`），因为探针按 `#picker-list .picker-row` 数行。
  - `#picker-roots` 仍是盘符按钮容器、子元素仍是 `.picker-root`；新增的位置条目用别的 class（建议 `.picker-place`），不要塞进 `#picker-roots`。
  - `#picker`、`#picker-scrim`、`#picker-path`、`#picker-go`、`#picker-up`、`#picker-close`、`#picker-list`、`#picker-selected`、`#picker-cancel`、`#picker-ok` 的 id 与语义不变；`#picker` 仍 `z-index:60`、`#picker-scrim` 仍 `55`。
  - 行仍带 `data-path` / `data-type`，名称仍在子元素 `.picker-name`；单击选中、双击目录进入、双击文件确认不变。
  - `#picker-path` 手输框与「回车列举」保留。
  - master 的探针文件与 `assets/fixture/` **不许改**。

### 9.1 现状证据（round 1 交付后 master 实测，可直接引用）

- `webapp/index.html:181-202` — 弹层 DOM：标题 +（`#picker-path`(189) / `#picker-go`(190) / `#picker-up`(191)）一行 → `#picker-roots`(193) → `#picker-list`(194) → 底部 `#picker-selected`(196) + Cancel/OK(198/199)。**没有面包屑、没有列头、没有侧栏、没有前进/后退**。
- `webapp/static/app.js:1778-1821`（`openPicker`）— 候选顺序 `[currentValue, dirNameOf(currentValue), localStorage['crispr.pickerDir'], '']`，**没有 home**；首个 200 胜出，其余静默跳过。
- `webapp/static/app.js:1823-1834`（`applyPickerListing`）— 每次都把 `picker.selected = null`、清空 `#picker-selected`：**打开后不会高亮字段里已有的值**，用户得自己在列表里找。
- `webapp/static/app.js:1857-1871`（`pickerRow`）— 行 = `.picker-icon`（目录 `[dir]`、文件空）+ `.picker-name` + `.picker-meta`（只有 `formatSize(size)`）：**没有修改时间、没有列头**。
- `webapp/static/app.js:1846-1855`（`renderPickerRoots`）— 盘符按钮平铺在顶部，**没有「位置」（home / 最近目录）概念**。
- `webapp/static/app.js:1991-2020`（`initPicker`）— 只有 `#picker-go` 点击、`#picker-path` 回车、`#picker-up`、close/cancel/ok、scrim 点击、Esc：**没有 ↑/↓ 选择、没有 Enter/Backspace、没有前进后退**。
- `webapp/static/app.js:1954-1976`（`confirmPicker`）— 文件类 kind 且无选中时直接 `return`：既不写回也不关闭（round 1 核验记为 P3「点了没反应」）。
- `webapp/static/styles.css:455-460`（`.picker`）— 宽 `min(880px, 100vw-40px)`、单列；`webapp/static/app.js:641-650` 包装出的 `.row` 在结果区 `#outputs-dir`（`webapp/index.html:289-292` 的 `.actions` 内）收缩到 265px、`Browse...` 换行（round 1 核验 P3 #2）。
- `webapp/app.py:365-434`（`_api_fs_list`）— 只认 `dir` 与 `kind`：**没有 `hidden`**，所以 `C:\` 下 `$Recycle.Bin`、`Config.Msi`、`System Volume Information`、`pagefile.sys` 之类会全部列出。
- 目录样本（master 实测）：`R:\` 根 38 个可见目录、**0 个隐藏项**；`C:\` 根（前 40 个条目里）13 个隐藏项：`$Recycle.Bin`、`.GamingRoot`、`Config.Msi`、`DumpStack.log.tmp`、`Finish.log`、`PageFile`、`ProgramData`、`Recovery`、`System Volume Information`、`devlist.txt`、`hiberfil.sys`、`pagefile.sys`、`swapfile.sys`。

### 9.2 必做项

- [ ] P0-1 打开即定位并高亮「当前值」
  - `openPicker`（`app.js:1778`）候选顺序改为：`字段值 → 其所在目录 → localStorage['crispr.pickerDir'] → home（新） → 根模式('')`；`home` 用响应里的 `home`（在 `applyPickerListing` 处存进 `picker.home`）。
  - 列出后，若字段当前值能在列表里对上号，就把它设为选中：`picker.selected` 就绪、行加 `selected`、`#picker-selected` 显示其 `data-path`，并 `row.scrollIntoView({block: 'nearest'})`。
  - 匹配算法（唯一版本）：
    - 值是目录（`kind === 'dir'`，或 `basename(value)` 等于某个 `dir` 行的 `name`）→ 选中该目录行；
    - `kind` 为 `db` / `index`（字段存的是前缀）→ 先找 `name === basename(value)`，找不到再找 `name` 形如 `basename(value) + strip 中任一后缀`（命中即选中）；
    - 其它文件类 kind → 找 `name === basename(value)`；
    - 都不命中就不选中（与 round 1 相同）。
  - 其余写回/双击/单击语义不变；`dir` 类「无选中时 OK = 当前目录」不变。
- [ ] P0-2 面包屑（保留地址栏）
  - 新增 `#picker-crumbs`（放在路径行**下方**）：按路径分隔符切段，每段 `<button class="picker-crumb">`，分隔符 `>`（或 `\u203A`）；每段可点（跳该级），末段也渲染、点击无动作；打开/跳转/手输回车后刷新，末段 `scrollIntoView` 保证可见；根模式下清空。
- [ ] P0-3 列头与行信息
  - `#picker-list` 顶部新增表头 `div.picker-head-row`（**不要用 `.picker-row` 类**）：`Name` / `Size` / `Modified`，列宽 = 名称 `flex:1`、大小 `90px` 右对齐、时间 `150px`。
  - 行三列：`.picker-name`（保留）+ `.picker-size`（复用 `formatSize`，目录留空）+ `.picker-mod`（新增 `formatStamp(epochSeconds)` → 本地 `YYYY-MM-DD HH:MM`，取不到留空）。原 `.picker-meta` 作为容器 class 保留（探针只用 `.picker-name`）。
  - 目录行 `.picker-icon` 用 `▸` 或保留 `[dir]`；文件行留空。
  - 排序**不变**（先目录、后文件，均 `name.lower()` 升序）；表头**不可排序**（点了不变）。
- [ ] P0-4 导航历史与键盘
  - 新增 `#picker-back` / `#picker-forward`（挨着 `#picker-up`），历史最多 50 条；无历史时 `disabled`；点击后 `pickerGoTo`，且**不**新增历史项（避免来回抖动）。
  - 键盘（picker 打开时挂 `document`；当 `document.activeElement === #picker-path` 时只处理 `Escape`）：`ArrowDown`/`ArrowUp` 移动选中（到底/到顶停在原位，不循环）、`Enter`（选中目录→进入；选中文件→确认写回）、`Backspace`→上一级（`parent` 为 null 时无动作）、`Escape` 关弹层（round 1 规则不变）；`#picker-path` 里的 `Enter` 仍是列举。
  - 键盘事件必须能被 `document.dispatchEvent(new KeyboardEvent('keydown', {...}))` 驱动（探针就是这么做的）。
- [ ] P0-5 「位置」栏
  - 新增 `#picker-places`（放 `#picker-roots` 之后、`#picker-list` 之前；一行/一栏均可，不做树）：条目 = `Home`（path = `home`）+ 最近目录（`localStorage['crispr.pickerRecent']`，JSON 数组，最多 5 条、最近在前、去重）。条目 class 用 `picker-place`，点击跳转。
  - 确认写回时把**当前列举目录** push 进 `crispr.pickerRecent`（去重、截 5 条），并保留 `crispr.pickerDir`（round 1 行为不变）。
  - 明确不做：可展开目录树（以后再说）。
- [ ] P0-6 无选中时的 OK 状态（修 round 1 P3 #1）
  - 文件类 kind 无选中：`#picker-ok` 置 `disabled`，`#picker-selected` 显示 `Select a file`；一有选中即恢复可用并显示该路径。
  - `dir` 类 kind：`#picker-ok` 始终可用（无选中时写当前目录，round 1 行为不变）。
  - 新增 `#picker-here`（文案 `Use this folder`）：仅 `dir` 类 kind 显示（其它 kind 加 `.hidden`），点击 = 写回当前目录。
- [ ] P1-1 `/api/fs/list` 增加 `hidden` 参数（默认过滤隐藏项）
  - `webapp/app.py`（`_api_fs_list`，`app.py:365-434`）新增查询参数 `hidden`：`1`/`true`/`yes` = 显示隐藏项，其余（含缺省）= 不显示。
  - 判定规则（唯一版本，写在一处并加注释）：名字以 `.` 开头 → 隐藏；Windows（`os.name == 'nt'`）且 `os.stat(path).st_file_attributes & stat.FILE_ATTRIBUTE_HIDDEN` → 隐藏；`stat` 失败按「不隐藏」处理。
  - 过滤在 kind 过滤之后、排序之前；仍计入 `FS_ENTRY_LIMIT`(2000) 与 `truncated`；**响应键不增不减**（`dir/parent/roots/home/kind/strip/entries/truncated`），条目字段仍是 `name/path/type/size/modified`。
  - 弹层新增 `#picker-hidden`（`type=checkbox`，label `Show hidden`）；状态存 `localStorage['crispr.pickerHidden']`（`'1'`/`'0'`）；切换后立即重列当前目录（面包屑与选中逻辑照旧）。
  - 文档：`docs/WEBAPP.md:186` 的 API 行补 `&hidden=1`；「路径浏览选取器」小节（`:204-256`）说明默认隐藏 `.` 开头与 Windows 隐藏属性项。
  - 测试：`tests/test_webapp.py` 新增 `test_fs_list_hidden_filter`：`tempfile` 目录里建 `.dot.fna` 与 `plain.fna`，另建一个用 `ctypes.windll.kernel32.SetFileAttributesW(path, 0x80 | 0x2)` 设为隐藏（**本机 NTFS 可行，master 已实测 `ok=True`；Samba 盘不行，返回 50**），断言缺省 `kind=fasta` 只有 `plain.fna`、`hidden=1` 时三者齐全且顺序正确；属性那条用 `unittest.skipUnless(os.name == 'nt', ...)` 包住，点号那条必须所有平台都跑。
- [ ] P1-2 视觉与文案
  - `.picker` 宽 `min(1040px, calc(100vw - 40px))`、高 `min(80vh, calc(100vh - 60px))`；`.picker-list` `min-height: 260px`。
  - 列表上方右侧加 `#picker-count`（`.muted`）：`3 folders, 12 files`；`truncated` 时追加 ` (listing truncated)`。
  - 文案一律英文（与现有界面一致）：`Show hidden`、`Use this folder`、`Select a file`、`Home`、`Recent`。
  - 修 round 1 P3 #2：给 `renderField`（`app.js:644`）与 `attachBrowseButton`（`app.js:1739`）包装出的行加 class `path-row`，CSS 里加 `.path-row { flex: 1 1 220px; min-width: 0; }`，让结果区 `#outputs-dir` 恢复宽度、`Browse...` 回到同一行。

### 9.3 不要做的事（本轮）

- 不改 round 1 的 id / 语义 / 探针依赖（见本节开头的兼容门槛）。
- 不改 `/api/fs/list` 的既有响应键、排序、2000 上限、错误映射与 `400` 文案；只加 `hidden`。
- 不新增 `.js` / `.css` 文件（`webapp/app.py:45-48` 白名单）；样式脚本追加进现有两个文件。
- 不做可展开目录树、拖放、文件内容预览、排序切换；不做上传；不用原生 `<input type=file>` / `showDirectoryPicker()`。
- 不改字段 key / 默认值 / 预设 / 作业模型 / 抽屉几何；不动 `shared/`；不改 `_api_outputs`；不碰 `scy-test/`、`logs/`。
- 不跑全量套件（`run_tests.py`）。
- 仍然禁止用 `Get-Content`/`Set-Content` 改带中文的文件（编码安全见 §7）。

### 9.4 决策默认值（未确认则按推荐执行）

- D8 = 只升级 picker + 新增 `hidden` 参数，其它不动。
- D9 = 起始目录链：字段值 → 其目录 → `crispr.pickerDir` → `home` → 根模式。
- D10 = 打开时高亮字段当前值对应行（`db`/`index` 用前缀反查）。
- D11 = 面包屑在路径行下方、`>` 分隔、每段可点；手输框保留。
- D12 = 列头 `Name / Size / Modified`；排序固定、不可点。
- D13 = 键盘 ↑↓ / Enter / Backspace / Esc；前进后退历史上限 50。
- D14 = 隐藏项默认不显示，`hidden=1` 显示，勾选框记忆在 `crispr.pickerHidden`。
- D15 = 文件类 kind 无选中时 `#picker-ok` 置灰；`#picker-here` 仅 `dir` 类显示。
- D16 = 位置栏只做 Home + 最近 5 个，不做树。

### 9.5 夹具与期望值（master 已备好）

- `assets/fixture/`（round 1 用）**不要动**：round 1 探针依赖它的精确名单。
- 新增 `assets/fixture2/`（master 已建）：`plain.fna`(16B)、`.dotfile.fna`(10B)、`sub/deep.gtf`。
  - `kind=fasta` 缺省 → `["sub", "plain.fna"]`；`hidden=1` → `["sub", ".dotfile.fna", "plain.fna"]`；
  - `kind=any` 缺省 → `["sub", "plain.fna"]`；`hidden=1` → `["sub", ".dotfile.fna", "plain.fna"]`。
  - 注意：本共享盘是 Samba，点号文件本身就会被报成隐藏属性，且 `SetFileAttributesW` 在该盘返回 50（不支持）——属性位请在**本机 NTFS 临时目录**上测（`tempfile`，master 实测可行）。
- `C:\` 根可作属性分支的实测样本（13 个隐藏项见 §9.1），`R:\` 根是 0 个隐藏项的对照。

### 9.6 servant 自检与报告

- 语法：`python -m py_compile webapp\app.py webapp\schema.py tests\test_webapp.py` + `node --check webapp\static\app.js`。
- 聚焦单测：`python -m unittest tests.test_webapp -v`（含新增 `test_fs_list_hidden_filter`）。
- 页面探针：**新写** `assets/probe_picker_explorer.js`（页面内表达式，仍用 `assets/probe_browser_cdp.js` 运行），至少断言并输出：`openHighlightsCurrentValue`（`.selected` 行名字 + `#picker-selected` 文本）、`crumbCount` / `crumbTexts`、`headRowCells`、`countText`、`downArrowMovesSelection`、`enterEntersDir` / `enterConfirmsFile`、`backspaceGoesUp`、`backButtonEnabled` / `backGoesBack`、`hereVisibleForDirKind` / `hereWritesCurrentDir`、`okDisabledForFileKindWithoutSelection`、`hiddenToggleHidesDotfile`（fixture2 上切勾选框前后名单）、`windowErrors`。
- **回归**：round 1 的 6 个探针改后必须重跑通过，报告里至少贴 `fastaNamesExact`、`pickerClosedAfterPick`、`escKeepsDrawerOpen`、`driveRootUpIsNoop`、`narrowAllUsable` 这几个键的原值。
- 报告照 §7 写（改动文件+行号、命令原文与输出、未做项、附带发现、待明确）；`state.json` 置 `ready_for_review`（`round` 保持 2）。
- 交付后给用户这句：`本会话是 master，核验 R:\songji\programfile\docs\handoff\webapp-file-picker\（round 2）。`

### 9.7 改前快照（本轮）

- 复制到 `backup/20260916_webapp_picker_explorer/`（保相对路径）：`webapp/app.py`、`webapp/schema.py`、`webapp/index.html`、`webapp/static/app.js`、`webapp/static/styles.css`、`tests/test_webapp.py`、`docs/WEBAPP.md`。

### 9.8 Round 2 核验补充（master 追加，2026-09-16）

round 2 已核验通过（结论见 `review.md` 的「Round 2 核验（master）」）。本节只记录**规格更正**与**规格留白**，
不改任何实现要求；§9.1-§9.7 的正文保持原样备查。

1. **D9 更正**（与 §9 开头的硬性兼容门槛对齐）：
   - **字段有值**时起始链 = `字段值 → 其所在目录 → crispr.pickerDir → home → 根模式`；
   - **字段为空**时跳过 `home`，直接落到根模式（`Home` 仍是位置栏第一项，一点即到）。
   - 理由：`probe_master_picker.js` §13 与 `probe_master_picker2.js` §7 把「空白字段 → 根模式」钉死，属 §9 开头的硬性兼容门槛，优先级高于 D9 的字面顺序。`docs/WEBAPP.md` 已按本条语义写。
2. **§9.5 的 fixture2 期望名单更正**：`assets/fixture2/` 实际含 `plain.fna`、`.dotfile.fna`、`attr-hidden.fna`、`sub/deep.gtf`。
   `attr-hidden.fna` 是 master 建夹具时多放的文件（22:20:11 创建，未写进 §9.5；本共享盘是 Samba，设不了 `FILE_ATTRIBUTE_HIDDEN`，所以它并不隐藏）。
   正确期望：缺省 `["sub", "attr-hidden.fna", "plain.fna"]`；`hidden=1` → `["sub", ".dotfile.fna", "attr-hidden.fna", "plain.fna"]`。
   点号那条期望（`.dotfile.fna` 只在 `hidden=1` 出现、排在 `sub` 之后）不变。夹具文件本身保留。
3. **规格留白（核验时已裁定，无需改动）**：根模式下 `#picker-count` 留空；位置栏的最近目录条目用**目录路径**作标签（没有 `Recent` 字样）；键盘 `Enter` 选中目录行 = 进入（不是写回）。
4. **既有问题（非本轮引入，建议另开一轮）**：抽屉在 380px 且 models 表渲染后横向滚动 655px（`table.models-table` 626px，`.table-wrap` 缺 `overflow-x`）；`#global-banner` 由 designer 预览与 data prep 校验共用。