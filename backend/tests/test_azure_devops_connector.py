"""Azure DevOps connector validation regression tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from app.auth import get_current_user
from app.main import app
from app.services import azure_devops
from app.services.azure_devops import (
    AzureDevOpsConnectionError,
    AzureDevOpsProject,
    AzureDevOpsValidationResult,
    normalize_organization_url,
    validate_connection,
)
from db import database


class AzureDevOpsServiceTests(unittest.TestCase):
    """Verify Azure DevOps credential checks before the UI can mark connected."""

    def test_normalize_organization_url_rejects_project_or_portal_urls(self) -> None:
        """Only the exact organization URL shape is accepted."""
        valid_url, organization = normalize_organization_url("https://dev.azure.com/Laserbeamch/")
        self.assertEqual(valid_url, "https://dev.azure.com/Laserbeamch")
        self.assertEqual(organization, "Laserbeamch")

        for value in (
            "https://dev.azure.com/Laserbeamch/ProjectA",
            "https://portal.azure.com/#view/project",
            "https://Laserbeamch.visualstudio.com",
        ):
            with self.subTest(value=value):
                with self.assertRaises(AzureDevOpsConnectionError) as failure:
                    normalize_organization_url(value)
                self.assertEqual(failure.exception.code, "invalid_organization_url")

    def test_validate_connection_fetches_projects_before_marking_connected(self) -> None:
        """A connection is successful only after Azure DevOps returns projects."""
        calls: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            """Return Azure-like responses for the required validation calls."""
            calls.append(request.url.path)
            if request.url.path == "/Laserbeamch/_apis/projects":
                self.assertEqual(request.url.params["api-version"], "7.2")
                return httpx.Response(
                    200,
                    json={"value": [{"id": "project-1", "name": "Knowledge Base"}]},
                )
            return httpx.Response(404, json={})

        transport = httpx.MockTransport(handler)
        real_client = httpx.Client

        def client_factory(*args, **kwargs):
            """Inject a mock transport while preserving httpx.Client behavior."""
            return real_client(transport=transport)

        with patch.object(azure_devops.httpx, "Client", side_effect=client_factory):
            result = validate_connection("https://dev.azure.com/Laserbeamch", "pat-value")

        self.assertEqual(result.organization_url, "https://dev.azure.com/Laserbeamch")
        self.assertEqual(result.projects[0].name, "Knowledge Base")
        self.assertIn("projects_api_access", result.checks)
        self.assertEqual(
            calls,
            ["/Laserbeamch/_apis/projects"],
        )

    def test_validate_connection_maps_azure_auth_and_access_failures(self) -> None:
        """Azure status codes are returned as actionable user-facing categories."""
        expected = {
            401: "pat_authentication_failed",
            403: "insufficient_permissions",
            404: "organization_not_found",
        }

        for status_code, code in expected.items():
            with self.subTest(status_code=status_code):
                transport = httpx.MockTransport(
                    lambda request: httpx.Response(status_code, json={})
                )
                real_client = httpx.Client

                def client_factory(*args, **kwargs):
                    """Inject the status-specific mock response."""
                    return real_client(transport=transport)

                with patch.object(azure_devops.httpx, "Client", side_effect=client_factory):
                    with self.assertRaises(AzureDevOpsConnectionError) as failure:
                        validate_connection("https://dev.azure.com/Laserbeamch", "pat-value")
                self.assertEqual(failure.exception.code, code)

    def test_validate_connection_rejects_empty_project_access(self) -> None:
        """A 200 project response with no projects is not a connected state."""
        transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"value": []}))
        real_client = httpx.Client

        def client_factory(*args, **kwargs):
            """Return a client backed by the empty project response."""
            return real_client(transport=transport)

        with patch.object(azure_devops.httpx, "Client", side_effect=client_factory):
            with self.assertRaises(AzureDevOpsConnectionError) as failure:
                validate_connection("https://dev.azure.com/Laserbeamch", "pat-value")

        self.assertEqual(failure.exception.code, "no_accessible_projects")

    def test_validate_connection_maps_bad_project_validation_request(self) -> None:
        """Bad project-list validation requests are categorized instead of generic."""
        transport = httpx.MockTransport(lambda request: httpx.Response(400, json={}))
        real_client = httpx.Client

        def client_factory(*args, **kwargs):
            """Return a client backed by the bad request response."""
            return real_client(transport=transport)

        with patch.object(azure_devops.httpx, "Client", side_effect=client_factory):
            with self.assertRaises(AzureDevOpsConnectionError) as failure:
                validate_connection("https://dev.azure.com/Laserbeamch", "pat-value")

        self.assertEqual(failure.exception.status_code, 400)
        self.assertEqual(failure.exception.code, "projects_request_failed")

    def test_validate_connection_falls_back_to_previous_projects_api_version(self) -> None:
        """A 7.2 bad request retries 7.1 before failing the connection."""
        versions: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            """Reject 7.2 and accept the 7.1 projects fallback."""
            versions.append(str(request.url.params["api-version"]))
            if request.url.params["api-version"] == "7.2":
                return httpx.Response(400, json={"message": "Unsupported api-version"})
            return httpx.Response(
                200,
                json={"value": [{"id": "project-1", "name": "Knowledge Base"}]},
            )

        transport = httpx.MockTransport(handler)
        real_client = httpx.Client

        def client_factory(*args, **kwargs):
            """Return a client backed by version-specific mock responses."""
            return real_client(transport=transport)

        with patch.object(azure_devops.httpx, "Client", side_effect=client_factory):
            result = validate_connection("https://dev.azure.com/Laserbeamch", "pat-value")

        self.assertEqual(versions, ["7.2", "7.1"])
        self.assertEqual(result.projects[0].id, "project-1")

    def test_validate_connection_surfaces_sanitized_azure_bad_request_message(self) -> None:
        """A persistent Azure 400 includes Azure's safe message for diagnosis."""
        transport = httpx.MockTransport(
            lambda request: httpx.Response(400, json={"message": "The requested project API version is invalid."})
        )
        real_client = httpx.Client

        def client_factory(*args, **kwargs):
            """Return a client backed by Azure's bad request body."""
            return real_client(transport=transport)

        with patch.object(azure_devops.httpx, "Client", side_effect=client_factory):
            with self.assertRaises(AzureDevOpsConnectionError) as failure:
                validate_connection("https://dev.azure.com/Laserbeamch", "pat-value")

        self.assertEqual(failure.exception.code, "projects_request_failed")
        self.assertEqual(failure.exception.message, "The requested project API version is invalid.")


class AzureDevOpsRouteTests(unittest.TestCase):
    """Verify the authenticated connector API response contract."""

    def setUp(self) -> None:
        """Create isolated persistence because app startup expects a database."""
        self.temporary = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temporary.name) / "azure-devops.db"
        self.db_patch = patch.object(database, "DATABASE_PATH", self.database_path)
        self.db_patch.start()
        database.initialize_database()
        app.dependency_overrides[get_current_user] = lambda: {
            "id": 1,
            "email": "owner@example.com",
            "organization_id": "org-a",
            "role": "organization_admin",
        }
        self.client = TestClient(app)

    def tearDown(self) -> None:
        """Release test resources and dependency overrides."""
        self.client.close()
        app.dependency_overrides.clear()
        self.db_patch.stop()
        self.temporary.cleanup()

    def test_test_endpoint_returns_projects_after_successful_validation(self) -> None:
        """The UI receives connected=true only from a successful backend test."""
        result = AzureDevOpsValidationResult(
            organization_url="https://dev.azure.com/Laserbeamch",
            projects=[AzureDevOpsProject(id="project-1", name="Knowledge Base")],
            checks=["organization_url", "pat_authentication", "work_items_read"],
        )
        with patch("app.routes.azure_devops.validate_connection", return_value=result):
            response = self.client.post(
                "/integrations/azure-devops/test",
                json={
                    "organization_url": "https://dev.azure.com/Laserbeamch",
                    "personal_access_token": "pat-value",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["connected"], True)
        self.assertEqual(response.json()["projects"][0]["name"], "Knowledge Base")

    def test_test_endpoint_exposes_failure_category_without_pat(self) -> None:
        """Failure responses include a category but never echo the PAT."""
        error = AzureDevOpsConnectionError(
            401,
            "pat_authentication_failed",
            "Azure DevOps rejected the PAT.",
        )
        with patch("app.routes.azure_devops.validate_connection", side_effect=error):
            response = self.client.post(
                "/integrations/azure-devops/test",
                json={
                    "organization_url": "https://dev.azure.com/Laserbeamch",
                    "personal_access_token": "secret-pat",
                },
            )

        self.assertEqual(response.status_code, 401)
        body = response.json()
        self.assertEqual(body["detail"]["code"], "pat_authentication_failed")
        self.assertNotIn("secret-pat", str(body))


if __name__ == "__main__":
    unittest.main()
