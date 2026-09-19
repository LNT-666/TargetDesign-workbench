import re, os, io, json

ROOT = r"R:\songji\programfile"
doc = os.path.join(ROOT, "docs", "PAPER_METHODS_DRAFT.md")
d = io.open(doc, encoding="utf-8").read()
body, table = d.split("## Anchor table")

rows = re.findall(r"^\|\s*\[(\d+)\]\s*\|(.*?)\|(.*?)\|(.*?)\|\s*$", table, re.M)
rows = [(int(n), s.strip(), a.strip(), t.strip()) for n, s, a, t in rows]

refpat = re.compile(r"`([^`]+?)`")

def parse_refs(anchor):
    found = []
    for tok in refpat.findall(anchor):
        if ":" not in tok:
            continue
        path, _, rest = tok.partition(":")
        for span in rest.split(","):
            span = span.strip()
            if re.fullmatch(r"\d+(?:-\d+)?", span):
                found.append((path.strip(), span))
    return found
cache = {}
out = []
problems = []

def getlines(path):
    if path not in cache:
        p = os.path.join(ROOT, path.replace("/", os.sep))
        cache[path] = io.open(p, encoding="utf-8", errors="replace").read().splitlines() if os.path.exists(p) else None
    return cache[path]

for num, stmt, anchor, note in rows:
    refs = parse_refs(anchor)
    if not refs:
        problems.append((num, "NO_REF", anchor))
    out.append("=== [%d] %s" % (num, stmt[:120]))
    out.append("    note: %s" % note[:90])
    for path, span in refs:
        lines = getlines(path)
        if lines is None:
            problems.append((num, "MISSING_FILE", path))
            out.append("    !! MISSING FILE %s" % path)
            continue
        if "-" in span:
            a, b = span.split("-"); a, b = int(a), int(b)
        else:
            a = b = int(span)
        if a < 1 or b > len(lines) or a > b:
            problems.append((num, "OUT_OF_RANGE", "%s:%s (file lines=%d)" % (path, span, len(lines))))
            out.append("    !! OUT OF RANGE %s:%s (file lines=%d)" % (path, span, len(lines)))
            continue
        out.append("    %s:%s" % (path, span))
        for i in range(a, b + 1):
            out.append("      %4d| %s" % (i, lines[i - 1].strip()[:150]))

table_nums = set(n for n, _, _, _ in rows)
cited = set(int(x) for x in re.findall(r"\[(\d+)\]", body))
out.append("")
out.append("TABLE_ROWS=%d  min=%d  max=%d" % (len(rows), min(table_nums), max(table_nums)))
out.append("MISSING_ROWS_FOR_CITED=%s" % sorted(cited - table_nums))
out.append("ROWS_NEVER_CITED=%s" % sorted(table_nums - cited))
out.append("TABLE_NUMBER_GAPS=%s" % sorted(set(range(1, max(table_nums) + 1)) - table_nums))
out.append("PROBLEMS=%s" % json.dumps(problems, ensure_ascii=False))

dest = os.path.join(ROOT, "docs", "handoff", "methods-draft", "assets", "master_anchors.txt")
os.makedirs(os.path.dirname(dest), exist_ok=True)
io.open(dest, "w", encoding="utf-8", newline="\n").write("\n".join(out) + "\n")
print("written", dest, "lines", len(out))
print("\n".join(out[-5:]))