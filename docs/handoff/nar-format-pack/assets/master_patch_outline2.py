import io, re

op = r"R:\songji\programfile\docs\PAPER_OUTLINE.md"
we = r"R:\songji\programfile\docs\PAPER_OUTLINE_WITH_EXPERIMENTS.md"

d = io.open(op, encoding="utf-8").read()
sec = d[d.index("### 2.1"):d.index("### 2.2")]
rows = [l for l in sec.split("\n") if l.startswith("| ") and "---" not in l]
print("2.1 table rows (incl header):", len(rows), "-> data rows:", len(rows) - 1)

d = d.replace("### Abstract（NAR 惯例：单段，不分区；参考文 206 词，目标 170-250 词）",
              "### Abstract（NAR 惯例：单段，不分区；实测 2024 副范本 206 词、2025 主范本 173 词；目标 170-250 词，硬上限 250）")
io.open(op, "w", encoding="utf-8", newline="\n").write(d)
print("outline: abstract heading updated")

w = io.open(we, encoding="utf-8").read()
before = w
w = w.replace("- 第二节 新颖性边界与措辞规范（15 篇先例表 + 5 条未找到先例 + 措辞对照）",
              "- 第二节 新颖性边界与措辞规范（20 篇先例表 + 5 条未找到先例 + 措辞对照）")
w = w.replace("- 第九节 格式规范（参考 CRISPR-COPIES, NAR 2024, 52, e30）",
              "- 第九节 格式规范（双范本：ALLEGRO NAR 2025 53 gkaf783 为主，CRISPR-COPIES NAR 2024 52 e30 为副）")
if w == before:
    print("WARN: with-experiments doc unchanged (anchors not matched)")
else:
    io.open(we, "w", encoding="utf-8", newline="\n").write(w)
    print("with-experiments: 2 pointers updated; chars %d -> %d" % (len(before), len(w)))