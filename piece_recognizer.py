import json
import math
from dataclasses import dataclass
from pathlib import Path

import chess
from PIL import Image, ImageFilter

from board_reader import square_name
from project_paths import PIECE_TEMPLATES_FILE
from square_change_detector import (
    BACKGROUND_RING_INSET,
    FOREGROUND_PIXEL_THRESHOLD,
    IGNORED_EDGE_SAMPLES,
    SAMPLES_PER_SQUARE_SIDE,
    color_difference,
    median_color,
    occupied_square_indices,
)

BACKGROUND_FEATURE_VALUE = -1
START_POSITION_ROWS = {0, 1, 6, 7}
EDGE_SAMPLES_PER_SQUARE_SIDE = 32
EDGE_IGNORED_BORDER = 3
EDGE_POOL_CELLS = 8

ColorFeature = tuple[int, ...]
ShapeFeature = tuple[float, ...]


@dataclass(frozen=True)
class PieceTemplate:
    symbol: str
    color_feature: ColorFeature
    shape_feature: ShapeFeature


def luminance(sample: tuple[int, int, int]) -> int:
    return round(0.299 * sample[0] + 0.587 * sample[1] + 0.114 * sample[2])


def square_color_features(image: Image.Image) -> list[ColorFeature]:
    side = 8 * SAMPLES_PER_SQUARE_SIDE
    pixels = image.convert("RGB").resize((side, side), Image.Resampling.BOX).load()
    ring_low = BACKGROUND_RING_INSET
    ring_high = SAMPLES_PER_SQUARE_SIDE - 1 - BACKGROUND_RING_INSET
    ring_range = range(ring_low, ring_high + 1)
    inner_range = range(IGNORED_EDGE_SAMPLES, SAMPLES_PER_SQUARE_SIDE - IGNORED_EDGE_SAMPLES)
    features = []
    for row in range(8):
        for column in range(8):
            origin_x, origin_y = column * SAMPLES_PER_SQUARE_SIDE, row * SAMPLES_PER_SQUARE_SIDE
            background = median_color([
                pixels[origin_x + sample_x, origin_y + sample_y]
                for sample_y in ring_range
                for sample_x in ring_range
                if sample_x in (ring_low, ring_high) or sample_y in (ring_low, ring_high)
            ])
            feature = []
            for sample_y in inner_range:
                for sample_x in inner_range:
                    sample = pixels[origin_x + sample_x, origin_y + sample_y]
                    is_foreground = color_difference(sample, background) > FOREGROUND_PIXEL_THRESHOLD
                    feature.append(luminance(sample) if is_foreground else BACKGROUND_FEATURE_VALUE)
            features.append(tuple(feature))
    return features


def square_shape_features(image: Image.Image) -> list[ShapeFeature]:
    side = 8 * EDGE_SAMPLES_PER_SQUARE_SIDE
    edges = image.convert("L").resize((side, side), Image.Resampling.BOX).filter(ImageFilter.FIND_EDGES).load()
    usable_span = EDGE_SAMPLES_PER_SQUARE_SIDE - 2 * EDGE_IGNORED_BORDER
    features = []
    for row in range(8):
        for column in range(8):
            origin_x, origin_y = column * EDGE_SAMPLES_PER_SQUARE_SIDE, row * EDGE_SAMPLES_PER_SQUARE_SIDE
            pooled = []
            for pool_y in range(EDGE_POOL_CELLS):
                for pool_x in range(EDGE_POOL_CELLS):
                    y_range = range(EDGE_IGNORED_BORDER + pool_y * usable_span // EDGE_POOL_CELLS, EDGE_IGNORED_BORDER + (pool_y + 1) * usable_span // EDGE_POOL_CELLS)
                    x_range = range(EDGE_IGNORED_BORDER + pool_x * usable_span // EDGE_POOL_CELLS, EDGE_IGNORED_BORDER + (pool_x + 1) * usable_span // EDGE_POOL_CELLS)
                    pooled.append(sum(edges[origin_x + x, origin_y + y] for y in y_range for x in x_range))
            norm = math.sqrt(sum(value * value for value in pooled)) or 1.0
            features.append(tuple(value / norm for value in pooled))
    return features


def color_feature_distance(first: ColorFeature, second: ColorFeature) -> float:
    total = 0.0
    for first_value, second_value in zip(first, second):
        first_is_background = first_value == BACKGROUND_FEATURE_VALUE
        second_is_background = second_value == BACKGROUND_FEATURE_VALUE
        if first_is_background and second_is_background:
            continue
        if first_is_background or second_is_background:
            total += 1.0
        else:
            total += abs(first_value - second_value) / 255
    return total / len(first)


def shape_feature_distance(first: ShapeFeature, second: ShapeFeature) -> float:
    return 1.0 - sum(first_value * second_value for first_value, second_value in zip(first, second))


def mean_foreground_luminance(features: list[ColorFeature], indices: set[int]) -> float:
    values = [value for index in indices for value in features[index] if value != BACKGROUND_FEATURE_VALUE]
    return sum(values) / len(values) if values else 0.0


def looks_like_start_position(occupied_indices: set[int]) -> bool:
    return len(occupied_indices) == 32 and {index // 8 for index in occupied_indices} == START_POSITION_ROWS


class PieceRecognizer:
    def __init__(self, templates_file: Path = PIECE_TEMPLATES_FILE) -> None:
        self.templates_file = templates_file
        self.templates: list[PieceTemplate] = []
        self.load()

    @property
    def has_templates(self) -> bool:
        return len({template.symbol for template in self.templates}) == 12

    def load(self) -> None:
        try:
            stored = json.loads(self.templates_file.read_text())
            self.templates = [
                PieceTemplate(entry["symbol"], tuple(entry["color_feature"]), tuple(entry["shape_feature"]))
                for entry in stored
            ]
        except (OSError, ValueError, KeyError, TypeError):
            self.templates = []

    def save(self) -> None:
        self.templates_file.write_text(json.dumps([
            {"symbol": template.symbol, "color_feature": template.color_feature, "shape_feature": template.shape_feature}
            for template in self.templates
        ]))

    def learn_start_position(self, image: Image.Image) -> bool | None:
        occupied_indices = occupied_square_indices(image)
        if not looks_like_start_position(occupied_indices):
            return None
        color_features = square_color_features(image)
        shape_features = square_shape_features(image)
        bottom_indices = {index for index in occupied_indices if index // 8 >= 6}
        top_indices = occupied_indices - bottom_indices
        white_at_bottom = mean_foreground_luminance(color_features, bottom_indices) >= mean_foreground_luminance(color_features, top_indices)
        start_board = chess.Board()
        self.templates = [
            PieceTemplate(
                symbol=start_board.piece_at(chess.parse_square(square_name(index % 8, index // 8, white_at_bottom))).symbol(),
                color_feature=color_features[index],
                shape_feature=shape_features[index],
            )
            for index in sorted(occupied_indices)
        ]
        self.save()
        return white_at_bottom

    def classify_piece(self, color_feature: ColorFeature, shape_feature: ShapeFeature) -> chess.Piece:
        closest_by_color = min(self.templates, key=lambda template: color_feature_distance(color_feature, template.color_feature))
        piece_is_white = closest_by_color.symbol.isupper()
        same_color_templates = [template for template in self.templates if template.symbol.isupper() == piece_is_white]
        closest_by_shape = min(same_color_templates, key=lambda template: shape_feature_distance(shape_feature, template.shape_feature))
        return chess.Piece.from_symbol(closest_by_shape.symbol)

    def recognize_cells(self, image: Image.Image) -> dict[int, chess.Piece]:
        color_features = square_color_features(image)
        shape_features = square_shape_features(image)
        return {
            index: self.classify_piece(color_features[index], shape_features[index])
            for index in occupied_square_indices(image)
        }

    def recognize_pieces(self, image: Image.Image, white_at_bottom: bool) -> dict[chess.Square, chess.Piece]:
        return pieces_on_squares(self.recognize_cells(image), white_at_bottom)


def pieces_on_squares(cells: dict[int, chess.Piece], white_at_bottom: bool) -> dict[chess.Square, chess.Piece]:
    return {chess.parse_square(square_name(index % 8, index // 8, white_at_bottom)): piece for index, piece in cells.items()}


def mean_screen_row(cells: dict[int, chess.Piece], symbol: str) -> tuple[float | None, int]:
    rows = [index // 8 for index, piece in cells.items() if piece.symbol() == symbol]
    return (sum(rows) / len(rows) if rows else None), len(rows)


def infer_white_at_bottom(cells: dict[int, chess.Piece]) -> bool | None:
    white_pawn_row, white_pawn_count = mean_screen_row(cells, "P")
    black_pawn_row, black_pawn_count = mean_screen_row(cells, "p")
    if white_pawn_row is not None and black_pawn_row is not None:
        row_gap = white_pawn_row - black_pawn_row
        if (min(white_pawn_count, black_pawn_count) >= 2 and abs(row_gap) >= 1) or abs(row_gap) >= 3:
            return row_gap > 0
    white_king_row, _ = mean_screen_row(cells, "K")
    black_king_row, _ = mean_screen_row(cells, "k")
    if white_king_row is not None and black_king_row is not None and abs(white_king_row - black_king_row) >= 3:
        return white_king_row > black_king_row
    return None


def board_from_pieces(pieces: dict[chess.Square, chess.Piece], white_to_move: bool) -> chess.Board | None:
    board = chess.Board(None)
    board.set_piece_map(pieces)
    board.turn = chess.WHITE if white_to_move else chess.BLACK
    board.set_castling_fen("KQkq")
    board.castling_rights = board.clean_castling_rights()
    return board if board.is_valid() else None
