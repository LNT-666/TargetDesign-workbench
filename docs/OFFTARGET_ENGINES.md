# Off-target 引擎层

所有脱靶搜索引擎都通过 `shared/search/offtarget_backend.py` 的统一接口调用。
评分、GUI 和 Library 流程只读取统一的命中记录，因此新增或切换引擎不需要改
评分代码。

## 统一命中记录

每个命中包含：

```text
qid, guide, target, start, strand, mismatch, indel, pam, bitscore, engine,
target_start, target_end, query_start, query_end,
rna_bulges, dna_bulges, cigar, aligned_guide, aligned_target
```

- `start` 是 0-based 基因组坐标
- `strand` 为 `+` / `-`
- `mismatch` 是错配数，`indel` 是插入/缺失数
- `target_start` / `target_end` 是该 alignment 实际占用的目标坐标
- `rna_bulges`（CIGAR `I`）表示 guide/query 多出的碱基；
  `dna_bulges`（CIGAR `D`）表示 target 多出的碱基
- `engine` 标记来源引擎

PAM 检查一律使用 alignment 的 `target_start` / `target_end`，不再用
`seed_start + probe_len` 推测目标末端。

## 引擎

| engine | 说明 | 依赖 |
| --- | --- | --- |
| `exact` | 本地 k-mer + Levenshtein 精确/indel 搜索 | Biopython、pyfaidx |
| `blast` | NCBI BLAST+ `blastn` | `blastn`、`makeblastdb` |
| `gggenome` | GGGenome 在线 API | 网络 |
| `indexed` | 本地持久化基因组索引，穷尽列出错配范围内位点 | Python fallback：numpy、Biopython、pyfaidx；native：C++ binary |

## 能力矩阵

每个 backend 通过 `engine_capability_matrix()` 暴露能力；`auto` 和
`validate_search_params()` 会在运行前拒绝不兼容参数。

| engine | substitutions | indels | unknown_gap_type | PAM sides |
| --- | --- | --- | --- | --- |
| `exact` | yes | `dna_rna` | no | 3prime, 5prime |
| `indexed` | yes | `dna_rna` | no | 3prime, 5prime |
| `blast` | yes | basic | no | 3prime, 5prime |
| `gggenome` | yes | basic | yes | 3prime, 5prime |

- `blast` 在 `max_bulge=0` 时使用 `-ungapped`；`max_bulge=1` 时启用
  gapped alignment，并从 BLAST 的 aligned query/target 恢复 CIGAR、RNA/DNA
  bulge 和真实 target span。
- `exact` 在大型基因组上会自动回退到支持 mismatch 和 bulge 的 `blast`。
- 超过 50 Mbp 的 indexed/auto 搜索在未显式给 `--max-bulge` 时默认使用
  `0`。显式请求 `max_bulge=1` 时，未指定 `--index-k` 会自动选择能覆盖
  guide 长度的最大可用 k；显式指定的 k 无法形成保证穷尽的 seed plan 时
  才提示改用 `--max-bulge 0`、更小的 `--index-k` 或 `exact`。
- `gggenome` 的 gap 类型标记为 unknown，评分使用保守 penalty。

## 使用方式

> **已废弃**：Library 一键流程（`shared/design/library_pipeline.py`，以及调用它的 `main.py` Library 标签页、`unified_gui.py`、`webapp/`）已不再开发也不再维护，保留代码只是为了不影响其它功能正常使用。下面的命令仅作历史参考。

Library 一键流程：

```powershell
python shared\design\library_pipeline.py regions.tsv genome.fa outdir --engine exact
python shared\design\library_pipeline.py regions.tsv genome.fa outdir --engine blast
python shared\design\library_pipeline.py regions.tsv genome.fa outdir --engine gggenome --genome-build hg38
python shared\design\library_pipeline.py regions.tsv genome.fa outdir --engine indexed --index-path outdir\genome_index\genome
python shared\design\library_pipeline.py regions.tsv genome.fa outdir --engine exact --pam-mode strict_ngg
python shared\design\library_pipeline.py regions.tsv genome.fa outdir --engine exact --pam-mode guidescan2_nrg
```

`indexed` 引擎会复用 `--index-path` 指定的索引；索引不存在或 FASTA 已变化时
自动重新构建，并把构建/搜索的运行时间和内存峰值写入 `outdir/index_report.json`。
索引格式与扩展 GRCh38 的方法见 `docs/GENOME_INDEX.md`。

不指定 `--engine` 时使用原有 `--search exact|blast|auto` 行为。
`auto` 的优先级由本地基准测量决定，并由 `shared/search/offtarget_backend.py`
的 `auto_engine_candidates` 逐行实现：

- 提供 `--blastdb` 时 auto 只使用 blast，提供 `--index-path` 时 auto 只使用
  indexed。这两个参数是“独占”而不是“优先”：指定的资源不可用或运行失败时
  auto 不会静默换用其他引擎，而是直接报错；错误信息会写明已指定
  `--blastdb` / `--index-path`、auto 只使用该引擎，需要回退请显式指定
  `--engine`。
- 两者都没有，且 FASTA 文件不超过 `MAX_EXACT_GENOME_BYTES` 时：native
  indexed 可用时按 indexed、blast、exact 顺序选择，`max_bulge` 开关不改变该顺序；
  native 不可用时，`max_bulge=0` 按 blast、indexed、exact 顺序选择，
  `max_bulge=1` 按 blast、exact、indexed 顺序选择。
- 两者都没有，且 FASTA 文件超过 `MAX_EXACT_GENOME_BYTES` 时：
  按 blast、indexed 顺序选择，`max_bulge` 开关不改变该顺序，避免自动构建超大索引。
- 未显式指定 `max_bulge` 时 auto 默认使用 `0`，排序和实际执行共享同一份
  默认值；显式 `max_bulge=1` 保留给支持 bulge 的引擎，BLAST 此时使用
  gapped alignment。

`MAX_EXACT_GENOME_BYTES` 等于 `200 * 1024 * 1024`，比较对象是 FASTA 文件的
字节数（`os.path.getsize`），不是 200 Mbp 碱基。文件大小读不到时
（`genome_size=None`）按“不超过”分支处理。

所有入口（三个 motif GUI 的 Library 出库、统一工作台、网页版、CLI）共用
同一份引擎列表，见 `shared/design/library_preflight.py`。出库前会做预检：引擎依赖
缺失、BLAST 数据库不完整、索引不存在等情况会先给出错误或提示。CLI 可用
`--preflight-only` 只检查不运行。

`indexed` 引擎搜索时按 guide 输出进度行（`PROGRESS: guide <qid> <pct>`），
GUI 和网页版可以直接显示当前搜索到第几条 guide。

## Native indexed engine（默认启用）

`indexed` 默认优先通过独立的 C++20 CLI 读取和构建现有 `.ggi` v1 索引。
它仍然是同一个公开 engine，不会新增 `native-indexed` 名称。native 二进制
缺失或不兼容时继续使用 Python fallback；`auto` 在可用时优先 native
`indexed`，大型基因组仍优先 BLAST。native search 的 `--threads` 会并行
处理 guides；各 worker 独立使用 FASTA/cache，最终 hit 按输入顺序确定性合并。
各引擎的当前性能可用 `tools/benchmark_all_engines.py` 与
`tools/benchmark_search.py` 自行测量。

```powershell
cmake -S native\offtarget_engine -B native\build -DCMAKE_BUILD_TYPE=Release
cmake --build native\build -j

$env:PROGRAMFILE_NATIVE_INDEXED = "auto"
$env:PROGRAMFILE_OFFTARGET_NATIVE = "native\bin\offtarget-engine.exe"
$env:PROGRAMFILE_NATIVE_INDEXED_FALLBACK = "1"
$env:PROGRAMFILE_MAX_MEMORY_MB = "32768"
```

- `PROGRAMFILE_NATIVE_INDEXED`：`auto`（默认）、`0` 或 `1`。
- `PROGRAMFILE_OFFTARGET_NATIVE`：显式 binary 路径；为空时查找
  `native/bin/offtarget-engine[.exe]` 和 `PATH`。
- `PROGRAMFILE_NATIVE_INDEXED_FALLBACK`：native 在输出 hit 前失败时，
  默认 `1` 允许回退 Python；设为 `0` 则直接报错。binary 缺失或不兼容时
  始终使用 Python。
- `--max-memory-mb N`：`search` / `build-index` 的显式进程 RSS 上限；
  省略或 `0` 表示无显式上限。`PROGRAMFILE_MAX_MEMORY_MB` 提供环境变量
  默认值，CLI 显式参数优先。

- `--timeout-s N` / `PROGRAMFILE_OFFTARGET_TIMEOUT_S`：单次 native
  `search` / `build-index` 的墙钟上限，默认不限时；超时抛出
  `NativeEngineTimeout`，不会退化到 Python 实现。
- 索引前缀按 `k` 命名（`<output_dir>/genome_index/<genome>.k<k>.ggi`），
  构建时持有 `<prefix>.lock` 排他锁：并发运行时后来者会等待并复用已
  校验的索引，不再覆盖其他进程正在读取的 `.ggi`；`--index-path` 仍是
  显式覆盖。
- `--engine auto` 现在是运行期引擎链：按 `auto_engine_candidates` 的偏好顺序逐个尝试，
  某个候选不可用或运行失败时先记录失败原因，再按策略
  `CRISPR_OFFTARGET_ENGINE_FALLBACK`（`ask`/`allow`/`deny`，默认 `ask`；CLI 对应
  `--engine-fallback`，GUI 里会弹窗确认）决定是否切换到下一个候选。大基因组带 bulge
  时的顺序是 blast → indexed，因此原生索引不可用就会落到 blast。
- 链中的 indexed 候选强制 `python_fallback=deny`：auto 只会切换到真正的引擎，不会退化
  成纯 Python 索引；内存超限（`MEMORY_LIMIT_EXCEEDED`）直接终止链，不会切换到绕过该上限
  的引擎。命中由实际使用的引擎产生，`last_report` 记录 `engine_used`、`fallback_from`、
  `fallback_reason`、`fallback_attempts`。显式指定 `--engine indexed` 等仍保持原行为。
native search 在启动前按 `fixed + workers × cache_per_worker + workspace`
估算峰值；`cache-genome=auto` 超出预算时先关闭 worker 序列缓存，
`cache-genome=true` 的超预算配置直接报错。运行中每个 guide 开始前以及
候选循环每 256 个候选检查一次 RSS，越界后设置 atomic cancel，所有 worker
join 后统一抛出 `MEMORY_LIMIT_EXCEEDED`，因此不会写出部分 JSONL。
`MEMORY_LIMIT_EXCEEDED` 不会触发 Python fallback；fallback 的 Python
indexed 路径同样应用限制。

`IndexedBackend.last_report["implementation"]` 为 `native-cpp` 或 `python`。
native 读取 Python 生成的索引；Python `load_index` 也可以读取 native 构建
的索引。报告的 `memory_limit_mb` 是实际生效限制，`observed_peak_mb`
是进程峰值；搜索 summary 另含启动估算 `estimated_peak_mb`。构建说明和当前限制见
`native/offtarget_engine/README.md`。

## 约束处理

- exact/indexed 共用非重叠 seed planner：seed 数 `N > B`，每个 seed
  容差 `t = floor(M / (N - B))`。若当前 k/guide 长度无法形成保证穷尽的
  规划，小基因组回退全位置扫描，大基因组显式报错，不会静默降低灵敏度。
- BLAST 的 `max_bulge=0` 路径使用 `-ungapped`；`max_bulge=1` 路径使用
  gapped `blastn`，解析 aligned query/target 后过滤实际 bulge 数。
- GGGenome 的错配预算必须写在 URL 路径里（`/<build>/<mismatch>/<query>.txt`），
  `?mismatch=` 查询参数会被服务端静默忽略、只返回精确匹配。预算为 0 时报告
  `exact_only=True`；预算超过查询长度 25% 时 API 返回 `### ERROR`，本工具会
  直接报错，而不是把它当成“没有脱靶”。`--require-pam` 会把 PAM 拼进查询
  序列，此时请求退化为一次普通子串搜索。
- indexed 使用共享 seed planner，并输出实际 seed 配置和
  `exhaustive_seed_plan` 标志。

## BLAST 数据库复用

建库成功后写出 `<db>.source.json`，记录原始 FASTA 路径、大小、
`mtime_ns`、全文件 SHA256、`makeblastdb` 版本和构建时间。复用前会校验
manifest；manifest 缺失或 FASTA 中间内容改变时会自动重建。只有显式传
`--trust-existing-blastdb` 才会跳过校验，并打印警告。

## 其他入口的 rich hit 传递

basic、complex 和 Y-ZBP 流程保留 backend 返回的完整 hit 字典；写入
`blast_results.tsv` 时使用 JSON 保存 alignment、CIGAR、RNA/DNA bulge 和
真实坐标。评分端兼容旧 tuple 记录，但旧 tuple 按 mismatch-only 语义处理，
不会在评分阶段补造 bulge。

批量性能基准：

```powershell
python tools\benchmark_search.py guides.tsv genome.fa --engine indexed `
  --index-k 12 --max-mismatch 4 --max-bulge 0 --limit 100
```

输出包含耗时、guides/s、内存峰值、seed plan 状态和预计 variant lookups。

## 引擎差异对比

```python
from offtarget_backend import SearchParams, compare_engines

params = SearchParams(
    max_mismatch=2, max_bulge=1, require_pam=True, pam="NGG")
result = compare_engines(
    [{"qid": "g0", "guide_seq": "GCCTCTTTCCCACCCACCTT"}],
    "genome.fa", params, engine_names=["exact", "indexed"])
print(result["summary"])
```

`summary` 按 guide 输出各引擎命中数，以及相对参考引擎（默认 exact）的召回率。
