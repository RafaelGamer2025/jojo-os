"""Interface reutilizável para os utilitários offline da Cleiton Store."""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

from core.cleiton_store import APP_BY_ID
from core.cleiton_tools import execute_cleiton_tool, get_tool_seed
from ui.themes.hacker_theme import HackerTheme


class CleitonToolWindow:
    def __init__(self, master: tk.Misc, app_id: str) -> None:
        if app_id not in APP_BY_ID:
            raise ValueError("Aplicativo Cleiton OS desconhecido.")
        self.app_id = app_id
        self.definition = APP_BY_ID[app_id]
        self.selected_file: Path | None = None
        self.window = tk.Toplevel(master)
        self.window.title(f"CLEITON OS // {self.definition.name.upper()}")
        self.window.geometry("680x650")
        self.window.minsize(560, 500)
        self.window.configure(bg=HackerTheme.BLACK)
        self.window.transient(master)
        self._build_ui()

    def _build_ui(self) -> None:
        app = self.definition
        tk.Label(
            self.window, text=f"{app.icon}  {app.name.upper()}", bg=HackerTheme.BLACK,
            fg=HackerTheme.GOLD, font=("Courier New", 18, "bold"), anchor="w",
        ).pack(fill="x", padx=18, pady=(16, 4))
        tk.Label(
            self.window, text=app.description, bg=HackerTheme.BLACK, fg=HackerTheme.WHITE,
            font=("Courier New", 9), wraplength=630, justify="left", anchor="w",
        ).pack(fill="x", padx=18, pady=(0, 10))
        tk.Label(
            self.window, text=app.input_hint, bg=HackerTheme.BLACK, fg=HackerTheme.GOLD,
            font=("Courier New", 9), wraplength=630, justify="left", anchor="w",
        ).pack(fill="x", padx=18, pady=(0, 5))
        self.input = tk.Text(
            self.window, height=9, wrap="word", bg="#101810", fg=HackerTheme.WHITE,
            insertbackground=HackerTheme.GOLD, font=("Consolas", 10), relief="flat",
        )
        self.input.pack(fill="x", expand=False, padx=18, pady=(0, 9))
        seed = get_tool_seed(app.app_id)
        if seed or app.app_id in {"cleiton_notes", "cleiton_checklist"}:
            self.input.insert("1.0", seed)

        controls = tk.Frame(self.window, bg=HackerTheme.BLACK)
        controls.pack(fill="x", padx=18, pady=(0, 8))
        style = {
            "bg": HackerTheme.PURPLE, "fg": HackerTheme.GOLD,
            "activebackground": HackerTheme.PINK, "activeforeground": HackerTheme.WHITE,
            "font": ("Courier New", 9, "bold"), "relief": "flat", "bd": 0,
            "padx": 12, "pady": 7,
        }
        tk.Button(controls, text=app.action_label, command=self._run, **style).pack(side="left", padx=(0, 7))
        if self.app_id == "cleiton_sha256":
            tk.Button(controls, text="ESCOLHER ARQUIVO", command=self._choose_file, **style).pack(side="left", padx=(0, 7))
        tk.Button(controls, text="COPIAR RESULTADO", command=self._copy_result, **style).pack(side="left")
        self.file_status = tk.StringVar(value="Nenhum arquivo selecionado.")
        if self.app_id == "cleiton_sha256":
            tk.Label(controls, textvariable=self.file_status, bg=HackerTheme.BLACK, fg=HackerTheme.WHITE, font=("Courier New", 8)).pack(side="left", padx=8)

        tk.Label(
            self.window, text="RESULTADO", bg=HackerTheme.BLACK, fg=HackerTheme.GOLD,
            font=("Courier New", 10, "bold"), anchor="w",
        ).pack(fill="x", padx=18, pady=(4, 3))
        self.output = tk.Text(
            self.window, height=12, wrap="word", state="disabled", bg="#080c08",
            fg="#b7ffb7", insertbackground=HackerTheme.GOLD,
            font=("Consolas", 10), relief="flat",
        )
        self.output.pack(fill="both", expand=True, padx=18, pady=(0, 16))
        self._set_output("Escolha EXECUTAR para iniciar. Os dados permanecem locais.")

    def _choose_file(self) -> None:
        selected = filedialog.askopenfilename(parent=self.window, title="Escolha arquivo para SHA-256")
        if selected:
            self.selected_file = Path(selected)
            self.file_status.set(self.selected_file.name)

    def _run(self) -> None:
        try:
            result = execute_cleiton_tool(
                self.app_id, self.input.get("1.0", "end-1c"), file_path=self.selected_file,
            )
        except (OSError, ValueError, TypeError, UnicodeError) as exc:
            messagebox.showwarning("Cleiton OS", str(exc), parent=self.window)
            return
        self._set_output(result)

    def _set_output(self, value: str) -> None:
        self.output.configure(state="normal")
        self.output.delete("1.0", "end")
        self.output.insert("1.0", value)
        self.output.configure(state="disabled")

    def _copy_result(self) -> None:
        value = self.output.get("1.0", "end-1c")
        self.window.clipboard_clear()
        self.window.clipboard_append(value)
        self.window.update_idletasks()

    def winfo_exists(self) -> bool:
        return bool(self.window.winfo_exists())

    def focus_force(self) -> None:
        self.window.deiconify()
        self.window.lift()
        self.window.focus_force()
