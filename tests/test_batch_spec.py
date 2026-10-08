import json
import os
import sys
import tempfile
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "shared"))

from design.batch_spec import (  # noqa: E402
    MAX_UNIT_ID,
    BatchGroup,
    BatchSpec,
    PatternVariant,
    ScopeSpec,
    build_unit_form_state,
    expand_scope_dir,
    load_batch_json,
    load_units_tsv,
    make_unit_id,
    normalize_units,
    scope_input_keys,
    spec_from_dict,
    spec_to_dict,
    validate_spec,
    write_batch_json,
)
from design.workbench_form import (  # noqa: E402
    build_pattern_spec,
    build_runner_config,
)


def _spec(groups=None, scopes=None, patterns=None, shared=None, label="batch1"):
    return BatchSpec(
        batch_label=label,
        shared=shared if shared is not None else {},
        scopes=scopes
        if scopes is not None
        else [
            ScopeSpec("a", search_fasta="a.fa"),
            ScopeSpec("b", search_fasta="b.fa"),
            ScopeSpec("c", regions="c.bed"),
        ],
        patterns=patterns
        if patterns is not None
        else [
            PatternVariant("P1", "single_motif_flank", {"motif": "TTAG"}),
            PatternVariant("P2", "single_motif_flank", {"motif": "TCAA"}),
        ],
        groups=groups
        if groups is not None
        else [
            BatchGroup("G1", ["a", "b"], ["P1"]),
            BatchGroup("G2", ["c"], ["P2"]),
        ],
    )


class NormalizeUnitsTests(unittest.TestCase):
    def test_expansion_order_and_dedup(self):
        spec = _spec(
            groups=[
                BatchGroup("G1", ["a", "b"], ["P1"]),
                BatchGroup("G2", ["a", "b"], ["P1", "P2"]),
            ]
        )
        units = normalize_units(spec)
        self.assertEqual(
            [(u.scope_id, u.pattern_id) for u in units],
            [("a", "P1"), ("b", "P1"), ("a", "P2"), ("b", "P2")],
        )
        self.assertEqual(units[0].unit_id, "a__P1")

    def test_unit_id_truncation_is_stable_and_unique(self):
        scope = "s" * 60
        pattern = "p" * 60
        first = make_unit_id(scope, pattern)
        self.assertEqual(first, make_unit_id(scope, pattern))
        self.assertEqual(len(first), MAX_UNIT_ID + 1 + 6)
        self.assertTrue(first.startswith(scope[:MAX_UNIT_ID]))
        self.assertNotEqual(first, make_unit_id(scope, pattern + "x"))


class ValidateSpecTests(unittest.TestCase):
    def test_unassigned_scope_is_an_error(self):
        spec = _spec(groups=[BatchGroup("G1", ["a"], ["P1"])])
        errors, _warnings = validate_spec(spec, dry_run=True)
        self.assertIn("scope b is not assigned to any group", errors)
        self.assertIn("scope c is not assigned to any group", errors)

    def test_unused_pattern_is_a_warning(self):
        spec = _spec(
            groups=[
                BatchGroup("G1", ["a", "b"], ["P1"]),
                BatchGroup("G2", ["c"], ["P1"]),
            ]
        )
        errors, warnings = validate_spec(spec, dry_run=True)
        self.assertEqual(errors, [])
        self.assertIn("pattern P2 is not used by any group", warnings)

    def test_reserved_keys_are_errors(self):
        spec = _spec(
            shared={"output_dir": "/tmp/x"},
            patterns=[
                PatternVariant("P1", "single_motif_flank", {"input_mode": "bed"}),
            ],
            groups=[BatchGroup("G1", ["a", "b", "c"], ["P1"])],
        )
        errors, _warnings = validate_spec(spec, dry_run=True)
        self.assertIn("shared must not set reserved key 'output_dir'", errors)
        self.assertIn(
            "pattern P1 overlay must not set reserved key 'input_mode'", errors
        )

    def test_scope_needs_exactly_one_input(self):
        spec = _spec(
            scopes=[ScopeSpec("a")],
            patterns=[PatternVariant("P1", "single_motif_flank", {"motif": "TTAG"})],
            groups=[BatchGroup("G1", ["a"], ["P1"])],
        )
        errors, _warnings = validate_spec(spec, dry_run=True)
        self.assertIn(
            "scope a must set exactly one of search_fasta/regions (neither set)",
            errors,
        )

    def test_dry_run_downgrades_missing_files_to_warnings(self):
        strict_errors, _ = validate_spec(_spec(), dry_run=False)
        dry_errors, dry_warnings = validate_spec(_spec(), dry_run=True)
        self.assertTrue(
            any("not found" in message for message in strict_errors)
        )
        self.assertEqual(dry_errors, [])
        self.assertTrue(any("not found" in message for message in dry_warnings))


class ScopeTests(unittest.TestCase):
    def test_scope_input_keys(self):
        self.assertEqual(
            scope_input_keys(ScopeSpec("a", search_fasta="a.fa")),
            {
                "input_mode": "sequence",
                "search_fasta": "a.fa",
                "mask_same_as_target": True,
            },
        )
        self.assertEqual(
            scope_input_keys(ScopeSpec("b", regions="b.bed")),
            {
                "input_mode": "bed",
                "bed_regions": "b.bed",
                "mask_same_as_target": True,
            },
        )
        self.assertEqual(
            scope_input_keys(
                ScopeSpec("c", search_fasta="c.fa", mask_fasta="c_mask.fa",
                          mask_same_as_target=False)
            ),
            {
                "input_mode": "sequence",
                "search_fasta": "c.fa",
                "mask_fasta": "c_mask.fa",
            },
        )
        with self.assertRaises(ValueError):
            scope_input_keys(ScopeSpec("d"))
        with self.assertRaises(ValueError):
            scope_input_keys(
                ScopeSpec("e", search_fasta="e.fa", mask_fasta="e_mask.fa")
            )

    def test_build_unit_form_state_overlays_and_struct_fields(self):
        spec = _spec(
            shared={"genome_fasta": "g.fa", "nuclease": "tnpb"},
            scopes=[ScopeSpec("a", regions="a.bed")],
            patterns=[
                PatternVariant("P1", "motif_gap_motif", {"left_motif": "TTAG"})
            ],
            groups=[BatchGroup("G1", ["a"], ["P1"])],
        )
        unit = normalize_units(spec)[0]
        state = build_unit_form_state(spec, unit)
        self.assertEqual(state.mode, "motif_gap_motif")
        self.assertEqual(state.input_mode, "bed")
        self.assertEqual(state.nuclease, "tnpb")
        self.assertEqual(state.value("bed_regions"), "a.bed")
        self.assertEqual(state.value("left_motif"), "TTAG")
        self.assertEqual(state.value("genome_fasta"), "g.fa")
        self.assertNotIn("nuclease", state.values)

    def test_shared_nuclease_survives_the_default_spcas9_side_preset(self):
        """A batch that sets ``shared.nuclease`` must not be relabelled
        SpCas9 just because the side presets were left at their default."""
        spec = _spec(
            shared={"genome_fasta": "g.fa", "nuclease": "tnpb"},
            scopes=[ScopeSpec("a", search_fasta="a.fa")],
            patterns=[
                PatternVariant("P1", "single_motif_flank", {"motif": "TTAG"})
            ],
            groups=[BatchGroup("G1", ["a"], ["P1"])],
        )
        state = build_unit_form_state(spec, normalize_units(spec)[0])
        self.assertEqual(state.side_presets["target"], "cas9")
        config = build_runner_config(state, build_pattern_spec(state))
        self.assertEqual(config.nuclease, "tnpb")

    def test_expand_scope_dir_sorts_and_renames_duplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name in ("b.fasta", "a.fa", "a.fasta", "c.fa.gz", "notes.txt"):
                open(os.path.join(tmp, name), "w", encoding="utf-8").close()
            os.makedirs(os.path.join(tmp, "sub.fa"), exist_ok=True)
            scopes = expand_scope_dir(tmp)
            self.assertEqual(
                [scope.scope_id for scope in scopes],
                ["a", "a_2", "b", "c"],
            )
            self.assertTrue(scopes[0].search_fasta.endswith("a.fa"))


class ScopeMaskTests(unittest.TestCase):
    def test_conflict_raises_from_scope_input_keys(self):
        with self.assertRaises(ValueError):
            scope_input_keys(
                ScopeSpec("a", search_fasta="a.fa", mask_fasta="m.fa")
            )

    def test_validate_conflict_and_missing_scope_mask(self):
        with tempfile.TemporaryDirectory() as tmp:
            fasta = os.path.join(tmp, "a.fa")
            open(fasta, "w", encoding="utf-8").close()
            missing_mask = os.path.join(tmp, "nope.fa")
            patterns = [
                PatternVariant("P1", "single_motif_flank", {"motif": "TTAG"})
            ]
            groups = [BatchGroup("G1", ["a"], ["P1"])]
            conflict = _spec(
                scopes=[
                    ScopeSpec("a", search_fasta=fasta, mask_fasta="m.fa",
                              mask_same_as_target=True)
                ],
                patterns=patterns,
                groups=groups,
            )
            errors, _warnings = validate_spec(conflict, dry_run=True)
            self.assertTrue(
                any("mask_fasta and mask_same_as_target" in m for m in errors),
                errors,
            )
            missing = _spec(
                scopes=[
                    ScopeSpec("a", search_fasta=fasta, mask_fasta=missing_mask,
                              mask_same_as_target=False)
                ],
                patterns=patterns,
                groups=groups,
            )
            errors, warnings = validate_spec(missing, dry_run=True)
            self.assertEqual(errors, [])
            self.assertTrue(
                any("mask_fasta not found" in m for m in warnings), warnings
            )
            errors, _warnings = validate_spec(missing, dry_run=False)
            self.assertTrue(
                any("mask_fasta not found" in m for m in errors), errors
            )

    def test_shared_mask_is_a_reserved_key_error(self):
        spec = _spec(shared={"mask_fasta": "shared_mask.fa"})
        errors, _warnings = validate_spec(spec, dry_run=True)
        self.assertIn("shared must not set reserved key 'mask_fasta'", errors)

    def test_shared_annotation_file_is_checked(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = os.path.join(tmp, "nope.gff3")
            spec = _spec(shared={"annotation": missing})
            errors, warnings = validate_spec(spec, dry_run=True)
            self.assertEqual(errors, [])
            self.assertTrue(
                any("shared annotation not found" in m for m in warnings),
                warnings,
            )
            errors, _warnings = validate_spec(spec, dry_run=False)
            self.assertTrue(
                any("shared annotation not found" in m for m in errors), errors
            )

    def test_build_unit_form_state_keeps_scope_masks_isolated(self):
        spec = _spec(
            scopes=[
                ScopeSpec("a", search_fasta="a.fa"),
                ScopeSpec("b", search_fasta="b.fa", mask_fasta="b_mask.fa",
                          mask_same_as_target=False),
            ],
            patterns=[
                PatternVariant("P1", "single_motif_flank", {"motif": "TTAG"})
            ],
            groups=[BatchGroup("G1", ["a", "b"], ["P1"])],
        )
        states = {
            unit.scope_id: build_unit_form_state(spec, unit)
            for unit in normalize_units(spec)
        }
        self.assertTrue(states["a"].bool_value("mask_same_as_target"))
        self.assertEqual(states["a"].value("mask_fasta"), "")
        self.assertEqual(states["b"].value("mask_fasta"), "b_mask.fa")
        self.assertFalse(states["b"].bool_value("mask_same_as_target"))


class RoundTripTests(unittest.TestCase):
    def test_json_round_trip(self):
        spec = _spec()
        units = normalize_units(spec)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "batch.json")
            write_batch_json(spec, units, path)
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            self.assertEqual(len(data["units"]), 3)
            self.assertEqual(spec_from_dict(data), spec)
            self.assertEqual(load_batch_json(path), spec)

    def test_spec_to_dict_includes_units(self):
        spec = _spec()
        data = spec_to_dict(spec, normalize_units(spec))
        self.assertEqual(
            [unit["unit_id"] for unit in data["units"]],
            ["a__P1", "b__P1", "c__P2"],
        )

    def test_load_units_tsv_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "pairing.tsv")
            with open(path, "w", encoding="utf-8", newline="") as handle:
                handle.write(
                    "scope_id\tpattern_id\tsearch_fasta\tregions\tpattern_json\n"
                )
                handle.write(
                    "a\tP1\ta.fa\t\t%s\n"
                    % json.dumps({"mode": "single_motif_flank", "motif": "TTAG"})
                )
                handle.write(
                    "b\tP1\tb.fa\t\t%s\n"
                    % json.dumps({"mode": "single_motif_flank", "motif": "TTAG"})
                )
            spec = load_units_tsv(path)
            units = normalize_units(spec)
            self.assertEqual(
                [(u.scope_id, u.pattern_id) for u in units],
                [("a", "P1"), ("b", "P1")],
            )
            self.assertEqual(spec.patterns[0].mode, "single_motif_flank")
            self.assertEqual(spec.patterns[0].overlay, {"motif": "TTAG"})
            self.assertEqual(spec_from_dict(spec_to_dict(spec, units)), spec)

    def test_scope_mask_json_round_trip(self):
        spec = _spec(
            scopes=[
                ScopeSpec("a", search_fasta="a.fa"),
                ScopeSpec("b", search_fasta="b.fa", mask_fasta="b_mask.fa",
                          mask_same_as_target=False),
            ],
            patterns=[
                PatternVariant("P1", "single_motif_flank", {"motif": "TTAG"})
            ],
            groups=[BatchGroup("G1", ["a", "b"], ["P1"])],
        )
        restored = spec_from_dict(spec_to_dict(spec))
        self.assertEqual(restored, spec)
        self.assertTrue(restored.scopes[0].mask_same_as_target)
        self.assertEqual(restored.scopes[1].mask_fasta, "b_mask.fa")
        self.assertFalse(restored.scopes[1].mask_same_as_target)

    def test_spec_from_dict_applies_mask_defaults(self):
        plain = spec_from_dict({
            "batch_label": "b",
            "scopes": [{"scope_id": "a", "search_fasta": "a.fa"}],
        })
        self.assertEqual(plain.scopes[0].mask_fasta, "")
        self.assertTrue(plain.scopes[0].mask_same_as_target)
        explicit = spec_from_dict({
            "batch_label": "b",
            "scopes": [
                {"scope_id": "a", "search_fasta": "a.fa",
                 "mask_fasta": "m.fa"}
            ],
        })
        self.assertEqual(explicit.scopes[0].mask_fasta, "m.fa")
        self.assertFalse(explicit.scopes[0].mask_same_as_target)

    def test_load_units_tsv_reads_optional_mask_columns(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "pairing.tsv")
            with open(path, "w", encoding="utf-8", newline="") as handle:
                handle.write(
                    "scope_id\tpattern_id\tsearch_fasta\tregions\t"
                    "mask_fasta\tmask_same_as_target\tpattern_json\n"
                )
                handle.write(
                    "a\tP1\ta.fa\t\t\t\t%s\n"
                    % json.dumps(
                        {"mode": "single_motif_flank", "motif": "TTAG"}
                    )
                )
                handle.write(
                    "b\tP1\t\tb.bed\tb_mask.fa\tfalse\t%s\n"
                    % json.dumps(
                        {"mode": "single_motif_flank", "motif": "TTAG"}
                    )
                )
            spec = load_units_tsv(path)
            by_id = {scope.scope_id: scope for scope in spec.scopes}
            self.assertEqual(by_id["a"].mask_fasta, "")
            self.assertTrue(by_id["a"].mask_same_as_target)
            self.assertEqual(by_id["b"].mask_fasta, "b_mask.fa")
            self.assertFalse(by_id["b"].mask_same_as_target)
            self.assertEqual(spec_from_dict(spec_to_dict(spec)), spec)

    def test_example_batch_uses_default_style_pattern_ids(self):
        path = os.path.join(ROOT, "example", "batch", "example_batch.json")
        spec = load_batch_json(path)
        self.assertEqual(
            [pattern.pattern_id for pattern in spec.patterns],
            ["TTAG", "TCAA", "TTAG_10-40_TCAA"],
        )
        self.assertIn(
            "scope_fa__TTAG_10-40_TCAA",
            [unit.unit_id for unit in normalize_units(spec)],
        )


if __name__ == "__main__":
    unittest.main()
