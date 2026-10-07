"""Cloud upload providers.

Add new providers as modules under this package (e.g. ``cloud/gdrive.py``)
and register them in ``maybe_cloud_upload``.
"""

from pathlib import Path

from .exceptions import CloudUploadError
from .pixeldrain import (
    DEFAULT_UPLOAD_WORKERS,
    create_album_pixeldrain,
    upload_file_pixeldrain,
    upload_folder_to_pixeldrain,
)

__all__ = [
    "CloudUploadError",
    "DEFAULT_UPLOAD_WORKERS",
    "create_album_pixeldrain",
    "maybe_cloud_upload",
    "upload_file_pixeldrain",
    "upload_folder_to_pixeldrain",
]


def maybe_cloud_upload(output_files, config, progress_callback=None):
    """
    If cloud_upload.enabled, upload to the configured provider.
    Returns album_url or None.
    """
    cloud = (config or {}).get("cloud_upload") or {}
    if not cloud.get("enabled"):
        return None

    provider = str(cloud.get("provider") or "pixeldrain").strip().lower()

    album_name = (cloud.get("album_name") or "").strip()
    if not album_name:
        input_folder = ((config or {}).get("input_folder") or "").strip()
        album_name = Path(input_folder).name if input_folder else ""

    if provider == "pixeldrain":
        result = upload_folder_to_pixeldrain(
            output_files,
            api_key=cloud.get("api_key") or "",
            album_name=album_name,
            progress_callback=progress_callback,
            max_workers=cloud.get("max_workers", DEFAULT_UPLOAD_WORKERS),
        )
        return result.get("album_url")

    raise CloudUploadError(f"Unsupported cloud provider: {provider}")
