# PairRank 双靶点排序规范

本文定义“两个非冗余靶点都必须使用、且两侧都必须成功编辑”时的候选
pair 排序规则。该规范用于 Pattern A（Target-xbp-Target）和 Pattern B
（Target-xbp-Motif-ybp-Target）的 pair 级排序。

当前规范有两个模式：

- `prediction_only`：确定未来不会开展 pair 级湿实验，只能使用预测值和
  可用的公开先验。
- `experiment_calibrated`：已经完成 paired 编辑实验，可以用实测联合编辑
  率和实测脱靶风险更新排序。

两种模式都不把未经校准的 on-target 分数作为精细主排序变量。两个靶点
必须同时成功，任一侧都不能被另一侧补偿。

## 模式选择与优劣对比

`experiment_calibrated` 不是天然优于 `prediction_only`。实验数据只对
相同核酸酶、guide 化学、递送方式、细胞类型、编辑类型、剂量和时间点
具有较强外推能力。条件不匹配时，直接使用实验校准模式可能比预测模式
更危险，因为它会制造“已经校准”的假象。

| 维度 | `prediction_only` | `experiment_calibrated` |
| --- | --- | --- |
| 所需数据 | 模型分数、逐位点脱靶预测或 aggregate specificity | 需要 `left-only`、`right-only`、`left+right` 三臂计数；最好有直接 `k_both` |
| 实验成本 | 无额外湿实验成本 | 成本高，通常需要扩增子测序、联合编辑检测和脱靶检测 |
| on-target 使用方式 | 只做 A/B/C 证据分级，不精细区分同级候选 | 使用 `E_both_LCB` 精细排序，并保留活动门槛 |
| on-target 主要优点 | 不会被不可靠模型分数过度放大；规则透明、稳定 | 直接反映当前实验体系中的联合编辑成功率；可发现 pair 互作 |
| on-target 主要缺点 | 同级候选无法精确比较；阈值仍依赖模型和策略配置 | 对批次、细胞类型、递送方式和时间点敏感；样本不足时容易过拟合 |
| 脱靶风险 | 默认使用 `B_pair+ = B_L+ + B_R+` 保守上界 | 使用 pair 实测的背景校正 `B_pair_UCB` 和 `M_pair_UCB` |
| 脱靶主要优点 | 对未知共享位点和非加性风险更保守，不容易漏掉高风险 pair | 能区分共享位点、pair 增强和单侧高估，减少不必要的保守淘汰 |
| 脱靶主要缺点 | 共享位点可能被重复计数；可能误杀安全 pair | 检测灵敏度、覆盖度和对照质量会影响结果；未测位点仍然没有信息 |
| 排序分辨率 | 较低，主要按风险等级和 A/B 证据层排序 | 较高，可对通过门槛的 pair 使用连续 `E_both_LCB` 和实测风险 |
| 结果可信度 | 可信度取决于模型适用性和策略阈值 | 可信度取决于实验重复、QC、配对设计和外推范围 |
| 过拟合风险 | 主要来自人为权重和阈值，不是实验样本过拟合 | 小样本、高 dropout、批次效应和多次筛选后容易过拟合 |
| 泛化能力 | 可跨较多 pair 和场景，但预测准确性有限 | 在匹配实验条件下较强；跨细胞类型、递送方式和编辑类型时明显下降 |
| 失效模式 | 可能错过真正可行的 pair，或让模型偏差决定顺序 | 可能把实验噪声、批次偏差或选择偏倚当成真实排序信号 |
| 可解释性 | 高，能明确展示门槛、风险等级和排序键 | 高，但必须同时披露样本量、置信区间、dropout 和排除样本 |
| 适用场景 | 确定不做 pair 实验；大规模初筛；探索性设计；实验条件经常变化 | 已经完成可靠 paired 实验；相同实验条件下筛选；临床或安全敏感候选验证 |
| 主要优势 | 稳健、低成本、不过度声称精度 | 能真正测量联合成功和 pair 特异性风险 |
| 主要局限 | 只能给出保守候选顺序，不能给出可靠概率 | 不能自动外推到未验证的细胞、递送或实验条件 |

模式选择规则：

1. 确定未来不做 pair 实验时，必须使用 `prediction_only`。
2. 有实验数据，但核酸酶、细胞类型、递送方式、剂量、时间点或检测方法
   与待排序场景不一致时，不能直接使用 `experiment_calibrated`。
3. 有直接 `k_both`，且至少包含匹配的三臂对照和足够生物学重复时，优先
   使用 `experiment_calibrated`。
4. 只有边际编辑率、没有 `k_both` 时，`experiment_calibrated` 只能作为
   带有 `independence_assumed` 标记的次级排序。
5. 最好的组合策略是先用 `prediction_only` 选择实验 panel，再用
   `experiment_calibrated` 对同一条件下的 pair 更新排序；未实验条件仍
   回退到 `prediction_only`。

## 一、核心原则

1. pair 是排序单位，不是分别对左右侧 guide 排序后再简单组合。
2. 两个靶点必须成功，所以 pair 活动能力使用左、右两侧较弱的证据作为
   约束，不使用两侧平均。
3. pair 脱靶风险默认按两侧风险合并，不使用左、右两侧的最小值或平均值。
4. 未经校准、fallback、`reference_only` 或不适用的模型不能进入主排名。
5. 预测阶段使用证据等级，实验后阶段使用联合编辑率的下界。
6. 禁止区域脱靶、未校准 bulge、结构变异兼容性等问题属于硬门槛，不靠
   增加总分来补偿。
7. 排序必须可复现。相同排序键获得相同名次，最终用稳定的 `pair_id`
   做确定性排序。

## 二、公共符号和预处理

对每一侧 `s ∈ {L, R}` 定义：

```text
a[s,k]      第 s 侧候选在第 k 个额外脱靶位点的预测活性
a[s,k]+     第 s 侧候选在第 k 个额外脱靶位点的活性上界
B[s]        第 s 侧候选的脱靶负担
B[s]+       第 s 侧候选的脱靶负担上界
M[s]+       第 s 侧候选的最大单点脱靶活性上界
H[s]        第 s 侧候选达到高危阈值的额外位点数量
Tier[s]     第 s 侧候选的 on-target 证据等级
```

### 2.1 预期目标位点

`a[s,k]` 必须排除该侧的预期 on-target 位点。如果一个 guide 具有多个
预期目标位点，必须显式列出所有预期位点并全部排除。

### 2.2 单侧脱靶负担

预测模式下：

```text
B[s]+ = sum(a[s,k]+ for k in extra_offtargets)
M[s]+ = max(a[s,k]+ for k in extra_offtargets)
```

只有聚合 specificity 而没有逐位点分数时，可以使用：

```text
B[s]+ = 1 / specificity[s] - 1
M[s]+ = unknown
```

此时候选可以参与 `prediction_only` 排序，但必须标记
`offtarget_detail=aggregate_only`，不能获得高置信度等级。
`M[s]+ = unknown` 时，在排序键中将该值排在所有数值之后。

### 2.3 上界规则

优先使用模型自带的不确定性：

```text
a[s,k]+ = 95% upper credible bound of a[s,k]
```

没有不确定性输出时，使用模型校准误差 `delta[model]`：

```text
a[s,k]+ = min(1.0, a[s,k] + delta[model])
```

`delta[model]` 必须来自留出实验数据的校准结果。没有校准数据时，
`delta[model]` 不能设为 0；该模型应标记为
`calibration_status=uncalibrated`，只能进入低置信度候选组。

## 三、预测模式：未来不做 pair 实验

模式名：

```text
rank_mode = prediction_only
```

该模式的目的是在预测不可靠时避免过拟合噪声。on-target 只用于证据筛选
和粗糙分层，pair 的安全性优先。

### 3.1 双侧 on-target 证据等级

每个适用模型先输出一个活动分数 `e[model]`。阈值由
`pair_rank_policy` 提供：

```text
e_high    强活动证据阈值
e_min     最低可接受活动证据阈值
e_fail    明确失败阈值
```

等级定义：

```text
Tier A:
  applicable_models >= 2
  所有适用模型 e[model] >= e_high
  不存在 fallback、reference_only 或强相反证据

Tier B:
  不满足 Tier A
  至少一个适用模型 e[model] >= e_min
  不存在所有适用模型都低于 e_fail 的情况

Tier C:
  不满足 Tier B
```

只有一个适用模型时，最高只能评为 Tier B，除非该模型已经由当前细胞
类型和当前核酸酶的实验数据校准，并且校准状态为 `calibrated_reference`。

pair 等级：

```text
Tier_pair = min(Tier_L, Tier_R)
```

`Tier_pair == C` 的 pair 不进入主排名，进入 `conditional` 组。

### 3.2 模型分歧

对每一侧，将适用 on-target 模型的输出转换为当前候选池内的百分位排名。
模型两两之间的最大排名差定义为：

```text
D[s] = max(abs(percentile[m1] - percentile[m2]))
D_pair = max(D_L, D_R)
```

`D_pair` 越小表示模型越一致。它只用于同分排序，不直接改变硬门槛。

### 3.3 pair 脱靶风险

默认使用保守上界：

```text
B_pair+ = B_L+ + B_R+
```

如果已经能够把两侧映射到相同脱靶位点，并且独立性经过验证，可以使用：

```text
B_pair+ = sum(
    1 - (1 - a[L,k]+) * (1 - a[R,k]+)
    for k in union_offtargets
)
```

最大单点风险：

```text
M_pair+ = max(M_L+, M_R+)
```

高危位点数量：

```text
H_pair = count(unique high-risk loci from both sides)
```

### 3.4 预测模式硬门槛

以下情况标记为 `rejected`，不进入 `pass`：

- 任一侧 PAM/TAM、guide 结构、靶点位置或预期编辑结果不合法。
- `Tier_pair == C`。
- 任一侧属于 fallback、`reference_only` 或模型不适用。
- 任一侧搜索不完整。
- `B_pair+ > b_high`。
- `M_pair+ > m_high`。
- `H_pair > h_max`。
- 存在禁止区域脱靶。
- 双侧距离、方向、递送方式、核酸酶或 multiplex 条件不兼容。
- 存在未校准 bulge，且没有适用的 bulge 风险模型。

### 3.5 预测模式风险等级

阈值位于 `pair_rank_policy`：

```text
Risk 0:
  B_pair+ <= b_low
  M_pair+ <= m_low
  H_pair == 0

Risk 1:
  B_pair+ <= b_high
  M_pair+ <= m_high
  不存在禁止区域脱靶

Risk 2:
  其余情况
```

`Risk 2` 不进入主排名。

### 3.6 预测模式排序键

只对通过硬门槛的 pair 生成 `pair_rank`。排序键为：

```text
sort_key = (
    risk_class,                 # Risk 0 < Risk 1
    -activity_tier_value,       # A=3, B=2
    B_pair+,                    # 越小越好
    M_pair+,                    # 越小越好
    H_pair,                     # 越小越好
    D_pair,                     # 越小越好
    compatibility_penalty,      # 越小越好
    pair_id                     # 最终稳定排序
)
```

按从小到大排序。`compatibility_penalty` 是软性警告数量，例如：

- 两个靶点距离处于警戒区，但尚未达到硬拒绝条件。
- 递送或表达兼容性不确定。
- 注释、异构体或目标区域边界不确定。
- 一侧需要特殊的 PAM 模式或非默认模型。

相同 `sort_key` 的 pair 获得相同名次。下一条名次等于前面 pair 数量加一。

### 3.7 预测模式输出

实际写入结果表的字段清单与含义见 `docs/OUTPUTS.md` 第 3.5 节；
本节只规定这些字段的策略来源与排序含义。

## 四、实验校准模式：已经完成 pair 实验

模式名：

```text
rank_mode = experiment_calibrated
```

该模式必须包含 `left-only`、`right-only` 和 `left+right` 三臂实验，
并且双 guide 组能够直接或间接得到两个靶点同时编辑的比例。

### 4.1 必需实验输入

每个 pair 和每个生物学重复至少需要：

```text
n_total
k_left
k_right
k_both
```

定义：

```text
r_L = k_left / n_total
r_R = k_right / n_total
r_both = k_both / n_total
```

如果实验只能得到边际编辑率而无法得到 `k_both`，必须标记：

```text
joint_edit_status = independence_assumed
r_both_independent = r_L * r_R
```

这类结果排在具有直接 `r_both` 的 pair 之后。

### 4.2 联合编辑置信下界

默认使用 Jeffreys 先验：

```text
alpha0 = beta0 = 0.5
```

`r_both` 的后验为：

```text
Beta(alpha0 + k_both, beta0 + n_total - k_both)
```

联合编辑下界：

```text
E_both_LCB = 5% posterior quantile
```

如果实验包含多个批次或多个生物学重复，不应直接把所有 read 混合。
先按重复计算，再使用层次模型或 bootstrap 合并批次间不确定性。

### 4.3 pair 交互系数

当 `r_L`、`r_R` 和 `r_both` 都存在时：

```text
kappa_pair = r_both / (r_L * r_R)
```

解释：

```text
kappa_pair ~= 1    两侧近似独立
kappa_pair < 1     两侧联合编辑低于独立预期
kappa_pair > 1     两侧联合编辑高于独立预期
```

`kappa_pair` 是诊断量和同分排序项，不直接覆盖实测 `r_both`。
当 `r_L == 0` 或 `r_R == 0` 时，`kappa_pair` 不可计算，按缺失值处理。

### 4.4 实测脱靶负担

每个脱靶位点先做背景校正：

```text
rate_net[k] = max(0, treated_rate[k] - matched_control_rate[k])
```

然后计算位点级 95% 上界：

```text
rate_UCB[k] = 95% upper bound of rate_net[k]
```

默认：

```text
B_pair_UCB = sum(rate_UCB[k] for k in pair_offtargets)
M_pair_UCB = max(rate_UCB[k] for k in pair_offtargets)
```

当共享位点已经完成 pair 级验证时，可以使用共享位点的联合估计值，
但不得用单侧上界平均代替 pair 实测。

### 4.5 实验模式硬门槛

以下情况标记为 `rejected` 或 `conditional`：

- `E_both_LCB < e_pair_min`。
- `B_pair_UCB > b_high`。
- `M_pair_UCB > m_high`。
- 存在禁止区域脱靶。
- 存在未解释的大片段缺失、倒位或易位。
- `joint_edit_status == independence_assumed` 且项目要求直接联合测量。
- 实验 QC 未通过，例如对照异常、覆盖度不足或重复间不一致。

实验模式的 Risk 等级与预测模式相同，但使用 `B_pair_UCB` 和
`M_pair_UCB` 替代 `B_pair+` 和 `M_pair+`。

实验活动等级定义为：

```text
Tier A: E_both_LCB >= e_pair_high
Tier B: e_pair_min <= E_both_LCB < e_pair_high
Tier C: E_both_LCB < e_pair_min
```

`Tier C` 不进入主排名。

### 4.6 实验模式排序键

排序键为：

```text
sort_key = (
    risk_class,                 # Risk 0 < Risk 1
    -activity_tier_value,       # 由 E_both_LCB 映射，A=3, B=2
    -E_both_LCB,                # 越大越好
    B_pair_UCB,                 # 越小越好
    M_pair_UCB,                 # 越小越好
    abs(log(kappa_pair)),       # 越接近 1 越好
    compatibility_penalty,      # 越小越好
    pair_id
)
```

如果 `kappa_pair` 不可计算，使用一个大于所有已计算值的固定惩罚，
确保该 pair 排在同等级已校准 pair 之后。

如果需要单一的实验校准分数，可以使用：

```text
S_pair = 1 / (1 + B_pair_UCB)
Q_pair = min(S_pair, c * E_both_LCB)
```

`c` 必须由项目策略配置。`Q_pair` 只用于展示，主排序仍使用上面的
`sort_key`。

### 4.7 实验模式输出

本模式尚未在代码中实现，当前不会输出以下字段；它们只作为后续实现的目标契约：

```text
joint_edit_status             # measured / independence_assumed / missing
r_left
r_right
r_both
E_both_LCB
kappa_pair
pair_offtarget_burden_measured
pair_offtarget_burden_UCB
pair_max_offtarget_UCB
pair_rank_confidence
```

## 五、策略参数

以下参数必须由 `pair_rank_policy` 按核酸酶、细胞类型、编辑类型和实验
目的提供：

```text
e_high
e_min
e_fail
e_pair_high
e_pair_min
b_low
b_high
m_low
m_high
h_max
c
delta[model]
alpha0
beta0
```

这些参数不能使用全局固定值。没有实验校准时，应使用保守默认值并明确
标记 `policy_status=uncalibrated`。

## 六、模型融合规则

不允许直接平均不同模型的原始分数。多模型必须按以下顺序处理：

1. 每个模型先映射到当前任务可解释的量，例如活动概率或脱靶活性的
   上界。
2. 使用 leave-pair-out 或 leave-guide-out 数据做概率校准。
3. 有足够标签时，使用 logistic regression、stacking 或 AdaBoost 融合。
4. 没有足够标签时，使用中位排名、最差排名或一致性投票。
5. 模型分歧写入 `D_pair`，用于同分排序和置信度，而不是被平均掉。

## 七、评价指标

排序策略必须使用以下指标评估，不能只报告 accuracy：

- 联合编辑预测：Brier score、ECE、校准曲线。
- 脱靶预测：AUPRC、top-k precision、固定编辑率阈值下的 recall。
- 候选排序：Spearman、NDCG@k、top-k 命中率。
- pair 实验：`both_edit_rate`、`E_both_LCB`、`kappa_pair`。
- 安全评估：禁止区域命中数、最大单点脱靶率、结构变异率。

训练集、校准集和测试集必须按 pair、guide 或 locus 划分，不能按 read
随机划分。

## 八、回退规则

满足任一条件时，必须回退到 `prediction_only`：

- 没有 `left-only`、`right-only` 或 `left+right` 对照。
- 只有边际编辑率，且项目要求直接测量联合编辑。
- 缺少匹配的 mock 或 non-targeting 对照。
- 脱靶位点没有背景校正。
- 实验重复不足以估计不确定性。
- 模型分数没有完成校准。

回退时必须保留实验字段，但将它们标记为 `diagnostic_only`，不能用于
正式 `pair_rank`。
