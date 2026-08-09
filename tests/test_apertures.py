"""Tests for the Tier-1 aperture models: parabolic dish and horns.

Golden values are hand-computed with the arithmetic written out, so a future reader can
check them rather than trust them.
"""

from __future__ import annotations

import math

import pytest

from jansky_forge.apertures import (
    ConicalHorn,
    ParabolicDish,
    PyramidalHorn,
    ruze_efficiency,
    subtended_half_angle_deg,
)
from jansky_forge.core import AntennaModel

HI_HZ = 1_420_405_751.768


def test_ruze_is_negligible_at_21cm_and_severe_at_10ghz():
    # 2 mm RMS: at lambda=0.211 m, 4*pi*0.002/0.211 = 0.1191 -> exp(-0.01418) = 0.9859
    assert ruze_efficiency(0.002, 0.211061) == pytest.approx(0.9859, abs=1e-3)
    # Same surface at 10 GHz (lambda=0.03 m): 4*pi*0.002/0.03 = 0.8378 -> exp(-0.7019) = 0.4956
    assert ruze_efficiency(0.002, 0.03) == pytest.approx(0.4956, abs=1e-3)
    # A perfect surface loses nothing.
    assert ruze_efficiency(0.0, 0.211) == pytest.approx(1.0)


def test_ruze_rejects_negative_surface_error():
    with pytest.raises(ValueError, match="negative"):
        ruze_efficiency(-0.001, 0.211)


def test_subtended_half_angle_of_common_f_over_d():
    # f/D = 0.25 puts the focus in the aperture plane: theta0 = 2*arctan(1/1) = 90 deg
    assert subtended_half_angle_deg(0.25) == pytest.approx(90.0)
    # f/D = 0.4: 2*arctan(1/1.6) = 2*32.005 = 64.01 deg
    assert subtended_half_angle_deg(0.4) == pytest.approx(64.01, abs=0.02)
    # Deeper dish (smaller f/D) subtends a wider angle at the feed.
    assert subtended_half_angle_deg(0.3) > subtended_half_angle_deg(0.5)
    with pytest.raises(ValueError, match="positive"):
        subtended_half_angle_deg(0.0)


def test_700mm_dish_at_21cm_reproduces_the_station_numbers():
    """The Discovery Dish sanity check: ~21 deg beam, high-teens dBi.

    HPBW = 70 * 0.211061 / 0.7 = 21.11 deg — this is the number the station notes quote,
    and it is pure geometry, so any model regression shows up here first.
    """
    dish = ParabolicDish(diameter_m=0.7, f_over_d=0.4, surface_rms_mm=1.0)
    char = dish.characterize(HI_HZ)
    assert char.hpbw_e_deg == pytest.approx(21.11, abs=0.05)
    assert char.hpbw_h_deg == pytest.approx(char.hpbw_e_deg)
    # eta = 0.80*0.85*0.95*1.0*ruze(0.001 m) ; ruze = exp(-(4pi*0.001/0.211061)^2) = 0.99646
    # -> eta = 0.6460*0.99646 = 0.6437 ; (pi*0.7/0.211061)^2 = (10.4180)^2 = 108.53
    # -> G = 69.86 -> 18.44 dBi
    assert char.aperture_efficiency == pytest.approx(0.6437, abs=0.002)
    assert char.gain_dbi == pytest.approx(18.44, abs=0.05)


def test_dish_gain_scales_as_diameter_squared_and_beam_as_inverse_diameter():
    small = ParabolicDish(diameter_m=1.0).characterize(HI_HZ)
    big = ParabolicDish(diameter_m=2.0).characterize(HI_HZ)
    assert big.gain_dbi - small.gain_dbi == pytest.approx(6.0206, abs=1e-3)  # 10*log10(4)
    assert big.hpbw_e_deg == pytest.approx(small.hpbw_e_deg / 2.0)
    # Effective area follows the gain, and for a fixed efficiency tracks physical area.
    assert big.effective_area_m2 == pytest.approx(4.0 * small.effective_area_m2, rel=1e-6)


def test_dish_reports_ruze_detail_and_warns_when_the_surface_dominates():
    # A 5 mm surface at Ku band: 4*pi*0.005/0.02458 = 2.557 -> exp(-6.537) = 0.00145, ~28 dB
    dish = ParabolicDish(diameter_m=1.0, surface_rms_mm=5.0)
    char = dish.characterize(12.2e9)
    assert char.detail["ruze_loss_db"] > 20.0
    assert any("surface" in n for n in char.notes)


def test_dish_warns_when_it_is_electrically_small():
    # 0.7 m at the JOVE band (lambda = 14.9 m) is 0.047 lambda — aperture theory is nonsense
    char = ParabolicDish(diameter_m=0.7).characterize(20.1e6)
    assert any("aperture theory degrades" in n for n in char.notes)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"diameter_m": 0.0},
        {"diameter_m": -1.0},
        {"illumination_efficiency": 0.0},
        {"spillover_efficiency": 1.5},
        {"blockage_efficiency": -0.1},
        {"other_efficiency": 2.0},
    ],
)
def test_dish_rejects_impossible_geometry(kwargs):
    with pytest.raises(ValueError):
        ParabolicDish(**kwargs)


def test_pyramidal_horn_gain_matches_the_aperture_relation():
    """A 0.6 x 0.45 m horn at 21 cm, computed by hand.

    A = 0.27 m^2 ; 4*pi*A/lambda^2 = 4*pi*0.27/0.0445468 = 76.174
    G = 0.51 * 76.174 = 38.85 -> 15.895 dBi
    HPBW_E = 54*0.211061/0.45 = 25.33 deg ; HPBW_H = 78*0.211061/0.6 = 27.44 deg
    """
    horn = PyramidalHorn(aperture_a_m=0.6, aperture_b_m=0.45, axial_length_m=0.7)
    char = horn.characterize(HI_HZ)
    assert char.gain_dbi == pytest.approx(15.895, abs=0.02)
    assert char.hpbw_e_deg == pytest.approx(25.33, abs=0.05)
    assert char.hpbw_h_deg == pytest.approx(27.44, abs=0.05)
    # The E-plane (narrow, b) beam is the tighter one here — a swapped a/b would flip this.
    assert char.hpbw_e_deg < char.hpbw_h_deg


def test_pyramidal_horn_warns_when_its_aperture_is_sub_wavelength():
    char = PyramidalHorn(aperture_a_m=0.15, aperture_b_m=0.1).characterize(HI_HZ)
    assert any("unreliable" in n for n in char.notes)


def test_conical_horn_applies_the_phase_error_loss():
    """0.4 m aperture, 0.5 m axial at 21 cm — M1 charges it for its phase error.

    Slant (throat unknown, apex at throat) = hypot(0.5, 0.2) = 0.53852 m.
    s = 0.4^2/(8*0.211061*0.53852) = 0.16/0.90926 = 0.17597
    L(s) = 0.8 - 1.71(0.17597) + 26.25(0.17597)^2 - 17.79(0.17597)^3 = 1.2166 dB
    aperture gain = (pi*0.4/0.211061)^2 = 35.454 -> 15.496 dB ; minus loss -> 14.28 dBi
    """
    char = ConicalHorn(aperture_diameter_m=0.4, axial_length_m=0.5).characterize(HI_HZ)
    assert char.gain_dbi == pytest.approx(14.28, abs=0.05)
    assert char.detail["phase_deviation"] == pytest.approx(0.176, abs=0.002)
    assert char.detail["loss_figure_db"] == pytest.approx(1.217, abs=0.01)
    # M0 assumed 51% regardless; the real efficiency here is higher because this horn is
    # under-flared for its length.
    assert char.aperture_efficiency > 0.51
    assert any("loss figure" in n for n in char.notes)


def test_conical_horn_says_when_the_throat_is_unknown():
    unknown = ConicalHorn(aperture_diameter_m=0.4, axial_length_m=0.5).characterize(HI_HZ)
    assert any("Throat diameter unknown" in n for n in unknown.notes)
    # A known throat pushes the apex further back: longer slant, less phase error, more gain.
    known = ConicalHorn(
        aperture_diameter_m=0.4, axial_length_m=0.5, throat_diameter_m=0.15
    ).characterize(HI_HZ)
    assert known.detail["slant_m"] > unknown.detail["slant_m"]
    assert known.gain_dbi > unknown.gain_dbi
    assert not any("Throat diameter unknown" in n for n in known.notes)


def test_conical_horn_warns_beyond_the_loss_fit_validity():
    # A very wide, very short horn: huge phase deviation, outside the cubic fit's range.
    char = ConicalHorn(aperture_diameter_m=1.6, axial_length_m=0.25).characterize(HI_HZ)
    assert char.detail["phase_deviation"] > 0.8
    assert any("beyond where the loss-figure fit is" in n for n in char.notes)


@pytest.mark.parametrize(
    "factory",
    [
        lambda: PyramidalHorn(aperture_a_m=0.0),
        lambda: PyramidalHorn(aperture_b_m=-0.1),
        lambda: PyramidalHorn(aperture_efficiency=1.5),
        lambda: ConicalHorn(aperture_diameter_m=0.0),
        lambda: ConicalHorn(axial_length_m=0.0),
        lambda: ConicalHorn(aperture_diameter_m=0.2, throat_diameter_m=0.3),
    ],
)
def test_horns_reject_impossible_geometry(factory):
    with pytest.raises(ValueError):
        factory()


def test_every_model_satisfies_the_protocol_and_exposes_flat_parameters():
    for model in (ParabolicDish(), PyramidalHorn(), ConicalHorn()):
        assert isinstance(model, AntennaModel)
        params = model.parameters()
        assert params and all(isinstance(v, float) for v in params.values())
        char = model.characterize(HI_HZ)
        assert char.gain_dbi > 0
        assert 0.0 < char.aperture_efficiency <= 1.0


def test_characterization_derived_properties():
    char = ParabolicDish(diameter_m=1.0).characterize(HI_HZ)
    assert char.wavelength_m == pytest.approx(0.211061, abs=1e-6)
    assert char.gain_linear == pytest.approx(10 ** (char.gain_dbi / 10.0))
    # Geometric mean of two equal widths is that width.
    assert char.hpbw_geometric_mean_deg == pytest.approx(char.hpbw_e_deg)
    assert "MHz" in char.summary() and "dBi" in char.summary()
    # Beam solid angle agrees with the Gaussian approximation of the reported widths.
    expected = 1.133 * math.radians(char.hpbw_e_deg) * math.radians(char.hpbw_h_deg)
    assert char.beam_solid_angle_sr == pytest.approx(expected)
