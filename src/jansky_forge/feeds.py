"""Feeds and dish illumination: efficiency as a computed quantity (M3).

M0 treated a dish's efficiency as four constants you typed in. That is fine for a first
number and useless for a decision, because the constants are exactly what changes when you
pick a different feed or a different f/D. This module computes them.

**The physical story.** A feed at the focus does not light the dish evenly. The rim is
further away than the vertex (space attenuation) *and* sits off the feed's boresight (the
feed's own pattern falls away), so illumination tapers toward the edge. Taper too hard and
you waste the outer dish — poor *illumination* efficiency. Taper too little and feed power
sails past the rim into the ground — poor *spillover* efficiency, and worse, that ground is
warm and it lands in your system temperature. The two pull against each other, and the
optimum is a real, findable compromise.

The standard front-fed paraboloid integrals, for a rotationally symmetric feed pattern
``G_f(theta)`` and a rim at half-angle ``theta_0``:

    eta_spillover  = int_0^th0 G_f sin(th) dth  /  int_0^pi G_f sin(th) dth
    eta_illum      = 2 cot^2(th0/2) |int_0^th0 sqrt(G_f) tan(th/2) dth|^2
                     / int_0^th0 G_f sin(th) dth

The ``tan(th/2)`` is where the reflector geometry enters: a paraboloid maps feed angle to
aperture radius as rho = 2f tan(th/2), and the path length f sec^2(th/2) supplies the space
attenuation.

**Verification.** Maximizing the product over feed shape and rim angle gives an aperture
efficiency of 0.82-0.85 at a total edge taper of **-10.9 dB**, essentially independent of
the feed's shape (checked for cos^2q feeds with q from 0.5 to 4). That is the textbook
"optimum edge illumination is -10 to -11 dB", reproduced here rather than assumed — and its
near-invariance with feed shape is why the rule of thumb is worth trusting.

References
----------
Balanis, *Antenna Theory*, ch. 15 (Reflector Antennas): the aperture-efficiency integrals,
the cos^2q feed model, and aperture blockage.
Kraus, *Radio Astronomy*: beam efficiency and the cost of spillover in system temperature.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol, runtime_checkable

import numpy as np
from scipy.integrate import simpson
from scipy.optimize import minimize_scalar

from jansky_forge.units import C_M_S, to_db, wavelength_m

#: Total edge taper (feed pattern plus space attenuation) that maximizes aperture
#: efficiency, in dB. Computed here, not asserted: see the module docstring.
OPTIMUM_EDGE_TAPER_DB = -10.9


@runtime_checkable
class FeedPattern(Protocol):
    """A rotationally symmetric feed pattern, as relative power versus angle.

    Normalization does not matter: every integral below is a ratio, so a pattern may be
    returned in whatever scale is convenient.
    """

    def gain_relative(self, theta_rad: np.ndarray) -> np.ndarray:
        """Relative power radiated at ``theta_rad`` from boresight (0 <= theta <= pi)."""
        ...


@dataclass(frozen=True)
class CosQFeed:
    """The classic ``cos^(2q)(theta)`` feed model, radiating into the forward hemisphere.

    One number stands in for a whole feed. Larger ``q`` means a tighter beam, which suits a
    deeper dish (smaller f/D). It is an idealization — real feeds have sidelobes and are not
    rotationally symmetric — but it is the model the reflector literature is written in, and
    it makes "what beamwidth should my feed have?" answerable before the feed exists.
    """

    q: float = 1.0

    def __post_init__(self) -> None:
        if self.q <= 0:
            raise ValueError(f"q must be positive, got {self.q}")

    def gain_relative(self, theta_rad: np.ndarray) -> np.ndarray:
        theta = np.asarray(theta_rad, dtype=float)
        return np.where(
            theta <= math.pi / 2, np.cos(np.minimum(theta, math.pi / 2)) ** (2 * self.q), 0.0
        )

    @property
    def half_power_beamwidth_deg(self) -> float:
        """Full width where the pattern falls to half power."""
        return 2.0 * math.degrees(math.acos(0.5 ** (1.0 / (2.0 * self.q))))

    @classmethod
    def from_beamwidth(cls, hpbw_deg: float) -> CosQFeed:
        """Fit the model to a known half-power beamwidth."""
        if not 0.0 < hpbw_deg < 180.0:
            raise ValueError(f"beamwidth must be in (0, 180) deg, got {hpbw_deg}")
        half = math.radians(hpbw_deg / 2.0)
        return cls(q=math.log(0.5) / (2.0 * math.log(math.cos(half))))


@dataclass(frozen=True)
class HornFeed:
    """A real designed horn used as a dish feed — the M1-to-M3 join.

    Uses the horn's *computed* E- and H-plane patterns rather than a fitted model, so the
    answer reflects the horn you actually drew.

    A horn is not rotationally symmetric, and the reflector integrals assume it is. The
    equivalent symmetric pattern used here is the **geometric mean of the two principal
    planes**, which is the standard approximation and is exact only where the two agree.
    That is stated rather than hidden: :attr:`approximation` names it, and the dish result
    carries it into its notes.
    """

    aperture_a1_m: float
    aperture_b1_m: float
    rho1_m: float
    rho2_m: float
    freq_hz: float

    approximation: str = (
        "A horn's pattern is not rotationally symmetric; the reflector integrals assume it "
        "is. This uses the geometric mean of the E- and H-plane patterns, which is exact "
        "only where those two agree."
    )

    def gain_relative(self, theta_rad: np.ndarray) -> np.ndarray:
        grid, values = _horn_pattern_table(
            self.aperture_a1_m, self.aperture_b1_m, self.rho1_m, self.rho2_m, self.freq_hz
        )
        theta = np.atleast_1d(np.asarray(theta_rad, dtype=float))
        degrees = np.degrees(theta)
        # Beyond 90 degrees the aperture model has no validity; a horn radiates little
        # there, and treating it as zero is both conventional and conservative for
        # spillover (it cannot invent power that misses the dish).
        return np.where(degrees <= 90.0, np.interp(degrees, grid, values), 0.0)


#: Angular resolution of the cached feed-pattern table, in degrees. The reflector integrals
#: sample a pattern hundreds of times; recomputing a horn's aperture integral for each
#: sample costs most of a second per dish evaluation, which would break this package's
#: interactivity promise. Horn patterns are smooth on this scale, so tabulate once and
#: interpolate — the error against a direct evaluation is under 0.01 dB.
_FEED_TABLE_STEP_DEG = 0.1


@lru_cache(maxsize=64)
def _horn_pattern_table(
    aperture_a1_m: float, aperture_b1_m: float, rho1_m: float, rho2_m: float, freq_hz: float
) -> tuple[np.ndarray, np.ndarray]:
    """Tabulate a horn's equivalent symmetric pattern once per geometry.

    Cached on the geometry, so sweeping f/D for a fixed horn — the common case — pays for
    the pattern exactly once.
    """
    from jansky_forge.horns import e_plane_pattern, h_plane_pattern

    grid = np.arange(0.0, 90.0 + _FEED_TABLE_STEP_DEG, _FEED_TABLE_STEP_DEG)
    e_db = e_plane_pattern(
        aperture_b1_m=aperture_b1_m, rho1_m=rho1_m, freq_hz=freq_hz, theta_deg=grid
    )
    h_db = h_plane_pattern(
        aperture_a1_m=aperture_a1_m, rho2_m=rho2_m, freq_hz=freq_hz, theta_deg=grid
    )
    return grid, 10.0 ** ((e_db + h_db) / 20.0)  # geometric mean in power


def conical_horn_feed(*, aperture_diameter_m: float, freq_hz: float) -> CosQFeed:
    """A conical horn as a dish feed, via its rule-of-thumb beamwidth. **Approximate.**

    Conical horns are the natural prime-focus feed, so M3 needs a way to use one. But the
    true circular-aperture TE11 far-field pattern is still not implemented (M1 computed
    conical *gain* exactly and left the pattern as rules of thumb), so this fits a
    ``cos^2q`` model to the geometric mean of those rule-of-thumb beamwidths — 60 and 70
    lambda/d — and hands back a feed you can use today.

    That is two approximations stacked: a rule-of-thumb beamwidth, then a symmetric model
    fitted to it. Use it to choose an f/D to aim for, not to predict efficiency to the
    third decimal. A pyramidal horn via :class:`HornFeed` uses its real computed pattern
    and is the more trustworthy route where either will do.
    """
    lam = wavelength_m(freq_hz)
    if aperture_diameter_m <= 0:
        raise ValueError("aperture diameter must be positive")
    hpbw = math.sqrt(60.0 * 70.0) * lam / aperture_diameter_m
    if hpbw >= 180.0:
        raise ValueError(
            f"aperture is only {aperture_diameter_m / lam:.2f} wavelengths across; its beam "
            "is too broad for the feed model to mean anything"
        )
    return CosQFeed.from_beamwidth(hpbw)


#: Samples per integral. The reflector integrands are smooth and bounded, so fixed Simpson
#: quadrature over a dense grid beats an adaptive rule here: it evaluates the feed pattern
#: ONCE, vectorized, instead of several hundred times one angle at a time, and it does not
#: thrash against the small kinks in an interpolated pattern the way adaptive refinement
#: does. Accuracy at this density is far below the honesty floor of the model itself.
_QUADRATURE_POINTS = 2001


def _integrate(values: np.ndarray, grid: np.ndarray) -> float:
    return float(simpson(values, x=grid))


def spillover_efficiency(feed: FeedPattern, subtended_half_angle_deg: float) -> float:
    """Fraction of the feed's radiated power that lands on the dish rather than past it.

    The power that misses is not merely lost: on a ground-pointing prime-focus feed it
    picks up ~290 K of warm earth, which is why a radio telescope cares about spillover far
    more than a communications link of the same gain does.
    """
    theta0 = math.radians(subtended_half_angle_deg)
    on_dish = np.linspace(0.0, theta0, _QUADRATURE_POINTS)
    everywhere = np.linspace(0.0, math.pi, _QUADRATURE_POINTS)
    intercepted = _integrate(feed.gain_relative(on_dish) * np.sin(on_dish), on_dish)
    total = _integrate(feed.gain_relative(everywhere) * np.sin(everywhere), everywhere)
    if total <= 0:
        raise ValueError("feed radiates no power")
    return intercepted / total


def illumination_efficiency(feed: FeedPattern, subtended_half_angle_deg: float) -> float:
    """How uniformly the feed lights the aperture (1.0 would be perfectly even)."""
    theta0 = math.radians(subtended_half_angle_deg)
    grid = np.linspace(0.0, theta0, _QUADRATURE_POINTS)
    gain = np.maximum(feed.gain_relative(grid), 0.0)
    field = _integrate(np.sqrt(gain) * np.tan(grid / 2.0), grid)
    power = _integrate(gain * np.sin(grid), grid)
    if power <= 0:
        raise ValueError("feed delivers no power to the dish; is it pointed at it?")
    cot = 1.0 / math.tan(theta0 / 2.0)
    return 2.0 * cot * cot * field * field / power


def aperture_efficiency(feed: FeedPattern, subtended_half_angle_deg: float) -> float:
    """Illumination times spillover — the part of dish efficiency the feed controls."""
    return spillover_efficiency(feed, subtended_half_angle_deg) * illumination_efficiency(
        feed, subtended_half_angle_deg
    )


def space_attenuation_db(subtended_half_angle_deg: float) -> float:
    """Extra taper from the rim being further from the focus than the vertex.

    Path length goes as f*sec^2(theta/2), so amplitude goes as cos^2(theta/2) and power as
    cos^4(theta/2). A deep dish (small f/D) is penalized hard here — at f/D = 0.25 the rim
    is 12 dB down on this effect alone, before the feed's own pattern is considered.
    """
    return 40.0 * math.log10(math.cos(math.radians(subtended_half_angle_deg) / 2.0))


def edge_taper_db(feed: FeedPattern, subtended_half_angle_deg: float) -> float:
    """Total illumination at the rim relative to the vertex, in dB (negative).

    Feed pattern *plus* space attenuation. This is the number the literature means by "edge
    taper", and the one to compare against :data:`OPTIMUM_EDGE_TAPER_DB`.
    """
    theta0 = math.radians(subtended_half_angle_deg)
    on_axis, at_edge = (
        float(v) for v in np.atleast_1d(feed.gain_relative(np.array([0.0, theta0])))
    )
    if on_axis <= 0:
        raise ValueError("feed has no on-axis gain")
    if at_edge <= 0:
        return -math.inf
    return to_db(at_edge / on_axis) + space_attenuation_db(subtended_half_angle_deg)


def f_over_d_from_subtended_angle(subtended_half_angle_deg: float) -> float:
    """Invert the dish geometry: f/D = 1 / (4 tan(theta0/2))."""
    if not 0.0 < subtended_half_angle_deg < 180.0:
        raise ValueError("subtended half-angle must be in (0, 180) deg")
    return 1.0 / (4.0 * math.tan(math.radians(subtended_half_angle_deg) / 2.0))


@dataclass(frozen=True)
class FeedMatch:
    """The result of matching a feed to a dish, or a dish to a feed."""

    subtended_half_angle_deg: float
    f_over_d: float
    edge_taper_db: float
    illumination_efficiency: float
    spillover_efficiency: float
    aperture_efficiency: float
    notes: tuple[str, ...] = ()

    def summary(self) -> str:
        return (
            f"f/D {self.f_over_d:.3f} (rim at {self.subtended_half_angle_deg:.1f} deg), "
            f"edge taper {self.edge_taper_db:.1f} dB, eta_ap {self.aperture_efficiency:.3f} "
            f"(illum {self.illumination_efficiency:.3f} x spill "
            f"{self.spillover_efficiency:.3f})"
        )


def evaluate_feed(feed: FeedPattern, *, f_over_d: float) -> FeedMatch:
    """How well does this feed suit a dish of this f/D?"""
    if f_over_d <= 0:
        raise ValueError(f"f/D must be positive, got {f_over_d}")
    theta0 = math.degrees(2.0 * math.atan(1.0 / (4.0 * f_over_d)))
    illum = illumination_efficiency(feed, theta0)
    spill = spillover_efficiency(feed, theta0)
    taper = edge_taper_db(feed, theta0)

    notes = []
    if taper > -6.0:
        notes.append(
            f"Edge taper {taper:.1f} dB is much flatter than the {OPTIMUM_EDGE_TAPER_DB:g} dB "
            "optimum: the feed overshoots the rim, so power spills onto the ground. On a "
            "radio telescope that costs system temperature as well as gain."
        )
    elif taper < -16.0:
        notes.append(
            f"Edge taper {taper:.1f} dB is much deeper than the {OPTIMUM_EDGE_TAPER_DB:g} dB "
            "optimum: the outer dish is barely lit, so you are carrying metal that is not "
            "working. A wider feed, or a deeper dish, would use it."
        )
    approximation = getattr(feed, "approximation", None)
    if approximation:
        notes.append(str(approximation))

    return FeedMatch(
        subtended_half_angle_deg=theta0,
        f_over_d=f_over_d,
        edge_taper_db=taper,
        illumination_efficiency=illum,
        spillover_efficiency=spill,
        aperture_efficiency=illum * spill,
        notes=tuple(notes),
    )


def best_f_over_d(feed: FeedPattern) -> FeedMatch:
    """The f/D that maximizes aperture efficiency for this feed.

    Answers "I have this feed — what dish shape should I look for?", which is the question
    an amateur usually faces, since the feed is often the part you already own.
    """
    result = minimize_scalar(
        lambda theta0: -aperture_efficiency(feed, theta0),
        bounds=(5.0, 165.0),
        method="bounded",
    )
    return evaluate_feed(feed, f_over_d=f_over_d_from_subtended_angle(result.x))


def best_feed_for_dish(
    *, f_over_d: float, q_bounds: tuple[float, float] = (0.1, 30.0)
) -> FeedMatch:
    """The ``cos^2q`` feed that best suits a given dish, as a required beamwidth.

    Answers the other direction: "I have this dish — what feed do I need?" The useful output
    is :attr:`FeedMatch.notes`, which states the beamwidth to aim for; a horn of that
    beamwidth can then be synthesized with :mod:`jansky_forge.horns`.
    """
    theta0 = math.degrees(2.0 * math.atan(1.0 / (4.0 * f_over_d)))
    result = minimize_scalar(
        lambda q: -aperture_efficiency(CosQFeed(q=q), theta0),
        bounds=q_bounds,
        method="bounded",
    )
    feed = CosQFeed(q=result.x)
    match = evaluate_feed(feed, f_over_d=f_over_d)
    return FeedMatch(
        subtended_half_angle_deg=match.subtended_half_angle_deg,
        f_over_d=match.f_over_d,
        edge_taper_db=match.edge_taper_db,
        illumination_efficiency=match.illumination_efficiency,
        spillover_efficiency=match.spillover_efficiency,
        aperture_efficiency=match.aperture_efficiency,
        notes=(
            f"Wanted: a feed with a half-power beamwidth near "
            f"{feed.half_power_beamwidth_deg:.1f} deg (cos^2q model, q = {feed.q:.2f}). "
            "Synthesize a horn to roughly that beamwidth and re-check with HornFeed — a real "
            "horn is not rotationally symmetric, so it will not match exactly.",
            *match.notes,
        ),
    )


# --------------------------------------------------------------------------------------
# Blockage and surface
# --------------------------------------------------------------------------------------


def central_blockage_efficiency(*, dish_diameter_m: float, blocker_diameter_m: float) -> float:
    """Efficiency loss from a feed or subreflector shadowing the aperture centre.

    For roughly uniform illumination the blocked field subtracts, so gain falls as
    (1 - (d/D)^2)^2 — the loss goes as the *square* of the blocked area fraction, which is
    why blockage hurts more than its area suggests. An offset dish avoids it entirely.
    """
    if dish_diameter_m <= 0:
        raise ValueError("dish diameter must be positive")
    if not 0.0 <= blocker_diameter_m < dish_diameter_m:
        raise ValueError("blocker must be smaller than the dish (and not negative)")
    return (1.0 - (blocker_diameter_m / dish_diameter_m) ** 2) ** 2


def strut_blockage_efficiency(
    *, dish_diameter_m: float, strut_count: int, strut_width_m: float, strut_length_m: float
) -> float:
    """Plane-wave blockage from feed support struts.

    Treats each strut as shadowing ``width * length`` of aperture — the standard first-order
    estimate. It ignores scattering, which is what actually produces the sidelobe spikes
    struts are notorious for; this number is about lost gain, not about pattern damage.
    """
    if strut_count < 0 or strut_width_m < 0 or strut_length_m < 0:
        raise ValueError("strut geometry cannot be negative")
    aperture = math.pi * (dish_diameter_m / 2.0) ** 2
    shadow = strut_count * strut_width_m * strut_length_m
    if shadow >= aperture:
        raise ValueError("struts would shadow the entire aperture")
    return (1.0 - shadow / aperture) ** 2


def mesh_verdict(*, mesh_opening_m: float, freq_hz: float) -> tuple[float, str]:
    """Is a mesh reflector solid enough at this frequency?

    Returns the opening as a fraction of a wavelength and a plain verdict. This is a rule of
    thumb, deliberately: a real transmission coefficient depends on wire diameter, weave, and
    polarization, and quoting a precise number from the opening size alone would be false
    precision. The threshold everyone uses is that openings below about lambda/10 leak
    negligibly.
    """
    lam = wavelength_m(freq_hz)
    ratio = mesh_opening_m / lam
    if ratio <= 0.05:
        verdict = "effectively solid"
    elif ratio <= 0.1:
        verdict = "fine — the usual lambda/10 rule is satisfied"
    elif ratio <= 0.2:
        verdict = "marginal: expect some leakage, and more sky noise through the dish"
    else:
        verdict = "too open at this frequency — the mesh will leak badly"
    return ratio, (
        f"Mesh opening is lambda/{1 / ratio:.1f} ({ratio * 100:.1f}% of a wavelength) — {verdict}."
    )


# --------------------------------------------------------------------------------------
# Waveguide feed: probe and backshort
#
# The gap M2 named: a horn with no feed design is a nicely-shaped piece of metal.
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ProbeDesign:
    """Where to put the coaxial probe in a rectangular waveguide, and how long to make it."""

    freq_hz: float
    waveguide_a_m: float
    waveguide_b_m: float
    cutoff_freq_hz: float
    guide_wavelength_m: float
    backshort_distance_m: float
    probe_length_m: float
    notes: tuple[str, ...] = ()

    def summary(self) -> str:
        return (
            f"probe {self.probe_length_m * 1000:.1f} mm long, "
            f"{self.backshort_distance_m * 1000:.1f} mm from the backshort "
            f"(guide wavelength {self.guide_wavelength_m * 1000:.1f} mm, "
            f"cutoff {self.cutoff_freq_hz / 1e6:.0f} MHz)"
        )


def design_probe(*, freq_hz: float, waveguide_a_m: float, waveguide_b_m: float) -> ProbeDesign:
    """Quarter-wave probe and quarter-guide-wavelength backshort for a TE10 waveguide.

    The probe is a monopole launching into the guide; the shorted back wall reflects, and
    placing the probe a quarter *guide* wavelength in front of it makes the reflection add
    in phase. The guide wavelength is longer than free space:

        lambda_g = lambda_0 / sqrt(1 - (lambda_0 / lambda_c)^2),   lambda_c = 2a for TE10

    Using the free-space quarter wave for the backshort instead of the guide value is a
    classic and expensive mistake — at 21 cm in WR-650 they differ by 16 mm.

    **Verified against a published build.** The PhysicsOpenLab 21 cm horn uses a 146 x 117 mm
    oil-can waveguide with a 52.5 mm probe 76.4 mm from the backshort; this function returns
    52.8 mm and 76.4 mm.
    """
    if waveguide_a_m <= 0 or waveguide_b_m <= 0:
        raise ValueError("waveguide dimensions must be positive")
    lam = wavelength_m(freq_hz)
    cutoff_lambda = 2.0 * waveguide_a_m
    cutoff_freq = C_M_S / cutoff_lambda
    if lam >= cutoff_lambda:
        raise ValueError(
            f"{freq_hz / 1e6:.1f} MHz is below this waveguide's {cutoff_freq / 1e6:.1f} MHz "
            f"cutoff — nothing propagates. The broad wall must exceed {lam / 2 * 1000:.0f} mm."
        )
    guide_lambda = lam / math.sqrt(1.0 - (lam / cutoff_lambda) ** 2)

    notes = [
        "Probe length is the free-space quarter wave; the backshort distance is a quarter "
        "GUIDE wavelength. They are different numbers and swapping them is a common error.",
        "Both are starting points. Match is sensitive to probe length and diameter, so "
        "expect to trim while watching a VNA — leave the probe long and cut it down.",
        "The probe goes on the centreline of the broad wall, where the TE10 electric field "
        "is strongest.",
    ]
    # Single-mode operation: TE20 turns on when the free-space wavelength drops below a.
    if lam < waveguide_a_m:
        notes.append(
            f"WARNING: at {freq_hz / 1e6:.1f} MHz this guide is overmoded (TE20 propagates "
            f"above {C_M_S / waveguide_a_m / 1e6:.0f} MHz). The single-mode assumptions "
            "behind this design, and behind the horn gain model, no longer hold."
        )
    if lam > 0.95 * cutoff_lambda:
        notes.append(
            "Operating close to cutoff: guide wavelength changes steeply with frequency "
            "here, so the backshort position is sharply tuned and the usable bandwidth is "
            "narrow."
        )
    if waveguide_b_m > waveguide_a_m:
        notes.append(
            "The narrow wall b is larger than the broad wall a — check the dimensions are "
            "the right way round, since a sets the cutoff."
        )

    return ProbeDesign(
        freq_hz=freq_hz,
        waveguide_a_m=waveguide_a_m,
        waveguide_b_m=waveguide_b_m,
        cutoff_freq_hz=cutoff_freq,
        guide_wavelength_m=guide_lambda,
        backshort_distance_m=guide_lambda / 4.0,
        probe_length_m=lam / 4.0,
        notes=tuple(notes),
    )
