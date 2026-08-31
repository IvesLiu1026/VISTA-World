#!/usr/bin/env python3
"""Validate the pinned HSSD articulated-fridge source without importing it.

This module is deliberately read-only.  It binds the private HSSD payload to a
closed public contract, verifies the URDF/AO topology and source bytes, and
returns a source receipt suitable for a later append-only UE import attempt.
It never makes a network request and never copies HSSD payload into Git.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any
import xml.etree.ElementTree as ET

import jsonschema


SCHEMA_VERSION = "vista.playable-articulated-fridge/v1"
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SCHEMA_PATH = (
    REPOSITORY_ROOT
    / "world_packs/schemas/vista-playable-articulated-fridge-v1.schema.json"
)
CONTRACT_PATH = (
    REPOSITORY_ROOT
    / "world_packs/vista_playable_home_r1/articulations/"
    "hssd_side_by_side_fridge_r1.json"
)
DEFAULT_HSSD_ROOT = Path("/mnt/NAS2/yhliu/habitat_data/versioned_data/hssd-hab")
MODEL_ID = "01841f449f738c1e24fa15753d1fbc5fe0c6a92c"
ROLE_COUNTS = {
    "urdf": 1,
    "ao_config": 1,
    "body": 1,
    "primary_door": 1,
    "secondary_door": 1,
    "receptacle": 11,
}


class ArticulatedFridgeContractError(RuntimeError):
    """The closed contract or private source differs from the pinned model."""


def _require(condition: Any, message: str) -> None:
    if not condition:
        raise ArticulatedFridgeContractError(message)


def _duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        _require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ArticulatedFridgeContractError(f"non-finite JSON constant: {value}")


def canonical_json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8", "strict")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise ArticulatedFridgeContractError(
            "contract is not finite canonical JSON"
        ) from exc


def content_digest(value: Mapping[str, Any]) -> str:
    body = copy.deepcopy(dict(value))
    body.pop("content_digest", None)
    return hashlib.sha256(canonical_json_bytes(body)).hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_contract(path: Path | str = CONTRACT_PATH) -> dict[str, Any]:
    source = Path(path)
    try:
        document = json.loads(
            source.read_text(encoding="utf-8"),
            object_pairs_hook=_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except ArticulatedFridgeContractError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ArticulatedFridgeContractError(
            "articulated fridge contract is not strict UTF-8 JSON"
        ) from exc
    _require(type(document) is dict, "contract root must be one object")
    return document


def _schema() -> dict[str, Any]:
    try:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator.check_schema(schema)
    except (OSError, json.JSONDecodeError, jsonschema.SchemaError) as exc:
        raise ArticulatedFridgeContractError(
            "articulated fridge schema is unavailable"
        ) from exc
    return schema


def validate_contract(document: Mapping[str, Any]) -> None:
    errors = sorted(
        jsonschema.Draft202012Validator(_schema()).iter_errors(document),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    _require(not errors, f"schema validation failed: {errors[0].message}" if errors else "")
    _require(document["schema_version"] == SCHEMA_VERSION, "schema version differs")
    _require(
        document["content_digest"] == content_digest(document),
        "contract content digest differs",
    )

    files = document["source_files"]
    relative_paths = [item["relative_path"] for item in files]
    _require(len(relative_paths) == len(set(relative_paths)), "source paths repeat")
    _require(Counter(item["role"] for item in files) == ROLE_COUNTS, "role counts differ")
    for relative in relative_paths:
        path = PurePosixPath(relative)
        _require(
            not path.is_absolute() and ".." not in path.parts,
            "source path escapes the HSSD root",
        )

    links = document["links"]
    _require(
        [link["role"] for link in links]
        == ["body", "primary_door", "secondary_door"],
        "link role order differs",
    )
    role_to_name = {
        item["role"]: PurePosixPath(item["relative_path"]).name
        for item in files
        if item["role"] != "receptacle"
    }
    _require(
        all(role_to_name[link["role"]] == link["mesh_filename"] for link in links),
        "link mesh and pinned file differ",
    )

    joints = document["joints"]
    _require(
        [item["joint_name"] for item in joints]
        == ["fridge0014_door01", "fridge0014_door02"],
        "joint order differs",
    )
    _require(joints[0]["axis"] == [0, 0, -1], "primary joint axis differs")
    _require(joints[1]["axis"] == [0, 0, 1], "secondary joint axis differs")
    _require(
        all(item["joint_name"] == item["child"] for item in joints),
        "joint and child identity differ",
    )

    receptacles = document["receptacles"]
    _require(
        len({item["anchor_id"] for item in receptacles}) == len(receptacles),
        "receptacle anchor IDs repeat",
    )
    pinned_receptacles = {
        PurePosixPath(item["relative_path"]).name
        for item in files
        if item["role"] == "receptacle"
    }
    _require(
        {item["mesh_filename"] for item in receptacles} == pinned_receptacles,
        "receptacle inventory differs from pinned source files",
    )


def _safe_source_path(root: Path, relative: str) -> Path:
    relative_path = PurePosixPath(relative)
    _require(
        not relative_path.is_absolute() and ".." not in relative_path.parts,
        "source relative path is unsafe",
    )
    candidate = root.joinpath(*relative_path.parts)
    resolved = candidate.resolve(strict=True)
    _require(resolved.is_relative_to(root), "source file escaped HSSD root")
    _require(resolved.is_file() and not candidate.is_symlink(), "source is not regular")
    return resolved


def _verify_record(path: Path, record: Mapping[str, Any]) -> None:
    stat = path.stat()
    _require(stat.st_size == record["size_bytes"], f"source size differs: {path.name}")
    _require(_sha256(path) == record["sha256"], f"source digest differs: {path.name}")


def _float_vector(raw: str, label: str) -> list[float]:
    try:
        values = [float(value) for value in raw.split()]
    except ValueError as exc:
        raise ArticulatedFridgeContractError(f"{label} is not numeric") from exc
    _require(len(values) == 3 and all(math.isfinite(value) for value in values), f"{label} differs")
    return values


def _vectors_close(left: Sequence[float], right: Sequence[float]) -> bool:
    return len(left) == len(right) and all(
        math.isclose(a, b, rel_tol=0.0, abs_tol=1e-6)
        for a, b in zip(left, right, strict=True)
    )


def _verify_urdf(document: Mapping[str, Any], path: Path) -> None:
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError) as exc:
        raise ArticulatedFridgeContractError("URDF is not parseable") from exc
    _require(root.tag == "robot", "URDF root differs")
    links = {element.attrib.get("name"): element for element in root.findall("link")}
    _require(
        set(links) == {"root", "fridge0014", "fridge0014_door01", "fridge0014_door02"},
        "URDF link inventory differs",
    )
    for expected in document["links"]:
        mesh = links[expected["link_name"]].find("./visual/geometry/mesh")
        _require(mesh is not None, "URDF visual mesh missing")
        _require(mesh.attrib.get("filename") == expected["mesh_filename"], "URDF visual mesh differs")

    joints = {element.attrib.get("name"): element for element in root.findall("joint")}
    _require(
        set(joints) == {"root_rotation", "fridge0014_door01", "fridge0014_door02"},
        "URDF joint inventory differs",
    )
    root_expected = document["root_transform"]
    root_joint = joints["root_rotation"]
    _require(root_joint.attrib.get("type") == "fixed", "URDF root joint type differs")
    _require(root_joint.find("parent").attrib.get("link") == root_expected["parent"], "URDF root parent differs")
    _require(root_joint.find("child").attrib.get("link") == root_expected["child"], "URDF root child differs")
    root_origin = root_joint.find("origin")
    _require(root_origin is not None, "URDF root origin missing")
    _require(_vectors_close(_float_vector(root_origin.attrib["rpy"], "root rpy"), root_expected["rpy_rad"]), "URDF root rpy differs")
    _require(_vectors_close(_float_vector(root_origin.attrib["xyz"], "root xyz"), root_expected["xyz_m"]), "URDF root xyz differs")

    for expected in document["joints"]:
        joint = joints[expected["joint_name"]]
        _require(joint.attrib.get("type") == expected["joint_type"], "URDF joint type differs")
        _require(joint.find("parent").attrib.get("link") == expected["parent"], "URDF joint parent differs")
        _require(joint.find("child").attrib.get("link") == expected["child"], "URDF joint child differs")
        _require(_vectors_close(_float_vector(joint.find("axis").attrib["xyz"], "joint axis"), expected["axis"]), "URDF joint axis differs")
        origin = joint.find("origin")
        limit = joint.find("limit")
        _require(origin is not None and limit is not None, "URDF joint origin/limit missing")
        _require(_vectors_close(_float_vector(origin.attrib["xyz"], "joint origin"), expected["origin_xyz_m"]), "URDF joint origin differs")
        _require(_vectors_close(_float_vector(origin.attrib.get("rpy", "0 0 0"), "joint rpy"), expected["origin_rpy_rad"]), "URDF joint rpy differs")
        for attribute, field in (("lower", "lower_rad"), ("upper", "upper_rad"), ("velocity", "velocity_rad_s")):
            _require(math.isclose(float(limit.attrib[attribute]), expected[field], rel_tol=0.0, abs_tol=1e-6), f"URDF joint {attribute} differs")


def _verify_ao_config(document: Mapping[str, Any], path: Path) -> None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_duplicate_keys, parse_constant=_reject_constant)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ArticulatedFridgeContractError("AO config is not strict JSON") from exc
    _require(type(value) is dict, "AO config root differs")
    _require(value.get("urdf_filepath") == f"{MODEL_ID}.urdf", "AO URDF binding differs")
    user_defined = value.get("user_defined")
    _require(type(user_defined) is dict and len(user_defined) == 11, "AO receptacle count differs")
    observed = {
        (item.get("mesh_filepath"), item.get("parent_link"))
        for item in user_defined.values()
        if type(item) is dict
    }
    expected = {
        (item["mesh_filename"], item["parent_link"])
        for item in document["receptacles"]
    }
    _require(observed == expected, "AO receptacle bindings differ")


def _verify_glb(path: Path) -> None:
    raw = path.read_bytes()[:12]
    _require(len(raw) == 12 and raw[:4] == b"glTF", f"GLB header differs: {path.name}")
    _require(int.from_bytes(raw[4:8], "little") == 2, f"GLB version differs: {path.name}")
    _require(int.from_bytes(raw[8:12], "little") == path.stat().st_size, f"GLB length differs: {path.name}")


def verify_source_tree(document: Mapping[str, Any], hssd_root: Path | str) -> dict[str, Any]:
    validate_contract(document)
    root = Path(hssd_root).resolve(strict=True)
    _require(root.is_dir(), "HSSD root is not a directory")

    verified_paths: dict[str, Path] = {}
    for record in document["metadata_evidence"]:
        path = _safe_source_path(root, record["relative_path"])
        _verify_record(path, record)
        _require(record["required_row"] in path.read_text(encoding="utf-8").splitlines(), "required metadata row is absent")
        verified_paths[record["relative_path"]] = path
    for record in document["source_files"]:
        path = _safe_source_path(root, record["relative_path"])
        _verify_record(path, record)
        verified_paths[record["relative_path"]] = path
        if path.suffix == ".glb":
            _verify_glb(path)

    role_paths = {
        item["role"]: verified_paths[item["relative_path"]]
        for item in document["source_files"]
        if item["role"] != "receptacle"
    }
    _verify_urdf(document, role_paths["urdf"])
    _verify_ao_config(document, role_paths["ao_config"])

    return {
        "schema_version": "vista.playable-articulated-fridge-source-receipt/v1",
        "accepted": False,
        "status": "source_verified_pending_ue_import_runtime_and_human_review",
        "contract_id": document["contract_id"],
        "contract_content_digest": document["content_digest"],
        "dataset_revision": document["dataset"]["revision"],
        "model_id": document["source_model"]["model_id"],
        "source_file_count": len(document["source_files"]),
        "metadata_file_count": len(document["metadata_evidence"]),
        "link_count": len(document["links"]),
        "joint_count": len(document["joints"]),
        "receptacle_count": len(document["receptacles"]),
        "ue_imported": False,
        "runtime_verified": False,
        "human_reviewed": False,
        "gta_quality": False,
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, default=CONTRACT_PATH)
    parser.add_argument("--hssd-root", type=Path, default=DEFAULT_HSSD_ROOT)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    document = load_contract(args.contract)
    result = verify_source_tree(document, args.hssd_root)
    print(json.dumps(result, allow_nan=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
