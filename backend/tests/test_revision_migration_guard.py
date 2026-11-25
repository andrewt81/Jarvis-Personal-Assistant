from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "migration_guard",
    Path(__file__).resolve().parents[2] / "scripts" / "migrate_document_revisions.py",
)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


@pytest.mark.parametrize("already", [False, True])
def test_only_expected_upgrade_or_already_applied_state_is_accepted(already):
    states = iter(
        [(guard.TARGET, True) if already else (guard.BEFORE, False), (guard.TARGET, True)]
    )
    calls = []
    result = guard.migrate(
        lambda: next(states), lambda: calls.append("upgrade"), lambda: calls.append("verify")
    )
    assert result["ok"]
    assert calls == (["verify"] if already else ["upgrade", "verify"])


@pytest.mark.parametrize("state", [("other", False), (guard.BEFORE, True), (guard.TARGET, False)])
def test_unexpected_state_never_runs_migration(state):
    with pytest.raises(guard.MigrationFailure):
        guard.migrate(
            lambda: state,
            lambda: pytest.fail("Unexpected schema mutation"),
            lambda: pytest.fail("Unexpected verification"),
        )


def test_incomplete_upgrade_is_not_reported_as_success():
    with pytest.raises(guard.MigrationFailure, match="revision_not_verified"):
        guard.migrate(
            lambda: (guard.BEFORE, False),
            lambda: None,
            lambda: pytest.fail("Unexpected verification"),
        )
