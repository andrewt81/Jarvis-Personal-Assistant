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
