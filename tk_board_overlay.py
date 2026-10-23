import ctypes
import tkinter as tk

from board_reader import FILES, square_cell
from overlay_shapes import (
    DETECTED_SQUARE_COLOR,
    GRID_COLOR,
    LOCKED_BORDER_COLOR,
    RESIZE_GRIP_SIZE,
    BoardGeometry,
    OverlayState,
    clamp_board_size,
    hollow_arrow_shape,
)

TRANSPARENT_KEY_COLOR = "#ff00fe"
DRAG_HANDLE_HEIGHT = 22
HANDLE_TEXT_COLOR = "#0b1a22"
GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WDA_EXCLUDEFROMCAPTURE = 0x00000011
FRAME_LOCKED_THICKNESS = 3
FRAME_ADJUST_THICKNESS = 8
FRAME_HANDLE_THICKNESS = 20
FRAME_TICK_LENGTH = 6


def windows_frame_handle(window: tk.Toplevel) -> int:
    return int(window.wm_frame(), 16)


def windows_user32():
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    user32.SetWindowDisplayAffinity.argtypes = [wintypes.HWND, wintypes.DWORD]
    user32.SetWindowDisplayAffinity.restype = wintypes.BOOL
    user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.GetWindowLongW.restype = wintypes.LONG
    user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.LONG]
    user32.SetWindowLongW.restype = wintypes.LONG
    return user32


def exclude_window_from_capture(window_handle: int) -> None:
    try:
        windows_user32().SetWindowDisplayAffinity(window_handle, WDA_EXCLUDEFROMCAPTURE)
    except (AttributeError, OSError):
        pass


def set_window_click_through(window_handle: int, is_click_through: bool) -> None:
    user32 = windows_user32()
    extended_style = user32.GetWindowLongW(window_handle, GWL_EXSTYLE) | WS_EX_LAYERED
    if is_click_through:
        extended_style |= WS_EX_TRANSPARENT
    else:
        extended_style &= ~WS_EX_TRANSPARENT
    user32.SetWindowLongW(window_handle, GWL_EXSTYLE, extended_style)


class DraggableBoardGeometry:
    def __init__(self, left: int, top: int, board_size: int) -> None:
        self.left = left
        self.top = top
        self.board_size = clamp_board_size(board_size)
        self.drag_start: tuple[int, int, int, int, int, bool] | None = None
        self.pending_geometry: BoardGeometry | None = None
        self.pending_geometry_is_final = False

    def geometry(self) -> BoardGeometry:
        return self.left, self.top, self.board_size

    def begin_drag(self, event: tk.Event, is_resizing: bool) -> None:
        self.drag_start = (event.x_root, event.y_root, self.left, self.top, self.board_size, is_resizing)

    def continue_drag(self, event: tk.Event) -> None:
        if self.drag_start is None:
            return
        start_x, start_y, start_left, start_top, start_size, is_resizing = self.drag_start
        delta_x, delta_y = event.x_root - start_x, event.y_root - start_y
        if is_resizing:
            self.set_geometry(start_left, start_top, start_size + max(delta_x, delta_y))
        else:
            self.set_geometry(start_left + delta_x, start_top + delta_y, start_size)
        self.pending_geometry = self.geometry()

    def finish_drag(self, event: tk.Event) -> None:
        if self.drag_start is not None:
            self.drag_start = None
            self.pending_geometry = self.geometry()
            self.pending_geometry_is_final = True

    def take_pending_geometry(self) -> tuple[BoardGeometry, bool] | None:
        if self.pending_geometry is None:
            return None
        geometry_update = (self.pending_geometry, self.pending_geometry_is_final)
        self.pending_geometry = None
        self.pending_geometry_is_final = False
        return geometry_update

    def set_geometry(self, left: int, top: int, board_size: int) -> None:
        raise NotImplementedError


class WindowsBoardOverlay(DraggableBoardGeometry):
    def __init__(self, root: tk.Tk, left: int, top: int, board_size: int) -> None:
        super().__init__(left, top, board_size)
        self.state = OverlayState()
        self.window = tk.Toplevel(root)
        self.window.overrideredirect(True)
        self.window.attributes("-topmost", True)
        self.window.configure(bg=TRANSPARENT_KEY_COLOR)
        self.window.attributes("-transparentcolor", TRANSPARENT_KEY_COLOR)
        self.canvas = tk.Canvas(self.window, bg=TRANSPARENT_KEY_COLOR, highlightthickness=0, borderwidth=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.tag_bind("drag_handle", "<ButtonPress-1>", lambda event: self.begin_drag(event, False))
        self.canvas.tag_bind("resize_grip", "<ButtonPress-1>", lambda event: self.begin_drag(event, True))
        self.canvas.bind("<B1-Motion>", self.continue_drag)
        self.canvas.bind("<ButtonRelease-1>", self.finish_drag)
        self.apply_window_geometry()
        self.window.update_idletasks()
        self.window_handle = windows_frame_handle(self.window)
        exclude_window_from_capture(self.window_handle)
        self.redraw()

    def apply_window_geometry(self) -> None:
        self.window.geometry(f"{self.board_size}x{self.board_size + DRAG_HANDLE_HEIGHT}+{self.left}+{self.top - DRAG_HANDLE_HEIGHT}")

    def set_geometry(self, left: int, top: int, board_size: int) -> None:
        self.left, self.top, self.board_size = int(left), int(top), clamp_board_size(board_size)
        self.apply_window_geometry()
        self.redraw()

    def update_state(self, state: OverlayState) -> None:
        self.state = state
        set_window_click_through(self.window_handle, state.is_locked)
        self.redraw()

    def redraw(self) -> None:
        canvas = self.canvas
        canvas.delete("all")
        board_size = self.board_size
        cell_size = board_size / 8
        offset_y = DRAG_HANDLE_HEIGHT
        if not self.state.is_locked:
            canvas.create_rectangle(0, 0, board_size, offset_y, fill=GRID_COLOR, outline=GRID_COLOR, tags="drag_handle")
            canvas.create_text(8, offset_y / 2, text="⠿ Geser kotak", anchor="w", fill=HANDLE_TEXT_COLOR, font=("Segoe UI", 9, "bold"), tags="drag_handle")
            for line_index in range(1, 8):
                offset = line_index * cell_size
                canvas.create_line(offset, offset_y, offset, offset_y + board_size, fill=GRID_COLOR)
                canvas.create_line(0, offset_y + offset, board_size, offset_y + offset, fill=GRID_COLOR)
            for column in range(8):
                file_letter = FILES[column if self.state.white_at_bottom else 7 - column]
                canvas.create_text(column * cell_size + 4, offset_y + board_size - 4, text=file_letter, anchor="sw", fill=GRID_COLOR, font=("Segoe UI", 9, "bold"))
            canvas.create_rectangle(
                board_size - RESIZE_GRIP_SIZE,
                offset_y + board_size - RESIZE_GRIP_SIZE,
                board_size,
                offset_y + board_size,
                fill=GRID_COLOR,
                outline=GRID_COLOR,
                tags="resize_grip",
            )
        canvas.create_rectangle(1, offset_y + 1, board_size - 1, offset_y + board_size - 1, outline=LOCKED_BORDER_COLOR if self.state.is_locked else GRID_COLOR, width=2)
        for square in self.state.highlighted_squares or ():
            column, row = square_cell(square, self.state.white_at_bottom)
            canvas.create_rectangle(
                column * cell_size + 3,
                offset_y + row * cell_size + 3,
                (column + 1) * cell_size - 3,
                offset_y + (row + 1) * cell_size - 3,
                outline=DETECTED_SQUARE_COLOR,
                dash=(4, 3),
            )
        if self.state.arrow:
            shape = hollow_arrow_shape(self.state.arrow, self.state.white_at_bottom, cell_size)
            if shape:
                points = [coordinate for x, y in shape.outline_points for coordinate in (x, y + offset_y)]
                canvas.create_polygon(points, outline=self.state.arrow.color, fill="", width=shape.line_width, joinstyle="round")
                center_x, center_y = shape.circle_center
                canvas.create_oval(
                    center_x - shape.circle_radius,
                    offset_y + center_y - shape.circle_radius,
                    center_x + shape.circle_radius,
                    offset_y + center_y + shape.circle_radius,
                    outline=self.state.arrow.color,
                    width=shape.line_width,
                )

    def close(self) -> None:
        self.window.destroy()


class FrameBoardOverlay(DraggableBoardGeometry):
    def __init__(self, root: tk.Tk, left: int, top: int, board_size: int) -> None:
        super().__init__(left, top, board_size)
        self.state = OverlayState()
        self.edges = {name: self.create_edge_window(root) for name in ("top", "bottom", "left", "right", "grip")}
        self.edges["top"][1].bind("<ButtonPress-1>", lambda event: self.begin_drag(event, False))
        self.edges["grip"][1].bind("<ButtonPress-1>", lambda event: self.begin_drag(event, True))
        for name in ("top", "grip"):
            self.edges[name][1].bind("<B1-Motion>", self.continue_drag)
            self.edges[name][1].bind("<ButtonRelease-1>", self.finish_drag)
        self.redraw()

    @staticmethod
    def create_edge_window(root: tk.Tk) -> tuple[tk.Toplevel, tk.Canvas]:
        window = tk.Toplevel(root)
        window.overrideredirect(True)
        window.attributes("-topmost", True)
        canvas = tk.Canvas(window, highlightthickness=0, borderwidth=0)
        canvas.pack(fill="both", expand=True)
        return window, canvas

    def set_geometry(self, left: int, top: int, board_size: int) -> None:
        self.left, self.top, self.board_size = int(left), int(top), clamp_board_size(board_size)
        self.redraw()

    def update_state(self, state: OverlayState) -> None:
        self.state = state
        self.redraw()

    def redraw(self) -> None:
        is_locked = self.state.is_locked
        side_thickness = FRAME_LOCKED_THICKNESS if is_locked else FRAME_ADJUST_THICKNESS
        top_thickness = FRAME_LOCKED_THICKNESS if is_locked else FRAME_HANDLE_THICKNESS
        edge_color = LOCKED_BORDER_COLOR if is_locked else GRID_COLOR
        left, top, board_size = self.left, self.top, self.board_size
        cell_size = board_size / 8
        placements = {
            "top": (left - side_thickness, top - top_thickness, board_size + 2 * side_thickness, top_thickness),
            "bottom": (left - side_thickness, top + board_size, board_size + 2 * side_thickness, side_thickness),
            "left": (left - side_thickness, top, side_thickness, board_size),
            "right": (left + board_size, top, side_thickness, board_size),
            "grip": (left + board_size, top + board_size, RESIZE_GRIP_SIZE, RESIZE_GRIP_SIZE),
        }
        for name, (x, y, width, height) in placements.items():
            window, canvas = self.edges[name]
            if name == "grip" and is_locked:
                window.withdraw()
                continue
            window.deiconify()
            window.geometry(f"{width}x{height}+{x}+{y}")
            canvas.configure(bg=edge_color)
            canvas.delete("all")
            if is_locked:
                continue
            for line_index in range(1, 8):
                offset = line_index * cell_size
                if name in ("top", "bottom"):
                    tick_top = height - FRAME_TICK_LENGTH if name == "top" else 0
                    canvas.create_line(side_thickness + offset, tick_top, side_thickness + offset, tick_top + FRAME_TICK_LENGTH, fill=HANDLE_TEXT_COLOR, width=2)
                elif name in ("left", "right"):
                    canvas.create_line(0, offset, width, offset, fill=HANDLE_TEXT_COLOR, width=2)
            if name == "top":
                canvas.create_text(side_thickness + 6, height / 2 - 2, text="⠿ Geser kotak", anchor="w", fill=HANDLE_TEXT_COLOR, font=("TkDefaultFont", 9, "bold"))

    def close(self) -> None:
        for window, _ in self.edges.values():
            window.destroy()
