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
        OpenWebUIDocumentAnalyzer._check_profile(profile)
        result["profile_policy"] = True
        result["reasoning_boolean_true"] = profile["params"].get("think") is True
        result["context_65536"] = profile["params"].get("num_ctx") == 65536
        result["profile_tools_complete"] = set(profile["meta"].get("toolIds", [])) == set(TOOLS)
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
                "context_65536",
                "profile_tools_complete",
            )
        ) and all(result["tools_accessible"].values())
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
