#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""master 的根因探针：同一份 mini 基因组，明文 vs gzip，走 main.py 自身代码路径。

用法（在本机、或服务器的 programfile 目录下均可）：
    $env:PYTHONUTF8="1"; python docs\handoff\fasta-gz-prep\assets\master_probe_genome_gz.py

预期（改动前）：plain OK / gz FAIL UnsupportedCompressionFormat
预期（改动后）：两行都是 OK 且长度一致（需先把 _extract_sequences 换成 prepared 路径）
"""

import gzip
import os
import shutil
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))
ASSETS = os.path.join(REPO, "docs", "handoff", "fasta-gz-prep", "assets")
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "shared"))


class FakeEntry:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value


def main():
    import main as main_module

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        gff = os.path.join(tmp, "mini.gff")
        shutil.copyfile(os.path.join(ASSETS, "mini.gff"), gff)
        plain = os.path.join(tmp, "mini.fna")
        gz = os.path.join(tmp, "mini.fna.gz")
        shutil.copyfile(os.path.join(ASSETS, "mini.fna"), plain)
        with open(gz, "wb") as raw:
            with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as out:
                out.write(open(plain, "rb").read())

        app = main_module.MainApp.__new__(main_module.MainApp)
        app.log_messages = []
        app.log = app.log_messages.append
        app._gtf_cache = {}
        app._genome_cache = {}
        app.entry_output = FakeEntry(tmp)

        for label, path in (("plain", plain), ("gz", gz)):
            app.entry_genome = FakeEntry(path)
            try:
                parts = app._extract_sequences("A", "Coding region", None, "gene_name", gff)
                print(label, "OK", parts[0][0], len(parts[0][1].replace("\n", "")))
            except Exception as exc:
                print(label, "FAIL", type(exc).__name__, "|", str(exc)[:160])


if __name__ == "__main__":
    main()
