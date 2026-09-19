from __future__ import annotations

import csv
import json
import os
import re
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from design.pattern_spec import MotifSpec, PatternKind, PatternSpec
from design.system_presets import (
    get_preset, normalize_pam_mode, pam_motif_for_mode,
)
from scoring.pair_ranking_adapter import write_pair_rank_policy_file
from utils.child_process import (
    popen_kwargs, register_child, terminate_process_tree, unregister_child,
)


@dataclass
class RunnerConfig:
    search_fasta: str = ""
    regions: str = ""
    genome_fasta: str = ""
    mask_fasta: str = ""
    output_dir: str = ""
    blastdb: str = ""
    nuclease: str = "cas9"
    tnpb_subtype: str = "unknown"
    left_nuclease: Optional[str] = None
    right_nuclease: Optional[str] = None
    left_tnpb_subtype: Optional[str] = None
    right_tnpb_subtype: Optional[str] = None
    left_preset: Optional[str] = None
    right_preset: Optional[str] = None
    left_off_target_model: Optional[str] = None
    right_off_target_model: Optional[str] = None
    left_on_target_model: Optional[str] = None
    right_on_target_model: Optional[str] = None
    left_reference_only_model: Optional[str] = None
    right_reference_only_model: Optional[str] = None
    left_pam_motif: Optional[str] = None
    right_pam_motif: Optional[str] = None
    left_pam_side: Optional[str] = None
    right_pam_side: Optional[str] = None
    left_require_pam: Optional[bool] = None
    right_require_pam: Optional[bool] = None
    reference_only_model: str = "none"
    on_target_model: str = "cropsr"
    off_target_model: str = "rules"
    max_mismatch: int = 4
    max_bulge: Optional[int] = None
    pam_mode: str = "strict_ngg"
    require_pam: bool = False
    seed_mismatch_max: Optional[int] = None
    seed_len: int = 12
    max_memory_mode: str = "auto"
    max_memory_mb: Optional[int] = None
    timeout_s: Optional[float] = None
    repeat_fasta: str = ""
    gc_min: float = 40.0
    gc_max: float = 70.0
    self_comp_max: int = 4
    filter_hard: bool = False
    crispai: bool = False
    unique_guides: bool = False
    annotation: str = ""
    xlsx: bool = False
    exact_offtarget: bool = False
    pam_side: str = "3prime"
    pam_motif: str = "GG"
    mode: str = "free"
    preset: str = "custom"
    engine: str = "auto"
    index_path: str = ""
    genome_build: str = ""
    run_label: str = ""
    pair_rank_policy: Optional[Dict[str, float]] = None


@dataclass(frozen=True)
class PipelineStep:
    name: str
    command: List[str]


CONFIRM_REQUIRED_PREFIX = "CONFIRM_REQUIRED:"

# Return code reported when a front end stops a pipeline on purpose.
STOPPED_RETURN_CODE = 130


def parse_confirm_request(line):
    """Return the parsed ``CONFIRM_REQUIRED: kind|reason`` request, if any."""
    text = (line or "").strip()
    if not text.startswith(CONFIRM_REQUIRED_PREFIX):
        return None
    payload = text[len(CONFIRM_REQUIRED_PREFIX):].strip()
    kind, _, reason = payload.partition("|")
    return {"kind": kind.strip(), "reason": reason.strip(), "line": text}


def python_fallback_env():
    """Child environment that makes engine steps ask before degrading."""
    env = os.environ.copy()
    try:
        from search.offtarget_backend import (
            ENGINE_FALLBACK_ENV, PYTHON_FALLBACK_ENV)
    except Exception:
        PYTHON_FALLBACK_ENV = "CRISPR_OFFTARGET_PYTHON_FALLBACK"
        ENGINE_FALLBACK_ENV = "CRISPR_OFFTARGET_ENGINE_FALLBACK"
    env.setdefault(PYTHON_FALLBACK_ENV, "ask")
    env.setdefault(ENGINE_FALLBACK_ENV, "ask")
    return env


def _write_child_stdin(proc, text):
    try:
        if proc.stdin is not None:
            proc.stdin.write(text)
            proc.stdin.flush()
    except (BrokenPipeError, ValueError, OSError):
        pass


def _close_child_stdin(proc):
    try:
        if proc.stdin is not None:
            proc.stdin.close()
    except (BrokenPipeError, ValueError, OSError):
        pass


def _close_child_stdout(proc):
    try:
        if proc.stdout is not None:
            proc.stdout.close()
    except (AttributeError, OSError, ValueError):
        pass


class PatternRunner:
    """Convert a PatternSpec into the existing extract/search/score scripts."""

    def __init__(self, spec: PatternSpec, config: RunnerConfig):
        self.spec = spec
        self.config = config
        self._window_fasta: Optional[str] = None
        self._stop_requested = False
        self._current_proc = None
        self._proc_lock = threading.Lock()
        self.spec.validate()

    @property
    def project_root(self) -> Path:
        return Path(__file__).resolve().parents[2]

    def _py(self) -> str:
        return sys.executable

    def _outdir(self) -> str:
        output_dir = (self.config.output_dir or "").strip()
        if not output_dir:
            raise ValueError("RunnerConfig.output_dir is required")
        os.makedirs(output_dir, exist_ok=True)
        return output_dir

    def _run_label_suffix(self) -> str:
        label = (self.config.run_label or "").strip()
        label = re.sub(r"[/\\]+", "-", label)
        label = re.sub(r"[^A-Za-z0-9._-]+", "_", label)
        return label.strip("._-")

    def _finalize_labeled_outputs(self) -> None:
        label = self._run_label_suffix()
        if not label:
            return
        output_dir = self._outdir()
        if self.spec.kind is PatternKind.SINGLE_MOTIF_FLANK:
            names = (
                "query_scores_sorted.tsv",
                "query_scores_sorted.xlsx",
                "unique_guides.tsv",
                "unique_guides.xlsx",
                "top_offtargets.tsv",
                "top_offtargets.xlsx",
                "blast_results.tsv",
            )
        elif self.spec.kind is PatternKind.MOTIF_GAP_MOTIF:
            names = (
                "query_scores_sorted.tsv",
                "query_scores_sorted.xlsx",
                "unique_guides.tsv",
                "unique_guides.xlsx",
                "top_offtargets.tsv",
                "top_offtargets.xlsx",
            )
        else:
            names = (
                "scores.tsv",
                "scores.sorted.tsv",
                "unique_guides.tsv",
                "unique_guides.xlsx",
                "top_offtargets.tsv",
                "top_offtargets.xlsx",
            )
        for name in names:
            old_path = os.path.join(output_dir, name)
            if not os.path.isfile(old_path):
                continue
            stem, ext = os.path.splitext(name)
            short_stem = {
                "query_scores_sorted": "scores",
                "unique_guides": "guides",
                "top_offtargets": "offtargets",
            }.get(stem, stem)
            new_path = os.path.join(
                output_dir, "%s_%s%s" % (label, short_stem, ext))
            try:
                os.replace(old_path, new_path)
            except OSError:
                pass

    def extract_output_path(self) -> str:
        output_dir = self._outdir()
        if self.spec.kind is PatternKind.SINGLE_MOTIF_FLANK:
            return os.path.join(output_dir, "extracted_seqs.tsv")
        if self.spec.kind is PatternKind.MOTIF_GAP_MOTIF:
            return os.path.join(output_dir, "complex_queries.tsv")
        return os.path.join(output_dir, "occurrence")

    def _script(self, relative_path: str) -> str:
        return str(self.project_root / relative_path)

    def build_extract_command(self) -> List[str]:
        if self.spec.kind is PatternKind.SINGLE_MOTIF_FLANK:
            return self._single_extract_command()
        if self.spec.kind is PatternKind.MOTIF_GAP_MOTIF:
            return self._gap_extract_command()
        return self._y_extract_command()

    def build_pipeline(self) -> List[PipelineStep]:
        if self.spec.kind is PatternKind.SINGLE_MOTIF_FLANK:
            return self._single_pipeline()
        if self.spec.kind is PatternKind.MOTIF_GAP_MOTIF:
            return self._gap_pipeline()
        return self._y_pipeline()

    def _single_extract_command(self) -> List[str]:
        motif = self._required_motif(self.spec.motif)
        output = self.extract_output_path()
        return [
            self._py(),
            self._script(os.path.join("basic", "extract.py")),
            self._search_fasta(),
            motif.sequence,
            str(motif.flank_length),
            motif.side.value,
            output,
        ]

    def _gap_extract_command(self) -> List[str]:
        left = self._required_motif(self.spec.left)
        right = self._required_motif(self.spec.right)
        if self.spec.min_gap is None or self.spec.max_gap is None:
            raise ValueError("motif_gap_motif requires min_gap and max_gap")
        return [
            self._py(),
            self._script(
                os.path.join("Target_xbp_Target", "extract_complex_queries.py")
            ),
            self._search_fasta(),
            left.sequence,
            right.sequence,
            str(self.spec.min_gap),
            str(self.spec.max_gap),
            left.side.value,
            str(left.flank_length),
            right.side.value,
            str(right.flank_length),
            self.extract_output_path(),
        ]

    def _y_extract_command(self) -> List[str]:
        left = self._required_motif(self.spec.left)
        right = self._required_motif(self.spec.right)
        if (
            self.spec.left_max_distance is None
            or self.spec.right_max_distance is None
            or self.spec.left_min_distance is None
            or self.spec.right_min_distance is None
        ):
            raise ValueError("y_centered_motifs requires distance ranges")
        return [
            self._py(),
            self._script(
                os.path.join("Target_xbp_Y_zbp_Target", "extract_motifs.py")
            ),
            self._search_fasta(),
            self.spec.y_sequence,
            str(self.spec.left_max_distance),
            str(self.spec.right_max_distance),
            left.sequence,
            str(left.flank_length),
            left.side.value,
            right.sequence,
            str(right.flank_length),
            right.side.value,
            "--min_left",
            str(self.spec.left_min_distance),
            "--min_right",
            str(self.spec.right_min_distance),
            "--outdir",
            self._outdir(),
        ]

    def _single_pipeline(self) -> List[PipelineStep]:
        query = self.extract_output_path()
        intermediate = os.path.join(self._outdir(), "blast_results.tsv")
        steps = [
            PipelineStep("extract", self.build_extract_command()),
            PipelineStep(
                "off-target search", self._single_offtarget_command(query)
            ),
            PipelineStep("score", self._single_analyze_command(intermediate)),
        ]
        return steps

    def _gap_pipeline(self) -> List[PipelineStep]:
        query = self.extract_output_path()
        return [
            PipelineStep("extract", self.build_extract_command()),
            PipelineStep(
                "off-target search & score", self._gap_analyze_command(query)
            ),
        ]

    def _y_pipeline(self) -> List[PipelineStep]:
        query_dir = self.extract_output_path()
        scores = os.path.join(self._outdir(), "scores.tsv")
        sorted_scores = os.path.join(self._outdir(), "scores.sorted.tsv")
        return [
            PipelineStep("extract", self.build_extract_command()),
            PipelineStep(
                "off-target search & score", self._y_offtarget_command(query_dir)
            ),
            PipelineStep(
                "sort", self._y_sort_command(scores, sorted_scores)
            ),
        ]

    def _single_offtarget_command(self, query: str) -> List[str]:
        command = [
            self._py(),
            self._script(os.path.join("basic", "blast.py")),
            query,
            self._genome_fasta(),
            "--输出目录",
            self._outdir(),
        ]
        if self._mask_fasta():
            command.extend(["--屏蔽基因", self._mask_fasta()])
        motif = self._required_motif(self.spec.motif)
        command.extend(["--motif", motif.sequence])
        command.extend(["--flank_len", str(motif.flank_length)])
        command.extend(["--side", motif.side.value])
        if self.config.blastdb:
            command.extend(["--blastdb", self.config.blastdb])
        command.extend(["--engine", self.config.engine])
        if self.config.index_path:
            command.extend(["--index-path", self.config.index_path])
        if self.config.genome_build:
            command.extend(["--genome-build", self.config.genome_build])
        command.extend(["--max-mismatch", str(self.config.max_mismatch)])
        if self.config.max_bulge is not None:
            command.extend(["--max-bulge", str(self.config.max_bulge)])
        pam_motif, pam_side, require_pam = self._pam_settings()
        if require_pam:
            command.append("--require-pam")
        if pam_motif:
            command.extend(["--pam-motif", pam_motif])
        if pam_side:
            command.extend(["--pam-side", pam_side])
        if self.config.seed_mismatch_max is not None:
            command.extend(
                ["--seed-mismatch-max", str(self.config.seed_mismatch_max)]
            )
        command.extend(["--seed-len", str(self.config.seed_len)])
        if self.config.repeat_fasta:
            command.extend(["--repeat-fasta", self.config.repeat_fasta])
        command.extend(self._memory_limit_flags())
        command.extend(self._timeout_flags())
        return command

    def _single_analyze_command(self, intermediate: str) -> List[str]:
        return [
            self._py(),
            self._script(os.path.join("basic", "analyze_scores.py")),
            intermediate,
            self._outdir(),
            "--nuclease",
            self.config.nuclease,
            "--tnpb-subtype",
            self.config.tnpb_subtype,
            "--reference-only-model",
            self.config.reference_only_model,
            "--on-target-model",
            self.config.on_target_model,
            "--off-target-model",
            self.config.off_target_model,
            "--max-mismatch",
            str(self.config.max_mismatch),
            "--mode",
            self.config.mode,
            "--preset",
            self.config.preset,
            "--pam-motif",
            self._pam_settings()[0],
            "--gc-min",
            str(self.config.gc_min),
            "--gc-max",
            str(self.config.gc_max),
            "--self-comp-max",
            str(self.config.self_comp_max),
        ] + self._common_score_flags(include_exact=False) + self._crispai_flags()

    def _gap_analyze_command(self, query: str) -> List[str]:
        command = [
            self._py(),
            self._script(
                os.path.join("Target_xbp_Target", "analyze_complex_scores.py")
            ),
            query,
            self._mask_fasta(),
            self._genome_fasta(),
            self._outdir(),
            "--blastdb",
            self.config.blastdb,
            "--engine",
            self.config.engine,
            "--index-path",
            self.config.index_path,
            "--genome-build",
            self.config.genome_build,
            "--nuclease",
            self.config.nuclease,
            "--tnpb-subtype",
            self.config.tnpb_subtype,
            "--reference-only-model",
            self.config.reference_only_model,
            "--on-target-model",
            self.config.on_target_model,
            "--off-target-model",
            self.config.off_target_model,
            "--mode",
            self.config.mode,
            "--preset",
            self.config.preset,
            "--max-mismatch",
            str(self.config.max_mismatch),
            "--seed-len",
            str(self.config.seed_len),
            "--gc-min",
            str(self.config.gc_min),
            "--gc-max",
            str(self.config.gc_max),
            "--self-comp-max",
            str(self.config.self_comp_max),
        ]
        if self.config.max_bulge is not None:
            command.extend(
                ["--max-bulge", str(self.config.max_bulge)])
        pam_motif, pam_side, require_pam = self._pam_settings()
        if require_pam:
            command.append("--require-pam")
        if pam_motif:
            command.extend(["--pam-motif", pam_motif])
        if pam_side:
            command.extend(["--pam-side", pam_side])
        left_motif, left_side, left_require = self._side_pam_settings("left")
        right_motif, right_side, right_require = self._side_pam_settings("right")
        if left_require:
            command.append("--left-require-pam")
        if left_motif:
            command.extend(["--left-pam-motif", left_motif])
        if left_side:
            command.extend(["--left-pam-side", left_side])
        if right_require:
            command.append("--right-require-pam")
        if right_motif:
            command.extend(["--right-pam-motif", right_motif])
        if right_side:
            command.extend(["--right-pam-side", right_side])
        command.extend([
            "--left-nuclease",
            self.config.left_nuclease or self.config.nuclease,
            "--right-nuclease",
            self.config.right_nuclease or self.config.nuclease,
            "--left-tnpb-subtype",
            self.config.left_tnpb_subtype or self.config.tnpb_subtype,
            "--right-tnpb-subtype",
            self.config.right_tnpb_subtype or self.config.tnpb_subtype,
            "--left-preset",
            self.config.left_preset or self.config.preset,
            "--right-preset",
            self.config.right_preset or self.config.preset,
            "--left-off-target-model",
            self.config.left_off_target_model or self.config.off_target_model,
            "--right-off-target-model",
            self.config.right_off_target_model or self.config.off_target_model,
            "--left-on-target-model",
            self.config.left_on_target_model or self.config.on_target_model,
            "--right-on-target-model",
            self.config.right_on_target_model or self.config.on_target_model,
            "--left-reference-only-model",
            self.config.left_reference_only_model or self.config.reference_only_model,
            "--right-reference-only-model",
            self.config.right_reference_only_model or self.config.reference_only_model,
        ])
        if self.spec.min_gap is not None:
            command.extend(["--min-gap", str(self.spec.min_gap)])
        if self.spec.max_gap is not None:
            command.extend(["--max-gap", str(self.spec.max_gap)])
        if self.spec.left is not None:
            command.extend(["--left-side", self.spec.left.side.value])
        if self.spec.right is not None:
            command.extend(["--right-side", self.spec.right.side.value])
        command.extend([
            "--pair-rank-policy",
            self._pair_rank_policy_file(),
        ])
        command.extend(self._common_score_flags())
        command.extend(self._crispai_flags())
        command.extend(self._memory_limit_flags())
        command.extend(self._timeout_flags())
        return command

    def _y_offtarget_command(self, query_dir: str) -> List[str]:
        command = [
            self._py(),
            self._script(
                os.path.join("Target_xbp_Y_zbp_Target", "blast_combined.py")
            ),
            "--input_dir",
            query_dir,
            "--genome",
            self._genome_fasta(),
            "--target-fasta",
            self._search_fasta(),
            "-o",
            os.path.join(self._outdir(), "scores.tsv"),
            "--blast_db",
            self.config.blastdb,
            "--engine",
            self.config.engine,
            "--index-path",
            self.config.index_path,
            "--genome-build",
            self.config.genome_build,
            "--nuclease",
            self.config.nuclease,
            "--tnpb-subtype",
            self.config.tnpb_subtype,
            "--reference-only-model",
            self.config.reference_only_model,
            "--on-target-model",
            self.config.on_target_model,
            "--off-target-model",
            self.config.off_target_model,
            "--mode",
            self.config.mode,
            "--preset",
            self.config.preset,
            "--max-mismatch",
            str(self.config.max_mismatch),
            "--seed-len",
            str(self.config.seed_len),
            "--gc-min",
            str(self.config.gc_min),
            "--gc-max",
            str(self.config.gc_max),
            "--self-comp-max",
            str(self.config.self_comp_max),
        ]
        if self.config.max_bulge is not None:
            command.extend(
                ["--max-bulge", str(self.config.max_bulge)])
        if self._mask_fasta():
            command.extend(["--mask", self._mask_fasta()])
        pam_motif, pam_side, require_pam = self._pam_settings()
        if require_pam:
            command.append("--require-pam")
        if pam_motif:
            command.extend(["--pam-motif", pam_motif])
        if pam_side:
            command.extend(["--pam-side", pam_side])
        if self.config.seed_mismatch_max is not None:
            command.extend(
                ["--seed-mismatch-max", str(self.config.seed_mismatch_max)]
            )
        if self.config.repeat_fasta:
            command.extend(["--repeat-fasta", self.config.repeat_fasta])
        command.extend([
            "--left-nuclease",
            self.config.left_nuclease or self.config.nuclease,
            "--right-nuclease",
            self.config.right_nuclease or self.config.nuclease,
            "--left-tnpb-subtype",
            self.config.left_tnpb_subtype or self.config.tnpb_subtype,
            "--right-tnpb-subtype",
            self.config.right_tnpb_subtype or self.config.tnpb_subtype,
            "--left-preset",
            self.config.left_preset or self.config.preset,
            "--right-preset",
            self.config.right_preset or self.config.preset,
            "--left-off-target-model",
            self.config.left_off_target_model or self.config.off_target_model,
            "--right-off-target-model",
            self.config.right_off_target_model or self.config.off_target_model,
            "--left-on-target-model",
            self.config.left_on_target_model or self.config.on_target_model,
            "--right-on-target-model",
            self.config.right_on_target_model or self.config.on_target_model,
            "--left-reference-only-model",
            self.config.left_reference_only_model or self.config.reference_only_model,
            "--right-reference-only-model",
            self.config.right_reference_only_model or self.config.reference_only_model,
        ])
        command.extend(self._common_score_flags())
        command.extend(self._crispai_flags())
        command.extend(self._memory_limit_flags())
        command.extend(self._timeout_flags())
        return command

    def _y_sort_command(self, scores: str, output: str) -> List[str]:
        left_distance = self.spec.left_max_distance
        right_distance = self.spec.right_max_distance
        if left_distance is None or right_distance is None:
            raise ValueError("y_centered_motifs requires distance ranges")
        return [
            self._py(),
            self._script(
                os.path.join("Target_xbp_Y_zbp_Target", "sort_by_distance.py")
            ),
            scores,
            output,
            "--best_left",
            str(left_distance),
            "--best_right",
            str(right_distance),
            "--left-min-distance",
            str(self.spec.left_min_distance),
            "--left-max-distance",
            str(left_distance),
            "--right-min-distance",
            str(self.spec.right_min_distance),
            "--right-max-distance",
            str(right_distance),
            "--left-nuclease",
            self.config.left_nuclease or self.config.nuclease,
            "--right-nuclease",
            self.config.right_nuclease or self.config.nuclease,
            "--pair-rank-policy",
            self._pair_rank_policy_file(),
        ]

    def _common_score_flags(self, include_exact: bool = True) -> List[str]:
        flags: List[str] = []
        if self.config.filter_hard:
            flags.append("--filter-hard")
        if self.config.unique_guides:
            flags.append("--unique-guides")
        if self.config.annotation:
            flags.extend(["--annotation", self.config.annotation])
        if self.config.xlsx:
            flags.append("--xlsx")
        if include_exact and self.config.exact_offtarget:
            flags.append("--exact-offtarget")
        return flags

    def _crispai_flags(self) -> List[str]:
        """Return [--crispai] when the config asks for crispAI columns."""
        return ["--crispai"] if getattr(self.config, "crispai", False) else []

    def _required_motif(self, motif: Optional[MotifSpec]) -> MotifSpec:
        if motif is None:
            raise ValueError("pattern requires a motif component")
        return motif

    def _pam_settings(self):
        if self.config.mode == "preset":
            preset = get_preset(self.config.preset)
            if preset.get("pam_required") and preset.get("pam"):
                return (preset["pam"], preset.get("pam_side") or "3prime", True)
            if preset.get("pam"):
                return (preset["pam"], preset.get("pam_side") or "", False)
            return ("", "", False)
        mode = normalize_pam_mode(
            self.config.pam_mode, self.config.pam_motif)
        motif = pam_motif_for_mode(mode, self.config.pam_motif)
        return motif, self.config.pam_side, self.config.require_pam

    def _side_pam_settings(self, side):
        """Return (motif, side, require) for one TAM side.

        Per-side fields override the global PAM fields when present; otherwise
        the single/global PAM settings continue to apply for compatibility
        with existing direct CLI callers of the complex scoring scripts.
        """
        motif = getattr(self.config, f"{side}_pam_motif", None)
        pam_side = getattr(self.config, f"{side}_pam_side", None)
        require = getattr(self.config, f"{side}_require_pam", None)
        default_motif, default_side, default_require = self._pam_settings()
        return (
            motif if motif is not None else default_motif,
            pam_side if pam_side is not None else default_side,
            bool(require if require is not None else default_require),
        )

    def _search_fasta(self) -> str:
        if (self.config.regions or "").strip():
            return self._build_window_fasta()
        path = (self.config.search_fasta or "").strip()
        if not path:
            raise ValueError("RunnerConfig.search_fasta is required")
        return path

    def _build_window_fasta(self) -> str:
        """Extract each BED region's genomic window into a temporary FASTA."""
        regions_path = (self.config.regions or "").strip()
        genome = (self.config.genome_fasta or "").strip()
        if not regions_path:
            raise ValueError("RunnerConfig.regions is required")
        if not os.path.isfile(regions_path):
            raise ValueError("Regions file not found: %s" % regions_path)
        if not genome:
            raise ValueError("RunnerConfig.genome_fasta is required for BED input")
        if not os.path.isfile(genome):
            raise ValueError("Genome FASTA not found: %s" % genome)
        if self._window_fasta and os.path.isfile(self._window_fasta):
            return self._window_fasta
        from design.library_utils import extract_region_sequences, load_regions
        regions = load_regions(regions_path)
        if not regions:
            raise ValueError("No valid regions in %s" % regions_path)
        windows = extract_region_sequences(genome, regions, pad=0)
        out = os.path.join(self._outdir(), "bed_windows.fa")
        with open(out, "w", encoding="utf-8") as handle:
            for win in windows:
                rid = "%s:%s-%s:%s:%s" % (
                    win["seq_id"], win["start"], win["end"],
                    win.get("strand", "+"), win["region"],
                )
                handle.write(">%s\n%s\n" % (rid, win["sequence"]))
        self._window_fasta = out
        return out

    def _genome_fasta(self) -> str:
        path = (self.config.genome_fasta or "").strip()
        if not path:
            raise ValueError("RunnerConfig.genome_fasta is required")
        return path

    def _mask_fasta(self) -> str:
        return (self.config.mask_fasta or "").strip()

    def resolved_max_memory_mb(self) -> int:
        """Resolve the command-line memory limit for this run."""
        mode = (self.config.max_memory_mode or "auto").strip().lower()
        if mode == "unlimited":
            return 0
        if mode == "custom":
            try:
                value = int(self.config.max_memory_mb)
            except (TypeError, ValueError):
                raise ValueError(
                    "Custom memory limit must be an integer MiB value")
            if value < 512:
                raise ValueError(
                    "Custom memory limit must be at least 512 MiB")
            return value
        if mode != "auto":
            raise ValueError("Unknown memory limit mode: %s" % mode)
        if self.config.max_memory_mb is not None:
            value = int(self.config.max_memory_mb)
            if value <= 0:
                raise ValueError(
                    "Auto memory limit resolved to an invalid value")
            return value
        from utils.system_memory import (
            available_memory_mb,
            resolve_auto_limit_mb,
            total_physical_mb,
        )
        value = resolve_auto_limit_mb(
            total_physical_mb(), available_memory_mb())
        if value <= 0:
            raise ValueError(
                "Cannot resolve Auto memory limit for this execution host")
        return value

    def _memory_limit_flags(self) -> List[str]:
        return [
            "--max-memory-mb",
            str(self.resolved_max_memory_mb()),
        ]

    def _timeout_flags(self) -> List[str]:
        """Opt-in wall-clock limit for the off-target search step."""
        if not self.config.timeout_s:
            return []
        return ["--timeout-s", str(self.config.timeout_s)]

    def _pair_rank_policy_file(self) -> str:
        policy = self.config.pair_rank_policy
        if not policy:
            raise ValueError("pair_rank_policy is required for paired designs")
        path = os.path.join(self._outdir(), "pair_rank_policy.json")
        return write_pair_rank_policy_file(path, policy)

    def stop(self) -> None:
        """Stop the running pipeline and tear down its child process tree."""
        self._stop_requested = True
        with self._proc_lock:
            proc = self._current_proc
        if proc is not None:
            terminate_process_tree(proc)

    def _register_process(self, proc) -> None:
        with self._proc_lock:
            self._current_proc = proc
        register_child(proc)

    def _release_process(self, proc) -> None:
        unregister_child(proc)
        with self._proc_lock:
            if self._current_proc is proc:
                self._current_proc = None

    def run_pipeline(
        self,
        on_line: Optional[Callable[[str], None]] = None,
        start: int = 0,
        end: Optional[int] = None,
        on_prompt: Optional[Callable[[Dict[str, str]], bool]] = None,
    ) -> int:
        steps = self.build_pipeline()[start:end]
        child_env = python_fallback_env()
        self._stop_requested = False
        for step in steps:
            if self._stop_requested:
                return STOPPED_RETURN_CODE
            if on_line:
                on_line(f"[{step.name}] {' '.join(step.command)}")
            proc = subprocess.Popen(
                step.command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=child_env,
                **popen_kwargs()
            )
            self._register_process(proc)
            try:
                assert proc.stdout is not None
                for raw_line in proc.stdout:
                    line = raw_line.rstrip()
                    request = parse_confirm_request(line)
                    if request is not None:
                        self._answer_confirm_request(
                            proc, request, on_prompt, on_line)
                    if on_line:
                        on_line(line)
                _close_child_stdin(proc)
                returncode = proc.wait()
            finally:
                self._release_process(proc)
                # A stopped or failed step must not leave descendants behind.
                terminate_process_tree(proc)
                _close_child_stdout(proc)
            if self._stop_requested:
                return STOPPED_RETURN_CODE
            if returncode != 0:
                return returncode
        if start > 0 or any(
                "score" in step.name or "sort" in step.name
                for step in steps):
            self._finalize_labeled_outputs()
        return 0

    def _answer_confirm_request(
        self,
        proc,
        request: Dict[str, str],
        on_prompt: Optional[Callable[[Dict[str, str]], bool]],
        on_line: Optional[Callable[[str], None]],
    ) -> None:
        """Answer a child confirmation request; the default answer is no."""
        approved = False
        if on_prompt is not None:
            try:
                approved = bool(on_prompt(request))
            except Exception as exc:
                if on_line:
                    on_line(
                        "Confirmation handler failed (%s); answering no." % exc
                    )
            else:
                if on_line:
                    on_line("Confirmation request answered by the front-end.")
        elif on_line:
            on_line("No confirmation handler available; answering no.")
        _write_child_stdin(proc, "yes\n" if approved else "no\n")

    def read_extract_candidates(self) -> List[Dict[str, Any]]:
        if self.spec.kind is PatternKind.SINGLE_MOTIF_FLANK:
            return self._read_single_candidates()
        if self.spec.kind is PatternKind.MOTIF_GAP_MOTIF:
            return self._read_gap_candidates()
        return self._read_y_candidates()

    def _read_single_candidates(self) -> List[Dict[str, Any]]:
        path = self.extract_output_path()
        if not os.path.isfile(path):
            return []
        rows: List[Dict[str, Any]] = []
        with open(path, "r", encoding="utf-8") as handle:
            lines = handle.readlines()
        data_start = 1 if lines and lines[0].startswith("#") else 0
        if data_start >= len(lines):
            return []
        reader = csv.DictReader(
            lines[data_start:],
            delimiter="\t",
        )
        for row in reader:
            query_seq = row.get("sequence", "")
            try:
                positions = json.loads(row.get("positions", "[]"))
            except json.JSONDecodeError:
                positions = []
            for position in positions:
                if len(position) < 3:
                    continue
                seq_id, strand, start = position[:3]
                rows.append({
                    "query_id": row.get("qid", ""),
                    "query_seq": query_seq,
                    "seq_id": seq_id,
                    "strand": strand,
                    "start": str(int(start) + 1),
                    "end": str(int(start) + len(query_seq)),
                    "positions_json": row.get("positions", ""),
                })
        return rows

    def _read_gap_candidates(self) -> List[Dict[str, Any]]:
        path = self.extract_output_path()
        if not os.path.isfile(path):
            return []
        query_sidecar = os.path.splitext(path)[0] + ".queries.fa"
        seq_by_qid = {}
        if os.path.isfile(query_sidecar):
            from Bio import SeqIO
            with open(query_sidecar, "r", encoding="utf-8") as handle:
                for record in SeqIO.parse(handle, "fasta"):
                    seq_by_qid[record.id] = str(record.seq)
        with open(path, "r", encoding="utf-8") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            rows = []
            for raw in reader:
                row = dict(raw)
                if not row.get("query_seq"):
                    row["query_seq"] = seq_by_qid.get(row.get("qid"), "")
                rows.append(row)
            return rows

    def _read_y_candidates(self) -> List[Dict[str, Any]]:
        occurrence_dir = self.extract_output_path()
        info_path = os.path.join(occurrence_dir, "occurrence_info.tsv")
        if not os.path.isfile(info_path):
            return []

        occurrences: Dict[str, Dict[str, Any]] = {}
        with open(info_path, "r", encoding="utf-8") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            for row in reader:
                occurrences[row["occurrence"]] = row

        rows: List[Dict[str, Any]] = []
        for occurrence_id, info in occurrences.items():
            for side in ("left", "right"):
                path = os.path.join(
                    occurrence_dir,
                    f"{side}_occurrence_{occurrence_id}.tsv",
                )
                if not os.path.isfile(path):
                    continue
                with open(path, "r", encoding="utf-8") as handle:
                    lines = handle.readlines()
                data_start = 1 if lines and lines[0].startswith("#") else 0
                if data_start >= len(lines):
                    continue
                reader = csv.DictReader(
                    lines[data_start:],
                    delimiter="\t",
                )
                for row in reader:
                    query_seq = row.get("sequence", "")
                    try:
                        positions = json.loads(row.get("positions", "[]"))
                    except json.JSONDecodeError:
                        positions = []
                    for position in positions:
                        if len(position) < 3:
                            continue
                        seq_id, strand, start = position[:3]
                        rows.append({
                            "occurrence": occurrence_id,
                            "y_sequence": self.spec.y_sequence,
                            "side": side,
                            "query_id": row.get("qid", ""),
                            "query_seq": query_seq,
                            "seq_id": seq_id,
                            "strand": strand,
                            "start": str(int(start) + 1),
                            "end": str(int(start) + len(query_seq)),
                            "positions_json": row.get("positions", ""),
                            "chrom": info.get("chrom", ""),
                            "y_start": info.get("y_start", ""),
                            "y_end": info.get("y_end", ""),
                            "y_strand": info.get("strand", ""),
                        })
        return rows
