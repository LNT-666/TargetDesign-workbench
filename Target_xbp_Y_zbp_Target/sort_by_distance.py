"""Rank Y/ZBP per-side rows as complete pairs with prediction-only PairRank."""

import argparse
import csv
import json
import os
import sys
from collections import defaultdict


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "shared"))

from scoring.pair_ranking import (  # noqa: E402
    PREDICTION_ONLY_OUTPUT_FIELDS,
    rank_prediction_only,
)
from scoring.pair_ranking_adapter import (  # noqa: E402
    apply_pair_rank_outputs,
    build_pair_compatibility,
    build_pair_input,
    load_pair_rank_policy_file,
)


def _int_value(row, key, default=0):
    try:
        return int(float(row.get(key) or default))
    except (TypeError, ValueError):
        return default


def _has_bulge(row):
    if row is None:
        return False
    for key in ("bulge_hits", "scored_bulge_hits", "unscored_bulge_hits"):
        if _int_value(row, key, 0) > 0:
            return True
    return False


def _parse_off_hits(row):
    value = row.get("forbidden_hits")
    if value is None or not str(value).strip():
        return []
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        parsed = None
    if not isinstance(parsed, list):
        parsed = [{
            "locus_id": "invalid_forbidden_hits:" + str(row.get("qid") or ""),
            "score": None,
            "upper": 1.0,
            "forbidden": True,
            "is_bulge": False,
            "bulge_calibrated": False,
        }]
    return [hit for hit in parsed if isinstance(hit, dict)]


def _distance_range(minimum, maximum):
    if minimum is None and maximum is None:
        return None
    return minimum, maximum


def main():
    parser = argparse.ArgumentParser(
        description="Rank complete Y/ZBP occurrences with PairRank"
    )
    parser.add_argument("input", help="Input per-side TSV")
    parser.add_argument("output", nargs="?", help="Output TSV")
    parser.add_argument("--best_left", type=int, default=20,
                        help="Reference left distance used for distance_score")
    parser.add_argument("--best_right", type=int, default=20,
                        help="Reference right distance used for distance_score")
    parser.add_argument("--left-min-distance", type=int, default=None)
    parser.add_argument("--left-max-distance", type=int, default=None)
    parser.add_argument("--right-min-distance", type=int, default=None)
    parser.add_argument("--right-max-distance", type=int, default=None)
    parser.add_argument("--left-nuclease", default=None)
    parser.add_argument("--right-nuclease", default=None)
    parser.add_argument("--pair-rank-policy", required=True,
                        help="JSON file containing pair_rank_policy")
    args = parser.parse_args()

    if not os.path.isfile(args.input):
        print("Error: file not found: %s" % args.input)
        return 2
    policy = load_pair_rank_policy_file(args.pair_rank_policy)

    with open(args.input, "r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        fieldnames = list(reader.fieldnames or [])
        rows = [dict(row) for row in reader]

    grouped = defaultdict(dict)
    for row in rows:
        occurrence = str(row.get("occurrence") or "").strip()
        side = str(row.get("side") or "").strip().lower()
        if occurrence and side in ("left", "right"):
            grouped[occurrence][side] = row

    pair_inputs = []
    for occurrence, sides in grouped.items():
        left_row = sides.get("left")
        right_row = sides.get("right")
        hard_fail = _has_bulge(left_row) or _has_bulge(right_row)
        compatibility = build_pair_compatibility(
            left_row,
            right_row,
            hard_fail=hard_fail,
            left_nuclease=args.left_nuclease,
            right_nuclease=args.right_nuclease,
            left_distance_range=_distance_range(
                args.left_min_distance,
                args.left_max_distance,
            ),
            right_distance_range=_distance_range(
                args.right_min_distance,
                args.right_max_distance,
            ),
            require_same_locus=True,
            require_same_strand=True,
        )
        pair_inputs.append(build_pair_input(
            occurrence,
            left_row,
            right_row,
            left_off_hits=_parse_off_hits(left_row) if left_row else [],
            right_off_hits=_parse_off_hits(right_row) if right_row else [],
            compatibility=compatibility,
        ))

    ranked = rank_prediction_only(pair_inputs, policy)
    ranked_by_id = {str(row["pair_id"]): row for row in ranked}
    rows = apply_pair_rank_outputs(
        rows,
        ranked,
        lambda row, _index: str(row.get("occurrence") or ""),
    )
    for row in rows:
        occurrence = str(row.get("occurrence") or "")
        output = ranked_by_id.get(occurrence, {})
        row["rank"] = (
            output.get("pair_rank")
            if output.get("pair_rank") is not None
            else output.get("conditional_rank", "")
        )
        if row.get("side") == "left":
            distance_score = abs(
                _int_value(row, "distance") - args.best_left
            )
        else:
            distance_score = abs(
                _int_value(row, "distance") - args.best_right
            )
        row["distance_score"] = str(distance_score)

    output_fields = list(fieldnames)
    for field in (
        "rank",
        *PREDICTION_ONLY_OUTPUT_FIELDS,
        "conditional_rank",
        "distance_score",
    ):
        if field not in output_fields:
            output_fields.append(field)

    out_handle = (
        open(args.output, "w", newline="", encoding="utf-8")
        if args.output else sys.stdout
    )
    try:
        writer = csv.DictWriter(
            out_handle,
            fieldnames=output_fields,
            delimiter="\t",
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)
    finally:
        if args.output:
            out_handle.close()
    if args.output:
        print("PairRank results written to %s" % args.output,
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
