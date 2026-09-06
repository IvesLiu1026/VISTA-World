# Connected home review

The standalone kitchen has been extended into a connected home: entry hall,
living room, kitchen/dining, bedroom, office and bathroom/laundry. The five
interior portals follow the existing nominal home layout. The home is an
independent review project on `codex/vista-photoreal-design-r1`.

Open **VISTA Photoreal Home** in Moonlight/Sunshine. The reviewed project is
`project-g/PhotorealHome.uproject` under the run root below. The live profile is
`sunshine-review-profile-g.json`; its game and input relay are active on `:119`.

## Contents and controls

| Key | Room | Modeled contents |
| --- | --- | --- |
| 1 | Entry | Shoe bench, slippers, key tray, entrance door, service panel |
| 2 | Living | Three-seat sofa, coffee table, media console/TV, curtains, lamp |
| 3 | Kitchen | Existing sage kitchen, dining set, pot, mug and articulated fridge |
| 4 | Bedroom | Double bed, cotton duvet/pillows, wardrobe, bedside furniture, phone, backpack |
| 5 | Office | Desk, monitor/keyboard/cables, five-star chair, cabinet, books, box, stepladder |
| 6 | Bathroom | Tub, shower, toilet, vanity/mirror, washer, basket, drain and towel |

WASD and mouse move/look; **V** selects the current room's second viewpoint.
**F** opens/closes the fridge; **7–9** show the fridge, pot and mug.
**C** switches walking/flying; Q/E descend/ascend in flight. Escape releases or
captures the cursor. F8 writes a native Unreal screenshot and a movement-state
record to that launch's UserDir.

Interior room doors are modeled in an open position. Fridge doors are animated
about their hinges. Furniture and fixtures have walking collision; simulated
grasping, articulated room doors, water and appliance cycles are not implemented.

## Reproducible assets

Run root:
`/data/sysx/vista-world/runs/vista-photoreal-design-r1/home-r1-20260906a`.

- `model-a`: initial complete build and its evidence.
- `model-b/photoreal_home.blend`: refined original Blender scene with packed maps.
- `model-b/model-manifest.json`: accepted geometric parts; unchanged GLBs refer
  to the frozen `model-a/glb` paths, revised parts to `model-b/glb`.
- `export-check-b.json`: 6 rooms, 5 portals, 126 parts, 2,394 source meshes,
  1,376,608 triangles and 434,193,016 bytes of self-contained GLBs.
- `model-b/previews`: six actual Cycles renders, inspected independently from UE.
- `import-b.json`: all 126 UE imports passed material and 1 mm bounds checks.

All geometry and PBR maps are project-authored. No third-party asset payloads,
paid generations, API keys or remote model calls were used for this extension.
The nominal 116 m² plan is a design layout, not a surveyed site or construction
drawing. Blender metres map to UE centimetres as `(x, -y, z) * 100`.

`build_home.py` reuses the accepted kitchen recipe and creates the new rooms.
`refine_home.py` in the Blender folder can apply the reviewed normal/duvet
changes to a completed initial scene. `verify_home.py` reads actual GLB JSON and
binary headers, checks hashes and embedded images, and counts geometry.

In Unreal, `create_project.py --whole-home` creates a fresh isolated project.
`import_home.py` imports the manifest and creates the map; the UE
`refine_home.py` prepares project-local Nanite material parents and records
actual light directions. Run it on a copied project when revising an existing
review. Never edit the engine's shared Interchange material assets.

Use named `pitch`, `yaw`, `roll` arguments for Python `unreal.Rotator`.
Positional arguments use a different order from the C++ constructor; a prior
iteration pointed ceiling lights sideways. The reviewed import now rejects
ceiling lights whose forward vector does not point down.

`r.ExposureOffset` belongs in the review launch's console commands, not the
Engine INI: this cheat CVar causes a handled ensure when set there. Shader
parents for Nanite must opt into that usage in project-local copies.

Fabric uses the standard PBR master in UE, retaining the original base-colour
and normal maps and roughness. The imported sheen master had applied a full
white fuzz layer even to charcoal fabric; the reviewed fallback fixes that
colour mismatch. The live exposure offset is `-2.8`.

## Runtime isolation

`review_session.py` selects mutually exclusive kitchen/home input relays and
restores the prior relay when no review remains. It stops only its named review
services. Selection failure also restores the original input state. Existing
R23/R6 demo processes, accepted standalone kitchen assets and authentication
remain separate.

The home uses GPU0 for interactive X11 presentation; GPU1 rendered the Blender
previews. A temporary display `:120` is used for inspection before promoting to
Sunshine display `:119`. The launcher requests 1920×1080 and caps at 30 fps;
this is a cap, not a measured minimum performance guarantee.

The Sunshine application installer preserves existing app entries and takes a
byte-for-byte backup before an atomic update. An app list written directly to
disk may need a reload; verify actual client connection logs before restarting
the service. A retained application can report BUSY even after the client has
disconnected. Sunshine's authenticated [application API implementation](https://github.com/LizardByte/Sunshine/blob/master/src/confighttp.cpp)
refreshes its process list after saving an app.

## Validation

- Contract/compiler baseline and relay regression suite: 31 tests passed.
- Actual Blender exports: integrity, material and embedding checks passed.
- Actual UE import: all part bounds and material bindings checked.
- Five hall-to-room routes: traversed using CharacterMovement and W input,
  with position and walking-mode logs. Bookmark teleport alone is not counted
  as evidence of traversal.
- Native UE room and reverse-angle screenshots are retained for visual review.

The final `final-evidence/live-check.json` contains 29 native 1920×1080
screenshots, five bidirectional walking checks, blocked walking at the closed
front door, fridge open/closed state, flying and landing. The final runtime has
no missing Nanite-material or VSM job-overflow warnings. The Sunshine service
was reloaded after confirming the client had disconnected; the existing R23
and R6 services retained their process IDs.

Final asset hashes, runtime profile and screenshot receipt are recorded in
`home-implementation-manifest.json`.
