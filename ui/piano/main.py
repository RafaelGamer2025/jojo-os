from __future__ import annotations

import tkinter as tk

import numpy as np
import pygame

SAMPLE_RATE = 44_100
NOTES = {
    "a": 130.81, "w": 138.59, "s": 146.83, "e": 155.56, "d": 164.81,
    "f": 174.61, "t": 185.00, "g": 196.00, "y": 207.65, "h": 220.00,
    "u": 233.08, "j": 246.94, "k": 261.63, "o": 277.18, "l": 293.66,
    "p": 311.13, ";": 329.63, "'": 349.23, "]": 369.99, "\\": 392.00,
    "z": 415.30, "x": 466.16, "c": 493.88, "v": 523.25, "b": 554.37,
    "n": 587.33, "m": 622.25, ",": 659.25, ".": 698.46, "/": 783.99,
    "1": 830.61, "2": 880.00, "3": 932.33, "4": 987.77, "5": 1046.50,
    "6": 1108.73, "7": 1174.66, "8": 1244.51, "9": 1318.51, "0": 1396.91,
    "-": 1479.98, "=": 1567.98,
}
_KEYSYM_ALIASES = {
    "semicolon": ";", "apostrophe": "'", "quotedbl": "'", "bracketright": "]",
    "backslash": "\\", "comma": ",", "period": ".", "slash": "/",
    "minus": "-", "equal": "=",
}


class Synth:
    """Síntese simples com cache de notas e volume conservador."""

    def __init__(self):
        self.cache: dict[float, pygame.mixer.Sound] = {}

    def create_sound(self, frequency: float, duration: float = 0.5) -> pygame.mixer.Sound:
        cycles = max(1, round(frequency * duration))
        sample_count = max(2, round(SAMPLE_RATE * cycles / frequency))
        loop_frequency = cycles * SAMPLE_RATE / sample_count
        time = np.arange(sample_count, dtype=np.float32) / SAMPLE_RATE
        wave = (
            np.sin(2 * np.pi * loop_frequency * time)
            + 0.35 * np.sin(2 * np.pi * loop_frequency * 2 * time)
            + 0.15 * np.sin(2 * np.pi * loop_frequency * 3 * time)
        )
        peak = float(np.max(np.abs(wave))) if wave.size else 0.0
        if peak > 0:
            wave = wave / peak * 0.28
        audio = np.asarray(wave * 32767, dtype=np.int16)
        stereo = np.ascontiguousarray(np.column_stack((audio, audio)))
        return pygame.sndarray.make_sound(stereo)

    def play(self, frequency: float) -> pygame.mixer.Channel:
        if frequency not in self.cache:
            self.cache[frequency] = self.create_sound(frequency)
        channel = pygame.mixer.find_channel(force=True)
        if channel is None:
            raise RuntimeError("Não há canal de áudio disponível.")
        channel.play(self.cache[frequency], loops=-1)
        return channel


class PianoWindow:
    """Piano em janela filha; importar o módulo não abre janelas nem inicia o mixer."""

    def __init__(self, master, theme=None):
        self.window = tk.Toplevel(master)
        self.window.title("JOJO-OS // PIANO")
        self.window.geometry("900x390")
        self.window.minsize(760, 350)
        self.window.configure(bg=getattr(theme, "BLACK", "#101014"))
        self.window.transient(master)

        self.bg = getattr(theme, "BLACK", "#101014")
        self.accent = getattr(theme, "PURPLE", "#6A0DAD")
        self.foreground = getattr(theme, "GOLD", "#FFD700")
        self.white_key = "#F4F1E8"
        self.synth = Synth()
        self.channels_active: dict[str, pygame.mixer.Channel] = {}
        self.pressed_keys: set[str] = set()
        self.sustained_keys: set[str] = set()
        self.sustain = False
        self.audio_ready = False

        self._build_ui()
        self._init_audio()
        self.window.bind("<KeyPress>", self.key_press)
        self.window.bind("<KeyRelease>", self.key_release)
        self.window.bind("<Destroy>", self._on_destroy, add="+")
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.focus_force()

    def _init_audio(self):
        try:
            if pygame.mixer.get_init() is None:
                pygame.mixer.pre_init(SAMPLE_RATE, -16, 2, 512)
                pygame.mixer.init()
            pygame.mixer.set_num_channels(max(128, pygame.mixer.get_num_channels()))
            self.audio_ready = True
            self.status.config(text="SOM LIGADO — Espaço ativa/desativa sustain")
        except pygame.error:
            self.audio_ready = False
            self.status.config(text="Áudio indisponível neste dispositivo; a interface continua aberta.")

    def _build_ui(self):
        tk.Label(
            self.window,
            text="PIANO JOJO-OS",
            bg=self.bg,
            fg=self.foreground,
            font=("Impact", 22),
        ).pack(pady=(12, 4))

        self.canvas = tk.Canvas(
            self.window,
            width=880,
            height=240,
            bg="#777777",
            highlightthickness=0,
        )
        self.canvas.pack(padx=10, pady=8, fill="x")

        white_keys = [("C", "A"), ("D", "S"), ("E", "D"), ("F", "F"), ("G", "G"), ("A", "H"), ("B", "J")]
        for index, (note, key) in enumerate(white_keys):
            x = index * 120
            self.canvas.create_rectangle(x, 0, x + 120, 240, fill=self.white_key, outline="#222222", width=2)
            self.canvas.create_text(x + 60, 215, text=f"{note}\n{key}", fill="#111111", font=("Arial", 11))

        black_keys = [("C#", "W", 90), ("D#", "E", 210), ("F#", "T", 450), ("G#", "Y", 570), ("A#", "U", 690)]
        for note, key, x in black_keys:
            self.canvas.create_rectangle(x, 0, x + 60, 135, fill="#111111", outline="#000000", width=2)
            self.canvas.create_text(x + 30, 112, text=f"{note}\n{key}", fill="#FFFFFF", font=("Arial", 9))

        self.status = tk.Label(
            self.window,
            text="Iniciando áudio...",
            bg=self.bg,
            fg=self.foreground,
            font=("Consolas", 10),
        )
        self.status.pack(pady=(2, 4))
        tk.Label(
            self.window,
            text="Teclas: A W S E D F T G Y H U J K O L P ; ' ] \\ Z X C V B N M , . / 1–0 - =  |  Espaço = Sustain",
            bg=self.bg,
            fg="#CCCCCC",
            font=("Consolas", 9),
            wraplength=860,
        ).pack(pady=(0, 10))

    @staticmethod
    def _key_for_event(event) -> str | None:
        char = getattr(event, "char", "")
        if char:
            candidate = char.lower()
            if candidate in NOTES or candidate == " ":
                return candidate
        keysym = getattr(event, "keysym", "").lower()
        return _KEYSYM_ALIASES.get(keysym, keysym)

    def key_press(self, event):
        key = self._key_for_event(event)
        if key == "space":
            if not self.sustain:
                self.sustain = True
                self.status.config(text="SUSTAIN LIGADO")
            return "break"
        if key == " ":
            if not self.sustain:
                self.sustain = True
                self.status.config(text="SUSTAIN LIGADO")
            return "break"
        if key not in NOTES or key in self.pressed_keys or not self.audio_ready:
            return "break"
        self.pressed_keys.add(key)
        try:
            self.channels_active[key] = self.synth.play(NOTES[key])
        except (pygame.error, RuntimeError):
            self.status.config(text="Não foi possível tocar esta nota.")
        return "break"

    def key_release(self, event):
        key = self._key_for_event(event)
        if key in {"space", " "}:
            if self.sustain:
                self.sustain = False
                self.status.config(text="SUSTAIN DESLIGADO")
                self._stop_sustained()
            return "break"
        if key not in NOTES:
            return "break"
        self.pressed_keys.discard(key)
        channel = self.channels_active.get(key)
        if channel is None:
            return "break"
        if self.sustain:
            self.sustained_keys.add(key)
        else:
            channel.fadeout(100)
            self.channels_active.pop(key, None)
        return "break"

    def _stop_sustained(self):
        for key in list(self.sustained_keys):
            channel = self.channels_active.pop(key, None)
            if channel is not None:
                channel.fadeout(100)
        self.sustained_keys.clear()

    def _on_destroy(self, event):
        if event.widget is self.window:
            self._stop_all_notes()

    def _stop_all_notes(self):
        for channel in list(self.channels_active.values()):
            try:
                channel.fadeout(60)
            except pygame.error:
                pass
        self.channels_active.clear()
        self.pressed_keys.clear()
        self.sustained_keys.clear()

    def close(self):
        self._stop_all_notes()
        try:
            self.window.destroy()
        except tk.TclError:
            pass


if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()
    PianoWindow(root)
    root.mainloop()
