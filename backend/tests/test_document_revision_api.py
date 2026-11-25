from __future__ import annotations

import importlib.util
from dataclasses import replace
from io import StringIO
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from jarvis.api.auth import current_user
from jarvis.api.documents import router
from jarvis.auth.models import AuthenticatedUser
from test_document_revisions import case as shared_case
from test_document_revisions import complete

case = shared_case


@pytest.fixture
def client(case):
    application = FastAPI()
    application.state.document_service = case[2]
    application.include_router(router)
    application.dependency_overrides[current_user] = lambda: AuthenticatedUser(
        case[0], "synthetic@example.invalid"
    )
    with TestClient(application) as value:
        yield value


def route(case):
    return f"/api/v1/households/{case[1]}/documents/{case[3].id}"


def headers(case):
    return {
        "Content-Type": "text/plain",
        "X-Filename": "lettera.txt",
        "If-Match": '"' + case[3].sha256.hex() + '"',
    }


def test_revision_http_preconditions_do_not_mutate_original(client, case):
    url = route(case) + "/revisions"
    for etag, status in ((None, 428), ("*", 422), ('"' + "0" * 64 + '"', 412)):
        supplied = headers(case)
        if etag is None:
            supplied.pop("If-Match")
        else:
            supplied["If-Match"] = etag
        assert client.post(url, content=b"new version", headers=supplied).status_code == status
    assert len(case[4].values) == len(case[5].values) == 1


def test_current_history_original_hash_and_stale_analysis_http_contract(client, case):
    original = case[3]
    complete(case[2].analyze(case[0], case[1], original.id))
    url = route(case)
    response = client.post(url + "/revisions", content=b"version two", headers=headers(case))
    assert response.status_code == 200
    updated = response.json()
    assert updated["id"] != str(original.id)
    assert response.headers["etag"] == '"' + updated["sha256"] + '"'
    assert client.get(url + "/revisions/current").json() == updated
    history = client.get(url + "/revisions").json()
    assert {item["id"] for item in history} == {str(original.id), updated["id"]}
    assert client.get(url.rsplit("/", 1)[0]).json() == [updated]
    saved = client.get(url + "/content")
    assert saved.content == b"version one"
    assert saved.headers["etag"] == '"' + original.sha256.hex() + '"'
    assert client.get(url + "/analysis/latest").status_code == 409
    assert client.post(url + "/analysis").status_code == 409
    new_url = url.rsplit("/", 1)[0] + "/" + updated["id"]
    assert client.get(new_url + "/analysis/latest").status_code == 404
    analysis = client.post(new_url + "/analysis")
    assert analysis.status_code == 200
    assert analysis.json()["source_sha256"] == updated["sha256"]
    assert analysis.json()["document_id"] == updated["id"]
    assert client.delete(url).status_code == client.delete(new_url).status_code == 409
    assert len(case[5].values) == 2


def test_viewer_and_other_identity_cannot_write_or_discover_revision_history(client, case):
    membership = case[2]._households.membership
    case[2]._households.membership = replace(membership, role="viewer")
    url = route(case)
    assert client.get(url + "/revisions/current").status_code == 200
    assert client.get(url + "/revisions").status_code == 200
    assert client.post(url + "/revisions", content=b"new", headers=headers(case)).status_code == 403
    client.app.dependency_overrides[current_user] = lambda: AuthenticatedUser(
        uuid4(), "other@example.invalid"
    )
    assert client.get(url + "/revisions/current").status_code == 404
    assert client.get(url + "/revisions").status_code == 404
    assert client.post(url + "/revisions", content=b"new", headers=headers(case)).status_code == 404
    assert len(case[4].values) == len(case[5].values) == 1


def test_stream_limit_is_enforced_even_with_false_content_length(client, case, monkeypatch):
    monkeypatch.setattr("jarvis.api.documents.MAX_DOCUMENT_BYTES", 3)
    supplied = {**headers(case), "Content-Length": "1"}
    response = client.post(route(case) + "/revisions", content=b"too long", headers=supplied)
    assert response.status_code == 413
    assert len(case[4].values) == len(case[5].values) == 1


def test_additive_migration_emits_postgresql_constraints_without_connecting():
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    migration_file = (
        Path(__file__).resolve().parents[1]
        / "migrations"
        / "versions"
        / "20261125_0007_document_revisions.py"
    )
    spec = importlib.util.spec_from_file_location("revision_migration", migration_file)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    output = StringIO()
    context = MigrationContext.configure(
        dialect_name="postgresql", opts={"as_sql": True, "output_buffer": output}
    )
    migration.op = Operations(context)
    migration.upgrade()
    sql = output.getvalue()
    assert "CREATE TABLE document_revisions" in sql
    assert "uq_documents_id_household" in sql
    assert sql.count("ON DELETE RESTRICT") == 2
    assert "DROP TABLE" not in sql and "UPDATE documents" not in sql
