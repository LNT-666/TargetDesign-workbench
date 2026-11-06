#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Shared genome database / Off-target search utilities for all analysis pipelines."""

import sys
import os
import re
import hashlib
import json
import subprocess
import tempfile
from datetime import datetime, timezone

try:
    from Bio import SeqIO
except ImportError:
    SeqIO = None

try:
    from pyfaidx import Fasta
except ImportError:
    Fasta = None

from search.iupac import IUPAC_REGEX, iupac_to_regex
from search.alignment import (
    align_global, cigar_from_operations, reverse_complement_gapped,
)
from data.annotation_utils import ensure_plain_fasta, is_gzip_file


def default_blast_threads():
    """Pick a sensible blastn thread count, capped to avoid oversubscription."""
    try:
        requested = int(os.environ.get("BLAST_NUM_THREADS") or 0)
    except (TypeError, ValueError):
        requested = 0
    if requested > 0:
        return max(1, requested)
    return max(1, min(os.cpu_count() or 2, 32))


def check_blast_installed():
    """Verify blastn and makeblastdb are available."""
    for cmd in ["blastn", "makeblastdb"]:
        try:
            subprocess.run([cmd, "-h"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except FileNotFoundError:
            print(f"Error: {cmd} not found. Please install NCBI BLAST+.")
            sys.exit(3)


def _sha256_file(path, chunk_size=1024 * 1024):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _makeblastdb_version():
    try:
        result = subprocess.run(
            ["makeblastdb", "-version"], capture_output=True, text=True)
    except FileNotFoundError:
        return ""
    text = (result.stdout or result.stderr or "").strip()
    return text.splitlines()[0] if text else ""


def _blastdb_files_exist(db_name):
    return all(
        os.path.isfile(db_name + extension)
        for extension in (".nin", ".nsq")
    )


def blastdb_manifest_path(db_name):
    return db_name + ".source.json"


def read_blastdb_manifest(db_name):
    path = blastdb_manifest_path(db_name)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError, TypeError):
        return None


def blastdb_is_current(fasta_file, db_name):
    """Return True only when the db files and a matching sidecar exist."""
    if not _blastdb_files_exist(db_name):
        return False
    manifest = read_blastdb_manifest(db_name)
    if not manifest:
        return False
    fasta_file = os.path.abspath(fasta_file)
    try:
        stat = os.stat(fasta_file)
    except OSError:
        return False
    if os.path.abspath(manifest.get("source_fasta", "")) != fasta_file:
        return False
    if int(manifest.get("fasta_size", -1)) != int(stat.st_size):
        return False
    if int(manifest.get("fasta_mtime_ns", -1)) != int(stat.st_mtime_ns):
        return False
    return manifest.get("fasta_sha256") == _sha256_file(fasta_file)


def write_blastdb_manifest(fasta_file, db_name):
    fasta_file = os.path.abspath(fasta_file)
    stat = os.stat(fasta_file)
    payload = {
        "format": "programfile-blastdb-source",
        "version": 1,
        "source_fasta": fasta_file,
        "fasta_size": int(stat.st_size),
        "fasta_mtime_ns": int(stat.st_mtime_ns),
        "fasta_sha256": _sha256_file(fasta_file),
        "makeblastdb_version": _makeblastdb_version(),
        "built_at": datetime.now(timezone.utc).isoformat(),
    }
    path = blastdb_manifest_path(db_name)
    temp_path = path + ".tmp"
    with open(temp_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
    os.replace(temp_path, path)
    return payload


def build_blastdb(fasta_file, db_name, log=None, trust_existing=False):
    """Build a nucleotide genome database from a FASTA file.

    Existing files are reused only when the source manifest matches. Missing
    manifests and stale FASTA fingerprints force a rebuild unless the caller
    explicitly requests ``trust_existing=True``.
    """
    out = log if log else _log
    db_dir = os.path.dirname(db_name)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    if _blastdb_files_exist(db_name):
        if trust_existing:
            out(
                "WARNING: trusting existing BLAST database without "
                "validating its source manifest: %s" % db_name
            )
            return
        if blastdb_is_current(fasta_file, db_name):
            out(f"Genome database {db_name} already exists, skipping.")
            return
        reason = (
            "source manifest is missing"
            if not os.path.isfile(blastdb_manifest_path(db_name))
            else "FASTA changed or manifest does not match"
        )
        out(f"Genome database {db_name} is stale ({reason}); rebuilding.")
    out(f"Building genome database: {db_name} ...")
    cmd = ["makeblastdb", "-in", fasta_file, "-dbtype", "nucl", "-out", db_name]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            out(f"Failed: {result.stderr}")
            sys.exit(5)
        write_blastdb_manifest(fasta_file, db_name)
        out("Database built.")
    except FileNotFoundError:
        sys.exit(3)


def ensure_blastdb(fasta_file, output_dir=None, db_name=None, log=None,
                   trust_existing=False):
    """Build (or reuse) a genome database from a FASTA file.

    Database files are placed in <output_dir>/blastdb/ (or next to the FASTA
    when output_dir is None). Returns the database prefix.
    """
    if output_dir is None:
        output_dir = os.path.dirname(os.path.abspath(fasta_file))
    db_dir = os.path.join(output_dir, "blastdb")
    if db_name is None:
        base = os.path.splitext(os.path.basename(fasta_file))[0]
        db_name = base + ".blastdb"
    db_prefix = os.path.join(db_dir, db_name)
    build_blastdb(
        fasta_file, db_prefix, log=log, trust_existing=trust_existing)
    return db_prefix


def find_existing_blastdb(genome_fasta, output_dir=None,
                          trust_existing=False, log=None):
    """Return a validated BLAST db prefix near the FASTA when one exists."""
    if not os.path.isfile(genome_fasta):
        return None
    directory = os.path.dirname(os.path.abspath(genome_fasta))
    genome_stem = os.path.splitext(os.path.basename(genome_fasta))[0]
    candidates = [
        os.path.join(directory, "blastdb", genome_stem + ".blastdb"),
        os.path.join(directory, genome_stem + ".blastdb"),
        os.path.join(directory, genome_stem),
    ]
    if output_dir:
        candidates.append(
            os.path.join(output_dir, "blastdb", genome_stem + ".blastdb"))
    for prefix in candidates:
        if trust_existing and _blastdb_files_exist(prefix):
            if log:
                log(
                    "WARNING: trusting existing BLAST database without "
                    "validating its source manifest: %s" % prefix
                )
            return prefix
        if blastdb_is_current(genome_fasta, prefix):
            return prefix
    return None


def _query_sequences_from_fasta(query_fasta):
    if SeqIO is None:
        return {}
    try:
        with open(query_fasta, "r", encoding="utf-8") as handle:
            return {rec.id: str(rec.seq).upper()
                    for rec in SeqIO.parse(handle, "fasta")}
    except Exception:
        return {}


def _count_seed_mismatches(query_seq, target_seq, seed_len):
    seed_start = max(0, len(query_seq) - seed_len)
    query_seed = query_seq[seed_start:]
    target_seed = target_seq[seed_start:]
    return sum(1 for a, b in zip(query_seed, target_seed) if a != b)


def queries_embed_pam(sequences, motif, pam, flank_len):
    """Return whether extracted windows carry the PAM inside each sequence."""
    if not sequences or not motif or not pam or flank_len is None:
        return False
    motif = motif.upper().replace("U", "T")
    pam = pam.upper().replace("U", "T")
    if motif != pam:
        return False
    expected_len = flank_len + len(motif)
    return all(len(seq) == expected_len for seq in sequences)


def _pam_matches(seq, pam_pattern):
    """Return whether ``seq`` matches an IUPAC PAM pattern."""
    if not seq:
        return False
    return bool(
        re.fullmatch(
            iupac_to_regex(pam_pattern),
            seq.upper().replace("U", "T"),
        )
    )


#: IUPAC code -> the concrete bases it allows.
_IUPAC_BASE_SETS = {
    code: frozenset(re.findall(r"[ACGT]", chars))
    for code, chars in IUPAC_REGEX.items()
}


def pam_patterns_may_overlap(motif, pam):
    """Return whether a motif pattern can sit on the PAM at a window edge.

    A TnpB TAM belongs *outside* a downstream target window, so its motif and
    PAM patterns disagree.  A window that really embeds the PAM carries the
    motif as the PAM itself or as a degenerate prefix of it, so every motif
    position is compatible with the PAM position it covers.
    """

    motif = str(motif or "").upper().replace("U", "T")
    pam = str(pam or "").upper().replace("U", "T")
    if not motif or not pam:
        return False
    return all(
        _IUPAC_BASE_SETS.get(a, frozenset())
        & _IUPAC_BASE_SETS.get(b, frozenset())
        for a, b in zip(motif, pam)
    )


def pam_span_in_window(sequence, motif, pam, side="downstream"):
    """Return ``(span, expected)`` for a PAM anchored inside a window.

    ``basic/extract.py`` anchors every window on the extraction motif and
    stores it on the plus strand of the search FASTA, so a PAM that belongs
    to that motif lies *inside* the window instead of beyond it::

        downstream / plus  -> motif + flank       (PAM at the 5-prime edge)
        downstream / minus -> flank + rc(motif)   (PAM at the 3-prime edge)
        upstream   / plus  -> flank + motif       (PAM at the 3-prime edge)
        upstream   / minus -> rc(motif) + flank   (PAM at the 5-prime edge)

    ``span`` is the half-open PAM span in query coordinates and ``expected``
    is the pattern that span has to match (``pam`` when the window is stored
    in its biological orientation, ``rc(pam)`` when it is stored reversed).
    ``None`` means the motif is not on a window edge, so the PAM has to be
    looked up outside the window instead.
    """
    if not sequence or not motif or not pam:
        return None
    sequence = sequence.upper().replace("U", "T")
    motif = motif.upper().replace("U", "T")
    pam = pam.upper().replace("U", "T")
    if not motif or len(motif) > len(sequence) or len(pam) > len(sequence):
        return None
    if not pam_patterns_may_overlap(motif, pam):
        return None
    five_prime = side != "upstream"
    for pattern, expected, at_five_prime in (
            (motif, pam, five_prime),
            (reverse_complement(motif), reverse_complement(pam),
             not five_prime)):
        if len(pattern) > len(sequence):
            continue
        edge = (sequence[:len(pattern)] if at_five_prime
                else sequence[len(sequence) - len(pattern):])
        if not _pam_matches(edge, pattern):
            continue
        span = ((0, len(pam)) if at_five_prime
                else (len(sequence) - len(pam), len(sequence)))
        return span, expected
    return None


def _pam_ok_blast(genome, seqid, target_start, target_end, strand, pam,
                  pam_side):
    """Check PAM against a BLAST hit in its reported strand orientation."""
    if not pam:
        return True
    pam = pam.upper().replace("U", "T")
    if strand == "+":
        if pam_side == "5prime":
            seq = fetch_sequence(
                genome, seqid, target_start - len(pam), target_start)
        else:
            seq = fetch_sequence(
                genome, seqid, target_end, target_end + len(pam))
    else:
        rc_pam = reverse_complement(pam)
        if pam_side == "5prime":
            seq = fetch_sequence(
                genome, seqid, target_end, target_end + len(pam))
            expected = rc_pam
        else:
            seq = fetch_sequence(
                genome, seqid, target_start - len(pam), target_start)
            expected = rc_pam
        return _pam_matches(seq, expected)
    return _pam_matches(seq, pam)


def _alignment_fields(query_aligned, target_aligned):
    """Derive CIGAR, substitutions, and bulge classes from one alignment."""
    query_aligned = str(query_aligned or "").upper()
    target_aligned = str(target_aligned or "").upper()
    if not query_aligned or len(query_aligned) != len(target_aligned):
        return None
    operations = []
    mismatches = 0
    for query_base, target_base in zip(query_aligned, target_aligned):
        if query_base == "-" and target_base == "-":
            return None
        if query_base == "-":
            operations.append("D")
        elif target_base == "-":
            operations.append("I")
        elif query_base == target_base:
            operations.append("M")
        else:
            operations.append("X")
            mismatches += 1
    rna_bulges = operations.count("I")
    dna_bulges = operations.count("D")
    return {
        "mismatch": mismatches,
        "indel": rna_bulges + dna_bulges,
        "rna_bulges": rna_bulges,
        "dna_bulges": dna_bulges,
        "cigar": cigar_from_operations(operations),
    }


def _oriented_alignment_strings(alignment, strand):
    """Return one rebuilt alignment in the original query orientation."""
    query_aligned = alignment.query_aligned
    target_aligned = alignment.target_aligned
    if strand == "-":
        query_aligned = reverse_complement_gapped(query_aligned)
        target_aligned = reverse_complement_gapped(target_aligned)
    return query_aligned, target_aligned


def _seed_interval(query_len, seed_len, pam_side, pam_anchor=None):
    """Return the PAM-proximal query interval used by the seed filter."""
    query_len = int(query_len)
    seed_len = max(0, min(int(seed_len or 0), query_len))
    if seed_len == 0:
        return 0, 0
    if pam_anchor is not None:
        pam_start, pam_end = pam_anchor[0]
        if pam_start <= 0:
            return pam_end, min(query_len, pam_end + seed_len)
        if pam_end >= query_len:
            return max(0, pam_start - seed_len), pam_start
    if pam_side == "5prime":
        return 0, seed_len
    return query_len - seed_len, query_len


def _count_seed_mismatches_aligned(
        query_aligned, target_aligned, seed_len, seed_start=None):
    """Count seed edits, counting RNA gaps as mismatches in seed budget."""
    query_aligned = str(query_aligned or "").upper()
    target_aligned = str(target_aligned or "").upper()
    query_len = len(query_aligned.replace("-", ""))
    if seed_start is None:
        seed_start = max(0, query_len - int(seed_len or 0))
    seed_end = min(query_len, int(seed_start) + int(seed_len or 0))
    mismatches = 0
    query_pos = 0
    for query_base, target_base in zip(query_aligned, target_aligned):
        if query_base == "-":
            continue
        if seed_start <= query_pos < seed_end:
            if target_base == "-" or query_base != target_base:
                mismatches += 1
        query_pos += 1
    return mismatches


def _pam_ok_rebuilt(query_aligned, target_aligned, span, expected):
    """Check an embedded PAM against a contiguous target mapping."""
    query_aligned = str(query_aligned or "").upper()
    target_aligned = str(target_aligned or "").upper()
    if (not span or not expected
            or len(query_aligned) != len(target_aligned)):
        return False
    span_start, span_end = (int(span[0]), int(span[1]))
    query_len = len(query_aligned.replace("-", ""))
    if span_start < 0 or span_end <= span_start or span_end > query_len:
        return False
    query_pos = 0
    target_pos = 0
    target_bases = []
    target_positions = []
    for query_base, target_base in zip(query_aligned, target_aligned):
        if query_base == "-" and target_base == "-":
            return False
        if query_base == "-":
            if span_start <= query_pos < span_end:
                return False
            if target_base != "-":
                target_pos += 1
            continue
        if span_start <= query_pos < span_end:
            if target_base == "-":
                return False
            target_bases.append(target_base)
            target_positions.append(target_pos)
        query_pos += 1
        if target_base != "-":
            target_pos += 1
    if (len(target_positions) != span_end - span_start
            or not target_positions):
        return False
    first_target_pos = target_positions[0]
    if any(pos != first_target_pos + offset
           for offset, pos in enumerate(target_positions)):
        return False
    return (len(target_bases) == span_end - span_start
            and _pam_matches("".join(target_bases), expected))


def _rebuilt_candidates(genome, seqid, probe, center, max_bulge):
    """Yield every full-query target interval in one HSP neighborhood."""
    probe = str(probe or "").upper().replace("U", "T")
    query_len = len(probe)
    if query_len == 0 or genome is None:
        return
    try:
        chrom_len = len(genome[seqid])
    except KeyError:
        return
    max_bulge = max(0, int(max_bulge))
    center = int(center)
    start_lo = max(0, center - max_bulge)
    start_hi = min(chrom_len, center + max_bulge)
    min_len = max(1, query_len - max_bulge)
    max_len = query_len + max_bulge
    window_start = max(0, start_lo)
    window_end = min(chrom_len, start_hi + max_len)
    window = fetch_sequence(genome, seqid, window_start, window_end)
    if not window:
        return
    for target_start in range(start_lo, start_hi + 1):
        for target_len in range(min_len, max_len + 1):
            target_end = target_start + target_len
            if target_end > chrom_len:
                break
            local_start = target_start - window_start
            local_end = target_end - window_start
            target = window[local_start:local_end]
            if len(target) != target_len:
                continue
            alignment = align_global(probe, target)
            yield target_start, target_end, alignment


def _candidate_center(query_len, qstart, qend, sstart, send, strand):
    """Estimate the full-query target start from both HSP end offsets."""
    hsp_start = min(sstart, send) - 1
    hsp_end = max(sstart, send)
    if strand == "+":
        probe_qstart = qstart - 1
        probe_qend = qend
    else:
        probe_qstart = query_len - qend
        probe_qend = query_len - (qstart - 1)
    start_from_left = hsp_start - probe_qstart
    start_from_right = hsp_end - probe_qend
    return int(round((start_from_left + start_from_right) / 2.0))


def run_blastn(query_fasta, db_name, task="blastn-short", word_size=4,
               evalue=1000, best_only=False, max_mismatch=None,
               require_pam=False, pam_motif="GG", pam_offset=0,
               seed_mismatch_max=None, seed_len=12, genome=None,
               repeat_intervals=None, pam_side="3prime",
               num_threads=None, max_bulge=0,
               window_motif=None, window_side="downstream"):
    """Run blastn and return matches.

    BLAST is only a candidate generator. Every hit is rebuilt from the actual
    reference with ``align_global`` using the full query; coordinates, counts,
    CIGAR, and aligned strings all come from that rebuilt alignment.
    ``max_bulge=0`` runs ungapped BLAST; ``max_bulge>0`` enables gapped
    candidate generation and constrains the rebuilt alignments.
    If best_only=True, only the single best match (by bitscore desc) per qid is kept.
    PAM/seed filters use the rebuilt alignment and require a pyfaidx genome.

    ``window_motif`` names the extraction motif that anchors each query
    window. When it is given, a PAM that sits at that motif edge is checked
    against the aligned target site itself instead of the sequence beyond the
    window, which is what a window that already carries its PAM requires.
    """
    if genome is None:
        raise RuntimeError(
            "BLAST full-length realignment requires a reference FASTA/genome")
    if num_threads is None:
        num_threads = default_blast_threads()
    cmd = [
        "blastn",
        "-db", db_name,
        "-query", query_fasta,
        "-outfmt", "6 qseqid sseqid pident length mismatch gapopen qstart qend sstart send evalue bitscore qseq sseq",
        "-task", task,
        "-word_size", str(word_size),
        "-num_threads", str(max(1, int(num_threads))),
        "-evalue", str(evalue),
        "-strand", "both",
        "-dust", "no",
        "-soft_masking", "false"
    ]
    max_bulge = max(0, int(0 if max_bulge is None else max_bulge))
    if max_bulge == 0:
        cmd.append("-ungapped")
    print("Running blastn ...")
    out_tmp = tempfile.NamedTemporaryFile(
        mode="w+", suffix=".tsv", delete=False, encoding="utf-8")
    out_path = out_tmp.name
    out_tmp.close()
    try:
        os.unlink(out_path)
    except OSError:
        pass
    err_tmp = tempfile.NamedTemporaryFile(
        mode="w+", suffix=".err", delete=False, encoding="utf-8")
    cmd += ["-out", out_path]
    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.DEVNULL, stderr=err_tmp)
        proc.wait()
        err_tmp.flush()
        err_tmp.seek(0)
        stderr_text = err_tmp.read()
        err_tmp.close()
        if proc.returncode != 0:
            print("blastn failed:")
            print(stderr_text)
            sys.exit(4)

        query_seqs = _query_sequences_from_fasta(query_fasta)
        if not query_seqs:
            raise RuntimeError("BLAST query FASTA could not be read")
        repeat_intervals = repeat_intervals or {}
        pam_anchors = {}
        if window_motif and pam_motif:
            for query_seq in query_seqs.values():
                pam_anchors[query_seq] = pam_span_in_window(
                    query_seq, window_motif, pam_motif, window_side)
        dropped_by_pam = 0
        matches = {}
        seen_hsps = set()
        with open(out_path, "r", encoding="utf-8") as blast_out:
            for line in blast_out:
                line = line.rstrip("\n")
                if not line.strip():
                    continue
                fields = line.split("\t")
                if len(fields) < 12:
                    continue
                (qseqid, sseqid, pident, length, hsp_mismatch,
                 gapopen, qstart, qend, sstart, send, evalue,
                 bitscore) = fields[:12]
                hsp_length = int(length)
                hsp_mismatch = int(hsp_mismatch)
                gapopen = int(gapopen)
                qstart = int(qstart)
                qend = int(qend)
                sstart = int(sstart)
                send = int(send)
                pident = float(pident)
                evalue = float(evalue)
                bitscore = float(bitscore)
                hsp_query_aligned = fields[12] if len(fields) > 12 else ""
                hsp_target_aligned = fields[13] if len(fields) > 13 else ""
                query_seq = query_seqs.get(qseqid, "")
                query_len = len(query_seq)
                if query_len <= 0:
                    continue
                strand = "+" if sstart <= send else "-"
                hsp_key = (
                    qseqid, sseqid, strand, qstart, qend, sstart, send,
                )
                if hsp_key in seen_hsps:
                    continue
                seen_hsps.add(hsp_key)
                probe = (query_seq if strand == "+"
                         else reverse_complement(query_seq))
                center = _candidate_center(
                    query_len, qstart, qend, sstart, send, strand)
                for start, target_end, alignment in _rebuilt_candidates(
                        genome, sseqid, probe, center, max_bulge):
                    query_aligned, target_aligned = \
                        _oriented_alignment_strings(alignment, strand)
                    rebuilt = _alignment_fields(
                        query_aligned, target_aligned)
                    if rebuilt is None:
                        continue
                    if (max_mismatch is not None
                            and rebuilt["mismatch"] > max_mismatch):
                        continue
                    if rebuilt["indel"] > max_bulge:
                        continue
                    if repeat_intervals and is_in_excluded(
                            sseqid, start, repeat_intervals):
                        continue

                    anchor = pam_anchors.get(query_seq)
                    if require_pam:
                        if anchor is not None:
                            pam_ok = _pam_ok_rebuilt(
                                query_aligned, target_aligned,
                                anchor[0], anchor[1])
                        else:
                            pam_ok = _pam_ok_blast(
                                genome, sseqid,
                                start + pam_offset,
                                target_end + pam_offset,
                                strand, pam_motif, pam_side)
                        if not pam_ok:
                            dropped_by_pam += 1
                            continue

                    if seed_mismatch_max is not None:
                        seed_start, seed_end = _seed_interval(
                            query_len, seed_len, pam_side, anchor)
                        seed_mm = _count_seed_mismatches_aligned(
                            query_aligned, target_aligned,
                            seed_end - seed_start, seed_start)
                        if seed_mm > seed_mismatch_max:
                            continue

                    if qseqid not in matches:
                        matches[qseqid] = []
                    matches[qseqid].append({
                        "target": sseqid,
                        "start": start,
                        "target_start": start,
                        "target_end": target_end,
                        "query_start": 0,
                        "query_end": query_len,
                        "mismatch": rebuilt["mismatch"],
                        "indel": rebuilt["indel"],
                        "rna_bulges": rebuilt["rna_bulges"],
                        "dna_bulges": rebuilt["dna_bulges"],
                        "cigar": rebuilt["cigar"],
                        "aligned_guide": query_aligned,
                        "aligned_target": target_aligned,
                        "bitscore": bitscore,
                        "strand": strand,
                        "hsp": {
                            "pident": pident,
                            "length": hsp_length,
                            "mismatch": hsp_mismatch,
                            "gapopen": gapopen,
                            "qstart": qstart,
                            "qend": qend,
                            "sstart": sstart,
                            "send": send,
                            "evalue": evalue,
                            "bitscore": bitscore,
                            "query_aligned": hsp_query_aligned,
                            "target_aligned": hsp_target_aligned,
                        },
                    })
    finally:
        try:
            os.unlink(out_path)
        except OSError:
            pass
        try:
            os.unlink(err_tmp.name)
        except OSError:
            pass

    # Deduplicate: keep the best alignment per target span and strand.
    for qid in matches:
        unique = {}
        for m in matches[qid]:
            key = (
                m["target"], m.get("target_start", m["start"]),
                m.get("target_end", m["start"]), m.get("strand", "+"),
            )
            rank = (
                m["mismatch"], m.get("indel", 0),
                2 * m["mismatch"] + 3 * m.get("indel", 0),
                m.get("cigar", ""),
            )
            old = unique.get(key)
            old_rank = None if old is None else (
                old["mismatch"], old.get("indel", 0),
                2 * old["mismatch"] + 3 * old.get("indel", 0),
                old.get("cigar", ""),
            )
            if old is None or rank < old_rank:
                unique[key] = m
        deduped = list(unique.values())
        deduped.sort(key=lambda x: (
            x["mismatch"], x.get("indel", 0),
            2 * x["mismatch"] + 3 * x.get("indel", 0),
            x.get("cigar", ""), x["target"], x["start"],
            x.get("target_end", 0), x.get("strand", "+"),
        ))
        if best_only:
            deduped.sort(key=lambda x: x["bitscore"], reverse=True)
            matches[qid] = deduped[:1]
            if matches[qid]:
                matches[qid][0]["rank"] = 1
        else:
            matches[qid] = deduped

    total = sum(len(v) for v in matches.values())
    if dropped_by_pam and not total:
        print("Warning: the required PAM check rejected all %d blastn hits; "
              "check --pam-motif/--pam-side against the query window layout."
              % dropped_by_pam)
    print(f"blastn complete, {total} valid matches.")
    return matches


def _log(msg):
    print(msg)
    sys.stdout.flush()


def fetch_sequence(genome, rec_id, start, end):
    """Return upper-cased [start, end) sequence, or None if unavailable."""
    if Fasta is None:
        _log("Error: pyfaidx required for indexed genome access.")
        sys.exit(6)
    try:
        chrom = genome[rec_id]
    except KeyError:
        return None
    chrom_len = len(chrom)
    start = max(0, start)
    end = min(chrom_len, end)
    if start >= end:
        return None
    try:
        return str(chrom[start:end]).upper()
    except Exception:
        return None


# ---------- ?????? ----------

def reverse_complement(seq):
    """??????????????????????????????????"""
    from Bio.Seq import Seq
    return str(Seq(seq).reverse_complement())


def orient_off_target_pair(raw_off, raw_pam, hit_strand, guide_strand):
    """Convert a genomic off-target segment to the guide's 5'->3' orientation.

    ``raw_off`` / ``raw_pam`` are the plus-strand genome sequences at a hit.
    ``hit_strand`` is the match strand reported by the search engine relative
    to the stored query; ``guide_strand`` is the candidate's plus/minus strand.
    """
    off_query = raw_off if hit_strand == "+" else reverse_complement(raw_off)
    pam_query = raw_pam if hit_strand == "+" else reverse_complement(raw_pam)
    if guide_strand in ("minus", "-"):
        off_query = reverse_complement(off_query)
        pam_query = reverse_complement(pam_query)
    return off_query, pam_query


def max_inverted_repeat_len(seq, min_len=3):
    """???????????????????????????????????????????????????????????????????p??????????????????????????????????????????????????????????????????????????????"""
    seq = seq.upper()
    L = len(seq)
    best = 0
    for l in range(min_len, L // 2 + 1):
        found = False
        for i in range(L - 2 * l + 1):
            sub1 = seq[i:i + l]
            rev_comp = reverse_complement(sub1)
            for j in range(i + l, L - l + 1):
                if seq[j:j + l] == rev_comp:
                    found = True
                    break
            if found:
                break
        if found:
            best = l
        else:
            break
    return best


# ---------- ?????? ----------

def build_exclusion_intervals(mask_fasta, genome):
    """Build exact-match exclusion intervals from mask FASTA sequences."""
    if is_gzip_file(mask_fasta):
        prepared = ensure_plain_fasta(mask_fasta)
        if not prepared:
            raise ValueError(f"Could not decompress mask FASTA: {mask_fasta}")
        mask_fasta = prepared
    mask_seqs = [str(rec.seq).upper() for rec in SeqIO.parse(mask_fasta, "fasta")]
    if not mask_seqs:
        print("Warning: No sequences in masked gene file; no regions excluded.")
        return {}
    intervals = {}
    for name in genome.keys():
        seq = fetch_sequence(genome, name, 0, len(genome[name]))
        if seq is None:
            continue
        rec_intervals = []
        for pattern in mask_seqs:
            start = 0
            while True:
                pos = seq.find(pattern, start)
                if pos == -1:
                    break
                rec_intervals.append((pos, pos + len(pattern)))
                start = pos + 1
        if rec_intervals:
            rec_intervals.sort()
            merged = []
            for s, e in rec_intervals:
                if not merged or s > merged[-1][1]:
                    merged.append([s, e])
                else:
                    merged[-1][1] = max(merged[-1][1], e)
            intervals[name] = [(s, e) for s, e in merged]
    return intervals


def is_in_excluded(rec_id, pos, intervals):
    # [fixed] # [fixed] # [fixed] ...
    if rec_id in intervals:
        for start, end in intervals[rec_id]:
            if start <= pos < end:
                return True
    return False



def load_genome_records(genome_file):
    """Return a pyfaidx Fasta index for the genome."""
    if Fasta is None:
        _log("Error: pyfaidx required for indexed genome access.")
        sys.exit(6)
    try:
        return Fasta(genome_file)
    except Exception:
        _log(f"Cannot read genome file {genome_file}, check format.")
        sys.exit(6)


def _looks_like_fasta(genome_file):
    with open(genome_file, "rb") as fh:
        for line in fh:
            stripped = line.strip()
            if stripped and not stripped.startswith(b"#"):
                return stripped.startswith(b">")
    return False


def _is_annotation_path(path):
    return os.path.splitext(path)[1].lower() in (
        ".gff", ".gff3", ".gtf")


def _sibling_fasta_for_annotation(annotation_path):
    """Find the nucleotide FASTA that usually sits next to a GFF/GTF."""
    directory = os.path.dirname(os.path.abspath(annotation_path))
    filename = os.path.basename(annotation_path)
    root, ext = os.path.splitext(filename)
    if ext.lower() not in (".gff", ".gff3", ".gtf"):
        return None
    core = root
    for suffix in ("_with_utrs", "_with_UTR", "_utrs", "_UTR"):
        if core.lower().endswith(suffix.lower()):
            core = core[:-(len(suffix))]
            break
    for fasta_ext in (".fna", ".fa", ".fasta"):
        candidate = os.path.join(directory, core + fasta_ext)
        if os.path.isfile(candidate):
            return candidate
    return None


def prepare_genome_fasta(genome_file):
    """Return ``(FASTA path, temporary file object)`` for reference access."""
    if Fasta is None:
        _log("Error: pyfaidx required for indexed genome access.")
        sys.exit(6)
    if not os.path.isfile(genome_file):
        _log(f"Cannot read genome file {genome_file}, check format.")
        sys.exit(6)
    if is_gzip_file(genome_file):
        # gzip 基因组（.fna.gz）先就地解压成纯文本，pyfaidx 不接受普通 gzip FASTA
        prepared = ensure_plain_fasta(genome_file, log_func=_log)
        if not prepared:
            _log(f"Cannot read genome file {genome_file}, check format.")
            sys.exit(6)
        genome_file = prepared
    if _looks_like_fasta(genome_file):
        return genome_file, None

    if _is_annotation_path(genome_file):
        sibling = _sibling_fasta_for_annotation(genome_file)
        if sibling is not None:
            _log(
                "Annotation file given; using matching genome FASTA: %s"
                % sibling
            )
            return sibling, None
        _log(
            "The genome file looks like an annotation file (%s). "
            "Provide the genome FASTA (.fna) used for BLAST search."
            % genome_file
        )
        sys.exit(6)

    _log("Detected non-FASTA input, converting to temporary FASTA ...")
    temp_fasta = tempfile.NamedTemporaryFile(mode="w", suffix=".fa", delete=False)
    try:
        SeqIO.write(SeqIO.parse(genome_file, "genbank"), temp_fasta, "fasta")
    except Exception:
        temp_fasta.close()
        try:
            os.unlink(temp_fasta.name)
        except OSError:
            pass
        _log(f"Cannot read genome file {genome_file}, check format.")
        sys.exit(6)
    temp_fasta.close()
    return temp_fasta.name, temp_fasta


def load_genome_and_prepare_fasta(genome_file):
    """Return (pyfaidx Fasta index, FASTA path, temp file object)."""
    prepared_fasta, temp_file = prepare_genome_fasta(genome_file)
    return Fasta(prepared_fasta), prepared_fasta, temp_file
