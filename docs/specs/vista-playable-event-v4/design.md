# VISTA Playable Event v4 Design

## Authority chain

```text
frozen v3 catalog --exact digest--> v4 readiness overlay --R15 candidate-->
frozen EventSpec v3 --exact digest/prefix--> EventSpec v4 --> validated projection
R18 typed profile --exact digest/roles------^          |
                                                      --> source-only compiler
                                                      --> closed preflight envelopes
```

V4 is an overlay. It imports existing validators rather than restating old behavior.
The source v3 event remains the authority for inherited queue bytes; appended v4
actions are separately validated.

## Files

- `catalog_v4.py` and `vista_indoor_actions_r4.json`: exact r3 semantic overlay with
  R15 candidate provenance and fail-closed readiness.
- `vista-playable-action-catalog-v4.schema.json`: closed catalog representation.
- `vista-playable-event-v4.schema.json`: closed EventSpec grammar and exact source-v3
  binding.
- `playable_home_event_v4.py`: digest, authority, prefix, identity, and sequence
  validation.
- `playable_home_event_v4_compiler.py`: deterministic unaccepted runtime sidecar.
- `event_v4_dispatch.py`: read-only preparation and envelope generation only.
- `events_v4/mmg_013.json`: a source-only contract fixture extending the exact v3
  safe-remediation queue. It is not original-action ground truth or runtime evidence.

## Event model

Each v4 event contains the same house and interaction binding identities as v3, a v4
catalog binding, an exact R18 typed-scene binding, and
`derivation.source_v3_event`. Queue IDs and NPC IDs must match the source v3 event.
Each v4 action list begins with the exact source v3 action list and may append only the
closed typed-scene suffix.

The fixture appends a contract exercise only: Sit/Stand on an exact seat entity and
PickUp/Pour using an exact source and receiver. It remains labeled
`source_only_contract_extension_not_vista_action_replay` by the compiler.

## Typed identities

- `sit.target_id`: `seat` role, exact house entity promoted by the typed profile.
- `stand.target_id`: `seat` role, exact current seated target.
- `pour.target_id`: `primary_source` role, exact held typed liquid source.
- `pour.secondary_target_id`: `secondary_receiver` role, exact compatible typed
  liquid receiver.

The frozen house lacks liquid receiver taxonomy, so v4 separately binds the exact R18
typed-scene profile. The appended PickUp must name its water-jug source and Pour must
name a distinct glass/bowl receiver with a compatible liquid type and positive
capacity. Runtime liquid mutation remains deferred to the UE adapter milestone, and
no acceptance is promoted.

## Sequence state

Projection begins by replaying only the exact v3 prefix through the v3 validator. The
closed suffix permits typed-scene Sit/Stand, navigation inside the NPC patrol set,
PickUp of the exact typed liquid source, and two-target Pour. It tracks
`held_target_id`, `posture`, and `seat_target_id` per NPC. Pour consumes neither
identity and does not invent liquid-state changes.

## Compiler contract

Wire mappings are closed:

- `sit` -> `sit_down` / `Sit` / `sit`
- `stand` -> `stand_up` / `Stand` / `stand`
- `pour` -> `pour` / `Pour` / `pour`

Parameters are copied from a fixed tuple only. Each plan and action carries false
acceptance and runtime authorization. The sidecar is deterministically recompilable.

## Dispatcher boundary

The dispatcher does not open sockets. It validates/recompiles the sidecar and produces
an envelope with `kind=vista_world_action_preflight`, exact event/queue/action IDs,
typed `targets`, closed `parameters`, and false authorization. A later UE adapter must
explicitly support the runtime types and return independent receipts before execution.

## NLP boundary

NLP is upstream and untrusted:

```text
text -> intent candidate -> closed JSON ActionPlan -> schema -> identity allowlist
     -> sequence preflight -> compiler
```

No model output is interpolated into commands, URLs, shell, Python, Unreal object paths,
or file paths. Unknown intents and IDs have no fallback.

## Failure strategy

All validation failures carry stable v4 error codes and JSON paths. There is no
best-effort coercion, alias guessing, target swapping, or basic-geometry fallback.

## Remaining adapter work

Live completion requires a UE allowlist/preflight implementation for Sit, Stand, and
Pour; seat alignment and collision handling; held-container attachment; receiver/liquid
state authority; montage import and notify verification; and visual acceptance receipts.
