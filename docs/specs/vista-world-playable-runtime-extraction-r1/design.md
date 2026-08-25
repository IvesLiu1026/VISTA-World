# Design: VISTA World Playable Runtime Extraction R1

Status: Draft
Updated: 2026-08-22
Depends on: requirements.md

## Summary

Extract the proven VISTA playable-home runtime spine from the pinned SimWorld
source tree into standalone VISTA-World without a branch-wide merge. Preserve the
historical path layout for the first parity milestone, rebuild against UE 5.7.3,
then add the missing event outcome evaluator and complete a three-room `mmg_044`
vertical slice. Visual assets, animation content, SimWorld integration and remote
input advance through independent later gates.

The accepted SimWorld packages and receipts are rollback and comparison evidence,
not binaries to copy into Git or automatic proof of the new standalone build.

## Evidence and Source Basis

| Role | Pin | Use |
| --- | --- | --- |
| VISTA-World base | `633244c8018771551e388f597c9d8e81bbc41a2b` | protected standalone contract/compiler baseline |
| Playable-home R1 rollback | `57fc8485097cd4514a9f223cfd8fffda3d8c3c87` | accepted game-only/package lineage reference |
| Realistic R2 source tree | `d80aa78f7681e378a051528ec55b7cfdbe39f64d` | primary selected-path extraction source |
| Current realism tip | `2571455fab4bf19bc622d656a1adf29313f3b16e` | discovery only; never bulk-merge |

Generated Blender, UE, package and runtime evidence remains at its append-only NAS
locations. The migration ledger records receipt identifiers and hashes but does not
copy payloads.

## Architecture and Flow

```text
VISTA projections / natural language
                 |
                 v
HouseSpec + EventSpec + ActionPlan
                 |
                 v
deterministic compiler -> Unreal BuildPlan
                 |
        +--------+---------+
        |                  |
        v                  v
Blender presentation   UE composition pipeline
        |                  |
        +--------+---------+
                 v
VistaPlayableHome UE 5.7.3 plugin
interaction + NPC + event conditions + typed transport
                 |
                 v
sealed Linux package -> local play -> Sunshine/Moonlight

Optional providers:
SimWorld asset retrieval -> AssetProvider adapter -> reviewed manifests
SimWorld Studio/NLP      -> VistaWorldTransport adapter -> typed commands
```

## Extraction Strategy

### Stage A: selected-path parity

The first extraction retains historical paths to minimize import and receipt drift:

| SimWorld source path | Initial VISTA-World path | Disposition |
| --- | --- | --- |
| `unreal_plugins/VistaPlayableHome/**` | same | extract runtime/editor plugin source |
| `tools/blender/vista_playable_home/**` | same | extract deterministic R1 forge |
| `tools/blender/vista_playable_home_realism/**` | same | extract R2 presentation source |
| `tools/ue/vista_playable_home/**` | same | extract import/composition/package materializer |
| `tools/runtime/vista_playable_home/**` | same | extract launch/acceptance/Sunshine tooling |
| `tools/tests/test_vista_playable_home_*` | same | select only tests required by retained modules |
| relevant schemas/profiles | existing or same relative path | reconcile against accepted standalone contracts |

Every selected file receives one ledger entry with source commit, destination,
license, dependency closure, expected digest or tree binding and validation owner.
Files unrelated to the selected path set remain excluded even when adjacent commits
modify them.

### Stage B: standalone dependency closure

Replace SimWorld-relative imports and package assumptions with VISTA-World-owned
entry points. This stage may add narrow compatibility shims but may not import the
Studio server/UI into core.

The existing v1 contracts remain authoritative. If a retained pipeline expects an
older fixture digest or generated evidence path, it must be updated through an
explicit adapter or rejected; accepted standalone fixtures are never rewritten to
match stale SimWorld output.

### Stage C: path normalization

After standalone package parity, move source in separate logical changes toward:

```text
plugins/unreal/VistaPlayableHome/
pipelines/blender/playable_home/
pipelines/unreal/playable_home/
runtime/playable_home/
adapters/simworld-studio/
```

Path normalization is not part of the first extraction PR because it multiplies the
number of changed imports and weakens comparison with retained receipts.

## Runtime Design

### Unreal plugin

`VistaPlayableHome` remains the native runtime owner for:

- third-person movement and collision-aware indoor camera;
- semantic actors and stable IDs;
- door, container, pickup/place and appliance affordances;
- bounded NPC action queues and navigation;
- event apply/reset/outcome state;
- typed loopback transport and renderer observations.

The plugin targets UE 5.7.3 and Linux x86_64 for R1 extraction. Engine or platform
changes require a new plugin/package receipt chain.

### Event outcome evaluator

The compiler already emits triggers, success conditions and failure conditions.
The UE runtime adds closed condition representations for:

- entity state comparison;
- entity room membership;
- player room membership;
- interaction occurrence;
- elapsed time.

On event start, all targets and operators are validated before mutation. During the
active event, interaction/state/room observations update one deterministic condition
state. Failure takes precedence when a single observation satisfies both a success
and failure boundary unless the EventSpec later defines another explicit policy.
Timeout is terminal failure. Reset restores the captured baseline and increments the
session generation only after successful completion.

### Typed transport

The initial protocol keeps one request per loopback connection and the existing
64 KiB request/response limits. Operations are:

```text
status | renderer_status | interaction | npc_queue | event
```

All commands bind `command_id`, `expected_revision` and `session_generation` where
applicable. Mutations are never transport-retried. Ambiguous timeout returns an
outcome-unknown code and requires status/reconciliation before another mutation.

### Host control plane

The standalone host layer compiles trusted fixtures and sends typed commands. A
future SimWorld adapter may reuse the existing REST/MCP user experience but must
depend on the standalone transport package, not the reverse.

## Asset and Visual Design

The repository stores only source manifests, license/entitlement records, hashes,
transformation recipes and receipts. Payloads remain in private external storage.

Provider policy:

| Provider | R1 private-demo policy |
| --- | --- |
| project-authored | preferred; exact source and build receipt required |
| Poly Haven CC0 | preferred external hero/material source |
| YCB CC BY 4.0 | accepted after attribution and target-engine inspection |
| HSSD CC BY-NC | private noncommercial research only; never public/commercial baseline |
| Fab/Marketplace | entitlement-gated; incorporated package use only; no raw redistribution |
| SimWorld static catalogs | discovery hint only until bound to exact Content and license receipts |

Visible R2 presentation meshes remain `NoCollision`; hidden semantic R1 actors own
collision, navigation, affordances and event state. A visual replacement cannot
change a semantic ID or gameplay digest.

## Animation Design

Animation work starts only after UE 5.7.3 standalone package parity. The historical
Quinn/Manny, LiftSet, pickup montage, IK/Control Rig and fall-loop assets are source
candidates. They are migrated into a disposable UE 5.7.3 copy, retargeted to a
project-owned skeleton and saved beneath `/Game/VISTA/Characters/PlayableHomeR1/`.

Animation V1 includes locomotion, idle, turn-in-place, pickup/drop, door interaction,
hand contact IK and foot IK. Exact montage notifies, root-motion policy, skeleton
binding, target anchors and completion evidence are pinned.

The historical `VistaAnimationContentApi` 1.1.0 source is not extracted unchanged
because its static compatibility contract targets UE 5.3.2. Its closed typed-action,
no-retry and evidence principles may inform a new UE 5.7.3 contract revision.

## First Vertical Slice

The first user-facing standalone slice contains:

- rooms: entry hall, living room, kitchen/dining;
- character: third-person Manny-compatible project pawn;
- interactables: keys, one dynamic door and the stove;
- event: `mmg_044`;
- renderer: accepted R2 profile request, re-observed in the standalone package;
- session: unconstrained play duration, with event-specific timeout only;
- control: local keyboard/mouse first; Moonlight input is a later gate.

Acceptance requires continuous traversal, camera recovery, keys pickup/carry/place,
door open/close, stove toggle, `mmg_044` success/failure/reset, exact generation
accounting, nonblank captures and no SimWorld process dependency.

## Interfaces and Contracts

- Existing inputs:
  `simworld.vista.playable-house/v1`,
  `simworld.vista.playable-event/v1`,
  `simworld.vista.playable-home-build-plan/v1`.
- Runtime command family: `vista_world_action` with the closed operation allowlist.
- New runtime source type: closed condition structures mirroring the five EventSpec
  condition variants; no generic expression evaluator.
- Asset input: provider-neutral manifest plus exact license, source and transformed
  content digests.
- Runtime evidence: package identity, typed readiness, command/event transition,
  renderer observation and visual/performance receipts.

Any new schema is closed by default and versioned. No caller JSON may include host
paths, Unreal object paths, functions, scripts or credentials.

## Data Model and Migration

No accepted R1 schema or fixture is rewritten during initial extraction. New internal
runtime condition types are compiled from the existing EventSpec and are bound to the
same event digest.

The migration ledger is the source of truth for selected paths. It records:

```text
source_repository
source_commit
source_path
destination_path
source_blob_or_tree_digest
license_class
dependency_disposition
validation_profile
rollback_reference
```

Generated receipt paths in historical docs remain references; new receipts use fresh
VISTA-World attempt roots and never overwrite old evidence.

## File Plan

Specification and migration:

- `docs/specs/vista-world-playable-runtime-extraction-r1/**`
- `docs/migration/playable-runtime-extraction-r1.md`

Initial selected paths:

- `unreal_plugins/VistaPlayableHome/**`
- `tools/blender/vista_playable_home/**`
- `tools/blender/vista_playable_home_realism/**`
- `tools/ue/vista_playable_home/**`
- `tools/runtime/vista_playable_home/**`
- selected `tools/tests/test_vista_playable_home_*`

Later paths:

- animation source/contracts under the runtime plugin or a versioned companion plugin;
- `adapters/simworld-studio/**`;
- asset manifests and receipts, without payloads.

## Ownership Streams

| Stream | Owns | Must not touch |
| --- | --- | --- |
| integrator/migration | spec, ledger, selected-history import | runtime implementation while another owner is active |
| Unreal runtime | `unreal_plugins/VistaPlayableHome/**` | pipelines, assets, adapters |
| Blender/UE pipeline | `tools/blender/**`, `tools/ue/**` selected paths | plugin runtime, SimWorld server |
| package/runtime | `tools/runtime/vista_playable_home/**` | service lifecycle without authorization |
| event bridge | condition compiler/runtime and focused tests | animation and asset payloads |
| animation | project-owned animation contracts/content recipes | generic MCP/Studio core |
| SimWorld adapter | `adapters/simworld-studio/**` | VISTA runtime contracts |

Each writing stream uses a separate worktree. One file has one owner.

## Failure Handling and Rollback

- Missing selected source, digest mismatch or unclassified dependency blocks import.
- Engine/tool/content mismatch blocks BuildPlugin or package acceptance.
- A failed UE/Blender attempt is retained as quarantined append-only evidence.
- Missing hero assets cannot be replaced by Cube/default material in a claimed visual
  acceptance run.
- Event target or condition mismatch prevents event start before any operation applies.
- Ambiguous runtime mutation blocks further mutation until reconciliation or restart.
- Remote video with blocked input reports view-only.
- The accepted SimWorld R1/R2 packages remain rollback references until standalone
  acceptance closes equivalent gates.

## Testing Strategy

### Offline extraction gate

- migration-ledger schema/content checks;
- no SimWorld import/dependency audit;
- existing contract/compiler tests;
- selected plugin/pipeline/runtime source tests;
- secret, binary, large-file and license-manifest scans;
- deterministic fixture and path-containment tests.

### UE build gate, explicit authorization

- UE 5.7.3 BuildPlugin for Editor, Development and Shipping targets;
- disposable project install and map compose/save/reload;
- exact plugin/content/tool receipt binding.

### Packaged runtime gate, explicit authorization

- Linux Development Build/Cook/Stage/Package/Archive;
- NullRHI typed readiness and listener ownership;
- local rendered traversal, interaction and event outcomes;
- renderer observation against the exact package;
- fixed performance traversal.

### Remote gate, explicit authorization/admin action

- Sunshine application/profile binding;
- decoded advancing frames;
- real Moonlight keyboard/mouse/gamepad input;
- device permission and reboot-persistence evidence.

## Rollout and Observability

1. Approve this SDD.
2. Land selected-path ledger only.
3. Extract source by ownership stream through small PRs.
4. Pass offline standalone parity.
5. Obtain explicit UE/toolchain authorization and rebuild plugin.
6. Package and close three-room event slice.
7. Promote visual and animation slices independently.
8. Add optional SimWorld adapter.
9. Close remote input, performance and six-room scale-out.

Every phase publishes source SHA, test/build summary, artifact digests, license
limits, known blockers and rollback pin. A later phase cannot relabel an earlier
partial receipt.

## Traceability

- R1-R2 -> selected-path migration and ownership model
- R3 -> exact UE/toolchain/package binding
- R4-R5 -> standalone core and immutable v1 contracts
- R6 -> runtime plugin and first gameplay slice
- R7 -> condition evaluator and event receipts
- R8 -> typed transport
- R9 -> provider-neutral external asset manifests
- R10 -> UE 5.7.3 project-owned animation flow
- R11 -> deterministic pipelines, quarantine and package receipts
- R12 -> Sunshine/Moonlight truthfulness
- R13 -> three-room `mmg_044` acceptance
- R14 -> World Agent and SimWorld adapters
- R15 -> ownership and execution gates

## Open Questions

- No question blocks the ledger and source-extraction phase.
- UE/GPU/runtime execution awaits a later explicit authorization after the offline
  source diff and exact commands are ready.
- Public/commercial asset promotion requires a future policy revision.

## Approval

- Requested by: Codex primary integrator
- Approved by:
- Date:
