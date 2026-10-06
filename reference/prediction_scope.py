"""Shared scope rules for the external aerodynamic benchmarks.

Unavailable predictions have no raw metric. Their original composite weights
remain in place and contribute zero; surface-only scores are never rescaled.
"""

SURFACE_ONLY_DATASETS = frozenset({"drivaerml", "ahmedml", "windsorml", "hiliftaeroml"})
UNAVAILABLE_COMPONENTS = frozenset(
    {
        "volume_velocity_rel_l2",
        "volume_pressure_rel_l2",
        "velocity_profile_r2",
    }
)


def prediction_scope(value="surface_and_volume"):
    if value not in {"surface_and_volume", "surface_only"}:
        raise ValueError(f"unsupported prediction_scope {value!r}")
    return value


def is_surface_only(submission):
    return (
        submission.get("dataset_id") in SURFACE_ONLY_DATASETS
        and submission.get("prediction_scope") == "surface_only"
    )


def unavailable_metrics(dataset_id, metric_ids):
    if dataset_id == "drivaerml":
        return set(UNAVAILABLE_COMPONENTS)
    return {
        metric_id
        for metric_id in metric_ids
        if metric_id.startswith(("volume_", "velocity_profile_"))
    }


def unavailable_support(support):
    identifier = support.get("id", "")
    metric_ids = [
        binding.get("metric_id", "")
        for binding in support.get("metric_bindings", [])
        if isinstance(binding, dict)
    ]
    return (
        support.get("domain") == "volume"
        or "volume" in identifier
        or (
            bool(metric_ids)
            and all(
                metric_id.startswith(("volume_", "velocity_profile_"))
                for metric_id in metric_ids
            )
        )
    )


def surface_only_implementation_binding(specification):
    """Verify the additive scope implementation without changing old releases."""
    import hashlib
    import json
    from pathlib import Path

    binding = specification.get("scoring_support", {}).get(
        "surface_only_implementation_binding"
    )
    if (
        not isinstance(binding, dict)
        or binding.get("version") != "aerodynamic-surface-only-v1"
    ):
        raise ValueError(
            "surface-only implementation binding is missing or unsupported"
        )
    root = Path(__file__).resolve().parents[1]
    path = root / binding.get("file", "")
    if not path.resolve().is_relative_to(root) or not path.is_file():
        raise ValueError("surface-only implementation manifest is unavailable")
    payload = path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != binding.get("sha256"):
        raise ValueError("surface-only implementation manifest digest differs")
    manifest = json.loads(payload)
    if (
        manifest.get("version") != binding["version"]
        or manifest.get("activation_effect") != "none"
    ):
        raise ValueError("surface-only implementation manifest identity differs")
    for artifact in manifest["artifacts"]:
        source = root / artifact["file"]
        if (
            not source.resolve().is_relative_to(root)
            or hashlib.sha256(source.read_bytes()).hexdigest() != artifact["sha256"]
        ):
            raise ValueError(
                f"surface-only implementation artifact differs: {artifact['file']}"
            )
    return dict(binding)
