# 统一 GUI 工作台

运行 `python main.py` 直接打开统一工作台，按工作流步骤组织界面。
不再单独保留 `--legacy` 入口，也不再需要分别打开三个 Motif 独立窗口。

主控制台原来的公共功能已并入工作流：数据准备、Target/Mask、模型下载、
搜索、评分、导出都由统一工作台串联完成。

## 布局

```text
顶部   工作流步骤条：Back / Next、当前步骤
步骤 0 Data prep / Models
步骤 1 Motif analysis
步骤 2 Results / Output
底部   进度条、日志
```

## 工作流步骤

1. Data prep / Models：下载基因组与注释、补 UTR、提取 Target/Mask、模型下载。
   Models 页签按效应蛋白（Cas9 / Cas12a / TnpB）分组展示本地模型，
   每组默认收起，点击组头展开后再下载 / 删除。
2. Motif analysis：打开 Pattern Designer，由 Design Pattern 选择 Basic、Complex 或 Y/ZBP 模式。
3. Results / Output：查看运行摘要、输出文件和日志；参数统一在 Pattern Designer 中设置。

打开 Pattern Designer 时会自动带入 Data prep 中填写的 Genome FASTA、
Annotation GFF3、Output Directory、BLAST db，以及已提取的 Target/Mask FASTA。
Annotation GFF3 为空时打分表会隐藏 `Annotation` / `Nearest-TSS` / `Isoforms` /
`Downstream-ATG` 四列。若尚未提取 Target FASTA，点击 Find Targets 会弹出
明确提示，而不会静默无反应。

## Pattern Designer 参数区

参数分散在 Pattern Designer 的左 / 中 / 右三列与底部 Run Settings 中，与网页版一致：

- 系统预设：custom、cas9、cas12a/b、cas13、crispri、tnpb
- Nuclease / TnpB 亚型
- Spacer 长度、PAM、PAM 侧
- 脱靶引擎：exact、indexed、blast、gggenome、auto
- 最大错配、Max Bulge（engine default / 0 / 1）、要求 PAM
- 索引前缀、BLAST db、基因组 build
- On-target / Off-target 模型（per-side）：各 TAM 组的模型行按该侧核酸酶
  自适应显示对应选项；模型行是多选下拉框，勾选的每个模型都会单独计算
  并写入 `on_target_score_<model>` / `off_target_specificity_<model>` 列。
  双靶 pattern 使用 PairRank 作为主排序；单靶 pattern 按
  `off_target_specificity` 排序，旧 `combined_score` 已删除。选择
  `custom` 时，下拉框自动包含所有预设的模型，并按蛋白类型显示
  `[Cas9]` / `[Cas12a]` / `[Cas13]` / `[TnpB]` / `[General]`；新增预设模型
  也会自动并入。`nuclease == custom` 时所有模型都可调用，并按参考模型处理
- Cas13 DR 序列、靶 RNA、CRISPRi TSS 距离

点击“应用”预设后，spacer、PAM、PAM 侧等字段会自动填充。
Pattern Designer 使用左 / 中 / 右三列：
- 左列：公共输入 + Left TAM
- 中列：Middle 设计 + 结构预览
- 右列：Right TAM
每个 TAM 组有自己的 System Preset，可独立应用预设并选择
`Use for Run`；公共文件输入只保留一份，放在左列。
每个 TAM 组底部还有一条模型行：On-target 模型按核酸酶给出选项（cas9:
cropsr；cas12a: rules / deepcas12a / deepcpf1；cas13: rna_rules / tiger；
tnpb: omega / teep，其中 omega 是离线 omegaRNA 规则，teep 是 ISDra2 TnpB
的在线参考模型），Off-target 模型按核酸酶展示：cas9 为 cfd / crispr_m /
deepcrispr / crispai，cas13 为 pfs / identity / tiger，其他侧为 rules 或
identity。`crispai` 与其他 Off-target 模型一样通过多选下拉框选择；作为第一个
模型时参与主分排序，作为后续模型时只输出独立的 crispAI 得分列。TnpB 侧把
on-target 选择映射为该侧 `reference_only_model`
（`omega` -> `none`，`teep` -> `teep`），仅作在线参考。
左右两侧的 PAM/TAM motif、side 和 require 现在各自独立保存；在 Pattern A
与 Y-ZBP 的评分阶段，`analyze_complex_scores.py` / `blast_combined.py` 会分别
按左右侧 PAM 做脱靶搜索与过滤。单侧模式仍使用全局 PAM，三个字段都有回退
到全局值，旧的命令行参数保持兼容。
Pattern A 提取时，左右 motif 会各自在正链和负链上搜索，
`++`、`+-`、`-+`、`--` 四种组合都会保留，结果中含
`left_strand` 与 `right_strand` 两列。
候选结果新增
`left_target_start/left_target_end`、`right_target_start/right_target_end`
四个 0-based 半开区间坐标。TSV 不再输出 `query_seq` 和 `gap_seq`，
完整查询序列保存在同名 `.queries.fa` 内部文件中供导出等内部流程使用，
不再参与评分；
左右 motif 序列与 `left_flank_seq/right_flank_seq` 保留。
Pattern A 评分不再把整条拼接序列当作 guide，而是对左右两个
`flank_seq` 分别做脱靶搜索和打分；`query_scores_sorted.tsv` 中每个候选
保留一行，分数分别放在 `left_*` 与 `right_*` 两套列里。
结果不再输出旧的 `left_rank` / `right_rank`。双靶总排名使用
`prediction_only` PairRank，输出 pair 风险、证据等级和门槛原因。
引擎、最大错配、seed、索引前缀、GC、基因组 build、Hard Filter 等
公共运行参数放在底部 Run Settings。PAM Mode 可选择 `strict_ngg` 或
`guidescan2_nrg`；Max Bulge 留空时采用 engine-specific default。
双靶模式还会显示 `PairRank prediction_only policy` 设置区，必须显式填写
`e_high`、`e_min`、`e_fail`、`delta_default`、`b_low`、`b_high`、
`m_low`、`m_high`、`h_risk`、`h_max`。缺少任一项时 readiness 会阻止运行，
不会使用隐藏的全局固定阈值。
Nuclease、TnpB 亚型、Require PAM 与 On/Off-target 模型由各 TAM 组决定：前者
来自该组 System Preset，后两者在该组模型行内单独选择（On-target 默认按
核酸酶取 cas9: cropsr、cas12a: rules、cas13: rna_rules、tnpb: omega，
Off-target 默认按侧使用 cas9: cfd、cas12a/b: rules、cas13: pfs、tnpb: identity；模型行不再提供 auto，传统规则显示 `[rule]`
标识，规则见 `docs/SCORING_GUIDE.md`）；模型行支持多选，所有勾选项
都会输出各自的模型得分列；非 Cas9 侧会忽略 Off-target
模型，走各自的 preset/identity 规则。TnpB 侧把 on-target 选择映射为该侧
`reference_only_model`，单侧用 `reference_only_model`，双靶用
`left_reference_only_model` / `right_reference_only_model`，随运行一起传给
评分流程。
运行级 `nuclease`（传给 `analyze_scores.py` 的 `--nuclease`，也是结果表
`nuclease` 列的取值）取生效侧 System Preset 的 nuclease。`cas9` 是表单默认
值，所以在非 cas9 预设下会被预设覆盖——不会出现 `--preset tnpb` 却配
`--nuclease cas9`、把 TnpB 结果显示成 cas9 的情况（桌面端选预设即时应用，
网页端选预设同样即时应用，未点 `Apply` 也不会让该列失真）；反过来，显式选择
的非 cas9 值（例如批量 `shared.nuclease`）优先于默认的 cas9 预设，`custom`
预设没有系统规则，始终沿用表单里的显式值。该规则统一收敛在
`system_presets.resolve_run_nuclease()`，前端、批量和命令行共用。
窗口默认最大化（1440x900 兜底）；Common Inputs、Middle、Run Settings、Run Log
均可折叠，候选结果移入统一工作台的 `Results / Output` 页查看。
Run Settings 下方常驻进度条：流程输出 `PROGRESS:` 百分比时按真实进度显示，
否则自动切换为不定进度动画，避免看起来像卡住。
脱靶搜索和评分阶段输出的计数消息不改动百分比数值，进度条仍由阶段百分比驱动。
空闲时会自动检查运行所需参数：齐了显示绿色 `Ready`，缺参数时进度条变红并
用英文提示缺失项（如 `Missing: Search FASTA is required`）；运行中为蓝色。
右上角流程已拆成两步：`Find Targets` 只做候选提取，`Score & Off-target`
在已有提取结果上继续做脱靶搜索和打分；未先提取时点打分会提示先运行
`Find Targets`。Run Settings 中选择的 engine（exact / indexed / blast /
gggenome / auto）现在会直接用于这两步的脱靶搜索；
exact 在大基因组上会自动回退到 blast，避免直接建立超大内存索引。

## 操作

| 按钮 | 作用 |
| --- | --- |
| 构建索引 | 运行 `tools/build_genome_index.py` 并自动填入索引前缀 |
| 打开输出 | 打开输出目录 |
| 刷新结果 | 重新读取结果摘要和输出文件列表 |

输出文件支持双击打开。

每次运行的中间产物在本运行子目录 `<output_dir>/<run_label>/`，完整参数见
`<output_dir>/<run_label>_params.json`。

## 专用工具

统一工作台不再需要分别打开三个 Motif 独立窗口：

- Motif 分析：`Motif analysis -> Pattern Designer`，在 Design Pattern 中选择 Basic、Complex 或 Y/ZBP。
- Data prep / Models：统一工作台内嵌页签，保留数据准备、Target/Mask、模型下载等原功能

Pattern Designer 本身只提供 `Find Targets` 和 `Score & Off-target`。

对应的 GUI 模块仍保留为可复用面板：`basic/gui.py`、
`Target_xbp_Target/gui.py`、`Target_xbp_Y_zbp_Target/gui.py`，
也可以继续用命令行脚本运行。

## 功能状态

- **Library 出库：已废弃。** `shared/design/library_pipeline.py` 及其预检与工具函数
  不再开发也不再维护；`Results / Output` 页的 `一键出库` 按钮已置灰停用，
  按钮背后的代码保留只为不影响其它功能，相关既有失败不再修复。
- **多任务/批量：CLI 批量支持（见 `docs/BATCH.md`）；GUI 面板暂不支持。**
