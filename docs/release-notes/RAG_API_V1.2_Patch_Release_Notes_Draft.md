# API Release Notes - v1.2 Patch Draft

Release Date: 03-09-2026
Build Numbers:
Environment: Docsense AI Backend API
Release Owner: Aparna / Adev Tech Corp
Release Type: Backend/API Patch Release

## Summary

This patch release updates the new cloned Docsense AI project with backend, database, and frontend-connected improvements compared with the old project at `C:\Users\aparna_adevtechcorp\Desktop\RAG PROJECT`.

The release introduces project and folder-scoped document organization, improved Azure DevOps integration, saved Azure DevOps connection handling, imported Azure work-item viewing, authenticated document file preview/download, stronger production security validation, protected operational metrics, safer storage-key resolution, and chat latency diagnostics.

The new project also reorganizes backend code from `backend/app` to `backend/src/app` and moves the active SQLite database module from `backend/app/database.py` to `db/database.py`.

## Features and Changes

### Project and Folder Organization

- Added owner-scoped project management APIs.
- Added project-scoped folders.
- Added `project_id` and `folder_id` support for documents, chunks, chat sessions, and chat contexts.
- Added document listing filters by project and folder.
- Added project and folder names to document listing responses.
- Preserved existing unassigned document behavior.
- Added duplicate active project-name prevention for each user and organization.
- Added safe migration handling for legacy duplicate project names before the unique project-name index is applied.

### Azure DevOps Integration

- Replaced the older Azure DevOps configuration API with `/integrations/azure-devops` endpoints.
- Added test-and-save Azure DevOps connection support.
- Added saved Azure DevOps connection retrieval without returning the saved PAT.
- Added Azure DevOps disconnect support.
- Added manual Azure Boards work-item sync.
- Added imported Azure work-item listing from stored Docsense documents without calling Azure live.
- Imported Azure work items are stored as normal Docsense documents and chunks with Azure metadata.
- Save & Sync automatically creates or reuses the `Azure Dev` project and project/type folder scope for imported work items.
- Re-sync avoids duplicate documents for unchanged work items and updates changed content through document/version storage.
- Azure DevOps URLs are generated as clickable links for imported work items.
- Backend errors are returned with safe structured messages containing code, message, and retryable fields.

### Document Preview and Download

- Added authenticated `GET /documents/{document_id}/file`.
- Supports inline preview by default.
- Supports download mode through `download=true`.
- Uses the existing document read access control before serving a file.
- Resolves current-version storage using `storage_key` or legacy `stored_filename`.
- Returns safe 404 responses when the file or storage key is invalid.
- Does not expose internal file paths or storage details.

### Chat and Retrieval

- Chat requests now support project and folder scope.
- Folder scope is validated against the selected project before retrieval.
- Added chat latency diagnostics around total request time, chat-history save time, SQLite hydration, embedding creation, and vector search.
- Added backend logging for chat latency breakdowns.
- Hybrid retrieval continues to combine vector retrieval with local keyword/BM25-style matching over authorized chunks.

### Production Security and Operations

- Added production startup validation for required secrets and deployment settings.
- Added explicit CORS configuration through `CORS_ALLOW_ORIGINS`.
- Added trusted host configuration through `TRUSTED_HOSTS`.
- Added `TrustedHostMiddleware`.
- Added default API security headers:
  - Content-Security-Policy
  - X-Content-Type-Options
  - X-Frame-Options
  - Referrer-Policy
  - Strict-Transport-Security for production HTTPS requests
- Added metrics access protection by private-network access or `METRICS_TOKEN`.
- Changed metrics output to tenant-safe aggregate counters without organization IDs.
- Added `API_BASE_URL`, `METRICS_TOKEN`, and `METRICS_ALLOW_PRIVATE_NETWORKS` configuration.

### Storage Security

- Hardened storage-key resolution for preview, download, and hard-delete flows.
- URL-decoded storage keys are checked before path resolution.
- Rejects absolute paths, Windows drive paths, UNC-style paths, null bytes, empty path segments, current-directory segments, and parent-directory traversal.
- Keeps legacy plain filenames readable for older stored documents.

## API Endpoints Added or Changed

### Azure DevOps

- `POST /integrations/azure-devops/test`
  - Tests and saves Azure DevOps credentials, or re-tests the saved token when no token is supplied.

- `GET /integrations/azure-devops/connection`
  - Returns saved connection state without exposing the saved PAT.

- `POST /integrations/azure-devops/sync`
  - Imports selected Azure Boards work items into Docsense AI document storage and retrieval.

- `DELETE /integrations/azure-devops/connection`
  - Disconnects the saved Azure DevOps connection.

- `GET /integrations/azure-devops/imported-items`
  - Lists already imported Azure Boards work items with search, type filter, state filter, and pagination.

### Documents

- `GET /documents/{document_id}/file`
  - Serves the authenticated user's current document file inline or as a download.

### Projects and Folders

- `POST /projects`
- `GET /projects`
- `GET /projects/{project_id}`
- `PATCH /projects/{project_id}`
- `DELETE /projects/{project_id}`
- `POST /projects/{project_id}/folders`
- `GET /projects/{project_id}/folders`
- `GET /projects/{project_id}/folders/{folder_id}`
- `PATCH /projects/{project_id}/folders/{folder_id}`
- `DELETE /projects/{project_id}/folders/{folder_id}`

### Chat

- `POST /chat`
  - Request payload supports `project_id` and `folder_id`.

- `POST /chat/diagnostics`
  - Diagnostics payload supports `project_id` and `folder_id`.

### Operations

- `GET /metrics`
  - Now requires authorized metrics access and returns aggregate tenant-safe values.

## Database Changes

### Module Location

- Active database module moved from `backend/app/database.py` to `db/database.py`.
- Active SQLite path in the new project is `db/data/rag_new.db`.

### Migration 015 - Projects

- Added `projects`.
- Added `project_id` to:
  - `documents`
  - `chunks`
  - `chat_sessions`
  - `chat_contexts`
- Added project indexes for owner, documents, chunks, and chat sessions.
- Added active project-name uniqueness:
  - `ux_projects_active_name`
  - Scope: organization, user, lower project name
  - Applies only when `deleted_at IS NULL`
- Added duplicate legacy project-name repair before creating the unique index.

### Migration 016 - Project Folders

- Added `folders`.
- Added `folder_id` to:
  - `documents`
  - `chunks`
  - `chat_sessions`
  - `chat_contexts`
- Added active folder-name uniqueness:
  - `ux_folders_active_name`
  - Scope: organization, user, project, lower folder name
  - Applies only when `deleted_at IS NULL`
- Added folder indexes for owner/project, documents, and chunks.
- Existing project documents remain folderless unless moved or imported into a folder.

### Migration 017 - Azure DevOps Connection Persistence

- Added `azure_devops_connections`.
- Stores one active Azure DevOps connection per user and organization.
- Stores:
  - organization URL
  - encrypted PAT
  - visible Azure projects JSON
  - validation checks JSON
  - connected flag
  - last tested timestamp
  - created/updated/deleted timestamps
- Added unique active connection index:
  - `ux_azure_devops_connections_active_user`
- Added owner lookup index:
  - `idx_azure_devops_connections_owner`

### Azure Work-Item Storage Model

- No separate `azure_devops_work_items` table is used in the new patch.
- Imported Azure work items are represented through existing:
  - `documents`
  - `document_versions`
  - `document_contents`
  - `chunks`
  - `projects`
  - `folders`
- Azure metadata is stored in document/chunk source metadata for retrieval and imported-item display.

## Frontend-Connected Changes

- Added an integrations-style Configuration page.
- Added `Add Integration` button.
- Added integration cards for Azure Dev, GitHub, SharePoint, and Google Drive.
- Added Azure Dev configuration page.
- Added `Test Connection` button for Azure DevOps.
- Added `Replace token` action for saved Azure DevOps credentials.
- Added `Save & Sync` button for Azure work-item import.
- Added `View imported items` action after Azure DevOps is connected.
- Added imported work-item table with search, type filter, state filter, refresh, pagination, and expandable details.
- Added imported item details for ID, title, description, and Azure DevOps URL.
- Added GitHub configuration preview UI. This is frontend-only in the inspected patch and is not backed by a live backend persistence API.
- Added document preview modal support for authenticated backend file fetching.

## Configuration Changes

- `API_BASE_URL`
- `CORS_ALLOW_ORIGINS`
- `TRUSTED_HOSTS`
- `METRICS_TOKEN`
- `METRICS_ALLOW_PRIVATE_NETWORKS`
- `QDRANT_LOCAL_PATH` default changed to `db/qdrant_data`

Production deployments must set strong non-placeholder secrets and HTTPS URLs before startup validation will pass.

## Dependency Changes

- Replaced `python-jose`, `ecdsa`, `rsa`, and `pyasn1` usage with `PyJWT`.
- Upgraded `cryptography` from `49.0.0` to `50.0.0`.
- Upgraded `pypdf` from `5.9.0` to `6.16.2`.
- Added security/audit-related packages including `pip_audit`, CycloneDX/package URL support, and supporting dependencies.

## Files Changed - Main Areas

### Backend

- `backend/src/app/config.py`
- `backend/src/app/main.py`
- `backend/src/app/routes/azure_devops.py`
- `backend/src/app/routes/chat.py`
- `backend/src/app/routes/documents.py`
- `backend/src/app/routes/health.py`
- `backend/src/app/routes/projects.py`
- `backend/src/app/services/azure_devops.py`
- `backend/src/app/services/keyword_search.py`
- `backend/src/app/services/rag_diagnostics.py`
- `backend/src/app/services/rag_service.py`
- `backend/src/app/services/storage.py`
- `backend/src/app/services/vector_search.py`

### Database

- `db/database.py`
- `db/models/user_accounts.py`

### Frontend

- `frontend/src/components/ConfigurationPage.tsx`
- `frontend/src/components/DocumentPreviewModal.tsx`
- `frontend/src/components/LibraryPage.tsx`
- `frontend/src/components/ProjectsPage.tsx`
- `frontend/src/components/ui/ErrorBoundary.tsx`
- `frontend/src/context/AppContext.tsx`
- `frontend/src/services/api.ts`
- `frontend/src/styles/globals.css`
- `frontend/src/types/index.ts`

### Tests and Reports

- `backend/tests/test_azure_devops_connector.py`
- `backend/tests/test_deployment_security.py`
- `backend/tests/test_chat.py`
- `backend/tests/test_multitenant_architecture.py`
- `backend/tests/test_projects.py`
- `backend/tests/test_rag_diagnostic_endpoint.py`
- `backend/tests/test_rag_diagnostics.py`
- `backend/tests/test_security_limits.py`
- `security-review-report.md`

## Testing

The comparison identified updated and added backend tests for Azure DevOps, deployment security, chat, multitenant behavior, projects, diagnostics, and security limits.

Current-turn test execution was not performed during this diff comparison. Before final release approval, run:

- Backend unit/regression suite from `backend`
- Frontend production build from `frontend`
- Security/audit checks approved for the release
- Manual Azure DevOps connection, Save & Sync, imported-items, project/folder upload, document preview, and document download smoke tests

## Deployment Steps

1. Back up the current SQLite database.
2. Back up uploaded document storage.
3. Back up Qdrant or the configured vector store.
4. Deploy the new backend code layout using `backend/src/app` and top-level `db`.
5. Confirm import paths and service startup commands use the new layout.
6. Configure production environment variables:
   - `APP_ENVIRONMENT=production`
   - `CORS_ALLOW_ORIGINS`
   - `TRUSTED_HOSTS`
   - `API_BASE_URL`
   - `FRONTEND_BASE_URL`
   - strong JWT and rate-limit secrets
   - metrics access settings
7. Run database startup migrations through migration 017.
8. Verify that project, folder, and Azure DevOps connection tables/indexes exist.
9. Verify that `/health` and `/health/ready` pass.
10. Verify that `/metrics` is blocked from public access and allowed only through approved access.
11. Test Azure DevOps connection with a PAT.
12. Run Save & Sync for a small Azure project/type/state selection.
13. Verify that imported work items appear under the Azure Dev project/folder scope.
14. Verify that imported work items are searchable in chat.
15. Verify document preview and download from the frontend.

## Post-Deployment Validation

Confirm the following:

- Existing users can log in.
- Existing uploaded documents still list correctly.
- Existing unassigned documents remain available.
- Project creation, rename, duplicate-name handling, and delete behavior work.
- Folder creation, rename, duplicate-name handling, and delete behavior work.
- Uploading into a project/folder applies the expected scope.
- Chat retrieval respects selected project/folder scope.
- Azure DevOps connection does not expose the saved PAT.
- Azure DevOps connection can be replaced or disconnected.
- Save & Sync imports selected Azure work items.
- Re-running Save & Sync does not duplicate unchanged work items.
- Imported Azure items display only safe allowlisted details.
- Document preview opens through the authenticated file endpoint.
- Document download uses the same access-controlled endpoint.
- Metrics do not expose organization IDs or customer content.
- Storage-key traversal attempts return safe failures.

## Rollback Plan

1. Stop the backend API and worker.
2. Stop frontend traffic to the new patch if the UI was deployed.
3. Restore the pre-deployment SQLite backup if schema rollback is required.
4. Restore the matching uploaded-file storage backup if files were changed after deployment.
5. Restore the matching Qdrant/vector-store backup if imported or reindexed content must be reverted.
6. Deploy the previous known-good backend and frontend build together.
7. Restart backend API and worker.
8. Verify login, document listing, upload, chat, health, and existing document access.

Do not manually delete Azure-imported documents, project rows, folder rows, or Azure connection rows as a rollback shortcut. Use a reviewed backup restore or an approved cleanup plan.

## Known Issues and Limitations

- The GitHub integration page is a frontend preview in the inspected patch and does not have confirmed backend persistence or live GitHub sync.
- Azure imported work items use existing document/version/chunk storage rather than dedicated Azure work-item tables.
- True nested folder hierarchy is not implemented in the database; the available schema supports one project level and one folder level.
- Release validation still requires fresh backend test, frontend build, and manual smoke-test evidence.

## Release Result

Status: Draft patch release notes prepared from old-project to new-project diff.

The release should not be promoted until:

- Database migrations through 017 complete successfully.
- Backend tests pass.
- Frontend build passes.
- Azure DevOps connection and Save & Sync are smoke tested.
- Imported Azure work-item viewing is smoke tested.
- Project/folder document scope is smoke tested.
- Authenticated document preview and download are smoke tested.
- Production security settings are configured and startup validation passes.
