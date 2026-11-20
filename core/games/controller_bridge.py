"""USB controller bridge for IKEMEN GO.

The TCP listener is deliberately bound to IPv4 loopback only.  The Android side
must reach it through ``adb reverse``; this module never opens a LAN listener or
runs commands received from the phone.  The client sends one newline-delimited
``{"token": "<32 lowercase hex>", "protocol": 1}`` handshake, then a newline JSON
``{"mask": <0..2047>}`` every 100 ms and immediately on changes; only the handshake
receives an acknowledgement.
"""
from __future__ import annotations

import ctypes
import hmac
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import threading
import time
from collections.abc import Callable, Mapping
from ctypes import wintypes
from pathlib import Path
from typing import Protocol

HOST = "127.0.0.1"
PORT = 8765
PROTOCOL_VERSION = 1
LINE_LIMIT = 256
CLIENT_TIMEOUT_SECONDS = 0.5
POLL_INTERVAL_SECONDS = 0.05

CONTROL_BITS: tuple[tuple[str, int], ...] = (
    ("Up", 0),
    ("Down", 1),
    ("Left", 2),
    ("Right", 3),
    ("A", 4),
    ("B", 5),
    ("C", 6),
    ("X", 7),
    ("Y", 8),
    ("Z", 9),
    ("Start", 10),
)
DEFAULT_MAPPING: dict[str, str] = {
    "Up": "up",
    "Down": "down",
    "Left": "left",
    "Right": "right",
    "A": "z",
    "B": "x",
    "C": "c",
    "X": "a",
    "Y": "s",
    "Z": "d",
    "Start": "enter",
}

# Names are intentionally restricted to ordinary game keys.  System/Windows
# keys, Escape and arbitrary key names are not accepted by the UI or bridge.
_SCAN_CODES: dict[str, tuple[int, bool]] = {
    "up": (0x48, True),
    "down": (0x50, True),
    "left": (0x4B, True),
    "right": (0x4D, True),
    "enter": (0x1C, False),
    "space": (0x39, False),
    "shift": (0x2A, False),
    "ctrl": (0x1D, False),
    "alt": (0x38, False),
    "0": (0x0B, False),
    "1": (0x02, False),
    "2": (0x03, False),
    "3": (0x04, False),
    "4": (0x05, False),
    "5": (0x06, False),
    "6": (0x07, False),
    "7": (0x08, False),
    "8": (0x09, False),
    "9": (0x0A, False),
    "a": (0x1E, False),
    "b": (0x30, False),
    "c": (0x2E, False),
    "d": (0x20, False),
    "e": (0x12, False),
    "f": (0x21, False),
    "g": (0x22, False),
    "h": (0x23, False),
    "i": (0x17, False),
    "j": (0x24, False),
    "k": (0x25, False),
    "l": (0x26, False),
    "m": (0x32, False),
    "n": (0x31, False),
    "o": (0x18, False),
    "p": (0x19, False),
    "q": (0x10, False),
    "r": (0x13, False),
    "s": (0x1F, False),
    "t": (0x14, False),
    "u": (0x16, False),
    "v": (0x2F, False),
    "w": (0x11, False),
    "x": (0x2D, False),
    "y": (0x15, False),
    "z": (0x2C, False),
}
ALLOWED_KEYS: tuple[str, ...] = tuple(_SCAN_CODES)
_TOKEN_RE = re.compile(r"[0-9a-f]{32}\Z")


class KeyboardBackend(Protocol):
    """Minimal keyboard output interface used by the state machine."""

    def set_keys(self, keys: set[str]) -> None: ...

    def release_all(self) -> None: ...


class RecordingKeyboardBackend:
    """Dry-run backend for tests and Linux development; never injects input."""

    def __init__(self) -> None:
        self.current_keys: set[str] = set()
        self.history: list[frozenset[str]] = []
        self._lock = threading.Lock()

    def set_keys(self, keys: set[str]) -> None:
        with self._lock:
            self.current_keys = set(keys)
            self.history.append(frozenset(keys))

    def release_all(self) -> None:
        self.set_keys(set())


class WindowsSendInputBackend:
    """Windows-only scan-code keyboard backend backed by ``SendInput``."""

    KEYEVENTF_EXTENDEDKEY = 0x0001
    KEYEVENTF_KEYUP = 0x0002
    KEYEVENTF_SCANCODE = 0x0008
    INPUT_KEYBOARD = 1

    def __init__(self) -> None:
        if os.name != "nt":
            raise RuntimeError("O controle USB do IKEMEN só injeta teclas no Windows.")
        self._down: set[str] = set()
        self._lock = threading.Lock()
        self._user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._user32.SendInput.argtypes = (
            wintypes.UINT,
            ctypes.POINTER(_INPUT),
            ctypes.c_int,
        )
        self._user32.SendInput.restype = wintypes.UINT

    def _send(self, key: str, down: bool) -> None:
        scan_code, extended = _SCAN_CODES[key]
        flags = self.KEYEVENTF_SCANCODE
        if extended:
            flags |= self.KEYEVENTF_EXTENDEDKEY
        if not down:
            flags |= self.KEYEVENTF_KEYUP
        event = _INPUT(type=self.INPUT_KEYBOARD)
        event.ki = _KEYBDINPUT(
            wVk=0,
            wScan=scan_code,
            dwFlags=flags,
            time=0,
            dwExtraInfo=0,
        )
        sent = self._user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(_INPUT))
        if sent != 1:
            raise OSError(ctypes.get_last_error(), "SendInput não aceitou a tecla.")

    def set_keys(self, keys: set[str]) -> None:
        unknown = keys.difference(_SCAN_CODES)
        if unknown:
            raise ValueError(f"Teclas não permitidas: {sorted(unknown)!r}")
        with self._lock:
            released = self._down - keys
            pressed = keys - self._down
            try:
                for key in sorted(released):
                    self._send(key, False)
                for key in sorted(pressed):
                    self._send(key, True)
            except OSError:
                # A partial SendInput failure must not leave a held key behind.
                self._release_locked()
                raise
            self._down = set(keys)

    def _release_locked(self) -> None:
        for key in sorted(self._down):
            try:
                self._send(key, False)
            except OSError:
                pass
        self._down.clear()

    def release_all(self) -> None:
        with self._lock:
            self._release_locked()


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = (
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    )


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = (
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    )


class _HARDWAREINPUT(ctypes.Structure):
    _fields_ = (
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    )


class _INPUT_UNION(ctypes.Union):
    _fields_ = (("mi", _MOUSEINPUT), ("ki", _KEYBDINPUT), ("hi", _HARDWAREINPUT))


class _INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = (("type", wintypes.DWORD), ("u", _INPUT_UNION))


def validate_mapping(mapping: Mapping[str, str]) -> dict[str, str]:
    """Return a normalized, one-to-one mapping over the fixed control set."""
    expected = {name for name, _bit in CONTROL_BITS}
    if set(mapping) != expected:
        raise ValueError("O mapeamento deve conter exatamente os 11 controles do protocolo.")
    normalized: dict[str, str] = {}
    for control, key in mapping.items():
        if not isinstance(key, str) or key.casefold() not in _SCAN_CODES:
            raise ValueError(f"Tecla não permitida para {control}: {key!r}")
        normalized[control] = key.casefold()
    if len(set(normalized.values())) != len(normalized):
        raise ValueError("Cada controle precisa usar uma tecla diferente.")
    return normalized


def neutralize_opposites(mask: int) -> int:
    """Clear Up+Down and Left+Right pairs from a valid controller mask."""
    if type(mask) is not int or not 0 <= mask <= 2047:
        raise ValueError("mask deve ser um inteiro entre 0 e 2047.")
    if mask & 0b11 == 0b11:
        mask &= ~0b11
    if mask & 0b1100 == 0b1100:
        mask &= ~0b1100
    return mask


def _normalized_path(path: str | Path) -> str:
    return os.path.normcase(str(Path(path).expanduser().resolve(strict=False)))


def foreground_process_matches(expected_path: str | Path) -> bool:
    """Return true only when the foreground window belongs to the exact EXE."""
    if os.name != "nt":
        return False
    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        user32.GetForegroundWindow.restype = wintypes.HWND
        user32.GetWindowThreadProcessId.argtypes = (
            wintypes.HWND,
            ctypes.POINTER(wintypes.DWORD),
        )
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.QueryFullProcessImageNameW.argtypes = (
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.LPWSTR,
            ctypes.POINTER(wintypes.DWORD),
        )
        kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel32.CloseHandle.restype = wintypes.BOOL
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return False
        process_id = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
        if not process_id.value:
            return False
        process = kernel32.OpenProcess(0x1000, False, process_id.value)
        if not process:
            return False
        try:
            size = wintypes.DWORD(32768)
            buffer = ctypes.create_unicode_buffer(size.value)
            if not kernel32.QueryFullProcessImageNameW(
                process, 0, buffer, ctypes.byref(size)
            ):
                return False
            return _normalized_path(buffer.value) == _normalized_path(expected_path)
        finally:
            kernel32.CloseHandle(process)
    except (AttributeError, OSError, ValueError):
        return False


class ControllerState:
    """Translate masks into pressed keys with focus and neutral-frame guards."""

    def __init__(
        self,
        backend: KeyboardBackend,
        mapping: Mapping[str, str] | None = None,
        focus_check: Callable[[], bool] | None = None,
    ) -> None:
        self.backend = backend
        self._mapping = validate_mapping(
            mapping if mapping is not None else DEFAULT_MAPPING
        )
        self._focus_check = focus_check or (lambda: True)
        self._lock = threading.RLock()
        self._last_focus: bool | None = None
        self._needs_neutral = True
        self._stopped = False
        self._active_keys: set[str] = set()

    @property
    def mapping(self) -> dict[str, str]:
        with self._lock:
            return dict(self._mapping)

    @property
    def needs_neutral(self) -> bool:
        with self._lock:
            return self._needs_neutral

    def set_mapping(self, mapping: Mapping[str, str]) -> None:
        normalized = validate_mapping(mapping)
        with self._lock:
            if self._stopped:
                return
            self._mapping = normalized
            self._needs_neutral = True
            self._set_keys_locked(set())

    def _set_keys_locked(self, keys: set[str]) -> None:
        if keys == self._active_keys:
            return
        self.backend.set_keys(set(keys))
        self._active_keys = set(keys)

    def _observe_focus_locked(self) -> bool:
        try:
            focused = bool(self._focus_check())
        except Exception:  # noqa: BLE001 - focus uncertainty must fail closed.
            focused = False
        if self._last_focus is None:
            self._last_focus = focused
            if not focused:
                self._needs_neutral = True
        elif focused != self._last_focus:
            if not focused:
                self._set_keys_locked(set())
            self._needs_neutral = True
            self._last_focus = focused
        return focused

    def tick_focus(self) -> None:
        """Poll focus even between protocol frames, releasing on focus loss."""
        with self._lock:
            if not self._stopped:
                self._observe_focus_locked()

    def apply_mask(self, mask: int) -> None:
        mask = neutralize_opposites(mask)
        with self._lock:
            if self._stopped:
                return
            focused = self._observe_focus_locked()
            if not focused:
                self._needs_neutral = True
                self._set_keys_locked(set())
                return
            if self._needs_neutral:
                if mask == 0:
                    self._needs_neutral = False
                    self._set_keys_locked(set())
                return
            pressed = {
                self._mapping[control]
                for control, bit in CONTROL_BITS
                if mask & (1 << bit)
            }
            self._set_keys_locked(pressed)

    def release_all(self, *, require_neutral: bool = True) -> None:
        with self._lock:
            self._set_keys_locked(set())
            if require_neutral:
                self._needs_neutral = True

    def stop(self) -> None:
        with self._lock:
            self._set_keys_locked(set())
            self._needs_neutral = True
            self._stopped = True


class ProtocolError(ValueError):
    """Malformed, oversized or unauthenticated protocol data."""


def _json_object(line: bytes) -> dict[str, object]:
    def reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ProtocolError("JSON contém uma chave duplicada.")
            result[key] = value
        return result

    try:
        decoded = json.loads(line.decode("utf-8"), object_pairs_hook=reject_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProtocolError("JSON inválido.") from exc
    if not isinstance(decoded, dict):
        raise ProtocolError("Cada linha precisa conter um objeto JSON.")
    return decoded


class ControllerBridge:
    """Single-client, loopback-only TCP bridge for one Android USB session."""

    def __init__(
        self,
        *,
        backend: KeyboardBackend | None = None,
        port: int = PORT,
        mapping: Mapping[str, str] | None = None,
        expected_ikemen_path: str | Path | None = None,
        focus_check: Callable[[], bool] | None = None,
        on_status: Callable[[str], None] | None = None,
    ) -> None:
        if not 0 <= port <= 65535:
            raise ValueError("A porta precisa estar entre 0 e 65535.")
        self.backend = backend if backend is not None else WindowsSendInputBackend()
        self._mapping = validate_mapping(
            mapping if mapping is not None else DEFAULT_MAPPING
        )
        if focus_check is not None:
            self._focus_check = focus_check
        elif expected_ikemen_path is not None and isinstance(
            self.backend, WindowsSendInputBackend
        ):
            self._focus_check = lambda: foreground_process_matches(expected_ikemen_path)
        else:
            self._focus_check = lambda: True
        self._state = ControllerState(self.backend, self._mapping, self._focus_check)
        self._requested_port = port
        self.port = port
        self.token: str | None = None
        self._on_status = on_status or (lambda _message: None)
        self._stop_event = threading.Event()
        self._lifecycle_lock = threading.Lock()
        self._client_lock = threading.Lock()
        self._listener: socket.socket | None = None
        self._active_socket: socket.socket | None = None
        self._accept_thread: threading.Thread | None = None
        self._client_thread: threading.Thread | None = None
        self._started = False

    def start(self) -> str:
        with self._lifecycle_lock:
            if self._started or self._stop_event.is_set():
                raise RuntimeError("Esta sessão da ponte já foi iniciada ou encerrada.")
            self.token = secrets.token_hex(16)
            listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                # Deliberately hard-coded; never change this to 0.0.0.0.
                listener.bind((HOST, self._requested_port))
                listener.listen(4)
                listener.settimeout(POLL_INTERVAL_SECONDS)
            except OSError:
                listener.close()
                raise
            self.port = int(listener.getsockname()[1])
            self._listener = listener
            self._started = True
            self._accept_thread = threading.Thread(
                target=self._accept_loop,
                name="jojo-controller-listener",
                daemon=True,
            )
            self._accept_thread.start()
            self._notify(f"Servidor USB local iniciado em 127.0.0.1:{self.port}.")
        return self.token

    def _notify(self, message: str) -> None:
        try:
            self._on_status(message)
        except Exception:  # noqa: BLE001 - status callbacks must not break the bridge.
            return

    def set_mapping(self, mapping: Mapping[str, str]) -> None:
        normalized = validate_mapping(mapping)
        self._mapping = normalized
        self._state.set_mapping(normalized)

    def _accept_loop(self) -> None:
        listener = self._listener
        if listener is None:
            return
        while not self._stop_event.is_set():
            try:
                connection, _address = listener.accept()
            except TimeoutError:
                continue
            except OSError:
                break
            connection.settimeout(POLL_INTERVAL_SECONDS)
            with self._client_lock:
                if self._active_socket is not None:
                    # Only one active client is allowed; do not interrupt it.
                    connection.close()
                    continue
                self._active_socket = connection
                worker = threading.Thread(
                    target=self._serve_client,
                    args=(connection,),
                    name="jojo-controller-client",
                    daemon=True,
                )
                self._client_thread = worker
                worker.start()
        self._notify("Servidor USB local encerrado.")

    def _authenticate(self, line: bytes) -> None:
        message = _json_object(line)
        if set(message) != {"token", "protocol"}:
            raise ProtocolError("Handshake com campos inválidos.")
        token = message.get("token")
        protocol = message.get("protocol")
        if (
            not isinstance(token, str)
            or not _TOKEN_RE.fullmatch(token)
            or type(protocol) is not int
            or protocol != PROTOCOL_VERSION
            or self.token is None
            or not hmac.compare_digest(token, self.token)
        ):
            raise ProtocolError("Token ou versão de protocolo inválidos.")

    @staticmethod
    def _parse_mask(line: bytes) -> int:
        message = _json_object(line)
        if set(message) != {"mask"}:
            raise ProtocolError("Quadro de controle com campos inválidos.")
        mask = message.get("mask")
        if type(mask) is not int or not 0 <= mask <= 2047:
            raise ProtocolError("mask precisa ser um inteiro entre 0 e 2047.")
        return mask

    def _serve_client(self, connection: socket.socket) -> None:
        self._state.release_all()
        authenticated = False
        buffer = bytearray()
        last_received = time.monotonic()
        self._notify("Conexão USB recebida; aguardando autenticação do telefone.")
        try:
            while not self._stop_event.is_set():
                try:
                    data = connection.recv(1024)
                except TimeoutError:
                    self._state.tick_focus()
                    if time.monotonic() - last_received >= CLIENT_TIMEOUT_SECONDS:
                        raise TimeoutError("sem dados por 0,5 segundo")
                    continue
                if not data:
                    raise ConnectionError("o telefone encerrou a conexão")
                last_received = time.monotonic()
                buffer.extend(data)
                while b"\n" in buffer:
                    newline = buffer.index(b"\n")
                    if newline + 1 > LINE_LIMIT:
                        raise ProtocolError("Linha JSON excede o limite de 256 bytes.")
                    line = bytes(buffer[:newline])
                    del buffer[: newline + 1]
                    if line.endswith(b"\r"):
                        line = line[:-1]
                    if not authenticated:
                        self._authenticate(line)
                        authenticated = True
                        connection.sendall(b'{"ok":true,"protocol":1}\n')
                        self._notify("Telefone autenticado; controles USB ativos.")
                    else:
                        self._state.apply_mask(self._parse_mask(line))
                if len(buffer) > LINE_LIMIT:
                    raise ProtocolError("Linha JSON excede o limite de 256 bytes.")
                self._state.tick_focus()
        except (OSError, ValueError, TimeoutError, ConnectionError) as exc:
            if not self._stop_event.is_set():
                self._notify(f"Sessão encerrada: {exc}")
        finally:
            self._state.release_all()
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            connection.close()
            with self._client_lock:
                if self._active_socket is connection:
                    self._active_socket = None
                    self._client_thread = None
            if not self._stop_event.is_set():
                self._notify("Teclas liberadas; aguardando uma nova conexão USB.")

    def request_stop(self) -> None:
        """Signal shutdown and release keys immediately; safe to call from Tk."""
        self._stop_event.set()
        listener = self._listener
        if listener is not None:
            try:
                listener.close()
            except OSError:
                pass
        with self._client_lock:
            active = self._active_socket
        if active is not None:
            try:
                active.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                active.close()
            except OSError:
                pass
        self._state.stop()

    def stop(self) -> None:
        """Stop the session, release all keys, and wait for its workers."""
        self.request_stop()
        current = threading.current_thread()
        for worker in (self._client_thread, self._accept_thread):
            if worker is not None and worker is not current:
                worker.join()
        self._notify("Ponte USB parada; todas as teclas foram liberadas.")


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def find_adb_path(
    explicit_path: str | Path | None = None,
    *,
    root: str | Path | None = None,
) -> str:
    """Find ADB from an explicit choice, project tools, or PATH; never download it."""
    if explicit_path:
        candidate = Path(explicit_path).expanduser()
        if candidate.is_file():
            return str(candidate.resolve())
        raise FileNotFoundError(f"O caminho do ADB não é um arquivo: {candidate}")
    bundled = Path(root or project_root()) / "tools" / "platform-tools" / "adb.exe"
    if bundled.is_file():
        return str(bundled.resolve())
    located = shutil.which("adb")
    if located:
        return located
    raise FileNotFoundError("ADB não encontrado. Escolha adb.exe do Android Platform Tools.")


def _run_adb(adb_path: str, arguments: list[str], timeout: float = 8.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [adb_path, *arguments],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        shell=False,
        check=False,
    )


class AdbReverseLease:
    """Own and remove only the reverse mapping successfully created here."""

    def __init__(self, adb_path: str) -> None:
        self.adb_path = adb_path
        self.owns_reverse = False
        self._lock = threading.Lock()

    def cleanup(self) -> str | None:
        with self._lock:
            if not self.owns_reverse:
                return None
            try:
                result = _run_adb(
                    self.adb_path,
                    ["-d", "reverse", "--remove", f"tcp:{PORT}"],
                )
            except (OSError, subprocess.SubprocessError) as exc:
                return f"Não consegui remover o reverse criado por esta sessão: {exc}"
            if result.returncode:
                detail = result.stdout.strip() or f"código {result.returncode}"
                return f"Não consegui remover o reverse criado por esta sessão: {detail}"
            self.owns_reverse = False
            return None


def establish_adb_reverse(adb_path: str) -> tuple[AdbReverseLease, str]:
    """Show USB authorization diagnostics, then create the documented mapping."""
    try:
        devices = _run_adb(adb_path, ["devices", "-l"])
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f"Não consegui executar ADB para listar dispositivos USB: {exc}") from exc
    output = devices.stdout.strip()
    if devices.returncode:
        raise RuntimeError("adb devices -l falhou. Diagnóstico:\n" + (output or "sem saída"))

    states: list[tuple[str, str]] = []
    for line in output.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2 and not line.lstrip().startswith("*"):
            states.append((parts[0], parts[1]))
    unauthorized = [serial for serial, state in states if state == "unauthorized"]
    authorized = [serial for serial, state in states if state == "device"]
    if unauthorized:
        raise RuntimeError(
            "Telefone USB não autorizado no Android. Desbloqueie a tela e aceite a "
            "permissão de depuração USB/RSA.\nDiagnóstico adb devices -l:\n" + output
        )
    if not authorized:
        raise RuntimeError(
            "Nenhum telefone USB autorizado foi encontrado. Confira o cabo, a opção "
            "Depuração USB e o driver; em seguida tente novamente.\n"
            "Diagnóstico adb devices -l:\n" + (output or "nenhum dispositivo listado")
        )

    lease = AdbReverseLease(adb_path)
    try:
        result = _run_adb(
            adb_path,
            ["-d", "reverse", "--no-rebind", f"tcp:{PORT}", f"tcp:{PORT}"],
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f"Não consegui criar o reverse USB do ADB: {exc}\n{output}") from exc
    if result.returncode:
        detail = result.stdout.strip() or f"código {result.returncode}"
        raise RuntimeError(
            "O ADB não criou o reverse USB. Verifique se há exatamente um dispositivo "
            "USB autorizado e se tcp:8765 já está ocupado; um mapeamento preexistente "
            "não foi substituído.\nDiagnóstico adb devices -l:\n"
            + output
            + "\n\nResposta do ADB:\n"
            + detail
        )
    lease.owns_reverse = True
    return lease, output
