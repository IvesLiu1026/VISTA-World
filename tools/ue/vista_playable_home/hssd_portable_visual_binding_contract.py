#!/usr/bin/env python3
"""Validate the closed HSSD presentation binding for two portable pickups.

This validator reads only Git-tracked metadata.  HSSD payload bytes stay outside
Git and are never resolved here.  The contract deliberately binds an already
imported HSSD StaticMesh to the presentation child of an authoritative
``AVistaPickupActor``; it never replaces that actor's collision/physics root.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

import jsonschema


SCHEMA_VERSION = "vista.playable-hssd-portable-visual-binding/v1"
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SCHEMA_PATH = (
    REPOSITORY_ROOT
    / "world_packs/schemas/vista-playable-hssd-portable-visual-binding-v1.schema.json"
)
CONTRACT_PATH = (
    REPOSITORY_ROOT / "world_packs/vista_playable_home_r1/visual_bindings/"
    "hssd_portable_pickups_r1.json"
)
HOUSE_PATH = REPOSITORY_ROOT / "world_packs/vista_playable_home_r1/house.json"
PROFILE_PATH = (
    REPOSITORY_ROOT / "world_packs/vista_playable_home_r1/visual_profiles/"
    "hssd_private_research_r1.json"
)
EXPECTED_SEMANTIC_IDS = (
    "home.r1/room.kitchen_dining/entity.coffee_cup.01",
    "home.r1/room.living_room/entity.slipper.01",
)
EXPECTED_BINDINGS = {
    EXPECTED_SEMANTIC_IDS[0]: {
        "instance_id": "hssd.r1/kitchen_dining.coffee_cup.01",
        "source_asset_id": "hssd.static.coffee_cup",
        "root_asset_ref": "asset.prop.coffee_cup",
        "root_mesh": "/Game/VISTA/PlayableHome/vista_playable_home_r1/Assets/asset_prop_coffee_cup/asset_prop_coffee_cup.asset_prop_coffee_cup",
        "hssd_mesh": "/Game/VISTA/PlayableHome/hssd_private_research_r5_phase1_diagnostic/HSSDPrivateResearch/Assets/hssd_static_coffee_cup/hssd_static_coffee_cup.hssd_static_coffee_cup",
        "shell_label": "VISTA_HSSD_R7_hssd_r1_kitchen_dining_coffee_cup_01",
        "pickup_label": "VISTA_home_r1_room_kitchen_dining_entity_coffee_cup_01",
        "profile_semantic_target": EXPECTED_SEMANTIC_IDS[0],
        "source_shell_world_transform_cm": {
            "location_cm": [345, -220, 76.9894],
            "rotation_deg": [0, 0, 0],
            "scale": [1, 1, 1],
        },
        "interaction_authority": "hidden_r1_proxy_query_authority_repaired",
    },
    EXPECTED_SEMANTIC_IDS[1]: {
        "instance_id": "hssd.r1/living_room.slipper.01",
        "source_asset_id": "hssd.static.flip_flops",
        "root_asset_ref": "asset.prop.slipper",
        "root_mesh": "/Game/VISTA/PlayableHome/vista_playable_home_r1/Assets/asset_prop_slipper/asset_prop_slipper.asset_prop_slipper",
        "hssd_mesh": "/Game/VISTA/PlayableHome/hssd_private_research_r5_phase1_diagnostic/HSSDPrivateResearch/Assets/hssd_static_flip_flops/hssd_static_flip_flops.hssd_static_flip_flops",
        "shell_label": "VISTA_HSSD_R7_hssd_r1_living_room_slipper_01",
        "pickup_label": "VISTA_home_r1_room_living_room_entity_slipper_01",
        "profile_semantic_target": None,
        # The accepted diagnostic source map deliberately offsets the visual
        # dressing 30 cm from the semantic slipper.  The binding moves the
        # HSSD mesh to the semantic actor (identity child transform), but must
        # first prove this exact historical shell before deleting it.
        "source_shell_world_transform_cm": {
            "location_cm": [-260, -280, 3],
            "rotation_deg": [0, 0, 25],
            "scale": [1, 1, 1],
        },
        "interaction_authority": "none_visual_dressing",
    },
}


class PortableVisualBindingContractError(RuntimeError):
    """The closed contract or its HouseSpec/HSSD profile binding differs."""


def _require(condition: Any, message: str) -> None:
    if not condition:
        raise PortableVisualBindingContractError(message)


def _duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        _require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise PortableVisualBindingContractError(f"non-finite JSON constant: {value}")


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
        raise PortableVisualBindingContractError(
            "document is not finite canonical JSON"
        ) from exc


def content_digest(value: Mapping[str, Any]) -> str:
    body = copy.deepcopy(dict(value))
    body.pop("content_digest", None)
    return hashlib.sha256(canonical_json_bytes(body)).hexdigest()


def _load_json(path: Path | str, label: str) -> dict[str, Any]:
    try:
        value = json.loads(
            Path(path).read_text(encoding="utf-8"),
            object_pairs_hook=_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except PortableVisualBindingContractError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PortableVisualBindingContractError(
            f"{label} is not strict UTF-8 JSON"
        ) from exc
    _require(type(value) is dict, f"{label} root must be one object")
    return value


def load_contract(path: Path | str = CONTRACT_PATH) -> dict[str, Any]:
    return _load_json(path, "portable visual-binding contract")


def _schema() -> dict[str, Any]:
    schema = _load_json(SCHEMA_PATH, "portable visual-binding schema")
    try:
        jsonschema.Draft202012Validator.check_schema(schema)
    except jsonschema.SchemaError as exc:
        raise PortableVisualBindingContractError(
            "portable visual-binding schema is invalid"
        ) from exc
    return schema


def _quaternion(rotation_deg: Sequence[float]) -> tuple[float, float, float, float]:
    roll, pitch, yaw = (math.radians(float(value)) / 2.0 for value in rotation_deg)
    cr, sr = math.cos(roll), math.sin(roll)
    cp, sp = math.cos(pitch), math.sin(pitch)
    cy, sy = math.cos(yaw), math.sin(yaw)
    return (
        cr * cp * cy + sr * sp * sy,
        sr * cp * cy - cr * sp * sy,
        cr * sp * cy + sr * cp * sy,
        cr * cp * sy - sr * sp * cy,
    )


def _qmul(
    left: Sequence[float], right: Sequence[float]
) -> tuple[float, float, float, float]:
    lw, lx, ly, lz = left
    rw, rx, ry, rz = right
    return (
        lw * rw - lx * rx - ly * ry - lz * rz,
        lw * rx + lx * rw + ly * rz - lz * ry,
        lw * ry - lx * rz + ly * rw + lz * rx,
        lw * rz + lx * ry - ly * rx + lz * rw,
    )


def _qrotate(quaternion: Sequence[float], vector: Sequence[float]) -> list[float]:
    value = (0.0, *(float(item) for item in vector))
    conjugate = (quaternion[0], -quaternion[1], -quaternion[2], -quaternion[3])
    rotated = _qmul(_qmul(quaternion, value), conjugate)
    return [rotated[1], rotated[2], rotated[3]]


def _euler(quaternion: Sequence[float]) -> list[float]:
    w, x, y, z = quaternion
    roll = math.atan2(2 * (w * x + y * z), 1 - 2 * (x * x + y * y))
    sin_pitch = 2 * (w * y - z * x)
    pitch = (
        math.copysign(math.pi / 2, sin_pitch)
        if abs(sin_pitch) >= 1
        else math.asin(sin_pitch)
    )
    yaw = math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))
    return [math.degrees(value) for value in (roll, pitch, yaw)]


def _world_transform(
    parent: Mapping[str, Sequence[float]], local: Mapping[str, Sequence[float]]
) -> dict[str, list[float]]:
    parent_q = _quaternion(parent["rotation_deg"])
    local_q = _quaternion(local["rotation_deg"])
    scaled = [
        float(local["location_m"][axis]) * float(parent["scale"][axis])
        for axis in range(3)
    ]
    rotated = _qrotate(parent_q, scaled)
    return {
        "location_cm": [
            (float(parent["location_m"][axis]) + rotated[axis]) * 100.0
            for axis in range(3)
        ],
        "rotation_deg": _euler(_qmul(parent_q, local_q)),
        "scale": [
            float(parent["scale"][axis]) * float(local["scale"][axis])
            for axis in range(3)
        ],
    }


def _transform_matches(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    return (
        all(
            math.isclose(float(a), float(b), rel_tol=0.0, abs_tol=1e-5)
            for a, b in zip(left["location_cm"], right["location_cm"], strict=True)
        )
        and all(
            abs((float(a) - float(b) + 180.0) % 360.0 - 180.0) <= 1e-5
            for a, b in zip(left["rotation_deg"], right["rotation_deg"], strict=True)
        )
        and all(
            math.isclose(float(a), float(b), rel_tol=0.0, abs_tol=1e-8)
            for a, b in zip(left["scale"], right["scale"], strict=True)
        )
    )


def _unique(rows: Sequence[Mapping[str, Any]], key: str, value: str, label: str):
    matches = [row for row in rows if row.get(key) == value]
    _require(len(matches) == 1, f"{label} is not unique: {value}")
    return matches[0]


def validate_contract(
    document: Mapping[str, Any],
    *,
    house_path: Path | str = HOUSE_PATH,
    profile_path: Path | str = PROFILE_PATH,
) -> None:
    errors = sorted(
        jsonschema.Draft202012Validator(_schema()).iter_errors(document),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    _require(
        not errors,
        f"schema validation failed: {errors[0].message}" if errors else "",
    )
    _require(document["schema_version"] == SCHEMA_VERSION, "schema version differs")
    _require(
        document["content_digest"] == content_digest(document),
        "contract content digest differs",
    )

    house = _load_json(house_path, "HouseSpec")
    profile = _load_json(profile_path, "HSSD profile")
    _require(
        house.get("content_digest") == content_digest(house), "HouseSpec digest differs"
    )
    _require(
        profile.get("content_digest") == content_digest(profile),
        "HSSD profile digest differs",
    )
    _require(
        document["house_binding"]
        == {
            "house_id": house.get("house_id"),
            "revision": house.get("revision"),
            "content_digest": house.get("content_digest"),
        },
        "HouseSpec binding differs",
    )
    _require(
        document["source_profile_binding"]
        == {
            "schema_version": profile.get("schema_version"),
            "profile_id": profile.get("profile_id"),
            "content_digest": profile.get("content_digest"),
        },
        "HSSD profile binding differs",
    )
    _require(
        profile.get("house_id") == house.get("house_id")
        and profile.get("house_revision") == house.get("revision")
        and profile.get("source_house_content_digest") == house.get("content_digest"),
        "HSSD profile does not target the bound HouseSpec",
    )
    bindings = document["bindings"]
    _require(
        tuple(row["semantic_id"] for row in bindings) == EXPECTED_SEMANTIC_IDS,
        "portable binding semantic order differs",
    )
    for binding in bindings:
        semantic = binding["semantic_id"]
        expected = EXPECTED_BINDINGS[semantic]
        entity = _unique(house["entities"], "entity_id", semantic, "HouseSpec entity")
        room = _unique(house["rooms"], "room_id", entity["room_id"], "HouseSpec room")
        placement = _unique(
            profile["placements"],
            "instance_id",
            expected["instance_id"],
            "HSSD placement",
        )
        _unique(
            profile["source_assets"],
            "source_asset_id",
            expected["source_asset_id"],
            "HSSD source asset",
        )
        _require(
            entity.get("component_role") == "pickup"
            and entity.get("mobility") == "simulated"
            and entity.get("collision_policy") == "pickup_physics"
            and entity.get("asset_ref") == expected["root_asset_ref"]
            and entity.get("initial_state", {}).get("portable") is True
            and {"pick_up", "drop", "place", "inspect"}.issubset(
                set(entity.get("affordances", []))
            ),
            f"portable HouseSpec authority differs: {semantic}",
        )
        _require(
            binding["room_id"] == entity["room_id"] == placement["room_id"]
            and binding["hssd_instance_id"] == expected["instance_id"]
            and binding["source_asset_id"] == expected["source_asset_id"]
            and placement["source_asset_id"] == expected["source_asset_id"]
            and placement["semantic_target_id"] == expected["profile_semantic_target"],
            f"HSSD/HouseSpec identity binding differs: {semantic}",
        )
        _require(
            binding["hssd_mesh_object_path"] == expected["hssd_mesh"]
            and binding["pickup_root_mesh_object_path"] == expected["root_mesh"]
            and binding["shell_actor_label"] == expected["shell_label"]
            and binding["pickup_actor_label"] == expected["pickup_label"],
            f"closed actor/mesh path binding differs: {semantic}",
        )
        expected_shell_tags = {
            "VistaRole=hssd_visual_shell",
            "VistaHssdInstanceId=" + expected["instance_id"],
            "VistaHssdSourceAssetId=" + expected["source_asset_id"],
            "VistaRoomId=" + binding["room_id"],
            "VistaHssdDiagnosticOnly=true",
            "VistaHssdFullMaterialFidelity=false",
            "VistaHssdPromotable=false",
            "VistaHssdInteractionAuthority=" + expected["interaction_authority"],
        }
        if expected["profile_semantic_target"] is not None:
            expected_shell_tags.add("VistaHssdSemanticTargetId=" + semantic)
        _require(
            set(binding["shell_required_tags"]) == expected_shell_tags
            and set(binding["pickup_required_tags"])
            == {"VistaRole=pickup", "VistaSemanticId=" + semantic}
            and binding["shell_semantic_target_tag"]
            == (
                "VistaHssdSemanticTargetId=" + semantic
                if expected["profile_semantic_target"] is not None
                else None
            ),
            f"closed exact-tag binding differs: {semantic}",
        )
        _require(
            placement["transform"].get("coordinate_frame") == "room_local_m"
            and _transform_matches(
                binding["shell_world_transform_cm"],
                expected["source_shell_world_transform_cm"],
            )
            and _transform_matches(
                binding["pickup_world_transform_cm"],
                _world_transform(room["transform"], entity["transform"]),
            ),
            f"closed world transform differs: {semantic}",
        )
        _require(
            binding["presentation_relative_transform"]
            == {
                "location_cm": [0, 0, 0],
                "rotation_deg": [0, 0, 0],
                "scale": [1, 1, 1],
            },
            f"presentation transform is not identity: {semantic}",
        )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, default=CONTRACT_PATH)
    parser.add_argument("--house", type=Path, default=HOUSE_PATH)
    parser.add_argument("--profile", type=Path, default=PROFILE_PATH)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        document = load_contract(args.contract)
        validate_contract(document, house_path=args.house, profile_path=args.profile)
    except PortableVisualBindingContractError as exc:
        print(f"VISTA_HSSD_PORTABLE_BINDING_CONTRACT_FAILED: {exc}")
        return 1
    print(
        "VISTA_HSSD_PORTABLE_BINDING_CONTRACT_RESULT:"
        + json.dumps(
            {
                "status": "validated_source_only",
                "contract_id": document["contract_id"],
                "content_digest": document["content_digest"],
                "external_payload_resolved": False,
                "ue_launched": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
