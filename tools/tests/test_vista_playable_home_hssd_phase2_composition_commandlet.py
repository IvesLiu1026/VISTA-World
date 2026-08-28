from __future__ import annotations

import ast
import copy
import pathlib
import sys
import types

import pytest


ROOT = pathlib.Path(__file__).resolve().parents[2]
COMMANDLET = (
    ROOT / "tools/ue/vista_playable_home/"
    "compose_hssd_private_research_phase2_commandlet.py"
)
COMMANDLET_ROOT = COMMANDLET.parent
sys.path.insert(0, str(COMMANDLET_ROOT))
import run_hssd_private_research_composition as runner  # noqa: E402


class FakeName(str):
    pass


class FakeReflectedClass:
    def __init__(self, path: str) -> None:
        self.path = path

    def get_path_name(self) -> str:
        return self.path


class FakeVector:
    def __init__(self, x=0.0, y=0.0, z=0.0) -> None:
        self.x = x
        self.y = y
        self.z = z


class FakeRotator:
    def __init__(self, pitch=0.0, yaw=0.0, roll=0.0) -> None:
        self.pitch = pitch
        self.yaw = yaw
        self.roll = roll


class FakeMesh:
    def __init__(self, path: str) -> None:
        self.path = path

    def get_path_name(self) -> str:
        return self.path


class FakeComponent:
    def __init__(
        self,
        path: str,
        *,
        mesh: FakeMesh | None = None,
        collision_enabled: str = "QueryAndPhysics",
        collision_profile: str = "BlockAll",
        visible: bool = True,
        navigation: bool = True,
        collision_responses: dict[str, str] | None = None,
    ) -> None:
        self.path = path
        self.properties = {
            "static_mesh": mesh,
            "generate_overlap_events": True,
            "can_ever_affect_navigation": navigation,
            "visible": visible,
            "simulate_physics": False,
            "mobility": "Movable",
        }
        self.collision_enabled = collision_enabled
        self.collision_profile = collision_profile
        default_response = "Ignore" if collision_profile == "NoCollision" else "Block"
        self.collision_responses = collision_responses or {
            "Pawn": default_response,
            "Visibility": default_response,
        }

    def get_path_name(self) -> str:
        return self.path

    def get_editor_property(self, name: str):
        if name not in self.properties:
            raise AttributeError(name)
        return self.properties[name]

    def set_editor_property(self, name: str, value) -> None:
        self.properties[name] = value

    def set_static_mesh(self, mesh: FakeMesh) -> None:
        self.properties["static_mesh"] = mesh

    def set_collision_profile_name(self, name: str) -> None:
        self.collision_profile = str(name)
        if self.collision_profile == "NoCollision":
            self.collision_enabled = "NoCollision"
            self.collision_responses = {"Pawn": "Ignore", "Visibility": "Ignore"}
        elif self.collision_profile in {"BlockAll", "BlockAllDynamic"}:
            self.collision_enabled = "QueryAndPhysics"
            self.collision_responses = {"Pawn": "Block", "Visibility": "Block"}

    def set_collision_enabled(self, value: str) -> None:
        if self.collision_enabled != value:
            self.collision_profile = "Custom"
        self.collision_enabled = value

    def get_collision_enabled(self) -> str:
        return self.collision_enabled

    def get_collision_profile_name(self) -> str:
        return self.collision_profile

    def set_collision_response_to_all_channels(self, value: str) -> None:
        if any(response != value for response in self.collision_responses.values()):
            self.collision_profile = "Custom"
        self.collision_responses = {"Pawn": value, "Visibility": value}

    def get_collision_response_to_channel(self, channel: str) -> str:
        return self.collision_responses[channel]

    def set_simulate_physics(self, value: bool) -> None:
        self.properties["simulate_physics"] = value

    def is_simulating_physics(self) -> bool:
        return self.properties["simulate_physics"]

    def set_mobility(self, value: str) -> None:
        self.properties["mobility"] = value

    def get_mobility(self) -> str:
        return self.properties["mobility"]

    def set_visibility(self, value: bool, _propagate: bool) -> None:
        self.properties["visible"] = value


class FakeActor:
    def __init__(
        self,
        path: str,
        component: FakeComponent,
        *,
        semantic_target_id: str | None = None,
    ) -> None:
        self.path = path
        self.component = component
        self.label = "Original"
        self.location = FakeVector()
        self.rotation = FakeRotator()
        self.scale = FakeVector(1, 1, 1)
        self.properties = {
            "static_mesh_component": component,
            "tags": (
                [FakeName("VistaSemanticId=" + semantic_target_id)]
                if semantic_target_id
                else []
            ),
            "hidden": False,
            "semantic_id": semantic_target_id,
            "world_revision": FakeName("vista_playable_home_r1"),
            "allowed_affordances": ["Inspect", "Toggle"],
            "initial_state_values": {"active": "false"},
            "appliance_kind": FakeName("fixture"),
            "initially_on": False,
        }
        self.collision_enabled = True

    def get_path_name(self) -> str:
        return self.path

    def get_class(self) -> FakeReflectedClass:
        return FakeReflectedClass(
            "/Script/VistaPlayableHome.VistaStatefulApplianceActor"
        )

    def get_actor_label(self) -> str:
        return self.label

    def set_actor_label(self, value: str) -> None:
        self.label = value

    def get_editor_property(self, name: str):
        if name not in self.properties:
            raise AttributeError(name)
        return self.properties[name]

    def set_editor_property(self, name: str, value) -> None:
        self.properties[name] = value

    def get_components_by_class(self, _component_class):
        return [self.component]

    def set_actor_hidden_in_game(self, value: bool) -> None:
        self.properties["hidden"] = value

    def set_actor_enable_collision(self, value: bool) -> None:
        self.collision_enabled = value

    def get_actor_enable_collision(self) -> bool:
        return self.collision_enabled

    def set_actor_scale3d(self, value: FakeVector) -> None:
        self.scale = value

    def get_actor_location(self) -> FakeVector:
        return self.location

    def get_actor_rotation(self) -> FakeRotator:
        return self.rotation

    def get_actor_scale3d(self) -> FakeVector:
        return self.scale


@pytest.fixture
def commandlet(monkeypatch: pytest.MonkeyPatch):
    unreal = types.ModuleType("unreal")
    unreal.Name = FakeName
    unreal.Vector = FakeVector
    unreal.Rotator = FakeRotator
    unreal.StaticMeshComponent = FakeComponent
    unreal.StaticMesh = FakeMesh
    unreal.CollisionEnabled = types.SimpleNamespace(
        NO_COLLISION="NoCollision",
        QUERY_ONLY="QueryOnly",
        PHYSICS_ONLY="PhysicsOnly",
        QUERY_AND_PHYSICS="QueryAndPhysics",
        PROBE_ONLY="ProbeOnly",
        QUERY_AND_PROBE="QueryAndProbe",
    )
    unreal.CollisionChannel = types.SimpleNamespace(
        PAWN="Pawn",
        VISIBILITY="Visibility",
    )
    unreal.CollisionResponseType = types.SimpleNamespace(
        IGNORE="Ignore",
        OVERLAP="Overlap",
        BLOCK="Block",
    )
    unreal.ComponentMobility = types.SimpleNamespace(STATIC="Static")
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
    module = types.ModuleType("vista_hssd_phase2_commandlet_test")
    module.__file__ = str(COMMANDLET)
    exec(compile(tree, str(COMMANDLET), "exec"), module.__dict__)
    return module


def test_visual_shell_configuration_disables_collision_navigation_and_physics(
    commandlet,
) -> None:
    placement = runner.load_pinned_contracts().placements[0]
    mesh = FakeMesh(placement["object_path"])
    component = FakeComponent("/Game/Map.Shell.Component")
    actor = FakeActor("/Game/Map.Shell", component)

    commandlet.configure_visual_shell(actor, mesh, placement)
    observation = commandlet.component_observation(component)

    assert observation["mesh_path"] == placement["object_path"]
    assert observation["collision_profile"] == "NoCollision"
    assert observation["collision_enabled"] is False
    assert observation["simulate_physics"] is False
    assert observation["generate_overlap_events"] is False
    assert observation["can_ever_affect_navigation"] is False
    assert observation["mobility"] == "Static"
    assert actor.collision_enabled is False
    assert commandlet.sorted_tags(actor) == placement["tags"]


def test_semantic_proxy_no_collision_is_repaired_to_query_authority_before_hide(
    commandlet,
) -> None:
    target = "home.r1/room.living_room/entity.sofa.01"
    component = FakeComponent(
        "/Game/Map.Proxy.Component",
        mesh=FakeMesh("/Game/Map/ProxyMesh.ProxyMesh"),
        collision_enabled="NoCollision",
        collision_profile="NoCollision",
    )
    actor = FakeActor("/Game/Map.Proxy", component, semantic_target_id=target)
    baseline = commandlet.semantic_proxy_observation(actor, target)

    commandlet.repair_semantic_proxy_query_authority_and_hide(actor)
    observed = commandlet.semantic_proxy_observation(actor, target)

    assert baseline["components"][0]["collision_mode"] == "NoCollision"
    assert baseline["components"][0]["collision_enabled"] is False
    assert observed["actor_hidden_in_game"] is True
    assert observed["components"][0]["visible"] is False
    assert observed["components"][0]["collision_profile"] == "Custom"
    assert observed["components"][0]["collision_mode"] == "QueryOnly"
    assert observed["components"][0]["collision_responses"] == {
        "Pawn": "Block",
        "Visibility": "Block",
    }
    assert observed["components"][0]["collision_enabled"] is True
    assert observed["components"][0]["can_ever_affect_navigation"] is True
    assert observed["components"][0]["simulate_physics"] is False
    assert observed["semantic_state"] == baseline["semantic_state"]
    assert commandlet._proxy_authority_repaired_and_hidden(baseline, observed) is True


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value.__setitem__("actor_label", "Changed"),
        lambda value: value.__setitem__(
            "actor_class_path", "/Script/Changed.OtherActor"
        ),
        lambda value: value.__setitem__("actor_collision_enabled", False),
        lambda value: value["world_transform_cm"]["location_cm"].__setitem__(0, 10),
        lambda value: value["semantic_state"].__setitem__("semantic_id", "changed"),
        lambda value: value["components"][0].__setitem__(
            "mesh_path", "/Game/Changed.Changed"
        ),
        lambda value: value["components"][0].__setitem__("mobility", "Static"),
        lambda value: value["components"][0].__setitem__(
            "collision_profile", "NoCollision"
        ),
        lambda value: value["components"][0].__setitem__(
            "collision_mode", "NoCollision"
        ),
        lambda value: value["components"][0].__setitem__("collision_enabled", False),
        lambda value: value["components"][0].__setitem__("simulate_physics", True),
        lambda value: value["components"][0]["collision_responses"].__setitem__(
            "Visibility", "Ignore"
        ),
    ],
    ids=[
        "label",
        "class",
        "actor-collision",
        "transform",
        "semantic-state",
        "mesh",
        "mobility",
        "no-collision-profile-regression",
        "no-collision-mode-regression",
        "collision-disabled-regression",
        "physics-regression",
        "visibility-response-regression",
    ],
)
def test_proxy_authority_repair_fails_closed_for_state_or_collision_drift(
    commandlet, mutation
) -> None:
    target = "home.r1/room.living_room/entity.sofa.01"
    component = FakeComponent(
        "/Game/Map.Proxy.Component",
        mesh=FakeMesh("/Game/Map/ProxyMesh.ProxyMesh"),
        collision_enabled="NoCollision",
        collision_profile="NoCollision",
    )
    actor = FakeActor("/Game/Map.Proxy", component, semantic_target_id=target)
    baseline = commandlet.semantic_proxy_observation(actor, target)
    commandlet.repair_semantic_proxy_query_authority_and_hide(actor)
    observed = commandlet.semantic_proxy_observation(actor, target)
    mutated = copy.deepcopy(observed)
    mutation(mutated)

    assert commandlet._proxy_authority_repaired_and_hidden(baseline, mutated) is False


def test_visual_shell_reload_requires_actor_collision_off_and_component_visible(
    commandlet,
) -> None:
    placement = runner.load_pinned_contracts().placements[0]
    mesh = FakeMesh(placement["object_path"])
    component = FakeComponent("/Game/Map.Shell.Component")
    actor = FakeActor("/Game/Map.Shell", component)
    transform = placement["world_transform_cm"]
    actor.location = FakeVector(*transform["location_cm"])
    actor.rotation = FakeRotator(
        pitch=transform["rotation_deg"][1],
        yaw=transform["rotation_deg"][2],
        roll=transform["rotation_deg"][0],
    )
    commandlet.configure_visual_shell(actor, mesh, placement)

    observation = commandlet.visual_shell_observation(actor, placement)
    assert observation["actor_collision_enabled"] is False
    assert observation["actor_hidden_in_game"] is False
    assert observation["visible"] is True

    actor.collision_enabled = True
    with pytest.raises(RuntimeError, match="reloaded HSSD visual shell differs"):
        commandlet.visual_shell_observation(actor, placement)
    actor.collision_enabled = False
    component.properties["visible"] = False
    with pytest.raises(RuntimeError, match="reloaded HSSD visual shell differs"):
        commandlet.visual_shell_observation(actor, placement)
    component.properties["visible"] = True
    actor.properties["hidden"] = True
    with pytest.raises(RuntimeError, match="reloaded HSSD visual shell differs"):
        commandlet.visual_shell_observation(actor, placement)


def test_commandlet_source_requires_exact_reload_and_keeps_honest_claims() -> None:
    source = COMMANDLET.read_text(encoding="utf-8")

    assert "load_execution_for_commandlet(__file__)" in source
    assert "len(actors_observed) == 60" in source
    assert "len(proxy_observations) == phase2.SEMANTIC_PROXY_COUNT" in source
    assert "EditorLoadingAndSavingUtils.save_map" in source
    assert '"NoCollision"' in source
    assert "SEMANTIC_PROXY_COLLISION_PROFILE" in source
    assert runner.SEMANTIC_PROXY_COLLISION_SEED_PROFILE == "BlockAllDynamic"
    assert runner.SEMANTIC_PROXY_COLLISION_PROFILE == "Custom"
    assert "CollisionEnabled.QUERY_ONLY" in source
    assert "set_collision_response_to_all_channels" in source
    assert '"after_authority_repair_and_hide"' in source
    assert '"component_query_authority_repaired": True' in source
    assert "component_collision_preserved" not in source
    assert "actor_collision_enabled(actor) is False" in source
    assert 'component_state["visible"] is True' in source
    assert '"can_ever_affect_navigation", False' in source
    assert '"gta_level": False' in source
    assert '"character_present": False' in source
    assert '"interaction_proven": False' in source
