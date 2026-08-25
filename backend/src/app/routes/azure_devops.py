"""Azure DevOps connector validation and sync endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth import get_current_user
from app.services.azure_devops import AzureDevOpsConnectionError, sync_work_items, validate_connection

router = APIRouter(prefix="/integrations/azure-devops", tags=["azure-devops"])


class AzureDevOpsTestRequest(BaseModel):
    """Credentials supplied for one live Azure DevOps validation attempt."""

    organization_url: str = Field(min_length=1, max_length=300)
    personal_access_token: str = Field(min_length=1, max_length=512)


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


class AzureDevOpsSyncRequest(BaseModel):
    """Selected Azure Boards source and field mapping for one manual sync."""

    organization_url: str = Field(min_length=1, max_length=300)
    personal_access_token: str = Field(min_length=1, max_length=512)
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
    """Test credentials before any Azure DevOps connection is marked active."""
    _ = current_user
    try:
        result = validate_connection(
            payload.organization_url,
            payload.personal_access_token,
        )
    except AzureDevOpsConnectionError as error:
        raise _azure_http_error(error) from error

    return AzureDevOpsTestResponse(
        connected=True,
        organization_url=result.organization_url,
        projects=[
            AzureDevOpsProjectResponse(id=project.id, name=project.name)
            for project in result.projects
        ],
        checks=result.checks,
    )


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
