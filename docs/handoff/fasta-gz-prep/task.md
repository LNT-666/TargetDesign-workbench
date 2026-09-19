# 任务：让 gzip 压缩的基因组 FASTA（.fna.gz / .fa.gz）能在数据准备与序列提取链路里使用

- task-slug: `fasta-gz-prep`
- round: 1
- master: 会话 A（master）
- servant: 会话 B（servant）
- repo: `R:\songji\programfile`（镜像服务器 `/home/apool/songji/programfile`）
- 权威运行环境：ms01 服务器 `/home/apool/songji/programfile/.venv/bin/python`（Python 3.12.3）
- 本地环境：`python` = Python 3.14.7（本机已装 pyfaidx 0.9.0.4 与 tkinter；本任务只用标准库 + pyfaidx，因此本地跑单测是可用的，但权威复跑仍归 master）
- 基线快照（master 已建，servant 不得修改）：`backup/fasta_gz_prep_20260916_081632/`（内含改动前的 `main.py` 与 `annotation_utils.py`）

## 0. 目标与边界

需求原文（用户）："在输入注释文件的时候，已经可以输入 gz 压缩包。但是输入 fasta 文件就不行。请增加这个功能。"

master 的解读（以此为准；如认为解读有误，先写进 `report.md` 的「待明确」，不要自行扩大范围）：
上一轮已完成 **注释文件** 的 `.gff.gz` 支持；本轮要让 **数据准备里的 Genome file (FASTA)** 也支持 gzip 压缩的基因组 FASTA。用户手上的基因组几乎全是 `.fna.gz`（`R:\songji\genome\*\*.fna.gz`），例如 `/home/apool/songji/genome/Danio_rerio/GCF_049306965.2_GRCz12tu_genomic.fna.gz`；同一个目录里没有未压缩的 `.fna`。

要做到：

1. Genome file (FASTA) 填 `.fna.gz` 时，目标/屏蔽序列提取不再报 `UnsupportedCompressionFormat`；
2. 下游拿到的必须是**未压缩的纯文本 FASTA 路径**（pyfaidx 读序列、`makeblastdb -in`、子工具的 `params["genome"]`）；
3. 同一份基因组，用 `.fna.gz` 与用已解压的 `.fna`，提取结果逐字符相同；
4. 用户在输入框里填的 `.fna.gz` 原值不变（只做内部换算，workspace 仍保存原值）。

不在范围内（不要做）：注释文件的 gz 逻辑（上一轮已完成）；`shared/search/*` 引擎；`designer_workbench.py` / `unified_gui.py` / `webapp/` / `Target_xbp_*` 的 gz 支持；下载流程；BGZF/bgzip 支持；任何 UTR/评分/输出列契约。

## 1. 规则 / 契约（唯一权威版本，servant 不需要也不允许重新调研）

```text
C1  gz 判定：读文件头前 2 字节，等于 b"\x1f\x8b" 才视为 gzip（复用既有 is_gzip_file）。不得只看扩展名；
    路径不存在 / 是目录 / 不可读时返回 False，不抛异常。
C2  非 gz 输入：ensure_plain_fasta(path) 原样返回 path；不得复制、改名、改写或删除任何文件（C12 的既有行为不变）。
C3  gz 输入的解压目标：<gz 所在目录>/<名>，其中 <名> = 去掉末尾一个 ".gz"（大小写不敏感）后的基名；
    若结果没有 FASTA 类扩展名（.fa/.fna/.fasta/.fas/.fsa，大小写不敏感），追加 ".fna"。
    例：GCF_x_genomic.fna.gz -> GCF_x_genomic.fna；genome.gz -> genome.fna。
C4  复用条件：目标文件已存在 且 非 gzip 且 大小 > 0 且 mtime(目标) >= mtime(源) —— 直接复用，不重写。
    否则重新生成（允许覆盖）。
C5  原子写出：先写同目录临时文件（如 <目标>.part），成功后 os.replace 到目标；任何异常（损坏的 gz、IO 错误、磁盘满）
    都要删除临时文件、通过 log_func 记录失败原因、返回 None。不得留下半个目标文件。
C6  内容校验：解压产物的第一个非空字节必须是 ">"（允许 UTF-8 BOM 与空白/换行）。否则按失败处理（同 C5），
    日志里写明不是 FASTA。
C7  流式解压：gzip.open(源, "rb") + 分块写出（1 MiB 级），不得把整文件读进内存。
C8  目录回退：目标目录不可写（OSError）时回退到调用方传入的 fallback_dir；两处都不可写 -> 失败（返回 None）。
C9  日志（log_func 可为 None，此时静默）：解压成功记 "Decompressed genome FASTA: <目标>"；复用记
    "Using existing plain FASTA: <目标>"；失败记 "Failed to prepare FASTA (<源>): <原因>"。
C10 返回契约：ensure_plain_fasta 返回的路径必须能被 open(path, "r") 直接读取（纯文本 FASTA）。
C11 main.py 的 _get_prepared_genome() 返回纯文本 FASTA 路径或 None；None = 输入为空 / 文件不存在 / 准备失败。
结果放进 self._genome_cache（键 = 用户原始输入），缓存命中且目标仍存在时直接返回。
C12 用户原始输入在 entry_genome 与 workspace 里保持不变；只有内部消费（pyfaidx 读序列、makeblastdb -in、
    params["genome"]）使用 prepared 路径。
C13 写进 params["genome"] 的一律是 prepared 路径（prepare_data / extract_target_sequences / extract_mask_sequences
    三处），否则子工具会再次拿到 .gz。
```

## 2. 现状证据（master 已核实，可直接引用）

- 报错点：`shared/data/local_extract.py:28-29` —— `from pyfaidx import Fasta` / `genome = Fasta(genome_fasta)`。
- master 端到端复现（本机 pyfaidx 0.9.0.4，走 main.py 自身代码路径；脚本见 `assets/master_probe_genome_gz.py`）：

```text
plain OK >A-gene 1000
gz FAIL UnsupportedCompressionFormat | Compressed FASTA is only supported in BGZF format. Use the samtools bgzip utility (instead of gzip) to compress your FASTA. For example: gunzip file.fa.gz; bgzip file.fa
```

  即：同一份 4000 bp 的 `NC_000001.11` 与同一份 `mini.gff`，明文 FASTA 能提取出 1000 bp 的 `>A-gene`，换成 `.fna.gz` 直接抛 `UnsupportedCompressionFormat`。
- 用户链路上的原始路径传递点（都是把输入框原值往下传）：
  - `main.py:167` `_extract_sequences`：`genome = self.entry_genome.get().strip()`
  - `main.py:277` `prepare_data`；`:327` `self.build_blastdb(genome, output_dir)`；`:337` `"genome": genome`
  - `main.py:413` / `:436` `extract_target_sequences`
  - `main.py:456` / `:485` `extract_mask_sequences`
- 用户环境证据：`R:\songji\genome\Danio_rerio\` 下只有 `GCF_049306965.2_GRCz12tu_genomic.fna.gz`（435 MB）与 `..._with_utrs.gff3`（上一轮产物），没有 `.fna`。
- 上一轮已在生产验证注释 gz：`logs/main_20260915_165858.log` 记录 `UTR added: /home/apool/songji/genome/Danio_rerio/GCF_049306965.2_GRCz12tu_genomic_with_utrs.gff3` 与 `已从缓存中提取 'gene_name' 类型的基因列表，共 41192 个`。
- 既有可复用工具：`shared/data/annotation_utils.py:22-40`（`GZIP_MAGIC`、`is_gzip_file`、`open_annotation_text`，上一轮加入）。
- 引擎侧同类缺陷（**本轮不修**，只作为背景）：`shared/search/blast_utils.py:655-661` 的 `_looks_like_fasta` 对 gz 返回 False，随后按 GenBank 解析失败并 `sys.exit(6)`；`shared/search/exact_offtarget.py:378`、`shared/search/genome_index.py:751`、`Target_xbp_Y_zbp_Target/extract_motifs.py:166` 都是直接 `Fasta(path)`。

## 3. 必做改动

- [ ] P0-1 `shared/data/annotation_utils.py` 新增 `ensure_plain_fasta(path, log_func=None, fallback_dir=None)`
  - 位置：`shared/data/annotation_utils.py:40` 之后（紧随 `open_annotation_text`）；文件头 import 区（`:3-5`）补 `import shutil`；模块 docstring 补一句「本模块同时承载 gz / 文本读取的通用帮手（注释与 FASTA）」。
  - 期望行为：满足 C1-C10。建议再拆一个小函数 `_plain_fasta_name(basename)` 负责 C3 的命名规则，便于单测。
  - 证据要求：`python -m unittest tests.test_fasta_gz -v` 完整输出；report 里另贴 plain / gz / 伪 gz 名 三例的最小调用与返回值。

- [ ] P0-2 `main.py` 新增 `_get_prepared_genome()`
  - 位置：`main.py:148` 之后（`_get_prepared_gtf` 之后）；`self._genome_cache = {}` 加在 `main.py:52`（`self._gtf_cache = {}`）之后。
  - 期望行为：C11。fallback_dir 取 `self.entry_output.get().strip()`（属性缺失或为空时传 None）。
  - 证据要求：`tests/test_fasta_gz.py` 用例 7；report 贴出 gz 输入时的返回值与日志行。

- [ ] P0-3 `main.py:167` `_extract_sequences` 使用 prepared 路径
  - 位置：`main.py:167`
  - 期望行为：`genome = self._get_prepared_genome()`；为 None 时保持原有 `FileNotFoundError`（可把文案补成 "Genome FASTA file not specified or not found"）。其余逻辑（ids 切分、`get_region_sequence` 调用、60 列换行格式化）不变。
  - 证据要求：用例 7 的对比断言。

- [ ] P0-4 `main.py:276-352` `prepare_data` 使用 prepared 路径
  - 位置：`main.py:277`、`:285`、`:327`、`:337`、`:346`
  - 期望行为：
    - `:277` 保留 `raw_genome = self.entry_genome.get().strip()`，`:285` 的存在性检查仍用 **raw**（否则解压失败会误跑「下载」分支）；
    - 通过 raw 检查后：`genome = self._get_prepared_genome()`；为 None 时 `messagebox.showerror("Error", "Genome FASTA could not be prepared, see log")` 并 `return`；
    - `:327` 传 prepared 给 `build_blastdb`；`:337` `"genome": genome` 即 prepared；`:346` `entry_library_genome` 填 prepared。
  - 证据要求：代码 diff + 用例 7；report 里说明 `params["genome"]` 的值。

- [ ] P0-5 `main.py:412-440` `extract_target_sequences` 与 `main.py:455-489` `extract_mask_sequences`
  - 位置：`main.py:413`、`:436`、`:456`、`:485`
  - 期望行为：同样把 raw 检查与 prepared 取值分开；`:436` / `:485` 的 `params["genome"]` 一律 prepared。
  - 证据要求：代码 diff。

- [ ] P0-6 不要改 `main.py:512` 的 workspace 映射
  - 位置：`main.py:512`（`"entry_genome": "genome"`）
  - 期望行为：保持不变，`entry_genome` 仍读写用户原始输入。

- [ ] P0-7 新回归测试 `tests/test_fasta_gz.py`
  - 风格对齐 `tests/test_gff_gz.py`：`FakeEntry`、`MainApp.__new__(MainApp)`、不创建 Tk root、只写 tempfile 目录（不得往仓库里写文件）；`asset` 路径基于 `__file__` 计算。
  - fixture（master 已放好）：`docs/handoff/fasta-gz-prep/assets/mini.fna`（4000 bp `NC_000001.11`，70 列/行）、`mini.fna.gz`（同一内容，mtime=0 的确定字节）、`mini.gff`（2 个基因 A/B，坐标与 mini.fna 匹配）。
  - 用例：
    1. plain 输入 -> 返回原路径，且同目录没有新增文件；
    2. `mini.fna.gz` -> 返回 `<tmp>/mini.fna`，内容与 `mini.fna` 逐字节相同，且不是 gzip 头；
    3. 第二次调用 -> 返回同一路径且目标 mtime 不变（复用，未重写）；
    4. 扩展名叫 `.gz` 但内容是纯文本 -> 原样返回（按魔法字节判定）；
    5. 伪造 gz（`b"\x1f\x8b"` + 垃圾）-> 返回 None，且目标文件不存在（无半成品残留）；
    6. `genome.gz`（FASTA 载荷）-> `<tmp>/genome.fna`（C3 的扩展名补齐）；
    7. 端到端：`_extract_sequences("A", "Coding region", None, "gene_name", mini.gff)` 在 gz 与 plain 两种 Genome 输入下返回完全相同；`_extract_target_fasta(...)` 产出的 FASTA 文本相同；`_get_prepared_genome()` 返回的是纯文本路径（首字节 `>`）。
  - 证据要求：`python -m unittest tests.test_fasta_gz -v` 完整输出（含 `Ran N tests ... OK`）。
  - 环境坑（master 实测）：`get_region_sequence` 内部 `Fasta(...)` 不会关闭句柄，Windows 上会让 `tempfile.TemporaryDirectory` 清理失败（`PermissionError: WinError 32`）。测试里请用 `tempfile.TemporaryDirectory(ignore_cleanup_errors=True)`（或自己建临时目录后不删），不要为此改 `local_extract.py`。

## 4. 不要做的事

- 不改 `shared/data/local_extract.py`（含 `:41` 的 `open(annotation_file, "r")` 明文读取契约）。
- 不改 `shared/search/*`、`designer_workbench.py`、`unified_gui.py`、`webapp/`、`Target_xbp_Target/`、`Target_xbp_Y_zbp_Target/`、`tools/`、`basic/`。
- 不改 `shared/data/download_data.py`（其下载路径本来就会解压成 `.fna`）。
- 不改 `_get_prepared_gtf` 与上一轮的 gz 注释逻辑、`GZIP_MAGIC`/`is_gzip_file` 的语义。
- 不引入第三方依赖（只用标准库 `gzip` / `shutil` / `os`）。
- 不删除、不移动任何文件；不碰 `backup/`、`example/`、`external_tools/`、`native/`、`models/`。
- 不跑 `run_tests.py` 全量套件、不连服务器跑批（那是 master 的核验范围）。

## 5. 决策项（未确认则按推荐执行）

- D1 帮手放哪 -> 推荐放在 `shared/data/annotation_utils.py`（不新建模块）。理由：`main.py:14` 已经 import 该模块，上一轮的 gz 帮手也在里面；代价是模块名偏注释语义，用 docstring 说明即可。
- D2 解压产物落哪 -> 推荐 gz 同级目录（C3），fallback 到 output 目录（C8）。理由：与上一轮 `_with_utrs.gff3` 同级落盘的既有习惯一致；而且 `shared/search/blast_utils.py:669 _sibling_fasta_for_annotation` 正好会认同级 `.fna`。
- D3 是否顺带修引擎 / workbench 的 gz -> 推荐**不修**。理由：用户链路「数据准备 -> 子工具」已经靠 params 传纯文本；引擎侧改动需要服务器大基因组复跑，成本高，列入 review 的 U 项。
- D4 复用是否加 mtime 新鲜度判断 -> 推荐加（C4）。理由：基因组是 GB 级，用户换了 `.gz` 后不应继续用旧 `.fna`。
- D5 解压产物是否保留原后缀 -> 推荐保留（C3）。理由：`.fna` 是 BLAST/pyfaidx 与同目录惯例认识的扩展名。

## 6. 轻量自检（servant 的检验上限）

```powershell
python -m py_compile main.py shared\data\annotation_utils.py tests\test_fasta_gz.py
python -m unittest tests.test_fasta_gz -v
python -m unittest tests.test_gff_gz -v
```

- 编码注意：本机 Python 默认编码是 GBK，跑测试前设 `$env:PYTHONUTF8="1"`。
- 不要跑全量 `run_tests.py`，不要上服务器。
- 可选（够用就够）：把 `docs/handoff/fasta-gz-prep/assets/mini.fna.gz` 拷到临时目录，直接调 `ensure_plain_fasta` 看解压产物（用例 2、3 已覆盖）。

## 7. 交付要求

- 快照：master 已建 `backup/fasta_gz_prep_20260916_081632/`，servant 不必再建，且不得修改该目录。
- 完成后：`state.json` 置 `ready_for_review`，写 `report.md`（改动文件+行号、命令原文与输出、未做项及原因、附带发现、待明确）。
- 附带发现只记录、不修复，交 master 决定。
- 编码坑：本机 PowerShell 是 7.x（UTF-8 输出），但 `main.py` / `annotation_utils.py` 含中文注释；修改时用 `apply_patch`，或用 Python 脚本 + `encoding="utf-8"`。**不要**用 `Get-Content` / `Set-Content` 改含中文的源文件。
- `apply_patch.bat` 传多行参数会被 cmd 截断；必要时直接调真实 exe：
  `& "C:\Users\ASUS\AppData\Local\OpenAI\Codex\bin\12219cbfbcbddde7\codex.exe" --codex-run-as-apply-patch $patch`
  （hash 目录名可能随版本变化，先确认路径存在；工作目录先切到本地盘符，UNC 工作目录会被 cmd 拒绝）。
- 共享盘 I/O 慢：命令要聚焦，避免全仓扫描。


---

# round 2（master 接管）：缓存命中时复查新鲜度

- 触发：用户反馈「换了 `.gz` 内容后，除非重启 GUI（或删掉旁边的 `.fna`），否则一直用旧的解压产物」。
- 定性：round 1 的 C11 只要求「缓存命中且目标存在就返回」，把 C4 的 mtime 新鲜度检查挡在了缓存之外 —— 属 round 1 的规格缺口，不是 servant 的越界或实现错误。
- 处理：master 明确接管（`master_takeover`）后直接修改，未再开 servant 轮次；改动与证据见 `review.md` 的「round 2」小节。
- 新增要求（作为 C14，替代 C11 的缓存语义）：
  ```text
  C14 缓存命中必须按 C4 复查：仅当 plain_fasta_is_current(副本, 源) 为真才返回缓存；
      否则丢弃该缓存项、记一条日志，并重新走 ensure_plain_fasta（源变新则重新解压，副本被删则重建）。
  C15 "当前"的判定只有一处实现：shared/data/annotation_utils.py 的 plain_fasta_is_current()
      （round 1 的私有 _reusable_plain_fasta 改名为公开名，语义不变）。
  ```
- 验收：`tests/test_fasta_gz.py` 用例 8/9（同进程热缓存 + 源变新 / 副本被删）；master 探针 V15/V16；ms01 真实 1.4 GB 副本上强制陈旧后 7.9 s 自动重解压且 sha256 不变。
