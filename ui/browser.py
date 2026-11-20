"""Launcher seguro para o navegador Chromium opcional.

A aplicação principal usa Tkinter. Como o QtWebEngine mantém seu próprio ciclo
 de eventos, o navegador visual é executado em um processo separado por
:class:`BrowserApp`. O módulo não importa PyQt6, para que o restante do
aplicativo continue inicializando mesmo sem a dependência opcional.
"""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox
from urllib.parse import urlsplit

ALLOWED_SCHEMES = frozenset({"http", "https"})
ABOUT_BLANK = "about:blank"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")


class BrowserInputError(ValueError):
    """Indica que um endereço não pode ser navegado pelo navegador."""


def normalize_browser_url(value: str, *, allow_about_blank: bool = True) -> str:
    """Valida e normaliza um endereço para a barra do navegador.

    Endereços sem esquema recebem ``https://``. Apenas HTTP e HTTPS são
    aceitos para navegação externa; ``about:blank`` é a única página interna
    permitida para novas guias e para o botão Início.
    """

    if not isinstance(value, str):
        raise BrowserInputError("Digite um endereço web válido.")

    raw = value.strip()
    if not raw:
        raise BrowserInputError("Digite um endereço web.")
    if any(char.isspace() or ord(char) < 32 for char in raw) or "\\" in raw:
        raise BrowserInputError("O endereço contém caracteres inválidos.")

    if raw.lower() == ABOUT_BLANK:
        if allow_about_blank:
            return ABOUT_BLANK
        raise BrowserInputError("Somente endereços http:// e https:// são aceitos.")

    scheme_match = _SCHEME_RE.match(raw)
    if scheme_match:
        scheme = scheme_match.group(0)[:-1].lower()
        if scheme not in ALLOWED_SCHEMES:
            raise BrowserInputError("Somente endereços http:// e https:// são aceitos.")
        candidate = raw
    else:
        candidate = f"https://{raw}"

    try:
        parsed = urlsplit(candidate)
        hostname = parsed.hostname
        # Força a validação da porta; urlsplit levanta ValueError para portas
        # inválidas, inclusive em endereços IPv6 malformados.
        _ = parsed.port
    except ValueError as exc:
        raise BrowserInputError("O endereço web não é válido.") from exc

    if parsed.scheme.lower() not in ALLOWED_SCHEMES or not parsed.netloc or not hostname:
        raise BrowserInputError("Somente endereços http:// e https:// são aceitos.")

    return candidate


def is_allowed_navigation(url: str) -> bool:
    """Retorna se uma URL já formada pode ser carregada pelo WebEngine."""

    try:
        normalize_browser_url(url, allow_about_blank=True)
    except BrowserInputError:
        return False
    return True


def qt_webengine_available() -> bool:
    """Detecta PyQt6-WebEngine sem importar Qt no processo Tkinter."""

    try:
        if importlib.util.find_spec("PyQt6") is None:
            return False
        return importlib.util.find_spec("PyQt6.QtWebEngineWidgets") is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def browser_process_command() -> list[str]:
    """Monta o comando do processo Qt sem shell e sem incluir a URL."""

    return [sys.executable, "-m", "ui.browser_qt"]


def launch_browser_process(initial_url: str) -> subprocess.Popen[str]:
    """Abre o processo Qt e encaminha uma única URL validada por stdin."""

    url = normalize_browser_url(initial_url, allow_about_blank=True)
    process = subprocess.Popen(
        browser_process_command(),
        cwd=str(PROJECT_ROOT),
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    try:
        if process.stdin is None:
            raise OSError("O processo do navegador não abriu o canal inicial.")
        process.stdin.write(json.dumps({"url": url}) + "\n")
        process.stdin.close()
    except (OSError, ValueError, subprocess.SubprocessError):
        try:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    process.kill()
        except (OSError, subprocess.SubprocessError):
            pass
        raise
    return process


class BrowserApp:
    """Compatibilidade com ``BrowserApp(master)`` usada pelo desktop Tkinter.

    A janela Tk serve apenas como launcher e como painel de erro quando o
    componente opcional não está instalado. Com o componente disponível, ela
    é ocultada após iniciar ``ui.browser_qt``; a janela com abas e Chromium é
    criada pelo processo Qt separado.
    """

    def __init__(self, master: tk.Misc):
        self.master = master
        self.process: subprocess.Popen[str] | None = None
        self._engine_available = qt_webengine_available()

        self._build_launcher()
        if self._engine_available:
            # Mantém a chamada compatível e abre uma nova guia real sem exigir
            # uma segunda ação do usuário ao clicar no ícone do desktop.
            self.master.after_idle(self.open_browser)
        else:
            self._show_missing_engine()

    def _build_launcher(self) -> None:
        self.master.title("Navegador")
        self.master.geometry("560x220")
        self.master.minsize(480, 200)
        self.master.configure(bg="#111827")
        self.master.protocol("WM_DELETE_WINDOW", self.close)

        header = tk.Frame(self.master, bg="#111827")
        header.pack(fill="x", padx=20, pady=(18, 8))
        tk.Label(
            header,
            text="NAVEGADOR",
            bg="#111827",
            fg="#f9fafb",
            font=("Segoe UI", 16, "bold"),
        ).pack(anchor="w")
        tk.Label(
            header,
            text="Chromium isolado do processo principal",
            bg="#111827",
            fg="#9ca3af",
            font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(2, 0))

        address_frame = tk.Frame(self.master, bg="#111827")
        address_frame.pack(fill="x", padx=20, pady=(8, 6))
        self.url_entry = tk.Entry(
            address_frame,
            bg="#1f2937",
            fg="#f9fafb",
            insertbackground="#f9fafb",
            relief="flat",
            font=("Segoe UI", 11),
        )
        self.url_entry.pack(side="left", expand=True, fill="x", ipady=8)
        self.url_entry.insert(0, ABOUT_BLANK)
        self.url_entry.bind("<Return>", lambda _event: self.open_browser())

        self.go_button = tk.Button(
            address_frame,
            text="Abrir",
            command=self.open_browser,
            bg="#7c3aed",
            fg="#ffffff",
            activebackground="#6d28d9",
            activeforeground="#ffffff",
            relief="flat",
            cursor="hand2",
            font=("Segoe UI", 10, "bold"),
            padx=16,
        )
        self.go_button.pack(side="left", padx=(8, 0), ipady=5)

        self.status_var = tk.StringVar(value="Pronto para abrir uma nova guia.")
        self.status_label = tk.Label(
            self.master,
            textvariable=self.status_var,
            bg="#111827",
            fg="#d1d5db",
            justify="left",
            anchor="w",
            wraplength=510,
            font=("Segoe UI", 9),
        )
        self.status_label.pack(fill="x", padx=20, pady=(8, 8))

        self.quit_button = tk.Button(
            self.master,
            text="Fechar",
            command=self.close,
            bg="#374151",
            fg="#f9fafb",
            activebackground="#4b5563",
            activeforeground="#ffffff",
            relief="flat",
            cursor="hand2",
            font=("Segoe UI", 9),
            padx=14,
        )
        self.quit_button.pack(anchor="e", padx=20, pady=(0, 14))

        # O método run_browser mantém apenas uma referência local. Atribuir a
        # instância ao widget evita que o controlador seja coletado enquanto
        # o subprocesso Qt estiver em execução.
        self.master._browser_app = self

    def _show_missing_engine(self) -> None:
        self.status_var.set(
            "Motor Chromium indisponível. Instale a dependência opcional com:\n"
            "python -m pip install -r requirements-optional.txt"
        )
        self.status_label.configure(fg="#fbbf24")

    def _set_error(self, message: str) -> None:
        self.status_var.set(message)
        self.status_label.configure(fg="#fca5a5")

    def open_browser(self) -> None:
        """Valida a barra inicial e abre/reutiliza o processo Chromium."""

        if not self._engine_available:
            self._show_missing_engine()
            return
        if self.process is not None and self.process.poll() is None:
            return

        try:
            url = normalize_browser_url(self.url_entry.get(), allow_about_blank=True)
        except BrowserInputError as exc:
            self._set_error(str(exc))
            try:
                messagebox.showerror("Navegador", str(exc), parent=self.master)
            except tk.TclError:
                # Permite testar a validação em ambientes sem display.
                pass
            return

        try:
            self.process = launch_browser_process(url)
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            self.process = None
            self._set_error(f"Não foi possível iniciar o navegador Chromium: {exc}")
            return

        self.status_var.set("Navegador Chromium iniciado.")
        self.status_label.configure(fg="#86efac")
        self.master.withdraw()
        self.master.after(250, self._monitor_process)

    def _monitor_process(self) -> None:
        if self.process is None:
            return
        return_code = self.process.poll()
        if return_code is None:
            self.master.after(250, self._monitor_process)
            return

        self.process = None
        self.master.deiconify()
        if return_code == 0:
            self.status_var.set("Navegador encerrado.")
            self.status_label.configure(fg="#d1d5db")
        else:
            self._set_error(
                "O processo Chromium foi encerrado antes de abrir a janela. "
                "Verifique a instalação de PyQt6-WebEngine."
            )

    def close(self) -> None:
        """Encerra apenas o processo filho criado por esta janela."""

        if self.process is not None and self.process.poll() is None:
            try:
                self.process.terminate()
            except (OSError, ProcessLookupError, subprocess.SubprocessError):
                pass
        self.process = None
        try:
            self.master.destroy()
        except tk.TclError:
            pass


if __name__ == "__main__":
    root = tk.Tk()
    BrowserApp(root)
    root.mainloop()
