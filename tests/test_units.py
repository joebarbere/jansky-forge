"""Tests for jansky_forge.units — the constants and conversions everything else builds on."""

from __future__ import annotations

import math

import pytest

from jansky_forge import units


def test_wavelength_of_the_hydrogen_line():
    # c / 1420.405751768 MHz = 299792458 / 1.420405751768e9 = 0.21106 m — the "21 cm" line
    # is really 21.106 cm, and the package should say so rather than round to 0.21.
    assert units.wavelength_m(1_420_405_751.768) == pytest.approx(0.211061, abs=1e-6)


def test_wavelength_and_frequency_are_inverses():
    for freq in (20.1e6, 143.05e6, 1.4204e9, 12.2e9):
        assert units.frequency_hz(units.wavelength_m(freq)) == pytest.approx(freq)


@pytest.mark.parametrize("bad", [0.0, -1.0])
def test_non_positive_inputs_are_rejected(bad):
    with pytest.raises(ValueError, match="positive"):
        units.wavelength_m(bad)
    with pytest.raises(ValueError, match="positive"):
        units.frequency_hz(bad)


def test_db_round_trip_and_known_values():
    assert units.to_db(1.0) == pytest.approx(0.0)
    assert units.to_db(2.0) == pytest.approx(3.0103, abs=1e-4)
    assert units.to_db(100.0) == pytest.approx(20.0)
    assert units.from_db(units.to_db(7.3)) == pytest.approx(7.3)


def test_to_db_rejects_non_positive_power():
    # A zero or negative power ratio has no dB value; returning -inf silently would let a
    # broken efficiency propagate into a plausible-looking gain.
    with pytest.raises(ValueError, match="non-positive"):
        units.to_db(0.0)


def test_gaussian_beam_solid_angle_matches_hand_computation():
    # 1.133 * (1 deg in rad)^2 = 1.133 * (0.0174533)^2 = 3.4515e-4 sr
    assert units.gaussian_beam_solid_angle_sr(1.0, 1.0) == pytest.approx(3.4515e-4, rel=1e-3)
    # Scales linearly in each width.
    wide = units.gaussian_beam_solid_angle_sr(2.0, 1.0)
    assert wide == pytest.approx(2.0 * units.gaussian_beam_solid_angle_sr(1.0, 1.0))


def test_effective_area_from_gain_is_the_reciprocity_identity():
    # An isotropic antenna (G = 1) at 21 cm: A_e = lambda^2/4pi = 0.211061^2/(4pi) = 3.545e-3 m^2
    a_e = units.effective_area_m2(1.0, 1_420_405_751.768)
    assert a_e == pytest.approx(3.5449e-3, rel=1e-4)
    # Exact form, free of the rounded wavelength above.
    lam = units.wavelength_m(1_420_405_751.768)
    assert a_e == pytest.approx(lam**2 / (4 * math.pi), rel=1e-12)
    # Gain and area are proportional at fixed frequency.
    assert units.effective_area_m2(50.0, 1.42e9) == pytest.approx(
        50.0 * units.effective_area_m2(1.0, 1.42e9)
    )
