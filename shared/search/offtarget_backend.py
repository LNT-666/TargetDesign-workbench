#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unified off-target search backend abstraction.

Every backend accepts the same input (guide dicts + genome FASTA + params)
and returns the same normalized hit records:

    {
        "qid", "guide", "target", "start", "strand",
        "mismatch", "indel", "pam", "bitscore", "engine",
    }

The scoring and GUI code only reads the normalized records, so switching
engines does not require changes outside this module and the pipeline entry.
"""

import contextlib
import json
import os
import re
import shutil
import struct
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field, replace
from typing import Dict, List, Optional


HIT_FIELDS = [
    "qid", "guide", "target", "start", "strand",
    "mismatch", "indel", "rna_bulges", "dna_bulges", "pam",
    "target_start", "target_end", "query_start", "query_end", "cigar",
    "aligned_guide", "aligned_target", "bitscore", "engine",
]

SEARCH_CHUNK_SIZE = 10
INDEXED_BULGE_DEFAULT_MAX_BASES = 50000000
MAX_EXACT_GENOME_BYTES = 200 * 1024 * 1024


# Policy for degrading the indexed engine to its pure-Python implementation.
# ``allow`` keeps the historical behaviour, ``deny`` refuses the fallback and
# ``ask`` requires an explicit confirmation: a front-end callback when one is
# registered, otherwise the CONFIRM_REQUIRED protocol on stdout/stdin.
PYTHON_FALLBACK_ENV = "CRISPR_OFFTARGET_PYTHON_FALLBACK"
PYTHON_FALLBACK_POLICIES = ("allow", "ask", "deny")
PYTHON_FALLBACK_PROMPT = "CONFIRM_REQUIRED:"


class PythonFallbackDeclined(RuntimeError):
    """Raised when the pure-Python index fallback is refused."""


def resolve_python_fallback_policy(params=None):
    """Return the fallback policy: explicit param, env var, then ``allow``."""
    policy = getattr(params, "extra", {}).get("python_fallback")
    if policy is None:
        policy = os.environ.get(PYTHON_FALLBACK_ENV)
    if policy is None:
        return "allow"
    policy = str(policy).strip().lower()
    if policy not in PYTHON_FALLBACK_POLICIES:
        return "allow"
    return policy


def ask_python_fallback_on_stdin(reason, prompt=""):
    """Emit the confirmation protocol line and read the answer from stdin.

    The parent process (see ``design.pattern_runner``) answers with
    ``yes``/``no``; a closed or unreadable stdin counts as a refusal.
    """
    detail = " ".join(str(reason or "unknown").splitlines()).strip()
    print("%s python_fallback|%s" % (PYTHON_FALLBACK_PROMPT, detail), flush=True)
    if prompt:
        print(prompt, end="", flush=True)
    try:
        answer = input()
    except (EOFError, KeyboardInterrupt):
        return False
    return answer.strip().lower() in ("y", "yes", "1", "true")


def approve_python_fallback(params=None, reason="", log=None):
    """Return True when the pure-Python index search may be used.

    The fallback reason is always reported through ``log`` so that a slow
    degrade is never silent, whatever the policy decides.
    """
    policy = resolve_python_fallback_policy(params)
    if log:
        log("indexed engine: native search unavailable, considering the "
            "pure-Python implementation")
        log("indexed engine: python fallback reason: %s" % reason)
        log("indexed engine: python fallback policy: %s" % policy)
    if policy == "allow":
        return True
    if policy == "deny":
        if log:
            log("indexed engine: python fallback refused by policy")
        return False
    confirm = getattr(params, "extra", {}).get("python_fallback_confirm")
    if callable(confirm):
        approved = bool(confirm(reason))
    else:
        approved = ask_python_fallback_on_stdin(reason)
    if log:
        log("indexed engine: python fallback %s"
            % ("approved" if approved else "refused"))
    return approved


# Cross-engine degradation (the ``auto`` chain) uses the same confirm protocol
# as the pure-Python fallback, with its own policy and its own prompt kind: a
# switch to another engine changes the search semantics, so it is never silent.
ENGINE_FALLBACK_ENV = "CRISPR_OFFTARGET_ENGINE_FALLBACK"
ENGINE_FALLBACK_POLICIES = ("allow", "ask", "deny")


def resolve_engine_fallback_policy(params=None):
    """Return the cross-engine policy: explicit param, env var, then ``ask``."""
    policy = getattr(params, "extra", {}).get("engine_fallback")
    if policy is None:
        policy = os.environ.get(ENGINE_FALLBACK_ENV)
    if policy is None:
        return "ask"
    policy = str(policy).strip().lower()
    if policy not in ENGINE_FALLBACK_POLICIES:
        return "ask"
    return policy


def ask_engine_fallback_on_stdin(target, reason):
    """Emit ``CONFIRM_REQUIRED: engine_fallback|<target>|<reason>`` for a parent.

    The parent process (see ``design.pattern_runner``) answers with
    ``yes``/``no``; a closed or unreadable stdin counts as a refusal.
    """
    detail = " ".join(str(reason or "unknown").splitlines()).strip()
    print("%s engine_fallback|%s|%s"
          % (PYTHON_FALLBACK_PROMPT, target, detail), flush=True)
    try:
        answer = input()
    except (EOFError, KeyboardInterrupt):
        return False
    return answer.strip().lower() in ("y", "yes", "1", "true")


def approve_engine_fallback(params=None, target="", reason="", log=None):
    """Return True when ``auto`` may continue the search with ``target``.

    The reason is always reported through ``log`` so that an engine switch is
    never silent, whatever the policy decides.
    """
    policy = resolve_engine_fallback_policy(params)
    if log:
        log("auto engine: considering the %s engine instead" % target)
        log("auto engine: engine fallback reason: %s" % reason)
        log("auto engine: engine fallback policy: %s" % policy)
    if policy == "allow":
        return True
    if policy == "deny":
        if log:
            log("auto engine: engine fallback refused by policy")
        return False
    confirm = getattr(params, "extra", {}).get("engine_fallback_confirm")
    if callable(confirm):
        approved = bool(confirm(target, reason))
    else:
        approved = ask_engine_fallback_on_stdin(target, reason)
    if log:
        log("auto engine: engine fallback %s"
            % ("approved" if approved else "refused"))
    return approved


def default_engine_threads():
    """Pick a shared thread count for engines that accept -p/--threads."""
    try:
        value = int(os.environ.get("SEARCH_NUM_THREADS") or 0)
    except (TypeError, ValueError):
        value = 0
    if value > 0:
        return value
    return max(1, min(os.cpu_count() or 2, 32))


def _progress_chunk_size(total):
    """Keep external-tool overhead bounded to about 20 progress updates."""
    return max(SEARCH_CHUNK_SIZE, -(-total // 20))


def print_search_progress(done, total):
    """Emit count-only target progress understood by the Pattern Designer UI."""
    print("PROGRESS_TARGET: %d/%d" % (done, total), flush=True)


@dataclass
class SearchParams:
    """Normalized search parameters shared by all backends."""

    max_mismatch: int = 4
    max_bulge: int = 1
    max_bulge_explicit: bool = False
    seed_len: int = 10
    seed_mismatch: Optional[int] = None
    seed_mismatch_max: Optional[int] = None
    pam: Optional[str] = None
    pam_side: str = "3prime"
    require_pam: bool = False
    window_motif: Optional[str] = None
    window_side: str = "downstream"
    blastdb: Optional[str] = None
    index_path: Optional[str] = None
    output_dir: Optional[str] = None
    genome_build: Optional[str] = None
    extra: Dict = field(default_factory=dict)

    @classmethod
    def from_args(cls, args):
        extra = {}
        max_mismatch = getattr(args, "max_mismatch", None)
        max_bulge = getattr(args, "max_bulge", None)
        cache_genome = getattr(args, "cache_genome", None)
        if cache_genome is not None:
            extra["cache_genome"] = cache_genome
        threads = getattr(args, "threads", None)
        if threads:
            extra["threads"] = int(threads)
        max_memory_mb = getattr(args, "max_memory_mb", None)
        if max_memory_mb is not None:
            extra["max_memory_mb"] = int(max_memory_mb)
        timeout_s = getattr(args, "timeout_s", None)
        if timeout_s:
            extra["timeout_s"] = float(timeout_s)
        return cls(
            max_mismatch=int(4 if max_mismatch is None else max_mismatch),
            max_bulge=int(1 if max_bulge is None else max_bulge),
            max_bulge_explicit=max_bulge is not None,
            seed_len=int(getattr(args, "seed_len", 10) or 10),
            seed_mismatch=getattr(args, "seed_mismatch", None),
            seed_mismatch_max=getattr(args, "seed_mismatch_max", None),
            pam=getattr(args, "pam", None),
            pam_side=getattr(args, "pam_side", "3prime") or "3prime",
            require_pam=bool(getattr(args, "require_pam", False)),
            window_motif=getattr(args, "window_motif", None) or None,
            window_side=getattr(args, "window_side", None) or "downstream",
            blastdb=getattr(args, "blastdb", None) or None,
            index_path=getattr(args, "index_path", None) or None,
            output_dir=getattr(args, "output_dir", None),
            genome_build=getattr(args, "genome_build", None) or None,
            extra=extra,
        )


class SearchParameterError(ValueError):
    """Raised before a backend runs when its contract cannot be honored."""


@dataclass(frozen=True)
class EngineCapabilities:
    substitutions: bool
    indels: str
    unknown_gap_type: bool
    pam_sides: tuple
    exhaustive_small_genome: bool = False

    def supports_bulges(self):
        return self.indels != "none"


def normalize_hit(hit, engine, qid=None, guide=None):
    """Return a hit dict with every unified field populated."""
    out = dict(hit or {})
    out.setdefault("qid", qid)
    out.setdefault("guide", guide)
    out.setdefault("target", out.get("seq_id") or out.get("chrom") or "")
    out.setdefault("start", 0)
    out.setdefault("strand", "+")
    out.setdefault("mismatch", 0)
    out.setdefault("indel", 0)
    out.setdefault("rna_bulges", 0)
    out.setdefault("dna_bulges", 0)
    out.setdefault("pam", "")
    out.setdefault("bitscore", 0.0)
    out["engine"] = engine
    out["start"] = int(out["start"])
    out["mismatch"] = int(out["mismatch"])
    out["indel"] = int(out["indel"])
    out["rna_bulges"] = int(out.get("rna_bulges") or 0)
    out["dna_bulges"] = int(out.get("dna_bulges") or 0)
    out["target_start"] = int(out.get("target_start") or out["start"])
    target_end = out.get("target_end")
    if target_end is None:
        target_end = (
            out["target_start"] + len(str(out.get("guide") or ""))
            - out["indel"]
        )
    out["target_end"] = int(target_end)
    out.setdefault("query_start", 0)
    out.setdefault("query_end", len(str(out.get("guide") or "")))
    out["query_start"] = int(out["query_start"])
    out["query_end"] = int(out["query_end"])
    out.setdefault("cigar", "")
    out.setdefault("aligned_guide", out.get("guide") or "")
    out.setdefault("aligned_target", "")
    try:
        out["bitscore"] = float(out["bitscore"])
    except (TypeError, ValueError):
        out["bitscore"] = 0.0
    return out


class OffTargetBackend:
    """Base class for off-target search engines."""

    name = "base"
    display_name = "Base"
    capabilities = EngineCapabilities(
        substitutions=True,
        indels="none",
        unknown_gap_type=False,
        pam_sides=("3prime", "5prime"),
    )

    def available(self):
        """Return (ok, reason)."""
        return True, ""

    def search(self, guides, genome_fasta, params, genome=None, **kwargs):
        raise NotImplementedError


class ExactBackend(OffTargetBackend):
    name = "exact"
    display_name = "Local exact"
    capabilities = EngineCapabilities(
        substitutions=True,
        indels="dna_rna",
        unknown_gap_type=False,
        pam_sides=("3prime", "5prime"),
        exhaustive_small_genome=True,
    )

    def search(self, guides, genome_fasta, params, genome=None, **kwargs):
        from search.exact_offtarget import search_guides

        validate_search_params(self.name, params)
        seed_mm = params.seed_mismatch
        if seed_mm is None:
            seed_mm = 0 if params.seed_mismatch_max is not None else 1
        results = search_guides(
            guides, genome_fasta,
            max_mismatch=params.max_mismatch,
            max_bulge=params.max_bulge,
            seed_len=params.seed_len,
            seed_mm=seed_mm,
            pam=params.pam if params.require_pam else None,
            pam_side=params.pam_side,
            progress_callback=kwargs.get("progress_callback"),
        )
        return {
            qid: [normalize_hit(hit, self.name) for hit in hits]
            for qid, hits in results.items()
        }


class BlastBackend(OffTargetBackend):
    name = "blast"
    display_name = "NCBI BLAST"
    capabilities = EngineCapabilities(
        substitutions=True,
        indels="basic",
        unknown_gap_type=False,
        pam_sides=("3prime", "5prime"),
    )

    def available(self):
        missing = [cmd for cmd in ("blastn", "makeblastdb")
                   if shutil.which(cmd) is None]
        if missing:
            return False, "Missing NCBI BLAST+: %s" % ", ".join(missing)
        return True, ""

    def search(self, guides, genome_fasta, params, genome=None, **kwargs):
        from search.blast_utils import (
            _blastdb_files_exist, blastdb_is_current, build_blastdb,
            ensure_blastdb, find_existing_blastdb, run_blastn)

        ok, reason = self.available()
        if not ok:
            raise RuntimeError(reason)
        validate_search_params(self.name, params)
        trust_existing = bool(
            params.extra.get("trust_existing_blastdb", False))
        if params.blastdb:
            db_name = params.blastdb
            for extension in (".nin", ".nsq", ".nhr", ".nal", ".nog"):
                if db_name.endswith(extension):
                    db_name = db_name[:-len(extension)]
                    break
            if not _blastdb_files_exist(db_name):
                raise RuntimeError(
                    "BLAST database is incomplete: %s" % db_name)
            if trust_existing:
                print(
                    "WARNING: trusting existing BLAST database without "
                    "validating its source manifest: %s" % db_name,
                    flush=True,
                )
            if not trust_existing and not blastdb_is_current(
                    genome_fasta, db_name):
                print(
                    "WARNING: BLAST database source manifest is missing or "
                    "stale; rebuilding %s." % db_name,
                    flush=True,
                )
                build_blastdb(genome_fasta, db_name)
        else:
            db_name = find_existing_blastdb(
                genome_fasta, output_dir=params.output_dir,
                trust_existing=trust_existing, log=print)
            if not db_name:
                db_name = ensure_blastdb(
                    genome_fasta, output_dir=params.output_dir)
        progress_callback = kwargs.get("progress_callback")
        chunk_size = (
            _progress_chunk_size(len(guides))
            if progress_callback else len(guides) or 1
        )
        min_guide_len = min(
            (len(g.get("guide_seq") or "") for g in guides), default=0)
        perc_identity = None
        if params.max_mismatch is not None and min_guide_len > 0:
            permitted_span = min_guide_len + max(0, int(params.max_bulge))
            threshold = 100.0 * (
                min_guide_len - params.max_mismatch) / permitted_span
            if threshold > 0:
                perc_identity = threshold
        raw_results = {}
        for start in range(0, len(guides), chunk_size):
            chunk = guides[start:start + chunk_size]
            query_fasta = tempfile.NamedTemporaryFile(
                mode="w", suffix=".fa", delete=False, encoding="utf-8")
            for guide in chunk:
                query_fasta.write(
                    ">%s\n%s\n" % (guide["qid"], guide["guide_seq"])
                )
            query_fasta.close()
            try:
                raw_results.update(run_blastn(
                    query_fasta.name, db_name,
                    task=("blastn-short"
                          if max(len(g["guide_seq"]) for g in chunk) <= 30
                          else "blastn"),
                    word_size=4,
                    evalue=1000,
                    max_mismatch=params.max_mismatch,
                    max_bulge=params.max_bulge,
                    require_pam=params.require_pam,
                    pam_motif=params.pam or "GG",
                    pam_side=params.pam_side,
                    window_motif=params.window_motif,
                    window_side=params.window_side,
                    seed_mismatch_max=params.seed_mismatch_max,
                    seed_len=params.seed_len,
                    genome=genome,
                    num_threads=params.extra.get("threads"),
                    perc_identity=perc_identity,
                ))
            finally:
                try:
                    os.unlink(query_fasta.name)
                except OSError:
                    pass
            if progress_callback:
                progress_callback(start + len(chunk), len(guides))
        out = {}
        guide_by_qid = {
            guide.get("qid"): guide.get("guide_seq")
            for guide in guides
        }
        for qid, hits in raw_results.items():
            out[qid] = [normalize_hit(
                hit, self.name, qid=qid, guide=guide_by_qid.get(qid))
                        for hit in hits]
        return out


class GGGenomeBackend(OffTargetBackend):
    name = "gggenome"
    display_name = "GGGenome"
    capabilities = EngineCapabilities(
        substitutions=True,
        indels="basic",
        unknown_gap_type=True,
        pam_sides=("3prime", "5prime"),
    )

    BASE_URL = "https://gggenome.dbcls.jp"

    # The online API rejects a budget above 25% of the query length.
    MAX_MISMATCH_FRACTION = 0.25

    def __init__(self):
        self.last_report = {}

    def available(self):
        return True, ""

    def search(self, guides, genome_fasta, params, genome=None, **kwargs):
        """Search GGGenome, honouring the mismatch budget for real.

        The mismatch/gap budget belongs in the URL *path*
        (``/<build>/<mismatch>/<query>.txt``); passing it as a ``?mismatch=``
        query parameter is silently ignored by the service, which returns
        exact matches only and makes a substitution search look like "no
        off-targets found".
        """
        validate_search_params(self.name, params)
        build = params.genome_build or "hg38"
        out = {}
        progress_callback = kwargs.get("progress_callback")
        log = kwargs.get("log")
        mismatch_budget = int(params.max_mismatch) + int(params.max_bulge)
        if log:
            if mismatch_budget:
                log("gggenome: searching %s with up to %d mismatches/gaps"
                    % (build, mismatch_budget))
            else:
                log("gggenome: exact-match-only search on %s" % build)
        hits_total = 0
        for index, guide in enumerate(guides, start=1):
            if progress_callback:
                progress_callback(index, len(guides))
            query = guide["guide_seq"].upper().replace("U", "T")
            pam_seq = ""
            if params.require_pam and params.pam:
                pam_seq = params.pam.upper().replace("U", "T")
                if params.pam_side == "5prime":
                    query = pam_seq + query
                else:
                    query += pam_seq
            url = "%s/%s/%d/%s.txt" % (
                self.BASE_URL, urllib.parse.quote(build), mismatch_budget,
                urllib.parse.quote(query, safe="ACGTN"))
            text = self._request(url, guide)
            hits = self._parse_tsv(text, params)
            for hit in hits:
                hit["qid"] = guide["qid"]
                hit["guide"] = guide["guide_seq"]
                hit["pam"] = pam_seq
                out.setdefault(guide["qid"], []).append(hit)
            hits_total += len(hits)
        self.last_report = {
            "engine": self.name,
            "implementation": "online-api",
            "genome_build": build,
            "mismatch_budget": mismatch_budget,
            "exact_only": mismatch_budget == 0,
            "guides": len(guides),
            "hits": hits_total,
            "hits_by_qid": {qid: len(items) for qid, items in out.items()},
        }
        return out

    def _request(self, url, guide):
        request = urllib.request.Request(
            url, headers={"User-Agent": "TargetDesign-workbench/0.1 (+https://github.com/LNT-666/TargetDesign-workbench)"})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                text = response.read().decode("utf-8", "replace")
        except Exception as exc:
            raise RuntimeError("GGGenome API request failed: %s" % exc)
        error = self._api_error(text)
        if error:
            raise RuntimeError(
                "GGGenome rejected query %s (mismatch budget %d): %s; "
                "lower --max-mismatch/--max-bulge for this engine"
                % (guide.get("qid"), self._budget_from_url(url), error))
        return text

    @staticmethod
    def _budget_from_url(url):
        parts = urllib.parse.urlparse(url).path.split("/")
        for part in reversed(parts):
            if part.isdigit():
                return int(part)
        return -1

    @staticmethod
    def _api_error(text):
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("###") and "ERROR" in stripped.upper():
                return stripped.lstrip("#").strip()
        return ""

    def _parse_tsv(self, text, params):
        header = None
        hits = []
        for line in text.splitlines():
            line = line.rstrip("\n")
            if not line.strip():
                continue
            if line.startswith("###"):
                continue
            if line.startswith("#"):
                if line.startswith("# name") or "name\tstrand\tstart" in line:
                    header = [part.strip() for part in
                              line.lstrip("#").split("\t")]
                continue
            parts = line.split("\t")
            if len(parts) < 6:
                continue
            if header:
                row = dict(zip(header, parts))
                target = row.get("name") or parts[0]
                start = _int_or(row.get("start"), parts[2]) - 1
                strand = row.get("strand", "+")
                mismatch = _int_or(row.get("mis"), 0)
                indel = (_int_or(row.get("del"), 0) +
                         _int_or(row.get("ins"), 0))
            else:
                target, strand, start = parts[0], parts[1], parts[2]
                start = _int_or(start, 0) - 1
                mismatch = _int_or(parts[12], 0) if len(parts) > 12 else 0
                indel = 0
            if mismatch > params.max_mismatch or indel > params.max_bulge:
                continue
            hits.append(normalize_hit({
                "target": target,
                "start": max(0, start),
                "strand": strand if strand in ("+", "-") else "+",
                "mismatch": mismatch,
                "indel": indel,
                "rna_bulges": 0,
                "dna_bulges": 0,
                "gap_type": "unknown" if indel else "none",
                "bitscore": max(0.0, 100.0 - mismatch * 12.0 - indel * 18.0),
                "pam": "",
            }, self.name))
        return hits


# How long a run waits for another run's index build before giving up.
INDEX_LOCK_TIMEOUT_S = 600.0
INDEX_LOCK_POLL_S = 0.5


def _lock_file(handle):
    """Take a non-blocking exclusive lock; raise OSError when it is busy."""
    if os.name == "nt":
        import msvcrt

        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock_file(handle):
    try:
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except OSError:
        pass


@contextlib.contextmanager
def index_build_lock(prefix, timeout_s=INDEX_LOCK_TIMEOUT_S, log=None):
    """Serialize index builds that share ``prefix``.

    Two concurrent runs with the same output directory and the same k would
    otherwise rebuild one ``.ggi`` while the other is still reading it. The
    lock makes the second run wait, re-validate, and reuse the fresh index
    instead of overwriting a file that another process has open.
    """
    path = prefix + ".lock"
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    handle = open(path, "a+b")
    if handle.seek(0, os.SEEK_END) == 0:
        handle.write(b"\0")
        handle.flush()
    locked = False
    waited = False
    try:
        deadline = time.monotonic() + float(timeout_s)
        while True:
            try:
                _lock_file(handle)
                locked = True
                break
            except OSError:
                if not waited:
                    waited = True
                    if log:
                        log("indexed engine: another run holds the index "
                            "lock; waiting for %s" % path)
                if time.monotonic() >= deadline:
                    raise RuntimeError(
                        "index %s is being built by another run (lock %s); "
                        "wait for it to finish, or use a different "
                        "--output-dir/--index-path" % (prefix, path))
                time.sleep(INDEX_LOCK_POLL_S)
        if log:
            log("indexed engine: holding the index lock for %s" % prefix)
        yield
    finally:
        try:
            if locked:
                _unlock_file(handle)
        finally:
            handle.close()


class IndexedBackend(OffTargetBackend):
    name = "indexed"
    display_name = "Local indexed genome"
    capabilities = EngineCapabilities(
        substitutions=True,
        indels="dna_rna",
        unknown_gap_type=False,
        pam_sides=("3prime", "5prime"),
        exhaustive_small_genome=True,
    )

    def __init__(self):
        self.last_report = {}

    def available(self):
        from search import native_offtarget

        if native_offtarget.native_enabled():
            native_ok, _native_reason = native_offtarget.probe_binary()
            if native_ok:
                return True, ""
        missing = []
        for module in ("numpy", "Bio", "pyfaidx"):
            try:
                __import__(module)
            except ImportError:
                missing.append(module)
        if missing:
            return False, "Missing Python packages for indexed search: %s" % (
                ", ".join(missing))
        return True, ""

    def _index_prefix(self, genome_fasta, params, k=None):
        """Return the index prefix for this run.

        ``params.index_path`` is an explicit override and is used verbatim.
        Otherwise the prefix carries ``k``: the index format is k-specific, so
        two runs that pick different k values must never share one file.
        """
        if params.index_path:
            base = params.index_path
            for ext in (".ggi", ".json"):
                if base.endswith(ext):
                    base = base[:-len(ext)]
            return base
        out_dir = params.output_dir or os.path.dirname(
            os.path.abspath(genome_fasta))
        index_dir = os.path.join(out_dir, "genome_index")
        os.makedirs(index_dir, exist_ok=True)
        base = os.path.splitext(os.path.basename(genome_fasta))[0]
        if k is not None:
            base = "%s.k%d" % (base, int(k))
        return os.path.join(index_dir, base)

    def _search_native(self, guides, genome_fasta, params, prefix, k,
                       log=None, progress_callback=None):
        from search import native_offtarget

        ok, binary_or_reason = native_offtarget.probe_binary()
        if not ok:
            raise native_offtarget.NativeEngineError(
                ["offtarget-engine", "probe"], 4, binary_or_reason)
        binary = binary_or_reason
        max_memory_mb = params.extra.get("max_memory_mb")
        report = {
            "engine": self.name,
            "index_path": prefix + ".ggi",
            "built": False,
            "reused": False,
            "native_binary": binary,
            "memory_limit_mb": int(max_memory_mb or 0),
        }
        if "k_auto_reduced_from" in params.extra:
            report["k_auto_reduced_from"] = params.extra["k_auto_reduced_from"]
        timeout_s = params.extra.get("timeout_s")
        with index_build_lock(prefix, log=log):
            inspection = None
            try:
                inspection = native_offtarget.inspect_index(
                    binary, genome_fasta, prefix, timeout_s=timeout_s)
            except native_offtarget.NativeEngineError:
                inspection = None
            index_valid = bool(
                inspection and inspection.get("valid") and
                int(inspection.get("k") or -1) == k)
            if index_valid:
                try:
                    with open(prefix + ".json", "r",
                              encoding="utf-8") as index_meta:
                        report.update(json.load(index_meta))
                except (OSError, json.JSONDecodeError):
                    pass
                report["reused"] = True
            else:
                if log:
                    log("indexed engine: building native index k=%d at %s"
                        % (k, prefix))
                build_report = native_offtarget.build_index(
                    binary, genome_fasta, prefix, k=k,
                    threads=params.extra.get("threads"), force=True,
                    max_memory_mb=max_memory_mb, log=log, timeout_s=timeout_s)
                report.update(build_report)
                report["built"] = True
                report["reused"] = False

        from search.genome_index import DEFAULT_K
        seed_len = max(params.seed_len or DEFAULT_K, k)
        seed_mm = params.seed_mismatch
        if seed_mm is None:
            seed_mm = 0 if params.seed_mismatch_max is not None else 1
        seed_mm = max(int(seed_mm), params.max_mismatch // 3)

        def on_progress(done, total, qid=""):
            # Forwarded live from the JSONL events: the search can run for
            # hours, so progress must not wait for the final report.
            if log:
                percent = int(100.0 * done / max(1, total))
                log("PROGRESS: guide %s %d" % (qid, percent))
                log("PROGRESS_TARGET: %d/%d" % (done, total))
            elif progress_callback:
                progress_callback(done, total)

        results, search_report = native_offtarget.search(
            binary,
            genome_fasta,
            prefix,
            guides,
            max_mismatch=params.max_mismatch,
            max_bulge=params.max_bulge,
            seed_len=seed_len,
            seed_mismatch=seed_mm,
            seed_mismatch_max=params.seed_mismatch_max,
            pam=params.pam if params.require_pam else None,
            pam_side=params.pam_side,
            threads=params.extra.get("threads"),
            cache_genome=params.extra.get("cache_genome"),
            progress=bool(log or progress_callback),
            max_memory_mb=max_memory_mb,
            progress_callback=(
                on_progress if (log or progress_callback) else None),
            timeout_s=timeout_s,
        )
        search_report.pop("progress_events", None)
        report.update(search_report)
        report["implementation"] = "native-cpp"
        self.last_report = report
        return {
            qid: [normalize_hit(hit, self.name) for hit in hits]
            for qid, hits in results.items()
        }

    def _search_python(self, guides, genome_fasta, params, prefix, k,
                       genome=None, log=None, **kwargs):
        from search.genome_index import (DEFAULT_K, build_index, load_index,
                                  search_indexed)

        report = {
            "engine": self.name,
            "index_path": prefix + ".ggi",
            "built": False,
            "reused": False,
            "memory_limit_mb": int(
                params.extra.get("max_memory_mb") or 0),
        }
        if "k_auto_reduced_from" in params.extra:
            report["k_auto_reduced_from"] = params.extra["k_auto_reduced_from"]
        try:
            index = load_index(prefix)
            if index.k != k:
                raise ValueError(
                    "index k=%d does not match requested k=%d"
                    % (index.k, k))
            if not index.is_valid_for(genome_fasta):
                raise FileNotFoundError("index is stale for this genome")
        except (FileNotFoundError, ValueError, KeyError, struct.error,
                json.JSONDecodeError):
            build = build_index(
                genome_fasta, prefix, k=k,
                max_memory_mb=params.extra.get("max_memory_mb"))
            report.update(build)
            report["built"] = True
            index = load_index(prefix)
        else:
            report.update(index.meta)
            report["reused"] = True

        seed_len = max(params.seed_len or DEFAULT_K, index.k)
        seed_mm = params.seed_mismatch
        if seed_mm is None:
            seed_mm = 0 if params.seed_mismatch_max is not None else 1
        seed_mm = max(int(seed_mm), params.max_mismatch // 3)
        results, search_report = search_indexed(
            index, guides, genome_fasta,
            max_mismatch=params.max_mismatch,
            max_bulge=params.max_bulge,
            seed_len=seed_len,
            seed_mm=seed_mm,
            pam=params.pam if params.require_pam else None,
            pam_side=params.pam_side,
            log=log,
            progress_callback=kwargs.get("progress_callback"),
            cache_genome=params.extra.get("cache_genome"),
            max_memory_mb=params.extra.get("max_memory_mb"),
        )
        report.update(search_report)
        report["implementation"] = "python"
        self.last_report = report
        return {
            qid: [normalize_hit(hit, self.name) for hit in hits]
            for qid, hits in results.items()
        }

    def search(self, guides, genome_fasta, params, genome=None, log=None,
               **kwargs):
        from search import native_offtarget
        from search.genome_index import select_index_k, suggest_k

        ok, reason = self.available()
        if not ok:
            raise RuntimeError(reason)
        apply_engine_defaults(
            self.name, params, os.path.getsize(genome_fasta))
        validate_search_params(self.name, params)
        k = params.extra.get("k")
        if not k:
            k = suggest_k(os.path.getsize(genome_fasta))
        k = int(k)
        if "k" not in params.extra:
            guide_lengths = [
                len(str(
                    guide.get("guide_seq") or guide.get("spacer_seq") or ""
                ))
                for guide in guides
                if isinstance(guide, dict)
            ]
            if not guide_lengths:
                guide_lengths = [
                    len(str(guide)) for guide in guides if str(guide)
                ]
            selected_k = select_index_k(
                os.path.getsize(genome_fasta),
                guide_lengths,
                params.max_mismatch,
                params.max_bulge,
            )
            if selected_k != k:
                params.extra["k_auto_reduced_from"] = k
                k = selected_k
                params.extra["k"] = k
        prefix = self._index_prefix(genome_fasta, params, k)

        fallback_reason = ""
        if native_offtarget.native_enabled():
            native_ready, _binary = native_offtarget.probe_binary()
            if native_ready:
                try:
                    return self._search_native(
                        guides, genome_fasta, params, prefix, k,
                        log=log,
                        progress_callback=kwargs.get("progress_callback"))
                except native_offtarget.NativeEngineError as exc:
                    if exc.is_memory_limit:
                        raise native_offtarget.MemoryLimitExceededError(
                            str(exc)) from exc
                    if exc.emitted_hits or \
                            not native_offtarget.native_fallback_enabled():
                        raise RuntimeError(str(exc)) from exc
                    fallback_reason = str(exc)
            else:
                fallback_reason = _binary
        if not fallback_reason:
            fallback_reason = "native off-target engine is unavailable"
        if not approve_python_fallback(params, fallback_reason, log=log):
            self.last_report = {
                "engine": self.name,
                "index_path": prefix + ".ggi",
                "implementation": "python",
                "native_fallback_reason": fallback_reason,
            }
            raise PythonFallbackDeclined(
                "pure-Python index fallback refused for the indexed engine "
                "(reason: %s); install the native off-target engine at "
                "native/bin/offtarget-engine or set the fallback policy to "
                "'allow'" % fallback_reason)
        result = self._search_python(
            guides, genome_fasta, params, prefix, k, genome=genome,
            log=log, **kwargs)
        self.last_report["native_fallback_reason"] = fallback_reason
        return result


def validate_search_params(engine, params, genome_size=None):
    """Reject unsupported parameter combinations before a backend starts."""
    key = (engine or "").lower()
    if key == "auto":
        resolve_engine(key, params, genome_size=genome_size)
        return True
    if key not in BACKENDS:
        raise ValueError(
            "Unknown off-target engine: %s (choose from %s)"
            % (engine, ", ".join(sorted(BACKENDS)))
        )
    params = params or SearchParams()
    if int(params.max_mismatch) < 0:
        raise SearchParameterError("max_mismatch must be >= 0")
    if int(params.max_bulge) < 0:
        raise SearchParameterError("max_bulge must be >= 0")
    capabilities = BACKENDS[key]().capabilities
    if int(params.max_bulge) > 0 and not capabilities.supports_bulges():
        raise SearchParameterError(
            "%s does not support max_bulge=%d; set max_bulge=0 or choose "
            "an engine with %s indel support"
            % (BACKENDS[key].display_name, int(params.max_bulge),
               "dna_rna" if key in ("exact", "indexed") else "basic")
        )
    if params.require_pam and not params.pam:
        raise SearchParameterError(
            "%s requires a PAM motif when require_pam=True"
            % BACKENDS[key].display_name
        )
    if params.pam_side not in capabilities.pam_sides:
        raise SearchParameterError(
            "%s does not support pam_side=%s (supported: %s)"
            % (BACKENDS[key].display_name, params.pam_side,
               ", ".join(capabilities.pam_sides))
        )
    return True


def apply_engine_defaults(name, params, genome_size=None):
    """Apply documented engine-specific defaults without overriding users.

    BLAST defaults to ``max_bulge=0`` unless the user explicitly requests
    gapped search. ``auto`` also uses the
    mismatch-only default when a BLAST database is available, so the presence
    of a db keeps its intended priority. Large indexed searches default to
    bulge-free mode; an explicit ``max_bulge`` is always preserved.
    """
    params = params or SearchParams()
    if getattr(params, "max_bulge_explicit", False):
        return params
    key = (name or "auto").lower()
    reason = ""
    if key == "blast":
        reason = "blast defaults to mismatch-only unless max_bulge is explicit"
    elif key == "auto":
        reason = "auto defaults to mismatch-only unless max_bulge is explicit"
    elif key == "indexed" and genome_size is not None and \
            int(genome_size) > INDEXED_BULGE_DEFAULT_MAX_BASES:
        reason = (
            "indexed searches above %.0f Mbp default to mismatch-only; "
            "explicit max_bulge=1 requires a seed plan that can be guaranteed"
            % (INDEXED_BULGE_DEFAULT_MAX_BASES / 1000000.0)
        )
    if reason:
        params.max_bulge = 0
        params.extra["max_bulge_default_reason"] = reason
    return params


def native_indexed_available():
    """Return whether the native indexed binary is usable."""
    try:
        from search import native_offtarget
    except ImportError:
        return False
    if not native_offtarget.native_enabled():
        return False
    ok, _reason = native_offtarget.probe_binary()
    return bool(ok)


def auto_engine_candidates(params, genome_size=None, native_available=None):
    """Return the benchmark-derived auto engine preference order."""
    params = params or SearchParams()
    if getattr(params, "blastdb", None):
        return ["blast"]
    if getattr(params, "index_path", None):
        return ["indexed"]
    if native_available is None:
        native_available = native_indexed_available()
    bulge_enabled = int(params.max_bulge) > 0
    if genome_size is not None and \
            int(genome_size) > MAX_EXACT_GENOME_BYTES:
        return ["blast", "indexed"]
    if native_available:
        return ["indexed", "blast", "exact"]
    if bulge_enabled:
        return ["blast", "exact", "indexed"]
    return ["blast", "indexed", "exact"]


def resolve_engine(name, params, genome_size=None):
    """Resolve ``auto`` to an engine that can honor the requested contract.

    Explicit engines are preserved. For ``auto``, existing BLAST databases
    and local indexes keep their priority. Without either resource, large
    genomes avoid the memory-heavy exact backend and prefer BLAST.
    """
    requested = (name or "auto").lower()
    apply_engine_defaults(requested, params, genome_size=genome_size)
    if requested != "auto":
        validate_search_params(requested, params)
        return requested
    params = params or SearchParams()
    for candidate in auto_engine_candidates(params, genome_size):
        try:
            validate_search_params(candidate, params)
        except SearchParameterError:
            continue
        ok, _reason = get_backend(candidate).available()
        if not ok:
            continue
        return candidate
    raise SearchParameterError(
        "auto could not find an engine compatible with max_bulge=%d; "
        "choose exact or indexed explicitly" % int(params.max_bulge)
    )


def _int_or(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


BACKENDS = {
    "exact": ExactBackend,
    "blast": BlastBackend,
    "gggenome": GGGenomeBackend,
    "indexed": IndexedBackend,
}

# Engines retired from the off-target search stack. Kept here only so a stale
# UI or saved session gets an explicit error instead of a silent engine swap.
REMOVED_ENGINES = ("bowtie2", "casoffinder")


def get_backend(name):
    key = (name or "exact").lower()
    if key in REMOVED_ENGINES:
        raise ValueError(
            "Off-target engine %s was removed; choose from %s"
            % (key, ", ".join(sorted(BACKENDS))))
    if key not in BACKENDS:
        raise ValueError("Unknown off-target engine: %s (choose from %s)"
                         % (name, ", ".join(sorted(BACKENDS))))
    return BACKENDS[key]()


def engine_available(name):
    if (name or "").lower() == "auto":
        return True, ""
    return get_backend(name).available()


def engine_capability_matrix():
    """Return the public parameter-support matrix for every backend."""
    return {
        name: {
            "substitutions": backend.capabilities.substitutions,
            "indels": backend.capabilities.indels,
            "unknown_gap_type": backend.capabilities.unknown_gap_type,
            "pam_sides": list(backend.capabilities.pam_sides),
            "exhaustive_small_genome":
                backend.capabilities.exhaustive_small_genome,
        }
        for name, backend in BACKENDS.items()
    }


def _genome_size_or_none(genome_fasta):
    try:
        return os.path.getsize(genome_fasta)
    except OSError:
        return None


def _attempt_params(params, engine, genome_size):
    """Copy ``params`` and apply the candidate engine's own defaults."""
    candidate = replace(params, extra=dict(getattr(params, "extra", {}) or {}))
    apply_engine_defaults(engine, candidate, genome_size)
    if engine == "indexed":
        # An auto chain still has real engines left to try, so it must never
        # spend hours inside the pure-Python index implementation.
        candidate.extra["python_fallback"] = "deny"
        candidate.extra.pop("python_fallback_confirm", None)
    return candidate


def run_auto_chain(guides, genome_fasta, params, genome=None, log=None,
                   progress_callback=None, **kwargs):
    """Run ``auto`` as a runtime chain over ``auto_engine_candidates``.

    Candidates are attempted in the documented preference order. A failure
    that is not a configuration error (missing binary, build failure, engine
    error) moves on to the next candidate, but only after the reason has been
    logged and the switch approved. Memory-limit failures stop the chain: the
    next engine would ignore the cap that produced them.
    """
    genome_size = _genome_size_or_none(genome_fasta)
    # Rank the candidates with the same defaults the engines will run with.
    # A default SearchParams (max_bulge=1, not explicit) would otherwise pick
    # the bulge order while _attempt_params still zeroes BLAST max_bulge.
    apply_engine_defaults("auto", params, genome_size)
    failures = []
    attempts = []
    for position, name in enumerate(auto_engine_candidates(params, genome_size)):
        try:
            validate_search_params(name, params)
        except (SearchParameterError, ValueError) as exc:
            attempts.append(
                {"engine": name, "started": False, "reason": str(exc)})
            failures.append("%s: %s" % (name, exc))
            continue
        backend = get_backend(name)
        available, unavailable_reason = backend.available()
        if not available:
            attempts.append(
                {"engine": name, "started": False, "reason": unavailable_reason})
            failures.append("%s: %s" % (name, unavailable_reason))
            continue
        if position and not approve_engine_fallback(
                params, name, " | ".join(failures), log=log):
            failures.append("%s: refused by the user" % name)
            break
        if log:
            log("auto engine: running %s" % name)
        try:
            results = backend.search(
                guides, genome_fasta,
                _attempt_params(params, name, genome_size),
                genome=genome,
                progress_callback=progress_callback,
                log=log,
                **kwargs)
        except RuntimeError as exc:
            if getattr(exc, "error_code", "") == "MEMORY_LIMIT_EXCEEDED":
                if log:
                    log("auto engine: %s hit the memory limit; stopping the "
                        "chain" % name)
                raise
            attempts.append(
                {"engine": name, "started": True, "reason": str(exc)})
            failures.append("%s: %s" % (name, exc))
            if log:
                log("auto engine: %s failed: %s" % (name, exc))
            continue
        attempts.append({"engine": name, "started": True, "reason": ""})
        report = getattr(backend, "last_report", None)
        if isinstance(report, dict):
            report["engine_used"] = name
            report["fallback_attempts"] = attempts
            if position:
                report["fallback_from"] = attempts[0]["engine"]
                report["fallback_reason"] = " | ".join(failures)
            extra = getattr(params, "extra", None)
            if isinstance(extra, dict):
                extra["engine_run_report"] = report
        return results
    # An explicitly named resource makes auto single-candidate, so say why
    # no fallback happened instead of leaving the user to guess.
    hint = ""
    if getattr(params, "blastdb", None):
        hint = (" --blastdb was given, so auto only uses blast; specify "
                "--engine to choose a different engine.")
    elif getattr(params, "index_path", None):
        hint = (" --index-path was given, so auto only uses indexed; "
                "specify --engine to choose a different engine.")
    raise RuntimeError(
        "auto could not run an off-target search; tried: %s%s"
        % ("; ".join(failures) or "no candidate engine", hint))


def run_backend(name, guides, genome_fasta, params, genome=None, log=None,
                **kwargs):
    """Run one engine, or the ``auto`` preference chain."""
    if (name or "auto").lower() == "auto":
        return run_auto_chain(guides, genome_fasta, params, genome=genome,
                              log=log, **kwargs)
    engine = resolve_engine(name, params)
    backend = get_backend(engine)
    validate_search_params(engine, params)
    results = backend.search(guides, genome_fasta, params, genome=genome,
                             log=log, **kwargs)
    report = getattr(backend, "last_report", None)
    extra = getattr(params, "extra", None)
    if isinstance(report, dict) and isinstance(extra, dict):
        report.setdefault("engine_used", engine)
        extra["engine_run_report"] = report
    return results


def compare_engines(guides, genome_fasta, params, engine_names,
                    genome=None, reference="exact"):
    """Run several engines and report hit-set agreement/recall."""
    results = {}
    for name in engine_names:
        results[name] = run_backend(name, guides, genome_fasta, params,
                                    genome=genome)
    ref = results.get(reference, next(iter(results.values())))
    summary = {}
    all_qids = set()
    for name, matches in results.items():
        for qid in matches:
            all_qids.add(qid)
    for qid in sorted(all_qids):
        ref_keys = {(h["target"], h["start"], h["strand"])
                    for h in ref.get(qid, [])}
        row = {"reference": len(ref_keys)}
        for name, matches in results.items():
            keys = {(h["target"], h["start"], h["strand"])
                    for h in matches.get(qid, [])}
            row[name] = len(keys)
            if ref_keys:
                row[name + "_recall"] = len(keys & ref_keys) / len(ref_keys)
        summary[qid] = row
    return {"results": results, "summary": summary}
