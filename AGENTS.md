# VISTA World Agent Guide

This is an active multi-agent research and engineering repository. Preserve accepted
contracts, provenance, and other agents' work before making changes.

## Required entry checks

- Run `git status --short --branch` before editing or staging.
- Treat unrelated dirty files as user or agent work; never reset or discard them.
- Use an isolated branch/worktree for every writing worker.
- Record owned and forbidden paths before parallel implementation.

## Development rules

- Use `uv` for Python. Do not invoke `pip` directly.
- Keep one logical change per commit and stage named files only.
- Work through pull requests after bootstrap; never force-push `main`.
- Never commit secrets, credentials, generated packages, Unreal/Blender binaries,
  runtime logs, canonical datasets, or external asset payloads.
- Large assets stay outside Git; commit only manifests, licenses, digests, and receipts.
- Runtime/GPU/streaming lifecycle and paid model or asset work require explicit approval.

## Required validation

For the current contract/compiler baseline:

```bash
uv sync --frozen
PYTHONPATH=tools uv run python -m unittest \
  tools.tests.test_vista_playable_home_contracts \
  tools.tests.test_vista_playable_home_compiler -v
git diff --check
```

Add focused regression tests for behavioral changes. Do not weaken assertions, add
skip/xfail, or relax closed schemas to make a patch pass.

## Daily Maintainer protected surfaces

The autonomous patcher must never edit:

- `.github/**`, `AGENTS.md`, `SECURITY.md`, `pyproject.toml`, or lockfiles;
- `automation/daily-maintainer/**`, its prompts, policy, guard, or verifier;
- `ops/systemd/**`;
- `docs/maintenance/backlog.*`, validation profiles, or policy;
- credentials/auth, deployment, networking, runtime lifecycle, accepted world receipts,
  datasets, evidence, binary assets, or dependency manifests.

Only a human-reviewed policy change may alter these boundaries. Tier 0 auto-merge is
allowed only after the approved canary and PR-only pilot described in the spec.
