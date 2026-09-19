#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Rebuild the fasta-gz-prep fixtures (deterministic, master-side)."""

import gzip
import os

ASSETS = os.path.dirname(os.path.abspath(__file__))
UNIT = "ACGTTGCA"
SEQ = (UNIT * 625)[:4000]


def build():
    fasta = ">NC_000001.11 synthetic\n" + \
        "\n".join(SEQ[i:i + 70] for i in range(0, len(SEQ), 70)) + "\n"
    with open(os.path.join(ASSETS, "mini.fna"), "w", encoding="ascii", newline="\n") as fh:
        fh.write(fasta)
    with open(os.path.join(ASSETS, "mini.fna.gz"), "wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as gz:
            gz.write(fasta.encode("ascii"))
    print("fixtures written to", ASSETS)


if __name__ == "__main__":
    build()
