import sys
import tkinter as tk


def overlay_draws_on_board() -> bool:
    return sys.platform in ("darwin", "win32")


def create_board_overlay(root: tk.Tk, left: int, top: int, board_size: int):
    if sys.platform == "darwin":
        from native_board_overlay import NativeBoardOverlay

        return NativeBoardOverlay(root, left, top, board_size)
    if sys.platform == "win32":
        from tk_board_overlay import WindowsBoardOverlay

        return WindowsBoardOverlay(root, left, top, board_size)
    from tk_board_overlay import FrameBoardOverlay

    return FrameBoardOverlay(root, left, top, board_size)


def keep_panel_on_top(root: tk.Tk) -> None:
    if sys.platform == "darwin":
        from native_board_overlay import keep_window_floating

        keep_window_floating(root.title())
        return
    root.attributes("-topmost", True)
