from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, scrolledtext, ttk

RUN_TIMEOUT_SECONDS = 10
MAX_OUTPUT_CHARS = 200_000
SUPPORTED_LANGUAGES = {"python", "javascript", "java", "c", "cpp"}


class JoJoDebugger:
    """Executor local de código com argv seguro; não é um sandbox de segurança."""

    def __init__(self, parent, theme):
        self.win = tk.Toplevel(parent)
        self.theme = theme
        self.win.title("JOJO-OS // DEBUGGER")
        self.win.geometry("760x520")
        self.win.minsize(620, 420)
        self.win.configure(bg=self.theme.BLACK)

        self.style = ttk.Style()
        self.style.theme_use("clam")
        self.style.configure("TLabel", background=self.theme.BLACK, foreground=self.theme.GOLD)
        self.style.configure("TButton", padding=5)
        self.setup_ui()

    def setup_ui(self):
        frame_top = tk.Frame(self.win, bg=self.theme.BLACK)
        frame_top.pack(pady=10, padx=10, fill="x")

        tk.Label(frame_top, text="CAMINHO DO ARQUIVO:", bg=self.theme.BLACK, fg=self.theme.WHITE).pack(side="left")
        self.entry_path = ttk.Entry(frame_top, width=44)
        self.entry_path.pack(side="left", padx=5, fill="x", expand=True)

        self.lang_var = tk.StringVar(value="python")
        self.combo_lang = ttk.Combobox(
            frame_top,
            textvariable=self.lang_var,
            values=sorted(SUPPORTED_LANGUAGES),
            width=12,
            state="readonly",
        )
        self.combo_lang.pack(side="left", padx=5)
        self.btn_run = ttk.Button(frame_top, text="RUN DEBUG", command=self.run_process)
        self.btn_run.pack(side="left", padx=5)

        tk.Label(
            self.win,
            text="Aviso: executa o arquivo com as permissões da sua conta; não é um sandbox. Rode somente código confiável.",
            bg=self.theme.BLACK,
            fg="#FFB86C",
            wraplength=720,
            justify="left",
        ).pack(fill="x", padx=12, pady=(0, 6))

        self.output_area = scrolledtext.ScrolledText(
            self.win,
            bg="#1A1A1A",
            fg=self.theme.GOLD,
            font=("Courier New", 10),
            wrap=tk.WORD,
        )
        self.output_area.pack(pady=8, padx=10, fill="both", expand=True)

    @staticmethod
    def _run(command, cwd: Path):
        return subprocess.run(
            command,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            errors="replace",
            timeout=RUN_TIMEOUT_SECONDS,
            shell=False,
            check=False,
        )

    def _execute(self, path: Path, language: str) -> str:
        language = language.lower()
        if language not in SUPPORTED_LANGUAGES:
            return "[ERRO] Linguagem não suportada."

        interpreters = {
            "python": sys.executable,
            "javascript": shutil.which("node"),
            "java": shutil.which("java"),
            "c": shutil.which("gcc") or shutil.which("cc"),
            "cpp": shutil.which("g++") or shutil.which("c++"),
        }
        tool = interpreters[language]
        if not tool:
            return f"[ERRO] Interpretador/compilador de {language} não encontrado."

        try:
            if language in {"python", "javascript"}:
                result = self._run([tool, str(path)], path.parent)
            elif language == "java":
                result = self._run([tool, path.name], path.parent)
            else:
                with tempfile.TemporaryDirectory(prefix="jojo_debug_") as temp_dir:
                    executable = Path(temp_dir) / ("program.exe" if os.name == "nt" else "program")
                    compiler = [tool, str(path), "-o", str(executable)]
                    if language == "cpp":
                        compiler.insert(1, "-std=c++17")
                    build = self._run(compiler, path.parent)
                    if build.returncode != 0:
                        return self._format_result(build, "COMPILAÇÃO")
                    result = self._run([str(executable)], path.parent)
            return self._format_result(result, "SAÍDA" if result.returncode == 0 else "ERRO")
        except subprocess.TimeoutExpired:
            return f"[TIMEOUT] O processo excedeu {RUN_TIMEOUT_SECONDS} segundos."
        except OSError as exc:
            return f"[ERRO] Não foi possível iniciar o processo ({type(exc).__name__})."

    @staticmethod
    def _format_result(result, heading: str) -> str:
        output = result.stdout or ""
        if result.stderr:
            output += ("\n" if output else "") + result.stderr
        if not output:
            output = "(sem saída)"
        if len(output) > MAX_OUTPUT_CHARS:
            output = output[:MAX_OUTPUT_CHARS] + "\n[saída truncada]"
        return f"--- {heading} (código {result.returncode}) ---\n{output}"

    def run_process(self):
        raw_path = self.entry_path.get().strip()
        language = self.lang_var.get().strip().lower()
        self.output_area.delete("1.0", tk.END)

        if language not in SUPPORTED_LANGUAGES:
            self.output_area.insert(tk.END, "[ERRO] Selecione uma linguagem suportada.\n")
            return
        if not raw_path:
            self.output_area.insert(tk.END, "[ERRO] Informe o caminho de um arquivo.\n")
            return

        path = Path(raw_path).expanduser().resolve(strict=False)
        if not path.is_file():
            self.output_area.insert(tk.END, f"[ERRO] Arquivo não encontrado: {path}\n")
            return
        if path.stat().st_size > 5_000_000:
            self.output_area.insert(tk.END, "[ERRO] Arquivos acima de 5 MB não são executados.\n")
            return

        if not messagebox.askyesno(
            "Executar código local",
            "Este recurso executa o arquivo com as permissões da sua conta e não consegue isolá-lo. Continue apenas se você confia no código.",
            parent=self.win,
        ):
            return

        self.btn_run.config(state="disabled")
        self.output_area.insert(tk.END, f"[SISTEMA] Executando {path.name} como {language} (máx. {RUN_TIMEOUT_SECONDS}s)...\n")

        def finished(text):
            try:
                if self.win.winfo_exists():
                    self.output_area.insert(tk.END, text + "\n")
                    self.output_area.see(tk.END)
                    self.btn_run.config(state="normal")
            except tk.TclError:
                pass

        # A thread de trabalho não toca nos widgets Tk; apenas devolve texto pela fila.
        import queue
        import threading
        result_queue = queue.Queue(maxsize=1)

        def worker():
            try:
                result_queue.put_nowait(self._execute(path, language))
            except Exception as exc:  # noqa: BLE001 - fronteira de thread: sempre devolve um erro à UI e libera o botão.
                try:
                    result_queue.put_nowait(f"[ERRO] Falha ({type(exc).__name__}).")
                except queue.Full:
                    pass

        poll = {"after_id": None}
        thread = threading.Thread(target=worker, name="jojo-debug-worker", daemon=True)
        thread.start()

        def check_result():
            try:
                text = result_queue.get_nowait()
            except queue.Empty:
                if self.win.winfo_exists():
                    poll["after_id"] = self.win.after(80, check_result)
                return
            finished(text)

        poll["after_id"] = self.win.after(80, check_result)
