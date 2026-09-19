#!/usr/bin/env python3
# local_extract.py

import re
import os
import sys
from collections import defaultdict

def parse_gtf_attributes(attr_str):
    """Parse GFF3/GTF attributes."""
    attrs = {}
    if not attr_str or attr_str == ".":
        return attrs
    for item in re.split(r'[;\s]+', attr_str):
        if not item:
            continue
        if "=" in item:
            k, v = item.split("=", 1)
            attrs[k.strip()] = v.strip('"')
        elif " " in item:
            k, v = item.split(" ", 1)
            attrs[k.strip()] = v.strip('"')
    return attrs

def get_region_sequence(genome_fasta, annotation_file, identifier, region_type,
                        region_num=None, id_type="gene_name"):
    """Extract region sequence from genome and annotation."""
    from pyfaidx import Fasta
    genome = Fasta(genome_fasta)

    genes = defaultdict(lambda: {
        "mrnas": [],
        "attrs": {},
        "seqid": None,
        "strand": None,
        "start": None,
        "end": None
    })
    mrna_data = {}

    with open(annotation_file, "r") as f:
        for line in f:
            if line.startswith("#"):
                continue
            parts = line.strip().split("\t")
            if len(parts) < 9:
                continue
            seqid, source, feat, start, end, score, strand, phase, attrs_str = parts
            start, end = int(start), int(end)
            attrs = parse_gtf_attributes(attrs_str)

            if feat in ("gene", "pseudogene", "ncRNA_gene", "rRNA_gene", "tRNA_gene"):
                gid = attrs.get("ID") or attrs.get("gene_id")
                if not gid:
                    continue
                genes[gid]["seqid"] = seqid
                genes[gid]["strand"] = strand
                genes[gid]["start"] = start
                genes[gid]["end"] = end
                genes[gid]["attrs"] = {
                    "ID": gid,
                    "gene_id": attrs.get("gene_id", ""),
                    "gene_name": attrs.get("gene_name", "") or attrs.get("Name", "") or attrs.get("gene", ""),
                    "locus_tag": attrs.get("locus_tag", ""),
                }
                if not genes[gid]["attrs"]["gene_name"]:
                    genes[gid]["attrs"]["gene_name"] = gid

            elif feat in ("mRNA", "transcript", "primary_transcript",
                          "C_gene_segment", "V_gene_segment", "D_gene_segment", "J_gene_segment"):
                tid = attrs.get("ID") or attrs.get("transcript_id")
                parents = attrs.get("Parent", "").split(",")
                if tid and parents:
                    tags = []
                    if "tag" in attrs:
                        for t in attrs["tag"].split(","):
                            tags.append(t.strip())
                    for p in parents:
                        if p in genes:
                            mrna_data[tid] = {
                                "gene": p,
                                "seqid": seqid,
                                "strand": strand,
                                "exons": [],
                                "cds": [],
                                "start": start,
                                "end": end,
                                "tags": tags
                            }
                            genes[p]["mrnas"].append(tid)
                            break
            elif feat == "exon":
                parents = attrs.get("Parent", "").split(",")
                for p in parents:
                    if p in mrna_data:
                        mrna_data[p]["exons"].append((start, end))
                        break
            elif feat == "CDS":
                parents = attrs.get("Parent", "").split(",")
                for p in parents:
                    if p in mrna_data:
                        mrna_data[p]["cds"].append((start, end))
                        break

    # Find gene by identifier
    gene_id = None
    if identifier in genes:
        gene_id = identifier
    else:
        for gid, gdata in genes.items():
            attr_value = gdata["attrs"].get(id_type, "")
            if attr_value == identifier:
                gene_id = gid
                break
        if gene_id is None and identifier in mrna_data:
            gene_id = mrna_data[identifier]["gene"]
        if gene_id is None:
            for tid, tdata in mrna_data.items():
                if tid == identifier:
                    gene_id = tdata["gene"]
                    break
        if gene_id is None:
            raise ValueError(f"Identifier '{identifier}' not found (type: '{id_type}').")

    gene_info = genes[gene_id]
    if not gene_info["mrnas"]:
        raise ValueError(f"Gene {identifier} has no transcripts")

    # Select transcript by tag priority
    priority_tags = ["MANE", "RefSeq", "APPRIS P1"]
    selected_tid = None
    for tag in priority_tags:
        for tid in gene_info["mrnas"]:
            if tag in mrna_data[tid].get("tags", []):
                selected_tid = tid
                break
        if selected_tid:
            break
    if selected_tid is None:
        selected_tid = sorted(gene_info["mrnas"],
                              key=lambda t: mrna_data[t]["end"] - mrna_data[t]["start"],
                              reverse=True)[0]

    tid = selected_tid
    mrna = mrna_data[tid]
    seqid = mrna["seqid"]
    strand = mrna["strand"]

    genomic_exons = sorted(mrna["exons"])
    biological_exons = genomic_exons if strand == "+" else genomic_exons[::-1]

    genomic_introns = []
    for i in range(len(genomic_exons) - 1):
        s = genomic_exons[i][1] + 1
        e = genomic_exons[i + 1][0] - 1
        if s <= e:
            genomic_introns.append((s, e))
    biological_introns = genomic_introns if strand == "+" else genomic_introns[::-1]

    coords = []
    if region_type == "Coding region":
        coords = [(gene_info["start"], gene_info["end"])]
    elif region_type == "Exonic sequence":
        coords = genomic_exons
    elif region_type == "Specific exon":
        try:
            n = int(region_num)
            if 1 <= n <= len(biological_exons):
                coords = [biological_exons[n - 1]]
        except (ValueError, TypeError, IndexError):
            coords = []
    elif region_type == "Introns":
        coords = genomic_introns
    elif region_type == "Specific intron":
        try:
            n = int(region_num)
            if 1 <= n <= len(biological_introns):
                coords = [biological_introns[n - 1]]
        except (ValueError, TypeError, IndexError):
            coords = []
    elif region_type == "5' UTR":
        if mrna["cds"]:
            cds_sorted = sorted(mrna["cds"])
            if strand == "+":
                first_exon_start = genomic_exons[0][0]
                first_cds_start = cds_sorted[0][0]
                if first_exon_start < first_cds_start:
                    coords = [(first_exon_start, first_cds_start - 1)]
            else:
                last_exon_end = genomic_exons[-1][1]
                last_cds_end = cds_sorted[-1][1]
                if last_cds_end < last_exon_end:
                    coords = [(last_cds_end + 1, last_exon_end)]
        else:
            coords = []
    elif region_type == "3' UTR":
        if mrna["cds"]:
            cds_sorted = sorted(mrna["cds"])
            if strand == "+":
                last_exon_end = genomic_exons[-1][1]
                last_cds_end = cds_sorted[-1][1]
                if last_cds_end < last_exon_end:
                    coords = [(last_cds_end + 1, last_exon_end)]
            else:
                first_exon_start = genomic_exons[0][0]
                first_cds_start = cds_sorted[0][0]
                if first_exon_start < first_cds_start:
                    coords = [(first_exon_start, first_cds_start - 1)]
        else:
            coords = []
    else:
        raise ValueError(f"Unknown region type: {region_type}")

    if not coords:
        raise ValueError(f"Region {region_type} has no valid coordinates")

    seq_parts = []
    for s, e in coords:
        if s > e:
            continue
        seq_parts.append(str(genome[seqid][s-1:e]))
    if strand == "-":
        full_seq = "".join(seq_parts)
        if len(coords) == 1:
            seq = str(genome[seqid][coords[0][0]-1:coords[0][1]].reverse.complement)
        else:
            seq = full_seq[::-1].translate(str.maketrans("ATCG", "TAGC"))
    else:
        seq = "".join(seq_parts)

    gene_name = gene_info["attrs"].get("gene_name", identifier)
    if region_type == "Coding region":
        region_desc = "gene"
    elif region_type == "Exonic sequence":
        region_desc = "exons"
    elif region_type == "Specific exon":
        region_desc = f"exon{region_num}"
    elif region_type == "Introns":
        region_desc = "introns"
    elif region_type == "Specific intron":
        region_desc = f"intron{region_num}"
    elif region_type == "5' UTR":
        region_desc = "5utr"
    elif region_type == "3' UTR":
        region_desc = "3utr"
    else:
        region_desc = region_type

    header = f">{gene_name}-{region_desc}"
    return header, seq


def extract_full_transcript_sequences(genome_fasta, annotation_file, identifier, id_type="gene_name"):
    """Extract full transcript sequences."""
    header, seq = get_region_sequence(genome_fasta, annotation_file, identifier, "Coding region", id_type=id_type)
    return [(header, seq)]


def gbff_to_fasta_gtf(gbff_path, prefix):
    """Convert GBFF to FASTA/GTF (not implemented)."""
    raise NotImplementedError("GBFF conversion requires additional tools.")
