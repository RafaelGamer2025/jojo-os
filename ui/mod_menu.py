from __future__ import annotations

from tkinter import Menu


class ModMenu:
    """Menu da barra nativa que delega ações ao controlador do desktop."""

    def __init__(self, master, app):
        self.master = master
        self.app = app
        self.menu = Menu(master)
        master.config(menu=self.menu)

        self.app_menu = Menu(self.menu, tearoff=0)
        self.menu.add_cascade(label="Aplicativos", menu=self.app_menu)
        self.app_menu.add_command(label="Calculadora", command=lambda: self._invoke("open_calc"))
        self.app_menu.add_command(label="Assistente IA", command=lambda: self._invoke("open_ia"))
        self.app_menu.add_command(label="Batalha", command=lambda: self._invoke("open_battle"))
        self.app_menu.add_command(label="Scanner antivírus local", command=lambda: self._invoke("open_antivirus"))
        self.app_menu.add_command(label="Mini-jogo", command=lambda: self._invoke("run_pygame"))
        self.app_menu.add_command(label="Navegador", command=lambda: self._invoke("run_browser"))
        self.app_menu.add_command(label="Terminal virtual", command=lambda: self._invoke("open_terminal"))
        self.app_menu.add_separator()
        self._profile_store_index = self.app_menu.index("end") + 1
        self.app_menu.add_command(label="Store JoJo", command=lambda: self._invoke("open_app_catalog"))
        self.app_menu.add_separator()
        self.app_menu.add_command(label="Sair", command=self.master.destroy)
        self.set_profile(getattr(app, "skin_mode", "JOJO"))

    def set_profile(self, skin_mode):
        """Mostra no menu apenas a loja pertencente à skin atual."""
        cleiton = str(skin_mode).upper() == "CLEITON"
        if cleiton:
            self.app_menu.entryconfigure(
                self._profile_store_index,
                label="CLEITON STORE // 20 SISTEMAS",
                command=lambda: self._invoke("open_cleiton_store"),
            )
        else:
            self.app_menu.entryconfigure(
                self._profile_store_index,
                label="STORE JOJO // RESTAURANTE",
                command=lambda: self._invoke("open_app_catalog"),
            )

    def _invoke(self, name):
        callback = getattr(self.app, name, None)
        if callable(callback):
            callback()


def create_mod_menu(root, app):
    return ModMenu(root, app)
