"""Theme constants and shared GUI helpers."""

import customtkinter as ctk

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

BG = "#0f172a"
PANEL = "#18181b"
CARD = "#1e293b"
BORDER = "#334155"
ACCENT = "#6366f1"
ACCENT_HOVER = "#818cf8"
MUTED = "#94a3b8"
TEXT = "#e2e8f0"
SUCCESS = "#34d399"
DANGER = "#f87171"

PREVIEW_LANDSCAPE = (960, 720)
PREVIEW_PORTRAIT = (720, 960)
PREVIEW_MARGIN = 80
PREVIEW_WORK_MAX = 1600
DEBOUNCE_MS = 150
ESTIMATE_DEBOUNCE_MS = 400
IMAGE_EXTS = {".jpg", ".jpeg", ".png"}
RESIZE_PRESETS = (720, 1080, 1440, 1920)
TRBL_SIDES = ("top", "right", "bottom", "left")
TRBL_LABELS = ("T", "R", "B", "L")

POSITION_GRID = [
    ("top-left", "top-middle", "top-right"),
    ("middle-left", "center", "middle-right"),
    ("bottom-left", "bottom-middle", "bottom-right"),
]


def truncate_path(path, max_len=42):
    path = (path or "").strip()
    if len(path) <= max_len:
        return path or "No folder selected"
    return "…" + path[-(max_len - 1):]
