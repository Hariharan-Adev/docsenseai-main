"""Azure DevOps connector validation endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth import get_current_user
from app.services.azure_devops import AzureDevOpsConnectionError, validate_connection

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
        raise HTTPException(
            status_code=error.status_code,
            detail={
                "code": error.code,
                "message": error.message,
                "retryable": error.retryable,
            },
        ) from error

    return AzureDevOpsTestResponse(
        connected=True,
        organization_url=result.organization_url,
        projects=[
            AzureDevOpsProjectResponse(id=project.id, name=project.name)
            for project in result.projects
        ],
        checks=result.checks,
    )
