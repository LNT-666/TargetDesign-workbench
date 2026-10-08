#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Canonical filesystem locations for the toolkit.

Every run output is pinned to a single ``output`` directory next to the
program, and every downloaded genome / built genome index is pinned to a
sibling ``resource`` directory.  Keeping the destinations fixed means a job
can never be pointed at a directory the running account cannot write (the
webapp designer used to expose a free-form Output Directory and could fail
with PermissionError).
"""

from __future__ import annotations

import os


#: Program/repository root: the directory that holds ``unified_gui.py``.
PROGRAM_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

#: Name of the fixed run-output directory under :data:`PROGRAM_ROOT`.
OUTPUT_DIRNAME = "output"

#: Name of the fixed resource directory (downloads / indexes) under :data:`PROGRAM_ROOT`.
RESOURCE_DIRNAME = "resource"


def program_root() -> str:
    """Absolute path of the program/repository root."""
    return PROGRAM_ROOT


def default_output_dir() -> str:
    """Absolute path of the fixed run-output directory."""
    return os.path.join(PROGRAM_ROOT, OUTPUT_DIRNAME)


def ensure_default_output_dir() -> str:
    """Return :func:`default_output_dir`, creating it when missing."""
    path = default_output_dir()
    os.makedirs(path, exist_ok=True)
    return path


def default_resource_dir() -> str:
    """Absolute path of the fixed resource directory (downloads / indexes)."""
    return os.path.join(PROGRAM_ROOT, RESOURCE_DIRNAME)


def ensure_default_resource_dir() -> str:
    """Return :func:`default_resource_dir`, creating it when missing."""
    path = default_resource_dir()
    os.makedirs(path, exist_ok=True)
    return path
