"""Janela da Cleiton Store; criada somente pelo perfil CLEITON."""
from __future__ import annotations

import tkinter as tk
from collections.abc import Callable, Iterable
from tkinter import messagebox

from core.cleiton_store import CLEITON_APPS, CleitonApp
from ui.themes.hacker_theme import HackerTheme

AppCallback = Callable[[str], None]


class CleitonStoreWindow:
    def __init__(
        self,
        master: tk.Misc,
        installed_ids: Iterable[str],
        on_install: AppCallback,
        on_uninstall: AppCallback,
        on_open: AppCallback,
    ) -> None:
        self.installed_ids = set(installed_ids)
        self.on_install = on_install
        self.on_uninstall = on_uninstall
        self.on_open = on_open
        self.window = tk.Toplevel(master)
        self.window.title("CLEITON OS // STORE")
        self.window.geometry("860x700")
        self.window.minsize(650, 500)
        self.window.configure(bg=HackerTheme.BLACK)
        self.window.transient(master)
        self.window.protocol("WM_DELETE_WINDOW", self.window.withdraw)
        self._cards: dict[str, tuple[tk.StringVar, tk.Button, tk.Button, tk.Button]] = {}
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        header = tk.Frame(self.window, bg=HackerTheme.BLACK)
        header.pack(fill="x", padx=20, pady=(16, 10))
        tk.Label(
            header, text="CLEITON STORE", bg=HackerTheme.BLACK, fg=HackerTheme.GOLD,
            font=("Courier New", 22, "bold"),
        ).pack(anchor="w")
        self.summary = tk.StringVar()
        tk.Label(
            header, textvariable=self.summary, bg=HackerTheme.BLACK, fg=HackerTheme.WHITE,
            font=("Courier New", 10),
        ).pack(anchor="w", pady=(4, 0))

        shell = tk.Frame(self.window, bg=HackerTheme.PURPLE, bd=1, relief="solid")
        shell.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        canvas = tk.Canvas(shell, bg=HackerTheme.BLACK, highlightthickness=0)
        scroll = tk.Scrollbar(shell, orient="vertical", command=canvas.yview)
        self.cards_frame = tk.Frame(canvas, bg=HackerTheme.BLACK)
        self.cards_frame.bind(
            "<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        self._frame_window = canvas.create_window((0, 0), window=self.cards_frame, anchor="nw")
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(self._frame_window, width=event.width))
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True, padx=(10, 0), pady=10)
        scroll.pack(side="right", fill="y", padx=(0, 8), pady=10)
        canvas.bind("<Enter>", lambda _event: canvas.bind_all(
            "<MouseWheel>", lambda event: canvas.yview_scroll(int(-event.delta / 120), "units")
        ))
        canvas.bind("<Leave>", lambda _event: canvas.unbind_all("<MouseWheel>"))

        for index, definition in enumerate(CLEITON_APPS):
            row, col = divmod(index, 2)
            self._build_card(self.cards_frame, definition, row, col)
        self.cards_frame.grid_columnconfigure(0, weight=1, uniform="cards")
        self.cards_frame.grid_columnconfigure(1, weight=1, uniform="cards")

    def _build_card(self, parent: tk.Misc, definition: CleitonApp, row: int, col: int) -> None:
        card = tk.Frame(parent, bg=HackerTheme.PURPLE, bd=1, relief="ridge")
        card.grid(row=row, column=col, sticky="nsew", padx=6, pady=6)
        card.grid_columnconfigure(0, weight=1)
        tk.Label(
            card, text=f"{definition.icon}  {definition.name}", bg=HackerTheme.PURPLE,
            fg=HackerTheme.GOLD, font=("Courier New", 12, "bold"), anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=10, pady=(9, 3))
        tk.Label(
            card, text=definition.description, bg=HackerTheme.PURPLE,
            fg=HackerTheme.WHITE, font=("Courier New", 9), anchor="w", justify="left",
            wraplength=340,
        ).grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 4))
        status = tk.StringVar()
        tk.Label(
            card, textvariable=status, bg=HackerTheme.PURPLE, fg=HackerTheme.GOLD,
            font=("Courier New", 9, "bold"), anchor="w",
        ).grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 5))
        buttons = tk.Frame(card, bg=HackerTheme.PURPLE)
        buttons.grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 9))
        style = {
            "bg": HackerTheme.BLACK, "fg": HackerTheme.GOLD,
            "activebackground": HackerTheme.PINK, "activeforeground": HackerTheme.WHITE,
            "font": ("Courier New", 8, "bold"), "relief": "flat", "bd": 0,
            "padx": 9, "pady": 5,
        }
        install = tk.Button(buttons, text="INSTALAR", command=lambda app_id=definition.app_id: self._install(app_id), **style)
        open_button = tk.Button(buttons, text="ABRIR", command=lambda app_id=definition.app_id: self.on_open(app_id), **style)
        uninstall = tk.Button(buttons, text="REMOVER", command=lambda app_id=definition.app_id: self._uninstall(app_id), **style)
        install.pack(side="left", padx=(0, 5))
        open_button.pack(side="left", padx=(0, 5))
        uninstall.pack(side="left")
        self._cards[definition.app_id] = status, install, open_button, uninstall

    def refresh(self, installed_ids: Iterable[str] | None = None) -> None:
        if installed_ids is not None:
            self.installed_ids = set(installed_ids)
        count = len(self.installed_ids)
        self.summary.set(f"20 UTILITÁRIOS LOCAIS  //  {count} INSTALADO(S)  //  sem serviços externos")
        for app_id, (status, install, open_button, uninstall) in self._cards.items():
            installed = app_id in self.installed_ids
            status.set("INSTALADO" if installed else "DISPONÍVEL")
            install.configure(state=tk.DISABLED if installed else tk.NORMAL)
            open_button.configure(state=tk.NORMAL if installed else tk.DISABLED)
            uninstall.configure(state=tk.NORMAL if installed else tk.DISABLED)

    def _install(self, app_id: str) -> None:
        try:
            self.on_install(app_id)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Cleiton Store", f"Não foi possível instalar ({type(exc).__name__}).", parent=self.window)
            return
        self.installed_ids.add(app_id)
        self.refresh()

    def _uninstall(self, app_id: str) -> None:
        if not messagebox.askyesno("Remover aplicativo", "Desinstalar este aplicativo da Cleiton Store? Os textos salvos serão preservados.", parent=self.window):
            return
        try:
            self.on_uninstall(app_id)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Cleiton Store", f"Não foi possível desinstalar ({type(exc).__name__}).", parent=self.window)
            return
        self.installed_ids.discard(app_id)
        self.refresh()

    def winfo_exists(self) -> bool:
        return bool(self.window.winfo_exists())

    def focus_force(self) -> None:
        self.window.deiconify()
        self.window.lift()
        self.window.focus_force()
