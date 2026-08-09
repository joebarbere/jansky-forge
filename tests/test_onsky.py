"""Tests for M8: on-sky characterization and the jansky-observe cross-repo contract.

The bundle fixture here is built to the **real** upstream schema
(``jansky-observe.observation-bundle/1``) — manifest keys and npz array names copied from
that repo's exporter, not invented. A cross-repo contract tested against a made-up format
tests nothing.
"""

from __future__ import annotations

import json
import math
import zipfile

import numpy as np
import pytest

from jansky_forge import onsky
from jansky_forge.apertures import ParabolicDish

HI_HZ = 1_420_405_751.768


def _write_bundle(directory, *, levels_db, dish_diameter_m=0.7, schema=None, as_zip=False):
    """Build a bundle matching jansky-observe's exporter, for reading back."""
    directory.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(0)
    freqs = np.linspace(1.4194e9, 1.4214e9, 128)
    captures = []
    for index, (kind, level) in enumerate(levels_db):
        name = f"capture-{index}.npz"
        np.savez(
            directory / name,
            frequency_hz=freqs,
            power_db=level + 0.02 * rng.standard_normal(freqs.size),
            capture_id=np.int64(index),
            station_uuid="station-uuid-1234",
            kind=kind,
        )
        captures.append(
            {
                "id": index,
                "kind": kind,
                "start": "2026-08-09T12:00:00Z",
                "az_deg": 180.0,
                "el_deg": 45.0,
                "spectrum_file": name,
            }
        )
    manifest = {
        "schema": schema or onsky.SUPPORTED_BUNDLE_SCHEMA,
        "station": {
            "uuid": "station-uuid-1234",
            "name": "Manayunk rooftop",
            "dish_diameter_m": dish_diameter_m,
            "dish_f_d": 0.35,
        },
        "observation": {
            "name": "Sky/ground calibration",
            "source": {"name": "cold sky"},
            "captures": captures,
        },
    }
    (directory / "bundle.json").write_text(json.dumps(manifest))
    if not as_zip:
        return directory
    archive = directory.parent / "bundle.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        for file in sorted(directory.iterdir()):
            zf.write(file, file.name)
    return archive


# --------------------------------------------------------------------------------------
# Y-factor
# --------------------------------------------------------------------------------------


def test_y_factor_of_hand_computed_cases():
    """Tsys = (T_hot - Y*T_cold)/(Y - 1). A 3 dB Y-factor against 290/6 K gives ~279 K."""
    result = onsky.y_factor_tsys(y_db=3.0, t_hot_k=290.0, t_cold_k=6.0)
    assert result.tsys_k == pytest.approx(279.4, abs=1.0)
    hotter = onsky.y_factor_tsys(y_db=5.0)
    assert hotter.tsys_k < result.tsys_k  # a bigger ratio means a quieter system


def test_y_factor_reports_how_ill_conditioned_it_is():
    """The trap: sensitivity to error explodes as Y approaches unity.

    This is the whole reason the function reports a sensitivity rather than just a number —
    a small Y-factor is not a precise measurement of a hot system, it is barely a
    measurement at all.
    """
    weak = onsky.y_factor_tsys(y_db=1.0)
    strong = onsky.y_factor_tsys(y_db=6.0)
    assert weak.sensitivity_k_per_0p1db > 10 * strong.sensitivity_k_per_0p1db
    assert any("upper bound rather than a number" in n for n in weak.notes)
    assert not any("upper bound" in n for n in strong.notes)


def test_y_factor_warns_about_a_suspiciously_good_result():
    """A saturated front end fakes a good Y-factor by refusing to get hotter."""
    assert any("compressing" in n for n in onsky.y_factor_tsys(y_db=14.0).notes)


def test_y_factor_rejects_impossible_measurements():
    with pytest.raises(ValueError, match="must be positive"):
        onsky.y_factor_tsys(y_db=0.0)  # hot and cold read the same
    with pytest.raises(ValueError, match="must be positive"):
        onsky.y_factor_tsys(y_db=-2.0)  # pointings swapped
    with pytest.raises(ValueError, match="hotter than the cold"):
        onsky.y_factor_tsys(y_db=3.0, t_hot_k=5.0, t_cold_k=100.0)


def test_y_factor_from_recorded_power_levels():
    """What a station actually logs is two power levels, not a ratio."""
    from_powers = onsky.y_factor_from_power_db(hot_power_db=-66.5, cold_power_db=-70.0)
    from_ratio = onsky.y_factor_tsys(y_db=3.5)
    assert from_powers.tsys_k == pytest.approx(from_ratio.tsys_k)


def test_y_factor_supersedes_the_modelled_tsys_and_says_so():
    assert any("supersedes any modelled Tsys" in n for n in onsky.y_factor_tsys(y_db=4.0).notes)


# --------------------------------------------------------------------------------------
# Drift scans
# --------------------------------------------------------------------------------------


def test_sidereal_drift_rate_and_why_circumpolar_is_hard():
    assert onsky.sidereal_drift_rate_deg_per_hour(0.0) == pytest.approx(15.0)
    assert onsky.sidereal_drift_rate_deg_per_hour(60.0) == pytest.approx(7.5)
    # At 80 degrees a 21 degree beam takes over 8 hours to cross.
    rate = onsky.sidereal_drift_rate_deg_per_hour(80.0)
    assert 21.1 / rate > 8.0
    with pytest.raises(ValueError):
        onsky.sidereal_drift_rate_deg_per_hour(100.0)


def _gaussian_drift(hpbw_deg: float, dec_deg: float, points: int = 801):
    rate = onsky.sidereal_drift_rate_deg_per_hour(dec_deg)
    duration = hpbw_deg / rate * 3600 * 4.0
    time_s = np.linspace(0.0, duration, points)
    angle = (time_s - duration / 2) / 3600 * rate
    power = 1.0 + 0.5 * np.exp(-4 * math.log(2) * (angle / hpbw_deg) ** 2)
    return time_s, power


def test_drift_scan_recovers_a_known_beamwidth():
    """Feed it a Gaussian of known width and it must measure that width back."""
    time_s, power = _gaussian_drift(21.1, 58.0)
    result = onsky.drift_scan_beamwidth(time_s=time_s, power=power, declination_deg=58.0)
    assert result.hpbw_deg == pytest.approx(21.1, rel=0.03)
    assert result.baseline == pytest.approx(1.0, abs=0.05)
    assert result.peak_amplitude == pytest.approx(0.5, abs=0.05)


def test_drift_scan_converts_time_to_angle_with_the_declination():
    """The same trace at a different declination is a different beam. Physically."""
    for dec in (0.0, 60.0):
        time_s, power = _gaussian_drift(21.1, dec)
        result = onsky.drift_scan_beamwidth(time_s=time_s, power=power, declination_deg=dec)
        assert result.hpbw_deg == pytest.approx(21.1, rel=0.03)
    # A trace of fixed duration means a wider beam near the pole than at the equator.
    time_s = np.linspace(0, 7200, 401)
    power = 1.0 + 0.5 * np.exp(-4 * math.log(2) * ((time_s - 3600) / 1800) ** 2)
    at_equator = onsky.drift_scan_beamwidth(time_s=time_s, power=power, declination_deg=0.0)
    near_pole = onsky.drift_scan_beamwidth(time_s=time_s, power=power, declination_deg=70.0)
    assert at_equator.hpbw_deg > near_pole.hpbw_deg


def test_drift_scan_rejects_decibels():
    """Half of a dB value is not the half-power point — a genuinely easy mistake."""
    time_s, power = _gaussian_drift(21.1, 30.0)
    with pytest.raises(ValueError, match="LINEAR power, not dB"):
        onsky.drift_scan_beamwidth(
            time_s=time_s, power=10 * np.log10(power) - 40, declination_deg=30.0
        )


def test_drift_scan_needs_a_trace_that_starts_and_ends_off_source():
    """Without off-source ends there is no baseline, and no width to measure."""
    time_s = np.linspace(0, 3600, 200)
    rising = 1.0 + time_s / 3600  # never comes back down
    with pytest.raises(ValueError, match="does not fall to half power"):
        onsky.drift_scan_beamwidth(time_s=time_s, power=rising, declination_deg=0.0)
    flat = np.ones_like(time_s)
    with pytest.raises(ValueError, match="no source above the baseline"):
        onsky.drift_scan_beamwidth(time_s=time_s, power=flat, declination_deg=0.0)


def test_drift_scan_warns_at_high_declination():
    time_s, power = _gaussian_drift(21.1, 78.0)
    result = onsky.drift_scan_beamwidth(time_s=time_s, power=power, declination_deg=78.0)
    assert any("gain-stable throughout" in n for n in result.notes)


def test_drift_scan_states_it_measured_only_one_plane():
    time_s, power = _gaussian_drift(21.1, 30.0)
    result = onsky.drift_scan_beamwidth(time_s=time_s, power=power, declination_deg=30.0)
    assert any("perpendicular plane" in n for n in result.notes)


@pytest.mark.parametrize("kwargs", [dict(time_s=np.array([1.0, 2.0])), dict(power=np.array([1.0]))])
def test_drift_scan_rejects_malformed_input(kwargs):
    base = dict(time_s=np.linspace(0, 10, 20), power=np.ones(20), declination_deg=0.0)
    with pytest.raises(ValueError):
        onsky.drift_scan_beamwidth(**(base | kwargs))


# --------------------------------------------------------------------------------------
# Transit efficiency — the loop closing
# --------------------------------------------------------------------------------------


def test_transit_effective_area_inverts_the_sensitivity_relation():
    """A_e = 2k*dT/S is M4's relation run backwards, and it round-trips."""
    from jansky_forge.sensitivity import antenna_temperature_point_k

    area = 0.305
    flux = 1768.0
    delta_t = antenna_temperature_point_k(flux, area)
    recovered = onsky.transit_effective_area(delta_t_k=delta_t, flux_jy=flux)
    assert recovered.effective_area_m2 == pytest.approx(area, rel=1e-9)


def test_transit_gives_the_efficiency_every_earlier_milestone_assumed():
    physical = math.pi * 0.35**2
    result = onsky.transit_effective_area(
        delta_t_k=0.195, flux_jy=1768.0, physical_area_m2=physical, source_name="Cas A"
    )
    assert 0.0 < result.aperture_efficiency < 1.0
    assert "Cas A" in " ".join(result.notes)
    # It never lets the calibrator's own uncertainty be forgotten.
    assert any("fading calibrator" in n for n in result.notes)
    assert any("resolved source or a miss" in n for n in result.notes)


def test_transit_flags_a_physically_impossible_efficiency():
    """Over 1 means the calibration or the source is wrong, not that the dish is magic."""
    result = onsky.transit_effective_area(
        delta_t_k=5.0, flux_jy=1768.0, physical_area_m2=math.pi * 0.35**2
    )
    assert result.aperture_efficiency > 1.0
    assert any("impossible" in n for n in result.notes)


def test_transit_flags_a_suspiciously_low_efficiency_and_suggests_pointing():
    result = onsky.transit_effective_area(
        delta_t_k=0.02, flux_jy=1768.0, physical_area_m2=math.pi * 0.35**2
    )
    assert any("check pointing" in n for n in result.notes)


@pytest.mark.parametrize(
    "kwargs",
    [dict(delta_t_k=0.0), dict(flux_jy=0.0), dict(physical_area_m2=0.0)],
)
def test_transit_rejects_impossible_inputs(kwargs):
    base = dict(delta_t_k=0.2, flux_jy=1768.0, physical_area_m2=0.38)
    with pytest.raises(ValueError):
        onsky.transit_effective_area(**(base | kwargs))


# --------------------------------------------------------------------------------------
# The cross-repo contract
# --------------------------------------------------------------------------------------


def test_reads_a_bundle_in_the_real_upstream_format(tmp_path):
    path = _write_bundle(tmp_path / "b", levels_db=[("cold_sky", -70.0), ("hot_ground", -66.5)])
    bundle = onsky.read_bundle(path)
    assert bundle.schema == onsky.SUPPORTED_BUNDLE_SCHEMA
    assert bundle.station_name == "Manayunk rooftop"
    assert bundle.dish_diameter_m == pytest.approx(0.7)
    assert bundle.physical_area_m2 == pytest.approx(math.pi * 0.35**2)
    assert len(bundle.captures) == 2
    assert {c.kind for c in bundle.captures} == {"cold_sky", "hot_ground"}
    assert bundle.of_kind("cold_sky")[0].power_db is not None
    assert "Manayunk" in bundle.summary()


def test_reads_a_zipped_bundle_too(tmp_path):
    """The station ships a zip; an unpacked directory is what you get after inspecting it."""
    archive = _write_bundle(
        tmp_path / "b", levels_db=[("cold_sky", -70.0), ("hot_ground", -66.0)], as_zip=True
    )
    bundle = onsky.read_bundle(archive)
    assert len(bundle.captures) == 2
    assert bundle.of_kind("hot_ground")[0].mean_power_db is not None


def test_an_unknown_schema_fails_loudly_rather_than_guessing():
    """The identifier exists so a format change breaks here instead of mis-reading."""
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as directory:
        path = _write_bundle(
            Path(directory) / "b",
            levels_db=[("cold_sky", -70.0)],
            schema="jansky-observe.observation-bundle/2",
        )
        with pytest.raises(ValueError, match="Failing rather than guessing"):
            onsky.read_bundle(path)


def test_missing_bundle_is_reported_clearly(tmp_path):
    with pytest.raises(FileNotFoundError, match="no bundle at"):
        onsky.read_bundle(tmp_path / "nope.zip")


def test_mean_power_averages_in_linear_units_not_decibels():
    """Averaging dB values is wrong, and wrong in a direction that flatters quiet data."""
    capture = onsky.BundleCapture(
        capture_id=1,
        kind="science",
        start_utc="",
        az_deg=0.0,
        el_deg=45.0,
        frequency_hz=np.array([1.0, 2.0]),
        power_db=np.array([0.0, 20.0]),  # 1 and 100 in linear
    )
    # Linear mean is 50.5 -> 17.0 dB. The naive dB mean would be 10 dB.
    assert capture.mean_power_db == pytest.approx(10 * math.log10(50.5), abs=0.01)
    assert capture.mean_power_db > 10.0


def test_y_factor_straight_from_a_bundle(tmp_path):
    """The contract working end to end: point at sky and ground, get a system temperature."""
    path = _write_bundle(tmp_path / "b", levels_db=[("cold_sky", -70.0), ("hot_ground", -66.5)])
    result = onsky.bundle_y_factor(onsky.read_bundle(path))
    assert result.y_db == pytest.approx(3.5, abs=0.1)
    assert 150.0 < result.tsys_k < 350.0
    assert any("station" in n for n in result.notes)


def test_bundle_without_a_calibration_pair_says_what_to_run(tmp_path):
    path = _write_bundle(tmp_path / "b", levels_db=[("science", -69.0)])
    with pytest.raises(ValueError, match="sky/ground calibration pair"):
        onsky.bundle_y_factor(onsky.read_bundle(path))


# --------------------------------------------------------------------------------------
# Measured against predicted — separate, as always
# --------------------------------------------------------------------------------------


def test_beam_comparison_has_no_field_merging_model_and_sky():
    """Same structural rule as M7. One is a model, one is the sky."""
    fields = set(onsky.BeamComparison.__dataclass_fields__)
    assert {"predicted_hpbw_deg", "measured_hpbw_deg"} <= fields
    assert not (
        fields & {"corrected_hpbw_deg", "combined_hpbw_deg", "best_hpbw_deg", "fitted_hpbw_deg"}
    )


def test_a_drift_scanned_beam_lands_beside_the_modelled_one():
    """The payoff of the whole project: a measured beam next to a predicted one."""
    predicted = ParabolicDish(diameter_m=0.7, f_over_d=0.35).characterize(HI_HZ).hpbw_e_deg
    time_s, power = _gaussian_drift(predicted, 58.0)
    measured = onsky.drift_scan_beamwidth(time_s=time_s, power=power, declination_deg=58.0)
    comparison = onsky.compare_beam(predicted_hpbw_deg=predicted, measured=measured)
    assert comparison.ratio == pytest.approx(1.0, abs=0.05)
    assert any("agree to within" in n for n in comparison.notes)
    assert any("no combined value" in n for n in comparison.notes)
    assert "predicted" in comparison.summary() and "measured" in comparison.summary()


def test_beam_comparison_diagnoses_a_wide_measurement():
    time_s, power = _gaussian_drift(30.0, 30.0)
    measured = onsky.drift_scan_beamwidth(time_s=time_s, power=power, declination_deg=30.0)
    comparison = onsky.compare_beam(predicted_hpbw_deg=21.1, measured=measured)
    assert comparison.ratio > 1.25
    assert any("pointing drift" in n or "resolved" in n for n in comparison.notes)


def test_beam_comparison_is_suspicious_of_a_narrow_measurement():
    """Beams are rarely better than modelled; a narrow one usually means over-subtraction."""
    time_s, power = _gaussian_drift(14.0, 30.0)
    measured = onsky.drift_scan_beamwidth(time_s=time_s, power=power, declination_deg=30.0)
    comparison = onsky.compare_beam(predicted_hpbw_deg=21.1, measured=measured)
    assert comparison.ratio < 0.8
    assert any("suspicious" in n for n in comparison.notes)
    assert any("off-source" in n for n in comparison.notes)


def test_beam_comparison_rejects_a_nonsense_prediction():
    time_s, power = _gaussian_drift(21.1, 30.0)
    measured = onsky.drift_scan_beamwidth(time_s=time_s, power=power, declination_deg=30.0)
    with pytest.raises(ValueError, match="must be positive"):
        onsky.compare_beam(predicted_hpbw_deg=0.0, measured=measured)
