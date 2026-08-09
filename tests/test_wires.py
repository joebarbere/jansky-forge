"""Tests for M5: dipoles, ground reflection, arrays, and the bounded Yagi estimate.

External anchors, per honesty invariant 8:

* the half-wave dipole's directivity must come out at the textbook 2.15 dBi **by
  integrating its own pattern**, not by asserting the constant;
* the ground model must reproduce **NASA Radio JOVE's published 5.8 dBi** for a single
  dipole, and the published **23.28 ft** element length;
* the Yagi estimate must match a published 7-element design and must *fail* on a published
  3-element one, in the direction its own validity condition predicts.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from jansky_forge import wires
from jansky_forge.units import wavelength_m

JOVE_HZ = 20.1e6
GRAVES_HZ = 143.05e6
FOOT_M = 0.3048


# --------------------------------------------------------------------------------------
# The dipole
# --------------------------------------------------------------------------------------


def test_dipole_directivity_comes_out_of_its_own_pattern():
    """Integrate the pattern and get 1.64. The constant is a result, not an input."""
    theta = np.linspace(1e-6, math.pi - 1e-6, 200001)
    power = wires.dipole_power_pattern(theta)
    radiated = 2 * math.pi * np.trapezoid(power * np.sin(theta), theta)
    directivity = 4 * math.pi * power.max() / radiated
    assert directivity == pytest.approx(1.6409, abs=0.001)
    assert 10 * math.log10(directivity) == pytest.approx(2.15, abs=0.01)
    assert directivity == pytest.approx(wires.HALF_WAVE_DIPOLE_DIRECTIVITY, rel=1e-3)


def test_dipole_pattern_is_broadside_maximum_and_null_off_the_ends():
    """The end nulls are what make a dipole usable as a direction finder."""
    assert wires.dipole_power_pattern(np.array([math.pi / 2]))[0] == pytest.approx(1.0)
    assert wires.dipole_power_pattern(np.array([0.0]))[0] == pytest.approx(0.0)
    assert wires.dipole_power_pattern(np.array([math.pi]))[0] == pytest.approx(0.0)
    # Symmetric about broadside.
    a = wires.dipole_power_pattern(np.array([math.pi / 3]))[0]
    b = wires.dipole_power_pattern(np.array([2 * math.pi / 3]))[0]
    assert a == pytest.approx(b)


def test_element_length_reproduces_nasas_published_dimension():
    """NASA specifies 23.28 ft tip to tip at 20.1 MHz; a 0.95 velocity factor gives 23.24."""
    length_ft = wires.half_wave_length_m(JOVE_HZ) / FOOT_M
    assert length_ft == pytest.approx(23.28, abs=0.06)
    # A velocity factor of 1 would be too long — the correction is real, not cosmetic.
    assert wires.half_wave_length_m(JOVE_HZ, velocity_factor=1.0) > wires.half_wave_length_m(
        JOVE_HZ
    )
    with pytest.raises(ValueError):
        wires.half_wave_length_m(JOVE_HZ, velocity_factor=0.0)


def test_half_wave_dipole_model_reports_free_space_values():
    char = wires.HalfWaveDipole(freq_hz=JOVE_HZ).characterize(JOVE_HZ)
    assert char.gain_dbi == pytest.approx(2.15, abs=0.01)
    assert char.detail["radiation_resistance_ohm"] == pytest.approx(73.1)
    assert any("Free space, with no ground" in n for n in char.notes)
    # It says plainly that aperture efficiency is meaningless here.
    assert any("not a meaningful quantity for a wire" in n for n in char.notes)


def test_dipole_warns_when_used_far_off_resonance():
    char = wires.HalfWaveDipole(freq_hz=JOVE_HZ).characterize(JOVE_HZ * 1.5)
    assert any("away from the" in n and "cut for" in n for n in char.notes)
    with pytest.raises(ValueError):
        wires.HalfWaveDipole(freq_hz=0.0)


def test_folded_dipole_changes_impedance_and_nothing_else():
    plain = wires.HalfWaveDipole(freq_hz=GRAVES_HZ).characterize(GRAVES_HZ)
    folded = wires.FoldedDipole(freq_hz=GRAVES_HZ).characterize(GRAVES_HZ)
    assert folded.gain_dbi == pytest.approx(plain.gain_dbi)
    assert folded.hpbw_e_deg == pytest.approx(plain.hpbw_e_deg)
    assert folded.detail["feed_impedance_ohm"] == pytest.approx(4 * 73.1)
    assert any("not the pattern" in n for n in folded.notes)


# --------------------------------------------------------------------------------------
# Ground — the anchor
# --------------------------------------------------------------------------------------


def test_radio_jove_single_dipole_matches_nasas_published_gain():
    """NASA publishes 5.8 dBi. Over AVERAGE ground at their 10 ft height we get 5.89.

    This agreement is what identifies the manual's figure as an average-ground number: a
    perfect conductor would give 8.17 dBi, so the 2.4 dB difference is real soil loss rather
    than a modelling error.
    """
    dipole = wires.DipoleOverGround(
        freq_hz=JOVE_HZ, height_m=10 * FOOT_M, ground=wires.AVERAGE_GROUND
    )
    assert dipole.characterize(JOVE_HZ).gain_dbi == pytest.approx(5.8, abs=0.15)

    perfect = wires.DipoleOverGround(
        freq_hz=JOVE_HZ, height_m=10 * FOOT_M, ground=wires.PERFECT_GROUND
    )
    assert perfect.characterize(JOVE_HZ).gain_dbi > 7.5  # the idealization overstates it


def test_height_steers_the_beam_exactly_as_the_jove_manual_describes():
    """The manual treats height as a beam-steering control. The model must reproduce that."""
    elevations = []
    for feet in (10, 15, 20):
        _, elevation = wires.ground_gain_db(
            height_m=feet * FOOT_M, freq_hz=JOVE_HZ, ground=wires.AVERAGE_GROUND
        )
        elevations.append(elevation)
    # Low and the lobe is overhead; raise it and the lobe drops toward the horizon.
    assert elevations[0] == pytest.approx(90.0, abs=1.0)
    assert elevations == sorted(elevations, reverse=True)
    assert elevations[-1] < 40.0


def test_ground_gain_is_capped_at_six_db_and_ordered_by_soil_quality():
    """A perfect image doubles the field: +6.02 dB, and nothing does better."""
    common = dict(height_m=20 * FOOT_M, freq_hz=JOVE_HZ)
    perfect, _ = wires.ground_gain_db(**common, ground=wires.PERFECT_GROUND)
    sea, _ = wires.ground_gain_db(**common, ground=wires.SEAWATER)
    average, _ = wires.ground_gain_db(**common, ground=wires.AVERAGE_GROUND)
    poor, _ = wires.ground_gain_db(**common, ground=wires.POOR_GROUND)
    assert perfect == pytest.approx(6.02, abs=0.02)
    assert perfect >= sea > average > poor
    # Soil quality is worth several dB, which is a real design consideration.
    assert sea - poor > 1.5


def test_horizontal_polarization_always_nulls_on_the_horizon():
    """Gamma -> -1 at grazing for any ground, so the image always cancels there."""
    for ground in (wires.PERFECT_GROUND, wires.SEAWATER, wires.POOR_GROUND):
        gamma = wires.fresnel_reflection_horizontal(np.array([1e-6]), ground, JOVE_HZ)
        assert gamma[0].real == pytest.approx(-1.0, abs=0.02)
        factor = wires.ground_reflection_factor(
            np.array([1e-6]), height_m=5.0, freq_hz=JOVE_HZ, ground=ground
        )
        assert factor[0] < 0.05


def test_directivity_over_perfect_ground_converges_to_the_shortcut_at_height():
    """The convenient '2.15 + 6.02 = 8.17 dBi' is the large-height limit, and only that.

    At half a wavelength up the true figure is 8.4 dBi and at a quarter wavelength 7.5 —
    so the shortcut is a limit, not a general answer, and this pins both facts.
    """
    assert wires.directivity_over_perfect_ground_db(0.25) == pytest.approx(7.5, abs=0.2)
    assert wires.directivity_over_perfect_ground_db(0.5) == pytest.approx(8.4, abs=0.2)
    # Far up, it approaches the shortcut.
    assert wires.directivity_over_perfect_ground_db(4.0) == pytest.approx(8.17, abs=0.25)
    with pytest.raises(ValueError):
        wires.directivity_over_perfect_ground_db(-1.0)


def test_ground_types_lookup_and_validation():
    assert wires.get_ground("average") is wires.AVERAGE_GROUND
    assert wires.get_ground("SEAWATER") is wires.SEAWATER
    with pytest.raises(KeyError, match="known"):
        wires.get_ground("lava")
    with pytest.raises(ValueError):
        wires.GroundType("impossible", 0.5, 0.01)
    with pytest.raises(ValueError):
        wires.GroundType("impossible", 5.0, -1.0)


def test_ground_reflection_rejects_a_buried_antenna():
    with pytest.raises(ValueError, match="height cannot be negative"):
        wires.ground_reflection_factor(
            np.array([0.5]), height_m=-1.0, freq_hz=JOVE_HZ, ground=wires.AVERAGE_GROUND
        )


# --------------------------------------------------------------------------------------
# Arrays
# --------------------------------------------------------------------------------------


def test_array_factor_peaks_at_n_and_is_exact():
    """A finite geometric series — no approximation, so it had better be right."""
    lam = wavelength_m(JOVE_HZ)
    broadside = wires.array_factor(
        np.array([math.pi / 2]), n_elements=4, spacing_m=lam / 2, freq_hz=JOVE_HZ
    )
    assert broadside[0] == pytest.approx(4.0)
    # Half-wave spaced broadside array: nulls where sin(n*psi/2) = 0.
    angles = np.linspace(0, math.pi, 2001)
    factor = wires.array_factor(angles, n_elements=4, spacing_m=lam / 2, freq_hz=JOVE_HZ)
    assert factor.max() == pytest.approx(4.0, rel=1e-3)
    assert factor.min() < 0.05
    # One element is omnidirectional in the array sense.
    single = wires.array_factor(angles, n_elements=1, spacing_m=lam / 2, freq_hz=JOVE_HZ)
    assert np.allclose(single, 1.0)


def test_array_factor_phasing_steers_the_beam():
    lam = wavelength_m(JOVE_HZ)
    angles = np.linspace(0, math.pi, 4001)
    unphased = wires.array_factor(angles, n_elements=2, spacing_m=lam / 2, freq_hz=JOVE_HZ)
    endfire = wires.array_factor(
        angles, n_elements=2, spacing_m=lam / 2, freq_hz=JOVE_HZ, phase_step_deg=-180.0
    )
    assert math.degrees(angles[int(np.argmax(unphased))]) == pytest.approx(90.0, abs=1.0)
    assert math.degrees(angles[int(np.argmax(endfire))]) < 10.0


@pytest.mark.parametrize("kwargs", [dict(n_elements=0), dict(spacing_m=-1.0)])
def test_array_factor_rejects_impossible_arrays(kwargs):
    base = dict(n_elements=2, spacing_m=1.0, freq_hz=JOVE_HZ)
    with pytest.raises(ValueError):
        wires.array_factor(np.array([1.0]), **(base | kwargs))


def test_broadside_array_gain_is_the_ideal_ceiling():
    assert wires.broadside_array_gain_db(1) == pytest.approx(0.0)
    assert wires.broadside_array_gain_db(2) == pytest.approx(3.01, abs=0.01)
    assert wires.broadside_array_gain_db(4) == pytest.approx(6.02, abs=0.01)
    with pytest.raises(ValueError):
        wires.broadside_array_gain_db(0)


def test_the_jove_dual_dipole_overshoots_its_published_gain_and_says_why():
    """Our ideal-array assumption predicts 8.9 dBi against NASA's published 7.8.

    The ~1 dB shortfall in the real antenna is mutual coupling between the two dipoles,
    which a pattern-multiplication model cannot represent. It is left standing and the notes
    say so, because tuning an array factor to match would destroy the model's independence.
    """
    array = wires.DipoleOverGround(
        freq_hz=JOVE_HZ,
        height_m=10 * FOOT_M,
        ground=wires.AVERAGE_GROUND,
        n_elements=2,
        spacing_m=20 * FOOT_M,
    )
    char = array.characterize(JOVE_HZ)
    assert char.gain_dbi == pytest.approx(8.9, abs=0.2)
    assert char.gain_dbi > 7.8  # overshoots, knowingly
    assert char.detail["array_gain_db"] == pytest.approx(3.01, abs=0.01)
    assert any("couple to each other and fall short" in n for n in char.notes)


def test_a_very_low_antenna_is_flagged():
    low = wires.DipoleOverGround(freq_hz=JOVE_HZ, height_m=1.0, ground=wires.AVERAGE_GROUND)
    assert any("very low" in n for n in low.characterize(JOVE_HZ).notes)


@pytest.mark.parametrize("kwargs", [dict(freq_hz=0.0), dict(height_m=-1.0), dict(n_elements=0)])
def test_dipole_over_ground_rejects_impossible_configurations(kwargs):
    with pytest.raises(ValueError):
        wires.DipoleOverGround(**({"freq_hz": JOVE_HZ, "height_m": 3.0} | kwargs))


# --------------------------------------------------------------------------------------
# Yagi — a bounded estimate that must fail where it says it will
# --------------------------------------------------------------------------------------


def test_yagi_estimate_matches_a_published_long_boom_design():
    """W7ZOI's 7-element, 2.377 m boom at 143.05 MHz, published as 11.6 dBi modelled."""
    gain, caveats = wires.yagi_gain_estimate(boom_length_m=2.377, freq_hz=GRAVES_HZ)
    assert gain == pytest.approx(11.6, abs=0.5)
    assert any("sizing a boom" in c for c in caveats)
    # A boom over 0.75 wavelengths does not trigger the short-array warning.
    assert not any("UNDERSTATES" in c for c in caveats)


def test_yagi_estimate_fails_on_a_short_boom_in_the_direction_it_predicts():
    """G4CQM's 3-element, 0.5 m boom, published 6.75 dBi. We give 4.5 — and we warn.

    The Hansen-Woodyard bound assumes a long array. A model that quietly returned a
    plausible number here would be worse than one that is visibly wrong for a stated
    reason, so the shortfall is asserted rather than tolerated.
    """
    gain, caveats = wires.yagi_gain_estimate(boom_length_m=0.500, freq_hz=GRAVES_HZ)
    assert gain == pytest.approx(4.47, abs=0.3)
    assert gain < 6.75 - 1.5  # genuinely and knowingly low
    assert any("UNDERSTATES a short Yagi" in c for c in caveats)


def test_yagi_gain_grows_with_boom_length():
    short, _ = wires.yagi_gain_estimate(boom_length_m=1.0, freq_hz=GRAVES_HZ)
    long, _ = wires.yagi_gain_estimate(boom_length_m=4.0, freq_hz=GRAVES_HZ)
    assert long - short == pytest.approx(6.02, abs=0.01)  # 4x boom is +6 dB
    with pytest.raises(ValueError):
        wires.yagi_gain_estimate(boom_length_m=0.0, freq_hz=GRAVES_HZ)


def test_yagi_model_includes_ground_when_told_about_it():
    free = wires.YagiUda(freq_hz=GRAVES_HZ, boom_length_m=2.377, n_elements=7)
    over_ground = wires.YagiUda(
        freq_hz=GRAVES_HZ,
        boom_length_m=2.377,
        n_elements=7,
        height_m=4.0,
        ground=wires.AVERAGE_GROUND,
    )
    assert over_ground.characterize(GRAVES_HZ).gain_dbi > free.characterize(GRAVES_HZ).gain_dbi
    assert any("interacts with the ground" in n for n in over_ground.characterize(GRAVES_HZ).notes)


def test_yagi_refuses_to_pretend_it_models_elements():
    """The docstring must keep pointing at M6 rather than growing an element model."""
    assert "method-of-moments" in wires.yagi_gain_estimate.__doc__
    assert "not for cutting elements" in wires.yagi_gain_estimate.__doc__
    char = wires.YagiUda(freq_hz=GRAVES_HZ, boom_length_m=1.0).characterize(GRAVES_HZ)
    assert any("useless for cutting elements" in n for n in char.notes)
    with pytest.raises(ValueError, match="at least a driven element"):
        wires.YagiUda(n_elements=1)
