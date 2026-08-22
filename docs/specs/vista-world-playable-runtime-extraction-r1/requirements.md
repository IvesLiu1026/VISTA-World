# Requirements: VISTA World Playable Runtime Extraction R1

Status: Draft
Updated: 2026-08-22
Depends on: `../vista-world-repository-extraction/{requirements,design,tasks}.md`

## Problem

Standalone `VISTA-World` currently contains the accepted playable-home contracts,
R1 world pack, VISTA-derived public event projections and deterministic compiler,
but not the Unreal gameplay plugin, Blender/Unreal build pipelines, packaged runtime
or Sunshine integration that were previously developed and evidenced in the
SimWorld Studio realism lineage.

The retained SimWorld lineage contains an accepted UE 5.7.3 Linux package, typed
door/pickup/NPC/event behavior, a realistic-interior renderer profile and a
Sunshine video path. It also contains unrelated Studio, Daily Maintainer and
experimental history. Bulk-merging that branch would blur product ownership,
reintroduce coupling and make provenance and licensing difficult to audit.

The product needs a selected-path, evidence-preserving extraction that makes the
runtime reproducible from VISTA-World without claiming that external assets,
animations, remote input or visual-quality gates are complete before they are
revalidated.

## Goals

- Make VISTA-World the canonical source for the playable-home Unreal runtime,
  deterministic Blender/UE pipelines and packaged game launcher.
- Reproduce the accepted gameplay and renderer baseline on UE 5.7.3 without a
  SimWorld server, Studio UI, Postgres, Qdrant or generic MCP mutation lane.
- Preserve selected-path authorship, source pins, receipts, licenses and rollback
  references while excluding unrelated branch history.
- Deliver one GTA-like private-research vertical slice with three rooms, a
  third-person character, three interactable object types and one fully evaluated
  VISTA-derived event.
- Treat SimWorld characters, animations and asset catalogs as reviewed providers
  or authoring sources rather than VISTA-World runtime dependencies.
- Keep external asset payloads and generated Unreal/Blender artifacts outside Git.

## Success Signals

- A clean VISTA-World checkout can validate, build and package the selected runtime
  using only pinned external tool/content inputs.
- The packaged game reaches typed `READY`, traverses the selected rooms and closes
  interaction and event outcome receipts without a running SimWorld service.
- Every visible external asset has a source, license, digest, transformation and
  usage-policy receipt.
- Runtime and documentation report missing animation, input, performance or visual
  evidence as blocked instead of silently falling back or promoting a partial demo.

## Non-goals

- Building a GTA-scale open world, vehicle system, combat system or production MMO.
- Importing the complete SimWorld Studio UI/backend or its approximately 16k-asset
  retrieval stack into the runtime core.
- Bulk-merging the 298-commit realism worktree branch or copying its generated
  binaries and NAS evidence into Git.
- Redistributing Marketplace/Fab source payloads, HSSD data, VISTA media, Unreal
  Engine binaries or canonical datasets.
- Enabling public deployment, paid APIs, GPU jobs, external downloads, Sunshine
  service changes or administrator device permissions without a separate gate.
- Treating the historical UE 5.3.2 animation contract as current UE 5.7.3 live
  evidence.

## Assumptions and Decisions

- Product policy for this milestone is a private, noncommercial research demo.
- UE `5.7.3` on Linux x86_64 is the runtime baseline because the accepted R2 package
  and renderer observation were produced on that engine.
- The selected source tree is pinned at SimWorld commit
  `d80aa78f7681e378a051528ec55b7cfdbe39f64d`; the accepted R1 rollback source is
  `57fc8485097cd4514a9f223cfd8fffda3d8c3c87`.
- The first extraction preserves historical source paths where renaming would
  invalidate imports or receipts. Path normalization is a later logical change.
- `mmg_044` is the first event outcome slice because it exercises room traversal,
  pickup/carry and an exit-door failure boundary.
- HSSD may be used only in a clearly labelled private noncommercial research demo
  with exact CC BY-NC attribution. CC0 and CC BY sources remain preferred.

## Requirements

### R1. Canonical standalone ownership

WHEN playable runtime source is extracted THEN VISTA-World SHALL become its
canonical product source, while SimWorld Studio remains an upstream history and
optional compatibility provider.

Acceptance notes:
- Core runtime code must not import or require Studio web/server modules.
- Generated packages and external content remain outside Git.

### R2. Selected-path provenance

WHEN source is imported from the SimWorld lineage THEN the extraction SHALL bind
each retained path to an exact source commit, preserve authorship where practical
and exclude unrelated history by default.

Acceptance notes:
- The primary source tree is `d80aa78f7681e378a051528ec55b7cfdbe39f64d`.
- A migration ledger records old path, new path, source commit, license, dependency
  disposition and validation status.
- No branch-wide merge is permitted.

### R3. Exact engine baseline

WHEN Unreal source, content or a package is accepted THEN the receipt SHALL bind
UE 5.7.3, target platform, toolchain digests and the exact project/content revision.

Acceptance notes:
- A UE 5.3 artifact is an authoring input only until migrated and revalidated.
- A source-only test or older BuildPlugin receipt is not runtime evidence.

### R4. Standalone runtime core

WHEN the packaged game starts THEN it SHALL reach typed readiness and support its
gameplay loop without SimWorld Studio, Postgres, Qdrant, a browser, Python scripting
or a generic MCP bridge.

Acceptance notes:
- Optional adapters may be absent.
- Missing optional services must not block local packaged gameplay.

### R5. Contract compatibility

WHEN the extracted runtime consumes the R1 house or event pack THEN it SHALL retain
the accepted `simworld.vista.*` v1 schema IDs, semantic IDs, content digests and
centimeter-resolved build-plan semantics.

Acceptance notes:
- Namespace modernization requires a separately versioned compatibility design.
- Existing closed schemas may not be relaxed to accommodate extraction defects.

### R6. Third-person gameplay parity

WHEN the player enters the first vertical slice THEN the system SHALL provide
collision-aware third-person movement, indoor camera handling, interaction focus,
door open/close, pickup/carry/drop/place and appliance toggle behavior.

Acceptance notes:
- The first slice uses entry hall, living room and kitchen/dining.
- Initial interactable types are keys, a door and the stove.
- Controls remain move, look, jump, sprint, crouch, interact and drop.

### R7. Complete event outcomes

WHEN a compiled EventSpec is started THEN the UE runtime SHALL evaluate its declared
triggers, success conditions, failure conditions, timeout and restore-baseline reset
against the exact active world revision.

Acceptance notes:
- `start/reset` and initial overlay application alone are insufficient.
- Interaction, entity state, entity room, player room and elapsed conditions require
  deterministic evaluators.
- Every terminal transition produces generation-bound status and evidence.

### R8. Closed typed transport

WHEN a host or adapter controls the runtime THEN it SHALL use a loopback-only,
bounded, versioned typed protocol with exact operations and no caller-selected path,
class, function, script, console command or retryable mutation.

Acceptance notes:
- Mutations use `maxAttempts=1` and report outcome-unknown after ambiguous timeout.
- Requests bind command ID, world revision and session generation.
- Existing `status`, `renderer_status`, `interaction`, `npc_queue` and `event`
  operations remain the initial allowlist.

### R9. Private-research asset policy

WHEN an external asset is selected THEN the build SHALL require a source/license/
digest/entitlement receipt and SHALL keep its payload outside Git.

Acceptance notes:
- CC0 is preferred; CC BY requires attribution; HSSD CC BY-NC is research-demo only.
- Fab/Marketplace assets require verified entitlement and may be distributed only as
  permitted inside the packaged project, never as standalone source payloads.
- `allow AI` metadata is not redistribution evidence.
- Unknown, `NoAI` or incompatible assets fail closed.

### R10. Project-owned animation content

WHEN a SimWorld or Unreal sample animation is used THEN it SHALL be treated as an
authoring source and retargeted or migrated into a versioned `/Game/VISTA/...`
namespace with target-engine receipts.

Acceptance notes:
- First animation scope is locomotion, idle, turn, pickup/drop, door interaction,
  hand IK and foot IK.
- `mmg_040` look/brace/drag/lift-foot/pause/fall/recover is a later content slice.
- Loadability, shared skeleton or filename similarity does not prove live behavior.

### R11. Deterministic build and package

WHEN Blender or Unreal materializes a world THEN every input, transform, output,
tool version and receipt SHALL be pinned, and partial attempts SHALL remain
quarantined without replacing an accepted pointer.

Acceptance notes:
- Presentation meshes and semantic collision/gameplay authority remain separate.
- A package must be re-hashed before spawn and after typed readiness.

### R12. Truthful remote surface

WHEN Sunshine or Moonlight is offered THEN the system SHALL distinguish video-ready,
input-ready and unavailable states and SHALL not claim remote control while
`/dev/uinput` or `/dev/uhid` permissions remain blocked.

Acceptance notes:
- Runtime/service changes require explicit owner authorization.
- Local input evidence cannot substitute for Moonlight input evidence.

### R13. First vertical-slice acceptance

WHEN R1 extraction parity is complete THEN the first user-facing acceptance SHALL
run a packaged three-room demo with one third-person character, keys, a door, the
stove and `mmg_044` through success, failure and reset paths.

Acceptance notes:
- The playable session is not limited to the 12-second source-media duration.
- SimWorld Studio is stopped or absent during standalone acceptance.
- The run retains continuous traversal, state, event and visual evidence.

### R14. Optional World Agent and SimWorld adapters

WHEN natural language or Studio controls VISTA World THEN the control plane SHALL
compile requests into closed World/Scene/Event/Action plans and pass only validated
typed commands to runtime.

Acceptance notes:
- SimWorld asset retrieval may implement a versioned provider interface.
- The NLP/browser caller cannot directly select Unreal paths or executable actions.

### R15. Isolation and authorization

WHEN work touches UE, GPU, external assets, streaming, services or administrator
device policy THEN execution SHALL occur in an explicitly owned attempt after the
corresponding user authorization and preflight.

Acceptance notes:
- GPU 1, production port 8000, datasets, accepted evidence and Daily Maintainer
  protected surfaces remain out of scope.
- Every writing worker has a separate branch/worktree and non-overlapping paths.

## Edge Cases

- A retained source path depends on an excluded Studio module.
- A UE 5.3 asset loads in 5.7.3 but its dependency, skeleton, notify or material
  behavior changes after save.
- A package reaches process liveness but not typed readiness.
- Event initial operations apply while one condition target is absent or stale.
- A mutation times out after UE may have accepted it.
- An asset is available on disk but lacks entitlement or redistribution evidence.
- A private HSSD asset is accidentally selected for a public/commercial package.
- A renderer profile is requested at build time but differs from live observations.
- Sunshine captures video while input devices remain inaccessible.
- The current SimWorld branch contains unrelated maintenance commits after the
  accepted source pin.

## Open Questions

- No blocking product question remains for specification and extraction-ledger work.
- UE BuildPlugin, package, GPU validation, external download and administrator input
  permissions remain explicit later execution gates.
- Final public/commercial asset policy is intentionally deferred beyond this private
  research-demo milestone.

## Approval

- Requested by: Codex primary integrator
- Approved by:
- Date:
