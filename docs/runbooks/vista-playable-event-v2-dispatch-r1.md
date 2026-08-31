# EventSpec v2 loopback dispatcher (development-only R1)

This bridge revalidates an EventSpec v2 runtime-action sidecar against all of
its source contracts, probes the current loopback VISTA TCP session, starts one
event, and replaces one NPC queue using the authoritative
`session_generation` returned by the preceding response.

It is a **human-operated, unaccepted, nonpromotable development demo**. The
compiler sidecar remains `accepted=false` and
`runtime_execution_authorized=false`; dispatching it does not create research
acceptance, evidence, or animation verification. The tool does not launch,
stop, reset, or poll Unreal and never connects anywhere except `127.0.0.1`.

## 1. Create a fresh sidecar

From the repository root:

```bash
mkdir -p /tmp/vista-event-v2-dev
PYTHONPATH=. uv run python -m tools.worlds.playable_home_event_v2_compiler \
  --house world_packs/vista_playable_home_r1/house.json \
  --base-events-dir world_packs/vista_playable_home_r1/events \
  --events-v2-dir world_packs/vista_playable_home_r1/events_v2 \
  --action-catalog \
    world_packs/vista_playable_home_r1/action_catalogs/vista_indoor_actions_r2.json \
  --output /tmp/vista-event-v2-dev/runtime-action-plan.json
```

## 2. Validate and inspect without connecting

```bash
PYTHONPATH=. uv run python -m \
  tools.runtime.vista_playable_home.event_v2_dispatch \
  --sidecar /tmp/vista-event-v2-dev/runtime-action-plan.json \
  --house world_packs/vista_playable_home_r1/house.json \
  --base-events-dir world_packs/vista_playable_home_r1/events \
  --events-v2-dir world_packs/vista_playable_home_r1/events_v2 \
  --action-catalog \
    world_packs/vista_playable_home_r1/action_catalogs/vista_indoor_actions_r2.json \
  --event-id mmg_013 \
  --operation-id op.05 \
  --dry-run
```

Dry-run performs full compiler validation but opens no socket. Inspect the
printed `runtime_actions` before approving a live developer run.

## 3. Dispatch to an already-owned runtime

Only the current runtime owner should run this after confirming that the UE
session on port `55620` is disposable and has no active event:

```bash
PYTHONPATH=. uv run python -m \
  tools.runtime.vista_playable_home.event_v2_dispatch \
  --sidecar /tmp/vista-event-v2-dev/runtime-action-plan.json \
  --house world_packs/vista_playable_home_r1/house.json \
  --base-events-dir world_packs/vista_playable_home_r1/events \
  --events-v2-dir world_packs/vista_playable_home_r1/events_v2 \
  --action-catalog \
    world_packs/vista_playable_home_r1/action_catalogs/vista_indoor_actions_r2.json \
  --event-id mmg_013 \
  --operation-id op.05 \
  --port 55620 \
  --socket-timeout-s 1.0 \
  --acknowledge-unaccepted-dev-only
```

The bounded sequence is exactly:

1. `status` — require `READY`, the bound world revision, an inactive event,
   and read the current generation;
2. `start_event` — use that generation and require `EVENT_STARTED` plus an
   increment of exactly one;
3. `npc_queue` — use the returned generation and require `QUEUE_REPLACED`, the
   exact NPC semantic identity, and one further increment.

The projection converts the compiler's provenance ID
`mmg_013/op.05/000` to the UE-safe `mmg_013.op.05.000`, resolves
`npc.resident` through the validated HouseSpec to the resident entity semantic
ID, and resolves navigation rooms to `/anchor.room_center`. It maps
`target_id`, owner-local `placement_anchor_id`, `duration_s`, and `utterance`
to the TCP fields `target_semantic_id`, `placement_anchor_id`, `duration_sec`,
and `speech`. Every action receives the HouseSpec NPC timeout; a positive
duration receives a two-second completion margin, still capped by the UE
300-second bound. A targetless `drop` never receives a target field.

If the initial probe reports an active or terminal-but-not-reset event, the
dispatcher stops without mutation. Reset that disposable session through its
separately reviewed runtime workflow, then retry. A failure after
`start_event` is intentionally not auto-rolled-back; the result identifies the
exact failed step for the runtime owner to inspect.

Focused offline tests:

```bash
PYTHONPATH=. uv run python -m unittest \
  tools.tests.test_vista_playable_home_event_v2_dispatch -v
```
