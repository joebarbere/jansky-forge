"""Tests for M7: measurement ingest, and the invariant it makes structural.

The central assertion of this file is not a number. It is that
:class:`~jansky_forge.measure.Comparison` has **no field combining prediction and
measurement** — no corrected value, no blended estimate, no fitted efficiency. Honesty
invariant 5 stops being a slogan here and becomes something a test can check.

The Touchstone reader is cross-checked against ``scikit-rf`` where it is installed; CI
installs it so the check runs rather than skipping.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from jansky_forge import measure
from jansky_forge.units import wavelength_m

GRAVES_HZ = 143.05e6

# A minimal, hand-written .s1p of the kind a NanoVNA exports.
SAMPLE_S1P = """! Touchstone written by a NanoVNA
! Antenna under test: 2 m dipole
# MHZ S RI R 50
140.0 -0.30  0.25
143.0 -0.02  0.01
146.0  0.28 -0.22
"""


# --------------------------------------------------------------------------------------
# Touchstone
# --------------------------------------------------------------------------------------


def test_reads_a_nanovna_style_file_including_units_and_comments():
    sweep = measure.parse_touchstone(SAMPLE_S1P, source="bench.s1p")
    assert sweep.freq_hz.tolist() == [140e6, 143e6, 146e6]  # MHZ honoured
    assert sweep.z0_ohm == 50.0
    assert sweep.s11[1] == pytest.approx(complex(-0.02, 0.01))
    assert sweep.source == "bench.s1p"
    # Comments are kept: they are the only provenance many bench files carry.
    assert any("dipole" in note for note in sweep.notes)


@pytest.mark.parametrize(
    ("header", "row", "expected"),
    [
        ("# HZ S RI R 50", "1.0e8 0.5 -0.5", complex(0.5, -0.5)),
        ("# HZ S MA R 50", "1.0e8 0.5 90", complex(0.0, 0.5)),
        ("# HZ S DB R 50", "1.0e8 -6.0206 0", complex(0.5, 0.0)),
    ],
)
def test_all_three_data_formats(header, row, expected):
    """RI, MA and DB. Angles are in degrees in every format — getting that wrong rotates
    every point on the chart, which looks like a broken antenna rather than a broken reader."""
    sweep = measure.parse_touchstone(f"{header}\n{row}\n")
    assert sweep.s11[0] == pytest.approx(expected, abs=1e-4)


def test_default_frequency_unit_is_ghz_per_the_spec():
    sweep = measure.parse_touchstone("# S RI R 50\n1.5 0.1 0.0\n")
    assert sweep.freq_hz[0] == pytest.approx(1.5e9)


def test_reader_rejects_a_file_with_no_data():
    with pytest.raises(ValueError, match="no data rows"):
        measure.parse_touchstone("! only a comment\n")


def test_round_trip_through_touchstone_is_lossless_enough_to_trust():
    original = measure.parse_touchstone(SAMPLE_S1P)
    restored = measure.parse_touchstone(measure.write_touchstone(original))
    assert np.max(np.abs(restored.s11 - original.s11)) < 1e-9
    assert np.allclose(restored.freq_hz, original.freq_hz)


def test_written_files_say_whether_they_are_predictions():
    """Writing a prediction out as if it were bench data is exactly the confusion to avoid."""
    sweep = measure.sweep_from_impedance(
        np.array([1e8]), np.array([complex(70, -5)]), source="model"
    )
    text = measure.write_touchstone(sweep, comment="PREDICTION, not a measurement")
    assert "PREDICTION" in text
    assert "source: model" in text


def test_reads_from_disk_and_records_the_filename(tmp_path):
    path = tmp_path / "sweep.s1p"
    path.write_text(SAMPLE_S1P)
    sweep = measure.read_touchstone(path)
    assert str(path) in sweep.source


def test_touchstone_reader_agrees_with_scikit_rf():
    """Two independent readers of the same file. CI installs scikit-rf so this runs for real."""
    skrf = pytest.importorskip("skrf", reason="scikit-rf is an optional extra")
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "check.s1p"
        path.write_text(SAMPLE_S1P)
        ours = measure.read_touchstone(path)
        theirs = skrf.Network(str(path))
        assert np.allclose(ours.freq_hz, theirs.f)
        assert np.allclose(ours.s11, theirs.s.ravel(), atol=1e-9)
        # And the derived quantities agree too, which is the part users actually read.
        assert np.allclose(ours.swr, theirs.s_vswr.ravel(), rtol=1e-6)
        assert np.allclose(ours.impedance, theirs.z.ravel(), rtol=1e-6)


# --------------------------------------------------------------------------------------
# Derived quantities
# --------------------------------------------------------------------------------------


def test_impedance_swr_and_return_loss_of_known_reflections():
    freqs = np.array([1e8, 1e8 + 1, 1e8 + 2])
    sweep = measure.MeasuredSweep(freqs, np.array([0.0 + 0j, 1 / 3 + 0j, -1 / 3 + 0j]))
    # S11 = 0 is a perfect match: Z = Z0, SWR 1, infinite return loss.
    assert sweep.impedance[0] == pytest.approx(50.0)
    assert sweep.swr[0] == pytest.approx(1.0)
    assert math.isinf(sweep.return_loss_db[0])
    # S11 = 1/3 -> SWR 2, Z = 100 ohm.
    assert sweep.swr[1] == pytest.approx(2.0)
    assert sweep.impedance[1] == pytest.approx(100.0)
    # S11 = -1/3 -> SWR 2 as well, but Z = 25 ohm. SWR loses the sign; impedance keeps it.
    assert sweep.swr[2] == pytest.approx(2.0)
    assert sweep.impedance[2] == pytest.approx(25.0)
    assert sweep.return_loss_db[1] == pytest.approx(9.54, abs=0.01)


def test_sweep_validation_rejects_impossible_measurements():
    freqs = np.array([1e8, 2e8])
    with pytest.raises(ValueError, match="same length"):
        measure.MeasuredSweep(freqs, np.array([0j]))
    with pytest.raises(ValueError, match="empty sweep"):
        measure.MeasuredSweep(np.array([]), np.array([]))
    with pytest.raises(ValueError, match="must be positive"):
        measure.MeasuredSweep(np.array([0.0, 1e8]), np.array([0j, 0j]))
    # A passive antenna cannot reflect more than it receives.
    with pytest.raises(ValueError, match=r"\|S11\| exceeds 1"):
        measure.MeasuredSweep(freqs, np.array([1.5 + 0j, 0j]))


def test_interpolation_refuses_to_extrapolate():
    sweep = measure.parse_touchstone(SAMPLE_S1P)
    assert sweep.at(141.5e6) == pytest.approx((sweep.s11[0] + sweep.s11[1]) / 2, abs=1e-9)
    with pytest.raises(ValueError, match="outside the swept range"):
        sweep.at(200e6)


def test_bandwidth_and_resonance():
    freqs = np.linspace(140e6, 146e6, 61)
    # A synthetic resonance: reflection minimum at 143 MHz.
    s11 = 0.9 * (freqs - 143e6) / 3e6
    sweep = measure.MeasuredSweep(freqs, s11.astype(complex))
    assert sweep.resonance_hz() == pytest.approx(143e6, abs=0.1e6)
    span = sweep.bandwidth_hz(max_swr=2.0)
    assert span is not None and span[0] < 143e6 < span[1]
    # A sweep that never matches well reports None rather than inventing a bandwidth.
    bad = measure.MeasuredSweep(freqs, np.full(freqs.shape, 0.9 + 0j))
    assert bad.bandwidth_hz(max_swr=2.0) is None
    with pytest.raises(ValueError, match="must exceed 1"):
        sweep.bandwidth_hz(max_swr=1.0)


# --------------------------------------------------------------------------------------
# The reference plane
# --------------------------------------------------------------------------------------


def test_shifting_the_reference_plane_rotates_but_preserves_the_match():
    """Lossless cable moves the phase, not the magnitude — the classic VNA trap.

    An antenna seen through half a metre of coax has the same SWR and a completely different
    impedance, which is why a measurement can look wrong when it is merely displaced.
    """
    sweep = measure.parse_touchstone(SAMPLE_S1P)
    shifted = measure.shift_reference_plane(sweep, length_m=-0.5)
    assert np.allclose(np.abs(shifted.s11), np.abs(sweep.s11))  # SWR unchanged
    assert not np.allclose(shifted.s11, sweep.s11)  # impedance very much changed
    assert any("not new data" in note for note in shifted.notes)


def test_de_embedding_is_the_inverse_of_embedding():
    sweep = measure.parse_touchstone(SAMPLE_S1P)
    through_cable = measure.shift_reference_plane(sweep, length_m=-0.5)
    recovered = measure.shift_reference_plane(through_cable, length_m=0.5)
    assert np.allclose(recovered.s11, sweep.s11, atol=1e-9)


def test_reference_plane_rejects_an_impossible_velocity_factor():
    sweep = measure.parse_touchstone(SAMPLE_S1P)
    with pytest.raises(ValueError, match="velocity factor"):
        measure.shift_reference_plane(sweep, length_m=0.5, velocity_factor=1.5)


# --------------------------------------------------------------------------------------
# Cable, and the join back to M4
# --------------------------------------------------------------------------------------


def test_cable_loss_scales_as_the_square_root_of_frequency():
    """Conductor loss dominates, so four times the frequency is twice the loss."""
    common = dict(length_m=100.0, loss_db_per_100m=6.6, reference_freq_hz=1e9)
    at_1ghz = measure.cable_loss_db(freq_hz=1e9, **common)
    at_4ghz = measure.cable_loss_db(freq_hz=4e9, **common)
    assert at_1ghz == pytest.approx(6.6)
    assert at_4ghz == pytest.approx(2 * 6.6)
    # And it scales linearly with length.
    assert measure.cable_loss_db(
        freq_hz=1e9, length_m=50.0, loss_db_per_100m=6.6, reference_freq_hz=1e9
    ) == pytest.approx(3.3)
    with pytest.raises(ValueError):
        measure.cable_loss_db(
            freq_hz=0.0, length_m=1.0, loss_db_per_100m=6.6, reference_freq_hz=1e9
        )


def test_cable_loss_before_the_lna_costs_system_temperature():
    """The M7-to-M4 join, and the reason mast-head amplifiers exist."""
    before, why_before = measure.cable_noise_penalty_k(loss_db=3.0, before_lna=True)
    after, why_after = measure.cable_noise_penalty_k(loss_db=3.0, before_lna=False)
    assert before == pytest.approx(289.0, abs=5.0)  # ~290 K for 3 dB at room temperature
    assert after == 0.0
    assert "Move the amplifier to the antenna" in why_before
    assert "costs almost nothing in noise" in why_after


# --------------------------------------------------------------------------------------
# Matching
# --------------------------------------------------------------------------------------


def test_l_network_actually_matches_the_load_it_was_designed_for():
    """Build the network, apply it, and check the result really is 50 ohms.

    Verifying a matching network by re-deriving its own algebra proves nothing. This applies
    the components to the load and checks what a VNA would see.
    """
    load = complex(20.0, -25.0)
    freq = GRAVES_HZ
    match = measure.l_network_match(load_ohm=load, freq_hz=freq)
    # Series element in line with the load, then shunt across the pair.
    after_series = load + 1j * match.series_reactance_ohm
    shunt_admittance = 1 / (1j * match.shunt_reactance_ohm)
    total = 1 / (1 / after_series + shunt_admittance)
    assert total.real == pytest.approx(50.0, rel=0.02)
    assert total.imag == pytest.approx(0.0, abs=1.0)


def test_l_network_reports_its_q_and_warns_when_the_match_is_sharp():
    # 1 ohm into 50 gives Q = sqrt(49) = 7, comfortably over the threshold. (2 ohm gives
    # 4.90, which is *just* under it — a reminder that Q rises slowly as the load falls.)
    narrow = measure.l_network_match(load_ohm=complex(1.0, 0.0), freq_hz=GRAVES_HZ)
    assert any("high" in note and "sharp" in note for note in narrow.notes)
    gentle = measure.l_network_match(load_ohm=complex(35.0, 0.0), freq_hz=GRAVES_HZ)
    assert not any("sharp" in note for note in gentle.notes)
    assert all("only" in note or "ideal" in note or "sharp" in note for note in gentle.notes)


def test_l_network_component_values_are_physical():
    match = measure.l_network_match(load_ohm=complex(20.0, -25.0), freq_hz=GRAVES_HZ)
    series_kind, series_value = match.series
    shunt_kind, shunt_value = match.shunt
    assert series_value > 0 and shunt_value > 0
    assert {series_kind, shunt_kind} <= {"inductor", "capacitor"}
    assert "nH" in match.summary() or "pF" in match.summary()


def test_l_network_refuses_the_wrong_topology_and_impossible_loads():
    with pytest.raises(ValueError, match="below the source"):
        measure.l_network_match(load_ohm=complex(200.0, 0.0), freq_hz=GRAVES_HZ)
    with pytest.raises(ValueError, match="resistance must be positive"):
        measure.l_network_match(load_ohm=complex(-5.0, 0.0), freq_hz=GRAVES_HZ)


# --------------------------------------------------------------------------------------
# The invariant, made structural
# --------------------------------------------------------------------------------------


def test_comparison_has_no_field_that_merges_prediction_and_measurement():
    """The structural expression of honesty invariant 5.

    If someone later adds a `corrected_impedance` or a fitted efficiency that reconciles the
    two, this test fails — which is the point. A prediction and a measurement are different
    kinds of claim, and the type system should say so.
    """
    fields = set(measure.Comparison.__dataclass_fields__)
    assert "predicted_impedance_ohm" in fields
    assert "measured_impedance_ohm" in fields
    forbidden = {
        "corrected_impedance_ohm",
        "combined_impedance_ohm",
        "best_estimate_ohm",
        "fitted_efficiency",
        "reconciled_impedance_ohm",
    }
    assert not (fields & forbidden)
    # Both provenances are carried, separately.
    assert "predicted_source" in fields and "measured_source" in fields


def _sweep_at(z: complex) -> measure.MeasuredSweep:
    freqs = np.array([GRAVES_HZ - 1e6, GRAVES_HZ, GRAVES_HZ + 1e6])
    return measure.sweep_from_impedance(freqs, np.full(3, z), source="bench.s1p")


def test_comparison_diagnoses_a_reactance_error_as_a_length_problem():
    """Reactance off, resistance fine — the signature of a mis-cut element or a stray cable."""
    comparison = measure.compare(
        freq_hz=GRAVES_HZ,
        predicted_impedance_ohm=complex(70.0, 0.0),
        measured=_sweep_at(complex(70.0, 30.0)),
    )
    assert comparison.reactance_error_ohm == pytest.approx(30.0, abs=0.5)
    assert comparison.resistance_error_ohm == pytest.approx(0.0, abs=0.5)
    assert any("length error" in note for note in comparison.notes)
    assert any("reference plane" in note for note in comparison.notes)


def test_comparison_diagnoses_a_resistance_error_as_loss_or_surroundings():
    comparison = measure.compare(
        freq_hz=GRAVES_HZ,
        predicted_impedance_ohm=complex(70.0, 0.0),
        measured=_sweep_at(complex(120.0, 0.0)),
    )
    assert any(
        "gutter" in note or "loss the model does not include" in note for note in comparison.notes
    )


def test_comparison_says_so_when_the_two_agree():
    comparison = measure.compare(
        freq_hz=GRAVES_HZ,
        predicted_impedance_ohm=complex(70.0, -3.0),
        measured=_sweep_at(complex(71.0, -2.0)),
    )
    assert any("agree to within" in note for note in comparison.notes)
    assert "predicted" in comparison.summary() and "measured" in comparison.summary()


def test_comparison_always_states_that_it_keeps_them_apart():
    comparison = measure.compare(
        freq_hz=GRAVES_HZ,
        predicted_impedance_ohm=complex(70.0, 0.0),
        measured=_sweep_at(complex(70.0, 0.0)),
    )
    assert any("different kinds of claim" in note for note in comparison.notes)
    assert comparison.measured_source == "bench.s1p"
    assert comparison.predicted_source == "jansky-forge model"


def test_comparison_computes_swr_for_each_side_separately():
    comparison = measure.compare(
        freq_hz=GRAVES_HZ,
        predicted_impedance_ohm=complex(100.0, 0.0),
        measured=_sweep_at(complex(25.0, 0.0)),
    )
    assert comparison.predicted_swr() == pytest.approx(2.0, abs=0.01)
    assert comparison.measured_swr() == pytest.approx(2.0, abs=0.01)


# --------------------------------------------------------------------------------------
# The most actionable number a VNA gives a builder
# --------------------------------------------------------------------------------------


def test_resonance_offset_turns_a_frequency_error_into_a_length_correction():
    freqs = np.linspace(135e6, 150e6, 151)
    # Resonant 2% low: the element is about 2% too long.
    low = 143.05e6 * 0.98
    s11 = 0.9 * (freqs - low) / 8e6
    sweep = measure.MeasuredSweep(freqs, np.clip(s11, -0.99, 0.99).astype(complex))
    fraction, advice = measure.resonance_offset(sweep, GRAVES_HZ)
    assert fraction == pytest.approx(-0.02, abs=0.003)
    assert "shorten" in advice
    assert "2.0" in advice or "1.9" in advice
    assert "re-measure" in advice  # the correction is not exactly linear, and it says so


def test_resonance_offset_recognises_a_good_result():
    freqs = np.linspace(140e6, 146e6, 61)
    s11 = 0.9 * (freqs - GRAVES_HZ) / 3e6
    sweep = measure.MeasuredSweep(freqs, np.clip(s11, -0.99, 0.99).astype(complex))
    fraction, advice = measure.resonance_offset(sweep, GRAVES_HZ)
    assert abs(fraction) < 0.002
    assert "as close as a tape measure gets" in advice


# --------------------------------------------------------------------------------------
# End to end: M6's prediction meets M7's measurement
# --------------------------------------------------------------------------------------


@pytest.mark.skipif(
    not __import__("jansky_forge.mom", fromlist=["x"]).available_backends(),
    reason="needs a MoM backend for the predicted sweep",
)
def test_a_predicted_sweep_and_a_measured_one_diagnose_a_mis_cut_element():
    """The whole toolchain: solve, 'measure', de-embed, compare, get told what to cut.

    The synthetic bench data is the same antenna 2% long behind half a metre of coax — the
    two most common real-world discrepancies at once. The tool must separate them.
    """
    from jansky_forge import mom

    backend = mom.default_backend()
    lam = wavelength_m(GRAVES_HZ)
    length = 0.95 * lam / 2
    freqs = np.linspace(136e6, 150e6, 15)

    def sweep_for(scale: float) -> measure.MeasuredSweep:
        impedances = [
            backend.solve(
                mom.dipole_model(freq_hz=f, length_m=length * scale, radius_m=0.003), f
            ).feed_impedance_ohm
            for f in freqs
        ]
        return measure.sweep_from_impedance(freqs, np.array(impedances))

    predicted = sweep_for(1.0)
    measured = measure.shift_reference_plane(sweep_for(1.02), length_m=-0.5)

    # Resonance is low, because the element is long.
    fraction, advice = measure.resonance_offset(measured, GRAVES_HZ)
    assert fraction < 0
    assert "shorten" in advice

    # De-embedding the cable recovers the antenna's own impedance.
    at_antenna = measure.shift_reference_plane(measured, length_m=0.5)
    comparison = measure.compare(
        freq_hz=GRAVES_HZ,
        predicted_impedance_ohm=predicted.impedance_at(GRAVES_HZ),
        measured=at_antenna,
    )
    # A too-long element reads inductive against the prediction.
    assert comparison.reactance_error_ohm > 5.0
    assert comparison.predicted_source and comparison.measured_source
