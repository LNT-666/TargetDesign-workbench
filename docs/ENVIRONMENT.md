# Python 环境复现说明

本项目的运行环境分为主环境和模型转换环境：

- **Python 3.12 主环境（默认）**：CI 与 Docker 使用该版本，日常运行、评分、GUI 和测试以它为准。
- **Python 3.13 支持环境**：可以运行主流程，但不是 CI/Docker 的默认版本。
- **Python 3.10 模型转换环境**：只用于旧模型文件的一次性转换，不参与日常评分。

机器可读的 Python 版本约束记录在仓库根目录的 `pyproject.toml`：

```text
requires-python = ">=3.12,<3.14"
```

## 1. 主环境（Python 3.12，3.13 可选）

Windows 下创建并激活：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements-windows.txt
```

Linux / macOS 下对应为：

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements-linux.txt
```

`requirements-linux.txt` 是兼容的完整环境入口，会同时安装基础依赖、模型栈和 crispAI
的 Python 依赖。需要 Python 3.13 时，把上面的 `3.12` 替换为 `3.13`，但不要把 3.13
当作 CI/Docker 的默认解释器。

主环境已验证可用的核心依赖：

| 包 | 用途 |
| --- | --- |
| numpy | CRISPR-M NumPy 前向、评分矩阵运算 |
| h5py | 读取 `tcrispr_model.h5` |
| biopython / pyfaidx | FASTA、基因组和注释处理 |
| openpyxl | Excel 输出 |

运行全部测试：

```powershell
python run_tests.py
```

或：

```powershell
python -m unittest discover -s tests -v
```

## 2. 模型转换环境（Python 3.10）

模型转换环境不应与主环境混用。建议使用独立虚拟环境。共享盘上的 pip 安装较慢时，
可把虚拟环境放在本机磁盘，例如
`<local disk>\.venvs\...`。

### DeepCRISPR 转换

Web 或桌面端的模型设置会先取得原始 tar.gz，再由
`shared/scoring/deepcrispr_convert.py` 直接解析 TensorFlow checkpoint 并生成
portable npz。这条链路只依赖 NumPy，不需要 TensorFlow，也不需要额外的转换环境；
转换完成后模型状态为 `ready`。如果本地只有原始 tar.gz 而 portable npz 缺失，
状态会显示 `needs_conversion`，重新执行该模型的下载即可补做转换。

只有在修改转换器或前向实现、需要重新做 TensorFlow 参考校验时，才建议使用下面的
隔离环境。人工脚本会用 `tf.compat.v1` 读取 checkpoint、导出权重，并比较
NumPy 前向与 TensorFlow 参考图的输出：

```powershell
py -3.10 -m venv .venv310-tf
.\.venv310-tf\Scripts\activate
pip install tensorflow==2.10.0
python tools\convert_deepcrispr.py
```

Linux / macOS 对应为：

```bash
python3.10 -m venv .venv310-tf
source .venv310-tf/bin/activate
pip install tensorflow==2.10.0
python tools/convert_deepcrispr.py
```

`tools/convert_deepcrispr.py` 是可选的人工校验路径，不是正常下载所必需。转换完成后，
模型始终以 portable npz 运行，不再依赖 TensorFlow。

## 3. 固定版本安装与 CPU-only / CUDA 安装

Linux x86_64 的 CPU-only / CUDA 快照支持 Python >=3.12,<3.14，并在推荐版本 Python 3.12
上验证。两份快照由已安装并通过检查的环境生成，不是手工编写的版本猜测：

- `requirements/constraints-linux-cpu.txt`：已验证的 Linux CPU 环境，Python 3.12.3、pip 26.2.1；`pip check`
  通过，内存限制 14 项、索引 10 项、依赖扫描 2 项测试通过。
- `requirements/constraints-linux-cuda.txt`：已验证的 RTX 4090 Linux GPU 环境，驱动 565.57.01、Python 3.12.7、
  pip 26.2.1；torch 2.10.0 CUDA 与 TensorFlow 2.20.0 的 GPU 张量运算、关键 import 和
  `pip check` 均通过。

两份快照都包含完整传递依赖。CI 和容器 `core` 层只安装 `requirements.txt`，但会通过
`-c requirements/constraints-linux-cpu.txt` 固定其中的包版本。

### CPU-only

CPU-only 环境不要求 NVIDIA 驱动。使用 CPU wheel 索引安装完整环境：

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -c requirements/constraints-linux-cpu.txt \
  -r requirements/requirements-linux-cpu.txt \
  --extra-index-url https://download.pytorch.org/whl/cpu
```

快照固定 `torch==2.10.0+cpu`；TensorFlow 使用相同 Python 3.12 环境中的已测试版本。
无需设置 CUDA 环境变量。

### CUDA

CUDA 环境需要与所选 wheel 匹配的 NVIDIA 驱动。先确认驱动和 GPU，再安装 GPU 快照：

```bash
nvidia-smi
python -m pip install -c requirements/constraints-linux-cuda.txt \
  -r requirements/requirements-linux-cuda.txt
```

该快照固定 `torch==2.10.0`、`tensorflow==2.20.0` 及匹配的 CUDA/NCCL 传递依赖。上述组合
已在 RTX 4090 Linux GPU 环境实际执行 torch 和 TensorFlow GPU 矩阵运算。升级驱动或 CUDA
组件前，请重新运行 GPU 验证并更新快照。

`pybdm` 仍导入 `pkg_resources`，因此 `requirements-crispai.txt` 明确要求
`setuptools<81`；两份快照都固定了已验证的 setuptools 版本。

## 4. 可选依赖

### scikit-learn（可选离线分析）

主运行流程不要求 scikit-learn。它仅作为离线分析与配图的可选依赖保留在完整
requirements 中；没有当前模型预测器依赖它。

### ViennaRNA（Cas13 RNA 可及性）

Cas13 的 RNA 可及性评分依赖 ViennaRNA。Linux/macOS 可用 conda 安装：

```bash
conda install -c bioconda viennarna
```

也可安装 Python 绑定：

```bash
pip install ViennaRNA
```

Windows 建议在 WSL 中安装。未安装时评分自动回退到确定性的
`cas13_u_rich` / `cas13_a_rich` 启发式，`rna_features` 中的结构值为 `None`，
不会中断流程；评分字段与行为见 `docs/SCORING_GUIDE.md`。

### 其它可选工具

```powershell
pip install requests
```

## 5. 模型目录

模型文件统一放在 `models/`，真实可用状态见 [MODELS.md](MODELS.md)。

## 6. Off-target 引擎

脱靶搜索引擎的统一接口、外部工具依赖和引擎差异对比方法见
[OFFTARGET_ENGINES.md](OFFTARGET_ENGINES.md)。
