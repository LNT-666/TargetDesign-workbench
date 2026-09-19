import io

p = r"R:\songji\programfile\docs\PAPER_OUTLINE.md"
lines = io.open(p, encoding="utf-8").read().split("\n")

stray_idx = [i for i, l in enumerate(lines) if l.startswith("| ALLEGRO | NAR 2025, 53, gkaf783 -")]
assert len(stray_idx) == 1, stray_idx
i = stray_idx[0]
removed = lines[i:i + 4]
expect = ["| ALLEGRO |", "| MINORg |", "| CRISPys |", "| multicrispr |"]
for line, tag in zip(removed, expect):
    assert line.startswith(tag), (tag, line)
del lines[i:i + 4]
print("removed %d stray lines at %d" % (len(removed), i + 1))

target = [j for j, l in enumerate(lines) if l.startswith("| CRISPR-COPIES |")]
assert len(target) == 1, target
j = target[0]
print("table anchor line %d: %s" % (j + 1, lines[j][:60]))

rows = [
 "| ALLEGRO | NAR 2025, 53, gkaf783 · 10.1093/nar/gkaf783 | 跨物种最小 guide 文库（ILP 集合覆盖）；用户可选 track（any/each）× 倍数 m；候选削减「不影响最优性」 |",
 "| MINORg | NAR 2023, 51, e43 · 10.1093/nar/gkad142 | 每个输入序列求最小 guide 集以覆盖多靶标（ALLEGRO 视其为该问题当时最强基线） |",
 "| CRISPys | J Mol Biol 2018, 430, 2184-95 · 10.1016/j.jmb.2018.03.019 | 基因家族多成员编辑的最优 sgRNA 设计 |",
 "| multicrispr | Life Sci Alliance 2020, 3, e202000757 · 10.26508/lsa.202000757 | 单基因组内多重编辑 / prime editing 的 gRNA 设计（可上千靶标） |",
]
lines[j + 1:j + 1] = rows
print("inserted %d rows after table line %d" % (len(rows), j + 1))

out = "\n".join(lines)
io.open(p, "w", encoding="utf-8", newline="\n").write(out)
print("chars", len(out))