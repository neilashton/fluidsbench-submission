#!/usr/bin/env python3
"""Validate and archive the exact existing compact support for dev distribution.

This does not upload anything or rewrite the retained support. Its output gives
the transport hashes to bind after uploading the archive to a dev prerelease.
"""

from __future__ import annotations

import argparse
import json
import os
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in os.sys.path:
    os.sys.path.insert(0, str(ROOT))

from reference.hiliftaeroml.compact_profile_evaluator import (
    open_compact_support_release,
)
from reference.hiliftaeroml.dev_release import SUPPORT_MANIFEST_SHA256
from reference.hiliftaeroml.dev_support import _digest, resolve_support


def build_archive(source: Path, output: Path) -> dict:
    spec = json.loads(
        (ROOT / "benchmark-specs/hiliftaeroml/submission-spec.json").read_text()
    )
    split = json.loads(
        (ROOT / "benchmark-specs/hiliftaeroml/splits/full.json").read_text()
    )
    release = open_compact_support_release(
        release_root=source,
        expected_manifest_sha256=SUPPORT_MANIFEST_SHA256,
        expected_case_ids=split["case_ids"],
        case_set_id=split["case_set_id"],
    )
    expected = {}
    for entry in spec["splits"]:
        index = json.loads(
            (ROOT / "benchmark-specs/hiliftaeroml" / entry["index_file"]).read_text()
        )
        expected[index["case_set_id"]] = index["case_ids"]
    actual = {
        entry["case_set_id"]: entry["case_ids"] for entry in release.index["case_sets"]
    }
    if actual != expected:
        raise ValueError("support must cover every declared ordered case set")
    files = sorted(path for path in source.rglob("*") if path.is_file())
    total = sum(path.stat().st_size for path in files)
    if total != 1028030877:
        raise ValueError("retained all-case support byte count differs")
    try:
        with output.open("xb") as stream, zipfile.ZipFile(
            stream, "w", compression=zipfile.ZIP_STORED
        ) as bundle:
            for path in files:
                info = zipfile.ZipInfo(
                    path.relative_to(source).as_posix(), date_time=(1980, 1, 1, 0, 0, 0)
                )
                info.create_system = 3
                info.external_attr = 0o100600 << 16
                with path.open("rb") as source_file, bundle.open(
                    info, "w", force_zip64=True
                ) as target:
                    import shutil

                    shutil.copyfileobj(source_file, target, 1 << 20)
    except Exception:
        # Never delete a file that predated this invocation.
        if not isinstance(os.sys.exc_info()[1], FileExistsError):
            output.unlink(missing_ok=True)
        raise
    return {
        "sha256": _digest(output),
        "size_bytes": output.stat().st_size,
        "expanded_bytes": total,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-release", type=Path)
    parser.add_argument("--archive", type=Path)
    args = parser.parse_args()
    try:
        if args.archive:
            if args.source_release is None:
                parser.error("--archive requires --source-release")
            result = build_archive(args.source_release, args.archive)
        else:
            result = {
                "profile_support_release": str(resolve_support(args.source_release))
            }
        print(json.dumps(result, indent=2))
        return 0
    except (OSError, ValueError) as error:
        print(str(error), file=os.sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
