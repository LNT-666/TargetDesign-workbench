# Design Pattern Definitions (English)

## 1. Single target design

- PAM/TAM Motif
- Target Length
- Target position to PAM/TAM

## 2. Paired target design pattern A (Target-xbp-Target)

- Left PAM/TAM
- Left target length
- Left target position
  - Relative position of left target to left PAM/TAM
- Minimum distance
  - Minimum distance to left PAM/TAM
- Maximum distance
  - Maximum distance to left PAM/TAM
- Right PAM/TAM
- Right target length
- Right target position
  - Relative position of right target to right PAM/TAM

During candidate extraction the left and right motifs are each matched on
both genomic strands independently, so the `++`, `+-`, `-+`, and `--`
combinations are all considered. Each extracted row records the actual
orientation in `left_strand` and `right_strand`; `strand` is `plus` for the
cross-strand combinations and `minus` only when both motifs are on the
minus strand. Extracted rows also report the left/right target intervals as
0-based half-open `left_target_start/end` and `right_target_start/end`.
`query_seq` and `gap_seq` are not written to the TSV; the assembled query
sequences are kept in a sibling `.queries.fa` sidecar for library export.
Scoring treats the left and right `flank_seq` as separate guides and writes
the two score sets into one candidate row as `left_*` and `right_*` columns.
Rows are ranked as complete pairs by `prediction_only` PairRank. The output
contains PairRank status, risk, gate-reason, and rank fields; the old
`combined_score` and side-rank aggregation have been removed.

## 3. Paired target design pattern B (Target-xbp-Motif-ybp-Target)

- Middle motif (no mismatch) included
- Left PAM/TAM
- Left target length
- Left target position
  - Relative position of left target position to left PAM/TAM
- Minimum distance
  - Minimum distance from the middle motif to left PAM/TAM
- Maximum distance
  - Maximum distance from the middle motif to the left PAM/TAM
- Right PAM/TAM motif
- Right target length
- Right target position
  - Relative position of right target position to right PAM/TAM
- Minimum distance
  - Minimum distance from the middle motif to right PAM/TAM
- Maximum distance
  - Maximum distance from the middle motif to the right PAM/TAM
