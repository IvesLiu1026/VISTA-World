"""No-I/O dispatcher boundary for source-only EventSpec v4 plans.

This module builds typed UE adapter *preflight* envelopes.  It deliberately has no
socket/exchange/execute function and cannot authorize runtime actions.
"""

from __future__ import annotations

import copy
from typing import Any, Mapping

from worlds import playable_home as base
from worlds import playable_home_event_v4_compiler as compiler


ENVELOPE_SCHEMA_VERSION = "simworld.vista.action-preflight-envelope/v4"
RUNTIME_TYPES = frozenset(binding[2] for binding in compiler.WIRE_BINDINGS.values())


def _fail(code: str, path: str, message: str) -> None:
    raise base.PlayableHomeContractError(code=code, path=path, message=message)


def prepare_dispatch(sidecar: Mapping[str, Any], **authorities: Any) -> tuple[dict[str, Any], ...]:
    """Recompile authorities and return immutable-by-copy source-only plans."""

    compiler.validate_runtime_sidecar(sidecar, **authorities)
    if sidecar["accepted"] is not False or sidecar["runtime_execution_authorized"] is not False:
        _fail("VISTA_HOME_EVENT_V4_DISPATCH_FORBIDDEN", "$", "V4 source-only plan is never runtime authorized")
    return tuple(copy.deepcopy(sidecar["event_plans"]))


def _targets(action: Mapping[str, Any], *, path: str) -> list[dict[str, str]]:
    parameters = action["parameters"]
    roles = action["identity_roles"]
    if set(roles) - set(parameters):
        _fail("VISTA_HOME_EVENT_V4_IDENTITY_ROLE_INVALID", path, "Identity role has no exact parameter value")
    result = []
    for parameter in ("room_id", "target_id", "secondary_target_id", "placement_anchor_id"):
        if parameter in roles:
            value = parameters[parameter]
            if type(value) is not str:
                _fail("VISTA_HOME_EVENT_V4_IDENTITY_TYPE_INVALID", f"{path}.{parameter}", "Typed identity must be a string")
            result.append({"parameter": parameter, "role": roles[parameter], "semantic_id": value})
    return result


def build_preflight_envelopes(sidecar: Mapping[str, Any], **authorities: Any) -> tuple[dict[str, Any], ...]:
    """Build closed typed envelopes without contacting or executing a UE adapter."""

    plans = prepare_dispatch(sidecar, **authorities)
    envelopes: list[dict[str, Any]] = []
    for plan in plans:
        for queue in plan["runtime_queues"]:
            for action in queue["actions"]:
                path = f"$.event_plans.{plan['event_id']}.{queue['queue_id']}.{action['sequence_index']}"
                if action["runtime_type"] not in RUNTIME_TYPES:
                    _fail("VISTA_HOME_EVENT_V4_RUNTIME_TYPE_INVALID", path, "Runtime type is outside the closed v4 allowlist")
                envelope = {
                    "schema_version": ENVELOPE_SCHEMA_VERSION,
                    "kind": "vista_world_action_preflight",
                    "event_id": plan["event_id"],
                    "event_content_digest": plan["event_content_digest"],
                    "queue_id": queue["queue_id"],
                    "npc_id": queue["npc_id"],
                    "action_id": action["action_id"],
                    "sequence_index": action["sequence_index"],
                    "canonical_action_id": action["canonical_action_id"],
                    "backend_action": action["backend_action"],
                    "runtime_type": action["runtime_type"],
                    "targets": _targets(action, path=path),
                    "parameters": copy.deepcopy(action["parameters"]),
                    "preflight_only": True,
                    "accepted": False,
                    "runtime_execution_authorized": False,
                    "live_composition_status": "pending_ue_adapter_and_visual_acceptance",
                }
                envelopes.append(envelope)
    return tuple(envelopes)


def dry_run_report(sidecar: Mapping[str, Any], **authorities: Any) -> dict[str, Any]:
    envelopes = build_preflight_envelopes(sidecar, **authorities)
    return {
        "ok": True,
        "mode": "source_only_preflight_envelope_generation",
        "envelope_count": len(envelopes),
        "runtime_execution_authorized": False,
        "live_composition_status": "pending_ue_adapter_and_visual_acceptance",
        "required_next_authority": "ue_event_v4_adapter_plus_visual_acceptance_receipts",
    }
