# EventSpec v3 NPC queue preflight R1

This slice adds the missing source-side Unreal bridge for the
`npc_queue_preflight` request emitted by
`tools/runtime/vista_playable_home/event_v3_dispatch.py`.

## Boundary

The TCP adapter accepts one exact top-level request shape:

- `operation = npc_queue_preflight`
- `command_id`, `expected_revision`, and `session_generation`
- `event_id`, `event_content_digest`, and `sidecar_content_digest`
- `queue_id`, `npc_semantic_id`, `replace = true`, and `actions`

Preflight and `npc_queue` commit call the same `ReadNpcQueueRequest` and
`ReadNpcQueueAction` parser. EventSpec v3 preflight narrows the parser to the
eleven runtime action types emitted by the v3 dispatcher and requires the exact
per-action fields. It accepts no class, object path, function, script, or
console-command field.

A successful response has exactly `command_id`, `status`, `code`,
`session_generation`, `queue_id`, `target_semantic_id`, and `action_ids`.
`code` is `QUEUE_PREFLIGHT_OK`; generation is unchanged.

## Read-only guarantee

`UVistaPlayableHomeRuntimeSubsystem::PreflightNpcQueue` validates:

1. revision and generation;
2. inactive event state and one uniquely authored revision-compatible event;
3. a non-empty queue of at most 32 unique bounded action ids;
4. one exact NPC/controller/pawn;
5. action parameters and the production animation approval gate;
6. unique targets, affordances, appliance types, portable-item sequencing, and
   exact placement-anchor tags.

It does not call `ReplaceActionQueue`, `CancelActionQueue`, `StartEvent`,
`CommitCommandGeneration`, any interaction/reservation primitive, or a command
ledger. Parser failures report the current generation. Runtime failures return
the typed queue receipt with the same generation.

The Editor proof
`VISTA.PlayableHome.EventV3.QueuePreflightReadOnly` snapshots event identity,
status, generation, public goal, terminal condition, queue depth, current NPC
action, NPC room, and target state. It checks exact equality after success and
multiple failures. It also proves unchanged preflight-approved input commits,
while generation drift rejects commit.

## Digest authority limitation

Current map actors contain `FVistaEventDefinition`, but no sealed EventSpec or
runtime-sidecar content digests. R1 validates each digest as exactly 64
lowercase hexadecimal characters, but does not compare, echo, or promote it as
authority. `QUEUE_PREFLIGHT_OK` means queue feasibility only. Dispatcher and
receipts remain:

```json
{"accepted": false, "runtime_execution_authorized": false}
```

Authorization must stay false until a separately reviewed composer change
embeds and registers the exact digest authorities. This source slice is not an
accepted or production-authorized runtime receipt.

## Validation

```bash
PYTHONPATH=.:tools uv run pytest -q \
  tools/tests/test_vista_playable_home_event_v3_ue_preflight.py \
  tools/tests/test_vista_playable_home_event_v3_dispatch.py

uv run ruff check \
  tools/tests/test_vista_playable_home_event_v3_ue_preflight.py

git diff --check
```

The Unreal proof is authored but is not execution evidence until an approved
plugin build and Editor automation run execute:

```text
Automation RunTests VISTA.PlayableHome.EventV3.QueuePreflightReadOnly
```

Do not start a build, Editor, GPU job, or live service merely to validate this
source slice.
