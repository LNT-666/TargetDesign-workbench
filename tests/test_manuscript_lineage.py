# -*- coding: utf-8 -*-
"""The seal must reject anything but the lineage-correct head manuscript."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

try:
    import docx
except ImportError:  # optional test dependency; skip instead of failing discovery
    docx = None

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import manuscript_lineage as lineage  # noqa: E402

BASE = [
    "Genome editing rests on effectors that differ in size and target nucleic acid, "
    "and the workbench keeps those differences visible to the user at every step.",
    "A design request binds one effector, one layout and one scoring policy, so the "
    "same candidate can be compared across engines without rewriting the pipeline.",
    "Off-target search decides whether a candidate is acceptable, and the result "
    "tables keep the evidence together with the score that was actually used.",
]
NEW = [
    "The manuscript line is sealed so that only the reviewed head can reach a "
    "release bundle or a journal upload staging tree.",
]


def write_docx(path, paragraphs):
    path.parent.mkdir(parents=True, exist_ok=True)
    document = docx.Document()
    for text in paragraphs:
        document.add_paragraph(text)
    document.save(str(path))


def build_tree(root):
    submission = root / "docs" / "submission"
    write_docx(submission / "branch_base" / "SUBMISSION_SHORT_r9_markup_view.docx",
               BASE)
    write_docx(submission / "SUBMISSION_SHORT_v1.docx", BASE + NEW)
    (submission / "SUBMISSION_SHORT_v1.md").write_text(
        "\n\n".join(BASE + NEW) + "\n", encoding="utf-8")
    (submission / "SUPPLEMENTARY_v1.md").write_text("supplementary\n", encoding="utf-8")
    (submission / "SUPPLEMENTARY_v1.pdf").write_bytes(b"%PDF-1.4\n")


@unittest.skipUnless(docx is not None,
                     "python-docx is not installed (pip install python-docx)")
class LineageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        build_tree(self.root)
        self.submission = self.root / "docs" / "submission"
        self.head_docx = self.submission / "SUBMISSION_SHORT_v1.docx"
        self.head_md = self.submission / "SUBMISSION_SHORT_v1.md"

    def tearDown(self):
        self.tmp.cleanup()

    def test_seal_then_check_passes(self):
        lineage.seal(self.root, "fixture")
        self.assertEqual(lineage.check(self.root), [])

    def test_missing_seal_blocks(self):
        errors = lineage.check(self.root)
        self.assertTrue(errors)
        self.assertIn("seal", errors[0])

    def test_edited_file_after_seal_blocks(self):
        lineage.seal(self.root, "fixture")
        with self.head_md.open("a", encoding="utf-8") as handle:
            handle.write("\nOne more sentence that is long enough to count as a block, "
                         "but the docx was never rebuilt after this edit.\n")
        errors = lineage.check(self.root)
        self.assertTrue(any("changed after sealing" in e for e in errors), errors)

    def test_stray_docx_blocks(self):
        lineage.seal(self.root, "fixture")
        write_docx(self.submission / "MS-V2.docx", BASE)
        errors = lineage.check(self.root)
        self.assertTrue(any("exactly one manuscript docx" in e for e in errors), errors)

    def test_old_docx_blocks(self):
        lineage.seal(self.root, "fixture")
        future = self.head_md.stat().st_mtime + 60
        os.utime(self.head_md, (future, future))
        errors = lineage.check(self.root)
        self.assertTrue(any("older than md" in e for e in errors), errors)

    def test_wrong_lineage_blocks(self):
        unrelated = [
            "A completely unrelated manuscript about a different subject, long "
            "enough to be considered a paragraph in this check.",
        ]
        write_docx(self.head_docx, unrelated)
        with self.assertRaises(SystemExit) as caught:
            lineage.seal(self.root, "wrong")
        self.assertIn("lineage", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
