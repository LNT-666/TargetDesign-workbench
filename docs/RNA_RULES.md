# Phase 4：RNA 可及性与非 Cas9 规则

Phase 4 的目标是把 Cas13 的 RNA 结构分数和非 Cas9 的文献规则接入统一评分，
不再只用 U/A 富集和通用启发式。

## 新增模块

| 文件 | 作用 |
| --- | --- |
| `shared/scoring/rna_utils.py` | ViennaRNA 封装：RNAfold MFE、RNAplfold 可及性、RNAduplex/RNAcofold；无 ViennaRNA 时安全返回 None |
| `shared/scoring/cas13_scoring.py` | Cas13 guide 综合分数：guide 可及性、自结构、DR-spacer 相互作用、靶 RNA 可及性和结构扰动 |
| `shared/scoring/non_cas9_rules.py` | Cas12a/b、Cas14a、Cas13、CRISPRi、TnpB 的 PAM/PFS、seed、错配容忍、切割位点和文献来源 |

## ViennaRNA 安装

Linux / macOS：

```bash
conda install -c bioconda viennarna
```

或使用 Python 绑定：

```bash
pip install ViennaRNA
```

Windows 建议在 WSL 中安装。未安装时评分自动回退到确定性的
`cas13_u_rich` / `cas13_a_rich` 启发式，`rna_features` 中的值为 `None`，
不会中断流程。

## Cas13 输出字段

`compute_guide_scores(..., preset_key="cas13")` 现在返回
`rna_features`，包含：

```text
guide_mfe, guide_structure, guide_accessibility,
target_accessibility, dr_spacer_duplex_mfe, dr_spacer_penalty,
perturbation_mfe, rna_model, rna_note, dr_source
```

直接重复序列（DR）来源：

| 系统 | DR 序列 | 文献 |
| --- | --- | --- |
| Cas13（CHOPCHOP 默认，LwaCas13a） | `GATTTAGACTACCCCAAAAACGAAGGGGACTAAAAC` | Abudayyeh et al. 2017, Nature |

## 非 Cas9 规则表

规则表在 `shared/scoring/non_cas9_rules.py`，每个系统都带 `source` 和
`source_url`。`compute_guide_scores` 的输出新增：

```text
rule_source, rule_reference, rule_summary
```

Library 流程可追溯来源：

```powershell
python shared\design\library_pipeline.py regions.tsv genome.fa outdir `
  --preset cas13 --engine exact --direct-repeat GATTTAGACTACCCCAAAAACGAAGGGGACTAAAAC `
  --target-rna AUGGCCAUUAAAGCCCACACGU
```

输出 TSV 会包含 `rna_model`、`guide_mfe`、`guide_accessibility`、
`dr_spacer_duplex_mfe`、`rule_source` 等列。

## 验收状态

- Cas13 输出包含 MFE、可及性和 DR-spacer 分数：已完成。
- 非 Cas9 结果能从规则表追溯到文献来源：已完成。
- ViennaRNA 未安装时仍有确定性回退：已完成并有回归测试。
