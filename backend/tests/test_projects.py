"""Project table and owner-scoped project API regression tests."""

from __future__ import annotations

from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from db import database
from app.auth import get_current_user
from app.main import app


class ProjectTableTests(unittest.TestCase):
    """Verify projects can group documents without weakening tenant isolation."""

    def setUp(self) -> None:
        """Create an isolated SQLite database and authenticated users for each test."""
        self.temporary = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temporary.name) / "projects.db"
        self.db_patch = patch.object(database, "DATABASE_PATH", self.database_path)
        self.db_patch.start()
        database.initialize_database()
        with database.get_connection() as connection:
            connection.executemany(
                "INSERT INTO organizations (id, name) VALUES (?, ?)",
                [("org-a", "AdevTech"), ("org-b", "Client B")],
            )
            connection.executemany(
                """INSERT INTO users
                   (id, email, password_hash, organization_id, role)
                   VALUES (?, ?, 'hash', ?, ?)""",
                [
                    (10, "owner@example.com", "org-a", "organization_admin"),
                    (20, "other@example.com", "org-b", "organization_admin"),
                ],
            )
        self.current_user = {
            "id": 10,
            "email": "owner@example.com",
            "organization_id": "org-a",
            "role": "organization_admin",
        }
        app.dependency_overrides[get_current_user] = lambda: self.current_user
        self.client = TestClient(app, base_url="http://localhost")

    def tearDown(self) -> None:
        """Release the test client, dependency override, and temporary database."""
        self.client.close()
        app.dependency_overrides.clear()
        self.db_patch.stop()
        self.temporary.cleanup()

    def test_initialize_database_creates_project_schema(self) -> None:
        """Projects and folders include ownership, metadata, and soft-delete support."""
        with database.get_connection() as connection:
            project_columns = {
                row["name"]: row
                for row in connection.execute("PRAGMA table_info(projects)")
            }
            folder_columns = {
                row["name"]: row
                for row in connection.execute("PRAGMA table_info(folders)")
            }
            migration = connection.execute(
                "SELECT 1 FROM schema_migrations WHERE version = '016_project_folders'"
            ).fetchone()
            document_columns = {
                table: {
                    row["name"]
                    for row in connection.execute(f"PRAGMA table_info({table})")
                }
                for table in ("documents", "chunks", "chat_sessions", "chat_contexts")
            }

        for required in (
            "id",
            "organization_id",
            "user_id",
            "name",
            "description",
            "created_at",
            "updated_at",
            "deleted_at",
        ):
            self.assertIn(required, project_columns)
        self.assertEqual(project_columns["id"]["pk"], 1)
        self.assertEqual(project_columns["description"]["notnull"], 0)
        self.assertEqual(project_columns["deleted_at"]["notnull"], 0)
        self.assertIsNotNone(migration)
        for required in (
            "id",
            "organization_id",
            "user_id",
            "project_id",
            "name",
            "created_at",
            "updated_at",
            "deleted_at",
        ):
            self.assertIn(required, folder_columns)
        for columns in document_columns.values():
            self.assertIn("project_id", columns)
            self.assertIn("folder_id", columns)

    def test_project_name_migration_deduplicates_existing_active_names(self) -> None:
        """Legacy duplicate active projects are preserved before adding uniqueness."""
        with tempfile.TemporaryDirectory() as temporary:
            database_path = Path(temporary) / "legacy-projects.db"
            connection = sqlite3.connect(database_path)
            connection.row_factory = sqlite3.Row
            connection.executescript(
                """
                CREATE TABLE projects (
                    id TEXT PRIMARY KEY,
                    organization_id TEXT NOT NULL,
                    user_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    deleted_at TEXT
                );
                INSERT INTO projects (id, organization_id, user_id, name) VALUES
                    ('project_1', 'org-a', 10, 'ASRC'),
                    ('project_2', 'org-a', 10, ' asrc '),
                    ('project_3', 'org-a', 10, 'ASRC'),
                    ('project_4', 'org-b', 20, 'asrc');
                """
            )

            database._dedupe_active_project_names_v15(connection)
            connection.execute(
                """CREATE UNIQUE INDEX ux_projects_active_name
                   ON projects(organization_id, user_id, lower(name))
                   WHERE deleted_at IS NULL"""
            )
            rows = connection.execute(
                "SELECT id, name FROM projects ORDER BY id"
            ).fetchall()
            connection.close()

        self.assertEqual(
            [tuple(row) for row in rows],
            [
                ("project_1", "ASRC"),
                ("project_2", "asrc (duplicate 2)"),
                ("project_3", "ASRC (duplicate 3)"),
                ("project_4", "asrc"),
            ],
        )

    def test_project_crud_is_owner_scoped_and_soft_deletes(self) -> None:
        """Only the owning user can see a project, and delete marks it inactive."""
        created = self.client.post(
            "/projects",
            json={"name": "  HR Policy  ", "description": "Policies and benefits"},
        )
        self.assertEqual(created.status_code, 201)
        project = created.json()
        self.assertEqual(project["name"], "HR Policy")
        self.assertEqual(project["description"], "Policies and benefits")
        self.assertTrue(project["id"].startswith("project_"))
        self.assertIn("created_at", project)
        self.assertIn("updated_at", project)

        listed = self.client.get("/projects")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual([item["id"] for item in listed.json()["projects"]], [project["id"]])

        self.current_user = {
            "id": 20,
            "email": "other@example.com",
            "organization_id": "org-b",
            "role": "organization_admin",
        }
        self.assertEqual(self.client.get(f"/projects/{project['id']}").status_code, 404)

        self.current_user = {
            "id": 10,
            "email": "owner@example.com",
            "organization_id": "org-a",
            "role": "organization_admin",
        }
        deleted = self.client.delete(f"/projects/{project['id']}")
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(deleted.json()["documents_deleted"], False)
        self.assertEqual(self.client.get(f"/projects/{project['id']}").status_code, 404)
        self.assertEqual(self.client.get("/projects").json()["projects"], [])
        with database.get_connection() as connection:
            deleted_at = connection.execute(
                "SELECT deleted_at FROM projects WHERE id = ?", (project["id"],)
            ).fetchone()["deleted_at"]
        self.assertIsNotNone(deleted_at)

    def test_duplicate_project_names_are_rejected_in_owner_scope(self) -> None:
        """Project names are trimmed, case-insensitive, and unique per owner."""
        created = self.client.post("/projects", json={"name": "  ASRC  "})
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["name"], "ASRC")

        for duplicate_name in ("ASRC", "asrc", "  ASRC  "):
            duplicate = self.client.post("/projects", json={"name": duplicate_name})
            self.assertEqual(duplicate.status_code, 409)
            self.assertEqual(duplicate.json()["detail"], "Project name already exists.")

        with database.get_connection() as connection:
            count = connection.execute(
                """SELECT COUNT(*) FROM projects
                   WHERE organization_id = 'org-a' AND user_id = 10
                     AND lower(name) = 'asrc' AND deleted_at IS NULL"""
            ).fetchone()[0]
        self.assertEqual(count, 1)

        self.current_user = {
            "id": 20,
            "email": "other@example.com",
            "organization_id": "org-b",
            "role": "organization_admin",
        }
        same_name_other_owner = self.client.post("/projects", json={"name": "asrc"})
        self.assertEqual(same_name_other_owner.status_code, 201)

    def test_project_api_accepts_same_domain_api_prefix(self) -> None:
        """The API prefix alias supports proxies that forward /api unchanged."""
        created = self.client.post("/api/projects", json={"name": "Support"})
        self.assertEqual(created.status_code, 201)

        listed = self.client.get("/api/projects")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()["projects"][0]["id"], created.json()["id"])

    def test_removed_project_management_apis_are_unavailable(self) -> None:
        """Project settings and sharing cannot be reached through direct API calls."""
        project = self.client.post("/projects", json={"name": "ASRC"}).json()

        settings = self.client.patch(
            f"/projects/{project['id']}",
            json={"name": "Renamed"},
        )
        share = self.client.post(
            f"/projects/{project['id']}/share",
            json={"email": "reader@example.com"},
        )
        api_settings = self.client.patch(
            f"/api/projects/{project['id']}",
            json={"name": "Renamed"},
        )
        api_share = self.client.post(
            f"/api/projects/{project['id']}/share",
            json={"email": "reader@example.com"},
        )

        self.assertEqual(settings.status_code, 405)
        self.assertEqual(share.status_code, 404)
        self.assertEqual(api_settings.status_code, 405)
        self.assertEqual(api_share.status_code, 404)
        self.assertEqual(self.client.get(f"/projects/{project['id']}").json()["name"], "ASRC")

    def test_folder_crud_enforces_project_scope_and_soft_deletes(self) -> None:
        """Folders are unique within one project and invisible after soft delete."""
        hr_project = self.client.post("/projects", json={"name": "HR Policy"}).json()
        ops_project = self.client.post("/projects", json={"name": "Operations"}).json()

        created = self.client.post(
            f"/projects/{hr_project['id']}/folders",
            json={"name": "  Leave Policy  "},
        )
        self.assertEqual(created.status_code, 201)
        folder = created.json()
        self.assertEqual(folder["name"], "Leave Policy")
        self.assertEqual(folder["project_id"], hr_project["id"])
        self.assertEqual(folder["document_count"], 0)

        duplicate = self.client.post(
            f"/projects/{hr_project['id']}/folders",
            json={"name": "leave policy"},
        )
        self.assertEqual(duplicate.status_code, 409)
        same_name_other_project = self.client.post(
            f"/projects/{ops_project['id']}/folders",
            json={"name": "Leave Policy"},
        )
        self.assertEqual(same_name_other_project.status_code, 201)

        listed = self.client.get(f"/projects/{hr_project['id']}/folders")
        self.assertEqual([item["id"] for item in listed.json()["folders"]], [folder["id"]])

        renamed = self.client.patch(
            f"/projects/{hr_project['id']}/folders/{folder['id']}",
            json={"name": "Benefits"},
        )
        self.assertEqual(renamed.status_code, 200)
        self.assertEqual(renamed.json()["name"], "Benefits")

        deleted = self.client.delete(f"/projects/{hr_project['id']}/folders/{folder['id']}")
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(deleted.json()["documents_deleted"], False)
        self.assertEqual(
            self.client.get(f"/projects/{hr_project['id']}/folders").json()["folders"],
            [],
        )

    def test_folder_access_and_document_listing_are_owner_scoped(self) -> None:
        """Folder details and document filters deny cross-tenant access."""
        project = self.client.post("/projects", json={"name": "HR Policy"}).json()
        folder = self.client.post(
            f"/projects/{project['id']}/folders",
            json={"name": "Employee Documents"},
        ).json()
        with database.get_connection() as connection:
            content_id = connection.execute(
                """INSERT INTO document_contents
                   (owner_id, organization_id, file_hash, normalized_content_hash,
                    extracted_text, processing_status)
                   VALUES (?, ?, 'hash-a', 'normalized-a', 'alpha', 'completed')""",
                (10, "org-a"),
            ).lastrowid
            connection.execute(
                """INSERT INTO documents
                   (owner_id, organization_id, original_filename, display_filename,
                    stored_filename, file_hash, content_id, project_id, folder_id,
                    visibility, processing_status, updated_at)
                   VALUES (?, ?, 'policy.txt', 'policy.txt', 'policy.txt', 'hash-a',
                           ?, ?, ?, 'private', 'completed', CURRENT_TIMESTAMP)""",
                (10, "org-a", content_id, project["id"], folder["id"]),
            )

        folder_docs = self.client.get(
            f"/documents?project_id={project['id']}&folder_id={folder['id']}"
        )
        self.assertEqual(folder_docs.status_code, 200)
        self.assertEqual(len(folder_docs.json()["documents"]), 1)
        self.assertEqual(folder_docs.json()["documents"][0]["folder_id"], folder["id"])

        self.current_user = {
            "id": 20,
            "email": "other@example.com",
            "organization_id": "org-b",
            "role": "organization_admin",
        }
        self.assertEqual(
            self.client.get(f"/projects/{project['id']}/folders/{folder['id']}").status_code,
            404,
        )
        self.assertEqual(
            self.client.get(
                f"/documents?project_id={project['id']}&folder_id={folder['id']}"
            ).status_code,
            404,
        )

    def test_document_listing_includes_real_project_and_folder_names(self) -> None:
        """Document rows expose source names without changing stored document scope."""
        project = self.client.post("/projects", json={"name": "ASRC"}).json()
        folder = self.client.post(
            f"/projects/{project['id']}/folders",
            json={"name": "Database"},
        ).json()
        with database.get_connection() as connection:
            for index, (filename, project_id, folder_id) in enumerate((
                ("all-docs.txt", None, None),
                ("project-doc.txt", project["id"], None),
                ("folder-doc.txt", project["id"], folder["id"]),
            ), start=1):
                content_id = connection.execute(
                    """INSERT INTO document_contents
                       (owner_id, organization_id, file_hash, normalized_content_hash,
                        extracted_text, processing_status)
                       VALUES (?, ?, ?, ?, ?, 'completed')""",
                    (10, "org-a", f"hash-{index}", f"normalized-{index}", filename),
                ).lastrowid
                connection.execute(
                    """INSERT INTO documents
                       (owner_id, organization_id, original_filename, display_filename,
                        stored_filename, file_hash, content_id, project_id, folder_id,
                        visibility, processing_status, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'private', 'completed',
                               CURRENT_TIMESTAMP)""",
                    (
                        10,
                        "org-a",
                        filename,
                        filename,
                        filename,
                        f"hash-{index}",
                        content_id,
                        project_id,
                        folder_id,
                    ),
                )

        response = self.client.get("/documents")

        self.assertEqual(response.status_code, 200)
        documents = {
            document["filename"]: document
            for document in response.json()["documents"]
        }
        self.assertIsNone(documents["all-docs.txt"]["project_id"])
        self.assertIsNone(documents["all-docs.txt"]["project_name"])
        self.assertEqual(documents["project-doc.txt"]["project_name"], "ASRC")
        self.assertIsNone(documents["project-doc.txt"]["folder_name"])
        self.assertEqual(documents["folder-doc.txt"]["project_name"], "ASRC")
        self.assertEqual(documents["folder-doc.txt"]["folder_name"], "Database")


if __name__ == "__main__":
    unittest.main()
