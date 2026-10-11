"""Immutable adapter identity and benchmark-owned defaults for dev packages.

The native evaluator and the later compact/SI adapter have separate identities.
Historical preview packages retain their original unbound adapter declaration.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RELEASE_FILE = Path("benchmark-specs/hiliftaeroml/dev-release.json")
SUPPORT_MANIFEST_SHA256 = (
    "7f946510cf8f63d05adaff4c91980d74f29c45ed7209b5a8f7e604e521cb823b"
)


def load_release(root: Path = ROOT) -> dict:
    release = json.loads((root / RELEASE_FILE).read_text())
    if (
        release.get("schema") != "hiliftaeroml-dev-release-v1"
        or release.get("status") != "closed_candidate_dev_only"
        or release.get("official_intake_open") is not False
        or release.get("support_manifest_sha256") != SUPPORT_MANIFEST_SHA256
    ):
        raise ValueError("HiLiftAeroML dev release identity or lifecycle differs")
    binding = release["implementation_binding"]
    if (
        binding.get("status") != "frozen_dev_candidate"
        or binding.get("activation_effect") != "none"
        or not re.fullmatch(r"[0-9a-f]{40}", binding.get("code_revision", ""))
    ):
        raise ValueError(
            "HiLiftAeroML dev implementation must name an immutable commit"
        )
    manifest_path = (
        root / "benchmark-specs/hiliftaeroml/dev-implementation-manifest.json"
    )
    if hashlib.sha256(manifest_path.read_bytes()).hexdigest() != binding.get(
        "implementation_manifest_sha256"
    ):
        raise ValueError("HiLiftAeroML dev implementation manifest digest differs")
    manifest = json.loads(manifest_path.read_text())
    if manifest.get(
        "schema"
    ) != "hiliftaeroml-dev-implementation-manifest-v1" or not manifest.get("files"):
        raise ValueError("HiLiftAeroML dev source manifest is invalid")
    for entry in manifest["files"]:
        relative = Path(entry["file"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("invalid dev source path")
        if (
            hashlib.sha256((root / relative).read_bytes()).hexdigest()
            != entry["sha256"]
        ):
            raise ValueError(f"HiLiftAeroML dev runtime source differs: {relative}")
    return release


def implementation_binding(root: Path = ROOT) -> dict:
    return copy.deepcopy(load_release(root)["implementation_binding"])


def resolve_config(config: dict, specification: dict) -> dict:
    """Supply release metadata from the benchmark, never participant placeholders."""
    result = copy.deepcopy(config)
    support = specification["scoring_support"]
    profile = specification["profile_definition"]
    evaluator = support["dataset_evaluator_binding"]
    result["release_bindings"] = {
        "candidate_manifest": {
            key: support["candidate_manifest"][key]
            for key in ("status", "release_id", "manifest_url", "manifest_sha256")
        },
        "evaluator": {
            "reference_version": evaluator["evaluator_reference_version"],
            "code_revision": evaluator["evaluator_code_revision"],
        },
        "profile_contract": {
            key: profile[key] for key in ("contract_id", "file", "format", "sha256")
        },
        "profile_ground_truth": {
            key: profile["candidate_dry_run_profile_ground_truth"][key]
            for key in ("release_id", "manifest_sha256")
        },
    }
    return result
