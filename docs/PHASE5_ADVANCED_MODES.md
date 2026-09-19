# Phase 5：高级模式离线化与规则完善

Phase 5 的目标是让 CRISPRi、TnpB、omegaRNA 和 CROPSR 在没有网络和外部
服务的环境下也能给出可解释的结果。

## CRISPRi：TSS 窗口与链方向

`compute_guide_scores(..., preset_key="crispri")` 现在支持三个额外维度：

- TSS 窗口：默认给 -50..+300 bp 的最佳区间，窗口外按距离线性衰减。
- 链方向：提供 `tss_strand` 和 `guide_strand` 后，优先非模板链；方向不符
  时对 TSS 分数打 0.8 折扣。
- 启动子区域：提供 `promoter_start`、`promoter_end`、`spacer_start` 后，
  落在启动子窗口内给满分，否则给 0 分。

只传 `tss_distance` 时保持旧的 `crispri_tss` 行为，兼容现有调用。

## TnpB 与 omegaRNA：离线默认

原来的默认路径会请求在线 TEEP。现在默认改为本地 `omega_rna_rules`：

```text
spacer_len_score       14-18 nt 最佳，12-20 nt 可接受
guide_hairpin_len      自结构 hairpin 长度，过长会扣分
repeat_hairpin_score   直接重复区的茎环结构，越强越好
gc_score               40-60% 最佳
```

在线 TEEP 保留为 `reference_only_model="teep"` 时的显式参考模型，
不再影响默认离线流程。

## CROPSR

当前 `cropsr_on_target_score` 已经是 CROPSR 论文工作流使用的完整
Doench logistic 系数（一阶、二阶、GC 调整和截距），不是简化的启发式。
回归测试锁定了输出的确定性，并返回 `cropsr_model_note` 说明模型来源。

## 验收状态

- CRISPRi：TSS 窗口、链方向、启动子区域评分：已完成并有独立测试。
- TnpB：默认离线 omegaRNA 规则，TEEP 仅作参考：已完成。
- omegaRNA：重复区、茎环、spacer 长度和结构约束：已完成。
- CROPSR：完整系数模型说明与确定性回归：已完成。
