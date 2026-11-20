from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from core.database import record_scan

SCAN_TIMEOUT_SECONDS = 4 * 60 * 60
MAX_CAPTURED_LINES = 1200
MAX_DETECTION_LINES = 100


@dataclass(frozen=True)
class EngineInfo:
    engine_id: str
    name: str
    available: bool
    executable: str | None
    detail: str
    version: str = ""
    signature_version: str = ""
    real_time_enabled: bool | None = None


@dataclass(frozen=True)
class ScanResult:
    engine: str
    target: str
    verdict: str
    detections: int
    summary: str
    started_at: str
    finished_at: str
    exit_code: int | None
    output: tuple[str, ...] = ()


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _windows_creation_flags() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


def _version_key(name: str) -> tuple[int, ...]:
    values = re.findall(r"\d+", name)
    return tuple(int(value) for value in values) or (0,)


def find_defender_cli(
    environ: dict[str, str] | None = None,
    which: Callable[[str], str | None] = shutil.which,
) -> str | None:
    env = environ if environ is not None else os.environ
    program_data = Path(env.get("ProgramData", r"C:\ProgramData"))
    platform_root = program_data / "Microsoft" / "Windows Defender" / "Platform"
    if platform_root.is_dir():
        versions = [
            entry
            for entry in platform_root.iterdir()
            if entry.is_dir() and (entry / "MpCmdRun.exe").is_file()
        ]
        if versions:
            versions.sort(key=lambda entry: _version_key(entry.name), reverse=True)
            return str(versions[0] / "MpCmdRun.exe")

    program_files = Path(env.get("ProgramFiles", r"C:\Program Files"))
    fallback = program_files / "Windows Defender" / "MpCmdRun.exe"
    if fallback.is_file():
        return str(fallback)
    return which("MpCmdRun.exe") or which("MpCmdRun")


def _powershell_path(
    environ: dict[str, str] | None = None,
    which: Callable[[str], str | None] = shutil.which,
) -> str | None:
    env = environ if environ is not None else os.environ
    found = which("powershell.exe") or which("powershell")
    if found:
        return found
    system_root = env.get("SystemRoot", r"C:\Windows")
    fallback = Path(system_root) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    return str(fallback) if fallback.is_file() else None


def _defender_status(
    powershell: str | None,
    run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> tuple[str, str, bool | None, str]:
    if not powershell:
        return "", "", None, "Microsoft Defender foi localizado; não foi possível consultar o status do serviço."
    script = (
        "$ErrorActionPreference='Stop'; "
        "$s=Get-MpComputerStatus; "
        "[pscustomobject]@{" 
        "service_enabled=[bool]$s.AMServiceEnabled; "
        "antivirus_enabled=[bool]$s.AntivirusEnabled; "
        "real_time_enabled=[bool]$s.RealTimeProtectionEnabled; "
        "engine_version=[string]$s.AMEngineVersion; "
        "signature_version=[string]$s.AntivirusSignatureVersion" 
        "}|ConvertTo-Json -Compress"
    )
    try:
        result = run(
            [powershell, "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            timeout=20,
            check=False,
            creationflags=_windows_creation_flags(),
        )
        raw = (result.stdout or "").strip().lstrip("\ufeff")
        if result.returncode != 0 or not raw:
            return "", "", None, "Microsoft Defender foi localizado, mas o status não pôde ser consultado."
        import json

        status = json.loads(raw)
        engine_version = str(status.get("engine_version") or "")
        signature_version = str(status.get("signature_version") or "")
        enabled = bool(status.get("antivirus_enabled")) and bool(status.get("service_enabled"))
        realtime = bool(status.get("real_time_enabled"))
        state = "proteção ativa" if enabled and realtime else "serviço detectado; proteção em tempo real não confirmada"
        detail = f"{state}; mecanismo {engine_version or 'versão desconhecida'}; assinaturas {signature_version or 'versão desconhecida'}."
        return engine_version, signature_version, realtime, detail
    except (OSError, subprocess.SubprocessError, ValueError, TypeError):
        return "", "", None, "Microsoft Defender foi localizado, mas o status não pôde ser consultado."


def detect_engine(
    system_name: str | None = None,
    *,
    which: Callable[[str], str | None] = shutil.which,
    environ: dict[str, str] | None = None,
    run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> EngineInfo:
    os_name = system_name or platform.system()
    if os_name.lower() == "windows":
        defender = find_defender_cli(environ, which)
        if defender:
            powershell = _powershell_path(environ, which)
            version, signatures, realtime, detail = _defender_status(powershell, run)
            return EngineInfo(
                engine_id="defender",
                name="Microsoft Defender Antivirus",
                available=True,
                executable=defender,
                detail=detail,
                version=version,
                signature_version=signatures,
                real_time_enabled=realtime,
            )
        clam = which("clamscan.exe") or which("clamscan")
        if clam:
            return _clamav_info(clam, run)
        return EngineInfo(
            "none", "Nenhum mecanismo compatível", False, None,
            "Não foi encontrado Microsoft Defender nem clamscan. Nenhuma varredura será simulada.",
        )

    clam = which("clamscan") or which("clamscan.exe")
    if clam:
        return _clamav_info(clam, run)
    return EngineInfo(
        "none", "Nenhum mecanismo compatível", False, None,
        "ClamAV não está instalado ou não foi encontrado no PATH. Instale-o com as assinaturas oficiais para usar a varredura.",
    )


def _clamav_info(
    executable: str,
    run: Callable[..., subprocess.CompletedProcess],
) -> EngineInfo:
    try:
        result = run(
            [executable, "--version"],
            capture_output=True,
            timeout=15,
            check=False,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=_windows_creation_flags(),
        )
        version = (result.stdout or result.stderr or "").strip().splitlines()
        version_line = version[0][:240] if version else ""
        available = result.returncode == 0
        detail = (
            f"{version_line}. Varredura manual sob demanda; o aplicativo não ativa proteção em tempo real."
            if available and version_line
            else "ClamAV foi localizado, mas o mecanismo não respondeu ao comando --version."
        )
        return EngineInfo("clamav", "ClamAV", available, executable, detail, version=version_line)
    except (OSError, subprocess.SubprocessError):
        return EngineInfo(
            "clamav", "ClamAV", False, executable,
            "ClamAV foi localizado, mas não pôde ser consultado.",
        )


def build_scan_command(engine: EngineInfo, target: str | Path) -> list[str]:
    if not engine.available or not engine.executable:
        raise ValueError("Nenhum mecanismo de antivírus está disponível.")
    target_path = str(Path(target).expanduser().resolve(strict=True))
    if engine.engine_id == "defender":
        # Custom scan com remediation desativada: o app nunca pede para apagar,
        # mover ou colocar arquivos em quarentena.
        return [
            engine.executable,
            "-Scan",
            "-ScanType",
            "3",
            "-File",
            target_path,
            "-DisableRemediation",
        ]
    if engine.engine_id == "clamav":
        # Não adicionar --remove, --move ou --copy. O resultado é apenas relatório.
        return [engine.executable, "--recursive", "--infected", target_path]
    raise ValueError("O mecanismo detectado não é compatível com uma varredura local.")


def _clamav_detection_lines(lines: Sequence[str]) -> list[str]:
    found = []
    for line in lines:
        if re.search(r":\s+.+\s+FOUND\s*$", line, re.IGNORECASE):
            found.append(line.strip())
    return found


def _defender_detection_lines(lines: Sequence[str]) -> list[str]:
    found = []
    for line in lines:
        if re.search(r"\bFOUND\b|ThreatName\s*:|ThreatID\s*:", line, re.IGNORECASE) and not re.search(
            r"\bno\s+(?:threats?|malware|viruses?)\s+found\b", line, re.IGNORECASE
        ):
            found.append(line.strip())
    return found


def classify_scan_output(engine_id: str, return_code: int, lines: Sequence[str]) -> tuple[str, int, str]:
    if engine_id == "clamav":
        detections = _clamav_detection_lines(lines)
        if return_code == 0 and not detections:
            return "clean", 0, "ClamAV concluiu a varredura sem relatar detecções."
        if return_code == 1 or detections:
            return "detections", len(detections) or 1, "ClamAV relatou uma ou mais detecções. Nenhum arquivo foi alterado pelo JoJo-OS."
        return "error", 0, f"ClamAV terminou com código {return_code}; o resultado não pode ser considerado limpo."

    if engine_id == "defender":
        detections = _defender_detection_lines(lines)
        if detections:
            return "detections", len(detections), "O Defender relatou detecção; nenhuma ação de remediação foi solicitada pelo JoJo-OS."
        if return_code == 0:
            return "clean", 0, "O Defender concluiu a varredura sem detecção não remediada no resultado do comando."
        return "inconclusive", 0, f"O Defender terminou com código {return_code}; isso pode indicar detecção não remediada ou erro. Verifique a saída e a Segurança do Windows."

    return "error", 0, "O resultado do mecanismo não pôde ser classificado."


def _terminate_process(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=3)


def scan_target(
    target: str | Path,
    engine: EngineInfo | None = None,
    *,
    on_line: Callable[[str], None] | None = None,
    cancel_event: threading.Event | None = None,
    timeout: float = SCAN_TIMEOUT_SECONDS,
    popen_factory: Callable[..., subprocess.Popen] = subprocess.Popen,
) -> ScanResult:
    started_at = _utc_now()
    target_text = str(target)
    selected_engine = engine or detect_engine()
    if not selected_engine.available:
        finished_at = _utc_now()
        return ScanResult(
            selected_engine.name, target_text, "error", 0,
            selected_engine.detail, started_at, finished_at, None,
        )

    try:
        command = build_scan_command(selected_engine, target)
    except (OSError, ValueError) as exc:
        finished_at = _utc_now()
        return ScanResult(
            selected_engine.name, target_text, "error", 0,
            f"O caminho escolhido não pôde ser aberto: {exc}", started_at, finished_at, None,
        )

    lines: list[str] = []
    output_lock = threading.Lock()
    reader_errors: list[str] = []
    process: subprocess.Popen | None = None
    cancelled = False
    timed_out = False
    try:
        process = popen_factory(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            shell=False,
            creationflags=_windows_creation_flags(),
        )
        if process.stdout is None:
            raise OSError("O mecanismo não disponibilizou uma saída de diagnóstico.")

        def read_output() -> None:
            try:
                for raw_line in process.stdout:
                    line = raw_line.rstrip("\r\n")
                    with output_lock:
                        lines.append(line[:1000])
                        if len(lines) > MAX_CAPTURED_LINES:
                            del lines[: len(lines) - MAX_CAPTURED_LINES]
                    if on_line is not None and line:
                        try:
                            on_line(line[:1000])
                        except (OSError, RuntimeError, ValueError) as exc:
                            reader_errors.append(f"callback de saída: {exc}")
            except (OSError, ValueError) as exc:
                reader_errors.append(str(exc))

        reader = threading.Thread(target=read_output, name="jojo-av-output", daemon=True)
        reader.start()
        start_time = time.monotonic()
        while process.poll() is None:
            if cancel_event is not None and cancel_event.is_set():
                cancelled = True
                _terminate_process(process)
                break
            if time.monotonic() - start_time > timeout:
                timed_out = True
                _terminate_process(process)
                break
            time.sleep(0.1)
        return_code = process.wait(timeout=5)
        reader.join(timeout=5)
        with output_lock:
            captured = tuple(lines[-MAX_CAPTURED_LINES:])

        finished_at = _utc_now()
        if cancelled:
            summary = "Processo do scanner encerrado a pedido. No Microsoft Defender, o serviço pode terminar algum trabalho em segundo plano."
            return ScanResult(selected_engine.name, target_text, "cancelled", 0, summary, started_at, finished_at, return_code, captured)
        if timed_out:
            summary = "A varredura excedeu o limite de quatro horas e foi interrompida. O resultado é incompleto."
            return ScanResult(selected_engine.name, target_text, "error", 0, summary, started_at, finished_at, return_code, captured)

        verdict, detections, summary = classify_scan_output(
            selected_engine.engine_id, return_code, captured
        )
        if reader_errors:
            summary = f"{summary} A leitura do log também falhou; o resultado pode estar incompleto."
            if verdict == "clean":
                verdict = "inconclusive"
        return ScanResult(
            selected_engine.name,
            target_text,
            verdict,
            detections,
            summary,
            started_at,
            finished_at,
            return_code,
            captured,
        )
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        if process is not None:
            _terminate_process(process)
        finished_at = _utc_now()
        return ScanResult(
            selected_engine.name,
            target_text,
            "error",
            0,
            f"O scanner não conseguiu concluir: {exc}",
            started_at,
            finished_at,
            process.returncode if process is not None else None,
            tuple(lines[-MAX_CAPTURED_LINES:]),
        )


def save_scan_result(result: ScanResult, path: str | Path | None = None) -> int:
    return record_scan(
        engine=result.engine,
        target=result.target,
        verdict=result.verdict,
        detections=result.detections,
        summary=result.summary,
        started_at=result.started_at,
        finished_at=result.finished_at,
        exit_code=result.exit_code,
        path=path,
    )
