"""One synthetic document through the internal app and its configured AI provider.

Run interactively inside the AI pilot. Never print tokens, passwords, raw errors,
model reasoning or document analysis. Failed runs retain their synthetic document.
"""

from __future__ import annotations

import getpass
import hashlib
import json
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
from uuid import UUID, uuid4


class Failure(Exception):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise Failure("redirect_refused")


def require(condition, phase):
    if not condition:
        raise Failure(phase)


def request(method, route, token="", data=None, headers=None, *, timeout=15):
    merged = {"Content-Type": "application/json"}
    merged.update(headers or {})
    if token:
        merged["Authorization"] = "Bearer " + token
    req = Request(  # noqa: S310 - fixed loopback inside the operator-selected pilot
        "http://127.0.0.1:8080" + route, data=data, headers=merged, method=method
    )
    try:
        with build_opener(ProxyHandler({}), NoRedirect()).open(req, timeout=timeout) as response:
            body = response.read(512 * 1024 + 1)
            require(len(body) <= 512 * 1024, "response_too_large")
            return response.status, body
    except HTTPError as error:
        code = error.code
        error.close()
        return code, b""


def call(method, route, token="", payload=None, *, timeout=15):
    code, body = request(
        method,
        route,
        token,
        json.dumps(payload).encode() if payload is not None else None,
        timeout=timeout,
    )
    return code, json.loads(body) if body else None


def run(email, password, result):
    code, pair = call("POST", "/api/v1/auth/login", payload={"email": email, "password": password})
    require(code == 200 and isinstance(pair, dict), "login_failed")
    token = pair.get("access_token")
    require(isinstance(token, str) and bool(token), "login_token_invalid")
    result["login"] = True
    try:
        code, households = call("GET", "/api/v1/households", token)
        require(code == 200 and isinstance(households, list), "households_unavailable")
        owned = [item for item in households if item.get("role") == "owner"]
        require(len(owned) == 1, "single_owner_household_required")
        household = str(UUID(owned[0]["id"]))
        route = f"/api/v1/households/{household}/documents"
        code, previous = call("GET", route, token)
        require(code == 200 and isinstance(previous, list), "document_list_failed")
        previous_ids = {item["id"] for item in previous}
        marker = "PILOTA-" + uuid4().hex
        filename = "jarvis-synthetic-analysis-" + marker + ".txt"
        content = (
            "DOCUMENTO SINTETICO DI COLLAUDO. Nessuna pratica reale.\n"
            f"Codice pratica: {marker}\n"
            "Oggetto: restituzione del modulo di prova compilato.\n"
            "Scadenza per restituire il modulo: 30 novembre 2026.\n"
            "Destinatario: non indicato.\nCosto: non indicato.\n"
        ).encode()
        digest = hashlib.sha256(content).hexdigest()
        code, raw = request(
            "POST", route, token, content, {"Content-Type": "text/plain", "X-Filename": filename}
        )
        require(code == 201, "synthetic_upload_failed")
        document = json.loads(raw)
        document_id = str(UUID(document["id"]))
        require(
            document_id not in previous_ids
            and document.get("household_id") == household
            and document.get("original_filename") == filename
            and document.get("sha256") == digest
            and document.get("size_bytes") == len(content),
            "synthetic_upload_identity_mismatch",
        )
        result.update(
            document_uploaded=True, synthetic_document_retained=True, document_id=document_id
        )
        own = route + "/" + document_id
        code, original = request("GET", own + "/content", token)
        require(code == 200 and original == content, "original_mismatch")
        result["original_content_and_hash_verified"] = True
        for target, expected, label in (
            (own + "/analysis/latest", 404, "analysis_initially_absent"),
            (route + f"/{uuid4()}/analysis/latest", 404, "missing_document_hidden"),
            (
                f"/api/v1/households/{uuid4()}/documents/{document_id}/analysis/latest",
                404,
                "wrong_household_hidden",
            ),
        ):
            code, _ = call("GET", target, token)
            require(code == expected, label + "_failed")
            result[label] = True
        code, _ = call("POST", own + "/analysis")
        require(code == 401, "anonymous_analysis_not_blocked")
        result["anonymous_analysis_blocked"] = True
        print("SYNTHETIC_ANALYSIS_STARTED (attesa massima 3600 secondi)", flush=True)
        code, analysis = call("POST", own + "/analysis", token, timeout=3615)
        result["analysis_http_status"] = code
        require(code == 200 and isinstance(analysis, dict), "analysis_failed")
        require(analysis.get("document_id") == document_id, "analysis_document_mismatch")
        analysis_id = str(UUID(analysis["id"]))
        result["analysis_completed_and_document_verified"] = True
        facts = analysis.get("facts", [])
        deadlines = analysis.get("deadlines", [])
        result["marker_source_verified"] = any(
            marker in item.get("source_text", "") for item in facts
        )
        result["deadline_source_verified"] = any(
            "30 novembre 2026" in item.get("source_text", "").lower() for item in deadlines
        )
        result["deadline_value_verified"] = any(
            item.get("date", "").strip().lower() in {"2026-11-30", "30/11/2026", "30 novembre 2026"}
            for item in deadlines
        )
        missing = " ".join(analysis.get("missing_information", [])).lower()
        result["missing_information_reported"] = "destinat" in missing or "costo" in missing
        code, latest = call("GET", own + "/analysis/latest", token)
        require(code == 200 and latest == analysis, "persisted_analysis_mismatch")
        result["persisted_analysis_verified"] = True
        code, _ = call("GET", own + "/analysis/latest")
        require(code == 401, "anonymous_stored_analysis_not_blocked")
        result["anonymous_stored_analysis_blocked"] = True
        code, _ = call(
            "GET",
            f"/api/v1/households/{uuid4()}/documents/{document_id}/analysis/latest",
            token,
        )
        require(code == 404, "stored_analysis_wrong_household_not_hidden")
        result["stored_analysis_wrong_household_hidden"] = True
        code, cached = call("POST", own + "/analysis", token)
        require(
            code == 200 and cached == analysis and cached["id"] == analysis_id, "cache_mismatch"
        )
        result["unchanged_document_cached_result_verified"] = True
        for check in (
            "marker_source_verified",
            "deadline_source_verified",
            "deadline_value_verified",
            "missing_information_reported",
        ):
            require(result[check], check + "_failed")
        # Cleanup is limited to this run's new ID after its exact bytes are reread.
        # On any previous failure/timeout, retain it for diagnosis instead.
        code, original = request("GET", own + "/content", token)
        require(code == 200 and original == content, "cleanup_identity_not_verified")
        code, _ = call("DELETE", own, token)
        require(code == 204, "synthetic_cleanup_failed")
        result["synthetic_document_retained"] = False
        code, _ = request("GET", own + "/content", token)
        require(code == 404, "synthetic_document_still_visible")
        result["synthetic_document_removed_from_app"] = True
        result["openwebui_copy_cleanup_verified"] = False
        result["physical_s3_purge_verified"] = False
    finally:
        code, _ = call("POST", "/api/v1/auth/logout", token)
        require(code == 204, "logout_failed")
        result["logout"] = True
    code, _ = call("GET", "/api/v1/me", token)
    require(code == 401, "session_not_revoked")
    result["session_revoked"] = True


def main():
    result = {"ok": False, "synthetic_only": True}
    try:
        email = input("Email applicazione Jarvis: ").strip()
        password = getpass.getpass("Password applicazione Jarvis: ")
        run(email, password, result)
        result["ok"] = True
    except Failure as error:
        result["error"] = str(error)
    except Exception:
        result["error"] = "analysis_smoke_unavailable"
    print(json.dumps(result, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
