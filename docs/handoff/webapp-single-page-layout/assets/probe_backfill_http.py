"""End-to-end probe for P0-3 + P0-1 (webapp-single-page-layout).

What it proves:

1. ``status.json`` / ``GET /api/jobs/<id>`` carry the new ``outputs`` map and
   every value is an existing absolute path (task 1.4).
2. The scenario the UI's back-fill depends on: a user has already typed
   ``output_dir`` by hand, so the job's ``outputs.output_dir`` must come back
   byte-for-byte identical (nothing is overwritten) while the value the user
   left empty (the Search FASTA) is available to fill it in.

Run against a running local server (default http://127.0.0.1:8123):

    python docs/handoff/webapp-single-page-layout/assets/probe_backfill_http.py
    python .../probe_backfill_http.py --port 8124
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
GENOME = os.path.join(ROOT, "example", "engine_benchmark", "synthetic_genome.fa")

SEARCH_FASTA = ">probe_target\nACGTACGTACGTACGTACGTACGTACGTACGTACGTACGT\n"
ANNOTATION = (
    "##gff-version 3\n"
    "chr1\tprobe\tgene\t1001\t1200\t.\t+\t.\tID=gene:PROBE1;gene_id=PROBE1;"
    "gene_name=PROBE1\n"
    "chr1\tprobe\tmRNA\t1001\t1200\t.\t+\t.\tID=transcript:PROBE1.t1;"
    "Parent=gene:PROBE1;gene_id=PROBE1\n"
    "chr1\tprobe\tCDS\t1001\t1200\t.\t+\t0\tID=cds:PROBE1.t1;"
    "Parent=transcript:PROBE1.t1;gene_id=PROBE1\n"
)

failures = []


def check(label, condition, detail=""):
    print(("PASS " if condition else "FAIL ") + label
          + (("  -> " + detail) if detail and not condition else ""))
    if not condition:
        failures.append(label)


def request(url, payload=None):
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8123)
    args = parser.parse_args()
    base = "http://%s:%d" % (args.host, args.port)

    work = os.path.join(ROOT, "out", "probe_backfill")
    os.makedirs(work, exist_ok=True)
    search_fasta = os.path.join(work, "probe_target.fa")
    annotation = os.path.join(work, "probe_annotation.gff")
    with open(search_fasta, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(SEARCH_FASTA)
    with open(annotation, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(ANNOTATION)

    check("synthetic genome fixture exists", os.path.isfile(GENOME), GENOME)
    if failures:
        return 1

    # The user typed this by hand in the main area before opening the drawer.
    pre_filled_output_dir = os.path.join(work, "hand_typed_output")
    os.makedirs(pre_filled_output_dir, exist_ok=True)

    payload = {
        "genome": GENOME,
        "annotation": annotation,
        "output_dir": pre_filled_output_dir,
        "target_id": "PROBE1",
        "target_id_type": "gene_name",
        "target_region": "Coding region",
        "skip_mask": True,
    }
    print("POST /api/dataprep/extract-target")
    print("  output_dir (typed by the user) = " + pre_filled_output_dir)
    print("  search_fasta (left empty)      -> outputs.target_fasta")
    submitted = request(base + "/api/dataprep/extract-target", payload)
    job_id = submitted["job_id"]
    print("  job_id = " + job_id)

    deadline = time.time() + 300
    job = None
    while time.time() < deadline:
        job = request(base + "/api/jobs/" + job_id)
        if job.get("status") in ("succeeded", "failed", "cancelled", "interrupted"):
            break
        time.sleep(2)
    print("GET /api/jobs/%s -> status=%s message=%s"
          % (job_id, job.get("status"), job.get("message")))
    check("job succeeded", job.get("status") == "succeeded",
          json.dumps(job, ensure_ascii=False))
    if failures:
        return 1

    outputs = job.get("outputs") or {}
    print("outputs = " + json.dumps(outputs, indent=2, ensure_ascii=False))

    check("outputs is present and non-empty", bool(outputs))
    for key, value in sorted(outputs.items()):
        check("outputs.%s is an existing absolute path" % key,
              os.path.isabs(value) and os.path.exists(value), str(value))

    check("outputs.output_dir equals what the user typed (not overwritten)",
          outputs.get("output_dir") == pre_filled_output_dir,
          "%r != %r" % (outputs.get("output_dir"), pre_filled_output_dir))

    target = outputs.get("target_fasta")
    check("outputs has target_fasta (feeds the empty search_fasta field)",
          bool(target))
    if target:
        check("target_fasta points at the extracted FASTA",
              os.path.isfile(target) and os.path.getsize(target) > 0, str(target))
        with open(target, "r", encoding="utf-8") as handle:
            head = handle.read(80).strip()
        print("  target_fasta head: " + head.replace("\n", " | "))

    # The list endpoint must expose the same field (legacy dirs get {}).
    listing = request(base + "/api/jobs")
    match = [entry for entry in listing.get("jobs", [])
             if entry.get("job_id") == job_id]
    check("GET /api/jobs lists the job", bool(match))
    if match:
        check("GET /api/jobs carries outputs",
              (match[0].get("outputs") or {}).get("target_fasta") == target)
    legacy = [entry for entry in listing.get("jobs", [])
              if not entry.get("outputs")]
    print("jobs without outputs (legacy dirs must still expose {}): %d"
          % len(legacy))

    status_path = os.path.join(ROOT, "webapp", "jobs", job_id, "status.json")
    with open(status_path, "r", encoding="utf-8") as handle:
        on_disk = json.load(handle)
    check("status.json on disk carries outputs",
          (on_disk.get("outputs") or {}).get("target_fasta") == target)

    print("")
    print("probe_backfill_http.py: " + ("all checks passed" if not failures
                                        else "%d check(s) FAILED" % len(failures)))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())