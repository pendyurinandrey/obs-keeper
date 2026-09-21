import pytest

from obs_keeper.levels import SILENCE_FLOOR_DB, linear_to_db, peak_db


def test_linear_to_db_reference_points():
    assert linear_to_db(1.0) == pytest.approx(0.0)
    assert linear_to_db(0.5) == pytest.approx(-6.0206, abs=1e-3)
    assert linear_to_db(0.1) == pytest.approx(-20.0)


def test_zero_and_negative_are_clamped_to_floor():
    assert linear_to_db(0.0) == SILENCE_FLOOR_DB
    assert linear_to_db(-1.0) == SILENCE_FLOOR_DB
    assert linear_to_db(1e-12) == SILENCE_FLOOR_DB


def test_peak_db_takes_loudest_channel_peak_not_magnitude():
    # [magnitude, peak, input_peak] per channel
    levels = [[0.9, 0.01, 0.0], [0.0, 0.1, 0.0]]
    assert peak_db(levels) == pytest.approx(-20.0)


def test_peak_db_without_channels_is_silence():
    assert peak_db([]) == SILENCE_FLOOR_DB
    assert peak_db([[0.5]]) == SILENCE_FLOOR_DB
