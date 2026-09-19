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

from search.iupac import iupac_to_regex
from search.alignment import cigar_from_operations
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


def _parse_blast_alignment(query_aligned, target_aligned):
    """Return CIGAR operations and mismatch/bulge counts from BLAST strings."""
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
    return operations, mismatches


def _count_seed_mismatches_aligned(query_aligned, target_aligned, seed_len):
    """Count mismatches in the PAM-proximal seed of a gapped alignment."""
    mismatches = 0
    query_bases = 0
    for query_base, target_base in zip(
            reversed(query_aligned), reversed(target_aligned)):
        if query_base == "-":
            continue
        query_bases += 1
        if target_base == "-" or query_base != target_base:
            mismatches += 1
        if query_bases >= int(seed_len):
            break
    return mismatches


def run_blastn(query_fasta, db_name, task="blastn-short", word_size=4,
               evalue=1000, best_only=False, max_mismatch=None,
               require_pam=False, pam_motif="GG", pam_offset=0,
               seed_mismatch_max=None, seed_len=12, genome=None,
               repeat_intervals=None, pam_side="3prime",
               num_threads=None, perc_identity=None, max_bulge=0):
    """Run blastn and return matches.

    Returns rich hit dictionaries including target span, mismatch, bulge type,
    CIGAR, and aligned sequences. ``max_bulge=0`` runs ungapped BLAST;
    ``max_bulge>0`` enables gapped alignments and filters their actual indels.
    If best_only=True, only the single best match (by bitscore desc) per qid is kept.
    PAM/seed filters need a pyfaidx genome index and are only applied when requested.
    """
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
    if perc_identity is not None:
        cmd += ["-perc_identity", "%.4f" % float(perc_identity)]
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
        repeat_intervals = repeat_intervals or {}
        warned_context_filter = False
        matches = {}
        with open(out_path, "r", encoding="utf-8") as blast_out:
            for line in blast_out:
                line = line.rstrip("\n")
                if not line.strip():
                    continue
                fields = line.split("\t")
                if len(fields) < 12:
                    continue
                qseqid, sseqid, pident, length, mismatch, gapopen, qstart, qend, sstart, send, evalue, bitscore = fields[:12]
                length = int(length)
                mismatch = int(mismatch)
                gapopen = int(gapopen)
                qstart = int(qstart)
                qend = int(qend)
                sstart = int(sstart)
                send = int(send)
                bitscore = float(bitscore)
                query_aligned = fields[12] if len(fields) > 12 else ""
                target_aligned = fields[13] if len(fields) > 13 else ""
                parsed_alignment = _parse_blast_alignment(
                    query_aligned, target_aligned)
                indel = 0
                rna_bulges = 0
                dna_bulges = 0
                cigar = ""
                if parsed_alignment is not None:
                    operations, mismatch = parsed_alignment
                    rna_bulges = operations.count("I")
                    dna_bulges = operations.count("D")
                    indel = rna_bulges + dna_bulges
                    cigar = cigar_from_operations(operations)
                elif gapopen != 0:
                    continue
                query_seq = query_seqs.get(qseqid, "")
                query_len = len(query_seq)
                if query_len <= 0 or qstart != 1 or qend != query_len:
                    continue
                strand = "+" if sstart <= send else "-"
                start = min(sstart, send) - 1
                target_end = max(sstart, send)
                if max_mismatch is not None and mismatch > max_mismatch:
                    continue
                if indel > max_bulge:
                    continue
                if repeat_intervals and is_in_excluded(
                        sseqid, start, repeat_intervals):
                    continue

                if require_pam or seed_mismatch_max is not None:
                    if genome is None:
                        if not warned_context_filter:
                            print(
                                "Warning: PAM/seed filtering requires a "
                                "genome index; filters skipped.")
                            warned_context_filter = True
                    else:
                        if require_pam:
                            if not _pam_ok_blast(
                                    genome, sseqid,
                                    start + pam_offset,
                                    target_end + pam_offset,
                                    strand, pam_motif, pam_side):
                                continue
                        if seed_mismatch_max is not None:
                            if parsed_alignment is not None:
                                seed_mm = _count_seed_mismatches_aligned(
                                    query_aligned, target_aligned, seed_len)
                            else:
                                off = fetch_sequence(
                                    genome, sseqid, start, target_end)
                                if off is None or len(off) < len(query_seq):
                                    continue
                                comparison = (
                                    query_seq if strand == "+"
                                    else reverse_complement(query_seq))
                                seed_mm = _count_seed_mismatches(
                                    comparison, off, seed_len)
                            if seed_mm > seed_mismatch_max:
                                continue

                if qseqid not in matches:
                    matches[qseqid] = []
                matches[qseqid].append({
                    "target": sseqid,
                    "start": start,
                    "target_start": start,
                    "target_end": target_end,
                    "query_start": qstart - 1,
                    "query_end": qend,
                    "mismatch": mismatch,
                    "indel": indel,
                    "rna_bulges": rna_bulges,
                    "dna_bulges": dna_bulges,
                    "cigar": cigar,
                    "aligned_guide": query_aligned,
                    "aligned_target": target_aligned,
                    "bitscore": bitscore,
                    "strand": strand,
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
            rank = (m["mismatch"], m.get("indel", 0))
            old = unique.get(key)
            if old is None or rank < (old["mismatch"], old.get("indel", 0)):
                unique[key] = m
        deduped = list(unique.values())
        if best_only:
            deduped.sort(key=lambda x: x["bitscore"], reverse=True)
            matches[qid] = deduped[:1]
            if matches[qid]:
                matches[qid][0]["rank"] = 1
        else:
            matches[qid] = deduped

    total = sum(len(v) for v in matches.values())
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


def load_genome_and_prepare_fasta(genome_file):
    """Return (pyfaidx Fasta index, FASTA path, temp file object)."""
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
        return Fasta(genome_file), genome_file, None

    if _is_annotation_path(genome_file):
        sibling = _sibling_fasta_for_annotation(genome_file)
        if sibling is not None:
            _log(
                "Annotation file given; using matching genome FASTA: %s"
                % sibling
            )
            return Fasta(sibling), sibling, None
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
    return Fasta(temp_fasta.name), temp_fasta.name, temp_fasta
