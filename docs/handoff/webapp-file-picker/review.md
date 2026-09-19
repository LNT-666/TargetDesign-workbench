# 核验报告：webapp-file-picker

- round: 1
- verdict: pass_with_followups
- updated: 2026-09-16 22:16
- 依据：`report.md`（round 1）+ `backup/20260916_webapp_file_picker/` + master 自写探针
  （`assets/probe_master_api.py`、`assets/probe_master_picker.js` ~ `probe_master_picker5.js`，均由 master 新增）
- 权威环境：本任务只涉及本地 webapp 与本机 fixture，权威验证即本机（未使用 ms01）。

## 逐条核验

| 任务项 | 结论 | 证据 |
| --- | --- | --- |
| P0-1 后端列目录接口 | 通过 | 代码：`webapp/app.py:59-62`（`FS_ENTRY_LIMIT=2000`）、`:86-91`（`filesystem_roots`）、`:184-186`（路由，错误映射未动）、`:365-434`（`_api_fs_list`）；`webapp/schema.py:103-124`（`FS_KINDS` / `FS_STRIP`）。接口探针（master 自写，真起服务 8371）：`python docs\handoff\webapp-file-picker\assets\probe_master_api.py http://127.0.0.1:8371` → `checks=67 failed=0`，覆盖根模式键齐全/`dir`+`parent` 为 null、6 个 kind 的名字与顺序、未知 kind 回显 `any`、`sub\..` 规范化、`db`/`index` 的 `strip` 按长度降序且 `strip[0]==".source.json"`、2000 条上限且 30 个目录全部保住（只丢文件）、`400` 映射与错误文案、`/api/outputs` 回归、静态白名单与 `..` 拒绝 |
| P0-2 字段标注 kind | 通过 | `webapp/schema.py:64,66,67,69,70,71,89` 七个字段均带 `kind`。页面探针：`pathFieldsPerMode` 三个模式各 6 个路径字段、`data-kind` 与规格表一一对应；BED 输入模式下 `#field-bed_regions` 渲染且按钮 `data-kind="bed"`（`probe_master_picker3.js` → `bedMode_fieldRendered=true`、`bedMode_button="bed"`） |
| P0-3 picker 弹层与按钮 | 通过 | 代码：`webapp/index.html:181-203`（DOM 只在 `#drawer-scrim` 后追加）、`webapp/static/app.js:366`（Esc 条件）、`:641-650`（`renderField` 仅对 `file`/`dir` 加按钮）、`:1679-2019`（单一 picker 模块）、`webapp/static/styles.css:443-545`。页面探针（headless Edge + CDP 9334）：`nativeFileInputs=0`、13 个按钮文案全为 `Browse...`、`pickerZIndex=60` / `pickerScrimZIndex=55`、`fastaNamesExact=true`（`sub|mini.fna`）、`fastaWorksOnNotesTxt=false`、`enterKeyLists=sub|mini.fna`、双击目录进入且弹层不关、`db` 选 `mini.blastdb.source.json` → 写回 `...\fixture\mini.blastdb`（最长后缀优先）、`index` 选 `miniindex.json` 与 `miniindex.ggi` → 均写回 `...\fixture\miniindex`、`dir` 字段空选 OK 写当前目录、单击选中/双击文件确认、`cancel` 与点遮罩字段值不变、`inputEventsFired=1`、`crispr.pickerDir` 已写入 fixture、文件路径候选自动退到其目录、`windowErrors=[]` |
| P0-3 已知坑（窄抽屉几何） | 通过 | `--drawer-width=380px` → 6 个路径输入各 242px、按钮 80px、同一行、无重叠（`probe_master_picker3.js` → `narrowAllUsable=true`）；路径行横向 29..359 ≤ 抽屉 `clientWidth` 364 |
| P0-4 测试 | 通过 | `tests/test_webapp.py:242-256`（`test_path_fields_carry_a_browse_kind`）、`:674-725`（`test_fs_list_route`，§3 的 11 条断言逐条对应，错误信息用 `assertIn`）。master 实跑：`python -m unittest tests.test_webapp -v` → `Ran 58 tests in 49.456s` / `OK`（基线 56 + 新增 2） |
| P1-1 文档 | 通过 | `docs/WEBAPP.md:186`（API 表新增 `/api/fs/list`）、`:204-256`（「路径浏览选取器」：字段→kind 表、行为要点、`strip` 语义、为什么不用原生文件框/不上传）、`:262-263`（安全边界）。master 逐条比对文档与实现（`strip` 顺序、候选顺序、Esc 规则、写回方式），一致 |
| P1-2 断言不回归 | 通过 | `/api/outputs` 与 `OUTPUT_EXTENSIONS` 未改（diff 仅在 `do_GET` 加 3 行 + 新增函数）；探针 G1-G4 用 master 按旧规则自算的参照名单比对 `/api/outputs` 输出，逐名一致，`dir` 缺失仍 `400`；`STATIC_WHITELIST` 未改、未新增静态文件（`webapp/static/` 仍只有 `app.js`、`styles.css`）；三模式字段渲染与 `data-kind` 与 schema 一致 |

## master 独立验证

- 快照/基线：`backup/20260916_webapp_file_picker/` 的 7 个文件与改后逐文件 `difflib.unified_diff`；
  快照内 `picker|fs/list|browse` 命中数均为 0（确为改前状态），且快照 `docs/WEBAPP.md` 已含
  上一轮 `webapp-big-prep-panel` 的「Data prep 近满屏面板」内容 → 基线落在上一轮交付之后。
- 改动面控制：全仓（depth 2、排除 `docs/handoff`）在 21:30 之后被写过的文件只有规格点名的 7 个
  （`webapp/app.py`、`webapp/schema.py`、`webapp/index.html`、`webapp/static/app.js`、
  `webapp/static/styles.css`、`tests/test_webapp.py`、`docs/WEBAPP.md`），外加 `logs/`、
  `scy-test/`（并行跑批产物，与本任务无关，已确认非 servant 交付内容）。
- 编码：7 个改动文件 + 新探针均为 UTF-8 无 BOM、`crlf=0`。
- 接口：`assets/probe_master_api.py`（67 检查，含 master 自算参照）→ `failed=0`。
- 页面端到端：`assets/probe_master_picker.js` ~ `probe_master_picker5.js` 经
  `assets/probe_browser_cdp.js` + headless Edge（CDP 9334，全新 profile、全新 `localStorage`）驱动；
  5 次运行 `probeError` 全为 null、`cdpExceptionsDuringLoad=0`、`cdpExceptionsTotal=0`、`windowErrors=[]`。
  运行器 `assets/probe_browser_cdp.js` 与 `webapp-big-prep-panel/assets/probe_browser_cdp.js` SHA256 相同（未被改动）。
- 测试：`python -m unittest tests.test_webapp -v` → `Ran 58 tests in 49.456s` / `OK`（master 自己跑）。

## 归属判定（既有失败 vs 本次引入）

- 抽屉在 380px 出现横向滚动（`drawerScrollWidth 655 > clientWidth 364`）：**既有**。
  证据：溢出元素全部是 `table.models-table` 及其行列（宽 626），本轮 diff 未触及该表相关代码/样式；
  新加的路径行本身在抽屉内不溢出（29..359）。规格只要求路径字段行不挤扁，该点通过。
- 结果区 `#outputs-dir` 从整宽 669px 变 265px、`Browse...` 落到输入框下一行：**本次引入，但由规格直接导致**。
  证据：`probe_master_picker5.js` —— 现状 `row=265/input=265/browse.top=2691(第二行)`；把输入框移回
  `.actions`（复现改前 DOM）后 `input=669`（`inputWidthGain=404`）。原因是 master 在 §3 P0-3 要求
  「用一个 `.row` 把输入框 + 按钮包起来」，而 `.actions` 本身是 flex 容器，被包后 `.row` 按内容收缩。
  功能正常（按钮 `kind=dir`、可开弹层、可写回），属外观问题。
- 「文件类字段无选中时点 `#picker-ok` 弹层不关」：**规格未覆盖**。规格 §1.4-7 原文是
  「文件类 kind 什么都不做（字段保持原值）」，实现照此（`webapp/static/app.js:1954-1976`，
  `picked` 为空即 `return`），字段确实保持原值；观感上是「点了没反应」。

## 新发现

- `webapp/static/app.js:1954`（`confirmPicker`）— 文件类字段无选中时点 `#picker-ok` 既不写回也不关闭，
  弹层看似无响应 — 等级 P3（建议二选一：关闭弹层，或在 `#picker-list` 提示「先选一行」；规格未定，等用户拍板）
- `webapp/static/app.js:641-650` + `webapp/static/styles.css:447` — 结果区被 `.row` 包装的 `#outputs-dir`
  收缩到 265px、按钮换行 — 等级 P3（建议给该 `.row` 或 `#outputs-dir` 的包装行加 `flex: 1 1 auto`，
  一行 CSS 即可恢复整行输入框并让 `Browse...` 同行）
- `webapp/static/app.js:1790`（`openPicker` 打开先置 `Loading...`）— servant 报告列为「附带发现」，
  规格未写；master 认可该实现（避免弹层短暂显示上一个字段的行），保留即可 — 非缺陷
- `docs/handoff/webapp-big-prep-panel/review.md` 仍是空模板（上一轮 master 未落核验）— 与本次交付无关，
  仅记录备查 — 等级 P3
- `report.md` 头部 `updated: 2026-09-16 22:40`、`state.json` 原 `updated: 22:45`，而两者实际 mtime 为
  22:01；不影响结论，下次请写真实时间 — 等级 P3

## 下一步

- 结论：**通过（pass_with_followups）**，P0-1 ~ P1-2 全部核验通过，无最小修复清单；`state.json` 置 `done`。
- 可选后续（需用户拍板，不建议现在自动开工）：
  1. 结果区输出目录行改 `flex: 1 1 auto`，恢复整行输入框并把 `Browse...` 放回同一行。
  2. 文件类字段无选中点 OK 时给出可见反馈（关闭或提示）。
  3. 若希望留痕，补写上一轮 `docs/handoff/webapp-big-prep-panel/review.md`。
- master 本轮新增文件：`assets/probe_master_api.py`、`assets/probe_master_picker.js`、
  `probe_master_picker2.js`、`probe_master_picker3.js`、`probe_master_picker4.js`、`probe_master_picker5.js`（只增不改）。
- 本轮未改任何交付代码：核验全程只读交付物 + 新增探针 + 本文件。
- 环境清理：master 起的 `webapp/app.py --port 8371`（PID 12240）与 headless Edge（CDP 9334）已在收尾时关闭；
  8351 端口自 servant 交付后一直空闲。

---

# Round 2 核验（master，2026-09-16 23:30）

- round: 2
- verdict: **pass**（无最小修复清单；`state.json` 置 `done`）
- 依据：`report.md`（round 2）、`backup/20260916_webapp_picker_explorer/`（改前快照）、master 本轮新增的 4 个探针
  （`assets/probe_master_r2_picker.js`、`probe_master_r2_drawer.js`、`probe_master_r2_limit.js`、`probe_master_r2_gaps.js`，只增不改）、
  重跑 round 1 的 6 个探针 + servant 的 `probe_picker_explorer.js` + `assets/probe_master_api.py`
- 权威环境：本机（本轮只涉及本地 webapp 与本机 fixture，未使用 ms01）
- master 本轮 11 次探针运行的日志：`%TEMP%\picker_probe_master_r2\*.json`（全部 `probeError=null`、`cdpExceptionsDuringLoad=0`、`cdpExceptionsTotal=0`）

## 0. 改动面与快照核对

| 核对项 | 结论 | 证据 |
| --- | --- | --- |
| 快照确为改前状态 | 通过 | `backup/20260916_webapp_picker_explorer/`（7 文件，22:25）里 `webapp/app.py` 的 `hidden` 命中 **0**、`webapp/static/app.js` 的 `path-row\|picker-crumb\|picker-place\|picker-head-row` 命中 **0**、`webapp/index.html` 的 `picker-crumbs\|picker-places\|picker-back\|picker-hidden` 命中 **0** |
| 只有规格点名的文件被改 | 通过 | 22:20 之后被写过的交付文件恰为 6 个：`webapp/app.py`(22:26)、`webapp/index.html`(22:30)、`webapp/static/app.js`(22:45)、`webapp/static/styles.css`(22:29)、`tests/test_webapp.py`(22:26)、`docs/WEBAPP.md`(22:49)；`webapp/schema.py` 与快照逐字节相同（diff hunk=0）；`webapp/static/` 未新增文件（白名单未动） |
| 夹具与 round 1 探针未被改 | 通过 | `assets/fixture/` 全部条目 mtime 21:29（round 1）；`assets/fixture2/` 22:20:11-12（master 自建，早于 `task.md` 的 22:21:27）；master 的 6 个探针 mtime 22:11-22:16；`assets/` 里本轮唯一新增文件是 servant 的 `probe_picker_explorer.js`(22:49) |
| 编码 | 通过 | 7 个改动文件：UTF-8 无 BOM、`crlf=0`（逐文件实测） |
| 语法 | 通过 | `python -m py_compile webapp\app.py webapp\schema.py tests\test_webapp.py` → exit 0；`node --check webapp\static\app.js` → exit 0 |

## 1. 逐条核验（§9.2 必做项）

| 任务项 | 结论 | master 证据 |
| --- | --- | --- |
| P0-1 打开即定位并高亮当前值 | 通过 | 代码：`app.js:1838-1920`（候选链 + `picker.gen` 取消游走）、`app.js:1922`（`applyPickerListing` 末尾调 `highlightPickerValue`）、`app.js:2230`。探针：`openHighlightsCurrentValue.selectedRows=["mini.fna"]`、`selectedText=R:\…\fixture\mini.fna`、`openHighlightMatchesValue=true`、`okEnabledWithHighlightedFile=true`；`db`/`index` 前缀反查：`blastdbStrippedToPrefix=true`、`indexStrippedToPrefix=true`、`indexStrippedSlow=true`、`ggiStripped=true` |
| P0-2 面包屑 | 通过 | 代码：`app.js:2016-2065`、`index.html:195`。探针：`crumbCount=8`、`crumbTexts=R:\｜songji｜programfile｜docs｜handoff｜webapp-file-picker｜assets｜fixture`、`lastCrumbDisabled=true`；master 自写 `probe_master_r2_picker.js`：中间段 `assets` 可点且 `crumbJump.path=…\assets`（`crumbJumpOk=true`、`crumbAssetsDisabled=false`）；根模式 `rootMode.crumbs=0` |
| P0-3 列头与行信息 | 通过 | 代码：`app.js:2244`（行：`▸` + `.picker-size` + `.picker-mod`，`.picker-meta` 仅作容器）、`app.js:2266`（`pickerHeadRow` 用 `.picker-head-row`）；`styles.css:547/572/579`（表头 90px/150px 右对齐）。探针：`headRowLabels=["Name","Size","Modified"]`、`rowCount=2`（表头不计入 `.picker-row`）；master 自写：`headerClickDoesNotSort=true`（逐个点 4 个表头单元后名单与顺序不变）、`fileRowCells.size="28 B"`、`fileRowCells.mod="2026-09-16 21:29"`（`modifiedLooksLikeStamp=true`）、`dirRowCells.size=""`、`dirRowIconOk=true` |
| P0-4 导航历史与键盘 | 通过 | 代码：`app.js:1973`（`pushPickerHistory`，`PICKER_HISTORY_MAX=50`）、`app.js:2333`/`2356`（↑↓/Enter）、`app.js:2455-2500`（`document` keydown；焦点在 `#picker-path` 时只处理 `Escape`）。探针：`downArrowWorks=true`、`arrowStopsAtEnd/Top=true`、`enterEnteredSub=true`、`enterConfirmsFileOk=true`、`backspaceGoesUp=true`、`backGoesBack=true`、`forwardGoesForward=true`、`forwardDisabledAtTip=true`；master 自写：`secondBackIsNoop=true`（到端点不越界）、`forwardDisabledAfterNewNavigation=true`（从历史中段跳新目录后前向被丢弃）、`addressBarSwallowsArrows=true`（焦点在地址栏时 ↓ 不动选中；失焦后 ↓ 选中 `sub`） |
| P0-5 位置栏 | 通过 | 代码：`app.js:2088`（`rememberPickerDir`：写 `crispr.pickerDir` + 去重截 5 的 `crispr.pickerRecent`）、`app.js:2100`（`Home` + 最近）。master 自写：`placesAfterFixture=["Home",…\fixture]`、`placesAfterSub=["Home",…\sub,…\fixture]`、`placesAfterFixtureAgain=["Home",…\fixture,…\sub]`、`recentMostRecentFirst=true`、`recentDeduped=true`、`recentCapHonoured=true`、`placesShapeOk=true`；`homePlaceFound=true`、`homePlaceWorks=true` |
| P0-6 无选中时的 OK | 通过 | 代码：`app.js:2317`（`updatePickerFoot`）、`app.js:2425`（`usePickerDir`）、`index.html:206`。探针：`okDisabledForFileKindWithoutSelection=true`、`selectedHintForFileKind="Select a file"`、`okEnabledAfterFileSelection=true`、`hereHiddenForFileKind=true`、`hereVisibleForDirKind=true`、`hereWritesCurrentDir=true`、`hereClosedPicker=true`；master 自写：`okInertForFileKind=true`（置灰时点 `OK` 弹层不关、字段仍为 `KEEP-ME`）、`hereWritesBrowsedDir=true`（已选中 `sub` 行时 `Use this folder` 仍写**当前浏览目录**而非该行） |
| P1-1 `/api/fs/list?hidden=` | 通过 | 代码：`app.py:21`（`import stat`）、`app.py:95-111`（`hidden_entry`）、`app.py:397-398`（`1/true/yes`）、`app.py:428-431`（过滤在 kind 过滤之后、排序与 2000 上限之前；响应键未增删）。master 实测（真起服务 8361）：`R:\` 根 `36` vs `hidden=1` `36`（Samba 0 隐藏项对照）；`C:\` `kind=dir` 缺省 `20` vs `hidden=1` `25`，多出的正是 `$Recycle.Bin, Config.Msi, ProgramData, Recovery, System Volume Information`（走 Windows 属性分支）；fixture2 `kind=any/fasta` 缺省 `sub, attr-hidden.fna, plain.fna`、`hidden=1` 多出 `.dotfile.fna`；`hidden=0` 与缺省一致、`hidden=true` 与 `hidden=1` 一致。单测：`python -m unittest tests.test_webapp -v` → `Ran 60 tests in 49.357s` / `OK`，且 `test_fs_list_hidden_attribute_filter … ok`（**未 skip**）、`test_fs_list_hidden_filter … ok` |
| P1-1 勾选框与记忆 | 通过 | 代码：`app.js:2433`（`togglePickerHidden`）、`app.js:1838-1860`（打开时读 `crispr.pickerHidden` 并同步勾选）。探针：`hiddenToggleWorks=true`、`hiddenStored="1"`、`hiddenStoredAfterUncheck="0"`、`hiddenToggleRestores=true`、`hiddenAfterUncheck=["sub","attr-hidden.fna","plain.fna"]`；master 自写：关掉再打开后 `hiddenReopen.checkboxChecked=true`、`stored="1"`、名单直接含 `.dotfile.fna`（`hiddenReopenOk=true`） |
| P1-1 文档 | 通过 | `docs/WEBAPP.md:186`（API 行含 `hidden=1`）、`:234-283`（起始目录链含「字段为空 → 跳过 home 落根模式」、面包屑/列头/键盘/位置栏/`Show hidden`/`Select a file`/`Use this folder`、隐藏项默认不列）。master 逐条与实现对照（候选顺序、写回与 `strip`、Esc 规则、隐藏项判定、记忆键名），未发现不符处 |
| P1-2 视觉/文案/条目数 | 通过 | 代码：`styles.css:451`（`.path-row`）、`:459-461`（宽 `min(1040px, calc(100vw - 40px))`、高 `min(80vh, calc(100vh - 60px))`）、`:497`（`min-height: 260px`）、`:586-633`。探针：`countText="1 folder, 1 file"`；master 自写 `probe_master_r2_limit.js`（本机 2001 文件 + 1 子目录）：`rowCount=2000`、`countText="1 folder, 1999 files (listing truncated)"`、`countHasTruncatedSuffix=true`，列表末尾仍是 round 1 的 `Listing truncated at 2000 entries.`；接口侧同 `truncated=true / entries=2000`（`kind=any` 与 `kind=fasta&hidden=1` 都一样） |
| P1-2 修 round 1 P3 #2 | 通过 | 改后文件行 `app.js:645`（`renderField`）/`app.js:1763`（`attachBrowseButton`）为 `div.row.path-row`。探针：`probe_master_picker3.js` → `outputsDir.inputWidth=498`、`sameLine=true`、`overlaps=false`；`probe_master_picker4.js` → `outputsRow.row="div.row.path-row"`、`inputBox.width=498`、`buttonBelowInput=false`、`verticalOverlap=true`（同线，非上下叠）、`offenders=[]`；`probe_master_picker5.js` → `asShipped.input.width=498`、`loadSharesLineWithInput=true`（round 1 记录为 265px / 换行） |

## 2. 回归（§9 兼容门槛）

- 6 个 round 1 探针 + servant 的 `probe_picker_explorer.js` 全部由 master 重跑（每个探针一个全新 headless Edge profile，端口 9421-9428）：
  - `probe_picker_flow.js`：`fastaNamesExactly=true`、`pickerClosedAfterPick=true`、`escKeepsDrawerOpen=true`、`drawerNarrowInputUsable=true`、`drawerNarrowNoOverlap=true`、`pickerPathValueAtOpen=""`、`rootsShownAtOpen=C:\｜R:\｜X:\`、`inputEventCount=1`、`pickerDirStored=…\fixture`
  - `probe_master_picker.js`：`fastaNamesExact=true`、`subRowFound=true`、`enterDirExpectedPath=true`、`driveRootUpIsNoop=true`、`rootButtonCount=3`、`rootButtonTexts=C:\｜R:\｜X:\`、`rootModeHasNoRows=true`、`rootModeNote="Pick a drive above, or type an absolute path."`、`rootClickListedRoot=true`、`pathAfterRootClick=C:\`、`schemaInputEvents=1`、`pickerClosedAfterPick=true`、`fileOkKeptValue=true`、`drawerClosedAfterSecondEsc=true`、`errorKeepsPickerOpen=true`、`pickerZIndex="60"`、`pickerScrimZIndex="55"`
  - `probe_master_picker2.js`：`pathFieldsPerMode`（三模式各 6 个字段）、`indexRowFoundSlow=true`、`indexStrippedSlow=true`、`ggiRowFound=true`、`ggiStripped=true`、`fileOk_dialogStillOpen=true`、`rootMode_rootsShown=C:\｜R:\｜X:\`、`bannerBefore==bannerAfterError`
  - `probe_master_picker3.js`：`narrowAllUsable=true`（6 个抽屉路径输入各 242px、按钮 80px、同一行、无重叠）、`bedMode_fieldRendered=true`、`bedMode_button="bed"`
  - `probe_master_picker4.js` / `probe_master_picker5.js`：见上表 P1-2
- 接口契约：`python docs\handoff\webapp-file-picker\assets\probe_master_api.py http://127.0.0.1:8361` → `checks=67 failed=0`（含 6 个 kind 的名单与顺序、`strip`、2000 上限、`400` 文案、`/api/outputs` 回归、静态白名单与 `..` 拒绝）。
- 全部 11 次页面探针：`nativeFileInputs=0`、`windowErrors=[]`、CDP 异常 0。

## 3. 归属判定（既有失败 vs 本次引入）

1. `probe_master_picker.js` 的 `bannerStayedHidden=false` 与 `pickerClosedAfterFileOk=false`：**都不是回归**，与 round 1 逐字相同。
   - `pickerClosedAfterFileOk=false`：round 1 的「`confirmPicker` 无选中时直接 `return`」在本轮换成「`#picker-ok` 置灰（D15/P0-6）」，外部行为不变（`okDisabledForFileKindWithoutSelection=true`、点它弹层不关、字段保持原值）。
   - `bannerStayedHidden=false` 与 picker 无关：`probe_master_picker2.js` 在进弹层**之前**记下的 banner 与「picker 报错之后」逐字相同（`banner info | Pattern: motif sequence cannot be empty`），master 自写探针另测 `bannerUnchangedByPickerError=true`（前后都是 `banner info`）。触发者是探针自己清空 pattern/`dp-load` 后的 designer 预览消息 —— designer 预览与 data prep 校验共用 `#global-banner` 的既有行为，本轮未碰。
2. 抽屉在 380px 出现横向滚动：**既有**，本轮既没引入也没修掉。
   - 用改后代码复现 round 1 的数字（`probe_master_r2_drawer.js`：从关闭状态点 `#drawer-toggle` 打开抽屉，触发 `loadModels()`）：`table.models-table` 632px（行 626px、`left=29`、`right=655`），`drawer.clientWidth=364`、`drawer.scrollWidth=655`，越界元素就是该表及其行列（`overRight=[table.models-table, tr, th, th, tr, td.muted, td, button, button, tr, …]`）——与 round 1 核验记录的「`table.models-table` 宽 626 → scrollWidth 655」一致。
   - 本轮 diff 不含 `.models-table` 或抽屉表相关的任何改动（`styles.css` 的新增全在 `.path-row` 与 `.picker*`）。
   - 两个**用改后代码**做的对照，证明本轮改动不参与该溢出：摘掉全部 13 个 `.path-row` 的 class 后 `drawer.scrollWidth` 仍为 367（不变）；picker 打开时也仍为 367。
   - 抽屉未触发 `loadModels()`（models 区为空）时 `drawer.scrollWidth=367` vs `clientWidth=364`（3px）：`probe_master_picker3.js` 的 `drawerScrollFits=false` 在 round 1 也是 `false`，同键、非本轮引入。
   - 结论：`drawerScrollFits=false` 属既有问题，需另开一轮（建议 `.table-wrap { overflow-x: auto }`），不在本轮范围。
3. `assets/fixture2/attr-hidden.fna`：**master 自己的夹具/规格疏漏**，不是 servant 的问题。证据：它与 `plain.fna`、`.dotfile.fna`、`sub/deep.gtf` 同为 22:20:11-12 创建（早于 `task.md` 的 22:21:27），即 master 建 fixture2 时多放了一个文件、却没写进 §9.5 的期望名单；共享盘是 Samba，`SetFileAttributesW` 返回 50，所以它并没有隐藏属性，缺省列表本就该带它。servant 没动夹具、没动自己的断言口径（改成「包含 + 顺序」）并把两次接口原样结果贴进报告，是正确处置。

## 4. 待明确项裁定（master 拍板）

1. **D9 字面语义 vs 空白字段落根模式**：裁定按 servant 的实现（保留 `webapp/static/app.js:1899` 的 `picker.value &&` 这一处）。理由：§9 开头把 round 1 的 6 个探针列为**硬性兼容门槛**，而 `probe_master_picker.js` §13（`rootButtonCount`/`rootModeHasNoRows`/`rootClickListedRoot`）与 `probe_master_picker2.js` §7（`rootMode_rootsShown`）把「空白字段 → 根模式」钉死；硬性门槛优先于 D9 的字面顺序。master 同时把 D9 更正为：**字段有值时** `值 → 其目录 → crispr.pickerDir → home → 根模式`；**字段为空时** `crispr.pickerDir → 根模式`（`Home` 始终是位置栏第一项，一点即到，`homePlaceWorks=true`）。`docs/WEBAPP.md` 已按更正后的语义写；`task.md` 追加 §9.8 记录该更正。**无需改代码。**
2. `#picker-count` 在根模式留空：接受（规格只规定了 `N folders, M files` 与截断后缀）。
3. 键盘 `Enter` 选中目录行 = 进入（不是写回）：接受，与 round 1「双击目录 = 进入」一致；`dir` 字段要写回当前目录可点 `OK` 或 `Use this folder`。
4. 位置栏没有 `Recent` 字样：§9.2 P1-2 的文案清单里列了 `Recent`，但 §9.2 P0-5 的设计是「`Home` + 最近目录条目」。servant 用目录路径作标签（`title` 同为路径）。裁定接受现状（路径标签比一个 `Recent` 标题有用）；措辞含糊由 master 负责，不算偏离。
5. `assets/fixture2/attr-hidden.fna` 的处置：**保留**（合法普通文件，也提醒后续轮次 Samba 上设不了属性位）；§9.5 的期望名单以本节与 `task.md` §9.8 的更正为准。若用户希望夹具与 §9.5 逐字一致，删掉该文件即可 —— 共享盘上的删除按约定交给用户执行。

## 5. 后续可选（P3，等用户拍板，不建议自动开工）

- 抽屉在 380px、models 表渲染后横向滚动 655px（既有，见 §3.2）：给 `.table-wrap` 加 `overflow-x: auto` 即可，另开一轮。
- `#global-banner` 由 designer 预览与 data prep 校验共用（既有，见 §3.1）。
- `docs/handoff/webapp-big-prep-panel/review.md` 仍是空模板（round 1 已记）。

## 6. 环境清理

- master 起的 `python webapp\app.py --port 8361`（PID 3720）已 `Stop-Process`；`netstat` 上 8361 无 LISTENING。
- master 起的 headless Edge（CDP 9421-9433，profile `%TEMP%\edgeprobe_master_r2_*`）已按 CommandLine 匹配全部关闭；9421-9433 无 LISTENING（9410 是别的会话占的，未动）。
- `%TEMP%\pickerlimit_r2`（master 为截断分支测试新建的 2001 文件 + 1 目录）留在 `%TEMP%`：本会话的删除策略拦下了递归删除，交给用户处理（`Remove-Item -Recurse -Force` 即可）。
- master 只增不改：4 个新探针 + 本文件 + `state.json`；未改任何交付代码、夹具或 round 1 探针。

## 7. 全量套件（`run_tests.py`）说明

master 试跑过两次 `python run_tests.py`（`-u`，输出重定向到 `%TEMP%\full_suite_r2.log`）：两次都在**导入阶段**停住，
约 30 分钟既无输出也无实际进展（进程 CPU 仅 31s，属 I/O 等待）。逐模块实测 import 耗时解释了原因 ——
本共享盘上 32 个测试模块的 import 为 **7-25 s/模块**，其中 8 个（`test_core`、`test_fasta_gz`、`test_genome_index`、
`test_memory_limit`、`test_native_known_hits`、`test_search_hardening`、`test_webapp`、`test_workbench_form`）>25 s。
master 已停止这两次运行，未把「全量套件通过/不通过」写入结论。

本轮改动的覆盖面由以下三项替代（与 round 1 的核验尺度一致）：聚焦模块 `python -m unittest tests.test_webapp -v`
（`Ran 60 tests … OK`，含两条新增隐藏项单测且未 skip）、接口契约 `assets/probe_master_api.py`（67 检查 `failed=0`）、
11 次页面探针（round 1 的 6 个 + servant 的 1 个 + master 新增的 4 个）。本轮改动的文件不含 `shared/`、
不含搜索/off-target 相关模块，上述未完成的模块与本轮改动无交集。