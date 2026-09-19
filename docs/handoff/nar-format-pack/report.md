# 交付报告：nar-format-pack

- round: 1
- status: ready_for_review
- updated: 2026-09-19 10:46
- 环境：Windows + Samba 共享盘；`python` = Python 3.14.7（本机）

## 契约版本说明（重要）

本会话开工时读到的是 `task.md` **r1**（摘要 180-250 词、back matter 五段按 2024 顺序、主文表不超过 2 张）。
master 在 **2026-09-19 10:40:06** 发布了 **r2**（`state.json.task_md_revision` 记录）：双范本（ALLEGRO NAR 2025
53 gkaf783 为主范本）、摘要改 **170-250 词**、back matter 改 2025 顺序并增 `Author contributions:`、
Data availability 改「GitHub URL + Zenodo 版本 DOI + 文档」句式、**主文表 = 0**。
本报告与全部交付件已按 **r2** 重写并重跑自检；r1 版本的中间稿未保留（首轮交付前重写，无历史包袱）。

## 改动清单

全部为新增文件，未修改任何既有文件。

| 文件 | 行 | 改了什么 | 对应任务项 |
| --- | --- | --- | --- |
| `docs/NAR_FORMAT_CHECKLIST.md` | 1-52（新增） | 四列合规对照表：第九节 13 项 + 3 条 2025 主范本增量规则（back matter 顺序选择注明、Author contributions、数学表述入 Supplementary Notes）；`[TO FILL]` 登记 13 条 | P0-1 |
| `docs/PAPER_FRONT_MATTER.md` | 1-65（新增） | 3 个标题候选（含推荐 A）、作者/单位块 `[TO FILL]` 模板、Abstract 草稿 221 词、关键词、交付件接口 | P0-2 |
| `docs/PAPER_BACK_MATTER.md` | 1-60（新增） | 五段按 2025 顺序（Acknowledgements 含 `Author contributions:` -> Supplementary data -> Conflict of interest -> Funding -> Data availability），含 2025 两条基准句式与四句 Data availability 结构 | P0-3 |
| `docs/FIGURE_TABLE_PLAN.md` | 1-73（新增） | Figure 1-7 四字段清单 + 编号映射 + **主文表 = 0** 判定 + 原 Table 1-5 逐条判定与破例条款 + 规则冲突说明 | P0-4 |
| `docs/GRAPHICAL_ABSTRACT_SPEC.md` | 1-75（新增） | 三要素、版式结构、尺寸与比例（副范本实测 941x388 / 2.43:1）、配色约束、与 Figure 1 区分度、制作方式、验收清单 | P0-5 |
| `docs/assets/graphical_abstract_draft.svg` | 1-93（新增） | 自绘 SVG 草稿，941x388，三段式，可独立打开、无外部依赖 | P1-1 |

## 轻量自检结果

命令原文与输出（`task.md` r2 第 6 节四条，逐字执行）：

```powershell
cd R:\songji\programfile
python -c "import re;d=open(r'docs/PAPER_FRONT_MATTER.md',encoding='utf-8').read();m=re.search(r'## Abstract(.*?)##',d,re.S);w=len(re.findall(r'[A-Za-z][A-Za-z-]*',m.group(1)));print('abstract_words',w);print('ok',170<=w<=250)"
python -c "import os;fs=['NAR_FORMAT_CHECKLIST.md','PAPER_FRONT_MATTER.md','PAPER_BACK_MATTER.md','FIGURE_TABLE_PLAN.md','GRAPHICAL_ABSTRACT_SPEC.md'];print([(f,os.path.exists(os.path.join('docs',f))) for f in fs])"
python -c "import os;print('allegro_txt', os.path.exists(r'R:/songji/论文/3/ALLEGRO-2025-nar.txt'))"
python -c "import re,os;fs=['docs/PAPER_FRONT_MATTER.md','docs/PAPER_BACK_MATTER.md','docs/FIGURE_TABLE_PLAN.md','docs/GRAPHICAL_ABSTRACT_SPEC.md','docs/NAR_FORMAT_CHECKLIST.md'];pat=re.compile(r'(?i)\b(first|never|unprecedented)\b');print({f:pat.findall(open(f,encoding='utf-8').read()) for f in fs if os.path.exists(f)})"
```

```text
=== CMD1 ===
abstract_words 221
ok True
=== CMD2 ===
[('NAR_FORMAT_CHECKLIST.md', True), ('PAPER_FRONT_MATTER.md', True), ('PAPER_BACK_MATTER.md', True), ('FIGURE_TABLE_PLAN.md', True), ('GRAPHICAL_ABSTRACT_SPEC.md', True)]
=== CMD3 ===
allegro_txt True
=== CMD4 ===
{'docs/PAPER_FRONT_MATTER.md': [], 'docs/PAPER_BACK_MATTER.md': [], 'docs/FIGURE_TABLE_PLAN.md': [], 'docs/GRAPHICAL_ABSTRACT_SPEC.md': [], 'docs/NAR_FORMAT_CHECKLIST.md': []}
```

补充自检（本任务自加，非 `task.md` 要求）：

```powershell
python -c "import xml.etree.ElementTree as ET;print('svg xml ok', ET.parse(r'docs/assets/graphical_abstract_draft.svg').getroot().tag)"
```

```text
svg xml ok {http://www.w3.org/2000/svg}svg
```

SVG 渲染核验（headless Edge，输出 941x388 PNG 后人工目视）：

```powershell
& "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" --headless --disable-gpu --no-sandbox --user-data-dir="$env:TEMP\nar_ga_probe\profile" --screenshot="$env:TEMP\nar_ga_probe\ga_draft2.png" --window-size=941,388 --hide-scrollbars "file:///$env:TEMP/nar_ga_probe/ga.svg"
```

```text
输出文件存在：True（941x388 PNG，三段式与文字正常，无重叠、无越界）
```

图形摘要尺寸依据（副范本 CRISPR-COPIES 首页内嵌位图实测）：

```powershell
pdfimages -list "R:\songji\论文\3\gkae062.pdf"
```

```text
page   num  type   width height color comp bpc  enc interp  object ID x-ppi y-ppi size ratio
   1     0 image     941   388  rgb     3   8  jpeg   no      1461  0   200   200 62.9K 5.9%
```

上游行号引用核验（r2 后重取，逐条打印被引行内容，确认锚点仍指向预期语义）：

```text
NAR_FORMAT_CHECKLIST.md 9   -> 赛道：**NAR Methods**（在线专发，e-locator）
NAR_FORMAT_CHECKLIST.md 347 -> 摘要按 170-250 词写
NAR_FORMAT_CHECKLIST.md 325 -> | 章节顺序 | Abstract -> ... | Materials and methods 之前
NAR_FORMAT_CHECKLIST.md 351 -> 子标题改为无编号描述性短语
PAPER_FRONT_MATTER.md   128 -> 建议：`CRISPR-Motif Workbench: a constraint-driven ...`
PAPER_FRONT_MATTER.md   347 -> 摘要 170-250 词
PAPER_BACK_MATTER.md    328 -> Data availability 基准句（2024 副范本）
PAPER_BACK_MATTER.md    199 -> GitHub release tag + Zenodo DOI 建议
PAPER_BACK_MATTER.md    329 -> Supplementary data 固定句（2024 副范本）
ALLEGRO_REFERENCE_ANALYSIS.md 81/82/83/85 -> 摘要 173 词 / 主文图 5-6 张 / 主文表无 / back matter 2025 顺序
```

## 未做项

- 最终美术稿（图形摘要精修、按期刊规格出图）— `task.md` 第 0/4 节明确不做，本轮只出规格 + 示意草稿。
- 测试套件与任何耗时基准 — `task.md` 第 4 节明确不做。
- 正文 Results / Discussion、参考文献表、Supplementary 正文 — 不在本任务范围。
- Figure 最终编号与主文图是否压缩到 5-6 张 — 依赖 expr-matrix / engine-bench / methods-draft 三个任务交付，`FIGURE_TABLE_PLAN.md` 已给压缩预案但未擅自改号。
- 期刊侧待确认项（图形摘要尺寸与格式、摘要字数上限、关键词是否必需）— 需外部确认，已登记 `[TO FILL]`。

## 附带发现（不在本次范围，未修）

- `task.md` 在 10:40:06 由 r1 升到 r2，且 `docs/PAPER_OUTLINE.md`（10:40:40）、`docs/ALLEGRO_REFERENCE_ANALYSIS.md`（10:38:56）、`docs/handoff/nar-format-pack/state.json`（10:40:45）同批更新，均为 master 侧写入，非本会话改动。本会话在 r1 下已产出的中间稿全部重写，未残留 r1 口径（180-250 词、五段 2024 顺序、主文表 2 张）。
- `task.md` C3 与 §5 决策项冲突：C3 写「主文表 = 0」，§5 写「原 Table 1 推荐留在主文」。本包按「规则/契约是唯一权威版本」执行（0 张），并在 `docs/FIGURE_TABLE_PLAN.md` §2/§3 写下破例条款与冲突说明，请 master 裁定。
- `docs/EXPRESSIVENESS_MATRIX.md:1` 标题仍写「/ Table 3」，与本包「矩阵改为主文图 Figure 3」不一致 — 建议 master 决定是否让 expr-matrix 更新标题（本任务不得改该文件）。
- `docs/handoff/engine-bench/state.json` 仍为 `implementing`，`docs/SEED_PLAN_ANALYSIS.md` 未出现 — Figure 5/6 与 Table S3 数字待定稿。
- `docs/handoff/methods-draft/state.json` 为 `needs_rework`（round 2，must_fix 3 条）— 子标题去编号与「数学表述入 Supplementary Notes」两项在 checklist 中保持 `pending`，本轮无法验收。
- 表达力矩阵 16 个已发表工具行中含 `unknown` 格（GT-Scan、Cas-Designer、EuPaGDT、CRISPR multitargeter、DECKO 等）— Abstract 采用 `none is documented as expressing` 规避绝对化；若要更强表述需补证据。
- 矩阵共 17 行（16 个已发表工具 + This work），Abstract 写 `16 published design tools`，Figure 3 图注口径为 17 行 — 建议图注明确区分，避免审稿人误读。
- 主范本 ALLEGRO 的 PDF 不在本机（`R:/songji/论文/3/` 只有文本抽取件与副范本 PDF），故图形摘要尺寸只能按副范本实测值给建议。
- `docs/handoff/nar-format-pack/assets/master_probe_allegro.py` 为 master 的探针脚本（读 `ALLEGRO-2025-nar.txt`），非本任务产物，未改动。

## 待明确

1. 主文表最终取 0 张还是破例 1 张（§5 与 C3 冲突）：本包按 C3 = 0 张交付，破例首选项已标注为原 Table 1。
2. 主文图是否从 7 张压缩到 5-6 张（主范本规模）：本包给的压缩预案是 Figure 6、Figure 7 移 Supplementary，Figure 3 必须留主文。
3. Figure 3 的最终排位与全表编号：等 engine-bench / methods-draft 交付后由 master 排定。
4. 图形摘要最终尺寸与格式：需向期刊确认；是否按主范本（ALLEGRO）比例重取建议值，待 master 提供主范本 PDF。
5. Data availability 中「Documentation is provided on the project wiki.」是否保留 wiki 措辞，或改写为仓库 `docs/` 路径（本项目当前无 wiki）。
6. 关键词是否必需（两篇范本均未设该小节，投稿系统可能强制）。
7. 摘要是否补具体基准数字（warm search 延迟、线程扩展）：本包刻意留白，等 engine-bench 定稿后由 master 决定。
