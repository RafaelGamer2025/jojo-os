"""Catálogo interno de aplicativos opcionais do JoJo-OS.

Este módulo mantém somente o estado de instalação dos aplicativos opcionais na
configuração SQLite já existente. Ele não cria ícones nem abre janelas; a
camada de interface pode usar as funções abaixo para atualizar o controlador.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

from core import database

OPTIONAL_APPS_SETTING_KEY: Final[str] = "optional_apps"
"""Chave da configuração que contém uma lista JSON de IDs instalados."""

OPTIONAL_APP_ID: Final[str] = "restaurant_tonio"
"""ID estável do aplicativo fictício Restaurante do Tonio Trussardi."""

# Aliases descritivos evitam espalhar o literal pelo restante do aplicativo.
RESTAURANTE_TONIO_APP_ID: Final[str] = OPTIONAL_APP_ID
APP_RESTAURANTE_TONIO: Final[str] = OPTIONAL_APP_ID
APP_ID_RESTAURANTE_TONIO_TRUSSARDI: Final[str] = OPTIONAL_APP_ID


@dataclass(frozen=True)
class AppDefinition:
    """Metadados imutáveis de um aplicativo disponível no catálogo."""

    app_id: str
    nome: str
    descricao: str


APP_DEFINITIONS: Final[dict[str, AppDefinition]] = {
    OPTIONAL_APP_ID: AppDefinition(
        app_id=OPTIONAL_APP_ID,
        nome="Restaurante do Tonio Trussardi",
        descricao="Cardápio fictício com sugestões locais e aleatórias.",
    ),
}

# A whitelist é derivada dos metadados, evitando que um ID sem definição seja
# aceito por engano.
ALLOWED_APP_IDS: Final[frozenset[str]] = frozenset(APP_DEFINITIONS)
OPTIONAL_APP_IDS: Final[frozenset[str]] = ALLOWED_APP_IDS
APP_CATALOG: Final[tuple[AppDefinition, ...]] = tuple(APP_DEFINITIONS.values())


def _validate_app_id(app_id: str) -> str:
    if not isinstance(app_id, str) or app_id not in ALLOWED_APP_IDS:
        raise ValueError(f"ID de aplicativo opcional não permitido: {app_id!r}.")
    return app_id


def _read_installed_ids(path: str | Path | None = None) -> set[str]:
    raw_value = database.get_setting(
        OPTIONAL_APPS_SETTING_KEY,
        default=[],
        path=path,
    )
    if raw_value is None:
        return set()
    if not isinstance(raw_value, list):
        raise TypeError("O estado de aplicativos opcionais está malformado.")

    # Apenas IDs da whitelist podem virar estado ativo. Valores desconhecidos
    # eventualmente deixados por uma versão anterior não são executados.
    return {
        item for item in raw_value if isinstance(item, str) and item in ALLOWED_APP_IDS
    }


def _save_installed_ids(app_ids: set[str], path: str | Path | None = None) -> None:
    database.set_setting(
        OPTIONAL_APPS_SETTING_KEY,
        sorted(app_ids),
        path=path,
    )


def listar_apps_disponiveis() -> tuple[AppDefinition, ...]:
    """Retorna os aplicativos fictícios disponíveis na whitelist."""

    return APP_CATALOG


def get_available_apps() -> tuple[AppDefinition, ...]:
    """Alias em inglês para integração com controladores existentes."""

    return listar_apps_disponiveis()


def get_installed_optional_apps(path: str | Path | None = None) -> set[str]:
    """Retorna os IDs opcionais instalados, com estado vazio por padrão."""

    return _read_installed_ids(path)


def install_optional_app(
    app_id: str, path: str | Path | None = None
) -> set[str]:
    """Instala ``app_id`` e retorna o conjunto atualizado de IDs.

    A operação é idempotente: instalar novamente um aplicativo já instalado
    não regrava a configuração, mas devolve o mesmo conjunto de IDs.
    """

    _validate_app_id(app_id)
    installed_ids = _read_installed_ids(path)
    if app_id not in installed_ids:
        installed_ids.add(app_id)
        _save_installed_ids(installed_ids, path)
    return installed_ids


def uninstall_optional_app(
    app_id: str, path: str | Path | None = None
) -> set[str]:
    """Remove somente ``app_id`` e retorna o conjunto atualizado de IDs."""

    _validate_app_id(app_id)
    installed_ids = _read_installed_ids(path)
    if app_id in installed_ids:
        installed_ids.remove(app_id)
        _save_installed_ids(installed_ids, path)
    return installed_ids


# Funções em português e aliases legados mantêm a API fácil de descobrir sem
# alterar o contrato principal usado pelo controlador.
def listar_apps_instalados(path: str | Path | None = None) -> set[str]:
    """Alias em português para consulta do estado de instalação."""

    return get_installed_optional_apps(path)


def get_installed_apps(path: str | Path | None = None) -> set[str]:
    """Alias descritivo para consulta do estado de instalação."""

    return get_installed_optional_apps(path)


def list_installed_apps(path: str | Path | None = None) -> set[str]:
    """Alias em inglês para consulta do estado de instalação."""

    return get_installed_optional_apps(path)


def app_instalado(app_id: str, path: str | Path | None = None) -> bool:
    """Indica se ``app_id`` está instalado; IDs desconhecidos são rejeitados."""

    _validate_app_id(app_id)
    return app_id in _read_installed_ids(path)


def is_app_installed(app_id: str, path: str | Path | None = None) -> bool:
    """Alias em inglês para consulta de um aplicativo opcional."""

    return app_instalado(app_id, path)


def instalar_app(app_id: str, path: str | Path | None = None) -> set[str]:
    """Alias em português para instalação idempotente."""

    return install_optional_app(app_id, path)


def install_app(app_id: str, path: str | Path | None = None) -> set[str]:
    """Alias em inglês para instalação idempotente."""

    return install_optional_app(app_id, path)


def desinstalar_app(app_id: str, path: str | Path | None = None) -> set[str]:
    """Alias em português para desinstalação segura."""

    return uninstall_optional_app(app_id, path)


def uninstall_app(app_id: str, path: str | Path | None = None) -> set[str]:
    """Alias em inglês para desinstalação segura."""

    return uninstall_optional_app(app_id, path)
