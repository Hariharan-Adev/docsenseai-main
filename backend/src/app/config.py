"""Application settings loaded from .env."""

from urllib.parse import urlparse

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_LOCAL_CORS_ORIGINS = [
    "http://127.0.0.1:5173",
    "http://localhost:5173",
    "http://127.0.0.1:5174",
    "http://localhost:5174",
    "https://docsenseai.recezy.ai",
    "http://192.168.1.235",
]
_LOCAL_TRUSTED_HOSTS = [
    "127.0.0.1",
    "localhost",
    "testserver",
    "docsenseai.recezy.ai",
    "192.168.1.235",
]
_PLACEHOLDER_VALUES = {
    "",
    "change-me",
    "change-me-locally",
    "paste_key_1_here",
    "paste_brevo_smtp_key_here",
    "paste_brevo_smtp_login_here",
    "replace-with-secure-token",
    "replace-with-production-secret",
}


def _csv_values(value: str) -> list[str]:
    """Parse comma-separated environment values while ignoring blanks."""
    return [item.strip() for item in value.split(",") if item.strip()]


def _is_placeholder(value: str) -> bool:
    """Detect unset or template secret values before production startup."""
    return value.strip().lower() in _PLACEHOLDER_VALUES


def _url_host(value: str) -> str:
    """Return a parsed URL host or an empty string for malformed values."""
    return urlparse(value).hostname or ""


class Settings(BaseSettings):
    """Keep secrets outside source code."""

    groq_api_key: str = ""
    groq_model: str = ""
    groq_vision_model: str = "qwen/qwen3.6-27b"
    llm_provider: str = ""
    azure_openai_endpoint: str = ""
    azure_openai_api_key: str = ""
    azure_openai_api_version: str = "2024-12-01-preview"
    azure_openai_rag_deployment: str = ""
    azure_openai_utility_deployment: str = ""
    enable_image_vision: bool = True
    jwt_secret_key: str = ""
    access_token_expire_minutes: int = 30
    rate_limit_salt: str = ""
    chat_requests_per_hour: int = 20
    search_requests_per_hour: int = 60
    uploads_per_hour: int = 25
    password_reset_requests_per_hour: int = 5
    password_reset_token_minutes: int = Field(default=30, ge=5, le=120)
    smtp_host: str = ""
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    smtp_from_name: str = "Docsense AI"
    smtp_use_tls: bool = True
    smtp_timeout_seconds: float = Field(default=10.0, ge=1.0, le=60.0)
    frontend_base_url: str = "http://localhost:5173"
    api_base_url: str = "http://127.0.0.1:8000"
    cors_allow_origins: str = ""
    trusted_hosts: str = ""
    metrics_token: str = ""
    metrics_allow_private_networks: bool = True
    groq_calls_per_day: int = 50
    groq_daily_token_budget: int = 200000
    groq_daily_cost_cap_usd: float = 5.0
    groq_prompt_cost_per_million: float = 0.0
    groq_completion_cost_per_million: float = 0.0
    max_folder_files: int = 25
    max_file_size_mb: int = 25
    max_folder_total_size_mb: int = 200
    max_concurrent_file_processing: int = 3
    max_zip_upload_mb: int = 50
    max_zip_extracted_mb: int = 250
    max_zip_files: int = 100
    max_zip_compression_ratio: float = 100.0
    max_office_archive_entries: int = 10000
    max_office_uncompressed_mb: int = 250
    max_office_compression_ratio: float = 100.0
    max_pdf_pages: int = 1000
    max_powerpoint_slides: int = 1000
    max_workbook_sheets: int = 250
    max_workbook_rows: int = 200000
    parser_timeout_seconds: float = 120.0
    tesseract_cmd: str = ""
    ocr_required_languages: str = "eng"
    include_hidden_worksheets: bool = True
    include_very_hidden_worksheets: bool = False
    default_organization_name: str = "Default Organization"
    ingestion_max_attempts: int = 5
    ingestion_lock_seconds: int = 300
    ingestion_poll_seconds: float = 1.0
    ingestion_backoff_base_seconds: float = 2.0
    ingestion_backoff_max_seconds: float = 3600.0
    ingestion_pipeline_version: str = "v1"
    vector_store: str = ""
    vector_store_provider: str = "qdrant"
    vector_store_rollback_dual_write: bool = False
    qdrant_url: str = ""
    qdrant_api_key: str = ""
    qdrant_collection: str = "rag_chunks"
    qdrant_mode: str = "auto"
    qdrant_prefer_grpc: bool = False
    qdrant_path: str = ""
    qdrant_local_path: str = "db/qdrant_data"
    embedding_provider: str = "local"
    local_embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dimension: int = 384
    embedding_batch_size: int = 64
    embedding_model_version: str = "all-MiniLM-L6-v2"
    embedding_model_load_timeout_seconds: float = Field(default=60.0, ge=1.0, le=600.0)
    chat_follow_up_context_minutes: int = Field(default=30, ge=1, le=360)
    rag_retrieval_limit: int = Field(default=15, ge=1, le=100)
    rag_final_context_limit: int = Field(default=5, ge=1, le=20)
    rag_final_context_token_budget: int = Field(default=6000, ge=256, le=32000)
    rag_complementary_context_limit: int = Field(default=3, ge=1, le=10)
    rag_complementary_min_score: float = Field(default=0.15, ge=0.0, le=1.0)
    rag_neighbor_expansion_min_score: float = Field(default=0.50, ge=0.0)
    rag_neighbor_expansion_max_neighbors: int = Field(default=2, ge=0, le=4)
    # A weak-evidence floor for vector candidates; source evidence still decides grounding.
    rag_min_score: float = Field(default=0.30, ge=-1.0, le=1.0)
    rag_retrieval_mode: str = "hybrid"
    rag_vector_candidate_limit: int = Field(default=30, ge=1, le=200)
    rag_keyword_candidate_limit: int = Field(default=30, ge=1, le=200)
    rag_rrf_k: int = Field(default=60, ge=1, le=1000)
    rag_structured_result_limit: int = Field(default=100, ge=1, le=1000)
    rag_diagnostics_enabled: bool = False
    embedded_ocr_max_images_per_document: int = Field(default=25, ge=0, le=500)
    embedded_ocr_max_images_per_page: int = Field(default=5, ge=0, le=100)
    embedded_ocr_max_pixels: int = Field(default=16_000_000, ge=1, le=100_000_000)
    embedded_ocr_max_decoded_bytes: int = Field(default=20_000_000, ge=1, le=200_000_000)
    opensearch_url: str = ""
    opensearch_username: str = ""
    opensearch_password: str = ""
    opensearch_index: str = "rag_chunks"
    hard_delete_enabled: bool = False
    app_environment: str = "development"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def is_production(self) -> bool:
        """Centralize production checks so startup validation is consistent."""
        return self.app_environment.strip().lower() == "production"

    def cors_origin_list(self) -> list[str]:
        """Use environment CORS origins when supplied; keep local defaults for dev."""
        configured = _csv_values(self.cors_allow_origins)
        return configured or list(_LOCAL_CORS_ORIGINS)

    def trusted_host_list(self) -> list[str]:
        """Use explicit trusted hosts while preserving local/test access by default."""
        configured = _csv_values(self.trusted_hosts)
        return configured or list(_LOCAL_TRUSTED_HOSTS)

    def validate_production_settings(self) -> None:
        """Fail fast when production settings would expose deployment controls."""
        if not self.is_production:
            return

        problems: list[str] = []
        self._validate_required_secret("JWT_SECRET_KEY", self.jwt_secret_key, problems)
        self._validate_required_secret("RATE_LIMIT_SALT", self.rate_limit_salt, problems)
        self._validate_metrics_settings(problems)
        self._validate_production_cors(problems)
        self._validate_production_trusted_hosts(problems)
        self._validate_public_url("FRONTEND_BASE_URL", self.frontend_base_url, problems)
        self._validate_public_url("API_BASE_URL", self.api_base_url, problems)
        self._validate_provider_settings(problems)

        if self.rag_diagnostics_enabled:
            problems.append("RAG_DIAGNOSTICS_ENABLED must be false in production")

        if (
            self.vector_store_provider.strip().lower() == "qdrant"
            and self.qdrant_mode.strip().lower() != "remote"
        ):
            problems.append("QDRANT_MODE must be remote in production")
        if self.qdrant_url:
            self._validate_public_url("QDRANT_URL", self.qdrant_url, problems)

        if problems:
            raise RuntimeError(
                "Production configuration is not deployment safe: "
                + "; ".join(problems)
            )

    def _validate_required_secret(
        self, name: str, value: str, problems: list[str], minimum_length: int = 32
    ) -> None:
        """Require non-template secret material with enough entropy headroom."""
        if _is_placeholder(value) or len(value.strip()) < minimum_length:
            problems.append(
                f"{name} must be set to a non-placeholder value of at least "
                f"{minimum_length} characters"
            )

    def _validate_metrics_settings(self, problems: list[str]) -> None:
        """Require either a dedicated metrics credential or private-network access."""
        if self.metrics_token:
            self._validate_required_secret("METRICS_TOKEN", self.metrics_token, problems)
            return
        if not self.metrics_allow_private_networks:
            problems.append(
                "METRICS_TOKEN is required when METRICS_ALLOW_PRIVATE_NETWORKS is false"
            )

    def _validate_production_cors(self, problems: list[str]) -> None:
        """Reject wildcard and non-HTTPS origins before CORS is enabled."""
        configured = _csv_values(self.cors_allow_origins)
        if not configured:
            problems.append("CORS_ALLOW_ORIGINS must be explicitly set in production")
            return
        for origin in configured:
            parsed = urlparse(origin)
            if "*" in origin:
                problems.append("CORS_ALLOW_ORIGINS cannot contain wildcards in production")
            if parsed.scheme != "https" or not parsed.netloc:
                problems.append(
                    f"CORS origin {origin!r} must be an absolute HTTPS origin in production"
                )

    def _validate_production_trusted_hosts(self, problems: list[str]) -> None:
        """Require exact trusted hosts so Host header attacks are blocked."""
        configured = _csv_values(self.trusted_hosts)
        if not configured:
            problems.append("TRUSTED_HOSTS must be explicitly set in production")
            return
        for host in configured:
            if "*" in host:
                problems.append("TRUSTED_HOSTS cannot contain wildcards in production")
            if "://" in host or "/" in host:
                problems.append(f"Trusted host {host!r} must be a hostname, not a URL")

    def _validate_public_url(
        self, name: str, value: str, problems: list[str], require_https: bool = True
    ) -> None:
        """Validate deployment URLs used in redirects, links, and service clients."""
        parsed = urlparse(value)
        if not parsed.scheme or not parsed.netloc:
            problems.append(f"{name} must be an absolute URL in production")
            return
        if require_https and parsed.scheme != "https":
            problems.append(f"{name} must use HTTPS in production")
        if not _url_host(value):
            problems.append(f"{name} must include a valid host")

    def _validate_provider_settings(self, problems: list[str]) -> None:
        """Validate only the configured LLM provider's production credentials."""
        provider = self.llm_provider.strip().lower()
        if provider == "azure_openai":
            self._validate_required_secret(
                "AZURE_OPENAI_API_KEY", self.azure_openai_api_key, problems
            )
            self._validate_public_url(
                "AZURE_OPENAI_ENDPOINT", self.azure_openai_endpoint, problems
            )
            if _is_placeholder(self.azure_openai_rag_deployment):
                problems.append("AZURE_OPENAI_RAG_DEPLOYMENT must be set in production")
            if _is_placeholder(self.azure_openai_utility_deployment):
                problems.append("AZURE_OPENAI_UTILITY_DEPLOYMENT must be set in production")
        elif provider == "groq":
            self._validate_required_secret("GROQ_API_KEY", self.groq_api_key, problems)


settings = Settings()
