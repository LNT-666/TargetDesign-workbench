import os
import sys
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "shared"))

from output.output_columns import (  # noqa: E402
    mismatch_bucket_columns,
    mismatch_bucket_values,
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


if __name__ == "__main__":
    unittest.main()
