"""Reference implementations of benchmark-level score reductions."""

from __future__ import annotations

from collections.abc import Mapping, Sequence


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


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def arithmetic_mean(values: Mapping[str, float], metric_ids: Sequence[str]) -> float:
    """Return the unweighted mean of the named component metrics."""

    if not metric_ids:
        raise ValueError("at least one source metric is required")
    return sum(float(values[metric_id]) for metric_id in metric_ids) / len(metric_ids)


def legacy_aero_scores(values: Mapping[str, float]) -> dict[str, float]:
    """Return the four scores used by the prototype external-aero datasets."""

    field_score = sum(
        LEGACY_ERROR_WEIGHTS[metric_id]
        * _clamp(100.0 * (1.0 - float(values[metric_id]) / LEGACY_ERROR_CAPS[metric_id]), 0.0, 100.0)
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
