"""Fail-closed host-side contract for the HSSD six-room research profile.

The validator intentionally performs no Blender, Unreal, network, or payload
mutation.  It validates the portable Git-side manifest only; a later build must
still resolve the pinned external files and emit per-asset transport receipts.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import pathlib
from collections import Counter
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

import jsonschema


SCHEMA_VERSION = "simworld.vista.playable-home-hssd-private-research-profile/v1"
SCHEMA_PATH = (
    pathlib.Path(__file__).resolve().parents[2]
    / "world_packs"
    / "schemas"
    / "vista-playable-home-hssd-private-research-profile-v1.schema.json"
)
EXPECTED_ROOMS = (
    "home.r1/room.entry_hall",
    "home.r1/room.living_room",
    "home.r1/room.kitchen_dining",
    "home.r1/room.bedroom",
    "home.r1/room.office",
    "home.r1/room.bathroom_laundry",
)
EXPECTED_ARTICULATION_ROLES = frozenset({"fridge", "desk", "nightstand", "wardrobe", "stove"})
CORE_ROOM_CATEGORIES = {
    "home.r1/room.living_room": frozenset({"sofa", "coffee_table"}),
    "home.r1/room.kitchen_dining": frozenset({"fridge", "stove", "dining_table"}),
    "home.r1/room.office": frozenset({"desk", "rolling_chair", "cabinet"}),
    "home.r1/room.bedroom": frozenset({"bed", "nightstand"}),
}
PROHIBITED_KEYS = frozenset(
    {
        "execute_python_script",
        "python_code",
        "shell_command",
        "caller_script",
        "render_script",
        "filesystem_write",
        "auth_token",
        "access_token",
        "oracle_label",
        "oracle_assistance_required",
        "private_evidence",
        "review_notes",
        "payload_root",
        "absolute_path",
    }
)


@dataclass(frozen=True)
class HssdPrivateResearchProfileError(Exception):
    code: str
    path: str
    message: str

    def __str__(self) -> str:
        return f"{self.code} at {self.path}: {self.message}"


def _fail(code: str, path: str, message: str) -> None:
    raise HssdPrivateResearchProfileError(code, path, message)


def canonical_json_bytes(value: Any) -> bytes:
    try:
        text = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"), sort_keys=True)
    except (TypeError, ValueError, OverflowError) as exc:
        raise HssdPrivateResearchProfileError(
            "VISTA_HSSD_PROFILE_CANONICAL_JSON_INVALID",
            "$",
            "Document is not finite canonical JSON",
        ) from exc
    return text.encode("utf-8", "strict")


def content_digest(value: Mapping[str, Any]) -> str:
    body = copy.deepcopy(dict(value))
    body.pop("content_digest", None)
    return hashlib.sha256(canonical_json_bytes(body)).hexdigest()


def seal_document(value: Mapping[str, Any]) -> dict[str, Any]:
    sealed = copy.deepcopy(dict(value))
    sealed["content_digest"] = content_digest(sealed)
    return sealed


def _reject_constant(value: str) -> None:
    _fail("VISTA_HSSD_PROFILE_JSON_NON_FINITE", "$", f"JSON constant {value!r} is prohibited")


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("VISTA_HSSD_PROFILE_DUPLICATE_KEY", "$", "Duplicate JSON object key is prohibited")
        result[key] = value
    return result


def load_json(path: pathlib.Path | str) -> dict[str, Any]:
    source = pathlib.Path(path)
    try:
        parsed = json.loads(
            source.read_text(encoding="utf-8"),
            parse_constant=_reject_constant,
            object_pairs_hook=_reject_duplicate_keys,
        )
    except HssdPrivateResearchProfileError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise HssdPrivateResearchProfileError(
            "VISTA_HSSD_PROFILE_JSON_INVALID",
            "$",
            "Input is not strict UTF-8 JSON",
        ) from exc
    if type(parsed) is not dict:
        _fail("VISTA_HSSD_PROFILE_JSON_INVALID", "$", "Top-level JSON value must be an object")
    _assert_finite(parsed)
    return parsed


def _assert_finite(value: Any, path: str = "$", depth: int = 0) -> None:
    if depth > 96:
        _fail("VISTA_HSSD_PROFILE_JSON_TOO_DEEP", path, "JSON nesting exceeds the limit")
    if type(value) is float and not math.isfinite(value):
        _fail("VISTA_HSSD_PROFILE_JSON_NON_FINITE", path, "Non-finite numbers are prohibited")
    if type(value) is dict:
        for key, child in value.items():
            if type(key) is not str:
                _fail("VISTA_HSSD_PROFILE_JSON_INVALID", path, "Object keys must be strings")
            _assert_finite(child, f"{path}.{key}", depth + 1)
    elif type(value) is list:
        for index, child in enumerate(value):
            _assert_finite(child, f"{path}[{index}]", depth + 1)


def _scan_prohibited(value: Any, path: str = "$") -> None:
    if type(value) is dict:
        for key, child in value.items():
            normalized = key.strip().lower().replace("-", "_")
            if normalized in PROHIBITED_KEYS:
                _fail(
                    "VISTA_HSSD_PROFILE_PROHIBITED_FIELD",
                    f"{path}.{key}",
                    "Executable, private, or payload-root field is prohibited",
                )
            _scan_prohibited(child, f"{path}.{key}")
    elif type(value) is list:
        for index, child in enumerate(value):
            _scan_prohibited(child, f"{path}[{index}]")
    elif type(value) is str:
        lowered = value.strip().lower()
        if lowered.startswith(("/home/", "/root/", "/mnt/", "/nas/", "file://")):
            _fail(
                "VISTA_HSSD_PROFILE_PRIVATE_PATH_PROHIBITED",
                path,
                "Absolute private paths are prohibited; payloads stay outside Git",
            )


def _schema() -> dict[str, Any]:
    try:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator.check_schema(schema)
    except (OSError, json.JSONDecodeError, jsonschema.SchemaError) as exc:
        raise HssdPrivateResearchProfileError(
            "VISTA_HSSD_PROFILE_SCHEMA_UNAVAILABLE",
            "$",
            "Pinned HSSD private-research schema is unavailable",
        ) from exc
    return schema


def _json_path(error: jsonschema.ValidationError) -> str:
    path = "$"
    for part in error.absolute_path:
        path += f"[{part}]" if type(part) is int else f".{part}"
    return path


def _validate_schema(profile: Mapping[str, Any]) -> None:
    errors = sorted(
        jsonschema.Draft202012Validator(_schema()).iter_errors(profile),
        key=lambda error: (
            tuple(str(part) for part in error.absolute_path),
            error.validator or "",
            error.message,
        ),
    )
    if errors:
        error = errors[0]
        _fail(
            "VISTA_HSSD_PROFILE_SCHEMA_INVALID",
            _json_path(error),
            f"Schema constraint {error.validator!r} failed",
        )


def _require_unique(values: Iterable[str], path: str, label: str) -> None:
    seen: set[str] = set()
    for value in values:
        if value in seen:
            _fail("VISTA_HSSD_PROFILE_DUPLICATE_ID", path, f"Duplicate {label}: {value}")
        seen.add(value)


def _validate_relative_path(path_value: str, path: str) -> None:
    candidate = pathlib.PurePosixPath(path_value)
    if (
        candidate.is_absolute()
        or "\\" in path_value
        or "%" in path_value
        or any(part in {"", ".", ".."} for part in candidate.parts)
    ):
        _fail("VISTA_HSSD_PROFILE_PATH_UNSAFE", path, "Relative payload path is unsafe")


def _validate_sources(profile: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    sources = profile["source_assets"]
    _require_unique((item["source_asset_id"] for item in sources), "$.source_assets", "source asset ID")
    _require_unique((item["model_id"] for item in sources), "$.source_assets", "HSSD model ID")
    indexed = {item["source_asset_id"]: item for item in sources}
    for index, source in enumerate(sources):
        model_id = source["model_id"]
        category = source["semantic_category"]
        if source["source_asset_id"] != f"hssd.static.{category}":
            _fail(
                "VISTA_HSSD_PROFILE_SOURCE_ID_MISMATCH",
                f"$.source_assets[{index}].source_asset_id",
                "Source asset ID must be derived from its exact semantic category",
            )
        expected_render = f"objects/{model_id[0]}/{model_id}.glb"
        expected_config = f"objects/{model_id[0]}/{model_id}.object_config.json"
        if source["render_asset_relpath"] != expected_render:
            _fail(
                "VISTA_HSSD_PROFILE_SOURCE_PATH_MISMATCH",
                f"$.source_assets[{index}].render_asset_relpath",
                "Render path does not match the pinned model ID",
            )
        if source["object_config_relpath"] != expected_config:
            _fail(
                "VISTA_HSSD_PROFILE_SOURCE_PATH_MISMATCH",
                f"$.source_assets[{index}].object_config_relpath",
                "Object-config path does not match the pinned model ID",
            )
        _validate_relative_path(source["render_asset_relpath"], f"$.source_assets[{index}].render_asset_relpath")
        _validate_relative_path(source["object_config_relpath"], f"$.source_assets[{index}].object_config_relpath")
        if source["source_basisu_required"] is not True:
            _fail(
                "VISTA_HSSD_PROFILE_BASISU_REQUIRED",
                f"$.source_assets[{index}].source_basisu_required",
                "Every pinned HSSD static source in this profile requires BasisU transport",
            )
        if source["interaction_authority"] != "none_static_joined_glb":
            _fail(
                "VISTA_HSSD_PROFILE_STATIC_INTERACTION_LIE",
                f"$.source_assets[{index}].interaction_authority",
                "A static joined GLB cannot claim interaction authority",
            )
    return indexed


def _validate_catalog_semantic_receipts(
    profile: Mapping[str, Any], sources: Mapping[str, Mapping[str, Any]]
) -> None:
    receipts = profile["catalog_semantic_receipts"]
    _require_unique(
        (item["source_asset_id"] for item in receipts),
        "$.catalog_semantic_receipts",
        "catalog semantic source asset ID",
    )
    _require_unique(
        (item["model_id"] for item in receipts),
        "$.catalog_semantic_receipts",
        "catalog semantic HSSD model ID",
    )
    indexed = {item["source_asset_id"]: item for item in receipts}
    if set(indexed) != set(sources):
        _fail(
            "VISTA_HSSD_PROFILE_CATALOG_COVERAGE_NOT_CLOSED",
            "$.catalog_semantic_receipts",
            "Every static source requires exactly one reviewed catalog receipt",
        )
    for source_asset_id, source in sources.items():
        receipt = indexed[source_asset_id]
        if (
            receipt["model_id"] != source["model_id"]
            or receipt["reviewed_semantic_category"]
            != source["semantic_category"]
            or receipt["review_status"]
            != "catalog_verified_identity_visual_review_pending"
        ):
            _fail(
                "VISTA_HSSD_PROFILE_CATALOG_IDENTITY_MISMATCH",
                "$.catalog_semantic_receipts",
                f"Catalog identity differs from source {source_asset_id}",
            )


def _validate_room_local_point(
    point: Iterable[float],
    room_id: str,
    rooms: Mapping[str, Mapping[str, Any]],
    path: str,
) -> None:
    room = rooms[room_id]
    bounds = room["bounds_m"]
    values = list(point)
    if not all(low <= value <= high for value, low, high in zip(values, bounds["min_m"], bounds["max_m"])):
        _fail("VISTA_HSSD_PROFILE_PLACEMENT_OUTSIDE_ROOM", path, "Room-local placement origin is outside room bounds")


def _validate_placements(
    profile: Mapping[str, Any],
    sources: Mapping[str, Mapping[str, Any]],
    house: Mapping[str, Any] | None,
) -> Counter[str]:
    placements = profile["placements"]
    _require_unique((item["instance_id"] for item in placements), "$.placements", "placement ID")
    semantic_targets = [item["semantic_target_id"] for item in placements if item["semantic_target_id"] is not None]
    _require_unique(semantic_targets, "$.placements", "semantic target")
    known_entities: set[str] | None = None
    rooms: dict[str, Mapping[str, Any]] | None = None
    if house is not None:
        known_entities = {entity["entity_id"] for entity in house["entities"]}
        rooms = {room["room_id"]: room for room in house["rooms"]}

    counts: Counter[str] = Counter()
    room_categories: dict[str, set[str]] = {room_id: set() for room_id in EXPECTED_ROOMS}
    referenced_sources: set[str] = set()
    for index, placement in enumerate(placements):
        source = sources.get(placement["source_asset_id"])
        if source is None:
            _fail(
                "VISTA_HSSD_PROFILE_SOURCE_UNKNOWN",
                f"$.placements[{index}].source_asset_id",
                "Placement references an unknown source asset",
            )
        room_id = placement["room_id"]
        counts[room_id] += 1
        room_categories[room_id].add(source["semantic_category"])
        referenced_sources.add(placement["source_asset_id"])
        target = placement["semantic_target_id"]
        intent = placement["placement_intent"]
        if intent["role"] == "semantic_hero" and target is None:
            _fail(
                "VISTA_HSSD_PROFILE_SEMANTIC_TARGET_REQUIRED",
                f"$.placements[{index}].semantic_target_id",
                "Semantic hero placement requires an authoritative r1 target",
            )
        if intent["role"] != "semantic_hero" and target is not None:
            _fail(
                "VISTA_HSSD_PROFILE_SEMANTIC_TARGET_UNEXPECTED",
                f"$.placements[{index}].semantic_target_id",
                "Only semantic hero placements may bind authoritative targets",
            )
        if target is not None:
            room_prefix = f"{room_id}/entity."
            if not target.startswith(room_prefix):
                _fail(
                    "VISTA_HSSD_PROFILE_SEMANTIC_ROOM_MISMATCH",
                    f"$.placements[{index}].semantic_target_id",
                    "Semantic target belongs to another room",
                )
            if known_entities is not None and target not in known_entities:
                _fail(
                    "VISTA_HSSD_PROFILE_SEMANTIC_TARGET_UNKNOWN",
                    f"$.placements[{index}].semantic_target_id",
                    "Semantic target is absent from the pinned house",
                )
        if rooms is not None:
            if room_id not in rooms:
                _fail("VISTA_HSSD_PROFILE_ROOM_UNKNOWN", f"$.placements[{index}].room_id", "Room is absent")
            _validate_room_local_point(
                placement["transform"]["location_m"],
                room_id,
                rooms,
                f"$.placements[{index}].transform.location_m",
            )

    if set(counts) != set(EXPECTED_ROOMS) or any(counts[room_id] < 8 for room_id in EXPECTED_ROOMS):
        _fail(
            "VISTA_HSSD_PROFILE_ROOM_COVERAGE_INSUFFICIENT",
            "$.placements",
            "All six rooms require at least eight purposeful HSSD placements",
        )
    if len(placements) < 60:
        _fail("VISTA_HSSD_PROFILE_TOTAL_COVERAGE_INSUFFICIENT", "$.placements", "Profile requires at least 60 placements")
    for room_id, required in CORE_ROOM_CATEGORIES.items():
        missing = required - room_categories[room_id]
        if missing:
            _fail(
                "VISTA_HSSD_PROFILE_HERO_COVERAGE_INSUFFICIENT",
                "$.placements",
                f"Core room {room_id} lacks categories: {sorted(missing)}",
            )
    if referenced_sources != set(sources):
        _fail(
            "VISTA_HSSD_PROFILE_SOURCE_COVERAGE_NOT_CLOSED",
            "$.placements",
            "Every declared static source must be used by a placement",
        )
    return counts


def _validate_articulation(
    profile: Mapping[str, Any], sources: Mapping[str, Mapping[str, Any]]
) -> None:
    candidates = profile["articulated_sibling_candidates"]
    _require_unique((item["semantic_role"] for item in candidates), "$.articulated_sibling_candidates", "role")
    _require_unique((item["candidate_model_id"] for item in candidates), "$.articulated_sibling_candidates", "model ID")
    if {item["semantic_role"] for item in candidates} != EXPECTED_ARTICULATION_ROLES:
        _fail(
            "VISTA_HSSD_PROFILE_ARTICULATION_COVERAGE_INVALID",
            "$.articulated_sibling_candidates",
            "Fridge, desk, nightstand, wardrobe and stove candidates are required",
        )
    for index, candidate in enumerate(candidates):
        source = sources.get(candidate["static_source_asset_id"])
        if source is None:
            _fail(
                "VISTA_HSSD_PROFILE_SOURCE_UNKNOWN",
                f"$.articulated_sibling_candidates[{index}].static_source_asset_id",
                "Articulation candidate references an unknown static visual shell",
            )
        if candidate["semantic_role"] == "wardrobe":
            if source["semantic_category"] != "cabinet":
                _fail(
                    "VISTA_HSSD_PROFILE_ARTICULATION_SOURCE_MISMATCH",
                    f"$.articulated_sibling_candidates[{index}].static_source_asset_id",
                    "Wardrobe candidate must correspond to the cabinet visual shell",
                )
        elif source["semantic_category"] != candidate["semantic_role"]:
            _fail(
                "VISTA_HSSD_PROFILE_ARTICULATION_SOURCE_MISMATCH",
                f"$.articulated_sibling_candidates[{index}].static_source_asset_id",
                "Articulation role does not match its static visual shell",
            )
        model_id = candidate["candidate_model_id"]
        expected_urdf = f"urdf/{model_id}/{model_id}.urdf"
        expected_config = f"urdf/{model_id}/{model_id}.ao_config.json"
        if candidate["urdf_relpath"] != expected_urdf or candidate["ao_config_relpath"] != expected_config:
            _fail(
                "VISTA_HSSD_PROFILE_ARTICULATION_PATH_MISMATCH",
                f"$.articulated_sibling_candidates[{index}]",
                "Articulation paths do not match the candidate model ID",
            )
        _validate_relative_path(candidate["urdf_relpath"], f"$.articulated_sibling_candidates[{index}].urdf_relpath")
        _validate_relative_path(
            candidate["ao_config_relpath"],
            f"$.articulated_sibling_candidates[{index}].ao_config_relpath",
        )
        pending_fields = ("selection_status", "validation_status", "ue_integration_status")
        if any(candidate[field] != "pending" for field in pending_fields):
            _fail(
                "VISTA_HSSD_PROFILE_ARTICULATION_NOT_PENDING",
                f"$.articulated_sibling_candidates[{index}]",
                "Located URDF siblings remain pending until selection, validation and UE integration pass",
            )
        if (
            candidate["articulation_authority"] != "blocked_until_validated"
            or candidate["static_fallback_policy"] != "presentation_only_never_interactive"
        ):
            _fail(
                "VISTA_HSSD_PROFILE_STATIC_INTERACTION_LIE",
                f"$.articulated_sibling_candidates[{index}]",
                "Static joined GLBs may not be presented as articulated interaction assets",
            )


def _validate_coverage(profile: Mapping[str, Any], counts: Counter[str]) -> None:
    coverage = profile["coverage"]
    if set(coverage["required_room_ids"]) != set(EXPECTED_ROOMS):
        _fail("VISTA_HSSD_PROFILE_ROOM_COVERAGE_NOT_CLOSED", "$.coverage.required_room_ids", "Room scope is not closed")
    observed_counts = {room_id.rsplit(".", 1)[-1]: counts[room_id] for room_id in EXPECTED_ROOMS}
    if coverage["room_instance_counts"] != observed_counts:
        _fail(
            "VISTA_HSSD_PROFILE_COVERAGE_COUNT_MISMATCH",
            "$.coverage.room_instance_counts",
            "Declared per-room counts do not match placements",
        )
    source_ids = {item["source_asset_id"] for item in profile["source_assets"]}
    placement_ids = {item["instance_id"] for item in profile["placements"]}
    articulation_roles = {item["semantic_role"] for item in profile["articulated_sibling_candidates"]}
    if set(coverage["closed_source_asset_ids"]) != source_ids:
        _fail(
            "VISTA_HSSD_PROFILE_SOURCE_COVERAGE_NOT_CLOSED",
            "$.coverage.closed_source_asset_ids",
            "Closed source index differs from declared sources",
        )
    if set(coverage["closed_placement_ids"]) != placement_ids:
        _fail(
            "VISTA_HSSD_PROFILE_PLACEMENT_COVERAGE_NOT_CLOSED",
            "$.coverage.closed_placement_ids",
            "Closed placement index differs from declared placements",
        )
    if set(coverage["closed_articulation_roles"]) != articulation_roles:
        _fail(
            "VISTA_HSSD_PROFILE_ARTICULATION_COVERAGE_INVALID",
            "$.coverage.closed_articulation_roles",
            "Closed articulation index differs from declared pending candidates",
        )


def validate_profile(profile: Mapping[str, Any], house: Mapping[str, Any] | None = None) -> None:
    """Validate the Git-side HSSD profile without resolving external payloads."""

    _assert_finite(profile)
    _scan_prohibited(profile)
    _validate_schema(profile)
    if profile["content_digest"] != content_digest(profile):
        _fail("VISTA_HSSD_PROFILE_DIGEST_MISMATCH", "$.content_digest", "Profile content digest mismatch")
    if house is not None:
        if profile["house_revision"] != house.get("revision"):
            _fail(
                "VISTA_HSSD_PROFILE_STALE_HOUSE_REVISION",
                "$.house_revision",
                "Profile targets a different house revision",
            )
        if profile["source_house_content_digest"] != house.get("content_digest"):
            _fail(
                "VISTA_HSSD_PROFILE_STALE_HOUSE_DIGEST",
                "$.source_house_content_digest",
                "Profile targets different house content",
            )
    sources = _validate_sources(profile)
    _validate_catalog_semantic_receipts(profile, sources)
    counts = _validate_placements(profile, sources, house)
    _validate_articulation(profile, sources)
    _validate_coverage(profile, counts)
