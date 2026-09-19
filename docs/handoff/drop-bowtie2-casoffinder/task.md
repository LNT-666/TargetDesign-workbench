# 任务：下线 bowtie2 与 casoffinder 两个脱靶搜索引擎

- task-slug: `drop-bowtie2-casoffinder`
- round: 1
- master: 会话 A（master）
- servant: 会话 B（servant）
- repo: `R:\songji\programfile`（镜像服务器 `/home/apool/songji/programfile`）
- 权威运行环境：ms01 服务器 `/home/apool/songji/programfile/.venv/bin/python`（Python 3.12.3）
- 本地环境：`python` = Python 3.14.7（已装 pyfaidx 0.9.0.4 与 tkinter；无 numpy/biopython）
- 基线快照（master 已建，servant 直接引用，不要重建/修改）：`backup/drop_bowtie2_casoffinder_20260916_095125/`（17 个受影响文件的改动前副本，保持相对路径）

## 0. 目标与边界

需求原文（用户）："考虑删除bowtie2和casoffinder"。

master 已调研、给出范围，用户于 2026-09-16 回复"好"确认。执行范围如下（如认为解读有误，写进 `report.md` 的「待明确」，不要自行扩大范围）：

要做到：

1. 删除 `bowtie2` 与 `casoffinder` 两个**脱靶搜索引擎**的实现、注册、界面/命令行选项、基准工具、测试与文档表述；
2. 删除后 `ENGINE_CHOICES == ["exact", "indexed", "blast", "gggenome", "auto"]`，`BACKENDS` 只剩 exact / blast / gggenome / indexed；
3. `auto` 的候选顺序 = "把现有列表里的这两个名字删掉"（见 §1 C3 的权威结果表）；
4. **完整保留** crispAI 打分链路对 `cas-offinder` 二进制的依赖，一个字节都不许改（见 §4）。

不在范围内（不要做）：

- 不新增或替换任何搜索引擎，不引入新依赖；
- 不动 `exact` / `indexed` / `blast` / `gggenome` 的实现与能力声明；
- 不改 `auto` 的解析/回落机制本身，只改候选列表内容；
- 不动 crispAI 相关的一切（§4 有逐条清单）；
- 不重构 `shared/search/offtarget_backend.py` 的其它部分，不调整函数顺序，不重排 import。

为什么这是安全的（背景）：本机与 ms01 上都没有 `bowtie2` / `bowtie2-build`，PATH 上也没有 `cas-offinder`，因此这两个 backend 的 `available()` 一直返回 False，`auto` 每次都会跳过它们 —— 这两个引擎实际上从未可用（证据见 §2）。

## 1. 规则 / 契约（唯一权威版本，servant 不需要也不允许重新调研）

```text
C1  删除两个 backend 类。shared/search/offtarget_backend.py 里 Bowtie2Backend（488-663）与
    CasOFFinderBackend（664-777）是连续紧邻的，可整段删除 488-777（778 起是 GGGenomeBackend）。
    该区间内没有任何模块级函数，只有这两个类的成员；删除后文件其余部分行号整体上移，属预期。
C2  BACKENDS（1447-1454）删掉 "bowtie2" 与 "casoffinder" 两行，保留 exact / blast / gggenome / indexed
    四项且不改变它们的先后顺序。
C3  auto_engine_candidates（1388-1409）的每个 return 列表里删掉 "bowtie2" 与 "casoffinder"，
    其余元素的相对顺序必须保持不变。删除后必须精确等于：
      --blastdb 非空                        -> ["blast"]
      --index-path 非空                     -> ["indexed"]
      genome_size > MAX_EXACT_GENOME_BYTES   -> ["blast", "indexed"]              （bulge 开关都一样）
      native_available 为真                  -> ["indexed", "blast", "exact"]      （bulge 开关都一样）
      其余情况、bulge 开启                   -> ["blast", "exact", "indexed"]
      其余情况、bulge 关闭                   -> ["blast", "indexed", "exact"]
    允许把因删名而变得完全相同、只差 bulge 的分支合并（原 1401/1402、1405/1406），也允许保留原分支
    结构；两种写法都必须产出上面这张表。
C4  apply_engine_defaults（1343-1373）删掉 elif key == "casoffinder" 分支（1359-1360）。
    "auto" 分支、"indexed" 分支、以及 max_bulge_explicit 的早返回必须原样保留。
C5  default_engine_threads（180-189）不再读 BOWTIE2_NUM_THREADS，只保留 SEARCH_NUM_THREADS；
    无环境变量时的返回值 max(1, min(os.cpu_count() or 2, 32)) 必须不变。
C6  shared/design/library_preflight.py:23-24 的 ENGINE_CHOICES 改为
    ["exact", "indexed", "blast", "gggenome", "auto"]。LEGACY_ENGINE_CHOICES（:27）保持原样
    （它本来就只剩 exact/indexed/blast/auto，天然是新列表的子集）。
C7  三处硬编码 --engine choices 的脚本，只从字面量列表里删掉 'bowtie2' 与 'casoffinder' 两项；
    不要改成 import ENGINE_CHOICES（这些是独立入口脚本，加 import 会引入新的 sys.path 依赖）：
      basic/blast.py:137-139
      Target_xbp_Target/analyze_complex_scores.py:156-158
      Target_xbp_Y_zbp_Target/blast_combined.py:161-163
C8  webapp/index.html:59-67 的 <select id="engine"> 里删掉 bowtie2 / casoffinder 两个 <option> 行。
    注意：真正被服务的是 webapp/app.py:116-119 动态生成的页面（选项来自 ENGINE_CHOICES），所以
    app.py 不需要改；index.html 只是静态副本，改它是为了避免页面漂移。
C9  已下线的引擎名必须明确报错，不得静默换引擎：validate_engine（library_preflight.py:36-42）与
    get_backend（offtarget_backend.py:1457-1462）在收到 "bowtie2" / "casoffinder" 时，抛出的
    ValueError 文本必须含 "removed" 或 "已下线" 字样，并列出当前可用引擎；其它未知名字仍走原有
    报错路径。不要为已下线的名字自动回落到 auto。
C10 文档：只删改"把 bowtie2 / casoffinder 当作脱靶搜索引擎来介绍"的段落；凡描述 crispAI 依赖
    cas-offinder 的段落一律保留（§4）。
C11 除本任务点名的文件外，不得改动任何文件；不得顺手修复其它既有问题。
## 2. 现状证据（master 已核实，可直接引用）

- 类边界：`shared/search/offtarget_backend.py:488` `class Bowtie2Backend`、`:664` `class CasOFFinderBackend`、`:778` `class GGGenomeBackend` —— 前两个类在文件里紧邻，中间没有模块级函数。
- 可用性判定：`:499-502` Bowtie2 的 `available()` 检查 `bowtie2` 与 `bowtie2-build`；`:675` Cas-OFFinder 的 `available()` 检查 `shutil.which("cas-offinder")`。
- 服务器实测（master，2026-09-16，`command -v`）：

```text
bowtie2       -> MISSING
bowtie2-build -> MISSING
cas-offinder  -> MISSING
micromamba    -> MISSING
makeblastdb   -> /opt/bin/makeblastdb
blastn        -> /opt/bin/blastn
```

  本机 Windows 同样全部 MISSING。结论：两个后端长期 `available() == False`，`auto` 每次都会跳过它们。
- 但 crispAI 仍在用 cas-offinder：`external_tools/crispAI-main/crispAI_score/casoffinder/cas-offinder` 是指向 `/home/users/songji/.cache/casoffinder-env/bin/cas-offinder` 的符号链接（2026-09-07 建立）；`shared/scoring/crispai_runtime.py:59-68` 与 `:127-133` 在找不到它时会把 "cas-offinder binary not found" 记为 **error**。服务器当前 `preflight()` 返回 `ERRORS: []`。
- 引用清单（master 的 grep 结果，已排除 `backup/` 与 `.venv/`）：
  - `bowtie2`：`basic/blast.py`、`docs/GUI.md`、`docs/NATIVE_INDEXED_ENGINE_DESIGN.md`、`docs/OFFTARGET_ENGINES.md`、`docs/UPGRADE_REPORT.md`、`README.md`、`shared/design/library_pipeline.py`、`shared/design/library_preflight.py`、`shared/search/offtarget_backend.py`、`Target_xbp_Target/analyze_complex_scores.py`、`Target_xbp_Y_zbp_Target/blast_combined.py`、`tests/test_library_preflight.py`、`tests/test_offtarget_backend.py`、`tests/test_offtarget_hardening.py`、`tests/test_webapp.py`、`tools/benchmark_all_engines.py`、`webapp/index.html`
  - `casoffinder` / `cas-offinder`：上面这些 + `basic/analyze_scores.py`、`docs/CRISPAI.md`、`docs/SCORING_GUIDE.md`、`requirements.txt`、`requirements-linux.txt`、`requirements-windows.txt`、`shared/scoring/crispai_runtime.py`、`tools/build_crispai_env.sh`、`tools/score_crispai.py`、`scy-test/*/crispai.log.tsv`
- `shared/design/library_pipeline.py:249` 的 help 文本 `"blastn/bowtie2 threads (default: auto up to 32)"` 只是措辞问题（P2-1）。
- 附带发现（只记录、不修）：`main.py:575` 的工作区映射写成 `"combo_library_engine": "engine"`，而实际控件名是 `combo_library_search`（`main.py:734`），疑为长期失效的映射项；`main.py` 用的是 `LEGACY_ENGINE_CHOICES`，与本任务无交集。master 未深究，servant 不要修。
- 环境提醒：本仓库没有 git 历史，基线一律用 `backup/` 快照；读写含中文的文件必须显式 UTF-8（`PYTHONUTF8=1`、`PYTHONIOENCODING=utf-8`、`Get-Content -Encoding UTF8`）。

## 3. 必做改动

- [ ] P0-1 删除两个 backend 类
  - 位置：`shared/search/offtarget_backend.py:488-777`
  - 期望行为：C1。整段删除后 `GGGenomeBackend` 紧随 `BlastBackend` 之后。
  - 证据要求：`python -m py_compile shared/search/offtarget_backend.py` 的输出；`grep -n "Bowtie2\|CasOFFinder\|_parse_sam\|_run_casoffinder_chunk" shared/search/offtarget_backend.py` 返回空。

- [ ] P0-2 收敛注册表、auto 候选与引擎默认值
  - 位置：`shared/search/offtarget_backend.py:1447-1454`（C2）、`:1388-1409`（C3）、`:1343-1373`（C4）、`:180-189`（C5）
  - 期望行为：C2-C5，特别是 C3 的结果表必须逐条对齐。
  - 证据要求：贴一段 `python -c`（或 `python - <<PY`）的输出，打印 `sorted(BACKENDS)` 与八种组合下的 `auto_engine_candidates(...)`，覆盖 C3 表里的每一行；再打印 `default_engine_threads()` 在 `SEARCH_NUM_THREADS` 未设时的返回值。

- [ ] P0-3 收敛引擎清单
  - 位置：`shared/design/library_preflight.py:23-24`
  - 期望行为：C6。
  - 证据要求：`python -c "import design.library_preflight as m; print(m.ENGINE_CHOICES)"` 与 `print(m.LEGACY_ENGINE_CHOICES)` 的输出。
  - 不需改动（但要在 report 里确认已覆盖）：`unified_gui.py:385`、`designer_workbench.py:26,589`、`webapp/app.py:116-119`、`shared/design/library_pipeline.py:228` 都从 `ENGINE_CHOICES` 取值，会自动跟随；`main.py:18,735` 用的是 `LEGACY_ENGINE_CHOICES`。

- [ ] P0-4 收敛界面与命令行选项
  - 位置：`webapp/index.html:59-67`、`basic/blast.py:137-139`、`Target_xbp_Target/analyze_complex_scores.py:156-158`、`Target_xbp_Y_zbp_Target/blast_combined.py:161-163`
  - 期望行为：C7、C8。
  - 证据要求：三个脚本各跑一次 `--help`，贴出 `--engine` 那一行的原文。

- [ ] P0-5 更新测试
  - 位置与期望行为：
    - `tests/test_offtarget_backend.py:19` — import 行删掉 `Bowtie2Backend, CasOFFinderBackend`。
    - `tests/test_offtarget_backend.py:165-175` — 保留 `matrix["blast"]["indels"] == "basic"`；删掉 `:169`（bowtie2 断言）与 `:170-175`（依赖 `CasOFFinderBackend.available` 的 `SearchParameterError` 断言）。剩余引擎中已无 `indels == "none"`（exact/indexed 是 `"dna_rna"`，blast/gggenome 是 `"basic"`），该断言无法平移，直接删除即可，并在 report 的「附带发现」记一句。
    - `tests/test_offtarget_backend.py:221-232` — 每个期望列表里删掉 `"bowtie2"` 与 `"casoffinder"`，其余顺序不变。
    - `tests/test_offtarget_backend.py:420` — `(BlastBackend(), Bowtie2Backend(), CasOFFinderBackend())` → `(BlastBackend(),)`。
    - `tests/test_offtarget_backend.py:663-711` — 删除整个 `Bowtie2ThreadTests`；`tests/test_offtarget_backend.py:713-727` — 删除整个 `CasOFFinderTests`。
    - `tests/test_offtarget_hardening.py:598` — 元组改为 `("exact", "blast", "indexed")`；`:629`、`:632`、`:638`、`:641`、`:652` — 期望链逐个删掉这两个名字（不要改变剩余顺序）。
    - `tests/test_library_preflight.py:25` — 该断言右侧的字面量列表改为 `["exact", "indexed", "blast", "gggenome", "auto"]`。
    - `tests/test_webapp.py:185-186` — 元组里删掉这两个名字，保留 `("exact", "indexed", "blast", "gggenome", "auto")`。
  - 证据要求：`python -m unittest tests.test_offtarget_backend tests.test_offtarget_hardening tests.test_library_preflight tests.test_webapp -v` 的完整输出（含 `OK` 与用例数）。
  - 另外先跑一次 `grep -rn "_parse_sam\|Bowtie2Backend\|CasOFFinderBackend" tests/` 确认没有遗漏引用，并把结果贴进 report。

- [ ] P0-6 更新文档
  - 位置：`README.md`、`docs/OFFTARGET_ENGINES.md`、`docs/GUI.md`（P0）；`docs/NATIVE_INDEXED_ENGINE_DESIGN.md`（P1）；`docs/UPGRADE_REPORT.md`（P1，按 §5 决策项处理）。
  - 期望行为：C10；引擎清单、能力表、`auto` 优先级说明同步为四项；crispAI 段落原样保留。
  - 证据要求：`grep -rn -i "bowtie2" README.md docs/` 的结果，并对每一处说明是"已删除"还是"有意保留"。

- [ ] P1-1 已下线引擎名的报错文本
  - 位置：`shared/design/library_preflight.py:36-42`、`shared/search/offtarget_backend.py:1457-1462`
  - 期望行为：C9。
  - 证据要求：分别调用 `m.validate_engine("bowtie2")` 与 `get_backend("casoffinder")`，贴出捕获到的 ValueError 文本原文。

- [ ] P1-2 基准工具收敛
  - 位置：`tools/benchmark_all_engines.py:280-306`（`benchmark_bowtie2` 整个函数）、`:336-337`（`--engines` 默认值改为 `"exact,indexed,native-indexed,blast"`）、`:347`（删 `BOWTIE2_NUM_THREADS` 的 setdefault）、`:375-379`（bowtie2 分支）、`:380-384`（casoffinder 分支）。
  - 期望行为：`--engines` 里出现这两个名字时，按既有未知引擎路径处理；`benchmark_simple` 仍被 `:355-359` 的 exact 分支使用，**不要删**。
  - 证据要求：`python -m py_compile tools/benchmark_all_engines.py`；`grep -n "bowtie2\|casoffinder" tools/benchmark_all_engines.py` 返回空。

- [ ] P2-1 `shared/design/library_pipeline.py:249` 的 help 文本改为 `"blastn/native threads (default: auto up to 32)"`（或等义措辞）。
## 4. 不要做的事

crispAI 链路必须一个字节都不改（这是本次范围的关键取舍）：

- 不要改 `shared/scoring/**`，尤其 `shared/scoring/crispai_runtime.py`。
- 不要改 `tools/build_crispai_env.sh`、`tools/score_crispai.py`、`requirements.txt`、`requirements-linux.txt`、`requirements-windows.txt`。
- 不要改 `external_tools/**`；不要碰 `external_tools/crispAI-main/crispAI_score/casoffinder/` 下的任何东西（含那个 `cas-offinder` 符号链接）。
- 不要删除或卸载 `~/.cache/casoffinder-env/`。
- 不要改 `basic/analyze_scores.py:161`、`docs/CRISPAI.md`、`docs/SCORING_GUIDE.md`、`tools/score_crispai.py:9,48` —— 那里的 "Cas-OFFinder" 指的是 crispAI 打分依赖，不是脱靶搜索引擎。
- 不要改 `scy-test/*/crispai.log.tsv`（历史日志）。

其它：

- 不要动 `backup/**`，不要动 `docs/handoff/**`（含本目录）。
- 不要改 `LEGACY_ENGINE_CHOICES`（`shared/design/library_preflight.py:27`）。
- 不要改 `webapp/app.py`（它从 `ENGINE_CHOICES` 生成选项，会自动跟随）。
- 不要把三处 CLI 脚本的 `choices` 改成 `import ENGINE_CHOICES`。
- 不要动 `exact` / `indexed` / `blast` / `gggenome` 的实现、能力声明与可用性判定。
- 不要顺手修 §2 里的 `main.py:575`；不要重构、不要调整无关代码的格式或顺序。

## 5. 决策项（未确认则按推荐执行）

- 用户遇到已下线引擎名时的行为 → 推荐 C9「明确报错并列出可用引擎」，不做静默回落。理由：静默换引擎会让用户在两份结果之间失去可追溯性；而这两个引擎本来从未可用，报错不会打断任何真实工作流。
- `docs/UPGRADE_REPORT.md` → 推荐：历史报告正文不改，只在文件开头加一行「注：bowtie2 与 casoffinder 两个脱靶搜索引擎已于 2026-09 下线，下文相关描述仅作历史记录」。理由：该文件是历史证据，改正文会破坏可追溯性。
- `docs/NATIVE_INDEXED_ENGINE_DESIGN.md` → 推荐：按 C10 正常改写（设计文档不是历史记录）。
- `tools/benchmark_all_engines.py` 里的 bowtie2 基准 → 推荐整体删除函数与分支，不保留"仅供 benchmark"的残留实现。理由：它依赖外部二进制，本机与服务器都不存在，无法执行。

## 6. 轻量自检（servant 的检验上限，不要跑全量套件）

权威环境（ms01）：

```bash
cd /home/apool/songji/programfile
/home/apool/songji/programfile/.venv/bin/python -m py_compile \
  shared/search/offtarget_backend.py shared/design/library_preflight.py \
  shared/design/library_pipeline.py tools/benchmark_all_engines.py \
  basic/blast.py Target_xbp_Target/analyze_complex_scores.py \
  Target_xbp_Y_zbp_Target/blast_combined.py \
  tests/test_offtarget_backend.py tests/test_offtarget_hardening.py \
  tests/test_library_preflight.py tests/test_webapp.py
/home/apool/songji/programfile/.venv/bin/python -m unittest \
  tests.test_offtarget_backend tests.test_offtarget_hardening \
  tests.test_library_preflight tests.test_webapp -v
grep -rn -i "bowtie2" --include=*.py --include=*.html . \
  | grep -v -e "/backup/" -e "/.venv/" -e "/docs/" -e "/.json"
```

第三条命令预期无输出（文档与 `state.json` 除外）。

证明 §4 守住了（必做）：

```bash
cd /home/apool/songji/programfile
cat > /tmp/ck_crispai.py <<'PY'
import sys
sys.path.insert(0, "/home/apool/songji/programfile/shared")
from scoring.crispai_runtime import preflight
e, w = preflight()
print("ERRORS:", e)
print("WARNINGS:", w)
PY
/home/apool/songji/programfile/.venv/bin/python /tmp/ck_crispai.py
```

预期 `ERRORS: []`，与改前一致（warning 里可能仍有 `ucsc_chroms` 一条）。

若确实连不上服务器，就用本机 `python` 跑同样两条命令（`py_compile` 与 `unittest`），并在 report 里写明跑在哪台机器上、解释器版本。

## 7. 交付要求

- 改前快照：master 已建 `backup/drop_bowtie2_casoffinder_20260916_095125/`（17 个文件，保持相对路径）。直接引用，不要重建、不要修改。
- 完成后：把 `state.json` 置 `ready_for_review`（并更新 `updated`），写 `report.md`。
- `report.md` 必填：改动文件+行号表格、命令原文与输出原文、未做项及原因、附带发现（只记录不修）、待明确项。
- 不要自己裁定"通过"；核验归 master。
---

## round 1 补充（master 澄清，2026-09-16 12:10）

servant 在 `report.md` 的「待明确」里指出 C9 与 §6 第三条 grep 自相矛盾 —— 判断正确，是 master 的规格缺陷。以下以本节为准。

A1 C9 优先：保留 `REMOVED_ENGINES = ("bowtie2", "casoffinder")` 字面量。§6 第三条 grep 改为"除这两处有意保留的退役报错字面量外不得有其它命中"：

```bash
grep -rn -i "bowtie2" --include=*.py --include=*.html --include=*.js . \
  | grep -v -e "/backup/" -e "/.venv/" -e "/.codex_tmp/" -e "/docs/"
```

预期**恰好 2 行**：`./shared/design/library_preflight.py:26` 与 `./shared/search/offtarget_backend.py:1159`。report 里请贴出实际行数并说明。

A2 对 `casoffinder` / `cas-offinder` 也做同一审计；预期命中全部落在 crispAI 链路（`external_tools/crispAI-main/...`、`shared/scoring/crispai_runtime.py`、`basic/analyze_scores.py`、`tools/score_crispai.py`）加上同样那 2 处 `REMOVED_ENGINES`，搜索引擎侧为零。

A3 新增 P3-1（**推荐不修，只记录**）：`shared/design/library_preflight.py:81` 的 `validate_engine()` 在 try 之外，因此传已下线引擎名时会抛 ValueError，而不是像改动前那样把 "缺少 Bowtie2…" 放进 errors 返回。调用点 `webapp/app.py:508-516` 有 `except ValueError`（优雅），`unified_gui.py:679-691` 没有 try。这是既有契约（`tests/test_library_preflight.py:85-87` 本就断言无效引擎名要抛），本轮不改，写进 report 的「附带发现」即可。

A4 master 已在 ms01 代跑过一轮，结果仅供对照（**不构成 servant 的交付证据**）：`py_compile` 0；`Ran 91 tests in 6.834s / OK`；`bowtie2` 审计恰 2 行；八组 `auto_engine_candidates` 与 C3 表逐条一致；crispAI `preflight()` → `ERRORS: []`。