# Clean research workspace on the dual RTX 5090 workstation

Owner: this user-directed Codex task, solo; 2026-09-12.
Branch: `codex/vista-clean-workspace-r1`, integration baseline `125edc98`.
Owns: `tools/workspace/`, `tools/tests/test_research_workspace.py`,
`docs/workspace/`, this handoff; a new `workspace` directory under the existing
user-owned migration root on the target workstation.

Preserve: existing frozen releases, active display/game/input/streaming services,
other users' jobs, source dirty checkouts, current character/action workers,
credentials, authentication, NAS mounts, production, and main.
No runtime lifecycle ownership or changes are needed for workspace organization.
Validation: required contract/compiler tests, targeted workspace regressions,
remote clean checkout and content-hash verification, disk accounting, unchanged
service process identities. No model inference or dataset generation.

Source repositories and papers are transferred as pinned, clean snapshots.
Record upstream provenance and exclusions. Keep host paths and private endpoints
out of Git. Shared scene content must be versioned and verified; do not alter old
payloads to reclaim space. New host and scene configuration must not require
editing historical launch scripts.
