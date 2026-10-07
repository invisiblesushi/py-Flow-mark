"""FlowMark GUI — CustomTkinter app with live preview."""

import os
import threading
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

import flowmark
from flowmark import (
    CONFIG_PATH,
    DEFAULT_CONFIG,
    apply_watermarks,
    combine_trbl,
    default_workers,
    estimate_export_savings,
    export_resize_label,
    format_savings_estimate,
    load_config,
    normalize_position,
    normalize_trbl,
    process_folder,
    resize_image,
    save_config,
)

from .preview import find_folder_preview_images, fit_for_display, make_placeholder
from .theme import (
    ACCENT,
    ACCENT_HOVER,
    BG,
    BORDER,
    CARD,
    DEBOUNCE_MS,
    ESTIMATE_DEBOUNCE_MS,
    MUTED,
    PANEL,
    PREVIEW_LANDSCAPE,
    PREVIEW_MARGIN,
    PREVIEW_PORTRAIT,
    RESIZE_PRESETS,
    SUCCESS,
    TEXT,
    TRBL_LABELS,
    TRBL_SIDES,
)
from .widgets import Accordion, PathChip, PillGroup, PositionGrid


class FlowMarkApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("FlowMark")
        self.geometry("1280x820")
        self.minsize(1040, 700)
        self.configure(fg_color=BG)

        self._preview_job = None
        self._estimate_job = None
        self._estimate_token = 0
        self._photo_refs = {}
        self._running = False
        self._output_user_edited = False
        self._log_visible = False
        self._last_preview_rgba = None
        self._preview_source_note = ""
        self.var_preview_tab = ctk.StringVar(value="Landscape")
        self.var_preview_scale = ctk.DoubleVar(value=65.0)

        self._placeholder_landscape = make_placeholder(PREVIEW_LANDSCAPE, "Landscape")
        self._placeholder_portrait = make_placeholder(PREVIEW_PORTRAIT, "Portrait")
        self._base_landscape = self._placeholder_landscape
        self._base_portrait = self._placeholder_portrait

        self._build_vars()
        self._build_layout()
        self.load_into_form(load_config())
        self.after(80, self.refresh_preview)
        self.after(120, self.refresh_jpeg_estimate)

    def _build_vars(self):
        self.var_input = ctk.StringVar()
        self.var_output = ctk.StringVar()
        self.var_resize_preset = ctk.StringVar(value="original")
        self.var_size_px = ctk.IntVar(value=1080)
        self.var_jpeg_enabled = ctk.BooleanVar(value=True)
        self.var_jpeg_quality = ctk.IntVar(value=85)
        self.var_jpeg_progressive = ctk.BooleanVar(value=True)
        self.var_jpeg_subsample = ctk.StringVar(value="4:2:0")
        self.var_text_enabled = ctk.BooleanVar(value=True)
        self.var_text_content = ctk.StringVar()
        self.var_font_pct = ctk.DoubleVar(value=3.0)
        self.var_text_pos = ctk.StringVar(value="bottom-middle")
        self.var_text_padding = {s: ctk.IntVar(value=35) for s in TRBL_SIDES}
        self.var_sticker_enabled = ctk.BooleanVar(value=False)
        self.var_sticker_path = ctk.StringVar(value="Sticker.png")
        self.var_sticker_pct = ctk.DoubleVar(value=15.0)
        self.var_sticker_pos = ctk.StringVar(value="bottom-right")
        self.var_sticker_padding = {s: ctk.IntVar(value=35) for s in TRBL_SIDES}
        self.var_cloud_enabled = ctk.BooleanVar(value=False)
        self.var_cloud_album = ctk.StringVar(value="")
        self.var_cloud_api_key = ctk.StringVar(value="")
        self.var_cloud_workers = ctk.IntVar(value=10)
        self.var_export_status = ctk.StringVar(value="Export: original size")
        self.var_preview_warning = ctk.StringVar(value="")
        self.var_jpeg_estimate = ctk.StringVar(value="Select an input folder to estimate JPEG savings.")
        self.var_status = ctk.StringVar(value="Ready")

        preview_vars = [
            self.var_text_enabled, self.var_text_content, self.var_font_pct, self.var_text_pos,
            self.var_sticker_enabled, self.var_sticker_path, self.var_sticker_pct,
            self.var_sticker_pos,
        ]
        for group in (self.var_text_padding, self.var_sticker_padding):
            preview_vars.extend(group.values())
        for var in preview_vars:
            var.trace_add("write", self._on_preview_only_change)

        export_vars = [
            self.var_jpeg_enabled, self.var_resize_preset, self.var_size_px,
            self.var_jpeg_quality, self.var_jpeg_progressive, self.var_jpeg_subsample,
        ]
        for var in export_vars:
            var.trace_add("write", self._on_export_settings_change)

        self.var_input.trace_add("write", self._on_input_change)
        self.var_output.trace_add("write", self._on_output_change)

    def _build_layout(self):
        header = ctk.CTkFrame(self, fg_color=PANEL, height=56, corner_radius=0)
        header.pack(fill="x")
        header.pack_propagate(False)
        ctk.CTkLabel(
            header, text="FlowMark", font=ctk.CTkFont(size=20, weight="bold"), text_color=TEXT,
        ).pack(side="left", padx=20)
        ctk.CTkLabel(header, text="Batch watermark studio", text_color=MUTED, font=ctk.CTkFont(size=12)).pack(
            side="left", padx=(0, 12)
        )
        ctk.CTkButton(
            header, text="Reload", width=90, height=32, fg_color=CARD, hover_color=BORDER,
            border_width=1, border_color=BORDER, command=self.on_reload,
        ).pack(side="right", padx=(6, 20), pady=12)
        ctk.CTkButton(
            header, text="Save Config", width=110, height=32, fg_color=ACCENT, hover_color=ACCENT_HOVER,
            command=self.on_save,
        ).pack(side="right", padx=6, pady=12)

        body = ctk.CTkFrame(self, fg_color=BG)
        body.pack(fill="both", expand=True, padx=16, pady=(12, 0))
        body.grid_columnconfigure(0, weight=2, minsize=360, uniform="main")
        body.grid_columnconfigure(1, weight=3, minsize=400, uniform="main")
        body.grid_rowconfigure(0, weight=1)
        self._body = body

        self.config_scroll = ctk.CTkScrollableFrame(body, fg_color="transparent", corner_radius=0)
        self.config_scroll.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        self._build_config_panels(self.config_scroll)

        self.preview_panel = ctk.CTkFrame(
            body, fg_color=CARD, corner_radius=14, border_width=1, border_color=BORDER,
        )
        self.preview_panel.grid(row=0, column=1, sticky="nsew")
        self.preview_panel.grid_propagate(False)
        self._build_preview_panel(self.preview_panel)

        self._build_action_bar()

    def _build_config_panels(self, parent):
        d = DEFAULT_CONFIG

        acc = Accordion(parent, "Folders & Threads", expanded=True)
        acc.pack(fill="x", pady=(0, 10))
        self._option_header(acc.body, "Input folder", lambda: self._reset_input())
        PathChip(acc.body, self.var_input, self._browse_input).pack(fill="x", pady=(2, 10))
        self._option_header(acc.body, "Output folder", lambda: self._reset_output())
        PathChip(acc.body, self.var_output, self._browse_output).pack(fill="x", pady=(2, 8))
        ctk.CTkLabel(
            acc.body,
            text=f"Threads  ·  {default_workers()} (auto-detected)",
            text_color=MUTED,
            anchor="w",
            font=ctk.CTkFont(size=12),
        ).pack(fill="x", pady=(4, 0))

        acc = Accordion(parent, "Image Resizing", expanded=True)
        acc.pack(fill="x", pady=(0, 10))
        self._option_header(acc.body, "Longest-side target", lambda: self._reset_resize())
        pills = [
            ("Original", "original"),
            *((f"{p}p", str(p)) for p in RESIZE_PRESETS),
            ("Custom", "custom"),
        ]
        PillGroup(acc.body, pills, self.var_resize_preset, command=self._sync_resize_controls).pack(
            anchor="w", pady=(6, 8)
        )
        self.custom_row = ctk.CTkFrame(acc.body, fg_color="transparent")
        ctk.CTkLabel(self.custom_row, text="Custom px", text_color=MUTED).pack(side="left")
        self.spin_size = ctk.CTkEntry(self.custom_row, width=80, textvariable=self.var_size_px)
        self.spin_size.pack(side="left", padx=8)
        self._reset_btn(
            self.custom_row,
            lambda: self.var_size_px.set(1080),
        ).pack(side="left", padx=8)

        acc = Accordion(parent, "Export Settings", expanded=True)
        acc.pack(fill="x", pady=(0, 10))
        self._enable_switch(acc.body, self.var_jpeg_enabled).pack(anchor="w", pady=(0, 8))
        self._option_header(
            acc.body,
            "JPEG quality",
            lambda: self._reset_jpeg_quality(),
            badge_holder=True,
        )
        q_head = acc.body.winfo_children()[-1]
        self.lbl_quality = ctk.CTkLabel(
            q_head, text="85", width=36, fg_color=ACCENT, corner_radius=8, text_color="white",
        )
        self.lbl_quality.pack(side="right", padx=(0, 6))

        self.slider_quality = ctk.CTkSlider(
            acc.body, from_=1, to=95, number_of_steps=94,
            command=self._on_quality_slider, progress_color=ACCENT, button_color=ACCENT,
        )
        self.slider_quality.pack(fill="x", pady=(4, 8))
        self.slider_quality.set(int(d["jpeg"]["quality"]))
        self._disable_slider_mousewheel(self.slider_quality)

        opts = ctk.CTkFrame(acc.body, fg_color="transparent")
        opts.pack(fill="x", pady=(0, 6))
        prog_wrap = ctk.CTkFrame(opts, fg_color="transparent")
        prog_wrap.pack(side="left", padx=(0, 12))
        ctk.CTkSwitch(
            prog_wrap, text="Progressive", variable=self.var_jpeg_progressive,
            progress_color=ACCENT, button_color=ACCENT,
        ).pack(side="left")
        self._reset_btn(prog_wrap, lambda: self.var_jpeg_progressive.set(bool(d["jpeg"]["progressive"]))).pack(
            side="left", padx=6
        )

        sub_wrap = ctk.CTkFrame(opts, fg_color="transparent")
        sub_wrap.pack(side="left")
        ctk.CTkOptionMenu(
            sub_wrap,
            variable=self.var_jpeg_subsample,
            values=["4:4:4", "4:2:2", "4:2:0"],
            width=100,
            fg_color=PANEL,
            button_color=ACCENT,
            button_hover_color=ACCENT_HOVER,
        ).pack(side="left")
        self._reset_btn(sub_wrap, lambda: self.var_jpeg_subsample.set(d["jpeg"]["subsampling"])).pack(
            side="left", padx=6
        )

        ctk.CTkLabel(
            acc.body,
            textvariable=self.var_jpeg_estimate,
            text_color=SUCCESS,
            justify="left",
            anchor="w",
            wraplength=420,
            font=ctk.CTkFont(size=12),
        ).pack(fill="x", pady=(8, 0))

        acc = Accordion(parent, "Text Watermark", expanded=True)
        acc.pack(fill="x", pady=(0, 10))
        self._enable_switch(acc.body, self.var_text_enabled).pack(anchor="w", pady=(0, 8))
        self._option_header(acc.body, "Content", lambda: self.var_text_content.set(d["text"]["content"]))
        ctk.CTkEntry(
            acc.body, textvariable=self.var_text_content, placeholder_text="Watermark text",
            height=34, corner_radius=8,
        ).pack(fill="x", pady=(0, 8))
        self._labeled_slider(
            acc.body, "Font size %", self.var_font_pct, 0.5, 20, 0.1,
            default=d["text"]["font_size_percent"],
        )
        self._option_header(
            acc.body, "Position",
            lambda: self.var_text_pos.set(d["text"].get("position", "bottom-middle")),
        )
        PositionGrid(acc.body, self.var_text_pos, command=self.schedule_preview).pack(anchor="w")
        self._trbl_row(acc.body, "Padding", self.var_text_padding, default=d["text"]["padding"])

        acc = Accordion(parent, "Sticker / Logo", expanded=True)
        acc.pack(fill="x", pady=(0, 10))
        self._enable_switch(acc.body, self.var_sticker_enabled).pack(anchor="w", pady=(0, 8))
        self._option_header(acc.body, "PNG path", lambda: self.var_sticker_path.set(d["sticker"]["path"]))
        PathChip(acc.body, self.var_sticker_path, self._browse_sticker).pack(fill="x", pady=(0, 8))
        self._labeled_slider(
            acc.body, "Size %", self.var_sticker_pct, 1, 100, 0.5,
            default=d["sticker"]["size_percent"],
        )
        self._option_header(
            acc.body, "Position",
            lambda: self.var_sticker_pos.set(d["sticker"]["position"]),
        )
        PositionGrid(acc.body, self.var_sticker_pos, command=self.schedule_preview).pack(anchor="w")
        self._trbl_row(acc.body, "Padding", self.var_sticker_padding, default=d["sticker"]["padding"])

        # Cloud upload (Pixeldrain)
        cloud_d = d.get("cloud_upload") or {}
        acc = Accordion(parent, "Cloud Upload", expanded=False)
        acc.pack(fill="x", pady=(0, 10))
        self._enable_switch(acc.body, self.var_cloud_enabled).pack(anchor="w", pady=(0, 8))

        self.cloud_options = ctk.CTkFrame(acc.body, fg_color="transparent")
        self._option_header(
            self.cloud_options, "Album name",
            lambda: self.var_cloud_album.set(self._default_album_for(self.var_input.get())),
        )
        ctk.CTkEntry(
            self.cloud_options,
            textvariable=self.var_cloud_album,
            placeholder_text="Defaults to input folder name",
            height=34,
            corner_radius=8,
        ).pack(fill="x", pady=(0, 8))
        self._option_header(
            self.cloud_options, "API key",
            lambda: self.var_cloud_api_key.set(cloud_d.get("api_key") or ""),
        )
        ctk.CTkEntry(
            self.cloud_options,
            textvariable=self.var_cloud_api_key,
            placeholder_text="Pixeldrain API key",
            height=34,
            corner_radius=8,
            show="•",
        ).pack(fill="x", pady=(0, 8))
        self._option_header(
            self.cloud_options, "Upload threads",
            lambda: self.var_cloud_workers.set(int(cloud_d.get("max_workers") or 10)),
        )
        workers_row = ctk.CTkFrame(self.cloud_options, fg_color="transparent")
        workers_row.pack(fill="x", pady=(0, 4))
        ctk.CTkEntry(
            workers_row,
            textvariable=self.var_cloud_workers,
            width=72,
            height=34,
            corner_radius=8,
        ).pack(side="left")
        ctk.CTkLabel(
            workers_row,
            text="parallel uploads (1–32)",
            text_color=MUTED,
            font=ctk.CTkFont(size=12),
        ).pack(side="left", padx=10)
        ctk.CTkLabel(
            self.cloud_options,
            text="Get a key at pixeldrain.com/user/api_keys — album link appears in the log when done.",
            text_color=MUTED,
            wraplength=420,
            justify="left",
            anchor="w",
            font=ctk.CTkFont(size=11),
        ).pack(fill="x", pady=(4, 0))

        self.var_cloud_enabled.trace_add("write", self._sync_cloud_options)
        self._sync_cloud_options()

    def _enable_switch(self, parent, variable):
        """Switch whose label is Enable when on, Disable when off."""
        switch = ctk.CTkSwitch(
            parent,
            text="Enable",
            variable=variable,
            progress_color=ACCENT,
            button_color=ACCENT,
        )

        def sync(*_):
            switch.configure(text="Enable" if variable.get() else "Disable")

        variable.trace_add("write", sync)
        sync()
        return switch

    def _sync_cloud_options(self, *_):
        """Show cloud settings only when upload is enabled."""
        if not hasattr(self, "cloud_options"):
            return
        if self.var_cloud_enabled.get():
            if not self.cloud_options.winfo_ismapped():
                self.cloud_options.pack(fill="x")
        else:
            self.cloud_options.pack_forget()

    def _reset_btn(self, parent, command):
        return ctk.CTkButton(
            parent,
            text="Reset",
            width=52,
            height=24,
            corner_radius=6,
            fg_color="transparent",
            hover_color=BORDER,
            border_width=1,
            border_color=BORDER,
            text_color=MUTED,
            font=ctk.CTkFont(size=11),
            command=command,
        )

    def _option_header(self, parent, label, reset_cmd, badge_holder=False):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=(2, 0))
        ctk.CTkLabel(row, text=label, text_color=MUTED, anchor="w").pack(side="left")
        self._reset_btn(row, reset_cmd).pack(side="right")
        return row

    def _reset_input(self):
        self.var_input.set(DEFAULT_CONFIG["input_folder"])

    def _reset_output(self):
        self._output_user_edited = False
        self.var_output.set(self._default_output_for(self.var_input.get()))

    def _reset_resize(self):
        self._apply_resize_preset_from_size(DEFAULT_CONFIG["resize"]["size_px"])

    def _reset_jpeg_quality(self):
        q = int(DEFAULT_CONFIG["jpeg"]["quality"])
        self.var_jpeg_quality.set(q)
        self.slider_quality.set(q)
        self.lbl_quality.configure(text=str(q))

    def _scroll_config_panel(self, delta):
        try:
            canvas = self.config_scroll._parent_canvas  # noqa: SLF001
            canvas.yview_scroll(int(-1 * (delta / 120)), "units")
        except Exception:
            pass

    def _disable_slider_mousewheel(self, slider):
        def on_wheel(event):
            self._scroll_config_panel(event.delta)
            return "break"

        def on_linux_up(_event):
            self._scroll_config_panel(120)
            return "break"

        def on_linux_down(_event):
            self._scroll_config_panel(-120)
            return "break"

        targets = [slider]
        try:
            targets.extend(slider.winfo_children())
        except Exception:
            pass
        for widget in targets:
            widget.bind("<MouseWheel>", on_wheel)
            widget.bind("<Button-4>", on_linux_up)
            widget.bind("<Button-5>", on_linux_down)

    def _labeled_slider(self, parent, label, variable, from_, to, step, default=None):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=4)
        ctk.CTkLabel(row, text=label, text_color=MUTED).pack(side="left")

        def do_reset():
            if default is None:
                return
            variable.set(default)
            try:
                slider.set(float(default))
            except Exception:
                pass

        if default is not None:
            self._reset_btn(row, do_reset).pack(side="right", padx=(6, 0))

        badge = ctk.CTkLabel(row, text=str(variable.get()), width=44, fg_color=PANEL, corner_radius=8)
        badge.pack(side="right")

        def on_slide(val):
            snapped = round(float(val) / step) * step
            if step >= 1:
                variable.set(int(round(snapped)))
                badge.configure(text=str(int(variable.get())))
            else:
                variable.set(round(snapped, 1))
                badge.configure(text=f"{float(variable.get()):.1f}")

        slider = ctk.CTkSlider(
            parent, from_=from_, to=to, number_of_steps=max(1, int((to - from_) / step)),
            command=on_slide, progress_color=ACCENT, button_color=ACCENT,
        )
        slider.pack(fill="x", pady=(0, 4))
        self._disable_slider_mousewheel(slider)
        try:
            slider.set(float(variable.get()))
        except Exception:
            pass

        def sync_badge(*_):
            try:
                if step < 1:
                    badge.configure(text=f"{float(variable.get()):.1f}")
                    slider.set(float(variable.get()))
                else:
                    badge.configure(text=str(int(float(variable.get()))))
                    slider.set(float(variable.get()))
            except Exception:
                pass

        variable.trace_add("write", sync_badge)

    def _trbl_row(self, parent, label, var_map, default=None):
        default_box = normalize_trbl(default if default is not None else 0, 0)

        wrap = ctk.CTkFrame(parent, fg_color="transparent")
        wrap.pack(fill="x", pady=4)
        head = ctk.CTkFrame(wrap, fg_color="transparent")
        head.pack(fill="x")
        ctk.CTkLabel(head, text=label, text_color=MUTED).pack(side="left")
        self._reset_btn(head, lambda: self._set_trbl_vars(var_map, default_box)).pack(side="right")

        row = ctk.CTkFrame(wrap, fg_color="transparent")
        row.pack(fill="x", pady=(4, 0))
        for side, short in zip(TRBL_SIDES, TRBL_LABELS):
            cell = ctk.CTkFrame(row, fg_color="transparent")
            cell.pack(side="left", padx=(0, 8))
            ctk.CTkLabel(cell, text=short, text_color=MUTED, width=16).pack(side="left", padx=(0, 4))
            ctk.CTkEntry(cell, width=48, textvariable=var_map[side]).pack(side="left")

    def _set_trbl_vars(self, var_map, box):
        box = normalize_trbl(box, 0)
        for side in TRBL_SIDES:
            var_map[side].set(int(box[side]))

    def _trbl_from_vars(self, var_map):
        out = {}
        for side in TRBL_SIDES:
            try:
                out[side] = int(var_map[side].get())
            except (TypeError, ValueError):
                out[side] = 0
        return out

    def _build_preview_panel(self, parent):
        top = ctk.CTkFrame(parent, fg_color="transparent")
        top.pack(fill="x", padx=14, pady=(14, 6))
        ctk.CTkLabel(top, text="Live Preview", font=ctk.CTkFont(size=15, weight="bold"), text_color=TEXT).pack(
            side="left"
        )
        self._preview_seg = ctk.CTkSegmentedButton(
            top,
            values=["Landscape", "Portrait"],
            variable=self.var_preview_tab,
            command=self._on_preview_tab,
            selected_color=ACCENT,
            selected_hover_color=ACCENT_HOVER,
            unselected_color=PANEL,
            unselected_hover_color=BORDER,
        )
        self._preview_seg.pack(side="right")
        self.var_preview_tab.set("Landscape")

        ctk.CTkLabel(
            parent, textvariable=self.var_export_status, text_color=MUTED, font=ctk.CTkFont(size=11),
        ).pack(anchor="w", padx=14)
        ctk.CTkLabel(
            parent, textvariable=self.var_preview_warning, text_color="#fbbf24", font=ctk.CTkFont(size=11),
        ).pack(anchor="w", padx=14)

        scale_row = ctk.CTkFrame(parent, fg_color="transparent")
        scale_row.pack(fill="x", padx=14, pady=(8, 0))
        ctk.CTkLabel(scale_row, text="Preview scale", text_color=MUTED).pack(side="left")
        self.lbl_preview_scale = ctk.CTkLabel(
            scale_row, text="65%", width=48, fg_color=PANEL, corner_radius=8, text_color=TEXT,
        )
        self.lbl_preview_scale.pack(side="right")
        self.slider_preview_scale = ctk.CTkSlider(
            parent, from_=40, to=150, number_of_steps=110,
            command=self._on_preview_scale, progress_color=ACCENT, button_color=ACCENT,
        )
        self.slider_preview_scale.pack(fill="x", padx=14, pady=(4, 0))
        self.slider_preview_scale.set(65)
        self._disable_slider_mousewheel(self.slider_preview_scale)

        self.preview_canvas = ctk.CTkFrame(parent, fg_color=PANEL, corner_radius=12)
        self.preview_canvas.pack(fill="both", expand=True, padx=14, pady=12)
        self.preview_canvas.pack_propagate(False)
        self.preview_label = ctk.CTkLabel(self.preview_canvas, text="", fg_color="transparent")
        self.preview_label.place(relx=0.5, rely=0.5, anchor="center")
        self._canvas_box = (400, 300)
        self.preview_canvas.bind("<Configure>", self._on_preview_canvas_resize)

    def _build_action_bar(self):
        self.log_frame = ctk.CTkFrame(self, fg_color=CARD, height=160, corner_radius=0)
        self.log_box = ctk.CTkTextbox(
            self.log_frame, fg_color=PANEL, text_color=TEXT,
            font=ctk.CTkFont(family="Consolas", size=12),
        )
        self.log_box.pack(fill="both", expand=True, padx=12, pady=10)
        self.log_box.configure(state="disabled")

        self.action_bar = ctk.CTkFrame(self, fg_color=PANEL, height=64, corner_radius=0)
        self.action_bar.pack(fill="x", side="bottom")
        self.action_bar.pack_propagate(False)

        self.btn_log = ctk.CTkButton(
            self.action_bar, text="▾ Log", width=80, height=34, fg_color=CARD, hover_color=BORDER,
            border_width=1, border_color=BORDER, command=self.toggle_log,
        )
        self.btn_log.pack(side="left", padx=16, pady=14)

        ctk.CTkLabel(self.action_bar, textvariable=self.var_status, text_color=MUTED).pack(side="left", padx=8)

        self.btn_run = ctk.CTkButton(
            self.action_bar, text="Run Batch Process", width=180, height=38,
            fg_color=ACCENT, hover_color=ACCENT_HOVER, font=ctk.CTkFont(size=14, weight="bold"),
            command=self.on_run,
        )
        self.btn_run.pack(side="right", padx=16, pady=12)

    def toggle_log(self):
        self._log_visible = not self._log_visible
        if self._log_visible:
            self.action_bar.pack_forget()
            self.log_frame.pack(fill="x", side="bottom")
            self.action_bar.pack(fill="x", side="bottom")
            self.btn_log.configure(text="▴ Log")
        else:
            self.log_frame.pack_forget()
            self.btn_log.configure(text="▾ Log")

    def _on_preview_tab(self, value=None):
        if value:
            self.var_preview_tab.set(value)
        self._last_preview_rgba = None
        self.refresh_preview()

    def _on_preview_scale(self, value):
        pct = int(round(float(value)))
        self.var_preview_scale.set(pct)
        self.lbl_preview_scale.configure(text=f"{pct}%")
        if self._last_preview_rgba is not None:
            self._show_preview_image(self._last_preview_rgba)
        else:
            self.refresh_preview()

    def _on_quality_slider(self, value):
        q = int(round(float(value)))
        self.var_jpeg_quality.set(q)
        self.lbl_quality.configure(text=str(q))

    def _browse_input(self):
        path = filedialog.askdirectory(title="Input folder")
        if path:
            self.var_input.set(path)

    def _browse_output(self):
        path = filedialog.askdirectory(title="Output folder")
        if path:
            self._output_user_edited = True
            self.var_output.set(path)

    def _browse_sticker(self):
        path = filedialog.askopenfilename(
            title="Sticker PNG",
            filetypes=[("PNG images", "*.png"), ("All files", "*.*")],
        )
        if path:
            try:
                rel = Path(path).resolve().relative_to(flowmark.SCRIPT_DIR)
                self.var_sticker_path.set(str(rel))
            except ValueError:
                self.var_sticker_path.set(path)

    def _default_output_for(self, input_folder):
        folder = (input_folder or "").strip()
        return str(Path(folder) / "output") if folder else ""

    def _default_album_for(self, input_folder):
        folder = (input_folder or "").strip()
        return Path(folder).name if folder else ""

    def _on_input_change(self, *_):
        if not self._output_user_edited:
            self.var_output.set(self._default_output_for(self.var_input.get()))
        self.var_cloud_album.set(self._default_album_for(self.var_input.get()))
        self.reload_preview_bases()
        self.schedule_preview()
        self.schedule_jpeg_estimate()

    def _on_output_change(self, *_):
        expected = self._default_output_for(self.var_input.get())
        current = self.var_output.get().strip()
        if expected and current:
            try:
                if Path(current).resolve() != Path(expected).resolve():
                    self._output_user_edited = True
            except OSError:
                self._output_user_edited = True
        elif not current:
            self._output_user_edited = False

    def _resize_size_px_from_form(self):
        preset = self.var_resize_preset.get()
        if preset == "original":
            return 0
        if preset == "custom":
            try:
                return max(0, int(self.var_size_px.get()))
            except (TypeError, ValueError):
                return 0
        try:
            return int(preset)
        except (TypeError, ValueError):
            return 0

    def _apply_resize_preset_from_size(self, size_px):
        size_px = int(size_px or 0)
        if size_px <= 0:
            self.var_resize_preset.set("original")
        elif size_px in RESIZE_PRESETS:
            self.var_resize_preset.set(str(size_px))
            self.var_size_px.set(size_px)
        else:
            self.var_resize_preset.set("custom")
            self.var_size_px.set(size_px)
        self._sync_resize_controls()

    def _sync_resize_controls(self):
        preset = self.var_resize_preset.get()
        if preset == "custom":
            if not self.custom_row.winfo_ismapped():
                self.custom_row.pack(fill="x", pady=(4, 0))
        else:
            self.custom_row.pack_forget()
        if preset not in ("original", "custom"):
            try:
                self.var_size_px.set(int(preset))
            except ValueError:
                pass
        self.schedule_preview()
        self.schedule_jpeg_estimate()

    def _on_preview_canvas_resize(self, event):
        if event.width < 80 or event.height < 80:
            return
        margin = PREVIEW_MARGIN
        new_box = (max(32, event.width - margin), max(32, event.height - margin))
        if new_box == getattr(self, "_canvas_box", None):
            return
        self._canvas_box = new_box
        if self._last_preview_rgba is not None:
            self.schedule_preview_fit_only()

    def schedule_preview_fit_only(self):
        if self._preview_job is not None:
            self.after_cancel(self._preview_job)
        self._preview_job = self.after(DEBOUNCE_MS, self._fit_cached_preview)

    def reload_preview_bases(self):
        land, port = find_folder_preview_images(self.var_input.get().strip())
        notes = []
        if land is not None:
            self._base_landscape = land
            notes.append("landscape photo")
        else:
            self._base_landscape = self._placeholder_landscape
            notes.append("landscape placeholder")
        if port is not None:
            self._base_portrait = port
            notes.append("portrait photo")
        else:
            self._base_portrait = self._placeholder_portrait
            notes.append("portrait placeholder")
        self._preview_source_note = "Preview: " + " · ".join(notes)

    def form_to_config(self):
        return {
            "input_folder": self.var_input.get().strip(),
            "output_folder": self.var_output.get().strip(),
            "max_workers": default_workers(),
            "resize": {"size_px": self._resize_size_px_from_form()},
            "jpeg": {
                "enabled": bool(self.var_jpeg_enabled.get()),
                "quality": int(self.var_jpeg_quality.get()),
                "progressive": bool(self.var_jpeg_progressive.get()),
                "subsampling": self.var_jpeg_subsample.get(),
            },
            "text": {
                "enabled": bool(self.var_text_enabled.get()),
                "content": self.var_text_content.get(),
                "font_size_percent": float(self.var_font_pct.get()),
                "position": normalize_position(self.var_text_pos.get()) or "bottom-middle",
                "padding": self._trbl_from_vars(self.var_text_padding),
            },
            "sticker": {
                "enabled": bool(self.var_sticker_enabled.get()),
                "path": self.var_sticker_path.get().strip(),
                "size_percent": float(self.var_sticker_pct.get()),
                "position": normalize_position(self.var_sticker_pos.get()) or "bottom-right",
                "padding": self._trbl_from_vars(self.var_sticker_padding),
            },
            "cloud_upload": {
                "enabled": bool(self.var_cloud_enabled.get()),
                "provider": "pixeldrain",
                "api_key": self.var_cloud_api_key.get().strip(),
                "album_name": self.var_cloud_album.get().strip(),
                "max_workers": self._cloud_workers_from_form(),
            },
        }

    def _cloud_workers_from_form(self):
        try:
            return max(1, min(32, int(self.var_cloud_workers.get())))
        except (TypeError, ValueError):
            return 10

    def load_into_form(self, config):
        self._output_user_edited = False
        self.var_input.set(config.get("input_folder") or "")
        saved_output = (config.get("output_folder") or "").strip()
        input_folder = (config.get("input_folder") or "").strip()
        auto_output = self._default_output_for(input_folder)
        if saved_output:
            self.var_output.set(saved_output)
            if auto_output:
                try:
                    if Path(saved_output).resolve() != Path(auto_output).resolve():
                        self._output_user_edited = True
                except OSError:
                    self._output_user_edited = True
        else:
            self.var_output.set(auto_output)

        resize = config.get("resize") or {}
        try:
            size_px = int(resize.get("size_px") or 0)
        except (TypeError, ValueError):
            size_px = 0
        if str(resize.get("mode") or "").lower() == "original":
            size_px = 0
        self._apply_resize_preset_from_size(size_px)

        jpeg = config.get("jpeg") or {}
        if "quality" not in jpeg and "jpeg_quality" in config:
            jpeg = {**jpeg, "quality": config["jpeg_quality"]}
        self.var_jpeg_enabled.set(bool(jpeg.get("enabled", True)))
        q = int(jpeg.get("quality", 85))
        self.var_jpeg_quality.set(q)
        self.slider_quality.set(q)
        self.lbl_quality.configure(text=str(q))
        self.var_jpeg_progressive.set(bool(jpeg.get("progressive", True)))
        self.var_jpeg_subsample.set(jpeg.get("subsampling") or "4:2:0")

        text = config.get("text") or {}
        self.var_text_enabled.set(bool(text.get("enabled", True)))
        self.var_text_content.set(text.get("content") or "")
        self.var_font_pct.set(float(text.get("font_size_percent", 3.0)))
        self.var_text_pos.set(
            normalize_position(text.get("position") or "bottom-middle") or "bottom-middle"
        )
        pad = text.get("padding", 35)
        if "margin" in text:
            pad = combine_trbl(pad, text.get("margin"))
        self._set_trbl_vars(self.var_text_padding, pad)

        sticker = config.get("sticker") or {}
        self.var_sticker_enabled.set(bool(sticker.get("enabled", False)))
        self.var_sticker_path.set(sticker.get("path") or "Sticker.png")
        self.var_sticker_pct.set(float(sticker.get("size_percent", 15)))
        pos = normalize_position(sticker.get("position") or "bottom-right") or "bottom-right"
        self.var_sticker_pos.set(pos)
        spad = sticker.get("padding", 35)
        if "margin" in sticker:
            spad = combine_trbl(spad, sticker.get("margin"))
        self._set_trbl_vars(self.var_sticker_padding, spad)

        cloud = config.get("cloud_upload") or {}
        self.var_cloud_enabled.set(bool(cloud.get("enabled", False)))
        # Album name is not persisted; always default to the input folder name.
        self.var_cloud_album.set(self._default_album_for(self.var_input.get()))
        self.var_cloud_api_key.set(cloud.get("api_key") or "")
        try:
            self.var_cloud_workers.set(max(1, min(32, int(cloud.get("max_workers") or 10))))
        except (TypeError, ValueError):
            self.var_cloud_workers.set(10)
        self._sync_cloud_options()

        self.reload_preview_bases()
        self.var_export_status.set(export_resize_label(config))

    def _on_preview_only_change(self, *_):
        self.schedule_preview()

    def _on_export_settings_change(self, *_):
        self.schedule_preview()
        self.schedule_jpeg_estimate()

    def schedule_preview(self):
        if self._preview_job is not None:
            self.after_cancel(self._preview_job)
        self._preview_job = self.after(DEBOUNCE_MS, self.refresh_preview)

    def schedule_jpeg_estimate(self):
        if self._estimate_job is not None:
            self.after_cancel(self._estimate_job)
        self._estimate_job = self.after(ESTIMATE_DEBOUNCE_MS, self.refresh_jpeg_estimate)

    def _ui_scaling(self):
        try:
            return max(0.5, float(self._get_widget_scaling()))
        except Exception:
            return 1.0

    def _preview_fit_box(self):
        if getattr(self, "_canvas_box", None):
            w, h = self._canvas_box
        else:
            self.preview_canvas.update_idletasks()
            cw = self.preview_canvas.winfo_width()
            ch = self.preview_canvas.winfo_height()
            if cw < 80 or ch < 80:
                try:
                    win_w = max(400, self.winfo_width())
                    win_h = max(300, self.winfo_height())
                except Exception:
                    win_w, win_h = 1280, 820
                cw = int(win_w * 0.50)
                ch = int(win_h * 0.55)
            w = max(32, cw - PREVIEW_MARGIN)
            h = max(32, ch - PREVIEW_MARGIN)
            self._canvas_box = (w, h)

        try:
            scale = float(self.var_preview_scale.get()) / 100.0
        except Exception:
            scale = 1.0
        scale = max(0.4, min(1.5, scale))
        return max(32, int(w * scale)), max(32, int(h * scale))

    def _show_preview_image(self, rgba_image):
        max_w, max_h = self._preview_fit_box()
        display = fit_for_display(rgba_image.convert("RGBA"), max_w, max_h)

        scaling = self._ui_scaling()
        ctk_w = max(1, int(round(display.width / scaling)))
        ctk_h = max(1, int(round(display.height / scaling)))

        ctk_img = ctk.CTkImage(
            light_image=display,
            dark_image=display,
            size=(ctk_w, ctk_h),
        )
        self._photo_refs["preview"] = ctk_img
        self.preview_label.configure(image=None)
        self.preview_label.configure(image=ctk_img)
        self.preview_label.place(relx=0.5, rely=0.5, anchor="center")

    def _fit_cached_preview(self):
        self._preview_job = None
        if self._last_preview_rgba is not None:
            self._show_preview_image(self._last_preview_rgba)

    def refresh_preview(self):
        self._preview_job = None
        try:
            config = self.form_to_config()
        except Exception:
            return

        status = export_resize_label(config)
        if self._preview_source_note:
            status = f"{status}  |  {self._preview_source_note}"
        self.var_export_status.set(status)

        size_px = (config.get("resize") or {}).get("size_px", 0)
        tab = (self.var_preview_tab.get() or "Landscape").strip()
        base = self._base_portrait if tab.lower().startswith("portrait") else self._base_landscape

        warning = None
        try:
            working = resize_image(base.copy(), size_px=size_px)
            preview, warn = apply_watermarks(working, config)
            if warn:
                warning = warn
        except Exception as e:
            preview = base.copy()
            warning = str(e)

        self._last_preview_rgba = preview.convert("RGBA")
        self._show_preview_image(self._last_preview_rgba)
        self.var_preview_warning.set(warning or "")

    def refresh_jpeg_estimate(self):
        self._estimate_job = None
        folder = self.var_input.get().strip()
        if not folder or not os.path.isdir(folder):
            self.var_jpeg_estimate.set("Select an input folder with images to estimate JPEG savings.")
            return
        try:
            config = self.form_to_config()
        except Exception:
            return

        self.var_jpeg_estimate.set("Estimating from first image…")
        self._estimate_token += 1
        token = self._estimate_token

        def worker():
            try:
                result = estimate_export_savings(folder, config)
                text = format_savings_estimate(result)
            except Exception as e:
                text = f"Estimate failed: {e}"

            def apply():
                if token == self._estimate_token:
                    self.var_jpeg_estimate.set(text)

            self.after(0, apply)

        threading.Thread(target=worker, daemon=True).start()

    def append_log(self, message):
        def _write():
            self.log_box.configure(state="normal")
            self.log_box.insert("end", message + "\n")
            self.log_box.see("end")
            self.log_box.configure(state="disabled")
            self.var_status.set(message[:80])

        self.after(0, _write)

    def on_reload(self):
        self.load_into_form(load_config())
        self.refresh_preview()
        self.refresh_jpeg_estimate()
        self.append_log(f"Reloaded {CONFIG_PATH}")

    def on_save(self):
        try:
            path = save_config(self.form_to_config())
            self.append_log(f"Saved {path}")
            self.var_status.set("Config saved")
            messagebox.showinfo("Saved", f"Config saved to:\n{path}")
        except Exception as e:
            messagebox.showerror("Save failed", str(e))

    def on_run(self):
        if self._running:
            return
        try:
            config = self.form_to_config()
        except Exception as e:
            messagebox.showerror("Invalid settings", str(e))
            return

        folder = config.get("input_folder") or ""
        if not folder or not os.path.isdir(folder):
            messagebox.showerror("Input folder", "Please set a valid input folder.")
            return

        text_on = config["text"].get("enabled") and config["text"].get("content")
        sticker_on = config["sticker"].get("enabled")
        if not text_on and not sticker_on:
            if not messagebox.askyesno(
                "No watermarks",
                "Text and sticker are both off. Continue with resize/JPEG only?",
            ):
                return

        cloud = config.get("cloud_upload") or {}
        if cloud.get("enabled") and not (cloud.get("api_key") or "").strip():
            messagebox.showerror(
                "Cloud upload",
                "Cloud upload is enabled but no Pixeldrain API key is set.",
            )
            return

        try:
            save_config(config)
        except Exception as e:
            messagebox.showerror("Save failed", str(e))
            return

        if not self._log_visible:
            self.toggle_log()

        self._running = True
        self._last_album_url = None
        self.btn_run.configure(state="disabled", text="Running…")
        self.append_log("— Batch started —")
        out = config.get("output_folder") or None

        def worker():
            album_url = None
            try:
                result = process_folder(
                    folder,
                    config=config,
                    output_folder=out,
                    progress_callback=self.append_log,
                )
                album_url = (result or {}).get("album_url")
            except Exception as e:
                self.append_log(f"Batch failed: {e}")
            finally:
                self.after(0, lambda url=album_url: self._batch_done(url))

        threading.Thread(target=worker, daemon=True).start()

    def _batch_done(self, album_url=None):
        self._running = False
        self.btn_run.configure(state="normal", text="Run Batch Process")
        self.append_log("— Batch finished —")
        self._last_album_url = album_url
        if album_url:
            self.var_status.set("Album ready")
            self.append_log(f"🔗 Album link: {album_url}")
        else:
            self.var_status.set("Batch finished")


def main():
    app = FlowMarkApp()
    app.mainloop()


if __name__ == "__main__":
    main()
