#!/usr/bin/env python3
"""Generate and compare canonical full-tree UE authority manifests.

This helper never copies files, invokes sudo, changes ownership, or changes
permissions. The root-side provisioning script owns those operations. This
helper only performs full byte hashing, rejects symlinks, writes a new
manifest with O_EXCL, or compares two already generated content roots.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import stat
import sys
from typing import Any


SCHEMA = "vista.r5-immutable-engine-tree/v1"


class ManifestError(RuntimeError):
    pass


def _canonical(value: dict[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode() + b"\n"


def _hash_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(4 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _entry(root: pathlib.Path, path: pathlib.Path) -> dict[str, Any]:
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode):
        raise ManifestError(f"engine tree contains a symlink: {path}")
    relative = path.relative_to(root).as_posix()
    if stat.S_ISDIR(info.st_mode):
        kind = "directory"
        size = 0
        digest = ""
    elif stat.S_ISREG(info.st_mode):
        kind = "file"
        size = info.st_size
        digest = _hash_file(path)
    else:
        raise ManifestError(f"engine tree contains an unsupported node: {path}")
    return {
        "path": relative,
        "type": kind,
        "mode": stat.S_IMODE(info.st_mode),
        "uid": info.st_uid,
        "gid": info.st_gid,
        "size_bytes": size,
        "sha256": digest,
    }


def build_manifest(root: pathlib.Path, declared_root: pathlib.Path) -> dict[str, Any]:
    root = root.resolve(strict=True)
    declared_root = declared_root.absolute()
    if root.is_symlink() or not root.is_dir() or not declared_root.is_absolute():
        raise ManifestError("engine roots must be canonical absolute directories")
    paths: list[pathlib.Path] = []
    for directory, directory_names, file_names in os.walk(root, followlinks=False):
        base = pathlib.Path(directory)
        paths.extend(base / name for name in directory_names)
        paths.extend(base / name for name in file_names)
    entries = [
        _entry(root, path)
        for path in sorted(paths, key=lambda item: item.relative_to(root).as_posix())
    ]
    content_entries = [
        {
            "path": entry["path"],
            "type": entry["type"],
            "size_bytes": entry["size_bytes"],
            "sha256": entry["sha256"],
        }
        for entry in entries
    ]
    tree_root_digest = hashlib.sha256(
        _canonical({"entries": content_entries})
    ).hexdigest()
    payload = {
        "schema": SCHEMA,
        "engine_root": str(declared_root),
        "entries": entries,
        "tree_root_digest": tree_root_digest,
    }
    content_digest = hashlib.sha256(_canonical(payload)).hexdigest()
    return {**payload, "content_digest": content_digest}


def _load(path: pathlib.Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ManifestError(f"invalid manifest: {path}") from exc
    if not isinstance(value, dict) or value.get("schema") != SCHEMA:
        raise ManifestError(f"manifest schema differs: {path}")
    payload = dict(value)
    digest = payload.pop("content_digest", None)
    if (
        not isinstance(digest, str)
        or hashlib.sha256(_canonical(payload)).hexdigest() != digest
    ):
        raise ManifestError(f"manifest content digest differs: {path}")
    return value


def _write_new(path: pathlib.Path, document: dict[str, Any]) -> None:
    raw = _canonical(document)
    path.parent.resolve(strict=True)
    with path.open("xb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    path.chmod(0o600)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    snapshot = subparsers.add_parser("snapshot")
    snapshot.add_argument("--scan-root", type=pathlib.Path, required=True)
    snapshot.add_argument("--declared-root", type=pathlib.Path, required=True)
    snapshot.add_argument("--output", type=pathlib.Path, required=True)
    compare = subparsers.add_parser("compare-content")
    compare.add_argument("left", type=pathlib.Path)
    compare.add_argument("right", type=pathlib.Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "snapshot":
            document = build_manifest(args.scan_root, args.declared_root)
            _write_new(args.output.absolute(), document)
            raw = args.output.absolute().read_bytes()
            print(
                json.dumps(
                    {
                        "manifest_sha256": hashlib.sha256(raw).hexdigest(),
                        "tree_root_digest": document["tree_root_digest"],
                    },
                    sort_keys=True,
                )
            )
            return 0
        left = _load(args.left.absolute())
        right = _load(args.right.absolute())
        if left.get("tree_root_digest") != right.get("tree_root_digest"):
            raise ManifestError("engine content tree roots differ")
        print(left["tree_root_digest"])
        return 0
    except ManifestError as exc:
        print(f"R5_ENGINE_MANIFEST_FAILED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
