#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Portable physical-memory detection and Auto memory-limit resolution."""

from __future__ import annotations

import ctypes
import json
import os
import subprocess
from typing import Dict, Optional


MIB = 1024 * 1024
AUTO_TOTAL_FRACTION = 0.50
AUTO_AVAILABLE_FRACTION = 0.75


def _windows_memory_status() -> Optional[Dict[str, int]]:
    if os.name != "nt":
        return None

    class MemoryStatusEx(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    status = MemoryStatusEx()
    status.dwLength = ctypes.sizeof(MemoryStatusEx)
    try:
        ok = ctypes.windll.kernel32.GlobalMemoryStatusEx(
            ctypes.byref(status))
    except (AttributeError, OSError):
        return None
    if not ok:
        return None
    return {
        "total_mb": int(status.ullTotalPhys // MIB),
        "available_mb": int(status.ullAvailPhys // MIB),
    }


def _proc_meminfo() -> Optional[Dict[str, int]]:
    try:
        values = {}
        with open("/proc/meminfo", "r", encoding="ascii") as handle:
            for line in handle:
                key, _, remainder = line.partition(":")
                if key in ("MemTotal", "MemAvailable"):
                    values[key] = int(remainder.split()[0]) // 1024
        if "MemTotal" in values:
            return {
                "total_mb": values["MemTotal"],
                "available_mb": values.get("MemAvailable", 0),
            }
    except (OSError, ValueError, IndexError):
        pass
    return None


def _sysconf_memory() -> Optional[Dict[str, int]]:
    try:
        page_size = int(os.sysconf("SC_PAGE_SIZE"))
        total_pages = int(os.sysconf("SC_PHYS_PAGES"))
        available_pages = int(os.sysconf("SC_AVPHYS_PAGES"))
    except (AttributeError, OSError, TypeError, ValueError):
        return None
    if page_size <= 0 or total_pages <= 0:
        return None
    total_mb = page_size * total_pages // MIB
    available_mb = (
        page_size * available_pages // MIB
        if available_pages > 0 else 0
    )
    return {"total_mb": total_mb, "available_mb": available_mb}


def memory_snapshot() -> Dict[str, int]:
    """Return total/available physical memory in MiB for this host."""
    for detector in (_windows_memory_status, _proc_meminfo, _sysconf_memory):
        snapshot = detector()
        if snapshot is not None:
            return snapshot
    return {"total_mb": 0, "available_mb": 0}


def total_physical_mb() -> int:
    """Return total physical memory in MiB, or 0 when detection fails."""
    return int(memory_snapshot().get("total_mb") or 0)


def available_memory_mb() -> int:
    """Return currently available physical memory in MiB, or 0 if unknown."""
    return int(memory_snapshot().get("available_mb") or 0)


def resolve_auto_limit_mb(total_mb, available_mb) -> int:
    """Resolve Auto as min(50% total, 75% currently available)."""
    try:
        total = max(0, int(total_mb or 0))
        available = max(0, int(available_mb or 0))
    except (TypeError, ValueError):
        return 0
    if total == 0 or available == 0:
        return 0
    total_share = int(total * AUTO_TOTAL_FRACTION)
    available_share = int(available * AUTO_AVAILABLE_FRACTION)
    return max(0, min(total_share, available_share))


def format_memory_mb(value) -> str:
    """Format MiB as a compact human-readable MiB/GiB string."""
    try:
        amount = max(0, int(round(float(value or 0))))
    except (TypeError, ValueError):
        amount = 0
    if amount >= 1024:
        return "%.1f GiB" % (amount / 1024.0)
    return "%d MiB" % amount


def resolve_remote_memory(host: str) -> Dict[str, int]:
    """Query total/available memory on an SSH execution host.

    The helper intentionally uses non-interactive SSH. If key-based access is
    unavailable, it returns zeroes so callers can require an explicit custom
    limit instead of silently using the GUI host's memory.
    """
    host = str(host or "").strip()
    if not host:
        return {"total_mb": 0, "available_mb": 0}
    script = (
        "import json,os;"
        "total=avail=0;"
        "f=open('/proc/meminfo');"
        "values={line.split(':',1)[0]:line.split(':',1)[1] "
        "for line in f if ':' in line};"
        "f.close();"
        "total=int(values.get('MemTotal','0 kB').split()[0])//1024;"
        "avail=int(values.get('MemAvailable','0 kB').split()[0])//1024;"
        "print(json.dumps({'total_mb':total,'available_mb':avail}))"
    )
    remote_python = os.environ.get("PROGRAMFILE_REMOTE_PYTHON") or "python3"
    try:
        result = subprocess.run(
            [
                "ssh",
                "-o", "BatchMode=yes",
                "-o", "ConnectTimeout=10",
                host,
                remote_python,
                "-c",
                script,
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return {"total_mb": 0, "available_mb": 0}
    if result.returncode != 0:
        return {"total_mb": 0, "available_mb": 0}
    try:
        data = json.loads(result.stdout.strip())
    except (TypeError, ValueError):
        return {"total_mb": 0, "available_mb": 0}
    return {
        "total_mb": max(0, int(data.get("total_mb") or 0)),
        "available_mb": max(0, int(data.get("available_mb") or 0)),
    }
