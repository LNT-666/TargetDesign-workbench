#!/usr/bin/env python3
"""Check that the tested Linux constraint snapshots cover the declared deps."""
from __future__ import annotations

import re
import sys
import tomllib
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
ENTRY_FILES = (
    "requirements/requirements-linux-cpu.txt",
    "requirements/requirements-linux-cuda.txt",
)
DOCUMENT_FILES = (
    "README.md",
    "docs/ENVIRONMENT.md",
    "docs/help_en/index.md",
)
SUPPORTED_PYTHON_RANGE = ">=3.12,<3.14"
RECOMMENDED_PYTHON = "3.12"
PIN_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)\s*==\s*([^\s;#]+)\s*$")
REQ_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)")
RECOMMENDATION_RE = re.compile(
    r"(?:\brecommends?\b|\brecommended(?:\s+version)?\b|推荐(?:版本)?)"
    r"\s*[:：]?\s*(?:Python\s*)?3\.12\b",
    re.IGNORECASE,
)
PINNED_REQUIREMENTS_RE = re.compile(r"\bpinned requirements\b", re.IGNORECASE)
FLOATING_INSTALL_RE = re.compile(
    r"(?:^|\s)-r\s+requirements(?:-windows)?\.txt(?=\s|$)",
    re.MULTILINE,
)


def canonical(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def fenced_code_blocks(text: str) -> List[str]:
    blocks: List[str] = []
    current: List[str] | None = None
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            if current is None:
                current = []
            else:
                blocks.append("\n".join(current))
                current = None
        elif current is not None:
            current.append(line)
    if current is not None:
        blocks.append("\n".join(current))
    return blocks


def has_paired_install(blocks: List[str], constraint: str, entry: str) -> bool:
    return any(
        f"-c {constraint}" in block and f"-r {entry}" in block
        for block in blocks
    )


def check_constraint_header(
    relative: str,
    text: str,
    constraint: str,
    entry: str,
    errors: List[str],
) -> None:
    header_lines: List[str] = []
    for raw in text.splitlines():
        stripped = raw.strip()
        if stripped.startswith("#"):
            header_lines.append(stripped)
        elif stripped:
            break
    header = "\n".join(header_lines)
    entry_refs = re.findall(r"(?<!\S)-r\s+([^\s\\]+)", header)
    if f"-c {constraint}" not in header or entry_refs != [entry]:
        errors.append(
            f"{relative}: install header must pair -c {constraint} "
            f"with -r {entry}")


def check_python_metadata(root: Path, errors: List[str]) -> None:
    relative = "pyproject.toml"
    path = root / relative
    if not path.is_file():
        errors.append(f"missing Python metadata: {relative}")
        return
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        errors.append(f"{relative}: invalid TOML: {exc}")
        return
    project = data.get("project", {})
    python_range = project.get("requires-python") if isinstance(project, dict) else None
    if python_range != SUPPORTED_PYTHON_RANGE:
        errors.append(
            f"{relative}: requires-python must be {SUPPORTED_PYTHON_RANGE!r}")


def check_documentation(root: Path, errors: List[str]) -> None:
    texts: Dict[str, str] = {}
    for relative in DOCUMENT_FILES:
        path = root / relative
        if not path.is_file():
            errors.append(f"missing installation document: {relative}")
            continue
        text = path.read_text(encoding="utf-8")
        texts[relative] = text
        if f"Python {SUPPORTED_PYTHON_RANGE}" not in text:
            errors.append(
                f"{relative}: must declare Python {SUPPORTED_PYTHON_RANGE}")
        if not RECOMMENDATION_RE.search(text):
            errors.append(f"{relative}: must recommend Python {RECOMMENDED_PYTHON}")
        if PINNED_REQUIREMENTS_RE.search(text):
            errors.append(
                f"{relative}: must not call floating requirements 'pinned requirements'")
        if FLOATING_INSTALL_RE.search(text) and not re.search(
                r"(?:not\s+pinned|不固定|compatible|兼容)", text, re.IGNORECASE):
            errors.append(
                f"{relative}: floating requirements must be labeled as compatible ranges")

    for relative in ("README.md", "docs/help_en/index.md"):
        text = texts.get(relative)
        if text is None:
            continue
        if "ENVIRONMENT.md" not in text:
            errors.append(f"{relative}: must point to ENVIRONMENT.md for formal installs")
        for constraint, entry in zip(CONSTRAINT_FILES, ENTRY_FILES):
            if constraint not in text or entry not in text:
                errors.append(
                    f"{relative}: must reference {constraint} and {entry}")

    environment = texts.get("docs/ENVIRONMENT.md")
    if environment is None:
        return
    blocks = fenced_code_blocks(environment)
    for label, constraint, entry in zip(
            ("CPU", "CUDA"), CONSTRAINT_FILES, ENTRY_FILES):
        if not has_paired_install(blocks, constraint, entry):
            errors.append(
                f"docs/ENVIRONMENT.md: {label} install command must pair "
                f"-c {constraint} and -r {entry} in one fenced block")


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
        entry = ENTRY_FILES[CONSTRAINT_FILES.index(relative)]
        check_constraint_header(relative, text, relative, entry, errors)
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

    check_python_metadata(root, errors)
    check_documentation(root, errors)

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
