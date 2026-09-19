# 交付报告：fasta-gz-prep

- round: 4
- status: ready_for_review
- updated: 2026-09-16 12:32

## 改动清单

| 文件 | 行 | 改了什么 | 对应任务项 |
| --- | --- | --- | --- |
| `shared/data/annotation_utils.py` | 2-5 | 补模块 docstring（本模块同时承载注释与 FASTA 的 gz / 文本帮手） | P0-1 |
| `shared/data/annotation_utils.py` | 9 | 新增 `import shutil` | P0-1 |
| `shared/data/annotation_utils.py` | 46-146 | 新增 `FASTA_EXTENSIONS`、`_plain_fasta_name`、`_first_nonblank_byte`、`_decompress_to_plain_fasta`、`_reusable_plain_fasta`、`ensure_plain_fasta` | P0-1 |
| `main.py` | 14 | import 增加 `ensure_plain_fasta` | P0-2 |
| `main.py` | 53 | 新增 `self._genome_cache = {}` | P0-2 |
| `main.py` | 151-173 | 新增 `_get_prepared_genome()`（缓存键 = 用户原始输入，命中且目标存在时直接返回） | P0-2 |
| `main.py` | 192 | `_extract_sequences` 改用 prepared 路径；None 仍抛 `FileNotFoundError` | P0-3 |
| `main.py` | 302, 310 | `prepare_data` 的存在性检查改用 `raw_genome`（解压失败不再误跑下载分支） | P0-4 |
| `main.py` | 324-327 | `prepare_data` 取 prepared；None 时 `showerror` + `return` | P0-4 |
| `main.py` | 357, 367, 376 | `build_blastdb(genome, ...)`、`params["genome"]`、`entry_library_genome` 全部拿到同一个 prepared `genome` 变量 | P0-4 |
| `main.py` | 443, 449, 455-458, 470 | `extract_target_sequences`：raw 检查与 prepared 取值分离，`params["genome"]` = prepared | P0-5 |
| `main.py` | 490, 496, 502-505, 523 | `extract_mask_sequences`：同上 | P0-5 |
| `tests/test_fasta_gz.py` | 全文件（新增） | `EnsurePlainFastaTests`（用例 1-6）+ `MainAppGenomeGzTests`（用例 7） | P0-7 |

P0-6：`main.py:512` 的 workspace 映射（`"entry_genome": "genome"`）未动，`entry_genome` 仍读写用户原始输入。

## 轻量自检结果

```bash
python -m py_compile main.py shared\data\annotation_utils.py tests\test_fasta_gz.py
```

```text
（无输出即通过；本机执行后额外打印 py_compile OK）
```

```bash
python -m unittest tests.test_fasta_gz -v
```

```text
test_corrupt_gz_fails_without_leaving_partial_target ... ok
test_gz_input_is_decompressed_next_to_source ... ok
test_missing_fasta_extension_is_extended_with_fna ... ok
test_plain_input_returned_untouched ... ok
test_plain_text_behind_gz_extension_is_returned_as_is ... ok
test_second_call_reuses_existing_plain_fasta ... ok
test_gz_and_plain_genome_extract_identically ... ok

----------------------------------------------------------------------
Ran 7 tests in 40.243s

OK
```

```bash
python -m unittest tests.test_gff_gz -v
```

```text
test_load_gene_list_from_gz_matches_plain ... ok
test_prepared_gtf_from_gz_is_plain_text ... ok
test_read_gff_gz_matches_plain ... ok
test_utr_script_stdout_matches_plain ... ok

----------------------------------------------------------------------
Ran 4 tests in 45.951s

OK
```

环境：本机 `python` 3.14.7 + `$env:PYTHONUTF8="1"` + pyfaidx 0.9.0.4，命令都在 `R:\songji\programfile` 下执行；未跑 `run_tests.py` 全量、未连服务器。

## 关键证据

### P0-1 `ensure_plain_fasta` 最小调用（临时目录）

```text
plain     -> <tmp>\mini.fna    （原样返回，目录内无新增文件）
gz        -> <tmp>\mini.fna    （与 assets/mini.fna 逐字节相同，首字节不是 1f 8b）
fakegz    -> None              + 日志 "Failed to prepare FASTA (<tmp>\fake.fna.gz): Unknown compression method"
                                 且 <tmp>\fake.fna 与 <tmp>\fake.fna.part 都不存在
genome.gz -> <tmp>\genome.fna  （C3 的扩展名补齐）
第二次调用 -> 同一路径，mtime 不变，日志 "Using existing plain FASTA: <tmp>\mini.fna"
```

### P0-2 `_get_prepared_genome()`（`entry_genome` = `<tmp>\mini.fna.gz`）

```text
returned              : <tmp>\mini.fna
logs（首次）          : ['Decompressed genome FASTA: <tmp>\\mini.fna']
logs（再调）          : ['Using existing plain FASTA: <tmp>\\mini.fna']
raw entry value still : <tmp>\mini.fna.gz      ← C12
```

### P0-4 / P0-5 `params["genome"]`

`main.py:367` / `:470` / `:523` 的 `"genome": genome` 都来自 `main.py:324` / `:455` / `:502` 的 `genome = self._get_prepared_genome()`；`main.py:357` 的 `self.build_blastdb(genome, output_dir)` 用的是同一个变量。`prepare_data` 需要 Tk 组件，单测无法整段跑通，故此处以代码证据 + 用例 7（gz 与 plain 的 `_extract_sequences` / `_extract_target_fasta` 输出完全相同）为准。

## 未做项

- 引擎侧 gz（`shared/search/*`、`designer_workbench.py`、`unified_gui.py`、`webapp/`、`Target_xbp_*`）— 任务 D3 明确不修；用户链路（数据准备 → 子工具）已通过 params 传纯文本 FASTA。
- 全量 `run_tests.py`、ms01 服务器复跑 — 任务 §6 已划给 master。
- BGZF/bgzip 支持、下载流程 — 任务 §0 明确不在范围。

## 附带发现（不在本次范围，未修）

- `main.py:354` / `main.py:378` — `_extract_target_fasta` / `_extract_mask_fasta` 的 `output_dir` 形参其实没被使用（写文件走 `main.py:175` `_write_fasta` 里的 `self.entry_output`）；既有不一致，与本次改动无关。
- `shared/data/local_extract.py:29` — `Fasta(...)` 句柄从不关闭：① Windows 上会让 `tempfile.TemporaryDirectory` 清理报 WinError 32（测试已按任务提示用 `ignore_cleanup_errors=True` 绕过，未改该文件）；② 用户换 `.gz` 后重新解压时，若旧 `.fna` 仍被占用，`os.replace` 可能失败（此时记日志并返回 None，不留半成品）。
- `main.py:376` — 现在会把 prepared 路径写进 `entry_library_genome`（P0-4 明确要求），副作用是 `main.py:958`「Build genome index」读该框时也会拿到纯文本 FASTA（对用户是好事）；但用户若直接往 Library genome 框手填 `.fna.gz`，仍会失败（超范围）。
- C4 用 mtime 判新鲜度：若用户拿 mtime 更旧的同名 `.gz` 覆盖（例如从旧备份还原），已存在的 `.fna` 会被复用。属任务 D4 的既定语义，仅记录。

## 待明确

- C3 只处理「末尾是 `.gz`」的文件名：若内容为 gz 但文件名不以 `.gz` 结尾，产物是「原名 + 补 `.fna`」（如 `genome.bin` -> `genome.fna`）。按 C3 字面实现，未额外推断。
- P0-4 要求 `entry_library_genome` 填 prepared 路径，这意味着 workspace 保存的 `library_genome` 也会变成解压后的 `.fna`（C12 只保证 `entry_genome` 不变）。若期望 library 输入框保留用户原始 `.gz`，请 master 决策。

## round 3（servant 跟进：review.md 的 U2/U4，2026-09-16）

- 触发：用户指示「都进行吧」，执行 `review.md`「下一步」里剩下的可选项 U2（引擎/工作台入口）与 U4（`_get_prepared_gtf` 新鲜度）。本轮没有新 `task.md`；U3 按 master 的分类仍是「记录即可」，未改代码。
- 改动文件与行号：

| 文件 | 行 | 改了什么 | 任务项 |
| --- | --- | --- | --- |
| `shared/search/blast_utils.py` | 27 | 新增 `from data.annotation_utils import ensure_plain_fasta, is_gzip_file` | U2 |
| `shared/search/blast_utils.py` | 696-704 | `load_genome_and_prepare_fasta`：gz 输入先 `ensure_plain_fasta`（失败 `_log` + `sys.exit(6)`），再走原 `_looks_like_fasta` / `Fasta()` 路径 | U2 |
| `designer_workbench.py` | 39 | 新增 `from data.annotation_utils import ensure_plain_fasta` | U2 |
| `designer_workbench.py` | 1989-2002 | 新增 `_prepare_genome_fasta()`：Genome FASTA 行允许 `.fna.gz`，失败抛 `ValueError` | U2 |
| `designer_workbench.py` | 2076 | `_current_config()` 改用 `genome_fasta=self._prepare_genome_fasta()` | U2 |
| `main.py` | 89-94 | `_get_prepared_gtf` 缓存命中改为 `plain_fasta_is_current(cached, raw_gtf)`，陈旧时记 `Prepared annotation is stale or missing, re-generating:` 并丢弃缓存项 | U4 |
| `main.py` | 137-140 | `*_with_utrs.gff3` 复用改为同一套新鲜度判断，陈旧时记 `UTR file is stale, re-generating:` | U4 |
| `tests/test_fasta_gz.py` | 23, 215-262 | 新增 `EngineGenomeGzTests`（引擎入口 + workbench 行）与免 Tk 的 `FakeWorkbench` | U2 |
| `tests/test_gff_gz.py` | 6, 11, 94-157 | 新增用例：产物陈旧 → 重建；非 ASCII 属性按 UTF-8 写出 | U4 |

- 行为验证（本机，`$env:PYTHONUTF8="1"`）：
  - 引擎入口：`load_genome_and_prepare_fasta(<tmp>/mini.fna.gz)` → `(<pyfaidx Fasta>, <tmp>/mini.fna, None)`，`index["NC_000001.11"][0:10] == "ACGTTGCAAC"`，解压产物与 `assets/mini.fna` 逐字节相同；日志 `Decompressed genome FASTA: ...`。
  - 工作台：`_prepare_genome_fasta()` 对 `.fna.gz` 返回 `<tmp>/mini.fna`（日志同上 / 复用日志），明文输入原样返回，空输入返回 `""`。
  - U4：把产物 mtime 做旧到早于源 60 s 后，暖缓存下重新生成（日志 `Prepared annotation is stale or missing, re-generating:` + `UTR file is stale, re-generating:`），随后恢复复用；产物未做旧时二次调用不重写（mtime 不变）。
- 命令与输出：

```bash
python -m py_compile main.py shared\data\annotation_utils.py shared\search\blast_utils.py designer_workbench.py tests\test_fasta_gz.py tests\test_gff_gz.py
```

```text
（无输出即通过）
```

```bash
python -m unittest tests.test_fasta_gz -v
```

```text
Ran 11 tests in 24.917s

OK
```

```bash
python -m unittest tests.test_gff_gz -v
```

```text
Ran 6 tests in 56.259s

OK
```

```bash
python -m unittest tests.test_gui_common tests.test_designer_workbench -v
```

```text
Ran 31 tests in 63.439s

OK
```

```bash
python -m unittest tests.test_pattern_runner tests.test_library_fasta
```

```text
Ran 36 tests in 278.370s

OK
```

```bash
python -m unittest tests.test_offtarget_backend
```

```text
Ran 43 tests in 26.406s

FAILED (errors=1)

ERROR: test_auto_and_large_indexed_apply_mismatch_only_defaults
search.offtarget_backend.SearchParameterError: auto could not find an engine compatible with max_bulge=0; choose exact or indexed explicitly
```

- 该失败的归属（既有环境限制，非本次引入）：用例断言 `resolve_engine("auto", params) == "blast"`，而 `resolve_engine` 会逐个检查候选引擎的 `available()`；本机没有 NCBI BLAST+（`Get-Command blastn,makeblastdb` 无结果），探针输出为 `candidates: ['blast']` → `(False, '缺少 NCBI BLAST+：blastn, makeblastdb')`。本次改动未触及 `shared/search/offtarget_backend.py`，服务器（有 BLAST+）应通过——留给 master 在 ms01 全量复核时确认。

- 未做 / 仍开放：
  - `shared/search/exact_offtarget.py:378`、`shared/search/genome_index.py:751`、`Target_xbp_Y_zbp_Target/extract_motifs.py:166` 仍是裸 `Fasta(path)`：Designer 链路（config → CLI → `load_genome_and_prepare_fasta`）已覆盖，CLI 直接喂 `.gz` 仍会失败（U3 记录项）。
  - `shared/search/blast_utils.py:643 load_genome_records()` 没有调用方，未改。
  - workbench 的 Search FASTA / Mask FASTA 行未做 gz（U2 只点名 Genome FASTA 行）；BED 模式走 `_build_window_fasta`，读的是已 prepared 的 `config.genome_fasta`。
  - `main.py:958` 的「Build genome index」仍要求手填 `.fna.gz` 时失败（U3 记录项）。
  - U1（ms01 全量 `run_tests.py` + 真实 gff.gz 端到端）需要用户提供 `MS_PASS`，本会话未执行。
  - `plain_fasta_is_current` 这个名字（master round 2 定名）现在同时服务 FASTA 与 GFF 产物，语义上可考虑改名 `plain_text_is_current`；本轮未改名以免动到 master 的探针/文档。

## round 4（servant：ms01 权威自检 + 真实数据端到端，2026-09-16 12:32）

- 触发：用户提供 ms01 口令，并指定「读 `task.md` 和 `report.md` 并按其执行」。本轮执行 report「未做 / 仍开放」里唯一被口令阻塞的项 U1（ms01 全量 `run_tests.py` + 真实 gz 数据端到端）。**代码零改动**：本轮只做权威环境验证与证据留存。
- 环境：`ms01`（`[internal host]`），`nproc` 256，`/home/apool` 146T 总量 / 余 65T，`/home/apool/songji/programfile/.venv/bin/python` = Python 3.12.3（本机 3.14.7）。
- 动手前先验镜像一致性：6 个改动文件在 `R:\songji\programfile` 与 `/home/apool/songji/programfile` 的 sha256 完全相同 —— `main.py 7b76b153…`、`shared/data/annotation_utils.py 85a78ca5…`、`shared/search/blast_utils.py 47004806…`、`designer_workbench.py c04ffe78…`、`tests/test_fasta_gz.py 47effc6f…`、`tests/test_gff_gz.py 31652a01…`。

### 全量套件

```bash
cd /home/apool/songji/programfile
PYTHONUTF8=1 .venv/bin/python run_tests.py     # 后台 nohup，日志 /tmp/fasta_gz_verify/full_run_tests.log
```

```text
Ran 371 tests in 70.845s

FAILED (errors=1, skipped=29)                  # 335 ok / 29 skipped / 1 error

ERROR: test_build_memory_limit_success_and_clean_failure (test_genome_index.GenomeIndexTests.test_build_memory_limit_success_and_clean_failure)
  File ".../tests/test_genome_index.py", line 109, in test_build_memory_limit_success_and_clean_failure
    meta = build_index(
  File ".../shared/search/genome_index.py", line 340, in build_index
    budget.check(
  File ".../shared/search/genome_index.py", line 194, in check
    raise MemoryLimitExceededError(
search.genome_index.MemoryLimitExceededError: Memory limit exceeded during counts: RSS 1238.75 MiB exceeds --max-memory-mb=1024 MiB
```

该 error 的归属（既有测试脆弱性，与本任务无关）：

```bash
# 1) 只用「本任务没碰过」的模块 -> 同样复现
.venv/bin/python -m unittest tests.test_analyze_scores tests.test_core tests.test_genome_index
#   Ran 69 tests in 14.347s -> FAILED (errors=1)  RSS 1169.53 MiB exceeds --max-memory-mb=1024 MiB
# 2) 窄化：test_core + test_genome_index 复现；test_analyze_scores + test_genome_index 通过
.venv/bin/python -m unittest tests.test_core tests.test_genome_index
#   Ran 62 tests -> FAILED (errors=1)  RSS 1165.51 MiB exceeds --max-memory-mb=1024 MiB
.venv/bin/python -m unittest tests.test_analyze_scores tests.test_genome_index
#   Ran 17 tests in 5.300s -> OK
# 3) 单独跑通过；本任务模块 + genome_index 一起跑也通过
.venv/bin/python -m unittest tests.test_genome_index
#   Ran 10 tests in 3.045s -> OK
.venv/bin/python -m unittest tests.test_fasta_gz tests.test_gff_gz tests.test_genome_index
#   Ran 27 tests in 3.716s -> OK
```

```text
mtime 证据（均早于本轮改动日 09-16）：
  shared/search/genome_index.py   2026-09-14 16:14:04     ← 未改动
  tests/test_genome_index.py      2026-09-14 16:14:08     ← 未改动
  tests/test_core.py              2026-09-13 22:45:14     ← 未改动
  （test_core 的 import 链含 scoring.deep_models / model_registry，其测试体执行后抬升进程 RSS）
  本任务改动文件                   2026-09-16 08:52 ~ 09:24
```

即：该用例用**进程级 RSS** 对 `--max-memory-mb=1024` 做断言，而先跑 `test_core` 会把 RSS 抬到 1.1+ GB，断言必然失败；与本任务（以及同仓库 drop-bowtie2 那批改动）无关。

- 附带结论：round 3 报告里「本机 `tests.test_offtarget_backend` 失败」那条在 ms01 上通过 —— `test_auto_and_large_indexed_apply_mismatch_only_defaults (test_offtarget_backend.BackendTests...) ... ok`（服务器有 NCBI BLAST+），与 round 3 的归因一致。

### 真实数据端到端（新增探针）

```bash
cd /home/apool/songji/programfile
PYTHONUTF8=1 .venv/bin/python docs/handoff/fasta-gz-prep/assets/ms01/servant_probe_round4.py
```

```text
host=ms01 python=3.12.3
PASS  A1..A7   ensure_plain_fasta：mini.fna.gz -> mini.fna，与 mini.fna 逐字节相同、非 gzip、无 .part 残留、复用同路径且 mtime 不变
PASS  B0       1.4 GB 副本 sha256 == gzip -dc 源（f45c2b9bd1a36ad54cec964ff5a009530f6c67949d295bba1dfd94f1f04c21e6）
PASS  B1/B2    _get_prepared_gtf(.gff.gz)：产物落在 entry_output；产物 sha256 432fe674… == 用户既有 *_with_utrs.gff3（1,096,091,190 B）
PASS  B3/B4/B5 日志 "Adding UTR (file: …_genomic.gff.gz) …"；基因列表 41192；含目标 42sp43
PASS  B6..B9   _get_prepared_genome(.fna.gz) -> 纯文本 .fna；raw entry 原值不变；复用日志；副本未被重写
PASS  B10..B12 _extract_sequences("42sp43") -> >42sp43-gene 2914 bp（软屏蔽小写与基因组一致）；_extract_target_fasta 写出 2975 B
PASS  C1/C2    引擎 load_genome_and_prepare_fasta(.fna.gz) -> (Fasta, 纯文本路径, None)；gz 路径与 plain 路径切片相同
PASS  D1..D4   工作台 _prepare_genome_fasta()：gz 行 -> 纯文本；plain 行原样返回；空行 -> ""
PASS  E1..E4   副作用面：genome 目录列表不变；用户 UTR（sha256）、源 .gz（mtime+size）、副本（mtime+size）均未变
PASS  F1..F6   夹具：.gff.gz -> *_with_utrs.gff3；暖缓存+新鲜产物静默命中；冷缓存复用日志；产物陈旧自动重建；gz 产物与 plain 产物逐字节相同
SUMMARY: 36 checks, 0 failed
```

- 关键哈希（本轮实测）：`.fna` 副本 `1466904845 B` sha256 `f45c2b9b…` == `gzip -dc .fna.gz`；`.gff.gz` 经 GUI 路径重建的 UTR 产物 `1096091190 B` sha256 `432fe674a967211d20671077927207aaa3daa81aaa40a4917bb37db0e415930c` == 用户既有 `_with_utrs.gff3`。
- 副作用面：服务器上只新增/覆盖 `/tmp/fasta_gz_verify/**`（探针与中间产物）；用户 `genome/Danio_rerio/` 目录内容、`.gz` 源、既有 `.fna` 副本、`_with_utrs.gff3` 全部零改动（E1-E4）。

### 本轮新增文件（仅交接目录，未动 master 既有文件）

| 文件 | 大小 | sha256 |
| --- | --- | --- |
| `docs/handoff/fasta-gz-prep/assets/ms01/servant_probe_round4.py` | 12399 B | `b57e3e7c970bf39656ce14e442278ad2f04501b65b55fd981b15f35a0b36b807` |
| `docs/handoff/fasta-gz-prep/assets/ms01/full_run_tests_ms01_20260916.log` | 50803 B | `f16c16365ede476f4d49544906e276d0727180258dd366dc9496b39487faa5b1` |

两个文件在服务器侧与本地 `R:\` 侧 sha256 一致；探针默认只写 `/tmp/fasta_gz_verify`（可用 `FASTA_GZ_WORK` 覆盖），不写仓库。

### 未做 / 仍开放

- U3 记录项（仍按 master 的分类只记录）：`shared/search/exact_offtarget.py:378`、`shared/search/genome_index.py:751`、`Target_xbp_Y_zbp_Target/extract_motifs.py:166` 的裸 `Fasta(path)`；`main.py:958`「Build genome index」手填 `.fna.gz` 仍失败；workbench 的 Search/Mask FASTA 行未接 `ensure_plain_fasta`。
- 未对用户真实的 1.1 GB `*_with_utrs.gff3` 做「强制陈旧 -> 重建」实验：那会覆盖用户资产且重建需数十分钟，因此真实文件只验证「复用不改写」（B1/B2 + E2），陈旧重建只在夹具上验证（F5）。
- `plain_fasta_is_current` 改名建议（round 3 记录）本轮未做。

### 待明确（给 master）

- `tests/test_genome_index.py::test_build_memory_limit_success_and_clean_failure` 依赖进程级 RSS，任何先跑 `test_core` 的整跑都会失败；是否开单修（例如按模块隔离或改测子进程 RSS）。
