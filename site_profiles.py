import ast
from dataclasses import dataclass
from pathlib import Path

from project_paths import NAUTILUS_DIRECTORY

RgbColor = tuple[int, int, int]
CHANGE_DETECTION_NAME = "Semua papan (perubahan petak)"


@dataclass(frozen=True)
class SiteProfile:
    name: str
    highlight_colors: tuple[RgbColor, ...]
    light_square_color: RgbColor


def parse_color_list(line: str) -> tuple[RgbColor, ...]:
    return tuple(tuple(int(channel) for channel in color) for color in ast.literal_eval(line))


def load_site_profiles(nautilus_directory: Path = NAUTILUS_DIRECTORY) -> dict[str, SiteProfile]:
    profiles: dict[str, SiteProfile] = {}
    for pixel_file in sorted((nautilus_directory / "images").glob("*/pixel.txt")):
        lines = [line.strip() for line in pixel_file.read_text().splitlines() if line.strip()]
        if len(lines) < 2:
            continue
        site_name = pixel_file.parent.name
        profiles[site_name] = SiteProfile(
            name=site_name,
            highlight_colors=parse_color_list(lines[0]),
            light_square_color=parse_color_list(lines[1])[0],
        )
    return profiles
