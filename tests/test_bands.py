"""Tests for the band definitions — the frequencies are physics, so they get checked."""

from __future__ import annotations

import pytest

from jansky_forge import bands


def test_hydrogen_line_rest_frequency_is_the_laboratory_value():
    # 1420.405751768 MHz. Getting this wrong by a kHz is a 0.2 km/s velocity error, which
    # matters for anything downstream that turns frequency into velocity.
    assert bands.HI_21CM.freq_hz == pytest.approx(1_420_405_751.768)
    assert bands.HI_21CM.freq_mhz == pytest.approx(1420.405751768)


def test_the_four_oh_lines_are_present_and_ordered():
    oh = [bands.OH_1612, bands.OH_1665, bands.OH_1667, bands.OH_1720]
    freqs = [b.freq_hz for b in oh]
    assert freqs == sorted(freqs)
    # The main lines sit between the satellite lines.
    assert bands.OH_1612.freq_hz < bands.OH_1665.freq_hz < bands.OH_1720.freq_hz


def test_every_band_is_registered_under_its_own_slug_and_explains_itself():
    for slug, band in bands.BANDS.items():
        assert band.slug == slug
        assert band.freq_hz > 0
        assert len(band.why) > 20, f"{slug}: say why this frequency matters"
        assert band.bandwidth_hz >= 0


def test_get_band_and_its_error_message():
    assert bands.get_band("hi") is bands.HI_21CM
    with pytest.raises(KeyError, match="known bands"):
        bands.get_band("nonsense")


def test_the_bands_span_decametric_to_centimetric():
    freqs = [b.freq_hz for b in bands.BANDS.values()]
    assert min(freqs) == bands.JOVE_20M.freq_hz  # 20.1 MHz, Radio JOVE
    assert max(freqs) == bands.KU_BAND_SUN.freq_hz  # 12.2 GHz, satellite-TV dish
