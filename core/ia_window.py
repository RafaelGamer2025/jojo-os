from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import scrolledtext

from core.ia import perguntar_ia
from core.tts import SpeechWorker, selecionar_provedor_fala
from ui.themes.jojo_theme import JoJoTheme

MAX_PROMPT_CHARS = 4000


def abrir_janela_ia(app):
    janela_ia = tk.Toplevel(app.root)
    janela_ia.title("JOJO-OS // HEAVEN'S DOOR AI")
    janela_ia.geometry("700x600")
    janela_ia.minsize(520, 420)
    janela_ia.configure(bg=JoJoTheme.BLACK)
    janela_ia.transient(app.root)

    def executar_comando(texto):
        texto_lower = texto.lower()
        if "calculadora" in texto_lower or "calc" in texto_lower:
            app.open_calc()
            return "Abrindo calculadora..."
        if any(palavra in texto_lower for palavra in ("batalha", "battle", "lutar", "fight", "duel", "atacar")):
            app.open_battle()
            return "Preparando a batalha..."
        if "debugger" in texto_lower:
            app.open_debugger()
            return "Abrindo debugger..."
        return None

    tk.Label(
        janela_ia,
        text="📖 HEAVEN'S DOOR",
        font=("Impact", 24),
        bg=JoJoTheme.BLACK,
        fg=JoJoTheme.GOLD,
    ).pack(pady=10)

    chat_box = scrolledtext.ScrolledText(
        janela_ia,
        bg="#1A1A1A",
        fg=JoJoTheme.WHITE,
        font=("Courier New", 12),
        wrap=tk.WORD,
        insertbackground=JoJoTheme.GOLD,
    )
    chat_box.pack(padx=20, pady=10, fill="both", expand=True)
    chat_box.config(state=tk.DISABLED)

    entrada_usuario = tk.Entry(
        janela_ia,
        bg="#2A2A2A",
        fg=JoJoTheme.PINK,
        font=("Impact", 14),
        insertbackground=JoJoTheme.GOLD,
        bd=3,
        relief="sunken",
    )
    entrada_usuario.pack(padx=20, pady=10, fill="x")

    status_label = tk.Label(
        janela_ia,
        text="IA online opcional — configure GROQ_API_KEY no .env",
        bg=JoJoTheme.BLACK,
        fg="#999999",
        font=("Arial", 9),
    )
    status_label.pack(pady=(0, 4))

    voice_enabled = tk.BooleanVar(master=janela_ia, value=False)
    voice_event_queue: queue.Queue[tuple[str, str]] = queue.Queue()
    last_response = ""

    def report_voice_event(event, message):
        try:
            voice_event_queue.put_nowait((event, message))
        except queue.Full:
            pass

    voice_provider = selecionar_provedor_fala()
    voice_worker = SpeechWorker(on_event=report_voice_event, provider=voice_provider)

    voice_frame = tk.Frame(janela_ia, bg=JoJoTheme.BLACK)
    voice_frame.pack(padx=20, pady=(0, 8), fill="x")
    voice_toggle = tk.Checkbutton(
        voice_frame,
        text="FALA: FISH AUDIO (DIO)" if voice_provider == "fish" else "FALA: VOZ LOCAL",
        variable=voice_enabled,
        command=lambda: alternar_fala(),
        bg=JoJoTheme.BLACK,
        fg=JoJoTheme.WHITE,
        activebackground=JoJoTheme.BLACK,
        activeforeground=JoJoTheme.GOLD,
        selectcolor="#2A2A2A",
        font=("Arial", 9, "bold"),
    )
    voice_toggle.pack(side="left")
    listen_button = tk.Button(
        voice_frame,
        text="OUVIR ÚLTIMA RESPOSTA",
        command=lambda: ouvir_ultima_resposta(),
        bg=JoJoTheme.PURPLE,
        fg=JoJoTheme.GOLD,
        activebackground=JoJoTheme.PINK,
        activeforeground=JoJoTheme.WHITE,
        font=("Arial", 8, "bold"),
        state=tk.DISABLED,
    )
    listen_button.pack(side="left", padx=(8, 4))
    stop_button = tk.Button(
        voice_frame,
        text="PARAR FALA",
        command=lambda: parar_fala(),
        bg="#4A1F2D",
        fg=JoJoTheme.WHITE,
        activebackground=JoJoTheme.PINK,
        activeforeground=JoJoTheme.WHITE,
        font=("Arial", 8, "bold"),
    )
    stop_button.pack(side="left")
    voice_status_label = tk.Label(
        janela_ia,
        text=(
            "Fish Audio online: ao ativar, o texto da resposta será enviado para gerar o áudio."
            if voice_provider == "fish"
            else "Voz do sistema local. Configure a chave Fish Audio no .env para usar a voz online."
        ),
        bg=JoJoTheme.BLACK,
        fg="#999999",
        font=("Arial", 8),
    )
    voice_status_label.pack(pady=(0, 4))

    result_queue: queue.Queue[str] = queue.Queue(maxsize=1)
    send_button = tk.Button(
        janela_ia,
        text="WRYYYYYYY! (ENVIAR)",
        bg=JoJoTheme.PURPLE,
        fg=JoJoTheme.GOLD,
        font=("Impact", 14, "bold"),
        activebackground=JoJoTheme.PINK,
        activeforeground=JoJoTheme.WHITE,
    )
    send_button.pack(pady=15)

    def append_message(text, tag):
        chat_box.config(state=tk.NORMAL)
        chat_box.insert(tk.END, text + "\n\n", tag)
        chat_box.tag_config("user", foreground=JoJoTheme.PINK)
        chat_box.tag_config("ai", foreground=JoJoTheme.GOLD)
        chat_box.tag_config("error", foreground="#FF6B6B")
        chat_box.config(state=tk.DISABLED)
        chat_box.see(tk.END)

    def alternar_fala():
        if voice_enabled.get():
            if voice_provider == "fish":
                status_text = "Fish Audio ativado: o texto das respostas será enviado ao serviço online."
            else:
                status_text = "Voz local ativada — respostas novas serão lidas neste dispositivo."
            voice_status_label.config(
                text=status_text,
                fg=JoJoTheme.GOLD,
            )
        else:
            voice_worker.stop()
            voice_status_label.config(
                text="Fala desativada.",
                fg="#999999",
            )

    def parar_fala():
        voice_worker.stop()
        status_text = (
            "Interrompendo; se a API já estiver gerando, o áudio não será reproduzido."
            if voice_provider == "fish"
            else "Fala local parada."
        )
        voice_status_label.config(text=status_text, fg="#999999")

    def solicitar_fala(text):
        if not voice_enabled.get() or not text:
            return
        try:
            voice_worker.enqueue(text)
        except Exception as exc:  # noqa: BLE001 - erro de driver não pode derrubar a UI.
            try:
                voice_event_queue.put_nowait(("error", str(exc)))
            except queue.Full:
                pass

    def ouvir_ultima_resposta():
        if not voice_enabled.get():
            voice_status_label.config(
                text="Ative FALA DA IA para ouvir a última resposta.",
                fg="#FFCC66",
            )
            return
        if not last_response:
            voice_status_label.config(
                text="Ainda não há uma resposta para ouvir.",
                fg="#FFCC66",
            )
            return
        solicitar_fala(last_response)

    def poll_voice_events():
        try:
            if not janela_ia.winfo_exists():
                return
            while True:
                event, message = voice_event_queue.get_nowait()
                if event == "started":
                    status_text = (
                        "Gerando fala com Fish Audio..."
                        if voice_provider == "fish"
                        else "Falando resposta localmente..."
                    )
                    voice_status_label.config(text=status_text, fg=JoJoTheme.GOLD)
                elif event == "done":
                    voice_status_label.config(text="Fala concluída.", fg="#999999")
                elif event == "stopped":
                    voice_status_label.config(text="Fala parada.", fg="#999999")
                elif event == "error":
                    voice_status_label.config(text=f"⚠️ {message}", fg="#FF6B6B")
        except queue.Empty:
            pass
        except tk.TclError:
            return
        try:
            janela_ia.after(100, poll_voice_events)
        except tk.TclError:
            return

    def poll_result(placeholder_index):
        nonlocal last_response
        try:
            if not janela_ia.winfo_exists():
                return
            result = result_queue.get_nowait()
        except queue.Empty:
            try:
                janela_ia.after(100, lambda: poll_result(placeholder_index))
            except tk.TclError:
                pass
            return
        except tk.TclError:
            return

        try:
            chat_box.config(state=tk.NORMAL)
            chat_box.delete(placeholder_index, "end-1c")
            if "indisponível" in result.lower() or result.startswith("⚠️"):
                chat_box.insert(tk.END, result + "\n\n", "error")
            else:
                chat_box.insert(tk.END, f"✒️ [HEAVEN'S DOOR]: {result}\n\n", "ai")
                last_response = result
                listen_button.config(state=tk.NORMAL)
                solicitar_fala(result)
            chat_box.config(state=tk.DISABLED)
            chat_box.see(tk.END)
            entrada_usuario.config(state=tk.NORMAL)
            send_button.config(state=tk.NORMAL)
            status_label.config(text="Pronto", fg="#999999")
            entrada_usuario.focus_set()
        except tk.TclError:
            return

    def enviar_mensagem(_event=None):
        nonlocal last_response
        pergunta = entrada_usuario.get().strip()
        if not pergunta:
            return "break"
        if len(pergunta) > MAX_PROMPT_CHARS:
            append_message(f"⚠️ Limite de {MAX_PROMPT_CHARS} caracteres por mensagem.", "error")
            return "break"

        chat_box.config(state=tk.NORMAL)
        chat_box.insert(tk.END, f"👤 [JOJO]: {pergunta}\n", "user")
        placeholder_index = chat_box.index(tk.END)
        chat_box.insert(tk.END, "✒️ [HEAVEN'S DOOR]: Escrevendo...\n", "thinking")
        chat_box.tag_config("thinking", foreground="#777777")
        chat_box.config(state=tk.DISABLED)
        chat_box.see(tk.END)
        entrada_usuario.delete(0, tk.END)

        try:
            command_response = executar_comando(pergunta)
        except Exception as exc:  # noqa: BLE001 - callback Tk: converte falha inesperada em mensagem e mantém a janela viva.
            command_response = f"⚠️ Não foi possível abrir esse recurso ({type(exc).__name__})."
        if command_response is not None:
            chat_box.config(state=tk.NORMAL)
            chat_box.delete(placeholder_index, "end-1c")
            append_tag = "error" if command_response.startswith("⚠️") else "ai"
            chat_box.insert(tk.END, f"✒️ [HEAVEN'S DOOR]: {command_response}\n\n", append_tag)
            chat_box.config(state=tk.DISABLED)
            chat_box.see(tk.END)
            if append_tag == "ai":
                last_response = command_response
                listen_button.config(state=tk.NORMAL)
                solicitar_fala(command_response)
            return "break"

        entrada_usuario.config(state=tk.DISABLED)
        send_button.config(state=tk.DISABLED)
        status_label.config(text="Conectando com a IA...", fg=JoJoTheme.GOLD)

        def worker():
            try:
                result = perguntar_ia(pergunta)
            except Exception as exc:  # noqa: BLE001 - fronteira de worker: erros da SDK viram resultado para a fila.
                result = f"⚠️ IA indisponível ({type(exc).__name__})."
            try:
                result_queue.put_nowait(str(result))
            except queue.Full:
                pass

        threading.Thread(target=worker, name="jojo-ai-request", daemon=True).start()
        janela_ia.after(100, lambda: poll_result(placeholder_index))
        return "break"

    def fechar_janela():
        voice_worker.close()
        try:
            janela_ia.destroy()
        except tk.TclError:
            pass

    send_button.config(command=enviar_mensagem)
    entrada_usuario.bind("<Return>", enviar_mensagem)
    janela_ia.protocol("WM_DELETE_WINDOW", fechar_janela)
    entrada_usuario.focus_set()
    janela_ia.after(100, poll_voice_events)
    return janela_ia
