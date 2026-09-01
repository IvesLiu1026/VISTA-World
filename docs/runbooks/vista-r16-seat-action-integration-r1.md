# VISTA R16 seat action integration R1

## Status

The R16 source integration and offline Unreal verification pass. This milestone
does **not** claim a packaged, visually accepted or Sunshine-playable scene. It
also does not claim that Pour is integrated; Pour remains a separately tracked
two-target runtime slice.

## Integrated action path

The stable action sequence is:

```text
player / typed TCP / finite NPC queue
  -> shared semantic action executor
  -> reserve the exact seat
  -> align and play the approved R15 montage
  -> vista_sit_completed or vista_stand_completed
  -> commit posture and occupancy/vacancy
  -> atomically finalize session generation and terminal action receipt
  -> record one successful VISTA interaction
```

`vista_seated_idle_cycle_completed` is internal animation authority. It restarts
only while the posture component still authorizes the seated loop; it is not an
EventSpec or TCP action.

The player cannot move, sprint, crouch or jump while posture is non-standing.
Look input stays enabled so a seated human operator can still rotate the camera.
Pressing the contextual interaction while seated selects Stand from the exact
active seat. NPC whole-queue preflight simulates posture and accepts
`Sit -> Stand` while rejecting standing-only actions between them.

## Transaction and rollback contract

Sit and Stand retain their original physical snapshots through terminal
finalization. A completion signal changes posture, but the action is not durable
until the ledger and session generation can terminalize together on the game
thread.

- failed Sit restores the original standing transform, attachment and movement
  state and leaves the seat vacant;
- failed Stand restores the retained seated snapshot and exact occupancy;
- Sit/Stand postconditions verify the exact requester actor and semantic
  identity, not merely a non-empty `occupied_by` field;
- a stale generation or terminal-ledger precondition failure compensates posture
  and does not advance session generation;
- seat or occupant destruction clears authority-side reservations/occupancy;
- Event reset rejects active executor, reservations or durable seated posture
  instead of silently moving the character.

The same atomic finalizer now protects pickup, place and drop from advancing the
session generation before their terminal receipt is publishable.

## Verification evidence

Focused Python validation passed on 2026-09-01:

- 71 focused tests for the action executor, semantic executor, appliance action
  gates, typed ripple, NPC navigation, R16 posture integration, seat core and
  Pour primitives;
- 113 EventSpec/TCP/runtime/Unreal source tests plus 41 subtests;
- Ruff and `git diff --check`.

A fresh UE 5.7.3 BuildPlugin attempt succeeded for UnrealEditor Development,
UnrealGame Development and UnrealGame Shipping:

```text
/data/sysx/vista-world/runs/vista-action-world-r1/
  playable-actions-r2-plugin-build-r16-20260901e
```

The plugin was copied into a disposable project and executed with NullRHI. The
exact automation test found one test and completed with `Result={Success}` and
process exit code 0:

```text
VISTA.PlayableHome.SeatPosture.ActionExecutorIntegration

/data/sysx/vista-world/runs/vista-action-world-r1/
  seat-action-r16-ue-automation-20260901c/UnrealEditor.log
```

The proof covers Sit success, Stand success, post-contact Sit rollback, exact
post-contact Stand rollback, atomic terminal/generation finalization and a
stale-generation failure that compensates posture without advancing generation.

## Remaining acceptance gates

- Map the four current `static_furniture + sit` entities to `AVistaSeatActor`
  with category-specific capsule/root anchors.
- Build and package a fresh exact-tip scene candidate outside Git.
- Verify scale, clipping, seated loop, contextual Sit/Stand, 360-degree camera
  and reset behavior through Sunshine/Moonlight.
- Add a dedicated two-client replication proof before calling networked posture
  accepted.
- Complete the separate Pour integration and interactive receiver composition.

Root storage was approximately 143 MiB free after the offline proof. Future UE
builds, projects, DDC and logs must use `/data`; no further runtime launch should
write material build output to the root filesystem.
