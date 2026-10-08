import os
import sys
import unittest
from types import SimpleNamespace


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHARED = os.path.join(ROOT, "shared")
sys.path.insert(0, SHARED)

from design.pattern_spec import (  # noqa: E402
    MotifSpec,
    PatternKind,
    PatternSpec,
    Side,
    default_pattern_name,
)


class PatternSpecTests(unittest.TestCase):
    def test_single_motif_spec_validates_and_describes(self):
        spec = PatternSpec(
            kind=PatternKind.SINGLE_MOTIF_FLANK,
            motif=MotifSpec("TTAANN", flank_length=10, side=Side.UPSTREAM),
        )
        self.assertIn("[upstream flank 10 bp]", spec.describe())
        self.assertIn("[TTAANN]", spec.describe())

    def test_single_motif_requires_motif(self):
        spec = PatternSpec(kind=PatternKind.SINGLE_MOTIF_FLANK)
        with self.assertRaises(ValueError):
            spec.validate()

    def test_motif_gap_motif_validates_and_describes(self):
        spec = PatternSpec(
            kind=PatternKind.MOTIF_GAP_MOTIF,
            left=MotifSpec("ATCG", 5, Side.UPSTREAM),
            right=MotifSpec("CCGG", 7, Side.DOWNSTREAM),
            min_gap=10,
            max_gap=20,
        )
        description = spec.describe()
        self.assertIn("gap[10-20 bp]", description)
        self.assertIn("[upstream flank 5 bp][ATCG]", description)
        self.assertIn("[CCGG][downstream flank 7 bp]", description)

    def test_gap_range_is_validated(self):
        spec = PatternSpec(
            kind=PatternKind.MOTIF_GAP_MOTIF,
            left=MotifSpec("ATCG", 5, Side.UPSTREAM),
            right=MotifSpec("CCGG", 7, Side.DOWNSTREAM),
            min_gap=20,
            max_gap=10,
        )
        with self.assertRaises(ValueError):
            spec.validate()

    def test_y_centered_motif_validates_and_describes(self):
        spec = PatternSpec(
            kind=PatternKind.Y_CENTERED_MOTIFS,
            y_sequence="GGTACC",
            left=MotifSpec("RAC", 6, Side.DOWNSTREAM),
            right=MotifSpec("GYN", 8, Side.UPSTREAM),
            left_min_distance=2,
            left_max_distance=30,
            right_min_distance=0,
            right_max_distance=25,
        )
        description = spec.describe()
        self.assertIn("Y(GGTACC)", description)
        self.assertIn("left distance [2-30] bp", description)
        self.assertIn("right distance [0-25] bp", description)

    def test_invalid_iupac_sequence_is_rejected(self):
        with self.assertRaises(ValueError):
            MotifSpec("ATCZ")

    def test_default_pattern_name_for_each_kind(self):
        single = PatternSpec(
            kind=PatternKind.SINGLE_MOTIF_FLANK,
            motif=MotifSpec("ttag"),
        )
        gap = PatternSpec(
            kind=PatternKind.MOTIF_GAP_MOTIF,
            left=MotifSpec("TTAG"),
            right=MotifSpec("TCAA"),
            min_gap=10,
            max_gap=40,
        )
        y_centered = PatternSpec(
            kind=PatternKind.Y_CENTERED_MOTIFS,
            y_sequence="TTaW",
            left=MotifSpec("TTAT"),
            right=MotifSpec("TTAT"),
            left_min_distance=0,
            left_max_distance=10,
            right_min_distance=0,
            right_max_distance=10,
        )
        self.assertEqual(default_pattern_name(single), "TTAG")
        self.assertEqual(default_pattern_name(gap), "TTAG_10-40_TCAA")
        self.assertEqual(
            default_pattern_name(y_centered), "TTAT_TTAW_TTAT"
        )

    def test_default_pattern_name_cleans_and_falls_back(self):
        dirty = SimpleNamespace(
            kind=PatternKind.SINGLE_MOTIF_FLANK,
            motif=SimpleNamespace(sequence=" ..TTAG? "),
            validate=lambda: None,
        )
        empty = SimpleNamespace(
            kind=PatternKind.SINGLE_MOTIF_FLANK,
            motif=SimpleNamespace(sequence="???"),
            validate=lambda: None,
        )
        self.assertEqual(default_pattern_name(dirty), "TTAG")
        self.assertEqual(default_pattern_name(empty), "pattern")

    def test_default_pattern_name_rejects_invalid_spec(self):
        with self.assertRaises(ValueError):
            default_pattern_name(
                PatternSpec(kind=PatternKind.SINGLE_MOTIF_FLANK)
            )

    def test_candidate_columns_match_pattern_kind(self):
        single = PatternSpec(
            kind=PatternKind.SINGLE_MOTIF_FLANK,
            motif=MotifSpec("AAAA"),
        )
        paired = PatternSpec(
            kind=PatternKind.MOTIF_GAP_MOTIF,
            left=MotifSpec("AAAA"),
            right=MotifSpec("TTTT"),
            min_gap=1,
            max_gap=5,
        )
        self.assertIn("motif_seq", single.candidate_columns())
        self.assertIn("gap", paired.candidate_columns())


if __name__ == "__main__":
    unittest.main()
