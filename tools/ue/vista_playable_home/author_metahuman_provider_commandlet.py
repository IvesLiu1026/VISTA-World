"""Fixed UE 5.7 commandlet for the first VISTA MetaHuman provider.

The host-side materializer supplies a byte-pinned request through environment
variables.  This script never accepts arbitrary Python, asset paths, account
tokens, or caller-selected provider classes.  It creates only the approved
Vivian private-research provider in a fresh append-only project.
"""

from __future__ import annotations

import hashlib
import json
import os
import re

import unreal


REQUEST_SCHEMA = "vista.metahuman-provider-authoring-request/v1"
RESULT_SCHEMA = "vista.metahuman-provider-authoring-result/v1"
PROVIDER_ID = "metahuman_vivian_ue57_v1"
ENGINE_VERSION = "5.7.3-50162420+++UE5+Release-5.7"
PROVIDER_SPEC_CONTENT_DIGEST = (
    "d22f5438b2900992e64f701243b22d803daae64f4cfa469fbd5da27cba9437c1"
)
PROVIDER_SPEC_SHA256 = (
    "a1f1b3f5fe0e599ad3dcc4fa491182048d8aad6f98fb38a165240c030e9e5fdf"
)
PLUGIN_DESCRIPTOR_SHA256 = (
    "cdcbb519ae3b53aeb1c4bdaf9000cdd787c315543bff24e968b9243c6179df5c"
)
PRESET_SHA256 = "3e10df5a8aec201de48437c16370d51913dfb0412d30fa393ac4710c4a4fd06a"
PIPELINE_SHA256 = "eeb9de018a74234c9b3da5cca3642dd59206cec1c356b78c2baf31bd02e32e16"
PROVIDER_SPEC_FILENAME = "provider-spec.json"
PLUGIN_DESCRIPTOR_RELATIVE_PATH = (
    "Plugins/MetaHuman/MetaHumanCharacter/MetaHumanCharacter.uplugin"
)
PRESET_RELATIVE_PATH = (
    "Plugins/MetaHuman/MetaHumanCharacter/Content/Optional/Presets/Vivian.uasset"
)
PIPELINE_RELATIVE_PATH = (
    "Plugins/MetaHuman/MetaHumanCharacter/Content/BuildPipeline/"
    "BP_DefaultLegacyPipeline_High.uasset"
)
PRESET_OBJECT_PATH = "/MetaHumanCharacter/Optional/Presets/Vivian.Vivian"
PIPELINE_OBJECT_PATH = (
    "/MetaHumanCharacter/BuildPipeline/BP_DefaultLegacyPipeline_High."
    "BP_DefaultLegacyPipeline_High_C"
)
PIPELINE_SETTINGS_CLASS_PATH = (
    "/Script/MetaHumanCharacterPalette."
    "MetaHumanCharacterPaletteProjectSettings"
)
SOURCE_OBJECT_PATH = (
    "/Game/VISTA/Characters/MetaHumans/Source/"
    "MHC_Vivian_VISTA.MHC_Vivian_VISTA"
)
SOURCE_ASSET_PATH = SOURCE_OBJECT_PATH.rsplit(".", 1)[0]
ASSEMBLY_ROOT = "/Game/VISTA/Characters/MetaHumans"
COMMON_ROOT = ASSEMBLY_ROOT + "/Common"
PROVIDER_OUTPUT_ROOT = ASSEMBLY_ROOT + "/Vivian_VISTA"
EXPECTED_BLUEPRINT = (
    PROVIDER_OUTPUT_ROOT + "/BP_Vivian_VISTA.BP_Vivian_VISTA"
)
EXPECTED_BLUEPRINT_CLASS = EXPECTED_BLUEPRINT + "_C"
EXPECTED_BLUEPRINT_ASSET_PATH = EXPECTED_BLUEPRINT.rsplit(".", 1)[0]
SHA256 = re.compile(r"^[0-9a-f]{64}$")
REQUEST_ENV = "VISTA_METAHUMAN_AUTHORING_REQUEST"
REQUEST_SHA_ENV = "VISTA_METAHUMAN_AUTHORING_REQUEST_SHA256"
RESULT_ENV = "VISTA_METAHUMAN_AUTHORING_RESULT"


def canonical_json(value):
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")


def canonical_content_json(value):
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def canonical_path(value):
    return os.path.realpath(os.path.abspath(str(value))).replace("\\", "/")


def direct_attempt_child(value, attempt_root, label):
    path = canonical_path(value)
    root = canonical_path(attempt_root)
    require(path.startswith(root + "/"), label + " escapes attempt root")
    require(os.path.dirname(path) == root, label + " must be a direct attempt child")
    return path


def content_digest(value):
    payload = dict(value)
    payload.pop("content_digest", None)
    return hashlib.sha256(canonical_json(payload)).hexdigest()


def provider_content_digest(value):
    payload = dict(value)
    payload.pop("content_digest", None)
    return hashlib.sha256(canonical_content_json(payload)).hexdigest()


def reject_json_constant(value):
    raise RuntimeError("non-finite JSON constant is prohibited: " + str(value))


def reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate JSON key is prohibited")
        result[key] = value
    return result


def load_strict_json(path, label):
    with open(path, "r", encoding="utf-8") as handle:
        value = json.load(
            handle,
            parse_constant=reject_json_constant,
            object_pairs_hook=reject_duplicate_keys,
        )
    require(type(value) is dict, label + " must be a JSON object")
    return value


def verify_provider_spec(request, attempt_root):
    require(
        request["provider_spec_content_digest"] == PROVIDER_SPEC_CONTENT_DIGEST,
        "provider spec content digest pin differs",
    )
    require(
        request["provider_spec_sha256"] == PROVIDER_SPEC_SHA256,
        "provider spec byte pin differs",
    )
    provider_path = direct_attempt_child(
        request["provider_spec_path"], attempt_root, "provider spec"
    )
    require(
        os.path.basename(provider_path) == PROVIDER_SPEC_FILENAME,
        "provider spec filename differs",
    )
    require(os.path.isfile(provider_path), "provider spec is missing")
    require(
        sha256_file(provider_path) == PROVIDER_SPEC_SHA256,
        "provider spec byte digest differs",
    )
    provider = load_strict_json(provider_path, "provider spec")
    require(
        provider.get("schema_version") == "vista.playable-character-provider/v1",
        "provider spec schema differs",
    )
    require(provider.get("provider_id") == PROVIDER_ID, "provider spec ID differs")
    require(
        provider.get("content_digest") == PROVIDER_SPEC_CONTENT_DIGEST,
        "provider spec embedded content digest differs",
    )
    require(
        provider_content_digest(provider) == PROVIDER_SPEC_CONTENT_DIGEST,
        "provider spec canonical content digest differs",
    )
    require(
        provider.get("engine", {}).get("version") == "5.7.3"
        and provider.get("engine", {}).get("changelist") == 50162420,
        "provider spec engine identity differs",
    )
    require(
        provider.get("plugin", {}).get("descriptor", {}).get("sha256")
        == PLUGIN_DESCRIPTOR_SHA256,
        "provider spec plugin pin differs",
    )
    require(
        provider.get("preset", {}).get("object_path") == PRESET_OBJECT_PATH
        and provider.get("preset", {}).get("source_file", {}).get("sha256")
        == PRESET_SHA256,
        "provider spec preset pin differs",
    )
    assembly = provider.get("assembly_contract", {})
    require(assembly.get("output_root") == PROVIDER_OUTPUT_ROOT, "provider output root differs")
    require(
        assembly.get("expected_blueprint_class_path") == EXPECTED_BLUEPRINT_CLASS,
        "provider Blueprint class differs",
    )
    require(
        assembly.get("pipeline") == "optimized"
        and assembly.get("quality") == "high"
        and assembly.get("rig_type") == "joints_and_blend_shapes",
        "provider assembly policy differs",
    )
    require(
        assembly.get("pipeline_object_path") == PIPELINE_OBJECT_PATH,
        "provider pipeline class differs",
    )
    pipeline_source = assembly.get("pipeline_source_file", {})
    require(
        pipeline_source.get("relative_path") == "Engine/" + PIPELINE_RELATIVE_PATH
        and pipeline_source.get("sha256") == PIPELINE_SHA256
        and pipeline_source.get("size_bytes") == 9550,
        "provider pipeline source pin differs",
    )
    require(
        provider.get("current_readiness", {}).get("accepted") is False,
        "source provider spec may not be pre-accepted",
    )


def verify_runtime_sources(request):
    runtime_version = str(unreal.SystemLibrary.get_engine_version())
    require(runtime_version == ENGINE_VERSION, "runtime engine version differs")
    engine_dir = canonical_path(
        unreal.Paths.convert_relative_path_to_full(unreal.Paths.engine_dir())
    )
    require(os.path.isdir(engine_dir), "runtime engine directory is missing")

    plugin_path = canonical_path(os.path.join(engine_dir, PLUGIN_DESCRIPTOR_RELATIVE_PATH))
    preset_path = canonical_path(os.path.join(engine_dir, PRESET_RELATIVE_PATH))
    pipeline_path = canonical_path(os.path.join(engine_dir, PIPELINE_RELATIVE_PATH))
    require(plugin_path.startswith(engine_dir + "/"), "plugin descriptor escapes engine")
    require(preset_path.startswith(engine_dir + "/"), "Vivian preset escapes engine")
    require(pipeline_path.startswith(engine_dir + "/"), "pipeline source escapes engine")
    require(os.path.isfile(plugin_path), "MetaHuman Character descriptor is missing")
    require(os.path.isfile(preset_path), "Vivian preset source is missing")
    require(os.path.isfile(pipeline_path), "MetaHuman Legacy High pipeline is missing")
    require(
        request["plugin_descriptor_sha256"] == PLUGIN_DESCRIPTOR_SHA256,
        "request plugin descriptor pin differs",
    )
    require(request["preset_sha256"] == PRESET_SHA256, "request preset pin differs")
    require(request["pipeline_sha256"] == PIPELINE_SHA256, "request pipeline pin differs")
    require(
        sha256_file(plugin_path) == PLUGIN_DESCRIPTOR_SHA256,
        "runtime plugin descriptor byte digest differs",
    )
    require(
        sha256_file(preset_path) == PRESET_SHA256,
        "runtime Vivian preset byte digest differs",
    )
    require(
        sha256_file(pipeline_path) == PIPELINE_SHA256,
        "runtime MetaHuman pipeline byte digest differs",
    )
    return runtime_version


def load_pinned_pipeline_class():
    pipeline_class = unreal.load_class(None, PIPELINE_OBJECT_PATH)
    require(pipeline_class is not None, "pinned MetaHuman pipeline class is unavailable")
    require(
        pipeline_class.get_name() == "BP_DefaultLegacyPipeline_High_C",
        "pinned MetaHuman pipeline class identity differs",
    )
    return pipeline_class


def verify_pinned_native_default_pipeline(pipeline_class):
    # PipelineOverride is a protected UPROPERTY in UE 5.7.3 and is deliberately
    # unavailable to Python.  The native optimized/high path instead reads this
    # effective project setting and NewObject's that class with the character as
    # outer.  Resolve the non-Python-exported settings class by fixed script path
    # and fail closed if project/user/command-line config has changed the mapping.
    settings_class = unreal.load_class(None, PIPELINE_SETTINGS_CLASS_PATH)
    require(settings_class is not None, "MetaHuman pipeline settings class is unavailable")
    settings = unreal.get_default_object(settings_class)
    require(settings is not None, "MetaHuman pipeline settings are unavailable")
    legacy_pipelines = settings.get_editor_property(
        "DefaultCharacterLegacyPipelines"
    )
    configured_pipeline = legacy_pipelines[unreal.MetaHumanQualityLevel.HIGH]
    require(configured_pipeline is not None, "MetaHuman High pipeline setting is empty")
    require(
        configured_pipeline == pipeline_class,
        "effective MetaHuman High pipeline class differs",
    )
    require(
        configured_pipeline.get_path_name() == PIPELINE_OBJECT_PATH,
        "effective MetaHuman High pipeline path differs",
    )
    return configured_pipeline


def load_request():
    request_path = canonical_path(os.environ.get(REQUEST_ENV, ""))
    expected_sha = os.environ.get(REQUEST_SHA_ENV, "")
    require(SHA256.fullmatch(expected_sha or "") is not None, "request SHA is invalid")
    require(os.path.isfile(request_path), "request file is missing")
    require(sha256_file(request_path) == expected_sha, "request SHA differs")
    request = load_strict_json(request_path, "authoring request")

    require(
        set(request)
        == {
            "schema_version",
            "provider_id",
            "provider_spec_content_digest",
            "provider_spec_path",
            "provider_spec_sha256",
            "attempt_root",
            "project_file",
            "project_sha256",
            "script_sha256",
            "engine_version",
            "plugin_descriptor_sha256",
            "preset_sha256",
            "pipeline_sha256",
            "source_object_path",
            "assembly_root",
            "common_root",
            "expected_blueprint",
            "authorization",
            "policy",
            "content_digest",
        },
        "authoring request fields differ",
    )
    require(request["schema_version"] == REQUEST_SCHEMA, "request schema differs")
    require(request["provider_id"] == PROVIDER_ID, "provider ID differs")
    require(request["engine_version"] == ENGINE_VERSION, "engine version pin differs")
    require(request["source_object_path"] == SOURCE_OBJECT_PATH, "source path differs")
    require(request["assembly_root"] == ASSEMBLY_ROOT, "assembly root differs")
    require(request["common_root"] == COMMON_ROOT, "common root differs")
    require(request["expected_blueprint"] == EXPECTED_BLUEPRINT, "blueprint path differs")
    require(
        request["authorization"]
        == {
            "cloud_requests_authorized": True,
            "interactive_epic_sign_in_allowed": True,
            "store_account_tokens_in_receipt": False,
        },
        "cloud authorization contract differs",
    )
    require(
        request["policy"]
        == {
            "append_only_project": True,
            "binary_payload_in_git": False,
            "fail_closed_without_entitlement": True,
            "private_research_only": True,
            "replace_existing": False,
        },
        "authoring policy differs",
    )
    for key in (
        "provider_spec_content_digest",
        "provider_spec_sha256",
        "project_sha256",
        "script_sha256",
        "plugin_descriptor_sha256",
        "preset_sha256",
        "pipeline_sha256",
        "content_digest",
    ):
        require(SHA256.fullmatch(str(request[key])) is not None, key + " is invalid")
    require(request["content_digest"] == content_digest(request), "request digest differs")
    require(sha256_file(__file__) == request["script_sha256"], "script pin differs")

    attempt_root = canonical_path(request["attempt_root"])
    require(os.path.isdir(attempt_root), "attempt root is missing")
    require(
        request_path == direct_attempt_child(request_path, attempt_root, "request"),
        "request location differs",
    )
    verify_provider_spec(request, attempt_root)
    verify_runtime_sources(request)
    project_file = canonical_path(request["project_file"])
    require(project_file.startswith(attempt_root + "/project/"), "project escapes attempt")
    require(
        os.path.dirname(project_file) == attempt_root + "/project",
        "project file must be a direct project child",
    )
    require(project_file.endswith(".uproject"), "project file extension differs")
    require(os.path.isfile(project_file), "project file is missing")
    require(sha256_file(project_file) == request["project_sha256"], "project pin differs")
    require(
        canonical_path(unreal.Paths.get_project_file_path()) == project_file,
        "running project differs from request",
    )
    return request, attempt_root


def write_result(result_path, result):
    sealed = dict(result)
    sealed["content_digest"] = content_digest(sealed)
    raw = canonical_json(sealed)
    descriptor = os.open(
        result_path,
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        os.close(descriptor)
    unreal.log("VISTA_METAHUMAN_AUTHORING_RESULT:" + raw.decode("utf-8").strip())


def asset_inventory():
    registry = unreal.AssetRegistryHelpers.get_asset_registry()
    assets = registry.get_assets(
        unreal.ARFilter(
            package_paths=[ASSEMBLY_ROOT],
            recursive_paths=True,
            include_only_on_disk_assets=True,
        )
    )
    return [
        {
            "object_path": str(item.get_soft_object_path()),
            "class_path": str(item.asset_class_path),
            "package_name": str(item.package_name),
        }
        for item in sorted(assets, key=lambda value: str(value.get_soft_object_path()))
    ]


def main():
    request, attempt_root = load_request()
    result_path = direct_attempt_child(os.environ.get(RESULT_ENV, ""), attempt_root, "result")
    require(not os.path.exists(result_path), "result already exists")
    character = None
    subsystem = unreal.get_editor_subsystem(unreal.MetaHumanCharacterEditorSubsystem)
    stage = "resolve_pinned_native_pipeline"
    try:
        require(subsystem is not None, "MetaHuman Character editor subsystem is unavailable")
        pipeline_class = load_pinned_pipeline_class()
        verify_pinned_native_default_pipeline(pipeline_class)
        stage = "duplicate_preset"
        preset = unreal.load_asset(PRESET_OBJECT_PATH)
        require(preset is not None, "Vivian preset is missing")
        require(
            preset.get_class().get_name() == "MetaHumanCharacter",
            "Vivian preset class differs",
        )
        require(
            not unreal.EditorAssetLibrary.does_asset_exist(SOURCE_ASSET_PATH),
            "source character already exists",
        )
        require(
            not unreal.EditorAssetLibrary.does_asset_exist(EXPECTED_BLUEPRINT_ASSET_PATH),
            "assembled provider already exists",
        )
        character = unreal.EditorAssetLibrary.duplicate_asset(
            PRESET_OBJECT_PATH, SOURCE_ASSET_PATH
        )
        require(character is not None, "failed to duplicate Vivian preset")
        require(
            character.get_class().get_name() == "MetaHumanCharacter",
            "duplicated source class differs",
        )
        require(subsystem.try_add_object_to_edit(character), "failed to edit source")

        stage = "auto_rig"
        rig_request = unreal.MetaHumanCharacterAutoRiggingRequestParams()
        rig_request.blocking = True
        rig_request.report_progress = False
        rig_request.rig_type = unreal.MetaHumanRigType.JOINTS_AND_BLEND_SHAPES
        subsystem.request_auto_rigging(character=character, params=rig_request)

        stage = "high_resolution_textures"
        texture_request = unreal.MetaHumanCharacterTextureRequestParams()
        texture_request.blocking = True
        texture_request.report_progress = False
        subsystem.request_texture_sources(character=character, params=texture_request)
        require(
            bool(character.has_high_resolution_textures),
            "high-resolution textures are unavailable",
        )
        require(
            bool(subsystem.can_build_meta_human(character=character)),
            "character is not ready for assembly",
        )

        stage = "optimized_high_assembly"
        # Recheck immediately before the native call. With PipelineOverride left
        # null, UE 5.7.3 creates a new instance of this exact effective class with
        # `character` as its outer; the protected field cannot be assigned from
        # Python without an unsafe reflection/C++ bypass.
        verify_pinned_native_default_pipeline(pipeline_class)
        build = unreal.MetaHumanCharacterEditorBuildParameters()
        build.pipeline_type = unreal.MetaHumanDefaultPipelineType.OPTIMIZED
        build.pipeline_quality = unreal.MetaHumanQualityLevel.HIGH
        build.absolute_build_path = ASSEMBLY_ROOT
        build.common_folder_path = COMMON_ROOT
        build.name_override = "Vivian_VISTA"
        build.enable_wardrobe_item_validation = True
        subsystem.build_meta_human(character=character, params=build)

        stage = "save_and_verify"
        require(
            unreal.EditorAssetLibrary.save_directory(
                ASSEMBLY_ROOT, only_if_is_dirty=False, recursive=True
            ),
            "failed to save assembled provider",
        )
        blueprint = unreal.load_asset(EXPECTED_BLUEPRINT)
        require(blueprint is not None, "expected assembled Blueprint is missing")
        require(blueprint.get_class().get_name() == "Blueprint", "assembled class differs")
        inventory = asset_inventory()
        require(len(inventory) >= 8, "assembled provider inventory is unexpectedly small")
        write_result(
            result_path,
            {
                "schema_version": RESULT_SCHEMA,
                "provider_id": PROVIDER_ID,
                "provider_spec_content_digest": request[
                    "provider_spec_content_digest"
                ],
                "accepted": False,
                "status": "assembled_candidate_requires_package_validation",
                "authoring_succeeded": True,
                "assembly_completed": True,
                "assembled_component_digests_complete": False,
                "entitlement_receipt_complete": False,
                "engine_version": ENGINE_VERSION,
                "provider_spec_sha256": PROVIDER_SPEC_SHA256,
                "plugin_descriptor_sha256": PLUGIN_DESCRIPTOR_SHA256,
                "preset_sha256": PRESET_SHA256,
                "pipeline_sha256": PIPELINE_SHA256,
                "source_object_path": SOURCE_OBJECT_PATH,
                "assembly_pipeline": "optimized",
                "assembly_quality": "high",
                "pipeline_object_path": PIPELINE_OBJECT_PATH,
                "rig_type": "joints_and_blend_shapes",
                "has_high_resolution_textures": True,
                "expected_blueprint": EXPECTED_BLUEPRINT,
                "expected_blueprint_class": EXPECTED_BLUEPRINT_CLASS,
                "asset_inventory": inventory,
                "account_tokens_recorded": False,
                "package_validation_complete": False,
                "runtime_visual_acceptance_complete": False,
            },
        )
    except Exception as exc:
        error_digest = hashlib.sha256(str(exc).encode("utf-8", "replace")).hexdigest()
        write_result(
            result_path,
            {
                "schema_version": RESULT_SCHEMA,
                "provider_id": PROVIDER_ID,
                "provider_spec_content_digest": request[
                    "provider_spec_content_digest"
                ],
                "accepted": False,
                "status": "authoring_failed",
                "authoring_succeeded": False,
                "assembly_completed": False,
                "assembled_component_digests_complete": False,
                "entitlement_receipt_complete": False,
                "failed_stage": stage,
                "error_type": type(exc).__name__,
                "error_message_sha256": error_digest,
                "account_tokens_recorded": False,
                "package_validation_complete": False,
                "runtime_visual_acceptance_complete": False,
            },
        )
        raise
    finally:
        if (
            character is not None
            and subsystem is not None
            and subsystem.is_object_added_for_editing(character)
        ):
            subsystem.remove_object_to_edit(character)


main()
