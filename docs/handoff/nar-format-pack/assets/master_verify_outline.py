import io
p = r"R:\songji\programfile\docs\PAPER_OUTLINE.md"
raw = open(p, "rb").read()
d = raw.decode("utf-8")
lines = d.split("\n")
print("chars", len(d), "bom", raw[:3] == b"\xef\xbb\xbf", "cr", raw.count(b"\r"), "repl", d.count("\ufffd"))

def show(a, b, tag):
    print("---- %s (lines %d-%d) ----" % (tag, a, b))
    for i in range(a - 1, min(b, len(lines))):
        print("%4d: %s" % (i + 1, lines[i][:150]))

show(7, 17, "0")
show(60, 74, "2.1 table tail")
for i, l in enumerate(lines):
    if l.startswith("### 2.3"):
        show(i + 1, i + 14, "2.3")
        break
for i, l in enumerate(lines):
    if l.startswith("## 九"):
        show(i + 1, i + 6, "9 head")
        break
for i, l in enumerate(lines):
    if l.startswith("#### 9.0.1"):
        show(i + 1, i + 13, "9.0.1")
        break
print("180-250 occurrences", d.count("180-250"), "| 170-250 occurrences", d.count("170-250"))