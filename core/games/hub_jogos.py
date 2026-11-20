from __future__ import annotations

import json
import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from core.games.android_data_package import copy_android_character_data_pack
from core.games.character_downloader import (
    character_catalog,
    get_character_source,
    install_all_characters,
    install_selected_character,
)
from core.games.jojo_launcher import (
    download_android_ikemen,
    lancar_jojo_ikemen,
    prepare_jojo_ikemen,
)


class HubJogosApp:
    def __init__(self, master: tk.Toplevel):
        self.master = master
        self.master.title("JoJo-OS — IKEMEN GO")
        self.master.geometry("1180x820")
        self.master.minsize(760, 680)
        self.master.config(bg="#1e102b")
        self.master.resizable(True, True)
        self.master.protocol("WM_DELETE_WINDOW", self.fechar)

        self._events: queue.Queue[tuple] = queue.Queue()
        self._installing = False
        self._closed = False
        self._poll_id: str | None = None
        self._anime_buttons: list[tk.Button] = []
        self._controller_window = None
        self._character_options = {source.label: source.character_id for source in character_catalog()}
        self.character_var = tk.StringVar(master=self.master)
        self._fullscreen = False
        self.master.bind("<F11>", self.alternar_tela_cheia)
        self.master.bind("<Escape>", self.sair_tela_cheia)

        self.centralizar_janela()
        self._build_ui()
        self.master.after_idle(self._entrar_tela_cheia)

    def _build_ui(self) -> None:
        tk.Label(
            self.master,
            text="JOJO-OS // GAME CENTER",
            font=("Arial", 23, "bold"),
            bg="#1e102b",
            fg="#ffcc00",
        ).pack(pady=(20, 5))
        tk.Label(
            self.master,
            text="JOGO PRINCIPAL: IKEMEN GO — compatível com recursos M.U.G.E.N.",
            font=("Arial", 11),
            bg="#1e102b",
            fg="#d9c6e8",
        ).pack(pady=(0, 15))

        card = tk.Frame(self.master, bg="#30203d", bd=2, relief="groove")
        card.pack(padx=26, pady=8, fill="x")
        tk.Label(
            card,
            text="IKEMEN GO — MOTOR DO JOGO",
            font=("Arial", 16, "bold"),
            bg="#30203d",
            fg="#ffffff",
        ).pack(anchor="w", padx=18, pady=(16, 5))
        tk.Label(
            card,
            text=(
                "Um clique baixa e valida o motor oficial do IKEMEN GO se estiver faltando e abre o jogo. "
                "Na primeira instalação do motor, o download tem aproximadamente 54 MiB."
            ),
            font=("Arial", 10),
            bg="#30203d",
            fg="#ded6e3",
            justify="left",
            wraplength=680,
        ).pack(anchor="w", padx=18, pady=(0, 10))
        tk.Label(
            card,
            text=(
                "Este botão instala/abre somente o motor. A configuração de Steel Ball Run é separada, no botão "
                "INSTALAR SBR logo abaixo."
            ),
            font=("Arial", 10, "bold"),
            bg="#30203d",
            fg="#ffcc00",
            justify="left",
            wraplength=680,
        ).pack(anchor="w", padx=18, pady=(0, 14))
        tk.Label(
            card,
            text=(
                "Android: baixa o APK oficial ARM64 e prepara, ao lado, um ZIP separado com 44 personagens já disponíveis. "
                "O APK fica intacto; no celular, abra-o uma vez, escolha a pasta do jogo e depois mescle o ZIP nessa pasta."
            ),
            font=("Arial", 9),
            bg="#30203d",
            fg="#d9c6e8",
            justify="left",
            wraplength=900,
        ).pack(anchor="w", padx=18, pady=(0, 10))

        buttons = tk.Frame(card, bg="#30203d")
        buttons.pack(fill="x", padx=18, pady=(0, 16))
        self.btn_jogar = tk.Button(
            buttons,
            text="INSTALAR IKEMEN GO",
            font=("Arial", 11, "bold"),
            bg="#00aa55",
            fg="#ffffff",
            activebackground="#008844",
            activeforeground="#ffffff",
            bd=0,
            padx=15,
            pady=9,
            cursor="hand2",
            command=self.jogar,
        )
        self.btn_jogar.pack(side="left", padx=(0, 8))
        self.btn_android = tk.Button(
            buttons,
            text="BAIXAR APK + PACOTE DE DADOS",
            font=("Arial", 11, "bold"),
            bg="#644080",
            fg="#ffffff",
            activebackground="#764da0",
            activeforeground="#ffffff",
            bd=0,
            padx=15,
            pady=9,
            cursor="hand2",
            command=self.baixar_android,
        )
        self.btn_android.pack(side="left")
        self.btn_controller = tk.Button(
            buttons,
            text="CONTROLE PELO CELULAR",
            font=("Arial", 9, "bold"),
            bg="#226f68",
            fg="#ffffff",
            activebackground="#2b897f",
            activeforeground="#ffffff",
            bd=0,
            padx=10,
            pady=6,
            cursor="hand2",
            command=self.abrir_controle_celular,
        )
        self.btn_controller.pack(side="left", padx=(8, 0))

        sbr_card = tk.Frame(self.master, bg="#30203d", bd=2, relief="groove")
        sbr_card.pack(padx=26, pady=8, fill="x")
        tk.Label(
            sbr_card,
            text="STEEL BALL RUN",
            font=("Arial", 15, "bold"),
            bg="#30203d",
            fg="#ffffff",
        ).pack(anchor="w", padx=18, pady=(12, 4))
        tk.Label(
            sbr_card,
            text=(
                "Este botão instala os pacotes reais de Diego Brando e Funny Valentine incluídos no projeto, "
                "prepara as pastas SBR e registra os .def/.sff. Johnny Joestar e Gyro Zeppeli seguem pendentes "
                "até haver arquivos reais; o app não inventa personagens."
            ),
            font=("Arial", 10),
            bg="#30203d",
            fg="#ded6e3",
            justify="left",
            wraplength=1000,
        ).pack(anchor="w", padx=18, pady=(0, 8))
        self.btn_sbr = tk.Button(
            sbr_card,
            text="INSTALAR SBR",
            font=("Arial", 11, "bold"),
            bg="#00aa55",
            fg="#ffffff",
            activebackground="#008844",
            activeforeground="#ffffff",
            bd=0,
            padx=15,
            pady=9,
            cursor="hand2",
            command=self.instalar_sbr,
        )
        self.btn_sbr.pack(fill="x", padx=18, pady=(0, 12))

        character_card = tk.Frame(self.master, bg="#30203d", bd=2, relief="groove")
        character_card.pack(padx=26, pady=8, fill="x", before=sbr_card)
        tk.Label(
            character_card,
            text="ESCOLHA UM PERSONAGEM",
            font=("Arial", 15, "bold"),
            bg="#30203d",
            fg="#ffffff",
        ).pack(anchor="w", padx=18, pady=(12, 4))
        tk.Label(
            character_card,
            text=(
                "Selecione e clique no botão: o JoJo-OS prepara o motor se faltar, baixa ou instala "
                "automaticamente só o personagem escolhido, valida os arquivos e configura data/select.def."
            ),
            font=("Arial", 10),
            bg="#30203d",
            fg="#ded6e3",
            justify="left",
            wraplength=1000,
        ).pack(anchor="w", padx=18, pady=(0, 8))
        selection_row = tk.Frame(character_card, bg="#30203d")
        selection_row.pack(fill="x", padx=18, pady=(0, 12))
        choices = list(self._character_options)
        self.character_select = ttk.Combobox(
            selection_row,
            textvariable=self.character_var,
            values=choices,
            state="readonly",
            font=("Arial", 11),
        )
        self.character_select.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.character_select.bind("<<ComboboxSelected>>", self._atualizar_acao_personagem)
        self.btn_download_personagem = tk.Button(
            selection_row,
            text="BAIXAR E INSTALAR",
            font=("Arial", 11, "bold"),
            bg="#644080",
            fg="#ffffff",
            activebackground="#764da0",
            activeforeground="#ffffff",
            bd=0,
            padx=18,
            pady=10,
            cursor="hand2",
            command=self._instalar_personagem_selecionado,
        )
        self.btn_download_personagem.pack(side="right")
        self.btn_download_all = tk.Button(
            selection_row,
            text="BAIXAR TUDO",
            font=("Arial", 11, "bold"),
            bg="#9a3b54",
            fg="#ffffff",
            activebackground="#b64b67",
            activeforeground="#ffffff",
            bd=0,
            padx=18,
            pady=10,
            cursor="hand2",
            command=self.baixar_tudo,
        )
        self.btn_download_all.pack(side="right", padx=(0, 8))
        if choices:
            self.character_var.set(choices[0])
        self._anime_buttons = [self.btn_download_personagem, self.btn_download_all]
        self._atualizar_acao_personagem()

        self.status_var = tk.StringVar(value="Status: pronto")
        tk.Label(
            self.master,
            textvariable=self.status_var,
            font=("Arial", 10, "italic"),
            bg="#1e102b",
            fg="#c8bad4",
            wraplength=700,
            justify="left",
        ).pack(fill="x", padx=30, pady=(12, 3))
        self.progress = ttk.Progressbar(self.master, mode="determinate", maximum=100)
        self.progress.pack(fill="x", padx=30, pady=(0, 10))
        tk.Label(
            self.master,
            text=(
                "Tela cheia: F11 alterna e Esc sai. O motor também grava Fullscreen=1 no config.ini oficial. "
                "Fontes e créditos: ANIME_ASSET_SOURCES.md."
            ),
            font=("Arial", 9),
            bg="#1e102b",
            fg="#8f819a",
            wraplength=700,
            justify="center",
        ).pack(side="bottom", fill="x", padx=24, pady=16)

    def centralizar_janela(self) -> None:
        self.master.update_idletasks()
        width = min(1180, max(760, self.master.winfo_screenwidth() - 40))
        height = min(820, max(680, self.master.winfo_screenheight() - 80))
        x = (self.master.winfo_screenwidth() // 2) - (width // 2)
        y = (self.master.winfo_screenheight() // 2) - (height // 2)
        self.master.geometry(f"{width}x{height}+{x}+{y}")

    def abrir_controle_celular(self) -> None:
        if self._closed:
            return
        if self._controller_window is not None:
            self._controller_window.show()
            return
        from core.games.controller_window import abrir_janela_controle

        self._controller_window = abrir_janela_controle(
            self.master,
            on_close=lambda: setattr(self, "_controller_window", None),
        )

    def _entrar_tela_cheia(self) -> None:
        if self._closed:
            return
        try:
            self.master.attributes("-fullscreen", True)
            self.master.update_idletasks()
            if not self.master.attributes("-fullscreen"):
                width = self.master.winfo_screenwidth()
                height = self.master.winfo_screenheight()
                self.master.geometry(f"{width}x{height}+0+0")
        except tk.TclError:
            self.master.state("zoomed")
        self._fullscreen = True

    def alternar_tela_cheia(self, _event=None):
        if self._fullscreen:
            self.sair_tela_cheia()
        else:
            self._entrar_tela_cheia()
        return "break"

    def sair_tela_cheia(self, _event=None):
        if self._fullscreen:
            self.master.attributes("-fullscreen", False)
            self._fullscreen = False
            self.master.state("normal")
            self.centralizar_janela()
        return "break"

    def _atualizar_acao_personagem(self, _event=None) -> None:
        character_id = self._character_options.get(self.character_var.get())
        if not character_id:
            self.btn_download_personagem.configure(text="ESCOLHA UM PERSONAGEM", state=tk.DISABLED)
            return
        source = get_character_source(character_id)
        action = "INSTALAR" if source.kind == "bundled" else "BAIXAR E INSTALAR"
        character_name = source.label.split(" — ")[-1].split(" (")[0]
        self.btn_download_personagem.configure(text=f"{action}: {character_name}", state=tk.NORMAL)

    def _instalar_personagem_selecionado(self) -> None:
        character_id = self._character_options.get(self.character_var.get())
        if character_id:
            self.baixar_personagem(character_id)

    def jogar(self) -> None:
        if self._installing or self._closed:
            return
        self._installing = True
        self._set_controls_busy(True)
        self.progress.configure(value=0)
        self.status_var.set("Status: verificando o IKEMEN GO e consultando a release oficial, se necessário...")

        def report(message: str, current: int, total: int) -> None:
            self._events.put(("progress", message, current, total))

        def worker() -> None:
            try:
                result = prepare_jojo_ikemen(progress=report)
            except Exception as exc:  # noqa: BLE001 - traduz falhas de rede/arquivo para a UI.
                self._events.put(("error", f"{type(exc).__name__}: {exc}"))
            else:
                self._events.put(("ready", result))

        threading.Thread(target=worker, name="jojo-ikemen-setup", daemon=True).start()
        self._poll_id = self.master.after(100, self._process_events)

    def _process_events(self) -> None:
        if self._closed:
            return
        try:
            while True:
                event = self._events.get_nowait()
                if event[0] == "progress":
                    _, message, current, total = event
                    self.status_var.set("Status: " + message)
                    if total > 0:
                        self.progress.configure(value=min(100, current * 100 / total))
                elif event[0] == "error":
                    self._finish_install()
                    self.progress.configure(value=0)
                    self.status_var.set("Status: falha ao preparar o IKEMEN GO")
                    messagebox.showerror(
                        "IKEMEN GO",
                        "Não consegui baixar ou preparar o jogo. Confira a internet e tente novamente.\n\n"
                        + str(event[1]),
                        parent=self.master,
                    )
                elif event[0] == "ready":
                    result = event[1]
                    self._finish_install()
                    self.progress.configure(value=100)
                    if result.downloaded:
                        self.status_var.set(f"Status: IKEMEN GO {result.version} instalado; abrindo o jogo...")
                    else:
                        self.status_var.set("Status: IKEMEN GO encontrado; abrindo o jogo...")
                    success, message = lancar_jojo_ikemen(result.game_dir)
                    if success:
                        self.status_var.set("Status: IKEMEN GO iniciado; o setup SBR é feito pelo botão separado.")
                    else:
                        messagebox.showerror("IKEMEN GO", message, parent=self.master)
                        self.status_var.set("Status: o motor foi preparado, mas não abriu")
                elif event[0] == "android_error":
                    self._finish_install()
                    self.progress.configure(value=0)
                    self.status_var.set("Status: não foi possível baixar o APK Android")
                    messagebox.showerror("IKEMEN GO Android", str(event[1]), parent=self.master)
                elif event[0] == "android_ready":
                    self._finish_install()
                    self.progress.configure(value=100)
                    apk_path, data_pack_path = event[1], event[2]
                    self.status_var.set("Status: APK oficial e pacote de dados Android prontos")
                    messagebox.showinfo(
                        "IKEMEN GO Android — APK + dados",
                        "APK oficial verificado e salvo em:\n"
                        + str(apk_path)
                        + "\n\nPacote de dados separado:\n"
                        + str(data_pack_path)
                        + "\n\nNo celular: instale o APK; abra-o uma vez e escolha uma pasta pública para o jogo; feche o app; "
                        "extraia o conteúdo do ZIP diretamente nessa mesma pasta, mesclando chars e substituindo data/select.def; "
                        "depois abra o jogo novamente. Requer Android 13+ e ARM64. O JoJo-OS não instala nem grava no telefone.\n\n"
                        "O pacote tem 44 personagens reais já disponíveis (41 JoJo, Naruto, Yuji e Zoro); não são 60 e "
                        "não inclui personagens de Dragon Ball Z. O teste em aparelho físico ainda está pendente.",
                        parent=self.master,
                    )
                elif event[0] == "android_data_error":
                    self._finish_install()
                    self.progress.configure(value=0)
                    apk_path, error = event[1], event[2]
                    self.status_var.set("Status: APK pronto, mas o pacote de dados não foi copiado")
                    messagebox.showerror(
                        "Pacote de dados Android",
                        "O APK oficial foi baixado e verificado em:\n"
                        + str(apk_path)
                        + "\n\nNão copiei o pacote de personagens porque a validação falhou:\n"
                        + str(error),
                        parent=self.master,
                    )
                elif event[0] == "batch_error":
                    self._finish_install()
                    self.progress.configure(value=0)
                    self.status_var.set("Status: não foi possível preparar o IKEMEN para o lote")
                    messagebox.showerror("Baixar tudo", str(event[1]), parent=self.master)
                elif event[0] == "batch_ready":
                    result = event[1]
                    self._finish_install()
                    self.progress.configure(value=100)
                    self.status_var.set(
                        f"Status: {len(result.completed)}/{result.total} personagens prontos; "
                        f"{len(result.failures)} falharam."
                    )
                    summary = f"Prontos: {len(result.completed)} de {result.total}."
                    if result.failures:
                        details = "\n".join(f"• {failure.label}: {failure.error}" for failure in result.failures[:8])
                        if len(result.failures) > 8:
                            details += f"\n… e mais {len(result.failures) - 8} falha(s)."
                        messagebox.showwarning(
                            "Baixar tudo — resultado parcial",
                            summary + "\n\nFalhas (os demais foram mantidos):\n" + details
                            + "\n\nCorrija a conexão/limite da fonte e clique BAIXAR TUDO novamente; "
                            "os que já estiverem prontos não serão baixados outra vez.",
                            parent=self.master,
                        )
                    else:
                        messagebox.showinfo(
                            "Baixar tudo — concluído",
                            summary + "\nTodos os personagens foram instalados e registrados em data/select.def.",
                            parent=self.master,
                        )
                elif event[0] == "character_error":
                    self._finish_install()
                    self.progress.configure(value=0)
                    self.status_var.set("Status: não foi possível preparar o personagem")
                    messagebox.showerror("Instalar personagem", str(event[1]), parent=self.master)
                elif event[0] == "character_ready":
                    result, label = event[1], event[2]
                    self._finish_install()
                    self.progress.configure(value=100)
                    self.status_var.set(f"Status: {label} instalado e configurado; pronto para jogar.")
                    messagebox.showinfo(
                        "Personagem pronto",
                        f"{label} foi instalado em chars/ e registrado em data/select.def.\n\n"
                        "Agora clique em INSTALAR IKEMEN GO para abrir o jogo em tela cheia.",
                        parent=self.master,
                    )
                elif event[0] == "sbr_ready":
                    result = event[1]
                    self._finish_install()
                    self.progress.configure(value=100)
                    registered = result.setup_result.registered
                    waiting = result.setup_result.waiting_for_assets
                    if waiting:
                        waiting_text = ", ".join(waiting)
                        registered_text = ", ".join(registered) if registered else "nenhum ainda"
                        self.status_var.set(
                            f"Status: SBR configurado; instalados: {registered_text}; faltam: {waiting_text}."
                        )
                        message = (
                            "Os pacotes SBR disponíveis no JoJo-OS foram instalados e registrados: "
                            + registered_text + ".\n\nAinda faltam arquivos .def/.sff reais para: "
                            + waiting_text + ". Não criei personagens falsos."
                        )
                    else:
                        registered_text = ", ".join(registered)
                        self.status_var.set(f"Status: SBR instalado e configurado: {registered_text}.")
                        message = "Personagens SBR reais encontrados e registrados em data/select.def:\n" + registered_text
                    messagebox.showinfo("Instalar SBR", message, parent=self.master)
        except queue.Empty:
            pass
        if self._installing and not self._closed:
            self._poll_id = self.master.after(100, self._process_events)

    def _set_controls_busy(self, busy: bool) -> None:
        state = tk.DISABLED if busy else tk.NORMAL
        try:
            for button in (self.btn_jogar, self.btn_android, self.btn_sbr, *self._anime_buttons):
                button.configure(state=state)
            self.character_select.configure(state=tk.DISABLED if busy else "readonly")
        except tk.TclError:
            pass

    def _finish_install(self) -> None:
        self._installing = False
        self._set_controls_busy(False)
        self._atualizar_acao_personagem()

    def baixar_personagem(self, character_id: str) -> None:
        if self._installing or self._closed:
            return
        source = get_character_source(character_id)
        self._installing = True
        self._set_controls_busy(True)
        self.progress.configure(value=0)
        label = source.label
        action = "instalando o pacote local" if source.kind == "bundled" else "baixando e instalando"
        self.status_var.set(f"Status: preparando o IKEMEN GO e {action} {label}...")

        def report(message: str, current: int, total: int) -> None:
            self._events.put(("progress", message, current, total))

        def worker() -> None:
            try:
                engine = prepare_jojo_ikemen(progress=report)
                result = install_selected_character(engine.game_dir, character_id, progress=report)
            except Exception as exc:  # noqa: BLE001 - mostra falhas de rede/arquivo na interface.
                self._events.put(("character_error", f"{type(exc).__name__}: {exc}"))
            else:
                self._events.put(("character_ready", result, label))

        threading.Thread(target=worker, name="jojo-character-install", daemon=True).start()
        self._poll_id = self.master.after(100, self._process_events)

    def baixar_tudo(self) -> None:
        if self._installing or self._closed:
            return
        sources = character_catalog()
        local_count = sum(source.kind == "bundled" for source in sources)
        remote_count = len(sources) - local_count
        if not messagebox.askyesno(
            "Baixar e instalar todos",
            f"O JoJo-OS vai preparar o IKEMEN e instalar os {len(sources)} personagens do catálogo "
            f"({local_count} pacotes locais e {remote_count} downloads remotos). O pacote de Luffy pode ter "
            "cerca de 455 MB. A instalação será sequencial; se uma fonte falhar, as outras continuam e "
            "você verá um resumo. Continuar?",
            parent=self.master,
        ):
            return

        self._installing = True
        self._set_controls_busy(True)
        self.progress.configure(value=0)
        self.status_var.set("Status: preparando o IKEMEN e instalando o catálogo em sequência...")

        def report(message: str, current: int, total: int) -> None:
            self._events.put(("progress", message, current, total))

        def worker() -> None:
            try:
                engine = prepare_jojo_ikemen(progress=report)
                result = install_all_characters(engine.game_dir, progress=report)
            except Exception as exc:  # noqa: BLE001 - report setup failures while keeping the UI responsive.
                self._events.put(("batch_error", f"{type(exc).__name__}: {exc}"))
            else:
                self._events.put(("batch_ready", result))

        threading.Thread(target=worker, name="jojo-install-all-characters", daemon=True).start()
        self._poll_id = self.master.after(100, self._process_events)

    def baixar_android(self) -> None:
        if self._installing or self._closed:
            return
        self._installing = True
        self._set_controls_busy(True)
        self.progress.configure(value=0)
        self.status_var.set("Status: baixando o APK oficial e preparando o pacote de dados Android...")

        def report(message: str, current: int, total: int) -> None:
            self._events.put(("progress", message, current, total))

        def worker() -> None:
            try:
                apk_path = download_android_ikemen(progress=report)
            except Exception as exc:  # noqa: BLE001 - present network/archive failures in the hub.
                self._events.put(("android_error", f"{type(exc).__name__}: {exc}"))
                return
            try:
                metadata_path = apk_path.parent / "download-info.json"
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                version = metadata.get("version") if isinstance(metadata, dict) else None
                if not isinstance(version, str):
                    raise TypeError("Não consegui confirmar a versão do APK Android baixado.")
                data_pack_path = copy_android_character_data_pack(
                    apk_path.parent,
                    progress=report,
                    expected_engine_version=version,
                )
            except Exception as exc:  # noqa: BLE001 - o APK permanece pronto mesmo se os dados falharem.
                self._events.put(("android_data_error", apk_path, f"{type(exc).__name__}: {exc}"))
            else:
                self._events.put(("android_ready", apk_path, data_pack_path))

        threading.Thread(target=worker, name="jojo-download-android-apk", daemon=True).start()
        self._poll_id = self.master.after(100, self._process_events)

    def instalar_sbr(self) -> None:
        if self._installing or self._closed:
            return
        self._installing = True
        self._set_controls_busy(True)
        self.progress.configure(value=0)
        self.status_var.set("Status: instalando o setup SBR e verificando personagens reais...")

        def report(message: str, current: int, total: int) -> None:
            self._events.put(("progress", message, current, total))

        def worker() -> None:
            try:
                result = prepare_jojo_ikemen(progress=report, setup_sbr=True)
                if result.setup_result is None:
                    raise RuntimeError("O launcher não retornou o resultado da configuração SBR.")
            except Exception as exc:  # noqa: BLE001 - traduz falhas de rede/arquivo para a UI.
                self._events.put(("error", f"{type(exc).__name__}: {exc}"))
            else:
                self._events.put(("sbr_ready", result))

        threading.Thread(target=worker, name="jojo-sbr-setup", daemon=True).start()
        self._poll_id = self.master.after(100, self._process_events)

    def fechar(self) -> None:
        self._closed = True
        if self._controller_window is not None:
            self._controller_window.close()
        if self._poll_id is not None:
            try:
                self.master.after_cancel(self._poll_id)
            except tk.TclError:
                pass
        self.master.destroy()


def abrir_hub_jogos(master: tk.Misc | None = None) -> tk.Toplevel:
    """Open the IKEMEN GO hub as a child of JoJo-OS (or standalone for testing)."""
    janela_hub = tk.Toplevel(master) if master is not None else tk.Toplevel()
    HubJogosApp(janela_hub)
    return janela_hub


if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()
    janela = tk.Toplevel(root)
    HubJogosApp(janela)
    root.mainloop()
