"""Tests for M4: system temperature, sensitivity, and the radiometer equation.

External anchors, per honesty invariant 7:

* :func:`sensitivity_k_per_jy` must reproduce the **BHARAT paper's published 1.47e-4 K/Jy**
  from its published effective area alone;
* the sky model must land on the standard **3.4 K cold sky** at L band;
* the radiometer equation must agree with the sibling ``jansky`` course's independent
  implementation (this runs for real in CI, which checks the course out).
"""

from __future__ import annotations

import math

import pytest

from jansky_forge import sensitivity as sens
from jansky_forge.apertures import ParabolicDish
from jansky_forge.feeds import CosQFeed, spillover_efficiency

HI_HZ = 1_420_405_751.768


# --------------------------------------------------------------------------------------
# The anchors
# --------------------------------------------------------------------------------------


def test_sensitivity_reproduces_the_bharat_papers_published_value():
    """BHARAT publishes A_e = 0.407 m^2 AND 1.47e-4 K/Jy. We get the second from the first."""
    assert sens.sensitivity_k_per_jy(0.407) == pytest.approx(1.47e-4, rel=0.01)


def test_cold_sky_matches_the_standard_l_band_figure():
    """CMB + galactic away from the plane is the familiar ~3.4 K at 1.4 GHz."""
    assert sens.sky_temperature_k(HI_HZ, include_atmosphere=False) == pytest.approx(3.4, abs=0.1)
    # The atmosphere is a real extra couple of kelvin, and is separable on purpose.
    assert sens.sky_temperature_k(HI_HZ) > sens.sky_temperature_k(HI_HZ, include_atmosphere=False)


def test_galactic_synchrotron_falls_steeply_with_frequency():
    """~nu^-2.7 — which is why 21 cm is a far quieter band than the JOVE decametric one."""
    at_408 = sens.galactic_sky_temperature_k(408e6)
    assert at_408 == pytest.approx(sens.T_GALACTIC_408_MIN_K)
    assert sens.galactic_sky_temperature_k(HI_HZ) < 1.0
    assert sens.galactic_sky_temperature_k(20.1e6) > 1000.0  # Radio JOVE band is HOT
    with pytest.raises(ValueError):
        sens.galactic_sky_temperature_k(0.0)


def test_course_cross_check_radiometer_equation():
    """Our radiometer equation must equal the sibling course's independent implementation.

    Two implementations that nobody compares are two implementations that drift. CI checks
    the course out so this runs for real rather than skipping.
    """
    jansky_signals = pytest.importorskip(
        "jansky.signals", reason="the jansky course is not installed in this environment"
    )
    for tsys, bandwidth, tau, n_pol in (
        (100.0, 1e6, 60.0, 1),
        (45.0, 2.5e6, 3600.0, 2),
        (300.0, 1e4, 1.0, 1),
    ):
        assert sens.radiometer_sensitivity_k(tsys, bandwidth, tau, n_pol=n_pol) == pytest.approx(
            jansky_signals.radiometer_sensitivity(tsys, bandwidth, tau, n_pol=n_pol)
        )


def test_course_cross_check_noise_figure():
    jansky_observing = pytest.importorskip(
        "jansky.observing", reason="the jansky course is not installed in this environment"
    )
    for nf_db in (0.3, 1.0, 3.0, 6.0):
        assert sens.noise_figure_to_temperature_k(nf_db) == pytest.approx(
            jansky_observing.noise_figure_to_temperature(nf_db)
        )


# --------------------------------------------------------------------------------------
# Receiver chain
# --------------------------------------------------------------------------------------


def test_noise_figure_and_loss_conversions_of_known_values():
    # 0.3 dB -> 290*(10^0.03 - 1) = 290*0.0715 = 20.7 K
    assert sens.noise_figure_to_temperature_k(0.3) == pytest.approx(20.7, abs=0.2)
    # 3 dB -> 290*(2-1) = 290 K
    assert sens.noise_figure_to_temperature_k(3.0103) == pytest.approx(290.0, abs=0.5)
    assert sens.noise_figure_to_temperature_k(0.0) == pytest.approx(0.0)
    # A passive 3 dB loss at room temperature contributes the same 290 K.
    assert sens.loss_to_temperature_k(3.0103) == pytest.approx(290.0, abs=0.5)
    # A cold loss contributes less — the reason cryogenic front ends exist.
    assert sens.loss_to_temperature_k(3.0103, physical_k=20.0) == pytest.approx(20.0, abs=0.2)
    with pytest.raises(ValueError):
        sens.noise_figure_to_temperature_k(-1.0)
    with pytest.raises(ValueError):
        sens.loss_to_temperature_k(-1.0)


def test_friis_cascade_puts_the_first_stage_in_charge():
    """The headline consequence: loss BEFORE the LNA is ruinous, after it is nearly free."""
    lna = sens.Stage.amplifier("LNA", gain_db=30, noise_figure_db=0.3)
    coax = sens.Stage.loss("3 dB coax", loss_db=3.0)
    backend = sens.Stage.amplifier("SDR", gain_db=20, noise_figure_db=6.0)

    good = sens.cascade_noise_temperature_k([lna, coax, backend])
    bad = sens.cascade_noise_temperature_k([coax, lna, backend])
    assert bad > 5 * good
    assert good == pytest.approx(21.0, abs=2.0)  # essentially the LNA alone
    # And the backend's 6 dB noise figure is almost invisible behind 30 dB of gain.
    without_backend = sens.cascade_noise_temperature_k([lna, coax])
    assert good - without_backend < 2.0


def test_cascade_rejects_an_empty_chain():
    with pytest.raises(ValueError, match="at least one stage"):
        sens.cascade_noise_temperature_k([])


# --------------------------------------------------------------------------------------
# System temperature
# --------------------------------------------------------------------------------------


def test_spillover_turns_an_m3_feed_choice_into_kelvins():
    """The M3-to-M4 join: feed power that misses the dish sees ~290 K of ground."""
    tight = sens.system_temperature(freq_hz=HI_HZ, receiver_k=25.0, spillover_efficiency=0.95)
    leaky = sens.system_temperature(freq_hz=HI_HZ, receiver_k=25.0, spillover_efficiency=0.70)
    assert leaky.total_k > tight.total_k
    assert leaky.spillover_k == pytest.approx(0.30 * sens.T_GROUND_K)
    # A leaky feed makes spillover, not the receiver, the thing to fix — and it says so.
    assert leaky.dominant_term == "spillover (ground)"
    assert any("better-matched feed is worth more" in n for n in leaky.notes)
    assert any("sees warm ground" in n for n in leaky.notes)


def test_system_temperature_terms_sum_and_are_reported():
    ts = sens.system_temperature(
        freq_hz=HI_HZ, receiver_k=45.0, spillover_efficiency=0.92, other_k=3.0
    )
    assert ts.total_k == pytest.approx(ts.sky_k + ts.spillover_k + ts.receiver_k + ts.other_k)
    assert ts.dominant_term == "receiver"
    assert "Tsys" in ts.summary() and "dominated by" in ts.summary()
    # It never lets itself be mistaken for a measurement.
    assert any("not a measurement" in n for n in ts.notes)


@pytest.mark.parametrize(
    "kwargs",
    [
        dict(spillover_efficiency=0.0),
        dict(spillover_efficiency=1.5),
        dict(receiver_k=-1.0),
        dict(other_k=-1.0),
    ],
)
def test_system_temperature_rejects_impossible_inputs(kwargs):
    with pytest.raises(ValueError):
        sens.system_temperature(**({"freq_hz": HI_HZ, "receiver_k": 25.0} | kwargs))


# --------------------------------------------------------------------------------------
# Figures of merit
# --------------------------------------------------------------------------------------


def test_sefd_is_the_inverse_of_sensitivity_times_tsys():
    area, tsys = 0.3, 60.0
    assert sens.sefd_jy(tsys, area) == pytest.approx(tsys / sens.sensitivity_k_per_jy(area))
    # More area or less noise both lower SEFD, which is why it is the fair comparison.
    assert sens.sefd_jy(tsys, area * 2) < sens.sefd_jy(tsys, area)
    assert sens.sefd_jy(tsys / 2, area) < sens.sefd_jy(tsys, area)
    with pytest.raises(ValueError):
        sens.sefd_jy(0.0, area)


def test_g_over_t_is_gain_minus_tsys_in_db():
    assert sens.g_over_t_db(20.0, 100.0) == pytest.approx(0.0)
    assert sens.g_over_t_db(30.0, 100.0) == pytest.approx(10.0)
    with pytest.raises(ValueError):
        sens.g_over_t_db(20.0, 0.0)


def test_point_source_temperature_scales_with_collecting_area():
    small = sens.antenna_temperature_point_k(1000.0, 0.3)
    big = sens.antenna_temperature_point_k(1000.0, 3.0)
    assert big == pytest.approx(10 * small)
    with pytest.raises(ValueError):
        sens.antenna_temperature_point_k(-1.0, 0.3)


def test_extended_source_temperature_ignores_collecting_area_entirely():
    """The most important asymmetry in the module, and the easiest thing to get wrong.

    Galactic HI fills any amateur beam. A 0.9 m horn and a 30 m dish see the same line
    temperature; the big dish buys resolution, not signal.
    """
    assert sens.antenna_temperature_extended_k(100.0) == 100.0
    # Explicitly: no aperture appears in the call at all.
    for _area in (0.1, 1.0, 100.0):
        assert sens.antenna_temperature_extended_k(100.0) == 100.0
    # A source SMALLER than the beam is diluted by the filling factor.
    diluted = sens.antenna_temperature_extended_k(
        100.0, source_solid_angle_sr=0.01, beam_solid_angle_sr=0.1
    )
    assert diluted == pytest.approx(10.0)
    # Filling more than the beam cannot give more than the brightness temperature.
    assert sens.antenna_temperature_extended_k(
        100.0, source_solid_angle_sr=1.0, beam_solid_angle_sr=0.1
    ) == pytest.approx(100.0)
    with pytest.raises(ValueError):
        sens.antenna_temperature_extended_k(-1.0)


# --------------------------------------------------------------------------------------
# The radiometer equation
# --------------------------------------------------------------------------------------


def test_radiometer_sensitivity_of_a_hand_computed_case():
    # Tsys 100 K, B = 1 MHz, tau = 100 s -> 100/sqrt(1e8) = 0.01 K
    assert sens.radiometer_sensitivity_k(100.0, 1e6, 100.0) == pytest.approx(0.01)
    # Two polarizations gain sqrt(2).
    assert sens.radiometer_sensitivity_k(100.0, 1e6, 100.0, n_pol=2) == pytest.approx(
        0.01 / math.sqrt(2)
    )
    # Switching costs a factor of two, and that cost is visible rather than hidden.
    assert sens.radiometer_sensitivity_k(100.0, 1e6, 100.0, switched=True) == pytest.approx(0.02)


def test_sensitivity_improves_only_as_the_square_root_of_time():
    """Four times the integration for twice the sensitivity — why 'integrate longer' runs out."""
    one = sens.radiometer_sensitivity_k(100.0, 1e6, 100.0)
    hundred = sens.radiometer_sensitivity_k(100.0, 1e6, 10000.0)
    assert hundred == pytest.approx(one / 10.0)


def test_time_to_detect_inverts_the_radiometer_equation():
    tsys, bandwidth, signal = 60.0, 1e6, 0.05
    tau = sens.time_to_detect_s(
        signal_k=signal, tsys_k=tsys, bandwidth_hz=bandwidth, target_snr=5.0
    )
    assert sens.snr(signal, tsys, bandwidth, tau) == pytest.approx(5.0)
    # Halving the signal quadruples the time.
    tau_half = sens.time_to_detect_s(
        signal_k=signal / 2, tsys_k=tsys, bandwidth_hz=bandwidth, target_snr=5.0
    )
    assert tau_half == pytest.approx(4 * tau)


@pytest.mark.parametrize(
    "kwargs",
    [
        dict(signal_k=0.0),
        dict(tsys_k=0.0),
        dict(bandwidth_hz=0.0),
        dict(target_snr=0.0),
        dict(n_pol=0),
    ],
)
def test_time_to_detect_rejects_impossible_inputs(kwargs):
    base = dict(signal_k=0.1, tsys_k=60.0, bandwidth_hz=1e6, target_snr=5.0)
    with pytest.raises(ValueError):
        sens.time_to_detect_s(**(base | kwargs))


@pytest.mark.parametrize(
    ("tsys", "bandwidth", "tau", "n_pol"),
    [
        (0.0, 1e6, 10.0, 1),
        (100.0, 0.0, 10.0, 1),
        (100.0, 1e6, 0.0, 1),
        (100.0, 1e6, 10.0, 0),
    ],
)
def test_radiometer_rejects_impossible_inputs(tsys, bandwidth, tau, n_pol):
    with pytest.raises(ValueError):
        sens.radiometer_sensitivity_k(tsys, bandwidth, tau, n_pol=n_pol)


# --------------------------------------------------------------------------------------
# Solving backwards
# --------------------------------------------------------------------------------------


def test_required_diameter_round_trips_through_the_forward_calculation():
    """Ask for the dish that detects a source, then check that dish detects it."""
    flux, tsys, bandwidth, tau = 100.0, 60.0, 1e6, 60.0
    diameter = sens.required_diameter_m(
        flux_jy=flux,
        tsys_k=tsys,
        bandwidth_hz=bandwidth,
        integration_s=tau,
        aperture_efficiency=0.6,
        target_snr=5.0,
    )
    area = 0.6 * math.pi * (diameter / 2) ** 2
    signal = sens.antenna_temperature_point_k(flux, area)
    assert sens.snr(signal, tsys, bandwidth, tau) == pytest.approx(5.0, rel=1e-6)


def test_a_brighter_source_needs_a_smaller_dish():
    common = dict(tsys_k=60.0, bandwidth_hz=1e6, integration_s=60.0)
    assert sens.required_diameter_m(flux_jy=1000.0, **common) < sens.required_diameter_m(
        flux_jy=100.0, **common
    )
    with pytest.raises(ValueError):
        sens.required_diameter_m(flux_jy=0.0, **common)
    with pytest.raises(ValueError):
        sens.required_diameter_m(flux_jy=100.0, aperture_efficiency=0.0, **common)


# --------------------------------------------------------------------------------------
# Detection estimates
# --------------------------------------------------------------------------------------


def _point(flux_jy: float = 1900.0) -> sens.RadioSource:
    return sens.RadioSource(
        slug="test-point",
        name="Test point source",
        flux_jy=flux_jy,
        reference_freq_hz=HI_HZ,
        source="synthetic, for tests",
    )


def _extended(brightness_k: float = 100.0) -> sens.RadioSource:
    return sens.RadioSource(
        slug="test-extended",
        name="Test extended emission",
        flux_jy=None,
        reference_freq_hz=HI_HZ,
        brightness_temp_k=brightness_k,
        source="synthetic, for tests",
    )


def test_detect_routes_extended_sources_to_the_right_formula():
    """Using the point-source formula on HI is the most flattering possible mistake."""
    small = sens.detect(
        _extended(), effective_area_m2=0.3, tsys_k=60.0, bandwidth_hz=1e6, integration_s=60.0
    )
    big = sens.detect(
        _extended(), effective_area_m2=30.0, tsys_k=60.0, bandwidth_hz=1e6, integration_s=60.0
    )
    assert small.signal_k == big.signal_k == 100.0
    assert any("does NOT improve with a bigger aperture" in n for n in small.notes)
    # And it refuses to let a huge thermal SNR read as a promise.
    assert any("baseline stability" in n for n in small.notes)


def test_detect_scales_point_sources_with_area_and_reports_snr():
    small = sens.detect(
        _point(), effective_area_m2=0.3, tsys_k=60.0, bandwidth_hz=1e6, integration_s=60.0
    )
    big = sens.detect(
        _point(), effective_area_m2=3.0, tsys_k=60.0, bandwidth_hz=1e6, integration_s=60.0
    )
    assert big.signal_k == pytest.approx(10 * small.signal_k)
    assert big.snr == pytest.approx(10 * small.snr)
    assert "SNR" in small.summary()
    assert small.time_to_snr5_s is not None and small.time_to_snr5_s > 0


def test_detect_warns_when_a_source_is_larger_than_the_beam():
    resolved = sens.RadioSource(
        slug="big",
        name="Something enormous",
        flux_jy=1000.0,
        reference_freq_hz=HI_HZ,
        angular_size_deg=40.0,
        source="synthetic",
    )
    estimate = sens.detect(
        resolved,
        effective_area_m2=0.3,
        tsys_k=60.0,
        bandwidth_hz=1e6,
        integration_s=60.0,
        beam_solid_angle_sr=math.radians(20.0) ** 2,
    )
    assert any("it is resolved" in n for n in estimate.notes)


def test_detect_carries_a_sources_own_caveats_through():
    declining = sens.RadioSource(
        slug="decliner",
        name="A fading source",
        flux_jy=1000.0,
        reference_freq_hz=HI_HZ,
        source="synthetic",
        caveats=("This source fades measurably from year to year.",),
    )
    estimate = sens.detect(
        declining, effective_area_m2=0.3, tsys_k=60.0, bandwidth_hz=1e6, integration_s=60.0
    )
    assert any("fades measurably" in n for n in estimate.notes)


# --------------------------------------------------------------------------------------
# End to end, across the whole package
# --------------------------------------------------------------------------------------


def test_a_dish_from_m0_a_feed_from_m3_and_a_budget_from_m4():
    """The chain the project exists to make possible, in one test."""
    feed = CosQFeed.from_beamwidth(108.0)
    dish = ParabolicDish(diameter_m=0.7, f_over_d=0.35, feed=feed)
    char = dish.characterize(HI_HZ)

    eta_spill = spillover_efficiency(feed, char.detail["subtended_half_angle_deg"])
    receiver = sens.cascade_noise_temperature_k(
        [
            sens.Stage.loss("pigtail", loss_db=0.2),
            sens.Stage.amplifier("LNA", gain_db=30, noise_figure_db=0.3),
            sens.Stage.amplifier("SDR", gain_db=20, noise_figure_db=6.0),
        ]
    )
    tsys = sens.system_temperature(
        freq_hz=HI_HZ, receiver_k=receiver, spillover_efficiency=eta_spill
    )

    # Plausible for a well-built small amateur station.
    assert 40.0 < tsys.total_k < 120.0
    sefd = sens.sefd_jy(tsys.total_k, char.effective_area_m2)
    assert 1e5 < sefd < 5e6  # a 0.7 m dish is not a research instrument, and says so
    assert sens.g_over_t_db(char.gain_dbi, tsys.total_k) < 10.0
