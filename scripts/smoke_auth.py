"""Interactive auth smoke test inside the pilot container; no credentials in output."""

from __future__ import annotations

import argparse
import getpass
import hashlib
import json
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
from uuid import UUID, uuid4


class SmokeFailure(Exception):
    pass


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise SmokeFailure("redirect_refused")


def _request(method: str, route: str, data: bytes | None = None, token: str = "", extra=None):
    headers = {"Content-Type": "application/json"}
    headers.update(extra or {})
    if token:
        headers["Authorization"] = "Bearer " + token
    request = Request(  # noqa: S310 - fixed loopback service within the pilot container
        "http://127.0.0.1:8080" + route,
        method=method,
        headers=headers,
        data=data,
    )
    opener = build_opener(ProxyHandler({}), _NoRedirect())
    try:
        with opener.open(request, timeout=15) as response:
            body = response.read(512 * 1024 + 1)
            if len(body) > 512 * 1024:
                raise SmokeFailure("response_too_large")
            return response.status, body
    except HTTPError as error:
        # Error bodies are deliberately ignored, including potentially private details.
        status = error.code
        error.close()
        return status, b""


def _call(method: str, route: str, payload=None, token: str = ""):
    status, body = _request(
        method, route, json.dumps(payload).encode() if payload is not None else None, token
    )
    return status, json.loads(body) if body else None


def _require(condition: bool, phase: str) -> None:
    if not condition:
        raise SmokeFailure(phase)


def _documents(household_id: str, token: str) -> dict[str, bool]:
    route = f"/api/v1/households/{household_id}/documents"
    status, previous = _call("GET", route, token=token)
    _require(status == 200 and isinstance(previous, list), "document_list_failed")
    existing = {value["id"] for value in previous}
    marker = uuid4().hex
    filename = "jarvis-synthetic-smoke-" + marker + ".txt"
    content = ("Jarvis synthetic storage smoke test. Marker: " + marker).encode()
    digest = hashlib.sha256(content).hexdigest()
    status, raw = _request(
        "POST",
        route,
        content,
        token,
        {"Content-Type": "text/plain", "X-Filename": filename},
    )
    _require(status == 201, "synthetic_upload_failed")
    document = json.loads(raw)
    document_id = str(UUID(document["id"]))
    _require(
        document_id not in existing
        and document.get("household_id") == household_id
        and document.get("original_filename") == filename
        and document.get("sha256") == digest
        and document.get("size_bytes") == len(content),
        "synthetic_upload_identity_mismatch",
    )
    own_route = route + "/" + document_id
    result = {"document_uploaded": True}
    try:
        status, original = _request("GET", own_route + "/content", token=token)
        _require(status == 200 and original == content, "synthetic_original_mismatch")
        result["original_content_and_hash_verified"] = True
        status, _ = _request("GET", own_route + "/content")
        _require(status == 401, "anonymous_document_access_not_rejected")
        result["anonymous_document_blocked"] = True
        status, _ = _request(
            "GET", f"/api/v1/households/{uuid4()}/documents/{document_id}/content", token=token
        )
        _require(status == 404, "wrong_household_not_hidden")
        result["wrong_household_hidden"] = True
        status, _ = _request("GET", route + f"/{uuid4()}/content", token=token)
        _require(status == 404, "missing_document_not_hidden")
        result["missing_document_hidden"] = True
        status, _ = _call("POST", own_route + "/analysis", token=token)
        _require(status == 503, "analysis_not_disabled")
        result["analysis_disabled"] = True
    finally:
        # Delete only the new ID from this run, after rereading its exact synthetic bytes.
        status, original = _request("GET", own_route + "/content", token=token)
        _require(status == 200 and original == content, "synthetic_cleanup_identity_not_verified")
        status, _ = _call("DELETE", own_route, token=token)
        _require(status == 204, "synthetic_cleanup_failed")
    status, _ = _request("GET", own_route + "/content", token=token)
    _require(status == 404, "synthetic_document_still_visible")
    result["synthetic_document_removed"] = True
    return result


def check(email: str, password: str, *, documents: bool = False) -> dict[str, object]:
    result: dict[str, object] = {}
    status, _ = _call("GET", "/api/v1/me")
    _require(status == 401, "anonymous_access_not_rejected")
    result["anonymous_blocked"] = True
    status, pair = _call("POST", "/api/v1/auth/login", {"email": email, "password": password})
    _require(status == 200 and isinstance(pair, dict), "login_failed")
    token = pair.get("access_token")
    _require(isinstance(token, str) and bool(token), "login_response_invalid")
    result["login"] = True
    try:
        status, me = _call("GET", "/api/v1/me", token=token)
        _require(
            status == 200
            and isinstance(me, dict)
            and me.get("id") == pair.get("user", {}).get("id"),
            "profile_identity_mismatch",
        )
        result["profile_identity_verified"] = True
        status, households = _call("GET", "/api/v1/households", token=token)
        _require(status == 200 and isinstance(households, list), "household_read_failed")
        owned = [value for value in households if value.get("role") == "owner"]
        _require(bool(owned), "owner_membership_missing")
        household_id = str(UUID(owned[0]["id"]))
        status, people = _call("GET", f"/api/v1/households/{household_id}/people", token=token)
        _require(status == 200 and isinstance(people, list), "people_read_failed")
        _require(
            any(value.get("linked_user_id") == me["id"] for value in people),
            "linked_owner_person_missing",
        )
        result["owner_household_verified"] = True
        result["linked_person_verified"] = True
        if documents:
            result.update(_documents(household_id, token))
    finally:
        status, _ = _call("POST", "/api/v1/auth/logout", token=token)
        _require(status == 204, "logout_failed")
    result["logout"] = True
    status, _ = _call("GET", "/api/v1/me", token=token)
    _require(status == 401, "revoked_session_still_accepted")
    result["session_revoked"] = True
    result["ok"] = True
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--documents", action="store_true")
    arguments = parser.parse_args()
    try:
        email = input("Email applicazione Jarvis: ").strip()
        password = getpass.getpass("Password applicazione Jarvis: ")
        result = check(email, password, documents=arguments.documents)
    except SmokeFailure as error:
        # Only fixed internal phase identifiers are printed; never server bodies.
        print(json.dumps({"ok": False, "error": str(error)}))
        return 1
    except Exception:
        print(json.dumps({"ok": False, "error": "auth_smoke_unavailable"}))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
