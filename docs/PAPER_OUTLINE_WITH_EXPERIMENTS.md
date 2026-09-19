# 论文大纲（有实验版 / 平行版本）

检查日期：2026-09-19。本文件是 `docs/PAPER_OUTLINE.md`（无实验版）的平行版本，
用于「将来补齐湿实验数据」的情形。两版共用同一套仓库证据与同一份文献核查结论，
只有本文件 §0 列出的区块不同；§8 列出可直接沿用的章节。

## 0. 与无实验版的差异对照（切换时只看这一节）

| 区块 | 无实验版 `PAPER_OUTLINE.md` | 有实验版（本文件） |
| --- | --- | --- |
| 标题 | tool platform | validated design space |
| 主张等级 | 表达力层：设计空间可表达、可完备枚举 | 有效性层：设计空间能产出可用的 guide |
| 摘要第 4 句 | 计划完备性 + 引擎基准 | 引擎基准 + 实测效率与预测的相关性 |
| 贡献 C3（PairRank） | 支撑位，Limitations 交代未校准 | 升为头号之一，可演示 experiment_calibrated |
| Results 3.8 | 回顾性验证（公开数据集） | 前瞻性实验验证 |
| Results 3.9 | 无 | 回顾性验证（保留，作外部一致性检查） |
| Discussion | 必须声明未做实验 | 改为实验条件的外推边界 |
| 图表 | 6 图 5 表 | 8 图 6 表（新增实验设计图与效率分布图） |
| 期刊 | NAR 正刊 | NAR 正刊；条件好可冲 Genome Biology / Nature Communications |

## 1. 标题候选（有实验版）

1. `Motif-anchored multi-element CRISPR guide design: a validated design space
   with a native indexed off-target engine`
2. `Constraint-driven guide design across nucleases: from expressible layout to
   validated editing`

## 2. 摘要骨架（有实验版，NAR 惯例单段）

1. 现有工具以基因或坐标区间为中心枚举 guide，无法直接表达设计意图。
2. 我们把引导定义抽象为一组正交自由参数，并把设计空间形式化为其完备解集。
3. 配套原生 C++20 持久化索引引擎，含自动种子计划合成与完备性保证。
4. 结果 1（计算）：warm search [TIME] vs BLAST [TIME]；32 线程 [RATIO]x 扩展；
   命中输出与线程数无关。
5. 结果 2（表达力）：表达力矩阵显示 [N] 个已发表系统中 [M] 个现有工具无法表达目标设计。
6. 结果 3（实验）：[N] 条候选的实测编辑效率与预测的 Spearman rho = [RHO]；
   双侧联合编辑率 [X]%。
7. 可用性：桌面 GUI、本地 web 界面、完整测试套件。

## 3. 贡献列表（有实验版）

| 编号 | 贡献 | 定位 |
| --- | --- | --- |
| C1 | 声明式引导定义空间（正交自由参数 + motif 锚定 + 三元件布局） | 头号 |
| C2 | 原生 C++20 索引引擎（自动种子计划 + 完备性引理 + 确定性并行 + 硬资源边界） | 头号 |
| C3 | PairRank：双侧必成约束下的排序，含 experiment_calibrated 模式 | 头号 |
| C4 | 可移植模型复刻 + 校准状态传播 | 支撑 |

## 4. Results 实验章规格（可直接交给做实验的人）

3.8 前瞻性验证，最小可发表集合：

必做三臂设计：

- left-only、right-only、left+right 三组，每组 >= 3 个生物学重复
- 三臂读出方法一致（扩增子测序或等效方法）

必做读数：

- 每条候选的 on-target 编辑效率（%）
- 每对 pair 的联合编辑率（%）
- 脱靶：至少对 top-N 候选做靶向深度测序；条件允许时 GUIDE-seq / CIRCLE-seq

必做统计（审稿人必问）：

- 预测 vs 实测的 Spearman / Pearson 相关性 + 95% 置信区间
- 用实测标注做阈值判别时的 ROC / AUC
- 统计功效说明（重复数、效应量、检验方法）
- dropout 与失败样本必须记录，不能只报成功样本

PairRank 的 experiment_calibrated 模式需要：

- `E_both_LCB`、`B_pair_UCB`，以及每对的 dropout 计数
- 只有同一核酸酶、guide 化学、递送方式、细胞类型、编辑类型、剂量、时间点下的
  数据才可外推（沿用 `docs/PAIR_RANKING.md` 的表述）

## 5. Discussion 的变化（有实验版）

- 删除「本文为计算工具、未做实验验证」的声明。
- 改为写外推边界：实验结论只对相同核酸酶、guide 化学、递送方式、细胞类型、
  编辑类型、剂量和时间点具有较强外推能力。
- 计算侧局限保留：bulge 走 `conservative_bulge_v1` 且标 `uncalibrated`；
  TIGER 依赖 TensorFlow；TEEP 依赖网络；超过约 200 MB 的基因组自动首选 BLAST。

## 6. 图表增量（有实验版）

新增：

- Fig 7 实验设计示意图（三臂 + 对照）
- Fig 8 预测 vs 实测效率散点 + 回归曲线
- Table 6 每条候选的实测效率、预测值、置信区间

原有的 6 图 5 表保持不变。

## 7. 期刊与主张的对应

| 条件 | 建议 |
| --- | --- |
| 完整三臂 + 脱靶检测 + >= 3 重复 | NAR 正刊；可试 Genome Biology / Nature Communications |
| 只有 on-target 效率、无脱靶检测 | NAR 正刊，但 C3 仍难升为头号 |
| 无实验 | 回 `docs/PAPER_OUTLINE.md`（无实验版） |

## 8. 与无实验版共用的部分

以下内容两版完全相同，直接引用 `docs/PAPER_OUTLINE.md`，本文件不重复：

- 第二节 新颖性边界与措辞规范（15 篇先例表、5 条未找到先例、措辞对照）
- 第三节的 Materials and Methods 大纲（2.1-2.11）
- 第三节的 1 Introduction 与 3 Results 的 3.1-3.7
- 第四节的 Fig 1-6 与 Table 1-5
- 第五节 待补数据的第 1-6 项
- 第六节 证据索引（仓库内位置）
- 第八节 写作顺序建议
- 第九节 格式规范（双范本：ALLEGRO NAR 2025 53 gkaf783 为主，CRISPR-COPIES NAR 2024 52 e30 为副）