"""Catálogo isolado de utilitários disponíveis somente no perfil Cleiton OS."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

from core import database

CLEITON_STORE_SETTING_KEY: Final[str] = "cleiton_store_installed"
CLEITON_PROFILE: Final[str] = "CLEITON"


@dataclass(frozen=True)
class CleitonApp:
    app_id: str
    name: str
    description: str
    icon: str
    input_hint: str
    action_label: str = "EXECUTAR"


CLEITON_APPS: Final[tuple[CleitonApp, ...]] = (
    CleitonApp("cleiton_system_info", "Painel do Sistema", "Resumo local do Python, sistema, arquitetura, CPU e armazenamento.", "▣", "Não precisa digitar nada.", "ATUALIZAR PAINEL"),
    CleitonApp("cleiton_processes", "Processos Ativos", "Lista somente leitura dos processos atuais; não encerra processos.", "◉", "Não precisa digitar nada.", "ATUALIZAR LISTA"),
    CleitonApp("cleiton_notes", "Notas Rápidas", "Edite e salve uma nota local no banco do JoJo-OS.", "✎", "Digite sua nota. Executar salva o conteúdo." , "SALVAR NOTA"),
    CleitonApp("cleiton_checklist", "Lista de Tarefas", "Guarde uma lista local de tarefas, uma por linha.", "☷", "Uma tarefa por linha. Executar substitui a lista salva.", "SALVAR LISTA"),
    CleitonApp("cleiton_unit_converter", "Conversor de Unidades", "Converte distância, massa e temperatura sem serviços externos.", "⇄", "Exemplos: 10 km -> mi | 5 lb -> kg | 32 F -> C"),
    CleitonApp("cleiton_password_generator", "Gerador de Senhas", "Gera senha local com o gerador criptográfico do sistema.", "◆", "Digite um tamanho entre 8 e 128 (padrão: 20)."),
    CleitonApp("cleiton_sha256", "Verificador SHA-256", "Calcula SHA-256 de um arquivo escolhido por você.", "#", "Escolha um arquivo no botão abaixo.", "CALCULAR HASH"),
    CleitonApp("cleiton_storage", "Analisador de Armazenamento", "Mostra uso e espaço livre do disco do perfil atual.", "▤", "Não precisa digitar nada.", "ANALISAR DISCO"),
    CleitonApp("cleiton_network", "Rede Local", "Mostra hostname e endereços locais obtidos sem varredura de rede.", "⌁", "Não precisa digitar nada.", "ATUALIZAR REDE"),
    CleitonApp("cleiton_json_formatter", "Formatador JSON", "Valida e formata JSON localmente.", "{}", "Cole um JSON válido para formatar."),
    CleitonApp("cleiton_base64", "Codificador Base64", "Codifica texto UTF-8 ou decodifica Base64.", "B64", "Primeira linha: encode ou decode. Depois, o texto."),
    CleitonApp("cleiton_text_stats", "Analisador de Texto", "Conta caracteres, palavras, linhas e parágrafos.", "¶", "Cole ou digite o texto para analisar."),
    CleitonApp("cleiton_calendar", "Calendário Mensal", "Exibe o calendário do mês atual ou de um mês escolhido.", "▦", "Use AAAA-MM ou deixe vazio para o mês atual."),
    CleitonApp("cleiton_color_converter", "Conversor de Cores", "Converte hexadecimal para RGB e RGB para hexadecimal.", "◈", "Exemplos: #26A69A ou 38,166,154"),
    CleitonApp("cleiton_percentage", "Calculadora de Porcentagem", "Calcula uma porcentagem sobre um valor.", "%", "Digite valor, porcentagem. Exemplo: 250, 12.5"),
    CleitonApp("cleiton_line_filter", "Filtro de Linhas", "Filtra linhas por padrão glob simples (* e ?), sem regex executável.", "≋", "Primeira linha: padrão. Próximas linhas: texto. Exemplo: erro*"),
    CleitonApp("cleiton_timestamp", "Conversor de Data/Hora", "Converte timestamp Unix e data ISO em UTC.", "◷", "Digite timestamp Unix ou ISO 8601."),
    CleitonApp("cleiton_csv_analyzer", "Analisador CSV", "Resume cabeçalho, linhas e colunas de um CSV colado.", "▦", "Cole o conteúdo CSV (máximo de 1 MiB)."),
    CleitonApp("cleiton_url_codec", "Codificador URL", "Codifica ou decodifica texto de URL localmente.", "↗", "Primeira linha: encode ou decode. Depois, o texto."),
    CleitonApp("cleiton_uuid", "Gerador de UUID", "Gera identificadores UUID aleatórios sem rede.", "◇", "Digite a quantidade desejada (1 a 20, padrão: 1)."),
)

APP_BY_ID: Final[dict[str, CleitonApp]] = {app.app_id: app for app in CLEITON_APPS}
CLEITON_APP_IDS: Final[frozenset[str]] = frozenset(APP_BY_ID)


def is_cleiton_profile(skin_mode: str) -> bool:
    """True somente no perfil explícito Cleiton; nunca infere por tema/cor."""
    return isinstance(skin_mode, str) and skin_mode.upper() == CLEITON_PROFILE


def visible_cleiton_app_ids(skin_mode: str, installed_ids: set[str] | frozenset[str]) -> set[str]:
    """Filtra os apps do perfil; instalações continuam guardadas ao trocar de skin."""
    if not is_cleiton_profile(skin_mode):
        return set()
    return set(installed_ids) & CLEITON_APP_IDS


def _read_installed(path: str | Path | None = None) -> set[str]:
    raw = database.get_setting(CLEITON_STORE_SETTING_KEY, default=[], path=path)
    if raw is None:
        return set()
    if not isinstance(raw, list):
        raise TypeError("O estado da Cleiton Store está malformado.")
    return {item for item in raw if isinstance(item, str) and item in CLEITON_APP_IDS}


def get_installed_cleiton_apps(path: str | Path | None = None) -> set[str]:
    return _read_installed(path)


def install_cleiton_app(app_id: str, path: str | Path | None = None) -> set[str]:
    if not isinstance(app_id, str) or app_id not in CLEITON_APP_IDS:
        raise ValueError(f"Aplicativo Cleiton OS não permitido: {app_id!r}.")
    installed = _read_installed(path)
    if app_id not in installed:
        installed.add(app_id)
        database.set_setting(CLEITON_STORE_SETTING_KEY, sorted(installed), path=path)
    return installed


def uninstall_cleiton_app(app_id: str, path: str | Path | None = None) -> set[str]:
    if not isinstance(app_id, str) or app_id not in CLEITON_APP_IDS:
        raise ValueError(f"Aplicativo Cleiton OS não permitido: {app_id!r}.")
    installed = _read_installed(path)
    if app_id in installed:
        installed.remove(app_id)
        database.set_setting(CLEITON_STORE_SETTING_KEY, sorted(installed), path=path)
    return installed
