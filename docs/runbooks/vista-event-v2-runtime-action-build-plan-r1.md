# EventSpec v2 → runtime action build-plan sidecar

`tools/worlds/playable_home_event_v2_compiler.py` closes the pure-Python
boundary between a validated VISTA EventSpec v2 queue and the typed action
records required by the runtime. It is additive: the immutable v1 world build
plan remains byte-for-byte unchanged and is bound by schema, plan ID, and
content digest.

## Interface

```python
from tools.worlds import playable_home_event_v2_compiler as compiler

runtime_plan = compiler.compile_runtime_action_build_plan(
    house=house,
    action_catalog=action_catalog_v2,
    base_events=events_v1,
    events_v2=events_v2,
    world_build_plan=world_build_plan_v1,  # optional; compiled if omitted
)
```

Each additive `set_npc_queue` becomes:

```text
event_plans[]
  runtime_queues[]
    operation_id / npc_id / queue_policy
    actions[]
      action_id / sequence_index
      event_action / wire_action
      canonical_action_id / backend_action
      variant_id / variant_readiness
      target_policy / effect / parameters
```

The compiler supports the six core EventSpec actions:

| Event action | Event wire value | Catalog action | Runtime backend |
| --- | --- | --- | --- |
| pickup | `pick_up` | `pick_up` | `PickUp` |
| place | `place` | `place` | `Place` |
| drop | `drop` | `drop` | `Drop` |
| open | `open_door` | `articulation.open` | `OpenDoor` |
| close | `close_door` | `close` | `CloseDoor` |
| inspect | `inspect` | `inspect` | `Inspect` |

Semantics are intentionally not flattened:

- Inspect retains its explicit `target_id`.
- Drop has `target_policy=forbidden` and an empty parameter object; runtime must
  derive the released entity from the held-item slot.
- Place retains both `target_id` and `placement_anchor_id`.
- Open/close select the catalog default variants rather than the rejected
  legacy pickup-motion placeholders. The legacy wire variant remains recorded
  separately for audit.

## Read-only compile check

```bash
cd /home/yhliu/VISTA-World-worktrees/vista-playable-actions-r2
PYTHONPATH=. uv run python -m tools.worlds.playable_home_event_v2_compiler \
  --house world_packs/vista_playable_home_r1/house.json \
  --base-events-dir world_packs/vista_playable_home_r1/events \
  --events-v2-dir world_packs/vista_playable_home_r1/events_v2 \
  --action-catalog \
    world_packs/vista_playable_home_r1/action_catalogs/vista_indoor_actions_r2.json
```

To write an append-only sidecar, add `--output /fresh/path/plan.json`. The
writer is atomic; no UE, Blender, GPU, service, or asset generation is invoked.

Focused validation:

```bash
PYTHONPATH=. uv run python -m unittest \
  tools.tests.test_vista_playable_home_event_v2 \
  tools.tests.test_vista_playable_home_event_v2_compiler -v
```

## Current acceptance boundary

The checked-in `mmg_013` v2 fixture exercises pickup, place, targetless drop,
and inspect. Focused tests synthesize a schema-valid fridge extension and prove
that open and close compile through the same interface, giving exact six-action
coverage without changing the fixture.

The sidecar always sets `accepted=false` and
`runtime_execution_authorized=false`. Compilation proves semantic transport,
not animation acceptance. The UE consumer still has to read
`runtime_queues[].actions[]`, map `backend_action` to the typed runtime enum,
copy `parameters.placement_anchor_id`, and preserve the absent drop target.
