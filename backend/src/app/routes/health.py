"""Liveness, readiness, and operational metric endpoints."""

from ipaddress import ip_address, ip_network
from secrets import compare_digest
from typing import Mapping

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse

from app.config import settings
from db.database import get_connection
from app.services.embeddings import embedding_health
from app.services.image_processor.ocr import ocr_health
from app.services.vector_store import get_vector_store, vector_store_statistics

router = APIRouter(tags=["operations"])
_PRIVATE_CLIENT_NETWORKS = [
    ip_network("10.0.0.0/8"),
    ip_network("172.16.0.0/12"),
    ip_network("192.168.0.0/16"),
    ip_network("127.0.0.0/8"),
    ip_network("169.254.0.0/16"),
    ip_network("::1/128"),
    ip_network("fc00::/7"),
    ip_network("fe80::/10"),
]


def _is_private_client(host: str) -> bool:
    """Allow metrics without a token only from loopback or private networks."""
    normalized = (host or "").strip().strip("[]").lower()
    if normalized in {"localhost", "testclient", "testserver"}:
        return True
    try:
        address = ip_address(normalized)
    except ValueError:
        return False
    return any(address in network for network in _PRIVATE_CLIENT_NETWORKS)


def metrics_access_allowed(client_host: str, headers: Mapping[str, str]) -> bool:
    """Authorize metrics with a dedicated token or private-network source."""
    configured_token = settings.metrics_token.strip()
    normalized_headers = {key.lower(): value for key, value in headers.items()}
    header_token = normalized_headers.get("x-metrics-token", "").strip()
    bearer_token = normalized_headers.get("authorization", "").removeprefix("Bearer ")
    if configured_token and (
        compare_digest(configured_token, header_token)
        or compare_digest(configured_token, bearer_token.strip())
    ):
        return True
    return settings.metrics_allow_private_networks and _is_private_client(client_host)


def _require_metrics_access(request: Request) -> None:
    """Reject public metrics scraping while keeping the route path stable."""
    client_host = request.client.host if request.client else ""
    if not metrics_access_allowed(client_host, request.headers):
        raise HTTPException(status_code=403, detail="Metrics endpoint is not available.")


@router.get("/health")
def health() -> dict[str, object]:
    try:
        with get_connection() as connection:
            connection.execute("SELECT 1").fetchone()
        vector = get_vector_store().health()
    except Exception as error:
        raise HTTPException(
            status_code=503,
            detail="A required dependency is unavailable.",
        ) from error
    return {
        "status": "healthy",
        "database": "connected",
        "qdrant": (
            "connected"
            if vector.get("provider") == "qdrant"
            else "standby"
        ),
        "embedding": embedding_health(),
        "ocr": ocr_health(),
    }


@router.get("/health/ready")
def readiness() -> dict[str, object]:
    try:
        with get_connection() as connection:
            connection.execute("SELECT 1").fetchone()
        vector = get_vector_store().health()
        if (
            settings.app_environment == "production"
            and vector.get("provider") == "qdrant"
            and vector.get("mode") != "remote"
        ):
            raise RuntimeError("Production requires a remote persistent Qdrant deployment.")
    except Exception as error:
        raise HTTPException(status_code=503, detail="A required dependency is unavailable.") from error
    return {
        "status": "ready",
        "database": "ok",
        "vector_store": {**vector, **vector_store_statistics()},
        "embedding": embedding_health(),
        "ocr": ocr_health(),
    }


def build_metrics_output() -> str:
    """Render tenant-safe aggregate Prometheus metrics."""
    with get_connection() as connection:
        job_rows = connection.execute(
            """SELECT status, COUNT(*) AS count
               FROM ingestion_jobs GROUP BY status"""
        ).fetchall()
        document_count = connection.execute(
            """SELECT COUNT(*) AS count FROM documents WHERE deleted_at IS NULL"""
        ).fetchone()["count"]
        aggregate_row = connection.execute(
            """SELECT COALESCE(SUM(CASE WHEN attempt_count > 1
                           THEN attempt_count - 1 ELSE 0 END), 0) AS retries,
                      COALESCE(SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END), 0)
                           AS permanent_failures,
                      COALESCE(SUM(chunks_created), 0) AS chunks_created,
                      COALESCE(SUM(vector_upsert_failures), 0) AS vector_failures,
                      COALESCE(AVG(extraction_duration_ms), 0) AS extraction_ms,
                      COALESCE(AVG(embedding_duration_ms), 0) AS embedding_ms,
                      COALESCE(AVG(indexing_duration_ms), 0) AS indexing_ms
               FROM ingestion_jobs"""
        ).fetchone()
        lifecycle_rows = connection.execute(
            """SELECT event_type, COUNT(*) AS count
               FROM audit_events
               WHERE event_type IN ('document.delete', 'document.restore',
                                    'document.hard_delete')
               GROUP BY event_type"""
        ).fetchall()
    lines = [
        "# TYPE rag_documents_active gauge",
        "# TYPE rag_ingestion_jobs gauge",
        f"rag_documents_active {document_count}",
    ]
    lines.extend(
        f'rag_ingestion_jobs{{status="{row["status"]}"}} {row["count"]}'
        for row in job_rows
    )
    lines.extend([
        "# TYPE rag_ingestion_retries_total counter",
        "# TYPE rag_ingestion_permanent_failures_total counter",
        "# TYPE rag_chunks_created_total counter",
        "# TYPE rag_vector_upsert_failures_total counter",
        "# TYPE rag_ingestion_stage_duration_ms gauge",
    ])
    lines.extend([
        f'rag_ingestion_retries_total {aggregate_row["retries"]}',
        f'rag_ingestion_permanent_failures_total {aggregate_row["permanent_failures"]}',
        f'rag_chunks_created_total {aggregate_row["chunks_created"]}',
        f'rag_vector_upsert_failures_total {aggregate_row["vector_failures"]}',
        f'rag_ingestion_stage_duration_ms{{stage="extraction"}} {aggregate_row["extraction_ms"]}',
        f'rag_ingestion_stage_duration_ms{{stage="embedding"}} {aggregate_row["embedding_ms"]}',
        f'rag_ingestion_stage_duration_ms{{stage="indexing"}} {aggregate_row["indexing_ms"]}',
    ])
    lines.append("# TYPE rag_document_lifecycle_total counter")
    lines.extend(
        f'rag_document_lifecycle_total{{event="{row["event_type"]}"}} {row["count"]}'
        for row in lifecycle_rows
    )
    return "\n".join(lines) + "\n"


@router.get("/metrics", response_class=PlainTextResponse)
def metrics(request: Request) -> str:
    _require_metrics_access(request)
    return build_metrics_output()
