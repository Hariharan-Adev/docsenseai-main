"""Azure DevOps connection validation helpers."""

from base64 import b64encode
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

PROJECTS_API_VERSIONS = ("7.2", "7.1")
MAX_AZURE_MESSAGE_LENGTH = 300


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
