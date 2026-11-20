from __future__ import annotations

import unittest
from types import SimpleNamespace

from ui.widgets.draggable_icon import DraggableIcon


class FakeWidget:
    def __init__(self, *, root_x=100, root_y=100, width=50, height=50, children=()):
        self.root_x = root_x
        self.root_y = root_y
        self.width = width
        self.height = height
        self.children = list(children)
        self.bindings = {}
        self.position = None

    def bind(self, sequence, callback):
        self.bindings[sequence] = callback

    def winfo_children(self):
        return self.children

    def winfo_rootx(self):
        return self.root_x

    def winfo_rooty(self):
        return self.root_y

    def winfo_width(self):
        return self.width

    def winfo_height(self):
        return self.height

    def place(self, *, x, y):
        self.position = (x, y)


class FakeCanvas:
    def __init__(self, *, root_x=50, root_y=50, width=300, height=300):
        self.root_x = root_x
        self.root_y = root_y
        self.width = width
        self.height = height

    def winfo_rootx(self):
        return self.root_x

    def winfo_rooty(self):
        return self.root_y

    def winfo_width(self):
        return self.width

    def winfo_height(self):
        return self.height


class DraggableIconTests(unittest.TestCase):
    def setUp(self):
        self.child = FakeWidget(root_x=105, root_y=110, width=10, height=10)
        self.widget = FakeWidget(children=(self.child,))
        self.canvas = FakeCanvas()
        self.drag = DraggableIcon(self.canvas, self.widget)

    def test_drag_uses_root_pointer_and_does_not_snap_mid_motion(self):
        self.drag.start_drag(SimpleNamespace(x_root=120, y_root=130))
        self.drag.drag(SimpleNamespace(x_root=200, y_root=220))
        self.assertEqual(self.widget.position, (130, 140))
        self.assertTrue(self.drag.was_dragged)

    def test_small_pointer_jitter_remains_a_click(self):
        self.drag.start_drag(SimpleNamespace(x_root=120, y_root=130))
        self.drag.drag(SimpleNamespace(x_root=122, y_root=132))
        self.assertFalse(self.drag.was_dragged)

    def test_callbacks_fire_once_for_a_real_drag(self):
        events = []
        drag = DraggableIcon(
            self.canvas,
            self.widget,
            on_drag_begin=lambda: events.append("begin"),
            on_drag_end=lambda: events.append("end"),
        )

        drag.start_drag(SimpleNamespace(x_root=120, y_root=130))
        drag.drag(SimpleNamespace(x_root=123, y_root=133))
        self.assertEqual(events, [])
        drag.drag(SimpleNamespace(x_root=124, y_root=134))
        drag.drag(SimpleNamespace(x_root=200, y_root=220))
        self.assertEqual(events, ["begin"])

        drag.drop(SimpleNamespace(x_root=200, y_root=220))
        self.assertEqual(events, ["begin", "end"])

    def test_callbacks_do_not_fire_for_a_click_or_jitter(self):
        events = []
        drag = DraggableIcon(
            self.canvas,
            self.widget,
            on_drag_begin=lambda: events.append("begin"),
            on_drag_end=lambda: events.append("end"),
        )

        drag.start_drag(SimpleNamespace(x_root=120, y_root=130))
        drag.drag(SimpleNamespace(x_root=122, y_root=132))
        drag.drop(SimpleNamespace(x_root=122, y_root=132))

        self.assertEqual(events, [])

    def test_end_callback_fires_on_release_after_drag(self):
        ended = []
        drag = DraggableIcon(
            self.canvas,
            self.widget,
            on_drag_end=lambda: ended.append(True),
        )

        drag.start_drag(SimpleNamespace(x_root=120, y_root=130))
        drag.drag(SimpleNamespace(x_root=124, y_root=130))
        self.assertEqual(ended, [])

        drag.drop(SimpleNamespace(x_root=124, y_root=130))
        self.assertEqual(ended, [True])

    def test_drag_clamps_frame_to_canvas_bounds(self):
        self.drag.start_drag(SimpleNamespace(x_root=120, y_root=130))
        self.drag.drag(SimpleNamespace(x_root=1000, y_root=1000))
        self.assertEqual(self.widget.position, (250, 250))

    def test_frame_larger_than_canvas_returns_to_visible_origin(self):
        self.canvas.width = 40
        self.canvas.height = 40
        self.drag.start_drag(SimpleNamespace(x_root=120, y_root=130))
        self.drag.drag(SimpleNamespace(x_root=250, y_root=250))
        self.assertEqual(self.widget.position, (0, 0))

    def test_icon_children_remain_draggable_and_drop_does_not_snap(self):
        self.assertIn("<Button-1>", self.child.bindings)
        self.assertIn("<B1-Motion>", self.child.bindings)
        self.assertIn("<ButtonRelease-1>", self.child.bindings)
        self.drag.start_drag(SimpleNamespace(x_root=120, y_root=130))
        self.drag.drag(SimpleNamespace(x_root=200, y_root=220))
        position_before_release = self.widget.position
        self.drag.drop(SimpleNamespace(x_root=200, y_root=220))
        self.assertEqual(self.widget.position, position_before_release)


if __name__ == "__main__":
    unittest.main(verbosity=2)
