#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Round-4 servant probe on ms01: gzip genome FASTA / gzip annotation end to end.

Authoritative run:
    cd /home/apool/songji/programfile
    PYTHONUTF8=1 .venv/bin/python docs/handoff/fasta-gz-prep/assets/ms01/servant_probe_round4.py

Sections
    A  ensure_plain_fasta on the mini fixture (fresh decompress + reuse)
    B  real 1.4 GB genome + real .gff.gz through main.py (GUI code path)
    C  engine entry load_genome_and_prepare_fasta
    D  workbench entry PatternDesignerWorkbench._prepare_genome_fasta
    E  side-effect surface (user files untouched)
    F  gz annotation -> UTR product on the mini fixture (build / reuse / stale / gz==plain)

Prints PASS/FAIL per check plus a SUMMARY line; exit code 1 if any check fails.
Never writes inside the user's genome directory: all products go to WORK
(default /tmp/fasta_gz_verify, override with FASTA_GZ_WORK).
"""

import gzip
import hashlib
import os
import shutil
import sys
import tempfile
import time

ROOT = "/home/apool/songji/programfile"
for _path in (os.path.join(ROOT, "shared"), ROOT):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from data.annotation_utils import (  # noqa: E402
    ensure_plain_fasta,
    is_gzip_file,
    load_gene_list,
    plain_fasta_is_current,
)
from search.blast_utils import load_genome_and_prepare_fasta  # noqa: E402
from pyfaidx import Fasta  # noqa: E402
import main as main_module  # noqa: E402
from designer_workbench import PatternDesignerWorkbench  # noqa: E402

GEN = "/home/apool/songji/genome/Danio_rerio"
GZ = os.path.join(GEN, "GCF_049306965.2_GRCz12tu_genomic.fna.gz")
PLAIN = os.path.join(GEN, "GCF_049306965.2_GRCz12tu_genomic.fna")
GFF_GZ = os.path.join(GEN, "GCF_049306965.2_GRCz12tu_genomic.gff.gz")
REAL_UTR = os.path.join(GEN, "GCF_049306965.2_GRCz12tu_genomic_with_utrs.gff3")
ASSETS = os.path.join(ROOT, "docs", "handoff", "fasta-gz-prep", "assets")
WORK = os.environ.get("FASTA_GZ_WORK", "/tmp/fasta_gz_verify")
PROBE_UTR = os.path.join(WORK, "GCF_049306965.2_GRCz12tu_genomic_with_utrs.gff3")
os.makedirs(WORK, exist_ok=True)

RESULTS = []


def check(name, cond, extra=""):
    RESULTS.append((name, bool(cond)))
    print(("PASS  " if cond else "FAIL  ") + name + ("  | " + str(extra) if extra else ""), flush=True)


def sha256_file(path, chunk=1 << 22):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(chunk), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_gz_stream(path, chunk=1 << 22):
    digest = hashlib.sha256()
    with gzip.open(path, "rb") as handle:
        for block in iter(lambda: handle.read(chunk), b""):
            digest.update(block)
    return digest.hexdigest()


def read_bytes(path):
    with open(path, "rb") as handle:
        return handle.read()


class FakeEntry(object):
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value


def make_app(genome, gtf, outdir, target):
    app = main_module.MainApp.__new__(main_module.MainApp)
    app._gtf_cache = {}
    app._genome_cache = {}
    app.log_messages = []
    app.log = app.log_messages.append
    app.entry_genome = FakeEntry(genome)
    app.entry_gtf = FakeEntry(gtf)
    app.entry_output = FakeEntry(outdir)
    app.entry_target_id = FakeEntry(target)
    app.entry_target_num = FakeEntry("")
    app.combo_target_region = FakeEntry("Coding region")
    app.combo_target_id_type = FakeEntry("gene_name")
    return app


class FakeWorkbench(object):
    def __init__(self, values):
        self.values = values
        self.logs = []

    def _value(self, key, default=""):
        return self.values.get(key, default)

    def _log_line(self, line):
        self.logs.append(line)


def stage_mini(prefix, use_gz):
    tmp = tempfile.mkdtemp(dir=WORK, prefix=prefix)
    shutil.copyfile(os.path.join(ASSETS, "mini.fna"), os.path.join(tmp, "mini.fna"))
    shutil.copyfile(os.path.join(ASSETS, "mini.gff"), os.path.join(tmp, "mini.gff"))
    gz = os.path.join(tmp, "mini.gff.gz")
    with open(os.path.join(tmp, "mini.gff"), "rb") as raw, open(gz, "wb") as out:
        with gzip.GzipFile(filename="", mode="wb", fileobj=out, mtime=0) as handle:
            handle.write(raw.read())
    return tmp, (gz if use_gz else os.path.join(tmp, "mini.gff"))


print("host=%s python=%s" % (os.uname().nodename, sys.version.split()[0]), flush=True)

# ---------------- A. fixture: ensure_plain_fasta ----------------
print("== A. mini.fna.gz fresh decompress / reuse ==", flush=True)
tmp_a = tempfile.mkdtemp(dir=WORK, prefix="mini_")
gz_a = os.path.join(tmp_a, "mini.fna.gz")
target_a = os.path.join(tmp_a, "mini.fna")
shutil.copyfile(os.path.join(ASSETS, "mini.fna.gz"), gz_a)
logs = []
t0 = time.time()
prepared = ensure_plain_fasta(gz_a, logs.append)
check("A1 target = <gz dir>/mini.fna", prepared == target_a, prepared)
check("A2 byte-identical to mini.fna",
      read_bytes(prepared) == read_bytes(os.path.join(ASSETS, "mini.fna")))
check("A3 product is plain text (not gzip)", not is_gzip_file(prepared),
      "size=%d" % os.path.getsize(prepared))
check("A4 log line", logs == ["Decompressed genome FASTA: %s" % prepared], logs)
check("A5 no .part left behind", not os.path.exists(prepared + ".part"))
stamp_a = os.path.getmtime(prepared)
logs2 = []
again = ensure_plain_fasta(gz_a, logs2.append)
check("A6 reuse (same path, mtime unchanged, reuse log)",
      again == prepared and os.path.getmtime(again) == stamp_a and
      logs2 == ["Using existing plain FASTA: %s" % prepared], logs2)
check("A7 plain_fasta_is_current(copy, source)", plain_fasta_is_current(prepared, gz_a))
print("A elapsed %.2fs" % (time.time() - t0), flush=True)

# ---------------- B. real genome / real annotation through main.py ----------------
print("== B. real genomic files through main.py GUI path ==", flush=True)
listing_before = sorted(os.listdir(GEN))
plain_mtime0 = os.path.getmtime(PLAIN)
plain_size0 = os.path.getsize(PLAIN)
gz_stat0 = (os.path.getmtime(GZ), os.path.getsize(GZ))
utr_hash0 = sha256_file(REAL_UTR)
t0 = time.time()
check("B0 1.4 GB copy still matches source (sha256 vs gzip -dc)",
      sha256_file(PLAIN) == sha256_gz_stream(GZ), sha256_file(PLAIN))
print("B0 elapsed %.1fs" % (time.time() - t0), flush=True)

if os.path.exists(PROBE_UTR):
    os.remove(PROBE_UTR)
app = make_app(GZ, GFF_GZ, WORK, "")
t0 = time.time()
utr = app._get_prepared_gtf(GFF_GZ)
check("B1 _get_prepared_gtf(.gff.gz) lands in entry_output", utr == PROBE_UTR, utr)
check("B2 product rebuilt from .gff.gz == user's existing UTR file (sha256)",
      sha256_file(PROBE_UTR) == utr_hash0,
      "%s size=%d" % (sha256_file(PROBE_UTR)[:16], os.path.getsize(PROBE_UTR)))
check("B3 log shows the product was built from the gz annotation",
      any(line.startswith("Adding UTR") for line in app.log_messages), app.log_messages[:1])
genes = load_gene_list(utr, "gene_name", None, {}, None)
check("B4 gene count == 41192", len(genes) == 41192, len(genes))
target = "42sp43" if "42sp43" in genes else genes[0]
check("B5 target gene present in list", target in genes, target)
print("B gtf elapsed %.1fs" % (time.time() - t0), flush=True)

t0 = time.time()
app.entry_target_id = FakeEntry(target)
prepared_genome = app._get_prepared_genome()
check("B6 _get_prepared_genome(.fna.gz) -> plain .fna", prepared_genome == PLAIN, prepared_genome)
check("B7 raw entry value untouched", app.entry_genome.get() == GZ)
check("B8 reuse log", app.log_messages[-1].startswith("Using existing plain FASTA"),
      app.log_messages[-1:])
check("B9 copy not rewritten", os.path.getmtime(PLAIN) == plain_mtime0 and
      os.path.getsize(PLAIN) == plain_size0)
parts = app._extract_sequences(target, "Coding region", None, "gene_name", utr)
seq = parts[0][1].replace("\n", "")
check("B10 extracted %s coding region (2914 bp)" % target,
      parts[0][0] == ">%s-gene" % target and len(seq) == 2914,
      "%s len=%d" % (parts[0][0], len(seq)))
check("B11 nucleotides only (case as stored in the genome)",
      set(seq) <= set("ACGTNacgtn"), set(seq) - set("ACGTNacgtn"))
target_fa = app._extract_target_fasta(utr, WORK)
check("B12 target FASTA written", bool(target_fa) and os.path.isfile(target_fa),
      "%s %s" % (target_fa, os.path.getsize(target_fa) if target_fa else None))
print("B extract elapsed %.1fs seq=%s len=%d" % (time.time() - t0, seq[:40], len(seq)), flush=True)

# ---------------- C. engine entry ----------------
print("== C. engine: load_genome_and_prepare_fasta ==", flush=True)
t0 = time.time()
index, resolved, temp_file = load_genome_and_prepare_fasta(GZ)
check("C1 resolved == plain copy, temp=None", resolved == PLAIN and temp_file is None, resolved)
name = list(index.keys())[0]
engine_seq = str(index[name][0:60])
plain_seq = str(Fasta(PLAIN)[name][0:60])
check("C2 gz path sequence == plain path sequence",
      engine_seq == plain_seq and len(engine_seq) == 60, "%s %s" % (name, engine_seq))
print("C elapsed %.1fs" % (time.time() - t0), flush=True)

# ---------------- D. workbench entry ----------------
print("== D. workbench Genome FASTA row ==", flush=True)
stub = FakeWorkbench({"genome_fasta": GZ, "output_dir": WORK})
prepared_row = PatternDesignerWorkbench._prepare_genome_fasta(stub)
check("D1 gz row -> plain .fna", prepared_row == PLAIN, prepared_row)
check("D2 reuse log", any("Using existing plain FASTA" in line for line in stub.logs), stub.logs)
plain_stub = FakeWorkbench({"genome_fasta": PLAIN, "output_dir": WORK})
check("D3 plain row passthrough without logs",
      PatternDesignerWorkbench._prepare_genome_fasta(plain_stub) == PLAIN and plain_stub.logs == [])
check("D4 empty row -> empty string",
      PatternDesignerWorkbench._prepare_genome_fasta(FakeWorkbench({})) == "")

# ---------------- E. side effects ----------------
print("== E. side-effect surface ==", flush=True)
check("E1 genome dir listing unchanged", sorted(os.listdir(GEN)) == listing_before,
      sorted(set(os.listdir(GEN)) ^ set(listing_before)) or "identical")
check("E2 user's UTR file untouched (sha256)", sha256_file(REAL_UTR) == utr_hash0)
check("E3 source .gz untouched (mtime+size)", (os.path.getmtime(GZ), os.path.getsize(GZ)) == gz_stat0)
check("E4 plain copy untouched (mtime+size)",
      (os.path.getmtime(PLAIN), os.path.getsize(PLAIN)) == (plain_mtime0, plain_size0))

# ---------------- F. gz annotation -> UTR product (fixture) ----------------
print("== F. .gff.gz -> UTR product on the mini fixture ==", flush=True)
tmp_f, src_f = stage_mini("utr_gz_", True)
app_f = make_app(None, src_f, tmp_f, "")
log_f = app_f.log_messages
first_f = app_f._get_prepared_gtf(src_f)
utr_f = os.path.join(tmp_f, "mini_with_utrs.gff3")
check("F1 .gff.gz -> <out>/mini_with_utrs.gff3", first_f == utr_f, first_f)
check("F2 log shows build from the gz annotation",
      any(line.startswith("Adding UTR") for line in log_f), log_f)
stamp_f = os.path.getmtime(utr_f)
mark = len(log_f)
second_f = app_f._get_prepared_gtf(src_f)
check("F3 warm cache + current product -> silent hit (no rewrite, no new log)",
      second_f == utr_f and os.path.getmtime(utr_f) == stamp_f and log_f[mark:] == [],
      log_f[mark:])
app_cold = make_app(None, src_f, tmp_f, "")
cold_f = app_cold._get_prepared_gtf(src_f)
check("F4 cold cache -> reuse log",
      cold_f == utr_f and app_cold.log_messages[-1].startswith("Using existing UTR file"),
      app_cold.log_messages[-1:])
old = os.path.getmtime(src_f) - 60
os.utime(utr_f, (old, old))
app_stale = make_app(None, src_f, tmp_f, "")
stale_f = app_stale._get_prepared_gtf(src_f)
check("F5 stale product (older than source) rebuilt",
      stale_f == utr_f and
      any("UTR file is stale, re-generating" in line for line in app_stale.log_messages) and
      os.path.getmtime(utr_f) >= os.path.getmtime(src_f), app_stale.log_messages)
tmp_p, src_p = stage_mini("utr_plain_", False)
app_p = make_app(None, src_p, tmp_p, "")
plain_product = app_p._get_prepared_gtf(src_p)
check("F6 gz product == plain product (byte-identical)",
      read_bytes(plain_product) == read_bytes(utr_f),
      "sizes %d/%d" % (os.path.getsize(plain_product), os.path.getsize(utr_f)))

failed = [name for name, ok in RESULTS if not ok]
print("SUMMARY: %d checks, %d failed %s" % (len(RESULTS), len(failed), failed if failed else ""), flush=True)
sys.exit(1 if failed else 0)