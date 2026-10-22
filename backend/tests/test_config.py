from pathlib import Path

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
