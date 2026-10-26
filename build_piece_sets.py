import io
import json
import shutil
import subprocess
import tempfile
import tkinter as tk
import urllib.request
from pathlib import Path

import chess
from PIL import Image, ImageGrab

from piece_recognizer import PieceRecognizer
from project_paths import PROJECT_DIRECTORY

PIECE_SETS_DIRECTORY = PROJECT_DIRECTORY / "piece_sets"
RENDER_SQUARE_SIZE = 100
BOARD_THEMES = (
    ((238, 238, 210), (118, 150, 86)),
    ((240, 217, 181), (181, 136, 99)),
    ((222, 227, 230), (140, 162, 173)),
)
CHESSCOM_PIECE_URL = "https://images.chesscomfiles.com/chess-themes/pieces/{piece_set}/150/{color}{piece}.png"
LICHESS_PIECE_URL = "https://lichess1.org/assets/piece/{piece_set}/{color}{piece}.svg"
PIECE_SYMBOLS = "PNBRQKpnbrqk"
SVG_RENDER_SIZE = 150
CHROME_CANDIDATES = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "google-chrome",
    "chromium",
    "chromium-browser",
)
NAUTILUS_LIGHT_SQUARE = "#eed8b5"
NAUTILUS_DARK_SQUARE = "#b58863"
NAUTILUS_WHITE_PIECE = "#666666"
NAUTILUS_GLYPHS = {"k": 9818, "q": 9819, "r": 9820, "b": 9821, "n": 9822, "p": 9823}
NAUTILUS_SQUARE_SIZE = 80
NAUTILUS_WINDOW_POSITION = (200, 200)
NAUTILUS_RENDER_WAIT_MILLISECONDS = 1500


def start_position_cells() -> list[tuple[int, int, chess.Piece]]:
    return [
        (chess.square_file(square), 7 - chess.square_rank(square), piece)
        for square, piece in chess.Board().piece_map().items()
    ]


def download_bytes(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request) as response:
        return response.read()


def find_chrome() -> str:
    for candidate in CHROME_CANDIDATES:
        resolved = candidate if Path(candidate).is_file() else shutil.which(candidate)
        if resolved:
            return resolved
    raise SystemExit("Chrome atau Chromium dibutuhkan untuk menggambar bidak SVG Lichess")


def download_lichess_pieces(piece_set: str) -> dict[str, Image.Image]:
    with tempfile.TemporaryDirectory() as temporary_directory:
        directory = Path(temporary_directory)
        for symbol in PIECE_SYMBOLS:
            color = "w" if symbol.isupper() else "b"
            svg_url = LICHESS_PIECE_URL.format(piece_set=piece_set, color=color, piece=symbol.upper())
            (directory / f"{symbol}{color}.svg").write_bytes(download_bytes(svg_url))
        images_markup = "".join(
            f'<img src="{symbol}{"w" if symbol.isupper() else "b"}.svg" width="{SVG_RENDER_SIZE}" height="{SVG_RENDER_SIZE}" style="display:block;float:left">'
            for symbol in PIECE_SYMBOLS
        )
        (directory / "pieces.html").write_text(f'<html><body style="margin:0;background:transparent">{images_markup}</body></html>')
        screenshot_path = directory / "pieces.png"
        subprocess.run(
            [
                find_chrome(),
                "--headless=new",
                "--disable-gpu",
                "--hide-scrollbars",
                "--default-background-color=00000000",
                f"--window-size={SVG_RENDER_SIZE * len(PIECE_SYMBOLS)},{SVG_RENDER_SIZE}",
                f"--screenshot={screenshot_path}",
                (directory / "pieces.html").as_uri(),
            ],
            check=True,
            capture_output=True,
            timeout=120,
        )
        strip = Image.open(screenshot_path).convert("RGBA")
        return {
            symbol: strip.crop((index * SVG_RENDER_SIZE, 0, (index + 1) * SVG_RENDER_SIZE, SVG_RENDER_SIZE))
            for index, symbol in enumerate(PIECE_SYMBOLS)
        }


def download_chesscom_pieces(piece_set: str) -> dict[str, Image.Image]:
    pieces = {}
    for symbol in PIECE_SYMBOLS:
        url = CHESSCOM_PIECE_URL.format(piece_set=piece_set, color="w" if symbol.isupper() else "b", piece=symbol.lower())
        pieces[symbol] = Image.open(io.BytesIO(download_bytes(url))).convert("RGBA")
    return pieces


def render_image_piece_board(pieces: dict[str, Image.Image], light_color, dark_color) -> Image.Image:
    board = Image.new("RGB", (8 * RENDER_SQUARE_SIZE, 8 * RENDER_SQUARE_SIZE))
    for row in range(8):
        for column in range(8):
            color = light_color if (row + column) % 2 == 0 else dark_color
            board.paste(color, (column * RENDER_SQUARE_SIZE, row * RENDER_SQUARE_SIZE, (column + 1) * RENDER_SQUARE_SIZE, (row + 1) * RENDER_SQUARE_SIZE))
    for column, row, piece in start_position_cells():
        piece_image = pieces[piece.symbol()].resize((RENDER_SQUARE_SIZE, RENDER_SQUARE_SIZE), Image.Resampling.LANCZOS)
        board.paste(piece_image, (column * RENDER_SQUARE_SIZE, row * RENDER_SQUARE_SIZE), piece_image)
    return board


def render_nautilus_board() -> Image.Image:
    root = tk.Tk()
    root.withdraw()
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    board_size = 8 * NAUTILUS_SQUARE_SIZE
    left, top = NAUTILUS_WINDOW_POSITION
    root.geometry(f"{board_size}x{board_size}+{left}+{top}")
    canvas = tk.Canvas(root, width=board_size, height=board_size, bg=NAUTILUS_LIGHT_SQUARE, highlightthickness=0)
    canvas.pack()
    for row in range(8):
        for column in range(8):
            if (row + column) % 2 == 1:
                canvas.create_rectangle(column * NAUTILUS_SQUARE_SIZE, row * NAUTILUS_SQUARE_SIZE, (column + 1) * NAUTILUS_SQUARE_SIZE, (row + 1) * NAUTILUS_SQUARE_SIZE, fill=NAUTILUS_DARK_SQUARE)
    for column, row, piece in start_position_cells():
        canvas.create_text(
            (column + 0.5) * NAUTILUS_SQUARE_SIZE,
            (row + 0.5) * NAUTILUS_SQUARE_SIZE,
            text=chr(NAUTILUS_GLYPHS[piece.symbol().lower()]),
            font="Times 40",
            fill="black" if piece.color == chess.BLACK else NAUTILUS_WHITE_PIECE,
        )
    captured_images = []

    def capture_and_close() -> None:
        canvas_left, canvas_top = canvas.winfo_rootx(), canvas.winfo_rooty()
        captured_images.append(ImageGrab.grab(bbox=(canvas_left, canvas_top, canvas_left + board_size, canvas_top + board_size)).convert("RGB"))
        root.destroy()

    root.deiconify()
    root.after(NAUTILUS_RENDER_WAIT_MILLISECONDS, capture_and_close)
    root.mainloop()
    return captured_images[0]


def templates_from_start_boards(boards: list[Image.Image]) -> list[dict]:
    templates = []
    for board in boards:
        with tempfile.TemporaryDirectory() as temporary_directory:
            recognizer = PieceRecognizer(Path(temporary_directory) / "templates.json")
            if recognizer.learn_start_position(board) is not True:
                raise SystemExit("Papan render tidak terbaca sebagai posisi awal")
            templates += [
                {"symbol": template.symbol, "color_feature": template.color_feature, "shape_feature": template.shape_feature}
                for template in recognizer.templates
            ]
    return templates


def save_piece_set(file_name: str, display_name: str, templates: list[dict]) -> None:
    PIECE_SETS_DIRECTORY.mkdir(exist_ok=True)
    (PIECE_SETS_DIRECTORY / file_name).write_text(json.dumps({"name": display_name, "templates": templates}))
    print(f"{display_name}: {len(templates)} rekaman bidak -> piece_sets/{file_name}")


def main() -> None:
    neo_pieces = download_chesscom_pieces("neo")
    save_piece_set(
        "chesscom_neo.json",
        "Chess.com Neo",
        templates_from_start_boards([render_image_piece_board(neo_pieces, light, dark) for light, dark in BOARD_THEMES]),
    )
    lichess_pieces = download_lichess_pieces("cburnett")
    save_piece_set(
        "lichess_cburnett.json",
        "Lichess cburnett",
        templates_from_start_boards([render_image_piece_board(lichess_pieces, light, dark) for light, dark in BOARD_THEMES]),
    )
    save_piece_set("nautilus.json", "NautilusChess", templates_from_start_boards([render_nautilus_board()]))


if __name__ == "__main__":
    main()
