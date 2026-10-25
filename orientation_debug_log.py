import json
import time

from PIL import Image

from project_paths import DATA_DIRECTORY

ORIENTATION_DEBUG_DIRECTORY = DATA_DIRECTORY / "debug_orientation"
MAXIMUM_DEBUG_RECORDS = 20


def remove_oldest_records() -> None:
    records = sorted(ORIENTATION_DEBUG_DIRECTORY.glob("*.json"))
    for old_record in records[:-MAXIMUM_DEBUG_RECORDS]:
        old_record.unlink(missing_ok=True)
        old_record.with_suffix(".png").unlink(missing_ok=True)


def record_orientation_change(reason: str, image: Image.Image | None, details: dict) -> None:
    try:
        ORIENTATION_DEBUG_DIRECTORY.mkdir(parents=True, exist_ok=True)
        now = time.time()
        record_name = time.strftime("%Y%m%d-%H%M%S", time.localtime(now)) + f"-{int(now * 1000) % 1000:03d}"
        if image is not None:
            image.save(ORIENTATION_DEBUG_DIRECTORY / f"{record_name}.png")
        record = {"time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now)), "reason": reason, **details}
        (ORIENTATION_DEBUG_DIRECTORY / f"{record_name}.json").write_text(json.dumps(record, indent=2))
        remove_oldest_records()
    except OSError:
        pass
