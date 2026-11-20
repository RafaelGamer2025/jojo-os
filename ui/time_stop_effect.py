"""Centered, expanding screenshot-negative effect for Tkinter windows."""

from __future__ import annotations

import math
import time
import tkinter as tk
from collections.abc import Callable, Iterator
from typing import Any

from ui.visual_effects import (
    expanding_circle_radius,
    invert_rgb,
    maximum_circle_radius,
    negative_circle_frame,
)


class TimeStopEffect:
    """Show a color-negative snapshot revealed by a centered expanding circle.

    Pillow's ImageGrab is used only to capture the target Tk window. If screen
    capture is unavailable, the fallback inverts native widget colors radially
    instead of covering the interface with an opaque overlay.
    """

    COLOR_OPTIONS = (
        ("background", "bg"),
        ("foreground", "fg"),
        ("activebackground",),
        ("activeforeground",),
        ("disabledbackground",),
        ("disabledforeground",),
        ("highlightbackground",),
        ("highlightcolor",),
        ("insertbackground",),
        ("selectbackground",),
        ("selectforeground",),
        ("selectcolor",),
        ("readonlybackground",),
        ("troughcolor",),
    )

    def __init__(
        self,
        window: tk.Misc,
        *,
        duration_ms: int = 7000,
        expansion_ms: int = 3500,
        frame_ms: int = 40,
        title: str = "ZA WARUDO",
        title_color: str = "#FFD700",
        ring_color: str = "#FFF4B0",
        on_complete: Callable[[], Any] | None = None,
    ) -> None:
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value <= 0
            for value in (duration_ms, expansion_ms, frame_ms)
        ):
            raise ValueError("Duração, expansão e intervalo precisam ser inteiros positivos.")

        self.window = window
        self.duration_ms = duration_ms
        self.expansion_ms = min(expansion_ms, duration_ms)
        self.frame_ms = frame_ms
        self.title = title
        self.title_color = title_color
        self.ring_color = ring_color
        self.on_complete = on_complete

        self.canvas: tk.Canvas | None = None
        self.running = False
        self.width = 0
        self.height = 0
        self.center_x = 0
        self.center_y = 0
        self.max_radius = 0
        self.started_at = 0.0
        self.after_id: str | None = None
        self.destroy_bind_id: str | None = None
        self.base_image = None
        self.photo_image = None
        self.image_item: int | None = None
        self.circle_item: int | None = None
        self.title_item: int | None = None
        self.fallback_colors: list[dict[str, Any]] = []
        self._completion_sent = False

    def start(self) -> bool:
        if self.running:
            return True
        try:
            if not self.window.winfo_exists():
                return False
            self.window.update_idletasks()
            self.width = max(1, int(self.window.winfo_width()))
            self.height = max(1, int(self.window.winfo_height()))
            if self.width <= 1 or self.height <= 1:
                return False
            self.center_x = self.width // 2
            self.center_y = self.height // 2
            self.max_radius = maximum_circle_radius(self.width, self.height)
            self.base_image = self._capture_window()
            self.destroy_bind_id = self.window.bind(
                "<Destroy>", self._on_window_destroy, add="+"
            )
        except (tk.TclError, TypeError, ValueError, OSError):
            return False

        self.running = True
        self.started_at = time.monotonic()
        if self.base_image is not None:
            self._create_image_overlay()
        else:
            self._collect_fallback_colors()
        self._tick()
        return True

    def _capture_window(self):
        try:
            from PIL import Image, ImageGrab

            left = int(self.window.winfo_rootx())
            top = int(self.window.winfo_rooty())
            image = ImageGrab.grab(
                bbox=(left, top, left + self.width, top + self.height)
            ).convert("RGB")
            if image.size != (self.width, self.height):
                image = image.resize(
                    (self.width, self.height),
                    Image.Resampling.BILINEAR,
                )
            return image
        except (ImportError, OSError, RuntimeError, tk.TclError, ValueError):
            return None

    def _create_image_overlay(self) -> None:
        try:
            self.canvas = tk.Canvas(
                self.window,
                width=self.width,
                height=self.height,
                highlightthickness=0,
                bd=0,
                takefocus=0,
            )
            self.canvas.place(x=0, y=0, relwidth=1, relheight=1)
            self.image_item = self.canvas.create_image(0, 0, anchor="nw")
            self.circle_item = self.canvas.create_oval(
                0,
                0,
                0,
                0,
                outline=self.ring_color,
                width=3,
                tags="time-stop-circle",
            )
            font_size = max(16, min(40, self.width // 10))
            self.title_item = self.canvas.create_text(
                self.center_x,
                max(28, self.height // 7),
                text=self.title,
                fill=self.title_color,
                font=("Impact", font_size, "bold"),
                tags="time-stop-title",
            )
        except tk.TclError:
            self._destroy_canvas()
            self.base_image = None
            self._collect_fallback_colors()

    def _iter_widgets(self, widget: tk.Misc) -> Iterator[tk.Misc]:
        yield widget
        try:
            children = widget.winfo_children()
        except tk.TclError:
            return
        for child in children:
            if child is not self.canvas:
                yield from self._iter_widgets(child)

    @staticmethod
    def _inverted_color(widget: tk.Misc, color: Any) -> str | None:
        if not isinstance(color, str) or not color:
            return None
        try:
            channels_16 = widget.winfo_rgb(color)
        except (tk.TclError, TypeError, ValueError):
            return None
        if len(channels_16) != 3:
            return None
        channels_8 = tuple(
            max(0, min(255, round(channel / 65535 * 255)))
            for channel in channels_16
        )
        red, green, blue = invert_rgb(channels_8)
        return f"#{red:02X}{green:02X}{blue:02X}"

    def _collect_fallback_colors(self) -> None:
        self.fallback_colors.clear()
        try:
            origin_x = int(self.window.winfo_rootx())
            origin_y = int(self.window.winfo_rooty())
        except tk.TclError:
            return

        for widget in self._iter_widgets(self.window):
            try:
                options = set(widget.keys())
                center_x = widget.winfo_rootx() + widget.winfo_width() / 2 - origin_x
                center_y = widget.winfo_rooty() + widget.winfo_height() / 2 - origin_y
                originals: dict[str, str] = {}
                inversions: dict[str, str] = {}
                for aliases in self.COLOR_OPTIONS:
                    option = next((name for name in aliases if name in options), None)
                    if option is None:
                        continue
                    original = widget.cget(option)
                    inverted = self._inverted_color(widget, original)
                    if inverted is not None:
                        originals[option] = original
                        inversions[option] = inverted
                if originals:
                    self.fallback_colors.append(
                        {
                            "widget": widget,
                            "distance": math.hypot(
                                center_x - self.center_x,
                                center_y - self.center_y,
                            ),
                            "originals": originals,
                            "inversions": inversions,
                            "inverted": False,
                        }
                    )
            except (tk.TclError, TypeError, ValueError):
                continue

    def _apply_fallback(self, radius: int) -> None:
        for entry in self.fallback_colors:
            should_invert = entry["distance"] <= radius
            if should_invert == entry["inverted"]:
                continue
            widget = entry["widget"]
            options = entry["inversions"] if should_invert else entry["originals"]
            try:
                if widget.winfo_exists():
                    widget.configure(**options)
                    entry["inverted"] = should_invert
            except (tk.TclError, TypeError):
                continue

    def _render_image(self, radius: int) -> None:
        if self.canvas is None or self.image_item is None or self.base_image is None:
            return
        try:
            from PIL import ImageTk

            image = negative_circle_frame(self.base_image, radius)
            self.photo_image = ImageTk.PhotoImage(image, master=self.window)
            self.canvas.itemconfigure(self.image_item, image=self.photo_image)
            self.canvas.tag_raise("time-stop-circle")
            self.canvas.tag_raise("time-stop-title")
            if self.circle_item is not None:
                self.canvas.coords(
                    self.circle_item,
                    self.center_x - radius,
                    self.center_y - radius,
                    self.center_x + radius,
                    self.center_y + radius,
                )
        except (ImportError, tk.TclError, ValueError):
            self._destroy_canvas()
            self.base_image = None
            self.photo_image = None
            self._collect_fallback_colors()
            self._apply_fallback(radius)

    def _tick(self) -> None:
        self.after_id = None
        if not self.running:
            return
        try:
            if not self.window.winfo_exists():
                self.stop()
                return
            elapsed = max(0.0, time.monotonic() - self.started_at)
            radius = expanding_circle_radius(
                elapsed,
                self.expansion_ms / 1000,
                self.max_radius,
            )
            if self.base_image is not None:
                self._render_image(radius)
            else:
                self._apply_fallback(radius)
            if elapsed * 1000 >= self.duration_ms:
                self.stop()
                return
            self.after_id = self.window.after(self.frame_ms, self._tick)
        except (tk.TclError, TypeError, ValueError):
            self.stop()

    def _restore_fallback(self) -> None:
        for entry in self.fallback_colors:
            widget = entry["widget"]
            try:
                if widget.winfo_exists():
                    widget.configure(**entry["originals"])
            except (tk.TclError, TypeError):
                continue
        self.fallback_colors.clear()

    def _destroy_canvas(self) -> None:
        if self.canvas is None:
            return
        try:
            if self.canvas.winfo_exists():
                self.canvas.destroy()
        except tk.TclError:
            pass
        finally:
            self.canvas = None
            self.photo_image = None
            self.image_item = None
            self.circle_item = None
            self.title_item = None

    def _on_window_destroy(self, event: tk.Event) -> None:
        if getattr(event, "widget", None) is self.window:
            self.stop()

    def stop(self) -> None:
        was_running = self.running
        self.running = False
        if self.after_id is not None:
            try:
                self.window.after_cancel(self.after_id)
            except tk.TclError:
                pass
            self.after_id = None
        self._destroy_canvas()
        self._restore_fallback()
        self.base_image = None
        if self.destroy_bind_id is not None:
            try:
                self.window.unbind("<Destroy>", self.destroy_bind_id)
            except tk.TclError:
                pass
            self.destroy_bind_id = None
        if was_running and not self._completion_sent:
            self._completion_sent = True
            if self.on_complete is not None:
                try:
                    self.on_complete()
                except tk.TclError:
                    pass
