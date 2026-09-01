# VISTA R17 Pour action integration R1

## Status

The R17 source integration and offline Unreal behavior proofs pass. This
milestone does **not** claim that the action is present in the current live map,
packaged, visually accepted or Sunshine-playable. It also does not add Pour to
the frozen EventSpec v3 contract.

## Integrated action path

The closed path is:

```text
player E / typed TCP / finite generic NPC queue
  -> exact held pickup source + exact liquid receiver
  -> shared semantic action executor
  -> atomically reserve both actors
  -> align requester and retain the aligned held-item snapshot
  -> approved R15 Pour montage
  -> vista_pour_tilt_contact
  -> deterministic source debit + receiver credit
  -> vista_pour_completed
  -> atomically release both reservations and publish one terminal receipt
  -> record the receiver as one successful VISTA interaction observation
```

The canonical semantic command is versioned as
`vista.semantic-command/v2`; its signature includes both semantic identities.
A missing, identical or unexpected secondary target fails before mutation.
Player interaction prioritizes Pour over Place only when the held item is
pourable and the focused actor is a typed liquid receiver. The HUD names both
objects.

## State, alignment and rollback contract

The action distinguishes an actual object mutation from world-pose movement
inherited from the carrier. Turning the requester toward the receiver changes
the held object's world transform, but must preserve its attachment-relative
transform, inventory identity, collision profile, velocity and held state.
The aligned snapshot is then bit-exact across the contact mutation.

- one successful contact changes exactly two liquid states and reports zero
  direct rigid-body mutations;
- a post-contact failure restores receiver then source liquid, the original
  requester transform and the exact initial held-item snapshot;
- source and receiver reservation release is retry-safe and idempotent;
- destruction cleanup resolves the exact weak peer even while that peer is
  pending kill;
- UE 5.7 held items use the native `NoCollision` profile. Pairing
  `PhysicsActor` with an overridden `NoCollision` mode is invalid because UE
  deliberately renames that combination to `Custom`.

## VISTA and transport boundary

The generic runtime and NPC queue can execute Pour through the shared executor.
Whole-queue preflight simulates source and receiver liquid amounts, so a later
Pour in the same queue is checked against the earlier planned transfer rather
than stale actor state. Receipts retain primary and secondary identities, both
state snapshots and transferred millilitres.

EventSpec v3 remains a closed public contract. Its schema, compiler and
dispatcher reject `pour`, `secondary_target_id` and forged runtime Pour actions.
The Unreal runtime repeats that allowlist check so a direct C++ call cannot
bypass it. Adding dataset-authored Pour requires a separately versioned EventSpec
and new authority digests; this milestone does not reseal v3.

## Verification evidence

The exact integrated editor bytes passed these NullRHI automation tests:

```text
VISTA.PlayableHome.Pour.ActionExecutorIntegration
/data/sysx/vista-world/runs/vista-action-world-r1/
  pour-action-r17-ue-automation-20260901g/UnrealEditor.log

VISTA.PlayableHome.PourTransactionR1.AtomicTwoTargetMutation
/data/sysx/vista-world/runs/vista-action-world-r1/
  pour-primitive-r17-ue-automation-20260901e/UnrealEditor.log
```

The integration proof covers successful 200 ml transfer, receiver-bound command
identity, alignment without false physical drift and forced post-contact
rollback. The primitive proof covers planning, incompatible/full receivers,
two-sided reservation, partial-commit compensation, retry-safe release and both
peer-destruction directions.

Focused Python contracts cover the shared executor, player/HUD, animation,
typed TCP, generic NPC queue and EventSpec v3 fail-closed boundary. A fresh
UE 5.7.3 BuildPlugin run passed UnrealEditor Development, UnrealGame Development
and UnrealGame Shipping with UHT warnings treated as errors:

```text
/data/sysx/vista-world/runs/vista-action-world-r1/
  playable-actions-r2-plugin-build-r17-20260901d
```

The EventSpec defense-in-depth proof also passed:

```text
VISTA.PlayableHome.EventV3.QueuePreflightReadOnly
/data/sysx/vista-world/runs/vista-action-world-r1/
  event-v3-pour-guard-r17-ue-automation-20260901a/UnrealEditor.log
```

## Remaining acceptance gates

- Compose a real pourable bottle or jug and at least two typed glasses/bowls into
  the private research scene without committing external assets.
- Bind the exact R15 montage and contact/completion notifies in the composed
  project, then cook and package an exact-tip candidate.
- Human-test selection priority, turn alignment, hand/object clipping, liquid
  feedback and repeated transfers through Sunshine/Moonlight.
- Version the VISTA dataset event contract only after real samples justify a
  stable two-target Pour schema.
- Do not describe R17 as a playable demo until those composition, package and
  human-observation gates pass.
