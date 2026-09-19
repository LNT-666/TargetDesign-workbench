# 核验报告：gff-gz-annotation

- round: 1
- verdict: pass_with_followups
- updated: 2026-09-15 15:58
- 依据：`report.md`（round 1）+ 基线快照 `backup/gff_gz_annotation_20260915_151757/`
- 结论一句话：servant 的 4 个文件改动全部符合规格，根因已修，明文路径无回归；本机证据由 master 独立复跑，未采信转述。

## 逐条核验

| 任务项 | 结论 | 证据 |
| --- | --- | --- |
| P0-1 helper | 通过 | 代码：`shared/data/annotation_utils.py:22-40`（`GZIP_MAGIC`、`is_gzip_file`、`open_annotation_text`）。探针 `master_verify.py` V5：`is_gzip dir/missing/plain/gz = False/False/False/True` |
| P0-2 基因属性读取 | 通过 | `master_verify_e.py`：`OLD load_gene_list(plain)=['A','B']`、`OLD load_gene_list(gz)=[]`（日志里是被吞掉的 `'gbk' codec can't decode byte 0x8b`），`NEW plain=['A','B']`、`NEW gz=['A','B']` → 静默空列表的旧行为已消除 |
| P0-3 UTR 脚本 gz | 通过 | `master_verify.py` V1：`new(plain) sha=d2202d0b97dc2ec6`、`new(gz) sha=d2202d0b97dc2ec6`、`old(plain) sha=d2202d0b97dc2ec6` → gz==plain 且与基线脚本逐字节一致 |
| P0-4 main.py | 通过 | 代码：`main.py:95`（gz 判定一次）、`:97-105`（剥离 `.gz/.gff/.gff3/.gtf`）、`:107`、`:113`、`:127`、`:136-137`。探针 V3：A(gz)→`mini_with_utrs.gff3` 纯文本含 UTR；B(明文无 UTR)→同上；C(明文含 UTR)→原样返回输入；D(gz 含 UTR)→`has_utr_with_utrs.gff3`，非 gz 头、保留 `five_prime_UTR` |
| P0-5 回归测试 | 通过 | master 自跑 `python -m unittest tests.test_gff_gz -v` → `Ran 4 tests in 43.659s OK`（4 个用例断言有效，非空跑） |
| 范围纪律 | 通过 | mtime 扫描（2026-09-15 14:55 之后，排除 backup/example/external_tools/native/.venv/__pycache__）：仅 `shared/data/annotation_utils.py 15:28`、`shared/data/add_utrs_to_gff.py 15:29`、`main.py 15:29`、`tests/test_gff_gz.py 15:32` 及交接文档本身；无越界改动 |

## master 独立验证

- 代码比对：逐行读 `main.py:88-148`、`shared/data/add_utrs_to_gff.py:1-60`、`shared/data/annotation_utils.py:1-56`，与 `task.md` §3 五条必做项对照，未发现缺项或越界重构。
- 独立探针（master 自写，与 servant 的脚本无关）：`docs/handoff/gff-gz-annotation/assets/master_verify.py`、`master_verify_d.py`、`master_verify_e.py`。
- 关键端到端：把「已含 UTR 的 GFF」压成 gz（即真实 `GCF_049306965.2_GRCz12tu_genomic.gff.gz` 的形态）→ `_get_prepared_gtf` 返回**纯文本**副本并保留 UTR 特征；`input lines=21 blank=3 / output lines=25 blank=7`，**18 行非空行逐行相同**（差异仅为 A1 空行）。
- 回归哨兵：新脚本对明文 fixture 的输出与基线脚本输出 sha256 完全一致，明文路径无字节级回归。
- 测试：`tests.test_gff_gz` 4/4 OK；`tests.test_gui_common` 3/3 OK（`tests.test_unified_gui` 含 Tk 构建用例，本机非交互会话下未跑完，留给服务器全量）。

## 归属判定（既有失败 vs 本次引入）

- 用户上报的 `UnicodeDecodeError` → 既有缺陷（改动前 `add_utrs_to_gff.py:51` 文本读 gz），本次引入的改动已消除；证据：基线脚本对 gz 复现同一异常（`master_verify_d.py` 里 `UnicodeDecodeError: 'gbk' codec ... byte 0x8b`）。
- 「基因列表静默为空」→ 既有缺陷（`annotation_utils._load_gene_attributes` 的 `except` 吞异常），修 P0-2 后消除；证据：OLD gz=[] / NEW gz=['A','B']。
- A1 空行漂移 → 既有行为（`read_gff` 注释行保留 `\n`），非本次引入；且对含 UTR 的输入会放大（3→7 空行），但 18 行非空内容不变，下游 `shared/data/local_extract.py:41-47` 会跳过 `len(parts) < 9` 的行，功能无影响。

## 新发现

- `main.py:136-137` — P1：本次把父进程写文件固定为 UTF-8，但子进程 stdout 仍按子进程 locale 编码（Windows=cp936），非 ASCII 注释内容在 Windows 上会出现「GBK 字节 / UTF-8 读取」不一致（服务器 UTF-8 locale 无此问题）。最小修复：`subprocess.run(..., env={**os.environ, "PYTHONIOENCODING": "utf-8"})`。
- `main.py:107` — P3：gz 且基名含 `_with_utrs` 时会得到 `mini_with_utrs_with_utrs.gff3`（双后缀）。取舍正确（C4 优先），仅命名不美观；现实流程中不会触发（`_with_utrs.gff3` 是本工具产出的明文，不会被再压成 gz）。
- `shared/data/annotation_utils.py:76` — P3：`except Exception` 仍会把权限/损坏等错误吞成「没有基因」，建议至少保留日志（既有行为，未修）。
- `shared/data/local_extract.py:41` — P3：同为纯文本读取，目前依赖 C4 保证；若将来直接把原始 `.gz` 传进去会复现同类问题。
- `shared/data/annotation_utils.py:42` — P3（既有）：`gene_name -> Name -> gene` 回退链使 `load_gene_list(..., "gene")` 恒为空（`gene` 未进入 `attrs_list`）。
- `report.md` §待明确 1 的判定成立（master 采纳）：`mini.gff` 的 `Name=A` 先于 `gene=AAA` 命中，故明文基线本来就是 `['A','B']`；`task.md` 里 `["AAA","BBB"]` 的预期是 **master 的规格笔误**，fixture 与解析优先级均不改，servant 处理正确（并在测试里注明原因）。

## 下一步

- 通过（round 1 关闭）。剩余可选项：
  - U1（master，建议尽快）：在 ms01 上用 `/home/apool/songji/programfile/.venv/bin/python` 对真实 `GCF_049306965.2_GRCz12tu_genomic.gff.gz` 跑 GUI 同路径端到端（`load_gene_list` 非空 + 生成纯文本 `_with_utrs.gff3`）与全量 `run_tests.py`；需用户提供 `MS_PASS`。
  - U2（P1，可选 1 行改动）：`main.py:137` 补 `PYTHONIOENCODING=utf-8`，与本次 UTF-8 写入配对。
  - U3（P3，记录即可）：A1 空行、双后缀命名、`except` 吞异常、`local_extract` 纯文本读取。
- 若 U1 在服务器上暴露与平台相关的失败，按 `needs_rework` 重开并只列最小修复清单。