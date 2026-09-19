# 输出结果说明

检查日期：2026-09-16。本文以当前仓库实现为准（`shared/output/`、
`shared/scoring/scoring.py` 及各流程写出器），是结果文件与结果列的单一入口。
模型公式、引擎约束和排序策略细节仍以各自专题文档为准。

本文替代此前分散在多处的输出描述：`docs/TNPB.md` 第四章、
`docs/SCORING_GUIDE.md` 的字段章节、`docs/PAIR_RANKING.md` 的输出小节、
`docs/GUI.md` 的文件清单、`docs/CRISPAI.md` 的回填列说明。

## 一、通用规则

1. **每次评分流程都会写三类主表**
   - `query_scores_sorted.tsv`：每个候选一行，按该流程的主排序排列；
   - `unique_guides.tsv`：按唯一序列去重后的同一批列，需开启 `--unique-guides`；
   - `top_offtargets.tsv`：每个 query 排名靠前的命中位点，不含模型评分列。
2. **全空列自动隐藏**：写出前逐列检查，整列全空（`None`、空串、纯空格）的列不写出；
   数值 `0` 不算空。因此同一次运行的实际列集合取决于勾选的模型、是否提供
   direct repeat、是否运行 `--unique-guides` 或注释。
3. **模型列命名**：勾选的每个模型单独成列，`on_target_score_<model>` /
   `off_target_specificity_<model>`（例如 `on_target_score_cropsr`、
   `off_target_specificity_cfd`）。模型名称不单独占列：
   `on_target_model_<model>`、`off_target_model_<model>`、`rna_model`、
   `omega_model` 等只存在于内部评分结果，单 motif / 双靶候选表不再输出。
4. **主分列**：单 motif 与 unique guide 表保留不带后缀的 `off_target_specificity`，
   含义是第一个勾选 off-target 模型的主分，也是这两张表的排序依据。
   Pattern A 主表没有该列，排序由 PairRank 列表达。
5. **MM 列随预算变化**：`max_mismatch=N` 时输出 `MM0` 到 `MMN`，最后一列是合并桶，
   表示错配数 `>= N`。预算 0/1/2 分别只输出 `MM0`、`MM0-MM1`、`MM0-MM2`。
   单 motif 用大写 `MMn`；Pattern A 的左右侧列使用小写 `left_mm0` / `right_mm0`。
6. **BED / XLSX**：BED 给出候选区间，XLSX 由对应 TSV 转换，需显式开启 `--xlsx`。
7. **运行标签**：GUI 的 Run label 会把主表重命名为 `<label>_scores.tsv`、
   `<label>_guides.tsv`、`<label>_offtargets.tsv`，列内容不变。

## 二、输出文件清单

### 2.1 单 motif（`basic/`）

| 文件 | 内容 |
| --- | --- |
| 提取结果 TSV | 三列 `qid` / `sequence` / `positions`，首行为 `# motif=... flanking_len=... side=...` 注释 |
| `blast_results.tsv` | 搜索层命中（中间文件；MM 统计与评分只接受覆盖完整 query 的比对） |
| `query_scores_sorted.tsv` | 每个候选一行；含 `pos_id`、`seq_id`、`strand`、`motif_pos`、`qid`、`query_seq` 与全套评分列 |
| `unique_guides.tsv` | 按 `qid` 去重；用 `position_count` 取代 `pos_id` |
| `top_offtargets.tsv` | `qid, position_count, rank, target, start, mismatch, annotation` |
| `query_scores.bed` | `seq_id, motif_pos, motif_pos+len(query_seq), pos_id, 分数, strand`；分数为 `1/off_target_specificity`，越高表示风险越大 |

### 2.2 Pattern A（`Target_xbp_Target/`，motif-gap-motif）

| 文件 | 内容 |
| --- | --- |
| `query_scores_sorted.tsv` | 每个候选一行；左右两侧列分别加 `left_` / `right_` 前缀 |
| `unique_guides.tsv` | 按侧、按 flank 序列去重，带 `side`、`position_count`、`target_start/end` |
| `top_offtargets.tsv` | `qid, position_count, rank, target, start, mismatch, annotation` |
| `query_scores.bed` | `seq_id, compound_start, compound_end, pos_id, 1/(1+pair_offtarget_burden), strand`；越高表示 pair 风险越低 |
| `<主表名>.queries.fa` | 内部查询序列（完整拼接序列）；TSV 不再输出 `query_seq` 和 `gap_seq` |

Pattern A 的坐标列：`left_target_start` / `left_target_end` /
`right_target_start` / `right_target_end`（0-based 半开区间）、`left_pos`、
`right_pos`、`gap`、`compound_start`、`compound_end`、`left_strand`、
`right_strand`。不再输出旧的 `left_rank` / `right_rank`。

### 2.3 Y-ZBP（`Target_xbp_Y_zbp_Target/`）

| 文件 | 内容 |
| --- | --- |
| `scores.tsv` | 每侧一行：`occurrence, side, y_chrom, y_start, y_end, y_strand, y_seq, qid, motif_seq, distance, ...` |
| `scores.sorted.tsv` | 在 `scores.tsv` 基础上追加 PairRank 列、`conditional_rank` 与 `distance_score`；`rank` 取 `pair_rank`，条件或被拒的行取 `conditional_rank` |
| `unique_guides.tsv` | 按 `motif_seq` 去重，带 `occurrence_count`、`score` |
| `top_offtargets.tsv` | `qid, rank, target, start, mismatch, bitscore, annotation` |
| `scores.bed` | `chrom, start, end, name, 分数, strand`；分数等价于该侧特异性，越高越好 |

### 2.4 索引与数据准备

| 文件 | 内容 |
| --- | --- |
| `<prefix>.ggi` | 二进制索引：contig 表 + k-mer offsets + 扁平位置数组（只存正链） |
| `<prefix>.json` | 元数据：版本、`k`、`genome_fingerprint`、contig、构建时间与内存报告 |
| `<prefix>.lock` | 构建期的排他锁，避免共用输出目录时覆盖正在读取的索引 |
| `index_report.json` | `k, total_bases, valid_kmer_positions, build_time_s, memory_peak_mb, memory_limit_mb, estimated_peak_mb, observed_peak_mb, index_bytes, reused, search_time_s, search_memory_peak_mb, guides, hits` |
| `download_info.json` | 数据准备阶段的下载记录 |
| Target / Mask FASTA | 数据准备阶段提取的靶序列与屏蔽序列 |

## 三、结果列说明

### 3.1 公共统计列

| 列 | 含义 |
| --- | --- |
| `rank` | 写出器自己的行序：单 motif / unique guide 表按 `off_target_specificity` 降序；Pattern A 是 PairRank 分组后的行序号；Y-ZBP 取 `pair_rank` 或 `conditional_rank` |
| `nuclease` | 本次评分的核酸酶类型（TnpB 为 `tnpb`） |
| `total_matches` | 搜索后端返回的当前 query 命中数 |
| `valid_matches` | 排除屏蔽/重复区域后参与统计与评分的命中数 |
| `sum_mismatch` | 有效命中的错配总数 |
| `MM0` … `MMn` | 各错配桶；最后一列为 `>= n` 的合并桶，`n = max_mismatch` |
| `GC-content`、`GC-hint` | query 的 GC 百分比与程序内的低/通过/高提示 |
| `Self-complementarity`、`Self-comp-hint` | 最长反向互补长度及提示；计算范围可能覆盖完整 query window，与 TnpB 的 `guide_structure_penalty` 不是同一个量 |
| `legacy_total_score` | 旧版匹配压力分（`10*MM0 + 1*(MM0+MM1) + 0.1*...`）；不是 0-1 分数，不能与 `off_target_specificity` 直接比较，不建议用于最终排序 |
| `pos_id`、`seq_id`、`strand`、`motif_pos`、`qid`、`query_seq` | 单 motif 的位置与序列列；Pattern A 用 `left_*` / `right_*` 替代 `query_seq` |
| `Annotation`、`Nearest-TSS`、`Isoforms`、`Downstream-ATG` | 传入注释 GFF 时的注释列；无注释时整列隐藏 |

`MM0` 统计的是覆盖完整 query 长度的匹配位点，不是 BLAST 的任意局部短匹配：只比对上
25 bp query 中 16 bp 的 HSP 即使零错配也不计入。若 `MM0` 达到几十甚至几百，优先检查
低复杂度/重复序列、PAM 是否开启，以及是否误用了修复前的旧搜索结果文件。

### 3.2 特异性与 on-target 分数列

| 列 | 含义 |
| --- | --- |
| `off_target_specificity` | 主分，值越大越特异；1 表示除预期位点外没有额外相似位点 |
| `off_target_specificity_<model>` | 每个勾选 off-target 模型的独立结果；`crispai` 作为第一个模型时其值同时覆盖主分 |
| `on_target_score_<model>` | 每个勾选 on-target 模型的独立结果；单 motif 表没有不带后缀的 `on_target_score` 列 |
| `crispai_aggregate_score` | crispAI 上游原始聚合值，用于核对；换算关系为 `off_target_specificity_crispai = 1/(1+aggregate)` |

特异性聚合统一为 GuideScan2 风格 `1 / (1 + sum(模型分数))`；存在 1 个主要目标位点时
先减掉完全匹配位点的贡献，因此分数反映除目标位点外的额外风险。CFD 使用位置特异错配
权重乘积再乘 PAM 权重，实际传入的是靠近 spacer 的 2 nt（`NGG` 用 `GG`、`NAG` 用
`AG`），因此 `guidescan2_nrg` 不会把 NAG 当成 NGG。

### 3.3 bulge 与校准列

| 列 | 含义 |
| --- | --- |
| `input_offtargets`、`substitution_offtargets` | 进入评分的位点数，以及其中替换型位点数 |
| `bulge_hits`、`scored_bulge_hits`、`unscored_bulge_hits` | 带 gap 的命中数；恒有 `bulge_hits == scored_bulge_hits + unscored_bulge_hits` |
| `bulge_risk_sum` | bulge 风险的保守累加值 |
| `bulge_score_method` | bulge 评分方法标识，当前为保守 penalty `conservative_bulge_v1` |
| `calibration_status` | 校准状态；`cfd` 等模型只处理 substitution-only hit，bulge、Cas12a/TnpB 路径与通用启发式（`identity_heuristic` / `nuc_features`，如 `custom` 下的 `rules`）标记为 `uncalibrated` |

### 3.4 TnpB 与 RNA 子特征列

只随对应 on-target 模型出现，未选模型不会产生这些列。

| 列 | 含义 |
| --- | --- |
| `on_target_score_omega` | 本地 omegaRNA 规则分（0-1 启发式，不是实验校准的编辑效率） |
| `on_target_score_teep` | 在线 TEEP 的 CNN/RNN 平均值除以 100；网络失败时回退通用启发式，不会回退 omega |
| `off_target_specificity_identity` | TnpB 使用的序列同一性启发式 |
| `spacer_len_score` | guide 长度规则分（14-18 nt 为 1，12-20 nt 为 0.75，其余 `1-abs(L-16)/16`） |
| `guide_structure_penalty` | guide 自身发夹/反向互补惩罚，越低越好 |
| `repeat_hairpin_score` | direct repeat 发夹分；没有 direct repeat 时为空并可能整列隐藏 |
| `AT_score` | 仅当该侧 preset 为 `tnpb` 时输出；单 motif 用 `AT_score`，Pattern A 用 `left_AT_score` / `right_AT_score` |
| `guide_mfe`、`guide_accessibility`、`target_accessibility`、`dr_spacer_duplex_mfe`、`dr_spacer_penalty`、`perturbation_mfe`、`dr_source` | Cas13 RNA 子特征，仅随 RNA on-target 模型出现；有 ViennaRNA 时用结构计算，否则用启发式 |

公式与适用边界见 `docs/TNPB.md` 第二章与 `docs/MODELS.md`。

### 3.5 PairRank 列（双靶）

Pattern A 主表与 Y-ZBP 的 `scores.sorted.tsv` 会写入以下列：

| 列 | 含义 |
| --- | --- |
| `pair_id` | 稳定的 pair 标识，用于确定性排序 |
| `pair_rank` | 通过硬门槛的 pair 名次；相同排序键并列同名次 |
| `pair_rank_status` | `pass` / `conditional` / `rejected` |
| `pair_rank_mode` | 当前固定为 `prediction_only` |
| `pair_rank_key` | 实际使用的排序键 |
| `pair_activity_tier`、`left_activity_tier`、`right_activity_tier` | on-target 证据等级 A/B/C；pair 等级取两侧较弱者 |
| `left_eligible_model_count`、`right_eligible_model_count` | 该侧可用的适用模型数量 |
| `pair_offtarget_burden` | 两侧脱靶负担上界之和 `B_pair+`，越小越好 |
| `pair_max_offtarget_upper` | 最大单点脱靶活性上界 `M_pair+`，越小越好 |
| `pair_high_risk_count` | 达到高危阈值的额外位点数 `H_pair` |
| `pair_activity_disagreement` | 两侧模型百分位排名的最大差值 `D_pair`，越小越一致 |
| `pair_compatibility_penalty` | 软性警告数量（距离警戒区、递送不确定等），越小越好 |
| `pair_gate_reasons` | 被拒或条件通过的原因列表（分号分隔） |
| `conditional_rank` | `conditional` 组内部的并列名次 |

判断顺序：先看 `pair_rank_status`，`rejected` 直接排除；再看 `pair_rank` 与
`pair_activity_tier`；随后比较 `pair_offtarget_burden`、`pair_max_offtarget_upper`、
`pair_high_risk_count`；最后用 `pair_activity_disagreement` 与
`pair_compatibility_penalty` 做同分取舍。阈值与硬门槛定义见 `docs/PAIR_RANKING.md`。

### 3.6 旧列与不再输出的内容

以下列不会再出现在单 motif / Pattern A / Y-ZBP 候选表中，看到它们说明是旧结果文件：

- `combined_score`、`left_rank` / `right_rank`
- `on_target_model_<model>`、`off_target_model_<model>`、`on_target_model`、
  `off_target_model`、`rna_model`、`omega_model`
- `reference_only`、`reference_note`、`rule_source`、`rule_reference`、
  `rule_summary`、`subtype_note`、`tnpb_subtype`
- 固定子特征列 `cfd_specificity`、`crispr_m_off_target`、`deepcrispr_off_target`、
  `crispai_off_target`、`deepcas12a_on_target`、`deepcpf1_on_target`、
  `tiger_on_target`、`tiger_off_target`

这些字段部分仍保留在内部评分结果中，但不再属于候选表契约。
`tools/score_crispai.py` 单独回填时会在原 TSV 上追加 `crispai_aggregate_score`
与 `crispai_off_target`，属该工具的独立行为。

`docs/PAIR_RANKING.md` 第四章的 `experiment_calibrated` 模式（`r_left`、`r_right`、
`r_both`、`E_both_LCB`、`kappa_pair`、`pair_offtarget_burden_measured` 等）目前只是
规范草案，代码尚未实现，当前不会输出这些列。已下线的引擎（bowtie2、casoffinder）
与已删除的 `docs/EXPERIMENTAL_OUTPUTS.md` 涉及的文件和列同样不再适用。

## 四、按结果判断的推荐顺序

1. 确认运行使用了正确的核酸酶与模型组合；未勾选的模型不会产生列。
2. 先看对应模型的 `off_target_specificity_<model>`，优先保留接近 1 的候选。
3. 检查 `MM0`：开启 PAM 过滤时普通 unique guide 通常为 1；明显偏高时先排查重复
   序列、PAM 设置，以及搜索是否重新运行过。
4. 在特异性相近的候选中，再比较 `on_target_score_<model>`。
5. 单 motif 按 `off_target_specificity` 查看；双靶按 `pair_rank_status`、`pair_rank`
   与风险字段查看，并人工抽查 `top_offtargets.tsv`。
6. 所有启发式与 AI 分数只用于相对排序，不能当作绝对编辑效率。

影响 MM 统计的参数：`Require PAM`（关闭时无 PAM 的相似序列也计入）、
`max_mismatch`（决定保留范围与 `MMn` 档位）、`Mask FASTA`（屏蔽区域命中不计入
`valid_matches`，双靶下作为 forbidden hit 拒绝该 pair）、`Repeat FASTA`（不参与普通
风险聚合，但同样作为 forbidden hit 传入 PairRank）。

## 五、相关文档

- `docs/SCORING_GUIDE.md`：评分模型公式与特异性聚合细节
- `docs/TNPB.md`：TnpB/omega/TEEP 公式、边界与参考文献
- `docs/PAIR_RANKING.md`：PairRank 阈值、门槛与实验校准模式规范
- `docs/MODELS.md`：模型文件、格式与可用状态
- `docs/OFFTARGET_ENGINES.md`：脱靶引擎约束与选择规则
- `docs/CRISPAI.md`：crispAI 外部环境与回填流程
- `docs/GENOME_INDEX.md`：索引构建与复用
