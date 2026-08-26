"""Azure DevOps connector validation regression tests."""

from __future__ import annotations

import tempfile
import unittest
import json
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from app.auth import get_current_user
from app.main import app
from app.services import azure_devops
from app.services.azure_devops import (
    AzureDevOpsConnectionError,
    AzureDevOpsImportedItem,
    AzureDevOpsImportedItemsResult,
    AzureDevOpsProject,
    AzureDevOpsValidationResult,
    get_saved_connection,
    list_imported_work_items,
    normalize_organization_url,
    save_validated_connection,
    sync_work_items,
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

    def test_sync_work_items_indexes_selected_source_and_content_fields(self) -> None:
        """Selected Azure source filters and content fields become RAG chunks."""
        with tempfile.TemporaryDirectory() as temporary:
            database_path = Path(temporary) / "azure-sync.db"
            with patch.object(database, "DATABASE_PATH", database_path):
                database.initialize_database()
                with database.get_connection() as connection:
                    connection.execute(
                        "INSERT INTO organizations (id, name) VALUES ('org-a', 'Org A')"
                    )
                    connection.execute(
                        """INSERT INTO users
                           (id, email, password_hash, organization_id, role)
                           VALUES (1, 'owner@example.com', 'hash', 'org-a',
                                   'organization_admin')"""
                    )

                def handler(request: httpx.Request) -> httpx.Response:
                    """Return Azure-like WIQL and batch work-item responses."""
                    if request.url.path == "/Laserbeamch/Hunt/_apis/wit/wiql":
                        body = json.loads(request.content.decode("utf-8"))
                        self.assertTrue(body["query"].startswith("SELECT [System.Id] FROM WorkItems"))
                        self.assertNotIn("SELECT TOP", body["query"])
                        self.assertIn("[System.WorkItemType] IN ('Bug')", body["query"])
                        self.assertIn("[System.State] IN ('Active')", body["query"])
                        return httpx.Response(200, json={"workItems": [{"id": 101}]})
                    if request.url.path == "/Laserbeamch/Hunt/_apis/wit/workitemsbatch":
                        body = json.loads(request.content.decode("utf-8"))
                        self.assertEqual(
                            body["fields"],
                            ["System.Description", "System.State", "System.Title", "System.WorkItemType"],
                        )
                        return httpx.Response(
                            200,
                            json={
                                "value": [{
                                    "id": 101,
                                    "fields": {
                                        "System.Title": "Login bug",
                                        "System.Description": "<p>Login fails on submit</p>",
                                        "System.State": "Active",
                                        "System.WorkItemType": "Bug",
                                    },
                                }]
                            },
                        )
                    return httpx.Response(404, json={})

                class FakeVectorStore:
                    """Capture vector writes without requiring Qdrant in this unit test."""

                    def __init__(self) -> None:
                        self.points = []

                    def upsert_chunks(self, points) -> None:
                        self.points.extend(points)

                store = FakeVectorStore()
                transport = httpx.MockTransport(handler)
                real_client = httpx.Client

                def client_factory(*args, **kwargs):
                    """Inject mocked Azure responses into the sync client."""
                    return real_client(transport=transport)

                with patch.object(azure_devops.httpx, "Client", side_effect=client_factory), \
                    patch.object(azure_devops, "create_embeddings", return_value=[[1.0] + [0.0] * 383]), \
                    patch.object(azure_devops, "get_vector_store", return_value=store):
                    result = sync_work_items(
                        organization_url="https://dev.azure.com/Laserbeamch",
                        personal_access_token="pat-value",
                        project_id="project-1",
                        project_name="Hunt",
                        work_item_types=["Bug"],
                        states=["Active"],
                        title_field="System.Title",
                        content_field="System.Description",
                        metadata_fields=["System.State", "System.WorkItemType"],
                        owner_id=1,
                        organization_id="org-a",
                    )

                self.assertEqual(result.imported_count, 1)
                self.assertEqual(result.items[0].work_item_id, 101)
                self.assertEqual(len(store.points), 1)
                with database.get_connection() as connection:
                    chunk = connection.execute(
                        """SELECT text, source_type, source_location_json,
                                  indexing_status
                           FROM chunks"""
                    ).fetchone()
                self.assertEqual(chunk["source_type"], "azure_devops")
                self.assertEqual(chunk["indexing_status"], "completed")
                self.assertIn("Content: Login fails on submit", chunk["text"])
                self.assertIn("System.State: Active", chunk["text"])
                self.assertIn("System.WorkItemType: Bug", chunk["text"])
                location = json.loads(chunk["source_location_json"])
                self.assertEqual(location["project_name"], "Hunt")
                self.assertEqual(location["work_item_id"], 101)

                imported = list_imported_work_items(
                    owner_id=1,
                    organization_id="org-a",
                    search="101",
                    work_item_type="Bug",
                    state="Active",
                )
                self.assertEqual(imported.total, 1)
                self.assertEqual(imported.items[0].title, "Login bug")
                self.assertEqual(imported.items[0].description, "Login fails on submit")
                self.assertEqual(
                    imported.items[0].azure_url,
                    "https://dev.azure.com/Laserbeamch/Hunt/_workitems/edit/101",
                )
                self.assertEqual(imported.items[0].work_item_type, "Bug")
                self.assertEqual(imported.items[0].state, "Active")

    def test_imported_items_rebuilds_mismatched_stored_url(self) -> None:
        """Displayed Azure links must point to the selected imported work item."""
        class FakeVectorStore:
            """Capture indexed points without requiring a running Qdrant instance."""

            def __init__(self) -> None:
                self.points = []

            def upsert_chunks(self, points) -> None:
                self.points.extend(points)

        store = FakeVectorStore()
        with tempfile.TemporaryDirectory() as temporary:
            database_path = Path(temporary) / "azure-url.db"
            with patch.object(database, "DATABASE_PATH", database_path):
                database.initialize_database()
                with database.get_connection() as connection:
                    connection.execute(
                        "INSERT INTO organizations (id, name) VALUES ('org-a', 'Org A')"
                    )
                    connection.execute(
                        """INSERT INTO users
                           (id, email, password_hash, organization_id, role)
                           VALUES (1, 'owner@example.com', 'hash', 'org-a',
                                   'organization_admin')"""
                    )

                with patch.object(azure_devops, "create_embeddings", return_value=[[1.0] + [0.0] * 383]), \
                    patch.object(azure_devops, "get_vector_store", return_value=store):
                    azure_devops._index_work_item(
                        organization_id="org-a",
                        owner_id=1,
                        organization_url="https://dev.azure.com/Laserbeamch",
                        project_id="project-1",
                        project_name="Hunt",
                        title_field="System.Title",
                        content_field="System.Description",
                        metadata_fields=["System.State", "System.WorkItemType"],
                        item={
                            "id": 101,
                            "fields": {
                                "System.Title": "Login bug",
                                "System.Description": "Login fails on submit",
                                "System.State": "Active",
                                "System.WorkItemType": "Bug",
                            },
                        },
                    )
                with database.get_connection() as connection:
                    location = json.loads(connection.execute(
                        "SELECT source_location_json FROM chunks"
                    ).fetchone()["source_location_json"])
                    location["url"] = "https://dev.azure.com/Laserbeamch/Hunt/_workitems/edit/999"
                    connection.execute(
                        "UPDATE chunks SET source_location_json = ?",
                        (json.dumps(location),),
                    )

                imported = list_imported_work_items(
                    owner_id=1,
                    organization_id="org-a",
                )

        self.assertEqual(
            imported.items[0].azure_url,
            "https://dev.azure.com/Laserbeamch/Hunt/_workitems/edit/101",
        )

    def test_saved_connection_encrypts_pat_and_returns_non_secret_summary(self) -> None:
        """Saving a validated connection must persist the PAT without exposing it."""
        with tempfile.TemporaryDirectory() as temporary:
            database_path = Path(temporary) / "azure-saved.db"
            with patch.object(database, "DATABASE_PATH", database_path):
                database.initialize_database()
                with database.get_connection() as connection:
                    connection.execute(
                        "INSERT INTO organizations (id, name) VALUES ('org-a', 'Org A')"
                    )
                    connection.execute(
                        """INSERT INTO users
                           (id, email, password_hash, organization_id, role)
                           VALUES (1, 'owner@example.com', 'hash', 'org-a',
                                   'organization_admin')"""
                    )

                validation = AzureDevOpsValidationResult(
                    organization_url="https://dev.azure.com/Laserbeamch",
                    projects=[AzureDevOpsProject(id="project-1", name="Hunt")],
                    checks=["organization_url", "pat_authentication"],
                )
                with patch.object(azure_devops, "validate_connection", return_value=validation):
                    saved = save_validated_connection(
                        owner_id=1,
                        organization_id="org-a",
                        organization_url="https://dev.azure.com/Laserbeamch",
                        personal_access_token="secret-pat",
                    )

                with database.get_connection() as connection:
                    row = connection.execute(
                        """SELECT encrypted_pat FROM azure_devops_connections
                           WHERE organization_id = 'org-a' AND user_id = 1"""
                    ).fetchone()

                self.assertTrue(saved.connected)
                self.assertTrue(saved.token_saved)
                self.assertEqual(saved.organization_url, "https://dev.azure.com/Laserbeamch")
                self.assertEqual(saved.projects[0].name, "Hunt")
                self.assertNotIn("secret-pat", row["encrypted_pat"])
                self.assertNotIn("secret-pat", str(saved))
                self.assertNotIn("secret-pat", str(get_saved_connection(owner_id=1, organization_id="org-a")))


class AzureDevOpsRouteTests(unittest.TestCase):
    """Verify the authenticated connector API response contract."""

    def setUp(self) -> None:
        """Create isolated persistence because app startup expects a database."""
        self.temporary = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temporary.name) / "azure-devops.db"
        self.db_patch = patch.object(database, "DATABASE_PATH", self.database_path)
        self.db_patch.start()
        database.initialize_database()
        with database.get_connection() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO organizations (id, name) VALUES ('org-a', 'Org A')"
            )
            connection.execute(
                """INSERT OR IGNORE INTO users
                   (id, email, password_hash, organization_id, role)
                   VALUES (1, 'owner@example.com', 'hash', 'org-a',
                           'organization_admin')"""
            )
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
        """A successful test saves the connection without echoing the PAT."""
        result = AzureDevOpsValidationResult(
            organization_url="https://dev.azure.com/Laserbeamch",
            projects=[AzureDevOpsProject(id="project-1", name="Knowledge Base")],
            checks=["organization_url", "pat_authentication", "work_items_read"],
        )
        with patch("app.services.azure_devops.validate_connection", return_value=result):
            response = self.client.post(
                "/integrations/azure-devops/test",
                json={
                    "organization_url": "https://dev.azure.com/Laserbeamch",
                    "personal_access_token": "pat-value",
                },
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["connected"], True)
        self.assertEqual(body["projects"][0]["name"], "Knowledge Base")
        self.assertEqual(body["token_saved"], True)
        self.assertNotIn("pat-value", str(body))
        with database.get_connection() as connection:
            row = connection.execute(
                "SELECT organization_url, encrypted_pat, connected FROM azure_devops_connections"
            ).fetchone()
        self.assertEqual(row["organization_url"], "https://dev.azure.com/Laserbeamch")
        self.assertEqual(row["connected"], 1)
        self.assertNotIn("pat-value", row["encrypted_pat"])

    def test_connection_endpoint_returns_saved_state_without_pat(self) -> None:
        """Reloading the configuration page returns saved status but not the token."""
        validation = AzureDevOpsValidationResult(
            organization_url="https://dev.azure.com/Laserbeamch",
            projects=[AzureDevOpsProject(id="project-1", name="Knowledge Base")],
            checks=["organization_url", "pat_authentication"],
        )
        with patch("app.services.azure_devops.validate_connection", return_value=validation):
            save_validated_connection(
                owner_id=1,
                organization_id="org-a",
                organization_url="https://dev.azure.com/Laserbeamch",
                personal_access_token="secret-pat",
            )
            response = self.client.get("/integrations/azure-devops/connection")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["organization_url"], "https://dev.azure.com/Laserbeamch")
        self.assertEqual(body["projects"][0]["id"], "project-1")
        self.assertTrue(body["connected"])
        self.assertTrue(body["token_saved"])
        self.assertNotIn("secret-pat", str(body))

    def test_connection_endpoint_marks_expired_saved_pat_disconnected(self) -> None:
        """An invalid saved PAT is retained masked but no longer shown as connected."""
        validation = AzureDevOpsValidationResult(
            organization_url="https://dev.azure.com/Laserbeamch",
            projects=[AzureDevOpsProject(id="project-1", name="Knowledge Base")],
            checks=["organization_url", "pat_authentication"],
        )
        with patch("app.services.azure_devops.validate_connection", return_value=validation):
            save_validated_connection(
                owner_id=1,
                organization_id="org-a",
                organization_url="https://dev.azure.com/Laserbeamch",
                personal_access_token="expired-pat",
            )
        error = AzureDevOpsConnectionError(
            401,
            "pat_authentication_failed",
            "Azure DevOps rejected the PAT. Check that it is active, not expired, not revoked, and created for this organization.",
        )
        with patch("app.services.azure_devops.validate_connection", side_effect=error):
            response = self.client.get("/integrations/azure-devops/connection")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertFalse(body["connected"])
        self.assertTrue(body["token_saved"])
        self.assertIn("rejected the PAT", body["message"])
        self.assertNotIn("expired-pat", str(body))

    def test_sync_endpoint_can_use_saved_pat_without_frontend_echo(self) -> None:
        """Saved credentials allow sync without resending the PAT from the browser."""
        validation = AzureDevOpsValidationResult(
            organization_url="https://dev.azure.com/Laserbeamch",
            projects=[AzureDevOpsProject(id="project-1", name="Knowledge Base")],
            checks=["organization_url", "pat_authentication"],
        )
        with patch("app.services.azure_devops.validate_connection", return_value=validation):
            save_validated_connection(
                owner_id=1,
                organization_id="org-a",
                organization_url="https://dev.azure.com/Laserbeamch",
                personal_access_token="saved-pat",
            )
        with patch("app.routes.azure_devops.sync_work_items") as sync:
            sync.return_value.project_id = "project-1"
            sync.return_value.project_name = "Knowledge Base"
            sync.return_value.imported_count = 0
            sync.return_value.skipped_count = 0
            sync.return_value.items = []
            response = self.client.post(
                "/integrations/azure-devops/sync",
                json={
                    "organization_url": "https://dev.azure.com/Laserbeamch",
                    "project_id": "project-1",
                    "project_name": "Knowledge Base",
                    "work_item_types": ["Bug"],
                    "states": ["Active"],
                    "title_field": "System.Title",
                    "content_field": "System.Description",
                    "metadata_fields": ["System.State"],
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(sync.call_args.kwargs["personal_access_token"], "")

    def test_disconnect_endpoint_soft_deletes_saved_pat(self) -> None:
        """Disconnecting removes the saved PAT from future configuration loads."""
        validation = AzureDevOpsValidationResult(
            organization_url="https://dev.azure.com/Laserbeamch",
            projects=[AzureDevOpsProject(id="project-1", name="Knowledge Base")],
            checks=["organization_url", "pat_authentication"],
        )
        with patch("app.services.azure_devops.validate_connection", return_value=validation):
            save_validated_connection(
                owner_id=1,
                organization_id="org-a",
                organization_url="https://dev.azure.com/Laserbeamch",
                personal_access_token="secret-pat",
            )

        response = self.client.delete("/integrations/azure-devops/connection")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["disconnected"])
        self.assertIsNone(get_saved_connection(owner_id=1, organization_id="org-a"))

    def test_test_endpoint_exposes_failure_category_without_pat(self) -> None:
        """Failure responses include a category but never echo the PAT."""
        error = AzureDevOpsConnectionError(
            401,
            "pat_authentication_failed",
            "Azure DevOps rejected the PAT.",
        )
        with patch("app.services.azure_devops.validate_connection", side_effect=error):
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

    def test_imported_items_endpoint_returns_existing_sync_rows(self) -> None:
        """The configuration page receives paginated imported Azure item data."""
        result = AzureDevOpsImportedItemsResult(
            total=1,
            page=1,
            page_size=10,
            last_synced_at="2026-08-25 10:50:00",
            items=[
                AzureDevOpsImportedItem(
                    document_id=10,
                    work_item_id=101,
                    title="Login bug",
                    description="Login fails on submit",
                    azure_url="https://dev.azure.com/Laserbeamch/Hunt/_workitems/edit/101",
                    work_item_type="Bug",
                    state="Active",
                    imported_at="2026-08-25 10:50:00",
                )
            ],
        )
        with patch("app.routes.azure_devops.list_imported_work_items", return_value=result) as imported:
            response = self.client.get(
                "/integrations/azure-devops/imported-items",
                params={"search": "login", "work_item_type": "Bug", "state": "Active"},
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["total"], 1)
        self.assertEqual(body["items"][0]["work_item_id"], 101)
        self.assertEqual(body["items"][0]["description"], "Login fails on submit")
        self.assertEqual(
            body["items"][0]["azure_url"],
            "https://dev.azure.com/Laserbeamch/Hunt/_workitems/edit/101",
        )
        self.assertNotIn("metadata", body["items"][0])
        imported.assert_called_once_with(
            owner_id=1,
            organization_id="org-a",
            search="login",
            work_item_type="Bug",
            state="Active",
            page=1,
            page_size=10,
        )


if __name__ == "__main__":
    unittest.main()
