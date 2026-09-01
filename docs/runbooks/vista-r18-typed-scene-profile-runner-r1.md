# VISTA R18 Typed Scene Profile Runner R1

## Purpose

This runner binding lets the existing VISTA Playable Home UE build opt into the
closed R18 typed-scene composition overlay without changing the legacy R1, R2,
or R4 build path. The overlay upgrades the exact HouseSpec seats and adds the
typed liquid source/receiver actors compiled by `planning.build_composition_spec`.

This is build authority only. It is not UE runtime proof, human motion-quality
acceptance, external-asset acceptance, or GTA-quality acceptance.

## Inputs

Add both arguments to the existing `build_home.py` dry-run or apply command:

```text
--typed-scene-profile <absolute-profile-path>
--typed-scene-profile-sha256 <lowercase-sha256-of-exact-file-bytes>
```

The approved checked-in profile is:

```text
world_packs/vista_playable_home_r1/composition_profiles/vista_home_typed_scene_r18.json
```

Compute its exact source-file pin locally:

```bash
sha256sum \
  world_packs/vista_playable_home_r1/composition_profiles/vista_home_typed_scene_r18.json
```

Keep all other required build arguments unchanged. Omit both R18 arguments to
retain the legacy execution shape and behavior.

## Dry-run contract

The default zero-write dry run validates all of the following before an attempt
directory exists:

- the input path is absolute, normalized, regular, canonical, and contains no
  symlink component;
- the exact input bytes match the caller-supplied SHA-256;
- the JSON is strict UTF-8, finite, duplicate-key-free, and object-rooted;
- the schema is
  `simworld.vista.playable-home-typed-scene-composition/v1`;
- the profile ID is exactly `vista_home_typed_scene_r18`;
- the content digest seals the canonical profile body;
- the house ID, revision, and content digest match the pinned build plan;
- every typed seat, interaction/exit anchor, liquid source, and liquid receiver
  passes the closed R18 planner contract.

When selected, the dry-run report records the source path, attempt-staged path,
source SHA-256, schema, profile ID, and content digest. The execution manifest
contains an additive `typed_scene_profile` descriptor and the compiled
composition contains the same profile ID and content digest.

## Apply materialization

Apply writes the already validated source bytes, unchanged, to:

```text
<attempt>/contracts/typed-scene-profile.json
```

The file is created exclusively with mode `0600`. Before `execution.json` is
written, `contract.build_execution_manifest` rechecks the staged SHA-256,
strict JSON identity, house-bound planner output, schema, profile ID, and content
digest. The newly generated execution bytes must exactly equal the dry-run
execution bytes or the attempt fails with `VISTA_HOME_BUILD_EXECUTION_DRIFT`.

## Fail-closed cases

The runner refuses, among other cases:

- path without SHA, or SHA without path;
- wrong SHA or post-pin byte changes;
- wrong profile ID or schema;
- stale or forged content digest;
- a profile bound to another HouseSpec digest;
- materialized JSON that differs from the in-memory validated profile;
- any dry-run/apply execution-manifest drift.

An apply failure leaves the append-only attempt unaccepted. Do not treat a
staged or successfully composed R18 profile as proof that the required external
visual assets, R14/R15 detail-action UAssets, or CitySample/Manny retarget
authority are complete.

## Compatibility boundary

`simworld.vista.playable-home-ue-execution/v1` remains the execution schema.
The R18 descriptor is optional and additive. When the two CLI arguments are
omitted, the runner does not emit any typed-scene profile field and calls the
legacy composition path with no overlay; existing visual-profile, R4 realism,
presentation, script, project, and artifact pins remain unchanged.

## Source-only validation

```bash
TMPDIR=/data/sysx/tmp/vista-r18-typed-profile-runner \
UV_CACHE_DIR=/data/sysx/uv-cache \
PYTEST_ADDOPTS='-o cache_dir=/data/sysx/cache/pytest-vista-r18-typed-profile-runner' \
PYTHONPATH=. uv run pytest -q \
  tools/tests/test_vista_playable_home_r18_typed_profile_runner.py \
  tools/tests/test_vista_playable_home_build_home.py \
  tools/tests/test_vista_playable_home_realism_unreal.py \
  tools/tests/test_vista_playable_home_realism_r4.py
```
