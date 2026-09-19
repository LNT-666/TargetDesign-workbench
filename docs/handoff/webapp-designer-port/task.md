# 任务：重做 webapp，把 main（统一工作台）与 Pattern Designer 移植到网页版

- task-slug: `webapp-designer-port`
- round: 1
- master: 本会话（Codex master，工作目录 `R:\songji\programfile`）
- servant: 待指定（另一个 Codex 会话）
- repo: `R:\songji\programfile`

## 0. 目标与边界

把现有 `webapp/`（只做 library 出库的旧网页版）**整体重做**为一个本地网页工作台，
功能对齐桌面端两个界面：

1. `main.py`（`main.py:1702` 实际启动 `unified_gui.main()`）统一工作台的
   **Data prep / Models / Results-Output** 工作流；
2. `designer_workbench.py` 的 **Pattern Designer**：三种 pattern、左右 TAM、
   Run Settings、`Find Targets` / `Score & Off-target`、候选结果表、按选中行导出。

旧网页版（`webapp/app.py` + `webapp/job_store.py` + `webapp/index.html` 的
library-only 实现）作废，不再保留其功能。

**明确不做（本轮范围外）**：

- 不移植 Library 出库流程（`shared/design/library_pipeline.py` 已在 `README.md:288`
  声明废弃；`main.py:1576` 的 Library 页签也已被注释掉）。`unified_gui.py` 的
  “一键出库”不移植。
- 不移植三个独立 motif GUI 启动器：`basic/gui.py`、`Target_xbp_Target/gui.py`、
  `Target_xbp_Y_zbp_Target/gui.py` **已经不存在**（`main.py:31-35` 的 `GUI_SCRIPTS`
  是死代码，属“附带发现”，本轮不改）。
- 不引入任何第三方 web 框架、模板引擎或前端 CDN；只用 Python 标准库 + 原生 JS/CSS，
  必须离线可用，`requirements-windows.txt` 不变。
- 不改任何 CLI 脚本、共享管线、评分/输出列契约的行为。

## 1. 规则/契约（唯一权威版本）

### 1.1 复用原则（仓库既有约定，硬要求）

`docs/WEBAPP.md:3-5`：

```text
网页版是纯本机工具：默认只监听 127.0.0.1，不提供任何在线服务。
它复用同一个 shared/design/library_pipeline.py，因此网页结果与桌面端和
命令行完全一致。
```

因此：**网页端必须调用同一套 shared 模块**。禁止在 `webapp/` 里重写
「表单值 → PatternSpec / RunnerConfig」的映射逻辑；该逻辑必须与桌面端共用同一份代码
（见 P0-1 / P0-2）。

### 1.2 安全边界（沿用 `docs/WEBAPP.md` 的“安全边界”一节，不得放宽）

- 服务只绑定 `127.0.0.1`（默认 `--host 127.0.0.1`，`--port 8000`）。
- 下载只走白名单文件名。
- job id 只允许 `[a-z0-9-]`。
- 子进程通过参数列表调用，不经过 shell。

### 1.3 入口与启动命令保持不变

`README.md:97` 与 `README.md:30` 已把 `python webapp\app.py` 记为本地 Web UI 入口，
重做后必须仍可用同一条命令启动：

```powershell
python webapp\app.py            # 默认 http://127.0.0.1:8000
python webapp\app.py --port 8765
```

### 1.4 Pattern Designer 表单契约（照抄自 `designer_workbench.py:737-880`）

三种模式由 `PatternKind`（`shared/design/pattern_spec.py:8-12`）决定：`single_motif_flank`、
`motif_gap_motif`、`y_centered_motifs`。模式显示名必须与
`designer_workbench.py:51-55` 的 `MODE_LABELS` 完全一致。

公共输入（`designer_workbench.py:400-448`，键名即表单字段键）：

| 键 | 标签 | 控件 |
| --- | --- | --- |
| `search_fasta` | Search FASTA | 文件路径（sequence 模式显示） |
| `bed_regions` | BED Regions | 文件路径（bed 模式显示） |
| `genome_fasta` | Genome FASTA | 文件路径（允许 `.fna.gz`，见 1.7） |
| `mask_fasta` | Mask FASTA | 文件路径（可空） |
| `output_dir` | Output Directory | 目录 |
| `blastdb` | BLAST DB Prefix | 路径（可空） |
| `result_label` | Result Label | 文本（可空，空则自动命名） |

输入模式单选（`designer_workbench.py:428-446`）：Sequence (FASTA) / BED Regions，
对应 `input_mode = "sequence" | "bed"`；bed 模式隐藏 `search_fasta`、显示 `bed_regions`。

单靶 `single_motif_flank`（组标题 `Target TAM`，`designer_workbench.py:754-775`）：

| 键 | 标签 | 控件 / 默认 |
| --- | --- | --- |
| （侧）`target` | System Preset | 下拉 `PRESET_KEYS` + `Apply` 按钮 |
| `motif` | PAM/TAM Motif | 文本 |
| `flank` | Target Length | 文本 |
| `side` | Target Position | 下拉 `downstream` / `upstream`，默认 `upstream` |
| （侧）`target` | Use for Run | 单选，置 `active_side = "target"` |
| 侧模型行 | On-target Model / Off-target Model | 多选（见 1.6） |

双靶 `motif_gap_motif`（`designer_workbench.py:776-847`）：

- Left TAM：`left_motif`（PAM/TAM）、`left_flank`（Target Length）、
  `left_side`（Target Position，默认 `upstream`）、
  `left_require_pam`（Require PAM，默认 `True`）、Use for Run（`left`）、侧模型行。
- Middle：`min_gap`（Minimum Distance）、`max_gap`（Maximum Distance）。
- Right TAM：`right_motif`、`right_flank`、`right_side`（默认 `upstream`）、
  `right_require_pam`（默认 `True`）、Use for Run（`right`）、侧模型行。

Y 中置 `y_centered_motifs`（`designer_workbench.py:782-846`）：与双靶相同，但 Middle 改为
`y_sequence`（Middle Motif，必填）且无 `min_gap`/`max_gap`；左右各增加
`left_min_distance`/`left_max_distance`、`right_min_distance`/`right_max_distance`。

### 1.5 Run Settings 契约（照抄自 `designer_workbench.py:571-668`）

| 键 | 标签 | 取值 / 默认 |
| --- | --- | --- |
| `engine` | Engine | `ENGINE_CHOICES`（`shared/design/library_preflight.py:22`），默认 `auto` |
| `max_mismatch` | Max Mismatch | `0..4`，默认 `4` |
| `max_bulge` | Max Bulge | `""` / `0` / `1`，默认 `""` |
| `pam_mode` | PAM Mode | `strict_ngg` / `guidescan2_nrg` / `custom`，默认 `strict_ngg` |
| `seed_len` | Seed Length | 整数，默认 `12` |
| `index_path` | Index Prefix | 路径 |
| `gc_min` | GC Min | 默认 `40` |
| `gc_max` | GC Max | 默认 `70` |
| `genome_build` | Genome Build | 文本 |
| `filter_hard` | Hard Filter | 勾选，默认关 |
| `memory_mode` | Memory Limit | `auto` / `custom` / `unlimited`，默认 `auto` |
| `max_memory_mb` | Custom MiB | 整数，默认 `32768`；`<512` 报错（`designer_workbench.py:1629-1644`） |
| `search_timeout_s` | Search timeout (s) | 浮点，可空；`<=0` 报错（`designer_workbench.py:1719-1730`） |
| `pair_rank_<field>` | PairRank policy | `PAIR_RANK_POLICY_FIELDS` 10 个字段（`designer_workbench.py:57-68`） |

`Find Targets` = 流水线 step 0..1（仅提取），`Score & Off-target` = step 1..end
（在已有提取结果上继续），见 `designer_workbench.py:2555-2576`；未先提取就打分必须报
`Extracted targets not found. Run Find Targets first.`（`designer_workbench.py:2463-2473`）。

### 1.6 预设、切侧与模型下拉语义

- 每侧 System Preset 的 `Apply` 等价于 `designer_workbench.py:1455-1495`：
  用 preset 的 `pam` 填该侧 motif、`spacer_len` 填该侧 Target Length、
  `pam_side` 经 `_pam_side_to_side`（`designer_workbench.py:1771-1777`）转成该侧
  Target Position，并设置 `nuclease`、`pam_mode`、`tnpb_subtype`、该侧 `require_pam`，
  同时把 `active_side` 设为该侧。
- `Use for Run` 切侧时按 `designer_workbench.py:1510-1530` 同步
  `nuclease` / `pam_mode` / `tnpb_subtype` / `require_pam`。
- 侧模型多选的可选值与默认值按 `designer_workbench.py:1420-1453`：可选值来自
  `scoring.model_choices_for_preset(nuclease, role)`（`shared/scoring/scoring.py:105`）；
  on-target 默认 `cas9→cropsr`、`cas12a→rules`、`cas13→rna_rules`、`tnpb→omega`、
  `custom→rules`；off-target 默认候选列表第一项；候选为空时用占位 `void`。
- 多选值在表单里是逗号分隔字符串，拆分规则用 `designer_workbench.py:65-77` 的
  `_split_model_selection`（分号也当分隔符、去重保序）；非法/空值按上一条回落。

### 1.7 Genome FASTA 的 gz 规则（上一轮已交付的契约，不得回退）

`designer_workbench.py:1989-2004`（`_prepare_genome_fasta`）允许 `Genome FASTA` 填
`.fna.gz`，通过 `data.annotation_utils.ensure_plain_fasta(raw, log_func=...,
fallback_dir=output_dir)` 得到纯文本路径；失败抛
`ValueError("Genome FASTA could not be prepared: %s")`。网页端必须走同一函数
（`tests/test_fasta_gz.py` 覆盖该契约）。

### 1.8 进度与确认协议

- 子进程进度行（`designer_workbench.py:2308-2334`）：
  `PROGRESS_TARGET: i/n` → 只更新“正在处理第 i/n 个 target”文字；
  `PROGRESS: <label> <pct>` → 百分比进度：解析最后一个整数 token 为百分比，其余为文字。
  下载流程同为 `PROGRESS:<label> <pct>`（`main.py:253-262`）。
- `CONFIRM_REQUIRED: kind|reason`（`shared/design/pattern_runner.py:91-105`）：
  网页端**默认自动应答同意**，并写入作业日志，格式 `[auto-confirm] <kind>|<reason>`；
  作业参数 `confirm_policy` 取值 `yes`（默认）/ `no`。

### 1.9 候选结果与导出契约

- 候选列取自 `PatternSpec.candidate_columns()`（`shared/design/pattern_spec.py:131-`），
  表格隐藏 `query_seq` 与 `gap_seq`（`designer_workbench.py:2593-2596`）。
- 候选数据必须来自 `PatternRunner.read_extract_candidates()`（`designer_workbench.py:2582`），
  不得自行解析提取产物。
- 导出用 `shared/output/candidate_export.py:10-19` 的 `SUPPORTED_FORMATS`
  （`csv` / `tsv` / `fasta` / `bed` / `xlsx` / `unique_guides` / `library`）与
  `export_selected(rows, path, fmt)`；文件名规则照 `designer_workbench.py:2659-2684`。

## 2. 现状证据（master 已核实，可直接引用）

### 2.1 桌面端构成

- `main.py:1701-1703` — `if __name__ == "__main__": import unified_gui; unified_gui.main()`。
- `unified_gui.py:91-147` — 三个页签：`Results / Output`、`Data prep / Models`、
  `Target design`；`unified_gui.py:182-188` 的 `_create_legacy_panel` 直接嵌入
  `main.MainApp(parent, as_panel=True)`。
- `main.py:1411-1640` — `create_widgets()` 建 `Data preparation` / `Search scope` /
  `Mask gene` / `Models` 四个页签；`main.py:1574-1577` 的 Library 页签已被注释掉。
- `designer_workbench.py:273-340` — `PatternDesignerWorkbench.__init__`：
  `_create_header/body/run_bar/progress/log` + `_rebuild_pattern_frame`。
- `designer_workbench.py:469-546` — 中列含 `result_tree`（候选表）与
  `export_format_var`/`export_button`；`designer_workbench.py:2578-2698` 负责填充与导出。

### 2.2 现网页版（本次要作废的对象）

- `webapp/app.py:49` 起 `PAGE = """..."""`，`webapp/app.py:398-401` 再读
  `webapp/index.html` 做占位替换；`webapp/app.py:37-38` 绑定 `127.0.0.1:8000`。
- `webapp/job_store.py` 只服务 `shared/design/library_pipeline.py` 及三个 motif CLI
  （见 `tests/test_webapp.py:31-118` 的 `_build_command` / `_build_commands_for_job` 断言）。
- `tests/test_webapp.py` 绑定旧实现（`import job_store`、`app.PAGE` 内容断言）。
- `webapp/jobs/87499fe93868/` 是旧实现的遗留作业目录（**不要删除**）。
- `docs/WEBAPP.md` 整篇描述旧的 library 网页版，需要按新实现改写。

### 2.3 可直接复用的后端接口（均已存在，无需新建）

| 能力 | 入口 |
| --- | --- |
| 表单值 → PatternSpec | `designer_workbench.py:1888-1938` `_current_spec` |
| 表单值 → RunnerConfig | `designer_workbench.py:2006-2134` `_current_config` |
| 就绪检查 | `designer_workbench.py:2247-2306` `_readiness_errors` |
| 运行流水线 | `shared/design/pattern_runner.py:844` `PatternRunner.run_pipeline(on_line=, start=, end=, on_prompt=)` |
| 停止流水线 | `shared/design/pattern_runner.py:825` `PatternRunner.stop()` |
| 读候选 | `shared/design/pattern_runner.py:922` `read_extract_candidates()` |
| 提取产物路径 | `shared/design/pattern_runner.py:228` `extract_output_path()` |
| 导出 | `shared/output/candidate_export.py:21` `export_selected` |
| 引擎清单 | `shared/design/library_preflight.py:22` `ENGINE_CHOICES` |
| 预设清单 | `shared/design/system_presets.py:150-167` `preset_keys` / `preset_choices` / `get_preset` |
| 模型分组与状态 | `shared/scoring/model_registry.py:232-256` `get_all_statuses` / `models_by_protein`；`:477` `download_model`；`:552` `delete_model` |
| 深度模型可加载性 | `shared/scoring/deep_models.py:384-407, 637-651`（`crispr_m_status` / `model_statuses` / `deepcpf1_status` / `deepcas12a_status`） |
| gz → 纯文本 FASTA | `shared/data/annotation_utils.py` `ensure_plain_fasta` / `plain_fasta_is_current`（`main.py:14-17` 导入） |
| 注释 gz 读取 | `shared/data/annotation_utils.py` `is_gzip_file` / `open_annotation_text` |
| 区域序列提取 | `shared/data/local_extract.py:25` `get_region_sequence(genome, ann, id, region_type, region_num, id_type=...)` |
| BLAST 库构建 | `shared/search/blast_utils.py:176` `ensure_blastdb(fasta, output_dir=None, db_name=None, log=None, trust_existing=False)` |
| 基因组索引构建 | `tools/build_genome_index.py` → `shared/search/genome_index.py:867` `main()`（CLI：`genome --output-dir --prefix --k ...`） |
| 基因组下载 | `shared/data/download_data.py:106-109`（`--species` / `--output`；进度行 `PROGRESS:<label> <pct>`；产物 `download_info.json` 含 `genome_fasta` / `gtf`） |
| UTR 补全 | `shared/data/add_utrs_to_gff.py`（`python add_utrs_to_gff.py input.gff3 > out.gff3`，stdout 必须 UTF-8，见 `main.py:139-148`） |

### 2.4 master 实测的环境事实（本机 Windows）

- `python --version` → `Python 3.14.7`；`python -c "import numpy, Bio"` →
  `numpy 2.5.2` / `biopython 1.88`。**网页服务用系统 `python` 直接跑**。
- `R:\songji\programfile\.venv` 是 Linux venv（`bin/` + `lib64/`，`pyvenv.cfg` 指向
  `/usr/bin/python3.12`），Windows 下不可用；`.venv310` 指向已不存在的
  `C:\Users\LNT\...\Python310`，已失效。因此 `README.md:97` 里的
  `.\.venv\Scripts\python.exe` 在本机不成立（属“附带发现”，本轮不改 README 的其它内容）。
- `python webapp\app.py`（旧实现）→ `GET http://127.0.0.1:8000/` 返回 HTTP 200，
  页面标题 `CRISPR Motif Designer`；从启动到可访问约 20 秒（`R:` 网络盘 import 慢）。
  新实现必须仍能这样启动；前端首屏不得依赖外网。
- 仓库根目录**没有 `.git`**：基线只能用 `backup/<date>_<slug>/` 文件快照。

## 3. 必做改动

### P0-1 抽取共享表单层 `shared/design/workbench_form.py`（新增，禁止 import tkinter）

- 位置：新建 `shared/design/workbench_form.py`；来源为 `designer_workbench.py` 下列片段，
  **逐行搬迁、不得改语义**：
  - `MODE_LABELS`（`:51-55`）、`PAIR_RANK_POLICY_FIELDS`（`:57-68`）、
    `_split_model_selection`（`:65-77` → 公开名 `split_model_selection`）、
    `_model_display_name`（`:79-87` → `model_display_name`）、`PRESET_KEYS`（`:47`）。
  - `_to_side`（`:1759-1762`）、`_side_to_pam_side`（`:1763-1770`）、
    `_pam_side_to_side`（`:1771-1777`）、`_active_side_keys`（`:1501-1508`）。
  - `_auto_memory_limit`（`:1621-1627`）、`_resolved_memory_limit`（`:1629-1644`）、
    `_search_timeout_s`（`:1719-1730`）、`_pair_rank_policy_values`（`:1975-1987`）、
    `_resolve_side_models`（`:1732-1757`）、`_prepare_genome_fasta`（`:1989-2004`）。
  - `_current_spec`（`:1888-1938`）、`_default_run_label`（`:1940-1973`）、
    `_current_config`（`:2006-2134`）、`_readiness_errors`（`:2247-2306`）。
  - 预设应用与模型下拉的纯逻辑：`_apply_side_preset`（`:1455-1495`）中“算出要写的字段值”
    的部分、`_refresh_side_model_options`（`:1420-1453`）中“算出候选值与默认值”的部分、
    `_sync_active_side_rules`（`:1510-1530`）的字段同步规则。
- 期望 API（名字可微调，但语义必须一致，且必须被 GUI 与 webapp 同时使用）：

```python
@dataclass
class WorkbenchFormState:
    values: Dict[str, str]                      # 上述所有字段键 → 字符串值
    mode: str = "single_motif_flank"            # PatternKind 的值
    input_mode: str = "sequence"                # "sequence" | "bed"
    nuclease: str = "cas9"
    tnpb_subtype: str = "unknown"
    require_pam: bool = True
    active_side: str = "left"                   # "target" | "left" | "right"
    side_presets: Dict[str, str] = ...          # 每侧 preset key
    side_on_target_models: Dict[str, str] = ...  # 逗号分隔多选值
    side_off_target_models: Dict[str, str] = ...
    log: Callable[[str], None] = <no-op>

def build_pattern_spec(state) -> PatternSpec
def build_runner_config(state, spec=None) -> RunnerConfig
def readiness_errors(state) -> List[str]
def default_run_label(state, spec=None) -> str
def side_preset_updates(preset_key) -> Dict[str, str]   # Apply 时要写入的字段值
def side_model_options(preset_key) -> Dict[str, object] # on_target / off_target / on_target_default
def active_side_updates(state) -> Dict[str, object]     # Use for Run 切侧时的同步值
def prepare_genome_fasta(state) -> str
```

- 期望行为：对同一份 `WorkbenchFormState`，`build_pattern_spec`/`build_runner_config`
  的输出必须与改动前 `PatternDesignerWorkbench._current_spec`/`_current_config`
  逐字段相同（含 `run_label` 的自动命名、`max_memory_mb` 的 auto 解析、
  `pair_rank_policy` 缺失时为 `None`）。
- 证据要求：`python -m unittest tests.test_designer_workbench tests.test_pattern_runner -v`
  原文输出；以及新增 `tests/test_workbench_form.py` 的输出。

### P0-2 `designer_workbench.py` 改为薄包装（桌面行为不变）

- 位置：`designer_workbench.py:1617-2134`、`:1420-1530`、`:2247-2306`、
  `:1940-1973`、`:1989-2004`。
- 期望行为：上述方法保留原名与签名，内部改为组装 `WorkbenchFormState`
  （`self.vars` 的字符串值、`self.mode_var`、`self.input_mode_var`、`self.nuclease_var`、
  `self.tnpb_subtype_var`、`self.require_pam_var`、`self.active_side_var`、
  `self.side_*_vars`、`log=self._log_line`）并调用 `workbench_form` 的函数；
  Tk 控件、`root.after`、进度条逻辑**保持原样**。
- 约束：`designer_workbench.py` 里不得再保留第二份 spec/config 构造逻辑。
- 证据要求：同上单测原文；`python -m py_compile designer_workbench.py shared\design\workbench_form.py`。

### P0-3 重做 webapp 后端

目标文件结构（`webapp/` 内）：

```text
webapp/app.py                 # 重写：HTTP 路由 + 静态文件 + JSON API
webapp/jobs.py               # 新增：作业存储与后台执行
webapp/schema.py             # 新增：前端用的选项/字段 schema（值必须来自 shared）
webapp/services/__init__.py
webapp/services/designer.py  # 新增：designer 服务
webapp/services/dataprep.py  # 新增：数据准备服务
webapp/services/models.py    # 新增：模型管理服务
webapp/index.html            # 重写：单页外壳（4 个页签）
webapp/static/app.js         # 新增：原生 JS
webapp/static/styles.css     # 新增：样式
webapp/job_store.py          # 作废：内容替换为一句说明（不要删文件）
```

- `webapp/services/designer.py` 必须：用 `workbench_form` 构造 spec/config；
  运行 `PatternRunner.run_pipeline(on_line=..., start=..., end=..., on_prompt=...)`
  （`on_prompt` 按 1.8 自动应答并把请求写日志）；候选走 `read_extract_candidates()`；
  导出走 `export_selected`。
- 期望 API（JSON，全部同源，仅 `127.0.0.1`）：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/` | 返回 `index.html` |
| `GET` | `/static/<file>` | 白名单静态文件（`app.js` / `styles.css`），拒绝路径穿越 |
| `GET` | `/api/schema` | 模式名、预设、引擎、nuclease/tnpb 选项、模型分组、各字段默认值、`SUPPORTED_FORMATS` |
| `POST` | `/api/designer/preview` | 入参为表单值；返回 `{describe, errors, warnings, memory_resolved}`（`describe` 来自 `PatternSpec.describe()`） |
| `POST` | `/api/designer/preset` | `{side, preset}` → 该侧字段更新值（`side_preset_updates`）+ 模型候选 |
| `POST` | `/api/designer/jobs` | `{stage: "find"|"score", values, input_mode, mode, ...}` → `{job_id}` |
| `GET` | `/api/jobs` | 作业列表（按创建时间倒序） |
| `GET` | `/api/jobs/<id>` | `{status, progress, message, returncode, log_tail}` |
| `GET` | `/api/jobs/<id>/log?offset=<n>` | 增量日志 `{offset, text}` |
| `POST` | `/api/jobs/<id>/cancel` | 停止（`PatternRunner.stop()` / 终止子进程） |
| `GET` | `/api/jobs/<id>/candidates` | `{columns, rows, total}`（隐藏 `query_seq`/`gap_seq`） |
| `POST` | `/api/jobs/<id>/export` | `{format, rows: [i,...]\|"all", filename?}` → `{written, download_url}` |
| `GET` | `/api/jobs/<id>/download?file=<name>` | 白名单下载（导入结果、导出文件） |
| `POST` | `/api/dataprep/download` | `{species, output_dir}` → 作业；成功后回填 `download_info.json` 的 genome/gtf |
| `POST` | `/api/dataprep/prepare` | `{genome, annotation, output_dir, target_id, ...}` → 作业（准备基因组/注释 + 提取 Target + 提取 Mask + 可选建 BLAST 库） |
| `POST` | `/api/dataprep/extract-target` / `extract-mask` | 单独提取（区域选择参数同 1.4） |
| `POST` | `/api/dataprep/build-blastdb` | 调 `blast_utils.ensure_blastdb` |
| `POST` | `/api/dataprep/build-index` | 调 `tools/build_genome_index.py`（子进程） |
| `GET` | `/api/models` | 分组状态（含 `deep_models` 的可加载性修正，规则见 `main.py:1203-1260`） |
| `POST` | `/api/models/<key>/download` / `delete` | 建作业执行 `model_registry.download_model` / `delete_model` |
| `GET` | `/api/outputs?dir=<path>` | 输出目录文件列表（限白名单扩展名） |

- `webapp/jobs.py` 期望行为：
  - 作业目录 `<repo>/webapp/jobs/<job_id>/`，含 `params.json`、`status.json`、
    `job.log`、`out/`；`job_id` 12 位 `[a-z0-9]`。
  - `status.json` 字段：`job_id, kind, title, status, progress, message, returncode,
    created, started, finished`；`status ∈ queued|running|succeeded|failed|cancelled|interrupted`。
  - 同一时刻最多 1 个重作业在跑（`max_concurrent = 1`），其余排队；
    进程内重启时把遗留 `running`/`queued` 标为 `interrupted`（不假装还在跑）。
  - 进度按 1.8 解析进度行写入 `progress`/`message`；日志同时写 `job.log`。
- 期望行为（错误处理）：参数非法（缺 `output_dir`、文件不存在、spec 校验失败、
  `max_memory_mb < 512`、`search_timeout_s <= 0`）时不得启动子进程，返回 HTTP 400 +
  `{"error": "<readiness_errors 里的原始文案>"}`。
- 证据要求：`python -m py_compile` 全部新文件；启动服务后按第 6 节命令跑通并贴输出。

### P0-4 重做前端 `webapp/index.html` + `webapp/static/*`

- 页签顺序与桌面端工作流一致：`Data prep` → `Models` → `Designer` → `Results / Output`。
- `Designer` 页签必须包含 1.4/1.5/1.6 的全部字段与控制项（含每侧 Apply / Use for Run /
  侧模型多选），`Find Targets` 与 `Score & Off-target` 两个按钮，就绪状态
  （`Ready` / `Missing: <第一个错误>`，红色）、进度条与 `Analyzing target i/n` 文案、
  可折叠 Run Log、候选表格（隐藏 `query_seq`/`gap_seq`）、行选择 + 导出格式下拉 + 导出按钮。
- 导入 `Genome FASTA`/`Search FASTA`/`BED Regions`/`Mask FASTA` 用文本输入框（浏览器
  无法给出服务端路径）；`output_dir` 同样文本输入。不需要文件上传。
- 期望行为：`/api/schema` 失败或未返回时页面仍能显示并给出错误提示；所有请求同源
  （无 CDN、无外网）。
- 证据要求：`GET /` 返回 200 且含四个页签标题；`GET /api/schema` 返回的引擎列表等于
  `ENGINE_CHOICES`。

### P0-5 测试

- 新增 `tests/test_workbench_form.py`：三种 mode 的 `build_pattern_spec` /
  `build_runner_config` 关键字段；`readiness_errors` 的缺项文案；`max_memory_mb`、
  `search_timeout_s`、`pair_rank_*` 的报错分支；`default_run_label` 的自动命名；
  `side_preset_updates("cas12a")` 的字段值（`pam=TTTN` 等，参照
  `tests/test_designer_workbench.py:40-48` 的既有断言）。
- 重写 `tests/test_webapp.py`：覆盖 `webapp/jobs.py` 的创建/状态/列表顺序/日志增量/
  中断恢复，`webapp/services/designer.py` 的命令与预检拒绝路径（用 mock，
  不启动真实子进程、不需要浏览器），以及 `webapp/app.py` 的路由分发
  （沿用旧测试的 `object.__new__(Handler)` 手法）。
- 期望行为：`python -m unittest tests.test_webapp tests.test_workbench_form -v` 全绿，
  且 `tests/test_designer_workbench.py` 未修改仍全绿。

### P0-6 文档

- `docs/WEBAPP.md` 重写为新版网页版说明（启动、四个页签、API 表、作业目录、
  安全边界、与桌面端一致性说明）。
- `README.md:30` 的 `webapp/app.py` 行说明改为“本地 Web UI：Data prep / Models /
  Designer / Results”，`README.md:97` 的启动命令保持不变。

### P1（本轮应做，若时间紧张可留到下一轮，但必须在 `report.md` 的“未做项”列出）

- `POST /api/jobs/<id>/confirm` + 前端“待确认”提示（把 1.8 的自动应答变成可选）。
- `GET/POST /api/workspace`（对齐 `main.py:563-579` 的字段映射、`main.py:580-595`
  的内存模式序列化与 `main.py:865-957` 的内存解析）。
- `GET /api/outputs` 的目录遍历限制（只允许 `output_dir` 或作业目录下的路径）。

## 4. 不要做的事

- **不要删除任何文件**（共享盘上的删除/移动常被策略拦截，且需要用户拍板）：
  `webapp/job_store.py` 只把内容替换为一句话说明；`webapp/jobs/87499fe93868/` 原样保留。
- 不要改 `shared/design/pattern_runner.py`、`shared/design/pattern_spec.py`、
  `shared/design/system_presets.py`、`shared/search/*`、`shared/scoring/*`、
  `shared/output/*`、`shared/data/*`、`shared/utils/*` 的行为契约。
- 不要改 `unified_gui.py`、`main.py` 的界面代码（本轮只从它们读事实，不移植它们的
  Tk 代码到 webapp，也不改它们的布局）。
- 不要为了复用而重构 `designer_workbench.py:2308-2334` 的进度解析（它和进度条动画耦合），
  网页端在 `webapp/services/designer.py` 里写等价解析即可。
- 不要引入 flask/fastapi/aiohttp/jinja2/任何 CDN 资源；保持 stdlib + 原生 JS。
- 不要把 `webapp/services/*` 做成 Tk 或 GUI 的依赖，也不要 import
  `designer_workbench`（它会 import tkinter）。
- 不要改 `tests/` 下除 `tests/test_webapp.py`（重写）和新增
  `tests/test_workbench_form.py` 之外的测试文件。
- 不要跑全量测试套件（`run_tests.py`）并宣称“全部通过”——那是 master 的核验动作。
- 不要顺手修 2.2/2.4 里记的既有问题（无 `.git`、`.venv` 失效、`GUI_SCRIPTS` 死代码），
  只在 `report.md` 的“附带发现”里记录。

## 5. 决策项（未确认则按推荐执行）

- Web 框架 → 推荐：**Python 标准库 `http.server.ThreadingHTTPServer`**（沿用旧实现的
  形态）。理由：离线可用、无新依赖、与 `docs/WEBAPP.md` 的安全边界一致。
- 前端形态 → 推荐：**单页 + 原生 JS + fetch**，`index.html` + `static/app.js` +
  `static/styles.css`。理由：无需构建步骤，改完即可刷新。
- 表单映射逻辑位置 → 推荐：**抽到 `shared/design/workbench_form.py`**（P0-1），
  GUI 与 webapp 共用。理由：否则网页结果会与桌面端漂移，违反 `docs/WEBAPP.md:3-5`。
- 导出落盘位置 → 推荐：写到 `<job_dir>/export/<生成的文件名>`，再返回
  `/api/jobs/<id>/download?file=export/<name>`；不弹系统保存对话框。
  理由：浏览器无法写任意本地路径，且下载白名单可覆盖该目录。
- 作业并发 → 推荐：全局最多 1 个运行中的重作业，其余排队。理由：基因组级搜索/建索引
  内存占用大，桌面端也是单任务串行。
- `CONFIRM_REQUIRED` → 推荐：默认自动同意并记日志（`[auto-confirm] ...`）。
  理由：无人值守的网页端需要让 auto 引擎链的回退（`shared/search/offtarget_backend.py`）
  正常继续；P1 再加人工确认入口。
- 服务重启后的遗留作业 → 推荐：标为 `interrupted` 并在 UI 显示“已中断，可重新提交”。
  理由：不谎报 running。
- `panel`（Data prep / Models / Designer）状态保存 → 推荐：**不做**持久化（P1 的
  workspace 端点除外），刷新页面丢掉未提交的表单值是可接受的。
- 页面语言 → 推荐：英文（与桌面端控件文案一致），说明性文字可中文。

## 6. 轻量自检（servant 的检验上限）

```powershell
# 1) 语法
python -m py_compile webapp\app.py webapp\jobs.py webapp\schema.py `
  webapp\services\designer.py webapp\services\dataprep.py webapp\services\models.py `
  shared\design\workbench_form.py designer_workbench.py `
  tests\test_workbench_form.py tests\test_webapp.py

# 2) 聚焦单测（不启动真实子进程、不需要浏览器）
python -m unittest tests.test_webapp tests.test_workbench_form -v

# 3) 桌面端回归（桌面 spec/config 必须与改动前一致）
python -m unittest tests.test_designer_workbench tests.test_pattern_runner -v

# 4) 最小端到端（另开一个终端）
python webapp\app.py --port 8123
curl.exe -s http://127.0.0.1:8123/api/schema
curl.exe -s http://127.0.0.1:8123/ | Select-String -Pattern "Data prep","Models","Designer"

# 5) 若无浏览器：用 preview + 提交一个最小作业验证链路（示例，路径按本机实际改）
#    preview 应返回 errors=[]（或明确的缺失项文案）
curl.exe -s -X POST http://127.0.0.1:8123/api/designer/preview -H "Content-Type: application/json" `
  -d "{\"mode\":\"single_motif_flank\",\"input_mode\":\"sequence\",\"values\":{\"search_fasta\":\"example\\target.fa\",\"genome_fasta\":\"example\\genome.fa\",\"output_dir\":\"out\\webapp_smoke\"},\"motif\":\"TTAT\",\"flank\":\"5\",\"side\":\"upstream\"}"
```

第 5) 条的示例路径需要自行准备：仓库里**没有** `example/genome.fa` 或
`example/target.fa`。请自己造一个 2 行 FASTA（如 `out/webapp_smoke/target.fa`，
内容 `>t1` + 一行 40 bp 序列）当 Search FASTA，genome 用仓库现成的
`example/engine_benchmark/synthetic_genome.fa`（约 5 MB），`output_dir` 用
`out/webapp_smoke`；三者都写绝对路径。不要用 `example/GCF_000001405.40_GRCH38.p14_genomic.fna`
（3.3 GB）或 `example/chr21_22.fa`（100 MB）做这个 smoke。

自检通过标准：2) 与 3) 全绿；4) 返回 200 且 `/api/schema` 里的引擎列表与
`ENGINE_CHOICES` 一致。**不要**在自检里跑真实全基因组搜索或建索引。

## 7. 交付要求

- 改前把受影响文件快照到 `backup\20260916_webapp_designer_port\`
  （至少包含 `designer_workbench.py`、`webapp\app.py`、`webapp\job_store.py`、
  `webapp\index.html`、`tests\test_webapp.py`、`docs\WEBAPP.md`、`README.md`）。
- 完成后：`state.json` 置 `ready_for_review`，并在 `report.md` 写：改动文件 + 行号、
  第 6 节每条命令的**原文与输出**、未做项及原因、附带发现、待明确项。
- 附带发现只记录、不修复。
- 不要修改本 `task.md`；规格有疑问时写进 `report.md` 的“待明确”，由 master 决定。
