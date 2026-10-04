from __future__ import annotations

import os
import csv
import re
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, font as tkfont, messagebox, scrolledtext, ttk
from typing import Dict, Optional


ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "shared"))

from design.pattern_runner import PatternRunner, RunnerConfig  # noqa: E402
from design.pattern_spec import PatternKind, PatternSpec, Side  # noqa: E402
from design.system_presets import rule_summary  # noqa: E402
from design.library_preflight import ENGINE_CHOICES  # noqa: E402
from design import workbench_form  # noqa: E402
from design.workbench_form import (  # noqa: E402
    MODE_LABELS,
    PAIR_RANK_POLICY_FIELDS,
    PRESET_KEYS,
    WorkbenchFormState,
    model_display_name as _model_display_name,
    split_model_selection as _split_model_selection,
)
from output.candidate_export import (  # noqa: E402
    SUPPORTED_FORMATS,
    export_selected,
)
from utils.log_utils import LogWriter, install_excepthook  # noqa: E402
from utils import system_memory  # noqa: E402
from utils.paths import default_output_dir  # noqa: E402


class MultiSelectDropdown(ttk.Menubutton):
    """Readonly-style dropdown with a persistent checkbutton popup."""

    def __init__(
        self,
        master,
        variable: tk.StringVar,
        values=(),
        width: int = 16,
        on_change=None,
    ):
        self.variable = variable
        self._values = []
        self._option_vars = {}
        self._checkbuttons = {}
        self._selected_order = []
        self._on_change = on_change
        self._display_var = tk.StringVar(master)
        super().__init__(
            master,
            textvariable=self._display_var,
            width=width,
            direction="below",
        )
        default_font = tkfont.nametofont("TkDefaultFont")
        self._normal_font = default_font.copy()
        self._bold_font = default_font.copy()
        self._bold_font.configure(weight="bold")
        self._popup = tk.Toplevel(self)
        self._popup.withdraw()
        self._popup.overrideredirect(True)
        self._popup.transient(self.winfo_toplevel())
        self._popup.configure(background="#ffffff")
        self._popup.bind("<Escape>", lambda _event: self._hide_popup())
        self._popup.bind("<Button-1>", self._on_popup_click, add="+")
        self.bind("<Button-1>", self._on_button_click, add="+")
        self._var_trace = self.variable.trace_add(
            "write", self._on_variable_changed
        )
        self.set_values(values)

    def cget(self, key):
        if key == "values":
            return tuple(self._values)
        return super().cget(key)

    def set_values(self, values) -> None:
        self._values = [str(value) for value in values]
        for child in self._popup.winfo_children():
            child.destroy()
        self._option_vars = {}
        self._checkbuttons = {}
        selected = [
            model for model in _split_model_selection(self.variable.get())
            if model in self._values
        ]
        self._selected_order = selected
        for value in self._values:
            option_var = tk.BooleanVar(value=value in selected)
            self._option_vars[value] = option_var
            check = tk.Checkbutton(
                self._popup,
                text=value,
                variable=option_var,
                command=lambda v=value: self._toggle(v),
                anchor="w",
                justify=tk.LEFT,
                padx=6,
                pady=2,
                background="#ffffff",
                activebackground="#f1f1f1",
                highlightthickness=0,
                borderwidth=0,
            )
            check.pack(fill=tk.X)
            self._checkbuttons[value] = check
        self._sync_display()
        if self._popup.winfo_ismapped():
            self._position_popup()

    def _on_variable_changed(self, *_args) -> None:
        selected = [
            model for model in _split_model_selection(self.variable.get())
            if model in self._values
        ]
        self._selected_order = selected
        for value, option_var in self._option_vars.items():
            option_var.set(value in selected)
        self._sync_display()

    def _toggle(self, value: str) -> None:
        selected = list(self._selected_order)
        if self._option_vars[value].get():
            if value not in selected:
                selected.append(value)
        else:
            selected = [model for model in selected if model != value]
            if not selected:
                self._option_vars[value].set(True)
                return
        self._selected_order = selected
        self.variable.set(",".join(selected))
        if self._on_change is not None:
            self._on_change()

    def _on_button_click(self, _event=None):
        if self._popup.winfo_ismapped():
            self._hide_popup()
        else:
            self._show_popup()
        return "break"

    def _show_popup(self) -> None:
        self._position_popup()
        self._popup.deiconify()
        self._popup.lift()
        try:
            self._popup.grab_set()
        except tk.TclError:
            pass

    def _hide_popup(self) -> None:
        try:
            if self._popup.grab_current() == self._popup:
                self._popup.grab_release()
        except tk.TclError:
            pass
        self._popup.withdraw()

    def _position_popup(self) -> None:
        self.update_idletasks()
        self._popup.update_idletasks()
        width = max(self.winfo_width(), self._popup.winfo_reqwidth())
        height = self._popup.winfo_reqheight()
        x = self.winfo_rootx()
        y = self.winfo_rooty() + self.winfo_height()
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        x = max(0, min(x, screen_width - width))
        y = max(0, min(y, screen_height - height))
        self._popup.geometry("%dx%d+%d+%d" % (width, height, x, y))

    def _on_popup_click(self, event) -> None:
        if not self._popup.winfo_ismapped():
            return
        inside = (
            self._popup.winfo_rootx() <= event.x_root <
            self._popup.winfo_rootx() + self._popup.winfo_width()
            and self._popup.winfo_rooty() <= event.y_root <
            self._popup.winfo_rooty() + self._popup.winfo_height()
        )
        if not inside:
            self._hide_popup()

    def _sync_display(self) -> None:
        primary = self._selected_order[0] if self._selected_order else ""
        for value, check in self._checkbuttons.items():
            is_primary = value == primary
            check.configure(
                text=("[P] " if is_primary else "") + _model_display_name(value),
                font=self._bold_font if is_primary else self._normal_font,
            )
        if self._selected_order:
            self._display_var.set(
                "Primary: " + ", ".join(
                    _model_display_name(model)
                    for model in self._selected_order
                )
            )
        else:
            self._display_var.set("Select model")

    def destroy(self) -> None:
        try:
            self.variable.trace_remove("write", self._var_trace)
        except (tk.TclError, ValueError):
            pass
        try:
            self._popup.destroy()
        except tk.TclError:
            pass
        super().destroy()


class PatternDesignerWorkbench:
    def __init__(self, root: tk.Tk, default_bed: bool = False):
        self.root = root
        self.root.title(
            "TargetDesign-workbench BED Designer" if default_bed
            else "TargetDesign-workbench"
        )
        self.root.geometry("1440x900")
        self.root.minsize(1200, 700)
        try:
            self.root.state("zoomed")
        except tk.TclError:
            pass

        self.mode_var = tk.StringVar(value=PatternKind.SINGLE_MOTIF_FLANK.value)
        self.status_var = tk.StringVar(value="Ready")
        self.progress_var = tk.DoubleVar(value=0)
        self.progress_label = tk.StringVar(value="Ready")
        self.progress_bar: Optional[ttk.Progressbar] = None
        self._last_progress_success: Optional[bool] = None
        self.running = False
        self._syncing = False
        self._traced_vars = set()
        self._hint_labels = []
        self._hint_max_len = 20
        self.active_side_var = tk.StringVar(value="left")
        self.input_mode_var = tk.StringVar(
            value="bed" if default_bed else "sequence"
        )
        self.nuclease_var = tk.StringVar(value="cas9")
        self.tnpb_subtype_var = tk.StringVar(value="unknown")
        self.require_pam_var = tk.BooleanVar(value=True)
        self.side_preset_vars = {
            side: tk.StringVar(value="cas9")
            for side in ("target", "left", "right")
        }
        self.side_off_target_model_vars = {
            side: tk.StringVar(value="auto")
            for side in ("target", "left", "right")
        }
        self.side_on_target_model_vars = {
            side: tk.StringVar(value="auto")
            for side in ("target", "left", "right")
        }
        self._side_model_widgets: Dict[str, dict] = {}
        self.active_side_var.trace_add(
            "write", lambda *args: self._sync_active_side_rules()
        )
        self.vars: Dict[str, tk.StringVar] = {}
        self._entry_widgets: Dict[str, ttk.Entry] = {}
        self._combo_widgets: Dict[str, ttk.Combobox] = {}
        self._row_widgets: Dict[str, tuple] = {}
        self._row_indices: Dict[str, int] = {}
        self.buttons: Dict[str, ttk.Button] = {}
        self.current_runner: Optional[PatternRunner] = None
        self.last_result_rows = []
        self.export_format_var = tk.StringVar(value="csv")

        self.log_writer = LogWriter("designer_workbench")
        install_excepthook(self.log_writer)

        self._create_header()
        self._create_body()
        self._create_run_bar()
        self._create_progress()
        self._create_log()
        self._rebuild_pattern_frame()
        self._refresh_preview()

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.bind("<Configure>", lambda _e: self._update_hints())

    def _create_header(self) -> None:
        header = ttk.Frame(self.root, padding="10")
        header.grid(row=0, column=0, sticky=(tk.W, tk.E))
        header.columnconfigure(1, weight=1)

        ttk.Label(header, text="Design Pattern").grid(
            row=0, column=0, sticky=tk.W, padx=(0, 6)
        )
        self.mode_combo = ttk.Combobox(
            header,
            values=list(MODE_LABELS.values()),
            state="readonly",
            width=28,
        )
        self.mode_combo.set(MODE_LABELS[self.mode_var.get()])
        self.mode_combo.grid(row=0, column=1, sticky=tk.W)
        self.mode_combo.bind("<<ComboboxSelected>>", self._on_mode_changed)

        run_actions = ttk.Frame(header)
        run_actions.grid(row=0, column=2, padx=(16, 0))
        find_button = ttk.Button(
            run_actions,
            text="Find Targets",
            command=self._run_find_targets,
        )
        find_button.pack(side=tk.LEFT, padx=(0, 6))
        score_button = ttk.Button(
            run_actions,
            text="Score & Off-target",
            command=self._run_score_targets,
        )
        score_button.pack(side=tk.LEFT)
        self.buttons["find"] = find_button
        self.buttons["score"] = score_button

        ttk.Label(
            header,
            textvariable=self.status_var,
            foreground="#555",
        ).grid(row=0, column=3, sticky=tk.E, padx=(20, 0))

    def _create_body(self) -> None:
        body = ttk.Panedwindow(self.root, orient=tk.HORIZONTAL)
        body.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        left = ttk.Frame(body, padding="8")
        center = ttk.Frame(body, padding="8")
        right = ttk.Frame(body, padding="8")
        body.add(left, weight=3)
        body.add(center, weight=3)
        body.add(right, weight=4)

        self._create_left_panel(left)
        self._create_center_panel(center)
        self._create_right_panel(right)

    def _create_left_panel(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(3, weight=1)

        ttk.Label(parent, text="Common & Left TAM", font=("Arial", 11, "bold")) \
            .grid(row=0, column=0, sticky=tk.W, pady=(0, 6))

        _common_header, common = self._create_collapsible(
            parent, "Common Inputs", 1, default_open=True
        )
        common.columnconfigure(1, weight=1)
        self._add_file_row(common, 0, "search_fasta", "Search FASTA")
        self._add_file_row(common, 0, "bed_regions", "BED Regions")
        self._add_file_row(common, 1, "genome_fasta", "Genome FASTA")
        self._add_file_row(common, 2, "mask_fasta", "Mask FASTA")
        self._add_file_row(common, 3, "blastdb", "BLAST DB Prefix")
        self._add_entry_row(
            common, 4, "result_label", "Result Label",
            hint="e.g. Cas12f-TTR; blank = auto system-target",
        )

        mode_row = ttk.Frame(parent)
        mode_row.grid(row=2, column=0, sticky=tk.W, pady=(2, 4))
        ttk.Label(mode_row, text="Input:").pack(side=tk.LEFT)
        ttk.Radiobutton(
            mode_row,
            text="Sequence (FASTA)",
            value="sequence",
            variable=self.input_mode_var,
            command=self._sync_input_mode,
        ).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Radiobutton(
            mode_row,
            text="BED Regions",
            value="bed",
            variable=self.input_mode_var,
            command=self._sync_input_mode,
        ).pack(side=tk.LEFT, padx=(6, 0))

        self._sync_input_mode()

        self.pattern_frame = ttk.Frame(parent)
        self.pattern_frame.grid(
            row=3, column=0, sticky=(tk.W, tk.E, tk.N, tk.S)
        )
        self.pattern_frame.columnconfigure(0, weight=1)

    def _create_center_panel(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(3, weight=1)

        _middle_header, self.middle_frame = self._create_collapsible(
            parent, "Middle", 0, default_open=True
        )
        self.middle_frame.columnconfigure(0, weight=1)

        ttk.Label(parent, text="Structure Preview", font=("Arial", 11, "bold")) \
            .grid(row=2, column=0, sticky=tk.W, pady=(0, 6))
        self.preview_text = tk.Text(
            parent,
            wrap=tk.WORD,
            height=4,
            font=("Consolas", 11),
        )
        self.preview_text.grid(
            row=3, column=0, sticky=(tk.W, tk.E, tk.N, tk.S)
        )

    def _create_center_panel_v2(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(4, weight=2)

        self.middle_frame = ttk.Frame(parent)
        self.middle_frame.grid(
            row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 8)
        )
        self.middle_frame.columnconfigure(0, weight=1)

        ttk.Label(parent, text="Structure Preview", font=("Arial", 11, "bold")) \
            .grid(row=1, column=0, sticky=tk.W, pady=(0, 6))

        self.preview_text = tk.Text(
            parent,
            wrap=tk.WORD,
            height=6,
            font=("Consolas", 11),
        )
        self.preview_text.grid(
            row=2, column=0, sticky=(tk.W, tk.E, tk.N, tk.S)
        )

        results_header = ttk.Frame(parent)
        results_header.grid(row=3, column=0, sticky=(tk.W, tk.E), pady=(12, 4))
        ttk.Label(
            results_header,
            text="Extracted Candidates",
            font=("Arial", 11, "bold"),
        ).pack(side=tk.LEFT)
        self.export_button = ttk.Button(
            results_header,
            text="Export Selected",
            command=self._export_selected,
            state=tk.DISABLED,
        )
        self.export_button.pack(side=tk.RIGHT)
        self.export_format = ttk.Combobox(
            results_header,
            values=list(SUPPORTED_FORMATS),
            textvariable=self.export_format_var,
            state="readonly",
            width=12,
        )
        self.export_format.pack(side=tk.RIGHT, padx=(0, 8))
        ttk.Label(results_header, text="Format:").pack(
            side=tk.RIGHT, padx=(0, 4)
        )

        table_frame = ttk.Frame(parent)
        table_frame.grid(row=4, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)

        self.result_tree = ttk.Treeview(
            table_frame,
            show="headings",
            selectmode="extended",
        )
        self.result_tree.grid(
            row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S)
        )
        yscroll = ttk.Scrollbar(
            table_frame,
            orient=tk.VERTICAL,
            command=self.result_tree.yview,
        )
        yscroll.grid(row=0, column=1, sticky=(tk.N, tk.S))
        self.result_tree.configure(yscrollcommand=yscroll.set)

        xscroll = ttk.Scrollbar(
            table_frame,
            orient=tk.HORIZONTAL,
            command=self.result_tree.xview,
        )
        xscroll.grid(row=1, column=0, sticky=(tk.W, tk.E))
        self.result_tree.configure(xscrollcommand=xscroll.set)

    def _create_right_panel(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)
        canvas = tk.Canvas(parent, highlightthickness=0)
        scrollbar = ttk.Scrollbar(
            parent, orient=tk.VERTICAL, command=canvas.yview
        )
        canvas.configure(yscrollcommand=scrollbar.set)
        self.right_tam_frame = ttk.Frame(canvas)
        self.right_tam_frame.columnconfigure(0, weight=1)
        window_id = canvas.create_window(
            (0, 0), window=self.right_tam_frame, anchor="nw"
        )
        self.right_tam_frame.bind(
            "<Configure>",
            lambda _e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.bind(
            "<Configure>",
            lambda e: canvas.itemconfigure(window_id, width=e.width),
        )
        canvas.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))

    def _create_run_bar(self) -> None:
        container = ttk.Frame(self.root)
        container.grid(row=2, column=0, sticky=(tk.W, tk.E), pady=(4, 0))
        container.columnconfigure(0, weight=1)
        header, content = self._create_collapsible(
            container, "Run Settings", 0, default_open=False
        )
        content.columnconfigure(0, weight=1)
        content.columnconfigure(1, weight=1)

        run_left = ttk.Frame(content)
        run_left.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(0, 6))
        run_left.columnconfigure(1, weight=1)
        run_right = ttk.Frame(content)
        run_right.grid(row=0, column=1, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(6, 0))
        run_right.columnconfigure(1, weight=1)

        self._add_combo_row(
            run_left, 0, "engine", "Engine", ENGINE_CHOICES,
            default="auto",
        )
        self._add_combo_row(
            run_left, 1, "max_mismatch", "Max Mismatch",
            ["0", "1", "2", "3", "4"], default="4",
        )
        self._add_combo_row(
            run_left, 2, "max_bulge", "Max Bulge",
            ["", "0", "1"], default="",
        )
        self._add_combo_row(
            run_left, 3, "pam_mode", "PAM Mode",
            ["strict_ngg", "guidescan2_nrg", "custom"],
            default="strict_ngg",
        )
        self._add_entry_row(run_left, 4, "seed_len", "Seed Length", default="12", hint="informational only - the engine uses the index k-mer length as the seed length")
        self._add_file_row(run_right, 0, "index_path", "Index Prefix")
        self._add_entry_row(run_right, 1, "gc_min", "GC Min")
        self._add_entry_row(run_right, 2, "gc_max", "GC Max")
        self._add_entry_row(run_right, 3, "genome_build", "Genome Build")
        self._add_check_row(
            run_right, 4, "filter_hard", "Hard Filter",
            default=False,
        )
        self._add_combo_row(
            run_left, 5, "memory_mode", "Memory Limit",
            ["auto", "custom", "unlimited"], default="auto",
        )
        self._add_entry_row(
            run_right, 5, "max_memory_mb", "Custom MiB",
            default="32768",
        )
        self.memory_resolved_var = tk.StringVar(value="Resolved: detecting...")
        ttk.Label(
            run_right,
            textvariable=self.memory_resolved_var,
            foreground="#555",
        ).grid(row=6, column=0, columnspan=2, sticky=tk.W, pady=(2, 0))
        self._combo_widgets["memory_mode"].bind(
            "<<ComboboxSelected>>",
            lambda _event: self._on_memory_mode_changed(),
            add="+",
        )
        self._entry_widgets["max_memory_mb"].bind(
            "<KeyRelease>",
            lambda _event: self._refresh_memory_resolution(),
            add="+",
        )
        self._on_memory_mode_changed()

        self._add_entry_row(
            run_right, 7, "search_timeout_s", "Search timeout (s)",
            default="",
            hint="Optional wall-clock limit for the off-target search step",
        )

        pair_policy = ttk.LabelFrame(
            content,
            text="PairRank prediction_only policy",
            padding="6",
        )
        pair_policy.grid(
            row=1, column=0, columnspan=2,
            sticky=(tk.W, tk.E), pady=(8, 0),
        )
        policy_left = ttk.Frame(pair_policy)
        policy_left.grid(row=0, column=0, sticky=(tk.W, tk.E), padx=(0, 6))
        policy_left.columnconfigure(1, weight=1)
        policy_right = ttk.Frame(pair_policy)
        policy_right.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=(6, 0))
        policy_right.columnconfigure(1, weight=1)
        for index, field in enumerate(PAIR_RANK_POLICY_FIELDS):
            target = policy_left if index < 5 else policy_right
            row = index if index < 5 else index - 5
            self._add_entry_row(
                target,
                row,
                "pair_rank_%s" % field,
                field,
            )

    def _create_progress(self) -> None:
        frame = ttk.Frame(self.root, padding="8")
        frame.grid(row=3, column=0, sticky=(tk.W, tk.E))
        frame.columnconfigure(0, weight=1)
        self.style = ttk.Style(self.root)
        try:
            if "clam" in self.style.theme_names():
                self.style.theme_use("clam")
        except tk.TclError:
            pass
        self.style.configure(
            "Ready.Horizontal.TProgressbar",
            background="#2e7d32",
            troughcolor="#e0e0e0",
        )
        self.style.configure(
            "Missing.Horizontal.TProgressbar",
            background="#c62828",
            troughcolor="#e0e0e0",
        )
        self.style.configure(
            "Run.Horizontal.TProgressbar",
            background="#1565c0",
            troughcolor="#e0e0e0",
        )
        bar = ttk.Progressbar(
            frame,
            variable=self.progress_var,
            maximum=100,
            mode="determinate",
            style="Ready.Horizontal.TProgressbar",
        )
        bar.grid(row=0, column=0, sticky=(tk.W, tk.E))
        ttk.Label(
            frame,
            textvariable=self.progress_label,
            width=50,
            anchor=tk.W,
        ).grid(row=0, column=1, padx=(8, 0))
        self.progress_bar = bar

    def _create_log(self) -> None:
        container = ttk.Frame(self.root, padding="8")
        container.grid(row=4, column=0, sticky=(tk.W, tk.E))
        container.columnconfigure(0, weight=1)
        header, content = self._create_collapsible(
            container, "Run Log", 0, default_open=False
        )
        content.columnconfigure(0, weight=1)
        content.rowconfigure(0, weight=1)
        ttk.Button(
            header,
            text="Clear",
            command=self._clear_log,
        ).pack(side=tk.RIGHT, padx=4)

        self.log_text = scrolledtext.ScrolledText(
            content,
            height=8,
            wrap=tk.WORD,
            font=("Consolas", 9),
        )
        self.log_text.grid(
            row=0, column=0, sticky=(tk.W, tk.E), pady=(4, 0)
        )

    def _rebuild_pattern_frame(self) -> None:
        self._hint_labels = []
        self._side_model_widgets = {}
        for frame in (self.pattern_frame, self.middle_frame, self.right_tam_frame):
            for child in frame.winfo_children():
                child.destroy()
        kind = PatternKind(self.mode_var.get())

        def make_group(parent: ttk.Frame, title: str) -> ttk.LabelFrame:
            group = ttk.LabelFrame(parent, text=title, padding="6")
            group.pack(fill=tk.X, pady=(0, 6))
            group.columnconfigure(1, weight=1)
            return group

        if kind is PatternKind.SINGLE_MOTIF_FLANK:
            group = make_group(self.pattern_frame, "Target TAM")
            self._add_side_preset_row(group, 0, "target")
            self._add_entry_row(
                group, 1, "motif", "PAM/TAM Motif",
                hint="PAM/TAM motif",
            )
            self._add_entry_row(
                group, 2, "flank", "Target Length",
                hint="Target length",
            )
            self._add_combo_row(
                group, 3, "side", "Target Position",
                ["downstream", "upstream"],
                default="upstream",
                hint="Relative position to PAM/TAM",
            )
            self._add_use_for_run(group, 4, "target")
            self._add_side_model_row(group, "target", 5)
            ttk.Label(
                self.middle_frame,
                text="Not used in this pattern",
                foreground="#777",
            ).pack(anchor=tk.W)
            ttk.Label(
                self.right_tam_frame,
                text="Not used in this pattern",
                foreground="#777",
            ).pack(anchor=tk.W)
        else:
            left = make_group(self.pattern_frame, "Left TAM")
            self._add_side_preset_row(left, 0, "left")
            self._add_entry_row(
                left, 1, "left_motif", "PAM/TAM",
                hint="Left PAM/TAM",
            )
            self._add_entry_row(
                left, 2, "left_flank", "Target Length",
                hint="Left target length",
            )
            self._add_combo_row(
                left, 3, "left_side", "Target Position",
                ["downstream", "upstream"],
                default="upstream",
                hint="Relative position to left PAM/TAM",
            )
            self._add_check_row(
                left, 4, "left_require_pam", "Require PAM",
                default=True, hint="Require the left PAM/TAM during scoring",
            )
            if kind is PatternKind.Y_CENTERED_MOTIFS:
                self._add_entry_row(
                    left, 5, "left_min_distance", "Minimum Distance",
                    hint="From middle motif to left PAM/TAM",
                )
                self._add_entry_row(
                    left, 6, "left_max_distance", "Maximum Distance",
                    hint="From middle motif to left PAM/TAM",
                )
                self._add_use_for_run(left, 7, "left")
                self._add_side_model_row(left, "left", 8)
            else:
                self._add_use_for_run(left, 5, "left")
                self._add_side_model_row(left, "left", 6)

            middle = make_group(self.middle_frame, "Middle")
            if kind is PatternKind.Y_CENTERED_MOTIFS:
                self._add_entry_row(
                    middle, 0, "y_sequence", "Middle Motif",
                    hint="Middle motif (no mismatch) included",
                )
            else:
                self._add_entry_row(
                    middle, 0, "min_gap", "Minimum Distance",
                    hint="Minimum distance to left PAM/TAM",
                )
                self._add_entry_row(
                    middle, 1, "max_gap", "Maximum Distance",
                    hint="Maximum distance to left PAM/TAM",
                )

            right = make_group(self.right_tam_frame, "Right TAM")
            self._add_side_preset_row(right, 0, "right")
            self._add_entry_row(
                right, 1, "right_motif", "PAM/TAM",
                hint=(
                    "Right PAM/TAM motif"
                    if kind is PatternKind.Y_CENTERED_MOTIFS
                    else "Right PAM/TAM"
                ),
            )
            self._add_entry_row(
                right, 2, "right_flank", "Target Length",
                hint="Right target length",
            )
            self._add_combo_row(
                right, 3, "right_side", "Target Position",
                ["downstream", "upstream"],
                default="upstream",
                hint="Relative position to right PAM/TAM",
            )
            self._add_check_row(
                right, 4, "right_require_pam", "Require PAM",
                default=True, hint="Require the right PAM/TAM during scoring",
            )
            if kind is PatternKind.Y_CENTERED_MOTIFS:
                self._add_entry_row(
                    right, 5, "right_min_distance", "Minimum Distance",
                    hint="From middle motif to right PAM/TAM",
                )
                self._add_entry_row(
                    right, 6, "right_max_distance", "Maximum Distance",
                    hint="From middle motif to right PAM/TAM",
                )
                self._add_use_for_run(right, 7, "right")
                self._add_side_model_row(right, "right", 8)
            else:
                self._add_use_for_run(right, 5, "right")
                self._add_side_model_row(right, "right", 6)

        self._bind_sync_traces()

    def _rebuild_pattern_frame_v1(self) -> None:
        for child in self.pattern_frame.winfo_children():
            child.destroy()
        kind = PatternKind(self.mode_var.get())
        row_index = 0

        def add_group(title: str) -> ttk.LabelFrame:
            nonlocal row_index
            group = ttk.LabelFrame(
                self.pattern_frame, text=title, padding="6"
            )
            group.grid(
                row=row_index, column=0, sticky=(tk.W, tk.E), pady=(0, 6)
            )
            group.columnconfigure(1, weight=1)
            row_index += 1
            return group

        if kind is PatternKind.SINGLE_MOTIF_FLANK:
            group = add_group("Target")
            self._add_entry_row(
                group, 0, "motif", "PAM/TAM Motif",
                hint="PAM/TAM motif used for target definition",
            )
            self._add_entry_row(
                group, 1, "flank", "Target Length",
                hint="Length of the target sequence",
            )
            self._add_combo_row(
                group, 2, "side", "Target Position",
                ["downstream", "upstream"],
                default="upstream",
                hint="Relative position of target to PAM/TAM",
            )
            self._add_apply_button(group, 3, "target")
        elif kind is PatternKind.MOTIF_GAP_MOTIF:
            left = add_group("Left TAM")
            self._add_entry_row(
                left, 0, "left_motif", "PAM/TAM",
                hint="Left PAM/TAM motif",
            )
            self._add_entry_row(
                left, 1, "left_flank", "Target Length",
                hint="Length of left target",
            )
            self._add_combo_row(
                left, 2, "left_side", "Target Position",
                ["downstream", "upstream"],
                default="upstream",
                hint="Relative position of left target to left PAM/TAM",
            )
            self._add_apply_button(left, 3, "left")

            middle = add_group("Middle")
            self._add_entry_row(
                middle, 0, "min_gap", "Minimum Distance",
                hint="Minimum distance to left PAM/TAM",
            )
            self._add_entry_row(
                middle, 1, "max_gap", "Maximum Distance",
                hint="Maximum distance to left PAM/TAM",
            )

            right = add_group("Right TAM")
            self._add_entry_row(
                right, 0, "right_motif", "PAM/TAM",
                hint="Right PAM/TAM motif",
            )
            self._add_entry_row(
                right, 1, "right_flank", "Target Length",
                hint="Length of right target",
            )
            self._add_combo_row(
                right, 2, "right_side", "Target Position",
                ["downstream", "upstream"],
                default="upstream",
                hint="Relative position of right target to right PAM/TAM",
            )
            self._add_apply_button(right, 3, "right")
        else:
            left = add_group("Left TAM")
            self._add_entry_row(
                left, 0, "left_motif", "PAM/TAM",
                hint="Left PAM/TAM motif",
            )
            self._add_entry_row(
                left, 1, "left_flank", "Target Length",
                hint="Length of left target",
            )
            self._add_combo_row(
                left, 2, "left_side", "Target Position",
                ["downstream", "upstream"],
                default="upstream",
                hint="Relative position of left target position to left PAM/TAM",
            )
            self._add_entry_row(
                left, 3, "left_min_distance", "Minimum Distance",
                hint="Minimum distance from the middle motif to left PAM/TAM",
            )
            self._add_entry_row(
                left, 4, "left_max_distance", "Maximum Distance",
                hint="Maximum distance from the middle motif to the left PAM/TAM",
            )
            self._add_apply_button(left, 5, "left")

            middle = add_group("Middle")
            self._add_entry_row(
                middle, 0, "y_sequence", "Middle Motif",
                hint="Middle motif (no mismatch) included",
            )

            right = add_group("Right TAM")
            self._add_entry_row(
                right, 0, "right_motif", "PAM/TAM",
                hint="Right PAM/TAM motif",
            )
            self._add_entry_row(
                right, 1, "right_flank", "Target Length",
                hint="Length of right target",
            )
            self._add_combo_row(
                right, 2, "right_side", "Target Position",
                ["downstream", "upstream"],
                default="upstream",
                hint="Relative position of right target position to right PAM/TAM",
            )
            self._add_entry_row(
                right, 3, "right_min_distance", "Minimum Distance",
                hint="Minimum distance from the middle motif to right PAM/TAM",
            )
            self._add_entry_row(
                right, 4, "right_max_distance", "Maximum Distance",
                hint="Maximum distance from the middle motif to the right PAM/TAM",
            )
            self._add_apply_button(right, 5, "right")

        self._bind_sync_traces()

    def _rebuild_pattern_frame_legacy(self) -> None:
        for child in self.pattern_frame.winfo_children():
            child.destroy()

        kind = PatternKind(self.mode_var.get())
        if kind is PatternKind.SINGLE_MOTIF_FLANK:
            self._add_entry_row(
                self.pattern_frame, 0, "motif", "PAM/TAM Motif",
                hint="PAM/TAM motif used for target definition",
            )
            self._add_entry_row(
                self.pattern_frame, 1, "flank", "Target Length",
                hint="Length of the target sequence",
            )
            self._add_combo_row(
                self.pattern_frame,
                2,
                "side",
                "Target Position",
                ["downstream", "upstream"],
                default="upstream",
                hint="Relative position of target to PAM/TAM",
            )
        elif kind is PatternKind.MOTIF_GAP_MOTIF:
            self._add_entry_row(
                self.pattern_frame, 0, "left_motif", "Left PAM/TAM",
                hint="Left PAM/TAM motif",
            )
            self._add_entry_row(
                self.pattern_frame, 1, "left_flank", "Left Target Length",
                hint="Length of left target",
            )
            self._add_combo_row(
                self.pattern_frame,
                2,
                "left_side",
                "Left Target Position",
                ["downstream", "upstream"],
                default="upstream",
                hint="Relative position of left target to left PAM/TAM",
            )
            self._add_entry_row(
                self.pattern_frame, 3, "min_gap", "Minimum Distance",
                hint="Minimum distance to left PAM/TAM",
            )
            self._add_entry_row(
                self.pattern_frame, 4, "max_gap", "Maximum Distance",
                hint="Maximum distance to left PAM/TAM",
            )
            self._add_entry_row(
                self.pattern_frame, 5, "right_motif", "Right PAM/TAM",
                hint="Right PAM/TAM motif",
            )
            self._add_entry_row(
                self.pattern_frame, 6, "right_flank", "Right Target Length",
                hint="Length of right target",
            )
            self._add_combo_row(
                self.pattern_frame,
                7,
                "right_side",
                "Right Target Position",
                ["downstream", "upstream"],
                default="upstream",
                hint="Relative position of right target to right PAM/TAM",
            )
        else:
            self._add_entry_row(
                self.pattern_frame, 0, "y_sequence", "Middle Motif",
                hint="Middle motif (no mismatch) included",
            )
            self._add_entry_row(
                self.pattern_frame, 1, "left_motif", "Left PAM/TAM",
                hint="Left PAM/TAM motif",
            )
            self._add_entry_row(
                self.pattern_frame, 2, "left_flank", "Left Target Length",
                hint="Length of left target",
            )
            self._add_combo_row(
                self.pattern_frame,
                3,
                "left_side",
                "Left Target Position",
                ["downstream", "upstream"],
                default="upstream",
                hint="Relative position of left target position to left PAM/TAM",
            )
            self._add_entry_row(
                self.pattern_frame, 4, "left_min_distance", "Minimum Distance",
                hint="Minimum distance from the middle motif to left PAM/TAM",
            )
            self._add_entry_row(
                self.pattern_frame, 5, "left_max_distance", "Maximum Distance",
                hint="Maximum distance from the middle motif to the left PAM/TAM",
            )
            self._add_entry_row(
                self.pattern_frame, 6, "right_motif", "Right PAM/TAM Motif",
                hint="Right PAM/TAM motif",
            )
            self._add_entry_row(
                self.pattern_frame, 7, "right_flank", "Right Target Length",
                hint="Length of right target",
            )
            self._add_combo_row(
                self.pattern_frame,
                8,
                "right_side",
                "Right Target Position",
                ["downstream", "upstream"],
                default="upstream",
                hint="Relative position of right target position to right PAM/TAM",
            )
            self._add_entry_row(
                self.pattern_frame, 9, "right_min_distance", "Minimum Distance",
                hint="Minimum distance from the middle motif to right PAM/TAM",
            )
            self._add_entry_row(
                self.pattern_frame, 10, "right_max_distance", "Maximum Distance",
                hint="Maximum distance from the middle motif to the right PAM/TAM",
            )
        self._bind_sync_traces()

    def _create_collapsible(
        self,
        parent: ttk.Frame,
        title: str,
        row: int,
        default_open: bool = True,
        colspan: int = 1,
    ):
        header = ttk.Frame(parent)
        header.grid(row=row, column=0, columnspan=colspan,
                    sticky=(tk.W, tk.E))
        content = ttk.Frame(parent)
        state = {"open": default_open}
        if default_open:
            content.grid(row=row + 1, column=0, columnspan=colspan,
                         sticky=(tk.W, tk.E))
        else:
            content.grid_remove()

        def toggle() -> None:
            state["open"] = not state["open"]
            if state["open"]:
                content.grid(row=row + 1, column=0, columnspan=colspan,
                             sticky=(tk.W, tk.E))
            else:
                content.grid_remove()
            button.config(
                text=("[-] " if state["open"] else "[+] ") + title
            )

        button = ttk.Button(
            header,
            text=("[-] " if default_open else "[+] ") + title,
            command=toggle,
        )
        button.pack(side=tk.LEFT)
        return header, content

    def _truncate_hint(self, text: str, max_len: int = 20) -> str:
        text = (text or "").strip()
        if len(text) <= max_len:
            return text
        return text[:max_len - 1].rstrip() + "..."

    def _update_hints(self) -> None:
        width = self.root.winfo_width()
        if width >= 1600:
            max_len = 10000
        elif width >= 1400:
            max_len = 90
        else:
            max_len = 20
        if max_len == self._hint_max_len:
            return
        self._hint_max_len = max_len
        for label, text in self._hint_labels:
            try:
                label.config(text=self._truncate_hint(text, max_len))
            except tk.TclError:
                pass

    def _add_entry_row(
        self,
        parent: ttk.Frame,
        row: int,
        key: str,
        label: str,
        default: str = "",
        hint: str = "",
    ) -> None:
        label_box = ttk.Frame(parent)
        label_box.grid(
            row=row, column=0, sticky=tk.W, pady=2, padx=(0, 6)
        )
        ttk.Label(label_box, text=label).pack(anchor=tk.W)
        if hint:
            hint_label = ttk.Label(
                label_box,
                text=self._truncate_hint(hint),
                foreground="#777",
                font=("", 8),
            )
            hint_label.pack(anchor=tk.W)
            self._hint_labels.append((hint_label, hint))
        var = tk.StringVar(value=default)
        entry = ttk.Entry(parent, textvariable=var)
        entry.grid(row=row, column=1, sticky=(tk.W, tk.E), pady=2)
        entry.bind("<KeyRelease>", lambda _event: self._refresh_preview())
        self.vars[key] = var
        self._entry_widgets[key] = entry

    def _add_combo_row(
        self,
        parent: ttk.Frame,
        row: int,
        key: str,
        label: str,
        values,
        default: Optional[str] = None,
        hint: str = "",
    ) -> None:
        label_box = ttk.Frame(parent)
        label_box.grid(
            row=row, column=0, sticky=tk.W, pady=2, padx=(0, 6)
        )
        ttk.Label(label_box, text=label).pack(anchor=tk.W)
        if hint:
            hint_label = ttk.Label(
                label_box,
                text=self._truncate_hint(hint),
                foreground="#777",
                font=("", 8),
            )
            hint_label.pack(anchor=tk.W)
            self._hint_labels.append((hint_label, hint))
        var = tk.StringVar(value=default or values[0])
        combo = ttk.Combobox(parent, values=values, textvariable=var, state="readonly")
        combo.grid(row=row, column=1, sticky=(tk.W, tk.E), pady=2)
        combo.bind("<<ComboboxSelected>>", lambda _event: self._refresh_preview())
        self.vars[key] = var
        self._combo_widgets[key] = combo

    def _add_check_row(
        self,
        parent: ttk.Frame,
        row: int,
        key: str,
        label: str,
        default: bool = False,
        hint: str = "",
    ) -> None:
        label_box = ttk.Frame(parent)
        label_box.grid(
            row=row, column=0, sticky=tk.W, pady=2, padx=(0, 6)
        )
        ttk.Label(label_box, text=label).pack(anchor=tk.W)
        if hint:
            hint_label = ttk.Label(
                label_box,
                text=self._truncate_hint(hint),
                foreground="#777",
                font=("", 8),
            )
            hint_label.pack(anchor=tk.W)
            self._hint_labels.append((hint_label, hint))
        var = tk.BooleanVar(value=default)
        tk.Checkbutton(
            parent, text="", variable=var,
        ).grid(row=row, column=1, sticky=tk.W, padx=5, pady=2)
        self.vars[key] = var

    def _add_apply_button(
        self,
        parent: ttk.Frame,
        row: int,
        side: str,
    ) -> None:
        ttk.Button(
            parent,
            text="Apply to Pipeline",
            command=lambda s=side: self._apply_tam_to_pipeline(s),
        ).grid(
            row=row, column=0, columnspan=3, sticky=tk.W, pady=(6, 0)
        )

    def _apply_tam_to_pipeline(self, side: str) -> None:
        mapping = {
            "target": ("motif", "flank", "side"),
            "left": ("left_motif", "left_flank", "left_side"),
            "right": ("right_motif", "right_flank", "right_side"),
        }
        keys = mapping.get(side)
        if not keys:
            return
        motif_key, flank_key, side_key = keys
        self._syncing = True
        try:
            for target_key, source_key in (
                ("pam", motif_key),
                ("spacer_len", flank_key),
                ("pam_side", side_key),
            ):
                target_var = self.vars.get(target_key)
                source_var = self.vars.get(source_key)
                if target_var is not None and source_var is not None:
                    value = str(source_var.get()).strip()
                    if value:
                        if target_key == "pam_side":
                            value = self._side_to_pam_side(value)
                        target_var.set(value)
        finally:
            self._syncing = False
        self.status_var.set("%s TAM applied to pipeline" % side)
        self._log_line(
            "Applied %s TAM to pipeline: PAM/TAM=%s, Target Length=%s, "
            "Target Position=%s"
            % (
                side,
                self._value("pam"),
                self._value("spacer_len"),
                self._value(side_key),
            )
        )

    def _add_side_preset_row(
        self,
        parent: ttk.Frame,
        row: int,
        side: str,
    ) -> None:
        label_box = ttk.Frame(parent)
        label_box.grid(row=row, column=0, sticky=tk.W, pady=2, padx=(0, 6))
        ttk.Label(label_box, text="System Preset").pack(anchor=tk.W)
        ttk.Label(
            label_box,
            text="Preset fills this TAM side",
            foreground="#777",
            font=("", 8),
        ).pack(anchor=tk.W)
        preset_var = self.side_preset_vars[side]
        combo = ttk.Combobox(
            parent, values=PRESET_KEYS, textvariable=preset_var,
            state="readonly", width=14,
        )
        combo.grid(row=row, column=1, sticky=tk.W, padx=5, pady=2)
        combo.bind(
            "<<ComboboxSelected>>",
            lambda _e, s=side: self._apply_side_preset(s),
        )
        ttk.Button(
            parent,
            text="Apply",
            command=lambda s=side: self._apply_side_preset(s),
        ).grid(row=row, column=2, padx=(3, 0), pady=2)

    def _add_use_for_run(
        self,
        parent: ttk.Frame,
        row: int,
        side: str,
    ) -> None:
        ttk.Radiobutton(
            parent,
            text="Use for Run",
            value=side,
            variable=self.active_side_var,
        ).grid(
            row=row, column=0, columnspan=3, sticky=tk.W, pady=(6, 0)
        )

    def _add_side_model_row(self, parent: ttk.Frame, side: str, row: int) -> None:
        """Add the per-side on/off-target model controls + crispAI toggle.

        The dropdown values adapt to the side's nuclease (SpCas9, Cas12a, or
        other).  On/Off-target fall back to ``auto`` placeholders when they do
        not apply to the side's nuclease; crispAI only shows for SpCas9.
        """
        opt = ttk.Frame(parent)
        opt.grid(row=row, column=0, columnspan=3, sticky=tk.W, pady=2)
        opt.columnconfigure(1, weight=1)

        ttk.Label(opt, text="On-target Model").grid(
            row=0, column=0, sticky=tk.W, padx=(0, 6))
        on_combo = MultiSelectDropdown(
            opt,
            variable=self.side_on_target_model_vars[side],
            width=16,
            on_change=self._refresh_preview,
        )
        on_combo.grid(row=0, column=1, sticky=tk.W, padx=5)

        ttk.Label(opt, text="Off-target Model").grid(
            row=1, column=0, sticky=tk.W, padx=(0, 6))
        off_combo = MultiSelectDropdown(
            opt,
            variable=self.side_off_target_model_vars[side],
            width=16,
            on_change=self._refresh_preview,
        )
        off_combo.grid(row=1, column=1, sticky=tk.W, padx=5)
        self._side_model_widgets[side] = {
            "on_combo": on_combo,
            "off_combo": off_combo,
        }
        self._refresh_side_model_options(side)

    def _form_state(self) -> WorkbenchFormState:
        """Snapshot the designer controls for the shared form layer."""
        return WorkbenchFormState(
            values={key: var.get() for key, var in self.vars.items()},
            mode=self.mode_var.get(),
            input_mode=self.input_mode_var.get(),
            nuclease=self.nuclease_var.get(),
            tnpb_subtype=self.tnpb_subtype_var.get(),
            require_pam=bool(self.require_pam_var.get()),
            active_side=self.active_side_var.get(),
            side_presets={
                side: var.get()
                for side, var in self.side_preset_vars.items()
            },
            side_on_target_models={
                side: var.get()
                for side, var in self.side_on_target_model_vars.items()
            },
            side_off_target_models={
                side: var.get()
                for side, var in self.side_off_target_model_vars.items()
            },
            log=self._log_line,
        )

    def _apply_field_updates(self, updates: dict) -> None:
        """Write shared-form field values back into the Tk variables."""
        for key, value in updates.items():
            if key == "require_pam":
                self.require_pam_var.set(bool(value))
            elif key == "nuclease":
                self.nuclease_var.set(str(value))
            elif key == "tnpb_subtype":
                self.tnpb_subtype_var.set(str(value))
            else:
                var = self.vars.get(key)
                if var is not None:
                    var.set(value)

    def _refresh_side_model_options(self, side: str) -> None:
        """Reconfigure the per-side model dropdowns to match its nuclease."""
        widgets = self._side_model_widgets.get(side)
        if not widgets:
            return
        options = workbench_form.side_model_options(
            self.side_preset_vars[side].get() or "custom")
        on_combo = widgets["on_combo"]
        off_combo = widgets["off_combo"]
        on_combo.set_values(options["on_target"])
        off_combo.set_values(options["off_target"])
        on_var = self.side_on_target_model_vars[side]
        off_var = self.side_off_target_model_vars[side]
        on_value = workbench_form.resolve_side_model_selection(
            on_var.get(),
            options["on_target"],
            options["on_target_preferred"],
        )
        if on_value is not None:
            on_var.set(on_value)
        off_value = workbench_form.resolve_side_model_selection(
            off_var.get(), options["off_target"])
        if off_value is not None:
            off_var.set(off_value)

    def _apply_side_preset(self, side: str) -> None:
        preset_key = self.side_preset_vars[side].get() or "custom"
        if not workbench_form.SIDE_FIELD_KEYS.get(side):
            return
        self._apply_field_updates(
            workbench_form.side_preset_updates(preset_key, side))
        self.active_side_var.set(side)
        self.status_var.set(
            "%s side preset applied: %s" % (side, rule_summary(preset_key))
        )
        self._log_line(
            "%s side preset applied: %s" % (side, rule_summary(preset_key))
        )
        self._refresh_side_model_options(side)
        self._refresh_preview()

    def _active_side_keys(self) -> tuple:
        return workbench_form.active_side_keys(self.active_side_var.get())

    def _sync_active_side_rules(self) -> None:
        if not hasattr(self, "vars"):
            return
        self._apply_field_updates(
            workbench_form.active_side_updates(self._form_state()))

    def _is_bed_mode(self) -> bool:
        return self.input_mode_var.get() == "bed"

    def _sync_input_mode(self) -> None:
        bed = self._is_bed_mode()
        self._set_row_visible("search_fasta", not bed)
        self._set_row_visible("bed_regions", bed)
        if self.buttons:
            self._refresh_readiness()

    def _set_row_visible(self, key: str, visible: bool) -> None:
        widgets = self._row_widgets.get(key)
        if not widgets:
            return
        for widget in widgets:
            if visible:
                widget.grid()
            else:
                widget.grid_remove()

    def _add_file_row(
        self,
        parent: ttk.Frame,
        row: int,
        key: str,
        label: str,
    ) -> None:
        label_widget = ttk.Label(parent, text=label)
        label_widget.grid(
            row=row, column=0, sticky=tk.W, pady=2, padx=(0, 6)
        )
        var = tk.StringVar()
        entry = ttk.Entry(parent, textvariable=var)
        entry.grid(row=row, column=1, sticky=(tk.W, tk.E), pady=2)
        button = ttk.Button(
            parent,
            text="Browse",
            command=lambda k=key: self._browse_file(k),
        )
        button.grid(row=row, column=2, padx=(4, 0), pady=2)
        self.vars[key] = var
        self._row_widgets[key] = (label_widget, entry, button)
        self._row_indices[key] = row

    def _browse_file(self, key: str) -> None:
        path = filedialog.askopenfilename(parent=self.root)
        if path:
            self.vars[key].set(path)
            self._refresh_preview()

    def _browse_dir(self, key: str) -> None:
        path = filedialog.askdirectory(parent=self.root)
        if path:
            self.vars[key].set(path)
            self._refresh_preview()

    def _on_mode_changed(self, _event=None) -> None:
        value = self.mode_combo.get()
        for key, label in MODE_LABELS.items():
            if label == value:
                self.mode_var.set(key)
                break
        self._rebuild_pattern_frame()
        self._refresh_preview()

    def _value(self, key: str, default: str = "") -> str:
        var = self.vars.get(key)
        return var.get().strip() if var else default

    def _auto_memory_limit(self) -> int:
        return workbench_form.auto_memory_limit()

    def _resolved_memory_limit(self) -> int:
        return workbench_form.resolved_memory_limit(self._form_state())

    def _on_memory_mode_changed(self) -> None:
        entry = self._entry_widgets.get("max_memory_mb")
        mode = self._value("memory_mode", "auto").lower()
        if entry is not None:
            entry.configure(
                state="normal" if mode == "custom" else "disabled")
            if mode == "custom" and not entry.get().strip():
                try:
                    entry.insert(0, str(self._auto_memory_limit()))
                except ValueError:
                    entry.insert(0, "32768")
        self._refresh_memory_resolution()

    def _refresh_memory_resolution(self) -> None:
        var = getattr(self, "memory_resolved_var", None)
        if var is None:
            return
        mode = self._value("memory_mode", "auto").lower()
        try:
            value = self._resolved_memory_limit()
        except ValueError as exc:
            var.set("Resolved: %s" % exc)
            return
        if mode == "unlimited":
            var.set("Resolved: Unlimited")
            return
        if mode == "custom":
            var.set(
                "Resolved: %s (custom)"
                % system_memory.format_memory_mb(value))
            return
        snapshot = system_memory.memory_snapshot()
        var.set(
            "Resolved: %s (%s total, %s available)"
            % (
                system_memory.format_memory_mb(value),
                system_memory.format_memory_mb(snapshot["total_mb"]),
                system_memory.format_memory_mb(snapshot["available_mb"]),
            )
        )

    def apply_defaults(self, defaults: Dict[str, str]) -> None:
        """Overlay caller-provided values (e.g. from Data prep) onto fields.

        Only keys that already exist in :attr:`vars` are updated, and empty
        values are ignored so an absent extraction does not wipe what the user
        has already entered. The preview is refreshed so any readiness state is
        recomputed from the newly filled inputs.
        """
        if not defaults:
            return
        changed = False
        for key, value in defaults.items():
            var = self.vars.get(key)
            if var is not None and value:
                var.set(value)
                changed = True
        if changed:
            self._refresh_preview()

    def _int_value(self, key: str, default: str = "") -> Optional[int]:
        value = self._value(key, default)
        return int(value) if value.isdigit() else None

    def _bool_value(self, key: str, default: bool = False) -> bool:
        var = self.vars.get(key)
        if var is None:
            return default
        try:
            return bool(var.get())
        except Exception:
            return default

    def _search_timeout_s(self) -> Optional[float]:
        """Resolve the optional off-target search timeout, in seconds."""
        return workbench_form.search_timeout_s(self._form_state())

    def _resolve_side_models(self, side: str) -> tuple:
        """Return (on_target, off_target, reference_only) for one TAM side."""
        return workbench_form.resolve_side_models(self._form_state(), side)

    def _to_side(self, value: str, default: Side = Side.UPSTREAM) -> Side:
        return workbench_form.to_side(value, default)

    def _side_to_pam_side(self, value: str, default: str = "3prime") -> str:
        return workbench_form.side_to_pam_side(value, default)

    def _pam_side_to_side(self, value: str, default: str = "upstream") -> str:
        return workbench_form.pam_side_to_side(value, default)

    def _sync_pattern_fields(self) -> None:
        kind = PatternKind(self.mode_var.get())
        if kind is PatternKind.SINGLE_MOTIF_FLANK:
            pairs = [
                ("motif", "pam"),
                ("flank", "spacer_len"),
                ("side", "pam_side"),
            ]
        else:
            pairs = [
                ("left_motif", "pam"),
                ("left_flank", "spacer_len"),
                ("left_side", "pam_side"),
            ]
        for left_key, right_key in pairs:
            left_var = self.vars.get(left_key)
            right_var = self.vars.get(right_key)
            if left_var is None or right_var is None:
                continue
            left_value = str(left_var.get()).strip()
            right_value = str(right_var.get()).strip()
            if left_value and not right_value:
                if (left_key, right_key) in (
                    ("side", "pam_side"),
                    ("left_side", "pam_side"),
                ):
                    right_var.set(self._side_to_pam_side(left_value))
                else:
                    right_var.set(left_value)
            elif right_value and not left_value:
                if (left_key, right_key) in (
                    ("side", "pam_side"),
                    ("left_side", "pam_side"),
                ):
                    left_var.set(self._pam_side_to_side(right_value))
                else:
                    left_var.set(right_value)

    def _bind_sync_traces(self) -> None:
        for key in (
            "motif", "flank", "side",
            "left_motif", "left_flank", "left_side",
            "pam", "spacer_len", "pam_side",
        ):
            var = self.vars.get(key)
            if var is None:
                continue
            if id(var) in self._traced_vars:
                continue
            try:
                var.trace_add(
                    "write",
                    lambda *args, k=key: self._on_sync_field_changed(k),
                )
            except Exception:
                pass
            self._traced_vars.add(id(var))

    def _on_sync_field_changed(self, key: str) -> None:
        if self._syncing:
            return
        self._syncing = True
        try:
            self._propagate_from(key)
        finally:
            self._syncing = False

    def _propagate_from(self, changed_key: str) -> None:
        kind = PatternKind(self.mode_var.get())
        if kind is PatternKind.SINGLE_MOTIF_FLANK:
            pairs = [
                ("motif", "pam"),
                ("flank", "spacer_len"),
                ("side", "pam_side"),
            ]
        else:
            pairs = [
                ("left_motif", "pam"),
                ("left_flank", "spacer_len"),
                ("left_side", "pam_side"),
            ]
        for left_key, right_key in pairs:
            if changed_key not in (left_key, right_key):
                continue
            left_var = self.vars.get(left_key)
            right_var = self.vars.get(right_key)
            if left_var is None or right_var is None:
                continue
            if changed_key == left_key:
                value = str(left_var.get()).strip()
                if value:
                    if (left_key, right_key) in (
                        ("side", "pam_side"),
                        ("left_side", "pam_side"),
                    ):
                        right_var.set(self._side_to_pam_side(value))
                    else:
                        right_var.set(value)
            else:
                value = str(right_var.get()).strip()
                if value:
                    if (left_key, right_key) in (
                        ("side", "pam_side"),
                        ("left_side", "pam_side"),
                    ):
                        left_var.set(self._pam_side_to_side(value))
                    else:
                        left_var.set(value)

    def _current_spec(self) -> PatternSpec:
        return workbench_form.build_pattern_spec(self._form_state())

    def _default_run_label(self) -> str:
        return workbench_form.default_run_label(self._form_state())

    def _pair_rank_policy_values(self):
        return workbench_form.pair_rank_policy_values(self._form_state())

    def _prepare_genome_fasta(self) -> str:
        """Return a plain-text Genome FASTA path (accepts .fna.gz input)."""
        return workbench_form.prepare_genome_fasta(self._form_state())

    def _current_config(self) -> RunnerConfig:
        return workbench_form.build_runner_config(self._form_state())

    def _refresh_preview(self) -> None:
        if not hasattr(self, "preview_text"):
            return
        self._sync_pattern_fields()
        self.preview_text.delete("1.0", tk.END)
        try:
            spec = self._current_spec()
            spec.validate()
            columns = spec.candidate_columns()
            self.preview_text.insert(tk.END, spec.describe())
            self.preview_text.insert(
                tk.END,
                "\n\nCandidate columns:\n" + "\n".join(columns),
            )
            self.status_var.set("Ready")
        except Exception as exc:
            self.preview_text.insert(tk.END, f"Invalid pattern: {exc}")
            self.status_var.set("Invalid pattern")
        if not self.running:
            self._refresh_readiness()

    def _show_error(self, title: str, message: str) -> None:
        self.status_var.set("Failed")
        self._finish_progress(False)
        self._log_line(message)
        try:
            messagebox.showerror(title, message, parent=self.root)
        except tk.TclError:
            pass

    def _failure_detail(self, lines, limit: int = 6) -> str:
        tail = []
        for line in lines:
            text = line.rstrip()
            if text:
                tail.append(text)
        return "\n".join(tail[-limit:])

    def _show_step_failure(
        self, label: str, returncode: int, detail: str = ""
    ) -> None:
        title = "%s failed" % label.rstrip(".")
        message = "Pipeline stopped with return code %d." % returncode
        if detail:
            message += "\n\nLast output:\n%s" % detail
        self._show_error(title, message)

    def _start_progress(self, label: str = "Running...") -> None:
        if self.progress_bar is None:
            return
        self.progress_bar.stop()
        self.progress_bar.configure(
            mode="indeterminate",
            style="Run.Horizontal.TProgressbar",
        )
        self.progress_bar.start(12)
        self.progress_var.set(0)
        self.progress_label.set(label)

    def _set_progress(self, value: int, label: str = "") -> None:
        if self.progress_bar is None:
            return
        self.progress_bar.stop()
        self.progress_bar.configure(
            mode="determinate",
            style="Run.Horizontal.TProgressbar",
        )
        self.progress_var.set(max(0, min(100, value)))
        if label and re.search(r"\d+/\d+$", label):
            self.progress_label.set(label)
        elif label:
            self.progress_label.set("%s %d%%" % (label, value))
        else:
            self.progress_label.set("%d%%" % value)

    def _finish_progress(self, success: bool = True) -> None:
        if self.progress_bar is None:
            return
        self.progress_bar.stop()
        style = (
            "Ready.Horizontal.TProgressbar"
            if success
            else "Missing.Horizontal.TProgressbar"
        )
        self.progress_bar.configure(mode="determinate", style=style)
        self.progress_var.set(100 if success else 0)
        self.progress_label.set("Ready" if success else "Failed")
        self._last_progress_success = success

    def _refresh_readiness(self) -> None:
        if self.progress_bar is None:
            return
        errors = self._readiness_errors()
        if errors:
            self.progress_bar.stop()
            self.progress_bar.configure(
                mode="determinate",
                style="Missing.Horizontal.TProgressbar",
            )
            self.progress_var.set(100)
            self.progress_label.set("Missing: %s" % errors[0])
            self._last_progress_success = False
        else:
            self.progress_bar.stop()
            self.progress_bar.configure(
                mode="determinate",
                style="Ready.Horizontal.TProgressbar",
            )
            self.progress_var.set(100)
            self.progress_label.set("Ready")
            self._last_progress_success = True

    def _readiness_errors(self) -> list:
        return workbench_form.readiness_errors(self._form_state())

    def _handle_command_line(self, line: str) -> None:
        self._log_line(line)
        text = line.strip()
        if text.startswith("PROGRESS_TARGET:"):
            counter = text.split(":", 1)[1].strip()
            if re.fullmatch(r"\d+/\d+", counter):
                self.root.after(
                    0,
                    lambda c=counter: self.progress_label.set(
                        "Analyzing target %s" % c
                    ),
                )
            return
        if not text.startswith("PROGRESS:"):
            return
        parts = text.split()
        if len(parts) < 3:
            return
        try:
            value = int(parts[-1])
        except ValueError:
            return
        label = " ".join(parts[1:-1]) or parts[1]
        self.root.after(
            0,
            lambda v=value, l=label: self._set_progress(v, l),
        )

    def _log_writer_note(self, message: str) -> None:
        """Mirror a message into the session log file, not just the UI."""
        writer = getattr(self, "log_writer", None)
        if writer is None:
            return
        try:
            writer.write(message)
        except Exception:
            pass

    def _confirm_pipeline_prompt(self, request: Dict[str, str]) -> bool:
        """Ask the user to approve a pipeline confirmation request.

        Called on the pipeline worker thread, so the dialog is scheduled on
        the Tk thread while this thread waits for the answer. Both the reason
        and the answer are written to the session log.
        """
        if not isinstance(request, dict):
            return False
        kind = request.get("kind")
        reason = request.get("reason") or "unknown"
        if kind == "python_fallback":
            label = "Python fallback"
            title = "Slow Python fallback"
            message = (
                "The native off-target engine is unavailable, so the indexed "
                "search would fall back to the pure-Python implementation.\n\n"
                "On a whole genome that implementation can take many hours, so "
                "this run may never finish.\n\n"
                "Fallback reason:\n%s\n\n"
                "Continue with the Python fallback?" % reason
            )
        elif kind == "engine_fallback":
            target, _, detail = reason.partition("|")
            target = target.strip() or "another"
            detail = detail.strip() or "unknown"
            label = "Engine fallback"
            title = "Switch off-target engine"
            message = (
                "The preferred off-target engine could not run, so this "
                "search would continue with the %s engine instead.\n\n"
                "The engines differ in seeding and gap handling, so the "
                "resulting hit list may differ from the one the selected "
                "engine would have produced.\n\n"
                "Failures so far:\n%s\n\n"
                "Continue with the %s engine?" % (target, detail, target)
            )
            reason = detail
        else:
            return False
        self._log_writer_note(
            "%s confirmation requested; reason: %s" % (label, reason))
        result: Dict[str, bool] = {}
        done = threading.Event()

        def ask() -> None:
            try:
                result["value"] = bool(
                    messagebox.askyesno(title, message, parent=self.root))
            except tk.TclError:
                result["value"] = False
            finally:
                done.set()

        self.root.after(0, ask)
        done.wait()
        approved = bool(result.get("value"))
        decision = "approved" if approved else "declined"
        self._log_line(
            "%s %s by user (reason: %s)" % (label, decision, reason))
        self._log_writer_note(
            "%s %s by user; reason: %s" % (label, decision, reason))
        return approved

    def _prepare_runner(
        self, require_genome: bool = True
    ) -> PatternRunner:
        spec = self._current_spec()
        spec.validate()
        config = self._current_config()
        if config.max_memory_mode == "auto":
            snapshot = system_memory.memory_snapshot()
            self._log_line(
                "Memory limit: auto, resolved=%d MiB "
                "(50%% total, 75%% available guard; total=%d MiB, "
                "available=%d MiB)"
                % (
                    config.max_memory_mb,
                    snapshot["total_mb"],
                    snapshot["available_mb"],
                )
            )
        elif config.max_memory_mode == "custom":
            self._log_line(
                "Memory limit: custom, resolved=%d MiB"
                % config.max_memory_mb)
        else:
            self._log_line("Memory limit: unlimited")
        output_dir = config.output_dir or default_output_dir()
        if self._is_bed_mode():
            regions = self._value("bed_regions")
            if not regions:
                raise ValueError(
                    "BED Regions file is required in BED designer mode."
                )
            if not os.path.isfile(regions):
                raise ValueError("BED Regions not found: %s" % regions)
        else:
            search_fasta = self._value("search_fasta")
            if not search_fasta:
                raise ValueError(
                    "Search FASTA is required. Click \'Extract Target FASTA\' "
                    "in Data prep first, or fill the Search FASTA field."
                )
            if not os.path.isfile(search_fasta):
                raise ValueError("Search FASTA not found: %s" % search_fasta)
        if require_genome:
            genome_fasta = self._value("genome_fasta")
            if not genome_fasta:
                raise ValueError("Genome FASTA is required")
            if not os.path.isfile(genome_fasta):
                raise ValueError("Genome FASTA not found: %s" % genome_fasta)
        os.makedirs(output_dir, exist_ok=True)
        return PatternRunner(spec, config)

    def _require_extract_output(self, runner: PatternRunner) -> None:
        path = runner.extract_output_path()
        if runner.spec.kind is PatternKind.Y_CENTERED_MOTIFS:
            if not os.path.isdir(path):
                raise ValueError(
                    "Extracted targets not found. Run Find Targets first."
                )
        elif not os.path.isfile(path):
            raise ValueError(
                "Extracted targets not found. Run Find Targets first."
            )

    def _run_steps(
        self,
        start: int,
        end: Optional[int],
        label: str,
        require_genome: bool = True,
    ) -> None:
        if self.running:
            return
        try:
            runner = self._prepare_runner(require_genome=require_genome)
            self.current_runner = runner
            if start > 0:
                self._require_extract_output(runner)
        except Exception as exc:
            self._show_error(
                "Configuration error",
                "Configuration error: %s" % exc,
            )
            self._refresh_readiness()
            return

        self.running = True
        for key in ("find", "score"):
            self.buttons[key].config(state=tk.DISABLED)
        self.status_var.set(label)
        self._start_progress(label)
        self._log_line("Starting %s" % label)

        def worker() -> None:
            output_lines = []

            def on_line(line: str) -> None:
                output_lines.append(line)
                if len(output_lines) > 200:
                    del output_lines[: len(output_lines) - 200]
                self._handle_command_line(line)

            try:
                returncode = runner.run_pipeline(
                    on_line=on_line,
                    start=start,
                    end=end,
                    on_prompt=self._confirm_pipeline_prompt,
                )
                if returncode == 0:
                    self.root.after(
                        0,
                        lambda: (
                            self.status_var.set("Complete"),
                            self._finish_progress(True),
                        ),
                    )
                else:
                    detail = self._failure_detail(output_lines)
                    self.root.after(
                        0,
                        lambda rc=returncode, text=detail: (
                            self._show_step_failure(
                                label, rc, text
                            )
                        ),
                    )
            except Exception as exc:
                self.root.after(
                    0,
                    lambda e=exc: self._show_error(
                        "Pipeline failed",
                        "Pipeline error: %s" % e,
                    ),
                )
            finally:
                try:
                    self.root.after(0, self._finish_run)
                except Exception:
                    # The window was closed while the worker was unwinding.
                    pass

        threading.Thread(target=worker, daemon=True).start()

    def _run_find_targets(self) -> None:
        self._run_steps(
            0,
            1,
            "Finding targets...",
            require_genome=self._is_bed_mode(),
        )

    def _run_score_targets(self) -> None:
        self._run_steps(
            1,
            None,
            "Scoring targets...",
            require_genome=True,
        )

    def _finish_run(self) -> None:
        self.running = False
        for key in ("find", "score"):
            self.buttons[key].config(state=tk.NORMAL)
        if self._last_progress_success:
            self._refresh_readiness()

    def _populate_results(self) -> None:
        if self.current_runner is None:
            return
        try:
            rows = self.current_runner.read_extract_candidates()
        except Exception as exc:
            self._log_line(f"Failed to read extracted candidates: {exc}")
            rows = []

        self.last_result_rows = rows
        self.result_tree.delete(*self.result_tree.get_children())

        if not rows:
            self.export_button.config(state=tk.DISABLED)
            return

        columns = list(rows[0].keys())
        columns = [
            column for column in columns
            if column not in ("query_seq", "gap_seq")
        ]
        self.result_tree.configure(columns=columns)
        for col in columns:
            self.result_tree.heading(col, text=col)
            self.result_tree.column(
                col,
                width=110,
                minwidth=70,
                stretch=True,
            )

        for row in rows:
            self.result_tree.insert(
                "",
                tk.END,
                values=[str(row.get(col, "")) for col in columns],
            )
        self.export_button.config(state=tk.NORMAL)

    def _populate_library_results(self, output_dir: str) -> None:
        path = os.path.join(output_dir, "library_scores.tsv")
        if not os.path.isfile(path):
            self._log_line(
                "Library scores not found: %s" % path
            )
            return
        try:
            with open(path, "r", encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle, delimiter="\t")
                rows = [dict(row) for row in reader]
        except Exception as exc:
            self._log_line(f"Failed to read library scores: {exc}")
            return

        self.last_result_rows = rows
        self.result_tree.delete(*self.result_tree.get_children())
        if not rows:
            self.export_button.config(state=tk.DISABLED)
            return

        columns = list(rows[0].keys())
        self.result_tree.configure(columns=columns)
        for col in columns:
            self.result_tree.heading(col, text=col)
            self.result_tree.column(
                col,
                width=110,
                minwidth=70,
                stretch=True,
            )
        for row in rows:
            self.result_tree.insert(
                "",
                tk.END,
                values=[str(row.get(col, "")) for col in columns],
            )
        self.export_button.config(state=tk.NORMAL)
        self._log_line("Loaded %d library candidate(s)" % len(rows))

    def _export_selected(self) -> None:
        selected = self.result_tree.selection()
        if not selected:
            return
        fmt = self.export_format_var.get()
        extension = ".tsv" if fmt in ("unique_guides", "library") else f".{fmt}"
        label = (
            self._value("result_label", "").strip()
            or self._default_run_label()
        )
        label = re.sub(r"[/\\]+", "-", label)
        label = re.sub(r"[^A-Za-z0-9._-]+", "_", label).strip("._-")
        base_name = {
            "csv": "candidates",
            "tsv": "candidates",
            "fasta": "candidates",
            "bed": "candidates",
            "xlsx": "candidates",
            "unique_guides": "unique_guides",
            "library": "library_input",
        }.get(fmt, "export")
        stamp = time.strftime("%Y%m%d_%H%M%S")
        path = filedialog.asksaveasfilename(
            parent=self.root,
            initialfile="%s_%s_%s%s" % (
                label, base_name, stamp, extension),
            defaultextension=extension,
            filetypes=[(fmt.upper(), f"*{extension}"), ("All files", "*.*")],
        )
        if not path:
            return

        columns = list(self.last_result_rows[0].keys())
        selected_ids = set(selected)
        rows = []
        for item_id in selected_ids:
            values = self.result_tree.item(item_id, "values")
            rows.append(dict(zip(columns, values)))

        written = export_selected(rows, path, fmt)
        self._log_line(f"Exported {written} selected candidate(s) to {path}")

    def _log_line(self, line: str) -> None:
        self.root.after(
            0,
            lambda: self._append_log(line),
        )

    def _append_log(self, line: str) -> None:
        self.log_text.insert(tk.END, line + "\n")
        self.log_text.see(tk.END)

    def _clear_log(self) -> None:
        self.log_text.delete("1.0", tk.END)

    def _on_close(self) -> None:
        runner = getattr(self, "current_runner", None)
        if runner is not None and getattr(self, "running", False):
            try:
                runner.stop()
            except Exception:
                pass
        self.log_writer.close()
        self.root.destroy()


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Target / BED Designer")
    parser.add_argument(
        "--bed",
        action="store_true",
        help="Open in BED regions input mode",
    )
    args = parser.parse_args()
    root = tk.Tk()
    PatternDesignerWorkbench(root, default_bed=args.bed)
    root.mainloop()


if __name__ == "__main__":
    main()
