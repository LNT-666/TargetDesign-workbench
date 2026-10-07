#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Derive the dependency inventory from the imports and diff it against the
requirement files.

The requirement files say what a user installs; the import graph says what the
code needs. This tool computes the second one statically (nothing is executed
or imported, so it runs without any dependency being installed) and reports the
drift:

    MISSING          the code imports a third-party package that no requirement
                     file declares. For a *hard* import (module level, outside
                     ``try:``) that breaks startup, so ``--check`` fails on it.
    UNTRACKED LOCAL  a module of this program that exists on disk but is not
                     tracked by git. A clone - and therefore a container build
                     or a release stage - does not have it, so the import fails
                     there even though it works locally. ``--check`` fails on
                     this too: it is how a missing ``shared/output`` package
                     broke the container smoke test.
    UNUSED           a requirement file declares a package that no shipped code
                     imports. Reported in two buckets so nobody deletes
                     something the offline paper workflow still needs.

Import kinds:

    hard      module level, outside ``try:`` -> must be installed, or the
              module cannot be imported at all
    guarded   inside ``try:`` at module level -> optional, the code handles
              ``ImportError`` itself
    lazy      inside a function -> optional, needed only for that feature

Usage::

    python tools/dep_scan.py                      # inventory + drift report
    python tools/dep_scan.py --check              # exit 1 on MISSING/UNTRACKED LOCAL
    python tools/dep_scan.py --json dep.json      # machine readable copy
    python tools/dep_scan.py --include-untracked  # also scan uncommitted files

File paths come from git, so the scan covers exactly what a clone or a
container build sees; file *contents* are read from the working tree, so a local
run also reports an import of a file that is not committed yet.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import subprocess
import sys
from typing import Dict, List, Set, Tuple


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: Import name -> distribution name, for the few that differ.
ALIASES = {
    "bio": "biopython",
    "rna": "viennarna",
    "sklearn": "scikit-learn",
    "yaml": "pyyaml",
    "pil": "pillow",
    "cv2": "opencv-python",
    "keras": "tensorflow",
}

#: Requirement files, in report order.
REQUIREMENTS = (
    "requirements.txt",
    "requirements-linux.txt",
    "requirements-windows.txt",
)

#: Entry points: their import closure defines "what the program needs".
ENTRY_FILES = ("webapp/app.py", "main.py", "designer_workbench.py", "unified_gui.py")
ENTRY_DIRS = ("basic", "tools", "Target_xbp_Target", "Target_xbp_Y_zbp_Target")

#: Declared for the offline paper workflow, which lives outside the published
#: tree, so the scan cannot see its imports.
OFFLINE_ONLY = {
    "matplotlib": "figure scripts under docs/figures (not published)",
    "scikit-learn": "one-off Azimuth conversion, see docs/ENVIRONMENT.md",
    "scipy": "offline analysis helpers",
    "tensorboardx": "training logs of the offline model conversions",
    "pybdm": "upstream crispAI script (external_tools/, not published)",
    "genomepy": "upstream crispAI script downloads GRCh38 on first run",
    "jax": "upstream crispAI script",
    "numpyro": "upstream crispAI script",
    "tqdm": "upstream crispAI script",
    "seaborn": "upstream crispAI script",
}

STD_TOP: Set[str] = set(sys.stdlib_module_names) | {"__future__"}


def normalise(name: str) -> str:
    """Map an import or requirement name to a comparable distribution name."""
    name = name.strip().lower()
    for sep in ("[", "=", ">", "<", "!", ";", " "):
        if sep in name:
            name = name.split(sep, 1)[0]
    name = name.replace("_", "-")
    return ALIASES.get(name, name)


def dist_name(module: str) -> str:
    """Top level distribution behind a dotted import path."""
    return normalise(module.split(".")[0])


def git(*args: str) -> str:
    return subprocess.run(("git",) + args, cwd=ROOT, capture_output=True,
                          check=True).stdout.decode("utf-8", "replace")


def _expand(path: str, found: List[str]) -> None:
    if path.endswith(".py") and os.path.isfile(os.path.join(ROOT, path)):
        found.append(path)
    elif os.path.isdir(os.path.join(ROOT, path)):
        for dirpath, dirnames, filenames in os.walk(os.path.join(ROOT, path)):
            dirnames[:] = [d for d in dirnames if d != "__pycache__"]
            found += [os.path.relpath(os.path.join(dirpath, f), ROOT).replace(os.sep, "/")
                      for f in filenames if f.endswith(".py")]


def file_sets() -> Tuple[List[str], List[str]]:
    """(tracked, untracked) .py files, as git sees them."""
    tracked = [p.replace(os.sep, "/") for p in git("ls-files", "-z", "*.py").split("\0") if p]
    untracked: List[str] = []
    for line in git("status", "--porcelain").splitlines():
        if line.startswith("??"):
            _expand(line[3:].strip().replace("\\", "/"), untracked)
    return sorted(set(tracked)), sorted(set(untracked) - set(tracked))


def module_map(files) -> Dict[str, str]:
    """`dotted.module` -> path, using every source root the program uses.

    ``shared/`` and ``webapp/`` are sys.path roots without being packages, and a
    few scripts import a sibling by bare name, so every directory that holds a
    .py file counts as a root.
    """
    files = list(files)
    roots = [""] + sorted({os.path.dirname(f) for f in files}, key=len, reverse=True)
    roots += sorted({f.split("/")[0] for f in files if "/" in f})
    mapping: Dict[str, str] = {}
    for path in files:
        for root in roots:
            if root and not path.startswith(root + "/"):
                continue
            rel = path[len(root) + 1:] if root else path
            if rel.endswith("/__init__.py"):
                mapping.setdefault(rel[:-12].replace("/", "."), path)
            elif rel.endswith(".py"):
                mapping.setdefault(rel[:-3].replace("/", "."), path)
    return mapping


class ImportScanner(ast.NodeVisitor):
    """Collect (kind, module) for every import of one file."""

    def __init__(self) -> None:
        self.found: List[Tuple[str, str]] = []
        self._depth = 0

    def visit_Try(self, node: ast.Try) -> None:
        for child in node.body:
            if isinstance(child, (ast.Import, ast.ImportFrom)):
                self._collect(child, "guarded")
            else:
                self.visit(child)
        for child in list(node.handlers) + list(node.orelse) + list(node.finalbody):
            self.visit(child)

    def visit_Import(self, node: ast.Import) -> None:
        self._collect(node, "lazy" if self._depth else "hard")

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.level == 0:
            self._collect(node, "lazy" if self._depth else "hard")

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._depth += 1
        self.generic_visit(node)
        self._depth -= 1

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._depth += 1
        self.generic_visit(node)
        self._depth -= 1

    def _collect(self, node, kind: str) -> None:
        if isinstance(node, ast.Import):
            mods = [alias.name for alias in node.names]
        else:
            mods = [node.module or ""]
        for mod in mods:
            if mod and mod.split(".")[0] not in STD_TOP:
                self.found.append((kind, mod))


def scan(files) -> Dict[str, List[Tuple[str, str]]]:
    graph: Dict[str, List[Tuple[str, str]]] = {}
    for path in files:
        try:
            with open(os.path.join(ROOT, path), encoding="utf-8", errors="replace") as handle:
                tree = ast.parse(handle.read())
        except (SyntaxError, UnicodeDecodeError):
            graph[path] = []
            continue
        scanner = ImportScanner()
        scanner.visit(tree)
        graph[path] = scanner.found
    return graph


def read_requirements(path: str) -> Set[str]:
    """Distribution names declared in one requirement file."""
    declared: Set[str] = set()
    full = os.path.join(ROOT, path)
    if not os.path.isfile(full):
        return declared
    with open(full, encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if line and not line.startswith("#") and not line.startswith("-"):
                declared.add(normalise(line))
    return declared


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true",
                        help="exit 1 on a missing hard import or an untracked local module")
    parser.add_argument("--json", metavar="PATH", help="also write the result as JSON")
    parser.add_argument("--include-untracked", action="store_true",
                        help="also scan the imports of uncommitted files")
    args = parser.parse_args()

    tracked, untracked = file_sets()
    scanned = tracked + untracked if args.include_untracked else tracked
    local = module_map(tracked)
    local_any = module_map(tracked + untracked)
    graph = scan(scanned)

    entries = [f for f in ENTRY_FILES if f in graph]
    entries += [f for f in scanned if f.split("/")[0] in ENTRY_DIRS and f.endswith(".py")]
    declared = {name: read_requirements(name) for name in REQUIREMENTS}

    per_entry: Dict[str, Dict[str, List[str]]] = {}
    hard: Set[str] = set()
    optional: Set[str] = set()
    untracked_used: Dict[str, Set[str]] = {}
    for entry in sorted(set(entries)):
        # files needed at startup: hard imports only
        req, stack = {entry}, [entry]
        while stack:
            for kind, mod in graph.get(stack.pop(), []):
                target = local.get(mod)
                if kind == "hard" and target and target not in req:
                    req.add(target)
                    stack.append(target)
        # files reachable only through an optional edge; their hard imports are
        # optional too, because the module is never imported at startup
        opt_files, stack = set(), []
        for path in sorted(req):
            for kind, mod in graph.get(path, []):
                target = local.get(mod)
                if kind != "hard" and target and target not in req:
                    opt_files.add(target)
                    stack.append(target)
        while stack:
            for kind, mod in graph.get(stack.pop(), []):
                target = local.get(mod)
                if target and target not in req and target not in opt_files:
                    opt_files.add(target)
                    stack.append(target)
        entry_hard, entry_optional = set(), set()
        for path in sorted(req | opt_files):
            required_file = path in req
            for kind, mod in graph.get(path, []):
                if local.get(mod):
                    continue
                if local_any.get(mod):
                    untracked_used.setdefault(local_any[mod], set()).add(path)
                    continue
                name = dist_name(mod)
                if kind == "hard" and required_file:
                    entry_hard.add(name)
                else:
                    entry_optional.add(name)
        per_entry[entry] = {"hard": sorted(entry_hard),
                            "optional": sorted(entry_optional - entry_hard)}
        hard |= entry_hard
        optional |= entry_optional - entry_hard

    declared_any = set().union(*declared.values()) if declared else set()
    missing = sorted(n for n in hard if n not in declared_any)
    unused = sorted(n for n in declared_any if n not in hard and n not in optional)

    print("== per entry point ==")
    for entry in sorted(per_entry):
        info = per_entry[entry]
        print("%-44s hard: %s" % (entry, ", ".join(info["hard"]) or "-"))
        if info["optional"]:
            print("%-44s opt : %s" % ("", ", ".join(info["optional"])))
    print()
    print("== what this program imports ==")
    print("hard, must be installed     : %s" % (", ".join(sorted(hard)) or "-"))
    print("optional, feature dependent : %s" % (", ".join(sorted(optional)) or "-"))
    print()
    print("== drift against the requirement files ==")
    print("MISSING (imported, undeclared)     : %s" % (", ".join(missing) or "none"))
    if untracked_used:
        for path in sorted(untracked_used):
            print("UNTRACKED LOCAL MODULE             : %s (imported by %s)"
                  % (path, ", ".join(sorted(untracked_used[path]))))
    else:
        print("UNTRACKED LOCAL MODULE             : none")
    offline = [n for n in unused if n in OFFLINE_ONLY]
    print("UNUSED, offline workflow only      : %s" % (", ".join(offline) or "none"))
    for name in offline:
        print("    %-14s %s" % (name, OFFLINE_ONLY[name]))
    print("UNUSED, nothing in this repo uses  : %s"
          % (", ".join(n for n in unused if n not in OFFLINE_ONLY) or "none"))

    if args.json:
        with open(args.json, "w", encoding="utf-8") as handle:
            json.dump({"per_entry": per_entry, "hard": sorted(hard), "optional": sorted(optional),
                       "declared": declared, "missing": missing,
                       "untracked_local": {k: sorted(v) for k, v in untracked_used.items()},
                       "unused": unused, "files_scanned": len(scanned)},
                      handle, indent=2, sort_keys=True)

    if args.check and (missing or untracked_used):
        if missing:
            print("\nFAIL: undeclared hard import(s): %s" % ", ".join(missing), file=sys.stderr)
        if untracked_used:
            print("FAIL: source file(s) not tracked by git: %s"
                  % ", ".join(sorted(untracked_used)), file=sys.stderr)
        return 1
    if args.check:
        print("\nOK: every hard import is declared and every module of this program is tracked")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())