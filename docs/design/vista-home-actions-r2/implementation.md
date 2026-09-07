# Six-room actions and VISTA review

The connected Home now has 46 bound entities, the 40 action IDs in the frozen
indoor catalog, and two explicit extensions: `step_down` and `unequip`. The
player can use these through first- or third-person controls or the local typed
action bridge. Seven legacy VISTA events run against the same scene state.
This is a native interaction review build; visual acceptance and benchmark
release still require review.

The current runtime is `build-r` in `project-s`, under
`runs/vista-photoreal-design-r1/home-actions-r2-20260907a`. Its source and contract
bytes match this worktree. The [implementation manifest](implementation-manifest.json)
binds the binaries, map, modeling artifacts, source contracts, validation reports
and seven recorded cases by SHA-256. Generated media, UE projects and Blender
files remain outside Git.

## Play and inspect

Select **VISTA Photoreal Home** in Sunshine/Moonlight. The Home review uses display
`:119` and starts in the entry hall with the first-person body visible. The
previous accepted embodied build remains available in its original run folder.
Only the Home app entry was updated; the other five Sunshine entries, R23, R6
and Sunshine authentication were preserved.

| Control | Behavior |
| --- | --- |
| WASD / mouse | Walk and look; Shift jogs |
| Tab | Switch first/third person, including while holding an object |
| E / left click | Perform the selected contextual interaction |
| Mouse wheel | Select another available interaction |
| F / C | Inspect / crouch |
| B | Equip or remove the backpack |
| G | Drop the held object or cancel an active action |
| 1–6 | Entry, living room, kitchen, bedroom, office, bathroom/laundry |
| F2 / R | Cycle the seven VISTA events / reset the episode |

Room shortcuts are disabled while carrying an object. Carrying between rooms
uses normal movement and collision. Movement is briefly locked during a reach
or initial lift so that the body cannot walk away from a contact transaction.

| Space | Implemented interactions |
| --- | --- |
| Entry | Exit and five interior doors, shoe bench sitting, arrival with keys/phone, exit event checks |
| Living room | Sofa sitting, key and slipper pickup, table placement, lamp/TV controls, visible spill and trip reactions |
| Kitchen/dining | Cup, jug and two-hand pot handling; pour/spill; table placement; stove control; fridge door and storage |
| Bedroom | Bed sitting, phone pickup and carry, bedside drawer, four wardrobe leaves, backpack pickup/equip/unequip |
| Office | Chair push/pull/sit, desk and monitor, two cabinet leaves, ladder ascent/descent, two-hand high-box pickup |
| Bathroom/laundry | Bath and basin taps, water level/overflow, toilet flush, basket lid/storage, clothes load/unload, washer door/control/drum |

The interaction set covers the authored entities in `scene.json`. Decorative
meshes outside that set do not automatically acquire interaction behavior.

## Actions, contact and state

`AHomeActionsCharacter` extends the accepted 53-bone embodied character with
typed action transactions. The base animation hooks default to zero so that
the earlier embodied review retains its behavior. `HomeActionMotion` and
`HomeActionClimb` supply reach, grip, two-hand, seating and supported ladder
motion; object controls and visible effects share the same runtime state.

Grasped objects have simple physics collision and resume gravity on release.
Pot and box grips use both wrists. Pinch and thin-object hand profiles supplement
the original grip. Doors test their future swept volume against the body;
drawers, chair movement and storage entry paths also check collision. Single-slot
storage validates the role, aperture, fit and ownership on both sides. Washer
operation requires a closed door and loaded clothes, and locks the running door.

Pouring tilts the held jug toward the selected receiver with rim clearance,
transfers only the available capacity and conserves tracked volume. Tipping or
impact can empty a vessel and create a visible puddle on the contacted support.
These are analytic liquid levels and effects, not a fluid solver. Seat anchors
follow moved furniture. Ladder motion checks sole support on physical treads
and sweeps the torso; descending restores the normal walking capsule.

Commands bind exact entity IDs, session, revision, generation and command ID.
The bridge publishes atomic state/response files. It rejects stale sessions,
extra fields, ambiguous IDs, conflicting replays and concurrent actions. An
identical replay returns the original receipt without committing twice.
Cancellation and reset restore the object, physics, attachment, ownership,
player, seat and platform state captured by the transaction.

Wrist errors are measured after skeletal animation. Non-contact terminal poses
report null wrist-contact error; diagnostic distances before recovery use
separate fields. A small wrist error is evidence about the IK target, not a
measurement of every finger against the mesh. Fingertip alignment, backpack
straps and some clothing/ankle deformation still need visual refinement.
Falls are procedural poses rather than a ragdoll, and fabric uses authored
geometry rather than cloth simulation.

## Frozen events and VISTA boundaries

The source house, catalog, bindings and seven event files are unchanged and
hash-bound in the manifest. Their original readiness fields are preserved in
the projected contract. The new contract also retains pending authoring flags;
native test results live in the separate implementation/coverage records.

| Event | Original success condition | Failure behavior exercised |
| --- | --- | --- |
| mmg_001 | Stove switched off | Exit while the stove remains active |
| mmg_013 | Slipper picked up | Visible spill marker |
| mmg_021 | Bath tap switched off | Overflow / timeout |
| mmg_040 | Ladder inspected | Sit on the rolling chair |
| mmg_044 | Keys entity reaches the entry hall | Exit before bringing keys |
| mmg_045 | Phone entity reaches the entry hall | Exit before bringing phone |
| mmg_070 | Washer running | Timeout |

In particular, `mmg_040` does **not** define high-box retrieval as its success
condition. Actual ladder climbing and box pickup have separate native detail
tests. No NPC replay or new oracle is substituted for these source definitions.

`capture.py` records continuous native X11 video with the scenario HUD hidden
and samples runtime state into privileged evidence. `record_events.py` produced
seven real 1920×1080 recordings, then `export_review.py` created candidates with
`needs_review`, no final category and no oracle. The final viewer directory is
`vista-review-candidates-b/<opaque-case-id>/`; the earlier event-named export
attempt remains retained outside model inputs.

Only `restricted/observation.mp4` and the selected external dialogue enter
`MllmEvalInputV1`. Source event IDs, setup, seeds, render scripts, runtime state,
receipts and review notes remain privileged. Each input and its
`AgentAssistanceResponse` shape passed validation against VISTA's actual
`contracts/downstream.py`, digest
`96d383d8e60038ad59766bf8a483e52c610ffd80436496f504452fcf2e0bdc0a`.
There were no model calls or paid generation requests.

The dialogue is project-authored external text, not recorded speech. The clips
include action completion. Formal assist-step evaluation needs a reviewed
observation cutoff and label; simulator success alone does not determine whether
assistance was needed at an earlier instant.

The companion VISTA-Web branch `codex/native-home-review-r2` adds the
`/native-home-review` page and a read-only development service on port 8001.
It plays the seven videos, seeks to dialogue timestamps, exposes the restricted
input for inspection/download and downloads a local reviewer draft. It verifies
video hashes, bundle containment and capture/input policy before serving files.
Simulation outcomes shown to the human reviewer are excluded from the model
input. Review drafts do not update canonical ledgers. Production port 8000 is
outside this integration.

## Validation and artifact lineage

The run's `validation/native-coverage-final.json` indexes the latest supplied
result for each named test, retaining earlier failed attempts and receipt IDs.
All 40 source actions and both extensions have successful native receipts in
the selected passing cases. This is cumulative evidence: build o supplied the
sequence/protocol baseline, p supplied detail fixes and r supplied the final
box grip correction. It is not a claim that every test was rerun on build r.

| Check | Result |
| --- | --- |
| World contract/compiler and focused regressions | 32 passed |
| Existing review launcher compatibility | 5 passed |
| Native event/interaction sequences | 21 passed |
| Latest native detail cases | 34 passed |
| Native transaction protocol | 14 passed |
| Actual Sunshine keyboard controls on build r | 11 passed |
| Unreal Linux Editor / Game Development / Shipping build r | Successful |
| VISTA router tests, including malformed JSON shapes | 6 passed |
| VISTA frontend production build | Passed |
| Actual VISTA input-contract validations | 7 passed |
| Browser playback / candidate catalog | 7 playable / 0 rejected |
| Mobile layout / local review-draft download | Passed |

Native recording medians were **17.9–19.8 FPS** on the shared GPU; the encoded
20 FPS container rate is not a 60 FPS performance claim. The captures use
build q/project-r, while live Sunshine uses build r/project-s. The final build
adjusted box grip reach and terminal diagnostics; recording and release hashes
are recorded separately.

Modeling derives from the accepted whole-home Blender scene and CC0 embodied
character described in the [previous implementation](../vista-photoreal-r1/embodied-implementation.md).
`model-c` contains 54 split/rebuilt parts. `model-d` supplies the bed-drape and
clothes corrections. `hands-a` contains mirrored pinch/thin grip authoring.
Imports d/e and repair i establish the map's final geometry: operable room
doors, furniture leaves, open washer cavity, storage supports and exact labels.
The import-d report was written successfully before an allocator error during
editor shutdown; its exit was not accepted as a clean import. Later native
loading and interaction tests verify the saved assets. Import e exited cleanly.
All failed attempts remain retained. The original accepted build-v DLL,
project-f project and map hashes were rechecked unchanged.

For reproduction, first build the plugin into a fresh package directory. Use
`tools/ue/vista_home_actions_r2/prepare_project.py` to copy the accepted project
and install the package/contract without editing the original. Run Blender
`build_parts.py` and `build_hand_profiles.py` into fresh output directories, then
UE `import_parts.py` with `VISTA_HOME_ACTIONS_CONFIG` pointing to the selected
parts, contract, hands, fresh asset root and result path. Use UE's
`-run=pythonscript -script=...` commandlet. `validate_bindings.py` resolves only
superseded copies owned by that parts set and checks each entity label is unique.
Import receipts establish authoring, not runtime acceptance.

The launcher opts into `VistaHomeActionsCache`, reads the accepted cache without
modifying it and writes new DDC data under `/data/sysx/cache`. The original
profiles retain their previous defaults. Fresh validation runtimes use display
`:120`; the tested validation service is stopped at handoff. Do not run input
probes against an active Sunshine client. Current Home status can be read with:

```sh
uv run python tools/runtime/vista_photoreal_r1/review_session.py \
  --profile /data/sysx/vista-world/runs/vista-photoreal-design-r1/home-actions-r2-20260907a/sunshine-review-profile-r.json \
  --action status
```
