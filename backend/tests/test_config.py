from pathlib import Path

import pytest
from jarvis.core.config import Settings


def test_configuration_accepts_existing_infrastructure_aliases(tmp_path: Path) -> None:
    secret = tmp_path / "postgres-password"
    secret.write_text("safe-test-password\n", encoding="utf-8")
    settings = Settings.from_environment(
        {
            "JARVIS_ENVIRONMENT": "test",
            "PGHOST": "10.10.30.20",
            "PGPORT": "5432",
            "PGDATABASE": "jarvis",
            "PGUSER": "jarvis_app",
            "PGSSLMODE": "require",
            "PGPASSWORD_FILE": str(secret),
            "RUSTFS_ENDPOINT": "http://10.10.30.20:9000",
            "RUSTFS_BUCKET": "jarvis-documents-prod",
            "RUSTFS_ACCESS_KEY": "test-access",
            "RUSTFS_SECRET_KEY": "test-secret",
            "RUSTFS_PATH_STYLE": "true",
        }
    )
    assert settings.postgres_host == "10.10.30.20"
    assert settings.postgres_password_file == secret
    assert settings.read_postgres_password() == "safe-test-password"
    assert settings.s3_path_style is True
    assert settings.s3_bucket == "jarvis-documents-prod"


def test_settings_repr_does_not_read_postgres_secret(tmp_path: Path) -> None:
    missing_secret = tmp_path / "missing"
    settings = Settings.from_environment(
        {
            "PGPASSWORD_FILE": str(missing_secret),
            "S3_ACCESS_KEY_ID": "sensitive-access-key",
            "S3_SECRET_ACCESS_KEY": "sensitive-secret-key",
        }
    )
    rendered = repr(settings)
    assert "sensitive-access-key" not in rendered
    assert "sensitive-secret-key" not in rendered


def test_openwebui_configuration_is_separate_from_cloud_settings(tmp_path: Path) -> None:
    settings = Settings.from_environment(
        {
            "JARVIS_AI_PROVIDER": "openwebui",
            "JARVIS_OPENWEBUI_BASE_URL": "http://100.127.56.71:3000/",
            "JARVIS_OPENWEBUI_MODEL": "jarvis",
            "JARVIS_OPENWEBUI_TIMEOUT_SECONDS": "1800",
            "JARVIS_OPENWEBUI_API_KEY_FILE": str(tmp_path / "local-key"),
        }
    )
    assert settings.ai_provider == "openwebui"
    assert settings.openwebui_base_url == "http://100.127.56.71:3000"
    assert settings.openwebui_model == "jarvis"
    assert settings.openwebui_timeout_seconds == 1800
    assert settings.openwebui_api_key_file == tmp_path / "local-key"
    assert settings.ai_api_key_file != settings.openwebui_api_key_file
    assert Settings.from_environment({}).ai_provider == "disabled"


def test_configuration_reads_jarvis_host_template_without_renaming_secrets(tmp_path: Path):
    secret = tmp_path / "existing-db-password"
    secret.write_text("synthetic-db-password\n", encoding="utf-8")
    settings = Settings.from_environment(
        {
            "JARVIS_DB_HOST": "database-app.invalid",
            "JARVIS_DB_PORT": "6543",
            "JARVIS_DB_NAME": "application_db",
            "JARVIS_DB_USER": "application_user",
            "JARVIS_DB_SSLMODE": "verify-full",
            "JARVIS_DB_PASSWORD_FILE": str(secret),
            "JARVIS_S3_ENDPOINT": "https://objects-app.invalid",
            "JARVIS_S3_BUCKET": "application-documents",
            "JARVIS_S3_REGION": "eu-test-1",
            "JARVIS_S3_PATH_STYLE": "false",
            "JARVIS_S3_ACCESS_KEY": "synthetic-access-key",
            "JARVIS_S3_SECRET_KEY": "synthetic-secret-key",
        }
    )
    assert settings.postgres_configured and settings.s3_configured
    assert settings.postgres_host == "database-app.invalid"
    assert settings.postgres_port == 6543
    assert settings.postgres_database == "application_db"
    assert settings.postgres_user == "application_user"
    assert settings.postgres_sslmode == "verify-full"
    assert settings.postgres_password_file == secret
    assert settings.read_postgres_password() == "synthetic-db-password"
    assert settings.s3_endpoint_url == "https://objects-app.invalid"
    assert settings.s3_bucket == "application-documents"
    assert settings.s3_region == "eu-test-1"
    assert settings.s3_path_style is False
    assert settings.s3_access_key_id == "synthetic-access-key"
    assert settings.s3_secret_access_key == "synthetic-secret-key"  # noqa: S105 - test fixture
    assert "synthetic-access-key" not in repr(settings)
    assert "synthetic-secret-key" not in repr(settings)
    assert "synthetic-db-password" not in repr(settings)


@pytest.mark.parametrize(
    "primary, alias, attribute, first, second, expected_first, expected_second",
    [
        ("JARVIS_POSTGRES_HOST", "JARVIS_DB_HOST", "postgres_host", "new", "old", "new", "old"),
        ("JARVIS_POSTGRES_PORT", "JARVIS_DB_PORT", "postgres_port", "5432", "6543", 5432, 6543),
        (
            "JARVIS_POSTGRES_DATABASE",
            "JARVIS_DB_NAME",
            "postgres_database",
            "new",
            "old",
            "new",
            "old",
        ),
        ("JARVIS_POSTGRES_USER", "JARVIS_DB_USER", "postgres_user", "new", "old", "new", "old"),
        (
            "JARVIS_POSTGRES_SSLMODE",
            "JARVIS_DB_SSLMODE",
            "postgres_sslmode",
            "verify-full",
            "require",
            "verify-full",
            "require",
        ),
        (
            "JARVIS_POSTGRES_PASSWORD_FILE",
            "JARVIS_DB_PASSWORD_FILE",
            "postgres_password_file",
            "/new",
            "/old",
            Path("/new"),
            Path("/old"),
        ),
        (
            "JARVIS_S3_ENDPOINT_URL",
            "JARVIS_S3_ENDPOINT",
            "s3_endpoint_url",
            "new",
            "old",
            "new",
            "old",
        ),
        (
            "JARVIS_S3_ACCESS_KEY_ID",
            "JARVIS_S3_ACCESS_KEY",
            "s3_access_key_id",
            "new-key",
            "old-key",
            "new-key",
            "old-key",
        ),
        (
            "JARVIS_S3_SECRET_ACCESS_KEY",
            "JARVIS_S3_SECRET_KEY",
            "s3_secret_access_key",
            "new-secret",
            "old-secret",
            "new-secret",
            "old-secret",
        ),
    ],
)
def test_jarvis_template_aliases_preserve_explicit_override_and_blank_fallback(
    primary, alias, attribute, first, second, expected_first, expected_second
):
    settings = Settings.from_environment({primary: first, alias: second})
    assert getattr(settings, attribute) == expected_first
    fallback = Settings.from_environment({primary: "  ", alias: second})
    assert getattr(fallback, attribute) == expected_second


def test_openwebui_version_pin_is_explicit_and_optional():
    assert Settings.from_environment({}).openwebui_profile_version_id == ""
    configured = Settings.from_environment({"JARVIS_OPENWEBUI_PROFILE_VERSION_ID": " verified "})
    assert configured.openwebui_profile_version_id == "verified"
