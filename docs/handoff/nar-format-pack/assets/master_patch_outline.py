import io, sys

p = r"R:\songji\programfile\docs\PAPER_OUTLINE.md"
d = io.open(p, encoding="utf-8").read()
lines = d.split("\n")

def find(sub, start=0):
    for i in range(start, len(lines)):
        if sub in lines[i]:
            return i
    raise SystemExit("ANCHOR NOT FOUND: " + sub)

log = []

i = find("10.1093/nar/gkae062")
rows = [
 "| ALLEGRO | NAR 2025, 53, gkaf783 - 10.1093/nar/gkaf783 | 跨物种最小 guide 文库（ILP 集合覆盖）；用户可选 track（any/each）× 倍数 m；候选削减「不影响最优性」 |",
 "| MINORg | NAR 2023, 51, e43 - 10.1093/nar/gkad142 | 每个输入序列求最小 guide 集以覆盖多靶标（ALLEGRO 视其为该问题当时最强基线） |",
 "| CRISPys | J Mol Biol 2018, 430, 2184-95 - 10.1016/j.jmb.2018.03.019 | 基因家族多成员编辑的最优 sgRNA 设计 |",
 "| multicrispr | Life Sci Alliance 2020, 3, e202000757 - 10.26508/lsa.202000757 | 单基因组内多重编辑 / prime editing 的 gRNA 设计（可上千靶标） |",
]
lines[i + 1:i + 1] = rows
log.append("precedent rows: +4 after line " + str(i + 1))

j = find("### 2.2 ")
block = [
 "",
 "**ALLEGRO（NAR 2025, gkaf783）单独说明（2026-09-19 增补）**",
 "",
 "它把「用最少的 guide 覆盖多物种的一组基因」建模为集合覆盖问题并用整数线性规划求解，与本项目同属",
 "「设计规模与布局」这一大类；但它以物种集合与基因/直系同源组为输入，不涉及 motif 锚定、多元件间距、",
 "PAM/TAM 自由输入或脱靶索引。有两点必须落到论文里：",
 "",
 "1. 它用 **track（A = any / E = each）× 倍数 m** 提供「用户可选的设计策略」。因此「本工具提供多种设计模式」",
 "   这件事本身不新 —— 我们的新颖性只能落在**布局语义**（以 IUPAC motif 的基因组出现为锚 + 每侧独立距离",
 "   区间 + Y 序列约束），不能落在「我们有两个模式」这个说法上。",
 "2. 它的 Discussion 明确写：非 Cas9 效应子（如 Cas12a）的 PAM 识别需要另行定制 PAM 约束",
 "   （`R:/songji/论文/3/ALLEGRO-2025-nar.txt:662-665`）。这是「参数化 PAM/TAM 是尚未被满足的需求」",
 "   最有力的外部佐证，Introduction 缺口段 (a) 应直接引用它，而不是只由我们自述。",
 "",
 "完整分析见 `docs/ALLEGRO_REFERENCE_ANALYSIS.md`。",
 "",
]
lines[j:j] = block
log.append("2.1 ALLEGRO note: +%d lines before line %d" % (len(block), j + 1))

k = find("Our tool is the first to allow custom PAM/TAM input.")
extra = [
 "> Our tool is the first to provide multiple user-selectable design strategies.",
 "> Our approach is the first to reduce candidate enumeration without loss.",
 "",
 "（后两句已被 ALLEGRO 2025 推翻：它的 track 机制与「不影响最优性」的候选削减都构成先例；",
 "详见 `docs/ALLEGRO_REFERENCE_ANALYSIS.md` 第 3、5 节。）",
]
lines[k + 1:k + 1] = extra
log.append("2.3 forbidden phrasings: +%d lines after line %d" % (len(extra), k + 1))

h = find("## 九、格式规范")
old_head = lines[h]
lines[h] = ("## 九、格式规范（双范本：ALLEGRO NAR 2025 53 gkaf783 为主范本，"
            "CRISPR-COPIES NAR 2024 52 e30 为副范本）")
log.append("9 heading: " + old_head + "  ->  " + lines[h])

s = find("gkae062.pdf")
src = [
 "- 主范本：ALLEGRO（NAR 2025, 53, gkaf783, doi:10.1093/nar/gkaf783, 栏目 Methods），抽取文本",
 "  `R:/songji/论文/3/ALLEGRO-2025-nar.txt`；量化数据为本文档 2026-09-19 用 `pdftotext -layout -enc UTF-8` 统计所得。",
]
lines[s:s] = src
log.append("9 source block: +%d lines before line %d" % (len(src), s + 1))

b = find("BioRender")
tbl = [
 "",
 "#### 9.0.1 2025 主范本（ALLEGRO）增量对照",
 "",
 "| 项目 | 2025 主范本 | 2024 副范本 | 本项目的处置 |",
 "| --- | --- | --- | --- |",
 "| 摘要词数 | 173 词 | 206 词 | 区间放宽为 **170-250 词** |",
 "| 主文图 | Figure 1-5 | 19 处 Figure 引用 | 主文 5-6 张可行，其余进 Supplementary |",
 "| 主文表 | 无（表一律 Supplementary Table Sn） | 无 | 维持主文不加表 |",
 "| Back matter 顺序 | Acknowledgements（含 Author contributions:） -> Supplementary data -> Conflict of interest -> Funding -> Data availability -> References | Data availability -> Supplementary data -> Acknowledgements -> Funding -> Conflict of interest | **改用 2025 顺序**；Back matter 需增 Author contributions 段 |",
 "| Supplementary data 句式 | `Supplementary data is available at NAR online.` | `Supplementary Data are available at NAR Online.` | 以 2025 句式为主，两种都被接受 |",
 "| Data availability 写法 | 仓库 URL + Zenodo DOI + 文档地址 + NCBI accession | 通用句式（within the article and its Supplementary Data files...） | 采用 2025 写法：仓库 URL + 版本 DOI + 文档；未定项写 [TO FILL] |",
 "| 数学表述位置 | 详细数学放 **Supplementary Notes** | 无此惯例 | 支持把「源码对照说明」移入 Supplementary note 的裁定 |",
 "| 竞品比较 | 与 MINORg 比文库大小 / RAM / 时间 | 与既有工具比 | 与 engine-bench 任务的基准曲线同级做法 |",
]
lines[b + 1:b + 1] = tbl
log.append("9.0.1 table: +%d lines after line %d" % (len(tbl), b + 1))

d2 = "\n".join(lines)
n_before = d2.count("180-250")
d2 = d2.replace("180-250", "170-250")
log.append("abstract range: replaced %d occurrence(s) of 180-250" % n_before)

io.open(p, "w", encoding="utf-8", newline="\n").write(d2)
print("\n".join(log))
print("chars %d -> %d" % (len(d), len(d2)))