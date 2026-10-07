"""Config load/save, path helpers, and defaults."""

import copy
import json
import os
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
SCRIPT_DIR = PACKAGE_DIR.parent
CONFIG_PATH = SCRIPT_DIR / "config.json"

SUBSAMPLING_MAP = {
    "4:4:4": 0,
    "4:2:2": 1,
    "4:2:0": 2,
}

DEFAULT_CONFIG = {
    "input_folder": "",
    "output_folder": "",
    "max_workers": os.cpu_count() or 4,
    "resize": {
        "size_px": 0,
    },
    "jpeg": {
        "enabled": True,
        "quality": 85,
        "progressive": True,
        "subsampling": "4:2:0",
    },
    "text": {
        "enabled": True,
        "content": "",
        "font_size_percent": 3.0,
        "position": "bottom-middle",
        "padding": {"top": 35, "right": 35, "bottom": 35, "left": 35},
    },
    "sticker": {
        "enabled": False,
        "path": "Sticker.png",
        "size_percent": 15,
        "position": "bottom-right",
        "padding": {"top": 35, "right": 35, "bottom": 35, "left": 35},
    },
    "cloud_upload": {
        "enabled": False,
        "provider": "pixeldrain",
        "api_key": "",
        "max_workers": 10,
    },
}


def _deep_merge(base, override):
    """Merge override into base (dicts only); override wins for leaf values."""
    result = dict(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def default_workers():
    """CPU thread count for the thread pool (fallback: 4)."""
    return os.cpu_count() or 4


def _blank_config():
    """Fresh deep copy of DEFAULT_CONFIG."""
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    cfg["max_workers"] = default_workers()
    return cfg


def normalize_trbl(value, default=0):
    """
    Normalize padding/margin to {top, right, bottom, left}.
    Accepts int, [v], [vertical, horizontal], [t,r,b,l], or dict.
    """
    sides = ("top", "right", "bottom", "left")
    try:
        default = int(default)
    except (TypeError, ValueError):
        default = 0

    if isinstance(value, dict):
        return {s: int(value.get(s, default)) for s in sides}

    if isinstance(value, (list, tuple)):
        vals = [int(v) for v in value]
        if len(vals) == 1:
            v = vals[0]
            return {s: v for s in sides}
        if len(vals) == 2:
            v, h = vals
            return {"top": v, "right": h, "bottom": v, "left": h}
        if len(vals) >= 4:
            return {"top": vals[0], "right": vals[1], "bottom": vals[2], "left": vals[3]}

    try:
        v = int(value)
    except (TypeError, ValueError):
        v = default
    return {s: v for s in sides}


def combine_trbl(padding, margin=None):
    """
    Build inset TRBL from padding.
    Legacy: if margin is provided, it is added into padding (old dual-field configs).
    """
    p = normalize_trbl(padding, 0)
    if margin is None:
        return p
    m = normalize_trbl(margin, 0)
    return {s: p[s] + m[s] for s in ("top", "right", "bottom", "left")}


def normalize_position(position):
    """
    Normalize sticker position to a 3x3 slot name.
    Legacy left/right/middle map to the bottom row.
    """
    position = (position or "bottom-right").strip().lower().replace("_", "-").replace(" ", "-")
    aliases = {
        "l": "bottom-left",
        "left": "bottom-left",
        "bottom-left": "bottom-left",
        "bl": "bottom-left",
        "m": "bottom-middle",
        "middle": "bottom-middle",
        "bottom": "bottom-middle",
        "bottom-middle": "bottom-middle",
        "bottom-center": "bottom-middle",
        "bm": "bottom-middle",
        "r": "bottom-right",
        "right": "bottom-right",
        "bottom-right": "bottom-right",
        "br": "bottom-right",
        "top-left": "top-left",
        "tl": "top-left",
        "top-middle": "top-middle",
        "top-center": "top-middle",
        "tm": "top-middle",
        "top": "top-middle",
        "top-right": "top-right",
        "tr": "top-right",
        "middle-left": "middle-left",
        "ml": "middle-left",
        "center-left": "middle-left",
        "center": "center",
        "c": "center",
        "middle-middle": "center",
        "middle-center": "center",
        "mc": "center",
        "middle-right": "middle-right",
        "mr": "middle-right",
        "center-right": "middle-right",
    }
    return aliases.get(position)


def _normalize_resize_config(config):
    """
    Normalize resize block to {size_px: int}.
    0 = original. Positive = longest-side target (never upscale).
    Accepts legacy {mode, size_px} where mode was original|longest|shortest.
    """
    resize = dict(config.get("resize") or {})
    has_mode = "mode" in resize
    mode = str(resize.get("mode") or "").strip().lower() if has_mode else None
    try:
        size_px = int(resize.get("size_px") or 0)
    except (TypeError, ValueError):
        size_px = 0

    if mode == "original":
        size_px = 0
    else:
        size_px = max(0, size_px)

    config["resize"] = {"size_px": size_px}
    return config


def _normalize_box_fields(config):
    """Ensure text/sticker padding is TRBL; fold legacy margin into padding."""
    for section, pad_default in (
        ("text", 35),
        ("sticker", 35),
    ):
        block = config.get(section)
        if not isinstance(block, dict):
            continue
        pad = normalize_trbl(block.get("padding", pad_default), pad_default)
        if "margin" in block:
            mar = normalize_trbl(block.get("margin"), 0)
            pad = {s: pad[s] + mar[s] for s in ("top", "right", "bottom", "left")}
            block.pop("margin", None)
        block["padding"] = pad
        block.pop("margin", None)
    return config


def load_config(path=None):
    """Load config.json; fall back to built-in defaults for missing keys."""
    path = Path(path) if path else CONFIG_PATH
    config = _blank_config()

    if not path.is_file():
        print(f"⚠️ Config not found at {path}, using built-in defaults.")
        return config

    try:
        with open(path, encoding="utf-8") as f:
            loaded = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"⚠️ Failed to read config ({e}), using built-in defaults.")
        return config

    legacy_quality = loaded.pop("jpeg_quality", None) if isinstance(loaded, dict) else None
    config = _deep_merge(config, loaded)
    if legacy_quality is not None and "jpeg" not in (loaded or {}):
        config["jpeg"]["quality"] = int(legacy_quality)
    elif legacy_quality is not None and isinstance(loaded.get("jpeg"), dict) and "quality" not in loaded["jpeg"]:
        config["jpeg"]["quality"] = int(legacy_quality)

    config = _normalize_resize_config(_normalize_box_fields(config))
    cloud = config.get("cloud_upload")
    if isinstance(cloud, dict):
        cloud.pop("album_name", None)
    return config


def save_config(config, path=None):
    """Write config to JSON (new schema; drops legacy keys)."""
    path = Path(path) if path else CONFIG_PATH
    to_save = copy.deepcopy(config)
    to_save.pop("jpeg_quality", None)
    cloud = to_save.get("cloud_upload")
    if isinstance(cloud, dict):
        # Album title is session-only (defaults to input folder name in the UI).
        cloud.pop("album_name", None)
    to_save = _normalize_resize_config(_normalize_box_fields(to_save))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(to_save, f, indent=2)
        f.write("\n")
    return path


def resolve_path(value, base_dir=SCRIPT_DIR):
    """Resolve a path; relative paths are relative to the config/script folder."""
    if not value:
        return None
    path = Path(str(value).strip().strip('"'))
    if not path.is_absolute():
        path = base_dir / path
    return path


def export_resize_label(config):
    """Human-readable export resize summary for UI status."""
    resize = (config.get("resize") or {})
    try:
        size_px = int(resize.get("size_px") or 0)
    except (TypeError, ValueError):
        size_px = 0
    if size_px > 0:
        return f"Export: longest side {size_px}px"
    return "Export: original size"


def effective_jpeg_options(config):
    """
    JPEG options used for compress/estimate.
    When jpeg.enabled is False, fall back to built-in defaults.
    """
    jpeg = dict((config or {}).get("jpeg") or {})
    if jpeg.get("enabled", True) is False:
        jpeg = dict(DEFAULT_CONFIG["jpeg"])
    jpeg.pop("enabled", None)
    return jpeg
