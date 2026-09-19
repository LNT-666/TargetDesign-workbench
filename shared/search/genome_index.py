#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Persistent local genome index for exhaustive off-target search.

The index stores contig metadata plus a compact k-mer seed table:
for every k-mer code c, ``positions[offsets[c]:offsets[c + 1]]`` holds the
global 0-based genome positions where that k-mer occurs on the plus strand.

Searching both the guide and its reverse complement therefore covers both
genome strands. Seed layout is shared with the exact backend. A plan is
considered exhaustive only when the non-overlapping seed count is greater
than the bulge budget and the substitution variants fit the configured cap.
"""

import argparse
import bisect
import hashlib
import json
import os
import struct
import sys
import time

import numpy as np

try:
    from Bio import SeqIO
except ImportError:  # pragma: no cover
    SeqIO = None

try:
    from pyfaidx import Fasta
except ImportError:  # pragma: no cover
    Fasta = None

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from search.alignment import best_alignment
from search.exact_offtarget import (
    _alignment_to_hit, _fetch, _pam_ok_span, _pam_sequence_span,
    reverse_complement,
)
from search.seed_plan import build_seed_plan, iter_seed_variants
from utils.system_memory import (
    available_memory_mb as _system_available_memory_mb,
)


MAGIC = b"CRISPRGGI"
FORMAT_VERSION = 1
DEFAULT_K = 12
MAX_EXHAUSTIVE_FALLBACK_BASES = 50000000
_BASE_VALUES = {"A": 0, "C": 1, "G": 2, "T": 3}


def suggest_k(genome_size_bytes):
    """Pick a compact k that keeps the offsets table small for small genomes."""
    if genome_size_bytes < 1000000:
        return 8
    if genome_size_bytes < 10000000:
        return 10
    if genome_size_bytes < 100000000:
        return 11
    return DEFAULT_K


def select_index_k(genome_size_bytes, guide_lengths, max_mismatch, max_bulge,
                   requested_k=None):
    """Choose the largest compatible index k, preserving an explicit request."""
    if requested_k is not None:
        return int(requested_k)
    preferred_k = int(suggest_k(genome_size_bytes))
    lengths = sorted({
        int(length) for length in guide_lengths if int(length) > 0
    })
    if not lengths:
        return preferred_k
    for candidate_k in range(preferred_k, 0, -1):
        if all(
                build_seed_plan(
                    length, max_mismatch, max_bulge,
                    candidate_k, candidate_k,
                ).guaranteed
                for length in lengths
        ):
            return candidate_k
    return preferred_k


def reverse_complement_index(seq):
    """Public alias so callers do not depend on exact_offtarget internals."""
    return reverse_complement(seq)


def genome_fingerprint(path):
    """Cheap but reliable fingerprint: size, mtime and first/last 64 KiB."""
    stat = os.stat(path)
    digest = hashlib.sha256()
    digest.update(b"%d:%d" % (stat.st_size, stat.st_mtime_ns))
    with open(path, "rb") as handle:
        digest.update(handle.read(1 << 16))
        try:
            handle.seek(max(0, stat.st_size - (1 << 16)))
        except OSError:
            pass
        digest.update(handle.read(1 << 16))
    return digest.hexdigest()


def _current_rss_mb():
    """Current resident set size in MB; returns 0.0 when unavailable."""
    if sys.platform == "win32":
        try:
            import ctypes

            class ProcessMemoryCountersEx(ctypes.Structure):
                _fields_ = [
                    ("cb", ctypes.c_ulong),
                    ("PageFaultCount", ctypes.c_ulong),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                ]

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            psapi = ctypes.WinDLL("psapi", use_last_error=True)
            kernel32.GetCurrentProcess.restype = ctypes.c_void_p
            psapi.GetProcessMemoryInfo.argtypes = [
                ctypes.c_void_p,
                ctypes.POINTER(ProcessMemoryCountersEx),
                ctypes.c_size_t,
            ]
            psapi.GetProcessMemoryInfo.restype = ctypes.c_bool
            counters = ProcessMemoryCountersEx()
            counters.cb = ctypes.sizeof(counters)
            ok = psapi.GetProcessMemoryInfo(
                kernel32.GetCurrentProcess(),
                ctypes.byref(counters), counters.cb)
            if not ok:
                return 0.0
            return counters.WorkingSetSize / 1048576.0
        except Exception:
            return 0.0
    try:
        import resource
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0
    except Exception:
        return 0.0


class _MemTracker:
    def __init__(self):
        self.peak = 0.0
        self.sample()

    def sample(self):
        value = _current_rss_mb()
        self.peak = max(self.peak, value)
        return value


class MemoryLimitExceededError(RuntimeError):
    """Raised when a Python indexed operation exceeds its memory budget."""

    error_code = "MEMORY_LIMIT_EXCEEDED"


class _MemoryBudget:
    def __init__(self, limit_mb=None, tracker=None):
        try:
            self.limit_mb = max(0, int(limit_mb or 0))
        except (TypeError, ValueError):
            self.limit_mb = 0
        self.tracker = tracker

    def check(self, stage, estimated_mb=None):
        if self.limit_mb <= 0:
            return
        if estimated_mb is not None and int(estimated_mb) > self.limit_mb:
            raise MemoryLimitExceededError(
                "Memory limit exceeded during %s: estimated peak %d MiB "
                "exceeds --max-memory-mb=%d MiB"
                % (stage, int(estimated_mb), self.limit_mb)
            )
        current_mb = _current_rss_mb()
        if self.tracker is not None:
            self.tracker.peak = max(self.tracker.peak, current_mb)
        if current_mb > self.limit_mb:
            raise MemoryLimitExceededError(
                "Memory limit exceeded during %s: RSS %.2f MiB exceeds "
                "--max-memory-mb=%d MiB"
                % (stage, current_mb, self.limit_mb)
            )


def _estimate_index_build_peak_mb(k, total_bases, valid_count=0):
    code_count = 4 ** int(k)
    position_bytes = 8 if total_bases >= 2 ** 32 else 4
    table_bytes = (
        code_count * 24
        + int(valid_count) * position_bytes * 2
    )
    return 128 + (table_bytes + 1024 * 1024 - 1) // (1024 * 1024)


def _estimate_indexed_search_peak_mb(
        genome_bytes, index_bytes, worker_count, use_sequence_cache):
    workers = max(1, int(worker_count or 1))
    per_worker = 24
    if use_sequence_cache:
        per_worker += int(genome_bytes * 1.25 // (1024 * 1024)) + 1
    return (
        160
        + int(index_bytes) // (1024 * 1024)
        + workers * per_worker
    )


def _available_memory_mb():
    """Best-effort free RAM in MB, or None when unknown."""
    value = _system_available_memory_mb()
    return value if value > 0 else None


def _use_sequence_cache(fasta_path, requested):
    """Decide whether to load the FASTA into memory for window reads."""
    if requested is False:
        return False
    genome_bytes = os.path.getsize(fasta_path)
    if requested is True:
        return True
    if genome_bytes <= 600 * 1024 * 1024:
        return True
    available_mb = _available_memory_mb()
    if available_mb is None:
        return False
    # Sequence objects cost roughly 2.5-3x their raw FASTA size.
    needed_mb = genome_bytes * 3 / (1024 * 1024) + 2048
    return available_mb >= needed_mb


def _load_fasta_sequences(fasta_path):
    """Read FASTA records into plain ASCII strings (fast, memory-heavy)."""
    sequences = {}
    current_name = None
    buffer = bytearray()

    def flush():
        if current_name is not None:
            sequences[current_name] = bytes(buffer).decode("ascii").upper()
            buffer.clear()

    with open(fasta_path, "rb") as handle:
        for raw_line in handle:
            if raw_line.startswith(b">"):
                flush()
                header = raw_line[1:].strip().split(None, 1)[0]
                current_name = header.decode("ascii")
            else:
                buffer.extend(raw_line.rstrip(b"\r\n"))
    flush()
    if not sequences:
        raise ValueError("No FASTA records found: %s" % fasta_path)
    return sequences


def _kmer_code(kmer):
    code = 0
    for char in kmer.upper():
        value = _BASE_VALUES.get(char)
        if value is None:
            return -1
        code = (code << 2) | value
    return code


def _seed_variants(seed, max_mismatch):
    """Compatibility wrapper for the shared uncapped variant generator."""
    return set(iter_seed_variants(seed, max_mismatch))


def _encode_chunk(chunk, k, chunk_start, contig_start):
    """Return (kmer codes, global positions) for valid ACGT k-mers."""
    n = len(chunk)
    if n < k:
        return (np.empty(0, dtype=np.uint32),
                np.empty(0, dtype=np.uint64))
    raw = np.frombuffer(chunk.encode("ascii"), dtype=np.uint8)
    base = np.full(n, 255, dtype=np.uint8)
    for i, char in enumerate(b"ACGT"):
        base[raw == char] = i
    invalid = (base == 255).astype(np.int64)
    cumulative = np.concatenate(([0], np.cumsum(invalid)))
    valid = (cumulative[k:] - cumulative[:-k]) == 0
    if not valid.any():
        return (np.empty(0, dtype=np.uint32),
                np.empty(0, dtype=np.uint64))
    windows = np.lib.stride_tricks.sliding_window_view(base, k)
    powers = (1 << (2 * (k - 1 - np.arange(k)))).astype(np.uint64)
    codes = (windows @ powers)[valid].astype(np.uint32)
    positions = np.arange(chunk_start, chunk_start + n - k + 1,
                          dtype=np.uint64)[valid]
    positions = positions + contig_start
    return codes, positions


def _iter_sequences(genome_path, contigs, max_records):
    if SeqIO is None:
        raise RuntimeError(
            "Biopython is required to build the genome index")
    count = 0
    with open(genome_path, "r", encoding="utf-8") as handle:
        for record in SeqIO.parse(handle, "fasta"):
            if contigs is not None and record.id not in contigs:
                continue
            yield record
            count += 1
            if max_records is not None and count >= max_records:
                break


def build_index(genome_path, prefix, k=DEFAULT_K, max_records=None,
                contigs=None, chunk_size=5000000, log=None,
                max_memory_mb=None):
    """Build a persistent index at ``prefix.ggi`` plus ``prefix.json``.

    Returns the metadata dict (also written as the JSON sidecar).
    """
    start_time = time.perf_counter()
    tracker = _MemTracker()
    budget = _MemoryBudget(max_memory_mb, tracker)
    genome_path = os.path.abspath(genome_path)
    if not os.path.isfile(genome_path):
        raise FileNotFoundError("Genome FASTA not found: %s" % genome_path)
    budget.check(
        "counts",
        _estimate_index_build_peak_mb(k, 0),
    )

    contig_meta = []
    total_bases = 0
    for record in _iter_sequences(genome_path, contigs, max_records):
        contig_meta.append({
            "id": record.id,
            "start": total_bases,
            "length": len(record.seq),
        })
        total_bases += len(record.seq)
    if not contig_meta:
        raise ValueError("No sequences matched the requested contigs")
    budget.check(
        "counts",
        _estimate_index_build_peak_mb(k, total_bases),
    )

    selected = {c["id"]: c for c in contig_meta}
    code_chunks = []
    position_chunks = []
    valid_count = 0
    if max_records is not None and contigs is None:
        selected = dict(list(selected.items())[:max_records])
    for record in _iter_sequences(genome_path, contigs, max_records):
        if record.id not in selected:
            continue
        meta = selected[record.id]
        seq = str(record.seq).upper()
        if len(seq) < k:
            continue
        for chunk_start in range(0, len(seq) - k + 1, chunk_size):
            chunk = seq[chunk_start:chunk_start + chunk_size + k - 1]
            codes, positions = _encode_chunk(
                chunk, k, chunk_start, meta["start"])
            if codes.size:
                code_chunks.append(codes)
                position_chunks.append(positions)
                valid_count += codes.size
        if log:
            percent = 100.0 * (meta["start"] + len(seq)) / total_bases
            log("PROGRESS: index %s %d" % (record.id, int(percent)))
        budget.check("postings")
    if not code_chunks:
        raise ValueError("No valid ACGT k-mers found for k=%d" % k)

    budget.check(
        "postings",
        _estimate_index_build_peak_mb(k, total_bases, valid_count),
    )
    codes = np.concatenate(code_chunks)
    positions = np.concatenate(position_chunks)
    budget.check("sort")
    order = np.argsort(codes, kind="stable")
    codes = codes[order]
    positions = positions[order]
    del order

    counts = np.bincount(codes, minlength=4 ** k).astype(np.uint64)
    offsets = np.zeros(len(counts) + 1, dtype=np.uint64)
    offsets[1:] = np.cumsum(counts)
    del codes, counts

    if total_bases < 2 ** 32:
        position_dtype = "u4"
        positions = positions.astype(np.dtype("<u4"), copy=False)
    else:
        position_dtype = "u8"
        positions = positions.astype(np.dtype("<u8"), copy=False)

    index_dir = os.path.dirname(os.path.abspath(prefix))
    if index_dir:
        os.makedirs(index_dir, exist_ok=True)
    temp_path = prefix + ".ggi.tmp"
    budget.check(
        "index output",
        _estimate_index_build_peak_mb(k, total_bases, valid_count),
    )
    try:
        with open(temp_path, "wb") as handle:
            handle.write(MAGIC)
            handle.write(struct.pack("<B", FORMAT_VERSION))
            handle.write(
                struct.pack("<IIQ", k, len(contig_meta), total_bases))
            for contig in contig_meta:
                name = contig["id"].encode("utf-8")
                handle.write(struct.pack("<I", len(name)))
                handle.write(name)
                handle.write(struct.pack("<QQ", contig["start"],
                                         contig["length"]))
            handle.write(struct.pack("<Q", valid_count))
            handle.write(
                np.ascontiguousarray(offsets, dtype="<u8").tobytes())
            handle.write(np.ascontiguousarray(positions).tobytes())
        budget.check("index output")
        os.replace(temp_path, prefix + ".ggi")
    except Exception:
        try:
            os.remove(temp_path)
        except OSError:
            pass
        raise

    tracker.sample()
    estimated_peak_mb = _estimate_index_build_peak_mb(
        k, total_bases, valid_count)
    report = {
        "format": "crispr-genome-index",
        "version": FORMAT_VERSION,
        "k": int(k),
        "genome": genome_path,
        "genome_fingerprint": genome_fingerprint(genome_path),
        "genome_bytes": os.path.getsize(genome_path),
        "total_bases": int(total_bases),
        "valid_kmer_positions": int(valid_count),
        "contig_count": len(contig_meta),
        "contigs": contig_meta,
        "position_dtype": position_dtype,
        "build_time_s": round(time.perf_counter() - start_time, 3),
        "memory_peak_mb": round(tracker.peak, 2),
        "memory_limit_mb": budget.limit_mb,
        "estimated_peak_mb": int(estimated_peak_mb),
        "observed_peak_mb": round(tracker.peak, 2),
        "index_bytes": os.path.getsize(prefix + ".ggi"),
    }
    with open(prefix + ".json", "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False)
    return report


def _locate(contig_meta, starts, global_pos):
    idx = bisect.bisect_right(starts, global_pos) - 1
    if idx < 0:
        return None
    contig = contig_meta[idx]
    local = global_pos - contig["start"]
    if local >= contig["length"]:
        return None
    return contig["id"], local


class GenomeIndex:
    """Read-only k-mer seed index loaded from ``prefix.ggi``."""

    def __init__(self, prefix, meta, contigs, k, total_bases, offsets,
                 positions):
        self.prefix = prefix
        self.meta = meta
        self.contigs = contigs
        self.k = k
        self.total_bases = total_bases
        self.offsets = offsets
        self.positions = positions
        self.contig_starts = [c["start"] for c in contigs]

    def is_valid_for(self, genome_path):
        if not os.path.exists(genome_path):
            return False
        return self.meta.get("genome_fingerprint") == \
            genome_fingerprint(genome_path)

    def positions_for(self, kmer):
        code = _kmer_code(kmer)
        if code < 0 or code >= len(self.offsets) - 1:
            return ()
        lo = int(self.offsets[code])
        hi = int(self.offsets[code + 1])
        if hi <= lo:
            return ()
        return self.positions[lo:hi]


def load_index(prefix):
    """Load a ``.ggi`` index; raises on missing or malformed files."""
    ggi_path = prefix + ".ggi"
    meta_path = prefix + ".json"
    if not os.path.isfile(ggi_path):
        raise FileNotFoundError("Index file not found: %s" % ggi_path)
    if not os.path.isfile(meta_path):
        raise FileNotFoundError("Index metadata not found: %s" % meta_path)
    with open(meta_path, "r", encoding="utf-8") as handle:
        meta = json.load(handle)
    with open(ggi_path, "rb") as handle:
        magic = handle.read(len(MAGIC))
        if magic != MAGIC:
            raise ValueError("Not a CRISPR genome index file")
        version = struct.unpack("<B", handle.read(1))[0]
        if version != FORMAT_VERSION:
            raise ValueError("Unsupported index version: %d" % version)
        k, contig_count, total_bases = struct.unpack(
            "<IIQ", handle.read(16))
        contigs = []
        for _ in range(contig_count):
            name_len = struct.unpack("<I", handle.read(4))[0]
            name = handle.read(name_len).decode("utf-8")
            start, length = struct.unpack("<QQ", handle.read(16))
            contigs.append({"id": name, "start": start, "length": length})
        valid_count = struct.unpack("<Q", handle.read(8))[0]
        offsets = np.fromfile(handle, dtype=np.dtype("<u8"),
                              count=4 ** k + 1)
        if offsets.size != 4 ** k + 1:
            raise ValueError("Index offsets table is truncated")
        position_dtype = np.dtype("<u4") if total_bases < 2 ** 32 \
            else np.dtype("<u8")
        positions = np.fromfile(handle, dtype=position_dtype,
                                count=valid_count)
        if positions.size != valid_count:
            raise ValueError("Index position table is truncated")
    return GenomeIndex(prefix, meta, contigs, k, total_bases,
                       offsets, positions)


def _search_probe(index, probe, genome, target_strand, max_mismatch,
                  max_bulge, seed_len, seed_mm, pam, pam_side, context,
                  fetch_func=None, memory_budget=None):
    hits = []
    seen = set()
    checkpoint_counter = 0

    def checkpoint():
        nonlocal checkpoint_counter
        if memory_budget is None:
            return
        checkpoint_counter += 1
        if checkpoint_counter % 256 == 0:
            memory_budget.check("search")

    if memory_budget is not None:
        memory_budget.check("search")
    probe_len = len(probe)
    if probe_len < index.k:
        return hits
    plan = build_seed_plan(
        probe_len, max_mismatch, max_bulge, seed_len, index.k)
    fetch = fetch_func or (
        lambda seqid, start, end: _fetch(genome, seqid, start, end))
    pam_fetch = (
        (lambda _genome, seqid, start, end:
         fetch_func(seqid, start, end))
        if fetch_func is not None else None
    )

    if not plan.guaranteed:
        if index.total_bases > MAX_EXHAUSTIVE_FALLBACK_BASES:
            raise RuntimeError(
                "Unsupported indexed search configuration: %s. "
                "Use the exact backend, a smaller index k, or reduce "
                "max_bulge/max_mismatch." % plan.reason
            )
        for contig in index.contigs:
            seqid = contig["id"]
            sequence = fetch(seqid, 0, int(contig["length"]))
            if sequence is None:
                continue
            for candidate_start in range(
                    0, max(0, len(sequence) - probe_len + max_bulge + 1)):
                checkpoint()
                window_start = max(0, candidate_start - max_bulge)
                window_end = min(
                    len(sequence),
                    candidate_start + probe_len + max_bulge,
                )
                window = sequence[window_start:window_end]
                alignment = best_alignment(
                    window, probe, candidate_start - window_start,
                    max_bulge, max_mismatch=max_mismatch,
                    accept_alignment=lambda local_start, local_end: (
                        _pam_ok_span(
                            genome, seqid, window_start + local_start,
                            window_start + local_end, target_strand,
                            pam, pam_side, fetch_func=pam_fetch)
                    ),
                )
                if alignment is None:
                    continue
                if (alignment.mismatches > max_mismatch
                        or alignment.indels > max_bulge):
                    continue
                hit = _alignment_to_hit(
                    alignment, seqid, window_start, target_strand)
                hit_key = (
                    seqid, hit["target_start"], hit["target_end"],
                    target_strand,
                )
                if hit_key in seen:
                    continue
                if not _pam_ok_span(
                        genome, seqid, hit["target_start"],
                        hit["target_end"], target_strand, pam, pam_side,
                        fetch_func=pam_fetch):
                    continue
                hit["pam"] = _pam_sequence_span(
                    genome, seqid, hit["target_start"], hit["target_end"],
                    target_strand, pam, pam_side, fetch_func=pam_fetch)
                seen.add(hit_key)
                hits.append(hit)
        return hits

    for segment in plan.segments:
        seed = probe[segment.start:segment.end]
        for offset in range(0, len(seed) - index.k + 1):
            seed_kmer = seed[offset:offset + index.k]
            for kmer in iter_seed_variants(
                    seed_kmer, segment.allowed_mismatches):
                for global_pos in index.positions_for(kmer):
                    checkpoint()
                    candidate_start = (
                        int(global_pos) - segment.start - offset
                    )
                    if candidate_start < 0:
                        continue
                    located = _locate(
                        index.contigs, index.contig_starts, candidate_start)
                    if located is None:
                        continue
                    seqid, local_start = located
                    candidate_key = (
                        seqid, local_start, target_strand)
                    if candidate_key in seen:
                        continue
                    fetch_start = max(0, local_start - context)
                    fetch_end = local_start + probe_len + context
                    window = fetch(seqid, fetch_start, fetch_end)
                    if window is None:
                        continue
                    center = local_start - fetch_start
                    alignment = best_alignment(
                        window, probe, center, max_bulge,
                        max_mismatch=max_mismatch,
                        accept_alignment=lambda local_start, local_end: (
                            _pam_ok_span(
                                genome, seqid, fetch_start + local_start,
                                fetch_start + local_end, target_strand,
                                pam, pam_side, fetch_func=pam_fetch)
                        ),
                    )
                    if alignment is None:
                        continue
                    if (alignment.mismatches > max_mismatch
                            or alignment.indels > max_bulge):
                        continue
                    hit = _alignment_to_hit(
                        alignment, seqid, fetch_start, target_strand)
                    hit_key = (
                        seqid, hit["target_start"], hit["target_end"],
                        target_strand,
                    )
                    if hit_key in seen:
                        continue
                    if not _pam_ok_span(
                            genome, seqid, hit["target_start"],
                            hit["target_end"], target_strand, pam, pam_side,
                            fetch_func=pam_fetch):
                        continue
                    hit["pam"] = _pam_sequence_span(
                        genome, seqid, hit["target_start"],
                        hit["target_end"], target_strand, pam, pam_side,
                        fetch_func=pam_fetch)
                    seen.add(candidate_key)
                    seen.add(hit_key)
                    hits.append(hit)
    return hits


def search_indexed(index, guides, genome_fasta, max_mismatch=4,
                   max_bulge=1, seed_len=DEFAULT_K, seed_mm=1,
                   pam=None, pam_side="3prime", context=40, log=None,
                   progress_callback=None, cache_genome=None,
                   max_memory_mb=None):
    """Search guides against a prebuilt index.

    Returns ``(matches, report)`` where matches maps qid to hit lists.
    """
    start_time = time.perf_counter()
    tracker = _MemTracker()
    budget = _MemoryBudget(max_memory_mb, tracker)
    use_sequence_cache = _use_sequence_cache(genome_fasta, cache_genome)
    genome_bytes = os.path.getsize(genome_fasta)
    estimated_peak_mb = _estimate_indexed_search_peak_mb(
        genome_bytes, index.meta.get("index_bytes", 0)
        or os.path.getsize(index.prefix + ".ggi"),
        1,
        use_sequence_cache,
    )
    if (budget.limit_mb > 0 and use_sequence_cache
            and estimated_peak_mb > budget.limit_mb):
        if cache_genome is True:
            budget.check("search startup", estimated_peak_mb)
        use_sequence_cache = False
        estimated_peak_mb = _estimate_indexed_search_peak_mb(
            genome_bytes, index.meta.get("index_bytes", 0)
            or os.path.getsize(index.prefix + ".ggi"),
            1,
            False,
        )
    budget.check("search startup", estimated_peak_mb)
    sequence_cache = {}
    genome = None
    if use_sequence_cache:
        try:
            sequence_cache = _load_fasta_sequences(genome_fasta)
        except Exception:
            sequence_cache = {}
            use_sequence_cache = False
    if not use_sequence_cache:
        if Fasta is None:
            raise RuntimeError(
                "pyfaidx is required for indexed off-target search")
        genome = Fasta(genome_fasta)

    def cached_fetch(seqid, start, end):
        seq = sequence_cache.get(seqid)
        if seq is None:
            return None
        start = max(0, int(start))
        end = min(len(seq), int(end))
        if start >= end:
            return None
        return seq[start:end]

    fetch_func = cached_fetch if use_sequence_cache else None
    out = {}
    candidate_count = 0
    try:
        for i, guide_item in enumerate(guides):
            budget.check("search")
            if isinstance(guide_item, dict):
                seq = guide_item.get("guide_seq") or \
                    guide_item.get("spacer_seq") or ""
                qid = guide_item.get("qid") or guide_item.get("seq_id") or \
                    "guide_%d" % i
            else:
                seq = guide_item
                qid = "guide_%d" % i
            seq = seq.upper().replace("U", "T")
            if not seq:
                continue
            if log:
                percent = int(100.0 * (i + 1) / len(guides))
                log("PROGRESS: guide %s %d" % (qid, percent))
                log("PROGRESS_TARGET: %d/%d" % (i + 1, len(guides)))
            elif progress_callback:
                progress_callback(i + 1, len(guides))
            for probe, strand in ((seq, "+"),
                                  (reverse_complement(seq), "-")):
                hits = _search_probe(index, probe, genome, strand,
                                     max_mismatch=max_mismatch,
                                     max_bulge=max_bulge,
                                     seed_len=seed_len,
                                     seed_mm=seed_mm,
                                     pam=pam, pam_side=pam_side,
                                     context=context,
                                     fetch_func=fetch_func,
                                     memory_budget=budget)
                candidate_count += len(hits)
                for hit in hits:
                    hit["qid"] = qid
                    hit["guide"] = seq
                    out.setdefault(qid, []).append(hit)
    finally:
        close = getattr(genome, "close", None)
        if genome is not None and callable(close):
            close()

    for qid, hits in out.items():
        unique = {}
        for hit in hits:
            key = (
                hit["target"], hit.get("target_start", hit["start"]),
                hit.get("target_end", hit["start"] + len(hit["guide"])),
                hit["strand"],
            )
            rank = (hit["mismatch"], hit.get("indel", 0))
            if key not in unique:
                unique[key] = hit
                continue
            old = unique[key]
            if rank < (old["mismatch"], old.get("indel", 0)):
                unique[key] = hit
        out[qid] = sorted(unique.values(),
                          key=lambda x: (
                              x["mismatch"], x.get("indel", 0),
                              x["target"], x["start"],
                              x.get("target_end", 0)))
    tracker.sample()
    estimated_peak_mb = max(
        estimated_peak_mb,
        _estimate_indexed_search_peak_mb(
            genome_bytes,
            index.meta.get("index_bytes", 0)
            or os.path.getsize(index.prefix + ".ggi"),
            1,
            use_sequence_cache,
        ),
    )
    report = {
        "search_time_s": round(time.perf_counter() - start_time, 3),
        "search_memory_peak_mb": round(tracker.peak, 2),
        "memory_limit_mb": budget.limit_mb,
        "estimated_peak_mb": int(estimated_peak_mb),
        "observed_peak_mb": round(tracker.peak, 2),
        "guides": len(guides),
        "hits": sum(len(v) for v in out.values()),
        "candidates": candidate_count,
        "seed_len": seed_len,
        "seed_mm": seed_mm,
        "seed_plan": [
            {
                "start": segment.start,
                "length": segment.length,
                "allowed_mismatches": segment.allowed_mismatches,
            }
            for segment in build_seed_plan(
                max((len(g.get("guide_seq") or "") for g in guides), default=0),
                max_mismatch, max_bulge, seed_len, index.k).segments
        ],
        "exhaustive_seed_plan": build_seed_plan(
            max((len(g.get("guide_seq") or "") for g in guides), default=0),
            max_mismatch, max_bulge, seed_len, index.k).guaranteed,
        "sequence_cache": bool(use_sequence_cache),
    }
    return out, report


def main():
    parser = argparse.ArgumentParser(
        description="Build a reusable local genome index for off-target search")
    parser.add_argument("genome", help="Genome FASTA")
    parser.add_argument("--output-dir", default=None,
                        help="Directory for index files (default: next to "
                             "the FASTA)")
    parser.add_argument("--prefix", default=None,
                        help="Explicit output prefix (overrides --output-dir)")
    parser.add_argument("--k", type=int, default=DEFAULT_K,
                        help="k-mer seed size (default: %d)" % DEFAULT_K)
    parser.add_argument("--contigs", default="",
                        help="Comma-separated contig ids to index")
    parser.add_argument("--max-records", type=int, default=None)
    parser.add_argument("--chunk-size", type=int, default=5000000)
    parser.add_argument(
        "--max-memory-mb", type=int, default=None,
        help="Explicit process RSS limit in MiB; omitted or 0 is unlimited")
    args = parser.parse_args()

    if args.prefix:
        prefix = args.prefix
    else:
        output_dir = args.output_dir or os.path.dirname(
            os.path.abspath(args.genome))
        base = os.path.splitext(os.path.basename(args.genome))[0]
        prefix = os.path.join(output_dir, base)
    contigs = [c.strip() for c in args.contigs.split(",") if c.strip()] or None
    if args.max_records is None and contigs:
        args.max_records = len(contigs)

    def log(message):
        print(message, flush=True)

    report = build_index(
        args.genome, prefix, k=args.k, max_records=args.max_records,
        contigs=contigs, chunk_size=args.chunk_size, log=log,
        max_memory_mb=args.max_memory_mb)
    print("INDEX_READY: %s.ggi" % prefix, flush=True)
    print("REPORT: %s" % json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
