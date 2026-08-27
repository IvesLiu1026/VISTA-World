"""Purposeful deterministic dressing anchors and protected clearances."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .config import ForgeInputError, content_digest, require_mapping, vector3


@dataclass(frozen=True)
class DressingAnchorSpec:
    anchor_id: str
    room_id: str
    purpose: str
    location_m: tuple[float, float, float]
    surface_normal: tuple[float, float, float]
    clearance_radius_m: float
    allowed_categories: tuple[str, ...]
    deterministic_yaw_deg: float


@dataclass(frozen=True)
class ExclusionVolumeSpec:
    exclusion_id: str
    room_id: str
    exclusion_kind: str
    min_m: tuple[float, float, float]
    max_m: tuple[float, float, float]
    source_id: str


@dataclass(frozen=True)
class DressingInstanceSpec:
    instance_id: str
    room_id: str
    logical_asset_id: str
    source_receipt_id: str
    location_m: tuple[float, float, float]
    rotation_deg: tuple[float, float, float]
    scale: tuple[float, float, float]
    collision_policy: str
    semantic_behavior: str


@dataclass(frozen=True)
class DressingPlan:
    seed: int
    placement_policy: str
    anchors: tuple[DressingAnchorSpec, ...]
    exclusions: tuple[ExclusionVolumeSpec, ...]
    profile_instances: tuple[DressingInstanceSpec, ...]
    content_digest: str


def _stable_yaw(seed: int, anchor_id: str) -> float:
    digest = hashlib.sha256(f"{seed}:{anchor_id}".encode("utf-8")).digest()
    unit = int.from_bytes(digest[:4], "big") / 0xFFFFFFFF
    return round(-7.5 + unit * 15.0, 3)


def _portal_exclusion(room: Any, opening: Any) -> ExclusionVolumeSpec:
    x0, y0, z0 = room.bounds_min_m
    x1, y1, _ = room.bounds_max_m
    half = opening.width_m / 2 + 0.25
    depth = 1.0
    if opening.wall_side == "west":
        minimum, maximum = (x0 - 0.05, opening.center_offset_m - half, z0), (x0 + depth, opening.center_offset_m + half, 2.3)
    elif opening.wall_side == "east":
        minimum, maximum = (x1 - depth, opening.center_offset_m - half, z0), (x1 + 0.05, opening.center_offset_m + half, 2.3)
    elif opening.wall_side == "south":
        minimum, maximum = (opening.center_offset_m - half, y0 - 0.05, z0), (opening.center_offset_m + half, y0 + depth, 2.3)
    else:
        minimum, maximum = (opening.center_offset_m - half, y1 - depth, z0), (opening.center_offset_m + half, y1 + 0.05, 2.3)
    return ExclusionVolumeSpec(
        exclusion_id=f"exclusion.portal.{hashlib.sha256(opening.opening_id.encode()).hexdigest()[:12]}",
        room_id=room.room_id,
        exclusion_kind="portal_clearance",
        min_m=minimum,
        max_m=maximum,
        source_id=opening.source_id,
    )


def _event_exclusions(house: Mapping[str, Any], room_ids: set[str]) -> list[ExclusionVolumeSpec]:
    protected_categories = {"keys", "phone", "stove"}
    result: list[ExclusionVolumeSpec] = []
    for entity in house.get("entities", []):
        if not isinstance(entity, Mapping) or entity.get("category") not in protected_categories:
            continue
        room_id = str(entity.get("room_id", ""))
        if room_id not in room_ids:
            continue
        transform = require_mapping(entity.get("transform"), field="event entity transform")
        location = vector3(transform.get("location_m", ()), field="event entity location")
        radius = 0.60 if entity.get("category") != "stove" else 0.72
        result.append(
            ExclusionVolumeSpec(
                exclusion_id=f"exclusion.event.{str(entity['entity_id']).split('/')[-1]}",
                room_id=room_id,
                exclusion_kind="event_interaction_clearance",
                min_m=(location[0] - radius, location[1] - radius, 0.0),
                max_m=(location[0] + radius, location[1] + radius, 2.2),
                source_id=str(entity["entity_id"]),
            )
        )
    return result


def _entry_corridor(room: Any) -> ExclusionVolumeSpec:
    return ExclusionVolumeSpec(
        exclusion_id="exclusion.navigation.entry_spine",
        room_id=room.room_id,
        exclusion_kind="pawn_and_npc_corridor",
        min_m=(-0.62, room.bounds_min_m[1], 0.0),
        max_m=(0.62, room.bounds_max_m[1], 2.3),
        source_id="authored.navigation.entry_spine",
    )


def _authored_anchor_rows(
    kind_to_room: Mapping[str, Any],
) -> list[
    tuple[
        Any,
        str,
        str,
        tuple[float, float, float],
        tuple[float, float, float],
        float,
        tuple[str, ...],
    ]
]:
    up = (0.0, 0.0, 1.0)
    down = (0.0, 0.0, -1.0)
    return [
        (kind_to_room["entry_hall"], "shoe_drop", "shoe and bag landing", (1.15, -3.30, 0.56), up, 0.28, ("shoe", "bag", "basket")),
        (kind_to_room["entry_hall"], "coat_wall", "coat and umbrella story", (1.22, 0.10, 1.48), up, 0.30, ("coat", "umbrella", "wall_hook")),
        (kind_to_room["entry_hall"], "console_top", "entry correspondence", (-1.15, 0.00, 0.84), up, 0.25, ("mail", "ceramic_bowl", "small_lamp")),
        (kind_to_room["living_room"], "window_sill", "daylight edge detail", (-2.32, -0.35, 0.88), up, 0.24, ("plant", "book")),
        (kind_to_room["living_room"], "reading_corner", "reading activity", (1.62, 1.34, 0.04), up, 0.38, ("floor_lamp", "book_stack", "basket")),
        (kind_to_room["living_room"], "media_console", "media wall detail", (0.92, -1.52, 0.62), up, 0.32, ("speaker", "book", "decorative_object")),
        (kind_to_room["living_room"], "coffee_table_style", "coffee table cluster", (0.45, 0.30, 0.39), up, 0.15, ("book", "tray", "ceramic_bowl")),
        (kind_to_room["living_room"], "sofa_soft", "sofa cushion styling", (-1.60, 1.05, 0.4524), up, 0.18, ("throw_pillows",)),
        (kind_to_room["living_room"], "sofa_side", "sofa side-table cluster", (-1.60, 0.05, 0.0), up, 0.20, ("side_table", "decorative_object")),
        (kind_to_room["living_room"], "reading_storage", "reading storage", (0.45, 1.65, 0.0), up, 0.12, ("basket",)),
        (kind_to_room["living_room"], "conversation_south", "conversation seating", (1.0, -0.85, 0.0), up, 0.18, ("armchair",)),
        (kind_to_room["living_room"], "ceiling_fixture", "primary ceiling fixture", (0.85, 0.25, 2.0484485), down, 0.25, ("ceiling_lamp",)),
        (kind_to_room["living_room"], "rug_main", "conversation-zone floor textile", (-0.10, 0.10, 0.0), up, 0.20, ("rug",)),
        (kind_to_room["living_room"], "window_drapes", "softened daylight edge", (-2.38, -0.35, 0.18), (1.0, 0.0, 0.0), 0.18, ("curtain",)),
        (kind_to_room["living_room"], "media_tv", "media wall display", (0.92, -1.89, 1.05), (0.0, 1.0, 0.0), 0.16, ("television",)),
        (kind_to_room["living_room"], "media_audio", "media wall audio", (0.92, -1.82, 0.62), up, 0.16, ("speaker",)),
        (kind_to_room["living_room"], "media_surface", "media console daily objects", (0.48, -1.52, 0.374078), up, 0.12, ("media_control", "decorative_object")),
        (kind_to_room["living_room"], "coffee_table_center", "coffee table shared tray", (0.42, 0.08, 0.39), up, 0.08, ("tray", "bowl", "fruit")),
        (kind_to_room["living_room"], "coffee_mug", "coffee table active drink", (0.55, 0.48, 0.39), up, 0.03, ("mug",)),
        (kind_to_room["living_room"], "sofa_throw", "casual sofa textile", (-1.20, 1.40, 0.4524), up, 0.10, ("textile",)),
        (kind_to_room["living_room"], "reading_floor_lamp", "reading practical light", (2.24, 1.66, 0.0), up, 0.14, ("floor_lamp",)),
        (kind_to_room["living_room"], "sofa_art", "framed living-room art", (-2.39, 1.22, 1.35), (1.0, 0.0, 0.0), 0.10, ("wall_art",)),
        (kind_to_room["living_room"], "sofa_picture_light", "art picture light", (-2.36, 1.22, 2.18), (1.0, 0.0, 0.0), 0.08, ("picture_light",)),
        (kind_to_room["living_room"], "reading_wall_shelf", "reading wall vignette", (0.0, 1.82, 1.27), (0.0, -1.0, 0.0), 0.12, ("shelf",)),
        (kind_to_room["kitchen_dining"], "prep_counter", "food preparation", (-1.52, 1.34, 0.96), up, 0.24, ("cutting_board", "bowl", "utensil")),
        (kind_to_room["kitchen_dining"], "coffee_station", "morning routine", (0.42, 1.34, 0.96), up, 0.22, ("mug", "coffee_maker", "jar")),
        (kind_to_room["kitchen_dining"], "dining_center", "shared meal", (-0.82, -0.20, 0.80), up, 0.28, ("plate", "bowl", "napkin", "fruit")),
        (kind_to_room["kitchen_dining"], "pantry_corner", "pantry overflow", (1.66, -1.55, 0.06), up, 0.32, ("basket", "cardboard_box", "recycling")),
    ]


def _inside(point: Sequence[float], volume: ExclusionVolumeSpec, radius: float = 0.0) -> bool:
    return all(
        volume.min_m[index] - radius <= point[index] <= volume.max_m[index] + radius
        for index in range(3)
    )


def _profile_instances(profile: Mapping[str, Any], room_ids: set[str]) -> tuple[DressingInstanceSpec, ...]:
    raw = profile.get("dressing_instances", [])
    if not isinstance(raw, list):
        raise ForgeInputError("VisualProfile dressing_instances must be a list")
    result: list[DressingInstanceSpec] = []
    for item in raw:
        if not isinstance(item, Mapping):
            raise ForgeInputError("VisualProfile dressing instances must be objects")
        room_id = str(item.get("room_id", ""))
        if room_id not in room_ids:
            continue
        transform = require_mapping(item.get("transform"), field="dressing transform")
        location_cm = vector3(transform.get("location_cm", ()), field="dressing location_cm")
        result.append(
            DressingInstanceSpec(
                instance_id=str(item.get("instance_id", "")),
                room_id=room_id,
                logical_asset_id=str(item.get("logical_asset_id", "")),
                source_receipt_id=str(item.get("source_receipt_id", "")),
                location_m=tuple(value / 100.0 for value in location_cm),  # type: ignore[arg-type]
                rotation_deg=vector3(transform.get("rotation_deg", ()), field="dressing rotation_deg"),
                scale=vector3(transform.get("scale", ()), field="dressing scale"),
                collision_policy=str(item.get("collision_policy", "disabled")),
                semantic_behavior=str(item.get("semantic_behavior", "non_interactive_presentation")),
            )
        )
    result.sort(key=lambda item: item.instance_id)
    if any(not item.instance_id for item in result) or len({item.instance_id for item in result}) != len(result):
        raise ForgeInputError("finished-room dressing instance IDs must be non-empty and unique")
    return tuple(result)


def _is_nonblocking_floor_anchor(anchor: DressingAnchorSpec) -> bool:
    return (
        anchor.allowed_categories == ("rug",)
        and abs(float(anchor.location_m[2])) <= 0.005
        and anchor.surface_normal == (0.0, 0.0, 1.0)
    )


def _floor_anchor_may_overlap_exclusion(
    anchor: DressingAnchorSpec,
    volume: ExclusionVolumeSpec,
) -> bool:
    """Allow rugs below event footprints, never through doors or nav spines."""

    return (
        _is_nonblocking_floor_anchor(anchor)
        and volume.exclusion_kind == "event_interaction_clearance"
    )


def build_dressing_plan(
    house: Mapping[str, Any],
    profile: Mapping[str, Any],
    rooms: Sequence[Any],
    openings: Sequence[Any],
) -> DressingPlan:
    seed = int(profile["seed"])
    room_by_id = {room.room_id: room for room in rooms}
    kind_to_room = {room.kind: room for room in rooms}
    exclusions = [
        _portal_exclusion(room_by_id[opening.room_id], opening)
        for opening in openings
        if opening.opening_kind == "door"
    ]
    exclusions.append(_entry_corridor(kind_to_room["entry_hall"]))
    exclusions.extend(_event_exclusions(house, set(room_by_id)))
    exclusions.sort(key=lambda item: item.exclusion_id)

    anchors: list[DressingAnchorSpec] = []
    for (
        room,
        short_id,
        purpose,
        location,
        surface_normal,
        radius,
        categories,
    ) in _authored_anchor_rows(kind_to_room):
        anchor_id = f"{room.room_id}/dressing_anchor.{short_id}"
        anchor = DressingAnchorSpec(
            anchor_id=anchor_id,
            room_id=room.room_id,
            purpose=purpose,
            location_m=location,
            surface_normal=surface_normal,
            clearance_radius_m=radius,
            allowed_categories=categories,
            deterministic_yaw_deg=(
                0.0
                if abs(float(surface_normal[2])) < 0.5
                else _stable_yaw(seed, anchor_id)
            ),
        )
        blockers = [
            volume.exclusion_id
            for volume in exclusions
            if (
                volume.room_id == room.room_id
                and _inside(location, volume, radius)
                and not _floor_anchor_may_overlap_exclusion(anchor, volume)
            )
        ]
        if blockers:
            raise ForgeInputError(f"authored dressing anchor {anchor_id} intersects exclusions: {blockers}")
        anchors.append(anchor)
    anchors.sort(key=lambda item: item.anchor_id)
    instances = _profile_instances(profile, set(room_by_id))
    payload = {
        "seed": seed,
        "placement_policy": "authored_surface_anchor_plus_closed_profile_instances_v2",
        "anchors": anchors,
        "exclusions": exclusions,
        "profile_instances": instances,
    }
    return DressingPlan(
        seed=seed,
        placement_policy="authored_surface_anchor_plus_closed_profile_instances_v2",
        anchors=tuple(anchors),
        exclusions=tuple(exclusions),
        profile_instances=instances,
        content_digest=content_digest(payload),
    )


def anchors_clear_exclusions(plan: DressingPlan) -> bool:
    return all(
        _floor_anchor_may_overlap_exclusion(anchor, volume)
        or not _inside(anchor.location_m, volume, anchor.clearance_radius_m)
        for anchor in plan.anchors
        for volume in plan.exclusions
        if anchor.room_id == volume.room_id
    )
