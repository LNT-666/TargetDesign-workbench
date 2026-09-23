#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared guide/motif scoring helpers.

The off-target score follows the CFD aggregation used by GuideScan2:
    1 / (1 + sum(CFD(o, g))).
The on-target score uses CROPSR's published Doench/Cas9 logistic model when the
input sequence is a 30mer, and falls back to a deterministic feature heuristic
for the variable-length motif windows produced by this toolkit.
"""

import math
import json
import urllib.request
from collections.abc import Mapping
from design.system_presets import get_preset, SYSTEM_PRESETS
import scoring.cas13_scoring as cas13_scoring
import scoring.deep_models as deep_models
import scoring.non_cas9_rules as non_cas9_rules
import scoring.tiger_model as tiger_model
import scoring.tnpb_scoring as tnpb_scoring


_DNA_COMPLEMENT = {
    "A": "T",
    "C": "G",
    "G": "C",
    "T": "A",
    "U": "A",
    "N": "N",
    "-": "-",
}


PRESET_ON_TARGET_MODELS = {
    "cas9": ("cropsr",),
    "cas12a": ("rules", "deepcas12a", "deepcpf1"),
    "cas12b": ("rules",),
    "cas13": ("rna_rules", "tiger"),
    "tnpb": ("omega", "teep"),
}

PRESET_OFF_TARGET_MODELS = {
    "cas9": ("cfd", "crispr_m", "deepcrispr", "crispai"),
    "cas12a": ("rules",),
    "cas12b": ("rules",),
    "cas13": ("pfs", "identity", "tiger"),
    "tnpb": ("identity",),
}

TRADITIONAL_MODELS = frozenset({
    "cfd",
    "identity",
    "omega",
    "pfs",
    "rna_rules",
    "rules",
})

MODEL_PROTEIN_GROUPS = {
    "cfd": "cas9",
    "crispr_m": "cas9",
    "deepcrispr": "cas9",
    "crispai": "cas9",
    "cropsr": "cas9",
    "deepcas12a": "cas12a",
    "deepcpf1": "cas12a",
    "rna_rules": "cas13",
    "pfs": "cas13",
    "tiger": "cas13",
    "omega": "tnpb",
    "teep": "tnpb",
    "identity": "general",
    "rules": "general",
}

PROTEIN_GROUP_LABELS = {
    "cas9": "Cas9",
    "cas12a": "Cas12a",
    "cas13": "Cas13",
    "tnpb": "TnpB",
    "general": "General",
}


def _ordered_model_union(groups):
    models = []
    for group in groups:
        for model in group:
            if model not in models:
                models.append(model)
    if "auto" in models:
        models = [model for model in models if model != "auto"] + ["auto"]
    return tuple(models)


ALL_ON_TARGET_MODELS = _ordered_model_union(
    PRESET_ON_TARGET_MODELS.values()
)
ALL_OFF_TARGET_MODELS = _ordered_model_union(
    PRESET_OFF_TARGET_MODELS.values()
)


def model_choices_for_preset(preset_key, role):
    """Return the model choices exposed by a preset or by custom mode."""
    preset_key = (preset_key or "custom").lower()
    role = (role or "").lower()
    if role == "on_target":
        mapping = PRESET_ON_TARGET_MODELS
        all_models = ALL_ON_TARGET_MODELS
    elif role == "off_target":
        mapping = PRESET_OFF_TARGET_MODELS
        all_models = ALL_OFF_TARGET_MODELS
    else:
        raise ValueError("unknown model role: %s" % role)
    if preset_key == "custom":
        return list(all_models)
    return list(mapping.get(preset_key, ()))


# CFD mismatch table from the Doench et al. / CRISPRitz CFD score. Rows are
# positions 1..20. Within each row, values follow:
#   guide A,C,G,U x target DNA A,C,G,T.
# Exact matches are handled separately and are equivalent to 1.0.
CFD_MM_ROWS = [
    [1, 0.857142857, 1, 1, 1, 1, 0.913043478, 1, 0.9, 0.714285714, 1, 1, 1, 0.857142857, 0.956521739, 1],
    [1, 0.785714286, 0.8, 0.727272727, 0.727272727, 1, 0.695652174, 0.909090909, 0.846153846, 0.692307692, 1, 0.636363636, 0.846153846, 0.857142857, 0.84, 1],
    [1, 0.428571429, 0.611111111, 0.705882353, 0.866666667, 1, 0.5, 0.6875, 0.75, 0.384615385, 1, 0.5, 0.714285714, 0.428571429, 0.5, 1],
    [1, 0.352941176, 0.625, 0.636363636, 0.842105263, 1, 0.5, 0.8, 0.9, 0.529411765, 1, 0.363636364, 0.476190476, 0.647058824, 0.625, 1],
    [1, 0.5, 0.72, 0.363636364, 0.571428571, 1, 0.6, 0.636363636, 0.866666667, 0.785714286, 1, 0.3, 0.5, 1, 0.64, 1],
    [1, 0.454545455, 0.714285714, 0.714285714, 0.928571429, 1, 0.5, 0.928571429, 1, 0.681818182, 1, 0.666666667, 0.866666667, 0.909090909, 0.571428571, 1],
    [1, 0.4375, 0.705882353, 0.4375, 0.75, 1, 0.470588235, 0.8125, 1, 0.6875, 1, 0.571428571, 0.875, 0.6875, 0.588235294, 1],
    [1, 0.428571429, 0.733333333, 0.428571429, 0.65, 1, 0.642857143, 0.875, 1, 0.615384615, 1, 0.625, 0.8, 1, 0.733333333, 1],
    [1, 0.571428571, 0.666666667, 0.6, 0.857142857, 1, 0.619047619, 0.875, 0.642857143, 0.538461538, 1, 0.533333333, 0.928571429, 0.923076923, 0.619047619, 1],
    [1, 0.333333333, 0.555555556, 0.882352941, 0.866666667, 1, 0.388888889, 0.941176471, 0.933333333, 0.4, 1, 0.8125, 0.857142857, 0.533333333, 0.5, 1],
    [1, 0.4, 0.65, 0.307692308, 0.75, 1, 0.25, 0.307692308, 1, 0.428571429, 1, 0.384615385, 0.75, 0.666666667, 0.4, 1],
    [1, 0.263157895, 0.722222222, 0.333333333, 0.714285714, 1, 0.444444444, 0.538461538, 0.933333333, 0.529411765, 1, 0.384615385, 0.8, 0.947368421, 0.5, 1],
    [1, 0.210526316, 0.652173913, 0.3, 0.384615385, 1, 0.136363636, 0.7, 0.923076923, 0.421052632, 1, 0.3, 0.692307692, 0.789473684, 0.260869565, 1],
    [1, 0.214285714, 0.466666667, 0.533333333, 0.35, 1, 0, 0.733333333, 0.75, 0.428571429, 1, 0.266666667, 0.619047619, 0.285714286, 0, 1],
    [1, 0.272727273, 0.65, 0.2, 0.222222222, 1, 0.05, 0.066666667, 0.941176471, 0.272727273, 1, 0.142857143, 0.578947368, 0.272727273, 0.05, 1],
    [1, 0, 0.192307692, 0, 1, 1, 0.153846154, 0.307692308, 1, 0, 1, 0, 0.909090909, 0.666666667, 0.346153846, 1],
    [1, 0.176470588, 0.176470588, 0.133333333, 0.466666667, 1, 0.058823529, 0.466666667, 0.933333333, 0.235294118, 1, 0.25, 0.533333333, 0.705882353, 0.117647059, 1],
    [1, 0.19047619, 0.4, 0.5, 0.538461538, 1, 0.133333333, 0.642857143, 0.692307692, 0.476190476, 1, 0.666666667, 0.666666667, 0.428571429, 0.333333333, 1],
    [1, 0.206896552, 0.375, 0.538461538, 0.428571429, 1, 0.125, 0.461538462, 0.714285714, 0.448275862, 1, 0.666666667, 0.285714286, 0.275862069, 0.25, 1],
    [1, 0.227272727, 0.764705882, 0.6, 0.5, 1, 0.058823529, 0.3, 0.9375, 0.428571429, 1, 0.7, 0.5625, 0.090909091, 0.176470588, 1],
]


PAM_SCORES = {
    "AA": 0.0,
    "AC": 0.0,
    "AG": 0.259259259,
    "AT": 0.0,
    "CA": 0.0,
    "CC": 0.0,
    "CG": 0.107142857,
    "CT": 0.0,
    "GA": 0.069444444,
    "GC": 0.022222222,
    "GG": 1.0,
    "GT": 0.016129032,
    "TA": 0.0,
    "TC": 0.0,
    "TG": 0.038961039,
    "TT": 0.0,
}

BULGE_PENALTY_VERSION = "conservative_bulge_v1"


def _pam_score_key(pam):
    """CFD uses the two PAM bases adjacent to the spacer (GG in NGG)."""
    if pam is None:
        return ""
    key = str(pam).upper().replace("U", "T").strip()
    return key[-2:] if len(key) >= 2 else key


def _coerce_offtarget(item):
    """Return ``(aligned_target, pam, metadata)`` for old and rich hits."""
    if isinstance(item, Mapping):
        metadata = dict(item)
        target = (
            metadata.get("aligned_target")
            or metadata.get("target_segment")
            or metadata.get("off_spacer")
            or ""
        )
        pam = metadata.get("pam") or metadata.get("pam_seq") or ""
        metadata["rna_bulges"] = int(metadata.get("rna_bulges") or 0)
        metadata["dna_bulges"] = int(metadata.get("dna_bulges") or 0)
        metadata["indel"] = max(
            int(metadata.get("indel") or 0),
            metadata["rna_bulges"] + metadata["dna_bulges"],
        )
        metadata["is_bulge"] = metadata["indel"] > 0
        return str(target), str(pam), metadata
    if isinstance(item, (tuple, list)):
        target = item[0] if len(item) > 0 else ""
        pam = item[1] if len(item) > 1 else ""
        return str(target or ""), str(pam or ""), {
            "indel": 0,
            "rna_bulges": 0,
            "dna_bulges": 0,
            "is_bulge": False,
        }
    return "", "", {
        "indel": 0,
        "rna_bulges": 0,
        "dna_bulges": 0,
        "is_bulge": False,
    }


def _split_bulge_hits(offtargets):
    substitution_pairs = []
    bulge_hits = []
    for item in offtargets or []:
        target, pam, metadata = _coerce_offtarget(item)
        if metadata.get("is_bulge"):
            bulge_hits.append((target, pam, metadata))
        else:
            substitution_pairs.append((target, pam))
    return substitution_pairs, bulge_hits


def _bulge_risk(guide, hit):
    """Conservative, explicitly uncalibrated penalty for one bulge hit."""
    target, _pam, metadata = hit
    guide = str(guide or "").upper().replace("U", "T")
    target = str(target or "").upper().replace("U", "T")
    positions = [
        (a, b) for a, b in zip(guide, target)
        if a != "-" and b != "-"
    ]
    if positions:
        similarity = (
            sum(1 for a, b in positions if a == b) / float(len(positions))
        )
    else:
        similarity = 0.0
    rna = int(metadata.get("rna_bulges") or 0)
    dna = int(metadata.get("dna_bulges") or 0)
    unknown = max(0, int(metadata.get("indel") or 0) - rna - dna)
    penalty = (0.5 ** rna) * (0.5 ** dna) * (0.5 ** unknown)
    penalty *= 0.75 ** int(metadata.get("mismatch") or 0)
    return max(0.01, min(1.0, similarity * penalty))


# CROPSR's published implementation of the Doench Cas9 on-target score.
CROPSR_INTERCEPT = 0.59763615
CROPSR_LOW_GC = -0.2026259
CROPSR_HIGH_GC = -0.1665878
CROPSR_MODEL_NOTE = (
    "Full published CROPSR/Doench logistic coefficients, not a reduced "
    "heuristic; sequence format is 4 nt upstream + 20 nt guide + NGG + "
    "3 nt downstream."
)

CROPSR_FIRST_ORDER = [
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, -0.2753771, -0.3238875, 0.0, 0.17212887, 0.0, 0.0, 0.0, -0.1006662, 0.0, 0.0, 0.0, -0.2018029, 0.24595663,
    0.03644004, 0.0, 0.09837684, 0.0, 0.0, 0.0, -0.7411813, -0.3932644, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
    0.0, 0.0, 0.0, 0.0, -0.466099, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.08537695, 0.0, -0.013814, 0.0,
    0.27262051, -0.2859442, 0.1190226, 0.0, 0.09745459, 0.0, 0.0, -0.1755462, 0.0, 0.0, -0.3457955, -0.6780964, 0.22508903, 0.0, -0.5077941, 0.0, 0.0, -0.054307, 0.0, -0.4173736,
    0.0, -0.0907126, 0.0, 0.37989937, 0.0, -0.5305673, 0.05782332, 0.0, 0.0, -0.8770074, 0.0, 0.0, 0.0, -0.4031022, -0.8762358, 0.27891626, -0.0773007, -0.2216372, 0.28793562, 0.0,
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.11787758, 0.0, -0.6890167, 0.0, 0.0, -0.1604453, 0.0, 0.0, 0.0, 0.0, 0.38634258,
]

CROPSR_SECOND_ORDER = [
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, -0.6257787, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.30004332, 0.0,
    -0.8348362, 0.0, 0.0, 0.0, 0.76062777, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, -0.4908167, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
    0.7092612, -0.5868739, 0.49629861, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, -1.5169074, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, -0.3345637, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
    0.76384993, 0.0, -0.5370252, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
    0.0, 0.0, 0.0, -0.7981461, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.35318325, 0.0, 0.0, 0.0, 0.0, 0.0,
    0.0, 0.0, 0.0, -0.6668087, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, -0.3672668, 0.0, 0.0, 0.74807209, 0.0, 0.0, 0.0, 0.0, 0.0,
    0.0, 0.0, 0.56820913, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.32907207, -0.8364568, 0.0, 0.0, -0.7822076, 0.0, 0.0, 0.0, 0.0,
    0.0, 0.0, -1.029693, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
    0.0, -0.4632077, 0.0, 0.85619782, 0.0, 0.0, 0.0, 0.0, -0.5794924, 0.0, 0.0, 0.64907554, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, -0.0773007, 0.0, 0.0, 0.0, -0.2216372, 0.0, 0.0, 0.0, 0.28793562, 0.0, 0.0, 0.0, 0.0,
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.11787758, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
    0.0, 0.0, 0.0, -0.69774,
]


_GUIDE_BASE_INDEX = {"A": 0, "C": 1, "G": 2, "U": 3, "T": 3}
_OFF_BASE_INDEX = {"A": 0, "C": 1, "G": 2, "T": 3, "U": 3}


NUCLEASE_PRESET_MAP = {
    "cas9": "cas9",
    "cas12a": "cas12a",
    "cas12b": "cas12b",
    "cas14a": "cas14a",
    "cas13": "cas13",
    "tnpb": "tnpb",
}


def _dna_complement(base):
    return _DNA_COMPLEMENT.get(base.upper(), "N")


def cfd_score(guide, off_spacer, pam=None):
    """Return the single off-target CFD score for one guide/off-target pair."""
    guide = guide.upper().replace("T", "U")
    off_spacer = off_spacer.upper().replace("T", "U")

    if len(guide) != len(off_spacer):
        return 0.0
    if len(guide) == 0:
        return 0.0

    score = 1.0
    for i, (guide_base, off_base) in enumerate(zip(guide, off_spacer)):
        if guide_base == off_base:
            continue
        if i >= len(CFD_MM_ROWS):
            continue
        g_idx = _GUIDE_BASE_INDEX.get(guide_base)
        o_idx = _OFF_BASE_INDEX.get(_dna_complement(off_base))
        if g_idx is None or o_idx is None:
            continue
        score *= CFD_MM_ROWS[i][g_idx * 4 + o_idx]

    if pam:
        score *= PAM_SCORES.get(_pam_score_key(pam), 0.0)

    return max(0.0, min(1.0, score))


def aggregate_off_target_specificity(guide, off_pairs, assume_one_primary=True):
    """Aggregate CFD scores using GuideScan2's specificity formula."""
    if not off_pairs:
        return 1.0

    cfds = []
    has_perfect = False
    for off_spacer, pam in off_pairs:
        cfd = cfd_score(guide, off_spacer, pam)
        cfds.append(cfd)
        if cfd >= 0.999999:
            has_perfect = True

    total = sum(cfds)
    if assume_one_primary and has_perfect:
        total = max(0.0, total - 1.0)

    return 1.0 / (1.0 + total)


def identity_off_target_specificity(guide, off_pairs, assume_one_primary=True):
    """Non-Cas9 fallback based on sequence identity rather than CFD."""
    if not off_pairs:
        return 1.0

    total = 0.0
    has_perfect = False
    guide = guide.upper().replace("U", "T")
    for off_spacer, _ in off_pairs:
        off_spacer = off_spacer.upper().replace("U", "T")
        n = min(len(guide), len(off_spacer))
        if n == 0:
            continue
        matches = sum(1 for a, b in zip(guide[:n], off_spacer[:n]) if a == b)
        similarity = matches / n
        total += similarity
        if similarity >= 0.999999:
            has_perfect = True

    if assume_one_primary and has_perfect:
        total = max(0.0, total - 1.0)

    return 1.0 / (1.0 + total)


def cropsr_on_target_score(seq30):
    """CROPSR/Doench score for a 30mer input.

    The expected format is 4 nt upstream + 20 nt guide + NGG + 3 nt downstream.
    Returns None for non-ACGT sequences that cannot be scored by this model.
    """
    if len(seq30) != 30:
        return None
    seq = seq30.upper()
    if not all(base in "ACGT" for base in seq):
        return None

    first = 0.0
    for pos, base in enumerate(seq):
        idx = pos * 4 + {"A": 0, "T": 1, "C": 2, "G": 3}[base]
        first += CROPSR_FIRST_ORDER[idx]

    second = 0.0
    base_idx = {"A": 0, "T": 1, "C": 2, "G": 3}
    for pos in range(29):
        b1 = base_idx[seq[pos]]
        b2 = base_idx[seq[pos + 1]]
        idx = pos * 16 + b1 * 4 + b2
        second += CROPSR_SECOND_ORDER[idx]

    gc_count = seq.count("G") + seq.count("C")
    gc_content = gc_count / 30.0
    gc_adjust = CROPSR_LOW_GC if gc_content < 0.5 else CROPSR_HIGH_GC
    z = first + second + CROPSR_INTERCEPT + gc_adjust
    try:
        return 1.0 / (1.0 + math.exp(-z))
    except OverflowError:
        return 1.0 if z > 0 else 0.0


def best_cropsr_on_target_score(seq):
    """Score a guide window with CROPSR.

    Uses the exact 30mer when available; for longer motif windows, slides a
    30mer window and keeps the best CROPSR score.
    """
    seq = seq.upper().replace("U", "T")
    candidates = []
    if len(seq) == 30:
        score = cropsr_on_target_score(seq)
        if score is not None:
            candidates.append(score)
    elif len(seq) > 30:
        for start in range(0, len(seq) - 29):
            score = cropsr_on_target_score(seq[start:start + 30])
            if score is not None:
                candidates.append(score)
    return max(candidates) if candidates else None


def _max_homopolymer_run(seq):
    best = 1
    current = 1
    for i in range(1, len(seq)):
        if seq[i] == seq[i - 1]:
            current += 1
            best = max(best, current)
        else:
            current = 1
    return best


def heuristic_on_target_score(seq):
    """Deterministic fallback for variable-length motif windows."""
    seq = seq.upper()
    if not seq:
        return 0.0

    length = len(seq)
    gc = (seq.count("G") + seq.count("C")) / length
    gc_score = max(0.0, 1.0 - abs(gc - 0.50) / 0.30)

    seed_len = min(8, length)
    seed = seq[-seed_len:]
    seed_gc = (seed.count("G") + seed.count("C")) / seed_len
    seed_score = max(0.0, 1.0 - abs(seed_gc - 0.50) / 0.50)

    run_score = max(0.0, 1.0 - (_max_homopolymer_run(seq) - 3) / 6.0)

    if length >= 2:
        kmer_count = len({seq[i:i + 2] for i in range(length - 1)})
        complexity = min(1.0, kmer_count / min(16, length - 1))
    else:
        complexity = 1.0

    return max(0.0, min(1.0, 0.35 * gc_score + 0.25 * seed_score + 0.20 * run_score + 0.20 * complexity))


def filter_hints(gc_content, self_comp, gc_min=40.0, gc_max=70.0, self_comp_max=4):
    """Return pass/low/high hints for GC and self-complementarity."""
    if gc_content < gc_min:
        gc_hint = "low"
    elif gc_content > gc_max:
        gc_hint = "high"
    else:
        gc_hint = "pass"
    self_comp_hint = "pass" if self_comp <= self_comp_max else "warn"
    return {"gc_hint": gc_hint, "self_comp_hint": self_comp_hint}


def passes_filter(hints, filter_hard=False):
    """Apply hard filtering only when explicitly requested."""
    if not filter_hard:
        return True
    return hints["gc_hint"] == "pass" and hints["self_comp_hint"] == "pass"


def teep_on_target_score(seq):
    """Query TEEP for ISDra2 TnpB editing efficiency (online reference only)."""
    try:
        request = urllib.request.Request(
            "https://www.tnpb.app/",
            data=json.dumps({"input_data": seq.upper()}).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "User-Agent": "TargetDesign-workbench/0.1 (+https://github.com/LNT-666/TargetDesign-workbench)",
            },
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            values = json.loads(response.read().decode("utf-8")).get(seq.upper(), {})
        scores = []
        for key in ("CNN_pred", "RNN_pred"):
            try:
                scores.append(float(values[key]) / 100.0)
            except (TypeError, KeyError, ValueError):
                continue
        if scores:
            return max(0.0, min(1.0, sum(scores) / len(scores)))
    except Exception:
        pass
    return None


def _cas9_on_target_score(seq, model_choice):
    if model_choice == "rules":
        return heuristic_on_target_score(seq), "rules_heuristic"
    if model_choice in ("cropsr", "auto"):
        score = best_cropsr_on_target_score(seq)
        if score is not None:
            model_name = "CROPSR_best30" if len(seq) != 30 else "CROPSR_30mer"
            return score, model_name
    return heuristic_on_target_score(seq), "heuristic"


def _deep_off_target_score(seq, off_pairs, model_choice, assume_one_primary):
    """Score off-targets with a local deep model when it is usable."""
    fallback_notes = {
        "cfd": "本地深度模型不可用，off-target 已回退 CFD 评分",
        "crispr_m_unavailable": "CRISPR-M 模型未就绪，off-target 已回退 CFD 评分",
        "crispr_m_error": "CRISPR-M 预测失败，off-target 已回退 CFD 评分",
        "deepcrispr_unavailable": "DeepCRISPR 模型未就绪，off-target 已回退 CFD 评分",
        "deepcrispr_error": "DeepCRISPR 预测失败，off-target 已回退 CFD 评分",
    }
    choice = (model_choice or "auto").lower()
    if choice == "rules":
        spec = aggregate_off_target_specificity(
            seq, off_pairs, assume_one_primary)
        return spec, "cfd", ""
    if choice == "auto":
        if deep_models.crispr_m_status() == "ready":
            choice = "crispr_m"
        elif deep_models.DeepCrisprPredictor.available():
            choice = "deepcrispr"
        else:
            spec = aggregate_off_target_specificity(
                seq, off_pairs, assume_one_primary)
            return spec, "cfd", fallback_notes["cfd"]
    if choice == "crispr_m":
        if deep_models.crispr_m_status() != "ready":
            spec = aggregate_off_target_specificity(
                seq, off_pairs, assume_one_primary)
            return spec, "crispr_m_unavailable", fallback_notes["crispr_m_unavailable"]
        try:
            spec = deep_models.deep_model_off_target_specificity(
                seq, off_pairs, "crispr_m", assume_one_primary)
            return spec, "crispr_m", ""
        except Exception:
            spec = aggregate_off_target_specificity(
                seq, off_pairs, assume_one_primary)
            return spec, "crispr_m_error", fallback_notes["crispr_m_error"]
    if choice == "deepcrispr":
        if not deep_models.DeepCrisprPredictor.available():
            spec = aggregate_off_target_specificity(
                seq, off_pairs, assume_one_primary)
            return spec, "deepcrispr_unavailable", fallback_notes["deepcrispr_unavailable"]
        try:
            spec = deep_models.deep_model_off_target_specificity(
                seq, off_pairs, "deepcrispr", assume_one_primary)
            return spec, "deepcrispr", ""
        except Exception:
            spec = aggregate_off_target_specificity(
                seq, off_pairs, assume_one_primary)
            return spec, "deepcrispr_error", fallback_notes["deepcrispr_error"]
    return None


def _empty_deep_off_target_columns():
    columns = {
        "crispr_m_off_target": "",
        "deepcrispr_off_target": "",
        "crispai_off_target": "",
    }
    return columns


def specificity_from_off_target_activities(activities, primary_flags,
                                           assume_one_primary=True):
    """Aggregate per-hit contributions with the existing GuideScan2 rule."""
    values = [max(0.0, float(value or 0.0)) for value in activities or []]
    primaries = list(primary_flags or [])
    total = sum(values)
    if assume_one_primary and any(primaries):
        total = max(0.0, total - 1.0)
    return 1.0 / (1.0 + total)


def _off_target_activity_model(
        seq, nuclease, reference_only_model, preset_key, off_target_model):
    """Resolve the model used to produce per-hit activity values."""
    nuclease = (nuclease or "cas9").lower()
    reference_only_model = (reference_only_model or "none").lower()
    preset_key = (preset_key or "custom").lower()
    if preset_key not in SYSTEM_PRESETS:
        preset_key = "custom"
    if preset_key == "custom" and nuclease in NUCLEASE_PRESET_MAP:
        preset_key = NUCLEASE_PRESET_MAP[nuclease]
    if nuclease == "tnpb" and preset_key == "custom":
        preset_key = "tnpb"
    if nuclease == "custom":
        preset_key = "custom"

    choice = _normalize_model_choices(off_target_model, "rules")[0]

    if preset_key in ("cas12a", "cas12b", "cas14a", "cas13"):
        if preset_key == "cas13":
            if choice in ("pfs", "rules"):
                return "cas13_pfs", "cas13_pfs", False
            if choice in ("tiger", "tiger13", "auto"):
                if (tiger_model.TigerPredictor.available()
                        and len(seq) == tiger_model.GUIDE_LEN):
                    return "tiger13", "tiger13", False
                return "cas13_pfs", "cas13_pfs", False
            return ("preset_identity", "preset_cas13", False)
        return ("preset_identity", "preset_%s" % preset_key, False)

    if reference_only_model == "teep" and nuclease == "tnpb":
        return "identity_heuristic", "identity_heuristic", False
    if preset_key == "tnpb":
        return "identity_heuristic", "identity_heuristic", False

    if nuclease == "cas9" or preset_key == "cas9":
        if choice == "rules":
            return "cfd", "cfd", False
        if choice == "auto":
            if deep_models.crispr_m_status() == "ready":
                return "crispr_m", "crispr_m", False
            if deep_models.DeepCrisprPredictor.available():
                return "deepcrispr", "deepcrispr", False
            return "cfd", "cfd", False
        if choice == "crispr_m":
            if deep_models.crispr_m_status() == "ready":
                return "crispr_m", "crispr_m", False
            return "cfd", "crispr_m_unavailable", False
        if choice == "deepcrispr":
            if deep_models.DeepCrisprPredictor.available():
                return "deepcrispr", "deepcrispr", False
            return "cfd", "deepcrispr_unavailable", False
        return "cfd", "cfd", False

    if nuclease == "tnpb":
        return "identity_heuristic", "identity_heuristic", False
    if reference_only_model == "cas9" and nuclease != "custom":
        return "cfd", "cfd_reference_only", True

    if nuclease == "custom":
        if choice in ("auto", "rules", "identity", "identity_heuristic",
                      "nuc_features"):
            return "identity_heuristic", "identity_heuristic", False
        if choice == "cfd":
            return "cfd", "cfd_reference_only", True
        if choice == "crispai":
            return "identity_heuristic", "identity_heuristic", True
        if choice == "crispr_m":
            if deep_models.crispr_m_status() == "ready":
                return "crispr_m", "crispr_m_reference_only", True
            return ("cfd", "crispr_m_unavailable_reference_only", True)
        if choice == "deepcrispr":
            if deep_models.DeepCrisprPredictor.available():
                return "deepcrispr", "deepcrispr_reference_only", True
            return ("cfd", "deepcrispr_unavailable_reference_only", True)
        if choice in ("tiger", "tiger13"):
            if (tiger_model.TigerPredictor.available()
                    and len(seq) == tiger_model.GUIDE_LEN):
                return "tiger13", "tiger13_reference_only", True
            return "cas13_pfs", "cas13_pfs_reference_only", True
        return "identity_heuristic", "%s_unavailable" % choice, True

    return "identity_heuristic", "identity_heuristic", False


def _identity_activity(guide, target, pam, seed_start=None, seed_end=None,
                       seed_penalty=0.25):
    guide = guide.upper().replace("U", "T")
    target = (target or "").upper().replace("U", "T")
    length = min(len(guide), len(target))
    if length == 0:
        return 0.0, False
    matches = sum(
        1 for left, right in zip(guide[:length], target[:length])
        if left == right
    )
    similarity = matches / float(length)
    seed_mm = _count_seed_mismatches(guide, target, seed_start, seed_end)
    if seed_mm:
        similarity *= seed_penalty ** seed_mm
    return similarity, similarity >= 0.999999


def _deep_activity_scores(model_key, guide, substitutions):
    """Score substitution hits in batches while preserving each hit's PAM."""
    if not substitutions:
        return []
    grouped = {}
    for index, (target, pam) in enumerate(substitutions):
        grouped.setdefault(str(pam or ""), []).append((index, target))
    scores = [0.0] * len(substitutions)
    if model_key == "crispr_m":
        predictor = deep_models.CrisprMPredictor.get()
        for pam, items in grouped.items():
            values = predictor.predict_pairs(
                guide, [target for _index, target in items], pam=pam)
            for (index, _target), value in zip(items, values):
                scores[index] = max(0.0, float(value))
    elif model_key == "deepcrispr":
        predictor = deep_models.DeepCrisprPredictor()
        for pam, items in grouped.items():
            values = predictor.predict_pairs(
                guide, [target for _index, target in items], pam=pam)
            for (index, _target), value in zip(items, values):
                scores[index] = max(0.0, float(value))
    else:
        raise ValueError("Unknown deep model: %s" % model_key)
    return scores


def compute_off_target_activities(
        seq, off_targets, nuclease="cas9", tnpb_subtype="unknown",
        reference_only_model=None, preset_key=None, seed_start=None,
        seed_end=None, off_target_model="rules", assume_one_primary=True):
    """Return one pair-activity value per off-target hit.

    Model inference is batched by guide and PAM.  The result is aligned with
    ``off_targets`` and includes the raw contribution plus whether the hit is
    treated as a primary/perfect site by the selected model.  The returned
    ``specificity`` covers substitution hits only; callers adding bulge risk
    should apply that penalty separately, as ``compute_guide_scores`` does.
    """
    seq = (seq or "").upper().replace("U", "T")
    raw_hits = list(off_targets or [])
    activities = [0.0] * len(raw_hits)
    primary_flags = [False] * len(raw_hits)
    substitution_flags = [False] * len(raw_hits)
    substitutions = []
    substitution_indices = []

    for index, item in enumerate(raw_hits):
        target, pam, metadata = _coerce_offtarget(item)
        if metadata.get("is_bulge"):
            activities[index] = _bulge_risk(seq, (target, pam, metadata))
            continue
        substitution_flags[index] = True
        substitution_indices.append(index)
        substitutions.append((target, pam))

    kind, model_name, reference_only = _off_target_activity_model(
        seq, nuclease, reference_only_model, preset_key, off_target_model)

    try:
        if kind == "cfd":
            values = [cfd_score(seq, target, pam)
                      for target, pam in substitutions]
            primaries = [value >= 0.999999 for value in values]
        elif kind == "identity_heuristic":
            identity = [
                _identity_activity(seq, target, pam)
                for target, pam in substitutions
            ]
            values = [value for value, _primary in identity]
            primaries = [primary for _value, primary in identity]
        elif kind == "preset_identity":
            rules = non_cas9_rules.get_rules(preset_key)
            seed_penalty = rules.get("seed_penalty", 0.25) if rules else 0.25
            identity = [
                _identity_activity(
                    seq, target, pam, seed_start, seed_end, seed_penalty)
                for target, pam in substitutions
            ]
            values = [value for value, _primary in identity]
            primaries = [primary for _value, primary in identity]
        elif kind == "cas13_pfs":
            values = []
            primaries = []
            for target, pam in substitutions:
                identity, primary = _identity_activity(seq, target, pam)
                values.append(identity * cas13_scoring._pfs_penalty(pam))
                primaries.append(primary)
        elif kind == "tiger13":
            predictor = tiger_model.TigerPredictor.get()
            target_windows = [
                "N" * tiger_model.CONTEXT_5P + target
                + "N" * tiger_model.CONTEXT_3P
                for target, _pam in substitutions
            ]
            mismatches = []
            for target, _pam in substitutions:
                length = min(len(seq), len(target))
                mismatches.append(sum(
                    1 for left, right in zip(seq[:length], target[:length])
                    if left != right
                ))
            lfc = predictor.predict_lfc_for_targets(seq, target_windows)
            if lfc is None:
                raise RuntimeError("TIGER returned no off-target scores")
            calibrated = predictor._calibrate(lfc, mismatches)
            values = [
                min(1.0, max(0.0, float(value)))
                for value in predictor._score(calibrated)
            ]
            primaries = [int(value) == 0 for value in mismatches]
        else:
            values = _deep_activity_scores(kind, seq, substitutions)
            primaries = [value >= 0.999999 for value in values]
    except Exception:
        if kind == "crispr_m":
            model_name = "crispr_m_error"
            kind = "cfd"
        elif kind == "deepcrispr":
            model_name = "deepcrispr_error"
            kind = "cfd"
        elif kind in ("tiger13",):
            model_name = "cas13_pfs"
            kind = "cas13_pfs"
        else:
            raise
        if reference_only and model_name.endswith("_reference_only"):
            pass
        elif reference_only:
            model_name += "_reference_only"
        if kind == "cas13_pfs":
            values = []
            primaries = []
            for target, pam in substitutions:
                identity, primary = _identity_activity(seq, target, pam)
                values.append(identity * cas13_scoring._pfs_penalty(pam))
                primaries.append(primary)
        else:
            values = [cfd_score(seq, target, pam)
                      for target, pam in substitutions]
            primaries = [value >= 0.999999 for value in values]

    for index, value, primary in zip(
            substitution_indices, values, primaries):
        activities[index] = float(value)
        primary_flags[index] = bool(primary)

    substitution_activities = [
        activities[index] for index in substitution_indices
    ]
    substitution_primaries = [
        primary_flags[index] for index in substitution_indices
    ]
    specificity = specificity_from_off_target_activities(
        substitution_activities, substitution_primaries,
        assume_one_primary=assume_one_primary)
    return {
        "activities": activities,
        "primary": primary_flags,
        "substitution": substitution_flags,
        "specificity": specificity,
        "model": model_name,
        "reference_only": reference_only,
    }


def _count_seed_mismatches(guide, off_spacer, seed_start, seed_end):
    if seed_start is None or seed_end is None:
        return 0
    start = max(0, seed_start - 1)
    end = min(len(guide), seed_end)
    if start >= end:
        return 0
    return sum(1 for a, b in zip(guide[start:end], off_spacer[start:end]) if a != b)


def preset_off_target_specificity(guide, off_pairs, preset_key="custom",
                                  seed_start=None, seed_end=None,
                                  assume_one_primary=True):
    """System-aware off-target score for presets outside SpCas9."""
    if not off_pairs:
        return 1.0
    if preset_key == "cas9":
        return aggregate_off_target_specificity(guide, off_pairs, assume_one_primary)
    if preset_key == "cas12b":
        return identity_off_target_specificity(guide, off_pairs, assume_one_primary)

    rules = non_cas9_rules.get_rules(preset_key)
    seed_penalty = rules.get("seed_penalty", 0.25) if rules else 0.25
    total = 0.0
    has_perfect = False
    guide = guide.upper().replace("U", "T")
    for off_spacer, _ in off_pairs:
        off_spacer = off_spacer.upper().replace("U", "T")
        n = min(len(guide), len(off_spacer))
        if n == 0:
            continue
        matches = sum(1 for a, b in zip(guide[:n], off_spacer[:n]) if a == b)
        similarity = matches / n
        seed_mm = _count_seed_mismatches(guide, off_spacer, seed_start, seed_end)
        if seed_mm:
            similarity *= seed_penalty ** seed_mm
        total += similarity
        if similarity >= 0.999999:
            has_perfect = True
    if assume_one_primary and has_perfect:
        total = max(0.0, total - 1.0)
    return 1.0 / (1.0 + total)


def nucleotide_bias_on_target_score(seq, prefer="u_rich"):
    """RNA-targeting heuristic: U/A richness plus local dinucleotide preference."""
    seq = seq.upper().replace("T", "U")
    if not seq:
        return 0.0
    length = len(seq)
    if prefer == "a_rich":
        target_base = "A"
        preferred_pairs = {"AA", "UA"}
    else:
        target_base = "U"
        preferred_pairs = {"UU", "AU"}
    content = seq.count(target_base) / length
    content_score = max(0.0, min(1.0, (content - 0.20) / 0.20))
    pair_score = 0.0
    if length > 1:
        preferred = sum(1 for i in range(length - 1) if seq[i:i + 2] in preferred_pairs)
        pair_score = min(1.0, preferred / max(1, length - 1) * 2.0)
    return max(0.0, min(1.0, 0.35 * content_score + 0.15 * pair_score +
                        0.50 * heuristic_on_target_score(seq)))


def _cas13_flank_base(target_rna, spacer_start, side="5prime", spacer_len=None):
    """Return the Cas13 PFS flanking base for a guide, or None when unknown.

    The preset's PFS is 5' (``H`` = non-G), so the flanking base is the base
    immediately before the protospacer on the target RNA.  ``spacer_len`` falls
    back to the TIGER spacer length so 3' flanks use the correct offset.
    """
    if not target_rna or spacer_start is None:
        return None
    seq = target_rna.upper().replace("U", "T")
    start = int(spacer_start)
    spacer_len = spacer_len or tiger_model.GUIDE_LEN
    if side == "5prime" and start >= 1:
        return seq[start - 1]
    if side == "3prime" and start + spacer_len < len(seq):
        return seq[start + spacer_len]
    return None


def _cas13_on_target_score(seq, model_choice, direct_repeat=None,
                           target_rna=None, spacer_start=None,
                           guide_strand=None):
    """Score one Cas13 guide with TIGER when applicable, else the RNA rules."""
    choice = (model_choice or "auto").lower()
    seq_clean = seq.upper().replace("T", "U")
    # TIGER is a 23 nt Cas13d model; only apply at that spacer length.
    if len(seq_clean) == tiger_model.GUIDE_LEN and choice in ("tiger", "tiger13", "auto"):
        if tiger_model.TigerPredictor.available():
            try:
                tiger_seq = seq.upper().replace("U", "T")
                # Prefer the real 3 nt upstream context from the target RNA; the
                # helper returns None when it cannot be placed confidently, in
                # which case TIGER pads it with N (transcript-boundary behaviour).
                window = tiger_model.build_target_window(
                    tiger_seq, target_rna, spacer_start)
                score = tiger_model.TigerPredictor.get().score_guide(
                    tiger_seq, window)
                if score is not None:
                    upstream_note = ("" if window is not None
                                     else " (3 nt upstream context N-padded)")
                    features = {
                        "rna_model": "tiger13",
                        "rna_note": "TIGER Cas13d deep-learning on-target model "
                                    "(23 nt spacer)" + upstream_note,
                        "guide_mfe": None,
                        "guide_accessibility": None,
                        "target_accessibility": None,
                        "dr_spacer_duplex_mfe": None,
                        "dr_spacer_penalty": None,
                        "perturbation_mfe": None,
                        "dr_source": "",
                    }
                    return score, "tiger13", features
            except Exception:
                pass
        # CFD-style PFS fallback: the deep model is unavailable.
        flank = _cas13_flank_base(target_rna, spacer_start)
        return cas13_scoring.cas13_pfs_on_target_score(
            seq, flank_base=flank)
    return cas13_scoring.cas13_on_target_score(
        seq, "cas13", direct_repeat=direct_repeat, target_rna=target_rna)


def _cas13_off_target_score(guide, off_pairs, model_choice,
                            assume_one_primary, seed_start, seed_end):
    """Cas13 off-target specificity, preferring TIGER when it is usable."""
    choice = (model_choice or "auto").lower()
    if choice in ("pfs", "rules"):
        spec = cas13_scoring.cas13_pfs_off_target_specificity(
            guide, off_pairs, assume_one_primary)
        return spec, "cas13_pfs"
    if choice in ("tiger", "tiger13", "auto"):
        if (tiger_model.TigerPredictor.available()
                and len(guide) == tiger_model.GUIDE_LEN):
            try:
                spec = tiger_model.cas13_off_target_specificity(
                    guide, off_pairs, assume_one_primary)
                if spec is not None:
                    return spec, "tiger13"
            except Exception:
                pass
        # CFD-style PFS fallback: the deep model is unavailable.
        spec = cas13_scoring.cas13_pfs_off_target_specificity(
            guide, off_pairs, assume_one_primary)
        return spec, "cas13_pfs"
    spec = preset_off_target_specificity(
        guide, off_pairs, "cas13", seed_start, seed_end, assume_one_primary)
    return spec, "preset_cas13"


def _non_cas9_on_target_score(seq, preset_key, seed_start=None, seed_end=None,
                              tss_distance=None, direct_repeat=None,
                              target_rna=None, guide_strand=None,
                              tss_strand=None, promoter_start=None,
                              promoter_end=None, spacer_start=None,
                              model_choice=None):
    if preset_key == "cas13":
        return _cas13_on_target_score(
            seq, model_choice, direct_repeat=direct_repeat,
            target_rna=target_rna, spacer_start=spacer_start,
            guide_strand=guide_strand)
    return heuristic_on_target_score(seq), "preset_heuristic", {}


def deepcas12a_on_target_score(seq, methylation=None, dnase=None):
    """Return a DeepCas12a class-1 probability, or None when unavailable.

    DeepCas12a is an AsCas12a on-target model.  It requires a 34 nt
    target-context sequence (4 nt upstream + TTTV PAM + 23 nt protospacer +
    3 nt downstream) and two 34-character epigenetic channels.  Missing
    epigenetic tracks use all ``N``, matching the upstream example data.
    """
    if deep_models.deepcas12a_status(load=True) != "ready":
        return None
    try:
        return deep_models.DeepCas12aPredictor.get().predict(
            seq, methylation=seq_epigenetic_or_none(methylation, 34),
            dnase=seq_epigenetic_or_none(dnase, 34))
    except Exception:
        return None


def deepcpf1_on_target_score(seq):
    """Return the raw DeepCpf1 on-target score, or None when unavailable.

    DeepCpf1 is a sequence-only Cas12a/Cpf1 efficiency model.  It requires a
    34 nt target-context window (4 nt upstream + TTTV PAM + 23 nt protospacer
    + 3 nt downstream).  When the model is not ready or the input cannot be
    represented by the model, the caller falls back to the heuristic.
    """
    if deep_models.deepcpf1_status(load=True) != "ready":
        return None
    try:
        return deep_models.DeepCpf1Predictor.get().predict(seq)
    except Exception:
        return None


def seq_epigenetic_or_none(track, expected_len):
    """Normalize an optional epigenetic string, or return None for a default."""
    if track is None:
        return None
    track = str(track).upper()
    if len(track) != expected_len:
        return None
    return track


def custom_nuc_on_target_score(
        seq, model_choice, direct_repeat=None, target_rna=None,
        spacer_start=None, guide_strand=None):
    """Score an on-target for a free-form/custom nuclease using an explicit model.

    ``auto`` keeps the generic built-in heuristic and is never treated as
    reference-only. Any preset-specific model is applied when it can produce a
    score; the result is flagged ``reference_only`` because that model was
    validated for a specific nuclease, not for the custom one. Returns
    ``(score, model, reference_only, rna_features, tnpb_features)``.
    """
    choice = (model_choice or "auto").lower()
    if choice == "rules":
        return heuristic_on_target_score(seq), "rules_heuristic", False, {}, {}
    if choice in ("auto", "nuc_features"):
        return heuristic_on_target_score(seq), "nuc_features", False, {}, {}
    if choice == "cropsr":
        score = best_cropsr_on_target_score(seq)
        if score is not None:
            return score, "CROPSR_reference_only", True, {}, {}
        return heuristic_on_target_score(seq), "cropsr_fallback", True, {}, {}
    if choice == "deepcas12a":
        score = deepcas12a_on_target_score(seq)
        if score is not None:
            return score, "deepcas12a_reference_only", True, {}, {}
        return heuristic_on_target_score(seq), "deepcas12a_fallback", True, {}, {}
    if choice == "deepcpf1":
        score = deepcpf1_on_target_score(seq)
        if score is not None:
            return score, "deepcpf1_reference_only", True, {}, {}
        return heuristic_on_target_score(seq), "deepcpf1_fallback", True, {}, {}
    if choice in ("tiger", "tiger13"):
        score, model, features = _cas13_on_target_score(
            seq, choice, direct_repeat=direct_repeat, target_rna=target_rna,
            spacer_start=spacer_start, guide_strand=guide_strand)
        return score, model + "_reference_only", True, features, {}
    if choice in ("rna_rules", "cas13_rna_rules"):
        score, model, features = _cas13_on_target_score(
            seq, "rna_rules", direct_repeat=direct_repeat,
            target_rna=target_rna, spacer_start=spacer_start,
            guide_strand=guide_strand)
        return score, model + "_reference_only", True, features, {}
    if choice == "omega":
        score, model, features = tnpb_scoring.omega_rna_on_target_score(
            seq, direct_repeat=direct_repeat)
        return score, model + "_reference_only", True, {}, features
    if choice == "teep":
        score = teep_on_target_score(seq)
        if score is not None:
            return score, "teep_reference_only", True, {}, {}
        return heuristic_on_target_score(seq), "teep_fallback", True, {}, {}
    return heuristic_on_target_score(seq), "%s_unavailable" % choice, True, {}, {}


def custom_nuc_off_target_score(seq, off_pairs, model_choice,
                                assume_one_primary=True, seed_start=None,
                                seed_end=None):
    """Score off-targets for a free-form/custom nuclease using an explicit model.

    ``auto`` uses the generic identity/seed heuristic and is never
    reference-only. Preset-specific models are applied when usable and flagged
    ``reference_only`` because they were validated for another nuclease.
    ``crispai`` is a batch pipeline model and falls back to identity here.
    Unavailable models fall back while keeping the reference-only marker.
    """
    choice = (model_choice or "auto").lower()
    if choice in ("auto", "rules", "identity", "identity_heuristic",
                  "nuc_features"):
        return (identity_off_target_specificity(
            seq, off_pairs, assume_one_primary),
            "identity_heuristic", False)
    if choice == "cfd":
        spec = aggregate_off_target_specificity(
            seq, off_pairs, assume_one_primary)
        return spec, "cfd_reference_only", True
    if choice == "crispai":
        return (identity_off_target_specificity(
            seq, off_pairs, assume_one_primary),
            "identity_heuristic", True)
    if choice in ("crispr_m", "deepcrispr"):
        deep_result = _deep_off_target_score(
            seq, off_pairs, choice, assume_one_primary)
        if deep_result is not None:
            spec, model, _note = deep_result
            return spec, model + "_reference_only", True
        spec = aggregate_off_target_specificity(
            seq, off_pairs, assume_one_primary)
        return spec, "cfd_reference_only", True
    if choice in ("tiger", "tiger13"):
        spec, model = _cas13_off_target_score(
            seq, off_pairs, choice, assume_one_primary, seed_start, seed_end)
        return spec, model + "_reference_only", True
    return (identity_off_target_specificity(
        seq, off_pairs, assume_one_primary),
        "%s_unavailable" % choice, True)


def _is_heuristic_model(model_name):
    """Return True when a model tag marks a deterministic heuristic score.

    Heuristics such as the identity/seed fallback have no held-out
    calibration data, so rows scored with them must report
    ``calibration_status="uncalibrated"`` (see docs/PAIR_RANKING.md).
    """
    text = str(model_name or "").strip().lower()
    return text in ("heuristic", "nuc_features") or text.endswith("_heuristic")


def _compute_guide_scores_single(
        seq, off_pairs, nuclease="cas9", tnpb_subtype="unknown",
        reference_only_model=None, assume_one_primary=True,
        on_target_model="rules", preset_key=None,
        seed_start=None, seed_end=None, target_type=None,
        tss_distance=None, off_target_model="rules",
        direct_repeat=None, target_rna=None,
        guide_strand=None, tss_strand=None,
        promoter_start=None, promoter_end=None,
        spacer_start=None, precomputed_off_target=None):
    """Compute scores for one on-target and one off-target model."""
    seq = seq.upper().replace("U", "T")
    input_offtargets = list(off_pairs or [])
    off_pairs, bulge_hits = _split_bulge_hits(input_offtargets)
    nuclease = (nuclease or "cas9").lower()
    tnpb_subtype = (tnpb_subtype or "unknown").lower()
    reference_only_model = (reference_only_model or "none").lower()
    on_target_model = (on_target_model or "cropsr").lower()
    preset_key = (preset_key or "custom").lower()
    if preset_key not in SYSTEM_PRESETS:
        preset_key = "custom"

    if preset_key == "custom" and nuclease in NUCLEASE_PRESET_MAP:
        preset_key = NUCLEASE_PRESET_MAP[nuclease]
    if nuclease == "tnpb" and preset_key == "custom":
        preset_key = "tnpb"
    if nuclease == "custom":
        # A custom nuclease must use the custom dispatcher even when a
        # pattern-level preset key is still present from the surrounding UI.
        preset_key = "custom"

    preset = get_preset(preset_key)
    if target_type is None:
        target_type = preset.get("target_type", "dna")
    if seed_start is None:
        seed_start = preset.get("seed_start")
    if seed_end is None:
        seed_end = preset.get("seed_end")
    if direct_repeat is None:
        direct_repeat = preset.get("direct_repeat")

    reference_only = False
    reference_note = ""
    off_note = ""
    subtype_note = ""
    rna_features = {}
    tnpb_features = {}
    cfd_specificity = ""
    has_precomputed_off_target = precomputed_off_target is not None
    precomputed_specificity = None
    precomputed_model = ""
    precomputed_reference_only = False
    ai_off_target = _empty_deep_off_target_columns()
    if has_precomputed_off_target:
        precomputed_specificity = float(
            precomputed_off_target.get("specificity", 1.0))
        precomputed_model = str(
            precomputed_off_target.get("model") or off_target_model or "")
        precomputed_reference_only = bool(
            precomputed_off_target.get("reference_only", False))
    deepcas12a_on_target = ""
    deepcpf1_on_target = ""
    tiger_on_target = ""
    tiger_off_target = ""

    if preset_key in ("cas12a", "cas12b", "cas14a", "cas13"):
        cfd_specificity = ""
        if preset_key == "cas13":
            if has_precomputed_off_target:
                off_specificity = precomputed_specificity
                off_target_model = precomputed_model
            else:
                off_specificity, off_target_model = _cas13_off_target_score(
                    seq, off_pairs, off_target_model, assume_one_primary,
                    seed_start, seed_end)
            if off_target_model == "tiger13":
                tiger_off_target = off_specificity
        else:
            if has_precomputed_off_target:
                off_specificity = precomputed_specificity
                off_target_model = precomputed_model
            else:
                off_specificity = preset_off_target_specificity(
                    seq, off_pairs, preset_key, seed_start, seed_end,
                    assume_one_primary)
                off_target_model = "preset_%s" % preset_key
        if preset_key == "cas12a" and on_target_model == "deepcpf1":
            score = deepcpf1_on_target_score(seq)
            if score is not None:
                on_target = score
                on_target_model = "deepcpf1"
                deepcpf1_on_target = score
                rna_features = {}
            else:
                on_target = heuristic_on_target_score(seq)
                on_target_model = "deepcpf1_fallback"
                rna_features = {}
        elif preset_key == "cas12a" and on_target_model in ("deepcas12a", "auto"):
            score = deepcas12a_on_target_score(seq)
            if score is not None:
                on_target = score
                on_target_model = "deepcas12a"
                deepcas12a_on_target = score
                rna_features = {}
            else:
                on_target = heuristic_on_target_score(seq)
                on_target_model = "deepcas12a_fallback"
                rna_features = {}
        else:
            on_target, on_target_model, rna_features = _non_cas9_on_target_score(
                seq, preset_key, seed_start, seed_end, tss_distance,
                direct_repeat=direct_repeat, target_rna=target_rna,
                spacer_start=spacer_start, guide_strand=guide_strand,
                model_choice=on_target_model)
            if on_target_model == "tiger13":
                tiger_on_target = on_target
        if preset_key == "cas13":
            subtype_note = (
                "Cas13 RNA 评分规则仅适用于 %s 亚型，其他 Cas13 变体结果仅供参考。"
                % preset_key
            )
    elif reference_only_model == "teep" and nuclease == "tnpb":
        cfd_specificity = ""
        off_specificity = identity_off_target_specificity(seq, off_pairs, assume_one_primary)
        off_target_model = "identity_heuristic"
        teep_score = teep_on_target_score(seq)
        if teep_score is not None:
            on_target = teep_score
            on_target_model = "teep_reference_only"
        else:
            on_target = heuristic_on_target_score(seq)
            on_target_model = "teep_fallback"
        reference_only = True
        reference_note = "TEEP trained on ISDra2 TnpB; applied to another TnpB, result is not validated."
        subtype_note = (
            "TEEP 仅适用于 ISDra2 TnpB（isdra2）亚型；此处作为参考模型使用，结果未经验证。"
        )
    elif preset_key == "tnpb":
        cfd_specificity = ""
        off_specificity = identity_off_target_specificity(seq, off_pairs, assume_one_primary)
        off_target_model = "identity_heuristic"
        on_target, on_target_model, tnpb_features = \
            tnpb_scoring.omega_rna_on_target_score(
                seq, direct_repeat=direct_repeat)
        subtype_note = (
            "TnpB omegaRNA/TEEP 规则仅适用于 ISDra2 TnpB（isdra2）亚型，"
            "其他 TnpB 变体结果仅供参考。"
        )
    elif nuclease == "cas9" or preset_key == "cas9":
        cfd_specificity = aggregate_off_target_specificity(
            seq, off_pairs, assume_one_primary)
        if has_precomputed_off_target:
            off_specificity = precomputed_specificity
            off_target_model = precomputed_model
        else:
            deep_result = _deep_off_target_score(
                seq, off_pairs, off_target_model, assume_one_primary)
            if deep_result is not None:
                off_specificity, off_target_model, off_note = deep_result
            else:
                off_specificity = aggregate_off_target_specificity(
                    seq, off_pairs, assume_one_primary)
                off_target_model = "cfd"
                off_note = "指定的 off-target 模型不可用，已回退 CFD 评分"
        on_target, on_target_model = _cas9_on_target_score(seq, on_target_model)
    elif nuclease == "tnpb":
        cfd_specificity = ""
        off_specificity = identity_off_target_specificity(seq, off_pairs, assume_one_primary)
        off_target_model = "identity_heuristic"
        on_target, on_target_model, tnpb_features = \
            tnpb_scoring.omega_rna_on_target_score(
                seq, direct_repeat=direct_repeat)
        subtype_note = (
            "TnpB omegaRNA/TEEP 规则仅适用于 ISDra2 TnpB（isdra2）亚型，"
            "其他 TnpB 变体结果仅供参考。"
        )
    elif reference_only_model == "cas9" and nuclease != "custom":
        cfd_specificity = aggregate_off_target_specificity(
            seq, off_pairs, assume_one_primary)
        off_specificity = aggregate_off_target_specificity(seq, off_pairs, assume_one_primary)
        off_target_model = "cfd_reference_only"
        on_target, base_model = _cas9_on_target_score(seq, on_target_model)
        on_target_model = base_model + "_reference_only"
        reference_only = True
        reference_note = "Cas9 model applied to an unsupported nuclease; result is not validated."
    elif nuclease == "custom":
        cfd_specificity = ""
        (on_target, on_target_model, on_ref, on_rna_features,
         on_tnpb_features) = custom_nuc_on_target_score(
            seq, on_target_model, direct_repeat=direct_repeat,
            target_rna=target_rna, spacer_start=spacer_start,
            guide_strand=guide_strand)
        rna_features = on_rna_features
        tnpb_features = on_tnpb_features
        if has_precomputed_off_target:
            off_specificity = precomputed_specificity
            off_target_model = precomputed_model
            off_ref = precomputed_reference_only
        else:
            off_specificity, off_target_model, off_ref = \
                custom_nuc_off_target_score(
                    seq, off_pairs, off_target_model, assume_one_primary,
                    seed_start=seed_start, seed_end=seed_end)
        if (off_target_model.startswith("cfd")
                or off_target_model.startswith("crispr_m")
                or off_target_model.startswith("deepcrispr")):
            cfd_specificity = aggregate_off_target_specificity(
                seq, off_pairs, assume_one_primary)
        if on_target_model == "deepcas12a_reference_only":
            deepcas12a_on_target = on_target
        if on_target_model == "deepcpf1_reference_only":
            deepcpf1_on_target = on_target
        if on_target_model.startswith("tiger13"):
            tiger_on_target = on_target
        if off_target_model.startswith("tiger13"):
            tiger_off_target = off_specificity
        if on_ref or off_ref:
            reference_only = True
            reference_note = (
                "模型未针对自定义核酸酶验证；结果仅供参考，不应用于实验决策。"
            )
    else:
        cfd_specificity = ""
        off_specificity = identity_off_target_specificity(seq, off_pairs, assume_one_primary)
        off_target_model = "identity_heuristic"
        on_target = heuristic_on_target_score(seq)
        on_target_model = "nuc_features"
        if nuclease in ("cas13/tnpb", "cas13", "tnpb"):
            subtype_note = (
                "未指定具体亚型，使用通用启发式评分；"
                "特定亚型模型的结果会标注其适用范围。"
            )

    if has_precomputed_off_target:
        off_specificity = precomputed_specificity
        off_target_model = precomputed_model
        if precomputed_reference_only:
            reference_only = True
            if not reference_note:
                reference_note = (
                    "模型未针对自定义核酸酶验证；结果仅供参考，不应用于实验决策。"
                )
    if off_target_model == "crispr_m":
        ai_off_target["crispr_m_off_target"] = off_specificity
    elif off_target_model == "deepcrispr":
        ai_off_target["deepcrispr_off_target"] = off_specificity
    elif off_target_model == "tiger13":
        tiger_off_target = off_specificity

    bulge_risk = sum(_bulge_risk(seq, hit) for hit in bulge_hits)
    if bulge_risk:
        base_burden = max(0.0, (1.0 / max(off_specificity, 1e-12)) - 1.0)
        off_specificity = 1.0 / (1.0 + base_burden + bulge_risk)
        off_note = (
            (off_note + "; ") if off_note else ""
        ) + (
            "Bulge hits use an uncalibrated conservative penalty "
            "(%s)." % BULGE_PENALTY_VERSION
        )

    heuristic_specificity = _is_heuristic_model(off_target_model)
    calibration_status = "uncalibrated" if (
        bulge_hits or heuristic_specificity
        or preset_key in ("cas12a", "cas12b", "cas14a", "tnpb")
    ) else "calibrated_reference"
    rules = non_cas9_rules.get_rules(preset_key)
    return {
        "off_target_specificity": off_specificity,
        "off_target_model": off_target_model,
        "off_target_model_note": off_note,
        "calibration_status": calibration_status,
        "bulge_score_method": (
            BULGE_PENALTY_VERSION if bulge_hits else "not_applicable"
        ),
        "input_offtargets": len(input_offtargets),
        "substitution_offtargets": len(off_pairs),
        "bulge_hits": len(bulge_hits),
        "scored_bulge_hits": len(bulge_hits),
        "unscored_bulge_hits": 0,
        "bulge_risk_sum": bulge_risk,
        "cfd_specificity": cfd_specificity,
        "crispr_m_off_target": ai_off_target["crispr_m_off_target"],
        "deepcrispr_off_target": ai_off_target["deepcrispr_off_target"],
        "crispai_off_target": ai_off_target["crispai_off_target"],
        "deepcas12a_on_target": deepcas12a_on_target,
        "deepcpf1_on_target": deepcpf1_on_target,
        "tiger_on_target": tiger_on_target,
        "tiger_off_target": tiger_off_target,
        "on_target_score": on_target,
        "on_target_model": on_target_model,
        "reference_only": reference_only,
        "reference_note": reference_note,
        "subtype_note": subtype_note,
        "preset": preset_key,
        "preset_label": preset.get("label", preset_key),
        "target_type": target_type,
        "rule_source": rules["source"] if rules else "",
        "rule_reference": rules["source_url"] if rules else "",
        "rule_summary": non_cas9_rules.rule_summary_text(preset_key),
        "rna_features": rna_features,
        "tnpb_features": tnpb_features,
        "cropsr_model_note": CROPSR_MODEL_NOTE,
    }


def _normalize_model_choices(value, default):
    """Return unique, lower-case model names from a scalar or sequence."""
    if value is None:
        raw = [default]
    elif isinstance(value, set):
        raw = sorted(value)
    elif isinstance(value, (list, tuple)):
        raw = list(value)
    else:
        raw = str(value).replace(";", ",").split(",")
    choices = []
    for item in raw:
        model = str(item or "").strip().lower()
        if model and model not in choices:
            choices.append(model)
    return choices or [str(default).lower()]


def _model_score_key(prefix, model):
    slug = "".join(
        char if char.isalnum() else "_"
        for char in str(model or "").lower()
    ).strip("_")
    while "__" in slug:
        slug = slug.replace("__", "_")
    return "%s_%s" % (prefix, slug or "model")


def compute_guide_scores(
        seq, off_pairs, nuclease="cas9", tnpb_subtype="unknown",
        reference_only_model=None, assume_one_primary=True,
        on_target_model="rules", preset_key=None,
        seed_start=None, seed_end=None, target_type=None,
        tss_distance=None, off_target_model="rules",
        direct_repeat=None, target_rna=None,
        guide_strand=None, tss_strand=None,
        promoter_start=None, promoter_end=None,
        spacer_start=None, on_target_models=None,
        off_target_models=None, precomputed_off_target_activities=None):
    """Compute scores for every selected on/off-target model.

    A scalar model value may contain comma-separated choices for backwards
    compatibility with command-line callers. Per-model values are returned
    under names such as ``on_target_score_cropsr`` and
    ``off_target_specificity_cfd`` so every checked model is visible.
    """
    on_choices = _normalize_model_choices(
        on_target_models if on_target_models is not None else on_target_model,
        "rules",
    )
    off_choices = _normalize_model_choices(
        off_target_models if off_target_models is not None else off_target_model,
        "rules",
    )
    primary_on = on_choices[0]
    primary_off = off_choices[0]

    def reference_for_on_choice(choice):
        if str(nuclease or "").lower() == "tnpb":
            if choice == "teep":
                return "teep"
            if choice == "omega":
                return "none"
            return reference_only_model
        return reference_only_model

    def score_one(on_choice, off_choice):
        return _compute_guide_scores_single(
            seq, off_pairs,
            nuclease=nuclease,
            tnpb_subtype=tnpb_subtype,
            reference_only_model=reference_for_on_choice(on_choice),
            assume_one_primary=assume_one_primary,
            on_target_model=on_choice,
            preset_key=preset_key,
            seed_start=seed_start,
            seed_end=seed_end,
            target_type=target_type,
            tss_distance=tss_distance,
            off_target_model=off_choice,
            direct_repeat=direct_repeat,
            target_rna=target_rna,
            guide_strand=guide_strand,
            tss_strand=tss_strand,
            promoter_start=promoter_start,
            promoter_end=promoter_end,
            spacer_start=spacer_start,
            precomputed_off_target=(
                precomputed_off_target_activities or {}
            ).get(off_choice),
        )

    primary = score_one(primary_on, primary_off)
    on_results = {primary_on: primary}
    off_results = {primary_off: primary}

    for choice in on_choices[1:]:
        on_results[choice] = score_one(choice, primary_off)
    for choice in off_choices[1:]:
        off_results[choice] = score_one(primary_on, choice)

    for choice, result in on_results.items():
        primary[_model_score_key("on_target_score", choice)] = \
            result["on_target_score"]
        primary[_model_score_key("on_target_model", choice)] = \
            result["on_target_model"]
    for choice, result in off_results.items():
        primary[_model_score_key("off_target_specificity", choice)] = \
            result["off_target_specificity"]
        primary[_model_score_key("off_target_model", choice)] = \
            result["off_target_model"]
    for key in ("crispr_m_off_target", "deepcrispr_off_target",
                "tiger_off_target"):
        if primary.get(key) not in (None, ""):
            continue
        for result in off_results.values():
            if result.get(key) not in (None, ""):
                primary[key] = result[key]
                break
    return primary


# Columns that are only surfaced by the library pipeline today.  Every scoring
# path should expose the same per-guide fields so the AI model scores (and the
# per-system RNA/TnpB features) appear no matter which pipeline produced the row.
_OUTPUT_OFF_TARGET_MODELS = _ordered_model_union(
    (ALL_OFF_TARGET_MODELS, ("crispai",))
)
MODEL_SCORE_COLUMNS = tuple(
    ["on_target_score_%s" % model for model in ALL_ON_TARGET_MODELS]
    + ["off_target_specificity_%s" % model for model in _OUTPUT_OFF_TARGET_MODELS]
)

MODEL_NAME_COLUMNS = tuple(
    ["on_target_model_%s" % model for model in ALL_ON_TARGET_MODELS]
    + ["off_target_model_%s" % model for model in _OUTPUT_OFF_TARGET_MODELS]
)

GUIDE_FEATURE_COLUMNS = (
    "cfd_specificity",
    "calibration_status",
    "bulge_score_method",
    "input_offtargets",
    "substitution_offtargets",
    "bulge_hits",
    "scored_bulge_hits",
    "unscored_bulge_hits",
    "bulge_risk_sum",
    "crispr_m_off_target",
    "deepcrispr_off_target",
    "crispai_off_target",
    "deepcas12a_on_target",
    "deepcpf1_on_target",
    "tiger_on_target",
    "tiger_off_target",
    "rule_source",
    "rule_reference",
    "rule_summary",
    "rna_model",
    "subtype_note",
    "guide_mfe",
    "guide_accessibility",
    "target_accessibility",
    "dr_spacer_duplex_mfe",
    "dr_spacer_penalty",
    "perturbation_mfe",
    "dr_source",
    "omega_model",
    "spacer_len_score",
    "guide_structure_penalty",
    "repeat_hairpin_score",
) + MODEL_SCORE_COLUMNS + MODEL_NAME_COLUMNS

OUTPUT_EXCLUDED_COLUMNS = frozenset({
    "reference_only",
    "reference_note",
    "rule_source",
    "rule_reference",
    "rule_summary",
    "subtype_note",
    "rna_model",
    "omega_model",
    "cfd_specificity",
    "crispr_m_off_target",
    "deepcrispr_off_target",
    "crispai_off_target",
    "deepcas12a_on_target",
    "deepcpf1_on_target",
    "tiger_on_target",
    "tiger_off_target",
}) | frozenset(MODEL_NAME_COLUMNS)

OUTPUT_GUIDE_FEATURE_COLUMNS = tuple(
    column for column in GUIDE_FEATURE_COLUMNS
    if column not in OUTPUT_EXCLUDED_COLUMNS
)

_RNA_FEATURE_KEYS = (
    "rna_model", "guide_mfe", "guide_accessibility", "target_accessibility",
    "dr_spacer_duplex_mfe", "dr_spacer_penalty", "perturbation_mfe",
    "dr_source",
)

_TNPB_FEATURE_KEYS = (
    "omega_model", "spacer_len_score", "guide_structure_penalty",
    "repeat_hairpin_score",
)


def apply_guide_feature_columns(row, scores):
    """Copy the library-exclusive per-guide columns from compute_guide_scores().

    ``scores`` is the dict returned by :func:`compute_guide_scores`.  The nested
    ``rna_features`` / ``tnpb_features`` dicts are flattened into top-level
    columns so TSV/XLSX writers can emit them directly, mirroring how the
    library pipeline surfaces them.  Returns ``row`` for chaining.
    """
    row["cfd_specificity"] = scores.get("cfd_specificity", "")
    for key in (
            "calibration_status", "bulge_score_method", "input_offtargets",
            "substitution_offtargets", "bulge_hits", "scored_bulge_hits",
            "unscored_bulge_hits", "bulge_risk_sum"):
        row[key] = scores.get(key, "")
    for key in ("crispr_m_off_target", "deepcrispr_off_target",
                "crispai_off_target"):
        row[key] = scores.get(key, "")
    row["deepcas12a_on_target"] = scores.get("deepcas12a_on_target", "")
    row["deepcpf1_on_target"] = scores.get("deepcpf1_on_target", "")
    row["tiger_on_target"] = scores.get("tiger_on_target", "")
    row["tiger_off_target"] = scores.get("tiger_off_target", "")
    for key in ("rule_source", "rule_reference", "rule_summary"):
        row[key] = scores.get(key, "")
    row["subtype_note"] = scores.get("subtype_note", "")
    rna = scores.get("rna_features") or {}
    for key in _RNA_FEATURE_KEYS:
        row[key] = rna.get(key, "")
    tnpb = scores.get("tnpb_features") or {}
    for key in _TNPB_FEATURE_KEYS:
        row[key] = tnpb.get(key, "")
    for key in MODEL_SCORE_COLUMNS + MODEL_NAME_COLUMNS:
        row[key] = scores.get(key, "")
    return row


def rank_rows(rows, score_key="off_target_specificity"):
    """Sort rows by a score key and assign rank 1..N in-place."""
    rows.sort(key=lambda row: float(row.get(score_key, -1.0)), reverse=True)
    for rank, row in enumerate(rows, start=1):
        row["rank"] = rank
    return rows
