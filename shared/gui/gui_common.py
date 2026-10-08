#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared Tkinter building blocks for the CRISPR toolkit GUI.

The main window owns a JSON-backed workspace with common paths and analysis
parameters. The three motif GUIs inherit CommonGUIMixin so they can load and
save the same workspace without duplicating file dialogs or command runners.
"""

import json
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

from utils.log_utils import parse_progress_line


WORKSPACE_FILENAME = "workspace.json"


class Workspace:
    """Small JSON-backed key/value store shared by all GUI windows."""

    def __init__(self, root_dir=None, path=None):
        self.root_dir = root_dir or os.getcwd()
        self.path = path or os.path.join(self.root_dir, WORKSPACE_FILENAME)
        self.data = {}
        self.load()

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value

    def update(self, mapping):
        if mapping:
            self.data.update(mapping)

    def values(self):
        return dict(self.data)

    def load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                loaded = json.load(handle)
            if isinstance(loaded, dict):
                self.data = loaded
        except (OSError, ValueError):
            self.data = {}
        return self.data

    def save(self):
        directory = os.path.dirname(os.path.abspath(self.path))
        try:
            os.makedirs(directory, exist_ok=True)
            with open(self.path, "w", encoding="utf-8", newline="") as handle:
                json.dump(self.data, handle, indent=2, ensure_ascii=False)
            return True
        except OSError:
            return False


class CommonGUIMixin:
    """Shared behaviors for MainApp and the three motif GUIs."""

    def init_common(self, root, workspace_dir=None, workspace_path=None):
        self.root = root
        self.workspace_dir = workspace_dir or os.getcwd()
        self.workspace_path = workspace_path or os.path.join(
            self.workspace_dir, WORKSPACE_FILENAME)
        self._ui_queue = queue.Queue()
        self.workspace = Workspace(self.workspace_dir, self.workspace_path)
        if not hasattr(self, "process"):
            self.process = None
        if not hasattr(self, "progress_var"):
            self.progress_var = tk.DoubleVar(value=0)
        if not hasattr(self, "progress_label"):
            self.progress_label = tk.StringVar(value="")
        if not hasattr(self, "status_var"):
            self.status_var = tk.StringVar(value="")
        if not hasattr(self, "output_summary"):
            self.output_summary = tk.StringVar(value="")
        self.root.after(50, self._poll_ui_queue)
        return self.workspace

    def run_on_ui(self, func, *args, **kwargs):
        """Run a callback on the Tk main thread from any worker thread."""
        self._ui_queue.put((func, args, kwargs))

    def _poll_ui_queue(self):
        try:
            while True:
                func, args, kwargs = self._ui_queue.get_nowait()
                try:
                    func(*args, **kwargs)
                except Exception:
                    pass
        except queue.Empty:
            pass
        try:
            if self.root.winfo_exists():
                self.root.after(50, self._poll_ui_queue)
        except Exception:
            pass

    def workspace_file(self):
        return self.workspace_path

    def setup_workspace_menu(self, workspace_mapping=None):
        """Add a Workspace menu that loads/saves the shared JSON file."""
        self._workspace_mapping = dict(workspace_mapping or {})
        menubar = tk.Menu(self.root)
        workspace_menu = tk.Menu(menubar, tearoff=0)
        workspace_menu.add_command(
            label="Load Workspace", command=self._load_workspace_fields)
        workspace_menu.add_command(
            label="Save Workspace", command=self._save_workspace_fields)
        menubar.add_cascade(label="Workspace", menu=workspace_menu)
        self.root.config(menu=menubar)

    def _load_workspace_fields(self):
        self.workspace.load()
        self.apply_workspace(self._workspace_map())
        message = "Workspace loaded: %s" % self.workspace.path
        if hasattr(self, "log"):
            self.log(message)

    def _save_workspace_fields(self):
        self.workspace.update(self.collect_workspace(self._workspace_map()))
        ok = self.workspace.save()
        if hasattr(self, "log"):
            self.log("Workspace saved: %s" % self.workspace.path)
        return ok

    def _workspace_map(self):
        mapping = getattr(self, "_workspace_mapping", {})
        if callable(mapping):
            mapping = mapping()
        return dict(mapping or {})

    def apply_workspace(self, mapping):
        """Fill Entry widgets or tk variables from workspace values."""
        for attr, key in mapping.items():
            value = self.workspace.get(key)
            if value is None or value == "":
                continue
            target = getattr(self, attr, None)
            if target is None:
                continue
            try:
                target.delete(0, tk.END)
                target.insert(0, str(value))
            except AttributeError:
                try:
                    target.set(str(value))
                except Exception:
                    pass

    def collect_workspace(self, mapping):
        """Collect Entry/Variable values into a workspace dict."""
        collected = {}
        for attr, key in mapping.items():
            target = getattr(self, attr, None)
            if target is None:
                continue
            try:
                value = target.get()
            except Exception:
                continue
            if value is None or value == "":
                continue
            collected[key] = value
        return collected

    # ---------- File dialogs ----------
    def browse_file(self, entry, filetypes=None):
        if filetypes is None:
            filetypes = [("All files", "*.*")]
        path = filedialog.askopenfilename(filetypes=filetypes)
        if path:
            entry.delete(0, tk.END)
            entry.insert(0, path)

    def browse_directory(self, entry):
        path = filedialog.askdirectory()
        if path:
            entry.delete(0, tk.END)
            entry.insert(0, path)

    def browse_save_file(self, entry, ext=""):
        filetypes = [("Files", "*" + ext), ("All files", "*.*")] if ext \
            else [("All files", "*.*")]
        path = filedialog.asksaveasfilename(
            defaultextension=ext, filetypes=filetypes)
        if path:
            entry.delete(0, tk.END)
            entry.insert(0, path)

    def browse_index(self, entry):
        path = filedialog.askopenfilename(
            filetypes=[("Genome index", "*.ggi *.json"),
                       ("All files", "*.*")])
        if not path:
            return
        base, ext = os.path.splitext(path)
        value = base if ext in (".ggi", ".json") else path
        entry.delete(0, tk.END)
        entry.insert(0, value)

    def browse_blastdb(self, entry):
        path = filedialog.askopenfilename(
            filetypes=[("BLAST db", "*.nin *.nsq *.nhr *.nal *.nog"),
                       ("All files", "*.*")])
        if not path:
            return
        base, ext = os.path.splitext(path)
        value = base if ext in (".nin", ".nsq", ".nhr", ".nal", ".nog") \
            else path
        entry.delete(0, tk.END)
        entry.insert(0, value)

    # ---------- Logging and command runner ----------
    def log(self, message):
        if not hasattr(self, "log_text") or self.log_text is None:
            return
        root = getattr(self, "root", None)
        if root is not None:
            try:
                self.run_on_ui(self._log_now, str(message))
                return
            except Exception:
                pass
        self._log_now(str(message))

    def _log_now(self, message):
        if not hasattr(self, "log_text") or self.log_text is None:
            return
        self.log_text.insert(tk.END, str(message) + "\n")
        self.log_text.see(tk.END)

    def clear_log(self):
        if hasattr(self, "log_text") and self.log_text is not None:
            self.log_text.delete("1.0", tk.END)

    def open_log(self):
        path = getattr(self, "log_path", None)
        if path and os.path.isfile(path):
            os.startfile(path)  # noqa

    def run_command(self, cmd, description, on_finish=None):
        """Run a command in a background thread and stream output to the log."""
        self.set_busy(True)
        self.progress_var.set(0)
        self.progress_label.set(description + " ...")
        thread = threading.Thread(
            target=self._run_process, args=(cmd, description, on_finish),
            daemon=True)
        thread.start()

    def _run_process(self, cmd, description, on_finish):
        root = getattr(self, "root", None)
        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1, encoding="utf-8", errors="replace")
        except Exception as exc:
            if root is not None:
                try:
                    self.run_on_ui(self.log, "Launch failed: %s" % exc)
                    self.run_on_ui(self.set_busy, False)
                except Exception:
                    pass
            return
        for line in proc.stdout:
            line = line.rstrip("\n")
            if root is not None:
                try:
                    self.run_on_ui(self.log, line)
                except Exception:
                    pass
            parsed = parse_progress_line(line)
            if parsed is not None and root is not None:
                value, label = parsed
                self.run_on_ui(
                    self._set_progress_now, value,
                    "%s %d%%" % (label, value))
        proc.wait()
        code = proc.returncode
        if root is not None:
            try:
                self.run_on_ui(self._finish_run, code, on_finish)
            except Exception:
                pass

    def _set_progress_now(self, value, label):
        self.progress_var.set(value)
        self.progress_label.set(label)

    def _finish_run(self, code, on_finish):
        self.progress_var.set(100 if code == 0 else 0)
        self.progress_label.set("Complete" if code == 0 else "Failed")
        self.set_busy(False)
        if code == 0 and on_finish:
            on_finish()

    def set_busy(self, busy):
        if hasattr(self, "buttons"):
            for button in self.buttons:
                try:
                    button.config(state=tk.DISABLED if busy else tk.NORMAL)
                except Exception:
                    pass

    def disable_buttons(self):
        self.set_busy(True)

    def enable_buttons(self):
        self.set_busy(False)

    # ---------- Result helpers ----------
    def open_output(self):
        output = getattr(self, "entry_output", None)
        if output is None:
            return
        path = output.get().strip()
        if path and os.path.isdir(path):
            os.startfile(path)  # noqa
        else:
            messagebox.showinfo("Output", "Output directory is not ready")

    def refresh_output(self):
        if not hasattr(self, "entry_output"):
            return
        output = self.entry_output.get().strip()
        if hasattr(self, "file_list") and self.file_list is not None:
            self.file_list.delete(0, tk.END)
            if not output or not os.path.isdir(output):
                return
            for name in sorted(os.listdir(output)):
                path = os.path.join(output, name)
                if os.path.isfile(path) and name.endswith(
                        (".tsv", ".bed", ".json", ".log", ".xlsx")):
                    self.file_list.insert(tk.END, name)
