# Tasks: VISTA HSSD R2 + City Sample Live R1

Status: Specification ready; implementation not started
Updated: 2026-08-30
Depends on: requirements.md, design.md

## Rules

- Work only in `codex/vista-r9-six-room-finish-r1`.
- R6/HSSD run directories are read-only or append-only inputs.
- Keep R6/Sunshine/Xvfb/input unchanged through T8.
- External asset payloads stay outside Git; no AI/VLM pixel review.
- One runtime owner performs T9; earlier tasks are CPU/NullRHI only.

## Task list

- [x] T1. Freeze requirements, design and source lineage
  - Requirements: R1-R9
  - Validation: exact pins, 42→57+3 model, legal boundary, rollback and human
    acceptance ownership recorded

- [ ] T2. Add the closed finish profile and deterministic fixture forge
  - Requirements: R2, R4, R5, R9
  - Validation: six rooms/materials/trims/wet zone, three headless Blender
    fixture GLBs plus CPU previews/inspection, 60 slots and collision ledgers;
    no caller overrides and no Git-tracked binary payloads

- [ ] T3. Implement exact R6/HSSD preflight and zero-write planning
  - Requirements: R1-R3, R6, R9
  - Depends on: T2
  - Validation: exact R6 receipt/tree/map/legal scope, HSSD v4/namespace,
    separate HSSD-source and R6-runtime semantic authorities, scripts and
    deterministic no-write plan

- [ ] T4. Implement the UE composition commandlet
  - Requirements: R2-R5
  - Depends on: T2, T3
  - Validation: exact 41 shell reuse/reposition, one legacy phone-shell delete,
    16 shell spawns, three presentations, 108 preserved actors, six-room finish,
    19/20/21 collision, exact static 5+11 runtime projection and cold-reload
    receipt; exact package/world/WorldSettings/game-mode/lighting authority

- [ ] T5. Close containment, map-plus-fixture publication and current-byte receipts
  - Requirements: R1, R6
  - Depends on: T4
  - Validation: bwrap/NullRHI/no TraceServer/GPU, process/log closure, exact
    one-result/one-scene marker cardinality, map-plus-fixture-package delta,
    scene/host/combined receipts and negative claims

- [ ] T6. Add dedicated human-only live launcher
  - Requirements: R7-R9
  - Depends on: T5
  - Validation: receipt-bound City Sample command, agent/VLM rejection, startup
    grace, exact transient-unit reconstruction command and executable R6
    rollback preflight

- [ ] T7. Run focused and related CPU review gates
  - Requirements: R1-R9
  - Depends on: T2-T6
  - Validation: focused plus R4/R6/HSSD/launcher regressions, bidirectional
    coherent collision drift rejection, coherent world-authority drift
    rejection, Ruff, format, diff-check and independent review with no P0/P1

- [ ] T8. Execute one fresh append-only NullRHI candidate
  - Requirements: R1-R6, R9
  - Depends on: T7
  - Validation: UE zero, cold reload, 60 slots, 108 preserved, 6/6 finish,
    19/20/21 collision, exact map-plus-fixture package delta, delayed
    current-byte validation and all human/GTA acceptance false

- [ ] T9. Perform controlled live switch and human review
  - Requirements: R7-R9
  - Depends on: T8 and runtime-owner checkpoint
  - Validation: R6 checkpoint, R9 on `:118`/GPU0, Sunshine controls/pickups/
    portals/performance and rollback; human acceptance pending yhliu signature

- [ ] T10. Integrate, push and hand off
  - Validation: named-file commits, integration into
    `codex/vista-action-world-r1`, GitHub push, evidence/service pointers and
    remaining blockers documented

## Initial blockers

- HSSD R2 proves 60/19/17 but not this R9 merge.
- Twenty secondary proxies need live tuning; 18 wall fixtures, faucet support,
  ladder and five contacts remain review items.
- Human review owns City Sample appearance, player-eye quality, pickups,
  portal walkability and performance acceptance.
