import re, io, os, unicodedata

ROOT = r"R:\songji\programfile"
doc = os.path.join(ROOT, "docs", "PAPER_METHODS_DRAFT.md")
raw = open(doc, "rb").read()
d = raw.decode("utf-8")

print("bytes", len(raw), "chars", len(d))
print("bom", raw[:3] == b"\xef\xbb\xbf", "cr", raw.count(b"\r"), "repl", d.count("\ufffd"))

secs = re.findall(r"^### (2\.\d[^\n]*)$", d, re.M)
print("sections", len(secs))
for s in secs:
    print("   ", s)

low = d.lower()
for w in ["first", "never", "unprecedented", "novel", "首创", "首次", "唯一"]:
    print("forbidden %-14s count=%d" % (w, low.count(w.lower())))

# CJK outside the notes column of the anchor table
at = d.index("## Anchor table")
body = d[:at]
cjk = [(i, c) for i, c in enumerate(body) if unicodedata.east_asian_width(c) in ("W", "F") and ord(c) > 0x2E80]
print("cjk_in_body", len(cjk))
cjk_table_rows = [i for i, line in enumerate(d[at:].splitlines()) if any(ord(c) > 0x2E80 for c in line)]
print("table_rows_with_cjk", len(cjk_table_rows))

# notes column must be the only Chinese: check every table row's 4th cell
rows = re.findall(r"^\|\s*\[(\d+)\]\s*\|(.*?)\|(.*?)\|(.*?)\|\s*$", d[at:], re.M)
bad = [n for n, s, a, t in rows if any(ord(c) > 0x2E80 for c in (s + a))]
print("rows_with_cjk_outside_note", bad)

# placeholder discipline
print("placeholders TIME/RATIO/N:", d.count("[TIME]"), d.count("[RATIO]"), d.count("[N]"))
# absolute claims
for pat in [r"\bwe (show|demonstrate|prove)\b", r"\boutperform", r"\bbetter than\b", r"\bfaster than\b"]:
    print("absclaim", pat, len(re.findall(pat, low)))