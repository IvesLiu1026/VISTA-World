# VISTA EventSpec v5 Storage Contract R1

Status: source-complete, deterministic preflight only, unaccepted

## Purpose

This slice adds a closed source authority for the first T19 storage chain while
preserving every EventSpec/ActionCatalog v1-v4 authority byte. It does not start
Unreal, open a socket, dispatch a command, or authorize runtime execution.

## Catalog derivation

ActionCatalog v5 binds the exact ActionCatalog v4 digest and preserves its 38
action records as an exact prefix. V4 already inherits a generic canonical
`insert`; replacing or widening that record would break source compatibility.
V5 therefore appends two distinct native actions:

- `storage.insert` (`insert` wire, `Insert` UE backend);
- `storage.remove` (`remove` wire, `Remove` UE backend).

Neither action has aliases. In particular, neither resolves through the legacy
generic `insert`, `pick_up`, or `place` semantics. Both actions mutate the exact
item/container tuple at contact and require joint rollback.

## Event derivation and state simulation

The v5 `mmg_013` fixture binds the exact R18 typed scene profile and preserves
the complete v4 queue as an exact prefix. V4 ends while the water jug is held,
so the v5 suffix first performs the exact inherited `drop`, then runs:

```text
open fridge
  -> pick up exact coffee cup
  -> insert exact cup into exact fridge
  -> close exact fridge
  -> open exact fridge
  -> remove exact cup from exact fridge
```

The item must be a portable simulated HouseSpec `pickup` with a matching pickup
interaction binding. The secondary target must be a HouseSpec `container` with
boolean open state and exact open/close binding, making it compatible with the
`AVistaContainerActor` runtime authority. Item and container identities must be
distinct and remain unchanged across the whole chain.

Projection deterministically records, before and after every suffix action:

- held item identity;
- container open state;
- single-slot container contents identity;
- item `contained_in` identity.

Insert requires the exact item held and exact open empty container. Remove
requires the same item contained in the same open container and a free held
slot. The chain finishes with the removed item held and the container empty.

## Animation and acceptance gate

The R19 transaction implementation has no approved dedicated Insert/Remove
animation authority. V5 therefore keeps animation readiness `blocked` and
requires, separately for these actions:

- a dedicated action montage (not reused PickUp or Place);
- typed contact signal;
- typed completion signal;
- runtime acceptance receipt;
- visual/contact review receipt.

Catalog, EventSpec, compiled action, sidecar, and preflight envelopes all remain
`accepted=false` and `runtime_execution_authorized=false`. The dispatcher module
has no exchange, socket, or execute function.

## Validation

```bash
TMPDIR=/data/sysx/tmp/vista-event-v5-storage \
UV_CACHE_DIR=/data/sysx/uv-cache \
PYTEST_ADDOPTS='-o cache_dir=/data/sysx/cache/pytest-vista-event-v5-storage' \
PYTHONPATH=.:tools uv run pytest -q \
  tools/tests/test_vista_playable_home_action_catalog_v5.py \
  tools/tests/test_vista_playable_home_event_v5.py \
  tools/tests/test_vista_playable_home_event_v5_compiler_dispatch.py \
  tools/tests/test_vista_playable_home_v5_legacy_authority_bytes.py
```

The legacy authority test pins the exact SHA-256 of every checked-in v1-v4
action catalog, EventSpec payload, v4 extension fixture, and v1-v4 schema.

Before integration, also run the v3/v4 regressions, `ruff`, `py_compile`, and
`git diff --check`. This source slice is not a playable or accepted demo until
the dedicated animation and live evidence gates close.
