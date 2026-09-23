#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Expressiveness probe for the C1 parameter matrix (docs/expressiveness_matrix.tsv).

The probe re-runs this repository's own code paths on small synthetic sequences
and asserts every capability claimed for the "This work (TargetDesign-
workbench)" row of the matrix:

    input_model, custom_pam_tam, custom_target_length, custom_orientation,
    middle_element_constraint, enumerates_all_occurrences, pair_side_independent

Claims are not taken on trust:

* guide enumeration from shared/design/guide_design.py is compared against an
  independent reference enumerator defined in this file (plain string logic);
* the distance-window behaviour of the paired layout is re-derived from the
  real helper functions lifted out of
  Target_xbp_Target/extract_complex_queries.py;
* every prose claim is tied to a repository file:line anchor that is re-located
  at run time, so a stale anchor fails the probe instead of rotting silently.
* the Pattern B (Y-centred) layout is exercised end to end: the probe writes a
  small synthetic genome and drives the production extractor
  (Target_xbp_Y_zbp_Target/extract_motifs.py) with two design requests, then
  compares the reported left/right occurrences with the planted layout.

Standard library only: no numpy, no network access, and no import of Biopython.
The Pattern B end-to-end check runs the production extractor as a subprocess,
and that subprocess needs the dependencies of the Pattern B pipeline itself
(Biopython and pyfaidx).

Usage:
    python tools/expressiveness_probe.py           # human readable report
    python tools/expressiveness_probe.py --json    # one machine-readable record

Exit status is 0 only when every assertion passes.
"""

import argparse
import ast
import subprocess
import tempfile
import json
import os
import platform
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHARED = os.path.join(ROOT, "shared")
for _path in (SHARED, ROOT):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from design.guide_design import find_guides          # noqa: E402
from design.pattern_spec import (                    # noqa: E402
    MotifSpec, PatternKind, PatternSpec, Side,
)
from search.iupac import find_all_iupac_positions    # noqa: E402


# ---------------------------------------------------------------------------
# Independent reference implementation (deliberately not imported from shared/)
# ---------------------------------------------------------------------------

REFERENCE_IUPAC = {
    "A": "A", "C": "C", "G": "G", "T": "T", "U": "T",
    "R": "AG", "Y": "CT", "S": "GC", "W": "AT", "K": "GT", "M": "AC",
    "D": "AGT", "H": "ACT", "V": "ACG", "B": "CGT", "N": "ACGT",
}
_REFERENCE_COMPLEMENT = str.maketrans("ACGTRYSWKMBDHVN", "TGCAYRSWMKVHDBN")


def revcomp(seq):
    return seq.upper().translate(_REFERENCE_COMPLEMENT)[::-1]


def pam_matches(window, pam):
    if len(window) != len(pam):
        return False
    for base, code in zip(window.upper(), pam.upper()):
        if base not in REFERENCE_IUPAC.get(code, code):
            return False
    return True


def reference_guides(sequence, spacer_len, pam, pam_side="3prime",
                     allow_reverse=True):
    """Brute-force [spacer][PAM] / [PAM][spacer] enumeration, plain string logic."""
    seq = sequence.upper().replace("U", "T")
    length = len(seq)
    span = spacer_len + len(pam)
    found = []
    for strand in ("+", "-") if allow_reverse else ("+",):
        source = seq if strand == "+" else revcomp(seq)
        for start in range(len(source) - span + 1):
            window = source[start:start + span]
            if pam_side == "3prime":
                spacer, pam_window = window[:spacer_len], window[spacer_len:]
            else:
                spacer, pam_window = window[len(pam):], window[:len(pam)]
            if set(spacer) - set("ACGT"):
                continue
            if not pam_matches(pam_window, pam):
                continue
            if strand == "+":
                spacer_start = start if pam_side == "3prime" else start + len(pam)
            else:
                spacer_start = length - start - span
            found.append((strand, spacer_start, spacer_start + spacer_len,
                          pam_window))
    return sorted(found)


def production_guides(sequence, spacer_len, pam, pam_side="3prime",
                      allow_reverse=True):
    records = find_guides(sequence, spacer_len=spacer_len, pam=pam,
                          pam_side=pam_side, allow_reverse=allow_reverse)
    return sorted((r["strand"], r["spacer_start"], r["spacer_end"], r["pam_seq"])
                  for r in records)


# ---------------------------------------------------------------------------
# Test sequences (20 nt self-reverse-complementary spacer, so both strands are
# guaranteed to carry the same number of sites)
# ---------------------------------------------------------------------------

SPACER = "ACGTACGTACGTACGTACGT"

# VNG and NNGRRT PAMs placed immediately 3' of a fixed spacer.
SEQ_VNG = SPACER + "CAG" + "TTTT"
SEQ_NNGRRT = SPACER + "AAGAAT" + "TTTT"
# The same non-NGG PAM (TTTV) placed 3' of one spacer and 5' of another.
SEQ_PAM_3PRIME = "CCCC" + SPACER + "TTTACCCC"
SEQ_PAM_5PRIME = "GGGTTTA" + SPACER + "CCCC"
# Four NGG sites on both strands, for exhaustive-enumeration checks
# (CCN on the plus strand is NGG on the minus strand).  The AT filler carries
# no NGG/CCN site of its own and keeps every site away from the sequence ends.
SEQ_ALL_OCCURRENCES = ("ATATATATATATATATATATATATA"
                       + "TTTTT" + SPACER + "AGG" + "TTTTT"
                       + "GCGCGCGCGCGCGCGCGCGC" + "TGG" + "TTTTT"
                       + "ATATATATATATATATATAT" + "CGG" + "TTTTT"
                       + "TGTGTGTGTGTGTGTGTGTG" + "CCA" + "TTTTT"
                       + "ATATATATATATATATATATATATA")

# Paired layout: one locus per strand combination (++ / +- / -+ / --).
LEFT_MOTIF = "TTAT"
RIGHT_MOTIF = "CCAA"
LINKER = "GAGAGAGA"
PAIR_GAP = "GAGAGA"
STRAND_COMBOS = (("plus", "plus"), ("plus", "minus"),
                 ("minus", "plus"), ("minus", "minus"))
PAIR_SEQ = (
    LINKER + LEFT_MOTIF + PAIR_GAP + RIGHT_MOTIF + LINKER
    + LEFT_MOTIF + PAIR_GAP + revcomp(RIGHT_MOTIF) + LINKER
    + revcomp(LEFT_MOTIF) + PAIR_GAP + RIGHT_MOTIF + LINKER
    + revcomp(LEFT_MOTIF) + PAIR_GAP + revcomp(RIGHT_MOTIF) + LINKER
)


# ---------------------------------------------------------------------------
# Repository anchors re-located at run time
# ---------------------------------------------------------------------------

ANCHORS = {
    "guide_design.free_input": (
        "shared/design/guide_design.py",
        "This module keeps the existing free-input behavior",
    ),
    "guide_design.find_guides": (
        "shared/design/guide_design.py",
        'def find_guides(sequence, spacer_len=20, pam=None, pam_side="3prime",',
    ),
    "guide_design.allow_reverse": (
        "shared/design/guide_design.py",
        'strands = ["+", "-"] if allow_reverse else ["+"]',
    ),
    "iupac.positions": (
        "shared/search/iupac.py",
        "def find_all_iupac_positions(sequence, pattern):",
    ),
    "iupac.matches": (
        "shared/search/iupac.py",
        "def find_all_iupac_matches(sequence, pattern):",
    ),
    "pattern_spec.iupac_bases": (
        "shared/design/pattern_spec.py",
        '_IUPAC_BASES = set("ACGTUNRYSWKMBDHV")',
    ),
    "queries.strand_combos": (
        "Target_xbp_Target/extract_complex_queries.py",
        '("minus", "minus", left_motif_minus, right_motif_minus),',
    ),
    "queries.four_strands_doc": (
        "Target_xbp_Target/extract_complex_queries.py",
        "Left and right motifs are each matched on plus and minus",
    ),
    "queries.gap_args": (
        "Target_xbp_Target/extract_complex_queries.py",
        "<min_gap> <max_gap> <left_side> <left_len> <right_side> <right_len>",
    ),
    "queries.independent_columns": (
        "Target_xbp_Target/extract_complex_queries.py",
        '"left_side", "left_len", "right_side", "right_len"]',
    ),
    "motifs.min_left": (
        "Target_xbp_Y_zbp_Target/extract_motifs.py",
        '"--min_left", type=int, default=0',
    ),
    "motifs.min_right": (
        "Target_xbp_Y_zbp_Target/extract_motifs.py",
        '"--min_right", type=int, default=0',
    ),
    "motifs.max_left": (
        "Target_xbp_Y_zbp_Target/extract_motifs.py",
        '"L", type=int, help="Maximum left distance from Y (bp)"',
    ),
    "motifs.max_right": (
        "Target_xbp_Y_zbp_Target/extract_motifs.py",
        '"R", type=int, help="Maximum right distance from Y (bp)"',
    ),
    "workbench.pam_tam": (
        "designer_workbench.py",
        '"PAM/TAM Motif",',
    ),
    "workbench.target_length": (
        "designer_workbench.py",
        '"Target Length",',
    ),
    "workbench.target_position": (
        "designer_workbench.py",
        '"Target Position",',
    ),
    "workbench.left_distance": (
        "designer_workbench.py",
        '"left_min_distance", "Minimum Distance",',
    ),
    "workbench.right_distance": (
        "designer_workbench.py",
        '"right_max_distance", "Maximum Distance",',
    ),
    "workbench.middle_motif": (
        "designer_workbench.py",
        '"Middle Motif",',
    ),
    "gui.bed_regions": (
        "unified_gui.py",
        '"input_regions.bed"',
    ),
    "search_indexed.pam_side": (
        "tools/search_indexed.py",
        'choices=["3prime", "5prime"]',
    ),
    "pattern_spec.y_centered_kind": (
        "shared/design/pattern_spec.py",
        "if self.kind is PatternKind.Y_CENTERED_MOTIFS:",
    ),
    "runner.y_extract_command": (
        "shared/design/pattern_runner.py",
        '"Target_xbp_Y_zbp_Target", "extract_motifs.py")',
    ),
    "runner.y_min_left": (
        "shared/design/pattern_runner.py",
        '"--min_left",',
    ),
    "motifs.y_left_window": (
        "Target_xbp_Y_zbp_Target/extract_motifs.py",
        "left_search_start = max(0, start - args.L - args.flank_left)",
    ),
    "motifs.y_right_window": (
        "Target_xbp_Y_zbp_Target/extract_motifs.py",
        "right_search_start = end + args.min_right",
    ),
}

PAIR_HELPERS_PATH = os.path.join("Target_xbp_Target",
                                 "extract_complex_queries.py")


def locate(relative_path, needle):
    """Return the 1-based line number of the first line containing needle."""
    path = os.path.join(ROOT, relative_path)
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        for number, line in enumerate(handle, start=1):
            if needle in line:
                return number
    return None


def load_pair_helpers():
    """Lift flank_interval/get_flank out of the real script (it imports Biopython
    at module level, which this stdlib-only probe must not require)."""
    path = os.path.join(ROOT, PAIR_HELPERS_PATH)
    with open(path, "r", encoding="utf-8") as handle:
        source = handle.read()
    tree = ast.parse(source, filename=path)
    wanted = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in ("flank_interval",
                                                               "get_flank"):
            wanted[node.name] = node
    missing = [name for name in ("flank_interval", "get_flank")
               if name not in wanted]
    if missing:
        raise RuntimeError("missing definitions in %s: %s" % (path, missing))
    module = ast.Module(body=[wanted["flank_interval"], wanted["get_flank"]],
                        type_ignores=[])
    namespace = {"__file__": path}
    exec(compile(module, path, "exec"), namespace)
    lines = {name: node.lineno for name, node in wanted.items()}
    return namespace["flank_interval"], namespace["get_flank"], lines


def enumerate_pairs(sequence, left_motif, right_motif, min_gap, max_gap):
    """Same enumeration order as extract_complex_queries.py main()."""
    seq = sequence.upper()
    combos = set()
    gaps = []
    for left_strand, right_strand in STRAND_COMBOS:
        l_motif = left_motif if left_strand == "plus" else revcomp(left_motif)
        r_motif = right_motif if right_strand == "plus" else revcomp(right_motif)
        for lpos in sorted(find_all_iupac_positions(seq, l_motif)):
            for rpos in sorted(find_all_iupac_positions(seq, r_motif)):
                gap = rpos - (lpos + len(l_motif))
                if min_gap <= gap <= max_gap:
                    combos.add((left_strand, right_strand))
                    gaps.append(gap)
    return combos, gaps


# ---------------------------------------------------------------------------
# Pattern B (Y-centred) fixture: Target - xbp - Y - ybp - Target
# ---------------------------------------------------------------------------

PATTERN_B_Y = "ACGTGCA"
PATTERN_B_LEFT_PATTERN = "CGGWA"
PATTERN_B_LEFT_LITERAL = "CGGTA"
PATTERN_B_RIGHT_PATTERN = "GCCAT"
PATTERN_B_RIGHT_LITERAL = "GCCAT"
PATTERN_B_MAX_DISTANCE = 20
PATTERN_B_FLANK_LEFT = 6
PATTERN_B_FLANK_RIGHT = 2
PATTERN_B_SIDE_LEFT = "upstream"
PATTERN_B_SIDE_RIGHT = "downstream"
PATTERN_B_REQUEST = (3, 20)
PATTERN_B_TIGHT_RIGHT_REQUEST = (5, 20)
PATTERN_B_EXTRACTOR = os.path.join("Target_xbp_Y_zbp_Target",
                                   "extract_motifs.py")

# Single record, plus strand.  The filler is A/T only, so neither an anchoring
# motif nor a Y copy can appear outside the planted sites.
PATTERN_B_PARTS = (
    ("pre", "ATATATATA"),
    ("left_high", PATTERN_B_LEFT_LITERAL),
    ("gap1", "AT"),
    ("left_minus", revcomp(PATTERN_B_LEFT_LITERAL)),
    ("gap2", "ATAT"),
    ("left_plus", PATTERN_B_LEFT_LITERAL),
    ("gap3", "ATATA"),
    ("y", PATTERN_B_Y),
    ("gap4", "ATAT"),
    ("right_plus", PATTERN_B_RIGHT_LITERAL),
    ("gap5", "ATA"),
    ("right_minus", revcomp(PATTERN_B_RIGHT_LITERAL)),
    ("gap6", "ATAT"),
    ("right_high", PATTERN_B_RIGHT_LITERAL),
    ("post", "ATATAT"),
)

PATTERN_B_GENOME = "".join(part for _name, part in PATTERN_B_PARTS)


def pattern_b_offsets():
    offsets = {}
    pointer = 0
    for name, part in PATTERN_B_PARTS:
        offsets[name] = pointer
        pointer += len(part)
    return offsets


def pattern_b_expected():
    """Solutions implied by the planted layout, plus the distance of each one."""
    offsets = pattern_b_offsets()
    y_start = offsets["y"]
    y_end = y_start + len(PATTERN_B_Y)
    left_len = len(PATTERN_B_LEFT_LITERAL)
    right_len = len(PATTERN_B_RIGHT_LITERAL)

    def solution(name, strand, motif_len, side):
        start = offsets[name]
        end = start + motif_len
        if side == "left":
            distance = y_start - end
            flank = PATTERN_B_FLANK_LEFT
            full_start = start - flank if strand == "plus" else start
            full_end = end if strand == "plus" else end + flank
        else:
            distance = start - y_end
            flank = PATTERN_B_FLANK_RIGHT
            full_start = start if strand == "plus" else start - flank
            full_end = end + flank if strand == "plus" else end
        return {
            "side": side,
            "strand": strand,
            "distance": distance,
            "motif_start": start,
            "motif_end": end,
            "full_start": full_start,
            "full_end": full_end,
            "sequence": PATTERN_B_GENOME[full_start:full_end],
        }

    return {
        "left_plus": solution("left_plus", "plus", left_len, "left"),
        "left_minus": solution("left_minus", "minus", left_len, "left"),
        "right_plus": solution("right_plus", "plus", right_len, "right"),
        "right_minus": solution("right_minus", "minus", right_len, "right"),
    }


def run_pattern_b_request(genome, outdir, left_range, right_range):
    """Drive the production Pattern B extractor with one design request."""
    fasta = os.path.join(outdir, "pattern_b_genome.fa")
    with open(fasta, "w", encoding="ascii", newline="") as handle:
        handle.write(">chr1\n")
        for start in range(0, len(genome), 60):
            handle.write(genome[start:start + 60] + "\n")
    command = [
        sys.executable,
        os.path.join(ROOT, PATTERN_B_EXTRACTOR),
        fasta,
        PATTERN_B_Y,
        str(left_range[1]),
        str(right_range[1]),
        PATTERN_B_LEFT_PATTERN,
        str(PATTERN_B_FLANK_LEFT),
        PATTERN_B_SIDE_LEFT,
        PATTERN_B_RIGHT_PATTERN,
        str(PATTERN_B_FLANK_RIGHT),
        PATTERN_B_SIDE_RIGHT,
        "--min_left", str(left_range[0]),
        "--min_right", str(right_range[0]),
        "--outdir", outdir,
    ]
    return subprocess.run(command, cwd=ROOT, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, timeout=300)


def read_pattern_b_occurrences(outdir, side):
    """Read left_occurrence_1.tsv / right_occurrence_1.tsv from the extractor."""
    path = os.path.join(outdir, "occurrence", "%s_occurrence_1.tsv" % side)
    rows = []
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.rstrip("\n")
            if not line or line.startswith("#") or line.startswith("qid\t"):
                continue
            _qid, sequence, payload = line.split("\t")
            for item in json.loads(payload):
                (chrom, strand, full_start, full_end,
                 motif_start, motif_end) = item
                rows.append({
                    "sequence": sequence,
                    "strand": strand,
                    "motif_start": motif_start,
                    "motif_end": motif_end,
                    "full_start": full_start,
                    "full_end": full_end,
                })
    return rows


def read_pattern_b_y_sites(outdir):
    """Read occurrence_info.tsv written by the production extractor."""
    path = os.path.join(outdir, "occurrence", "occurrence_info.tsv")
    rows = []
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.rstrip("\n")
            if not line or line.startswith("occurrence\t"):
                continue
            index, chrom, y_start, y_end, strand = line.split("\t")
            rows.append((int(index), chrom, int(y_start), int(y_end), strand))
    return rows


def pattern_b_key(row):
    return (row["strand"], row["motif_start"], row["motif_end"],
            row["full_start"], row["full_end"], row["sequence"])


def rejects_pattern_spec(kwargs):
    """True when the production spec rejects a malformed Y-centred request."""
    try:
        PatternSpec(**kwargs).validate()
    except ValueError:
        return True
    return False


def check_pattern_b_end_to_end(report):
    """Run the production Pattern B extractor and check the layout contract."""
    expected = pattern_b_expected()
    offsets = pattern_b_offsets()
    genome = PATTERN_B_GENOME
    y_start = offsets["y"]
    y_end = y_start + len(PATTERN_B_Y)
    left_len = len(PATTERN_B_LEFT_LITERAL)
    right_len = len(PATTERN_B_RIGHT_LITERAL)

    left_names = ("left_plus", "left_minus")
    right_names = ("right_plus", "right_minus")
    wanted = {
        "left": sorted(pattern_b_key(expected[name]) for name in left_names),
        "right": sorted(pattern_b_key(expected[name]) for name in right_names),
    }
    wanted_distances = {
        "left": sorted(expected[name]["distance"] for name in left_names),
        "right": sorted(expected[name]["distance"] for name in right_names),
    }
    rejected_distances = sorted((
        y_start - (offsets["left_high"] + left_len),
        offsets["right_high"] - y_end,
    ))

    # The planted fixture, before the extractor is involved: one Y site, no Y
    # copy on the minus strand, and every planted anchor where it should be.
    fixture_ok = (
        genome.count(PATTERN_B_Y) == 1
        and genome.count(revcomp(PATTERN_B_Y)) == 0
        and len(find_all_iupac_positions(genome, PATTERN_B_LEFT_PATTERN)) == 2
        and len(find_all_iupac_positions(
            genome, revcomp(PATTERN_B_LEFT_PATTERN))) == 1
        and len(find_all_iupac_positions(genome, PATTERN_B_RIGHT_PATTERN)) == 2
        and len(find_all_iupac_positions(
            genome, revcomp(PATTERN_B_RIGHT_PATTERN))) == 1
        and genome[offsets["left_plus"]:offsets["left_plus"] + left_len]
        == PATTERN_B_LEFT_LITERAL
        and genome[offsets["left_minus"]:offsets["left_minus"] + left_len]
        == revcomp(PATTERN_B_LEFT_LITERAL)
        and genome[offsets["right_plus"]:offsets["right_plus"] + right_len]
        == PATTERN_B_RIGHT_LITERAL
        and genome[offsets["right_minus"]:offsets["right_minus"] + right_len]
        == revcomp(PATTERN_B_RIGHT_LITERAL)
    )

    # Both over-distance copies sit inside the raw scan window, so their absence
    # from the solution set is what shows the distance window was enforced.
    left_window = (y_start - PATTERN_B_MAX_DISTANCE - PATTERN_B_FLANK_LEFT,
                   y_start - PATTERN_B_REQUEST[0] + 1)
    right_window = (y_end + PATTERN_B_REQUEST[0],
                    y_end + PATTERN_B_MAX_DISTANCE
                    + PATTERN_B_FLANK_RIGHT + 1)
    rejected_in_window = (
        left_window[0] <= offsets["left_high"] < left_window[1]
        and right_window[0] <= offsets["right_high"] < right_window[1]
    )

    spec = PatternSpec(
        kind=PatternKind.Y_CENTERED_MOTIFS,
        y_sequence=PATTERN_B_Y,
        left=MotifSpec(PATTERN_B_LEFT_PATTERN, PATTERN_B_FLANK_LEFT,
                       Side.UPSTREAM),
        right=MotifSpec(PATTERN_B_RIGHT_PATTERN, PATTERN_B_FLANK_RIGHT,
                        Side.DOWNSTREAM),
        left_min_distance=PATTERN_B_REQUEST[0],
        left_max_distance=PATTERN_B_REQUEST[1],
        right_min_distance=PATTERN_B_REQUEST[0],
        right_max_distance=PATTERN_B_REQUEST[1],
    )
    try:
        spec.validate()
        validated = True
    except ValueError:
        validated = False
    description = spec.describe().splitlines()
    description_head = ("[%s flank %d bp][%s] <-Y(%s)-> [%s][%s flank %d bp]"
                        % (PATTERN_B_SIDE_LEFT, PATTERN_B_FLANK_LEFT,
                           PATTERN_B_LEFT_PATTERN, PATTERN_B_Y,
                           PATTERN_B_RIGHT_PATTERN, PATTERN_B_SIDE_RIGHT,
                           PATTERN_B_FLANK_RIGHT))
    contract_columns = ["query_id", "seq_id", "strand", "start", "end",
                        "query_seq", "y_sequence", "left_motif_seq",
                        "right_motif_seq", "left_distance", "right_distance",
                        "left_flank_seq", "right_flank_seq", "left_side",
                        "right_side"]
    malformed = (
        dict(kind=PatternKind.Y_CENTERED_MOTIFS, left=spec.left,
             right=spec.right, left_min_distance=3, left_max_distance=20,
             right_min_distance=3, right_max_distance=20),
        dict(kind=PatternKind.Y_CENTERED_MOTIFS, y_sequence=PATTERN_B_Y,
             left=spec.left, right=spec.right, left_min_distance=3,
             left_max_distance=20),
        dict(kind=PatternKind.Y_CENTERED_MOTIFS, y_sequence=PATTERN_B_Y,
             left=spec.left, right=spec.right, left_min_distance=3,
             left_max_distance=20, right_min_distance=20,
             right_max_distance=5),
        dict(kind=PatternKind.Y_CENTERED_MOTIFS, y_sequence="ACGTXCA",
             left=spec.left, right=spec.right, left_min_distance=3,
             left_max_distance=20, right_min_distance=3,
             right_max_distance=20),
    )
    contract_ok = (
        validated
        and spec.candidate_columns() == contract_columns
        and description[0] == description_head
        and ("left distance [%d-%d] bp" % PATTERN_B_REQUEST) in description[1]
        and ("right distance [%d-%d] bp" % PATTERN_B_REQUEST) in description[1]
        and all(rejects_pattern_spec(item) for item in malformed)
        and all(report.anchor_lines.get(name) for name in (
            "pattern_spec.y_centered_kind", "runner.y_extract_command",
            "runner.y_min_left", "motifs.y_left_window",
            "motifs.y_right_window"))
    )

    runs = []
    with tempfile.TemporaryDirectory(prefix="pattern_b_probe_") as tmp:
        for label, request in (
            ("request_a", (PATTERN_B_REQUEST, PATTERN_B_REQUEST)),
            ("request_b", (PATTERN_B_REQUEST,
                           PATTERN_B_TIGHT_RIGHT_REQUEST)),
        ):
            run_dir = os.path.join(tmp, label)
            os.makedirs(run_dir)
            completed = run_pattern_b_request(genome, run_dir, request[0],
                                              request[1])
            if completed.returncode != 0:
                runs.append({
                    "returncode": completed.returncode,
                    "observed": None,
                    "distances": None,
                    "y_sites": None,
                    "stderr": completed.stderr.decode(
                        "utf-8", "replace").strip().splitlines()[-1:],
                })
                continue
            observed = {}
            distances = {}
            for side in ("left", "right"):
                rows = read_pattern_b_occurrences(run_dir, side)
                observed[side] = sorted(pattern_b_key(row) for row in rows)
                distances[side] = sorted(
                    y_start - row["motif_end"] if side == "left"
                    else row["motif_start"] - y_end for row in rows)
            runs.append({
                "returncode": 0,
                "observed": observed,
                "distances": distances,
                "y_sites": read_pattern_b_y_sites(run_dir),
                "stderr": [],
            })

    first, second = runs
    expected_y_sites = [(1, "chr1", y_start, y_end, "+")]
    parts = {
        "fixture": fixture_ok,
        "rejected_copies_in_scan_window": rejected_in_window,
        "planted_distances": (
            wanted_distances["left"] == [5, 14]
            and wanted_distances["right"] == [4, 12]
            and rejected_distances == [PATTERN_B_MAX_DISTANCE + 1] * 2),
        "layout_contract": contract_ok,
        "request_left_3_20_right_3_20": (
            first["returncode"] == 0
            and first["observed"] == wanted
            and first["y_sites"] == expected_y_sites),
        "request_left_3_20_right_5_20": (
            second["returncode"] == 0
            and second["observed"]["left"] == wanted["left"]
            and second["distances"]["left"] == wanted_distances["left"]
            and second["observed"]["right"]
            == [pattern_b_key(expected["right_minus"])]
            and second["distances"]["right"]
            == [expected["right_minus"]["distance"]]),
    }
    failed = sorted(name for name, value in parts.items() if not value)
    if not failed:
        detail = (
            "left[%d-%d] right[%d-%d] -> %d Y site(s), left distances %s, "
            "right distances %s; left[%d-%d] right[%d-%d] -> left distances %s "
            "unchanged, right distances %s; the two copies at distance %d sat "
            "inside the scan windows and were dropped"
            % (PATTERN_B_REQUEST[0], PATTERN_B_REQUEST[1],
               PATTERN_B_REQUEST[0], PATTERN_B_REQUEST[1],
               len(first["y_sites"]), first["distances"]["left"],
               first["distances"]["right"],
               PATTERN_B_REQUEST[0], PATTERN_B_REQUEST[1],
               PATTERN_B_TIGHT_RIGHT_REQUEST[0],
               PATTERN_B_TIGHT_RIGHT_REQUEST[1],
               second["distances"]["left"], second["distances"]["right"],
               PATTERN_B_MAX_DISTANCE + 1))
    else:
        detail = ("failed parts: %s; exit codes %s/%s; stderr %s"
                  % (failed, first["returncode"], second["returncode"],
                     first["stderr"] or second["stderr"]))
    report.check("middle_element_constraint", "pattern_b_end_to_end",
                 not failed, detail)


class Report:
    def __init__(self):
        self.checks = []
        self.anchor_lines = {}

    def check(self, column, name, ok, detail):
        self.checks.append({"column": column, "name": name, "ok": bool(ok),
                            "detail": detail})
        return bool(ok)

    def capability(self, column):
        return all(item["ok"] for item in self.checks
                   if item["column"] == column)


def run_checks():
    report = Report()

    for name, (relative_path, needle) in ANCHORS.items():
        line = locate(relative_path, needle)
        report.anchor_lines[name] = ("%s:%s" % (relative_path, line)
                                     if line else None)
    missing = sorted(name for name, value in report.anchor_lines.items()
                     if value is None)
    report.check("anchors", "anchors_present", not missing,
                 "missing anchors: %s" % (missing or "none"))

    try:
        flank_interval, get_flank, helper_lines = load_pair_helpers()
        report.check("pair_side_independent", "pair_helpers_loaded", True,
                     "flank_interval=%s:%s get_flank=%s:%s"
                     % (PAIR_HELPERS_PATH, helper_lines["flank_interval"],
                        PAIR_HELPERS_PATH, helper_lines["get_flank"]))
    except Exception as exc:  # pragma: no cover - reported as a failure
        report.check("pair_side_independent", "pair_helpers_loaded", False,
                     "could not load pair helpers: %r" % (exc,))
        return report

    # (a) IUPAC PAM/TAM -----------------------------------------------------
    sequence_hits = production_guides(SEQ_VNG, 20, "VNG", "3prime", True)
    coordinate_anchors = [report.anchor_lines.get("gui.bed_regions"),
                          report.anchor_lines.get("search_indexed.pam_side")]
    report.check(
        "input_model", "sequence_and_coordinate_input",
        len(sequence_hits) >= 1 and all(coordinate_anchors),
        "raw sequence input -> %d guide(s); coordinate-input anchors -> %s"
        % (len(sequence_hits), coordinate_anchors),
    )

    for label, sequence, pam, expected_hits in (
        ("VNG", SEQ_VNG, "VNG", 2),
        ("NNGRRT", SEQ_NNGRRT, "NNGRRT", 1),
    ):
        expected = reference_guides(sequence, 20, pam, "3prime", True)
        actual = production_guides(sequence, 20, pam, "3prime", True)
        report.check(
            "custom_pam_tam", "iupac_pam_%s" % label,
            actual == expected and len(actual) == expected_hits,
            "pam=%s hits=%d (reference %d, expected %d) %s"
            % (pam, len(actual), len(expected), expected_hits, actual),
        )
    expanded = {"".join(REFERENCE_IUPAC[code] for code in pam)
                for pam in ("VNG", "NNGRRT", "TTTV", "NGG")}
    report.check(
        "custom_pam_tam", "iupac_alphabet",
        set(REFERENCE_IUPAC) == set("ACGTURYSWKMBDHVN")
        and all(set(item) <= set("ACGT") for item in expanded),
        "reference IUPAC table covers ACGTUNRYSWKMBDHV; expanded: %s"
        % sorted(expanded),
    )

    # (b) non-NGG PAM, 3' and 5' of the spacer ----------------------------
    for label, sequence, expected_hits, opposite_hits in (
        ("3prime", SEQ_PAM_3PRIME, [("+", 4, 24, "TTTA")], []),
        ("5prime", SEQ_PAM_5PRIME, [("+", 7, 27, "TTTA")], []),
    ):
        expected = reference_guides(sequence, 20, "TTTV", label, True)
        actual = production_guides(sequence, 20, "TTTV", label, True)
        other = "5prime" if label == "3prime" else "3prime"
        opposite = production_guides(sequence, 20, "TTTV", other, True)
        report.check(
            "custom_orientation", "tttv_%s" % label,
            actual == expected == expected_hits and opposite == opposite_hits,
            "pam=TTTV side=%s hits=%s (same PAM on the opposite side: %s)"
            % (label, actual, opposite),
        )
    hits_3p = production_guides(SEQ_PAM_3PRIME, 20, "TTTV", "3prime", True)
    report.check(
        "custom_pam_tam", "non_ngg_pam",
        len(hits_3p) == 1 and all(row[3].startswith("TTT") for row in hits_3p),
        "TTTV (non-NGG) accepted: %s" % (hits_3p,),
    )

    # (c) variable spacer length -------------------------------------------
    for spacer_len in (18, 20, 23):
        sequence = "TTTT" + SPACER + "AGG" + "TTTT"
        expected = reference_guides(sequence, spacer_len, "NGG", "3prime", True)
        actual = production_guides(sequence, spacer_len, "NGG", "3prime", True)
        widths = {row[2] - row[1] for row in actual}
        report.check(
            "custom_target_length", "spacer_len_%d" % spacer_len,
            actual == expected and len(actual) >= 1 and widths == {spacer_len},
            "spacer_len=%d hits=%d widths=%s (reference %d)"
            % (spacer_len, len(actual), sorted(widths), len(expected)),
        )

    # (d)(e) orientation and both strands ----------------------------------
    both = production_guides(SEQ_VNG, 20, "VNG", "3prime", True)
    forward = production_guides(SEQ_VNG, 20, "VNG", "3prime", False)
    report.check(
        "custom_orientation", "strand_switch",
        {row[0] for row in forward} == {"+"} and {row[0] for row in both} == {"+", "-"},
        "allow_reverse=False -> %s; allow_reverse=True -> %s"
        % (sorted({row[0] for row in forward}), sorted({row[0] for row in both})),
    )

    # exhaustive enumeration of every occurrence ---------------------------
    positions = find_all_iupac_positions("GGTTATCCTTATGGTTATTATAA", "TTAT")
    overlapping = find_all_iupac_positions("TTATTAT", "TTAT")
    report.check(
        "enumerates_all_occurrences", "iupac_all_positions",
        positions == [2, 8, 14, 17] and overlapping == [0, 3],
        "TTAT in 23 nt probe -> %s; overlapping probe -> %s"
        % (positions, overlapping),
    )
    expected = reference_guides(SEQ_ALL_OCCURRENCES, 20, "NGG", "3prime", True)
    actual = production_guides(SEQ_ALL_OCCURRENCES, 20, "NGG", "3prime", True)
    strands = {row[0] for row in actual}
    report.check(
        "enumerates_all_occurrences", "guides_all_sites",
        actual == expected and len(actual) >= 4 and strands == {"+", "-"},
        "NGG sites on a 4-block sequence: production=%d reference=%d strands=%s"
        % (len(actual), len(expected), sorted(strands)),
    )

    # (f) paired layout, four strand combinations --------------------------
    combos, gaps = enumerate_pairs(PAIR_SEQ, LEFT_MOTIF, RIGHT_MOTIF, 5, 7)
    report.check(
        "middle_element_constraint", "four_strand_combos",
        combos == set(STRAND_COMBOS),
        "strand combinations found: %s" % sorted(combos),
    )
    report.check(
        "middle_element_constraint", "gap_window_enforced",
        bool(gaps) and set(gaps) == {6},
        "gaps inside [5, 7]: %s" % sorted(set(gaps)),
    )
    empty_combos, empty_gaps = enumerate_pairs(PAIR_SEQ, LEFT_MOTIF, RIGHT_MOTIF,
                                               100, 200)
    report.check(
        "middle_element_constraint", "gap_window_rejects",
        not empty_combos and not empty_gaps,
        "gaps inside [100, 200]: %s" % (sorted(set(empty_gaps)),),
    )

    lpos = find_all_iupac_positions(PAIR_SEQ, LEFT_MOTIF)[0]
    rpos = find_all_iupac_positions(PAIR_SEQ, RIGHT_MOTIF)[0]
    left_span = flank_interval(len(PAIR_SEQ), lpos, len(LEFT_MOTIF),
                               "upstream", 4, "plus")
    right_span = flank_interval(len(PAIR_SEQ), rpos, len(RIGHT_MOTIF),
                                "downstream", 7, "minus")
    left_flank = get_flank(PAIR_SEQ, lpos, len(LEFT_MOTIF), "upstream", 4, "plus")
    right_flank = get_flank(PAIR_SEQ, rpos, len(RIGHT_MOTIF), "downstream", 7,
                            "minus")
    flipped = flank_interval(len(PAIR_SEQ), lpos, len(LEFT_MOTIF), "upstream", 4,
                             "minus")
    report.check(
        "pair_side_independent", "independent_length_and_side",
        (left_span[1] - left_span[0] == 4
         and right_span[1] - right_span[0] == 7
         and left_flank == PAIR_SEQ[left_span[0]:left_span[1]]
         and right_flank == PAIR_SEQ[right_span[0]:right_span[1]]
         and flipped == flank_interval(len(PAIR_SEQ), lpos, len(LEFT_MOTIF),
                                       "downstream", 4, "plus")),
        "left upstream/4 -> %s %r; right downstream/7 -> %s %r; strand flips side"
        % (left_span, left_flank, right_span, right_flank),
    )

    # Pattern B (Y-centred layout), driven through the real extractor --------
    check_pattern_b_end_to_end(report)
    return report


CAPABILITY_COLUMNS = ("custom_pam_tam", "custom_target_length",
                      "custom_orientation", "middle_element_constraint",
                      "enumerates_all_occurrences", "pair_side_independent")


def build_record(report):
    record = {
        "tool": "This work (TargetDesign-workbench)",
        "year": "2026",
        "input_model": "both" if report.capability("input_model") else "sequence",
    }
    for column in CAPABILITY_COLUMNS:
        record[column] = report.capability(column)
    failed = [item["name"] for item in report.checks if not item["ok"]]
    record["checks_passed"] = sum(1 for item in report.checks if item["ok"])
    record["checks_total"] = len(report.checks)
    record["failed_checks"] = failed
    record["ok"] = not failed
    return record


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Probe the C1 expressiveness claims of this repository")
    parser.add_argument("--json", action="store_true",
                        help="emit one machine-readable summary record")
    args = parser.parse_args(argv)

    report = run_checks()
    record = build_record(report)

    if args.json:
        payload = dict(record)
        payload["anchors"] = report.anchor_lines
        payload["checks"] = report.checks
        payload["python"] = platform.python_version()
        payload["platform"] = platform.platform()
        payload["script"] = os.path.join("tools", "expressiveness_probe.py")
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        for item in report.checks:
            print("[%s] %-28s %s" % ("PASS" if item["ok"] else "FAIL",
                                     item["name"], item["detail"]))
        print("")
        for name, value in sorted(report.anchor_lines.items()):
            print("anchor %-28s %s" % (name, value))
        print("")
        print("capabilities: %s" % ", ".join(
            "%s=%s" % (column, record[column]) for column in CAPABILITY_COLUMNS))
        print("%d/%d checks passed" % (record["checks_passed"],
                                       record["checks_total"]))

    return 0 if record["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
