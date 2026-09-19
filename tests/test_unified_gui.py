#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the unified GUI workbench and main.py entry point."""

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import unified_gui  # noqa: E402


class UnifiedGuiTests(unittest.TestCase):
    def test_tool_scripts_exist(self):
        for name, rel in unified_gui.TOOL_SCRIPTS.items():
            self.assertTrue(
                os.path.isfile(os.path.join(ROOT, rel)),
                "missing tool script %s" % name)

    def test_options_cover_web_features(self):
        self.assertIn("cas13", unified_gui.PRESETS)
        self.assertIn("tnpb", unified_gui.PRESETS)
        self.assertNotIn("crispri", unified_gui.PRESETS)
        self.assertIn("indexed", unified_gui.ENGINES)
        self.assertIn("gggenome", unified_gui.ENGINES)

    def test_main_launches_unified_gui(self):
        with open(os.path.join(ROOT, "main.py"), "r",
                  encoding="utf-8") as handle:
            text = handle.read()
        self.assertIn("unified_gui.main()", text)
        self.assertNotIn("--legacy", text)
        self.assertIn("MainApp", text)

    def test_gui_builds_and_builds_command(self):
        import tkinter as tk
        try:
            root = tk.Tk()
        except tk.TclError:
            self.skipTest("no display available")
        root.withdraw()
        app = unified_gui.UnifiedGUI(root)
        root.update_idletasks()
        self.assertTrue(hasattr(app, "legacy_app"))
        self.assertIsNotNone(app.legacy_app)
        self.assertTrue(hasattr(app, "motif_notebook"))
        self.assertTrue(hasattr(app, "motif_apps"))
        self.assertEqual(len(app.motif_apps), 0)
        self.assertEqual(
            [app.main_notebook.tab(t, "text")
             for t in app.main_notebook.tabs()],
            ["Data prep / Models", "Target design",
             "Results / Output"])
        self.assertEqual(
            app.main_notebook.tab(app.main_notebook.select(), "text"),
            "Data prep / Models")
        self.assertFalse(hasattr(app, "analysis_type_var"))
        self.assertEqual(
            [app.motif_notebook.tab(t, "text")
             for t in app.motif_notebook.tabs()],
            ["Pattern Designer"])
        root.destroy()
        self.assertTrue(hasattr(app, "entry_output"))
        self.assertTrue(hasattr(app, "summary_text"))
        self.assertTrue(hasattr(app, "file_list"))
        self.assertFalse(hasattr(app, "combo_engine"))
        self.assertFalse(hasattr(app, "btn_run"))

    def test_motif_tab_shows_design_pattern_intro(self):
        import tkinter as tk
        from tkinter import ttk

        try:
            root = tk.Tk()
        except tk.TclError:
            self.skipTest("no display available")
        root.withdraw()
        app = unified_gui.UnifiedGUI(root)
        root.update_idletasks()

        found = False

        def walk(widget):
            nonlocal found
            if isinstance(widget, ttk.Label):
                text = widget.cget("text")
                if "three distinct target design patterns" in text:
                    found = True
            for child in widget.winfo_children():
                walk(child)

        walk(app.motif_notebook)
        root.destroy()
        self.assertTrue(found)

    def test_designer_defaults_carry_data_prep_paths(self):
        import tkinter as tk

        try:
            root = tk.Tk()
        except tk.TclError:
            self.skipTest("no display available")
        root.withdraw()
        app = unified_gui.UnifiedGUI(root)
        root.update_idletasks()
        legacy = app.legacy_app
        legacy.entry_genome.delete(0, tk.END)
        legacy.entry_genome.insert(0, r"C:\genome.fa")
        legacy.entry_output.delete(0, tk.END)
        legacy.entry_output.insert(0, r"C:\out")
        legacy.entry_blastdb.delete(0, tk.END)
        legacy.entry_blastdb.insert(0, r"C:\db")
        legacy.prepared_params = {
            "target_fasta": r"C:\target.fa",
            "mask_fasta": r"C:\mask.fa",
        }
        defaults = app._designer_defaults()
        root.destroy()
        self.assertEqual(defaults["genome_fasta"], r"C:\genome.fa")
        self.assertEqual(defaults["output_dir"], r"C:\out")
        self.assertEqual(defaults["blastdb"], r"C:\db")
        self.assertEqual(defaults["search_fasta"], r"C:\target.fa")
        self.assertEqual(defaults["mask_fasta"], r"C:\mask.fa")


if __name__ == "__main__":
    unittest.main()
