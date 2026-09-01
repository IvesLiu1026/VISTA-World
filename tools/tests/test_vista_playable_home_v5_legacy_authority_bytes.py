from __future__ import annotations

import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

# These are the exact source authorities present at the approved v5 branch
# point.  V5 is additive; any old payload or schema byte change must fail.
EXPECTED_SHA256 = {
    "world_packs/vista_playable_home_r1/action_catalogs/vista_indoor_actions_r1.json": "df1c1a3f48d8a46b6cfd716047cb11838a69583e8a999710f5c731a230c13fa2",
    "world_packs/vista_playable_home_r1/action_catalogs/vista_indoor_actions_r2.json": "bceca3be4f54f9422bb53b2e5805f762de2a9b6ac1f1747afa983c6f79760868",
    "world_packs/vista_playable_home_r1/action_catalogs/vista_indoor_actions_r3.json": "07ee1d6a2e09f95bff0c5379ada2e31acd7273cb91e813ac862bb30666c76129",
    "world_packs/vista_playable_home_r1/action_catalogs/vista_indoor_actions_r4.json": "44062943dd6b138717c93d9d86c9114f6084276764f399b468b546b58a5e9689",
    "world_packs/vista_playable_home_r1/events/mmg_001.json": "6d0ce9f13f8847bf14ce0d04262edc23da1b9a80efdedf8fcb62b417a70fe4ed",
    "world_packs/vista_playable_home_r1/events/mmg_013.json": "8157865f7762a42394575da25ed2517974676482291bbe941934f4591af8d34b",
    "world_packs/vista_playable_home_r1/events/mmg_021.json": "10f2256e1c8893e21d96e5569e2866dada9c91da9459efe664251128cfdf7c89",
    "world_packs/vista_playable_home_r1/events/mmg_040.json": "a8787de2b87d7905ab4b195c7e01b747581019e6e3a00da39582fe4275da10c4",
    "world_packs/vista_playable_home_r1/events/mmg_044.json": "b3855233e6a5097f5d405fc7c48e3808511d6161d3580cd0fd67d47e50dee25a",
    "world_packs/vista_playable_home_r1/events/mmg_045.json": "f263f8981648a24a6832f8962d08b86e07b2be98c6b72bcd3f7cf5b2759598ff",
    "world_packs/vista_playable_home_r1/events/mmg_070.json": "72a2c5723b51007f158cc3b2701b2e8339157226cafe60b03fbfc5bd68101cb0",
    "world_packs/vista_playable_home_r1/events_v2/mmg_013.json": "8a3850d4b5b22965dd0f5269a4da8237bad3f3310d0173761c6f8cb4317d2d01",
    "world_packs/vista_playable_home_r1/events_v2/mmg_040.json": "bcab81b014315cbd34b340b2694ce5302ba19a4f9ee78e6f2910feb1b35ff6de",
    "world_packs/vista_playable_home_r1/events_v2/mmg_044.json": "1949f66c34d3af68dfbb6a2504e0559f03acf07bd7a94aba75018ef24ade8e08",
    "world_packs/vista_playable_home_r1/events_v2/mmg_045.json": "653ab3ee070f46dde9cf2c73c27f652200fb56a9e734be4c285f90c8fb81592b",
    "world_packs/vista_playable_home_r1/events_v3/mmg_001.json": "b64517e3fc28f4314fdd7a03d68f6564a2838157c49acbf054f5b0e48b799c71",
    "world_packs/vista_playable_home_r1/events_v3/mmg_013.json": "8bdd234f62e2f7b1fa6e2f714ee8583acce4f2de5a7e77636b352a983be0c574",
    "world_packs/vista_playable_home_r1/events_v3/mmg_021.json": "140ca4f22e3ae00e423be12c725903af84e8ccca01f497fb067df48d627654a5",
    "world_packs/vista_playable_home_r1/events_v3/mmg_040.json": "d3cb0df27b9707f4d72274a07382c57d3704147310aa0ae116afb6c87ee7c52f",
    "world_packs/vista_playable_home_r1/events_v3/mmg_044.json": "d9904c305f27016e960b8277d4ba35213c7ceddf6e38468ee97749a2cd55f828",
    "world_packs/vista_playable_home_r1/events_v3/mmg_045.json": "18d11e2d16991c86e2de4d4e7e294516f02e2d4178226bf3e32e1be3073a14fc",
    "world_packs/vista_playable_home_r1/events_v3/mmg_070.json": "037c9b3791f9715e7157bbb9021a4d4826f31fb5f0dd47d66d64340415161ed3",
    "tools/tests/fixtures/vista_playable_event_v4/mmg_013_contract_extension.json": "d58a7fd3f44d39eac90e60c38680195e3a97030ae57269727708809e40738186",
    "world_packs/schemas/vista-playable-action-catalog-v1.schema.json": "2946dbef24fbc32ab44fbf0f1a8302810cd03075f3eab9fee1a99a976b7da21c",
    "world_packs/schemas/vista-playable-action-catalog-v2.schema.json": "541000ae28fb46573cf955939a42a21c752eb706c2641c4c37442813e48d7c61",
    "world_packs/schemas/vista-playable-action-catalog-v3.schema.json": "6230c4a948b0c0dd27691c403af6a1ef6f2933860b40f3af87e7db7b1fa9c73a",
    "world_packs/schemas/vista-playable-action-catalog-v4.schema.json": "bffdf0b2b53e22c839632c00c3d4244a24fc94552d591eb8ae520efb0e3a8d77",
    "world_packs/schemas/vista-playable-event-v1.schema.json": "5a8f146e9594f90c118cbb1d403e5fdb4ccd1d02302dba70f8466de42b356504",
    "world_packs/schemas/vista-playable-event-v2.schema.json": "43c95b3ff8a0d7dfffd3214ab3875519329b7886c1ef699e9f7c3aefee03669e",
    "world_packs/schemas/vista-playable-event-v3.schema.json": "ebe60d910d05d54a0fa78000d4f5592a69c102c025caf899d16f44a05a9ec53d",
    "world_packs/schemas/vista-playable-event-v4.schema.json": "468252906f2fe7fc86d3fde2232e4bf2c97d45c4c41d622e89500c5d7840e4ce",
}


def test_v1_through_v4_authority_bytes_are_frozen() -> None:
    observed = {
        relative: hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
        for relative in EXPECTED_SHA256
    }
    assert observed == EXPECTED_SHA256
