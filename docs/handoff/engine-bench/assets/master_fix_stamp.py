import pathlib
repo = pathlib.Path(r"R:\songji\programfile")
fixes = [
    (repo/"docs/handoff/engine-bench/review.md", "## 5. 遗留项结清（2026-09-19 15:00）", "## 5. 遗留项结清（2026-09-19 14:43）"),
    (repo/"docs/handoff/engine-bench/state.json", '"updated": "2026-09-19 15:00"', '"updated": "2026-09-19 14:43"'),
]
for p, old, new in fixes:
    t = p.read_text(encoding="utf-8")
    if old not in t:
        print("SKIP (pattern absent):", p.name)
        continue
    p.write_text(t.replace(old, new), encoding="utf-8", newline="\n")
    print("fixed", p.name, "->", new, "| remaining 15:00 =", p.read_text(encoding="utf-8").count("15:00"))