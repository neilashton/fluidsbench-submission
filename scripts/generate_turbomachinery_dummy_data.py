#!/usr/bin/env python3
"""Generate clearly labelled prototype submissions for dataset-driven feeds."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MODEL_METADATA = {
    "VKI-LS59": ("Transolver", "Transformer", ["Transformer"]),
    "Rotor37": ("MeshGraphNets", "GNN", ["GNN"]),
    "BlendedNet": ("UPT", "Transformer", ["Transformer"]),
}


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def rounded(value: float, digits: int = 5) -> float:
    return round(value, digits)


def profile(
    case_id: str,
    station_id: str,
    quantity_id: str,
    x_key: str,
    y_key: str,
    points: list[tuple[float, float]],
) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "station_id": station_id,
        "quantity_id": quantity_id,
        "values": [{x_key: rounded(x), y_key: rounded(y)} for x, y in points],
    }


def metric_block(
    quantities: list[tuple[str, float]],
    scale: float,
    absolute_scales: dict[str, tuple[float, float]] | None = None,
) -> dict[str, float]:
    values: dict[str, float] = {}
    rrmse_values = []
    for prefix, factor in quantities:
        rrmse = scale * factor
        rel_l2 = rrmse * 100.0 * (1.04 + factor * 0.015)
        values[f"{prefix}_rrmse"] = rounded(rrmse)
        values[f"{prefix}_rel_l2"] = rounded(rel_l2, 3)
        values[f"{prefix}_rel_l1"] = rounded(rel_l2 * (0.69 + 0.015 * factor), 3)
        values[f"{prefix}_r2"] = rounded(max(-0.2, 1.0 - 2.6 * rrmse**1.35), 4)
        rrmse_values.append(rrmse)
        if absolute_scales and prefix in absolute_scales:
            mae_scale, rmse_scale = absolute_scales[prefix]
            values[f"{prefix}_mae"] = rounded(scale * mae_scale, 4)
            values[f"{prefix}_rmse"] = rounded(scale * rmse_scale, 4)
    values["total_error"] = rounded(sum(rrmse_values) / len(rrmse_values))
    return values


def common_submission(dataset: str, split: str, index: int) -> dict[str, Any]:
    slug = dataset.lower().replace("-", "")
    model, model_type, model_types = MODEL_METADATA[dataset]
    return {
        "submission_id": f"{slug}-prototype-{split.replace('_', '-')}",
        "model": model,
        "model_type": model_type,
        "model_types": model_types,
        "training_regime": "from_scratch",
        "target_data_used": "official_train",
        "external_pretraining": False,
        "pretraining_data": [],
        "dataset": dataset,
        "split": split,
        "parameter_count": rounded(6.8 + 0.35 * index, 2),
        "submitter_name": "Neil Ashton",
        "institution": "FluidsBench dummy data",
        "paper_url": "",
        "code_url": "",
        "submitted_at": "2026-07-15",
        "note": "Illustrative dummy result for frontend and submission-pipeline testing. It is not a published benchmark result.",
    }


def vki_diagnostics(case_id: str, offset: float) -> dict[str, Any]:
    x_values = [i / 12 for i in range(13)]
    pressure = [(x, 0.62 + 0.52 * x + 0.08 * math.sin(math.pi * x) + offset) for x in x_values]
    suction = [(x, 0.48 + 0.95 * math.sin(math.pi * x) ** 0.72 + 0.22 * x + offset) for x in x_values]
    pitch = [i / 14 for i in range(15)]
    downstream = [
        (x, 1.01 - 0.27 * math.exp(-((x - 0.53) / 0.115) ** 2) + offset * 0.35)
        for x in pitch
    ]
    return {
        "surface_profiles": [
            profile(case_id, "pressure_side", "m_iso", "x_over_c", "m_iso", pressure),
            profile(case_id, "suction_side", "m_iso", "x_over_c", "m_iso", suction),
        ],
        "flow_profiles": [
            profile(case_id, "outlet_plane_2", "velocity_ratio", "pitch_fraction", "velocity_ratio", downstream)
        ],
    }


def rotor_diagnostics(case_id: str, offset: float) -> dict[str, Any]:
    x_values = [i / 12 for i in range(13)]
    pressure_profiles = []
    thermo_profiles = []
    for station_index, station_id in enumerate(("span_10", "span_50", "span_90")):
        span_factor = 0.94 + 0.06 * station_index
        pressure = [
            (x, 0.88 + span_factor * (0.28 * x + 0.34 * x**1.8) + 0.035 * math.sin(math.pi * x) + offset)
            for x in x_values
        ]
        temperature = [(x, 0.99 + span_factor * 0.23 * x**1.45 + offset * 0.18) for x in x_values]
        density = [(x, 0.96 + span_factor * 0.19 * x**1.25 + offset * 0.12) for x in x_values]
        pressure_profiles.append(
            profile(case_id, station_id, "pressure_ratio", "x_over_c", "pressure_ratio", pressure)
        )
        thermo_profiles.extend(
            [
                profile(case_id, station_id, "temperature_ratio", "x_over_c", "temperature_ratio", temperature),
                profile(case_id, station_id, "density_ratio", "x_over_c", "density_ratio", density),
            ]
        )
    return {"blade_profiles": pressure_profiles, "blade_thermo_profiles": thermo_profiles}


def blendednet_diagnostics(case_id: str, offset: float) -> dict[str, Any]:
    x_values = [i / 12 for i in range(13)]
    cp_cuts = []
    friction_profiles = []
    stations = (
        ("prototype_centerline", 0.0),
        ("prototype_midspan", 0.45),
        ("prototype_outer_wing", 0.8),
    )
    for station_id, span_fraction in stations:
        cp = [
            (
                x,
                -0.82 * (1.0 - 0.42 * span_fraction) * math.exp(-((x - 0.18) / 0.2) ** 2)
                + 0.24 * x
                + offset,
            )
            for x in x_values
        ]
        cfx = [
            (x, 0.0036 * (1.0 - 0.28 * span_fraction) * (1.0 - 0.62 * x) + offset * 0.002)
            for x in x_values
        ]
        cfz = [
            (x, -0.0011 * span_fraction * math.sin(math.pi * x) + offset * 0.0015)
            for x in x_values
        ]
        cp_cuts.append(profile(case_id, station_id, "cp", "x_over_c1", "cp", cp))
        friction_profiles.extend(
            [
                profile(case_id, station_id, "cfx", "x_over_c1", "cfx", cfx),
                profile(case_id, station_id, "cfz", "x_over_c1", "cfz", cfz),
            ]
        )
    return {"cp_cuts": cp_cuts, "skin_friction_profiles": friction_profiles}


def generate_vki() -> None:
    splits = ["train", "train_500", "train_250", "train_125", "train_64", "train_32", "train_16", "train_8"]
    quantities = [
        ("vki_mach", 0.82), ("vki_nut", 1.75), ("vki_q", 0.94), ("vki_power", 1.08),
        ("vki_pr", 0.71), ("vki_tr", 0.68), ("vki_eth_is", 0.88), ("vki_angle_out", 1.02),
    ]
    for index, split in enumerate(splits):
        scale = 0.018 + 0.0095 * index
        submission = common_submission("VKI-LS59", split, index)
        submission["metric_values"] = metric_block(quantities, scale)
        submission["diagnostics"] = vki_diagnostics(submission["submission_id"], scale * 0.16)
        write_json(ROOT / "submissions" / "vki-ls59" / f"dummy-vki-ls59-{split}.json", submission)


def generate_rotor() -> None:
    splits = ["train_1000", "train_500", "train_250", "train_125", "train_64", "train_32", "train_16", "train_8"]
    quantities = [
        ("rotor_density", 0.91), ("rotor_pressure", 1.12), ("rotor_temperature", 0.78),
        ("rotor_massflow", 0.72), ("rotor_compression_ratio", 0.83), ("rotor_efficiency", 0.96),
    ]
    absolute_scales = {
        "rotor_density": (0.42, 0.58),
        "rotor_pressure": (42000.0, 61000.0),
        "rotor_temperature": (64.0, 91.0),
        "rotor_massflow": (8.2, 11.4),
        "rotor_compression_ratio": (0.31, 0.44),
        "rotor_efficiency": (0.19, 0.27),
    }
    for index, split in enumerate(splits):
        scale = 0.016 + 0.0105 * index
        submission = common_submission("Rotor37", split, index)
        submission["metric_values"] = metric_block(quantities, scale, absolute_scales)
        submission["diagnostics"] = rotor_diagnostics(submission["submission_id"], scale * 0.13)
        write_json(ROOT / "submissions" / "rotor37" / f"dummy-rotor37-{split}.json", submission)


def generate_blendednet() -> None:
    submission = common_submission("BlendedNet", "geometry_holdout", 0)
    submission["submission_id"] = "blendednet-prototype-geometry-holdout"
    submission["parameter_count"] = 5.42
    submission["metric_values"] = {
        "blended_surface_rel_l2": 10.3,
        "blended_cp_mse": 0.0084,
        "blended_cp_mae": 0.0385,
        "blended_cp_rel_l1": 13.9,
        "blended_cp_rel_l2": 3.4,
        "blended_cp_r2": 0.978,
        "blended_cfx_mse": 0.000032,
        "blended_cfx_mae": 0.00142,
        "blended_cfx_rel_l1": 22.7,
        "blended_cfx_rel_l2": 8.2,
        "blended_cfx_r2": 0.941,
        "blended_cfz_mse": 0.000018,
        "blended_cfz_mae": 0.00084,
        "blended_cfz_rel_l1": 30.8,
        "blended_cfz_rel_l2": 19.3,
        "blended_cfz_r2": 0.887,
        "c_drag_mae": 0.0018,
        "c_lift_mae": 0.0095,
        "c_pitch_mae": 0.0048,
        "cd_r2": 0.982,
        "cl_r2": 0.975,
        "c_pitch_r2": 0.964,
    }
    submission["diagnostics"] = blendednet_diagnostics(submission["submission_id"], 0.018)
    write_json(
        ROOT / "submissions" / "blendednet" / "dummy-blendednet-geometry-holdout.json",
        submission,
    )


if __name__ == "__main__":
    generate_vki()
    generate_rotor()
    generate_blendednet()
