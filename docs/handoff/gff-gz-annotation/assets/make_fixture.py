import gzip, io, os

FIXTURE = r"""##gff-version 3
#!gff-spec-version 1.21
NC_000001.11	RefSeq	gene	1001	2000	.	+	.	ID=gene-A;Name=A;gene=AAA
NC_000001.11	RefSeq	mRNA	1001	2000	.	+	.	ID=rna-A;Parent=gene-A
NC_000001.11	RefSeq	exon	1001	1200	.	+	.	ID=exon-A1;Parent=rna-A
NC_000001.11	RefSeq	exon	1501	2000	.	+	.	ID=exon-A2;Parent=rna-A
NC_000001.11	RefSeq	CDS	1101	1200	.	+	0	ID=cds-A;Parent=rna-A
NC_000001.11	RefSeq	CDS	1501	1800	.	+	0	ID=cds-A;Parent=rna-A
NC_000001.11	RefSeq	gene	3001	4000	.	-	.	ID=gene-B;Name=B;gene=BBB
NC_000001.11	RefSeq	mRNA	3001	4000	.	-	.	ID=rna-B;Parent=gene-B
NC_000001.11	RefSeq	exon	3001	3400	.	-	.	ID=exon-B1;Parent=rna-B
NC_000001.11	RefSeq	exon	3801	4000	.	-	.	ID=exon-B2;Parent=rna-B
NC_000001.11	RefSeq	CDS	3101	3400	.	-	0	ID=cds-B;Parent=rna-B
NC_000001.11	RefSeq	CDS	3801	3900	.	-	0	ID=cds-B;Parent=rna-B
"""
base = os.path.join(os.path.dirname(os.path.abspath(__file__)))
plain = os.path.join(base, "mini.gff")
gz = os.path.join(base, "mini.gff.gz")
with io.open(plain, "w", encoding="ascii", newline="\n") as f:
    f.write(FIXTURE)
with gzip.open(gz, "wb") as f:
    f.write(FIXTURE.encode("ascii"))
with open(gz, "rb") as f:
    print("gz magic bytes:", f.read(2).hex())
print("plain:", plain, os.path.getsize(plain))
print("gz   :", gz, os.path.getsize(gz))