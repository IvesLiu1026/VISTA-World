# VISTA Pour Transaction R1

## Scope

This slice adds the closed, authority-side data and actor primitives for a
two-target `Pour` interaction. It intentionally does not wire player/NPC input,
animation selection, EventSpec parsing, TCP dispatch, or the runtime action
executor. Those integration owners can call the private transaction surface
through `UVistaActionExecutorComponent`, which is the only friend of the
receiver besides editor-only proof helpers.

## Closed state

- A source is an `AVistaPickupActor` with `bPourable=true`, a closed lowercase
  `liquid_type`, a finite capacity, and a finite non-zero amount.
- A receiver is an `AVistaLiquidReceiverActor` with a closed receiver kind,
  accepted liquid type, finite capacity, and an amount inside that capacity.
- The source must already be held by the exact requester. `Pour` never claims,
  releases, detaches, places, or otherwise changes that held item.
- The transition transfers `min(source amount, receiver free capacity)` and
  rejects empty, full, malformed, and liquid-type-mismatched states.

## Transaction order

1. Validate requester/source/receiver and compute the transition without
   mutation.
2. Reserve the source using `(executor, command_id)`.
3. Reserve the receiver using the same identity. If this fails, release the
   source reservation before returning a typed error.
4. Snapshot source liquid, receiver liquid, and the complete held physical and
   inventory state.
5. Debit the source, then credit the receiver.
6. If the receiver credit or a final postcondition fails, restore receiver and
   source liquid and verify the complete held snapshot bit-for-bit.
7. The executor explicitly releases both reservations after recording the
   terminal receipt. Release is source-first: the receiver retains the exact
   `(executor, command_id, source)` identity until source release succeeds and
   verifies empty, then clears its own half. The primitives do not silently
   release ownership during commit.

An exact duplicate release is idempotent. If source release fails, neither
half is cleared. If source release succeeds but receiver finalization is
interrupted, the receiver keeps its identity and the same release request
converges on retry. A source reservation owned by any different identity is
reported as `POUR_SOURCE_RESERVATION_DRIFT` and is never cleared.

Authority-side `EndPlay` on either actor snapshots the active executor and
command, verifies the peer and command identity, and clears only that matching
peer reservation. This prevents a destroyed source or receiver from leaving
the surviving half permanently busy without allowing teardown to release a
newer transaction.

The stable success code is `POUR_COMMITTED`. A failed receiver credit that is
fully compensated returns `POUR_SECOND_MUTATION_FAILED_ROLLED_BACK`; an
unverified compensation returns `POUR_COMPENSATION_FAILED` and must be treated
as terminal and fail-closed.

## Focused verification

Run the source contract tests without launching Unreal:

```bash
UV_CACHE_DIR=/data/sysx/vista-world/cache/uv \
  uv run --no-sync pytest -q \
  tools/tests/test_vista_playable_home_pour_transaction_r1.py \
  tools/tests/test_vista_playable_home_action_executor.py \
  tools/tests/test_vista_playable_home_player_pickup_slice.py
```

The authored Editor automation proof is:

```text
VISTA.PlayableHome.PourTransactionR1.AtomicTwoTargetMutation
```

It uses transient carriers, held pickups, and a typed receiver. It proves exact
requester ownership, two-target reservation compensation, a successful bounded
transfer with unchanged held attachment/inventory state, and injected failure
of the second mutation with bit-exact rollback. It also authors source-release
failure, receiver-finalization retry, duplicate-release idempotence, and
source/receiver `EndPlay` cleanup cases. This task does not execute UE,
BuildPlugin, or the automation test; run that only under the coordinator's UE
build/runtime authority.

## Integration checklist

- Extend the shared action executor with a closed pour request carrying both
  source and receiver actor identities. Do not accept object/class/script paths.
- Bind `TargetSemanticId` to the held source and
  `SecondaryTargetSemanticId` to the receiver in signatures and receipts.
- Acquire both reservations before animation/contact and release both only
  after a terminal receipt is durable.
- Call commit only at the approved pour contact notify.
- Preserve these exact actor-level error codes rather than converting failures
  to an untyped boolean.
- Do not expose public runtime-state patches as a transaction bypass.
