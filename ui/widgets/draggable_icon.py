class DraggableIcon:
    DRAG_THRESHOLD = 4

    def __init__(self, canvas, widget, on_drag_begin=None, on_drag_end=None):
        self.canvas = canvas
        self.widget = widget
        self.on_drag_begin = on_drag_begin
        self.on_drag_end = on_drag_end

        self.offset_x = 0
        self.offset_y = 0
        self.start_pointer_x = 0
        self.start_pointer_y = 0
        self.was_dragged = False
        self._drag_end_fired = False

        self._bind_all(self.widget)

    def _bind_all(self, current_widget):
        current_widget.bind("<Button-1>", self.start_drag)
        current_widget.bind("<B1-Motion>", self.drag)
        current_widget.bind("<ButtonRelease-1>", self.drop)

        for child in current_widget.winfo_children():
            self._bind_all(child)

    def start_drag(self, event):
        self.offset_x = event.x_root - self.widget.winfo_rootx()
        self.offset_y = event.y_root - self.widget.winfo_rooty()
        self.start_pointer_x = event.x_root
        self.start_pointer_y = event.y_root
        self.was_dragged = False
        self._drag_end_fired = False

    def _clamp_position(self, x, y):
        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()
        widget_width = self.widget.winfo_width()
        widget_height = self.widget.winfo_height()

        if (
            canvas_width <= 0
            or canvas_height <= 0
            or widget_width <= 0
            or widget_height <= 0
            or canvas_width < widget_width
            or canvas_height < widget_height
        ):
            return 0, 0

        max_x = canvas_width - widget_width
        max_y = canvas_height - widget_height
        return min(max(x, 0), max_x), min(max(y, 0), max_y)

    def drag(self, event):
        if (
            abs(event.x_root - self.start_pointer_x) >= self.DRAG_THRESHOLD
            or abs(event.y_root - self.start_pointer_y) >= self.DRAG_THRESHOLD
        ) and not self.was_dragged:
            self.was_dragged = True
            if self.on_drag_begin is not None:
                self.on_drag_begin()
        canvas_x = event.x_root - self.canvas.winfo_rootx()
        canvas_y = event.y_root - self.canvas.winfo_rooty()
        x = canvas_x - self.offset_x
        y = canvas_y - self.offset_y

        new_x, new_y = self._clamp_position(x, y)
        self.widget.place(x=new_x, y=new_y)

    def drop(self, _event):
        # The main_gui release handler chooses the free slot and persists it.
        if self.was_dragged and not self._drag_end_fired:
            self._drag_end_fired = True
            if self.on_drag_end is not None:
                self.on_drag_end()
