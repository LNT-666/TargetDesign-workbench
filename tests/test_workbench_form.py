#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Focused tests for the shared Pattern Designer form layer.

These tests never touch tkinter: ``shared/design/workbench_form.py`` is the
single place where the desktop workbench and the web workbench turn form
values into a PatternSpec / RunnerConfig, so pinning it down here pins down
both front ends.
"""

import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHARED = os.path.join(ROOT, "shared")
for _path in (ROOT, SHARED):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from design.pattern_spec import PatternKind, Side  # noqa: E402
from design.system_presets import get_preset  # noqa: E402
from design.workbench_form import (  # noqa: E402
    PAIR_RANK_POLICY_FIELDS,
    WorkbenchFormState,
    active_side_updates,
    build_pattern_spec,
    build_runner_config,
    coerce_bool,
    default_run_label,
    pair_rank_policy_values,
    readiness_errors,
    resolve_side_model_selection,
    resolved_memory_limit,
    search_timeout_s,
    side_model_options,
    side_preset_updates,
    split_model_selection,
)
from utils.paths import default_output_dir  # noqa: E402


class FormTestCase(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.mkdtemp(prefix="workbench_form_")
        self.out_dir = os.path.join(self.tempdir, "out")
        os.makedirs(self.out_dir, exist_ok=True)
        self.search_fasta = self._write("search.fa", ">c1\nACGTACGTACGTACGTACGT\n")
        self.genome_fasta = self._write(
            "genome.fa", ">chr1\n" + "ACGT" * 60 + "\n")
        self.mask_fasta = self._write("mask.fa", ">m1\nACGTACGTACGTACGTACGT\n")

    def _write(self, name, text):
        path = os.path.join(self.tempdir, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
        return path

    def single_state(self, **overrides):
        return WorkbenchFormState(
            values=self.single_values(**overrides), active_side="target")

    def single_values(self, **overrides):
        values = {
            "search_fasta": self.search_fasta,
            "genome_fasta": self.genome_fasta,
            "output_dir": self.out_dir,
            "motif": "TTAT",
            "flank": "5",
            "side": "upstream",
        }
        values.update(overrides)
        return values

    def pair_values(self, **overrides):
        values = {
            "search_fasta": self.search_fasta,
            "genome_fasta": self.genome_fasta,
            "output_dir": self.out_dir,
            "left_motif": "TTAT",
            "left_flank": "4",
            "left_side": "upstream",
            "right_motif": "GGG",
            "right_flank": "6",
            "right_side": "downstream",
            "min_gap": "10",
            "max_gap": "40",
        }
        values.update(overrides)
        return values

    def policy_values(self, blank=False, **overrides):
        values = {}
        if not blank:
            values = {"pair_rank_%s" % name: "1"
                      for name in PAIR_RANK_POLICY_FIELDS}
        for key, value in overrides.items():
            if key in PAIR_RANK_POLICY_FIELDS:
                values["pair_rank_%s" % key] = value
            else:
                values[key] = value
        return values


class SingleModeTests(FormTestCase):
    def test_spec_and_config_use_the_form_values(self):
        state = self.single_state()
        spec = build_pattern_spec(state)
        self.assertIs(spec.kind, PatternKind.SINGLE_MOTIF_FLANK)
        self.assertEqual(spec.motif.sequence, "TTAT")
        self.assertEqual(spec.motif.flank_length, 5)
        self.assertIs(spec.motif.side, Side.UPSTREAM)
        spec.validate()

        config = build_runner_config(state, spec)
        self.assertEqual(config.search_fasta, self.search_fasta)
        self.assertEqual(config.genome_fasta, self.genome_fasta)
        self.assertEqual(config.output_dir, default_output_dir())
        self.assertEqual(config.mode, "preset")
        self.assertEqual(config.preset, "cas9")
        self.assertEqual(config.pam_motif, "TTAT")
        self.assertTrue(config.require_pam)
        self.assertEqual(config.timeout_s, None)
        self.assertEqual(readiness_errors(state), [])

    def test_bed_mode_moves_the_search_input_to_regions(self):
        bed = self._write("regions.bed", "chr1\t0\t40\n")
        state = WorkbenchFormState(
            values=self.single_values(bed_regions=bed),
            input_mode="bed",
            active_side="target",
        )
        self.assertTrue(state.is_bed_mode())
        config = build_runner_config(state)
        self.assertEqual(config.regions, bed)
        self.assertEqual(config.search_fasta, "")
        self.assertEqual(readiness_errors(state), [])

    def test_default_run_label_is_system_and_target_name(self):
        state = self.single_state()
        expected = get_preset("cas9")["label"].split("/")[0].strip() + "_search"
        self.assertEqual(default_run_label(state), expected)

    def test_result_label_overrides_the_default(self):
        state = self.single_state(result_label="my_run")
        self.assertEqual(build_runner_config(state).run_label, "my_run")


class PairModeTests(FormTestCase):
    def test_gap_pair_spec_and_config(self):
        values = self.pair_values(**self.policy_values())
        state = WorkbenchFormState(
            values=values, mode=PatternKind.MOTIF_GAP_MOTIF.value)
        spec = build_pattern_spec(state)
        self.assertIs(spec.kind, PatternKind.MOTIF_GAP_MOTIF)
        self.assertEqual(spec.left.sequence, "TTAT")
        self.assertEqual(spec.left.flank_length, 4)
        self.assertIs(spec.left.side, Side.UPSTREAM)
        self.assertEqual(spec.right.sequence, "GGG")
        self.assertEqual(spec.right.flank_length, 6)
        self.assertIs(spec.right.side, Side.DOWNSTREAM)
        self.assertEqual(spec.min_gap, 10)
        self.assertEqual(spec.max_gap, 40)
        spec.validate()

        config = build_runner_config(state, spec)
        self.assertFalse(config.require_pam)
        self.assertEqual(config.preset, "cas9")
        self.assertEqual(config.left_preset, "cas9")
        self.assertEqual(config.right_preset, "cas9")
        self.assertEqual(readiness_errors(state), [])

    def test_gap_pair_requires_every_policy_value(self):
        state = WorkbenchFormState(
            values=self.pair_values(), mode=PatternKind.MOTIF_GAP_MOTIF.value)
        policy, missing = pair_rank_policy_values(state)
        self.assertEqual(policy, {})
        self.assertEqual(sorted(missing), sorted(PAIR_RANK_POLICY_FIELDS))
        errors = readiness_errors(state)
        self.assertTrue(
            any(error.startswith("PairRank policy values required") for error in errors),
            errors,
        )
        self.assertIsNone(build_runner_config(state).pair_rank_policy)

    def test_partial_policy_is_reported_field_by_field(self):
        values = self.pair_values(
            **self.policy_values(blank=True, e_high="2.5", h_max=""))
        state = WorkbenchFormState(
            values=values, mode=PatternKind.MOTIF_GAP_MOTIF.value)
        policy, missing = pair_rank_policy_values(state)
        self.assertEqual(policy, {"e_high": 2.5})
        self.assertEqual(
            missing,
            [name for name in PAIR_RANK_POLICY_FIELDS if name != "e_high"])
        self.assertTrue(
            any("h_max" in error for error in readiness_errors(state)))

    def test_y_centered_spec_and_config(self):
        values = self.pair_values(**self.policy_values(
            y_sequence="TTTT",
            left_min_distance="3",
            left_max_distance="8",
            right_min_distance="4",
            right_max_distance="9",
        ))
        state = WorkbenchFormState(
            values=values, mode=PatternKind.Y_CENTERED_MOTIFS.value)
        spec = build_pattern_spec(state)
        self.assertIs(spec.kind, PatternKind.Y_CENTERED_MOTIFS)
        self.assertEqual(spec.y_sequence, "TTTT")
        self.assertEqual(spec.left_min_distance, 3)
        self.assertEqual(spec.left_max_distance, 8)
        self.assertEqual(spec.right_min_distance, 4)
        self.assertEqual(spec.right_max_distance, 9)
        spec.validate()
        self.assertEqual(readiness_errors(state), [])
        self.assertEqual(default_run_label(state, spec), "TTAT-TTTT-GGG")


class ErrorBranchTests(FormTestCase):
    def test_missing_and_unreadable_inputs_are_reported_in_order(self):
        missing = os.path.join(self.tempdir, "nope.fa")
        state = WorkbenchFormState(values={
            "search_fasta": missing,
            "genome_fasta": missing,
            "mask_fasta": missing,
        }, active_side="target")
        errors = readiness_errors(state)
        self.assertIn("Search FASTA not found: %s" % missing, errors)
        self.assertIn("Genome FASTA not found: %s" % missing, errors)
        self.assertIn("Mask FASTA not found: %s" % missing, errors)

    def test_empty_inputs_report_required_fields(self):
        state = WorkbenchFormState(
            values={"output_dir": self.out_dir}, active_side="target")
        errors = readiness_errors(state)
        self.assertIn("Search FASTA is required", errors)
        self.assertIn("Genome FASTA is required", errors)

    def test_bed_mode_reports_missing_regions(self):
        bed = os.path.join(self.tempdir, "nope.bed")
        state = WorkbenchFormState(
            values=self.single_values(bed_regions=bed), input_mode="bed",
            active_side="target")
        errors = readiness_errors(state)
        self.assertIn("BED Regions not found: %s" % bed, errors)
        self.assertFalse(any("Search FASTA" in error for error in errors))

    def test_memory_limit_modes(self):
        self.assertEqual(
            resolved_memory_limit(self.single_state(memory_mode="unlimited")), 0)
        self.assertGreater(resolved_memory_limit(self.single_state()), 0)

        low = self.single_state(memory_mode="custom", max_memory_mb="256")
        with self.assertRaises(ValueError) as caught:
            resolved_memory_limit(low)
        self.assertIn("at least 512", str(caught.exception))
        self.assertTrue(any(
            error.startswith("Memory limit:") for error in readiness_errors(low)))

        text_value = self.single_state(memory_mode="custom", max_memory_mb="lots")
        with self.assertRaises(ValueError):
            resolved_memory_limit(text_value)

        unknown = self.single_state(memory_mode="wild")
        with self.assertRaises(ValueError) as caught:
            resolved_memory_limit(unknown)
        self.assertIn("Unknown Memory Limit mode", str(caught.exception))

    def test_search_timeout_values(self):
        self.assertIsNone(search_timeout_s(self.single_state()))
        self.assertEqual(search_timeout_s(
            self.single_state(search_timeout_s="12.5")), 12.5)
        zero = self.single_state(search_timeout_s="0")
        with self.assertRaises(ValueError) as caught:
            search_timeout_s(zero)
        self.assertIn("greater than zero", str(caught.exception))
        self.assertTrue(any(
            error.startswith("Search timeout:") for error in readiness_errors(zero)))
        with self.assertRaises(ValueError):
            search_timeout_s(self.single_state(search_timeout_s="soon"))

    def test_pattern_errors_are_reported_last(self):
        state = self.single_state(motif="")
        errors = readiness_errors(state)
        self.assertEqual(len(errors), 1, errors)
        self.assertTrue(errors[-1].startswith("Pattern:"), errors)
        with self.assertRaises(ValueError):
            build_pattern_spec(state)


class PresetAndModelTests(unittest.TestCase):
    def test_cas12a_preset_updates_the_target_side(self):
        updates = side_preset_updates("cas12a", "target")
        self.assertEqual(updates["motif"], "TTTN")
        self.assertEqual(updates["flank"], "24")
        self.assertEqual(updates["side"], "downstream")
        self.assertEqual(updates["pam_mode"], "custom")
        self.assertEqual(updates["nuclease"], "cas12a")
        self.assertTrue(updates["require_pam"])

    def test_cas9_preset_updates_the_left_side(self):
        updates = side_preset_updates("cas9", "left")
        self.assertEqual(updates["left_motif"], "NGG")
        self.assertEqual(updates["left_side"], "upstream")
        self.assertTrue(updates["left_require_pam"])
        self.assertEqual(updates["nuclease"], "cas9")

    def test_side_model_options_follow_the_nuclease(self):
        cas9 = side_model_options("cas9")
        self.assertIn("cropsr", cas9["on_target"])
        self.assertIn("cfd", cas9["off_target"])
        self.assertEqual(cas9["on_target_default"], "cropsr")

        tnpb = side_model_options("tnpb")
        self.assertEqual(tnpb["on_target"], ["omega", "teep"])
        self.assertEqual(tnpb["off_target"], ["identity"])
        self.assertEqual(tnpb["on_target_default"], "omega")

        cas12a = side_model_options("cas12a")
        self.assertIn("rules", cas12a["on_target"])

    def test_resolve_side_model_selection(self):
        options = ["auto", "cropsr"]
        self.assertEqual(
            resolve_side_model_selection("auto", options, "cropsr"), "cropsr")
        self.assertEqual(
            resolve_side_model_selection("gone", options, "cropsr"), "cropsr")
        self.assertEqual(resolve_side_model_selection("gone", options), "auto")
        self.assertIsNone(resolve_side_model_selection("cropsr", options))

    def test_active_side_updates(self):
        state = WorkbenchFormState(
            values={"motif": "TTAT"},
            active_side="right",
            side_presets={"target": "cas9", "left": "cas9", "right": "cas12a"},
        )
        updates = active_side_updates(state)
        self.assertEqual(updates["nuclease"], "cas12a")
        self.assertTrue(updates["right_require_pam"])
        self.assertNotIn("require_pam", updates)

        cas9_side = WorkbenchFormState(
            values={"motif": "TTAT"},
            active_side="target",
            side_presets={"target": "cas9", "left": "cas9", "right": "cas9"},
        )
        self.assertIn("require_pam", active_side_updates(cas9_side))

    def test_helpers(self):
        self.assertTrue(coerce_bool("yes"))
        self.assertTrue(coerce_bool(1))
        self.assertFalse(coerce_bool("off"))
        self.assertFalse(coerce_bool(""))
        self.assertTrue(coerce_bool(None, True))
        self.assertEqual(
            split_model_selection("cropsr, cfd ; crispai"),
            ["cropsr", "cfd", "crispai"])
        self.assertEqual(split_model_selection(None), [])
        self.assertEqual(split_model_selection(""), [])


if __name__ == "__main__":
    unittest.main()