# Python 环境复现说明

本项目的可复现运行环境分成两个层次：

- **Python 3.13 主环境**：日常运行、评分、GUI、Library 流程和测试都在这里。
- **Python 3.10 备用环境**：只负责加载旧版模型文件并转成可移植格式，例如
  Azimuth 的旧 scikit-learn pickle 和 DeepCRISPR 的 TensorFlow 1.x checkpoint。

## 1. 主环境（Python 3.13）

Windows 下创建并激活：

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

Linux / macOS 下对应为：

```bash
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

主环境已验证可用的核心依赖：

| 包 | 用途 |
| --- | --- |
| numpy | CRISPR-M NumPy 前向、评分矩阵运算 |
| h5py | 读取 `tcrispr_model.h5` |
| biopython / pyfaidx | FASTA、基因组和注释处理 |
| openpyxl | Excel 输出 |
| scikit-learn | 当前版本可用于其它评分逻辑，但不能直接加载旧 Azimuth pickle |

运行全部测试：

```powershell
python run_tests.py
```

或：

```powershell
python -m unittest discover -s tests -v
```

### 已记录的测试运行

仓库内跟踪的一次完整测试套件运行（Windows x64 工作站，Python 3.14.7）：

```text
python run_tests.py
Ran 339 tests in 1297.947s
FAILED (errors=1, skipped=6)
```

- 唯一的 error 来自该机器未安装 `blastn`（环境问题，非本项目代码缺陷）：
  `test_auto_and_large_indexed_apply_mismatch_only_defaults` 报
  `auto could not find an engine compatible with max_bulge=0`。
- 6 个 skip = 5 个 TIGER/TensorFlow 不可用 + 1 个 Linux 专用用例
  `test_parent_death_kills_the_engine`（依赖 `/proc/<pid>/stat`）。

该记录即提交稿 Implementation, interface and test suite 一节所引用的测试运行。

## 2. 备用环境（Python 3.10）

备用环境用于模型转换，不参与日常评分。创建方式：

```powershell
py -3.10 -m venv .venv310
.\.venv310\Scripts\activate
pip install numpy==1.23.5 pandas==1.5.3 scikit-learn==1.0.2 biopython==1.79
```

如果项目位于网络共享盘（例如 `\\fileserver\share\...`），建议把备用环境建在
本地磁盘上，否则 pip 安装会非常慢：

```powershell
py -3.10 -m venv <local disk>\.venvs\crispr310
<local disk>\.venvs\crispr310\Scripts\activate
pip install numpy==1.23.5 pandas==1.5.3 scikit-learn==1.0.2 biopython==1.79
```

备用环境放在本机磁盘的任一可写路径即可（例如 `<user>` 主目录下的 `.venvs\crispr310`）。

在 Linux / macOS 上，DeepCRISPR 直接推理还需要 TensorFlow 1.x：

```bash
python3.8 -m venv .venv38
source .venv38/bin/activate
pip install tensorflow==1.15
```

## 3. 可选依赖

### TensorFlow（DeepCRISPR 转换）

Windows 上推荐 Python 3.10 + TensorFlow 2.10，用 `tf.compat.v1` 读取 checkpoint：

```powershell
py -3.10 -m venv .venv310
.\.venv310\Scripts\activate
pip install tensorflow==2.10.0
```

Linux / macOS 上需要读取原始 TF1 checkpoint 时，可用 Python 3.7/3.8 +
`tensorflow==1.15`。转换完成后，推理路径不再依赖 TensorFlow。

### scikit-learn（Azimuth 转换）

`models/azimuth_V3_model_nopos.pickle` 是旧版 scikit-learn 的 pickle，内部引用
`sklearn.ensemble.gradient_boosting` 模块路径；scikit-learn 1.1+ 已移除该路径，因此
转换阶段必须使用旧版本：

```powershell
pip install scikit-learn==1.0.2 pandas
```

转换完成后生成的可移植模型文件可在主环境（任意 scikit-learn 版本）直接使用。

执行转换：

```powershell
python tools\convert_azimuth.py --order "gc_count,_nuc_pd_Order2,_nuc_pd_Order1,gc_above_10,_nuc_pi_Order1,_nuc_pi_Order2,Tm,NGGX,gc_below_10"
python tools\convert_deepcrispr.py
```

`convert_deepcrispr.py` 会用 TensorFlow 参考图对 NumPy 前向做一致性校验；
`convert_azimuth.py` 会使用仓库内的官方 `1000guides.csv` 校验特征顺序。

### ViennaRNA（Phase 4 的 RNA 可及性计算）

Linux / macOS 推荐：

```bash
conda install -c bioconda viennarna
```

或从源码安装：

```bash
pip install ViennaRNA
```

Windows 原生支持有限，建议在 WSL 或 Linux 容器中安装。

### 其它可选工具

```powershell
pip install requests
```

## 4. 模型目录

模型文件统一放在 `models/`，真实可用状态见 [MODELS.md](MODELS.md)。

## 5. Off-target 引擎

脱靶搜索引擎的统一接口、外部工具依赖和引擎差异对比方法见
[OFFTARGET_ENGINES.md](OFFTARGET_ENGINES.md)。
