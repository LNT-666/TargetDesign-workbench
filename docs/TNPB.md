# TnpB 模型与输出说明

检查日期：2026-09-12。本文以当前仓库实现为准，说明 TnpB 评分路径、
适用边界、参考文献和结果字段。

## 一、结论

本程序的 TnpB 评分不是单一神经网络：

- 默认 on-target 路径是本地、确定性的 `omega` / `omega_rna_rules` 规则。
  它不是从实验数据训练的 TEEP 模型，也没有可下载的权重文件。
- `teep` 是用户显式选择的在线参考路径。它调用 `https://www.tnpb.app/`
  上的 TEEP 模型，程序把服务返回的 CNN 和 RNN 预测值分别除以 100 后取平均，
  归一化到 0-1。
- TnpB 的 off-target 路径固定为 `identity` 启发式，不调用 TEEP，
  也不是针对 TnpB 实验数据训练的特异性模型。
- 单 motif、unique guide 和 library 输出按 `off_target_specificity`
  降序排名；Pattern A / Y-ZBP 使用 `prediction_only` PairRank。
  `combined_score` 已从实现和输出中删除。
- TnpB 默认模型组合是 `identity` + `omega`；只有显式勾选 `teep` 时，
  结果才会额外出现 `on_target_score_teep`。

## 二、模型路径

| 界面/模型键 | 类型 | 是否默认 | 网络 | 输入 | 输出 | 适用性 |
| --- | --- | --- | --- | --- | --- | --- |
| `omega` | 本地确定性规则 `omega_rna_rules` | 是 | 否 | 引导序列，可选 direct repeat | 0-1 on-target 编辑效率启发式分数 | 离线可用；未按实验编辑效率校准 |
| `teep` | 在线深度学习预测器 TEEP | 否，需显式选择 | 是 | 20 nt 左右的 ISDra2 TnpB 引导序列 | CNN/RNN 原始 0-100 预测的平均值，再除以 100 | 面向 ISDra2 TnpBmax/TEEP 训练体系；其他 TnpB 仅作参考 |
| `identity` | 序列同一性启发式 | on-target 之外默认 | 否 | guide 与 off-target spacer | 0-1 off-target specificity | 通用近似值；TnpB 当前没有专用 off-target 学习模型 |

### 2.1 `omega` / omegaRNA 本地规则

实现位置：`shared/scoring/tnpb_scoring.py`。

对每条 guide，程序先把 `U` 转成 `T/U` 后统一计算以下特征：

```text
length_score:
  L = 14-18             -> 1.00
  L = 12-20             -> 0.75
  其他长度              -> max(0, 1 - abs(L - 16) / 16)

gc_score:
  GC 比例              -> 1 - abs(GC - 0.50) / 0.30，限制在 0-1

guide_structure_penalty:
  最长局部反向互补长度 h
  penalty = clamp((h - 3) / 6, 0, 1)

repeat_hairpin_score（仅提供 direct repeat 时）:
  min(1, repeat_hairpin_len / 6)
```

没有 direct repeat 时的分数为：

```text
0.30 * length_score
+ 0.25 * (1 - guide_structure_penalty)
+ 0.20 * gc_score
--------------------------------
0.75
```

提供 direct repeat 时的分数为：

```text
0.30 * length_score
+ 0.25 * (1 - guide_structure_penalty)
+ 0.20 * gc_score
+ 0.25 * repeat_hairpin_score
--------------------------------
1.00
```

这些权重和分段阈值是程序内的可解释规则，并非 TEEP 论文发布的训练模型或
实验校准曲线。分数越高只表示该规则下的序列特征更理想，不能直接解释为
“编辑效率等于该百分比”。

### 2.2 `teep` 在线模型

实现位置：`shared/scoring/scoring.py` 的 `teep_on_target_score()`；
注册信息位于 `shared/scoring/model_registry.py`。

程序向 `https://www.tnpb.app/` 发送：

```json
{"input_data": "GUIDE_SEQUENCE"}
```

服务返回类似：

```json
{
  "ATCACCATCATGGTTCTTAT": {
    "CNN_pred": 38.754,
    "RNN_pred": 40.654
  }
}
```

程序读取同一个序列对应的 `CNN_pred` 和 `RNN_pred`，分别除以 100，取可用值的
平均数并限制到 0-1。以该例计算：

```text
(38.754 / 100 + 40.654 / 100) / 2 = 0.39704
```

TEEP 论文说明其模型面向增强型 ISDra2 TnpB（TnpBmax），训练数据来自
10,211 个靶点；候选模型包括 CNN 和双向 LSTM/RNN，论文报告预测与测量的
相关系数 `r > 0.8`。TEEP 网站和程序都按单条或批量 guide 查询常规预测端点；
本程序没有调用网站提供的 mismatch-pair 端点。

重要限制：

- TEEP 的示例和训练输入是 20 nt 靶向序列。程序没有在本路径中强制检查长度；
  不符合服务要求的序列可能由服务端拒绝。
- TEEP 网络超时、HTTP 错误、缺少字段或返回空值时，`teep` 路径回退到
  `heuristic_on_target_score()`，不是自动回退到 `omega_rna_rules`。
- 当前最终候选表不输出 `reference_note` 或模型名称列，因此仅看
  `on_target_score_teep` 不能判断该次在线推理是否成功。需要诊断时查看运行日志，
  或在同一次运行中同时选择 `omega` 与 `teep` 做并列比较。
- 在线服务版本不会固定到本地提交，也没有离线缓存；同一输入在不同时间可能
  受到服务端版本或可用性影响。

### 2.3 `identity` off-target 规则

实现位置：`shared/scoring/scoring.py` 的
`identity_off_target_specificity()`。

对每个有效 off-target：

```text
similarity = 相同碱基数 / min(guide 长度, off-target spacer 长度)
total      = sum(similarity)
```

如果模型假定结果集中包含 1 个主要完全匹配位点，且确实检测到完全匹配，
则从 `total` 中减去 1。最终：

```text
off_target_specificity = 1 / (1 + total)
```

1 表示没有额外的相似位点，越低表示相似位点压力越大。TnpB 路径直接使用
这个函数，不走带 seed penalty 的 `preset_off_target_specificity()`；
`non_cas9_rules.py` 中记录的建议 seed 参数不会影响该分值。PAM/TAM 过滤发生在
进入评分前：只有启用 `Require PAM` 并提供了正确 motif 时，带有错误 TAM 的
命中才会被排除。

## 三、适用范围和当前限制

### 3.1 ISDra2 与 TnpBmax

默认 TnpB preset 标记为 `isdra2`。TEEP 的训练数据来自 TnpBmax，即用于哺乳动物
细胞优化的 ISDra2 TnpB 版本。对另外的 TnpB 同源蛋白或其他编辑架构，TEEP
没有验证；本地 `omega` 规则也只是通用序列启发式。程序仍允许在
`nuclease=custom` 下调用这些模型，但此时应视为参考结果。

### 3.2 TAM 默认值

ISDra2 TnpB 的经典 TAM 是 `5'-TTGAT`。系统 preset 现在默认使用
`pam="TTGAT"`、`pam_side="5prime"`、`pam_required=True`，因此默认
library 搜索会强制经典 TAM。若用户切换到自定义模式，应显式维持相同约束，
否则结果不能解释为经典 ISDra2 TAM 搜索。

### 3.3 旧结果文件

旧版结果表可能包含 `tnpb_subtype`、`on_target_score`、`on_target_model`、
`off_target_model`、`reference_only`、`reference_note`、`rule_source`、
`rule_reference`、`rule_summary`、`subtype_note`、`omega_model` 等列。
这些字段中的一部分仍保留在内部评分结果、库流水线或 `library_summary.json`，
但不属于当前单 motif / Pattern A / Y-ZBP 候选表的统一输出契约。
不要从旧 TSV 的列存在性推断当前程序仍会写这些列。

## 四、输出字段

> 结果文件与结果列的完整清单已整合到 `docs/OUTPUTS.md`；
> 本节只保留 TnpB 专有的列含义与公式。

所有 TSV/XLSX 写出器会删除“整列均为空”的可选列；数值 0 不算空。因此同一
次运行中实际列集合取决于勾选的模型、是否提供 direct repeat，以及是否运行
`--unique-guides`、注释等功能。

### 4.1 TnpB 相关列

| 列 | 含义 | 计算或取值 |
| --- | --- | --- |
| `on_target_score_omega` | 本地 omegaRNA 启发式 on-target 分数 | 2.1 节公式，0-1，越高越好 |
| `on_target_score_teep` | TEEP CNN/RNN 平均预测 | 平均原始值后除以 100，0-1；失败时为通用启发式回退值 |
| `off_target_specificity_identity` | TnpB 的 off-target specificity | 2.3 节公式，0-1，越高越好 |
| `spacer_len_score` | guide 长度规则分 | 14-18 nt 为 1；12-20 nt 为 0.75；其他按 `1-abs(L-16)/16` |
| `guide_structure_penalty` | guide 自身发夹/反向互补惩罚 | `clamp((guide_hairpin_len-3)/6, 0, 1)`，越低越好 |
| `repeat_hairpin_score` | direct repeat 的发夹结构分数 | `min(1, repeat_hairpin_len/6)`；没有 direct repeat 时为空，整列可能被隐藏 |
| `AT_score` | TnpB preset 的 flanking AT 分数 | 仅当对应侧 system preset 为 `tnpb` 时计算和输出；Pattern A 列名为 `left_AT_score` / `right_AT_score`，Y-ZBP 为逐侧 `AT_score` |
| `omega_model` | 本地模型标识 | `library_scores.tsv` 中的值为 `omega_rna_rules`；单 motif 和复杂模式候选表会过滤该内部列 |

### 4.2 Pattern A / Y-ZBP 的左、右列

复杂模式对每一侧独立评分并加前缀：

- `left_on_target_score_omega`
- `right_on_target_score_omega`
- `left_on_target_score_teep`
- `right_on_target_score_teep`
- `left_off_target_specificity_identity`
- `right_off_target_specificity_identity`
- `left_spacer_len_score`、`right_spacer_len_score`
- `left_guide_structure_penalty`、`right_guide_structure_penalty`
- `left_repeat_hairpin_score`、`right_repeat_hairpin_score`
- `left_AT_score`、`right_AT_score`（仅在该侧 preset 为 TnpB 时）

左右两侧可以选择不同的 nuclease 和模型。配对结果使用 PairRank 综合两侧
证据、脱靶风险和兼容性；一侧不是 TnpB 时，不应把 TnpB 列与该侧混用。

### 4.3 公共统计和排序列

| 列 | 含义 |
| --- | --- |
| `rank` | 当前写出器自己的排名。单 motif、unique guide 和 `library_scores.tsv` 按 `off_target_specificity` 降序；Pattern A / Y-ZBP 的 `rank` 来自 PairRank 分组顺序 |
| `nuclease` | 本次评分的核酸酶类型，TnpB 为 `tnpb` |
| `total_matches` | 搜索后端返回的当前 query 命中数 |
| `valid_matches` | 排除屏蔽区域后参与统计和评分的命中数 |
| `sum_mismatch` | 有效命中的错配总数 |
| `MM0` ... `MMn` | 各错配桶；最后一列 `MMn` 表示 `>= n`，n 等于本次 `max_mismatch` |
| `GC-content`、`GC-hint` | query 的 GC 百分比和程序内的低/通过/高提示 |
| `Self-complementarity`、`Self-comp-hint` | 最长反向互补长度及提示；其计算范围可能覆盖完整 query window，不等同于输出中的 `guide_structure_penalty` |
| `legacy_total_score` | 旧版“匹配压力”分，只用于兼容参考，不是 0-1 分数，不能与 `off_target_specificity` 直接比较 |

### 4.4 文件和摘要

| 输出 | TnpB 相关内容 |
| --- | --- |
| `query_scores_sorted.tsv` | 每个候选一行；包含勾选模型的 `on_target_score_<model>` 和 `off_target_specificity_<model>`，以及非空的 TnpB 子特征 |
| `unique_guides.tsv` | 按唯一 guide 去重后的同一类模型和 TnpB 子特征列 |
| `library_scores.tsv` | Library 流程结果；额外保留 `omega_model`，TnpB 子特征和其他模型评分同样存在 |
| `top_offtargets.tsv` | 每个 guide 排名靠前的命中位点，不包含 on-target 模型分数 |
| `query_scores.bed` | 候选区间和归一化 BED 分数，不展开 TnpB 子特征 |
| `library_summary.json` | 包含主 `off_target_model`、`rule_source`、`rule_reference`、`subtype_note`、`omega_model`、搜索引擎等摘要字段 |

当前统一的候选表不输出以下内部字段：

- `reference_only`、`reference_note`
- `rule_source`、`rule_reference`、`rule_summary`
- `subtype_note`
- `omega_model`（Library 表例外）
- `on_target_model_<model>`、`off_target_model_<model>`
- `tnpb_subtype`

因此，结果的模型身份由 `on_target_score_<model>` /
`off_target_specificity_<model>` 列名表达，而不是另设模型名称列。

## 五、按结果判断的推荐顺序

1. 确认运行使用 ISDra2/TnpBmax 适用的数据；其他 TnpB 只作参考。
2. ISDra2 preset 默认使用 `5'-TTGAT` TAM，并强制 PAM 过滤。
3. 先用 `off_target_specificity_identity` 排除额外相似位点多的候选。
4. 本地筛选优先看 `on_target_score_omega`；要比较在线 TEEP 时，再同时查看
   `on_target_score_teep`，并确认运行日志中没有 TEEP 回退。
5. 单 motif 按 `off_target_specificity` 查看；双靶点按 PairRank 状态和
   风险字段查看。再人工核查 `top_offtargets.tsv`、种子区域和实验链路。
   不要把任一启发式分数直接当成绝对编辑效率。

## 六、参考文献

1. Marquart KF, Mathis N, Mollaysa A, et al. **Effective genome editing with
   an enhanced ISDra2 TnpB system and deep learning-predicted ωRNAs.**
   *Nature Methods* 21, 2084-2093 (2024).
   DOI: [10.1038/s41592-024-02418-z](https://doi.org/10.1038/s41592-024-02418-z)

   本程序 TEEP 在线模型及其 CNN/RNN 预测的直接来源。

2. Karvelis T, Druteika G, Bigelyte G, et al. **Transposon-associated TnpB is
   a programmable RNA-guided DNA endonuclease.** *Nature* 599, 692-696 (2021).
   DOI: [10.1038/s41586-021-04058-1](https://doi.org/10.1038/s41586-021-04058-1)

   ISDra2 TnpB、omegaRNA 引导 DNA 切割和 TAM 的基础工作。

3. Altae-Tran H, Kannan S, Demircioglu FE, et al. **The widespread
   IS200/IS605 transposon family encodes diverse programmable RNA-guided
   endonucleases.** *Science* 374, 57-65 (2021).
   DOI: [10.1126/science.abj6856](https://doi.org/10.1126/science.abj6856)

   TnpB 家族、RNA 引导机制和靶向范围的原始工作。

4. TEEP web application: [https://www.tnpb.app/](https://www.tnpb.app/)

   程序 `teep` 路径实际调用的在线服务。

本地 `omega_rna_rules` 的权重和阈值是仓库实现，不应引用上述论文将其描述为
论文发布的训练模型。上述文献为该规则的生物学适用范围提供背景依据。
