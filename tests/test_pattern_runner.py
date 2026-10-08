import json
import os
import sys
import tempfile
import unittest
from unittest import mock


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHARED = os.path.join(ROOT, "shared")
sys.path.insert(0, SHARED)

from design.pattern_runner import (  # noqa: E402
    PatternRunner,
    RunnerConfig,
    parse_confirm_request,
    python_fallback_env,
    split_single_query,
)
from design.pattern_spec import (  # noqa: E402
    MotifSpec,
    PatternKind,
    PatternSpec,
    Side,
)


def make_config(**overrides):
    values = {
        "search_fasta": "input.fa",
        "genome_fasta": "genome.fa",
        "mask_fasta": "mask.fa",
        "output_dir": "out",
        "blastdb": "genome_db",
        "pair_rank_policy": {
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
        },
    }
    values.update(overrides)
    return RunnerConfig(**values)


class PatternRunnerTests(unittest.TestCase):
    def test_single_motif_pipeline_shape(self):
        spec = PatternSpec(
            kind=PatternKind.SINGLE_MOTIF_FLANK,
            motif=MotifSpec("TTAT", 10, Side.UPSTREAM),
        )
        runner = PatternRunner(spec, make_config())
        steps = runner.build_pipeline()
        self.assertEqual(
            [step.name for step in steps],
            ["extract", "off-target search", "score"],
        )
        self.assertTrue(
            runner.build_extract_command()[0].endswith("python.exe")
            or runner.build_extract_command()[0].endswith("python")
        )

    def test_bed_regions_builds_window_fasta(self):
        tmp = tempfile.mkdtemp()
        genome = os.path.join(tmp, "genome.fa")
        bed = os.path.join(tmp, "regions.bed")
        with open(genome, "w", encoding="utf-8") as handle:
            handle.write(">chr1\n")
            handle.write("A" * 40 + "TTAT" + "G" * 40 + "\n")
        with open(bed, "w", encoding="utf-8") as handle:
            handle.write("chr1\t0\t84\tregion1\t0\t+\n")
        spec = PatternSpec(
            kind=PatternKind.SINGLE_MOTIF_FLANK,
            motif=MotifSpec("TTAT", 5, Side.UPSTREAM),
        )
        config = RunnerConfig(
            regions=bed,
            genome_fasta=genome,
            output_dir=tmp,
            search_fasta="",
            preset="cas9",
            engine="exact",
        )
        runner = PatternRunner(spec, config)
        cmd = runner.build_extract_command()
        window_fasta = os.path.join(tmp, "bed_windows.fa")
        self.assertTrue(os.path.isfile(window_fasta))
        self.assertTrue(cmd[2].endswith("bed_windows.fa"))
        with open(window_fasta, encoding="utf-8") as handle:
            content = handle.read()
        self.assertIn(">chr1:0-84:+:region1", content)

    def test_scope_default_mask_uses_search_fasta(self):
        spec = PatternSpec(
            kind=PatternKind.SINGLE_MOTIF_FLANK,
            motif=MotifSpec("TTAT", 10, Side.UPSTREAM),
        )
        default = PatternRunner(
            spec, make_config(mask_fasta="", mask_same_as_target=False)
        )
        self.assertEqual(default._mask_fasta(), "")
        same = PatternRunner(
            spec, make_config(mask_fasta="", mask_same_as_target=True)
        )
        self.assertEqual(same._mask_fasta(), "input.fa")
        explicit = PatternRunner(
            spec, make_config(mask_fasta="mask.fa", mask_same_as_target=True)
        )
        self.assertEqual(explicit._mask_fasta(), "mask.fa")

    def test_bed_scope_default_mask_uses_window_fasta(self):
        tmp = tempfile.mkdtemp()
        genome = os.path.join(tmp, "genome.fa")
        bed = os.path.join(tmp, "regions.bed")
        with open(genome, "w", encoding="utf-8") as handle:
            handle.write(">chr1\n" + "A" * 40 + "TTAT" + "G" * 40 + "\n")
        with open(bed, "w", encoding="utf-8") as handle:
            handle.write("chr1\t0\t84\tregion1\t0\t+\n")
        spec = PatternSpec(
            kind=PatternKind.SINGLE_MOTIF_FLANK,
            motif=MotifSpec("TTAT", 5, Side.UPSTREAM),
        )
        config = RunnerConfig(
            regions=bed,
            genome_fasta=genome,
            output_dir=tmp,
            search_fasta="",
            preset="cas9",
            engine="exact",
            mask_same_as_target=True,
        )
        runner = PatternRunner(spec, config)
        self.assertEqual(
            runner._mask_fasta(), os.path.join(tmp, "bed_windows.fa")
        )

    def test_run_pipeline_supports_find_and_score_split(self):
        spec = PatternSpec(
            kind=PatternKind.SINGLE_MOTIF_FLANK,
            motif=MotifSpec("TTAT", 10, Side.UPSTREAM),
        )
        runner = PatternRunner(spec, make_config())
        steps = runner.build_pipeline()
        self.assertEqual(len(steps), 3)

        with mock.patch(
            "design.pattern_runner.subprocess.Popen"
        ) as popen:
            proc = mock.Mock()
            proc.stdout = []
            proc.wait.return_value = 0
            popen.return_value = proc

            self.assertEqual(runner.run_pipeline(start=0, end=1), 0)
            self.assertEqual(popen.call_count, 1)

            popen.reset_mock()
            self.assertEqual(runner.run_pipeline(start=1), 0)
            self.assertEqual(popen.call_count, 2)

    def test_engine_selection_reaches_offtarget_commands(self):
        config = make_config(
            engine="indexed",
            index_path="idx/prefix",
            genome_build="hg38",
        )
        single = PatternRunner(
            PatternSpec(
                kind=PatternKind.SINGLE_MOTIF_FLANK,
                motif=MotifSpec("TTAT", 10, Side.UPSTREAM),
            ),
            config,
        )
        single_cmd = single.build_pipeline()[1].command
        self.assertIn("--engine", single_cmd)
        self.assertIn("indexed", single_cmd)
        self.assertIn("--index-path", single_cmd)
        self.assertIn("idx/prefix", single_cmd)
        self.assertIn("--genome-build", single_cmd)
        self.assertIn("hg38", single_cmd)

        gap = PatternRunner(
            PatternSpec(
                kind=PatternKind.MOTIF_GAP_MOTIF,
                left=MotifSpec("ATCG", 5, Side.UPSTREAM),
                right=MotifSpec("CCGG", 7, Side.DOWNSTREAM),
                min_gap=10,
                max_gap=20,
            ),
            config,
        )
        gap_cmd = gap.build_pipeline()[1].command
        self.assertIn("--engine", gap_cmd)
        self.assertIn("indexed", gap_cmd)

        y_spec = PatternSpec(
            kind=PatternKind.Y_CENTERED_MOTIFS,
            y_sequence="GGTACC",
            left=MotifSpec("RAC", 6, Side.DOWNSTREAM),
            right=MotifSpec("GYN", 8, Side.UPSTREAM),
            left_min_distance=2,
            left_max_distance=30,
            right_min_distance=0,
            right_max_distance=25,
        )
        y_cmd = PatternRunner(y_spec, config).build_pipeline()[1].command
        self.assertIn("--engine", y_cmd)
        self.assertIn("indexed", y_cmd)

    def test_annotation_reaches_every_score_command(self):
        spec = PatternSpec(
            kind=PatternKind.SINGLE_MOTIF_FLANK,
            motif=MotifSpec("TTAT", 10, Side.UPSTREAM),
        )
        command = PatternRunner(
            spec, make_config(annotation="anno.gff3")
        ).build_pipeline()[-1].command
        self.assertEqual(
            command[command.index("--annotation") + 1], "anno.gff3"
        )
        blank = PatternRunner(spec, make_config()).build_pipeline()[-1].command
        self.assertNotIn("--annotation", blank)

        gap = PatternSpec(
            kind=PatternKind.MOTIF_GAP_MOTIF,
            left=MotifSpec("ATCG", 5, Side.UPSTREAM),
            right=MotifSpec("CCGG", 7, Side.DOWNSTREAM),
            min_gap=10,
            max_gap=20,
        )
        gap_command = PatternRunner(
            gap, make_config(annotation="anno.gff3")
        ).build_pipeline()[-1].command
        self.assertEqual(
            gap_command[gap_command.index("--annotation") + 1], "anno.gff3"
        )

    def test_max_bulge_and_pam_mode_reach_offtarget_commands(self):
        config = make_config(
            engine="exact",
            max_bulge=1,
            pam_mode="guidescan2_nrg",
            pam_motif="NGG",
            pam_side="3prime",
            require_pam=True,
        )
        spec = PatternSpec(
            kind=PatternKind.SINGLE_MOTIF_FLANK,
            motif=MotifSpec("NGG", 10, Side.DOWNSTREAM),
        )
        command = PatternRunner(spec, config).build_pipeline()[1].command
        self.assertEqual(
            command[command.index("--max-bulge") + 1], "1")
        self.assertEqual(
            command[command.index("--pam-motif") + 1], "NRG")

    def test_single_score_step_does_not_pass_exact_flag_to_analyze(self):
        spec = PatternSpec(
            kind=PatternKind.SINGLE_MOTIF_FLANK,
            motif=MotifSpec("TTAT", 10, Side.UPSTREAM),
        )
        runner = PatternRunner(
            spec,
            make_config(exact_offtarget=True, pam_side="5prime"),
        )
        score_step = runner.build_pipeline()[-1]
        self.assertNotIn("--exact-offtarget", score_step.command)
        self.assertNotIn("--pam-side", score_step.command)
        self.assertIn("--max-mismatch", score_step.command)
        index = score_step.command.index("--max-mismatch")
        self.assertEqual(score_step.command[index + 1], "4")

    def test_labeled_outputs_rename_after_run(self):
        spec = PatternSpec(
            kind=PatternKind.SINGLE_MOTIF_FLANK,
            motif=MotifSpec("TTAT", 10, Side.UPSTREAM),
        )
        with tempfile.TemporaryDirectory() as tmp:
            config = make_config(
                output_dir=tmp,
                run_label="Cas12f/TTR",
            )
            runner = PatternRunner(spec, config)
            run_dir = os.path.join(tmp, "Cas12f-TTR")
            os.makedirs(run_dir, exist_ok=True)
            old_path = os.path.join(run_dir, "query_scores_sorted.tsv")
            with open(old_path, "w", encoding="utf-8") as handle:
                handle.write("qid\n")
            runner._finalize_labeled_outputs()
            new_path = os.path.join(
                tmp, "Cas12f-TTR_scores.tsv")
            self.assertTrue(os.path.isfile(new_path))
            self.assertFalse(os.path.isfile(old_path))

    def test_run_labeled_steps_use_a_per_run_dir(self):
        spec = PatternSpec(
            kind=PatternKind.SINGLE_MOTIF_FLANK,
            motif=MotifSpec("TTAT", 10, Side.UPSTREAM),
        )
        with tempfile.TemporaryDirectory() as tmp:
            runner = PatternRunner(
                spec, make_config(output_dir=tmp, run_label="Run/One"))
            run_dir = os.path.join(tmp, "Run-One")
            self.assertEqual(runner._workdir(), run_dir)
            command = runner.build_extract_command()
            print("STEP_ARGV: %s" % " ".join(command))
            self.assertEqual(
                command[-1], os.path.join(run_dir, "extracted_seqs.tsv"))
            for step in runner.build_pipeline():
                self.assertTrue(
                    any(run_dir in arg for arg in step.command), step)

    def test_params_file_records_search_and_scoring_parameters(self):
        spec = PatternSpec(
            kind=PatternKind.SINGLE_MOTIF_FLANK,
            motif=MotifSpec("TTAT", 10, Side.UPSTREAM),
        )
        with tempfile.TemporaryDirectory() as tmp:
            config = make_config(
                output_dir=tmp,
                run_label="Params/A",
                annotation="anno.gff3",
                engine="indexed",
                max_mismatch=3,
                max_bulge=1,
                seed_len=10,
                seed_mismatch_max=2,
                pam_mode="custom",
                pam_motif="NGG",
                pam_side="3prime",
                require_pam=True,
                timeout_s=30,
                max_memory_mode="custom",
                max_memory_mb=1024,
                nuclease="cas12a",
                on_target_model="rules",
                off_target_model="cfd",
                reference_only_model="none",
                gc_min=35,
                gc_max=75,
                self_comp_max=3,
                filter_hard=True,
                crispai=True,
                unique_guides=True,
                xlsx=True,
                exact_offtarget=True,
            )
            runner = PatternRunner(spec, config)
            with mock.patch(
                "design.pattern_runner.subprocess.Popen"
            ) as popen:
                proc = mock.Mock()
                proc.stdout = []
                proc.wait.return_value = 0
                popen.return_value = proc
                self.assertEqual(runner.run_pipeline(), 0)

            run_dir = os.path.join(tmp, "Params-A")
            params_path = os.path.join(run_dir, "params.json")
            self.assertTrue(os.path.isfile(params_path))
            with open(params_path, encoding="utf-8") as handle:
                params = json.load(handle)
            self.assertEqual(params["status"], "ok")
            self.assertEqual(params["return_code"], 0)
            self.assertEqual(params["inputs"]["annotation"], "anno.gff3")
            self.assertEqual(params["search"]["pam_motif"], "NGG")
            self.assertEqual(params["search"]["max_mismatch"], 3)
            self.assertEqual(params["scoring"]["on_target_model"], "rules")
            self.assertTrue(params["output"]["steps"])
            self.assertTrue(any(
                run_dir in arg
                for step in params["output"]["steps"]
                for arg in step["argv"]
            ))
            self.assertTrue(os.path.isfile(
                os.path.join(tmp, "Params-A_params.json")))
            text = json.dumps(params, ensure_ascii=False, indent=2)
            print("PARAMS_JSON_HEAD:")
            print("\n".join(text.splitlines()[:40]))

    def test_motif_gap_motif_extract_command(self):
        spec = PatternSpec(
            kind=PatternKind.MOTIF_GAP_MOTIF,
            left=MotifSpec("ATCG", 5, Side.UPSTREAM),
            right=MotifSpec("CCGG", 7, Side.DOWNSTREAM),
            min_gap=10,
            max_gap=20,
        )
        runner = PatternRunner(spec, make_config())
        command = runner.build_extract_command()
        self.assertTrue(
            any("extract_complex_queries.py" in item for item in command)
        )
        self.assertIn("10", command)
        self.assertIn("20", command)

    def test_y_centered_extract_command(self):
        spec = PatternSpec(
            kind=PatternKind.Y_CENTERED_MOTIFS,
            y_sequence="GGTACC",
            left=MotifSpec("RAC", 6, Side.DOWNSTREAM),
            right=MotifSpec("GYN", 8, Side.UPSTREAM),
            left_min_distance=2,
            left_max_distance=30,
            right_min_distance=0,
            right_max_distance=25,
        )
        runner = PatternRunner(spec, make_config())
        command = runner.build_extract_command()
        self.assertTrue(any("extract_motifs.py" in item for item in command))
        self.assertIn("GGTACC", command)
        self.assertIn("--min_left", command)
        self.assertIn("--min_right", command)

    def test_single_preset_forces_pam_hard_filter(self):
        spec = PatternSpec(
            kind=PatternKind.SINGLE_MOTIF_FLANK,
            motif=MotifSpec("TTAT", 10, Side.UPSTREAM),
        )
        runner = PatternRunner(
            spec,
            make_config(
                mode="preset", preset="cas12a", require_pam=False,
                pam_motif="GG", pam_side="3prime",
            ),
        )
        command = runner.build_pipeline()[1].command
        self.assertIn("--require-pam", command)
        self.assertIn("--pam-motif", command)
        self.assertIn("TTTN", command)
        self.assertIn("--pam-side", command)
        self.assertIn("5prime", command)

    def test_gap_preset_forces_pam_hard_filter(self):
        spec = PatternSpec(
            kind=PatternKind.MOTIF_GAP_MOTIF,
            left=MotifSpec("ATCG", 5, Side.UPSTREAM),
            right=MotifSpec("CCGG", 7, Side.DOWNSTREAM),
            min_gap=10,
            max_gap=20,
        )
        runner = PatternRunner(
            spec,
            make_config(
                mode="preset", preset="cas9", require_pam=False,
                pam_motif="NAG", pam_side="3prime",
            ),
        )
        command = runner.build_pipeline()[1].command
        self.assertIn("--require-pam", command)
        self.assertIn("--pam-motif", command)
        self.assertIn("NGG", command)
        self.assertIn("--pam-side", command)

    def test_pair_pam_settings_are_split_per_side(self):
        spec = PatternSpec(
            kind=PatternKind.MOTIF_GAP_MOTIF,
            left=MotifSpec("ATCG", 5, Side.UPSTREAM),
            right=MotifSpec("CCGG", 7, Side.DOWNSTREAM),
            min_gap=10,
            max_gap=20,
        )
        runner = PatternRunner(
            spec,
            make_config(
                pam_motif="NGG", pam_side="3prime", require_pam=False,
                left_pam_motif="TTTN", left_pam_side="5prime",
                left_require_pam=True,
                right_pam_motif="CCN", right_pam_side="3prime",
                right_require_pam=True,
            ),
        )
        command = runner.build_pipeline()[1].command
        self.assertIn("--left-require-pam", command)
        self.assertIn("--right-require-pam", command)
        self.assertIn("--left-pam-motif", command)
        self.assertIn("TTTN", command)
        self.assertIn("--left-pam-side", command)
        self.assertIn("5prime", command)
        self.assertIn("--right-pam-motif", command)
        self.assertIn("CCN", command)
        self.assertIn("--right-pam-side", command)
        self.assertEqual(runner._side_pam_settings("left"),
                         ("TTTN", "5prime", True))
        self.assertEqual(runner._side_pam_settings("right"),
                         ("CCN", "3prime", True))

    def test_pair_runner_passes_multiple_model_choices_per_side(self):
        spec = PatternSpec(
            kind=PatternKind.MOTIF_GAP_MOTIF,
            left=MotifSpec("ATCG", 5, Side.UPSTREAM),
            right=MotifSpec("CCGG", 7, Side.DOWNSTREAM),
            min_gap=10,
            max_gap=20,
        )
        runner = PatternRunner(
            spec,
            make_config(
                left_on_target_model="cropsr,rules",
                left_off_target_model="cfd,crispr_m",
                right_on_target_model="deepcas12a,rules",
                right_off_target_model="rules,cfd",
                left_preset="tnpb",
                right_preset="cas9",
            ),
        )
        command = runner.build_pipeline()[1].command
        self.assertIn("cropsr,rules", command)
        self.assertIn("cfd,crispr_m", command)
        self.assertIn("deepcas12a,rules", command)
        self.assertIn("rules,cfd", command)
        self.assertEqual(
            command[command.index("--left-preset") + 1], "tnpb")
        self.assertEqual(
            command[command.index("--right-preset") + 1], "cas9")

    def test_y_preset_forces_pam_hard_filter(self):
        spec = PatternSpec(
            kind=PatternKind.Y_CENTERED_MOTIFS,
            y_sequence="GGTACC",
            left=MotifSpec("RAC", 6, Side.DOWNSTREAM),
            right=MotifSpec("GYN", 8, Side.UPSTREAM),
            left_min_distance=2,
            left_max_distance=30,
            right_min_distance=0,
            right_max_distance=25,
        )
        runner = PatternRunner(
            spec,
            make_config(
                mode="preset", preset="cas12b", require_pam=False,
                pam_motif="GG", pam_side="3prime",
            ),
        )
        command = runner.build_pipeline()[1].command
        self.assertIn("--require-pam", command)
        self.assertIn("--pam-motif", command)
        self.assertIn("TTN", command)
        self.assertIn("--pam-side", command)
        self.assertIn("5prime", command)
        self.assertIn("--target-fasta", command)
        self.assertIn("input.fa", command)

    def test_y_sort_requires_both_sides(self):
        spec = PatternSpec(
            kind=PatternKind.Y_CENTERED_MOTIFS,
            y_sequence="GGTACC",
            left=MotifSpec("RAC", 6, Side.DOWNSTREAM),
            right=MotifSpec("GYN", 8, Side.UPSTREAM),
            left_min_distance=2,
            left_max_distance=30,
            right_min_distance=0,
            right_max_distance=25,
        )
        runner = PatternRunner(spec, make_config())
        command = runner.build_pipeline()[-1].command
        self.assertIn("--pair-rank-policy", command)
        self.assertIn("--left-min-distance", command)
        self.assertIn("--left-max-distance", command)
        self.assertIn("--right-min-distance", command)
        self.assertIn("--right-max-distance", command)
        self.assertIn("--left-nuclease", command)
        self.assertIn("--right-nuclease", command)
        self.assertNotIn("--sort", command)
        self.assertNotIn("combined", command)

    def test_y_sorted_output_uses_motif_label(self):
        spec = PatternSpec(
            kind=PatternKind.Y_CENTERED_MOTIFS,
            y_sequence="TTAA",
            left=MotifSpec("TTR", 8, Side.DOWNSTREAM),
            right=MotifSpec("TTR", 8, Side.UPSTREAM),
            left_min_distance=2,
            left_max_distance=30,
            right_min_distance=0,
            right_max_distance=25,
        )
        with tempfile.TemporaryDirectory() as tmp:
            config = make_config(output_dir=tmp, run_label="TTR-TTAA-TTR")
            runner = PatternRunner(spec, config)
            run_dir = os.path.join(tmp, "TTR-TTAA-TTR")
            os.makedirs(run_dir, exist_ok=True)
            old_path = os.path.join(run_dir, "scores.sorted.tsv")
            with open(old_path, "w", encoding="utf-8") as handle:
                handle.write("occurrence\n")
            runner._finalize_labeled_outputs()
            new_path = os.path.join(
                tmp, "TTR-TTAA-TTR_scores.sorted.tsv")
            self.assertTrue(os.path.isfile(new_path))
            self.assertFalse(os.path.isfile(old_path))

    def test_output_path_is_mode_specific(self):
        single = PatternSpec(
            kind=PatternKind.SINGLE_MOTIF_FLANK,
            motif=MotifSpec("AAAA"),
        )
        paired = PatternSpec(
            kind=PatternKind.MOTIF_GAP_MOTIF,
            left=MotifSpec("AAAA"),
            right=MotifSpec("TTTT"),
            min_gap=1,
            max_gap=5,
        )
        y_spec = PatternSpec(
            kind=PatternKind.Y_CENTERED_MOTIFS,
            y_sequence="GGTACC",
            left=MotifSpec("AAAA"),
            right=MotifSpec("TTTT"),
            left_min_distance=0,
            left_max_distance=10,
            right_min_distance=0,
            right_max_distance=10,
        )
        self.assertTrue(
            PatternRunner(single, make_config()).extract_output_path().endswith(
                "extracted_seqs.tsv"
            )
        )
        self.assertTrue(
            PatternRunner(paired, make_config()).extract_output_path().endswith(
                "complex_queries.tsv"
            )
        )
        self.assertTrue(
            PatternRunner(y_spec, make_config()).extract_output_path().endswith(
                "occurrence"
            )
        )

    def test_read_single_extract_candidates(self):
        spec = PatternSpec(
            kind=PatternKind.SINGLE_MOTIF_FLANK,
            motif=MotifSpec("TTAT", 4, Side.UPSTREAM),
        )
        with tempfile.TemporaryDirectory() as tmp:
            config = make_config(output_dir=tmp)
            runner = PatternRunner(spec, config)
            path = runner.extract_output_path()
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("# motif=TTAT flanking_len=4 side=upstream\n")
                handle.write("qid\tsequence\tpositions\n")
                handle.write(
                    'uniq_0\tAATTTTAT\t[["chr1", "plus", 10]]\n'
                )
            rows = runner.read_extract_candidates()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["query_id"], "uniq_0")
            self.assertEqual(rows[0]["seq_id"], "chr1")
            self.assertEqual(rows[0]["start"], "11")
            self.assertEqual(rows[0]["motif_seq"], "TTAT")
            self.assertEqual(rows[0]["flank_seq"], "AATT")
            self.assertEqual(rows[0]["side"], "upstream")
            self.assertEqual(rows[0]["flank_length"], "4")

    def test_split_single_query_matches_extract_layout(self):
        # basic/extract.py: plus/upstream and minus/downstream put the flank
        # first; plus/downstream and minus/upstream put the motif first.
        self.assertEqual(
            split_single_query("AATTTTAT", "plus", "upstream", 4),
            ("TTAT", "AATT"),
        )
        self.assertEqual(
            split_single_query("TTATCCCC", "plus", "downstream", 4),
            ("TTAT", "CCCC"),
        )
        self.assertEqual(
            split_single_query("TTATCCCC", "minus", "upstream", 4),
            ("TTAT", "CCCC"),
        )
        self.assertEqual(
            split_single_query("AATTTTAT", "minus", "downstream", 4),
            ("TTAT", "AATT"),
        )

    def test_read_single_extract_candidates_accepts_target_start(self):
        spec = PatternSpec(
            kind=PatternKind.SINGLE_MOTIF_FLANK,
            motif=MotifSpec("TTAT", 4, Side.UPSTREAM),
        )
        with tempfile.TemporaryDirectory() as tmp:
            config = make_config(output_dir=tmp)
            runner = PatternRunner(spec, config)
            path = runner.extract_output_path()
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("# motif=TTAT flanking_len=4 side=upstream\n")
                handle.write("qid\tsequence\tpositions\n")
                handle.write(
                    'uniq_0\tAATTTTAT\t[["chr1", "plus", 10, 6]]\n'
                )
            rows = runner.read_extract_candidates()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["start"], "11")

    def test_read_gap_extract_candidates(self):
        spec = PatternSpec(
            kind=PatternKind.MOTIF_GAP_MOTIF,
            left=MotifSpec("ATCG", 5, Side.UPSTREAM),
            right=MotifSpec("CCGG", 7, Side.DOWNSTREAM),
            min_gap=10,
            max_gap=20,
        )
        with tempfile.TemporaryDirectory() as tmp:
            config = make_config(output_dir=tmp)
            runner = PatternRunner(spec, config)
            path = runner.extract_output_path()
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(
                    "seq_id\tstrand\tleft_pos\tright_pos\tgap\tquery_seq\n"
                )
                handle.write("chr1\tplus\t10\t20\t6\tATCGNNNNNNCCGG\n")
            rows = runner.read_extract_candidates()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["seq_id"], "chr1")
            self.assertEqual(rows[0]["gap"], "6")

    def test_read_gap_extract_candidates_uses_query_sidecar(self):
        spec = PatternSpec(
            kind=PatternKind.MOTIF_GAP_MOTIF,
            left=MotifSpec("ATCG", 5, Side.UPSTREAM),
            right=MotifSpec("CCGG", 7, Side.DOWNSTREAM),
            min_gap=10,
            max_gap=20,
        )
        with tempfile.TemporaryDirectory() as tmp:
            config = make_config(output_dir=tmp)
            runner = PatternRunner(spec, config)
            path = runner.extract_output_path()
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(
                    "qid\tseq_id\tstrand\tleft_pos\tright_pos\tgap\n"
                )
                handle.write("uniq_0\tchr1\tplus\t10\t20\t6\n")
            sidecar = os.path.splitext(path)[0] + ".queries.fa"
            with open(sidecar, "w", encoding="utf-8") as handle:
                handle.write(">uniq_0\nATCGNNNNNNCCGG\n")
            rows = runner.read_extract_candidates()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["qid"], "uniq_0")
            self.assertEqual(rows[0]["query_seq"], "ATCGNNNNNNCCGG")

    def test_read_y_extract_candidates(self):
        spec = PatternSpec(
            kind=PatternKind.Y_CENTERED_MOTIFS,
            y_sequence="GGTACC",
            left=MotifSpec("RAC", 6, Side.DOWNSTREAM),
            right=MotifSpec("GYN", 8, Side.UPSTREAM),
            left_min_distance=2,
            left_max_distance=30,
            right_min_distance=0,
            right_max_distance=25,
        )
        with tempfile.TemporaryDirectory() as tmp:
            config = make_config(output_dir=tmp)
            runner = PatternRunner(spec, config)
            occurrence_dir = runner.extract_output_path()
            os.makedirs(occurrence_dir, exist_ok=True)
            with open(
                os.path.join(occurrence_dir, "occurrence_info.tsv"),
                "w",
                encoding="utf-8",
            ) as handle:
                handle.write("occurrence\tchrom\ty_start\ty_end\tstrand\n")
                handle.write("1\tchr1\t100\t106\t+\n")
            for side, seq in (("left", "AACG"), ("right", "GTT")):
                with open(
                    os.path.join(occurrence_dir, f"{side}_occurrence_1.tsv"),
                    "w",
                    encoding="utf-8",
                ) as handle:
                    handle.write("# metadata\n")
                    handle.write("qid\tsequence\tpositions\n")
                    handle.write(
                        f'uniq_0\t{seq}\t[["chr1", "plus", 20]]\n'
                    )
            rows = runner.read_extract_candidates()
            self.assertEqual(len(rows), 2)
            self.assertEqual({row["side"] for row in rows}, {"left", "right"})


class PipelineConfirmationTests(unittest.TestCase):
    """CONFIRM_REQUIRED requests from engine steps must be answered."""

    def test_parse_confirm_request(self):
        request = parse_confirm_request(
            "CONFIRM_REQUIRED: python_fallback|native engine missing")
        self.assertEqual(request["kind"], "python_fallback")
        self.assertEqual(request["reason"], "native engine missing")
        self.assertIsNone(parse_confirm_request("PROGRESS: 10"))
        self.assertIsNone(parse_confirm_request(""))

    def test_fallback_env_defaults_to_ask(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CRISPR_OFFTARGET_PYTHON_FALLBACK", None)
            env = python_fallback_env()
        self.assertEqual(env["CRISPR_OFFTARGET_PYTHON_FALLBACK"], "ask")

    def _run_marker_pipeline(self, on_prompt, lines=None):
        spec = PatternSpec(
            kind=PatternKind.SINGLE_MOTIF_FLANK,
            motif=MotifSpec("TTAT", 10, Side.UPSTREAM),
        )
        runner = PatternRunner(spec, make_config())
        proc = mock.Mock()
        proc.stdout = [
            "[off-target search] python blast.py\n",
            "CONFIRM_REQUIRED: python_fallback|native engine missing\n",
            "PROGRESS: 10\n",
        ]
        proc.stdin = mock.Mock()
        proc.wait.return_value = 0
        with mock.patch(
                "design.pattern_runner.subprocess.Popen", return_value=proc):
            code = runner.run_pipeline(
                on_line=(lines.append if lines is not None else None),
                start=1, end=2, on_prompt=on_prompt)
        return code, proc

    def test_pipeline_answers_confirmation_from_the_front_end(self):
        prompts = []

        def on_prompt(request):
            prompts.append(request)
            return True

        lines = []
        code, proc = self._run_marker_pipeline(on_prompt, lines)
        self.assertEqual(code, 0)
        self.assertEqual(prompts[0]["kind"], "python_fallback")
        self.assertEqual(prompts[0]["reason"], "native engine missing")
        proc.stdin.write.assert_called_once_with("yes\n")
        self.assertIn(
            "CONFIRM_REQUIRED: python_fallback|native engine missing", lines)

    def test_pipeline_can_be_declined_by_the_front_end(self):
        lines = []
        code, proc = self._run_marker_pipeline(lambda request: False, lines)
        self.assertEqual(code, 0)
        proc.stdin.write.assert_called_once_with("no\n")

    def test_pipeline_refuses_without_a_handler(self):
        lines = []
        code, proc = self._run_marker_pipeline(None, lines)
        self.assertEqual(code, 0)
        proc.stdin.write.assert_called_once_with("no\n")
        self.assertIn(
            "No confirmation handler available; answering no.", lines)

    def test_pipeline_refuses_when_the_handler_raises(self):
        def boom(request):
            raise RuntimeError("dialog closed")

        lines = []
        code, proc = self._run_marker_pipeline(boom, lines)
        self.assertEqual(code, 0)
        proc.stdin.write.assert_called_once_with("no\n")
        self.assertTrue(any("dialog closed" in line for line in lines))


if __name__ == "__main__":
    unittest.main()
