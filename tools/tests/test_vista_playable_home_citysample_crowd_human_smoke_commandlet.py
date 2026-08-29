from __future__ import annotations

import ast
import hashlib
import json
import pathlib
import types

import pytest

from tools.ue.vista_playable_home import run_citysample_crowd_human_smoke as runner

ROOT = pathlib.Path(__file__).resolve().parents[2]
COMMANDLET = (
    ROOT / "tools/ue/vista_playable_home/citysample_crowd_human_smoke_commandlet.py"
)


def _pure_commandlet() -> types.ModuleType:
    tree = ast.parse(COMMANDLET.read_text(encoding="utf-8"), filename=str(COMMANDLET))
    body = []
    for node in tree.body:
        if isinstance(node, ast.Import) and any(
            alias.name == "unreal" for alias in node.names
        ):
            continue
        if (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name)
            and node.value.func.id == "main"
        ):
            continue
        body.append(node)
    tree.body = body
    ast.fix_missing_locations(tree)
    module = types.ModuleType("citysample_crowd_human_smoke_commandlet_test")
    module.__dict__["unreal"] = types.SimpleNamespace()
    exec(compile(tree, str(COMMANDLET), "exec"), module.__dict__)  # noqa: S102
    return module


class _AssetData:
    def __init__(
        self,
        class_name: str,
        object_path: str | None = None,
        *,
        asset_name: str | None = None,
        package_name: str | None = None,
    ) -> None:
        self.asset_class_path = "/Script/Engine." + class_name
        if object_path is not None:
            self.object_path = object_path
            inferred_package, inferred_name = object_path.rsplit(".", 1)
            package_name = package_name or inferred_package
            asset_name = asset_name or inferred_name
        self.asset_name = asset_name
        self.package_name = package_name

    def get_editor_property(self, name: str):
        return getattr(self, name)


class _Registry:
    def __init__(self) -> None:
        self.dependencies = {
            "/Game/CitySampleCrowd/Blueprints/BP_CrowdCharacter": [
                "/Game/CitySampleCrowd/Blueprints/NPC1_AnimBP",
                "/Game/CitySampleCrowd/Character/Female/NormalWeight/Meshes/f_tal_nrw_body",
            ],
            "/Game/CitySampleCrowd/Blueprints/NPC1_AnimBP": [
                "/Game/CitySampleCrowd/Character/Shared/Rig/metahuman_base_skel"
            ],
        }
        self.assets = {
            "/Game/CitySampleCrowd/Blueprints/BP_CrowdCharacter": [
                _AssetData(
                    "BlueprintGeneratedClass",
                    asset_name="BP_CrowdCharacter_C",
                    package_name=("/Game/CitySampleCrowd/Blueprints/BP_CrowdCharacter"),
                ),
                _AssetData(
                    "Blueprint",
                    asset_name="BP_CrowdCharacter",
                    package_name=("/Game/CitySampleCrowd/Blueprints/BP_CrowdCharacter"),
                ),
            ],
            "/Game/CitySampleCrowd/Blueprints/NPC1_AnimBP": [
                _AssetData(
                    "AnimBlueprint",
                    "/Game/CitySampleCrowd/Blueprints/NPC1_AnimBP.NPC1_AnimBP",
                )
            ],
            "/Game/CitySampleCrowd/Character/Female/NormalWeight/Meshes/f_tal_nrw_body": [
                _AssetData(
                    "SkeletalMesh",
                    "/Game/CitySampleCrowd/Character/Female/NormalWeight/Meshes/"
                    "f_tal_nrw_body.f_tal_nrw_body",
                )
            ],
            "/Game/CitySampleCrowd/Character/Shared/Rig/metahuman_base_skel": [
                _AssetData(
                    "Skeleton",
                    "/Game/CitySampleCrowd/Character/Shared/Rig/"
                    "metahuman_base_skel.metahuman_base_skel",
                )
            ],
        }

    def get_dependencies(self, package: str, _options):
        return self.dependencies.get(package, [])

    def get_assets_by_package_name(self, package: str, _disk_only=True):
        return self.assets.get(package, [])


def test_recursive_asset_registry_closure_reaches_anim_mesh_and_skeleton() -> None:
    module = _pure_commandlet()
    registry = _Registry()

    dependencies = module._recursive_dependencies(
        registry,
        module.TARGET_PACKAGE,
        object(),
    )
    records, class_counts = module._dependency_class_inventory(registry, dependencies)

    assert dependencies == sorted(
        [
            "/Game/CitySampleCrowd/Blueprints/NPC1_AnimBP",
            "/Game/CitySampleCrowd/Character/Female/NormalWeight/Meshes/f_tal_nrw_body",
            "/Game/CitySampleCrowd/Character/Shared/Rig/metahuman_base_skel",
        ]
    )
    assert class_counts == {"AnimBlueprint": 1, "SkeletalMesh": 1, "Skeleton": 1}
    assert len(records) == 3


def test_target_asset_data_requires_exact_stably_ordered_blueprint_pair() -> None:
    module = _pure_commandlet()
    registry = _Registry()

    assert module._target_asset_data_evidence(registry) == (
        module.TARGET_ASSET_DATA_RECORDS
    )


@pytest.mark.parametrize("mutation", ["missing", "extra", "class", "name", "package"])
def test_target_asset_data_rejects_incomplete_or_wrong_inventory(mutation: str) -> None:
    module = _pure_commandlet()
    registry = _Registry()
    records = list(registry.assets[module.TARGET_PACKAGE])
    if mutation == "missing":
        records.pop()
    elif mutation == "extra":
        records.append(
            _AssetData(
                "Blueprint",
                asset_name="Unexpected",
                package_name=module.TARGET_PACKAGE,
            )
        )
    elif mutation == "class":
        records[0] = _AssetData(
            "Character",
            asset_name="BP_CrowdCharacter_C",
            package_name=module.TARGET_PACKAGE,
        )
    elif mutation == "name":
        records[0] = _AssetData(
            "BlueprintGeneratedClass",
            asset_name="Unrelated_C",
            package_name=module.TARGET_PACKAGE,
        )
    else:
        records[0] = _AssetData(
            "BlueprintGeneratedClass",
            asset_name="BP_CrowdCharacter_C",
            package_name="/Game/Other/BP_CrowdCharacter",
        )
    registry.assets[module.TARGET_PACKAGE] = records

    with pytest.raises(
        module.SmokeFailure, match="exact Blueprint and BlueprintGeneratedClass pair"
    ):
        module._target_asset_data_evidence(registry)


def test_key_dependency_evidence_rejects_rotated_global_class_counts() -> None:
    module = _pure_commandlet()
    dependencies = [
        binding["package_name"] for binding in module.KEY_DEPENDENCY_BINDINGS
    ]
    exact_records = [
        {
            "asset_class": binding["asset_class"],
            "object_path": binding["object_path"],
            "package_name": binding["package_name"],
        }
        for binding in module.KEY_DEPENDENCY_BINDINGS
    ]
    request = {"key_dependencies": module.KEY_DEPENDENCY_BINDINGS}

    evidence = module._key_dependency_evidence(exact_records, dependencies, request)
    assert [item["kind"] for item in evidence] == [
        "anim_blueprint",
        "skeletal_mesh",
        "skeleton",
    ]

    rotated = [dict(record) for record in exact_records]
    rotated[0]["asset_class"] = "SkeletalMesh"
    rotated[1]["asset_class"] = "Skeleton"
    rotated[2]["asset_class"] = "AnimBlueprint"
    assert sorted(record["asset_class"] for record in rotated) == [
        "AnimBlueprint",
        "SkeletalMesh",
        "Skeleton",
    ]
    with pytest.raises(module.SmokeFailure, match="exact key dependency"):
        module._key_dependency_evidence(rotated, dependencies, request)


class _FakePathObject:
    def __init__(self, path: str) -> None:
        self.path = path

    def get_path_name(self) -> str:
        return self.path


class _FakeCharacter(_FakePathObject):
    def __init__(self, path: str, component_count: int = 1) -> None:
        super().__init__(path)
        self.components = [object() for _ in range(component_count)]

    def get_components_by_class(self, _component_class):
        return self.components


def _class_binding_unreal(module, default_object: _FakeCharacter):
    blueprint = _FakePathObject(module.TARGET_OBJECT)
    generated_class = _FakePathObject(module.TARGET_CLASS)
    return types.SimpleNamespace(
        Character=_FakeCharacter,
        SkeletalMeshComponent=object,
        EditorAssetLibrary=types.SimpleNamespace(
            load_asset=lambda _path: blueprint,
            load_blueprint_class=lambda _path: generated_class,
        ),
        load_class=lambda _outer, _path: generated_class,
        get_default_object=lambda _loaded_class: default_object,
    )


def test_exact_generated_class_and_cdo_path_binding_rejects_unrelated_character() -> (
    None
):
    module = _pure_commandlet()
    module.unreal = _class_binding_unreal(
        module, _FakeCharacter(module.TARGET_CDO_PATH)
    )
    evidence = module._load_exact_target_class()
    assert evidence["generated_class_path"] == module.TARGET_CLASS
    assert evidence["default_object_path"] == module.TARGET_CDO_PATH

    # Being an Unreal Character is insufficient: its CDO must belong to the
    # exact pinned BP_CrowdCharacter GeneratedClass.
    module.unreal = _class_binding_unreal(
        module, _FakeCharacter("/Game/Other.Default__UnrelatedCharacter_C")
    )
    with pytest.raises(module.SmokeFailure, match="exact target class"):
        module._load_exact_target_class()


def test_sanitized_config_byte_pins_match_host_runner() -> None:
    module = _pure_commandlet()
    expected = {
        relative.as_posix(): (hashlib.sha256(raw).hexdigest(), len(raw))
        for relative, raw in runner.SANITIZED_CONFIG_FILES.items()
    }

    assert module.SANITIZED_CONFIG_PINS == expected
    assert module.PINNED_CONTENT_FILE_COUNT == runner.PINNED_CONTENT_FILE_COUNT
    assert module.PINNED_CONTENT_SIZE_BYTES == runner.PINNED_CONTENT_SIZE_BYTES
    assert (
        module.PINNED_CONTENT_METADATA_PROJECTION_SHA256
        == runner.PINNED_CONTENT_METADATA_PROJECTION_SHA256
    )
    default_engine = runner.SANITIZED_CONFIG_FILES[
        pathlib.PurePosixPath("Config/DefaultEngine.ini")
    ]
    assert (
        b"[/Script/AndroidFileServerEditor.AndroidFileServerRuntimeSettings]"
        in default_engine
    )
    assert b"bEnablePlugin=False" in default_engine
    assert b"SecurityToken" not in default_engine


def test_manifest_rejects_android_file_server_security_token_mutation(
    tmp_path: pathlib.Path,
) -> None:
    module = _pure_commandlet()
    project_root = tmp_path / "project"
    project_path = project_root / module.PROJECT_NAME
    project_path.parent.mkdir(parents=True)
    project_path.write_bytes(b"{}\n")

    records = []
    for relative, raw in runner.SANITIZED_CONFIG_FILES.items():
        candidate = project_root.joinpath(*relative.parts)
        candidate.parent.mkdir(parents=True, exist_ok=True)
        candidate.write_bytes(raw)
        records.append(
            {
                "project_relative_path": relative.as_posix(),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "size_bytes": len(raw),
                "source_kind": "project_generated_sanitized_config",
            }
        )

    content_raw = b"fixture-uasset"
    content_relative = "Content/Fixture.uasset"
    content_path = project_root / content_relative
    content_path.parent.mkdir(parents=True)
    content_path.write_bytes(content_raw)
    records.append(
        {
            "project_relative_path": content_relative,
            "sha256": hashlib.sha256(content_raw).hexdigest(),
            "size_bytes": len(content_raw),
            "source_kind": "pinned_source_content_copy",
        }
    )
    records.sort(key=lambda record: record["project_relative_path"])

    projection = "a" * 64
    module.PINNED_CONTENT_FILE_COUNT = 1
    module.PINNED_CONTENT_SIZE_BYTES = len(content_raw)
    module.PINNED_CONTENT_METADATA_PROJECTION_SHA256 = projection
    manifest = {
        "schema_version": module.COPY_MANIFEST_SCHEMA,
        "accepted": False,
        "copy_strategy": "full_content_and_sanitized_config_then_registry_audit",
        "source_metadata_projection_sha256": projection,
        "source_content_file_count": 1,
        "source_content_size_bytes": len(content_raw),
        "file_count": len(records),
        "size_bytes": sum(record["size_bytes"] for record in records),
        "files": records,
        "source_format_uassets_in_git": False,
        "source_config_copied": False,
        "source_network_settings_copied": False,
        "redistribution_authorized": False,
        "content_digest": "",
    }
    manifest["content_digest"] = module.content_digest(manifest)
    manifest_raw = module.canonical_json(manifest)
    manifest_path = tmp_path / module.COPY_MANIFEST_NAME
    manifest_path.write_bytes(manifest_raw)
    manifest_sha256 = hashlib.sha256(manifest_raw).hexdigest()
    manifest_path.with_name(manifest_path.name + ".sha256").write_text(
        f"{manifest_sha256}  {module.COPY_MANIFEST_NAME}\n",
        encoding="utf-8",
    )
    request = {
        "copy_manifest_sha256": manifest_sha256,
        "copy_projection_sha256": projection,
    }

    module._validate_copy_manifest(
        request, manifest_path.as_posix(), project_path.as_posix()
    )

    default_engine = project_root / "Config/DefaultEngine.ini"
    default_engine.write_bytes(
        default_engine.read_bytes()
        + b"SecurityToken=must-never-be-accepted-even-if-ue-generated-it\n"
    )
    with pytest.raises(module.SmokeFailure, match="copied size differs"):
        module._validate_copy_manifest(
            request, manifest_path.as_posix(), project_path.as_posix()
        )


def test_commandlet_authorization_requires_exact_six_true_fields() -> None:
    module = _pure_commandlet()
    required = {
        "epic_ue_only_content_entitlement_acknowledged": True,
        "large_full_content_copy_acknowledged": True,
        "metahuman_visual_demo_only_not_ai_training_testing_acknowledged": True,
        "no_redistribution_acknowledged": True,
        "private_noncommercial_research_acknowledged": True,
        "source_uassets_outside_git_acknowledged": True,
    }

    assert module._validate_authorization({"authorization": required}) == required
    missing = dict(required)
    missing.pop("metahuman_visual_demo_only_not_ai_training_testing_acknowledged")
    false_value = dict(required)
    false_value["metahuman_visual_demo_only_not_ai_training_testing_acknowledged"] = (
        False
    )
    variants = [missing, false_value, {**required, "unexpected_acknowledgement": True}]

    for authorization in variants:
        with pytest.raises(module.SmokeFailure, match="authorization differs"):
            module._validate_authorization({"authorization": authorization})


def test_engine_plugin_descriptor_pins_match_host_runner() -> None:
    module = _pure_commandlet()
    expected = [
        {
            "name": name,
            "relative_path": relative.as_posix(),
            "required_native_modules": list(
                runner.REQUIRED_NATIVE_MODULES_BY_PLUGIN[name]
            ),
            "sha256": sha256,
            "size_bytes": size_bytes,
        }
        for name, (relative, sha256, size_bytes) in runner.ENGINE_PLUGIN_PINS.items()
    ]

    assert module.ENGINE_PLUGIN_PINS == expected
    assert module.ENGINE_NATIVE_BINARY_PINS == [
        dict(pin) for pin in runner.ENGINE_NATIVE_BINARY_PINS
    ]
    assert module.ENGINE_MODULES_RECEIPT_PINS == [
        dict(pin) for pin in runner.ENGINE_MODULES_RECEIPT_PINS
    ]
    assert module.FIXED_COMMAND_ARGUMENTS_AFTER_SCRIPT == list(
        runner.FIXED_COMMAND_ARGUMENTS_AFTER_SCRIPT
    )
    assert module.NETWORK_TRANSPORT_DISABLE_FLAGS == list(
        runner.NETWORK_TRANSPORT_DISABLE_FLAGS
    )


def test_native_module_authority_constants_match_exact_ue57_files() -> None:
    module = _pure_commandlet()

    assert module.ENGINE_PLUGIN_PINS[-1] == {
        "name": "RigLogic",
        "relative_path": "Engine/Plugins/Animation/RigLogic/RigLogic.uplugin",
        "required_native_modules": [
            "RigLogicLib",
            "RigLogicModule",
            "RigLogicDeveloper",
        ],
        "sha256": ("c6ce682b00793943614fea31fdae5c201a6a4595f96bf4a901d3657f79e5e340"),
        "size_bytes": 1_044,
    }
    assert [
        (
            pin["module_name"],
            pin["binary_sha256"],
            pin["binary_size_bytes"],
        )
        for pin in module.ENGINE_NATIVE_BINARY_PINS
    ] == [
        (
            "HairStrandsCore",
            "9c23d053f91222a8a2384cad77e3b97ae26b9e3ba4b2a02cc53bcbd6fbd95849",
            4_211_808,
        ),
        (
            "MassActors",
            "06397bf474c86e8ea039a93a6b2c827101cb4d3af4ef244887fa43d39ffaa734",
            552_848,
        ),
        (
            "PythonScriptPlugin",
            "0bdb1456413da669eae53cf61795c25a70376050445d340e8277b452a66032be",
            7_959_824,
        ),
        (
            "PythonScriptPluginPreload",
            "aaf9458af7925a23fc003f258115027f20cb2640c0c742196a5f1ee3ae7a2655",
            364_128,
        ),
        (
            "RigLogicLib",
            "efda18f1bb2d361ca96833541d4f95e9240c44a491c882dd5cd7ae3beb15968e",
            1_942_744,
        ),
        (
            "RigLogicModule",
            "c5244c83d59cbfda87e07554c7f59da04601202f23ca69a191d26f670b067b64",
            849_728,
        ),
        (
            "RigLogicDeveloper",
            "d53c036d5f4b7e695f1d1107de0ab248bdf29fa41979580c9f4d89d0053fdefb",
            59_464,
        ),
    ]
    assert [
        (
            pin["plugin_name"],
            pin["modules_receipt_sha256"],
            pin["modules_receipt_size_bytes"],
        )
        for pin in module.ENGINE_MODULES_RECEIPT_PINS
    ] == [
        (
            "HairStrands",
            "915bfaaaa00fb6e8bae41b5ca3f7ca1bc61814ca8e1cc84dc6bd19e0f44f70ad",
            510,
        ),
        (
            "MassGameplay",
            "0e5ce59af3f6285cdc48124c15dad7c2fe8a76321d29a882913b04c7ba80ed78",
            971,
        ),
        (
            "PythonScriptPlugin",
            "6f436c8e22ce1b75ac0721a91a257b731131932b80b9328835cbb1e361aaff3b",
            189,
        ),
        (
            "RigLogic",
            "d92089953171e325bb03cf40be10138ee1d77d4143d0e529eb62fc9233b2ab62",
            273,
        ),
    ]


def _plugin_descriptor_fixture(module, tmp_path: pathlib.Path):
    engine_directory = (tmp_path / "Engine").resolve()
    pins = []
    paths = {}
    for raw_pin in module.ENGINE_PLUGIN_PINS:
        pin = dict(raw_pin)
        descriptor = tmp_path.joinpath(*pin["relative_path"].split("/"))
        descriptor.parent.mkdir(parents=True, exist_ok=True)
        descriptor.write_bytes(
            json.dumps(
                {
                    "FileVersion": 3,
                    "Modules": [
                        {"Name": name, "Type": "Runtime"}
                        for name in pin["required_native_modules"]
                    ],
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
            + b"\n"
        )
        pin["sha256"] = hashlib.sha256(descriptor.read_bytes()).hexdigest()
        pin["size_bytes"] = descriptor.stat().st_size
        pins.append(pin)
        paths[pin["name"]] = descriptor
    module.ENGINE_PLUGIN_PINS = pins
    return engine_directory.as_posix(), pins, paths


def test_commandlet_validates_riglogic_descriptor_and_rejects_mutation(
    tmp_path: pathlib.Path,
) -> None:
    module = _pure_commandlet()
    engine_directory, pins, paths = _plugin_descriptor_fixture(module, tmp_path)
    request = {"engine_plugin_descriptors": pins}

    evidence = module._validate_engine_plugin_descriptors(request, engine_directory)
    assert evidence[-1] == {
        **pins[-1],
        "descriptor_file_validated": True,
    }

    mutated_request = json.loads(json.dumps(request))
    mutated_request["engine_plugin_descriptors"][-1]["sha256"] = "0" * 64
    with pytest.raises(module.SmokeFailure, match="descriptor pins differ"):
        module._validate_engine_plugin_descriptors(mutated_request, engine_directory)

    descriptor = paths["RigLogic"]
    descriptor.write_bytes(descriptor.read_bytes() + b"mutated")
    with pytest.raises(module.SmokeFailure, match="descriptor differs"):
        module._validate_engine_plugin_descriptors(request, engine_directory)


def _native_authority_fixture(module, tmp_path: pathlib.Path):
    engine_directory = (tmp_path / "Engine").resolve()
    binary_pins = []
    binary_paths = {}
    for raw_pin in module.ENGINE_NATIVE_BINARY_PINS:
        pin = dict(raw_pin)
        binary = tmp_path.joinpath(*pin["binary_relative_path"].split("/"))
        binary.parent.mkdir(parents=True, exist_ok=True)
        binary.write_bytes(f"{pin['module_name']}-binary".encode())
        pin["binary_sha256"] = hashlib.sha256(binary.read_bytes()).hexdigest()
        pin["binary_size_bytes"] = binary.stat().st_size
        binary_pins.append(pin)
        binary_paths[pin["module_name"]] = binary
    receipt_pins = []
    receipt_paths = {}
    for raw_pin in module.ENGINE_MODULES_RECEIPT_PINS:
        pin = {**dict(raw_pin), "module_bindings": dict(raw_pin["module_bindings"])}
        receipt = tmp_path.joinpath(*pin["modules_receipt_relative_path"].split("/"))
        receipt.parent.mkdir(parents=True, exist_ok=True)
        receipt.write_bytes(
            json.dumps(
                {
                    "BuildId": pin["modules_receipt_build_id"],
                    "Modules": pin["module_bindings"],
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
            + b"\n"
        )
        pin["modules_receipt_sha256"] = hashlib.sha256(receipt.read_bytes()).hexdigest()
        pin["modules_receipt_size_bytes"] = receipt.stat().st_size
        receipt_pins.append(pin)
        receipt_paths[pin["plugin_name"]] = receipt
    module.ENGINE_NATIVE_BINARY_PINS = binary_pins
    module.ENGINE_MODULES_RECEIPT_PINS = receipt_pins
    return (
        engine_directory.as_posix(),
        module._native_authority_contract(),
        binary_paths,
        receipt_paths,
    )


def test_commandlet_validates_exact_native_module_binary_and_receipt_binding(
    tmp_path: pathlib.Path,
) -> None:
    module = _pure_commandlet()
    engine_directory, authority, _binaries, _receipts = _native_authority_fixture(
        module, tmp_path
    )
    request = {"engine_native_authority": authority}

    evidence = module._validate_engine_native_authority(request, engine_directory)

    assert evidence["inventory"] == {
        "binary_file_count": 7,
        "distinct_file_count": 11,
        "modules_receipt_file_count": 4,
        "shared_modules_receipt_paths": [
            "Engine/Plugins/Animation/RigLogic/Binaries/Linux/UnrealEditor.modules",
            (
                "Engine/Plugins/Experimental/PythonScriptPlugin/Binaries/Linux/"
                "UnrealEditor.modules"
            ),
        ],
    }
    assert len(evidence["binary_files"]) == 7
    assert len(evidence["modules_receipt_files"]) == 4


def test_commandlet_rejects_mutated_native_module_request_or_disk_bytes(
    tmp_path: pathlib.Path,
) -> None:
    module = _pure_commandlet()
    engine_directory, authority, binaries, _receipts = _native_authority_fixture(
        module, tmp_path
    )
    mutated_request = json.loads(json.dumps({"engine_native_authority": authority}))
    riglogic_developer = next(
        pin
        for pin in mutated_request["engine_native_authority"]["binary_files"]
        if pin["module_name"] == "RigLogicDeveloper"
    )
    riglogic_developer["binary_sha256"] = "0" * 64
    with pytest.raises(module.SmokeFailure, match="native authority differs"):
        module._validate_engine_native_authority(mutated_request, engine_directory)

    binary = binaries["RigLogicDeveloper"]
    binary.write_bytes(binary.read_bytes() + b"mutated")
    with pytest.raises(module.SmokeFailure, match="native module binary differs"):
        module._validate_engine_native_authority(
            {"engine_native_authority": authority}, engine_directory
        )


def test_commandlet_rejects_byte_pinned_receipt_with_wrong_module_binding(
    tmp_path: pathlib.Path,
) -> None:
    module = _pure_commandlet()
    engine_directory, authority, _binaries, receipts = _native_authority_fixture(
        module, tmp_path
    )
    receipt = receipts["RigLogic"]
    receipt.write_bytes(
        json.dumps(
            {
                "BuildId": "47537391",
                "Modules": {
                    "RigLogicDeveloper": "libUnrealEditor-UnrelatedDeveloper.so",
                    "RigLogicEditor": "libUnrealEditor-RigLogicEditor.so",
                    "RigLogicLib": "libUnrealEditor-RigLogicLib.so",
                    "RigLogicModule": "libUnrealEditor-RigLogicModule.so",
                },
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        + b"\n"
    )
    riglogic_receipt_pin = next(
        pin
        for pin in module.ENGINE_MODULES_RECEIPT_PINS
        if pin["plugin_name"] == "RigLogic"
    )
    riglogic_receipt_pin["modules_receipt_sha256"] = hashlib.sha256(
        receipt.read_bytes()
    ).hexdigest()
    riglogic_receipt_pin["modules_receipt_size_bytes"] = receipt.stat().st_size
    authority = module._native_authority_contract()

    with pytest.raises(module.SmokeFailure, match="module receipt binding differs"):
        module._validate_engine_native_authority(
            {"engine_native_authority": authority}, engine_directory
        )


def test_key_dependency_bindings_match_host_runner() -> None:
    module = _pure_commandlet()
    expected = []
    for relative, (sha256, size_bytes, kind) in runner.KEY_SOURCE_PINS.items():
        package = "/Game/" + relative.with_suffix("").relative_to("Content").as_posix()
        expected.append(
            {
                "asset_class": runner.KEY_KIND_ASSET_CLASSES[kind],
                "kind": kind,
                "object_path": package + "." + relative.stem,
                "package_name": package,
                "project_relative_path": relative.as_posix(),
                "sha256": sha256,
                "size_bytes": size_bytes,
            }
        )

    assert module.KEY_DEPENDENCY_BINDINGS == expected


def test_dependency_query_failure_and_malformed_name_fail_closed() -> None:
    module = _pure_commandlet()

    class FailedRegistry:
        def get_dependencies(self, _package, _options):
            return False, []

    with pytest.raises(module.SmokeFailure, match="dependency query failed"):
        module._recursive_dependencies(
            FailedRegistry(), module.TARGET_PACKAGE, object()
        )

    class MalformedRegistry:
        def get_dependencies(self, _package, _options):
            return ["relative/package"]

    with pytest.raises(module.SmokeFailure, match="dependency name differs"):
        module._recursive_dependencies(
            MalformedRegistry(), module.TARGET_PACKAGE, object()
        )


def test_commandlet_is_read_only_pinned_and_non_promoting() -> None:
    source = COMMANDLET.read_text(encoding="utf-8")
    compile(source, str(COMMANDLET), "exec")

    assert "unreal.AssetRegistryHelpers.get_asset_registry()" in source
    assert "registry.get_dependencies" in source
    assert "sha256_file(candidate) == digest" in source
    assert "sorted(actual_paths) == observed_paths" in source
    assert "full_content_and_sanitized_config_then_registry_audit" in source
    assert "SANITIZED_CONFIG_PINS" in source
    assert "ENGINE_PLUGIN_PINS" in source
    assert "ENGINE_NATIVE_BINARY_PINS" in source
    assert "ENGINE_MODULES_RECEIPT_PINS" in source
    assert "_validate_engine_plugin_descriptors" in source
    assert "_validate_engine_native_authority" in source
    assert "binary_file_validated" in source
    assert "modules_receipt_binding_validated" in source
    assert "KEY_DEPENDENCY_BINDINGS" in source
    assert "TARGET_CDO_PATH" in source
    assert "unreal.load_class(None, TARGET_CLASS)" in source
    assert "unreal.EditorAssetLibrary.load_blueprint_class(TARGET_OBJECT)" in source
    assert "unreal.get_default_object(loaded_class)" in source
    assert "get_components_by_class(unreal.SkeletalMeshComponent)" in source
    assert '"AnimBlueprint", "SkeletalMesh", "Skeleton"' in source
    assert '"accepted": False' in source
    assert '"runtime_visual_acceptance": False' in source
    assert '"character_provider_published": False' in source
    assert '"-NoMessaging"' in source
    assert "save_asset" not in source
    assert "save_package" not in source
    assert "duplicate_asset" not in source
    assert "spawn_actor" not in source
    assert "main()" == source.strip().splitlines()[-1]


def test_commandlet_contains_no_live_display_gpu1_port_or_source_project_path() -> None:
    source = COMMANDLET.read_text(encoding="utf-8")

    for forbidden in (
        ":117",
        "CUDA_VISIBLE_DEVICES=1",
        "8000",
        "55620",
        "55621",
        "/mnt/NAS2/yhliu/SimWorldStudio",
    ):
        assert forbidden not in source
