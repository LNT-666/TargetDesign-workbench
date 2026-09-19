import os
import sys
import tempfile
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHARED = os.path.join(ROOT, "shared")
sys.path.insert(0, SHARED)

from output.candidate_export import export_selected  # noqa: E402


ROWS = [
    {
        "query_id": "uniq_0",
        "query_seq": "AATTTTAT",
        "seq_id": "chr1",
        "strand": "+",
        "start": "11",
        "end": "19",
    },
    {
        "query_id": "uniq_1",
        "query_seq": "GGGGCCCC",
        "seq_id": "chr2",
        "strand": "-",
        "start": "21",
        "end": "29",
    },
]


class CandidateExportTests(unittest.TestCase):
    def test_export_csv_and_tsv(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = os.path.join(tmp, "out.csv")
            tsv_path = os.path.join(tmp, "out.tsv")
            self.assertEqual(export_selected(ROWS, csv_path, "csv"), 2)
            self.assertEqual(export_selected(ROWS, tsv_path, "tsv"), 2)
            self.assertTrue(os.path.isfile(csv_path))
            self.assertTrue(os.path.isfile(tsv_path))

    def test_export_fasta(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "out.fa")
            self.assertEqual(export_selected(ROWS, path, "fasta"), 2)
            with open(path, encoding="utf-8") as handle:
                content = handle.read()
            self.assertIn(">uniq_0", content)
            self.assertIn("AATTTTAT", content)

    def test_export_bed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "out.bed")
            self.assertEqual(export_selected(ROWS, path, "bed"), 2)
            with open(path, encoding="utf-8") as handle:
                content = handle.read()
            self.assertIn("chr1\t10\t19\tuniq_0\t0\t+", content)
            self.assertIn("chr2\t20\t29\tuniq_1\t0\t-", content)

    def test_export_xlsx(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "out.xlsx")
            self.assertEqual(export_selected(ROWS, path, "xlsx"), 2)
            self.assertTrue(os.path.isfile(path))

    def test_export_unique_guides(self):
        rows = ROWS + [
            {
                "query_id": "uniq_0_dup",
                "query_seq": "AATTTTAT",
                "seq_id": "chr1",
                "strand": "+",
                "start": "31",
                "end": "39",
            }
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "unique.tsv")
            self.assertEqual(export_selected(rows, path, "unique_guides"), 2)
            with open(path, encoding="utf-8") as handle:
                content = handle.read()
            self.assertIn("occurrence_count", content)

    def test_export_library_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "library.tsv")
            self.assertEqual(export_selected(ROWS, path, "library"), 2)
            with open(path, encoding="utf-8") as handle:
                content = handle.read()
            self.assertIn("qid\tsequence\tpositions", content)
            self.assertIn("uniq_0", content)
            self.assertIn("AATTTTAT", content)


if __name__ == "__main__":
    unittest.main()
