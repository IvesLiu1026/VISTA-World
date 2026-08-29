from __future__ import annotations

import ast
import copy
import dataclasses
import hashlib
import json
import os
import pathlib
import types

import pytest

from tools.runtime.vista_playable_home import human_visual_demo_launch as launcher
from tools.ue.vista_playable_home import materialize_citysample_human_demo as demo
from tools.ue.vista_playable_home import materialize_hybrid_camera_overlay as tree_io


ROOT = pathlib.Path(__file__).resolve().parents[2]
COMMANDLET = (
    ROOT / "tools/ue/vista_playable_home/compose_citysample_human_demo_commandlet.py"
)


def _mkdir(path: pathlib.Path, mode: int = 0o700) -> None:
    path.mkdir(parents=True, exist_ok=True)
    os.chmod(path, mode)


def _write(path: pathlib.Path, raw: bytes, mode: int = 0o600) -> None:
    _mkdir(path.parent)
    path.write_bytes(raw)
    os.chmod(path, mode)


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
            and node.value.func.id == "run"
        ):
            continue
        body.append(node)
    tree.body = body
    ast.fix_missing_locations(tree)
    module = types.ModuleType("citysample_human_demo_commandlet_test")
    module.__dict__["unreal"] = types.SimpleNamespace()
    exec(compile(tree, str(COMMANDLET), "exec"), module.__dict__)  # noqa: S102
    return module


def _repo_descriptor() -> bytes:
    return (
        json.dumps(
            {
                "FileVersion": 3,
                "Version": 1,
                "Installed": False,
                "Modules": [{"Name": "VistaPlayableHome", "Type": "Runtime"}],
                "Plugins": [{"Name": "EnhancedInput", "Enabled": True}],
            },
            indent=2,
        )
        + "\n"
    ).encode()


def _package_descriptor() -> bytes:
    value = json.loads(_repo_descriptor())
    value["Installed"] = True
    value.update(
        {
            "CreatedByURL": "",
            "DocsURL": "",
            "MarketplaceURL": "",
            "SupportURL": "",
            "EngineVersion": "5.7.0",
        }
    )
    return json.dumps(value, separators=(",", ":")).encode()


def _plugin_pair(root: pathlib.Path) -> tuple[pathlib.Path, pathlib.Path]:
    repository = root / "repo/unreal_plugins/VistaPlayableHome"
    package = root / "plugins/vista-playable-home-plugin-human-demo-fixture"
    _write(repository / "VistaPlayableHome.uplugin", _repo_descriptor())
    _write(package / "VistaPlayableHome.uplugin", _package_descriptor())
    for index in range(53):
        relative = pathlib.Path("Source/VistaPlayableHome") / f"File{index:02}.cpp"
        raw = f"source-{index}\n".encode()
        _write(repository / relative, raw)
        _write(package / relative, raw)
    return repository, package


def _observation(binding: dict[str, object], index: int) -> dict[str, object]:
    return {
        "semantic_id": binding["semantic_id"],
        "actor_path": f"/Game/Fixture/Pickup_{index}",
        "actor_class_path": "/Script/VistaPlayableHome.VistaPickupActor",
        "actor_hidden_in_game": False,
        "root_component_path": f"/Game/Fixture/Pickup_{index}.PickupMesh",
        "root_visible": False,
        "presentation_component_path": (
            f"/Game/Fixture/Pickup_{index}.PresentationMesh"
        ),
        "presentation_visible": True,
        "mesh_object_path": binding["mesh_object_path"],
        "relative_transform": copy.deepcopy(binding["relative_transform"]),
        "collision_mode": "NoCollision",
        "simulate_physics": False,
        "generate_overlap_events": False,
        "can_ever_affect_navigation": False,
    }


def _result(request: dict[str, object], attempt: pathlib.Path) -> dict[str, object]:
    observations = [
        _observation(binding, index)
        for index, binding in enumerate(copy.deepcopy(list(demo.PRESENTATIONS)))
    ]
    gates = {
        "exact_city_blueprint_loaded": True,
        "exact_generated_class_loaded": True,
        "exact_character_cdo_loaded": True,
        "fixed_map_loaded": True,
        "exact_three_pickups_found": True,
        "exact_three_presentation_meshes_loaded": True,
        "configure_presentation_mesh_succeeded": True,
        "pickup_actors_unhidden": True,
        "pickup_root_meshes_hidden": True,
        "presentation_collision_disabled": True,
        "presentation_physics_disabled": True,
        "presentation_navigation_disabled": True,
        "only_exact_duplicate_hssd_pot_destroyed": True,
        "all_other_actor_identities_preserved": True,
        "map_saved": True,
        "map_cold_reloaded": True,
        "cold_reloaded_map_artifact_sealed": True,
        "exact_three_presentations_reloaded": True,
        "pickup_actor_paths_stable_after_reload": True,
        "duplicate_absent_after_reload": True,
    }
    map_path = attempt / "project" / pathlib.Path(demo.MAP_RELATIVE_PATH)
    _write(map_path, b"cold-reloaded-map\n")
    stable_inventory = [
        {
            "actor_path": row["actor_path"],
            "actor_class_path": row["actor_class_path"],
            "tags": ["VistaSemanticId=" + row["semantic_id"]],
        }
        for row in observations
    ]
    duplicate = {
        "actor_path": "/Game/Fixture/HSSD_Pot",
        "actor_class_path": "/Script/Engine.StaticMeshActor",
        "tags": sorted(
            [
                demo.DUPLICATE_HSSD_TAG,
                "VistaRole=hssd_curated_overlay",
            ]
        ),
    }
    actor_inventory_before = sorted(
        [*stable_inventory, duplicate], key=lambda row: row["actor_path"]
    )
    actor_inventory_reloaded = sorted(
        stable_inventory, key=lambda row: row["actor_path"]
    )
    return demo._seal(
        {
            "schema_version": demo.RESULT_SCHEMA,
            "status": demo.RESULT_STATUS,
            "provider_id": demo.PROVIDER_ID,
            "human_operated_visual_demo_only": True,
            "prohibited_agent_adapter": True,
            "request_sha256": hashlib.sha256(demo._canonical_json(request)).hexdigest(),
            "map_object_path": demo.MAP_OBJECT_PATH,
            "map_package": demo._artifact(map_path),
            "city_character": request["city_character"],
            "presentations": request["presentations"],
            "observations_before_save": copy.deepcopy(observations),
            "observations_reloaded": copy.deepcopy(observations),
            "actor_inventory_before": actor_inventory_before,
            "actor_inventory_reloaded": actor_inventory_reloaded,
            "duplicate_hssd_actor_tag_destroyed": demo.DUPLICATE_HSSD_TAG,
            "destroyed_actor_path": "/Game/Fixture/HSSD_Pot",
            "legal_scope": copy.deepcopy(demo.LEGAL_SCOPE),
            "claims": copy.deepcopy(demo.CLAIMS),
            "gates": gates,
            "error": None,
        }
    )


def _write_result(attempt: pathlib.Path, result: dict[str, object]) -> None:
    _mkdir(attempt)
    raw = demo._canonical_json(result)
    digest = hashlib.sha256(raw).hexdigest()
    _write(attempt / demo.RESULT_NAME, raw)
    _write(
        attempt / (demo.RESULT_NAME + ".sha256"),
        f"{digest}  {demo.RESULT_NAME}\n".encode("ascii"),
    )


def _request_for_result() -> dict[str, object]:
    return {
        "city_character": {
            "blueprint_object_path": demo.CITY_BLUEPRINT_OBJECT,
            "generated_class_path": demo.CITY_GENERATED_CLASS,
            "default_object_path": demo.CITY_DEFAULT_OBJECT,
        },
        "presentations": copy.deepcopy(list(demo.PRESENTATIONS)),
    }


def _commandlet_request(module: types.ModuleType) -> dict[str, object]:
    repository_contract = {
        "VistaPlayableHome.uplugin": {"sha256": "1" * 64, "size_bytes": 1},
        "Source/A.cpp": {"sha256": "2" * 64, "size_bytes": 2},
        "Source/B.cpp": {"sha256": "3" * 64, "size_bytes": 3},
    }
    return {
        "schema_version": module.REQUEST_SCHEMA,
        "engine_version": module.ENGINE_VERSION,
        "provider_id": module.PROVIDER_ID,
        "human_operated_visual_demo_only": True,
        "prohibited_agent_adapter": True,
        "map_object_path": module.MAP_OBJECT_PATH,
        "map_relative_path": module.MAP_RELATIVE_PATH,
        "city_character": {
            "blueprint_object_path": module.CITY_BLUEPRINT_OBJECT,
            "generated_class_path": module.CITY_GENERATED_CLASS,
            "default_object_path": module.CITY_DEFAULT_OBJECT,
        },
        "presentations": copy.deepcopy(module.PRESENTATIONS),
        "duplicate_hssd_actor_tag_to_destroy": module.DUPLICATE_HSSD_TAG,
        "source_pins": {
            "hssd_host_receipt_sha256": module.HSSD_HOST_RECEIPT_SHA256,
            "hssd_project_sha256": module.HSSD_PROJECT_SHA256,
            "hssd_scene_receipt_sha256": module.HSSD_SCENE_RECEIPT_SHA256,
            "city_host_receipt_sha256": module.CITY_HOST_RECEIPT_SHA256,
            "city_result_sha256": module.CITY_RESULT_SHA256,
            "citysample_crowd_sha256": module.CITY_CONTENT_SHA256,
            "plugin_package_sha256": "4" * 64,
            "plugin_source_git_commit": module.PLUGIN_SOURCE_GIT_COMMIT,
            "repository_plugin_contract": repository_contract,
        },
        "legal_scope": copy.deepcopy(module.LEGAL_SCOPE),
        "acknowledgements": copy.deepcopy(module.ACKNOWLEDGEMENTS),
        "claims": copy.deepcopy(module.CLAIMS),
    }


def test_combined_receipt_contract_matches_launcher_v2() -> None:
    assert demo.COMBINED_RECEIPT_SCHEMA == launcher.COMBINED_RECEIPT_SCHEMA
    assert demo.COMBINED_RECEIPT_STATUS == launcher.COMBINED_RECEIPT_STATUS
    assert demo.COMBINED_RECEIPT_NAME == launcher.COMBINED_RECEIPT_NAME
    assert demo.LEGAL_SCOPE == launcher.LEGAL_SCOPE
    assert demo.CLAIMS == launcher.CLAIMS
    assert demo.PROVIDER_ID == launcher.PROVIDER_ID
    assert demo.PLUGIN_SOURCE_GIT_COMMIT == "dadb00a278218a1b402908c72b9d1c8967770035"


def test_apply_fails_before_io_when_any_legal_acknowledgement_is_missing() -> None:
    acknowledgements = dict(demo.ACKNOWLEDGEMENTS)
    acknowledgements["hssd_attribution"] = None
    with pytest.raises(demo.DemoMaterializerError, match="every exact legal"):
        demo.build_plan(
            pathlib.Path("/does/not/matter"),
            pathlib.Path("/does/not/matter"),
            "0" * 64,
            apply=True,
            acknowledgements=acknowledgements,
        )


def test_attempt_reuse_and_non_direct_path_fail_closed(tmp_path: pathlib.Path) -> None:
    run_parent = tmp_path / "runs"
    repository = tmp_path / "repo"
    _mkdir(run_parent)
    _mkdir(repository)
    config = dataclasses.replace(
        demo.production_config(), run_parent=run_parent, repository_root=repository
    )
    reused = run_parent / "citysample-human-demo-reused"
    _mkdir(reused)
    with pytest.raises(demo.DemoMaterializerError, match="already exists"):
        demo._validate_attempt(config, reused)
    nested = run_parent / "nested/citysample-human-demo-new"
    with pytest.raises(demo.DemoMaterializerError, match="direct"):
        demo._validate_attempt(config, nested)


def test_cli_exposes_no_token_provider_source_or_ue_redirect() -> None:
    with pytest.raises(SystemExit):
        demo.parse_args(
            [
                "--attempt-root",
                "/tmp/citysample-human-demo-x",
                "--plugin-package-root",
                "/tmp/vista-playable-home-plugin-human-demo-x",
                "--plugin-package-tree-sha256",
                "0" * 64,
                "--access-token",
                "random-token",
            ]
        )
    options = {
        action.dest
        for action in demo.parse_args.__globals__["argparse"].ArgumentParser()._actions
    }
    assert "token" not in options


def test_commandlet_environment_is_closed_and_strips_every_sensitive_family(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sensitive = {
        "OPENAI_API_KEY": "openai-secret",
        "ANTHROPIC_API_KEY": "anthropic-secret",
        "POSTGRES_URL": "postgres-secret",
        "DATABASE_URL": "database-secret",
        "HTTP_PROXY": "proxy-secret",
        "HTTPS_PROXY": "proxy-secret",
        "ALL_PROXY": "proxy-secret",
        "NO_PROXY": "proxy-secret",
        "OPENROUTER_MODEL": "model-secret",
        "VISTA_PORT": "55620",
        "STUDIO_ACCESS_TOKEN": "studio-secret",
        "DISPLAY": ":117",
        "SSH_AUTH_SOCK": "/tmp/secret-agent.sock",
        "PYTHONPATH": "/secret/python/path",
        "LD_LIBRARY_PATH": "/secret/library/path",
    }
    for key, value in sensitive.items():
        monkeypatch.setenv(key, value)
    attempt = tmp_path / "attempt"
    _mkdir(attempt)
    request = attempt / demo.REQUEST_NAME
    environment = demo._environment(attempt, request, "a" * 64)
    assert set(environment) == {
        "LANG",
        "LC_ALL",
        "PATH",
        "HOME",
        "TMPDIR",
        "XDG_CACHE_HOME",
        "XDG_CONFIG_HOME",
        "XDG_DATA_HOME",
        "CUDA_VISIBLE_DEVICES",
        "NVIDIA_VISIBLE_DEVICES",
        "VULKAN_DEVICE_INDEX",
        "SDL_VIDEODRIVER",
        demo.REQUEST_ENV,
        demo.REQUEST_SHA_ENV,
        demo.RESULT_ENV,
        demo.RESULT_SHA_ENV,
    }
    assert environment["LANG"] == environment["LC_ALL"] == "C.UTF-8"
    assert environment["PATH"] == demo.TRUSTED_PATH
    assert environment["CUDA_VISIBLE_DEVICES"] == "0"
    assert environment["NVIDIA_VISIBLE_DEVICES"] == "0"
    assert environment["SDL_VIDEODRIVER"] == "offscreen"
    assert not set(sensitive).intersection(environment)
    assert not set(sensitive.values()).intersection(environment.values())
    for key in (
        "HOME",
        "TMPDIR",
        "XDG_CACHE_HOME",
        "XDG_CONFIG_HOME",
        "XDG_DATA_HOME",
    ):
        path = pathlib.Path(environment[key])
        assert path.is_relative_to(attempt)
        assert path.is_dir()
        assert os.stat(path, follow_symlinks=False).st_mode & 0o777 == 0o700


class _InterruptingProcess:
    pid = 424242

    def __init__(self, mode: str) -> None:
        self.mode = mode
        self.wait_calls = 0

    def poll(self):
        return None

    def wait(self, timeout):
        self.wait_calls += 1
        if self.wait_calls == 1:
            if self.mode == "keyboard":
                raise KeyboardInterrupt
            demo.signal.raise_signal(demo.signal.SIGTERM)
        return -demo.signal.SIGTERM


@pytest.mark.parametrize(
    ("mode", "exception"),
    [
        ("keyboard", KeyboardInterrupt),
        ("sigterm", demo.DemoMaterializerError),
    ],
)
def test_run_unreal_cleans_process_group_and_restores_handlers_on_interrupt(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    exception: type[BaseException],
) -> None:
    attempt = tmp_path / mode
    _mkdir(attempt)
    process = _InterruptingProcess(mode)
    killed: list[tuple[int, int]] = []
    monkeypatch.setattr(demo.subprocess, "Popen", lambda *_args, **_kwargs: process)
    monkeypatch.setattr(
        demo.os, "killpg", lambda pid, signum: killed.append((pid, signum))
    )
    prepared = types.SimpleNamespace(
        attempt_root=attempt,
        config=types.SimpleNamespace(
            unreal_editor_cmd=pathlib.Path("/fixed/UnrealEditor-Cmd")
        ),
    )
    previous = {
        signum: demo.signal.getsignal(signum)
        for signum in (demo.signal.SIGINT, demo.signal.SIGTERM)
    }
    with pytest.raises(exception):
        demo._run_unreal(
            prepared,
            attempt / demo.REQUEST_NAME,
            "b" * 64,
            attempt / demo.COMMANDLET_NAME,
        )
    assert killed == [(process.pid, demo.signal.SIGTERM)]
    assert {
        signum: demo.signal.getsignal(signum)
        for signum in (demo.signal.SIGINT, demo.signal.SIGTERM)
    } == previous


def test_terminate_escalates_stubborn_process_group_to_sigkill(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class StubbornProcess:
        pid = 515151

        @staticmethod
        def poll():
            return None

        @staticmethod
        def wait(timeout):
            raise demo.subprocess.TimeoutExpired("UnrealEditor-Cmd", timeout)

    killed: list[tuple[int, int]] = []
    monkeypatch.setattr(
        demo.os, "killpg", lambda pid, signum: killed.append((pid, signum))
    )
    demo._terminate(StubbornProcess())
    assert killed == [
        (StubbornProcess.pid, demo.signal.SIGTERM),
        (StubbornProcess.pid, demo.signal.SIGKILL),
    ]


def test_buildplugin_descriptor_allows_only_fixed_semantic_normalization(
    tmp_path: pathlib.Path,
) -> None:
    repository, package = _plugin_pair(tmp_path)
    evidence = demo._validate_buildplugin_descriptor(repository, package)
    assert evidence["equivalence"] == (
        "strict_buildplugin_semantic_equivalence_not_literal_bytes"
    )
    value = json.loads((package / "VistaPlayableHome.uplugin").read_text())
    value["EngineVersion"] = "5.8.0"
    _write(
        package / "VistaPlayableHome.uplugin",
        json.dumps(value).encode(),
    )
    with pytest.raises(demo.DemoMaterializerError, match="semantic normalization"):
        demo._validate_buildplugin_descriptor(repository, package)


def test_plugin_source_inventory_mismatch_fails_closed(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository, package = _plugin_pair(tmp_path)
    config = dataclasses.replace(
        demo.production_config(),
        repository_root=tmp_path / "repo",
        repository_plugin=repository,
    )
    monkeypatch.setattr(demo, "_validate_git_contract", lambda *_args: None)
    snapshot = tree_io.snapshot_tree(package, "plugin fixture")
    contract, descriptor = demo._validate_plugin_contract(config, snapshot)
    assert len([key for key in contract if key.startswith("Source/")]) == 53
    assert descriptor["allowed_normalization"]["EngineVersion"] == "5.7.0"
    _write(package / "Source/VistaPlayableHome/File07.cpp", b"mutated\n")
    mutated = tree_io.snapshot_tree(package, "mutated plugin fixture")
    with pytest.raises(demo.DemoMaterializerError, match="Source bytes"):
        demo._validate_plugin_contract(config, mutated)


def test_fixed_presentations_and_duplicate_identity_are_exact() -> None:
    assert [row["semantic_id"] for row in demo.PRESENTATIONS] == [
        "home.r1/room.bedroom/entity.phone.01",
        "home.r1/room.kitchen_dining/entity.coffee_cup.01",
        "home.r1/room.kitchen_dining/entity.pot.01",
    ]
    assert [
        row["relative_transform"]["location_cm"][2] for row in demo.PRESENTATIONS
    ] == [
        -6.0,
        -1.0106,
        4.25,
    ]
    assert demo.PRESENTATIONS[0]["relative_transform"]["rotation_deg"][2] == 10.0
    assert demo.DUPLICATE_HSSD_TAG == (
        "VistaHssdInstanceId=hssd.r1/kitchen_dining.pot.01"
    )


def test_commandlet_has_configure_save_destroy_and_cold_reload_proof() -> None:
    source = COMMANDLET.read_text(encoding="utf-8")
    assert "actor.configure_presentation_mesh(" in source
    assert 'component.get_editor_property("relative_location")' in source
    assert 'component.get_editor_property("relative_rotation")' in source
    assert 'component.get_editor_property("relative_scale3d")' in source
    assert "component.get_relative_location()" not in source
    assert "component.get_relative_rotation()" not in source
    assert "component.get_relative_scale3d()" not in source
    assert "actor_subsystem.destroy_actor(duplicate)" in source
    assert "EditorLoadingAndSavingUtils.save_map" in source
    assert source.count("level_subsystem.load_level(MAP_OBJECT_PATH)") >= 2
    assert 'gates["map_cold_reloaded"] = True' in source
    assert 'gates["duplicate_absent_after_reload"]' in source


def test_commandlet_rejects_random_token_and_non_strict_legal_boolean() -> None:
    module = _pure_commandlet()
    request = _commandlet_request(module)
    module.validate_request_contract(request)
    random_token = dict(request)
    random_token["studio_access_token"] = "random-token"
    with pytest.raises(module.CommandletFailure, match="key inventory"):
        if set(random_token) != module.REQUEST_KEYS:
            module.require(False, "request key inventory differs")
    wrong_boolean = copy.deepcopy(request)
    wrong_boolean["legal_scope"]["private_noncommercial_research_only"] = 1
    with pytest.raises(module.CommandletFailure, match="legal booleans"):
        module.validate_request_contract(wrong_boolean)


@pytest.mark.parametrize(
    "mutation",
    ["actor", "mesh", "transform", "root_visible", "collision", "physics", "nav"],
)
def test_result_observation_rejects_wrong_actor_mesh_transform_or_policy(
    mutation: str,
) -> None:
    expected = copy.deepcopy(demo.PRESENTATIONS[0])
    value = _observation(expected, 0)
    if mutation == "actor":
        value["actor_class_path"] = "/Script/Engine.StaticMeshActor"
    elif mutation == "mesh":
        value["mesh_object_path"] = "/Game/Wrong/Wrong.Wrong"
    elif mutation == "transform":
        value["relative_transform"]["location_cm"][2] += 1.0
    elif mutation == "root_visible":
        value["root_visible"] = True
    elif mutation == "collision":
        value["collision_mode"] = "QueryAndPhysics"
    elif mutation == "physics":
        value["simulate_physics"] = True
    else:
        value["can_ever_affect_navigation"] = True
    assert not demo._result_observation_valid(value, expected)


@pytest.mark.parametrize(
    "mutation",
    [
        "cold_reload",
        "false_claim",
        "wrong_mesh",
        "wrong_transform",
        "map_pin",
        "other_actor_removed",
        "pickup_path",
        "error",
    ],
)
def test_host_terminal_validation_rejects_false_or_incomplete_result(
    tmp_path: pathlib.Path, mutation: str
) -> None:
    request = _request_for_result()
    attempt = tmp_path / mutation
    result = _result(request, attempt)
    if mutation == "cold_reload":
        result["gates"]["map_cold_reloaded"] = False
    elif mutation == "false_claim":
        result["claims"]["gta_level_quality"] = True
    elif mutation == "wrong_mesh":
        result["observations_reloaded"][0]["mesh_object_path"] = "/Game/Wrong.Wrong"
    elif mutation == "wrong_transform":
        result["observations_reloaded"][1]["relative_transform"]["location_cm"][2] = 9
    elif mutation == "map_pin":
        result["map_package"]["sha256"] = "0" * 64
    elif mutation == "other_actor_removed":
        result["actor_inventory_reloaded"].pop()
    elif mutation == "pickup_path":
        result["observations_reloaded"][0]["actor_path"] += "_changed"
    else:
        result["error"] = {"type": "Failure", "message": "not successful"}
    result = demo._seal(result)
    _write_result(attempt, result)
    with pytest.raises(demo.DemoMaterializerError, match="failed closed"):
        demo._validate_result(attempt, request)


def test_host_terminal_validation_accepts_only_exact_closed_result(
    tmp_path: pathlib.Path,
) -> None:
    request = _request_for_result()
    attempt = tmp_path / "accepted"
    result = _result(request, attempt)
    _write_result(attempt, result)
    assert demo._validate_result(attempt, request) == result


def test_launcher_static_tree_algorithm_matches_exact_record_definition(
    tmp_path: pathlib.Path,
) -> None:
    project = tmp_path / "project"
    _mkdir(project)
    descriptor = project / demo.PROJECT_NAME
    _write(descriptor, b"project\n")
    _write(project / "Config/DefaultEngine.ini", b"engine\n")
    _write(project / "Content/Map.umap", b"map\n")
    _write(project / "Plugins/P/P.uplugin", b"plugin\n")
    _write(project / "Saved/ignored.bin", b"mutable\n")
    observed = launcher.compute_project_static_tree(descriptor)
    records = []
    relative_paths = sorted(
        (
            demo.PROJECT_NAME,
            "Config/DefaultEngine.ini",
            "Content/Map.umap",
            "Plugins/P/P.uplugin",
        ),
        key=lambda value: value.encode("utf-8"),
    )
    for relative in relative_paths:
        path = project / relative
        raw = path.read_bytes()
        records.append(
            relative.encode()
            + b"\0"
            + b"0600"
            + b"\0"
            + str(len(raw)).encode()
            + b"\0"
            + hashlib.sha256(raw).hexdigest().encode()
            + b"\n"
        )
    assert observed == {
        "algorithm": "sha256-path-nul-mode-size-content-v1",
        "file_count": 4,
        "total_bytes": sum(
            len((project / relative).read_bytes()) for relative in relative_paths
        ),
        "tree_sha256": hashlib.sha256(b"".join(records)).hexdigest(),
    }


def test_published_v2_receipt_is_consumed_by_launcher_without_adapter(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    attempt = tmp_path / "attempt"
    project = attempt / "project"
    _mkdir(project)
    descriptor = project / demo.PROJECT_NAME
    _write(descriptor, demo._project_document_raw())
    _write(project / pathlib.Path(demo.MAP_RELATIVE_PATH), b"sealed-map\n")
    _write(project / "Config/DefaultEngine.ini", b"[fixture]\n")
    _write(project / "Plugins/VistaPlayableHome/VistaPlayableHome.uplugin", b"{}\n")
    prepared = types.SimpleNamespace(
        attempt_root=attempt,
        plugin_sha256=(
            "a5662c78f0a607484ef0232912bbfa041d96b3ec88cc59f46a8fcc105d4d04f2"
        ),
        config=demo.production_config(),
    )
    state = {
        "project": demo._artifact(descriptor),
        "project_static_tree": launcher.compute_project_static_tree(descriptor),
        "source_provenance": demo._source_provenance(prepared),
        "executable": demo._artifact_pinned(
            prepared.config.unreal_editor,
            prepared.config.unreal_editor_sha256,
            demo.UNREAL_EDITOR_BYTES,
            "fixture UnrealEditor",
        ),
        "map_package": demo._artifact(project / pathlib.Path(demo.MAP_RELATIVE_PATH)),
        "terminal_result_sha256": "1" * 64,
        "copied_commandlet": {
            "path": str(attempt / demo.COMMANDLET_NAME),
            "sha256": "2" * 64,
            "size_bytes": 2,
        },
        "request_sha256": "3" * 64,
    }
    monkeypatch.setattr(demo, "_publication_state", lambda *_args: state)
    receipt = demo._publish_combined_receipt(
        prepared,
        {},
        attempt / demo.REQUEST_NAME,
        attempt / demo.COMMANDLET_NAME,
    )
    assert set(receipt) == launcher.RECEIPT_KEYS
    assert receipt["schema_version"] == launcher.COMBINED_RECEIPT_SCHEMA
    assert receipt["prohibited_agent_adapter"] is True
    loaded = launcher.load_combined_receipt(attempt / launcher.COMBINED_RECEIPT_NAME)
    assert loaded.project.path == descriptor
    assert loaded.source_provenance["plugin_source_git_commit"] == (
        demo.PLUGIN_SOURCE_GIT_COMMIT
    )
