import queue
import tkinter as tk

import chess

from advisor_worker import AdvisorWorker, ReaderSettings, WorkerUpdate
from engine_advisor import Advice
from board_overlay_factory import create_board_overlay, keep_panel_on_top, overlay_draws_on_board
from overlay_shapes import OverlayArrow, OverlayState, clamp_board_size
from settings_store import load_settings, save_settings
from site_profiles import CHANGE_DETECTION_NAME, load_site_profiles

PANEL_WIDTH = 290
PANEL_GAP = 12
RESIZE_STEP = 20
THINK_TIME_CHOICES = (0.3, 0.5, 0.8, 1.2, 2.0, 3.0, 5.0)
UPDATE_POLL_MILLISECONDS = 30

PANEL_BACKGROUND = "#1d1f24"
BUTTON_BACKGROUND = "#33373f"
BUTTON_ACTIVE_BACKGROUND = "#4a8cff"
TEXT_COLOR = "#e8e8e8"
MUTED_TEXT_COLOR = "#9aa0aa"
BEST_MOVE_COLOR = "#ffb02e"
PLAYER_ARROW_COLOR = "#ff5a1f"
OPPONENT_ARROW_COLOR = "#8fa3c0"


class OverlayApp:
    def __init__(self) -> None:
        self.settings = load_settings()
        self.site_profiles = load_site_profiles()
        if self.settings.site_name not in self.site_profiles:
            self.settings.site_name = CHANGE_DETECTION_NAME
        self.settings.board_size = clamp_board_size(self.settings.board_size)
        self.is_locked = False
        self.is_reading = False
        self.latest_advice: Advice | None = None
        self.highlighted_squares: tuple[str, ...] | None = None

        self.root = tk.Tk()
        self.root.title("Chess Overlay")
        self.root.configure(bg=PANEL_BACKGROUND)
        self.root.resizable(False, False)
        self.root.attributes("-topmost", True)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

        self.site_name_variable = tk.StringVar(value=self.settings.site_name)
        self.site_name_variable.trace_add("write", self.handle_site_change)
        self.build_side_panel()

        self.board_overlay = create_board_overlay(self.root, self.settings.x, self.settings.y, self.settings.board_size)
        self.handle_board_geometry_change(*self.board_overlay.geometry())
        self.refresh_board_overlay()
        self.root.update_idletasks()
        self.root.after(200, lambda: keep_panel_on_top(self.root))

        self.update_queue: queue.Queue[WorkerUpdate] = queue.Queue()
        self.worker = AdvisorWorker(self.update_queue)
        self.worker.start()

        self.root.after(UPDATE_POLL_MILLISECONDS, self.poll_worker_updates)

    def run(self) -> None:
        self.root.mainloop()

    def create_flat_button(self, parent: tk.Widget, text: str, command) -> tk.Label:
        button = tk.Label(parent, text=text, bg=BUTTON_BACKGROUND, fg=TEXT_COLOR, padx=8, pady=4, font=("Helvetica", 12), cursor="hand2")
        button.bind("<Button-1>", lambda event: command())
        return button

    def build_side_panel(self) -> None:
        self.side_panel = tk.Frame(self.root, bg=PANEL_BACKGROUND, padx=12, pady=10, width=PANEL_WIDTH)
        self.side_panel.pack(fill="both", expand=True)

        def add_label(text: str = "", font_size: int = 12, color: str = TEXT_COLOR, bold: bool = False) -> tk.Label:
            label = tk.Label(
                self.side_panel,
                text=text,
                bg=PANEL_BACKGROUND,
                fg=color,
                font=("Helvetica", font_size, "bold" if bold else "normal"),
                justify="left",
                anchor="w",
                wraplength=PANEL_WIDTH - 24,
            )
            label.pack(fill="x", anchor="w")
            return label

        def add_button_row() -> tk.Frame:
            row = tk.Frame(self.side_panel, bg=PANEL_BACKGROUND)
            row.pack(fill="x", pady=3)
            return row

        def add_divider() -> None:
            tk.Frame(self.side_panel, bg=BUTTON_BACKGROUND, height=1).pack(fill="x", pady=8)

        add_label("Saran langkah", 11, MUTED_TEXT_COLOR)
        self.best_move_label = add_label("–", 28, BEST_MOVE_COLOR, bold=True)
        self.best_move_detail_label = add_label("Atur kotak sampai pas dengan papan, lalu tekan Mulai", 12, MUTED_TEXT_COLOR)
        self.evaluation_label = add_label("", 14, TEXT_COLOR, bold=True)
        self.engine_lines_label = add_label("", 11, TEXT_COLOR)

        add_divider()

        control_row = add_button_row()
        self.reading_button = self.create_flat_button(control_row, "▶ Mulai", self.toggle_reading)
        self.reading_button.pack(side="left", padx=(0, 4))
        self.create_flat_button(control_row, "↺ Game baru", self.start_new_game).pack(side="left", padx=4)
        self.create_flat_button(control_row, "↶ Mundur", self.undo_last_move).pack(side="left", padx=4)

        position_row = add_button_row()
        tk.Label(position_row, text="Baca posisi", bg=PANEL_BACKGROUND, fg=MUTED_TEXT_COLOR, font=("Helvetica", 12)).pack(side="left")
        self.create_flat_button(position_row, "Putih jalan", lambda: self.worker.request_position_read(True)).pack(side="left", padx=(8, 4))
        self.create_flat_button(position_row, "Hitam jalan", lambda: self.worker.request_position_read(False)).pack(side="left", padx=4)

        lock_row = add_button_row()
        self.lock_button = self.create_flat_button(lock_row, "", self.toggle_lock)
        self.lock_button.pack(side="left")

        size_row = add_button_row()
        self.create_flat_button(size_row, "− Perkecil", lambda: self.change_board_size(-RESIZE_STEP)).pack(side="left", padx=(0, 4))
        self.create_flat_button(size_row, "+ Perbesar", lambda: self.change_board_size(RESIZE_STEP)).pack(side="left", padx=4)
        self.board_size_label = tk.Label(size_row, bg=PANEL_BACKGROUND, fg=MUTED_TEXT_COLOR, font=("Helvetica", 11))
        self.board_size_label.pack(side="left", padx=4)

        site_row = add_button_row()
        tk.Label(site_row, text="Cara baca", bg=PANEL_BACKGROUND, fg=MUTED_TEXT_COLOR, font=("Helvetica", 12)).pack(side="left")
        site_names = [CHANGE_DETECTION_NAME, *self.site_profiles]
        site_menu = tk.OptionMenu(site_row, self.site_name_variable, *site_names)
        site_menu.configure(bg=BUTTON_BACKGROUND, fg=TEXT_COLOR, highlightthickness=0, borderwidth=0, font=("Helvetica", 12))
        site_menu.pack(side="left", padx=8)

        orientation_row = add_button_row()
        tk.Label(orientation_row, text="Bawah papan", bg=PANEL_BACKGROUND, fg=MUTED_TEXT_COLOR, font=("Helvetica", 12)).pack(side="left")
        self.white_bottom_button = self.create_flat_button(orientation_row, "Putih", lambda: self.set_white_at_bottom(True))
        self.white_bottom_button.pack(side="left", padx=(8, 4))
        self.black_bottom_button = self.create_flat_button(orientation_row, "Hitam", lambda: self.set_white_at_bottom(False))
        self.black_bottom_button.pack(side="left", padx=4)

        think_row = add_button_row()
        tk.Label(think_row, text="Waktu pikir", bg=PANEL_BACKGROUND, fg=MUTED_TEXT_COLOR, font=("Helvetica", 12)).pack(side="left")
        self.create_flat_button(think_row, "−", lambda: self.change_think_time(-1)).pack(side="left", padx=(8, 4))
        self.think_time_label = tk.Label(think_row, bg=PANEL_BACKGROUND, fg=TEXT_COLOR, font=("Helvetica", 12), width=5)
        self.think_time_label.pack(side="left")
        self.create_flat_button(think_row, "+", lambda: self.change_think_time(1)).pack(side="left", padx=4)

        add_divider()

        add_label("Langkah game", 11, MUTED_TEXT_COLOR)
        self.move_history_label = add_label("–", 11, TEXT_COLOR)
        self.status_label = add_label("Menyiapkan engine…", 10, MUTED_TEXT_COLOR)
        self.engine_name_label = add_label("", 10, MUTED_TEXT_COLOR)
        if not overlay_draws_on_board():
            add_label("Di sistem ini panah tidak digambar di atas papan, saran hanya tampil di panel", 10, MUTED_TEXT_COLOR)

        self.refresh_panel_controls()

    def handle_board_geometry_change(self, left: int, top: int, board_size: int) -> None:
        self.settings.x, self.settings.y, self.settings.board_size = left, top, board_size
        self.board_size_label.configure(text=f"{board_size} px")
        self.root.geometry(f"+{left + board_size + PANEL_GAP}+{top}")

    def commit_board_geometry(self, left: int, top: int, board_size: int) -> None:
        self.handle_board_geometry_change(left, top, board_size)
        save_settings(self.settings)

    def change_board_size(self, size_change: int) -> None:
        self.board_overlay.set_geometry(self.settings.x, self.settings.y, self.settings.board_size + size_change)
        self.commit_board_geometry(*self.board_overlay.geometry())

    def change_think_time(self, step: int) -> None:
        current_index = min(
            range(len(THINK_TIME_CHOICES)),
            key=lambda index: abs(THINK_TIME_CHOICES[index] - self.settings.think_seconds),
        )
        next_index = max(0, min(len(THINK_TIME_CHOICES) - 1, current_index + step))
        self.settings.think_seconds = THINK_TIME_CHOICES[next_index]
        self.refresh_panel_controls()
        save_settings(self.settings)

    def set_white_at_bottom(self, white_at_bottom: bool) -> None:
        self.settings.white_at_bottom = white_at_bottom
        self.refresh_panel_controls()
        self.refresh_board_overlay()
        save_settings(self.settings)

    def handle_site_change(self, *unused_trace_arguments) -> None:
        self.settings.site_name = self.site_name_variable.get()
        save_settings(self.settings)

    def toggle_lock(self) -> None:
        self.is_locked = not self.is_locked
        if not self.is_locked:
            self.is_reading = False
        self.refresh_panel_controls()
        self.refresh_board_overlay()

    def toggle_reading(self) -> None:
        self.is_reading = not self.is_reading
        if self.is_reading:
            self.is_locked = True
        self.refresh_panel_controls()
        self.refresh_board_overlay()

    def start_new_game(self) -> None:
        self.latest_advice = None
        self.highlighted_squares = None
        self.worker.request_new_game()
        self.refresh_board_overlay()

    def undo_last_move(self) -> None:
        self.worker.request_undo()

    def refresh_panel_controls(self) -> None:
        self.lock_button.configure(text="🔒 Terkunci (tembus klik)" if self.is_locked else "🔓 Mode atur kotak")
        self.reading_button.configure(
            text="⏸ Jeda" if self.is_reading else "▶ Mulai",
            bg=BUTTON_ACTIVE_BACKGROUND if self.is_reading else BUTTON_BACKGROUND,
        )
        self.white_bottom_button.configure(bg=BUTTON_ACTIVE_BACKGROUND if self.settings.white_at_bottom else BUTTON_BACKGROUND)
        self.black_bottom_button.configure(bg=BUTTON_BACKGROUND if self.settings.white_at_bottom else BUTTON_ACTIVE_BACKGROUND)
        self.think_time_label.configure(text=f"{self.settings.think_seconds:g} s")

    def arrow_color_for(self, advice: Advice) -> str:
        player_is_to_move = advice.white_to_move == self.settings.white_at_bottom
        return PLAYER_ARROW_COLOR if player_is_to_move else OPPONENT_ARROW_COLOR

    def refresh_board_overlay(self) -> None:
        arrow = None
        if self.latest_advice and self.latest_advice.best_move:
            arrow = OverlayArrow(
                from_square=chess.square_name(self.latest_advice.best_move.from_square),
                to_square=chess.square_name(self.latest_advice.best_move.to_square),
                color=self.arrow_color_for(self.latest_advice),
            )
        self.board_overlay.update_state(
            OverlayState(
                is_locked=self.is_locked,
                white_at_bottom=self.settings.white_at_bottom,
                highlighted_squares=self.highlighted_squares,
                arrow=arrow,
            )
        )

    def current_reader_settings(self) -> ReaderSettings:
        return ReaderSettings(
            board_rect=(self.settings.x, self.settings.y, self.settings.board_size),
            site_profile=self.site_profiles.get(self.settings.site_name),
            white_at_bottom=self.settings.white_at_bottom,
            color_tolerance=self.settings.color_tolerance,
            think_seconds=self.settings.think_seconds,
            is_reading=self.is_reading and self.is_locked,
        )

    def show_advice(self, advice: Advice) -> None:
        self.latest_advice = advice
        side_name = "Putih" if advice.white_to_move else "Hitam"
        if advice.game_over_text:
            self.best_move_label.configure(text="Selesai")
            self.best_move_detail_label.configure(text=advice.game_over_text)
            self.evaluation_label.configure(text="")
            self.engine_lines_label.configure(text="")
            return
        if advice.best_move is None:
            return
        player_is_to_move = advice.white_to_move == self.settings.white_at_bottom
        turn_text = "giliranmu" if player_is_to_move else "perkiraan balasan lawan"
        from_square = chess.square_name(advice.best_move.from_square)
        to_square = chess.square_name(advice.best_move.to_square)
        self.best_move_label.configure(text=advice.best_move_san)
        self.best_move_detail_label.configure(text=f"{from_square} → {to_square} · {side_name} jalan ({turn_text})")
        self.evaluation_label.configure(text=f"Evaluasi {advice.lines[0].score_text}")
        self.engine_lines_label.configure(
            text="\n".join(f"{line_number}. {line.score_text}  {line.san_text}" for line_number, line in enumerate(advice.lines, start=1))
        )

    def apply_worker_update(self, update: WorkerUpdate) -> bool:
        needs_redraw = update.highlighted_squares != self.highlighted_squares
        self.highlighted_squares = update.highlighted_squares
        self.status_label.configure(text=update.status_text)
        if update.engine_name:
            self.engine_name_label.configure(text=f"Engine: {update.engine_name}")
        if update.detected_white_at_bottom is not None and update.detected_white_at_bottom != self.settings.white_at_bottom:
            self.set_white_at_bottom(update.detected_white_at_bottom)
            needs_redraw = True
        if update.move_history_san is not None:
            self.move_history_label.configure(text=update.move_history_san or "–")
        if update.advice is not None:
            self.show_advice(update.advice)
            needs_redraw = True
        return needs_redraw

    def apply_pending_board_geometry(self) -> None:
        geometry_update = self.board_overlay.take_pending_geometry()
        if geometry_update is None:
            return
        board_geometry, is_final = geometry_update
        if is_final:
            self.commit_board_geometry(*board_geometry)
        else:
            self.handle_board_geometry_change(*board_geometry)

    def poll_worker_updates(self) -> None:
        self.apply_pending_board_geometry()
        self.worker.update_reader_settings(self.current_reader_settings())
        needs_redraw = False
        while not self.update_queue.empty():
            needs_redraw = self.apply_worker_update(self.update_queue.get_nowait()) or needs_redraw
        if needs_redraw:
            self.refresh_board_overlay()
        self.root.after(UPDATE_POLL_MILLISECONDS, self.poll_worker_updates)

    def close(self) -> None:
        save_settings(self.settings)
        self.worker.stop()
        self.worker.join(timeout=3)
        self.board_overlay.close()
        self.root.destroy()
