#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the Pattern Designer workflow."""

import os
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHARED = os.path.join(ROOT, "shared")
sys.path.insert(0, ROOT)
sys.path.insert(0, SHARED)

from design.pattern_spec import PatternKind  # noqa: E402


class DesignerWorkbenchTests(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        try:
            self.root = tk.Tk()
        except tk.TclError:
            self.skipTest("no display available")
        self.root.withdraw()
        from designer_workbench import PatternDesignerWorkbench
        self.app = PatternDesignerWorkbench(self.root)

    def tearDown(self):
        if hasattr(self, "app"):
            self.app._finish_progress(True)
            for _ in range(20):
                self.root.update()
            self.app._on_close()
        else:
            self.root.destroy()

    def test_single_side_preset_fills_config(self):
        self.app.side_preset_vars["target"].set("cas12a")
        self.app._apply_side_preset("target")
        config = self.app._current_config()
        self.assertEqual(config.mode, "preset")
        self.assertEqual(config.preset, "cas12a")
        self.assertEqual(config.pam_motif, "TTTN")
        self.assertEqual(config.pam_side, "5prime")
        self.assertTrue(config.require_pam)
        self.assertEqual(self.app._value("motif"), "TTTN")
        self.assertEqual(self.app._value("flank"), "24")
        self.assertEqual(self.app._value("side"), "downstream")
        self.assertEqual(self.app.nuclease_var.get(), "cas12a")

    def test_bed_input_mode_config(self):
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        from designer_workbench import PatternDesignerWorkbench
        app = PatternDesignerWorkbench(root, default_bed=True)
        try:
            self.assertTrue(app._is_bed_mode())
            self.assertEqual(app.input_mode_var.get(), "bed")
            app.vars["bed_regions"].set("my.bed")
            app.vars["genome_fasta"].set("genome.fa")
            app.vars["output_dir"].set(tempfile.mkdtemp())
            # Fill the pattern fields so the runner spec validates.
            app.vars["motif"].set("GGG")
            app.vars["flank"].set("5")
            app.vars["side"].set("upstream")
            config = app._current_config()
            self.assertEqual(config.regions, "my.bed")
            self.assertEqual(config.search_fasta, "")
            errors = app._readiness_errors()
            self.assertTrue(
                any("BED Regions not found" in error for error in errors)
            )
        finally:
            app._on_close()

    def test_switching_to_cas13_sets_pfs(self):
        # Start with a PAM-carrying preset, then switch to the CHOPCHOP Cas13.
        self.app.side_preset_vars["target"].set("cas9")
        self.app._apply_side_preset("target")
        self.assertEqual(self.app._value("motif"), "NGG")
        self.assertEqual(self.app._value("side"), "upstream")
        self.assertTrue(self.app.require_pam_var.get())

        self.app.side_preset_vars["target"].set("cas13")
        self.app._apply_side_preset("target")
        self.assertEqual(self.app._value("motif"), "H")
        self.assertEqual(self.app._value("side"), "downstream")
        self.assertEqual(self.app._value("flank"), "27")
        self.assertTrue(self.app.require_pam_var.get())

    def test_crispai_is_a_normal_off_target_model(self):
        self.app.side_preset_vars["target"].set("cas9")
        self.app._apply_side_preset("target")
        self.app.side_off_target_model_vars["target"].set("cfd,crispai")
        self.assertEqual(
            self.app._current_config().off_target_model,
            "cfd,crispai",
        )

    def test_crispai_is_only_listed_for_cas9(self):
        widgets = self.app._side_model_widgets["target"]
        self.app.side_preset_vars["target"].set("cas9")
        self.app._apply_side_preset("target")
        self.assertIn("crispai", widgets["off_combo"].cget("values"))

        self.app.side_preset_vars["target"].set("cas13")
        self.app._apply_side_preset("target")
        self.assertNotIn("crispai", widgets["off_combo"].cget("values"))

    def test_side_model_options_follow_nuclease(self):
        widgets = self.app._side_model_widgets["target"]
        self.assertEqual(
            self.app.side_on_target_model_vars["target"].get(), "cropsr")
        self.assertEqual(widgets["on_combo"].cget("values"), ("cropsr",))
        self.assertEqual(widgets["off_combo"].cget("values"),
                         ("cfd", "crispr_m", "deepcrispr", "crispai"))
        self.assertEqual(
            self.app.side_off_target_model_vars["target"].get(), "cfd")
        self.app.side_preset_vars["target"].set("cas12a")
        self.app._apply_side_preset("target")
        self.assertEqual(
            self.app.side_on_target_model_vars["target"].get(), "rules")
        self.assertEqual(widgets["on_combo"].cget("values"),
                         ("rules", "deepcas12a", "deepcpf1"))
        self.assertEqual(widgets["off_combo"].cget("values"), ("rules",))
        self.assertEqual(
            self.app.side_off_target_model_vars["target"].get(), "rules")

        # Cas12b defaults to its local preset rules.
        self.app.side_preset_vars["target"].set("cas12b")
        self.app._apply_side_preset("target")
        self.assertEqual(widgets["on_combo"].cget("values"), ("rules",))
        self.assertEqual(widgets["off_combo"].cget("values"), ("rules",))
        config = self.app._current_config()
        self.assertEqual(config.on_target_model, "rules")
        self.assertEqual(config.off_target_model, "rules")

        # TnpB offers omegaRNA (offline default) and TEEP (online reference).
        self.app.side_preset_vars["target"].set("tnpb")
        self.app._apply_side_preset("target")
        self.assertEqual(widgets["on_combo"].cget("values"), ("omega", "teep"))
        self.assertEqual(
            self.app.side_on_target_model_vars["target"].get(), "omega")
        self.assertEqual(self.app._current_config().reference_only_model, "none")
        self.app.side_on_target_model_vars["target"].set("teep")
        self.assertEqual(self.app._current_config().reference_only_model, "teep")

    def test_side_model_options_support_multiple_selections(self):
        self.app.side_preset_vars["target"].set("cas9")
        self.app._apply_side_preset("target")
        self.app.side_on_target_model_vars["target"].set("cropsr,rules")
        self.app.side_off_target_model_vars["target"].set("cfd,crispr_m")

        config = self.app._current_config()
        self.assertEqual(config.on_target_model, "cropsr,rules")
        self.assertEqual(config.off_target_model, "cfd,crispr_m")

        self.app.side_preset_vars["target"].set("tnpb")
        self.app._apply_side_preset("target")
        self.app.side_on_target_model_vars["target"].set("omega,teep")
        config = self.app._current_config()
        self.assertEqual(config.on_target_model, "omega,teep")
        self.assertEqual(config.reference_only_model, "teep")

    def test_custom_model_options_include_all_preset_models(self):
        widgets = self.app._side_model_widgets["target"]
        self.app.side_preset_vars["target"].set("custom")
        self.app._apply_side_preset("target")
        self.assertEqual(
            widgets["on_combo"].cget("values"),
            (
                "cropsr", "rules", "deepcas12a", "deepcpf1",
                "rna_rules", "tiger", "omega", "teep",
            ),
        )
        self.assertEqual(
            widgets["off_combo"].cget("values"),
            (
                "cfd", "crispr_m", "deepcrispr", "crispai", "rules",
                "pfs", "identity", "tiger",
            ),
        )

    def test_model_display_names_include_protein_group(self):
        from designer_workbench import _model_display_name
        self.assertEqual(
            _model_display_name("cfd"), "[Cas9] [rule] cfd")
        self.assertEqual(
            _model_display_name("crispai"), "[Cas9] crispai")
        self.assertEqual(
            _model_display_name("deepcas12a"), "[Cas12a] deepcas12a")
        self.assertEqual(
            _model_display_name("pfs"), "[Cas13] [rule] pfs")
        self.assertEqual(
            _model_display_name("omega"), "[TnpB] [rule] omega")
        self.assertEqual(
            _model_display_name("rules"), "[General] [rule] rules")

    def test_model_dropdown_stays_open_after_selection(self):
        widget = self.app._side_model_widgets["target"]["off_combo"]
        widget._show_popup()
        self.root.update()
        try:
            self.assertTrue(widget._popup.winfo_ismapped())
            widget._toggle("crispr_m")
            self.root.update()
            self.assertTrue(widget._popup.winfo_ismapped())
        finally:
            widget._hide_popup()
            self.root.update()
        self.assertFalse(widget._popup.winfo_ismapped())

    def test_primary_model_marker_follows_selection_order(self):
        widget = self.app._side_model_widgets["target"]["off_combo"]
        self.app.side_off_target_model_vars["target"].set("cfd,crispr_m")
        self.root.update()
        self.assertEqual(
            widget._display_var.get(),
            "Primary: [Cas9] [rule] cfd, [Cas9] crispr_m")
        self.assertEqual(
            widget._checkbuttons["cfd"].cget("text"),
            "[P] [Cas9] [rule] cfd")
        self.assertEqual(
            widget._checkbuttons["crispr_m"].cget("text"),
            "[Cas9] crispr_m")

        self.app.side_off_target_model_vars["target"].set("crispr_m,cfd")
        self.root.update()
        self.assertEqual(
            widget._display_var.get(),
            "Primary: [Cas9] crispr_m, [Cas9] [rule] cfd")
        self.assertEqual(
            widget._checkbuttons["cfd"].cget("text"),
            "[Cas9] [rule] cfd")
        self.assertEqual(
            widget._checkbuttons["crispr_m"].cget("text"),
            "[P] [Cas9] crispr_m")

    def test_pair_config_uses_per_side_nuclease_and_model(self):
        self.app.mode_var.set(PatternKind.MOTIF_GAP_MOTIF.value)
        self.app._rebuild_pattern_frame()
        self.app.side_preset_vars["left"].set("cas9")
        self.app._apply_side_preset("left")
        self.app.side_preset_vars["right"].set("tnpb")
        self.app._apply_side_preset("right")
        self.app.side_off_target_model_vars["left"].set("crispr_m")
        self.app.side_off_target_model_vars["right"].set("identity")
        config = self.app._current_config()
        self.assertEqual(config.left_nuclease, "cas9")
        self.assertEqual(config.right_nuclease, "tnpb")
        self.assertEqual(config.left_off_target_model, "crispr_m")
        self.assertEqual(config.right_off_target_model, "identity")

    def test_pair_config_includes_pair_rank_policy(self):
        self.app.mode_var.set(PatternKind.MOTIF_GAP_MOTIF.value)
        self.app._rebuild_pattern_frame()
        for field, value in {
            "e_high": "0.8",
            "e_min": "0.5",
            "e_fail": "0.2",
            "delta_default": "0.05",
            "b_low": "0.4",
            "b_high": "0.8",
            "m_low": "0.2",
            "m_high": "0.45",
            "h_risk": "0.7",
            "h_max": "1",
        }.items():
            self.app.vars["pair_rank_%s" % field].set(value)
        self.app.vars["result_label"].set("pair-policy-test")
        config = self.app._current_config()
        self.assertEqual(config.pair_rank_policy["e_high"], 0.8)
        self.assertEqual(config.pair_rank_policy["h_max"], 1.0)

    def test_pair_config_crispai_any_side(self):
        self.app.mode_var.set(PatternKind.MOTIF_GAP_MOTIF.value)
        self.app._rebuild_pattern_frame()
        self.app.side_preset_vars["left"].set("cas9")
        self.app._apply_side_preset("left")
        self.app.side_preset_vars["right"].set("cas9")
        self.app._apply_side_preset("right")
        self.app.side_off_target_model_vars["right"].set("crispai")
        config = self.app._current_config()
        self.assertEqual(config.right_off_target_model, "crispai")

    def test_single_off_target_model_default_cfd(self):
        self.assertEqual(self.app.side_off_target_model_vars["target"].get(), "cfd")
        self.app.side_preset_vars["target"].set("cas9")
        self.app._apply_side_preset("target")
        self.assertEqual(self.app._current_config().off_target_model, "cfd")

    def test_max_mismatch_default_and_zero_are_consistent(self):
        self.app.side_preset_vars["target"].set("cas9")
        self.app._apply_side_preset("target")
        self.assertEqual(self.app._value("max_mismatch"), "4")
        self.assertEqual(self.app._current_config().max_mismatch, 4)

        self.app.vars["max_mismatch"].set("0")
        self.assertEqual(self.app._current_config().max_mismatch, 0)

    def test_left_and_right_presets_independent(self):
        self.app.mode_var.set(PatternKind.MOTIF_GAP_MOTIF.value)
        self.app._rebuild_pattern_frame()
        self.app.side_preset_vars["left"].set("cas12a")
        self.app._apply_side_preset("left")
        self.app.side_preset_vars["right"].set("cas9")
        self.app._apply_side_preset("right")
        self.assertEqual(self.app._value("left_motif"), "TTTN")
        self.assertEqual(self.app._value("left_flank"), "24")
        self.assertEqual(self.app._value("left_side"), "downstream")
        self.assertEqual(self.app._value("right_motif"), "NGG")
        self.assertEqual(self.app._value("right_flank"), "20")
        self.assertEqual(self.app._value("right_side"), "upstream")
        self.assertEqual(self.app.active_side_var.get(), "right")
        self.assertEqual(self.app.nuclease_var.get(), "cas9")

    def test_mode_labels_match_design_patterns(self):
        labels = list(self.app.mode_combo["values"])
        self.assertEqual(
            labels,
            [
                "Single target design",
                "Paired-target design Pattern A: Target-xbp-Target",
                "Paired-target design Pattern B: "
                "Target-xbp-Motif-ybp-Target",
            ],
        )

    def test_progress_bar_falls_back_to_indeterminate(self):
        try:
            self.app._start_progress("Running...")
            self.assertEqual(
                str(self.app.progress_bar["mode"]), "indeterminate"
            )
            self.assertEqual(
                str(self.app.progress_bar["style"]),
                "Run.Horizontal.TProgressbar",
            )
            self.app._set_progress(45, "off-target search")
            self.assertEqual(
                str(self.app.progress_bar["mode"]), "determinate"
            )
            self.assertEqual(self.app.progress_var.get(), 45)
            self.assertIn("45%", self.app.progress_label.get())
            self.app._set_progress(63, "Analyzing target 50/80")
            self.assertEqual(
                self.app.progress_label.get(), "Analyzing target 50/80"
            )
            self.app._finish_progress(True)
            self.assertEqual(self.app.progress_var.get(), 100)
            self.assertEqual(self.app.progress_label.get(), "Ready")
            self.assertEqual(
                str(self.app.progress_bar["style"]),
                "Ready.Horizontal.TProgressbar",
            )
        finally:
            self.app._finish_progress(True)

    def _run_prompt_sync(self, request, answer):
        """Run the confirm dialog with a synchronous root.after stub."""
        with mock.patch.object(
                self.app.root, "after",
                side_effect=lambda _delay, fn=None: fn()), \
                mock.patch(
                    "designer_workbench.messagebox.askyesno",
                    return_value=answer) as ask:
            approved = self.app._confirm_pipeline_prompt(request)
        return approved, ask

    def test_python_fallback_prompt_asks_and_logs_the_reason(self):
        request = {
            "kind": "python_fallback",
            "reason": "offtarget-engine is missing",
        }
        approved, ask = self._run_prompt_sync(request, True)
        self.assertTrue(approved)
        self.assertEqual(ask.call_count, 1)
        self.assertIn("offtarget-engine is missing", ask.call_args.args[1])
        self.assertIn("pure-Python", ask.call_args.args[1])

        with open(self.app.log_writer.path, encoding="utf-8") as handle:
            log_text = handle.read()
        self.assertIn("offtarget-engine is missing", log_text)
        self.assertIn("Python fallback approved by user", log_text)

    def test_python_fallback_prompt_can_be_declined(self):
        request = {
            "kind": "python_fallback",
            "reason": "no native binary",
        }
        approved, _ = self._run_prompt_sync(request, False)
        self.assertFalse(approved)
        with open(self.app.log_writer.path, encoding="utf-8") as handle:
            log_text = handle.read()
        self.assertIn("Python fallback declined by user", log_text)

    def test_unknown_prompt_kind_is_refused_without_a_dialog(self):
        with mock.patch(
                "designer_workbench.messagebox.askyesno") as ask:
            approved = self.app._confirm_pipeline_prompt({"kind": "other"})
        self.assertFalse(approved)
        ask.assert_not_called()

    def test_target_counter_line_updates_label(self):
        self.app._handle_command_line("PROGRESS_TARGET: 50/80")
        self.root.update()
        self.assertEqual(
            self.app.progress_label.get(), "Analyzing target 50/80"
        )

    def test_readiness_tracks_missing_and_ready_states(self):
        with tempfile.TemporaryDirectory() as tmp:
            search = os.path.join(tmp, "target.fa")
            genome = os.path.join(tmp, "genome.fa")
            with open(search, "w", encoding="utf-8") as handle:
                handle.write(">t\nACGT\n")
            with open(genome, "w", encoding="utf-8") as handle:
                handle.write(">g\nACGT\n")
            self.app.vars["output_dir"].set(tmp)
            self.app.vars["search_fasta"].set(search)
            self.app.vars["genome_fasta"].set(genome)
            self.app._refresh_preview()
            self.assertEqual(
                str(self.app.progress_bar["style"]),
                "Missing.Horizontal.TProgressbar",
            )
            self.assertIn("Missing:", self.app.progress_label.get())

            self.app.side_preset_vars["target"].set("cas9")
            self.app._apply_side_preset("target")
            self.assertEqual(self.app.progress_label.get(), "Ready")
            self.assertEqual(
                str(self.app.progress_bar["style"]),
                "Ready.Horizontal.TProgressbar",
            )

    def test_score_targets_requires_find_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            search = os.path.join(tmp, "target.fa")
            genome = os.path.join(tmp, "genome.fa")
            with open(search, "w", encoding="utf-8") as handle:
                handle.write(">t\nACGT\n")
            with open(genome, "w", encoding="utf-8") as handle:
                handle.write(">g\nACGT\n")
            self.app.vars["output_dir"].set(tmp)
            self.app.vars["search_fasta"].set(search)
            self.app.vars["genome_fasta"].set(genome)
            self.app.side_preset_vars["target"].set("cas9")
            self.app._apply_side_preset("target")
            with mock.patch(
                "designer_workbench.messagebox.showerror"
            ) as show_error:
                self.app._run_score_targets()
                self.root.update()
            self.assertTrue(show_error.called)
            self.assertFalse(self.app.running)
            self.assertIn(
                "Run Find Targets first",
                self.app.log_text.get("1.0", "end"),
            )

    def test_pipeline_failure_shows_popup_with_output_tail(self):
        with mock.patch(
            "designer_workbench.messagebox.showerror"
        ) as show_error:
            self.app._show_step_failure(
                "Finding targets...",
                1,
                "ERROR: min_right (20) must be smaller than R (10)",
            )
        self.assertEqual(self.app.status_var.get(), "Failed")
        self.assertTrue(show_error.called)
        title, message = show_error.call_args[0][:2]
        self.assertEqual(title, "Finding targets failed")
        self.assertIn("return code 1", message)
        self.assertIn("min_right (20)", message)


class DesignerFileDialogTests(unittest.TestCase):
    def _make_app(self):
        from types import SimpleNamespace

        selected = mock.Mock()
        return SimpleNamespace(
            root=object(),
            vars={"path": selected},
            _refresh_preview=mock.Mock(),
        ), selected

    def test_browse_file_uses_designer_as_parent(self):
        from designer_workbench import PatternDesignerWorkbench

        app, selected = self._make_app()
        with mock.patch(
            "designer_workbench.filedialog.askopenfilename",
            return_value="/tmp/genome.fa",
        ) as ask:
            PatternDesignerWorkbench._browse_file(app, "path")

        ask.assert_called_once_with(parent=app.root)
        selected.set.assert_called_once_with("/tmp/genome.fa")
        app._refresh_preview.assert_called_once_with()

    def test_browse_directory_uses_designer_as_parent(self):
        from designer_workbench import PatternDesignerWorkbench

        app, selected = self._make_app()
        with mock.patch(
            "designer_workbench.filedialog.askdirectory",
            return_value="/tmp/output",
        ) as ask:
            PatternDesignerWorkbench._browse_dir(app, "path")

        ask.assert_called_once_with(parent=app.root)
        selected.set.assert_called_once_with("/tmp/output")
        app._refresh_preview.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
