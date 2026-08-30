# Design: R9 h CC0 Animation Overlay Plan

Status: Approved for implementation
Updated: 2026-08-30
Depends on: requirements.md

## Summary

Add one standard-library-only planner that validates the immutable inputs for a
future `h → MakeHuman CC0 R8` overlay without creating an attempt directory.
Production configuration hard-codes the accepted `h` and R3 authorities; the
not-yet-published R8 animation and BuildPlugin authorities are represented as
absent optional bindings, so the truthful production result is blocked.

The planner is deliberately not a materializer. A later reviewed phase can
consume the ready report, but it must independently hold file descriptors,
copy into a fresh private staging tree, re-seal the full 9.15 GB parent, run
Unreal NullRHI, and atomically publish a new child.

## Architecture and Flow

1. Validate the closed attempt name and require a nonexistent direct child of
   the fixed VISTA run parent.
2. Read the three small `h` receipt documents with no-follow file opens and
   exact file pins; verify strict JSON, unique keys, canonical content seals,
   schemas, statuses, linkage, legal scope, project/map pins, and tree agreement.
3. Re-hash the current project descriptor and map package.
4. Read and validate the R3 receipt, including its exact 23-record inventory,
   then re-hash each current package using a no-follow open.
5. Verify all planned package paths using a normalized POSIX path contract;
   reject duplicates, case-fold collisions, traversal, and pre-existence in h.
6. If the R8 binding is present, validate the complete executor host/runtime
   receipts: close both receipt-SHA lineage edges, require the exact additive
   project counts, then validate asset classes, sequence observations, terminal
   gates/claims, content delta, nine packages, and inherited R3 bytes.
7. If the BuildPlugin binding is present, walk the actual immutable payload and
   require its root-owned directory/file namespace to equal the manifest, then
   validate exact critical files, publisher/interpreter, policy, and claims.
8. If either optional binding is absent, record the two exact blockers. Future
   bindings cannot be supplied from the CLI.
9. Return one canonical report with negative claims and zero-write evidence.

## Interfaces and Contracts

### CLI

```text
uv run python tools/ue/vista_playable_home/plan_hssd_r2_cc0_animation_overlay.py \
  --attempt-name hssd-r2-cc0-animation-overlay-r1-<suffix>
```

The CLI has no path, provider, map, authority, apply, or execute option.

### Python interface

```python
build_plan(attempt_name: str, *, config: Config = PRODUCTION_CONFIG) -> PreparedPlan
```

Tests may construct a complete fake `Config`; production callers receive only
the fixed `PRODUCTION_CONFIG` from the CLI.

### Report

Schema: `simworld.vista.hssd-r2-cc0-animation-overlay-plan/v1`.

Important fields:

- `mode: dry_run_zero_writes`
- `status`
- `attempt_name`, `attempt_root`
- `parent` receipt/tree/map/project pins
- `character_partition` with exact 23 paths and receipt identity
- `animation_partition` with exact 9 paths and authority readiness
- `plugin_partition` with `replace_tree` policy and authority readiness
- `provider_transition` from City Sample visual demo to `makehuman_cc0_r8`
- ordered `blockers`
- `claims`, all acceptance claims false
- `security` and `legal_scope`
- `content_digest`

## Data Model and Migration

No repository schema or binary data is migrated. The planner emits a transient
JSON value to stdout. It does not write a receipt. Future materialization must
define a new versioned execution and receipt contract rather than treating this
planning document as execution authority.

Target child partitions are closed:

- Parent copy: all sealed `h` bytes, verified again by the future materializer.
- R6 character add: exact 23 packages from the R3 receipt.
- R8 animation add: exact nine packages from the R8 executor contract.
- Plugin replacement: exact whole `Plugins/VistaPlayableHome` tree from the
  reviewed root BuildPlugin authority.

## File Plan

- `docs/specs/vista-r9-h-cc0-animation-overlay-plan-r1/requirements.md`
- `docs/specs/vista-r9-h-cc0-animation-overlay-plan-r1/design.md`
- `docs/specs/vista-r9-h-cc0-animation-overlay-plan-r1/tasks.md`
- `tools/ue/vista_playable_home/plan_hssd_r2_cc0_animation_overlay.py`
- `tools/tests/test_vista_playable_home_hssd_r2_cc0_animation_overlay_plan.py`

## Failure Handling and Rollback

- Malformed or drifting present authorities raise a bounded `PlanError`; they
  are not downgraded to blockers.
- Genuinely absent future authorities produce the two ordered blockers.
- Partially present future authorities fail closed instead of being reported as
  merely absent.
- Planning has no rollback because it writes nothing.
- Candidate `h`, R3, quarantined R8 attempts, service state, and GPUs are never
  modified.

## Testing Strategy

- Build a compact fake `h`, R3, R8, and BuildPlugin authority graph under a
  temporary directory.
- Assert deterministic production-like blocked and all-authorities-ready plans.
- Parameterize parent document, tree, map, project, package content, package
  inventory, provider, legal-scope, and linkage drift.
- Reject omitted/extra/duplicate/case-fold/traversing package paths and parent
  namespace overlap.
- Reject wrong R8 classes, failed gates, positive prohibited claims, altered
  inherited R3 bytes, unmanifested plugin payload bytes, incomplete publisher
  policy, and non-root future authority descendants.
- Assert the CLI exposes only `--attempt-name`, performs zero writes, creates no
  bytecode in a clean subprocess checkout, and keeps all acceptance claims
  false.
- Run the focused test module, the existing animation executor/materializer
  regression set, Ruff, formatting, bytecode compilation, and `git diff --check`.

## Rollout and Observability

This slice lands as a source-only planner. Its production CLI should report two
blockers on the current machine. No service, port, GPU, database, Unreal, or
Blender process changes are permitted. Clearing blockers requires a separately
reviewed root publication procedure and a new materializer spec.

## Tradeoffs

- The planner does not rescan the full 9.15 GB h tree; it validates its sealed
  final projection plus current receipt/project/map bytes. This keeps planning
  cheap. The future materializer must perform the expensive full-tree seal.
- Whole-plugin replacement is larger than copying only two new source files, but
  it prevents ABI/BuildId mixing and is the only reviewable binary boundary.
- A blocked report is preferable to copying the already-working development E/F
  animation bytes because those attempts explicitly remain unaccepted.

## Traceability

- R1 -> exact parent pins and coherent receipt validation
- R2 -> exact R3 inventory and current package re-hash
- R3 -> optional sealed R8 authority and exact nine-package contract
- R4 -> optional root BuildPlugin manifest and whole-tree replacement
- R5 -> closed CLI, direct-child attempt, and zero-write behavior
- R6 -> canonical deterministic report and negative claims
- R7 -> safe path and namespace composition validation
- R8 -> documented future materializer/runtime/human gates

## Open Questions

- None for this CPU-only planning slice. Motion-quality criteria belong to the
  future runtime and human review spec.

## Approval

- Requested by: Ives / VISTA World owner
- Approved by: User approval to continue the accepted spec and CPU-safe work
- Date: 2026-08-30
