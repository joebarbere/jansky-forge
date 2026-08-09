"""Measurement ingest: what the antenna actually does (M7).

Every milestone so far produced a *prediction*. This one reads what a vector network
analyser says about the metal you built, and the whole point is to put the two side by side
**without letting them merge**.

That is honesty invariant 5, and this is the module where it stops being a slogan. A
:class:`Comparison` here has a ``predicted`` field and a ``measured`` field and no third
field combining them. There is no "corrected" value, no blended estimate, no fitted
efficiency that quietly reconciles the two. If they disagree, the disagreement *is* the
result — it is the thing that tells you the horn is a centimetre off, or the probe is too
long, or the model's assumption about your soil was wrong.

**Reading Touchstone is done natively.** A ``.s1p`` file is a header line and three columns,
and every NanoVNA and LiteVNA writes one. Parsing it needs no dependency, so the core stays
installable with almost nothing — and where ``scikit-rf`` is present the test suite checks
the two readers agree rather than trusting either alone.

**The gotcha this module exists to catch.** A VNA measures at *its* port, not at your
antenna. Everything between — the coax, the adapter, the connector you soldered at midnight —
is included in what you read, and a half-metre of cable rotates the impedance right round the
Smith chart at VHF. :func:`shift_reference_plane` moves the plane; ignoring it is the single
most common reason a measurement "disagrees" with a model that was in fact correct.
"""

from __future__ import annotations

import cmath
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from jansky_forge.units import C_M_S

#: The impedance nearly everything is referenced to.
DEFAULT_Z0_OHM = 50.0

_FREQ_UNITS = {"hz": 1.0, "khz": 1e3, "mhz": 1e6, "ghz": 1e9}


@dataclass(frozen=True)
class MeasuredSweep:
    """One-port measured data, with where it came from attached.

    Provenance is a field, not a convention. A sweep whose origin is unrecorded cannot be
    compared honestly against anything later, and "which file was that?" is the question
    every bench notebook fails to answer three months on.
    """

    freq_hz: np.ndarray
    s11: np.ndarray
    z0_ohm: float = DEFAULT_Z0_OHM
    source: str = ""
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.freq_hz.shape != self.s11.shape:
            raise ValueError("frequency and S11 arrays must be the same length")
        if self.freq_hz.size == 0:
            raise ValueError("an empty sweep measures nothing")
        if np.any(self.freq_hz <= 0):
            raise ValueError("frequencies must be positive")
        if self.z0_ohm <= 0:
            raise ValueError("reference impedance must be positive")
        if np.any(np.abs(self.s11) > 1.0 + 1e-6):
            raise ValueError(
                "|S11| exceeds 1: a passive antenna cannot reflect more than it receives. "
                "Check the calibration, or that this is really a reflection measurement."
            )

    @property
    def impedance(self) -> np.ndarray:
        """Z = Z0 (1 + S11) / (1 - S11)."""
        with np.errstate(divide="ignore", invalid="ignore"):
            return self.z0_ohm * (1 + self.s11) / (1 - self.s11)

    @property
    def swr(self) -> np.ndarray:
        magnitude = np.abs(self.s11)
        with np.errstate(divide="ignore"):
            return np.where(magnitude >= 1.0, np.inf, (1 + magnitude) / (1 - magnitude))

    @property
    def return_loss_db(self) -> np.ndarray:
        """Positive dB. Larger is better — 20 dB return loss is a very good match."""
        magnitude = np.abs(self.s11)
        with np.errstate(divide="ignore"):
            return np.where(magnitude > 0, -20 * np.log10(magnitude), np.inf)

    def at(self, freq_hz: float) -> complex:
        """S11 at one frequency, linearly interpolated between samples."""
        if not self.freq_hz[0] <= freq_hz <= self.freq_hz[-1]:
            raise ValueError(
                f"{freq_hz / 1e6:.3f} MHz is outside the swept range "
                f"{self.freq_hz[0] / 1e6:.3f}-{self.freq_hz[-1] / 1e6:.3f} MHz; "
                "extrapolating a resonance is how a good antenna gets a bad reputation"
            )
        real = np.interp(freq_hz, self.freq_hz, self.s11.real)
        imag = np.interp(freq_hz, self.freq_hz, self.s11.imag)
        return complex(real, imag)

    def impedance_at(self, freq_hz: float) -> complex:
        s = self.at(freq_hz)
        return self.z0_ohm * (1 + s) / (1 - s)

    def resonance_hz(self) -> float:
        """Where the antenna is best matched — the minimum of |S11|.

        Note this is the *match* minimum, not necessarily where the reactance crosses zero.
        The two coincide for a simple resonator and part company for anything with a
        matching network in front of it.
        """
        return float(self.freq_hz[int(np.argmin(np.abs(self.s11)))])

    def bandwidth_hz(self, max_swr: float = 2.0) -> tuple[float, float] | None:
        """The contiguous span around resonance where SWR stays below ``max_swr``.

        Returns None if the sweep never gets that good — which is itself an answer.
        """
        if max_swr <= 1.0:
            raise ValueError("max_swr must exceed 1")
        good = self.swr <= max_swr
        if not good.any():
            return None
        best = int(np.argmin(np.abs(self.s11)))
        low = best
        while low > 0 and good[low - 1]:
            low -= 1
        high = best
        while high < good.size - 1 and good[high + 1]:
            high += 1
        return float(self.freq_hz[low]), float(self.freq_hz[high])

    def summary(self) -> str:
        resonance = self.resonance_hz()
        z = self.impedance_at(resonance)
        span = self.bandwidth_hz()
        text = (
            f"{self.freq_hz.size} points, {self.freq_hz[0] / 1e6:.3f}-"
            f"{self.freq_hz[-1] / 1e6:.3f} MHz; best match at {resonance / 1e6:.3f} MHz, "
            f"Z = {z.real:.1f}{z.imag:+.1f}j ohm, SWR {self.swr.min():.2f}:1"
        )
        if span is not None:
            text += f", SWR<2 over {(span[1] - span[0]) / 1e6:.3f} MHz"
        return text


# --------------------------------------------------------------------------------------
# Touchstone
# --------------------------------------------------------------------------------------


def parse_touchstone(text: str, *, source: str = "") -> MeasuredSweep:
    """Read a one-port Touchstone (``.s1p``) file.

    Handles the three data formats a VNA might write — ``RI`` (real/imaginary), ``MA``
    (magnitude/angle) and ``DB`` (dB/angle) — and all four frequency units. Angles are in
    degrees in every format, which is a Touchstone convention worth stating because it is
    not obvious and getting it wrong rotates every point.

    Deliberately native: this is the file a NanoVNA writes, and reading it should not
    require installing a network-analysis library.
    """
    frequency_scale = 1e9  # Touchstone's default unit is GHz
    fmt = "ma"
    z0 = DEFAULT_Z0_OHM
    freqs: list[float] = []
    values: list[complex] = []
    comments: list[str] = []

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("!"):
            comment = line.lstrip("!").strip()
            if comment:
                comments.append(comment)
            continue
        if line.startswith("#"):
            tokens = line[1:].lower().split()
            for index, token in enumerate(tokens):
                if token in _FREQ_UNITS:
                    frequency_scale = _FREQ_UNITS[token]
                elif token in ("ri", "ma", "db"):
                    fmt = token
                elif token == "r" and index + 1 < len(tokens):
                    z0 = float(tokens[index + 1])
            continue
        line = line.split("!", 1)[0]
        parts = re.split(r"[\s,]+", line.strip())
        if len(parts) < 3:
            continue
        frequency, first, second = (float(parts[0]), float(parts[1]), float(parts[2]))
        if fmt == "ri":
            value = complex(first, second)
        elif fmt == "ma":
            value = cmath.rect(first, math.radians(second))
        else:  # db
            value = cmath.rect(10 ** (first / 20.0), math.radians(second))
        freqs.append(frequency * frequency_scale)
        values.append(value)

    if not freqs:
        raise ValueError(
            "no data rows found. A Touchstone file needs an option line starting '#' and "
            "rows of 'frequency value value'."
        )
    return MeasuredSweep(
        freq_hz=np.asarray(freqs, dtype=float),
        s11=np.asarray(values, dtype=complex),
        z0_ohm=z0,
        source=source,
        notes=tuple(comments[:8]),
    )


def read_touchstone(path: str | Path) -> MeasuredSweep:
    """Read a ``.s1p`` from disk, recording the filename as provenance."""
    file = Path(path)
    return parse_touchstone(file.read_text(), source=str(file))


def write_touchstone(sweep: MeasuredSweep, *, comment: str = "") -> str:
    """Serialize a sweep back to Touchstone, in RI form at Hz.

    Mostly for round-trip tests and for handing a prediction to another tool — writing out a
    *predicted* sweep as if it were measured data is exactly the confusion this module
    exists to prevent, so the comment block says which it is.
    """
    lines = []
    if comment:
        lines.append(f"! {comment}")
    if sweep.source:
        lines.append(f"! source: {sweep.source}")
    lines.append(f"# HZ S RI R {sweep.z0_ohm:g}")
    for frequency, value in zip(sweep.freq_hz, sweep.s11, strict=True):
        lines.append(f"{frequency:.6f} {value.real:.9f} {value.imag:.9f}")
    return "\n".join(lines) + "\n"


def sweep_from_impedance(
    freq_hz: np.ndarray, impedance: np.ndarray, *, z0_ohm: float = DEFAULT_Z0_OHM, source: str = ""
) -> MeasuredSweep:
    """Build a sweep from complex impedances — how a *prediction* becomes comparable.

    M6's solver returns impedance, not S-parameters. This converts, so a predicted curve and
    a measured one can be plotted on the same axes. It does not make the prediction a
    measurement, and :func:`compare` keeps them in separate fields for that reason.
    """
    z = np.asarray(impedance, dtype=complex)
    return MeasuredSweep(
        freq_hz=np.asarray(freq_hz, dtype=float),
        s11=(z - z0_ohm) / (z + z0_ohm),
        z0_ohm=z0_ohm,
        source=source or "computed from predicted impedance",
    )


# --------------------------------------------------------------------------------------
# The reference plane — the gotcha
# --------------------------------------------------------------------------------------


def shift_reference_plane(
    sweep: MeasuredSweep,
    *,
    length_m: float,
    velocity_factor: float = 0.66,
    loss_db_per_m: float = 0.0,
) -> MeasuredSweep:
    """Move the measurement plane along a transmission line.

    A VNA calibrated at its own port sees your antenna *through* whatever cable is in
    between, and at VHF half a metre of coax rotates S11 most of the way round the Smith
    chart. Positive ``length_m`` de-embeds a cable (moves the plane toward the antenna);
    negative adds one.

    ``velocity_factor`` defaults to 0.66, which is solid polyethylene coax (RG-58, RG-213).
    Foam dielectric is nearer 0.8, and using the wrong one puts the plane in the wrong place
    by that ratio.
    """
    if velocity_factor <= 0 or velocity_factor > 1:
        raise ValueError("velocity factor must be in (0, 1]")
    beta = 2 * math.pi * sweep.freq_hz * velocity_factor**-1 / C_M_S
    phase = np.exp(2j * beta * length_m)
    attenuation = 10 ** (2 * loss_db_per_m * abs(length_m) / 20.0) if loss_db_per_m else 1.0
    shifted = sweep.s11 * phase * attenuation
    # De-embedding loss can push |S11| above 1 when the assumed loss is too large.
    if np.any(np.abs(shifted) > 1.0):
        shifted = shifted / max(np.max(np.abs(shifted)), 1.0)
    return MeasuredSweep(
        freq_hz=sweep.freq_hz,
        s11=shifted,
        z0_ohm=sweep.z0_ohm,
        source=sweep.source,
        notes=(
            *sweep.notes,
            f"Reference plane moved {length_m:+.3f} m (velocity factor {velocity_factor:g}"
            + (f", {loss_db_per_m:g} dB/m" if loss_db_per_m else "")
            + "). This is a transformation of the data, not new data.",
        ),
    )


# --------------------------------------------------------------------------------------
# Cable
# --------------------------------------------------------------------------------------


def cable_loss_db(
    *, freq_hz: float, length_m: float, loss_db_per_100m: float, reference_freq_hz: float
) -> float:
    """Scale a datasheet loss figure to another frequency.

    Coax attenuation is dominated by conductor loss, which goes as the square root of
    frequency. So one number off a datasheet — "RG-213: 6.6 dB per 100 m at 1 GHz" —
    scales to anywhere useful.

    You supply the datasheet figure rather than choosing from a built-in table on purpose:
    cable specifications vary between manufacturers and between the real cable and the one
    printed on the drum, and a table of invented losses inside a noise budget would be an
    invented noise budget.
    """
    if freq_hz <= 0 or reference_freq_hz <= 0:
        raise ValueError("frequencies must be positive")
    if length_m < 0 or loss_db_per_100m < 0:
        raise ValueError("length and loss cannot be negative")
    return loss_db_per_100m * math.sqrt(freq_hz / reference_freq_hz) * length_m / 100.0


def cable_noise_penalty_k(
    *, loss_db: float, physical_k: float = 290.0, before_lna: bool = True
) -> tuple[float, str]:
    """What a length of cable costs in system temperature. Returns ``(kelvin, why)``.

    This is the join to M4. Loss *ahead of* the first amplifier is charged at nearly the
    full rate — it both attenuates the signal and adds its own thermal noise — while the
    same cable after 30 dB of gain is almost free. That asymmetry is why a mast-head LNA is
    worth the trouble, and why this function asks *where* the cable is.
    """
    from jansky_forge.sensitivity import loss_to_temperature_k

    penalty = loss_to_temperature_k(loss_db, physical_k=physical_k)
    if before_lna:
        return penalty, (
            f"{loss_db:.2f} dB ahead of the LNA adds about {penalty:.0f} K to the system "
            "temperature, and attenuates the signal on top. Move the amplifier to the "
            "antenna if you can."
        )
    return 0.0, (
        f"{loss_db:.2f} dB after the LNA costs almost nothing in noise — the Friis cascade "
        "divides it by the gain ahead of it. It still costs signal level, which matters for "
        "the ADC but not for sensitivity."
    )


# --------------------------------------------------------------------------------------
# Matching
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class LMatch:
    """A two-component L network, with the values you would actually buy."""

    series_reactance_ohm: float
    shunt_reactance_ohm: float
    freq_hz: float
    notes: tuple[str, ...] = ()

    def _component(self, reactance: float) -> tuple[str, float]:
        omega = 2 * math.pi * self.freq_hz
        if reactance >= 0:
            return "inductor", reactance / omega
        return "capacitor", -1.0 / (omega * reactance)

    @property
    def series(self) -> tuple[str, float]:
        """(kind, value) — henries for an inductor, farads for a capacitor."""
        return self._component(self.series_reactance_ohm)

    @property
    def shunt(self) -> tuple[str, float]:
        return self._component(self.shunt_reactance_ohm)

    def summary(self) -> str:
        def render(pair: tuple[str, float]) -> str:
            kind, value = pair
            return (
                f"{value * 1e9:.1f} nH inductor"
                if kind == "inductor"
                else f"{value * 1e12:.1f} pF capacitor"
            )

        return f"series {render(self.series)}, shunt {render(self.shunt)}"


def l_network_match(*, load_ohm: complex, freq_hz: float, z0_ohm: float = DEFAULT_Z0_OHM) -> LMatch:
    """Design an L network matching ``load_ohm`` to ``z0_ohm`` at one frequency.

    Shunt element across the load, series element toward the source — the configuration for
    a load whose resistance is *below* the source impedance, which is the usual case for a
    short antenna or a close-spaced Yagi.

    One frequency. An L network is two components and therefore matches at a point; its
    bandwidth falls as the transformation ratio rises, and a network that transforms 5 ohms
    to 50 will be narrow. The Q is reported so that is visible rather than discovered later.
    """
    if freq_hz <= 0 or z0_ohm <= 0:
        raise ValueError("frequency and reference impedance must be positive")
    r_load, x_load = load_ohm.real, load_ohm.imag
    if r_load <= 0:
        raise ValueError("load resistance must be positive; a passive antenna has one")
    if r_load >= z0_ohm:
        raise ValueError(
            f"this topology needs the load resistance ({r_load:.1f} ohm) below the source "
            f"({z0_ohm:.1f} ohm). Swap the network round for a high-resistance load."
        )

    q = math.sqrt(z0_ohm / r_load - 1.0)
    series = q * r_load - x_load  # cancel the load's own reactance while transforming
    shunt = -z0_ohm / q
    notes = [
        f"Matched at {freq_hz / 1e6:.3f} MHz only. Loaded Q is {q:.2f}; the higher it is, "
        "the narrower the match.",
        "Component values assume ideal parts. Real inductors have resistance and real "
        "capacitors have lead inductance, so expect to tune.",
    ]
    if q > 5:
        notes.append(
            f"Q of {q:.1f} is high — this match will be sharp and sensitive to component "
            "tolerance. Consider a two-stage network, or moving the antenna's own resonance."
        )
    return LMatch(
        series_reactance_ohm=series, shunt_reactance_ohm=shunt, freq_hz=freq_hz, notes=tuple(notes)
    )


# --------------------------------------------------------------------------------------
# Predicted vs measured — the invariant, made structural
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Comparison:
    """A prediction and a measurement, kept apart.

    There is deliberately no combined field. No "corrected" impedance, no blended estimate,
    no efficiency fitted to close the gap. If you want one number, you must choose which
    one, and that choice is yours to make and to defend.
    """

    freq_hz: float
    predicted_impedance_ohm: complex
    measured_impedance_ohm: complex
    predicted_source: str
    measured_source: str
    notes: tuple[str, ...] = field(default_factory=tuple)

    @staticmethod
    def _swr(z: complex, z0: float) -> float:
        reflection = abs((z - z0) / (z + z0))
        return math.inf if reflection >= 1 else (1 + reflection) / (1 - reflection)

    def predicted_swr(self, z0_ohm: float = DEFAULT_Z0_OHM) -> float:
        return self._swr(self.predicted_impedance_ohm, z0_ohm)

    def measured_swr(self, z0_ohm: float = DEFAULT_Z0_OHM) -> float:
        return self._swr(self.measured_impedance_ohm, z0_ohm)

    @property
    def resistance_error_ohm(self) -> float:
        return self.measured_impedance_ohm.real - self.predicted_impedance_ohm.real

    @property
    def reactance_error_ohm(self) -> float:
        return self.measured_impedance_ohm.imag - self.predicted_impedance_ohm.imag

    def summary(self) -> str:
        p, m = self.predicted_impedance_ohm, self.measured_impedance_ohm
        return (
            f"{self.freq_hz / 1e6:.3f} MHz — predicted {p.real:.1f}{p.imag:+.1f}j, "
            f"measured {m.real:.1f}{m.imag:+.1f}j "
            f"(dR {self.resistance_error_ohm:+.1f}, dX {self.reactance_error_ohm:+.1f} ohm)"
        )


def compare(
    *,
    freq_hz: float,
    predicted_impedance_ohm: complex,
    measured: MeasuredSweep,
    predicted_source: str = "jansky-forge model",
    z0_ohm: float = DEFAULT_Z0_OHM,
) -> Comparison:
    """Set a predicted impedance beside a measured one, and interpret the difference.

    The interpretation is the useful part. A pure reactance error usually means the element
    is the wrong length; a resistance error usually means loss, ground, or something nearby
    that the model does not know about. Saying which is which is more use than a number.
    """
    measured_z = measured.impedance_at(freq_hz)
    notes: list[str] = []

    delta_r = measured_z.real - predicted_impedance_ohm.real
    delta_x = measured_z.imag - predicted_impedance_ohm.imag
    scale = max(abs(predicted_impedance_ohm.real), 1.0)

    if abs(delta_x) > 0.2 * scale and abs(delta_r) < 0.15 * scale:
        notes.append(
            f"Reactance is off by {delta_x:+.1f} ohm while resistance agrees. That pattern "
            "is almost always a length error or an un-de-embedded cable, not a modelling "
            "failure — check the reference plane before you cut anything."
        )
    elif abs(delta_r) > 0.25 * scale:
        notes.append(
            f"Resistance is off by {delta_r:+.1f} ohm. Suspect loss the model does not "
            "include, ground proximity, or nearby metal — a model in free space does not "
            "know about your gutter."
        )
    else:
        notes.append("Prediction and measurement agree to within the usual bench tolerances.")

    notes.append(
        "These two numbers are kept separate on purpose. There is no combined value here, "
        "because a prediction and a measurement are different kinds of claim."
    )
    return Comparison(
        freq_hz=freq_hz,
        predicted_impedance_ohm=predicted_impedance_ohm,
        measured_impedance_ohm=measured_z,
        predicted_source=predicted_source,
        measured_source=measured.source or "unrecorded measurement",
        notes=tuple(notes),
    )


def resonance_offset(measured: MeasuredSweep, design_freq_hz: float) -> tuple[float, str]:
    """How far off design the antenna actually resonated, and what to do about it.

    Element length scales inversely with frequency, so a resonance 3% low means the element
    is about 3% long. That is the most actionable single number a VNA gives an antenna
    builder, and the correction is arithmetic rather than guesswork.
    """
    actual = measured.resonance_hz()
    fractional = (actual - design_freq_hz) / design_freq_hz
    if abs(fractional) < 0.002:
        return fractional, (
            f"Resonant at {actual / 1e6:.3f} MHz against a design of "
            f"{design_freq_hz / 1e6:.3f} — within 0.2%, which is as close as a tape measure gets."
        )
    direction = "high" if fractional > 0 else "low"
    remedy = "shorten" if fractional < 0 else "lengthen"
    return fractional, (
        f"Resonant at {actual / 1e6:.3f} MHz, {abs(fractional) * 100:.2f}% {direction} of the "
        f"{design_freq_hz / 1e6:.3f} MHz design. Element length scales inversely with "
        f"frequency, so {remedy} it by about {abs(fractional) * 100:.2f}% — and re-measure, "
        "because end effects mean the correction is rarely exactly linear."
    )
