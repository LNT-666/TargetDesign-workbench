# 交付报告：webapp-model-labels

- round: 1
- status: ready_for_review
- updated: 2026-09-17 10:40
- 起始快照：`backup/20260917_webapp_model_labels/`（6 个文件已按相对路径落盘）

## 改动清单

| 文件 | 行 | 改了什么 | 对应任务项 |
| --- | --- | --- | --- |
| `webapp/schema.py` | `:28`（import）、`:358-363`、`:374-375` | 顶层新增 `model_labels = {key: model_display_name(key)}`，覆盖 `PRESET_KEYS` 全部 on/off 选项（14 个 key）；`preset_models` 改为先算一次再复用 | P0-1 |
| `webapp/static/app.js` | `:694-765`（新增 `modelDisplayLabel`、`splitModelKeys`、`paintModelOptions`、`MODEL_SELECT_HINT`、`sideModelHint`；`modelSelect` 多一个 `refreshHint` 参数）、`:767-781`（`renderSideModels` 用 `sideModelHint`，hint 节点复用） | `<option>` 文本改用 `state.schema.model_labels[model]`；primary（第一个选中项）加 `[P] ` 前缀；hint 追加 `Primary: …`；`value`、`multiple`、`size`、写进 state 的逗号串格式全部不变 | P0-2 |
| `webapp/static/app.js` | `:1268`、`:1282-1286` | Models 表头改成 `['Model','Status','Path','Description','']`；路径单元格 `model.path \|\| model.url \|\| ''`；新增描述单元格 `model.description \|\| ''`（`class="muted"`） | P0-3 |
| `tests/test_webapp.py` | `:27`、`:30`（import）、`:226-239`、`:573-591` | 新增 `test_model_labels_match_the_shared_display_names`、`test_model_descriptions_come_from_the_registry` | P1-1 |
| `docs/WEBAPP.md` | `:99-104`、`:122-125`、`:189`、`:195` | 侧模型选择器多选/显示名/primary 说明；Models 面板 `description` + `url` 回退；API 表 `/api/schema`、`/api/models` 两行 | P0-4 |
| `docs/handoff/webapp-model-labels/assets/probe_servant_model_labels.js` | 新增（158 行） | 新写 DOM 探针（页面内 async IIFE，`return JSON.stringify(...)`） | §6 |
| `docs/handoff/webapp-model-labels/assets/probe_servant_model_labels.out.json` | 新增 | 探针原始输出（真实页面跑完后落盘，master 可直接查证，不必重跑） | §6 |

未改（与快照逐字节相同）：`webapp/index.html`、`webapp/static/styles.css`。未改 `webapp/services/*`、`shared/*`、`main.py`、`designer_workbench.py`、`unified_gui.py`、`README.md`。

## 轻量自检结果

### 1) 语法检查

```powershell
python -m py_compile R:\songji\programfile\webapp\schema.py
& '<node.exe>' --check R:\songji\programfile\webapp\static\app.js
& '<node.exe>' --check R:\songji\programfile\docs\handoff\webapp-model-labels\assets\probe_servant_model_labels.js
```

```text
py_compile EXIT=0
node EXIT=0          (webapp/static/app.js)
node EXIT=0          (probe_servant_model_labels.js)
```

### 2) P0-1 证据：`/api/schema` 的 `model_labels` == `model_display_name` 直调

```powershell
python -c "
import json
import schema
from design.workbench_form import PRESET_KEYS, side_model_options, model_display_name
doc = schema.build_schema()
labels = doc['model_labels']
expected = {}
for key in PRESET_KEYS:
    options = side_model_options(key)
    for model in list(options['on_target']) + list(options['off_target']):
        expected.setdefault(model, model_display_name(model))
print('labels == expected:', labels == expected)
print('label_count:', len(labels))
print(json.dumps(labels, sort_keys=True))
"
```

```text
labels == expected: True
label_count: 14
{"cfd": "[Cas9] [rule] cfd", "crispai": "[Cas9] crispai", "crispr_m": "[Cas9] crispr_m", "cropsr": "[Cas9] cropsr", "deepcas12a": "[Cas12a] deepcas12a", "deepcpf1": "[Cas12a] deepcpf1", "deepcrispr": "[Cas9] deepcrispr", "identity": "[General] [rule] identity", "omega": "[TnpB] [rule] omega", "pfs": "[Cas13] [rule] pfs", "rna_rules": "[Cas13] [rule] rna_rules", "rules": "[General] [rule] rules", "teep": "[TnpB] teep", "tiger": "[Cas13] tiger"}
```

### 3) 聚焦单测（改动前基线 → 改动后）

```powershell
python -m unittest tests.test_webapp -v
```

```text
# 改动前基线
Ran 60 tests in 50.813s
OK

# 改动后
test_model_descriptions_come_from_the_registry (tests.test_webapp.ModelServiceTests.test_model_descriptions_come_from_the_registry) ... ok
test_model_labels_match_the_shared_display_names (tests.test_webapp.SchemaTests.test_model_labels_match_the_shared_display_names) ... ok
Ran 62 tests in 49.894s
OK
```

### 4) DOM 级探针（本任务唯一「真跑界面」证据）

```powershell
# 终端 A（服务；见文末「环境与偏差」：本机 R: 作 cwd 会卡死，故用绝对路径 + 本地盘 cwd）
Start-Process python -ArgumentList R:\songji\programfile\webapp\app.py,--port,8361 -WindowStyle Hidden
# 终端 B（headless Edge，一直占着）
& 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe' --headless=new --disable-gpu --no-first-run --user-data-dir=C:\Users\ASUS\AppData\Local\Temp\edgeprobe_models --remote-debugging-port=9343 about:blank
# 终端 C（探针）
$env:CDP_PORT='9343'; $env:APP_URL='http://127.0.0.1:8361/'; $env:WAIT_MS='12000'
& 'C:\Users\ASUS\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe' `
  R:\songji\programfile\docs\handoff\webapp-model-labels\assets\probe_browser_cdp.js `
  R:\songji\programfile\docs\handoff\webapp-model-labels\assets\probe_servant_model_labels.js
```

输出（完整原文见 `assets/probe_servant_model_labels.out.json`；下面按 §6 要求的键逐条摘录）：

```text
probeError = null        cdpExceptionsDuringLoad = 0   cdpExceptionsTotal = 0
modelLabelCount = 14

optionValues  = ["cropsr"]
optionLabels  = ["[Cas9] cropsr"]
expectedLabels= ["[Cas9] cropsr"]                -> optionLabelsEqualExpectedLabels = true
selectMultipleStillTrue = true                   sizeAfter = 2
firstSelectGroupTitle = "Target TAM"             multiSelectCount = 2

selectDetails[0] = {"values":["cropsr"],"texts":["[Cas9] cropsr"],"expected":["[Cas9] cropsr"],"labelsEqualExpected":true}
selectDetails[1] = {"values":["cfd","crispr_m","deepcrispr","crispai"],
                    "texts":["[Cas9] [rule] cfd","[Cas9] crispr_m","[Cas9] deepcrispr","[Cas9] crispai"],
                    "expected":（同上，逐字相等）,"labelsEqualExpected":true}

# 连选两项（默认 cas9 的 on-target 只有 1 项，故先用同一 .group 的 System Preset 控件切到 custom，on-target 变 8 项）
presetValueBefore = "cas9"   presetValueAfter = "custom"   optionCountAfterPresetSwitch = 8
selectedValuesAfterTwoPicks = ["cropsr","rules"]
stateAfterTwoPicks = "cropsr,rules"          （state.side_on_target_models.target；全量见 out.json 的 stateAfterTwoPicksAll）
labelsAfterTwoPicks = ["[P] [Cas9] cropsr","[General] [rule] rules","[Cas12a] deepcas12a","[Cas12a] deepcpf1",
                       "[Cas13] [rule] rna_rules","[Cas13] tiger","[TnpB] [rule] omega","[TnpB] teep"]
primaryMarkedInLabels = true                 （第 1 项以 "[P] " 开头，第 2 项不以它开头）
hintAfterPicks = "Ctrl/Cmd-click to select several models; the first selection is primary. Primary: [Cas9] cropsr, [General] [rule] rules. Primary (Off-target): [Cas9] [rule] cfd."
hintHasPrimaryLine = true                    hintHasPrimaryLineBeforePicks = true

# Models 面板（await loadModels()）
modelsHeaderCells = ["Model","Status","Path","Description",""]     modelsHeaderHasDescription = true
modelsTableCount = 4   modelsHeaderCells（4 张表表头完全一致）   modelsApiRowCount = 7   modelsRowCount = 7
eachRowDescriptionMatchesRegistry = true      eachRowPathMatchesRegistry = true
teepPathCell = "https://www.tnpb.app"         teepUrl = "https://www.tnpb.app"   teepPathCellMatchesUrl = true

windowErrors = []
```

逐行比对（前端单元格文本 === `/api/models` 同 key 的字段）：

| # | key | Path 单元格 | Description 单元格 | path 等值 | description 等值 |
| --- | --- | --- | --- | --- | --- |
| 0 | `crispr_m` | `R:\songji\programfile\models\tcrispr_model.h5` | Cas9 off-target deep learning ranking model (~20 MB) | True | True |
| 1 | `deepcrispr` | `R:\songji\programfile\models\deepcrispr_offtar_pt_cnn_reg.tar.gz` | Cas9 off-target CNN model (~28 MB, TensorFlow 1.x) | True | True |
| 2 | `crispai` | `R:\songji\programfile\models\crispai.pt` | crispAI uncertainty-aware off-target aggregate model (~10 MB) | True | True |
| 3 | `deepcpf1` | `R:\songji\programfile\models\seq_deepcpf1_weights.h5` | DeepCpf1 sequence-only Cas12a/Cpf1 on-target model (~0.4 MB) | True | True |
| 4 | `deepcas12a` | `R:\songji\programfile\models\deepcas12a_fold1.pth` | DeepCas12a AsCas12a on-target CNN-Transformer fold 1 (~23 MB) | True | True |
| 5 | `tiger` | `R:\songji\programfile\models\tiger` | TIGER Cas13d on/off-target deep-learning model (~1.2 MB, downloaded via hf-mirror resolve) | True | True |
| 6 | `teep` | `https://www.tnpb.app` | ISDra2 TnpB editing efficiency predictor (online API, no download) | True | True |

编码：改动文件 + 新探针均为 UTF-8 无 BOM、`crlf=0`（逐文件字节核查：4 个改动文件与 2 个新文件的 `\r\n` 计数均为 0）。

## 未做项

- 全量测试套件（`run_tests.py`）与 ms01 复跑 —— 按 §4/§6 属 master 的核验范围，未做。
- 未测窄抽屉（380px）下 5 列 Models 表的横向溢出 —— 规格未要求，且属既有问题（见附带发现 1）。
- 未加任何中文描述/翻译文本 —— 按 D5、§4「不得在 webapp/ 里新增任何 per-model 文本」。

## 附带发现（不在本次范围，未修）

1. `webapp/static/app.js:1268-1286` — Models 表新增第 5 列后更宽，窄抽屉里会加剧横向滚动 — 等级 P3。上一轮 master 已判定 `table.models-table`（宽 626）在 380px 抽屉里溢出是**既有**问题；本轮只是让它更宽。建议后续给 `td` 加 `max-width` + `text-overflow: ellipsis`，或把 description 改成行内第二行（桌面端 `main.py:1174-1176` 就是每行下方一行灰字，`wraplength=420`）。
2. `webapp/static/app.js:770`（side 的 hint 节点）— 一个 TAM 侧只有一行 hint，On/Off 两个 primary 只能拼在同一行（`Primary: …` + `Primary (Off-target): …`）— 等级 P3。桌面端是「关闭态显示一行 primary、点击开弹层」，网页是原生多选列表框（D1 不重写），所以只能这样表达；若用户觉得啰嗦，可改成只在 On-target 那行显示 `Primary: …`。
3. `webapp/static/app.js:749-762`（`change` 处理器）— 选中集变化时只重绘该控件的 option 文本，不触发整侧重渲染（`renderPattern`）—— 这是刻意的（避免丢焦点/滚动），但副作用是「preset 切换会重建控件、初始渲染不带 `[P] `」（见待明确 1）。
4. `docs/WEBAPP.md:99-104` — 文档里写了「用户改动后 primary 项的选项文本加 `[P] ` 前缀」，与实现的「初始渲染不加前缀」一致；若 master 采纳待明确 1 的另一种取舍，这里要同步改。

## 待明确（需要 master 裁定，我按推荐执行了，未自行扩大范围）

1. **§6 的 `optionLabels == expectedLabels` 与 P0-2.2「已选中的 option 加 `[P] ` 前缀」在初始渲染上互相冲突。** `cas9` 预设的 on-target 列表只有 `cropsr` 且**默认已选中**（探针实测 `stateBeforePicks = {"on":{"target":"cropsr","left":"cropsr","right":"cropsr"},"off":{"target":"cfd","left":"cfd","right":"cfd"}}`），若初始渲染就加前缀，`optionLabels[0]` 会是 `"[P] [Cas9] cropsr"`，与 `model_labels["cropsr"] = "[Cas9] cropsr"` 必然不等，§6 第一条断言必失败。本轮的取舍（可回滚，1 行）：**初始渲染用纯显示名（等值断言成立），用户交互（`change`）后第一个选中项才加 `[P] `**；primary 在初始状态仍由 hint 的 `Primary: [Cas9] cropsr` 标出（`hintHasPrimaryLineBeforePicks=true`）。若 master 要求初始渲染即带前缀，请把 §6 的断言改为「去掉前缀后与 `model_labels` 相等」，我按新规格改 `webapp/static/app.js:763`。
2. **§6 要求「连选第一个 `select[multiple]` 的前两项」并断言 `state.side_on_target_models.target == "<key1>,<key2>"`，但默认 `cas9` 的 on-target 只有 1 项**（master 自己的 §2 探针输出也是 `optionLabels:["cropsr"]`，`webapp/schema.py` 侧 `side_model_options("cas9")["on_target"] == ["cropsr"]`）。探针的解法：先用同一 `.group` 里的 `System Preset` 控件把该侧切到 `custom`（on-target 8 项），再连选前两项 → `cropsr,rules`（`presetValueAfter="custom"` 已记录在输出里，master 可据此判读）。若 master 希望不动 preset，请指定改在哪个侧/角色（例如 `off-target` 的 `cfd,crispr_m`）做「连选两项」，我改探针。
3. Models 面板描述列表头用英文 `Description`（按 D2/D5）。若要中文表头，需要新增第二份文本或新映射，与 D5、§4 冲突，未做。

## 环境与偏差（重要，可能影响 master 复跑）

- **R: 盘的「当前目录」目前不可用**：`Set-Location R:\songji\programfile` 实测 45.6s 才返回；任何以 R: 为 cwd 启动的进程（含 `python -I -S -c "print(1)"`）会卡住 >30s（CPU、IO 均为 0，卡在进程启动阶段）。因此本轮全部命令都在 `C:\Users\ASUS` 作 cwd、用绝对路径 `R:\...` 访问仓库。`webapp/app.py` 的 `ROOT/WEBAPP/SHARED` 全部由 `__file__` 推导（`app.py:26-28`），与 cwd 无关，服务照常起来（`GET /api/schema` → 200，15758 bytes）。
- 权威解释器：本机 `python` 3.14.7（`C:\Users\ASUS\AppData\Local\Programs\Python\Python314\python.exe`）；`.venv` / `.venv310` 未用。
- 探针 runner `assets/probe_browser_cdp.js` **未改动**：SHA256 `D04ABDFB7EFAC3E1C29707E696D99F49DA5ECE5F5F51BE3AB1BB9E82A4E4A4A6`，与 `docs/handoff/webapp-file-picker/assets/probe_browser_cdp.js` 逐字节相同。
- 探针进程已全部关闭：`http://127.0.0.1:8361/api/schema` 与 `http://127.0.0.1:9343/json/version` 均连接失败（DOWN），端口留给 master。
- 快照 `backup/20260917_webapp_model_labels/` 含 6 个文件（4 个改名文件 + `webapp/index.html` + `webapp/static/styles.css`），保持相对路径，未移动/删除任何旧文件。
