"""On-sky characterization: what the antenna does under the actual sky (M8).

M7 read a vector network analyser, which tells you whether the antenna is *matched*. A
matched antenna can still be pointing at your neighbour's shed. This module reads what the
sky put through it, and produces the three numbers that decide whether a telescope works:
system temperature, beam width, and aperture efficiency.

Unlike everything before it, none of these are derived from geometry. They are measured, and
they arrive from the sibling `jansky-observe <https://github.com/joebarbere/jansky-observe>`_
station software as a codified observation bundle — the cross-repo contract written into
this project's plan at M0 and honoured here.

**The three measurements, and what each is really telling you.**

*Y-factor* points the antenna at something hot (the ground, ~290 K) and something cold (the
sky, a few K) and takes the power ratio. The arithmetic is trivial; the trap is that
sensitivity to measurement error explodes as the ratio approaches unity, so a 1 dB Y-factor
is nearly uninformative while a 5 dB one is solid. :func:`y_factor_tsys` says so with numbers
rather than leaving it to be discovered.

*Drift scan* stops the dish and lets the sky rotate a source through the beam. The recorded
power against time **is** the beam pattern, once you convert time to angle at 15·cos(dec)
degrees per hour. It is the only beam measurement an amateur can make without a rotator, a
test range, or a second site.

*Transit efficiency* uses a source of known flux to turn a temperature rise into collecting
area, and hence into the aperture efficiency every earlier milestone could only assume.

**Measured never merges with predicted.** Same structural rule as M7: a
:class:`BeamComparison` carries the model's number and the sky's number in separate fields
with nothing combining them.
"""

from __future__ import annotations

import json
import math
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from jansky_forge.units import JANSKY_W_M2_HZ, K_B

#: The bundle format this module consumes. Bumping it upstream should break loudly here
#: rather than silently mis-reading a changed layout.
SUPPORTED_BUNDLE_SCHEMA = "jansky-observe.observation-bundle/1"

#: Sidereal drift rate at the celestial equator, degrees per hour.
SIDEREAL_RATE_DEG_PER_HOUR = 15.0

#: Capture kinds the station uses for calibration pointings.
COLD_KIND = "cold_sky"
HOT_KIND = "hot_ground"


# --------------------------------------------------------------------------------------
# Y-factor
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class YFactorResult:
    """A measured system temperature, with the honesty its arithmetic demands."""

    tsys_k: float
    y_db: float
    t_hot_k: float
    t_cold_k: float
    #: How much Tsys moves for a 0.1 dB error in the measured ratio — the number that says
    #: whether to believe the answer.
    sensitivity_k_per_0p1db: float
    notes: tuple[str, ...] = ()

    def summary(self) -> str:
        return (
            f"Tsys = {self.tsys_k:.1f} K from a {self.y_db:.2f} dB Y-factor "
            f"(+/- {self.sensitivity_k_per_0p1db:.1f} K per 0.1 dB of measurement error)"
        )


def y_factor_tsys(*, y_db: float, t_hot_k: float = 290.0, t_cold_k: float = 6.0) -> YFactorResult:
    """System temperature from a hot/cold power ratio: Tsys = (T_hot - Y·T_cold)/(Y - 1).

    ``t_hot_k`` defaults to 290 K, the ground. ``t_cold_k`` defaults to 6 K, which is a cold
    L-band sky including the atmosphere — use :func:`jansky_forge.sensitivity.sky_temperature_k`
    for another band, and remember the sky is not cold at 20 MHz.

    **The trap this function exists to flag.** Tsys depends on Y through a difference of
    nearly-equal quantities, so as Y approaches 1 (0 dB) the result runs away. At a 1 dB
    Y-factor, a tenth of a decibel of error moves Tsys by over a hundred kelvin; at 5 dB the
    same error is worth a few. The reported sensitivity makes that concrete instead of
    leaving it to be discovered after the fact.
    """
    if y_db <= 0:
        raise ValueError(
            f"a Y-factor must be positive — the hot load must read hotter than the cold sky. "
            f"Got {y_db:g} dB, which means the pointings are swapped or the ground is colder "
            "than the sky, and neither is likely."
        )
    if t_hot_k <= t_cold_k:
        raise ValueError("the hot load must be hotter than the cold one")

    y = 10 ** (y_db / 10.0)
    tsys = (t_hot_k - y * t_cold_k) / (y - 1.0)
    if tsys <= 0:
        raise ValueError(
            f"a {y_db:g} dB Y-factor implies a negative system temperature against these "
            "hot and cold references, which is impossible. Either the references are wrong "
            "or the measurement is."
        )
    nudged = 10 ** ((y_db + 0.1) / 10.0)
    sensitivity = abs(tsys - (t_hot_k - nudged * t_cold_k) / (nudged - 1.0))

    notes = []
    if y_db < 1.5:
        notes.append(
            f"A {y_db:.2f} dB Y-factor is small, and Tsys is correspondingly ill-conditioned: "
            f"0.1 dB of error moves the answer by {sensitivity:.0f} K. Either the system is "
            "genuinely hot, or the hot and cold references are not far enough apart to "
            "measure with. Treat this as an upper bound rather than a number."
        )
    elif y_db > 10:
        notes.append(
            f"A {y_db:.2f} dB Y-factor is unusually large for an amateur system. Check the "
            "receiver was not compressing on the hot load — a saturated front end fakes a "
            "good Y-factor by refusing to get any hotter."
        )
    notes.append(
        "This is a measurement of the whole system, including whatever the feed sees past "
        "the dish. It supersedes any modelled Tsys, and it is the number to carry forward."
    )
    return YFactorResult(
        tsys_k=tsys,
        y_db=y_db,
        t_hot_k=t_hot_k,
        t_cold_k=t_cold_k,
        sensitivity_k_per_0p1db=sensitivity,
        notes=tuple(notes),
    )


def y_factor_from_power_db(
    *, hot_power_db: float, cold_power_db: float, t_hot_k: float = 290.0, t_cold_k: float = 6.0
) -> YFactorResult:
    """Y-factor from two recorded power levels in dB — what a station actually logs."""
    return y_factor_tsys(y_db=hot_power_db - cold_power_db, t_hot_k=t_hot_k, t_cold_k=t_cold_k)


# --------------------------------------------------------------------------------------
# Drift scans
# --------------------------------------------------------------------------------------


def sidereal_drift_rate_deg_per_hour(declination_deg: float) -> float:
    """How fast the sky carries a source past a fixed beam: 15·cos(dec) degrees per hour.

    The cosine is why circumpolar sources are the hard case for a drift scan: at 80 degrees
    declination the sky moves 2.6 degrees an hour, so a 21 degree beam takes eight hours to
    cross and the receiver must be stable for all of it.
    """
    if not -90.0 <= declination_deg <= 90.0:
        raise ValueError("declination must be between -90 and +90 degrees")
    return SIDEREAL_RATE_DEG_PER_HOUR * math.cos(math.radians(declination_deg))


@dataclass(frozen=True)
class DriftScanResult:
    """A beam measured by letting the sky do the scanning."""

    hpbw_deg: float
    peak_amplitude: float
    peak_time_s: float
    declination_deg: float
    baseline: float
    notes: tuple[str, ...] = ()

    def summary(self) -> str:
        return (
            f"measured HPBW {self.hpbw_deg:.2f} deg at dec {self.declination_deg:+.1f}, "
            f"peak {self.peak_amplitude:.4g} above a baseline of {self.baseline:.4g}"
        )


def drift_scan_beamwidth(
    *,
    time_s: np.ndarray,
    power: np.ndarray,
    declination_deg: float,
    baseline: float | None = None,
) -> DriftScanResult:
    """Measure a beam's half-power width from a drift-scan trace.

    ``power`` must be **linear** power, not decibels: a beam's half-power point is half the
    power, and taking half of a dB value is a different and wrong thing. That mistake makes
    the beam look far narrower than it is, so the input convention is stated rather than
    assumed.

    The baseline (the off-source level) is taken from the outer tenth of the trace at each
    end unless given. A drift scan that does not begin and end off-source has no baseline to
    subtract, and its width will be overestimated.
    """
    time_s = np.asarray(time_s, dtype=float)
    power = np.asarray(power, dtype=float)
    if time_s.shape != power.shape:
        raise ValueError("time and power arrays must be the same length")
    if time_s.size < 5:
        raise ValueError("a drift scan needs more than a handful of samples to fit a beam")
    if np.any(power < 0):
        raise ValueError(
            "negative power. This function needs LINEAR power, not dB — halving a dB value "
            "is not the half-power point."
        )

    if baseline is None:
        edge = max(1, time_s.size // 10)
        baseline = float(np.median(np.concatenate([power[:edge], power[-edge:]])))
    corrected = power - baseline
    peak_index = int(np.argmax(corrected))
    peak = float(corrected[peak_index])
    if peak <= 0:
        raise ValueError("no source above the baseline; there is no beam here to measure")

    half = peak / 2.0
    crossings: list[float] = []
    for direction in (-1, 1):
        index = peak_index
        while 0 < index < corrected.size - 1 and corrected[index] > half:
            index += direction
        if corrected[index] > half:
            # Walked off the end of the trace still above half power: there is no width here.
            raise ValueError(
                "the trace does not fall to half power on both sides of the peak. A drift "
                "scan must start and finish off-source, or there is nothing to measure the "
                "width of."
            )
        # Linear interpolation between the bracketing samples.
        previous = index - direction
        span = corrected[index] - corrected[previous]
        fraction = 0.0 if span == 0 else (half - corrected[previous]) / span
        crossings.append(float(time_s[previous] + fraction * (time_s[index] - time_s[previous])))

    notes: list[str] = []
    duration_s = abs(crossings[1] - crossings[0])
    rate = sidereal_drift_rate_deg_per_hour(declination_deg)
    hpbw = duration_s / 3600.0 * rate

    if abs(declination_deg) > 70:
        notes.append(
            f"At declination {declination_deg:+.0f} the sky drifts only {rate:.2f} deg/hr, so "
            "this beam took a long time to cross and the result depends on the receiver "
            "having been gain-stable throughout. Consider a source nearer the equator."
        )
    notes.append(
        "This is the beam in the direction the source drifted, which is not the same as the "
        "beam in the perpendicular plane unless the antenna is symmetric."
    )
    return DriftScanResult(
        hpbw_deg=hpbw,
        peak_amplitude=peak,
        peak_time_s=float(time_s[peak_index]),
        declination_deg=declination_deg,
        baseline=float(baseline),
        notes=tuple(notes),
    )


# --------------------------------------------------------------------------------------
# Transit efficiency
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class TransitResult:
    """Collecting area and efficiency, measured against a source of known flux."""

    effective_area_m2: float
    aperture_efficiency: float | None
    delta_t_k: float
    flux_jy: float
    notes: tuple[str, ...] = ()

    def summary(self) -> str:
        text = f"A_e = {self.effective_area_m2:.4f} m^2 from a {self.delta_t_k:.4f} K rise"
        if self.aperture_efficiency is not None:
            text += f", aperture efficiency {self.aperture_efficiency:.3f}"
        return text


def transit_effective_area(
    *,
    delta_t_k: float,
    flux_jy: float,
    physical_area_m2: float | None = None,
    source_name: str = "",
) -> TransitResult:
    """Turn a transit's temperature rise into collecting area: A_e = 2k·ΔT / S.

    This is the inverse of the sensitivity relation from M4, and it is the measurement that
    finally closes the loop — every efficiency before this milestone was assumed, computed,
    or bounded. This one was observed.

    ``delta_t_k`` is the rise **above the off-source baseline**, in kelvin, which means the
    receiver must already be calibrated in temperature (a Y-factor gives you that). Feeding
    raw uncalibrated power in here produces a confident and meaningless number.
    """
    if delta_t_k <= 0:
        raise ValueError("the on-source rise must be positive; nothing transited otherwise")
    if flux_jy <= 0:
        raise ValueError("source flux must be positive")
    area = 2.0 * K_B * delta_t_k / (flux_jy * JANSKY_W_M2_HZ)

    efficiency = None
    notes = []
    if physical_area_m2 is not None:
        if physical_area_m2 <= 0:
            raise ValueError("physical area must be positive")
        efficiency = area / physical_area_m2
        if efficiency > 1.0:
            notes.append(
                f"Aperture efficiency came out at {efficiency:.2f}, which is above 1 and "
                "therefore impossible: the antenna cannot collect more than its physical "
                "area. Suspect the temperature calibration, a resolved source, or "
                "confusion from something else in the beam."
            )
        elif efficiency < 0.2:
            notes.append(
                f"An aperture efficiency of {efficiency:.2f} is low. Before blaming the dish, "
                "check pointing — a transit that missed the beam centre understates "
                "everything — and check the source was not resolved."
            )
    notes.append(
        f"Measured against {source_name or 'a source'} of {flux_jy:g} Jy. The answer is only "
        "as good as that flux: a fading calibrator quoted at the wrong epoch propagates "
        "straight into this efficiency."
    )
    notes.append(
        "Assumes the source is unresolved and passed through the beam centre. A resolved "
        "source or a miss both bias this low."
    )
    return TransitResult(
        effective_area_m2=area,
        aperture_efficiency=efficiency,
        delta_t_k=delta_t_k,
        flux_jy=flux_jy,
        notes=tuple(notes),
    )


# --------------------------------------------------------------------------------------
# The cross-repo contract: jansky-observe bundles
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class BundleCapture:
    """One capture from an observation bundle."""

    capture_id: int
    kind: str
    start_utc: str
    az_deg: float
    el_deg: float
    frequency_hz: np.ndarray | None = None
    power_db: np.ndarray | None = None

    @property
    def mean_power_db(self) -> float | None:
        """Band-averaged power. Averaging in dB is wrong, so this converts first."""
        if self.power_db is None or self.power_db.size == 0:
            return None
        linear = 10 ** (np.asarray(self.power_db, dtype=float) / 10.0)
        return float(10 * np.log10(linear.mean()))


@dataclass(frozen=True)
class ObservationBundle:
    """A parsed ``jansky-observe`` observation bundle."""

    schema: str
    station_uuid: str
    station_name: str
    dish_diameter_m: float | None
    observation_name: str
    source_name: str | None
    captures: tuple[BundleCapture, ...]
    path: str = ""
    notes: tuple[str, ...] = field(default_factory=tuple)

    def of_kind(self, kind: str) -> list[BundleCapture]:
        return [capture for capture in self.captures if capture.kind == kind]

    @property
    def physical_area_m2(self) -> float | None:
        if self.dish_diameter_m is None or self.dish_diameter_m <= 0:
            return None
        return math.pi * (self.dish_diameter_m / 2.0) ** 2

    def summary(self) -> str:
        kinds = ", ".join(sorted({capture.kind for capture in self.captures})) or "none"
        return (
            f"{self.observation_name!r} from station {self.station_name} "
            f"({len(self.captures)} captures: {kinds})"
        )


def _load_manifest_and_spectra(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Read ``bundle.json`` and the per-capture npz files, from a zip or a directory."""
    spectra: dict[str, Any] = {}
    if path.is_dir():
        manifest = json.loads((path / "bundle.json").read_text())
        for npz in sorted(path.glob("capture-*.npz")):
            spectra[npz.name] = np.load(npz, allow_pickle=False)
        return manifest, spectra
    with zipfile.ZipFile(path) as archive:
        manifest = json.loads(archive.read("bundle.json"))
        for name in archive.namelist():
            if name.endswith(".npz"):
                import io

                spectra[Path(name).name] = np.load(
                    io.BytesIO(archive.read(name)), allow_pickle=False
                )
    return manifest, spectra


def read_bundle(path: str | Path) -> ObservationBundle:
    """Read a ``jansky-observe`` observation bundle — zip or unpacked directory.

    The schema identifier is checked rather than assumed. If the station software bumps its
    format, this should fail loudly here instead of silently mis-reading a changed layout,
    which is the whole reason that identifier exists.
    """
    file = Path(path)
    if not file.exists():
        raise FileNotFoundError(f"no bundle at {file}")
    manifest, spectra = _load_manifest_and_spectra(file)

    schema = manifest.get("schema", "")
    notes: list[str] = []
    if schema != SUPPORTED_BUNDLE_SCHEMA:
        raise ValueError(
            f"bundle schema is {schema!r}, and this reader understands "
            f"{SUPPORTED_BUNDLE_SCHEMA!r}. Failing rather than guessing at a changed layout."
        )

    station = manifest.get("station") or {}
    observation = manifest.get("observation") or {}
    source = observation.get("source") or {}

    captures = []
    for block in observation.get("captures", manifest.get("captures", [])):
        spectrum = spectra.get(str(block.get("spectrum_file", "")))
        captures.append(
            BundleCapture(
                capture_id=int(block.get("id", -1)),
                kind=str(block.get("kind", "science")),
                start_utc=str(block.get("start") or ""),
                az_deg=float(block.get("az_deg") or math.nan),
                el_deg=float(block.get("el_deg") or math.nan),
                frequency_hz=(
                    np.asarray(spectrum["frequency_hz"]) if spectrum is not None else None
                ),
                power_db=(np.asarray(spectrum["power_db"]) if spectrum is not None else None),
            )
        )
    if not captures:
        notes.append("This bundle contains no captures, so there is nothing to characterize.")

    return ObservationBundle(
        schema=schema,
        station_uuid=str(station.get("uuid", "")),
        station_name=str(station.get("name", "unnamed station")),
        dish_diameter_m=station.get("dish_diameter_m"),
        observation_name=str(observation.get("name", "unnamed observation")),
        source_name=source.get("name"),
        captures=tuple(captures),
        path=str(file),
        notes=tuple(notes),
    )


def bundle_y_factor(
    bundle: ObservationBundle, *, t_hot_k: float = 290.0, t_cold_k: float = 6.0
) -> YFactorResult:
    """Compute Tsys from a bundle's ``cold_sky`` and ``hot_ground`` captures.

    The station already labels calibration pointings with those kinds, which is why this
    needs no configuration: point at the sky, point at the ground, and the bundle carries
    enough to work out the system temperature.
    """
    cold = bundle.of_kind(COLD_KIND)
    hot = bundle.of_kind(HOT_KIND)
    if not cold or not hot:
        raise ValueError(
            f"a Y-factor needs both a {COLD_KIND!r} and a {HOT_KIND!r} capture; this bundle "
            f"has {len(cold)} and {len(hot)}. Run the station's sky/ground calibration pair."
        )
    cold_power = [c.mean_power_db for c in cold if c.mean_power_db is not None]
    hot_power = [h.mean_power_db for h in hot if h.mean_power_db is not None]
    if not cold_power or not hot_power:
        raise ValueError("the calibration captures carry no spectra to average")

    result = y_factor_from_power_db(
        hot_power_db=float(np.mean(hot_power)),
        cold_power_db=float(np.mean(cold_power)),
        t_hot_k=t_hot_k,
        t_cold_k=t_cold_k,
    )
    return YFactorResult(
        tsys_k=result.tsys_k,
        y_db=result.y_db,
        t_hot_k=result.t_hot_k,
        t_cold_k=result.t_cold_k,
        sensitivity_k_per_0p1db=result.sensitivity_k_per_0p1db,
        notes=(
            *result.notes,
            f"Averaged over {len(hot_power)} hot and {len(cold_power)} cold captures from "
            f"station {bundle.station_uuid[:8] or 'unknown'}.",
        ),
    )


# --------------------------------------------------------------------------------------
# Measured against predicted — separate fields, as always
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class BeamComparison:
    """The model's beam and the sky's beam, side by side and never merged."""

    predicted_hpbw_deg: float
    measured_hpbw_deg: float
    predicted_source: str
    measured_source: str
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def ratio(self) -> float:
        return self.measured_hpbw_deg / self.predicted_hpbw_deg

    def summary(self) -> str:
        return (
            f"predicted {self.predicted_hpbw_deg:.2f} deg, measured "
            f"{self.measured_hpbw_deg:.2f} deg (ratio {self.ratio:.2f})"
        )


def compare_beam(
    *,
    predicted_hpbw_deg: float,
    measured: DriftScanResult,
    predicted_source: str = "jansky-forge model",
) -> BeamComparison:
    """Set a modelled beamwidth beside a drift-scanned one, and interpret the difference.

    A measured beam wider than predicted usually means pointing wander during the scan or a
    resolved source; narrower usually means the baseline was taken on-source, which flatters
    the width. Saying which is more use than the ratio alone.
    """
    if predicted_hpbw_deg <= 0:
        raise ValueError("predicted beamwidth must be positive")
    ratio = measured.hpbw_deg / predicted_hpbw_deg
    notes = []
    if ratio > 1.25:
        notes.append(
            f"The measured beam is {ratio:.2f} times the predicted width. Suspect pointing "
            "drift during the scan, or a source that is resolved rather than a point — both "
            "broaden a drift trace without the antenna being at fault."
        )
    elif ratio < 0.8:
        notes.append(
            f"The measured beam is only {ratio:.2f} of the predicted width, which is "
            "suspicious: beams are rarely better than modelled. Check the baseline was taken "
            "genuinely off-source, since subtracting too much narrows the trace."
        )
    else:
        notes.append("Measured and predicted beamwidths agree to within the usual scatter.")
    notes.append(
        "These are kept separate on purpose: one is a model and one is the sky, and there "
        "is no combined value here."
    )
    notes.extend(measured.notes)
    return BeamComparison(
        predicted_hpbw_deg=predicted_hpbw_deg,
        measured_hpbw_deg=measured.hpbw_deg,
        predicted_source=predicted_source,
        measured_source=f"drift scan at dec {measured.declination_deg:+.1f}",
        notes=tuple(notes),
    )
