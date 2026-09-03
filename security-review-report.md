# Deployment Security Review Report

Date: 2026-08-31
Scope: Continued deployment security remediation for the local RAG project checkout.
Mode: Authorized local remediation. No deployment performed. No commit created. Existing `.env` secret values were not read or modified.

## Revised Deployment Verdict

PASS - GO FOR DEPLOYMENT SECURITY GATE

Deployment-blocking dependency advisories were remediated and `pip-audit -r backend/requirements.txt` now reports no known vulnerabilities. The independent authentication/authorization review for document preview/download, path traversal, and tenant isolation is complete with source and regression-test evidence.

Operational deployment is still conditional on supplying production-safe environment values, preserving the approved reverse-proxy/TLS setup, and accepting or separately remediating the non-blocking residual risks listed below. No deployment or commit was performed.

## Engineering Loop

1. Implementation Agent: Replaced vulnerable backend dependency pins, migrated HS256 JWT handling from `python-jose` to PyJWT, tightened storage-key path validation, and added focused authorization/path traversal tests.
2. Test Validation Agent: Ran focused dependency, PDF, authentication, upload, and tenant-isolation tests.
3. Root Cause Patch Agent: No follow-up code patch was required after focused tests passed.
4. Retest Verification Agent: Re-ran grouped requested suites, full backend discovery, dependency audit, frontend audit/build, `pip check`, and `git diff --check`.
5. Security Review Agent: Independently reviewed dependency exposure, document preview/download authorization, path traversal controls, and tenant isolation evidence.
6. Final Documentation Agent: Updated this report with compatibility analysis, before/after audit results, evidence, commands, residual risks, and final verdict.
7. Commit Message Agent: Suggested commit message included below.
8. API Documentation Agent: Documented API-visible behavior below.
9. Database Documentation Agent: Documented that no schema changes were made.
10. Frontend Design Documentation Agent: Documented that this phase made no frontend design changes.

## Dependency Remediation

| Package | Before | After | Relationship | Application usage | Compatibility notes |
|---|---:|---:|---|---|---|
| `cryptography` | 49.0.0 | 50.0.0 | Direct dependency | Imported by `app.services.azure_devops` for Fernet PAT encryption/decryption. | Existing Fernet APIs are still exercised by Azure DevOps connector tests. |
| `h2` | 4.4.0 | 4.4.1 | Direct dependency | No imports found in `backend/src`, `backend/tests`, `db`, or frontend code. | Patch-level upgrade only; no app API usage identified. |
| `pypdf` | 5.9.0 | 6.15.0 | Direct dependency | Imported by PDF parsing/layout/source-extraction services. | Existing usage is limited to `PdfReader(...).pages`, `page.extract_text()`, layout extraction, visitor callbacks, and optional `page.images`; focused parser tests passed. |
| `python-jose` | 3.5.0 | Removed | Direct dependency | Previously used only for HS256 JWT encode/decode. | Replaced with PyJWT while preserving `sub`, `org`, `exp`, HS256, and bearer-token behavior. |
| `ecdsa` | 0.19.2 | Removed | Transitive via `python-jose`; also pinned directly | No app imports found. | `pip-audit` listed no fixed version, so the root cause was removed by replacing `python-jose`. |
| `rsa` | 4.9.1 | Removed | Transitive via `python-jose`; also pinned directly | No app imports found. | Removed with the unused `python-jose` chain. |
| `pyasn1` | 0.6.4 | Removed | Transitive via `python-jose`/`rsa`; also pinned directly | No app imports found. | Removed with the unused `python-jose` chain. |
| `PyJWT` | Not present | 2.13.0 | New direct dependency | Imported by `app.auth` for JWT encode/decode. | Supports existing HS256 encode/decode and datetime `exp` behavior; auth tests passed. |

Availability checks found `cryptography` 50.0.1, `h2` 4.4.1, `pypdf` 6.16.2, and PyJWT 2.13.0 available. The selected plan used the smallest versions needed by the verified advisories: `cryptography==50.0.0`, `h2==4.4.1`, `pypdf==6.15.0`, plus PyJWT to remove the no-fixed-version `ecdsa` path.

## Pip Audit Results

Before remediation, `pip-audit -r backend/requirements.txt` reported 40 advisories:

| Package | Vulnerable version | Advisory coverage | Fixed version used |
|---|---:|---|---:|
| `cryptography` | 49.0.0 | PYSEC-2026-3552 | 50.0.0 |
| `h2` | 4.4.0 | PYSEC-2026-3628 | 4.4.1 |
| `pypdf` | 5.9.0 | Multiple PYSEC-2026 and GHSA advisories, highest listed fix 6.15.0 | 6.15.0 |
| `ecdsa` | 0.19.2 | PYSEC-2026-1325, no fixed version listed | Removed by replacing `python-jose` |

After remediation:

`.\venv\Scripts\python.exe -m pip_audit -r requirements.txt --cache-dir .\.pip-audit-cache --disable-pip --no-deps --progress-spinner off`

Result: exit 0, `No known vulnerabilities found`.

## Independent Authorization Review Evidence

### A. Document Preview And Download

- Every `GET /documents/{document_id}/file` request uses `current_user: dict[str, object] = Depends(get_current_user)`, so bearer-token authentication is required before route body execution.
- The route calls `require_document(connection, document_id, current_user)` before reading `document_versions` or resolving any storage key.
- `require_document()` scopes by `organization_id`, active document state, owner/shared/organization visibility, and returns the same 404 message for all denials.
- New regression evidence in `backend/tests/test_multitenant_architecture.py` verifies owner preview and download work, inline and attachment responses share authorization, same-tenant unshared user is denied, cross-tenant user is denied, modified document IDs are denied, denied responses omit filename/body/storage metadata, and unauthorized requests do not call `resolve_storage_key()`.

### B. Path Traversal

- `resolve_storage_key()` now decodes URL-encoded values, normalizes mixed separators, rejects empty/null-byte keys, rejects `..`, `.`, empty path segments, absolute POSIX paths, Windows drive paths, and UNC/absolute Windows paths, then verifies the final resolved path remains under `UPLOAD_DIRECTORY`.
- Legacy flat-file fallback remains supported for plain filenames and is still resolved under the configured upload root.
- `storage_key_for()` continues to use a SHA-256 organization prefix; tests verify raw organization IDs are not present in storage keys.
- New regression evidence in `backend/tests/test_security_limits.py` covers `..`, backslash traversal, absolute paths, Windows drive paths, UNC paths, encoded traversal, and mixed separators.

### C. Tenant Isolation

- Test fixtures include two organizations (`org-a`, `org-b`) and at least two users in `org-a`.
- Direct object-reference tests cover the owner, a same-tenant unshared user, and a cross-tenant user.
- Modified-ID requests return generic 404 without disclosing document names, paths, existence, body, or storage metadata.

No confirmed authorization gap remains in the reviewed preview/download and storage-key scope.

## Commands And Results

| Command | Result |
|---|---|
| `.\venv\Scripts\python.exe -m pip show pip-audit` | Exit 0; `pip-audit` 2.10.1 is installed. |
| `.\venv\Scripts\python.exe -m pip index versions cryptography` | Available: 50.0.1 latest; selected 50.0.0 as minimum advisory fix. |
| `.\venv\Scripts\python.exe -m pip index versions h2` | Available: 4.4.1 latest; selected 4.4.1. |
| `.\venv\Scripts\python.exe -m pip index versions pypdf` | Available: 6.16.2 latest; selected 6.15.0 as minimum version resolving the listed advisories. |
| `.\venv\Scripts\python.exe -m pip index versions PyJWT` | Available: 2.13.0 latest; selected 2.13.0. |
| `.\venv\Scripts\python.exe -m pip install -r requirements.txt` | Exit 0; installed updated pins. |
| `.\venv\Scripts\python.exe -m pip uninstall -y python-jose ecdsa rsa pyasn1` | Exit 0; removed obsolete local packages from the venv. |
| `.\venv\Scripts\python.exe -m pip check` | Exit 0; no broken requirements found. |
| `.\venv\Scripts\python.exe -m pip_audit -r requirements.txt --cache-dir .\.pip-audit-cache --disable-pip --no-deps --progress-spinner off` | First post-change run failed due local proxy refusal; escalated rerun exited 0 with no known vulnerabilities. |
| `.\venv\Scripts\python.exe -m unittest tests.test_security_limits` | 4 tests OK. |
| `.\venv\Scripts\python.exe -m unittest tests.test_document_parsers` | 29 tests OK. |
| `.\venv\Scripts\python.exe -m unittest tests.test_auth_password_reset tests.test_upload` | 4 tests OK. |
| `.\venv\Scripts\python.exe -m unittest tests.test_multitenant_architecture` | 19 tests OK. |
| `.\venv\Scripts\python.exe -m unittest tests.test_deployment_security tests.test_security_limits tests.test_auth_password_reset tests.test_upload tests.test_zip_upload tests.test_folder_uploads tests.test_rag_hybrid_security tests.test_rag_prompt_injection tests.test_azure_devops_connector tests.test_multitenant_architecture` | 71 tests OK. |
| `.\venv\Scripts\python.exe -m unittest discover` | 389 tests OK in 400.718s. |
| `npm audit` | Exit 0; found 0 vulnerabilities. |
| `npm run build` | Exit 0; production build passed. Vite warned one JS chunk is larger than 500 kB. |
| `git diff --check` | Exit 0; whitespace OK. Git emitted LF-to-CRLF warnings. |

## New Or Updated Tests

- `backend/tests/test_security_limits.py`: expanded storage-key traversal and tenant-prefix regression coverage.
- `backend/tests/test_multitenant_architecture.py`: expanded current-file preview/download authorization coverage for same-tenant unshared users, cross-tenant users, modified IDs, metadata non-disclosure, and authorization-before-storage behavior.

## Remaining Risks

- Access tokens remain short-lived but not revocable; this phase preserved existing authentication behavior as requested.
- Metrics private-network enforcement depends on correct reverse-proxy/network placement. A dedicated metrics token remains recommended for production.
- HSTS depends on production HTTPS scheme or trusted `X-Forwarded-Proto: https`; the proxy must preserve TLS scheme correctly.
- CSP is conservative for API responses. If FastAPI later serves frontend assets, CSP may need explicit asset/connect directives.
- RAG source text and follow-up context retention remain a policy/data-governance review item.
- `pip-audit` was run against `backend/requirements.txt` with `--no-deps` as requested for the pinned manifest. Consider adding hashes or a compiled lock process in CI.

## API Documentation

No routes were renamed or removed.

| Surface | Behavior |
|---|---|
| Authentication internals | JWT encode/decode now uses PyJWT instead of `python-jose`; token claims, HS256 algorithm, bearer auth dependency, and error behavior are preserved. |
| `GET /documents/{document_id}/file` | Preview and download behavior are unchanged for authorized users. Unauthorized same-tenant, cross-tenant, and nonexistent document IDs return the same generic 404 before storage lookup. |
| Storage-key resolution | API behavior is unchanged for valid stored files. Invalid stored keys now reject encoded traversal, mixed separators, absolute paths, Windows drive paths, UNC paths, null bytes, and empty path segments. |
| Production hardening from prior phase | CORS, TrustedHost, security headers, `/metrics` protection, and startup validation remain in effect. |

## Database Documentation

No database schema, migration, table, index, or stored data format was changed in this phase.

Existing stored `document_versions.storage_key` values continue to resolve when they are valid tenant-prefixed keys or valid legacy flat filenames under the upload root. Invalid legacy keys that rely on traversal or absolute paths are now rejected before filesystem access.

## Frontend Design Documentation

No frontend UI or design behavior changed in this phase.

The prior production ErrorBoundary hardening remains in place: production renders a generic error message and avoids logging raw error objects or component stacks.

## Commit Message

```text
security: resolve deployment dependency and file access blockers

- upgrade vulnerable backend dependency pins and replace python-jose with PyJWT
- remove the ecdsa dependency path with no fixed version
- reject encoded, Windows, UNC, and mixed-separator storage traversal keys
- add preview/download authorization and tenant-isolation regressions
- document clean dependency audit and deployment security review evidence
```
