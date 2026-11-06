# crispAI 外部接入

crispAI 在本项目中是一个 **aggregate off-target model**，不是逐命中打分器。
它先为所有唯一 guide 搜索全基因组脱靶位点，再对位点做 NuPoP occupancy /
affinity、73 bp 侧翼 GC 和 nucleotide BDM 注释，最后从零膨胀负二项后验中
采样得到 aggregate activity。适配器把 `aggregate_score_mean` 转成
`crispai_off_target = 1 / (1 + aggregate_score_mean)`；值越大表示越特异。
该转换不提供 per-hit activity，现有 per-hit 模型列仍保持原语义。

本项目只提供适配器，不分发 crispAI 权重或上游代码。`models/crispai.pt` 和
`external_tools/crispAI-main/` 均被 git 忽略，不会出现在 clone 或发布包中；
必须按下面的来源和顺序单独准备。

## 来源与获取

### 上游代码

当前适配器针对以下公开仓库的 `crispAI_score` 目录：

```text
https://github.com/furkanozdenn/crispr-offtarget-uncertainty
```

上游没有在代码中声明可用版本号。推荐从该仓库下载固定 archive 或记录完整
commit，然后将其中 `crispAI_score/` 放到：

```text
external_tools/crispAI-main/crispAI_score/
```

适配器要求以下入口文件齐全：

```text
crispAI.py
annotate_pi.py
model.py
loss_functions.py
_negative_binomial.py
utils.py
encoding.py
nupop.R
```

运行时会把这些小文件复制到临时 run directory，只为 staged copy 注入
`CRISPAI_GENOME`，并把上游 `os.system(...)` 外部命令包装成检查退出码的
helper；原 vendored 源码不会被改写。如果上游代码不再包含预期的
`genomepy.Genome('GRCh38')` 或外部命令调用，适配器会拒绝运行，避免静默使用
未审计版本。

### 权重

默认 checkpoint：

```text
models/crispai.pt
```

注册表中的来源是上游：

```text
https://raw.githubusercontent.com/furkanozdenn/crispr-offtarget-uncertainty/main/crispAI_score/model_checkpoint/epoch%3A19-best_valid_loss%3A0.270.pt
```

该文件约 10 MB，需单独下载并核对大小；缺失时状态是 `not_downloaded`，而不是
`dependency_missing`。请遵守上游仓库及其模型分发条款。

## 依赖清单

只有下列全部项目都通过真实探测，crispAI 才会显示 `ready`：

- checkpoint、全部 vendored 入口文件；
- Python：`torch`、`pandas`、`numpy`、`pybdm`、`genomepy`、`jax`、
  `numpyro`、`tqdm`、`seaborn`；
- `Rscript`，以及 R 包 `NuPoP`；探测要求退出码为 0 且 stdout 去空白后严格
  等于 `TRUE`；
- 可执行的 `cas-offinder`；
- `ucsc_chroms/` 下至少一份未压缩的 `.fa`、`.fasta` 或 `.fna` 分染色体
  FASTA；
- 可由 genomepy 读取，或由 `CRISPAI_GENOME` 直接指向的 FASTA。默认名称是
  `GRCh38`；预检只读取 FASTA header 和首个序列行，不会联网下载全基因组。

UCSC FASTA 供 Cas-OFFinder 搜索，genomepy FASTA 供 73 bp 侧翼注释；两份资源
用途不同，必须分别准备。全基因组搜索和注释需要较大磁盘空间与内存。

## 环境变量

| 变量 | 默认值 | 作用 |
| --- | --- | --- |
| `CRISPAI_VENDOR_DIR` | `external_tools/crispAI-main/crispAI_score` | 上游 `crispAI_score` 目录 |
| `CRISPAI_CHECKPOINT` | `models/crispai.pt` | crispAI checkpoint |
| `CRISPAI_CASOFFINDER_DIR` | `<vendor>/casoffinder` | 包含 `cas-offinder` 和 `ucsc_chroms/` 的目录 |
| `CRISPAI_GENOME` | `GRCh38` | genomepy 已安装名称，或可直接解析的 FASTA 路径 |
| `CRISPAI_GENOME_DIR` | genomepy 本地 genome 目录 | 可选；用于查找 `<genome>/<genome>.fa` 等资源 |

适配器在模块 import 时不执行慢探测。registry、Web `/api/models` 和
`--check-only` 会复用同一套完整 preflight；失败详情包含缺失项和解析后的路径。

## 准备顺序

```bash
# 1. Linux Python 环境
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements-linux.txt

# 2. R + NuPoP（示例使用用户库）
conda install -c r r-base
Rscript -e 'if(!requireNamespace("BiocManager", quietly=TRUE)) install.packages("BiocManager", repos="https://cloud.r-project.org"); BiocManager::install("NuPoP", lib=Sys.getenv("R_LIBS_USER"), ask=FALSE, update=FALSE)'

# 3. Cas-OFFinder；可手工放置或使用项目脚本安装到默认目录
bash tools/build_crispai_env.sh

# 4. UCSC 分染色体 FASTA 与 genomepy GRCh38
#    将 UCSC FASTA 放到 <CRISPAI_CASOFFINDER_DIR>/ucsc_chroms/
#    将 genomepy 资源安装到其本地库，或直接设置 CRISPAI_GENOME=<GRCh38.fa>

# 5. 校验完整运行时
python tools/score_crispai.py outdir/library_scores.tsv --check-only
```

建议在 Linux 服务器运行。Windows 原生环境通常缺少上游脚本依赖的
`cp/rm/Rscript/cas-offinder` 行为；若使用 WSL/容器，请确保上述路径变量在
同一进程中可见。

## 检查状态

```powershell
python tools\score_crispai.py outdir\library_scores.tsv --check-only
```

退出码：

- `0`：完整 preflight 通过，状态为 `ready`；
- `3`：checkpoint 或其他运行时依赖未就绪。

`/api/models` 返回的 crispAI `status`、`is_ready` 与 `status_detail.errors`
来自同一探测结果。只有完整 preflight 通过时，Web 才把 crispAI 标为可立即使用。

## 运行与输出契约

```powershell
python tools\score_crispai.py outdir\library_scores.tsv --samples 200
```

每次调用都会：

1. 对候选 `guide_seq` 去重，生成 23 nt sgRNA（20 nt spacer + `NGG`）；
2. 在输出目录下创建唯一 `crispai-run-*` 工作目录；
3. 把入口文件 stage 到工作目录，把 Cas-OFFinder binary 和 UCSC 目录链接到
   专用的 `casoffinder/` 子目录；NuPoP 临时文件也只写在 staged vendor 目录；
4. 使用全新的 aggregate/log 路径调用上游，检查主进程退出码、输出是否存在、
   解析是否完整；
5. 要求输出 sgRNA 集合与本次去重请求集合完全相等。缺一个、多一个、重复或
   不可解析都会拒绝整次结果，不做部分回填；
6. 仅在成功后把原始输出和日志发布到
   `<输入名>.crispai.aggregate.tsv`、`<输入名>.crispai.log.tsv`，并写
   `<输入名>.crispai.run.json`。

`crispai.run.json` 至少包含 `requested_model`、`effective_model`、
`fallback_reason`、`score_scope`、`success`、`run_dir` 和输出/日志路径；
其中 `score_scope` 固定为 `aggregate`。CLI 无 fallback 分数时
`effective_model` 为 `none`，运行失败返回非零。

候选 TSV 回填仍使用两列：

```text
crispai_aggregate_score
crispai_off_target = 1 / (1 + aggregate_score_mean)
```

## 集成到主流程

basic `analyze_scores.py` 与 `library_pipeline.py` 把 crispAI 作为后处理通道。
命令行使用 `--off-target-model crispai`；旧 `--crispai` 参数仅保留兼容。
crispAI 只适用于 SpCas9 / NGG 风格的 20 nt spacer。

- crispAI 是第一个 off-target 模型时，成功的 aggregate specificity 覆盖
  `off_target_specificity`；作为后续模型时只补独立列。
- preflight、运行或 guide 集合失败时保留原主分。basic/library 的主分是
  `cfd` 时，结构化元数据记录 `effective_model="cfd"` 和非空
  `fallback_reason`；不会把失败伪装成 crispAI 成功。
- basic 运行在输出目录写 `crispai_run.json`；library 在
  `library_summary.json` 的 `crispai` 对象中写同一组元数据。

```powershell
python basic\analyze_scores.py <blast_results.tsv> <outdir> --nuclease cas9 --off-target-model crispai --crispai-samples 200
python shared\design\library_pipeline.py <...> --off-target-model crispai
```

## 参数

```text
--samples     后验采样数，默认 200（上游合法范围 100-2000）
--gpu         CUDA 设备号，默认 -1（CPU）
--out         原始聚合输出的发布路径
--log         子进程日志的发布路径
--no-backfill 只发布原始聚合输出，不改候选 TSV
--check-only  只检查环境，成功 0、未就绪 3
```

## 注意事项

- crispAI 不是逐位点打分模型；不要把它写进 per-hit 模型列表或解释为
  per-hit activity。
- 上游每轮会重跑 Cas-OFFinder 与 NuPoP，耗时取决于 guide 数和全基因组搜索
  规模；采样数越大越慢。
- 不提交 `models/`、`external_tools/` 或第三方许可证内容。公开仓库只保存
  适配器、测试和获取说明。
