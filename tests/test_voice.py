from __future__ import annotations

import io
import json
import os
import sys
import threading
import time
import types
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from core.tts import (
    FISH_AUDIO_API_URL,
    FISH_AUDIO_DEFAULT_MODEL,
    FISH_AUDIO_DEFAULT_REFERENCE_ID,
    SPEECH_RATE,
    SpeechWorker,
    TTSUnavailableError,
    TTSVoiceUnavailableError,
    falar_texto,
    gerar_audio_fish,
    limpar_texto_fala,
    reproduzir_audio_fish,
    selecionar_provedor_fala,
)


class FakeVoice:
    def __init__(self, voice_id, name, languages, gender):
        self.id = voice_id
        self.name = name
        self.languages = languages
        self.gender = gender


class FakeEngine:
    def __init__(self, voices):
        self.voices = voices
        self.properties = {}
        self.spoken = []
        self.stopped = False

    def getProperty(self, name):
        if name == "voices":
            return self.voices
        return self.properties.get(name)

    def setProperty(self, name, value):
        self.properties[name] = value

    def say(self, text):
        self.spoken.append(text)

    def runAndWait(self):
        return None

    def stop(self):
        self.stopped = True


class FakeCancelableEngine(FakeEngine):
    def __init__(self, voices):
        super().__init__(voices)
        self.busy = False
        self.speech_started = threading.Event()
        self.stop_thread_id = None
        self.loop_ended = False

    def say(self, text):
        super().say(text)
        self.busy = True
        self.speech_started.set()

    def startLoop(self, use_driver_loop):
        self.use_driver_loop = use_driver_loop

    def isBusy(self):
        return self.busy

    def iterate(self):
        time.sleep(0.005)

    def stop(self):
        self.stopped = True
        self.busy = False
        self.stop_thread_id = threading.get_ident()

    def endLoop(self):
        self.loop_ended = True


class FakeResponse:
    def __init__(self, data):
        self.data = data
        self.offset = 0

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _traceback):
        return False

    def read(self, size=-1):
        if size < 0:
            size = len(self.data) - self.offset
        result = self.data[self.offset : self.offset + size]
        self.offset += len(result)
        return result


class VoiceTests(unittest.TestCase):
    def test_markdown_code_and_visual_symbols_are_cleaned_and_limited(self):
        text = """# Título

**Olá** [documentação](https://example.test) ⚔️

```python
print('não falar')
```
"""
        cleaned = limpar_texto_fala(text, max_chars=80)
        self.assertEqual(cleaned, "Título Olá documentação")
        self.assertNotIn("print", cleaned)
        self.assertNotIn("⚔️", cleaned)

        limited = limpar_texto_fala("uma resposta muito longa " * 20, max_chars=60)
        self.assertLessEqual(len(limited), 60)
        self.assertTrue(limited.endswith("..."))

    def test_speaks_using_mocked_local_engine_and_prefers_male_portuguese_voice(self):
        voices = [
            FakeVoice("pt-female", "Português feminina", ["pt-BR"], "female"),
            FakeVoice("en-male", "English male", ["en-US"], "male"),
            FakeVoice("pt-male-low", "Português masculino grave", [b"pt-br"], "male"),
        ]
        engine = FakeEngine(voices)
        fake_pyttsx3 = types.SimpleNamespace(init=lambda: engine)

        with patch.dict(sys.modules, {"pyttsx3": fake_pyttsx3}):
            spoken = falar_texto("**Olá**, mundo!")

        self.assertEqual(spoken, "Olá, mundo!")
        self.assertEqual(engine.spoken, ["Olá, mundo!"])
        self.assertEqual(engine.properties["voice"], "pt-male-low")
        self.assertEqual(engine.properties["rate"], SPEECH_RATE)

    def test_missing_dependency_reports_clear_local_error(self):
        with patch.dict(sys.modules, {"pyttsx3": None}), self.assertRaisesRegex(
            TTSUnavailableError, "pyttsx3"
        ):
            falar_texto("Olá")

    def test_missing_system_voice_reports_clear_error(self):
        engine = FakeEngine([])
        fake_pyttsx3 = types.SimpleNamespace(init=lambda: engine)

        with patch.dict(sys.modules, {"pyttsx3": fake_pyttsx3}), self.assertRaisesRegex(
            TTSVoiceUnavailableError, "nenhuma voz"
        ):
            falar_texto("Olá")

    def test_stop_calls_audio_driver_only_from_worker_thread(self):
        engine = FakeCancelableEngine(
            [FakeVoice("pt-male", "Português masculino grave", ["pt-BR"], "male")]
        )
        events = []
        stopped = threading.Event()

        def record_event(event, message):
            events.append((event, message))
            if event == "stopped":
                stopped.set()

        with patch("core.tts.criar_engine", return_value=engine):
            worker = SpeechWorker(on_event=record_event)
            try:
                worker.enqueue("Resposta cancelável")
                self.assertTrue(engine.speech_started.wait(timeout=2))
                worker.stop()
                self.assertTrue(stopped.wait(timeout=2))
            finally:
                worker.close()

        self.assertTrue(engine.stopped)
        self.assertTrue(engine.loop_ended)
        self.assertEqual(engine.stop_thread_id, worker._thread.ident)
        self.assertNotEqual(engine.stop_thread_id, threading.get_ident())

    def test_worker_serializes_mocked_speech_without_audio(self):
        active = 0
        maximum_active = 0
        spoken = []
        lock = threading.Lock()
        completed = threading.Event()
        events = []

        def fake_speak(text, engine=None, stop_event=None):
            nonlocal active, maximum_active
            with lock:
                active += 1
                maximum_active = max(maximum_active, active)
                spoken.append(text)
            time.sleep(0.02)
            with lock:
                active -= 1
            if len(spoken) == 2:
                completed.set()
            return text

        def record_event(event, message):
            events.append((event, message))

        with patch("core.tts.criar_engine", return_value=object()), patch(
            "core.tts.falar_texto", side_effect=fake_speak
        ):
            worker = SpeechWorker(on_event=record_event, provider="local")
            try:
                worker.enqueue("Primeira resposta")
                worker.enqueue("Segunda resposta")
                self.assertTrue(completed.wait(timeout=2))
            finally:
                worker.close()

        self.assertEqual(spoken, ["Primeira resposta", "Segunda resposta"])
        self.assertEqual(maximum_active, 1)
        self.assertEqual([event for event, _ in events].count("started"), 2)
        self.assertEqual([event for event, _ in events].count("done"), 2)

    def test_auto_provider_prefers_fish_only_when_api_key_is_configured(self):
        with patch.dict(
            os.environ,
            {"JOJO_TTS_PROVIDER": "auto", "FISH_AUDIO_API_KEY": "test-token"},
            clear=True,
        ):
            self.assertEqual(selecionar_provedor_fala(), "fish")
        with patch.dict(os.environ, {"JOJO_TTS_PROVIDER": "auto"}, clear=True):
            self.assertEqual(selecionar_provedor_fala(), "local")
        with patch.dict(os.environ, {"JOJO_TTS_PROVIDER": "local", "FISH_AUDIO_API_KEY": "x"}, clear=True):
            self.assertEqual(selecionar_provedor_fala(), "local")

    def test_fish_request_uses_character_model_and_returns_audio(self):
        captured = {}
        audio = b"RIFF-test-WAVE"

        def fake_urlopen(request, timeout):
            captured["url"] = request.full_url
            captured["timeout"] = timeout
            captured["headers"] = {key.lower(): value for key, value in request.header_items()}
            captured["payload"] = json.loads(request.data.decode("utf-8"))
            return FakeResponse(audio)

        with patch("core.tts.urlopen", side_effect=fake_urlopen):
            result = gerar_audio_fish(
                "**Olá** [amigo](https://example.test)",
                api_key="test-token",
            )

        self.assertEqual(result, audio)
        self.assertEqual(captured["url"], FISH_AUDIO_API_URL)
        self.assertEqual(captured["headers"]["authorization"], "Bearer test-token")
        self.assertEqual(captured["headers"]["model"], FISH_AUDIO_DEFAULT_MODEL)
        self.assertEqual(captured["payload"]["reference_id"], FISH_AUDIO_DEFAULT_REFERENCE_ID)
        self.assertEqual(captured["payload"]["text"], "Olá amigo")
        self.assertEqual(captured["payload"]["format"], "wav")

    def test_fish_missing_key_and_http_errors_are_clear_without_exposing_token(self):
        with patch.dict(os.environ, {}, clear=True), self.assertRaisesRegex(
            TTSUnavailableError, "FISH_AUDIO_API_KEY"
        ):
            gerar_audio_fish("Olá")

        secret = "token-never-display"
        error = HTTPError(
            FISH_AUDIO_API_URL,
            402,
            "payment required",
            hdrs={},
            fp=io.BytesIO(secret.encode("utf-8")),
        )
        with patch("core.tts.urlopen", side_effect=error), self.assertRaises(
            TTSUnavailableError
        ) as raised:
            gerar_audio_fish("Olá", api_key=secret)
        self.assertIn("créditos", str(raised.exception))
        self.assertNotIn(secret, str(raised.exception))

    def test_worker_routes_fish_audio_through_background_player(self):
        done = threading.Event()
        events = []

        def record_event(event, message):
            events.append((event, message))
            if event == "done":
                done.set()

        with patch("core.tts.gerar_audio_fish", return_value=b"audio") as generate, patch(
            "core.tts.reproduzir_audio_fish"
        ) as play:
            worker = SpeechWorker(on_event=record_event, provider="fish")
            try:
                worker.enqueue("Resposta falada")
                self.assertTrue(done.wait(timeout=2))
            finally:
                worker.close()

        generate.assert_called_once_with("Resposta falada")
        play.assert_called_once()
        self.assertEqual([event for event, _ in events], ["started", "done"])

    def test_fish_playback_uses_pygame_and_stops_the_channel(self):
        stop_event = threading.Event()
        state = {"initialized": False, "loaded": None, "stopped": False}

        class FakeChannel:
            def get_busy(self):
                stop_event.set()
                return True

            def stop(self):
                state["stopped"] = True

        class FakeSound:
            def play(self):
                return FakeChannel()

        class FakeMixer:
            def get_init(self):
                return state["initialized"]

            def init(self):
                state["initialized"] = True

            def Sound(self, *, file):
                state["loaded"] = file.read()
                return FakeSound()

        fake_pygame = types.SimpleNamespace(mixer=FakeMixer())
        with patch.dict(sys.modules, {"pygame": fake_pygame}):
            reproduzir_audio_fish(b"RIFF-test-WAVE", stop_event)

        self.assertTrue(state["initialized"])
        self.assertEqual(state["loaded"], b"RIFF-test-WAVE")
        self.assertTrue(state["stopped"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
