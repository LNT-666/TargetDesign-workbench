#!/usr/bin/env python3
# download_data.py

import os
import sys
import argparse
import requests
import gzip
import shutil
import json

DOWNLOAD_URLS = {
    "human": {
        "fasta": "https://ftp.ncbi.nlm.nih.gov/genomes/all/GCF/000/001/405/GCF_000001405.40_GRCh38.p14/GCF_000001405.40_GRCh38.p14_genomic.fna.gz",
        "gtf": "https://ftp.ncbi.nlm.nih.gov/genomes/all/GCF/000/001/405/GCF_000001405.40_GRCh38.p14/GCF_000001405.40_GRCh38.p14_genomic.gff.gz"
    },
    "yeast": {
        "fasta": "https://ftp.ncbi.nlm.nih.gov/genomes/all/GCF/000/146/045/GCF_000146045.2_R64/GCF_000146045.2_R64_genomic.fna.gz",
        "gtf": "https://ftp.ncbi.nlm.nih.gov/genomes/all/GCF/000/146/045/GCF_000146045.2_R64/GCF_000146045.2_R64_genomic.gff.gz"
    },
    "mouse": {
        "fasta": "https://ftp.ncbi.nlm.nih.gov/genomes/all/GCF/000/001/635/GCF_000001635.27_GRCm39/GCF_000001635.27_GRCm39_genomic.fna.gz",
        "gtf": "https://ftp.ncbi.nlm.nih.gov/genomes/all/GCF/000/001/635/GCF_000001635.27_GRCm39/GCF_000001635.27_GRCm39_genomic.gff.gz"
    },
    "zebrafish": {
        "fasta": "https://ftp.ncbi.nlm.nih.gov/genomes/all/GCF/052/040/795/GCF_052040795.1_GRCz12ab/GCF_052040795.1_GRCz12ab_genomic.fna.gz",
        "gtf": "https://ftp.ncbi.nlm.nih.gov/genomes/all/GCF/052/040/795/GCF_052040795.1_GRCz12ab/GCF_052040795.1_GRCz12ab_genomic.gff.gz"
    },
    "fly": {
        "fasta": "https://ftp.ncbi.nlm.nih.gov/genomes/all/GCF/000/001/215/GCF_000001215.4_Release_6_plus_ISO1_MT/GCF_000001215.4_Release_6_plus_ISO1_MT_genomic.fna.gz",
        "gtf": "https://ftp.ncbi.nlm.nih.gov/genomes/all/GCF/000/001/215/GCF_000001215.4_Release_6_plus_ISO1_MT/GCF_000001215.4_Release_6_plus_ISO1_MT_genomic.gff.gz"
    },
    "worm": {
        "fasta": "https://ftp.ncbi.nlm.nih.gov/genomes/all/GCF/000/002/985/GCF_000002985.6_WBcel235/GCF_000002985.6_WBcel235_genomic.fna.gz",
        "gtf": "https://ftp.ncbi.nlm.nih.gov/genomes/all/GCF/000/002/985/GCF_000002985.6_WBcel235/GCF_000002985.6_WBcel235_genomic.gff.gz"
    },
}

def download_file_with_progress(url, dest_path, label, chunk_size=8192):
    try:
        response = requests.get(url, stream=True, timeout=300)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Download failed: {e}", flush=True)
        sys.exit(7)
    total_size = int(response.headers.get("content-length", 0))
    downloaded = 0
    last_percent = -1
    with open(dest_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=chunk_size):
            if chunk:
                f.write(chunk)
                downloaded += len(chunk)
                if total_size > 0:
                    percent = int(100 * downloaded / total_size)
                    if percent > last_percent:
                        last_percent = percent
                        print(f"PROGRESS: {label} {percent}", flush=True)
                else:
                    if downloaded % (10 * 1024 * 1024) < chunk_size:
                        print(f"PROGRESS: {label} {downloaded // (1024*1024)}MB", flush=True)
    return dest_path

def gunzip_file(gz_path, out_path, label):
    print(f"PROGRESS: {label} 0", flush=True)
    with gzip.open(gz_path, "rb") as f_in, open(out_path, "wb") as f_out:
        shutil.copyfileobj(f_in, f_out)
    print(f"PROGRESS: {label} 100", flush=True)
    os.remove(gz_path)

def download_and_extract(url, output_dir, base_name, label):
    local_file = os.path.join(output_dir, base_name)
    if os.path.exists(local_file):
        print(f"File exists, skipping: {local_file}")
        return local_file
    if url.endswith(".gz"):
        gz_file = local_file + ".gz"
        print(f"Downloading {label} ...")
        download_file_with_progress(url, gz_file, label)
        print(f"Decompressing {label} ...")
        gunzip_file(gz_file, local_file, label)
        print(f"Decompressed: {local_file}")
        return local_file
    else:
        print(f"Downloading {label} ...")
        download_file_with_progress(url, local_file, label)
        print(f"Downloaded: {local_file}")
        return local_file

def download_data(species, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    if species not in DOWNLOAD_URLS:
        raise ValueError(f"Species not configured: {species}")
    urls = DOWNLOAD_URLS[species]
    fasta_url = urls.get("fasta")
    gtf_url = urls.get("gtf")
    if not fasta_url or not gtf_url:
        raise ValueError(f"Incomplete URLs for: {species}")
    fasta_name = os.path.basename(fasta_url).replace(".gz", "") or f"{species}_genome.fa"
    gtf_name = os.path.basename(gtf_url).replace(".gz", "") or f"{species}_annotations.gtf"
    print(f"Downloading {species} data...")
    fasta_file = download_and_extract(fasta_url, output_dir, fasta_name, "FASTA")
    gtf_file = download_and_extract(gtf_url, output_dir, gtf_name, "GTF")
    return fasta_file, gtf_file

def main():
    parser = argparse.ArgumentParser(description="Download genome and annotation from URL")
    parser.add_argument("--species", required=True, help="Species name")
    parser.add_argument("--output", required=True, help="Output directory")
    args = parser.parse_args()
    try:
        genome_file, annotation_file = download_data(args.species, args.output)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(7)
    info = {"genome_fasta": genome_file, "gtf": annotation_file}
    with open(os.path.join(args.output, "download_info.json"), "w") as f:
        json.dump(info, f, indent=2)
    print("Download complete.")

if __name__ == "__main__":
    main()
