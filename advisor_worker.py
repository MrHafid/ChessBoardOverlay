import queue
import threading
from dataclasses import dataclass

import chess

from board_reader import BoardRect, capture_board, find_highlighted_squares, square_name
from engine_advisor import Advice, EngineAdvisor, find_engine_path
from game_tracker import GameTracker
from piece_recognizer import PieceRecognizer, board_from_pieces, infer_white_at_bottom, looks_like_start_position, pieces_on_squares
from site_profiles import SiteProfile
from square_change_detector import SquareChangeDetector, occupied_square_indices, square_signatures

POLL_INTERVAL_SECONDS = 0.35
ENGINE_LINE_COUNT = 3
MISMATCHES_BEFORE_RESYNC = 4
STICKY_STATUS_POLLS = 9
UNKNOWN_PIECE_SET_STATUS = "Set bidak di layar belum dikenal: buka papan di posisi awal sekali supaya bidak terekam otomatis"


@dataclass(frozen=True)
class ReaderSettings:
    board_rect: BoardRect | None = None
    site_profile: SiteProfile | None = None
    white_at_bottom: bool = True
    color_tolerance: int = 12
    think_seconds: float = 0.8
    is_reading: bool = False


@dataclass(frozen=True)
class WorkerUpdate:
    status_text: str
    highlighted_squares: tuple[str, ...] | None = None
    advice: Advice | None = None
    move_history_san: str | None = None
    detected_white_at_bottom: bool | None = None


class AdvisorWorker(threading.Thread):
    def __init__(self, update_queue: queue.Queue) -> None:
        super().__init__(daemon=True)
        self.update_queue = update_queue
        self.settings_lock = threading.Lock()
        self.reader_settings = ReaderSettings()
        self.pending_commands: queue.Queue[str] = queue.Queue()
        self.stop_event = threading.Event()
        self.tracker = GameTracker()
        self.change_detector = SquareChangeDetector()
        self.last_board_layout: tuple[BoardRect | None, bool, SiteProfile | None] | None = None
        self.advisor: EngineAdvisor | None = None
        self.analysis_needed = True
        self.recognizer = PieceRecognizer()
        self.learning_requested = False
        self.learned_this_session = False
        self.position_read_request: bool | None = None
        self.mismatch_streak = 0
        self.pending_status: str | None = None
        self.sticky_status: str | None = None
        self.sticky_status_polls_left = 0
        self.detected_white_at_bottom: bool | None = None

    def update_reader_settings(self, reader_settings: ReaderSettings) -> None:
        with self.settings_lock:
            self.reader_settings = reader_settings

    def current_reader_settings(self) -> ReaderSettings:
        with self.settings_lock:
            return self.reader_settings

    def request_new_game(self) -> None:
        self.pending_commands.put("new_game")

    def request_undo(self) -> None:
        self.pending_commands.put("undo")

    def request_analysis(self) -> None:
        self.pending_commands.put("analyse")

    def request_position_read(self, white_to_move: bool) -> None:
        self.pending_commands.put("read_position_white" if white_to_move else "read_position_black")

    def stop(self) -> None:
        self.stop_event.set()

    def start_engine(self) -> None:
        engine_path = find_engine_path()
        if engine_path is None:
            self.update_queue.put(WorkerUpdate(status_text="Engine tidak ditemukan. Jalankan: brew install stockfish"))
            return
        try:
            self.advisor = EngineAdvisor(engine_path)
        except Exception as error:
            self.update_queue.put(WorkerUpdate(status_text=f"Engine gagal dijalankan: {error}"))
            return
        self.update_queue.put(WorkerUpdate(status_text="Engine siap"))

    def process_pending_commands(self) -> None:
        while not self.pending_commands.empty():
            command = self.pending_commands.get_nowait()
            if command == "new_game":
                self.tracker.reset()
                self.learning_requested = True
            elif command == "undo":
                self.tracker.undo_last_move()
            elif command.startswith("read_position_"):
                self.position_read_request = command == "read_position_white"
            self.change_detector.reset()
            self.mismatch_streak = 0
            self.analysis_needed = True

    def learn_pieces_from_screen(self, reader_settings: ReaderSettings) -> None:
        self.learning_requested = False
        try:
            image = capture_board(reader_settings.board_rect)
        except Exception as error:
            self.pending_status = f"Gagal capture layar: {error}"
            return
        white_at_bottom = self.recognizer.learn_start_position(image)
        if white_at_bottom is None:
            self.pending_status = "Bidak belum direkam: papan di layar bukan posisi awal"
            return
        self.detected_white_at_bottom = white_at_bottom
        self.learned_this_session = True
        self.pending_status = f"Bidak direkam dari posisi awal, {'Putih' if white_at_bottom else 'Hitam'} di bawah"

    def read_position_from_screen(self, reader_settings: ReaderSettings, white_to_move: bool) -> None:
        self.position_read_request = None
        if not self.recognizer.has_templates:
            self.pending_status = "Rekam bidak dulu: buka papan di posisi awal lalu tekan Game baru"
            return
        try:
            image = capture_board(reader_settings.board_rect)
        except Exception as error:
            self.pending_status = f"Gagal capture layar: {error}"
            return
        pieces, _ = self.recognize_with_orientation(image, reader_settings.white_at_bottom)
        if pieces is None:
            self.pending_status = UNKNOWN_PIECE_SET_STATUS
            return
        board = board_from_pieces(pieces, white_to_move)
        if board is None:
            self.pending_status = "Posisi di layar tidak valid. Cek posisi kotak dan arah papan"
            return
        self.tracker.set_position(board)
        self.change_detector.reset()
        self.analysis_needed = True
        self.pending_status = f"Posisi dibaca dari layar ({self.recognizer.active_piece_set_name}), {'Putih' if white_to_move else 'Hitam'} jalan"

    def infer_white_to_move(self, pieces) -> bool:
        previous_board = self.tracker.board
        arriving_colors = {piece.color for square, piece in pieces.items() if previous_board.piece_at(square) != piece}
        if arriving_colors == {True}:
            return False
        if arriving_colors == {False}:
            return True
        return previous_board.turn

    @staticmethod
    def board_fen_of(pieces) -> str:
        board = chess.Board(None)
        board.set_piece_map(pieces)
        return board.board_fen()

    def flip_orientation(self, white_at_bottom: bool) -> None:
        self.detected_white_at_bottom = white_at_bottom
        self.pending_status = f"Arah papan dikoreksi otomatis: {'Putih' if white_at_bottom else 'Hitam'} di bawah"

    def recognize_with_orientation(self, image, white_at_bottom: bool):
        cells = self.recognizer.recognize_cells(image)
        if cells is None:
            return None, False
        current_pieces = pieces_on_squares(cells, white_at_bottom)
        if self.tracker.is_consistent_with(self.board_fen_of(current_pieces)):
            return current_pieces, False
        flipped_pieces = pieces_on_squares(cells, not white_at_bottom)
        if self.tracker.is_consistent_with(self.board_fen_of(flipped_pieces)):
            self.flip_orientation(not white_at_bottom)
            return flipped_pieces, True
        if infer_white_at_bottom(cells) == (not white_at_bottom):
            self.flip_orientation(not white_at_bottom)
            return flipped_pieces, True
        return current_pieces, False

    def resync_from_screen(self, image, white_at_bottom: bool, signatures) -> str | None:
        if not self.recognizer.has_templates:
            return None
        pieces, _ = self.recognize_with_orientation(image, white_at_bottom)
        if pieces is None:
            return None
        return self.apply_screen_position(pieces, signatures)

    def apply_screen_position(self, pieces, signatures) -> str | None:
        board = board_from_pieces(pieces, self.infer_white_to_move(pieces))
        if board is not None and board.board_fen() == chess.STARTING_BOARD_FEN:
            board = chess.Board()
        if board is None or board.board_fen() == self.tracker.board.board_fen():
            return None
        self.tracker.set_position(board)
        self.change_detector.accept(signatures)
        self.mismatch_streak = 0
        self.analysis_needed = True
        self.pending_status = f"Posisi dibaca dari layar ({self.recognizer.active_piece_set_name}), {'Putih' if board.turn else 'Hitam'} jalan"
        return self.pending_status

    def reset_baseline_when_layout_changes(self, reader_settings: ReaderSettings) -> None:
        board_layout = (reader_settings.board_rect, reader_settings.white_at_bottom, reader_settings.site_profile)
        if board_layout != self.last_board_layout:
            self.change_detector.reset()
            self.last_board_layout = board_layout

    def read_board(self, reader_settings: ReaderSettings) -> tuple[str, tuple[str, ...] | None]:
        try:
            image = capture_board(reader_settings.board_rect)
        except Exception as error:
            return f"Gagal capture layar: {error}", None
        if reader_settings.site_profile is None:
            return self.read_board_by_square_changes(image, reader_settings.white_at_bottom)
        return self.read_board_by_highlight(image, reader_settings)

    def learn_automatically_from_start_position(self, image) -> None:
        if not looks_like_start_position(occupied_square_indices(image)):
            return
        white_at_bottom = self.recognizer.learn_start_position(image)
        if white_at_bottom is None:
            return
        self.learned_this_session = True
        self.detected_white_at_bottom = white_at_bottom
        self.tracker.reset()
        self.change_detector.reset()
        self.mismatch_streak = 0
        self.analysis_needed = True
        self.pending_status = f"Posisi awal terlihat: bidak direkam otomatis, {'Putih' if white_at_bottom else 'Hitam'} di bawah"

    def read_board_by_square_changes(self, image, white_at_bottom: bool) -> tuple[str, tuple[str, ...] | None]:
        if not self.learned_this_session:
            self.learn_automatically_from_start_position(image)
            if self.learned_this_session:
                return self.pending_status, None
        signatures = square_signatures(image)
        if self.recognizer.has_templates and self.change_detector.reference is None:
            self.change_detector.observe(signatures)
            return self.sync_with_screen_on_first_frame(image, white_at_bottom, signatures)
        changed_indices = self.change_detector.observe(signatures)
        if changed_indices is None:
            return "Membaca papan, menunggu langkah", None
        changed_squares = tuple(sorted(square_name(index % 8, index // 8, white_at_bottom) for index in changed_indices))
        if self.recognizer.has_templates:
            return self.read_moves_by_recognition(image, white_at_bottom, signatures, changed_squares)
        return self.read_moves_by_occupancy(image, white_at_bottom, signatures, changed_squares)

    def read_moves_by_occupancy(self, image, white_at_bottom: bool, signatures, changed_squares: tuple[str, ...]) -> tuple[str, tuple[str, ...] | None]:
        occupied_squares = frozenset(square_name(index % 8, index // 8, white_at_bottom) for index in occupied_square_indices(image))
        moves = self.tracker.apply_changed_squares(frozenset(changed_squares), occupied_squares)
        if moves is None:
            return f"Langkah tidak cocok ({', '.join(changed_squares)}). {UNKNOWN_PIECE_SET_STATUS}", changed_squares
        return self.accept_detected_moves(moves, signatures, changed_squares)

    def sync_with_screen_on_first_frame(self, image, white_at_bottom: bool, signatures) -> tuple[str, tuple[str, ...] | None]:
        pieces, _ = self.recognize_with_orientation(image, white_at_bottom)
        if pieces is None:
            return UNKNOWN_PIECE_SET_STATUS, None
        sync_status = self.apply_screen_position(pieces, signatures)
        return sync_status or self.pending_status or f"Membaca papan ({self.recognizer.active_piece_set_name}), menunggu langkah", None

    def read_moves_by_recognition(self, image, white_at_bottom: bool, signatures, changed_squares: tuple[str, ...]) -> tuple[str, tuple[str, ...] | None]:
        pieces, orientation_was_corrected = self.recognize_with_orientation(image, white_at_bottom)
        if pieces is None:
            return self.read_moves_by_occupancy(image, white_at_bottom, signatures, changed_squares)
        if orientation_was_corrected:
            return self.apply_screen_position(pieces, signatures) or self.pending_status, None
        recognized_board = chess.Board(None)
        recognized_board.set_piece_map(pieces)
        recognized_board_fen = recognized_board.board_fen()
        if recognized_board_fen == self.tracker.board.board_fen():
            self.change_detector.accept(signatures)
            self.mismatch_streak = 0
            return "Membaca papan, menunggu langkah", None
        if recognized_board_fen == chess.STARTING_BOARD_FEN:
            self.tracker.reset()
            self.change_detector.accept(signatures)
            self.mismatch_streak = 0
            self.analysis_needed = True
            self.pending_status = "Game baru terlihat di papan, posisi direset"
            return self.pending_status, None
        moves = self.tracker.find_moves_reaching(recognized_board_fen)
        if moves is not None:
            self.tracker.apply_moves(moves)
            return self.accept_detected_moves(moves, signatures, changed_squares)
        self.mismatch_streak += 1
        if self.mismatch_streak >= MISMATCHES_BEFORE_RESYNC:
            resync_status = self.resync_from_screen(image, white_at_bottom, signatures)
            if resync_status:
                return resync_status, changed_squares
        return f"Menunggu langkah selesai, petak berubah: {', '.join(changed_squares)}", changed_squares

    def accept_detected_moves(self, moves, signatures, changed_squares: tuple[str, ...]) -> tuple[str, tuple[str, ...] | None]:
        self.change_detector.accept(signatures)
        self.mismatch_streak = 0
        self.analysis_needed = True
        return f"Langkah terbaca: {' '.join(move.uci() for move in moves)}", changed_squares

    def read_board_by_highlight(self, image, reader_settings: ReaderSettings) -> tuple[str, tuple[str, ...] | None]:
        squares = find_highlighted_squares(
            image,
            reader_settings.site_profile,
            reader_settings.white_at_bottom,
            reader_settings.color_tolerance,
        )
        if squares is None:
            return "Membaca papan, belum ada highlight langkah", None
        move = self.tracker.apply_highlighted_squares(squares)
        if move is not None:
            self.analysis_needed = True
            return f"Langkah terbaca: {move.uci()}", squares
        return f"Highlight: {squares[0]} dan {squares[1]}", squares

    def analyse_position(self, think_seconds: float) -> Advice | None:
        if self.advisor is None:
            return None
        try:
            return self.advisor.advise(self.tracker.board, think_seconds, ENGINE_LINE_COUNT)
        except Exception as error:
            self.update_queue.put(WorkerUpdate(status_text=f"Analisis gagal: {error}"))
            return None

    def run(self) -> None:
        self.start_engine()
        while not self.stop_event.is_set():
            self.process_pending_commands()
            reader_settings = self.current_reader_settings()
            status_text = "Dijeda"
            highlighted_squares = None
            self.reset_baseline_when_layout_changes(reader_settings)
            if reader_settings.board_rect and self.learning_requested:
                self.learn_pieces_from_screen(reader_settings)
            if reader_settings.board_rect and self.position_read_request is not None:
                self.read_position_from_screen(reader_settings, self.position_read_request)
            if reader_settings.is_reading and reader_settings.board_rect:
                status_text, highlighted_squares = self.read_board(reader_settings)
            if self.pending_status:
                self.sticky_status, self.pending_status = self.pending_status, None
                self.sticky_status_polls_left = STICKY_STATUS_POLLS
            if self.sticky_status_polls_left > 0:
                status_text = self.sticky_status
                self.sticky_status_polls_left -= 1
            advice = None
            if self.analysis_needed:
                self.analysis_needed = False
                advice = self.analyse_position(reader_settings.think_seconds)
            self.update_queue.put(
                WorkerUpdate(
                    status_text=status_text,
                    highlighted_squares=highlighted_squares,
                    advice=advice,
                    move_history_san=self.tracker.move_history_san(),
                    detected_white_at_bottom=self.detected_white_at_bottom,
                )
            )
            self.detected_white_at_bottom = None
            self.stop_event.wait(POLL_INTERVAL_SECONDS)
        if self.advisor is not None:
            self.advisor.close()
