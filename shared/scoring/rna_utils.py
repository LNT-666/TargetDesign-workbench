#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ViennaRNA wrappers and deterministic RNA fallbacks for Phase 4.

The wrappers accept either the ViennaRNA Python bindings (import RNA) or the
command-line tools (RNAfold, RNAplfold, RNAduplex, RNAcofold). When neither is
present every function returns None so callers can fall back to deterministic
heuristics without crashing.
"""

import os
import re
import shutil
import subprocess
import tempfile


CAS13_DR = {
    "cas13": {
        "seq": "GATTTAGACTACCCCAAAAACGAAGGGGACTAAAAC",
        "source": "Cas13 default direct repeat (LwaCas13a); CHOPCHOP Cas13 rules",
    },
}


def vienna_available():
    """Return (ok, mode) where mode is python-bindings or command-line."""
    try:
        import RNA  # noqa: F401
        return True, "python-bindings"
    except ImportError:
        pass
    for tool in ("RNAfold", "RNAplfold", "RNAduplex", "RNAcofold"):
        if shutil.which(tool):
            return True, "command-line"
    return False, "ViennaRNA is not installed"


def _run_vienna(tool, args, input_text=None, cwd=None, timeout=60):
    exe = shutil.which(tool)
    if exe is None:
        return None
    try:
        result = subprocess.run(
            [exe] + args, input=input_text, capture_output=True,
            text=True, timeout=timeout, cwd=cwd)
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def _rnafold_output(seq):
    text = _run_vienna("RNAfold", ["--noPS"], input_text=seq + "\n")
    if not text:
        return None
    lines = text.strip().splitlines()
    if not lines:
        return None
    return "\n".join(lines[1:]) if len(lines) > 1 else lines[0]


def rnafold_mfe(seq):
    """Minimum free energy in kcal/mol, or None when ViennaRNA is absent."""
    out = _rnafold_output(seq)
    if not out:
        return None
    match = re.search(r"\(\s*([-+]?\d+\.\d+)\s*\)\s*$", out)
    if not match:
        return None
    return float(match.group(1))


def rnafold_structure(seq):
    """Dot-bracket MFE structure, or None when ViennaRNA is absent."""
    out = _rnafold_output(seq)
    if not out:
        return None
    for line in out.splitlines():
        parts = line.split()
        if parts and parts[0] and all(char in ".()" for char in parts[0]):
            return parts[0]
    return None


def rnaplfold_unpaired(seq, window=80, max_pair_distance=40, unpaired=1):
    """Per-position unpaired probabilities from RNAplfold, or None."""
    if len(seq) < 2:
        return None
    with tempfile.TemporaryDirectory() as tmp:
        text = _run_vienna(
            "RNAplfold",
            ["-W", str(window), "-L", str(max_pair_distance),
             "-u", str(unpaired)],
            input_text=seq + "\n", cwd=tmp)
        if text is None:
            return None
        path = os.path.join(tmp, "plfold_lunp")
        if not os.path.isfile(path):
            return None
        probs = []
        with open(path, "r", encoding="utf-8") as handle:
            for line in handle:
                parts = line.split()
                if len(parts) >= 3:
                    try:
                        probs.append(float(parts[2]))
                    except ValueError:
                        continue
        return probs or None


def rna_duplex_mfe(seq_a, seq_b):
    """Duplex MFE between two separate RNA strands, or None."""
    text = _run_vienna(
        "RNAduplex", [], input_text=seq_a + "\n" + seq_b + "\n")
    if not text:
        return None
    for line in text.splitlines():
        match = re.match(r"^\s*([-+]?\d+\.\d+)", line)
        if match:
            return float(match.group(1))
    return None


def rna_cofold_mfe(seq_a, seq_b):
    """Cofold MFE for two RNA strands, or None."""
    text = _run_vienna(
        "RNAcofold", ["--noPS"], input_text=seq_a + "&" + seq_b + "\n")
    if not text:
        return None
    match = re.search(r"\(\s*([-+]?\d+\.\d+)\s*\)\s*$", text.strip())
    if not match:
        return None
    return float(match.group(1))


def structure_accessibility(seq, start=0, end=None):
    """Fraction of unpaired bases in a window of the MFE structure."""
    structure = rnafold_structure(seq)
    if structure is None:
        return None
    end = len(structure) if end is None else min(len(structure), end)
    start = max(0, start)
    if end <= start:
        return None
    window = structure[start:end]
    return window.count(".") / len(window)


def sequence_accessibility(seq, start=0, end=None):
    """Ensemble unpaired probability when available, else MFE proxy."""
    probs = rnaplfold_unpaired(seq)
    if probs is not None:
        end = len(probs) if end is None else min(len(probs), end)
        start = max(0, start)
        if end > start:
            return sum(probs[start:end]) / (end - start)
    return structure_accessibility(seq, start, end)


def max_inverted_repeat_len(seq):
    """Longest local reverse-complement match; cheap hairpin proxy."""
    seq = (seq or "").upper().replace("T", "U")
    comp = {"A": "U", "U": "A", "C": "G", "G": "C"}
    best = 0
    n = len(seq)
    for i in range(n):
        for j in range(i + 1, n):
            length = 0
            while (i + length < n and j - length >= 0 and
                   comp.get(seq[i + length]) == seq[j - length]):
                length += 1
            best = max(best, length)
    return best
