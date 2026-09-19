#!/usr/bin/env python3
"""Known-hit differential fixture for the native indexed engine."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHARED = os.path.join(ROOT, "shared")
sys.path.insert(0, SHARED)

from search.exact_offtarget import reverse_complement  # noqa: E402
from search.genome_index import build_index, load_index, search_indexed  # noqa: E402


GUIDE = "GCCTCTTTCCCACCCACCTT"
MUTANT = GUIDE[:10] + "A" + GUIDE[11:]
GENOME = {
    "chrPlus": (
        "N" * 10 + GUIDE + "AGG" + "N" * 10 + MUTANT + "TGG" + "N" * 10
    ),
    "chrMinus": "N" * 15 + reverse_complement(GUIDE + "AGG") + "N" * 15,
}

EXPECTED = [
    {
        "target": "chrMinus",
        "start": 18,
        "strand": "-",
        "mismatch": 0,
        "pam": "AGG",
        "target_start": 18,
        "target_end": 38,
        "cigar": "20M",
        "aligned_target": GUIDE,
    },
    {
        "target": "chrPlus",
        "start": 10,
        "strand": "+",
        "mismatch": 0,
        "pam": "AGG",
        "target_start": 10,
        "target_end": 30,
        "cigar": "20M",
        "aligned_target": GUIDE,
    },
    {
        "target": "chrPlus",
        "start": 43,
        "strand": "+",
        "mismatch": 1,
        "pam": "TGG",
        "target_start": 43,
        "target_end": 63,
        "cigar": "10M1X9M",
        "aligned_target": MUTANT,
    },
]


def _native_path():
    configured = os.environ.get("PROGRAMFILE_OFFTARGET_NATIVE")
    if configured:
        return configured
    suffix = ".exe" if os.name == "nt" else ""
    candidate = os.path.join(
        ROOT, "native", "bin", "offtarget-engine" + suffix)
    if os.path.isfile(candidate):
        return candidate
    return shutil.which("offtarget-engine")


def _write_inputs(directory):
    fasta = os.path.join(directory, "known.fa")
    guides = os.path.join(directory, "guides.tsv")
    with open(fasta, "w", encoding="utf-8") as handle:
        for target, sequence in GENOME.items():
            handle.write(">%s\n%s\n" % (target, sequence))
    with open(guides, "w", encoding="utf-8") as handle:
        handle.write("qid\tguide_seq\nknown\t%s\n" % GUIDE)
    return fasta, guides


def _run_native(binary, fasta, prefix, guides):
    result = subprocess.run(
        [
            binary,
            "search",
            "--genome", fasta,
            "--index", prefix,
            "--guides", guides,
            "--max-mismatch", "1",
            "--max-bulge", "0",
            "--seed-len", "8",
            "--seed-mismatch", "1",
            "--require-pam",
            "--pam", "NGG",
            "--pam-side", "3prime",
            "--progress-every", "0",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        raise AssertionError(
            "native search failed (%d): %s"
            % (result.returncode, result.stderr))
    hits = []
    for line in result.stdout.splitlines():
        event = json.loads(line)
        if event["type"] == "hit":
            hits.append(event)
    return hits


def _project(hits):
    keys = tuple(EXPECTED[0])
    return sorted(
        [{key: hit[key] for key in keys} for hit in hits],
        key=lambda hit: tuple(str(hit[key]) for key in keys),
    )


class NativeKnownHitsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.binary = _native_path()
        if not cls.binary or not os.path.isfile(cls.binary):
            raise unittest.SkipTest(
                "native offtarget-engine binary is not built")

    def test_known_hits_match_python_and_native(self):
        with tempfile.TemporaryDirectory() as tmp:
            fasta, guides = _write_inputs(tmp)
            prefix = os.path.join(tmp, "known")
            build_index(fasta, prefix, k=8)
            python_hits, _report = search_indexed(
                load_index(prefix),
                [{"qid": "known", "guide_seq": GUIDE}],
                fasta,
                max_mismatch=1,
                max_bulge=0,
                seed_len=8,
                seed_mm=1,
                pam="NGG",
                pam_side="3prime",
            )
            native_hits = _run_native(self.binary, fasta, prefix, guides)

        self.assertEqual(EXPECTED, _project(python_hits["known"]))
        self.assertEqual(EXPECTED, _project(native_hits))


if __name__ == "__main__":
    unittest.main()
