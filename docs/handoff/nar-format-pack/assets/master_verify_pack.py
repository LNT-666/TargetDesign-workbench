import io, os, re, json, subprocess, sys, unicodedata

ROOT = r"R:\songji\programfile"
os.chdir(ROOT)
out = []

def rd(p):
    raw = open(p, "rb").read()
    return raw, raw.decode("utf-8", "replace")

def enc(tag, p):
    raw, s = rd(p)
    out.append("%-56s chars=%-6d bom=%s cr=%d repl=%d" % (tag, len(s), raw[:3] == b"\xef\xbb\xbf", raw.count(b"\r"), s.count("\ufffd")))

for p in ["docs/NAR_FORMAT_CHECKLIST.md", "docs/PAPER_FRONT_MATTER.md", "docs/PAPER_BACK_MATTER.md",
          "docs/FIGURE_TABLE_PLAN.md", "docs/GRAPHICAL_ABSTRACT_SPEC.md", "docs/assets/graphical_abstract_draft.svg",
          "docs/EXPRESSIVENESS_MATRIX.md", "docs/expressiveness_matrix.tsv"]:
    enc(os.path.basename(p), p)

front = rd("docs/PAPER_FRONT_MATTER.md")[1]
m = re.search(r"## Abstract(.*?)\n##", front, re.S)
abs_ = m.group(1)
words = len(re.findall(r"[A-Za-z][A-Za-z-]*", abs_))
paras = [b for b in abs_.strip().split("\n\n") if b.strip()]
out.append("ABSTRACT words=%d paragraphs=%d citations=%d forbidden=%s" % (
    words, len(paras), len(re.findall(r"\[\d+\]", abs_)),
    re.findall(r"(?i)\b(first|never|unprecedented)\b", abs_)))

back = rd("docs/PAPER_BACK_MATTER.md")[1]
heads = [l.strip() for l in back.split("\n") if re.match(r"^#{2,3} ", l)]
out.append("BACK_MATTER headings: " + " | ".join(heads))
out.append("BACK_MATTER has Author contributions: %s | wiki wording: %s" % (
    "Author contributions" in back, "project wiki" in back.lower()))
for key in ["is available at NAR online", "is available at NAR Online", "Zenodo", "[TO FILL]"]:
    out.append("  back_matter contains %-28s %s" % (key, key in back))

plan = rd("docs/FIGURE_TABLE_PLAN.md")[1]
main_tbl = re.findall(r"主文表[^\n]{0,60}", plan)
out.append("FIGURE_TABLE_PLAN 主文表 mentions: " + " || ".join(x[:70] for x in main_tbl[:6]))
figs = sorted(set(int(x) for x in re.findall(r"Figure\s+(\d+)", plan)))
out.append("FIGURE_TABLE_PLAN figure numbers seen: %s" % figs)

chk = rd("docs/NAR_FORMAT_CHECKLIST.md")[1]
rows = [l for l in chk.split("\n") if l.startswith("| ") and "---" not in l]
out.append("CHECKLIST table rows=%d (data rows %d) | [TO FILL] count=%d" % (len(rows), len(rows) - 1, chk.count("[TO FILL]")))

files = ["docs/PAPER_FRONT_MATTER.md", "docs/PAPER_BACK_MATTER.md", "docs/FIGURE_TABLE_PLAN.md",
         "docs/GRAPHICAL_ABSTRACT_SPEC.md", "docs/NAR_FORMAT_CHECKLIST.md"]
bad = {f: re.findall(r"(?i)\b(first|never|unprecedented)\b", rd(f)[1]) for f in files}
out.append("forbidden scan: " + json.dumps({k.split('/')[-1]: v for k, v in bad.items()}))

cjk = {}
for f in files:
    s = rd(f)[1]
    cjk[f.split("/")[-1]] = sum(1 for c in s if ord(c) > 0x2E80)
out.append("cjk char counts: " + json.dumps(cjk))

try:
    import xml.etree.ElementTree as ET
    root = ET.parse("docs/assets/graphical_abstract_draft.svg").getroot()
    out.append("SVG parse OK: tag=%s viewBox=%s" % (root.tag.split('}')[-1], root.get("viewBox")))
except Exception as e:
    out.append("SVG parse FAILED: %r" % e)

r = subprocess.run([sys.executable, "tools/expressiveness_probe.py", "--json"], capture_output=True, text=True, encoding="utf-8")
out.append("probe --json exit=%d" % r.returncode)
out.append("probe json: " + r.stdout.strip().splitlines()[-1][:400] if r.stdout.strip() else "no stdout")

import csv
rows = list(csv.DictReader(io.open("docs/expressiveness_matrix.tsv", encoding="utf-8"), delimiter="\t"))
out.append("TSV rows=%d cols=%d first=%s" % (len(rows), len(rows[0]), rows[0]["tool"]))
unk = {r_["tool"]: sum(1 for v in r_.values() if str(v).strip().lower() in ("unknown", "n/a", "", "?")) for r_ in rows}
out.append("rows with unknown/empty cells: " + json.dumps({k: v for k, v in unk.items() if v}))

print("\n".join(out))