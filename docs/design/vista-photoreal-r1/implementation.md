# Kitchen modeling and Sunshine review

The first implemented space is the 5 × 4 × 3 m kitchen, with an original hollow
stainless pot and separate lid, a hollow ceramic mug, and an articulated
side-by-side refrigerator. The other five rooms remain design references.

This work lives on `codex/vista-photoreal-design-r1` in
`/data/sysx/vista-world/worktrees/vista-photoreal-design-r1`. It is an independent
review project. Existing playable-home maps, data contracts and demo projects
were preserved.

## Open the review

Connect Moonlight to the existing Sunshine host and select **VISTA Photoreal
Kitchen**. Refresh the application's list if the entry is not yet visible.

| Input | Result |
| --- | --- |
| WASD + mouse | Walk and look |
| 1 | Kitchen overview |
| 2 | Refrigerator view |
| 3 | Pot view |
| 4 | Mug and table view |
| F | Open/close both refrigerator doors |
| C | Toggle flying |
| Q / E | Descend / ascend while flying |
| Esc | Release/capture the cursor |
| F8 | Native UE screenshot and diagnostic state in the runtime log |

The review launcher selects a dedicated input relay for the `PhotorealKitchen`
window on display `:119`. Stopping the review restores the previous relay. The
original demo processes remain available. Existing Sunshine applications were
retained and its application file was backed up before adding this entry.

## Deliverables

The output root is:

`/data/sysx/vista-world/runs/vista-photoreal-design-r1/kitchen-r1-20260906a`

- `model-d/photoreal_kitchen.blend`: authored metric scene with semantic objects
  and packed original material maps.
- `model-d/glb/`: 23 self-contained GLB parts. The source contains 692 meshes;
  enclosure surfaces are exported separately for interior lighting.
- `model-d/model-manifest.json`: dimensions, part pivots, geometry counts and
  SHA-256 hashes. GLB payloads total 98,722,296 bytes.
- `model-d/previews/`: four Blender Cycles reference renders.
- `project-d/PhotorealKitchen.uproject`: UE 5.7.3 review project.
- `final-evidence/`: actual UE review screenshots after exposure adjustment.
- `import-c.json`, `lighting-d.json`: material/mesh import and final daylight
  change receipts. Project D is copied from C with a corrected sun orientation.
- `sunshine-review-profile-d.json`: the live review profile.
- `runtime/`: application-file backup, service selection state and live logs.
- `skill-research/`: pinned public skill documents reviewed for this task.

Large models, UE assets, binaries, logs and screenshots stay outside Git. The
repository contains reproducible model, import and runtime scripts instead.

## Modeling and rendering decisions

The cabinet fronts have thickness and gaps; edges use small bevels. The kitchen
includes floor and ceiling slabs, a door opening, window glazing and frames,
tile joints, sink basin and drain, faucet, gas hob, hood, table and chairs. The
pot and mug have inner walls; the refrigerator has shell, liners, shelves,
drawers, door bins, gaskets, handles and outer-edge pivots.

Procedural base-color, roughness and normal maps are authored locally. Steel
brushing and wood grain were reduced after visual inspection. Glazing uses a
dedicated UE translucent material. UE uses Lumen, soft local lighting, a
daylight-facing exterior facade, and an exposure offset of −1.8 stops for the
review. The startup command preserves that adjustment.

Blender 4.5.8 rendered on GPU1. The current Xvfb/Vulkan setup cannot present the
UE window from GPU1, so the live review uses GPU0 and is capped at 30 fps. This
is a frame-rate target, not a measured performance guarantee.

## Validation

- Blender generation completed; all GLB headers, embedded textures and SHA-256
  hashes were checked.
- All 23 meshes imported into UE with materials. Imported bounds match the
  meter-to-centimeter and handedness conversion within 1 mm.
- The custom UE review plugin compiled successfully using direct UBT without
  UBA. The earlier UBA stall and failed initial imports remain in the run logs.
- Fixed viewpoints and refrigerator open/close were exercised with X11 input
  and native UE screenshot/state records. Door progress reached 1 and returned
  to 0.
- Flying raised the character until the ceiling stopped its capsule at
  approximately 211.98 cm; returning to walking settled it at 90.15 cm.
- The existing contract/compiler suite passed all 28 tests; Python syntax and
  `git diff --check` passed.
- Starting/stopping the review restored the previous input relay. The new relay
  opened Sunshine's keyboard and mouse devices and checks the exact review
  window before forwarding input.

Host-side display and controls were checked. A connection from the user's own
Moonlight device is not represented as a completed end-to-end test.

## Scope and next step

This is an inspectable kitchen review, with walking collision and driven fridge
doors. It does not yet implement grasping, pot/mug rigid-body simulation, a
force-driven refrigerator hinge, or integration into the original task runtime.
The dimensions are design specifications, not surveyed measurements of an
existing apartment or manufacturer-certified product drawings.

Before adding simulated manipulation, create simple/convex collision proxies,
physical materials, mass properties and contact/constraint checks. Before
expanding to the whole home, promote agreed room measurements and component
relationships into an authoritative architectural model. See
[the skill review](skills-research.md) for the relevant archviz, BIM/CAD and UE
physics workflows.
