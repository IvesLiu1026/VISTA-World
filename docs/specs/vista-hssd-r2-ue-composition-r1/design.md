# Design: VISTA HSSD R2 UE Composition R1

Status: Approved for implementation
Updated: 2026-08-30
Depends on: requirements.md

## Summary

Version the existing HSSD Phase-2 runner contract and add the sealed R2 Blender
plan as a fourth placement contract beside the original profile, house and
scene plan. The host derives world-space UE operations from the R2 transforms;
the copied Phase-2 runner independently repeats the same derivation inside UE.
The existing composition commandlet, semantic-proxy repair and terminal
validator remain the execution mechanism.

## Fixed Inputs

- Existing Phase-1 diagnostic project and receipts remain byte-pinned.
- The reusable Phase-1 project is explicitly bound to its original R5 HSSD
  source lineage; current importer-module R7 defaults cannot silently replace
  that historical source authority.
- Existing R1 profile, house and source scene plan remain identity authority.
- R2 build plan:
  - path: fixed external append-only R5 attempt;
  - SHA-256: `4b2ded463a0be4caf26cd326a06944ab171d93c917d5de530fd36ca9b3ae9de2`;
  - bytes: `206549`;
  - content digest:
    `97bb05ad7df63a24c284eb840dc306950286c526257f673056b0eb6a50bb2de4`.

## Flow

1. Revalidate Phase-1 project/evidence and all four placement contracts.
2. Require the R2 plan to reconstruct the exact original 60 placement rows,
   bind canonical SHA-256 projections for the complete 17 overrides, their 17
   target transforms, and the support/proxy/portal/contact review ledgers.
3. Derive 60 UE world transforms from room transforms plus R2 room-local
   transforms.
4. Include the R2 plan record and remediation summary in host plan/execution.
5. Copy the exact R2 plan into the fresh attempt and rederive inside UE.
6. Launch the commandlet through pinned Bubblewrap with `--unshare-net` and
   NullRHI, with same-FD JSON parsing plus immediate pre-launch input checks.
7. Spawn/reload the same 60 NoCollision shells under deterministic
   persistent-level object names, close every actor receipt to the exact field
   schema and class path, repair/hide the same 19 semantic proxies and bind the
   R2 plan into scene and host receipts.
8. Revalidate the execution manifest, scripts, evidence, contracts and project
   descriptor before terminal publication.

## Failure Handling

- Any R2 file, schema, digest, canonical projection, placement, ledger or
  transform drift fails before attempt creation in dry/apply preflight.
- Any actor receipt with a forged map path, suffix-only class match or extra
  claim field fails terminal validation.
- UE failure retains only the fresh quarantined attempt and failure receipt.
- Existing material-conflict, visual, runtime and GTA claims remain false.

## File Plan

- Update `run_hssd_private_research_composition.py` to the R2-bound v3 contract.
- Update the Phase-1 terminal validator with explicit historical-lineage
  parameters, plus the focused Phase-2 runner/commandlet tests.
- Update the parent T10 task evidence only after a real append-only run succeeds.

## Rollout

1. Land source and focused tests in an isolated branch.
2. Run zero-write preflight against the actual R2 plan.
3. Create one fresh NullRHI append-only Phase-2 attempt.
4. Revalidate receipts, then merge/push source. Visual/runtime promotion remains
   a separate GPU and human-review step.
