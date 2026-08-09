"""Tests for N1: amplifier stability.

The anchor is Pozar's Example 12.1 (HP HFET-102 at 2 GHz), but the *verification* is
stronger than a textbook comparison: unconditional stability has a definition — ``|Γin| < 1``
for every passive load and ``|Γout| < 1`` for every passive source — and that definition is
checkable by brute force. K, μ, and the sweep are three independent routes to one answer, and
these tests make them agree.

One caution is itself pinned as a test: **a brute-force sweep of the Smith chart can miss a
small unstable region entirely.** That is not a hypothetical — it happened while writing
these tests, and it is the reason the closed-form circles are worth having.
"""

from __future__ import annotations

import cmath
import math

import numpy as np
import pytest

from jansky_forge import stability as st
from jansky_forge import twoport as tp


def polar(magnitude: float, degrees: float) -> complex:
    return cmath.rect(magnitude, math.radians(degrees))


#: Pozar, *Microwave Engineering*, Example 12.1 — HP HFET-102 GaAs FET at 2 GHz.
#: Published: K = 0.607, |Δ| = 0.696; source circle C = 1.132∠68.5°, R = 0.199;
#: load circle C = 1.361∠47.0°, R = 0.50.
HFET_102 = np.array(
    [
        [polar(0.894, -60.6), polar(0.020, 62.4)],
        [polar(3.122, 123.6), polar(0.781, -27.6)],
    ]
)

#: An unconditionally stable device, for the cases the HFET cannot exercise.
STABLE_DEVICE = np.array([[0.3 + 0j, 0.02 + 0j], [4.0 + 0j, 0.2 + 0j]])


def max_reflection_over_passive(s: np.ndarray, port: str, points: int = 400) -> float:
    """Brute force: the largest |Γin| (or |Γout|) any *passive* termination can produce.

    This is the definition of stability, evaluated rather than derived. Below 1 means no
    passive termination oscillates.
    """
    radii = np.linspace(0, 0.99999, points)
    angles = np.linspace(0, 2 * np.pi, points, endpoint=False)
    gamma = (radii[:, None] * np.exp(1j * angles[None, :])).ravel()
    feedback = s[0, 1] * s[1, 0]
    if port == "in":
        reflected = s[0, 0] + feedback * gamma / (1 - s[1, 1] * gamma)
    else:
        reflected = s[1, 1] + feedback * gamma / (1 - s[0, 0] * gamma)
    return float(np.max(np.abs(reflected)))


# --------------------------------------------------------------------------------------
# The textbook anchor
# --------------------------------------------------------------------------------------


def test_pozar_example_12_1_stability_factors():
    assert st.rollett_k(HFET_102) == pytest.approx(0.607, abs=0.001)
    assert abs(st.determinant(HFET_102)) == pytest.approx(0.696, abs=0.001)
    assert not st.is_unconditionally_stable(HFET_102)
    # K alone is not the criterion, and here both parts happen to point the same way.
    assert st.rollett_k(HFET_102) < 1
    assert abs(st.determinant(HFET_102)) < 1


def test_pozar_example_12_1_stability_circles():
    source = st.source_stability_circle(HFET_102)
    assert abs(source.center) == pytest.approx(1.132, abs=0.002)
    assert math.degrees(cmath.phase(source.center)) == pytest.approx(68.5, abs=0.2)
    assert source.radius == pytest.approx(0.199, abs=0.002)

    load = st.load_stability_circle(HFET_102)
    assert abs(load.center) == pytest.approx(1.361, abs=0.005)
    assert math.degrees(cmath.phase(load.center)) == pytest.approx(47.0, abs=0.4)
    assert load.radius == pytest.approx(0.50, abs=0.005)


def test_the_mu_factors_are_below_one_for_a_potentially_unstable_device():
    assert st.mu_load(HFET_102) < 1
    assert st.mu_source(HFET_102) < 1
    # μ is a distance: 0.86 means an unstable load exists at |Γ| = 0.86, inside the passive
    # region — which is exactly why this device's matches are not free choices.
    assert st.mu_load(HFET_102) == pytest.approx(0.863, abs=0.002)


# --------------------------------------------------------------------------------------
# Verification against the definition, not against another formula
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("plane", ["source", "load"])
def test_the_stability_circle_is_exactly_where_the_reflection_reaches_one(plane):
    """The defining property. Not "close to 1" — exactly 1, at every point on the circle."""
    circle = (
        st.source_stability_circle(HFET_102)
        if plane == "source"
        else st.load_stability_circle(HFET_102)
    )
    angles = np.linspace(0, 2 * np.pi, 500, endpoint=False)
    on_circle = circle.center + circle.radius * np.exp(1j * angles)
    feedback = HFET_102[0, 1] * HFET_102[1, 0]
    if plane == "load":
        reflected = HFET_102[0, 0] + feedback * on_circle / (1 - HFET_102[1, 1] * on_circle)
    else:
        reflected = HFET_102[1, 1] + feedback * on_circle / (1 - HFET_102[0, 0] * on_circle)
    assert np.allclose(np.abs(reflected), 1.0, atol=1e-12)


def test_all_three_criteria_agree_over_random_networks():
    """K/Δ, μ, and the brute-force definition are three independent routes to one answer.

    They are provably equivalent, so any disagreement is a bug. Random complex networks
    include plenty of unphysical ones, which is fine — the algebra does not care, and it
    exercises corners a catalogue of real transistors would not.
    """
    rng = np.random.default_rng(20260809)
    unconditional = 0
    for _ in range(300):
        s = rng.uniform(0, 1.4, (2, 2)) * np.exp(2j * np.pi * rng.uniform(0, 1, (2, 2)))
        by_definition = (
            max_reflection_over_passive(s, "in", 120) < 1
            and max_reflection_over_passive(s, "out", 120) < 1
        )
        by_classical = st.rollett_k(s) > 1 and abs(st.determinant(s)) < 1
        by_mu = st.mu_load(s) > 1
        assert by_classical == by_mu, f"K/Δ and μ disagree for {s}"
        # The sweep can only miss an unstable region, never invent one, so it may report
        # "stable" where the closed form correctly says otherwise. See the next test.
        if by_definition:
            assert by_classical or st.load_stability_circle(s).radius < 0.05
        unconditional += by_classical
    assert 50 < unconditional < 250, "the random sample should contain both kinds"


def test_a_smith_chart_sweep_can_step_straight_over_an_unstable_region():
    """The trap that justifies closed-form circles over sampling.

    A device can have an unstable region a few thousandths of a Smith chart across, sitting
    well inside the passive disk. A uniform 600 × 600 sweep — 360 000 points — walks right
    past it and reports the device safe. The circle finds it in closed form.
    """
    rng = np.random.default_rng(11)
    for _ in range(3000):
        s = rng.uniform(0, 1.4, (2, 2)) * np.exp(2j * np.pi * rng.uniform(0, 1, (2, 2)))
        try:
            circle = st.load_stability_circle(s)
        except ValueError:
            continue
        if circle.radius < 0.001 and abs(circle.center) < 1 and circle.stable_region == "outside":
            break
    else:  # pragma: no cover - the seed is fixed, so this is unreachable
        pytest.skip("no tiny-circle case in this sample")

    # The sweep says the device is safe...
    assert max_reflection_over_passive(s, "in", 600) < 1
    # ...but there are passive loads on that circle where |Γin| is exactly 1.
    angles = np.linspace(0, 2 * np.pi, 200, endpoint=False)
    on_circle = circle.center + circle.radius * np.exp(1j * angles)
    reflected = s[0, 0] + s[0, 1] * s[1, 0] * on_circle / (1 - s[1, 1] * on_circle)
    assert np.allclose(np.abs(reflected), 1.0, atol=1e-9)
    assert np.all(np.abs(on_circle) < 1)  # genuinely passive loads
    assert not circle.excludes_passive


def test_the_stable_side_of_the_circle_is_identified_correctly():
    """Which side is safe is not always the outside, and it is checked, not assumed."""
    rng = np.random.default_rng(4)
    checked = 0
    for _ in range(200):
        s = rng.uniform(0, 1.4, (2, 2)) * np.exp(2j * np.pi * rng.uniform(0, 1, (2, 2)))
        try:
            circle = st.load_stability_circle(s)
        except ValueError:
            continue
        for _ in range(10):
            gamma = complex(rng.uniform(0, 0.999) * np.exp(2j * np.pi * rng.uniform()))
            reflected = s[0, 0] + s[0, 1] * s[1, 0] * gamma / (1 - s[1, 1] * gamma)
            assert circle.is_stable(gamma) == (abs(reflected) < 1)
            checked += 1
    assert checked > 1000


def test_excludes_passive_matches_the_brute_force_answer_for_a_real_device():
    stable_circle = st.load_stability_circle(STABLE_DEVICE)
    assert stable_circle.excludes_passive
    assert max_reflection_over_passive(STABLE_DEVICE, "in") < 1

    unstable_circle = st.load_stability_circle(HFET_102)
    assert not unstable_circle.excludes_passive
    assert max_reflection_over_passive(HFET_102, "in") > 1


# --------------------------------------------------------------------------------------
# Gains
# --------------------------------------------------------------------------------------


def test_max_available_gain_does_not_exist_below_k_of_one():
    """Substituting MSG for MAG is how a K < 1 part gets quoted at a gain it cannot hold."""
    with pytest.raises(ValueError, match="not unconditionally stable"):
        st.max_available_gain_db(HFET_102)
    assert st.max_stable_gain_db(HFET_102) == pytest.approx(21.93, abs=0.01)


def test_max_available_gain_needs_both_halves_of_the_criterion():
    """K > 1 with |Δ| > 1 is not unconditional stability, and MAG does not exist there.

    The module's own docstring calls K-alone "the classic misuse"; the first version of this
    function then committed it, guarding on `k <= 1` only. For the device below there are
    passive loads driving |Γin| to 820, so the true supremum of gain is unbounded — and it
    returned a tidy −10.37 dB.
    """
    rng = np.random.default_rng(3)
    for _ in range(200_000):
        s = rng.uniform(0, 2.0, (2, 2)) * np.exp(2j * np.pi * rng.uniform(0, 1, (2, 2)))
        if st.rollett_k(s) > 1 and abs(st.determinant(s)) > 1:
            break
    else:  # pragma: no cover - fixed seed
        pytest.skip("no K>1, |Δ|>1 case in this sample")
    assert not st.is_unconditionally_stable(s)
    assert max_reflection_over_passive(s, "in") > 1  # passive loads really do oscillate
    with pytest.raises(ValueError, match=r"K > 1 alone is NOT enough"):
        st.max_available_gain_db(s)


def test_max_available_gain_survives_a_nearly_unilateral_device():
    """The subtractive form cancels catastrophically; the reciprocal form does not.

    MSG + 10·log10(K − √(K²−1)) is 5.8 dB high by K = 1.3e8 and underflows to log10(0) by
    K = 3.8e8. MSG − 10·log10(K + √(K²−1)) is exact at every K.
    """
    for s12 in (1e-8, 1e-9, 3e-10, 1e-10):
        s = np.array([[0.4 + 0j, s12 + 0j], [10.0 + 0j, 0.3 + 0j]])
        assert st.rollett_k(s) > 1e6
        assert st.max_available_gain_db(s) == pytest.approx(21.1668, abs=1e-3)


def test_max_available_gain_is_below_max_stable_gain():
    msg = st.max_stable_gain_db(STABLE_DEVICE)
    mag = st.max_available_gain_db(STABLE_DEVICE)
    assert mag < msg
    assert msg == pytest.approx(23.01, abs=0.01)
    assert mag == pytest.approx(12.68, abs=0.01)


def test_gain_limits_agree_with_scikit_rf():
    """An independent implementation, run in CI rather than skipped."""
    skrf = pytest.importorskip("skrf", reason="scikit-rf is an optional extra")
    network = skrf.Network(
        frequency=skrf.Frequency.from_f([2.0], unit="ghz"), s=HFET_102[None, ...], z0=50
    )
    assert float(network.stability[0]) == pytest.approx(st.rollett_k(HFET_102), rel=1e-9)
    theirs_db = 10 * math.log10(float(network.max_stable_gain[0]))
    assert theirs_db == pytest.approx(st.max_stable_gain_db(HFET_102), abs=1e-9)


# --------------------------------------------------------------------------------------
# Edge cases the algebra has to survive
# --------------------------------------------------------------------------------------


def test_a_unilateral_device_has_no_feedback_and_so_no_k():
    """S12 = 0 puts a zero in K's denominator. It is stable, not undefined."""
    unilateral = np.array([[0.4 + 0j, 0.0], [10.0 + 0j, 0.3 + 0j]])
    assert st.rollett_k(unilateral) == math.inf
    assert st.is_unconditionally_stable(unilateral)
    assert st.max_stable_gain_db(unilateral) == math.inf  # MSG genuinely diverges

    # MAG does NOT. It is the S12 -> 0 limit of MSG·(K − √(K²−1)), which is the unilateral
    # transducer gain with both ports conjugate-matched — a finite number. Saying infinity
    # would claim a unilateral amplifier can deliver unlimited power gain.
    unilateral_limit = abs(unilateral[1, 0]) ** 2 / (
        (1 - abs(unilateral[0, 0]) ** 2) * (1 - abs(unilateral[1, 1]) ** 2)
    )
    assert st.max_available_gain_db(unilateral) == pytest.approx(10 * math.log10(unilateral_limit))
    assert st.max_available_gain_db(unilateral) == pytest.approx(21.1668, abs=1e-3)

    # μ is NOT infinite here, and that is right: with no feedback the load still sees S22,
    # so the load stability circle degenerates to the single point 1/S22 at distance
    # 1/|S22| from the origin. Outside the unit disk exactly when the output is passive.
    assert st.mu_load(unilateral) == pytest.approx(1 / 0.3)
    assert st.load_stability_circle(unilateral).radius == pytest.approx(0.0, abs=1e-12)


def test_mu_only_goes_infinite_when_no_load_can_reach_the_input():
    """S22 = 0 with no feedback: nothing the load does changes Γin, so μ has no finite value."""
    isolated = np.array([[0.4 + 0j, 0.0], [10.0 + 0j, 0.0]])
    assert st.mu_load(isolated) == math.inf
    assert st.is_unconditionally_stable(isolated)


def test_mu_is_the_distance_to_the_load_stability_circle():
    """μ = |C_L| − R_L, exactly. The identity ties μ and the circles to each other.

    They are computed from different expressions, so if either is wrong they stop agreeing —
    a cross-check with no extra machinery, on every network tested.
    """
    rng = np.random.default_rng(99)
    checked = 0
    for _ in range(400):
        s = rng.uniform(0, 1.4, (2, 2)) * np.exp(2j * np.pi * rng.uniform(0, 1, (2, 2)))
        try:
            circle = st.load_stability_circle(s)
        except ValueError:
            continue
        # The identity holds in the form μ = |C| − R when the circle's denominator is
        # positive; the sign flips with it, which is what makes μ negative for a device
        # already unstable at Γ = 0.
        if abs(s[1, 1]) ** 2 - abs(st.determinant(s)) ** 2 <= 0:
            continue
        assert st.mu_load(s) == pytest.approx(abs(circle.center) - circle.radius, rel=1e-9)
        checked += 1
    assert checked > 100


def test_a_unilateral_device_with_an_active_port_is_not_stable():
    """|S11| > 1 is a negative-resistance input; no feedback path is needed to oscillate."""
    assert not st.is_unconditionally_stable(np.array([[1.2 + 0j, 0.0], [10.0 + 0j, 0.3 + 0j]]))


def test_a_degenerate_circle_says_so_rather_than_dividing_by_zero():
    """|S22| = |Δ| makes the boundary a straight line, which this API cannot express."""
    # S12·S21 = 0 with S11 = 0 gives Δ = 0 and S22 = 0: the denominator vanishes.
    degenerate = np.array([[0.0, 0.0], [2.0 + 0j, 0.0]])
    with pytest.raises(ValueError, match="degenerate"):
        st.load_stability_circle(degenerate)


def test_mu_goes_negative_for_a_device_that_is_unstable_when_matched():
    """|S11| > 1 makes μ negative — it cannot be a distance, and the sign says so."""
    active_input = np.array(
        [[polar(1.2, -60), polar(0.15, 70)], [polar(3.0, 120), polar(0.7, -30)]]
    )
    assert st.mu_load(active_input) < 0
    assert not st.is_unconditionally_stable(active_input)


# --------------------------------------------------------------------------------------
# The report, and the automatic check
# --------------------------------------------------------------------------------------

HFET_S2P = """! HP HFET-102 GaAs FET, Pozar Microwave Engineering Example 12.1
# HZ S MA R 50
1.9e9 0.894 -60.6  3.122 123.6  0.020 62.4  0.781 -27.6
2.0e9 0.894 -60.6  3.122 123.6  0.020 62.4  0.781 -27.6
2.1e9 0.894 -60.6  3.122 123.6  0.020 62.4  0.781 -27.6
"""

STABLE_S2P = """# HZ S RI R 50
1.3e9 0.3 0 4.0 0 0.02 0 0.2 0
1.4e9 0.3 0 4.0 0 0.02 0 0.2 0
"""


def test_the_report_finds_the_worst_frequency_not_just_the_design_one():
    """An amplifier marginal outside its band is a real hazard; the oscillation does not
    care that you were not using that frequency."""
    varying = tp.parse_touchstone_2port(
        "# HZ S RI R 50\n"
        "1.0e9 0.3 0 8.0 0 0.05 0 0.2 0\n"  # high gain, marginal
        "1.4e9 0.3 0 4.0 0 0.02 0 0.2 0\n"  # comfortable
    )
    report = st.analyse(varying)
    assert report.worst.freq_hz == 1.0e9
    assert report.worst.mu < st.analyse(varying).points[1].mu


def test_the_report_summarises_an_unstable_device_with_its_span():
    report = st.analyse(tp.parse_touchstone_2port(HFET_S2P))
    assert not report.is_unconditional
    assert len(report.unstable_points) == 3
    summary = report.summary()
    assert "POTENTIALLY UNSTABLE at 3 of 3" in summary
    assert "1900.000-2100.000 MHz" in summary
    assert any("does not mean the part is faulty" in note for note in report.notes)
    assert any("most dangerous below its intended band" in note for note in report.notes)


def test_the_report_summarises_a_stable_device_with_its_margin():
    report = st.analyse(tp.parse_touchstone_2port(STABLE_S2P))
    assert report.is_unconditional
    assert "unconditionally stable across all 2 points" in report.summary()
    assert "tightest margin" in report.summary()
    assert any("this file says nothing" in note for note in report.notes)


def test_reading_an_unstable_part_attaches_the_warning_automatically():
    """The N1 requirement: the check runs on any amplifier the tool touches.

    The same way realizability runs on any pyramidal horn — not on request, because the
    person who most needs the warning is the one who did not think to ask for it.
    """
    network = tp.parse_touchstone_2port(HFET_S2P)
    assert any("potentially unstable at 3 of 3 frequencies" in note for note in network.notes)
    assert any("stability circles" in note for note in network.notes)


def test_no_stability_noise_for_devices_that_do_not_need_it():
    passive = tp.attenuator(loss_db=3.0, freq_hz=np.linspace(1.3e9, 1.5e9, 5))
    assert st.stability_notes(passive) == ()
    assert not any("stability" in note for note in passive.notes)

    stable = tp.parse_touchstone_2port(STABLE_S2P)
    assert st.stability_notes(stable) == ()
    assert not any("stability" in note for note in stable.notes)


def test_stability_summary_lines_are_readable():
    point = st.analyse(tp.parse_touchstone_2port(HFET_S2P)).points[0]
    line = point.summary()
    assert "K =" in line and "|Δ| =" in line and "μ =" in line
    assert "POTENTIALLY UNSTABLE" in line
    assert point.margin == point.mu

    circle = st.load_stability_circle(HFET_102)
    assert "stable outside" in circle.summary()
    assert "cuts the Smith chart" in circle.summary()
    assert "excludes every passive" in st.load_stability_circle(STABLE_DEVICE).summary()


# --------------------------------------------------------------------------------------
# The review's findings, pinned. Each of these passed before the fix.
# --------------------------------------------------------------------------------------


def lossless_shunt(susceptance: complex, z0: float = 50.0) -> np.ndarray:
    """A lossless shunt reactance — no loss, no gain, and it changes |S21| a great deal."""
    normalized = susceptance * z0
    return np.array(
        [
            [-normalized / (2 + normalized), 2 / (2 + normalized)],
            [2 / (2 + normalized), -normalized / (2 + normalized)],
        ],
        dtype=complex,
    )


def test_a_filter_in_front_of_an_unstable_amplifier_does_not_hide_it():
    """The gate bug: `max|S21| > 1` is not the test for "does stability need checking".

    A lossless network ahead of an unstable amplifier leaves K, μ and the unstable loads
    *exactly* where they were, while pushing |S21| far below 1. Gating on gain skipped
    precisely the file — a filtered LNA module — most likely to be handed to this tool.
    """
    amplifier = tp.TwoPort(freq_hz=np.array([2e9]), s=HFET_102[None, ...])
    for susceptance in (-6j, -20j):
        filtered = tp.cascade(
            tp.TwoPort(freq_hz=np.array([2e9]), s=lossless_shunt(susceptance)[None, ...]),
            amplifier,
        )
        s = filtered.s[0]
        assert abs(s[1, 0]) < 1  # looks like a lossy passive part by |S21| alone
        assert st.rollett_k(s) == pytest.approx(st.rollett_k(HFET_102), rel=1e-9)
        assert st.mu_load(s) == pytest.approx(st.mu_load(HFET_102), rel=1e-9)
        assert not st.is_passive(s)
        assert st.stability_notes(filtered)  # the warning survives the filter


def test_activity_can_live_entirely_in_the_reflection_coefficients():
    """|S11| > 1 with |S21| < 1: a negative-resistance stage, and no gain to give it away."""
    s = np.array([[polar(1.6, -40), polar(0.1, 20)], [polar(0.5, 10), polar(0.3, -20)]])
    network = tp.TwoPort(freq_hz=np.array([2e9]), s=s[None, ...])
    assert abs(s[1, 0]) < 1
    assert not st.is_passive(s)
    assert st.mu_load(s) < 0
    assert st.stability_notes(network)


def test_is_passive_agrees_with_unconditional_stability_for_passive_networks():
    """σmax ≤ 1 means no termination can extract net power, so stability is automatic."""
    rng = np.random.default_rng(31)
    checked = 0
    for _ in range(2000):
        s = rng.uniform(0, 0.7, (2, 2)) * np.exp(2j * np.pi * rng.uniform(0, 1, (2, 2)))
        if not st.is_passive(s):
            continue
        assert st.is_unconditionally_stable(s)
        checked += 1
    assert checked > 100
    assert st.is_passive(tp.attenuator(loss_db=3.0, freq_hz=np.array([1.4e9])).s[0])
    assert not st.is_passive(HFET_102)


def test_delta_says_nothing_about_behaviour_at_the_reference_impedance():
    """A docstring claim that was false in both directions. |S11|, |S22| decide that."""
    # |Δ| < 1 yet unstable at Z0.
    unstable_at_z0 = np.array([[1.5 + 0j, 0.0], [5.0 + 0j, 0.1 + 0j]])
    assert abs(st.determinant(unstable_at_z0)) < 1
    assert abs(unstable_at_z0[0, 0]) > 1

    # |Δ| > 1 yet perfectly well behaved at Z0.
    stable_at_z0 = np.array([[0.0, 1.2 + 0j], [1.2 + 0j, 0.0]])
    assert abs(st.determinant(stable_at_z0)) > 1
    assert abs(stable_at_z0[0, 0]) == 0.0


def test_the_margin_is_the_tighter_of_the_two_planes():
    """μ′ is the smaller one about half the time, and the margin has to reflect that."""
    point = st.Stability(
        freq_hz=1e9, k=2.0, delta=0.1 + 0j, mu=3.0, mu_source=1.5, is_unconditional=True
    )
    assert point.margin == 1.5


def test_a_scattered_unstable_set_is_not_reported_as_a_band():
    """ "1.0-3.0 GHz" reads as contiguous; which frequencies are safe in between matters."""
    scattered = tp.parse_touchstone_2port(
        "# HZ S MA R 50\n"
        "1.0e9 0.894 -60.6  3.122 123.6  0.020 62.4  0.781 -27.6\n"  # unstable
        "2.0e9 0.300   0.0  4.000   0.0  0.020  0.0  0.200   0.0\n"  # stable
        "3.0e9 0.894 -60.6  3.122 123.6  0.020 62.4  0.781 -27.6\n"  # unstable
    )
    summary = st.analyse(scattered).summary()
    assert "not contiguous" in summary
    assert " and " in summary
