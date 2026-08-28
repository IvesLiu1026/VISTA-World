from __future__ import annotations

import ast
import os
import pathlib
import sys
import types

import pytest

from tools.ue.vista_playable_home import ycb_handheld_kit_commandlet_common as common


ROOT = pathlib.Path(__file__).resolve().parents[2]
COMMANDLET = ROOT / "tools/ue/vista_playable_home/import_ycb_handheld_kit_commandlet.py"


def _pure_commandlet(monkeypatch: pytest.MonkeyPatch):
    unreal = types.ModuleType("unreal")

    class Editable:
        def __init__(self, **values):
            self.values = dict(values)

        def set_editor_property(self, name, value):
            self.values[name] = value

        def get_editor_property(self, name):
            if name not in self.values:
                raise AttributeError(name)
            return self.values[name]

    class Pipeline(Editable):
        def __init__(self):
            super().__init__(
                mesh_pipeline=Editable(
                    import_static_meshes=False,
                    combine_static_meshes=True,
                    collision=False,
                    import_collision_according_to_mesh_name=False,
                    one_convex_hull_per_ucx=False,
                    fallback_collision_type="BOX",
                    force_collision_primitive_generation=True,
                    build_nanite=True,
                ),
                material_pipeline=Editable(
                    import_materials=False,
                    material_import="IMPORT_AS_MATERIAL_INSTANCES",
                    search_location="LOCAL",
                    texture_pipeline=Editable(import_textures=False),
                ),
            )

        def get_path_name(self):
            return "/Engine/Transient.YcbPipeline"

    class SoftObjectPath:
        def __init__(self, path):
            self.path = path

    unreal.InterchangeGenericAssetsPipeline = Pipeline
    unreal.InterchangeMeshCollision = types.SimpleNamespace(NONE="NONE")
    unreal.InterchangeMaterialImportOption = types.SimpleNamespace(
        IMPORT_AS_MATERIALS="IMPORT_AS_MATERIALS"
    )
    unreal.InterchangeMaterialSearchLocation = types.SimpleNamespace(
        DO_NOT_SEARCH="DO_NOT_SEARCH"
    )
    unreal.SoftObjectPath = SoftObjectPath
    unreal.StaticMesh = type("StaticMesh", (), {})
    unreal.Texture2D = type("Texture2D", (), {})
    unreal.MaterialInterface = type("MaterialInterface", (), {})
    unreal.Material = type("Material", (unreal.MaterialInterface,), {})
    unreal.MaterialExpressionTextureBase = type("MaterialExpressionTextureBase", (), {})
    unreal.MaterialProperty = types.SimpleNamespace(MP_BASE_COLOR="MP_BASE_COLOR")
    monkeypatch.setitem(sys.modules, "unreal", unreal)
    monkeypatch.setitem(sys.modules, "ycb_handheld_kit_commandlet_common", common)
    tree = ast.parse(COMMANDLET.read_text(encoding="utf-8"), filename=str(COMMANDLET))
    final = tree.body[-1]
    assert (
        isinstance(final, ast.Expr)
        and isinstance(final.value, ast.Call)
        and isinstance(final.value.func, ast.Name)
        and final.value.func.id == "run"
    )
    tree.body.pop()
    module = types.ModuleType("ycb_import_commandlet_test")
    module.__file__ = str(COMMANDLET)
    exec(compile(tree, str(COMMANDLET), "exec"), module.__dict__)  # noqa: S102
    return module, unreal


def test_fixed_r3_blender_source_revalidates_exact_18_and_182() -> None:
    source, bindings = common.validate_blender_source(
        common.BLENDER_ROOT,
        host_receipt_sha256=common.BLENDER_HOST_RECEIPT_SHA256,
        host_receipt_content_digest=common.BLENDER_HOST_RECEIPT_CONTENT_DIGEST,
    )

    assert source == {
        "root": common.BLENDER_ROOT,
        "host_receipt": common.BLENDER_ROOT + "/ycb-blender-host-receipt.json",
        "host_receipt_sha256": common.BLENDER_HOST_RECEIPT_SHA256,
        "host_receipt_content_digest": common.BLENDER_HOST_RECEIPT_CONTENT_DIGEST,
        "build_plan_content_digest": common.BLENDER_BUILD_PLAN_CONTENT_DIGEST,
        "worker_request_content_digest": (common.BLENDER_WORKER_REQUEST_CONTENT_DIGEST),
        "worker_result_sha256": common.BLENDER_WORKER_RESULT_SHA256,
        "worker_result_path": (common.BLENDER_ROOT + "/ycb-blender-worker-result.json"),
        "asset_count": 18,
        "total_convex_hulls": 182,
    }
    assert [item["asset_id"] for item in bindings] == list(common.EXPECTED_ASSET_IDS)
    assert sum(item["expected_convex_count"] for item in bindings) == 182
    assert all(
        item["target_object_path"].startswith(common.CONTENT_NAMESPACE + "/")
        for item in bindings
    )


def test_dry_run_is_explicitly_zero_write_and_keeps_claims_honest() -> None:
    before = os.stat(common.BLENDER_ROOT).st_mtime_ns
    report = common.dry_run_report()
    after = os.stat(common.BLENDER_ROOT).st_mtime_ns

    assert before == after
    assert report["mode"] == "dry_run_zero_writes"
    assert report["will_write"] is False
    assert report["will_run_unreal"] is False
    assert report["accepted"] is False
    assert report["claims"] == {
        "blender_source_validated": True,
        "ue_imported": False,
        "ucx_collision_verified_in_ue": False,
        "full_pbr_verified": False,
        "gameplay_interaction_verified": False,
        "gta_level_quality": False,
    }
    assert report["content_digest"] == common.content_digest(report)


@pytest.mark.parametrize("suffix", ["r1", "r2"])
def test_quarantined_legacy_attempts_are_rejected_before_receipt_trust(
    suffix: str,
) -> None:
    root = common.BLENDER_ROOT.replace("r3", suffix)
    with pytest.raises(RuntimeError, match="fixed successful r3"):
        common.validate_blender_source(
            root,
            host_receipt_sha256=common.BLENDER_HOST_RECEIPT_SHA256,
            host_receipt_content_digest=common.BLENDER_HOST_RECEIPT_CONTENT_DIGEST,
        )


def test_wrong_r3_host_pin_is_rejected() -> None:
    with pytest.raises(RuntimeError, match="exact successful r3 receipt"):
        common.validate_blender_source(
            common.BLENDER_ROOT,
            host_receipt_sha256="0" * 64,
            host_receipt_content_digest=common.BLENDER_HOST_RECEIPT_CONTENT_DIGEST,
        )


def test_atomic_terminal_receipt_recovers_post_link_interrupt(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    attempt = tmp_path / "attempt"
    attempt.mkdir(mode=0o700)
    final = attempt / common.IMPORT_RECEIPT_NAME
    original_fsync = os.fsync
    calls = 0

    def interrupt_directory_fsync(descriptor: int) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise KeyboardInterrupt
        original_fsync(descriptor)

    monkeypatch.setattr(os, "fsync", interrupt_directory_fsync)
    receipt = {"schema_version": "test/v1", "status": "success"}

    digest = common.write_atomic_terminal_receipt(final, attempt, receipt)

    provisional = attempt / "ycb-import-receipt.provisional"
    assert digest == common.hashlib.sha256(common.canonical_json(receipt)).hexdigest()
    assert (
        final.read_bytes() == provisional.read_bytes() == common.canonical_json(receipt)
    )
    assert final.stat().st_ino == provisional.stat().st_ino
    assert final.stat().st_nlink == 2


def test_atomic_terminal_receipt_never_publishes_final_on_link_failure(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    attempt = tmp_path / "attempt"
    attempt.mkdir(mode=0o700)
    final = attempt / common.IMPORT_RECEIPT_NAME

    def reject_link(*_args, **_kwargs):
        raise OSError("injected link failure")

    monkeypatch.setattr(os, "link", reject_link)
    with pytest.raises(OSError, match="injected"):
        common.write_atomic_terminal_receipt(final, attempt, {"status": "failed"})

    assert not final.exists()
    assert (attempt / "ycb-import-receipt.provisional").is_file()


def test_interchange_pipeline_is_exact_ucx_no_fallback_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module, _unreal = _pure_commandlet(monkeypatch)

    pipeline, path, observed = module.configure_interchange_pipeline("SM_YCB_APPLE")

    assert pipeline.get_editor_property("asset_name") == "SM_YCB_APPLE"
    assert path.path == "/Engine/Transient.YcbPipeline"
    assert observed == common.INTERCHANGE_COLLISION_POLICY
    assert observed["fallback_collision_type"] == "NONE"
    assert observed["one_convex_hull_per_ucx"] is True
    assert observed["build_nanite"] is False
    assert observed["import_materials"] is True
    assert observed["material_import"] == "IMPORT_AS_MATERIALS"
    assert observed["material_search_location"] == "DO_NOT_SEARCH"
    assert observed["import_textures"] is True


def _material_fixture(unreal, source: str):
    class Reflected:
        def __init__(self, path: str):
            self.path = path

        def get_path_name(self):
            return self.path

    class ImportData:
        def __init__(self, filenames):
            self.filenames = filenames

        def extract_filenames(self):
            return list(self.filenames)

        def get_class(self):
            return Reflected("/Script/InterchangeEngine.InterchangeAssetImportData")

    class Texture(unreal.Texture2D):
        def __init__(self, path, filenames):
            self.path = path
            self.import_data = ImportData(filenames)

        def get_path_name(self):
            return self.path

        def get_class(self):
            return Reflected("/Script/Engine.Texture2D")

        def blueprint_get_size_x(self):
            return 4096

        def blueprint_get_size_y(self):
            return 4096

        def get_editor_property(self, name):
            if name == "asset_import_data":
                return self.import_data
            raise AttributeError(name)

    class Expression:
        def __init__(self, path, class_path, inputs=None):
            self.path = path
            self.class_path = class_path
            self.inputs = list(inputs or [])

        def get_path_name(self):
            return self.path

        def get_class(self):
            return Reflected(self.class_path)

    class TextureExpression(unreal.MaterialExpressionTextureBase):
        def __init__(self, path, texture):
            self.path = path
            self.texture = texture
            self.inputs = [None, None]

        def get_path_name(self):
            return self.path

        def get_class(self):
            return Reflected("/Script/Engine.MaterialExpressionTextureSample")

        def get_editor_property(self, name):
            if name == "texture":
                return self.texture
            raise AttributeError(name)

    class Material(unreal.Material):
        def __init__(self, path, texture, root):
            self.path = path
            self.textures = [texture]
            self.root = root

        def get_path_name(self):
            return self.path

        def get_class(self):
            return Reflected("/Script/Engine.Material")

    class Slot:
        def __init__(self, material):
            self.material = material

        def get_editor_property(self, name):
            if name == "material_interface":
                return self.material
            raise AttributeError(name)

    class Mesh:
        def __init__(self, material):
            self.slots = [Slot(material)]

        def get_editor_property(self, name):
            if name == "static_materials":
                return self.slots
            raise AttributeError(name)

    private = "/Game/VISTA/PlayableHome/ycb_handheld_kit_r1/YCB/Imports/SM_TEST"
    texture = Texture(private + "/Textures/texture_map.texture_map", [source])
    material_path = private + "/Materials/material_0.material_0"
    texture_expression = TextureExpression(
        material_path + ":MaterialExpressionTextureSample_0", texture
    )
    root = Expression(
        material_path + ":MaterialExpressionMultiply_0",
        "/Script/Engine.MaterialExpressionMultiply",
        [texture_expression, None],
    )
    material = Material(material_path, texture, root)
    mesh = Mesh(material)
    unreal.MaterialEditingLibrary = types.SimpleNamespace(
        get_used_textures=lambda value: value.textures,
        get_material_property_input_node=lambda value, _property: value.root,
        get_material_property_input_node_output_name=lambda _value, _property: "RGB",
        get_inputs_for_material_expression=lambda _material, value: value.inputs,
    )
    objects = {texture.get_path_name(): texture, material.get_path_name(): material}
    saves = []
    unreal.EditorAssetLibrary = types.SimpleNamespace(
        save_loaded_asset=lambda value, only_if_is_dirty=False: (
            saves.append((value.get_path_name(), only_if_is_dirty)) or True
        )
    )
    unreal.load_asset = objects.get
    binding = {
        "source_embedded_png": {
            "width": 4096,
            "height": 4096,
            "sha256": "a" * 64,
            "size_bytes": 123,
        }
    }
    return mesh, material, texture, texture_expression, private, binding, saves


def test_private_material_texture_is_saved_reloaded_and_source_bound(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module, unreal = _pure_commandlet(monkeypatch)
    source = str(tmp_path / "sealed.glb")
    mesh, material, texture, texture_expression, private, binding, saves = (
        _material_fixture(unreal, source)
    )
    material.textures = []  # NullRHI compiled cache can be empty before compilation.

    evidence = module._save_private_dependencies(mesh, source, binding, private)
    inspection = module._material_inspection(
        mesh, [mesh], private, source, binding, evidence
    )

    assert saves == [
        (texture.get_path_name(), False),
        (material.get_path_name(), False),
    ]
    assert inspection["returned_texture2d_paths"] == []
    assert inspection["material_texture2d_paths"] == [texture.get_path_name()]
    assert (
        inspection["texture_binding_authority"]
        == "ue5_7_material_editing_library_mp_base_color_expression_graph"
    )
    assert inspection["base_color_texture_expression_paths"] == [
        texture_expression.get_path_name()
    ]
    assert inspection["compiled_used_texture2d_paths"] == []
    assert inspection["base_color_null_default_input_count"] == 3
    assert inspection["source_texture_import_filenames"] == [source]
    assert inspection["source_texture_width"] == 4096
    assert inspection["source_texture_height"] == 4096
    assert inspection["persisted_dependency_paths"] == sorted(
        [material.get_path_name(), texture.get_path_name()]
    )
    assert inspection["dependencies_reloaded"] is True


def test_private_texture_rejects_wrong_source_glb(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module, unreal = _pure_commandlet(monkeypatch)
    source = str(tmp_path / "sealed.glb")
    mesh, _material, texture, _expression, private, binding, _saves = _material_fixture(
        unreal, source
    )
    texture.import_data.filenames = [str(tmp_path / "other.glb")]

    with pytest.raises(RuntimeError, match="exact source GLB"):
        module._save_private_dependencies(mesh, source, binding, private)


def test_private_texture_rejects_unbound_or_default_dependency(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module, unreal = _pure_commandlet(monkeypatch)
    source = str(tmp_path / "sealed.glb")
    mesh, material, texture, expression, private, binding, _saves = _material_fixture(
        unreal, source
    )
    expression.texture = None
    with pytest.raises(RuntimeError, match="has no Texture2D"):
        module._save_private_dependencies(mesh, source, binding, private)

    expression.texture = texture
    material.path = "/Engine/BasicShapes/BasicShapeMaterial.BasicShapeMaterial"
    with pytest.raises(RuntimeError, match="shared/default/basic"):
        module._save_private_dependencies(mesh, source, binding, private)


def _imported_item(asset_id: str, convex_count: int) -> dict:
    return {
        "asset_id": asset_id,
        "inspection": {
            "static_mesh_count": 1,
            "expected_convex_count": convex_count,
            "convex_collision_count": convex_count,
            "total_simple_collision_shapes": convex_count,
            "collision_import_policy": common.INTERCHANGE_COLLISION_POLICY,
            "returned_texture2d_paths": [],
            "material_texture2d_paths": ["/Game/Private/T_Test.T_Test"],
            "source_texture2d_path": "/Game/Private/T_Test.T_Test",
            "source_texture_width": 4096,
            "source_texture_height": 4096,
            "material_saved": True,
            "source_texture_saved": True,
            "dependencies_reloaded": True,
            "nanite_enabled": False,
            "has_navigation_data": False,
        },
    }


def test_success_gates_require_all_18_assets_and_exact_182_hulls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module, _unreal = _pure_commandlet(monkeypatch)
    imported = [
        _imported_item(asset_id, common.EXPECTED_CONVEX_COUNTS[asset_id])
        for asset_id in common.EXPECTED_ASSET_IDS
    ]

    gates = module._success_gates(imported, True)

    assert gates["exact_18_assets_imported_in_order"] is True
    assert gates["exact_182_ucx_convex_hulls_verified"] is True
    assert gates["fallback_basic_geometry_absent"] is True
    assert gates["gameplay_authoring_deferred"] is True
    assert gates["quarantined"] is False

    imported[0]["inspection"]["convex_collision_count"] = 2
    assert (
        module._success_gates(imported, True)["exact_182_ucx_convex_hulls_verified"]
        is False
    )


def test_receipt_contract_carries_camera_project_provenance_without_gta_claim() -> None:
    assert common.PROJECT_PROVENANCE == {
        "source_camera_attempt": common.SOURCE_CAMERA_ATTEMPT,
        "source_camera_host_receipt_sha256": (common.SOURCE_CAMERA_HOST_RECEIPT_SHA256),
        "source_camera_project_projection": (common.SOURCE_CAMERA_PROJECT_PROJECTION),
        "source_map_relative_path": common.SOURCE_MAP_RELATIVE_PATH,
        "source_map_sha256": common.SOURCE_MAP_SHA256,
        "source_map_bytes": common.SOURCE_MAP_BYTES,
        "project_descriptor_sha256": common.PROJECT_DESCRIPTOR_SHA256,
        "project_descriptor_bytes": common.PROJECT_DESCRIPTOR_BYTES,
    }
    assert common.CLAIMS["gta_level_quality"] is False
    assert common.CLAIMS["gameplay_interaction_verified"] is False
    assert common.CLAIMS["full_pbr_verified"] is False
