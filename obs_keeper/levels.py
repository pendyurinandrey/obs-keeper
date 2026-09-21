"""Pure helpers for audio level maths."""

import math

SILENCE_FLOOR_DB = -120.0


def linear_to_db(value: float) -> float:
    """Convert a linear amplitude (0..1+) to dBFS, clamped at ``SILENCE_FLOOR_DB``."""
    if value <= 0.0:
        return SILENCE_FLOOR_DB
    return max(20.0 * math.log10(value), SILENCE_FLOOR_DB)


def peak_db(levels_mul: list[list[float]]) -> float:
    """Highest peak in dBFS over all channels of one ``InputVolumeMeters`` entry.

    ``levels_mul`` is obs-websocket's ``inputLevelsMul``: per channel
    ``[magnitude, peak, input_peak]`` as linear values. An input without channels
    is reported as silence.
    """
    peaks = [channel[1] for channel in levels_mul if len(channel) >= 2]
    if not peaks:
        return SILENCE_FLOOR_DB
    return linear_to_db(max(peaks))
