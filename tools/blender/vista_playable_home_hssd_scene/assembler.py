"""Validate one fixed HSSD R5 run and assemble its living room externally.

The default operation is a read-only dry run.  Only :func:`execute_assembly`
creates an append-only external attempt and invokes the pinned Blender 4.5.8
worker.  HSSD payloads remain private, external, static presentation shells.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import pathlib
import re
import stat
import subprocess
import sys
from typing import Any, Mapping, Sequence

from tools.blender.vista_playable_home_hssd import HssdBindingError, inspect_glb
from tools.blender.vista_playable_home_realism.config import ForgeInputError
from tools.blender.vista_playable_home_realism.external_assets import (
    AcquiredAsset,
    asset_digest_record,
    load_external_asset_set,
)


DEFAULT_SOURCE_RUN = pathlib.Path(
    "/data/sysx/vista-world/runs/vista-action-world-r1/"
    "hssd-private-research-r5-20260828t040000z"
)
DEFAULT_BLENDER = pathlib.Path("/home/yhliu/.local/opt/blender-4.5.8-linux-x64/blender")
DEFAULT_POLY_HAVEN_ROOT = pathlib.Path(
    "/mnt/NAS2/yhliu/SimWorldStudio/vista-playable-home-realism/runs/"
    "20260816T073747Z/external-assets/attempt-01-poly-haven-cc0"
)
EXPECTED_BLENDER_SHA256 = (
    "86b39e16cf8043a93de6b4ac5e23399d790f662c644573f600398a3c3bd121eb"
)
EXPECTED_DOCUMENT_SHA256 = {
    "build-plan.json": "88b645fc81936b2eefe7e2d572d7b6e4959aede2d20b3277096753edeba78c1e",
    "build-result.json": "f9cdeff719e6faf0850d1fb0184406a5a49c9a772cb8889022c1f465cc3150be",
    "scene-plan.json": "bcf8d1cc63fd6529a7277020ba6712b88de7dc04e0f7448df98e24e0c54238fc",
}
EXPECTED_CONTENT_DIGESTS = {
    "build-plan.json": "b06e0fb2cc92231f3ddc674a9adf99c7684204978e3ba303239484335cb33de7",
    "build-result.json": "6b75a0c83191873b5e62e465d266f340d37aa24befda1e5e291686137d1685c7",
    "scene-plan.json": "c02223bf7d113264455d83f5426cbb3efca171f087a654492af01d7c619cae0f",
}
ASSEMBLY_PLAN_SCHEMA = "simworld.vista.hssd-living-scene-plan/v1"
ASSEMBLY_RECEIPT_SCHEMA = "simworld.vista.hssd-living-scene-receipt/v1"
ROOM_ID = "home.r1/room.living_room"
ROOM_BOUNDS_M = {"min_m": [-2.5, -2.0, 0.0], "max_m": [2.5, 2.0, 3.0]}
RENDER_RELATIVE_PATH = "render/living_room_player_eye.png"
BLEND_RELATIVE_PATH = "scene/hssd_living_room_research.blend"
_SHA256 = re.compile(r"[0-9a-f]{64}")
_POLY_HAVEN_RECEIPT_REFERENCE = {
    "provider": "poly_haven",
    "receipt_schema_version": "simworld.vista.playable-home-poly-haven-receipt/v1",
    "receipt_digest": "a8a6b03c8fae71b299a2fcb36764e2dc1ec32c1e4dcd0b30ff0d3db3223fef70",
    "receipt_file_sha256": "6b894d75f61115a2d2d63769c091ae4da511e9ce9697cd0809fff1b3d1f910a3",
    "acquisition_manifest_sha256": "317ca0f30409d04365ae8d7b5aa096e8454d8bc8fbe13a8b386935b19e719774",
}
_POLY_HAVEN_LICENSE = {
    "license_id": "CC0-1.0",
    "license_url": "https://polyhaven.com/license",
    "entitlement_status": "verified",
    "commercial_use": "allowed",
    "redistribution_restriction": "project_policy",
}
_POLY_HAVEN_ASSET_PINS: Mapping[str, Mapping[str, Any]] = {
    "white_oak_veneer": {
        "logical_asset_id": "visual.material.white_oak_veneer",
        "asset_type": "texture",
        "resolution": "4k",
        "provider_files_hash": "26c153c913feebf19d0ce09ce70dcd3b2b7443b5",
        "source_relative_root": "assets/white_oak_veneer",
        "primary_relative_path": "assets/white_oak_veneer/white_oak_veneer_diff_4k.jpg",
        "source_tree_sha256": "16b8c64f8fdb4301724373913909978a2c31fce1941a55677f4437b5b5976661",
        "files": (
            (
                "white_oak_veneer_diff_4k.jpg",
                9_759_576,
                "3d37444db4293941ef1a9794d6a52457e26d7729ccab6434e5136c093168ed8e",
            ),
            (
                "white_oak_veneer_nor_gl_4k.jpg",
                11_725_297,
                "6fa75cd8f2aff2a13ee67fa5257d1c6b535aeccc13de92f0c59903f530af77aa",
            ),
            (
                "white_oak_veneer_rough_4k.jpg",
                8_834_547,
                "3330235fbdbd061073040f25f27cc76b74ccd8489d8ec5aeb06a4fe2f20b83d3",
            ),
        ),
    },
    "poly_wool_herringbone": {
        "logical_asset_id": "visual.material.poly_wool_herringbone",
        "asset_type": "texture",
        "resolution": "4k",
        "provider_files_hash": "4ef2868d578f407e6aa9c761d7743b5d0a9c3918",
        "source_relative_root": "assets/poly_wool_herringbone",
        "primary_relative_path": "assets/poly_wool_herringbone/poly_wool_herringbone_diff_4k.jpg",
        "source_tree_sha256": "468f726d965639fc8ee66ae459353061ea1050aef9eae50324195fb0f3d93fde",
        "files": (
            (
                "poly_wool_herringbone_diff_4k.jpg",
                13_605_843,
                "a72582be1337c11e2e59a03e01ef0270f2c0f455a410c5cc667df9682e2c76ce",
            ),
            (
                "poly_wool_herringbone_nor_gl_4k.jpg",
                14_307_275,
                "d58370b656d08316b9aca02c3f627e0ffcf2dd22873c4cbeb343321ccd044620",
            ),
            (
                "poly_wool_herringbone_rough_4k.jpg",
                15_049_055,
                "04ba7ce77111a715fd689aa420a6e880b3d166a11e2e9068ae52c0235f2c3329",
            ),
        ),
    },
    "modern_ceiling_lamp_01": {
        "logical_asset_id": "visual.dressing.living.ceiling_lamp",
        "asset_type": "model",
        "resolution": "2k",
        "provider_files_hash": "d324ea2a3c480145e3cf8beca5ec9c408b257dbb",
        "source_relative_root": "assets/modern_ceiling_lamp_01",
        "primary_relative_path": "assets/modern_ceiling_lamp_01/modern_ceiling_lamp_01_2k.blend",
        "source_tree_sha256": "d78debf5a509e5df348a96aaea051ef95efab322ea02a096c6c78b756142ec79",
        "files": (
            (
                "modern_ceiling_lamp_01_2k.blend",
                330_321,
                "7eea1d3318ce550b3251593de9c1110f8b9f76af1523ea19e87c3d638e3c117d",
            ),
            (
                "textures/modern_ceiling_lamp_01_diff_2k.jpg",
                240_872,
                "b0341690dc56eeddd3efa8a91c179a26e163f330907e5483b6903626b600347e",
            ),
            (
                "textures/modern_ceiling_lamp_01_metal_2k.exr",
                77_305,
                "74bbeb0483a70f7509e9a43757892a2073e0b30544824018c7451952ab8aab0c",
            ),
            (
                "textures/modern_ceiling_lamp_01_nor_gl_2k.exr",
                1_671_019,
                "406238c4d1827f216a7d967429277fe6ce053fb779e5d90f1e72396ab5764ffe",
            ),
            (
                "textures/modern_ceiling_lamp_01_rough_2k.jpg",
                443_113,
                "2af306d18d939389f6fa3f8f9d02253aa1cccaa218c794d7b7a9468c18610d92",
            ),
        ),
    },
    "throw_pillows_01": {
        "logical_asset_id": "visual.dressing.living.throw_pillows",
        "asset_type": "model",
        "resolution": "2k",
        "provider_files_hash": "8a475b95a0956bd700394e0f5ed32822071e2f54",
        "source_relative_root": "assets/throw_pillows_01",
        "primary_relative_path": "assets/throw_pillows_01/throw_pillows_01_2k.blend",
        "source_tree_sha256": "4b34ec2f0b2f9691a54b79c6de2175bec6c7474152222fb5742085a23aa39c9d",
        "files": (
            (
                "throw_pillows_01_2k.blend",
                390_419,
                "ba430553adfa9831a3cf0373728db142886203c5dbc8578963a12cee3957d8af",
            ),
            (
                "textures/throw_pillows_01_diff_2k.jpg",
                898_774,
                "119dc2fa364113e862fd09805bf70fc24e96119f0cefd8ecf32d18ac3dbfb831",
            ),
            (
                "textures/throw_pillows_01_nor_gl_2k.exr",
                10_798_338,
                "6467e4a8a1acd361d4eed84f539642117aa972e402313102b92771e93993cc66",
            ),
            (
                "textures/throw_pillows_01_rough_2k.jpg",
                1_275_948,
                "d3e1956bfedf62d50b527bdfcfd053aabf674f4d6df931a2d8b87e554fe8b24f",
            ),
        ),
    },
    "potted_plant_04": {
        "logical_asset_id": "visual.dressing.living.potted_plant",
        "asset_type": "model",
        "resolution": "2k",
        "provider_files_hash": "c71ad499bc2ad1a95b689fc8895447eff788408b",
        "source_relative_root": "assets/potted_plant_04",
        "primary_relative_path": "assets/potted_plant_04/potted_plant_04_2k.blend",
        "source_tree_sha256": "084884b0a341699d76764e4f0186cb0cabbff1cd87f0536cfe168ba38e683da2",
        "files": (
            (
                "potted_plant_04_2k.blend",
                297_303,
                "7c917f78e527ee5b882b53893c2b4dc9bc495da4f07dbb19aa7cf05428501003",
            ),
            (
                "textures/potted_plant_04_diff_2k.jpg",
                1_804_144,
                "088004de42f405aaa5e14b22f9376e066d3b1ba58e957ad7a67a14697f086bcf",
            ),
            (
                "textures/potted_plant_04_nor_gl_2k.exr",
                5_472_710,
                "c2cc78e35e9c83bc3647aeef124dbb3343d28a0d58b713cfcb543dd795c353da",
            ),
            (
                "textures/potted_plant_04_rough_2k.exr",
                1_458_337,
                "cb53f3ac88b49cd394a0b703e9e14ed20fae68fe79d89fae7c9fe385dcdf7415",
            ),
        ),
    },
    "modern_arm_chair_01": {
        "logical_asset_id": "visual.dressing.living.armchair",
        "asset_type": "model",
        "resolution": "2k",
        "provider_files_hash": "6893f36e58dddba95bd0ae1f1ef38537c1852a0b",
        "source_relative_root": "assets/modern_arm_chair_01",
        "primary_relative_path": "assets/modern_arm_chair_01/modern_arm_chair_01_2k.blend",
        "source_tree_sha256": "79118e13383af850d801f14b9ace7a65f91d520ce54b3a5bc8b4cf5e2089a7b1",
        "files": (
            (
                "modern_arm_chair_01_2k.blend",
                355_136,
                "c6c92b5a07be4ab37e48fbf43c7ff233b90b1e364987e2bae790aed501fe97f6",
            ),
            (
                "textures/modern_arm_chair_01_legs_diff_2k.png",
                10_153_780,
                "86cd587fe94c561695df91fc23cc48935be9bc2d98e811ac2be084bcb9ee2bdc",
            ),
            (
                "textures/modern_arm_chair_01_legs_metal_2k.png",
                8_264,
                "e280cde7e0775c960c448ea75e95e4023e3c47f6f5a825ee08d07b397ebbe98e",
            ),
            (
                "textures/modern_arm_chair_01_legs_nor_gl_2k.png",
                10_611_050,
                "6364741a59f40e84f43c06f6e2b40b165613d0bb048ec8729a64b423de0d17d6",
            ),
            (
                "textures/modern_arm_chair_01_legs_rough_2k.png",
                3_497_673,
                "fa49217cd4908d6c403fe37e0ee0b7f74d15168ac3b585ed8d22277c07f4e59b",
            ),
            (
                "textures/modern_arm_chair_01_pillow_diff_2k.png",
                6_961_371,
                "b339fcdde4c1fc1c863b607d3eb878aca495c2edf452d1b9b45ef96641a13ac2",
            ),
            (
                "textures/modern_arm_chair_01_pillow_metal_2k.png",
                8_264,
                "e280cde7e0775c960c448ea75e95e4023e3c47f6f5a825ee08d07b397ebbe98e",
            ),
            (
                "textures/modern_arm_chair_01_pillow_nor_gl_2k.png",
                7_433_277,
                "7b3c44c34ecfa8cf07a8930592364c52a7c543eecd9434b34df1ee46884a7680",
            ),
            (
                "textures/modern_arm_chair_01_pillow_rough_2k.png",
                2_512_880,
                "cc00fe679b9be02e68c3d65980c99fa2b75251fad0649f025b281fe8881086d1",
            ),
        ),
    },
}
_R3_DRESSING_BODY: Mapping[str, Any] = {
    "schema_version": "simworld.vista.hssd-living-r3-dressing/v1",
    "profile_id": "poly-haven-cc0-living-r3",
    "surface_materials": {
        "floor": {
            "asset_id": "white_oak_veneer",
            "target_object_name": "Shell.Floor",
            "mapping_scale": [10.0, 8.0, 1.0],
            "normal_strength": 0.30,
        },
        "rug": {
            "asset_id": "poly_wool_herringbone",
            "object_name": "Dressing.Rug.PolyWoolHerringbone",
            "dimensions_m": [2.85, 1.65, 0.012],
            "location_m": [0.15, -0.08, 0.006],
            "rotation_deg": [0.0, 0.0, 0.0],
            "bevel_m": 0.018,
            "mapping_scale": [10.552473652185, 5.984765986914, 1.0],
            "normal_strength": 0.45,
        },
    },
    "model_instances": [
        {
            "instance_id": "poly.r3/living_room.ceiling_lamp.01",
            "asset_id": "modern_ceiling_lamp_01",
            "collection_name": "modern_ceiling_lamp_01",
            "expected_modifiers": {"modern_ceiling_lamp_01": ["SUBSURF"]},
            "source_bounds_m": {
                "min": [-0.215796411037, -0.217333108187, 0.221092164516],
                "max": [0.215852916241, 0.214327648282, 1.172643661499],
            },
            "transform": {
                "location_m": [0.0, 0.25, 1.827356338501],
                "rotation_deg": [0.0, 0.0, 0.0],
                "scale": [1.0, 1.0, 1.0],
            },
            "support": {"mode": "ceiling", "contact_z_m": 3.0},
            "interaction_policy": "visual_only_no_interaction_authority",
        },
        {
            "instance_id": "poly.r3/living_room.throw_pillows.01",
            "asset_id": "throw_pillows_01",
            "collection_name": "throw_pillows_01",
            "expected_modifiers": {
                "throw_pillows_01_pillow01": [],
                "throw_pillows_01_pillow02": [],
            },
            "source_bounds_m": {
                "min": [-0.504625082016, -0.385605484247, -0.002105058869],
                "max": [0.516942799091, 0.241887062788, 0.448054224253],
            },
            "transform": {
                "location_m": [-1.45, 1.18, 0.481515642386],
                "rotation_deg": [0.0, 0.0, 0.0],
                "scale": [0.72, 0.72, 0.72],
            },
            "support": {
                "mode": "surface",
                "support_instance_id": "hssd.r1/living_room.sofa.01",
                "contact_z_m": 0.48,
            },
            "interaction_policy": "visual_only_no_interaction_authority",
        },
        {
            "instance_id": "poly.r3/living_room.table_plant.01",
            "asset_id": "potted_plant_04",
            "collection_name": "potted_plant_04",
            "expected_modifiers": {
                "potted_plant_04_dirt": [],
                "potted_plant_04_ground": [],
                "potted_plant_04_plant": ["NODES", "WEIGHTED_NORMAL"],
                "potted_plant_04_pot": ["WEIGHTED_NORMAL", "NODES", "SUBSURF"],
            },
            "source_bounds_m": {
                "min": [-0.085137039423, -0.100808270276, 0.00023656647],
                "max": [0.085137039423, 0.085137039423, 0.267833054066],
            },
            "transform": {
                "location_m": [-0.47, 0.47, 0.44151743353],
                "rotation_deg": [0.0, 0.0, -15.0],
                "scale": [1.0, 1.0, 1.0],
            },
            "support": {
                "mode": "surface",
                "support_instance_id": "hssd.r1/living_room.coffee_table.01",
                "contact_z_m": 0.441754,
            },
            "interaction_policy": "visual_only_no_interaction_authority",
        },
        {
            "instance_id": "hssd.r1/living_room.rolling_chair.01",
            "asset_id": "modern_arm_chair_01",
            "collection_name": "modern_arm_chair_01",
            "expected_modifiers": {"modern_arm_chair_01": ["WEIGHTED_NORMAL"]},
            "source_bounds_m": {
                "min": [-0.40680873394, -0.411109954119, 0.000381595368],
                "max": [0.413535684347, 0.575451731682, 1.023233652115],
            },
            "transform": {
                "location_m": [1.7, 0.5, -0.000381595368],
                "rotation_deg": [0.0, 0.0, 145.0],
                "scale": [1.0, 1.0, 1.0],
            },
            "support": {"mode": "floor", "contact_z_m": 0.0},
            "replacement_for": {
                "source_asset_id": "hssd.static.accent_chair",
                "interaction_policy": "visual_only_hidden_r1_proxy_remains_authoritative",
            },
            "interaction_policy": "visual_only_hidden_r1_proxy_remains_authoritative",
        },
    ],
    "lighting": {
        "lamp_point": {
            "name": "Light.CeilingLampWarm",
            "location_m": [0.0, 0.25, 2.26],
            "energy_w": 120.0,
            "color_linear_rgb": [1.0, 0.72, 0.50],
            "shadow_soft_size_m": 0.22,
        }
    },
    "import_policy": {
        "blend_link": False,
        "collection_instance_only": True,
        "preserve_modifiers": True,
        "image_remap": "new_images_only_absolute_receipt_bound_rehash_reload",
        "fail_on_missing_or_unpinned_image": True,
    },
    "authoritative_semantics": {
        "hidden_r1_proxies_remain_authoritative": True,
        "poly_haven_assets_are_visual_only": True,
    },
}
_RENDER_CONFIG = {
    "width_px": 1920,
    "height_px": 1080,
    "camera_class": "player_eye",
    "camera_location_m": [0.75, -1.75, 1.62],
    "camera_target_m": [-0.35, 0.65, 1.05],
    "lens_mm": 32.0,
    "aperture_fstop": 8.0,
    "engine": "CYCLES_CPU",
    "color_management": {
        "view_transform": "AgX",
        "look": "AgX - Medium High Contrast",
        "exposure_ev": -0.75,
    },
    "cycles": {
        "samples": 64,
        "adaptive_sampling": True,
        "adaptive_threshold": 0.02,
        "adaptive_min_samples": 16,
        "max_bounces": 6,
        "sample_clamp_indirect": 3.0,
        "denoising": True,
    },
    "lighting": {
        "window_day": {
            "energy_w": 330.0,
            "size_m": 1.8,
            "color_linear_rgb": [0.95, 0.97, 1.0],
        },
        "ceiling_soft": {
            "energy_w": 80.0,
            "size_m": 1.4,
            "color_linear_rgb": [1.0, 0.82, 0.68],
        },
        "camera_fill": {
            "energy_w": 20.0,
            "size_m": 1.0,
            "color_linear_rgb": [1.0, 0.90, 0.82],
        },
    },
    "saved_png_quality_gates": {
        "minimum_dynamic_range": 0.12,
        "mean_luminance_min_exclusive": 0.025,
        "mean_luminance_max": 0.72,
        "median_luminance_max": 0.80,
        "p95_luminance_max": 0.97,
        "clipped_luminance_threshold": 0.985,
        "clipped_fraction_max": 0.02,
    },
}
_LIVING_IDS = (
    "hssd.r1/living_room.sofa.01",
    "hssd.r1/living_room.coffee_table.01",
    "hssd.r1/living_room.coffee_cup.01",
    "hssd.r1/living_room.coffee_cup.02",
    "hssd.r1/living_room.slipper.01",
    "hssd.r1/living_room.slipper.02",
    "hssd.r1/living_room.pot.01",
    "hssd.r1/living_room.phone.01",
    "hssd.r1/living_room.backpack.01",
    "hssd.r1/living_room.rolling_chair.01",
)
_SUPPORT_REVIEW = {
    "hssd.r1/living_room.sofa.01": ("floor", 0.0, None),
    "hssd.r1/living_room.coffee_table.01": ("floor", 0.0, None),
    "hssd.r1/living_room.coffee_cup.01": (
        "surface",
        0.441754,
        "hssd.r1/living_room.coffee_table.01",
    ),
    "hssd.r1/living_room.coffee_cup.02": (
        "surface",
        0.441754,
        "hssd.r1/living_room.coffee_table.01",
    ),
    "hssd.r1/living_room.slipper.01": ("floor", 0.03, None),
    "hssd.r1/living_room.slipper.02": ("floor", 0.03, None),
    "hssd.r1/living_room.pot.01": ("wall_edge", 0.0, None),
    "hssd.r1/living_room.phone.01": (
        "surface",
        0.441754,
        "hssd.r1/living_room.coffee_table.01",
    ),
    "hssd.r1/living_room.backpack.01": ("wall_edge", 0.0, None),
    "hssd.r1/living_room.rolling_chair.01": ("floor", 0.0, None),
}


class SceneAssemblyError(RuntimeError):
    """Stable fail-closed assembler error."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def _fail(code: str, message: str) -> None:
    raise SceneAssemblyError(code, message)


def canonical_json(value: Any, *, newline: bool = True) -> bytes:
    try:
        data = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise SceneAssemblyError("JSON_INVALID", "non-canonical JSON value") from exc
    return data + (b"\n" if newline else b"")


def content_digest(value: Mapping[str, Any]) -> str:
    body = copy.deepcopy(dict(value))
    body.pop("content_digest", None)
    return hashlib.sha256(canonical_json(body)).hexdigest()


def seal_document(value: Mapping[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(dict(value))
    result["content_digest"] = content_digest(result)
    return result


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _regular_file(root: pathlib.Path, relative: str) -> pathlib.Path:
    candidate = root / relative
    if candidate.is_symlink():
        _fail("SOURCE_SYMLINK", f"symbolic source is prohibited: {relative}")
    try:
        metadata = candidate.stat()
    except OSError as exc:
        raise SceneAssemblyError("SOURCE_MISSING", relative) from exc
    if not stat.S_ISREG(metadata.st_mode):
        _fail("SOURCE_NOT_REGULAR", relative)
    try:
        candidate.resolve(strict=True).relative_to(root)
    except ValueError:
        _fail("SOURCE_ESCAPE", relative)
    return candidate


def _reject_constant(value: str) -> None:
    _fail("JSON_INVALID", f"non-finite constant: {value}")


def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("JSON_DUPLICATE_KEY", key)
        result[key] = value
    return result


def _load_json(path: pathlib.Path) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=_reject_constant,
            object_pairs_hook=_reject_duplicates,
        )
    except SceneAssemblyError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SceneAssemblyError("JSON_INVALID", path.name) from exc
    if type(value) is not dict:
        _fail("JSON_INVALID", f"object root required: {path.name}")
    return value


def _asset_pin_record(asset: AcquiredAsset) -> dict[str, Any]:
    return {
        "logical_asset_id": asset.logical_asset_id,
        "asset_type": asset.asset_type,
        "resolution": asset.resolution,
        "provider_files_hash": asset.provider_files_hash,
        "source_relative_root": asset.source_relative_root,
        "primary_relative_path": asset.primary_relative_path,
        "source_tree_sha256": asset.source_tree_sha256,
        "files": tuple(
            (item.relative_path, item.size_bytes, item.sha256) for item in asset.files
        ),
    }


def _poly_haven_plan_asset(asset: AcquiredAsset) -> dict[str, Any]:
    record = asset_digest_record(asset)
    record.update(
        {
            "source_relative_root": asset.source_relative_root,
            "primary_relative_path": asset.primary_relative_path,
        }
    )
    return record


def _validate_poly_haven_asset_set(external: Any) -> dict[str, Any]:
    if external.receipt_reference() != _POLY_HAVEN_RECEIPT_REFERENCE:
        _fail("POLY_HAVEN_RECEIPT_DRIFT", "fixed CC0 acquisition receipt changed")
    assets_by_id = {asset.asset_id: asset for asset in external.assets}
    if len(assets_by_id) != len(external.assets):
        _fail("POLY_HAVEN_ASSET_SET_INVALID", "duplicate acquisition asset ID")
    selected: dict[str, dict[str, Any]] = {}
    for asset_id, pin in _POLY_HAVEN_ASSET_PINS.items():
        asset = assets_by_id.get(asset_id)
        if asset is None or _asset_pin_record(asset) != pin:
            _fail("POLY_HAVEN_ASSET_DRIFT", asset_id)
        selected[asset_id] = _poly_haven_plan_asset(asset)
    if sum(len(asset["files"]) for asset in selected.values()) != 28:
        _fail("POLY_HAVEN_PAYLOAD_SET_INVALID", "exactly 28 selected payloads required")
    return seal_document(
        {
            "schema_version": "simworld.vista.hssd-living-poly-haven-input/v1",
            "path": str(external.root),
            "receipt": {
                **_POLY_HAVEN_RECEIPT_REFERENCE,
                "relative_path": "acquisition-receipt.json",
                "license": _POLY_HAVEN_LICENSE,
            },
            "assets": selected,
            "selected_asset_count": 6,
            "selected_payload_count": 28,
            "validation_policy": (
                "receipt_sha_digest_manifest_plus_recomputed_tree_and_every_payload_sha256"
            ),
            "binary_payload_in_git": False,
        }
    )


def _validate_poly_haven_bundle(root: pathlib.Path) -> dict[str, Any]:
    try:
        external = load_external_asset_set(root, verify_files=True)
    except (ForgeInputError, OSError) as exc:
        raise SceneAssemblyError(
            "POLY_HAVEN_BUNDLE_INVALID", "fixed CC0 acquisition validation failed"
        ) from exc
    return _validate_poly_haven_asset_set(external)


def _safe_relative(value: Any, *, label: str) -> str:
    if not isinstance(value, str):
        _fail("PATH_INVALID", label)
    path = pathlib.PurePosixPath(value)
    if (
        path.is_absolute()
        or not path.parts
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        _fail("PATH_INVALID", f"unsafe {label}")
    return value


def _footprint(
    location: Sequence[float], dimensions: Sequence[float], yaw_deg: float
) -> tuple[tuple[float, float], ...]:
    radians = math.radians(float(yaw_deg))
    cosine, sine = math.cos(radians), math.sin(radians)
    half_x, half_y = float(dimensions[0]) / 2.0, float(dimensions[1]) / 2.0
    return tuple(
        (
            float(location[0]) + cosine * x - sine * y,
            float(location[1]) + sine * x + cosine * y,
        )
        for x, y in (
            (-half_x, -half_y),
            (half_x, -half_y),
            (half_x, half_y),
            (-half_x, half_y),
        )
    )


def _project(
    points: Sequence[Sequence[float]], axis: Sequence[float]
) -> tuple[float, float]:
    values = [
        float(point[0]) * float(axis[0]) + float(point[1]) * float(axis[1])
        for point in points
    ]
    return min(values), max(values)


def _footprints_overlap(
    left: Sequence[Sequence[float]],
    right: Sequence[Sequence[float]],
    *,
    tolerance: float = 1e-6,
) -> bool:
    axes: list[tuple[float, float]] = []
    for polygon in (left, right):
        for index in range(2):
            edge = (
                float(polygon[index + 1][0]) - float(polygon[index][0]),
                float(polygon[index + 1][1]) - float(polygon[index][1]),
            )
            length = math.hypot(*edge)
            if length <= tolerance:
                _fail("GEOMETRY_INVALID", "degenerate footprint edge")
            axes.append((-edge[1] / length, edge[0] / length))
    for axis in axes:
        left_min, left_max = _project(left, axis)
        right_min, right_max = _project(right, axis)
        if left_max <= right_min + tolerance or right_max <= left_min + tolerance:
            return False
    return True


def _point_in_footprint(
    point: Sequence[float], polygon: Sequence[Sequence[float]]
) -> bool:
    sign: bool | None = None
    for index in range(4):
        start, end = polygon[index], polygon[(index + 1) % 4]
        cross = (float(end[0]) - float(start[0])) * (
            float(point[1]) - float(start[1])
        ) - (float(end[1]) - float(start[1])) * (float(point[0]) - float(start[0]))
        current = cross >= -1e-6
        if sign is None:
            sign = current
        elif current != sign and abs(cross) > 1e-6:
            return False
    return True


def _validate_source_run(
    source_root: pathlib.Path, blender: pathlib.Path
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    if (
        not source_root.is_absolute()
        or source_root.is_symlink()
        or not source_root.is_dir()
    ):
        _fail("SOURCE_ROOT_INVALID", "source run must be an absolute regular directory")
    source_root = source_root.resolve(strict=True)
    documents: dict[str, dict[str, Any]] = {}
    for name, expected_sha in EXPECTED_DOCUMENT_SHA256.items():
        path = _regular_file(source_root, name)
        if sha256_file(path) != expected_sha:
            _fail("SOURCE_DOCUMENT_DRIFT", name)
        document = _load_json(path)
        if document.get("content_digest") != EXPECTED_CONTENT_DIGESTS[
            name
        ] or content_digest(document) != document.get("content_digest"):
            _fail("SOURCE_DOCUMENT_DIGEST_INVALID", name)
        documents[name] = document

    build_plan = documents["build-plan.json"]
    build_result = documents["build-result.json"]
    scene_plan = documents["scene-plan.json"]
    if (
        build_plan.get("schema_version")
        != "simworld.vista.hssd-private-research-forge-plan/v1"
        or build_plan.get("mode") != "execute"
        or build_plan.get("accepted") is not False
        or build_result.get("schema_version")
        != "simworld.vista.hssd-private-research-forge-result/v1"
        or build_result.get("accepted") is not False
        or build_result.get("status")
        != "assets_materialized_scene_plan_only_not_rendered"
        or scene_plan.get("schema_version")
        != "simworld.vista.hssd-private-research-scene-plan/v1"
        or scene_plan.get("accepted_as_visual_evidence") is not False
    ):
        _fail("SOURCE_STATE_INVALID", "R5 source state or schemas drifted")
    if (
        build_result.get("build_plan_content_digest")
        != build_plan.get("content_digest")
        or build_result.get("scene_plan_content_digest")
        != scene_plan.get("content_digest")
        or build_plan.get("scene_plan", {}).get("content_digest")
        != scene_plan.get("content_digest")
    ):
        _fail("SOURCE_LINK_INVALID", "plan/result/scene digest links differ")

    blender_path = blender.resolve(strict=True)
    if (
        blender.is_symlink()
        or not blender_path.is_file()
        or sha256_file(blender_path) != EXPECTED_BLENDER_SHA256
    ):
        _fail("BLENDER_INVALID", "pinned Blender binary is absent or changed")
    if build_plan.get("toolchain", {}).get("blender") != {
        "version": "4.5.8",
        "sha256": EXPECTED_BLENDER_SHA256,
        "bytes": blender_path.stat().st_size,
        "version_enforcement": "worker_requires_exact_bpy_app_version",
        "dry_run_version_probe": False,
    }:
        _fail("BLENDER_RECEIPT_INVALID", "source Blender receipt drifted")

    jobs = build_plan.get("asset_jobs")
    result_assets = build_result.get("assets")
    if (
        not isinstance(jobs, list)
        or not isinstance(result_assets, list)
        or len(jobs) != 26
        or len(result_assets) != 26
    ):
        _fail("SOURCE_ASSET_COUNT_INVALID", "exactly 26 source/result assets required")
    jobs_by_id = {
        job.get("source_asset_id"): job for job in jobs if isinstance(job, dict)
    }
    results_by_id = {
        item.get("source_asset_id"): item
        for item in result_assets
        if isinstance(item, dict)
    }
    if len(jobs_by_id) != 26 or set(jobs_by_id) != set(results_by_id):
        _fail("SOURCE_ASSET_SET_INVALID", "source/result asset sets differ")

    receipts: dict[str, dict[str, Any]] = {}
    for asset_id, job in jobs_by_id.items():
        if not isinstance(asset_id, str) or not isinstance(job, dict):
            _fail("SOURCE_ASSET_INVALID", "invalid asset job")
        result = results_by_id[asset_id]
        output = job.get("output")
        if not isinstance(result, dict) or not isinstance(output, dict):
            _fail("SOURCE_ASSET_INVALID", asset_id)
        glb_relpath = _safe_relative(result.get("glb_relpath"), label="GLB path")
        receipt_relpath = _safe_relative(
            result.get("receipt_relpath"), label="receipt path"
        )
        if glb_relpath != output.get("glb_relpath") or receipt_relpath != output.get(
            "receipt_relpath"
        ):
            _fail("SOURCE_ASSET_LINK_INVALID", asset_id)
        glb_path = _regular_file(source_root, glb_relpath)
        receipt_path = _regular_file(source_root, receipt_relpath)
        receipt = _load_json(receipt_path)
        if (
            receipt.get("schema_version")
            != "simworld.vista.hssd-private-research-asset-receipt/v1"
            or receipt.get("source_asset_id") != asset_id
            or receipt.get("content_digest") != result.get("receipt_content_digest")
            or content_digest(receipt) != receipt.get("content_digest")
            or receipt.get("output_sha256") != result.get("output_sha256")
            or receipt.get("output_relpath") != glb_relpath
            or receipt.get("status") != "normalized_pbr_glb_built_for_private_research"
            or receipt.get("accepted_as_interactive_asset") is not False
            or receipt.get("interaction_authority") != "none_static_joined_glb"
            or receipt.get("output_basisu_required") is not False
            or receipt.get("texture_transport") != "KHR_texture_basisu_to_core_png"
            or sha256_file(glb_path) != result.get("output_sha256")
            or glb_path.stat().st_size != receipt.get("output_bytes")
        ):
            _fail("SOURCE_ASSET_RECEIPT_INVALID", asset_id)
        receipts[asset_id] = receipt

    living_sources = {
        placement.get("source_asset_id")
        for placement in scene_plan.get("placements", [])
        if isinstance(placement, dict) and placement.get("room_id") == ROOM_ID
    }
    if len(living_sources) != 8:
        _fail("LIVING_SOURCE_SET_INVALID", "living room must use exactly 8 sources")
    for asset_id in living_sources:
        assert isinstance(asset_id, str)
        try:
            inspection = inspect_glb(
                _regular_file(source_root, f"assets/{asset_id}.glb")
            )
        except HssdBindingError as exc:
            raise SceneAssemblyError(
                "SOURCE_GLB_INVALID", f"{asset_id}: {exc}"
            ) from exc
        if (
            inspection.get("mesh_count") != 1
            or inspection.get("material_count", 0) < 1
            or inspection.get("pbr_material_count") != inspection.get("material_count")
            or inspection.get("all_primitives_material_bound") != 1
            or inspection.get("pbr_texture_slot_count", 0) < 1
            or inspection.get("basisu_required") != 0
        ):
            _fail("SOURCE_PBR_GATE_FAILED", asset_id)
    return documents, receipts


def _living_placements(
    scene_plan: Mapping[str, Any], receipts: Mapping[str, Mapping[str, Any]]
) -> list[dict[str, Any]]:
    raw = [
        item
        for item in scene_plan.get("placements", [])
        if isinstance(item, dict) and item.get("room_id") == ROOM_ID
    ]
    if tuple(item.get("instance_id") for item in raw) != _LIVING_IDS:
        _fail(
            "LIVING_PLACEMENT_SET_INVALID",
            "fixed living placement set or order drifted",
        )
    records: list[dict[str, Any]] = []
    for item in raw:
        instance_id = item["instance_id"]
        source_id = item.get("source_asset_id")
        transform = item.get("transform")
        intent = item.get("placement_intent")
        receipt = receipts.get(source_id)
        if (
            not isinstance(transform, dict)
            or not isinstance(intent, dict)
            or receipt is None
        ):
            _fail("LIVING_PLACEMENT_INVALID", instance_id)
        location = transform.get("location_m")
        rotation = transform.get("rotation_deg")
        dimensions = receipt.get("actual_dimensions_m")
        if (
            transform.get("coordinate_frame") != "room_local_m"
            or transform.get("scale") != [1, 1, 1]
            or not isinstance(location, list)
            or len(location) != 3
            or not isinstance(rotation, list)
            or len(rotation) != 3
            or rotation[:2] != [0, 0]
            or not isinstance(dimensions, list)
            or len(dimensions) != 3
            or any(
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(float(value))
                for value in [*location, *rotation, *dimensions]
            )
        ):
            _fail("LIVING_TRANSFORM_INVALID", instance_id)
        footprint = _footprint(location, dimensions, rotation[2])
        bounds_min, bounds_max = ROOM_BOUNDS_M["min_m"], ROOM_BOUNDS_M["max_m"]
        if any(
            x < bounds_min[0] - 1e-6
            or x > bounds_max[0] + 1e-6
            or y < bounds_min[1] - 1e-6
            or y > bounds_max[1] + 1e-6
            for x, y in footprint
        ):
            _fail("LIVING_FOOTPRINT_OUTSIDE_ROOM", instance_id)
        review = _SUPPORT_REVIEW.get(instance_id)
        if (
            review is None
            or intent.get("support_mode") != review[0]
            or abs(float(location[2]) - review[1]) > 1e-6
        ):
            _fail("LIVING_SUPPORT_REVIEW_FAILED", instance_id)
        records.append(
            {
                "instance_id": instance_id,
                "source_asset_id": source_id,
                "source_glb_relpath": receipt["output_relpath"],
                "source_glb_sha256": receipt["output_sha256"],
                "source_receipt_content_digest": receipt["content_digest"],
                "dimensions_m": dimensions,
                "transform": transform,
                "footprint_m": [[round(x, 9), round(y, 9)] for x, y in footprint],
                "support_review": {
                    "support_mode": review[0],
                    "reviewed_bottom_z_m": review[1],
                    "support_instance_id": review[2],
                    "contact_status": (
                        "reviewed_surface_contact"
                        if review[2]
                        else "reviewed_floor_contact"
                        if review[1] == 0
                        else "reviewed_floor_presentation_clearance"
                    ),
                },
                "interaction_policy": item.get("interaction_policy"),
            }
        )

    by_id = {record["instance_id"]: record for record in records}
    for record in records:
        support_id = record["support_review"]["support_instance_id"]
        if support_id:
            support = by_id[support_id]
            support_top = float(support["transform"]["location_m"][2]) + float(
                support["dimensions_m"][2]
            )
            if abs(
                support_top - float(record["transform"]["location_m"][2])
            ) > 1e-6 or not all(
                _point_in_footprint(corner, support["footprint_m"])
                for corner in record["footprint_m"]
            ):
                _fail("LIVING_SURFACE_CONTACT_INVALID", record["instance_id"])

    for left_index, left in enumerate(records):
        left_bottom = float(left["transform"]["location_m"][2])
        left_top = left_bottom + float(left["dimensions_m"][2])
        for right in records[left_index + 1 :]:
            right_bottom = float(right["transform"]["location_m"][2])
            right_top = right_bottom + float(right["dimensions_m"][2])
            z_overlap = min(left_top, right_top) > max(left_bottom, right_bottom) + 1e-6
            if z_overlap and _footprints_overlap(
                left["footprint_m"], right["footprint_m"]
            ):
                _fail(
                    "LIVING_NON_INTENTIONAL_OVERLAP",
                    f"{left['instance_id']} intersects {right['instance_id']}",
                )
    return records


def _source_bounds_footprint(
    model: Mapping[str, Any],
) -> tuple[tuple[float, float], ...]:
    bounds = model["source_bounds_m"]
    transform = model["transform"]
    minimum = bounds["min"]
    maximum = bounds["max"]
    location = transform["location_m"]
    scale = transform["scale"]
    yaw = math.radians(float(transform["rotation_deg"][2]))
    cosine, sine = math.cos(yaw), math.sin(yaw)
    return tuple(
        (
            float(location[0])
            + cosine * float(x) * float(scale[0])
            - sine * float(y) * float(scale[1]),
            float(location[1])
            + sine * float(x) * float(scale[0])
            + cosine * float(y) * float(scale[1]),
        )
        for x, y in (
            (minimum[0], minimum[1]),
            (maximum[0], minimum[1]),
            (maximum[0], maximum[1]),
            (minimum[0], maximum[1]),
        )
    )


def _build_r3_dressing_plan(
    placements: Sequence[Mapping[str, Any]], poly_haven: Mapping[str, Any]
) -> dict[str, Any]:
    if set(poly_haven.get("assets", {})) != set(_POLY_HAVEN_ASSET_PINS):
        _fail("R3_POLY_HAVEN_SET_INVALID", "R3 requires the exact six pinned assets")
    by_id = {placement.get("instance_id"): placement for placement in placements}
    replacement = by_id.get("hssd.r1/living_room.rolling_chair.01")
    if (
        replacement is None
        or replacement.get("source_asset_id") != "hssd.static.accent_chair"
        or replacement.get("interaction_policy")
        != "visual_only_hidden_r1_proxy_remains_authoritative"
    ):
        _fail(
            "R3_REPLACEMENT_AUTHORITY_INVALID", "accent-chair proxy authority drifted"
        )

    dressing = seal_document(_R3_DRESSING_BODY)
    room_min, room_max = ROOM_BOUNDS_M["min_m"], ROOM_BOUNDS_M["max_m"]
    model_footprints: dict[str, tuple[tuple[float, float], ...]] = {}
    for model in dressing["model_instances"]:
        transform = model["transform"]
        bounds = model["source_bounds_m"]
        values = [
            *transform["location_m"],
            *transform["rotation_deg"],
            *transform["scale"],
            *bounds["min"],
            *bounds["max"],
        ]
        if any(
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(float(value))
            for value in values
        ):
            _fail("R3_MODEL_TRANSFORM_INVALID", model["instance_id"])
        footprint = _source_bounds_footprint(model)
        if any(
            x < room_min[0] - 1e-6
            or x > room_max[0] + 1e-6
            or y < room_min[1] - 1e-6
            or y > room_max[1] + 1e-6
            for x, y in footprint
        ):
            _fail("R3_MODEL_FOOTPRINT_OUTSIDE_ROOM", model["instance_id"])
        model_footprints[model["instance_id"]] = footprint
        scale_z = float(transform["scale"][2])
        world_min_z = (
            float(transform["location_m"][2]) + float(bounds["min"][2]) * scale_z
        )
        world_max_z = (
            float(transform["location_m"][2]) + float(bounds["max"][2]) * scale_z
        )
        support = model["support"]
        contact = world_max_z if support["mode"] == "ceiling" else world_min_z
        if abs(contact - float(support["contact_z_m"])) > 1e-9:
            _fail("R3_MODEL_SUPPORT_INVALID", model["instance_id"])

    support_pairs = {
        "poly.r3/living_room.throw_pillows.01": "hssd.r1/living_room.sofa.01",
        "poly.r3/living_room.table_plant.01": "hssd.r1/living_room.coffee_table.01",
    }
    for child_id, support_id in support_pairs.items():
        support = by_id[support_id]
        if not all(
            _point_in_footprint(corner, support["footprint_m"])
            for corner in model_footprints[child_id]
        ):
            _fail("R3_MODEL_SUPPORT_FOOTPRINT_INVALID", child_id)

    chair_id = "hssd.r1/living_room.rolling_chair.01"
    chair_footprint = model_footprints[chair_id]
    for placement in placements:
        if placement["instance_id"] == chair_id:
            continue
        bottom = float(placement["transform"]["location_m"][2])
        top = bottom + float(placement["dimensions_m"][2])
        if top > 1e-6 and _footprints_overlap(
            chair_footprint, placement["footprint_m"]
        ):
            _fail("R3_CHAIR_NON_INTENTIONAL_OVERLAP", placement["instance_id"])
    return dressing


def build_assembly_plan(
    *,
    source_run: pathlib.Path = DEFAULT_SOURCE_RUN,
    blender: pathlib.Path = DEFAULT_BLENDER,
    poly_haven_root: pathlib.Path = DEFAULT_POLY_HAVEN_ROOT,
    output_root: pathlib.Path | None = None,
    execute: bool = False,
) -> dict[str, Any]:
    """Return a deterministic plan; dry-run performs no writes or subprocesses."""

    if execute and output_root is None:
        _fail("OUTPUT_REQUIRED", "--execute requires --output-root")
    if output_root is not None and not output_root.is_absolute():
        _fail("OUTPUT_INVALID", "output root must be absolute")
    resolved_output = (
        _validate_output_location(
            output_root,
            source_root=source_run,
            poly_haven_root=poly_haven_root,
        )
        if output_root is not None
        else None
    )
    documents, receipts = _validate_source_run(source_run, blender)
    poly_haven = _validate_poly_haven_bundle(poly_haven_root)
    source_root = source_run.resolve(strict=True)
    placements = _living_placements(documents["scene-plan.json"], receipts)
    for placement in placements:
        placement["visual_import_policy"] = (
            "replace_with_poly_haven_collection"
            if placement["instance_id"] == "hssd.r1/living_room.rolling_chair.01"
            else "import_hssd_normalized_glb"
        )
    r3_dressing = _build_r3_dressing_plan(placements, poly_haven)
    plan = {
        "schema_version": ASSEMBLY_PLAN_SCHEMA,
        "mode": "execute" if execute else "dry_run",
        "will_write": execute,
        "will_execute_blender": execute,
        "accepted_as_visual_evidence": False,
        "status": "ready_for_explicit_blender_execution"
        if execute
        else "dry_run_validated_no_write",
        "source_run": {
            "path": str(source_root),
            "documents": [
                {
                    "relative_path": name,
                    "sha256": EXPECTED_DOCUMENT_SHA256[name],
                    "content_digest": EXPECTED_CONTENT_DIGESTS[name],
                }
                for name in sorted(EXPECTED_DOCUMENT_SHA256)
            ],
            "license_scope": documents["build-plan.json"]["license_scope"],
        },
        "poly_haven": poly_haven,
        "blender": {
            "path": str(blender.resolve(strict=True)),
            "version": "4.5.8",
            "sha256": EXPECTED_BLENDER_SHA256,
        },
        "output": {
            "path": str(resolved_output) if resolved_output is not None else None,
            "root_policy": "fresh_append_only_external_directory",
            "render_relative_path": RENDER_RELATIVE_PATH,
            "blend_relative_path": BLEND_RELATIVE_PATH,
            "binary_payload_in_git": False,
        },
        "room": {
            "room_id": ROOM_ID,
            "coordinate_frame": "room_local_m_z_up",
            "bounds_m": ROOM_BOUNDS_M,
            "shell": "enclosed_four_walls_floor_ceiling_with_interior_trim",
        },
        "placements": placements,
        "r3_dressing": r3_dressing,
        "render": copy.deepcopy(_RENDER_CONFIG),
        "preflight_gates": {
            "fixed_source_documents_validated": True,
            "all_26_result_asset_receipts_validated": True,
            "living_normalized_pbr_glbs_validated": True,
            "poly_haven_receipt_tree_and_28_payloads_validated": True,
            "r3_dressing_geometry_and_supports_validated": True,
            "accent_chair_visual_replacement_preserves_proxy_authority": True,
            "full_rotated_footprints_inside_room": True,
            "non_intentional_overlaps_absent": True,
            "reviewed_support_contacts_validated": True,
            "pinned_blender_4_5_8_validated_without_execution": True,
        },
        "claims": {
            "gta_level": False,
            "production_ready": False,
            "interactive": False,
            "ue_runtime_validated": False,
            "scope": "private_noncommercial_research_visual_evidence_only",
        },
        "visible_limits": [
            "HSSD embedded textures are 256x256 base levels",
            "Poly Haven model maps are 2K and floor/rug maps are 4K CC0 sources",
            "assets are static joined presentation shells with no collision or interaction authority",
            "two footwear placements retain the reviewed 0.03m presentation clearance",
            "no character, animation, Unreal runtime, or gameplay is validated by this render",
        ],
    }
    return seal_document(plan)


def _is_relative_to(path: pathlib.Path, root: pathlib.Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _validate_output_location(
    path: pathlib.Path,
    *,
    source_root: pathlib.Path = DEFAULT_SOURCE_RUN,
    poly_haven_root: pathlib.Path = DEFAULT_POLY_HAVEN_ROOT,
) -> pathlib.Path:
    if not path.is_absolute() or path.is_symlink() or path.exists():
        _fail("OUTPUT_NOT_FRESH", "execute output must be a new absolute path")
    try:
        resolved_parent = path.parent.resolve(strict=True)
    except OSError as exc:
        raise SceneAssemblyError(
            "OUTPUT_PARENT_INVALID", "output parent must already exist"
        ) from exc
    if not resolved_parent.is_dir():
        _fail("OUTPUT_PARENT_INVALID", "output parent must be a directory")
    candidate = resolved_parent / path.name
    if ".git" in candidate.parts or any(
        os.path.lexists(str(ancestor / ".git"))
        for ancestor in (resolved_parent, *resolved_parent.parents)
    ):
        _fail(
            "OUTPUT_INSIDE_GIT_WORKTREE",
            "binary render output cannot have any .git ancestor",
        )
    fixed_source = DEFAULT_SOURCE_RUN.resolve(strict=False)
    requested_source = source_root.resolve(strict=False)
    fixed_poly_haven = DEFAULT_POLY_HAVEN_ROOT.resolve(strict=False)
    requested_poly_haven = poly_haven_root.resolve(strict=False)
    if any(
        _is_relative_to(candidate, prohibited)
        for prohibited in {fixed_source, requested_source}
    ):
        _fail(
            "OUTPUT_INSIDE_SOURCE_RUN",
            "render output cannot be created inside an immutable source run",
        )
    if any(
        _is_relative_to(candidate, prohibited)
        for prohibited in {fixed_poly_haven, requested_poly_haven}
    ):
        _fail(
            "OUTPUT_INSIDE_POLY_HAVEN",
            "render output cannot be created inside the immutable CC0 acquisition",
        )
    return candidate


def _prepare_output_root(
    path: pathlib.Path,
    *,
    source_root: pathlib.Path = DEFAULT_SOURCE_RUN,
    poly_haven_root: pathlib.Path = DEFAULT_POLY_HAVEN_ROOT,
) -> pathlib.Path:
    candidate = _validate_output_location(
        path,
        source_root=source_root,
        poly_haven_root=poly_haven_root,
    )
    candidate.mkdir(mode=0o700)
    return candidate.resolve(strict=True)


def _write_exclusive(path: pathlib.Path, data: bytes) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(data)


def _safe_environment() -> dict[str, str]:
    allowed = (
        "HOME",
        "LANG",
        "LC_ALL",
        "LOGNAME",
        "PATH",
        "TMPDIR",
        "USER",
        "XDG_CACHE_HOME",
        "XDG_CONFIG_HOME",
        "XDG_DATA_HOME",
        "XDG_RUNTIME_DIR",
    )
    environment = {key: os.environ[key] for key in allowed if key in os.environ}
    environment.update(
        {
            "CUDA_VISIBLE_DEVICES": "",
            "VISTA_NETWORK_DISABLED": "1",
            "NO_PROXY": "*",
            "no_proxy": "*",
            "PYTHONNOUSERSITE": "1",
        }
    )
    return environment


def validate_assembly_receipt(
    receipt: Mapping[str, Any], plan: Mapping[str, Any], output_root: pathlib.Path
) -> None:
    if (
        receipt.get("schema_version") != ASSEMBLY_RECEIPT_SCHEMA
        or receipt.get("content_digest") != content_digest(receipt)
        or receipt.get("assembly_plan_content_digest") != plan.get("content_digest")
        or receipt.get("status") != "rendered_private_research_review_pending"
        or receipt.get("accepted_as_visual_evidence") is not False
        or receipt.get("visual_review") != "pending"
    ):
        _fail("ASSEMBLY_RECEIPT_INVALID", "receipt identity or review state invalid")
    render = receipt.get("render")
    gates = receipt.get("gates")
    if (
        not isinstance(render, dict)
        or not isinstance(gates, dict)
        or any(value is not True for value in gates.values())
    ):
        _fail("ASSEMBLY_RECEIPT_INVALID", "render gates are incomplete")
    metrics = render.get("metrics")
    quality = plan.get("render", {}).get("saved_png_quality_gates")
    if not isinstance(metrics, dict) or not isinstance(quality, dict):
        _fail("ASSEMBLY_RECEIPT_INVALID", "saved-PNG metrics are absent")
    numeric = (
        "sample_luminance_min",
        "sample_luminance_max",
        "sample_luminance_mean",
        "sample_luminance_median",
        "sample_luminance_p95",
        "sample_clipped_fraction",
    )
    if (
        metrics.get("exposure_gate_passed") is not True
        or any(
            not isinstance(metrics.get(key), (int, float))
            or isinstance(metrics.get(key), bool)
            or not math.isfinite(float(metrics[key]))
            for key in numeric
        )
        or float(metrics["sample_luminance_max"])
        - float(metrics["sample_luminance_min"])
        < float(quality["minimum_dynamic_range"])
        or not float(quality["mean_luminance_min_exclusive"])
        < float(metrics["sample_luminance_mean"])
        <= float(quality["mean_luminance_max"])
        or float(metrics["sample_luminance_median"])
        > float(quality["median_luminance_max"])
        or float(metrics["sample_luminance_p95"]) > float(quality["p95_luminance_max"])
        or float(metrics["sample_clipped_fraction"])
        > float(quality["clipped_fraction_max"])
    ):
        _fail("ASSEMBLY_RECEIPT_INVALID", "saved-PNG exposure metrics failed")
    render_path = _regular_file(output_root, render.get("relative_path"))
    blend_path = _regular_file(
        output_root, receipt.get("blend", {}).get("relative_path")
    )
    if (
        render.get("width_px") != 1920
        or render.get("height_px") != 1080
        or render.get("sha256") != sha256_file(render_path)
        or render.get("bytes") != render_path.stat().st_size
        or receipt.get("blend", {}).get("sha256") != sha256_file(blend_path)
    ):
        _fail("ASSEMBLY_ARTIFACT_INVALID", "render or blend seal mismatch")


def execute_assembly(plan: Mapping[str, Any]) -> dict[str, Any]:
    """Execute exactly one external Blender assembly attempt."""

    if (
        plan.get("mode") != "execute"
        or plan.get("will_execute_blender") is not True
        or plan.get("content_digest") != content_digest(plan)
    ):
        _fail("EXECUTE_NOT_AUTHORIZED", "an intact explicit execute plan is required")
    output_value = plan.get("output", {}).get("path")
    if not isinstance(output_value, str):
        _fail("OUTPUT_REQUIRED", "execute plan lacks output root")
    source_value = plan.get("source_run", {}).get("path")
    if not isinstance(source_value, str):
        _fail("EXECUTE_NOT_AUTHORIZED", "execute plan lacks fixed source root")
    poly_haven_value = plan.get("poly_haven", {}).get("path")
    if not isinstance(poly_haven_value, str):
        _fail("EXECUTE_NOT_AUTHORIZED", "execute plan lacks fixed Poly Haven root")
    output_root = _prepare_output_root(
        pathlib.Path(output_value),
        source_root=pathlib.Path(source_value),
        poly_haven_root=pathlib.Path(poly_haven_value),
    )
    plan_path = output_root / "assembly-plan.json"
    _write_exclusive(plan_path, canonical_json(plan))
    worker = pathlib.Path(__file__).with_name("blender_worker.py").resolve(strict=True)
    command = [
        plan["blender"]["path"],
        "--background",
        "--factory-startup",
        "--disable-autoexec",
        "--python-exit-code",
        "1",
        "--python",
        str(worker),
        "--",
        "--assembly-plan",
        str(plan_path),
        "--output-root",
        str(output_root),
    ]
    with (output_root / "blender.log").open("xb") as log:
        try:
            subprocess.run(
                command,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                env=_safe_environment(),
                timeout=600,
                check=True,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise SceneAssemblyError(
                "BLENDER_EXECUTION_FAILED", str(output_root / "blender.log")
            ) from exc
    receipt_path = output_root / "assembly-receipt.json"
    receipt = _load_json(_regular_file(output_root, receipt_path.name))
    validate_assembly_receipt(receipt, plan, output_root)
    return receipt


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-run", type=pathlib.Path, default=DEFAULT_SOURCE_RUN)
    parser.add_argument("--blender", type=pathlib.Path, default=DEFAULT_BLENDER)
    parser.add_argument(
        "--poly-haven-root", type=pathlib.Path, default=DEFAULT_POLY_HAVEN_ROOT
    )
    parser.add_argument("--output-root", type=pathlib.Path)
    parser.add_argument("--execute", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parse_args(argv)
    plan = build_assembly_plan(
        source_run=arguments.source_run,
        blender=arguments.blender,
        poly_haven_root=arguments.poly_haven_root,
        output_root=arguments.output_root,
        execute=arguments.execute,
    )
    result: Mapping[str, Any] = execute_assembly(plan) if arguments.execute else plan
    sys.stdout.buffer.write(canonical_json(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
