import math
from dataclasses import dataclass

from board_reader import square_cell

RESIZE_GRIP_SIZE = 22
MINIMUM_BOARD_SIZE = 240
MAXIMUM_BOARD_SIZE = 1400
GRID_COLOR = "#00c8ff"
LOCKED_BORDER_COLOR = "#5a6270"
DETECTED_SQUARE_COLOR = "#ff3df0"

BoardGeometry = tuple[int, int, int]
Point = tuple[float, float]


@dataclass(frozen=True)
class OverlayArrow:
    from_square: str
    to_square: str
    color: str


@dataclass(frozen=True)
class OverlayState:
    is_locked: bool = False
    white_at_bottom: bool = True
    highlighted_squares: tuple[str, ...] | None = None
    arrow: OverlayArrow | None = None


@dataclass(frozen=True)
class HollowArrowShape:
    outline_points: list[Point]
    circle_center: Point
    circle_radius: float
    line_width: float


def clamp_board_size(board_size: float) -> int:
    return max(MINIMUM_BOARD_SIZE, min(MAXIMUM_BOARD_SIZE, int(board_size)))


def square_center(square: str, white_at_bottom: bool, cell_size: float) -> Point:
    column, row = square_cell(square, white_at_bottom)
    return (column + 0.5) * cell_size, (row + 0.5) * cell_size


def hollow_arrow_shape(arrow: OverlayArrow, white_at_bottom: bool, cell_size: float) -> HollowArrowShape | None:
    start_x, start_y = square_center(arrow.from_square, white_at_bottom, cell_size)
    end_x, end_y = square_center(arrow.to_square, white_at_bottom, cell_size)
    length = math.hypot(end_x - start_x, end_y - start_y)
    if length == 0:
        return None
    unit_x, unit_y = (end_x - start_x) / length, (end_y - start_y) / length
    normal_x, normal_y = -unit_y, unit_x
    shaft_half_width = cell_size * 0.09
    head_half_width = cell_size * 0.24
    head_length = min(cell_size * 0.45, length * 0.6)
    shaft_end_x, shaft_end_y = end_x - unit_x * head_length, end_y - unit_y * head_length
    return HollowArrowShape(
        outline_points=[
            (start_x + normal_x * shaft_half_width, start_y + normal_y * shaft_half_width),
            (shaft_end_x + normal_x * shaft_half_width, shaft_end_y + normal_y * shaft_half_width),
            (shaft_end_x + normal_x * head_half_width, shaft_end_y + normal_y * head_half_width),
            (end_x, end_y),
            (shaft_end_x - normal_x * head_half_width, shaft_end_y - normal_y * head_half_width),
            (shaft_end_x - normal_x * shaft_half_width, shaft_end_y - normal_y * shaft_half_width),
            (start_x - normal_x * shaft_half_width, start_y - normal_y * shaft_half_width),
        ],
        circle_center=(start_x, start_y),
        circle_radius=cell_size * 0.36,
        line_width=max(2.0, cell_size * 0.05),
    )
