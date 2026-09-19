import io, re
p = r"R:\songji\programfile\docs\handoff\nar-format-pack\task.md"
raw = open(p, "rb").read()
d = raw.decode("utf-8")
print("chars", len(d), "bom", raw[:3] == b"\xef\xbb\xbf", "cr", raw.count(b"\r"), "repl", d.count("\ufffd"))
print("backslash_quote", d.count("\\\""), "| 180-250:", d.count("180-250"), "| 170-250:", d.count("170-250"),
      "| 170<=w<=250:", d.count("170<=w<=250"))
lines = d.split("\n")
print("---- lines 1-16 ----")
for i in range(0, 16):
    print("%4d: %s" % (i + 1, lines[i][:140]))
print("---- C2 block ----")
a = [i for i, l in enumerate(lines) if l.startswith("C2  Back matter")][0]
for i in range(a, a + 20):
    print("%4d: %s" % (i + 1, lines[i][:140]))
print("---- self-check ----")
a = [i for i, l in enumerate(lines) if l.startswith("## 6.")][0]
for i in range(a, a + 12):
    print("%4d: %s" % (i + 1, lines[i][:150]))