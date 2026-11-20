from __future__ import annotations

import re
import unittest
from dataclasses import FrozenInstanceError

from core.stand_awakening import (
    ALL_STANDS,
    EGYPTIAN,
    OTHER,
    TAROT,
    StandCard,
    choose_random_stand,
    get_stand,
)

EXPECTED_NAMES = (
    "Star Platinum",
    "Magician's Red",
    "Hermit Purple",
    "Hierophant Green",
    "Silver Chariot",
    "The Fool",
    "The World",
    "Tower of Gray",
    "Dark Blue Moon",
    "Strength",
    "Ebony Devil",
    "Yellow Temperance",
    "Hanged Man",
    "Emperor",
    "Empress",
    "Wheel of Fortune",
    "Justice",
    "Lovers",
    "Sun",
    "Death Thirteen",
    "Judgement",
    "High Priestess",
    "Geb",
    "Khnum",
    "Tohth",
    "Anubis",
    "Bastet",
    "Sethan",
    "Osiris",
    "Horus",
    "Atum",
    "Cream",
    "Tenore Sax",
)

ALLOWED_SYMBOLS = {
    "star",
    "flame",
    "hermit",
    "emerald",
    "sword",
    "fool",
    "world",
    "tower",
    "moon",
    "strength",
    "devil",
    "temperance",
    "hand",
    "emperor",
    "empress",
    "wheel",
    "justice",
    "lovers",
    "sun",
    "death",
    "judgement",
    "priestess",
    "egyptian",
    "anubis",
    "cat",
    "shadow",
    "bird",
    "eye",
    "void",
    "illusion",
}


class _LastStandRng:
    def __init__(self) -> None:
        self.seen: tuple[StandCard, ...] | None = None

    def choice(self, sequence: tuple[StandCard, ...]) -> StandCard:
        self.seen = sequence
        return sequence[-1]


class StandAwakeningTests(unittest.TestCase):
    def test_catalog_has_33_unique_names_in_requested_order(self) -> None:
        self.assertIsInstance(ALL_STANDS, tuple)
        names = tuple(stand.name for stand in ALL_STANDS)
        self.assertEqual(len(ALL_STANDS), 33)
        self.assertEqual(len(set(names)), len(names))
        self.assertEqual(names, EXPECTED_NAMES)

    def test_all_catalog_data_is_valid(self) -> None:
        for stand in ALL_STANDS:
            with self.subTest(stand=stand.name):
                self.assertIsInstance(stand, StandCard)
                self.assertTrue(stand.name)
                self.assertIn(stand.group, {TAROT, EGYPTIAN, OTHER})
                self.assertRegex(stand.color, re.compile(r"^#[0-9A-Fa-f]{6}$"))
                self.assertIn(stand.symbol, ALLOWED_SYMBOLS)
                self.assertTrue(stand.description)
                if stand.group == TAROT:
                    self.assertIsInstance(stand.arcana, str)
                    self.assertTrue(stand.arcana)
                else:
                    self.assertIsNone(stand.arcana)

    def test_cards_are_immutable(self) -> None:
        with self.assertRaises(FrozenInstanceError):
            ALL_STANDS[0].name = "Altered"  # type: ignore[misc]

    def test_get_stand_returns_matching_card(self) -> None:
        for stand in ALL_STANDS:
            with self.subTest(stand=stand.name):
                self.assertIs(get_stand(stand.name), stand)

    def test_unknown_names_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            get_stand("Stand inexistente")
        with self.assertRaises(ValueError):
            get_stand(None)  # type: ignore[arg-type]

    def test_random_choice_uses_injected_rng(self) -> None:
        rng = _LastStandRng()

        selected = choose_random_stand(rng)

        self.assertIs(rng.seen, ALL_STANDS)
        self.assertIs(selected, ALL_STANDS[-1])


if __name__ == "__main__":
    unittest.main(verbosity=2)
