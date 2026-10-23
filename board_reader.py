from PIL import Image, ImageGrab

from site_profiles import RgbColor, SiteProfile

FILES = "abcdefgh"
SAMPLES_PER_SQUARE_SIDE = 12
SQUARE_EDGE_MARGIN_RATIO = 0.06
MINIMUM_HIGHLIGHT_RATIO = 0.2

BoardRect = tuple[int, int, int]


def capture_board(board_rect: BoardRect) -> Image.Image:
    left, top, size = board_rect
    return ImageGrab.grab(bbox=(left, top, left + size, top + size)).convert("RGB")


def color_matches(pixel: RgbColor, colors: tuple[RgbColor, ...], tolerance: int) -> bool:
    return any(
        abs(pixel[0] - color[0]) <= tolerance
        and abs(pixel[1] - color[1]) <= tolerance
        and abs(pixel[2] - color[2]) <= tolerance
        for color in colors
    )


def square_name(column: int, row: int, white_at_bottom: bool) -> str:
    if white_at_bottom:
        return FILES[column] + str(8 - row)
    return FILES[7 - column] + str(row + 1)


def square_cell(square: str, white_at_bottom: bool) -> tuple[int, int]:
    file_index = FILES.index(square[0])
    rank = int(square[1])
    if white_at_bottom:
        return file_index, 8 - rank
    return 7 - file_index, rank - 1


def measure_highlight_ratio(image: Image.Image, column: int, row: int, colors: tuple[RgbColor, ...], tolerance: int) -> float:
    pixels = image.load()
    cell_width = image.width / 8
    cell_height = image.height / 8
    usable_ratio = 1 - 2 * SQUARE_EDGE_MARGIN_RATIO
    matched_samples = 0
    for sample_y in range(SAMPLES_PER_SQUARE_SIDE):
        for sample_x in range(SAMPLES_PER_SQUARE_SIDE):
            offset_x = SQUARE_EDGE_MARGIN_RATIO + usable_ratio * (sample_x + 0.5) / SAMPLES_PER_SQUARE_SIDE
            offset_y = SQUARE_EDGE_MARGIN_RATIO + usable_ratio * (sample_y + 0.5) / SAMPLES_PER_SQUARE_SIDE
            x = min(image.width - 1, int((column + offset_x) * cell_width))
            y = min(image.height - 1, int((row + offset_y) * cell_height))
            if color_matches(pixels[x, y], colors, tolerance):
                matched_samples += 1
    return matched_samples / (SAMPLES_PER_SQUARE_SIDE * SAMPLES_PER_SQUARE_SIDE)


def find_highlighted_squares(image: Image.Image, profile: SiteProfile, white_at_bottom: bool, tolerance: int) -> tuple[str, str] | None:
    ratios = sorted(
        (
            (measure_highlight_ratio(image, column, row, profile.highlight_colors, tolerance), column, row)
            for row in range(8)
            for column in range(8)
        ),
        reverse=True,
    )
    (_, first_column, first_row), (second_ratio, second_column, second_row) = ratios[0], ratios[1]
    if second_ratio < MINIMUM_HIGHLIGHT_RATIO:
        return None
    return (
        square_name(first_column, first_row, white_at_bottom),
        square_name(second_column, second_row, white_at_bottom),
    )
