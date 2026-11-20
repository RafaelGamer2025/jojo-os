from __future__ import annotations

import math
import shlex
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

from core.workspace import (
    WORKSPACE_DIR,
    ensure_workspace,
    resolve_workspace_path,
    validate_filename,
)
from ui.visual_effects import expanding_circle_radii, psychedelic_palette

MAX_TEXT_BYTES = 1_000_000
PSYCHEDELIC_DURATION_SECONDS = 7.0
PSYCHEDELIC_FRAME_INTERVAL_MS = 50
PSYCHEDELIC_RING_COUNT = 5


class TerminalWindow:
    """Terminal virtual do JoJo-OS; nunca executa comandos do Windows/Linux."""

    def __init__(self, master, workspace: str | Path | None = None):
        self.win = tk.Toplevel(master)
        self.win.title("JOJO-OS // TERMINAL VIRTUAL")
        self.win.geometry("900x540")
        self.win.configure(bg="black")
        self._effect_after_id = None
        self._effect_started_at = None
        self._closed = False

        self.workspace = ensure_workspace(workspace or WORKSPACE_DIR)
        self.current_path = self.workspace

        self.output = tk.Text(
            self.win,
            bg="black",
            fg="lime",
            insertbackground="lime",
            font=("Consolas", 11),
            wrap=tk.WORD,
            state=tk.DISABLED,
        )
        self.output.pack(fill="both", expand=True, padx=10, pady=(10, 6))

        self.entry = tk.Entry(
            self.win,
            bg="#111111",
            fg="lime",
            insertbackground="lime",
            font=("Consolas", 12),
        )
        self.entry.pack(fill="x", padx=10, pady=(4, 10))
        self.entry.bind("<Return>", self.executar)
        self.entry.focus_set()

        self._original_colors = {
            "window": self._capture_colors(self.win),
            "output": self._capture_colors(self.output),
            "entry": self._capture_colors(self.entry),
        }
        self._effect_canvas = tk.Canvas(
            self.win,
            bg=self._original_colors["window"]["bg"],
            bd=0,
            height=48,
            highlightthickness=0,
        )
        self._effect_canvas.pack_forget()
        self.win.protocol("WM_DELETE_WINDOW", self._close)

        self.escrever("JOJO-OS TERMINAL VIRTUAL\n")
        self.escrever(
            "Modo seguro: os comandos operam somente em data/workspace.\nDigite /help para ver a lista.\n"
        )
        self._prompt()

    @staticmethod
    def _capture_colors(widget: tk.Misc) -> dict[str, str]:
        colors = {}
        for option in ("bg", "fg", "insertbackground"):
            try:
                colors[option] = widget.cget(option)
            except tk.TclError:
                continue
        return colors

    def _restore_effect_colors(self) -> None:
        for name, widget in (
            ("window", self.win),
            ("output", self.output),
            ("entry", self.entry),
        ):
            try:
                widget.configure(**self._original_colors[name])
            except tk.TclError:
                continue
        try:
            self._effect_canvas.configure(bg=self._original_colors["window"]["bg"])
            self._effect_canvas.delete("psychedelic-ring")
            self._effect_canvas.pack_forget()
        except tk.TclError:
            pass

    def _start_psychedelic_effect(self) -> None:
        if self._effect_after_id is not None:
            try:
                self.win.after_cancel(self._effect_after_id)
            except tk.TclError:
                pass
            self._effect_after_id = None
        self._effect_started_at = time.monotonic()
        self._animate_psychedelic_effect()

    def _animate_psychedelic_effect(self) -> None:
        self._effect_after_id = None
        if self._closed or self._effect_started_at is None:
            return
        try:
            if not self.win.winfo_exists():
                self._effect_started_at = None
                return
        except tk.TclError:
            self._effect_started_at = None
            return

        elapsed = time.monotonic() - self._effect_started_at
        if elapsed >= PSYCHEDELIC_DURATION_SECONDS:
            self._effect_started_at = None
            self._restore_effect_colors()
            return

        background, foreground, accent = psychedelic_palette(elapsed)
        self.win.configure(bg=background)
        self.output.configure(
            bg=background,
            fg=foreground,
            insertbackground=foreground,
        )
        self.entry.configure(
            bg=background,
            fg=foreground,
            insertbackground=foreground,
        )
        self._effect_canvas.configure(bg=background)
        if self._effect_canvas.winfo_manager() != "pack":
            self._effect_canvas.pack(fill="x", padx=10, pady=(0, 4))

        width = max(1, self._effect_canvas.winfo_width())
        height = max(1, self._effect_canvas.winfo_height())
        center_x = width / 2
        center_y = height / 2
        maximum_radius = max(1, min(width, height) // 2)
        self._effect_canvas.delete("psychedelic-ring")
        for index, radius in enumerate(
            expanding_circle_radii(
                elapsed,
                PSYCHEDELIC_DURATION_SECONDS,
                maximum_radius,
                count=PSYCHEDELIC_RING_COUNT,
            )
        ):
            if radius <= 0:
                continue
            ring_color = accent if index % 2 == 0 else foreground
            self._effect_canvas.create_oval(
                center_x - radius,
                center_y - radius,
                center_x + radius,
                center_y + radius,
                outline=ring_color,
                width=2,
                tags="psychedelic-ring",
            )

        remaining_ms = math.ceil((PSYCHEDELIC_DURATION_SECONDS - elapsed) * 1000)
        self._effect_after_id = self.win.after(
            min(PSYCHEDELIC_FRAME_INTERVAL_MS, max(1, remaining_ms)),
            self._animate_psychedelic_effect,
        )

    def _stop_psychedelic_effect(self) -> None:
        if self._effect_after_id is not None:
            try:
                self.win.after_cancel(self._effect_after_id)
            except tk.TclError:
                pass
            self._effect_after_id = None
        self._effect_started_at = None
        self._restore_effect_colors()

    def _close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._stop_psychedelic_effect()
        self.win.destroy()

    def escrever(self, texto: str) -> None:
        self.output.config(state=tk.NORMAL)
        self.output.insert(tk.END, str(texto))
        self.output.see(tk.END)
        self.output.config(state=tk.DISABLED)

    def _prompt(self) -> None:
        relative = (
            "."
            if self.current_path == self.workspace
            else self.current_path.relative_to(self.workspace).as_posix()
        )
        self.escrever(f"\nJOJO:/{relative}> ")

    def _resolve(self, target: str = ".") -> Path:
        return resolve_workspace_path(self.workspace, self.current_path / target)

    def _help(self) -> None:
        self.escrever(
            "Comandos do terminal virtual:\n"
            "  /help                  mostra esta ajuda\n"
            "  /clear                 limpa a tela\n"
            "  pwd                    mostra a pasta atual\n"
            "  dir | ls               lista arquivos e pastas\n"
            "  cd [pasta]             navega somente dentro do workspace\n"
            "  cat arquivo.txt        mostra texto UTF-8 de até 1 MB\n"
            "  mkdir pasta            cria uma pasta\n"
            "  touch arquivo.txt      cria um arquivo vazio\n"
            "  echo texto             imprime texto\n"
            "  rm arquivo.txt         pede confirmação e apaga um arquivo\n"
            "  /za_warudo             efeito visual local de 7 segundos\n"
            "  /psychedelic           alias do efeito psicodélico\n"
            "  exit                   fecha a janela\n\n"
            "Comandos externos, pipes, redirecionamentos e execução de programas estão desativados.\n"
        )

    def _list_directory(self) -> None:
        try:
            entries = sorted(
                self.current_path.iterdir(),
                key=lambda p: (not p.is_dir(), p.name.casefold()),
            )
            if not entries:
                self.escrever("(pasta vazia)\n")
                return
            for entry in entries:
                if entry.is_symlink():
                    continue
                marker = "<DIR> " if entry.is_dir() else "      "
                self.escrever(f"{marker}{entry.name}\n")
        except OSError as exc:
            self.escrever(f"Não foi possível listar: {exc}\n")

    def _read_text(self, filename: str) -> None:
        try:
            path = self._resolve(filename)
            if not path.is_file() or path.is_symlink():
                self.escrever("Arquivo não encontrado ou tipo não permitido.\n")
                return
            if path.stat().st_size > MAX_TEXT_BYTES:
                self.escrever("Arquivo acima do limite de prévia de 1 MB.\n")
                return
            self.escrever(path.read_text(encoding="utf-8") + "\n")
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            self.escrever(f"Não foi possível ler o arquivo: {exc}\n")

    def executar(self, _event=None) -> None:
        raw = self.entry.get().strip()
        self.entry.delete(0, tk.END)
        if not raw:
            self._prompt()
            return

        if raw == "/clear":
            self.output.config(state=tk.NORMAL)
            self.output.delete("1.0", tk.END)
            self.output.config(state=tk.DISABLED)
            self._prompt()
            return

        self.escrever(raw + "\n")
        if raw in {"/za_warudo", "/psychedelic"}:
            self.escrever("TOKI WO TOMARE!\n")
            self._start_psychedelic_effect()
            self._prompt()
            return

        try:
            parts = shlex.split(raw, posix=True)
        except ValueError as exc:
            self.escrever(f"Sintaxe inválida: {exc}\n")
            self._prompt()
            return

        if not parts:
            self._prompt()
            return
        command, *args = parts
        command = command.casefold()

        try:
            if command in {"/help", "help"}:
                self._help()
            elif command in {"clear", "cls"}:
                self.output.config(state=tk.NORMAL)
                self.output.delete("1.0", tk.END)
                self.output.config(state=tk.DISABLED)
            elif command == "exit":
                self._close()
                return
            elif command in {"pwd"}:
                relative = (
                    "."
                    if self.current_path == self.workspace
                    else self.current_path.relative_to(self.workspace).as_posix()
                )
                self.escrever(f"/{relative}\n")
            elif command in {"dir", "ls"}:
                self._list_directory()
            elif command == "cd":
                target = args[0] if args else "."
                candidate = self._resolve(target)
                if not candidate.is_dir():
                    self.escrever("Pasta não encontrada.\n")
                else:
                    self.current_path = candidate
            elif command == "cat":
                if len(args) != 1:
                    self.escrever("Uso: cat arquivo.txt\n")
                else:
                    self._read_text(args[0])
            elif command == "echo":
                self.escrever(" ".join(args) + "\n")
            elif command == "mkdir":
                if len(args) != 1:
                    self.escrever("Uso: mkdir pasta\n")
                else:
                    name = validate_filename(args[0])
                    target = self._resolve(name)
                    target.mkdir()
                    self.escrever(f"Pasta criada: {name}\n")
            elif command == "touch":
                if len(args) != 1:
                    self.escrever("Uso: touch arquivo.txt\n")
                else:
                    name = validate_filename(args[0])
                    target = self._resolve(name)
                    with target.open("x", encoding="utf-8"):
                        pass
                    self.escrever(f"Arquivo criado: {name}\n")
            elif command == "rm":
                if len(args) != 1:
                    self.escrever("Uso: rm arquivo\n")
                else:
                    target = self._resolve(args[0])
                    if not target.is_file() or target.is_symlink():
                        self.escrever(
                            "Somente arquivos comuns do workspace podem ser removidos.\n"
                        )
                    elif messagebox.askyesno(
                        "Confirmar exclusão", f"Apagar {target.name}?", parent=self.win
                    ):
                        target.unlink()
                        self.escrever(f"Arquivo removido: {target.name}\n")
                    else:
                        self.escrever("Exclusão cancelada.\n")
            else:
                self.escrever(
                    "Comando não reconhecido. O terminal virtual não executa comandos do sistema; digite /help.\n"
                )
        except FileExistsError:
            self.escrever("Já existe um item com esse nome.\n")
        except (OSError, ValueError) as exc:
            self.escrever(f"Operação bloqueada ou inválida: {exc}\n")

        self._prompt()
