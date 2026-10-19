import os
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class CliHelpTests(unittest.TestCase):
    def run_script(self, relative_path, *args):
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        return subprocess.run(
            [sys.executable, str(ROOT / relative_path), *args],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            check=False,
        )

    def test_extract_help_lists_positional_arguments(self):
        result = self.run_script("basic/extract.py", "--help")
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0, output)
        for token in (
            "<input.fasta>",
            "<motif>",
            "<flanking sequence length>",
            "<side>",
            "<output.tsv>",
        ):
            self.assertIn(token, output)

    def test_complex_extract_help_lists_positional_arguments(self):
        result = self.run_script(
            "Target_xbp_Target/extract_complex_queries.py", "--help"
        )
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0, output)
        for token in (
            "<input.fasta>",
            "<left_motif>",
            "<right_motif>",
            "<min_gap>",
            "<max_gap>",
            "<left_side>",
            "<left_len>",
            "<right_side>",
            "<right_len>",
            "<output.tsv>",
        ):
            self.assertIn(token, output)

    def test_short_help_alias(self):
        for relative_path in (
            "basic/extract.py",
            "Target_xbp_Target/extract_complex_queries.py",
        ):
            with self.subTest(relative_path=relative_path):
                result = self.run_script(relative_path, "-h")
                output = result.stdout + result.stderr
                self.assertEqual(result.returncode, 0, output)
                self.assertIn("Usage:", output)

    def test_extract_rejects_unknown_option(self):
        result = self.run_script(
            "basic/extract.py", "--bogus", "TTAT", "10", "upstream", "out.tsv"
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("unknown option: --bogus", result.stderr)

    def test_extract_rejects_missing_positionals(self):
        result = self.run_script("basic/extract.py")
        self.assertEqual(result.returncode, 1)
        self.assertIn("expected 5 positional arguments", result.stderr)

    def test_complex_extract_rejects_unknown_option(self):
        result = self.run_script(
            "Target_xbp_Target/extract_complex_queries.py",
            "--bogus",
            "TTAT",
            "CCGG",
            "5",
            "20",
            "upstream",
            "10",
            "downstream",
            "15",
            "out.tsv",
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("unknown option: --bogus", result.stderr)

    def test_complex_extract_rejects_missing_positionals(self):
        result = self.run_script("Target_xbp_Target/extract_complex_queries.py")
        self.assertEqual(result.returncode, 1)
        self.assertIn("expected 10 positional arguments", result.stderr)


if __name__ == "__main__":
    unittest.main()
