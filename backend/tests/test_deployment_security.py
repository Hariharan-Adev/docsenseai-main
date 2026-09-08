"""Deployment security regression tests for production hardening controls."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from starlette.requests import Request
from starlette.responses import Response

from app.config import Settings, _load_ini_environment
from app.main import apply_security_headers
from app.routes import health
from db import database


def production_settings(**overrides) -> Settings:
    """Build a minimal production-safe settings object for validation tests."""
    values = {
        "app_environment": "production",
        "jwt_secret_key": "j" * 32,
        "rate_limit_salt": "r" * 32,
        "cors_allow_origins": "https://app.example.com",
        "trusted_hosts": "api.example.com",
        "frontend_base_url": "https://app.example.com",
        "api_base_url": "https://api.example.com",
        "metrics_token": "m" * 32,
        "llm_provider": "azure_openai",
        "azure_openai_endpoint": "https://azure.example.com",
        "azure_openai_api_key": "a" * 32,
        "azure_openai_rag_deployment": "rag-prod",
        "azure_openai_utility_deployment": "utility-prod",
        "qdrant_mode": "remote",
        "qdrant_url": "https://qdrant.example.com",
    }
    values.update(overrides)
    return Settings(**values)


def request_for(scheme: str, forwarded_proto: str = "") -> Request:
    """Create a tiny ASGI request for direct middleware helper tests."""
    headers = []
    if forwarded_proto:
        headers.append((b"x-forwarded-proto", forwarded_proto.encode("ascii")))
    return Request({
        "type": "http",
        "method": "GET",
        "path": "/health",
        "scheme": scheme,
        "headers": headers,
        "client": ("127.0.0.1", 12345),
    })


class DeploymentSecurityTests(unittest.TestCase):
    def test_ini_configuration_loads_before_settings_without_overriding_env(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            ini_path = Path(temporary) / "config.ini"
            ini_path.write_text(
                "[app]\n"
                "APP_ENVIRONMENT=production\n"
                "API_BASE_URL=https://api-from-ini.example.com\n"
                "CORS_ALLOW_ORIGINS=https://app-from-ini.example.com\n",
                encoding="utf-8",
            )

            keys = ("APP_CONFIG_INI", "APP_ENVIRONMENT", "API_BASE_URL", "CORS_ALLOW_ORIGINS")
            old_values = {key: os.environ.get(key) for key in keys}
            try:
                for key in keys:
                    os.environ.pop(key, None)
                os.environ["APP_CONFIG_INI"] = str(ini_path)
                os.environ["API_BASE_URL"] = "https://api-from-env.example.com"

                _load_ini_environment()

                self.assertEqual(os.environ["APP_ENVIRONMENT"], "production")
                self.assertEqual(os.environ["CORS_ALLOW_ORIGINS"], "https://app-from-ini.example.com")
                self.assertEqual(os.environ["API_BASE_URL"], "https://api-from-env.example.com")
            finally:
                for key in keys:
                    if old_values[key] is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = old_values[key]

    def test_production_settings_accept_explicit_https_controls(self) -> None:
        production_settings().validate_production_settings()

    def test_production_settings_reject_wildcard_or_http_cors(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "wildcards"):
            production_settings(cors_allow_origins="https://app.example.com,*").validate_production_settings()
        with self.assertRaisesRegex(RuntimeError, "HTTPS"):
            production_settings(cors_allow_origins="http://app.example.com").validate_production_settings()

    def test_production_settings_reject_wildcard_hosts_and_weak_secrets(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "TRUSTED_HOSTS"):
            production_settings(trusted_hosts="*").validate_production_settings()
        with self.assertRaisesRegex(RuntimeError, "JWT_SECRET_KEY"):
            production_settings(jwt_secret_key="change-me-locally").validate_production_settings()
        with self.assertRaisesRegex(RuntimeError, "RATE_LIMIT_SALT"):
            production_settings(rate_limit_salt="change-me-locally").validate_production_settings()
        with self.assertRaisesRegex(RuntimeError, "AZURE_OPENAI_API_KEY"):
            production_settings(azure_openai_api_key="PASTE_KEY_1_HERE").validate_production_settings()
        with self.assertRaisesRegex(RuntimeError, "RAG_DIAGNOSTICS_ENABLED"):
            production_settings(rag_diagnostics_enabled=True).validate_production_settings()

    def test_production_settings_reject_insecure_frontend_api_and_qdrant_urls(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "FRONTEND_BASE_URL"):
            production_settings(frontend_base_url="http://app.example.com").validate_production_settings()
        with self.assertRaisesRegex(RuntimeError, "API_BASE_URL"):
            production_settings(api_base_url="http://api.example.com").validate_production_settings()
        with self.assertRaisesRegex(RuntimeError, "QDRANT_MODE"):
            production_settings(qdrant_mode="local").validate_production_settings()

    def test_security_headers_are_applied_with_hsts_only_for_production_https(self) -> None:
        response = Response()
        with patch.object(health.settings, "app_environment", "production"):
            apply_security_headers(response, request_for("http", "https"))

        self.assertEqual(response.headers["Content-Security-Policy"].split(";", 1)[0], "default-src 'self'")
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response.headers["X-Frame-Options"], "DENY")
        self.assertEqual(response.headers["Referrer-Policy"], "no-referrer")
        self.assertIn("max-age=31536000", response.headers["Strict-Transport-Security"])

        http_response = Response()
        with patch.object(health.settings, "app_environment", "production"):
            apply_security_headers(http_response, request_for("http"))
        self.assertNotIn("Strict-Transport-Security", http_response.headers)

    def test_metrics_requires_token_or_private_client(self) -> None:
        with (
            patch.object(health.settings, "metrics_token", "m" * 32),
            patch.object(health.settings, "metrics_allow_private_networks", False),
        ):
            self.assertTrue(
                health.metrics_access_allowed(
                    "203.0.113.5",
                    {"authorization": f"Bearer {'m' * 32}"},
                )
            )
            self.assertFalse(health.metrics_access_allowed("203.0.113.5", {}))

        with (
            patch.object(health.settings, "metrics_token", ""),
            patch.object(health.settings, "metrics_allow_private_networks", True),
        ):
            self.assertTrue(health.metrics_access_allowed("10.1.2.3", {}))
            self.assertFalse(health.metrics_access_allowed("203.0.113.5", {}))

    def test_metrics_output_omits_raw_organization_identifiers(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            db_path = Path(temporary) / "metrics.db"
            with patch.object(database, "DATABASE_PATH", db_path):
                database.initialize_database()
                with database.get_connection() as connection:
                    connection.execute(
                        "INSERT INTO users (id, email, password_hash) VALUES (?, ?, ?)",
                        (1, "metrics@example.com", "hash"),
                    )
                    connection.executemany(
                        "INSERT INTO organizations (id, name) VALUES (?, ?)",
                        [
                            ("org-secret-a", "Org A"),
                            ("org-secret-b", "Org B"),
                            ("org-secret-c", "Org C"),
                        ],
                    )
                    connection.execute(
                        """INSERT INTO document_contents
                           (id, organization_id, owner_id, file_hash,
                            normalized_content_hash, extracted_text, processing_status)
                           VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (1, "org-secret-a", 1, "h1", "nh1", "metric document", "completed"),
                    )
                    connection.execute(
                        """INSERT INTO documents
                           (organization_id, owner_id, original_filename, display_filename,
                            stored_filename, file_hash, content_id, collection_id)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                        ("org-secret-a", 1, "a.txt", "a.txt", "a.txt", "h1", 1, None),
                    )
                    connection.execute(
                        """INSERT INTO ingestion_jobs
                           (id, organization_id, owner_id, document_id, version_id,
                            idempotency_key, status, attempt_count, max_attempts,
                            chunks_created, vector_upsert_failures, extraction_duration_ms,
                            embedding_duration_ms, indexing_duration_ms)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            "job-a",
                            "org-secret-b",
                            1,
                            None,
                            None,
                            "metrics-job-a",
                            "failed",
                            3,
                            3,
                            7,
                            1,
                            10.0,
                            20.0,
                            30.0,
                        ),
                    )
                    connection.execute(
                        """INSERT INTO audit_events
                           (organization_id, user_id, event_type, endpoint, outcome)
                           VALUES (?, ?, ?, ?, ?)""",
                        ("org-secret-c", 1, "document.delete", "/documents/1", "success"),
                    )

                output = health.build_metrics_output()

        self.assertIn('rag_ingestion_jobs{status="failed"} 1', output)
        self.assertIn('rag_document_lifecycle_total{event="document.delete"} 1', output)
        self.assertNotIn("org-secret-a", output)
        self.assertNotIn("org-secret-b", output)
        self.assertNotIn("org-secret-c", output)
        self.assertNotIn("organization_id", output)

    def test_frontend_error_boundary_hides_raw_errors_in_production(self) -> None:
        source_path = Path(__file__).resolve().parents[2] / "frontend" / "src" / "components" / "ui" / "ErrorBoundary.tsx"
        source = source_path.read_text(encoding="utf-8")

        self.assertIn("if (import.meta.env.DEV)", source)
        self.assertIn("console.error('Application render failed', error, info)", source)
        self.assertIn("console.error('Application render failed')", source)
        self.assertIn("const detail = import.meta.env.DEV", source)
        self.assertIn("An unexpected error occurred. Please reload the dashboard.", source)
        self.assertNotIn("{this.state.error.message}</p>", source)


if __name__ == "__main__":
    unittest.main()
