# 交付报告：expr-matrix

- round: 1
- status: ready_for_review
- updated: 2026-09-19 10:36

## 改动清单

| 文件 | 行 | 改了什么 | 对应任务项 |
| --- | --- | --- | --- |
| `tools/expressiveness_probe.py` | 1–470（新增） | 纯标准库自证探针：IUPAC PAM、非 NGG PAM、可变靶长度、3'/5' 方向、双链、motif 锚定成对四链向 + 距离区间；`--json` 输出汇总记录（键名即 C1 列名），任一断言失败退出码非 0 | P0-1 |
| `docs/expressiveness_matrix.tsv` | 1–17（新增） | 表头 + 16 数据行，列名与顺序按 C1，取值按 C2，行序按 C3；证据列全部为 DOI / 官方文档 URL / 本仓库 `文件:行` | P0-2 |
| `docs/EXPRESSIVENESS_MATRIX.md` | 1–145（新增） | 同内容 Markdown 表 + C6/C7/C8 定义与判定口径 + 我方行锚点清单 + 「如何复现」+ 逐行说明 + 「证据来源」（工具 — 来源 — 支撑列） | P0-3 / P1-1 |

未改动任何既有文件：`shared/`、`basic/`、`tools/` 既有文件、`docs/PAPER_OUTLINE.md` 均保持原样（本任务无需基线快照）。

## 轻量自检结果

```powershell
cd R:\songji\programfile
python -m py_compile tools\expressiveness_probe.py
python tools\expressiveness_probe.py --json
python -c "import csv;rows=list(csv.DictReader(open(r'docs\expressiveness_matrix.tsv',encoding='utf-8'),delimiter='\t'));print(len(rows));print(rows[0]['tool'])"
```

```text
py_compile exit=0

python tools\expressiveness_probe.py
...
[PASS] independent_length_and_side  left upstream/4 -> (4, 8) 'GAGA'; right downstream/7 -> (11, 18) 'TGAGAGA'; strand flips side

capabilities: custom_pam_tam=True, custom_target_length=True, custom_orientation=True, middle_element_constraint=True, enumerates_all_occurrences=True, pair_side_independent=True
19/19 checks passed
exit=0

python tools\expressiveness_probe.py --json   （退出码 0，摘录汇总键）
{"tool": "This work (CRISPR-Motif Workbench)", "year": "2026", "input_model": "both",
 "custom_pam_tam": true, "custom_target_length": true, "custom_orientation": true,
 "middle_element_constraint": true, "enumerates_all_occurrences": true,
 "pair_side_independent": true, "checks_passed": 19, "checks_total": 19, "ok": true}

python -c "...csv self-check..." 
16
This work (CRISPR-Motif Workbench)
```

附带的一致性自检（自写，非任务要求）：

```text
tsv rows: 16 first: This work (CRISPR-Motif Workbench)
md header == tsv header: True
md rows: 16 equal to tsv: True
cell diffs: [] count: 0
```

探针在本机 Python 3.14.7 上的完整输出已原文贴在 `docs/EXPRESSIVENESS_MATRIX.md` 的「如何复现」小节。
未使用 ms01 权威环境复跑（属 master 核验范围）。

## 未做项

- 引擎基准（`tools/benchmark_all_engines.py` 扩展）— 任务 §0「不做」，属 `engine-bench`。
- 安装/运行任何竞品工具 — 任务 §4 明确禁止；竞品能力只从其论文/官方文档/公开仓库读取。
- 全量测试套件 `run_tests.py` — 任务 §4 明确不做。
- 部分竞品源码核验 — 官方站点为 JS 单页应用或站点不可访问（EuPaGDT、GT-Scan、DECKO），只核验到论文，已在 md「逐行说明」注明（未核验源码）。

## 附带发现（不在本次范围，未修）

- `Target_xbp_Y_zbp_Target/extract_motifs.py:136-145` — task.md §2 现状证据写的 argparse 参数名与实际不符：仓库里没有 `--left-min-distance/--left-max-distance/--right-min-distance/--right-max-distance`，实际是位置参数 `L`/`R`（最大左/右距离）加 `--min_left`/`--min_right`（默认 0）。本次按仓库实际锚点写入矩阵与锚点清单；task.md 若再版建议更正。
- `Target_xbp_Target/extract_complex_queries.py:8-11` — 模块级 `from Bio import SeqIO` / `from Bio.Seq import Seq`，纯标准库探针无法直接 `import` 该模块。探针改为用 `ast` 只提取 `flank_interval`/`get_flank` 两个函数定义后 `exec`，运行期记录锚点（`extract_complex_queries.py:19` 与 `:30`），并在 JSON 的 `pair_helpers_loaded` 检查中留痕。若要长期免依赖复用，可考虑将来把这两个纯字符串函数抽到 `shared/`（本次未改，属越界）。
- task.md §2 提到的 `native\bin\offtarget-engine.exe capabilities --json` 佐证 — 本地未复跑该二进制（超出 servant 自检上限，且属引擎侧证据）；若正文要用，请 master 在 ms01 或本机复核后引用。
- `docs/PAPER_OUTLINE.md:47` 把 GuideScan 记为 2017（Nat Biotechnol），而本表 `GuideScan2` 行按 `pritykinlab/guidescan-cli` README 的官方引用取 Genome Biology 2025（DOI 10.1186/s13059-025-03488-8）。正文引用时建议明确区分 GuideScan(2017) 与 GuideScan2(2025)，否则 year 列会被审稿人挑。
- EuPaGDT 站点 `http://grna.ctegd.uga.edu/` 现为 React 单页应用，抓取不到界面源码，其 `custom_orientation` / `middle_element_constraint` / `pair_side_independent` 记 `unknown`；仅依据论文正文（DOI 10.1099/mgen.0.000033）填了 PAM/长度两列。

## 待明确

- `enumerates_all_occurrences` 的竞品判定口径：本表对只接受坐标区间的工具，按「是否枚举该区间内全部符合条件位点（而非只返回最优位点）」判定，并在 md 的列定义里写明「本列不区分锚点类型」。若 master 认为该口径不合适（例如应只对 motif 锚定工具记 yes，坐标工具记 partial），请回一版口径，我按新口径重算该列。
- DECKO / GT-Scan 两行大量 `unknown` 是否可接受：若正文需要更硬的结论，建议 master 指定可核验的替代来源（如 DECKO 的补充材料、GT-Scan 的存档页面），我再补。
- 我方行 `year=2026`：按投稿年份填写，若需与论文/预印本一致请给出准确年份。
