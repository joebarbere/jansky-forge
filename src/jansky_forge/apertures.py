"""Aperture antennas: parabolic dishes and horns (Tier-1 closed-form models).

Why closed-form is the right answer here rather than a compromise: a 21 cm dish or horn
is an *aperture* antenna many wavelengths across, exactly the regime where textbook
aperture theory is accurate to a few tenths of a dB — and where a full-wave solver would
spend minutes to tell you what these formulas tell you in microseconds. The interactivity
this package promises comes from that physics choice.

Validity is stated, not assumed: each model attaches ``notes`` to its
:class:`~jansky_forge.core.Characterization` describing where it stops being trustworthy
(horns below a few wavelengths, dishes with severe blockage, non-optimum flare angles).

References
----------
Balanis, *Antenna Theory: Analysis and Design*, 4th ed. — horn design (ch. 13), aperture
efficiency, the optimum-horn beamwidth approximations.
Kraus, *Radio Astronomy*, 2nd ed. — beam solid angle, effective aperture, the Ruze
formula for surface tolerance.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import ClassVar

from jansky_forge import horns
from jansky_forge.core import Characterization, characterization_from_gain
from jansky_forge.horns import OPTIMUM_PHASE_DEVIATION_E, OPTIMUM_PHASE_DEVIATION_H
from jansky_forge.units import C_M_S

#: Beamwidth constant k in HPBW = k·λ/D (degrees) for a parabolic dish. The textbook
#: range is 58 (uniform illumination) to ~72 (heavy edge taper); 70 is the value the
#: radio-astronomy literature and the amateur community quote for a typically-tapered
#: dish, and it is what this package defaults to. Override per design if you know better.
DISH_BEAM_CONSTANT_DEG = 70.0

#: Aperture efficiency of an *optimum* (maximum-gain-for-its-length) horn. Both the
#: pyramidal and conical optimum designs land near this because their aperture phase
#: error is, by construction, the same fraction of a wavelength. Balanis ch. 13.
OPTIMUM_HORN_EFFICIENCY = 0.51

#: Optimum-pyramidal-horn half-power beamwidth constants, HPBW = k·λ/aperture (degrees).
PYRAMIDAL_HPBW_E_CONST = 54.0
PYRAMIDAL_HPBW_H_CONST = 78.0

#: Optimum-conical-horn beamwidth constants against aperture *diameter*.
CONICAL_HPBW_E_CONST = 60.0
CONICAL_HPBW_H_CONST = 70.0


def ruze_efficiency(surface_rms_m: float, wavelength_metres: float) -> float:
    """Ruze surface-tolerance efficiency: η_s = exp(−(4πσ/λ)²).

    The reason a mesh or hand-formed dish that works beautifully at 1420 MHz is useless
    at 10 GHz. σ is the RMS deviation of the real surface from a true paraboloid.

    >>> round(ruze_efficiency(0.002, 0.211), 3)   # 2 mm RMS at 21 cm — negligible
    0.986
    """
    if surface_rms_m < 0:
        raise ValueError(f"surface RMS cannot be negative, got {surface_rms_m}")
    return math.exp(-((4.0 * math.pi * surface_rms_m / wavelength_metres) ** 2))


def subtended_half_angle_deg(f_over_d: float) -> float:
    """Half-angle a prime-focus dish subtends at its feed: θ₀ = 2·arctan(1/(4·f/D)).

    The number that decides which feed belongs on a dish — a feed must illuminate this
    angle and no more, or you trade spillover against illumination taper. The full
    feed-matching treatment arrives at M3; this is the geometry it will build on.
    """
    if f_over_d <= 0:
        raise ValueError(f"f/D must be positive, got {f_over_d}")
    return math.degrees(2.0 * math.atan(1.0 / (4.0 * f_over_d)))


@dataclass(frozen=True)
class ParabolicDish:
    """A circular parabolic reflector, prime-focus or offset-fed.

    Efficiency is kept as *separate named factors* rather than one lumped number,
    because that is how a builder can act on it: a bad taper is a feed-choice problem, a
    bad surface is a fabrication problem, and blockage is a strut-and-feed-size problem.
    Their product, times Ruze, is the aperture efficiency reported.

    ``surface_rms_mm`` is in millimetres — the unit a builder measures with — and is the
    only non-SI field in the package, deliberately.
    """

    kind: ClassVar[str] = "Parabolic dish"
    diameter_m: float = 1.0
    f_over_d: float = 0.4
    surface_rms_mm: float = 1.0
    #: Illumination (taper) efficiency: how uniformly the feed lights the aperture.
    illumination_efficiency: float = 0.80
    #: Spillover: the fraction of feed power that lands on the dish rather than the ground.
    spillover_efficiency: float = 0.85
    #: Aperture blockage by the feed and its supports (1.0 = unblocked, e.g. offset feed).
    blockage_efficiency: float = 0.95
    #: Ohmic/mismatch losses lumped: 1.0 unless you have a measured number.
    other_efficiency: float = 1.0
    beam_constant_deg: float = DISH_BEAM_CONSTANT_DEG

    def __post_init__(self) -> None:
        if self.diameter_m <= 0:
            raise ValueError(f"diameter must be positive, got {self.diameter_m}")
        for name in (
            "illumination_efficiency",
            "spillover_efficiency",
            "blockage_efficiency",
            "other_efficiency",
        ):
            value = getattr(self, name)
            if not 0.0 < value <= 1.0:
                raise ValueError(f"{name} must be in (0, 1], got {value}")

    @property
    def focal_length_m(self) -> float:
        return self.f_over_d * self.diameter_m

    @property
    def physical_area_m2(self) -> float:
        return math.pi * (self.diameter_m / 2.0) ** 2

    def parameters(self) -> dict[str, float]:
        return {
            "diameter_m": self.diameter_m,
            "f_over_d": self.f_over_d,
            "focal_length_m": self.focal_length_m,
            "surface_rms_mm": self.surface_rms_mm,
            "illumination_efficiency": self.illumination_efficiency,
            "spillover_efficiency": self.spillover_efficiency,
            "blockage_efficiency": self.blockage_efficiency,
            "other_efficiency": self.other_efficiency,
        }

    def characterize(self, freq_hz: float) -> Characterization:
        lam = 299_792_458.0 / freq_hz
        eta_surface = ruze_efficiency(self.surface_rms_mm / 1000.0, lam)
        eta = (
            self.illumination_efficiency
            * self.spillover_efficiency
            * self.blockage_efficiency
            * self.other_efficiency
            * eta_surface
        )
        gain_linear = eta * (math.pi * self.diameter_m / lam) ** 2
        hpbw = self.beam_constant_deg * lam / self.diameter_m

        notes = [
            f"Beamwidth uses HPBW = {self.beam_constant_deg:g}·λ/D; the textbook range is 58–72 "
            "depending on edge taper, so treat this as ±10%.",
            "Aperture efficiency is a product of assumed factors, not a measurement — "
            "M7/M8 replace it with one derived from a Y-factor or transit measurement.",
        ]
        if self.diameter_m / lam < 5.0:
            notes.append(
                f"Dish is only {self.diameter_m / lam:.1f}λ across; aperture theory degrades "
                "below ~5λ and this gain is optimistic."
            )
        if eta_surface < 0.7:
            notes.append(
                f"Ruze surface loss is severe ({10 * math.log10(eta_surface):.1f} dB) — "
                "the surface, not the diameter, is the limiting term at this frequency."
            )

        return characterization_from_gain(
            freq_hz=freq_hz,
            gain_linear=gain_linear,
            hpbw_e_deg=hpbw,
            hpbw_h_deg=hpbw,
            aperture_efficiency=eta,
            detail={
                "focal_length_m": self.focal_length_m,
                "physical_area_m2": self.physical_area_m2,
                "ruze_efficiency": eta_surface,
                "ruze_loss_db": -10.0 * math.log10(eta_surface),
                "subtended_half_angle_deg": subtended_half_angle_deg(self.f_over_d),
                "diameter_wavelengths": self.diameter_m / lam,
            },
            notes=tuple(notes),
        )


@dataclass(frozen=True)
class PyramidalHorn:
    """A rectangular pyramidal horn — the classic build-it-from-sheet-metal 21 cm antenna.

    ``aperture_a_m`` is the H-plane (wide) dimension, ``aperture_b_m`` the E-plane.
    ``axial_length_m`` is the horn's physical length from the waveguide face to the
    aperture — Balanis' p_e/p_h — which is what a builder measures.

    Given the waveguide dimensions, gain and beamwidths come from the exact
    phase-error physics in :mod:`jansky_forge.horns`: no assumption that the flare is
    near-optimum, so the model correctly reports that an over-flared horn *loses* gain.
    Without them (a source that never published its throat) it falls back to M0's
    optimum-flare estimate and says so in the notes.

    ``axial_length_h_m`` exists to check published designs that quote two different flare
    lengths. A real pyramidal horn has one; see :func:`jansky_forge.horns.realizability`.
    """

    kind: ClassVar[str] = "Pyramidal horn"
    aperture_a_m: float = 0.5
    aperture_b_m: float = 0.4
    axial_length_m: float = 0.5
    #: Feeding waveguide's internal broad and narrow walls (0 = not published).
    waveguide_a_m: float = 0.0
    waveguide_b_m: float = 0.0
    #: Separate H-plane axial length, only for checking non-realizable published designs.
    #: 0 means "the same as the E-plane", which is the physical case.
    axial_length_h_m: float = 0.0
    #: Fallback efficiency, used only when the waveguide dimensions are unknown.
    aperture_efficiency: float = OPTIMUM_HORN_EFFICIENCY

    def __post_init__(self) -> None:
        if self.aperture_a_m <= 0 or self.aperture_b_m <= 0:
            raise ValueError("horn aperture dimensions must be positive")
        if not 0.0 < self.aperture_efficiency <= 1.0:
            raise ValueError(
                f"aperture efficiency must be in (0, 1], got {self.aperture_efficiency}"
            )

    @property
    def physical_area_m2(self) -> float:
        return self.aperture_a_m * self.aperture_b_m

    @property
    def _axial_h_m(self) -> float:
        return self.axial_length_h_m or self.axial_length_m

    @property
    def _exact(self) -> bool:
        """Is there enough geometry for the phase-error model?"""
        return (
            self.waveguide_a_m > 0
            and self.waveguide_b_m > 0
            and self.aperture_a_m > self.waveguide_a_m
            and self.aperture_b_m > self.waveguide_b_m
            and self.axial_length_m > 0
        )

    def parameters(self) -> dict[str, float]:
        params = {
            "aperture_a_m": self.aperture_a_m,
            "aperture_b_m": self.aperture_b_m,
            "axial_length_m": self.axial_length_m,
            "waveguide_a_m": self.waveguide_a_m,
            "waveguide_b_m": self.waveguide_b_m,
        }
        if self.axial_length_h_m:
            params["axial_length_h_m"] = self.axial_length_h_m
        if not self._exact:
            params["aperture_efficiency"] = self.aperture_efficiency
        return params

    def characterize(self, freq_hz: float) -> Characterization:
        lam = C_M_S / freq_hz
        if not self._exact:
            return self._characterize_approximate(freq_hz, lam)

        rho1 = horns.apex_distance_e(
            aperture_b1_m=self.aperture_b_m,
            waveguide_b_m=self.waveguide_b_m,
            axial_m=self.axial_length_m,
        )
        rho2 = horns.apex_distance_h(
            aperture_a1_m=self.aperture_a_m,
            waveguide_a_m=self.waveguide_a_m,
            axial_m=self._axial_h_m,
        )
        gain = horns.pyramidal_gain(
            waveguide_a_m=self.waveguide_a_m,
            waveguide_b_m=self.waveguide_b_m,
            aperture_a1_m=self.aperture_a_m,
            aperture_b1_m=self.aperture_b_m,
            rho1_m=rho1,
            rho2_m=rho2,
            wavelength_metres=lam,
        )
        hpbw_e, hpbw_h = horns.pattern_beamwidths(
            aperture_a1_m=self.aperture_a_m,
            aperture_b1_m=self.aperture_b_m,
            rho1_m=rho1,
            rho2_m=rho2,
            freq_hz=freq_hz,
        )
        s = horns.phase_deviation_e(
            aperture_b1_m=self.aperture_b_m, rho1_m=rho1, wavelength_metres=lam
        )
        t = horns.phase_deviation_h(
            aperture_a1_m=self.aperture_a_m, rho2_m=rho2, wavelength_metres=lam
        )
        eta = gain / (4.0 * math.pi * self.physical_area_m2 / (lam * lam))

        notes = [
            "Gain and beamwidths come from the exact aperture-phase-error model "
            "(Balanis ch. 13 Fresnel-integral form), not an assumed efficiency.",
        ]
        if s > 1.5 * OPTIMUM_PHASE_DEVIATION_E or t > 1.5 * OPTIMUM_PHASE_DEVIATION_H:
            notes.append(
                f"Over-flared for its length (phase deviation s={s:.2f}, t={t:.2f} against "
                f"optima {OPTIMUM_PHASE_DEVIATION_E:g}/{OPTIMUM_PHASE_DEVIATION_H:g}): a "
                "shorter aperture or a longer horn would gain MORE, not less."
            )
        elif s < 0.5 * OPTIMUM_PHASE_DEVIATION_E and t < 0.5 * OPTIMUM_PHASE_DEVIATION_H:
            notes.append(
                f"Under-flared (s={s:.2f}, t={t:.2f}): this horn is longer than it needs to "
                "be for its aperture — widening it would gain more for the same length."
            )
        check = horns.realizability(axial_e_m=self.axial_length_m, axial_h_m=self._axial_h_m)
        if not check.realizable:
            notes.append(check.message)

        return characterization_from_gain(
            freq_hz=freq_hz,
            gain_linear=gain,
            hpbw_e_deg=hpbw_e,
            hpbw_h_deg=hpbw_h,
            aperture_efficiency=eta,
            detail={
                "physical_area_m2": self.physical_area_m2,
                "rho1_axial_m": rho1,
                "rho2_axial_m": rho2,
                "slant_e_m": horns.slant_e(rho1_m=rho1, aperture_b1_m=self.aperture_b_m),
                "slant_h_m": horns.slant_h(rho2_m=rho2, aperture_a1_m=self.aperture_a_m),
                "phase_deviation_e": s,
                "phase_deviation_h": t,
                "aperture_a_wavelengths": self.aperture_a_m / lam,
                "aperture_b_wavelengths": self.aperture_b_m / lam,
            },
            notes=tuple(notes),
        )

    def _characterize_approximate(self, freq_hz: float, lam: float) -> Characterization:
        """M0's optimum-flare estimate, for geometry too incomplete for the real model."""
        gain_linear = self.aperture_efficiency * 4.0 * math.pi * self.physical_area_m2 / (lam * lam)
        notes = [
            "APPROXIMATE: the waveguide dimensions are unknown, so the aperture phase error "
            f"cannot be computed. This assumes near-optimum flare ({self.aperture_efficiency:g} "
            "aperture efficiency) and will overstate the gain of an over-flared horn.",
        ]
        smallest = min(self.aperture_a_m, self.aperture_b_m) / lam
        if smallest < 1.0:
            notes.append(
                f"Smallest aperture dimension is {smallest:.2f} wavelengths — below ~1 the "
                "aperture approximation is unreliable and this gain should not be trusted."
            )
        return characterization_from_gain(
            freq_hz=freq_hz,
            gain_linear=gain_linear,
            hpbw_e_deg=PYRAMIDAL_HPBW_E_CONST * lam / self.aperture_b_m,
            hpbw_h_deg=PYRAMIDAL_HPBW_H_CONST * lam / self.aperture_a_m,
            aperture_efficiency=self.aperture_efficiency,
            detail={
                "physical_area_m2": self.physical_area_m2,
                "aperture_a_wavelengths": self.aperture_a_m / lam,
                "aperture_b_wavelengths": self.aperture_b_m / lam,
                "axial_length_m": self.axial_length_m,
            },
            notes=tuple(notes),
        )


@dataclass(frozen=True)
class ConicalHorn:
    """A circular conical horn — the natural feed for a prime-focus dish.

    Gain uses Balanis' loss-figure treatment (13-59), which reduces the aperture gain by an
    empirical phase-error loss fitted to King's 1950 measurements. Unlike the pyramidal
    case there is no tractable closed form; Balanis explicitly declines the rigorous
    spherical-mode analysis as too involved, and this is the standard engineering route.

    Beamwidths remain the optimum-flare rules of thumb — the exact conical pattern is not
    yet implemented, and the notes say so rather than implying the two are equally solid.
    """

    kind: ClassVar[str] = "Conical horn"
    aperture_diameter_m: float = 0.3
    axial_length_m: float = 0.3
    #: Feeding circular waveguide diameter (0 = not published; treated as a point apex,
    #: which understates the slant and so gives a conservative gain).
    throat_diameter_m: float = 0.0

    def __post_init__(self) -> None:
        if self.aperture_diameter_m <= 0:
            raise ValueError("aperture diameter must be positive")
        if self.axial_length_m <= 0:
            raise ValueError("axial length must be positive")
        if 0 < self.aperture_diameter_m <= self.throat_diameter_m:
            raise ValueError("throat diameter must be smaller than the aperture")

    @property
    def physical_area_m2(self) -> float:
        return math.pi * (self.aperture_diameter_m / 2.0) ** 2

    @property
    def slant_m(self) -> float:
        return horns.conical_slant_m(
            aperture_diameter_m=self.aperture_diameter_m,
            axial_length_m=self.axial_length_m,
            throat_diameter_m=self.throat_diameter_m,
        )

    def parameters(self) -> dict[str, float]:
        return {
            "aperture_diameter_m": self.aperture_diameter_m,
            "axial_length_m": self.axial_length_m,
            "throat_diameter_m": self.throat_diameter_m,
            "slant_m": self.slant_m,
        }

    def characterize(self, freq_hz: float) -> Characterization:
        lam = C_M_S / freq_hz
        slant = self.slant_m
        s = horns.conical_phase_deviation(
            aperture_diameter_m=self.aperture_diameter_m,
            slant_m=slant,
            wavelength_metres=lam,
        )
        gain = horns.conical_gain(
            aperture_diameter_m=self.aperture_diameter_m,
            slant_m=slant,
            wavelength_metres=lam,
        )
        eta = gain / (4.0 * math.pi * self.physical_area_m2 / (lam * lam))

        notes = [
            "Gain uses Balanis' empirical loss figure (13-59b), a cubic fit to measured "
            "data rather than a derivation.",
            "Beamwidths are the optimum-flare rules of thumb (60 and 70 lambda/d); unlike "
            "the pyramidal case these are NOT computed from the aperture field, so they do "
            "not track a badly-flared design. Treat them as indicative.",
        ]
        if s > horns.CONICAL_LOSS_FIT_MAX_S:
            notes.append(
                f"Phase deviation s={s:.2f} is beyond where the loss-figure fit is "
                f"trustworthy (~{horns.CONICAL_LOSS_FIT_MAX_S:g}); this gain is unreliable "
                "and the horn is in any case badly over-flared."
            )
        if self.throat_diameter_m <= 0:
            notes.append(
                "Throat diameter unknown, so the apex is taken at the throat. That "
                "understates the slant and overstates the phase error, making this gain a "
                "conservative floor rather than a best estimate."
            )

        return characterization_from_gain(
            freq_hz=freq_hz,
            gain_linear=gain,
            hpbw_e_deg=CONICAL_HPBW_E_CONST * lam / self.aperture_diameter_m,
            hpbw_h_deg=CONICAL_HPBW_H_CONST * lam / self.aperture_diameter_m,
            aperture_efficiency=eta,
            detail={
                "physical_area_m2": self.physical_area_m2,
                "slant_m": slant,
                "phase_deviation": s,
                "loss_figure_db": horns.conical_loss_figure_db(s),
                "aperture_wavelengths": self.aperture_diameter_m / lam,
            },
            notes=tuple(notes),
        )
