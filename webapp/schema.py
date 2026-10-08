#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Option/field schema served to the local web front end.

Every option list here comes from the shared modules the desktop workbench
uses, so the web form cannot drift from ``designer_workbench``: modes, presets,
engines, PAM modes, model choices, export formats and the PairRank policy
fields are all read from ``shared``.
"""

from __future__ import annotations

import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHARED = os.path.join(ROOT, "shared")
if SHARED not in sys.path:
    sys.path.insert(0, SHARED)

from design.library_preflight import ENGINE_CHOICES  # noqa: E402
from design.system_presets import (  # noqa: E402
    PAM_MODES,
    TNPB_SUBTYPE_LABELS,
    TNPB_SUBTYPES,
    get_preset,
    preset_choices,
)
from design.workbench_form import (  # noqa: E402
    MODE_LABELS,
    PAIR_RANK_POLICY_FIELDS,
    PRESET_KEYS,
    model_display_name,
    side_model_options,
)
from output.candidate_export import SUPPORTED_FORMATS  # noqa: E402
from scoring.scoring import PROTEIN_GROUP_LABELS  # noqa: E402
import scoring.model_registry as model_registry  # noqa: E402


#: Order matters: it mirrors designer_workbench._create_run_bar.
PAM_MODE_CHOICES = ["strict_ngg", "guidescan2_nrg", "custom"]
MEMORY_MODE_CHOICES = ["auto", "custom", "unlimited"]

#: Region / identifier choices copied from main.py's Data preparation tabs.
REGION_TYPES = [
    "Coding region",
    "Exonic sequence",
    "Specific exon",
    "Introns",
    "Specific intron",
    "5' UTR",
    "3' UTR",
]
ID_TYPES = ["gene_name", "ID", "gene_id", "locus_tag"]

FALLBACK_SPECIES = ["human", "yeast", "mouse", "zebrafish", "fly", "worm"]

#: Candidate columns the workbench hides (designer_workbench.py:2593-2596).
HIDDEN_CANDIDATE_COLUMNS = ("query_seq", "gap_seq")


def _field(key, label, **extra):
    field = {"key": key, "label": label, "type": "text", "default": ""}
    field.update(extra)
    return field


COMMON_FIELDS = [
    _field("search_fasta", "Search FASTA", type="file", kind="fasta",
           input_modes=["sequence"]),
    _field("bed_regions", "BED Regions", type="file", kind="bed",
           input_modes=["bed"]),
    _field("genome_fasta", "Genome FASTA", type="file", kind="fasta",
           hint="A .fna.gz path is decompressed next to the file"),
    _field("mask_fasta", "Mask FASTA", type="file", kind="fasta",
           hint="optional"),
    _field("blastdb", "BLAST DB Prefix", type="file", kind="db",
           hint="optional"),
    _field("annotation", "Annotation GFF3", type="file", kind="annotation",
           hint="optional - adds Annotation / Nearest-TSS / Isoforms / "
                "Downstream-ATG to the score table"),
    _field("result_label", "Result Label",
           hint="blank = auto system-target"),
]

RUN_FIELDS = [
    _field("engine", "Engine", type="combo",
           options=list(ENGINE_CHOICES), default="auto"),
    _field("max_mismatch", "Max Mismatch", type="combo",
           options=["0", "1", "2", "3", "4"], default="4"),
    _field("max_bulge", "Max Bulge", type="combo",
           options=["", "0", "1"], default=""),
    _field("pam_mode", "PAM Mode", type="combo",
           options=list(PAM_MODE_CHOICES), default="strict_ngg"),
    _field("seed_len", "Seed Length", default="12", hint="informational only - the engine uses the index k-mer length as the seed length"),
    _field("index_path", "Index Prefix", type="file", kind="index"),
    _field("gc_min", "GC Min", default="40"),
    _field("gc_max", "GC Max", default="70"),
    _field("genome_build", "Genome Build"),
    _field("filter_hard", "Hard Filter", type="check", default=False),
    _field("memory_mode", "Memory Limit", type="combo",
           options=list(MEMORY_MODE_CHOICES), default="auto"),
    _field("max_memory_mb", "Custom MiB", default="32768"),
    _field("search_timeout_s", "Search timeout (s)",
           hint="optional wall-clock limit for the off-target search step"),
]


#: ``GET /api/fs/list`` kind filter: the extensions a kind keeps. Directories
#: are always listed -- ``dir`` only drops the files, ``any`` filters nothing.
FS_KINDS = {
    "any": (),
    "dir": (),
    "fasta": (".fa", ".fasta", ".fna", ".fas", ".ffn", ".faa",
              ".fa.gz", ".fasta.gz", ".fna.gz", ".fas.gz"),
    "annotation": (".gtf", ".gff", ".gff3", ".gtf.gz", ".gff.gz", ".gff3.gz"),
    "bed": (".bed", ".bed.gz"),
    "db": (".nin", ".nhr", ".nsq", ".ndb", ".nog", ".nos", ".not",
           ".ntf", ".nto", ".njs", ".source.json"),
    "index": (".ggi", ".json"),
}

#: Suffixes the picker strips from a chosen file. ``blastdb`` wants the BLAST
#: library prefix (``blastn -db <prefix>``: ``<prefix>.nin``/``.nsq`` plus the
#: ``<prefix>.source.json`` sidecar) and ``index_path`` wants the genome index
#: prefix (``<prefix>.ggi`` + ``<prefix>.json``). Longest suffix wins.
FS_STRIP = {
    "db": (".source.json", ".nin", ".nhr", ".nsq", ".ndb", ".nog", ".nos",
           ".not", ".ntf", ".nto", ".njs"),
    "index": (".ggi", ".json"),
}


def _side_preset(side):
    return {"type": "side_preset", "side": side, "label": "System Preset"}


def _use_for_run(side):
    return {"type": "use_for_run", "side": side, "label": "Use for Run"}


def _side_models(side):
    return {"type": "side_models", "side": side, "label": "Side Models"}


PATTERN_FORMS = {
    "single_motif_flank": {
        "left": {
            "title": "Target TAM",
            "fields": [
                _side_preset("target"),
                _field("motif", "PAM/TAM Motif", hint="PAM/TAM motif"),
                _field("flank", "Target Length", hint="Target length"),
                _field("side", "Target Position", type="combo",
                       options=["downstream", "upstream"], default="upstream",
                       hint="Relative position to PAM/TAM"),
                _use_for_run("target"),
                _side_models("target"),
            ],
        },
    },
    "motif_gap_motif": {
        "left": {
            "title": "Left TAM",
            "fields": [
                _side_preset("left"),
                _field("left_motif", "PAM/TAM", hint="Left PAM/TAM"),
                _field("left_flank", "Target Length",
                       hint="Left target length"),
                _field("left_side", "Target Position", type="combo",
                       options=["downstream", "upstream"], default="upstream",
                       hint="Relative position to left PAM/TAM"),
                _field("left_require_pam", "Require PAM", type="check",
                       default=True,
                       hint="Require the left PAM/TAM during scoring"),
                _use_for_run("left"),
                _side_models("left"),
            ],
        },
        "middle": {
            "title": "Middle",
            "fields": [
                _field("min_gap", "Minimum Distance",
                       hint="Minimum distance to left PAM/TAM"),
                _field("max_gap", "Maximum Distance",
                       hint="Maximum distance to left PAM/TAM"),
            ],
        },
        "right": {
            "title": "Right TAM",
            "fields": [
                _side_preset("right"),
                _field("right_motif", "PAM/TAM", hint="Right PAM/TAM"),
                _field("right_flank", "Target Length",
                       hint="Right target length"),
                _field("right_side", "Target Position", type="combo",
                       options=["downstream", "upstream"], default="upstream",
                       hint="Relative position to right PAM/TAM"),
                _field("right_require_pam", "Require PAM", type="check",
                       default=True,
                       hint="Require the right PAM/TAM during scoring"),
                _use_for_run("right"),
                _side_models("right"),
            ],
        },
    },
    "y_centered_motifs": {
        "left": {
            "title": "Left TAM",
            "fields": [
                _side_preset("left"),
                _field("left_motif", "PAM/TAM", hint="Left PAM/TAM"),
                _field("left_flank", "Target Length",
                       hint="Left target length"),
                _field("left_side", "Target Position", type="combo",
                       options=["downstream", "upstream"], default="upstream",
                       hint="Relative position to left PAM/TAM"),
                _field("left_require_pam", "Require PAM", type="check",
                       default=True,
                       hint="Require the left PAM/TAM during scoring"),
                _field("left_min_distance", "Minimum Distance",
                       hint="From middle motif to left PAM/TAM"),
                _field("left_max_distance", "Maximum Distance",
                       hint="From middle motif to left PAM/TAM"),
                _use_for_run("left"),
                _side_models("left"),
            ],
        },
        "middle": {
            "title": "Middle",
            "fields": [
                _field("y_sequence", "Middle Motif",
                       hint="Middle motif (no mismatch) included"),
            ],
        },
        "right": {
            "title": "Right TAM",
            "fields": [
                _side_preset("right"),
                _field("right_motif", "PAM/TAM",
                       hint="Right PAM/TAM motif"),
                _field("right_flank", "Target Length",
                       hint="Right target length"),
                _field("right_side", "Target Position", type="combo",
                       options=["downstream", "upstream"], default="upstream",
                       hint="Relative position to right PAM/TAM"),
                _field("right_require_pam", "Require PAM", type="check",
                       default=True,
                       hint="Require the right PAM/TAM during scoring"),
                _field("right_min_distance", "Minimum Distance",
                       hint="From middle motif to right PAM/TAM"),
                _field("right_max_distance", "Maximum Distance",
                       hint="From middle motif to right PAM/TAM"),
                _use_for_run("right"),
                _side_models("right"),
            ],
        },
    },
}


def _plain_fields(fields):
    return [item for item in fields if "key" in item]


def designer_field_keys():
    """Every plain form field key of the Designer panel."""
    keys = []
    for field in COMMON_FIELDS + RUN_FIELDS:
        keys.append(field["key"])
    for form in PATTERN_FORMS.values():
        for group in form.values():
            for field in _plain_fields(group["fields"]):
                if field["key"] not in keys:
                    keys.append(field["key"])
    for name in PAIR_RANK_POLICY_FIELDS:
        keys.append("pair_rank_%s" % name)
    return keys


def designer_defaults():
    """Field defaults, matching the Tk widget defaults of the desktop app."""
    defaults = {}
    for field in COMMON_FIELDS + RUN_FIELDS:
        defaults[field["key"]] = field["default"]
    for form in PATTERN_FORMS.values():
        for group in form.values():
            for field in _plain_fields(group["fields"]):
                defaults.setdefault(field["key"], field["default"])
    for name in PAIR_RANK_POLICY_FIELDS:
        defaults["pair_rank_%s" % name] = ""
    return defaults


DESIGNER_FIELD_KEYS = designer_field_keys()
DESIGNER_DEFAULTS = designer_defaults()

def species_choices():
    """Downloadable organisms, in the desktop combo's order."""
    try:
        from data.download_data import DOWNLOAD_URLS
        keys = list(DOWNLOAD_URLS)
    except Exception:
        return list(FALLBACK_SPECIES)
    ordered = [name for name in FALLBACK_SPECIES if name in keys]
    ordered += [name for name in keys if name not in ordered]
    return ordered


def model_catalog():
    """Visible registry models grouped by protein, for the Models tab."""
    catalog = []
    for protein, keys in model_registry.models_by_protein().items():
        entries = []
        for key in keys:
            info = model_registry.MODELS.get(key) or {}
            entries.append({
                "key": key,
                "name": info.get("name") or key,
                "role": info.get("role") or "",
                "protein": info.get("protein") or protein,
                "type": info.get("type") or "",
                "downloadable": model_registry.is_downloadable(info),
                "url": info.get("url") or "",
                "description": info.get("description") or "",
            })
        catalog.append({
            "protein": protein,
            "label": (
                model_registry.PROTEIN_LABELS.get(protein)
                or PROTEIN_GROUP_LABELS.get(protein)
                or protein
            ),
            "models": entries,
        })
    return catalog


def build_schema():
    """Return the JSON document served by ``GET /api/schema``."""
    presets = []
    for key, label in preset_choices():
        preset = get_preset(key)
        presets.append({
            "value": key,
            "label": label,
            "nuclease": preset.get("nuclease") or "custom",
            "tnpb_subtype": preset.get("tnpb_subtype") or "unknown",
            "pam": preset.get("pam") or "",
            "spacer_len": preset.get("spacer_len"),
            "pam_side": preset.get("pam_side") or "",
            "pam_mode": preset.get("pam_mode") or "custom",
            "pam_required": bool(preset.get("pam_required")),
        })
    nucleases = []
    for item in presets:
        if item["nuclease"] not in nucleases:
            nucleases.append(item["nuclease"])
    tnpb_subtypes = [
        {"value": value, "label": TNPB_SUBTYPE_LABELS.get(value, value)}
        for value in TNPB_SUBTYPES
    ]
    side_keys = ["target", "left", "right"]
    cas9_models = side_model_options("cas9")
    preset_models = {key: side_model_options(key) for key in PRESET_KEYS}
    model_labels = {}
    for options in preset_models.values():
        for model in list(options["on_target"]) + list(options["off_target"]):
            if model not in model_labels:
                model_labels[model] = model_display_name(model)
    return {
        "modes": [
            {"value": value, "label": MODE_LABELS[value]}
            for value in MODE_LABELS
        ],
        "input_modes": [
            {"value": "sequence", "label": "Sequence (FASTA)"},
            {"value": "bed", "label": "BED Regions"},
        ],
        "presets": presets,
        "preset_models": preset_models,
        "model_labels": model_labels,
        "engines": list(ENGINE_CHOICES),
        "pam_modes": list(PAM_MODE_CHOICES),
        "memory_modes": list(MEMORY_MODE_CHOICES),
        "nucleases": nucleases,
        "tnpb_subtypes": tnpb_subtypes,
        "export_formats": list(SUPPORTED_FORMATS),
        "pair_rank_fields": list(PAIR_RANK_POLICY_FIELDS),
        "hidden_candidate_columns": list(HIDDEN_CANDIDATE_COLUMNS),
        "model_groups": model_catalog(),
        "designer": {
            "common_fields": COMMON_FIELDS,
            "run_fields": RUN_FIELDS,
            "pattern_forms": PATTERN_FORMS,
            "field_keys": list(DESIGNER_FIELD_KEYS),
            "defaults": dict(DESIGNER_DEFAULTS),
            "side_keys": side_keys,
            "default_side_presets": {
                side: "cas9" for side in side_keys
            },
            "default_side_on_target_models": {
                side: cas9_models["on_target_default"] for side in side_keys
            },
            "default_side_off_target_models": {
                side: cas9_models["off_target_default"] for side in side_keys
            },
            "default_require_pam": True,
        },
        "dataprep": {
            "species": species_choices(),
            "region_types": list(REGION_TYPES),
            "id_types": list(ID_TYPES),
            "skip_mask_default": False,
            "mask_same_as_target_default": True,
        },
    }
