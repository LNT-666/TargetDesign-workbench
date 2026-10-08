# 评分说明

本文说明脱靶搜索后结果表里的评分字段、MM 计数含义，以及如何判断候选的优劣。
结果文件清单、通用列与 PairRank 列见 `docs/OUTPUTS.md`。

## 一、命中统计字段

`total_matches`、`valid_matches`、`sum_mismatch`、`MM0` ... `MMn` 的字段定义，
以及 `max_mismatch` 对输出列的裁剪规则，见 `docs/OUTPUTS.md` 的「3.1 公共统计列」。
其中 `MM0` 统计的是“满足完整 query 长度的匹配位点”，不是 BLAST 的任意局部短匹配。

## 二、MM0 应该有多少

对于一条普通的 unique guide，如果开了 PAM 过滤：

- 目标位点本身通常是 1 个，因此 `MM0` 通常等于 1；
- 如果序列在基因组里有同源重复、多拷贝位点，`MM0` 会大于 1；
- 如果结果里 `MM0` 达到几十甚至几百，优先检查 query 是否落在低复杂度/重复序列，或者搜索结果是否仍来自修复前的旧 BLAST 结果文件。

旧版本曾把“只覆盖 query 前 15-19 bp 的 BLAST 局部 HSP”误当作完整命中，导致 MM0 被严重灌高。使用本次修复后的代码时，请重新运行脱靶搜索，不要直接分析旧 `blast_results.tsv`。

## 三、特异性分数

### CFD specificity

对每个 off-target 计算单点 CFD 分数：

```text
CFD(off-target) = 错配位置权重乘积 x PAM 权重
```

完全匹配且 PAM 正确的位点 CFD 接近 1；错配越靠近 PAM、越多错配，CFD 越低。

搜索保留完整 3 nt PAM。评分时实际传给 `PAM_SCORES` 的是靠近 spacer 的
2 nt：`NGG` 使用 `GG` 权重，`NAG` 使用 `AG` 权重。因此
`guidescan2_nrg` 模式不会把 NAG 错当成 NGG。

### Bulge hit 评分

带 gap 的 hit 不再被截成等长序列后当作替换错配评分。搜索层必须传入
`aligned_guide` / `aligned_target`、`rna_bulges`、`dna_bulges`、CIGAR 和
alignment 坐标。当前 `cfd` 等模型只处理 substitution-only hit；bulge hit
使用明确版本化的保守 penalty `conservative_bulge_v1`，并将
`calibration_status` 标记为 `uncalibrated`；走通用启发式（`identity_heuristic` / `nuc_features`，例如 `custom` 下选 `rules` / `identity`）的得分同样标记为 `uncalibrated`，因为它们没有留出实验校准数据。

每条 guide 的输出和 summary 包含：

```text
search_hits, scoring_hits_received, scoring_hits_excluded,
input_offtargets, substitution_offtargets,
bulge_hits, scored_bulge_hits, unscored_bulge_hits, bulge_risk_sum
```

发生 bulge 时 `bulge_hits == scored_bulge_hits + unscored_bulge_hits`。
Cas12a/TnpB 不套用 Cas9 CFD 的校准结论；其 bulge 结果统一标记为
`uncalibrated`；`custom` 下走通用启发式的行同样标记 `uncalibrated`，只有真正使用 `cfd` 等已校准参考模型的 substitution-only 结果才是 `calibrated_reference`。

总特异性按 GuideScan2 风格聚合：

```text
off_target_specificity = 1 / (1 + sum(CFD))
```

假设存在 1 个主要目标位点时，会先把完全匹配位点的贡献减掉 1 再聚合，因此特异性反映“除目标位点外还有多少额外风险”。

### 其他特异性模型

在复杂（Pattern A/B）与 Y-ZBP 双靶设计中，`on_target_model` / `off_target_model`
按侧生效：左、右各自选择模型；非 Cas9 的一侧会忽略 Off-target 选择，走各自的
preset/identity 规则。TnpB 的 on-target 通过该侧的 `reference_only_model`
（单侧为 `reference_only_model`，双靶为 `left_reference_only_model` /
`right_reference_only_model`）传递：默认走离线 omegaRNA 规则
（`reference_only_model="none"`），仅当该侧把 on-target 选为 `teep` 时将其设为
`"teep"`，TEEP 只作在线参考，不替代默认 omega 路径。

- `cfd`：只使用 CFD 表，最快，适合 Cas9 快速筛选；
- `crispr_m`：使用本地 CRISPR-M NumPy 模型，对每个 guide 的 off-target 批量推理；
- `deepcrispr`：使用 DeepCRISPR portable CNN；
- `pfs`：Cas13 的 PFS + identity 传统规则，不依赖 AI 模型；
- `rules`：通用传统规则入口，Cas9 下等价 CFD，非 Cas9 preset 下走 identity/seed；
- `identity`：序列相似度 + seed 惩罚规则。
- `crispai`：外部 crispAI-aggregate 批量模型。选择后对每条 guide 重跑
  全基因组 Cas-OFFinder + NuPoP/BDM 注释并采样聚合。作为第一个 Off-target
  模型时覆盖 `off_target_specificity`，单 motif 排序和双靶 PairRank
  都会读取该值；作为后续模型时只填充
  `off_target_specificity_crispai` 和 `crispai_off_target` 列；
  环境未就绪或非 SpCas9 时自动回退 CFD。依赖与用法见 `docs/CRISPAI.md`，
  需在 Linux 服务器上运行。
- 非 Cas9 预设（Cas12/Cas13/TnpB 等）通常使用 identity/seed 启发式分数，不再套用 SpCas9 CFD。

Pattern A（Target-xbp-Target）会按 `(flank_qid, strand, model)` 缓存一次
flank 扫描，并对该 guide 的脱靶位点按 PAM 分组执行一次批量深度模型推理。
逐位点活性会在一次扫描中生成，随后同时用于 aggregate specificity 和
PairRank，不再为每个 hit 单独调用 `compute_guide_scores()`。未选择的深度模型
不会被探测或推理；选择 `cfd`、`identity` 或规则模型时不会因为本地存在
CRISPR-M/DeepCRISPR 模型文件而额外运行深度推理。

TnpB 的 off-target 当前直接走 `identity` 相似度规则；公式、是否应用 seed
penalty 以及 PAM/TAM 的生效条件见 `docs/TNPB.md` 的「2.3 `identity` off-target
规则」。

## 四、On-target 分数

### CROPSR / Doench

当输入是标准 30mer（4 nt upstream + 20 nt spacer + NGG + 3 nt downstream）时，使用 CROPSR 的发布系数计算。如果输入比 30mer 长，则滑动 30mer 窗口并取最高分。

On-target 模型按侧选择且随核酸酶过滤：SpCas9 侧为 `cropsr`，
Cas12a 侧为 `rules` / `deepcas12a` / `deepcpf1`，Cas13 侧为
`rna_rules` / `tiger`，TnpB 侧为 `omega` / `teep`
（`omega` 是离线默认的 omegaRNA 规则，`teep` 是 ISDra2 TnpB 的在线参考
模型；选 `teep` 时通过该侧 `reference_only_model` 传给 scoring，仅作参考，
不影响默认 omega 路径）。界面不再提供 `auto`；旧命令行传入 `auto` 仍兼容。
`rules` 只在 `cas12a` / `cas12b` 预设与 `custom` 的候选里出现，SpCas9 预设的 on-target 只有 `cropsr`；界面上 `rules` 与 `identity` 归入 `[General]` 分组，因为它们不绑定特定核酸酶。
`rules`、`rna_rules`、`omega`、`cfd`、`pfs`、`identity` 会显示 `[rule]`
标识，表示它们不是 AI 模型；模型名还会带蛋白分类前缀，如 `[Cas9] [rule] cfd`、
`[Cas12a] deepcas12a`、`[Cas13] tiger`、`[TnpB] [rule] omega`。
`omega`（omegaRNA）与 `teep` 都属于 **on-target 编辑效率规则**，预测的是
TnpB 的引导 RNA 在靶位点上的编辑效率，不是 off-target 特异性评分；脱靶侧
TnpB 当前直接走 identity，不应用 seed penalty。`omega` 是默认的本地确定性
规则；`teep` 是显式选择的在线 TnpBmax/TEEP 模型。TEEP 请求失败时回退通用
启发式，不会自动改用 `omega`。TEEP 的 CNN/RNN 平均值/100 归一化、TAM 和
输出字段限制见 `docs/TNPB.md`。
`deepcpf1` 是 Cas12a/Cpf1 的序列-only CNN 模型，需显式选择；模型未就绪或
输入不是标准 34 bp 上下文时同样回退启发式，并在 `deepcpf1_on_target` 列
保留原始模型输出。

自定义（`custom`）核酸酶的模型下拉框会汇总所有预设的模型：Cas9 的
`cropsr` / `cfd` / `crispr_m` / `deepcrispr` / `crispai`，Cas12a 的 `rules` /
`deepcas12a` / `deepcpf1`，Cas13 的 `rna_rules` / `tiger` / `pfs` /
`identity`，以及 TnpB 的
`omega` / `teep`。选择特定预设训练的模型时会实际调用对应评分逻辑，并以
`reference_only` 标注"未经验证"，不应用于实验决策。`rules`、`identity`
等通用传统规则不标注未验证；`crispai` 作为普通 Off-target 模型选择，
依赖外部 Cas-OFFinder 批量环境。当 `nuclease == custom` 时，所有模型都
允许调用；不满足模型原生蛋白或输入要求时，按该模型的 fallback 规则计算。在 `custom` 下 `rules` 不进入参考模型路径：on-target 走 `heuristic_on_target_score()`（记为 `rules_heuristic`），off-target 走 identity/seed 相似度（记为 `identity_heuristic`），两者都不标 `reference_only`。

双靶（Pattern A / Y-ZBP）中左右侧的 PAM motif、PAM side 与 require 也按侧
生效：`left_*` / `right_*` 参数分别用于该侧脱靶搜索和过滤；单侧模式继续
使用全局 `pam_motif` / `pam_side` / `require_pam`。左右侧
`left_nuclease` / `right_nuclease` 为 `custom` 时，该侧同样进入通用模型
分派；所有已选模型都可调用并按 `reference_only` 处理。

### 启发式 fallback

输入不满足 30mer 条件时，退化为 GC、seed GC、homopolymer、序列复杂度组成的 0-1 启发式分数。

## 五、综合排序

当前版本不再生成 `combined_score`：

- `off_target_specificity` 越高越好，1 表示没有额外 off-target 风险；
- `on_target_score` 越高越好；
- 单 motif、unique guide 和 library 输出按 `off_target_specificity`
  降序排名；
- Pattern A / Y-ZBP 双靶点使用 `prediction_only` PairRank 分组和排名，
  具体硬门槛、风险等级和排序键见 `docs/PAIR_RANKING.md`。

Pattern Designer 的模型选择支持多选。最终结果表中的每个勾选 on-target 模型
输出 `on_target_score_<model>`，每个勾选 off-target 模型输出
`off_target_specificity_<model>`；列命名与内部字段的取舍见 `docs/OUTPUTS.md`
的「3.2 特异性与 on-target 分数列」「3.6 旧列与不再输出的内容」。

`AT_score` 仅在对应 system preset 为 `tnpb` 时计算和输出。单 motif 使用
`AT_score`，Pattern A 使用 `left_AT_score` / `right_AT_score`，Y-ZBP 的
逐侧行使用 `AT_score` 配合 `side` 列；其他 preset 不生成对应列。

`legacy_total_score` 是旧版匹配压力分，公式为：

```text
score = 10*MM0
      + 1*(MM0+MM1)
      + 0.1*(MM0+MM1+MM2)
      + 0.01*(MM0+MM1+MM2+MM3)
      + ...
```

该值不是 0-1 标准化分数，也不能直接和 `off_target_specificity` 比较；它更偏向表示“相似/完美脱靶总量”，一般不要用它做最终排序依据。

当前单 motif 与复杂模式的候选表只输出勾选的
`on_target_score_<model>` / `off_target_specificity_<model>`，以及未列入
`OUTPUT_EXCLUDED_COLUMNS` 的可用子特征。TnpB 常见输出包括
`on_target_score_omega`、可选的 `on_target_score_teep`、
`off_target_specificity_identity`、`spacer_len_score` 和
`guide_structure_penalty`；`omega_model` 只在 `library_scores.tsv` 中保留。
完整字段和公式见 `docs/TNPB.md`。

## 六、常见判断流程

1. 先看对应模型的 `off_target_specificity_<model>`，优先保留接近 1 的候选；
2. 看 `MM0`：应接近 1；明显偏高时检查重复序列、PAM 是否开启、是否重新搜索过；
3. 看对应模型的 `on_target_score_<model>`，在特异性相近的候选中取编辑效率更高的；
4. 单 motif 按 `off_target_specificity` 查看；双靶点按 PairRank 的
   `pair_rank_status`、`pair_rank` 和风险字段查看，并人工抽查
   `top_offtargets.tsv`。

## 七、影响 MM 统计的参数

- `Require PAM`：开启后只统计带有效 PAM 的位点；否则无 PAM 的相似序列也会进入 MM 计数；
- `max_mismatch`：只保留错配数不超过该值的命中，并决定结果表输出到 `MMn` 的哪一档；
- `Mask FASTA`：落入屏蔽基因区域的命中不计入 `valid_matches`，也不会参与
  聚合特异性评分；双靶流程会把它作为 forbidden hit 传入 PairRank 并拒绝该 pair；
- `Repeat FASTA`：命中不参与普通脱靶风险聚合，但会作为 forbidden hit
  递给双靶 PairRank；
- BLAST 引擎只接受覆盖完整 query 的比对，局部短 HSP 不参与 MM 和评分。
