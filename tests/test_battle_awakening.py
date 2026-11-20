from __future__ import annotations

import unittest

from core.battle_system import STANDS, criar_lutador
from core.stand_awakening import ALL_STANDS


class AwakenedStandBattleTests(unittest.TestCase):
    def test_every_random_stand_is_supported_by_battle_system(self):
        for card in ALL_STANDS:
            with self.subTest(stand=card.name):
                self.assertIn(card.name, STANDS)
                self.assertEqual(criar_lutador(card.name)["stand"], card.name)

    def test_existing_special_stand_abilities_are_preserved(self):
        self.assertTrue(STANDS["The World"]["time_stop"])
        self.assertGreater(STANDS["Star Platinum"]["crit"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
