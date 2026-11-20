"""Lógica local, testável e sem rede dos 20 utilitários da Cleiton Store."""
from __future__ import annotations

import base64
import calendar
import csv
import datetime as dt
import fnmatch
import hashlib
import io
import json
import math
import os
import platform
import re
import secrets
import shutil
import socket
import string
import subprocess
import urllib.parse
import uuid
from pathlib import Path

from core import database
from core.cleiton_store import APP_BY_ID, CLEITON_APP_IDS

MAX_TEXT_BYTES = 1_048_576


def get_tool_seed(app_id: str, database_path: str | Path | None = None) -> str:
    if app_id == "cleiton_notes":
        value = database.get_setting("cleiton_tool_notes", default="", path=database_path)
        return value if isinstance(value, str) else ""
    if app_id == "cleiton_checklist":
        value = database.get_setting("cleiton_tool_checklist", default="", path=database_path)
        return value if isinstance(value, str) else ""
    return ""


def _text_limit(text: str) -> str:
    if not isinstance(text, str):
        raise TypeError("O conteúdo precisa ser texto.")
    if len(text.encode("utf-8")) > MAX_TEXT_BYTES:
        raise ValueError("O conteúdo excede o limite local de 1 MiB.")
    return text


def _system_info() -> str:
    usage = shutil.disk_usage(Path.home())
    gib = 1024 ** 3
    return "\n".join((
        "CLEITON OS // PAINEL DO SISTEMA",
        f"Sistema: {platform.system()} {platform.release()}",
        f"Versão: {platform.version()}",
        f"Arquitetura: {platform.machine() or 'indisponível'}",
        f"Python: {platform.python_version()}",
        f"Processadores lógicos: {os.cpu_count() or 'indisponível'}",
        f"PID do JoJo-OS: {os.getpid()}",
        f"Disco do perfil: {usage.free / gib:.2f} GiB livres de {usage.total / gib:.2f} GiB",
    ))


def _process_list() -> str:
    if os.name == "nt":
        command = ["tasklist", "/FO", "CSV", "/NH"]
    else:
        command = ["ps", "-eo", "pid,comm", "--no-headers"]
    try:
        completed = subprocess.run(
            command, capture_output=True, text=True, errors="replace", timeout=5,
            check=False, shell=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"Não foi possível consultar processos: {type(exc).__name__}."
    if completed.returncode != 0:
        return "O sistema não retornou a lista de processos."
    lines = completed.stdout.splitlines()
    if not lines:
        return "Nenhum processo listado."
    return "PROCESSOS (somente leitura; nenhum será encerrado)\n" + "\n".join(lines[:41]) + ("\n… lista limitada a 40 processos" if len(lines) > 41 else "")


def _unit_convert(text: str) -> str:
    match = re.fullmatch(r"\s*(-?\d+(?:[.,]\d+)?)\s*([a-z]+)\s*(?:->|to)\s*([a-z]+)\s*", text, re.IGNORECASE)
    if not match:
        raise ValueError("Formato inválido. Exemplo: 10 km -> mi")
    value = float(match.group(1).replace(",", "."))
    if not math.isfinite(value):
        raise ValueError("O valor precisa ser um número finito.")
    source, target = match.group(2).lower(), match.group(3).lower()
    dimensions = {
        "distance": {"m": 1.0, "km": 1000.0, "cm": .01, "mi": 1609.344, "ft": .3048},
        "mass": {"g": 1.0, "kg": 1000.0, "lb": 453.59237, "oz": 28.349523125},
    }
    for units in dimensions.values():
        if source in units and target in units:
            return f"{value:g} {source} = {value * units[source] / units[target]:.6g} {target}"
    if source in {"c", "°c"} and target in {"f", "°f"}:
        result = value * 9 / 5 + 32
    elif source in {"f", "°f"} and target in {"c", "°c"}:
        result = (value - 32) * 5 / 9
    else:
        raise ValueError("Unidades incompatíveis. Distância: m/km/cm/mi/ft; massa: g/kg/lb/oz; temperatura: C/F.")
    return f"{value:g} {source} = {result:.6g} {target}"


def _network_info() -> str:
    host = socket.gethostname()
    addresses = sorted({item[4][0] for item in socket.getaddrinfo(host, None, family=socket.AF_INET)})
    addresses = [address for address in addresses if not address.startswith("127.")]
    return "REDE LOCAL (sem varredura)\nHost: " + host + "\nIPv4 local: " + (", ".join(addresses) if addresses else "não disponível")


def _calendar(text: str) -> str:
    raw = text.strip()
    if raw:
        match = re.fullmatch(r"(\d{4})-(\d{1,2})", raw)
        if not match:
            raise ValueError("Use o formato AAAA-MM, por exemplo 2026-11.")
        year, month = int(match.group(1)), int(match.group(2))
    else:
        now = dt.date.today()
        year, month = now.year, now.month
    if not 1 <= month <= 12 or not 1 <= year <= 9999:
        raise ValueError("Ano ou mês fora do intervalo.")
    return calendar.month(year, month)


def _color(text: str) -> str:
    raw = text.strip()
    if raw.startswith("#"):
        value = raw[1:]
        if not re.fullmatch(r"[0-9a-fA-F]{6}", value):
            raise ValueError("Cor HEX deve ter formato #RRGGBB.")
        red, green, blue = (int(value[index:index + 2], 16) for index in (0, 2, 4))
        return f"#{value.upper()}\nRGB({red}, {green}, {blue})"
    parts = [part.strip() for part in raw.split(",")]
    if len(parts) != 3:
        raise ValueError("Digite #RRGGBB ou três números separados por vírgula.")
    try:
        red, green, blue = (int(part) for part in parts)
    except ValueError as exc:
        raise ValueError("Os valores RGB devem ser inteiros entre 0 e 255.") from exc
    if any(not 0 <= channel <= 255 for channel in (red, green, blue)):
        raise ValueError("Os valores RGB devem estar entre 0 e 255.")
    return f"#{red:02X}{green:02X}{blue:02X}\nRGB({red}, {green}, {blue})"


def _timestamp(text: str) -> str:
    raw = text.strip()
    if not raw:
        raise ValueError("Digite um timestamp Unix ou uma data ISO 8601.")
    try:
        value = float(raw)
        moment = dt.datetime.fromtimestamp(value, tz=dt.UTC)
    except ValueError:
        try:
            moment = dt.datetime.fromisoformat(raw)
        except ValueError as exc:
            raise ValueError("Data inválida. Use timestamp ou ISO 8601.") from exc
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=dt.UTC)
        else:
            moment = moment.astimezone(dt.UTC)
    return f"UTC: {moment.isoformat()}\nUnix: {moment.timestamp():.3f}"


def execute_cleiton_tool(
    app_id: str,
    text: str = "",
    *,
    file_path: str | Path | None = None,
    database_path: str | Path | None = None,
) -> str:
    """Executa ferramenta da whitelist local; não aceita comandos arbitrários."""
    if not isinstance(app_id, str) or app_id not in CLEITON_APP_IDS:
        raise ValueError(f"Ferramenta Cleiton OS não permitida: {app_id!r}.")
    text = _text_limit(text)

    if app_id == "cleiton_system_info":
        return _system_info()
    if app_id == "cleiton_processes":
        return _process_list()
    if app_id in {"cleiton_notes", "cleiton_checklist"}:
        key = "cleiton_tool_notes" if app_id == "cleiton_notes" else "cleiton_tool_checklist"
        database.set_setting(key, text, path=database_path)
        return f"Salvo localmente ({len(text)} caracteres)."
    if app_id == "cleiton_unit_converter":
        return _unit_convert(text)
    if app_id == "cleiton_password_generator":
        raw = text.strip()
        length = 20 if not raw else int(raw)
        if not 8 <= length <= 128:
            raise ValueError("O tamanho deve ser entre 8 e 128 caracteres.")
        alphabet = string.ascii_letters + string.digits + "!@#$%&*+-_?"
        return "Senha gerada localmente:\n" + "".join(secrets.choice(alphabet) for _ in range(length))
    if app_id == "cleiton_sha256":
        if file_path is None:
            raise ValueError("Escolha um arquivo para calcular o SHA-256.")
        target = Path(file_path)
        if target.is_symlink() or not target.is_file():
            raise ValueError("O caminho escolhido não é um arquivo regular.")
        digest = hashlib.sha256()
        with target.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return f"SHA-256  {target.name}\n{digest.hexdigest()}"
    if app_id == "cleiton_storage":
        usage = shutil.disk_usage(Path.home())
        gib = 1024 ** 3
        return f"Pasta analisada: {Path.home()}\nTotal: {usage.total / gib:.2f} GiB\nUsado: {usage.used / gib:.2f} GiB\nLivre: {usage.free / gib:.2f} GiB"
    if app_id == "cleiton_network":
        return _network_info()
    if app_id == "cleiton_json_formatter":
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"JSON inválido na linha {exc.lineno}, coluna {exc.colno}: {exc.msg}") from exc
        return json.dumps(parsed, ensure_ascii=False, indent=2, sort_keys=False)
    if app_id == "cleiton_base64":
        mode, separator, payload = text.partition("\n")
        if not separator or mode.strip().lower() not in {"encode", "decode"}:
            raise ValueError("A primeira linha deve ser encode ou decode, seguida pelo conteúdo.")
        try:
            if mode.strip().lower() == "encode":
                return base64.b64encode(payload.encode("utf-8")).decode("ascii")
            return base64.b64decode(payload.encode("ascii"), validate=True).decode("utf-8")
        except (ValueError, UnicodeError) as exc:
            raise ValueError("Base64 inválido ou conteúdo decodificado não é UTF-8 válido.") from exc
    if app_id == "cleiton_text_stats":
        words = re.findall(r"\S+", text)
        paragraphs = [part for part in re.split(r"\n\s*\n", text) if part.strip()]
        return f"Caracteres: {len(text)}\nSem espaços: {sum(not char.isspace() for char in text)}\nPalavras: {len(words)}\nLinhas: {len(text.splitlines())}\nParágrafos: {len(paragraphs)}"
    if app_id == "cleiton_calendar":
        return _calendar(text)
    if app_id == "cleiton_color_converter":
        return _color(text)
    if app_id == "cleiton_percentage":
        parts = re.split(r"[,;\s]+", text.strip())
        if len(parts) != 2:
            raise ValueError("Digite valor e porcentagem, por exemplo: 250, 12.5")
        try:
            amount, percent = (float(item.replace(",", ".")) for item in parts)
        except ValueError as exc:
            raise ValueError("Valor ou porcentagem inválido.") from exc
        if not math.isfinite(amount) or not math.isfinite(percent):
            raise ValueError("Valor e porcentagem devem ser finitos.")
        return f"{percent:g}% de {amount:g} = {amount * percent / 100:g}"
    if app_id == "cleiton_line_filter":
        pattern, separator, body = text.partition("\n")
        if not separator or not pattern:
            raise ValueError("Digite o padrão glob na primeira linha e o texto nas próximas.")
        if len(pattern) > 256:
            raise ValueError("Padrão limitado a 256 caracteres.")
        matched = [line for line in body.splitlines() if fnmatch.fnmatchcase(line, pattern)]
        return "\n".join(matched) if matched else "Nenhuma linha corresponde ao padrão."
    if app_id == "cleiton_timestamp":
        try:
            return _timestamp(text)
        except (OverflowError, OSError) as exc:
            raise ValueError("Timestamp fora do intervalo suportado.") from exc
    if app_id == "cleiton_csv_analyzer":
        reader = csv.reader(io.StringIO(text, newline=""))
        try:
            rows = list(reader)
        except csv.Error as exc:
            raise ValueError(f"CSV inválido: {exc}") from exc
        if not rows:
            return "CSV vazio."
        width = max((len(row) for row in rows), default=0)
        header = ", ".join(rows[0]) if rows else ""
        return f"Linhas de dados: {max(0, len(rows) - 1)}\nColunas máximas: {width}\nCabeçalho: {header}"
    if app_id == "cleiton_url_codec":
        mode, separator, payload = text.partition("\n")
        if not separator or mode.strip().lower() not in {"encode", "decode"}:
            raise ValueError("A primeira linha deve ser encode ou decode, seguida pelo conteúdo.")
        if mode.strip().lower() == "encode":
            return urllib.parse.quote(payload, safe="")
        return urllib.parse.unquote(payload, errors="strict")
    if app_id == "cleiton_uuid":
        raw = text.strip()
        count = 1 if not raw else int(raw)
        if not 1 <= count <= 20:
            raise ValueError("A quantidade deve ser de 1 a 20.")
        return "\n".join(str(uuid.uuid4()) for _ in range(count))
    raise RuntimeError("Definição do aplicativo sem implementação.")


if set(APP_BY_ID) != set(CLEITON_APP_IDS):
    raise RuntimeError("O catálogo Cleiton OS contém uma definição inconsistente.")
