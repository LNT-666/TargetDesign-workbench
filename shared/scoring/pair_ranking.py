"""Prediction-only pair ranking for paired guide candidates.

The public entry point is :func:`rank_prediction_only`.  It accepts mappings
with the ``PairInput`` shape and a complete policy mapping, returns rows in
``pass``, ``conditional``, ``rejected`` order, and assigns pair ranks using
competition ranking.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Mapping


PAIR_RANK_POLICY_FIELDS = (
    "e_high",
    "e_min",
    "e_fail",
    "delta_default",
    "b_low",
    "b_high",
    "m_low",
    "m_high",
    "h_risk",
    "h_max",
)

PREDICTION_ONLY_OUTPUT_FIELDS = (
    "pair_id",
    "pair_rank",
    "pair_rank_status",
    "pair_rank_mode",
    "pair_rank_key",
    "pair_activity_tier",
    "left_activity_tier",
    "right_activity_tier",
    "left_eligible_model_count",
    "right_eligible_model_count",
    "pair_offtarget_burden",
    "pair_max_offtarget_upper",
    "pair_high_risk_count",
    "pair_activity_disagreement",
    "pair_compatibility_penalty",
    "pair_gate_reasons",
)

_TIER_VALUE = {"A": 3, "B": 2, "C": 1}
_RISK_STATUS = {0: "pass", 1: "pass", 2: "conditional"}


class PairRankingConfigError(ValueError):
    """Raised when a policy is incomplete or internally inconsistent."""


def _get(value, key, default=None):
    if isinstance(value, Mapping):
        return value.get(key, default)
    return getattr(value, key, default)


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
        return default
    return bool(value)


def _as_float(value, field, *, minimum=None, maximum=None):
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise PairRankingConfigError("%s must be numeric" % field)
    if not math.isfinite(number):
        raise PairRankingConfigError("%s must be finite" % field)
    if minimum is not None and number < minimum:
        raise PairRankingConfigError(
            "%s must be >= %s" % (field, minimum)
        )
    if maximum is not None and number > maximum:
        raise PairRankingConfigError(
            "%s must be <= %s" % (field, maximum)
        )
    return number


def _as_nonnegative_int(value, field):
    number = _as_float(value, field, minimum=0)
    if not number.is_integer():
        raise PairRankingConfigError("%s must be an integer" % field)
    return int(number)


def _items(value, field):
    if value is None:
        return []
    if isinstance(value, (str, bytes, Mapping)):
        raise PairRankingConfigError("%s must be a sequence" % field)
    try:
        return list(value)
    except TypeError:
        raise PairRankingConfigError("%s must be a sequence" % field)


def normalize_pair_rank_policy(policy):
    """Validate and normalize a complete ``pair_rank_policy`` mapping."""
    if policy is None:
        raise PairRankingConfigError("pair_rank_policy is required")
    normalized = {}
    missing = []
    for field in PAIR_RANK_POLICY_FIELDS:
        value = _get(policy, field, None)
        if value is None:
            missing.append(field)
        else:
            normalized[field] = value
    if missing:
        raise PairRankingConfigError(
            "pair_rank_policy is missing: %s" % ", ".join(missing)
        )

    for field in ("e_high", "e_min", "e_fail"):
        normalized[field] = _as_float(
            normalized[field], field, minimum=0.0, maximum=1.0
        )
    normalized["delta_default"] = _as_float(
        normalized["delta_default"], "delta_default", minimum=0.0
    )
    if normalized["delta_default"] == 0:
        raise PairRankingConfigError("delta_default must not be zero")

    for field in ("b_low", "b_high", "m_low", "m_high"):
        normalized[field] = _as_float(
            normalized[field], field, minimum=0.0
        )
    normalized["h_risk"] = _as_float(
        normalized["h_risk"], "h_risk", minimum=0.0, maximum=1.0
    )
    normalized["h_max"] = _as_nonnegative_int(
        normalized["h_max"], "h_max"
    )

    if not (
        normalized["e_fail"]
        <= normalized["e_min"]
        <= normalized["e_high"]
    ):
        raise PairRankingConfigError(
            "policy requires e_fail <= e_min <= e_high"
        )
    if normalized["b_low"] > normalized["b_high"]:
        raise PairRankingConfigError("policy requires b_low <= b_high")
    if normalized["m_low"] > normalized["m_high"]:
        raise PairRankingConfigError("policy requires m_low <= m_high")
    return normalized


def _model_score(model):
    value = _get(model, "score", None)
    if value is None:
        return None
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(score) or score < 0.0 or score > 1.0:
        return None
    return score


def _model_name(model, index):
    name = _get(model, "name", None)
    if name is None:
        return "model_%d" % index
    return str(name).strip().lower() or "model_%d" % index


def _model_flags_allow_ranking(model):
    return (
        _as_bool(_get(model, "applicable", False))
        and not _as_bool(_get(model, "is_fallback", False))
        and not _as_bool(_get(model, "reference_only", False))
    )


def _percentiles(values):
    if not values:
        return {}
    ordered = sorted(values)
    count = len(ordered)
    result = {}
    start = 0
    while start < count:
        end = start + 1
        while end < count and ordered[end] == ordered[start]:
            end += 1
        average_rank = (start + 1 + end) / 2.0
        result[ordered[start]] = average_rank / count
        start = end
    return result


def _build_model_percentiles(pairs):
    scores = defaultdict(list)
    for pair in pairs:
        sides = (_get(pair, "left", None), _get(pair, "right", None))
        for side in sides:
            if side is None:
                continue
            models = _items(_get(side, "on_models", []), "on_models")
            for model in models:
                if not _model_flags_allow_ranking(model):
                    continue
                score = _model_score(model)
                if score is None:
                    continue
                scores[_model_name(model, 0)].append(score)
    return {
        name: _percentiles(model_scores)
        for name, model_scores in scores.items()
        if len(model_scores) >= 2
    }


def _percentile_for(model_name, score, percentiles):
    return (percentiles.get(model_name) or {}).get(score)


def _prepare_models(side, side_name, percentiles):
    rankable = []
    hard_reasons = []
    if side is None:
        return rankable, hard_reasons

    for index, model in enumerate(
        _items(_get(side, "on_models", []), "%s.on_models" % side_name)
    ):
        name = _model_name(model, index)
        applicable = _as_bool(_get(model, "applicable", False))
        is_fallback = _as_bool(_get(model, "is_fallback", False))
        reference_only = _as_bool(_get(model, "reference_only", False))
        if not applicable:
            hard_reasons.append(
                "inapplicable_model:%s:%s" % (side_name, name)
            )
            continue
        if is_fallback:
            hard_reasons.append(
                "fallback_model:%s:%s" % (side_name, name)
            )
            continue
        if reference_only:
            hard_reasons.append(
                "reference_only_model:%s:%s" % (side_name, name)
            )
            continue

        raw_score = _model_score(model)
        if raw_score is None:
            hard_reasons.append(
                "invalid_model_score:%s:%s" % (side_name, name)
            )
            continue

        calibrated = _as_bool(_get(model, "calibrated", False))
        rank_score = raw_score
        if not calibrated:
            rank_score = _percentile_for(name, raw_score, percentiles)
            if rank_score is None:
                continue

        rankable.append({
            "name": name,
            "score": rank_score,
            "calibrated": calibrated,
            "percentile": _percentile_for(name, raw_score, percentiles),
        })
    return rankable, hard_reasons


def _side_activity_tier(models, policy):
    if not models:
        return "C"
    scores = [model["score"] for model in models]
    calibrated_count = sum(
        1 for model in models if model["calibrated"]
    )
    if (
        len(models) >= 2
        and calibrated_count >= 2
        and all(score >= policy["e_high"] for score in scores)
    ):
        return "A"
    if max(scores) >= policy["e_min"]:
        return "B"
    return "C"


def _expected_on_target(hit):
    return (
        _as_bool(_get(hit, "is_expected_on_target", False))
        or _as_bool(_get(hit, "expected_on_target", False))
    )


def _side_risk(side, side_name, policy):
    if side is None:
        return 0.0, 0.0, 0, []

    hits = _items(_get(side, "off_hits", []), "%s.off_hits" % side_name)
    if not hits:
        specificity = _get(side, "aggregate_specificity", None)
        if specificity is None:
            return 0.0, 0.0, 0, []
        specificity = _as_float(
            specificity,
            "%s.aggregate_specificity" % side_name,
            minimum=0.0,
        )
        if specificity <= 0.0:
            return (
                0.0,
                None,
                None,
                ["invalid_aggregate_specificity:%s" % side_name],
            )
        return max(0.0, (1.0 / specificity) - 1.0), None, None, []

    burden = 0.0
    maximum = None
    high_risk = 0
    hard_reasons = []
    for index, hit in enumerate(hits):
        if _expected_on_target(hit):
            continue
        locus = _get(hit, "locus_id", "hit_%d" % index)
        locus = str(locus)
        if _as_bool(_get(hit, "forbidden", False)):
            hard_reasons.append(
                "forbidden_offtarget:%s:%s" % (side_name, locus)
            )
        is_bulge = _as_bool(_get(hit, "is_bulge", False))
        if is_bulge and not _as_bool(
            _get(hit, "bulge_calibrated", False)
        ):
            hard_reasons.append(
                "uncalibrated_bulge:%s:%s" % (side_name, locus)
            )

        upper_value = _get(hit, "upper", None)
        if upper_value is None:
            score = _model_score({"score": _get(hit, "score", None)})
            if score is None:
                hard_reasons.append(
                    "invalid_offtarget_score:%s:%s" % (side_name, locus)
                )
                continue
            upper = min(1.0, score + policy["delta_default"])
        else:
            try:
                upper = float(upper_value)
            except (TypeError, ValueError):
                hard_reasons.append(
                    "invalid_offtarget_upper:%s:%s" % (side_name, locus)
                )
                continue
            if not math.isfinite(upper) or upper < 0.0 or upper > 1.0:
                hard_reasons.append(
                    "invalid_offtarget_upper:%s:%s" % (side_name, locus)
                )
                continue

        burden += upper
        maximum = upper if maximum is None else max(maximum, upper)
        if upper >= policy["h_risk"]:
            high_risk += 1
    if maximum is None:
        maximum = 0.0
    return burden, maximum, high_risk, hard_reasons


def _side_activity_disagreement(models):
    if len(models) < 2:
        return 1.0
    values = [
        model["percentile"]
        for model in models
        if model["percentile"] is not None
    ]
    if len(values) < 2:
        return 1.0
    return max(
        abs(values[first] - values[second])
        for first in range(len(values))
        for second in range(first + 1, len(values))
    )


def _activity_disagreement(left_models, right_models):
    return max(
        _side_activity_disagreement(left_models),
        _side_activity_disagreement(right_models),
    )


def _risk_class(burden, maximum, high_risk, policy):
    if (
        maximum is not None
        and burden <= policy["b_low"]
        and maximum <= policy["m_low"]
        and high_risk == 0
    ):
        return 0
    if (
        burden <= policy["b_high"]
        and (maximum is None or maximum <= policy["m_high"])
        and (high_risk is None or high_risk <= policy["h_max"])
    ):
        return 1
    return 2


def _soft_warning_count(pair):
    compatibility = _get(pair, "compatibility", None)
    warnings = _get(compatibility, "soft_warnings", [])
    if warnings is None:
        return 0
    if isinstance(warnings, str):
        return 1 if warnings.strip() else 0
    try:
        return len(warnings)
    except TypeError:
        return 1


def _evaluate_pair(pair, policy, percentiles):
    pair_id = _get(pair, "pair_id", None)
    if pair_id is None:
        raise PairRankingConfigError("pair_id is required")

    left = _get(pair, "left", None)
    right = _get(pair, "right", None)
    compatibility = _get(pair, "compatibility", None)
    hard_reasons = []
    conditional_reasons = []

    if not _as_bool(_get(pair, "search_complete", False)):
        hard_reasons.append("pair_search_incomplete")
    if not _as_bool(_get(left, "valid", False)):
        hard_reasons.append("left_invalid")
    if not _as_bool(_get(left, "search_complete", False)):
        hard_reasons.append("left_search_incomplete")
    if not _as_bool(_get(right, "valid", False)):
        hard_reasons.append("right_invalid")
    if not _as_bool(_get(right, "search_complete", False)):
        hard_reasons.append("right_search_incomplete")
    if _as_bool(_get(compatibility, "hard_fail", False)):
        hard_reasons.append("compatibility_hard_fail")

    left_burden, left_max, left_high_risk, left_risk_reasons = _side_risk(
        left, "left", policy
    )
    right_burden, right_max, right_high_risk, right_risk_reasons = _side_risk(
        right, "right", policy
    )
    hard_reasons.extend(left_risk_reasons)
    hard_reasons.extend(right_risk_reasons)

    left_models, left_model_reasons = _prepare_models(
        left, "left", percentiles
    )
    right_models, right_model_reasons = _prepare_models(
        right, "right", percentiles
    )
    hard_reasons.extend(left_model_reasons)
    hard_reasons.extend(right_model_reasons)

    left_tier = _side_activity_tier(left_models, policy)
    right_tier = _side_activity_tier(right_models, policy)
    pair_tier = min(
        (left_tier, right_tier),
        key=lambda tier: _TIER_VALUE[tier],
    )

    pair_burden = left_burden + right_burden
    if left_max is None or right_max is None:
        pair_max = None
    else:
        pair_max = max(left_max, right_max)
    if left_high_risk is None or right_high_risk is None:
        pair_high_risk = None
    else:
        pair_high_risk = left_high_risk + right_high_risk

    if pair_tier == "C":
        conditional_reasons.append("tier_c")
    if pair_burden > policy["b_high"]:
        conditional_reasons.append("burden_above_b_high")
    if pair_max is not None and pair_max > policy["m_high"]:
        conditional_reasons.append("max_offtarget_above_m_high")
    if pair_high_risk is not None and pair_high_risk > policy["h_max"]:
        conditional_reasons.append("high_risk_above_h_max")

    risk_class = _risk_class(pair_burden, pair_max, pair_high_risk, policy)
    if risk_class == 2:
        conditional_reasons.append("risk_2")

    if hard_reasons:
        status = "rejected"
    elif conditional_reasons:
        status = "conditional"
    else:
        status = _RISK_STATUS[risk_class]

    disagreement = _activity_disagreement(left_models, right_models)
    compatibility_penalty = _soft_warning_count(pair)
    sort_copy = (
        risk_class,
        -_TIER_VALUE[pair_tier],
        pair_burden,
        math.inf if pair_max is None else pair_max,
        math.inf if pair_high_risk is None else pair_high_risk,
        disagreement,
        compatibility_penalty,
    )

    reasons = hard_reasons + [
        reason
        for reason in conditional_reasons
        if reason not in hard_reasons
    ]
    return {
        "pair_id": pair_id,
        "pair_rank": None,
        "pair_rank_status": status,
        "pair_rank_mode": "prediction_only",
        "pair_rank_key": sort_copy + (pair_id,),
        "pair_activity_tier": pair_tier,
        "left_activity_tier": left_tier,
        "right_activity_tier": right_tier,
        "left_eligible_model_count": len(left_models),
        "right_eligible_model_count": len(right_models),
        "pair_offtarget_burden": pair_burden,
        "pair_max_offtarget_upper": pair_max,
        "pair_high_risk_count": pair_high_risk,
        "pair_activity_disagreement": disagreement,
        "pair_compatibility_penalty": compatibility_penalty,
        "pair_gate_reasons": reasons,
        "conditional_rank": None,
        "_competition_key": sort_copy,
        "_sort_key": sort_copy + (pair_id,),
    }


def _assign_competition_ranks(rows, rank_field):
    ordered = sorted(rows, key=lambda row: row["_sort_key"])
    for index, row in enumerate(ordered, start=1):
        if (
            index > 1
            and row["_competition_key"]
            != ordered[index - 2]["_competition_key"]
        ):
            competition_rank = index
        elif index == 1:
            competition_rank = 1
        else:
            competition_rank = ordered[index - 2][rank_field]
        row[rank_field] = competition_rank
    return ordered


def _public_row(row):
    result = {
        field: row[field]
        for field in PREDICTION_ONLY_OUTPUT_FIELDS
    }
    result["conditional_rank"] = row["conditional_rank"]
    return result


def rank_prediction_only(pairs, pair_rank_policy):
    """Evaluate and rank pair rows using the prediction-only policy.

    ``pairs`` must contain mapping-like ``PairInput`` records.  The returned
    list is ordered as sorted passes, sorted conditionals, then rejected rows
    in input order.  ``pair_rank`` is assigned only to passing rows and
    ``conditional_rank`` only to conditional rows.
    """
    materialized = list(pairs)
    policy = normalize_pair_rank_policy(pair_rank_policy)
    percentiles = _build_model_percentiles(materialized)
    rows = [
        _evaluate_pair(pair, policy, percentiles)
        for pair in materialized
    ]

    pass_rows = [row for row in rows if row["pair_rank_status"] == "pass"]
    conditional_rows = [
        row for row in rows if row["pair_rank_status"] == "conditional"
    ]
    rejected_rows = [
        row for row in rows if row["pair_rank_status"] == "rejected"
    ]
    pass_rows = _assign_competition_ranks(pass_rows, "pair_rank")
    conditional_rows = _assign_competition_ranks(
        conditional_rows, "conditional_rank"
    )
    return [
        _public_row(row)
        for row in pass_rows + conditional_rows + rejected_rows
    ]


__all__ = [
    "PAIR_RANK_POLICY_FIELDS",
    "PREDICTION_ONLY_OUTPUT_FIELDS",
    "PairRankingConfigError",
    "normalize_pair_rank_policy",
    "rank_prediction_only",
]
