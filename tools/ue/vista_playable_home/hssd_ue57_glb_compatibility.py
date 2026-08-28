"""Deterministic HSSD GLB material compatibility derivation for UE 5.7.

The transform is intentionally narrow: UE 5.7 Interchange selects its
transmission material path when ``KHR_materials_transmission`` is present, even
when the extension's effective factor is zero.  That presence can shadow an
active clear-coat material and leave its textures unbound.  We remove only the
schema-known, texture-free, factor-zero form and preserve every non-JSON GLB
chunk byte-for-byte.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import struct
from typing import Any, Mapping


SCHEMA_VERSION = "simworld.vista.hssd-ue57-glb-compatibility/v1"
RULE_ID = "remove_noop_khr_materials_transmission_v1"
GLB_MAGIC = b"glTF"
GLB_VERSION = 2
GLB_JSON_CHUNK = 0x4E4F534A
MAX_GLB_BYTES = 64 * 1024 * 1024
MAX_JSON_BYTES = 16 * 1024 * 1024
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ASSET_ID_RE = re.compile(r"^hssd\.static\.[a-z0-9_]+$")
TRANSMISSION = "KHR_materials_transmission"
CLEARCOAT = "KHR_materials_clearcoat"
TRANSMISSION_KEYS = {"transmissionFactor", "transmissionTexture"}


class CompatibilityError(RuntimeError):
    """Raised when a GLB cannot be transformed without semantic ambiguity."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CompatibilityError(message)


def canonical_json(value: Any, *, newline: bool = False) -> bytes:
    raw = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return raw + (b"\n" if newline else b"")


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _content_digest(value: Mapping[str, Any]) -> str:
    body = copy.deepcopy(dict(value))
    body.pop("content_digest", None)
    return _sha256(canonical_json(body, newline=True))


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        _require(key not in result, "HSSD GLB JSON contains a duplicate key")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise CompatibilityError("HSSD GLB JSON contains a non-finite number: " + value)


def _parse_glb(raw: bytes) -> tuple[dict[str, Any], list[tuple[int, bytes]]]:
    _require(
        isinstance(raw, bytes) and 20 <= len(raw) <= MAX_GLB_BYTES,
        "HSSD compatibility input size is invalid",
    )
    magic, version, declared_size = struct.unpack("<4sII", raw[:12])
    _require(
        magic == GLB_MAGIC and version == GLB_VERSION and declared_size == len(raw),
        "HSSD compatibility input is not an exact GLB 2 container",
    )
    chunks: list[tuple[int, bytes]] = []
    offset = 12
    while offset < len(raw):
        _require(offset + 8 <= len(raw), "HSSD GLB chunk header is truncated")
        chunk_length, chunk_type = struct.unpack("<II", raw[offset : offset + 8])
        offset += 8
        _require(
            chunk_length % 4 == 0 and offset + chunk_length <= len(raw),
            "HSSD GLB chunk bounds are invalid",
        )
        payload = raw[offset : offset + chunk_length]
        chunks.append((chunk_type, payload))
        offset += chunk_length
    _require(offset == len(raw) and chunks, "HSSD GLB chunks are incomplete")
    json_indices = [
        index
        for index, (chunk_type, _payload) in enumerate(chunks)
        if chunk_type == GLB_JSON_CHUNK
    ]
    _require(
        json_indices == [0] and len(chunks[0][1]) <= MAX_JSON_BYTES,
        "HSSD GLB must have one bounded leading JSON chunk",
    )
    try:
        graph = json.loads(
            chunks[0][1].rstrip(b" \t\r\n\x00").decode("utf-8"),
            object_pairs_hook=_strict_object,
            parse_constant=_reject_constant,
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise CompatibilityError("HSSD GLB JSON is invalid") from exc
    _require(isinstance(graph, dict), "HSSD GLB JSON root is invalid")
    return graph, chunks


def _pack_glb(graph: Mapping[str, Any], chunks: list[tuple[int, bytes]]) -> bytes:
    json_payload = canonical_json(graph)
    json_payload += b" " * ((4 - len(json_payload) % 4) % 4)
    rebuilt = [(GLB_JSON_CHUNK, json_payload), *chunks[1:]]
    body = b"".join(
        struct.pack("<II", len(payload), chunk_type) + payload
        for chunk_type, payload in rebuilt
    )
    return struct.pack("<4sII", GLB_MAGIC, GLB_VERSION, 12 + len(body)) + body


def _number(value: Any, label: str) -> float:
    _require(
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and 0.0 <= float(value) <= 1.0,
        label + " must be a finite 0..1 number",
    )
    return float(value)


def _active_clearcoat(value: Any) -> bool:
    _require(isinstance(value, dict), "KHR_materials_clearcoat must be an object")
    factor = (
        _number(value["clearcoatFactor"], "clearcoatFactor")
        if "clearcoatFactor" in value
        else 0.0
    )
    return factor > 0.0


def _extension_declarations(graph: Mapping[str, Any], field: str) -> list[str]:
    values = graph.get(field, [])
    _require(
        isinstance(values, list)
        and all(isinstance(item, str) and item for item in values),
        "glTF " + field + " is invalid",
    )
    _require(len(values) == len(set(values)), "glTF " + field + " contains duplicates")
    return list(values)


def _material_texture_indices(graph: Mapping[str, Any]) -> set[int]:
    textures = graph.get("textures", [])
    materials = graph.get("materials", [])
    images = graph.get("images", [])
    _require(
        isinstance(textures, list)
        and textures
        and isinstance(materials, list)
        and materials
        and isinstance(images, list),
        "HSSD GLB material, texture or image arrays are invalid",
    )
    for texture in textures:
        _require(isinstance(texture, dict), "HSSD GLB texture record is invalid")
        source = texture.get("source")
        _require(
            isinstance(source, int)
            and not isinstance(source, bool)
            and 0 <= source < len(images),
            "HSSD GLB texture source index is invalid",
        )
    referenced: set[int] = set()

    def visit(node: Any, key: str = "") -> None:
        if isinstance(node, dict):
            if key.lower().endswith("texture") and "index" in node:
                index = node.get("index")
                _require(
                    isinstance(index, int)
                    and not isinstance(index, bool)
                    and 0 <= index < len(textures),
                    "HSSD GLB material texture index is invalid",
                )
                referenced.add(index)
            for child_key, child in node.items():
                visit(child, str(child_key))
        elif isinstance(node, list):
            for child in node:
                visit(child, key)

    visit(materials)
    _require(
        referenced == set(range(len(textures))),
        "HSSD GLB has an unbound or dangling texture record",
    )
    return referenced


def _json_diff_paths(source: Any, output: Any, path: str = "") -> set[str]:
    if isinstance(source, dict) and isinstance(output, dict):
        changes: set[str] = set()
        for key in sorted(set(source) | set(output)):
            escaped = key.replace("~", "~0").replace("/", "~1")
            child_path = path + "/" + escaped
            if key not in source or key not in output:
                changes.add(child_path)
            else:
                changes.update(_json_diff_paths(source[key], output[key], child_path))
        return changes
    if isinstance(source, list) and isinstance(output, list):
        if len(source) != len(output):
            return {path or "/"}
        changes = set()
        for index, (source_item, output_item) in enumerate(zip(source, output)):
            changes.update(
                _json_diff_paths(source_item, output_item, f"{path}/{index}")
            )
        return changes
    return set() if source == output else {path or "/"}


def _non_json_chunks(chunks: list[tuple[int, bytes]]) -> list[dict[str, Any]]:
    return [
        {
            "chunk_index": index,
            "chunk_type": f"0x{chunk_type:08x}",
            "bytes": len(payload),
            "sha256": _sha256(payload),
        }
        for index, (chunk_type, payload) in enumerate(chunks[1:], start=1)
    ]


def derive_glb(
    raw: bytes,
    *,
    source_asset_id: str,
    transform_script_sha256: str,
) -> tuple[bytes, dict[str, Any]]:
    """Return exact UE-compatible GLB bytes and a sealed transform receipt."""

    _require(
        isinstance(source_asset_id, str)
        and ASSET_ID_RE.fullmatch(source_asset_id) is not None,
        "HSSD compatibility source asset ID is invalid",
    )
    _require(
        isinstance(transform_script_sha256, str)
        and SHA256_RE.fullmatch(transform_script_sha256) is not None,
        "HSSD compatibility transform digest is invalid",
    )
    source_graph, chunks = _parse_glb(raw)
    source_texture_indices = _material_texture_indices(source_graph)
    extensions_used_before = _extension_declarations(source_graph, "extensionsUsed")
    extensions_required_before = _extension_declarations(
        source_graph, "extensionsRequired"
    )
    output_graph = copy.deepcopy(source_graph)
    materials = output_graph.get("materials", [])
    _require(isinstance(materials, list) and materials, "HSSD GLB has no materials")
    removed: list[dict[str, Any]] = []
    active_transmission: list[dict[str, Any]] = []
    active_dual: list[dict[str, Any]] = []
    for material_index, material in enumerate(materials):
        _require(isinstance(material, dict), "HSSD GLB material is invalid")
        extensions = material.get("extensions")
        if extensions is None:
            continue
        _require(isinstance(extensions, dict), "HSSD material extensions are invalid")
        if TRANSMISSION not in extensions:
            continue
        transmission = extensions[TRANSMISSION]
        _require(
            isinstance(transmission, dict),
            "KHR_materials_transmission must be an object",
        )
        unknown = sorted(set(transmission) - TRANSMISSION_KEYS)
        _require(
            not unknown,
            "KHR_materials_transmission has unknown fields: " + ",".join(unknown),
        )
        clearcoat = extensions.get(CLEARCOAT)
        clearcoat_active = (
            _active_clearcoat(clearcoat) if CLEARCOAT in extensions else False
        )
        factor = (
            _number(transmission["transmissionFactor"], "transmissionFactor")
            if "transmissionFactor" in transmission
            else 0.0
        )
        texture_present = "transmissionTexture" in transmission
        texture = transmission.get("transmissionTexture")
        if texture_present:
            _require(isinstance(texture, dict), "transmissionTexture must be an object")
        material_name = material.get("name")
        _require(
            material_name is None or isinstance(material_name, str),
            "HSSD material name is invalid",
        )
        record = {
            "material_index": material_index,
            "material_name": material_name,
            "transmission": copy.deepcopy(transmission),
        }
        if factor == 0.0 and not texture_present:
            removed.append(record)
            del extensions[TRANSMISSION]
            if not extensions:
                material.pop("extensions", None)
            continue
        active_transmission.append(record)
        if clearcoat_active:
            active_dual.append(
                {
                    **record,
                    "clearcoat": copy.deepcopy(clearcoat),
                    "blocks_full_material_fidelity": True,
                }
            )

    remaining_transmission = any(
        isinstance(material, dict)
        and isinstance(material.get("extensions"), dict)
        and TRANSMISSION in material["extensions"]
        for material in materials
    )
    if not remaining_transmission and TRANSMISSION in extensions_used_before:
        _require(
            TRANSMISSION not in extensions_required_before,
            "required KHR_materials_transmission cannot be removed",
        )
        output_graph["extensionsUsed"] = [
            name for name in extensions_used_before if name != TRANSMISSION
        ]
        if not output_graph["extensionsUsed"]:
            output_graph.pop("extensionsUsed")
    extensions_used_after = _extension_declarations(output_graph, "extensionsUsed")
    extensions_required_after = _extension_declarations(
        output_graph, "extensionsRequired"
    )
    _require(
        extensions_required_after == extensions_required_before,
        "HSSD compatibility changed extensionsRequired",
    )
    output_texture_indices = _material_texture_indices(output_graph)
    _require(
        output_texture_indices == source_texture_indices,
        "HSSD compatibility changed material texture coverage",
    )
    expected_changes = set()
    for record in removed:
        material_index = record["material_index"]
        source_extensions = source_graph["materials"][material_index]["extensions"]
        expected_changes.add(
            (
                f"/materials/{material_index}/extensions"
                if set(source_extensions) == {TRANSMISSION}
                else f"/materials/{material_index}/extensions/{TRANSMISSION}"
            )
        )
    if extensions_used_after != extensions_used_before:
        expected_changes.add("/extensionsUsed")
    changed_json_pointers = _json_diff_paths(source_graph, output_graph)
    _require(
        changed_json_pointers == expected_changes,
        "HSSD compatibility JSON changes exceed the exact allowlist",
    )
    output = _pack_glb(output_graph, chunks)
    reparsed_graph, reparsed_chunks = _parse_glb(output)
    _require(
        reparsed_graph == output_graph
        and _material_texture_indices(reparsed_graph) == source_texture_indices
        and _non_json_chunks(reparsed_chunks) == _non_json_chunks(chunks),
        "HSSD compatibility output did not preserve protected content",
    )
    receipt = {
        "schema_version": SCHEMA_VERSION,
        "rule_id": RULE_ID,
        "status": (
            "derived_with_active_dual_material_blocker"
            if active_dual
            else "derived_ue57_compatible_candidate"
        ),
        "accepted_as_visual_evidence": False,
        "source_asset_id": source_asset_id,
        "source_sha256": _sha256(raw),
        "source_bytes": len(raw),
        "output_sha256": _sha256(output),
        "output_bytes": len(output),
        "transform_script_sha256": transform_script_sha256,
        "source_json_sha256": _sha256(canonical_json(source_graph)),
        "output_json_sha256": _sha256(canonical_json(output_graph)),
        "changed_json_pointers": sorted(changed_json_pointers),
        "material_texture_indices": sorted(source_texture_indices),
        "extensions_used_before": extensions_used_before,
        "extensions_used_after": extensions_used_after,
        "extensions_required": extensions_required_before,
        "non_json_chunks": _non_json_chunks(chunks),
        "removed_noop_transmission": removed,
        "retained_active_transmission": active_transmission,
        "retained_active_dual_conflicts": active_dual,
        "blocks_full_material_fidelity": bool(active_dual),
        "source_license_scope": {
            "commercial_release": "blocked",
            "public_payload_distribution": "prohibited",
            "use_class": "private_noncommercial_research_only",
        },
        "modification_notice": (
            "UE 5.7 compatibility derivative: removed only texture-free "
            "factor-zero KHR_materials_transmission objects listed in this receipt"
        ),
    }
    receipt["content_digest"] = _content_digest(receipt)
    return output, receipt


def validate_receipt(receipt: Mapping[str, Any]) -> None:
    """Validate a receipt's closed shape and self-digest."""

    expected_keys = {
        "schema_version",
        "rule_id",
        "status",
        "accepted_as_visual_evidence",
        "source_asset_id",
        "source_sha256",
        "source_bytes",
        "output_sha256",
        "output_bytes",
        "transform_script_sha256",
        "source_json_sha256",
        "output_json_sha256",
        "changed_json_pointers",
        "material_texture_indices",
        "extensions_used_before",
        "extensions_used_after",
        "extensions_required",
        "non_json_chunks",
        "removed_noop_transmission",
        "retained_active_transmission",
        "retained_active_dual_conflicts",
        "blocks_full_material_fidelity",
        "source_license_scope",
        "modification_notice",
        "content_digest",
    }
    _require(set(receipt) == expected_keys, "HSSD compatibility receipt keys differ")
    removed = receipt.get("removed_noop_transmission")
    active = receipt.get("retained_active_transmission")
    dual = receipt.get("retained_active_dual_conflicts")
    _require(
        isinstance(removed, list)
        and isinstance(active, list)
        and isinstance(dual, list),
        "HSSD compatibility material records are invalid",
    )
    base_record_keys = {"material_index", "material_name", "transmission"}
    for record in [*removed, *active]:
        _require(
            isinstance(record, dict)
            and set(record) == base_record_keys
            and isinstance(record["material_index"], int)
            and not isinstance(record["material_index"], bool)
            and record["material_index"] >= 0
            and (
                record["material_name"] is None
                or isinstance(record["material_name"], str)
            )
            and isinstance(record["transmission"], dict),
            "HSSD compatibility material record differs",
        )
    for record in removed:
        transmission = record["transmission"]
        _require(
            not (set(transmission) - TRANSMISSION_KEYS)
            and "transmissionTexture" not in transmission
            and (
                "transmissionFactor" not in transmission
                or (
                    isinstance(transmission["transmissionFactor"], (int, float))
                    and not isinstance(transmission["transmissionFactor"], bool)
                    and float(transmission["transmissionFactor"]) == 0.0
                )
            ),
            "removed HSSD transmission record was not a no-op",
        )
    for record in active:
        transmission = record["transmission"]
        factor = transmission.get("transmissionFactor", 0)
        _require(
            not (set(transmission) - TRANSMISSION_KEYS)
            and (
                "transmissionTexture" in transmission
                or (
                    isinstance(factor, (int, float))
                    and not isinstance(factor, bool)
                    and float(factor) > 0.0
                )
            ),
            "retained HSSD transmission record is not active",
        )
    active_index = {
        (
            record["material_index"],
            record["material_name"],
            canonical_json(record["transmission"]),
        )
        for record in active
    }
    for record in dual:
        _require(
            isinstance(record, dict)
            and set(record)
            == base_record_keys | {"clearcoat", "blocks_full_material_fidelity"}
            and isinstance(record["clearcoat"], dict)
            and record["blocks_full_material_fidelity"] is True
            and (
                record["material_index"],
                record["material_name"],
                canonical_json(record["transmission"]),
            )
            in active_index,
            "HSSD dual-active material record differs",
        )
    changed = receipt.get("changed_json_pointers")
    texture_indices = receipt.get("material_texture_indices")
    _require(
        isinstance(changed, list)
        and all(isinstance(path, str) for path in changed)
        and changed == sorted(set(changed))
        and all(
            (
                path == "/extensionsUsed"
                or re.fullmatch(
                    r"/materials/[0-9]+/extensions(?:/KHR_materials_transmission)?",
                    path,
                )
                is not None
            )
            for path in changed
        )
        and isinstance(texture_indices, list)
        and all(
            isinstance(index, int) and not isinstance(index, bool) and index >= 0
            for index in texture_indices
        )
        and texture_indices == sorted(set(texture_indices)),
        "HSSD compatibility diff or texture-index ledger differs",
    )
    for field in (
        "extensions_used_before",
        "extensions_used_after",
        "extensions_required",
    ):
        values = receipt.get(field)
        _require(
            isinstance(values, list)
            and all(isinstance(item, str) and item for item in values)
            and len(values) == len(set(values)),
            "HSSD compatibility extension declaration ledger differs",
        )
    chunks = receipt.get("non_json_chunks")
    _require(isinstance(chunks, list), "HSSD compatibility chunk ledger differs")
    for index, chunk in enumerate(chunks, start=1):
        _require(
            isinstance(chunk, dict)
            and set(chunk) == {"chunk_index", "chunk_type", "bytes", "sha256"}
            and chunk["chunk_index"] == index
            and isinstance(chunk["chunk_type"], str)
            and re.fullmatch(r"0x[0-9a-f]{8}", chunk["chunk_type"]) is not None
            and isinstance(chunk["bytes"], int)
            and chunk["bytes"] >= 0
            and isinstance(chunk["sha256"], str)
            and SHA256_RE.fullmatch(chunk["sha256"]) is not None,
            "HSSD compatibility chunk record differs",
        )
    expected_license = {
        "commercial_release": "blocked",
        "public_payload_distribution": "prohibited",
        "use_class": "private_noncommercial_research_only",
    }
    expected_notice = (
        "UE 5.7 compatibility derivative: removed only texture-free "
        "factor-zero KHR_materials_transmission objects listed in this receipt"
    )
    _require(
        receipt.get("schema_version") == SCHEMA_VERSION
        and receipt.get("rule_id") == RULE_ID
        and receipt.get("accepted_as_visual_evidence") is False
        and receipt.get("content_digest") == _content_digest(receipt)
        and isinstance(receipt.get("source_asset_id"), str)
        and ASSET_ID_RE.fullmatch(receipt["source_asset_id"]) is not None
        and all(
            isinstance(receipt.get(key), str)
            and SHA256_RE.fullmatch(receipt[key]) is not None
            for key in (
                "source_sha256",
                "output_sha256",
                "transform_script_sha256",
                "source_json_sha256",
                "output_json_sha256",
            )
        )
        and isinstance(receipt.get("source_bytes"), int)
        and not isinstance(receipt["source_bytes"], bool)
        and receipt["source_bytes"] > 0
        and isinstance(receipt.get("output_bytes"), int)
        and not isinstance(receipt["output_bytes"], bool)
        and receipt["output_bytes"] > 0
        and receipt.get("blocks_full_material_fidelity") is bool(dual)
        and receipt.get("status")
        == (
            "derived_with_active_dual_material_blocker"
            if dual
            else "derived_ue57_compatible_candidate"
        )
        and receipt.get("source_license_scope") == expected_license
        and receipt.get("modification_notice") == expected_notice,
        "HSSD compatibility receipt identity or digest differs",
    )


def validate_derivation(
    source_raw: bytes,
    output_raw: bytes,
    receipt: Mapping[str, Any],
    *,
    source_asset_id: str,
    transform_script_sha256: str,
) -> None:
    """Re-derive exact bytes and receipt; reject drift or substitution."""

    validate_receipt(receipt)
    expected_output, expected_receipt = derive_glb(
        source_raw,
        source_asset_id=source_asset_id,
        transform_script_sha256=transform_script_sha256,
    )
    _require(output_raw == expected_output, "HSSD compatibility output bytes differ")
    _require(dict(receipt) == expected_receipt, "HSSD compatibility receipt differs")
