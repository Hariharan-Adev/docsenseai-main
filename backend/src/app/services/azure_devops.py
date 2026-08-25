"""Azure DevOps connection validation and work-item import helpers."""

from base64 import b64encode
from dataclasses import dataclass
from hashlib import sha256
from html import unescape
import json
import re
import sqlite3
from urllib.parse import urlparse
from urllib.parse import quote

import httpx

from app.config import settings
from app.services.embeddings import create_embeddings
from app.services.vector_store import VectorPoint, get_vector_store, make_vector_point_id
from app.utils.document_content import normalize_extracted_text
from db.database import get_connection

PROJECTS_API_VERSIONS = ("7.2", "7.1")
WORK_ITEMS_API_VERSION = "7.1"
MAX_AZURE_MESSAGE_LENGTH = 300
MAX_SYNC_WORK_ITEMS = 200
AZURE_DEVOPS_FIELD_OPTIONS = {
    "System.Title",
    "System.Description",
    "System.State",
    "System.WorkItemType",
    "System.Tags",
    "System.AreaPath",
}


class AzureDevOpsConnectionError(Exception):
    """Categorized validation failure safe to return to the frontend."""

    def __init__(self, status_code: int, code: str, message: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.retryable = retryable


@dataclass(frozen=True)
class AzureDevOpsProject:
    """Minimal project data needed by the configuration UI."""

    id: str
    name: str


@dataclass(frozen=True)
class AzureDevOpsValidationResult:
    """Successful validation details for the tested organization and PAT."""

    organization_url: str
    projects: list[AzureDevOpsProject]
    checks: list[str]


@dataclass(frozen=True)
class AzureDevOpsSyncItem:
    """One Azure Boards work item normalized for knowledge-base indexing."""

    document_id: int
    work_item_id: int
    title: str


@dataclass(frozen=True)
class AzureDevOpsSyncResult:
    """Summary returned after selected Azure Boards items are indexed."""

    project_id: str
    project_name: str
    imported_count: int
    skipped_count: int
    items: list[AzureDevOpsSyncItem]


@dataclass(frozen=True)
class AzureDevOpsImportedItem:
    """Read-only view of one already-imported Azure Boards work item."""

    document_id: int
    work_item_id: int
    title: str
    work_item_type: str
    state: str
    imported_at: str
    metadata: dict[str, object]


@dataclass(frozen=True)
class AzureDevOpsImportedItemsResult:
    """Paginated list and summary for imported Azure Boards items."""

    total: int
    page: int
    page_size: int
    last_synced_at: str | None
    items: list[AzureDevOpsImportedItem]


def normalize_organization_url(value: str) -> tuple[str, str]:
    """Accept only https://dev.azure.com/{organization} URLs before calling Azure."""
    parsed = urlparse(value.strip())
    path_parts = [part for part in parsed.path.split("/") if part]
    if (
        parsed.scheme.lower() != "https"
        or parsed.netloc.lower() != "dev.azure.com"
        or len(path_parts) != 1
        or parsed.params
        or parsed.query
        or parsed.fragment
    ):
        raise AzureDevOpsConnectionError(
            422,
            "invalid_organization_url",
            "Use the organization URL format https://dev.azure.com/<organization-name>.",
        )
    organization = path_parts[0]
    return f"https://dev.azure.com/{organization}", organization


def _auth_header(personal_access_token: str) -> str:
    """Build the Basic auth header Azure DevOps expects for PAT requests."""
    token = personal_access_token.strip()
    if not token:
        raise AzureDevOpsConnectionError(
            422,
            "missing_pat",
            "Enter an Azure DevOps personal access token.",
        )
    return "Basic " + b64encode(f":{token}".encode("utf-8")).decode("ascii")


def _azure_error_message(response: httpx.Response) -> str:
    """Extract Azure's user-safe error message without exposing request secrets."""
    try:
        body = response.json()
    except ValueError:
        body = {}
    message = body.get("message") or body.get("Message") or body.get("error_description")
    if not isinstance(message, str) or not message.strip():
        return ""
    return " ".join(message.split())[:MAX_AZURE_MESSAGE_LENGTH]


def _raise_for_status(response: httpx.Response, validation_step: str) -> None:
    """Translate Azure REST status codes into actionable connection categories."""
    status_code = response.status_code
    azure_message = _azure_error_message(response)
    if status_code == 401:
        raise AzureDevOpsConnectionError(
            401,
            "pat_authentication_failed",
            "Azure DevOps rejected the PAT. Check that it is active, not expired, not revoked, and created for this organization.",
        )
    if status_code == 403:
        raise AzureDevOpsConnectionError(
            403,
            "insufficient_permissions",
            "Azure DevOps authenticated the PAT, but the user lacks Basic access, project membership, or required read scopes.",
        )
    if status_code == 404:
        raise AzureDevOpsConnectionError(
            404,
            "organization_not_found",
            "Azure DevOps could not find this organization URL or API path.",
        )
    if status_code == 400:
        raise AzureDevOpsConnectionError(
            400,
            f"{validation_step}_request_failed",
            azure_message
            or "Azure DevOps rejected the validation request. Check the organization URL, project access, PAT scopes, and Azure DevOps policy restrictions.",
        )
    if status_code == 429:
        raise AzureDevOpsConnectionError(
            429,
            "azure_devops_rate_limited",
            "Azure DevOps rate-limited the validation request. Try again shortly.",
            retryable=True,
        )
    if status_code >= 400:
        raise AzureDevOpsConnectionError(
            502,
            "azure_devops_error",
            "Azure DevOps returned an unexpected error while validating the connection.",
            retryable=status_code >= 500,
        )


def _clean_field_text(value: object) -> str:
    """Convert Azure rich-text or scalar field values into compact plain text."""
    if value is None:
        return ""
    text = str(value)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</p\s*>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    return " ".join(unescape(text).split())


def _line_value(text: str, label: str) -> str:
    """Read one stored field line from imported Azure chunk text."""
    match = re.search(rf"(?m)^{re.escape(label)}:\s*(.+)$", text)
    return match.group(1).strip() if match else ""


def _validate_field_name(field_name: str) -> str:
    """Allow only known Azure field references before using them in WIQL or indexing."""
    if field_name not in AZURE_DEVOPS_FIELD_OPTIONS:
        raise AzureDevOpsConnectionError(
            422,
            "unsupported_azure_field",
            "Choose a supported Azure DevOps field.",
        )
    return field_name


def _wiql_string(value: str) -> str:
    """Escape a selected filter value before embedding it in a WIQL literal."""
    return "'" + value.replace("'", "''") + "'"


def _work_item_url(organization_url: str, project_name: str, work_item_id: int) -> str:
    """Build the browser URL that opens the imported Azure Boards work item."""
    return f"{organization_url}/{quote(project_name)}/_workitems/edit/{work_item_id}"


def _project_path_segment(project_name: str, project_id: str) -> str:
    """Prefer the display project name for Azure project-scoped REST paths."""
    return quote((project_name or project_id).strip(), safe="")


def _fetch_work_items(
    client: httpx.Client,
    *,
    organization_url: str,
    project_id: str,
    project_name: str,
    headers: dict[str, str],
    fields: list[str],
    work_item_types: list[str],
    states: list[str],
) -> list[dict[str, object]]:
    """Fetch selected Azure Boards work items with WIQL IDs followed by batch fields."""
    type_filter = ", ".join(_wiql_string(value) for value in work_item_types)
    state_filter = ", ".join(_wiql_string(value) for value in states)
    where_parts = [f"[System.TeamProject] = {_wiql_string(project_name or project_id)}"]
    if work_item_types:
        where_parts.append(f"[System.WorkItemType] IN ({type_filter})")
    if states:
        where_parts.append(f"[System.State] IN ({state_filter})")
    # Azure WIQL does not accept SQL-style TOP in the SELECT clause; cap the
    # returned IDs after Azure evaluates the valid query.
    wiql = (
        "SELECT [System.Id] FROM WorkItems "
        f"WHERE {' AND '.join(where_parts)} ORDER BY [System.ChangedDate] DESC"
    )
    project_segment = _project_path_segment(project_name, project_id)
    wiql_response = client.post(
        f"{organization_url}/{project_segment}/_apis/wit/wiql",
        params={"api-version": WORK_ITEMS_API_VERSION},
        headers=headers,
        json={"query": wiql},
    )
    _raise_for_status(wiql_response, "work_items_query")
    ids = [
        int(item["id"])
        for item in wiql_response.json().get("workItems", [])
        if isinstance(item, dict) and isinstance(item.get("id"), int)
    ][:MAX_SYNC_WORK_ITEMS]
    if not ids:
        return []
    batch_response = client.post(
        f"{organization_url}/{project_segment}/_apis/wit/workitemsbatch",
        params={"api-version": WORK_ITEMS_API_VERSION},
        headers=headers,
        json={"ids": ids, "fields": fields, "errorPolicy": "Omit"},
    )
    _raise_for_status(batch_response, "work_items_batch")
    return [
        item for item in batch_response.json().get("value", [])
        if isinstance(item, dict)
    ]


def _index_work_item(
    *,
    organization_id: str,
    owner_id: int,
    organization_url: str,
    project_id: str,
    project_name: str,
    title_field: str,
    content_field: str,
    metadata_fields: list[str],
    item: dict[str, object],
) -> AzureDevOpsSyncItem | None:
    """Persist one Azure work item as a current private document and vector chunk."""
    fields = item.get("fields")
    if not isinstance(fields, dict):
        return None
    raw_id = item.get("id")
    try:
        work_item_id = int(raw_id)
    except (TypeError, ValueError):
        return None
    title = _clean_field_text(fields.get(title_field)) or f"Azure Work Item {work_item_id}"
    display_filename = f"{title} (Azure #{work_item_id})"
    content = _clean_field_text(fields.get(content_field))
    metadata_lines = [
        f"{field}: {_clean_field_text(fields.get(field))}"
        for field in metadata_fields
        if _clean_field_text(fields.get(field))
    ]
    text = "\n".join([
        f"Title: {title}",
        f"Azure Work Item ID: {work_item_id}",
        f"Project: {project_name}",
        f"Content: {content}" if content else "",
        *metadata_lines,
    ]).strip()
    normalized_text = normalize_extracted_text(text)
    if not normalized_text:
        return None

    normalized_hash = sha256(normalized_text.encode("utf-8")).hexdigest()
    file_hash = sha256(
        f"azure-devops:{organization_url}:{project_id}:{work_item_id}:{normalized_hash}".encode("utf-8")
    ).hexdigest()
    original_filename = f"azure-devops-{project_id}-{work_item_id}.md"
    source_metadata = {
        "source_type": "azure_devops",
        "organization_url": organization_url,
        "project_id": project_id,
        "project_name": project_name,
        "work_item_id": work_item_id,
        "title_field": title_field,
        "content_field": content_field,
        "metadata_fields": metadata_fields,
        "url": _work_item_url(organization_url, project_name, work_item_id),
    }
    embedding = create_embeddings([normalized_text])[0]
    if len(embedding) != settings.embedding_dimension:
        raise AzureDevOpsConnectionError(
            502,
            "azure_devops_embedding_failed",
            "Azure DevOps work item content could not be indexed.",
        )

    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        existing_document = connection.execute(
            """SELECT id, current_version_id FROM documents
               WHERE organization_id = ? AND owner_id = ? AND original_filename = ?
                 AND deleted_at IS NULL
               ORDER BY id DESC LIMIT 1""",
            (organization_id, owner_id, original_filename),
        ).fetchone()
        existing_content = connection.execute(
            """SELECT id FROM document_contents
               WHERE organization_id = ? AND owner_id = ?
                 AND normalized_content_hash = ? AND deleted_at IS NULL
               ORDER BY id LIMIT 1""",
            (organization_id, owner_id, normalized_hash),
        ).fetchone()
        if existing_document and existing_content:
            current_version = connection.execute(
                "SELECT content_id FROM document_versions WHERE id = ?",
                (existing_document["current_version_id"],),
            ).fetchone()
            if current_version and int(current_version["content_id"]) == int(existing_content["id"]):
                return None

        if existing_content:
            content_id = int(existing_content["id"])
        else:
            content_id = int(connection.execute(
                """INSERT INTO document_contents
                   (owner_id, organization_id, file_hash, normalized_content_hash,
                    extracted_text, processing_status)
                   VALUES (?, ?, ?, ?, ?, 'completed')""",
                (owner_id, organization_id, file_hash, normalized_hash, normalized_text),
            ).lastrowid)

        if existing_document:
            document_id = int(existing_document["id"])
            version_number = int(connection.execute(
                """SELECT COALESCE(MAX(version_number), 0) + 1
                   FROM document_versions
                   WHERE organization_id = ? AND document_id = ?""",
                (organization_id, document_id),
            ).fetchone()[0])
        else:
            document_id = int(connection.execute(
                """INSERT INTO documents
                   (owner_id, organization_id, original_filename, display_filename,
                    stored_filename, file_hash, content_id, visibility,
                    processing_status, updated_at)
                   VALUES (?, ?, ?, ?, '', ?, ?, 'private', 'completed',
                           CURRENT_TIMESTAMP)""",
                (
                    owner_id, organization_id, original_filename,
                    display_filename, file_hash, content_id,
                ),
            ).lastrowid)
            version_number = 1

        version_id = int(connection.execute(
            """INSERT INTO document_versions
               (organization_id, document_id, version_number, content_id,
                stored_filename, file_hash, normalized_content_hash, status,
                ingestion_status, extraction_status, indexing_status,
                source_metadata_json, created_by, completed_at)
               VALUES (?, ?, ?, ?, '', ?, ?, 'completed', 'completed',
                       'completed', 'completed', ?, ?, CURRENT_TIMESTAMP)""",
            (
                organization_id, document_id, version_number, content_id,
                file_hash, normalized_hash, json.dumps(source_metadata), owner_id,
            ),
        ).lastrowid)
        point_id = make_vector_point_id(
            organization_id, version_id, 0, settings.embedding_model_version
        )
        chunk_id = int(connection.execute(
            """INSERT INTO chunks
               (content_id, chunk_index, text, embedding, organization_id,
                document_id, version_id, source_type, source_location_json,
                token_count, vector_point_id, embedding_model,
                embedding_dimension, indexing_status, qdrant_indexed_at)
               VALUES (?, 0, ?, ?, ?, ?, ?, 'azure_devops', ?, ?, ?, ?, ?,
                       'pending', NULL)""",
            (
                content_id, normalized_text, json.dumps(embedding), organization_id,
                document_id, version_id, json.dumps(source_metadata),
                len(normalized_text.split()), point_id,
                settings.embedding_model_version, settings.embedding_dimension,
            ),
        ).lastrowid)
        connection.execute(
            """UPDATE documents SET current_version_id = ?, content_id = ?,
               file_hash = ?, display_filename = ?, updated_at = CURRENT_TIMESTAMP
               WHERE id = ? AND organization_id = ?""",
            (
                version_id, content_id, file_hash, display_filename,
                document_id, organization_id,
            ),
        )

    point = VectorPoint(
        organization_id=organization_id,
        owner_id=owner_id,
        document_id=document_id,
        version_id=version_id,
        content_id=content_id,
        chunk_id=chunk_id,
        chunk_index=0,
        vector=embedding,
        text=normalized_text,
        filename=display_filename,
        visibility="private",
        source_type="azure_devops",
        source_location=source_metadata,
        embedding_model=settings.embedding_model_version,
    )
    get_vector_store().upsert_chunks([point])
    with get_connection() as connection:
        connection.execute(
            """UPDATE chunks SET indexing_status = 'completed',
               qdrant_indexed_at = CURRENT_TIMESTAMP
               WHERE id = ? AND organization_id = ?""",
            (chunk_id, organization_id),
        )
    return AzureDevOpsSyncItem(
        document_id=document_id,
        work_item_id=work_item_id,
        title=title,
    )


def validate_connection(organization_url: str, personal_access_token: str) -> AzureDevOpsValidationResult:
    """Validate URL, PAT authentication, organization membership, and project access."""
    normalized_url, _organization = normalize_organization_url(organization_url)
    headers = {
        "Accept": "application/json",
        "Authorization": _auth_header(personal_access_token),
    }
    try:
        with httpx.Client(timeout=10.0) as client:
            projects_response = None
            for api_version in PROJECTS_API_VERSIONS:
                projects_response = client.get(
                    f"{normalized_url}/_apis/projects",
                    params={"api-version": api_version},
                    headers=headers,
                )
                # Some Azure DevOps tenants reject a newer API version before
                # authentication is useful. Retry the stable previous version
                # before surfacing a validation failure.
                if projects_response.status_code != 400:
                    break
            _raise_for_status(projects_response, "projects")
            project_items = projects_response.json().get("value", [])
            projects = [
                AzureDevOpsProject(id=str(item["id"]), name=str(item["name"]))
                for item in project_items
                if item.get("id") and item.get("name")
            ]
            if not projects:
                raise AzureDevOpsConnectionError(
                    403,
                    "no_accessible_projects",
                    "Azure DevOps authenticated the PAT, but no projects were returned for this user.",
                )
    except httpx.TimeoutException as error:
        raise AzureDevOpsConnectionError(
            504,
            "azure_devops_timeout",
            "The backend timed out while reaching dev.azure.com.",
            retryable=True,
        ) from error
    except httpx.RequestError as error:
        raise AzureDevOpsConnectionError(
            503,
            "azure_devops_network_error",
            "The backend cannot reach dev.azure.com right now.",
            retryable=True,
        ) from error
    except ValueError as error:
        raise AzureDevOpsConnectionError(
            502,
            "invalid_azure_response",
            "Azure DevOps returned a response the backend could not read.",
        ) from error

    return AzureDevOpsValidationResult(
        organization_url=normalized_url,
        projects=projects,
        checks=[
            "organization_url",
            "pat_authentication",
            "project_membership",
            "project_and_team_read",
            "projects_api_access",
        ],
    )


def sync_work_items(
    *,
    organization_url: str,
    personal_access_token: str,
    project_id: str,
    project_name: str,
    work_item_types: list[str],
    states: list[str],
    title_field: str,
    content_field: str,
    metadata_fields: list[str],
    owner_id: int,
    organization_id: str,
) -> AzureDevOpsSyncResult:
    """Fetch selected Azure Boards work items and index them for retrieval."""
    normalized_url, _organization = normalize_organization_url(organization_url)
    title_field = _validate_field_name(title_field)
    content_field = _validate_field_name(content_field)
    metadata_fields = [_validate_field_name(field) for field in metadata_fields]
    fields = sorted({title_field, content_field, *metadata_fields})
    safe_types = [value.strip() for value in work_item_types if value.strip()]
    safe_states = [value.strip() for value in states if value.strip()]
    if not project_id.strip() or not project_name.strip():
        raise AzureDevOpsConnectionError(422, "missing_project", "Select an Azure DevOps project.")
    if not safe_types:
        raise AzureDevOpsConnectionError(422, "missing_work_item_types", "Select at least one work item type.")
    if not safe_states:
        raise AzureDevOpsConnectionError(422, "missing_states", "Select at least one work item state.")
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": _auth_header(personal_access_token),
    }
    try:
        with httpx.Client(timeout=20.0) as client:
            items = _fetch_work_items(
                client,
                organization_url=normalized_url,
                project_id=project_id.strip(),
                project_name=project_name.strip(),
                headers=headers,
                fields=fields,
                work_item_types=safe_types,
                states=safe_states,
            )
    except httpx.TimeoutException as error:
        raise AzureDevOpsConnectionError(
            504,
            "azure_devops_timeout",
            "The backend timed out while fetching Azure DevOps work items.",
            retryable=True,
        ) from error
    except httpx.RequestError as error:
        raise AzureDevOpsConnectionError(
            503,
            "azure_devops_network_error",
            "The backend cannot reach dev.azure.com right now.",
            retryable=True,
        ) from error
    except (ValueError, sqlite3.Error) as error:
        raise AzureDevOpsConnectionError(
            502,
            "azure_devops_sync_failed",
            "Azure DevOps work items could not be imported.",
        ) from error

    imported: list[AzureDevOpsSyncItem] = []
    skipped = 0
    for item in items:
        try:
            synced = _index_work_item(
                organization_id=organization_id,
                owner_id=owner_id,
                organization_url=normalized_url,
                project_id=project_id.strip(),
                project_name=project_name.strip(),
                title_field=title_field,
                content_field=content_field,
                metadata_fields=metadata_fields,
                item=item,
            )
        except AzureDevOpsConnectionError:
            raise
        except Exception as error:
            raise AzureDevOpsConnectionError(
                502,
                "azure_devops_sync_failed",
                "Azure DevOps work items could not be imported.",
            ) from error
        if synced is None:
            skipped += 1
        else:
            imported.append(synced)

    return AzureDevOpsSyncResult(
        project_id=project_id.strip(),
        project_name=project_name.strip(),
        imported_count=len(imported),
        skipped_count=skipped,
        items=imported,
    )


def list_imported_work_items(
    *,
    owner_id: int,
    organization_id: str,
    search: str = "",
    work_item_type: str = "",
    state: str = "",
    page: int = 1,
    page_size: int = 10,
) -> AzureDevOpsImportedItemsResult:
    """Return imported Azure Boards items from existing indexed RAG records."""
    page = max(1, page)
    page_size = min(max(1, page_size), 50)
    with get_connection() as connection:
        rows = connection.execute(
            """SELECT d.id AS document_id, d.display_filename, d.updated_at,
                      dv.completed_at, c.text, c.source_location_json
               FROM documents d
               JOIN chunks c
                 ON c.document_id = d.id
                AND c.version_id = d.current_version_id
                AND c.organization_id = d.organization_id
               JOIN document_versions dv
                 ON dv.id = d.current_version_id
                AND dv.organization_id = d.organization_id
               WHERE d.organization_id = ? AND d.owner_id = ?
                 AND d.deleted_at IS NULL AND c.deleted_at IS NULL
                 AND c.source_type = 'azure_devops'
               ORDER BY COALESCE(dv.completed_at, d.updated_at, d.uploaded_at) DESC,
                        d.id DESC""",
            (organization_id, owner_id),
        ).fetchall()

    items: list[AzureDevOpsImportedItem] = []
    for row in rows:
        try:
            metadata = json.loads(row["source_location_json"] or "{}")
        except (TypeError, json.JSONDecodeError):
            metadata = {}
        text = str(row["text"] or "")
        raw_work_item_id = metadata.get("work_item_id")
        try:
            work_item_id = int(raw_work_item_id)
        except (TypeError, ValueError):
            continue
        title = _line_value(text, "Title") or str(row["display_filename"] or "")
        imported_type = _line_value(text, "System.WorkItemType")
        imported_state = _line_value(text, "System.State")
        imported_at = str(row["completed_at"] or row["updated_at"] or "")
        item = AzureDevOpsImportedItem(
            document_id=int(row["document_id"]),
            work_item_id=work_item_id,
            title=title,
            work_item_type=imported_type,
            state=imported_state,
            imported_at=imported_at,
            metadata=metadata,
        )
        query = search.strip().casefold()
        if query and query not in item.title.casefold() and query not in str(work_item_id):
            continue
        if work_item_type.strip() and item.work_item_type != work_item_type.strip():
            continue
        if state.strip() and item.state != state.strip():
            continue
        items.append(item)

    start = (page - 1) * page_size
    paged = items[start:start + page_size]
    last_synced = max((item.imported_at for item in items if item.imported_at), default=None)
    return AzureDevOpsImportedItemsResult(
        total=len(items),
        page=page,
        page_size=page_size,
        last_synced_at=last_synced,
        items=paged,
    )
