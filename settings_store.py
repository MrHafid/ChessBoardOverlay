import json
from dataclasses import asdict, dataclass, fields

from project_paths import SETTINGS_FILE
from site_profiles import CHANGE_DETECTION_NAME


@dataclass
class OverlaySettings:
    x: int = 120
    y: int = 120
    board_size: int = 480
    site_name: str = CHANGE_DETECTION_NAME
    white_at_bottom: bool = True
    think_seconds: float = 0.8
    color_tolerance: int = 12


def load_settings() -> OverlaySettings:
    try:
        stored_values = json.loads(SETTINGS_FILE.read_text())
    except (OSError, ValueError):
        return OverlaySettings()
    known_names = {setting_field.name for setting_field in fields(OverlaySettings)}
    return OverlaySettings(**{name: value for name, value in stored_values.items() if name in known_names})


def save_settings(settings: OverlaySettings) -> None:
    SETTINGS_FILE.write_text(json.dumps(asdict(settings), indent=2))
