from __future__ import annotations

import io
import json
import os
import queue
import re
import threading
import time
import unicodedata
from collections.abc import Callable, Iterable
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

MAX_SPEECH_CHARS = 3000
SPEECH_RATE = 145
VOICE_PROFILE = "grave e dramático"
FISH_AUDIO_API_URL = "https://api.fish.audio/v1/tts"
FISH_AUDIO_DEFAULT_MODEL = "drama-3"
FISH_AUDIO_DEFAULT_REFERENCE_ID = "ed45c9bdc3d74548bf4987c9987f218b"
FISH_AUDIO_TIMEOUT_SECONDS = 45
FISH_AUDIO_MAX_BYTES = 25 * 1024 * 1024


class TTSUnavailableError(RuntimeError):
    """Falha ao disponibilizar o mecanismo local de fala."""


class TTSVoiceUnavailableError(TTSUnavailableError):
    """O mecanismo existe, mas não há voz de sistema utilizável."""


_CODE_BLOCK_RE = re.compile(r"```[^\n`]*?(?:\r?\n|```).*?```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`[^`\n]*`")
_MARKDOWN_LINK_RE = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
_MARKDOWN_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s*", re.MULTILINE)
_MARKDOWN_LIST_RE = re.compile(r"^\s{0,3}(?:[-*+]\s+|\d+[.)]\s+)", re.MULTILINE)
_MARKDOWN_QUOTE_RE = re.compile(r"^\s{0,3}>\s?", re.MULTILINE)
_HTML_TAG_RE = re.compile(r"<[^>\n]+>")


def _remove_visual_symbols(text: str) -> str:
    """Retira emojis e símbolos decorativos que não têm leitura útil no TTS."""
    return "".join(
        character
        for character in text
        if character not in {"\ufe0e", "\ufe0f", "\u200d"}
        and not (
            ord(character) > 127
            and unicodedata.category(character) in {"So", "Sk"}
        )
    )


def limitar_texto_fala(texto: str, max_chars: int = MAX_SPEECH_CHARS) -> str:
    """Limita uma fala sem cortar uma palavra quando há espaço para recuar."""
    if max_chars < 1:
        raise ValueError("max_chars deve ser maior que zero")
    if len(texto) <= max_chars:
        return texto
    if max_chars <= 3:
        return texto[:max_chars]

    body_limit = max_chars - 3
    trecho = texto[:body_limit].rstrip()
    boundary = trecho.rfind(" ")
    if boundary >= max(1, body_limit // 2):
        trecho = trecho[:boundary].rstrip()
    trecho = trecho.rstrip(".,;:!?-")
    return trecho + "..."


def limpar_texto_fala(texto: str, max_chars: int = MAX_SPEECH_CHARS) -> str:
    """Converte uma resposta em texto curto e legível para uma voz de sistema."""
    if not isinstance(texto, str):
        raise TypeError("O texto da fala precisa ser uma string.")

    texto_limpo = _CODE_BLOCK_RE.sub(" ", texto)
    texto_limpo = _INLINE_CODE_RE.sub(" ", texto_limpo)
    texto_limpo = _MARKDOWN_LINK_RE.sub(r"\1", texto_limpo)
    texto_limpo = _MARKDOWN_HEADING_RE.sub("", texto_limpo)
    texto_limpo = _MARKDOWN_LIST_RE.sub("", texto_limpo)
    texto_limpo = _MARKDOWN_QUOTE_RE.sub("", texto_limpo)
    texto_limpo = _HTML_TAG_RE.sub(" ", texto_limpo)
    texto_limpo = re.sub(r"[*_~]", "", texto_limpo)
    texto_limpo = re.sub(r"\[([^\]]+)\]", r"\1", texto_limpo)
    texto_limpo = _remove_visual_symbols(texto_limpo)
    texto_limpo = re.sub(r"\s+", " ", texto_limpo).strip()
    return limitar_texto_fala(texto_limpo, max_chars=max_chars)


def _load_pyttsx3() -> Any:
    """Importa pyttsx3 somente quando uma fala foi realmente solicitada."""
    try:
        import pyttsx3
    except ImportError as exc:
        raise TTSUnavailableError(
            "Fala local indisponível: instale a dependência 'pyttsx3'."
        ) from exc
    return pyttsx3


def selecionar_provedor_fala(provider: str | None = None) -> str:
    """Usa Fish Audio quando configurado; mantém voz local como alternativa."""
    choice = (provider or os.getenv("JOJO_TTS_PROVIDER", "auto")).strip().lower()
    if choice == "auto":
        return "fish" if os.getenv("FISH_AUDIO_API_KEY", "").strip() else "local"
    if choice in {"fish", "local"}:
        return choice
    raise ValueError("JOJO_TTS_PROVIDER deve ser 'auto', 'fish' ou 'local'.")


def _as_text(value: Any) -> str:
    if isinstance(value, (bytes, bytearray)):
        return value.decode("utf-8", errors="ignore")
    if isinstance(value, (list, tuple, set)):
        return " ".join(_as_text(item) for item in value)
    return str(value or "")


def _voice_descriptor(voice: Any) -> str:
    values = (
        getattr(voice, "id", ""),
        getattr(voice, "name", ""),
        getattr(voice, "gender", ""),
        getattr(voice, "languages", ""),
    )
    return " ".join(_as_text(value) for value in values).lower()


def selecionar_voz(voices: Iterable[Any]) -> Any:
    """Escolhe, por melhor esforço, uma voz portuguesa masculina e grave."""
    candidates = list(voices or [])
    if not candidates:
        raise TTSVoiceUnavailableError(
            "Fala local indisponível: nenhuma voz de sistema foi encontrada."
        )

    def score(voice: Any) -> tuple[int, int, int, int]:
        descriptor = _voice_descriptor(voice)
        portuguese = int(
            bool(
                re.search(
                    r"(?:pt(?:[-_ ]?(?:br|pt))?|portugu|brazil|brasil)",
                    descriptor,
                )
            )
        )
        female = int(bool(re.search(r"female|feminina|mulher", descriptor)))
        male = int(
            bool(re.search(r"(?<!fe)male|masculino|homem", descriptor))
        )
        low = int(bool(re.search(r"low|deep|grave|baixo", descriptor)))
        return (portuguese, male - female, low, -female)

    return max(candidates, key=score)


def configurar_voz(engine: Any) -> Any:
    """Configura a voz do engine sem tentar imitar uma pessoa real."""
    try:
        voices = engine.getProperty("voices")
    except Exception as exc:
        raise TTSVoiceUnavailableError(
            "Fala local indisponível: não foi possível consultar as vozes do sistema."
        ) from exc

    voice = selecionar_voz(voices)
    voice_id = getattr(voice, "id", None)
    if not voice_id:
        raise TTSVoiceUnavailableError(
            "Fala local indisponível: a voz do sistema não possui identificador."
        )

    try:
        engine.setProperty("voice", voice_id)
        engine.setProperty("rate", SPEECH_RATE)
    except Exception as exc:
        raise TTSUnavailableError(
            "Fala local indisponível: não foi possível configurar a voz do sistema."
        ) from exc
    return voice


def criar_engine() -> Any:
    """Cria um engine pyttsx3 sem inicializá-lo durante o import da aplicação."""
    pyttsx3 = _load_pyttsx3()
    try:
        engine = pyttsx3.init()
    except Exception as exc:
        raise TTSUnavailableError(
            "Fala local indisponível: não foi possível iniciar o pyttsx3."
        ) from exc
    if engine is None:
        raise TTSUnavailableError(
            "Fala local indisponível: o pyttsx3 não retornou um engine."
        )
    return engine


def falar_texto(
    texto: str,
    engine: Any | None = None,
    *,
    stop_event: threading.Event | None = None,
) -> str:
    """Fala texto localmente e devolve o texto efetivamente enviado ao engine."""
    texto_limpo = limpar_texto_fala(texto)
    if not texto_limpo:
        raise ValueError("Não há texto legível para falar.")

    engine = engine or criar_engine()
    configurar_voz(engine)
    try:
        engine.say(texto_limpo)
        if stop_event is None:
            engine.runAndWait()
        else:
            engine.startLoop(False)
            try:
                while engine.isBusy():
                    if stop_event.is_set():
                        engine.stop()
                        break
                    engine.iterate()
                    stop_event.wait(0.01)
            finally:
                engine.endLoop()
    except Exception as exc:
        raise TTSUnavailableError(
            "Fala local indisponível: o driver de voz não conseguiu reproduzir o texto."
        ) from exc
    return texto_limpo


def gerar_audio_fish(
    texto: str,
    *,
    api_key: str | None = None,
    reference_id: str | None = None,
    model: str | None = None,
) -> bytes:
    """Solicita áudio WAV à Fish Audio sem registrar a chave nem o texto."""
    texto_limpo = limpar_texto_fala(texto)
    if not texto_limpo:
        raise ValueError("Não há texto legível para falar.")

    token = (api_key if api_key is not None else os.getenv("FISH_AUDIO_API_KEY", "")).strip()
    if not token:
        raise TTSUnavailableError(
            "Fish Audio não configurado: adicione FISH_AUDIO_API_KEY ao arquivo .env local."
        )
    if "\r" in token or "\n" in token:
        raise TTSUnavailableError("A chave Fish Audio configurada é inválida.")

    voice_id = (
        reference_id
        if reference_id is not None
        else os.getenv("FISH_AUDIO_REFERENCE_ID", FISH_AUDIO_DEFAULT_REFERENCE_ID)
    ).strip()
    model_name = (
        model if model is not None else os.getenv("FISH_AUDIO_MODEL", FISH_AUDIO_DEFAULT_MODEL)
    ).strip()
    if not voice_id or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", voice_id):
        raise TTSUnavailableError("O identificador da voz Fish Audio é inválido.")
    if not model_name or not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", model_name):
        raise TTSUnavailableError("O modelo Fish Audio configurado é inválido.")

    payload = {
        "text": texto_limpo,
        "reference_id": voice_id,
        "format": "wav",
        "sample_rate": 44100,
        "normalize": True,
        "prosody": {"speed": 1.0, "volume": 0},
    }
    request = Request(
        FISH_AUDIO_API_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "model": model_name,
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=FISH_AUDIO_TIMEOUT_SECONDS) as response:
            chunks = []
            total = 0
            while total <= FISH_AUDIO_MAX_BYTES:
                chunk = response.read(min(1024 * 1024, FISH_AUDIO_MAX_BYTES + 1 - total))
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
            audio = b"".join(chunks)
    except HTTPError as exc:
        status = int(getattr(exc, "code", 0) or 0)
        try:
            exc.close()
        except OSError:
            pass
        if status in {401, 403}:
            detail = "Fish Audio recusou a chave ou a permissão desta voz. Confira sua conta."
        elif status == 402:
            detail = "Fish Audio informou que a conta não tem acesso ou créditos para a API."
        elif status == 413:
            detail = "O texto ultrapassou o limite aceito pela conta Fish Audio."
        elif status == 429:
            detail = "O limite de uso Fish Audio foi atingido. Aguarde ou confira sua cota."
        else:
            detail = f"Fish Audio retornou um erro HTTP ({status or 'desconhecido'})."
        raise TTSUnavailableError(detail) from None
    except (URLError, TimeoutError, OSError, ValueError) as exc:
        del exc
        raise TTSUnavailableError(
            "Não foi possível conectar à Fish Audio. Confira a internet e tente novamente."
        ) from None

    if not audio:
        raise TTSUnavailableError("Fish Audio não retornou um arquivo de áudio.")
    if len(audio) > FISH_AUDIO_MAX_BYTES:
        raise TTSUnavailableError("O áudio Fish Audio excedeu o limite de tamanho do aplicativo.")
    return audio


def reproduzir_audio_fish(
    audio: bytes,
    stop_event: threading.Event | None = None,
) -> None:
    """Reproduz o WAV gerado pela Fish Audio sem bloquear a interface Tk."""
    if stop_event is not None and stop_event.is_set():
        return
    try:
        import pygame

        if not pygame.mixer.get_init():
            pygame.mixer.init()
        sound = pygame.mixer.Sound(file=io.BytesIO(audio))
        channel = sound.play()
        if channel is None:
            raise RuntimeError("Não há canal de áudio disponível.")
        while channel.get_busy():
            if stop_event is not None and stop_event.is_set():
                channel.stop()
                return
            if stop_event is None:
                time.sleep(0.03)
            else:
                stop_event.wait(0.03)
    except Exception as exc:  # noqa: BLE001 - driver de áudio depende do sistema local.
        del exc
        raise TTSUnavailableError(
            "A fala foi gerada, mas o áudio não pôde ser reproduzido neste computador."
        ) from None


class SpeechWorker:
    """Fila serial de fala local ou Fish Audio para não sobrepor respostas."""

    def __init__(
        self,
        on_event: Callable[[str, str], None] | None = None,
        *,
        provider: str | None = None,
    ):
        self._queue: queue.Queue[str | None] = queue.Queue()
        self._on_event = on_event
        self._provider = selecionar_provedor_fala(provider)
        self._stop_requested = threading.Event()
        self._engine: Any | None = None
        self._closed = False
        self._thread = threading.Thread(
            target=self._run,
            name="jojo-tts-worker",
            daemon=True,
        )
        self._thread.start()

    def _emit(self, event: str, message: str = "") -> None:
        if self._on_event is None:
            return
        try:
            self._on_event(event, message)
        except Exception as exc:  # noqa: BLE001 - callback externo não pode parar o worker.
            del exc
            return

    def _discard_pending(self) -> None:
        while True:
            try:
                pending = self._queue.get_nowait()
            except queue.Empty:
                return
            if pending is not None:
                self._queue.task_done()

    def enqueue(self, texto: str) -> str:
        """Adiciona uma fala para execução serial, sem sobrepor nem descartar respostas."""
        if self._closed:
            raise RuntimeError("O worker de fala já foi encerrado.")
        texto_limpo = limpar_texto_fala(texto)
        if not texto_limpo:
            raise ValueError("Não há texto legível para falar.")
        self._queue.put_nowait(texto_limpo)
        return texto_limpo

    def stop(self) -> None:
        """Para a fala atual e remove itens ainda não iniciados da fila."""
        self._stop_requested.set()
        self._discard_pending()
        # O engine só é acessado pela thread consumidora. Ela percebe este
        # evento no loop incremental e chama stop() em seu próprio contexto.

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.stop()
        self._discard_pending()
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            self._discard_pending()
            self._queue.put_nowait(None)
        if self._thread is not threading.current_thread():
            self._thread.join(timeout=1.0)

    def _run(self) -> None:
        while True:
            texto = self._queue.get()
            if texto is None:
                return
            self._stop_requested.clear()
            try:
                self._emit("started", texto)
                if self._provider == "fish":
                    audio = gerar_audio_fish(texto)
                    if not self._stop_requested.is_set():
                        reproduzir_audio_fish(audio, self._stop_requested)
                else:
                    if self._engine is None:
                        self._engine = criar_engine()
                    falar_texto(
                        texto,
                        engine=self._engine,
                        stop_event=self._stop_requested,
                    )
                if self._stop_requested.is_set():
                    self._emit("stopped", "")
                else:
                    self._emit("done", texto)
            except Exception as exc:  # noqa: BLE001 - erro fica isolado no worker.
                self._emit("error", str(exc))
            finally:
                self._queue.task_done()
