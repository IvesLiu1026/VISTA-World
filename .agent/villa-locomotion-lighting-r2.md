# Villa R2 — locomotion, natural first person and daylight

Agent/session: Codex, current user-directed implementation task.
Worktree: `/data/sysx/vista-world/worktrees/vista-villa-locomotion-lighting-r2`
Branch: `codex/vista-villa-locomotion-lighting-r2`
Base: integration commit `830bca5cb9ea58454bf2f71a7f780866fed35a2d`.

Owns: Villa character, narrowly scoped opt-in hooks in EmbodiedReview, Villa
motion/lighting authoring and private validation tools, focused tests, evidence
manifests and workflow documentation. Solo implementation, no delegated writers.

Must not touch: main, previous worktrees, frozen Villa R1 and Home R5 projects,
live game/input processes, production 8000, development 8001, datasets/secrets.
Live Villa R1 at entry: game service PID 3852019 and input service PID 3853922;
project is `vista-villa-r1-20260910b/demo-project-a/PhotorealHome.uproject`.

Runtime ownership: fresh local copies and bounded private GPU 1 proofs under
`/data/sysx/vista-world/runs/vista-villa-r1-20260910c`, separate displays/network
namespace; existing user authorization covers builds and local demo delivery.

Acceptance: less clipped exterior; visible stair/gallery daylight; unoccupied
arms hang naturally in both views; free look reveals the same body; continuous
walk timing without two competing gait layers; preserved lengths and contact;
pickup/pour/place/stairs and original Home pose regressions. Rendered review
remains necessary beyond numerical landmarks. No claim of GTA-equivalent quality
or of Rockstar's internal animation implementation.

Validation: baseline uv contract/compiler checks, focused motion behavior,
Editor/Game builds, isolated native frame sequence and functional receipts,
visual review, named commits and PR to the integration branch.

Completed acceptance: Editor build-h and Linux Game Development/Shipping build-game-d;
650 fixed-step motion frames across 12 cases, maximum full-stance excursion 1.43 cm;
12 original Home pose/interaction cases; native-d pickup, pour, place and stairs;
28 baseline and 7 focused tests. Final asset/proof hashes are recorded in
`docs/design/vista-villa-r2/implementation-manifest.json`.

Delivery: `vista-villa-r1-20260910c/demo-project-b`, 2,848 equal copied files;
`demo-b/sunshine-profile.json`, explicit selection via `VISTA Villa R2`.
Sunshine was reloaded while FREE; all eight older entries and the original game/input
PIDs remained unchanged. No new client/game session was started. Villa R1's 2,763
frozen files still match its manifest; Home R5 map/plugin match its profile.
