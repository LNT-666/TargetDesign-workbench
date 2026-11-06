import os
import sys
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "shared"))

from output.output_columns import (  # noqa: E402
    format_display_value,
    format_output_row,
    format_output_value,
    mismatch_bucket_columns,
    mismatch_bucket_values,
    nonempty_columns,
    nonempty_indices,
)


class MismatchBucketTests(unittest.TestCase):
    def test_columns_follow_max_mismatch(self):
        self.assertEqual(mismatch_bucket_columns(0), ["MM0"])
        self.assertEqual(
            mismatch_bucket_columns(2), ["MM0", "MM1", "MM2"])
        self.assertEqual(
            mismatch_bucket_columns(4),
            ["MM0", "MM1", "MM2", "MM3", "MM4"],
        )

    def test_final_bucket_is_cumulative(self):
        counts = [2, 3, 4, 5, 6, 7]
        self.assertEqual(mismatch_bucket_values(counts, 2), [2, 3, 22])
        self.assertEqual(mismatch_bucket_values(counts, 3), [2, 3, 4, 18])
        self.assertEqual(
            mismatch_bucket_values(counts, 4), [2, 3, 4, 5, 13])

    def test_zero_budget_reports_only_exact_zero_bucket(self):
        self.assertEqual(mismatch_bucket_values([2, 3, 4], 0), [2])

    def test_nonempty_columns_drop_blank_cells_but_keep_zero(self):
        rows = [{
            "empty": "",
            "missing": None,
            "spaces": "   ",
            "number_zero": 0,
            "string_zero": "0",
            "value": "x",
        }]
        self.assertEqual(
            nonempty_columns(
                rows,
                ["empty", "missing", "spaces", "number_zero",
                 "string_zero", "value"],
            ),
            ["number_zero", "string_zero", "value"],
        )
        self.assertEqual(
            nonempty_indices([["", None, "   ", 0, "0", "x"]]),
            [3, 4, 5],
        )


class NumericFormattingTests(unittest.TestCase):
    def test_real_values_keep_two_decimal_places(self):
        self.assertEqual(format_output_value(0.207207207), "0.21")
        self.assertEqual(format_output_value(44.45), "44.45")
        self.assertEqual(format_output_value(0.5625), "0.56")
        self.assertEqual(format_output_value(-0.0), "0.00")

    def test_counts_and_text_are_not_reformatted(self):
        self.assertEqual(format_output_value(3), "3")
        self.assertEqual(format_output_value(True), "True")
        self.assertEqual(format_output_value(None), "")
        self.assertEqual(format_output_value("uniq_611"), "uniq_611")
        self.assertEqual(format_output_value(float("nan")), "nan")

    def test_display_formats_legacy_decimal_strings(self):
        self.assertEqual(format_display_value("0.207207207"), "0.21")
        self.assertEqual(format_display_value("0.5"), "0.50")
        self.assertEqual(format_display_value("1e-05"), "0.00")
        self.assertEqual(format_display_value("00012"), "00012")
        self.assertEqual(format_display_value("RNA1.2_minus"), "RNA1.2_minus")

    def test_row_formatting_returns_a_copy(self):
        row = {"score": 0.1234, "count": 2, "seq": "ACGT"}
        formatted = format_output_row(row)
        self.assertEqual(
            formatted, {"score": "0.12", "count": "2", "seq": "ACGT"})
        self.assertEqual(row["score"], 0.1234)


if __name__ == "__main__":
    unittest.main()
