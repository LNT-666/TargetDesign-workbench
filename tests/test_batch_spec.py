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
            {"input_mode": "sequence", "search_fasta": "a.fa"},
        )
        self.assertEqual(
            scope_input_keys(ScopeSpec("b", regions="b.bed")),
            {"input_mode": "bed", "bed_regions": "b.bed"},
        )
        with self.assertRaises(ValueError):
            scope_input_keys(ScopeSpec("c"))

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


if __name__ == "__main__":
    unittest.main()
