# Responsive dialogue and distinct humanoid companion

The six-room prototype now has separate human and robot appearances. The human
remains the person who needs assistance; the robot uses the existing companion
planner, following, collision and contact execution. Large-model decisions remain
final. Laya measures text intent in a parallel, non-authoritative channel.

## Dialogue behavior

`--research-stream` requests SSE from the same explicitly routed GPT-5.4-mini
provider. A completed `speech` JSON string can prepare the first complete sentence
using local male Kokoro TTS while the remaining decision arrives. No audio or
physical action executes until the full document passes the existing schema,
evidence, permission, scene, revision and freshness checks. The final speech must
match a prepared clip before that clip is reused. Unfinished streams, unsupported
fields, tool calls and altered provider identities fail closed. Completed JSON
fences accepted by the final parser are supported for preparation only.

New input invalidates old and queued sentences, and interrupts current assistant
audio. A separate preparation worker avoids contention with the policy pool.
Only local TTS can be speculative; failed streams never retry a paid call or fall
back to another provider. Durable request accounting and count/cost limits remain
in effect even when the client disconnects. The remote inference itself is not
cancelled by local interruption.

Native-start logs distinguish request time, direct input time, first provider
content, preview preparation and the first accepted audio start. Later action
completion does not count as another response to an already answered question.
These are server timings, not the acoustic latency heard on a Moonlight client.

Two small counterbalanced pilots used four frozen-image prompts each. Outputs and
sentence lengths vary; local TTS may have its own cache. This is engineering
measurement, not a statistically controlled model-speed comparison.

| Pilot | Serial audio-ready p50 | Streamed audio-ready p50 | Serial TTS wait after validation | Streamed wait |
| --- | ---: | ---: | ---: | ---: |
| Initial, without fenced previews | 6.356 s | 4.776 s | 1.109 s | 0.467 s |
| Final parser | 6.799 s | 6.397 s | 1.569 s | 0.418 s |

In a separate actual native run, five spoken answers started 4.096–6.573 seconds
after typed input (median 5.570 seconds). Recall of “mystery novels”, interruption
of an unfinished story, the new arithmetic answer, and follow/wait commands were
observed. The model chose a silent valid wait command; the original harness
incorrectly required a spoken acknowledgement and timed out. An independent
receipt/trace audit verified the actual wait, without a paid retry. Captured native
Pulse audio is non-silent. Cloud model latency still dominates; this does not
establish subsecond conversation.

## Optional local Laya

`laya_shadow.py` runs Laya 0.3.11 / torch 2.8.0+cpu with six CPU threads and pinned
`convaiinnovations/laya-multilingual` revision
`82d57fc4f2d1be3d2caac494045f2ec51d0842f3`. The loopback service accepts only recent
observed dialogue. It cannot receive Director events, gold labels or scene truth,
and its outputs never authorize, veto, rewrite or delay the large-model policy.
Only one shadow request can be outstanding; failures are logged separately.

An authored 42-case English/Chinese smoke probe got 36/42 labels correct. CPU
inference p50/p95 was 84.775/91.9 ms (max 122.12 ms). Help requests and ambiguous
phrases caused errors, including one confidently wrong Chinese request to close
the tap. Actual multi-turn runtime inputs took longer than these isolated short
utterances (one six-turn example was 232.24 ms). No Jev matched benchmark, visual
perception, conversation generation or reliable physical permission inference is
claimed. Do not treat its confidence as calibrated execution permission.

Reproduce in the separately provisioned local environment:

```sh
PYTHONPATH=tools <laya-python> -m runtime.vista_live.laya_shadow \
  --checkpoint <pinned-local-snapshot> --threads 6 --port 49130
PYTHONPATH=tools uv run python -m runtime.vista_live.benchmark_laya --out <fresh-run>
```

Upstream: [Laya multilingual](https://huggingface.co/convaiinnovations/laya-multilingual).
Jev remains the existing bounded scene asset selector; this change does not replace
it with a dialogue model or add arbitrary mesh generation.

## Character assets and limits

The human groom has 29,900 tapered geometry fibers, distributed roots, a raised
and refined hairline, asymmetric front locks and less reflective dark materials.
Head weighting and all 53 original bind transforms are retained. This improves the
coarse cap but is still a procedural prototype, not a production strand groom.

The assistant visual is adapted from the official
[Unitree G1 source](https://github.com/unitreerobotics/unitree_ros), pinned at
`ccfc6fd8430a17ba3dacef9a1e2faf64ff3b0aee`. The 50 referenced STL visual meshes and
URDF are checksum verified. BSD-3-Clause notices are retained in source and the
external Unreal payload. A dark visor insert closes the open CAD head housing;
cyan optics/chest accents respond to speech. Robot segments are rescaled and
attached to VISTA's retained 53-joint human rig. This is an adapted visual model,
not a Unitree dynamics model, Isaac Sim controller, or validated physical robot.
Contact success still uses the existing kinematic fingertip proxy, not full
articulated CAD collision or force simulation.

`fetch_robot.py`, `build_robot.py`, `refine_hair.py` and `import_responsive.py`
reproduce acquisition, adaptation and import into a fresh independent DEV copy.
Meshes, weights, model checkpoints and generated media remain outside Git.
The importer saves all dependencies and separates `VistaHumanAppearance.json`
from `VistaCompanion.json`; robot face settings cannot disable human blinking or
lip sync. Native review confirmed seven human face channels and an actual jaw
morph weight of 0.90 during cached male human speech.

## Verification and demonstration

- 78 focused Python checks and 28 contract/compiler checks pass.
- Broader unittest discovery with its existing pytest import dependency: 641/642
  pass. The inherited indoor-camera source assertion still fails; it checks
  `AVistaPlayableHomeCharacter::Tick` in an unrelated existing plugin. No assertion
  was weakened and no remote CI success is claimed.
- Unreal build 3 succeeds; all 64 plugin source files match the built project.
- All six rooms pass first/third-view body and camera checks. Robot approach,
  reaching and shutoff pass for both tap and stove with the existing contact gate.
- Native movement audit uses companion snapshot publication times; the human
  state and companion state publish at different rates and cannot share one
  timestamp. Earlier failed audit attempts are retained with their diagnostics.
- A private adapter-selection attempt landed on GPU 1 and was stopped. Accepted
  native checks run on physical GPU 0; other users' processes are preserved.
- Existing six Director scenarios, ten-theme gallery, ten research movies and
  offline pack are retained. Recorded movies are labeled September 22; current
  robot/groom changes are in the live view. No new human-client readback is implied.

The same Moonlight entry is **VISTA Six Rooms Live AI**. The accompanying demo
page is `http://100.114.231.122:48999/`. Typing starts a new live request; Stop
cancels assistance and returns control. The assistant starts paused to avoid idle
paid calls. Local Laya and local male TTS do not use cloud speech allowance.

The new bounded task ledger is separate from all prior ledgers: USD 2, 160 plan
calls, 20 decisions, one unused cloud-TTS slot. Existing exhausted ledgers are not
reset. Host-specific budgets, selection/rollback, source hashes and raw traces are
recorded under `runs/responsive-companion-20260924-a` and the workspace handoff.
