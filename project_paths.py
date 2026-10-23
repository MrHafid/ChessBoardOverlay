import os
import sys
from pathlib import Path

PROJECT_DIRECTORY = Path(__file__).resolve().parent
IS_FROZEN_BUILD = getattr(sys, "frozen", False)
APPLICATION_NAME = "ChessBoardOverlay"


def user_data_directory() -> Path:
    if sys.platform == "darwin":
        base_directory = Path.home() / "Library" / "Application Support"
    elif sys.platform == "win32":
        base_directory = Path(os.environ.get("APPDATA", Path.home()))
    else:
        base_directory = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    directory = base_directory / APPLICATION_NAME
    directory.mkdir(parents=True, exist_ok=True)
    return directory


if IS_FROZEN_BUILD:
    BUNDLE_DIRECTORY = Path(getattr(sys, "_MEIPASS", PROJECT_DIRECTORY))
    DATA_DIRECTORY = user_data_directory()
    NAUTILUS_DIRECTORY = BUNDLE_DIRECTORY / "NautilusChess"
else:
    BUNDLE_DIRECTORY = PROJECT_DIRECTORY
    DATA_DIRECTORY = PROJECT_DIRECTORY
    NAUTILUS_DIRECTORY = PROJECT_DIRECTORY.parent / "NautilusChess"

BUNDLED_ENGINE_DIRECTORY = BUNDLE_DIRECTORY / "engines"
SETTINGS_FILE = DATA_DIRECTORY / "settings.json"
PIECE_TEMPLATES_FILE = DATA_DIRECTORY / "piece_templates.json"
