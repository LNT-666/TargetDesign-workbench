import pathlib
p = pathlib.Path(r"R:\songji\programfile\docs\handoff\manuscript-v2\task.md")
t = p.read_text(encoding="utf-8")
old = "P0-4 `docs/FIGURE_TABLE_PLAN.md`：`:`18`、`:`20`、`:`32`、`:`44`、`:`77` 改为"
new = "P0-4 `docs/FIGURE_TABLE_PLAN.md`：`:18`、`:20`、`:32`、`:44`、`:77` 改为"
assert old in t, "pattern not found"
p.write_text(t.replace(old, new), encoding="utf-8", newline="\n")
print("fixed line:")
for i,l in enumerate(p.read_text(encoding="utf-8").splitlines(),1):
    if l.startswith("P0-4"): print(i, l[:150])