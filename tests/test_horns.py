"""Tests for the M1 horn physics.

The anchors here are Balanis' own published worked examples, which is the strongest check
available short of building a horn: independent numbers, from the source the equations came
from, that our code must reproduce without any fitting.

Tolerances are stated with their reason. Where the book reads Fresnel values off printed
tables, ~0.1 dB is the honest tolerance and pretending to 1e-6 would be false precision.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from jansky_forge import horns
from jansky_forge.units import to_db, wavelength_m

HI_HZ = 1_420_405_751.768
HI_LAMBDA = wavelength_m(HI_HZ)
# WR-650 is the standard L-band waveguide, and what an L-band horn is usually fed with.
WR650_A, WR650_B = 0.1651, 0.08255


# --------------------------------------------------------------------------------------
# Fresnel integrals and geometry
# --------------------------------------------------------------------------------------


def test_fresnel_returns_c_then_s_not_scipys_order():
    """scipy hands back (S, C); every antenna text writes (C, S). Guard the swap."""
    c, s = horns.fresnel_cs(1.0)
    assert c == pytest.approx(0.779893, abs=1e-6)
    assert s == pytest.approx(0.438259, abs=1e-6)
    # C(x) -> 0.5 and S(x) -> 0.5 as x -> infinity.
    c_inf, s_inf = horns.fresnel_cs(50.0)
    assert c_inf == pytest.approx(0.5, abs=0.02)
    assert s_inf == pytest.approx(0.5, abs=0.02)


def test_apex_distance_is_the_similar_triangles_result():
    """rho1 = p_e * b1/(b1 - b). Directly checkable: a 2:1 flare doubles the apex distance."""
    rho1 = horns.apex_distance_e(aperture_b1_m=0.4, waveguide_b_m=0.2, axial_m=1.0)
    assert rho1 == pytest.approx(2.0)
    # And the inverse round-trips.
    assert horns.axial_length_e(rho1_m=rho1, aperture_b1_m=0.4, waveguide_b_m=0.2) == pytest.approx(
        1.0
    )
    rho2 = horns.apex_distance_h(aperture_a1_m=0.6, waveguide_a_m=0.2, axial_m=1.0)
    assert rho2 == pytest.approx(1.5)
    assert horns.axial_length_h(rho2_m=rho2, aperture_a1_m=0.6, waveguide_a_m=0.2) == pytest.approx(
        1.0
    )


def test_slant_is_longer_than_the_axial_apex_distance():
    """rho_e = sqrt(rho1^2 + (b1/2)^2) — the distinction that caused a real 7% bug here."""
    slant = horns.slant_e(rho1_m=6.0, aperture_b1_m=2.75)
    assert slant == pytest.approx(math.hypot(6.0, 1.375))
    assert slant > 6.0
    assert horns.slant_h(rho2_m=6.0, aperture_a1_m=5.5) == pytest.approx(math.hypot(6.0, 2.75))


@pytest.mark.parametrize(
    "call",
    [
        lambda: horns.apex_distance_e(aperture_b1_m=0.1, waveguide_b_m=0.2, axial_m=1.0),
        lambda: horns.apex_distance_h(aperture_a1_m=0.1, waveguide_a_m=0.2, axial_m=1.0),
        lambda: horns.apex_distance_e(aperture_b1_m=0.4, waveguide_b_m=0.2, axial_m=0.0),
    ],
)
def test_geometry_rejects_impossible_flares(call):
    with pytest.raises(ValueError):
        call()


# --------------------------------------------------------------------------------------
# Golden test: Balanis Example 13.5 (analysis)
# rho1 = rho2 = 6L, a1 = 5.5L, b1 = 2.75L, a = 0.5L, b = 0.25L
# --------------------------------------------------------------------------------------

EX135 = dict(rho1=6.0, rho2=6.0, a1=5.5, b1=2.75, a=0.5, b=0.25, lam=1.0)


def test_balanis_example_13_5_geometry():
    assert horns.slant_e(rho1_m=6.0, aperture_b1_m=2.75) == pytest.approx(6.1555, abs=1e-4)
    assert horns.slant_h(rho2_m=6.0, aperture_a1_m=5.5) == pytest.approx(6.6000, abs=1e-3)
    # Both axial flare lengths equal 5.454L, so the book's horn IS realizable.
    p_e = horns.axial_length_e(rho1_m=6.0, aperture_b1_m=2.75, waveguide_b_m=0.25)
    p_h = horns.axial_length_h(rho2_m=6.0, aperture_a1_m=5.5, waveguide_a_m=0.5)
    assert p_e == pytest.approx(5.454, abs=1e-3)
    assert p_h == pytest.approx(5.454, abs=1e-3)
    assert horns.realizability(axial_e_m=p_e, axial_h_m=p_h).realizable


def test_balanis_example_13_5_phase_deviations():
    s = horns.phase_deviation_e(aperture_b1_m=2.75, rho1_m=6.0, wavelength_metres=1.0)
    t = horns.phase_deviation_h(aperture_a1_m=5.5, rho2_m=6.0, wavelength_metres=1.0)
    assert s == pytest.approx(0.1575, abs=1e-3)
    assert t == pytest.approx(0.63, abs=1e-3)


def test_balanis_example_13_5_gains():
    """Book: D_E = 12.79, D_H = 7.52, D_p = 18.78 dB.

    Tolerance 0.1 dB / 0.1 linear: the book looks its Fresnel values up in printed tables,
    so exact agreement is neither expected nor a sign of correctness.
    """
    d_e = horns.e_plane_sectoral_gain(
        waveguide_a_m=0.5, aperture_b1_m=2.75, rho1_m=6.0, wavelength_metres=1.0
    )
    d_h = horns.h_plane_sectoral_gain(
        waveguide_b_m=0.25, aperture_a1_m=5.5, rho2_m=6.0, wavelength_metres=1.0
    )
    d_p = horns.pyramidal_gain(
        waveguide_a_m=0.5,
        waveguide_b_m=0.25,
        aperture_a1_m=5.5,
        aperture_b1_m=2.75,
        rho1_m=6.0,
        rho2_m=6.0,
        wavelength_metres=1.0,
    )
    assert d_e == pytest.approx(12.79, abs=0.1)
    assert d_h == pytest.approx(7.52, abs=0.1)
    assert to_db(d_p) == pytest.approx(18.78, abs=0.1)


# --------------------------------------------------------------------------------------
# Golden test: Balanis Example 13.6 (design)
# G0 = 22.6 dB, f = 11 GHz, WR-90 (a = 2.286 cm, b = 1.016 cm)
# --------------------------------------------------------------------------------------


def test_balanis_example_13_6_design():
    """Book: a1 = 6.002L, b1 = 4.715L, p_e = p_h = 10.005L.

    Our synthesis solves for a true Fresnel gain of exactly 22.6 dB, while the book's design
    equation uses a 50%-efficiency approximation whose dimensions actually realize ~22.5 dB.
    Ours therefore come out a shade larger, and the tolerances below encode that rather than
    pretending the two procedures are identical.
    """
    lam = wavelength_m(11e9)
    design = horns.design_pyramidal_horn(
        gain_dbi=22.6, freq_hz=11e9, waveguide_a_m=0.02286, waveguide_b_m=0.01016
    )
    assert design.aperture_a1_m / lam == pytest.approx(6.002, rel=0.01)
    assert design.aperture_b1_m / lam == pytest.approx(4.715, rel=0.01)
    assert design.axial_length_m / lam == pytest.approx(10.005, rel=0.03)
    assert design.gain_dbi == pytest.approx(22.6, abs=1e-6)


# --------------------------------------------------------------------------------------
# Synthesis
# --------------------------------------------------------------------------------------


def test_synthesis_round_trips_at_every_practical_gain():
    for target in (12.0, 15.0, 18.0, 22.0, 26.0):
        design = horns.design_pyramidal_horn(
            gain_dbi=target, freq_hz=HI_HZ, waveguide_a_m=WR650_A, waveguide_b_m=WR650_B
        )
        assert design.gain_dbi == pytest.approx(target, abs=1e-6)


def test_synthesis_lands_exactly_on_the_optimum_flare():
    """The strongest internal check: the phase deviations must hit 1/4 and 3/8 exactly.

    Nothing in the solver targets those numbers — it solves for gain. Their appearing at the
    textbook optima means the closed-form aperture relations and the geometry agree.
    """
    design = horns.design_pyramidal_horn(
        gain_dbi=18.0, freq_hz=HI_HZ, waveguide_a_m=WR650_A, waveguide_b_m=WR650_B
    )
    assert design.phase_deviation_e == pytest.approx(horns.OPTIMUM_PHASE_DEVIATION_E, abs=1e-9)
    assert design.phase_deviation_h == pytest.approx(horns.OPTIMUM_PHASE_DEVIATION_H, abs=1e-9)


def test_optimum_designs_reproduce_the_textbook_51_percent():
    """Efficiency is an OUTPUT here, never an input. It must land near the textbook value."""
    for target in (12.0, 18.0, 25.0):
        d = horns.design_pyramidal_horn(
            gain_dbi=target, freq_hz=HI_HZ, waveguide_a_m=WR650_A, waveguide_b_m=WR650_B
        )
        aperture_gain = 4.0 * math.pi * d.aperture_a1_m * d.aperture_b1_m / HI_LAMBDA**2
        eta = 10 ** (d.gain_dbi / 10.0) / aperture_gain
        assert eta == pytest.approx(horns.OPTIMUM_PYRAMIDAL_EFFICIENCY, abs=0.001)


def test_optimum_aperture_matches_the_closed_form():
    """b1 and a1 are roots of quadratics; check against the quadratic formula directly."""
    axial = 0.6
    a1, b1 = horns.optimum_aperture_for_axial(
        axial_length_m=axial, freq_hz=HI_HZ, waveguide_a_m=WR650_A, waveguide_b_m=WR650_B
    )
    assert b1 == pytest.approx((WR650_B + math.sqrt(WR650_B**2 + 8 * HI_LAMBDA * axial)) / 2)
    assert a1 == pytest.approx((WR650_A + math.sqrt(WR650_A**2 + 12 * HI_LAMBDA * axial)) / 2)


def test_synthesis_refuses_impossible_targets():
    with pytest.raises(ValueError, match="below what this waveguide"):
        horns.design_pyramidal_horn(
            gain_dbi=1.0, freq_hz=HI_HZ, waveguide_a_m=WR650_A, waveguide_b_m=WR650_B
        )
    with pytest.raises(ValueError, match="reflector"):
        horns.design_pyramidal_horn(
            gain_dbi=60.0, freq_hz=HI_HZ, waveguide_a_m=WR650_A, waveguide_b_m=WR650_B
        )
    with pytest.raises(ValueError, match="waveguide dimensions"):
        horns.design_pyramidal_horn(gain_dbi=18.0, freq_hz=HI_HZ, waveguide_a_m=0, waveguide_b_m=0)


# --------------------------------------------------------------------------------------
# The physics M0 could not express
# --------------------------------------------------------------------------------------


def test_over_flaring_a_fixed_length_horn_loses_gain():
    """The headline M1 behaviour: gain PEAKS at the optimum flare, then falls.

    An efficiency-constant model rises monotonically with aperture forever and would happily
    advise someone to build a horn that performs worse.
    """
    axial = 0.5
    gains = []
    for b1 in (0.30, 0.45, 0.5235, 0.70, 1.00):
        rho1 = horns.apex_distance_e(aperture_b1_m=b1, waveguide_b_m=WR650_B, axial_m=axial)
        gains.append(
            horns.e_plane_sectoral_gain(
                waveguide_a_m=WR650_A,
                aperture_b1_m=b1,
                rho1_m=rho1,
                wavelength_metres=HI_LAMBDA,
            )
        )
    peak = max(range(len(gains)), key=gains.__getitem__)
    assert 0 < peak < len(gains) - 1, "gain should peak in the interior, not at an end"
    assert gains[-1] < gains[peak], "an over-flared horn must lose gain"


# --------------------------------------------------------------------------------------
# Patterns
# --------------------------------------------------------------------------------------


def test_computed_beamwidths_agree_with_the_optimum_rules_of_thumb():
    """For optimum designs, 54*lam/b1 and 78*lam/a1 should be within a few percent.

    Two independent routes — an aperture integration and a textbook approximation — landing
    together is what makes either believable.
    """
    for target in (12.0, 15.0, 18.0, 22.0):
        d = horns.design_pyramidal_horn(
            gain_dbi=target, freq_hz=HI_HZ, waveguide_a_m=WR650_A, waveguide_b_m=WR650_B
        )
        e_hp, h_hp = horns.pattern_beamwidths(
            aperture_a1_m=d.aperture_a1_m,
            aperture_b1_m=d.aperture_b1_m,
            rho1_m=d.rho1_m,
            rho2_m=d.rho2_m,
            freq_hz=HI_HZ,
        )
        assert e_hp == pytest.approx(54.0 * HI_LAMBDA / d.aperture_b1_m, rel=0.05)
        assert h_hp == pytest.approx(78.0 * HI_LAMBDA / d.aperture_a1_m, rel=0.05)


def test_h_plane_sidelobes_sit_below_e_plane_because_of_the_cosine_taper():
    """The most visible asymmetry in any horn pattern — and an orientation check."""
    d = horns.design_pyramidal_horn(
        gain_dbi=18.0, freq_hz=HI_HZ, waveguide_a_m=WR650_A, waveguide_b_m=WR650_B
    )
    theta = np.linspace(30.0, 90.0, 61)
    e_pat = horns.e_plane_pattern(
        aperture_b1_m=d.aperture_b1_m, rho1_m=d.rho1_m, freq_hz=HI_HZ, theta_deg=theta
    )
    h_pat = horns.h_plane_pattern(
        aperture_a1_m=d.aperture_a1_m, rho2_m=d.rho2_m, freq_hz=HI_HZ, theta_deg=theta
    )
    assert np.all(h_pat < e_pat)


def test_patterns_peak_on_boresight_and_are_normalized():
    d = horns.design_pyramidal_horn(
        gain_dbi=15.0, freq_hz=HI_HZ, waveguide_a_m=WR650_A, waveguide_b_m=WR650_B
    )
    theta = np.linspace(-60.0, 60.0, 241)
    for pattern in (
        horns.e_plane_pattern(
            aperture_b1_m=d.aperture_b1_m, rho1_m=d.rho1_m, freq_hz=HI_HZ, theta_deg=theta
        ),
        horns.h_plane_pattern(
            aperture_a1_m=d.aperture_a1_m, rho2_m=d.rho2_m, freq_hz=HI_HZ, theta_deg=theta
        ),
    ):
        assert pattern.max() == pytest.approx(0.0, abs=1e-9)
        assert np.argmax(pattern) == len(theta) // 2  # symmetric about boresight
        assert pattern[0] < -10.0


def test_patterns_are_referenced_to_boresight_not_the_sampled_maximum():
    """A sweep that excludes boresight must not be silently renormalized to its own peak."""
    d = horns.design_pyramidal_horn(
        gain_dbi=18.0, freq_hz=HI_HZ, waveguide_a_m=WR650_A, waveguide_b_m=WR650_B
    )
    kw = dict(aperture_b1_m=d.aperture_b1_m, rho1_m=d.rho1_m, freq_hz=HI_HZ)
    full = horns.e_plane_pattern(theta_deg=np.array([0.0, 40.0, 60.0]), **kw)
    partial = horns.e_plane_pattern(theta_deg=np.array([40.0, 60.0]), **kw)
    assert partial == pytest.approx(full[1:])
    assert partial.max() < -5.0  # far off boresight, so nothing should sit at 0 dB


def test_beamwidth_search_reports_when_there_is_no_main_beam():
    with pytest.raises(ValueError, match="never falls to -3 dB"):
        horns.pattern_beamwidths(
            aperture_a1_m=0.05,
            aperture_b1_m=0.05,
            rho1_m=10.0,
            rho2_m=10.0,
            freq_hz=HI_HZ,
            max_theta_deg=20.0,
        )


# --------------------------------------------------------------------------------------
# Conical horns
# --------------------------------------------------------------------------------------


def test_conical_optimum_reproduces_balanis_loss_figure():
    """At s = 3/8 the loss figure is ~2.9 dB, i.e. about 51% aperture efficiency."""
    loss = horns.conical_loss_figure_db(horns.OPTIMUM_CONICAL_PHASE_DEVIATION)
    assert loss == pytest.approx(2.9, abs=0.05)
    assert 10 ** (-loss / 10) == pytest.approx(horns.OPTIMUM_CONICAL_EFFICIENCY, abs=0.005)


def test_conical_slant_and_the_unknown_throat_convention():
    # With no throat the apex sits at the throat plane: slant = hypot(axial, radius).
    assert horns.conical_slant_m(aperture_diameter_m=0.4, axial_length_m=0.5) == pytest.approx(
        math.hypot(0.5, 0.2)
    )
    # A real throat pushes the apex back, lengthening the slant.
    assert horns.conical_slant_m(
        aperture_diameter_m=0.4, axial_length_m=0.5, throat_diameter_m=0.15
    ) > math.hypot(0.5, 0.2)
    with pytest.raises(ValueError, match="smaller than the aperture"):
        horns.conical_slant_m(aperture_diameter_m=0.2, axial_length_m=0.5, throat_diameter_m=0.3)


def test_conical_gain_agrees_with_an_independent_aperture_integration():
    """Cross-check Balanis' empirical loss figure against a first-principles integration.

    The integration route reproduces the Fresnel gain to 0.000 dB when applied to a
    *pyramidal* horn, so it is a genuinely independent instrument here. The two agree within
    0.25 dB while the empirical fit is in its valid range — worth knowing, and worth knowing
    that they part company beyond it.
    """
    for s_target in (0.1, 0.25, 0.375, 0.5):
        slant = 1.0
        d = math.sqrt(8 * HI_LAMBDA * slant * s_target)
        empirical = to_db(
            horns.conical_gain(aperture_diameter_m=d, slant_m=slant, wavelength_metres=HI_LAMBDA)
        )
        integrated = to_db(
            horns.conical_gain_by_aperture_integration(
                aperture_diameter_m=d, slant_m=slant, wavelength_metres=HI_LAMBDA
            )
        )
        assert abs(integrated - empirical) < 0.25


def test_conical_aperture_integration_reproduces_the_te11_efficiency():
    """With no phase error, the TE11 circular aperture is 83.6% efficient. Textbook value."""
    for radius in (0.3, 0.5, 1.0):
        gain = horns.conical_gain_by_aperture_integration(
            aperture_diameter_m=2 * radius, slant_m=1e9, wavelength_metres=HI_LAMBDA
        )
        eta = gain / (4 * math.pi * math.pi * radius**2 / HI_LAMBDA**2)
        assert eta == pytest.approx(0.836, abs=0.002)


def test_conical_synthesis_round_trips():
    for target in (15.0, 18.0, 20.6):
        d = horns.design_conical_horn(gain_dbi=target, freq_hz=HI_HZ)
        assert d.gain_dbi == pytest.approx(target, abs=1e-6)
        # Optimum flare: d = sqrt(3*lambda*l).
        assert d.aperture_diameter_m == pytest.approx(math.sqrt(3 * HI_LAMBDA * d.slant_m))
        assert "dBi" in d.summary()


def test_conical_synthesis_refuses_impossible_targets():
    with pytest.raises(ValueError, match="smallest useful"):
        horns.design_conical_horn(gain_dbi=-5.0, freq_hz=HI_HZ)
    with pytest.raises(ValueError, match="reflector"):
        horns.design_conical_horn(gain_dbi=60.0, freq_hz=HI_HZ)


@pytest.mark.parametrize(
    "call",
    [
        lambda: horns.conical_gain(aperture_diameter_m=0.0, slant_m=1.0, wavelength_metres=0.21),
        lambda: horns.conical_gain_by_aperture_integration(
            aperture_diameter_m=0.4, slant_m=0.0, wavelength_metres=0.21
        ),
    ],
)
def test_conical_rejects_impossible_geometry(call):
    with pytest.raises(ValueError):
        call()


# --------------------------------------------------------------------------------------
# Realizability
# --------------------------------------------------------------------------------------


def test_realizability_accepts_one_axial_length_and_rejects_two():
    ok = horns.realizability(axial_e_m=0.5, axial_h_m=0.5)
    assert ok.realizable and ok.mismatch == 0.0
    assert "single buildable horn" in ok.message

    bad = horns.realizability(axial_e_m=0.68185, axial_h_m=0.57836)
    assert not bad.realizable
    assert bad.mismatch == pytest.approx(0.152, abs=0.002)
    assert "NOT a single buildable" in bad.message
    assert "681.8" in bad.message and "578.4" in bad.message  # actionable, not just a flag


def test_realizability_tolerates_rounding_in_published_dimensions():
    """A source quoting 500 and 501 mm has rounded, not designed something unbuildable."""
    assert horns.realizability(axial_e_m=0.500, axial_h_m=0.501).realizable


def test_realizability_rejects_nonsense_input():
    with pytest.raises(ValueError, match="must be positive"):
        horns.realizability(axial_e_m=0.0, axial_h_m=0.0)


def test_synthesized_horns_are_always_realizable():
    """The property that matters: synthesis cannot emit an unbuildable design."""
    for target in (12.0, 18.0, 24.0):
        d = horns.design_pyramidal_horn(
            gain_dbi=target, freq_hz=HI_HZ, waveguide_a_m=WR650_A, waveguide_b_m=WR650_B
        )
        p_e = horns.axial_length_e(
            rho1_m=d.rho1_m, aperture_b1_m=d.aperture_b1_m, waveguide_b_m=WR650_B
        )
        p_h = horns.axial_length_h(
            rho2_m=d.rho2_m, aperture_a1_m=d.aperture_a1_m, waveguide_a_m=WR650_A
        )
        assert horns.realizability(axial_e_m=p_e, axial_h_m=p_h).realizable
        assert p_e == pytest.approx(d.axial_length_m)
