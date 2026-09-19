# 核验报告：drop-bowtie2-casoffinder

- round: 1（两遍核验：第一遍为 servant 中止点的部分核验，第二遍为终核）
- verdict: **pass**
- updated: 2026-09-16 13:05
- 依据：`report.md`（round 1 终版，497 行）+ 基线快照 `backup/drop_bowtie2_casoffinder_20260916_095125/`（17 文件）
- 权威环境：ms01 `/home/apool/songji/programfile/.venv/bin/python`（3.12.3），`PATH` 含 `/opt/bin`
- 最终验收：P0-1 ~ P0-6、P1-1、P1-2、P2-1 全部通过；P3 三项记录不修（已在 `report.md` §4 与 `state.json.open_followups` 留痕）

---

## 第一遍核验（servant 中止点，2026-09-16 12:43；当时 verdict = needs_rework）

> 该遍只覆盖了代码与测试（P0-1 ~ P0-5、P1-1、P1-2、P2-1），当时 P0-6 文档与 ms01 权威自检尚未完成。以下内容原样保留作为追溯证据。
## 已完成部分：逐条核验（全部通过）

| 任务项 | 结论 | 证据 |
| --- | --- | --- |
| P0-1 删除两个 backend 类 | 通过 | 基线 1632 行 → 现 1341 行；类边界现为 ExactBackend 333 / BlastBackend 367 / GGGenomeBackend 487 / IndexedBackend 723。difflib 报的删除区间起点含 `return out` 是对齐假象，已单独确认 `BlastBackend.search` 的 `return out` 完好（现 484 行）、`GGGenomeBackend` 紧随其后 |
| P0-2 / C2 BACKENDS | 通过 | ms01 探针：`BACKENDS: ['blast', 'exact', 'gggenome', 'indexed']`；`capability_keys: ['blast', 'exact', 'gggenome', 'indexed']` |
| P0-2 / C3 auto 候选 | 通过 | ms01 探针八种组合逐条比对 C3 结果表，全部一致；另 `blastdb -> ['blast']`、`indexpath -> ['indexed']`。因删名而重复的 bulge 分支已按 C3 允许的方式合并 |
| P0-2 / C4 casoffinder 默认值分支 | 通过 | 基线 1359-1360 两行删除，docstring 里 "Cas-OFFinder is mismatch-only." 半句同步删除；`auto` / `indexed` 分支与 `max_bulge_explicit` 早返回保留 |
| P0-2 / C5 threads | 通过 | 函数体只读 `SEARCH_NUM_THREADS`；ms01 `threads(no env) : 32`，未设环境变量时回落值不变 |
| P0-3 / C6 ENGINE_CHOICES | 通过 | `['exact', 'indexed', 'blast', 'gggenome', 'auto']`；`LEGACY_ENGINE_CHOICES` 仍为 `['exact', 'indexed', 'blast', 'auto']` |
| P0-4 / C7 三处 CLI | 通过 | `basic/blast.py`、`Target_xbp_Target/analyze_complex_scores.py`、`Target_xbp_Y_zbp_Target/blast_combined.py` 各只删两个名字，未引入 import |
| P0-4 / C8 index.html | 通过 | 删两个 `<option>`；`webapp/app.py` 未改动（其选项由 `ENGINE_CHOICES` 生成） |
| P0-5 测试更新 | 通过 | **ms01：`Ran 91 tests in 6.834s` → `OK`**（0 失败、0 跳过） |
| P1-1 / C9 退役引擎报错 | 通过 | `get_backend('casoffinder')` → `ValueError: Off-target engine casoffinder was removed; choose from blast, exact, gggenome, indexed`；`validate_engine('bowtie2')` → `... was removed; choose from exact, indexed, blast, gggenome, auto`；`validate_engine('Indexed')` → `'indexed'`；`get_backend('typod')` 仍走原 "Unknown off-target engine" 路径 |
| P1-2 benchmark 收敛 | 通过 | 426 → 374 行；`benchmark_bowtie2` 与 bowtie2/casoffinder 两个分支删除；`benchmark_simple` 保留（仍服务 exact） |
| P2-1 措辞 | 通过 | `shared/design/library_pipeline.py:249` → `"blastn/native threads (default: auto up to 32)"` |

## master 独立验证

- **基线比对**：脚本按 17 个文件逐字比对基线快照 → CHANGED 12 / UNCHANGED 5，未变动的 5 个全是文档（`README.md`、`docs/OFFTARGET_ENGINES.md`、`docs/GUI.md`、`docs/NATIVE_INDEXED_ENGINE_DESIGN.md`、`docs/UPGRADE_REPORT.md`）。这与「P0-6 未做」完全一致，且无任何越界改动。
- **源码逐 hunk 核对**：`offtarget_backend.py` 的 9 处改动、4 个测试文件的全部改动、`library_preflight.py`、`index.html`、三处 CLI、`library_pipeline.py` —— 均与契约一致，无多余改动。
- **权威测试**：ms01 4 模块 91 用例 `OK`。本机（Python 3.14.7，未装 BLAST+）跑同一命令得到 `FAILED (errors=1, skipped=1)`，唯一 error 是 `test_auto_and_large_indexed_apply_mismatch_only_defaults`（本地 `blastn`/`makeblastdb` 缺失，`resolve_engine('auto', blastdb=...)` 选不到 blast）。
- **§4 冻结验证（本次范围的关键取舍）**：
  - crispAI `preflight()` → `ERRORS: []`，只剩既有的 `ucsc_chroms` warning，与改动前一致。
  - 只读 mtime 取证：`shared/scoring/crispai_runtime.py` 09-07 14:23、`tools/build_crispai_env.sh` 09-07 15:33、`tools/score_crispai.py` 09-06 17:31、`requirements.txt` 09-06 17:37、`requirements-linux.txt`/`-windows.txt` 09-07 15:33、`basic/analyze_scores.py` 09-13 12:24、`docs/CRISPAI.md` 09-13 18:05、`docs/SCORING_GUIDE.md` 09-13 22:45、`cas-offinder` 符号链接 09-07 15:32 —— 全部早于本次会话基线时刻（09-16 09:51），证明一个字节未动。
- **grep 审计**（ms01，排除 `backup/`、`.venv/`、`.codex_tmp/`、`docs/`）：
  - `bowtie2` 仅 2 处命中，都是有意保留的 `REMOVED_ENGINES = ("bowtie2", "casoffinder")`（`shared/search/offtarget_backend.py:1159`、`shared/design/library_preflight.py:26`）。
  - `casoffinder` / `cas-offinder` 的命中全部落在 crispAI 链路（`external_tools/crispAI-main/crispAI_score/crispAI.py`、`shared/scoring/crispai_runtime.py`、`basic/analyze_scores.py:161`、`tools/score_crispai.py:9,48`）加上同样那 2 处 `REMOVED_ENGINES`。搜索引擎侧已清零。

## 归属判定（既有失败 vs 本次引入）

- `test_auto_and_large_indexed_apply_mismatch_only_defaults` 在本机失败 — 依据：① servant 用基线逐字比对证明 `resolve_engine` 与该用例**与基线完全相同**；② 失败原因是本机缺 BLAST+（`shutil.which("blastn") is None`）；③ 在 ms01（`/opt/bin/blastn` 可用）复跑通过。**归属：既有环境性失败，非本次引入。**
- `ProcessLifetimeTests.test_parent_death_kills_the_engine` 在本机 skipped（`PR_SET_PDEATHSIG is Linux-only`）— 依据：跳过原因字符串；在 ms01 上正常执行。**归属：平台差异。**
- 其余 89 个用例在本机与 ms01 均通过 → **本次改动未引入任何测试回归。**

## 新发现

- `shared/design/library_preflight.py:81`（P3）— `preflight_library()` 在 try 之外调用 `validate_engine()`，所以传已下线引擎名时**抛 ValueError**，而改动前是把 "缺少 Bowtie2…" 放进 `errors` 返回。调用点 `webapp/app.py:508-516` 有 `except ValueError` → 优雅；`unified_gui.py:679-691` **没有** try → 陈旧选择会变成 Tk 未捕获异常。`tests/test_library_preflight.py:85-87` 本就断言无效引擎名要抛，属既有契约。**master 裁定：本轮不修，只记录**（真实暴露面近乎为零：`main.py` 用 `LEGACY_ENGINE_CHOICES`，且 `main.py:575` 的 `combo_library_engine` 映射与真实控件名 `combo_library_search` 不一致，引擎其实没被持久化）。
- `tests/test_offtarget_backend.py:165-175`（P3）— 删掉的两条断言中，"mismatch-only 引擎拒绝 `max_bulge=1`" 无法平移（剩余引擎无 `indels == "none"`：exact/indexed 为 `dna_rna`，blast/gggenome 为 `basic`）。规格已预判并允许。若日后想恢复该保护，需另立范围。
- 规格缺陷（已由 master 在 `task.md` 的「round 1 补充」修正）：原 §6 第三条 grep 的"预期无输出"与 C9 要求的退役报错字面量互相矛盾。servant 发现并上报，处理得当。

## 下一步

**不通过 —— 未完工**，交回 servant 完成最小清单（不改已完成部分）：

1. **P0-6 文档**：`README.md`、`docs/OFFTARGET_ENGINES.md`、`docs/GUI.md` 按 C10 收敛引擎清单/能力表/`auto` 优先级；`docs/NATIVE_INDEXED_ENGINE_DESIGN.md` 按 C10 改写；`docs/UPGRADE_REPORT.md` 只在标题下加一行退役说明。crispAI 段落一律保留。
2. **ms01 权威自检**：跑 `task.md` §6 的三条命令 + crispAI preflight，把**原文**贴进 `report.md`。
3. **补全 `report.md`**：把「进度记录」并入正式结构，填上「crispAI 未受影响的证据」与「待明确」的结论。
4. **按 `task.md`「round 1 补充」**（A1-A3）更新 grep 证据写法与 P3-1 记录。
5. 收尾：`state.json` 置 `ready_for_review` 并更新时间戳。

完成后可选项（不阻塞）：P3 两条新发现、文档措辞统一。
---

## 第二遍：终核（master，2026-09-16 13:05）

### 本轮新增交付的核验

| 任务项 | 结论 | master 独立证据 |
| --- | --- | --- |
| P0-6 文档（5 项） | 通过 | 基线逐字比对：受管 17 个文件现全部 CHANGED，且 5 个文档的改动都是最小集 —— `README.md` -3/+1（引擎表删两行 + `auto` 顺序一句）、`docs/OFFTARGET_ENGINES.md` -20/+7（工具表/能力表/默认值/`auto` 顺序/回落顺序）、`docs/GUI.md` -4/+4（四处引擎枚举）、`docs/NATIVE_INDEXED_ENGINE_DESIGN.md` -1/+1（out-of-scope 行改为 "Replacing `blast` or `gggenome`."）、`docs/UPGRADE_REPORT.md` -0/+2（仅在标题下加一行退役说明，正文未动）。crispAI 段落（如 `README.md:143` 的 Cas-OFFinder 依赖）保留 |
| 文档与代码一致 | 通过 | `docs/OFFTARGET_ENGINES.md` 改写后的 `auto` 顺序文字，与我在 ms01 实测的 C3 表逐条吻合：native 可用 → `indexed`/`blast`/`exact`；native 不可用且 bulge=0 → `blast`/`indexed`/`exact`、bulge=1 → `blast`/`exact`/`indexed`；大基因组 → `blast`/`indexed` |
| ms01 权威自检 | 通过（master 复跑） | 不采信转述，独立复跑：`py_compile` exit=0；`Ran 91 tests in 7.321s` → `OK`，exit=0，无 `ERROR:`/`FAIL:` 行；A1 `bowtie2` 审计 `wc -l` = **2**；A2 非 crispAI 来源的 `casoffinder` 审计 = **2**；`preflight()` → `ERRORS: []` |
| `report.md` 补全 | 通过 | 497 行，含 §1.1 文档改动行号、§2.1-§2.11 服务器证据原文、§3 未做项、§4 附带发现、§5 待明确（两问均按 `task.md`「round 1 补充」A1 关闭） |
| 交接文件完整性 | 通过 | `task.md` 20212 B 与第一遍 `review.md` 8043 B 均未被 servant 改写；`report.md` 只由其追加内容 |

### 归属判定（本轮新增）

| 现象 | 归属 | 依据 |
| --- | --- | --- |
| `designer_workbench.py`(09:07:46)、`main.py`(09:07:26)、`shared/search/blast_utils.py`(09:07:36) 也出现在「09-16 09:00 后被修改」清单里 | **非本任务**，属 fasta-gz-prep 的 U2 收尾 | 三者 mtime 全部早于本任务基线时刻（09:51）；对本任务引擎关键字命中数为 0；对 `ensure_plain_fasta`/`plain_fasta_is_current`/`is_gzip_file`/`open_annotation_text` 的命中数为 2/8/3 |
| 其余 09:00 后被修改项：`logs/designer_workbench_20260916_0915*.log`、`out/pair_rank_policy.json`、`scy-test/rDNA/*`、`docs/handoff/{fasta-gz-prep,gff-gz-annotation}/*`、`tests/test_fasta_gz.py`、`tests/test_gff_gz.py` | **非本任务** | 分别是运行产物、其它任务的交接文件与用例；本任务 17 个受管文件之外，无一处属于本次改动 |
| 第一遍我用 `tail -6` 抓不到 unittest 汇总行 | master 自身命令缺陷 | `2>&1 | tail` 受 stdout 块缓冲影响，stderr 汇总行被顶到前面；改用 `PYTHONUNBUFFERED=1` + 落盘后 grep 即得 `Ran 91 tests ... OK` |

### 冻结与越界复核

- 冻结清单 mtime（本轮再次取证）：`shared/scoring/crispai_runtime.py` 09-07 14:23、`tools/build_crispai_env.sh` 09-07 15:33、`tools/score_crispai.py` 09-06 17:31、`requirements.txt` 09-06 17:37、`requirements-linux.txt`/`-windows.txt` 09-07 15:33、`basic/analyze_scores.py` 09-13 12:24、`docs/CRISPAI.md` 09-13 18:05、`docs/SCORING_GUIDE.md` 09-13 22:45、`external_tools/.../casoffinder/cas-offinder` 09-07 15:32 —— **全部未动**。
- 本任务 17 个受管文件之外，无一处本次改动。

## 最终结论：pass

- P0-1 ~ P0-6、P1-1、P1-2、P2-1 全部通过，无 P0/P1 遗留。
- 无本次引入的测试回归（ms01 91/91 通过；本机那 1 error + 1 skip 已分别证明为缺 BLAST+ 的环境性失败与 Linux-only 平台差异）。
- 冻结清单完好，crispAI `preflight()` 仍为 `ERRORS: []`。
- 记录不修（P3，已在 `report.md` §4 与 `state.json.open_followups` 留痕）：`shared/design/library_preflight.py:81` 陈旧引擎名抛异常路径；`tests/test_offtarget_backend.py` 原 mismatch-only 断言无法平移；`main.py:575` 的失效映射。

### 可选的后续（不阻塞，建议另立任务）

1. P3-1：把 `shared/design/library_preflight.py:81` 的 `validate_engine()` 包进 `try/except ValueError` 并返回 errors（`unified_gui.py:679-691` 当前无 except）。
2. 三处 CLI 的 `--engine` 字面量改为从 `ENGINE_CHOICES` 派生（本次按 C7 有意保留字面量）。
3. 修正 `main.py:575` 的 `combo_library_engine` → `combo_library_search` 映射（会改变引擎持久化行为，需单独评估）。