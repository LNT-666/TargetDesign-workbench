# 交付报告：gff-gz-annotation

- round: 1
- status: ready_for_review
- updated: 2026-09-15 15:50
- servant: 会话 B
- 基线快照（只读，未修改）：`backup/gff_gz_annotation_20260915_151757/`

## 改动清单

| 文件 | 行 | 改了什么 | 对应任务项 |
| --- | --- | --- | --- |
| `shared/data/annotation_utils.py` | 4 | 新增 `import gzip` | P0-1 |
| `shared/data/annotation_utils.py` | 22-40 | 新增 `GZIP_MAGIC`、`is_gzip_file()`、`open_annotation_text()` | P0-1 |
| `shared/data/annotation_utils.py` | 50 | `_load_gene_attributes` 改用 `open_annotation_text(gff_path)` | P0-2 / D4 |
| `shared/data/add_utrs_to_gff.py` | 14-20 | 头部加 `import os`、`sys.path.insert`、`from annotation_utils import open_annotation_text`（绝对导入，非相对导入） | P0-3 |
| `shared/data/add_utrs_to_gff.py` | 55 | `read_gff` 改用 `open_annotation_text(input_file)`（根因修复） | P0-3 |
| `main.py` | 14 | import 增加 `is_gzip_file, open_annotation_text` | P0-4a |
| `main.py` | 95 | `is_gz = is_gzip_file(raw_gtf)`，在 `try` 之外、全函数只判一次 | P0-4c |
| `main.py` | 97-105 | base 按 C5 循环剥离 `.gz/.gff/.gff3/.gtf`（大小写不敏感） | P0-4b |
| `main.py` | 107 | `_with_utrs` 提前返回加 `not is_gz` 排除 | C4/C6（见「待明确 2」） |
| `main.py` | 113 | 预检查改用 `open_annotation_text(raw_gtf)` | P0-4c |
| `main.py` | 127 | 「已含 UTR」提前返回加 `not is_gz` 排除（gz 一律走子进程分支产出纯文本副本） | P0-4d |
| `main.py` | 136-137 | 输出文件 `encoding='utf-8'`；子进程 `text=True, encoding='utf-8'` | P0-4e |
| `tests/test_gff_gz.py` | 1-94 | 新增 4 个用例（`test_` 位于 33/42/69/81 行） | P0-5 |

改动文件共 4 个（3 改 1 新增），未创建/删除/移动其它文件；`backup/`、`example/`、`external_tools/`、`native/`、`webapp/` 未触碰。

## 轻量自检结果

### 1) 语法检查

```powershell
python -m py_compile shared\data\add_utrs_to_gff.py shared\data\annotation_utils.py main.py tests\test_gff_gz.py
```

```text
py_compile exit=0
```

（首次执行时写 `shared\data\__pycache__\annotation_utils.cpython-314.pyc` 报过 `[WinError 5] 拒绝访问`，原样重跑即通过；见附带发现 A5。）

### 2) UTR 脚本 gz/明文输出对比

```powershell
python shared\data\add_utrs_to_gff.py docs\handoff\gff-gz-annotation\assets\mini.gff    > $env:TEMP\plain.out 2>&1; "plain exit=$LASTEXITCODE"
python shared\data\add_utrs_to_gff.py docs\handoff\gff-gz-annotation\assets\mini.gff.gz > $env:TEMP\gz.out    2>&1; "gz exit=$LASTEXITCODE"
fc.exe $env:TEMP\plain.out $env:TEMP\gz.out
```

```text
plain exit=0
gz exit=0
Comparing files C:\USERS\ASUS\APPDATA\LOCAL\TEMP\plain.out and C:\USERS\ASUS\APPDATA\LOCAL\TEMP\GZ.OUT
FC: no differences encountered
fc exit=0
```

### 3) P0-1 / P0-3 / C6 证据（`$env:TEMP\sv_evidence_a.py`）

```python
import hashlib, os, shutil, subprocess, sys

REPO = r"R:\songji\programfile"
sys.path.insert(0, os.path.join(REPO, "shared"))
from data.annotation_utils import is_gzip_file, open_annotation_text

ASSETS = os.path.join(REPO, "docs", "handoff", "gff-gz-annotation", "assets")
plain = os.path.join(ASSETS, "mini.gff")
gz = os.path.join(ASSETS, "mini.gff.gz")

print("== P0-1 helper evidence ==")
print("is_gzip_file(plain)  =", is_gzip_file(plain))
print("is_gzip_file(gz)     =", is_gzip_file(gz))
print("is_gzip_file(dir)    =", is_gzip_file(ASSETS))
print("is_gzip_file(missing)=", is_gzip_file(os.path.join(ASSETS, "no_such.gff")))
with open_annotation_text(plain) as fh:
    plain_text = fh.read()
with open_annotation_text(gz) as fh:
    gz_text = fh.read()
print("open_annotation_text text identical:", plain_text == gz_text, len(plain_text), len(gz_text))

def run(script, path):
    return subprocess.run([sys.executable, script, path], capture_output=True, cwd=REPO)

new_script = os.path.join(REPO, "shared", "data", "add_utrs_to_gff.py")
old_script = os.path.join(os.environ["TEMP"], "baseline_add_utrs_to_gff.py")
shutil.copyfile(os.path.join(REPO, "backup", "gff_gz_annotation_20260915_151757", "add_utrs_to_gff.py"), old_script)

print("\n== P0-3 / C6 script evidence (raw stdout bytes) ==")
for label, script in (("baseline", old_script), ("patched", new_script)):
    plain_run = run(script, plain)
    gz_run = run(script, gz)
    print(f"[{label}] plain rc={plain_run.returncode} sha256={hashlib.sha256(plain_run.stdout).hexdigest()} bytes={len(plain_run.stdout)}")
    print(f"[{label}] gz    rc={gz_run.returncode} sha256={hashlib.sha256(gz_run.stdout).hexdigest()} bytes={len(gz_run.stdout)}")
    print(f"[{label}] gz stdout == plain stdout: {gz_run.stdout == plain_run.stdout}")
    if gz_run.returncode != 0:
        print(f"[{label}] gz stderr:", gz_run.stderr.decode("utf-8", "replace").strip().splitlines()[-1])
```

```text
== P0-1 helper evidence ==
is_gzip_file(plain)  = False
is_gzip_file(gz)     = True
is_gzip_file(dir)    = False
is_gzip_file(missing)= False
open_annotation_text text identical: True 810 810

== P0-3 / C6 script evidence (raw stdout bytes) ==
[baseline] plain rc=0 sha256=d2202d0b97dc2ec6c32611e7e16dadb455f0f65a291ad0aa1e9335e735b10abf bytes=1162
[baseline] gz    rc=1 sha256=e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 bytes=0
[baseline] gz stdout == plain stdout: False
[baseline] gz stderr: UnicodeDecodeError: 'gbk' codec can't decode byte 0x8b in position 1: illegal multibyte sequence
[patched] plain rc=0 sha256=d2202d0b97dc2ec6c32611e7e16dadb455f0f65a291ad0aa1e9335e735b10abf bytes=1162
[patched] gz    rc=0 sha256=d2202d0b97dc2ec6c32611e7e16dadb455f0f65a291ad0aa1e9335e735b10abf bytes=1162
[patched] gz stdout == plain stdout: True
```

要点：明文输出与改动前**逐字节相同**（同 sha256，C6）；gz 输入改动前 rc=1（根因复现），改动后 rc=0 且与明文输出逐字节相同（P0-3）。

### 4) P0-4 `_get_prepared_gtf` 假 self 用例（`$env:TEMP\sv_evidence_b.py`）

```python
import gzip, hashlib, os, shutil, subprocess, sys, tempfile

REPO = r"R:\songji\programfile"
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "shared"))
import main

ASSETS = os.path.join(REPO, "docs", "handoff", "gff-gz-annotation", "assets")
mini_plain = os.path.join(ASSETS, "mini.gff")
mini_gz = os.path.join(ASSETS, "mini.gff.gz")

class FakeEntry:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

def make_app(output_dir):
    app = main.MainApp.__new__(main.MainApp)   # no Tk root
    app.entry_output = FakeEntry(output_dir)
    app._gtf_cache = {}
    app.logs = []
    app.log = app.logs.append
    return app

def sha(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()[:16]

root = tempfile.mkdtemp(prefix="gff_gz_check_")
print("check dir:", root)

d1 = os.path.join(root, "case1"); os.makedirs(d1)
app = make_app(d1)
p1 = app._get_prepared_gtf(mini_gz)
text1 = open(p1, "r", encoding="utf-8").read()
print("\n== case 1: gz input ==")
print("input   :", mini_gz)
print("returned:", p1)
print("not .gz:", not p1.endswith(".gz"), "| basename ends with mini_with_utrs.gff3:", os.path.basename(p1).endswith("mini_with_utrs.gff3"))
print("open(path,'r',encoding='utf-8') ok, lines =", len(text1.splitlines()), "| has five_prime_UTR:", "five_prime_UTR" in text1)
print("sha256[:16]:", sha(p1), "| logs:", app.logs)

d2 = os.path.join(root, "case2"); os.makedirs(d2)
app = make_app(d2)
p2 = app._get_prepared_gtf(mini_plain)
print("\n== case 2: plain input without UTR ==")
print("returned:", p2, "| cache:", app._gtf_cache.get(mini_plain))
print("sha256[:16]:", sha(p2), "| logs:", app.logs)
base_script = os.path.join(os.environ["TEMP"], "baseline_add_utrs_to_gff.py")
base_out = subprocess.run([sys.executable, base_script, mini_plain], capture_output=True, cwd=REPO).stdout
print("bytes == pre-change script stdout:", open(p2, "rb").read() == base_out, "| sha256[:16]:", hashlib.sha256(base_out).hexdigest()[:16])

d3 = os.path.join(root, "case3"); os.makedirs(d3)
utr_plain = os.path.join(d3, "mini_with_utrs.gff3")
shutil.copyfile(p1, utr_plain)
app = make_app(d3)
p3 = app._get_prepared_gtf(utr_plain)
print("\n== case 3a: plain input, basename contains _with_utrs ==")
print("returned == input:", p3 == utr_plain, "| logs:", app.logs)

utr_plain2 = os.path.join(d3, "utr_only.gff")
shutil.copyfile(p1, utr_plain2)
app = make_app(d3)
p3b = app._get_prepared_gtf(utr_plain2)
print("== case 3b: plain input that already contains UTR features ==")
print("returned == input:", p3b == utr_plain2, "| no copy created:", not os.path.exists(os.path.join(d3, "utr_only_with_utrs.gff3")), "| logs:", app.logs)

d4 = os.path.join(root, "case4"); os.makedirs(d4)
utr_gz = os.path.join(d4, "mini_with_utrs.gff3.gz")
with gzip.open(utr_gz, "wb") as fh:
    fh.write(open(p1, "rb").read())
app = make_app(d4)
p4 = app._get_prepared_gtf(utr_gz)
print("\n== case 4 (C4 edge, documented deviation): gz input whose base contains _with_utrs ==")
print("input   :", utr_gz)
print("returned:", os.path.basename(p4), "| plain text:", not p4.endswith(".gz"), "| has five_prime_UTR:", "five_prime_UTR" in open(p4, encoding="utf-8").read())
print("logs:", app.logs)
```

```text
check dir: C:\Users\ASUS\AppData\Local\Temp\gff_gz_check_sxl94cf4

== case 1: gz input ==
input   : R:\songji\programfile\docs\handoff\gff-gz-annotation\assets\mini.gff.gz
returned: C:\Users\ASUS\AppData\Local\Temp\gff_gz_check_sxl94cf4\case1\mini_with_utrs.gff3
not .gz: True | basename ends with mini_with_utrs.gff3: True
open(path,'r',encoding='utf-8') ok, lines = 20 | has five_prime_UTR: True
sha256[:16]: d2202d0b97dc2ec6 | logs: ['Adding UTR (file: R:\\songji\\programfile\\docs\\handoff\\gff-gz-annotation\\assets\\mini.gff.gz) ...', 'UTR added: C:\\Users\\ASUS\\AppData\\Local\\Temp\\gff_gz_check_sxl94cf4\\case1\\mini_with_utrs.gff3']

== case 2: plain input without UTR ==
returned: C:\Users\ASUS\AppData\Local\Temp\gff_gz_check_sxl94cf4\case2\mini_with_utrs.gff3 | cache: C:\Users\ASUS\AppData\Local\Temp\gff_gz_check_sxl94cf4\case2\mini_with_utrs.gff3
sha256[:16]: d2202d0b97dc2ec6 | logs: ['Adding UTR (file: R:\\songji\\programfile\\docs\\handoff\\gff-gz-annotation\\assets\\mini.gff) ...', 'UTR added: C:\\Users\\ASUS\\AppData\\Local\\Temp\\gff_gz_check_sxl94cf4\\case2\\mini_with_utrs.gff3']
bytes == pre-change script stdout: True | sha256[:16]: d2202d0b97dc2ec6

== case 3a: plain input, basename contains _with_utrs ==
returned == input: True | logs: []
== case 3b: plain input that already contains UTR features ==
returned == input: True | no copy created: True | logs: ['Annotation file already contains UTR, no need to add']

== case 4 (C4 edge, documented deviation): gz input whose base contains _with_utrs ==
input   : C:\Users\ASUS\AppData\Local\Temp\gff_gz_check_sxl94cf4\case4\mini_with_utrs.gff3.gz
returned: mini_with_utrs_with_utrs.gff3 | plain text: True | has five_prime_UTR: True
logs: ['Adding UTR (file: C:\\Users\\ASUS\\AppData\\Local\\Temp\\gff_gz_check_sxl94cf4\\case4\\mini_with_utrs.gff3.gz) ...', 'UTR added: C:\\Users\\ASUS\\AppData\\Local\\Temp\\gff_gz_check_sxl94cf4\\case4\\mini_with_utrs_with_utrs.gff3']
```

### 5) 回归测试

```powershell
python -m unittest tests.test_gff_gz -v
```

```text
test_load_gene_list_from_gz_matches_plain (tests.test_gff_gz.GffGzipPreparedTests.test_load_gene_list_from_gz_matches_plain) ... ok
test_prepared_gtf_from_gz_is_plain_text (tests.test_gff_gz.GffGzipPreparedTests.test_prepared_gtf_from_gz_is_plain_text) ... ok
test_read_gff_gz_matches_plain (tests.test_gff_gz.GffGzipScriptTests.test_read_gff_gz_matches_plain) ... ok
test_utr_script_stdout_matches_plain (tests.test_gff_gz.GffGzipScriptTests.test_utr_script_stdout_matches_plain) ... ok

----------------------------------------------------------------------
Ran 4 tests in 43.937s

OK
unittest exit=0
```

## 未做项

- 服务器 ms01 跑批、真实 `GCF_049306965.2_GRCz12tu_genomic.gff.gz` 端到端复现、全量测试套件 — 按 §4/§6 属 master 核验范围。
- `tests/test_gff_gz.py` 之外未新增测试；未动下载流程、UTR 坐标算法、GFF 字段/列契约、FASTA.gz 等其它 gz 场景（明确不在范围内）。

## 附带发现（不在本次范围，未修）

- `shared/data/add_utrs_to_gff.py:58`（原 `:54`）`read_gff` 对注释行 `lines.append(line)` 保留了行尾 `\n`，随后 `'\n'.join(lines)` 会多出空行（A1）；未修，符合 §4。
- `main.py:137` 子进程 stdout 直接复用文件句柄，子进程自身的 `sys.stdout` 编码由子进程 locale 决定（本机 Windows=cp936，服务器=UTF-8）；非 ASCII 注释内容在 Windows 上存在「GBK 字节写入 / UTF-8 读出」的乱码风险。建议加 `env={**os.environ, "PYTHONIOENCODING": "utf-8"}`；本次按 P0-4e 指定的最小改动执行，未额外添加。
- `shared/data/local_extract.py:41` 同为 `open(annotation_file, "r")` 文本读，仅靠 C4（上游必须是纯文本）保证；若将来把原始 `.gz` 直接传进去会复现同类问题，可参照 D4 改用 `open_annotation_text`。
- `shared/data/annotation_utils.py:76`（`_load_gene_attributes` 的 `except Exception`）把任何读取异常吞成「没有基因」：改动前 gz 输入静默返回 `[]`（已用 backup 模块复现，见「待明确 1」证据），这是原 bug 表现为「列表为空」而非报错的原因。读取路径已修，但该兜底仍会吞掉其它错误（权限、文件损坏），建议至少保留日志。
- 环境：首次 `python -m py_compile` 因向共享盘 `shared\data\__pycache__\annotation_utils.cpython-314.pyc` 写入被拒（`[WinError 5] 拒绝访问`）失败一次，原样重跑通过；疑为并行进程短暂占用，与代码无关。
- `shared/data/annotation_utils.py:42` 的 `gene_name` 回退链是 `gene_name -> Name -> gene`，而 `gene` 这个 key 并不进入 `attrs_list`（只存 `gene_name/gene_id/ID/locus_tag`）；即 `load_gene_list(..., "gene")` 恒为 `[]`。未改（字段契约不在范围内），仅记录。

## 待明确

1. P0-5 用例 4（以及 §3 P0-2 的证据示例）写的是 `load_gene_list(<mini.gff.gz>, "gene_name", None, {}, None) == ["AAA", "BBB"]`，但按既有解析契约该 fixture 实际得到 `["A", "B"]`（`Name=A` 先于 `gene=AAA` 命中）。用改动前的模块跑明文同样是 `["A", "B"]`，改动后的模块跑 gz 也是 `["A", "B"]`（`OLD plain: ['A','B'] / OLD gz: [] / NEW plain: ['A','B'] / NEW gz: ['A','B']`，见 `$env:TEMP\verify_genelist.py`）。我的用例因此断言「gz 与明文结果一致」并显式写出 `["A","B"]`，并在测试注释里标注原因。若 master 要求字面 `["AAA","BBB"]`，需调整 fixture（如 `Name=AAA`）或改解析优先级（超出本次范围）。
2. 边界取舍：gz 且基名含 `_with_utrs`（如 `mini_with_utrs.gff3.gz`）时，我按 C4/C6「只有纯文本才直接返回」优先于「基名含 `_with_utrs` 直接返回」，走子进程分支产出纯文本副本；按 C5 字面命名得到 `mini_with_utrs_with_utrs.gff3`（双后缀，见用例 4）。请确认该取舍与命名是否接受，或给出期望规则。
3. C7 的「输入已含 UTR 时原样输出」会把 A1 的空行行为带进 gz 副本；本次未改，确认无需处理。

## round 2（servant 跟进：review.md 的 U2，2026-09-16）

- 触发：用户指示「都进行吧」，执行 `review.md`「下一步」中的 U2（P1）：给 UTR 子进程固定 `PYTHONIOENCODING=utf-8`。本轮没有新 `task.md`。
- 改动与行号：

| 文件 | 行 | 改了什么 | 任务项 |
| --- | --- | --- | --- |
| `main.py` | 144-147 | `subprocess.run(cmd, stdout=f, stderr=PIPE, text=True, encoding='utf-8', env={**os.environ, "PYTHONIOENCODING": "utf-8"})` | U2 |
| `tests/test_gff_gz.py` | 6, 11, 124-157 | 新增 `test_utr_product_keeps_non_ascii_text`：用例内清掉 `PYTHONUTF8`/`PYTHONIOENCODING`，复现 GUI 默认环境 | U2 |

- 反向对照（同一台机器，直接跑 `shared/data/add_utrs_to_gff.py`，输入含 `Name=测试基因A`）：

```text
OLD (子进程无编码 env)          | utf8: False | gbk: True  | rc 0
NEW (PYTHONIOENCODING=utf-8)    | utf8: True  | gbk: False | rc 0
```

  Windows 上子进程默认 cp936：产物会混入 GBK 字节，父进程按 UTF-8 读回即乱码/报错；补 env 后产物是合法 UTF-8（`with open(prepared, encoding="utf-8")` 可正常读回同一串中文）。
- 测试：`python -m unittest tests.test_gff_gz -v` → `Ran 6 tests in 56.259s OK`（含本轮新增的 2 个用例：编码 + 产物新鲜度）。
- 未做：U1（ms01 真实 `GCF_049306965.2_GRCz12tu_genomic.gff.gz` 端到端 + 全量 `run_tests.py`）需要用户提供 `MS_PASS`，本会话未执行；U3 仍为记录项（A1 空行、双后缀命名、`except` 吞异常、`local_extract` 纯文本读取）。
- 附带说明：`main.py` 同一轮还改了 `_get_prepared_gtf` 的产物新鲜度（属 `fasta-gz-prep` 的 U4），两条改动都记在该任务 `report.md` 的 round 3 小节里。
