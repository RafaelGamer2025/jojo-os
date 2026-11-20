# calc_window.py
import os
import time
import tkinter as tk
from typing import ClassVar

import pygame
from pygame import mixer

from core.safe_math import CalculationError, safe_calculate
from ui.themes.hacker_theme import HackerTheme
from ui.themes.jojo_theme import JoJoTheme
from ui.time_stop_effect import TimeStopEffect
from ui.visual_effects import expanding_circle_radii, invert_rgb


def localizar_pasta_soms():
    """Busca a pasta 'soms' subindo os níveis de diretório até encontrar"""
    diretorio_atual = os.path.dirname(os.path.abspath(__file__))
    for _ in range(5):
        tentativa = os.path.join(diretorio_atual, "soms")
        if os.path.exists(tentativa): 
            return tentativa
        diretorio_atual = os.path.dirname(diretorio_atual)
    return None

class JoJoCalc:
    EFFECT_DURATION_MS = 7000
    EFFECT_EXPANSION_MS = 3500
    EFFECT_FRAME_MS = 40
    COLOR_OPTIONS: ClassVar[dict[str, tuple[str, ...]]] = {
        "background": ("background", "bg"),
        "foreground": ("foreground", "fg"),
        "activebackground": ("activebackground",),
        "activeforeground": ("activeforeground",),
        "disabledbackground": ("disabledbackground",),
        "disabledforeground": ("disabledforeground",),
        "highlightbackground": ("highlightbackground",),
        "highlightcolor": ("highlightcolor",),
        "insertbackground": ("insertbackground",),
        "selectbackground": ("selectbackground",),
        "selectforeground": ("selectforeground",),
        "selectcolor": ("selectcolor",),
        "readonlybackground": ("readonlybackground",),
        "troughcolor": ("troughcolor",),
    }

    def __init__(self, master, theme_atual="JOJO", sound_mode="ora"):
        self.sound_mode = sound_mode
        self.master = master
        # Define o tema com base na escolha do sistema
        self.theme_name = theme_atual
        self.theme = JoJoTheme if theme_atual == "JOJO" else HackerTheme
        
        self.master.title("JOJO CALCULATOR" if theme_atual == "JOJO" else "CLEITAN-OS TERMINAL")
        self.master.geometry("400x600")
        self.master.configure(bg="#000000") # Fundo sempre preto para ambos

        self.system_root = self.master.winfo_toplevel()
        
        # Configuração de sons e estados
        self.hold_job = None 
        self.was_held = False 
        self.ee_activated = False 
        self.sound_channel = None
        self.last_error = ""

        # Definição de cores de Inversão (Efeito Especial)
        if theme_atual == "JOJO":
            self.neg_black, self.neg_gold = "#ffffff", "#005aff"
            self.neg_purple, self.neg_pink = "#a0ff5f", "#00ffbf"
            self.text_color = "#FFD700" # Dourado JoJo
        else:
            # Cores "Matrix" para o modo Hacker
            self.neg_black, self.neg_gold = "#000000", "#00FF41"
            self.neg_purple, self.neg_pink = "#003B00", "#008F11"
            self.text_color = "#00FF00" # Verde Hacker

        self.canvas_overlay = None
        self.radius = 0
        self.effect_animation_job = None
        self.effect_end_job = None
        self.effect_started_at = None
        self.original_widget_colors = {}
        self.destroy_bind_id = None
        self.destroyed = False
        self.time_stop_effect = None

        # Inicialização de Sons
        try:
            mixer.init()
            pasta = localizar_pasta_soms()
            if not pasta:
                raise FileNotFoundError("Pasta de sons opcional não encontrada.")
            if self.sound_mode == "muda":
                # DIO
                self.click_sound = mixer.Sound(os.path.join(pasta, "inutil.wav"))
                self.hold_sound = mixer.Sound(os.path.join(pasta, "dio-time-stop.wav"))
            else:
                # JOTARO
                self.click_sound = mixer.Sound(os.path.join(pasta, "ora-jotaro.wav"))
                self.hold_sound = mixer.Sound(os.path.join(pasta, "star-platinum-zw.wav"))
        except (pygame.error, OSError, TypeError):
            self.click_sound = None
            self.hold_sound = None    
        self.result_var = tk.StringVar()
        self.buttons_list = [] 
        self.create_widgets()
        try:
            self.destroy_bind_id = self.system_root.bind(
                "<Destroy>", self._on_window_destroy, add="+"
            )
        except tk.TclError:
            self.destroy_bind_id = None

    def play_sound(self, sound_type):
        try:
            sound = self.click_sound if sound_type == "click" else self.hold_sound
            if sound is None:
                return
            if self.sound_channel is not None and self.sound_channel.get_busy():
                self.sound_channel.stop()
            self.sound_channel = sound.play()
        except pygame.error:
            self.sound_channel = None

    def stop_time_effect(self):
        if self.ee_activated or self.destroyed:
            return
        self.ee_activated = True
        self.was_held = True # Marca que foi um clique longo
        self.play_sound("hold")

        try:
            self._cancel_effect_jobs()
            self.time_stop_effect = TimeStopEffect(
                self.master,
                duration_ms=self.EFFECT_DURATION_MS,
                expansion_ms=self.EFFECT_EXPANSION_MS,
                frame_ms=self.EFFECT_FRAME_MS,
                title="ZA WARUDO",
                title_color=self.text_color,
                ring_color=self.neg_gold,
                on_complete=self._on_time_effect_complete,
            )
            if not self.time_stop_effect.start():
                self.restore_colors()
        except (tk.TclError, OSError):
            self.restore_colors()

    def _on_time_effect_complete(self):
        self.time_stop_effect = None
        self.effect_started_at = None
        self.radius = 0
        self.ee_activated = False

    def _iter_widgets(self, widget):
        yield widget
        try:
            children = widget.winfo_children()
        except tk.TclError:
            return
        for child in children:
            yield from self._iter_widgets(child)

    def _widget_color(self, widget, option):
        try:
            return widget.cget(option)
        except (tk.TclError, TypeError):
            return None

    def _inverted_color(self, widget, color):
        if not isinstance(color, str) or not color:
            return None
        try:
            channels_16 = widget.winfo_rgb(color)
        except (tk.TclError, TypeError, ValueError):
            return None
        if (
            not isinstance(channels_16, (tuple, list))
            or len(channels_16) != 3
            or any(
                isinstance(channel, bool)
                or not isinstance(channel, int)
                for channel in channels_16
            )
        ):
            return None
        channels_8 = tuple(
            max(0, min(255, round(channel / 65535 * 255)))
            for channel in channels_16
        )
        inverted = invert_rgb(channels_8)
        return f"#{inverted[0]:02x}{inverted[1]:02x}{inverted[2]:02x}"

    def _invert_widget_colors(self):
        self.original_widget_colors = {}
        for widget in self._iter_widgets(self.system_root):
            try:
                options = set(widget.keys())
            except tk.TclError:
                continue
            for option_aliases in self.COLOR_OPTIONS.values():
                option = next(
                    (candidate for candidate in option_aliases if candidate in options),
                    None,
                )
                if option is None:
                    continue
                original = self._widget_color(widget, option)
                if original is None:
                    continue
                self.original_widget_colors.setdefault(widget, {})[option] = original
                inverted = self._inverted_color(widget, original)
                if inverted is None:
                    continue
                try:
                    widget.configure(**{option: inverted})
                except (tk.TclError, TypeError):
                    continue

    def _restore_widget_colors(self):
        for widget, colors in self.original_widget_colors.items():
            for option, original in colors.items():
                try:
                    widget.configure(**{option: original})
                except (tk.TclError, TypeError):
                    pass
        self.original_widget_colors = {}

    def _cancel_after(self, attribute):
        job = getattr(self, attribute)
        if job is None:
            return
        try:
            self.system_root.after_cancel(job)
        except tk.TclError:
            pass
        finally:
            setattr(self, attribute, None)

    def _cancel_effect_jobs(self):
        self._cancel_after("effect_animation_job")
        self._cancel_after("effect_end_job")

    def _destroy_canvas(self):
        if self.canvas_overlay is None:
            return
        try:
            self.canvas_overlay.destroy()
        except tk.TclError:
            pass
        finally:
            self.canvas_overlay = None

    def animate_expansion(self, w=None, h=None):
        self.effect_animation_job = None
        if self.canvas_overlay is None or not self.ee_activated:
            return

        try:
            if w is None:
                w = int(self.canvas_overlay.winfo_width())
                if w <= 1:
                    w = int(self.master.winfo_width())
            if h is None:
                h = int(self.canvas_overlay.winfo_height())
                if h <= 1:
                    h = int(self.canvas_overlay.winfo_reqheight())
            w = max(1, w)
            h = max(1, h)
            elapsed = max(0.0, time.monotonic() - (self.effect_started_at or 0.0))
            max_radius = max(1, min(w, h) // 2)
            radii = expanding_circle_radii(
                elapsed,
                self.EFFECT_DURATION_MS / 1000,
                max_radius,
                count=3,
            )
        except (tk.TclError, TypeError, ValueError):
            self.restore_colors()
            return

        self.canvas_overlay.delete("pulse")
        cx, cy = w // 2, h // 2
        ring_colors = (self.neg_pink, self.neg_gold, self.text_color)
        for index, radius in enumerate(radii):
            self.canvas_overlay.create_oval(
                cx - radius,
                cy - radius,
                cx + radius,
                cy + radius,
                outline=ring_colors[index],
                width=3,
                tags="pulse",
            )
        self.radius = max(radii, default=0)
        self.canvas_overlay.tag_raise("title")
        self.effect_animation_job = self.system_root.after(
            self.EFFECT_FRAME_MS, self.animate_expansion
        )

    def restore_colors(self):
        effect = self.time_stop_effect
        self.time_stop_effect = None
        if effect is not None:
            effect.stop()
        self._cancel_effect_jobs()
        self._restore_widget_colors()
        self._destroy_canvas()
        self.effect_started_at = None
        self.radius = 0
        self.ee_activated = False

    def _on_window_destroy(self, event=None):
        if event is not None and event.widget is not self.system_root:
            return
        self.destroyed = True
        self._cancel_after("hold_job")
        self.restore_colors()

    def on_press(self, char):
        self.was_held = False
        # Se segurar por mais de 400ms, ativa o ZA WARUNDO / HACK
        self.hold_job = self.master.after(400, self.stop_time_effect)

    def on_release(self, char):
        if self.hold_job:
            try:
                self.master.after_cancel(self.hold_job)
            except tk.TclError:
                pass
            self.hold_job = None
        
        if not self.was_held:
            if char == 'C':
                self.result_var.set("")
                self.last_error = ""
                self.status_label.config(text="", fg=self.text_color)
            elif char == '=':
                try:
                    self.result_var.set(str(safe_calculate(self.result_var.get())))
                except CalculationError as exc:
                    self.result_var.set("ERROR")
                    self.last_error = str(exc)
                    self.status_label.config(text=self.last_error, fg="#FF6B6B")
                else:
                    self.last_error = ""
                    self.status_label.config(text="", fg=self.text_color)
            else: 
                self.result_var.set(self.result_var.get() + char)
            self.play_sound("click")

    def create_widgets(self):
        font_name = "Impact" if self.theme_name == "JOJO" else "Courier New"
        
        self.display = tk.Entry(self.master, textvariable=self.result_var, font=(font_name, 32), 
                           bg="#1a1a1a", fg=self.text_color, bd=5, relief="sunken", justify='right')
        self.display.pack(expand=True, fill='both', padx=10, pady=10)
        self.status_label = tk.Label(self.master, text="", bg="#000000", fg=self.text_color, font=("Arial", 9))
        self.status_label.pack(fill="x", padx=10)

        self.btn_frame = tk.Frame(self.master, bg="#000000")
        self.btn_frame.pack(expand=True, fill='both', padx=5, pady=5)

        btns = ['7', '8', '9', '/', '4', '5', '6', '*', '1', '2', '3', '-', '0', 'C', '=', '+']
        r, c = 0, 0
        for b in btns:
            if b.isdigit():
                color = getattr(self.theme, 'PURPLE', "#003b00")
            else:
                color = getattr(self.theme, 'PINK', "#008f11")
            
            btn = tk.Button(self.btn_frame, text=b, font=(font_name, 20), 
                            bg=color, fg=self.text_color,
                            activebackground=self.text_color, activeforeground="black",
                            relief="raised" if self.theme_name == "JOJO" else "flat")
            
            # Binds para clique longo e curto
            btn.bind("<ButtonPress-1>", lambda e, b=b: self.on_press(b))
            btn.bind("<ButtonRelease-1>", lambda e, b=b: self.on_release(b))
            
            btn.grid(row=r, column=c, sticky="nsew", padx=2, pady=2)
            self.buttons_list.append((btn, b))
            
            c += 1
            if c > 3: 
                c = 0
                r += 1
        
        for i in range(4): 
            self.btn_frame.grid_columnconfigure(i, weight=1)
        for i in range(4):
            self.btn_frame.grid_rowconfigure(i, weight=1)

# Função para testar a janela sozinha
if __name__ == "__main__":
    root = tk.Tk()
    app = JoJoCalc(root, theme_atual="HACKER") # Teste manual
    root.mainloop()
