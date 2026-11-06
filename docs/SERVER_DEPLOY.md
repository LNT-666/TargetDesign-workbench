# 服务器部署与 GRCh38 全基因组构建

推荐在 Linux 服务器上从完整源码部署，并优先使用
`native/bin/offtarget-engine` 构建和搜索索引；下面的 Python
`tools/server_build_index.sh` 流程是二选一的 fallback。服务器建议配置：

- Linux，Python 3.12（支持到 3.13，见 `pyproject.toml`）
- 内存 64 GB+（全基因组构建峰值约 50–64 GB）
- 磁盘至少预留 40 GB
- 已有 GRCh38 FASTA；没有的话先上传，3.3 GB 文件建议走内网或共享盘

## 1. 推荐：完整源码部署

### 1.1 从干净目录克隆

在服务器上从空目录开始，一次取得 Python 入口、全部递归依赖和 native
源码：

```bash
git clone https://github.com/LNT-666/TargetDesign-workbench.git /data/crispr_tool
cd /data/crispr_tool
```

如果服务器使用仓库的 SSH 地址，也可以把 clone 地址换成
`git@github.com:LNT-666/TargetDesign-workbench.git`。后续命令都从
`/data/crispr_tool` 执行。

不能从服务器 clone 时，可在本地工程目录上传完整源码树。下面的命令需要
本机 WSL/Git Bash 提供 `rsync`，服务器也需要安装 `rsync`：

```bash
ssh user@server 'mkdir -p /data/crispr_tool'
rsync -av \
  --exclude '.venv*' \
  --exclude 'native/build*' \
  --exclude 'native/bin/' \
  --exclude 'example/GRCh38.fna' \
  --exclude 'example/grch38_server_result/' \
  ./ user@server:/data/crispr_tool/
```

不要上传本地 `.venv*`、`native/build*`、`native/bin/` 中的 Windows 产物、
3.3 GB 测试 FASTA 或其他生成结果。若确实要上传预编译 native，只允许传
与目标 Linux OS/CPU ABI 兼容的 `native/bin/offtarget-engine`，见第 3 节。

### 1.2 最小上传/离线上传

只有无法 clone 或必须走离线介质时才使用此方案。最小清单必须同时包含
Python 运行、递归依赖和 native 构建输入，不能只传 `shared/`、`tools/` 和
一个 `requirements.txt`。

公共必需路径：

```text
shared/
tools/
requirements.txt
requirements-linux.txt
requirements-models-linux.txt
requirements-crispai.txt
pyproject.toml
```

native 构建二选一：

```text
方案 A（目标机从源码构建）
native/CMakeLists.txt
native/offtarget_engine/CMakeLists.txt
native/offtarget_engine/src/
native/offtarget_engine/include/
native/offtarget_engine/tests/

方案 B（上传兼容 Linux 的预编译二进制）
native/bin/offtarget-engine
```

方案 A 中的 `native/CMakeLists.txt` 是 native 顶层入口，
`native/offtarget_engine/` 是实际 CMake 源目录。方案 B 的二进制必须与
目标机 OS、CPU 架构和系统 ABI 兼容，不能上传 Windows `.exe` 后当作
Linux binary。若无法逐项复制完整清单，请删除本方案并回到完整源码部署。

## 2. 安装 Python 依赖

使用 Python 3.12 创建独立虚拟环境：

```bash
cd /data/crispr_tool
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-linux.txt
```

必须在源码根目录执行安装命令，让 `requirements-linux.txt` 能递归读取
`requirements.txt`、`requirements-models-linux.txt` 和
`requirements-crispai.txt`。
`python-docx` 只服务 `run_tests.py` 的稿件密封检查；缺它时该测试模块会明确
skip，不是收集期报错。

### 可选：使用 conda 前缀

conda 环境可以放在源码树外，例如 `/data/conda-envs/targetdesign`：

```bash
conda create -p /data/conda-envs/targetdesign python=3.12 pip
conda activate /data/conda-envs/targetdesign
cd /data/crispr_tool
python -m pip install -r requirements-linux.txt
```

如果部署策略要求前缀靠近源码树，可以直接放在项目内；测试会通过前缀中的
`conda-meta/`（或 venv 的 `pyvenv.cfg`）识别并跳过环境目录。不要把 conda 前缀提交到仓库，
也不要把安装在其中的 Python 或原生库移动到别的路径。

## 3. Native 引擎：构建或使用兼容二进制

native 编译本身需要 CMake 3.20+、支持 C++20 的编译器和 native 源码；第 2
节的 Python 环境用于后续 Python 集成，不是编译 native core 的前置条件。以下
命令使用现有 native 源码目录，并把 release 二进制输出到
`native/bin/offtarget-engine`：

```bash
cd /data/crispr_tool
cmake -S native/offtarget_engine -B native/build \
  -DCMAKE_BUILD_TYPE=Release
cmake --build native/build -j
```

不使用源码构建时，可以改用预编译 Linux 二进制。它必须与目标 OS/CPU ABI
兼容，放到固定路径并具有执行权限：

```bash
cd /data/crispr_tool
mkdir -p native/bin
install -m 0755 /path/to/linux/offtarget-engine native/bin/offtarget-engine
file native/bin/offtarget-engine
```

不要把 Windows `native/bin/offtarget-engine.exe` 改名后用于 Linux。

## 4. Native 构建 GRCh38 索引

native 索引步骤只使用上一节生成的二进制和 GRCh38 FASTA，不调用 Python
fallback 脚本，也不会自动安装 fallback 的基础依赖：

```bash
cd /data/crispr_tool
mkdir -p /data/grch38_out/genome_index
native/bin/offtarget-engine build-index \
  --genome /data/GRCh38.fna \
  --prefix /data/grch38_out/genome_index/GRCh38 \
  --k 12 --threads 16
```

## 5. Python fallback（与 native 二选一）

只有不使用 native 引擎时才走本节。fallback 构建索引所需的输入是：

- `shared/`；
- `tools/server_build_index.sh` 和它调用的 `tools/build_genome_index.py`；
- 带 guides 参数搜索时另需 `tools/search_indexed.py`；
- 可由脚本读取的 GRCh38 FASTA；
- Linux 的 `bash`、`python3` 和 venv 模块。

脚本会在源码根目录创建 `.venv_server`，自动安装基础依赖
`numpy`、`biopython`、`pyfaidx`，然后构建索引。它不使用已构建的 native
二进制；下面显式关闭 native 选择，保证后续搜索也走 Python：

```bash
cd /data/crispr_tool
PROGRAMFILE_NATIVE_INDEXED=0 \
  bash tools/server_build_index.sh /data/GRCh38.fna /data/grch38_out
```

结果仍写到 `/data/grch38_out/genome_index/`。脚本用 FASTA basename 作为
索引前缀，所以上述输入会得到：

```text
/data/grch38_out/genome_index/GRCh38.fna.ggi
/data/grch38_out/genome_index/GRCh38.fna.json
```

构建日志继续输出 `INDEX_READY` 和 `REPORT_JSON` 两行；对应的 `.json`
文件包含运行时间、内存峰值、位置数量等报告。若 FASTA 文件名不同，以日志
中两行给出的实际前缀为准。

## 6. Python fallback 的真实搜索验证

把 guide 列表传到服务器，例如 `guides.tsv`：

```text
qid	guide_seq
demo	GCCTTGGCCTCCTAAAGTGC
```

```bash
cd /data/crispr_tool
PROGRAMFILE_NATIVE_INDEXED=0 \
  bash tools/server_build_index.sh /data/GRCh38.fna /data/grch38_out guides.tsv
```

搜索输出在 `/data/grch38_out/search/top_offtargets.tsv`，
报告在 `/data/grch38_out/search/index_report.json`。

## 7. 长任务放后台

构建可能要几十分钟到数小时，建议用 nohup。native 路径使用：

```bash
cd /data/crispr_tool
nohup native/bin/offtarget-engine build-index \
  --genome /data/GRCh38.fna \
  --prefix /data/grch38_out/genome_index/GRCh38 \
  --k 12 --threads 16 \
  > /data/grch38_native.log 2>&1 &
tail -f /data/grch38_native.log
```

Python fallback 路径使用：

```bash
cd /data/crispr_tool
PROGRAMFILE_NATIVE_INDEXED=0 \
nohup bash tools/server_build_index.sh /data/GRCh38.fna /data/grch38_out \
  > /data/grch38_build.log 2>&1 &
tail -f /data/grch38_build.log
```

## 8. 取回结果（本机 PowerShell）

```powershell
scp -r user@server:/data/grch38_out <本地工程目录>\example\grch38_server_result
```

之后本机 Library 流程可以直接复用：

```powershell
python shared\design\library_pipeline.py regions.tsv example\GRCh38.fna outdir `
  --engine indexed --index-path example\grch38_server_result\genome_index\GRCh38
```

## 其他选择

- 只有 Windows 服务器：直接跑 `python tools\build_genome_index.py`，但需要
  64 GB+ 内存，且 Python 依赖用 `pip install numpy biopython pyfaidx`。
- 没有现成服务器：租一台 64 GB 内存的云主机（阿里云、腾讯云、AWS 等），
  把 FASTA 放到数据盘再执行同一套命令。
- 内存仍然不够：用 `--contigs NC_000021.9` 等参数逐条染色体构建，
  或用后续的 FM-index/Rust 扩展后端降低峰值内存。
