# VISTA R19 Container Transactions R1

Status: source-complete, production fail-closed, not gameplay-packaged, not accepted

## Scope

R19 implements the first one-slot typed storage primitive for the approved T19
chain:

```text
open -> insert -> close -> open -> remove
```

The transaction always binds the same three authorities:

- requester/carrier;
- exact `AVistaPickupActor` as the primary target;
- exact `AVistaContainerActor` as the secondary target.

`Insert` and `Remove` are appended to the C++ affordance/action enums. Existing
enum values retain their order. EventSpec and ActionCatalog v1-v4 files are not
modified by this slice; in particular, the EventSpec v3 TCP preflight allowlist
remains closed to both actions.

The exact appended C++ wire values at this base are:

- `EVistaAffordance::Insert = 13`, `Remove = 14`;
- `EVistaNpcActionType::Insert = 24`, `Remove = 25`;
- `EVistaPickupDisposition::Contained = 3`.

Loopback TCP spells both affordance and NPC-queue verbs as lowercase `insert`
and `remove`. In both request forms, `target_semantic_id` is the exact pickup
and `secondary_target_semantic_id` is the exact container.

## Authoritative state

The container owns a replicated single-slot identity and an authored
`ContentsAnchor`:

```text
storage_capacity = 1
contents_count = 0 | 1
contained_item = <exact semantic id> | ""
```

The pickup remains the only body/attachment authority. A contained pickup uses
the appended `EVistaPickupDisposition::Contained`, is attached to the exact
container contents anchor, is absent from carrier inventory, and exposes:

```text
held = false
held_by = ""
contained_in = <exact container semantic id>
```

Public state patches cannot forge container contents or pickup disposition.
Event reset uses a separate trusted baseline path and restores non-pickup
container state before pickup attachment/inventory state.

## Transaction flow

Both actions use `UVistaActionExecutorComponent::BeginSemanticInteraction` for
local-player-compatible requests, NPC queues, and loopback TCP interactions:

```text
validate exact identities and current state
  -> reserve container and item as one tuple
  -> approach and align to ContentsAnchor
  -> play dedicated action animation
  -> typed contact signal
  -> commit item body/inventory and container contents
  -> verify joint before/contact/after evidence
  -> publish one terminal transaction and one VISTA observation
  -> release both reservations
```

The transaction receipt records the item as `TargetSemanticId`, the container
as `SecondaryTargetSemanticId`, both semantic state snapshots, the pickup
physical snapshot, two semantic mutations and one physical mutation. A terminal
success records exactly one interaction observation against the container.

Rejected pre-contact cases include:

- closed or already reserved container;
- full single-slot container;
- item not on the exact allowlist;
- insert item not exactly held by the requester;
- remove item not exactly contained in the requested container;
- occupied requester inventory on remove;
- mismatched primary/secondary semantic identity.

## Rollback and teardown

Any failed step after contact restores state while both reservations remain
held. The order is intentional:

1. restore exact container `open` and contents snapshot;
2. restore exact pickup runtime/body/attachment snapshot;
3. restore the requester's exact inventory item;
4. reread and compare both semantic states and the physical snapshot;
5. release item and container reservations together.

Pickup, container, and executor teardown paths also clear the peer reservation.
Finalization treats an already-cleared peer teardown as idempotent success.

## Player, NPC, TCP, and VISTA boundaries

- The shared executor accepts the same two-target request shape used by the
  existing player action path. The R18 selector file is intentionally untouched
  in this isolated worktree; exposing `Insert`/`Remove` in its visible action
  list is a coordinator-owned follow-up after the animation gate closes.
- NPC queue shape, read-only queue simulation, action start, polling, and result
  identity all route through the shared semantic executor. The simulation tracks
  container open/contents state so the full five-action chain can preflight
  atomically once approved animations exist.
- Direct loopback TCP `interaction` and non-EventSpec `npc_queue` accept
  `insert`/`remove` with an exact `secondary_target_semantic_id`.
- `contained_in_semantic_id` is projected only for Insert/Remove transaction
  physical-state JSON; prior action receipts do not gain an empty member.
- Frozen EventSpec v3 preflight does not authorize either action. This worktree
  does not edit any EventSpec/ActionCatalog schema or payload.
- Success records one VISTA interaction observation for the container; rejected,
  canceled, timed-out, and rolled-back actions record none.

## Animation hard gate

There is no dedicated Insert or Remove montage/materialization in base
`a83410e3`. R19 deliberately does not edit `VistaAnimationComponent`, character
providers, retarget assets, or animation profiles.

Production calls therefore fail `UVistaAnimationComponent::SupportsAction`
with `ANIMATION_ACTION_UNSUPPORTED` before reservation or mutation. A future
animation authority must both declare the route and pass
`HasApprovedMutationAnimation`; enum membership alone is insufficient. The
dev-automation entry point may bypass animation readiness only to prove the
real transaction, rollback, and teardown code. Until dedicated
contact/completion animation authority is materialized and reviewed, this slice
is **not playable and not accepted**.

No Insert/Remove signal names are declared by this branch:
`ContactSignalFor(Insert|Remove)` and
`CompletionSignalFor(Insert|Remove)` both remain `NAME_None`. The animation
authority must add dedicated mappings; adding only `SupportsAction` would still
fail at `ANIMATION_COMPLETION_CONTRACT_MISSING`.

## Validation

Focused Python/source regression:

```bash
TMPDIR=/data/sysx/tmp/vista-r19-container-transactions \
UV_CACHE_DIR=/data/sysx/uv-cache \
PYTEST_ADDOPTS='-o cache_dir=/data/sysx/cache/pytest-vista-r19-container-transactions' \
PYTHONPATH=.:tools uv run pytest -q \
  tools/tests/test_vista_playable_home_r19_container_transactions.py \
  tools/tests/test_vista_playable_home_action_executor.py \
  tools/tests/test_vista_playable_home_semantic_action_executor.py \
  tools/tests/test_vista_playable_home_npc_navigation.py \
  tools/tests/test_vista_playable_home_r17_pour_executor.py \
  tools/tests/test_vista_playable_home_event_outcomes.py
```

Observed result: `59 passed, 4 subtests passed`.

The required legacy contract/compiler gate also passed `28/28` with `unittest`.
A complete `tools/tests` run observed `2248 passed, 1 skipped, 209 subtests`
and five failures. The one failure caused by this append-only enum change was a
stale R16 assertion that required `Stand` to remain the final member; it was
updated and its focused suite now passes. The remaining four are deliberately
not repaired here:

- the sealed R5 projection detects the new compiled C++ proof path; coordinator
  regeneration is required after all C++ lanes merge and this branch may not
  edit that projection;
- three failures are in untouched base paths (the external-forge digest, the
  presentation-import digest, and the existing indoor-camera `Tick` assertion).

Fresh UE 5.7.3 `BuildPlugin` evidence:

```text
/data/sysx/vista-world/runs/vista-action-world-r1/
  playable-actions-r2-plugin-build-r19-container-20260901d
```

Observed result: Editor Development, Game Development, and Game Shipping all
compiled; `BUILD SUCCESSFUL`. This also compiles the real automation test:

```text
VISTA.PlayableHome.ContainerTransactionsR19.AtomicInsertRemove
```

The coordinator still needs to run that test in a fresh NullRHI automation host
because this isolated worker owns no UE runtime/GPU/service lifecycle.

## Remaining acceptance work

- materialize and approve dedicated Insert and Remove montage/contact/completion
  signals for the active character provider;
- add the two actions to the player selector only after animation readiness can
  pass;
- merge the separately versioned EventSpec/ActionCatalog authority without
  changing frozen older bytes;
- run the compiled UE automation proof, package a fresh isolated candidate, and
  capture two-client plus Sunshine human evidence;
- do not check T19 complete until the package and human interaction gates pass.
