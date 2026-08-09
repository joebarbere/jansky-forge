"""Two-port networks: the vocabulary the receiver track is written in (N0).

M4 taught the tool to say "your system is receiver-limited" and then had nothing to offer.
This is the first step toward offering something. It is deliberately foundational — a
`TwoPort`, the conversions between the ways of describing one, the three gain definitions,
and a cascade — because everything in N1–N5 is written in these terms and a mistake here
would propagate silently through all of it.

**The ordering trap.** Touchstone two-port data is written ``S11 S21 S12 S22`` — **S21
before S12**, unlike every other port count, where the order is row-major. Reading it the
obvious way transposes the device, which for a reciprocal attenuator is invisible and for an
amplifier means reading its *reverse isolation* as its gain. That is a 30 dB error that looks
like a working design. :func:`parse_touchstone_2port` handles it and the tests pin it.

**Three gains, not one.** "Gain" is three different numbers and they are routinely confused:

===================  ==================================================================
**Transducer** G_T   Power delivered to the load over power *available* from the source.
                     What you actually get. Depends on both terminations
**Available** G_A    Power available from the network over power available from the
                     source. Depends only on the source — this is the one noise figure
                     calculations use
**Operating** G_P    Power delivered to the load over power *input* to the network.
                     Depends only on the load
===================  ==================================================================

They collapse to ``|S21|²`` when both ports are matched, which is the check that they are
implemented right.

**We ship no transistor data.** Fmin, Γopt and Rn come from vendor files. Under honesty
invariant 2 this module reads them and never invents them — the same rule that kept a
cable-loss table out of M7.

References
----------
Pozar, *Microwave Engineering*, ch. 4 (network analysis) and ch. 12 (amplifier design).
Gonzalez, *Microwave Transistor Amplifiers* — the gain definitions and their conditions.
"""

from __future__ import annotations

import cmath
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from jansky_forge.measure import DEFAULT_Z0_OHM, parse_option_line

#: Rows of this many numbers in a ``.s2p`` are S-parameter data; the shorter rows are the
#: optional noise block. Column count is the robust discriminator, and it is what the
#: standard actually distinguishes on.
_S_COLUMNS = 9
_NOISE_COLUMNS = 5


@dataclass(frozen=True)
class NoiseParameters:
    """A device's noise behaviour versus source impedance, from its datasheet.

    Four numbers per frequency, and they are not independent of the match: an amplifier has
    a *minimum* noise figure achieved at one particular source reflection coefficient, and
    gets worse as you move away from it. That is the fact N2 is built on and the reason
    "match for best noise" and "match for best gain" are different instructions.
    """

    freq_hz: np.ndarray
    #: Minimum achievable noise figure, dB.
    fmin_db: np.ndarray
    #: Source reflection coefficient that achieves it.
    gamma_opt: np.ndarray
    #: Equivalent noise resistance, ohms — how sharply F degrades away from Γopt.
    rn_ohm: np.ndarray

    def __post_init__(self) -> None:
        shapes = {a.shape for a in (self.freq_hz, self.fmin_db, self.gamma_opt, self.rn_ohm)}
        if len(shapes) != 1:
            raise ValueError("all noise-parameter arrays must be the same length")
        if self.freq_hz.size == 0:
            raise ValueError("empty noise data")

    def noise_figure_db(
        self, gamma_source: complex, freq_hz: float, z0_ohm: float = DEFAULT_Z0_OHM
    ) -> float:
        """Noise figure for a given source match.

        F = Fmin + (4·Rn/Z0)·|Γs − Γopt|² / ((1 − |Γs|²)·|1 + Γopt|²)

        At Γs = Γopt this returns Fmin, which is the check that it is right.
        """
        if abs(gamma_source) >= 1.0:
            raise ValueError(
                "|Γs| must be below 1 — a passive source cannot reflect more than it receives"
            )
        fmin = float(np.interp(freq_hz, self.freq_hz, self.fmin_db))
        rn = float(np.interp(freq_hz, self.freq_hz, self.rn_ohm))
        opt = complex(
            float(np.interp(freq_hz, self.freq_hz, self.gamma_opt.real)),
            float(np.interp(freq_hz, self.freq_hz, self.gamma_opt.imag)),
        )
        fmin_linear = 10 ** (fmin / 10.0)
        excess = (
            4.0
            * rn
            / z0_ohm
            * abs(gamma_source - opt) ** 2
            / ((1 - abs(gamma_source) ** 2) * abs(1 + opt) ** 2)
        )
        return 10.0 * math.log10(fmin_linear + excess)


@dataclass(frozen=True)
class TwoPort:
    """A two-port network: an S-matrix per frequency, and where it came from."""

    freq_hz: np.ndarray
    #: Shape (n, 2, 2). ``s[:, 0, 1]`` is S12, ``s[:, 1, 0]`` is S21 — index by row, column.
    s: np.ndarray
    z0_ohm: float = DEFAULT_Z0_OHM
    noise: NoiseParameters | None = None
    source: str = ""
    notes: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.s.ndim != 3 or self.s.shape[1:] != (2, 2):
            raise ValueError(f"S must have shape (n, 2, 2), got {self.s.shape}")
        if self.freq_hz.shape[0] != self.s.shape[0]:
            raise ValueError("frequency and S arrays must have the same length")
        if self.freq_hz.size == 0:
            raise ValueError("an empty network describes nothing")
        if self.z0_ohm <= 0:
            raise ValueError("reference impedance must be positive")

    # -- named accessors, because s[:, 1, 0] is where the transpose bug hides -------------
    @property
    def s11(self) -> np.ndarray:
        return self.s[:, 0, 0]

    @property
    def s12(self) -> np.ndarray:
        """Reverse transmission — isolation, for an amplifier."""
        return self.s[:, 0, 1]

    @property
    def s21(self) -> np.ndarray:
        """Forward transmission — gain, for an amplifier."""
        return self.s[:, 1, 0]

    @property
    def s22(self) -> np.ndarray:
        return self.s[:, 1, 1]

    @property
    def is_reciprocal(self) -> bool:
        """S12 == S21. True of any passive network; false of any amplifier.

        Useful as a sanity check on a freshly-read file: an amplifier that reads reciprocal
        has almost certainly been transposed.
        """
        return bool(np.allclose(self.s12, self.s21, atol=1e-9))

    def at(self, freq_hz: float) -> np.ndarray:
        """The 2×2 S-matrix at one frequency, interpolated between samples."""
        if not self.freq_hz[0] <= freq_hz <= self.freq_hz[-1]:
            raise ValueError(
                f"{freq_hz / 1e6:.3f} MHz is outside the swept range "
                f"{self.freq_hz[0] / 1e6:.3f}-{self.freq_hz[-1] / 1e6:.3f} MHz"
            )
        out = np.empty((2, 2), dtype=complex)
        for i in range(2):
            for j in range(2):
                out[i, j] = complex(
                    float(np.interp(freq_hz, self.freq_hz, self.s[:, i, j].real)),
                    float(np.interp(freq_hz, self.freq_hz, self.s[:, i, j].imag)),
                )
        return out

    def summary(self) -> str:
        mid = self.freq_hz[len(self.freq_hz) // 2]
        s = self.at(float(mid))
        kind = "reciprocal (passive)" if self.is_reciprocal else "non-reciprocal (active)"
        return (
            f"{self.freq_hz.size} points, {self.freq_hz[0] / 1e6:.3f}-"
            f"{self.freq_hz[-1] / 1e6:.3f} MHz, {kind}; at {mid / 1e6:.1f} MHz "
            f"|S21| = {20 * math.log10(abs(s[1, 0])):+.2f} dB, "
            f"|S11| = {20 * math.log10(max(abs(s[0, 0]), 1e-12)):+.1f} dB"
        )


# --------------------------------------------------------------------------------------
# Touchstone .s2p
# --------------------------------------------------------------------------------------


def parse_touchstone_2port(text: str, *, source: str = "") -> TwoPort:
    """Read a two-port Touchstone (``.s2p``), including the optional noise block.

    **Column order is S11 S21 S12 S22.** Two-port Touchstone is the historical exception to
    row-major ordering, and reading it row-major silently transposes the device. For a
    reciprocal network that is invisible; for an amplifier it swaps 20 dB of gain for 20 dB
    of isolation and everything downstream is wrong in a plausible-looking way.

    Noise rows follow the S-parameter block and carry five columns:
    ``freq  Fmin(dB)  |Γopt|  ∠Γopt(deg)  Rn/Z0``.
    """
    scale, fmt, z0 = 1e9, "ma", DEFAULT_Z0_OHM
    freqs: list[float] = []
    matrices: list[np.ndarray] = []
    noise_rows: list[tuple[float, float, complex, float]] = []
    comments: list[str] = []

    def value(first: float, second: float) -> complex:
        if fmt == "ri":
            return complex(first, second)
        if fmt == "ma":
            return cmath.rect(first, math.radians(second))
        return cmath.rect(10 ** (first / 20.0), math.radians(second))

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
            scale, fmt, z0 = parse_option_line(line)
            continue
        parts = re.split(r"[\s,]+", line.split("!", 1)[0].strip())
        try:
            numbers = [float(p) for p in parts if p]
        except ValueError:
            continue
        if len(numbers) >= _S_COLUMNS:
            f, s11a, s11b, s21a, s21b, s12a, s12b, s22a, s22b = numbers[:_S_COLUMNS]
            freqs.append(f * scale)
            matrices.append(
                np.array(
                    [
                        [value(s11a, s11b), value(s12a, s12b)],
                        [value(s21a, s21b), value(s22a, s22b)],
                    ],
                    dtype=complex,
                )
            )
        elif len(numbers) == _NOISE_COLUMNS:
            f, fmin_db, mag, ang_deg, rn_norm = numbers
            noise_rows.append(
                (f * scale, fmin_db, cmath.rect(mag, math.radians(ang_deg)), rn_norm * z0)
            )

    if not freqs:
        raise ValueError(
            "no two-port data rows found. A .s2p needs an option line starting '#' and rows "
            "of 'frequency S11 S21 S12 S22' (nine numbers)."
        )

    noise = None
    if noise_rows:
        noise = NoiseParameters(
            freq_hz=np.array([r[0] for r in noise_rows]),
            fmin_db=np.array([r[1] for r in noise_rows]),
            gamma_opt=np.array([r[2] for r in noise_rows]),
            rn_ohm=np.array([r[3] for r in noise_rows]),
        )

    return TwoPort(
        freq_hz=np.asarray(freqs, dtype=float),
        s=np.asarray(matrices, dtype=complex),
        z0_ohm=z0,
        noise=noise,
        source=source,
        notes=tuple(comments[:8]),
    )


def read_touchstone_2port(path: str | Path) -> TwoPort:
    """Read a ``.s2p`` from disk, recording the filename as provenance."""
    file = Path(path)
    return parse_touchstone_2port(file.read_text(), source=str(file))


# --------------------------------------------------------------------------------------
# Conversions
# --------------------------------------------------------------------------------------


def s_to_abcd(s: np.ndarray, z0_ohm: float = DEFAULT_Z0_OHM) -> np.ndarray:
    """S-matrix to ABCD. ABCD is the representation that cascades by matrix multiplication."""
    s11, s12, s21, s22 = s[0, 0], s[0, 1], s[1, 0], s[1, 1]
    if abs(s21) < 1e-300:
        raise ValueError("S21 is zero; a network with no forward transmission has no ABCD form")
    denominator = 2 * s21
    return np.array(
        [
            [
                ((1 + s11) * (1 - s22) + s12 * s21) / denominator,
                z0_ohm * ((1 + s11) * (1 + s22) - s12 * s21) / denominator,
            ],
            [
                ((1 - s11) * (1 - s22) - s12 * s21) / (denominator * z0_ohm),
                ((1 - s11) * (1 + s22) + s12 * s21) / denominator,
            ],
        ]
    )


def abcd_to_s(abcd: np.ndarray, z0_ohm: float = DEFAULT_Z0_OHM) -> np.ndarray:
    """ABCD back to an S-matrix."""
    a, b, c, d = abcd[0, 0], abcd[0, 1], abcd[1, 0], abcd[1, 1]
    denominator = a + b / z0_ohm + c * z0_ohm + d
    return np.array(
        [
            [(a + b / z0_ohm - c * z0_ohm - d) / denominator, 2 * (a * d - b * c) / denominator],
            [2 / denominator, (-a + b / z0_ohm - c * z0_ohm + d) / denominator],
        ]
    )


def s_to_z(s: np.ndarray, z0_ohm: float = DEFAULT_Z0_OHM) -> np.ndarray:
    """S-matrix to impedance matrix: Z = Z0(I + S)(I − S)⁻¹."""
    identity = np.eye(2, dtype=complex)
    return z0_ohm * (identity + s) @ np.linalg.inv(identity - s)


def z_to_s(z: np.ndarray, z0_ohm: float = DEFAULT_Z0_OHM) -> np.ndarray:
    identity = np.eye(2, dtype=complex)
    return (z / z0_ohm - identity) @ np.linalg.inv(z / z0_ohm + identity)


def s_to_y(s: np.ndarray, z0_ohm: float = DEFAULT_Z0_OHM) -> np.ndarray:
    """S-matrix to admittance matrix."""
    return np.linalg.inv(s_to_z(s, z0_ohm))


# --------------------------------------------------------------------------------------
# Reflection coefficients and the three gains
# --------------------------------------------------------------------------------------


def input_reflection(s: np.ndarray, gamma_load: complex) -> complex:
    """Γin = S11 + S12·S21·ΓL/(1 − S22·ΓL). What the source sees, given the load."""
    return complex(s[0, 0] + s[0, 1] * s[1, 0] * gamma_load / (1 - s[1, 1] * gamma_load))


def output_reflection(s: np.ndarray, gamma_source: complex) -> complex:
    """Γout = S22 + S12·S21·Γs/(1 − S11·Γs). What the load sees, given the source."""
    return complex(s[1, 1] + s[0, 1] * s[1, 0] * gamma_source / (1 - s[0, 0] * gamma_source))


def transducer_gain(
    s: np.ndarray, *, gamma_source: complex = 0j, gamma_load: complex = 0j
) -> float:
    """Power delivered to the load over power available from the source — what you get.

    The honest one for "how much signal came out". Depends on both terminations, which is why
    a datasheet gain figure means little until you say what it is connected to.
    """
    s11, s12, s21, s22 = s[0, 0], s[0, 1], s[1, 0], s[1, 1]
    denominator = (
        abs(
            (1 - s11 * gamma_source) * (1 - s22 * gamma_load)
            - s12 * s21 * gamma_source * gamma_load
        )
        ** 2
    )
    if denominator == 0:
        raise ValueError("degenerate termination; the gain expression is singular here")
    return float(
        abs(s21) ** 2 * (1 - abs(gamma_source) ** 2) * (1 - abs(gamma_load) ** 2) / denominator
    )


def available_gain(s: np.ndarray, *, gamma_source: complex = 0j) -> float:
    """Power available from the network over power available from the source.

    Depends only on the source, which is why **this** is the gain that appears in noise
    figure and cascade calculations — noise cares about what the network could deliver, not
    what a particular load happened to accept.
    """
    s11, s21 = s[0, 0], s[1, 0]
    gamma_out = output_reflection(s, gamma_source)
    denominator = abs(1 - s11 * gamma_source) ** 2 * (1 - abs(gamma_out) ** 2)
    if denominator == 0:
        raise ValueError("degenerate source match; available gain is singular here")
    return float(abs(s21) ** 2 * (1 - abs(gamma_source) ** 2) / denominator)


def operating_gain(s: np.ndarray, *, gamma_load: complex = 0j) -> float:
    """Power delivered to the load over power *input* to the network.

    Depends only on the load. Also called power gain, which is unhelpfully vague given the
    other two are also powers.
    """
    s22, s21 = s[1, 1], s[1, 0]
    gamma_in = input_reflection(s, gamma_load)
    denominator = (1 - abs(gamma_in) ** 2) * abs(1 - s22 * gamma_load) ** 2
    if denominator == 0:
        raise ValueError("degenerate load match; operating gain is singular here")
    return float(abs(s21) ** 2 * (1 - abs(gamma_load) ** 2) / denominator)


# --------------------------------------------------------------------------------------
# Cascade
# --------------------------------------------------------------------------------------


def cascade(first: TwoPort, second: TwoPort) -> TwoPort:
    """Chain two networks, first then second, via ABCD.

    Both must share a frequency grid and reference impedance — silently interpolating one
    onto the other would hide a mismatch that usually means the wrong file was loaded.

    **Noise does not cascade here.** Combining noise through a chain is Friis's job and it
    already lives in :func:`jansky_forge.sensitivity.cascade_noise_temperature_k`; the result
    of this function carries no noise parameters, and says so.
    """
    # Length first: np.allclose *raises* on mismatched shapes rather than returning False,
    # so the broadcast error would escape ahead of the message that explains it.
    if first.freq_hz.shape != second.freq_hz.shape or not np.allclose(
        first.freq_hz, second.freq_hz
    ):
        raise ValueError(
            "the two networks are on different frequency grids. Resample one deliberately "
            "rather than letting them be silently interpolated together."
        )
    if not math.isclose(first.z0_ohm, second.z0_ohm):
        raise ValueError(
            f"reference impedances differ ({first.z0_ohm} vs {second.z0_ohm} ohm); "
            "renormalize one before cascading"
        )
    combined = np.empty_like(first.s)
    for index in range(first.freq_hz.size):
        product = s_to_abcd(first.s[index], first.z0_ohm) @ s_to_abcd(
            second.s[index], second.z0_ohm
        )
        combined[index] = abcd_to_s(product, first.z0_ohm)
    return TwoPort(
        freq_hz=first.freq_hz.copy(),
        s=combined,
        z0_ohm=first.z0_ohm,
        noise=None,
        source=f"cascade({first.source or 'network'}, {second.source or 'network'})",
        notes=(
            "Cascaded S-parameters only. Noise does not combine here — use the Friis cascade "
            "in jansky_forge.sensitivity, which knows that order matters.",
        ),
    )


# --------------------------------------------------------------------------------------
# Exactly-known networks, for anchoring
# --------------------------------------------------------------------------------------


def attenuator(*, loss_db: float, freq_hz: np.ndarray, z0_ohm: float = DEFAULT_Z0_OHM) -> TwoPort:
    """A matched attenuator — the network this module is anchored against.

    Exactly analysable: S11 = S22 = 0, |S21| = 10^(−L/20), all three gains equal −L dB, two
    in series sum in dB, and its noise figure equals its loss.
    """
    if loss_db < 0:
        raise ValueError("an attenuator's loss cannot be negative")
    freq_hz = np.asarray(freq_hz, dtype=float)
    magnitude = 10 ** (-loss_db / 20.0)
    s = np.zeros((freq_hz.size, 2, 2), dtype=complex)
    s[:, 0, 1] = magnitude
    s[:, 1, 0] = magnitude
    return TwoPort(
        freq_hz=freq_hz,
        s=s,
        z0_ohm=z0_ohm,
        source=f"ideal {loss_db:g} dB attenuator",
        notes=("Ideal and matched at every frequency. A real pad is neither.",),
    )


def transmission_line(
    *,
    length_m: float,
    freq_hz: np.ndarray,
    velocity_factor: float = 0.66,
    loss_db_per_m: float = 0.0,
    z0_ohm: float = DEFAULT_Z0_OHM,
) -> TwoPort:
    """A matched length of line: magnitude from loss, phase from electrical length."""
    if not 0.0 < velocity_factor <= 1.0:
        raise ValueError("velocity factor must be in (0, 1]")
    from jansky_forge.units import C_M_S

    freq_hz = np.asarray(freq_hz, dtype=float)
    beta = 2 * np.pi * freq_hz / (C_M_S * velocity_factor)
    magnitude = 10 ** (-loss_db_per_m * abs(length_m) / 20.0)
    transmission = magnitude * np.exp(-1j * beta * length_m)
    s = np.zeros((freq_hz.size, 2, 2), dtype=complex)
    s[:, 0, 1] = transmission
    s[:, 1, 0] = transmission
    return TwoPort(
        freq_hz=freq_hz,
        s=s,
        z0_ohm=z0_ohm,
        source=f"{length_m:g} m line, vf {velocity_factor:g}",
    )


def ideal_amplifier(
    *,
    gain_db: float,
    freq_hz: np.ndarray,
    isolation_db: float = 40.0,
    z0_ohm: float = DEFAULT_Z0_OHM,
) -> TwoPort:
    """A matched, unilateral amplifier. For tests and for reasoning, never for a datasheet.

    ``isolation_db`` sets S12, which is what makes it non-reciprocal — and therefore what a
    transposed read would destroy.
    """
    freq_hz = np.asarray(freq_hz, dtype=float)
    s = np.zeros((freq_hz.size, 2, 2), dtype=complex)
    s[:, 1, 0] = 10 ** (gain_db / 20.0)
    s[:, 0, 1] = 10 ** (-abs(isolation_db) / 20.0)
    return TwoPort(
        freq_hz=freq_hz,
        s=s,
        z0_ohm=z0_ohm,
        source=f"ideal {gain_db:g} dB amplifier",
        notes=(
            "Ideal: perfectly matched at both ports and unconditionally stable by "
            "construction. A real device is neither, which is what N1 is for.",
        ),
    )


# --------------------------------------------------------------------------------------
# The link back to M4
# --------------------------------------------------------------------------------------


def as_stage(
    network: TwoPort, freq_hz: float, *, noise_temp_k: float | None = None, name: str = ""
):
    """Turn a two-port into a :class:`jansky_forge.sensitivity.Stage` for the Friis cascade.

    This is the seam between the receiver track and M4's noise budget: once a network is a
    Stage, everything the tool already knows about system temperature applies to it.

    With no ``noise_temp_k`` the network is assumed **passive at room temperature**, so its
    noise temperature is derived from its loss — which is exactly right for a cable, a pad or
    a filter, and exactly wrong for an amplifier. Pass the amplifier's noise figure instead.
    """
    from jansky_forge.sensitivity import Stage, loss_to_temperature_k

    s = network.at(freq_hz)
    gain_db = 20 * math.log10(abs(s[1, 0]))
    if noise_temp_k is None:
        if gain_db > 0:
            raise ValueError(
                f"this network has {gain_db:+.1f} dB of gain, so it is not passive and its "
                "noise temperature cannot be derived from loss. Supply noise_temp_k (from "
                "the device's noise figure)."
            )
        noise_temp_k = loss_to_temperature_k(-gain_db)
    return Stage(name or network.source or "two-port", gain_db, noise_temp_k)
