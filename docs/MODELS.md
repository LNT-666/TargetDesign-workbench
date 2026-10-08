# 模型目录与格式清单

检查日期：2026-09-12。目录：`models/`。

| 模型键 | 文件 | 格式 | 大小 | SHA256 | 注册表状态 | 真实可用状态 |
| --- | --- | --- | --- | --- | --- | --- |
| crispr_m | `tcrispr_model.h5` | Keras HDF5 权重 | 20,820,808 B | `9D6C307C26930E10CEC38D5508069311F2E868716F9A027CE8DA47CF564A7E3E` | ready | **可用**：纯 NumPy 前向已验证，样例输出 0.6321092247962952 |
| deepcrispr | `deepcrispr_offtar_pt_cnn_reg.tar.gz` | TensorFlow 1.x checkpoint（tar.gz） | 29,160,245 B（解压 data 44,228,628 B） | `88A272791B72E915632B815FCE0118F7A6140AFBA99CFC458E51DB778395398C` | ready（仅文件） | 原始 checkpoint 需要 TF，已转成下面的可移植文件 |
| deepcrispr | `deepcrispr_offtar_pt_cnn_reg.portable.npz` | NumPy 权重（67 个张量） | 14,778,336 B | `468A2B00F94A8A099EC2D4D91D23C7B03380F382F29209DF925D990AA95AEAA4` | - | **可用**：NumPy 前向与 TensorFlow 参考输出最大误差 3e-7 |
| azimuth | `azimuth_V3_model_nopos.pickle` | 旧版 scikit-learn pickle（GradientBoostingRegressor） | 135,380 B | `AF933634BE494336BC95BF657B07F7599AF842A2E9601797C88A49158D040214` | ready（仅文件） | 原始 pickle 需要旧版 sklearn，已转成下面的可移植文件 |
| azimuth | `azimuth_V3_model_nopos.portable.npz` | NumPy GBDT 树（100 棵）+ 特征顺序 | 194,548 B | `9659ED5B58A77A94F7306CE20BDE571949656DEA7756EF8E99784A8E89A5E6FB` | - | **可用**：与官方 1000 条参考样例 Spearman 0.993，MAE 0.0073 |
| teep | 无本地文件 | 在线 HTTP API | - | - | web_api | **可用但依赖网络**：调用 `https://www.tnpb.app/` 的 TEEP CNN/RNN 预测；没有本地权重、缓存或版本锁定 |

## 选用对比

On-target 模型：

| 模型 | 用途 | 特点 | 优点 | 缺点 |
| --- | --- | --- | --- | --- |
| CROPSR | Cas9 on-target | 已发表的 Doench/CROPSR 逻辑回归系数；对 30mer 窗口计算，长窗口取最佳 30mer | 纯数值计算，速度快、无外部依赖、结果可复现 | 只面向 Cas9/30mer 结构，非标准窗口会退回启发式 |
| Azimuth V3 nopos | Cas9 on-target | GBDT 回归（100 棵树），含 order1/order2、GC、NGGX、Tm 特征 | 参考验证好（Spearman 0.993）；不依赖旧版 sklearn | 当前不是默认入口；训练数据年代较早 |
| DeepCpf1 | Cas12a/Cpf1 on-target | 序列 CNN 模型，HDF5 权重 | 面向 Cas12a/Cpf1 的专项模型 | 需显式选择；输入不足 34 bp 时回退启发式 |
| TEEP | ISDra2 TnpBmax on-target | 在线 CNN + Bi-LSTM API，预测 20 nt 引导序列 | 针对 ISDra2/TnpBmax 的专项预测 | 需要网络、逐条查询较慢；失败时退回通用启发式，不会退回 omegaRNA 规则 |
| omegaRNA 规则 | TnpB on-target 编辑效率 | 本地确定性规则：长度、GC、发夹、repeat | 离线可用、快速、稳定 | 是简化规则，不是训练模型；属 on-target 效率规则，不是特异性评分 |
| Cas13 RNA 规则 | Cas13a/b/d on-target | 有 ViennaRNA 时计算 accessibility、MFE、DR-spacer、靶 RNA 扰动；无则用 U/A 富集启发式 | 可解释、离线可用、包含 RNA 结构信息 | 质量依赖 ViennaRNA 是否安装，启发式部分较粗 |
| TIGER | Cas13d on-target | TensorFlow SavedModel，对 23 nt spacer 给出 0-1 活性分数；有 `target_rna`+`spacer_start` 时自动抠 3 nt 上游上下文 | 23 nt Cas13d 专项预测，准确性优于简化规则 | 只适用于 23 nt spacer；需要 TensorFlow 运行时 |
| 内置启发式 | 通用 on-target | GC、seed GC、homopolymer、复杂度加权 | 任何输入都能出分，速度最快 | 精度最低，只适合兜底 |

Off-target 模型：

| 模型 | 用途 | 特点 | 优点 | 缺点 |
| --- | --- | --- | --- | --- |
| CFD | Cas9 off-target | 位置特异错配表 + PAM 权重 | 极快、无需模型文件、稳定 | 非学习模型，主要面向 SpCas9 |
| CRISPR-M | Cas9 off-target | 多头注意力 + 卷积 + 双向 LSTM，NumPy 前向 | 对 off-target 排序能力通常优于 CFD；无需 TensorFlow | 需要约 20MB 模型文件；推理比 CFD 慢 |
| DeepCRISPR | Cas9 off-target | CNN 模型，已转为 portable NumPy | 免 TensorFlow，权重转换已验证 | 需要 portable 模型文件；推理较慢 |
| crispAI | Cas9 off-target | uncertainty-aware 聚合模型，外部适配器调用上游 agg-score | 输出保留后验不确定性信息 | 需要 R/NuPoP、Cas-OFFinder、GRCh38；见 `docs/CRISPAI.md` |
| identity/preset 启发式 | 非 Cas9 off-target | 序列相似度 + seed 惩罚 | 无需模型，快速覆盖 Cas12/Cas13/TnpB | 近似评分，缺少学习模型精度 |
| TIGER | Cas13d off-target | 对每个 off-target spacer 用 TIGER 打分并按 `1/(1+sum)` 聚合；模型不可用时回退 PFS 规则 | 23 nt Cas13d 专项 off-target 活性评估 | 只适用于 23 nt spacer；需要 TensorFlow 运行时 |

## CRISPR-M

`tcrispr_model.h5` 是 CRISPR-M 的 Keras HDF5 权重文件。`shared/scoring/deep_models.py` 已实现
纯 NumPy 前向（embedding、多头注意力、卷积、BatchNorm、双向 LSTM、Dense），
不需要 TensorFlow。

验证结果：

```text
guide:    GAACACAAAGCATAGACTGC
off:      GAACACAAAGCATAGACTGA
pam:      NGG
score:    0.6321092247962952
```

## DeepCRISPR

`deepcrispr_offtar_pt_cnn_reg.tar.gz` 解压后为：

```text
offtar_pt_cnn_reg/
  checkpoint
  model.ckpt-ptreg.index
  model.ckpt-ptreg.data-00000-of-00001
```

`checkpoint` 内容为 `model_checkpoint_path: "model.ckpt-ptreg"`。该格式需要
TensorFlow 1.x（或 TensorFlow 2.x 的 `tf.compat.v1`）读取。当前主环境没有
TensorFlow，因此状态是“文件已下载但运行时不可用”。

`deepcrispr_offtar_pt_cnn_reg.portable.npz` 是从 checkpoint 导出的 NumPy 权重。
`shared/scoring/deepcrispr_forward.py` 实现了 23 nt 序列编码、8 通道特征（4 个 one-hot +
4 个可选的表观通道）和完整 CNN 前向；与 TensorFlow 参考图在 100 条官方示例上的
最大输出误差为 `2.98e-7`。

## DeepCpf1

`seq_deepcpf1_weights.h5` 是 DeepCpf1 的序列-only Cas12a/Cpf1 on-target 权重。
`shared/scoring/deepcpf1_forward.py` 实现纯 NumPy 前向：34 bp one-hot 输入
（4 bp upstream + TTTV PAM + 23 bp protospacer + 3 bp downstream）、
Conv1D(80, 5)、AveragePooling1D(2)、Flatten，再依次经过 80 -> 40 -> 40 -> 1
的 Dense 层；Dropout 在推理时恒等。加载时沿长度轴反转卷积核以匹配原
Theano/Keras 权重布局。官方两条样例的输出为 `55.699318 / 53.469837`，当前
NumPy 前向输出为 `55.699310 / 53.469837`，误差在浮点舍入范围内。

DeepCpf1 输出是原始编辑效率回归值，不是 0-1 概率。选择 `deepcpf1` 后，该值
会作为 Cas12a 的 on-target 分数写入 `on_target_score`，原始模型值同时写入
`deepcpf1_on_target`；模型未就绪或输入不足 34 bp 时回退启发式并标记
`deepcpf1_fallback`。

## Azimuth

`azimuth_V3_model_nopos.pickle` 是 Azimuth V3 `nopos` 模型的旧版 scikit-learn
pickle。pickle 内引用 `sklearn.ensemble.gradient_boosting.GradientBoostingRegressor`；
该模块路径在 scikit-learn 1.1+ 被移除，直接加载会报：

```text
ModuleNotFoundError: No module named 'sklearn.ensemble.gradient_boosting'
```

因此需要在 Python 3.10 备用环境安装 `scikit-learn==1.0.2` 后加载，再转成
不依赖旧模块路径的可移植格式。

`azimuth_V3_model_nopos.portable.npz` 包含 100 棵回归树和特征顺序。
`shared/scoring/azimuth_predictor.py` 在纯 NumPy 下复刻 V3 `nopos` 的 30mer 特征：
order1/order2 核酸特征、GC、NGGX 和 SantaLucia Tm。
官方 `1000guides.csv` 参考中 561/947 条完全一致，整体 Spearman 0.993、
MAE 0.0073；残余差异来自官方参考与当前仓库保存模型之间的版本漂移
（Azimuth 自带的测试注释也声明预测可能因模型随机性失败）。

## TIGER (Cas13d)

`models/tiger/` 存放 TIGER（Cas13d on/off-target 深度学习模型）的 TensorFlow
SavedModel 以及两组校准参数：

```text
models/tiger/
  model/
    saved_model.pb
    keras_metadata.pb
    fingerprint.pb
    variables/
      variables.index
      variables.data-00000-of-00001
  scoring_params.pkl
  calibration_params.pkl
```

TIGER 原始权重由 TensorFlow 2.11 保存，官方代码用
`tf.keras.models.load_model('model')` 加载。在 TensorFlow 2.2x / Keras 3
（服务器 `.venv` 当前为 TensorFlow 2.21 / Keras 3.15）中该调用会报
“不支持的格式”。`shared/scoring/tiger_model.py` 改用版本无关的
`tf.saved_model.load` 读取，再按 serving signature 调用；若该路径不可用，
会回退到 `keras.layers.TFSMLayer`。

模型签名（已在服务器上验证）：

```text
input:  sequence_sequential_with_non_sequence_bypass_input  float32 (None, 208)
output: dense_2                                              float32 (None, 1)
```

输入是两段并排的 26 位置 one-hot（target 通道 + guide 通道，guide 通道前 3 个
`N` 上下文补零），共 208 列。`shared/scoring/tiger_model.py` 用纯 NumPy 复现
该编码、校准（`calibration_params.pkl` 的 slope 乘子，按错配数取）和 sigmoid
评分映射（`scoring_params.pkl` 的 `a`/`b`：`1 - 1/(1+exp(a*lfc+b))`）。

注意朝向约定：本工具存的 `guide_seq` 是目标序列上的**正向 protospacer**（不是
crRNA 互补序列），所以 TIGER 的 target 通道是 `NNN + 该引导`，guide 通道是
`NNN + complement(该引导)`。`build_input_vector` 以此为基准；当传入
`target_rna` 与 `spacer_start` 时，`build_target_window` 会从靶序列里自动抠出
真实的 3 nt 上游上下文来构造 26 nt 窗口（而不是用 `N` 补零），提高 23 nt
Cas13d 靶点的评分精度。

注册表键为 `tiger`，`role=on_target`，`runtime=tensorflow`，`scope` 覆盖
`cas13` / `cas13d`。由于 TIGER 同时给出 on/off-target 活性，Cas13 preset 下
选择 `tiger` 会同时用于 `on_target_score` 与 `off_target_specificity`，并把
原始 TIGER 分数写入 `tiger_on_target` / `tiger_off_target` 两列。

模型下载走 Hugging Face 的 `resolve` 接口并通过国内镜像 `hf-mirror.com`
逐文件下载（不使用 `git clone` / `git lfs pull`），见
`shared/scoring/model_registry.py` 的 `_download_model_dir`。

## TnpB：本地 omegaRNA 规则与在线 TEEP

`models/` 中没有 TnpB 的本地深度学习权重。当前 TnpB 有两条不同路径：

- 默认 `omega` 使用 `shared/scoring/tnpb_scoring.py` 的
  `omega_rna_rules`。它是长度、GC、guide 发夹和 direct-repeat 发夹组成的
  本地确定性规则，输出 0-1 启发式分数，不是 TEEP 的复现。
- 显式选择 `teep` 时，`shared/scoring/scoring.py` 向
  `https://www.tnpb.app/` POST 20 nt 左右的引导序列，读取返回的
  `CNN_pred` 和 `RNN_pred`，分别除以 100 后取可用值平均，再限制到 0-1。
  请求超时、异常或缺字段时回退 `heuristic_on_target_score()`，不是回退
  `omega_rna_rules`。在线服务不进入本目录，也没有下载/删除按钮。

TEEP 的直接文献是：

> Marquart KF, Mathis N, Mollaysa A, et al. Effective genome editing with an
> enhanced ISDra2 TnpB system and deep learning-predicted ωRNAs.
> *Nature Methods* 21, 2084-2093 (2024).
> DOI: <https://doi.org/10.1038/s41592-024-02418-z>

ISDra2 TnpB/omegaRNA 和 TAM 的基础文献还包括 Karvelis et al., *Nature*
599, 692-696 (2021), DOI
<https://doi.org/10.1038/s41586-021-04058-1>，以及 Altae-Tran et al.,
*Science* 374, 57-65 (2021), DOI
<https://doi.org/10.1126/science.abj6856>。TnpB 的公式、适用边界和完整输出
字段见 `docs/TNPB.md`。

### PFS 兜底（CFD 风格的 Cas13 规则）

当 TIGER 不可用（未下载或运行时缺失）时，Cas13 会回退到
`shared/scoring/cas13_scoring.py` 的 PFS 规则，起与 CFD 之于 Cas9 相同的兜底
作用：on-target 用 `cas13_pfs_on_target_score`（PFS + U/A 富集确定性评分），
off-target 用 `cas13_pfs_off_target_specificity`（按
`identity * PFS 权重` 逐对累加后取 `1/(1+sum)`）。PFS 基取靶序列 5' 端
紧邻 protospacer 的碱基；符合 preset 的 `H`（A/C/U 非 G）得 1.0，`G` 被强
惩罚，未知则中性 0.5。

## 状态定义

Phase 1 会把注册表状态从“文件存在且大小匹配”细化为：

| 状态 | 含义 |
| --- | --- |
| `not_downloaded` | 模型文件未下载 |
| `load_error` | 文件存在但无法加载 |
| `ready` | 文件存在且运行时可加载 |
| `prediction_error` | 已加载但推理失败 |
