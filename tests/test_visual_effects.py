from __future__ import annotations

import re
import unittest

from PIL import Image

from ui.visual_effects import (
    expanding_circle_radii,
    expanding_circle_radius,
    invert_rgb,
    maximum_circle_radius,
    negative_circle_frame,
    psychedelic_palette,
)


class VisualEffectHelperTests(unittest.TestCase):
    def test_invert_rgb_complements_each_channel(self):
        self.assertEqual(invert_rgb((0, 127, 255)), (255, 128, 0))

    def test_invert_rgb_rejects_invalid_channels(self):
        for rgb in ((-1, 0, 0), (256, 0, 0), (True, 0, 0), (1, 2)):
            with self.subTest(rgb=rgb), self.assertRaises(ValueError):
                invert_rgb(rgb)

    def test_rings_are_evenly_phased_and_grow_over_time(self):
        self.assertEqual(expanding_circle_radii(0, 7, 90, count=3), (0, 30, 60))
        self.assertEqual(expanding_circle_radii(7, 7, 90, count=3), (0, 30, 60))
        self.assertEqual(expanding_circle_radii(3.5, 7, 90, count=3), (45, 75, 15))

    def test_rings_validate_bounds(self):
        with self.assertRaises(ValueError):
            expanding_circle_radii(0, 0, 90)
        with self.assertRaises(ValueError):
            expanding_circle_radii(0, 7, 90, count=13)

    def test_centered_circle_radius_reaches_every_corner(self):
        self.assertEqual(maximum_circle_radius(400, 600), 361)
        self.assertEqual(expanding_circle_radius(0, 3.5, 361), 0)
        self.assertEqual(expanding_circle_radius(1.75, 3.5, 361), 180)
        self.assertEqual(expanding_circle_radius(9, 3.5, 361), 361)

    def test_negative_circle_inverts_only_pixels_inside_the_circle(self):
        source = Image.new("RGB", (5, 5), (10, 20, 30))
        partial = negative_circle_frame(source, 1)
        self.assertEqual(partial.getpixel((2, 2)), (245, 235, 225))
        self.assertEqual(partial.getpixel((0, 0)), (10, 20, 30))

        full = negative_circle_frame(source, maximum_circle_radius(5, 5))
        self.assertTrue(
            all(
                full.getpixel((x, y)) == (245, 235, 225)
                for y in range(5)
                for x in range(5)
            )
        )

    def test_centered_circle_helpers_reject_invalid_dimensions_and_radius(self):
        with self.assertRaises(ValueError):
            maximum_circle_radius(0, 10)
        with self.assertRaises(ValueError):
            expanding_circle_radius(0, 0, 10)
        with self.assertRaises(ValueError):
            negative_circle_frame(Image.new("RGB", (2, 2)), -1)

    def test_psychedelic_palette_is_valid_and_changes_with_time(self):
        palette = psychedelic_palette(0)
        self.assertEqual(len(palette), 3)
        self.assertTrue(all(re.fullmatch(r"#[0-9A-F]{6}", color) for color in palette))
        self.assertNotEqual(palette, psychedelic_palette(1.0))
        with self.assertRaises(ValueError):
            psychedelic_palette(float("nan"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
