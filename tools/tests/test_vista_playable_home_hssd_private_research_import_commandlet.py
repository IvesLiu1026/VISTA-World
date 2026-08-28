from __future__ import annotations

import ast
import hashlib
import json
import pathlib
import sys
import types

import pytest


ROOT = pathlib.Path(__file__).resolve().parents[2]
COMMANDLET = (
    ROOT / "tools/ue/vista_playable_home/import_hssd_private_research_commandlet.py"
)
COMMANDLET_ROOT = COMMANDLET.parent
sys.path.insert(0, str(COMMANDLET_ROOT))
import hssd_private_research_commandlet_common as common  # noqa: E402


NAMESPACE = common.DIAGNOSTIC_NAMESPACE
ASSET_ID = common.EXPECTED_ASSET_IDS[0]


class FakeReflectedClass:
    def __init__(self, path: str) -> None:
        self.path = path

    def get_path_name(self) -> str:
        return self.path


class FakeEditorObject:
    def __init__(self, **properties) -> None:
        self.properties = dict(properties)

    def get_editor_property(self, name: str):
        if name not in self.properties:
            raise AttributeError(name)
        return self.properties[name]

    def set_editor_property(self, name: str, value) -> None:
        self.properties[name] = value


class FakePathObject(FakeEditorObject):
    class_path = "/Script/CoreUObject.Object"

    def __init__(self, path: str, **properties) -> None:
        super().__init__(**properties)
        self.path = path

    def get_path_name(self) -> str:
        return self.path

    def get_class(self) -> FakeReflectedClass:
        return FakeReflectedClass(self.class_path)


class FakeMaterialInterface(FakePathObject):
    pass


class FakeMaterial(FakeMaterialInterface):
    class_path = "/Script/Engine.Material"

    def __init__(self, path: str, textures: list) -> None:
        super().__init__(path, texture_parameter_values=[])
        self.textures = textures

    def get_base_material(self):
        return self


class FakeTexture2D(FakePathObject):
    class_path = "/Script/Engine.Texture2D"


class FakeStaticMesh(FakePathObject):
    class_path = "/Script/Engine.StaticMesh"


@pytest.fixture
def commandlet(monkeypatch: pytest.MonkeyPatch):
    unreal = types.ModuleType("unreal")
    unreal.MaterialInterface = FakeMaterialInterface
    unreal.Material = FakeMaterial
    unreal.Texture2D = FakeTexture2D
    unreal.StaticMesh = FakeStaticMesh
    unreal.CollisionTraceFlag = types.SimpleNamespace(
        CTF_USE_SIMPLE_AS_COMPLEX="CTF_USE_SIMPLE_AS_COMPLEX"
    )
    state = types.SimpleNamespace(
        registry={},
        directories=set(),
        manager_calls=[],
        parameters=None,
        mode="valid",
        logs=[],
    )

    class ImportAssetParameters(FakeEditorObject):
        def __init__(self) -> None:
            super().__init__()
            state.parameters = self

    unreal.ImportAssetParameters = ImportAssetParameters

    class Manager:
        def import_asset(self, destination, source_data, parameters):
            state.manager_calls.append((destination, source_data, parameters))
            name = parameters.properties["destination_name"]
            texture_path = destination + "/Textures/T_Base.T_Base"
            texture = FakeTexture2D(texture_path)
            material_path = destination + "/Materials/M_PBR.M_PBR"
            if state.mode == "default_material":
                material_path = (
                    "/Engine/EngineMaterials/DefaultMaterial.DefaultMaterial"
                )
            textures = [] if state.mode == "missing_texture" else [texture]
            material = FakeMaterial(material_path, textures)
            slot = FakeEditorObject(material_interface=material)
            aggregate = FakeEditorObject(
                **{
                    property_name: [object()]
                    for property_name in common.SIMPLE_COLLISION_ELEMENT_PROPERTIES
                }
            )
            body_setup = FakeEditorObject(
                agg_geom=aggregate, collision_trace_flag="CTF_USE_DEFAULT"
            )
            nanite = FakeEditorObject(enabled=True)
            raw_path = destination + "/StaticMeshes/" + name + "." + name
            mesh = FakeStaticMesh(
                raw_path,
                static_materials=[slot],
                body_setup=body_setup,
                nanite_settings=nanite,
                has_navigation_data=True,
            )
            state.registry[raw_path] = mesh
            returned = [mesh, material]
            if state.mode != "missing_texture":
                returned.append(texture)
            if state.mode == "multiple_meshes":
                returned.append(
                    FakeStaticMesh(
                        raw_path + "_extra",
                        static_materials=[slot],
                        body_setup=body_setup,
                        nanite_settings=nanite,
                        has_navigation_data=True,
                    )
                )
            return returned

    manager = Manager()

    class InterchangeManager:
        @staticmethod
        def get_interchange_manager_scripted():
            return manager

        @staticmethod
        def create_source_data(source):
            return {"source": source}

    unreal.InterchangeManager = InterchangeManager

    class EditorAssetLibrary:
        @staticmethod
        def does_directory_exist(path):
            return path in state.directories

        @staticmethod
        def rename_asset(source, package):
            mesh = state.registry.pop(source)
            name = package.rsplit("/", 1)[-1]
            target = package + "." + name
            mesh.path = target
            state.registry[target] = mesh
            return True

        @staticmethod
        def save_loaded_asset(_asset, only_if_is_dirty=False):
            return only_if_is_dirty is False

        @staticmethod
        def make_directory(path):
            state.directories.add(path)
            return True

        @staticmethod
        def save_directory(_path, only_if_is_dirty=False, recursive=True):
            return only_if_is_dirty is False and recursive is True

    unreal.EditorAssetLibrary = EditorAssetLibrary

    class MaterialEditingLibrary:
        @staticmethod
        def get_used_textures(material):
            return material.textures

        @staticmethod
        def get_texture_parameter_names(_material):
            return []

    unreal.MaterialEditingLibrary = MaterialEditingLibrary
    unreal.load_asset = lambda path: state.registry.get(path)
    unreal.log = state.logs.append
    unreal.SystemLibrary = types.SimpleNamespace(
        get_engine_version=lambda: common.EXPECTED_ENGINE_VERSION
    )
    unreal.Paths = types.SimpleNamespace(get_project_file_path=lambda: "")
    monkeypatch.setitem(sys.modules, "unreal", unreal)

    tree = ast.parse(COMMANDLET.read_text(encoding="utf-8"), filename=str(COMMANDLET))
    final = tree.body[-1]
    assert (
        isinstance(final, ast.Expr)
        and isinstance(final.value, ast.Call)
        and isinstance(final.value.func, ast.Name)
        and final.value.func.id == "run"
    )
    tree.body.pop()
    module = types.ModuleType("vista_hssd_import_commandlet_test")
    module.__file__ = str(COMMANDLET)
    exec(compile(tree, str(COMMANDLET), "exec"), module.__dict__)
    return module, unreal, state


def _binding() -> dict:
    pin = common.EXPECTED_ASSET_PINS[ASSET_ID]
    return {
        "source": {
            "source_asset_id": ASSET_ID,
            "semantic_category": "accent_chair",
            "glb_relative_path": f"assets/{ASSET_ID}.glb",
            "glb_sha256": pin["glb_sha256"],
            "glb_bytes": pin["glb_bytes"],
            "receipt_relative_path": f"receipts/{ASSET_ID}.json",
            "receipt_sha256": pin["receipt_sha256"],
            "receipt_content_digest": pin["receipt_content_digest"],
            "material_count": 1,
            "pbr_material_count": 1,
            "texture_count": 1,
            "pbr_texture_slot_count": 1,
            "base_normal_orm_texture_slot_count": 1,
            "target_object_path": common.derived_hssd_asset_path(NAMESPACE, ASSET_ID),
        },
        "derivative": {
            "source_asset_id": ASSET_ID,
            "glb_path": "/tmp/derivative.glb",
            "glb_sha256": "a" * 64,
            "glb_bytes": 64,
            "receipt_path": "/tmp/derivative.json",
            "receipt_sha256": "b" * 64,
            "receipt_content_digest": "c" * 64,
            "compatibility_status": "derived_ue57_compatible_candidate",
            "blocks_full_material_fidelity": False,
        },
    }


def test_interchange_import_validates_pbr_dependencies_and_disables_mesh_authority(
    commandlet, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module, _unreal, state = commandlet
    source = tmp_path / "pinned.glb"
    source.write_bytes(b"pinned")
    monkeypatch.setattr(module, "verify_binding_source", lambda *_args: str(source))

    result = module.import_one({}, _binding(), NAMESPACE)

    expected = common.derived_hssd_asset_path(NAMESPACE, ASSET_ID)
    assert result["object_path"] == expected
    assert result["inspection"]["class_path"] == "/Script/Engine.StaticMesh"
    assert result["inspection"]["material_paths"] == [
        NAMESPACE + "/Imports/hssd_static_accent_chair/Materials/M_PBR.M_PBR"
    ]
    assert result["inspection"]["returned_texture2d_paths"] == [
        NAMESPACE + "/Imports/hssd_static_accent_chair/Textures/T_Base.T_Base"
    ]
    assert result["inspection"]["simple_collision_shapes"] == 0
    assert result["inspection"]["has_navigation_data"] is False
    assert result["inspection"]["nanite_enabled"] is False
    assert "SIMPLE_AS_COMPLEX" in result["inspection"]["collision_trace_flag"]
    assert state.parameters.properties == {
        "is_automated": True,
        "follow_redirectors": False,
        "destination_name": "hssd_static_accent_chair",
        "replace_existing": False,
        "force_show_dialog": False,
    }


@pytest.mark.parametrize(
    ("mode", "message"),
    [
        ("default_material", "shared/default/basic material"),
        ("missing_texture", "Texture2D count"),
        ("multiple_meshes", "exactly one StaticMesh"),
    ],
)
def test_interchange_dependency_or_primary_mesh_failure_is_fail_closed(
    commandlet,
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    message: str,
) -> None:
    module, _unreal, state = commandlet
    source = tmp_path / "pinned.glb"
    source.write_bytes(b"pinned")
    monkeypatch.setattr(module, "verify_binding_source", lambda *_args: str(source))
    state.mode = mode

    with pytest.raises(RuntimeError, match=message):
        module.import_one({}, _binding(), NAMESPACE)


def test_terminal_receipt_records_exact_26_and_visual_only_gates(
    commandlet,
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module, unreal, state = commandlet
    attempt = tmp_path / "candidate-attempt"
    attempt.mkdir()
    receipt_path = attempt / "hssd-import-receipt.json"
    project = attempt / "Candidate.uproject"
    project.write_bytes(b"{}\n")
    execution = {
        "attempt_root": str(attempt),
        "project_file": str(project),
        "project_sha256": hashlib.sha256(project.read_bytes()).hexdigest(),
        "content_namespace": NAMESPACE,
        "source_run": {"path": str(tmp_path / "source")},
        "import_mode": common.DIAGNOSTIC_IMPORT_MODE,
        "compatibility": {
            "aggregate_receipt_sha256": "d" * 64,
            "aggregate_receipt_content_digest": "e" * 64,
            "promotable": False,
            "full_material_fidelity": False,
            "diagnostic_only": True,
        },
        "import_receipt": str(receipt_path),
    }
    bindings = []
    for asset_id in common.EXPECTED_ASSET_IDS:
        binding = _binding()
        binding["source"]["source_asset_id"] = asset_id
        binding["derivative"]["source_asset_id"] = asset_id
        bindings.append(binding)

    safety = {
        "simple_collision_shapes": 0,
        "collision_trace_flag": "CTF_USE_SIMPLE_AS_COMPLEX",
        "collision_trace_policy": module.NO_COLLISION_TRACE_POLICY,
        "component_collision_profile": "NoCollision",
        "has_navigation_data": False,
        "can_ever_affect_navigation_for_components": False,
        "nanite_policy": module.NANITE_POLICY,
        "nanite_enabled": False,
    }

    def fake_import(_execution, binding, _namespace):
        asset_id = binding["source"]["source_asset_id"]
        object_path = NAMESPACE + "/Assets/" + asset_id
        state.registry[object_path] = FakeStaticMesh(object_path)
        return {
            "source_asset_id": asset_id,
            "object_path": object_path,
            "inspection": {
                "static_mesh_count": 1,
                "material_paths": ["/Game/Private/M"],
                "returned_texture2d_paths": ["/Game/Private/T"],
                "material_texture2d_paths": ["/Game/Private/T"],
                **safety,
            },
        }

    monkeypatch.setattr(
        module,
        "load_hssd_execution",
        lambda *_args: (execution, str(attempt / "execution.json"), "a" * 64, bindings),
    )
    monkeypatch.setattr(
        module,
        "verify_runtime",
        lambda _execution: (common.EXPECTED_ENGINE_VERSION, str(project), NAMESPACE),
    )
    monkeypatch.setattr(module, "import_one", fake_import)
    monkeypatch.setattr(module, "_verify_mesh_safety", lambda _mesh: dict(safety))
    unreal.load_asset = lambda path: state.registry.get(path)

    module.run()

    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["schema_version"] == common.IMPORT_RECEIPT_SCHEMA
    assert receipt["status"] == common.DIAGNOSTIC_IMPORT_STATUS
    assert receipt["accepted_as_visual_evidence"] is False
    assert receipt["full_material_fidelity"] is False
    assert receipt["promotable"] is False
    assert receipt["diagnostic_only"] is True
    assert receipt["promotion_status"] == common.PROMOTION_STATUS
    assert receipt["interaction_authority"] == "none_static_joined_glb"
    assert len(receipt["assets"]) == 26
    assert receipt["gates"] == {
        "exact_r7_source_inventory_verified": True,
        "compatibility_derivatives_revalidated": True,
        "diagnostic_nonpromotable_disposition_recorded": True,
        "namespace_fresh": True,
        "namespace_created": True,
        "exact_26_assets_imported": True,
        "one_static_mesh_per_source": True,
        "pbr_material_interfaces_verified": True,
        "texture2d_imported_and_bound": True,
        "simple_collision_absent": True,
        "complex_collision_disabled": True,
        "asset_navigation_disabled": True,
        "component_instantiation_deferred_to_phase2": True,
        "nanite_disabled": True,
        "quarantined": False,
    }
    result_path = attempt / common.IMPORT_RESULT_FILE
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert result["status"] == common.DIAGNOSTIC_IMPORT_STATUS
    assert result["receipt"] == str(receipt_path)
    assert len(result["sha256"]) == 64
    assert state.logs[-1].startswith(common.IMPORT_MARKER)


def test_failure_after_namespace_creation_is_never_reported_clean(
    commandlet,
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module, _unreal, _state = commandlet
    attempt = tmp_path / "candidate-attempt"
    attempt.mkdir()
    project = attempt / "Candidate.uproject"
    project.write_bytes(b"{}\n")
    receipt_path = attempt / "hssd-import-receipt.json"
    execution = {
        "attempt_root": str(attempt),
        "project_file": str(project),
        "project_sha256": hashlib.sha256(project.read_bytes()).hexdigest(),
        "content_namespace": NAMESPACE,
        "source_run": {"path": str(tmp_path / "source")},
        "import_mode": common.DIAGNOSTIC_IMPORT_MODE,
        "compatibility": {
            "aggregate_receipt_sha256": "d" * 64,
            "aggregate_receipt_content_digest": "e" * 64,
            "promotable": False,
            "full_material_fidelity": False,
            "diagnostic_only": True,
        },
        "import_receipt": str(receipt_path),
    }
    monkeypatch.setattr(
        module,
        "load_hssd_execution",
        lambda *_args: (
            execution,
            str(attempt / "execution.json"),
            "a" * 64,
            [_binding()],
        ),
    )
    monkeypatch.setattr(
        module,
        "verify_runtime",
        lambda _execution: (common.EXPECTED_ENGINE_VERSION, str(project), NAMESPACE),
    )
    monkeypatch.setattr(
        module,
        "import_one",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("interchange failed")),
    )

    with pytest.raises(RuntimeError, match="fresh namespace quarantined"):
        module.run()

    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["status"] == "partial_import_quarantined"
    assert receipt["gates"]["namespace_created"] is True
    assert receipt["gates"]["quarantined"] is True
    assert receipt["gates"]["component_instantiation_deferred_to_phase2"] is False


def test_commandlet_source_is_commandlet_safe_and_has_terminal_handshake() -> None:
    source = COMMANDLET.read_text(encoding="utf-8")
    tree = ast.parse(source)
    final = tree.body[-1]

    assert isinstance(final, ast.Expr)
    assert isinstance(final.value, ast.Call)
    assert isinstance(final.value.func, ast.Name)
    assert final.value.func.id == "run"
    assert "InterchangeManager.get_interchange_manager_scripted" in source
    assert "InterchangeManager.create_source_data" in source
    assert 'parameters.set_editor_property("replace_existing", False)' in source
    assert "clear_simple_collision(mesh)" in source
    assert "CTF_USE_SIMPLE_AS_COMPLEX" in source
    assert 'mesh.set_editor_property("has_navigation_data", False)' in source
    assert "returned_texture2d_paths" in source
    assert "returned_material_interface_paths" in source
    assert "set(returned_texture2d_paths).issubset" in source
    assert "set(material_texture2d_paths)" in source
    assert "write_exclusive_receipt" in source
    assert "IMPORT_RESULT_FILE" in source
    assert "engine == EXPECTED_ENGINE_VERSION" in source
    assert "if namespace_created" in source
    assert ".remove_collisions" not in source
    assert "remove_collisions(" not in source
