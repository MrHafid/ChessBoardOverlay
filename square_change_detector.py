from PIL import Image

SAMPLES_PER_SQUARE_SIDE = 16
IGNORED_EDGE_SAMPLES = 2
PIXEL_CHANGE_THRESHOLD = 60
CHANGED_SAMPLE_FRACTION = 0.03
STABLE_FRAMES_REQUIRED = 2
FOREGROUND_PIXEL_THRESHOLD = 70
OCCUPIED_SAMPLE_FRACTION = 0.04
BACKGROUND_RING_INSET = 1

SquareSignature = tuple[tuple[int, int, int], ...]
RgbSample = tuple[int, int, int]


def median_color(samples: list[RgbSample]) -> RgbSample:
    middle = len(samples) // 2
    return tuple(sorted(sample[channel] for sample in samples)[middle] for channel in range(3))


def color_difference(first: RgbSample, second: RgbSample) -> int:
    return sum(abs(first_channel - second_channel) for first_channel, second_channel in zip(first, second))


def occupied_square_indices(image: Image.Image) -> set[int]:
    side = 8 * SAMPLES_PER_SQUARE_SIDE
    pixels = image.convert("RGB").resize((side, side), Image.Resampling.BOX).load()
    background_ring_low = BACKGROUND_RING_INSET
    background_ring_high = SAMPLES_PER_SQUARE_SIDE - 1 - BACKGROUND_RING_INSET
    background_ring_range = range(background_ring_low, background_ring_high + 1)
    inner_range = range(IGNORED_EDGE_SAMPLES, SAMPLES_PER_SQUARE_SIDE - IGNORED_EDGE_SAMPLES)
    inner_sample_count = len(inner_range) ** 2
    occupied = set()
    for row in range(8):
        for column in range(8):
            origin_x, origin_y = column * SAMPLES_PER_SQUARE_SIDE, row * SAMPLES_PER_SQUARE_SIDE
            border_samples = [
                pixels[origin_x + sample_x, origin_y + sample_y]
                for sample_y in background_ring_range
                for sample_x in background_ring_range
                if sample_x in (background_ring_low, background_ring_high) or sample_y in (background_ring_low, background_ring_high)
            ]
            background = median_color(border_samples)
            foreground_samples = sum(
                1
                for sample_y in inner_range
                for sample_x in inner_range
                if color_difference(pixels[origin_x + sample_x, origin_y + sample_y], background) > FOREGROUND_PIXEL_THRESHOLD
            )
            if foreground_samples >= OCCUPIED_SAMPLE_FRACTION * inner_sample_count:
                occupied.add(row * 8 + column)
    return occupied


def square_signatures(image: Image.Image) -> list[SquareSignature]:
    side = 8 * SAMPLES_PER_SQUARE_SIDE
    pixels = image.convert("RGB").resize((side, side), Image.Resampling.BOX).load()
    inner_range = range(IGNORED_EDGE_SAMPLES, SAMPLES_PER_SQUARE_SIDE - IGNORED_EDGE_SAMPLES)
    return [
        tuple(
            pixels[column * SAMPLES_PER_SQUARE_SIDE + sample_x, row * SAMPLES_PER_SQUARE_SIDE + sample_y]
            for sample_y in inner_range
            for sample_x in inner_range
        )
        for row in range(8)
        for column in range(8)
    ]


def square_has_changed(first: SquareSignature, second: SquareSignature) -> bool:
    changed_samples = sum(
        1
        for first_color, second_color in zip(first, second)
        if sum(abs(first_channel - second_channel) for first_channel, second_channel in zip(first_color, second_color)) > PIXEL_CHANGE_THRESHOLD
    )
    return changed_samples >= CHANGED_SAMPLE_FRACTION * len(first)


def changed_square_indices(reference: list[SquareSignature], current: list[SquareSignature]) -> set[int]:
    return {index for index in range(64) if square_has_changed(reference[index], current[index])}


class SquareChangeDetector:
    def __init__(self) -> None:
        self.reference: list[SquareSignature] | None = None
        self.previous_frame: list[SquareSignature] | None = None
        self.stable_frame_count = 0

    def reset(self) -> None:
        self.reference = None
        self.previous_frame = None
        self.stable_frame_count = 0

    def observe(self, current: list[SquareSignature]) -> set[int] | None:
        if self.reference is None:
            self.reference = current
            return None
        if self.previous_frame is not None and not changed_square_indices(self.previous_frame, current):
            self.stable_frame_count += 1
        else:
            self.stable_frame_count = 1
        self.previous_frame = current
        if self.stable_frame_count < STABLE_FRAMES_REQUIRED:
            return None
        changed = changed_square_indices(self.reference, current)
        return changed or None

    def accept(self, current: list[SquareSignature]) -> None:
        self.reference = current
