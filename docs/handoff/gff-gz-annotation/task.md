# 任务：让 gzip 压缩的 GFF/GTF 注释文件能在 UTR 预处理与基因列表加载中被正确读取

- task-slug: `gff-gz-annotation`
- round: 1
- master: 会话 A（master）
- servant: 会话 B（servant）
- repo: `R:\songji\programfile`（镜像服务器 `/home/apool/songji/programfile`）
- 权威运行环境：ms01 服务器 `/home/apool/songji/programfile/.venv/bin/python`（Python 3.12.3）
- 本地环境：`python` = Python 3.14.7，仅用于语法检查与最小复现（本任务只用标准库，不需要 numpy/服务器）

## 0. 目标与边界

用户在 GUI 的 annotation 输入框里选中一个 **gzip 压缩**的 GFF（本次实测：
`/home/apool/songji/genome/Danio_rerio/GCF_049306965.2_GRCz12tu_genomic.gff.gz`）后，
`Loading search list...` 流程报 `Failed to add UTR: ... UnicodeDecodeError` 并最终
`GTF preprocessing failed`。要做到：

1. `_get_prepared_gtf` 不再抛 `UnicodeDecodeError`；
2. 返回给下游的路径必须是**未压缩的纯文本 GFF3**（下游 `_extract_target_fasta` 与设计脚本都按文本读）；
3. `Load Target list` / `Load Mask list` 能正常加载基因列表。

不在范围内（不要做）：下载流程、UTR 坐标算法、GFF 字段/输出列契约、其它格式的 gz 支持（FASTA.gz 等）。

## 1. 规则 / 契约（唯一权威版本，servant 不需要也不允许重新调研）

```text
C1 gzip 判定：读取文件头前 2 字节，等于 b"\x1f\x8b" 即视为 gzip。不得只看扩展名；
   路径不存在/不可读/是目录时返回 False，不得抛异常。
C2 文本读取：gzip 用 gzip.open(path, "rt", encoding="utf-8")；否则 open(path, "r", encoding="utf-8")。
   两者都是 universal newline 模式，对同一份内容产生完全相同的文本。
C3 编码：所有读写一律显式 encoding="utf-8"（文件读取、子进程管道、写出文件），不依赖平台默认编码。
C4 下游契约：_get_prepared_gtf 返回的路径必须能被 open(path, "r") 直接读；输入是 gz 时必须先落盘纯文本副本再返回。
C5 命名规则：输出基名 = 输入基名从右往左循环剥离尾部 .gz/.gff/.gff3/.gtf（大小写不敏感），再拼 "_with_utrs.gff3"。
   例：GCF_049306965.2_GRCz12tu_genomic.gff.gz -> GCF_049306965.2_GRCz12tu_genomic_with_utrs.gff3
C6 既有行为必须保持（纯文本输入路径完全不变）：
   - 基名含 "_with_utrs" 或已含 UTR 特征的纯文本 -> 直接返回该输入路径（不复制、不改名）；
   - 纯文本且无 UTR -> 生成 {base}_with_utrs.gff3，其字节内容与改动前一致。
C7 UTR 判定/生成逻辑不变：add_utrs_to_gff.py 在输入已含 UTR 时原样输出全部行，不改坐标、不改 feature 类型。
```

## 2. 现状证据（master 已核实，可直接引用）

- `shared/data/add_utrs_to_gff.py:51` `with open(input_file, 'r') as f:`，`:52` `for line in f:` — 以文本方式打开 gz，必然失败。
- master 复现（本机，与服务器报错同根因）：
  - `python shared\data\add_utrs_to_gff.py docs\handoff\gff-gz-annotation\assets\mini.gff.gz`
    → `UnicodeDecodeError: 'gbk' codec can't decode byte 0x8b in position 1`，exit=1（服务器上是 `'utf-8' codec`）。
  - `python shared\data\add_utrs_to_gff.py docs\handoff\gff-gz-annotation\assets\mini.gff`（同内容明文）
    → 输出 12 行原始行 + 4 行 UTR（`five_prime_UTR` / `three_prime_UTR` 各 2 行，正负链各一），exit=0。
- `main.py:123-128` 打印 `Adding UTR (file: ...)` / `Failed to add UTR: {proc.stderr}`，与用户贴出的日志逐字一致
  → 用户链路 = `main.py:1646`(Loading search list) → `main.py:1658-1663`(_load_list) → `main.py:81`(_get_prepared_gtf)。
- `main.py:102` 的预检查同样用 `open(raw_gtf, 'r')`；异常被 `main.py:113-114` 的 `except Exception: pass` 吞掉
  → gz 输入时 `has_utr` 恒为 False（静默错误结果）。
- `main.py:116-119` 输入已含 UTR 时直接返回**原始路径**；若原始路径是 .gz，下游 `main.py:298` 的 `_extract_target_fasta`
  及设计脚本会再次按文本读 gz → 必须在 gz 场景绕过该分支（见 P0-4d）。
- `shared/data/annotation_utils.py:29` `with open(gff_path, 'r') as f:` 同样读不了 gz；`:55-58` 的 `except Exception`
  会把它伪装成「没有基因」，导致列表为空而不是报错。
- master 探针（`docs/handoff/gff-gz-annotation/assets/probe_gz_read.py`）：
  - `sniff plain: False  sniff gz: True`（magic bytes `1f8b`）；
  - `text identical: True 810 810`（`gzip.open(gz,"rt",encoding="utf-8")` 与明文逐字符相等）。
- 基线快照：`backup/gff_gz_annotation_20260915_151757/`（`main.py`、`add_utrs_to_gff.py`、`annotation_utils.py` 改动前副本，master 建立，供 diff 与回归比对）。
- 固定 fixture（master 放好，可直接用）：
  `docs/handoff/gff-gz-annotation/assets/mini.gff`（810 B，2 基因/2 mRNA/4 exon/4 CDS/2 注释行）
  `docs/handoff/gff-gz-annotation/assets/mini.gff.gz`（262 B，内容同上）

## 3. 必做改动

- [ ] P0-1 新增 gz 感知的读文件 helper
  - 位置：`shared/data/annotation_utils.py`，在 `:19`（`parse_gff_attributes` 结束）与 `:21`（`_load_gene_attributes` 定义）之间。
  - 期望行为：新增两个模块级函数 —
    `is_gzip_file(path) -> bool`（按 C1，异常一律 False）；
    `open_annotation_text(path, encoding="utf-8")`（按 C2 返回**已打开的文本句柄**，交给调用方 `with` 管理）。
  - 证据要求：贴出对 `mini.gff` / `mini.gff.gz` 分别打印 `is_gzip_file` 与两次 `read()` 文本相等的小脚本与输出。

- [ ] P0-2 基因属性读取改用 helper
  - 位置：`shared/data/annotation_utils.py:29`
  - 期望行为：`with open_annotation_text(gff_path) as f:`；明文解析结果与改动前完全一致；`.gz` 路径也能解析出 gene 属性。
  - 证据要求：`load_gene_list(<mini.gff.gz 原始路径>, "gene_name", None, {}, print)` 返回 `['AAA', 'BBB']`。

- [ ] P0-3 UTR 脚本支持 gz 输入（根因修复）
  - 位置：`shared/data/add_utrs_to_gff.py:51`
  - 期望行为：`with open_annotation_text(input_file) as f:`。
  - 约束（重要）：该脚本既能被直接执行（`python shared/data/add_utrs_to_gff.py <in>`，此时 `sys.path[0]` 是 `shared/data`），
    也可能被测试按 `data.add_utrs_to_gff` 导入，因此头部必须是：
    ```python
    import os
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from annotation_utils import open_annotation_text
    ```
    不要用相对导入 `from .annotation_utils import ...`。
  - 证据要求：对 `mini.gff.gz` 与 `mini.gff` 各跑一次同一命令，两次 stdout **逐字节相同**（`fc` 或 sha256），退出码均为 0。

- [ ] P0-4 main.py：预检查 + gz 强制落地纯文本 + 命名
  - 位置与期望行为：
    - `main.py:14` → `from data.annotation_utils import is_gzip_file, load_gene_list, open_annotation_text`
    - `main.py:95` → base 按 C5 循环剥离 `.gz/.gff/.gff3/.gtf`（大小写不敏感）
    - `main.py:102` → 改用 `open_annotation_text(raw_gtf)`；gz 判定与 `has_utr` 探测各只做一次（局部变量保存），gz 判定应在 `try` 之外或先做，不要被 `except` 吞掉
    - `main.py:116-119` → 提前返回条件加 gz 排除（`if has_utr and not <gz>` 才返回 `raw_gtf`）；gz 输入一律走 `:121-136` 子进程分支产出纯文本副本（脚本对含 UTR 输入原样输出，副本内容正确）
    - `main.py:125-126` → `open(utr_path, 'w', encoding='utf-8')` 与 `subprocess.run(..., text=True, encoding='utf-8')`
  - 期望行为：gz 输入返回 `<output_dir>/<C5 基名>_with_utrs.gff3` 且该文件是纯文本 GFF3；纯文本输入的返回值与字节输出与改动前一致。
  - 证据要求：用假 `self`（`main.MainApp.__new__(main.MainApp)`，**不要**创建 Tk root）调用 `_get_prepared_gtf`，覆盖 3 个用例（gz 输入 / 明文无 UTR / 明文已含 UTR）并贴出脚本与输出。

- [ ] P0-5 回归测试
  - 位置：新文件 `tests/test_gff_gz.py`（风格对齐 `tests/test_gui_common.py`：假对象，不建 Tk root）
  - 期望行为（4 个用例）：
    1. `from data.add_utrs_to_gff import read_gff` 对 `mini.gff.gz` 与 `mini.gff` 返回相同的行数/基因数/`has_utr`；
    2. 端到端：`subprocess.run([sys.executable, "shared/data/add_utrs_to_gff.py", gz], capture_output=True, text=True, encoding="utf-8")` 的 stdout == 明文调用 stdout，且 returncode == 0；
    3. `_get_prepared_gtf(<mini.gff.gz>)` 返回文件存在、可用 `open(..., encoding="utf-8")` 读、含 `five_prime_UTR` 行、文件名以 `mini_with_utrs.gff3` 结尾；
    4. `load_gene_list(<mini.gff.gz 原始路径>, "gene_name", None, {}, None) == ["AAA", "BBB"]`。
  - 提示：`_get_prepared_gtf` 会用到 `self.entry_output` / `self._gtf_cache` / `self.log`；用 `main.MainApp.__new__(main.MainApp)` 后自行赋值即可（`CommonGUIMixin.log` 在无 `log_text` 属性时静默返回，不碰 Tk）。
  - fixture：直接用 `docs/handoff/gff-gz-annotation/assets/mini.gff{,.gz}`。
  - 证据要求：`python -m unittest tests.test_gff_gz -v` 完整输出。

## 4. 不要做的事

- 不改 `shared/data/download_data.py`（其下载路径已解压，不是本次根因）。
- 不改 UTR 生成算法、`source` 字段（`BestRefSeq`）、GFF 列数或字段顺序。
- 不改 `_gtf_cache` 结构与 `_with_utrs` 提前返回语义（P0-4d 的 gz 例外除外）。
- 不修 `read_gff` 中「注释行保留换行 → 输出多空行」的既有行为（见附带发现 A1），它会改变既有明文字节输出。
- 不新增第三方依赖（只用标准库 `gzip`）。
- 不触碰 `backup/`、`example/`、`external_tools/`、`native/`、`webapp/`；不删除或移动任何文件。
- 不跑全量测试套件、不做服务器跑批（那是 master 的核验范围）。

## 5. 决策项（未确认则按推荐执行）

- D1 输出命名 → 推荐按 C5 剥离多后缀。理由：避免 `..._genomic.gff_with_utrs.gff3` 这种双后缀名。
- D2 gz 且已含 UTR 时是否仍落地纯文本副本 → 推荐**是**（P0-4d）。理由：C4 下游契约，否则下游读 .gz 会再炸一次。
- D3 helper 放在 `shared/data/annotation_utils.py` → 推荐是。理由：该模块已是注释解析工具的家，`main.py:14` 已 import 它，无需新建模块。
- D4 是否顺带把 `_load_gene_attributes` 改为 helper → 推荐是（1 行）。理由：同一契约，防后续把原始 gz 路径直接传进来的隐患。

## 6. 轻量自检（servant 的检验上限）

```powershell
python -m py_compile shared\data\add_utrs_to_gff.py shared\data\annotation_utils.py main.py
python shared\data\add_utrs_to_gff.py docs\handoff\gff-gz-annotation\assets\mini.gff    > $env:TEMP\plain.out 2>&1; "plain exit=$LASTEXITCODE"
python shared\data\add_utrs_to_gff.py docs\handoff\gff-gz-annotation\assets\mini.gff.gz > $env:TEMP\gz.out    2>&1; "gz exit=$LASTEXITCODE"
fc.exe $env:TEMP\plain.out $env:TEMP\gz.out
python -m unittest tests.test_gff_gz -v
```

（`fc` 输出 `FC: no differences encountered` 即通过。共享盘 I/O 慢，命令保持聚焦。）

## 7. 交付要求

- 快照：master 已建 `backup/gff_gz_annotation_20260915_151757/`，servant 不必再建，且不得修改该目录。
- 完成后：把 `state.json` 置 `ready_for_review`，并写 `report.md`（改动文件+行号、命令原文与输出、未做项及原因、附带发现、待明确）。
- 附带发现只记录、不修复。
- 编码注意：本机 PowerShell 是 7.6.5（UTF-8 输出），但编辑含中文的 `.py` 请用 `apply_patch`，或用 Python 脚本 + `encoding="utf-8"`；
  不要用 `Get-Content`/`Set-Content` 修改含中文的源文件（会被 GBK 双重编码损坏）。