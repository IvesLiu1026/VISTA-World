# VISTA seat/posture runtime core R1

## Status and scope

This change is a source-level, fail-closed runtime core. It does **not** claim
that sit/stand is wired into the player, NPC queue, TCP adapter, animation
component, or packaged demo. No Unreal build or runtime execution was performed
for this source-only change.

The owned runtime classes are:

- `AVistaSeatActor`: one authored `SeatTarget`, one server-local reservation,
  and one atomically replicated occupancy record;
- `UVistaPostureComponent`: the four-state posture authority and the physical
  snapshots required for rollback.

No runtime input may select an attachment component or asset path. The only
valid target is the `SeatTarget` compiled into the selected seat actor.

## Closed state contract

The posture state machine is exactly:

```text
Standing -> SittingTransition -> Seated -> StandingTransition -> Standing
             | rollback          ^             | rollback         |
             +--------------------+-------------+------------------+
```

The rollback destinations are deliberate:

- failed or canceled sit restores the pre-sit standing snapshot and releases
  the reservation;
- failed or canceled stand restores the exact seated snapshot, retains
  `occupied=true` and `occupied_by`, releases only the stand reservation, and
  restores seated-loop authority.

The seat is never considered occupied during approach, alignment, or the sit
montage. `CommitSitAtCompletion` is the sole occupancy commit. Similarly,
`CommitStandAtCompletion` is the sole vacancy commit.

## Physical snapshot closure

Each snapshot records and verifies:

- actor world transform;
- attachment parent identity, component name, socket, and relative transform;
- movement-component identity and active state;
- movement velocity;
- character movement mode and custom mode when present.

A missing or replaced parent/movement component fails closed. Restore is not
reported successful until the current physical state matches the snapshot.

## Seat observations

`AVistaSeatActor::VistaGetRuntimeState` publishes exactly these occupancy
fields for EventSpec/runtime observation:

```json
{
  "occupied": "true|false",
  "occupied_by": "<stable semantic id or empty>"
}
```

They are derived from the replicated `FVistaSeatOccupancyState`. General
runtime-state application cannot forge them. Reservation state remains
authority-local and is not presented as durable EventSpec state.

## Required integration mapping

The integrating branch must preserve this mapping:

| Runtime event | Core call | Required pre-state | Successful post-state |
| --- | --- | --- | --- |
| accepted sit command | `BeginSitTransition(seat, command)` | `Standing` | `SittingTransition`, reserved, not occupied |
| `vista_sit_completed` | `CommitSitAtCompletion(command)` | `SittingTransition` | `Seated`, occupied |
| seated montage cycle | `IsSeatedLoopAuthorized()` | `Seated` | replay only while true |
| accepted stand command | `BeginStandTransition(command)` | `Seated` | `StandingTransition`, still occupied |
| `vista_stand_completed` | `CommitStandAtCompletion(command)` | `StandingTransition` | `Standing`, vacant |
| timeout/cancel/failure | matching rollback method | transition state | exact standing or seated rollback |

Do not infer completion from montage duration. Only the fixed typed completion
signals may call the completion methods. The `vista_seated_idle_cycle_completed`
signal may request another seated-idle cycle only when
`IsSeatedLoopAuthorized()` remains true.

## Source validation

The focused Python contract test is safe to run without Unreal:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. uv run pytest -q \
  tools/tests/test_vista_playable_home_seat_posture_core.py
```

After an integrator compiles a fresh plugin, the UE automation proof is:

```text
VISTA.PlayableHome.SeatPosture.CoreTransactions
```

That proof must be executed before any runtime-playable claim. This branch only
authors the proof source; it does not claim that the proof was compiled or run.

## Remaining integration gates

- Add `UVistaPostureComponent` to both player and NPC semantic actors and bind
  their stable semantic IDs.
- Route target-aware sit/stand montages through the existing animation
  authority without accepting arbitrary asset paths.
- Map typed animation completion/failure signals to the methods above.
- Project posture/seat evidence into the shared action transaction receipt and
  TCP/EventSpec observation surfaces.
- Compile a fresh plugin and run the UE proof plus a dedicated-server/two-client
  replication proof.
- Complete a human-operated playtest before calling the feature playable.
