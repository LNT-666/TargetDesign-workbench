# 参数表达力矩阵（论文 C1 的核心证据 / Figure 3）

- 机读版本：`docs/expressiveness_matrix.tsv`（与本文件同源生成，内容一致）
- 规则来源：`docs/handoff/expr-matrix/task.md`（列 C1、取值 C2、行 C3、证据 C4）
- 本工作行自证：`tools/expressiveness_probe.py`（`--json` 汇总记录；退出码非 0 即断言失败）

## 矩阵

| tool | year | input_model | custom_pam_tam | custom_target_length | custom_orientation | middle_element_constraint | enumerates_all_occurrences | pair_side_independent | evidence |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| This work (CRISPR-Motif Workbench) | 2026 | both | yes | yes | yes | yes | yes | yes | tools/expressiveness_probe.py --json (19/19 checks); shared/design/guide_design.py:54; designer_workbench.py:705; designer_workbench.py:709; designer_workbench.py:713; designer_workbench.py:753; designer_workbench.py:769; designer_workbench.py:812; Target_xbp_Target/extract_complex_queries.py:19; Target_xbp_Target/extract_complex_queries.py:107; Target_xbp_Y_zbp_Target/extract_motifs.py:136; Target_xbp_Y_zbp_Target/extract_motifs.py:144; shared/search/iupac.py:40; unified_gui.py:603 |
| CHOPCHOP v3 | 2019 | both | yes | yes | partial | partial | yes | no | https://chopchop.cbu.uib.no/ (form: geneInput/fastaInput, nonstandardCas9, gLengthCas9, NICKASEdist1-2); DOI 10.1093/nar/gkz365 |
| CRISPOR | 2018 | both | no | partial | partial | no | yes | no | https://crispor.gi.ucsc.edu/ (textarea name="seq"; select name="pam" 为固定选项列表); DOI 10.1093/nar/gky354 |
| FlashFry | 2018 | sequence | yes | yes | yes | no | yes | no | https://github.com/mckennalab/FlashFry/blob/main/docs/nuclease-profiles.md (spacerLength/pamSide/pams); https://github.com/mckennalab/FlashFry#readme (index/discover/score/extract); DOI 10.1186/s12915-018-0545-0 |
| CRISPRitz | 2020 | both | yes | yes | yes | no | yes | no | https://github.com/pinellolab/crispritz#readme (pam/pamNGG.txt = "NNNNNNNNNNNNNNNNNNNNNGG 3"; pam/pamTTTN.txt = "TTTNNNNNNNNNNNNNNNNNNNNN -4"); DOI 10.1093/bioinformatics/btz867 |
| GuideScan2 | 2025 | both | yes | yes | yes | no | yes | no | https://github.com/pritykinlab/guidescan-cli/blob/master/manual/manual.pdf (--pam, --kmer-length, --alt-pam, --start); DOI 10.1186/s13059-025-03488-8 |
| CRISPETa | 2017 | both | no | no | no | partial | yes | no | DOI 10.1371/journal.pcbi.1005341 (Table 1: BED 输入 + du/dd/eu/ed；Methods: canonical NGG, 20mer) |
| pgRNAFinder | 2017 | both | unknown | yes | no | partial | yes | partial | DOI 10.1093/bioinformatics/btx472 (Results: gRNA 长度可选；3' PAM；paired-gRNA offset 区间；same/different/both strand) |
| GT-Scan | 2014 | coordinate | unknown | unknown | unknown | unknown | yes | unknown | DOI 10.1093/bioinformatics/btu354 (摘要；官方站点 gt-scan.braembl.org.au 已不可访问) |
| Cas-Designer | 2015 | both | no | partial | partial | unknown | yes | unknown | http://www.rgenome.net/cas-designer/ (pam_type 单选 + update_seedlen(18/20/21/22/23/24)); DOI 10.1093/bioinformatics/btv537 |
| Breaking-Cas | 2016 | sequence | yes | partial | yes | no | yes | no | http://bioinfogp.cnb.csic.es/tools/breakingcas/ (input name="PAM"; pam_pos 单选 5/3; select oligosize 18-25); DOI 10.1093/nar/gkw407 |
| EuPaGDT | 2015 | both | yes | yes | unknown | unknown | yes | unknown | DOI 10.1099/mgen.0.000033 (custom on-target PAM: IUPAC 3–10 bp; gRNA length 可自定义; identifies all possible gRNAs) |
| CaSilico | 2022 | both | no | no | no | no | yes | no | https://github.com/mrb20045/CaSilico#readme (CaSilico() 参数表); DOI 10.3389/fbioe.2022.957131 |
| crisprVerse | 2022 | both | yes | yes | yes | partial | yes | partial | https://bioconductor.org/packages/release/bioc/manuals/crisprBase/man/crisprBase.pdf (CrisprNickase 槽：pams/pam_side/spacer_length/spacer_gap/nickingStrand); https://bioconductor.org/packages/release/bioc/manuals/crisprDesign/man/crisprDesign.pdf (findSpacerPairs: x1/x2/pamOrientation/minCutLength/maxCutLength/spacer_len); DOI 10.1038/s41467-022-34320-7 |
| DECKO | 2015 | coordinate | unknown | unknown | unknown | unknown | unknown | unknown | DOI 10.1186/s12864-015-2086-z (Methods: gRNA 由 MIT CRISPR Design 工具设计，200 bp 窗口内取最高分) |
| CRISPR multitargeter | 2015 | sequence | yes | yes | yes | unknown | yes | unknown | DOI 10.1371/journal.pone.0119372 (Results: 5' 二核苷酸三选项、target 长度、PAM 所在侧、默认 NGG 或 IUPAC 自定义；regex 枚举全部位点) |

## 列定义与判定口径

- `input_model`：`coordinate` = 只接受基因组坐标/区间/基因标识；`sequence` = 只接受序列（FASTA/粘贴）；
  `both` = 两者都有官方入口。
- `custom_pam_tam`：**yes** = 可用自由输入（自由文本 / IUPAC 模式 / 可写配置文件或对象）给出任意 PAM/TAM；
  **partial** = 只能从预置酶列表中选择，或必须通过固定预设间接改变；**no** = 官方界面/文档给出固定枚举且无自定义入口；
  **unknown** = 官方文档未明确说明（宁可记 unknown，不记 no）。
- `custom_target_length`：**yes** = 任意整数长度可给定；**partial** = 仅固定列表（下拉/单选/每酶固定值）；
  **no** = 单一固定长度且无入口；**unknown** = 未明确说明。
- `custom_orientation`：**yes** = 可显式选择 PAM/TAM 相对靶点的方位（3′/5′、起始端/末端、upstream/downstream）；
  **partial** = 方位只能随预置酶间接改变（如 Cas9 3′ / Cas12a 5′）；**no** = 固定单一方位；**unknown** = 未明确说明。
- `middle_element_constraint`（C6）：设计输入是否允许指定一个**必须存在于左右靶点之间的序列元件**，
  并对**左右两侧分别给出独立距离区间**。**partial** = 可以给中间区间的距离约束，但中间是坐标区间而非序列元件，
  或左右距离不是各自独立的区间。
- `enumerates_all_occurrences`（C7）：锚点以序列 motif 给出时，是否枚举该 motif 在目标序列/基因组中的全部出现位置。
  对只接受坐标区间的工具，本表按「是否枚举该区间内全部符合条件位点（而非只返回最优位点）」判定；
  motif 锚定本身是 C1 设计空间差异，见正文（本列不区分锚点类型）。
- `pair_side_independent`（C8）：成对设计中左右两侧的 PAM/TAM、长度、方向能否各自独立设定。
  **partial** = 左右的目标区间可以各自给定，但 PAM/长度/方向在成对级别统一。
- `evidence`：论文 DOI、官方文档 URL 或源码 `文件:行`；无处可查时该格记 `unknown`。
- 竞品能力**只依据论文正文与官方文档/公开仓库**推断，未运行任何竞品工具、未安装其依赖；
  对只核验到论文摘要或站点不可访问的工具，已在「逐行说明」中注明（未核验源码）。

## 我方行锚点清单（由探针在运行期重新定位）

- `input_model`（序列输入 / 坐标输入）：`shared/design/guide_design.py:54`、`unified_gui.py:603`、`tools/search_indexed.py:36`
- `custom_pam_tam`（任意 PAM/TAM（含 IUPAC））：`shared/design/guide_design.py:54`、`shared/search/iupac.py:40`、`designer_workbench.py:705`、`shared/search/iupac.py:33`、`shared/design/pattern_spec.py:19`
- `custom_target_length`（任意靶长度）：`shared/design/guide_design.py:54`、`designer_workbench.py:709`
- `custom_orientation`（任意方向 / PAM 侧）：`shared/design/guide_design.py:54`、`tools/search_indexed.py:36`、`designer_workbench.py:713`
- `middle_element_constraint`（中间元件 + 左右独立距离区间）：`designer_workbench.py:769`、`designer_workbench.py:753`、`designer_workbench.py:812`、`Target_xbp_Target/extract_complex_queries.py:39`、`Target_xbp_Target/extract_complex_queries.py:107`、`Target_xbp_Y_zbp_Target/extract_motifs.py:136`、`Target_xbp_Y_zbp_Target/extract_motifs.py:137`、`Target_xbp_Y_zbp_Target/extract_motifs.py:144`、`Target_xbp_Y_zbp_Target/extract_motifs.py:145`
- `enumerates_all_occurrences`（枚举全部出现位置）：`shared/search/iupac.py:40`、`shared/search/iupac.py:33`、`shared/design/guide_design.py:54`
- `pair_side_independent`（左右两侧独立设定）：`Target_xbp_Target/extract_complex_queries.py:91`、`Target_xbp_Target/extract_complex_queries.py:42`、`designer_workbench.py:753`、`designer_workbench.py:812`、`shared/design/guide_design.py:71`

## 如何复现

```powershell
cd R:\songji\programfile
python tools\expressiveness_probe.py
python tools\expressiveness_probe.py --json
```

退出码 `0` 表示全部断言通过；`--json` 记录的键名即本表列名。探针在本机 Python 3.14.7 上的实际输出：

```text
[PASS] anchors_present              missing anchors: none
[PASS] pair_helpers_loaded          flank_interval=Target_xbp_Target\extract_complex_queries.py:19 get_flank=Target_xbp_Target\extract_complex_queries.py:30
[PASS] sequence_and_coordinate_input raw sequence input -> 2 guide(s); coordinate-input anchors -> ['unified_gui.py:603', 'tools/search_indexed.py:36']
[PASS] iupac_pam_VNG                pam=VNG hits=2 (reference 2, expected 2) [('+', 0, 20, 'CAG'), ('-', 1, 21, 'ACG')]
[PASS] iupac_pam_NNGRRT             pam=NNGRRT hits=1 (reference 1, expected 1) [('+', 0, 20, 'AAGAAT')]
[PASS] iupac_alphabet               reference IUPAC table covers ACGTUNRYSWKMBDHV; expanded: ['ACGACGTG', 'ACGTACGTGAGAGT', 'ACGTGG', 'TTTACG']
[PASS] tttv_3prime                  pam=TTTV side=3prime hits=[('+', 4, 24, 'TTTA')] (same PAM on the opposite side: [])
[PASS] tttv_5prime                  pam=TTTV side=5prime hits=[('+', 7, 27, 'TTTA')] (same PAM on the opposite side: [])
[PASS] non_ngg_pam                  TTTV (non-NGG) accepted: [('+', 4, 24, 'TTTA')]
[PASS] spacer_len_18                spacer_len=18 hits=1 widths=[18] (reference 1)
[PASS] spacer_len_20                spacer_len=20 hits=1 widths=[20] (reference 1)
[PASS] spacer_len_23                spacer_len=23 hits=1 widths=[23] (reference 1)
[PASS] strand_switch                allow_reverse=False -> ['+']; allow_reverse=True -> ['+', '-']
[PASS] iupac_all_positions          TTAT in 23 nt probe -> [2, 8, 14, 17]; overlapping probe -> [0, 3]
[PASS] guides_all_sites             NGG sites on a 4-block sequence: production=4 reference=4 strands=['+', '-']
[PASS] four_strand_combos           strand combinations found: [('minus', 'minus'), ('minus', 'plus'), ('plus', 'minus'), ('plus', 'plus')]
[PASS] gap_window_enforced          gaps inside [5, 7]: [6]
[PASS] gap_window_rejects           gaps inside [100, 200]: []
[PASS] independent_length_and_side  left upstream/4 -> (4, 8) 'GAGA'; right downstream/7 -> (11, 18) 'TGAGAGA'; strand flips side

anchor gui.bed_regions              unified_gui.py:603
anchor guide_design.allow_reverse   shared/design/guide_design.py:71
anchor guide_design.find_guides     shared/design/guide_design.py:54
anchor guide_design.free_input      shared/design/guide_design.py:5
anchor iupac.matches                shared/search/iupac.py:33
anchor iupac.positions              shared/search/iupac.py:40
anchor motifs.max_left              Target_xbp_Y_zbp_Target/extract_motifs.py:136
anchor motifs.max_right             Target_xbp_Y_zbp_Target/extract_motifs.py:137
anchor motifs.min_left              Target_xbp_Y_zbp_Target/extract_motifs.py:144
anchor motifs.min_right             Target_xbp_Y_zbp_Target/extract_motifs.py:145
anchor pattern_spec.iupac_bases     shared/design/pattern_spec.py:19
anchor queries.four_strands_doc     Target_xbp_Target/extract_complex_queries.py:42
anchor queries.gap_args             Target_xbp_Target/extract_complex_queries.py:39
anchor queries.independent_columns  Target_xbp_Target/extract_complex_queries.py:91
anchor queries.strand_combos        Target_xbp_Target/extract_complex_queries.py:107
anchor search_indexed.pam_side      tools/search_indexed.py:36
anchor workbench.left_distance      designer_workbench.py:753
anchor workbench.middle_motif       designer_workbench.py:769
anchor workbench.pam_tam            designer_workbench.py:705
anchor workbench.right_distance     designer_workbench.py:812
anchor workbench.target_length      designer_workbench.py:709
anchor workbench.target_position    designer_workbench.py:713

capabilities: custom_pam_tam=True, custom_target_length=True, custom_orientation=True, middle_element_constraint=True, enumerates_all_occurrences=True, pair_side_independent=True
19/19 checks passed
```

汇总记录（截取）：

```text
python tools/expressiveness_probe.py --json   # 退出码 0
{"tool": "This work (CRISPR-Motif Workbench)", "year": "2026", "input_model": "both", "custom_pam_tam": true, "custom_target_length": true, "custom_orientation": true, "middle_element_constraint": true, "enumerates_all_occurrences": true, "pair_side_independent": true, "ok": true, "checks_passed": 19, "checks_total": 19}
```

## 逐行说明（补充，非矩阵列）

- **This work (CRISPR-Motif Workbench)**（2026）：全部七列由 tools/expressiveness_probe.py 在真实代码路径上逐项断言（19/19 通过），锚点见下方「我方行锚点清单」。
- **CHOPCHOP v3**（2019）：Custom PAM 文本框（nonstandardCas9/nonstandardCpf1，示例占位 e.g. NGAG）；sgRNA 长度数字输入 14–30（gLengthCas9）；nickase 面板有单一「Distance between guides: 10 to 31」区间，但左右共用一组 PAM 单选与一个长度输入。PAM 侧随酶选择隐含（Cas9 为 PAM-3'，Cpf1/Cas12a 为 5'）。
- **CRISPOR**（2018）：PAM 只能从固定 select 中选择（38 个选项，含 20bp-NGG、TTTV-23bp、NGG-22bp 等），没有自由文本入口；靶长度只能随选项预设改变（如 NGG-22bp / TTTV-23bp），不能独立设定；序列输入框同时接受染色体区间（chr1:11,130,540-11,130,751）。表单无成对设计入口（页面全文检索无 nickase/pair 字段）。
- **FlashFry**（2018）：自定义能力通过 nuclease profile（Java properties 文件）表达：spacerLength、pamSide=3prime/5prime、pams（等宽 IUPAC，允许 A C G T R Y K M S W B D H V N），由 `index --profileFile` 建库；文档说明「每个数据库只有一种固定 target geometry」，即参数在建库期确定而非每次运行自由给定。输入为参考基因组 FASTA 与目标序列 FASTA；未在官方 README 中发现坐标区间输入或成对设计。
- **CRISPRitz**（2020）：PAM 以文本文件给出：N 的个数即 guide 长度，末尾数字给出 PAM 长度与方向（正数 3'、负数 5'，如 -4），因此 PAM 序列（IUPAC）、靶长度、方向三者都可自定义。
- **GuideScan2**（2025）：manual.pdf：`--pam`/`--kmer-length`（默认 NGG 与 20），`--alt-pam` 可给逗号分隔的多个 PAM；`--start` 指定 PAM 位于 protospacer 的起始端或末端（默认末端，即 3'）。
- **CRISPETa**（2017）：Table 1 的用户参数含上游/下游设计区（du/dd）与上游/下游排除区（eu/ed），左右两侧搜索窗口可独立设定；但 PAM 固定为 canonical NGG、protospacer 固定 20 nt（Methods: 搜索 NNNN[20nt]NGGNNN），中间约束是被删除的基因组 BED 区间（坐标）而不是序列元件，故 middle_element_constraint 记 partial。
- **pgRNAFinder**（2017）：「users can set the length of gRNA as an optional argument in the website」；成对模式给出 offset 区间（短距离默认 -2..32 bp，长距离默认 200–5 kbp、最大距离 1 Mb 可设），但中间不是序列元件；链向可以选 same/different/both（pair 级），PAM 与长度两侧共用。论文只说明按 3' PAM 搜索，未说明可否自定义 PAM，故该格记 unknown。
- **GT-Scan**（2014）：摘要：「ranks all potential targets in a user-selected region of a genome」，并允许用 'target rule' 定义靶点/脱靶特征；论文非开放获取、站点不可访问，故只核验到摘要，其余各格记 unknown（未核验源码）。
- **Cas-Designer**（2015）：PAM 只能从固定单选列表挑选（SpCas9 NGG、StCas9 NNAGAAW、CjCas9 NNNVRYAC、AsCpf1 TTTN/TTTV 等），无自由文本入口；每种酶对应固定 seed 长度（update_seedlen），故长度记 partial；PAM 侧随酶选择隐含，记 partial。成对设计在该页面无入口，但未核验站点是否另有成对工具页，故 middle/pair 两格记 unknown。
- **Breaking-Cas**（2016）：表单有自由文本 PAM 输入（help 原文：write a different PAM sequence (in IUPAC notation)）、PAM 位置单选（pam_pos=5/3）、oligosize 下拉 18–25 nt（固定列表，故长度记 partial）。论文：The flexibility to customize the PAM motif sequence and its position relative to the guide oligonucleotide (5' or 3')。
- **EuPaGDT**（2015）：论文：「users can specify multiple, custom on-target PAMs ... using the standard IUPAC code to specify degenerate PAM(s) of 3–10 bp」；「EuPaGDT provides other customized parameters such as gRNA length」，故长度记 yes。方向与成对相关格在论文中无明确说明，记 unknown（官方站点为 JS 应用，本轮未能抓取到界面源码）。
- **CaSilico**（2022）：README 给出完整参数表：TargetFasta/TargetAccession/TargetCoordinate(染色体/起止/链/物种)、CrisprTypes、ConservationMethod、ConservationThreshold、OffTarget/Organism/Local*。文档化的参数里没有 PAM、长度或方向入口（PAM/PFS 由内置的 CRISPR 类型规则表决定），也没有成对设计入口。
- **crisprVerse**（2022）：crisprBase 的 CrisprNuclease/CrisprNickase 槽位可直接给出 IUPAC PAM（pams）、PAM 侧（pam_side=3prime/5prime）、spacer 长度（spacer_length）与 spacer 间距（spacer_gap）；crisprDesign::findSpacerPairs 支持两个独立序列空间 x1/x2、minCutLength/maxCutLength 双切点距离区间、pamOrientation(all/out/in)、spacer_len 覆盖。中间约束只是距离区间而非序列元件，故记 partial；每侧可传各自的 GuideSet，但成对约束在 pair 级统一施加，故 pair 记 partial。
- **DECKO**（2015）：DECKO 是单寡核苷酸双 CRISPR 删除的克隆/协议策略而非设计软件：Methods 明确「gRNA sequences were designed with the CRISPR Design tool from MIT (http://crispr.mit.edu/)」，本文没有给出自身可配置的 PAM/长度/方向参数空间，故各能力格记 unknown（未核验其配套模板）。
- **CRISPR multitargeter**（2015）：论文原文：「the user needs to specify the 5' dinucleotide by choosing from three options ("NN", "GN", "GG"), the length of the target, and from which side the PAM sequence is located for that particular CRISPR/Cas system. The user can either choose the default "NGG" PAM sequence or specify it using standard nucleic acid alphabet characters.」成对（nickase）模式的间距参数未在正文说明，故 middle/pair 记 unknown。

## 证据来源（P1-1）

格式：`工具 — 来源 — 支撑哪几列`

- This work (CRISPR-Motif Workbench) — tools/expressiveness_probe.py --json (19/19 checks); shared/design/guide_design.py:54; designer_workbench.py:705; designer_workbench.py:709; designer_workbench.py:713; designer_workbench.py:753; designer_workbench.py:769; designer_workbench.py:812; Target_xbp_Target/extract_complex_queries.py:19; Target_xbp_Target/extract_complex_queries.py:107; Target_xbp_Y_zbp_Target/extract_motifs.py:136; Target_xbp_Y_zbp_Target/extract_motifs.py:144; shared/search/iupac.py:40; unified_gui.py:603 — 支撑列：input_model、custom_pam_tam、custom_target_length、custom_orientation、middle_element_constraint、enumerates_all_occurrences、pair_side_independent
- CHOPCHOP v3 — https://chopchop.cbu.uib.no/ (form: geneInput/fastaInput, nonstandardCas9, gLengthCas9, NICKASEdist1-2); DOI 10.1093/nar/gkz365 — 支撑列：input_model、custom_pam_tam、custom_target_length、custom_orientation、middle_element_constraint、enumerates_all_occurrences、pair_side_independent
- CRISPOR — https://crispor.gi.ucsc.edu/ (textarea name="seq"; select name="pam" 为固定选项列表); DOI 10.1093/nar/gky354 — 支撑列：input_model、custom_pam_tam、custom_target_length、custom_orientation、middle_element_constraint、enumerates_all_occurrences、pair_side_independent
- FlashFry — https://github.com/mckennalab/FlashFry/blob/main/docs/nuclease-profiles.md (spacerLength/pamSide/pams); https://github.com/mckennalab/FlashFry#readme (index/discover/score/extract); DOI 10.1186/s12915-018-0545-0 — 支撑列：input_model、custom_pam_tam、custom_target_length、custom_orientation、middle_element_constraint、enumerates_all_occurrences、pair_side_independent
- CRISPRitz — https://github.com/pinellolab/crispritz#readme (pam/pamNGG.txt = "NNNNNNNNNNNNNNNNNNNNNGG 3"; pam/pamTTTN.txt = "TTTNNNNNNNNNNNNNNNNNNNNN -4"); DOI 10.1093/bioinformatics/btz867 — 支撑列：input_model、custom_pam_tam、custom_target_length、custom_orientation、middle_element_constraint、enumerates_all_occurrences、pair_side_independent
- GuideScan2 — https://github.com/pritykinlab/guidescan-cli/blob/master/manual/manual.pdf (--pam, --kmer-length, --alt-pam, --start); DOI 10.1186/s13059-025-03488-8 — 支撑列：input_model、custom_pam_tam、custom_target_length、custom_orientation、middle_element_constraint、enumerates_all_occurrences、pair_side_independent
- CRISPETa — DOI 10.1371/journal.pcbi.1005341 (Table 1: BED 输入 + du/dd/eu/ed；Methods: canonical NGG, 20mer) — 支撑列：input_model、custom_pam_tam、custom_target_length、custom_orientation、middle_element_constraint、enumerates_all_occurrences、pair_side_independent
- pgRNAFinder — DOI 10.1093/bioinformatics/btx472 (Results: gRNA 长度可选；3' PAM；paired-gRNA offset 区间；same/different/both strand) — 支撑列：input_model、custom_pam_tam、custom_target_length、custom_orientation、middle_element_constraint、enumerates_all_occurrences、pair_side_independent
- GT-Scan — DOI 10.1093/bioinformatics/btu354 (摘要；官方站点 gt-scan.braembl.org.au 已不可访问) — 支撑列：input_model、custom_pam_tam、custom_target_length、custom_orientation、middle_element_constraint、enumerates_all_occurrences、pair_side_independent
- Cas-Designer — http://www.rgenome.net/cas-designer/ (pam_type 单选 + update_seedlen(18/20/21/22/23/24)); DOI 10.1093/bioinformatics/btv537 — 支撑列：input_model、custom_pam_tam、custom_target_length、custom_orientation、middle_element_constraint、enumerates_all_occurrences、pair_side_independent
- Breaking-Cas — http://bioinfogp.cnb.csic.es/tools/breakingcas/ (input name="PAM"; pam_pos 单选 5/3; select oligosize 18-25); DOI 10.1093/nar/gkw407 — 支撑列：input_model、custom_pam_tam、custom_target_length、custom_orientation、middle_element_constraint、enumerates_all_occurrences、pair_side_independent
- EuPaGDT — DOI 10.1099/mgen.0.000033 (custom on-target PAM: IUPAC 3–10 bp; gRNA length 可自定义; identifies all possible gRNAs) — 支撑列：input_model、custom_pam_tam、custom_target_length、custom_orientation、middle_element_constraint、enumerates_all_occurrences、pair_side_independent
- CaSilico — https://github.com/mrb20045/CaSilico#readme (CaSilico() 参数表); DOI 10.3389/fbioe.2022.957131 — 支撑列：input_model、custom_pam_tam、custom_target_length、custom_orientation、middle_element_constraint、enumerates_all_occurrences、pair_side_independent
- crisprVerse — https://bioconductor.org/packages/release/bioc/manuals/crisprBase/man/crisprBase.pdf (CrisprNickase 槽：pams/pam_side/spacer_length/spacer_gap/nickingStrand); https://bioconductor.org/packages/release/bioc/manuals/crisprDesign/man/crisprDesign.pdf (findSpacerPairs: x1/x2/pamOrientation/minCutLength/maxCutLength/spacer_len); DOI 10.1038/s41467-022-34320-7 — 支撑列：input_model、custom_pam_tam、custom_target_length、custom_orientation、middle_element_constraint、enumerates_all_occurrences、pair_side_independent
- DECKO — DOI 10.1186/s12864-015-2086-z (Methods: gRNA 由 MIT CRISPR Design 工具设计，200 bp 窗口内取最高分) — 支撑列：input_model、custom_pam_tam、custom_target_length、custom_orientation、middle_element_constraint、enumerates_all_occurrences、pair_side_independent
- CRISPR multitargeter — DOI 10.1371/journal.pone.0119372 (Results: 5' 二核苷酸三选项、target 长度、PAM 所在侧、默认 NGG 或 IUPAC 自定义；regex 枚举全部位点) — 支撑列：input_model、custom_pam_tam、custom_target_length、custom_orientation、middle_element_constraint、enumerates_all_occurrences、pair_side_independent

（核验时间 2026-09-19；竞品信息取自其论文/官方文档/公开仓库，未运行竞品工具；只核验到摘要或站点不可访问的工具已在逐行说明中标注。）
