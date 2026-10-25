import chess

CASTLING_ALIASES = {
    "e1h1": "e1g1",
    "e1a1": "e1c1",
    "e8h8": "e8g8",
    "e8a8": "e8c8",
}


class GameTracker:
    def __init__(self) -> None:
        self.board = chess.Board()
        self.last_applied_squares: frozenset[str] | None = None
        self.previous_move_squares: frozenset[str] = frozenset()

    def reset(self) -> None:
        self.board = chess.Board()
        self.last_applied_squares = None
        self.previous_move_squares = frozenset()

    def find_legal_move(self, first_square: str, second_square: str) -> chess.Move | None:
        legal_moves = {move.uci(): move for move in self.board.legal_moves}
        for candidate in (first_square + second_square, second_square + first_square):
            for uci in (candidate, candidate + "q", CASTLING_ALIASES.get(candidate, "")):
                if uci in legal_moves:
                    return legal_moves[uci]
        return None

    def apply_highlighted_squares(self, squares: tuple[str, str]) -> chess.Move | None:
        squares_key = frozenset(squares)
        if squares_key == self.last_applied_squares:
            return None
        move = self.find_legal_move(*squares)
        if move is None:
            return None
        self.board.push(move)
        self.last_applied_squares = squares_key
        return move

    @staticmethod
    def squares_changed_by(board: chess.Board, moves: list[chess.Move]) -> frozenset[str]:
        before = board.piece_map()
        after_board = board.copy(stack=False)
        for move in moves:
            after_board.push(move)
        after = after_board.piece_map()
        return frozenset(chess.square_name(square) for square in chess.SQUARES if before.get(square) != after.get(square))

    @staticmethod
    def move_endpoint_squares(moves: list[chess.Move]) -> frozenset[str]:
        return frozenset(chess.square_name(square) for move in moves for square in (move.from_square, move.to_square))

    @staticmethod
    def changes_are_explained(expected: frozenset[str], changed: frozenset[str], tolerated: frozenset[str]) -> bool:
        return expected <= changed and changed - expected <= tolerated

    @staticmethod
    def most_explaining_candidate(candidates: list[tuple[frozenset[str], list[chess.Move]]]) -> list[chess.Move] | None:
        if not candidates:
            return None
        return max(
            candidates,
            key=lambda candidate: (len(candidate[0]), all(move.promotion in (None, chess.QUEEN) for move in candidate[1])),
        )[1]

    @staticmethod
    def occupancy_matches(board: chess.Board, moves: list[chess.Move], expected: frozenset[str], occupied_squares: frozenset[str] | None) -> bool:
        if occupied_squares is None:
            return True
        after_board = board.copy(stack=False)
        for move in moves:
            after_board.push(move)
        return all(
            (after_board.piece_at(chess.parse_square(square)) is not None) == (square in occupied_squares)
            for square in expected
        )

    def find_moves_for_changed_squares(self, changed_squares: frozenset[str], occupied_squares: frozenset[str] | None = None) -> list[chess.Move] | None:
        tolerated = self.previous_move_squares
        single_candidates = []
        for move in self.board.legal_moves:
            expected = self.squares_changed_by(self.board, [move])
            if self.changes_are_explained(expected, changed_squares, tolerated) and self.occupancy_matches(self.board, [move], expected, occupied_squares):
                single_candidates.append((expected, [move]))
        if single_candidates:
            return self.most_explaining_candidate(single_candidates)
        pair_candidates = []
        for first_move in self.board.legal_moves:
            self.board.push(first_move)
            reply_moves = [move for move in self.board.legal_moves if move.promotion in (None, chess.QUEEN)]
            self.board.pop()
            pair_tolerated = tolerated | self.move_endpoint_squares([first_move])
            for reply_move in reply_moves:
                expected = self.squares_changed_by(self.board, [first_move, reply_move])
                if self.changes_are_explained(expected, changed_squares, pair_tolerated) and self.occupancy_matches(
                    self.board, [first_move, reply_move], expected, occupied_squares
                ):
                    pair_candidates.append((expected, [first_move, reply_move]))
        return self.most_explaining_candidate(pair_candidates)

    def apply_changed_squares(self, changed_squares: frozenset[str], occupied_squares: frozenset[str] | None = None) -> list[chess.Move] | None:
        moves = self.find_moves_for_changed_squares(changed_squares, occupied_squares)
        if moves is None:
            return None
        self.apply_moves(moves)
        return moves

    def undo_last_move(self) -> None:
        self.previous_move_squares = frozenset()
        if self.board.move_stack:
            self.board.pop()

    @staticmethod
    def single_move_reaching(board: chess.Board, target_board_fen: str) -> chess.Move | None:
        for move in list(board.legal_moves):
            board.push(move)
            reached = board.board_fen() == target_board_fen
            board.pop()
            if reached:
                return move
        return None

    def correct_turn_if_opponent_moved(self, target_board_fen: str) -> chess.Move | None:
        flipped_board = self.board.copy(stack=False)
        flipped_board.turn = not flipped_board.turn
        flipped_board.ep_square = None
        if not flipped_board.is_valid():
            return None
        move = self.single_move_reaching(flipped_board, target_board_fen)
        if move is not None:
            self.set_position(flipped_board)
        return move

    def find_moves_reaching(self, target_board_fen: str) -> list[chess.Move] | None:
        single_move = self.single_move_reaching(self.board, target_board_fen)
        if single_move is not None:
            return [single_move]
        corrected_move = self.correct_turn_if_opponent_moved(target_board_fen)
        if corrected_move is not None:
            return [corrected_move]
        for first_move in list(self.board.legal_moves):
            self.board.push(first_move)
            for reply_move in list(self.board.legal_moves):
                self.board.push(reply_move)
                reached_after_reply = self.board.board_fen() == target_board_fen
                self.board.pop()
                if reached_after_reply:
                    self.board.pop()
                    return [first_move, reply_move]
            self.board.pop()
        return None

    def is_consistent_with(self, target_board_fen: str) -> bool:
        if target_board_fen in (self.board.board_fen(), chess.STARTING_BOARD_FEN):
            return True
        probe = GameTracker()
        probe.board = self.board.copy(stack=False)
        return probe.find_moves_reaching(target_board_fen) is not None

    def apply_moves(self, moves: list[chess.Move]) -> None:
        self.previous_move_squares = self.squares_changed_by(self.board, moves) | self.move_endpoint_squares(moves)
        for move in moves:
            self.board.push(move)
        self.last_applied_squares = None

    def set_position(self, board: chess.Board) -> None:
        self.board = board
        self.last_applied_squares = None
        self.previous_move_squares = frozenset()

    def move_history_san(self) -> str:
        return self.board.root().variation_san(self.board.move_stack)
