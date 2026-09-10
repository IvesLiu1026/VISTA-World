# RTX5090 environment migration

Owner: this user-directed Codex task, solo.
Branch: `codex/vista-5090-migration-r1`, based on the accepted Home/Villa
integration branch after Moonlight recovery.

Owns: portable environment export/launch helpers under
`tools/runtime/vista_lab_migration`, their focused tests and runbook, plus a new
isolated migration release in the user's own space on the RTX5090 workstation.
The user explicitly requested moving and running the existing environments on
that workstation; scoped transfers, GPU checks and scene launches are covered.

Preserve: the source demo and all frozen assets, other users' GPU processes,
existing remote desktops, credentials/authentication, NAS mounts, production
ports, unrelated worktrees and main. New authentication/device-permission
requirements must be made concrete before any outstanding user action.

Use the nlplab-admin source-of-truth document to resolve the target at execution
time. Do not save target addresses, SSH ports, accounts, credentials or internal
mount details in source, receipts or this record. Evidence must be sanitized.

Scope inventory: VISTA World, Photoreal Kitchen, Photoreal Home, Home R5,
Villa R1, Villa R2 and Alpine Villa R3. Validate asset hashes, actual remote GPU
selection, native rendering and interaction separately from Moonlight pairing.
