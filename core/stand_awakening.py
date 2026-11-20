"""Catálogo de Stands de Stardust Crusaders para sorteio e apresentação."""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Final, Literal, Protocol

TAROT: Final[str] = "TAROT"
EGYPTIAN: Final[str] = "EGYPTIAN"
OTHER: Final[str] = "OTHER"

StandGroup = Literal["TAROT", "EGYPTIAN", "OTHER"]


@dataclass(frozen=True, slots=True)
class StandCard:
    """Metadados imutáveis de um Stand do catálogo."""

    name: str
    arcana: str | None
    group: StandGroup
    color: str
    symbol: str
    description: str


ALL_STANDS: Final[tuple[StandCard, ...]] = (
    StandCard(
        "Star Platinum",
        "The Star",
        TAROT,
        "#4B67A1",
        "star",
        "Um guardião de força e precisão extraordinárias; seu auge desperta a técnica Star Platinum: The World.",
    ),
    StandCard(
        "Magician's Red",
        "The Magician",
        TAROT,
        "#D74932",
        "flame",
        "Um Stand de fogo intenso associado à criatividade do Mago.",
    ),
    StandCard(
        "Hermit Purple",
        "The Hermit",
        TAROT,
        "#76549B",
        "hermit",
        "Vinhas roxas que representam intuição e busca por conhecimento.",
    ),
    StandCard(
        "Hierophant Green",
        "The Hierophant",
        TAROT,
        "#3E9B68",
        "emerald",
        "Um Stand verde de longo alcance associado ao Hierofante.",
    ),
    StandCard(
        "Silver Chariot",
        "The Chariot",
        TAROT,
        "#B8C2D1",
        "sword",
        "Um espadachim veloz, guiado pela determinação do Carro.",
    ),
    StandCard(
        "The Fool",
        "The Fool",
        TAROT,
        "#C9A66B",
        "fool",
        "Um companheiro versátil cuja forma lembra areia compactada.",
    ),
    StandCard(
        "The World",
        "The World",
        TAROT,
        "#D8B548",
        "world",
        "Um Stand poderoso que encarna domínio e ambição sem limites.",
    ),
    StandCard(
        "Tower of Gray",
        "The Tower",
        TAROT,
        "#73818C",
        "tower",
        "Um inseto veloz e perigoso ligado à carta da Torre.",
    ),
    StandCard(
        "Dark Blue Moon",
        "The Moon",
        TAROT,
        "#315B83",
        "moon",
        "Um Stand aquático que luta com vantagem sob as ondas.",
    ),
    StandCard(
        "Strength",
        "Strength",
        TAROT,
        "#A67C52",
        "strength",
        "Uma presença de força bruta associada à carta da Força.",
    ),
    StandCard(
        "Ebony Devil",
        "The Devil",
        TAROT,
        "#39323D",
        "devil",
        "Uma figura vingativa que se fortalece com ressentimento.",
    ),
    StandCard(
        "Yellow Temperance",
        "Temperance",
        TAROT,
        "#D6C83F",
        "temperance",
        "Uma substância amarela adaptável que imita e envolve alvos.",
    ),
    StandCard(
        "Hanged Man",
        "The Hanged Man",
        TAROT,
        "#8C658F",
        "hand",
        "Um Stand que se move por reflexos e superfícies espelhadas.",
    ),
    StandCard(
        "Emperor",
        "The Emperor",
        TAROT,
        "#A83B3B",
        "emperor",
        "Uma arma de fogo sobrenatural cujas balas seguem o alvo.",
    ),
    StandCard(
        "Empress",
        "The Empress",
        TAROT,
        "#B14C71",
        "empress",
        "Uma ameaça parasítica que cresce junto ao corpo da vítima.",
    ),
    StandCard(
        "Wheel of Fortune",
        "Wheel of Fortune",
        TAROT,
        "#59666F",
        "wheel",
        "Um automóvel transformado em Stand, associado à Roda da Fortuna.",
    ),
    StandCard(
        "Justice",
        "Justice",
        TAROT,
        "#A7A89B",
        "justice",
        "Uma névoa capaz de manipular ferimentos e movimentos alheios.",
    ),
    StandCard(
        "Lovers",
        "The Lovers",
        TAROT,
        "#D47C9C",
        "lovers",
        "Um Stand diminuto que pode invadir o sistema nervoso.",
    ),
    StandCard(
        "Sun",
        "The Sun",
        TAROT,
        "#F2A52B",
        "sun",
        "Um sol artificial que projeta calor intenso sobre seus alvos.",
    ),
    StandCard(
        "Death Thirteen",
        "Death",
        TAROT,
        "#514A62",
        "death",
        "Um Stand ligado a sonhos e à carta da Morte.",
    ),
    StandCard(
        "Judgement",
        "Judgement",
        TAROT,
        "#8D795F",
        "judgement",
        "Um Stand que molda desejos em figuras feitas de terra.",
    ),
    StandCard(
        "High Priestess",
        "The High Priestess",
        TAROT,
        "#4F8F91",
        "priestess",
        "Uma entidade mineral que pode se fundir a materiais ao redor.",
    ),
    StandCard(
        "Geb",
        None,
        EGYPTIAN,
        "#7B8F45",
        "egyptian",
        "Um Stand egípcio associado à terra e ao controle da água.",
    ),
    StandCard(
        "Khnum",
        None,
        EGYPTIAN,
        "#B77B45",
        "egyptian",
        "Um Stand egípcio com habilidade de alterar a própria aparência.",
    ),
    StandCard(
        "Tohth",
        None,
        EGYPTIAN,
        "#55A6A1",
        "bird",
        "Um Stand egípcio que prevê acontecimentos em forma de quadrinhos.",
    ),
    StandCard(
        "Anubis",
        None,
        EGYPTIAN,
        "#62646B",
        "anubis",
        "Uma espada senciente que aprende com os oponentes que enfrenta.",
    ),
    StandCard(
        "Bastet",
        None,
        EGYPTIAN,
        "#D0A44D",
        "cat",
        "Um Stand egípcio que magnetiza quem toca sua tomada.",
    ),
    StandCard(
        "Sethan",
        None,
        EGYPTIAN,
        "#4A3D52",
        "shadow",
        "Uma sombra egípcia capaz de rejuvenescer quem alcança.",
    ),
    StandCard(
        "Osiris",
        None,
        EGYPTIAN,
        "#6985A8",
        "egyptian",
        "Um Stand egípcio que aposta as almas de quem perde seus jogos.",
    ),
    StandCard(
        "Horus",
        None,
        EGYPTIAN,
        "#8FC5D5",
        "bird",
        "Um Stand de gelo associado ao deus egípcio Horus.",
    ),
    StandCard(
        "Atum",
        None,
        EGYPTIAN,
        "#8C704C",
        "eye",
        "Um Stand egípcio que lê as almas por meio de jogos e perguntas.",
    ),
    StandCard(
        "Cream",
        None,
        OTHER,
        "#D9D5D0",
        "void",
        "Um Stand que apaga tudo o que é engolido por seu vazio.",
    ),
    StandCard(
        "Tenore Sax",
        None,
        OTHER,
        "#856CA6",
        "illusion",
        "Um Stand que cria ilusões em uma mansão labiríntica.",
    ),
)

_STANDS_BY_NAME: Final[dict[str, StandCard]] = {
    stand.name: stand for stand in ALL_STANDS
}


class _ChoiceRng(Protocol):
    def choice(self, sequence: tuple[StandCard, ...], /) -> StandCard: ...


def get_stand(name: str) -> StandCard:
    """Retorna o cartão pelo nome ou rejeita um nome desconhecido."""
    try:
        return _STANDS_BY_NAME[name]
    except (KeyError, TypeError) as error:
        raise ValueError(f"Stand inexistente: {name!r}.") from error


def choose_random_stand(rng: _ChoiceRng | None = None) -> StandCard:
    """Escolhe um cartão; ``rng`` opcionalmente fornece um método ``choice``."""
    if rng is None:
        return random.choice(ALL_STANDS)
    return rng.choice(ALL_STANDS)
