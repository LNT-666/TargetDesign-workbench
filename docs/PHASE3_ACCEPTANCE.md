# Phase 3 验收：GRCh38 全基因组脱靶搜索

> 本文记录 Phase 3 当时的 Python indexed 基线。当前默认优先 native
> indexed，Python 实现保留为 fallback；最新引擎对比见
> `example/engine_benchmark_small/REPORT.md`。

## 输入

- 基因组：GRCh38.p14（`example/GCF_000001405.40_GRCh38.p14_genomic.fna`，3.34 GB，705 个 contig）
- 索引：`example/genome_index/GCF_000001405.40_GRCh38.p14_genomic.ggi`（12.68 GB，k=12）
- Guide：2 个真实序列
  - `complex1`：`GAACACAAAGCATAGACTGC`
  - `demo`：`GCCTTGGCCTCCTAAAGTGC`
- 参数：`--max-mismatch 4 --require-pam`（NGG，seed len 12，seed mismatch 1，允许 1 个 bulge）

## 搜索命令

```bash
cd /home/apool/songji/programfile
.venv/bin/python tools/search_indexed.py example/grch38_search_guides.tsv \
  example/GCF_000001405.40_GRCh38.p14_genomic.fna example/grch38_search \
  --index-path example/genome_index/GCF_000001405.40_GRCh38.p14_genomic \
  --max-mismatch 4 --require-pam
```

## 结果

| 项目 | 数值 |
| --- | --- |
| 索引复用 | `reused=true`，未重新构建 |
| 搜索耗时 | 1386.49 s（约 23.1 分钟） |
| 搜索内存峰值 | 12198.86 MB（约 11.9 GB） |
| 总命中数 | 12445 |
| complex1 命中 | 82 |
| demo 命中 | 12363 |

命中按错配数分布：

| mismatch | 0 | 1 | 2 | 3 | 4 | 5（含 indel） |
| --- | --- | --- | --- | --- | --- | --- |
| 命中数 | 226 | 4861 | 3750 | 1810 | 1410 | 388 |

输出文件：

```text
example/grch38_search/top_offtargets.tsv
example/grch38_search/index_report.json
```

## 穷尽性说明

搜索同时覆盖 guide 和 reverse complement，并使用与 `exact` 相同的非重叠
seed planner：`N > max_bulge`，每 seed 容差
`floor(max_mismatch / (N - max_bulge))`。候选位点再经过共享 gapped
alignment 和基于真实 target span 的 PAM 过滤。小基因组上的穷举对比测试
（`tests/test_genome_index.py`、`tests/test_search_hardening.py`）已锁住
mismatch 与 bulge 预算内的命中集合。

## 验收结论

Phase 3 全部验收项通过：

- 全基因组脱靶搜索不再依赖 BLAST。
- 指定错配范围内的位点被穷尽列出并写出 `top_offtargets.tsv`。
- `index_report.json` 提供耗时与内存报告。
- 已有索引可直接复用，无需重新构建。
