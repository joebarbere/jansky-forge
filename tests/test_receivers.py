"""Tests for N4: the parts catalogue and receiver selection.

Two kinds of test here, and the second kind is the point.

The first checks arithmetic — noise figure ↔ temperature round trips, Friis, the quantum
limit. The second checks **that the tool gives honest advice**, which is a testable property:
it must not rank an impossible upgrade above an achievable one, must not present a
manufacturer claim as a measurement, and must not let a catalogue entry become design data.
Those are assertions about judgement, and they are exactly the ones that rot silently.
"""

from __future__ import annotations

import math

import pytest

from jansky_forge import receivers as rx
from jansky_forge.sensitivity import noise_figure_to_temperature_k

HI_HZ = 1_420_405_751.768


# --------------------------------------------------------------------------------------
# Provenance: the catalogue's own rules, enforced mechanically
# --------------------------------------------------------------------------------------


def test_the_catalogue_audit_is_silent():
    """`make audit` must print nothing. Same bar as the antenna catalogue since M0."""
    assert list(rx.audit()) == []


def test_every_entry_carries_a_real_source_url():
    for entry in (*rx.amplifiers(), *rx.digitizers(), *rx.clocks()):
        assert entry.source_url.startswith("http"), entry.slug


def test_a_cryogenic_part_must_say_it_needs_cooling():
    """Comparing a 2 K part against a 60 K one is only honest if the dewar is visible."""
    cryo = rx.get_amplifier("cryo-inp-hemt")
    assert cryo.needs_cryogenics
    assert any(
        word in caveat.lower()
        for caveat in cryo.caveats
        for word in ("cryostat", "cryogenic", "dewar")
    )
    assert "needs 4 K cooling" in cryo.summary()


def test_the_audit_actually_fails_when_provenance_is_missing():
    """A guard that only ever passes is not a guard — N1's lesson, applied here."""
    original = dict(rx._AMPLIFIERS)
    try:
        rx._AMPLIFIERS["bogus"] = rx.Amplifier(
            slug="bogus",
            name="Undocumented cryo part",
            technology="unknown",
            noise_temp_k=3.0,
            gain_db=30.0,
            freq_min_hz=1e9,
            freq_max_hz=2e9,
            physical_temp_k=4.0,
            availability=rx.Availability.RESEARCH,
            claim=rx.Claim.LITERATURE,
            source_url="https://example.invalid/paper",
        )
        complaints = list(rx.audit())
        assert any("bogus" in complaint for complaint in complaints)
    finally:
        rx._AMPLIFIERS.clear()
        rx._AMPLIFIERS.update(original)
    assert list(rx.audit()) == []


def test_an_entry_without_a_source_is_refused_outright():
    with pytest.raises(ValueError, match="every entry needs a source URL"):
        rx.Amplifier(
            slug="x",
            name="x",
            technology="x",
            noise_temp_k=1.0,
            gain_db=1.0,
            freq_min_hz=1e9,
            freq_max_hz=2e9,
            availability=rx.Availability.AMATEUR,
            claim=rx.Claim.DATASHEET,
            source_url="",
        )


# --------------------------------------------------------------------------------------
# The numbers
# --------------------------------------------------------------------------------------


def test_the_quantum_limit_is_the_floor_nothing_reaches():
    assert rx.quantum_noise_limit_k(HI_HZ) == pytest.approx(0.0682, abs=1e-4)
    # Every catalogued part, including the best cryogenic one, sits well above it.
    for amplifier in rx.amplifiers():
        assert amplifier.times_quantum_limit(HI_HZ) > 1.0
    assert rx.get_amplifier("cryo-inp-hemt").times_quantum_limit(HI_HZ) == pytest.approx(32, abs=1)
    with pytest.raises(ValueError, match="frequency must be positive"):
        rx.quantum_noise_limit_k(0.0)


def test_noise_figure_and_temperature_cannot_drift_apart():
    """Noise figure is derived, never stored, so the two representations always agree."""
    for amplifier in rx.amplifiers():
        assert noise_figure_to_temperature_k(amplifier.noise_figure_db) == pytest.approx(
            amplifier.noise_temp_k, rel=1e-9
        )


def test_the_sourced_datasheet_figures_convert_as_published():
    """Cross-check the entries against the arithmetic on their published dB figures."""
    assert rx.get_amplifier("sawbird-h1").noise_figure_db == pytest.approx(0.8, abs=1e-9)
    assert rx.get_amplifier("sawbird-h1").noise_temp_k == pytest.approx(58.7, abs=0.1)
    assert rx.get_amplifier("qpl9547").noise_figure_db == pytest.approx(0.3, abs=1e-9)
    assert rx.get_amplifier("qpl9547").noise_temp_k == pytest.approx(20.7, abs=0.1)


def test_the_historical_axis_is_the_interesting_comparison():
    """A 1980 observatory front end beats a 2019 hobby module. That is the point."""
    hobby = rx.get_amplifier("sawbird-h1")
    observatory_1980 = rx.get_amplifier("nrao-1980-4.5ghz")
    assert observatory_1980.noise_temp_k < hobby.noise_temp_k
    assert observatory_1980.year == 1980
    # ...and two decades of HEMT work took the observatory from 25 K to 2 K.
    assert rx.get_amplifier("nrao-2003-4ghz").noise_temp_k == 2.0


def test_dynamic_range_is_the_axis_that_separates_digitizers():
    rtl = rx.get_digitizer("rtl-sdr-v4")
    airspy = rx.get_digitizer("airspy-r2")
    assert rtl.dynamic_range_db == pytest.approx(6.02 * 8 + 1.76)
    assert airspy.dynamic_range_db - rtl.dynamic_range_db == pytest.approx(24.08, abs=0.01)


def test_a_digitizer_without_a_published_noise_figure_refuses_to_guess():
    """The honest failure. A plausible guess in Tsys is an invented Tsys."""
    with pytest.raises(ValueError, match="a plausible guess in a Tsys number"):
        rx.get_digitizer("rtl-sdr-v4").as_stage()


def test_the_backend_stops_mattering_after_about_thirty_db():
    """Which is why arguing about SDR noise figures behind a 40 dB LNA is arguing about air."""
    threshold = rx.backend_matters_below_gain_db(6.0, 58.7)
    assert 25 < threshold < 32
    # A backend quieter than the tolerance never mattered at any gain. Note 0.05 dB is NOT
    # such a backend — it is still 3.4 K — which is its own reminder that dB near zero are
    # not "nearly nothing".
    assert rx.backend_matters_below_gain_db(0.05, 58.7) == pytest.approx(5.3, abs=0.1)
    assert rx.backend_matters_below_gain_db(0.01, 58.7) == -math.inf


# --------------------------------------------------------------------------------------
# Comparison
# --------------------------------------------------------------------------------------

ANTENNA = {
    "freq_hz": HI_HZ,
    "gain_dbi": 18.4,
    "effective_area_m2": 0.248,
    "spillover_efficiency": 0.926,
}


def test_comparison_ranks_by_system_temperature_not_by_noise_figure():
    ranked = rx.compare_amplifiers(rx.amplifiers(covering_hz=HI_HZ), **ANTENNA, pre_lna_loss_db=0.5)
    assert [c.amplifier.slug for c in ranked] == ["cryo-inp-hemt", "qpl9547", "sawbird-h1"]
    assert ranked[0].penalty_k == pytest.approx(0.0, abs=0.05)
    assert ranked[-1].penalty_k > 50
    # And the numbers are a system, not a part: SEFD and G/T come out too.
    assert ranked[0].sefd_jy > 0 and ranked[0].g_over_t_db > ranked[-1].g_over_t_db


def test_comparison_flags_a_figure_quoted_at_the_wrong_frequency():
    """The QPL9547's 0.3 dB is a 1.9 GHz number and must not pass silently as a 1.42 GHz one."""
    ranked = rx.compare_amplifiers([rx.get_amplifier("qpl9547")], **ANTENNA)
    assert any("quoted at 1900 MHz" in note for note in ranked[0].notes)
    assert any("not interpolated" in note for note in ranked[0].notes)


def test_comparison_flags_a_part_used_outside_its_range():
    outside = rx.compare_amplifiers([rx.get_amplifier("nrao-2003-4ghz")], **ANTENNA)
    assert any("is not specified at" in note for note in outside[0].notes)
    assert any("should not be trusted" in note for note in outside[0].notes)


def test_comparison_flags_the_dewar():
    ranked = rx.compare_amplifiers([rx.get_amplifier("cryo-inp-hemt")], **ANTENNA)
    assert any("the dewar is the project" in note for note in ranked[0].notes)


def test_comparison_needs_something_to_compare():
    with pytest.raises(ValueError, match="nothing to compare"):
        rx.compare_amplifiers([], **ANTENNA)


def test_loss_ahead_of_the_amplifier_can_erase_the_difference_between_parts():
    """The argument people leave at zero, and it dominates the one they agonise over."""
    clean = rx.compare_amplifiers(rx.amplifiers(covering_hz=HI_HZ), **ANTENNA, pre_lna_loss_db=0.0)
    lossy = rx.compare_amplifiers(rx.amplifiers(covering_hz=HI_HZ), **ANTENNA, pre_lna_loss_db=1.0)
    # 1 dB in front of the chain costs more than the gap between the two amateur parts.
    amateur_gap = clean[-1].tsys_k - clean[-2].tsys_k
    loss_cost = lossy[-1].tsys_k - clean[-1].tsys_k
    assert loss_cost > amateur_gap


# --------------------------------------------------------------------------------------
# Honest advice — the assertions that matter most, and that rot silently
# --------------------------------------------------------------------------------------


def test_advice_never_ranks_an_impossible_upgrade_above_an_achievable_one():
    """The bug this test exists to prevent, caught in this milestone's own first draft.

    The first version compared "a perfect 0 K amplifier" against "use better cable" and let
    the impossible option win. They are not the same kind of thing: one is a physical
    impossibility and the other is a Saturday afternoon. The verdict now ranks only actions.
    """
    advice = rx.would_a_better_lna_help(
        freq_hz=HI_HZ,
        amplifier=rx.get_amplifier("sawbird-h1"),
        spillover_efficiency=0.926,
        pre_lna_loss_db=0.5,
    )
    assert "removing the loss ahead of it" in advice.verdict
    # The impossible ceiling is still reported, but labelled as impossible.
    assert "impossible, not a target" in advice.summary()
    assert advice.best_possible_lna_gain_k > advice.achievable_lna_gain_k


def test_advice_names_the_part_you_could_actually_buy():
    advice = rx.would_a_better_lna_help(
        freq_hz=HI_HZ, amplifier=rx.get_amplifier("sawbird-h1"), spillover_efficiency=0.926
    )
    assert advice.best_available is not None
    assert advice.best_available.slug == "qpl9547"
    assert advice.best_available.availability is rx.Availability.AMATEUR
    assert advice.tsys_best_available_k < advice.tsys_now_k


def test_advice_stays_within_the_tier_you_are_shopping_in():
    """It must not answer "buy a cryostat" to someone holding a hobby module."""
    advice = rx.would_a_better_lna_help(
        freq_hz=HI_HZ, amplifier=rx.get_amplifier("sawbird-h1"), spillover_efficiency=0.926
    )
    assert advice.best_available is not None
    assert not advice.best_available.needs_cryogenics


def test_advice_says_stop_shopping_when_nothing_is_left_to_buy():
    advice = rx.would_a_better_lna_help(
        freq_hz=HI_HZ, amplifier=rx.get_amplifier("qpl9547"), spillover_efficiency=0.926
    )
    assert advice.best_available is None
    assert "Nothing purchasable" in advice.summary()
    assert "fixing spillover" in advice.verdict


def test_advice_tells_a_receiver_limited_system_to_stop_reading_datasheets():
    """When the receiver is under 10% of Tsys the honest answer is "not this"."""
    quiet = rx.Amplifier(
        slug="hypothetical",
        name="hypothetical near-perfect LNA",
        technology="test fixture",
        noise_temp_k=1.0,
        gain_db=30.0,
        freq_min_hz=1e9,
        freq_max_hz=2e9,
        availability=rx.Availability.RESEARCH,
        claim=rx.Claim.LITERATURE,
        source_url="https://example.org/none",
    )
    advice = rx.would_a_better_lna_help(
        freq_hz=HI_HZ, amplifier=quiet, spillover_efficiency=0.926, backend_gain_db=40.0
    )
    assert "Stop reading amplifier datasheets" in advice.verdict


def test_advice_always_states_the_quantum_limit():
    """So "better amplifiers exist" is put in proportion rather than left as a vibe."""
    advice = rx.would_a_better_lna_help(freq_hz=HI_HZ, amplifier=rx.get_amplifier("sawbird-h1"))
    assert any("quantum limit" in note for note in advice.notes)
    assert any("rarely the answer" in note for note in advice.notes)


# --------------------------------------------------------------------------------------
# Clocks: accuracy and stability answer different questions
# --------------------------------------------------------------------------------------


def test_a_clock_error_looks_exactly_like_radial_velocity():
    assert rx.velocity_error_km_s(1e-6) == pytest.approx(0.2998, abs=1e-3)


def test_an_ordinary_tcxo_is_good_enough_for_hydrogen_line_spectroscopy():
    """The unwelcome conclusion, and the reason this function exists.

    1 ppm at 1420 MHz is 300 m/s. Galactic HI linewidths are tens of km/s, so a GPSDO bought
    to fix a spectroscopy problem is a GPSDO bought to fix the wrong problem.
    """
    notes = rx.clock_verdict(rx.get_clock("tcxo"), freq_hz=HI_HZ)
    assert any("Comfortably enough for HI spectroscopy" in note for note in notes)
    assert any("299.8 m/s" in note for note in notes)


def test_the_same_tcxo_is_useless_for_coherent_work():
    """Stability, not accuracy — and the verdict must not let the two be confused."""
    notes = rx.clock_verdict(rx.get_clock("tcxo"), freq_hz=HI_HZ, integration_s=600)
    assert any("too much for *coherent* integration" in note for note in notes)
    assert any("answer different questions" in note for note in notes)

    maser = rx.clock_verdict(rx.get_clock("h-maser"), freq_hz=HI_HZ, integration_s=600)
    assert any("fine for *coherent* integration" in note for note in maser)
    assert any("professional, not something to buy for a rooftop" in note for note in maser)


def test_an_ocxo_beats_a_rubidium_in_the_short_term_and_loses_long():
    """The inversion that surprises people who assume "atomic" means better everywhere."""
    ocxo, rubidium = rx.get_clock("ocxo"), rx.get_clock("rubidium")
    assert ocxo.adev_1s < rubidium.adev_1s
    assert ocxo.adev_1000s > rubidium.adev_1000s


def test_a_gpsdo_is_an_ocxo_with_gps_accuracy_not_gps_stability():
    gpsdo, ocxo = rx.get_clock("gpsdo"), rx.get_clock("ocxo")
    assert gpsdo.adev_1s == ocxo.adev_1s  # short term is the oscillator's
    assert gpsdo.accuracy < ocxo.accuracy  # long term is GPS's
    assert any("needs sky view" in caveat for caveat in gpsdo.caveats)


# --------------------------------------------------------------------------------------
# The boundary invariant 2 draws
# --------------------------------------------------------------------------------------


def test_a_catalogue_entry_cannot_become_design_data():
    """No path from a headline figure to a TwoPort, and none should ever be added.

    A datasheet noise figure is a system-budget number. Fmin, Γopt, Rn and S-parameters are
    measurement-grade design data, and inventing them from a headline is precisely what
    honesty invariant 2 forbids.
    """
    amplifier = rx.get_amplifier("qpl9547")
    for forbidden in ("s_parameters", "as_twoport", "to_twoport", "noise_parameters", "gamma_opt"):
        assert not hasattr(amplifier, forbidden), (
            f"Amplifier.{forbidden} would turn a catalogue headline into design data"
        )
    # What it does offer is a Stage — a number in a budget, which is all it can honestly be.
    stage = amplifier.as_stage()
    assert stage.noise_temp_k == amplifier.noise_temp_k
    assert stage.gain_db == amplifier.gain_db


def test_every_figure_is_labelled_as_a_claim():
    for entry in (*rx.amplifiers(), *rx.digitizers(), *rx.clocks()):
        assert entry.claim in tuple(rx.Claim), entry.slug


def test_lookup_failures_name_the_alternatives():
    for getter in (rx.get_amplifier, rx.get_digitizer, rx.get_clock):
        with pytest.raises(KeyError, match="known:"):
            getter("not-a-real-part")


def test_filters_work_and_are_honest_about_emptiness():
    amateur = rx.amplifiers(availability=rx.Availability.AMATEUR)
    assert amateur and all(a.availability is rx.Availability.AMATEUR for a in amateur)
    assert rx.amplifiers(covering_hz=1.0) == []  # nothing covers 1 Hz, and it says so
    assert all(a.covers(HI_HZ) for a in rx.amplifiers(covering_hz=HI_HZ))


def test_amplifier_validation():
    common = {
        "slug": "x",
        "name": "x",
        "technology": "x",
        "gain_db": 1.0,
        "availability": rx.Availability.AMATEUR,
        "claim": rx.Claim.DATASHEET,
        "source_url": "https://example.org",
    }
    with pytest.raises(ValueError, match="cannot be negative"):
        rx.Amplifier(noise_temp_k=-1.0, freq_min_hz=1e9, freq_max_hz=2e9, **common)
    with pytest.raises(ValueError, match="range is inverted"):
        rx.Amplifier(noise_temp_k=1.0, freq_min_hz=2e9, freq_max_hz=1e9, **common)


def test_registering_a_duplicate_slug_is_refused():
    with pytest.raises(ValueError, match="duplicate catalogue slug"):
        rx._register(rx.get_amplifier("qpl9547"))
