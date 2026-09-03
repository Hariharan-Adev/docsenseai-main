"""Organization-scoped upload storage with traversal-safe resolution."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path, PurePosixPath, PureWindowsPath
from urllib.parse import unquote

from db import database


def organization_storage_prefix(organization_id: str) -> str:
    """Return an opaque, filesystem-safe tenant partition."""
    return sha256(organization_id.encode("utf-8")).hexdigest()


def storage_key_for(organization_id: str, stored_filename: str) -> str:
    """Create an opaque tenant-prefixed key for a plain stored filename."""
    filename = Path(stored_filename).name
    if not filename or filename != stored_filename:
        raise ValueError("Invalid stored filename.")
    return f"{organization_storage_prefix(organization_id)}/{filename}"


def _decoded_storage_key(storage_key: str) -> str:
    """Decode URL-encoded path separators before traversal checks run."""
    decoded = storage_key
    for _ in range(3):
        next_value = unquote(decoded)
        if next_value == decoded:
            break
        decoded = next_value
    return decoded


def resolve_storage_key(storage_key: str) -> Path:
    """Resolve a relative key beneath the upload root.

    Plain filenames remain readable for data migrated from the legacy flat layout.
    """
    decoded_key = _decoded_storage_key(storage_key)
    normalized_key = decoded_key.replace("\\", "/")
    posix_key = PurePosixPath(normalized_key)
    windows_key = PureWindowsPath(decoded_key)
    if (
        not decoded_key
        or "\x00" in decoded_key
        or posix_key.is_absolute()
        or windows_key.is_absolute()
        or windows_key.drive
        or any(part in {"", ".", ".."} for part in posix_key.parts)
    ):
        raise ValueError("Invalid storage key.")

    root = database.UPLOAD_DIRECTORY.resolve()
    candidate = (root / posix_key).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise ValueError("Invalid storage key.") from error
    return candidate


def write_storage_bytes(storage_key: str, content: bytes) -> Path:
    path = resolve_storage_key(storage_key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path
