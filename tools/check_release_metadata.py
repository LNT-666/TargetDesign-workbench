#!/usr/bin/env python3
"""Check release metadata shared by pyproject, CFF and Zenodo."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

import yaml


#: Zenodo concept DOI; it resolves to every archived version of the software.
CONCEPT_DOI = "10.5281/zenodo.23231712"
DOI_RE = re.compile(r"^10\.\d{4,5}/zenodo\.\d+$")
#: Comment wording that means the value below it still has to be filled in.
PLACEHOLDER_MARKERS = (
    "replace with", "tbd", "todo", "fixme", "fill in", "待补", "待回填",
)


def _load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a mapping")
    return data


def _score_name(author: dict[str, Any]) -> tuple[str, str]:
    return str(author.get("family-names", "")), str(author.get("given-names", ""))


def _creator_name(creator: dict[str, Any]) -> str:
    return str(creator.get("name", ""))


def _orcid(value: Any) -> str:
    text = str(value or "").strip()
    for prefix in ("https://orcid.org/", "http://orcid.org/"):
        if text.startswith(prefix):
            return text[len(prefix):]
    return text


def _tagged_locally(root: Path, version: str) -> bool | None:
    """Whether ``v<version>`` is a local git tag; ``None`` when that is unknown.

    Release staging copies a plain directory and a bundle has no ``.git``, so an
    unreadable answer downgrades to "not verifiable" rather than a false error.
    """
    tag = f"v{version}"
    try:
        result = subprocess.run(
            ["git", "tag", "--list", tag], cwd=str(root), capture_output=True,
            text=True, timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return tag in result.stdout.split()


def check_dois(root: Path, citation: dict[str, Any]) -> list[str]:
    """Check the archived DOI of a version that has already been released."""
    errors: list[str] = []
    cff_path = root / "CITATION.cff"
    try:
        lines = cff_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        return [f"CITATION.cff read failed: {exc}"]
    for line in lines:
        if not line.lstrip().startswith("#"):
            continue
        lowered = line.lower()
        for marker in PLACEHOLDER_MARKERS:
            if marker in lowered:
                errors.append(
                    f"CITATION.cff still carries an unresolved placeholder "
                    f"({marker!r}); publish the reserved version DOI first")

    version = str(citation.get("version", "") or "")
    doi = str(citation.get("doi", "") or "").strip()
    if doi and not DOI_RE.match(doi):
        errors.append(f"CITATION.cff doi is not a Zenodo DOI: {doi!r}")
    released = _tagged_locally(root, version) if version else None
    if released and (not doi or doi == CONCEPT_DOI):
        errors.append(
            f"v{version} is tagged locally but CITATION.cff still cites the "
            "concept DOI; fill in the reserved version DOI before publishing")
    return errors


def check_metadata(root: Path) -> list[str]:
    """Return all release-metadata inconsistencies under ``root``."""
    errors: list[str] = []
    try:
        with (root / "pyproject.toml").open("rb") as fh:
            project = tomllib.load(fh).get("project", {})
        citation = _load_yaml(root / "CITATION.cff")
        zenodo = json.loads((root / ".zenodo.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError, tomllib.TOMLDecodeError) as exc:
        return [f"metadata load failed: {exc}"]

    versions = {
        "pyproject.toml": str(project.get("version", "")),
        "CITATION.cff": str(citation.get("version", "")),
        ".zenodo.json": str(zenodo.get("version", "")),
    }
    if not all(versions.values()) or len(set(versions.values())) != 1:
        errors.append("version mismatch: " + ", ".join(
            f"{name}={value or '<missing>'}" for name, value in versions.items()))

    cff_title = " ".join(str(citation.get("title", "")).split())
    zenodo_title = " ".join(str(zenodo.get("title", "")).split())
    if not cff_title or cff_title != zenodo_title:
        errors.append(
            f"title mismatch: CITATION.cff={cff_title or '<missing>'!r}, "
            f".zenodo.json={zenodo_title or '<missing>'!r}")
    project_name = str(project.get("name", ""))
    if not project_name or cff_title.lower() != project_name.lower():
        errors.append(
            f"project/title mismatch: pyproject.toml={project_name or '<missing>'!r}, "
            f"CITATION.cff={cff_title or '<missing>'!r}")

    cff_authors = citation.get("authors") or []
    creators = zenodo.get("creators") or []
    if len(cff_authors) != len(creators):
        errors.append(
            f"author count mismatch: CITATION.cff={len(cff_authors)}, "
            f".zenodo.json={len(creators)}")
    for index, (author, creator) in enumerate(zip(cff_authors, creators), 1):
        if not isinstance(author, dict) or not isinstance(creator, dict):
            errors.append(f"author {index}: expected mappings")
            continue
        family, given = _score_name(author)
        if _creator_name(creator) != f"{family}, {given}":
            errors.append(
                f"author {index} order/name mismatch: "
                f"CITATION.cff={family}, {given!r}; "
                f".zenodo.json={_creator_name(creator)!r}")
        cff_affiliation = str(author.get("affiliation", ""))
        zenodo_affiliation = str(creator.get("affiliation", ""))
        if cff_affiliation != zenodo_affiliation:
            errors.append(
                f"author {index} affiliation mismatch: "
                f"CITATION.cff={cff_affiliation!r}; "
                f".zenodo.json={zenodo_affiliation!r}")
        if _orcid(author.get("orcid")) != _orcid(creator.get("orcid")):
            errors.append(
                f"author {index} ORCID mismatch: "
                f"CITATION.cff={_orcid(author.get('orcid')) or '<missing>'}; "
                f".zenodo.json={_orcid(creator.get('orcid')) or '<missing>'}")

    errors.extend(check_dois(root, citation))
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parent.parent,
        help="repository root (default: parent of tools/)")
    args = parser.parse_args(argv)
    errors = check_metadata(args.root.resolve())
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("release metadata: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
