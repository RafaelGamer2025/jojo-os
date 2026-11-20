from __future__ import annotations

import unittest

from ui.desktop_grid import (
    DesktopGrid,
    choose_nearest_free_slot,
    normalize_positions,
    reflow_positions,
)


class DesktopGridTests(unittest.TestCase):
    def test_dimensions_expose_row_major_slots_without_tk(self):
        grid = DesktopGrid(width=500, height=360)

        self.assertEqual(grid.columns, 3)
        self.assertEqual(grid.rows, 2)
        self.assertEqual(
            grid.slots,
            (
                (50, 50),
                (200, 50),
                (350, 50),
                (50, 200),
                (200, 200),
                (350, 200),
            ),
        )

    def test_minimum_desktop_grid_has_room_for_current_icon_frames(self):
        grid = DesktopGrid(width=700, height=660)

        self.assertGreaterEqual(grid.cell_width, 137 + 12)
        self.assertGreaterEqual(grid.slot_count, 11)

    def test_normalization_snaps_pixels_and_resolves_conflicts_deterministically(self):
        normalized = normalize_positions(
            {
                "b": [53, 57],
                "a": [49, 51],
                "offscreen": [9999, -100],
            },
            width=500,
            height=360,
            order=("a", "b", "offscreen"),
        )

        self.assertEqual(normalized["a"], [50, 50])
        self.assertEqual(normalized["b"], [50, 200])
        self.assertEqual(normalized["offscreen"], [350, 50])
        self.assertEqual(len({tuple(value) for value in normalized.values()}), 3)

    def test_drop_uses_nearest_free_slot_and_origin_when_full(self):
        grid = DesktopGrid(width=450, height=360)
        occupied = list(grid.slots)

        self.assertEqual(
            choose_nearest_free_slot((201, 53), occupied[:-1], [50, 200], grid=grid),
            (200, 200),
        )
        self.assertEqual(choose_nearest_free_slot((250, 250), occupied, [50, 50], grid=grid), (50, 50))

    def test_drop_prefers_a_new_free_slot_over_origin_when_target_cell_differs(self):
        grid = DesktopGrid(width=450, height=360)
        origin = (50, 50)
        free_elsewhere = (200, 200)
        occupied = [
            slot
            for slot in grid.slots
            if slot not in {origin, free_elsewhere}
        ]

        self.assertEqual(
            choose_nearest_free_slot((126, 53), occupied, origin, grid=grid),
            free_elsewhere,
        )

    def test_resize_reflows_into_unique_slots(self):
        positions = {
            "first": [50, 50],
            "second": [175, 50],
            "third": [300, 50],
        }

        resized = reflow_positions(
            positions,
            width=350,
            height=360,
            order=("first", "second", "third"),
        )

        self.assertEqual(resized, {"first": [50, 50], "second": [200, 50], "third": [200, 200]})
        self.assertEqual(len({tuple(value) for value in resized.values()}), len(resized))
        self.assertTrue(
            all(tuple(value) in DesktopGrid(width=350, height=360).slots for value in resized.values())
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
