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
        "landscape": {
            "font_size_percent": 3.0,
            "position": "bottom-middle",
            "padding": {"top": 35, "right": 35, "bottom": 35, "left": 35},
            "opacity": 100,
        },
        "portrait": {
            "font_size_percent": 3.0,
            "position": "bottom-middle",
            "padding": {"top": 35, "right": 35, "bottom": 35, "left": 35},
            "opacity": 100,
        },
    },
    "sticker": {
        "enabled": False,
        "path": "Sticker.png",
        "landscape": {
            "size_percent": 15,
            "position": "bottom-right",
            "padding": {"top": 35, "right": 35, "bottom": 35, "left": 35},
            "opacity": 100,
        },
        "portrait": {
            "size_percent": 15,
            "position": "bottom-right",
            "padding": {"top": 35, "right": 35, "bottom": 35, "left": 35},
            "opacity": 100,
        },
    },
    "cloud_upload": {
        "enabled": False,
        "provider": "pixeldrain",
        "api_key": "",
        "max_workers": 10,
        "album_mode": "new",
        "album_id": "",
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


ORIENTATIONS = ("landscape", "portrait")

# Per-orientation layout keys for each watermark section. Everything else in the
# section (enabled, content, path) is shared by both orientations.
LAYOUT_KEYS = {
    "text": ("font_size_percent", "position", "padding", "opacity"),
    "sticker": ("size_percent", "position", "padding", "opacity"),
}


def image_orientation(width, height):
    """'portrait' when taller than wide, otherwise 'landscape' (squares count as landscape)."""
    return "portrait" if height > width else "landscape"


def normalize_opacity(value, default=100):
    """Clamp opacity to an int percentage 0-100."""
    try:
        return max(0, min(100, int(round(float(value)))))
    except (TypeError, ValueError):
        return default


def _normalize_layout(section, layout, pad_default=35):
    """Normalize one orientation's layout dict (padding TRBL, legacy margin, opacity)."""
    layout = dict(layout or {})
    pad = normalize_trbl(layout.get("padding", pad_default), pad_default)
    if "margin" in layout:
        mar = normalize_trbl(layout.pop("margin"), 0)
        pad = {s: pad[s] + mar[s] for s in ("top", "right", "bottom", "left")}
    layout["padding"] = pad
    layout["opacity"] = normalize_opacity(layout.get("opacity", 100))
    defaults = DEFAULT_CONFIG[section]["landscape"]
    for key in LAYOUT_KEYS[section]:
        layout.setdefault(key, copy.deepcopy(defaults[key]))
    return layout


def _normalize_box_fields(config):
    """
    Ensure text/sticker have landscape/portrait layout blocks.
    Legacy flat keys (font_size_percent/size_percent, position, padding, margin)
    are copied into both orientations.
    """
    for section in ("text", "sticker"):
        block = config.get(section)
        if not isinstance(block, dict):
            continue
        legacy = {}
        for key in LAYOUT_KEYS[section] + ("margin",):
            if key in block:
                legacy[key] = block.pop(key)
        for orientation in ORIENTATIONS:
            layout = dict(block.get(orientation) or {})
            layout.update(copy.deepcopy(legacy))
            block[orientation] = _normalize_layout(section, layout)
    return config


def watermark_settings(config, section, orientation):
    """Flat settings for one section/orientation: shared keys + that orientation's layout."""
    block = dict((config or {}).get(section) or {})
    layouts = {o: block.pop(o, None) for o in ORIENTATIONS}
    layout = layouts.get(orientation) or layouts.get("landscape") or {}
    # Legacy flat configs (not run through load_config) keep working.
    return {**block, **layout}


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
        mode = str(cloud.get("album_mode") or "new").strip().lower()
        cloud["album_mode"] = mode if mode in ("new", "existing") else "new"
        album_id = cloud.get("album_id")
        cloud["album_id"] = album_id.strip() if isinstance(album_id, str) else ""
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
