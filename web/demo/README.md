# VISTA World browser preview

A portable Three.js interaction preview for a standalone website or `/demo/`
subdirectory. Six lightweight furnished rooms, two rigged avatars, first/third
person cameras, collision, assisted navigation and contextual actions run locally
in the browser. The visible **scripted assistance** label is intentional.

WASD/arrows move, drag looks, E interacts and V switches cameras. Small screens
have a touch joystick and action button. “Stage a moment” recognizes bounded
English/Chinese descriptions of a phone call with a running bath or stove, or
walking with a companion. Unsupported requests are rejected visibly.

This is not a pixel-identical export of the Unreal home. It does not run Jev or
another model, use a microphone, generate arbitrary scenes, or produce research
evaluation results. Shutoffs are proximity/time scripts rather than native
fingertip/physics commits. First person hides the player mesh. Dialogue is text;
voice, conversational memory and fine manipulation remain in the research backend.
No API keys, research traces or local service URLs belong in this client bundle.

## Build

Use the workspace Node/npm wrappers or Node 22.12+ with npm:

```sh
npm ci --ignore-scripts --no-audit --no-fund
npm test
npm run build
npm run preview -- --port 49241
```

Before building, supply `public/models/human.glb` and `companion.glb` from the
reviewed export, with the checked-in credits and external manifest. Binary models
and packages are intentionally ignored by Git. Each avatar uses the existing
53-bone hierarchy and `Idle`/`Walk` clips. To reproduce from authorized local
source files, run Blender with `tools/blender/vista_companion/export_web.py`:

```sh
blender --background --threads 2 --python-exit-code 1 \
  --python tools/blender/vista_companion/export_web.py -- \
  --source SOURCE.blend --motion mocap.json --out OUTPUT --name human
```

Repeat with the G1 companion blend and `--name companion`. The exporter changes
only its in-memory scene. It strips duplicate owner meshes, reduces geometry,
keeps complete hair strands, omits facial morphs, bakes two clips and records
source/output hashes. It does not save over source blends.

## Hosting

Upload the **contents** of `dist` to a static host. Relative asset URLs support
both a hostname root and a subdirectory. Serve over HTTP(S), not `file://`.
No runtime server, server GPU, database or paid inference is required. A browser
with WebGL2 and hardware acceleration is recommended; performance depends on
the visitor's device. Test Safari on the actual Mac before a public presentation.

Suggested public destination: `https://demo.ivesliu.org/`. Keep the existing
Cloudflare Access-protected `vista.ivesliu.org` research service intact. The
`_headers` file supplies compatible static-host caching/CSP rules and permits
embedding from the owned ivesliu.org websites. Other hosts should apply equivalent
headers themselves. This repository does not change DNS, Access or production.

`wrangler.jsonc` prepares an assets-only Cloudflare Worker named
`vista-world-demo`, with only `demo.ivesliu.org` as its custom domain. It disables
workers.dev and version preview URLs. Before an approved publish, validate with
`WRANGLER_SEND_METRICS=false npx wrangler deploy --dry-run`; after the owner confirms
the public destination and authenticates the correct account, use
`WRANGLER_SEND_METRICS=false npx wrangler deploy`. The latter uploads assets and
configures the public custom domain, so it is deliberately not a build hook or CI
job. Config follows the official [static assets guide](https://developers.cloudflare.com/workers/static-assets/get-started/)
and [custom-domain guide](https://developers.cloudflare.com/workers/configuration/routing/custom-domains/).

Before a production publish, review the exact built artifact and confirm the
target hosting project/domain. A release can be rolled back by restoring the
previous static directory or the host's prior deployment; no database migration
is involved. The private preview and release archive are recorded in the workspace
handoff, separate from the public hostname.

## Checks and limits

`npm test` checks scenario support, collision tunnelling, path corner clearance,
water/shutoff consequences and reset invalidation. Browser review must use actual
UI/keyboard/pointer input, including all rooms, both cameras, the two assistance
examples, reset and assistance-off. `?debug` exposes a read-only state snapshot
for that review; it is not a model observation or policy interface.

The local source assets retain their MakeHuman, CMU and Unitree provenance.
`public/THIRD_PARTY_NOTICES.txt` accompanies every release. No Taipei GTA models,
animations, textures or source are used. Source binaries stay outside Git.
