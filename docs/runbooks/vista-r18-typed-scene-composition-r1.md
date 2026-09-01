# VISTA R18 typed scene composition source

Status: source milestone only. This document is not a live-scene, packaged-build,
Sunshine, visual-quality, animation-contact, or human-play acceptance receipt.

## Closed input

The additive profile is:

`world_packs/vista_playable_home_r1/composition_profiles/vista_home_typed_scene_r18.json`

It is bound to the exact `home.r1` revision and HouseSpec content digest. The
existing house/build-plan schemas remain unchanged. The profile fails closed when
its digest, house binding, seat coverage, source/receiver identity, liquid type,
room containment, or external-asset policy differs.

External `.uasset`, GLB, textures, and other payloads are not stored in Git. Each
new liquid actor carries a stable `visual_binding_id`, requires a future external
receipt, and states that its current HouseSpec proxy mesh is not acceptance
evidence.

### Animation dependency hard gates

The observed live R6 project contains neither the R14 nor the R15 DetailActions
assets. Both source profiles therefore remain explicit, unmet dependencies:

- `makehuman_cc0_detail_actions_r14`, digest
  `eccf9da1ca7283efc08cffabe1d52ba020578e3d7c04d423cb2356f25b320d43`,
  under `/Game/VISTA/MakeHumanCC0/R14/DetailActions`;
- `makehuman_cc0_detail_actions_r15`, digest
  `fb88d2cdfe810226d84b9111cbe99ad7c13842cab0e60c4af48354fe5bc02384`,
  under `/Game/VISTA/MakeHumanCC0/R15/DetailActions`.

Their exact sequences, montages, skeleton binding, and notifies must first be
materialized as UAssets and proved in the candidate project. Source contracts or
soft object paths alone do not satisfy this gate.

The live CitySample human is driven by a hidden Manny authority, while the R14/R15
montages are authored against the 53-bone MakeHuman CC0 skeleton. A separate,
receipt-bound CC0-to-Manny retarget authority is therefore also required. The
original CC0 montages are **not** CitySample-playable assets and this source
milestone makes no such claim. Materializing CC0 UAssets and authoring/proving the
Manny retarget are two independent hard gates.

## Compiled native actors

When the profile is explicitly supplied to `build_composition_spec`:

- all four HouseSpec entities with the `sit` affordance compile as
  `/Script/VistaPlayableHome.VistaSeatActor`;
- every seat has an authored local `SeatTarget`, a semantic interaction anchor,
  and a semantic exit anchor;
- `entity.water_jug.18` compiles as one pourable `AVistaPickupActor`, with 1500 ml
  capacity, 80% initial water, and pickup/drop/place/inspect/pour affordances;
- `entity.drinking_glass.18` and `entity.serving_bowl.18` compile as
  `AVistaLiquidReceiverActor`, with typed water acceptance, independent capacity,
  and authored local `PourTarget` transforms;
- all appended actor and anchor semantic IDs participate in save/reload
  verification.

The fixed home composer binds reflected native properties; it does not accept a
caller-selected Unreal class or component path.

## Source validation

Executed from the isolated `codex/vista-r18-composition` worktree:

```bash
PYTHONPATH=.:tools uv run pytest -q \
  tools/tests/test_vista_playable_home_unreal.py \
  tools/tests/test_vista_playable_home_build_home.py \
  tools/tests/test_vista_playable_home_r18_scene_composition.py
```

Result: `43 passed, 2 subtests passed`.

```bash
PYTHONPATH=tools uv run python -m unittest \
  tools.tests.test_vista_playable_home_contracts \
  tools.tests.test_vista_playable_home_compiler -v
```

Result: `28 tests`, `OK`.

Ruff, Python byte compilation, and `git diff --check` also passed. No Unreal
Editor, UBT, GPU, Sunshine, Pixel Streaming, package job, external asset import,
or service lifecycle operation was run for this source milestone.

## Remaining gates before live use

1. Materialize an execution manifest that explicitly supplies and pins this
   optional typed profile.
2. Bind real jug, glass, and bowl visual assets through external receipts while
   preserving these actors as semantic/collision authorities.
3. Materialize the exact R14/R15 CC0 UAssets, then independently author and prove
   the CC0-to-hidden-Manny retarget authority used by the CitySample visual.
4. Run a fresh UE commandlet composition and save/reload proof.
5. Package a candidate and visually verify scale, collision, seat target height,
   exit clearance, PourTarget alignment, and liquid mutations.
6. Complete Sunshine human-play testing before calling the slice playable.
