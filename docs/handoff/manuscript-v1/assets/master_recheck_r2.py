import difflib, hashlib, json, os, re, pathlib
repo = pathlib.Path(r"R:\songji\programfile")
bak = repo / "backup" / "2026-09-19_manuscript-v1-r2"
docs = repo / "docs"
names = ["SEED_PLAN_ANALYSIS.md","PAPER_FIGURE_CAPTIONS.md","PAPER_REFERENCES.md",
         "PAPER_RESULTS_DRAFT.md","PAPER_TABLES_SUPP.md","PAPER_BACK_MATTER.md","PAPER_DRAFT.md"]
print("== 1. hunk count: round-2 backup vs current ==")
tot = 0
for n in names:
    a = (bak / n).read_text(encoding="utf-8").splitlines()
    b = (docs / n).read_text(encoding="utf-8").splitlines()
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    ops = [o for o in sm.get_opcodes() if o[0] != "equal"]
    plus = sum(o[4]-o[3] for o in ops); minus = sum(o[2]-o[1] for o in ops)
    tot += len(ops)
    print(f"{n:28s} old {len(a):4d} -> new {len(b):4d}  hunks {len(ops)}  +{plus} -{minus}")
print(f"TOTAL hunks = {tot}")
print()
print("== 2. untouched baseline: files in backup vs current outside the 7 ==")
extra = sorted(p.name for p in bak.iterdir() if p.is_file() and p.name not in names)
print("files in snapshot not in the 7:", extra)
print()
print("== 3. spec anchor read-backs ==")
s = (docs / "SEED_PLAN_ANALYSIS.md").read_text(encoding="utf-8").splitlines()
print("  [D1] SEED_PLAN_ANALYSIS.md:128 ->", repr(s[127]))
fig = (docs / "PAPER_FIGURE_CAPTIONS.md").read_text(encoding="utf-8").splitlines()
for i in (50, 58, 62):
    print(f"  [D2] PAPER_FIGURE_CAPTIONS.md:{i} ->", repr(fig[i-1]))
ref = (docs / "PAPER_REFERENCES.md").read_text(encoding="utf-8").splitlines()
print("  [D3] reference lines [27]-[30]:")
for line in ref:
    if re.match(r"^\[(2[7-9]|30)\]", line):
        print("        ", line)
back = (docs / "PAPER_BACK_MATTER.md").read_text(encoding="utf-8").splitlines()
print("  [8.1-4] PAPER_BACK_MATTER.md:34 ->", repr(back[33]))
draft = (docs / "PAPER_DRAFT.md").read_text(encoding="utf-8")
print("  [N1] ALLEGRO ellipsis present:", "..." in draft or "\u2026" in draft)
for i, ln in enumerate(draft.splitlines(), 1):
    if "ALLEGRO" in ln:
        print("        PAPER_DRAFT.md:%d" % i, ln.strip()[:160])