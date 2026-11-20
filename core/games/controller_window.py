"""Tk companion-controller window for the IKEMEN GO hub."""
from __future__ import annotations

import queue
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from core.games.controller_bridge import (
    ALLOWED_KEYS,
    CONTROL_BITS,
    DEFAULT_MAPPING,
    PORT,
    AdbReverseLease,
    ControllerBridge,
    establish_adb_reverse,
    find_adb_path,
    validate_mapping,
)

PLATFORM_TOOLS_URL = "https://developer.android.com/tools/releases/platform-tools"


class ControllerWindow:
    """Own one controller Toplevel and marshal worker events through a queue."""

    def __init__(self, parent: tk.Misc, on_close=None) -> None:
        self.parent = parent
        self.on_close = on_close
        self.window = tk.Toplevel(parent)
        self.window.title("JoJo-OS — Controle pelo celular")
        self.window.geometry("800x710")
        self.window.minsize(680, 600)
        self.window.configure(bg="#1e102b")
        self.window.transient(parent)
        self.window.protocol("WM_DELETE_WINDOW", self.close)

        self._events: queue.Queue[tuple] = queue.Queue()
        self._phase = "idle"
        self._bridge: ControllerBridge | None = None
        self._lease: AdbReverseLease | None = None
        self._worker: threading.Thread | None = None
        self._cancel_event = threading.Event()
        self._closing = False
        self._destroyed = False
        self._poll_id: str | None = None
        self._mapping = dict(DEFAULT_MAPPING)

        try:
            adb_default = find_adb_path()
        except FileNotFoundError:
            adb_default = ""
        self.adb_path_var = tk.StringVar(master=self.window, value=adb_default)
        self.game_path_var = tk.StringVar(master=self.window, value="")
        self.token_var = tk.StringVar(master=self.window, value="")
        self.status_var = tk.StringVar(value="Desconectado")
        self.diagnostics_var = tk.StringVar(value="ADB USB ainda não verificado.")
        self.mapping_vars: dict[str, tk.StringVar] = {}

        self._build_ui()
        self._poll_id = self.window.after(100, self._poll_events)

    def _build_ui(self) -> None:
        self.window.configure(padx=18, pady=14)
        heading = tk.Label(
            self.window,
            text="CONTROLE PELO CELULAR",
            font=("Arial", 18, "bold"),
            bg="#1e102b",
            fg="#ffcc00",
        )
        heading.pack(anchor="w", pady=(0, 3))
        tk.Label(
            self.window,
            text=(
                "USB envia apenas os 11 botões do controle ao IKEMEN GO no Windows. "
                "A ponte aceita conexões somente por 127.0.0.1."
            ),
            font=("Arial", 10),
            bg="#1e102b",
            fg="#d9c6e8",
            justify="left",
            wraplength=740,
        ).pack(anchor="w", pady=(0, 12))

        notebook = ttk.Notebook(self.window)
        notebook.pack(fill="both", expand=True)
        usb_tab = tk.Frame(notebook, bg="#30203d", padx=15, pady=13)
        bluetooth_tab = tk.Frame(notebook, bg="#30203d", padx=15, pady=13)
        notebook.add(usb_tab, text="USB (ADB)")
        notebook.add(bluetooth_tab, text="Bluetooth HID")
        self._build_usb_tab(usb_tab)
        self._build_bluetooth_tab(bluetooth_tab)

        tk.Label(
            self.window,
            textvariable=self.status_var,
            font=("Arial", 10, "bold"),
            bg="#1e102b",
            fg="#b7f0c1",
            anchor="w",
            wraplength=740,
        ).pack(fill="x", pady=(10, 2))
        tk.Label(
            self.window,
            textvariable=self.diagnostics_var,
            font=("Arial", 9),
            bg="#1e102b",
            fg="#bbaec6",
            anchor="w",
            justify="left",
            wraplength=740,
        ).pack(fill="x", pady=(0, 2))

    def _build_usb_tab(self, parent: tk.Frame) -> None:
        tk.Label(
            parent,
            text=(
                "Conecte o Android por USB, habilite Depuração USB e aceite a solicitação RSA "
                "no telefone. Ao iniciar, o JoJo-OS lista os dispositivos autorizados e cria "
                "adb -d reverse --no-rebind tcp:8765 tcp:8765. A janela do PC não instala nem "
                "executa APK: o cliente Android deve conectar a 127.0.0.1:8765, enviar primeiro "
                '{"token":"<32 lowercase hex>","protocol":1} e aguardar o ACK; depois envia '
                '{"mask":0..2047} em linhas JSON a cada 100 ms e em toda mudança. Só o handshake '
                "recebe ACK. Bits: Up 0, Down 1, Left 2, Right 3, A 4, B 5, C 6, X 7, Y 8, "
                "Z 9, Start 10."
            ),
            font=("Arial", 10),
            bg="#30203d",
            fg="#eee6f3",
            justify="left",
            wraplength=690,
        ).pack(anchor="w", pady=(0, 10))

        adb_row = tk.Frame(parent, bg="#30203d")
        adb_row.pack(fill="x", pady=(0, 8))
        tk.Label(
            adb_row,
            text="ADB:",
            font=("Arial", 9, "bold"),
            bg="#30203d",
            fg="#ffffff",
        ).pack(side="left", padx=(0, 7))
        self.adb_entry = ttk.Entry(adb_row, textvariable=self.adb_path_var)
        self.adb_entry.pack(side="left", fill="x", expand=True, padx=(0, 7))
        ttk.Button(adb_row, text="Escolher adb.exe…", command=self._choose_adb).pack(side="left")
        platform_tools_link = tk.Label(
            parent,
            text="Baixar Android SDK Platform-Tools oficial",
            font=("Arial", 9, "underline"),
            bg="#30203d",
            fg="#8ed8ff",
            cursor="hand2",
        )
        platform_tools_link.pack(anchor="w", pady=(0, 8))
        platform_tools_link.bind(
            "<Button-1>", lambda _event: webbrowser.open(PLATFORM_TOOLS_URL)
        )

        path_row = tk.Frame(parent, bg="#30203d")
        path_row.pack(fill="x", pady=(0, 10))
        tk.Label(
            path_row,
            text="IKEMEN_GO.exe (opcional):",
            font=("Arial", 9, "bold"),
            bg="#30203d",
            fg="#ffffff",
        ).pack(side="left", padx=(0, 7))
        self.game_entry = ttk.Entry(path_row, textvariable=self.game_path_var)
        self.game_entry.pack(side="left", fill="x", expand=True, padx=(0, 7))
        ttk.Button(path_row, text="Escolher…", command=self._choose_game).pack(side="left")
        tk.Label(
            parent,
            text=(
                "Se informar o caminho acima, as teclas só serão enviadas enquanto a janela em "
                "primeiro plano pertencer exatamente a esse executável. Sem caminho, não há filtro "
                "de processo. A janela não edita os arquivos de configuração do IKEMEN."
            ),
            font=("Arial", 9),
            bg="#30203d",
            fg="#d0c3da",
            justify="left",
            wraplength=690,
        ).pack(anchor="w", pady=(0, 11))

        token_row = tk.Frame(parent, bg="#30203d")
        token_row.pack(fill="x", pady=(0, 9))
        tk.Label(
            token_row,
            text="Token da sessão:",
            font=("Arial", 9, "bold"),
            bg="#30203d",
            fg="#ffffff",
        ).pack(side="left", padx=(0, 7))
        self.token_entry = ttk.Entry(token_row, textvariable=self.token_var, state="readonly")
        self.token_entry.pack(side="left", fill="x", expand=True, padx=(0, 7))
        ttk.Button(token_row, text="Copiar", command=self.copy_token).pack(side="left")

        actions = tk.Frame(parent, bg="#30203d")
        actions.pack(fill="x", pady=(0, 11))
        self.connect_button = tk.Button(
            actions,
            text="CONECTAR USB",
            font=("Arial", 10, "bold"),
            bg="#00aa55",
            fg="#ffffff",
            activebackground="#008844",
            activeforeground="#ffffff",
            bd=0,
            padx=16,
            pady=8,
            cursor="hand2",
            command=self.connect_usb,
        )
        self.connect_button.pack(side="left", padx=(0, 8))
        self.disconnect_button = tk.Button(
            actions,
            text="DESCONECTAR",
            font=("Arial", 10, "bold"),
            bg="#9a3b54",
            fg="#ffffff",
            activebackground="#b64b67",
            activeforeground="#ffffff",
            bd=0,
            padx=16,
            pady=8,
            cursor="hand2",
            state=tk.DISABLED,
            command=self.disconnect_usb,
        )
        self.disconnect_button.pack(side="left")

        mapping_frame = tk.LabelFrame(
            parent,
            text="Mapeamento de teclas no PC",
            font=("Arial", 10, "bold"),
            bg="#30203d",
            fg="#ffcc00",
            padx=10,
            pady=7,
        )
        mapping_frame.pack(fill="x", pady=(1, 5))
        self._build_mapping(mapping_frame)
        tk.Label(
            parent,
            text=(
                "Padrão: direções = setas; A=z, B=x, C=c, X=a, Y=s, Z=d, Start=Enter. "
                "Este mapeamento envia teclas ao Windows, mas não altera command/config do IKEMEN; "
                "se necessário, ajuste os comandos do jogo manualmente."
            ),
            font=("Arial", 9),
            bg="#30203d",
            fg="#d0c3da",
            justify="left",
            wraplength=690,
        ).pack(anchor="w", pady=(4, 0))

    def _build_mapping(self, parent: tk.LabelFrame) -> None:
        key_values = [key for key in ALLOWED_KEYS]
        for index, (control, _bit) in enumerate(CONTROL_BITS):
            row, column = divmod(index, 4)
            cell = tk.Frame(parent, bg="#30203d")
            cell.grid(row=row, column=column, sticky="ew", padx=4, pady=3)
            tk.Label(
                cell,
                text=f"{control}:",
                width=7,
                anchor="w",
                font=("Arial", 9),
                bg="#30203d",
                fg="#ffffff",
            ).pack(side="left")
            variable = tk.StringVar(master=self.window, value=self._mapping[control])
            self.mapping_vars[control] = variable
            ttk.Combobox(
                cell,
                textvariable=variable,
                values=key_values,
                state="readonly",
                width=8,
            ).pack(side="left", fill="x", expand=True)
            parent.grid_columnconfigure(column, weight=1)
        self.apply_mapping_button = ttk.Button(
            parent,
            text="Aplicar mapeamento",
            command=self.apply_mapping,
        )
        self.apply_mapping_button.grid(row=3, column=0, columnspan=4, sticky="e", pady=(5, 0))

    def _build_bluetooth_tab(self, parent: tk.Frame) -> None:
        instructions = (
            "Bluetooth HID é um caminho separado do USB/ADB. Esta janela não cria nem consulta "
            "uma conexão Bluetooth e o projeto não instala nem executa um APK companion.\n\n"
            "Para usar Bluetooth, o Android precisa de um aplicativo que implemente o perfil "
            "Bluetooth HID Device (disponível a partir do Android 9 / API 28). O aplicativo Android "
            "deve declarar e solicitar as permissões Bluetooth adequadas à versão e ao target SDK: "
            "BLUETOOTH e BLUETOOTH_ADMIN em versões anteriores; em Android 12 ou mais recente, "
            "BLUETOOTH_CONNECT e BLUETOOTH_ADVERTISE (permissões de execução, quando aplicável).\n\n"
            "1. No telefone, habilite o perfil HID no aplicativo compatível e inicie o pareamento.\n"
            "2. No Windows, abra Configurações > Bluetooth e dispositivos e pareie o telefone.\n"
            "3. Confira o dispositivo em Configurações de entrada / Controladores de jogo "
            "(ou execute joy.cpl). Se o Android o apresentar como teclado, teste as teclas no jogo.\n\n"
            "Não mostramos um indicador de Bluetooth conectado: o JoJo-OS não observa esse perfil. "
            "O HID é fornecido pelo telefone e pelo Windows, não por esta ponte USB."
        )
        tk.Label(
            parent,
            text="Uso de controle Bluetooth HID",
            font=("Arial", 13, "bold"),
            bg="#30203d",
            fg="#ffcc00",
        ).pack(anchor="w", pady=(0, 12))
        tk.Label(
            parent,
            text=instructions,
            font=("Arial", 10),
            bg="#30203d",
            fg="#eee6f3",
            justify="left",
            anchor="nw",
            wraplength=690,
        ).pack(fill="both", expand=True)

    def _choose_adb(self) -> None:
        path = filedialog.askopenfilename(
            parent=self.window,
            title="Escolher ADB do Android Platform Tools",
            filetypes=(("ADB", "adb.exe"), ("Todos os arquivos", "*")),
        )
        if path:
            self.adb_path_var.set(path)

    def _choose_game(self) -> None:
        path = filedialog.askopenfilename(
            parent=self.window,
            title="Escolher executável do IKEMEN GO",
            filetypes=(("IKEMEN GO", "Ikemen_GO.exe"), ("Executáveis", "*.exe"), ("Todos", "*")),
        )
        if path:
            self.game_path_var.set(path)

    def _read_mapping(self) -> dict[str, str]:
        try:
            mapping = validate_mapping(
                {control: variable.get() for control, variable in self.mapping_vars.items()}
            )
        except ValueError as exc:
            messagebox.showerror("Mapeamento inválido", str(exc), parent=self.window)
            raise
        return mapping

    def apply_mapping(self) -> None:
        try:
            mapping = self._read_mapping()
        except ValueError:
            return
        self._mapping = mapping
        if self._bridge is not None and self._phase in {"starting", "connected"}:
            self._bridge.set_mapping(mapping)
        self.status_var.set("Mapeamento aplicado. Uma máscara neutra será exigida antes de retomar.")

    def copy_token(self) -> None:
        token = self.token_var.get()
        if not token:
            self.status_var.set("Inicie uma sessão USB para gerar um token temporário.")
            return
        self.window.clipboard_clear()
        self.window.clipboard_append(token)
        self.status_var.set("Token temporário copiado para a área de transferência.")

    def connect_usb(self) -> None:
        if self._phase != "idle" or self._closing:
            return
        try:
            mapping = self._read_mapping()
            adb_path = find_adb_path(self.adb_path_var.get().strip() or None)
        except (ValueError, FileNotFoundError) as exc:
            messagebox.showerror(
                "Preparar controle USB",
                f"{exc}\n\nInstale o Android Platform Tools e escolha adb.exe, se necessário.",
                parent=self.window,
            )
            return

        expected_path = self.game_path_var.get().strip() or None
        if expected_path and (
            Path(expected_path).name.casefold() != "ikemen_go.exe"
            or not Path(expected_path).is_file()
        ):
            messagebox.showerror(
                "Executável IKEMEN não encontrado",
                "Escolha o caminho completo de um Ikemen_GO.exe existente ou deixe o campo vazio.",
                parent=self.window,
            )
            return
        try:
            bridge = ControllerBridge(
                mapping=mapping,
                expected_ikemen_path=expected_path,
                on_status=lambda message: self._events.put(("bridge_status", message)),
            )
        except (OSError, RuntimeError) as exc:
            messagebox.showerror("Controle USB indisponível", str(exc), parent=self.window)
            return

        self._mapping = mapping
        self._bridge = bridge
        self._lease = None
        self._cancel_event.clear()
        self._phase = "starting"
        self._set_busy(True)
        self.token_var.set("")
        self.diagnostics_var.set("Iniciando servidor local e verificando adb devices -l…")
        self.status_var.set("Preparando a sessão USB…")
        self._worker = threading.Thread(
            target=self._startup_worker,
            args=(bridge, adb_path),
            name="jojo-controller-usb-start",
            daemon=True,
        )
        self._worker.start()

    def _startup_worker(self, bridge: ControllerBridge, adb_path: str) -> None:
        lease: AdbReverseLease | None = None
        try:
            token = bridge.start()
            if self._cancel_event.is_set():
                bridge.stop()
                self._events.put(("stopped", None))
                return
            lease, diagnostics = establish_adb_reverse(adb_path)
            if self._cancel_event.is_set():
                bridge.stop()
                cleanup_error = lease.cleanup()
                self._events.put(("stopped", cleanup_error))
                return
            self._events.put(("connected", token, lease, diagnostics))
        except Exception as exc:  # noqa: BLE001 - display bounded setup failures in the window.
            bridge.stop()
            if lease is not None:
                lease.cleanup()
            self._events.put(("start_error", f"{type(exc).__name__}: {exc}"))

    def disconnect_usb(self) -> None:
        if self._phase == "starting":
            self._cancel_event.set()
            if self._bridge is not None:
                self._bridge.request_stop()
            self._phase = "stopping"
            self.disconnect_button.configure(state=tk.DISABLED)
            self.status_var.set("Cancelando a conexão e liberando todas as teclas…")
            return
        if self._phase == "connected":
            self._begin_shutdown(close_when_done=False)

    def _begin_shutdown(self, *, close_when_done: bool) -> None:
        if close_when_done:
            self._closing = True
            try:
                self.window.withdraw()
            except tk.TclError:
                pass
        if self._phase == "starting":
            self._cancel_event.set()
            if self._bridge is not None:
                self._bridge.request_stop()
            self._phase = "stopping"
            return
        if self._phase == "stopping":
            return
        if self._phase != "connected":
            if self._closing:
                self._destroy()
            return
        bridge, lease = self._bridge, self._lease
        self._phase = "stopping"
        self._set_busy(True)
        self.status_var.set("Desconectando, removendo somente o reverse desta sessão e liberando teclas…")
        if bridge is not None:
            bridge.request_stop()
        self._worker = threading.Thread(
            target=self._shutdown_worker,
            args=(bridge, lease),
            name="jojo-controller-usb-stop",
            daemon=True,
        )
        self._worker.start()

    def _shutdown_worker(
        self,
        bridge: ControllerBridge | None,
        lease: AdbReverseLease | None,
    ) -> None:
        if bridge is not None:
            bridge.stop()
        cleanup_error = lease.cleanup() if lease is not None else None
        self._events.put(("stopped", cleanup_error))

    def _set_busy(self, busy: bool) -> None:
        if self._destroyed:
            return
        self.connect_button.configure(state=tk.DISABLED if busy else tk.NORMAL)
        self.disconnect_button.configure(
            state=tk.NORMAL if self._phase == "connected" and not busy else tk.DISABLED
        )
        self.adb_entry.configure(state=tk.DISABLED if busy else tk.NORMAL)
        self.game_entry.configure(state=tk.DISABLED if busy else tk.NORMAL)

    def _poll_events(self) -> None:
        if self._destroyed:
            return
        try:
            while True:
                event = self._events.get_nowait()
                name = event[0]
                if name == "bridge_status":
                    if not self._closing:
                        self.status_var.set(str(event[1]))
                elif name == "connected":
                    _name, token, lease, diagnostics = event
                    if self._cancel_event.is_set() or self._closing:
                        self._lease = lease
                        self._phase = "connected"
                        self._begin_shutdown(close_when_done=self._closing)
                    else:
                        self._lease = lease
                        self._phase = "connected"
                        self.token_var.set(token)
                        authorized_count = sum(
                            1
                            for line in diagnostics.splitlines()[1:]
                            if len(line.split()) >= 2 and line.split()[1] == "device"
                        )
                        self.diagnostics_var.set(
                            f"ADB autorizado; {authorized_count} dispositivo(s) listado(s). "
                            f"Loopback: 127.0.0.1:{PORT}."
                        )
                        self.status_var.set("Sessão USB pronta. Copie o token e informe-o ao companion Android.")
                        self._set_busy(False)
                elif name == "start_error":
                    detail = str(event[1])
                    was_cancelled = self._cancel_event.is_set()
                    self._bridge = None
                    self._lease = None
                    self._phase = "idle"
                    self._cancel_event.clear()
                    self.token_var.set("")
                    self._set_busy(False)
                    if self._closing:
                        self._destroy()
                    elif was_cancelled:
                        self.status_var.set("Conexão cancelada; nenhuma tecla permanece pressionada.")
                    else:
                        self.status_var.set("Não foi possível iniciar a sessão USB.")
                        messagebox.showerror("Controle USB", detail, parent=self.window)
                elif name == "stopped":
                    _name, cleanup_error = event
                    self._bridge = None
                    self._lease = None
                    self._worker = None
                    self._phase = "idle"
                    self._cancel_event.clear()
                    self.token_var.set("")
                    if self._closing:
                        self._destroy()
                    else:
                        self._set_busy(False)
                        if cleanup_error:
                            self.status_var.set(str(cleanup_error))
                            messagebox.showwarning(
                                "Controle USB",
                                str(cleanup_error),
                                parent=self.window,
                            )
                        else:
                            self.status_var.set("Desconectado; todas as teclas foram liberadas.")
        except queue.Empty:
            pass
        if not self._destroyed:
            self._poll_id = self.window.after(100, self._poll_events)

    def show(self) -> None:
        if self._destroyed or self._closing:
            return
        self.window.deiconify()
        self.window.lift()

    def close(self) -> None:
        """Stop the USB session before destroying this child window."""
        if self._destroyed or self._closing:
            return
        if self._phase in {"starting", "connected", "stopping"}:
            self._begin_shutdown(close_when_done=True)
            return
        self._closing = True
        self._destroy()

    def _destroy(self) -> None:
        if self._destroyed:
            return
        self._destroyed = True
        if self._poll_id is not None:
            try:
                self.window.after_cancel(self._poll_id)
            except tk.TclError:
                pass
        try:
            self.window.destroy()
        except tk.TclError:
            pass
        if self.on_close is not None:
            callback, self.on_close = self.on_close, None
            callback()


def abrir_janela_controle(parent: tk.Misc, on_close=None) -> ControllerWindow:
    """Open the phone-controller window and return its lifecycle handle."""
    return ControllerWindow(parent, on_close=on_close)


def main() -> None:
    """Run only the receiver UI; never start IKEMEN or an Android application."""
    root = tk.Tk()
    root.withdraw()
    controller = abrir_janela_controle(root, on_close=root.destroy)
    controller.window.transient("")
    root.mainloop()


if __name__ == "__main__":
    main()
