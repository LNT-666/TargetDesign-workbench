"""Master-side independent probe for GET /api/fs/list (webapp-file-picker, round 1).

Usage:
    python probe_master_api.py [base_url]      # default http://127.0.0.1:8371

Checks the response contract of task.md sections 1.1/1.2/1.3 against a live
server, plus the /api/outputs and static-whitelist regressions (P1-2).
Exit code 0 only when every check passes.
"""
import json
import os
import shutil
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8371/").rstrip("/")
ASSETS = os.path.dirname(os.path.abspath(__file__))
FIXTURE = os.path.abspath(os.path.join(ASSETS, "fixture"))
ASSETS_ABS = os.path.dirname(FIXTURE)
KEYS = {"dir", "parent", "roots", "home", "kind", "strip", "entries", "truncated"}
ENTRY_KEYS = {"name", "path", "type", "size", "modified"}
OUTPUT_EXTENSIONS = (".tsv", ".csv", ".bed", ".fa", ".fasta", ".fna", ".fai", ".xlsx",
                     ".json", ".txt", ".log", ".ggi", ".idx", ".meta")
RESULTS = []


def record(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    line = ("PASS " if ok else "FAIL ") + name
    if detail and not ok:
        line += "  <- " + str(detail)
    print(line)


def request(path):
    try:
        with urllib.request.urlopen(BASE + path, timeout=120) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            payload = json.loads(raw)
        except ValueError:
            payload = {"error": raw}
        return exc.code, payload


def request_raw(path):
    try:
        with urllib.request.urlopen(BASE + path, timeout=120) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def listing(**params):
    query = urllib.parse.urlencode(params)
    return request("/api/fs/list" + ("?" + query if query else ""))


def names(payload):
    return [entry["name"] for entry in payload.get("entries", [])]


def ordered_ok(entries):
    dirs = [e["name"] for e in entries if e["type"] == "dir"]
    files = [e["name"] for e in entries if e["type"] == "file"]
    types = [e["type"] for e in entries]
    return (types == ["dir"] * len(dirs) + ["file"] * len(files)
            and dirs == sorted(dirs, key=str.lower)
            and files == sorted(files, key=str.lower))


# ---------------------------------------------------------------- A. root mode
status, root = listing()
record("A1-empty-query-200", status == 200, status)
record("A2-root-keys", set(root) == KEYS, sorted(root))
record("A3-root-dir-parent-null", root.get("dir") is None and root.get("parent") is None)
record("A4-root-roots-nonempty-alphabetical",
       isinstance(root.get("roots"), list) and len(root["roots"]) > 0
       and root["roots"] == sorted(root["roots"]), root.get("roots"))
record("A5-root-entries-empty", root.get("entries") == [])
record("A6-root-kind-any", root.get("kind") == "any", root.get("kind"))
record("A7-root-strip-empty", root.get("strip") == [])
record("A8-root-truncated-false", root.get("truncated") is False)
record("A9-root-home", root.get("home") == os.path.expanduser("~"), root.get("home"))

status, blank = listing(dir="", kind="fasta")
record("A10-blank-dir-is-root-mode",
       status == 200 and blank.get("dir") is None and blank.get("kind") == "fasta")

# ------------------------------------------------------------ B. fixture / fasta
status, fasta = listing(dir=FIXTURE, kind="fasta")
record("B1-fasta-200", status == 200, status)
record("B2-fasta-keys", set(fasta) == KEYS, sorted(fasta))
record("B3-dir-normalized-absolute", fasta.get("dir") == FIXTURE, fasta.get("dir"))
record("B4-parent", fasta.get("parent") == ASSETS_ABS, fasta.get("parent"))
record("B5-kind-echoed", fasta.get("kind") == "fasta", fasta.get("kind"))
record("B6-strip-empty-for-fasta", fasta.get("strip") == [])
record("B7-roots-empty-in-dir-mode", fasta.get("roots") == [])
record("B8-truncated-false", fasta.get("truncated") is False)
record("B9-fasta-names-and-order", names(fasta) == ["sub", "mini.fna"], names(fasta))
record("B10-entry-keys", all(set(e) == ENTRY_KEYS for e in fasta.get("entries", [])))
record("B11-modified-is-number",
       all(isinstance(e["modified"], (int, float)) for e in fasta.get("entries", [])))
by_name = {e["name"]: e for e in fasta.get("entries", [])}
record("B12-dir-entry-shape",
       by_name["sub"]["type"] == "dir" and by_name["sub"]["size"] is None
       and by_name["sub"]["path"] == os.path.join(FIXTURE, "sub"), by_name.get("sub"))
record("B13-file-entry-shape",
       by_name["mini.fna"]["type"] == "file" and by_name["mini.fna"]["size"] == 28
       and by_name["mini.fna"]["path"] == os.path.join(FIXTURE, "mini.fna"),
       by_name.get("mini.fna"))

# ---------------------------------------------------------------- C. kind filters
EXPECTED = {
    "any": ["sub", "mini.blastdb.nin", "mini.blastdb.nsq", "mini.blastdb.source.json",
            "mini.fna", "miniindex.ggi", "miniindex.json", "notes.txt", "regions.bed"],
    "dir": ["sub"],
    "annotation": ["sub"],
    "bed": ["sub", "regions.bed"],
    "db": ["sub", "mini.blastdb.nin", "mini.blastdb.nsq", "mini.blastdb.source.json"],
    "index": ["sub", "mini.blastdb.source.json", "miniindex.ggi", "miniindex.json"],
}
for kind in sorted(EXPECTED):
    status, payload = listing(dir=FIXTURE, kind=kind)
    record("C-%s-200" % kind, status == 200, status)
    record("C-%s-names" % kind, names(payload) == EXPECTED[kind], names(payload))
    record("C-%s-order-deterministic" % kind, ordered_ok(payload.get("entries", [])))

status, unknown = listing(dir=FIXTURE, kind="bogus")
record("C-unknown-kind-echoes-any",
       status == 200 and unknown.get("kind") == "any" and names(unknown) == EXPECTED["any"],
       (status, unknown.get("kind"), names(unknown)))
record("C-unknown-kind-strip-empty", unknown.get("strip") == [])

status, nosort = listing(dir=os.path.join(FIXTURE, "sub", ".."))
record("C-dotdot-normalizes", status == 200 and nosort.get("dir") == FIXTURE, nosort.get("dir"))

# ------------------------------------------------------------------- D. strip
status, db = listing(dir=FIXTURE, kind="db")
strip = db.get("strip", [])
record("D1-db-strip-members",
       set(strip) == {".source.json", ".nin", ".nhr", ".nsq", ".ndb", ".nog", ".nos",
                      ".not", ".ntf", ".nto", ".njs"}, strip)
record("D2-db-strip-longest-first",
       [len(s) for s in strip] == sorted([len(s) for s in strip], reverse=True)
       and strip[0] == ".source.json", strip)
status, index = listing(dir=FIXTURE, kind="index")
record("D3-index-strip-members", set(index.get("strip", [])) == {".ggi", ".json"},
       index.get("strip"))
record("D4-index-strip-longest-first",
       [len(s) for s in index.get("strip", [])]
       == sorted([len(s) for s in index.get("strip", [])], reverse=True), index.get("strip"))

# ------------------------------------------------------------------- E. errors
missing = os.path.join(FIXTURE, "nope")
status, payload = listing(dir=missing)
record("E1-missing-dir-400", status == 400, status)
record("E2-missing-dir-message",
       "Directory not found" in str(payload.get("error", "")), payload)
status, payload = listing(dir=os.path.join(FIXTURE, "mini.fna"))
record("E3-file-path-400", status == 400, (status, payload))
status, payload = listing(dir="R:\\this\\drive\\does\\not\\exist")
record("E4-bogus-drive-400", status == 400, (status, payload))

# --------------------------------------------------------------- F. truncation
tmp = tempfile.mkdtemp(prefix="fslist_master_")
try:
    for i in range(30):
        os.mkdir(os.path.join(tmp, "d%02d" % i))
    for i in range(2100):
        with open(os.path.join(tmp, "f%04d.txt" % i), "w", encoding="utf-8") as handle:
            handle.write("x")
    status, big = listing(dir=tmp)
    entries = big.get("entries", [])
    dirs_kept = [e for e in entries if e["type"] == "dir"]
    files_kept = [e for e in entries if e["type"] == "file"]
    record("F1-truncation-200", status == 200, status)
    record("F2-truncated-flag", big.get("truncated") is True, big.get("truncated"))
    record("F3-cap-2000", len(entries) == 2000, len(entries))
    record("F4-all-30-dirs-kept", len(dirs_kept) == 30, len(dirs_kept))
    record("F5-files-dropped-not-dirs",
           len(files_kept) == 1970 and ordered_ok(entries), (len(files_kept),))
    status, small = listing(dir=tmp, kind="dir")
    record("F6-kind-dir-hides-files",
           [e["type"] for e in small.get("entries", [])] == ["dir"] * 30,
           len(small.get("entries", [])))
finally:
    shutil.rmtree(tmp, ignore_errors=True)

# -------------------------------------------------- G. P1-2 regressions (outputs)
reference = sorted(
    name for name in os.listdir(FIXTURE)
    if os.path.isfile(os.path.join(FIXTURE, name))
    and name.lower().endswith(OUTPUT_EXTENSIONS))
status, outputs = request("/api/outputs?dir=" + urllib.parse.quote(FIXTURE))
record("G1-outputs-200", status == 200, status)
record("G2-outputs-reference-names",
       [item["name"] for item in outputs.get("files", [])] == reference,
       ([item["name"] for item in outputs.get("files", [])], reference))
record("G3-outputs-dir-echo", outputs.get("dir") == FIXTURE, outputs.get("dir"))
status, payload = request("/api/outputs")
record("G4-outputs-requires-dir", status == 400, status)
status, payload = listing(dir=FIXTURE, kind="db")
record("G5-fs-list-does-not-leak-content",
       all("content" not in e and "text" not in e for e in payload.get("entries", [])))

# ------------------------------------------------------- H. static whitelist
status, body = request_raw("/static/app.js")
record("H1-app-js-served", status == 200 and b"browse-btn" in body, (status, len(body)))
status, body = request_raw("/static/styles.css")
record("H2-styles-served", status == 200 and b".picker" in body, (status, len(body)))
status, body = request_raw("/static/nope.js")
record("H3-unknown-static-404", status == 404, status)
status, body = request_raw("/static/../app.py")
record("H4-traversal-static-404", status == 404, status)

failed = [name for name, ok in RESULTS if not ok]
print("")
print("checks=%d failed=%d" % (len(RESULTS), len(failed)))
for name in failed:
    print("FAILED: " + name)
sys.exit(1 if failed else 0)