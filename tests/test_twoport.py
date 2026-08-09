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
