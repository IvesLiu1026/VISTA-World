# Tasks: VISTA HSSD R2 UE Composition R1

Status: Complete — diagnostic composition evidence only
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
    and contradictory terminal claims fail; v4 additionally binds
    `-notraceserver`, a Bubblewrap PID namespace and post-exit log closure

- [x] T4. Execute one fresh diagnostic NullRHI candidate
  - Files: external append-only run only
  - Requirements: R5
  - Validation: UE return 0, closed scene/host receipts, exact R2 plan binding;
    accepted/full-fidelity/playable/GTA claims remain false

- [x] T5. Integrate, push and hand off
  - Depends on: T2-T4
  - Validation: focused and related suites, Ruff, diff-check, reviewed commit and
    exact external evidence pointer

## Current evidence

- Real zero-write preflight succeeded against the original R5 Phase-1 project
  lineage and exact R2 plan. It emitted no attempt directory.
- The execution contract pins Bubblewrap `0.6.1` at `/usr/bin/bwrap`, SHA-256
  `d78807229d616606e339c5988392b9e0ab4a6a6998fa51e4590837f426a12fca`,
  and requires `--unshare-net`, `--unshare-pid`, NullRHI and `-notraceserver`.
- The first real R2 attempt at
  `hssd-ue-phase2-r2-diagnostic-20260829T201223Z` is retained as failed evidence:
  direct UE returned successfully, but a forked UnrealTraceServer appended after
  return. Its host receipt pins stdout SHA-256
  `69e1d216865638356d885486dc1ed751615011168ac648fa326354ad4c8555d7`,
  while current bytes hash to
  `7bcc89c4a94f0f3cc9fc09c09988b9790c80992d215d0bdcc97ee7390514f89d`.
  The v4 standalone revalidator rejects it explicitly; it is not T4 success.
- The fresh v4 attempt at
  `/data/sysx/vista-world/runs/vista-action-world-r1/hssd-ue-phase2-r2-diagnostic-20260829T203309Z`
  completed successfully as diagnostic-only evidence. Its host receipt content
  digest is
  `83d2686ced55389625049462b1f46eadef4d0d34302dc7e7c22d345929196a09`;
  the 437,720-byte map SHA-256 is
  `60c4f7195d3715e6f6d6691594ca17c481fdad21e838121fcae9ed3ffca4f4d1`;
  the scene receipt SHA-256 is
  `f7d225fb07a51f6eeb76e565df589a317f57c7618b489393c44b79b23a5f4a4d`.
  It contains 60 visual placements and preserves 19 hidden QueryOnly semantic
  proxies. The final stdout and engine-log SHA-256 values are respectively
  `d4ff25ae00575ddc3654226985f336a94136ecbd79ec52709b0c3da97d6e916c`
  and `30f38912ae210b82835b3e3bb73d40758b7653f0fe6d8a9f4f65b41d19bb3070`;
  a delayed independent current-byte validation passed with no residual
  commandlet process.
- This success does not satisfy visual review, playable collision, UE runtime,
  interaction, character or GTA-quality acceptance. All such claims remain
  false in the host receipt; 20 secondary collision candidates, 18 wall
  fixtures and the bathroom faucet support remain review/runtime work.
- CPU closure validation: 60 focused tests and 238 full HSSD-related tests pass;
  stdout, engine log, execution manifest, scene receipt and map drift all fail.
