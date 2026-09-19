# -*- coding: utf-8 -*-
"""master 独立核验探针（与 servant 的 tests/test_fasta_gz.py 无关）。"""

import gzip
import io
import os
import shutil
import sys
import tempfile

REPO = r"R:\songji\programfile"
ASSETS = os.path.join(REPO, "docs", "handoff", "fasta-gz-prep", "assets")
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "shared"))

from data.annotation_utils import ensure_plain_fasta  # noqa: E402

PLAIN = os.path.join(ASSETS, "mini.fna")
GZ = os.path.join(ASSETS, "mini.fna.gz")
GFF = os.path.join(ASSETS, "mini.gff")
RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok, detail))
    print("%-4s %-46s %s" % ("PASS" if ok else "FAIL", name, detail))


def make_gz(path, payload_bytes, mtime=0):
    with open(path, "wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=mtime) as out:
            out.write(payload_bytes)


class FakeEntry:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value


def main():
    import main as main_module

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        # V1: plain input -> returned untouched, no new files
        plain = os.path.join(tmp, "plain.fna")
        shutil.copyfile(PLAIN, plain)
        before = set(os.listdir(tmp))
        logs = []
        got = ensure_plain_fasta(plain, log_func=logs.append)
        check("V1 plain untouched", got == plain and set(os.listdir(tmp)) == before,
              "returned=%s new_files=%s" % (got == plain, sorted(set(os.listdir(tmp)) - before)))

        # V2: .gz name but plain content -> returned as is
        fake = os.path.join(tmp, "notreally.fna.gz")
        shutil.copyfile(PLAIN, fake)
        got = ensure_plain_fasta(fake, log_func=logs.append)
        check("V2 gz-name/plain-content", got == fake and not os.path.exists(os.path.join(tmp, "notreally.fna")),
              "returned=%s" % got)

        # V3: gz -> sibling .fna, byte identical to plain
        gz = os.path.join(tmp, "mini.fna.gz")
        shutil.copyfile(GZ, gz)
        logs = []
        got = ensure_plain_fasta(gz, log_func=logs.append)
        ok = got == os.path.join(tmp, "mini.fna") and os.path.isfile(got)
        same = ok and open(got, "rb").read() == open(PLAIN, "rb").read()
        head = open(got, "rb").read(2) if ok else b""
        check("V3 gz -> sibling .fna, bytes equal", bool(ok and same and head != b"\x1f\x8b"),
              "target=%s bytes_equal=%s head=%r log=%s" % (os.path.basename(got or ""), same, head, logs))

        # V4: reuse (no rewrite)
        mtime_before = os.path.getmtime(got)
        logs = []
        got2 = ensure_plain_fasta(gz, log_func=logs.append)
        check("V4 reuse existing (mtime kept)",
              got2 == got and os.path.getmtime(got) == mtime_before and "existing" in (logs[0] if logs else ""),
              "logs=%s" % logs)

        # V5: freshness -> gz newer with different payload forces rebuild
        newer = ">NC_000001.11 synthetic\n" + "TTTT" + "\n"
        make_gz(gz, newer.encode("ascii"))
        os.utime(gz, (mtime_before + 10, mtime_before + 10))
        logs = []
        got3 = ensure_plain_fasta(gz, log_func=logs.append)
        content = open(got3, "rb").read() if got3 else b""
        check("V5 newer gz rebuilds target", got3 == got and content == newer.encode("ascii"),
              "content_len=%d logs=%s" % (len(content), logs))

        # V6: mixed case .GZ stripped
        mixed = os.path.join(tmp, "Mini.FNA.GZ")
        shutil.copyfile(GZ, mixed)
        got4 = ensure_plain_fasta(mixed)
        check("V6 mixed-case .GZ stripped", got4 == os.path.join(tmp, "Mini.FNA"),
              "target=%s" % os.path.basename(got4 or ""))

        # V7: no FASTA extension -> .fna appended
        noext = os.path.join(tmp, "genome.gz")
        shutil.copyfile(GZ, noext)
        got5 = ensure_plain_fasta(noext)
        check("V7 no-ext name -> .fna", got5 == os.path.join(tmp, "genome.fna"),
              "target=%s" % os.path.basename(got5 or ""))

        # V8: corrupt gz -> None, no partial artefacts
        bad = os.path.join(tmp, "bad.fna.gz")
        open(bad, "wb").write(b"\x1f\x8b" + b"garbage-not-gzip")
        logs = []
        got6 = ensure_plain_fasta(bad, log_func=logs.append)
        check("V8 corrupt gz -> None, no partial",
              got6 is None and not os.path.exists(os.path.join(tmp, "bad.fna"))
              and not os.path.exists(os.path.join(tmp, "bad.fna.part")),
              "logs=%s" % logs)

        # V9: gz payload that is not FASTA (a GFF) -> None, no partial
        gffgz = os.path.join(tmp, "annot.gff.gz")
        make_gz(gffgz, open(GFF, "rb").read())
        logs = []
        got7 = ensure_plain_fasta(gffgz, log_func=logs.append)
        check("V9 gz non-FASTA -> None, no partial",
              got7 is None and not os.path.exists(os.path.join(tmp, "annot.gff"))
              and not os.path.exists(os.path.join(tmp, "annot.gff.part")),
              "logs=%s" % logs)

        # V10: primary target blocked (dir in the way) -> fallback_dir (C8)
        fb_src = os.path.join(tmp, "c8src")
        fb_out = os.path.join(tmp, "c8out")
        os.makedirs(fb_src, exist_ok=True)
        os.makedirs(fb_out, exist_ok=True)
        shutil.copyfile(GZ, os.path.join(fb_src, "mini.fna.gz"))
        os.makedirs(os.path.join(fb_src, "mini.fna"), exist_ok=True)  # blocks os.replace
        logs = []
        got8 = ensure_plain_fasta(os.path.join(fb_src, "mini.fna.gz"), log_func=logs.append, fallback_dir=fb_out)
        check("V10 fallback_dir when sibling blocked",
              got8 == os.path.join(fb_out, "mini.fna") and os.path.getsize(got8) > 0,
              "target=%s logs=%s" % (got8, logs))

        # V11: _get_prepared_genome cache + raw entry unchanged (C11/C12)
        app = main_module.MainApp.__new__(main_module.MainApp)
        app.log_messages = []
        app.log = app.log_messages.append
        app._gtf_cache = {}
        app._genome_cache = {}
        app.entry_output = FakeEntry(tmp)
        app.entry_genome = FakeEntry(gz)
        first = app._get_prepared_genome()
        second = app._get_prepared_genome()
        check("V11 _get_prepared_genome cache/C12",
              first == second == os.path.join(tmp, "mini.fna") and app.entry_genome.get() == gz,
              "first=%s entries=%d raw_kept=%s" % (os.path.basename(first or ""), len(app._genome_cache), app.entry_genome.get() == gz))

        # V15: warm cache + newer source -> refreshed (round 2)
        warm_gz = os.path.join(tmp, "warm.fna.gz")
        shutil.copyfile(GZ, warm_gz)
        app.entry_genome = FakeEntry(warm_gz)
        app._genome_cache = {}
        baseline = app._get_prepared_genome()
        before = open(baseline, "rb").read()
        new_payload = b">NC_000001.11 synthetic\nGGGG\n"
        make_gz(warm_gz, new_payload)
        later = os.path.getmtime(warm_gz) + 10
        os.utime(warm_gz, (later, later))
        refreshed = app._get_prepared_genome()
        check("V15 warm cache refreshes on newer source",
              refreshed == baseline and open(refreshed, "rb").read() == new_payload and before != new_payload,
              "logs=%s" % app.log_messages[-2:])

        # V16: warm cache + deleted copy -> rebuilt (round 2)
        app.entry_genome = FakeEntry(gz)
        app._genome_cache = {}
        built = app._get_prepared_genome()
        os.remove(built)
        rebuilt = app._get_prepared_genome()
        check("V16 deleted copy rebuilt", rebuilt == built and os.path.isfile(rebuilt),
              "logs=%s" % app.log_messages[-2:])

        # V12: end-to-end gz vs plain through main.py extraction
        plain_copy = os.path.join(tmp, "e2e.fna")
        shutil.copyfile(PLAIN, plain_copy)
        seqs = {}
        fastas = {}
        app.entry_target_id = FakeEntry("A")
        app.entry_target_num = FakeEntry("")
        app.combo_target_region = FakeEntry("Coding region")
        app.combo_target_id_type = FakeEntry("gene_name")
        for label, genome in (("plain", plain_copy), ("gz", gz)):
            app.entry_genome = FakeEntry(genome)
            app._genome_cache = {}
            seqs[label] = app._extract_sequences("A", "Coding region", None, "gene_name", GFF)
            app.entry_output = FakeEntry(tmp)
            fastas[label] = open(app._extract_target_fasta(GFF, tmp), "rb").read()
        check("V12 gz == plain end-to-end",
              seqs["plain"] == seqs["gz"] and fastas["plain"] == fastas["gz"] and len(seqs["gz"][0][1]) > 0,
              "seq_len=%d fasta_bytes=%d" % (len(seqs["gz"][0][1].replace("\n", "")), len(fastas["gz"])))

        # V13: workspace mapping still points at the raw entry (P0-6 / C12)
        workspace = app._workspace_mapping()
        check("V13 workspace mapping unchanged",
              workspace.get("entry_genome") == "genome" and workspace.get("entry_gtf") == "annotation",
              "entry_genome=%r" % workspace.get("entry_genome"))

    # V14: C13 - the three params["genome"] writers use the prepared variable
    src = io.open(os.path.join(REPO, "main.py"), encoding="utf-8").read().splitlines()
    writers = [i + 1 for i, line in enumerate(src) if line.strip() == '"genome": genome,']
    prepared = [i + 1 for i, line in enumerate(src) if line.strip() == "genome = self._get_prepared_genome()"]
    direct = [i + 1 for i, line in enumerate(src) if line.strip() == "raw_genome = self.entry_genome.get().strip()"]
    def body_range(name):
        """1-based inclusive line range of a top-level class method."""
        start = next(i for i, line in enumerate(src) if line.startswith("    def %s(" % name))
        end = start + 1
        while end < len(src) and not src[end].startswith("    def "):
            end += 1
        return start + 1, end

    ok = len(writers) == 3 and len(prepared) == 4 and len(direct) == 4
    for name in ("prepare_data", "extract_target_sequences", "extract_mask_sequences"):
        lo, hi = body_range(name)
        prep = [n for n in prepared if lo <= n <= hi]
        raw = [n for n in direct if lo <= n <= hi]
        writer = [n for n in writers if lo <= n <= hi]
        ok = ok and len(prep) == 1 and len(raw) == 1 and len(writer) == 1 and raw[0] < prep[0] < writer[0]
    check("V14 C13 prepared-before-params in all 3 entries", ok,
          "params_writers=%s prepared=%s raw_readers=%s" % (writers, prepared, direct))

    bad = [n for n, ok, _ in RESULTS if not ok]
    print("\n%d checks, %d failed" % (len(RESULTS), len(bad)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
