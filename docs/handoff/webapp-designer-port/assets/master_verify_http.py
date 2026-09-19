"""Master HTTP probe for the handoff task ``webapp-designer-port``.

Runs against a live ``python webapp/app.py --port <port>`` server and checks
schema parity with the shared modules, the JSON routing, the readiness
rejections, static-file and download whitelists, one real ``find`` job with
candidates + export + download, and a ``score`` job stopped through the cancel
endpoint.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8341"
REPO = r"R:\songji\programfile"
for entry in (REPO, os.path.join(REPO, "shared")):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from design.library_preflight import ENGINE_CHOICES          # noqa: E402
from design.system_presets import preset_choices              # noqa: E402
from design.workbench_form import (                           # noqa: E402
    MODE_LABELS,
    PAIR_RANK_POLICY_FIELDS,
    PRESET_KEYS,
    active_side_updates,
    side_preset_updates,
)
from output.candidate_export import SUPPORTED_FORMATS         # noqa: E402
from webapp import schema as webapp_schema                    # noqa: E402

FIXTURE = os.path.join(REPO, "out", "master_verify_w1")
TARGET_FA = os.path.join(FIXTURE, "target.fa")
GENOME = os.path.join(REPO, "example", "engine_benchmark", "synthetic_genome.fa")

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
            print("      %s" % str(detail)[:1000])


def note(text):
    print("      .. %s" % text)


def request(method, path, payload=None, timeout=300):
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(
        BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()
    except Exception as exc:  # noqa: BLE001
        return -1, ("%s: %s" % (type(exc).__name__, exc)).encode("utf-8")


def as_json(status, body):
    try:
        return json.loads(body.decode("utf-8"))
    except Exception:  # noqa: BLE001
        return None


def values_of(items):
    out = []
    for item in items:
        out.append(item["value"] if isinstance(item, dict) else item)
    return out


def read(path):
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def write_fixture():
    if not os.path.isdir(FIXTURE):
        os.makedirs(FIXTURE)
    with open(TARGET_FA, "w", encoding="ascii", newline="\n") as handle:
        handle.write(">t1\n" + "ACGT" * 10 + "\n")


def schema_checks():
    data = webapp_schema.build_schema()
    designer = data["designer"]
    field_keys = list(webapp_schema.designer_field_keys())
    collected = set()
    for field in designer["common_fields"]:
        collected.add(field["key"])
    for field in designer["run_fields"]:
        collected.add(field["key"])
    for _mode, form in designer["pattern_forms"].items():
        for _slot, group in form.items():
            for field in group.get("fields", []):
                if field.get("key"):
                    collected.add(field["key"])
    for name in data["pair_rank_fields"]:
        collected.add("pair_rank_" + name)
    missing = sorted(key for key in field_keys if key not in collected)
    check("schema renders all %d designer field keys" % len(field_keys),
          not missing, "missing=%s" % missing)

    check("modes match MODE_LABELS",
          values_of(data["modes"]) == list(MODE_LABELS.keys())
          and [m["label"] for m in data["modes"]] == [
              MODE_LABELS[key] for key in MODE_LABELS],
          "%s" % values_of(data["modes"]))
    check("presets match PRESET_KEYS",
          values_of(data["presets"]) == list(PRESET_KEYS),
          "%s" % values_of(data["presets"]))
    check("engines match ENGINE_CHOICES",
          values_of(data["engines"]) == list(ENGINE_CHOICES),
          "%s" % values_of(data["engines"]))
    check("export formats match SUPPORTED_FORMATS",
          values_of(data["export_formats"]) == list(SUPPORTED_FORMATS),
          "%s" % values_of(data["export_formats"]))
    check("pair rank fields match PAIR_RANK_POLICY_FIELDS",
          list(data["pair_rank_fields"]) == list(PAIR_RANK_POLICY_FIELDS))
    check("hidden candidate columns are query_seq/gap_seq",
          tuple(data["hidden_candidate_columns"]) == ("query_seq", "gap_seq"),
          "%s" % data["hidden_candidate_columns"])

    for mode in ("single_motif_flank", "motif_gap_motif", "y_centered_motifs"):
        form = designer["pattern_forms"].get(mode) or {}
        kinds = []
        for slot in ("left", "middle", "right"):
            for field in (form.get(slot) or {}).get("fields", []):
                kinds.append(field.get("type") or field.get("key"))
        expected_slots = ({"left"} if mode == "single_motif_flank"
                          else {"left", "middle", "right"})
        check("pattern_forms[%s] slots" % mode,
              set(form) == expected_slots, "%s" % sorted(form))
        if mode == "single_motif_flank":
            check("single mode has preset / use-for-run / side models",
                  "side_preset" in kinds and "use_for_run" in kinds
                  and "side_models" in kinds, "%s" % kinds)
        else:
            check("%s exposes both TAM sides" % mode,
                  kinds.count("side_preset") == 2
                  and kinds.count("use_for_run") == 2
                  and kinds.count("side_models") == 2, "%s" % kinds)
    y_form = designer["pattern_forms"]["y_centered_motifs"]
    y_keys = [field.get("key") for slot in y_form.values()
              for field in slot.get("fields", [])]
    check("y-centred mode exposes y_sequence", "y_sequence" in y_keys,
          "%s" % y_keys)

    html = read(os.path.join(REPO, "webapp", "index.html"))
    for marker in ("designer-find", "designer-score", "designer-ready",
                   "designer-progress-bar", "designer-progress-label",
                   "designer-log", "designer-candidates", "designer-describe",
                   "designer-export-format", "designer-export", "Find Targets",
                   "Score &amp; Off-target", "designer-loaded-hint"):
        check("index.html has %r" % marker, marker in html)
    scripts = read(os.path.join(REPO, "webapp", "static", "app.js"))
    check("app.js posts to /api/designer/jobs",
          "/api/designer/jobs" in scripts)
    service = read(os.path.join(REPO, "webapp", "services", "designer.py"))
    check("candidate columns are filtered server side",
          "HIDDEN_COLUMNS" in service
          and "if column not in HIDDEN_COLUMNS" in service)


def job_status(job_id):
    status, body = request("GET", "/api/jobs/%s" % job_id)
    return status, as_json(status, body)


def wait_job(job_id, timeout=1800, want=("succeeded", "failed", "cancelled",
                                        "interrupted")):
    deadline = time.time() + timeout
    info = None
    while time.time() < deadline:
        status, info = job_status(job_id)
        if status != 200 or not isinstance(info, dict):
            return status, info
        if info.get("status") in want:
            return status, info
        time.sleep(4)
    return status, info


def server_checks():
    payload = {
        "stage": "find",
        "mode": "single_motif_flank",
        "input_mode": "sequence",
        "values": {
            "search_fasta": TARGET_FA,
            "genome_fasta": GENOME,
            "output_dir": FIXTURE,
            "motif": "TACG",
            "flank": "5",
            "side": "upstream",
        },
    }

    status, body = request("GET", "/")
    check("GET / -> 200", status == 200, status)
    text = body.decode("utf-8", "replace")
    check("index served with Designer shell",
          "designer-find" in text and "CRISPR Motif Workbench" in text)

    status, body = request("GET", "/api/schema")
    live = as_json(status, body)
    check("GET /api/schema -> 200", status == 200, status)
    check("GET /api/schema matches build_schema()",
          live == webapp_schema.build_schema())

    for name, path in (("app.js", "/static/app.js"),
                       ("styles.css", "/static/styles.css")):
        status, body = request("GET", path)
        check("GET %s -> 200 (%d bytes)" % (path, len(body)), status == 200,
              status)
    status, _body = request("GET", "/static/..%2fapp.py")
    check("static traversal /static/..%2fapp.py rejected", status in (400, 404),
          status)
    status, _body = request("GET", "/static/nope.js")
    check("unknown static file -> 404", status == 404, status)

    status, body = request("POST", "/api/designer/preview", payload)
    preview = as_json(status, body)
    check("POST /api/designer/preview -> 200", status == 200, status)
    check("preview has no errors and a describe string",
          isinstance(preview, dict) and preview.get("errors") == []
          and bool(preview.get("describe")),
          json.dumps(preview if not isinstance(preview, dict)
                     else {k: v for k, v in preview.items()
                           if k in ("errors", "describe")},
                     ensure_ascii=False)[:300])
    note("preview: %s" % json.dumps(
        {k: v for k, v in (preview or {}).items() if k != "warnings"},
        ensure_ascii=False)[:300])

    bad = dict(payload)
    bad["values"] = dict(payload["values"], output_dir="")
    status, body = request("POST", "/api/designer/preview", bad)
    preview_bad = as_json(status, body)
    check("preview reports the missing Output Directory",
          isinstance(preview_bad, dict)
          and "Output Directory is required" in (preview_bad.get("errors") or []),
          "%s" % (preview_bad or {}).get("errors"))

    status, body = request("POST", "/api/designer/preset",
                           {"side": "left", "preset": "cas12a"})
    preset = as_json(status, body)
    check("POST /api/designer/preset -> 200", status == 200, status)
    check("preset updates == side_preset_updates('cas12a', 'left')",
          isinstance(preset, dict)
          and preset.get("updates") == side_preset_updates("cas12a", "left"),
          "%s" % (preset or {}).get("updates"))

    side_payload = dict(payload["values"])
    side_payload.update({"mode": "single_motif_flank",
                         "input_mode": "sequence", "active_side": "left",
                         "side_presets": {"left": "cas12a", "right": "cas9",
                                          "target": "cas9"}})
    status, body = request("POST", "/api/designer/active-side", side_payload)
    active = as_json(status, body)
    check("POST /api/designer/active-side -> 200", status == 200, status)
    from webapp.services.designer import state_from_payload  # noqa: E402
    state = state_from_payload(side_payload)
    state.active_side = "left"
    check("active-side updates == active_side_updates(state)",
          isinstance(active, dict)
          and active.get("updates") == active_side_updates(state),
          "%s" % (active or {}).get("updates"))

    rejections = [
        ("missing Output Directory", {"output_dir": ""},
         "Output Directory is required"),
        ("missing Search FASTA", {"search_fasta": ""},
         "Search FASTA is required"),
        ("search FASTA not found",
         {"search_fasta": os.path.join(FIXTURE, "nope.fa")},
         "Search FASTA not found: %s" % os.path.join(FIXTURE, "nope.fa")),
        ("custom memory below 512 MiB",
         {"memory_mode": "custom", "max_memory_mb": "16"},
         "Memory limit: Custom MiB must be at least 512"),
        ("timeout <= 0", {"search_timeout_s": "-1"},
         "Search timeout: Search timeout must be greater than zero"),
    ]
    for name, override, expected in rejections:
        bad = dict(payload)
        bad["values"] = dict(payload["values"], **override)
        status, body = request("POST", "/api/designer/jobs", bad)
        info = as_json(status, body)
        check("jobs rejects %s -> 400" % name, status == 400, status)
        check("jobs rejection text for %s" % name,
              isinstance(info, dict) and info.get("error") == expected,
              "got %r want %r" % ((info or {}).get("error"), expected))

    score_first = dict(payload)
    score_first["stage"] = "score"
    score_first["values"] = dict(payload["values"], output_dir=os.path.join(
        REPO, "out", "master_verify_w1_empty"))
    status, body = request("POST", "/api/designer/jobs", score_first)
    info = as_json(status, body)
    check("score before extract -> 400", status == 400, status)
    check("score before extract message",
          isinstance(info, dict)
          and info.get("error") == "Extracted targets not found. "
          "Run Find Targets first.",
          "%s" % (info or {}).get("error"))

    status, _body = request("POST", "/api/designer/jobs",
                            {"stage": "nope"})
    check("unknown stage rejected", status == 400, status)

    status, body = request("GET", "/api/jobs")
    jobs = as_json(status, body)
    check("GET /api/jobs -> 200 with a job list", status == 200
          and isinstance(jobs, dict) and isinstance(jobs.get("jobs"), list),
          "%s %s" % (status, type(jobs)))
    if isinstance(jobs, dict) and jobs.get("jobs"):
        created = [entry.get("created") for entry in jobs["jobs"]]
        note("jobs newest first: %s" % created[:4])
        check("job list is newest first",
              created == sorted(created, reverse=True), "%s" % created[:4])
    status, body = request("GET", "/api/jobs/zzzzzzzzzzzz")
    check("unknown (well-formed) job id -> 404", status == 404, status)
    status, body = request("GET", "/api/jobs/doesnotexist00")
    check("malformed job id -> 400", status == 400, status)
    status, body = request("GET", "/api/jobs/../../main.py")
    check("job id traversal rejected", status in (400, 404), status)

    status, body = request("GET", "/api/models")
    models = as_json(status, body)
    check("GET /api/models -> 200", status == 200, status)
    groups = (models or {}).get("groups") if isinstance(models, dict) else None
    check("models payload carries groups", bool(groups), "%s" % type(models))
    if isinstance(models, dict):
        keys = []
        for group in models.get("groups") or []:
            for entry in group.get("models") or []:
                keys.append(entry.get("key"))
        note("model keys: %s" % keys)

    status, body = request("GET", "/api/outputs?dir=" + urllib.parse.quote(
        FIXTURE))
    outputs = as_json(status, body)
    check("GET /api/outputs -> 200", status == 200, status)
    files = outputs.get("files") if isinstance(outputs, dict) else None
    names = []
    if isinstance(files, list):
        names = [item.get("name") if isinstance(item, dict) else item
                 for item in files]
    check("outputs lists the fixture files", "target.fa" in names,
          "%s" % names)
    status, body = request("GET", "/api/outputs?dir=" + urllib.parse.quote(
        os.path.join(REPO, "example")))
    check("outputs for another directory still answered",
          status in (200, 400, 403), status)

    return payload


def real_job_checks(payload):
    status, body = request("POST", "/api/designer/jobs", payload)
    submitted = as_json(status, body)
    check("POST /api/designer/jobs (find) accepted", status in (200, 202),
          "%s %s" % (status, submitted))
    job_id = (submitted or {}).get("job_id")
    check("job id shape", bool(job_id) and len(str(job_id)) == 12
          and str(job_id).isalnum(), job_id)
    if not job_id:
        return None
    note("find job: %s" % job_id)

    status, info = wait_job(job_id)
    check("find job finished", isinstance(info, dict)
          and info.get("status") in ("succeeded", "failed"),
          "%s" % (info or {}).get("status"))
    final = (info or {}).get("status")
    check("find job succeeded", final == "succeeded",
          "%s message=%r" % (final, (info or {}).get("message")))
    note("find status=%s progress=%s message=%r"
         % (final, (info or {}).get("progress"), (info or {}).get("message")))

    status, body = request("GET", "/api/jobs/%s/log?offset=0" % job_id)
    log = as_json(status, body)
    check("GET log?offset=0 -> 200 with text", status == 200
          and isinstance(log, dict) and bool(log.get("text")), status)
    offset = (log or {}).get("offset")
    status, body = request("GET", "/api/jobs/%s/log?offset=%s"
                           % (job_id, offset))
    log2 = as_json(status, body)
    check("incremental log offset honoured", isinstance(log2, dict)
          and log2.get("text") == "", "%s" % (log2 or {}).get("text"))
    status, body = request("GET", "/api/jobs/%s/log?offset=-5" % job_id)
    check("bad log offset answered", status == 200, status)

    status, body = request("GET", "/api/jobs/%s/candidates" % job_id)
    cand = as_json(status, body)
    check("GET candidates -> 200", status == 200, status)
    columns = (cand or {}).get("columns") or []
    rows = (cand or {}).get("rows") or []
    check("candidates hide query_seq/gap_seq",
          "query_seq" not in columns and "gap_seq" not in columns,
          "%s" % columns)
    check("candidates carry rows", bool(rows), "total=%s" % (cand or {}).get("total"))
    note("candidates total=%s columns=%s" % ((cand or {}).get("total"), columns))

    status, body = request("POST", "/api/jobs/%s/export" % job_id,
                           {"format": "tsv", "rows": [0], "filename": "probe.tsv"})
    exported = as_json(status, body)
    check("POST export -> 200", status == 200, "%s %s" % (status, exported))
    url = (exported or {}).get("download_url")
    check("export reported one written row and a download url",
          (exported or {}).get("written") == 1 and bool(url),
          "%s" % exported)
    if url:
        status, body = request("GET", url)
        check("download of the exported file -> 200", status == 200, status)
        check("downloaded file has the candidate header",
              b"seq_id" in body or b"query_id" in body, body[:120])

    status, body = request("GET", "/api/jobs/%s/download?file=../../main.py"
                           % job_id)
    check("download traversal rejected", status == 400, status)
    status, body = request("GET", "/api/jobs/%s/download?file=evil.tsv" % job_id)
    check("download of a non-whitelisted name rejected", status == 400, status)

    status, body = request("POST", "/api/jobs/%s/export" % job_id,
                           {"format": "nope", "rows": [0]})
    check("unknown export format rejected", status == 400, status)
    status, body = request("POST", "/api/jobs/%s/export" % job_id,
                           {"format": "tsv", "rows": []})
    check("empty selection rejected", status == 400, status)

    score = dict(payload)
    score["stage"] = "score"
    status, body = request("POST", "/api/designer/jobs", score)
    score_job = as_json(status, body)
    check("POST /api/designer/jobs (score) accepted", status in (200, 202),
          "%s %s" % (status, score_job))
    score_id = (score_job or {}).get("job_id")
    if score_id:
        note("score job: %s" % score_id)
        time.sleep(12)
        status, body = request("POST", "/api/jobs/%s/cancel" % score_id)
        cancelled = as_json(status, body)
        check("POST cancel -> 200", status == 200,
              "%s %s" % (status, cancelled))
        note("cancel response: %s" % cancelled)
        status, info = wait_job(score_id, timeout=600)
        final = (info or {}).get("status")
        check("cancelled job left the running state", final != "running",
              "%s" % (info or {}))
        note("score status=%s message=%r" % (final, (info or {}).get("message")))
    return job_id


def main():
    write_fixture()
    schema_checks()
    payload = server_checks()
    real_job_checks(payload)
    failed = [name for name, ok in RESULTS if not ok]
    print("")
    print("checks: %d, passed: %d, failed: %d"
          % (TOTAL[0], TOTAL[0] - len(failed), len(failed)))
    for name in failed:
        print("  FAILED: %s" % name)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
