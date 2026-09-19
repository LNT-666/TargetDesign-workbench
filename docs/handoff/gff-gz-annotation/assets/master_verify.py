import gzip, hashlib, io, os, shutil, subprocess, sys, tempfile

REPO = r"R:\songji\programfile"
ASSETS = os.path.join(REPO, "docs", "handoff", "gff-gz-annotation", "assets")
plain = os.path.join(ASSETS, "mini.gff")
gz = os.path.join(ASSETS, "mini.gff.gz")
BASELINE = os.path.join(REPO, "backup", "gff_gz_annotation_20260915_151757")
SCRIPT = os.path.join("shared", "data", "add_utrs_to_gff.py")

sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "shared"))

def sha(b):
    return hashlib.sha256(b).hexdigest()[:16]

# ---------- V1: new vs baseline script on plain (byte regression) ----------
tmp = tempfile.mkdtemp(prefix="master_verify_")
old_script = os.path.join(tmp, "baseline_add_utrs.py")
shutil.copyfile(os.path.join(BASELINE, "add_utrs_to_gff.py"), old_script)
os.makedirs(os.path.join(tmp, "shared", "data"), exist_ok=True)
new_script = os.path.join(tmp, "shared", "data", "add_utrs_to_gff.py")
shutil.copyfile(os.path.join(REPO, "shared", "data", "add_utrs_to_gff.py"), new_script)
shutil.copyfile(os.path.join(REPO, "shared", "data", "annotation_utils.py"),
                os.path.join(tmp, "shared", "data", "annotation_utils.py"))

def run(script, path):
    return subprocess.run([sys.executable, script, path], capture_output=True, cwd=tmp)

r_new_plain = run(new_script, plain)
r_new_gz = run(new_script, gz)
r_old_plain = run(old_script, plain)
print("V1 new(plain): rc=%d sha=%s" % (r_new_plain.returncode, sha(r_new_plain.stdout)))
print("V1 new(gz)   : rc=%d sha=%s" % (r_new_gz.returncode, sha(r_new_gz.stdout)))
print("V1 old(plain): rc=%d sha=%s" % (r_old_plain.returncode, sha(r_old_plain.stdout)))
print("V1 gz==plain (new):", r_new_gz.stdout == r_new_plain.stdout)
print("V1 new==old (plain, no regression):", r_new_plain.stdout == r_old_plain.stdout)
print("V1 stderr new(gz):", r_new_gz.stderr.decode("utf-8", "replace")[:200])

# ---------- V2: read_gff module-level equivalence incl. baseline module ----------
sys.path.insert(0, os.path.join(REPO, "shared", "data"))
from data.add_utrs_to_gff import read_gff as read_gff_new
import importlib.util
spec = importlib.util.spec_from_file_location("baseline_add_utrs", os.path.join(BASELINE, "add_utrs_to_gff.py"))
baseline_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(baseline_mod)
ln, gn, mn, hu = read_gff_new(gz)
ln2, gn2, mn2, hu2 = read_gff_new(plain)
lno, gno, mno, huo = baseline_mod.read_gff(plain)
print("V2 read_gff new(gz)==new(plain):", ln == ln2, gn == gn2, mn == mn2, hu == hu2)
print("V2 read_gff new(plain)==baseline(plain):", ln == lno, gn == gno, mn == mno, hu == huo)
print("V2 keys: genes=%d mrnas=%d has_utr=%s" % (len(gn), len(mn), hu))

# ---------- V3: _get_prepared_gtf via MainApp.__new__ ----------
import main as main_mod
from data.annotation_utils import load_gene_list

class FakeEntry:
    def __init__(self, v):
        self.v = v
    def get(self):
        return self.v

def make_app(outdir):
    app = main_mod.MainApp.__new__(main_mod.MainApp)
    app.entry_output = FakeEntry(outdir)
    app._gtf_cache = {}
    app.logs = []
    app.log = lambda m: app.logs.append(str(m))
    return app

def show(tag, ret, app):
    ok = ret is not None and os.path.isfile(ret)
    txt = open(ret, encoding="utf-8").read() if ok else ""
    print("%s -> %s | exists=%s | plain_readable=%s | has_5UTR=%s" % (
        tag, os.path.basename(ret) if ret else None, ok, ok, "five_prime_UTR" in txt))
    print("   logs:", app.logs)

# case A: gz input
a = make_app(os.path.join(tmp, "caseA"))
retA = a._get_prepared_gtf(gz)
show("V3-A gz input", retA, a)

# case B: plain input without UTR
b = make_app(os.path.join(tmp, "caseB"))
retB = b._get_prepared_gtf(plain)
show("V3-B plain no-UTR", retB, b)
print("   B returns input unchanged:", retB == plain)

# case C: plain input already containing UTR
pl_with = os.path.join(tmp, "has_utr.gff3")
open(pl_with, "wb").write(r_old_plain.stdout)
c = make_app(os.path.join(tmp, "caseC"))
retC = c._get_prepared_gtf(pl_with)
show("V3-C plain with UTR", retC, c)
print("   C returns input unchanged:", retC == pl_with)

# case D: gz input that ALREADY contains UTR (the real zebra-fish shape)
gz_with = os.path.join(tmp, "has_utr.gff3.gz")
with gzip.open(gz_with, "wb") as fh:
    fh.write(r_old_plain.stdout)
d = make_app(os.path.join(tmp, "caseD"))
retD = d._get_prepared_gtf(gz_with)
show("V3-D gz with UTR", retD, d)
if retD and os.path.isfile(retD):
    body = open(retD, encoding="utf-8").read()
    print("   D is plain text (not gz):", open(retD, "rb").read(2) != b"\x1f\x8b")
    print("   D keeps UTR features:", "five_prime_UTR" in body)
    print("   D content == decompressed input:", body == r_old_plain.stdout.decode("utf-8"))

# case E: gz whose base name contains _with_utrs (naming edge)
gz_wu = os.path.join(tmp, "mini_with_utrs.gff3.gz")
shutil.copyfile(gz, gz_wu)
e = make_app(os.path.join(tmp, "caseE"))
retE = e._get_prepared_gtf(gz_wu)
show("V3-E gz name has _with_utrs", retE, e)

# ---------- V4: load_gene_list on raw gz vs plain ----------
lg = load_gene_list(gz, "gene_name", None, {}, None)
lp = load_gene_list(plain, "gene_name", None, {}, None)
print("V4 gene_name gz=%s plain=%s equal=%s" % (lg, lp, lg == lp))
print("V4 gene_id  gz=%s" % load_gene_list(gz, "gene_id", None, {}, None))
print("V4 ID       gz=%s" % load_gene_list(gz, "ID", None, {}, None))

# ---------- V5: helper edge cases ----------
from data.annotation_utils import is_gzip_file
print("V5 is_gzip dir:", is_gzip_file(ASSETS), "| missing:", is_gzip_file(os.path.join(ASSETS, "nope.gff")),
      "| plain:", is_gzip_file(plain), "| gz:", is_gzip_file(gz))
print("TMP:", tmp)