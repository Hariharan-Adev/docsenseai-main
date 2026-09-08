# Docsense AI — Project Checklist

Prepared: 8 September 2026

Scope: React/Vite frontend, FastAPI backend, ingestion worker, SQLite, Qdrant, and Azure DevOps integration.

All items start unchecked. This is a verification checklist, not a completed audit or deployment approval. Check an item only after recording evidence for the release being reviewed. Record an explanation for anything not applicable.

Release/version: __________  Environment: __________  Review owner: __________

## 1. Requirements and scope

- [ ] Confirm the release requirements and acceptance criteria.
- [ ] Identify affected features and existing behavior that must be preserved.
- [ ] Review the worktree and separate intended release changes from unrelated work.
- [ ] Assign an owner to each applicable checklist section.

## 2. Authentication and access

- [ ] Verify login with valid credentials and safe errors for invalid credentials.
- [ ] Verify protected APIs reject missing, invalid, and expired tokens.
- [ ] Verify logout and session expiry behavior.
- [ ] Verify password-reset email delivery, token expiry, and prevention of token reuse.
- [ ] Verify tenant isolation using users from different organizations.
- [ ] Verify private, organization-visible, and explicitly shared document permissions.
- [ ] Verify member, owner, manage-grant, and administrator permissions on mutations.

## 3. Projects and folders

- [ ] Verify project creation, listing, updating, and deletion according to supported behavior.
- [ ] Verify blank, duplicate, and invalid project names are handled consistently.
- [ ] Verify folder creation and document assignment within the supported hierarchy.
- [ ] Verify project/folder selection scopes document lists and chat correctly.
- [ ] Verify unauthorized project/folder IDs cannot expose or modify another user's data.

## 4. Uploads and background processing

- [ ] Verify each supported document type with representative sample files.
- [ ] Verify scanned documents and image extraction with the deployed OCR installation.
- [ ] Verify spreadsheet/CSV extraction preserves sheet, row, and table relationships.
- [ ] Verify empty, corrupt, unsupported, oversized, and unsafe files fail safely.
- [ ] Verify filename sanitization, ZIP limits, and protection against unsafe archive paths.
- [ ] Verify uploads return a queued job and the UI shows processing, success, and failure states.
- [ ] Verify the worker completes extraction, chunking, embedding, and indexing.
- [ ] Verify retries, cancellation, duplicate submissions, and recovery after worker restart.
- [ ] Verify partial ingestion failures do not publish an incomplete current version.

## 5. Document lifecycle

- [ ] Verify authorized document preview and download, including authentication errors.
- [ ] Verify duplicate-document handling and immutable version creation.
- [ ] Verify switching to a completed version updates retrieval consistently.
- [ ] Verify deletion removes documents from normal lists and retrieval immediately.
- [ ] Verify restore behavior and restrictions on current-version deletion and hard deletion.
- [ ] Verify SQLite records, stored files, and Qdrant vectors remain consistent.

## 6. RAG answers and chat

- [ ] Evaluate factual, broad-summary, follow-up, and differently phrased questions.
- [ ] Evaluate spreadsheet totals, filters, comparisons, and multi-sheet questions against known answers.
- [ ] Verify answers use authorized sources within the selected scope and document version.
- [ ] Verify citations identify the supporting document and relevant location accurately.
- [ ] Verify unavailable information produces a clear insufficient-evidence response.
- [ ] Verify malicious instructions inside documents cannot override application rules or expose data.
- [ ] Verify chat history is saved, reopened, and isolated between users.
- [ ] Measure cold and warm response times separately, including retrieval and provider time.

## 7. Azure DevOps integration

- [ ] Verify valid configuration and safe handling of invalid or expired credentials.
- [ ] Verify personal access tokens remain hidden from UI responses and logs.
- [ ] Verify Save & Sync imports the selected work items into the correct project/type organization.
- [ ] Verify repeated sync does not create unintended duplicates and updates changed items correctly.
- [ ] Verify imported items can be viewed and retrieved only by authorized users.
- [ ] Verify connection failures and partial sync failures show actionable, safe messages.

## 8. Frontend experience

- [ ] Verify navigation, dashboard, document library, projects, configuration, and chat flows.
- [ ] Verify loading, empty, success, error, and retry states.
- [ ] Verify light/dark themes and usable layouts at desktop and mobile widths.
- [ ] Verify keyboard navigation, visible focus, form labels, contrast, and modal behavior.
- [ ] Verify direct-page refresh, file preview, and downloads in the target browsers.

## 9. Security and configuration

- [ ] Review authentication, authorization, parameterized queries, and safe storage-path resolution.
- [ ] Verify production secrets are strong, privately stored, and absent from source, bundles, and logs.
- [ ] Verify production environment validation, allowed origins, trusted hosts, HTTPS, and rate limits.
- [ ] Verify errors and diagnostics do not expose document text, prompts, credentials, or internal paths.
- [ ] Verify metrics access is controlled and RAG diagnostics are disabled unless explicitly approved.
- [ ] Scan backend and frontend dependencies; resolve or formally assess release-blocking findings.
- [ ] Verify backend configuration precedence and the actual browser API URL after publication.
- [ ] Verify public frontend `app-config.ini` contains only public settings.

## 10. Tests and engineering workflow

- [ ] Follow [the engineering loop](ENGINEERING_LOOP.md) for code changes: implementation, validation, root-cause patching when needed, retesting, and security review.
- [ ] Record focused regression tests and the applicable full backend test results.
- [ ] Verify backend dependency consistency and a successful frontend production build.
- [ ] Run representative end-to-end flows in the target environment using approved test data.
- [ ] Return failed tests or security findings to the Root Cause Patch Agent and verify the correction.
- [ ] Record skipped tests, remaining defects, and evidence; do not count unrun checks as passed.

## 11. Deployment and recovery

- [ ] Confirm server prerequisites, network access, persistent storage, and service permissions.
- [ ] Configure persistent production Qdrant and verify backend connectivity.
- [ ] Configure API and ingestion worker services to start automatically and recover after failure.
- [ ] Verify frontend hosting, reverse-proxy routes, upload limits, and request timeouts.
- [ ] Verify health/readiness endpoints and actual login, upload, processing, and chat after deployment.
- [ ] Back up SQLite, uploaded files, and Qdrant consistently; test restoration in an isolated environment.
- [ ] Review database migration compatibility and prepare a tested rollback procedure.
- [ ] Verify monitoring and alerts for API errors, stalled jobs, provider failures, and storage capacity.
- [ ] Record the deployed version, configuration changes, deployment owner, and recovery contacts.

## 12. Documentation and release sign-off

- [ ] Complete the dated implementation report and proposed commit message.
- [ ] Update affected API contracts, request/response examples, and authentication/error documentation.
- [ ] Update affected database tables, relationships, migrations, and reindexing guidance.
- [ ] Update frontend design documentation when UI behavior or appearance changes.
- [ ] Record release notes, known limitations, operating instructions, and rollback steps.
- [ ] Obtain release-owner sign-off after applicable checks pass and exceptions are documented.

## Evidence and exceptions

Add one row per verified item or unresolved issue. Keep secrets and private document content out of evidence.

| Section / checklist item | Owner | Result: Pass / Fail / Pending / N/A | Evidence and date | Issue / next action |
| --- | --- | --- | --- | --- |
| | | Pending | | |

Release decision: Pending / Approved / Blocked  
Approved by: __________  Date: __________

## Project references

- [Project overview](../README.md)
- [Backend behavior and lifecycle](../backend/README.md)
- [Engineering workflow](ENGINEERING_LOOP.md)
- [Publish-time configuration](configuration.md)

Preparation involved documentation and file-structure review only. No application tests, security scans, or live deployment checks were run to produce this checklist.
