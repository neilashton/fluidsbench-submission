"""Fetch a checksum-bound dev support archive, or use an exact local release.

Only transport is new: scoring still opens the unchanged canonical support
with the existing strict loader, including every case's transitive hashes.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import stat
import tempfile
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

from reference.hiliftaeroml.dev_release import (
    ROOT,
    SUPPORT_MANIFEST_SHA256,
    load_release,
)


def _digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _verify_manifest(path: Path, digest: str) -> Path:
    if (
        not path.is_dir()
        or path.is_symlink()
        or _digest(path / "manifest.json") != digest
    ):
        raise ValueError(
            "HiLiftAeroML compact scoring-support manifest differs from the dev release"
        )
    return path


def extract_archive(archive: Path, destination: Path, *, expected_bytes: int) -> None:
    """Extract regular members only; bound expansion and forbid traversal/duplicates."""
    with zipfile.ZipFile(archive) as bundle:
        members = bundle.infolist()
        names = [item.filename for item in members]
        if len(names) != len(set(names)) or len(names) > 6000:
            raise ValueError("support archive has duplicate or excessive members")
        if sum(item.file_size for item in members) != expected_bytes:
            raise ValueError("support archive expanded byte count differs")
        for item in members:
            path = PurePosixPath(item.filename)
            mode = item.external_attr >> 16
            if (
                not item.filename
                or path.is_absolute()
                or ".." in path.parts
                or "\\" in item.filename
                or str(path) != item.filename.rstrip("/")
                or stat.S_ISLNK(mode)
                or (stat.S_IFMT(mode) not in {0, stat.S_IFREG, stat.S_IFDIR})
            ):
                raise ValueError("support archive contains an unsafe member")
        for item in members:
            target = destination / item.filename
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            if item.is_dir():
                target.mkdir(exist_ok=True, mode=0o700)
            else:
                with bundle.open(item) as source, target.open("xb") as output:
                    shutil.copyfileobj(source, output, 1 << 20)
                target.chmod(0o600)


def resolve_support(explicit: Path | None = None, *, root: Path = ROOT) -> Path:
    """Resolve explicit path, environment, then the benchmark-pinned download."""
    selected = explicit or os.environ.get("FLUIDSBENCH_HILIFT_PROFILE_SUPPORT")
    if selected:
        return _verify_manifest(
            Path(selected).expanduser().resolve(), SUPPORT_MANIFEST_SHA256
        )
    cache_base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    cache = cache_base / "fluidsbench/hiliftaeroml" / SUPPORT_MANIFEST_SHA256
    if cache.exists():
        return _verify_manifest(cache, SUPPORT_MANIFEST_SHA256)
    release = load_release(root)
    transport = release.get("support_transport")
    if not isinstance(transport, dict):
        raise ValueError(
            "HiLiftAeroML dev scoring support has no published transport yet. "
            "Provide --profile-support-release or FLUIDSBENCH_HILIFT_PROFILE_SUPPORT "
            "pointing to the complete 7f946510 compact support release; "
            "public plotting truth is insufficient."
        )
    url = transport.get("url", "")
    if not url.startswith("https://"):
        raise ValueError("support transport must be HTTPS")
    archive_size = transport.get("size_bytes")
    if type(archive_size) is not int or not 0 < archive_size <= 2_000_000_000:
        raise ValueError("invalid support archive size")
    cache.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.TemporaryDirectory(
        prefix=".download-", dir=cache.parent
    ) as temporary:
        staging = Path(temporary)
        archive = staging / "support.zip"
        total = 0
        with urllib.request.urlopen(url, timeout=60) as response, archive.open(
            "xb"
        ) as output:
            for block in iter(lambda: response.read(1 << 20), b""):
                total += len(block)
                if total > archive_size:
                    raise ValueError("support download exceeds its pinned size")
                output.write(block)
        if total != archive_size or _digest(archive) != transport.get("sha256"):
            raise ValueError("support download size or SHA-256 differs")
        unpacked = staging / "release"
        unpacked.mkdir(mode=0o700)
        extract_archive(archive, unpacked, expected_bytes=transport["expanded_bytes"])
        _verify_manifest(unpacked, SUPPORT_MANIFEST_SHA256)
        # Full canonical/transitive validation precedes cache publication.
        import json
        from reference.hiliftaeroml.compact_profile_evaluator import (
            open_compact_support_release,
        )

        split = json.loads(
            (root / "benchmark-specs/hiliftaeroml/splits/full.json").read_text()
        )
        open_compact_support_release(
            release_root=unpacked,
            expected_manifest_sha256=SUPPORT_MANIFEST_SHA256,
            expected_case_ids=split["case_ids"],
            case_set_id=split["case_set_id"],
        )
        try:
            os.rename(unpacked, cache)
        except FileExistsError:
            _verify_manifest(cache, SUPPORT_MANIFEST_SHA256)
    return cache
