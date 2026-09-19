#!/usr/bin/env python3
"""Round-2 self-check probe for the `manuscript-v1` handoff (servant side).

Run from the repository root:

    python docs/handoff/manuscript-v1/assets/servant_round2_selfcheck.py

Checks
  A  D1  docs/SEED_PLAN_ANALYSIS.md section-2 grid vs docs/seed_plan_sweep.json
  B  D1  the hit-growth prose line vs the same JSON
  C  D2  every [path:...] anchor in the six draft documents resolves to a real file,
         and every numeric [path:line] anchor lies inside that file
  D  C2  forbidden words (first/never/unprecedented and the three CJK terms)
  E      encoding/structure of every touched document (BOM, CR, U+FFFD)
  F      abstract word count, reference coverage [1]-[30], DOI presence

Exit status is 0 only when every check passes.
"""

import io
import json
import os
import re
import sys

FAILS = []


def check(label, ok, detail=""):
    if not ok:
        FAILS.append(label)
    print(("PASS  " if ok else "FAIL  ") + label + (("   " + detail) if detail else ""))


FILES = [
    "docs/SEED_PLAN_ANALYSIS.md",
    "docs/PAPER_DRAFT.md",
    "docs/PAPER_RESULTS_DRAFT.md",
    "docs/PAPER_FIGURE_CAPTIONS.md",
    "docs/PAPER_TABLES_SUPP.md",
    "docs/PAPER_REFERENCES.md",
    "docs/PAPER_BACK_MATTER.md",
]
DIRS = [
    ".", "docs", "tools", "native/offtarget_engine/src",
    "native/offtarget_engine/include/offtarget", "Target_xbp_Target",
    "Target_xbp_Y_zbp_Target", "shared/search", "shared/design", "shared/scoring",
    "example/engine_benchmark_small",
]
ZH_PROSE = "\u547d\u4e2d\u6570\u968f\u9884\u7b97"      # hit count grows with budget
ZH_SAME = "\u540c\u503c"                              # "same value" (stale claim)
ZH_FORBIDDEN = ["\u9996\u521b", "\u9996\u6b21", "\u4ece\u672a"]


def read(path):
    return io.open(path, encoding="utf-8").read()


def resolve(path):
    if "/" in path:
        return path if os.path.exists(path) else None
    for d in DIRS:
        cand = os.path.join(d, path)
        if os.path.exists(cand):
            return cand
    return None


sweep = json.loads(read("docs/seed_plan_sweep.json"))
recs = sweep["records"]
idx = {(r["k"], r["M"], r["B"]): r for r in recs}
md = read("docs/SEED_PLAN_ANALYSIS.md").split("\n")

print("== A. D1: SEED_PLAN_ANALYSIS.md grid vs seed_plan_sweep.json ==")
header = next(i for i, line in enumerate(md) if line.startswith("| k | M | B |"))
rows = []
j = header + 2
while j < len(md) and md[j].startswith("|"):
    rows.append([c.strip() for c in md[j].strip().strip("|").split("|")])
    j += 1
check("data rows == 16", len(rows) == 16, "got %d" % len(rows))
keys = set((int(r[0]), int(r[1]), int(r[2])) for r in rows)
check("(k,M,B) keys == json keys", keys == set(idx), "sym-diff=%s" % sorted(keys ^ set(idx)))
mismatch = []
for cells in rows:
    k, m, b = int(cells[0]), int(cells[1]), int(cells[2])
    rec = idx[(k, m, b)]
    segments = rec["py_plan_segments"]
    pairs = [
        ("s*", cells[3], str(int(segments.split("x")[0]))),
        ("W(s)", cells[4], str(rec["py_plan_variants"])),
        ("guaranteed", cells[5], str(rec["seed_plan_guaranteed"]).lower()),
        ("segments", cells[6].strip("`"), segments),
        ("median", cells[7], "%g" % rec["median_search_time_s"]),
        ("candidates", cells[8], str(rec["candidates"])),
        ("hits", cells[9], str(rec["hits"])),
        ("peak RSS", cells[10], "%g" % rec["memory_peak_mb"]),
        ("repeats", cells[11], str(rec["repeats_consistent"]).lower()),
    ]
    for name, seen, expected in pairs:
        if seen != expected:
            mismatch.append("k=%d M=%d B=%d %s md=%r json=%r" % (k, m, b, name, seen, expected))
check("16 rows x 9 columns match json value by value", not mismatch, "; ".join(mismatch[:6]))
check("all 16 records candidates == hits", all(r["candidates"] == r["hits"] for r in recs))
check("all 16 records keep the four guarantee flags",
      all(r["seed_plan_guaranteed"] and r["exhaustive_seed_plan"]
          and r["py_plan_guaranteed"] and r["repeats_consistent"] for r in recs))

print()
print("== B. D1: prose numbers vs json ==")
prose = [line for line in md if ZH_PROSE in line]
check("hit-growth prose line found exactly once", len(prose) == 1, "n=%d" % len(prose))
prose = prose[0] if prose else ""
check("prose carries '(0,0) = 24'", "\u4e3a 24" in prose)
check("prose carries '(3,1) = 67 (k=8) and 66 (k=10)'",
      "\u4e3a 67\uff08k=8\uff09\u4e0e 66\uff08k=10\uff09" in prose)
check("stale 'same value' claim is gone", ZH_SAME not in prose)
check("json k=8 (3,1) hits == 67", idx[(8, 3, 1)]["hits"] == 67, str(idx[(8, 3, 1)]["hits"]))
check("json k=10 (3,1) hits == 66", idx[(10, 3, 1)]["hits"] == 66, str(idx[(10, 3, 1)]["hits"]))
check("json (0,0) hits == 24 for both k",
      idx[(8, 0, 0)]["hits"] == 24 and idx[(10, 0, 0)]["hits"] == 24)

print()
print("== C. D2: [path:...] anchor existence scan ==")
anchors = {}
for path in FILES:
    for match in re.finditer(r"\[([A-Za-z0-9_./-]+):([^\]]*)\]", read(path)):
        anchors.setdefault(match.group(1), set()).add(os.path.basename(path))
unresolved = []
for anchor in sorted(anchors):
    real = resolve(anchor)
    if real is None:
        unresolved.append(anchor)
    else:
        print("   OK  %-38s -> %s   (%s)" % (anchor, real, ", ".join(sorted(anchors[anchor]))))
check("all distinct [path:...] anchors resolve (%d paths)" % len(anchors), not unresolved,
      str(unresolved))
outside = []
for path in FILES:
    for match in re.finditer(r"\[([A-Za-z0-9_./-]+):([0-9]+(?:[-,][0-9]+)*)\]", read(path)):
        real = resolve(match.group(1))
        if real:
            lines = read(real).count("\n")
            if max(int(x) for x in re.findall(r"\d+", match.group(2))) > lines:
                outside.append("%s -> %s:%s (file has %d lines)"
                               % (path, match.group(1), match.group(2), lines))
check("every numeric [path:line] anchor lies inside its file", not outside,
      "; ".join(outside[:6]))

print()
print("== D. C2 forbidden words ==")
hits_any = False
for path in FILES:
    text = read(path)
    hits = [w for w in ("first", "never", "unprecedented")
            if re.search(r"(?i)\b%s\b" % w, text)]
    hits += [w for w in ZH_FORBIDDEN if w in text]
    hits_any = hits_any or bool(hits)
    print("   %-34s hits=%s" % (os.path.basename(path), hits))
check("no forbidden word in any touched document", not hits_any)

print()
print("== E. encoding / structure ==")
bad = []
for path in FILES:
    raw = open(path, "rb").read()
    text = raw.decode("utf-8")
    bom = raw[:3] == b"\xef\xbb\xbf"
    cr = b"\r" in raw
    repl = "\ufffd" in text
    if bom or cr or repl:
        bad.append(path)
    print("   %-34s bytes=%6d BOM=%s CR=%s U+FFFD=%s lines=%d"
          % (os.path.basename(path), len(raw), bom, cr, repl, text.count("\n")))
check("no BOM, no CR, no U+FFFD in any touched document", not bad, str(bad))

print()
print("== F. abstract and reference coverage ==")
draft = read("docs/PAPER_DRAFT.md")
abstract = draft.split("\n")[27]
words = len(re.findall(r"[A-Za-z][A-Za-z-]*", abstract))
check("abstract word count inside 170-250", 170 <= words <= 250, "n=%d" % words)
check("abstract carries no citation number", not re.search(r"\[\d+\]", abstract))
body = draft + read("docs/PAPER_RESULTS_DRAFT.md")
cited = set(int(x) for x in re.findall(r"\[(\d+)\]", body))
missing = [i for i in range(1, 31) if i not in cited]
check("every reference [1]-[30] is cited in the draft body", not missing, "missing=%s" % missing)
refs = read("docs/PAPER_REFERENCES.md")
numbers = sorted(int(x) for x in re.findall(r"^\[(\d+)\] ", refs, re.M))
check("reference list is exactly [1]-[30], one line each", numbers == list(range(1, 31)),
      "n=%d" % len(numbers))
dois = re.findall(r"doi:(10\.[^\s]+)", refs)
check("every reference entry carries a DOI", len(dois) == 30, "dois=%d" % len(dois))
check("no stale tools/expressiveness_matrix.tsv anchor",
      not any("tools/expressiveness_matrix.tsv" in read(path) for path in FILES))

print()
print("RESULT: %s (%d failing checks)" % ("ALL PASS" if not FAILS else "FAILURES", len(FAILS)))
for label in FAILS:
    print("  - " + label)
sys.exit(1 if FAILS else 0)
