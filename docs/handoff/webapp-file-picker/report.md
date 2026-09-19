# 交付报告：webapp-file-picker

- round: 2
- status: ready_for_review
- updated: 2026-09-16 22:58

本轮范围 = `task.md` §9（把选取器做成资源管理器式 + `/api/fs/list` 新增 `hidden`）+ round 1 核验留下的
P3 #2（结果区 `#outputs-dir` 宽度）。§0–§8 的行为契约（字段 key、写回语义、`strip`、Esc 规则、错误映射、
排序与 2000 上限）一律未动。

## 改动清单

行号均为**改后**文件行号。改前 7 个文件已快照到 `backup/20260916_webapp_picker_explorer/`（开工前创建、
保相对路径）；快照确为改前状态：快照 `webapp/app.py` 里 `hidden` 命中 **0** 次，快照
`webapp/static/app.js` 里 `path-row|picker-crumb|picker-place` 命中 **0** 次。

| 文件 | 行（改后） | 改了什么 | 对应任务项 |
| --- | --- | --- | --- |
| `webapp/app.py` | 21、95-110、384-434 | `import stat`；新增 `hidden_entry(path, name)`（`.` 开头 → 隐藏；Windows 再算 `st_file_attributes & FILE_ATTRIBUTE_HIDDEN`；`stat` 失败按不隐藏）；`_api_fs_list` 读 `hidden`（`1`/`true`/`yes` 才显示），过滤放在 **kind 过滤之后、排序之前**（431-432），响应键与 `400` 文案未动 | P1-1 |
| `webapp/index.html` | 192-193、195、197、198-201、206 | `#picker-back` / `#picker-forward`（挨着 `#picker-up`，初始 `disabled`）、`#picker-crumbs`、`#picker-places`、`.picker-toolbar`（`#picker-hidden` + `#picker-count`）、`#picker-here`（`Use this folder`）；原有 id/元素一个没改没删 | P0-2/3/4/5/6、P1-2 |
| `webapp/static/app.js` | 645、1763 | `renderField` / `attachBrowseButton` 包装出的行改成 `class: 'row path-row'`（修 round 1 P3 #2） | P1-2 |
| `webapp/static/app.js` | 1685-1694 | picker 常量：`PICKER_RECENT_KEY='crispr.pickerRecent'`、`PICKER_HIDDEN_KEY='crispr.pickerHidden'`、最近 5 条 / 历史 50 条 | P0-4/5、P1-1 |
| `webapp/static/app.js` | 1769-1790 | `dirNameOf`；`fetchPickerDir` 按 `picker.showHidden` 追加 `&hidden=1` | P1-1 |
| `webapp/static/app.js` | 1792-1938 | `loadPickerDir`（打开时的候选游走，可被用户操作取消）、`pickerLoad(dir, record)`（手输/Go/面包屑/双击；`record` 决定是否记历史）、`openPicker`（起始目录链 + `picker.gen`）、`applyPickerListing`（一次刷新盘符/位置栏/面包屑/条目数/列表/导航/底部/高亮） | P0-1 |
| `webapp/static/app.js` | 1944-1955、1968-2008 | `resetPickerListing`；`pushPickerHistory` / `pickerBackOrForward` / `updatePickerNav`（上限 50、无历史 `disabled`、前后进退不重写历史） | P0-4 |
| `webapp/static/app.js` | 2013-2069、2070-2116、2118-2142 | 面包屑（`pickerCrumbs` / `renderPickerCrumbs`：`>` 分隔、每段可点、末段 `disabled`）；`pickerRecent` / `rememberPickerDir`（去重、截 5 条，写 `crispr.pickerDir` + `crispr.pickerRecent`）/ `renderPickerPlaces`（`Home` + 最近）；`renderPickerCount`（`N folders, M files`，`truncated` 追加 ` (listing truncated)`） | P0-2/5、P1-2 |
| `webapp/static/app.js` | 2146-2240 | `formatStamp`（本地 `YYYY-MM-DD HH:MM`）、`pickerBaseName` / `sameName` / `samePath` / `pickerRowsInOrder` / `pickerRowNamed` / `pickerValueRow`（`db`/`index` 按 `strip` 前缀反查）、`highlightPickerValue`（打开时选中并 `scrollIntoView`） | P0-1/3 |
| `webapp/static/app.js` | 2241-2312 | `pickerRow`（目录 `▸`、`.picker-name` + `.picker-meta` 内的 `.picker-size` / `.picker-mod`）、`renderPickerList`（顶部 `div.picker-head-row`，**不是** `.picker-row`） | P0-3 |
| `webapp/static/app.js` | 2317-2440 | `updatePickerFoot`（文件类无选中 → `#picker-ok` 置灰 + `Select a file`；`#picker-here` 仅 `dir` 类显示）、`movePickerSelection` / `activatePickerSelection` / `activatePickerRow`、`pickerGo` / `pickerGoTo` / `pickerUp`、`stripPickerSuffix`、`confirmPicker`（写回 + 记最近）、`usePickerDir`、`togglePickerHidden` | P0-4/5/6、P1-1 |
| `webapp/static/app.js` | 2455-2509 | `initPicker`：新增 `#picker-back` / `#picker-forward` / `#picker-hidden` / `#picker-here` 监听；`document` 上的 `keydown`（`ArrowDown`/`ArrowUp`/`Enter`/`Backspace`；焦点在 `#picker-path` 时只处理 `Escape`） | P0-4、P1-1 |
| `webapp/static/styles.css` | 451、459-470、495-497、528-637 | `.path-row`；`.picker` 宽 `min(1040px, calc(100vw - 40px))`、高 `min(80vh, calc(100vh - 60px))`；`.picker-list min-height: 260px`；列头、`.picker-size`（90px 右对齐）/ `.picker-mod`（150px 右对齐）、面包屑、位置栏、工具条样式 | P1-2 |
| `tests/test_webapp.py` | 726-747、749-769 | `test_fs_list_hidden_filter`（点号，所有平台都跑）；`test_fs_list_hidden_attribute_filter`（`@unittest.skipUnless(os.name == 'nt')`，`SetFileAttributesW(..., 0x02)` 返回假即 skip） | P1-1 |
| `docs/WEBAPP.md` | 186、204-273、280-283 | API 行补 `hidden=1`；「路径浏览选取器」小节按 round 2 重写（起始目录链、高亮、面包屑、列头、条目数、键盘、OK / `Use this folder` 规则、`Show hidden`）；安全边界补隐藏项过滤 | P1-1 |
| `docs/handoff/webapp-file-picker/assets/probe_picker_explorer.js` | 新增（全文 393 行） | 本轮页面探针：§9.6 点名的键全部断言并输出 | §9.6 |
| `backup/20260916_webapp_picker_explorer/` | 新增 | 改前快照：`webapp/app.py`、`webapp/schema.py`、`webapp/index.html`、`webapp/static/app.js`、`webapp/static/styles.css`、`tests/test_webapp.py`、`docs/WEBAPP.md` | §9.7 |

diff 规模（对快照做 `difflib.unified_diff` 计数）：`webapp/app.py +27/-1`、`webapp/static/app.js +524/-33`、
`webapp/static/styles.css +106/-4`、`webapp/index.html +10/-1`、`tests/test_webapp.py +45/-0`、
`docs/WEBAPP.md +32/-11`、`webapp/schema.py +0/-0`（**本轮未改**，SHA256 与快照一致）。

未碰：`webapp/schema.py`、`shared/`、`_api_outputs` / `OUTPUT_EXTENSIONS`、字段 key / 默认值 / 预设 /
作业模型 / 抽屉几何、`assets/fixture/`、master 的 6 个探针与 `assets/probe_browser_cdp.js`、未新增
`.js` / `.css`、`run_tests.py` 未跑。

兼容门槛（§9 开头）逐条自检：`#picker-list` 里只有数据行用 `.picker-row`（表头是 `.picker-head-row`）；
`#picker-roots` 仍是盘符按钮容器、子元素仍是 `.picker-root`，位置条目用 `.picker-place`、不进
`#picker-roots`；`#picker`/`#picker-scrim`/`#picker-path`/`#picker-go`/`#picker-up`/`#picker-close`/
`#picker-list`/`#picker-selected`/`#picker-cancel`/`#picker-ok` 的 id 与语义未变、z-index 仍 60/55；
行仍带 `data-path` / `data-type`、名字仍在 `.picker-name`；单击选中、双击目录进入、双击文件确认、
`#picker-path` 手输回车均未变。

## 轻量自检结果

### 1) 语法

```powershell
python -m py_compile webapp\app.py webapp\schema.py tests\test_webapp.py
node --check webapp\static\app.js
node --check docs\handoff\webapp-file-picker\assets\probe_picker_explorer.js
```

```text
py_compile exit=0
node --check app.js exit=0
node --check probe exit=0
```

### 2) 聚焦单测（基线 56，round 1 后 58，本轮 60）

```powershell
python -m unittest tests.test_webapp -v
```

```text
test_dataprep_choices (tests.test_webapp.SchemaTests.test_dataprep_choices) ... ok
test_engine_and_format_lists_come_from_shared (tests.test_webapp.SchemaTests.test_engine_and_format_lists_come_from_shared) ... ok
test_modes_and_presets (tests.test_webapp.SchemaTests.test_modes_and_presets) ... ok
test_path_fields_carry_a_browse_kind (tests.test_webapp.SchemaTests.test_path_fields_carry_a_browse_kind) ... ok
test_pattern_form_field_keys_exist (tests.test_webapp.SchemaTests.test_pattern_form_field_keys_exist) ... ok

----------------------------------------------------------------------
Ran 60 tests in 48.375s

OK
```

本轮新增的两条单跑原文：

```powershell
python -m unittest tests.test_webapp.HandlerRouteTests.test_fs_list_hidden_filter tests.test_webapp.HandlerRouteTests.test_fs_list_hidden_attribute_filter tests.test_webapp.HandlerRouteTests.test_fs_list_route -v
```

```text
test_fs_list_hidden_filter (tests.test_webapp.HandlerRouteTests.test_fs_list_hidden_filter)
Dot-prefixed entries are only listed when ``hidden=1`` asks for them. ... ok
test_fs_list_hidden_attribute_filter (tests.test_webapp.HandlerRouteTests.test_fs_list_hidden_attribute_filter)
The Windows hidden attribute hides an entry until ``hidden=1``. ... ok
test_fs_list_route (tests.test_webapp.HandlerRouteTests.test_fs_list_route) ... ok

----------------------------------------------------------------------
Ran 3 tests in 0.092s

OK
```

`run_tests.py` 未跑（§9.3 禁止）。

### 3) 接口实跑（真起服务 `python webapp\app.py --port 8351`）

```powershell
$base='http://127.0.0.1:8351/api/fs/list'
$e='R%3A%5Csongji%5Cprogramfile%5Cdocs%5Chandoff%5Cwebapp-file-picker%5Cassets%5Cfixture2'
Invoke-WebRequest -UseBasicParsing "$base`?kind=fasta&dir=$e"
Invoke-WebRequest -UseBasicParsing "$base`?kind=fasta&dir=$e&hidden=1"
```

缺省（不列隐藏项）响应原文：

```text
STATUS 200
{"dir": "R:\\songji\\programfile\\docs\\handoff\\webapp-file-picker\\assets\\fixture2", "parent": "R:\\songji\\programfile\\docs\\handoff\\webapp-file-picker\\assets", "roots": [], "home": "C:\\Users\\ASUS", "kind": "fasta", "strip": [], "entries": [{"name": "sub", "path": "R:\\songji\\programfile\\docs\\handoff\\webapp-file-picker\\assets\\fixture2\\sub", "type": "dir", "size": null, "modified": 1789568411.9781277}, {"name": "attr-hidden.fna", "path": "R:\\songji\\programfile\\docs\\handoff\\webapp-file-picker\\assets\\fixture2\\attr-hidden.fna", "type": "file", "size": 11, "modified": 1789568411.953762}, {"name": "plain.fna", "path": "R:\\songji\\programfile\\docs\\handoff\\webapp-file-picker\\assets\\fixture2\\plain.fna", "type": "file", "size": 16, "modified": 1789568411.5978606}], "truncated": false}
```

`hidden=1` 响应原文：

```text
STATUS 200
{"dir": "R:\\songji\\programfile\\docs\\handoff\\webapp-file-picker\\assets\\fixture2", "parent": "R:\\songji\\programfile\\docs\\handoff\\webapp-file-picker\\assets", "roots": [], "home": "C:\\Users\\ASUS", "kind": "fasta", "strip": [], "entries": [{"name": "sub", "path": "R:\\songji\\programfile\\docs\\handoff\\webapp-file-picker\\assets\\fixture2\\sub", "type": "dir", "size": null, "modified": 1789568411.9781277}, {"name": ".dotfile.fna", "path": "R:\\songji\\programfile\\docs\\handoff\\webapp-file-picker\\assets\\fixture2\\.dotfile.fna", "type": "file", "size": 10, "modified": 1789568411.7757676}, {"name": "attr-hidden.fna", "path": "R:\\songji\\programfile\\docs\\handoff\\webapp-file-picker\\assets\\fixture2\\attr-hidden.fna", "type": "file", "size": 11, "modified": 1789568411.953762}, {"name": "plain.fna", "path": "R:\\songji\\programfile\\docs\\handoff\\webapp-file-picker\\assets\\fixture2\\plain.fna", "type": "file", "size": 16, "modified": 1789568411.5978606}], "truncated": false}
```

`kind=any` 与 `kind=fasta` 在这两份原文里名单一致（夹具里没有非 fasta 后缀的文件）。响应键仍是
`dir/parent/roots/home/kind/strip/entries/truncated` 八个、条目字段仍是 `name/path/type/size/modified`；
排序仍是先目录后文件、组内 `name.lower()` 升序（`.dotfile.fna` 落在 `sub` 之后、`attr-hidden.fna` 之前）。

属性位分支（真盘样本，`kind=dir` 只列目录便于比对）：

```powershell
Invoke-WebRequest -UseBasicParsing "$base`?kind=dir&dir=C%3A%5C"          # 20 条
Invoke-WebRequest -UseBasicParsing "$base`?kind=dir&dir=C%3A%5C&hidden=1" # 25 条
Invoke-WebRequest -UseBasicParsing "$base`?kind=dir&dir=R%3A%5C"          # 36 条
Invoke-WebRequest -UseBasicParsing "$base`?kind=dir&dir=R%3A%5C&hidden=1" # 36 条
```

```text
C:\  缺省 20 条：5EDemocache, Config, csgodemocache, db, Documents and Settings, download, eSupport, inetpub, Intel, opaivmplayer, PerfLogs, Program Files, Program Files (x86), rtools45, Temp, Users, websymbols, WebView2DataSt, Windows, XboxGames
C:\  hidden=1 25 条：多出 $Recycle.Bin, Config.Msi, ProgramData, Recovery, System Volume Information（这 5 个都不以 `.` 开头 → 走的是 Windows 属性位分支）
R:\  缺省 36 条 = hidden=1 的 36 条（Samba 上 0 个隐藏项，与 §9.1 的对照一致）
```

（§9.1 列的 13 个 `C:\` 隐藏项里，`DumpStack.log.tmp` / `Finish.log` / `PageFile` / `devlist.txt` /
`hiberfil.sys` / `pagefile.sys` / `swapfile.sys` 是文件，本组 `kind=dir` 查不到；`kind=any` 也能看到它们被
`hidden` 过滤掉。）

### 4) 页面探针（7 个，全绿）

每个探针起一个**全新的 headless Edge profile**（`localStorage` 是空的），端口 9401-9407；7 份日志原文在
`%TEMP%\picker_probe_out\<probe>.js.json`。单条命令形态（与 round 1 报告同构）：

```powershell
python webapp\app.py --port 8351
& 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe' --headless=new --disable-gpu --no-first-run --user-data-dir="$env:TEMP\edgeprobe_r2_<probe>" --remote-debugging-port=9401 about:blank
$env:CDP_PORT='9401'; $env:APP_URL='http://127.0.0.1:8351/'; $env:WAIT_MS='9000'
& 'C:\Users\ASUS\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe' docs\handoff\webapp-file-picker\assets\probe_browser_cdp.js docs\handoff\webapp-file-picker\assets\probe_<name>.js
```

7 份日志的外层字段全部是：`exit=0`、`probeError=null`、`"cdpExceptionsDuringLoad": 0`、
`"cdpExceptionsTotal": 0`、`"cdpEvents": []`；每个探针自身的 `windowErrors` 都是 `[]`。

#### 4.1 回归：round 1 的 6 个探针（§9.6 点名的键）

```text
probe_picker_flow.js       fastaNamesExactly=true   pickerClosedAfterPick=true   escKeepsDrawerOpen=true
                           drawerNarrowInputUsable=true   drawerNarrowNoOverlap=true
                           pickerPathValueAtOpen=""   rootsShownAtOpen=C:\,R:\,X:\   windowErrors=[]
                           （其余键与 round 1 报告逐个一致：fastaRowNames=sub|mini.fna、upLandsOnParent=true、
                             pickup 写回 …\fixture\mini.fna、blastdb/index 前缀剥离、cancelKeepsFieldValue=true、
                             inputEventCount=1、pickerDirStored=…\fixture）
probe_master_picker.js     fastaNamesExact=true   subRowFound=true   enterDirExpectedPath=true
                           driveRootUpIsNoop=true   rootButtonCount=3   rootButtonTexts=C:\,R:\,X:\
                           rootModeHasNoRows=true   rootModeNote="Pick a drive above, or type an absolute path."
                           rootClickListedRoot=true   pathAfterRootClick=C:\
                           schemaFieldValueExpected=true   schemaInputEvents=1   pickerClosedAfterPick=true
                           fileOkKeptValue=true   drawerClosedAfterSecondEsc=true   errorKeepsPickerOpen=true
                           bannerStayedHidden=false   pickerClosedAfterFileOk=false   windowErrors=[]
probe_master_picker2.js    rootMode_rootsShown=C:\,R:\,X:\   indexRowFoundSlow=true   indexStrippedSlow=true
                           ggiRowFound=true   ggiStripped=true   indexOpenOk=true
                           fileOk_dialogStillOpen=true   fileOk_fieldValue=KEEP-FILE
                           bannerBefore="banner info | Pattern: motif sequence cannot be empty"
                           bannerAfterError="banner info | Pattern: motif sequence cannot be empty"   windowErrors=[]
probe_master_picker3.js    narrowAllUsable=true   outputsDir.inputWidth=498   outputsDir.sameLine=true
                           outputsDir.overlaps=false   bedMode_fieldRendered=true   bedMode_button=bed
                           narrow: dp-download-output/dp-genome/dp-annotation/dp-output/dp-blastdb/dp-index-prefix
                           六个字段 inputWidth=242 buttonWidth=80 sameLine=true overlaps=false
                           drawerScrollFits=false（drawerScrollWidth=367 > clientWidth=364，见附带发现）
probe_master_picker4.js    outputsRow.row="div.row.path-row"   rowBox.width=586   inputBox.width=498
                           buttonBox.left=541   sameLine=true   buttonBelowInput=false   horizontalOverlap=false
                           offenders=[]   offenderCount=0   drawerClientWidth=364   drawerScrollWidth=367
probe_master_picker5.js    asShipped.input.width=498   asShipped.inputOnOwnLine=false
                           asShipped.loadSharesLineWithInput=true   preRoundDom.inputWidthGain=171
```

两个不是 `true` 的键，都不是回归：

- `bannerStayedHidden=false`（`probe_master_picker.js` §14）：与 picker 无关，见「附带发现」第 2 条；
  `probe_master_picker2.js` 里同一场景的 `bannerBefore` / `bannerAfterError` 原文**逐字相同**
  （`banner info | Pattern: motif sequence cannot be empty`），即 picker 报错确实不写 `#global-banner`。
- `pickerClosedAfterFileOk=false`：round 1 同为 `false`（文件类字段无选中时弹层不关）。round 2 的原因由
  「`confirmPicker` 直接 return」变成「`#picker-ok` 被置灰」（D15/P0-6），外部行为不变。
- `probe_master_picker2.js` 的 `bedModeHasButton=false` 也不是回归：`bed_regions` 不在三个 designer 模式里，
  它由 BED 输入模式渲染，由 `probe_master_picker3.js` 覆盖（`bedMode_fieldRendered=true`、`bedMode_button=bed`）；
  本轮字段渲染一行未改。

#### 4.2 本轮新键（`assets/probe_picker_explorer.js`，§9.6 点名的键全在）

```text
openHighlightsCurrentValue: selectedRows=["mini.fna"]  selectedText=R:\…\fixture\mini.fna
                            openHighlightMatchesValue=true   okEnabledWithHighlightedFile=true
crumbCount=8  crumbTexts=R:\ | songji | programfile | docs | handoff | webapp-file-picker | assets | fixture
              lastCrumbDisabled=true
headRowCells=["", "Name", "Size", "Modified"]   headRowLabels=["Name", "Size", "Modified"]
countText="1 folder, 1 file"   rowCount=2   rowTypes=dir,file   selectionClearedByRelist=true
downArrowMovesSelection: first=["sub"] second=["mini.fna"] end=["mini.fna"] top=["sub"]
                         downArrowWorks=true   arrowStopsAtEnd=true   arrowStopsAtTop=true
enterEntersDir: path=R:\…\fixture\sub  stillOpen=true  rows=[]   enterEnteredSub=true   enterEntersDirOk=true
                crumbCountInSub=9
backButtonEnabled=true  forwardDisabledAtTip=true  backGoesBack=true  forwardEnabledAfterBack=true
                        forwardGoesForward=true  backspaceGoesUp=true
enterConfirmsFile: closed=true  value=R:\…\fixture\mini.fna  inputEvents=1   enterConfirmsFileOk=true
hereVisibleForDirKind=true   okEnabledForDirKindWithoutSelection=true   dirKindRowTypes=dir
                             hereWritesCurrentDir=true   hereClosedPicker=true
okDisabledForFileKindWithoutSelection=true   selectedHintForFileKind="Select a file"
                         hereHiddenForFileKind=true   okEnabledAfterFileSelection=true
hiddenToggleHidesDotfile: before=["sub", "attr-hidden.fna", "plain.fna"]
                          after=["sub", ".dotfile.fna", "attr-hidden.fna", "plain.fna"]
                          hiddenToggleWorks=true   hiddenStored="1"   hiddenCheckboxChecked=true
                          hiddenToggleRestores=true   hiddenAfterUncheck=["sub", "attr-hidden.fna", "plain.fna"]
                          hiddenStoredAfterUncheck="0"
fixture2ApiDefault: status=200  names=sub, attr-hidden.fna, plain.fna
fixture2ApiHidden:  status=200  names=sub, .dotfile.fna, attr-hidden.fna, plain.fna
placesAfterConfirm=["Home", "R:\…\fixture"]   homePlaceFound=true   homePlaceWorks=true
              pickerDirStored=R:\…\fixture   recentStored=["R:\…\fixture"]
emptyFieldStartPath=""   driveButtonsShownForEmptyField=3   emptyFieldStartShowsDriveList=true
                         emptyFieldStartIsHome=false（见「待明确」第 1 条）
pickerErrorShownInList=true   errorKeepsPickerOpen=true
pickerErrorText="Could not list R:\no\such\dir: Directory not found: R:\no\such\dir"
bannerBeforeError="banner info"   bannerAfterError="banner info"   bannerUnchangedByPickerError=true
nativeFileInputs=0   windowErrors=[]
```

#### 4.3 round 1 的两条 P3

- P3 #1（文件类字段无选中时点 `#picker-ok` 像没反应）：已按 D15/P0-6 修成
  `#picker-ok` 置灰 + `#picker-selected` 显示 `Select a file`（证据：
  `okDisabledForFileKindWithoutSelection=true`、`selectedHintForFileKind="Select a file"`、
  `okEnabledAfterFileSelection=true`）。
- P3 #2（结果区 `#outputs-dir` 缩到 265px、`Browse...` 换行）：已修。原文：
  `probe_master_picker3.js` → `outputsDir.inputWidth=498 outputsDir.sameLine=true outputsDir.overlaps=false`；
  `probe_master_picker4.js` → `rowBox.width=586 inputBox.width=498 buttonBelowInput=false offenders=[]`；
  `probe_master_picker5.js` → `asShipped.input.width=498 asShipped.inputOnOwnLine=false
  asShipped.loadSharesLineWithInput=true`，`preRoundDom.inputWidthGain` 从 round 1 核验记录的 `404`
  收到 `171`（剩下的 171 ≈ `Browse...` 80 + `Load` 75 + 间距）。

## 未做项

- P0-1 ~ P1-2 全部完成；除本文件与交付物外没有另外记录「已完成」。
- 未跑全量套件 `run_tests.py`（§9.3 禁止，属 master 核验范围）。
- 未做 §9.3 点名的「不要做」：可展开目录树、拖放、文件内容预览、排序切换、上传、原生
  `<input type=file>` / `showDirectoryPicker()`、新增 `.js` / `.css` 文件。
- 唯一偏离 §9.2 P0-1 / §9.4 D9 字面的一处：**空白字段不落在 `home` 而落在根模式**，
  理由与开关见「待明确」第 1 条。

## 附带发现（不在本次范围，未修）

1. **`assets/fixture2/` 的内容与 §9.5 的期望值不符**。夹具里除 `plain.fna`(16B)、`.dotfile.fna`(10B)、
   `sub/deep.gtf` 之外还有一个 `attr-hidden.fna`(11B)，它的属性是 **Normal**（Samba 上
   `SetFileAttributesW(0x02)` 返回 50，属性位设不上），于是它在缺省与 `hidden=1` 两种模式下**都被列出**：
   `kind=fasta` 缺省 `["sub", "attr-hidden.fna", "plain.fna"]`、`hidden=1`
   `["sub", ".dotfile.fna", "attr-hidden.fna", "plain.fna"]`（§9.5 写的是 `["sub","plain.fna"]` 与
   `["sub",".dotfile.fna","plain.fna"]`）。我的探针因此断言「`.dotfile.fna` 只在 `hidden=1` 出现且落在
   `sub` 之后」这种包含+顺序关系，并把两次接口原样结果一并输出（`fixture2ApiDefault` /
   `fixture2ApiHidden`）；单测不受影响（`test_fs_list_hidden_filter` 用 `tempfile` 自建夹具）。
   **未动夹具、未动探针**，等 master 处置。
2. **`#global-banner` 的既有竞争与 picker 无关**。`probe_master_picker.js` §14 的
   `bannerStayedHidden=false` 不是 picker 写的：同一场景下 `probe_master_picker2.js` 在进弹层**之前**
   记下的 banner 文本，与「picker 报错之后」的文本逐字相同
   （`banner info | Pattern: motif sequence cannot be empty`）——那是探针自己把 pattern / `dp-load`
   置空触发的 designer 预览消息。我的探针也断言了 `bannerUnchangedByPickerError=true`
   （前后都是 `banner info`）。这是 designer 预览与 data prep 校验共用 banner 的既有行为，本轮未碰。
3. **抽屉在 380px 仍有 3px 横向溢出**（`probe_master_picker3.js` 的
   `drawerScrollFits=false`：`drawerScrollWidth=367` > `drawerClientWidth=364`），而
   `probe_master_picker4.js` 的溢出元素清单是空的（`offenders=[]`）。round 1 核验记录的 655px
   （`table.models-table`）在这个页面上没再出现。§9.2 P1-2 只要求路径行可用与 `.picker` 几何，
   3px 不属本轮范围，未修。
4. **打开时的候选游走会与「立刻操作」抢列表**（本轮加了防抖，属实现细节）。round 1 的 `openPicker`
   是「候选逐个请求、第一个 200 胜出」，而 `probe_master_picker.js` / `probe_master_picker2.js` 的用法是
   「打开后不等落地就手输路径点 `Go` / 直接双击行」；在 round 2 的起始目录链（多 1~2 次请求，`R:\` 是
   Samba 共享）下，游走后到的响应会把用户要看的目录覆盖掉。本轮加了 `picker.gen`：`pickerLoad`
   （手输 / `Go` / 面包屑 / 双击 / Back·Forward）自增 `gen`，打开时的游走在每个 `await` 之后检查 `gen`，
   不一致就整体放弃（不再应用、也不再写回）。没改任何对外契约。
5. `webapp/schema.py` 本轮一字未改（`FS_KINDS` / `FS_STRIP` 沿用 round 1），快照里仍按 §9.7 收了一份。

## 待明确

1. **空白字段的起始目录（本轮唯一一处偏离规格字面）**：D9 的字面顺序是
   `字段值 → 其所在目录 → crispr.pickerDir → home → 根模式`，照字面，**字段为空**且没有
   `crispr.pickerDir` 时应停在 `home`；但 `probe_master_picker.js` §13（`rootButtonCount`、
   `rootModeHasNoRows`、`rootClickListedRoot`）与 `probe_master_picker2.js` §7（`rootMode_rootsShown`）
   都要求这条路径落到**根模式**（`#picker-roots` 列出 3 个盘符、列表 0 行、点盘符列举该盘）。
   二者只能选一个，我按 §9 开头「兼容门槛（硬性）」优先，实现为：
   **字段有值**时保留 D9 全链（`值 → 其目录 → pickerDir → home → 根模式`）；
   **字段为空**时跳过 `home`、直接落到根模式（= round 1 行为）。
   `Home` 仍始终是位置栏第一项（`homePlaceFound=true`、`homePlaceWorks=true`），空白字段一点即到。
   要改回 D9 字面语义只需删掉 `webapp/static/app.js:1901` 里 `picker.value &&` 这一处（一行），
   代价是上面两个 master 探针的 4 个键变红。
2. `assets/fixture2/attr-hidden.fna` 如何处置（见「附带发现」1）：删掉它，还是把 §9.5 的期望名单改成
   实际名单？
3. 键盘 `Enter` 选中**目录**行时是「进入」（D13 / §9.2 P0-4），`dir` 类字段要写回当前目录仍需再点
   `OK` 或 `Use this folder`——与 round 1「双击目录 = 进入」一致，未擅改；若希望「`dir` 字段按 `Enter`
   即写回」，说一声我改。
4. `#picker-count` 在根模式（无目录）显示为空串；规格只规定了 `N folders, M files` 与
   ` (listing truncated)`，未规定根模式文案，我按留空处理。

## 环境清理

- 8351 上的 `python webapp\app.py`（PID 35736，22:33 起）已 `Stop-Process`，端口 8351 交还空闲。
- 7 个探针各自的 headless Edge（`--user-data-dir=%TEMP%\edgeprobe_r2_*`）已按 profile 关闭
  （`Get-CimInstance Win32_Process | Where CommandLine -like '*edgeprobe_r2*'` 为空）；
  这些临时 profile 目录本身留在 `%TEMP%`（未删）。
- `assets/fixture/` 与 master 的 6 个探针文件未被写过。
- 7 份探针日志（本报告引用的原文）落在 `%TEMP%\picker_probe_out\<probe>.js.json`，mtime 22:49:39-22:51:45，
  即**改后代码**的最后一次整体运行；7 份日志的 `probeError=null`、`cdpExceptions*=0`、`windowErrors=[]`。
