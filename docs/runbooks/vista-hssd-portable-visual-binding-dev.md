# HSSD portable pickup visual binding (dev derivative)

Status: source tooling and focused tests only. This runbook does not claim that
Unreal, pickup/place/drop, or human visual review has passed.

The pipeline handles each source shell with an explicit closed disposition, then
binds both already imported StaticMeshes to the render-only `PresentationMesh` child
of the existing `VistaPickupActor` authority:

- `home.r1/room/kitchen_dining/entity.coffee_cup.01` ← `hssd.static.coffee_cup`;
  disposition `already_absent_source_shell`. Before any binding mutation, the full
  actor inventory must contain zero matches for its exact HSSD instance tag, actor
  label, and semantic-target tag.
- `home.r1/room/living_room/entity.slipper.01` ← `hssd.static.flip_flops`;
  disposition `exact_visual_shell_to_delete`. Its exact visual-only shell must be
  uniquely closed and is the only actor deleted.

The pickup actor, `PickupMesh` collision/physics root, semantic ID, transform,
replication and portability remain authoritative. The presentation relative transform
is identity, so the HSSD mesh moves with pickup/place/drop instead of remaining at its
old shell transform.

## Closed inputs

- Contract:
  `world_packs/vista_playable_home_r1/visual_bindings/hssd_portable_pickups_r1.json`
- Contract content digest:
  `ac3f53d70481e4565e777e50757006a70a105e3b3c7c1fb3a27725c39453e1bd`
- Contract raw SHA-256:
  `a39d49235b7fec3cbf0c3dd2cebd9424b97a3f3868272e56786f327e0a4f1cb5`
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

Do not reinterpret the absent coffee shell as permission to bind a different visual
shell such as coffee cup 02. Any one or duplicate match in any of the three declared
coffee identity namespaces fails closed. The exact coffee HSSD StaticMesh and exact
unbound coffee pickup must still load and validate.

The observed portable attempt `hssd-portable-bind-dev-r1-20260901a` is permanently
quarantined at `prove_all_identities_before_delete`: it correctly established that the
declared coffee-cup-01 shell has zero instance-tag matches, but its older contract
incorrectly required one shell. Never reuse that attempt directory or derivative path.

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
calls `new_level_from_template(new_map, completed_fridge_map)`, proves the declared
coffee identity is absent across the full actor inventory, and proves the unique
slipper shell plus both pickup actors before the only deletion. Slipper proof includes
unique identity tag/label closure, visual-only diagnostic/authority tags,
root-component ownership, static mobility, visibility, disabled
overlap/navigation/collision and no physics. It then loads both exact HSSD StaticMeshes
without importing/replacing assets, deletes exactly the declared slipper shell, proves
that the actor inventory differs by only that one actor, binds the meshes,
saves/cold-reloads the derivative, re-proves both source-shell identities absent, and
rechecks the source-map package SHA. The receipt records each binding's declared and
observed shell disposition. Any partial derivative is append-only quarantine evidence.
After binding, the exact validated pickup is expected to carry its HSSD instance tag;
the cold-reload shell-absence check excludes only that one pickup actor path from the
instance-tag match set. Actor-label and semantic-target checks have no exception, and
any other actor carrying the instance tag still fails closed.

Even a successful source receipt remains `accepted=false`, `runtime_verified=false`,
and `human_reviewed=false`. A separate live review must demonstrate coffee-cup and
slipper pickup/place/drop while their HSSD presentation follows the authoritative actor
before this map can be selected for the playable demo.
