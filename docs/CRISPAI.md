# crispAI 外部接入

crispAI-aggregate 不是库内可直接加载的轻量评分器。上游模型需要先对每条
guide 在全基因组找脱靶位点，再对每个位点做物理特征注释
（NuPoP occupancy/affinity、73 bp 侧翼 GC、nucleotide BDM），最后从
零膨胀负二项后验中采样聚合。因此本项目按外部工具接入：保留官方
`crispAI_score` 代码，新增 `tools/score_crispai.py` 负责生成输入、调用上游、
把 aggregate score 回填到候选 TSV。

## 前置环境

建议在 Linux 服务器上运行；Windows 上上游脚本用到的
`cp/rm/Rscript/cas-offinder` 路径通常不可用。

```bash
# 一键 build（推荐）：创建 .venv、装 Python 依赖、装 R + NuPoP，最后跑 preflight
bash tools/build_crispai_env.sh

# Python 依赖（在上游脚本运行环境中执行）
pip install -r requirements-linux.txt
# Windows 本地调试则使用: pip install -r requirements-windows.txt
# （crispAI 上游还会 import seaborn，已包含在上面两个 requirements 里。）

# R + NuPoP
conda install -c r r-base   # 或系统安装 R
# NuPoP 在 R >= 4.3 的 CRAN 上已不可用，用 Bioconductor 装到用户库：
Rscript -e 'if(!requireNamespace("BiocManager", quietly=TRUE)) install.packages("BiocManager", repos="https://cloud.r-project.org"); BiocManager::install("NuPoP", lib=Sys.getenv("R_LIBS_USER"), ask=FALSE, update=FALSE)'

# Cas-OFFinder（上游环境要求）
# `bash tools/build_crispai_env.sh` 会用 micromamba + bioconda 装好并软链到
# external_tools/crispAI-main/crispAI_score/casoffinder/cas-offinder；
# 也可手动放置二进制，或设置环境变量 CRISPAI_CASOFFINDER_DIR 指向其所在目录
```

还需要 hg38/GRCh38 序列。上游 `annotate_pi.py` 使用 genomepy 获取
`GRCh38`（首次运行会下载/安装到 genomepy 本地库），用于每个脱靶位点的
侧翼序列注释；同时 Cas-OFFinder 需要一份独立的 UCSC 分染色体 FASTA，
放在 `casoffinder/ucsc_chroms/` 下，供脱靶搜索使用。两份数据都需要准备。

`models/crispai.pt` 和 vendored 代码已经在仓库内：

```text
models/crispai.pt
external_tools/crispAI-main/crispAI_score/
external_tools/crispAI-main/LICENSE
```

## 检查环境

```powershell
python tools\score_crispai.py outdir\library_scores.tsv --check-only
```

所有缺失项都会列出来；退出码 `3` 表示环境未就绪。

## 运行并回填

先生成一份带 `guide_seq` 的候选 TSV（例如 `library_scores.tsv`），然后运行：

```powershell
python tools\score_crispai.py outdir\library_scores.tsv --samples 200
```

该命令会：

1. 读取候选 TSV，去重并生成 23 nt sgRNA（20 nt spacer + `NGG`）。
2. 调用 vendored 上游 `crispAI.py --mode agg-score`。
3. 在原 TSV 上追加 `crispai_aggregate_score` 与 `crispai_off_target` 两列。

`crispai_off_target` 的换算：

```text
crispai_off_target = 1 / (1 + aggregate_score_mean)
```

与 CFD/CRISPR-M/DeepCRISPR 保持一致的方向：值越大表示越特异；`crispai_aggregate_score`
保留原始上游聚合值用于核对。原始聚合输出默认写到
`<输入名>.crispai.aggregate.tsv`，运行日志写到 `<输入名>.crispai.log.tsv`。

## 集成到主流程（off-target-model=crispai）

crispAI 作为后处理通道集成到 basic `analyze_scores.py`、`library_pipeline.py`，
以及复杂 `analyze_complex_scores.py` 与 Y-ZBP `blast_combined.py`。GUI 现在把
`crispai` 作为普通 Off-target 模型放在多选下拉框中，不再使用单独勾选框；
命令行使用 `--off-target-model crispai`，旧的 `--crispai` 参数仅保留兼容。
对双靶设计按侧生效，`left_nuclease/right_nuclease` 为 `cas9` 或 `custom`
的侧都可以运行。
把 crispAI 提升为该侧主分。选择后：

1. 评分阶段完成后，对所有唯一 20 nt spacer 批量调用一次 crispAI 聚合管线
   （内部基于 `scoring.crispai_runtime.run_crispai_aggregate`）。
2. 当 `crispai` 是第一个 Off-target 模型时，用
   `crispai_off_target = 1 / (1 + aggregate)` 覆盖每条候选的
   `off_target_specificity`，因此单 motif 排序和双靶 PairRank
   输入会随 crispAI 改变；作为后续模型时只补充独立列。
3. 结果 TSV 额外带 `off_target_specificity_crispai` 与 `crispai_aggregate_score`；`crispai_off_target` 只在单独运行 `tools/score_crispai.py` 回填时写入，模型名称列不再输出。字段总览见 `docs/OUTPUTS.md`。

若 crispAI 环境未就绪（`--check-only` 有报错），或输入不是可用的 20 nt
Cas9-compatible spacer，则保留主流程 fallback/reference-only 结果，不会中断。
`custom` 下的调用结果按参考模型处理。

```powershell
python basic\analyze_scores.py <blast_results.tsv> <outdir> --nuclease cas9 --off-target-model crispai --crispai-samples 200
python basic\analyze_scores.py <blast_results.tsv> <outdir> --nuclease custom --off-target-model crispai --crispai-samples 200
python shared\design\library_pipeline.py <...> --off-target-model crispai
```

仍可单独用 `tools/score_crispai.py` 做纯回填，两者共用同一套
`crispai_runtime` 底层。

## 参数

```text
--samples     后验采样数，默认 200（上游合法范围 100-2000）
--gpu         CUDA 设备号，默认 -1（CPU）
--out         原始 crispAI 聚合输出路径
--log         crispAI 子进程日志路径
--no-backfill 只生成原始聚合输出，不改候选 TSV
--check-only  只检查环境
```

## 注意事项

- crispAI-aggregate 只针对 SpCas9 / NGG。非 NGG 或非 20 nt spacer 的
  `guide_seq` 会被跳过。
- 上游每轮会重新跑 Cas-OFFinder 与 NuPoP 注释，速度取决于 guide 数量与
  全基因组搜索规模；采样数越大越慢。
- 结果列仍保持 0-1 specificity 语义。当 `crispai` 是第一个模型时，
  crispAI 会直接覆盖主 `off_target_specificity`；单独跑
  `tools/score_crispai.py` 只是追加列，不改主分。
