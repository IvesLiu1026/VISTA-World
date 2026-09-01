# VISTA R21 first-person camera toggle R1

This source slice adds an owner-local camera presentation switch to the single
`AVistaPlayableHomeCharacter`. It does not spawn a second player, send an RPC,
or alter replicated action, movement, posture, carry, or EventSpec authority.

## Demo control

- `V`: switch between the existing third-person follow camera and the
  capsule-mounted first-person eye camera.
- Mouse look stays on the existing controller yaw/pitch path, including full
  horizontal rotation.
- The HUD names the active view and the available `V` transition.

The default remains the existing third-person camera. First person uses a
separate inactive-by-default camera component, so the spring-arm length,
socket, collision recovery, lag, and follow-camera settings are not rewritten.
On return, the exact prior active-camera and owner-visibility bits are restored.
The local owner body and reviewed visual provider use `OwnerNoSee` in first
person to prevent head/body clipping without hiding the actor for other views.

## Validation boundary

Run the focused source contract with:

```bash
TMPDIR=/data/sysx/tmp/vista-playable-actions-r2 \
UV_CACHE_DIR=/data/sysx/uv-cache \
PYTEST_ADDOPTS='-o cache_dir=/data/sysx/cache/pytest-vista-playable-actions-r2' \
uv run pytest -q tools/tests/test_vista_playable_home_first_person_camera.py
```

This is source validation only. BuildPlugin and a human Sunshine test remain
the runtime gates for camera activation, clipping, input capture, and feel.
