from __future__ import annotations

import hashlib
import json
import struct
from types import SimpleNamespace

import pytest

from tools.blender.vista_playable_home_realism import build as blender_build
from tools.blender.vista_playable_home_realism.build import (
    PROJECT_METRIC_UV_LAYER,
    PROJECT_METRIC_UV_MAPPING,
    PROJECT_METRIC_UV_METERS_PER_TILE,
    _apply_project_metric_box_uv,
    _metric_box_uv,
)
from tools.blender.vista_playable_home_realism.config import content_digest
from tools.blender.vista_playable_home_realism.export import (
    build_quality_claims,
    project_architecture_uv_contract,
)
from tools.blender.vista_playable_home_realism.materials import (
    _height_field_python,
    _save_image,
    _texture_pixels,
    _texture_pixels_from_height_python,
    material_by_id,
    material_plan_manifest,
)


class _UVLayers(list):
    active = None

    def __init__(self, loop_count: int) -> None:
        super().__init__([SimpleNamespace(name="UVMap")])
        self.loop_count = loop_count

    def new(self, *, name: str):
        layer = SimpleNamespace(
            name=name,
            data=[SimpleNamespace(uv=None) for _ in range(self.loop_count)],
            active_render=False,
        )
        self.append(layer)
        return layer


def test_project_metric_box_uv_uses_one_metre_tiles_and_binds_receipt() -> None:
    # A 2 m x 3 m top and a 3 m x 0.5 m side prove that UV distances
    # follow baked object-local metre dimensions rather than primitive UVs.
    coordinates = [
        (-1.0, -1.5, 0.25),
        (1.0, -1.5, 0.25),
        (1.0, 1.5, 0.25),
        (-1.0, 1.5, 0.25),
        (1.0, -1.5, -0.25),
        (1.0, 1.5, -0.25),
        (1.0, 1.5, 0.25),
        (1.0, -1.5, 0.25),
    ]
    uv_layers = _UVLayers(loop_count=len(coordinates))
    mesh = SimpleNamespace(
        uv_layers=uv_layers,
        polygons=[
            SimpleNamespace(normal=(0.0, 0.0, 1.0), loop_indices=(0, 1, 2, 3)),
            SimpleNamespace(normal=(1.0, 0.0, 0.0), loop_indices=(4, 5, 6, 7)),
        ],
        loops=[SimpleNamespace(vertex_index=index) for index in range(len(coordinates))],
        vertices=[SimpleNamespace(co=value) for value in coordinates],
        update=lambda: None,
    )

    class _Object(dict):
        data = mesh

    obj = _Object()
    _apply_project_metric_box_uv(obj, component_id="component.fixture")

    top = [item.uv for item in uv_layers[0].data[:4]]
    side = [item.uv for item in uv_layers[0].data[4:]]
    assert abs(top[1][0] - top[0][0]) == pytest.approx(2.0)
    assert abs(top[2][1] - top[1][1]) == pytest.approx(3.0)
    assert abs(side[1][0] - side[0][0]) == pytest.approx(3.0)
    assert abs(side[2][1] - side[1][1]) == pytest.approx(0.5)
    assert uv_layers[0].name == PROJECT_METRIC_UV_LAYER
    assert uv_layers[0].active_render is True
    assert obj["vista_uv_mapping"] == PROJECT_METRIC_UV_MAPPING
    assert obj["vista_uv_meters_per_tile"] == PROJECT_METRIC_UV_METERS_PER_TILE
    receipt = json.loads(obj["vista_uv_receipt_json"])
    assert receipt == {
        "component_id": "component.fixture",
        "coordinate_space": "object_local_metres_after_scale_apply",
        "mapping": "metric_box_v1",
        "meters_per_tile": 1.0,
        "schema_version": "simworld.vista.project-architecture-metric-uv/v1",
        "uv_layer": "VISTA_MetricUV",
    }
    assert obj["vista_uv_receipt_sha256"] == content_digest(receipt)


def test_metric_box_uv_axis_ties_are_deterministic() -> None:
    assert _metric_box_uv((2.0, 3.0, 0.5), (1.0, 1.0, 0.0)) == (-3.0, 0.5)
    assert _metric_box_uv((2.0, 3.0, 0.5), (0.0, 0.0, 1.0)) == (2.0, 3.0)
    with pytest.raises(RuntimeError, match="invalid"):
        _metric_box_uv((0.0, 0.0, 0.0), (0.0, 0.0, 0.0))


def test_every_project_component_creation_applies_metric_uv(monkeypatch) -> None:
    class _Object(dict):
        def __init__(self) -> None:
            super().__init__()
            self.users_collection = []
            self.data = SimpleNamespace(name="", materials=[])
            self.matrix_parent_inverse = SimpleNamespace(identity=lambda: None)

    obj = _Object()
    collection = SimpleNamespace(objects=SimpleNamespace(link=lambda _obj: None))
    bpy = SimpleNamespace(
        context=SimpleNamespace(
            active_object=obj,
            view_layer=SimpleNamespace(objects=SimpleNamespace(active=None)),
        ),
        ops=SimpleNamespace(
            mesh=SimpleNamespace(primitive_cube_add=lambda **_kwargs: None),
            object=SimpleNamespace(transform_apply=lambda **_kwargs: None),
        ),
    )
    applied: list[str] = []
    monkeypatch.setattr(blender_build, "_apply_edge_softening", lambda *_args: None)
    monkeypatch.setattr(
        blender_build,
        "_apply_project_metric_box_uv",
        lambda _obj, *, component_id: applied.append(component_id),
    )
    component = SimpleNamespace(
        component_id="component.fixture",
        room_id="room.fixture",
        room_kind="living_room",
        role="floor_finish",
        export_role="presentation",
        material_id="r2.oak_natural",
        collision_policy="presentation_no_collision",
        semantic_policy="presentation_only",
        source_opening_id=None,
        location_m=(0.0, 0.0, 0.0),
        rotation_deg=(0.0, 0.0, 0.0),
        dimensions_m=(2.0, 3.0, 0.5),
        preview_visible=True,
    )
    assert blender_build._component_object(
        bpy,
        component,
        object(),
        object(),
        collection,
    ) is obj
    assert applied == ["component.fixture"]


def test_2k_is_the_only_production_quality_and_cli_default() -> None:
    for size in (64, 512, 1024):
        claims = build_quality_claims(size)
        assert claims["quality_class"] == "smoke_only"
        assert claims["eligible_as_architecture_source_evidence"] is False
        assert claims["production_minimum_texture_size_px"] == 2048
    assert build_quality_claims(2048)["quality_class"] == "production_candidate"
    args = blender_build.parse_blender_args(
        [
            "--house",
            "/tmp/house.json",
            "--visual-profile",
            "/tmp/profile.json",
            "--output-root",
            "/tmp/output",
        ]
    )
    assert args.texture_size_px == 2048


def test_normalized_manifest_uv_receipt_contract_is_closed_and_metric() -> None:
    assert project_architecture_uv_contract() == {
        "schema_version": "simworld.vista.project-architecture-metric-uv/v1",
        "mapping": "metric_box_v1",
        "uv_layer": "VISTA_MetricUV",
        "meters_per_tile": 1.0,
        "coordinate_space": "object_local_metres_after_scale_apply",
        "exported_custom_properties": [
            "vista_uv_layer",
            "vista_uv_mapping",
            "vista_uv_meters_per_tile",
            "vista_uv_receipt_json",
            "vista_uv_receipt_sha256",
        ],
    }


def test_material_receipt_reports_actual_and_minimum_metric_texel_density() -> None:
    production = material_plan_manifest(2048)
    smoke = material_plan_manifest(64)
    assert {item["texel_density_px_per_m"] for item in production} == {2048}
    assert {item["texel_density_px_per_m"] for item in smoke} == {64}
    assert {
        item["design_minimum_texel_density_px_per_m"] for item in production
    } == {1024}


def test_shared_python_height_field_preserves_legacy_small_smoke_pixels() -> None:
    spec = material_by_id()["r2.oak_natural"]
    heights = _height_field_python(spec, 8)
    expected_digests = {
        "base_color": "9f6ad85064b61deac8552c4a4d5f46007bbc91252e8df3fd0342140d8c26f21c",
        "normal": "ac036ffca6096efe88242344ec2014c60559849bccf3bbc052704c5aeba3ff5d",
        "roughness": "55613dabcd3fa1fa4edd04a11e55450d4edee37dfa396ceb40a9916864f1f6b1",
    }
    for semantic, expected_digest in expected_digests.items():
        shared = _texture_pixels_from_height_python(spec, semantic, 8, heights)
        assert shared == _texture_pixels(spec, semantic, 8)
        encoded = struct.pack(f"!{len(shared)}d", *shared)
        assert hashlib.sha256(encoded).hexdigest() == expected_digest


def test_save_image_forwards_buffer_without_list_duplication(tmp_path) -> None:
    class _Buffer:
        def __iter__(self):
            raise AssertionError("_save_image must not materialize list(pixels)")

    source_buffer = _Buffer()

    class _PixelSink:
        received = None

        def foreach_set(self, value):
            self.received = value

    class _Image:
        def __init__(self) -> None:
            self.colorspace_settings = SimpleNamespace(name=None)
            self.pixels = _PixelSink()
            self.filepath_raw = ""
            self.file_format = ""

        def update(self) -> None:
            pass

        def save(self) -> None:
            from pathlib import Path

            Path(self.filepath_raw).write_bytes(b"png")

    image = _Image()
    bpy = SimpleNamespace(
        data=SimpleNamespace(
            images=SimpleNamespace(new=lambda **_kwargs: image),
        )
    )
    path = tmp_path / "texture.png"
    assert _save_image(
        bpy,
        path,
        "fixture",
        source_buffer,
        64,
        color_space="Non-Color",
    ) is image
    assert image.pixels.received is source_buffer
