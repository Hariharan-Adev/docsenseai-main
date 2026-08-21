"""Owner-scoped project CRUD without cascading document or vector deletion."""

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth import get_current_user
from app.database import get_connection

router = APIRouter(prefix="/projects", tags=["projects"])


class ProjectCreate(BaseModel):
    """Validated fields for a new project."""

    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=1000)


class ProjectUpdate(BaseModel):
    """Editable project metadata."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=1000)


class FolderCreate(BaseModel):
    """Validated fields for a new folder inside a project."""

    name: str = Field(min_length=1, max_length=100)


class FolderUpdate(BaseModel):
    """Editable folder metadata."""

    name: str = Field(min_length=1, max_length=100)


def _project_row(project_id: str, user: dict[str, object]):
    """Load one active project only inside the authenticated owner and tenant scope."""
    with get_connection() as connection:
        return connection.execute(
            """SELECT id, name, description, created_at, updated_at
               FROM projects WHERE id = ? AND organization_id = ? AND user_id = ?
                 AND deleted_at IS NULL""",
            (project_id, user["organization_id"], user["id"]),
        ).fetchone()


def require_project(project_id: str, user: dict[str, object]):
    """Reject missing or cross-owner project identifiers without leaking existence."""
    row = _project_row(project_id, user)
    if row is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    return row


def _normalized_name(value: str, label: str) -> str:
    """Collapse whitespace so uniqueness checks match what the user sees."""
    name = " ".join(value.split())
    if not name:
        raise HTTPException(status_code=422, detail=f"{label} is required.")
    return name


def _folder_row(folder_id: str, user: dict[str, object]):
    """Load one active folder only inside the authenticated owner and tenant scope."""
    with get_connection() as connection:
        return connection.execute(
            """SELECT f.id, f.name, f.project_id, f.organization_id, f.user_id,
                      f.created_at, f.updated_at,
                      COALESCE(COUNT(d.id), 0) AS document_count
               FROM folders f
               LEFT JOIN documents d
                 ON d.folder_id = f.id
                AND d.organization_id = f.organization_id
                AND d.owner_id = f.user_id
                AND d.deleted_at IS NULL
               WHERE f.id = ? AND f.organization_id = ? AND f.user_id = ?
                 AND f.deleted_at IS NULL
               GROUP BY f.id""",
            (folder_id, user["organization_id"], user["id"]),
        ).fetchone()


def require_folder(folder_id: str, user: dict[str, object]):
    """Reject missing or cross-owner folder identifiers without leaking existence."""
    row = _folder_row(folder_id, user)
    if row is None:
        raise HTTPException(status_code=404, detail="Folder not found.")
    return row


def _insert_folder(project_id: str, name: str, user: dict[str, object]) -> str:
    """Create a folder and translate active-name collisions into a user error."""
    folder_id = f"folder_{uuid4().hex}"
    try:
        with get_connection() as connection:
            connection.execute(
                """INSERT INTO folders
                   (id, organization_id, user_id, project_id, name)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    folder_id,
                    user["organization_id"],
                    user["id"],
                    project_id,
                    name,
                ),
            )
    except Exception as error:
        if "ux_folders_active_name" in str(error):
            raise HTTPException(
                status_code=409,
                detail="A folder with this name already exists in the project.",
            ) from error
        raise
    return folder_id


@router.post("", status_code=201)
def create_project(payload: ProjectCreate, current_user=Depends(get_current_user)):
    """Create an owner-scoped project and return its persisted representation."""
    name = _normalized_name(payload.name, "Project name")
    project_id = f"project_{uuid4().hex}"
    with get_connection() as connection:
        connection.execute(
            """INSERT INTO projects (id, organization_id, user_id, name, description)
               VALUES (?, ?, ?, ?, ?)""",
            (project_id, current_user["organization_id"], current_user["id"], name, payload.description),
        )
    return dict(require_project(project_id, current_user))


@router.get("")
def list_projects(current_user=Depends(get_current_user)):
    """Return active projects owned by the authenticated user."""
    with get_connection() as connection:
        rows = connection.execute(
            """SELECT id, name, description, created_at, updated_at FROM projects
               WHERE organization_id = ? AND user_id = ? AND deleted_at IS NULL
               ORDER BY updated_at DESC, name COLLATE NOCASE""",
            (current_user["organization_id"], current_user["id"]),
        ).fetchall()
    return {"projects": [dict(row) for row in rows]}


@router.get("/{project_id}")
def get_project(project_id: str, current_user=Depends(get_current_user)):
    """Return one owner-scoped project."""
    return dict(require_project(project_id, current_user))


@router.patch("/{project_id}")
def update_project(project_id: str, payload: ProjectUpdate, current_user=Depends(get_current_user)):
    """Update project metadata while retaining ownership and stable identity."""
    require_project(project_id, current_user)
    name = _normalized_name(payload.name, "Project name") if payload.name is not None else None
    # Explicit null clears the optional description; omitted fields preserve it.
    description_provided = "description" in payload.model_fields_set
    with get_connection() as connection:
        connection.execute(
            """UPDATE projects SET name = COALESCE(?, name),
                   description = CASE WHEN ? THEN ? ELSE description END,
                   updated_at = CURRENT_TIMESTAMP
               WHERE id = ? AND organization_id = ? AND user_id = ? AND deleted_at IS NULL""",
            (name, description_provided, payload.description, project_id,
             current_user["organization_id"], current_user["id"]),
        )
    return dict(require_project(project_id, current_user))


@router.delete("/{project_id}")
def delete_project(project_id: str, current_user=Depends(get_current_user)):
    """Soft-delete only the project container; linked data remains recoverable."""
    require_project(project_id, current_user)
    with get_connection() as connection:
        connection.execute(
            """UPDATE projects SET deleted_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
               WHERE id = ? AND organization_id = ? AND user_id = ?""",
            (project_id, current_user["organization_id"], current_user["id"]),
        )
    return {"id": project_id, "deleted": True, "documents_deleted": False}


@router.post("/{project_id}/folders", status_code=201)
def create_folder(
    project_id: str,
    payload: FolderCreate,
    current_user=Depends(get_current_user),
):
    """Create a folder inside an active owner-scoped project."""
    require_project(project_id, current_user)
    folder_id = _insert_folder(
        project_id,
        _normalized_name(payload.name, "Folder name"),
        current_user,
    )
    return dict(require_folder(folder_id, current_user))


@router.get("/{project_id}/folders")
def list_folders(project_id: str, current_user=Depends(get_current_user)):
    """Return active folders for one project with document counts."""
    require_project(project_id, current_user)
    with get_connection() as connection:
        rows = connection.execute(
            """SELECT f.id, f.name, f.project_id, f.organization_id, f.user_id,
                      f.created_at, f.updated_at,
                      COALESCE(COUNT(d.id), 0) AS document_count
               FROM folders f
               LEFT JOIN documents d
                 ON d.folder_id = f.id
                AND d.organization_id = f.organization_id
                AND d.owner_id = f.user_id
                AND d.deleted_at IS NULL
               WHERE f.project_id = ? AND f.organization_id = ? AND f.user_id = ?
                 AND f.deleted_at IS NULL
               GROUP BY f.id
               ORDER BY f.updated_at DESC, f.name COLLATE NOCASE""",
            (project_id, current_user["organization_id"], current_user["id"]),
        ).fetchall()
    return {"folders": [dict(row) for row in rows]}


@router.get("/{project_id}/folders/{folder_id}")
def get_folder(
    project_id: str,
    folder_id: str,
    current_user=Depends(get_current_user),
):
    """Return one active folder when it belongs to the requested project."""
    require_project(project_id, current_user)
    folder = require_folder(folder_id, current_user)
    if folder["project_id"] != project_id:
        raise HTTPException(status_code=404, detail="Folder not found.")
    return dict(folder)


@router.patch("/{project_id}/folders/{folder_id}")
def update_folder(
    project_id: str,
    folder_id: str,
    payload: FolderUpdate,
    current_user=Depends(get_current_user),
):
    """Rename an active folder without allowing duplicates inside the project."""
    get_folder(project_id, folder_id, current_user)
    name = _normalized_name(payload.name, "Folder name")
    try:
        with get_connection() as connection:
            connection.execute(
                """UPDATE folders
                   SET name = ?, updated_at = CURRENT_TIMESTAMP
                   WHERE id = ? AND organization_id = ? AND user_id = ?
                     AND project_id = ? AND deleted_at IS NULL""",
                (
                    name,
                    folder_id,
                    current_user["organization_id"],
                    current_user["id"],
                    project_id,
                ),
            )
    except Exception as error:
        if "ux_folders_active_name" in str(error):
            raise HTTPException(
                status_code=409,
                detail="A folder with this name already exists in the project.",
            ) from error
        raise
    return dict(require_folder(folder_id, current_user))


@router.delete("/{project_id}/folders/{folder_id}")
def delete_folder(
    project_id: str,
    folder_id: str,
    current_user=Depends(get_current_user),
):
    """Soft-delete a folder while retaining its documents under the project."""
    get_folder(project_id, folder_id, current_user)
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            """UPDATE folders
               SET deleted_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
               WHERE id = ? AND organization_id = ? AND user_id = ?
                 AND project_id = ? AND deleted_at IS NULL""",
            (
                folder_id,
                current_user["organization_id"],
                current_user["id"],
                project_id,
            ),
        )
        # Documents remain available at project scope after their folder is archived.
        connection.execute(
            """UPDATE documents
               SET folder_id = NULL, updated_at = CURRENT_TIMESTAMP
               WHERE folder_id = ? AND organization_id = ? AND owner_id = ?""",
            (folder_id, current_user["organization_id"], current_user["id"]),
        )
    return {"id": folder_id, "deleted": True, "documents_deleted": False}
