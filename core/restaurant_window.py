"""Interface local e fictícia do Restaurante do Tonio Trussardi.

O módulo exibe somente um cardápio estático e uma sugestão aleatória local.
Não há pedidos, pagamento, rede, login ou carregamento de assets externos.
"""

from __future__ import annotations

import random
import tkinter as tk
from dataclasses import dataclass

from ui.themes.jojo_theme import JoJoTheme


@dataclass(frozen=True)
class MenuItem:
    """Item fictício do cardápio local."""

    nome: str
    descricao: str
    preco: str


CARDAPIO: tuple[MenuItem, ...] = (
    MenuItem(
        nome="Risoto do Caminho",
        descricao="Arroz cremoso, cogumelos e ervas da casa.",
        preco="R$ 42,90",
    ),
    MenuItem(
        nome="Pizza Stand Duplo",
        descricao="Massa artesanal, tomate, muçarela e manjericão.",
        preco="R$ 38,50",
    ),
    MenuItem(
        nome="Lasanha do Ângulo",
        descricao="Camadas de massa, molho de tomate e queijo gratinado.",
        preco="R$ 36,00",
    ),
    MenuItem(
        nome="Pudim Bites the Dust",
        descricao="Pudim de leite com calda de caramelo dourado.",
        preco="R$ 18,90",
    ),
)

# Alias legível para controladores e testes que chamem o conjunto de menu em
# inglês. A tupla continua estática e não é alterada pela interface.
MENU: tuple[MenuItem, ...] = CARDAPIO


class RestaurantWindow:
    """Janela local do aplicativo opcional de restaurante."""

    def __init__(self, master: tk.Misc) -> None:
        self.window = tk.Toplevel(master)
        self.window.title("RESTAURANTE DO TONIO TRUSSARDI")
        self.window.geometry("640x610")
        self.window.minsize(560, 500)
        self.window.configure(bg=JoJoTheme.BLACK)
        self.window.transient(master)
        self.window.protocol("WM_DELETE_WINDOW", self.window.destroy)

        self._build_ui()
        self.sugerir_prato()

    def _build_ui(self) -> None:
        tk.Label(
            self.window,
            text="RESTAURANTE DO TONIO TRUSSARDI",
            bg=JoJoTheme.BLACK,
            fg=JoJoTheme.GOLD,
            font=("Impact", 19),
        ).pack(pady=(14, 2))
        tk.Label(
            self.window,
            text="Um cardápio fictício, servido localmente no JoJo-OS",
            bg=JoJoTheme.BLACK,
            fg=JoJoTheme.WHITE,
            font=("Courier New", 10),
        ).pack(pady=(0, 12))

        suggestion_frame = tk.Frame(
            self.window,
            bg="#1A1A1A",
            bd=2,
            relief="groove",
        )
        suggestion_frame.pack(fill="x", padx=18, pady=(0, 14))
        tk.Label(
            suggestion_frame,
            text="SUGESTÃO LOCAL",
            bg="#1A1A1A",
            fg=JoJoTheme.PINK,
            font=("Impact", 13),
        ).pack(pady=(9, 2))
        self.suggestion_var = tk.StringVar()
        tk.Label(
            suggestion_frame,
            textvariable=self.suggestion_var,
            bg="#1A1A1A",
            fg=JoJoTheme.GOLD,
            font=("Courier New", 11, "bold"),
            wraplength=530,
        ).pack(padx=10, pady=(0, 8))
        tk.Button(
            suggestion_frame,
            text="NOVA SUGESTÃO ALEATÓRIA",
            command=self.sugerir_prato,
            **JoJoTheme.get_button_style(),
        ).pack(pady=(0, 10))

        tk.Label(
            self.window,
            text="CARDÁPIO",
            bg=JoJoTheme.BLACK,
            fg=JoJoTheme.GOLD,
            font=("Impact", 15),
        ).pack(pady=(0, 6))
        menu_frame = tk.Frame(self.window, bg=JoJoTheme.BLACK)
        menu_frame.pack(fill="both", expand=True, padx=18)
        menu_frame.grid_columnconfigure(0, weight=1)
        for row, item in enumerate(CARDAPIO):
            self._build_menu_card(menu_frame, item, row)

        tk.Button(
            self.window,
            text="FECHAR",
            command=self.window.destroy,
            **JoJoTheme.get_button_style(),
        ).pack(pady=14)

    @staticmethod
    def _build_menu_card(parent: tk.Misc, item: MenuItem, row: int) -> None:
        card = tk.Frame(parent, bg=JoJoTheme.PURPLE, bd=1, relief="ridge")
        card.grid(row=row, column=0, sticky="ew", pady=3)
        card.grid_columnconfigure(0, weight=1)
        tk.Label(
            card,
            text=item.nome,
            bg=JoJoTheme.PURPLE,
            fg=JoJoTheme.GOLD,
            font=("Courier New", 11, "bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=10, pady=(6, 0))
        tk.Label(
            card,
            text=item.descricao,
            bg=JoJoTheme.PURPLE,
            fg=JoJoTheme.WHITE,
            font=("Courier New", 9),
            anchor="w",
        ).grid(row=1, column=0, sticky="ew", padx=10, pady=(2, 6))
        tk.Label(
            card,
            text=item.preco,
            bg=JoJoTheme.PURPLE,
            fg=JoJoTheme.PINK,
            font=("Courier New", 10, "bold"),
        ).grid(row=0, column=1, rowspan=2, padx=(8, 12), pady=6)

    def sugerir_prato(self) -> MenuItem:
        """Escolhe e mostra um item do cardápio, sem acessar rede ou serviço."""

        item = random.choice(CARDAPIO)
        self.suggestion_var.set(f"{item.nome} — {item.descricao} ({item.preco})")
        return item

    def suggest_random_dish(self) -> MenuItem:
        """Alias em inglês para a sugestão local."""

        return self.sugerir_prato()

    def winfo_exists(self) -> bool:
        """Expõe a existência da janela para o controlador."""

        return bool(self.window.winfo_exists())

    def focus_force(self) -> None:
        """Devolve o foco à janela já aberta."""

        self.window.focus_force()


# Nome alternativo em português para integração com o controlador.
JanelaRestaurante = RestaurantWindow
RestauranteWindow = RestaurantWindow


def open_restaurant_window(master: tk.Misc) -> RestaurantWindow:
    """Abre a janela do restaurante e devolve sua instância."""

    return RestaurantWindow(master)
