"""Reference implementations of benchmark-level score reductions."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any


LEGACY_ERROR_CAPS = {
    "surface_pressure_rel_l2": 15.0,
    "surface_wall_shear_rel_l2": 20.0,
    "volume_velocity_rel_l2": 12.0,
    "volume_pressure_rel_l2": 15.0,
}
LEGACY_ERROR_WEIGHTS = {
    "surface_pressure_rel_l2": 0.15,
    "surface_wall_shear_rel_l2": 0.10,
    "volume_velocity_rel_l2": 0.15,
    "volume_pressure_rel_l2": 0.10,
}

LEGACY_ERROR_ALIASES = {
    "volume_velocity_rel_l2": ("volume_velocity_rel_l2", "flow_domain_velocity_rel_l2"),
    "volume_pressure_rel_l2": ("volume_pressure_rel_l2", "flow_domain_pressure_rel_l2"),
}


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def arithmetic_mean(values: Mapping[str, float], metric_ids: Sequence[str]) -> float:
    """Return the unweighted mean of the named component metrics."""

    if not metric_ids:
        raise ValueError("at least one source metric is required")
    return sum(float(values[metric_id]) for metric_id in metric_ids) / len(metric_ids)


def composite_overall_score(values: Mapping[str, float], declaration: Mapping[str, Any]) -> float:
    """Evaluate a dataset-declared, weighted 0--100 composite score.

    ``bounded_error`` components convert an error ``e`` with published cap
    ``c`` to ``clip(100 * (1 - e / c), 0, 100)``. ``bounded_quality``
    components convert a quality value such as R2 to
    ``100 * clip(q, 0, 1)``. Component weights must be non-negative and sum
    to one.
    """

    if declaration.get("operation") != "weighted_component_scores":
        raise ValueError("unsupported overall-score composite operation")
    components = declaration.get("components")
    if not isinstance(components, Sequence) or isinstance(components, (str, bytes)) or not components:
        raise ValueError("overall-score composite requires at least one component")

    weighted_score = 0.0
    weight_sum = 0.0
    seen_metric_ids: set[str] = set()
    for component in components:
        if not isinstance(component, Mapping):
            raise ValueError("overall-score components must be objects")
        metric_id = component.get("metric_id")
        if not isinstance(metric_id, str) or not metric_id or metric_id in seen_metric_ids:
            raise ValueError("overall-score component metric IDs must be non-empty and unique")
        seen_metric_ids.add(metric_id)
        weight = float(component.get("weight"))
        if not math.isfinite(weight) or weight < 0.0:
            raise ValueError("overall-score component weights must be finite and non-negative")
        source_value = float(values[metric_id])
        if not math.isfinite(source_value):
            raise ValueError("overall-score component values must be finite")

        transform = component.get("transform")
        if transform == "bounded_error":
            cap = float(component.get("cap"))
            if not math.isfinite(cap) or cap <= 0.0:
                raise ValueError("bounded-error components require a finite positive cap")
            component_score = _clamp(100.0 * (1.0 - source_value / cap), 0.0, 100.0)
        elif transform == "bounded_quality":
            if "cap" in component:
                raise ValueError("bounded-quality components must not declare an error cap")
            component_score = 100.0 * _clamp(source_value, 0.0, 1.0)
        else:
            raise ValueError("unsupported overall-score component transform")
        weighted_score += weight * component_score
        weight_sum += weight

    if not math.isclose(weight_sum, 1.0, rel_tol=0.0, abs_tol=1e-12):
        raise ValueError("overall-score component weights must sum to one")
    return _clamp(weighted_score, 0.0, 100.0)


def _legacy_error_value(values: Mapping[str, float], metric_id: str) -> float:
    aliases = LEGACY_ERROR_ALIASES.get(metric_id, (metric_id,))
    matches = [alias for alias in aliases if alias in values]
    if len(matches) != 1:
        raise KeyError(f"expected exactly one of: {', '.join(aliases)}")
    return float(values[matches[0]])


def legacy_aero_scores(values: Mapping[str, float]) -> dict[str, float]:
    """Return the four scores used by the prototype external-aero datasets."""

    field_score = sum(
        LEGACY_ERROR_WEIGHTS[metric_id]
        * _clamp(100.0 * (1.0 - _legacy_error_value(values, metric_id) / LEGACY_ERROR_CAPS[metric_id]), 0.0, 100.0)
        for metric_id in LEGACY_ERROR_WEIGHTS
    ) / 0.5
    force_score = (
        0.15 * _clamp(float(values["cd_r2"]), 0.0, 1.0) * 100.0
        + 0.10 * _clamp(float(values["cl_r2"]), 0.0, 1.0) * 100.0
    ) / 0.25
    profile_score = (
        0.15 * _clamp(float(values["velocity_profile_r2"]), 0.0, 1.0) * 100.0
        + 0.10 * _clamp(float(values["cp_cut_r2"]), 0.0, 1.0) * 100.0
    ) / 0.25
    return {
        "field_score": field_score,
        "force_score": force_score,
        "diagnostic_score": profile_score,
        "overall_score": 0.5 * field_score + 0.25 * force_score + 0.25 * profile_score,
    }
