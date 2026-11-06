#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the external crispAI adapter helpers (no external runtime)."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "shared"))

from scoring.crispai_runtime import (  # noqa: E402
    CrispAIRunResult,
    VENDORED_ENTRY_FILES,
    backfill_candidates,
    collect_sgrnas,
    make_sgrna,
    parse_aggregate_output,
    run_crispai_aggregate,
    specificity_from_aggregate,
)
from scoring import crispai_runtime  # noqa: E402
from scoring import model_registry  # noqa: E402


class CrispAIRuntimeTests(unittest.TestCase):
    def _candidate_tsv(self, directory, guides):
        path = os.path.join(directory, "library_scores.tsv")
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write("rank\tqid\tguide_seq\tpam_seq\tcrispai_off_target\n")
            for index, guide in enumerate(guides):
                handle.write(
                    "%d\tg%d\t%s\tAGG\t\n" % (index + 1, index, guide))
        return path

    @staticmethod
    def _write_aggregate(path, rows):
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(
                "sgRNA\taggregate_score_mean\taggregate_score_median\t"
                "aggregate_score_std\t200-samples\n")
            for sgrna, value in rows:
                handle.write("%s\t%s\t%s\t0.2\t%s\n" % (
                    sgrna, value, value, value))

    def test_make_sgrna_20mer_always_uses_ngg(self):
        self.assertEqual(
            make_sgrna("GAACACAAAGCATAGACTGC", "AGG"),
            "GAACACAAAGCATAGACTGCNGG",
        )

    def test_make_sgrna_accepts_23mer_ngg(self):
        self.assertEqual(
            make_sgrna("GAACACAAAGCATAGACTGCNGG"),
            "GAACACAAAGCATAGACTGCNGG",
        )

    def test_make_sgrna_rejects_wrong_length(self):
        self.assertIsNone(make_sgrna("ACGT"))
        self.assertIsNone(make_sgrna("A" * 21))

    def test_specificity_conversion(self):
        self.assertAlmostEqual(specificity_from_aggregate(0.0), 1.0)
        self.assertAlmostEqual(specificity_from_aggregate(1.0), 0.5)

    def test_nupop_probe_rejects_nonzero_exit_even_if_stdout_is_true(self):
        completed = mock.Mock(returncode=1, stdout="TRUE\n")
        with mock.patch.object(crispai_runtime.shutil, "which",
                               return_value="Rscript"), mock.patch.object(
                                   crispai_runtime.subprocess, "run",
                                   return_value=completed):
            available, error = crispai_runtime.nupop_probe()
        self.assertFalse(available)
        self.assertIn("exit code 1", error)

    def test_nupop_probe_requires_exact_trimmed_true(self):
        completed = mock.Mock(returncode=0, stdout="TRUE FALSE\n")
        with mock.patch.object(crispai_runtime.shutil, "which",
                               return_value="Rscript"), mock.patch.object(
                                   crispai_runtime.subprocess, "run",
                                   return_value=completed):
            available, error = crispai_runtime.nupop_probe()
        self.assertFalse(available)
        self.assertIn("did not return TRUE", error)

    def test_registry_does_not_report_ready_from_weight_and_torch_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            checkpoint = Path(tmp) / "crispai.pt"
            checkpoint.write_bytes(b"not-a-real-checkpoint")
            model_info = dict(model_registry.MODELS["crispai"])
            model_info["expected_bytes"] = None
            with mock.patch.dict(
                    model_registry.MODELS, {"crispai": model_info}), \
                    mock.patch.object(crispai_runtime, "checkpoint_path",
                                      return_value=checkpoint), \
                    mock.patch.object(crispai_runtime, "_module_available",
                                      return_value=True), \
                    mock.patch.object(crispai_runtime, "vendor_dir",
                                      return_value=Path(tmp) / "missing_vendor"), \
                    mock.patch.object(crispai_runtime, "nupop_probe",
                                      return_value=(False, "NuPoP missing")), \
                    mock.patch.object(crispai_runtime, "_casoffinder_binary",
                                      return_value=None), \
                    mock.patch.object(crispai_runtime,
                                      "genome_resource_path",
                                      return_value=None):
                self.assertEqual(
                    model_registry.get_model_status("crispai"),
                    "dependency_missing")
                detail = model_registry.get_model_status_details("crispai")
        self.assertEqual(detail["status"], "dependency_missing")
        self.assertTrue(any("NuPoP" in error for error in detail["errors"]))
        self.assertTrue(any("vendored" in error for error in detail["errors"]))

    def test_stage_vendor_redirects_genome_only_in_run_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            vendor = Path(tmp) / "vendor"
            vendor.mkdir()
            for name in VENDORED_ENTRY_FILES:
                text = name
                if name == "annotate_pi.py":
                    text = (
                        "g = genomepy.Genome('GRCh38')\n"
                        "os.system('Rscript nupop.R')\n")
                elif name == "crispAI.py":
                    text = "os.system('cas-offinder input C output')\n"
                (vendor / name).write_text(text, encoding="utf-8")
            run_dir = Path(tmp) / "run"
            run_dir.mkdir()
            staged = crispai_runtime._stage_vendor(vendor, run_dir)
            self.assertIn(
                "os.environ.get('CRISPAI_GENOME', 'GRCh38')",
                (staged / "annotate_pi.py").read_text(encoding="utf-8"))
            self.assertEqual(
                (vendor / "annotate_pi.py").read_text(encoding="utf-8"),
                "g = genomepy.Genome('GRCh38')\n"
                "os.system('Rscript nupop.R')\n")
            for name in ("crispAI.py", "annotate_pi.py"):
                staged_text = (staged / name).read_text(encoding="utf-8")
                self.assertNotIn("os.system(", staged_text)
                self.assertIn("_crispai_checked_system", staged_text)
                compile(staged_text, name, "exec")

    def test_run_missing_checkpoint_fails_before_full_preflight(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
                crispai_runtime, "_checkpoint_present",
                return_value=False), mock.patch.object(
                    crispai_runtime, "preflight") as preflight:
            result = run_crispai_aggregate(
                ["GAACACAAAGCATAGACTGCNGG"], tmp, fallback_model="cfd")

        preflight.assert_not_called()
        self.assertFalse(result.succeeded)
        self.assertEqual(result.effective_model, "cfd")
        self.assertIn("checkpoint missing", result.fallback_reason)

    def test_run_uses_unique_directory_and_ignores_fixed_stale_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            sgrna = "GAACACAAAGCATAGACTGCNGG"
            stale = Path(tmp) / "crispai.aggregate.tsv"
            self._write_aggregate(stale, [(sgrna, "99")])
            seen = []

            def fake_run(_input, output, **_kwargs):
                seen.append(str(output))
                self._write_aggregate(output, [(sgrna, "1.0")])
                return 0

            with mock.patch.object(crispai_runtime, "_checkpoint_present",
                                   return_value=True), \
                    mock.patch.object(crispai_runtime, "preflight",
                                   return_value=([], [])), \
                    mock.patch.object(crispai_runtime, "_stage_vendor",
                                      return_value=Path(tmp) / "vendor"), \
                    mock.patch.object(crispai_runtime, "_stage_casoffinder",
                                      return_value=Path(tmp) / "casoffinder"), \
                    mock.patch.object(crispai_runtime, "run_aggregate",
                                      side_effect=fake_run):
                first = run_crispai_aggregate([sgrna], tmp)
                second = run_crispai_aggregate([sgrna], tmp)

        self.assertTrue(first.succeeded)
        self.assertEqual(first.requested_model, "crispai")
        self.assertEqual(first.effective_model, "crispai")
        self.assertEqual(first.fallback_reason, "")
        self.assertEqual(first.score_scope, "aggregate")
        self.assertAlmostEqual(first.scores[sgrna], 1.0)
        self.assertNotEqual(first.run_dir, second.run_dir)
        self.assertNotEqual(seen[0], seen[1])
        self.assertEqual(Path(seen[0]).parent, Path(first.run_dir))

    def test_run_nonzero_exit_is_failure_and_does_not_parse_stale_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            sgrna = "GAACACAAAGCATAGACTGCNGG"
            self._write_aggregate(
                os.path.join(tmp, "crispai.aggregate.tsv"), [(sgrna, "9")])
            with mock.patch.object(crispai_runtime, "_checkpoint_present",
                                   return_value=True), \
                    mock.patch.object(crispai_runtime, "preflight",
                                   return_value=([], [])), \
                    mock.patch.object(crispai_runtime, "_stage_vendor",
                                      return_value=Path(tmp) / "vendor"), \
                    mock.patch.object(crispai_runtime, "_stage_casoffinder",
                                      return_value=Path(tmp) / "casoffinder"), \
                    mock.patch.object(crispai_runtime, "run_aggregate",
                                      return_value=7):
                result = run_crispai_aggregate(
                    [sgrna], tmp, fallback_model="cfd")
        self.assertFalse(result.succeeded)
        self.assertEqual(result.scores, {})
        self.assertEqual(result.effective_model, "cfd")
        self.assertIn("code 7", result.fallback_reason)

    def test_run_rejects_missing_and_extra_guides(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = "GAACACAAAGCATAGACTGCNGG"
            second = "CAGTCAGTCAGTCAGTCAGTNGG"

            def fake_run(_input, output, **_kwargs):
                self._write_aggregate(output, [(first, "1.0")])
                return 0

            with mock.patch.object(crispai_runtime, "_checkpoint_present",
                                   return_value=True), \
                    mock.patch.object(crispai_runtime, "preflight",
                                   return_value=([], [])), \
                    mock.patch.object(crispai_runtime, "_stage_vendor",
                                      return_value=Path(tmp) / "vendor"), \
                    mock.patch.object(crispai_runtime, "_stage_casoffinder",
                                      return_value=Path(tmp) / "casoffinder"), \
                    mock.patch.object(crispai_runtime, "run_aggregate",
                                      side_effect=fake_run):
                missing = run_crispai_aggregate([first, second], tmp)

            def fake_extra(_input, output, **_kwargs):
                self._write_aggregate(output, [(first, "1.0"), (second, "2.0")])
                return 0

            with mock.patch.object(crispai_runtime, "_checkpoint_present",
                                   return_value=True), \
                    mock.patch.object(crispai_runtime, "preflight",
                                   return_value=([], [])), \
                    mock.patch.object(crispai_runtime, "_stage_vendor",
                                      return_value=Path(tmp) / "vendor2"), \
                    mock.patch.object(crispai_runtime, "_stage_casoffinder",
                                      return_value=Path(tmp) / "casoffinder2"), \
                    mock.patch.object(crispai_runtime, "run_aggregate",
                                      side_effect=fake_extra):
                extra = run_crispai_aggregate([first], tmp)
        self.assertFalse(missing.succeeded)
        self.assertIn("missing 1", missing.fallback_reason)
        self.assertFalse(extra.succeeded)
        self.assertIn("extra 1", extra.fallback_reason)

    def test_structured_fallback_records_effective_model_and_reason(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
                crispai_runtime, "_checkpoint_present",
                return_value=True), mock.patch.object(
                    crispai_runtime, "preflight",
                    return_value=(["NuPoP missing"], [])):
            result = run_crispai_aggregate(
                ["GAACACAAAGCATAGACTGCNGG"], tmp, fallback_model="cfd")
        self.assertIsInstance(result, CrispAIRunResult)
        self.assertEqual(result.requested_model, "crispai")
        self.assertEqual(result.effective_model, "cfd")
        self.assertEqual(result.score_scope, "aggregate")
        self.assertIn("NuPoP missing", result.fallback_reason)

    def test_collect_backfill_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            candidates = self._candidate_tsv(
                tmp, ["GAACACAAAGCATAGACTGC", "GAACACAAAGCATAGACTGC"])
            records = collect_sgrnas(candidates)
            self.assertEqual(len(records), 1)
            self.assertEqual(
                records[0]["sgrna"], "GAACACAAAGCATAGACTGCNGG"
            )

            aggregate = os.path.join(tmp, "agg.tsv")
            with open(aggregate, "w", encoding="utf-8", newline="") as handle:
                handle.write(
                    "sgRNA\taggregate_score_mean\taggregate_score_median\t"
                    "aggregate_score_std\t200-samples\n"
                    "GAACACAAAGCATAGACTGCNGG\t1.0\t1.0\t0.2\t1.0\n"
                )
            mapping = parse_aggregate_output(aggregate)
            self.assertEqual(mapping["GAACACAAAGCATAGACTGCNGG"], 1.0)

            matched, written = backfill_candidates(candidates, aggregate)
            self.assertEqual((matched, written), (2, 2))
            with open(candidates, "r", encoding="utf-8") as handle:
                content = handle.read()
            self.assertIn("crispai_off_target", content)
            self.assertIn("crispai_aggregate_score", content)
            self.assertIn("0.500000", content)

    def test_backfill_rejects_guide_set_mismatch_without_partial_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            candidate = "GAACACAAAGCATAGACTGC"
            candidates = self._candidate_tsv(tmp, [candidate])
            with open(candidates, "r", encoding="utf-8") as handle:
                before = handle.read()
            aggregate = os.path.join(tmp, "agg.tsv")
            self._write_aggregate(
                aggregate, [("CAGTCAGTCAGTCAGTCAGTNGG", "1.0")])
            with self.assertRaisesRegex(ValueError, "guide set mismatch"):
                backfill_candidates(candidates, aggregate)
            with open(candidates, "r", encoding="utf-8") as handle:
                self.assertEqual(handle.read(), before)


if __name__ == "__main__":
    unittest.main()
