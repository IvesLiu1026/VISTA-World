#!/usr/bin/env python3
"""Plan or execute an isolated R20 upgrade of the sealed photoreal R6 home.

The default dry run validates every caller-supplied path and byte/tree pin and
does not write.  ``--execute`` creates one append-only attempt, reflinks or
copies only the R6 static project projection, installs the exact compiled
plugin and animation/fridge overlays, then launches author and cold-verify UE
processes in separate network namespaces.  Publication revalidates every
source after UE so a concurrent source change cannot be blessed.
"""

from __future__ import annotations

import argparse
import copy
import dataclasses
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import subprocess
from typing import Any, Mapping, Sequence

from tools.runtime.vista_playable_home import human_visual_demo_launch as live_tree
from tools.ue.vista_playable_home import build_home
from tools.ue.vista_playable_home import live_scene_upgrade_r20_contract as contract


BINDING_SCHEMA = "vista.live-scene-upgrade-r20-input-bindings/v1"
RUN_PARENT_DEFAULT = Path("/data/sysx/vista-world/runs/vista-action-world-r1")
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
COMMANDLET = Path(__file__).with_name(
    "compose_live_scene_upgrade_r20_commandlet.py"
)
ATTEMPT_RE = re.compile(
    r"^live-scene-upgrade-r20-[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$"
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
MAX_JSON_BYTES = 16 * 1024 * 1024
TIMEOUT_SECONDS = 7_200
FICLONE = 0x40049409
STATIC_ROOTS = ("Config", "Content", "Plugins")
AUTHOR_RECEIPT_NAME = "r20-author-worker.json"
VERIFY_RECEIPT_NAME = "r20-verify-worker.json"
HOST_RECEIPT_NAME = "r20-live-scene-upgrade-host-receipt.json"
EXECUTION_NAME = "r20-live-scene-upgrade-execution.json"


class RunnerError(RuntimeError):
    """A source pin, append-only policy, UE proof, or publication gate failed."""


@dataclasses.dataclass(frozen=True)
class FileSeal:
    path: Path
    sha256: str
    size_bytes: int

    def public(self, *, path: str | None = None) -> dict[str, Any]:
        return {
            "path": str(self.path) if path is None else path,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
        }


@dataclasses.dataclass(frozen=True)
class TreePin:
    root: Path
    tree_sha256: str
    file_count: int
    total_bytes: int

    def public(self, *, root: str | None = None) -> dict[str, Any]:
        return {
            "root": str(self.root) if root is None else root,
            "algorithm": "sha256-path-nul-mode-size-content-v1",
            "tree_sha256": self.tree_sha256,
            "file_count": self.file_count,
            "total_bytes": self.total_bytes,
        }


@dataclasses.dataclass(frozen=True)
class OverlayInput:
    role: str
    tree: TreePin
    receipt: FileSeal
    receipt_value: dict[str, Any]
    inventory: tuple[dict[str, str], ...]
    supporting: FileSeal | None = None
    supporting_value: dict[str, Any] | None = None


@dataclasses.dataclass(frozen=True)
class Plan:
    attempt_name: str
    attempt_root: Path
    run_parent: Path
    bindings_path: Path
    bindings_seal: FileSeal
    bindings: dict[str, Any]
    source_project: TreePin
    source_descriptor: FileSeal
    source_map: FileSeal
    source_manifest: FileSeal
    source_manifest_value: dict[str, Any]
    plugin: TreePin
    typed_profile: FileSeal
    typed_profile_value: dict[str, Any]
    overlays: tuple[OverlayInput, ...]
    unreal_editor: FileSeal
    bwrap: FileSeal
    commandlet: FileSeal
    report: dict[str, Any]


def require(condition: Any, message: str) -> None:
    if not condition:
        raise RunnerError(message)


def canonical_json(value: Any) -> bytes:
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
        raise RunnerError("value is not finite canonical JSON") from exc


def content_digest(value: Mapping[str, Any]) -> str:
    body = copy.deepcopy(dict(value))
    body.pop("content_digest", None)
    return hashlib.sha256(canonical_json(body)).hexdigest()


def seal_document(value: Mapping[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(dict(value))
    result["content_digest"] = content_digest(result)
    return result


def _reject_duplicate_keys(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(token: str) -> None:
    raise RunnerError("non-finite JSON constant: " + token)


def _absolute(path: Any, label: str) -> Path:
    require(type(path) is str and bool(path), f"{label} path is invalid")
    candidate = Path(path)
    require(candidate.is_absolute(), f"{label} path must be absolute")
    require(os.path.normpath(path) == path, f"{label} path is not normalized")
    return candidate


def _reject_symlink_components(
    path: Path, label: str, *, allow_missing_tail: bool = False
) -> None:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current = current / part
        try:
            metadata = os.lstat(current)
        except FileNotFoundError:
            if allow_missing_tail:
                return
            raise RunnerError(f"{label} is missing") from None
        except OSError as exc:
            raise RunnerError(f"{label} cannot be inspected") from exc
        require(not stat.S_ISLNK(metadata.st_mode), f"{label} contains a symlink")


def _existing_file(path: Path, label: str) -> Path:
    require(path.is_absolute(), f"{label} path must be absolute")
    _reject_symlink_components(path, label)
    try:
        metadata = os.lstat(path)
    except OSError as exc:
        raise RunnerError(f"{label} is missing") from exc
    require(stat.S_ISREG(metadata.st_mode), f"{label} is not a regular file")
    require(path.resolve(strict=True) == path, f"{label} path is not canonical")
    return path


def _existing_directory(path: Path, label: str) -> Path:
    require(path.is_absolute(), f"{label} path must be absolute")
    _reject_symlink_components(path, label)
    try:
        metadata = os.lstat(path)
    except OSError as exc:
        raise RunnerError(f"{label} is missing") from exc
    require(stat.S_ISDIR(metadata.st_mode), f"{label} is not a directory")
    require(path.resolve(strict=True) == path, f"{label} path is not canonical")
    return path


def _within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def sha256_file(path: Path) -> FileSeal:
    source = _existing_file(path, "sealed file")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(source, flags)
    except OSError as exc:
        raise RunnerError(f"sealed file cannot be opened: {source}") from exc
    try:
        before = os.fstat(descriptor)
        identity = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        digest = hashlib.sha256()
        observed = 0
        while True:
            block = os.read(descriptor, 1024 * 1024)
            if not block:
                break
            digest.update(block)
            observed += len(block)
        after = os.fstat(descriptor)
        require(
            identity
            == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
            and observed == before.st_size,
            f"sealed file changed while hashing: {source}",
        )
        return FileSeal(source, digest.hexdigest(), observed)
    finally:
        os.close(descriptor)


def _file_pin(value: Any, label: str) -> FileSeal:
    require(
        type(value) is dict and set(value) == {"path", "sha256", "size_bytes"},
        f"{label} pin fields differ",
    )
    path = _absolute(value["path"], label)
    require(
        type(value["sha256"]) is str
        and SHA256_RE.fullmatch(value["sha256"]) is not None
        and type(value["size_bytes"]) is int
        and not isinstance(value["size_bytes"], bool)
        and value["size_bytes"] > 0,
        f"{label} pin is invalid",
    )
    observed = sha256_file(path)
    require(
        (observed.sha256, observed.size_bytes)
        == (value["sha256"], value["size_bytes"]),
        f"{label} bytes differ",
    )
    return observed


def strict_json(
    path: Path, label: str, *, require_canonical: bool = True
) -> tuple[dict[str, Any], FileSeal]:
    seal = sha256_file(path)
    require(0 < seal.size_bytes <= MAX_JSON_BYTES, f"{label} size is invalid")
    raw = path.read_bytes()
    try:
        value = json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except (UnicodeError, ValueError, TypeError) as exc:
        raise RunnerError(f"{label} is not strict JSON") from exc
    require(type(value) is dict, f"{label} root is not an object")
    if require_canonical:
        require(raw == canonical_json(value), f"{label} is not canonical JSON")
    return value, seal


def _tree_pin(value: Any, label: str) -> TreePin:
    require(
        type(value) is dict
        and set(value) == {"root", "tree_sha256", "file_count", "total_bytes"},
        f"{label} tree pin fields differ",
    )
    root = _existing_directory(_absolute(value["root"], label), label)
    require(
        type(value["tree_sha256"]) is str
        and SHA256_RE.fullmatch(value["tree_sha256"]) is not None
        and type(value["file_count"]) is int
        and not isinstance(value["file_count"], bool)
        and value["file_count"] > 0
        and type(value["total_bytes"]) is int
        and not isinstance(value["total_bytes"], bool)
        and value["total_bytes"] > 0,
        f"{label} tree pin is invalid",
    )
    observed = build_home.snapshot_tree(root, label)
    require(
        observed.sha256 == value["tree_sha256"]
        and observed.file_count == value["file_count"]
        and observed.total_bytes == value["total_bytes"],
        f"{label} tree differs",
    )
    return TreePin(
        root=root,
        tree_sha256=observed.sha256,
        file_count=observed.file_count,
        total_bytes=observed.total_bytes,
    )


def _project_static_pin(value: Any, label: str) -> TreePin:
    require(
        type(value) is dict
        and set(value)
        == {"root", "algorithm", "tree_sha256", "file_count", "total_bytes"},
        f"{label} pin fields differ",
    )
    require(
        value["algorithm"] == "sha256-path-nul-mode-size-content-v1",
        f"{label} algorithm differs",
    )
    root = _existing_directory(_absolute(value["root"], label), label)
    descriptor = root / contract.PROJECT_DESCRIPTOR_NAME
    observed = live_tree.compute_project_static_tree(descriptor)
    require(
        observed
        == {
            "algorithm": value["algorithm"],
            "tree_sha256": value["tree_sha256"],
            "file_count": value["file_count"],
            "total_bytes": value["total_bytes"],
        },
        f"{label} static tree differs",
    )
    return TreePin(
        root=root,
        tree_sha256=observed["tree_sha256"],
        file_count=observed["file_count"],
        total_bytes=observed["total_bytes"],
    )


def _inventory_from_receipt(
    role: str, receipt: Mapping[str, Any], tree: TreePin
) -> tuple[dict[str, str], ...]:
    authority = contract.RECEIPT_CONTRACTS[role]
    require(
        receipt.get("schema_version") in authority["schemas"]
        and receipt.get("status") in authority["statuses"]
        and receipt.get("accepted") is False
        and receipt.get("content_digest") == content_digest(receipt),
        f"{role} receipt authority differs",
    )
    inventory = None
    for key in authority["inventory_keys"]:
        if type(receipt.get(key)) is list:
            inventory = receipt[key]
            break
    require(type(inventory) is list, f"{role} receipt inventory is unavailable")
    namespace = contract.OVERLAY_NAMESPACES[role]
    selected: list[dict[str, str]] = []
    for raw in inventory:
        if type(raw) is not dict:
            continue
        object_path = raw.get("object_path")
        class_path = raw.get("class_path")
        if (
            type(object_path) is str
            and object_path.startswith(namespace + "/")
            and type(class_path) is str
            and class_path.startswith("/Script/")
        ):
            selected.append({"object_path": object_path, "class_path": class_path})
    require(bool(selected), f"{role} receipt contains no bound overlay assets")
    object_paths = [item["object_path"] for item in selected]
    require(
        len(object_paths) == len(set(object_paths)),
        f"{role} receipt contains duplicate object paths",
    )
    tree_files = {record[0] for record in build_home.snapshot_tree(tree.root, role).records}
    for item in selected:
        package = item["object_path"].split(".", 1)[0]
        relative = package.removeprefix(namespace + "/") + ".uasset"
        require(relative in tree_files, f"{role} UAsset is absent: {relative}")
    if role == "fridge":
        require(
            len(selected) == 3
            and {item["class_path"] for item in selected}
            == {"/Script/Engine.StaticMesh"}
            and receipt.get("gates", {}).get("map_saved") is True
            and receipt.get("gates", {}).get("map_cold_reloaded") is True
            and receipt.get("articulated_actor", {}).get("semantic_id")
            == contract.FRIDGE_ID,
            "fridge receipt is not the successful three-link authority",
        )
    return tuple(sorted(selected, key=lambda item: item["object_path"]))


def _validate_source_manifest(
    manifest: Mapping[str, Any], project: TreePin, descriptor: FileSeal, map_seal: FileSeal
) -> None:
    project_record = manifest.get("project", {})
    static_tree = project_record.get("static_tree", {})
    require(
        project_record.get("descriptor", {}).get("sha256") == descriptor.sha256
        and project_record.get("descriptor", {}).get("size_bytes")
        == descriptor.size_bytes
        and project_record.get("map_package", {}).get("sha256") == map_seal.sha256
        and project_record.get("map_package", {}).get("size_bytes")
        == map_seal.size_bytes
        and static_tree.get("algorithm")
        == "sha256-path-nul-mode-size-content-v1"
        and static_tree.get("tree_sha256") == project.tree_sha256
        and static_tree.get("file_count") == project.file_count
        and static_tree.get("total_bytes") == project.total_bytes
        and manifest.get("legal_scope", {}).get("human_operated_visual_demo_only")
        is True
        and manifest.get("legal_scope", {}).get("external_assets_outside_git")
        is True
        and manifest.get("claims", {}).get("gta_quality_claim") is False
        and manifest.get("claims", {}).get("photoreal_claim") is False,
        "R6 source manifest does not bind the exact private visual project",
    )


def _parse_bindings(
    path: Path, expected_sha256: str
) -> tuple[dict[str, Any], FileSeal]:
    value, seal = strict_json(path, "R20 input bindings")
    require(
        SHA256_RE.fullmatch(expected_sha256 or "") is not None
        and seal.sha256 == expected_sha256,
        "R20 input bindings pin differs",
    )
    require(
        set(value)
        == {
            "schema_version",
            "run_parent",
            "source_project",
            "compiled_plugin",
            "typed_profile",
            "overlays",
            "toolchain",
            "content_digest",
        }
        and value["schema_version"] == BINDING_SCHEMA
        and value["content_digest"] == content_digest(value),
        "R20 input bindings identity differs",
    )
    return value, seal


def build_plan(
    attempt_name: str,
    bindings_path: Path,
    bindings_sha256: str,
) -> Plan:
    """Validate exact sources and return a deterministic zero-write plan."""

    require(ATTEMPT_RE.fullmatch(attempt_name) is not None, "attempt name is invalid")
    bindings_path = _existing_file(bindings_path, "R20 input bindings")
    bindings, bindings_seal = _parse_bindings(bindings_path, bindings_sha256)
    run_parent = _existing_directory(
        _absolute(bindings["run_parent"], "run parent"), "run parent"
    )
    require(not _within(run_parent, REPOSITORY_ROOT), "run parent must stay outside Git")
    attempt_root = run_parent / attempt_name
    require(not os.path.lexists(attempt_root), "attempt output already exists")
    _reject_symlink_components(attempt_root, "attempt root", allow_missing_tail=True)

    source = bindings["source_project"]
    require(
        type(source) is dict
        and set(source) == {"static_tree", "descriptor", "map", "manifest"},
        "source project binding fields differ",
    )
    source_project = _project_static_pin(source["static_tree"], "R6 source project")
    source_descriptor = _file_pin(source["descriptor"], "R6 project descriptor")
    source_map = _file_pin(source["map"], "R6 main map")
    source_manifest = _file_pin(source["manifest"], "R6 source manifest")
    require(
        source_descriptor.path
        == source_project.root / contract.PROJECT_DESCRIPTOR_NAME
        and source_map.path == source_project.root / contract.MAP_RELATIVE_PATH,
        "R6 descriptor or map escaped the exact project",
    )
    source_manifest_value, _ = strict_json(
        source_manifest.path, "R6 source manifest", require_canonical=False
    )
    _validate_source_manifest(
        source_manifest_value, source_project, source_descriptor, source_map
    )

    plugin = _tree_pin(bindings["compiled_plugin"], "compiled VistaPlayableHome")
    require(not _within(plugin.root, REPOSITORY_ROOT), "compiled plugin must stay outside Git")
    required_plugin_files = (
        "VistaPlayableHome.uplugin",
        "Binaries/Linux/libUnrealEditor-VistaPlayableHome.so",
        "Binaries/Linux/libUnrealEditor-VistaPlayableHomeEditor.so",
        "Binaries/Linux/UnrealEditor.modules",
    )
    require(
        all((plugin.root / name).is_file() for name in required_plugin_files),
        "compiled plugin closure is incomplete",
    )

    typed_profile = _file_pin(bindings["typed_profile"], "typed R18 profile")
    typed_profile_value, _ = strict_json(
        typed_profile.path, "typed R18 profile", require_canonical=False
    )
    try:
        typed_profile_value = contract.validate_typed_profile(typed_profile_value)
    except contract.ContractError as exc:
        raise RunnerError(str(exc)) from exc

    overlay_values = bindings["overlays"]
    require(
        type(overlay_values) is dict
        and set(overlay_values) == set(contract.OVERLAY_DESTINATIONS),
        "overlay roles differ",
    )
    overlays: list[OverlayInput] = []
    for role in contract.OVERLAY_DESTINATIONS:
        binding = overlay_values[role]
        expected_fields = (
            {"tree", "receipt", "execution"}
            if role == "fridge"
            else {"tree", "receipt"}
        )
        require(
            type(binding) is dict and set(binding) == expected_fields,
            f"{role} overlay fields differ",
        )
        tree = _tree_pin(binding["tree"], f"{role} overlay")
        receipt = _file_pin(binding["receipt"], f"{role} receipt")
        receipt_value, _ = strict_json(receipt.path, f"{role} receipt")
        inventory = _inventory_from_receipt(role, receipt_value, tree)
        require(not _within(tree.root, REPOSITORY_ROOT), f"{role} overlay must stay outside Git")
        supporting = None
        supporting_value = None
        if role == "fridge":
            supporting = _file_pin(binding["execution"], "fridge execution")
            supporting_value, _ = strict_json(
                supporting.path, "fridge execution"
            )
            require(
                supporting.path.parent == receipt.path.parent
                and supporting.path.name == "articulated-fridge-execution.json"
                and supporting_value.get("schema_version")
                == "vista.playable-articulated-fridge-dev-execution/v1"
                and supporting_value.get("content_digest")
                == content_digest(supporting_value)
                and type(supporting_value.get("legacy")) is dict,
                "fridge execution does not bind the exact legacy scene",
            )
        overlays.append(
            OverlayInput(
                role,
                tree,
                receipt,
                receipt_value,
                inventory,
                supporting,
                supporting_value,
            )
        )

    tools = bindings["toolchain"]
    require(
        type(tools) is dict and set(tools) == {"unreal_editor_cmd", "bwrap"},
        "toolchain binding fields differ",
    )
    unreal_editor = _file_pin(tools["unreal_editor_cmd"], "UnrealEditor-Cmd")
    bwrap = _file_pin(tools["bwrap"], "bubblewrap")
    require(os.access(unreal_editor.path, os.X_OK), "UnrealEditor-Cmd is not executable")
    require(os.access(bwrap.path, os.X_OK), "bubblewrap is not executable")
    commandlet = sha256_file(COMMANDLET)

    report = contract.seal_document(
        {
            "schema_version": contract.PLAN_SCHEMA,
            "status": contract.DRY_RUN_STATUS,
            "attempt_name": attempt_name,
            "attempt_root": str(attempt_root),
            "bindings": bindings_seal.public(),
            "source_project": {
                "static_tree": source_project.public(),
                "descriptor": source_descriptor.public(),
                "map": source_map.public(),
                "manifest": source_manifest.public(),
            },
            "compiled_plugin": plugin.public(),
            "typed_profile": {
                **typed_profile.public(),
                "profile_id": contract.TYPED_PROFILE_ID,
                "content_digest": contract.TYPED_PROFILE_CONTENT_DIGEST,
            },
            "overlays": {
                item.role: {
                    "tree": item.tree.public(),
                    "receipt": item.receipt.public(),
                    "destination": contract.OVERLAY_DESTINATIONS[item.role],
                    "asset_count": len(item.inventory),
                    **(
                        {"execution": item.supporting.public()}
                        if item.supporting is not None
                        else {}
                    ),
                }
                for item in overlays
            },
            "toolchain": {
                "unreal_editor_cmd": unreal_editor.public(),
                "bwrap": bwrap.public(),
                "commandlet": commandlet.public(),
                "network_isolation": "bubblewrap_unshare_net",
                "separate_author_and_cold_verify_processes": True,
            },
            "planned_mutations": {
                "source_r6": False,
                "live_services": False,
                "gpu_or_renderer": False,
                "attempt_created": False,
                "fresh_project_created": False,
            },
            "claims": copy.deepcopy(contract.NEGATIVE_CLAIMS),
            "legal_scope": copy.deepcopy(contract.LEGAL_SCOPE),
        }
    )
    return Plan(
        attempt_name=attempt_name,
        attempt_root=attempt_root,
        run_parent=run_parent,
        bindings_path=bindings_path,
        bindings_seal=bindings_seal,
        bindings=bindings,
        source_project=source_project,
        source_descriptor=source_descriptor,
        source_map=source_map,
        source_manifest=source_manifest,
        source_manifest_value=source_manifest_value,
        plugin=plugin,
        typed_profile=typed_profile,
        typed_profile_value=typed_profile_value,
        overlays=tuple(overlays),
        unreal_editor=unreal_editor,
        bwrap=bwrap,
        commandlet=commandlet,
        report=report,
    )


def _copy_file(source: str, destination: str) -> str:
    source_path = Path(source)
    destination_path = Path(destination)
    method = "copy"
    source_fd = os.open(source_path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        destination_fd = os.open(
            destination_path,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0),
            stat.S_IMODE(os.fstat(source_fd).st_mode),
        )
        try:
            try:
                fcntl.ioctl(destination_fd, FICLONE, source_fd)
                method = "reflink"
            except OSError:
                with os.fdopen(os.dup(source_fd), "rb") as reader:
                    with os.fdopen(os.dup(destination_fd), "wb") as writer:
                        shutil.copyfileobj(reader, writer, 1024 * 1024)
            os.fchmod(destination_fd, stat.S_IMODE(os.fstat(source_fd).st_mode))
        finally:
            os.close(destination_fd)
    finally:
        os.close(source_fd)
    return str(destination_path) if method == "copy" else str(destination_path)


def _copy_tree(source: Path, destination: Path) -> None:
    require(not os.path.lexists(destination), f"copy destination exists: {destination}")
    shutil.copytree(source, destination, symlinks=False, copy_function=_copy_file)


def _write_exclusive(path: Path, value: Mapping[str, Any]) -> FileSeal:
    require(path.parent.is_dir(), "exclusive output parent is missing")
    raw = canonical_json(value)
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    descriptor = os.open(path, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        os.close(descriptor)
    return FileSeal(path, hashlib.sha256(raw).hexdigest(), len(raw))


def _copy_project_static(plan: Plan, destination: Path) -> None:
    destination.mkdir(mode=0o700)
    _copy_file(
        str(plan.source_descriptor.path),
        str(destination / contract.PROJECT_DESCRIPTOR_NAME),
    )
    for root_name in STATIC_ROOTS:
        source = plan.source_project.root / root_name
        if source.exists():
            _copy_tree(source, destination / root_name)
    copied = live_tree.compute_project_static_tree(
        destination / contract.PROJECT_DESCRIPTOR_NAME
    )
    require(
        copied
        == {
            "algorithm": "sha256-path-nul-mode-size-content-v1",
            "tree_sha256": plan.source_project.tree_sha256,
            "file_count": plan.source_project.file_count,
            "total_bytes": plan.source_project.total_bytes,
        },
        "fresh R6 project copy differs before overlays",
    )


def _overlay_tree(source: TreePin, destination: Path, label: str) -> None:
    if os.path.lexists(destination):
        require(destination.is_dir() and not destination.is_symlink(), f"{label} destination is unsafe")
        shutil.rmtree(destination)
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    _copy_tree(source.root, destination)
    observed = build_home.snapshot_tree(destination, f"copied {label}")
    require(
        observed.sha256 == source.tree_sha256
        and observed.file_count == source.file_count
        and observed.total_bytes == source.total_bytes,
        f"copied {label} tree differs",
    )


def _sandbox_path(plan: Plan, path: Path) -> str:
    try:
        relative = path.relative_to(plan.attempt_root).as_posix()
    except ValueError as exc:
        raise RunnerError("attempt path escaped sandbox") from exc
    return "/vista/work/" + relative


def _execution_document(
    plan: Plan,
    project: Path,
    profile_copy: FileSeal,
    receipt_copies: Mapping[str, FileSeal],
) -> dict[str, Any]:
    fridge = next(item for item in plan.overlays if item.role == "fridge")
    inventory = {
        item.role: [copy.deepcopy(record) for record in item.inventory]
        for item in plan.overlays
    }
    return contract.seal_document(
        {
            "schema_version": contract.EXECUTION_SCHEMA,
            "acknowledgement": contract.ACKNOWLEDGEMENT,
            "engine_version": contract.ENGINE_VERSION,
            "attempt_root": "/vista/work",
            "project": {
                "file": "/vista/work/project/" + contract.PROJECT_DESCRIPTOR_NAME,
                "descriptor_sha256": plan.source_descriptor.sha256,
                "map_object_path": contract.MAP_OBJECT_PATH,
                "map_file": "/vista/work/project/" + contract.MAP_RELATIVE_PATH,
                "source_map_sha256": plan.source_map.sha256,
                "source_map_size_bytes": plan.source_map.size_bytes,
                "source_static_tree": plan.source_project.public(
                    root="/vista/source-r6"
                ),
            },
            "typed_profile": {
                **profile_copy.public(path=_sandbox_path(plan, profile_copy.path)),
                "profile_id": contract.TYPED_PROFILE_ID,
                "content_digest": contract.TYPED_PROFILE_CONTENT_DIGEST,
            },
            "compiled_plugin": plan.plugin.public(
                root="/vista/work/project/Plugins/VistaPlayableHome"
            ),
            "overlays": {
                item.role: {
                    "tree": item.tree.public(
                        root=(
                            "/vista/work/project/"
                            + contract.OVERLAY_DESTINATIONS[item.role]
                        )
                    ),
                    "namespace": contract.OVERLAY_NAMESPACES[item.role],
                    "inventory": inventory[item.role],
                    "receipt": receipt_copies[item.role].public(
                        path=_sandbox_path(plan, receipt_copies[item.role].path)
                    ),
                }
                for item in plan.overlays
            },
            "fridge_binding": {
                "articulated_actor": copy.deepcopy(
                    fridge.receipt_value["articulated_actor"]
                ),
                "legacy": copy.deepcopy(
                    next(
                        value
                        for value in (
                            fridge.receipt_value.get("legacy"),
                            fridge.supporting_value.get("legacy")
                            if fridge.supporting_value is not None
                            else None,
                        )
                        if type(value) is dict
                    )
                ),
                "imported_assets": copy.deepcopy(
                    fridge.receipt_value["imported_assets"]
                ),
            },
            "ycb_mesh_bindings": copy.deepcopy(contract.YCB_MESH_BINDINGS),
            "commandlet": plan.commandlet.public(
                path=(
                    "/vista/repository/"
                    + str(plan.commandlet.path.relative_to(REPOSITORY_ROOT))
                )
            ),
            "outputs": {
                "author": "/vista/work/evidence/" + AUTHOR_RECEIPT_NAME,
                "verify": "/vista/work/evidence/" + VERIFY_RECEIPT_NAME,
            },
            "policy": {
                "append_only_attempt": True,
                "source_r6_read_only": True,
                "main_map_only": True,
                "save_reload_required": True,
                "separate_cold_verify_process": True,
                "network_isolated": True,
                "live_services_mutated": False,
                "external_binary_assets_outside_git": True,
                "accepted": False,
            },
            "claims": copy.deepcopy(contract.NEGATIVE_CLAIMS),
            "legal_scope": copy.deepcopy(contract.LEGAL_SCOPE),
        }
    )


def _bwrap_command(
    plan: Plan, execution_sha256: str, mode: str
) -> list[str]:
    relative = plan.commandlet.path.relative_to(REPOSITORY_ROOT).as_posix()
    return [
        str(plan.bwrap.path),
        "--unshare-net",
        "--unshare-pid",
        "--die-with-parent",
        "--dev-bind",
        "/",
        "/",
        "--tmpfs",
        "/vista",
        "--dir",
        "/vista/engine",
        "--dir",
        "/vista/repository",
        "--dir",
        "/vista/source-r6",
        "--dir",
        "/vista/work",
        "--ro-bind",
        str(plan.unreal_editor.path.parents[3]),
        "/vista/engine",
        "--ro-bind",
        str(REPOSITORY_ROOT),
        "/vista/repository",
        "--ro-bind",
        str(plan.source_project.root),
        "/vista/source-r6",
        "--bind",
        str(plan.attempt_root),
        "/vista/work",
        "--setenv",
        "HOME",
        "/vista/work/runtime/home",
        "--setenv",
        "TMPDIR",
        "/vista/work/runtime/tmp",
        "--setenv",
        "LANG",
        "C.UTF-8",
        "--setenv",
        "PYTHONNOUSERSITE",
        "1",
        "--setenv",
        "PYTHONDONTWRITEBYTECODE",
        "1",
        "--setenv",
        contract.EXECUTION_ENV,
        "/vista/work/inputs/" + EXECUTION_NAME,
        "--setenv",
        contract.EXECUTION_SHA_ENV,
        execution_sha256,
        "--setenv",
        contract.MODE_ENV,
        mode,
        "--chdir",
        "/vista/work",
        "--",
        "/vista/engine/Engine/Binaries/Linux/UnrealEditor-Cmd",
        "/vista/work/project/" + contract.PROJECT_DESCRIPTOR_NAME,
        "-nullrhi",
        "-nosound",
        "-unattended",
        "-nop4",
        "-nosplash",
        "-notraceserver",
        "-NoAnalytics",
        "-NoAssetRegistryCache",
        "-NoHotReloadFromIDE",
        "-NoEngineChanges",
        "-DDC-ForceMemoryCache",
        "-UDPMESSAGING_TRANSPORT_ENABLE=0",
        "-ini:Engine:[/Script/TcpMessaging.TcpMessagingSettings]:EnableTransport=False",
        "-EnablePlugins=VistaPlayableHome",
        "-ExecutePythonScript=/vista/repository/" + relative,
        "-AbsLog=/vista/work/evidence/r20-" + mode + "-unreal.log",
        "-stdout",
        "-FullStdOutLogOutput",
    ]


def _run_process(argv: Sequence[str], stdout: Path, stderr: Path) -> None:
    with stdout.open("xb") as stdout_stream, stderr.open("xb") as stderr_stream:
        process = subprocess.Popen(
            list(argv),
            stdin=subprocess.DEVNULL,
            stdout=stdout_stream,
            stderr=stderr_stream,
            env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"},
            start_new_session=True,
        )
        try:
            code = process.wait(timeout=TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired as exc:
            try:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=10)
            except (OSError, subprocess.TimeoutExpired):
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            raise RunnerError("UE R20 process timed out") from exc
    require(code == 0, f"UE R20 process exited {code}")


def validate_worker_receipt(
    path: Path, mode: str, execution_sha256: str
) -> tuple[dict[str, Any], FileSeal]:
    value, seal = strict_json(path, f"R20 {mode} receipt")
    gates = value.get("inspection", {}).get("gates", {})
    require(
        value.get("schema_version") == contract.WORKER_SCHEMA
        and value.get("status") == contract.WORKER_SUCCESS_STATUS
        and value.get("mode") == mode
        and value.get("execution_sha256") == execution_sha256
        and value.get("accepted") is False
        and value.get("error") is None
        and value.get("content_digest") == content_digest(value)
        and value.get("claims") == contract.NEGATIVE_CLAIMS
        and value.get("legal_scope") == contract.LEGAL_SCOPE
        and gates.get("exact_classes_and_semantic_ids") is True
        and gates.get("exact_anchor_transforms") is True
        and gates.get("exact_mesh_bindings") is True
        and gates.get("old_authorities_absent") is True
        and gates.get("duplicate_semantic_ids_absent") is True
        and gates.get("seat_hssd_shells_preserved") is True
        and gates.get("fridge_hssd_lineage_preserved") is True
        and gates.get("map_saved_reloaded") is True,
        f"R20 {mode} receipt differs",
    )
    return value, seal


def _revalidate_sources(plan: Plan) -> None:
    bindings, binding_seal = _parse_bindings(
        plan.bindings_path, plan.bindings_seal.sha256
    )
    require(bindings == plan.bindings and binding_seal == plan.bindings_seal, "bindings changed")
    observed_project = live_tree.compute_project_static_tree(plan.source_descriptor.path)
    require(
        observed_project["tree_sha256"] == plan.source_project.tree_sha256
        and observed_project["file_count"] == plan.source_project.file_count
        and observed_project["total_bytes"] == plan.source_project.total_bytes,
        "R6 source changed after UE",
    )
    for expected in (
        plan.source_descriptor,
        plan.source_map,
        plan.source_manifest,
        plan.typed_profile,
        plan.unreal_editor,
        plan.bwrap,
        plan.commandlet,
    ):
        require(sha256_file(expected.path) == expected, f"source file changed: {expected.path}")
    for expected in (plan.plugin, *(item.tree for item in plan.overlays)):
        observed = build_home.snapshot_tree(expected.root, "post-UE source tree")
        require(
            observed.sha256 == expected.tree_sha256
            and observed.file_count == expected.file_count
            and observed.total_bytes == expected.total_bytes,
            f"source tree changed after UE: {expected.root}",
        )
    for item in plan.overlays:
        require(sha256_file(item.receipt.path) == item.receipt, f"{item.role} receipt changed")
        if item.supporting is not None:
            require(
                sha256_file(item.supporting.path) == item.supporting,
                f"{item.role} supporting evidence changed",
            )


def _candidate_overlay_gates(plan: Plan, project: Path) -> dict[str, Any]:
    plugin_root = project / "Plugins/VistaPlayableHome"
    observed_plugin = build_home.snapshot_tree(plugin_root, "candidate plugin")
    require(
        observed_plugin.sha256 == plan.plugin.tree_sha256
        and observed_plugin.file_count == plan.plugin.file_count
        and observed_plugin.total_bytes == plan.plugin.total_bytes,
        "candidate plugin changed during UE",
    )
    overlays = {}
    for item in plan.overlays:
        destination = project / contract.OVERLAY_DESTINATIONS[item.role]
        observed = build_home.snapshot_tree(destination, f"candidate {item.role}")
        require(
            observed.sha256 == item.tree.tree_sha256
            and observed.file_count == item.tree.file_count
            and observed.total_bytes == item.tree.total_bytes,
            f"candidate {item.role} overlay changed during UE",
        )
        overlays[item.role] = item.tree.public(root=str(destination))
    return {"plugin": plan.plugin.public(root=str(plugin_root)), "overlays": overlays}


def execute(plan: Plan, acknowledgement: str) -> dict[str, Any]:
    require(acknowledgement == contract.ACKNOWLEDGEMENT, "exact acknowledgement is required")
    # Rebuild the dry-run plan before the first write and require identical bytes.
    fresh = build_plan(
        plan.attempt_name, plan.bindings_path, plan.bindings_seal.sha256
    )
    require(fresh.report == plan.report, "dry-run plan changed before execution")
    plan.attempt_root.mkdir(mode=0o700)
    project = plan.attempt_root / "project"
    inputs = plan.attempt_root / "inputs"
    receipts = inputs / "receipts"
    evidence = plan.attempt_root / "evidence"
    runtime = plan.attempt_root / "runtime"
    for directory in (inputs, receipts, evidence, runtime, runtime / "home", runtime / "tmp"):
        directory.mkdir(mode=0o700)
    _copy_project_static(plan, project)

    _overlay_tree(plan.plugin, project / "Plugins/VistaPlayableHome", "compiled plugin")
    for item in plan.overlays:
        _overlay_tree(
            item.tree,
            project / contract.OVERLAY_DESTINATIONS[item.role],
            item.role,
        )

    profile_path = inputs / "typed-scene-profile.json"
    _copy_file(str(plan.typed_profile.path), str(profile_path))
    profile_copy = sha256_file(profile_path)
    require(
        (profile_copy.sha256, profile_copy.size_bytes)
        == (plan.typed_profile.sha256, plan.typed_profile.size_bytes),
        "typed profile copy differs",
    )
    receipt_copies: dict[str, FileSeal] = {}
    for item in plan.overlays:
        destination = receipts / (item.role + ".json")
        _copy_file(str(item.receipt.path), str(destination))
        copied = sha256_file(destination)
        require(
            (copied.sha256, copied.size_bytes)
            == (item.receipt.sha256, item.receipt.size_bytes),
            f"{item.role} receipt copy differs",
        )
        receipt_copies[item.role] = copied

    execution_value = _execution_document(plan, project, profile_copy, receipt_copies)
    execution_seal = _write_exclusive(inputs / EXECUTION_NAME, execution_value)
    _run_process(
        _bwrap_command(plan, execution_seal.sha256, contract.AUTHOR_MODE),
        evidence / "r20-author-stdout.log",
        evidence / "r20-author-stderr.log",
    )
    author, author_seal = validate_worker_receipt(
        evidence / AUTHOR_RECEIPT_NAME,
        contract.AUTHOR_MODE,
        execution_seal.sha256,
    )
    _run_process(
        _bwrap_command(plan, execution_seal.sha256, contract.VERIFY_MODE),
        evidence / "r20-verify-stdout.log",
        evidence / "r20-verify-stderr.log",
    )
    verify, verify_seal = validate_worker_receipt(
        evidence / VERIFY_RECEIPT_NAME,
        contract.VERIFY_MODE,
        execution_seal.sha256,
    )
    require(author["inspection"] == verify["inspection"], "cold inspection differs from author")

    _revalidate_sources(plan)
    candidate_inputs = _candidate_overlay_gates(plan, project)
    first_target = live_tree.compute_project_static_tree(
        project / contract.PROJECT_DESCRIPTOR_NAME
    )
    second_target = live_tree.compute_project_static_tree(
        project / contract.PROJECT_DESCRIPTOR_NAME
    )
    require(first_target == second_target, "target static tree changed during publication")
    require(
        first_target["tree_sha256"] != plan.source_project.tree_sha256,
        "target project did not change from R6",
    )
    receipt = contract.seal_document(
        {
            "schema_version": contract.HOST_RECEIPT_SCHEMA,
            "status": contract.SUCCESS_STATUS,
            "accepted": False,
            "attempt_name": plan.attempt_name,
            "project": str(project),
            "source_project_static_tree": plan.source_project.public(),
            "target_project_static_tree": first_target,
            "source_inputs_revalidated_after_ue": True,
            "target_tree_verified_twice_identical": True,
            "candidate_input_trees": candidate_inputs,
            "evidence": {
                "execution": execution_seal.public(),
                "author": author_seal.public(),
                "cold_verify": verify_seal.public(),
            },
            "inspection": copy.deepcopy(author["inspection"]),
            "claims": copy.deepcopy(contract.NEGATIVE_CLAIMS),
            "legal_scope": copy.deepcopy(contract.LEGAL_SCOPE),
        }
    )
    _write_exclusive(plan.attempt_root / HOST_RECEIPT_NAME, receipt)
    return receipt


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--attempt-name", required=True)
    value.add_argument("--bindings", required=True, type=Path)
    value.add_argument("--bindings-sha256", required=True)
    value.add_argument("--execute", action="store_true")
    value.add_argument("--acknowledgement", default="")
    return value


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    plan = build_plan(args.attempt_name, args.bindings, args.bindings_sha256)
    result = execute(plan, args.acknowledgement) if args.execute else plan.report
    print(canonical_json(result).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
