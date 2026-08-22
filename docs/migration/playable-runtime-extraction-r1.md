# VISTA World Playable Runtime Extraction R1

Status: source extracted; T7 BuildPlugin and T9 source validation passed
Approval date: 2026-08-22
Target branch: `codex/playable-runtime-extraction-r1`

## Purpose

This extraction makes VISTA-World the canonical owner of the playable-home
runtime, build pipelines, and data contracts. SimWorld-Studio remains an
upstream provenance and compatibility source; its Studio server, web UI, and
general orchestration are not product dependencies of VISTA-World.

## Pinned sources

| Role | Commit | Use |
| --- | --- | --- |
| Accepted VISTA-World baseline | `633244c8018771551e388f597c9d8e81bbc41a2b` | Contract/compiler anchor |
| Runtime rollback point | `57fc8485097cd4514a9f223cfd8fffda3d8c3c87` | Bounded cold-start fallback |
| Selected extraction source | `d80aa78f7681e378a051528ec55b7cfdbe39f64d` | Runtime, forge, packaging, and renderer acceptance source |
| Discovery-only realism tip | `2571455fab4bf19bc622d656a1adf29313f3b16e` | Not extracted by this change |

The selected source is `IvesLiu1026/SimWorld-Studio`, licensed under
Apache-2.0. The complete per-file source path, Git blob, last modifying
commit, target path, and disposition are recorded in
[`playable-runtime-extraction-r1.tsv`](playable-runtime-extraction-r1.tsv).

## Extracted ownership surfaces

| Target surface | Files | VISTA-World responsibility |
| --- | ---: | --- |
| `unreal_plugins/VistaPlayableHome/**` | 49 | UE runtime/editor plugin, third-person interaction, NPC, event and typed loopback adapter |
| `tools/blender/vista_playable_home/**` | 5 | Contract-driven procedural home forge |
| `tools/blender/vista_playable_home_hssd/**` | 7 | Optional private-research HSSD visual binding |
| `tools/blender/vista_playable_home_realism/**` | 15 | Licensed deterministic realism forge and source resolution |
| `tools/ue/vista_playable_home/**` | 15 | UE composition, import, package materialization, and receipts |
| `tools/runtime/vista_playable_home/**` | 14 | Preview/package lifecycle plans, acceptance, and Sunshine entry generation |
| `tools/tests/test_vista_playable_home_*.py` | 30 | Extracted offline parity and regression coverage |
| Visual profile schema and profiles | 6 | R2 visual, placement, acquisition, and UE 5.7.3 renderer contracts |

All 141 selected files were materialized from one `git archive` of the pinned
source commit. Existing VISTA-World HouseSpec, EventSpec, BuildPlan compiler,
three baseline schemas, and their tests were not overwritten. Their target
bytes match the selected source for the compiler, contract tests, house, and
all seven event documents.

## Compatibility policy

The extracted source initially retains historical paths and
`simworld.vista.*` schema identifiers. Those identifiers are compatibility
wire names, not an ownership claim and not a runtime dependency on SimWorld.
Renaming them before standalone parity would break accepted receipts and is
therefore deferred to an explicit versioned migration.

One package materializer constant names a historical SimWorld NAS proof log.
It is retained only as upstream provenance metadata. It is not a VISTA-World
input, authorization, runtime path, or reusable acceptance claim; new package
proof must be generated under a caller-approved VISTA-World run root.

## VISTA-World post-extraction adaptations

The initial archive bytes remain recoverable through the per-file ledger. The
following VISTA-World-owned change adds a closed EventSpec outcome evaluator;
each modified Apache-2.0 source file carries a prominent modification notice:

- typed `entity_state`, `entity_room`, `player_room`, `interaction`, and
  `elapsed` conditions in the UE contract;
- all-success, any-failure, then generic-timeout terminal evaluation;
- successful interaction reporting from local player, direct placement, NPC,
  and typed TCP gameplay paths;
- deterministic BuildPlan-to-UE condition materialization, including pinned
  room bounds for movable entity and player location checks.

The modified plugin source tree is sealed by source-manifest SHA-256
`557ae4a7d4f1144672ea6c4b4cad736b02025c04df6547ab8d8019f80042167b`.
UE 5.7.3 BuildPlugin accepted Editor, UnrealGame Development, and UnrealGame
Shipping targets. The resulting 186-file, 35,209,187-byte package is sealed by
package-manifest SHA-256
`d442414bc968197da349b12b5cb42b03dd111a1fd80a67f206735d4ee457c58e`.

## Deliberate exclusions

- SimWorld Studio web/server, workspace UI, agents, adapters, and general asset services.
- External HSSD, YCB, Poly Haven, Fab, animation, Manny, and Unreal Engine payloads.
- UE/Blender binaries, generated GLB/Blend/UAsset/UMAP/PAK files, packages, logs, and receipts.
- Canonical VISTA datasets, private evidence, credentials, host configuration, and NAS content.
- The rejected Publisher/rematerializer prototype `c7ae5a22a934285205b44588a38b0b0d4cd37586`.
- Daily Maintainer scheduling, promotion, publisher, auto-merge, or runtime lifecycle changes.

## Safety state

The extracted programs are dormant source. No Unreal, Blender, GPU, network
download, Sunshine service, package build, or listener was started during
extraction. Poly Haven acquisition, HSSD processing, UE `--apply`, packaging,
runtime launch, and Sunshine mutation remain separate explicit authorization
gates. Source presence is not runtime evidence.

## Validation state

T6 completed on 2026-08-22 with 195 offline tests passing and no failures or
errors. After the T9 EventSpec outcome implementation, the same suite passed
198 tests. The accepted command used the root project plus both compatible
Python import roots:

```bash
PYTHONPATH=.:tools uv run --offline --no-sync --with pytest \
  python -m unittest discover -s tools/tests \
  -p 'test_vista_playable_home_*.py' -v
```

UE 5.7.3 BuildPlugin is proven for the pinned source and engine bytes above.
Disposable project composition, package materialization, live EventSpec
outcomes, renderer observation, and Moonlight input remain unproven in
VISTA-World until their corresponding retained validation steps complete.
