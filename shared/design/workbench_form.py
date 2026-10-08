#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Desktop/web shared form layer for the Pattern Designer.

The pure "form values -> PatternSpec / RunnerConfig" logic used to live inside
``designer_workbench.PatternDesignerWorkbench``. It moved here so that the
desktop workbench and the local web app build their specs and runner configs
from one implementation, keeping web results identical to desktop and CLI
results (see ``docs/WEBAPP.md``).

This module must never import tkinter.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from data.annotation_utils import ensure_plain_fasta
from design.pattern_runner import RunnerConfig
from design.pattern_spec import MotifSpec, PatternKind, PatternSpec, Side
from design.system_presets import (
    get_preset, preset_choices, resolve_preset_pam, resolve_run_nuclease,
)
from scoring.scoring import (
    MODEL_PROTEIN_GROUPS,
    PROTEIN_GROUP_LABELS,
    TRADITIONAL_MODELS,
    model_choices_for_preset,
)
from utils import system_memory
from utils.paths import default_output_dir


PRESET_KEYS = [key for key, _ in preset_choices()]


MODE_LABELS = {
    PatternKind.SINGLE_MOTIF_FLANK.value: "Single target design",
    PatternKind.MOTIF_GAP_MOTIF.value: (
        "Paired-target design Pattern A: Target-xbp-Target"
    ),
    PatternKind.Y_CENTERED_MOTIFS.value: (
        "Paired-target design Pattern B: Target-xbp-Motif-ybp-Target"
    ),
}

PAIR_RANK_POLICY_FIELDS = (
    "e_high",
    "e_min",
    "e_fail",
    "delta_default",
    "b_low",
    "b_high",
    "m_low",
    "m_high",
    "h_risk",
    "h_max",
)

#: On-target model a side falls back to when its nuclease is known.
DEFAULT_ON_TARGET_MODELS = {
    "cas9": "cropsr",
    "cas12a": "rules",
    "cas13": "rna_rules",
    "tnpb": "omega",
    "custom": "rules",
}

#: Field keys written by each side's motif / length / position control.
SIDE_FIELD_KEYS = {
    "target": ("motif", "flank", "side"),
    "left": ("left_motif", "left_flank", "left_side"),
    "right": ("right_motif", "right_flank", "right_side"),
}

#: "Use for Run" side -> the PAM requirement flag it maintains.
SIDE_REQUIRE_PAM_KEYS = {
    "target": "require_pam",
    "left": "left_require_pam",
    "right": "right_require_pam",
}

_TRUE_TEXT = ("1", "true", "yes", "on", "y", "t")
_FALSE_TEXT = ("", "0", "false", "no", "off", "n", "f")


def _noop_log(_line: str) -> None:
    return None


def coerce_bool(value: Any, default: bool = False) -> bool:
    """Return a boolean for Tk booleans, JSON booleans and form strings."""
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in _TRUE_TEXT:
        return True
    if text in _FALSE_TEXT:
        return False
    return bool(text)


def split_model_selection(value) -> list:
    """Return ordered, unique model names from a comma-separated value."""
    if isinstance(value, (list, tuple)):
        raw = value
    else:
        raw = str(value or "").replace(";", ",").split(",")
    models = []
    for item in raw:
        model = str(item or "").strip()
        if model and model not in models:
            models.append(model)
    return models


def model_display_name(model: str) -> str:
    parts = []
    protein = MODEL_PROTEIN_GROUPS.get(model, "general")
    parts.append("[%s]" % PROTEIN_GROUP_LABELS.get(protein, protein))
    if model in TRADITIONAL_MODELS:
        parts.append("[rule]")
    parts.append(model)
    return " ".join(parts)


def to_side(value: str, default: Side = Side.UPSTREAM) -> Side:
    value = (value or default.value).strip()
    return Side.UPSTREAM if value in ("upstream", "3prime") else Side.DOWNSTREAM


def side_to_pam_side(value: str, default: str = "3prime") -> str:
    value = (value or "").strip()
    if value in ("upstream", "3prime"):
        return "3prime"
    if value in ("downstream", "5prime"):
        return "5prime"
    return default


def pam_side_to_side(value: str, default: str = "upstream") -> str:
    value = (value or "").strip()
    if value == "3prime":
        return "upstream"
    if value == "5prime":
        return "downstream"
    return default


def _side_subtype(preset: Dict[str, Any], form_subtype: str) -> str:
    """Return the effective TnpB subtype for one side.

    A preset that names a concrete subtype wins; the generic ``tnpb`` preset
    reports ``unknown`` and defers to the subtype the user picked.
    """

    preset_subtype = str(
        preset.get("tnpb_subtype") or "unknown"
    ).strip().lower()
    if preset_subtype and preset_subtype != "unknown":
        return preset_subtype
    return str(form_subtype or "unknown").strip().lower() or "unknown"


def active_side_keys(side: str) -> tuple:
    """Return (motif, length, position, side) field keys for a run side."""
    mapping = {
        "target": ("motif", "flank", "side", "target"),
        "left": ("left_motif", "left_flank", "left_side", "left"),
        "right": ("right_motif", "right_flank", "right_side", "right"),
    }
    return mapping.get(side, mapping["left"])


def auto_memory_limit() -> int:
    snapshot = system_memory.memory_snapshot()
    value = system_memory.resolve_auto_limit_mb(
        snapshot["total_mb"], snapshot["available_mb"])
    if value <= 0:
        raise ValueError("cannot detect memory on this host")
    return value


@dataclass
class WorkbenchFormState:
    """Snapshot of the Pattern Designer controls.

    ``values`` holds every plain form field keyed by its field name. Tk
    ``BooleanVar``s and JSON payloads may hand over real booleans; everything
    is normalised by :meth:`value` / :meth:`bool_value`.
    """

    values: Dict[str, Any] = field(default_factory=dict)
    mode: str = PatternKind.SINGLE_MOTIF_FLANK.value
    input_mode: str = "sequence"
    nuclease: str = "cas9"
    tnpb_subtype: str = "unknown"
    require_pam: bool = True
    active_side: str = "left"
    side_presets: Dict[str, str] = field(
        default_factory=lambda: {
            "target": "cas9", "left": "cas9", "right": "cas9",
        }
    )
    side_on_target_models: Dict[str, str] = field(
        default_factory=lambda: {
            "target": "auto", "left": "auto", "right": "auto",
        }
    )
    side_off_target_models: Dict[str, str] = field(
        default_factory=lambda: {
            "target": "auto", "left": "auto", "right": "auto",
        }
    )
    log: Callable[[str], None] = _noop_log

    def value(self, key: str, default: str = "") -> str:
        if key not in self.values:
            return default
        raw = self.values[key]
        if isinstance(raw, bool):
            return "1" if raw else ""
        if raw is None:
            return ""
        return str(raw).strip()

    def int_value(self, key: str, default: str = "") -> Optional[int]:
        value = self.value(key, default)
        return int(value) if value.isdigit() else None

    def bool_value(self, key: str, default: bool = False) -> bool:
        if key not in self.values:
            return default
        return coerce_bool(self.values[key], default)

    def kind(self) -> PatternKind:
        return PatternKind(self.mode)

    def is_pair(self) -> bool:
        return self.kind() in (
            PatternKind.MOTIF_GAP_MOTIF,
            PatternKind.Y_CENTERED_MOTIFS,
        )

    def is_bed_mode(self) -> bool:
        return self.input_mode == "bed"

    def side_preset(self, side: str) -> str:
        if side in self.side_presets:
            return self.side_presets[side] or "custom"
        return self.side_presets.get("left") or "custom"

    def side_on_target_model(self, side: str) -> str:
        return self.side_on_target_models.get(side) or "auto"

    def side_off_target_model(self, side: str) -> str:
        return self.side_off_target_models.get(side) or "auto"

    def require_pam_for(self, side: str) -> bool:
        key = SIDE_REQUIRE_PAM_KEYS.get(side, "require_pam")
        if key in self.values:
            return self.bool_value(key, bool(self.require_pam))
        return bool(self.require_pam)


def resolved_memory_limit(state: WorkbenchFormState) -> int:
    mode = state.value("memory_mode", "auto").lower()
    if mode == "unlimited":
        return 0
    if mode == "custom":
        raw = state.value("max_memory_mb")
        try:
            value = int(raw)
        except ValueError:
            raise ValueError("Custom MiB must be an integer")
        if value < 512:
            raise ValueError("Custom MiB must be at least 512")
        return value
    if mode != "auto":
        raise ValueError("Unknown Memory Limit mode: %s" % mode)
    return auto_memory_limit()


def search_timeout_s(state: WorkbenchFormState) -> Optional[float]:
    """Resolve the optional off-target search timeout, in seconds."""
    raw = state.value("search_timeout_s")
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError:
        raise ValueError("Search timeout must be a number of seconds")
    if value <= 0:
        raise ValueError("Search timeout must be greater than zero")
    return value


def pair_rank_policy_values(
    state: WorkbenchFormState,
) -> Tuple[Dict[str, float], List[str]]:
    policy: Dict[str, float] = {}
    missing: List[str] = []
    for field_name in PAIR_RANK_POLICY_FIELDS:
        value = state.value("pair_rank_%s" % field_name, "").strip()
        if not value:
            missing.append(field_name)
            continue
        try:
            policy[field_name] = float(value)
        except ValueError:
            missing.append(field_name)
    return policy, missing


def prepare_genome_fasta(state: WorkbenchFormState) -> str:
    """Return a plain-text Genome FASTA path (accepts ``.fna.gz`` input).

    Non-gzip input is returned unchanged; gzip input is decompressed next to
    its source (or into the fixed output directory) and reused while it stays
    current.
    """
    raw = state.value("genome_fasta").strip()
    if not raw:
        return ""
    prepared = ensure_plain_fasta(
        raw,
        log_func=state.log,
        fallback_dir=default_output_dir(),
    )
    if not prepared:
        raise ValueError("Genome FASTA could not be prepared: %s" % raw)
    return prepared


def resolve_side_models(state: WorkbenchFormState, side: str) -> tuple:
    """Return (on_target, off_target, reference_only) for one TAM side.

    ``void`` placeholders become ``auto``; a TnpB side maps its on-target
    pick to ``omega`` (offline) or ``teep`` (online reference-only).
    """
    preset = get_preset(state.side_preset(side))
    nuc = (preset.get("nuclease") or "custom").lower()
    on_choices = split_model_selection(
        state.side_on_target_model(side)
    ) or ["auto"]
    off_choices = split_model_selection(
        state.side_off_target_model(side)
    ) or ["auto"]
    if nuc == "tnpb":
        ref = "teep" if "teep" in on_choices else "none"
        return ",".join(on_choices), ",".join(off_choices), ref
    on_models = [
        "auto" if model == "void" else model
        for model in on_choices
    ]
    off_models = [
        "auto" if model == "void" else model
        for model in off_choices
    ]
    return ",".join(on_models), ",".join(off_models), "none"

def build_pattern_spec(state: WorkbenchFormState) -> PatternSpec:
    kind = state.kind()
    if kind is PatternKind.SINGLE_MOTIF_FLANK:
        return PatternSpec(
            kind=kind,
            motif=MotifSpec(
                state.value("motif"),
                state.int_value("flank", "0") or 0,
                to_side(state.value("side", "upstream")),
            ),
        )
    if kind is PatternKind.MOTIF_GAP_MOTIF:
        return PatternSpec(
            kind=kind,
            left=MotifSpec(
                state.value("left_motif"),
                state.int_value("left_flank", "0") or 0,
                to_side(state.value("left_side", "upstream")),
            ),
            right=MotifSpec(
                state.value("right_motif"),
                state.int_value("right_flank", "0") or 0,
                to_side(
                    state.value("right_side", "downstream"),
                    default=Side.DOWNSTREAM,
                ),
            ),
            min_gap=state.int_value("min_gap"),
            max_gap=state.int_value("max_gap"),
        )
    return PatternSpec(
        kind=kind,
        y_sequence=state.value("y_sequence"),
        left=MotifSpec(
            state.value("left_motif"),
            state.int_value("left_flank", "0") or 0,
            to_side(state.value("left_side", "upstream")),
        ),
        right=MotifSpec(
            state.value("right_motif"),
            state.int_value("right_flank", "0") or 0,
            to_side(
                state.value("right_side", "downstream"),
                default=Side.DOWNSTREAM,
            ),
        ),
        left_min_distance=state.int_value("left_min_distance"),
        left_max_distance=state.int_value("left_max_distance"),
        right_min_distance=state.int_value("right_min_distance"),
        right_max_distance=state.int_value("right_max_distance"),
    )


def default_run_label(
    state: WorkbenchFormState,
    spec: Optional[PatternSpec] = None,
) -> str:
    spec = spec if spec is not None else build_pattern_spec(state)
    if (
        spec.kind is PatternKind.Y_CENTERED_MOTIFS
        and spec.left
        and spec.right
        and spec.y_sequence
    ):
        return "%s-%s-%s" % (
            spec.left.sequence,
            spec.y_sequence,
            spec.right.sequence,
        )
    active = (
        "target"
        if spec.kind is PatternKind.SINGLE_MOTIF_FLANK
        else state.active_side
    )
    preset_key = (
        state.side_presets.get(active, state.side_presets.get("left"))
        or "custom"
    )
    preset = get_preset(preset_key)
    system_label = (
        preset.get("label")
        or state.nuclease
        or "custom"
    )
    system = system_label.split("/")[0].strip()
    search_fasta = state.value(
        "bed_regions" if state.is_bed_mode() else "search_fasta"
    )
    target = (
        os.path.splitext(os.path.basename(search_fasta))[0]
        if search_fasta else ""
    )
    parts = [part for part in (system, target) if part]
    return "_".join(parts) if parts else "results"


def build_runner_config(
    state: WorkbenchFormState,
    spec: Optional[PatternSpec] = None,
) -> RunnerConfig:
    kind = spec.kind if spec is not None else state.kind()
    # A single-motif pattern only has a target side, so its preset must come
    # from ``target`` even when ``active_side`` still points at a pair side
    # (a batch that never sets ``active_side``, or a UI that switched back
    # from pair mode).  Otherwise a non-cas9 target preset is ignored and the
    # run silently falls back to the global cas9 nuclease.
    run_side = (
        "target"
        if kind is PatternKind.SINGLE_MOTIF_FLANK
        else state.active_side
    )
    motif_key, flank_key, side_key, side = active_side_keys(run_side)
    preset_key = (
        state.side_presets.get(side, state.side_presets.get("left"))
        or "custom"
    )
    preset = get_preset(preset_key)
    mode = "preset" if preset_key != "custom" else "free"
    # The active side's preset is the system this run is designed for, so it
    # owns the run-level nuclease as well: ``--mode preset --preset tnpb``
    # must not be paired with ``--nuclease cas9`` just because the global
    # nuclease was never refreshed by ``Apply`` (see ``resolve_run_nuclease``
    # for how an explicit non-cas9 choice still outranks the cas9 default).
    run_nuclease = resolve_run_nuclease(
        state.nuclease, preset_key if mode == "preset" else "custom"
    )
    preset_pam, preset_pam_side, _preset_required = resolve_preset_pam(
        preset_key, state.tnpb_subtype
    )
    pam = state.value(motif_key) or preset_pam or ""
    pam_side = preset_pam_side or side_to_pam_side(
        state.value(side_key), "3prime"
    )
    is_pair = kind in (
        PatternKind.MOTIF_GAP_MOTIF,
        PatternKind.Y_CENTERED_MOTIFS,
    )
    if is_pair:
        left_preset = get_preset(state.side_preset("left"))
        right_preset = get_preset(state.side_preset("right"))
        left_nuc = left_preset.get("nuclease") or state.nuclease
        right_nuc = right_preset.get("nuclease") or state.nuclease
        left_tnpb = _side_subtype(left_preset, state.tnpb_subtype)
        right_tnpb = _side_subtype(right_preset, state.tnpb_subtype)
        left_preset_pam, left_preset_side, left_preset_required = \
            resolve_preset_pam(state.side_preset("left"), left_tnpb)
        right_preset_pam, right_preset_side, right_preset_required = \
            resolve_preset_pam(state.side_preset("right"), right_tnpb)
        left_on_otm, left_otm, left_ref = resolve_side_models(state, "left")
        right_on_otm, right_otm, right_ref = resolve_side_models(state, "right")
        on_otm, off_otm, ref_otm = resolve_side_models(state, side)
        left_pam_motif = (
            state.value("left_motif") or left_preset_pam or ""
        )
        right_pam_motif = (
            state.value("right_motif") or right_preset_pam or ""
        )
        left_pam_side = left_preset_side or side_to_pam_side(
            state.value("left_side"), "3prime"
        )
        right_pam_side = right_preset_side or side_to_pam_side(
            state.value("right_side"), "3prime"
        )
        left_require_pam = state.bool_value(
            "left_require_pam", bool(left_preset_required))
        right_require_pam = state.bool_value(
            "right_require_pam", bool(right_preset_required))
    else:
        left_nuc = right_nuc = None
        left_tnpb = right_tnpb = None
        left_on_otm = left_otm = right_on_otm = right_otm = None
        left_ref = right_ref = None
        on_otm, off_otm, ref_otm = resolve_side_models(state, "target")
        left_pam_motif = right_pam_motif = None
        left_pam_side = right_pam_side = None
        left_require_pam = right_require_pam = None
    max_mismatch = state.int_value("max_mismatch", "4")
    if max_mismatch is None:
        max_mismatch = 4
    max_bulge_text = state.value("max_bulge", "").strip()
    max_bulge = int(max_bulge_text) if max_bulge_text else None
    pam_mode = state.value("pam_mode", "strict_ngg") or "strict_ngg"
    memory_mode = state.value("memory_mode", "auto").lower()
    memory_limit = resolved_memory_limit(state)
    pair_rank_policy = None
    if is_pair:
        pair_rank_policy, _missing = pair_rank_policy_values(state)
        if _missing:
            pair_rank_policy = None
    return RunnerConfig(
        search_fasta=(
            state.value("search_fasta")
            if not state.is_bed_mode() else ""
        ),
        regions=(
            state.value("bed_regions")
            if state.is_bed_mode() else ""
        ),
        genome_fasta=prepare_genome_fasta(state),
        mask_fasta=state.value("mask_fasta"),
        mask_same_as_target=coerce_bool(
            state.value("mask_same_as_target"), False
        ),
        output_dir=default_output_dir(),
        blastdb=state.value("blastdb"),
        annotation=state.value("annotation"),
        run_label=(
            state.value("result_label", "").strip()
            or default_run_label(state)
        ),
        nuclease=run_nuclease,
        tnpb_subtype=state.tnpb_subtype,
        left_nuclease=left_nuc,
        right_nuclease=right_nuc,
        left_tnpb_subtype=left_tnpb,
        right_tnpb_subtype=right_tnpb,
        left_preset=(
            state.side_preset("left") if is_pair else None
        ),
        right_preset=(
            state.side_preset("right") if is_pair else None
        ),
        on_target_model=on_otm,
        left_on_target_model=left_on_otm,
        right_on_target_model=right_on_otm,
        off_target_model=off_otm,
        left_off_target_model=left_otm,
        right_off_target_model=right_otm,
        reference_only_model=ref_otm,
        left_reference_only_model=left_ref,
        right_reference_only_model=right_ref,
        left_pam_motif=left_pam_motif,
        right_pam_motif=right_pam_motif,
        left_pam_side=left_pam_side,
        right_pam_side=right_pam_side,
        left_require_pam=left_require_pam,
        right_require_pam=right_require_pam,
        max_mismatch=max_mismatch,
        max_bulge=max_bulge,
        max_memory_mode=memory_mode,
        max_memory_mb=memory_limit,
        timeout_s=search_timeout_s(state),
        pam_mode=pam_mode,
        seed_len=state.int_value("seed_len", "12") or 12,
        gc_min=float(state.value("gc_min", "40") or 40),
        gc_max=float(state.value("gc_max", "70") or 70),
        filter_hard=state.bool_value("filter_hard", False),
        mode=mode,
        preset=preset_key,
        pam_motif=pam or "GG",
        pam_side=pam_side,
        require_pam=(
            False if is_pair else bool(state.require_pam)
        ),
        engine=state.value("engine", "auto"),
        index_path=state.value("index_path"),
        genome_build=state.value("genome_build"),
        pair_rank_policy=pair_rank_policy,
    )

def readiness_errors(state: WorkbenchFormState) -> List[str]:
    errors: List[str] = []
    if state.is_bed_mode():
        regions = state.value("bed_regions")
        if not regions:
            errors.append("BED Regions file is required")
        elif not os.path.isfile(regions):
            errors.append("BED Regions not found: %s" % regions)
    else:
        search_fasta = state.value("search_fasta")
        if not search_fasta:
            errors.append("Search FASTA is required")
        elif not os.path.isfile(search_fasta):
            errors.append("Search FASTA not found: %s" % search_fasta)

    genome_fasta = state.value("genome_fasta")
    if not genome_fasta:
        errors.append("Genome FASTA is required")
    elif not os.path.isfile(genome_fasta):
        errors.append("Genome FASTA not found: %s" % genome_fasta)

    mask_fasta = state.value("mask_fasta")
    if mask_fasta and not os.path.isfile(mask_fasta):
        errors.append("Mask FASTA not found: %s" % mask_fasta)

    annotation = state.value("annotation")
    if annotation and not os.path.isfile(annotation):
        errors.append("Annotation GFF3 not found: %s" % annotation)

    if state.is_pair():
        _policy, missing = pair_rank_policy_values(state)
        if missing:
            errors.append(
                "PairRank policy values required: %s"
                % ", ".join(missing)
            )

    try:
        resolved_memory_limit(state)
    except ValueError as exc:
        errors.append("Memory limit: %s" % exc)

    try:
        search_timeout_s(state)
    except ValueError as exc:
        errors.append("Search timeout: %s" % exc)

    if errors:
        return errors
    try:
        build_pattern_spec(state).validate()
    except Exception as exc:
        errors.append("Pattern: %s" % exc)
    return errors


def side_preset_updates(preset_key: str, side: str = "target") -> Dict[str, Any]:
    """Field values the per-side ``Apply`` button writes for one TAM side."""
    motif_key, flank_key, side_key = SIDE_FIELD_KEYS.get(
        side, SIDE_FIELD_KEYS["target"])
    preset = get_preset(preset_key or "custom")
    updates: Dict[str, Any] = {
        motif_key: preset.get("pam") or "",
        flank_key: str(preset["spacer_len"]) if preset.get("spacer_len") else "",
        side_key: (
            pam_side_to_side(preset.get("pam_side"))
            if preset.get("pam_side") else ""
        ),
        SIDE_REQUIRE_PAM_KEYS.get(side, "require_pam"): bool(
            preset.get("pam_required")),
        "pam_mode": preset.get("pam_mode") or "custom",
    }
    if preset.get("nuclease"):
        updates["nuclease"] = preset["nuclease"]
    if preset.get("tnpb_subtype"):
        updates["tnpb_subtype"] = preset["tnpb_subtype"]
    return updates


def side_model_options(preset_key: str) -> Dict[str, Any]:
    """Candidate and default model names for one side's preset."""
    preset = get_preset(preset_key or "custom")
    nuclease = (preset.get("nuclease") or "custom").lower()
    on_values = list(model_choices_for_preset(nuclease, "on_target"))
    off_values = list(model_choices_for_preset(nuclease, "off_target"))
    preferred = DEFAULT_ON_TARGET_MODELS.get(nuclease)
    if not on_values:
        on_values = ["void"]
        preferred = None
    if not off_values:
        off_values = ["void"]
    return {
        "nuclease": nuclease,
        "on_target": on_values,
        "off_target": off_values,
        "on_target_default": preferred or on_values[0],
        "on_target_preferred": preferred,
        "off_target_default": off_values[0],
    }


def resolve_side_model_selection(
    current: str,
    options: List[str],
    preferred: Optional[str] = None,
) -> Optional[str]:
    """Return the value a side model picker must be reset to, else ``None``."""
    selected = split_model_selection(current)
    if not selected or any(model not in options for model in selected):
        return preferred or options[0]
    if preferred and selected == ["auto"]:
        return preferred
    return None


def active_side_updates(state: WorkbenchFormState) -> Dict[str, Any]:
    """Field values ``Use for Run`` writes when the active side changes."""
    side = state.active_side
    if side not in state.side_presets:
        return {}
    preset = get_preset(state.side_presets[side] or "custom")
    updates: Dict[str, Any] = {
        SIDE_REQUIRE_PAM_KEYS.get(side, "require_pam"): bool(
            preset.get("pam_required")),
        "pam_mode": preset.get("pam_mode") or "custom",
    }
    if preset.get("nuclease"):
        updates["nuclease"] = preset["nuclease"]
    if preset.get("tnpb_subtype"):
        updates["tnpb_subtype"] = preset["tnpb_subtype"]
    return updates
