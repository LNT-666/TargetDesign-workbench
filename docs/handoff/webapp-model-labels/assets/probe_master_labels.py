#!/usr/bin/env python3
"""master verification for webapp-model-labels (independent of the servant probe)."""
import json
import os
import sys

ROOT = r"R:\songji\programfile"
sys.path.insert(0, os.path.join(ROOT, "webapp"))
sys.path.insert(0, os.path.join(ROOT, "shared"))

import schema  # noqa: E402
from design.workbench_form import PRESET_KEYS, model_display_name, side_model_options  # noqa: E402

doc = schema.build_schema()
labels = doc.get("model_labels")
print("has_model_labels:", isinstance(labels, dict))
print("label_count:", len(labels) if isinstance(labels, dict) else None)

expected = {}
for key in PRESET_KEYS:
    options = side_model_options(key)
    for model in list(options["on_target"]) + list(options["off_target"]):
        expected.setdefault(model, model_display_name(model))

print("keys_equal_union_over_presets:", set(labels or {}) == set(expected))
print("values_equal_model_display_name:",
      all(labels[k] == v for k, v in expected.items()) if labels else False)
bad = [k for k, v in (labels or {}).items() if not v or "[" not in v]
print("labels_missing_protein_prefix:", bad)

# every preset option must be renderable by the front end
missing_in_labels = []
for key in PRESET_KEYS:
    options = side_model_options(key)
    for model in list(options["on_target"]) + list(options["off_target"]):
        if model not in (labels or {}):
            missing_in_labels.append((key, model))
print("preset_options_missing_a_label:", missing_in_labels)

# description single-source check: /api/models payload equals the registry text
sys.path.insert(0, os.path.join(ROOT, "webapp"))
import services.models as models_service  # noqa: E402
import scoring.model_registry as model_registry  # noqa: E402

data = models_service.list_models()
flat = [m for g in data["groups"] for m in g["models"]]
print("model_count:", len(flat))
mismatch = [m["key"] for m in flat
            if m.get("description") != model_registry.MODELS[m["key"]].get("description")]
print("description_mismatch:", mismatch)
teep = next(m for m in flat if m["key"] == "teep")
print("teep_path_url:", repr(teep.get("path")), repr(teep.get("url")))
print("sample_labels:", json.dumps({k: labels[k] for k in sorted(labels)[:4]}, ensure_ascii=False))