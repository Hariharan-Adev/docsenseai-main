"""Azure DevOps connector validation and sync endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.auth import get_current_user
from app.services.azure_devops import (
    AzureDevOpsConnectionError,
    AzureDevOpsSavedConnection,
    delete_saved_connection,
    get_saved_connection,
    list_imported_work_items,
    save_validated_connection,
    sync_work_items,
    validate_saved_connection,
)

router = APIRouter(prefix="/integrations/azure-devops", tags=["azure-devops"])


class AzureDevOpsTestRequest(BaseModel):
    """Credentials supplied for one live Azure DevOps validation attempt."""

    organization_url: str = Field(default="", max_length=300)
    personal_access_token: str = Field(default="", max_length=512)


class AzureDevOpsProjectResponse(BaseModel):
    """Project option returned after Azure DevOps confirms access."""

    id: str
    name: str


class AzureDevOpsTestResponse(BaseModel):
    """Connection validation result shown by the configuration UI."""

    connected: bool
    organization_url: str
    projects: list[AzureDevOpsProjectResponse]
    checks: list[str]
    token_saved: bool = False
    last_tested_at: str | None = None
    message: str = ""


class AzureDevOpsConnectionResponse(BaseModel):
    """Saved Azure DevOps connection state returned without the stored PAT."""

    connected: bool
    organization_url: str
    projects: list[AzureDevOpsProjectResponse]
    checks: list[str]
    token_saved: bool
    last_tested_at: str | None
    message: str = ""


class AzureDevOpsSyncRequest(BaseModel):
    """Selected Azure Boards source and field mapping for one manual sync."""

    organization_url: str = Field(min_length=1, max_length=300)
    personal_access_token: str = Field(default="", max_length=512)
    project_id: str = Field(min_length=1, max_length=200)
    project_name: str = Field(min_length=1, max_length=300)
    work_item_types: list[str] = Field(min_length=1, max_length=20)
    states: list[str] = Field(min_length=1, max_length=20)
    title_field: str = Field(min_length=1, max_length=100)
    content_field: str = Field(min_length=1, max_length=100)
    metadata_fields: list[str] = Field(default_factory=list, max_length=20)


class AzureDevOpsSyncItemResponse(BaseModel):
    """Imported work-item pointer returned without exposing field content."""

    document_id: int
    work_item_id: int
    title: str


class AzureDevOpsSyncResponse(BaseModel):
    """Manual Azure Boards sync result for the configuration page."""

    project_id: str
    project_name: str
    imported_count: int
    skipped_count: int
    items: list[AzureDevOpsSyncItemResponse]


class AzureDevOpsDisconnectResponse(BaseModel):
    """Result returned after removing a saved Azure DevOps connection."""

    disconnected: bool


def _connection_response(
    saved: AzureDevOpsSavedConnection | None,
    message: str = "",
) -> AzureDevOpsConnectionResponse:
    """Map saved connection state to the non-secret frontend contract."""
    if saved is None:
        return AzureDevOpsConnectionResponse(
            connected=False,
            organization_url="",
            projects=[],
            checks=[],
            token_saved=False,
            last_tested_at=None,
            message=message,
        )
    return AzureDevOpsConnectionResponse(
        connected=saved.connected,
        organization_url=saved.organization_url,
        projects=[
            AzureDevOpsProjectResponse(id=project.id, name=project.name)
            for project in saved.projects
        ],
        checks=saved.checks,
        token_saved=saved.token_saved,
        last_tested_at=saved.last_tested_at,
        message=message,
    )


class AzureDevOpsImportedItemResponse(BaseModel):
    """One imported Azure Boards work item shown in the configuration table."""

    document_id: int
    work_item_id: int
    title: str
    description: str
    azure_url: str
    work_item_type: str
    state: str
    imported_at: str


class AzureDevOpsImportedItemsResponse(BaseModel):
    """Paginated read-only response for already imported Azure Boards items."""

    total: int
    page: int
    page_size: int
    last_synced_at: str | None
    items: list[AzureDevOpsImportedItemResponse]


def _azure_http_error(error: AzureDevOpsConnectionError) -> HTTPException:
    """Map service errors into a consistent non-secret API response."""
    return HTTPException(
        status_code=error.status_code,
        detail={
            "code": error.code,
            "message": error.message,
            "retryable": error.retryable,
        },
    )


@router.post("/test", response_model=AzureDevOpsTestResponse)
def test_azure_devops_connection(
    payload: AzureDevOpsTestRequest,
    current_user=Depends(get_current_user),
) -> AzureDevOpsTestResponse:
    """Test and save Azure credentials, or re-test the saved token when omitted."""
    try:
        if payload.personal_access_token.strip():
            result = save_validated_connection(
                owner_id=int(current_user["id"]),
                organization_id=str(current_user["organization_id"]),
                organization_url=payload.organization_url,
                personal_access_token=payload.personal_access_token,
            )
        else:
            result = validate_saved_connection(
                owner_id=int(current_user["id"]),
                organization_id=str(current_user["organization_id"]),
            )
    except AzureDevOpsConnectionError as error:
        raise _azure_http_error(error) from error

    return AzureDevOpsTestResponse(
        connected=result.connected,
        organization_url=result.organization_url,
        projects=[
            AzureDevOpsProjectResponse(id=project.id, name=project.name)
            for project in result.projects
        ],
        checks=result.checks,
        token_saved=result.token_saved,
        last_tested_at=result.last_tested_at,
        message="Azure DevOps connection verified and saved.",
    )


@router.get("/connection", response_model=AzureDevOpsConnectionResponse)
def get_azure_devops_connection(current_user=Depends(get_current_user)) -> AzureDevOpsConnectionResponse:
    """Load saved Azure DevOps state without exposing the encrypted PAT."""
    owner_id = int(current_user["id"])
    organization_id = str(current_user["organization_id"])
    saved = get_saved_connection(owner_id=owner_id, organization_id=organization_id)
    if saved is None:
        return _connection_response(None)
    try:
        return _connection_response(
            validate_saved_connection(owner_id=owner_id, organization_id=organization_id),
            "Azure DevOps connection is active.",
        )
    except AzureDevOpsConnectionError as error:
        saved = get_saved_connection(owner_id=owner_id, organization_id=organization_id)
        return _connection_response(saved, error.message)


@router.post("/sync", response_model=AzureDevOpsSyncResponse)
def sync_azure_devops_work_items(
    payload: AzureDevOpsSyncRequest,
    current_user=Depends(get_current_user),
) -> AzureDevOpsSyncResponse:
    """Import selected Azure Boards work items into owner-scoped RAG content."""
    try:
        result = sync_work_items(
            organization_url=payload.organization_url,
            personal_access_token=payload.personal_access_token,
            project_id=payload.project_id,
            project_name=payload.project_name,
            work_item_types=payload.work_item_types,
            states=payload.states,
            title_field=payload.title_field,
            content_field=payload.content_field,
            metadata_fields=payload.metadata_fields,
            owner_id=int(current_user["id"]),
            organization_id=str(current_user["organization_id"]),
        )
    except AzureDevOpsConnectionError as error:
        raise _azure_http_error(error) from error

    return AzureDevOpsSyncResponse(
        project_id=result.project_id,
        project_name=result.project_name,
        imported_count=result.imported_count,
        skipped_count=result.skipped_count,
        items=[
            AzureDevOpsSyncItemResponse(
                document_id=item.document_id,
                work_item_id=item.work_item_id,
                title=item.title,
            )
            for item in result.items
        ],
    )


@router.delete("/connection", response_model=AzureDevOpsDisconnectResponse)
def disconnect_azure_devops_connection(current_user=Depends(get_current_user)) -> AzureDevOpsDisconnectResponse:
    """Remove the saved Azure DevOps PAT when the user disconnects or deletes it."""
    delete_saved_connection(
        owner_id=int(current_user["id"]),
        organization_id=str(current_user["organization_id"]),
    )
    return AzureDevOpsDisconnectResponse(disconnected=True)


@router.get("/imported-items", response_model=AzureDevOpsImportedItemsResponse)
def get_imported_azure_devops_work_items(
    search: str = Query(default="", max_length=100),
    work_item_type: str = Query(default="", max_length=100),
    state: str = Query(default="", max_length=100),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=50),
    current_user=Depends(get_current_user),
) -> AzureDevOpsImportedItemsResponse:
    """List existing imported Azure Boards items without calling Azure."""
    result = list_imported_work_items(
        owner_id=int(current_user["id"]),
        organization_id=str(current_user["organization_id"]),
        search=search,
        work_item_type=work_item_type,
        state=state,
        page=page,
        page_size=page_size,
    )
    return AzureDevOpsImportedItemsResponse(
        total=result.total,
        page=result.page,
        page_size=result.page_size,
        last_synced_at=result.last_synced_at,
        items=[
            AzureDevOpsImportedItemResponse(
                document_id=item.document_id,
                work_item_id=item.work_item_id,
                title=item.title,
                description=item.description,
                azure_url=item.azure_url,
                work_item_type=item.work_item_type,
                state=item.state,
                imported_at=item.imported_at,
            )
            for item in result.items
        ],
    )
