"""Tests for M3: dish illumination, feed matching, blockage, and the waveguide probe.

Two external anchors carry this file, in keeping with honesty invariant 7 (self-consistency
is not verification):

* the reflector integrals must reproduce the textbook **-10 to -11 dB optimum edge taper**
  and ~82-85% aperture efficiency, without either being an input;
* the probe design must reproduce a **published, built** 21 cm horn's probe geometry.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from jansky_forge import feeds
from jansky_forge.apertures import ParabolicDish
from jansky_forge.horns import design_pyramidal_horn

HI_HZ = 1_420_405_751.768
WR650_A, WR650_B = 0.1651, 0.08255


# --------------------------------------------------------------------------------------
# The anchor: the optimum edge taper must emerge, not be assumed
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("q", [0.5, 1.0, 1.5, 2.0, 3.0, 4.0])
def test_optimum_edge_taper_emerges_at_the_textbook_value(q):
    """Maximizing aperture efficiency must land near -10.9 dB for ANY feed shape.

    Nothing in the optimizer targets an edge taper — it maximizes efficiency. That the
    answer is the same -10 to -11 dB across an eightfold range of feed directivity is both
    the textbook result and the reason the rule of thumb is trustworthy.
    """
    match = feeds.best_f_over_d(feeds.CosQFeed(q=q))
    assert match.edge_taper_db == pytest.approx(feeds.OPTIMUM_EDGE_TAPER_DB, abs=0.2)
    assert 0.80 < match.aperture_efficiency < 0.86


def test_deeper_dishes_want_wider_feeds():
    """A physical monotonicity: the smaller the f/D, the wider the rim, the wider the feed."""
    rim_angles = []
    for f_over_d in (0.3, 0.4, 0.5, 0.7):
        wanted = feeds.best_feed_for_dish(f_over_d=f_over_d)
        assert wanted.f_over_d == pytest.approx(f_over_d)
        rim_angles.append(wanted.subtended_half_angle_deg)
    # Rim angle falls monotonically as the dish gets shallower.
    assert rim_angles == sorted(rim_angles, reverse=True)
    shallow = feeds.best_feed_for_dish(f_over_d=0.7).subtended_half_angle_deg
    deep = feeds.best_feed_for_dish(f_over_d=0.3).subtended_half_angle_deg
    assert deep > shallow


def test_efficiency_components_behave_as_physics_requires():
    """Spillover improves with a tighter feed; illumination gets worse. That tension IS M3."""
    theta0 = 60.0
    narrow = feeds.CosQFeed(q=6.0)
    wide = feeds.CosQFeed(q=0.4)
    assert feeds.spillover_efficiency(narrow, theta0) > feeds.spillover_efficiency(wide, theta0)
    assert feeds.illumination_efficiency(narrow, theta0) < feeds.illumination_efficiency(
        wide, theta0
    )
    for feed in (narrow, wide):
        assert 0.0 < feeds.aperture_efficiency(feed, theta0) <= 1.0


# --------------------------------------------------------------------------------------
# Geometry and taper
# --------------------------------------------------------------------------------------


def test_space_attenuation_of_known_dishes():
    # f/D = 0.25 puts the rim at 90 deg: 40*log10(cos(45)) = -6.02 dB
    assert feeds.space_attenuation_db(90.0) == pytest.approx(-6.0206, abs=1e-3)
    # A shallow dish barely suffers: 40*log10(cos(15 deg)) = -0.602 dB
    assert feeds.space_attenuation_db(30.0) == pytest.approx(-0.6022, abs=1e-3)
    assert feeds.space_attenuation_db(0.0) == pytest.approx(0.0)


def test_f_over_d_round_trips_through_the_rim_angle():
    for f_over_d in (0.25, 0.35, 0.4, 0.6):
        theta0 = math.degrees(2.0 * math.atan(1.0 / (4.0 * f_over_d)))
        assert feeds.f_over_d_from_subtended_angle(theta0) == pytest.approx(f_over_d)
    assert feeds.f_over_d_from_subtended_angle(90.0) == pytest.approx(0.25)
    with pytest.raises(ValueError):
        feeds.f_over_d_from_subtended_angle(0.0)


def test_edge_taper_combines_the_feed_pattern_and_the_space_loss():
    """The quoted 'edge taper' is both effects, which is why it is not just the feed's -3 dB."""
    feed = feeds.CosQFeed(q=1.0)
    theta0 = 60.0
    feed_only = 10 * math.log10(math.cos(math.radians(theta0)) ** 2)
    total = feeds.edge_taper_db(feed, theta0)
    assert total == pytest.approx(feed_only + feeds.space_attenuation_db(theta0))
    assert total < feed_only  # the space term always makes it deeper


def test_cosq_beamwidth_round_trips():
    for hpbw in (30.0, 60.0, 90.0, 120.0):
        feed = feeds.CosQFeed.from_beamwidth(hpbw)
        assert feed.half_power_beamwidth_deg == pytest.approx(hpbw, rel=1e-9)
    with pytest.raises(ValueError):
        feeds.CosQFeed.from_beamwidth(200.0)
    with pytest.raises(ValueError):
        feeds.CosQFeed(q=0.0)


def test_cosq_feed_radiates_nothing_behind_itself():
    feed = feeds.CosQFeed(q=1.0)
    assert feed.gain_relative(np.array([math.pi * 0.6]))[0] == 0.0
    assert feed.gain_relative(np.array([0.0]))[0] == pytest.approx(1.0)


# --------------------------------------------------------------------------------------
# Real horns as feeds — the M1-to-M3 join
# --------------------------------------------------------------------------------------


def _horn_feed(gain_dbi: float) -> feeds.HornFeed:
    horn = design_pyramidal_horn(
        gain_dbi=gain_dbi, freq_hz=HI_HZ, waveguide_a_m=WR650_A, waveguide_b_m=WR650_B
    )
    return feeds.HornFeed(
        aperture_a1_m=horn.aperture_a1_m,
        aperture_b1_m=horn.aperture_b1_m,
        rho1_m=horn.rho1_m,
        rho2_m=horn.rho2_m,
        freq_hz=HI_HZ,
    )


def test_a_real_horn_can_illuminate_a_dish_and_declares_its_approximation():
    feed = _horn_feed(12.0)
    match = feeds.evaluate_feed(feed, f_over_d=0.4)
    assert 0.0 < match.aperture_efficiency < 1.0
    # The rotational-symmetry approximation must reach the user, not stay in a docstring.
    assert any("not rotationally symmetric" in n for n in match.notes)


def test_a_more_directive_horn_wants_a_shallower_dish():
    """Physical monotonicity across the M1/M3 boundary."""
    assert (
        feeds.best_f_over_d(_horn_feed(16.0)).f_over_d
        > feeds.best_f_over_d(_horn_feed(11.0)).f_over_d
    )


def test_horn_pattern_table_is_accurate_and_cached():
    """The interpolation exists for speed; it must not cost accuracy."""
    from jansky_forge.horns import e_plane_pattern, h_plane_pattern

    horn = design_pyramidal_horn(
        gain_dbi=13.0, freq_hz=HI_HZ, waveguide_a_m=WR650_A, waveguide_b_m=WR650_B
    )
    feed = feeds.HornFeed(
        aperture_a1_m=horn.aperture_a1_m,
        aperture_b1_m=horn.aperture_b1_m,
        rho1_m=horn.rho1_m,
        rho2_m=horn.rho2_m,
        freq_hz=HI_HZ,
    )
    angles = np.array([3.7, 17.3, 41.9, 63.1, 79.5])
    tabulated = 10 * np.log10(feed.gain_relative(np.radians(angles)))
    direct = (
        e_plane_pattern(
            aperture_b1_m=horn.aperture_b1_m,
            rho1_m=horn.rho1_m,
            freq_hz=HI_HZ,
            theta_deg=angles,
        )
        + h_plane_pattern(
            aperture_a1_m=horn.aperture_a1_m,
            rho2_m=horn.rho2_m,
            freq_hz=HI_HZ,
            theta_deg=angles,
        )
    ) / 2
    assert np.max(np.abs(tabulated - direct)) < 0.01  # dB
    # Behind the horn the model contributes nothing.
    assert feed.gain_relative(np.array([math.pi * 0.75]))[0] == 0.0


# --------------------------------------------------------------------------------------
# Blockage and mesh
# --------------------------------------------------------------------------------------


def test_central_blockage_hurts_more_than_its_area():
    """(1 - (d/D)^2)^2 — a 10% diameter blocker costs ~2% of gain, not 1%."""
    eta = feeds.central_blockage_efficiency(dish_diameter_m=1.0, blocker_diameter_m=0.1)
    assert eta == pytest.approx((1 - 0.01) ** 2)
    area_fraction = 0.01
    assert (1 - eta) > area_fraction  # the loss exceeds the blocked area fraction
    assert feeds.central_blockage_efficiency(dish_diameter_m=1.0, blocker_diameter_m=0.0) == 1.0


@pytest.mark.parametrize(
    "kwargs",
    [
        dict(dish_diameter_m=0.0, blocker_diameter_m=0.1),
        dict(dish_diameter_m=1.0, blocker_diameter_m=1.5),
        dict(dish_diameter_m=1.0, blocker_diameter_m=-0.1),
    ],
)
def test_central_blockage_rejects_impossible_geometry(kwargs):
    with pytest.raises(ValueError):
        feeds.central_blockage_efficiency(**kwargs)


def test_strut_blockage_scales_with_the_shadow():
    thin = feeds.strut_blockage_efficiency(
        dish_diameter_m=1.0, strut_count=3, strut_width_m=0.005, strut_length_m=0.5
    )
    thick = feeds.strut_blockage_efficiency(
        dish_diameter_m=1.0, strut_count=3, strut_width_m=0.02, strut_length_m=0.5
    )
    assert 1.0 > thin > thick > 0.0
    assert (
        feeds.strut_blockage_efficiency(
            dish_diameter_m=1.0, strut_count=0, strut_width_m=0.0, strut_length_m=0.0
        )
        == 1.0
    )
    with pytest.raises(ValueError, match="entire aperture"):
        feeds.strut_blockage_efficiency(
            dish_diameter_m=1.0, strut_count=4, strut_width_m=1.0, strut_length_m=1.0
        )
    with pytest.raises(ValueError, match="negative"):
        feeds.strut_blockage_efficiency(
            dish_diameter_m=1.0, strut_count=-1, strut_width_m=0.0, strut_length_m=0.0
        )


def test_mesh_verdict_tracks_the_lambda_over_ten_rule():
    """The same mesh is fine at 21 cm and useless at Ku band — the point of the check."""
    ratio_l, text_l = feeds.mesh_verdict(mesh_opening_m=0.012, freq_hz=HI_HZ)
    assert ratio_l < 0.1 and "fine" in text_l
    ratio_ku, text_ku = feeds.mesh_verdict(mesh_opening_m=0.012, freq_hz=1.22e10)
    assert ratio_ku > 0.2 and "too open" in text_ku
    assert feeds.mesh_verdict(mesh_opening_m=0.002, freq_hz=HI_HZ)[1].endswith("effectively solid.")
    assert "marginal" in feeds.mesh_verdict(mesh_opening_m=0.03, freq_hz=HI_HZ)[1]


# --------------------------------------------------------------------------------------
# The waveguide probe — anchored on a published build
# --------------------------------------------------------------------------------------


def test_probe_reproduces_a_published_21cm_build():
    """PhysicsOpenLab's oil-can horn: 52.5 mm probe, 76.4 mm from the backshort.

    An external anchor on a horn that was actually built and used to detect hydrogen — the
    strongest check available for this part of the package.
    """
    design = feeds.design_probe(freq_hz=HI_HZ, waveguide_a_m=0.146, waveguide_b_m=0.117)
    assert design.probe_length_m * 1000 == pytest.approx(52.5, abs=0.5)
    assert design.backshort_distance_m * 1000 == pytest.approx(76.4, abs=0.3)
    assert design.cutoff_freq_hz / 1e6 == pytest.approx(1026.7, abs=1.0)


def test_guide_wavelength_exceeds_free_space_and_the_backshort_is_not_the_probe():
    """The error this design exists to prevent: they are different quarter waves."""
    design = feeds.design_probe(freq_hz=HI_HZ, waveguide_a_m=WR650_A, waveguide_b_m=WR650_B)
    free_space_quarter = 299_792_458.0 / HI_HZ / 4
    assert design.guide_wavelength_m > 299_792_458.0 / HI_HZ
    assert design.probe_length_m == pytest.approx(free_space_quarter)
    assert design.backshort_distance_m > free_space_quarter
    # At 21 cm in WR-650 the two differ by ~16 mm — enough to ruin a match.
    assert (design.backshort_distance_m - free_space_quarter) * 1000 == pytest.approx(15.8, abs=1.0)
    assert any("common error" in n for n in design.notes)


def test_probe_refuses_a_waveguide_below_cutoff():
    with pytest.raises(ValueError, match="below this waveguide"):
        feeds.design_probe(freq_hz=HI_HZ, waveguide_a_m=0.05, waveguide_b_m=0.025)


def test_probe_warns_when_the_guide_is_overmoded():
    """WR-650 at 3 GHz propagates TE20; the single-mode assumptions stop holding."""
    design = feeds.design_probe(freq_hz=3e9, waveguide_a_m=WR650_A, waveguide_b_m=WR650_B)
    assert any("overmoded" in n for n in design.notes)


def test_probe_warns_near_cutoff_and_on_swapped_dimensions():
    near = feeds.design_probe(freq_hz=0.95e9, waveguide_a_m=WR650_A, waveguide_b_m=WR650_B)
    assert any("close to cutoff" in n for n in near.notes)
    swapped = feeds.design_probe(freq_hz=HI_HZ, waveguide_a_m=0.2, waveguide_b_m=0.3)
    assert any("right way round" in n for n in swapped.notes)
    with pytest.raises(ValueError, match="must be positive"):
        feeds.design_probe(freq_hz=HI_HZ, waveguide_a_m=0.0, waveguide_b_m=0.1)


def test_probe_summary_is_readable():
    text = feeds.design_probe(freq_hz=HI_HZ, waveguide_a_m=WR650_A, waveguide_b_m=WR650_B).summary()
    assert "probe" in text and "backshort" in text and "mm" in text


# --------------------------------------------------------------------------------------
# The dish, now that efficiency is computed
# --------------------------------------------------------------------------------------


def test_a_dish_with_a_feed_computes_its_efficiency_instead_of_assuming_it():
    assumed = ParabolicDish(diameter_m=0.7, f_over_d=0.35).characterize(HI_HZ)
    computed = ParabolicDish(
        diameter_m=0.7, f_over_d=0.35, feed=feeds.CosQFeed.from_beamwidth(108.0)
    ).characterize(HI_HZ)
    assert any("assumed constants" in n for n in assumed.notes)
    assert any("COMPUTED from the feed pattern" in n for n in computed.notes)
    # A well-matched feed beats the generic constants.
    assert computed.aperture_efficiency > assumed.aperture_efficiency
    assert "edge_taper_db" in computed.detail
    assert computed.detail["edge_taper_db"] == pytest.approx(-10.0, abs=1.5)


def test_a_badly_matched_feed_is_reported_as_such():
    """A too-directive feed under-lights the dish, and the dish must say so."""
    tight = ParabolicDish(
        diameter_m=0.7, f_over_d=0.35, feed=feeds.CosQFeed.from_beamwidth(35.0)
    ).characterize(HI_HZ)
    assert tight.detail["edge_taper_db"] < -16.0
    assert any("outer dish is barely lit" in n for n in tight.notes)

    loose = ParabolicDish(
        diameter_m=0.7, f_over_d=0.7, feed=feeds.CosQFeed.from_beamwidth(150.0)
    ).characterize(HI_HZ)
    assert any("spills onto the ground" in n for n in loose.notes)


def test_physical_blockage_overrides_the_blockage_constant():
    plain = ParabolicDish(diameter_m=1.0, blockage_efficiency=1.0).characterize(HI_HZ)
    blocked = ParabolicDish(
        diameter_m=1.0,
        blockage_efficiency=1.0,
        feed_blockage_diameter_m=0.15,
        strut_count=3,
        strut_width_m=0.01,
        strut_length_m=0.4,
    ).characterize(HI_HZ)
    assert blocked.detail["blockage_efficiency"] < plain.detail["blockage_efficiency"]
    assert any("offset dish avoids this" in n for n in blocked.notes)


def test_mesh_note_is_advisory_and_changes_no_number():
    solid = ParabolicDish(diameter_m=1.0).characterize(HI_HZ)
    meshed = ParabolicDish(diameter_m=1.0, mesh_opening_m=0.05).characterize(HI_HZ)
    assert meshed.gain_dbi == pytest.approx(solid.gain_dbi)
    assert any("advisory" in n for n in meshed.notes)


def test_dish_detail_exposes_the_efficiency_breakdown():
    """Which term dominates is the actionable part, so every term is reported."""
    char = ParabolicDish(diameter_m=0.7, f_over_d=0.35, feed=feeds.CosQFeed(q=0.7)).characterize(
        HI_HZ
    )
    for key in (
        "illumination_efficiency",
        "spillover_efficiency",
        "blockage_efficiency",
        "ruze_efficiency",
        "edge_taper_db",
        "subtended_half_angle_deg",
    ):
        assert key in char.detail
    product = (
        char.detail["illumination_efficiency"]
        * char.detail["spillover_efficiency"]
        * char.detail["blockage_efficiency"]
        * char.detail["ruze_efficiency"]
    )
    assert char.aperture_efficiency == pytest.approx(product, rel=1e-9)


def test_conical_horn_feed_is_usable_and_labelled_approximate():
    """Conical horns are the natural dish feed, so M3 needs a path even without their patterns."""
    feed = feeds.conical_horn_feed(aperture_diameter_m=0.30, freq_hz=HI_HZ)
    assert isinstance(feed, feeds.CosQFeed)
    # sqrt(60*70)*lambda/d = 64.8 * 211.06/300 = 45.6 deg
    assert feed.half_power_beamwidth_deg == pytest.approx(45.6, abs=0.5)
    # A bigger cone is more directive and wants a shallower dish.
    bigger = feeds.conical_horn_feed(aperture_diameter_m=0.60, freq_hz=HI_HZ)
    assert bigger.half_power_beamwidth_deg < feed.half_power_beamwidth_deg
    assert feeds.best_f_over_d(bigger).f_over_d > feeds.best_f_over_d(feed).f_over_d
    # The docstring must own the stacked approximation rather than bury it.
    assert "Approximate" in feeds.conical_horn_feed.__doc__
    assert "two approximations stacked" in feeds.conical_horn_feed.__doc__


def test_conical_horn_feed_refuses_a_sub_wavelength_aperture():
    with pytest.raises(ValueError, match="too broad"):
        feeds.conical_horn_feed(aperture_diameter_m=0.05, freq_hz=HI_HZ)
    with pytest.raises(ValueError, match="must be positive"):
        feeds.conical_horn_feed(aperture_diameter_m=0.0, freq_hz=HI_HZ)
