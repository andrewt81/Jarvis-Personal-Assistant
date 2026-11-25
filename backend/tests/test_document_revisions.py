from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

import pytest
from jarvis.documents.analysis import AnalysisResult
from jarvis.documents.service import (
    DocumentIntegrityError,
    DocumentNotFoundError,
    DocumentPreconditionFailed,
    DocumentRevisionConflict,
    DocumentRevisionUnavailable,
    DocumentService,
)
from jarvis.households.service import HouseholdNotFoundError, HouseholdPermissionError
from test_documents import Analyses, Documents, Households, Storage


def complete(coroutine):
    # These in-memory fakes complete every await immediately; no network/event
    # loop is needed, including in the restricted Windows development sandbox.
    try:
        coroutine.send(None)
    except StopIteration as finished:
        return finished.value
    finally:
        coroutine.close()
    raise AssertionError("Unexpected asynchronous dependency")


class Analyzer:
    def __init__(self):
        self.calls = 0
        self.hook = None

    async def analyze(self, *, filename, media_type, content):
        self.calls += 1
        if self.hook:
            await self.hook()
        return AnalysisResult(
            provider="test",
            model="fixture",
            document_type="test",
            summary=content.decode(),
            facts=(),
            deadlines=(),
            suggested_actions=(),
            missing_information=(),
        )


@pytest.fixture
def case():
    user, household = uuid4(), uuid4()
    repository, storage, analyses, analyzer = Documents(), Storage(), Analyses(), Analyzer()
    service = DocumentService(repository, Households(user, household), storage, analyses, analyzer)
    original = complete(
        service.upload(
            user, household, filename="lettera.txt", media_type="text/plain", content=b"version one"
        )
    )
    return user, household, service, original, repository, storage, analyses, analyzer


def revise(case, *, content=b"version two", expected=None, document=None):
    user, household, service, original, *_ = case
    original = document or original
    return complete(
        service.create_revision(
            user,
            household,
            original.id,
            expected_sha256=original.sha256 if expected is None else expected,
            filename="lettera.txt",
            media_type="text/plain",
            content=content,
        )
    )


def test_new_revision_preserves_original_and_requires_fresh_analysis(case):
    user, household, service, original, repository, storage, analyses, analyzer = case
    old_analysis = complete(service.analyze(user, household, original.id))
    updated = revise(case)
    assert updated.id != original.id and updated.object_key != original.object_key
    assert updated.sha256 != original.sha256
    assert complete(service.download(user, household, original.id))[1] == b"version one"
    assert complete(service.download(user, household, updated.id))[1] == b"version two"
    assert complete(service.current_revision(user, household, original.id)) == updated
    assert complete(service.revisions(user, household, updated.id)) == [original, updated]
    assert complete(service.list(user, household)) == [updated]
    for operation in (service.analyze, service.latest_analysis):
        with pytest.raises(DocumentRevisionConflict):
            complete(operation(user, household, original.id))
    with pytest.raises(DocumentNotFoundError):
        complete(service.latest_analysis(user, household, updated.id))
    new_analysis = complete(service.analyze(user, household, updated.id))
    assert new_analysis.source_sha256 == updated.sha256
    assert new_analysis.id != old_analysis.id
    assert complete(service.analyze(user, household, updated.id)) == new_analysis
    assert analyzer.calls == 2 and len(analyses.values) == 2


def test_precondition_and_superseded_source_fail_before_storage_write(case):
    *_, storage, _, _ = case
    before = dict(storage.values)
    with pytest.raises(DocumentPreconditionFailed):
        revise(case, expected=bytes(32))
    assert storage.values == before
    revise(case)
    before = dict(storage.values)
    with pytest.raises(DocumentRevisionConflict):
        revise(case, content=b"another parallel revision")
    assert storage.values == before


def test_identical_content_and_metadata_is_idempotent(case):
    updated = revise(case, content=b"version one")
    assert updated == case[3]
    assert len(case[4].values) == len(case[5].values) == 1


def test_confirmed_lost_race_removes_only_candidate_object(case, monkeypatch):
    async def lost(*_):
        return None

    monkeypatch.setattr(case[4], "create_revision", lost)
    before = dict(case[5].values)
    with pytest.raises(DocumentRevisionConflict):
        revise(case)
    assert case[5].values == before and len(case[4].values) == 1


def test_ambiguous_commit_never_deletes_a_potentially_committed_original(case, monkeypatch):
    create = case[4].create_revision

    async def committed_then_failed(previous, document):
        await create(previous, document)
        raise ConnectionError("private driver failure")

    monkeypatch.setattr(case[4], "create_revision", committed_then_failed)
    with pytest.raises(DocumentRevisionUnavailable):
        revise(case)
    current = complete(case[2].current_revision(case[0], case[1], case[3].id))
    assert current.id != case[3].id
    assert case[5].values[current.object_key] == b"version two"
    assert case[5].values[case[3].object_key] == b"version one"


def test_revision_while_model_runs_cannot_be_returned_as_current(case):
    async def update():
        await case[2].create_revision(
            case[0],
            case[1],
            case[3].id,
            expected_sha256=case[3].sha256,
            filename="lettera.txt",
            media_type="text/plain",
            content=b"version two",
        )

    case[7].hook = update
    with pytest.raises(DocumentRevisionConflict):
        complete(case[2].analyze(case[0], case[1], case[3].id))
    assert case[6].values == []


def test_cached_analysis_race_is_checked_again_before_return(case, monkeypatch):
    complete(case[2].analyze(case[0], case[1], case[3].id))
    latest = case[6].latest

    async def racing_latest(*args):
        value = await latest(*args)
        await case[2].create_revision(
            case[0],
            case[1],
            case[3].id,
            expected_sha256=case[3].sha256,
            filename="lettera.txt",
            media_type="text/plain",
            content=b"version two",
        )
        return value

    monkeypatch.setattr(case[6], "latest", racing_latest)
    with pytest.raises(DocumentRevisionConflict):
        complete(case[2].analyze(case[0], case[1], case[3].id))


def test_stale_source_hash_is_not_returned_by_latest(case):
    analysis = complete(case[2].analyze(case[0], case[1], case[3].id))
    case[6].values[-1] = replace(analysis, source_sha256=bytes(32))
    with pytest.raises(DocumentNotFoundError):
        complete(case[2].latest_analysis(case[0], case[1], case[3].id))


@pytest.mark.parametrize("historical", [True, False])
def test_delete_never_removes_an_original_in_a_revision_chain(case, historical):
    updated = revise(case)
    before = dict(case[5].values)
    with pytest.raises(DocumentRevisionConflict):
        complete(case[2].delete(case[0], case[1], case[3].id if historical else updated.id))
    assert case[5].values == before and len(case[4].values) == 2


def test_foreign_household_and_viewer_cannot_create_revision(case):
    user, household, _, original, repo, store, analyses, analyzer = case
    viewer = DocumentService(repo, Households(user, household, "viewer"), store, analyses, analyzer)
    with pytest.raises(HouseholdPermissionError):
        complete(
            viewer.create_revision(
                user,
                household,
                original.id,
                expected_sha256=original.sha256,
                filename="lettera.txt",
                media_type="text/plain",
                content=b"forbidden",
            )
        )
    with pytest.raises(HouseholdNotFoundError):
        complete(case[2].current_revision(uuid4(), household, original.id))
    assert len(repo.values) == len(store.values) == 1


def test_corrupted_original_is_detected_before_download_or_inference(case):
    case[5].values[case[3].object_key] = b"tampered"
    for method in (case[2].download, case[2].analyze):
        with pytest.raises(DocumentIntegrityError):
            complete(method(case[0], case[1], case[3].id))
    assert case[7].calls == 0
