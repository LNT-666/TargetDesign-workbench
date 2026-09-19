# 本地基因组索引（Phase 3）

目标是把人类级脱靶搜索从 BLAST 依赖中解耦，提供可复用、可报告、可审计的
本地基因组索引。当前实现先完成索引格式、穷尽搜索、增量复用和运行/内存报告，
小基因组正确性已用穷举测试锁定；GRCh38 可作为后台任务逐步构建。

## 引擎与文件

统一后端新增 `indexed` 引擎（`shared/search/offtarget_backend.py`），核心模块为
`shared/search/genome_index.py`。一个索引包含两个文件：

```text
<prefix>.ggi   # 二进制：contig 表 + k-mer offsets + 扁平位置数组
<prefix>.json  # 元数据：版本、k、genome 指纹、contig、构建时间/内存报告
```

索引只存正链 k-mer 位置；搜索时同时查询 guide 和 guide 的反向互补，因此
覆盖正反两条链。`<prefix>.json` 记录 `genome_fingerprint`（文件大小、
mtime 和首尾 64 KiB 的 SHA-256），FASTA 变化后索引会被自动判定为过期并重建。

## 构建与复用

当前 `IndexedBackend` 在 native 二进制可用时优先走 C++20 构建器；下面保留
Python 构建命令作为 fallback、旧格式兼容和差分验证入口。

命令行构建：

```powershell
python tools\build_genome_index.py genome.fa --output-dir outdir\genome_index --k 12
python tools\build_genome_index.py genome.fa --output-dir outdir\genome_index `
  --k 12 --max-memory-mb 32768
```

独立搜索入口：

```powershell
python tools\search_indexed.py guides.tsv genome.fa outdir `
  --index-path outdir\genome_index\genome --max-mismatch 4 --require-pam `
  --max-memory-mb 32768
```

构建完成后，Library 流程直接复用：

```powershell
python shared\design\library_pipeline.py regions.tsv genome.fa outdir `
  --engine indexed --index-path outdir\genome_index\genome
```

也可以只指定 `--engine indexed` 不传 `--index-path`：引擎会在输出目录的
`genome_index/` 子目录下按 FASTA 文件名生成并缓存索引。主 GUI 的
Library 页面新增了 "Genome index prefix" 输入框和 "Build index" 按钮，
一键构建后自动填入索引前缀。

每次搜索都会生成 `index_report.json`，包含：

```text
k, total_bases, valid_kmer_positions, build_time_s, memory_peak_mb,
memory_limit_mb, estimated_peak_mb, observed_peak_mb, index_bytes, reused,
search_time_s, search_memory_peak_mb, guides, hits
```

`--max-memory-mb` 省略或为 `0` 时保持无显式上限；正数限制同时约束 native
和 Python indexed 构建/搜索。Python native adapter 报
`MEMORY_LIMIT_EXCEEDED` 时不会自动回退到未受限制的 Python 实现。
主 GUI 默认使用 Auto（50% total，并受 75% available 约束），Custom 与
Unlimited 状态保存在 workspace；Auto 的解析值不写入 workspace。

未显式指定 `--index-k` 时，后端先按 FASTA 大小选择紧凑的 k（小基因组 8，
中型 10/11，人类级 12），再根据 guide 长度和 `max_bulge` 自动下调到能形成
保证穷尽 seed plan 的最大 k。显式指定 `--index-k` 时不会自动修改。

## 穷尽性保证

对每条 guide 使用与 `exact` 相同的非重叠 seed planner。对错配预算 `M`
和 bulge 预算 `B`，planner 要求 seed 数 `N > B`，每个 seed 的容差为
`t = floor(M / (N - B))`。若当前 k 与 guide 长度无法形成保证穷尽的
规划，小基因组会回退到全位置扫描；大基因组会显式报错，不会静默降低
灵敏度。

候选随后使用共享 gapped alignment 过滤 mismatch/indel。结果包含真实
`target_start` / `target_end`、`rna_bulges`、`dna_bulges` 和 CIGAR，
PAM 也基于真实 target span 检查。

对于超过 50 Mbp 的基因组，`indexed` 在未显式给出 `--max-bulge` 时默认
使用 mismatch-only (`0`)，避免 20 nt guide + `k=12` 无法形成保证 seed
plan 的默认失败。显式 `--max-bulge 1` 且未指定 k 时，会自动使用更小的
k（例如 20 nt guide 使用 `k=10`），并在现有索引 k 不匹配时重建索引。

## GRCh38 扩展路径

以 GRCh38 主 FASTA（约 3.3 GB）为例。
人类基因组总长约 3.1 Gbp，低于 uint32 上限，索引位置数组可用 `u4`：

```text
GRCh38 估算：positions 约 12.4 GB + offsets 约 0.13 GB（k=12）；
当前排序构建的峰值内存约 50–64 GB，建议在 64 GB+ 内存机器上构建，
或先用单条染色体验证。
```

一次性构建全基因组索引的峰值内存约 50-64 GB，内存不足时建议先用单条染色体验证：

```powershell
python tools\build_genome_index.py GCF_000001405.40_GRCh38.p14_genomic.fna `
  --output-dir outdir\genome_index --contigs NC_000021.9
```

`--contigs` 会指定只索引这些染色体，并且找到全部目标染色体后立即停止读取，
避免每次构建都扫描整个 3.3 GB 文件。

GRCh38 的 `.fai` 首次生成需要数分钟；生成一次后索引和搜索都会复用。
后续若需要更低内存/更快构建，可在同一 `indexed` 后端下替换为
BWT/FM-index（ropebwt2、SeqAn3 或自研 Rust/C++ 扩展），调用方无需改动。

## 参考实测（2026-08-15）

从 GRCh38 主 FASTA 抽出 21/22 号染色体（约 97.5 Mbp，`chr21_22.fa`）：

```text
构建：71.2 s，峰值内存 1478 MB，索引文件 451 MB，79.2M 个 k-mer 位置
搜索：单 guide、max_mismatch=4、要求 PAM，约 78 s（引擎计时），
      峰值内存约 474 MB，穷尽列出 423 个位点；关闭 PAM 过滤时列出
      2386 个候选位点（该 guide 位于高度重复区）
```

这些文件会留在上面 `--output-dir` 指定的目录下（`chr21_22.ggi` 和
`chr21_22.json`），后续搜索自动复用。

## Native C++ backend

同一 `.ggi` v1 格式现在也有独立的 C++20 reader/builder：

```bash
cmake -S native/offtarget_engine -B native/build \
  -DCMAKE_BUILD_TYPE=Release -DOFFTARGET_BUILD_TESTS=ON
cmake --build native/build -j

native/bin/offtarget-engine search \
  --genome genome.fa \
  --index genome_index/genome \
  --guides guides.tsv \
  --output hits.jsonl \
  --max-mismatch 4 --max-bulge 0 --seed-len 12 \
  --require-pam --pam NGG --pam-side 3prime \
  --max-memory-mb 32768
```

Python 侧保持 `indexed` engine 不变，默认优先使用 native；找不到或
不兼容原生二进制时自动使用 Python。常用覆盖设置：

```text
PROGRAMFILE_NATIVE_INDEXED=auto
PROGRAMFILE_OFFTARGET_NATIVE=native/bin/offtarget-engine
PROGRAMFILE_NATIVE_INDEXED_FALLBACK=1
```

回退到纯 Python 使用 `PROGRAMFILE_NATIVE_INDEXED=0`。

当前 native 搜索使用 worker pool 按 guide 并行。内存映射的 `GenomeIndex`
在多线程间只读共享，每个 worker 独立打开 positional FASTA reader，并在
`--cache-genome true` 时维护自己的序列缓存；最终结果按 guide 输入顺序合并，
因此不同 `--threads` 值的 hit 序列一致。`auto` 会把有效 worker 数计入
最坏情况内存估算，而不是只检查一份 genome；每个 worker 按完整 FASTA 大小
加固定开销估算，预留 2 GiB 后仅在不超过当前可用内存一半时启用缓存。
最终 hit 仍按 qid 在内存中汇总。
Python indexed 继续保留为 native 二进制缺失、不兼容或显式禁用时的 fallback，
不会删除。`auto` 在 200 Mbp 以内优先 native indexed，大型基因组仍优先
BLAST。native 与 Python 的差分测试和索引双向兼容测试见
`tests/test_native_indexed.py`。
