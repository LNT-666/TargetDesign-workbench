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
| `h5py` | 读 DeepCpf1 / DeepCRISPR 的 HDF5 权重 | 对应深度模型报不可用 |
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
| Cas-OFFinder | crispAI 聚合打分 | micromamba/bioconda，或用 `CRISPAI_CASOFFINDER_DIR` 指向可执行文件 |
| R + NuPoP | crispAI 的核小体占据/亲和注释 | R >= 4.3 需从 Bioconductor 装，见 docs/CRISPAI.md |
| `curl` | 模型权重下载，`shared/scoring/model_registry.py` | 系统包 |
| 参考基因组与索引 | 实际搜索 | 用户自备，`example/`、`genome_index/` 不入库 |
| 模型权重 | 深度打分模型 | 不随仓库分发，见 docs/MODELS.md |

## 3. requirements 文件与镜像目标

| 位置 | 内容 | 备注 |
| --- | --- | --- |
| `requirements.txt` | biopython, pyfaidx, requests, openpyxl, numpy, h5py | 已验证的运行必需集合；容器 `core` 层只装它 |
| `requirements-linux.txt` | 以上 + torch, tensorflow, ViennaRNA, pandas, scipy, scikit-learn, matplotlib, tensorboardX, 以及 crispAI 的 pybdm/genomepy/jax/numpyro/tqdm/seaborn | 服务器/桌面全功能 |
| `requirements-windows.txt` | 同上，Windows 变体 | 桌面 |
| 镜像 `core` | 只装 `requirements.txt` | 经典管线 + native 引擎 + h5py 深度模型；没有 torch/tensorflow/ViennaRNA |
| 镜像 `full` | core + ViennaRNA + Cas-OFFinder + R/NuPoP + CPU torch | 仍不含 tensorflow 与 crispAI 的 Python 依赖，所以 TIGER 与 crispAI 在容器里不可用 |

## 4. 只在离线论文工作流里需要

这些包在 `requirements-linux.txt` / `requirements-windows.txt` 里声明，但仓库里没有任何
模块导入它们。删掉会打断论文配图与模型转换的离线脚本（脚本在 `docs/figures/`、
`external_tools/`，不入库），因此保留：

| 包 | 谁在用 |
| --- | --- |
| `matplotlib` | `docs/figures/` 的配图脚本（不入库） |
| `scikit-learn` | 一次性 Azimuth 转换，见 docs/ENVIRONMENT.md |
| `scipy` | 离线分析辅助 |
| `tensorboardX` | 离线模型转换的训练日志 |
| `pybdm`、`genomepy`、`jax`、`numpyro`、`tqdm`、`seaborn` | 上游 crispAI 脚本（`external_tools/crispAI-main`，不入库） |

## 5. 维护规则

1. 新增第三方导入：硬导入必须在 `requirements.txt` 里声明，软导入至少要在
   `requirements-linux.txt` 里声明，否则 `tools/dep_scan.py --check` 失败，CI 的
   `container` 工作流会拦在构建之前。
2. 新增本地模块：必须提交进 git。`--check` 会报 `UNTRACKED LOCAL MODULE` —— 漏提交的
   文件在 clone 里不存在；`shared/output/` 正是这样让容器 smoke test 报
   `ModuleNotFoundError: No module named 'output'` 的。
3. 容器只装 `requirements.txt`。要在镜像里跑深度模型或 Cas13，需要单独扩展 `full` 层。