# 核验报告：webapp-model-labels

- round: 1
- verdict: **pass**（P0-1..P0-4 逐条成立，P1-1 成立；3 条「待明确」由 master 裁定**采纳 servant 方案**，无返工项）
- updated: 2026-09-17 10:30
- 依据：servant `report.md`（14,197 B）+ 基线快照 `backup/20260917_webapp_model_labels/`（6 文件，mtime 均落在 2026-09-16 21:40–22:49，确为改动前）+ master 自写探针 `assets/probe_master_labels.py`、`assets/probe_master_verify.js`

## 逐条核验

| 任务项 | 结论 | 证据（master 独立复现） |
| --- | --- | --- |
| P0-1 `/api/schema` 下发 `model_labels`（唯一来源 `model_display_name`） | 通过 | master 自写 `probe_master_labels.py`（不引用 servant 脚本）：`label_count=14`；`keys_equal_union_over_presets=True`（== `PRESET_KEYS` 全体 on/off 选项并集）；`values_equal_model_display_name=True`（逐项 == `workbench_form.model_display_name`）；`labels_missing_protein_prefix=[]`；`preset_options_missing_a_label=[]` |
| P0-2 侧模型选择器显示桌面文本 + 标 primary | 通过 | master 自写 DOM 探针（headless Edge + CDP，服务 8362）：`selectCount=2`、`initialMultiple=[true,true]`、`initialSize=[2,4]`；`initialValues=[["cropsr"],["cfd","crispr_m","deepcrispr","crispai"]]`；`initialTexts=[["[Cas9] cropsr"],["[Cas9] [rule] cfd","[Cas9] crispr_m","[Cas9] deepcrispr","[Cas9] crispai"]]`；`initialPlainLabels=true`；连选两项 → `stateAfterTwoPicks="cropsr,rules"`、`primaryPrefixOnFirst=true`、`primaryPrefixOnSecond=false`、`unselectedHaveNoPrefix=true`、`labelsAfterPicksMatchSchema=true`；`hintInitial` 与 `hintAfterPicks` 都含 `Primary: …` 且含 primary 的显示名；`windowErrors=[]` |
| P0-3 Models 面板补 Description 列 + URL 回退 | 通过 | 同一探针：4 张表表头均为 `["Model","Status","Path","Description",""]`；`domRowCount=7=apiRowCount`；`eachRowPathMatches=true`、`eachRowDescriptionMatches=true`、`rowDescriptionsNonEmpty=true`；`teepPathCell="https://www.tnpb.app"` == API 的 `path||url`。另有 `probe_master_labels.py`：7 个模型 `description_mismatch=[]`（== `model_registry.MODELS[*]["description"]`）、`teep_path_url='' 'https://www.tnpb.app'` |
| P0-4 文档同步 | 通过 | `docs/WEBAPP.md` +13/-2（diff 逐行读）：模型多选/显示名/primary 说明在 `:99-104` 段、Models 面板 `description`+`url` 回退在 `:122-125` 段、API 表 `/api/schema`（`:189`）与 `/api/models`（`:195`）两行已更新；未越界改 `README.md` |
| P1-1 聚焦用例 | 通过 | master 自己读 diff：`test_model_labels_match_the_shared_display_names`（断言 key 集合 == PRESET_KEYS 并集、逐项等值、含 `[General] [rule] rules`）、`test_model_descriptions_come_from_the_registry`（逐 key 等值 + teep 前提）；master 自己跑测试见下 |

## master 独立验证

- **基线 diff**（`git --no-index -U`，对 `backup/20260917_webapp_model_labels/`）：`webapp/schema.py` +9/-3、`webapp/static/app.js` +62/-9、`tests/test_webapp.py` +35/-0、`docs/WEBAPP.md` +13/-2；`webapp/index.html`、`webapp/static/styles.css` 与快照 **SHA256 相同**（未改动）；无其它文件被触碰。
- **自写 python 探针**：`assets/probe_master_labels.py`（输出见上表 P0-1/P0-3）。
- **自写 DOM 探针**：`assets/probe_master_verify.js`（master 自己的断言，未复用 servant 探针），服务 `python R:\songji\programfile\webapp\app.py --port 8362`，Edge `:9344`；原文摘要见上表，`probeError=null`、`cdpExceptionsDuringLoad=0`、`cdpExceptionsTotal=0`。
- **测试**（本机权威解释器 `python` 3.14.7）：
  - master 自跑 `python -m unittest tests.test_webapp -v` → `Ran 62 tests ... OK`（58.9s；与 servant 报的 62 一致，改动前基线 60）。
  - master 自跑 `python -m unittest tests.test_webapp tests.test_workbench_form tests.test_designer_workbench tests.test_pattern_runner` → `Ran 139 tests ... OK`（117.1s）。
- **单一来源核查**：`rg` 全仓 `[Cas9]|[Cas12a]|[Cas13]|[TnpB]|[General]` 在 `webapp/`、`tools/`、`basic/`、`main.py`、`designer_workbench.py`、`unified_gui.py` 下**零命中**；registry 的描述句在 `webapp/` 下无副本（只出现在交接文档与探针输出里）。
- **编码**：4 个改动文件 + 新探针 + 交接文件全部 `BOM=False`、`CRLF=0`。
- **归属证据**：改动文件 mtime 10:07–10:12，快照文件 mtime 2026-09-16 21:40–22:49（均早于改动），diff 只含本任务内容——本次交付即全部变更来源。

## 待明确裁定（round 1，master 结论）

1. **初始渲染是否带 `[P] ` 前缀** → **采纳 servant 方案**：初始渲染用纯显示名，首次用户交互起给第一个选中项加 `[P] `。理由：任务书 §6 第 1 条（`optionLabels == model_labels`）与 §3 P0-2.2 互相矛盾，属 master 规格问题；初始状态下 primary 已由 hint 的 `Primary: …` 表达（与桌面 picker 关闭态同义），交互后的 `[P] ` 与桌面弹层同义；纯显示名还让「DOM 文本 == `/api/schema`」这条单一来源断言保持最强。master 实测 `hintInitial="Ctrl/Cmd-click … the first selection is primary. Primary: [Cas9] cropsr. Primary (Off-target): [Cas9] [rule] cfd."`。可选后续（不阻塞）：若要初始即标前缀，改 `webapp/static/app.js` 一处 `paintModelOptions(select, false)` → `true`，并把 §6 断言改成「去前缀后与 `model_labels` 相等」。
2. **探针先把同组 System Preset 切到 `custom` 再连选两项** → 采纳。cas9 on-target 默认只有 `cropsr` 一项（master 自己的 §2 探针同样只看到 1 项），原规格「连选前两项」不可达；servant 的适配可复现，master 独立探针得到同样结果（`cropsr,rules`）。
3. **`Description` 表头用英文** → 采纳（D2/D5；中文表头会引入第二份文本）。

## 归属判定（既有失败 vs 本次引入）

- 无失败用例（62 + 139 tests OK）。
- 「网页端可把模型清空成 `''`，而桌面 `_toggle` 会阻止清空」= **既有行为，非本次引入**：基线 `app.js` 的 change 处理器同样 `values.join(',')`（空数组 → `''`），本轮未改；master 探针实测 `offTargetAfterDeselectAll=""`。等级 **P3**，不在本任务范围。
- 初始渲染不带 `[P] ` = 规格冲突的裁定结果（见上），非缺陷。

## 已知偏差（已接受，非返工项）

- `model_labels` 不含 `void` 占位值（仅当某 preset 候选列表为空时才出现，当前全部 preset 非空 → 不可达）；若将来可达，前端回落显示原始 key `void`。**P3**。

## 新发现（记录，不返工）

- Models 表新增第 5 列后更宽，窄抽屉（380px）里横向溢出加剧（**P3**；既有溢出问题被放大，桌面端是行内第二行显示 description）。
- 侧模型 hint 同时表达 On/Off 两个 primary（**P3**，原生多选列表框的表达限制）。

## 下一步

- 本任务 **done**。可选后续（不阻塞，未开工）：①窄抽屉里把 description 改行内第二行或加 `text-overflow: ellipsis`；②若要初始即显示 `[P] `，按裁定 1 的后备注另开 1 行改动任务。
- 证据留存：`task.md`（round 1 规格，未改）、`report.md`（servant）、本 `review.md`；master 探针 `assets/probe_master_labels.py`、`assets/probe_master_verify.js`。