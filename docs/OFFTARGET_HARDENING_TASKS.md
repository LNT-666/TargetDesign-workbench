# Off-target engine hardening tasks

Handoff spec. Written 2026-09-14 by a Codex session after triaging a stuck
`--engine indexed` run. Source of the two Chinese-named CLI options:
`basic/blast.py` (`--屏蔽基因`, `--输出目录`).

## 0. Why this exists

A user run (`--engine indexed`, 122 guides, `--max-mismatch 4 --max-bulge 1`,
GRCh38) reached 6 h 52 m wall / 8 d 22 h CPU / 245 GB RSS and had to be killed
by hand. Triaging it separated two kinds of finding:

* **Algorithmic cost (expected, not a bug).** Bulge-tolerant search on a
  3.3 Gbp genome is combinatorially enormous. `INDEXED_BULGE_DEFAULT_MAX_BASES =
  50000000` (`shared/search/offtarget_backend.py:38`) already defaults large
  genomes to mismatch-only, but an explicit `max_bulge`/`--max-bulge` bypasses
  that guard by design.
* **Code defects (this document).** No progress output, silent Python fallback,
  index path collisions, wrong gggenome results, orphaned child processes.

## 1. Ground rules (read before editing)

* **No version control.** `R:/songji/programfile` is not a git repository.
  Back up every file you change; `backup/` holds earlier snapshots named
  `<topic>_<YYYYMMDD_HHMMSS>`.
* **Encoding hazard.** `R:/songji/programfile` is the same filesystem as
  `/home/apool/songji/programfile` on the Linux server (network mount).
  `basic/blast.py` contains Chinese text (395 non-ASCII chars). On this
  Chinese-Windows host `Get-Content` / `Set-Content` / `Out-File` silently
  corrupt UTF-8 files that contain non-ASCII content. Use `apply_patch`, or
  drive the edit from an ASCII-only Python file.
* **Verify every non-ASCII file you touch.** Hash the non-ASCII characters
  before editing and assert the hash is unchanged afterwards, plus
  `compile(open(path, encoding="utf-8").read(), path, "exec")`:

  ```python
  non = "".join(c for c in open(path, encoding="utf-8").read() if ord(c) > 127)
  ```

  Baselines at the time of writing: `shared/search/offtarget_backend.py` 15
  chars, `shared/design/pattern_runner.py` 8, `basic/blast.py` 395,
  `designer_workbench.py` 0.
* **Running tests.** On the server (has Bio/numpy/pyfaidx + the native binary):

  ```bash
  cd /home/apool/songji/programfile
  export PYTHONPATH=shared
  .venv/bin/python -m unittest discover -s tests -p "test_offtarget_backend.py"
  ```

  `test_designer_workbench.py` and `test_unified_gui.py` need a display, so run
  them on the Windows host (local Python has tkinter, Bio, numpy, pyfaidx,
  openpyxl). Everything: `python run_tests.py`.
  Caveat measured on this Windows host (2026-09-14): `blastn` is not on
  PATH, so `test_auto_and_large_indexed_apply_mismatch_only_defaults`
  (tests/test_offtarget_backend.py:245) errors with `auto could not find an
  engine compatible with max_bulge=0`. That is an environment artefact
  (engine discovery, unrelated to the fallback work) and it passes on the
  server. Everything else is green: 38 + 28 backend/runner tests and 28
  designer tests; 94 tests ran locally with this single error.
* **Server facts.** 256 cores, 1 TB RAM. Native engine
  `native/bin/offtarget-engine` with commands `build-index`, `inspect-index`,
  `search`, `capabilities`; `--version` reports `index-format=1`. Genome:
  `/home/apool/songji/genome/Homo_sapiens/GCF_000001405.40_GRCh38.p14_genomic.fna`.
  Triage scratch project: `scy-test/trac-exon3/`.
* Never use the full GRCh38 bulge search as a test. Use a small genome, or
  `--engine blast`.

## 2. Already done (do not redo)

Present in the working tree:

* `shared/search/offtarget_backend.py` - new `PYTHON_FALLBACK_ENV`,
  `PYTHON_FALLBACK_POLICIES`, `PYTHON_FALLBACK_PROMPT`, `PythonFallbackDeclined`,
  `resolve_python_fallback_policy()`, `ask_python_fallback_on_stdin()`,
  `approve_python_fallback()` (~line 85). `IndexedBackend.search()` calls
  `approve_python_fallback()` before `_search_python()` (`:1062`) and raises
  `PythonFallbackDeclined` (`:1069`) when refused;
  `last_report["native_fallback_reason"]` is always recorded.
* `shared/design/pattern_runner.py` - `CONFIRM_REQUIRED_PREFIX`,
  `parse_confirm_request()`, `python_fallback_env()`. `run_pipeline()` passes
  `stdin=subprocess.PIPE`, injects `CRISPR_OFFTARGET_PYTHON_FALLBACK=ask` into
  every child step, accepts `on_prompt=`, answers `CONFIRM_REQUIRED:` lines with
  `yes`/`no`, and defaults to `no` when no handler is registered.
* `designer_workbench.py` - `_confirm_pipeline_prompt()` (Tk `askyesno` on the
  Tk thread while the worker thread waits) and `_log_writer_note()`;
  `_run_steps()` passes `on_prompt=`. The fallback reason and the user decision
  go to the UI log and to `logs/designer_workbench_<ts>.log`.
* `basic/blast.py` - `--python-fallback {ask,allow,deny}` (resolution order:
  flag, then `$CRISPR_OFFTARGET_PYTHON_FALLBACK`, then `ask`),
  `make_python_fallback_confirm()`, `build_search_extra()`, and
  `search(..., log=log)`.
* Tests added, all green: `tests/test_offtarget_backend.py` (38),
  `tests/test_pattern_runner.py` (28), `tests/test_designer_workbench.py` (28,
  Windows only), `tests/test_offtarget_hardening.py` (17, see 11).

Met acceptance: a refused fallback aborts with a clear message and exit code 3,
an approved one proceeds, and the reason is logged either way.

Closed since this handoff: the `CONFIRM_REQUIRED:` handshake between
`PatternRunner.run_pipeline()` and a real child process is now covered end to
end by `ConfirmHandshakeEndToEndTests` in `tests/test_offtarget_hardening.py`,
whose stub step really writes `CONFIRM_REQUIRED: ...` to stdout and is answered
`yes` (exit 0) or `no` (exit 4). See 12.

## 3. Task 1 (P0) - stream native search progress

**Problem.** `native_offtarget.search()` uses
`subprocess.run(capture_output=True, ...)` (`shared/search/native_offtarget.py:234`),
so every JSONL event is buffered until the process exits;
`IndexedBackend._search_native()` then replays
`search_report.pop("progress_events")` only after the search returns
(`shared/search/offtarget_backend.py:921`). A multi-hour search therefore prints
**no** `PROGRESS_TARGET:` / `PROGRESS:` lines at all and the GUI looks frozen.
`_run_json_command()` (`native_offtarget.py:139`) has the same problem for
`build-index`: a full GRCh38 build took 1569 s with zero output.

**Do.**
* Rewrite `search()` with `subprocess.Popen(text=True, stdout=PIPE, stderr=PIPE)`
  and consume stdout line by line while the process runs, parsing each line as
  JSON immediately: `hit` -> collect, `meta`/`summary` -> record,
  `progress` -> call a new `progress_callback(done, total, qid)` argument,
  `error` -> raise. Drain `stderr` from a reader thread so a chatty engine
  cannot deadlock on a full pipe.
* `IndexedBackend._search_native()` must forward that callback live instead of
  replaying a list. Keep the `PROGRESS_TARGET: <done>/<total>` shape -
  `_handle_command_line` in `designer_workbench.py` parses it.
* Do the same for `build_index()`; `search` supports `--progress-every`, check
  whether `build-index` reports progress and at minimum keep the process
  observable instead of silent.
* Keep `search()`'s `(hits_by_qid, report)` contract and keep `report`
  JSON-serializable.

**Acceptance.** `tests/test_native_indexed.py` still passes; a new test proves
the callback fires before the child exits (e.g. the fake child blocks on a pipe
the test controls, and the test asserts the callback already ran); on the
server, a small `--engine indexed` run shows `PROGRESS_TARGET:` lines *during*
the run.

## 4. Task 2 (P0) - no orphans: timeouts and process lifetime

**Problem.** `native_offtarget.search()` has **no timeout** (`probe_binary()`
does pass `timeout=15`; `search` and `build_index` do not) and creates no
process group, so killing the Python parent leaves the engine running. Observed
twice:

* pid 1798759: `basic/blast.py --engine indexed` orphaned (PPID 1) for 8 h at
  1 core / 15.6 GB, stdout pipe to a dead parent - result undeliverable.
* pid 2156421 + child 2201453: GUI closed, job ran 6 h 52 m wall / 8 d 22 h CPU
  / 245 GB RSS. `SIGTERM` was ignored and `SIGKILL` needed ~30 s to tear down
  the address space.

**Do.**
* Start the engine with `start_new_session=True` and guarantee cleanup: wrap
  `Popen` in `try/finally`; on `BaseException` send `SIGTERM` to the group, wait
  briefly, then `SIGKILL`
  (`os.killpg(os.getpgid(proc.pid), sig)`).
* Cover the parent-killed path too. On Linux `prctl(PR_SET_PDEATHSIG, SIGKILL)`
  is the most robust; a `signal`/`atexit` handler is the portable fallback.
* Add an opt-in timeout (`SearchParams.extra["timeout_s"]`, CLI/Tk knob) that
  raises a clear error instead of hanging. Default to no timeout so legitimate
  long runs are not broken, but document the knob.
* GUI side: `PatternRunner.run_pipeline()` should tear down the whole child
  tree when the pipeline is stopped or the app closes
  (`designer_workbench.py:_on_close`, `_finish_run`).

**Acceptance.** New test: start a long fake child through the backend, kill the
parent (or raise mid-run), assert the child is reaped. Server check: kill
`blast.py` mid-search and confirm `pgrep -a offtarget-engin` is empty. GUI
check: closing the window during a search leaves no engine process.

## 5. Task 3 (P1) - index path collisions between concurrent runs

**Problem.** `IndexedBackend._index_prefix()` derives the prefix from the output
directory (`<output_dir>/genome_index/<genome basename>`), and
`_search_native()` calls `build_index(..., force=True)` whenever the index does
not validate (`shared/search/offtarget_backend.py:892`). `k` is chosen per run
from genome size plus guide lengths and mismatch/bulge (`select_index_k`), so two
runs sharing an output directory can pick different `k` and rebuild each other's
index. Observed live: the 14:57 run rewrote the 12.5 GB `.ggi` at the prefix the
10:10 run was still reading, and a `native/bin/.nfs*` entry showed the engine
binary being replaced while a process had it open.

**Do.** Namespace the index by the parameters that affect it
(`<genome>.k<k>.ggi`), or store it outside the per-run output directory (next to
the genome), or take an exclusive lock (`flock` on `<prefix>.lock`) and fail
with an actionable message when another run holds it. Never silently rebuild an
index another process is reading. Keep `--index-path` as an explicit override.

**Acceptance.** New test: two backends sharing an output dir with different `k`
requirements either reuse a validated index or raise a clear lock error. Manual
check: two concurrent small-genome runs never replace an in-use `.ggi`.

## 6. Task 4 (P1) - gggenome returns wrong results silently

**Problem.** `GGGenomeBackend.search()` sends
`mismatch = params.max_mismatch + params.max_bulge`
(`shared/search/offtarget_backend.py:740`) without checking that the API honoured
it. Measured on the lab server (2026-09-14, `https://gggenome.dbcls.jp`):

* `CCAGAACCCTGACCCTGCCGTGT.txt?mismatch=0|1|2` - the base 23-mer returns
  `count: 1`, while a 1-mismatch variant of the same sequence returns
  `count: 0` at **every** mismatch value.
* `AAAAAAAAAAAAAAAAAAAA.txt?mismatch=0|1|2` - identical counts (102417).
* All 7 PAM-prepended TRAC windows from `scy-test/trac-exon3` returned **0
  hits**, including windows whose TRAC locus exists in the genome.

So the engine reports "no off-targets" when the truth is "this was not a
mismatch search". The existing `gggenome_offtargets.tsv` is therefore
meaningless.

**Do** (pick one, then document it):
* Probe the API once per session with a known 1-mismatch pair and refuse
  (raise) when `mismatch` is demonstrably ignored, instead of returning `{}`.
* Or make the engine honest: request `mismatch=0` only and flag hits plus the
  report as exact-match-only, so scoring cannot treat it as a full search.
* Never send a PAM-prepended query without confirming the semantics: prepending
  the PAM turns an off-target search into a plain substring search for
  `<PAM><guide>`.

**Acceptance.** A test with a stubbed API response shows the backend raises (or
flags exact-only) instead of returning `{}` when `mismatch` is ignored, and
`docs/OFFTARGET_ENGINES.md` states the real capability.

## 7. Task 5 (P2) - remaining silent-fallback entry points

`approve_python_fallback()` defaults to `allow` when neither
`SearchParams.extra["python_fallback"]` nor `$CRISPR_OFFTARGET_PYTHON_FALLBACK`
is set, so programmatic callers keep the historical behaviour:

* `basic/blast.py` sets a policy (covered; default `ask`).
* Inside the GUI pipeline every engine step inherits `ask` from
  `run_pipeline()` (covered), including
  `Target_xbp_Y_zbp_Target/blast_combined.py` (3 `backend.search()` calls, no
  `log=`).
* Run standalone, `tools/search_indexed.py` (1 call) and
  `Target_xbp_Y_zbp_Target/blast_combined.py` still degrade silently and never
  print the reason (it only lands in `last_report`).

**Do.** Pass `log=` plus an explicit policy from those entry points, or flip the
shared default to refusal and update callers and tests deliberately. Either way
the reason must reach stdout/stderr.

**Acceptance.** Every `get_backend(...).search(...)` caller passes `log=`; a
forced-fallback run of each entry point prints the reason.

## 8. Suggested order

1. Task 1 - progress; it is why a busy run was indistinguishable from a hung one.
2. Task 2 - orphans and timeouts; it is why two multi-hour jobs were wasted.
3. Task 3, Task 4, Task 5.
Then re-run `python run_tests.py` on the server and
`test_designer_workbench.py` on Windows.

## 9. The run that started this

`basic/blast.py <extracted_seqs.tsv> <GRCh38.fna>` with the two Chinese-named
options (`--屏蔽基因`, `--输出目录`), `--motif NGG --flank_len 20 --side upstream
--engine indexed --max-mismatch 4 --max-bulge 1 --require-pam --pam-motif NGG
--pam-side 3prime --seed-len 12`, output directory `scy-test/trac-exon3`.

## 10. Evidence to leave behind

So the work can be verified without re-reading every diff:

* A `backup/<topic>_<YYYYMMDD_HHMMSS>/` directory with a copy of every file you
  changed, taken before the first edit.
* The before/after non-ASCII character count for each touched file (see 1).
* The exact commands and their output for: the unit tests, `test_designer_workbench.py`
  on Windows, the Task 1 progress check, the Task 2 orphan check, and the Task 3
  concurrency check.
* A `## 11. What changed` section appended to this file: file, symbol, one line
  on why.
* Anything you deliberately left undone, and why.

## 11. What changed

Grouped by task. Every touched file compiles, keeps its pre-edit non-ASCII
fingerprint (or grows it only where the docs gained Chinese prose), and stays
LF without a BOM.

### Task 1 + Task 2 - streaming, timeouts, process lifetime

New file `shared/utils/child_process.py`

* `popen_kwargs()` - POSIX runs the child in its own session
  (`start_new_session=True`) and asks for `prctl(PR_SET_PDEATHSIG, SIGKILL)` so
  the engine dies with its parent; Windows uses `CREATE_NEW_PROCESS_GROUP`.
  `PROGRAMFILE_CHILD_PDEATHSIG=0` opts out.
* `terminate_process_tree()` - terminates the group, then the process itself;
  `TERMINATE_GRACE_S = 5.0` bounds the polite wait.
* `register_child()` / `unregister_child()` / `active_children()` /
  `reap_children()` plus `atexit` and SIGTERM/SIGINT handlers - a killed parent
  can no longer leave an engine behind.

`shared/search/native_offtarget.py`

* `NativeEngineTimeout` - `RuntimeError` subclass with `error_code = "TIMEOUT"`,
  deliberately *not* a `NativeEngineError`, so a timeout can never be retried by
  the much slower pure-Python engine.
* `resolve_timeout_s()` - explicit argument, else
  `PROGRAMFILE_OFFTARGET_TIMEOUT_S`, else `None` (no timeout).
* `_LineReader` and `_run_streaming()` - `Popen` with two reader threads instead
  of `subprocess.run(capture_output=True)`: stdout lines reach the caller while
  the child is still alive, stderr is drained so a chatty engine cannot deadlock
  on a full pipe, and every exit path terminates the process group.
* `BUILD_HEARTBEAT_S = 60.0` and `POLL_INTERVAL_S = 0.25` - a silent
  `build-index` still reports life.
* `search(..., progress_callback=, timeout_s=)` - progress is forwarded as it
  happens; the old "replay `progress_events` from the final report" block is
  gone.
* `build_index(..., log=, progress_callback=, timeout_s=)`,
  `inspect_index(..., timeout_s=)`, `_run_json_command(..., timeout_s=)`.

`shared/design/pattern_runner.py` (GUI runner)

* `RunnerConfig.timeout_s`, `STOPPED_RETURN_CODE = 130`, `_timeout_flags()`,
  `PatternRunner.stop()`.
* `run_pipeline()` uses `**popen_kwargs()` inside
  `try/finally: terminate_process_tree(proc)`; `_close_child_stdout()` closes the
  pipe on every path (including mocked runners whose `.stdout` is a list).

`designer_workbench.py`

* `PatternDesignerWorkbench._search_timeout_s()` reads the new "Search timeout
  (s)" row; the value feeds `RunnerConfig` and `_readiness_errors()`.
* `_on_close()` calls `runner.stop()` so closing the window no longer orphans a
  running search.
### Task 3 - index collisions between concurrent runs

`shared/search/offtarget_backend.py`

* `_index_prefix(genome_fasta, params, k=None)` - appends `.k<k>` to the derived
  prefix, unless `params.index_path` is an explicit override (used verbatim).
  Two runs that pick different `k` can no longer share one file.
* `index_build_lock(prefix, timeout_s=INDEX_LOCK_TIMEOUT_S, log=None)` with
  `_lock_file()` / `_unlock_file()` (`msvcrt.locking` on Windows, `fcntl.flock`
  elsewhere), `INDEX_LOCK_TIMEOUT_S = 600.0`, `INDEX_LOCK_POLL_S = 0.5`.
* `_search_native()` - the inspect-and-build pair now runs under that lock, so
  the loser waits, re-validates and reuses the freshly built index instead of
  overwriting a `.ggi` another process is reading. It also forwards live
  `PROGRESS:` / `PROGRESS_TARGET:` lines and the resolved `timeout_s`.
* `SearchParams.from_args()` - picks up `args.timeout_s`.

This is more than section 5 asked for: the section offered "namespace the path"
*or* "add a lock", and both were implemented, because renaming fixes the
different-`k` case while the lock fixes the same-`k`, same-second case.

### Task 4 - the gggenome budget

`shared/search/offtarget_backend.py`, `GGGenomeBackend`

* The budget is a URL *path* segment: `/<build>/<mismatch>/<query>.txt`. The old
  `?mismatch=N` shape is silently ignored by the service, which then answers with
  a perfectly valid *empty* result (measured live 2026-09-14, see 12).
* `_request()` / `_budget_from_url()` / `_api_error()` - a `### ... ERROR` body
  now raises a `RuntimeError` naming the guide, the budget and the fix, instead
  of being parsed as "no off-targets".
* `MAX_MISMATCH_FRACTION = 0.25` documents the service's ceiling.
* `self.last_report` carries `exact_only`, so a caller can tell an exact-only
  search from a substitution search.

Section 6's diagnosis was right about the symptom and wrong about the cause:
nothing needed a capability probe, the URL simply had to put the number where
the API reads it.

### Task 5 - the remaining silent-degradation entry points

* `basic/blast.py` - `--timeout-s`, forwarded into `SearchParams.extra`.
* `tools/search_indexed.py` - `--timeout-s` and
  `--python-fallback {ask,allow,deny}`; a fallback now prints the reason and
  exits 3 instead of degrading quietly.
* `Target_xbp_Y_zbp_Target/blast_combined.py` - local `report_line()` passed as
  `log=` to both search calls, plus `--timeout-s`.
* `Target_xbp_Target/analyze_complex_scores.py` - the same `report_line()` /
  `log=` treatment.
* `tools/benchmark_search.py`, `tools/benchmark_all_engines.py` -
  `log=lambda message: print(message, flush=True)`.

### Docs and tests

* `docs/OFFTARGET_ENGINES.md` - removed the incorrect claim that the GGGenome
  API takes a `mismatch` parameter; documented `--timeout-s`, the `.k<k>` index
  name and the `<prefix>.lock`.
* `README.md` - the same three behaviours in the memory-limit paragraph.
* `tests/test_offtarget_hardening.py` (new, 17 tests) - streaming callbacks,
  heartbeat, timeout, orphan handling, index namespacing and locking, GGGenome
  URL shape and error body, fallback reporting, and a real
  `CONFIRM_REQUIRED:` handshake.
* `tests/test_memory_limit.py` - `test_native_adapter_adds_build_and_search_flags`
  now patches `_run_streaming` (the adapter no longer calls `subprocess.run`).

### Deliberately not done

* No default timeout. A whole-genome bulge search is legitimately hours long, so
  `timeout_s` stays opt-in (`--timeout-s`, `PROGRAMFILE_OFFTARGET_TIMEOUT_S`).
* No active GGGenome capability probe. The service answers the wrong URL with a
  valid empty result, so a probe would cost an extra request per run for a
  question that the URL shape already answers; the tool now documents
  `exact_only` instead.
* The `--max-bulge` guard is unchanged. Section 9's 3.3 Gbp run was slow because
  an explicit `--max-bulge` bypasses the `5e7 bp` cost guard; that is the
  documented intent, not a bug, so it was left alone.
## 12. Evidence left behind

### Backup

`backup/offtarget_hardening_20260914_221157/` holds the pre-edit copy of every
touched file (13 entries in `BACKUP_MANIFEST.txt`) plus two extras:

* `nonscii_baseline.txt` - pre-edit non-ASCII count, non-ASCII hash and file hash
  per file.
* `README.md` - reconstructed after the fact, because the original copy was
  missed; the reconstruction was asserted byte-identical to the edited file minus
  the four inserted lines.

### Non-ASCII fingerprints

Non-ASCII character count, before -> after. The three code files that carry
Chinese comments are unchanged; the docs grew because they gained Chinese prose.

```
shared/search/native_offtarget.py              0 ->    0
shared/search/offtarget_backend.py            15 ->   15   (same non-ASCII hash d30e897a8c5639f4ba7e34784eda9052)
shared/design/pattern_runner.py                8 ->    8
designer_workbench.py                          0 ->    0
basic/blast.py                               395 ->  395
tools/search_indexed.py                        0 ->    0
Target_xbp_Y_zbp_Target/blast_combined.py    295 ->  295
docs/OFFTARGET_ENGINES.md                   1430 -> 1594
docs/OFFTARGET_HARDENING_TASKS.md             16 ->   16
README.md                                  (new) -> 2701
tests/test_offtarget_hardening.py          (new) ->    0
shared/utils/child_process.py              (new) ->    0
```

Every touched file is LF-only (no `\r\n`), has no BOM, and every touched `.py`
file passes `compile(text, path, "exec")`.

### Test runs

Server (Linux, Python 3.12.3, `/home/apool/songji/programfile/.venv/bin/python`):

```
cd /home/apool/songji/programfile
PYTHONPATH=shared .venv/bin/python run_tests.py
Ran 339 tests in 67.045s
FAILED (errors=1, skipped=29)
```

The one error is `test_genome_index.GenomeIndexTests.test_build_memory_limit_success_and_clean_failure`
(`RSS 1240.75 MiB exceeds --max-memory-mb=1024 MiB`). It reproduces on an idle
host and is a pre-existing test-design interaction, not a regression:

* the check is `resource.getrusage(RUSAGE_SELF).ru_maxrss`, i.e. the peak RSS of
  the *whole process*, not of the index builder;
* `unittest` discovery imports TensorFlow, numpy and tkinter (the TIGER and GUI
  test modules) before any test runs, and that alone takes the process from
  13.9 MiB to 868.0 MiB;
* the test then builds an in-process index on top of that baseline and crosses
  the 1 GiB budget.

Run on its own the same test passes twice in a row (`ok`, `ok`), which is why it
only shows up in a full-suite run; on Windows it passes because TensorFlow is not
installed there (hence the five `TIGER model or TensorFlow runtime not available`
skips). No file changed by this work is involved. A version that asserted on the
delta rather than the absolute peak would not have this problem, but that is
outside this task. The 29 skips are all `no display available` (headless host).

Windows (Python 3.14.7):

```
cd R:\songji\programfile
python run_tests.py
Ran 339 tests in 1297.947s
FAILED (errors=1, skipped=6)
```

The one error is the local-environment artefact already recorded in section 1:
this box has no `blastn`, so `test_auto_and_large_indexed_apply_mismatch_only_defaults`
cannot resolve the `auto` engine (`auto could not find an engine compatible with
max_bulge=0; choose exact or indexed explicitly`). The 6 skips are five
`TIGER model or TensorFlow runtime not available` plus the Linux-only
`test_parent_death_kills_the_engine`. Everything else is green, including the 28
`test_designer_workbench.py` tests and the 28 `test_pattern_runner.py` tests
whose mocked-child failures were fixed on the way through.

### Task 1 - progress is live, not buffered

Each output line is prefixed with its wall-clock time and the number of live
`offtarget-engine` processes, so a buffered implementation would show every line
at the same second.

```
cd /home/apool/songji/programfile
D=/tmp/oft_check_demo
PYTHONPATH=shared .venv/bin/python tools/search_indexed.py \
  example/engine_benchmark_small/guides.tsv $D/genome.fa $D/stream2 \
  --max-mismatch 4 --max-bulge 0 2>&1 \
  | while IFS= read -r line; do
      printf '%s|engines=%s|%s\n' "$(date +%H:%M:%S)" \
        "$(pgrep -c -f offtarget-engine || true)" "$line"
    done > $D/stream2.log
```

```
23:35:52|engines=1|indexed engine: holding the index lock for .../genome.k12
23:35:53|engines=1|indexed engine: building native index k=12 at .../genome.k12
23:36:10|engines=0|PROGRESS: guide g01 8
23:36:11|engines=0|PROGRESS_TARGET: 1/12
23:36:12|engines=0|PROGRESS: guide g02 16
...
23:36:31|engines=0|PROGRESS: guide g12 100
23:36:32|engines=0|PROGRESS_TARGET: 12/12
23:36:33|engines=0|Wrote 494 hits to .../top_offtargets.tsv
```

The `PROGRESS` lines arrive one per second for 22 seconds instead of all at the
end, which is the whole point of Task 1.

### Task 2 - killing the parent leaves no engine

```
D=/tmp/oft_check_demo
setsid .venv/bin/python tools/search_indexed.py example/engine_benchmark_small/guides.tsv \
  $D/genome.fa $D/orphan --max-mismatch 4 --max-bulge 0 > $D/orphan2.log 2>&1 &
PID=$!
sleep 6
pgrep -c -f offtarget-engine          # 1
kill -9 $PID
for i in 1 2 3 4 5 6; do sleep 1; echo "t+${i}s engines=$(pgrep -c -f offtarget-engine || true)"; done
pgrep -af offtarget-engine || echo NONE
```

```
engines while building: 1
3201353 .../native/bin/offtarget-engine build-index --genome .../genome.fa --prefix .../genome.k12 --k 12 --force
--- SIGKILL parent ---
parent alive=no
t+1s engines=0
t+2s engines=0
t+3s engines=0
t+4s engines=0
t+5s engines=0
t+6s engines=0
final pgrep:
NONE
```

Before this change the same experiment left an engine that ran for 8 days 22
hours at ~245 GB RSS. The only residue now is the partial
`genome.k12.positions.tmp` that the killed `build-index` was writing, which the
next run overwrites.

### Task 3 - two concurrent runs, one index

```
D=/tmp/oft_check_demo
rm -rf $D/shared
PYTHONPATH=shared .venv/bin/python tools/search_indexed.py example/engine_benchmark_small/guides.tsv \
  $D/genome.fa $D/shared --max-mismatch 4 --max-bulge 0 > $D/conc2_a.log 2>&1 &
sleep 3
PYTHONPATH=shared .venv/bin/python tools/search_indexed.py example/engine_benchmark_small/guides.tsv \
  $D/genome.fa $D/shared --max-mismatch 4 --max-bulge 0 > $D/conc2_b.log 2>&1 &
wait
```

```
$D/conc2_a.log  building=1 waiting=0 holding=1
$D/conc2_b.log  building=0 waiting=1 holding=1

conc2_a.log:
  indexed engine: holding the index lock for .../genome.k12
  indexed engine: building native index k=12 at .../genome.k12
conc2_b.log:
  indexed engine: another run holds the index lock; waiting for .../genome.k12.lock
  indexed engine: holding the index lock for .../genome.k12

$D/shared/genome_index:
  genome.k12.ggi      451207061
  genome.k12.json         753
  genome.k12.lock           1
```

A_EXIT=0, B_EXIT=0, 494 hits each, exactly one `.ggi`. The run that lost the race
waited, re-validated and reused the file the winner had just built, instead of
rebuilding over a file the other process had open.

### Task 4 - the gggenome budget is a URL path segment

Same guide (`GTAGGCCTTCCGTTACCCAT`), same database, budget varied two ways:

```
budget=0 path-form  /hg38/0/<q>.txt          ->   0 data lines   (# count: 0)
budget=1 path-form  /hg38/1/<q>.txt          ->   0 data lines
budget=2 path-form  /hg38/2/<q>.txt          ->   9 data lines
budget=3 path-form  /hg38/3/<q>.txt          -> 308 data lines
budget=1 query-param /hg38/<q>.txt?mismatch=1 ->   0 data lines
budget=3 query-param /hg38/<q>.txt?mismatch=3 ->   0 data lines

tool max_mismatch=1 -> hits=0 exact_only=False
tool max_mismatch=0 -> hits=0 exact_only=True
tool budget 8 -> RuntimeError: GGGenome rejected query g01 (mismatch budget 8):
                 ERROR : number of mismatches/gaps should be 25% or less ###
```

The path form returns more hits as the budget grows; the `?mismatch=` form stays
at zero for every budget, which is exactly the silent wrong answer section 6
described. The `### ... ERROR` body is now a `RuntimeError` instead of "no
off-targets".

### Task 5 - the fallback has to say so

* `tests/test_offtarget_hardening.py::FallbackReportingTests` parses every caller
  of the off-target backends and fails if a call site omits `log=` (or does not
  forward `**kwargs`), so a new silent entry point cannot be added silently.
* The same module runs `tools/search_indexed.py` with a forced fallback and
  asserts that the reason is printed and the process exits 3.
* `tests/test_offtarget_hardening.py::ConfirmHandshakeEndToEndTests` runs a real
  child that prints `CONFIRM_REQUIRED:` and answers it both ways (`ANSWER:yes`
  completes, `ANSWER:no` exits 4), closing the gap section 2 listed as the only
  unproven part of the handshake.

### What the new test module covers

`tests/test_offtarget_hardening.py`, 17 tests in six classes:

* `NativeStreamingTests` - a callback fires while a gated child is still alive
  (`active_children()` is non-empty), plus the build heartbeat.
* `ProcessLifetimeTests` - a timeout raises `NativeEngineTimeout` and explicitly
  is *not* a `NativeEngineError`; `IndexedBackend` propagates it without falling
  back to Python; a failing consumer still reaps the child;
  `test_parent_death_kills_the_engine` (Linux-only, uses `/proc/<pid>/stat`).
* `IndexNamespaceTests` - `.k<k>` naming, explicit `--index-path` override, lock
  contention raises within the timeout, and a valid index is reused, not rebuilt.
* `GGGenomeBudgetTests` - the URL carries the budget as a path segment, never as
  `?mismatch=`, `exact_only` is reported, and a `### ERROR` body raises.
* `FallbackReportingTests` and `ConfirmHandshakeEndToEndTests` as above.