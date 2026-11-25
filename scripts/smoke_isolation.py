"""Two temporary identities against the real internal pilot; no LLM calls.

Only new random fixture IDs are provisioned. Credentials stay in memory. The
accounts are disabled and sessions revoked even on failure; audit rows remain.
Requires smoke_analysis.py beside this file. Never run the opt-in destructive
PostgreSQL integration test against the application database instead.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
from pathlib import Path
from uuid import UUID, uuid4

from jarvis.core.config import Settings
from smoke_analysis import Failure, call, request, require


class Fixture:
    def __init__(self, settings):
        self.settings = settings
        self.run_id = uuid4().hex
        self.users = [uuid4(), uuid4()]
        self.households = [uuid4(), uuid4()]
        self.people = [uuid4(), uuid4()]
        self.emails = [f"{self.run_id}.{side}@jarvis-isolation.invalid" for side in ("a", "b")]
        self.names = [f"Jarvis isolation {self.run_id} {side}" for side in ("A", "B")]
        self.passwords = [secrets.token_urlsafe(32), secrets.token_urlsafe(32)]
        self.documents = []
        self.provisioned = False
        self.manifest = Path("/tmp") / f"jarvis-isolation-{self.run_id}.json"  # noqa: S108 - random ID, mode 0600

    def locate_run(self, run_id):
        require(UUID(run_id).hex == run_id, "invalid_fixture_run_id")
        emails = [f"{run_id}.{side}@jarvis-isolation.invalid" for side in ("a", "b")]
        names = [f"Jarvis isolation {run_id} {side}" for side in ("A", "B")]
        with self.connect() as connection:
            users = connection.execute(
                "SELECT id,email FROM users WHERE email=ANY(%s)", (emails,)
            ).fetchall()
            mapping = {email: user_id for user_id, email in users}
            require(
                len(users) == 2 and set(mapping) == set(emails), "fixture_recovery_users_missing"
            )
            households = connection.execute(
                "SELECT id,name,created_by_user_id FROM households WHERE name=ANY(%s)", (names,)
            ).fetchall()
            by_name = {name: (household, owner) for household, name, owner in households}
            require(
                len(households) == 2
                and set(by_name) == set(names)
                and all(by_name[names[i]][1] == mapping[emails[i]] for i in range(2)),
                "fixture_recovery_households_changed",
            )
        self.run_id = run_id
        self.users = [mapping[email] for email in emails]
        self.households = [by_name[name][0] for name in names]
        self.emails, self.names = emails, names
        self.provisioned = True

    def checkpoint(self):
        # No password, token, password hash, DB credential or real identity.
        payload = {
            "run_id": self.run_id,
            "users": [str(value) for value in self.users],
            "households": [str(value) for value in self.households],
            "emails": self.emails,
            "names": self.names,
            "documents": self.documents,
            "provisioned": self.provisioned,
        }
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(self.manifest, flags, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream)
            stream.flush()
            os.fsync(stream.fileno())

    def connect(self):
        import psycopg

        s = self.settings
        return psycopg.connect(
            host=s.postgres_host,
            port=s.postgres_port,
            dbname=s.postgres_database,
            user=s.postgres_user,
            password=s.read_postgres_password(),
            sslmode=s.postgres_sslmode,
            connect_timeout=5,
            options="-c statement_timeout=5000 -c lock_timeout=2000",
        )

    def guard(self, connection):
        users = connection.execute(
            "SELECT id, email FROM users WHERE id = ANY(%s) FOR UPDATE", (self.users,)
        ).fetchall()
        households = connection.execute(
            "SELECT id, name, created_by_user_id FROM households WHERE id = ANY(%s) FOR UPDATE",
            (self.households,),
        ).fetchall()
        require(
            set(users) == set(zip(self.users, self.emails, strict=True)), "fixture_users_changed"
        )
        expected = set(zip(self.households, self.names, self.users, strict=True))
        require(set(households) == expected, "fixture_households_changed")

    def provision(self):
        from jarvis.auth.passwords import PasswordManager

        self.checkpoint()
        hashes = [PasswordManager().hash(value) for value in self.passwords]
        with self.connect() as connection:
            identity = connection.execute("SELECT current_database(), current_user").fetchone()
            require(
                identity == (self.settings.postgres_database, self.settings.postgres_user),
                "database_identity_mismatch",
            )
            for index in range(2):
                connection.execute(
                    "INSERT INTO users (id,email,password_hash) VALUES (%s,%s,%s)",
                    (self.users[index], self.emails[index], hashes[index]),
                )
                connection.execute(
                    "INSERT INTO households (id,name,created_by_user_id) VALUES (%s,%s,%s)",
                    (self.households[index], self.names[index], self.users[index]),
                )
                connection.execute(
                    "INSERT INTO household_memberships (household_id,user_id,role) "
                    "VALUES (%s,%s,'owner')",
                    (self.households[index], self.users[index]),
                )
                connection.execute(
                    "INSERT INTO people (id,household_id,display_name,kind,linked_user_id) "
                    "VALUES (%s,%s,%s,'adult',%s)",
                    (
                        self.people[index],
                        self.households[index],
                        self.names[index],
                        self.users[index],
                    ),
                )
        self.provisioned = True
        self.checkpoint()

    def seed_analysis(self, index, document_id, digest):
        analysis_id = uuid4()
        with self.connect() as connection:
            self.guard(connection)
            row = connection.execute(
                "SELECT household_id,created_by_user_id,sha256 FROM documents "
                "WHERE id=%s FOR UPDATE",
                (UUID(document_id),),
            ).fetchone()
            require(
                row is not None
                and row[0] == self.households[index]
                and row[1] == self.users[index]
                and bytes(row[2]).hex() == digest,
                "fixture_document_identity_mismatch",
            )
            # Deliberately synthetic cached result: this tests authorization and
            # cache separation, not AI quality, without another LLM generation.
            connection.execute(
                "INSERT INTO document_analyses "
                "(id,document_id,household_id,source_sha256,provider,model,document_type,"
                "summary,facts,deadlines,suggested_actions,missing_information) "
                "VALUES (%s,%s,%s,%s,'isolation-fixture','no-inference','test',%s,"
                "'[]'::jsonb,'[]'::jsonb,'[]'::jsonb,'[]'::jsonb)",
                (
                    analysis_id,
                    UUID(document_id),
                    self.households[index],
                    bytes.fromhex(digest),
                    f"Synthetic cached fixture {index} {self.run_id}",
                ),
            )
        return str(analysis_id)

    def viewer(self, *, grant):
        with self.connect() as connection:
            self.guard(connection)
            if grant:
                connection.execute(
                    "INSERT INTO household_memberships (household_id,user_id,role) "
                    "VALUES (%s,%s,'viewer')",
                    (self.households[0], self.users[1]),
                )
            else:
                cursor = connection.execute(
                    "DELETE FROM household_memberships "
                    "WHERE household_id=%s AND user_id=%s AND role='viewer'",
                    (self.households[0], self.users[1]),
                )
                require(cursor.rowcount == 1, "fixture_viewer_membership_changed")

    def deactivate(self):
        with self.connect() as connection:
            self.guard(connection)
            cursor = connection.execute(
                "UPDATE users SET is_active=false WHERE id=ANY(%s)", (self.users,)
            )
            require(cursor.rowcount == 2, "fixture_deactivation_count_mismatch")
            connection.execute(
                "UPDATE auth_sessions SET revoked_at=COALESCE(revoked_at,now()) "
                "WHERE user_id=ANY(%s)",
                (self.users,),
            )
            active = connection.execute(
                "SELECT count(*) FROM users WHERE id=ANY(%s) AND is_active", (self.users,)
            ).fetchone()[0]
            sessions = connection.execute(
                "SELECT count(*) FROM auth_sessions WHERE user_id=ANY(%s) AND revoked_at IS NULL",
                (self.users,),
            ).fetchone()[0]
            require(active == 0 and sessions == 0, "fixture_deactivation_not_verified")


def run(fixture, result):
    tokens = []
    routes = []
    analysis_ids = []
    content = f"Jarvis isolation synthetic document. Run {fixture.run_id}.".encode()
    digest = hashlib.sha256(content).hexdigest()
    filename = f"jarvis-isolation-{fixture.run_id}.txt"
    for index in range(2):
        code, pair = call(
            "POST",
            "/api/v1/auth/login",
            payload={"email": fixture.emails[index], "password": fixture.passwords[index]},
        )
        require(code == 200 and isinstance(pair, dict), "fixture_login_failed")
        token = pair.get("access_token")
        require(isinstance(token, str) and bool(token), "fixture_token_invalid")
        tokens.append(token)
        code, me = call("GET", "/api/v1/me", token)
        require(code == 200 and me["id"] == str(fixture.users[index]), "fixture_identity_mismatch")
        base = f"/api/v1/households/{fixture.households[index]}/documents"
        code, raw = request(
            "POST", base, token, content, {"Content-Type": "text/plain", "X-Filename": filename}
        )
        require(code == 201, "fixture_upload_failed")
        document = json.loads(raw)
        document_id = str(UUID(document["id"]))
        require(
            document.get("household_id") == str(fixture.households[index])
            and document.get("original_filename") == filename
            and document.get("sha256") == digest
            and document.get("size_bytes") == len(content)
            and document_id not in fixture.documents,
            "fixture_upload_identity_mismatch",
        )
        fixture.documents.append(document_id)
        fixture.checkpoint()
        routes.append(base + "/" + document_id)
        analysis_ids.append(fixture.seed_analysis(index, document_id, digest))
    result["two_authenticated_identities_verified"] = True
    result["same_content_hash_distinct_documents"] = fixture.documents[0] != fixture.documents[1]
    for index in range(2):
        token = tokens[index]
        own = routes[index]
        code, body = request("GET", own + "/content", token)
        require(code == 200 and body == content, "own_original_mismatch")
        for method, suffix in (("GET", "/analysis/latest"), ("POST", "/analysis")):
            code, analysis = call(method, own + suffix, token)
            require(
                code == 200
                and analysis["id"] == analysis_ids[index]
                and analysis["document_id"] == fixture.documents[index],
                "own_cached_analysis_mismatch",
            )
        foreign = routes[1 - index]
        for method, suffix in (
            ("GET", "/content"),
            ("GET", "/analysis/latest"),
            ("POST", "/analysis"),
            ("DELETE", ""),
        ):
            code, _ = request(method, foreign + suffix, token)
            require(code == 404, "cross_household_access_not_hidden")
    result["bidirectional_cross_household_access_blocked"] = True
    result["identical_hash_cached_analyses_isolated"] = True
    fixture.viewer(grant=True)
    code, body = request("GET", routes[0] + "/content", tokens[1])
    require(code == 200 and body == content, "viewer_original_read_failed")
    code, analysis = call("GET", routes[0] + "/analysis/latest", tokens[1])
    require(code == 200 and analysis["id"] == analysis_ids[0], "viewer_analysis_read_failed")
    for method, suffix in (("POST", "/analysis"), ("DELETE", "")):
        code, _ = call(method, routes[0] + suffix, tokens[1])
        require(code == 403, "viewer_write_not_blocked")
    result["viewer_read_allowed_and_write_blocked"] = True
    fixture.viewer(grant=False)
    for suffix in ("/content", "/analysis/latest"):
        code, _ = request("GET", routes[0] + suffix, tokens[1])
        require(code == 404, "revoked_membership_still_accepted")
    result["membership_revocation_effective_on_existing_session"] = True
    code, me = call("GET", "/api/v1/me", tokens[1])
    require(code == 200 and me["id"] == str(fixture.users[1]), "revocation_invalidated_identity")
    result["revoked_membership_session_still_authenticated"] = True
    for index in range(2):
        code, body = request("GET", routes[index] + "/content", tokens[index])
        require(code == 200 and body == content, "cleanup_original_identity_mismatch")
        code, _ = call("DELETE", routes[index], tokens[index])
        require(code == 204, "fixture_document_cleanup_failed")
        code, _ = request("GET", routes[index] + "/content", tokens[index])
        require(code == 404, "fixture_document_still_visible")
        code, _ = call("POST", "/api/v1/auth/logout", tokens[index])
        require(code == 204, "fixture_logout_failed")
        code, _ = call("GET", "/api/v1/me", tokens[index])
        require(code == 401, "fixture_session_not_revoked")
    result["synthetic_documents_removed_from_app"] = True
    result["logout_and_revocation_verified"] = True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--deactivate-run", help="Disable only identities from a known fixture run")
    arguments = parser.parse_args()
    result = {"ok": False, "synthetic_only": True, "llm_generation_requested": False}
    fixture = Fixture(Settings.from_environment())
    result["fixture_run_id"] = fixture.run_id
    result["recovery_manifest"] = str(fixture.manifest)
    try:
        if arguments.deactivate_run:
            fixture.locate_run(arguments.deactivate_run)
            result["fixture_run_id"] = fixture.run_id
            result.pop("recovery_manifest", None)
            result["recovery_only"] = True
        else:
            fixture.provision()
            print("ISOLATION_TEST_STARTED (due identita sintetiche)", flush=True)
            run(fixture, result)
        result["ok"] = True
    except Failure as error:
        result["error"] = str(error)
    except Exception:
        result["error"] = "isolation_test_unavailable"
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
