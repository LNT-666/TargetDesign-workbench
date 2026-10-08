# Motif 分析工具集

本项目用于生物序列中的 motif 发现、候选区提取、Off-target search、评分排序和结果导出。

## 功能状态

- **Library 出库：已废弃。** `shared/design/library_pipeline.py` 及其调用入口（`main.py` 的 Library 页签、`unified_gui.py`）不再开发、不再维护；`unified_gui.py` 里的 `One-click library (disabled)` 按钮已置灰停用，按钮背后的代码保留只为不影响其它功能，相关既有失败不再修复。
- **多任务/批量：提供 CLI 批量入口（`tools/batch_run.py`，见 `docs/BATCH.md`）与 webapp 批量面板（见 `docs/WEBAPP.md`）；桌面 GUI 批量面板暂不支持；两种入口的操作步骤见下文「批量运行」。**

## 设计功能（补充）

- **BED designer**：`designer_workbench.py --bed` 以 BED 区域为输入打开设计器（窗口标题为 `BED Designer`），或在统一工作台的 Designer 工具条点击 “Open BED Designer”。结果 `library_scores.tsv` 会带 `genomic_start`/`genomic_end`/`genomic_strand` 和 `genomic_positions`（JSON，列出所有出现位置）；这些列仅在区域/BED 输入时填充，纯 FASTA 输入时全空并被隐藏。

- **全空列自动隐藏**：结果表（`library_scores.tsv`、`query_scores_sorted.tsv` 等）写出前检查每列，整列全空（`None`/`""`/纯空格）的列默认不显示；数值 0/0.0 不算空。

- **MM 列跟随 mismatch 预算**：`max_mismatch=N` 时结果表只输出 `MM0` 到 `MMN`，最后一列统计 `>= N` 的合并数量；例如预算 2 不再输出恒为 0 的 `MM3`，预算 4 会输出 `MM4`。

- **TnpB / TEEP**：designer 不再提供 TnpB 亚型选择。TnpB 默认使用离线、确定性的 `omega` / `omega_rna_rules` on-target 规则；`teep` 是显式选择的在线 ISDra2 TnpBmax 参考模型。TEEP 失败时回退通用启发式，不会自动改用 omega 规则。`tnpb_subtype` 和模型名称/文献内部字段已从当前候选表移除。完整公式、文献和字段说明见 `docs/TNPB.md`。

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

```text
.
├─ designer_workbench.py
├─ unified_gui.py
├─ main.py
├─ run_tests.py
├─ README.md
├─ shared/
│  ├─ design/       pattern 定义、guide 设计、library pipeline（已废弃）
│  ├─ search/       exact、BLAST、indexed、外部 Off-target 引擎
│  ├─ scoring/      评分模型、预设规则、非 Cas9/RNA 规则
│  ├─ data/         genome/annotation 下载、解析和本地提取
│  ├─ output/       TSV/BED/FASTA/XLSX/HTML
│  ├─ gui/          共享 GUI mixin 和 preset 控件
│  └─ utils/        日志、子进程工具
├─ basic/           单 motif 命令行流程
├─ tools/           索引构建、索引搜索、模型转换
├─ webapp/          本地 Web 服务和任务存储
├─ Target_xbp_Target/
├─ Target_xbp_Y_zbp_Target/
├─ tests/
├─ docs/
└─ models/
```

`models/` 存放本地模型权重，权重文件不入库，获取方式见 `docs/MODELS.md`；
基因组、索引和基准数据同样不入库，见 `docs/GENOME_INDEX.md`。

## 环境

- 主运行环境：Python 3.13，虚拟环境 `.venv`
- 旧模型转换环境：Python 3.10，虚拟环境 `.venv310`
- 外部工具：NCBI BLAST+，需要 `blastn` 和 `makeblastdb`

Windows 初始化：

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements-windows.txt
```

Linux/macOS 使用 `requirements.txt`，并按需安装 BLAST+。

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

## 命令行示例

基础 motif 提取和搜索：

```powershell
.\.venv\Scripts\python.exe basic\extract.py input.fasta TTAT 10 upstream extracted.tsv
.\.venv\Scripts\python.exe basic\blast.py queries.tsv genome.fa --outdir results --max-mismatch 2
.\.venv\Scripts\python.exe basic\analyze_scores.py results\blast_results.tsv results
```

构建基因组索引和搜索：

```powershell
.\.venv\Scripts\python.exe tools\build_genome_index.py genome.fa --prefix genome_index
.\.venv\Scripts\python.exe tools\search_indexed.py genome_index guides.tsv --out results
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
`docs/NATIVE_INDEXED_BENCHMARK.md`，构建说明见 `native/offtarget_engine/README.md`。

`indexed` 默认优先使用 C++20 CLI 实现，读取和写出相同的 `.ggi` v1 格式；找不到或
不兼容原生二进制时使用 Python 实现，`PROGRAMFILE_NATIVE_INDEXED=0` 可强制回退。
内存上限 `--max-memory-mb` / `PROGRAMFILE_MAX_MEMORY_MB`、墙钟上限 `--timeout-s` /
`PROGRAMFILE_OFFTARGET_TIMEOUT_S`、索引 `<genome>.k<k>.ggi` 命名与 `<prefix>.lock`
排他锁，以及 GUI 的 Auto 内存限制，见 `docs/OFFTARGET_ENGINES.md` 与
`docs/GENOME_INDEX.md`。

Cas9 PAM 支持 `strict_ngg`（只搜索 NGG）与 `guidescan2_nrg`（搜索 NRG = NGG + NAG，CFD 使用实际的 `GG` / `AG` 2 nt 权重）两种模式；CLI 用 `--pam-mode`，网页版和桌面主工作台在 Run Settings 选择，并显示当前模式，桌面 Run Settings 也暴露 `Max Bulge` 的 engine-default / 0 / 1 选项。模式定义与权重细节见 `docs/SCORING_GUIDE.md`。

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

`test_library_fasta` 覆盖的是已废弃的 library 管线，其既有失败不再修复。

## 文档

- `docs/OUTPUTS.md`：结果文件与结果列说明（输出结果的单一入口）
- `docs/design_patterns_en.md`：pattern 定义说明
- `docs/PAIR_RANKING.md`：双靶点必须同时成功时的 PairRank 排序规范
- `docs/ENVIRONMENT.md`：Python 环境和模型转换
- `docs/OFFTARGET_ENGINES.md`：Off-target 引擎说明
- `docs/GENOME_INDEX.md`：本地 `.ggi` 索引格式、构建和 native/Python 关系
- `docs/MODELS.md`：模型文件状态
- `docs/TNPB.md`：TnpB/TEEP 模型公式、适用范围和参考文献（结果字段见 `docs/OUTPUTS.md`）
- `docs/GUI.md`：桌面工作台使用说明
- `docs/WEBAPP.md`：本地 Web UI 使用说明
- `docs/BATCH.md`：批量运行规范（CLI 与 webapp 共用内核、manifest、汇总表与退出码）
- `docs/SCORING_GUIDE.md`：评分字段与候选优劣判断
- `docs/CRISPAI.md`：crispAI 运行时环境准备
- `docs/SERVER_DEPLOY.md`：Linux 服务器部署与全基因组索引构建
