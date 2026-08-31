# HSSD portable pickup visual binding (dev derivative)

Status: source tooling and focused tests only. This runbook does not claim that
Unreal, pickup/place/drop, or human visual review has passed.

The pipeline removes exactly two redundant HSSD visual-only shells and binds their
already imported StaticMeshes to the render-only `PresentationMesh` child of the
existing `VistaPickupActor` authority:

- `home.r1/room/kitchen_dining/entity.coffee_cup.01` ← `hssd.static.coffee_cup`
- `home.r1/room/living_room/entity.slipper.01` ← `hssd.static.flip_flops`

The pickup actor, `PickupMesh` collision/physics root, semantic ID, transform,
replication and portability remain authoritative. The presentation relative transform
is identity, so the HSSD mesh moves with pickup/place/drop instead of remaining at its
old shell transform.

## Closed inputs

- Contract:
  `world_packs/vista_playable_home_r1/visual_bindings/hssd_portable_pickups_r1.json`
- Contract content digest:
  `924bedcfbea04f6ec7f8fdbdf2871157c3b64c66b4874f68466ebb4d42bda185`
- Fixed planner:
  `tools/ue/vista_playable_home/plan_hssd_portable_visual_binding_dev.py`
- Fixed commandlet:
  `tools/ue/vista_playable_home/compose_hssd_portable_visual_binding_commandlet.py`
- One successful `vista.playable-articulated-fridge-dev-scene-receipt/v1` whose
  status is `dev_derivative_composed_pending_runtime_and_human_review`.
- A fresh isolated copy of that successful fridge attempt's `project/` directory.

Do not use a partial/quarantined fridge result. In particular, the observed
`hssd-r2-action-fridge-dev-r1-20260901c` receipt is quarantined at
`prove_legacy_identity` and is not a legal source for this planner.

Validate the Git-side contract without resolving private HSSD payloads:

```bash
uv run python \
  tools/ue/vista_playable_home/hssd_portable_visual_binding_contract.py
```

## Prepare one append-only attempt

Set `SOURCE` to a later *successful* articulated-fridge attempt. Use a new run ID;
never reuse a partial attempt or pre-existing output path.

```bash
SOURCE=/data/sysx/vista-world/runs/vista-action-world-r1/<successful-fridge-attempt>
ATTEMPT=/data/sysx/vista-world/runs/vista-action-world-r1/hssd-portable-bind-dev-r1-<run-id>

install -d -m 0700 "$ATTEMPT"
cp -a --reflink=auto "$SOURCE/project" "$ATTEMPT/project"
```

Before planning, the copied project must contain the fridge derivative `.umap` at the
object path and exact SHA/size in `$SOURCE/articulated-fridge-scene-receipt.json`.
There must be no map at the new portable-binding derivative path.

## Seal the execution (does not launch UE)

For the current project filename, the exact planner interface is:

```bash
uv run python \
  tools/ue/vista_playable_home/plan_hssd_portable_visual_binding_dev.py \
  --attempt-root "$ATTEMPT" \
  --project-file "$ATTEMPT/project/VistaPlayableHome.uproject" \
  --source-fridge-scene-receipt \
    "$SOURCE/articulated-fridge-scene-receipt.json" \
  --derivative-map \
    /Game/VISTA/Dev/PortableVisualBindings/<run-id>/Maps/VistaPortableHssd
```

The planner exclusively creates:

- `$ATTEMPT/inputs/hssd-portable-visual-binding-contract.json`
- `$ATTEMPT/inputs/source-articulated-fridge-scene-receipt.json`
- `$ATTEMPT/hssd-portable-visual-binding-execution.json`

It refuses an unsuccessful fridge receipt, source-map byte drift, an existing input
directory, a non-isolated project, or an existing/non-dev derivative.

## Explicitly approved UE commandlet

Only after reviewing the sealed execution and only against the isolated copied
project, run the fixed commandlet. This is a null-RHI editor mutation and is not part of
the source-only step:

```bash
EXECUTION="$ATTEMPT/hssd-portable-visual-binding-execution.json"
EXECUTION_SHA256="$(sha256sum "$EXECUTION" | awk '{print $1}')"

VISTA_HSSD_PORTABLE_VISUAL_BINDING_EXECUTION="$EXECUTION" \
VISTA_HSSD_PORTABLE_VISUAL_BINDING_EXECUTION_SHA256="$EXECUTION_SHA256" \
/mnt/NAS2/yhliu/UE_5.7.3_prebuilt/Engine/Binaries/Linux/UnrealEditor-Cmd \
  "$ATTEMPT/project/VistaPlayableHome.uproject" \
  -nullrhi -nosound -unattended -nop4 -nosplash \
  -NoAssetRegistryCache -NoHotReloadFromIDE -NoEngineChanges \
  -DDC-ForceMemoryCache -EnablePlugins=VistaPlayableHome \
  -ExecutePythonScript="$(pwd)/tools/ue/vista_playable_home/compose_hssd_portable_visual_binding_commandlet.py" \
  -AbsLog="$ATTEMPT/unreal-hssd-portable-binding.log" \
  -stdout -FullStdOutLogOutput
```

The commandlet binds each `/Game` map object path to its exact loaded-project `.umap`,
calls `new_level_from_template(new_map, completed_fridge_map)`, and proves both shells
and both pickup actors before the first deletion. Shell proof includes unique identity
tag namespaces, visual-only diagnostic/authority tags, root-component ownership,
static mobility, visibility, disabled overlap/navigation/collision and no physics. It
then loads the two exact HSSD
StaticMeshes without importing/replacing assets, deletes only the shell actors, binds
the meshes, saves/cold-reloads the derivative, and rechecks the source-map package SHA.
Any partial derivative is append-only quarantine evidence.

Even a successful source receipt remains `accepted=false`, `runtime_verified=false`,
and `human_reviewed=false`. A separate live review must demonstrate coffee-cup and
slipper pickup/place/drop while their HSSD presentation follows the authoritative actor
before this map can be selected for the playable demo.
