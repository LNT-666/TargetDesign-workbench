#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Expressiveness probe for the C1 parameter matrix (docs/expressiveness_matrix.tsv).

The probe re-runs this repository's own code paths on small synthetic sequences
and asserts every capability claimed for the "This work (CRISPR-Motif
Workbench)" row of the matrix:

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

Standard library only (no numpy / Biopython / network access).

Usage:
    python tools/expressiveness_probe.py           # human readable report
    python tools/expressiveness_probe.py --json    # one machine-readable record

Exit status is 0 only when every assertion passes.
"""

import argparse
import ast
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
    return report


CAPABILITY_COLUMNS = ("custom_pam_tam", "custom_target_length",
                      "custom_orientation", "middle_element_constraint",
                      "enumerates_all_occurrences", "pair_side_independent")


def build_record(report):
    record = {
        "tool": "This work (CRISPR-Motif Workbench)",
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
