# Tasks: VISTA HSSD R2 UE Composition R1

Status: In progress
Updated: 2026-08-30
Depends on: requirements.md, design.md

- [x] T1. Freeze and approve the exact R2 plan contract
  - Requirements: R1-R6
  - Validation: external plan SHA/bytes/content digest and blockers independently
    recomputed; no UE/GPU action

- [x] T2. Bind R2 plan into host and commandlet contracts
  - Files: Phase-2 runner and focused tests
  - Requirements: R1, R2, R4
  - Validation: exact keys/digests, original identity reconstruction, fixed
    transform projection, canonical semantic-ledger projection pins and drift
    rejection, including +123m target, forged contact gap/portal IDs/contact pair

- [x] T3. Preserve Phase-2 collision/proxy and receipt closure
  - Files: Phase-2 runner/commandlet tests
  - Requirements: R3-R6
  - Validation: 60 NoCollision actors, 19 query proxies, unresolved ledgers and
    all negative claims survive save/reload validation; actor receipts use exact
    keys, deterministic map paths and the exact StaticMeshActor class; all
    HSSD-related CPU tests pass; exact-plan exploits, extra negative actor claims
    and contradictory terminal claims fail

- [ ] T4. Execute one fresh diagnostic NullRHI candidate
  - Files: external append-only run only
  - Requirements: R5
  - Validation: UE return 0, closed scene/host receipts, exact R2 plan binding;
    accepted/full-fidelity/playable/GTA claims remain false

- [ ] T5. Integrate, push and hand off
  - Depends on: T2-T4
  - Validation: focused and related suites, Ruff, diff-check, reviewed commit and
    exact external evidence pointer

## Current evidence

- Real zero-write preflight succeeded against the original R5 Phase-1 project
  lineage and exact R2 plan. It emitted no attempt directory.
- The execution contract pins Bubblewrap `0.6.1` at `/usr/bin/bwrap`, SHA-256
  `d78807229d616606e339c5988392b9e0ab4a6a6998fa51e4590837f426a12fca`,
  and requires `--unshare-net` plus NullRHI.
