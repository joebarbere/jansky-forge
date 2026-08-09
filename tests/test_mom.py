"""Tests for M6: the Tier-2 method-of-moments validation layer.

The solver tests skip when ``pymininec`` is absent, because Tier 2 is an optional extra —
but CI installs it, so they run for real there. The same pattern as M4's course cross-check:
a guard that only ever skips is not a guard.

The two anchors that matter are the tickets M5 wrote:

* the **3-element GRAVES Yagi**, where Tier 1's endfire bound read 2.3 dB low and Tier 2
  must close the gap against the published figure;
* the **JOVE dual dipole**, where Tier 1 overshot because pattern multiplication cannot see
  mutual coupling, and Tier 2 must at least show the coupling exists.
"""

from __future__ import annotations

import pytest

from jansky_forge import mom
from jansky_forge.units import wavelength_m
from jansky_forge.wires import AVERAGE_GROUND, PERFECT_GROUND

GRAVES_HZ = 143.05e6
JOVE_HZ = 20.1e6
FOOT_M = 0.3048

needs_backend = pytest.mark.skipif(
    not mom.available_backends(),
    reason="no MoM backend installed; Tier 2 is an optional extra (pip install .[mom])",
)


# --------------------------------------------------------------------------------------
# Geometry and validation, which need no solver
# --------------------------------------------------------------------------------------


def test_wire_spec_rejects_impossible_conductors():
    with pytest.raises(ValueError, match="radius must be positive"):
        mom.WireSpec((0, 0, 0), (1, 0, 0), 0.0, 11)
    with pytest.raises(ValueError, match="at least one segment"):
        mom.WireSpec((0, 0, 0), (1, 0, 0), 0.001, 0)
    with pytest.raises(ValueError, match="non-zero length"):
        mom.WireSpec((0, 0, 0), (0, 0, 0), 0.001, 11)
    assert mom.WireSpec((0, 0, 0), (3, 4, 0), 0.001, 11).length_m == pytest.approx(5.0)


def test_model_rejects_a_feed_on_a_wire_that_is_not_there():
    wire = mom.WireSpec((-0.5, 0, 0), (0.5, 0, 0), 0.001, 11)
    with pytest.raises(ValueError, match="at least one wire"):
        mom.WireModel(name="empty", wires=())
    with pytest.raises(ValueError, match="not one of"):
        mom.WireModel(name="x", wires=(wire,), feed_wire=3)


def test_feed_defaults_to_the_middle_of_the_driven_element():
    model = mom.dipole_model(freq_hz=GRAVES_HZ, length_m=1.0, segments=21)
    assert model.driven.segments == 21
    assert model.feed_pulse == 10
    # An even segment count is bumped odd so a segment centre lands on the feed point.
    assert mom.dipole_model(freq_hz=GRAVES_HZ, length_m=1.0, segments=20).driven.segments == 21


def test_segmentation_check_catches_the_classic_mom_mistakes():
    """Too few segments per wavelength is the error that quietly produces wrong answers."""
    lam = wavelength_m(GRAVES_HZ)
    coarse = mom.WireModel(
        name="coarse",
        wires=(mom.WireSpec((-lam / 2, 0, 0), (lam / 2, 0, 0), 0.001, 3),),
    )
    warnings = mom.check_segmentation(coarse, GRAVES_HZ)
    assert any("segments per wavelength" in w for w in warnings)

    fat = mom.WireModel(
        name="fat",
        wires=(mom.WireSpec((-0.5, 0, 0), (0.5, 0, 0), 0.5, 3),),
    )
    assert any(
        "radius exceeds its segment length" in w for w in mom.check_segmentation(fat, GRAVES_HZ)
    )

    fine = mom.dipole_model(freq_hz=GRAVES_HZ, length_m=lam / 2, segments=21)
    assert mom.check_segmentation(fine, GRAVES_HZ) == ()


def test_yagi_model_requires_an_element_radius_and_enough_elements():
    """Radius has no default on purpose — guessing it would hide an invention in a result."""
    with pytest.raises(TypeError):
        mom.yagi_model(freq_hz=GRAVES_HZ, elements_m=mom.GRAVES_3EL_ELEMENTS)  # type: ignore[call-arg]
    with pytest.raises(ValueError, match="at least a driven element"):
        mom.yagi_model(freq_hz=GRAVES_HZ, elements_m=[(1.0, 0.0)], radius_m=0.003)
    with pytest.raises(ValueError, match="not one of the elements"):
        mom.yagi_model(
            freq_hz=GRAVES_HZ, elements_m=mom.GRAVES_3EL_ELEMENTS, radius_m=0.003, driven_index=9
        )
    model = mom.yagi_model(freq_hz=GRAVES_HZ, elements_m=mom.GRAVES_3EL_ELEMENTS, radius_m=0.003)
    assert len(model.wires) == 3
    assert model.feed_wire == 1  # the driven element, not the reflector
    assert any("element radius" in n.lower() for n in model.notes)


def test_published_graves_geometry_is_carried_verbatim():
    """The tables M5 recorded and could not use. Length and boom position, in metres."""
    assert mom.GRAVES_3EL_ELEMENTS[0] == (1.076, 0.0)  # reflector at the boom origin
    assert mom.GRAVES_7EL_ELEMENTS[-1] == (0.834, 2.377)  # last director
    # Elements shorten monotonically down the boom, as a Yagi's must.
    for table in (mom.GRAVES_3EL_ELEMENTS, mom.GRAVES_7EL_ELEMENTS):
        lengths = [length for length, _ in table]
        positions = [position for _, position in table]
        assert positions == sorted(positions)
        assert lengths[0] == max(lengths)  # reflector is the longest


def test_array_model_makes_the_drive_choice_explicit():
    both = mom.dipole_array_model(freq_hz=JOVE_HZ, length_m=7.0, spacing_m=6.1)
    parasitic = mom.dipole_array_model(
        freq_hz=JOVE_HZ, length_m=7.0, spacing_m=6.1, drive_all=False
    )
    assert both.drive_all and not parasitic.drive_all
    assert any("All elements driven" in n for n in both.notes)
    assert any("parasitic" in n for n in parasitic.notes)
    with pytest.raises(ValueError, match="at least two elements"):
        mom.dipole_array_model(freq_hz=JOVE_HZ, length_m=7.0, spacing_m=6.1, n_elements=1)


def test_backend_registry_reports_honestly_when_nothing_is_installed(monkeypatch):
    monkeypatch.setattr(mom, "BACKENDS", ())
    assert mom.available_backends() == []
    with pytest.raises(RuntimeError, match="optional extra"):
        mom.default_backend()


def test_swr_is_computed_from_the_feed_impedance():
    matched = mom.MomResult(
        backend="x",
        freq_hz=1e8,
        gain_dbi=2.0,
        peak_elevation_deg=0.0,
        feed_impedance_ohm=complex(50, 0),
    )
    assert matched.swr == pytest.approx(1.0)
    mismatched = mom.MomResult(
        backend="x",
        freq_hz=1e8,
        gain_dbi=2.0,
        peak_elevation_deg=0.0,
        feed_impedance_ohm=complex(150, 0),
    )
    assert mismatched.swr == pytest.approx(3.0)
    assert "SWR" in mismatched.summary()
    unknown = mom.MomResult(backend="x", freq_hz=1e8, gain_dbi=2.0, peak_elevation_deg=0.0)
    assert unknown.swr is None
    assert "ohm" not in unknown.summary()


# --------------------------------------------------------------------------------------
# NEC deck export — verifiable without any solver
# --------------------------------------------------------------------------------------


def test_nec_deck_has_the_cards_a_solver_needs():
    model = mom.yagi_model(freq_hz=GRAVES_HZ, elements_m=mom.GRAVES_3EL_ELEMENTS, radius_m=0.003)
    deck = mom.to_nec_deck(model, GRAVES_HZ)
    lines = deck.splitlines()
    assert lines[0].startswith("CM")
    assert any(line.startswith("CE") for line in lines)
    assert sum(line.startswith("GW") for line in lines) == 3  # one per element
    assert any(line.startswith("GE 0") for line in lines)  # free space
    assert any(line.startswith("EX 0 2 ") for line in lines)  # source on the driven element
    assert any("143.050000" in line for line in lines if line.startswith("FR"))
    assert any(line.startswith("RP") for line in lines)
    assert lines[-1] == "EN"


def test_nec_deck_writes_the_right_ground_card():
    lam = wavelength_m(JOVE_HZ)
    over_real = mom.dipole_model(
        freq_hz=JOVE_HZ, length_m=lam / 2, height_m=3.0, ground=AVERAGE_GROUND
    )
    deck = mom.to_nec_deck(over_real, JOVE_HZ)
    assert "GE 1" in deck
    assert "GN 2" in deck and "13.000" in deck  # finite ground, permittivity carried through

    over_perfect = mom.dipole_model(
        freq_hz=JOVE_HZ, length_m=lam / 2, height_m=3.0, ground=PERFECT_GROUND
    )
    assert "GN 1" in mom.to_nec_deck(over_perfect, JOVE_HZ)  # perfect conductor card


def test_nec_export_is_an_export_and_says_why():
    """It hands you a deck rather than linking a GPL solver — the M2 openEMS reasoning."""
    doc = mom.to_nec_deck.__doc__
    assert "export" in doc and "not a driver" in doc
    assert "GPL" in doc  # the reason it is an export rather than a linked solver


# --------------------------------------------------------------------------------------
# The solver — anchors
# --------------------------------------------------------------------------------------


@needs_backend
def test_backend_reproduces_the_half_wave_dipole():
    """The anchor: 2.15 dBi and ~73 ohms, which every MoM code must get right."""
    lam = wavelength_m(GRAVES_HZ)
    model = mom.dipole_model(
        freq_hz=GRAVES_HZ, length_m=0.95 * lam / 2, radius_m=0.001, segments=21
    )
    result = mom.default_backend().solve(model, GRAVES_HZ)
    assert result.gain_dbi == pytest.approx(2.15, abs=0.15)
    assert result.feed_impedance_ohm is not None
    assert result.feed_impedance_ohm.real == pytest.approx(70.0, abs=8.0)
    # Cut 5% short of resonance, so it must be capacitive. Tier 1 cannot tell you this.
    assert result.feed_impedance_ohm.imag < 0


@needs_backend
def test_a_longer_element_swings_the_reactance_inductive():
    """Reactance sign versus length is the sanity check that the solve is really solving."""
    lam = wavelength_m(GRAVES_HZ)
    backend = mom.default_backend()
    short = backend.solve(
        mom.dipole_model(freq_hz=GRAVES_HZ, length_m=0.90 * lam / 2, radius_m=0.001), GRAVES_HZ
    )
    long = backend.solve(
        mom.dipole_model(freq_hz=GRAVES_HZ, length_m=1.02 * lam / 2, radius_m=0.001), GRAVES_HZ
    )
    assert short.feed_impedance_ohm.imag < 0 < long.feed_impedance_ohm.imag


@needs_backend
def test_tier2_closes_the_short_boom_yagi_gap_m5_flagged():
    """M5's ticket: Tier 1 read 4.47 dBi against a published 6.75. Tier 2 must do better.

    This is the whole justification for having a second tier. The endfire bound assumes a
    long array and M5 said so and shipped the shortfall; here the numerics get it right.
    """
    model = mom.yagi_model(freq_hz=GRAVES_HZ, elements_m=mom.GRAVES_3EL_ELEMENTS, radius_m=0.003)
    comparison = mom.compare_with_analytic(
        model, freq_hz=GRAVES_HZ, analytic_dbi=4.47, published_dbi=6.75
    )
    # MoM lands within a few tenths of the published figure...
    assert comparison.mom.gain_dbi == pytest.approx(6.75, abs=0.6)
    # ...and is much closer to it than the analytic estimate was.
    assert abs(comparison.mom.gain_dbi - 6.75) < abs(4.47 - 6.75)
    assert not comparison.agrees  # the two tiers genuinely disagree, and should
    assert any("mutual coupling" in n or "endfire" in n for n in comparison.notes)


@needs_backend
def test_tier2_agrees_with_tier1_on_the_long_boom_yagi():
    """Where Tier 1's assumption holds, the tiers should agree — and they do, to 0.3 dB."""
    model = mom.yagi_model(freq_hz=GRAVES_HZ, elements_m=mom.GRAVES_7EL_ELEMENTS, radius_m=0.003)
    comparison = mom.compare_with_analytic(
        model, freq_hz=GRAVES_HZ, analytic_dbi=11.24, published_dbi=11.6
    )
    assert comparison.mom.gain_dbi == pytest.approx(11.6, abs=0.5)
    assert comparison.agrees
    assert "published" in comparison.summary()


@needs_backend
def test_the_seven_element_feed_impedance_explains_its_folded_driven_element():
    """A real, checkable insight Tier 1 could never offer.

    Modelled with a straight driven element the design shows a poor match. The published
    antenna uses a FOLDED driven element, which steps the impedance up about four times —
    and this is the number that explains why.
    """
    model = mom.yagi_model(freq_hz=GRAVES_HZ, elements_m=mom.GRAVES_7EL_ELEMENTS, radius_m=0.003)
    result = mom.default_backend().solve(model, GRAVES_HZ)
    assert result.feed_impedance_ohm.real < 35.0  # low, as a close-spaced Yagi is
    assert result.swr is not None and result.swr > 2.0

    # Folding the driven element multiplies the impedance by four. Judge that by SWR, not
    # by |Z - 50|: 20 ohm and 80 ohm are nearly equidistant from 50 by difference, but their
    # SWRs are 2.5 and 1.6. Mismatch is a ratio, and using the difference instead is a real
    # and easy mistake — it was made once while writing this test.
    straight = result.feed_impedance_ohm.real
    swr_straight = max(straight, 50.0) / min(straight, 50.0)
    folded = 4 * straight
    swr_folded = max(folded, 50.0) / min(folded, 50.0)
    assert swr_folded < swr_straight


@needs_backend
def test_tier2_sees_the_mutual_coupling_tier1_cannot():
    """M5's other ticket: two dipoles do not stack by the textbook 3 dB.

    Tier 1 assumes 3.01 dB and NASA's published pair implies about 2.0. Tier 2 lands
    between them — it demonstrates the mechanism and recovers part of the gap, which is an
    honest partial result rather than a claimed resolution.
    """
    lam = wavelength_m(JOVE_HZ)
    length = 0.95 * lam / 2
    backend = mom.default_backend()
    single = backend.solve(
        mom.dipole_model(freq_hz=JOVE_HZ, length_m=length, radius_m=0.0016), JOVE_HZ
    )
    pair = backend.solve(
        mom.dipole_array_model(
            freq_hz=JOVE_HZ, length_m=length, spacing_m=20 * FOOT_M, radius_m=0.0016
        ),
        JOVE_HZ,
    )
    stacking = pair.gain_dbi - single.gain_dbi
    assert stacking < 3.01  # less than the ideal, which is the entire point
    assert stacking > 2.0  # but more than NASA's published pair implies
    # The coupling is visible directly in the feed impedance, not merely inferred from gain.
    assert abs(pair.feed_impedance_ohm - single.feed_impedance_ohm) > 5.0


@needs_backend
def test_driving_the_neighbour_or_not_is_a_different_antenna():
    lam = wavelength_m(JOVE_HZ)
    backend = mom.default_backend()
    common = dict(freq_hz=JOVE_HZ, length_m=0.95 * lam / 2, spacing_m=20 * FOOT_M, radius_m=0.0016)
    driven = backend.solve(mom.dipole_array_model(**common, drive_all=True), JOVE_HZ)
    parasitic = backend.solve(mom.dipole_array_model(**common, drive_all=False), JOVE_HZ)
    assert driven.gain_dbi != pytest.approx(parasitic.gain_dbi, abs=0.05)


@needs_backend
def test_ground_results_carry_the_mininec_caveat():
    """MININEC's ground model is its known weakness, and the result must say so."""
    lam = wavelength_m(JOVE_HZ)
    model = mom.dipole_model(
        freq_hz=JOVE_HZ,
        length_m=0.95 * lam / 2,
        radius_m=0.0016,
        height_m=10 * FOOT_M,
        ground=AVERAGE_GROUND,
    )
    result = mom.default_backend().solve(model, JOVE_HZ)
    assert any("ground model is its known weak point" in n for n in result.notes)
    # Ground still helps, as it must.
    assert result.gain_dbi > 2.15


@needs_backend
def test_comparison_reports_both_tiers_without_privileging_either():
    lam = wavelength_m(GRAVES_HZ)
    model = mom.dipole_model(freq_hz=GRAVES_HZ, length_m=0.95 * lam / 2, radius_m=0.001)
    comparison = mom.compare_with_analytic(model, freq_hz=GRAVES_HZ, analytic_dbi=2.15)
    assert comparison.agrees
    assert abs(comparison.difference_db) < 0.2
    text = comparison.summary()
    assert "analytic" in text and "pymininec" in text and "agree" in text


@needs_backend
def test_segmentation_warnings_reach_the_result():
    lam = wavelength_m(GRAVES_HZ)
    coarse = mom.WireModel(
        name="coarse dipole",
        wires=(mom.WireSpec((-lam / 4, 0, 0), (lam / 4, 0, 0), 0.001, 3),),
    )
    result = mom.default_backend().solve(coarse, GRAVES_HZ)
    assert any("segments per wavelength" in n for n in result.notes)
