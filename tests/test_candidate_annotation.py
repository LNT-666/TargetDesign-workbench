#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the GFF3 annotation index that fills the score-table columns."""

import gzip
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "shared"))

from data.candidate_annotation import (  # noqa: E402
    annotate_interval,
    build_annotation_index,
    format_annotation,
    nearest_tss,
)


GFF_LINES = [
    "##gff-version 3",
    "##sequence-region chr1 1 1000",
    "##sequence-region chr2 1 500",
    "chr1\tRefSeq\tgene\t101\t400\t.\t+\t.\tID=gene-A;gene=AAA;gene_id=1",
    "chr1\tRefSeq\tmRNA\t101\t400\t.\t+\t.\tID=rna-A;Parent=gene-A;transcript_id=NM_1",
    "chr1\tRefSeq\texon\t101\t400\t.\t+\t.\tID=exon-A;Parent=rna-A",
    "chr1\tRefSeq\tCDS\t121\t380\t.\t+\t.\tID=cds-A;Parent=rna-A",
]


class AnnotationIndexTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="candidate_annotation_")
        self.addCleanup(self.tmp.cleanup)
        self.gff = os.path.join(self.tmp.name, "anno.gff3")
        with open(self.gff, "w", encoding="utf-8") as handle:
            handle.write("\n".join(GFF_LINES) + "\n")
        self.index = build_annotation_index(self.gff)

    def test_interval_inside_a_gene_is_annotated(self):
        ann = annotate_interval(self.index, "chr1", 130, 140)
        self.assertEqual(ann["feature"], "CDS")
        self.assertEqual(ann["gene"], "AAA")
        self.assertIn("gene=AAA", format_annotation(ann))
        self.assertIsNotNone(nearest_tss(self.index, "chr1", 130, 140))

    def test_known_sequence_without_features_is_intergenic(self):
        ann = annotate_interval(self.index, "chr2", 10, 20)
        self.assertEqual(ann["feature"], "intergenic")
        self.assertEqual(format_annotation(ann), "intergenic")

    def test_unknown_sequence_id_is_not_labelled_intergenic(self):
        # A custom target FASTA (for example "tyr-exon1") is not a sequence the
        # annotation describes, so the columns must stay blank instead of
        # claiming the interval is intergenic.
        ann = annotate_interval(self.index, "tyr-exon1", 0, 25)
        self.assertIsNone(ann)
        self.assertEqual(format_annotation(ann), "")
        self.assertIsNone(nearest_tss(self.index, "tyr-exon1", 0, 25))

    def test_gzipped_annotation_reads_like_plain_text(self):
        gz_path = os.path.join(self.tmp.name, "anno.gff3.gz")
        with gzip.open(gz_path, "wt", encoding="utf-8") as handle:
            handle.write("\n".join(GFF_LINES) + "\n")
        gz_index = build_annotation_index(gz_path)
        self.assertEqual(gz_index.gene_count, self.index.gene_count)
        self.assertEqual(gz_index.seqids, self.index.seqids)

    def test_missing_annotation_file_returns_none(self):
        self.assertIsNone(
            build_annotation_index(os.path.join(self.tmp.name, "nope.gff3")))


if __name__ == "__main__":
    unittest.main()
