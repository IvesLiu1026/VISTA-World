"""Fail-closed R5 HSSD source and execution validation for UE commandlets.

This module is intentionally independent from Unreal's Python module.  The
host can therefore validate the complete private-research source inventory and
construct a pinned execution manifest before an Editor commandlet is allowed
to read any GLB.  R5 is a closed, non-commercial visual-only payload: every
document byte digest, receipt byte/content digest, and GLB byte digest is fixed
below.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import stat
import struct
from typing import Any

import commandlet_common as base
import hssd_ue57_glb_compatibility as compatibility


EXECUTION_SCHEMA = "simworld.vista.playable-home-hssd-private-research-ue-execution/v2"
IMPORT_RECEIPT_SCHEMA = (
    "simworld.vista.playable-home-hssd-private-research-ue-import-receipt/v2"
)
COMPATIBILITY_AGGREGATE_SCHEMA = (
    "simworld.vista.hssd-ue57-glb-compatibility-aggregate/v1"
)
EXECUTION_ENV = "VISTA_PLAYABLE_HOME_HSSD_EXECUTION"
EXECUTION_SHA_ENV = "VISTA_PLAYABLE_HOME_HSSD_EXECUTION_SHA256"
PROJECT_ENV = "VISTA_PLAYABLE_HOME_PROJECT"
IMPORT_MARKER = "VISTA_PLAYABLE_HOME_HSSD_PRIVATE_RESEARCH_IMPORT_RESULT:"
IMPORT_RESULT_FILE = "hssd-private-research-import-result.json"
EXPECTED_ENGINE_VERSION = "5.7.3-50162420+++UE5+Release-5.7"
DIAGNOSTIC_NAMESPACE = (
    "/Game/VISTA/PlayableHome/"
    "hssd_private_research_r5_phase1_diagnostic/HSSDPrivateResearch"
)
DIAGNOSTIC_IMPORT_MODE = "diagnostic_nonpromotable_material_conflict"
DIAGNOSTIC_IMPORT_STATUS = "diagnostic_nonpromotable_imported_candidate"
COMPATIBILITY_STATUS = "nonpromotable_active_dual_material_conflict"
PROMOTION_STATUS = "blocked_active_dual_material_conflict"
EXPECTED_COMPATIBILITY_COUNTS = {
    "asset_count": 26,
    "removed_noop_transmission": 82,
    "retained_active_transmission": 2,
    "retained_active_dual_conflicts": 1,
    "blocking_asset_count": 1,
}

BUILD_PLAN_SCHEMA = "simworld.vista.hssd-private-research-forge-plan/v1"
BUILD_RESULT_SCHEMA = "simworld.vista.hssd-private-research-forge-result/v1"
SCENE_PLAN_SCHEMA = "simworld.vista.hssd-private-research-scene-plan/v1"
ASSET_RECEIPT_SCHEMA = "simworld.vista.hssd-private-research-asset-receipt/v1"
PROFILE_SCHEMA = "simworld.vista.playable-home-hssd-private-research-profile/v1"
PROFILE_ID = "hssd_private_research_r1"
PROFILE_CONTENT_DIGEST = (
    "4b76e178ab1a3043d6adda6fe5786a5111f58523f4f8a23eb9cc2c82d883e8d3"
)

EXPECTED_DOCUMENT_SHA256 = {
    "build-plan.json": (
        "88b645fc81936b2eefe7e2d572d7b6e4959aede2d20b3277096753edeba78c1e"
    ),
    "build-result.json": (
        "f9cdeff719e6faf0850d1fb0184406a5a49c9a772cb8889022c1f465cc3150be"
    ),
    "scene-plan.json": (
        "bcf8d1cc63fd6529a7277020ba6712b88de7dc04e0f7448df98e24e0c54238fc"
    ),
}
EXPECTED_CONTENT_DIGESTS = {
    "build-plan.json": (
        "b06e0fb2cc92231f3ddc674a9adf99c7684204978e3ba303239484335cb33de7"
    ),
    "build-result.json": (
        "6b75a0c83191873b5e62e465d266f340d37aa24befda1e5e291686137d1685c7"
    ),
    "scene-plan.json": (
        "c02223bf7d113264455d83f5426cbb3efca171f087a654492af01d7c619cae0f"
    ),
}

EXPECTED_ASSET_PINS = {
    "hssd.static.accent_chair": {
        "receipt_sha256": "6356909ac9ab60c015d59f7623693caf3ef2124121e98a8021a946dd4fec26cf",
        "receipt_content_digest": "ee20da8646d0843922b9f9c424de989853cfbde6881d257ab3a9d77ae2726a96",
        "glb_sha256": "11cb268e746fb24035682804134ee8cdef9ae2c208d6433adadc4604f829d29e",
        "glb_bytes": 966784,
        "material_count": 4,
        "pbr_material_count": 4,
        "texture_count": 3,
        "pbr_texture_slot_count": 3,
        "base_normal_orm_texture_slot_count": 3,
    },
    "hssd.static.bag": {
        "receipt_sha256": "ea3d0f1a94c54c38613fa8f64c497c03df555195374c6a80e96f936ee1f62127",
        "receipt_content_digest": "c241e68aefca41638d8f4957334ac5f33dad5865a30172f89205fd3fa842a0cb",
        "glb_sha256": "66e1efb0f43f37cb487917788600b7576c5ac10f42f561df30f3d044fac4f10b",
        "glb_bytes": 295644,
        "material_count": 1,
        "pbr_material_count": 1,
        "texture_count": 2,
        "pbr_texture_slot_count": 2,
        "base_normal_orm_texture_slot_count": 2,
    },
    "hssd.static.bathtub": {
        "receipt_sha256": "8091a64265fee2dae9b0ef96339cff2df3bc09c386c47618bcb71b870b73327b",
        "receipt_content_digest": "393a92f2c9e4125a64d865f58fd7e151f3db9e7a60a3f9a0bdc2295b1f4ecbde",
        "glb_sha256": "5165a9202a1be10992286c7a81b7a4adeb7df32c9d1d1eabcd8ddfce0a3f08ea",
        "glb_bytes": 236520,
        "material_count": 4,
        "pbr_material_count": 4,
        "texture_count": 3,
        "pbr_texture_slot_count": 2,
        "base_normal_orm_texture_slot_count": 2,
    },
    "hssd.static.bed": {
        "receipt_sha256": "b04639924c2a9c9a870204a23523894ca7634e93ef25f965cceed345c0f051a3",
        "receipt_content_digest": "35a43e363cb59075b6a978f4748a90be7c96cdcfb6fc04479a05e456dd966aa1",
        "glb_sha256": "a7c1a277c468b1f0bd9e823995bc96f458d494debacea6bca5716f2a2fc721bc",
        "glb_bytes": 1059452,
        "material_count": 4,
        "pbr_material_count": 4,
        "texture_count": 3,
        "pbr_texture_slot_count": 3,
        "base_normal_orm_texture_slot_count": 3,
    },
    "hssd.static.cabinet": {
        "receipt_sha256": "d530eeb4e3a348f1bee3ec5049ca3985de1985c082be2aa1566ff5508970f63d",
        "receipt_content_digest": "6e2b6321464c1fc6579f852b8b607f246ab545f92cbe94a794ed100883291454",
        "glb_sha256": "2150b6ec509c945ac3abc937479ff27a2043d476376f66891eb9cabb7c0b449a",
        "glb_bytes": 536008,
        "material_count": 2,
        "pbr_material_count": 2,
        "texture_count": 3,
        "pbr_texture_slot_count": 2,
        "base_normal_orm_texture_slot_count": 2,
    },
    "hssd.static.clothes": {
        "receipt_sha256": "3f7a6f8362eb446e6c298ae0d0d6b468645558d833806f0aed5221a5e7e0b669",
        "receipt_content_digest": "b60f271f0507502cc34ec721f2cbb8b296477e8b80647a2c1998689ac3df6ee6",
        "glb_sha256": "e6e9fffe67617a9ad64d250242acee84e9b7ffc41f54611846c2013044336488",
        "glb_bytes": 696796,
        "material_count": 5,
        "pbr_material_count": 5,
        "texture_count": 3,
        "pbr_texture_slot_count": 3,
        "base_normal_orm_texture_slot_count": 3,
    },
    "hssd.static.coffee_cup": {
        "receipt_sha256": "2d0f49da146360f0ba3fd9953a12d00ac31e42d06a9486a8ddb1df85895e320e",
        "receipt_content_digest": "c65143c56ea06e95983835e195901009f1285a143a4aba3a2a53716314e5853b",
        "glb_sha256": "58362d52f55a2b1ebbd4fca3fc444c4535fcb290353750a3779ef0cdd90927f0",
        "glb_bytes": 76896,
        "material_count": 3,
        "pbr_material_count": 3,
        "texture_count": 1,
        "pbr_texture_slot_count": 1,
        "base_normal_orm_texture_slot_count": 1,
    },
    "hssd.static.coffee_table": {
        "receipt_sha256": "ddb66be9767a923841a982c894c13e182c24dd53a1596b56cd53c07f93d46d65",
        "receipt_content_digest": "7005c587ff33f6b1ce20ad89b0506760064e25217b4f53a462ba28df5637bd0b",
        "glb_sha256": "87962fbd7b4001f6d79c0338485f588e1814361c17fa41a6ba3129238eef1213",
        "glb_bytes": 154296,
        "material_count": 3,
        "pbr_material_count": 3,
        "texture_count": 5,
        "pbr_texture_slot_count": 4,
        "base_normal_orm_texture_slot_count": 4,
    },
    "hssd.static.cooking_pot": {
        "receipt_sha256": "cfb6e0b2aa1ef9a5897cff5ff4514dca534ee3a00ac19eacea2e14cb8bce68e6",
        "receipt_content_digest": "aac38362b29ad3b1a77a048f3f061d11eea7f0a5050f7a261bc92f0348e40994",
        "glb_sha256": "2c16e33ce7ca02534c06526e08c3a2890cce5e5aafd47f95c439a01ef6104f83",
        "glb_bytes": 563948,
        "material_count": 2,
        "pbr_material_count": 2,
        "texture_count": 3,
        "pbr_texture_slot_count": 3,
        "base_normal_orm_texture_slot_count": 3,
    },
    "hssd.static.desk": {
        "receipt_sha256": "310945ece86c0ff0a90b05e39641cfcb05e973808342689aa092306b03404ed6",
        "receipt_content_digest": "510350673c6ed432b19cd1d79e6c8bceb78220e012e7fcc7aa8ac16f492a28f5",
        "glb_sha256": "a89b9b80f7c09f01ffd96262040e694c59d77a1082a9346581b91108115333e0",
        "glb_bytes": 292252,
        "material_count": 3,
        "pbr_material_count": 3,
        "texture_count": 9,
        "pbr_texture_slot_count": 6,
        "base_normal_orm_texture_slot_count": 6,
    },
    "hssd.static.dining_chair": {
        "receipt_sha256": "26036e8974769175f16a0152618c2620d9c55c2c7985d8a2081af80060d913f6",
        "receipt_content_digest": "bab902ed3cecfc2e38caafa72989b7e0b9ab417a1f71837ca3e618b124f2174b",
        "glb_sha256": "ef5cb8136c40e6798c5584ad021c3aff3ac55f39118e0097cbf0451db459f21d",
        "glb_bytes": 256448,
        "material_count": 3,
        "pbr_material_count": 3,
        "texture_count": 2,
        "pbr_texture_slot_count": 1,
        "base_normal_orm_texture_slot_count": 1,
    },
    "hssd.static.dining_table": {
        "receipt_sha256": "ddec9dfb74c2ad45fcf471cdc627fc1f9a2856256fea2a61af2eae09e9c471d5",
        "receipt_content_digest": "28d35629b7f6553f70f42a03d6fd4588453429e8533b63a020e3af7c14bdf6b6",
        "glb_sha256": "ec5535bc78982f56c60b3003ed65038c788aae4ab1c7f04498e9876edcf37506",
        "glb_bytes": 298212,
        "material_count": 2,
        "pbr_material_count": 2,
        "texture_count": 6,
        "pbr_texture_slot_count": 4,
        "base_normal_orm_texture_slot_count": 4,
    },
    "hssd.static.faucet": {
        "receipt_sha256": "e751b133f27167195387907d63b6fa4f60a923d83f4e6586a06c6dd02015f913",
        "receipt_content_digest": "cd501ebbf3a156c202f79d43afc947e541382bcf1790ae0578acaa46f7ceb3b2",
        "glb_sha256": "33e815f7e32e8387ef8836b98b0f4a9a2a963b6aa51d9af654a68e1b0adb8813",
        "glb_bytes": 135972,
        "material_count": 1,
        "pbr_material_count": 1,
        "texture_count": 2,
        "pbr_texture_slot_count": 2,
        "base_normal_orm_texture_slot_count": 2,
    },
    "hssd.static.flip_flops": {
        "receipt_sha256": "01d6ae2367bde870bcb20ff810bad9d3a3326b6a46abaecca7a6f0322100aa9b",
        "receipt_content_digest": "06fe9169444826452814e3c27f848e93ae4fc60f95bdd50151e48eb14af3c3c2",
        "glb_sha256": "53ec1b08331620bb7359ee69cdb61064d6d426c552d9a22d32b7ccdd25b279fc",
        "glb_bytes": 476356,
        "material_count": 4,
        "pbr_material_count": 4,
        "texture_count": 4,
        "pbr_texture_slot_count": 5,
        "base_normal_orm_texture_slot_count": 5,
    },
    "hssd.static.fridge": {
        "receipt_sha256": "c29c4841b3b3b6168ff37594cf03de41dcd9473deb654852767ba3c9a0f22923",
        "receipt_content_digest": "7704cd2c32e4acabe8575b2a482f84e84160a696e1e8f42a94e9cba4f1aaeec1",
        "glb_sha256": "f0074f961bed9453e43b2418d92c5f7a0c4f3b71e53a02ccb6cea0032d6e722b",
        "glb_bytes": 114080,
        "material_count": 4,
        "pbr_material_count": 4,
        "texture_count": 5,
        "pbr_texture_slot_count": 4,
        "base_normal_orm_texture_slot_count": 4,
    },
    "hssd.static.ladder": {
        "receipt_sha256": "0c1688ff33ac0be8a6b35048fc98f30a77801a7970dd52815c17537fa7d9a369",
        "receipt_content_digest": "82c5633e360e29c9ff4a7a2a4735cc23a2ae85be0cfb017b1bffdc061f0458a2",
        "glb_sha256": "2170964ba2782a49ad52a4c81e2b3c4031b2a981cd5b80dcddb91d947e76bcc5",
        "glb_bytes": 54488,
        "material_count": 2,
        "pbr_material_count": 2,
        "texture_count": 3,
        "pbr_texture_slot_count": 2,
        "base_normal_orm_texture_slot_count": 2,
    },
    "hssd.static.laundry_basket": {
        "receipt_sha256": "4bc557bfb2271da49f811fca9db1b5dbd40a44c317f9e5f91269de603546b410",
        "receipt_content_digest": "200b26c6ae91416202cb5f5fb95d00c837ccb864582f234ebcd9b147f921865b",
        "glb_sha256": "1a9349ac74ace26924696c2f1110ebb564aa44179d6cb8fa7c7a0a068c78742c",
        "glb_bytes": 126448,
        "material_count": 1,
        "pbr_material_count": 1,
        "texture_count": 1,
        "pbr_texture_slot_count": 1,
        "base_normal_orm_texture_slot_count": 1,
    },
    "hssd.static.nightstand": {
        "receipt_sha256": "765891983fbea9210fb111b968ed9826a26bf1fe5b46e1d02053a561a22cd151",
        "receipt_content_digest": "ab220caea930934bf900cae347a35fe9bae94cbbbd7ed18ace18be82caac3f1c",
        "glb_sha256": "e9da199bdff4917c2b3f002b9490938e2c1bf897725af269ae476bbda3cdb7e3",
        "glb_bytes": 986164,
        "material_count": 4,
        "pbr_material_count": 4,
        "texture_count": 8,
        "pbr_texture_slot_count": 8,
        "base_normal_orm_texture_slot_count": 8,
    },
    "hssd.static.phone": {
        "receipt_sha256": "6dc4ca65347d8cb5ad186ac7beb3846f15b695b1759be4f5004c1d634a76c2b2",
        "receipt_content_digest": "7ac340c4f192e240c016cc8acd0bca5580721f931406ab627962d6b1901e3760",
        "glb_sha256": "1067d9f95ee4d3ab871953b90a7f31293b2afcbaab6491ad0715b4c7cbf447d2",
        "glb_bytes": 662784,
        "material_count": 6,
        "pbr_material_count": 6,
        "texture_count": 3,
        "pbr_texture_slot_count": 3,
        "base_normal_orm_texture_slot_count": 3,
    },
    "hssd.static.plant": {
        "receipt_sha256": "de4a5f9a4acfd729bdf9c912ff231de6b860f07d63e5bec0551248b928a919d3",
        "receipt_content_digest": "f172517597385760ec5108394e81bc496c51ffe2755574b9cf3200cf87790feb",
        "glb_sha256": "e3bfa6ce4910d6f3a32f579314ed60d4f82abd569ca848c4df80a70d690762d8",
        "glb_bytes": 621400,
        "material_count": 5,
        "pbr_material_count": 5,
        "texture_count": 4,
        "pbr_texture_slot_count": 4,
        "base_normal_orm_texture_slot_count": 4,
    },
    "hssd.static.rolling_chair": {
        "receipt_sha256": "85d4df36ddda0089e1d1ca0c502a5099471118dcda702d5b05493097bbb0e8e6",
        "receipt_content_digest": "961b8c243ab3db85786f7785fa28829724c00fa8cf0f4b32a07c2e74dfa955c7",
        "glb_sha256": "193236ff8a5cea6342b1fef968c1a602aa71a8ee7a766e0d37549abead7e0663",
        "glb_bytes": 1498888,
        "material_count": 4,
        "pbr_material_count": 4,
        "texture_count": 1,
        "pbr_texture_slot_count": 1,
        "base_normal_orm_texture_slot_count": 1,
    },
    "hssd.static.shoe_bench": {
        "receipt_sha256": "fea85b14b712855a7bb10bb3308fc1ed02baff61eeeb29b49f8f0f4d29c5c1a2",
        "receipt_content_digest": "a102cc1549244787631e85a2a6448eae0a73755b0ef6e9375771e50076729289",
        "glb_sha256": "05b3ef803d9ed0a2586e628c35ae48d1cff6a81fd3b7022a8509b4adf391ce69",
        "glb_bytes": 252644,
        "material_count": 2,
        "pbr_material_count": 2,
        "texture_count": 3,
        "pbr_texture_slot_count": 3,
        "base_normal_orm_texture_slot_count": 3,
    },
    "hssd.static.sofa": {
        "receipt_sha256": "735dd4c82d9fe2d312a6f86f83e4f466ea8ec95b13edf00c9f99ac30b8f5ba9b",
        "receipt_content_digest": "6a3aab176f8eb7d796744cba8fec956d7110c9e006e0b5b981258ebf2b3b568e",
        "glb_sha256": "c322d9e3a0dcef0d2e0efd7e5f4227779afcecc8c388a49a11c2fae0e2811288",
        "glb_bytes": 703628,
        "material_count": 2,
        "pbr_material_count": 2,
        "texture_count": 2,
        "pbr_texture_slot_count": 2,
        "base_normal_orm_texture_slot_count": 2,
    },
    "hssd.static.storage_box": {
        "receipt_sha256": "57eb07759957a6467737c6ffe511bb8f20e0472f1051fe500fcdd72ce2bca8b6",
        "receipt_content_digest": "1dd4d9c93ceadf6ac40b56b891a97c8560a70ca3357695ee710def2611314c89",
        "glb_sha256": "08000b460e38df8fc87de5118adbbe585200cb1ef42a73c7a9f08e3a08b46a8b",
        "glb_bytes": 518340,
        "material_count": 3,
        "pbr_material_count": 3,
        "texture_count": 2,
        "pbr_texture_slot_count": 2,
        "base_normal_orm_texture_slot_count": 2,
    },
    "hssd.static.stove": {
        "receipt_sha256": "71e8ddeaa25450fe2a5d9f9c72b7d1c039c0a716fa309f8f6d16426820efa061",
        "receipt_content_digest": "03e89731db3a331d16320a3b7490bb40f421996139973b79f122b425e9729250",
        "glb_sha256": "08fa0a8a3d2c0d8d4c718db0208fddc81acd17581cdd8e033c13c4c762f0ffdd",
        "glb_bytes": 1143068,
        "material_count": 6,
        "pbr_material_count": 6,
        "texture_count": 9,
        "pbr_texture_slot_count": 7,
        "base_normal_orm_texture_slot_count": 7,
    },
    "hssd.static.washer": {
        "receipt_sha256": "f490e0b131ed41a568c398971d487dc029b6604e2f62e8c747b79a1142d8bed9",
        "receipt_content_digest": "1dbf949890f215ece5bf9517fab14a4e1f9682d8a90a93ce50f01320622deeef",
        "glb_sha256": "367abd5b4e6ed068c227c46b6394c3c5a2d759930c4a0fe4d790aa863490c973",
        "glb_bytes": 231684,
        "material_count": 5,
        "pbr_material_count": 5,
        "texture_count": 7,
        "pbr_texture_slot_count": 4,
        "base_normal_orm_texture_slot_count": 4,
    },
}
EXPECTED_ASSET_IDS = tuple(sorted(EXPECTED_ASSET_PINS))

EXECUTION_KEYS = {
    "schema_version",
    "attempt_root",
    "project_file",
    "project_sha256",
    "content_namespace",
    "source_run",
    "asset_bindings",
    "compatibility",
    "import_mode",
    "scripts",
    "import_receipt",
    "policy",
}
SOURCE_RUN_KEYS = {
    "path",
    "build_plan_sha256",
    "build_result_sha256",
    "scene_plan_sha256",
}
SCRIPT_KEYS = {"path", "sha256"}
SOURCE_BINDING_KEYS = {
    "source_asset_id",
    "semantic_category",
    "glb_relative_path",
    "glb_sha256",
    "glb_bytes",
    "receipt_relative_path",
    "receipt_sha256",
    "receipt_content_digest",
    "material_count",
    "pbr_material_count",
    "texture_count",
    "pbr_texture_slot_count",
    "base_normal_orm_texture_slot_count",
    "target_object_path",
}
DERIVATIVE_BINDING_KEYS = {
    "source_asset_id",
    "glb_path",
    "glb_sha256",
    "glb_bytes",
    "receipt_path",
    "receipt_sha256",
    "receipt_content_digest",
    "compatibility_status",
    "blocks_full_material_fidelity",
}
EXECUTION_BINDING_KEYS = {"source", "derivative"}
COMPATIBILITY_EXECUTION_KEYS = {
    "schema_version",
    "rule_id",
    "aggregate_receipt",
    "aggregate_receipt_sha256",
    "aggregate_receipt_content_digest",
    "status",
    "counts",
    "blocking_asset_ids",
    "promotable",
    "full_material_fidelity",
    "diagnostic_only",
}
COMPATIBILITY_AGGREGATE_KEYS = {
    "schema_version",
    "status",
    "accepted_as_visual_evidence",
    "full_material_fidelity",
    "promotable",
    "diagnostic_only",
    "asset_count",
    "source_asset_ids",
    "transform",
    "counts",
    "blocking_asset_ids",
    "assets",
    "source_license_scope",
    "content_digest",
}
COMPATIBILITY_AGGREGATE_ASSET_KEYS = {
    "source_asset_id",
    "source_sha256",
    "source_bytes",
    "derivative_relative_path",
    "derivative_sha256",
    "derivative_bytes",
    "receipt_relative_path",
    "receipt_sha256",
    "receipt_content_digest",
    "compatibility_status",
    "blocks_full_material_fidelity",
}
EXECUTION_POLICY = {
    "append_only_namespace": True,
    "quarantine_on_failure": True,
    "replace_existing": False,
    "visual_only": True,
    "component_collision_profile": "NoCollision",
    "can_ever_affect_navigation": False,
    "articulation": "blocked_until_validated",
    "license_scope": "private_noncommercial_research_only",
    "public_payload_distribution": "prohibited",
    "compatibility_derivative_required": True,
    "full_material_fidelity_promotion": "blocked_active_dual_material_conflict",
}
SOURCE_LICENSE_SCOPE = {
    "commercial_release": "blocked",
    "public_payload_distribution": "prohibited",
    "use_class": "private_noncommercial_research_only",
}
NAMESPACE_RE = re.compile(
    r"^/Game/VISTA/PlayableHome/[A-Za-z0-9_]{1,64}/HSSDPrivateResearch$"
)
SAFE_UE_NAME = re.compile(r"^[A-Za-z0-9_]{1,128}$")
SIMPLE_COLLISION_ELEMENT_PROPERTIES = (
    "box_elems",
    "sphere_elems",
    "sphyl_elems",
    "convex_elems",
    "tapered_capsule_elems",
    "level_set_elems",
    "ml_level_set_elems",
    "skinned_level_set_elems",
    "skinned_triangle_mesh_elems",
)


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        base.require(key not in result, "JSON contains a duplicate key: " + key)
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise RuntimeError("JSON contains a non-finite constant: " + value)


def _strict_json(raw: bytes, label: str) -> dict[str, Any]:
    try:
        text = raw.decode("utf-8")
        value = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, ValueError, TypeError) as exc:
        raise RuntimeError(label + " is not strict UTF-8 JSON") from exc
    base.require(isinstance(value, dict), label + " root must be an object")
    return value


def _exact_keys(value: Any, expected: set[str], label: str) -> None:
    base.require(
        isinstance(value, dict) and set(value) == expected,
        label + " fields differ from the closed contract",
    )


def _canonical_nonsymlink_path(value: Any, label: str) -> str:
    base.require(
        isinstance(value, str) and os.path.isabs(value), label + " must be absolute"
    )
    lexical = os.path.normpath(value).replace("\\", "/")
    resolved = base.canonical_path(value)
    base.require(lexical == resolved, label + " uses a symlink or non-canonical path")
    return resolved


def _source_child(root: str, relative: Any, label: str) -> str:
    base.require(isinstance(relative, str) and relative, label + " path is invalid")
    pure = pathlib.PurePosixPath(relative)
    base.require(
        not pure.is_absolute()
        and pure.as_posix() == relative
        and all(part not in {"", ".", ".."} for part in pure.parts),
        label + " path is not a canonical relative path",
    )
    lexical = os.path.normpath(os.path.join(root, *pure.parts)).replace("\\", "/")
    resolved = base.canonical_path(lexical)
    base.require(
        lexical == resolved and resolved.startswith(root + "/"),
        label + " escapes the source root or uses a symlink",
    )
    return resolved


def _read_regular_file(path: str, label: str) -> tuple[bytes, os.stat_result]:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise RuntimeError(label + " cannot be opened without following links") from exc
    try:
        before = os.fstat(descriptor)
        base.require(stat.S_ISREG(before.st_mode), label + " is not a regular file")
        chunks = []
        while True:
            block = os.read(descriptor, 1024 * 1024)
            if not block:
                break
            chunks.append(block)
        after = os.fstat(descriptor)
        identity_before = (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
        )
        identity_after = (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        )
        base.require(
            identity_before == identity_after, label + " changed while reading"
        )
        raw = b"".join(chunks)
        base.require(
            len(raw) == before.st_size, label + " byte count changed while reading"
        )
        return raw, before
    finally:
        os.close(descriptor)


def _load_pinned_json(path: str, expected_sha: str, label: str) -> dict[str, Any]:
    raw, _ = _read_regular_file(path, label)
    actual_sha = hashlib.sha256(raw).hexdigest()
    base.require(
        actual_sha == base.require_sha(expected_sha, label),
        label + " byte digest mismatch",
    )
    return _strict_json(raw, label)


def _content_digest(value: dict[str, Any]) -> str:
    body = dict(value)
    body.pop("content_digest", None)
    return hashlib.sha256(base.canonical_json(body)).hexdigest()


def _require_document_digest(value: dict[str, Any], expected: str, label: str) -> None:
    digest = base.require_sha(value.get("content_digest"), label + " content")
    base.require(digest == expected, label + " pinned content digest mismatch")
    base.require(digest == _content_digest(value), label + " content digest is invalid")


def hssd_asset_name(source_asset_id: str) -> str:
    base.require(source_asset_id in EXPECTED_ASSET_PINS, "HSSD asset ID is not pinned")
    value = re.sub(r"[^A-Za-z0-9_]", "_", source_asset_id)
    base.require(
        SAFE_UE_NAME.fullmatch(value) is not None,
        "HSSD asset ID cannot form a safe UE name",
    )
    return value


def derived_hssd_asset_path(namespace: str, source_asset_id: str) -> str:
    base.require(
        isinstance(namespace, str) and NAMESPACE_RE.fullmatch(namespace) is not None,
        "HSSD content namespace is invalid",
    )
    name = hssd_asset_name(source_asset_id)
    return namespace + "/Assets/" + name + "/" + name + "." + name


def property_or_none(value: Any, name: str) -> Any:
    try:
        return value.get_editor_property(name)
    except Exception:
        return None


def simple_collision_count(mesh: Any) -> int:
    body_setup = property_or_none(mesh, "body_setup")
    base.require(body_setup is not None, "HSSD StaticMesh BodySetup is unavailable")
    aggregate = property_or_none(body_setup, "agg_geom")
    base.require(aggregate is not None, "HSSD aggregate collision is unavailable")
    total = 0
    for name in SIMPLE_COLLISION_ELEMENT_PROPERTIES:
        values = property_or_none(aggregate, name)
        base.require(values is not None, "HSSD collision array is unavailable: " + name)
        total += len(values)
    return total


def clear_simple_collision(mesh: Any) -> None:
    """Clear every known UE 5.7 aggregate shape without editor subsystems."""

    body_setup = property_or_none(mesh, "body_setup")
    base.require(body_setup is not None, "HSSD StaticMesh BodySetup is unavailable")
    aggregate = property_or_none(body_setup, "agg_geom")
    base.require(aggregate is not None, "HSSD aggregate collision is unavailable")
    for name in SIMPLE_COLLISION_ELEMENT_PROPERTIES:
        values = property_or_none(aggregate, name)
        base.require(values is not None, "HSSD collision array is unavailable: " + name)
        aggregate.set_editor_property(name, [])
    body_setup.set_editor_property("agg_geom", aggregate)
    base.require(
        simple_collision_count(mesh) == 0, "HSSD mesh retained simple collision"
    )


def _verify_glb(path: str, pin: dict[str, Any], label: str) -> None:
    raw, metadata = _read_regular_file(path, label)
    base.require(metadata.st_size == pin["glb_bytes"], label + " byte count mismatch")
    base.require(
        hashlib.sha256(raw).hexdigest() == pin["glb_sha256"],
        label + " byte digest mismatch",
    )
    base.require(len(raw) >= 12 and raw[:4] == b"glTF", label + " GLB magic is invalid")
    version, declared_size = struct.unpack("<II", raw[4:12])
    base.require(version == 2, label + " must be GLB version 2")
    base.require(declared_size == len(raw), label + " declared GLB size differs")


def _validate_document_identities(
    build_plan: dict[str, Any],
    build_result: dict[str, Any],
    scene_plan: dict[str, Any],
) -> None:
    base.require(
        build_plan.get("schema_version") == BUILD_PLAN_SCHEMA
        and build_plan.get("mode") == "execute"
        and build_plan.get("status") == "ready_for_explicit_blender_execution"
        and build_plan.get("accepted") is False
        and build_plan.get("will_write") is True
        and build_plan.get("will_execute_blender") is True,
        "R5 build plan identity or execution state differs",
    )
    profile = build_plan.get("profile")
    base.require(
        isinstance(profile, dict)
        and profile.get("schema_version") == PROFILE_SCHEMA
        and profile.get("profile_id") == PROFILE_ID
        and profile.get("content_digest") == PROFILE_CONTENT_DIGEST,
        "R5 profile identity differs",
    )
    license_scope = build_plan.get("license_scope")
    base.require(
        isinstance(license_scope, dict)
        and all(
            license_scope.get(key) == value
            for key, value in SOURCE_LICENSE_SCOPE.items()
        ),
        "R5 private non-commercial license scope differs",
    )
    base.require(
        build_plan.get("network_policy")
        == {
            "network_fallback": "disabled",
            "network_resolution": "not_used",
            "proxy_environment_forwarding": "disabled",
        },
        "R5 network policy differs",
    )
    normalization = build_plan.get("normalization_policy")
    base.require(
        normalization
        == {
            "blender_version": "4.5.8",
            "maximum_axis_scale_anisotropy": 2.75,
            "one_primary_mesh_per_source": True,
            "origin_policy": "footprint_center_bottom_z_zero",
            "texture_transport": "KHR_texture_basisu_to_core_png",
        },
        "R5 normalization policy differs",
    )
    base.require(
        build_result.get("schema_version") == BUILD_RESULT_SCHEMA
        and build_result.get("status")
        == "assets_materialized_scene_plan_only_not_rendered"
        and build_result.get("accepted") is False
        and build_result.get("asset_count") == 26
        and build_result.get("scene_assembly_status") == "plan_only_not_assembled"
        and build_result.get("render_status") == "not_rendered"
        and build_result.get("articulation_status")
        == "pending_blocked_until_validated",
        "R5 build result state differs",
    )
    base.require(
        scene_plan.get("schema_version") == SCENE_PLAN_SCHEMA
        and scene_plan.get("profile_id") == PROFILE_ID
        and scene_plan.get("profile_content_digest") == PROFILE_CONTENT_DIGEST
        and scene_plan.get("house_id") == "home.r1"
        and scene_plan.get("house_revision") == "vista_playable_home_r1"
        and scene_plan.get("coordinate_frame") == "room_local_m"
        and scene_plan.get("placement_count") == 60
        and scene_plan.get("assembly_status") == "plan_only_not_assembled"
        and scene_plan.get("render_status") == "not_rendered"
        and scene_plan.get("accepted_as_visual_evidence") is False
        and scene_plan.get("interaction_policy")
        == {
            "articulation": "pending_blocked_until_validated",
            "static_visuals": (
                "presentation_only_hidden_r1_proxy_remains_authoritative"
            ),
        },
        "R5 scene plan identity or visual-only policy differs",
    )
    plan_digest = EXPECTED_CONTENT_DIGESTS["build-plan.json"]
    scene_digest = EXPECTED_CONTENT_DIGESTS["scene-plan.json"]
    base.require(
        build_result.get("build_plan_content_digest") == plan_digest
        and build_result.get("scene_plan_content_digest") == scene_digest
        and build_result.get("profile_content_digest") == PROFILE_CONTENT_DIGEST,
        "R5 build result source links differ",
    )
    scene_record = build_plan.get("scene_plan")
    base.require(
        isinstance(scene_record, dict)
        and scene_record.get("schema_version") == SCENE_PLAN_SCHEMA
        and scene_record.get("path") == "scene-plan.json"
        and scene_record.get("placement_count") == 60
        and scene_record.get("content_digest") == scene_digest,
        "R5 build plan scene link differs",
    )


def _closed_asset_ids(
    build_plan: dict[str, Any],
    build_result: dict[str, Any],
    scene_plan: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    jobs = build_plan.get("asset_jobs")
    results = build_result.get("assets")
    placements = scene_plan.get("placements")
    base.require(isinstance(jobs, list) and len(jobs) == 26, "R5 needs 26 asset jobs")
    base.require(
        isinstance(results, list) and len(results) == 26,
        "R5 needs 26 result assets",
    )
    base.require(
        isinstance(placements, list) and len(placements) == 60,
        "R5 needs 60 scene placements",
    )
    job_ids = [item.get("source_asset_id") for item in jobs if isinstance(item, dict)]
    result_ids = [
        item.get("source_asset_id") for item in results if isinstance(item, dict)
    ]
    placement_ids = [
        item.get("source_asset_id") for item in placements if isinstance(item, dict)
    ]
    expected = list(EXPECTED_ASSET_IDS)
    base.require(
        job_ids == expected, "R5 asset jobs are not the exact sorted closed set"
    )
    base.require(
        result_ids == expected, "R5 result assets are not the exact sorted closed set"
    )
    base.require(
        sorted(set(placement_ids)) == expected,
        "R5 placements do not use the exact closed asset set",
    )
    semantic_targets = [
        item.get("semantic_target_id")
        for item in placements
        if isinstance(item, dict) and item.get("semantic_target_id") is not None
    ]
    base.require(len(semantic_targets) == 19, "R5 semantic target count differs")
    base.require(
        len(set(item.get("instance_id") for item in placements)) == 60,
        "R5 placement instance IDs are duplicated",
    )
    closed_world = build_plan.get("closed_world")
    base.require(
        isinstance(closed_world, dict)
        and closed_world.get("source_count") == 26
        and closed_world.get("source_asset_ids") == expected
        and closed_world.get("placement_count") == 60
        and closed_world.get("unaccounted_source_asset_ids") == []
        and closed_world.get("unaccounted_placement_ids") == [],
        "R5 closed-world ledger differs",
    )
    return (
        {item["source_asset_id"]: item for item in jobs},
        {item["source_asset_id"]: item for item in results},
    )


def _validate_asset_receipt(
    receipt: dict[str, Any],
    asset_id: str,
    pin: dict[str, Any],
    job: dict[str, Any],
    result: dict[str, Any],
) -> None:
    base.require(
        receipt.get("schema_version") == ASSET_RECEIPT_SCHEMA
        and receipt.get("content_digest") == _content_digest(receipt)
        and receipt.get("content_digest") == pin["receipt_content_digest"]
        and receipt.get("source_asset_id") == asset_id
        and receipt.get("semantic_category") == job.get("semantic_category")
        and receipt.get("model_id") == job.get("model_id")
        and receipt.get("output_relpath") == "assets/" + asset_id + ".glb"
        and receipt.get("output_sha256") == pin["glb_sha256"]
        and receipt.get("output_bytes") == pin["glb_bytes"]
        and receipt.get("build_plan_content_digest")
        == EXPECTED_CONTENT_DIGESTS["build-plan.json"]
        and receipt.get("profile_content_digest") == PROFILE_CONTENT_DIGEST
        and receipt.get("texture_transport") == "KHR_texture_basisu_to_core_png"
        and receipt.get("source_basisu_required") is True
        and receipt.get("output_basisu_required") is False
        and receipt.get("visual_role") == "static_presentation_shell"
        and receipt.get("interaction_authority") == "none_static_joined_glb"
        and receipt.get("accepted_as_interactive_asset") is False
        and receipt.get("status") == "normalized_pbr_glb_built_for_private_research",
        "R5 asset receipt identity or safety policy differs: " + asset_id,
    )
    inspection = receipt.get("inspection")
    base.require(isinstance(inspection, dict), "R5 inspection is missing: " + asset_id)
    for key in (
        "material_count",
        "pbr_material_count",
        "texture_count",
        "pbr_texture_slot_count",
        "base_normal_orm_texture_slot_count",
    ):
        base.require(
            inspection.get(key) == pin[key],
            "R5 receipt inspection pin differs for " + asset_id + ": " + key,
        )
    base.require(
        inspection.get("mesh_count") == 1
        and inspection.get("all_primitives_material_bound") == 1
        and inspection.get("basisu_required") == 0
        and pin["material_count"] >= 1
        and pin["pbr_material_count"] == pin["material_count"]
        and pin["texture_count"] >= 1
        and pin["pbr_texture_slot_count"] >= 1
        and pin["base_normal_orm_texture_slot_count"] >= 1,
        "R5 normalized PBR receipt gate failed: " + asset_id,
    )
    base.require(
        result
        == {
            "source_asset_id": asset_id,
            "glb_relpath": "assets/" + asset_id + ".glb",
            "receipt_relpath": "receipts/" + asset_id + ".json",
            "output_sha256": pin["glb_sha256"],
            "receipt_content_digest": pin["receipt_content_digest"],
        },
        "R5 build-result asset record differs: " + asset_id,
    )


def validate_source_run(source_root: str, namespace: str) -> list[dict[str, Any]]:
    """Validate exact R5 source bytes and return deterministic UE bindings."""

    root = _canonical_nonsymlink_path(source_root, "R5 source root")
    base.require(os.path.isdir(root), "R5 source root is missing")
    base.require(
        NAMESPACE_RE.fullmatch(namespace) is not None,
        "HSSD content namespace is invalid",
    )
    documents: dict[str, dict[str, Any]] = {}
    for filename in ("build-plan.json", "build-result.json", "scene-plan.json"):
        path = _source_child(root, filename, "R5 " + filename)
        documents[filename] = _load_pinned_json(
            path, EXPECTED_DOCUMENT_SHA256[filename], "R5 " + filename
        )
        _require_document_digest(
            documents[filename], EXPECTED_CONTENT_DIGESTS[filename], "R5 " + filename
        )
    build_plan = documents["build-plan.json"]
    build_result = documents["build-result.json"]
    scene_plan = documents["scene-plan.json"]
    _validate_document_identities(build_plan, build_result, scene_plan)
    jobs, results = _closed_asset_ids(build_plan, build_result, scene_plan)

    expected_asset_names = {asset_id + ".glb" for asset_id in EXPECTED_ASSET_IDS}
    expected_receipt_names = {asset_id + ".json" for asset_id in EXPECTED_ASSET_IDS}
    assets_dir = _source_child(root, "assets", "R5 assets directory")
    receipts_dir = _source_child(root, "receipts", "R5 receipts directory")
    base.require(os.path.isdir(assets_dir), "R5 assets directory is missing")
    base.require(os.path.isdir(receipts_dir), "R5 receipts directory is missing")
    base.require(
        set(os.listdir(assets_dir)) == expected_asset_names,
        "R5 assets directory is not the exact 26-file closed set",
    )
    base.require(
        set(os.listdir(receipts_dir)) == expected_receipt_names,
        "R5 receipts directory is not the exact 26-file closed set",
    )

    bindings = []
    for asset_id in EXPECTED_ASSET_IDS:
        pin = EXPECTED_ASSET_PINS[asset_id]
        job = jobs[asset_id]
        result = results[asset_id]
        glb_relative = "assets/" + asset_id + ".glb"
        receipt_relative = "receipts/" + asset_id + ".json"
        base.require(
            job.get("output")
            == {
                "glb_relpath": glb_relative,
                "receipt_relpath": receipt_relative,
            }
            and job.get("visual_role") == "static_presentation_shell"
            and job.get("interaction_authority") == "none_static_joined_glb"
            and job.get("texture_transport")
            == {
                "required_mode": "KHR_texture_basisu_to_core_png",
                "source_basisu_required": True,
                "output_basisu_required": False,
                "output_image_transport": "embedded_core_png",
            },
            "R5 asset job output or visual-only policy differs: " + asset_id,
        )
        glb_path = _source_child(root, glb_relative, "R5 GLB " + asset_id)
        receipt_path = _source_child(root, receipt_relative, "R5 receipt " + asset_id)
        _verify_glb(glb_path, pin, "R5 GLB " + asset_id)
        receipt = _load_pinned_json(
            receipt_path, pin["receipt_sha256"], "R5 receipt " + asset_id
        )
        _validate_asset_receipt(receipt, asset_id, pin, job, result)
        bindings.append(
            {
                "source_asset_id": asset_id,
                "semantic_category": job["semantic_category"],
                "glb_relative_path": glb_relative,
                "glb_sha256": pin["glb_sha256"],
                "glb_bytes": pin["glb_bytes"],
                "receipt_relative_path": receipt_relative,
                "receipt_sha256": pin["receipt_sha256"],
                "receipt_content_digest": pin["receipt_content_digest"],
                "material_count": pin["material_count"],
                "pbr_material_count": pin["pbr_material_count"],
                "texture_count": pin["texture_count"],
                "pbr_texture_slot_count": pin["pbr_texture_slot_count"],
                "base_normal_orm_texture_slot_count": pin[
                    "base_normal_orm_texture_slot_count"
                ],
                "target_object_path": derived_hssd_asset_path(namespace, asset_id),
            }
        )
    return bindings


def binding_source_path(execution: dict[str, Any], binding: dict[str, Any]) -> str:
    source = binding["source"] if "source" in binding else binding
    root = _canonical_nonsymlink_path(execution["source_run"]["path"], "R5 source root")
    return _source_child(
        root,
        source["glb_relative_path"],
        "R5 GLB " + source["source_asset_id"],
    )


def verify_binding_source(execution: dict[str, Any], binding: dict[str, Any]) -> str:
    """Revalidate source and compatibility bytes, then return derivative input."""

    source = binding["source"]
    derivative = binding["derivative"]
    source_path = binding_source_path(execution, binding)
    pin = EXPECTED_ASSET_PINS[source["source_asset_id"]]
    base.require(
        source["glb_sha256"] == pin["glb_sha256"], "binding R5 GLB pin differs"
    )
    _verify_glb(source_path, pin, "R5 GLB " + source["source_asset_id"])
    derivative_raw, metadata = _read_regular_file(
        derivative["glb_path"], "HSSD compatibility GLB " + source["source_asset_id"]
    )
    base.require(
        metadata.st_size == derivative["glb_bytes"]
        and hashlib.sha256(derivative_raw).hexdigest() == derivative["glb_sha256"],
        "HSSD compatibility derivative pin differs",
    )
    return derivative["glb_path"]


def _validate_compatibility_execution(
    execution: dict[str, Any],
    attempt_root: str,
    source_bindings: list[dict[str, Any]],
    transform_script_sha256: str,
) -> list[dict[str, Any]]:
    """Independently re-derive every attempt-local GLB and aggregate receipt."""

    compatibility_execution = execution.get("compatibility")
    _exact_keys(
        compatibility_execution,
        COMPATIBILITY_EXECUTION_KEYS,
        "HSSD compatibility execution",
    )
    aggregate_path = base.safe_attempt_child(
        compatibility_execution["aggregate_receipt"],
        attempt_root,
        "HSSD compatibility aggregate receipt",
    )
    aggregate_path = _canonical_nonsymlink_path(
        aggregate_path, "HSSD compatibility aggregate receipt"
    )
    compatibility_root = _canonical_nonsymlink_path(
        os.path.join(attempt_root, "compatibility"), "HSSD compatibility root"
    )
    base.require(
        os.path.dirname(aggregate_path) == compatibility_root
        and os.path.basename(aggregate_path) == "aggregate-receipt.json",
        "HSSD compatibility aggregate path differs",
    )
    expected_asset_names = {asset_id + ".glb" for asset_id in EXPECTED_ASSET_IDS}
    expected_receipt_names = {asset_id + ".json" for asset_id in EXPECTED_ASSET_IDS}
    assets_root = _source_child(
        compatibility_root, "assets", "HSSD compatibility assets"
    )
    receipts_root = _source_child(
        compatibility_root, "receipts", "HSSD compatibility receipts"
    )
    base.require(
        set(os.listdir(compatibility_root))
        == {"aggregate-receipt.json", "assets", "receipts"}
        and set(os.listdir(assets_root)) == expected_asset_names
        and set(os.listdir(receipts_root)) == expected_receipt_names,
        "HSSD compatibility attempt inventory is not the exact closed set",
    )
    aggregate_sha = base.require_sha(
        compatibility_execution["aggregate_receipt_sha256"],
        "HSSD compatibility aggregate receipt",
    )
    aggregate = _load_pinned_json(
        aggregate_path, aggregate_sha, "HSSD compatibility aggregate receipt"
    )
    _exact_keys(
        aggregate,
        COMPATIBILITY_AGGREGATE_KEYS,
        "HSSD compatibility aggregate receipt",
    )
    _require_document_digest(
        aggregate,
        compatibility_execution["aggregate_receipt_content_digest"],
        "HSSD compatibility aggregate receipt",
    )
    base.require(
        aggregate.get("schema_version") == COMPATIBILITY_AGGREGATE_SCHEMA
        and aggregate.get("status") == COMPATIBILITY_STATUS
        and aggregate.get("accepted_as_visual_evidence") is False
        and aggregate.get("full_material_fidelity") is False
        and aggregate.get("promotable") is False
        and aggregate.get("diagnostic_only") is True
        and aggregate.get("asset_count") == 26
        and aggregate.get("source_asset_ids") == list(EXPECTED_ASSET_IDS)
        and aggregate.get("counts") == EXPECTED_COMPATIBILITY_COUNTS
        and aggregate.get("blocking_asset_ids") == ["hssd.static.washer"]
        and aggregate.get("source_license_scope") == SOURCE_LICENSE_SCOPE
        and aggregate.get("transform")
        == {
            "rule_id": compatibility.RULE_ID,
            "script_sha256": transform_script_sha256,
        },
        "HSSD compatibility aggregate identity or promotion state differs",
    )
    aggregate_assets = aggregate.get("assets")
    base.require(
        isinstance(aggregate_assets, list) and len(aggregate_assets) == 26,
        "HSSD compatibility aggregate asset count differs",
    )

    expected_bindings: list[dict[str, Any]] = []
    receipts: list[dict[str, Any]] = []
    for source, aggregate_asset in zip(source_bindings, aggregate_assets):
        asset_id = source["source_asset_id"]
        _exact_keys(
            aggregate_asset,
            COMPATIBILITY_AGGREGATE_ASSET_KEYS,
            "HSSD compatibility aggregate asset " + asset_id,
        )
        derivative_relative = "assets/" + asset_id + ".glb"
        receipt_relative = "receipts/" + asset_id + ".json"
        derivative_path = _source_child(
            compatibility_root,
            derivative_relative,
            "HSSD compatibility derivative " + asset_id,
        )
        derivative_receipt_path = _source_child(
            compatibility_root,
            receipt_relative,
            "HSSD compatibility receipt " + asset_id,
        )
        source_path = _source_child(
            execution["source_run"]["path"],
            source["glb_relative_path"],
            "R5 GLB " + asset_id,
        )
        source_raw, source_metadata = _read_regular_file(
            source_path, "R5 GLB " + asset_id
        )
        derivative_raw, derivative_metadata = _read_regular_file(
            derivative_path, "HSSD compatibility derivative " + asset_id
        )
        receipt_sha = base.require_sha(
            aggregate_asset["receipt_sha256"],
            "HSSD compatibility receipt " + asset_id,
        )
        receipt = _load_pinned_json(
            derivative_receipt_path,
            receipt_sha,
            "HSSD compatibility receipt " + asset_id,
        )
        compatibility.validate_derivation(
            source_raw,
            derivative_raw,
            receipt,
            source_asset_id=asset_id,
            transform_script_sha256=transform_script_sha256,
        )
        base.require(
            source_metadata.st_size == source["glb_bytes"]
            and hashlib.sha256(source_raw).hexdigest() == source["glb_sha256"]
            and derivative_metadata.st_size == receipt["output_bytes"]
            and hashlib.sha256(derivative_raw).hexdigest() == receipt["output_sha256"]
            and aggregate_asset
            == {
                "source_asset_id": asset_id,
                "source_sha256": source["glb_sha256"],
                "source_bytes": source["glb_bytes"],
                "derivative_relative_path": derivative_relative,
                "derivative_sha256": receipt["output_sha256"],
                "derivative_bytes": receipt["output_bytes"],
                "receipt_relative_path": receipt_relative,
                "receipt_sha256": receipt_sha,
                "receipt_content_digest": receipt["content_digest"],
                "compatibility_status": receipt["status"],
                "blocks_full_material_fidelity": receipt[
                    "blocks_full_material_fidelity"
                ],
            },
            "HSSD compatibility aggregate asset binding differs: " + asset_id,
        )
        derivative_binding = {
            "source_asset_id": asset_id,
            "glb_path": derivative_path,
            "glb_sha256": receipt["output_sha256"],
            "glb_bytes": receipt["output_bytes"],
            "receipt_path": derivative_receipt_path,
            "receipt_sha256": receipt_sha,
            "receipt_content_digest": receipt["content_digest"],
            "compatibility_status": receipt["status"],
            "blocks_full_material_fidelity": receipt["blocks_full_material_fidelity"],
        }
        expected_bindings.append({"source": source, "derivative": derivative_binding})
        receipts.append(receipt)

    counts = {
        "asset_count": len(receipts),
        "removed_noop_transmission": sum(
            len(receipt["removed_noop_transmission"]) for receipt in receipts
        ),
        "retained_active_transmission": sum(
            len(receipt["retained_active_transmission"]) for receipt in receipts
        ),
        "retained_active_dual_conflicts": sum(
            len(receipt["retained_active_dual_conflicts"]) for receipt in receipts
        ),
        "blocking_asset_count": sum(
            receipt["blocks_full_material_fidelity"] for receipt in receipts
        ),
    }
    blocking_asset_ids = [
        receipt["source_asset_id"]
        for receipt in receipts
        if receipt["blocks_full_material_fidelity"]
    ]
    base.require(
        counts == EXPECTED_COMPATIBILITY_COUNTS
        and blocking_asset_ids == ["hssd.static.washer"]
        and compatibility_execution
        == {
            "schema_version": COMPATIBILITY_AGGREGATE_SCHEMA,
            "rule_id": compatibility.RULE_ID,
            "aggregate_receipt": aggregate_path,
            "aggregate_receipt_sha256": aggregate_sha,
            "aggregate_receipt_content_digest": aggregate["content_digest"],
            "status": COMPATIBILITY_STATUS,
            "counts": counts,
            "blocking_asset_ids": blocking_asset_ids,
            "promotable": False,
            "full_material_fidelity": False,
            "diagnostic_only": True,
        },
        "HSSD compatibility corpus or execution disposition differs",
    )
    return expected_bindings


def _load_execution_json(path: str, expected_sha: str) -> dict[str, Any]:
    return _load_pinned_json(path, expected_sha, "HSSD execution manifest")


def load_hssd_execution(
    script_kind: str, script_file: str
) -> tuple[dict[str, Any], str, str, list[dict[str, Any]]]:
    """Load one exact execution and revalidate all 26 source artifacts."""

    base.require(script_kind == "import", "unknown HSSD commandlet script kind")
    manifest_value = os.environ.get(EXECUTION_ENV, "")
    manifest_path = _canonical_nonsymlink_path(
        manifest_value, "HSSD execution manifest"
    )
    expected_sha = base.require_sha(
        os.environ.get(EXECUTION_SHA_ENV, ""), "HSSD execution manifest"
    )
    execution = _load_execution_json(manifest_path, expected_sha)
    _exact_keys(execution, EXECUTION_KEYS, "HSSD execution")
    base.require(
        execution.get("schema_version") == EXECUTION_SCHEMA,
        "HSSD execution schema differs",
    )
    base.require(
        execution.get("policy") == EXECUTION_POLICY, "HSSD execution policy differs"
    )

    attempt_root = _canonical_nonsymlink_path(
        execution["attempt_root"], "HSSD attempt root"
    )
    base.require(os.path.isdir(attempt_root), "HSSD attempt root is missing")
    base.safe_attempt_child(manifest_path, attempt_root, "HSSD execution manifest")
    project = base.safe_attempt_child(
        execution["project_file"], attempt_root, "HSSD project"
    )
    project = _canonical_nonsymlink_path(project, "HSSD project")
    project_sha = base.require_sha(execution["project_sha256"], "HSSD project")
    project_raw, _ = _read_regular_file(project, "HSSD project")
    base.require(
        hashlib.sha256(project_raw).hexdigest() == project_sha,
        "HSSD project pin mismatch",
    )
    base.require(
        base.canonical_path(os.environ.get(PROJECT_ENV, project)) == project,
        "HSSD project environment differs",
    )
    receipt_path = base.safe_attempt_child(
        execution["import_receipt"], attempt_root, "HSSD import receipt"
    )
    base.require(
        os.path.dirname(receipt_path) == attempt_root,
        "HSSD import receipt must be a direct attempt-root child",
    )
    base.require(
        not os.path.lexists(receipt_path), "HSSD import receipt already exists"
    )

    namespace = execution.get("content_namespace")
    base.require(
        isinstance(namespace, str) and NAMESPACE_RE.fullmatch(namespace) is not None,
        "HSSD content namespace is invalid",
    )
    source_run = execution.get("source_run")
    _exact_keys(source_run, SOURCE_RUN_KEYS, "HSSD source run")
    source_root = _canonical_nonsymlink_path(source_run["path"], "R5 source root")
    base.require(
        source_run["build_plan_sha256"] == EXPECTED_DOCUMENT_SHA256["build-plan.json"]
        and source_run["build_result_sha256"]
        == EXPECTED_DOCUMENT_SHA256["build-result.json"]
        and source_run["scene_plan_sha256"]
        == EXPECTED_DOCUMENT_SHA256["scene-plan.json"],
        "HSSD execution does not pin the exact R5 documents",
    )

    scripts = execution.get("scripts")
    _exact_keys(scripts, {"base", "common", "compatibility", "import"}, "HSSD scripts")
    expected_script_names = {
        "base": "commandlet_common.py",
        "common": "hssd_private_research_commandlet_common.py",
        "compatibility": "hssd_ue57_glb_compatibility.py",
        "import": "import_hssd_private_research_commandlet.py",
    }
    scripts_root = os.path.join(attempt_root, "scripts")
    for label, record in scripts.items():
        _exact_keys(record, SCRIPT_KEYS, "HSSD " + label + " script")
        expected_script_sha = base.require_sha(
            record["sha256"], "HSSD " + label + " script"
        )
        script_path = _canonical_nonsymlink_path(
            record["path"], "HSSD " + label + " script"
        )
        base.safe_attempt_child(script_path, attempt_root, "HSSD " + label + " script")
        script_raw, _ = _read_regular_file(script_path, "HSSD " + label + " script")
        base.require(
            os.path.dirname(script_path) == scripts_root
            and os.path.basename(script_path) == expected_script_names[label]
            and hashlib.sha256(script_raw).hexdigest() == expected_script_sha,
            "HSSD " + label + " script is not the exact attempt-local dependency",
        )
    base_pin = scripts["base"]
    base.require(
        base.canonical_path(base.__file__) == base.canonical_path(base_pin["path"])
        and base.sha256_file(base.__file__) == base_pin["sha256"],
        "HSSD base helper identity or digest differs",
    )
    common_pin = scripts["common"]
    base.require(
        base.canonical_path(__file__) == base.canonical_path(common_pin["path"])
        and base.sha256_file(__file__) == common_pin["sha256"],
        "HSSD common helper identity or digest differs",
    )
    compatibility_pin = scripts["compatibility"]
    base.require(
        base.canonical_path(compatibility.__file__)
        == base.canonical_path(compatibility_pin["path"])
        and base.sha256_file(compatibility.__file__) == compatibility_pin["sha256"],
        "HSSD compatibility helper identity or digest differs",
    )
    script_pin = scripts[script_kind]
    base.require(
        base.canonical_path(script_file) == base.canonical_path(script_pin["path"])
        and base.sha256_file(script_file) == script_pin["sha256"],
        "HSSD commandlet identity or digest differs",
    )

    source_bindings = validate_source_run(source_root, namespace)
    derived_bindings = _validate_compatibility_execution(
        execution,
        attempt_root,
        source_bindings,
        compatibility_pin["sha256"],
    )
    bindings = execution.get("asset_bindings")
    base.require(
        isinstance(bindings, list)
        and len(bindings) == 26
        and all(
            isinstance(item, dict)
            and set(item) == EXECUTION_BINDING_KEYS
            and isinstance(item["source"], dict)
            and set(item["source"]) == SOURCE_BINDING_KEYS
            and isinstance(item["derivative"], dict)
            and set(item["derivative"]) == DERIVATIVE_BINDING_KEYS
            for item in bindings
        )
        and bindings == derived_bindings,
        "HSSD execution bindings differ from exact source/derivative inventory",
    )
    base.require(
        execution.get("import_mode") == DIAGNOSTIC_IMPORT_MODE
        and namespace == DIAGNOSTIC_NAMESPACE,
        "HSSD nonpromotable corpus is not bound to its diagnostic mode/namespace",
    )
    return execution, manifest_path, expected_sha, derived_bindings


canonical_json = base.canonical_json
canonical_path = base.canonical_path
require = base.require
require_sha = base.require_sha
safe_attempt_child = base.safe_attempt_child
sha256_file = base.sha256_file
write_exclusive_receipt = base.write_exclusive_receipt
