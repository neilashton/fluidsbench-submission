#!/usr/bin/env python3
"""Populate every checked-in prototype result with structured method metadata."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.prototype_methodologies import build_prototype_methodology  # noqa: E402


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, value: Any) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, ensure_ascii=True)
        handle.write("\n")


def update_all(*, check: bool) -> tuple[int, list[Path]]:
    changed: list[Path] = []
    count = 0
    contracts = {
        path.parent.name: load_json(path)
        for path in sorted((ROOT / "benchmark-specs").glob("*/methodology-contract.json"))
    }
    for path in sorted((ROOT / "submissions").glob("*/*/submission.json")):
        submission = load_json(path)
        if submission.get("approval", {}).get("status") != "prototype":
            continue
        dataset_id = submission.get("dataset_id")
        contract = contracts.get(dataset_id)
        if contract is None:
            raise ValueError(f"missing methodology contract for {dataset_id!r}")
        expected = build_prototype_methodology(submission, contract)
        count += 1
        if submission.get("methodology") == expected:
            continue
        changed.append(path)
        if not check:
            submission["methodology"] = expected
            write_json(path, submission)
    return count, changed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail if any checked-in prototype method record is stale",
    )
    args = parser.parse_args()
    count, changed = update_all(check=args.check)
    if args.check and changed:
        for path in changed:
            print(path.relative_to(ROOT))
        return 1
    action = "Checked" if args.check else "Updated"
    print(f"{action} structured methodology for {count} prototype submissions.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
