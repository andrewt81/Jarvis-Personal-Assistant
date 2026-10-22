from __future__ import annotations

import json
import os
import sys
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def call(
    method: str,
    path: str,
    *,
    token: str | None = None,
    payload: object | bytes | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, bytes]:
    base_url = os.environ.get("JARVIS_E2E_BASE_URL", "http://127.0.0.1:8080").rstrip("/")
    request_headers = dict(headers or {})
    if token:
        request_headers["Authorization"] = f"Bearer {token}"
    if payload is not None and not isinstance(payload, bytes):
        payload = json.dumps(payload).encode()
        request_headers["Content-Type"] = "application/json"
    request = Request(  # noqa: S310 - operator-supplied HTTP(S) test endpoint
        base_url + path, data=payload, method=method, headers=request_headers
    )
    try:
        with urlopen(request, timeout=15) as response:  # noqa: S310 - operator-supplied URL
            return response.status, response.read()
    except HTTPError as error:
        return error.code, error.read()


def json_call(*args, **kwargs) -> tuple[int, object]:
    status, body = call(*args, **kwargs)
    return status, json.loads(body or b"null")


def require_status(actual: int, expected: int, operation: str) -> None:
    if actual != expected:
        raise RuntimeError(f"{operation}: expected HTTP {expected}, received {actual}")


def main() -> int:
    email = os.environ["JARVIS_E2E_EMAIL"]
    password = os.environ["JARVIS_E2E_PASSWORD"]

    status, health = json_call("GET", "/health/ready")
    require_status(status, 200, "readiness")
    if health.get("status") != "ready":
        raise RuntimeError("readiness payload is invalid")

    status, login = json_call(
        "POST", "/api/v1/auth/login", payload={"email": email, "password": password}
    )
    require_status(status, 200, "login")
    token = login["access_token"]
    refresh_token = login["refresh_token"]

    status, households = json_call("GET", "/api/v1/households", token=token)
    require_status(status, 200, "household list")
    household_id = households[0]["id"]

    task_payload = {
        "title": "E2E release verification",
        "notes": "Disposable integration task",
        "priority": "urgent",
        "status": "open",
        "due_at": None,
        "person_id": None,
        "document_id": None,
    }
    status, task = json_call(
        "POST", f"/api/v1/households/{household_id}/tasks", token=token, payload=task_payload
    )
    require_status(status, 201, "task creation")

    original = b"Jarvis private E2E document\n"
    status, document = json_call(
        "POST",
        f"/api/v1/households/{household_id}/documents",
        token=token,
        payload=original,
        headers={"Content-Type": "text/plain", "X-Filename": "e2e.txt"},
    )
    require_status(status, 201, "document upload")
    document_id = document["id"]

    status, downloaded = call(
        "GET", f"/api/v1/households/{household_id}/documents/{document_id}/content", token=token
    )
    require_status(status, 200, "document download")
    if downloaded != original:
        raise RuntimeError("downloaded document differs from uploaded original")

    status, _ = call(
        "DELETE", f"/api/v1/households/{household_id}/documents/{document_id}", token=token
    )
    require_status(status, 204, "document deletion")

    task_payload["status"] = "done"
    status, completed = json_call(
        "PUT",
        f"/api/v1/households/{household_id}/tasks/{task['id']}",
        token=token,
        payload=task_payload,
    )
    require_status(status, 200, "task completion")
    if completed["status"] != "done":
        raise RuntimeError("task did not transition to done")

    status, refreshed = json_call(
        "POST", "/api/v1/auth/refresh", payload={"refresh_token": refresh_token}
    )
    require_status(status, 200, "session refresh")
    status, _ = call("POST", "/api/v1/auth/logout", token=refreshed["access_token"])
    require_status(status, 204, "logout")
    print("Jarvis MVP end-to-end test passed")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyError, RuntimeError, ValueError) as error:
        print(f"Jarvis MVP end-to-end test failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
