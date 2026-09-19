# 交付报告：Data prep / Models 改成近满屏大面板（prep 大抽屉）

- round: 1
- status: ready_for_review
- updated: 2026-09-16 21:20
- 改动前快照：`backup/20260916_webapp_big_prep_panel/`（5 个文件，按相对路径存放）
- 产品改动文件：`webapp/index.html`、`webapp/static/app.js`、`webapp/static/styles.css`、
  `docs/WEBAPP.md`、`README.md`（只改这 5 个）；另有本 handoff 目录 `assets/` 下的探针，见文末
- 后端：本轮**没有**改任何 Python / `/api/**` / 测试；`python -m py_compile` 与既有测试用作回归

## 改动清单

### `webapp/index.html`

| 文件:行 | 改了什么 | 对应任务项 |
| --- | --- | --- |
| `webapp/index.html:59-64` | Download 的 2 对 label/控件包进 `<div class="field">`（外层仍是 `<div class="grid">`） | P0-2 |
| `webapp/index.html:76-98` | Genome / annotation 的 5 对包进 `.field` | P0-2 |
| `webapp/index.html:103-117` | Search scope 的 4 对包进 `.field` | P0-2 |
| `webapp/index.html:130-143` | Mask gene 的 4 对包进 `.field`（3 个 `label.inline` 复选框保持原位不动） | P0-2 |
| `webapp/index.html:162` | 新增 `<div id="dp-loaded-hint" class="loaded-hint hidden"></div>`，位于 `#dp-job` 上方 | P0-3 |
| `webapp/index.html:175-177` | `#drawer-resizer` 从 `.workspace` 移到 `</aside>` 内、作为面板最后一个子元素 | P0-1 |
| `webapp/index.html:179` | 新增 `<div id="drawer-scrim" class="scrim hidden"></div>`，紧跟 `</aside>` 之后 | P0-1 |
| `webapp/index.html:189` | 新增专用槽容器 `<div id="designer-left-col"></div>`（在 `#common-inputs-wrap`、`#designer-loaded-hint` 之后） | P0-0 |

### `webapp/static/app.js`

| 文件:行 | 改了什么 | 对应任务项 |
| --- | --- | --- |
| `webapp/static/app.js:136-155` | `setDrawer()` 同步 `#drawer-scrim` 的 `hidden`；`loadModels()` 前加 `$('models-groups')` 守卫 | P0-1 |
| `webapp/static/app.js:162-163` | `DRAWER_MIN_WIDTH` 320 → **380**；新增 `DRAWER_VIEWPORT_GAP = 48`；删除 `DRAWER_MAX_RATIO` | P0-1 |
| `webapp/static/app.js:183-189` | `drawerDefaultWidth() = min(1800, innerWidth - 48)`；`drawerMaxWidth() = max(380, innerWidth - 48)` | P0-1 |
| `webapp/static/app.js:191-196` | `applyDrawerWidth()` 夹到 `[380, max]`，写到 `--drawer-width` | P0-1 |
| `webapp/static/app.js:204-270` | `initDrawerGeometry()` 去掉两处 `innerWidth < 1200` 分支，始终套用「已存宽度或默认宽度」；`setPointerCapture`/`releasePointerCapture` 包 `try/catch`（合成指针） | P0-1 |
| `webapp/static/app.js:370-375` | `#drawer-scrim` 点击 → `setDrawer(false)`（第 4 条关闭路径） | P0-1 |
| `webapp/static/app.js:461-482` | `LOADED_HINT_IDS` + `loadedHintText()`：两处提示共用同一段文案，不存在第二份规则 | P0-3 |
| `webapp/static/app.js:484-502` | `renderLoadedHint()` 同时写 `#designer-loaded-hint` 与 `#dp-loaded-hint`（`textContent` + `title` 完全一致） | P0-3 |
| `webapp/static/app.js:538-546` | 本次作业没有任何字段可带入时 `state.loadedHint = null` → 两处提示都回到 `hidden` | P0-3 |
| `webapp/static/app.js:723-727` | `renderCommon()` 加 `if (!container) { return; }` 守卫 | P0-0 |
| `webapp/static/app.js:764-768` | `SLOT_CONTAINERS.left = 'designer-left-col'`（不再指向 `#designer-common-col`） | **P0-0 根因修复** |
| `webapp/static/app.js:791-806` | `renderPattern()` 只清空三个 slot 容器（各自带守卫），静态 Common Inputs 不再被清掉 | **P0-0 根因修复** |
| `webapp/static/app.js:808-812` | `renderRun()` 加 `if (!container) { return; }` 守卫 | P0-0 |

### `webapp/static/styles.css`

| 文件:行 | 改了什么 | 对应任务项 |
| --- | --- | --- |
| `webapp/static/styles.css:13` | `--drawer-width: min(1800px, calc(100% - 48px))`（首屏兜底值）；删掉 `--drawer-width-default` 与 `--resizer-width` | P0-1 |
| `webapp/static/styles.css:102-107` | `.workspace` 只留主区一列（`minmax(0, 1fr)`）；删掉「未打开就把抽屉压成 0 宽」的规则 | P0-1 |
| `webapp/static/styles.css:111-126` | `.drawer` = `position: fixed` 左侧滑出面板：`z-index: 40`、`width: var(--drawer-width)`、`overflow-y: auto`、`border-right`、`box-shadow`、关闭态 `translateX(-102%)` + `visibility: hidden` + `transition: transform .18s ease, visibility 0s linear .18s` | P0-1 |
| `webapp/static/styles.css:128-132` | `.drawer.open` = `transform: none; visibility: visible; transition-delay: 0s`（关闭后输入框不会被 Tab 聚焦） | P0-1 |
| `webapp/static/styles.css:136-149` | `.drawer-resizer` 改为面板内绝对定位 `right: -3px` / `width: 6px`（固定面板即包含块），保留 hover/focus 高亮与 `body.resizing` | P0-1 |
| `webapp/static/styles.css:152-157` | `.scrim`：`position: fixed; inset: 0; z-index: 35; background: rgba(16,24,40,.16)` | P0-1 |
| `webapp/static/styles.css:178-184` | `.drawer .grid` → `repeat(auto-fit, minmax(330px, 1fr))` + `gap: 10px 20px` + `align-items: start`；`.drawer .field { margin-bottom: 0 }`（只加 `.drawer` 前缀，主区 `.field` 不受影响） | P0-2 |
| 整块删除 `@media (max-width: 1199px)`（原 `:429-455`） | 不再有「宽屏并排 / 窄屏覆盖」二分；只保留 `@media (max-width: 1399px)`（现 `:439`）三列纵向堆叠 | P0-1 |

### `docs/WEBAPP.md` / `README.md`

| 文件:行 | 改了什么 | 对应任务项 |
| --- | --- | --- |
| `docs/WEBAPP.md:4-6` | 概览句：Designer 常驻主区，Data prep / Models 是左侧滑出的**近满屏面板** | P0-5 |
| `docs/WEBAPP.md:37-95` | 「单页工作区」ASCII 图重画为「收起 / 展开（38-69 行）」，并写清几何（`min(1800px, 视口宽 − 48px)`、最小 380px）、拖动条（方向键 / 双击复位）、`crispr.drawerWidth` / `crispr.drawerOpen`、**4 种关闭方式**、多列字段排布；响应式一条改为「所有视口同一套行为」 | P0-5 |
| `docs/WEBAPP.md:103-114` | 「面板：Data prep / Models」补：几何与 4 种关闭方式、两处「已带入」提示（`#designer-loaded-hint` + `#dp-loaded-hint`，同一段拼串）、字段多列排布 | P0-5 |
| `docs/WEBAPP.md:115` | 仅补一个空行（`### 回填规则` 前），否则该标题会被渲染进上面的列表；该节**内容**未动 | P0-5 |
| `README.md:30` | `webapp/app.py` 描述 → 「单页工作区（Designer 常驻主区 + Data prep/Models 近满屏滑出面板）」 | P0-5 |

### 编码与格式（P0-4）

5 个产品文件全部重写为 **UTF-8 无 BOM + LF**（§6 第 4 条是证据）。
`docs/WEBAPP.md` 的 API / 安全边界 / 启动 章节与 `README.md:97`（启动命令）未改。

## 轻量自检结果

> 服务沿用 §8.6 那条 `python webapp\app.py --port 8351`（同一个 app，静态文件按请求现读，
> 改完不需要重启）；§6.5 里写的 8349 与它是同一个入口，本轮统一跑在 8351 上。

### 1. `node --check webapp\static\app.js`

```powershell
& 'C:\Users\ASUS\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe' --check webapp\static\app.js
"exit=$LASTEXITCODE"
```

```text
exit=0
```

### 2. `python -m py_compile webapp\app.py webapp\schema.py webapp\jobs.py`

```powershell
python -m py_compile webapp\app.py webapp\schema.py webapp\jobs.py
"exit=$LASTEXITCODE"
```

```text
exit=0
```

### 3. `python -m unittest tests.test_webapp tests.test_workbench_form -v`

```powershell
python -m unittest tests.test_webapp tests.test_workbench_form -v 2>&1 | Select-Object -Last 25
```

```text
test_empty_inputs_report_required_fields (tests.test_workbench_form.ErrorBranchTests.test_empty_inputs_report_required_fields) ... ok
test_memory_limit_modes (tests.test_workbench_form.ErrorBranchTests.test_memory_limit_modes) ... ok
test_missing_and_unreadable_inputs_are_reported_in_order (tests.test_workbench_form.ErrorBranchTests.test_missing_and_unreadable_inputs_are_reported_in_order) ... ok
test_output_dir_pointing_at_a_file (tests.test_workbench_form.ErrorBranchTests.test_output_dir_pointing_at_a_file) ... ok
test_pattern_errors_are_reported_last (tests.test_workbench_form.ErrorBranchTests.test_pattern_errors_are_reported_last) ... ok
test_search_timeout_values (tests.test_workbench_form.ErrorBranchTests.test_search_timeout_values) ... ok
test_gap_pair_requires_every_policy_value (tests.test_workbench_form.PairModeTests.test_gap_pair_requires_every_policy_value) ... ok
test_gap_pair_spec_and_config (tests.test_workbench_form.PairModeTests.test_gap_pair_spec_and_config) ... ok
test_partial_policy_is_reported_field_by_field (tests.test_workbench_form.PairModeTests.test_partial_policy_is_reported_field_by_field) ... ok
test_y_centered_spec_and_config (tests.test_workbench_form.PairModeTests.test_y_centered_spec_and_config) ... ok
test_active_side_updates (tests.test_workbench_form.PresetAndModelTests.test_active_side_updates) ... ok
test_cas12a_preset_updates_the_target_side (tests.test_workbench_form.PresetAndModelTests.test_cas12a_preset_updates_the_target_side) ... ok
test_cas9_preset_updates_the_left_side (tests.test_workbench_form.PresetAndModelTests.test_cas9_preset_updates_the_left_side) ... ok
test_helpers (tests.test_workbench_form.PresetAndModelTests.test_helpers) ... ok
test_resolve_side_model_selection (tests.test_workbench_form.PresetAndModelTests.test_resolve_side_model_selection) ... ok
test_side_model_options_follow_the_nuclease (tests.test_workbench_form.PresetAndModelTests.test_side_model_options_follow_the_nuclease) ... ok
test_bed_mode_moves_the_search_input_to_regions (tests.test_workbench_form.SingleModeTests.test_bed_mode_moves_the_search_input_to_regions) ... ok
test_default_run_label_is_system_and_target_name (tests.test_workbench_form.SingleModeTests.test_default_run_label_is_system_and_target_name) ... ok
test_result_label_overrides_the_default (tests.test_workbench_form.SingleModeTests.test_result_label_overrides_the_default) ... ok
test_spec_and_config_use_the_form_values (tests.test_workbench_form.SingleModeTests.test_spec_and_config_use_the_form_values) ... ok

----------------------------------------------------------------------
Ran 77 tests in 43.743s

OK
```

### 4. BOM / LF（§1.5 的一行命令）

```powershell
python -c "p=[r'webapp\index.html',r'webapp\static\app.js',r'webapp\static\styles.css']; [print(f, open(f,'rb').read(3)==b'\xef\xbb\xbf', b'\r' in open(f,'rb').read()) for f in p]"
python -c "p=[r'docs\WEBAPP.md',r'README.md']; [print(f, open(f,'rb').read(3)==b'\xef\xbb\xbf', b'\r' in open(f,'rb').read()) for f in p]"
```

```text
webapp\index.html False False
webapp\static\app.js False False
webapp\static\styles.css False False
docs\WEBAPP.md False False
README.md False False
```

### 5. 结构探针（HTTP 200 + 位置 + 计数）

```powershell
python docs\handoff\webapp-big-prep-panel\assets\probe_panel_structure.py http://127.0.0.1:8351
```

```text
GET / -> HTTP 200 (10478 bytes)
PASS GET / is 200
PASS GET / has the resizer
PASS GET / has the scrim
PASS GET / has the panel hint
PASS GET / has the left slot container
PASS resizer sits before </aside>
grid blocks found: 4
direct .field children: 15 | bare label/input/select: 0
PASS no bare control directly under .grid
PASS 15 field wrappers in the four grid blocks
GET /api/schema -> HTTP 200 (15181 bytes, 15 keys)
PASS GET /api/schema is 200

probe_panel_structure.py: all checks passed
```

### 6. 截图

```powershell
& 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe' --headless --disable-gpu --no-first-run --user-data-dir="$env:TEMP\edgeshot_servant" --window-size=1600,1000 --screenshot="R:\songji\programfile\out\big_panel_closed.png" http://127.0.0.1:8351/
```

```text
54928 bytes written to file R:\songji\programfile\out\big_panel_closed.png
```

关闭态截图 `out\big_panel_closed.png` 里可看到 P0-0 修复后的主区：`Common Inputs`
（`<details>`，含 INPUT 单选与 6 个字段）→ 左列 `TARGET TAM`，整块都在。

headless 的 `--screenshot` 不能点按钮（§6.6 说明），所以**面板打开态**用 CDP 点真实
`#drawer-toggle` 再截图（未往产品代码加任何 `?drawer=1` 之类的调试开关）：

```powershell
$env:CDP_PORT='9333'; $env:APP_URL='http://127.0.0.1:8351/'
& 'C:\Users\ASUS\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe' docs\handoff\webapp-big-prep-panel\assets\shot_open_panel.js out\big_panel_open.png
```

```text
panel width = 1552px
wrote out\big_panel_open.png (76483 bytes)
```

`panel width = 1552px` 正是 §1.2 的期望值（1600 − 48）；截图里可见 Download 2 列、
Genome / annotation 4 列、Search scope 4 列、Mask gene 4 列，右侧留着 48px 缝。
## §8.6 回归探针（P0-0）原文与断言对照

```powershell
$env:CDP_PORT='9333'; $env:APP_URL='http://127.0.0.1:8351/'; $env:WAIT_MS='9000'
& 'C:\Users\ASUS\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe' docs\handoff\webapp-big-prep-panel\assets\probe_browser_cdp.js docs\handoff\webapp-big-prep-panel\assets\probe_mode_switch.js
```

```json
{
  "url": "http://127.0.0.1:8351/",
  "probe": "{\n  \"modes\": [\n    \"single_motif_flank\",\n    \"motif_gap_motif\",\n    \"y_centered_motifs\"\n  ],\n  \"before\": {\n    \"mode\": \"single_motif_flank\",\n    \"hasCommonInputsWrap\": true,\n    \"hasCommonFields\": true,\n    \"hasLoadedHint\": true,\n    \"commonFieldsRendered\": 6,\n    \"leftHeads\": [\n      \"Input\",\n      \"Common Inputs\",\n      \"Target TAM\"\n    ],\n    \"middleHeads\": [],\n    \"rightHeads\": [],\n    \"leftHasGenomeInput\": true\n  },\n  \"switchedTo\": \"y_centered_motifs\",\n  \"after\": {\n    \"mode\": \"y_centered_motifs\",\n    \"hasCommonInputsWrap\": true,\n    \"hasCommonFields\": true,\n    \"hasLoadedHint\": true,\n    \"commonFieldsRendered\": 6,\n    \"leftHeads\": [\n      \"Input\",\n      \"Common Inputs\",\n      \"Left TAM\"\n    ],\n    \"middleHeads\": [\n      \"Middle\"\n    ],\n    \"rightHeads\": [\n      \"Right TAM\"\n    ],\n    \"leftHasGenomeInput\": true\n  },\n  \"windowErrors\": []\n}",
  "probeError": null,
  "cdpExceptionsDuringLoad": 0,
  "cdpExceptionsTotal": 0,
  "cdpEvents": []
}
```

断言对照（§8.6「修复后必须同时满足」）：

| 断言 | 本轮实测 | 结论 |
| --- | --- | --- |
| `before.hasCommonInputsWrap == true` | `true` | 通过 |
| `before.hasCommonFields == true` | `true`（`commonFieldsRendered = 6`） | 通过 |
| `before.hasLoadedHint == true` | `true` | 通过 |
| `cdpExceptionsTotal == 0` | `0`（`cdpExceptionsDuringLoad = 0`、`windowErrors = []`） | 通过 |
| `after.middleHeads == ["Middle"]` | `["Middle"]` | 通过 |
| `after.rightHeads == ["Right TAM"]` | `["Right TAM"]` | 通过 |
| `after.leftHeads != before.leftHeads` | `Target TAM` → `Left TAM`（中/右列从空变为有组） | 通过 |
| `before.leftHeads == ["Target TAM"]` | 探针实际返回 `["Input", "Common Inputs", "Target TAM"]` | **口径不符，见下** |
| `after.leftHeads == ["Left TAM"]` | 探针实际返回 `["Input", "Common Inputs", "Left TAM"]` | **口径不符，见下** |

`leftHeads` 口径说明：该探针（master 原样复用，未改）取的是 `#designer-common-col` 范围内
**全部** `<h4>`。修复前整列已被 `renderPattern()` 清空，所以只剩左 slot 的 `Target TAM`；
修复把 `#common-inputs-wrap` 恢复回来之后，`renderCommon()` 自己就往
`#designer-common-fields` 里渲染 `<h4>Input</h4>` 与 `<h4>Common Inputs</h4>`
（`webapp/static/app.js:731-751`），于是这两项必然出现。也就是说，两条字面断言与
§8.4「把静态 Common Inputs 还回来」在同一个探针口径下**互斥**；多出的两项是修复的
正确结果，不是残留。

为了把 §8.6 想要的字面值也测出来，另加了一个按 slot 容器取标题的补充探针（master 的
`probe_mode_switch.js` 仍未改动）：

```powershell
$env:CDP_PORT='9333'; $env:APP_URL='http://127.0.0.1:8351/'; $env:WAIT_MS='9000'
& 'C:\Users\ASUS\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe' docs\handoff\webapp-big-prep-panel\assets\probe_browser_cdp.js docs\handoff\webapp-big-prep-panel\assets\probe_mode_switch_slots.js
```

```json
{
  "url": "http://127.0.0.1:8351/",
  "probe": "{\n  \"before\": {\n    \"mode\": \"single_motif_flank\",\n    \"commonColDirectChildren\": [\n      \"common-inputs-wrap\",\n      \"designer-loaded-hint\",\n      \"designer-left-col\"\n    ],\n    \"staticBlockHeads\": [\n      \"Input\",\n      \"Common Inputs\"\n    ],\n    \"leftSlotHeads\": [\n      \"Target TAM\"\n    ],\n    \"middleSlotHeads\": [],\n    \"rightSlotHeads\": [],\n    \"inputMode\": \"sequence\"\n  },\n  \"switchedTo\": \"y_centered_motifs\",\n  \"after\": {\n    \"mode\": \"y_centered_motifs\",\n    \"commonColDirectChildren\": [\n      \"common-inputs-wrap\",\n      \"designer-loaded-hint\",\n      \"designer-left-col\"\n    ],\n    \"staticBlockHeads\": [\n      \"Input\",\n      \"Common Inputs\"\n    ],\n    \"leftSlotHeads\": [\n      \"Left TAM\"\n    ],\n    \"middleSlotHeads\": [\n      \"Middle\"\n    ],\n    \"rightSlotHeads\": [\n      \"Right TAM\"\n    ],\n    \"inputMode\": \"sequence\"\n  },\n  \"windowErrors\": []\n}",
  "probeError": null,
  "cdpExceptionsDuringLoad": 0,
  "cdpExceptionsTotal": 0,
  "cdpEvents": []
}
```

即：`leftSlotHeads` 修复后 = `["Target TAM"]`、切到 `y_centered_motifs` 后 = `["Left TAM"]`
（中 `["Middle"]`、右 `["Right TAM"]`），且 `commonColDirectChildren` 恒为
`["common-inputs-wrap", "designer-loaded-hint", "designer-left-col"]`（§8.4 第 2 条），
`windowErrors` 为空。
## 补充证据（本轮新增探针，非 master 脚本）

### 面板几何 / 4 条关闭路径（P0-1，D2/D4/D5/D6）

```powershell
$env:CDP_PORT='9333'; $env:APP_URL='http://127.0.0.1:8351/'; $env:WAIT_MS='9000'
& 'C:\Users\ASUS\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe' docs\handoff\webapp-big-prep-panel\assets\probe_browser_cdp.js docs\handoff\webapp-big-prep-panel\assets\probe_panel_geometry.js
```

```json
{
  "url": "http://127.0.0.1:8351/",
  "probe": "{\n  \"viewport\": {\n    \"w\": 1574,\n    \"h\": 907\n  },\n  \"pageLoaded\": true,\n  \"resizerInsidePanel\": true,\n  \"dpLoadedHintExists\": true,\n  \"scrimExists\": true,\n  \"open\": {\n    \"drawerClasses\": \"drawer open\",\n    \"ariaHidden\": \"false\",\n    \"ariaExpanded\": \"true\",\n    \"cssVar\": \"1526px\",\n    \"drawerRect\": {\n      \"left\": 0,\n      \"right\": 1526,\n      \"width\": 1526\n    },\n    \"scrimHidden\": false,\n    \"scrimRect\": {\n      \"left\": 0,\n      \"right\": 1559,\n      \"width\": 1559\n    },\n    \"resizerRect\": {\n      \"left\": 1507,\n      \"right\": 1513,\n      \"width\": 6\n    },\n    \"drawerGrids\": {\n      \"grids\": 4,\n      \"fields\": 15,\n      \"bareLabels\": 0,\n      \"bareInputs\": 0,\n      \"bareSelects\": 0,\n      \"inlineChecks\": 3,\n      \"firstColumns\": \"716px 716px 0px 0px\"\n    }\n  },\n  \"afterArrowLeft\": {\n    \"left\": 0,\n    \"right\": 1510,\n    \"width\": 1510\n  },\n  \"storedWidth\": \"1510\",\n  \"afterDoubleClick\": {\n    \"left\": 0,\n    \"right\": 1526,\n    \"width\": 1526\n  },\n  \"cssVarAfterReset\": \"1526px\",\n  \"afterScrimClick\": {\n    \"drawerClasses\": \"drawer\",\n    \"ariaHidden\": \"true\",\n    \"scrimHidden\": true,\n    \"drawerRight\": -31\n  },\n  \"reopened\": {\n    \"drawerClasses\": \"drawer open\",\n    \"scrimHidden\": false\n  },\n  \"afterCloseButton\": {\n    \"drawerClasses\": \"drawer\",\n    \"ariaHidden\": \"true\",\n    \"scrimHidden\": true,\n    \"drawerRight\": -31\n  },\n  \"windowErrors\": []\n}",
  "probeError": null,
  "cdpExceptionsDuringLoad": 0,
  "cdpExceptionsTotal": 0,
  "cdpEvents": []
}
```

要点：面板宽 = 视口宽 − 48（1574 − 48 = 1526）；拖动条在面板内、落在右边缘
（`1507..1513`，宽 6px）；`ArrowLeft` → 1510 且写入 `localStorage` 的
`crispr.drawerWidth`；双击复位到 1526；点遮罩与点 `Close` 都让
`aria-hidden="true"`、遮罩重新隐藏、面板整块移到视口外（`right = -31`，即
`-102%` 的余量）；重开正常；`windowErrors` 为空。4 条关闭路径里的 `Esc` / 顶部条按钮
由 `app.js:359-374` 的同一段代码处理（`setDrawer(false)`）。

### 面板内多列字段（P0-2 / §1.3 第 4 条）

```powershell
& 'C:\Users\ASUS\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe' docs\handoff\webapp-big-prep-panel\assets\probe_browser_cdp.js docs\handoff\webapp-big-prep-panel\assets\probe_panel_grid_all.js
```

```json
{
  "url": "http://127.0.0.1:8351/",
  "probe": "{\n  \"viewport\": {\n    \"w\": 1574,\n    \"h\": 907\n  },\n  \"atDefault\": {\n    \"width\": 1526,\n    \"grids\": [\n      {\n        \"index\": 0,\n        \"fields\": 2,\n        \"columns\": \"716px 716px 0px 0px\"\n      },\n      {\n        \"index\": 1,\n        \"fields\": 5,\n        \"columns\": \"348px 348px 348px 348px\"\n      },\n      {\n        \"index\": 2,\n        \"fields\": 4,\n        \"columns\": \"348px 348px 348px 348px\"\n      },\n      {\n        \"index\": 3,\n        \"fields\": 4,\n        \"columns\": \"348px 348px 348px 348px\"\n      }\n    ]\n  },\n  \"atMinimum\": {\n    \"width\": 380,\n    \"grids\": [\n      {\n        \"index\": 0,\n        \"fields\": 2,\n        \"columns\": \"330px\"\n      },\n      {\n        \"index\": 1,\n        \"fields\": 5,\n        \"columns\": \"330px\"\n      },\n      {\n        \"index\": 2,\n        \"fields\": 4,\n        \"columns\": \"330px\"\n      },\n      {\n        \"index\": 3,\n        \"fields\": 4,\n        \"columns\": \"330px\"\n      }\n    ]\n  },\n  \"windowErrors\": []\n}",
  "probeError": null,
  "cdpExceptionsDuringLoad": 0,
  "cdpExceptionsTotal": 0,
  "cdpEvents": []
}
```

默认宽度下面板里的 5 字段组（Genome / annotation）与两个 4 字段组（Search scope、
Mask gene）都排成 **4 列 × ≥330px**；380px 时四个 `.grid` 全部退化成 1 列。
Download 组只有 2 个字段，`auto-fit` 给它 2 列（`716px 716px`）是正确行为，
不是漏排。

### 拖动条钳位（最小 380 / 最大 视口宽 − 48）

```powershell
& 'C:\Users\ASUS\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe' docs\handoff\webapp-big-prep-panel\assets\probe_browser_cdp.js docs\handoff\webapp-big-prep-panel\assets\probe_panel_grid.js
```

```json
{
  "url": "http://127.0.0.1:8351/",
  "probe": "{\n  \"viewport\": {\n    \"w\": 1574,\n    \"h\": 907\n  },\n  \"atDefault\": {\n    \"width\": 1526,\n    \"columns\": \"716px 716px 0px 0px\"\n  },\n  \"afterDragToZero\": {\n    \"width\": 380,\n    \"columns\": \"330px\"\n  },\n  \"afterDragToMax\": {\n    \"width\": 1526,\n    \"columns\": \"716px 716px 0px 0px\"\n  },\n  \"windowErrors\": []\n}",
  "probeError": null,
  "cdpExceptionsDuringLoad": 0,
  "cdpExceptionsTotal": 0,
  "cdpEvents": []
}
```

### 回填提示同时出现在两处（P0-3 / §1.4）

```powershell
& 'C:\Users\ASUS\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe' docs\handoff\webapp-big-prep-panel\assets\probe_browser_cdp.js docs\handoff\webapp-big-prep-panel\assets\probe_loaded_hint.js
```

```json
{
  "url": "http://127.0.0.1:8351/",
  "probe": "{\n  \"before\": {\n    \"designerText\": \"\",\n    \"designerHidden\": true,\n    \"designerTitle\": \"\",\n    \"panelText\": \"\",\n    \"panelHidden\": true,\n    \"panelTitle\": \"\"\n  },\n  \"afterBackfill\": {\n    \"designerText\": \"已带入 / Loaded: search_fasta, output_dir, genome_fasta\",\n    \"designerHidden\": false,\n    \"designerTitle\": \"From job probejob0001 (Extract Target FASTA):\\nsearch_fasta = R:\\\\probe\\\\PROBE1-gene.fa\\noutput_dir = R:\\\\probe\\\\out\\ngenome_fasta = R:\\\\probe\\\\genome.fa\",\n    \"panelText\": \"已带入 / Loaded: search_fasta, output_dir, genome_fasta\",\n    \"panelHidden\": false,\n    \"panelTitle\": \"From job probejob0001 (Extract Target FASTA):\\nsearch_fasta = R:\\\\probe\\\\PROBE1-gene.fa\\noutput_dir = R:\\\\probe\\\\out\\ngenome_fasta = R:\\\\probe\\\\genome.fa\"\n  },\n  \"values\": {\n    \"search_fasta\": 6,\n    \"dp_genome\": \"\",\n    \"output_dir_written\": true\n  },\n  \"identical\": true,\n  \"afterEmptyJob\": {\n    \"designerText\": \"\",\n    \"designerHidden\": true,\n    \"designerTitle\": \"\",\n    \"panelText\": \"\",\n    \"panelHidden\": true,\n    \"panelTitle\": \"\"\n  },\n  \"windowErrors\": []\n}",
  "probeError": null,
  "cdpExceptionsDuringLoad": 0,
  "cdpExceptionsTotal": 0,
  "cdpEvents": []
}
```

`identical: true`：两处 `textContent` 与 `title` 逐字相同；本次作业无字段可带入时
（`afterEmptyJob`）两处都回到 `hidden`。
## 未做项

- **方案 A**（Designer 也做成滑出面板 / 左右双抽屉 / 两个面板并排）—— §4 明确不做；本轮只做方案 B。
- `python -m unittest discover` 全量套件 —— §6.7 说那是 master 的事，未跑。
- `webapp/app.py` / `schema.py` / `jobs.py` / `services/**` / `job_store.py` / `shared/**` / `/api/**` ——
  本轮不需要改，也没有改（`py_compile` 与 77 个既有用例只是确认没被顺手改坏）。
- `tests/**` —— 只跑不改。
- `docs/handoff/webapp-designer-port/**`、`docs/handoff/webapp-single-page-layout/**` —— 只读，未动。
- `docs/WEBAPP.md` 的 API / 安全边界 / 启动 三节与 `README.md:97`（启动命令）—— §1.6 要求不动，未动。
- `CRISPR-Motif-Workbench.exe`、`tools/launcher/**` —— 未动，也没有把启动器写进文档。
- 前端框架 / CDN / 打包器 / web font / 新图片 —— 未引入：页面只有
  `/static/styles.css` 与 `/static/app.js` 两个本地资源，`index.html` 里对
  `http://…|cdn.|unpkg|jsdelivr` 的匹配数为 0，`styles.css` 里 `@font-face` / `url(` 的匹配数为 0。
- 为截图加 `?drawer=1` 之类的调试开关 —— 没加；打开态截图是用 CDP 点真实 `#drawer-toggle` 得到的。
- 删除文件 —— 未删任何文件。

## 附带发现（不在本次范围，未修）

- `webapp/jobs.py:265,274` —— 子进程日志用 `encoding="utf-8", errors="replace"` 读写，Windows 下
  子进程打印的中文会变成替换字符（既有 P1，来自上一轮 review）。
- `tests/test_webapp.py:581` —— 用例名 `test_index_page_has_the_four_tabs` 已经过时（早就没有
  「四个页签」了），断言本身仍然有效，所以没动它。
- `webapp/services/dataprep.py:457-479` —— `build-index` 只给 `--prefix` 时，第 478 行仍把
  `output_dir` 写成空串；回填侧不会因此填错字段（与规格一致，只是 `outputs` 里留了个空键）。
- `webapp/services/designer.py:246-251` —— 单靶点抽取时 `bed_regions` 取自单模式的 `regions`（空），
  桌面端行为相同。
- **探针口径**（本轮最值得记录的一条）：`assets/probe_mode_switch.js`（master 原样）的 `leftHeads`
  统计整个 `#designer-common-col` 的 `<h4>`，与 §8.6 的两条字面断言在「静态 Common Inputs 必须
  恢复」这个前提下互斥 —— 详见上文「§8.6 回归探针」一节的说明与 `probe_mode_switch_slots.js` 的
  补充输出。master 的探针脚本**没有**被改。
- 遮罩（`z-index: 35`）覆盖整个视口，于是右侧那 48px 缝也被压暗，且缝上的**第一次点击只会关闭面板**
  （这正是 D4「点击遮罩即关闭」）。如果希望缝本身可以直接点（例如点回 Designer 露出来的那块内容），
  需要把遮罩右边界停在面板右缘 —— 这会改变 4 条关闭路径的语义，servant 侧没有擅自改。

## 待明确

- 48px 缝要不要「第一次点击就落到缝后面的内容」？当前行为（先关面板）与 D4 一致，若要与 D4 不同请明示。
- §8.6 的 `leftHeads` 字面断言要不要按新口径重写（改成只看 `#designer-left-col`，或直接引用
  `probe_mode_switch_slots.js` 的读数）？本轮只在报告里说明，未改 master 的探针脚本。

## 本轮新增 / 改动的非产品文件（都在本 handoff 目录内）

- 新增探针：`assets/probe_panel_structure.py`、`assets/probe_panel_geometry.js`、
  `assets/probe_panel_grid.js`、`assets/probe_panel_grid_all.js`、`assets/probe_loaded_hint.js`、
  `assets/probe_mode_switch_slots.js`，以及截图助手 `assets/shot_open_panel.js`。
- 改动：`assets/probe_browser_cdp.js` —— **唯一**改动是在 `Runtime.evaluate` 上加
  `awaitPromise: true`（新增的几何 / 回填提示探针是异步函数，没有它拿不到返回值）。异常捕获与
  断言逻辑一字未改；§8.6 那条命令用的就是这个文件。
- 截图产物：`out\big_panel_closed.png`、`out\big_panel_open.png`（`out/` 是仓库既有的产物目录）。

## 结论

§0-§7 与 §8 的 P0-0…P0-5 全部落地：P0-0 的根因（`SLOT_CONTAINERS.left` 指错列）已修好，
切模式 / 输入模式单选 / 预设 / 模型下拉 / 回填重绘都能刷新；面板几何、多列字段、两处回填提示、
编码与文档按契约完成。§6 的 6 条自检全部通过；§8.6 探针 `cdpExceptionsTotal = 0`、
切到 `y_centered_motifs` 后左/中/右列从 `Target TAM` + 空 + 空 变为 `Left TAM` + `Middle` +
`Right TAM`，控制台零未捕获异常。唯一与 §8.6 字面断言不一致的是 `leftHeads` 的**统计口径**，
已在上文说明并附按 slot 容器取值的补充证据。