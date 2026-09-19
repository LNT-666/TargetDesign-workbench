# Motif 分析工具集

本项目用于生物序列中的 motif 发现、候选区提取、Off-target search、评分排序和结果导出。当前代码已经完成一轮共享模块重构，README 和 `docs/` 是项目结构的**事实来源**；修改架构后请同步更新这里。

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
├─ models/
├─ example/
├─ logs/
├─ backup/
├─ .venv/
└─ .venv310/
```

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

## 模型与引擎

### 评分模型

On-target 评分模型：

| 模型 | 用途 | 特点 | 优点 | 缺点 |
| --- | --- | --- | --- | --- |
| CROPSR | Cas9 on-target | 使用已发表的 Doench/CROPSR 逻辑回归系数；对 30mer 窗口计算，长窗口取最佳 30mer | 纯数值计算，速度快、无外部依赖、结果可复现 | 只面向 Cas9/30mer 结构，非标准窗口会退回启发式 |
| Azimuth V3 nopos | Cas9 on-target | GBDT 回归（100 棵树），含 order1/order2、GC、NGGX、Tm 特征；已转为 NumPy 可移植格式 | 参考验证好（Spearman 0.993）；不依赖旧版 sklearn | 当前不是默认入口；训练数据年代较早 |
| DeepCpf1 | Cas12a/Cpf1 on-target | 序列 CNN 模型，HDF5 权重 | 面向 Cas12a/Cpf1 的专项模型 | 纯 NumPy 前向已接入，可作为 Cas12a/Cpf1 on-target 显式选项 |
| TEEP | ISDra2 TnpBmax on-target | 在线 CNN + Bi-LSTM API，预测 20 nt 引导序列；参考文献 Marquart et al. 2024 | 针对 ISDra2/TnpBmax 的专项预测 | 需要网络，逐条查询较慢；失败时退回通用启发式，不会退回 omegaRNA 规则 |
| omegaRNA 规则 | TnpB on-target 编辑效率 | 本地确定性规则：长度、GC、发夹、repeat | 离线可用、快速、稳定 | 是简化规则，不是训练模型；属 on-target 效率规则，不是特异性评分 |
| Cas13 RNA 规则 | Cas13a/b/d on-target | 有 ViennaRNA 时计算 accessibility、MFE、DR-spacer、靶 RNA 扰动；无则用 U/A 富集启发式 | 可解释、离线可用、包含 RNA 结构信息 | 质量依赖 ViennaRNA 是否安装，启发式部分较粗 |
| TIGER | Cas13d on-target | Cas13d 深度学习模型（TF SavedModel），对 23 nt spacer 给出 0-1 活性分数；有 `target_rna`+`spacer_start` 时自动抠 3 nt 上游上下文 | 23 nt Cas13d 专项预测，准确性优于简化规则 | 只适用于 23 nt spacer；需要 TensorFlow 运行时；模型文件经 hf-mirror resolve 下载 |
| 内置启发式 | 通用 on-target | GC、seed GC、homopolymer、复杂度加权 | 任何输入都能出分，速度最快 | 精度最低，只适合兜底 |

Off-target 评分模型：

| 模型 | 用途 | 特点 | 优点 | 缺点 |
| --- | --- | --- | --- | --- |
| CFD | Cas9 off-target | 位置特异错配表 + PAM 权重 | 极快、无需模型文件、稳定 | 非学习模型，主要面向 SpCas9 |
| CRISPR-M | Cas9 off-target | 多头注意力 + 卷积 + 双向 LSTM，NumPy 前向 | 对 off-target 排序能力通常优于 CFD；无需 TensorFlow | 需要约 20MB 模型文件；推理比 CFD 慢 |
| DeepCRISPR | Cas9 off-target | CNN 模型，已转为 portable NumPy | 免 TensorFlow，权重转换已验证 | 需要 portable 模型文件；推理较慢 |
| crispAI | Cas9 off-target | uncertainty-aware 聚合模型，外部适配器调用上游 agg-score | 输出保留后验不确定性信息 | 需要 R/NuPoP、Cas-OFFinder、GRCh38；见 `docs/CRISPAI.md` |
| identity/preset 启发式 | 非 Cas9 off-target | 序列相似度 + seed 惩罚 | 无需模型，快速覆盖 Cas12/Cas13/TnpB | 近似评分，缺少学习模型精度 |
| TIGER | Cas13d off-target | 对每个 off-target spacer 用 TIGER 打分并按 `1/(1+sum)` 聚合；模型不可用时回退 PFS 规则（CFD 风格） | 23 nt Cas13d 专项 off-target 活性评估 | 只适用于 23 nt spacer；需要 TensorFlow 运行时 |

模型文件、校验和与状态见 `docs/MODELS.md`。

### 脱靶搜索引擎

| 引擎 | 特点 | 优点 | 缺点 |
| --- | --- | --- | --- |
| `exact` | 本地 k-mer + Levenshtein，支持 mismatch/indel | 小基因组穷尽、无外部工具 | 大基因组内存和耗时高 |
| `indexed` | 本地持久化基因组索引 | 索引可复用，搜索穷尽且可重复 | 首次建索引较慢、占用磁盘 |
| `blast` | NCBI BLAST+ `blastn` | 大型基因组方案成熟 | 依赖 BLAST+，首次建库和全基因组搜索较慢 |
| `gggenome` | GGGenome 在线 API | 无本地依赖 | 需要网络，逐 guide 查询较慢，受在线服务限制 |
| `auto` | 自动选择 | 默认省心 | 小/中型优先 native indexed，其次 blast；大型优先 blast；显式 db/index 独占 |

`auto` 是一条运行期引擎链：显式 `--blastdb` 时只使用 blast，显式
`--index-path` 时只使用 indexed。这两个参数是“独占”而不是“优先”：指定的
资源不可用或运行失败时 auto 直接报错，错误信息会提示改用 `--engine`
显式回退。两者都没有时，FASTA 不超过 `MAX_EXACT_GENOME_BYTES`
（= `200 * 1024 * 1024` 字节，按文件字节数而不是碱基数比较；读不到大小时
按不超过处理）则在 native indexed 可用时优先 indexed，否则优先 blast；
超过该大小则优先 blast，避免自动构建超大索引。链按 `auto_engine_candidates`
的顺序逐个尝试，某个候选不可用或运行失败时先记录失败原因，再按
`--engine-fallback`（`CRISPR_OFFTARGET_ENGINE_FALLBACK`，默认 `ask`）确认后
切换到下一个候选；链中的 indexed 候选强制 `python_fallback=deny`，所以 auto
不会停在纯 Python 实现上，而是继续尝试 blast 等真正的引擎。未显式指定
`max_bulge` 时 auto 默认使用 `0`，排序和实际执行共享同一份默认值；显式
`max_bulge=1` 再启用 gapped alignment。完整能力矩阵见
`docs/OFFTARGET_ENGINES.md`。

`indexed` 默认优先使用 C++20 CLI 实现，读取和写出相同的 `.ggi` v1
格式，并通过原 `IndexedBackend` 对外提供同一 engine。找不到或不兼容
原生二进制时自动使用 Python 实现；设置
`PROGRAMFILE_NATIVE_INDEXED=0` 可强制回退 Python。
构建、限制和性能数据见 `native/offtarget_engine/README.md` 与
`example/engine_benchmark_small/REPORT.md`。原生在输出 hit 前失败时默认允许
Python fallback，设置 `PROGRAMFILE_NATIVE_INDEXED_FALLBACK=0` 可关闭；
`search` 和 `build-index` 都支持 `--max-memory-mb N`，省略或 `N=0`
表示无显式上限；也可用 `PROGRAMFILE_MAX_MEMORY_MB`，CLI 参数优先。
`search` / `build-index` 还接受 `--timeout-s N`（或
`PROGRAMFILE_OFFTARGET_TIMEOUT_S`）作为单次调用的墙钟上限，默认不限时；
索引前缀按 `k` 命名（`<genome>.k<k>.ggi`），构建时持有 `<prefix>.lock`
排他锁，多个 run 共用输出目录时不会覆盖正在读取的索引。
- `--engine auto` 在运行期按偏好顺序逐个尝试候选引擎：候选不可用或失败时记录原因，并按
  `--engine-fallback`（默认 `ask`）确认后切换到下一个；显式 `--blastdb` /
  `--index-path` 时只保留那一个候选，不会回退到其他引擎；大基因组带 bulge 时顺序为
  blast → indexed。链中的 indexed 不会退化成纯 Python 索引。
native 在输出 hit 前返回 `MEMORY_LIMIT_EXCEEDED` 时不会自动回退到
未受限制的 Python 路径；Python indexed fallback 也会应用同一预算。
GUI 的 Memory Limit 默认是 `Auto (50% RAM)`，实际值按
`min(50% total, 75% available)` 每次运行前重新解析，Auto 的固定 MiB
不会写入 workspace。summary 记录 `memory_limit_mb`、
`estimated_peak_mb` 和 `observed_peak_mb`。
`auto` 的大基因组 BLAST 选择规则不变；小型和中等基因组按上述基准顺序
选择。显式 `max_bulge=1` 会让 BLAST 使用 gapped alignment，indexed 也会
在运行前校验 seed plan。

Cas9 PAM 支持两种兼容模式：

- `strict_ngg`：只搜索 NGG
- `guidescan2_nrg`：搜索 NRG（NGG + NAG），CFD 使用实际的 `GG` / `AG`
  2 nt 权重

CLI 使用 `--pam-mode`，网页版和桌面主工作台的 Run Settings 可选择
Strict NGG / GuideScan2 NRG，并显示当前模式；桌面 Run Settings 也暴露
`Max Bulge` 的 engine-default / 0 / 1 选项。
搜索结果为每条 hit 保留真实 alignment span、CIGAR、`rna_bulges` 和
`dna_bulges`；`library_scores.tsv` 输出 `bulge_hits`、
`scored_bulge_hits`、`unscored_bulge_hits` 和 `calibration_status`。
BLAST 数据库通过 `.source.json` 校验源 FASTA；manifest 缺失或 FASTA
变化时默认重建。

批量搜索性能可用 `tools/benchmark_search.py` 复现和记录；它输出
guides/s、内存峰值、seed plan 状态和变体枚举量。

默认策略：脱靶引擎默认 `auto`（显式 BLAST db / index path 独占，不会回退到其他
引擎；小中型优先 native indexed，缺失时按 bulge 分榜回退；大型优先 BLAST）；on-target 默认按核酸酶取 `cas9: cropsr` / `cas12a: rules` / `cas13: rna_rules` / `tnpb: omega`，
off-target 默认按预设取 `cas9/custom: cfd` / `cas12a/cas12b: rules` / `cas13: pfs` / `tnpb: identity`。
模型下拉框不再提供 `auto`；旧命令行传入 `auto` 仍兼容。

Pattern Designer 中每侧的 On-target / Off-target 模型支持多选。结果文件不再
输出无后缀的 `on_target_score`、`on_target_model`、
`off_target_specificity`、`off_target_model` 基础列；每个勾选模型统一输出
带模型标识的评分列（如 `on_target_score_cropsr`、
`off_target_specificity_cfd`），不再单独输出 `on_target_model_<model>`、
`off_target_model_<model>` 等模型名称列。双靶 pattern 使用 PairRank
作为主排序，旧 `combined_score` 已删除。`reference_only`、`reference_note`、
`rule_source`、`rule_reference`、`rule_summary`、`subtype_note` 仅保留在内部
评分结果中，不再写入候选表；旧式固定列 `cfd_specificity`、
`crispr_m_off_target`、`deepcrispr_off_target`、`crispai_off_target`、
`deepcas12a_on_target`、`deepcpf1_on_target`、`tiger_on_target`、
`tiger_off_target` 也不再直接输出，统一使用勾选模型的 `<model>` 列。选择
`custom` 时，模型下拉框自动汇总所有预设的
on/off-target 模型；预设模型在 custom 下按 `reference_only` 参考评分调用。
Cas13 的 `rna_model`/MFE/accessibility 等 RNA 子特征只随 RNA on-target
模型输出；TnpB 的 `omega_model`/spacer/结构子特征只随 omega on-target
模型输出。未选择模型不会在结果表中产生对应列。
`cfd`、`pfs`、`identity`、`rna_rules`、`omega`、`rules` 等传统规则会显示
`[rule]` 标识；所有模型还会显示适用蛋白分类，例如 `[Cas9] [rule] cfd`、
`[Cas12a] deepcas12a`、`[Cas13] tiger`、`[TnpB] [rule] omega`。
`crispai` 也作为普通 Cas9 Off-target 模型参与多选，不再需要单独开关。
当 `nuclease == custom` 时，所有模型都允许调用；预设专属模型按参考模型
（`reference_only`）处理，`rules` / `identity` 等通用传统规则照常计算，
输入若不满足模型本身要求则由该模型回退。

双靶 Pattern A / Pattern B 的 Run Settings 提供
`PairRank prediction_only policy`，必须显式填写完整策略。缺少参数时 GUI
不会回退到旧的 `combined_score` 排序。

引擎的完整约束和使用示例见 `docs/OFFTARGET_ENGINES.md`。

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
- `docs/refactor_plan.md`：当前重构阶段和已完成项
- `docs/design_patterns_en.md`：pattern 定义说明
- `docs/PAIR_RANKING.md`：双靶点必须同时成功时的 PairRank 排序规范
- `docs/ENVIRONMENT.md`：Python 环境和模型转换
- `docs/OFFTARGET_ENGINES.md`：Off-target 引擎说明
- `docs/GENOME_INDEX.md`：本地 `.ggi` 索引格式、构建和 native/Python 关系
- `example/engine_benchmark_small/REPORT.md`：各 Off-target 引擎的基准结果与 auto 规则依据
- `docs/MODELS.md`：模型文件状态
- `docs/TNPB.md`：TnpB/TEEP 模型公式、适用范围和参考文献（结果字段见 `docs/OUTPUTS.md`）

## 修改约定

1. 优先复用 `shared/` 下的模块，不要在 GUI 中复制命令行逻辑。
2. 新增或修改 pattern 时，先更新 `shared/design/pattern_spec.py`，再由 `pattern_runner.py` 接入。
3. 修改目录结构、命令或运行约定后，同步更新本 README 和 `docs/`。
4. 不要依赖外部 skill 自动跟踪代码变化；skill 只负责指向本 README 和关键文档。
5. library 管线（`shared/design/library_pipeline.py`，以及调用它的入口：`main.py` 的 Library 标签页、`unified_gui.py`、`webapp/`）已废弃：保留代码只是为了不影响其它功能正常使用，不继续开发，也不需要维护；不要为它修 bug、补测试或做重构。
