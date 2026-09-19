import io

p = r"R:\songji\programfile\docs\handoff\nar-format-pack\task.md"
d = io.open(p, encoding="utf-8").read()
lines = d.split("\n")
log = []

def find(sub, start=0):
    for i in range(start, len(lines)):
        if sub in lines[i]:
            return i
    raise SystemExit("ANCHOR NOT FOUND: " + sub)

i = find("- 上位文档：")
lines[i:i + 1] = [
 "- 上位文档：`docs/PAPER_OUTLINE.md` 第九节（格式规范）+ `docs/ALLEGRO_REFERENCE_ANALYSIS.md`",
 "- 格式范本（两篇，均为 NAR Methods 在线专发）：",
 "  - 主范本 ALLEGRO，NAR 2025, 53, gkaf783, doi:10.1093/nar/gkaf783",
 "    （抽取文本 `R:/songji/论文/3/ALLEGRO-2025-nar.txt`，99690 字节）",
 "  - 副范本 CRISPR-COPIES，NAR 2024, 52, e30, doi:10.1093/nar/gkae062",
 "    （`R:/songji/论文/3/gkae062.pdf`，17 页）",
]
log.append("header: format models (+)")

a = find("背景：格式范本已确定")
b = find("第九节已记录其量化规范", a)
lines[a:b + 1] = [
 "背景：格式范本为**两篇 NAR Methods 专发论文**：主范本 **ALLEGRO**（NAR 2025, 53, gkaf783，",
 "doi:10.1093/nar/gkaf783；摘要 173 词、主文 Figure 1-5、无主文表、含 Graphical abstract）、",
 "副范本 **CRISPR-COPIES**（NAR 2024, 52, e30；摘要 206 词、17 页、无主文表）。",
 "两篇在摘要长度与 back matter 顺序上略有差异，本任务一律按下面的 C1/C2 执行，不要自行取中。",
 "`docs/PAPER_OUTLINE.md` 第九节与 `docs/ALLEGRO_REFERENCE_ANALYSIS.md` 已记录全部量化规范。",
]
log.append("background paragraph: two models")

a = find("C2  Back matter")
b = find("并在 NAR_FORMAT_CHECKLIST.md 登记为待补项，不得编造", a)
lines[a:b + 1] = [
 "C2  Back matter 段落与顺序（采用 2025 主范本 ALLEGRO 的顺序）：",
 "    Acknowledgements（须含一行 `Author contributions:`）| Supplementary data |",
 "    Conflict of interest | Funding | Data availability",
 "    - 注：2024 副范本顺序为 Data availability 在前、Acknowledgements 在后；NAR 两种都接受，",
 "      本次统一按 2025 顺序书写，并在 NAR_FORMAT_CHECKLIST.md 里注明这一选择",
 "    - Data availability 基准句式（2025 主范本，仓库+DOI 式，未定项写 [TO FILL]）：",
 "      `<工具名> is freely available on GitHub at [TO FILL repository URL] and on`",
 "      `Zenodo at [TO FILL version DOI]. Documentation is provided on the project wiki.`",
 "      `All data used in this study can be obtained from the repository and the`",
 "      `Supplementary Data.`",
 "    - Supplementary data 基准句式（2025 主范本）：`Supplementary data is available at NAR online.`",
 "      （2024 副范本写法 `Supplementary Data are available at NAR Online.` 同样被接受；两者不得混用）",
 "    - Acknowledgements 必须含 `Author contributions:` 段，按 CRediT 角色逐位写",
 "      （Conceptualization / Software / Methodology / Validation / Writing - original draft /",
 "      Writing - review and editing 等）；作者信息未定时整段写 [TO FILL]",
 "    - 凡本项目尚未确定的信息（作者、单位、基金号、仓库 URL、DOI）一律写 [TO FILL]，",
 "      并在 NAR_FORMAT_CHECKLIST.md 登记为待补项，不得编造",
 "    - 数学表述（如种子计划代价方程）按 2025 主范本惯例放 Supplementary Notes，主文只留结论与引用",
]
log.append("C2 back matter: 2025 order + author contributions + repo DOI")

a = find("主文表 <= 2 张")
lines[a] = "    - 主文表 = 0（两篇范本均无主文表）；确有需要时最多 1 张，其余一律进 Supplementary"
log.append("C3 main tables: 0")

a = find("参考文已抽取")
lines[a:a] = [
 "- 主范本已抽取：`R:/songji/论文/3/ALLEGRO-2025-nar.txt`（99690 字节，`pdftotext -layout -enc UTF-8`）",
 "  统计：摘要 173 词；主文 Figure 1-5；Supplementary Fig S1-S10；正文无 Table 引用（表一律 Sn）；",
 "  有 Graphical abstract；back matter 顺序 = Acknowledgements(含 Author contributions) ->",
 "  Supplementary data -> Conflict of interest -> Funding -> Data availability -> References",
]
log.append("evidence: ALLEGRO stats (+)")

a = find("print([(f,os.path.exists(os.path.join('docs',f))) for f in fs])")
lines[a + 1:a + 1] = [
 "python -c \"import os;print('allegro_txt', os.path.exists(r'R:/songji/论文/3/ALLEGRO-2025-nar.txt'))\"",
]
log.append("self-check: allegro txt (+)")

out = "\n".join(lines)
n1 = out.count("180-250")
n2 = out.count("180<=w<=250")
out = out.replace("180-250", "170-250").replace("180<=w<=250", "170<=w<=250")
io.open(p, "w", encoding="utf-8", newline="\n").write(out)
print("\n".join(log))
print("range replacements: 180-250 x%d, 180<=w<=250 x%d" % (n1, n2))
print("chars %d -> %d" % (len(d), len(out)))