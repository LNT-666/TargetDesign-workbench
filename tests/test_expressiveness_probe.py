#!/usr/bin/env python3
"""Regression tests for the expressiveness evidence probe."""

import contextlib
import io
import json
import os
import sys
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tools import expressiveness_probe as probe  # noqa: E402


def _passing_pattern_b(report):
    """Keep the check count stable without rerunning the subprocess fixture."""
    report.check("middle_element_constraint", "pattern_b_end_to_end",
                 True, "stubbed for mutation-only probe regression")


class ExpressivenessProbeTests(unittest.TestCase):
    def test_cross_line_anchor_and_real_probe(self):
        anchor = probe.locate(
            "Target_xbp_Target/extract_complex_queries.py",
            "<min_gap> <max_gap> <left_side> <left_len> <right_side> <right_len>",
        )
        self.assertEqual(anchor, 39)

        report = probe.run_checks()
        record = probe.build_record(report)

        self.assertEqual(record["checks_total"], 20)
        self.assertEqual(record["checks_passed"], 20, record["failed_checks"])
        self.assertEqual(record["failed_checks"], [])
        self.assertTrue(record["ok"])

    def test_missing_anchor_fails_main_and_keeps_check_count(self):
        missing_text = "anchor-that-does-not-exist-in-the-query-extractor"
        with mock.patch.dict(
            probe.ANCHORS,
            {"queries.gap_args": (
                "Target_xbp_Target/extract_complex_queries.py", missing_text)},
        ), mock.patch.object(
            probe, "check_pattern_b_end_to_end", new=_passing_pattern_b,
        ):
            report = probe.run_checks()
        record = probe.build_record(report)

        self.assertIsNone(report.anchor_lines["queries.gap_args"])
        self.assertIn("anchors_present", record["failed_checks"])
        self.assertEqual(record["checks_total"], 20)
        self.assertFalse(record["ok"])

        output = io.StringIO()
        with mock.patch.object(probe, "run_checks", return_value=report), \
                contextlib.redirect_stdout(output):
            returncode = probe.main(["--json"])
        payload = json.loads(output.getvalue())

        self.assertEqual(returncode, 1)
        self.assertEqual(payload["checks_total"], 20)
        self.assertIn("anchors_present", payload["failed_checks"])

    def test_reverse_strand_mutation_fails_strand_switch(self):
        real_find_guides = probe.find_guides

        def plus_only(*args, **kwargs):
            kwargs["allow_reverse"] = False
            return real_find_guides(*args, **kwargs)

        with mock.patch.object(probe, "find_guides", new=plus_only), \
                mock.patch.object(
                    probe, "check_pattern_b_end_to_end",
                    new=_passing_pattern_b,
                ):
            report = probe.run_checks()
        record = probe.build_record(report)

        self.assertFalse(record["custom_orientation"])
        self.assertIn("strand_switch", record["failed_checks"])
        self.assertEqual(record["checks_total"], 20)


if __name__ == "__main__":
    unittest.main()
