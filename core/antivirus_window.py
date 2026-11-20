from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from core.antivirus import (
    EngineInfo,
    ScanResult,
    detect_engine,
    save_scan_result,
    scan_target,
)
from core.database import DatabaseError, list_scan_history


class AntivirusWindow:
    """Interface de varredura local usando o mecanismo antivírus do computador."""

    def __init__(self, master, app):
        self.app = app
        self.theme = app.current_theme
        self.window = tk.Toplevel(master)
        self.window.title("JOJO-OS // SCANNER DE ARQUIVOS")
        self.window.geometry("820x600")
        self.window.minsize(700, 500)
        self.window.configure(bg=self.theme.BLACK)
        self.window.transient(master)
        self.window.protocol("WM_DELETE_WINDOW", self.close)

        self.engine: EngineInfo | None = None
        self.selected_target: Path | None = None
        self.message_queue: queue.Queue = queue.Queue()
        self.cancel_event = threading.Event()
        self.scan_active = False
        self.closed = False

        self.engine_var = tk.StringVar(value="Verificando mecanismos instalados…")
        self.target_var = tk.StringVar(value="Nenhum arquivo ou pasta selecionado")
        self.status_var = tk.StringVar(value="Aguardando diagnóstico do mecanismo local")

        self._build_ui()
        threading.Thread(target=self._probe_engine, name="jojo-av-probe", daemon=True).start()
        self.window.after(100, self._poll_messages)

    def _build_ui(self):
        header = tk.Frame(self.window, bg=self.theme.PURPLE, height=62)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(
            header,
            text="SCANNER DE SEGURANÇA",
            fg=self.theme.GOLD,
            bg=self.theme.PURPLE,
            font=("Impact", 19),
        ).pack(side="left", padx=18, pady=10)
        tk.Label(
            self.window,
            textvariable=self.engine_var,
            fg=self.theme.WHITE,
            bg=self.theme.BLACK,
            font=("Consolas", 10),
            justify="left",
            wraplength=770,
            anchor="w",
        ).pack(fill="x", padx=18, pady=(12, 3))

        controls = tk.Frame(self.window, bg=self.theme.BLACK)
        controls.pack(fill="x", padx=16, pady=(8, 4))
        self._button(controls, "ESCOLHER ARQUIVO", self.choose_file).pack(side="left", padx=(0, 7))
        self._button(controls, "ESCOLHER PASTA", self.choose_folder).pack(side="left", padx=7)
        self.scan_button = self._button(controls, "INICIAR VARREDURA", self.start_scan)
        self.scan_button.pack(side="left", padx=7)
        self.cancel_button = self._button(controls, "CANCELAR", self.cancel_scan)
        self.cancel_button.pack(side="left", padx=7)
        self.cancel_button.configure(state="disabled")

        tk.Label(
            self.window,
            textvariable=self.target_var,
            fg=self.theme.GOLD,
            bg=self.theme.BLACK,
            font=("Consolas", 9),
            justify="left",
            anchor="w",
            wraplength=780,
        ).pack(fill="x", padx=18, pady=(4, 8))

        self.progress = ttk.Progressbar(self.window, mode="indeterminate")
        self.progress.pack(fill="x", padx=18, pady=(0, 8))

        log_frame = tk.Frame(self.window, bg=self.theme.BLACK)
        log_frame.pack(fill="both", expand=True, padx=18, pady=4)
        tk.Label(
            log_frame,
            text="SAÍDA REAL DO MECANISMO",
            fg=self.theme.PINK,
            bg=self.theme.BLACK,
            font=("Impact", 11),
            anchor="w",
        ).pack(fill="x", pady=(0, 4))
        self.log = scrolledtext.ScrolledText(
            log_frame,
            bg="#111111",
            fg=self.theme.GOLD,
            insertbackground=self.theme.GOLD,
            font=("Consolas", 9),
            wrap=tk.WORD,
            height=14,
        )
        self.log.pack(fill="both", expand=True)
        self.log.insert(
            "end",
            "Esta ferramenta executa uma varredura sob demanda com um mecanismo instalado no computador.\n"
            "Ela não instala antivírus, não substitui proteção em tempo real e não apaga nem coloca arquivos em quarentena.\n\n",
        )
        self.log.configure(state="disabled")

        footer = tk.Frame(self.window, bg=self.theme.BLACK)
        footer.pack(fill="x", padx=18, pady=(5, 12))
        tk.Label(
            footer,
            textvariable=self.status_var,
            fg=self.theme.WHITE,
            bg=self.theme.BLACK,
            font=("Consolas", 9),
            anchor="w",
            wraplength=530,
            justify="left",
        ).pack(side="left", fill="x", expand=True)
        self._button(footer, "HISTÓRICO", self.show_history).pack(side="right", padx=(7, 0))
        self._button(footer, "FECHAR", self.close).pack(side="right", padx=7)

    def _button(self, parent, text, command):
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=self.theme.PURPLE,
            fg=self.theme.GOLD,
            activebackground=self.theme.PINK,
            activeforeground=self.theme.BLACK,
            font=("Impact", 9),
            relief="flat",
            padx=9,
            pady=6,
        )

    def _probe_engine(self):
        self.message_queue.put(("engine", detect_engine()))

    def _poll_messages(self):
        if self.closed:
            return
        try:
            while True:
                kind, payload = self.message_queue.get_nowait()
                if kind == "engine":
                    self.engine = payload
                    self.engine_var.set(f"{payload.name}: {payload.detail}")
                    if payload.available:
                        self.status_var.set("Mecanismo disponível. Escolha um arquivo ou uma pasta para verificar.")
                    else:
                        self.status_var.set(payload.detail)
                        self.scan_button.configure(state="disabled")
                elif kind == "line":
                    self._append_log(payload)
                elif kind == "done":
                    result, history_error = payload
                    self._finish_scan(result, history_error)
        except queue.Empty:
            pass
        self.window.after(100, self._poll_messages)

    def _append_log(self, text: str):
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        try:
            line_count = int(self.log.index("end-1c").split(".")[0])
            if line_count > 700:
                self.log.delete("1.0", f"{line_count - 600}.0")
        except (ValueError, tk.TclError):
            pass
        self.log.see("end")
        self.log.configure(state="disabled")

    def choose_file(self):
        target = filedialog.askopenfilename(parent=self.window, title="Escolha um arquivo para verificar")
        if target:
            self._select_target(target)

    def choose_folder(self):
        target = filedialog.askdirectory(parent=self.window, title="Escolha uma pasta para verificar", mustexist=True)
        if target:
            self._select_target(target)

    def _select_target(self, target: str):
        path = Path(target).expanduser()
        try:
            self.selected_target = path.resolve(strict=True)
        except OSError as exc:
            self.selected_target = None
            self.status_var.set(f"O caminho selecionado não está acessível: {exc}")
            return
        self.target_var.set(str(self.selected_target))
        if self.engine and self.engine.available and not self.scan_active:
            self.scan_button.configure(state="normal")
        self.status_var.set("Confira o caminho antes de iniciar; pastas grandes podem levar bastante tempo.")

    def start_scan(self):
        if self.scan_active:
            return
        if not self.engine or not self.engine.available:
            messagebox.showerror("Scanner indisponível", "Nenhum mecanismo de antivírus compatível foi encontrado.", parent=self.window)
            return
        if self.selected_target is None or not self.selected_target.exists():
            messagebox.showinfo("Selecione um destino", "Escolha primeiro um arquivo ou uma pasta.", parent=self.window)
            return
        target_text = str(self.selected_target)
        confirmed = messagebox.askyesno(
            "Confirmar varredura",
            "Executar uma varredura real, somente de leitura, neste destino?\n\n"
            f"{target_text}\n\n"
            "A verificação pode levar bastante tempo. O JoJo-OS não apagará, moverá nem colocará arquivos em quarentena.",
            parent=self.window,
        )
        if not confirmed:
            return

        self.scan_active = True
        self.cancel_event.clear()
        self.scan_button.configure(state="disabled")
        self.cancel_button.configure(state="normal")
        self.progress.start(12)
        self.status_var.set(f"Varredura em andamento com {self.engine.name}…")
        self._append_log(f"\n[INÍCIO] {self.engine.name} // {target_text}")
        threading.Thread(
            target=self._scan_worker,
            args=(self.selected_target, self.engine),
            name="jojo-av-scan",
            daemon=True,
        ).start()

    def _scan_worker(self, target: Path, engine: EngineInfo):
        result = scan_target(
            target,
            engine,
            on_line=lambda line: self.message_queue.put(("line", line)),
            cancel_event=self.cancel_event,
        )
        history_error = ""
        try:
            save_scan_result(result)
        except (DatabaseError, OSError, ValueError) as exc:
            history_error = str(exc)
        self.message_queue.put(("done", (result, history_error)))

    def cancel_scan(self):
        if not self.scan_active:
            return
        self.cancel_event.set()
        self.cancel_button.configure(state="disabled")
        self.status_var.set(
            "Encerrando o processo do scanner… No Microsoft Defender, o serviço pode concluir algo em segundo plano."
        )

    def _finish_scan(self, result: ScanResult, history_error: str):
        self.scan_active = False
        self.progress.stop()
        self.cancel_button.configure(state="disabled")
        if self.selected_target is not None and self.engine and self.engine.available:
            self.scan_button.configure(state="normal")
        verdict_labels = {
            "clean": "SEM DETECÇÕES RELATADAS",
            "detections": "DETECÇÃO RELATADA — REVISÃO NECESSÁRIA",
            "inconclusive": "RESULTADO INCONCLUSIVO",
            "error": "ERRO DE VARREDURA",
            "cancelled": "VARREDURA INTERROMPIDA",
        }
        self.status_var.set(f"{verdict_labels.get(result.verdict, result.verdict)} // {result.summary}")
        self._append_log(f"[FIM] {result.summary}")
        self._append_log(f"[RESULTADO LOCAL] {result.verdict} | detecções contabilizadas: {result.detections} | código: {result.exit_code}")
        if history_error:
            self._append_log(f"[HISTÓRICO] Não foi possível salvar: {history_error}")

    def show_history(self):
        try:
            entries = list_scan_history(50)
        except DatabaseError as exc:
            messagebox.showerror("Histórico", f"Não foi possível ler o histórico SQLite: {exc}", parent=self.window)
            return

        history = tk.Toplevel(self.window)
        history.title("JOJO-OS // HISTÓRICO DE VARREDURAS")
        history.geometry("760x460")
        history.configure(bg=self.theme.BLACK)
        history.transient(self.window)
        output = scrolledtext.ScrolledText(
            history,
            bg="#111111",
            fg=self.theme.GOLD,
            insertbackground=self.theme.GOLD,
            font=("Consolas", 9),
            wrap=tk.WORD,
        )
        output.pack(fill="both", expand=True, padx=12, pady=12)
        if not entries:
            output.insert("end", "Nenhuma varredura foi registrada neste banco.\n")
        for item in entries:
            output.insert(
                "end",
                f"#{item['id']} | {item['verdict'].upper()} | {item['engine']} | "
                f"detecções: {item['detections']} | {item['finished_at']}\n"
                f"Destino: {item['target']}\n{item['summary']}\n\n",
            )
        output.configure(state="disabled")
        controls = tk.Frame(history, bg=self.theme.BLACK)
        controls.pack(fill="x", padx=12, pady=(0, 12))
        self._button(controls, "LIMPAR HISTÓRICO", lambda: self.clear_history(history)).pack(side="left")
        self._button(controls, "FECHAR", history.destroy).pack(side="right")

    def clear_history(self, parent):
        if not messagebox.askyesno(
            "Limpar histórico",
            "Apagar somente o histórico local de varreduras do banco SQLite?",
            parent=parent,
        ):
            return
        from core.database import clear_scan_history

        try:
            clear_scan_history()
        except DatabaseError as exc:
            messagebox.showerror("Histórico", f"Não foi possível apagar o histórico: {exc}", parent=parent)
            return
        parent.destroy()
        self.status_var.set("Histórico local apagado.")

    def close(self):
        if self.closed:
            return
        if self.scan_active:
            confirmed = messagebox.askyesno(
                "Varredura em andamento",
                "Encerrar a chamada do scanner e fechar esta janela? No Microsoft Defender, o serviço pode continuar trabalhando em segundo plano.",
                parent=self.window,
            )
            if not confirmed:
                return
            self.cancel_event.set()
        self.closed = True
        try:
            self.window.destroy()
        except tk.TclError:
            pass

    def is_open(self) -> bool:
        return not self.closed and bool(self.window.winfo_exists())
