# Grounded companion motion and stationary turns

The companion now brakes before its target, slows for large heading changes and
uses an acceleration-limited yaw controller. Walk phase follows actual travelled
distance. Both characters use alternating raised steps when turning in place;
the human retains its existing directional gait and body/look separation.

Companion ground correction runs once per engine frame from the animation proxy's
game-thread PreUpdate, after character movement. It uses the existing clip contact
weights, bounded stance anchors, floor traces and two-bone leg IK. It preserves
segment lengths and lowers the pelvis by at most 12 cm when needed. The support
foot counter-rotates with its planted heading. Characters cannot be used as steps;
the companion's obstacle step height is 22 cm. Existing permission, clearance,
hand contact and native shutoff checks remain in force.

This is a procedural correction layer over the existing retargeted CMU walking
clip. It does not install Motion Matching, use Taipei GTA code/assets, or claim
human-quality locomotion. A bounded 6 cm stance correction can still leave visible
drift; turns, slopes and crowded layouts need broader perceptual evaluation.

## Verification

- `tools/tests/test_vista_ground_motion.py` compiles the production C++ helper.
  It checks both turn directions across angle wrap at 15/30/60/120 Hz, single-foot
  lift, stationary support, reset, heading rate and braking distance.
- Contract/compiler, motion curves and body/look tests: 32 passed.
- Existing motion audit and director tests: 26 passed.
- Private UE 5.7.3 build and native review: 18 checks passed, including six rooms
  in both views, continuous fixed-view routes and native faucet/stove contact.
- Dense finalized-bone samples passed the existing continuity limits. Polled
  samples had two gaps just over 0.5 s; those failures remain in the evidence.
- Six route segments had at most 4.94 cm companion foot-goal error. Leg lengths
  stayed constant to floating-point precision. These measurements do not imply
  zero sliding or visual parity with commercial games.

Host-local evidence: `runs/natural-companion-motion-20261001-a/`, including failed
earlier reviews, final `review-c`, build logs, source hashes and rollback files.
The independent payload is `projects/six-room-companion-dev-natural-b`.

The reusable reviewer is `tools/runtime/vista_companion/review_ground_motion.py`.
Run it only against an owned private runtime launched with motion proof and ego
sensor capture. It operates real native input/bridge commands; it makes no model
calls. First and third person recordings are separate continuous routes.
