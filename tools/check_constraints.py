#!/usr/bin/env python3
"""Check that the tested Linux constraint snapshots cover the declared deps."""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Dict, List


ROOT = Path(__file__).resolve().parents[1]
REQUIREMENT_FILES = (
    "requirements.txt",
    "requirements-models-linux.txt",
    "requirements-crispai.txt",
)
CONSTRAINT_FILES = (
    "requirements/constraints-linux-cpu.txt",
    "requirements/constraints-linux-cuda.txt",
)
PIN_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)\s*==\s*([^\s;#]+)\s*$")
REQ_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)")


def canonical(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def requirement_names(root: Path) -> set[str]:
    names: set[str] = set()
    for relative in REQUIREMENT_FILES:
        path = root / relative
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.split("#", 1)[0].strip()
            if not line or line.startswith(("-r ", "--")):
                continue
            match = REQ_RE.match(line)
            if match:
                names.add(canonical(match.group(1)))
    return names


def constraint_pins(path: Path, errors: List[str]) -> Dict[str, str]:
    pins: Dict[str, str] = {}
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        match = PIN_RE.fullmatch(line)
        if not match:
            errors.append(f"{path}:{number}: constraint is not an exact == pin: {line}")
            continue
        name, version = canonical(match.group(1)), match.group(2)
        old = pins.get(name)
        if old is not None and old != version:
            errors.append(
                f"{path}:{number}: conflicting pins for {name}: {old} and {version}")
        pins[name] = version
    return pins


def check_repository(root: Path = ROOT) -> List[str]:
    errors: List[str] = []
    required = requirement_names(root)
    all_pins: Dict[str, Dict[str, str]] = {}

    for relative in CONSTRAINT_FILES:
        path = root / relative
        if not path.is_file():
            errors.append(f"missing constraint snapshot: {relative}")
            continue
        pins = constraint_pins(path, errors)
        all_pins[relative] = pins
        missing = sorted(required - set(pins))
        if missing:
            errors.append(f"{relative}: missing pins for: {', '.join(missing)}")
        text = path.read_text(encoding="utf-8")
        for marker in ("# Generated:", "# Environment:", "# Validation:"):
            if marker not in text:
                errors.append(f"{relative}: missing provenance marker {marker!r}")

    cpu = all_pins.get(CONSTRAINT_FILES[0], {})
    if cpu.get("torch") != "2.10.0+cpu":
        errors.append("CPU snapshot must pin torch==2.10.0+cpu")

    cuda = all_pins.get(CONSTRAINT_FILES[1], {})
    if cuda.get("torch") != "2.10.0":
        errors.append("CUDA snapshot must pin torch==2.10.0")
    if cuda.get("tensorflow") != "2.20.0":
        errors.append("CUDA snapshot must pin tensorflow==2.20.0")
    if "nvidia-nccl-cu12" not in cuda:
        errors.append("CUDA snapshot must pin the NCCL distribution")

    crispai = (root / "requirements-crispai.txt").read_text(encoding="utf-8")
    if "setuptools<81" not in crispai:
        errors.append("requirements-crispai.txt must retain setuptools<81 for pybdm")

    entries = {
        "requirements/requirements-linux-cpu.txt": "torch==2.10.*",
        "requirements/requirements-linux-cuda.txt": "tensorflow[and-cuda]==2.20.*",
    }
    for relative, marker in entries.items():
        path = root / relative
        if not path.is_file():
            errors.append(f"missing Linux entry point: {relative}")
            continue
        text = path.read_text(encoding="utf-8")
        if "-r ../requirements-linux.txt" not in text:
            errors.append(f"{relative}: must include ../requirements-linux.txt")
        if marker not in text:
            errors.append(f"{relative}: missing {marker}")

    for relative in ("Dockerfile", ".github/workflows/portability.yml"):
        text = (root / relative).read_text(encoding="utf-8")
        if "constraints-linux-cpu.txt" not in text or " -c " not in text:
            errors.append(f"{relative}: must install with the CPU constraint snapshot")
    return errors


def main() -> int:
    errors = check_repository()
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print("linux constraints: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
