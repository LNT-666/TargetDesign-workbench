# 任务：参数表达力矩阵（论文 C1 的核心证据）

- task-slug: `expr-matrix`
- round: 1
- master: 会话 M（master）
- servant: 会话 S（servant）
- repo: `R:\songji\programfile`（镜像服务器 `/home/apool/songji/programfile`）
- 权威运行环境：ms01 `/home/apool/songji/programfile/.venv/bin/python`
- 本地环境：`python` = Python 3.14.7（master 已实测：本任务探针在本地可跑，不需要 numpy/biopython）
- 基线快照：本任务只新增文件、不改既有文件，无需快照
- 上位文档：`docs/PAPER_OUTLINE.md` 第五节第 1 项

## 0. 目标与边界

背景：论文 C1（声明式的引导定义空间）的立论依赖一张「参数表达力矩阵」，用来证明
现有工具无法表达本程序的设计意图。目标期刊为 Nucleic Acids Research 正刊。

要做到：

1. 新增 `tools/expressiveness_probe.py`，用本仓库真实代码路径证明我方能力。
2. 新增 `docs/expressiveness_matrix.tsv`（机读）与 `docs/EXPRESSIVENESS_MATRIX.md`（人读），内容一致。
3. 每个竞品单元格有可核查来源；无法确证填 `unknown`，不得填 `no`。

不做：不改任何既有生产代码；不做引擎基准（属 `engine-bench`）；不安装或运行竞品工具；
不写论文正文；不跑全量测试套件。

## 1. 规则 / 契约（唯一权威版本，servant 不需要重新调研）

```text
C1  列固定且顺序不可改：
    tool | year | input_model | custom_pam_tam | custom_target_length |
    custom_orientation | middle_element_constraint | enumerates_all_occurrences |
    pair_side_independent | evidence
C2  取值受限：
    input_model ∈ {coordinate, sequence, both}
    其余六列 ∈ {yes, partial, no, unknown}
C3  行固定为这 16 个，顺序不可改：
    1 This work (CRISPR-Motif Workbench)   2 CHOPCHOP v3      3 CRISPOR
    4 FlashFry     5 CRISPRitz   6 GuideScan2    7 CRISPETa   8 pgRNAFinder
    9 GT-Scan     10 Cas-Designer  11 Breaking-Cas  12 EuPaGDT
    13 CaSilico   14 crisprVerse  15 DECKO        16 CRISPR multitargeter
C4  证据列必须是可直接核查的定位：论文 DOI、官方文档 URL，或源码 file:line。
    不接受「据我们所知」「通常」这类无出处判断。无法确证 -> unknown。
C5  我方行的每一格必须有本仓库 文件:行 锚点，且被 tools/expressiveness_probe.py 实测支撑。
C6  middle_element_constraint 定义（写进 md 表头说明）：
    「设计输入是否允许指定一个必须存在于左右靶点之间的序列元件，
      并对左右两侧分别给出独立距离区间」
C7  enumerates_all_occurrences 定义：
    「锚点以序列 motif 给出时，是否枚举该 motif 在目标序列/基因组中的全部出现位置」
C8  pair_side_independent 定义：
    「成对设计中左右两侧的 PAM/TAM、长度、方向能否各自独立设定」
```

## 2. 现状证据（master 已核实，可直接引用）

- `shared/design/guide_design.py:9` — 模块 docstring 原文：`This module keeps the existing free-input behavior: callers can pass any spacer length, PAM and strand. System presets are only used to fill defaults.`
- `shared/design/guide_design.py:54` — `def find_guides(sequence, spacer_len=20, pam=None, pam_side="3prime", motif=None, allow_reverse=True, seq_id=None)`
- `shared/design/pattern_spec.py` — `_IUPAC_BASES = set("ACGTUNRYSWKMBDHV")`
- `shared/search/iupac.py` — `iupac_to_regex` / `find_all_iupac_matches` / `find_all_iupac_positions`
- `Target_xbp_Target/extract_complex_queries.py:26-33` — 用法
  `<input.fasta> <left_motif> <right_motif> <min_gap> <max_gap> <left_side> <left_len> <right_side> <right_len> <out.tsv>`，
  注释原文：`Left and right motifs are each matched on plus and minus, so all four strand combinations are considered.`
- `Target_xbp_Y_zbp_Target/extract_motifs.py` — 以 Y 为锚，argparse 含 `--left-min-distance` / `--left-max-distance` / `--right-min-distance` / `--right-max-distance`（约 136-158 行）
- `designer_workbench.py:702-730` — UI 字段原文：`PAM/TAM Motif`、`Target Length`、`Target Position`（选项 `downstream` / `upstream`）
- master 实测（本地 Python 3.14.7）：
  `sys.path.insert(0, r'R:\songji\programfile\shared'); from design.guide_design import find_guides; find_guides('TTTTACGTACGTACGTACGTAAGGTTTT', spacer_len=20, pam='NGG', pam_side='3prime')`
  → `OK count=1`，返回键含 `strand` / `pam_seq` / `pam_start` / `pam_end` / `spacer_start` / `spacer_end` / `system_pam_side`
- master 实测：`native\bin\offtarget-engine.exe capabilities --json` →
  `"pam_sides": ["3prime","5prime"]`（可作 C5 的引擎侧佐证）

## 3. 必做改动

- [ ] P0-1 `tools/expressiveness_probe.py`（新增）
  - 期望行为：纯标准库；把 `shared/` 与仓库根加入 `sys.path`；调用 `design.guide_design.find_guides` 逐项断言：
    (a) IUPAC PAM：至少 `VNG` 与 `NNGRRT` 能匹配到预期条数
    (b) 非 NGG PAM：至少 `TTTV`（3prime）与以 `pam_side='5prime'` 使用的 PAM
    (c) 可变靶长度：`spacer_len ∈ {18,20,23}` 均返回结果且 `spacer_end - spacer_start == spacer_len`
    (d) 方向：`pam_side='3prime'` 与 `'5prime'` 均返回结果
    (e) 双链：`allow_reverse=True` 时同一序列上同时出现 `strand` 为 plus 与 minus 的记录
    (f) motif 锚定成对：import `Target_xbp_Target/extract_complex_queries.py` 的 `flank_interval` / `get_flank`，
        断言四种链向组合 `++ / +- / -+ / --` 均可产生
  - 证据要求：`--json` 输出一条汇总记录（键名即 C1 的列名）；任一断言失败则退出码非 0
- [ ] P0-2 `docs/expressiveness_matrix.tsv`（新增）：按 C1–C4 生成，制表符分隔，含表头
- [ ] P0-3 `docs/EXPRESSIVENESS_MATRIX.md`（新增）：同内容 Markdown 表 + C6/C7/C8 定义 + 我方行锚点清单
      + 「如何复现」小节（给出 P0-1 命令与预期输出）
- [ ] P1-1 md 末尾附「证据来源」小节：按行列出每个竞品的 DOI/URL，格式 `工具 — 来源 — 支撑哪几列`

## 4. 不要做的事

- 不改 `shared/`、`basic/`、`tools/` 下任何既有文件（只新增 `tools/expressiveness_probe.py`）
- 不改 `docs/PAPER_OUTLINE.md`
- 不安装或运行竞品工具；竞品能力只从文献/官方文档/其源码公开仓库推断
- 不写 first / never / 从未 类措辞
- 不跑全量测试套件（`run_tests.py`）

## 5. 决策项（未确认则按推荐执行）

- 竞品某格在官方文档中找不到明确说明 → 推荐填 `unknown`；理由：宁缺勿假，审稿人会核查
- 某工具只支持固定几种靶长度 → `custom_target_length` 推荐填 `partial`
- 我方行的 `evidence` → 推荐填 `文件:行` 而不是论文
- 竞品源码不在本机 → 推荐只依据论文正文与官方文档，并在 md 中注明「未核验源码」

## 6. 轻量自检（servant 的检验上限）

```powershell
cd R:\songji\programfile
python tools\expressiveness_probe.py --json
python -c "import csv;rows=list(csv.DictReader(open(r'docs\expressiveness_matrix.tsv',encoding='utf-8'),delimiter='\t'));print(len(rows));print(rows[0]['tool'])"
```

预期：探针退出码 0 且全部能力为 true；TSV 恰好 16 行数据行 + 1 行表头，第一行 tool 为 `This work (CRISPR-Motif Workbench)`。

## 7. 交付要求

- 完成后：`state.json` 置 `ready_for_review` 并更新 `updated`，写 `report.md`
- `report.md` 必填：改动文件+行号表格、命令原文与输出原文、未做项及原因、附带发现（只记录不修）、待明确项
- 不要自己裁定「通过」；核验归 master