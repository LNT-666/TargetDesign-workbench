# 核验报告：fasta-gz-prep

- round: 1
- verdict: pass
- updated: 2026-09-16 08:35
- 依据：`report.md`（round 1）+ 基线快照 `backup/fasta_gz_prep_20260916_081632/`（`main.py`、`annotation_utils.py`）
- 结论一句话：4 个改动文件全部符合规格，根因（pyfaidx 不接受普通 gzip FASTA）已修，明文路径零回归；本机 14 项独立核验 + 3 个测试模块全部通过，未采信 servant 转述。

## 逐条核验

| 任务项 | 结论 | 证据 |
| --- | --- | --- |
| P0-1 helper（C1-C10） | 通过 | 代码：`shared/data/annotation_utils.py:46-146`（`FASTA_EXTENSIONS`、`_plain_fasta_name`、`_first_nonblank_byte`、`_decompress_to_plain_fasta`、`_reusable_plain_fasta`、`ensure_plain_fasta`）。master 探针 `assets/master_verify_fasta_gz.py` V1-V10（见下） |
| P0-2 `_get_prepared_genome` | 通过 | 代码：`main.py:151-173`，缓存初始化 `main.py:53`。探针 V11：`returned=<tmp>\mini.fna`、缓存 1 条、`entry_genome` 原值未被改写 |
| P0-3 `_extract_sequences` | 通过 | 代码：`main.py:192`。探针 V12：gz 与 plain 的 `_extract_sequences` 返回值完全相同（1000 bp） |
| P0-4 `prepare_data` | 通过 | 代码：`main.py:302`（raw）、`:310`（存在性检查仍用 raw，解压失败不会误跑下载分支）、`:324-327`（prepared 或 showerror+return）、`:357`（build_blastdb）、`:367`（`params["genome"]`）、`:376`（library 框） |
| P0-5 提取目标/屏蔽序列 | 通过 | 代码：`main.py:443/449/455-458/470`、`main.py:490/496/502-505/523`；两处控制流逐行读过，`if not genome: showerror + return` 位置正确 |
| P0-6 workspace 映射不变 | 通过 | 代码：`main.py:512` 未被 diff 触及；探针 V13 `_workspace_mapping()["entry_genome"] == "genome"` |
| P0-7 回归测试 | 通过 | 新增 `tests/test_fasta_gz.py`（7 用例，含逐字节比较与 1000 bp 长度断言，非空跑）；master 自跑 `Ran 7 tests in 40.512s OK` |
| 范围纪律 | 通过 | 全仓 `*.py` mtime 扫描（> 2026-09-16 08:16:32，排除 `backup/`、`docs/`、`example/`、`external_tools/`、`native/`、`__pycache__`）：仅 `shared/data/annotation_utils.py 08:22:04`、`main.py 08:22:32`、`tests/test_fasta_gz.py 08:23:11` |
| C13 一致性 | 通过 | 探针 V14：`"genome": genome` 三处（367/470/523）均为 prepared；`raw_genome = self.entry_genome.get().strip()` 三处 GUI 入口（302/443/490）+ helper 内一处（153） |

## master 独立验证

- 基线 diff：用 difflib 对 `backup/fasta_gz_prep_20260916_081632/{main.py,annotation_utils.py}` 逐块比对；`main.py` 仅 12 个改动块（1 处 import、1 处缓存初始化、1 个新方法、3 个入口的 raw/prepared 拆分），无夹带重构；`annotation_utils.py` 仅新增 docstring/`import shutil`/136 行新助手，既有函数零改动。
- 独立探针（master 自写，与 servant 测试无关）：`docs/handoff/fasta-gz-prep/assets/master_verify_fasta_gz.py` → `14 checks, 0 failed`：
  - V1 明文输入原样返回且目录无新增文件；V2 `.gz` 名 + 明文内容按魔法字节原样返回；
  - V3 gz → 同级 `mini.fna`，与明文逐字节相同、首 2 字节非 `1f 8b`；
  - V4 二次调用复用（目标 mtime 不变，日志 `Using existing plain FASTA`）；
  - V5 源 gz 变新（mtime +10s、内容不同）→ 目标被重写为新内容（C4 新鲜度生效）；
  - V6 `Mini.FNA.GZ` → `Mini.FNA`（大小写）；V7 `genome.gz` → `genome.fna`（补扩展名）；
  - V8 伪造 gz → `None`，`bad.fna`/`bad.fna.part` 均不存在，日志含 `Unknown compression method`；
  - V9 gz 包 GFF（非 FASTA）→ `None`，无半成品，日志 `not FASTA (first byte is not '>')`；
  - V10 C8 回退：源目录内用同名**目录**挡住 `os.replace` → 成功回退到 `fallback_dir/mini.fna`；
  - V11 缓存与 C12（原值不变）；V12 端到端 gz==plain（序列 + 写出的 FASTA 字节）；
  - V13 workspace；V14 C13 源码签名。
- 根因复现（改动前证据保留）：`assets/master_probe_genome_gz.py` 在改动前输出 `plain OK / gz FAIL UnsupportedCompressionFormat`；改动后同一脚本两行均为 `OK`（master 已复跑）。
- 测试（master 自跑）：
  - `python -m py_compile main.py shared\data\annotation_utils.py tests\test_fasta_gz.py` → exit 0；
  - `python -m unittest tests.test_fasta_gz -v` → `Ran 7 tests in 40.512s OK`；
  - `python -m unittest tests.test_gff_gz -v` → `Ran 4 tests in 46.694s OK`（上一轮 gz 注释无回归）；
  - `python -m unittest tests.test_gui_common -v` → `Ran 3 tests in 0.005s OK`（workspace 读写无回归）。
- 未采信项：servant 报告里的输出与我的复跑逐条一致（含 `Ran 7 tests` 的用例名与计数）。

## 归属判定（既有失败 vs 本次引入）

- 用户上报的 `UnsupportedCompressionFormat` → 既有缺陷（改动前 `shared/data/local_extract.py:29` 直接 `Fasta(path)`），本次已消除；证据：改动前后同一个 `master_probe_genome_gz.py` 的对照输出。
- 「明文基因组行为」→ 无回归：V1（不复制不改写）、C2 契约；`tests.test_gff_gz`、`tests.test_gui_common` 全绿。
- 无新增失败用例：`tests/` 下与本次相关的三个模块全绿；未跑全量套件（`tests/test_unified_gui.py` 需 Tk 交互，属既有环境限制，非本次引入）。

## 新发现

- `main.py:157-159` — P3：`_get_prepared_genome` 的会话内缓存在命中时**不**复查 C4 新鲜度，因此同一进程里用户把 `.gz` 换成更新内容后不会自动重解压（重启 GUI 后正常）。与 C11 的字面要求一致，记录即可。
- `shared/data/annotation_utils.py:63-75` — P3：`_first_nonblank_byte` 会打开 gz 读一次首块做 C6 校验，随后 `_decompress_to_plain_fasta` 再读一次；只多读 1 MiB，代价可忽略。
- `shared/data/local_extract.py:29` — P3（既有）：`Fasta(...)` 句柄不关闭。除 servant 已记录的 Windows 临时目录清理问题外，还有一个真实风险：用户在 GUI 里换用新 `.gz` 重新解压覆盖同名 `.fna` 时，若旧句柄仍占用，`os.replace` 会失败（此时记日志并返回 None，不留半成品，界面给出 "Genome FASTA could not be prepared, see log"）。
- `shared/data/annotation_utils.py:50-56` — P3：C3 只按文件名末尾 `.gz` 剥离，`genome.txt.gz` 会产出 `genome.txt.fna`（servant 已在「待明确」记录，判定为按规格实现，无需回改）。
- `main.py:376` — P3（既有不一致，servant 已记录，master 采纳）：`_extract_target_fasta` / `_extract_mask_fasta` 的 `output_dir` 形参实际未被使用（真正落盘走 `_write_fasta` 里的 `entry_output`）；与本次改动无关，未修。
- 引擎/工作台仍是明文假设：`shared/search/blast_utils.py:655` 的 `_looks_like_fasta` 对 gz 返回 False（gbz 输入会被当成 GenBank 解析后 `sys.exit(6)`）；`designer_workbench.py` 的 Genome FASTA 输入框、`exact_offtarget.py:378`、`genome_index.py:751`、`Target_xbp_Y_zbp_Target/extract_motifs.py:166` 同理。用户链路上「数据准备 → 子工具」已通过 `params["genome"]` 传给纯文本，因此不影响当前需求，但用户若在 Designer 里手填 `.fna.gz` 仍会失败。

## ms01 权威验证（真实数据，2026-09-16 08:36，master 执行）

- 目标：`/home/apool/songji/genome/Danio_rerio/GCF_049306965.2_GRCz12tu_genomic.fna.gz`（435,771,780 B）+ 配套注释 `..._genomic_with_utrs.gff3`（1,096,091,190 B，上一轮产物）。
- 环境：已确认 `[internal host]` = ms01，`/home/apool` 146T 余量 65T，venv `pyfaidx 0.9.0.4` / Python 3.12.3（与本地一致）。
- 命令：`/home/apool/songji/programfile/.venv/bin/python /tmp/fasta_gz_e2e.py`（按 GUI 路径构造假 `MainApp`，依次调用 `_get_prepared_genome` / `_extract_sequences` / `_extract_target_fasta`）。
- 输出要点：

```text
LOG: Decompressed genome FASTA: /home/apool/songji/genome/Danio_rerio/GCF_049306965.2_GRCz12tu_genomic.fna
prepared: ...GCF_049306965.2_GRCz12tu_genomic.fna elapsed 9.1s
plain is_gzip: False size: 1466904845
LOG: Using existing plain FASTA: ...GCF_049306965.2_GRCz12tu_genomic.fna
reuse same path: True mtime unchanged: True elapsed 0.0s
gene count: 41192 sample: ['42sp43', 'LOC100000086', 'LOC100000275', ...]
_get_prepared_genome: ...GCF_049306965.2_GRCz12tu_genomic.fna raw entry kept: True
target: 42sp43 header: >42sp43-gene len: 2914 elapsed 49.1s
target fasta: /tmp/fasta_gz_e2e_out/42sp43-gene.fa 2975
```

- 逐字节校验：`wc -c` 两边同为 `1466904845`；`sha256sum` 两边同为 `f45c2b9bd1a36ad54cec964ff5a009530f6c67949d295bba1dfd94f1f04c21e6` —— 解压产物与 `gzip -dc` 输出完全一致。
- 副作用面（`ls -l`）：只新增 `GCF_..._genomic.fna`（1.4 GB）与 `GCF_..._genomic.fna.fai`（927 B）；原始 `.fna.gz` / `.gff.gz` / `_with_utrs.gff3` 时间戳与大小未变。
- 结论：用户真实场景（数据准备 → 目标序列提取）在权威环境通过；基因列表 41192 与用户上一轮工位日志一致，`42sp43` 的 2914 bp 编码区被正确取出（首次 49.1 s 含 pyfaidx 为 1.4 GB 文件建 `.fai`，第二次同进程 `_get_prepared_genome` 直接命中缓存）。

## 下一步

- 通过（round 1 关闭），剩余可选项：
  - U1（已完成，见上节）：ms01 真实 435 MB 基因组端到端通过（sha256 与 `gzip -dc` 一致）。
  - U2（可选，P2）：把 `ensure_plain_fasta` 接到引擎/工作台入口（`blast_utils.load_genome_and_prepare_fasta`、`designer_workbench` 的 Genome FASTA 行），让用户可以直接在 Designer 里填 `.fna.gz`。
  - U3（记录即可，P3）：上文 6 条新发现。
- 不通过项：无。

## round 2（master 接管，2026-09-16 08:56）

- 触发：用户要求「换了 `.gz` 后不要靠重启 GUI 才重新解压」。
- 属性判定：round 1 的 C11（缓存命中即返回）挡住了 C4 的新鲜度检查 —— **round 1 的规格缺口**，servant 的实现与当时的规格一致，不算返工。
- 改动（master 直接改，基线见 `backup/fasta_gz_prep_r1_snapshot_20260916_085637/`，由 round 1 版本反向重建）：
  - `shared/data/annotation_utils.py:94` — `_reusable_plain_fasta` 更名为公开的 `plain_fasta_is_current(target, source)`（语义不变，条件仍是：存在、普通文件、非 gz、大小 > 0、`mtime(target) >= mtime(source)`）；`ensure_plain_fasta` 内的唯一调用点同步更名。
  - `main.py:14-17` — import 增加 `plain_fasta_is_current`（改为括号多行 import）。
  - `main.py:151-162` — `_get_prepared_genome` 缓存命中改为 `if cached and plain_fasta_is_current(cached, raw_genome): return cached`；不满足则记日志 `Plain genome FASTA is stale or missing, re-preparing: <副本>`、丢弃缓存项，再走 `ensure_plain_fasta`（源更新→重解压；副本被删→重建）。
  - `tests/test_fasta_gz.py:177-211` — 新增用例 8（热缓存 + 源变新 → 重解压出新内容）与用例 9（副本被删 → 重建），并补 `import gzip`。
- master 证据（本地）：`python -m unittest tests.test_fasta_gz -v` → `Ran 9 tests in 42.029s OK`；`python -m py_compile` exit 0；自写探针 `assets/master_verify_fasta_gz.py` → `16 checks, 0 failed`（新增 V15 热缓存刷新、V16 副本删除重建；V14 改为按函数体范围断言，摆脱硬编码行号）。
- master 证据（ms01 真实数据，2026-09-16 08:56，未改动用户的 `.gz`）：把 1.4 GB 副本 mtime 强制改到早于源 1 小时，随后同一个 app 实例第三次调用 `_get_prepared_genome()`：
  ```text
  1st       : GCF_049306965.2_GRCz12tu_genomic.fna 0.0s  (Using existing plain FASTA)
  2nd warm  : True 0.00s
  forced stale: plain mtime < source mtime
  3rd stale : True 7.9s size=1466904845
  logs      : ['Plain genome FASTA is stale or missing, re-preparing: .../GCF_..._genomic.fna',
               'Decompressed genome FASTA: .../GCF_..._genomic.fna']
  sha256    : f45c2b9bd1a36ad54cec964ff5a009530f6c67949d295bba1dfd94f1f04c21e6 (副本) == gzip -dc (源)
  ```
- 未做（仍是 U 项）：`_get_prepared_gtf` 对 `*_with_utrs.gff3` 的复用只判断「文件是否存在」，源 gff 更新后仍会复用旧产物。同样的 mtime 规则可以套用，但该文件可能是用户手工改过的产物、且人类基因组重建 UTR 需数十分钟，故先不动，等用户拍板。
