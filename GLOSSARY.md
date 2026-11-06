# TargetDesign-workbench

TargetDesign-workbench 将设计意图、脱靶搜索和候选评分分开。本词汇表固定项目领域的规范用语，供程序、界面、文档和手稿共同使用。

## Design

**Design request**:
一次完整的目标选择意图，包括目标区域、效应蛋白、pattern、搜索约束、评分模型和导出选择。
_Avoid_: job, query, run

**Pattern**:
anchor、guide 窗口和距离约束的声明式组合；它决定如何枚举 candidate，而不决定 candidate 的分数。
_Avoid_: mode, pipeline, target

**Single-anchor pattern**:
一个 anchor motif 与一个 guide 窗口相邻的 pattern，界面标签为 Basic（`single_motif_flank`）。
_Avoid_: single motif, when referring to the whole pattern

**Gap-anchored pair**:
两个 anchor motif 之间带距离约束的 paired pattern，也称 Pattern A（`motif_gap_motif`，界面标签 Complex）。
_Avoid_: Target-xbp-Target, complex mode

**Centered-anchor pair**:
两个 guide 围绕一个 middle motif 布置的 paired pattern，也称 Pattern B（`y_centered_motifs`，界面标签 Y/ZBP）。
_Avoid_: Y pattern, center mode

**Motif**:
用于定位基因组放置位置的 IUPAC 序列。
_Avoid_: target, guide, PAM, when referring to an arbitrary motif

**PAM/TAM**:
效应蛋白在 protospacer 邻近位置要求的短序列；PAM 是通用术语，TAM 特指 TnpB 的相邻 motif。
_Avoid_: motif, when a PAM or TAM is meant

**Middle motif**:
paired pattern 中位于两个 guide 之间、用于确定放置位置的 motif。
_Avoid_: Y sequence, when referring to the biological motif

**Guide**:
决定编辑位置的一段 spacer 序列。
_Avoid_: flank, query, target, when referring to the guide itself

**Candidate**:
pattern 在基因组上的一个合法放置，包含 anchor 位置及其一个或多个 target site 和 guide。
_Avoid_: hit, target, result row

**Target region**:
供 pattern 枚举 candidate 的输入基因组区间。
_Avoid_: target, search area

**Target site**:
某个 candidate 中预期由对应 guide 作用的具体基因组区间。
_Avoid_: candidate, hit, target

## Search

**Search query**:
提交给脱靶搜索引擎的核酸序列；它可以是 guide，也可以是带 PAM/TAM 或多个组件的查询窗口。
_Avoid_: guide, when the submitted sequence contains more than the guide

**On-target site**:
某个 guide 的预期基因组匹配位点。
_Avoid_: candidate, main hit

**Off-target hit**:
搜索引擎在给定错配、bulge、seed 和 PAM/TAM 约束下找到的、与 search query 相似的基因组放置。
_Avoid_: candidate, target site

**Alignment**:
search query 与目标序列之间带替换和 gap 的对应关系。
_Avoid_: hit, match, when the alignment itself is meant

**Mismatch**:
alignment 中 query 与 target 的碱基替换。
_Avoid_: edit, mutation

**RNA bulge**:
alignment 中 query 多出一个碱基的 gap。
_Avoid_: insertion

**DNA bulge**:
alignment 中 target 多出一个碱基的 gap。
_Avoid_: deletion

**Seed**:
guide 中靠近 PAM/TAM 的一段序列；搜索时通常使用更严格的错配预算。
_Avoid_: seed region, anchor motif

**Search engine**:
产生 off-target hit 的搜索实现，例如 exact、indexed、BLAST 或 GGGenome。
_Avoid_: model, scorer

**Exhaustive search**:
在当前声明约束和适用基因组范围内保证不遗漏合法位置的搜索性质。
_Avoid_: complete search, when only a finite fixture was tested

**Approximate search**:
可能因候选生成策略而漏掉合法位置的搜索；BLAST 属于此类。
_Avoid_: exhaustive search

## Scoring

**Scoring model**:
把 sequence 或 alignment 转换为预测分数的模型或规则集合。
_Avoid_: engine, backend

**Rule set**:
由明确公式和阈值定义、不依赖训练权重加载的 scoring model。
_Avoid_: learned model

**On-target score**:
guide 对预期 target site 的预测编辑能力。
_Avoid_: specificity, risk

**Off-target specificity**:
表示候选相对额外 off-target hit 的安全性，数值越大越安全。
_Avoid_: risk, burden

**Off-target burden**:
多个 off-target hit 合并后的风险或活性上界，数值越小越安全。
_Avoid_: specificity

**Calibration status**:
一个分数是否以及如何对应可比较的实验概率或证据。
_Avoid_: model status, validation status

## Paired Design

**Pair**:
两个 target site 必须同时成功时共同评价的设计单元。
_Avoid_: candidate, when referring to the paired unit

**PairRank**:
按 pair 的证据等级、联合风险和一致性对 paired candidate 排序的规则。
_Avoid_: combined score, side rank

**Prediction-only**:
没有匹配的 paired 实验校准时使用的 PairRank 模式。
_Avoid_: uncalibrated, when referring to the whole ranking mode

## Execution

**Run**:
对一个 design request 或其批次的一次执行。
_Avoid_: job, session

**Batch run**:
把一组设计单元作为同一批任务执行的一次 run。
_Avoid_: batch, when referring to a single execution
