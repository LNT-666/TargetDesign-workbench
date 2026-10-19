#!/usr/bin/env python3
"""Check release metadata shared by pyproject, CFF and Zenodo."""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from pathlib import Path
from typing import Any

import yaml


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
