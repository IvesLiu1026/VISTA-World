# VISTA R18 Player Action Selector R1

## Outcome

R18 adds a compact player action selector without replacing the accepted
context controls. `E` still executes the existing default action, `Q` drops the
held item, and `I` enters or exits Inspect. The selector adds:

- `R` or mouse wheel: cycle the executable actions for the current context;
- `F`: execute the selected action;
- a restrained HUD row showing the selected action and its position in the
  current action list.

This is a source milestone. It does not claim a packaged or Sunshine-accepted
demo and it does not start, stop, or modify any UE, GPU, or streaming service.

## Closed action surface

The cycle order is deterministic:

1. Press
2. TurnOn
3. TurnOff
4. Open
5. Close
6. Inspect
7. Sit
8. Stand
9. Pour
10. PickUp
11. Place

Drop remains an explicit `Q` control and Toggle is not presented as an
ambiguous player action. Stateful appliances expose the concrete TurnOn or
TurnOff operation that matches their replicated state.

## Executability projection

The client rebuilds the list from the focused interactable, held pickup, and
posture state. It omits actions when known local preconditions fail:

- no options while Inspect, another action transaction, or a posture
  transition is active;
- Open/Close and TurnOn/TurnOff are filtered by exact replicated state;
- Press requires a powered appliance and a valid authored press profile;
- Sit requires a free, unreserved seat; seated posture exposes only Stand on
  the character's exact active seat;
- PickUp requires a portable non-held pickup and an empty inventory slot;
- Pour requires the exact held source, a free typed receiver, and a successful
  positive-capacity `PlanPourTransition`;
- Place requires an exact stable placement anchor for the focused owner.
- every option requires the same approved mutation-animation gate used by the
  shared executor; missing provider/montage authority hides the option.

This projection prevents knowingly invalid actions from being advertised. It
is not an authority bypass: between presentation and input the world may
change. The server therefore rebuilds the same list, matches the exact
`(affordance, target, secondary target)` tuple, and rejects stale requests.

## Mutation authority

All accepted actions stay on existing authorities:

- PickUp and Place call `BeginPhysicalInteraction`;
- Pour and semantic actions call `BeginSemanticInteraction`;
- Inspect calls the existing animation-gated Inspect entry.

The selector never calls `VistaInteract` directly and never mutates actor
state from HUD or input code.

## Source validation

Run without starting Unreal services:

```bash
PYTHONPATH=.:tools uv run pytest -q \
  tools/tests/test_vista_playable_home_r18_player_action_selector.py \
  tools/tests/test_vista_playable_home_hud.py \
  tools/tests/test_vista_playable_home_action_executor.py \
  tools/tests/test_vista_playable_home_semantic_action_executor.py
git diff --check
```

The next integration gate is an Unreal compile plus a human input pass in a
composed scene containing an appliance, articulated container, seat, pourable
source, liquid receiver, pickup, and tagged placement anchor.

Current source evidence:

- focused selector/executor/HUD/posture/pour suites: `97 passed`;
- required contract/compiler baseline: `28 passed`;
- `git diff --check`: passed.
