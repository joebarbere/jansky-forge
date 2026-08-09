"""Horn design: exact aperture-phase-error gain, synthesis, and realizability (M1).

M0 modelled horns with a single assumption — that the flare is near-optimum, so aperture
efficiency is 51%. That is true of published designs (they come from the same equations)
and useless the moment you change a dimension, which is the whole point of this tool. This
module replaces the assumption with the physics.

**What aperture phase error is.** A horn's aperture is not an equiphase surface: the wave
travels further to reach the aperture edge than the centre, by an amount that grows as the
flare gets more aggressive for its length. Gain therefore does *not* rise without limit as
you widen a horn of fixed length — it peaks and then falls. The optimum-horn conditions are
exactly where that peak sits, and the reason "just make it bigger" is bad advice.

**Notation** (Balanis ch. 13, kept verbatim so the equations are checkable — and note
carefully which symbols are axial and which are slant, because mixing them is a silent 7%
error that no self-consistency test catches):

===============  ====================================================================
``a``, ``b``     Feeding waveguide broad (H-plane) and narrow (E-plane) walls
``a1``, ``b1``   Aperture width (H-plane) and height (E-plane)
``rho1``         E-plane **axial** distance, virtual apex to aperture plane
``rho2``         H-plane axial distance
``rho_e``        E-plane **slant**, apex to aperture *edge*: sqrt(rho1^2 + (b1/2)^2)
``rho_h``        H-plane slant: sqrt(rho2^2 + (a1/2)^2)
``p_e``, ``p_h`` **Axial flare lengths**: waveguide face to aperture. This is what a
                 builder measures as "the length of the horn"
===============  ====================================================================

The gain formulas take the *axial* ``rho1``/``rho2``; Balanis (13-49) is written in terms
of the *slants*. ``rho_e - rho1`` is the peak aperture phase error expressed as a length,
which is why ``s ~= (rho_e - rho1)/lambda``.

**Realizability.** A pyramidal horn is one rectangular frustum, so both flares share a
single axial length: ``p_e == p_h``. The apex distances ``rho1`` and ``rho2`` are then
generally *unequal* — about 7% apart in Balanis' own optimum design example. A geometry
quoting two different axial flare lengths is not one buildable horn, and
:func:`realizability` says so; it catches a real case in this package's own catalog.

**Verification.** This module reproduces Balanis' published worked examples. Example 13.5
(analysis): our rho_e = 6.1555, rho_h = 6.6002, p_e = p_h = 5.4545, s = 0.1576, t = 0.6302
against the book's 6.1555, 6.6000, 5.454, 0.1575, 0.63; D_p = 18.83 dB against 18.78 dB
(the book reads its Fresnel values off printed tables, so ~0.1 dB is the honest tolerance).
Example 13.6 (design): our a1 = 5.974 lambda and b1 = 4.712 lambda against 6.002 and 4.715.
Separately, fed optimum-flare geometry the Fresnel gain returns an aperture efficiency of
0.5144 at every size — the textbook "about 51%", reproduced rather than assumed.

References
----------
Balanis, *Antenna Theory: Analysis and Design*, 4th ed., ch. 13 (Horn Antennas):
E-plane sectoral gain, H-plane sectoral gain, the pyramidal product form, the optimum
flare conditions, and the design procedure.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
from scipy.optimize import brentq
from scipy.special import fresnel, j1, jvp

from jansky_forge.units import to_db, wavelength_m

#: Aperture efficiency an optimum pyramidal horn achieves, as *computed* by this module's
#: Fresnel-integral gain from optimum-flare geometry — not an input to it. Balanis' ch. 13
#: design derivation rounds this to 50% and other texts quote 51%; the exact figure the
#: equations give at the true optimum is this. (Evaluating Balanis' *published* Example
#: 13.6 dimensions gives 0.5014 instead, because the design equation's approximations land
#: marginally off the true optimum — a difference worth knowing about, not worth chasing.)
OPTIMUM_PYRAMIDAL_EFFICIENCY = 0.5144

#: Maximum aperture phase deviation (in wavelengths) at the optimum flare, per plane.
#: E-plane: s = b1^2/(8*lambda*rho1) = 1/4. H-plane: t = a1^2/(8*lambda*rho2) = 3/8.
OPTIMUM_PHASE_DEVIATION_E = 0.25
OPTIMUM_PHASE_DEVIATION_H = 0.375


def fresnel_cs(x: float | np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Fresnel integrals as ``(C, S)`` — note the order.

    ``scipy.special.fresnel`` returns ``(S, C)``, the opposite order to how they are
    written in every antenna text. Swapping them is a silent, plausible-looking error, so
    every use in this package goes through this one function.

    Convention (verified numerically against direct quadrature, and the one Balanis uses):
    C(x) = int_0^x cos(pi*t^2/2) dt, S(x) = int_0^x sin(pi*t^2/2) dt.
    """
    s, c = fresnel(x)
    return c, s


def apex_distance_e(*, aperture_b1_m: float, waveguide_b_m: float, axial_m: float) -> float:
    """E-plane apex distance ``rho1`` from the horn's axial length.

    ``rho1`` is the *axial* distance from the flare's virtual apex to the aperture. By
    similar triangles the axial flare length is p_e = rho1*(1 - b/b1), so

        rho1 = p_e * b1 / (b1 - b)

    This is Balanis (13-49a) rearranged. That equation is written in terms of the *slant*
    rho_e = sqrt(rho1^2 + (b1/2)^2), and reading rho1 where it says rho_e is a 7% error in
    the phase-error denominator that no test of internal consistency will catch — see
    :func:`slant_e`.
    """
    flare = aperture_b1_m - waveguide_b_m
    if flare <= 0:
        raise ValueError(
            f"aperture height {aperture_b1_m} must exceed the waveguide's {waveguide_b_m} — "
            "a horn has to flare outward"
        )
    if axial_m <= 0:
        raise ValueError(f"axial length must be positive, got {axial_m}")
    return axial_m * aperture_b1_m / flare


def apex_distance_h(*, aperture_a1_m: float, waveguide_a_m: float, axial_m: float) -> float:
    """H-plane apex distance ``rho2``: rho2 = p_h * a1/(a1 - a). See :func:`apex_distance_e`."""
    flare = aperture_a1_m - waveguide_a_m
    if flare <= 0:
        raise ValueError(
            f"aperture width {aperture_a1_m} must exceed the waveguide's {waveguide_a_m} — "
            "a horn has to flare outward"
        )
    if axial_m <= 0:
        raise ValueError(f"axial length must be positive, got {axial_m}")
    return axial_m * aperture_a1_m / flare


def axial_length_e(*, rho1_m: float, aperture_b1_m: float, waveguide_b_m: float) -> float:
    """Axial flare length p_e = rho1*(1 - b/b1) — the inverse of :func:`apex_distance_e`."""
    return rho1_m * (1.0 - waveguide_b_m / aperture_b1_m)


def axial_length_h(*, rho2_m: float, aperture_a1_m: float, waveguide_a_m: float) -> float:
    """Axial flare length p_h = rho2*(1 - a/a1)."""
    return rho2_m * (1.0 - waveguide_a_m / aperture_a1_m)


def slant_e(*, rho1_m: float, aperture_b1_m: float) -> float:
    """Balanis' ``rho_e``: apex-to-aperture-*edge* slant, sqrt(rho1^2 + (b1/2)^2).

    Distinct from ``rho1`` (axial). rho_e - rho1 is the peak aperture phase error as a
    length, which is why s ~= (rho_e - rho1)/lambda.
    """
    return math.hypot(rho1_m, aperture_b1_m / 2.0)


def slant_h(*, rho2_m: float, aperture_a1_m: float) -> float:
    """Balanis' ``rho_h``: H-plane apex-to-edge slant, sqrt(rho2^2 + (a1/2)^2)."""
    return math.hypot(rho2_m, aperture_a1_m / 2.0)


def phase_deviation_e(*, aperture_b1_m: float, rho1_m: float, wavelength_metres: float) -> float:
    """Maximum E-plane aperture phase deviation s = b1^2/(8*lambda*rho1), in wavelengths.

    0.25 is the optimum. Much above it, gain falls despite the bigger aperture.
    """
    return aperture_b1_m**2 / (8.0 * wavelength_metres * rho1_m)


def phase_deviation_h(*, aperture_a1_m: float, rho2_m: float, wavelength_metres: float) -> float:
    """Maximum H-plane aperture phase deviation t = a1^2/(8*lambda*rho2). Optimum is 0.375."""
    return aperture_a1_m**2 / (8.0 * wavelength_metres * rho2_m)


def e_plane_sectoral_gain(
    *, waveguide_a_m: float, aperture_b1_m: float, rho1_m: float, wavelength_metres: float
) -> float:
    """Gain (linear) of an E-plane sectoral horn, Fresnel-integral form.

    G_E = (64*a*rho1)/(pi*lambda*b1) * [C^2(w) + S^2(w)],  w = b1/sqrt(2*lambda*rho1)
    """
    w = aperture_b1_m / math.sqrt(2.0 * wavelength_metres * rho1_m)
    c, s = fresnel_cs(w)
    return float(
        (64.0 * waveguide_a_m * rho1_m)
        / (math.pi * wavelength_metres * aperture_b1_m)
        * (c**2 + s**2)
    )


def h_plane_sectoral_gain(
    *, waveguide_b_m: float, aperture_a1_m: float, rho2_m: float, wavelength_metres: float
) -> float:
    """Gain (linear) of an H-plane sectoral horn, Fresnel-integral form.

    G_H = (4*pi*b*rho2)/(lambda*a1) * {[C(u)-C(v)]^2 + [S(u)-S(v)]^2}
    with u = (1/sqrt2)*[sqrt(lambda*rho2)/a1 + a1/sqrt(lambda*rho2)]
    and  v = (1/sqrt2)*[sqrt(lambda*rho2)/a1 - a1/sqrt(lambda*rho2)]
    """
    root = math.sqrt(wavelength_metres * rho2_m)
    u = (root / aperture_a1_m + aperture_a1_m / root) / math.sqrt(2.0)
    v = (root / aperture_a1_m - aperture_a1_m / root) / math.sqrt(2.0)
    cu, su = fresnel_cs(u)
    cv, sv = fresnel_cs(v)
    return float(
        (4.0 * math.pi * waveguide_b_m * rho2_m)
        / (wavelength_metres * aperture_a1_m)
        * ((cu - cv) ** 2 + (su - sv) ** 2)
    )


def pyramidal_gain(
    *,
    waveguide_a_m: float,
    waveguide_b_m: float,
    aperture_a1_m: float,
    aperture_b1_m: float,
    rho1_m: float,
    rho2_m: float,
    wavelength_metres: float,
) -> float:
    """Gain (linear) of a pyramidal horn: G_P = (pi*lambda^2)/(32*a*b) * G_E * G_H.

    The two sectoral gains carry the phase error in their own plane; the product form
    combines them. This is the equation that makes the tool able to tell you a horn is
    *too* flared, which no efficiency constant can.
    """
    g_e = e_plane_sectoral_gain(
        waveguide_a_m=waveguide_a_m,
        aperture_b1_m=aperture_b1_m,
        rho1_m=rho1_m,
        wavelength_metres=wavelength_metres,
    )
    g_h = h_plane_sectoral_gain(
        waveguide_b_m=waveguide_b_m,
        aperture_a1_m=aperture_a1_m,
        rho2_m=rho2_m,
        wavelength_metres=wavelength_metres,
    )
    return (math.pi * wavelength_metres**2) / (32.0 * waveguide_a_m * waveguide_b_m) * g_e * g_h


# --------------------------------------------------------------------------------------
# Synthesis: gain -> dimensions
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class PyramidalDesign:
    """A synthesized pyramidal horn: the dimensions, and what they are predicted to do."""

    freq_hz: float
    waveguide_a_m: float
    waveguide_b_m: float
    aperture_a1_m: float
    aperture_b1_m: float
    #: The single axial length (rho_e == rho_h) — this is a realizable horn by construction.
    axial_length_m: float
    rho1_m: float
    rho2_m: float
    gain_dbi: float
    #: Balanis' rho_e / rho_h — apex to aperture edge along each flare.
    slant_e_m: float
    slant_h_m: float

    @property
    def phase_deviation_e(self) -> float:
        return phase_deviation_e(
            aperture_b1_m=self.aperture_b1_m,
            rho1_m=self.rho1_m,
            wavelength_metres=wavelength_m(self.freq_hz),
        )

    @property
    def phase_deviation_h(self) -> float:
        return phase_deviation_h(
            aperture_a1_m=self.aperture_a1_m,
            rho2_m=self.rho2_m,
            wavelength_metres=wavelength_m(self.freq_hz),
        )

    def summary(self) -> str:
        return (
            f"{self.gain_dbi:.2f} dBi at {self.freq_hz / 1e6:.3f} MHz: aperture "
            f"{self.aperture_a1_m * 1000:.1f} x {self.aperture_b1_m * 1000:.1f} mm, "
            f"axial length {self.axial_length_m * 1000:.1f} mm"
        )


def optimum_aperture_for_axial(
    *, axial_length_m: float, freq_hz: float, waveguide_a_m: float, waveguide_b_m: float
) -> tuple[float, float]:
    """The optimum aperture (a1, b1) for a horn of this axial length — in closed form.

    Impose the two optimum-flare conditions together with the geometry, holding the axial
    length common to both planes (so the result is realizable by construction):

        b1 = sqrt(2*lambda*rho1)  with  rho1 = L*b1/(b1 - b)   =>  b1^2 - b*b1 - 2*lambda*L = 0
        a1 = sqrt(3*lambda*rho2)  with  rho2 = L*a1/(a1 - a)   =>  a1^2 - a*a1 - 3*lambda*L = 0

    Both are quadratics, so no iteration is needed:

        b1 = [b + sqrt(b^2 +  8*lambda*L)] / 2
        a1 = [a + sqrt(a^2 + 12*lambda*L)] / 2

    These are exactly Nikolova's design relations (McMaster ECE L18, eq. 18.51 and the
    accompanying B expression) reached from the other direction, which is a useful
    independent check that the geometry above is right.
    """
    lam = wavelength_m(freq_hz)
    if axial_length_m <= 0:
        raise ValueError(f"axial length must be positive, got {axial_length_m}")
    if waveguide_a_m <= 0 or waveguide_b_m <= 0:
        raise ValueError("waveguide dimensions must be positive")
    b1 = (waveguide_b_m + math.sqrt(waveguide_b_m**2 + 8.0 * lam * axial_length_m)) / 2.0
    a1 = (waveguide_a_m + math.sqrt(waveguide_a_m**2 + 12.0 * lam * axial_length_m)) / 2.0
    return a1, b1


def design_pyramidal_horn(
    *, gain_dbi: float, freq_hz: float, waveguide_a_m: float, waveguide_b_m: float
) -> PyramidalDesign:
    """Synthesize an optimum pyramidal horn for a target gain — the M1 headline.

    Strategy: the axial length is the single free variable once "optimum flare in both
    planes" and "one axial length" are imposed, and gain rises monotonically with it. So
    solve directly for the axial length whose optimum aperture yields the requested gain,
    using the exact Fresnel gain at every step. No lookup tables, no design nomograms, and
    the answer is realizable by construction rather than by luck.

    >>> d = design_pyramidal_horn(
    ...     gain_dbi=18.0, freq_hz=1_420_405_751.768,
    ...     waveguide_a_m=0.1651, waveguide_b_m=0.08255,
    ... )
    >>> round(d.gain_dbi, 2)
    18.0
    """
    lam = wavelength_m(freq_hz)
    if waveguide_a_m <= 0 or waveguide_b_m <= 0:
        raise ValueError("waveguide dimensions must be positive")

    def gain_at(axial: float) -> float:
        a1, b1 = optimum_aperture_for_axial(
            axial_length_m=axial,
            freq_hz=freq_hz,
            waveguide_a_m=waveguide_a_m,
            waveguide_b_m=waveguide_b_m,
        )
        r1 = apex_distance_e(aperture_b1_m=b1, waveguide_b_m=waveguide_b_m, axial_m=axial)
        r2 = apex_distance_h(aperture_a1_m=a1, waveguide_a_m=waveguide_a_m, axial_m=axial)
        return to_db(
            pyramidal_gain(
                waveguide_a_m=waveguide_a_m,
                waveguide_b_m=waveguide_b_m,
                aperture_a1_m=a1,
                aperture_b1_m=b1,
                rho1_m=r1,
                rho2_m=r2,
                wavelength_metres=lam,
            )
        )

    lo, hi = 0.01 * lam, 1e4 * lam
    if gain_at(lo) > gain_dbi:
        raise ValueError(
            f"{gain_dbi:g} dBi is below what this waveguide gives with any flare "
            f"(>= {gain_at(lo):.2f} dBi) — an open waveguide already exceeds it"
        )
    if gain_at(hi) < gain_dbi:
        raise ValueError(
            f"{gain_dbi:g} dBi would need a horn longer than {hi:g} m at this frequency; "
            "a reflector is the right antenna above roughly 25-30 dBi"
        )
    axial = brentq(lambda ax: gain_at(ax) - gain_dbi, lo, hi, xtol=1e-12, rtol=1e-14)

    a1, b1 = optimum_aperture_for_axial(
        axial_length_m=axial,
        freq_hz=freq_hz,
        waveguide_a_m=waveguide_a_m,
        waveguide_b_m=waveguide_b_m,
    )
    r1 = apex_distance_e(aperture_b1_m=b1, waveguide_b_m=waveguide_b_m, axial_m=axial)
    r2 = apex_distance_h(aperture_a1_m=a1, waveguide_a_m=waveguide_a_m, axial_m=axial)
    return PyramidalDesign(
        freq_hz=freq_hz,
        waveguide_a_m=waveguide_a_m,
        waveguide_b_m=waveguide_b_m,
        aperture_a1_m=a1,
        aperture_b1_m=b1,
        axial_length_m=axial,
        rho1_m=r1,
        rho2_m=r2,
        gain_dbi=gain_at(axial),
        # Balanis' rho_e / rho_h: apex to aperture EDGE. The panel you actually cut runs
        # from the waveguide edge to the aperture edge, which is this minus the same
        # slant taken to the waveguide — computed in the properties below.
        slant_e_m=slant_e(rho1_m=r1, aperture_b1_m=b1),
        slant_h_m=slant_h(rho2_m=r2, aperture_a1_m=a1),
    )


# --------------------------------------------------------------------------------------
# Conical horns
#
# Balanis treats the conical horn with Lommel functions. This module instead integrates the
# aperture field directly — the TE11 mode of circular waveguide carrying the flare's
# quadratic phase — which needs no special functions beyond Bessel and, crucially, is
# *verifiable*: the identical method applied to a pyramidal horn reproduces the Fresnel
# gain to within 0.000 dB, including badly over-flared geometry where phase error dominates.
#
# Two independent checks anchor it:
#   * uniform phase (no flare) gives eta = 0.8368, the textbook TE11 circular-aperture
#     efficiency of 0.836;
#   * maximizing gain over diameter at fixed slant gives eta = 0.5176 at d = 1.021*
#     sqrt(3*lambda*rho), reproducing the textbook "about 51%" for an optimum conical horn.
# Neither number is an input — both fall out of the integration.
# --------------------------------------------------------------------------------------

#: First zero of J1', which sets the TE11 cutoff in circular waveguide. Used by the
#: independent aperture-integration cross-check, not by the primary gain model.
CHI_11_PRIME = 1.8411837813406593

#: Aperture efficiency of an optimum conical horn (Balanis p. 785). Unlike the pyramidal
#: case there is no tractable closed form — Balanis explicitly declines the rigorous
#: spherical-Bessel/Legendre analysis as too involved — so the standard engineering route
#: is the empirical loss figure below, fitted to King's 1950 measurements.
OPTIMUM_CONICAL_EFFICIENCY = 0.51

#: Optimum conical flare: d_m = sqrt(3*lambda*l), giving a phase deviation s = 3/8 and a
#: loss figure of about 2.9 dB. NOTE l is the SLANT length (apex to aperture edge), not the
#: axial length — Balanis Fig. 13.26 draws them separately and (13-59c) uses the slant.
OPTIMUM_CONICAL_PHASE_DEVIATION = 0.375

#: Range of phase deviation over which the loss-figure polynomial is trustworthy. It is a
#: cubic fit, and outside this it misbehaves badly — beyond about s = 1.4 it even returns a
#: negative loss, i.e. more gain than the physical aperture can give.
CONICAL_LOSS_FIT_MAX_S = 0.8


def conical_slant_m(
    *, aperture_diameter_m: float, axial_length_m: float, throat_diameter_m: float = 0.0
) -> float:
    """Slant distance ``l`` from the cone's virtual apex to the aperture edge.

    With a throat diameter the apex is found by extending the cone inward; without one
    (``throat_diameter_m == 0``, meaning the source did not publish it) the throat is
    treated as a point. That understates the slant and so *overstates* the phase error,
    making the resulting gain a conservative floor rather than an optimistic guess.
    """
    if aperture_diameter_m <= 0 or axial_length_m <= 0:
        raise ValueError("aperture diameter and axial length must be positive")
    if throat_diameter_m >= aperture_diameter_m:
        raise ValueError("throat diameter must be smaller than the aperture — horns flare out")
    radius = aperture_diameter_m / 2.0
    if throat_diameter_m > 0:
        tan_alpha = (aperture_diameter_m - throat_diameter_m) / (2.0 * axial_length_m)
        axial_from_apex = radius / tan_alpha
    else:
        axial_from_apex = axial_length_m
    return math.hypot(axial_from_apex, radius)


def conical_phase_deviation(
    *, aperture_diameter_m: float, slant_m: float, wavelength_metres: float
) -> float:
    """s = d^2/(8*lambda*l), Balanis (13-59c). The slant, not the axial length."""
    return aperture_diameter_m**2 / (8.0 * wavelength_metres * slant_m)


def conical_loss_figure_db(s: float) -> float:
    """Aperture-efficiency loss in dB from phase deviation, Balanis (13-59b).

    L(s) = 0.8 - 1.71*s + 26.25*s^2 - 17.79*s^3

    An empirical cubic (King, *Proc. IRE* 1950), so it is a fit and not a derivation. It is
    only meaningful up to roughly :data:`CONICAL_LOSS_FIT_MAX_S`; callers should check.
    """
    return 0.8 - 1.71 * s + 26.25 * s**2 - 17.79 * s**3


def conical_gain(*, aperture_diameter_m: float, slant_m: float, wavelength_metres: float) -> float:
    """Gain (linear) of a conical horn, Balanis (13-59)-(13-60).

    D_c(dB) = 10*log10[(C/lambda)^2] - L(s),  C = pi*d (aperture circumference)

    which is the aperture gain 4*pi*A/lambda^2 reduced by the phase-error loss figure.
    """
    if aperture_diameter_m <= 0 or slant_m <= 0:
        raise ValueError("aperture diameter and slant must be positive")
    s = conical_phase_deviation(
        aperture_diameter_m=aperture_diameter_m,
        slant_m=slant_m,
        wavelength_metres=wavelength_metres,
    )
    circumference_ratio = math.pi * aperture_diameter_m / wavelength_metres
    gain_db = 10.0 * math.log10(circumference_ratio**2) - conical_loss_figure_db(s)
    return float(10.0 ** (gain_db / 10.0))


def conical_gain_by_aperture_integration(
    *, aperture_diameter_m: float, slant_m: float, wavelength_metres: float, samples: int = 3000
) -> float:
    """Gain (linear) of a conical horn by aperture integration of the TE11 field.

    D = (4*pi/lambda^2) * |int E dA|^2 / int |E|^2 dA, with

        E_rho = J1(kc*r)/(kc*r),  E_phi = J1'(kc*r),  kc = chi'11 / R

    and the flare's quadratic phase exp(-j*k*r^2/(2*rho)). The azimuthal integrals of
    sin^2 and cos^2 each give pi, so both vector components reduce to the same radial
    quadrature.
    """
    if aperture_diameter_m <= 0 or slant_m <= 0:
        raise ValueError("aperture diameter and slant must be positive")
    radius = aperture_diameter_m / 2.0
    k = 2.0 * math.pi / wavelength_metres
    kc = CHI_11_PRIME / radius
    r = np.linspace(1e-12, radius, samples)
    e_rho = j1(kc * r) / (kc * r)
    e_phi = jvp(1, kc * r)
    phase = np.exp(-1j * k * r**2 / (2.0 * slant_m))
    numerator = abs(math.pi * np.trapezoid((e_rho + e_phi) * phase * r, r)) ** 2
    denominator = math.pi * np.trapezoid((e_rho**2 + e_phi**2) * r, r)
    return float((4.0 * math.pi / wavelength_metres**2) * numerator / denominator)


@dataclass(frozen=True)
class ConicalDesign:
    """A synthesized conical horn."""

    freq_hz: float
    aperture_diameter_m: float
    slant_m: float
    axial_length_m: float
    gain_dbi: float

    def summary(self) -> str:
        return (
            f"{self.gain_dbi:.2f} dBi at {self.freq_hz / 1e6:.3f} MHz: aperture "
            f"{self.aperture_diameter_m * 1000:.1f} mm across, axial length "
            f"{self.axial_length_m * 1000:.1f} mm (slant {self.slant_m * 1000:.1f} mm)"
        )


def design_conical_horn(*, gain_dbi: float, freq_hz: float) -> ConicalDesign:
    """Synthesize an optimum conical horn for a target gain.

    Uses Balanis' optimum flare d = sqrt(3*lambda*l) and solves for the slant that
    delivers the requested gain, so the result sits at the loss figure's ~2.9 dB optimum.
    """
    lam = wavelength_m(freq_hz)

    def gain_at(slant: float) -> float:
        d = math.sqrt(3.0 * lam * slant)  # Balanis (13-60), the optimum flare
        return to_db(conical_gain(aperture_diameter_m=d, slant_m=slant, wavelength_metres=lam))

    lo, hi = 0.05 * lam, 1e4 * lam
    if gain_at(lo) > gain_dbi:
        raise ValueError(
            f"{gain_dbi:g} dBi is below the smallest useful conical horn at this frequency"
        )
    if gain_at(hi) < gain_dbi:
        raise ValueError(
            f"{gain_dbi:g} dBi would need an impractically long conical horn; use a reflector"
        )
    slant = brentq(lambda s: gain_at(s) - gain_dbi, lo, hi, xtol=1e-12, rtol=1e-14)
    d = math.sqrt(3.0 * lam * slant)
    # Back out the physical axial length from apex geometry: rho^2 = z^2 + (d/2)^2.
    axial = math.sqrt(max(slant**2 - (d / 2.0) ** 2, 0.0))
    return ConicalDesign(
        freq_hz=freq_hz,
        aperture_diameter_m=d,
        slant_m=slant,
        axial_length_m=axial,
        gain_dbi=gain_at(slant),
    )


# --------------------------------------------------------------------------------------
# Radiation patterns
#
# Computed by integrating the aperture field directly rather than quoting a closed form.
# The aperture distribution of a pyramidal horn (Balanis 13-48) is
#
#     E_y(x', y') = cos(pi*x'/a1) * exp(-j*k/2 * (x'^2/rho2 + y'^2/rho1))
#
# — a cosine taper across the H-plane from the TE10 mode, uniform across the E-plane, and
# the quadratic phase term that IS the aperture phase error. The principal-plane patterns
# are the 1-D transforms of that, times the (1 + cos theta)/2 obliquity factor.
#
# Doing it numerically keeps the phase error in the pattern (where it broadens the beam and
# fills the nulls) instead of assuming it away, and it is derived from one stated field
# distribution rather than from remembered pattern formulas. Vectorized over angle, so a
# full pattern is well under a millisecond.
# --------------------------------------------------------------------------------------

#: Aperture samples per wavelength of aperture width. The integrand oscillates at most
#: once per wavelength (at grazing angles) plus the quadratic phase, so 40 samples per
#: wavelength is comfortably oversampled — and sizing the grid to the aperture rather than
#: fixing it keeps a small horn cheap instead of paying a large horn's cost every time.
_SAMPLES_PER_WAVELENGTH = 40
_MIN_APERTURE_SAMPLES = 201


def _aperture_grid(aperture_m: float, wavelength_metres: float) -> np.ndarray:
    n = max(_MIN_APERTURE_SAMPLES, int(_SAMPLES_PER_WAVELENGTH * aperture_m / wavelength_metres))
    return np.linspace(-aperture_m / 2.0, aperture_m / 2.0, n | 1)  # force odd: sample boresight


def _obliquity(theta_rad: np.ndarray) -> np.ndarray:
    return (1.0 + np.cos(theta_rad)) / 2.0


def e_plane_pattern(
    *,
    aperture_b1_m: float,
    rho1_m: float,
    freq_hz: float,
    theta_deg: np.ndarray | list[float],
) -> np.ndarray:
    """E-plane power pattern in dB relative to boresight, at the given angles.

    The E-plane aperture distribution is uniform in amplitude with the quadratic phase of
    the flare; a horn with significant phase error shows the classic filled nulls and
    raised shoulders rather than the clean sinc of an unflared aperture.
    """
    kwargs = dict(aperture_b1_m=aperture_b1_m, rho1_m=rho1_m, freq_hz=freq_hz)
    return _normalize_db(
        _e_plane_field(theta_deg=theta_deg, **kwargs),
        _e_plane_field(theta_deg=np.array([0.0]), **kwargs),
    )


def _e_plane_field(
    *,
    aperture_b1_m: float,
    rho1_m: float,
    freq_hz: float,
    theta_deg: np.ndarray | list[float],
) -> np.ndarray:
    lam = wavelength_m(freq_hz)
    k = 2.0 * math.pi / lam
    theta = np.radians(np.asarray(theta_deg, dtype=float))
    y = _aperture_grid(aperture_b1_m, lam)
    phase = np.exp(-1j * k * y**2 / (2.0 * rho1_m))
    integrand = phase[None, :] * np.exp(1j * k * np.sin(theta)[:, None] * y[None, :])
    return np.trapezoid(integrand, y, axis=1) * _obliquity(theta)


def h_plane_pattern(
    *,
    aperture_a1_m: float,
    rho2_m: float,
    freq_hz: float,
    theta_deg: np.ndarray | list[float],
) -> np.ndarray:
    """H-plane power pattern in dB relative to boresight.

    The H-plane carries the TE10 cosine taper, which is why the H-plane beam is wider and
    its sidelobes markedly lower than the E-plane's — the single most visible asymmetry in
    any horn's pattern, and a good check that a measured pattern is oriented as you think.
    """
    kwargs = dict(aperture_a1_m=aperture_a1_m, rho2_m=rho2_m, freq_hz=freq_hz)
    return _normalize_db(
        _h_plane_field(theta_deg=theta_deg, **kwargs),
        _h_plane_field(theta_deg=np.array([0.0]), **kwargs),
    )


def _h_plane_field(
    *,
    aperture_a1_m: float,
    rho2_m: float,
    freq_hz: float,
    theta_deg: np.ndarray | list[float],
) -> np.ndarray:
    lam = wavelength_m(freq_hz)
    k = 2.0 * math.pi / lam
    theta = np.radians(np.asarray(theta_deg, dtype=float))
    x = _aperture_grid(aperture_a1_m, lam)
    taper = np.cos(math.pi * x / aperture_a1_m)
    phase = np.exp(-1j * k * x**2 / (2.0 * rho2_m))
    integrand = (taper * phase)[None, :] * np.exp(1j * k * np.sin(theta)[:, None] * x[None, :])
    return np.trapezoid(integrand, x, axis=1) * _obliquity(theta)


def _normalize_db(field: np.ndarray, boresight: np.ndarray) -> np.ndarray:
    """Pattern in dB relative to BORESIGHT, not to the largest sampled value.

    Normalizing to the sampled maximum silently rescales a sweep that does not include
    theta = 0 — asking for 30-90 degrees would put 0 dB at 30 degrees and make two patterns
    incomparable. Referencing boresight instead makes any sweep directly comparable to any
    other, and lets a genuinely split beam show up as a positive value rather than hiding
    behind a renormalization.
    """
    reference = float(np.abs(boresight[0]) ** 2)
    if reference <= 0:  # pragma: no cover - only reachable for a degenerate aperture
        raise ValueError("aperture integration produced no power on boresight")
    with np.errstate(divide="ignore"):
        return 10.0 * np.log10(np.abs(field) ** 2 / reference)


def _half_power_angle(
    field_at: Callable[[np.ndarray], np.ndarray], max_theta_deg: float = 90.0
) -> float:
    """Angle where a pattern first falls to -3 dB, as a root-find rather than a plot.

    Rendering a fine pattern just to read one crossing off it costs hundreds of
    milliseconds and would break this package's interactivity promise. Instead: one coarse
    vectorized sweep to bracket the *first* crossing (so a badly over-flared horn whose
    sidelobes climb back above -3 dB still reports its main beam, not something wider), then
    Brent to refine. Sub-millisecond, and more accurate than any grid.
    """
    coarse = np.linspace(0.0, max_theta_deg, 91)
    peak = np.abs(field_at(np.array([0.0])))[0] ** 2
    if peak <= 0:  # pragma: no cover - degenerate aperture
        raise ValueError("aperture integration produced no power at boresight")

    def excess(theta: float) -> float:
        """dB above the half-power level: positive inside the beam, negative outside."""
        power = float(np.abs(field_at(np.array([theta])))[0] ** 2)
        if power <= 0:  # pragma: no cover - exact null
            return -np.inf
        return 10.0 * math.log10(power / peak) + 3.0

    values = 10.0 * np.log10(np.abs(field_at(coarse)) ** 2 / peak) + 3.0
    below = np.nonzero(values <= 0.0)[0]
    if below.size == 0:
        raise ValueError(
            f"pattern never falls to -3 dB within {max_theta_deg} deg of boresight — the "
            "aperture is too small for a main beam to be defined"
        )
    i = below[0]
    return float(brentq(excess, coarse[i - 1], coarse[i], xtol=1e-10))


def pattern_beamwidths(
    *,
    aperture_a1_m: float,
    aperture_b1_m: float,
    rho1_m: float,
    rho2_m: float,
    freq_hz: float,
    max_theta_deg: float = 90.0,
) -> tuple[float, float]:
    """Half-power beamwidths (E, H) in degrees, measured off the computed patterns.

    These supersede M0's ``54*lambda/b1`` / ``78*lambda/a1`` rules of thumb, which hold only
    at optimum flare; these follow the pattern wherever the geometry actually goes. For
    optimum designs the two agree to a few percent, which is how we know both are right.
    """
    e_hp = _half_power_angle(
        lambda th: _e_plane_field(
            aperture_b1_m=aperture_b1_m, rho1_m=rho1_m, freq_hz=freq_hz, theta_deg=th
        ),
        max_theta_deg,
    )
    h_hp = _half_power_angle(
        lambda th: _h_plane_field(
            aperture_a1_m=aperture_a1_m, rho2_m=rho2_m, freq_hz=freq_hz, theta_deg=th
        ),
        max_theta_deg,
    )
    return 2.0 * e_hp, 2.0 * h_hp


# --------------------------------------------------------------------------------------
# Realizability
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Realizability:
    """Whether a quoted pyramidal geometry describes one buildable horn."""

    realizable: bool
    axial_e_m: float
    axial_h_m: float
    #: Fractional disagreement between the two axial lengths.
    mismatch: float
    message: str


def realizability(*, axial_e_m: float, axial_h_m: float, tolerance: float = 0.02) -> Realizability:
    """Check the one-axial-length condition rho_e == rho_h.

    A pyramidal horn is a single rectangular frustum: both flares start at the waveguide
    aperture and end at the horn aperture, so there is exactly one axial length. Designs
    that optimize the E- and H-plane sectoral horns *independently* satisfy both optimum
    conditions and still cannot be built, because the two flares would need to begin at
    different places. This catches that, and it does catch a real published design.
    """
    longer = max(axial_e_m, axial_h_m)
    if longer <= 0:
        raise ValueError("axial lengths must be positive")
    mismatch = abs(axial_e_m - axial_h_m) / longer
    if mismatch <= tolerance:
        return Realizability(
            realizable=True,
            axial_e_m=axial_e_m,
            axial_h_m=axial_h_m,
            mismatch=mismatch,
            message="Both flares share one axial length; this is a single buildable horn.",
        )
    return Realizability(
        realizable=False,
        axial_e_m=axial_e_m,
        axial_h_m=axial_h_m,
        mismatch=mismatch,
        message=(
            f"NOT a single buildable pyramidal horn: the E-plane flare wants an axial length "
            f"of {axial_e_m * 1000:.1f} mm and the H-plane flare {axial_h_m * 1000:.1f} mm, "
            f"a {mismatch:.1%} disagreement. The two flares would have to start at different "
            "points on the waveguide. This is the signature of a design that optimized each "
            "plane separately; synthesize with design_pyramidal_horn() instead."
        ),
    )
