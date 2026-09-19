#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GFF3 interval index and candidate annotation helpers (compact layout)."""

import os
from collections import defaultdict


GENE_TYPES = {"gene", "pseudogene", "ncRNA_gene", "rRNA_gene", "tRNA_gene"}
TRANSCRIPT_TYPES = {
    "mRNA", "transcript", "primary_transcript", "lnc_RNA", "ncRNA",
    "miRNA", "tRNA", "rRNA", "snoRNA", "snRNA", "antisense_RNA",
    "misc_RNA", "guide_RNA", "telomerase_RNA", "vault_RNA", "Y_RNA",
    "RNase_P_RNA", "RNase_MRP_RNA",
    "C_gene_segment", "V_gene_segment", "D_gene_segment", "J_gene_segment",
}
UTR_TYPES = {"five_prime_UTR", "three_prime_UTR", "5'UTR", "3'UTR"}

TYPE_CODES = {
    "gene": 0,
    "mRNA": 1,
    "exon": 2,
    "CDS": 3,
    "five_prime_UTR": 4,
    "three_prime_UTR": 5,
    "transcript": 6,
}
CODE_TYPES = {value: key for key, value in TYPE_CODES.items()}
STRAND_CODES = {"+": 0, "-": 1, ".": 2}
CODE_STRANDS = {value: key for key, value in STRAND_CODES.items()}

_COMPLEMENT = str.maketrans("ACGTN", "TGCAN")


def reverse_complement(seq):
    return seq.upper().translate(_COMPLEMENT)[::-1]


def _parse_attrs(attr_str):
    attrs = {}
    if not attr_str or attr_str == ".":
        return attrs
    for item in attr_str.split(";"):
        if not item:
            continue
        if "=" in item:
            key, value = item.split("=", 1)
            attrs[key.strip()] = value.strip()
        elif " " in item:
            key, value = item.split(" ", 1)
            attrs[key.strip()] = value.strip().strip('"')
    return attrs


def _gene_name_from_attrs(attrs):
    return (attrs.get("gene") or attrs.get("Name") or
            attrs.get("gene_name") or attrs.get("locus_tag") or "")


def _mane_rank(tag_text):
    tags = tag_text or ""
    if "MANE Select" in tags or "MANE_Select" in tags:
        return 0
    if "MANE Plus Clinical" in tags or "MANE_Plus_Clinical" in tags:
        return 1
    return 2


def _compute_utrs(transcript):
    exons = sorted(transcript.get("exons", []))
    cds = sorted(transcript.get("cds", []))
    if not exons or not cds:
        return []
    utrs = []
    first_exon_start, last_exon_end = exons[0][0], exons[-1][1]
    first_cds_start, last_cds_end = cds[0][0], cds[-1][1]
    if transcript["strand"] == "+":
        if first_exon_start < first_cds_start:
            utrs.append((first_exon_start, first_cds_start - 1, "five_prime_UTR"))
        if last_cds_end < last_exon_end:
            utrs.append((last_cds_end + 1, last_exon_end, "three_prime_UTR"))
    else:
        if last_cds_end < last_exon_end:
            utrs.append((last_cds_end + 1, last_exon_end, "five_prime_UTR"))
        if first_exon_start < first_cds_start:
            utrs.append((first_exon_start, first_cds_start - 1, "three_prime_UTR"))
    return utrs


class AnnotationIndex:
    def __init__(self):
        self.features = defaultdict(list)
        self.tss = defaultdict(list)
        self.genes = []
        self.transcripts = []
        self._gene_id_to_idx = {}
        self._transcript_id_to_idx = {}
        self.gene_count = 0
        self.transcript_count = 0

    def _intern_gene(self, gid, attrs):
        if gid in self._gene_id_to_idx:
            return self._gene_id_to_idx[gid]
        idx = len(self.genes)
        self.genes.append({
            "gene_id": attrs.get("gene_id", gid),
            "name": _gene_name_from_attrs(attrs),
            "locus_tag": attrs.get("locus_tag", ""),
            "biotype": attrs.get("gene_biotype", ""),
        })
        self._gene_id_to_idx[gid] = idx
        self.gene_count += 1
        return idx

    def _intern_transcript(self, tid, attrs, gene_idx, seqid, start, end, strand):
        if tid in self._transcript_id_to_idx:
            return self._transcript_id_to_idx[tid]
        idx = len(self.transcripts)
        self.transcripts.append({
            "gene_idx": gene_idx,
            "seqid": seqid,
            "start": start,
            "end": end,
            "strand": strand,
            "name": attrs.get("Name") or tid,
            "transcript_id": attrs.get("transcript_id") or tid,
            "tags": attrs.get("tag", ""),
            "exons": [],
            "cds": [],
        })
        self._transcript_id_to_idx[tid] = idx
        self.transcript_count += 1
        return idx


def build_annotation_index(gff_path):
    """Read NCBI GFF3 and return an AnnotationIndex."""
    if not os.path.isfile(gff_path):
        return None

    index = AnnotationIndex()
    with open(gff_path, "r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if line.startswith("#") or not line.strip():
                continue
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 9:
                continue
            seqid, ftype = parts[0], parts[2]
            try:
                start, end = int(parts[3]), int(parts[4])
            except ValueError:
                continue
            strand = parts[6]
            strand_code = STRAND_CODES.get(strand, STRAND_CODES["."])
            attrs = _parse_attrs(parts[8])

            if ftype in GENE_TYPES:
                gid = attrs.get("ID") or attrs.get("gene_id")
                if not gid:
                    continue
                gene_idx = index._intern_gene(gid, attrs)
                index.features[seqid].append(
                    (start, end, TYPE_CODES["gene"], strand_code, gene_idx, -1)
                )
            elif ftype in TRANSCRIPT_TYPES:
                tid = attrs.get("ID") or attrs.get("transcript_id")
                parents = [p for p in attrs.get("Parent", "").split(",") if p]
                if not tid or not parents:
                    continue
                for parent in parents:
                    if parent in index._gene_id_to_idx:
                        gene_idx = index._gene_id_to_idx[parent]
                        transcript_idx = index._intern_transcript(
                            tid, attrs, gene_idx, seqid, start, end, strand
                        )
                        index.features[seqid].append(
                            (start, end, TYPE_CODES["mRNA"], strand_code, gene_idx, transcript_idx)
                        )
                        break
            elif ftype in ("exon", "CDS") or ftype in UTR_TYPES:
                parents = [p for p in attrs.get("Parent", "").split(",") if p]
                for parent in parents:
                    if parent not in index._transcript_id_to_idx:
                        continue
                    transcript_idx = index._transcript_id_to_idx[parent]
                    transcript = index.transcripts[transcript_idx]
                    gene_idx = transcript["gene_idx"]
                    if ftype == "exon":
                        transcript["exons"].append((start, end))
                    elif ftype == "CDS":
                        transcript["cds"].append((start, end))
                    type_code = TYPE_CODES.get(ftype, TYPE_CODES["exon"])
                    index.features[seqid].append(
                        (start, end, type_code, strand_code, gene_idx, transcript_idx)
                    )
                    break

    for transcript_idx, transcript in enumerate(index.transcripts):
        gene_idx = transcript["gene_idx"]
        for start, end, ftype in _compute_utrs(transcript):
            index.features[transcript["seqid"]].append(
                (start, end, TYPE_CODES[ftype],
                 STRAND_CODES.get(transcript["strand"], STRAND_CODES["."]),
                 gene_idx, transcript_idx)
            )
        tss = transcript["start"] if transcript["strand"] == "+" else transcript["end"]
        index.tss[transcript["seqid"]].append(
            (tss, transcript_idx, STRAND_CODES.get(transcript["strand"], STRAND_CODES["."]))
        )

    for seqid in index.features:
        index.features[seqid].sort(key=lambda item: (item[0], item[1]))
    return index


def _feature_to_dict(index, feature):
    start, end, type_code, strand_code, gene_idx, transcript_idx = feature
    gene = index.genes[gene_idx] if gene_idx >= 0 else {}
    transcript = index.transcripts[transcript_idx] if transcript_idx >= 0 else {}
    return {
        "start": start,
        "end": end,
        "type": CODE_TYPES.get(type_code, "other"),
        "gene": gene.get("name", ""),
        "locus_tag": gene.get("locus_tag", ""),
        "gene_id": gene.get("gene_id", ""),
        "transcript_id": transcript.get("transcript_id", ""),
        "transcript_name": transcript.get("name", ""),
        "strand": CODE_STRANDS.get(strand_code, ""),
        "mane": _mane_rank(transcript.get("tags", "")),
    }


_FEATURE_PRIORITY = {
    "CDS": 0,
    "exon": 1,
    "five_prime_UTR": 2,
    "three_prime_UTR": 2,
    "mRNA": 3,
    "gene": 3,
}


def annotate_interval(index, chrom, start0, end0):
    """Annotate a 0-based half-open interval, returning a dict."""
    if index is None or start0 >= end0:
        return None
    query_start = start0 + 1
    query_end = end0
    overlaps = [
        _feature_to_dict(index, feature)
        for feature in index.features.get(chrom, [])
        if query_start <= feature[1] and query_end >= feature[0]
    ]
    if not overlaps:
        return {
            "feature": "intergenic", "gene": "", "locus_tag": "",
            "gene_id": "", "transcript_id": "", "transcript_name": "",
            "strand": "", "isoforms": "", "promoter": False,
        }

    has_coding = any(f["type"] in ("CDS", "exon", "five_prime_UTR", "three_prime_UTR")
                     for f in overlaps)
    if has_coding:
        best = min(overlaps, key=lambda f: _FEATURE_PRIORITY.get(f["type"], 9))
    else:
        best = None
        for feature in overlaps:
            if feature["type"] in ("gene", "mRNA"):
                best = feature
                break
        if best is None:
            best = overlaps[0]

    feature_type = best["type"] if has_coding else "intron"
    if feature_type in ("mRNA", "gene"):
        feature_type = "intron"

    seen_iso = set()
    iso_parts = []
    for feature in sorted(overlaps, key=lambda f: _FEATURE_PRIORITY.get(f["type"], 9)):
        tid = feature.get("transcript_id", "")
        if not tid or tid in seen_iso:
            continue
        seen_iso.add(tid)
        label = feature.get("transcript_name") or tid
        if feature.get("mane") == 0:
            label += "(MANE)"
        iso_parts.append(f"{label}({feature['type']})")

    return {
        "feature": feature_type,
        "gene": best.get("gene", ""),
        "locus_tag": best.get("locus_tag", ""),
        "gene_id": best.get("gene_id", ""),
        "transcript_id": best.get("transcript_id", ""),
        "transcript_name": best.get("transcript_name", ""),
        "strand": best.get("strand", ""),
        "isoforms": ",".join(iso_parts[:6]),
        "promoter": False,
    }


def nearest_tss(index, chrom, start0, end0):
    """Return the nearest transcript TSS with a signed distance in bp."""
    if index is None or start0 >= end0:
        return None
    pos = start0 + (end0 - start0) // 2 + 1
    best = None
    for tss, transcript_idx, strand_code in index.tss.get(chrom, []):
        transcript = index.transcripts[transcript_idx]
        gene = index.genes[transcript["gene_idx"]]
        if strand_code == STRAND_CODES["+"]:
            signed = pos - tss
        else:
            signed = tss - pos
        mane = _mane_rank(transcript.get("tags", ""))
        if (best is None or abs(signed) < abs(best["distance"]) or
                (abs(signed) == abs(best["distance"]) and mane < best["mane"])):
            best = {
                "tss": tss, "distance": signed,
                "transcript_id": transcript["transcript_id"],
                "transcript_name": transcript["name"],
                "gene": gene.get("name", ""),
                "strand": CODE_STRANDS.get(strand_code, ""),
                "mane": mane,
            }
    return best


def find_downstream_atg(genome, chrom, start0, end0, strand, window=500):
    """Return the 0-based start of the next ATG in the coding direction."""
    if genome is None or chrom not in genome.keys():
        return None
    chrom_len = len(genome[chrom])
    try:
        if strand in ("+", "plus"):
            segment = str(genome[chrom][end0:min(chrom_len, end0 + window)]).upper()
            pos = segment.find("ATG")
            return end0 + pos if pos != -1 else None
        upstream_start = max(0, start0 - window)
        segment = str(genome[chrom][upstream_start:start0]).upper()
        rc = reverse_complement(segment)
        pos = rc.find("ATG")
        return start0 - pos if pos != -1 else None
    except Exception:
        return None


def format_annotation(ann):
    if not ann:
        return ""
    if ann["feature"] == "intergenic":
        return "intergenic"
    parts = [f"gene={ann['gene'] or '-'}", f"feature={ann['feature']}"]
    if ann.get("locus_tag"):
        parts.append(f"locus={ann['locus_tag']}")
    if ann.get("transcript_name"):
        parts.append(f"transcript={ann['transcript_name']}")
    if ann.get("strand"):
        parts.append(f"strand={ann['strand']}")
    return ";".join(parts)


def format_tss(tss):
    if not tss:
        return ""
    distance = tss["distance"]
    sign = "+" if distance >= 0 else ""
    label = tss["transcript_name"] or tss["transcript_id"]
    if tss.get("mane") == 0:
        label += "(MANE)"
    return f"{label}:{tss['gene'] or '-'}:{sign}{distance}bp"
