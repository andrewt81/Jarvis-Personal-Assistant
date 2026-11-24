"""Read-only service-account probe. Never print responses or credentials."""

from __future__ import annotations

import json
import time
from urllib.error import HTTPError
from urllib.parse import quote

from jarvis.core.config import Settings
from jarvis.documents.analysis import AnalysisUnavailableError
from jarvis.documents.openwebui import OpenWebUIDocumentAnalyzer, _Client

TOOLS = ("jarvis_decimal_calculator", "jarvis_schedule_planner", "jarvis_original_pdf")


def check_base_access(client, profile):
    seen = {profile.get("id")}
    base_id = profile.get("base_model_id")
    hops = 0
    while base_id:
        if not isinstance(base_id, str) or base_id in seen or hops >= 8:
            raise AnalysisUnavailableError("Invalid base model chain")
        seen.add(base_id)
        base = client.request("GET", "/api/v1/models/model?id=" + quote(base_id, safe=""))
        if base.get("id") != base_id or base.get("is_active") is False:
            raise AnalysisUnavailableError("Base model is unavailable")
        base_id = base.get("base_model_id")
        hops += 1
    return hops


def probe(settings: Settings) -> dict:
    result: dict = {
        "mode": "read_only",
        "ok": False,
        "account_role": "not_verified_by_api",
    }
    phase = "credentials"
    client = None
    try:
        client = _Client(settings, time.monotonic() + 60)
        # v0.13.4 /auths/ requires a human session and rejects valid API keys.
        # Resource access below verifies this key, but cannot establish its role.
        phase = "profile"
        profile = client.request(
            "GET", "/api/v1/models/model?id=" + quote(settings.openwebui_model, safe="")
        )
        result["profile_identity"] = profile.get("id") == settings.openwebui_model
        result["profile_version"] = profile.get("version_id")
        params, meta = profile.get("params"), profile.get("meta")
        result["params_object"] = isinstance(params, dict)
        result["meta_object"] = isinstance(meta, dict)
        params = params if isinstance(params, dict) else {}
        meta = meta if isinstance(meta, dict) else {}
        hidden = profile.get("write_access") is False and params == {}
        result["params_hidden_for_read_only"] = hidden
        pinned = bool(settings.openwebui_profile_version_id) and (
            profile.get("version_id") == settings.openwebui_profile_version_id
        )
        result["pinned_version_matches"] = pinned
        tool_ids = meta.get("toolIds")
        valid_tool_list = isinstance(tool_ids, list) and all(
            isinstance(tool, str) for tool in tool_ids
        )
        result["reasoning_boolean_true"] = None if hidden else params.get("think") is True
        result["reasoning_value_type"] = type(params.get("think")).__name__
        result["context_65536"] = None if hidden else params.get("num_ctx") == 65536
        result["profile_not_disabled"] = profile.get("is_active") is not False
        result["tools_list_valid"] = valid_tool_list
        result["profile_tools_present"] = {
            tool: valid_tool_list and tool in tool_ids for tool in TOOLS
        }
        result["only_allowed_tools"] = valid_tool_list and all(tool in TOOLS for tool in tool_ids)
        result["no_profile_knowledge"] = not bool(meta.get("knowledge"))
        result["no_profile_filters"] = not bool(meta.get("filterIds"))
        result["native_calling_compatible"] = params.get("function_calling") in (None, "native")
        result["profile_tools_complete"] = valid_tool_list and set(tool_ids) == set(TOOLS)
        try:
            OpenWebUIDocumentAnalyzer._check_profile(
                profile, expected_version_id=settings.openwebui_profile_version_id
            )
            result["profile_policy"] = True
        except AnalysisUnavailableError:
            result["profile_policy"] = False
        phase = "base_model_chain"
        result["base_model_chain_accessible"] = False
        result["base_model_hops"] = check_base_access(client, profile)
        result["base_model_chain_accessible"] = True
        result["tools_accessible"] = {}
        for tool_id in TOOLS:
            phase = tool_id
            tool = client.request("GET", "/api/v1/tools/id/" + tool_id)
            result["tools_accessible"][tool_id] = tool.get("id") == tool_id
        result["ok"] = all(
            result[key]
            for key in (
                "profile_identity",
                "profile_policy",
                "profile_tools_complete",
                "base_model_chain_accessible",
            )
        ) and (result["context_65536"] is True or (hidden and pinned))
        result["ok"] = result["ok"] and all(result["tools_accessible"].values())
    except (AnalysisUnavailableError, KeyError, TypeError, AttributeError, ValueError) as exc:
        result["failed_phase"] = phase
        # Only expose the HTTP status; bodies can contain private data.
        if isinstance(exc.__context__, HTTPError):
            result["http_status"] = exc.__context__.code
    finally:
        if client is not None:
            client.close()
    return result


if __name__ == "__main__":
    output = probe(Settings.from_environment())
    print(json.dumps(output, sort_keys=True))
    raise SystemExit(0 if output["ok"] else 1)
