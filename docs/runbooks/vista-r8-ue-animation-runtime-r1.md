# VISTA R8 CC0 animation → UE 5.7 runtime slice (R1)

## Status and boundary

This slice implements the code and evidence contract for importing the five
project-authored MakeHuman CC0 R8 FBXs into the already verified R6 character
project, then authoring a minimal locomotion/pickup/place runtime closure.

Current status is **blocked before write**. The source feature and dry-run plan
are implemented, but executable authority is intentionally a separate lane.
Three blockers remain:

1. a fresh root-published R8 host receipt produced after the reviewed
   Blender/publisher repair; and
2. a reviewed BuildPlugin package containing this exact plugin source; and
3. a sealed UE 5.7 execution authority/runner that binds immutable R3,
   BuildPlugin, commandlet, and **full engine closure**, mounts a sealed manifest
   at fixed sandbox paths, unshares the network, and publishes through a
   distinct immutable boundary.

The materializer's dry run is valid and zero-write. This source slice contains
no `Popen`/UE runner; `--apply` always refuses before creating an attempt. This
is deliberate because the installed NAS engine ancestry is mutable and an
attempt-local copied plugin/commandlet/FBX would permit same-UID pathname
replacement. No UE, UHT, UBT,
BuildPlugin, GPU, Blender, render, or external R8 artifact was executed or read
during this implementation. Nothing in this document is runtime, interaction,
human-motion-quality, photorealism, or GTA-quality acceptance.

Development attempts
`makehuman-cc0-animation-r8-candidate-20260829e` and
`makehuman-cc0-animation-r8-candidate-20260829f` are permanent quarantine
evidence. The host rejects both names even if a caller tries to pin their
bytes.

## Closed asset contract

Existing R6 inputs:

- mesh:
  `/Game/VISTA/MakeHumanCC0/R6/SK_VISTA_CC0_Hero_R6.SK_VISTA_CC0_Hero_R6`
- skeleton:
  `/Game/VISTA/MakeHumanCC0/R6/SK_VISTA_CC0_Hero_R6_Skeleton.SK_VISTA_CC0_Hero_R6_Skeleton`
- exact 53-bone hierarchy with lowercase `root`

New namespace:

`/Game/VISTA/MakeHumanCC0/R8/Animations`

Exact output inventory:

| Class | Exact assets |
| --- | --- |
| `AnimSequence` | `Sequences/AS_VistaCC0Idle`, `AS_VistaCC0Walk`, `AS_VistaCC0Run`, `AS_VistaCC0MugPickupCountertop`, `AS_VistaCC0MugPlaceCountertop` |
| `BlendSpace1D` | `BS_VistaCC0Locomotion_R8`, samples at 0/350/600 cm/s |
| `AnimBlueprint` | `ABP_VistaCC0Hero_R8`, native parent `UVistaMakeHumanCc0AnimInstance` |
| `AnimMontage` | `Montages/AM_VistaCC0MugPickupCountertop`, `AM_VistaCC0MugPlaceCountertop` |

No new Skeleton, SkeletalMesh, PhysicsAsset, StaticMesh, Material,
MaterialInstance, or Texture is permitted.

The three locomotion clips loop through the BlendSpace player. Pickup/place are
single-loop montages. The fixed typed notify contract is:

| Montage | Frame / 30 fps | Exact signal |
| --- | ---: | --- |
| pickup | 34 | `vista_pickup_contact` |
| pickup | 59 | `vista_pickup_completed` |
| place | 34 | `vista_drop_release` |
| place | 59 | `vista_drop_completed` |

## Host materializer

Implementation:

`tools/ue/vista_playable_home/materialize_makehuman_cc0_animation_runtime.py`

Dry run (reads only the fixed R3 receipt/project and source-code commandlet/
engine identity candidates; neither candidate is execution authority, and it
creates no output):

```bash
uv run python \
  tools/ue/vista_playable_home/materialize_makehuman_cc0_animation_runtime.py \
  --attempt-root \
  /data/sysx/vista-world/runs/vista-action-world-r1/makehuman-cc0-animation-ue57-r1-dryrun
```

Expected current blockers:

```text
fresh_root_published_r8_authority_pins
reviewed_buildplugin_package_pins
sealed_ue57_execution_authority_and_runner
```

Filling the R8 and BuildPlugin pins alone does **not** authorize apply. A future
execution-authority change must be reviewed independently; it may then consume
this closed plan/commandlet, but must not revive attempt-local executable
copies or the mutable NAS engine pathname.

## UE commandlet

Implementation:

`tools/ue/vista_playable_home/makehuman_cc0_animation_runtime_commandlet.py`

The commandlet accepts no CLI asset paths or recipes. It accepts one canonical,
sealed execution manifest only at `/vista/input/execution.json`, reads/hash
checks that manifest once through one FD, requires exact `/vista/input` source
and commandlet paths plus `/vista/work` outputs, and then revalidates every
input file.

For every FBX, the Interchange policy is exact:

- `import_only_animations = true`
- exact existing R6 skeleton required
- `import_animations = true`
- `import_bone_tracks = true`
- timeline range and 30 Hz bake
- static/skeletal mesh, morph, physics, material, texture, and custom-attribute
  import disabled
- use-T0-as-reference-pose and skeleton curve-metadata mutation disabled

Each imported sequence must have the exact R6 skeleton, all 53 unique bone
tracks, 30/1 sampling, the exact source frame range, root motion disabled,
forced reference-pose root lock, and zero root translation/scale/rotation delta
at **every** sampled frame. Merely matching first/last root pose is insufficient.

After the five sequences save, the commandlet invokes the zero-argument native
editor bridge, installs the four exact typed notifies, saves all packages,
cold-reloads them, repeats the full 30 Hz/frame/53-track/all-frame-root and
`REF_POSE` root-lock inspection, and verifies the exact nine-asset namespace.
It also seals the whole pre-import Content tree and requires the post-import
delta to be exactly those nine UAssets with every R3 byte unchanged. The
subordinate commandlet never self-claims Blender round-trip authority; that
claim remains false pending host authority. Success remains `accepted:false`
and leaves dedicated-server,
two-client, interaction, human review, photorealism, and GTA claims false.

## Native authoring and runtime integration

### Runtime

- `UVistaMakeHumanCc0AnimInstance::NativeUpdateAnimation` publishes only a
  finite, clamped horizontal speed.
- `UVistaCharacterProviderComponent::ActivateMakeHumanCc0R8` replaces the
  owning semantic character's visual mesh with the exact R6 mesh and exact R8
  AnimBP. The existing capsule remains collision authority.
- `IsMakeHumanCc0R8Active` revalidates mesh, skeleton, 53 bones, lowercase root,
  `hand_r`, AnimClass/AnimInstance, mesh no-collision, and capsule collision on
  every mutation gate call. Status fields alone are not sufficient.
- `UVistaAnimationComponent::HasApprovedMutationAnimation` permits pickup/place
  only for that active exact provider. Its resolver can select only the two
  fixed CC0 montage paths.
- `UVistaActionExecutorComponent` uses the same validated animation component
  for preflight and the R5 transaction; `AVistaHomeNpcController` uses the same
  instance gate for queued actions.

This does not upgrade the existing private Epic/CitySample/MetaHuman demo lane.
The CC0 paths are under `/Game/VISTA/MakeHumanCC0/R8`; no Manny, MetaHuman,
CitySample, Human_Avatar, or SimWorld animation path is referenced by the CC0
asset constants or commandlet.

### Editor authoring bridge

`UVistaPlayableHomeCc0AnimationLibrary` exposes exactly two zero-argument
functions:

- `AuthorMakeHumanCc0R8RuntimeAssets()`
- `InspectMakeHumanCc0R8RuntimeAssets()`

The author function requires a fresh namespace, creates the fixed BlendSpace,
AnimBP graph (`GroundSpeed → BlendSpace X → DefaultSlot → Result`), and two
single-loop montages. The inspector rechecks exact paths, skeleton/preview mesh,
generated class, three sample identities/speeds, four-node graph topology and
connections, BlendSpace looping, montage source/slot/loop count, and the exact
typed notify class/signal/time pairs.

## UE 5.7 text-authority provenance

The implementation did not guess the following API spellings. They were
checked against the installed 5.7.3 source tree:

| Contract | Installed source authority |
| --- | --- |
| `bUse30HzToBakeBoneAnimation` and timeline range | `/mnt/NAS2/yhliu/UE_5.7.3_prebuilt/Engine/Plugins/Interchange/Runtime/Source/Pipelines/Public/InterchangeGenericAnimationPipeline.h` |
| shared skeleton, import-only, T0, curve metadata | `/mnt/NAS2/yhliu/UE_5.7.3_prebuilt/Engine/Plugins/Interchange/Runtime/Source/Pipelines/Public/InterchangeGenericAssetsPipelineSharedSettings.h` |
| Python property conversion | `/mnt/NAS2/yhliu/UE_5.7.3_prebuilt/Engine/Plugins/Experimental/PythonScriptPlugin/Source/PythonScriptPlugin/Private/PyGenUtil.cpp` |
| acronym/digit break behavior (`D3D11`, `Vector2d`) | `/mnt/NAS2/yhliu/UE_5.7.3_prebuilt/Engine/Source/Runtime/Core/Private/Internationalization/CamelCaseBreakIterator.cpp` |
| `ERootMotionRootLock::RefPose` | `/mnt/NAS2/yhliu/UE_5.7.3_prebuilt/Engine/Source/Runtime/Engine/Classes/Animation/AnimEnums.h` |
| root-motion setters and bone-pose/frame APIs | `/mnt/NAS2/yhliu/UE_5.7.3_prebuilt/Engine/Source/Editor/AnimationBlueprintLibrary/Public/AnimationBlueprintLibrary.h` |
| `UAnimationGraph::GetGraphNodesOfClass` | `/mnt/NAS2/yhliu/UE_5.7.3_prebuilt/Engine/Source/Editor/AnimGraph/Public/AnimationGraph.h` |
| dynamic montage, first reference, slot tracks | `/mnt/NAS2/yhliu/UE_5.7.3_prebuilt/Engine/Source/Runtime/Engine/Classes/Animation/AnimMontage.h` |

`PyGenUtil::PythonizePropertyName` strips the boolean `b` prefix, and the
installed camel-case break rules preserve the `30` with `Use` before breaking
`Hz`; therefore the exact reflected property is
`use30_hz_to_bake_bone_animation`. `RefPose` is exposed as the Python enum
member `unreal.RootMotionRootLock.REF_POSE`. The commandlet uses the explicit
AnimationLibrary root-motion functions rather than directly guessing reflected
property names.

These text checks reduce API uncertainty but do **not** replace BuildPlugin,
UHT/UBT, or a disposable UE commandlet smoke. Those remain blocked until the
reviewed plugin package, fresh R8 authority, and separate sealed UE execution
authority/runner all exist.

## Pure verification completed

```bash
uv run ruff check \
  tools/ue/vista_playable_home/materialize_makehuman_cc0_animation_runtime.py \
  tools/ue/vista_playable_home/makehuman_cc0_animation_runtime_commandlet.py \
  tools/tests/test_vista_playable_home_makehuman_cc0_animation_runtime_materializer.py \
  tools/tests/test_vista_playable_home_makehuman_cc0_animation_runtime_integration.py
```

Result: `All checks passed!`

Focused plus related regression suite:

```bash
uv run --with pytest python -m pytest -q \
  tools/tests/test_vista_playable_home_makehuman_cc0_animation_runtime_materializer.py \
  tools/tests/test_vista_playable_home_makehuman_cc0_animation_runtime_integration.py \
  tools/tests/test_vista_playable_home_animation_runtime.py \
  tools/tests/test_vista_playable_home_animation_authoring.py \
  tools/tests/test_vista_playable_home_action_executor.py \
  tools/tests/test_vista_playable_home_character_provider.py \
  tools/tests/test_vista_playable_home_character_provider_runtime.py \
  tools/tests/test_vista_playable_home_npc_navigation.py \
  tools/tests/test_vista_playable_home_player_pickup_slice.py
```

Result after the sealed-runner boundary and cold-reload/content-delta fixes:
`90 passed`.

## Next authorized sequence

1. Finish review/commit of the R8 source lane and run its root-owned publisher
   to a **new** 0555/0444 output; do not reuse E/F.
2. Independently review the new host receipt, publisher bindings, five FBX
   seals, 53-bone round-trip evidence, root-motion evidence, and claims; then
   record the four R8 pins.
3. Build and review a plugin package from this exact source commit.
4. Implement/review the separate sealed UE runner: root-owned immutable full
   engine and R3/plugin/commandlet closure, held or sealed inputs, fixed sandbox
   paths, bwrap network isolation, and immutable publication. Do not use the
   current mutable NAS engine path or same-UID attempt copies.
5. Only after that runner passes adversarial review, record all pins and run one
   fresh external attempt. Do not touch production or any prior attempt.
6. If the commandlet succeeds, keep `accepted:false`; next run BuildPlugin/
   dedicated-server two-client runtime and human motion review as separate
   evidence lanes.
