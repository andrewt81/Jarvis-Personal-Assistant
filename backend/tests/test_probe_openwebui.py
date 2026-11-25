from __future__ import annotations

import importlib.util
from pathlib import Path
from urllib.error import HTTPError

import pytest
from jarvis.documents.analysis import AnalysisUnavailableError

spec = importlib.util.spec_from_file_location(
    "probe_openwebui", Path(__file__).resolve().parents[2] / "scripts" / "probe_openwebui.py"
)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class Client:
    def __init__(self, base, denied=False):
        self.base = base
        self.denied = denied
        self.calls = []

    def request(self, method, route):
        self.calls.append((method, route))
        if self.denied:
            try:
                raise HTTPError("http://private", 401, "private body", {}, None)
            except HTTPError:
                raise AnalysisUnavailableError("Open WebUI request failed") from None
        return self.base


def test_readable_base_model_is_required_and_id_is_url_encoded():
    client = Client({"id": "qwen:27b", "base_model_id": None})
    assert probe.check_base_access(client, {"id": "jarvis", "base_model_id": "qwen:27b"}) == 1
    assert client.calls == [("GET", "/api/v1/models/model?id=qwen%3A27b")]


@pytest.mark.parametrize(
    "base,denied",
    [
        ({"id": "qwen:27b"}, True),
        ({"id": "different"}, False),
        ({"id": "qwen:27b", "is_active": False}, False),
        ({"id": "qwen:27b", "base_model_id": "jarvis"}, False),
        ({"id": "qwen:27b", "base_model_id": ["bad"]}, False),
    ],
)
def test_missing_permission_or_invalid_chain_never_passes(base, denied):
    with pytest.raises(AnalysisUnavailableError):
        probe.check_base_access(Client(base, denied), {"id": "jarvis", "base_model_id": "qwen:27b"})
