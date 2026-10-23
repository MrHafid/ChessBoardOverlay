import shutil
from dataclasses import dataclass, field
from pathlib import Path

import chess
import chess.engine

from project_paths import NAUTILUS_DIRECTORY

MAXIMUM_LINE_PLIES = 6


@dataclass(frozen=True)
class EngineLine:
    moves: list[chess.Move]
    score_text: str
    san_text: str


@dataclass(frozen=True)
class Advice:
    white_to_move: bool
    best_move: chess.Move | None = None
    best_move_san: str = ""
    lines: list[EngineLine] = field(default_factory=list)
    game_over_text: str = ""


def find_engine_path() -> str | None:
    candidates = [
        shutil.which("stockfish"),
        "/opt/homebrew/bin/stockfish",
        "/usr/local/bin/stockfish",
        str(NAUTILUS_DIRECTORY / "engines" / "darwin" / "komodo-13.02-64-osx"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    return None


def format_score(score: chess.engine.PovScore) -> str:
    white_score = score.white()
    mate_in = white_score.mate()
    if mate_in is not None:
        return f"#{mate_in}" if mate_in > 0 else f"#-{abs(mate_in)}"
    return f"{white_score.score() / 100:+.2f}"


def describe_game_over(board: chess.Board) -> str:
    outcome = board.outcome()
    if outcome is None:
        return ""
    if outcome.winner is None:
        return "Remis"
    winner_name = "Putih" if outcome.winner == chess.WHITE else "Hitam"
    if outcome.termination == chess.Termination.CHECKMATE:
        return f"Skakmat, {winner_name} menang"
    return f"{winner_name} menang"


class EngineAdvisor:
    def __init__(self, engine_path: str) -> None:
        self.engine = chess.engine.SimpleEngine.popen_uci(engine_path)
        self.engine_name = self.engine.id.get("name", Path(engine_path).name)

    def advise(self, board: chess.Board, think_seconds: float, line_count: int) -> Advice:
        if board.is_game_over():
            return Advice(white_to_move=board.turn == chess.WHITE, game_over_text=describe_game_over(board))
        analysis = self.engine.analyse(board, chess.engine.Limit(time=think_seconds), multipv=line_count)
        infos = analysis if isinstance(analysis, list) else [analysis]
        lines = [
            EngineLine(
                moves=info["pv"],
                score_text=format_score(info["score"]),
                san_text=board.variation_san(info["pv"][:MAXIMUM_LINE_PLIES]),
            )
            for info in infos
            if info.get("pv") and "score" in info
        ]
        best_move = lines[0].moves[0] if lines else None
        return Advice(
            white_to_move=board.turn == chess.WHITE,
            best_move=best_move,
            best_move_san=board.san(best_move) if best_move else "",
            lines=lines,
        )

    def close(self) -> None:
        self.engine.quit()
