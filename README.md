# VISTA World

VISTA World is an agent-driven, interactive 3D simulation environment built around
versioned world contracts, verified VISTA events, reproducible scene compilation, and
replaceable runtime/control-plane adapters.

This repository is standalone: the contract/compiler core does not require SimWorld
Studio, Unreal Engine, Blender, Postgres, Qdrant, or a running GPU service. SimWorld
Studio remains an optional compatibility adapter while the native VISTA World runtime
is extracted incrementally.

## Current public baseline

The first extraction contains:

- a six-room indoor home contract;
- 34 semantic entities with interaction affordances;
- seven verified VISTA event overlays;
- closed JSON schemas and deterministic content digests;
- a pure-Python compiler that emits an Unreal-oriented build plan;
- offline contract/compiler regression tests;
- approved repository-extraction and Daily Maintainer specifications.

Unreal gameplay, realistic assets, Blender pipelines, streaming, and the native control
center are intentionally not claimed as standalone in this first baseline. They will be
imported only with reproducible tests, provenance, and rollback evidence.

## Quick start

Requirements: Python 3.10–3.12 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync --frozen

PYTHONPATH=tools uv run python -m unittest \
  tools.tests.test_vista_playable_home_contracts \
  tools.tests.test_vista_playable_home_compiler -v

PYTHONPATH=tools uv run python tools/worlds/playable_home.py validate \
  --house world_packs/vista_playable_home_r1/house.json \
  --events-dir world_packs/vista_playable_home_r1/events
```

Compile a deterministic build plan:

```bash
PYTHONPATH=tools uv run python tools/worlds/playable_home.py compile \
  --house world_packs/vista_playable_home_r1/house.json \
  --events-dir world_packs/vista_playable_home_r1/events \
  --output /tmp/vista-playable-home-plan.json
```

## Repository direction

The long-term package boundaries are:

```text
contracts / world packs -> Blender and Unreal pipelines -> packaged game/runtime
            |                                      |
            +------ versioned transport adapters --+
```

See [`docs/specs/vista-world-repository-extraction`](docs/specs/vista-world-repository-extraction)
and [`docs/specs/vista-world-daily-maintainer`](docs/specs/vista-world-daily-maintainer).

## License and provenance

The repository is licensed under Apache License 2.0. Selected history and authorship
from the SimWorld Studio lineage are preserved. See [`NOTICE`](NOTICE) and the migration
ledger under [`docs/migration`](docs/migration).
