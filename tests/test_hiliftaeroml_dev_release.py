"""The dev adapter freeze is separate from historical native evaluator evidence."""

import copy
import json
import subprocess
from pathlib import Path

from reference.hiliftaeroml.dev_release import load_release
from scripts.validate_submission import schema_errors

ROOT = Path(__file__).resolve().parents[1]


def test_dev_adapter_sources_match_the_frozen_commit():
    release = load_release()
    manifest = json.loads(
        (
            ROOT / "benchmark-specs/hiliftaeroml/dev-implementation-manifest.json"
        ).read_text()
    )
    revision = release["implementation_binding"]["code_revision"]
    import hashlib

    for entry in manifest["files"]:
        frozen = subprocess.run(
            ["git", "show", f"{revision}:{entry['file']}"],
            cwd=ROOT,
            check=True,
            capture_output=True,
        ).stdout
        assert hashlib.sha256(frozen).hexdigest() == entry["sha256"], entry["file"]
    spec = json.loads(
        (ROOT / "benchmark-specs/hiliftaeroml/submission-spec.json").read_text()
    )
    assert spec["scoring_support"]["submissions_open"] is False
    assert (
        spec["scoring_support"]["dataset_evaluator_binding"]["evaluator_code_revision"]
        == "68899f780d96b70f2badb5658971c87af0b17172"
    )


def test_dev_binding_requires_real_pins_in_both_schemas():
    directory = (
        ROOT / "submissions/hiliftaeroml/hiliftaeroml-transolver-aoa4-candidate-v1"
    )
    submission = json.loads((directory / "submission.json").read_text())
    evidence = json.loads((directory / "evaluation-evidence.json").read_text())
    binding = load_release()["implementation_binding"]
    submission["profile_data"]["compact_profile_implementation_binding"] = (
        copy.deepcopy(binding)
    )
    evidence["compact_profile_implementation_binding"] = copy.deepcopy(binding)
    assert not schema_errors(submission, "submission.schema.json", schema_version="v3")
    assert not schema_errors(
        evidence, "evaluation-evidence.schema.json", schema_version="v3"
    )
    submission["profile_data"]["compact_profile_implementation_binding"][
        "code_revision"
    ] = None
    evidence["compact_profile_implementation_binding"][
        "implementation_manifest_sha256"
    ] = None
    assert schema_errors(submission, "submission.schema.json", schema_version="v3")
    assert schema_errors(
        evidence, "evaluation-evidence.schema.json", schema_version="v3"
    )
