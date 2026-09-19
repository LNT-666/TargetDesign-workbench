#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Batch/library helpers for guide design across many target regions."""

import csv
import json
import os

try:
    from pyfaidx import Fasta
except ImportError:
    Fasta = None


def load_regions(path):
    """Load 0-based half-open regions from a BED-like TSV file."""
    regions = []
    with open(path, "r", encoding="utf-8") as handle:
        reader = csv.reader(handle, delimiter="\t")
        for i, row in enumerate(reader):
            if not row or row[0].startswith("#"):
                continue
            if i == 0 and row[0].lower() in ("chrom", "seqid", "chr"):
                continue
            if len(row) < 3:
                continue
            seqid = row[0]
            try:
                start = int(row[1])
                end = int(row[2])
            except ValueError:
                continue
            name = row[3] if len(row) > 3 and row[3] else "region_%d" % (i + 1)
            regions.append({"seqid": seqid, "start": start, "end": end,
                            "name": name, "strand": row[5] if len(row) > 5 else "+"})
    return regions


def extract_region_sequences(genome_fasta, regions, pad=0):
    """Extract FASTA sequences for each region using pyfaidx."""
    if Fasta is None:
        raise RuntimeError("pyfaidx is required for region extraction")
    genome = Fasta(genome_fasta)
    out = []
    try:
        for region in regions:
            chrom = genome[region["seqid"]]
            chrom_len = len(chrom)
            start = max(0, region["start"] - pad)
            end = min(chrom_len, region["end"] + pad)
            if start >= end:
                continue
            seq = str(chrom[start:end]).upper()
            out.append({
                "seq_id": region["seqid"],
                "region": region["name"],
                "start": start,
                "end": end,
                "strand": region.get("strand", "+"),
                "sequence": seq,
            })
    finally:
        close = getattr(genome, "close", None)
        if callable(close):
            close()
    return out


def deduplicate_guides(guides):
    """Deduplicate guides by sequence while preserving region counts."""
    by_seq = {}
    order = []
    for guide in guides:
        seq = guide.get("guide_seq") or ""
        if not seq:
            continue
        if seq not in by_seq:
            by_seq[seq] = dict(guide)
            by_seq[seq]["regions"] = []
            by_seq[seq]["genomic_positions"] = []
            by_seq[seq]["occurrence_count"] = 0
            order.append(seq)
        item = by_seq[seq]
        region = guide.get("region") or guide.get("seq_id") or ""
        if region and region not in item["regions"]:
            item["regions"].append(region)
        if guide.get("genomic_start") is not None and guide.get(
                "genomic_end") is not None:
            item["genomic_positions"].append({
                "region": region,
                "seq_id": guide.get("seq_id", "") or region,
                "strand": guide.get("genomic_strand", ""),
                "start": guide.get("genomic_start"),
                "end": guide.get("genomic_end"),
            })
        item["occurrence_count"] += 1
    return [by_seq[seq] for seq in order]


def library_summary(guides):
    total = len(guides)
    unique = len({g.get("guide_seq") for g in guides if g.get("guide_seq")})
    gcs = [g["gc"] for g in guides if isinstance(g.get("gc"), (int, float))]
    return {
        "candidate_count": total,
        "unique_guide_count": unique,
        "gc_mean": round(sum(gcs) / len(gcs), 4) if gcs else 0.0,
        "gc_min": round(min(gcs), 4) if gcs else 0.0,
        "gc_max": round(max(gcs), 4) if gcs else 0.0,
    }


def write_library_tsv(guides, path, fields=None):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    if not guides:
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write("")
        return
    if fields is None:
        fields = ["region", "seq_id", "strand", "guide_seq", "pam_seq",
                  "spacer_start", "spacer_end", "motif_overlap", "gc",
                  "occurrence_count", "regions", "preset"]
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t",
                                extrasaction="ignore")
        writer.writeheader()
        writer.writerows(guides)


def write_library_summary(summary, path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, ensure_ascii=False)


def _read_query_sidecar(tsv_path):
    """Read the FASTA sidecar written next to a motif query TSV."""
    sidecar = os.path.splitext(tsv_path)[0] + ".queries.fa"
    if not os.path.isfile(sidecar):
        return None
    rows = []
    current_id = None
    seq_parts = []

    def flush():
        if current_id is not None and seq_parts:
            rows.append((current_id, "".join(seq_parts)))

    with open(sidecar, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            if line.startswith(">"):
                flush()
                current_id = line[1:].strip().split()[0]
                seq_parts = []
            else:
                seq_parts.append(line)
    flush()
    return rows


def _region_description(row):
    """Build a region:chrom:start:end:strand:target_start description."""
    positions = row.get("positions")
    if positions:
        try:
            entries = json.loads(positions)
        except (ValueError, TypeError):
            return ""
        if not entries:
            return ""
        entry = entries[0]
        seq_id = str(entry[0])
        target_start = int(entry[3]) if len(entry) > 3 else None
    else:
        seq_id = str(row.get("seq_id", ""))
        target_start = None
    parts = seq_id.split(":")
    if len(parts) < 3:
        return ""
    try:
        start0, end0 = parts[1].split("-", 1)
        chrom = parts[0]
        start0 = int(start0)
        end0 = int(end0)
        strand = parts[2]
    except (ValueError, IndexError):
        return ""
    if target_start is None:
        target_start = _row_target_start(row)
    return "region:%s:%s:%s:%s:%s" % (
        chrom, start0, end0, strand, int(target_start or 0))


def _row_target_start(row):
    """Best-effort target offset within the window for a motif TSV row."""
    for key in ("target_start", "compound_start"):
        value = row.get(key)
        if value not in (None, ""):
            try:
                return int(value)
            except (ValueError, TypeError):
                pass
    left = row.get("left_pos")
    right = row.get("right_pos")
    if left not in (None, "") and right not in (None, ""):
        try:
            return int(min(int(left), int(right)))
        except (ValueError, TypeError):
            pass
    return 0


def _region_from_seq_id(seq_id, target_start=0):
    """Build a region description from a chrom:start-end:strand id."""
    parts = str(seq_id or "").split(":")
    if len(parts) < 3:
        return ""
    try:
        start0, end0 = parts[1].split("-", 1)
        return "region:%s:%s:%s:%s:%s" % (
            parts[0], int(start0), int(end0), parts[2], int(target_start or 0))
    except (ValueError, IndexError):
        return ""


def _tsv_region_map(path):
    """Map qid -> region description from a motif query TSV."""
    result = {}
    with open(path, "r", encoding="utf-8") as handle:
        reader = csv.DictReader(
            (line for line in handle if not line.lstrip().startswith("#")),
            delimiter="\t",
        )
        for row in reader:
            qid = row.get("qid") or row.get("seq_id")
            if not qid:
                continue
            desc = _region_description(row)
            if desc:
                result[qid] = desc
    return result


def parse_region_description(description):
    """Parse a region:chrom:start:end:strand[:target_start] header, or None."""
    if not description:
        return None
    for token in description.split():
        if not token.startswith("region:"):
            continue
        try:
            fields = token.split(":")
            _, chrom, start0, end0, strand = fields[:5]
            target_start = int(fields[5]) if len(fields) > 5 else 0
            return {
                "chrom": chrom,
                "start": int(start0),
                "end": int(end0),
                "strand": strand,
                "target_start": target_start,
            }
        except (ValueError, IndexError):
            return None
    return None


def queries_to_fasta(tsv_path_or_dir, fasta_path):
    """Collect query sequences from motif TSV files into one FASTA.

    Accepts a single TSV (query_seq/sequence columns) or a directory of
    occurrence TSVs written by the motif extract scripts.
    """
    rows = []
    paths = []
    if os.path.isdir(tsv_path_or_dir):
        for name in sorted(os.listdir(tsv_path_or_dir)):
            if name.endswith(".tsv"):
                paths.append(os.path.join(tsv_path_or_dir, name))
    elif os.path.isfile(tsv_path_or_dir):
        paths.append(tsv_path_or_dir)
    else:
        raise FileNotFoundError(tsv_path_or_dir)

    for path in paths:
        sidecar_rows = _read_query_sidecar(path)
        if sidecar_rows is not None:
            desc_by_qid = _tsv_region_map(path)
            rows.extend(
                (qid, seq, desc_by_qid.get(qid, ""))
                for qid, seq in sidecar_rows
            )
            continue
        with open(path, "r", encoding="utf-8") as handle:
            reader = csv.DictReader(
                (line for line in handle if not line.lstrip().startswith("#")),
                delimiter="\t")
            for row in reader:
                seq = row.get("query_seq") or row.get("sequence") or ""
                if seq:
                    qid = row.get("qid") or row.get("seq_id") or \
                        "seq_%d" % (len(rows) + 1)
                    rows.append((qid, seq, _region_description(row)))

    if not rows:
        raise ValueError("no query sequences found in %s"
                         % tsv_path_or_dir)
    with open(fasta_path, "w", encoding="utf-8", newline="") as handle:
        for qid, seq, desc in rows:
            if desc:
                handle.write(">%s %s\n%s\n" % (qid, desc, seq))
            else:
                handle.write(">%s\n%s\n" % (qid, seq))
    return len(rows)
