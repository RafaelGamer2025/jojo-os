import json
import math
import os
import re
import tkinter as tk
from pathlib import Path
from types import SimpleNamespace

import pygame
from dotenv import load_dotenv
from pygame import mixer

from core.app_catalog import (
    OPTIONAL_APP_ID,
    get_installed_optional_apps,
)
from core.app_catalog import (
    install_optional_app as install_catalog_app,
)
from core.app_catalog import (
    uninstall_optional_app as uninstall_catalog_app,
)
from core.calc_window import JoJoCalc
from core.cleiton_store import (
    APP_BY_ID as CLEITON_APP_BY_ID,
)
from core.cleiton_store import (
    get_installed_cleiton_apps,
    is_cleiton_profile,
)
from core.cleiton_store import (
    install_cleiton_app as install_cleiton_catalog_app,
)
from core.cleiton_store import (
    uninstall_cleiton_app as uninstall_cleiton_catalog_app,
)
from core.database import delete_setting, get_setting, set_setting
from core.debugger_window import JoJoDebugger
from core.file_manager import FileManager
from core.ia_window import abrir_janela_ia
from core.login_in_window import LoginWindow
from core.security import (
    DB_FILE,
    SecurityStoreError,
    carregar_db_seguro,
    get_system_key,
)
from core.system.terminal_window import TerminalWindow
from ui.desktop_grid import (
    DEFAULT_CELL_HEIGHT,
    DEFAULT_CELL_WIDTH,
    DEFAULT_HEIGHT,
    DEFAULT_ORIGIN_X,
    DEFAULT_ORIGIN_Y,
    DEFAULT_WIDTH,
    DesktopGrid,
    choose_nearest_free_slot,
    normalize_positions,
    reflow_positions,
)
from ui.menacing_animation import start_menacing
from ui.themes.hacker_theme import HackerTheme
from ui.themes.jojo_theme import JoJoTheme
from ui.time_stop_effect import TimeStopEffect
from ui.widgets.draggable_icon import DraggableIcon

APP_ROOT = Path(__file__).resolve().parent
load_dotenv(APP_ROOT / ".env")

DESKTOP_ICON_ORDER = (
    "calc",
    "ia",
    "menacing",
    "battle",
    "antivirus",
    "games",
    "browser",
    "debugger",
    "terminal",
    "sticky_fingers",
    "piano",
    "commands",
    "restaurant_tonio",
    "cleiton_store",
)
ICON_KEY_ALIASES = {
    "browser": ("browser", "explorer"),
    "terminal": ("terminal", "commands"),
}


def reparar_sistema():
    """Inicializa somente a chave ausente; nunca sobrescreve banco."""
    try:
        get_system_key()
        DB_FILE.parent.mkdir(parents=True, exist_ok=True)
        if DB_FILE.exists():
            database = carregar_db_seguro(DB_FILE)
            if database.get("__hack_detected__") is True:
                raise SecurityStoreError("A assinatura do banco não confere.")
        print("Verificação local concluída. Nenhum banco foi sobrescrito.")
        return True
    except (OSError, SecurityStoreError, ValueError) as exc:
        print(f"Falha na verificação local: {exc}")
        return False
    
class JoJoOS:
    def __init__(self, root):
        self.root = root
        try:
            mixer.init()
            self.audio_available = True
        except pygame.error:
            self.audio_available = False       
        # O perfil Cleiton é uma skin separada; começa em JoJo OS como antes.
        self.skin_mode = "JOJO"
        self.current_theme = JoJoTheme 
        self.root.title("JOJO-OS v4.0 // BIZARRE ADVENTURE")
        self.root.geometry("1000x700")
        self.root.minsize(700, 700)
        self.root.configure(bg=self.current_theme.BLACK)

        # Barra Superior Estilizada
        self.top_bar = tk.Frame(root, bg=self.current_theme.PURPLE, height=40)
        self.top_bar.pack(side="top", fill="x")
        
        self.title_label = tk.Label(self.top_bar, text="⭐ JOJO-OS: GOLDEN EXPERIENCE EDITION", 
                fg=self.current_theme.GOLD, bg=self.current_theme.PURPLE, font=("Impact", 14, "bold"))
        self.title_label.pack(side="left", padx=20)

        # Área de Trabalho
        self.canvas = tk.Canvas(root, bg=self.current_theme.BLACK, highlightthickness=0)
        self.canvas.pack(expand=True, fill="both")
        self._canvas_size = (DEFAULT_WIDTH, DEFAULT_HEIGHT)
        self._icon_frames = {}
        self._drag_origins = {}
        self._drag_controllers = {}
        self._active_icon_keys = ()
        self.canvas.bind("<Configure>", self._on_canvas_configure, add="+")
        
        self.btn_skin = tk.Button(self.top_bar, text="ATIVAR CLEITON OS", 
                                command=self.toggle_skin,
                                bg=self.current_theme.PURPLE, fg=self.current_theme.GOLD,
                                font=("Impact", 10))
        self.btn_skin.pack(side="right", padx=10)

        # Lista para armazenar ícones e recriar ao mudar a skin
        self.icons_list = []
        self.icon_positions = self.load_icon_positions()
        self.installed_optional_apps = get_installed_optional_apps(path=DB_FILE)
        self.installed_cleiton_apps = get_installed_cleiton_apps(path=DB_FILE)
        self.command_window = None
        # Variáveis de estado do usuário
        self.current_user = None
        self.is_admin = False
        self.stand_theme = None # Cores do stand escolhido para personalizar a interface
        self.app_catalog_window = None
        self.cleiton_store_window = None
        self.cleiton_tool_windows = {}
        self.restaurant_window = None
        self.game_hub_window = None
        self.time_stop_effect = None
        from ui.mod_menu import ModMenu
        self.mod_menu = ModMenu(self.root, self)

    def load_icon_positions(self):
        legacy_path = APP_ROOT / "data" / "icon_positions.json"

        try:
            positions = get_setting("icon_positions", None, path=DB_FILE)
            if positions is None and legacy_path.is_file():
                positions = json.loads(legacy_path.read_text(encoding="utf-8"))
                normalized = self._sanitize_icon_positions(positions)
                set_setting("icon_positions", normalized, path=DB_FILE)
                self._archive_legacy_data_file(legacy_path)
                return normalized
            normalized = self._sanitize_icon_positions(positions or {})
            if positions is not None and normalized != positions:
                set_setting("icon_positions", normalized, path=DB_FILE)
            return normalized
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError, OverflowError, RuntimeError):
            return {}

    @staticmethod
    def _sanitize_icon_positions(data, *, width=DEFAULT_WIDTH, height=DEFAULT_HEIGHT):
        return normalize_positions(
            data,
            width=width,
            height=height,
            order=DESKTOP_ICON_ORDER,
        )

    @staticmethod
    def _archive_legacy_data_file(path):
        backup = path.with_name(path.name + ".migrated.bak")
        suffix = 1
        while backup.exists():
            backup = path.with_name(path.name + f".migrated-{suffix}.bak")
            suffix += 1
        try:
            os.replace(path, backup)
            try:
                os.chmod(backup, 0o600)
            except OSError:
                pass
        except OSError:
            # A configuração já está no SQLite; o legado nunca é sobrescrito.
            return

    def save_icon_positions(self):
        try:
            width, height = self._canvas_dimensions()
            grid = self._desktop_grid(width, height)
            self.icon_positions = normalize_positions(
                self.icon_positions,
                width=width,
                height=height,
                order=DESKTOP_ICON_ORDER,
                grid=grid,
            )
            set_setting(
                "icon_positions",
                self.icon_positions,
                path=DB_FILE,
            )
        except (OSError, TypeError, ValueError, RuntimeError) as exc:
            print(f"Erro ao salvar posições no SQLite: {exc}")

    def grid_system(self, x, y):
        width, height = self._canvas_dimensions()
        grid = self._desktop_grid(width, height)
        return grid.snap((x, y)) or (grid.origin_x, grid.origin_y)

    def _canvas_dimensions(self):
        width, height = self._canvas_size
        try:
            measured_width = int(self.canvas.winfo_width())
            measured_height = int(self.canvas.winfo_height())
        except (AttributeError, tk.TclError, TypeError, ValueError):
            return width, height
        if measured_width > 1:
            width = measured_width
        if measured_height > 1:
            height = measured_height
        return width, height

    def _desktop_grid(self, width=None, height=None, *, item_count=None):
        measured_width, measured_height = self._canvas_dimensions()
        width = max(0, int(measured_width if width is None else width))
        height = max(0, int(measured_height if height is None else height))
        cell_width = DEFAULT_CELL_WIDTH
        cell_height = DEFAULT_CELL_HEIGHT
        for frame in getattr(self, "_icon_frames", {}).values():
            try:
                cell_width = max(cell_width, int(frame.winfo_reqwidth()) + 12)
                cell_height = max(cell_height, int(frame.winfo_reqheight()) + 12)
            except (tk.TclError, TypeError, ValueError):
                continue

        if item_count is None:
            item_count = len(getattr(self, "_active_icon_keys", ())) or len(
                getattr(self, "_icon_frames", {})
            )
        if isinstance(item_count, int) and not isinstance(item_count, bool) and item_count > 0:
            columns = max(1, math.ceil(math.sqrt(item_count)))
            rows = math.ceil(item_count / columns)
            required_width = DEFAULT_ORIGIN_X + columns * cell_width
            required_height = DEFAULT_ORIGIN_Y + rows * cell_height
            width = max(width, required_width)
            height = max(height, required_height)
            try:
                minimum_width, minimum_height = self.root.winfo_minsize()
                top_bar_height = max(40, int(self.top_bar.winfo_reqheight()))
                self.root.minsize(
                    max(int(minimum_width), required_width + 12),
                    max(int(minimum_height), required_height + top_bar_height + 12),
                )
            except (AttributeError, tk.TclError, TypeError, ValueError):
                pass

        return DesktopGrid(
            width=width,
            height=height,
            cell_width=cell_width,
            cell_height=cell_height,
        )

    def _on_canvas_configure(self, event):
        width = int(getattr(event, "width", 0) or 0)
        height = int(getattr(event, "height", 0) or 0)
        if width <= 1 or height <= 1:
            return
        if (width, height) == self._canvas_size:
            return
        self._canvas_size = (width, height)
        if self._icon_frames:
            self._reflow_rendered_icons()

    def _stored_position(self, icon_key):
        for key in ICON_KEY_ALIASES.get(icon_key, (icon_key,)):
            if key in self.icon_positions:
                return self.icon_positions[key]
        return None

    def _prepare_active_positions(self, defaults):
        width, height = self._canvas_dimensions()
        grid = self._desktop_grid(width, height, item_count=len(defaults))
        requested = {
            icon_key: self._stored_position(icon_key) or [x, y]
            for icon_key, (x, y) in defaults.items()
        }
        normalized = normalize_positions(
            requested,
            width=width,
            height=height,
            order=tuple(defaults),
            grid=grid,
        )
        self.icon_positions.update(normalized)
        self._active_icon_keys = tuple(defaults)

    def _reflow_rendered_icons(self):
        width, height = self._canvas_dimensions()
        requested = {
            key: self.icon_positions.get(key, [frame.winfo_x(), frame.winfo_y()])
            for key, frame in self._icon_frames.items()
        }
        grid = self._desktop_grid(width, height, item_count=len(requested))
        normalized = reflow_positions(
            requested,
            grid.width,
            grid.height,
            order=self._active_icon_keys or DESKTOP_ICON_ORDER,
            grid=grid,
        )
        for key, frame in self._icon_frames.items():
            position = normalized.get(key)
            if position is None:
                frame.place_forget()
                continue
            frame.place(x=position[0], y=position[1])
            self.icon_positions[key] = position
        self.save_icon_positions()

    def draggle_icon(self, widget):
        DraggableIcon(self.canvas, widget)

    def run_browser(self):
        from ui.browser import BrowserApp
        browser_win = tk.Toplevel(self.root)
        BrowserApp(browser_win)

    def open_battle(self):

        from battle.battle_in_window import BattleWindow

        if not self.current_user:
            print("⚠️ Nenhum usuário logado")
            return

        escolha_win = tk.Toplevel(self.root)

        escolha_win.title("⚔️ ESCOLHA SEU STAND")
        escolha_win.geometry("850x650")
        escolha_win.configure(bg="black")

        tk.Label(
            escolha_win,
            text="⚔️ ESCOLHA SEU STAND PARA A BATALHA ⚔️",
            fg="gold",
            bg="black",
            font=("Impact", 28)
        ).pack(pady=20)

        awakened = getattr(self, "current_stand", None)
        tk.Label(
            escolha_win,
            text=(f"STAND DESPERTADO: {awakened}" if awakened else "SEM STAND DESPERTADO — ESCOLHA LIVRE"),
            fg="#D8B65A",
            bg="black",
            font=("Courier New", 12, "bold"),
        ).pack(pady=(0, 10))

        STANDS = {

            "Star Platinum": {
                "cor": "#5E60CE",
                "desc": "Velocidade absurda e ORA ORA ORA!",
                "power": 10,
                "speed": 10,
                "range": 4,
                "skill": "ORA ORA BARRAGE"
            },

            "The World": {
                "cor": "#FFD60A",
                "desc": "ZA WARUDO! O tempo para.",
                "power": 10,
                "speed": 9,
                "range": 5,
                "skill": "TIME STOP"
            },

            "Killer Queen": {
                "cor": "#FF4D6D",
                "desc": "Explosões silenciosas.",
                "power": 8,
                "speed": 7,
                "range": 6,
                "skill": "BITE THE DUST"
            },

            "D4C": {
                "cor": "#80ED99",
                "desc": "Dimensões infinitas.",
                "power": 9,
                "speed": 7,
                "range": 8,
                "skill": "LOVE TRAIN"
            },

            "Wonder of U": {
                "cor": "#9D4EDD",
                "desc": "Calamidade inevitável.",
                "power": 8,
                "speed": 6,
                "range": 10,
                "skill": "CALAMITY"
            }
        }

        from core.battle_system import STANDS as BATTLE_STANDS

        for stand_name, details in BATTLE_STANDS.items():
            STANDS.setdefault(
                stand_name,
                {
                    "cor": details["color"],
                    "desc": details["desc"],
                    "power": details["power"],
                    "speed": details["speed"],
                    "range": details["range"],
                    "skill": details["skill"],
                },
            )

        selection_area = tk.Frame(escolha_win, bg="black")
        selection_area.pack(expand=True, fill="both", padx=8, pady=(0, 12))
        selector_canvas = tk.Canvas(selection_area, bg="black", highlightthickness=0)
        selector_scrollbar = tk.Scrollbar(selection_area, orient="vertical", command=selector_canvas.yview)
        container = tk.Frame(selector_canvas, bg="black")
        container.bind(
            "<Configure>",
            lambda _event: selector_canvas.configure(scrollregion=selector_canvas.bbox("all")),
        )
        frame_id = selector_canvas.create_window((0, 0), window=container, anchor="nw")
        selector_canvas.bind(
            "<Configure>",
            lambda event: selector_canvas.itemconfigure(frame_id, width=event.width),
        )
        selector_canvas.configure(yscrollcommand=selector_scrollbar.set)
        selector_scrollbar.pack(side="right", fill="y")
        selector_canvas.pack(side="left", expand=True, fill="both")
        def selecionar(stand):

            escolha_win.destroy()

            BattleWindow(
                self.root,
                self.current_user,
                stand
            )

        for stand, info in STANDS.items():

            card = tk.Frame(
                container,
                bg="#111",
                highlightbackground=info["cor"],
                highlightthickness=3,
                bd=0
            )

            card.pack(
                pady=10,
                padx=20,
                fill="x"
            )

            tk.Label(
                card,
                text=stand,
                fg=info["cor"],
                bg="#111",
                font=("Impact", 24)
            ).pack(pady=(10, 0))

            tk.Label(
                card,
                text=info["desc"],
                fg="white",
                bg="#111",
                font=("Courier New", 10)
            ).pack()

            stats = (
                f"⚔️ POWER: {info['power']}    "
                f"⚡ SPEED: {info['speed']}    "
                f"🎯 RANGE: {info['range']}"
            )

            tk.Label(
                card,
                text=stats,
                fg="gold",
                bg="#111",
                font=("Impact", 12)
            ).pack(pady=5)

            tk.Label(
                card,
                text=f"🔥 SPECIAL: {info['skill']}",
                fg="#ffcc00",
                bg="#111",
                font=("Impact", 14)
            ).pack()

            tk.Button(
                card,
                text="⚔️ ESCOLHER",
                bg=info["cor"],
                fg="black",
                font=("Impact", 14),
                bd=0,
                width=20,
                cursor="hand2",
                command=lambda s=stand: selecionar(s)).pack(pady=10)
    def open_files(self):
        FileManager(self.root)
    def open_terminal(self):
        TerminalWindow(self.root)
    def open_app_catalog(self):
        if self.skin_mode != "JOJO":
            return None
        from core.app_catalog_window import AppCatalogWindow

        if self.app_catalog_window is not None and self.app_catalog_window.winfo_exists():
            self.app_catalog_window.window.deiconify()
            self.app_catalog_window.focus_force()
            return self.app_catalog_window
        self.app_catalog_window = AppCatalogWindow(
            self.root,
            installed_ids=self.installed_optional_apps,
            on_install=self.install_optional_app,
            on_uninstall=self.uninstall_optional_app,
        )
        return self.app_catalog_window

    def open_cleiton_store(self):
        """Abre a Store de 20 sistemas somente quando a skin Cleiton está ativa."""
        if not is_cleiton_profile(self.skin_mode):
            return None
        if self.cleiton_store_window is not None and self.cleiton_store_window.winfo_exists():
            self.cleiton_store_window.focus_force()
            return self.cleiton_store_window
        from core.cleiton_store_window import CleitonStoreWindow

        self.cleiton_store_window = CleitonStoreWindow(
            self.root,
            installed_ids=self.installed_cleiton_apps,
            on_install=self.install_cleiton_app,
            on_uninstall=self.uninstall_cleiton_app,
            on_open=self.open_cleiton_tool,
        )
        return self.cleiton_store_window

    def install_cleiton_app(self, app_id):
        if not is_cleiton_profile(self.skin_mode):
            raise PermissionError("A Cleiton Store só pode ser usada no perfil Cleiton OS.")
        self.installed_cleiton_apps = install_cleiton_catalog_app(app_id, path=DB_FILE)
        if self.cleiton_store_window is not None and self.cleiton_store_window.winfo_exists():
            self.cleiton_store_window.refresh(self.installed_cleiton_apps)
        if self._icon_frames:
            self.render_icons()
        return set(self.installed_cleiton_apps)

    def uninstall_cleiton_app(self, app_id):
        if not is_cleiton_profile(self.skin_mode):
            raise PermissionError("A Cleiton Store só pode ser usada no perfil Cleiton OS.")
        window = self.cleiton_tool_windows.pop(app_id, None)
        if window is not None and window.winfo_exists():
            window.window.destroy()
        self.installed_cleiton_apps = uninstall_cleiton_catalog_app(app_id, path=DB_FILE)
        if self.cleiton_store_window is not None and self.cleiton_store_window.winfo_exists():
            self.cleiton_store_window.refresh(self.installed_cleiton_apps)
        if self._icon_frames:
            self.render_icons()
        return set(self.installed_cleiton_apps)

    def open_cleiton_tool(self, app_id):
        if not is_cleiton_profile(self.skin_mode) or app_id not in self.installed_cleiton_apps:
            return None
        if app_id not in CLEITON_APP_BY_ID:
            raise ValueError("Aplicativo Cleiton OS desconhecido.")
        existing = self.cleiton_tool_windows.get(app_id)
        if existing is not None and existing.winfo_exists():
            existing.focus_force()
            return existing
        from core.cleiton_tool_window import CleitonToolWindow

        window = CleitonToolWindow(self.root, app_id)
        self.cleiton_tool_windows[app_id] = window
        return window

    def _hide_cleiton_windows_outside_profile(self):
        """Mantém janelas do Cleiton guardadas, mas invisíveis em JoJo OS."""
        if is_cleiton_profile(self.skin_mode):
            return
        windows = [self.cleiton_store_window, *self.cleiton_tool_windows.values()]
        for handle in windows:
            if handle is None or not handle.winfo_exists():
                continue
            try:
                handle.window.withdraw()
            except tk.TclError:
                pass

    def install_optional_app(self, app_id):
        self.installed_optional_apps = install_catalog_app(app_id, path=DB_FILE)
        if self.app_catalog_window is not None and self.app_catalog_window.winfo_exists():
            self.app_catalog_window.refresh(self.installed_optional_apps)
        if self._icon_frames:
            self.render_icons()
        return set(self.installed_optional_apps)

    def uninstall_optional_app(self, app_id):
        self.installed_optional_apps = uninstall_catalog_app(app_id, path=DB_FILE)
        if self.restaurant_window is not None and self.restaurant_window.winfo_exists():
            try:
                self.restaurant_window.window.destroy()
            except tk.TclError:
                pass
            self.restaurant_window = None
        self.icon_positions.pop(app_id, None)
        self.save_icon_positions()
        if self.app_catalog_window is not None and self.app_catalog_window.winfo_exists():
            self.app_catalog_window.refresh(self.installed_optional_apps)
        if self._icon_frames:
            self.render_icons()
        return set(self.installed_optional_apps)

    def open_restaurant(self):
        if OPTIONAL_APP_ID not in self.installed_optional_apps:
            from tkinter import messagebox

            messagebox.showinfo(
                "Aplicativo não instalado",
                "Instale o Restaurante do Tonio Trussardi pelo Catálogo de aplicativos.",
                parent=self.root,
            )
            return
        if self.restaurant_window is not None and self.restaurant_window.winfo_exists():
            self.restaurant_window.focus_force()
            return self.restaurant_window
        from core.restaurant_window import RestaurantWindow

        self.restaurant_window = RestaurantWindow(self.root)
        return self.restaurant_window

    def render_icons(self):
        """Desenha os ícones dependendo da skin ativa"""
        if self.skin_mode == "JOJO":
            icon_specs = (
                ("Calculadora", "🔢", self.open_calc, 50, 50, "STAR PLATINUM", "calc"),
                ("Heaven's Door IA", "📖", self.open_ia, 150, 50, "ROHAN KISHIBE", "ia"),
                ("Menacing", "ゴ", self.open_menacing, 250, 50, "DIO BRANDO", "menacing"),
                ("Battle", "⚔️", self.open_battle, 350, 50, "STAND FIGHT", "battle"),
                ("Killer Queen", "💣", self.open_antivirus, 50, 200, "YOSHIKAGE KIRA", "antivirus"),
                ("IKEMEN GO", "🕹️", self.run_pygame, 250, 200, "STEEL BALL RUN", "games"),
                ("Internet", "🌐", self.run_browser, 400, 200, "D'ARBY THE PLAYER", "browser"),
                ("Debugger", "🔍", self.open_debugger, 500, 200, "HIEROPHANT GREEN", "debugger"),
                ("Terminal", "💻", self.open_terminal, 750, 200, "HERMIT PURPLE", "terminal"),
                ("Sticky Fingers", "📂", self.open_files, 750, 50, "BRUNO BUCCIARATI", "sticky_fingers"),
                ("Piano", "🎹", self.open_piano, 650, 50, "MUSIC MODE", "piano"),
            )
        else:
            icon_specs = (
                ("Calc.exe", "📟", self.open_calc, 50, 50, "DECRYPTOR", "calc"),
                ("Neural_Net", "💾", self.open_ia, 250, 50, "DATABASE", "ia"),
                ("Glitcher", "⚡", self.open_menacing, 250, 50, "OVERRIDE", "menacing"),
                ("Firewall", "🧨", self.open_antivirus, 50, 200, "BOMB_SCAN", "antivirus"),
                ("IKEMEN GO", "🎮", self.run_pygame, 250, 200, "FIGHTING_ENGINE", "games"),
                ("Browser", "🌐", self.run_browser, 400, 200, "D'ARBY THE PLAYER", "browser"),
                ("Debugger", "🔍", self.open_debugger, 500, 200, "HIEROPHANT GREEN", "debugger"),
                ("Battle", "⚔️", self.open_battle, 600, 50, "STAND FIGHT", "battle"),
                ("Comandos", "💻", self.open_command_window, 650, 200, "SHELL", "terminal"),
                ("Piano", "🎹", self.open_piano, 750, 50, "MUSIC MODE", "piano"),
            )

        if OPTIONAL_APP_ID in self.installed_optional_apps and self.skin_mode == "JOJO":
            icon_specs += (
                (
                    "Restaurante do Tonio",
                    "🍽️",
                    self.open_restaurant,
                    50,
                    350,
                    "TRUSSARDI",
                    OPTIONAL_APP_ID,
                ),
            )

        if is_cleiton_profile(self.skin_mode):
            icon_specs += (
                (
                    "CLEITON STORE",
                    "▦",
                    self.open_cleiton_store,
                    50,
                    350,
                    "20 SISTEMAS",
                    "cleiton_store",
                ),
            )

        defaults = {spec[6]: (spec[3], spec[4]) for spec in icon_specs}
        self._prepare_active_positions(defaults)
        self.save_icon_positions()

        for icon in self.icons_list:
            icon.destroy()
        self.icons_list.clear()
        self._icon_frames.clear()
        self._drag_origins.clear()
        self._drag_controllers.clear()
        for spec in icon_specs:
            self.add_icon(*spec)
        self._reflow_rendered_icons()

    def set_skin_mode(self, profile, *, render=True):
        self.skin_mode = "CLEITON" if str(profile).upper() == "CLEITON" else "JOJO"
        if self.skin_mode == "CLEITON":
            self.current_theme = HackerTheme
            self.title_label.configure(text="▣ CLEITON OS: SISTEMAS LOCAIS", font=("Courier New", 14, "bold"))
            self.root.title("CLEITON OS v4.0 // DIGITAL EDITION")
            self.btn_skin.configure(text="VOLTAR PARA JOJO OS")
        else:
            self.current_theme = JoJoTheme
            self.title_label.configure(text="⭐ JOJO-OS: GOLDEN EXPERIENCE EDITION", font=("Impact", 14, "bold"))
            self.root.title("JOJO-OS v4.0 // BIZARRE ADVENTURE")
            self.btn_skin.configure(text="ATIVAR CLEITON OS")
        self.mod_menu.set_profile(self.skin_mode)

        self.root.configure(bg=self.current_theme.BLACK)
        self.top_bar.configure(bg=self.current_theme.PURPLE)
        self.canvas.configure(bg=self.current_theme.BLACK)
        self.btn_skin.configure(bg=self.current_theme.PURPLE, fg=self.current_theme.GOLD)
        self.title_label.configure(fg=self.current_theme.GOLD, bg=self.current_theme.PURPLE)
        self._hide_cleiton_windows_outside_profile()
        if self.skin_mode == "CLEITON" and self.app_catalog_window is not None:
            try:
                self.app_catalog_window.window.withdraw()
            except tk.TclError:
                pass
        if render:
            self.render_icons()

    def toggle_skin(self):
        target = "CLEITON" if self.skin_mode == "JOJO" else "JOJO"
        self.set_skin_mode(target)

    def add_icon(self, name, symbol, command, x, y, stand_name, icon_key=None):
        icon_key = icon_key or name.lower()
        requested = self._stored_position(icon_key) or self.grid_system(x, y)
        width, height = self._canvas_dimensions()
        grid = self._desktop_grid(width, height, item_count=len(self._icon_frames) + 1)
        occupied = [
            self.icon_positions[key]
            for key in self._icon_frames
            if key in self.icon_positions
        ]
        position = grid.nearest_free_slot(requested, occupied) or grid.snap(requested)
        if position is None:
            position = requested
        pos_x, pos_y = position
        self.icon_positions[icon_key] = [pos_x, pos_y]

        icon_frame = tk.Frame(
            self.canvas,
            bg=self.current_theme.BLACK,
            bd=0,
            highlightthickness=0,
        )
        icon_frame.place(x=pos_x, y=pos_y)
        self.icons_list.append(icon_frame)
        self._icon_frames[icon_key] = icon_frame

        font_main = "Impact" if self.skin_mode == "JOJO" else "Courier New"
        font_sub = ("Courier New", 8, "bold") if self.skin_mode == "JOJO" else ("Consolas", 8, "bold")
        relief_btn = "raised" if self.skin_mode == "JOJO" else "flat"

        btn = tk.Button(icon_frame, text=f"{symbol}", command=command,
                        bg=self.current_theme.PURPLE, fg=self.current_theme.GOLD, font=(font_main, 30),
                        bd=4, relief=relief_btn, activebackground=self.current_theme.PINK,
                        activeforeground=self.current_theme.WHITE, width=3, height=1)
        btn.pack()
        normal_button_style = {
            option: btn.cget(option)
            for option in (
                "bg",
                "activebackground",
                "bd",
                "relief",
                "highlightthickness",
                "padx",
                "pady",
            )
        }

        name_label = tk.Label(
            icon_frame,
            text=name,
            fg=self.current_theme.WHITE,
            bg=self.current_theme.BLACK,
            font=(font_main, 10),
        )
        name_label.pack()
        stand_label = tk.Label(
            icon_frame,
            text=f"[{stand_name}]",
            fg=self.current_theme.PINK,
            bg=self.current_theme.BLACK,
            font=font_sub,
        )
        stand_label.pack()

        def hide_labels_for_drag():
            name_label.pack_forget()
            stand_label.pack_forget()
            canvas_bg = self.canvas.cget("bg")
            btn.configure(
                bg=canvas_bg,
                activebackground=canvas_bg,
                bd=0,
                relief="flat",
                highlightthickness=0,
                padx=0,
                pady=0,
            )
            icon_frame.update_idletasks()

        def restore_labels_after_drag():
            btn.configure(**normal_button_style)
            name_label.pack()
            stand_label.pack()
            icon_frame.update_idletasks()

        drag_controller = DraggableIcon(
            self.canvas,
            icon_frame,
            on_drag_begin=hide_labels_for_drag,
            on_drag_end=restore_labels_after_drag,
        )
        self._drag_controllers[icon_key] = drag_controller

        def iniciar_arraste(_event=None):
            self._drag_origins[icon_key] = [icon_frame.winfo_x(), icon_frame.winfo_y()]

        def finalizar_arraste(_event=None):
            width, height = self._canvas_dimensions()
            grid = self._desktop_grid(width, height, item_count=len(self._icon_frames))
            origin = self._drag_origins.pop(
                icon_key,
                self.icon_positions.get(icon_key, [icon_frame.winfo_x(), icon_frame.winfo_y()]),
            )
            occupied = [
                position
                for key, position in self.icon_positions.items()
                if key != icon_key and key in self._icon_frames
            ]
            position = choose_nearest_free_slot(
                (icon_frame.winfo_x(), icon_frame.winfo_y()),
                occupied,
                origin,
                grid=grid,
            )
            icon_frame.place(x=position[0], y=position[1])
            self.icon_positions[icon_key] = [position[0], position[1]]
            self.save_icon_positions()
            if drag_controller.was_dragged:
                return "break"

        def bind_to_tree(widget, sequence, callback):
            widget.bind(sequence, callback, add="+")
            for child in widget.winfo_children():
                bind_to_tree(child, sequence, callback)

        bind_to_tree(icon_frame, "<Button-1>", iniciar_arraste)
        bind_to_tree(icon_frame, "<ButtonRelease-1>", finalizar_arraste)

    def open_command_window(self):
        from core.command_window import CommandWindow

        if self.command_window and self.command_window.winfo_exists():
            self.command_window.focus_force()
            return

        self.command_window = CommandWindow(self.root, self)

    def open_debugger(self):
        JoJoDebugger(self.root, self.current_theme)

    def open_ia(self):
        # Enviar o objeto da aplicação para a IA, para que ela possa executar comandos
        abrir_janela_ia(self)

    def open_menacing(self):
        start_menacing()
    def handle_security_breach(self, db):
        from tkinter import messagebox
        messagebox.showerror(
            "Integridade do banco",
            "A assinatura do banco não confere. O aplicativo não vai re-assinar dados não confiáveis nem sobrescrever contas. Feche o programa e restaure juntos data/jojo_os.db e data/system_key.json de um backup correspondente.",
            parent=self.root,
        )
    def run_pygame(self):
        """Open the fighting-game hub; IKEMEN GO replaces the old walking demo here."""
        if self.game_hub_window is not None:
            try:
                if self.game_hub_window.winfo_exists():
                    self.game_hub_window.deiconify()
                    self.game_hub_window.lift()
                    self.game_hub_window.focus_force()
                    return self.game_hub_window
            except tk.TclError:
                pass
        from core.games.hub_jogos import abrir_hub_jogos

        self.game_hub_window = abrir_hub_jogos(self.root)
        return self.game_hub_window

    def open_antivirus(self):
        existing = getattr(self, "_antivirus_window", None)
        if existing is not None and existing.is_open():
            existing.window.lift()
            existing.window.focus_force()
            return
        from core.antivirus_window import AntivirusWindow

        self._antivirus_window = AntivirusWindow(self.root, self)

    def show_error_no_sound(self, title, message):
        win = tk.Toplevel(self.root)
        win.title(title)
        win.geometry("420x140")
        win.configure(bg=self.current_theme.BLACK)
        win.transient(self.root)
        win.resizable(False, False)

        tk.Label(win, text=title, fg=self.current_theme.PINK, bg=self.current_theme.BLACK, font=("Impact", 14, "bold")).pack(pady=(10, 5))
        tk.Label(win, text=message, fg=self.current_theme.GOLD, bg=self.current_theme.BLACK, font=("Courier New", 10), wraplength=380, justify="center").pack(padx=10)

        btn_frame = tk.Frame(win, bg=self.current_theme.BLACK)
        btn_frame.pack(pady=10)
        tk.Button(btn_frame, text="OK", width=10, bg=self.current_theme.PURPLE, fg=self.current_theme.GOLD,
                  command=win.destroy).pack()

        # Evita que outros widgets da janela principal recebam foco até fechar
        win.grab_set()

    def open_admin_panel(self):
        from tkinter import messagebox
        win = tk.Toplevel(self.root)
        win.title("ADMIN CONTROL PANEL")
        win.geometry("300x200")
        win.configure(bg="black")
        tk.Label(win, text="GERENCIAMENTO DE STANDS", fg="gold", bg="black").pack(pady=20)

        legacy_state_file = APP_ROOT / "data" / "system_state.json"
        try:
            saved_state = get_setting("system_state", None, path=DB_FILE)
            if saved_state is None and legacy_state_file.is_file():
                saved_state = json.loads(legacy_state_file.read_text(encoding="utf-8"))
                set_setting("system_state", saved_state, path=DB_FILE)
                self._archive_legacy_data_file(legacy_state_file)
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError, RuntimeError) as exc:
            messagebox.showerror("Estado local", f"Não foi possível migrar o estado para SQLite: {exc}", parent=win)
            win.destroy()
            return

        def reset_state():
            try:
                current_state = get_setting("system_state", None, path=DB_FILE)
            except (OSError, ValueError, RuntimeError) as exc:
                messagebox.showerror("Reset", f"Não foi possível ler o estado SQLite: {exc}", parent=win)
                return
            if current_state is None:
                messagebox.showinfo("Reset", "Não existe estado salvo para resetar.", parent=win)
                return
            if not messagebox.askyesno("Confirmar reset", "Apagar o estado local do banco SQLite? Esta ação não pode ser desfeita.", parent=win):
                return
            try:
                delete_setting("system_state", path=DB_FILE)
                messagebox.showinfo("Reset", "Estado removido.", parent=win)
            except (OSError, ValueError, RuntimeError) as exc:
                messagebox.showerror("Reset", f"Não foi possível remover: {exc}", parent=win)

        tk.Button(win, text="Resetar estado local", command=reset_state).pack()

    def logout(self):
        # Esconde tudo e volta para o login
        self.root.withdraw()
        # Remove o botão de logout antigo para não duplicar quando voltar
        
        if hasattr(self, "btn_logout"):

            self.btn_logout.destroy()
        self.chamar_login()

    def open_piano(self):
        from ui.piano.main import PianoWindow
        PianoWindow(self.root, self.current_theme)
    def chamar_login(self):
        """Prepara o ambiente e chama a autenticação"""
        # Força o processamento de eventos antes de esconder para evitar erro de desenho
        self.root.update()
        self.root.withdraw()
        
        # Chama a classe que criamos acima
        LoginWindow(self.root, self.current_theme, self.liberar_sistema)

    def liberar_sistema(self, user, is_admin=False, theme_data=None, stand=None, os_profile="JOJO"):
        self.current_user = user
        self.is_admin = is_admin
        self.current_stand = stand
        self.stand_theme = theme_data if isinstance(theme_data, dict) else {}
        self.set_skin_mode(os_profile, render=False)
        base = HackerTheme if self.skin_mode in {"CLEITON", "HACKER"} else JoJoTheme

        def valid_color(value, fallback):
            if isinstance(value, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", value):
                return value
            return fallback

        # Tema por usuário: nunca mutar os atributos de classe compartilhados.
        self.current_theme = SimpleNamespace(
            BLACK=valid_color(self.stand_theme.get("bg"), base.BLACK),
            PURPLE=valid_color(self.stand_theme.get("accent"), base.PURPLE),
            GOLD=valid_color(self.stand_theme.get("fg"), base.GOLD),
            PINK=base.PINK,
            WHITE=base.WHITE,
        )
        
        # Aplicar cores na interface principal
        self.root.configure(bg=self.current_theme.BLACK)
        self.top_bar.configure(bg=self.current_theme.PURPLE)
        self.canvas.configure(bg=self.current_theme.BLACK)
        self.btn_skin.configure(bg=self.current_theme.PURPLE, fg=self.current_theme.GOLD)
        self.title_label.configure(bg=self.current_theme.PURPLE, fg=self.current_theme.GOLD)
        
        self.root.deiconify() # Mostra a janela principal
        self.render_icons()

        # --- SEGREDO: THE WORLD / ZA WARUDO ---
        if user in ["the world", "za warudo"]:
            self.trigger_time_stop()

    def trigger_time_stop(self):
        self.play_stand_sound("dio-time-stop.wav")

        def start_effect():
            try:
                if not self.root.winfo_exists():
                    return
                if self.time_stop_effect is not None:
                    self.time_stop_effect.stop()
                effect = TimeStopEffect(
                    self.root,
                    duration_ms=4000,
                    expansion_ms=3000,
                    frame_ms=40,
                    title="ZA WARUDO",
                    title_color=self.current_theme.GOLD,
                    ring_color=self.current_theme.PINK,
                    on_complete=self._clear_time_stop_effect,
                )
                self.time_stop_effect = effect
                if not effect.start():
                    self.time_stop_effect = None
            except tk.TclError:
                self.time_stop_effect = None

        try:
            self.root.after_idle(start_effect)
        except tk.TclError:
            return

    def _clear_time_stop_effect(self):
        self.time_stop_effect = None

    def play_stand_sound(self, filename):
        try:
            sound_path = APP_ROOT / "soms" / Path(filename).name
            if self.audio_available and sound_path.is_file():
                mixer.Sound(str(sound_path)).play()
        except (pygame.error, OSError, TypeError, ValueError):
            return

    def open_calc(self):
        win = tk.Toplevel(self.root)
        # Se for THE WORLD, manda o comando MUDA, senão manda ORA
        calc_audio = "muda" if isinstance(self.current_user, str) and "za warudo" in self.current_user.lower() else "ora"
        JoJoCalc(win, theme_atual=self.skin_mode, sound_mode=calc_audio)

if __name__ == "__main__":
    root = tk.Tk()
    try:
        db = carregar_db_seguro(DB_FILE)
    except (OSError, SecurityStoreError, ValueError) as exc:
        from tkinter import messagebox
        messagebox.showerror("JOJO-OS", f"Não foi possível abrir o banco local:\n{exc}\n\nNenhum dado foi alterado.", parent=root)
        root.destroy()
        raise SystemExit(1)

    if db.get("__hack_detected__") is True:
        from tkinter import messagebox
        messagebox.showerror(
            "JOJO-OS — integridade",
            "A assinatura do banco não confere. O aplicativo foi fechado sem sobrescrever os dados. Restaure juntos data/jojo_os.db e data/system_key.json de um backup confiável.",
            parent=root,
        )
        root.destroy()
        raise SystemExit(1)
    app = JoJoOS(root)
    app.chamar_login()
    root.mainloop()