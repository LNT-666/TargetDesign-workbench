import csv
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHARED = os.path.join(ROOT, "shared")
GAP_DIR = os.path.join(ROOT, "Target_xbp_Target")
Y_DIR = os.path.join(ROOT, "Target_xbp_Y_zbp_Target")
sys.path.insert(0, SHARED)
sys.path.insert(0, GAP_DIR)


def _has_runtime_deps():
    return all(
        importlib.util.find_spec(name) is not None
        for name in ("numpy", "Bio", "pyfaidx")
    )


HAS_RUNTIME_DEPS = _has_runtime_deps()


def _has_blast():
    return all(shutil.which(name) is not None
               for name in ("blastn", "makeblastdb"))


HAS_BLAST = _has_blast()


def _write_fasta(path, seq, chrom="chr1"):
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(">%s\n%s\n" % (chrom, seq))


def _run(cmd, env=None):
    merged_env = dict(os.environ)
    if env:
        merged_env.update(env)
    proc = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=merged_env,
    )
    if proc.returncode != 0:
        raise AssertionError(
            "command failed (%s):\n%s" % (" ".join(cmd), proc.stdout)
        )
    return proc.stdout


def _rows(path):
    with open(path, encoding="utf-8") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def _write_pair_policy(tmp):
    path = os.path.join(tmp, "pair_rank_policy.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({
            "e_high": 0.8,
            "e_min": 0.5,
            "e_fail": 0.2,
            "delta_default": 0.05,
            "b_low": 0.4,
            "b_high": 0.8,
            "m_low": 0.2,
            "m_high": 0.45,
            "h_risk": 0.7,
            "h_max": 1,
        }, handle)
    return path


class SplitPamSmokeTests(unittest.TestCase):
    def test_flank_interval_and_get_flank_geometry(self):
        from extract_complex_queries import flank_interval, get_flank

        seq = "ABCDEFGHIJKLMNOPQRSTUVWXYZ" * 4
        self.assertEqual(flank_interval(len(seq), 50, 4, "upstream", 10, "plus"),
                         (40, 50))
        self.assertEqual(flank_interval(len(seq), 50, 4, "downstream", 10, "plus"),
                         (54, 64))
        self.assertEqual(flank_interval(len(seq), 50, 4, "upstream", 10, "minus"),
                         (54, 64))
        self.assertEqual(flank_interval(len(seq), 50, 4, "downstream", 10, "minus"),
                         (40, 50))
        self.assertEqual(get_flank(seq, 50, 4, "upstream", 10, "plus"),
                         seq[40:50])
        self.assertEqual(get_flank(seq, 50, 4, "downstream", 10, "plus"),
                         seq[54:64])

    @unittest.skipUnless(HAS_RUNTIME_DEPS, "requires numpy/biopython/pyfaidx")
    def test_pattern_a_split_pam_end_to_end(self):
        tmp = tempfile.mkdtemp()
        g1 = "ACGTCGATCGTGCATGTCGA"
        g2 = "TAGCTAGCATGTCGATACGA"
        genome = "A" * 40 + g1 + "TGG" + "A" * 15 + "TTTA" + g2 + "A" * 40
        left_start = 40
        right_start = 82
        genome_fa = os.path.join(tmp, "genome.fa")
        _write_fasta(genome_fa, genome)

        query_tsv = os.path.join(tmp, "complex_queries.tsv")
        _run([
            sys.executable,
            os.path.join(GAP_DIR, "extract_complex_queries.py"),
            genome_fa, "TGG", "TTTA", "15", "15",
            "upstream", "20", "downstream", "20", query_tsv,
        ])
        qrows = _rows(query_tsv)
        self.assertEqual(len(qrows), 1)
        self.assertEqual(qrows[0]["left_flank_seq"], g1)
        self.assertEqual(qrows[0]["right_flank_seq"], g2)
        self.assertEqual(int(qrows[0]["left_target_start"]), left_start)
        self.assertEqual(int(qrows[0]["right_target_start"]), right_start)

        positive = os.path.join(tmp, "positive")
        os.makedirs(positive)
        policy_path = _write_pair_policy(tmp)
        _run([
            sys.executable,
            os.path.join(GAP_DIR, "analyze_complex_scores.py"),
            query_tsv, "", genome_fa, positive,
            "--engine", "exact", "--max-mismatch", "0", "--seed-len", "12",
            "--left-pam-motif", "TGG", "--left-pam-side", "3prime",
            "--left-require-pam",
            "--right-pam-motif", "TTTA", "--right-pam-side", "5prime",
            "--right-require-pam",
            "--nuclease", "cas9", "--left-nuclease", "cas9",
            "--right-nuclease", "cas9",
            "--on-target-model", "cropsr", "--off-target-model", "cfd",
            "--left-on-target-model", "cropsr",
            "--right-on-target-model", "cropsr",
            "--left-off-target-model", "cfd",
            "--right-off-target-model", "cfd",
            "--pair-rank-policy", policy_path,
            "--mode", "free", "--preset", "custom",
            "--gc-min", "0", "--gc-max", "100", "--self-comp-max", "30",
        ])
        top = _rows(os.path.join(positive, "top_offtargets.tsv"))
        left_hit = next(h for h in top if h["qid"].startswith("left_flank_"))
        right_hit = next(h for h in top if h["qid"].startswith("right_flank_"))
        self.assertEqual(int(left_hit["start"]), left_start)
        self.assertEqual(int(left_hit["mismatch"]), 0)
        self.assertEqual(int(right_hit["start"]), right_start)
        self.assertEqual(int(right_hit["mismatch"]), 0)
        scored_path = os.path.join(positive, "query_scores_sorted.tsv")
        with open(scored_path, encoding="utf-8") as handle:
            scored_header = next(csv.reader(handle, delimiter="\t"))
        self.assertIn("left_mm0", scored_header)
        self.assertIn("right_mm0", scored_header)
        self.assertNotIn("left_mm1", scored_header)
        self.assertNotIn("right_mm1", scored_header)

        negative = os.path.join(tmp, "negative")
        os.makedirs(negative)
        policy_path = _write_pair_policy(tmp)
        _run([
            sys.executable,
            os.path.join(GAP_DIR, "analyze_complex_scores.py"),
            query_tsv, "", genome_fa, negative,
            "--engine", "exact", "--max-mismatch", "0", "--seed-len", "12",
            "--left-pam-motif", "TTTA", "--left-pam-side", "5prime",
            "--left-require-pam",
            "--right-pam-motif", "TGG", "--right-pam-side", "3prime",
            "--right-require-pam",
            "--nuclease", "cas9", "--left-nuclease", "cas9",
            "--right-nuclease", "cas9",
            "--on-target-model", "cropsr", "--off-target-model", "cfd",
            "--left-on-target-model", "cropsr",
            "--right-on-target-model", "cropsr",
            "--left-off-target-model", "cfd",
            "--right-off-target-model", "cfd",
            "--pair-rank-policy", policy_path,
            "--mode", "free", "--preset", "custom",
            "--gc-min", "0", "--gc-max", "100", "--self-comp-max", "30",
        ])
        self.assertEqual(_rows(os.path.join(negative, "top_offtargets.tsv")), [])

    @unittest.skipUnless(HAS_RUNTIME_DEPS, "requires numpy/biopython/pyfaidx")
    def test_y_zbp_split_pam_end_to_end(self):
        tmp = tempfile.mkdtemp()
        g1 = "ACGTCGATCGTGCATGTCGA"
        g2 = "TAGCTAGCATGTCGATACGA"
        genome = ("A" * 40 + g1 + "TGG" + "A" * 5 + "GGTACC"
                  + "A" * 5 + "TTTA" + g2 + "A" * 40)
        left_start = 40
        right_start = 83
        genome_fa = os.path.join(tmp, "genome.fa")
        _write_fasta(genome_fa, genome)

        outdir = os.path.join(tmp, "yout")
        _run([
            sys.executable,
            os.path.join(Y_DIR, "extract_motifs.py"),
            genome_fa, "GGTACC", "20", "20",
            "TGG", "20", "upstream", "TTTA", "20", "downstream",
            "--min_left", "0", "--min_right", "0", "--outdir", outdir,
        ])
        occ_dir = os.path.join(outdir, "occurrence")
        self.assertTrue(os.path.isfile(os.path.join(occ_dir, "occurrence_info.tsv")))

        positive = os.path.join(tmp, "positive.tsv")
        _run([
            sys.executable,
            os.path.join(Y_DIR, "blast_combined.py"),
            "--input_dir", occ_dir,
            "--genome", genome_fa,
            "--target-fasta", genome_fa,
            "-o", positive,
            "--engine", "exact", "--max-mismatch", "0", "--seed-len", "12",
            "--left-pam-motif", "TGG", "--left-pam-side", "3prime",
            "--left-require-pam",
            "--right-pam-motif", "TTTA", "--right-pam-side", "5prime",
            "--right-require-pam",
            "--nuclease", "cas9", "--left-nuclease", "cas9",
            "--right-nuclease", "cas9",
            "--on-target-model", "cropsr", "--off-target-model", "cfd",
            "--left-on-target-model", "cropsr",
            "--right-on-target-model", "cropsr",
            "--left-off-target-model", "cfd",
            "--right-off-target-model", "cfd",
            "--mode", "free", "--preset", "custom",
            "--gc-min", "0", "--gc-max", "100", "--self-comp-max", "30",
        ])
        top = _rows(os.path.join(tmp, "top_offtargets.tsv"))
        left_hit = next(h for h in top if h["qid"].startswith("left_"))
        right_hit = next(h for h in top if h["qid"].startswith("right_"))
        self.assertEqual(int(left_hit["start"]), left_start)
        self.assertEqual(int(left_hit["mismatch"]), 0)
        self.assertEqual(int(right_hit["start"]), right_start)
        self.assertEqual(int(right_hit["mismatch"]), 0)
        with open(positive, encoding="utf-8") as handle:
            scored_header = next(csv.reader(handle, delimiter="\t"))
        self.assertIn("MM0", scored_header)
        self.assertNotIn("MM1", scored_header)
        policy_path = _write_pair_policy(tmp)
        sorted_path = os.path.join(tmp, "positive.sorted.tsv")
        _run([
            sys.executable,
            os.path.join(Y_DIR, "sort_by_distance.py"),
            positive,
            sorted_path,
            "--left-min-distance", "0",
            "--left-max-distance", "20",
            "--right-min-distance", "0",
            "--right-max-distance", "20",
            "--left-nuclease", "cas9",
            "--right-nuclease", "cas9",
            "--pair-rank-policy", policy_path,
        ])
        sorted_rows = _rows(sorted_path)
        self.assertEqual(len(sorted_rows), 2)
        self.assertEqual(
            {row["pair_rank_status"] for row in sorted_rows},
            {"pass"},
        )
        self.assertNotIn("combined_score", sorted_rows[0])

        negative = os.path.join(tmp, "negative.tsv")
        _run([
            sys.executable,
            os.path.join(Y_DIR, "blast_combined.py"),
            "--input_dir", occ_dir,
            "--genome", genome_fa,
            "--target-fasta", genome_fa,
            "-o", negative,
            "--engine", "exact", "--max-mismatch", "0", "--seed-len", "12",
            "--left-pam-motif", "TTTA", "--left-pam-side", "5prime",
            "--left-require-pam",
            "--right-pam-motif", "TGG", "--right-pam-side", "3prime",
            "--right-require-pam",
            "--nuclease", "cas9", "--left-nuclease", "cas9",
            "--right-nuclease", "cas9",
            "--on-target-model", "cropsr", "--off-target-model", "cfd",
            "--left-on-target-model", "cropsr",
            "--right-on-target-model", "cropsr",
            "--left-off-target-model", "cfd",
            "--right-off-target-model", "cfd",
            "--mode", "free", "--preset", "custom",
            "--gc-min", "0", "--gc-max", "100", "--self-comp-max", "30",
        ])
        self.assertEqual(_rows(os.path.join(tmp, "top_offtargets.tsv")), [])

    def _gap_analyze_command(self, query_tsv, genome_fa, outdir, engine,
                             tmp):
        return [
            sys.executable,
            os.path.join(GAP_DIR, "analyze_complex_scores.py"),
            query_tsv, "", genome_fa, outdir,
            "--blastdb", "",
            "--engine", engine, "--max-mismatch", "0", "--seed-len", "12",
            "--left-pam-motif", "TGG", "--left-pam-side", "3prime",
            "--left-require-pam",
            "--right-pam-motif", "TTTA", "--right-pam-side", "5prime",
            "--right-require-pam",
            "--nuclease", "cas9", "--left-nuclease", "cas9",
            "--right-nuclease", "cas9",
            "--on-target-model", "cropsr", "--off-target-model", "cfd",
            "--left-on-target-model", "cropsr",
            "--right-on-target-model", "cropsr",
            "--left-off-target-model", "cfd",
            "--right-off-target-model", "cfd",
            "--pair-rank-policy", _write_pair_policy(tmp),
            "--mode", "free", "--preset", "custom",
            "--gc-min", "0", "--gc-max", "100", "--self-comp-max", "30",
        ]

    LEFT_FLANK = "ACGTCGATCGTGCATGTCGA"
    RIGHT_FLANK = "TAGCTAGCATGTCGATACGA"

    def _fixture_genome(self, y_layout=False):
        if y_layout:
            return ("A" * 40 + self.LEFT_FLANK + "TGG" + "A" * 5
                    + "GGTACC" + "A" * 5 + "TTTA" + self.RIGHT_FLANK
                    + "A" * 40)
        return ("A" * 40 + self.LEFT_FLANK + "TGG" + "A" * 15
                + "TTTA" + self.RIGHT_FLANK + "A" * 40)

    def _write_gap_fixture(self, tmp):
        genome_fa = os.path.join(tmp, "genome.fa")
        _write_fasta(genome_fa, self._fixture_genome())
        query_tsv = os.path.join(tmp, "complex_queries.tsv")
        _run([
            sys.executable,
            os.path.join(GAP_DIR, "extract_complex_queries.py"),
            genome_fa, "TGG", "TTTA", "15", "15",
            "upstream", "20", "downstream", "20", query_tsv,
        ])
        return genome_fa, query_tsv

    @unittest.skipUnless(HAS_RUNTIME_DEPS, "requires numpy/biopython/pyfaidx")
    @unittest.skipUnless(HAS_BLAST, "requires blastn/makeblastdb")
    def test_gap_script_non_exact_engine_writes_top_offtargets(self):
        """A non-exact engine returns hit dicts, not legacy tuple records.

        Regression for the post-processing branch that unpacked hits as
        tuples: it raised ``KeyError: 0`` as soon as BLAST found a hit.
        """
        tmp = tempfile.mkdtemp()
        genome_fa, query_tsv = self._write_gap_fixture(tmp)
        outdir = os.path.join(tmp, "blastout")
        os.makedirs(outdir)
        _run(self._gap_analyze_command(
            query_tsv, genome_fa, outdir, "blast", tmp))
        top_path = os.path.join(outdir, "top_offtargets.tsv")
        self.assertTrue(os.path.isfile(top_path))
        top = _rows(top_path)
        left_hit = next(row for row in top
                        if row["qid"].startswith("left_flank_"))
        right_hit = next(row for row in top
                         if row["qid"].startswith("right_flank_"))
        self.assertEqual(int(left_hit["start"]), 40)
        self.assertEqual(int(right_hit["start"]), 82)

    @unittest.skipUnless(HAS_RUNTIME_DEPS, "requires numpy/biopython/pyfaidx")
    @unittest.skipUnless(HAS_BLAST, "requires blastn/makeblastdb")
    def test_auto_engine_runs_the_chain_in_both_target_scripts(self):
        """auto must reach the runtime chain instead of folding to one engine."""
        env = {"CRISPR_OFFTARGET_ENGINE_FALLBACK": "allow"}
        tmp = tempfile.mkdtemp()
        genome_fa, query_tsv = self._write_gap_fixture(tmp)

        gap_out = os.path.join(tmp, "gap_auto")
        os.makedirs(gap_out)
        gap_log = _run(self._gap_analyze_command(
            query_tsv, genome_fa, gap_out, "auto", tmp), env=env)
        self.assertIn("auto engine: running", gap_log)
        top_path = os.path.join(gap_out, "top_offtargets.tsv")
        self.assertTrue(os.path.isfile(top_path))
        self.assertTrue(_rows(top_path))

        y_genome_fa = os.path.join(tmp, "y_genome.fa")
        _write_fasta(y_genome_fa, self._fixture_genome(y_layout=True))
        occ_dir = os.path.join(tmp, "yout", "occurrence")
        _run([
            sys.executable,
            os.path.join(Y_DIR, "extract_motifs.py"),
            y_genome_fa, "GGTACC", "20", "20",
            "TGG", "20", "upstream", "TTTA", "20", "downstream",
            "--min_left", "0", "--min_right", "0",
            "--outdir", os.path.dirname(occ_dir),
        ])
        y_log = _run([
            sys.executable,
            os.path.join(Y_DIR, "blast_combined.py"),
            "--input_dir", occ_dir,
            "--genome", y_genome_fa,
            "--target-fasta", y_genome_fa,
            "-o", os.path.join(tmp, "y_auto.tsv"),
            "--blast_db", "",
            "--engine", "auto", "--max-mismatch", "0", "--seed-len", "12",
            "--left-pam-motif", "TGG", "--left-pam-side", "3prime",
            "--left-require-pam",
            "--right-pam-motif", "TTTA", "--right-pam-side", "5prime",
            "--right-require-pam",
            "--nuclease", "cas9", "--left-nuclease", "cas9",
            "--right-nuclease", "cas9",
            "--on-target-model", "cropsr", "--off-target-model", "cfd",
            "--left-on-target-model", "cropsr",
            "--right-on-target-model", "cropsr",
            "--left-off-target-model", "cfd",
            "--right-off-target-model", "cfd",
            "--mode", "free", "--preset", "custom",
            "--gc-min", "0", "--gc-max", "100", "--self-comp-max", "30",
        ], env=env)
        self.assertIn("auto engine: running", y_log)
        self.assertTrue(
            os.path.isfile(os.path.join(tmp, "top_offtargets.tsv")))


if __name__ == "__main__":
    unittest.main()
