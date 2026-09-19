# 任务：NAR Methods 投稿要件打包（格式规范落地）

- task-slug: `nar-format-pack`
- round: 1
- master: 会话 M（master）
- servant: 会话 S（servant）
- repo: `R:\songji\programfile`
- 本地环境：`python` = Python 3.14.7
- 基线快照：本任务只新增文件，不改既有文件，无需快照
- 上位文档：`docs/PAPER_OUTLINE.md` 第九节（格式规范）+ `docs/ALLEGRO_REFERENCE_ANALYSIS.md`
- 格式范本（两篇，均为 NAR Methods 在线专发）：
  - 主范本 ALLEGRO，NAR 2025, 53, gkaf783, doi:10.1093/nar/gkaf783
    （抽取文本 `R:/songji/论文/3/ALLEGRO-2025-nar.txt`，99690 字节）
  - 副范本 CRISPR-COPIES，NAR 2024, 52, e30, doi:10.1093/nar/gkae062
    （`R:/songji/论文/3/gkae062.pdf`，17 页）

## 0. 目标与边界

背景：格式范本为**两篇 NAR Methods 专发论文**：主范本 **ALLEGRO**（NAR 2025, 53, gkaf783，
doi:10.1093/nar/gkaf783；摘要 173 词、主文 Figure 1-5、无主文表、含 Graphical abstract）、
副范本 **CRISPR-COPIES**（NAR 2024, 52, e30；摘要 206 词、17 页、无主文表）。
两篇在摘要长度与 back matter 顺序上略有差异，本任务一律按下面的 C1/C2 执行，不要自行取中。
`docs/PAPER_OUTLINE.md` 第九节与 `docs/ALLEGRO_REFERENCE_ANALYSIS.md` 已记录全部量化规范。

本任务把该规范落成可以直接用于投稿的一组要件。

**重要：另外三个任务正在进行中，本任务不得触碰它们的任何产物**：

| 任务 | 已占用文件（禁止改动） |
| --- | --- |
| `expr-matrix` | `tools/expressiveness_probe.py`、`docs/expressiveness_matrix.tsv`、`docs/EXPRESSIVENESS_MATRIX.md` |
| `engine-bench` | `tools/seed_plan_sweep.py`、`docs/seed_plan_sweep.json`、`docs/SEED_PLAN_ANALYSIS.md` |
| `methods-draft` | `docs/PAPER_METHODS_DRAFT.md` |

也不得改动 `docs/PAPER_OUTLINE.md` 与 `docs/PAPER_OUTLINE_WITH_EXPERIMENTS.md`。

要做到（全部为新增文件）：

1. `docs/NAR_FORMAT_CHECKLIST.md` — 逐条合规对照表
2. `docs/PAPER_FRONT_MATTER.md` — 标题候选 + 作者/单位块模板 + Abstract 草稿
3. `docs/PAPER_BACK_MATTER.md` — Data availability 等五段
4. `docs/GRAPHICAL_ABSTRACT_SPEC.md` — 图形摘要规格
5. `docs/FIGURE_TABLE_PLAN.md` — 主文图/表最终清单
6. （P1）`docs/assets/graphical_abstract_draft.svg` — 简易草稿

不做：不改代码；不改上述任何既有文件；不生成最终美术稿；不跑测试套件；
不写 Results / Discussion 正文。

## 1. 规则 / 契约（唯一权威版本，servant 不需要重新调研）

```text
C1  摘要（PAPER_FRONT_MATTER.md 内）：
    - 170-250 词，单段，无小标题，无引用编号
    - 立场必须与无实验版一致：主张止于「设计空间可表达、可完备枚举」，
      不得出现任何暗示做过实验的表述
    - 不得出现 first / never / unprecedented / 首创 类措辞
C2  Back matter 段落与顺序（采用 2025 主范本 ALLEGRO 的顺序）：
    Acknowledgements（须含一行 `Author contributions:`）| Supplementary data |
    Conflict of interest | Funding | Data availability
    - 注：2024 副范本顺序为 Data availability 在前、Acknowledgements 在后；NAR 两种都接受，
      本次统一按 2025 顺序书写，并在 NAR_FORMAT_CHECKLIST.md 里注明这一选择
    - Data availability 基准句式（2025 主范本，仓库+DOI 式，未定项写 [TO FILL]）：
      `<工具名> is freely available on GitHub at [TO FILL repository URL] and on`
      `Zenodo at [TO FILL version DOI]. Documentation is provided on the project wiki.`
      `All data used in this study can be obtained from the repository and the`
      `Supplementary Data.`
    - Supplementary data 基准句式（2025 主范本）：`Supplementary data is available at NAR online.`
      （2024 副范本写法 `Supplementary Data are available at NAR Online.` 同样被接受；两者不得混用）
    - Acknowledgements 必须含 `Author contributions:` 段，按 CRediT 角色逐位写
      （Conceptualization / Software / Methodology / Validation / Writing - original draft /
      Writing - review and editing 等）；作者信息未定时整段写 [TO FILL]
    - 凡本项目尚未确定的信息（作者、单位、基金号、仓库 URL、DOI）一律写 [TO FILL]，
      并在 NAR_FORMAT_CHECKLIST.md 登记为待补项，不得编造
    - 数学表述（如种子计划代价方程）按 2025 主范本惯例放 Supplementary Notes，主文只留结论与引用
C3  图表计划（FIGURE_TABLE_PLAN.md）：
    - 主文表 = 0（两篇范本均无主文表）；确有需要时最多 1 张，其余一律进 Supplementary
    - 表达力矩阵（expr-matrix 的产物）指定为主文**图**，不是表
    - 必须给出最终编号清单，格式：`Figure N — 内容 — 来源任务/文件 — 状态`
    - 原计划的主文表（Table 1-5）逐条判定：留主文 / 移 Supplementary / 合并
C4  合规对照表（NAR_FORMAT_CHECKLIST.md）每行四列：
    要求 | 现状 | 归属（任务或 master） | 状态（done / pending / blocked / n/a）
    至少要覆盖参考文第九节表格里的 13 个项目
C5  Graphical abstract 规格须含：展示要素（建议 3 个）、版式结构、
    建议尺寸与比例、配色约束、与 Figure 1 的区分度、制作方式建议。
    规格里必须写明「最终尺寸与格式需向期刊确认」。
C6  所有英文写作的立场与措辞必须与 `docs/PAPER_OUTLINE.md` 第二节「措辞对照」一致。
```

## 2. 现状证据（master 已核实，可直接引用）

- 主范本已抽取：`R:/songji/论文/3/ALLEGRO-2025-nar.txt`（99690 字节，`pdftotext -layout -enc UTF-8`）
  统计：摘要 173 词；主文 Figure 1-5；Supplementary Fig S1-S10；正文无 Table 引用（表一律 Sn）；
  有 Graphical abstract；back matter 顺序 = Acknowledgements(含 Author contributions) ->
  Supplementary data -> Conflict of interest -> Funding -> Data availability -> References
- 参考文已抽取：`R:\songji\论文\3\gkae062.pdf`（17 页）
  统计来源命令：`pdftotext -layout -enc UTF-8`，主文无 `Table` 引用
- `docs/PAPER_OUTLINE.md` 第九节含完整对照表（栏目/篇幅/摘要 206 词/78 条参考/19 处 Figure/
  0 主文表/章节顺序/子标题无编号/Data availability 句式/BioRender 声明）
- `docs/PAPER_OUTLINE.md` 第三节有 `### Abstract（NAR 惯例：单段，不分区；参考文 206 词，目标 170-250 词）`
- `docs/PAPER_OUTLINE.md` 第四节为现有图表清单（Fig 1-6、Table 1-5）
- master 已在该文 §2.1 先例表加入 CRISPR-COPIES 一行
- 参考文原文句式已抄录在本 task.md 的 C2

## 3. 必做改动

- [ ] P0-1 `docs/NAR_FORMAT_CHECKLIST.md`（新增，按 C4）
- [ ] P0-2 `docs/PAPER_FRONT_MATTER.md`（新增，按 C1）：
      标题候选 >= 2 个；作者/单位块用 [TO FILL] 占位；Abstract 草稿满足词数
- [ ] P0-3 `docs/PAPER_BACK_MATTER.md`（新增，按 C2）
- [ ] P0-4 `docs/FIGURE_TABLE_PLAN.md`（新增，按 C3）
- [ ] P0-5 `docs/GRAPHICAL_ABSTRACT_SPEC.md`（新增，按 C5）
- [ ] P1-1 `docs/assets/graphical_abstract_draft.svg`（新增，简易草稿即可，
      必须能独立打开、无外部依赖；不追求最终美术质量）

## 4. 不要做的事

- 不改其它三个任务的任何产物文件（见 §0 表）
- 不改 `docs/PAPER_OUTLINE.md`、`docs/PAPER_OUTLINE_WITH_EXPERIMENTS.md`
- 不改任何 `.py` / `.cpp` / `.html` 代码
- 不生成最终美术稿、不使用 BioRender 等外部服务
- 不编造作者、单位、基金、URL、DOI 等信息
- 不跑测试套件；不做耗时基准

## 5. 决策项（未确认则按推荐执行）

- 作者/单位/基金信息未知 → 推荐全部写 `[TO FILL]` 并在 checklist 登记
- 原 Table 5「输出字段契约」 → 推荐移到 Supplementary
- 原 Table 1「种子计划 (M,B,L) 下的 s* 与 W」 → 推荐留在主文（engine-bench 的产物）
- 表达力矩阵的图号 → 推荐排在 Fig 2 之后作为新的 Fig 3，原 Fig 3-6 顺延；
  并在 FIGURE_TABLE_PLAN.md 中标注「最终编号待 master 与其它三个任务交付后排定」
- Graphical abstract 尺寸 → 推荐先按参考文比例给建议值，并标注需向期刊确认

## 6. 轻量自检（servant 的检验上限）

```powershell
cd R:\songji\programfile
python -c "import re;d=open(r'docs/PAPER_FRONT_MATTER.md',encoding='utf-8').read();m=re.search(r'## Abstract(.*?)##',d,re.S);w=len(re.findall(r'[A-Za-z][A-Za-z-]*',m.group(1)));print('abstract_words',w);print('ok',170<=w<=250)"
python -c "import os;fs=['NAR_FORMAT_CHECKLIST.md','PAPER_FRONT_MATTER.md','PAPER_BACK_MATTER.md','FIGURE_TABLE_PLAN.md','GRAPHICAL_ABSTRACT_SPEC.md'];print([(f,os.path.exists(os.path.join('docs',f))) for f in fs])"
python -c "import os;print('allegro_txt', os.path.exists(r'R:/songji/论文/3/ALLEGRO-2025-nar.txt'))"
python -c "import re,os;fs=['docs/PAPER_FRONT_MATTER.md','docs/PAPER_BACK_MATTER.md','docs/FIGURE_TABLE_PLAN.md','docs/GRAPHICAL_ABSTRACT_SPEC.md','docs/NAR_FORMAT_CHECKLIST.md'];pat=re.compile(r'(?i)\b(first|never|unprecedented)\b');print({f:pat.findall(open(f,encoding='utf-8').read()) for f in fs if os.path.exists(f)})"
```

预期：`abstract_words` 落在 170-250；五个文件全部 True。

## 7. 交付要求

- 完成后：`state.json` 置 `ready_for_review` 并更新 `updated`，写 `report.md`
- `report.md` 必填：改动文件+行号表格、命令原文与输出、未做项及原因、
  附带发现（只记录不修）、待明确项
- 不要自己裁定「通过」；核验归 master