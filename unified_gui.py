#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unified local GUI workbench for the CRISPR toolkit.

main.py launches this workbench. It keeps the three motif GUIs as dedicated
tool launchers and centralises the target extraction -> scoring workflow that
the local web interface exposes.

The library (一键出库) pipeline is retired: its button is created disabled and
the code behind it is kept only so that the rest of the toolchain is
unaffected.
"""

import json
import importlib
import os
import csv
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk


ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "shared"))

from design.system_presets import get_preset, preset_choices, rule_summary  # noqa: E402
from scoring.model_registry import get_all_statuses  # noqa: E402
from design.library_preflight import ENGINE_CHOICES  # noqa: E402
import gui.gui_common as gui_common  # noqa: E402
from utils.log_utils import parse_progress_line  # noqa: E402


LIBRARY_SCRIPT = os.path.join("shared", "design", "library_pipeline.py")
INDEX_SCRIPT = os.path.join("tools", "build_genome_index.py")

TOOL_SCRIPTS = {
    "Designer": os.path.join("designer_workbench.py"),
}

PRESETS = [key for key, _ in preset_choices()]

# Back-compat alias used by older tests/callers.
ENGINES = ENGINE_CHOICES


class UnifiedGUI(gui_common.CommonGUIMixin):

    def __init__(self, root):
        self.root = root
        self.root.title("TargetDesign-workbench")
        self.root.geometry("1080x760")
        self.init_common(root, workspace_dir=ROOT)
        self.progress_var = tk.DoubleVar(value=0)
        self.progress_label = tk.StringVar(value="")
        self.progress_bar = None
        self.status_var = tk.StringVar(value="")
        self.output_summary = tk.StringVar(value="")
        self.legacy_entry = os.path.join(ROOT, "main.py")
        self.designer_window = None
        self.designer_app = None
        self._create_widgets()
        workspace_mapping = self._workspace_mapping()
        self.setup_workspace_menu(workspace_mapping)
        self.apply_workspace(workspace_mapping)
        self.refresh_models()

    def _workspace_mapping(self):
        return {
            "entry_output": "output_dir",
        }

    # ---------- 界面 ----------
    def _create_widgets(self):
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        workflow_header = ttk.Frame(self.root, padding="8")
        workflow_header.grid(row=0, column=0, sticky=(tk.W, tk.E))
        ttk.Label(workflow_header, text="TargetDesign-workbench",
                  font=("Arial", 12, "bold")).pack(side=tk.LEFT)
        self._step_label_var = tk.StringVar(value="Step 0 / 2")
        ttk.Label(workflow_header, textvariable=self._step_label_var,
                  foreground="#444").pack(side=tk.LEFT, padx=12)
        self._back_btn = ttk.Button(
            workflow_header, text="Back", command=lambda: self._goto_step(
                self._current_step - 1))
        self._back_btn.pack(side=tk.LEFT, padx=4)
        self._next_btn = ttk.Button(
            workflow_header, text="Next", command=lambda: self._goto_step(
                self._current_step + 1))
        self._next_btn.pack(side=tk.LEFT, padx=4)
        self._current_step = 0

        self.main_notebook = ttk.Notebook(self.root)
        self.main_notebook.grid(
            row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        self.main_notebook.bind(
            "<<NotebookTabChanged>>", self._on_tab_changed)

        outer = ttk.Frame(self.main_notebook, padding="10")
        self.main_notebook.add(outer, text="Results / Output")
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(2, weight=1)

        header = ttk.Frame(outer)
        header.grid(row=0, column=0, sticky=(tk.W, tk.E))
        ttk.Label(header, text="TargetDesign-workbench",
                  font=("Arial", 14, "bold")) \
            .pack(side=tk.LEFT)
        ttk.Label(header, textvariable=self.status_var, foreground="#444") \
            .pack(side=tk.LEFT, padx=12)
        ttk.Button(header, text="Refresh models", command=self.refresh_models) \
            .pack(side=tk.RIGHT)

        tool_bar = ttk.LabelFrame(outer, text="Designer", padding="5")
        tool_bar.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=(8, 6))
        ttk.Button(
            tool_bar,
            text="Open Pattern Designer",
            command=self._show_designer_workbench,
        ).pack(side=tk.LEFT, padx=6)
        ttk.Button(
            tool_bar,
            text="Open BED Designer",
            command=self._show_bed_designer_workbench,
        ).pack(side=tk.LEFT, padx=6)

        body = ttk.Frame(outer)
        body.grid(row=2, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)

        self._create_output_panel(body)
        self._create_progress(outer)
        self._create_log(outer)

        common_tab = ttk.Frame(self.main_notebook, padding="0")
        self.main_notebook.add(common_tab, text="Data prep / Models")
        self._create_legacy_panel(common_tab)

        motif_tab = ttk.Frame(self.main_notebook, padding="0")
        self.main_notebook.add(motif_tab, text="Target design")
        self._create_motif_panels(motif_tab)

        self.common_tab = common_tab
        self.motif_tab = motif_tab
        self.outer = outer
        self._reorder_workflow_tabs()
        self.main_notebook.select(self.common_tab)
        self._on_tab_changed()

    def _reorder_workflow_tabs(self):
        ordered = [self.common_tab, self.motif_tab, self.outer]
        for index, child in enumerate(ordered):
            self.main_notebook.insert(index, child)

    def _on_tab_changed(self, _event=None):
        tabs = self.main_notebook.tabs()
        selected = self.main_notebook.select()
        self._current_step = tabs.index(selected) if selected in tabs else 0
        self._update_step_label()

    def _goto_step(self, index):
        tabs = self.main_notebook.tabs()
        index = max(0, min(index, len(tabs) - 1))
        self.main_notebook.select(tabs[index])
        self._on_tab_changed()

    def _update_step_label(self):
        tabs = self.main_notebook.tabs()
        total = max(0, len(tabs) - 1)
        label = ""
        if 0 <= self._current_step < len(tabs):
            label = self.main_notebook.tab(
                tabs[self._current_step], "text")
        self._step_label_var.set(
            "Step %d / %d: %s" % (self._current_step, total, label))
        if hasattr(self, "_back_btn"):
            self._back_btn.config(
                state=tk.NORMAL if self._current_step > 0 else tk.DISABLED)
        if hasattr(self, "_next_btn"):
            self._next_btn.config(
                state=tk.NORMAL
                if self._current_step < len(tabs) - 1 else tk.DISABLED)

    def _create_legacy_panel(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)
        import main as main_module
        self.legacy_app = main_module.MainApp(
            parent, as_panel=True,
            motif_launcher=self._show_motif_tab_by_name)

    def _create_motif_panels(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)
        self.motif_notebook = ttk.Notebook(parent)
        self.motif_notebook.grid(
            row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        frame = ttk.Frame(self.motif_notebook, padding="20")
        self.motif_notebook.add(frame, text="Pattern Designer")
        ttk.Label(
            frame,
            text=(
                "The pipeline provides three distinct target design patterns: "
                "a single-target design, a paired-target design "
                "(Pattern A: Target-xbp-Target), and a paired-target design "
                "with an intervening motif "
                "(Pattern B: Target-xbp-Motif-ybp-Target)."
            ),
            wraplength=640,
        ).pack(pady=8)
        ttk.Button(
            frame,
            text="Open Pattern Designer",
            command=self._show_designer_workbench,
        ).pack(pady=6)
        self.motif_apps = {}

    def _show_designer_workbench(self):
        self._open_designer(bed=False)

    def _show_bed_designer_workbench(self):
        self._open_designer(bed=True)

    def _open_designer(self, bed=False):
        if self.designer_window is not None:
            try:
                if self.designer_window.winfo_exists():
                    # Re-sync the already-open designer with the latest Data
                    # prep extraction (search scope / mask FASTA) in case the
                    # user extracted new files after the designer was opened.
                    designer = getattr(self, "designer_app", None)
                    if designer is not None:
                        designer.apply_defaults(self._designer_defaults())
                    self.designer_window.lift()
                    return
            except tk.TclError:
                pass

        try:
            from designer_workbench import PatternDesignerWorkbench
        except Exception as exc:
            messagebox.showerror("Launch failed", str(exc))
            return

        window = tk.Toplevel(self.root)
        app = PatternDesignerWorkbench(window, default_bed=bed)
        app.apply_defaults(self._designer_defaults())
        self.designer_window = window
        self.designer_app = app

    def _designer_defaults(self):
        """Carry the file paths the user entered in Data prep into Designer."""
        defaults = {}
        legacy = getattr(self, "legacy_app", None)

        def take(key, entry):
            if entry is None:
                return
            value = (
                entry.get().strip()
                if hasattr(entry, "get")
                else str(entry).strip()
            )
            if value:
                defaults[key] = value

        if legacy is not None:
            take("genome_fasta", getattr(legacy, "entry_genome", None))
            take("output_dir", getattr(legacy, "entry_output", None))
            take("blastdb", getattr(legacy, "entry_blastdb", None))
            take("annotation", getattr(legacy, "entry_gtf", None))
            prepared = getattr(legacy, "prepared_params", {}) or {}
            take("search_fasta", prepared.get("target_fasta"))
            take("mask_fasta", prepared.get("mask_fasta"))

            # If the mask is configured to mirror the search scope and no
            # separate mask FASTA was extracted, reuse the search-scope file
            # so the Designer is pre-filled with a consistent mask value.
            if "mask_fasta" not in defaults and defaults.get("search_fasta"):
                try:
                    mirror = getattr(legacy, "mask_same_as_target_var", None)
                    skip = getattr(legacy, "skip_mask_var", None)
                    mirror_on = bool(mirror.get()) if mirror is not None else False
                    skip_on = bool(skip.get()) if skip is not None else False
                except tk.TclError:
                    mirror_on = False
                    skip_on = False
                if mirror_on and not skip_on:
                    defaults["mask_fasta"] = defaults["search_fasta"]

        # The Results/Output panel keeps its own output directory; prefer
        # whatever the user filled in there when Data prep has no value.
        for key, attr in (
            ("genome_fasta", "entry_genome"),
            ("output_dir", "entry_output"),
            ("blastdb", "entry_blastdb"),
        ):
            if key not in defaults:
                take(key, getattr(self, attr, None))
        return defaults

    def _show_motif_tab_by_name(self, name):
        self._show_designer_workbench()

    def _create_input_panel(self, parent):
        input_frame = ttk.LabelFrame(parent, text="Input", padding="8")
        input_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N), pady=(0, 6))
        input_frame.columnconfigure(1, weight=1)

        ttk.Label(input_frame, text="BED regions file:").grid(row=0, column=0, sticky=tk.W)
        self.entry_bed_path = ttk.Entry(input_frame)
        self.entry_bed_path.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=5)
        ttk.Button(input_frame, text="Browse",
                   command=lambda: self._browse_file(self.entry_bed_path)) \
            .grid(row=0, column=2, padx=3)

        ttk.Label(input_frame, text="or paste BED:").grid(row=1, column=0,
                                                       sticky=tk.NW)
        self.bed_text = tk.Text(input_frame, width=40, height=6,
                                font=("Consolas", 9))
        self.bed_text.grid(row=1, column=1, columnspan=2,
                           sticky=(tk.W, tk.E), padx=5, pady=3)

        ttk.Label(input_frame, text="Genome FASTA:").grid(row=2, column=0,
                                                         sticky=tk.W)
        self.entry_genome = ttk.Entry(input_frame)
        self.entry_genome.grid(row=2, column=1, sticky=(tk.W, tk.E), padx=5)
        ttk.Button(input_frame, text="Browse",
                   command=lambda: self._browse_file(self.entry_genome)) \
            .grid(row=2, column=2, padx=3)

        ttk.Label(input_frame, text="Output Directory:").grid(row=3, column=0,
                                                     sticky=tk.W)
        self.entry_output = ttk.Entry(input_frame)
        self.entry_output.grid(row=3, column=1, sticky=(tk.W, tk.E), padx=5)
        ttk.Button(input_frame, text="Browse",
                   command=lambda: self._browse_directory(self.entry_output)) \
            .grid(row=3, column=2, padx=3)

        params = ttk.LabelFrame(parent, text="Design and search", padding="8")
        params.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N))
        params.columnconfigure(1, weight=1)
        r = 0

        ttk.Label(params, text="System preset:").grid(row=r, column=0, sticky=tk.W)
        self.combo_preset = ttk.Combobox(
            params, values=PRESETS, state="readonly", width=16)
        self.combo_preset.set("cas9")
        self.combo_preset.grid(row=r, column=1, sticky=tk.W, padx=5)
        self.combo_preset.bind("<<ComboboxSelected>>", self._on_preset_selected)
        ttk.Button(params, text="Apply", command=self._apply_preset) \
            .grid(row=r, column=2, padx=3)
        self.preset_note = tk.StringVar(value="")
        ttk.Label(params, textvariable=self.preset_note, foreground="#666") \
            .grid(row=r, column=3, sticky=tk.W, padx=6)
        r += 1

        ttk.Label(params, text="Spacer length:").grid(row=r, column=0,
                                                   sticky=tk.W)
        self.entry_spacer = ttk.Entry(params, width=8)
        self.entry_spacer.insert(0, "20")
        self.entry_spacer.grid(row=r, column=1, sticky=tk.W, padx=5)
        ttk.Label(params, text="PAM:").grid(row=r, column=2, sticky=tk.W,
                                            padx=(10, 2))
        self.entry_pam = ttk.Entry(params, width=8)
        self.entry_pam.insert(0, "NGG")
        self.entry_pam.grid(row=r, column=3, sticky=tk.W, padx=2)
        r += 1

        ttk.Label(params, text="PAM side:").grid(row=r, column=0, sticky=tk.W)
        self.combo_pam_side = ttk.Combobox(
            params, values=["3prime", "5prime"], state="readonly", width=8)
        self.combo_pam_side.set("3prime")
        self.combo_pam_side.grid(row=r, column=1, sticky=tk.W, padx=5)
        ttk.Label(params, text="Max mismatches:").grid(row=r, column=2, sticky=tk.W,
                                                 padx=(10, 2))
        self.combo_max_mismatch = ttk.Combobox(
            params, values=["0", "1", "2", "3", "4"], state="readonly",
            width=5)
        self.combo_max_mismatch.set("4")
        self.combo_max_mismatch.grid(row=r, column=3, sticky=tk.W, padx=2)
        r += 1

        self.require_pam_var = tk.BooleanVar(value=True)
        ttk.Label(params, text="Search engine:").grid(row=r, column=2, sticky=tk.W,
                                             padx=(10, 2))
        self.combo_engine = ttk.Combobox(
            params, values=ENGINE_CHOICES, state="readonly", width=12)
        self.combo_engine.set("auto")
        self.combo_engine.grid(row=r, column=3, sticky=tk.W, padx=2)
        r += 1

        ttk.Label(params, text="Index prefix:").grid(row=r, column=0, sticky=tk.W)
        self.entry_index = ttk.Entry(params)
        self.entry_index.grid(row=r, column=1, sticky=(tk.W, tk.E), padx=5)
        ttk.Button(params, text="Browse", command=self._browse_index) \
            .grid(row=r, column=2, padx=3)
        ttk.Button(params, text="Build index", command=self._build_index) \
            .grid(row=r, column=3, padx=3)
        r += 1

        ttk.Label(params, text="BLAST db:").grid(row=r, column=0, sticky=tk.W)
        self.entry_blastdb = ttk.Entry(params)
        self.entry_blastdb.grid(row=r, column=1, sticky=(tk.W, tk.E), padx=5)
        ttk.Button(params, text="Browse", command=self._browse_blastdb) \
            .grid(row=r, column=2, padx=3)
        ttk.Label(params, text="Build:").grid(row=r, column=3, sticky=tk.W)
        self.entry_genome_build = ttk.Entry(params, width=10)
        self.entry_genome_build.insert(0, "hg38")
        self.entry_genome_build.grid(row=r, column=3, sticky=tk.W, padx=3)
        r += 1

        ttk.Label(params, text="On-target model:").grid(row=r, column=0,
                                                       sticky=tk.W)
        self.combo_on_target = ttk.Combobox(
            params,
            values=[
                "cropsr", "rules", "deepcas12a", "deepcpf1",
                "rna_rules", "tiger", "omega", "teep",
            ],
            state="readonly",
            width=10)
        self.combo_on_target.set("cropsr")
        self.combo_on_target.grid(row=r, column=1, sticky=tk.W, padx=5)
        ttk.Label(params, text="Off-target model:").grid(row=r, column=2,
                                                          sticky=tk.W,
                                                          padx=(10, 2))
        self.combo_off_target = ttk.Combobox(
            params,
            values=[
                "cfd", "pfs", "identity", "crispr_m",
                "deepcrispr", "crispai", "tiger",
            ],
            state="readonly", width=10)
        self.combo_off_target.set("cfd")
        self.combo_off_target.grid(row=r, column=3, sticky=tk.W, padx=2)
        r += 1

        ttk.Label(params, text="Filtering:").grid(row=r, column=2, sticky=tk.W,
                                             padx=(10, 2))
        self.filter_hard_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(params, text="Strict filtering",
                        variable=self.filter_hard_var) \
            .grid(row=r, column=3, sticky=tk.W)
        r += 1
        ttk.Label(params, text="DR sequence:").grid(row=r, column=0, sticky=tk.W)
        self.entry_dr = ttk.Entry(params)
        self.entry_dr.grid(row=r, column=1, columnspan=3,
                           sticky=(tk.W, tk.E), padx=5)
        r += 1
        ttk.Label(params, text="Target RNA:").grid(row=r, column=0, sticky=tk.W)
        self.entry_target_rna = ttk.Entry(params)
        self.entry_target_rna.grid(row=r, column=1, columnspan=3,
                                   sticky=(tk.W, tk.E), padx=5)
        r += 1
        ttk.Label(params, text="TSS distance:").grid(row=r, column=0, sticky=tk.W)
        self.entry_tss = ttk.Entry(params, width=10)
        self.entry_tss.grid(row=r, column=1, sticky=tk.W, padx=5)
        r += 1

        actions = ttk.Frame(parent)
        actions.grid(row=2, column=0, sticky=(tk.W, tk.E), pady=8)
        # 一键出库（library）已停用：按钮保留位置但不可点击。
        self.btn_run = ttk.Button(
            actions, text="One-click library (disabled)", command=self._run_library,
            state=tk.DISABLED)
        self.btn_run.pack(side=tk.LEFT, padx=4)
        ttk.Button(actions, text="Open output", command=self._open_output) \
            .pack(side=tk.LEFT, padx=4)
        ttk.Button(actions, text="Refresh results", command=self._refresh_output) \
            .pack(side=tk.LEFT, padx=4)
    def _create_output_panel(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(2, weight=1)

        dir_frame = ttk.Frame(parent)
        dir_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 6))
        dir_frame.columnconfigure(1, weight=1)
        ttk.Label(dir_frame, text="Output Directory:").grid(
            row=0, column=0, sticky=tk.W)
        self.entry_output = ttk.Entry(dir_frame)
        self.entry_output.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=5)
        ttk.Button(
            dir_frame, text="Browse",
            command=lambda: self._browse_directory(self.entry_output),
        ).grid(row=0, column=2, padx=3)
        ttk.Button(dir_frame, text="Refresh results",
                   command=self._refresh_output).grid(
                       row=0, column=3, padx=3)
        ttk.Button(dir_frame, text="Open output",
                   command=self._open_output).grid(
                       row=0, column=4, padx=3)

        summary = ttk.LabelFrame(parent, text="Summary", padding="6")
        summary.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S),
                     pady=(0, 6))
        summary.columnconfigure(0, weight=1)
        self.summary_text = scrolledtext.ScrolledText(
            summary, width=52, height=10, state="normal", wrap=tk.WORD)
        self.summary_text.grid(row=0, column=0, sticky=(tk.W, tk.E))

        files = ttk.LabelFrame(parent, text="Output files", padding="6")
        files.grid(row=2, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        files.columnconfigure(0, weight=1)
        files.rowconfigure(0, weight=1)
        self.file_list = tk.Listbox(files, height=8)
        self.file_list.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        self.file_list.bind("<Double-Button-1>", self._open_selected_file)

        candidates = ttk.LabelFrame(parent, text="Candidates", padding="6")
        candidates.grid(row=3, column=0, sticky=(tk.W, tk.E, tk.N, tk.S),
                        pady=(6, 0))
        candidates.columnconfigure(0, weight=1)
        candidates.rowconfigure(0, weight=1)
        self.candidate_tree = ttk.Treeview(candidates, show="headings")
        self.candidate_tree.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        cscroll = ttk.Scrollbar(
            candidates, orient=tk.VERTICAL,
            command=self.candidate_tree.yview,
        )
        cscroll.grid(row=0, column=1, sticky=(tk.N, tk.S))
        self.candidate_tree.configure(yscrollcommand=cscroll.set)
        parent.rowconfigure(3, weight=2)

    def _create_progress(self, parent):
        frame = ttk.Frame(parent)
        frame.grid(row=3, column=0, sticky=(tk.W, tk.E), pady=(6, 2))
        frame.columnconfigure(0, weight=1)
        self.progress_bar = ttk.Progressbar(
            frame, variable=self.progress_var, maximum=100
        )
        self.progress_bar.grid(row=0, column=0, sticky=(tk.W, tk.E))
        ttk.Label(frame, textvariable=self.progress_label).grid(
            row=0, column=1, padx=6)

    def _create_log(self, parent):
        frame = ttk.LabelFrame(parent, text="Log", padding="6")
        frame.grid(row=4, column=0, sticky=(tk.W, tk.E, tk.N, tk.S),
                   pady=(4, 0))
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        self.log_text = scrolledtext.ScrolledText(
            frame, height=12, state="normal", wrap=tk.WORD)
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        ttk.Button(frame, text="Clear", command=self._clear_log) \
            .grid(row=1, column=0, sticky=tk.W, pady=(3, 0))
        parent.rowconfigure(4, weight=1)

    # ---------- 输入输出辅助 ----------
    def _browse_file(self, entry):
        path = filedialog.askopenfilename()
        if path:
            entry.delete(0, tk.END)
            entry.insert(0, path)

    def _browse_directory(self, entry):
        path = filedialog.askdirectory()
        if path:
            entry.delete(0, tk.END)
            entry.insert(0, path)

    def _browse_index(self):
        path = filedialog.askopenfilename(
            filetypes=[("Genome index", "*.ggi *.json"), ("All", "*.*")])
        if not path:
            return
        base, ext = os.path.splitext(path)
        value = base if ext in (".ggi", ".json") else path
        self.entry_index.delete(0, tk.END)
        self.entry_index.insert(0, value)

    def _browse_blastdb(self):
        path = filedialog.askopenfilename(
            filetypes=[("BLAST db", "*.nin *.nsq *.nhr *.nal *.nog"),
                       ("All", "*.*")])
        if not path:
            return
        base, ext = os.path.splitext(path)
        value = base if ext in (".nin", ".nsq", ".nhr", ".nal", ".nog") \
            else path
        self.entry_blastdb.delete(0, tk.END)
        self.entry_blastdb.insert(0, value)

    def _apply_preset(self):
        key = self.combo_preset.get()
        preset = get_preset(key)
        if preset.get("spacer_len"):
            self.entry_spacer.delete(0, tk.END)
            self.entry_spacer.insert(0, str(preset["spacer_len"]))
        self.entry_pam.delete(0, tk.END)
        if preset.get("pam"):
            self.entry_pam.insert(0, preset["pam"])
        self.combo_pam_side.set(preset.get("pam_side") or "3prime")
        self.require_pam_var.set(bool(preset.get("pam_required")))
        self.preset_note.set(rule_summary(key))
        self._log("Applied preset: %s" % key)

    def _on_preset_selected(self, _event=None):
        self._apply_preset()

    def _bed_input_path(self):
        pasted = self.bed_text.get("1.0", tk.END).strip()
        if pasted:
            output = self.entry_output.get().strip()
            if not output:
                return None, "Fill in the output directory first"
            os.makedirs(output, exist_ok=True)
            path = os.path.join(output, "input_regions.bed")
            with open(path, "w", encoding="utf-8", newline="") as handle:
                handle.write(pasted + "\n")
            return path, ""
        path = self.entry_bed_path.get().strip()
        if not path or not os.path.isfile(path):
            return None, "Provide a valid BED file or paste BED content"
        return path, ""

    def _build_library_command(self, bed_path):
        cmd = [
            sys.executable, LIBRARY_SCRIPT, bed_path,
            self.entry_genome.get().strip(),
            self.entry_output.get().strip(),
        ]
        preset = self.combo_preset.get()
        preset_info = get_preset(preset)
        nuclease = preset_info.get("nuclease") or "cas9"
        # Keep ``custom`` as a first-class nuclease so the score dispatcher can
        # route an explicitly chosen on/off-target model to the custom path and
        # mark it reference-only (unverified) instead of silently using Cas9.
        tnpb_subtype = preset_info.get("tnpb_subtype") or "unknown"
        if preset == "custom":
            cmd += ["--mode", "free"]
        else:
            cmd += ["--mode", "preset", "--preset", preset]
        cmd += ["--spacer-len", self.entry_spacer.get().strip() or "20"]
        pam_required = bool(preset_info.get("pam_required"))
        if pam_required or preset == "custom":
            cmd += ["--pam", self.entry_pam.get().strip() or "NGG"]
            cmd += ["--pam-side", self.combo_pam_side.get()]
        cmd += ["--engine", self.combo_engine.get()]
        cmd += ["--max-mismatch", self.combo_max_mismatch.get()]
        cmd += ["--nuclease", nuclease]
        cmd += ["--tnpb-subtype", tnpb_subtype]
        cmd += ["--on-target-model", self.combo_on_target.get()]
        cmd += ["--off-target-model", self.combo_off_target.get()]
        if self.require_pam_var.get():
            cmd.append("--require-pam")
        if self.filter_hard_var.get():
            cmd.append("--filter-hard")
        index = self.entry_index.get().strip()
        if index:
            cmd += ["--index-path", index]
        blastdb = self.entry_blastdb.get().strip()
        if blastdb:
            cmd += ["--blastdb", blastdb]
        build = self.entry_genome_build.get().strip()
        if build:
            cmd += ["--genome-build", build]
        dr = self.entry_dr.get().strip()
        if dr:
            cmd += ["--direct-repeat", dr]
        target_rna = self.entry_target_rna.get().strip()
        if target_rna:
            cmd += ["--target-rna", target_rna]
        tss = self.entry_tss.get().strip()
        if tss:
            cmd += ["--tss-distance", tss]
        return cmd

    # ---------- 运行 ----------
    def _run_library(self):
        bed_path, error = self._bed_input_path()
        if error:
            messagebox.showerror("Input error", error)
            return
        genome = self.entry_genome.get().strip()
        output = self.entry_output.get().strip()
        if not genome or not os.path.isfile(genome):
            messagebox.showerror("Input error", "Select a valid genome FASTA")
            return
        if not output:
            messagebox.showerror("Input error", "Fill in the output directory")
            return
        os.makedirs(output, exist_ok=True)
        from design.library_preflight import preflight_library
        errors, warnings = preflight_library(
            self.combo_engine.get(),
            genome=genome,
            index_path=self.entry_index.get().strip(),
            blastdb=self.entry_blastdb.get().strip(),
            off_target_model=self.combo_off_target.get(),
        )
        if errors:
            messagebox.showerror(
                "Preflight failed",
                "\n".join(errors))
            return
        if warnings:
            self._log("Preflight notice:\n" + "\n".join(warnings))
        cmd = self._build_library_command(bed_path)
        self._run_async(cmd, "One-click library export", after=self._refresh_output)

    def _build_index(self):
        genome = self.entry_genome.get().strip()
        output = self.entry_output.get().strip()
        if not genome or not os.path.isfile(genome):
            messagebox.showerror("Input error", "Select a valid genome FASTA")
            return
        if not output:
            messagebox.showerror("Input error", "Fill in the output directory")
            return
        index_dir = os.path.join(output, "genome_index")
        cmd = [sys.executable, INDEX_SCRIPT, genome,
               "--output-dir", index_dir]
        self.entry_index.delete(0, tk.END)
        base = os.path.splitext(os.path.basename(genome))[0]
        self.entry_index.insert(0, os.path.join(index_dir, base))
        self._run_async(cmd, "Build index")

    def _run_async(self, cmd, description, after=None):
        self.progress_var.set(0)
        self.progress_label.set(description + " ...")
        if self.progress_bar is not None:
            self.progress_bar.stop()
            self.progress_bar.configure(mode="indeterminate")
            self.progress_bar.start(12)
        thread = threading.Thread(
            target=self._run_process, args=(cmd, description, after),
            daemon=True)
        thread.start()

    def _run_process(self, cmd, description, after):
        try:
            proc = subprocess.Popen(
                cmd, cwd=ROOT, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, bufsize=1,
                encoding="utf-8", errors="replace")
        except Exception as exc:
            self.run_on_ui(self._log, "Startup failed: %s" % exc)
            self.run_on_ui(self._finish_run, -1, None)
            return
        for line in proc.stdout:
            line = line.rstrip("\n")
            self.run_on_ui(self._log, line)
            parsed = parse_progress_line(line)
            if parsed is not None:
                value, label = parsed
                self.run_on_ui(
                    self._set_progress_now, value,
                    "%s %d%%" % (label, value))
        proc.wait()
        code = proc.returncode
        self.run_on_ui(self._finish_run, code, after)

    def _finish_run(self, code, after):
        if self.progress_bar is not None:
            self.progress_bar.stop()
            self.progress_bar.configure(mode="determinate")
        self.progress_var.set(100 if code == 0 else 0)
        self.progress_label.set("Complete" if code == 0 else "Failed")
        if code == 0 and after:
            after()

    def _set_progress_now(self, value, label):
        if self.progress_bar is not None:
            self.progress_bar.stop()
            self.progress_bar.configure(mode="determinate")
        self.progress_var.set(value)
        self.progress_label.set(label)

    # ---------- 输出 ----------
    def _refresh_output(self):
        output = self.entry_output.get().strip()
        self.summary_text.delete("1.0", tk.END)
        self.file_list.delete(0, tk.END)
        self.candidate_tree.delete(*self.candidate_tree.get_children())
        if not output or not os.path.isdir(output):
            self.summary_text.insert(tk.END, "Output directory has no results yet")
            return
        summary_path = os.path.join(output, "library_summary.json")
        if os.path.isfile(summary_path):
            with open(summary_path, "r", encoding="utf-8") as handle:
                summary = json.load(handle)
            self.summary_text.insert(
                tk.END, json.dumps(summary, indent=2, ensure_ascii=False))
        else:
            self.summary_text.insert(tk.END, "library_summary.json not found yet")
        for name in sorted(os.listdir(output)):
            path = os.path.join(output, name)
            if os.path.isfile(path) and name.endswith(
                    (".tsv", ".bed", ".json", ".log")):
                self.file_list.insert(tk.END, name)
        scores_path = os.path.join(output, "library_scores.tsv")
        if os.path.isfile(scores_path):
            with open(scores_path, "r", encoding="utf-8",
                      newline="") as handle:
                reader = csv.DictReader(handle, delimiter="\t")
                rows = [dict(row) for row in reader]
            if rows:
                columns = list(rows[0].keys())
                self.candidate_tree.configure(columns=columns)
                for col in columns:
                    self.candidate_tree.heading(col, text=col)
                    self.candidate_tree.column(
                        col, width=110, minwidth=70, stretch=True
                    )
                for row in rows:
                    self.candidate_tree.insert(
                        "", tk.END,
                        values=[str(row.get(col, "")) for col in columns],
                    )

    def _open_output(self):
        output = self.entry_output.get().strip()
        if output and os.path.isdir(output):
            os.startfile(output)  # noqa
        else:
            messagebox.showinfo("Output", "Fill in and run the output directory first")

    def _open_selected_file(self, _event):
        selection = self.file_list.curselection()
        if not selection:
            return
        output = self.entry_output.get().strip()
        path = os.path.join(output, self.file_list.get(selection[0]))
        if os.path.isfile(path):
            os.startfile(path)  # noqa

    # ---------- 工具与模型 ----------
    def _launch_tool(self, script, extra=None):
        cmd = [sys.executable, script]
        if extra:
            cmd.extend(extra)
        try:
            subprocess.Popen(cmd, cwd=ROOT)
        except Exception as exc:
            messagebox.showerror("Startup failed", str(exc))

    def refresh_models(self):
        try:
            statuses = get_all_statuses()
        except Exception as exc:
            self.status_var.set("Failed to read model status: %s" % exc)
            return
        text = " | ".join("%s=%s" % (key, status)
                          for key, status in statuses.items())
        self.status_var.set(text)

    # ---------- 日志 ----------
    def _log(self, message):
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)

    def _clear_log(self):
        self.log_text.delete("1.0", tk.END)


def main():
    root = tk.Tk()
    UnifiedGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
