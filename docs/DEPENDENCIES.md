# 依赖清单

检查日期：2026-10-07。本文件由导入图推导，不手工维护——改动依赖后请重新生成：

    python tools/dep_scan.py            # 清单 + 漂移报告
    python tools/dep_scan.py --check    # 有漂移就返回 1；CI 的 container 工作流会跑这一步

`tools/dep_scan.py` 静态解析 AST，不导入任何模块，所以不需要先装依赖。它扫描 git
跟踪的全部 `*.py`，入口取 `webapp/app.py`、`main.py`、`designer_workbench.py`、
`unified_gui.py` 以及 `tools/`、`basic/`、`Target_xbp_*` 下的脚本。「硬导入」指模块级、
不在 `try:` 里的导入，缺了直接 `ImportError`；「软导入」指函数内导入，或被
`try/except ImportError` 兜住的导入。

## 1. Python 依赖

### 1.1 硬依赖（缺失则启动失败）

| 包 | 用在哪 |
| --- | --- |
| `numpy` | `shared/scoring/deep_models.py`、`deepcpf1_forward.py`、`deepcrispr_forward.py`、`tiger_model.py`、`shared/search/genome_index.py` —— 全部 Python 入口的模块级依赖 |
| `biopython`（`Bio`） | `basic/extract.py`、`basic/blast.py`、`basic/analyze_scores.py`、`Target_xbp_*`；`shared/design/guide_design.py` 与 `shared/design/library_pipeline.py` 里是软导入 |
| `pyfaidx` | `Target_xbp_Y_zbp_Target/extract_motifs.py`（模块级）；`shared/data/local_extract.py`、`shared/search/exact_offtarget.py` 里是软导入 |

### 1.2 软依赖（缺了只有对应功能不可用）

| 包 | 用途 | 缺失时 |
| --- | --- | --- |
| `h5py` | 读 CRISPR-M / DeepCpf1 的 HDF5 权重；DeepCRISPR 运行时读取 portable npz | 对应深度模型报不可用 |
| `torch` | Cas12a ViT 打分（`shared/scoring/deepcas12a_model.py`，由 `deep_models.py` 在函数内导入） | Cas12a 深度模型不可用 |
| `tensorflow`（含 `keras`） | TIGER 打分模型 | TIGER 不可用 |
| `pandas` | TIGER 模型的 pickle 参数，仅 `shared/scoring/tiger_model.py` 使用 | TIGER 不可用 |
| `RNA`（ViennaRNA） | Cas13 的 RNA 折叠/可及性，`shared/scoring/rna_utils.py` | Cas13 打分退回启发式 |
| `openpyxl` | XLSX 导出，`shared/output/candidate_export.py`、`shared/output/xlsx_utils.py` | 只能导出 TSV |
| `pyfaidx` | FASTA 随机访问的加速路径 | 退回 `Bio` 读取 |
| `requests` | 参考数据下载，`shared/data/download_data.py` | 下载功能不可用 |

## 2. 非 Python 依赖

| 依赖 | 用在哪 | 获取方式 |
| --- | --- | --- |
| NCBI BLAST+（`blastn`/`makeblastdb`） | BLAST off-target 引擎：`shared/search/blast_utils.py`、`basic/blast.py`、`main.py` | 系统包或 conda |
| `offtarget-engine` | 自带的 native 索引引擎 | 由仓库 `native/` 编译（C++20 + CMake + GCC）；容器里现编后装到 `native/bin/` |
| ViennaRNA | Cas13 的 RNA 折叠 | bioconda 或 pip，见 docs/CRISPAI.md |
| Cas-OFFinder | crispAI aggregate 的全基因组脱靶搜索 | micromamba/bioconda；`CRISPAI_CASOFFINDER_DIR` 必须指向包含可执行文件的目录 |
| R + NuPoP | crispAI aggregate 的核小体占据/亲和注释 | R 包 NuPoP 需从 Bioconductor 安装；preflight 要求 Rscript 退出码 0 且输出严格为 `TRUE`，见 docs/CRISPAI.md |
| UCSC 分染色体 FASTA | Cas-OFFinder 的全基因组搜索输入 | 放在 `<CRISPAI_CASOFFINDER_DIR>/ucsc_chroms/`，至少一份 `.fa`/`.fasta`/`.fna`；不随仓库分发 |
| genomepy 全基因组资源 | crispAI 73 bp 侧翼注释 | 安装到 genomepy 本地库，或把 `CRISPAI_GENOME` 指向可解析 FASTA；还可设置 `CRISPAI_GENOME_DIR` |
| crispAI vendored 代码 + checkpoint | aggregate 外部运行器 | 均被 git 忽略，不随仓库或发布包分发；来源、默认路径和获取顺序见 docs/CRISPAI.md |
| `curl` | 模型权重下载，`shared/scoring/model_registry.py` | 系统包 |
| 参考基因组与索引 | 实际搜索 | 用户自备，`example/`、`genome_index/` 不入库 |
| 模型权重 | 深度打分模型 | 不随仓库分发，见 docs/MODELS.md |

## 3. requirements 文件与镜像目标

| 位置 | 内容 | 备注 |
| --- | --- | --- |
| `requirements.txt` | biopython, pyfaidx, requests, openpyxl, numpy, h5py | 已验证的运行必需集合；容器 `core` 层只装它 |
| `requirements-models-linux.txt` | torch, tensorflow, ViennaRNA, pandas, scipy, scikit-learn, matplotlib, tensorboardX | 模型打分、可选的 DeepCRISPR TensorFlow 参考校验与离线配图；正常下载转换不需要 TensorFlow |
| `requirements-crispai.txt` | pybdm, genomepy, jax, numpyro, tqdm, seaborn, setuptools<81 | crispAI 聚合适配器；`setuptools<81` 保留 pybdm 所需 `pkg_resources`；torch/pandas/numpy 由基础或模型依赖提供；R/NuPoP、Cas-OFFinder、UCSC FASTA、genomepy 全基因组、vendored 代码与 checkpoint 仍属外部依赖 |
| `requirements-linux.txt` | 通过 `-r` 聚合上面三个文件 | 保留为 `pip install -r requirements-linux.txt` 的兼容完整入口 |
| `requirements-windows.txt` | 同上，Windows 变体 | 桌面 |
| `requirements/constraints-linux-cpu.txt` | Linux x86_64 / Python 3.12 已测试 CPU 快照 | 来自已验证的 Linux CPU 环境：`pip check`、内存/索引/依赖扫描测试通过 |
| `requirements/constraints-linux-cuda.txt` | Linux x86_64 / Python 3.12 CUDA 快照 | 来自已验证的 RTX 4090 Linux GPU 环境：torch/TensorFlow GPU 张量运算和关键 import 通过 |
| `requirements/requirements-linux-cpu.txt` | 完整 Linux 依赖 + CPU torch 安装入口 | 与 CPU constraints 和 PyTorch CPU 索引一起使用 |
| `requirements/requirements-linux-cuda.txt` | 完整 Linux 依赖 + `tensorflow[and-cuda]` 安装入口 | 与 CUDA constraints 一起使用 |
| 镜像 `core` | 只装 `requirements.txt` | 经典管线 + native 引擎 + h5py 深度模型；没有 torch/tensorflow/ViennaRNA |
| 镜像 `full` | core + ViennaRNA + Cas-OFFinder + R/NuPoP + CPU torch | 仍不含 tensorflow 与 crispAI 的 Python 依赖，所以 TIGER 与 crispAI 在容器里不可用 |

## 4. 只在离线论文工作流里需要

这些包通过 `requirements-linux.txt` 的聚合入口或 `requirements-windows.txt` 声明，但仓库里
没有主程序模块导入它们。删掉会打断论文配图与模型转换的离线脚本（脚本在
`docs/figures/`、`external_tools/`，不入库），因此保留：

| 包 | 谁在用 |
| --- | --- |
| `matplotlib` | `docs/figures/` 的配图脚本（不入库） |
| `scikit-learn` | 离线分析与配图的可选依赖；当前公开模型流程不使用 |
| `scipy` | 离线分析辅助 |
| `tensorboardX` | 离线模型转换的训练日志 |
| `pybdm`、`genomepy`、`jax`、`numpyro`、`tqdm`、`seaborn` | 上游 crispAI aggregate 脚本；vendored 源码目录本身被 git 忽略，不随仓库分发 |

## 5. 维护规则

1. 新增第三方导入：硬导入必须在 `requirements.txt` 里声明；模型/推理软导入写入
   `requirements-models-linux.txt`，crispAI 运行时依赖写入 `requirements-crispai.txt`。
   两者均由 `requirements-linux.txt` 聚合，完整 Linux 安装入口保持不变。
2. 新增本地模块：必须提交进 git。`--check` 会报 `UNTRACKED LOCAL MODULE` —— 漏提交的
   文件在 clone 里不存在；`shared/output/` 正是这样让容器 smoke test 报
   `ModuleNotFoundError: No module named 'output'` 的。
3. 容器只装 `requirements.txt`。要在镜像里跑深度模型或 Cas13，需要单独扩展 `full` 层。
4. 修改 requirements 后运行 `python tools/check_constraints.py` 与约束测试；Linux 快照只能在
   安装、`pip check` 和聚焦测试都通过的 Python 3.12 环境中重新生成，不能手工猜版本。
