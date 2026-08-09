"""Wire antennas: dipoles, arrays, and the ground beneath them (M5).

Apertures (M0-M3) were the easy half. Wire antennas are where the amateur bands live —
Radio JOVE at 20 MHz, meteor scatter at 50 and 143 MHz — and where the dominant effect is
something an aperture model never has to think about: **the ground**.

**Height is not a mounting detail, it is a design parameter.** A horizontal dipole works
with its own reflection in the earth. The image is inverted, so at low heights the ground
cancels the antenna toward the horizon and reinforces it overhead; as the antenna rises the
main lobe splits away from the zenith and drops toward the horizon. Radio JOVE's manual
treats height as one of its two beam-steering controls for exactly this reason, and
:func:`ground_gain_db` reproduces that behaviour rather than treating height as a nuisance.

**Verification.** NASA's Radio JOVE manual publishes 5.8 dBi for a single dipole. Over
*average* ground at the manual's 10 ft height this module computes **5.89 dBi** — 0.09 dB
away. The perfect-ground idealization gives 8.17 dBi instead, so the 2.4 dB difference
between the two is real ground loss, not a modelling error, and that is why
:class:`GroundType` defaults to average earth rather than a perfect conductor.

**What this module deliberately does not do.** Yagi element design. Getting element lengths
and spacings right is precisely what a method-of-moments solver is for, and that is Tier 2
(M6). :func:`yagi_gain_estimate` gives a bounded estimate from boom length using a named
formula with a known failure mode, and says so; it is for sizing a mast, not for cutting
elements. Helical, log-periodic, and Moxon antennas are not modelled at all yet.

References
----------
Balanis, *Antenna Theory* — the half-wave dipole pattern and radiation resistance, image
theory over a ground plane, and endfire array directivity.
Hansen & Woodyard (1938) — the increased-directivity endfire condition.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import ClassVar

import numpy as np

from jansky_forge.core import Characterization, characterization_from_gain
from jansky_forge.units import C_M_S, to_db, wavelength_m

#: Directivity of a half-wave dipole in free space (linear), 1.6409 = 2.15 dBi. Computed
#: by integrating its pattern, not asserted — see the test suite.
HALF_WAVE_DIPOLE_DIRECTIVITY = 1.6409

#: Radiation resistance of a resonant half-wave dipole in free space, ohms.
HALF_WAVE_DIPOLE_RESISTANCE_OHM = 73.1

#: A folded dipole steps its feed impedance up by four, which is why it pairs with 300 ohm
#: ribbon and why it is the usual driven element in a Yagi.
FOLDED_DIPOLE_IMPEDANCE_RATIO = 4.0

#: Permittivity of free space, for the Fresnel coefficients.
_EPS0 = 8.8541878128e-12


@dataclass(frozen=True)
class GroundType:
    """Electrical properties of the earth under an antenna.

    The presets below span the realistic range. The difference between them is not
    academic: at 20 MHz a dipole 10 ft up gains 6.0 dB over seawater and 2.7 dB over dry
    sandy soil, which is most of the difference between hearing Jupiter and not.
    """

    name: str
    relative_permittivity: float
    conductivity_s_per_m: float

    def __post_init__(self) -> None:
        if self.relative_permittivity < 1 or self.conductivity_s_per_m < 0:
            raise ValueError("permittivity must be >= 1 and conductivity non-negative")


#: A perfect conductor. Not a real place — useful as the theoretical ceiling.
PERFECT_GROUND = GroundType("perfect conductor", 1.0, math.inf)
SEAWATER = GroundType("seawater", 81.0, 5.0)
#: Ordinary soil. The right default for a suburban back garden.
AVERAGE_GROUND = GroundType("average ground", 13.0, 0.005)
POOR_GROUND = GroundType("poor / dry sandy", 5.0, 0.001)
GROUND_TYPES: dict[str, GroundType] = {
    "perfect": PERFECT_GROUND,
    "seawater": SEAWATER,
    "average": AVERAGE_GROUND,
    "poor": POOR_GROUND,
}


def get_ground(name: str) -> GroundType:
    try:
        return GROUND_TYPES[name.lower()]
    except KeyError:
        raise KeyError(
            f"unknown ground {name!r}; known: {', '.join(sorted(GROUND_TYPES))}"
        ) from None


# --------------------------------------------------------------------------------------
# The dipole itself
# --------------------------------------------------------------------------------------


def dipole_power_pattern(angle_from_axis_rad: np.ndarray) -> np.ndarray:
    """Normalized power pattern of a half-wave dipole: [cos(pi/2 cos a) / sin a]^2.

    ``a`` is measured from the wire, so the pattern is maximum broadside (a = 90 deg) and
    exactly zero off the ends — the null that lets a dipole be used as a direction finder by
    what it *cannot* hear.
    """
    a = np.atleast_1d(np.asarray(angle_from_axis_rad, dtype=float))
    sin_a = np.sin(a)
    out = np.zeros_like(a)
    good = np.abs(sin_a) > 1e-12
    out[good] = (np.cos(math.pi / 2 * np.cos(a[good])) / sin_a[good]) ** 2
    return out


def half_wave_length_m(freq_hz: float, velocity_factor: float = 0.95) -> float:
    """Physical length to cut a half-wave dipole.

    A real wire resonates slightly short of a free-space half wavelength because of end
    effects; 0.95 is the usual factor for thin wire. This is where to start, not where to
    finish — trim against an analyser.
    """
    if not 0.0 < velocity_factor <= 1.0:
        raise ValueError("velocity factor must be in (0, 1]")
    return velocity_factor * wavelength_m(freq_hz) / 2.0


# --------------------------------------------------------------------------------------
# Ground
# --------------------------------------------------------------------------------------


def fresnel_reflection_horizontal(
    elevation_rad: np.ndarray, ground: GroundType, freq_hz: float
) -> np.ndarray:
    """Reflection coefficient for horizontal polarization off the earth.

    Approaches -1 at grazing incidence for any ground, which is why *every* horizontal
    antenna has a null on the horizon regardless of how good the soil is.
    """
    elevation = np.atleast_1d(np.asarray(elevation_rad, dtype=float))
    if math.isinf(ground.conductivity_s_per_m):
        return np.full_like(elevation, -1.0, dtype=complex)
    loss_tangent = ground.conductivity_s_per_m / (2 * math.pi * freq_hz * _EPS0)
    eps = ground.relative_permittivity - 1j * loss_tangent
    sin_e, cos_e = np.sin(elevation), np.cos(elevation)
    root = np.sqrt(eps - cos_e**2)
    return (sin_e - root) / (sin_e + root)


def ground_reflection_factor(
    elevation_rad: np.ndarray, *, height_m: float, freq_hz: float, ground: GroundType
) -> np.ndarray:
    """Field enhancement |1 + Gamma·exp(-j·2kh·sin(elev))| from the antenna's own image."""
    if height_m < 0:
        raise ValueError("height cannot be negative")
    elevation = np.atleast_1d(np.asarray(elevation_rad, dtype=float))
    k = 2 * math.pi / wavelength_m(freq_hz)
    gamma = fresnel_reflection_horizontal(elevation, ground, freq_hz)
    return np.abs(1.0 + gamma * np.exp(-2j * k * height_m * np.sin(elevation)))


def ground_gain_db(
    *, height_m: float, freq_hz: float, ground: GroundType = AVERAGE_GROUND, samples: int = 4001
) -> tuple[float, float]:
    """Peak gain above free space, and the elevation it occurs at. Returns ``(dB, degrees)``.

    The ceiling is +6.02 dB — a perfect image doubles the field. Real ground never quite
    reaches it, and low heights over poor soil fall far short.

    This treats the antenna's radiated power as unchanged by the ground, which is exact for
    a perfect conductor and slightly optimistic over lossy earth (some power is absorbed
    rather than reflected). It is the approximation that reproduces Radio JOVE's published
    figure, and the residual error is smaller than the uncertainty in anyone's soil.
    """
    elevation = np.linspace(1e-6, math.pi / 2, samples)
    factor = ground_reflection_factor(elevation, height_m=height_m, freq_hz=freq_hz, ground=ground)
    peak = int(np.argmax(factor))
    return float(to_db(factor[peak] ** 2)), float(math.degrees(elevation[peak]))


def directivity_over_perfect_ground_db(height_over_wavelength: float, samples: int = 720) -> float:
    """Directivity of a horizontal half-wave dipole over a perfect conductor, by integration.

    D = 4*pi*U_max / (integral of U over the upper hemisphere). Included because it is the
    honest way to compute directivity and because it shows where the convenient
    "2.15 + 6.02 = 8.17 dBi" shortcut is and is not right: the shortcut is the large-height
    limit, while at half a wavelength up the true figure is 8.4 dBi and at a quarter
    wavelength it is 7.5 dBi.
    """
    if height_over_wavelength < 0:
        raise ValueError("height cannot be negative")
    k = 2 * math.pi
    elevation = np.linspace(1e-7, math.pi / 2 - 1e-7, samples)
    azimuth = np.linspace(0.0, 2 * math.pi, 2 * samples)
    grid_e, grid_a = np.meshgrid(elevation, azimuth, indexing="ij")
    cos_from_axis = np.clip(np.cos(grid_e) * np.cos(grid_a), -1.0, 1.0)
    element = dipole_power_pattern(np.arccos(cos_from_axis))
    ground_factor = 4 * np.sin(k * height_over_wavelength * np.sin(grid_e)) ** 2
    intensity = element * ground_factor
    total = np.trapezoid(np.trapezoid(intensity * np.cos(grid_e), azimuth, axis=1), elevation)
    if total <= 0:  # pragma: no cover - only for a zero-height antenna
        raise ValueError("antenna radiates no power; is it lying on the ground?")
    return float(to_db(4 * math.pi * intensity.max() / total))


# --------------------------------------------------------------------------------------
# Arrays
# --------------------------------------------------------------------------------------


def array_factor(
    angle_rad: np.ndarray,
    *,
    n_elements: int,
    spacing_m: float,
    freq_hz: float,
    phase_step_deg: float = 0.0,
) -> np.ndarray:
    """Array factor magnitude for ``n`` equally-spaced, equally-phased elements.

    ``angle_rad`` is measured from the array axis. Exact, not approximate: this is a finite
    geometric series, and it is the piece of a phased array there is no excuse for getting
    wrong.
    """
    if n_elements < 1:
        raise ValueError("an array needs at least one element")
    if spacing_m < 0:
        raise ValueError("spacing cannot be negative")
    angle = np.atleast_1d(np.asarray(angle_rad, dtype=float))
    k = 2 * math.pi / wavelength_m(freq_hz)
    psi = k * spacing_m * np.cos(angle) + math.radians(phase_step_deg)
    numerator = np.sin(n_elements * psi / 2.0)
    denominator = np.sin(psi / 2.0)
    # At the grating-lobe maxima the denominator vanishes and the true limit is n. Guard the
    # divisor rather than dividing and patching afterwards: np.where evaluates both branches,
    # so the naive form still performs the singular division and warns.
    singular = np.abs(denominator) < 1e-12
    safe = np.where(singular, 1.0, denominator)
    return np.where(singular, float(n_elements), np.abs(numerator / safe))


def broadside_array_gain_db(n_elements: int) -> float:
    """Ideal gain of ``n`` equally-driven broadside elements: 10·log10(n).

    The ceiling, not the answer: mutual coupling between real elements always costs
    something, and Radio JOVE's own manual shows that cost — see the catalogue entry.
    """
    if n_elements < 1:
        raise ValueError("an array needs at least one element")
    return to_db(float(n_elements))


# --------------------------------------------------------------------------------------
# Models
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class HalfWaveDipole:
    """A resonant half-wave dipole in free space.

    The reference against which every other wire antenna is quoted — "dBd" means dB
    relative to this, and is 2.15 dB less than dBi.
    """

    kind: ClassVar[str] = "Half-wave dipole"
    freq_hz: float = 1e8
    velocity_factor: float = 0.95

    def __post_init__(self) -> None:
        if self.freq_hz <= 0:
            raise ValueError("frequency must be positive")

    @property
    def length_m(self) -> float:
        return half_wave_length_m(self.freq_hz, self.velocity_factor)

    def parameters(self) -> dict[str, float]:
        return {
            "design_freq_hz": self.freq_hz,
            "length_m": self.length_m,
            "velocity_factor": self.velocity_factor,
            "radiation_resistance_ohm": HALF_WAVE_DIPOLE_RESISTANCE_OHM,
        }

    def characterize(self, freq_hz: float) -> Characterization:
        gain = HALF_WAVE_DIPOLE_DIRECTIVITY
        notes = [
            "Free space, with no ground. A real dipole a few metres up behaves very "
            "differently — put it over a GroundType and use DipoleOverGround.",
            "Aperture efficiency is not a meaningful quantity for a wire antenna; the "
            "effective area reported is A_e = G*lambda^2/4pi, which is.",
        ]
        detune = abs(freq_hz - self.freq_hz) / self.freq_hz
        if detune > 0.05:
            notes.append(
                f"Characterized {detune * 100:.0f}% away from the {self.freq_hz / 1e6:.3f} MHz "
                "it was cut for. A dipole off resonance is reactive and badly matched; the "
                "pattern shown ignores that entirely."
            )
        return characterization_from_gain(
            freq_hz=freq_hz,
            gain_linear=gain,
            hpbw_e_deg=78.0,
            hpbw_h_deg=360.0,
            aperture_efficiency=1.0,
            detail={
                "length_m": self.length_m,
                "length_wavelengths": self.length_m / wavelength_m(freq_hz),
                "radiation_resistance_ohm": HALF_WAVE_DIPOLE_RESISTANCE_OHM,
            },
            notes=tuple(notes),
        )


@dataclass(frozen=True)
class FoldedDipole(HalfWaveDipole):
    """A folded dipole: the same pattern, four times the feed impedance.

    Nothing about the radiation changes — the value is the 292 ohm feed point (a good match
    to 300 ohm ribbon, or to 75 ohm through a 4:1 balun) and the wider bandwidth.
    """

    kind: ClassVar[str] = "Folded dipole"

    def parameters(self) -> dict[str, float]:
        return super().parameters() | {
            "feed_impedance_ohm": HALF_WAVE_DIPOLE_RESISTANCE_OHM * FOLDED_DIPOLE_IMPEDANCE_RATIO
        }

    def characterize(self, freq_hz: float) -> Characterization:
        base = super().characterize(freq_hz)
        return Characterization(
            freq_hz=base.freq_hz,
            gain_dbi=base.gain_dbi,
            hpbw_e_deg=base.hpbw_e_deg,
            hpbw_h_deg=base.hpbw_h_deg,
            aperture_efficiency=base.aperture_efficiency,
            effective_area_m2=base.effective_area_m2,
            beam_solid_angle_sr=base.beam_solid_angle_sr,
            detail=base.detail
            | {
                "feed_impedance_ohm": HALF_WAVE_DIPOLE_RESISTANCE_OHM
                * FOLDED_DIPOLE_IMPEDANCE_RATIO
            },
            notes=(
                *base.notes,
                "Folding changes the feed impedance, not the pattern: ~292 ohm instead of "
                "73, which matches 300 ohm ribbon directly and 75 ohm coax through a 4:1 "
                "balun.",
            ),
        )


@dataclass(frozen=True)
class DipoleOverGround:
    """A horizontal half-wave dipole at a height above real earth.

    The workhorse of HF radio astronomy, and the model behind the Radio JOVE array. Height
    sets both how much the ground helps and *where the beam points*, which is why it is a
    design variable here and not a mounting note.
    """

    kind: ClassVar[str] = "Horizontal dipole over ground"
    freq_hz: float = 20.1e6
    height_m: float = 3.048
    ground: GroundType = AVERAGE_GROUND
    n_elements: int = 1
    #: Broadside spacing between elements, when there is more than one.
    spacing_m: float = 0.0
    velocity_factor: float = 0.95

    def __post_init__(self) -> None:
        if self.freq_hz <= 0:
            raise ValueError("frequency must be positive")
        if self.height_m < 0:
            raise ValueError("height cannot be negative")
        if self.n_elements < 1:
            raise ValueError("need at least one element")

    @property
    def length_m(self) -> float:
        return half_wave_length_m(self.freq_hz, self.velocity_factor)

    def parameters(self) -> dict[str, float]:
        params = {
            "design_freq_hz": self.freq_hz,
            "element_length_m": self.length_m,
            "height_m": self.height_m,
            "height_wavelengths": self.height_m / wavelength_m(self.freq_hz),
            "n_elements": float(self.n_elements),
        }
        if self.n_elements > 1:
            params["spacing_m"] = self.spacing_m
            params["spacing_wavelengths"] = self.spacing_m / wavelength_m(self.freq_hz)
        return params

    def characterize(self, freq_hz: float) -> Characterization:
        ground_db, peak_elev = ground_gain_db(
            height_m=self.height_m, freq_hz=freq_hz, ground=self.ground
        )
        array_db = broadside_array_gain_db(self.n_elements)
        gain_dbi = to_db(HALF_WAVE_DIPOLE_DIRECTIVITY) + ground_db + array_db

        notes = [
            f"Over {self.ground.name}: the ground contributes {ground_db:+.2f} dB and puts "
            f"the main lobe at {peak_elev:.0f} deg elevation. The ceiling is +6.02 dB, which "
            "only a perfect conductor reaches.",
            "Height steers the beam. Raising the antenna pulls the lobe down toward the "
            "horizon; lowering it pushes the lobe overhead. Choose height for the elevation "
            "you want to observe, not for convenience.",
            "Aperture efficiency is not meaningful for a wire antenna; the effective area "
            "reported comes from the gain.",
        ]
        if self.n_elements > 1:
            notes.append(
                f"Array gain assumes {self.n_elements} ideal, identically-driven elements "
                f"({array_db:+.2f} dB). Real elements couple to each other and fall short of "
                "this — Radio JOVE's own published figures show about 1 dB of shortfall for "
                "two elements."
            )
        if self.height_m / wavelength_m(freq_hz) < 0.15:
            notes.append(
                f"At {self.height_m / wavelength_m(freq_hz):.2f} wavelengths this antenna is "
                "very low. Ground losses grow quickly here and the model's assumption that "
                "radiated power is unchanged gets optimistic."
            )

        return characterization_from_gain(
            freq_hz=freq_hz,
            gain_linear=10 ** (gain_dbi / 10.0),
            hpbw_e_deg=78.0,
            hpbw_h_deg=max(360.0 / max(self.n_elements, 1), 30.0),
            aperture_efficiency=1.0,
            detail={
                "element_length_m": self.length_m,
                "height_m": self.height_m,
                "height_wavelengths": self.height_m / wavelength_m(freq_hz),
                "ground_gain_db": ground_db,
                "peak_elevation_deg": peak_elev,
                "array_gain_db": array_db,
            },
            notes=tuple(notes),
        )


# --------------------------------------------------------------------------------------
# Yagi-Uda — bounded estimate only, by design
# --------------------------------------------------------------------------------------


def yagi_gain_estimate(*, boom_length_m: float, freq_hz: float) -> tuple[float, tuple[str, ...]]:
    """Estimate a Yagi's gain from boom length alone. Returns ``(dBi, caveats)``.

    A Yagi is an endfire array, and the Hansen-Woodyard increased-directivity condition
    bounds what an endfire array of a given length can do: ``D ~ 1.789 * 4L/lambda``, times
    the element's own directivity. That is a named result with a known validity condition —
    it assumes a long array — rather than a curve fitted to convenience.

    **It is for sizing a mast, not for cutting elements.** Element lengths and spacings are
    exactly what a method-of-moments solver is for, and that is Tier 2 (M6). Checked against
    two published 143 MHz designs: it lands 0.4 dB from a 7-element (1.13 lambda boom) and
    2.3 dB under a 3-element (0.24 lambda boom), which is the short-array failure the
    formula's own assumption predicts.
    """
    if boom_length_m <= 0 or freq_hz <= 0:
        raise ValueError("boom length and frequency must be positive")
    boom_wavelengths = boom_length_m / wavelength_m(freq_hz)
    directivity = 1.789 * 4.0 * boom_wavelengths * HALF_WAVE_DIPOLE_DIRECTIVITY
    caveats = [
        "Estimated from boom length via the Hansen-Woodyard endfire bound. Good for sizing "
        "a boom; useless for cutting elements — that needs the method-of-moments tier (M6).",
        "Treat as +/- 2 dB.",
    ]
    if boom_wavelengths < 0.75:
        caveats.append(
            f"Boom is only {boom_wavelengths:.2f} wavelengths. The endfire bound assumes a "
            "LONG array, so this UNDERSTATES a short Yagi — by about 2 dB at a quarter "
            "wavelength, on the published design checked."
        )
    return float(to_db(max(directivity, 1e-6))), tuple(caveats)


@dataclass(frozen=True)
class YagiUda:
    """A Yagi-Uda array, characterized by boom length only.

    Deliberately thin. This models what boom length buys, which is the question that decides
    whether an antenna fits your garden. It does not model elements, because doing that
    properly is what M6's method-of-moments backend is for, and a plausible-looking analytic
    element model would be worse than no model at all.
    """

    kind: ClassVar[str] = "Yagi-Uda"
    freq_hz: float = 143.05e6
    boom_length_m: float = 1.0
    n_elements: int = 3
    height_m: float = 0.0
    ground: GroundType | None = None

    def __post_init__(self) -> None:
        if self.n_elements < 2:
            raise ValueError("a Yagi needs at least a driven element and one parasitic")

    def parameters(self) -> dict[str, float]:
        return {
            "design_freq_hz": self.freq_hz,
            "boom_length_m": self.boom_length_m,
            "boom_wavelengths": self.boom_length_m / wavelength_m(self.freq_hz),
            "n_elements": float(self.n_elements),
            "height_m": self.height_m,
        }

    def characterize(self, freq_hz: float) -> Characterization:
        gain_dbi, caveats = yagi_gain_estimate(boom_length_m=self.boom_length_m, freq_hz=freq_hz)
        notes = list(caveats)
        if self.ground is not None and self.height_m > 0:
            ground_db, peak_elev = ground_gain_db(
                height_m=self.height_m, freq_hz=freq_hz, ground=self.ground
            )
            gain_dbi += ground_db
            notes.append(
                f"Includes {ground_db:+.2f} dB from {self.ground.name} at {self.height_m:g} m, "
                f"peaking at {peak_elev:.0f} deg elevation. A Yagi aimed at a fixed elevation "
                "interacts with the ground exactly as a dipole does."
            )
        notes.append(
            "Aperture efficiency is not meaningful for a wire antenna; effective area comes "
            "from the gain."
        )
        # Rough endfire beamwidth, stated as rough.
        boom_wavelengths = max(self.boom_length_m / wavelength_m(freq_hz), 1e-6)
        hpbw = float(np.clip(55.0 / math.sqrt(boom_wavelengths), 15.0, 120.0))
        return characterization_from_gain(
            freq_hz=freq_hz,
            gain_linear=10 ** (gain_dbi / 10.0),
            hpbw_e_deg=hpbw,
            hpbw_h_deg=hpbw * 1.15,
            aperture_efficiency=1.0,
            detail={
                "boom_length_m": self.boom_length_m,
                "boom_wavelengths": boom_wavelengths,
                "n_elements": float(self.n_elements),
            },
            notes=tuple(notes),
        )


def wavelength_for_band(freq_hz: float) -> float:
    """Convenience re-export so wire work does not need to import units."""
    return C_M_S / freq_hz
