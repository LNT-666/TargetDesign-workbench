"""Adapters between scored guide rows and prediction-only PairRank inputs."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping

from scoring.pair_ranking import (
    PREDICTION_ONLY_OUTPUT_FIELDS,
    normalize_pair_rank_policy,
)


_PAIR_RANK_FIELDS = tuple(PREDICTION_ONLY_OUTPUT_FIELDS)


def _get(row, key, default=None):
    if isinstance(row, Mapping):
        return row.get(key, default)
    return getattr(row, key, default)


def _as_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in ("1", "true", "yes", "y", "on"):
            return True
        if normalized in ("0", "false", "no", "n", "off", ""):
            return False
    return bool(value)


def _as_float(value):
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _as_text(value):
    if value is None:
        return ""
    return str(value).strip().lower()


def _is_fallback_model(model_name):
    text = _as_text(model_name)
    if not text:
        return False
    return (
        text in ("heuristic", "no_matches", "no_flank", "unavailable")
        or text.endswith("_fallback")
        or text.endswith("_unavailable")
        or "_fallback_" in text
        or "_unavailable_" in text
    )


def _is_reference_model(model_name):
    return "reference_only" in _as_text(model_name)


def _warning_list(value):
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    try:
        return list(value)
    except TypeError:
        return [value]


def _side_reference_only(row, side):
    value = _get(row, "%s_reference_only" % side, None)
    if value is None:
        value = _get(row, "reference_only", False)
    return _as_bool(value)


def _side_valid(row, side, default=True):
    explicit = _get(row, "%s_valid" % side, None)
    if explicit is not None:
        return _as_bool(explicit)

    marker = object()
    for key in (
        "%s_guide_seq" % side,
        "%s_flank_seq" % side,
        "%s_sequence" % side,
    ):
        value = _get(row, key, marker)
        if value is marker or value is None:
            continue
        if not str(value).strip():
            return False
    return bool(default)


def load_pair_rank_policy_file(path):
    """Load and validate a JSON PairRank policy file."""
    with open(path, "r", encoding="utf-8") as handle:
        return normalize_pair_rank_policy(json.load(handle))


def write_pair_rank_policy_file(path, policy):
    """Write a normalized PairRank policy JSON file."""
    normalized = normalize_pair_rank_policy(policy)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(normalized, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return path


def pair_id_for_row(row, fallback="pair"):
    """Return the stable pair identifier used by PairRank."""
    for key in ("pair_id", "pos_id", "occurrence", "qid"):
        value = _get(row, key, None)
        if value is not None and str(value).strip():
            return str(value).strip()
    return str(fallback)


def _model_suffixes(row, side):
    prefixes = (
        "%s_on_target_score_" % side,
        "on_target_score_",
    )
    suffixes = []
    for key in row:
        for prefix in prefixes:
            if key.startswith(prefix):
                suffix = key[len(prefix):]
                if suffix and suffix not in suffixes:
                    suffixes.append(suffix)
                break
    return suffixes


def collect_on_target_models(row, side):
    """Convert scored on-target model columns to PairRank model records."""
    suffixes = _model_suffixes(row, side)
    records = []
    calibration_status = str(
        _get(row, "%s_calibration_status" % side)
        or _get(row, "calibration_status", "")
        or ""
    ).strip().lower()
    side_reference = _side_reference_only(row, side)

    if not suffixes:
        score = _as_float(_get(row, "%s_on_target_score" % side))
        if score is None:
            score = _as_float(_get(row, "on_target_score"))
        if score is not None:
            model_name = (
                _get(row, "%s_on_target_model" % side)
                or _get(row, "on_target_model", "primary")
            )
            is_fallback = _is_fallback_model(model_name)
            reference_only = (
                side_reference or _is_reference_model(model_name)
            )
            records.append({
                "name": str(model_name).strip() or "primary",
                "score": score,
                "applicable": True,
                "calibrated": (
                    calibration_status == "calibrated_reference"
                    and not is_fallback
                    and not reference_only
                ),
                "is_fallback": is_fallback,
                "reference_only": reference_only,
            })
        return records

    for suffix in suffixes:
        score_key = "%s_on_target_score_%s" % (side, suffix)
        if score_key not in row:
            score_key = "on_target_score_%s" % suffix
        score = _as_float(_get(row, score_key))
        if score is None:
            continue
        model_name = (
            _get(row, "%s_on_target_model_%s" % (side, suffix))
            or _get(row, "on_target_model_%s" % suffix)
            or suffix
        )
        is_fallback = _is_fallback_model(model_name)
        reference_only = (
            side_reference
            or _is_reference_model(model_name)
        )
        records.append({
            "name": suffix,
            "score": score,
            "applicable": True,
            "calibrated": (
                calibration_status == "calibrated_reference"
                and not is_fallback
                and not reference_only
            ),
            "is_fallback": is_fallback,
            "reference_only": reference_only,
        })
    return records


def build_side_input(row, side, off_hits=None, search_complete=True,
                     valid=True):
    """Build a ``GuideSideInput`` mapping from a scored row."""
    if row is None:
        return {
            "valid": False,
            "search_complete": False,
            "on_models": [],
            "off_hits": [],
            "aggregate_specificity": None,
        }

    if off_hits is None:
        off_hits = []
    aggregate = None
    if not off_hits:
        aggregate = _as_float(_get(row, "%s_off_target_specificity" % side))
        if aggregate is None:
            aggregate = _as_float(_get(row, "off_target_specificity"))

    return {
        "valid": _side_valid(row, side, default=valid),
        "search_complete": _as_bool(
            _get(row, "%s_search_complete" % side, search_complete),
            search_complete,
        ),
        "on_models": collect_on_target_models(row, side),
        "off_hits": [dict(hit) for hit in off_hits],
        "aggregate_specificity": aggregate,
    }


def build_pair_input(pair_id, left_row, right_row, left_off_hits=None,
                     right_off_hits=None, hard_fail=False,
                     soft_warnings=None, search_complete=None,
                     compatibility=None):
    """Build a ``PairInput`` mapping for two scored side rows."""
    side_search_complete = True if search_complete is None else search_complete
    left = build_side_input(
        left_row, "left", off_hits=left_off_hits,
        search_complete=side_search_complete,
        valid=left_row is not None,
    )
    right = build_side_input(
        right_row, "right", off_hits=right_off_hits,
        search_complete=side_search_complete,
        valid=right_row is not None,
    )
    pair_complete = (
        left["search_complete"] and right["search_complete"]
        if search_complete is None
        else bool(search_complete)
        and left["search_complete"]
        and right["search_complete"]
    )
    compatibility = compatibility or {}
    hard_fail = bool(hard_fail) or _as_bool(
        _get(compatibility, "hard_fail", False)
    )
    warnings = list(_warning_list(soft_warnings))
    warnings.extend(_warning_list(
        _get(compatibility, "soft_warnings", None)
    ))
    return {
        "pair_id": str(pair_id),
        "left": left,
        "right": right,
        "compatibility": {
            "hard_fail": hard_fail,
            "soft_warnings": warnings,
        },
        "search_complete": pair_complete,
    }


def build_pair_compatibility(
        left_row, right_row, hard_fail=False, soft_warnings=None,
        left_nuclease=None, right_nuclease=None,
        gap_min=None, gap_max=None,
        expected_left_side=None, expected_right_side=None,
        left_distance_range=None, right_distance_range=None,
        require_same_locus=False, require_same_strand=False):
    """Build PairRank compatibility flags from observed pair data."""
    hard_reasons = []
    warnings = list(_warning_list(soft_warnings))
    if hard_fail:
        hard_reasons.append("explicit_hard_fail")
    if left_row is None:
        hard_reasons.append("missing_side:left")
    if right_row is None:
        hard_reasons.append("missing_side:right")

    actual_left_nuclease = _get(
        left_row, "left_nuclease", _get(left_row, "nuclease", None)
    )
    actual_right_nuclease = _get(
        right_row, "right_nuclease", _get(right_row, "nuclease", None)
    )
    left_nuclease_text = _as_text(actual_left_nuclease)
    right_nuclease_text = _as_text(actual_right_nuclease)
    if (
        left_nuclease_text
        and right_nuclease_text
        and left_nuclease_text != right_nuclease_text
    ):
        warnings.append(
            "nuclease_mismatch:left_right:%s:%s"
            % (left_nuclease_text, right_nuclease_text)
        )
    for side, expected, actual in (
        ("left", left_nuclease, left_nuclease_text),
        ("right", right_nuclease, right_nuclease_text),
    ):
        expected_text = _as_text(expected)
        if expected_text and actual and expected_text != actual:
            warnings.append(
                "nuclease_mismatch:%s:%s:%s"
                % (side, expected_text, actual)
            )

    if gap_min is not None or gap_max is not None:
        gap = _as_float(_get(left_row, "gap", _get(right_row, "gap", None)))
        if gap is None:
            hard_reasons.append("gap_missing")
        elif gap_min is not None and gap < float(gap_min):
            hard_reasons.append("gap_below_min:%s" % gap)
        elif gap_max is not None and gap > float(gap_max):
            hard_reasons.append("gap_above_max:%s" % gap)

    for side, expected in (
        ("left", expected_left_side),
        ("right", expected_right_side),
    ):
        expected_text = _as_text(expected)
        if not expected_text:
            continue
        actual_text = _as_text(_get(
            left_row if side == "left" else right_row,
            "%s_side" % side,
            None,
        ))
        if actual_text != expected_text:
            hard_reasons.append(
                "direction_mismatch:%s:%s:%s"
                % (side, expected_text, actual_text or "missing")
            )

    for side, row in (("left", left_row), ("right", right_row)):
        strand = _get(row, "%s_strand" % side, None)
        if strand is not None and _as_text(strand) not in ("plus", "minus"):
            hard_reasons.append(
                "invalid_strand:%s:%s" % (side, _as_text(strand))
            )

    for side, row, distance_range in (
        ("left", left_row, left_distance_range),
        ("right", right_row, right_distance_range),
    ):
        if distance_range is None:
            continue
        minimum, maximum = distance_range
        distance = _as_float(_get(row, "distance", None))
        if distance is None:
            hard_reasons.append("distance_missing:%s" % side)
            continue
        if minimum is not None and distance < float(minimum):
            hard_reasons.append(
                "distance_below_min:%s:%s" % (side, distance)
            )
        if maximum is not None and distance > float(maximum):
            hard_reasons.append(
                "distance_above_max:%s:%s" % (side, distance)
            )

    if require_same_locus and left_row is not None and right_row is not None:
        for key in ("y_chrom", "y_start", "y_end"):
            left_value = _get(left_row, key, None)
            right_value = _get(right_row, key, None)
            if left_value is not None and right_value is not None:
                if str(left_value) != str(right_value):
                    hard_reasons.append("locus_mismatch:%s" % key)
                    break

    if require_same_strand and left_row is not None and right_row is not None:
        left_strand = _as_text(_get(left_row, "y_strand", None))
        right_strand = _as_text(_get(right_row, "y_strand", None))
        if left_strand and right_strand and left_strand != right_strand:
            hard_reasons.append(
                "strand_mismatch:%s:%s" % (left_strand, right_strand)
            )

    return {
        "hard_fail": bool(hard_reasons),
        "soft_warnings": warnings,
        "hard_reasons": hard_reasons,
    }


def format_pair_rank_value(value):
    """Return a TSV-friendly representation of a PairRank output value."""
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return ";".join(str(item) for item in value)
    return value


def apply_pair_rank_outputs(rows, ranked_rows, pair_id_getter=None):
    """Attach PairRank outputs to rows and return rows in ranked group order."""
    getter = pair_id_getter or pair_id_for_row
    output_by_id = {
        str(row["pair_id"]): row
        for row in ranked_rows
    }
    grouped = {}
    for index, row in enumerate(rows):
        pair_id = str(getter(row, index))
        grouped.setdefault(pair_id, []).append(row)
        output = output_by_id.get(pair_id)
        if output is None:
            continue
        for field in _PAIR_RANK_FIELDS:
            row[field] = format_pair_rank_value(output.get(field))
        row["conditional_rank"] = format_pair_rank_value(
            output.get("conditional_rank")
        )
        row["_pair_rank_status_order"] = {
            "pass": 0,
            "conditional": 1,
            "rejected": 2,
        }.get(output.get("pair_rank_status"), 3)
        row["_pair_rank_output_order"] = index

    order = {}
    for index, output in enumerate(ranked_rows):
        order[str(output["pair_id"])] = index
    for pair_id in grouped:
        for row in grouped[pair_id]:
            row["_pair_rank_output_order"] = order.get(pair_id, len(order))
    return sorted(
        rows,
        key=lambda row: (
            row.get("_pair_rank_status_order", 3),
            row.get("_pair_rank_output_order", 0),
        ),
    )


__all__ = [
    "apply_pair_rank_outputs",
    "build_pair_compatibility",
    "build_pair_input",
    "build_side_input",
    "collect_on_target_models",
    "format_pair_rank_value",
    "load_pair_rank_policy_file",
    "pair_id_for_row",
    "write_pair_rank_policy_file",
]
