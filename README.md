# Motif 分析工具集

本项目用于生物序列中的 motif 发现、候选区提取、Off-target search、评分排序和结果导出。

## 功能状态

- **Library 出库：已废弃。** `shared/design/library_pipeline.py` 及其调用入口（`main.py` 的 Library 页签、`unified_gui.py`）不再开发、不再维护；`unified_gui.py` 里的 `One-click library (disabled)` 按钮已置灰停用，按钮背后的代码保留只为不影响其它功能，相关既有失败不再修复。
- **多任务/批量：提供 CLI 批量入口（`tools/batch_run.py`，见 `docs/BATCH.md`）与 webapp 批量面板（见 `docs/WEBAPP.md`）；桌面 GUI 批量面板暂不支持；两种入口的操作步骤见下文「批量运行」。**

## 设计功能（补充）

- **BED designer**：`designer_workbench.py --bed` 以 BED 区域作为搜索输入打开设计器（窗口标题为 `BED Designer`），或在统一工作台的 Designer 工具条点击 “Open BED Designer”。候选表列以 `shared/design/pattern_spec.py::candidate_columns()` 和 `docs/OUTPUTS.md` 的当前定义为准。

- **全空列自动隐藏**：结果表（如 `query_scores_sorted.tsv`）写出前检查每列，整列全空（`None`/`""`/纯空格）的列默认不显示；数值 0/0.0 不算空。

- **MM 列跟随 mismatch 预算**：`max_mismatch=N` 时结果表只输出 `MM0` 到 `MMN`，最后一列统计 `>= N` 的合并数量；例如预算 2 不再输出恒为 0 的 `MM3`，预算 4 会输出 `MM4`。

- **TnpB / TEEP**：designer 仍提供只读的 `tnpb_subtype` 选择，并把它传入运行参数和评分；`tnpb_subtype` 不再作为当前候选表的输出列。TnpB 默认使用离线、确定性的 `omega` / `omega_rna_rules` on-target 规则；`teep` 是显式选择的在线 ISDra2 TnpBmax 参考模型。TEEP 失败时回退通用启发式，不会自动改用 omega 规则。完整公式、文献和字段说明见 `docs/TNPB.md`。

## 当前架构

旧版三个独立 Tkinter GUI 正在收敛为统一的结果中心工作台：

```text
定义 pattern -> 提取候选 -> Off-target search -> 评分过滤排序 -> 导出选中候选
```

主要入口：

| 文件 | 作用 |
| --- | --- |
| `designer_workbench.py` | 当前主桌面工作台，以结果表为中心 |
| `unified_gui.py` | 统一模式/pattern/候选表工作台 |
| `main.py` | 旧版启动器，承担部分数据准备和共享 GUI 功能 |
| `webapp/app.py` | 本地 Web UI：单页工作区（Designer 常驻主区 + Data prep/Models 近满屏滑出面板） |

支持的 pattern 类型由 `shared/design/pattern_spec.py` 定义：

- `SINGLE_MOTIF_FLANK`
- `MOTIF_GAP_MOTIF`
- `Y_CENTERED_MOTIFS`

## 目录结构

以下是主要顶层目录与文件；生成目录、缓存、模型权重和本地运行产物不列入。

```text
.
├─ .dockerignore
├─ .gitattributes
├─ .github/          CI、容器与可移植性工作流
├─ .gitignore
├─ .zenodo.json
├─ basic/            单 motif 命令行流程
├─ docs/             公开文档与帮助页
├─ example/          可复现示例与小型基准证据
├─ native/           C++20 indexed 引擎源码与构建说明
├─ sample_data/      演示输入数据
├─ shared/           设计、搜索、评分、数据与输出模块
├─ Target_xbp_Target/
├─ Target_xbp_Y_zbp_Target/
├─ tests/
├─ tools/            索引构建、搜索、批量与发布工具
├─ webapp/           本地 Web 服务和任务存储
├─ CITATION.cff
├─ Dockerfile
├─ docker-compose.yml
├─ designer_workbench.py
├─ unified_gui.py
├─ main.py
├─ run_tests.py
├─ pyproject.toml
├─ requirements.txt
├─ requirements-linux.txt
├─ requirements-models-linux.txt
├─ requirements-crispai.txt
├─ requirements-windows.txt
├─ requirements/      Linux CPU/CUDA constraint snapshots
├─ README.md
└─ LICENSE
```

`models/` 存放本地模型权重，权重文件不入库，获取方式见 `docs/MODELS.md`；
大体积基因组与索引不入库；`example/engine_benchmark_small/` 的小型基准证据和
`sample_data/` 演示数据随仓库发布。索引构建与复用见 `docs/GENOME_INDEX.md`。

## 环境

- 主运行环境：Python 3.12（默认；Python 3.13 也受支持），虚拟环境 `.venv`
- 旧模型转换环境：Python 3.10，使用独立的模型转换虚拟环境
- 外部工具：NCBI BLAST+，需要 `blastn` 和 `makeblastdb`

Windows 初始化：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements-windows.txt
```

Linux/macOS 初始化：

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements-linux.txt
```

`requirements-linux.txt` 是完整环境入口，会安装基础、模型和 crispAI 的 Python 依赖；
系统级 BLAST+ 仍需按需安装。需要复现已测试的 Linux 版本组合时，按
`docs/ENVIRONMENT.md` 的 CPU/CUDA 命令同时传入 `requirements/constraints-linux-*.txt`。
机器可读的 Python 版本范围见 `pyproject.toml`。

## 启动

```powershell
.\.venv\Scripts\python.exe designer_workbench.py
```

也可以使用：

```powershell
.\.venv\Scripts\python.exe unified_gui.py
.\.venv\Scripts\python.exe main.py
.\.venv\Scripts\python.exe webapp\app.py
```

Linux/macOS 想让它常驻后台、并用一条命令重启（详见 `docs/WEBAPP.md`）：

```bash
bash tools/serve_webapp.sh start     # 默认 0.0.0.0:5000；restart / stop / status 同理
```

## 命令行示例

基础 motif 提取和搜索：

```powershell
.\.venv\Scripts\python.exe basic\extract.py input.fasta TTAT 10 upstream extracted.tsv
.\.venv\Scripts\python.exe basic\blast.py queries.tsv genome.fa --输出目录 results --max-mismatch 2
.\.venv\Scripts\python.exe basic\analyze_scores.py results\blast_results.tsv results
```

构建基因组索引和搜索：

```powershell
.\.venv\Scripts\python.exe tools\build_genome_index.py genome.fa --prefix genome_index
python tools/search_indexed.py guides.tsv genome.fa results --index-path genome_index --pam NGG
```

更多参数使用各脚本的 `--help`。

## 批量运行

一次批量提交把「search scope（序列 FASTA 或 BED 区域文件）」与「pattern 配置（一整份 `PatternSpec`）」两个轴组合成若干 unit，**串行**跑完同一个 `PatternRunner` 管道，并汇总成一张评分总表。CLI 与网页版共用同一套批量内核与产物契约，`docs/BATCH.md` 是权威定义（`batch.json` schema、unit 顺序、`manifest.tsv`、`summary/batch_scores.tsv`、退出码）；桌面 GUI 暂无批量面板。

- CLI：`python tools\batch_run.py --spec my_batch.json`，`--dry-run` 只预览，`--no-resume` / `--only` / `--units-tsv` 等参数见 `docs/BATCH.md`；完整可运行示例见 `example/batch/example_batch.json`。
- 网页版：启动 `python webapp\app.py` 后用页面下方 `Batch` 区块（`Add scope` → `Add current Designer pattern` → `Preview units` → `Run batch`）；payload 字段、接口与作业导出见 `docs/WEBAPP.md` 的「批量（Batch）」。

## 模型与引擎

### 评分模型

模型文件、格式、校验和、真实可用状态，以及 on/off-target 各模型的用途与优缺点对比，见 `docs/MODELS.md`。评分公式、特异性聚合、`custom` 下的模型分派与 `[rule]` / 蛋白分类标记见 `docs/SCORING_GUIDE.md`。

按核酸酶默认：on-target 取 `cas9: cropsr` / `cas12a: rules` / `cas13: rna_rules` / `tnpb: omega`；off-target 取 `cas9/custom: cfd` / `cas12a/cas12b: rules` / `cas13: pfs` / `tnpb: identity`。模型下拉框不再提供 `auto`，旧命令行传入 `auto` 仍兼容。Pattern Designer 每侧的 On-target / Off-target 模型支持多选，每个勾选模型输出自己的 `<model>` 评分列，列命名与旧列清单见 `docs/OUTPUTS.md`；双靶 pattern 使用 Prediction-only PairRank 作为主排序，旧 `combined_score` 已删除，规则见 `docs/PAIR_RANKING.md`。

### 脱靶搜索引擎

`exact` / `indexed` / `blast` / `gggenome` / `auto` 的统一命中记录、能力矩阵、
`auto` 运行期引擎链与回退策略见 `docs/OFFTARGET_ENGINES.md`；本地 `.ggi` 索引
格式、构建与复用见 `docs/GENOME_INDEX.md`；native indexed 的实测数据见
`example/engine_benchmark_small/REPORT.md`，设计说明见
`docs/NATIVE_INDEXED_ENGINE_DESIGN.md`，构建说明见 `native/offtarget_engine/README.md`。

`indexed` 默认优先使用 C++20 CLI 实现，读取和写出相同的 `.ggi` v1 格式；找不到或
不兼容原生二进制时使用 Python 实现，`PROGRAMFILE_NATIVE_INDEXED=0` 可强制回退。
内存上限 `--max-memory-mb` / `PROGRAMFILE_MAX_MEMORY_MB`、墙钟上限 `--timeout-s` /
`PROGRAMFILE_OFFTARGET_TIMEOUT_S`、索引 `<genome>.k<k>.ggi` 命名与 `<prefix>.lock`
排他锁，以及 GUI 的 Auto 内存限制，见 `docs/OFFTARGET_ENGINES.md` 与
`docs/GENOME_INDEX.md`。

Cas9 PAM 支持 `strict_ngg`（只搜索 NGG）、`guidescan2_nrg`（搜索 NRG = NGG + NAG，CFD 使用实际的 `GG` / `AG` 2 nt 权重）与 `custom`（使用用户输入的 PAM motif）三种模式；CLI 用 `--pam-mode`，网页版和桌面主工作台在 Run Settings 选择，并显示当前模式，桌面 Run Settings 也暴露 `Max Bulge` 的 engine-default / 0 / 1 选项。模式定义与权重细节见 `docs/SCORING_GUIDE.md`。

搜索结果为每条 hit 保留真实 alignment span、CIGAR、`rna_bulges` 和 `dna_bulges`；结果列与 bulge / 校准列见 `docs/OUTPUTS.md`。BLAST 数据库的 `.source.json` 校验、批量性能工具 `tools/benchmark_search.py`，以及各引擎的完整约束与使用示例，见 `docs/OFFTARGET_ENGINES.md`。

双靶 Pattern A / Pattern B 的 Run Settings 必须显式填写完整的 `PairRank prediction_only policy`；缺少参数时 GUI 不会回退到旧的 `combined_score` 排序，规则见 `docs/GUI.md` 与 `docs/PAIR_RANKING.md`。

## 测试

```powershell
.\.venv\Scripts\python.exe run_tests.py
```

聚焦单个模块：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_core.py" -v
```

## 文档

公开文档按用途分组列出。未跟踪的本地笔记、生成物和投稿材料不在本清单内。

使用、部署与输出：

- `docs/BATCH.md`：批量运行规范（CLI 与 webapp 共用内核、manifest、汇总表与退出码）
- `docs/WEBAPP.md`：本地 Web UI 使用说明
- `docs/GUI.md`：桌面工作台使用说明
- `docs/OUTPUTS.md`：结果文件与结果列说明（输出结果的单一入口）
- `docs/CONTAINER.md`：容器镜像与运行说明
- `docs/CRISPAI.md`：crispAI 外部运行时准备
- `docs/SERVER_DEPLOY.md`：Linux 服务器部署与全基因组索引构建

设计、模型、搜索与评分：

- `docs/design_patterns_en.md`：pattern 定义说明
- `docs/MODELS.md`：模型文件、格式与状态
- `docs/ENVIRONMENT.md`：Python 环境和模型转换
- `docs/DEPENDENCIES.md`：Python 与非 Python 依赖清单
- `docs/GENOME_INDEX.md`：本地 `.ggi` 索引格式、构建和 native/Python 关系
- `docs/OFFTARGET_ENGINES.md`：Off-target 引擎说明
- `docs/NATIVE_INDEXED_ENGINE_DESIGN.md`：native indexed 引擎设计契约
- `docs/RNA_RULES.md`：Cas13 RNA 规则与 ViennaRNA 行为
- `docs/SCORING_GUIDE.md`：评分字段与候选优劣判断
- `docs/TNPB.md`：TnpB/TEEP 模型公式、适用范围和参考文献
- `docs/PAIR_RANKING.md`：双靶点必须同时成功时的 PairRank 排序规范

英文帮助：

- `docs/help_en/index.md`：英文帮助入口
- `docs/help_en/README.md`：英文帮助概览
- `docs/help_en/tutorial.md`：英文教程
- `docs/help_en/sample_output/README.md`：英文示例输出说明
