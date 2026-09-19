import io, os, json, hashlib

ROOT = r"R:\songji\programfile"

def load(name):
    p = os.path.join(ROOT, "out", "master_methods_verify", name)
    lines = [l for l in io.open(p, encoding="utf-8").read().splitlines() if l.strip()]
    summary = [l for l in lines if '"summary"' in l]
    hits = [l for l in lines if l not in summary]
    return lines, summary, hits

for name in ["t1.jsonl", "t8.jsonl"]:
    lines, summary, hits = load(name)
    print(name, "total", len(lines), "hits", len(hits))
    print("  summary:", summary[0] if summary else "NONE")
    print("  hit_digest:", hashlib.sha256("\n".join(hits).encode()).hexdigest()[:32])

a = load("t1.jsonl")[2]
b = load("t8.jsonl")[2]
print("HIT_LINES_IDENTICAL:", a == b)
if a:
    print("first_hit:", a[0][:240])