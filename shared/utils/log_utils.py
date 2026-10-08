#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Shared file logging helper for the GUI tools."""

import os
import subprocess
import sys
import threading
import traceback
from datetime import datetime


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LOG_DIR = os.path.join(PROJECT_ROOT, "logs")


class LogWriter:
    """Write timestamped log lines to a per-session file."""

    def __init__(self, tool_name="program"):
        self.tool_name = tool_name
        self._lock = threading.Lock()
        os.makedirs(LOG_DIR, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.path = os.path.join(LOG_DIR, f"{tool_name}_{timestamp}.log")
        self._file = open(self.path, "a", encoding="utf-8")
        self.write("=== Log session started ===")
        self.write(f"Python: {sys.version}")
        self.write(f"Platform: {sys.platform}")
        self.write(f"Script: {os.path.abspath(sys.argv[0]) if sys.argv else ''}")

    def write(self, message):
        line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}"
        with self._lock:
            try:
                self._file.write(line + "\n")
                self._file.flush()
            except Exception:
                pass

    def exception(self):
        with self._lock:
            try:
                self._file.write(traceback.format_exc() + "\n")
                self._file.flush()
            except Exception:
                pass

    def close(self):
        self.write("=== Log session closed ===")
        with self._lock:
            try:
                self._file.close()
            except Exception:
                pass


def open_log_dir():
    try:
        if sys.platform == "win32":
            os.startfile(LOG_DIR)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", LOG_DIR])
        else:
            subprocess.Popen(["xdg-open", LOG_DIR])
    except Exception as e:
        print(f"Could not open log directory: {e}")


def install_excepthook(writer):
    def _hook(exc_type, exc_value, exc_tb):
        writer.write("Uncaught exception:")
        writer.write("".join(traceback.format_exception(exc_type, exc_value, exc_tb)).rstrip())

    sys.excepthook = _hook


def parse_progress_line(line):
    """Parse a ``PROGRESS: <label...> <percent>`` log line.

    Returns ``(percent, label)`` where the trailing integer is the percent
    and every word between ``PROGRESS:`` and it is the label, or ``None``
    when the line is not a well-formed progress line.
    """
    text = (line or "").strip()
    if not text.startswith("PROGRESS:"):
        return None
    parts = text.split()
    if len(parts) < 3:
        return None
    try:
        percent = int(parts[-1])
    except ValueError:
        return None
    label = " ".join(parts[1:-1]) or parts[1]
    return percent, label
