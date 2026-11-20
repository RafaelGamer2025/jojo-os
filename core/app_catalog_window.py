"""Janela Tk do catálogo de aplicativos opcionais."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable, Iterable
from tkinter import messagebox

from core.app_catalog import OPTIONAL_APP_ID, AppDefinition, listar_apps_disponiveis
from ui.themes.jojo_theme import JoJoTheme

InstallationCallback = Callable[[str], None]


class AppCatalogWindow:
    """Apresenta o catálogo e delega mudanças de instalação ao controlador.

    ``installed_ids`` é uma fotografia do estado atual. Os callbacks recebem
    somente o ID do aplicativo alterado; o controlador decide como persistir o
    estado e como repintar seus próprios ícones. Esta janela nunca cria ícones.
    """

    def __init__(
        self,
        master: tk.Misc,
        installed_ids: Iterable[str],
        on_install: InstallationCallback,
        on_uninstall: InstallationCallback,
    ) -> None:
        self.installed_ids = set(installed_ids)
        self.on_install = on_install
        self.on_uninstall = on_uninstall

        self.window = tk.Toplevel(master)
        self.window.title("CATÁLOGO DE APLICATIVOS")
        self.window.geometry("560x300")
        self.window.minsize(480, 260)
        self.window.configure(bg=JoJoTheme.BLACK)
        self.window.transient(master)
        self.window.protocol("WM_DELETE_WINDOW", self.window.destroy)

        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        title = tk.Label(
            self.window,
            text="CATÁLOGO INTERNO",
            bg=JoJoTheme.BLACK,
            fg=JoJoTheme.GOLD,
            font=("Impact", 18),
        )
        title.pack(pady=(14, 2))

        subtitle = tk.Label(
            self.window,
            text="Instale apenas os aplicativos opcionais que deseja usar.",
            bg=JoJoTheme.BLACK,
            fg=JoJoTheme.WHITE,
            font=("Courier New", 10),
        )
        subtitle.pack(pady=(0, 12))

        catalog_frame = tk.Frame(
            self.window,
            bg=JoJoTheme.PURPLE,
            bd=2,
            relief="groove",
        )
        catalog_frame.pack(fill="both", expand=True, padx=16, pady=(0, 14))

        definition = listar_apps_disponiveis()[0]
        self._build_app_card(catalog_frame, definition)

    def _build_app_card(self, parent: tk.Misc, definition: AppDefinition) -> None:
        content = tk.Frame(parent, bg=JoJoTheme.PURPLE)
        content.pack(fill="both", expand=True, padx=14, pady=12)

        tk.Label(
            content,
            text=definition.nome,
            bg=JoJoTheme.PURPLE,
            fg=JoJoTheme.GOLD,
            font=("Impact", 15),
            anchor="w",
        ).pack(fill="x")
        tk.Label(
            content,
            text=definition.descricao,
            bg=JoJoTheme.PURPLE,
            fg=JoJoTheme.WHITE,
            font=("Courier New", 10),
            justify="left",
            anchor="w",
        ).pack(fill="x", pady=(4, 10))

        self.status_var = tk.StringVar()
        tk.Label(
            content,
            textvariable=self.status_var,
            bg=JoJoTheme.PURPLE,
            fg=JoJoTheme.PINK,
            font=("Courier New", 10, "bold"),
            anchor="w",
        ).pack(fill="x", pady=(0, 10))

        buttons = tk.Frame(content, bg=JoJoTheme.PURPLE)
        buttons.pack(fill="x")
        button_style = JoJoTheme.get_button_style()
        self.install_button = tk.Button(
            buttons,
            text="INSTALAR",
            command=self._install_selected_app,
            **button_style,
        )
        self.install_button.pack(side="left", padx=(0, 8))
        self.uninstall_button = tk.Button(
            buttons,
            text="DESINSTALAR",
            command=self._uninstall_selected_app,
            **button_style,
        )
        self.uninstall_button.pack(side="left")

    def refresh(self, installed_ids: Iterable[str] | None = None) -> bool:
        """Atualiza status e botões, opcionalmente com um novo estado."""

        if installed_ids is not None:
            self.installed_ids = set(installed_ids)
        installed = OPTIONAL_APP_ID in self.installed_ids
        self.status_var.set("INSTALADO" if installed else "NÃO INSTALADO")
        self.install_button.configure(state=tk.DISABLED if installed else tk.NORMAL)
        self.uninstall_button.configure(state=tk.NORMAL if installed else tk.DISABLED)
        return installed

    def _install_selected_app(self) -> None:
        if OPTIONAL_APP_ID in self.installed_ids:
            return
        try:
            self.on_install(OPTIONAL_APP_ID)
        except Exception as exc:  # noqa: BLE001 - UI deve converter falha de persistência em aviso.
            self.status_var.set("FALHA AO INSTALAR")
            messagebox.showerror(
                "Catálogo de aplicativos",
                f"Não foi possível instalar o aplicativo ({type(exc).__name__}).",
                parent=self.window,
            )
            return
        self.installed_ids.add(OPTIONAL_APP_ID)
        self.refresh()

    def _uninstall_selected_app(self) -> None:
        if OPTIONAL_APP_ID not in self.installed_ids:
            return
        try:
            self.on_uninstall(OPTIONAL_APP_ID)
        except Exception as exc:  # noqa: BLE001 - UI deve converter falha de persistência em aviso.
            self.status_var.set("FALHA AO DESINSTALAR")
            messagebox.showerror(
                "Catálogo de aplicativos",
                f"Não foi possível desinstalar o aplicativo ({type(exc).__name__}).",
                parent=self.window,
            )
            return
        self.installed_ids.remove(OPTIONAL_APP_ID)
        self.refresh()

    def winfo_exists(self) -> bool:
        """Expõe a existência da janela para o controlador."""

        return bool(self.window.winfo_exists())

    def focus_force(self) -> None:
        """Devolve o foco à janela já aberta."""

        self.window.deiconify()
        self.window.focus_force()


# Nome curto útil para controladores que preferem português.
JanelaCatalogoApps = AppCatalogWindow
