"""Master probe for the handoff task ``webapp-designer-port``.

Independently proves that ``shared/design/workbench_form.py`` reproduces the
pre-change ``designer_workbench.PatternDesignerWorkbench`` logic value by
value.  The pre-change module is loaded from
``backup/20260916_webapp_designer_port/designer_workbench.py``; its class is
instantiated with ``object.__new__`` plus stub Tk variables, so no Tk root and
no GUI is created.
"""
from __future__ import annotations

import dataclasses
import importlib.util
import json
import os
import sys

REPO = r"R:\songji\programfile"
BACKUP_PATH = os.path.join(
    REPO, "backup", "20260916_webapp_designer_port", "designer_workbench.py")
SHARED = os.path.join(REPO, "shared")
for entry in (REPO, SHARED):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from design import workbench_form as wf            # noqa: E402
from design.system_presets import preset_choices    # noqa: E402
from webapp import schema as webapp_schema          # noqa: E402

DEFAULTS = webapp_schema.designer_defaults()
SMOKE = os.path.join(REPO, "out", "webapp_smoke")
TARGET_FA = os.path.join(SMOKE, "target.fa")
GENOME = os.path.join(REPO, "example", "engine_benchmark", "synthetic_genome.fa")
MISSING = os.path.join(SMOKE, "does_not_exist.fa")
OUT_DIR = SMOKE

RESULTS = []
TOTAL = [0]


def check(name, ok, detail=""):
    TOTAL[0] += 1
    RESULTS.append((name, bool(ok)))
    if ok:
        print("PASS  %s" % name)
    else:
        print("FAIL  %s" % name)
        if detail:
            print("      %s" % str(detail)[:1200])


class StubVar(object):
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class Combo(object):
    def __init__(self, sink):
        self.sink = sink

    def set_values(self, values):
        self.sink(list(values))


def load_backup():
    spec = importlib.util.spec_from_file_location(
        "backup_designer_workbench", BACKUP_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["backup_designer_workbench"] = module
    spec.loader.exec_module(module)
    return module


def as_plain(obj):
    if not isinstance(obj, type) and dataclasses.is_dataclass(obj):
        return dataclasses.asdict(obj)
    if hasattr(obj, "__dict__"):
        return dict(vars(obj))
    return obj


def call(func):
    try:
        return ("ok", as_plain(func()))
    except Exception as exc:  # noqa: BLE001
        return ("err", "%s: %s" % (type(exc).__name__, exc))


def brief(value):
    return json.dumps(value, default=str, ensure_ascii=False)[:700]


def base_values(**over):
    values = dict(DEFAULTS)
    values.update(over)
    return values


def make_case(name, **over):
    values = over.pop("values", None) or {}
    case = {
        "name": name,
        "mode": "single_motif_flank",
        "input_mode": "sequence",
        "nuclease": "cas9",
        "tnpb_subtype": "unknown",
        "require_pam": True,
        "active_side": "left",
        "side_presets": {"target": "cas9", "left": "cas9", "right": "cas9"},
        "side_on_target_models": {
            "target": "auto", "left": "auto", "right": "auto"},
        "side_off_target_models": {
            "target": "auto", "left": "auto", "right": "auto"},
    }
    case.update(over)
    case["values"] = base_values(**values)
    return case


def backup_object(module, case, log=None):
    klass = module.PatternDesignerWorkbench
    obj = klass.__new__(klass)
    obj.vars = {key: StubVar(value) for key, value in case["values"].items()}
    obj.mode_var = StubVar(case["mode"])
    obj.input_mode_var = StubVar(case["input_mode"])
    obj.nuclease_var = StubVar(case["nuclease"])
    obj.tnpb_subtype_var = StubVar(case["tnpb_subtype"])
    obj.require_pam_var = StubVar(case["require_pam"])
    obj.active_side_var = StubVar(case["active_side"])
    obj.side_preset_vars = {
        k: StubVar(v) for k, v in case["side_presets"].items()}
    obj.side_on_target_model_vars = {
        k: StubVar(v) for k, v in case["side_on_target_models"].items()}
    obj.side_off_target_model_vars = {
        k: StubVar(v) for k, v in case["side_off_target_models"].items()}
    obj.status_var = StubVar("")
    obj._log_line = log.append if log is not None else (lambda _line: None)
    return obj


def form_state(case):
    return wf.WorkbenchFormState(
        values=dict(case["values"]),
        mode=case["mode"],
        input_mode=case["input_mode"],
        nuclease=case["nuclease"],
        tnpb_subtype=case["tnpb_subtype"],
        require_pam=case["require_pam"],
        active_side=case["active_side"],
        side_presets=dict(case["side_presets"]),
        side_on_target_models=dict(case["side_on_target_models"]),
        side_off_target_models=dict(case["side_off_target_models"]),
    )


def compare(name, backup_call, new_call, tolerance=0):
    left = call(backup_call)
    right = call(new_call)
    if tolerance and left[0] == "ok" and right[0] == "ok":
        first, second = left[1], right[1]
        if isinstance(first, int) and isinstance(second, int):
            ok = abs(first - second) <= max(32, int(abs(first) * tolerance))
            check(name, ok, "backup=%s new=%s" % (first, second))
            return
    check(name, left == right, "backup=%s\n      new=%s" % (brief(left), brief(right)))


VALUES_OK = {
    "search_fasta": TARGET_FA,
    "genome_fasta": GENOME,
    "output_dir": OUT_DIR,
    "motif": "TTAT",
    "flank": "5",
    "side": "upstream",
}

POLICY = {
    "pair_rank_e_high": "0.9", "pair_rank_e_min": "0.5",
    "pair_rank_e_fail": "0.2", "pair_rank_delta_default": "0.1",
    "pair_rank_b_low": "0.1", "pair_rank_b_high": "0.2",
    "pair_rank_m_low": "0.3", "pair_rank_m_high": "0.4",
    "pair_rank_h_risk": "0.5", "pair_rank_h_max": "0.6",
}


def build_cases():
    pair_values = dict(VALUES_OK)
    pair_values.update({
        "left_motif": "TTTN", "left_flank": "20", "left_side": "upstream",
        "right_motif": "TTTV", "right_flank": "18", "right_side": "downstream",
        "min_gap": "10", "max_gap": "40",
        "left_min_distance": "5", "left_max_distance": "30",
        "right_min_distance": "6", "right_max_distance": "31",
    })
    pair_values.update(POLICY)
    cases = [
        make_case("single/defaults"),
        make_case("single/filled", values=VALUES_OK),
        make_case("single/bed", values=dict(VALUES_OK, bed_regions=TARGET_FA),
                  input_mode="bed"),
        make_case("single/missing-files", values={
            "search_fasta": MISSING, "genome_fasta": MISSING,
            "output_dir": MISSING, "mask_fasta": MISSING}),
        make_case("single/outdir-is-a-file",
                  values=dict(VALUES_OK, output_dir=TARGET_FA)),
        make_case("single/memory-custom",
                  values=dict(VALUES_OK, memory_mode="custom",
                              max_memory_mb="4096")),
        make_case("single/memory-below-min",
                  values=dict(VALUES_OK, memory_mode="custom",
                              max_memory_mb="16")),
        make_case("single/memory-not-a-number",
                  values=dict(VALUES_OK, memory_mode="custom",
                              max_memory_mb="abc")),
        make_case("single/memory-unknown-mode",
                  values=dict(VALUES_OK, memory_mode="plenty")),
        make_case("single/memory-unlimited",
                  values=dict(VALUES_OK, memory_mode="unlimited")),
        make_case("single/timeout-set",
                  values=dict(VALUES_OK, search_timeout_s="90")),
        make_case("single/timeout-negative",
                  values=dict(VALUES_OK, search_timeout_s="-1")),
        make_case("single/timeout-not-a-number",
                  values=dict(VALUES_OK, search_timeout_s="soon")),
        make_case("single/result-label",
                  values=dict(VALUES_OK, result_label="My run")),
        make_case("single/gc-and-seed",
                  values=dict(VALUES_OK, gc_min="35", gc_max="75", seed_len="14",
                              max_mismatch="3", max_bulge="2", filter_hard=True,
                              pam_mode="custom", engine="blast",
                              index_path="idx/prefix", genome_build="GRCh38")),
        make_case("single/tnpb-target-side", values=dict(VALUES_OK),
                  nuclease="tnpb", require_pam=False,
                  side_presets={"target": "tnpb", "left": "cas9", "right": "cas9"},
                  side_on_target_models={
                      "target": "omega,teep", "left": "auto", "right": "auto"},
                  side_off_target_models={
                      "target": "auto", "left": "auto", "right": "auto"}),
        make_case("single/void-models", values=dict(VALUES_OK),
                  side_presets={"target": "custom", "left": "cas9", "right": "cas9"},
                  side_on_target_models={
                      "target": "void", "left": "auto", "right": "auto"},
                  side_off_target_models={
                      "target": "void", "left": "auto", "right": "auto"}),
        make_case("pair/gap", mode="motif_gap_motif", values=dict(pair_values),
                  nuclease="cas12a", active_side="left",
                  side_presets={"target": "cas9", "left": "cas12a", "right": "cas9"},
                  side_on_target_models={
                      "target": "auto", "left": "rules", "right": "rules"}),
        make_case("pair/gap-partial-policy", mode="motif_gap_motif",
                  values=dict(pair_values, pair_rank_h_max=""),
                  nuclease="cas12a", active_side="right",
                  side_presets={"target": "cas9", "left": "cas12a",
                                "right": "cas12a"}),
        make_case("pair/gap-bad-policy", mode="motif_gap_motif",
                  values=dict(pair_values, pair_rank_e_high="high"),
                  nuclease="cas12a", active_side="left",
                  side_presets={"target": "cas9", "left": "cas12a",
                                "right": "cas12a"}),
        make_case("pair/y-centered", mode="y_centered_motifs",
                  values=dict(pair_values, y_sequence="ACGTACGT"),
                  nuclease="cas12a", active_side="target",
                  side_presets={"target": "cas9", "left": "cas9",
                                "right": "cas12a"}),
        make_case("pair/y-centered-no-y", mode="y_centered_motifs",
                  values=dict(pair_values, y_sequence=""),
                  active_side="target",
                  side_presets={"target": "cas9", "left": "cas9",
                                "right": "cas12a"}),
        make_case("pair/tnpb-and-cas13", mode="motif_gap_motif",
                  values=dict(pair_values), active_side="left",
                  side_presets={"target": "cas9", "left": "tnpb",
                                "right": "cas13"},
                  side_on_target_models={"target": "auto",
                                         "left": "omega,teep",
                                         "right": "rna_rules"},
                  side_off_target_models={"target": "auto", "left": "void",
                                          "right": "auto"}),
        make_case("pair/bed-missing", mode="motif_gap_motif", input_mode="bed",
                  values=dict(pair_values, bed_regions="", search_fasta=""),
                  nuclease="cas12a", active_side="left",
                  side_presets={"target": "cas9", "left": "cas12a",
                                "right": "cas12a"}),
    ]
    return cases


def compare_config(name, obj, state, case):
    """Compare RunnerConfig field by field.

    ``memory_mode=auto`` re-reads the live memory snapshot on every call, so
    ``max_memory_mb`` may drift a few MiB between the two calls; that single
    field is compared with a tolerance instead of exactly.
    """
    left = call(obj._current_config)
    right = call(lambda: wf.build_runner_config(state))
    mode = str(case["values"].get("memory_mode", "auto")).strip().lower()
    if left[0] == "ok" and right[0] == "ok" and mode == "auto":
        volatile = {}
        for key in sorted(set(left[1]) | set(right[1])):
            if left[1].get(key) != right[1].get(key):
                volatile[key] = (left[1].get(key), right[1].get(key))
        drift = volatile.get("max_memory_mb")
        ok = set(volatile) <= {"max_memory_mb"}
        if ok and drift is not None:
            ok = abs(drift[0] - drift[1]) <= 64
        detail = "volatile fields: %s" % brief(volatile)
        check(name, ok, detail)
        return
    check(name, left == right,
          "backup=%s\n      new=%s" % (brief(left), brief(right)))


def run_case_checks(module, case):
    name = case["name"]
    obj = backup_object(module, case)
    state = form_state(case)
    compare("%s :: _current_spec" % name,
            obj._current_spec, lambda: wf.build_pattern_spec(state))
    compare_config(name, obj, state, case)
    compare("%s :: _default_run_label" % name,
            obj._default_run_label, lambda: wf.default_run_label(state))
    compare("%s :: _readiness_errors" % name,
            obj._readiness_errors, lambda: wf.readiness_errors(state))
    compare("%s :: _resolved_memory_limit" % name,
            obj._resolved_memory_limit, lambda: wf.resolved_memory_limit(state),
            tolerance=0.02)
    compare("%s :: _search_timeout_s" % name,
            obj._search_timeout_s, lambda: wf.search_timeout_s(state))
    compare("%s :: _pair_rank_policy_values" % name,
            obj._pair_rank_policy_values,
            lambda: wf.pair_rank_policy_values(state))
    compare("%s :: _prepare_genome_fasta" % name,
            obj._prepare_genome_fasta, lambda: wf.prepare_genome_fasta(state))
    for side in ("target", "left", "right"):
        compare("%s :: _resolve_side_models(%s)" % (name, side),
                (lambda s: (lambda: obj._resolve_side_models(s)))(side),
                (lambda s: (lambda: wf.resolve_side_models(state, s)))(side))
    compare("%s :: _auto_memory_limit" % name,
            obj._auto_memory_limit, wf.auto_memory_limit, tolerance=0.02)


def snapshot(obj):
    recorded = {key: var.value for key, var in obj.vars.items()}
    recorded["nuclease"] = obj.nuclease_var.value
    recorded["tnpb_subtype"] = obj.tnpb_subtype_var.value
    recorded["require_pam"] = obj.require_pam_var.value
    recorded["active_side"] = obj.active_side_var.value
    return recorded


def initial_values(case):
    recorded = dict(case["values"])
    recorded["nuclease"] = case["nuclease"]
    recorded["tnpb_subtype"] = case["tnpb_subtype"]
    recorded["require_pam"] = case["require_pam"]
    recorded["active_side"] = case["active_side"]
    return recorded


def diff_updates(name, expected, recorded, initial, allow=("active_side",)):
    problems = []
    for key, value in expected.items():
        if key in allow:
            continue
        if recorded.get(key) != value:
            problems.append("%s: expected %r, backup wrote %r"
                            % (key, value, recorded.get(key)))
    for key, value in recorded.items():
        if key in allow or key in expected:
            continue
        if value != initial.get(key):
            problems.append("%s: backup wrote %r but the shared layer does "
                            "not return it" % (key, value))
    check(name, not problems, "; ".join(problems))


def run_preset_checks(module):
    for side in ("target", "left", "right"):
        for preset_key, _label in preset_choices():
            case = make_case(
                "preset/%s/%s" % (side, preset_key), values=VALUES_OK,
                side_presets={"target": preset_key, "left": preset_key,
                              "right": preset_key})
            obj = backup_object(module, case)
            obj._refresh_side_model_options = lambda _side: None
            obj._refresh_preview = lambda: None
            obj._apply_side_preset(side)
            expected = wf.side_preset_updates(preset_key, side)
            diff_updates("_apply_side_preset(%s, %s) == side_preset_updates"
                         % (side, preset_key), expected, snapshot(obj),
                         initial_values(case))


def run_active_side_checks(module):
    for side in ("target", "left", "right"):
        for preset_key, _label in preset_choices():
            case = make_case(
                "active/%s/%s" % (side, preset_key), values=VALUES_OK,
                active_side=side,
                side_presets={"target": preset_key, "left": preset_key,
                              "right": preset_key})
            obj = backup_object(module, case)
            obj._sync_active_side_rules()
            expected = wf.active_side_updates(form_state(case))
            diff_updates("_sync_active_side_rules(%s, %s) == "
                         "active_side_updates" % (side, preset_key), expected,
                         snapshot(obj), initial_values(case))

    case = make_case("active/unknown-side", values=VALUES_OK, active_side="nope",
                     side_presets={"target": "cas9", "left": "cas9",
                                   "right": "cas9"})
    obj = backup_object(module, case)
    obj._sync_active_side_rules()
    expected = wf.active_side_updates(form_state(case))
    diff_updates("_sync_active_side_rules(unknown side) == "
                 "active_side_updates", expected, snapshot(obj),
                 initial_values(case))


def run_model_option_checks(module):
    for preset_key, _label in preset_choices():
        options = wf.side_model_options(preset_key)
        starts = ["", "auto", "void", "auto,rules",
                  options["on_target"][0], options["off_target"][0],
                  "bogus_model", "auto;void"]
        for start in starts:
            case = make_case("models/%s/%r" % (preset_key, start),
                             values=VALUES_OK,
                             side_presets={"target": preset_key,
                                           "left": preset_key,
                                           "right": preset_key})
            obj = backup_object(module, case)
            captured = {}
            obj._side_model_widgets = {
                "left": {
                    "on_combo": Combo(lambda v: captured.__setitem__("on", v)),
                    "off_combo": Combo(lambda v: captured.__setitem__("off", v)),
                }
            }
            obj.side_on_target_model_vars["left"] = StubVar(start)
            obj.side_off_target_model_vars["left"] = StubVar(start)
            obj._refresh_side_model_options("left")
            new_on = wf.resolve_side_model_selection(
                start, options["on_target"], options["on_target_preferred"])
            new_off = wf.resolve_side_model_selection(
                start, options["off_target"])
            expected_on = start if new_on is None else new_on
            expected_off = start if new_off is None else new_off
            problems = []
            if captured.get("on") != list(options["on_target"]):
                problems.append("on options %r != %r"
                                % (captured.get("on"), options["on_target"]))
            if captured.get("off") != list(options["off_target"]):
                problems.append("off options %r != %r"
                                % (captured.get("off"), options["off_target"]))
            if obj.side_on_target_model_vars["left"].value != expected_on:
                problems.append("on selected %r != %r"
                                % (obj.side_on_target_model_vars["left"].value,
                                   expected_on))
            if obj.side_off_target_model_vars["left"].value != expected_off:
                problems.append("off selected %r != %r"
                                % (obj.side_off_target_model_vars["left"].value,
                                   expected_off))
            check("_refresh_side_model_options(%s, %r) == side_model_options"
                  % (preset_key, start), not problems, "; ".join(problems))


def read_text(path):
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def run_static_checks():
    form_text = read_text(os.path.join(SHARED, "design", "workbench_form.py"))
    workbench = read_text(os.path.join(REPO, "designer_workbench.py"))
    form_lines = [line.strip() for line in form_text.splitlines()]
    check("workbench_form.py has no tkinter import",
          not any(line.startswith(("import tkinter", "from tkinter"))
                  for line in form_lines))
    for needle in ("PatternSpec(", "MotifSpec(", "RunnerConfig("):
        check("designer_workbench.py has no leftover %r construction" % needle,
              needle not in workbench)
    for needle in ("workbench_form.side_preset_updates",
                   "workbench_form.active_side_updates",
                   "workbench_form.build_pattern_spec",
                   "workbench_form.build_runner_config",
                   "workbench_form.readiness_errors",
                   "workbench_form.resolve_side_models",
                   "workbench_form.side_model_options"):
        check("designer_workbench.py calls %s" % needle, needle in workbench)

    webapp_files = [
        os.path.join(REPO, "webapp", "app.py"),
        os.path.join(REPO, "webapp", "jobs.py"),
        os.path.join(REPO, "webapp", "schema.py"),
        os.path.join(REPO, "webapp", "services", "designer.py"),
        os.path.join(REPO, "webapp", "services", "dataprep.py"),
        os.path.join(REPO, "webapp", "services", "models.py"),
    ]
    for path in webapp_files:
        lines = [line.strip() for line in read_text(path).splitlines()]
        rel = os.path.relpath(path, REPO)
        check("%s has no tkinter import" % rel,
              not any(line.startswith(("import tkinter", "from tkinter"))
                      for line in lines))
        check("%s has no designer_workbench import" % rel,
              not any(line.startswith(("import designer_workbench",
                                       "from designer_workbench"))
                      for line in lines))

    designer_service = read_text(
        os.path.join(REPO, "webapp", "services", "designer.py"))
    for needle in ("from design.workbench_form import",
                   "build_pattern_spec", "build_runner_config",
                   "readiness_errors", "run_pipeline",
                   "read_extract_candidates", "export_selected"):
        check("webapp/services/designer.py uses %s" % needle,
              needle in designer_service)


def main():
    module = load_backup()
    print("backup module: %s" % BACKUP_PATH)
    run_static_checks()
    cases = build_cases()
    for case in cases:
        run_case_checks(module, case)
    run_preset_checks(module)
    run_active_side_checks(module)
    run_model_option_checks(module)
    failed = [name for name, ok in RESULTS if not ok]
    print("")
    print("checks: %d, passed: %d, failed: %d"
          % (TOTAL[0], TOTAL[0] - len(failed), len(failed)))
    for name in failed:
        print("  FAILED: %s" % name)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
