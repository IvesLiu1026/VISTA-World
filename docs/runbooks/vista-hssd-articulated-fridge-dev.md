# HSSD articulated fridge dev derivative

Status: tooling only; Unreal has not been run and no visual/runtime acceptance exists.

This path builds a fresh, append-only development derivative. It must never target the
current R6 project, map, package, Sunshine service, or production worktree. The isolated
project must live at `<attempt-root>/project/*.uproject`, contain a copied base map, and
have no pre-existing derivative map or articulated-fridge asset namespace.

## Inputs

- Repository contract:
  `world_packs/vista_playable_home_r1/articulations/hssd_side_by_side_fridge_r1.json`
- Private HSSD revision `4369cb9876214c7fbebcf552eb532380e4d287e4`.
- A successful sealed HSSD Phase-2 scene receipt containing exactly one
  `hssd.r1/kitchen_dining.fridge.01` visual shell and exactly one hidden
  `home.r1/room.kitchen_dining/entity.fridge.01` container proxy.
- The existing hash-pinned Three/Basis Universal JS and WASM decoder files.
- An isolated UE 5.7.3 project copy under the new attempt root.

Do not continue if the scene receipt was edited, the old shell/proxy cannot be located by
its exact receipt identity, or any project/map/asset destination already exists.

## 1. Transport the three pinned links

Choose a new attempt root outside Git and keep all generated GLBs there. Run:

```bash
uv run python tools/blender/vista_playable_home_hssd/articulated_fridge_transport.py \
  --hssd-root /mnt/NAS2/yhliu/habitat_data/versioned_data/hssd-hab \
  --output-root <attempt-root>/transport \
  --node /home/yhliu/.local/bin/node \
  --basis-transcoder-js /home/yhliu/judge-project/node_modules/three/examples/jsm/libs/basis/basis_transcoder.js \
  --basis-transcoder-wasm /home/yhliu/judge-project/node_modules/three/examples/jsm/libs/basis/basis_transcoder.wasm
```

The command refuses an existing output directory. Its receipt must report exactly
`body`, `primary_door`, and `secondary_door`, with self-contained embedded core PNGs.
It intentionally reports `accepted=false` and `ue_imported=false`.

## 2. Seal the UE execution without launching UE

After placing the isolated project at `<attempt-root>/project/`, run the planner with a
new dev-only map and asset namespace:

```bash
uv run python tools/ue/vista_playable_home/plan_hssd_articulated_fridge_dev.py \
  --attempt-root <attempt-root> \
  --project-file <attempt-root>/project/VistaFridgeDev.uproject \
  --transport-receipt <attempt-root>/transport/articulated-fridge-transport-receipt.json \
  --legacy-scene-receipt <sealed-phase2-scene-receipt.json> \
  --derivative-map /Game/VISTA/Dev/ArticulatedFridge/<run-id>/Maps/VistaFridge \
  --content-namespace /Game/VISTA/Dev/ArticulatedFridge/<run-id>/Content
```

This creates only `<attempt-root>/inputs/*` and
`<attempt-root>/articulated-fridge-execution.json`. It does not import, compose, launch
UE, or modify a map.

## 3. Future explicitly approved UE commandlet

Only after reviewing the execution manifest and confirming that the loaded project is
the isolated attempt copy, invoke UE Editor-Cmd with these two environment variables:

```text
VISTA_ARTICULATED_FRIDGE_EXECUTION=<attempt-root>/articulated-fridge-execution.json
VISTA_ARTICULATED_FRIDGE_EXECUTION_SHA256=<exact sha256 of that file>
```

Run the fixed script
`tools/ue/vista_playable_home/compose_hssd_articulated_fridge_commandlet.py` through
PythonScriptCommandlet in unattended/null-RHI mode. Do not point it at a live project.

The commandlet will:

1. Revalidate project, engine, script, contract, scene receipt, transport receipt, all
   three GLBs, and the base-map package hash.
2. Import the three links into a fresh dev namespace with `replace_existing=false`.
3. Duplicate the base map to a fresh dev map and load only the derivative.
4. Require one exact legacy visual shell and one exact hidden container proxy, including
   fresh derivative-map scope, label, class, tags, transform, mesh and collision state.
   Unreal assigns fresh persistent object names when cloning a level template, so the
   source receipt pins the original object path while the derivative gate pins the new
   map scope plus all observable identity fields.
5. Delete those two actors only from the derivative, spawn
   `/Script/VistaPlayableHome.VistaArticulatedFridgeActor`, and bind body, both hinges,
   both doors and the handle target.
6. Save and cold-reload the derivative, re-observe the full binding, and prove that the
   base-map package hash is unchanged.

Any partial namespace or derivative remains quarantined and must not be promoted or
reused. A successful tooling receipt still does not establish door animation, runtime
interaction, multiplayer, human visual quality, or GTA-level acceptance; those require
a separate explicitly approved UE/runtime and Sunshine review.
