from __future__ import annotations

from pathlib import Path

from core.security import DATA_DIR

WORKSPACE_DIR = DATA_DIR / "workspace"


def ensure_workspace(root: str | Path = WORKSPACE_DIR) -> Path:
    workspace = Path(root).resolve(strict=False)
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


def resolve_workspace_path(root: str | Path, target: str | Path = ".") -> Path:
    """Resolve um caminho e rejeita saída do sandbox, inclusive por symlink."""
    workspace = Path(root).resolve(strict=False)
    candidate = Path(target)
    if not candidate.is_absolute():
        candidate = workspace / candidate
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(workspace)
    except ValueError as exc:
        raise ValueError("O caminho precisa permanecer dentro da pasta de trabalho.") from exc
    return resolved


def validate_filename(name: str, *, max_length: int = 120) -> str:
    cleaned = name.strip()
    if not cleaned or cleaned in {".", ".."}:
        raise ValueError("Informe um nome de arquivo válido.")
    if len(cleaned) > max_length:
        raise ValueError(f"O nome deve ter até {max_length} caracteres.")
    if "/" in cleaned or "\\" in cleaned or "\x00" in cleaned:
        raise ValueError("Use somente um nome, sem caminho ou separadores.")
    if cleaned.endswith((".", " ")):
        raise ValueError("O nome não pode terminar com ponto ou espaço.")
    reserved = {"CON", "PRN", "AUX", "NUL"} | {f"COM{i}" for i in range(1, 10)} | {f"LPT{i}" for i in range(1, 10)}
    if cleaned.split(".", 1)[0].upper() in reserved:
        raise ValueError("Esse nome é reservado pelo Windows.")
    return cleaned
