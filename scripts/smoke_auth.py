"""Interactive auth smoke test inside the pilot container; no credentials in output."""

from __future__ import annotations

import getpass
import json
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
from uuid import UUID


class SmokeFailure(Exception):
    pass


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise SmokeFailure("redirect_refused")


def _call(method: str, route: str, payload=None, token: str = ""):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    request = Request(  # noqa: S310 - fixed loopback service within the pilot container
        "http://127.0.0.1:8080" + route,
        method=method,
        headers=headers,
        data=json.dumps(payload).encode() if payload is not None else None,
    )
    opener = build_opener(ProxyHandler({}), _NoRedirect())
    try:
        with opener.open(request, timeout=15) as response:
            body = response.read(512 * 1024 + 1)
            if len(body) > 512 * 1024:
                raise SmokeFailure("response_too_large")
            return response.status, json.loads(body) if body else None
    except HTTPError as error:
        # Error bodies are deliberately ignored, including potentially private details.
        status = error.code
        error.close()
        return status, None


def _require(condition: bool, phase: str) -> None:
    if not condition:
        raise SmokeFailure(phase)


def check(email: str, password: str) -> dict[str, object]:
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
    try:
        email = input("Email applicazione Jarvis: ").strip()
        password = getpass.getpass("Password applicazione Jarvis: ")
        result = check(email, password)
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
