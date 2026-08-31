#!/usr/bin/env python3
"""Build three append-only UE-compatible HSSD fridge link GLBs.

The source contract and every source byte are verified before the output root
is created.  Required KHR_texture_basisu images are decoded by the existing
hash-pinned offline transport and embedded as core glTF PNG images.  The
result remains private CC-BY-NC-4.0 research payload outside Git and is never
presented as imported, runtime-verified, or accepted visual evidence.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import sys
import tempfile
from typing import Any, Mapping, Sequence


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
TOOLS_ROOT = REPOSITORY_ROOT / "tools"
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from blender.vista_playable_home_hssd.glb_transport import (  # noqa: E402
    rehydrate_core_png_materials,
    uses_required_basisu,
    read_glb,
    validate_core_png_glb,
    write_blender_surrogate,
)
from blender.vista_playable_home_hssd.planner import HssdBindingError  # noqa: E402
from ue.vista_playable_home import hssd_articulated_fridge_contract as contract  # noqa: E402


SCHEMA_VERSION = "vista.playable-articulated-fridge-transport-receipt/v1"
OUTPUT_ROLES = ("body", "primary_door", "secondary_door")
OUTPUT_NAMES = {
    "body": "fridge_body_core_png.glb",
    "primary_door": "fridge_primary_door_core_png.glb",
    "secondary_door": "fridge_secondary_door_core_png.glb",
}
RECEIPT_NAME = "articulated-fridge-transport-receipt.json"


class ArticulatedFridgeTransportError(RuntimeError):
    """The source, decoder, output root, or transported link is not closed."""


def _require(condition: Any, message: str) -> None:
    if not condition:
        raise ArticulatedFridgeTransportError(message)


def _canonical_json(value: Any) -> bytes:
    try:
        return (
            json.dumps(
                value,
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8", "strict")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise ArticulatedFridgeTransportError(
            "transport receipt is not finite canonical JSON"
        ) from exc


def _content_digest(value: Mapping[str, Any]) -> str:
    body = copy.deepcopy(dict(value))
    body.pop("content_digest", None)
    return hashlib.sha256(_canonical_json(body)).hexdigest()


def _seal(value: Mapping[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(dict(value))
    result["content_digest"] = _content_digest(result)
    return result


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _regular_absolute(path: Path, label: str, *, executable: bool = False) -> Path:
    _require(path.is_absolute(), f"{label} must be absolute")
    _require(
        path.exists() and not path.is_symlink(), f"{label} is missing or symlinked"
    )
    resolved = path.resolve(strict=True)
    _require(resolved.is_file(), f"{label} must be a regular file")
    if executable:
        _require(os.access(resolved, os.X_OK), f"{label} must be executable")
    return resolved


def _safe_source(root: Path, record: Mapping[str, Any]) -> Path:
    relative = PurePosixPath(str(record["relative_path"]))
    _require(
        not relative.is_absolute() and ".." not in relative.parts,
        "source link path escapes the HSSD root",
    )
    candidate = root.joinpath(*relative.parts)
    _require(not candidate.is_symlink(), "source link must not be a symlink")
    resolved = candidate.resolve(strict=True)
    _require(resolved.is_relative_to(root), "source link escaped the HSSD root")
    _require(resolved.is_file(), "source link is not a regular file")
    _require(
        resolved.stat().st_size == record["size_bytes"]
        and _sha256(resolved) == record["sha256"],
        f"source manifest pin differs for {record['role']}",
    )
    return resolved


def _write_exclusive(path: Path, raw: bytes) -> None:
    descriptor = os.open(
        path,
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        os.close(descriptor)


def _source_record(document: Mapping[str, Any], role: str) -> Mapping[str, Any]:
    matches = [item for item in document["source_files"] if item["role"] == role]
    _require(len(matches) == 1, f"contract has no unique {role} link")
    return matches[0]


def _mesh_position_bounds(document: Mapping[str, Any]) -> dict[str, list[float]]:
    accessors = document.get("accessors")
    meshes = document.get("meshes")
    _require(
        isinstance(accessors, list) and isinstance(meshes, list),
        "transported GLB mesh/accessor arrays are unavailable",
    )
    minimums: list[list[float]] = []
    maximums: list[list[float]] = []
    for mesh in meshes:
        _require(isinstance(mesh, Mapping), "transported GLB mesh is invalid")
        for primitive in mesh.get("primitives", []):
            attributes = (
                primitive.get("attributes") if isinstance(primitive, Mapping) else None
            )
            position = (
                attributes.get("POSITION") if isinstance(attributes, Mapping) else None
            )
            _require(
                isinstance(position, int) and 0 <= position < len(accessors),
                "transported GLB POSITION accessor is invalid",
            )
            accessor = accessors[position]
            lower = accessor.get("min") if isinstance(accessor, Mapping) else None
            upper = accessor.get("max") if isinstance(accessor, Mapping) else None
            _require(
                isinstance(lower, list)
                and isinstance(upper, list)
                and len(lower) == len(upper) == 3
                and all(
                    type(value) in (int, float) and math.isfinite(value)
                    for value in lower + upper
                ),
                "transported GLB POSITION bounds are unavailable",
            )
            minimums.append([float(value) for value in lower])
            maximums.append([float(value) for value in upper])
    _require(minimums, "transported GLB has no bounded POSITION primitive")
    return {
        "min_m": [min(item[axis] for item in minimums) for axis in range(3)],
        "max_m": [max(item[axis] for item in maximums) for axis in range(3)],
    }


def build_transport(
    *,
    contract_path: Path,
    hssd_root: Path,
    output_root: Path,
    node_path: Path,
    transcoder_js_path: Path,
    transcoder_wasm_path: Path,
) -> dict[str, Any]:
    """Verify all inputs, create a new output root, and seal three derivatives."""

    pinned_contract = contract.load_contract(contract_path)
    contract.validate_contract(pinned_contract)
    source_receipt = contract.verify_source_tree(pinned_contract, hssd_root)
    root = hssd_root.resolve(strict=True)
    _require(root.is_dir(), "HSSD root is not a directory")
    node = _regular_absolute(node_path, "Node executable", executable=True)
    javascript = _regular_absolute(transcoder_js_path, "Basis transcoder JS")
    wasm = _regular_absolute(transcoder_wasm_path, "Basis transcoder WASM")
    manifest = _regular_absolute(contract_path, "articulated fridge contract")
    try:
        contract_relative_path = str(manifest.relative_to(REPOSITORY_ROOT))
    except ValueError as exc:
        raise ArticulatedFridgeTransportError(
            "articulated fridge contract must be repository-owned"
        ) from exc

    # Resolve and re-pin every link before creating output.  A failed source
    # check therefore leaves no artifact that could be mistaken for a run.
    sources = {
        role: _safe_source(root, _source_record(pinned_contract, role))
        for role in OUTPUT_ROLES
    }
    _require(output_root.is_absolute(), "output root must be absolute")
    _require(
        not output_root.exists() and not output_root.is_symlink(),
        "output root already exists",
    )
    output_root.mkdir(mode=0o700, parents=False)
    assets_root = output_root / "assets"
    assets_root.mkdir(mode=0o700)

    outputs: list[dict[str, Any]] = []
    for role in OUTPUT_ROLES:
        source = sources[role]
        source_document, _ = read_glb(source)
        _require(
            uses_required_basisu(source_document),
            f"{role} source does not require KHR_texture_basisu",
        )
        destination = assets_root / OUTPUT_NAMES[role]
        with tempfile.TemporaryDirectory(
            prefix=f".{role}-surrogate-", dir=output_root
        ) as temporary:
            surrogate = Path(temporary) / "material-index-surrogate.glb"
            surrogate_receipt = write_blender_surrogate(source, surrogate)
            transport_receipt = rehydrate_core_png_materials(
                source,
                surrogate,
                destination,
                node_path=node,
                transcoder_js_path=javascript,
                transcoder_wasm_path=wasm,
            )
        validation = validate_core_png_glb(source, destination)
        transported_document, _ = read_glb(destination)
        _require(
            validation["self_contained"] is True
            and validation["single_buffer"] is True
            and validation["single_mesh"] is True
            and validation["embedded_png_images_valid"] is True
            and transport_receipt["converted_image_count"]
            == len(validation["image_payloads"]),
            f"{role} derivative did not close the core-PNG contract",
        )
        source_record = _source_record(pinned_contract, role)
        outputs.append(
            {
                "role": role,
                "source": {
                    "relative_path": source_record["relative_path"],
                    "sha256": source_record["sha256"],
                    "size_bytes": source_record["size_bytes"],
                },
                "derivative": {
                    "relative_path": "assets/" + OUTPUT_NAMES[role],
                    "sha256": _sha256(destination),
                    "size_bytes": destination.stat().st_size,
                },
                "surrogate": surrogate_receipt,
                "transport": transport_receipt,
                "validation": validation,
                "mesh_bounds": _mesh_position_bounds(transported_document),
            }
        )

    receipt = _seal(
        {
            "schema_version": SCHEMA_VERSION,
            "status": "transported_pending_ue_import_runtime_and_human_review",
            "accepted": False,
            "ue_imported": False,
            "runtime_verified": False,
            "human_reviewed": False,
            "gta_quality": False,
            "contract": {
                "relative_repository_path": contract_relative_path,
                "sha256": _sha256(manifest),
                "content_digest": pinned_contract["content_digest"],
                "contract_id": pinned_contract["contract_id"],
                "semantic_target_id": pinned_contract["semantic_target_id"],
            },
            "source_verification": source_receipt,
            "license": {
                "provider": pinned_contract["dataset"]["provider"],
                "spdx": pinned_contract["dataset"]["license_spdx"],
                "use_class": pinned_contract["dataset"]["use_class"],
                "payload_policy": pinned_contract["dataset"]["payload_policy"],
            },
            "output_roles": list(OUTPUT_ROLES),
            "outputs": outputs,
            "claims": {
                "source_manifest_hashes_verified": True,
                "required_basisu_removed": True,
                "embedded_core_png_only": True,
                "source_pbr_material_records_preserved": True,
                "geometry_accepted_in_ue": False,
                "visual_quality_accepted": False,
            },
        }
    )
    raw = _canonical_json(receipt)
    _write_exclusive(output_root / RECEIPT_NAME, raw)
    return receipt


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, default=contract.CONTRACT_PATH)
    parser.add_argument("--hssd-root", type=Path, default=contract.DEFAULT_HSSD_ROOT)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--node", type=Path, required=True)
    parser.add_argument("--basis-transcoder-js", type=Path, required=True)
    parser.add_argument("--basis-transcoder-wasm", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        receipt = build_transport(
            contract_path=args.contract,
            hssd_root=args.hssd_root,
            output_root=args.output_root,
            node_path=args.node,
            transcoder_js_path=args.basis_transcoder_js,
            transcoder_wasm_path=args.basis_transcoder_wasm,
        )
    except (
        ArticulatedFridgeTransportError,
        contract.ArticulatedFridgeContractError,
        HssdBindingError,
        OSError,
    ) as exc:
        print(f"VISTA_ARTICULATED_FRIDGE_TRANSPORT_FAILED: {exc}", file=sys.stderr)
        return 1
    print(
        "VISTA_ARTICULATED_FRIDGE_TRANSPORT_RESULT:"
        + json.dumps(
            {
                "status": receipt["status"],
                "receipt": str(args.output_root / RECEIPT_NAME),
                "content_digest": receipt["content_digest"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
