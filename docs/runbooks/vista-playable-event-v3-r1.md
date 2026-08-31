# VISTA Playable Event v3 R1

## Status and boundary

This milestone is a source contract and transaction design, not a runtime
acceptance claim. Every compiled sidecar and every action remains:

- `accepted=false`
- `runtime_execution_authorized=false`
- without registry, animation, or runtime acceptance receipts

The seven queues are **safe-remediation intervention projections** grounded in
verified VISTA contexts. They are not claimed to replay every original human
action. Original scenario details that remain blocked are not silently counted
as implemented.

## Exact authorities

| Authority | SHA-256 content digest |
|---|---|
| Playable Home house | `d2636c119f6b96793df494fce15b497be857c8994213a5078370a75ff443d1a7` |
| Action catalog v3 | `0f761a4481586c7a684a7cddd188a6adae0ca67b8931fe3a757c6b62a79191cf` |
| Interaction bindings v1 | `261543543ee5370f0ef784a4d44c96351d4e367447046dfd4e40192f955ea0a0` |

The four pre-existing v2 projections (`mmg_013`, `mmg_040`, `mmg_044`, and
`mmg_045`) bind their exact v2 event digest and preserve their queues without
semantic rewriting. The other three projections add these interventions:

| Event | Intervention | Exact postcondition source |
|---|---|---|
| `mmg_001` | stove `turn_off` | `active=false`, `status=idle` |
| `mmg_021` | faucet `turn_off` | `active=false`, `status=idle` |
| `mmg_070` | washer `turn_on` | `active=true`, `status=running` |

`mmg_070` deliberately uses explicit `turn_on`. `press` is present in the
closed compiler mapping as `press_button → Press → press`, but the reviewed
washer interaction binding does not authorize Press. A washer Press event
therefore fails closed; the compiler never substitutes it behind the user's
back.

## VISTA source provenance

The canonical `seed_input` SHA-256 pins from
`scenario_pairing_manifest_2026-05-07` are:

| Sample | Seed input SHA-256 |
|---|---|
| `mmg_001` | `a87544a1fa2c8ee27e016ea471b8f104abd1e4dff111fb595423040e021d4f90` |
| `mmg_013` | `51e3fec2b8a258c02826ff58737e6391f182718f86c5841d9d136935b30d3d41` |
| `mmg_021` | `f4c568e3e39a68fbfb258eb5b5f8d1181f26a2d74952b189cc440f2ee9896116` |
| `mmg_040` | `99d91573f23d9d9457d6925fa7686819ddb81be6ba41d2ec6ce0a73ddff6370f` |
| `mmg_044` | `3918a5d695d406ba7afbe7c99c2bd72748fde5b2c82d116a3c48733a065763e4` |
| `mmg_045` | `76667c389067808eeed0a8535f9b6cfeac35dbc7f3af38b92c05ed109b4c1f52` |
| `mmg_070` | `275da597488ad3736e7497b3696af7cbbf9c59ca04359b403f14fb50e6f44f25` |

EventSpec v3 R1 intentionally has no source-evidence field, so these pins are
documented here rather than injected into a wider schema after review. A later
versioned contract must add a closed evidence binding before these hashes can
become machine-enforced EventSpec authority. No host-absolute source path is
recorded.

## Compiler contract

The closed concrete vocabulary is `Inspect`, `PickUp`, `Place`, `Drop`,
`Open`, `Close`, `Toggle`, `Press`, `TurnOn`, and `TurnOff`, plus navigation.
`Use` is compiler-only syntax:

1. build the exact house baseline;
2. apply the exact bound v1 event overlay;
3. simulate preceding queue postconditions;
4. resolve `Use` through the exact interaction profile;
5. validate every literal and symbolic precondition;
6. emit one concrete action or fail.

Missing state, exact-type mismatch, failed literal comparison, missing runtime
context, ambiguous target, unsupported target action, held-slot conflict, and
unknown placement anchor all fail before a sidecar is produced.

## Transaction protocol

Dispatch preparation recompiles the sidecar from the exact house, catalog,
bindings, v1 events, v2 sources, and v3 events. A self-consistent SHA-256 alone
is not authority. It then checks every room anchor, entity target, support
anchor, NPC, action type, and queue identity against the exact house.

The intended runtime sequence is:

1. observe idle status and authoritative generation;
2. preflight **all** queues with the same generation and exact event, sidecar,
   NPC, action IDs, targets, and parameters;
3. only after every preflight succeeds, start the event;
4. commit queues with generation chaining;
5. drain each unique NPC to an exact terminal last-action receipt without a
   generation change.

Any ambiguous StartEvent response is status-probed inside the rollback
boundary. Any queue request that may have reached the runtime causes every
prepared NPC to be canceled and observed idle, even if the event already
auto-transitioned to inactive. An active matching event is reset, and a final
status must prove `event_status=inactive`, `active_event=null`, and the exact
terminal generation. A different active event is never reset.

## Current runtime gap

The checked-in production TCP adapter on this branch does not implement
`npc_queue_preflight`, and the native appliance actions require the separate
P0/R18 plugin milestone. Consequently this dispatcher requires an injected
exchange and is not a live launcher. The compose commandlet now contains
source mappings for Drop, Inspect, Toggle, Press, TurnOn, and TurnOff, plus a
closed appliance profile:

- stove: heating/idle, TurnOn/TurnOff;
- faucet: flowing/idle, TurnOn/TurnOff;
- washer: running/idle, Press(start→running), TurnOn/TurnOff.

Power, activity, and status remain separate. Unknown appliance categories gain
no extra affordances. These mappings are integration inputs for R18; their
presence is not an acceptance receipt.

## Verification

Run locally without UE, GPU, services, or external APIs:

```bash
PYTHONPATH=.:tools uv run pytest -q \
  tools/tests/test_vista_playable_home_event_v3.py \
  tools/tests/test_vista_playable_home_event_v3_compiler.py \
  tools/tests/test_vista_playable_home_event_v3_dispatch.py

PYTHONPATH=.:tools uv run ruff check \
  tools/worlds/playable_home_event_v3.py \
  tools/worlds/playable_home_event_v3_compiler.py \
  tools/runtime/vista_playable_home/event_v3_dispatch.py \
  tools/ue/vista_playable_home/compose_home_commandlet.py \
  tools/tests/test_vista_playable_home_event_v3*.py

git diff --check
```
