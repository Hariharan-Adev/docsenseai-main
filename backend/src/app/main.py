"""FastAPI application entry point."""

from threading import Event, Lock, Thread
from fastapi import FastAPI, Request, Response
from uuid import uuid4
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.config import settings
from db.database import initialize_database
from app.routes.auth import router as auth_router
from app.routes.azure_devops import router as azure_devops_router
from app.routes.chat import router as chat_router
from app.routes.collections import router as collections_router
from app.routes.documents import router as documents_router
from app.routes.images import router as images_router
from app.routes.health import router as health_router
from app.routes.ingestion import public_router as public_ingestion_router
from app.routes.ingestion import router as ingestion_router
from app.routes.projects import router as projects_router
from app.routes.search import router as search_router
from app.routes.upload import router as upload_router
from app.services.image_processor.ocr import require_ocr_ready_for_startup
from app.utils.observability import log_event
from app.worker import run_worker

_worker_stop = Event()
_worker_lock = Lock()
_worker_thread: Thread | None = None


def _start_ingestion_worker() -> None:
    """Start one API-owned ingestion worker for this application process."""
    global _worker_thread
    with _worker_lock:
        if _worker_thread is not None and _worker_thread.is_alive():
            return
        _worker_stop.clear()
        _worker_thread = Thread(
            target=run_worker,
            args=(_worker_stop,),
            name="ingestion-worker",
            daemon=True,
        )
        _worker_thread.start()


def _stop_ingestion_worker() -> None:
    """Signal the API-owned ingestion worker during application shutdown."""
    _worker_stop.set()
    thread = _worker_thread
    if thread is not None and thread.is_alive():
        thread.join(timeout=max(2.0, settings.ingestion_poll_seconds + 1.0))


def _request_uses_https(request: Request) -> bool:
    """Honor proxy TLS headers so HSTS is set behind HTTPS terminators."""
    forwarded_proto = request.headers.get("X-Forwarded-Proto", "").split(",", 1)[0]
    return request.url.scheme == "https" or forwarded_proto.strip().lower() == "https"


def apply_security_headers(response: Response, request: Request) -> None:
    """Apply approved browser security headers to every API response."""
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; frame-ancestors 'none'; object-src 'none'; "
        "base-uri 'self'; form-action 'self'",
    )
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    if settings.is_production and _request_uses_https(request):
        response.headers.setdefault(
            "Strict-Transport-Security",
            "max-age=31536000; includeSubDomains",
        )


app = FastAPI(title="Simple RAG API", version="0.1.0")
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=settings.trusted_host_list(),
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list(),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth_router)
app.include_router(azure_devops_router)
app.include_router(public_ingestion_router)
app.include_router(upload_router)
app.include_router(documents_router)
app.include_router(images_router)
app.include_router(ingestion_router)
app.include_router(health_router)
app.include_router(search_router)
app.include_router(chat_router)
app.include_router(collections_router)
app.include_router(projects_router)


@app.on_event("startup")
def startup() -> None:
    """Initialize persistence and start ingestion with the API."""
    settings.validate_production_settings()
    require_ocr_ready_for_startup()
    initialize_database()
    _start_ingestion_worker()


@app.on_event("shutdown")
def shutdown() -> None:
    """Stop the API-owned ingestion worker."""
    _stop_ingestion_worker()


@app.middleware("http")
async def request_observability(request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    apply_security_headers(response, request)
    log_event(
        "http.request",
        request_id=request_id,
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
    )
    return response
