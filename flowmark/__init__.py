"""FlowMark — batch watermark library."""

from .batch import process_folder, process_image
from .cloud import (
    CloudUploadError,
    create_album_pixeldrain,
    maybe_cloud_upload,
    upload_file_pixeldrain,
    upload_folder_to_pixeldrain,
)
from .config import (
    CONFIG_PATH,
    DEFAULT_CONFIG,
    SCRIPT_DIR,
    SUBSAMPLING_MAP,
    combine_trbl,
    default_workers,
    export_resize_label,
    load_config,
    normalize_position,
    normalize_trbl,
    resolve_path,
    save_config,
    effective_jpeg_options,
)
from .estimate import (
    estimate_export_savings,
    format_bytes,
    format_savings_estimate,
    list_input_images,
)
from .image_ops import (
    add_sticker_watermark,
    add_text_watermark,
    anchor_xy,
    apply_watermarks,
    compress_image,
    resize_image,
)

__all__ = [
    "CONFIG_PATH",
    "DEFAULT_CONFIG",
    "SCRIPT_DIR",
    "SUBSAMPLING_MAP",
    "CloudUploadError",
    "add_sticker_watermark",
    "add_text_watermark",
    "anchor_xy",
    "apply_watermarks",
    "combine_trbl",
    "compress_image",
    "create_album_pixeldrain",
    "default_workers",
    "effective_jpeg_options",
    "estimate_export_savings",
    "export_resize_label",
    "format_bytes",
    "format_savings_estimate",
    "list_input_images",
    "load_config",
    "maybe_cloud_upload",
    "normalize_position",
    "normalize_trbl",
    "process_folder",
    "process_image",
    "resize_image",
    "resolve_path",
    "save_config",
    "upload_file_pixeldrain",
    "upload_folder_to_pixeldrain",
]
