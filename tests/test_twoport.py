"""Tests for N0: two-port foundations.

Everything in the receiver track will be written in this vocabulary, so a mistake here would
propagate silently through all of it. The anchors are chosen to be **exactly** analysable
rather than approximately right:

* a matched attenuator has all three gains equal to −L dB, exactly;
* two in series sum in dB, exactly;
* every representation round-trips to machine precision;
* a passive network's noise temperature must agree with M4's independent implementation.

And one test exists purely to pin a file-format trap: two-port Touchstone is ordered
``S11 S21 S12 S22``, and reading it row-major transposes the device.
"""

from __future__ import annotations

import cmath
import math

import numpy as np
import pytest

from jansky_forge import twoport as tp

FREQ = np.linspace(1.3e9, 1.5e9, 21)
MID = 1.4e9


# --------------------------------------------------------------------------------------
# The anchor: a matched attenuator is exactly analysable
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("loss_db", [0.0, 1.0, 3.0, 10.0, 20.0])
def test_all_three_gains_equal_minus_the_loss(loss_db):
    """With both ports matched, transducer, available and operating gain collapse to |S21|².

    That collapse is the check that three quite different expressions are all implemented
    right — they agree only when they should.
    """
    s = tp.attenuator(loss_db=loss_db, freq_hz=FREQ).at(MID)
    for gain in (tp.transducer_gain(s), tp.available_gain(s), tp.operating_gain(s)):
        assert 10 * math.log10(gain) == pytest.approx(-loss_db, abs=1e-9)
    assert 20 * math.log10(abs(s[1, 0])) == pytest.approx(-loss_db, abs=1e-9)


def test_the_three_gains_differ_once_the_terminations_do():
    """They are the same number only in the matched case; conflating them is the usual error."""
    s = tp.ideal_amplifier(gain_db=15.0, freq_hz=FREQ).at(MID)
    gamma_s, gamma_l = 0.3 + 0.2j, -0.25 + 0.1j
    transducer = tp.transducer_gain(s, gamma_source=gamma_s, gamma_load=gamma_l)
    available = tp.available_gain(s, gamma_source=gamma_s)
    operating = tp.operating_gain(s, gamma_load=gamma_l)
    assert transducer != pytest.approx(available, rel=1e-3)
    assert transducer != pytest.approx(operating, rel=1e-3)
    # Transducer gain is never more than either bound.
    assert transducer <= available * (1 + 1e-9)
    assert transducer <= operating * (1 + 1e-9)


def test_cascaded_attenuators_sum_in_decibels():
    combined = tp.cascade(
        tp.attenuator(loss_db=3.0, freq_hz=FREQ), tp.attenuator(loss_db=2.0, freq_hz=FREQ)
    )
    assert 20 * math.log10(abs(combined.at(MID)[1, 0])) == pytest.approx(-5.0, abs=1e-9)
    # And the result knows it carries no noise information.
    assert combined.noise is None
    assert any("Friis" in note for note in combined.notes)


def test_cascade_refuses_mismatched_grids_and_impedances():
    """Silently interpolating one onto the other would hide loading the wrong file."""
    other_grid = tp.attenuator(loss_db=1.0, freq_hz=np.linspace(1.3e9, 1.5e9, 11))
    with pytest.raises(ValueError, match="different frequency grids"):
        tp.cascade(tp.attenuator(loss_db=1.0, freq_hz=FREQ), other_grid)
    other_z0 = tp.attenuator(loss_db=1.0, freq_hz=FREQ, z0_ohm=75.0)
    with pytest.raises(ValueError, match="reference impedances differ"):
        tp.cascade(tp.attenuator(loss_db=1.0, freq_hz=FREQ), other_z0)


# --------------------------------------------------------------------------------------
# Conversions
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("loss_db", [1.0, 6.0])
def test_every_representation_round_trips_to_machine_precision(loss_db):
    s = tp.attenuator(loss_db=loss_db, freq_hz=FREQ).at(MID)
    assert np.allclose(tp.abcd_to_s(tp.s_to_abcd(s)), s, atol=1e-12)
    assert np.allclose(tp.z_to_s(tp.s_to_z(s)), s, atol=1e-12)
    # Y is the inverse of Z, by construction.
    assert np.allclose(tp.s_to_y(s) @ tp.s_to_z(s), np.eye(2), atol=1e-10)


def test_a_matched_line_has_unit_magnitude_and_linear_phase():
    """A lossless line changes phase and nothing else — the classic reference plane check."""
    line = tp.transmission_line(length_m=0.5, freq_hz=FREQ, velocity_factor=0.66)
    s = line.at(MID)
    assert abs(s[1, 0]) == pytest.approx(1.0, abs=1e-12)
    assert line.is_reciprocal
    # Twice the length is twice the phase.
    longer = tp.transmission_line(length_m=1.0, freq_hz=FREQ, velocity_factor=0.66).at(MID)
    assert np.angle(longer[1, 0]) == pytest.approx(np.angle(s[1, 0] ** 2), abs=1e-9) or np.angle(
        longer[1, 0]
    ) == pytest.approx(np.angle(s[1, 0] ** 2) + 2 * math.pi, abs=1e-9)


def test_a_lossy_line_attenuates():
    lossy = tp.transmission_line(length_m=10.0, freq_hz=FREQ, loss_db_per_m=0.2)
    assert 20 * math.log10(abs(lossy.at(MID)[1, 0])) == pytest.approx(-2.0, abs=1e-9)
    with pytest.raises(ValueError, match="velocity factor"):
        tp.transmission_line(length_m=1.0, freq_hz=FREQ, velocity_factor=2.0)


def test_abcd_refuses_a_network_with_no_forward_transmission():
    s = np.array([[0.5, 0.0], [0.0, 0.5]], dtype=complex)
    with pytest.raises(ValueError, match="no forward transmission"):
        tp.s_to_abcd(s)


# --------------------------------------------------------------------------------------
# Reflection coefficients
# --------------------------------------------------------------------------------------


def test_reflection_coefficients_of_a_unilateral_device():
    """With S12 = 0 the ports decouple: Γin is S11 whatever the load does."""
    s = np.array([[0.4 + 0.1j, 0.0], [5.0, -0.3 + 0.2j]], dtype=complex)
    for load in (0j, 0.5 + 0.5j, -0.8j):
        assert tp.input_reflection(s, load) == pytest.approx(s[0, 0])
    for source in (0j, 0.5 + 0.5j):
        assert tp.output_reflection(s, source) == pytest.approx(s[1, 1])


def test_reverse_transmission_couples_the_ports():
    """S12 is exactly what makes the load visible at the input — and stability possible."""
    s = np.array([[0.4, 0.05], [5.0, -0.3]], dtype=complex)
    assert tp.input_reflection(s, 0.6 + 0j) != pytest.approx(s[0, 0])


# --------------------------------------------------------------------------------------
# Touchstone — including the ordering trap
# --------------------------------------------------------------------------------------

# S11 S21 S12 S22, in RI. Asymmetric on purpose so a transpose is detectable.
AMPLIFIER_S2P = """! An amplifier, written the way Touchstone writes two ports
! S11 S21 S12 S22 -- note S21 comes SECOND
# HZ S RI R 50
1.3e9 -0.20 0.10   9.00 1.00   0.010 0.002  -0.30 0.05
1.4e9 -0.18 0.08  10.00 0.50   0.012 0.001  -0.28 0.04
1.5e9 -0.16 0.06   9.50 0.20   0.014 0.000  -0.26 0.03
! noise data follows: freq Fmin(dB) |Gopt| ang(Gopt) Rn/Z0
1.3e9 0.30 0.45  40.0 0.20
1.4e9 0.32 0.44  45.0 0.21
1.5e9 0.35 0.43  50.0 0.22
"""


def test_touchstone_two_port_ordering_is_s11_s21_s12_s22():
    """THE trap this module exists to guard.

    Two-port Touchstone is the historical exception to row-major ordering. Reading it the
    obvious way transposes the device: for this amplifier that would report 0.012 as the
    gain and 10.0 as the isolation — a 60 dB error that still looks like a number.
    """
    network = tp.parse_touchstone_2port(AMPLIFIER_S2P)
    s = network.at(1.4e9)
    assert s[1, 0] == pytest.approx(complex(10.0, 0.5))  # S21, the gain
    assert s[0, 1] == pytest.approx(complex(0.012, 0.001))  # S12, the isolation
    assert abs(s[1, 0]) > 100 * abs(s[0, 1])  # gain vastly exceeds isolation, as it must
    assert not network.is_reciprocal


def test_a_transposed_read_would_be_caught_by_reciprocity():
    """An amplifier that reads reciprocal has almost certainly been read wrong."""
    network = tp.parse_touchstone_2port(AMPLIFIER_S2P)
    assert not network.is_reciprocal
    assert tp.attenuator(loss_db=3.0, freq_hz=FREQ).is_reciprocal


def test_noise_block_is_read_and_denormalized():
    network = tp.parse_touchstone_2port(AMPLIFIER_S2P)
    assert network.noise is not None
    assert network.noise.fmin_db[1] == pytest.approx(0.32)
    # Rn is given normalized to Z0 and must come back in ohms.
    assert network.noise.rn_ohm[1] == pytest.approx(0.21 * 50.0)
    assert abs(network.noise.gamma_opt[1]) == pytest.approx(0.44)
    assert np.degrees(np.angle(network.noise.gamma_opt[1])) == pytest.approx(45.0)


def test_noise_figure_returns_fmin_at_gamma_opt():
    """The defining property, and the check that the excess-noise term is right."""
    noise = tp.parse_touchstone_2port(AMPLIFIER_S2P).noise
    assert noise is not None
    opt = complex(noise.gamma_opt[1])
    assert noise.noise_figure_db(opt, 1.4e9) == pytest.approx(noise.fmin_db[1], abs=1e-9)
    # And it gets worse in every direction away from it — the fact N2 is built on.
    for offset in (0.1, -0.1, 0.1j, -0.15j):
        assert noise.noise_figure_db(opt + offset, 1.4e9) > noise.fmin_db[1]


def test_a_matched_source_is_not_the_best_noise_match():
    """Γs = 0 is a perfect *power* match and generally NOT the best noise match.

    This is the tradeoff the whole receiver track turns on, visible already at N0.
    """
    noise = tp.parse_touchstone_2port(AMPLIFIER_S2P).noise
    assert noise is not None
    assert noise.noise_figure_db(0j, 1.4e9) > noise.fmin_db[1]


def test_noise_figure_rejects_an_active_source():
    noise = tp.parse_touchstone_2port(AMPLIFIER_S2P).noise
    assert noise is not None
    with pytest.raises(ValueError, match=r"\|Γs\| must be below 1"):
        noise.noise_figure_db(1.2 + 0j, 1.4e9)


def test_touchstone_formats_and_units():
    ma = tp.parse_touchstone_2port("# GHZ S MA R 50\n1.4 0.5 90 2.0 0 0.01 0 0.3 180\n")
    assert ma.freq_hz[0] == pytest.approx(1.4e9)
    assert ma.s[0, 0, 0] == pytest.approx(complex(0, 0.5), abs=1e-9)
    assert ma.s[0, 1, 0] == pytest.approx(complex(2.0, 0), abs=1e-9)  # S21 second in the row
    db = tp.parse_touchstone_2port("# MHZ S DB R 75\n1400 -6.0206 0 6.0206 0 -40 0 -20 0\n")
    assert db.z0_ohm == 75.0
    assert abs(db.s[0, 0, 0]) == pytest.approx(0.5, abs=1e-4)
    assert abs(db.s[0, 1, 0]) == pytest.approx(2.0, abs=1e-3)


def test_reader_rejects_a_file_with_no_two_port_rows():
    with pytest.raises(ValueError, match="no two-port data rows"):
        tp.parse_touchstone_2port("# HZ S RI R 50\n! nothing but comments\n")


def test_reads_from_disk_and_records_provenance(tmp_path):
    path = tmp_path / "amp.s2p"
    path.write_text(AMPLIFIER_S2P)
    network = tp.read_touchstone_2port(path)
    assert str(path) in network.source
    assert any("Touchstone writes two ports" in note for note in network.notes)


def test_reader_agrees_with_scikit_rf():
    """Two independent readers of the same file. CI installs scikit-rf so this runs."""
    skrf = pytest.importorskip("skrf", reason="scikit-rf is an optional extra")
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "amp.s2p"
        path.write_text(AMPLIFIER_S2P)
        ours = tp.read_touchstone_2port(path)
        theirs = skrf.Network(str(path))
        assert np.allclose(ours.freq_hz, theirs.f)
        # The decisive comparison: S21 and S12 must land in the same places.
        assert np.allclose(ours.s, theirs.s, atol=1e-9)
        assert np.allclose(ours.s21, theirs.s[:, 1, 0], atol=1e-9)
        assert np.allclose(ours.s12, theirs.s[:, 0, 1], atol=1e-9)


# --------------------------------------------------------------------------------------
# Validation and accessors
# --------------------------------------------------------------------------------------


def test_twoport_rejects_malformed_data():
    with pytest.raises(ValueError, match=r"shape \(n, 2, 2\)"):
        tp.TwoPort(freq_hz=FREQ, s=np.zeros((21, 3, 3), dtype=complex))
    with pytest.raises(ValueError, match="same length"):
        tp.TwoPort(freq_hz=FREQ, s=np.zeros((5, 2, 2), dtype=complex))
    with pytest.raises(ValueError, match="describes nothing"):
        tp.TwoPort(freq_hz=np.array([]), s=np.zeros((0, 2, 2), dtype=complex))
    with pytest.raises(ValueError, match="reference impedance"):
        tp.TwoPort(freq_hz=FREQ, s=np.zeros((21, 2, 2), dtype=complex), z0_ohm=0.0)


def test_named_accessors_match_the_matrix_indices():
    network = tp.parse_touchstone_2port(AMPLIFIER_S2P)
    assert np.allclose(network.s11, network.s[:, 0, 0])
    assert np.allclose(network.s12, network.s[:, 0, 1])
    assert np.allclose(network.s21, network.s[:, 1, 0])
    assert np.allclose(network.s22, network.s[:, 1, 1])


def test_interpolation_refuses_to_extrapolate():
    network = tp.attenuator(loss_db=3.0, freq_hz=FREQ)
    with pytest.raises(ValueError, match="outside the swept range"):
        network.at(2.0e9)


def test_summary_says_whether_it_is_active():
    assert "reciprocal (passive)" in tp.attenuator(loss_db=3.0, freq_hz=FREQ).summary()
    assert "non-reciprocal (active)" in tp.ideal_amplifier(gain_db=20.0, freq_hz=FREQ).summary()


def test_attenuator_rejects_negative_loss():
    with pytest.raises(ValueError, match="cannot be negative"):
        tp.attenuator(loss_db=-3.0, freq_hz=FREQ)


# --------------------------------------------------------------------------------------
# The seam back to M4
# --------------------------------------------------------------------------------------


def test_a_passive_network_becomes_a_stage_whose_noise_matches_m4():
    """A passive network's noise temperature is its loss — and M4 must agree independently."""
    from jansky_forge.sensitivity import loss_to_temperature_k

    stage = tp.as_stage(tp.attenuator(loss_db=3.0, freq_hz=FREQ), MID)
    assert stage.gain_db == pytest.approx(-3.0, abs=1e-9)
    assert stage.noise_temp_k == pytest.approx(loss_to_temperature_k(3.0), rel=1e-9)


def test_a_two_port_chain_agrees_with_the_friis_cascade():
    """The N0-to-M4 seam, end to end.

    Two attenuators cascaded as S-parameters, then converted to a Stage, must give the same
    noise temperature as feeding both stages to Friis separately — two routes to one answer.
    """
    from jansky_forge.sensitivity import cascade_noise_temperature_k

    first, second = 1.0, 2.0
    combined_stage = tp.as_stage(
        tp.cascade(
            tp.attenuator(loss_db=first, freq_hz=FREQ), tp.attenuator(loss_db=second, freq_hz=FREQ)
        ),
        MID,
    )
    separate = cascade_noise_temperature_k(
        [
            tp.as_stage(tp.attenuator(loss_db=first, freq_hz=FREQ), MID),
            tp.as_stage(tp.attenuator(loss_db=second, freq_hz=FREQ), MID),
        ]
    )
    assert combined_stage.noise_temp_k == pytest.approx(separate, rel=1e-9)


def test_an_amplifier_refuses_the_passive_noise_assumption():
    """Deriving noise from loss is right for a pad and catastrophically wrong for an amp."""
    amplifier = tp.ideal_amplifier(gain_db=20.0, freq_hz=FREQ)
    with pytest.raises(ValueError, match="not passive"):
        tp.as_stage(amplifier, MID)
    # Given its actual noise temperature, it becomes a Stage happily.
    stage = tp.as_stage(amplifier, MID, noise_temp_k=21.0, name="LNA")
    assert stage.gain_db == pytest.approx(20.0, abs=1e-9)
    assert stage.name == "LNA"


def test_the_receiver_seam_reproduces_the_masthead_lna_argument():
    """M4's headline result, rebuilt from two-ports: order dominates.

    The same components in a different order differ by hundreds of kelvin, and now that
    argument can be made from measured S-parameters rather than assumed numbers.
    """
    from jansky_forge.sensitivity import cascade_noise_temperature_k

    coax = tp.as_stage(tp.attenuator(loss_db=3.0, freq_hz=FREQ), MID, name="coax")
    lna = tp.as_stage(
        tp.ideal_amplifier(gain_db=30.0, freq_hz=FREQ), MID, noise_temp_k=21.0, name="LNA"
    )
    good = cascade_noise_temperature_k([lna, coax])
    bad = cascade_noise_temperature_k([coax, lna])
    assert bad > 5 * good
    assert good == pytest.approx(21.0, abs=1.0)


def test_matched_terminations_are_not_enough_for_the_gains_to_agree():
    """A correction to my own first draft, pinned so it cannot come back.

    With Γs = ΓL = 0 the three gains collapse to |S21|² only if the *device* is matched too.
    For a real amplifier they differ by exactly its own mismatch:

        G_T = |S21|²,  G_A = |S21|²/(1 − |S22|²),  G_P = |S21|²/(1 − |S11|²)

    The CLI said "these are equal because both terminations are matched", which is wrong and
    would have taught the reader the confusion this module exists to prevent.
    """
    s = tp.parse_touchstone_2port(AMPLIFIER_S2P).at(1.4e9)
    forward = abs(s[1, 0]) ** 2
    assert tp.transducer_gain(s) == pytest.approx(forward)
    assert tp.available_gain(s) == pytest.approx(forward / (1 - abs(s[1, 1]) ** 2))
    assert tp.operating_gain(s) == pytest.approx(forward / (1 - abs(s[0, 0]) ** 2))
    # A device matched at both ports is the case where they do agree.
    matched = tp.attenuator(loss_db=6.0, freq_hz=FREQ).at(MID)
    assert tp.transducer_gain(matched) == pytest.approx(tp.available_gain(matched))
    assert tp.transducer_gain(matched) == pytest.approx(tp.operating_gain(matched))


# --------------------------------------------------------------------------------------
# Fixes from the N0 review. Each of these passed before the fix, because every earlier
# anchor was a *matched* network -- the one case where the wrong formula is right.
# --------------------------------------------------------------------------------------


def series_resistor(ohms: float, z0: float = 50.0) -> tp.TwoPort:
    """A bare series resistor: passive, reciprocal, and badly mismatched.

    Exactly analysable from first principles with no S-parameters involved, which is what
    makes it the right anchor for a bug that hides behind a matched network.
    """
    s11 = ohms / (ohms + 2 * z0)
    s21 = 2 * z0 / (ohms + 2 * z0)
    s = np.array([[[s11, s21], [s21, s11]]], dtype=complex)
    return tp.TwoPort(freq_hz=np.array([1.4e9]), s=s, z0_ohm=z0)


def test_friis_wants_available_gain_not_s21_squared():
    """The N0 review's one real physics error, pinned.

    A passive network at 290 K has F = 1/G_A — the **available** loss, not the insertion
    loss. They agree only when the network is matched, and a measured `.s2p` never is.

    Thévenin check, no S-parameters: a series 200 Ω fed from 50 Ω leaves Voc unchanged and
    presents 250 Ω, so available gain is 50/250 = 1/5, F = 5, and Te = 4 × 290 = 1160 K.
    Taking |S21|² instead gives 1/9, F = 9, and 2320 K — a factor of two.
    """
    network = series_resistor(200.0)
    s = network.at(1.4e9)
    assert 20 * math.log10(abs(s[1, 0])) == pytest.approx(-9.542, abs=1e-3)  # insertion
    assert tp.available_gain(s) == pytest.approx(0.2)  # available: 50/250
    stage = tp.as_stage(network, 1.4e9)
    assert stage.gain_db == pytest.approx(-6.9897, abs=1e-3)
    assert stage.noise_temp_k == pytest.approx(1160.0, rel=1e-9)
    assert stage.noise_temp_k != pytest.approx(2320.0, rel=1e-3)


def test_the_matched_case_still_holds_which_is_why_this_hid():
    """For a matched pad the two definitions coincide, so the old anchor stayed green."""
    from jansky_forge.sensitivity import loss_to_temperature_k

    stage = tp.as_stage(tp.attenuator(loss_db=3.0, freq_hz=FREQ), MID)
    assert stage.gain_db == pytest.approx(-3.0, abs=1e-9)
    assert stage.noise_temp_k == pytest.approx(loss_to_temperature_k(3.0), rel=1e-9)


def test_as_stage_gain_depends_on_the_source_match_and_says_so():
    """Available gain is a function of Γs, so `as_stage` is too. Not a hidden default."""
    network = series_resistor(200.0)
    matched = tp.as_stage(network, 1.4e9)
    mismatched = tp.as_stage(network, 1.4e9, gamma_source=0.5 + 0j)
    assert mismatched.gain_db != pytest.approx(matched.gain_db, abs=1e-3)


def test_an_active_network_is_judged_on_available_gain_too():
    """An amplifier with a mismatched output has more available gain than |S21|²."""
    s = np.array([[[0.0, 0.0], [10.0, 0.5]]], dtype=complex)
    amp = tp.TwoPort(freq_hz=np.array([1.4e9]), s=s)
    stage = tp.as_stage(amp, 1.4e9, noise_temp_k=30.0)
    assert stage.gain_db == pytest.approx(10 * math.log10(100 / (1 - 0.25)), abs=1e-9)
    assert stage.gain_db == pytest.approx(21.249, abs=1e-3)  # not 20.000


def test_noise_parameters_carry_their_own_reference_impedance():
    """Touchstone stores Rn normalized to the file's Z0, so the Z0 must travel with it."""
    seventy_five = AMPLIFIER_S2P.replace("# HZ S RI R 50", "# HZ S RI R 75")
    network = tp.parse_touchstone_2port(seventy_five)
    assert network.noise is not None
    assert network.noise.z0_ohm == 75.0
    assert network.noise.rn_ohm[1] == pytest.approx(0.21 * 75.0)
    # The documented call takes no z0 argument, and must still be right for a 75 ohm file.
    assert network.noise.noise_figure_db(0.2 + 0.3j, 1.4e9) == pytest.approx(0.34667, abs=1e-4)


def test_noise_figure_refuses_to_extrapolate():
    """np.interp clamps; a clamped value is a plausible number for an unmeasured band."""
    noise = tp.parse_touchstone_2port(AMPLIFIER_S2P).noise
    assert noise is not None
    with pytest.raises(ValueError, match="outside the noise data's range"):
        noise.noise_figure_db(0j, 10e9)
    with pytest.raises(ValueError, match="outside the noise data's range"):
        noise.noise_figure_db(0j, 1.0)


def test_noise_parameters_reject_an_unphysical_gamma_opt():
    with pytest.raises(ValueError, match=r"\|Γopt\| must be below 1"):
        tp.NoiseParameters(
            freq_hz=np.array([1.4e9]),
            fmin_db=np.array([0.3]),
            gamma_opt=np.array([-1.0 + 0j]),  # makes |1 + Γopt|² = 0
            rn_ohm=np.array([10.0]),
        )


def test_an_oscillating_network_raises_instead_of_returning_negative_power():
    """A potentially unstable device driven past |Γ| = 1 is oscillating, not amplifying.

    The old code returned a *negative* power ratio, which the CLI then fed to log10.
    """
    # K < 1 transistor: |S11| and |S22| large, S12 non-negligible.
    s = np.array(
        [
            [cmath.rect(0.8, math.radians(-60)), cmath.rect(0.15, math.radians(70))],
            [cmath.rect(3.0, math.radians(120)), cmath.rect(0.7, math.radians(-30))],
        ],
        dtype=complex,
    )
    with pytest.raises(ValueError, match=r"\|Γout\| = 2\.\d+, so this port returns more"):
        tp.available_gain(s, gamma_source=0.378 + 0.872j)
    with pytest.raises(ValueError, match=r"\|Γin\| = 1\.\d+, so this port returns more"):
        tp.operating_gain(s, gamma_load=0.75 + 0.4j)
    # And it is perfectly well behaved at a source match that does not provoke it.
    assert tp.available_gain(s, gamma_source=0j) > 0


def test_the_instability_message_does_not_accuse_a_cable_of_oscillating():
    """A measured passive part can read |S22| just over 1 from calibration overshoot.

    Telling someone their cable is oscillating would send them hunting a fault that is in
    the calibration, so the message offers both readings.
    """
    s = np.array([[0.2, 0.9], [0.9, 1.0001]], dtype=complex)
    with pytest.raises(ValueError, match="calibration overshoot"):
        tp.available_gain(s)


def test_the_gains_reject_a_termination_no_passive_source_could_present():
    s = tp.attenuator(loss_db=3.0, freq_hz=FREQ).at(MID)
    with pytest.raises(ValueError, match=r"\|Γs\| = 1\.500"):
        tp.available_gain(s, gamma_source=1.5 + 0j)
    with pytest.raises(ValueError, match=r"\|ΓL\| = 1\.000"):
        tp.operating_gain(s, gamma_load=1.0 + 0j)


def test_s_to_y_handles_a_network_whose_z_matrix_does_not_exist():
    """A bare series impedance has a Y matrix and **no** Z matrix.

    Its ports carry I1 = −I2, so Z is singular — while Y = [[1/Z, −1/Z], [−1/Z, 1/Z]] is
    perfectly well defined. Computing Y as `inv(s_to_z(...))` therefore fails on a network
    whose answer exists, and usually fails *quietly*. The direct form does not.

    (The review that found this named a *shunt* element; it is the other way round. A shunt
    element is the case with a Z matrix and no Y. The bug and the fix are unaffected.)
    """
    z0, series_ohms = 50.0, 200.0
    normalized = series_ohms / z0
    s11 = normalized / (normalized + 2)
    s21 = 2 / (normalized + 2)
    s = np.array([[s11, s21], [s21, s11]], dtype=complex)

    y = tp.s_to_y(s, z0)
    assert y[0, 0] == pytest.approx(1 / series_ohms, rel=1e-9)
    assert y[0, 1] == pytest.approx(-1 / series_ohms, rel=1e-9)

    # The Z matrix does not exist. Asserting LinAlgError here would pin a floating-point
    # accident: it raises only at the one ratio where I − S is *exactly* singular. The
    # robust statement is that Z is singular to working precision.
    assert np.linalg.cond(tp.s_to_z(s, z0)) > 1e12

    # And the real reason the old route was dangerous: it mostly did not raise at all, it
    # returned a plausible wrong number. 0.003906 S where the truth is 0.005 S, a 21.9%
    # error, because an ill-conditioned matrix inverts to something that looks fine.
    silently_wrong = np.linalg.inv(tp.s_to_z(s, z0))[0, 0]
    assert abs(silently_wrong) == pytest.approx(0.003906, abs=1e-5)
    assert abs(abs(silently_wrong) / (1 / series_ohms) - 1) > 0.2


def test_the_reader_refuses_other_port_counts_and_parameter_types():
    """A 19-number row is a 3-port file; truncating it to four terms is not a read."""
    three_port = "# HZ S RI R 50\n1.4e9 " + " ".join(["0.1"] * 18) + "\n"
    with pytest.raises(ValueError, match="no two-port data rows"):
        tp.parse_touchstone_2port(three_port)
    with pytest.raises(ValueError, match="Y-parameters, not S-parameters"):
        tp.parse_touchstone_2port("# HZ Y RI R 50\n1.4e9 0 0 1 0 1 0 0 0\n")


def test_is_reciprocal_survives_measured_data():
    """A real cable's S12 and S21 never agree to nine decimals."""
    pad = tp.attenuator(loss_db=3.0, freq_hz=FREQ)
    noisy = pad.s.copy()
    noisy[:, 0, 1] += 1e-3  # VNA-scale disagreement between the two directions
    measured = tp.TwoPort(freq_hz=FREQ, s=noisy)
    assert measured.is_reciprocal
    assert "reciprocal (passive)" in measured.summary()
    # It still catches an actual transpose, which is the point of the check.
    assert not tp.ideal_amplifier(gain_db=20.0, freq_hz=FREQ).is_reciprocal


# --------------------------------------------------------------------------------------
# Fixes from the second review pass, on the first pass's fixes
# --------------------------------------------------------------------------------------


def ideal_transformer(ratio: float, z0: float = 50.0) -> tp.TwoPort:
    """A lossless, passive, badly-mismatched network: G_A is exactly 1."""
    s11 = (ratio**2 - 1) / (ratio**2 + 1)
    s21 = 2 * ratio / (ratio**2 + 1)
    s = np.array([[[s11, s21], [s21, -s11]]], dtype=complex)
    return tp.TwoPort(freq_hz=np.array([1.4e9]), s=s, z0_ohm=z0)


def test_a_lossless_matching_network_is_not_mistaken_for_an_amplifier():
    """A regression introduced by the available-gain fix, caught by the second pass.

    G_A of a lossless network is 1, but computing it through |S21|²/(1 − |S22|²) is a
    cancellation that lands a few ulp either side. With a bare `gain_db > 0` test, whether
    an ideal matching network was called "an amplifier" came down to the last bit — and an
    ideal matching network is exactly what an antenna tool puts in a Friis chain.
    """
    for ratio in (2.0, 5.0, 0.5):
        stage = tp.as_stage(ideal_transformer(ratio), 1.4e9)
        assert stage.gain_db == pytest.approx(0.0, abs=1e-6)
        assert stage.noise_temp_k == pytest.approx(0.0, abs=1e-6)
    # A network with real gain is still rejected.
    with pytest.raises(ValueError, match="not passive"):
        tp.as_stage(tp.ideal_amplifier(gain_db=1.0, freq_hz=FREQ), MID)


def test_as_stages_threads_the_source_match_and_the_default_does_not():
    """The flattering error: evaluating every stage at Γs = 0 under-reports Tsys.

    Available gain composes multiplicatively only when each stage is evaluated at the source
    it actually sees. A reactive interstage mismatch breaks that, in the optimistic
    direction — the tool reports a *lower* system temperature than the truth.
    """
    from jansky_forge.sensitivity import cascade_noise_temperature_k

    first = ideal_transformer(1.5)  # lossless, but leaves a mismatched output
    second = series_resistor(200.0)  # lossy and mismatched
    exact = tp.as_stage(tp.cascade(first, second), 1.4e9).noise_temp_k

    threaded = cascade_noise_temperature_k(tp.as_stages([first, second], 1.4e9))
    naive = cascade_noise_temperature_k([tp.as_stage(first, 1.4e9), tp.as_stage(second, 1.4e9)])

    assert threaded == pytest.approx(exact, rel=1e-9)
    assert naive < exact  # optimistic, which is the dangerous direction
    assert naive == pytest.approx(1160.0, rel=1e-6)
    assert exact > 1700.0


def test_as_stages_accepts_noise_temperatures_and_names():
    amp = tp.ideal_amplifier(gain_db=30.0, freq_hz=FREQ)
    pad = tp.attenuator(loss_db=3.0, freq_hz=FREQ)
    stages = tp.as_stages([(amp, 21.0), (pad, None)], MID, names=("LNA", "coax"))
    assert [s.name for s in stages] == ["LNA", "coax"]
    assert stages[0].noise_temp_k == 21.0
    assert stages[1].gain_db == pytest.approx(-3.0, abs=1e-9)


def test_an_active_stage_takes_its_noise_from_the_file_when_it_has_one():
    """Fmin is only reached at Γopt. Pinning one datasheet number ignores the source match.

    A vendor's noise block makes the honest number computable, so `as_stage` computes it
    rather than demanding a hand-supplied constant.
    """
    amp = tp.parse_touchstone_2port(AMPLIFIER_S2P)
    assert amp.noise is not None
    matched = tp.as_stage(amp, 1.4e9)
    at_opt = tp.as_stage(amp, 1.4e9, gamma_source=complex(amp.noise.gamma_opt[1]))
    assert at_opt.noise_temp_k < matched.noise_temp_k  # Γopt is the best noise match
    assert matched.noise_temp_k == pytest.approx(48.1, abs=0.5)
    assert at_opt.noise_temp_k == pytest.approx(22.2, abs=0.5)
    # An explicit value still wins over the file.
    assert tp.as_stage(amp, 1.4e9, noise_temp_k=5.0).noise_temp_k == 5.0


def test_an_active_network_without_noise_data_still_refuses_to_guess():
    with pytest.raises(ValueError, match="not passive"):
        tp.as_stage(tp.ideal_amplifier(gain_db=20.0, freq_hz=FREQ), MID)
