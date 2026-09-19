from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class PatternKind(str, Enum):
    SINGLE_MOTIF_FLANK = "single_motif_flank"
    MOTIF_GAP_MOTIF = "motif_gap_motif"
    Y_CENTERED_MOTIFS = "y_centered_motifs"


class Side(str, Enum):
    UPSTREAM = "upstream"
    DOWNSTREAM = "downstream"


_IUPAC_BASES = set("ACGTUNRYSWKMBDHV")


@dataclass(frozen=True)
class MotifSpec:
    sequence: str
    flank_length: int = 0
    side: Side = Side.UPSTREAM

    def __post_init__(self) -> None:
        sequence = (self.sequence or "").strip().upper()
        if not sequence:
            raise ValueError("motif sequence cannot be empty")
        if not set(sequence).issubset(_IUPAC_BASES):
            raise ValueError(f"motif contains unsupported characters: {sequence}")
        if self.flank_length < 0:
            raise ValueError("flank_length must be >= 0")
        if self.side not in (Side.UPSTREAM, Side.DOWNSTREAM):
            raise ValueError(f"unsupported side: {self.side}")
        object.__setattr__(self, "sequence", sequence)


@dataclass
class PatternSpec:
    kind: PatternKind
    motif: Optional[MotifSpec] = None
    left: Optional[MotifSpec] = None
    right: Optional[MotifSpec] = None
    min_gap: Optional[int] = None
    max_gap: Optional[int] = None
    y_sequence: Optional[str] = None
    left_min_distance: Optional[int] = None
    left_max_distance: Optional[int] = None
    right_min_distance: Optional[int] = None
    right_max_distance: Optional[int] = None
    metadata: dict = field(default_factory=dict)

    def validate(self) -> None:
        if self.kind not in PatternKind:
            raise ValueError(f"unsupported pattern kind: {self.kind}")

        if self.kind is PatternKind.SINGLE_MOTIF_FLANK:
            if self.motif is None:
                raise ValueError("single_motif_flank requires motif")
            return

        if self.kind is PatternKind.MOTIF_GAP_MOTIF:
            if self.left is None or self.right is None:
                raise ValueError("motif_gap_motif requires left and right motifs")
            self._validate_distance_range("gap", self.min_gap, self.max_gap)
            return

        if self.kind is PatternKind.Y_CENTERED_MOTIFS:
            y_sequence = (self.y_sequence or "").strip().upper()
            if not y_sequence:
                raise ValueError("y_centered_motifs requires y_sequence")
            if not set(y_sequence).issubset(_IUPAC_BASES):
                raise ValueError(f"y_sequence contains unsupported characters: {y_sequence}")
            object.__setattr__(self, "y_sequence", y_sequence)
            if self.left is None or self.right is None:
                raise ValueError("y_centered_motifs requires left and right motifs")
            self._validate_distance_range(
                "left", self.left_min_distance, self.left_max_distance
            )
            self._validate_distance_range(
                "right", self.right_min_distance, self.right_max_distance
            )
            return

    @staticmethod
    def _validate_distance_range(
        label: str, minimum: Optional[int], maximum: Optional[int]
    ) -> None:
        if minimum is None or maximum is None:
            raise ValueError(f"{label} distance range requires min and max")
        if minimum < 0 or maximum < 0:
            raise ValueError(f"{label} distances must be >= 0")
        if minimum > maximum:
            raise ValueError(f"{label} min distance cannot exceed max distance")

    def describe(self) -> str:
        self.validate()
        if self.kind is PatternKind.SINGLE_MOTIF_FLANK:
            return self._single_description()
        if self.kind is PatternKind.MOTIF_GAP_MOTIF:
            return self._gap_description()
        return self._y_description()

    def _single_description(self) -> str:
        motif = self.motif
        return f"[{motif.side.value} flank {motif.flank_length} bp] + [{motif.sequence}]"

    def _gap_description(self) -> str:
        left = self.left
        right = self.right
        return (
            f"[{left.side.value} flank {left.flank_length} bp][{left.sequence}]"
            f" -- gap[{self.min_gap}-{self.max_gap} bp] -- "
            f"[{right.sequence}][{right.side.value} flank {right.flank_length} bp]"
        )

    def _y_description(self) -> str:
        left = self.left
        right = self.right
        return (
            f"[{left.side.value} flank {left.flank_length} bp][{left.sequence}]"
            f" <-Y({self.y_sequence})-> [{right.sequence}]"
            f"[{right.side.value} flank {right.flank_length} bp]\n"
            f"left distance [{self.left_min_distance}-{self.left_max_distance}] bp; "
            f"right distance [{self.right_min_distance}-{self.right_max_distance}] bp"
        )

    def candidate_columns(self) -> List[str]:
        common = [
            "query_id",
            "seq_id",
            "strand",
            "start",
            "end",
            "query_seq",
        ]
        if self.kind is PatternKind.SINGLE_MOTIF_FLANK:
            return common + [
                "motif_seq",
                "flank_seq",
                "side",
                "flank_length",
            ]
        if self.kind is PatternKind.MOTIF_GAP_MOTIF:
            return common + [
                "left_strand",
                "right_strand",
                "left_motif_seq",
                "right_motif_seq",
                "gap",
                "left_target_start",
                "left_target_end",
                "right_target_start",
                "right_target_end",
                "left_flank_seq",
                "right_flank_seq",
                "left_side",
                "right_side",
            ]
        return common + [
            "y_sequence",
            "left_motif_seq",
            "right_motif_seq",
            "left_distance",
            "right_distance",
            "left_flank_seq",
            "right_flank_seq",
            "left_side",
            "right_side",
        ]
