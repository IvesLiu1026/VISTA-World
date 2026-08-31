# VISTA EventSpec v2 expansion r1

This milestone adds deterministic `npc.resident` action queues to three existing,
verified VISTA events. Each v2 document is an additive projection: the exact v1
operation prefix and all public goals, triggers, outcome conditions, source fields,
timeouts, and reset policy remain unchanged.

## Added projections

| Sample | Catalog-bound queue | Preserved outcome |
| --- | --- | --- |
| `mmg_040` | navigate to office; inspect high box; inspect unstable rolling chair; inspect ladder | box inspection triggers the event and ladder inspection satisfies the original success condition; no unsupported climb/step-up action is invented |
| `mmg_044` | navigate to living room; inspect keys; pick up keys; navigate to entry; targetless drop | dropping after entering the entry hall moves the keys to the room required by `keys_at_entry` |
| `mmg_045` | navigate to bedroom; inspect phone; pick up phone; navigate to entry; targetless drop | dropping after entering the entry hall moves the phone to the room required by `phone_at_entry` |

All three documents bind the exact `vista_indoor_actions_r2` digest
`07eb0a4740ea214c15fa59504b0b923787c23fa0b9232adfc18a0efc0cec7e35`.
The only wire actions introduced are `navigate_to`, `inspect`, `pick_up`, and
targetless `drop`, which already map to `NavigateTo`, `Inspect`, `PickUp`, and
`Drop` in the current TCP/NPC runtime.

The key and phone queues intentionally do not open the exit door. In the immutable
v1 fixtures, `exit_opened_without_keys` and `exit_opened_without_phone` are simple
interaction conditions, not compound predicates, so any queued `open_door` would
record failure even after the item arrived.

## Still blocked

- `mmg_001` remains v1-only. Completing it needs a real stove deactivate
  toggle/press backend, state-commit contract, and matching character/appliance
  animation.
- `mmg_021` remains v1-only. Completing it needs a real faucet deactivate
  toggle backend, water-state commit, and matching hand/faucet animation.
- `mmg_070` remains v1-only. Completing it needs a real washer start-button press
  or toggle backend, washer-state commit, and matching press/appliance animation.

An `inspect` substitute would not satisfy any of those original entity-state
success conditions. Do not publish v2 projections for them until the actual
toggle/press path exists end to end.

## Validation

Run from the repository root:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.:tools uv run python -m unittest \
  tools.tests.test_vista_playable_home_event_v2_expansion \
  tools.tests.test_vista_playable_home_event_v2 \
  tools.tests.test_vista_playable_home_event_v2_compiler -v
uv run ruff check tools/tests/test_vista_playable_home_event_v2_expansion.py
git diff --check
```

The compiler sidecar remains `accepted: false` and
`runtime_execution_authorized: false`; this milestone proves deterministic,
catalog-bound source semantics and does not itself promote animation or runtime
acceptance.
