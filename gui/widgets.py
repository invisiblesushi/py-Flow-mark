"""Reusable CustomTkinter widgets."""

import customtkinter as ctk

from flowmark import normalize_position

from .theme import (
    ACCENT,
    ACCENT_HOVER,
    BORDER,
    CARD,
    MUTED,
    PANEL,
    POSITION_GRID,
    TEXT,
    truncate_path,
)


class Accordion(ctk.CTkFrame):
    """Collapsible card section."""

    def __init__(self, master, title, expanded=True, **kwargs):
        super().__init__(master, fg_color=CARD, corner_radius=12, border_width=1, border_color=BORDER, **kwargs)
        self._expanded = expanded
        self._title = title

        self.header = ctk.CTkButton(
            self,
            text=self._header_text(),
            anchor="w",
            fg_color="transparent",
            hover_color="#273549",
            text_color=TEXT,
            font=ctk.CTkFont(size=14, weight="bold"),
            height=36,
            corner_radius=10,
            command=self.toggle,
        )
        self.header.pack(fill="x", padx=8, pady=(6, 0))

        self.body = ctk.CTkFrame(self, fg_color="transparent")
        if expanded:
            self.body.pack(fill="x", padx=12, pady=(4, 12))

    def _header_text(self):
        arrow = "▾" if self._expanded else "▸"
        return f"  {arrow}  {self._title}"

    def toggle(self):
        self._expanded = not self._expanded
        self.header.configure(text=self._header_text())
        if self._expanded:
            self.body.pack(fill="x", padx=12, pady=(4, 12))
        else:
            self.body.pack_forget()


class PathChip(ctk.CTkFrame):
    """Truncated path display with browse button."""

    def __init__(self, master, variable, browse_cmd, **kwargs):
        super().__init__(master, fg_color=PANEL, corner_radius=10, border_width=1, border_color=BORDER, **kwargs)
        self.variable = variable
        self.chip = ctk.CTkLabel(
            self,
            text=truncate_path(variable.get()),
            text_color=MUTED,
            anchor="w",
            font=ctk.CTkFont(size=12),
        )
        self.chip.pack(side="left", fill="x", expand=True, padx=(12, 6), pady=8)
        ctk.CTkButton(
            self,
            text="Browse",
            width=72,
            height=28,
            corner_radius=8,
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            command=browse_cmd,
        ).pack(side="right", padx=(0, 8), pady=6)
        variable.trace_add("write", self._refresh)
        self.chip.bind("<Enter>", lambda e: self.chip.configure(text=variable.get() or "No folder selected"))
        self.chip.bind("<Leave>", lambda e: self._refresh())

    def _refresh(self, *_):
        self.chip.configure(text=truncate_path(self.variable.get()))


class PillGroup(ctk.CTkFrame):
    """Exclusive pill/chip selector."""

    def __init__(self, master, options, variable, command=None, **kwargs):
        """options: list of (label, value)"""
        super().__init__(master, fg_color="transparent", **kwargs)
        self.variable = variable
        self.command = command
        self.buttons = {}
        for label, value in options:
            btn = ctk.CTkButton(
                self,
                text=label,
                width=64,
                height=30,
                corner_radius=16,
                font=ctk.CTkFont(size=12),
                command=lambda v=value: self._select(v),
            )
            btn.pack(side="left", padx=3, pady=2)
            self.buttons[value] = btn
        self._paint()
        variable.trace_add("write", lambda *_: self._paint())

    def _select(self, value):
        self.variable.set(value)
        if self.command:
            self.command()

    def _paint(self):
        current = self.variable.get()
        for value, btn in self.buttons.items():
            if value == current:
                btn.configure(fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color="white")
            else:
                btn.configure(fg_color=PANEL, hover_color=BORDER, text_color=MUTED)


class PositionGrid(ctk.CTkFrame):
    """3x3 sticker alignment picker."""

    def __init__(self, master, variable, command=None, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.variable = variable
        self.command = command
        self.buttons = {}
        for r, row in enumerate(POSITION_GRID):
            for c, pos in enumerate(row):
                btn = ctk.CTkButton(
                    self,
                    text="●",
                    width=34,
                    height=28,
                    corner_radius=6,
                    font=ctk.CTkFont(size=11),
                    command=lambda p=pos: self._select(p),
                )
                btn.grid(row=r, column=c, padx=3, pady=3)
                self.buttons[pos] = btn
        self._paint()
        variable.trace_add("write", lambda *_: self._paint())

    def _select(self, pos):
        self.variable.set(pos)
        if self.command:
            self.command()

    def _paint(self):
        current = normalize_position(self.variable.get()) or "bottom-right"
        for pos, btn in self.buttons.items():
            if pos == current:
                btn.configure(fg_color=ACCENT, text_color="white")
            else:
                btn.configure(fg_color=PANEL, text_color=MUTED)
