import AppKit
import objc
from Foundation import NSMakePoint, NSMakeRect

from board_reader import FILES, square_cell
from overlay_shapes import (
    DETECTED_SQUARE_COLOR,
    GRID_COLOR,
    LOCKED_BORDER_COLOR,
    RESIZE_GRIP_SIZE,
    BoardGeometry,
    OverlayArrow,
    OverlayState,
    clamp_board_size,
    hollow_arrow_shape,
)

ADJUST_MODE_TINT_ALPHA = 0.12
OVERLAY_WINDOW_LEVEL = AppKit.NSStatusWindowLevel


def ns_color(hex_color: str, alpha: float = 1.0) -> AppKit.NSColor:
    red, green, blue = (int(hex_color[index:index + 2], 16) / 255 for index in (1, 3, 5))
    return AppKit.NSColor.colorWithSRGBRed_green_blue_alpha_(red, green, blue, alpha)


def main_screen_height() -> float:
    return AppKit.NSScreen.screens()[0].frame().size.height


def keep_window_floating(window_title: str) -> bool:
    for window in AppKit.NSApp.windows():
        if window.title() == window_title:
            window.setLevel_(OVERLAY_WINDOW_LEVEL)
            window.setHidesOnDeactivate_(False)
            return True
    return False


def stroke_hollow_arrow(arrow: OverlayArrow, white_at_bottom: bool, cell_size: float) -> None:
    shape = hollow_arrow_shape(arrow, white_at_bottom, cell_size)
    if shape is None:
        return
    ns_color(arrow.color).setStroke()
    arrow_path = AppKit.NSBezierPath.bezierPath()
    arrow_path.moveToPoint_(NSMakePoint(*shape.outline_points[0]))
    for point in shape.outline_points[1:]:
        arrow_path.lineToPoint_(NSMakePoint(*point))
    arrow_path.closePath()
    arrow_path.setLineWidth_(shape.line_width)
    arrow_path.setLineJoinStyle_(AppKit.NSLineJoinStyleRound)
    arrow_path.stroke()
    center_x, center_y = shape.circle_center
    circle_path = AppKit.NSBezierPath.bezierPathWithOvalInRect_(
        NSMakeRect(center_x - shape.circle_radius, center_y - shape.circle_radius, shape.circle_radius * 2, shape.circle_radius * 2)
    )
    circle_path.setLineWidth_(shape.line_width)
    circle_path.stroke()


def draw_overlay(state: OverlayState, board_size: float) -> None:
    cell_size = board_size / 8
    if not state.is_locked:
        ns_color(GRID_COLOR, ADJUST_MODE_TINT_ALPHA).setFill()
        AppKit.NSBezierPath.fillRect_(NSMakeRect(0, 0, board_size, board_size))
    border_path = AppKit.NSBezierPath.bezierPathWithRect_(NSMakeRect(1, 1, board_size - 2, board_size - 2))
    border_path.setLineWidth_(2.0)
    ns_color(LOCKED_BORDER_COLOR if state.is_locked else GRID_COLOR).setStroke()
    border_path.stroke()
    if not state.is_locked:
        grid_path = AppKit.NSBezierPath.bezierPath()
        for line_index in range(1, 8):
            offset = line_index * cell_size
            grid_path.moveToPoint_(NSMakePoint(offset, 0))
            grid_path.lineToPoint_(NSMakePoint(offset, board_size))
            grid_path.moveToPoint_(NSMakePoint(0, offset))
            grid_path.lineToPoint_(NSMakePoint(board_size, offset))
        grid_path.setLineWidth_(1.0)
        grid_path.stroke()
        label_attributes = {
            AppKit.NSFontAttributeName: AppKit.NSFont.boldSystemFontOfSize_(11),
            AppKit.NSForegroundColorAttributeName: ns_color(GRID_COLOR),
        }
        for column in range(8):
            file_letter = FILES[column if state.white_at_bottom else 7 - column]
            AppKit.NSString.stringWithString_(file_letter).drawAtPoint_withAttributes_(
                NSMakePoint(column * cell_size + 4, board_size - 16), label_attributes
            )
        ns_color(GRID_COLOR).setFill()
        AppKit.NSBezierPath.fillRect_(
            NSMakeRect(board_size - RESIZE_GRIP_SIZE, board_size - RESIZE_GRIP_SIZE, RESIZE_GRIP_SIZE, RESIZE_GRIP_SIZE)
        )
    if state.highlighted_squares:
        ns_color(DETECTED_SQUARE_COLOR).setStroke()
        for square in state.highlighted_squares:
            column, row = square_cell(square, state.white_at_bottom)
            highlight_path = AppKit.NSBezierPath.bezierPathWithRect_(
                NSMakeRect(column * cell_size + 3, row * cell_size + 3, cell_size - 6, cell_size - 6)
            )
            highlight_path.setLineDash_count_phase_([4.0, 3.0], 2, 0.0)
            highlight_path.setLineWidth_(1.0)
            highlight_path.stroke()
    if state.arrow:
        stroke_hollow_arrow(state.arrow, state.white_at_bottom, cell_size)


class BoardOverlayView(AppKit.NSView):
    def initWithFrame_(self, frame):
        self = objc.super(BoardOverlayView, self).initWithFrame_(frame)
        if self is None:
            return None
        self.overlay_state = OverlayState()
        self.drag_controller = None
        return self

    def isFlipped(self):
        return True

    def acceptsFirstMouse_(self, event):
        return True

    def drawRect_(self, dirty_rect):
        draw_overlay(self.overlay_state, self.bounds().size.width)

    def mouseDown_(self, event):
        if self.drag_controller:
            local_point = self.convertPoint_fromView_(event.locationInWindow(), None)
            self.drag_controller.begin_drag(local_point.x, local_point.y)

    def mouseDragged_(self, event):
        if self.drag_controller:
            self.drag_controller.continue_drag()

    def mouseUp_(self, event):
        if self.drag_controller:
            self.drag_controller.finish_drag()


class NativeBoardOverlay:
    def __init__(self, root, left: int, top: int, board_size: int) -> None:
        self.drag_start: tuple[float, float, AppKit.NSRect, bool] | None = None
        self.pending_geometry: BoardGeometry | None = None
        self.pending_geometry_is_final = False
        board_size = clamp_board_size(board_size)
        self.window = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            self.cocoa_frame(left, top, board_size),
            AppKit.NSWindowStyleMaskBorderless,
            AppKit.NSBackingStoreBuffered,
            False,
        )
        self.window.setOpaque_(False)
        self.window.setBackgroundColor_(AppKit.NSColor.clearColor())
        self.window.setHasShadow_(False)
        self.window.setLevel_(OVERLAY_WINDOW_LEVEL)
        self.window.setReleasedWhenClosed_(False)
        self.window.setSharingType_(AppKit.NSWindowSharingNone)
        self.window.setCollectionBehavior_(
            AppKit.NSWindowCollectionBehaviorCanJoinAllSpaces | AppKit.NSWindowCollectionBehaviorFullScreenAuxiliary
        )
        self.view = BoardOverlayView.alloc().initWithFrame_(NSMakeRect(0, 0, board_size, board_size))
        self.view.drag_controller = self
        self.window.setContentView_(self.view)
        self.window.orderFrontRegardless()

    @staticmethod
    def cocoa_frame(left: float, top: float, board_size: float) -> AppKit.NSRect:
        return NSMakeRect(left, main_screen_height() - top - board_size, board_size, board_size)

    def geometry(self) -> BoardGeometry:
        frame = self.window.frame()
        board_size = int(frame.size.width)
        top = int(main_screen_height() - frame.origin.y - frame.size.height)
        return int(frame.origin.x), top, board_size

    def set_geometry(self, left: int, top: int, board_size: int) -> None:
        board_size = clamp_board_size(board_size)
        self.window.setFrame_display_(self.cocoa_frame(left, top, board_size), True)
        self.view.setNeedsDisplay_(True)

    def update_state(self, state: OverlayState) -> None:
        self.view.overlay_state = state
        self.window.setIgnoresMouseEvents_(state.is_locked)
        self.view.setNeedsDisplay_(True)

    def begin_drag(self, local_x: float, local_y: float) -> None:
        board_size = self.window.frame().size.width
        is_resizing = local_x >= board_size - RESIZE_GRIP_SIZE and local_y >= board_size - RESIZE_GRIP_SIZE
        mouse_location = AppKit.NSEvent.mouseLocation()
        self.drag_start = (mouse_location.x, mouse_location.y, self.window.frame(), is_resizing)

    def continue_drag(self) -> None:
        if self.drag_start is None:
            return
        start_x, start_y, start_frame, is_resizing = self.drag_start
        mouse_location = AppKit.NSEvent.mouseLocation()
        delta_x = mouse_location.x - start_x
        delta_y = mouse_location.y - start_y
        start_top = main_screen_height() - start_frame.origin.y - start_frame.size.height
        if is_resizing:
            new_size = clamp_board_size(start_frame.size.width + max(delta_x, -delta_y))
            self.set_geometry(int(start_frame.origin.x), int(start_top), new_size)
        else:
            self.set_geometry(int(start_frame.origin.x + delta_x), int(start_top - delta_y), int(start_frame.size.width))
        self.pending_geometry = self.geometry()

    def finish_drag(self) -> None:
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

    def close(self) -> None:
        self.window.orderOut_(None)
        self.window.close()
