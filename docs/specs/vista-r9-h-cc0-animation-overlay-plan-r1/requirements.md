# Requirements: R9 h CC0 Animation Overlay Plan

Status: Approved for the CPU-only planning slice
Updated: 2026-08-30

## Problem

The sealed `hssd-r2-citysample-live-r5-20260830h` project is the best current
six-room visual baseline, but it contains neither the sealed MakeHuman CC0 R6
character packages nor the nine R8 animation runtime packages. The current R8
animation evidence is development-only and no reviewed BuildPlugin or final R8
publication authority exists. Mutating the sealed `h` project, silently using
development evidence, or claiming GTA-quality motion would destroy provenance.

## Goals

- Produce a deterministic, zero-write plan for one future append-only child of
  sealed candidate `h`.
- Bind the plan to the exact `h` receipts, map, project descriptor, and sealed
  static-tree projection already observed on 2026-08-30.
- Bind the character partition to the exact 23-package R3 MakeHuman CC0 import.
- Define the only permitted future animation and plugin partitions, while
  reporting missing root authorities as explicit blockers.
- Keep all runtime, visual, interaction, human-motion, and GTA acceptance claims
  false until separate Unreal and human review phases complete.

## Non-goals

- Copying, editing, importing, building, launching, rendering, or publishing an
  Unreal project.
- Starting or stopping Sunshine, Unreal, CAR, tmux, or any GPU service.
- Treating the quarantined R8 development attempts `e` or `f` as accepted input.
- Solving motion capture, IK, foot planting, facial animation, or GTA-level
  motion quality in this slice.
- Republishing City Sample, HSSD, MakeHuman, Unreal, Blender, or any binary asset
  through Git.

## Assumptions and Constraints

- Candidate `h` remains immutable and append-only evidence remains append-only.
- The future child remains a private, human-operated, noncommercial research
  demo because its parent contains Epic and HSSD content, even though the
  MakeHuman character and authored animation source are CC0-compatible.
- The planner may re-hash small pinned documents and package files, but it SHALL
  not rescan or copy the 9.15 GB parent tree. A future materializer must re-seal
  the full parent immediately before and after copy.
- Existing production constants intentionally leave the future R8 publication
  and BuildPlugin authority absent. Missing authority is a planned blocked
  state, not permission to fall back to development content.

## Requirements

### R1 — Exact sealed parent

WHEN the production plan is evaluated THEN the system SHALL verify the current
bytes of the fixed `h` complete, combined, and host receipts, the project
descriptor, and the final map against their exact SHA-256 and size pins.

Acceptance notes:

- The complete receipt SHALL bind the exact combined and host receipt paths,
  hashes, and sizes and SHALL state `failure_absent: true`.
- The combined and host receipts SHALL agree on the final project tree
  `74846d5a...`, map `1fda1534...`, project descriptor, legal scope, and
  `citysample_crowd_visual_demo_v1` provider.
- Parent runtime, interaction, photoreal-character, and GTA claims SHALL remain
  false.

### R2 — Exact R3 character partition

WHEN an R3 character source is evaluated THEN the system SHALL accept exactly
the 23 package records in the sealed R3 host receipt and SHALL re-hash every
corresponding current package byte.

Acceptance notes:

- Omitted, extra, duplicate, case-fold-colliding, traversing, non-regular,
  symlinked, wrong-size, or wrong-hash package entries SHALL fail closed.
- All packages SHALL remain below
  `Content/VISTA/MakeHumanCC0/R6/` and SHALL not already exist in candidate `h`.
- The R3 receipt SHALL retain `accepted: false`; only its verified import claims
  may be true.

### R3 — Exact future R8 animation partition

IF a root-published R8 animation authority is supplied THEN the system SHALL
accept exactly five AnimSequences, one BlendSpace, one AnimBlueprint, and two
AnimMontages under `Content/VISTA/MakeHumanCC0/R8/Animations/`.

Acceptance notes:

- The authority SHALL be a fresh sealed publication produced by the reviewed R8
  executor and SHALL bind its R3 source tree.
- The exact nine package paths SHALL match the checked-in executor contract.
- The runtime and host receipts SHALL retain the executor's complete closed key
  sets, bindings, class inventory, sequence inspection, terminal gates, terminal
  claims, and exact R3-to-R8 content delta; a partial receipt is not authority.
- The host receipt SHALL bind the same source-host receipt SHA recorded by the
  runtime receipt and the exact SHA of that runtime receipt file.
- The host project projection SHALL equal the sealed R3 file, directory, and
  byte counts plus exactly the nine validated R8 packages and their four new
  directories; an arbitrary positive projection is not authority.
- Every inherited R3 package in the R8 publication SHALL remain byte-identical.
- Until that authority exists, the plan SHALL report
  `fresh_root_published_r8_animation_authority` as a blocker and SHALL not use
  quarantined attempts `e` or `f`.

### R4 — Exact animation-enabled plugin replacement

IF a reviewed root BuildPlugin authority is supplied THEN the system SHALL plan
one whole-tree replacement at `Plugins/VistaPlayableHome` using the exact
published authority manifest.

Acceptance notes:

- The BuildPlugin manifest SHALL match projection
  `69153cd6...`, inventory `cad2d8f0...`, 241 files, 32 directories, and
  51,661,522 bytes.
- Partial overlays, arbitrary plugin roots, or caller-selected BuildIds SHALL be
  rejected.
- The actual payload namespace SHALL equal the manifest namespace exactly;
  unmanifested files, directories, symlinks, hard links, or special files SHALL
  fail closed.
- Every future authority directory and file SHALL be root-owned and immutable,
  and the publisher, interpreter, policy, critical-file, and negative-claim
  records SHALL match the reviewed root publisher contract.
- Until the authority exists, the plan SHALL report
  `reviewed_root_buildplugin_authority` as a blocker.

### R5 — Closed append-only output

WHEN a plan is requested THEN the system SHALL accept only one closed attempt
name beneath the fixed run parent and SHALL require that destination not exist.

Acceptance notes:

- Absolute aliases, nested attempts, symlinks, traversal, and caller overrides
  of the parent, map, provider, authority roots, or package paths SHALL be
  impossible through the CLI.
- Planning SHALL perform process-wide zero writes, including no checkout-local
  Python bytecode cache, and SHALL expose no apply or execute flag.

### R6 — Deterministic honest report

WHEN inputs are unchanged THEN repeated planning SHALL emit byte-identical
canonical JSON with either `ready_for_future_materializer` or
`blocked_pending_animation_overlay_authorities` status.

Acceptance notes:

- The report SHALL list exact base, character, animation, and plugin partitions.
- The report SHALL state `writes_performed: false` and all unobserved acceptance
  claims as false.
- Ready means only that a future materializer may be reviewed; it SHALL not mean
  Unreal runtime success or human-motion acceptance.

### R7 — Namespace and collision safety

WHEN target partitions are composed THEN the system SHALL prove that R6 and R8
package paths are pairwise distinct, case-fold distinct, traversal-free, and
absent from the sealed parent; only the explicitly declared plugin replacement
may overlap an existing parent namespace.

### R8 — Future execution gate

IF all planning blockers are cleared THEN any materialization SHALL still occur
in a new append-only child and SHALL require separate full-tree copy sealing,
NullRHI save/cold-reload evidence, runtime provider verification with
`makehuman_cc0_r8`, interaction review, and human-motion review.

## Edge Cases

- Receipt bytes match their file pin but their internal content digest is wrong.
- The complete receipt points at a different run with individually valid files.
- Combined and host receipts disagree only on map size, legal scope, or provider.
- A package differs only by filename case or Unicode/traversal spelling.
- The future R8 root exists but is a development directory, symlink, or has an
  unexpected package inventory.
- The plugin manifest is valid JSON but binds a different payload projection.
- The requested attempt appeared between two planning calls.

## Approval

- Requested by: Ives / VISTA World owner
- Approved by: User approval to continue the accepted spec and CPU-safe work
- Date: 2026-08-30
