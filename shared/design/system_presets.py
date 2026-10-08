#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""System presets for guide design modes.

The GUI/CLI keeps two mutually exclusive modes:
  free   - current behavior, all fields are manual
  preset - a selected CRISPR system fills recommended values

Presets never lock the user out of editing fields. They only provide
defaults and the rule summary used by scoring and reporting.
"""

import copy

import scoring.non_cas9_rules as non_cas9_rules


PAM_MODES = {
    "strict_ngg": {
        "label": "Strict NGG",
        "motif": "NGG",
    },
    "guidescan2_nrg": {
        "label": "GuideScan2 NRG (NGG + NAG)",
        "motif": "NRG",
    },
    "custom": {
        "label": "Custom PAM",
        "motif": "",
    },
}


SYSTEM_PRESETS = {
    "custom": {
        "label": "Custom / free input",
        "nuclease": "custom",
        "tnpb_subtype": "unknown",
        "spacer_len": None,
        "pam": "",
        "pam_mode": "custom",
        "pam_side": "",
        "seed_start": None,
        "seed_end": None,
        "target_type": "dna",
        "score_profile": "custom",
        "prefer": "",
        "pam_required": False,
        "description": "No system rules are applied.",
    },
    "cas9": {
        "label": "SpCas9",
        "nuclease": "cas9",
        "tnpb_subtype": "unknown",
        "spacer_len": 20,
        "pam": "NGG",
        "pam_mode": "strict_ngg",
        "pam_side": "3prime",
        "seed_start": 10,
        "seed_end": 20,
        "target_type": "dna",
        "score_profile": "cas9",
        "prefer": "gc",
        "pam_required": True,
        "description": "20 nt spacer, NGG 3' PAM, PAM-proximal seed.",
        "rule_key": "cas9",
    },
    "cas12a": {
        "label": "Cas12a / LbCpf1",
        "nuclease": "cas12a",
        "tnpb_subtype": "unknown",
        "spacer_len": 24,
        "pam": "TTTN",
        "pam_side": "5prime",
        "seed_start": 1,
        "seed_end": 6,
        "target_type": "dna",
        "score_profile": "cas12a",
        "prefer": "gc",
        "pam_required": True,
        "description": "24 nt spacer, TTTN 5' PAM (CHOPCHOP Cpf1 default), seed positions 1-6.",
        "rule_key": "cas12a",
    },
    "cas12b": {
        "label": "Cas12b / AapCas12b",
        "nuclease": "cas12b",
        "tnpb_subtype": "unknown",
        "spacer_len": 20,
        "pam": "TTN",
        "pam_side": "5prime",
        "seed_start": 1,
        "seed_end": 20,
        "target_type": "dna",
        "score_profile": "cas12b",
        "prefer": "gc",
        "pam_required": True,
        "description": "20 nt spacer, TTN 5' PAM, mismatches broadly tolerated.",
        "rule_key": "cas12b",
    },
    "cas13": {
        "label": "Cas13 (CHOPCHOP)",
        "nuclease": "cas13",
        "tnpb_subtype": "unknown",
        "spacer_len": 27,
        "pam": "H",
        "pam_side": "5prime",
        "seed_start": None,
        "seed_end": None,
        "target_type": "rna",
        "score_profile": "cas13",
        "prefer": "u_rich",
        "pam_required": True,
        "description": "27 nt spacer, 5' non-G flanking site (H) per CHOPCHOP Cas13 default.",
        "rule_key": "cas13",
        "direct_repeat": "GATTTAGACTACCCCAAAAACGAAGGGGACTAAAAC",
    },
    "tnpb": {
        "label": "TnpB / omegaRNA",
        "nuclease": "tnpb",
        "tnpb_subtype": "unknown",
        "spacer_len": None,
        "pam": "",
        "pam_mode": "custom",
        "pam_side": "",
        "seed_start": None,
        "seed_end": None,
        "target_type": "dna",
        "score_profile": "tnpb",
        "prefer": "",
        "pam_required": False,
        "description": "Generic TnpB omegaRNA design; no TAM is assumed. "
                       "Pick the ISDra2 subtype to require the classic "
                       "5' TTGAT TAM.",
        "rule_key": "tnpb",
    },
}


#: TnpB subtypes selectable inside the single ``tnpb`` preset.
TNPB_SUBTYPES = ("unknown", "isdra2")

#: Display labels for the TnpB subtype selector.
TNPB_SUBTYPE_LABELS = {
    "unknown": "Unknown",
    "isdra2": "ISDra2",
}

#: Subtype-specific TAM defaults. A subtype with a fixed TAM enables the
#: PAM requirement automatically; a subtype without an entry keeps the
#: generic no-TAM behavior and the user fills the TAM fields by hand.
TNPB_SUBTYPE_TAMS = {
    "isdra2": {"pam": "TTGAT", "pam_side": "5prime"},
}


def resolve_preset_pam(preset_key, tnpb_subtype=None):
    """Return ``(pam, pam_side, pam_required)`` for a preset + subtype.

    The preset's own PAM wins when it defines one.  The generic ``tnpb``
    preset has no PAM; selecting a TnpB subtype with a fixed TAM (ISDra2)
    turns that TAM on without adding a second top-level preset.
    """

    preset = get_preset(preset_key)
    pam = preset.get("pam") or ""
    pam_side = preset.get("pam_side") or ""
    required = bool(preset.get("pam_required"))
    if pam:
        return pam, pam_side, required
    if (preset.get("nuclease") or "").lower() == "tnpb":
        override = TNPB_SUBTYPE_TAMS.get(
            str(tnpb_subtype or "").strip().lower()
        )
        if override:
            return override["pam"], override["pam_side"], True
    return pam, pam_side, required


def resolve_run_nuclease(nuclease, preset_key):
    """Return the nuclease a run should report for the chosen system.

    ``cas9`` is the form and dataclass default, so a real non-cas9 preset
    fills it in -- a TnpB side must never be reported as SpCas9 just because
    the nuclease field was left untouched.  An explicit non-cas9 choice, for
    example a batch ``shared.nuclease``, still wins over the default SpCas9
    preset, and the custom preset keeps whatever the caller asked for.
    """

    requested = str(nuclease or "").strip().lower()
    preset_nuclease = str(
        get_preset(preset_key).get("nuclease") or ""
    ).strip().lower()
    if preset_nuclease in ("", "custom"):
        return nuclease
    if requested in ("", "cas9") or preset_nuclease != "cas9":
        return preset_nuclease
    return nuclease


MODES = {
    "free": {
        "label": "Free mode",
        "description": "Current behavior. All fields are manual and no preset is applied.",
    },
    "preset": {
        "label": "Preset mode",
        "description": "A selected system preset fills recommended values; fields stay editable.",
    },
}


def preset_keys():
    return list(SYSTEM_PRESETS.keys())


def get_preset(key):
    key = key or "custom"
    if key not in SYSTEM_PRESETS:
        key = "custom"
    return copy.deepcopy(SYSTEM_PRESETS[key])


def preset_label(key):
    return get_preset(key)["label"]


def preset_choices():
    return [(key, SYSTEM_PRESETS[key]["label"]) for key in SYSTEM_PRESETS]


def normalize_pam_mode(mode, pam=None):
    """Return a supported PAM mode, inferring strict NGG when possible."""
    key = str(mode or "").strip().lower()
    if key in PAM_MODES:
        return key
    pam = str(pam or "").upper().replace("U", "T")
    if pam == "NRG":
        return "guidescan2_nrg"
    if pam == "NGG":
        return "strict_ngg"
    return "custom"


def pam_motif_for_mode(mode, fallback_pam=""):
    """Return the full search motif for a PAM compatibility mode."""
    key = normalize_pam_mode(mode, fallback_pam)
    return PAM_MODES[key]["motif"] or fallback_pam


def pam_mode_label(mode):
    key = normalize_pam_mode(mode)
    return PAM_MODES.get(key, PAM_MODES["custom"])["label"]


def apply_preset(key, current=None):
    """Fill only empty/None values from the selected preset.

    Existing user-provided values are preserved so free input is never
    overwritten unless a caller explicitly requests it.
    """
    preset = get_preset(key)
    merged = dict(current or {})
    for field, value in preset.items():
        if field == "label" or field == "description":
            merged.setdefault(field, value)
            continue
        old = merged.get(field)
        if old is None or old == "" or old == "unknown":
            merged[field] = value
    merged["preset"] = key
    return merged


def rule_summary(key):
    preset = get_preset(key)
    if key == "custom":
        return "custom"
    parts = [
        preset.get("pam") or "no-PAM",
        pam_mode_label(preset.get("pam_mode", "custom")),
        preset.get("pam_side") or "any-side",
        "%s nt spacer" % preset["spacer_len"] if preset.get("spacer_len") else "variable spacer",
        preset.get("target_type", "dna"),
    ]
    if preset.get("seed_start") and preset.get("seed_end"):
        parts.append("seed %s-%s" % (preset["seed_start"], preset["seed_end"]))
    if preset.get("prefer"):
        parts.append("prefer %s" % preset["prefer"])
    source = non_cas9_rules.rule_source(key)
    if source:
        parts.append("source %s" % source)
    return ",".join(parts)


def mode_choices():
    return [(key, MODES[key]["label"]) for key in MODES]
