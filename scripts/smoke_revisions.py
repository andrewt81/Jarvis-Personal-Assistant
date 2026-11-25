"""Real SQL/S3/API revision test on temporary identities, with one new LLM analysis.

Requires smoke_analysis.py and smoke_isolation.py alongside this file. Originals,
revision links and test audit remain for diagnosis; test identities are disabled.
Never prints credentials, raw responses, final model text or model reasoning.
"""

from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID

from jarvis.core.config import Settings
from jarvis.documents.service import DocumentService
from smoke_analysis import Failure, call, request, require
from smoke_isolation import Fixture


def document_text(marker, date, revision):
    return (
        "DOCUMENTO SINTETICO DI COLLAUDO. Nessuna pratica reale.\n"
        f"Codice pratica: {marker}\nRevisione: {revision}\n"
        f"Scadenza per restituire il modulo: {date}.\n"
        "Destinatario: non indicato.\nCosto: non indicato.\n"
    ).encode()


def check_document(document, household, filename, content):
    require(isinstance(document, dict), "document_metadata_missing")
    document_id = str(UUID(document["id"]))
    require(
        document.get("household_id") == str(household)
        and document.get("original_filename") == filename
        and document.get("sha256") == hashlib.sha256(content).hexdigest()
        and document.get("size_bytes") == len(content),
        "document_identity_mismatch",
    )
    return document_id


def run(fixture, result):
    tokens = []
    for index in range(2):
        code, pair = call(
            "POST",
            "/api/v1/auth/login",
            payload={"email": fixture.emails[index], "password": fixture.passwords[index]},
        )
        require(code == 200 and isinstance(pair, dict), "fixture_login_failed")
        token = pair.get("access_token")
        require(isinstance(token, str) and bool(token), "fixture_token_invalid")
        code, me = call("GET", "/api/v1/me", token)
        require(code == 200 and me["id"] == str(fixture.users[index]), "fixture_identity_mismatch")
        tokens.append(token)
    base = f"/api/v1/households/{fixture.households[0]}/documents"
    filename = f"jarvis-revisions-{fixture.run_id}.txt"
    marker = "REVISIONE-" + fixture.run_id
    original = document_text(marker + "-ORIGINALE", "30 novembre 2026", "PRIMA")
    upload_headers = {"Content-Type": "text/plain", "X-Filename": filename}
    code, raw = request("POST", base, tokens[0], original, upload_headers)
    require(code == 201, "original_upload_failed")
    old = json.loads(raw)
    old_id = check_document(old, fixture.households[0], filename, original)
    fixture.documents.append(old_id)
    fixture.checkpoint()
    own = base + "/" + old_id
    old_analysis_id = fixture.seed_analysis(0, old_id, old["sha256"])
    code, analysis = call("GET", own + "/analysis/latest", tokens[0])
    require(code == 200 and analysis["id"] == old_analysis_id, "initial_analysis_missing")
    result["initial_analysis_fixture_verified"] = True
    match_headers = {**upload_headers, "If-Match": '"' + old["sha256"] + '"'}
    for supplied, expected in (
        (upload_headers, 428),
        ({**match_headers, "If-Match": '"' + "0" * 64 + '"'}, 412),
    ):
        code, _ = request("POST", own + "/revisions", tokens[0], b"rejected", supplied)
        require(code == expected, "revision_precondition_not_enforced")
    result["revision_preconditions_verified"] = True
    candidates = [
        document_text(marker + "-A", "5 dicembre 2026", "SECONDA A"),
        document_text(marker + "-B", "8 dicembre 2026", "SECONDA B"),
    ]
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(request, "POST", own + "/revisions", tokens[0], value, match_headers)
            for value in candidates
        ]
        responses = [future.result() for future in futures]
    result["concurrent_revision_http_statuses"] = sorted(code for code, _ in responses)
    require(
        result["concurrent_revision_http_statuses"] == [200, 409], "concurrent_successors_invalid"
    )
    winner = next(index for index, (code, _) in enumerate(responses) if code == 200)
    updated = json.loads(responses[winner][1])
    content = candidates[winner]
    new_id = check_document(updated, fixture.households[0], filename, content)
    require(new_id != old_id, "revision_reused_original_identity")
    fixture.documents.append(new_id)
    fixture.checkpoint()
    latest = base + "/" + new_id
    result["concurrent_requests_single_successor_verified"] = True
    code, current = call("GET", own + "/revisions/current", tokens[0])
    require(code == 200 and current == updated, "current_revision_not_resolved")
    code, history = call("GET", latest + "/revisions", tokens[0])
    require(
        code == 200 and {item["id"] for item in history} == {old_id, new_id}, "history_incorrect"
    )
    code, listed = call("GET", base, tokens[0])
    require(
        code == 200 and {item["id"] for item in listed} == {new_id}, "superseded_document_listed"
    )
    for route, expected in ((own, original), (latest, content)):
        code, body = request("GET", route + "/content", tokens[0])
        require(code == 200 and body == expected, "revision_original_mismatch")
        code, _ = request("DELETE", route, tokens[0])
        require(code == 409, "linked_original_deletion_not_blocked")
        code, body = request("GET", route + "/content", tokens[0])
        require(code == 200 and body == expected, "original_not_preserved_after_delete_attempt")
    result["both_originals_and_history_preserved"] = True
    result["linked_original_deletion_blocked"] = True
    result["synthetic_revisions_retained"] = True
    for method, suffix in (("GET", "/analysis/latest"), ("POST", "/analysis")):
        code, _ = request(method, own + suffix, tokens[0])
        require(code == 409, "superseded_analysis_returned_as_current")
    code, _ = request("POST", own + "/revisions", tokens[0], b"stale", match_headers)
    require(code == 409, "superseded_revision_update_not_blocked")
    code, _ = call("GET", latest + "/analysis/latest", tokens[0])
    require(code == 404, "new_revision_reused_old_analysis")
    result["superseded_analysis_invalidated_for_current_use"] = True
    result["new_revision_initially_without_analysis"] = True
    for suffix in ("/revisions/current", "/revisions", "/content", "/analysis/latest"):
        code, _ = request("GET", own + suffix, tokens[1])
        require(code == 404, "foreign_revision_access_not_hidden")
    result["foreign_revision_access_blocked"] = True
    # Exactly one real analysis request on the winning new original. The first
    # version uses a deterministic seeded cache, not a second LLM generation.
    result["new_revision_llm_request_started"] = True
    print("REVISION_ANALYSIS_STARTED (attesa massima 3600 secondi)", flush=True)
    code, analysis = call("POST", latest + "/analysis", tokens[0], timeout=3615)
    result["analysis_http_status"] = code
    require(code == 200 and isinstance(analysis, dict), "new_revision_analysis_failed")
    analysis_id = str(UUID(analysis["id"]))
    require(
        analysis_id != old_analysis_id
        and analysis.get("document_id") == new_id
        and analysis.get("source_sha256") == updated["sha256"],
        "new_analysis_source_mismatch",
    )
    new_marker = marker + ("-A" if winner == 0 else "-B")
    source_date = "5 dicembre 2026" if winner == 0 else "8 dicembre 2026"
    dates = (
        {"2026-12-05", "05/12/2026", "5/12/2026", "05 dicembre 2026", source_date}
        if winner == 0
        else {"2026-12-08", "08/12/2026", "8/12/2026", "08 dicembre 2026", source_date}
    )
    require(
        any(new_marker in item.get("source_text", "") for item in analysis.get("facts", [])),
        "new_marker_source_not_verified",
    )
    deadlines = analysis.get("deadlines", [])
    require(
        any(
            item.get("date", "").strip().lower() in dates
            and source_date in item.get("source_text", "").lower()
            for item in deadlines
        ),
        "new_deadline_source_not_verified",
    )
    require(
        all(
            item.get("date", "").strip().lower()
            not in {"2026-11-30", "30/11/2026", "30 novembre 2026"}
            for item in deadlines
        ),
        "previous_deadline_leaked_into_new_analysis",
    )
    result["new_analysis_hash_marker_and_deadline_verified"] = True
    for method, suffix in (("GET", "/analysis/latest"), ("POST", "/analysis")):
        code, stored = call(method, latest + suffix, tokens[0])
        require(code == 200 and stored == analysis, "new_analysis_persistence_or_cache_mismatch")
    result["new_revision_analysis_persisted_and_cached"] = True
    for token in tokens:
        code, _ = call("POST", "/api/v1/auth/logout", token)
        require(code == 204, "fixture_logout_failed")
        code, _ = call("GET", "/api/v1/me", token)
        require(code == 401, "fixture_session_not_revoked")
    result["logout_and_revocation_verified"] = True


def main():
    result = {
        "ok": False,
        "synthetic_only": True,
        "original_retention_policy": "keep_for_diagnosis",
    }
    fixture = Fixture(Settings.from_environment())
    result["fixture_run_id"] = fixture.run_id
    result["recovery_manifest"] = str(fixture.manifest)
    try:
        require(hasattr(DocumentService, "create_revision"), "revision_runtime_not_ready")
        require(fixture.settings.ai_provider == "openwebui", "local_provider_not_configured")
        with fixture.connect() as connection:
            rows = connection.execute("SELECT version_num FROM alembic_version").fetchall()
        require(rows == [("20261125_0007",)], "revision_schema_not_ready")
        fixture.provision()
        print("REVISION_TEST_STARTED (originali sintetici conservati)", flush=True)
        run(fixture, result)
        result["ok"] = True
    except Failure as error:
        result["error"] = str(error)
    except Exception:
        result["error"] = "revision_smoke_unavailable"
    finally:
        if fixture.provisioned:
            try:
                fixture.deactivate()
                result["test_accounts_disabled"] = True
                result["test_sessions_revoked"] = True
                result["fixture_identity_and_audit_rows_retained"] = True
            except Exception:
                result["ok"] = False
                result["fixture_cleanup_failed"] = True
        fixture.passwords.clear()
    print(json.dumps(result, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
