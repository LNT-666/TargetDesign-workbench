import gzip, importlib.util, io, os, subprocess, sys, tempfile

REPO = r"R:\songji\programfile"
ASSETS = os.path.join(REPO, "docs", "handoff", "gff-gz-annotation", "assets")
BASELINE = os.path.join(REPO, "backup", "gff_gz_annotation_20260915_151757")
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "shared"))
tmp = tempfile.mkdtemp(prefix="master_verify2_")

old_script = os.path.join(BASELINE, "add_utrs_to_gff.py")
plain = os.path.join(ASSETS, "mini.gff")
r_old = subprocess.run([sys.executable, old_script, plain], capture_output=True, cwd=os.path.dirname(old_script))
base_out = r_old.stdout
gz_with = os.path.join(tmp, "has_utr.gff3.gz")
with gzip.open(gz_with, "wb") as fh:
    fh.write(base_out)

import main as main_mod
class FakeEntry:
    def __init__(self, v): self.v = v
    def get(self): return self.v
app = main_mod.MainApp.__new__(main_mod.MainApp)
app.entry_output = FakeEntry(os.path.join(tmp, "out"))
app._gtf_cache = {}
app.logs = []
app.log = lambda m: app.logs.append(str(m))
ret = app._get_prepared_gtf(gz_with)
new_body = io.open(ret, encoding="utf-8").read()
old_body = base_out.decode("utf-8").replace("\r\n", "\n")

def stats(t):
    ls = t.split("\n")
    return len(ls), sum(1 for l in ls if l.strip() == "")
print("D: input lines=%d blank=%d | output lines=%d blank=%d" % (stats(old_body) + stats(new_body)))
ne_old = [l for l in old_body.split("\n") if l.strip()]
ne_new = [l for l in new_body.split("\n") if l.strip()]
print("D: non-empty lines identical:", ne_old == ne_new, len(ne_old), len(ne_new))
print("D: only blank-line drift:", old_body.replace("\n", "") == new_body.replace("\n", ""))

# baseline module on gz (pre-existing silent behaviour)
spec = importlib.util.spec_from_file_location("baseline_add_utrs", old_script)
bm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bm)
print("OLD read_gff(gz) has_utr=%s genes=%d (silent empty)" % (bm.read_gff(gz_with)[3], len(bm.read_gff(gz_with)[1])))
from data.annotation_utils import load_gene_list
print("NEW load_gene_list(gz)=%s" % load_gene_list(gz_with, "gene_name", None, {}, None))
print("TMP:", tmp)