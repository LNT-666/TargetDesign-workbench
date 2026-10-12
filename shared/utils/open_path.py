#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Reveal a file or directory with the desktop handler of the host platform.

``os.startfile`` exists only on Windows, and ``xdg-open`` only on the Linux and
BSD desktops, so a caller that hard-codes one of them works on the machine it
was written on and raises on the other two.  The mapping is written once here,
and ``tests/test_open_path.py`` fails if a raw launcher call comes back.
"""

from __future__ import annotations

import os
import subprocess
import sys


def platform_launcher(platform=None):
    """Return the launcher command for *platform*, or ``None`` for ``startfile``.

    ``None`` means the platform carries ``os.startfile`` and needs no external
    command.  The default is the running platform; passing one explicitly lets
    every branch be exercised from any host.
    """
    name = sys.platform if platform is None else platform
    if name == "win32":
        return None
    if name == "darwin":
        return "open"
    return "xdg-open"


def open_path(path, platform=None):
    """Reveal *path* with the desktop handler of *platform*.

    Returns ``True`` when a handler was started and ``False`` when the platform
    has no handler or the launcher could not be spawned, so a GUI callback can
    report the failure instead of dying with an unrelated exception.
    """
    target = os.fspath(path)
    launcher = platform_launcher(platform)
    try:
        if launcher is None:
            os.startfile(target)  # type: ignore[attr-defined]
        else:
            subprocess.Popen([launcher, target])
    except OSError:
        return False
    return True
