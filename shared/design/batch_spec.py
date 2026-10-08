#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Batch specification model for multi search-scope x multi pattern runs.

A batch pairs a set of *search scopes* (a sequence FASTA or a BED region file)
with a set of *pattern configurations* (a full design spec overlay).  Groups
assign scope/pattern subsets; each group expands to the cartesian product of
its members, and the batch runs the union in a stable, reproducible order.

This module is pure: it validates and normalises a batch definition but never
launches a subprocess.  Execution lives in :mod:`design.batch_runner`.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

if TYPE_CHECKING:  # pragma: no cover - import kept out of the hot path
    from design.workbench_form import WorkbenchFormState


#: Characters allowed in scope/pattern/group ids and in the batch label.
_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")

#: FASTA suffixes recognised by :func:`expand_scope_dir`, longest first so a
#: ``.fasta.gz`` file is not mistaken for a plain ``.fasta`` one.
DEFAULT_FASTA_SUFFIXES: Tuple[str, ...] = (
    ".fasta.gz",
    ".fa.gz",
    ".fna.gz",
    ".fasta",
    ".fa",
    ".fna",
)

#: Keys owned by the scope (or by the batch kernel) that must never be set
#: from ``shared`` or from a pattern overlay.
RESERVED_KEYS: Tuple[str, ...] = (
    "search_fasta",
    "bed_regions",
    "input_mode",
    "result_label",
    "output_dir",
    "mask_fasta",
    "mask_same_as_target",
)

#: Keys that configure the :class:`WorkbenchFormState` struct itself instead
#: of being plain ``values`` entries.
_FORM_STRUCT_KEYS: Tuple[str, ...] = (
    "nuclease",
    "tnpb_subtype",
    "require_pam",
    "active_side",
    "side_presets",
    "side_on_target_models",
    "side_off_target_models",
)

#: Identity separator between a scope id and a pattern id.
UNIT_SEP = "__"

#: Unit ids longer than this are truncated and disambiguated with a hash.
MAX_UNIT_ID = 80


@dataclass
class ScopeSpec:
    """One search scope: exactly one of FASTA sequence or BED regions."""

    scope_id: str
    search_fasta: str = ""
    regions: str = ""
    mask_fasta: str = ""
    mask_same_as_target: bool = True

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {"scope_id": self.scope_id}
        if self.search_fasta:
            data["search_fasta"] = self.search_fasta
        if self.regions:
            data["regions"] = self.regions
        if self.mask_fasta:
            data["mask_fasta"] = self.mask_fasta
        data["mask_same_as_target"] = bool(self.mask_same_as_target)
        return data


@dataclass
class PatternVariant:
    """One pattern configuration: a design mode plus a form-value overlay."""

    pattern_id: str
    mode: str = "single_motif_flank"
    overlay: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pattern_id": self.pattern_id,
            "mode": self.mode,
            "overlay": dict(self.overlay),
        }


@dataclass
class BatchGroup:
    """A scope subset x pattern subset assignment (cartesian product)."""

    group_id: str
    scope_ids: List[str] = field(default_factory=list)
    pattern_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "group_id": self.group_id,
            "scope_ids": list(self.scope_ids),
            "pattern_ids": list(self.pattern_ids),
        }


@dataclass
class BatchSpec:
    """A whole batch: the shared form values plus the two axes and groups."""

    batch_label: str
    shared: Dict[str, Any] = field(default_factory=dict)
    scopes: List[ScopeSpec] = field(default_factory=list)
    patterns: List[PatternVariant] = field(default_factory=list)
    groups: List[BatchGroup] = field(default_factory=list)


@dataclass(frozen=True)
class BatchUnit:
    """A single runnable unit: one scope x one pattern configuration."""

    unit_id: str
    scope_id: str
    pattern_id: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "unit_id": self.unit_id,
            "scope_id": self.scope_id,
            "pattern_id": self.pattern_id,
        }


def make_unit_id(scope_id: str, pattern_id: str) -> str:
    """Return a stable ``<scope_id>__<pattern_id>`` id, hashed when too long."""

    raw = "%s%s%s" % (scope_id, UNIT_SEP, pattern_id)
    if len(raw) <= MAX_UNIT_ID:
        return raw
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:6]
    return "%s_%s" % (raw[:MAX_UNIT_ID], digest)


def _scope_index(spec: BatchSpec) -> Dict[str, ScopeSpec]:
    return {scope.scope_id: scope for scope in spec.scopes}


def _pattern_index(spec: BatchSpec) -> Dict[str, PatternVariant]:
    return {pattern.pattern_id: pattern for pattern in spec.patterns}


def normalize_units(spec: BatchSpec) -> List[BatchUnit]:
    """Expand every group to its cartesian product, de-duplicating pairs.

    Order is fixed: groups in declaration order, then each group's scopes in
    declaration order, then each group's patterns in declaration order.
    """

    scopes = _scope_index(spec)
    patterns = _pattern_index(spec)
    seen = set()
    units: List[BatchUnit] = []
    for group in spec.groups:
        for scope_id in group.scope_ids:
            if scope_id not in scopes:
                continue
            for pattern_id in group.pattern_ids:
                if pattern_id not in patterns:
                    continue
                key = (scope_id, pattern_id)
                if key in seen:
                    continue
                seen.add(key)
                units.append(
                    BatchUnit(
                        unit_id=make_unit_id(scope_id, pattern_id),
                        scope_id=scope_id,
                        pattern_id=pattern_id,
                    )
                )
    return units


def _scope_mask_values(
    mask_fasta: Any, raw_same: Any
) -> Tuple[str, bool]:
    """Normalise a scope's mask fields, applying the default rules.

    A scope with no explicit mask defaults to ``mask_same_as_target=True``;
    a scope with an explicit mask defaults to ``mask_same_as_target=False``.
    """

    mask = str(mask_fasta or "").strip()
    if raw_same is None or (
        isinstance(raw_same, str) and not raw_same.strip()
    ):
        return mask, not mask
    if isinstance(raw_same, bool):
        return mask, raw_same
    if isinstance(raw_same, (int, float)):
        return mask, bool(raw_same)
    return mask, str(raw_same).strip().lower() in ("1", "true", "yes", "on")


def _scope_from_mapping(data: Dict[str, Any]) -> ScopeSpec:
    """Build a :class:`ScopeSpec` from a raw mapping (JSON scope/TSV row)."""

    mask_fasta, same_as_target = _scope_mask_values(
        data.get("mask_fasta"), data.get("mask_same_as_target")
    )
    return ScopeSpec(
        scope_id=str(data.get("scope_id") or "").strip(),
        search_fasta=str(data.get("search_fasta") or ""),
        regions=str(data.get("regions") or ""),
        mask_fasta=mask_fasta,
        mask_same_as_target=same_as_target,
    )


def scope_input_keys(scope: ScopeSpec) -> Dict[str, Any]:
    """Return the input-mode keys for one scope.

    ``{"input_mode": "sequence", "search_fasta": ...}`` for a FASTA scope and
    ``{"input_mode": "bed", "bed_regions": ...}`` for a BED scope.
    """

    search_fasta = (scope.search_fasta or "").strip()
    regions = (scope.regions or "").strip()
    mask_fasta = (scope.mask_fasta or "").strip()
    same_as_target = bool(scope.mask_same_as_target)
    if search_fasta and regions:
        raise ValueError(
            "scope %s sets both search_fasta and regions" % scope.scope_id
        )
    if mask_fasta and same_as_target:
        raise ValueError(
            "scope %s sets both mask_fasta and mask_same_as_target"
            % scope.scope_id
        )
    if search_fasta:
        keys: Dict[str, Any] = {
            "input_mode": "sequence", "search_fasta": search_fasta,
        }
    elif regions:
        keys = {"input_mode": "bed", "bed_regions": regions}
    else:
        raise ValueError(
            "scope %s sets neither search_fasta nor regions" % scope.scope_id
        )
    if mask_fasta:
        keys["mask_fasta"] = mask_fasta
    else:
        keys["mask_same_as_target"] = same_as_target
    return keys


def build_unit_form_state(spec: BatchSpec, unit: BatchUnit):
    """Assemble the shared form state for one unit (see ``docs/BATCH.md``)."""

    from design.workbench_form import WorkbenchFormState

    scope = _scope_index(spec).get(unit.scope_id)
    pattern = _pattern_index(spec).get(unit.pattern_id)
    if scope is None:
        raise ValueError("unknown scope: %s" % unit.scope_id)
    if pattern is None:
        raise ValueError("unknown pattern: %s" % unit.pattern_id)

    keys = scope_input_keys(scope)
    values: Dict[str, Any] = dict(spec.shared)
    values.update(pattern.overlay or {})
    values.update(keys)

    struct: Dict[str, Any] = {}
    for key in _FORM_STRUCT_KEYS:
        if key in values:
            struct[key] = values.pop(key)
    values.pop("mode", None)

    return WorkbenchFormState(
        values=values,
        mode=pattern.mode,
        input_mode=keys["input_mode"],
        **struct,
    )


def validate_spec(
    spec: BatchSpec, dry_run: bool = False
) -> Tuple[List[str], List[str]]:
    """Static checks.  Returns ``(errors, warnings)``; errors block the batch.

    When ``dry_run`` is true, missing input files are downgraded to warnings so
    a batch can be previewed on a machine that holds no data.
    """

    errors: List[str] = []
    warnings: List[str] = []

    def missing(message: str) -> None:
        (warnings if dry_run else errors).append(message)

    label = (spec.batch_label or "").strip()
    if not label:
        errors.append("batch_label is required")
    elif not _ID_RE.match(label):
        errors.append(
            "batch_label contains illegal characters: %r (allowed: A-Za-z0-9._-)"
            % spec.batch_label
        )

    scope_ids: List[str] = []
    for scope in spec.scopes:
        scope_id = (scope.scope_id or "").strip()
        if not scope_id:
            errors.append("scope_id is required")
            continue
        if not _ID_RE.match(scope_id):
            errors.append(
                "scope_id %r contains illegal characters (allowed: A-Za-z0-9._-)"
                % scope_id
            )
        if scope_id in scope_ids:
            errors.append("duplicate scope_id: %s" % scope_id)
        scope_ids.append(scope_id)
        has_fasta = bool((scope.search_fasta or "").strip())
        has_bed = bool((scope.regions or "").strip())
        if has_fasta and has_bed:
            errors.append(
                "scope %s must set exactly one of search_fasta/regions (both set)"
                % scope_id
            )
        elif not has_fasta and not has_bed:
            errors.append(
                "scope %s must set exactly one of search_fasta/regions (neither set)"
                % scope_id
            )
    if not scope_ids:
        errors.append("at least one scope is required")

    pattern_ids: List[str] = []
    for pattern in spec.patterns:
        pattern_id = (pattern.pattern_id or "").strip()
        if not pattern_id:
            errors.append("pattern_id is required")
            continue
        if not _ID_RE.match(pattern_id):
            errors.append(
                "pattern_id %r contains illegal characters (allowed: A-Za-z0-9._-)"
                % pattern_id
            )
        if pattern_id in pattern_ids:
            errors.append("duplicate pattern_id: %s" % pattern_id)
        pattern_ids.append(pattern_id)
        try:
            from design.pattern_spec import PatternKind

            PatternKind(str(pattern.mode))
        except (ValueError, TypeError):
            errors.append(
                "pattern %s has unknown mode: %r" % (pattern_id, pattern.mode)
            )
    if not pattern_ids:
        errors.append("at least one pattern is required")

    for key in RESERVED_KEYS:
        if key in (spec.shared or {}):
            errors.append("shared must not set reserved key %r" % key)
    for pattern in spec.patterns:
        for key in RESERVED_KEYS:
            if key in (pattern.overlay or {}):
                errors.append(
                    "pattern %s overlay must not set reserved key %r"
                    % (pattern.pattern_id, key)
                )

    scopes = _scope_index(spec)
    patterns = _pattern_index(spec)
    if not spec.groups:
        errors.append("at least one group is required")
    group_ids: List[str] = []
    used_scopes = set()
    used_patterns = set()
    for group in spec.groups:
        group_id = (group.group_id or "").strip()
        if not group_id:
            errors.append("group_id is required")
        else:
            if not _ID_RE.match(group_id):
                errors.append(
                    "group_id %r contains illegal characters" % group_id
                )
            if group_id in group_ids:
                errors.append("duplicate group_id: %s" % group_id)
            group_ids.append(group_id)
        if not group.scope_ids:
            warnings.append("group %s has no scopes" % group_id)
        if not group.pattern_ids:
            warnings.append("group %s has no patterns" % group_id)
        for scope_id in group.scope_ids:
            if scope_id not in scopes:
                errors.append(
                    "group %s references unknown scope: %s" % (group_id, scope_id)
                )
            else:
                used_scopes.add(scope_id)
        for pattern_id in group.pattern_ids:
            if pattern_id not in patterns:
                errors.append(
                    "group %s references unknown pattern: %s"
                    % (group_id, pattern_id)
                )
            else:
                used_patterns.add(pattern_id)

    for scope_id in scope_ids:
        if scope_id not in used_scopes:
            errors.append("scope %s is not assigned to any group" % scope_id)
    for pattern_id in pattern_ids:
        if pattern_id not in used_patterns:
            warnings.append("pattern %s is not used by any group" % pattern_id)

    for scope in spec.scopes:
        scope_id = (scope.scope_id or "").strip()
        mask_fasta = (scope.mask_fasta or "").strip()
        if mask_fasta and bool(scope.mask_same_as_target):
            errors.append(
                "scope %s must not set both mask_fasta and "
                "mask_same_as_target" % scope_id
            )
        for key, value in (
            ("search_fasta", scope.search_fasta),
            ("regions", scope.regions),
            ("mask_fasta", mask_fasta),
        ):
            value = (value or "").strip()
            if value and not os.path.isfile(value):
                missing("scope %s %s not found: %s" % (scope_id, key, value))
    value = str((spec.shared or {}).get("genome_fasta") or "").strip()
    if value and not os.path.isfile(value):
        missing("shared genome_fasta not found: %s" % value)
    value = str((spec.shared or {}).get("annotation") or "").strip()
    if value and not os.path.isfile(value):
        missing("shared annotation not found: %s" % value)

    return errors, warnings


def expand_scope_dir(
    directory: str, suffixes: Tuple[str, ...] = DEFAULT_FASTA_SUFFIXES
) -> List[ScopeSpec]:
    """Expand a directory of FASTA files into scopes, sorted by file name.

    ``scope_id`` is the file name minus its FASTA suffix; duplicate stems get
    ``_2``, ``_3``, ... in sorted order.
    """

    try:
        names = sorted(os.listdir(directory))
    except OSError:
        return []
    lowered = tuple(suffix.lower() for suffix in suffixes)
    scopes: List[ScopeSpec] = []
    used: Dict[str, int] = {}
    for name in names:
        path = os.path.join(directory, name)
        if not os.path.isfile(path):
            continue
        lower_name = name.lower()
        suffix = next(
            (item for item in lowered if lower_name.endswith(item)), None
        )
        if suffix is None:
            continue
        stem = name[: len(name) - len(suffix)]
        count = used.get(stem, 0) + 1
        used[stem] = count
        scope_id = stem if count == 1 else "%s_%d" % (stem, count)
        scopes.append(ScopeSpec(scope_id=scope_id, search_fasta=path))
    return scopes


def _sanitize_label(text: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", text or "")
    return cleaned.strip("-._")


def load_units_tsv(path: str) -> BatchSpec:
    """Load the advanced units TSV (one unit per row) into a :class:`BatchSpec`."""

    scopes: Dict[str, ScopeSpec] = {}
    patterns: Dict[str, PatternVariant] = {}
    groups: List[BatchGroup] = []
    label = _sanitize_label(os.path.splitext(os.path.basename(path))[0])
    with open(path, "r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for index, row in enumerate(reader, start=1):
            scope_id = (row.get("scope_id") or "").strip()
            pattern_id = (row.get("pattern_id") or "").strip()
            if scope_id and scope_id not in scopes:
                mask_fasta, same_as_target = _scope_mask_values(
                    row.get("mask_fasta"), row.get("mask_same_as_target")
                )
                scopes[scope_id] = ScopeSpec(
                    scope_id=scope_id,
                    search_fasta=(row.get("search_fasta") or "").strip(),
                    regions=(row.get("regions") or "").strip(),
                    mask_fasta=mask_fasta,
                    mask_same_as_target=same_as_target,
                )
            if pattern_id and pattern_id not in patterns:
                mode = "single_motif_flank"
                overlay: Dict[str, Any] = {}
                raw = (row.get("pattern_json") or "").strip()
                if raw:
                    data = json.loads(raw)
                    if not isinstance(data, dict):
                        raise ValueError(
                            "pattern_json for %s must be a JSON object"
                            % pattern_id
                        )
                    data = dict(data)
                    mode = str(data.pop("mode", mode) or mode)
                    overlay = data
                patterns[pattern_id] = PatternVariant(
                    pattern_id=pattern_id, mode=mode, overlay=overlay
                )
            groups.append(
                BatchGroup(
                    group_id="G%d" % index,
                    scope_ids=[scope_id],
                    pattern_ids=[pattern_id],
                )
            )
    return BatchSpec(
        batch_label=label or "units-tsv",
        shared={},
        scopes=list(scopes.values()),
        patterns=list(patterns.values()),
        groups=groups,
    )


def spec_to_dict(
    spec: BatchSpec, units: Optional[List[BatchUnit]] = None
) -> Dict[str, Any]:
    """Serialise a spec (and optionally its normalised units) to a dict."""

    data: Dict[str, Any] = {
        "batch_label": spec.batch_label,
        "shared": dict(spec.shared),
        "scopes": [scope.to_dict() for scope in spec.scopes],
        "patterns": [pattern.to_dict() for pattern in spec.patterns],
        "groups": [group.to_dict() for group in spec.groups],
    }
    if units is not None:
        data["units"] = [unit.to_dict() for unit in units]
    return data


def spec_from_dict(data: Dict[str, Any]) -> BatchSpec:
    """Rebuild a :class:`BatchSpec` from a ``batch.json`` payload."""

    data = data or {}
    scopes = [
        _scope_from_mapping(scope) for scope in (data.get("scopes") or [])
    ]
    patterns = [
        PatternVariant(
            pattern_id=str(pattern.get("pattern_id") or ""),
            mode=str(pattern.get("mode") or "single_motif_flank"),
            overlay=dict(pattern.get("overlay") or {}),
        )
        for pattern in (data.get("patterns") or [])
    ]
    groups = [
        BatchGroup(
            group_id=str(group.get("group_id") or ""),
            scope_ids=[str(item) for item in (group.get("scope_ids") or [])],
            pattern_ids=[
                str(item) for item in (group.get("pattern_ids") or [])
            ],
        )
        for group in (data.get("groups") or [])
    ]
    return BatchSpec(
        batch_label=str(data.get("batch_label") or ""),
        shared=dict(data.get("shared") or {}),
        scopes=scopes,
        patterns=patterns,
        groups=groups,
    )


def load_batch_json(path: str) -> BatchSpec:
    """Read a ``batch.json`` file into a :class:`BatchSpec`."""

    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("batch.json must contain a JSON object: %s" % path)
    return spec_from_dict(data)


def write_batch_json(
    spec: BatchSpec, units: Optional[List[BatchUnit]], path: str
) -> None:
    """Write the normalised batch (spec + units) as UTF-8 JSON."""

    data = spec_to_dict(spec, units)
    directory = os.path.dirname(os.path.abspath(path))
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=False)
        handle.write("\n")
