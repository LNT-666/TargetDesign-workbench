import importlib.util, os, sys, tempfile
REPO = r"R:\songji\programfile"
BASELINE = os.path.join(REPO, "backup", "gff_gz_annotation_20260915_151757")
ASSETS = os.path.join(REPO, "docs", "handoff", "gff-gz-annotation", "assets")
gz = os.path.join(ASSETS, "mini.gff.gz")
plain = os.path.join(ASSETS, "mini.gff")
sys.path.insert(0, os.path.join(REPO, "shared"))
spec = importlib.util.spec_from_file_location("baseline_ann", os.path.join(BASELINE, "annotation_utils.py"))
bm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bm)
logs = []
print("OLD load_gene_list(plain)=", bm.load_gene_list(plain, "gene_name", None, {}, logs.append))
print("OLD load_gene_list(gz)   =", bm.load_gene_list(gz, "gene_name", None, {}, logs.append))
print("OLD logs:", logs)
from data.annotation_utils import load_gene_list as new_lgl
print("NEW load_gene_list(plain)=", new_lgl(plain, "gene_name", None, {}, None))
print("NEW load_gene_list(gz)   =", new_lgl(gz, "gene_name", None, {}, None))