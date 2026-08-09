"""Amplifier stability: will this thing oscillate? (N1)

The highest-value milestone in the receiver track, and it goes second rather than later
because of what the failure looks like rather than because it is hard. An unstable amplifier
does not announce itself. It gives you a noise floor that will not sit still, spurs that come
and go, a system that behaves differently when you touch the case or move the coax — a
weekend of confusion, blamed on the SDR, the cable, the sun, and eventually the sky.

The check costs microseconds and is decidable in closed form. There is no excuse for a tool
that reads S-parameters not to run it.

**Two questions, and only the second one is the useful one.**

*Unconditionally stable* means the device cannot oscillate into **any** passive termination —
whatever you build, whatever the antenna does when it rains, it is safe. *Conditionally* (or
"potentially") unstable means there exist passive source or load matches that make it
oscillate, and the stability circles say exactly which ones. Most real low-noise transistors
are potentially unstable over part of their range, so "potentially unstable" is a normal
answer that means *pay attention*, not *this part is broken*.

**Three equivalent tests, and why all three are here.**

Rollett's ``K`` with ``|Δ|`` is the classical pair, and it is two numbers — you cannot rank
two devices by it, only pass or fail them. The ``μ`` factor is a single number that is
directly comparable: bigger is more stable, and ``μ > 1`` is exactly unconditional stability.
Both are implemented, and :func:`is_unconditionally_stable` cross-checks them against each
other, because a disagreement means one of them is wrong.

The tests here verify all of it against something better than another formula: the
**definition**. Unconditional stability means ``|Γin| < 1`` for every passive load and
``|Γout| < 1`` for every passive source, which is checkable by brute force over the unit
disk. K, μ, and that brute-force sweep agree on 4000 random networks.

References
----------
Pozar, *Microwave Engineering*, ch. 12 — Example 12.1 is the anchor (K = 0.607,
|Δ| = 0.696 for an HP HFET-102 at 2 GHz), along with its two stability circles.
Edwards & Sinsky (1992), *A new criterion for linear 2-port stability* — the μ factor.
"""

from __future__ import annotations

import cmath
import math
from dataclasses import dataclass, field

import numpy as np

from jansky_forge.twoport import TwoPort

#: Below this, ``|S12·S21|`` is treated as a unilateral device rather than divided by. K and
#: the stability circles both have it in a denominator, and a device with genuinely zero
#: reverse transmission cannot feed its output back to its input at all — so it is stable
#: whenever both ports are, and the circle "at infinity" is not a useful object.
UNILATERAL_FLOOR = 1e-12


def determinant(s: np.ndarray) -> complex:
    """Δ = S11·S22 − S12·S21, the S-matrix determinant.

    Appears in every stability expression, and ``|Δ| < 1`` is half of the classical
    criterion. It is **not** on its own a statement about behaviour at the reference
    impedance — that is ``|S11| < 1 and |S22| < 1``, and the two come apart in both
    directions. ``S11 = 1.5, S12 = 0, S21 = 5, S22 = 0.1`` has ``|Δ| = 0.15`` and is unstable
    at Z0; ``S11 = S22 = 0, S12 = S21 = 1.2`` has ``|Δ| = 1.44`` and is stable at Z0.
    """
    return complex(s[0, 0] * s[1, 1] - s[0, 1] * s[1, 0])


def is_passive(s: np.ndarray) -> bool:
    """Can this network deliver more power than it is given, into any termination?

    The test is the largest singular value of S: ``σmax ≤ 1`` means the scattering matrix is
    a contraction, so no termination can extract net power, and the device is unconditionally
    stable as a matter of arithmetic.

    **This is the test for "does stability need checking", and ``|S21| > 1`` is not.** A
    lossless filter in front of an unstable amplifier leaves K, μ and the unstable loads
    exactly where they were while pushing ``|S21|`` below 1 — a perfectly ordinary
    "filtered LNA module" ``.s2p``. Gating on gain would skip precisely the device the check
    exists for. Activity can also live entirely in the reflection coefficients: a
    negative-resistance stage with ``|S11| = 1.6`` and ``|S21| = 0.5`` has ``μ = −1.9``.
    """
    return bool(np.linalg.svd(np.asarray(s), compute_uv=False).max() <= 1.0)


def rollett_k(s: np.ndarray) -> float:
    """Rollett's stability factor.

    K = (1 − |S11|² − |S22|² + |Δ|²) / (2·|S12·S21|)

    ``K > 1`` **and** ``|Δ| < 1`` together mean unconditionally stable. K alone does not —
    that is the classic misuse, and it is why this function is rarely the one you want.
    Use :func:`is_unconditionally_stable`, or :func:`mu_load` if you want a number you can
    compare between devices.

    Returns infinity for a unilateral device, which cannot feed back and so has no K.
    """
    feedback = abs(s[0, 1] * s[1, 0])
    if feedback < UNILATERAL_FLOOR:
        return math.inf
    numerator = 1 - abs(s[0, 0]) ** 2 - abs(s[1, 1]) ** 2 + abs(determinant(s)) ** 2
    return float(numerator / (2 * feedback))


def mu_load(s: np.ndarray) -> float:
    """The μ factor: geometric distance from the origin to the nearest unstable **load**.

    μ = (1 − |S11|²) / (|S22 − Δ·S11*| + |S12·S21|)

    ``μ > 1`` is necessary *and sufficient* for unconditional stability — one number, no
    companion condition, and unlike K it is **comparable**: of two devices the one with the
    larger μ is more stable, and μ is literally how far into the Smith chart you can go
    before finding a load that oscillates. μ = 1.4 means every load out to |Γ| = 1.4 is
    safe, so the passive region (|Γ| ≤ 1) has margin.

    That geometric reading is exact, not a metaphor: μ equals the distance from the origin
    to the nearest point of the load stability circle, ``|C_L| − R_L``. The tests assert the
    identity, which ties this function and :func:`load_stability_circle` together — if either
    is wrong they stop agreeing.

    Infinite only when no load can reach the input at all: no feedback *and* ``S22 = 0``. A
    unilateral device with a real output match has a perfectly finite μ of ``1/|S22|``, and
    it is greater than 1 exactly when that output is passive.
    """
    denominator = abs(s[1, 1] - determinant(s) * np.conj(s[0, 0])) + abs(s[0, 1] * s[1, 0])
    if denominator < UNILATERAL_FLOOR:
        return math.inf
    return float((1 - abs(s[0, 0]) ** 2) / denominator)


def mu_source(s: np.ndarray) -> float:
    """The μ′ factor: the same distance measured in the **source** plane.

    μ′ = (1 − |S22|²) / (|S11 − Δ·S22*| + |S12·S21|)

    ``μ`` and ``μ′`` cross the value 1 together — either alone decides unconditional
    stability — but they are different numbers, and which one is smaller tells you which
    termination is the dangerous one to get wrong.
    """
    denominator = abs(s[0, 0] - determinant(s) * np.conj(s[1, 1])) + abs(s[0, 1] * s[1, 0])
    if denominator < UNILATERAL_FLOOR:
        return math.inf
    return float((1 - abs(s[1, 1]) ** 2) / denominator)


def is_unconditionally_stable(s: np.ndarray) -> bool:
    """Can this device oscillate into *any* passive termination?

    Evaluates both the classical (K > 1 and |Δ| < 1) and the μ > 1 criteria and requires them
    to agree. They are provably equivalent, so a disagreement is a bug in one of them — this
    is the same reasoning that put two independent routes into the M4 seam.
    """
    if abs(s[0, 1] * s[1, 0]) < UNILATERAL_FLOOR:
        # No feedback path. It cannot oscillate as a two-port; it only needs both ports
        # passive. (An amplifier with |S11| > 1 is a negative-resistance device and unstable
        # on its own account.)
        return bool(abs(s[0, 0]) < 1 and abs(s[1, 1]) < 1)
    classical = rollett_k(s) > 1 and abs(determinant(s)) < 1
    geometric = mu_load(s) > 1
    if classical != geometric:  # pragma: no cover - equivalent by construction
        raise AssertionError(
            f"K/Δ says {classical} and μ says {geometric} for the same device. These criteria "
            "are provably equivalent, so one of them is implemented wrong."
        )
    return classical


@dataclass(frozen=True)
class StabilityCircle:
    """The boundary between terminations that are safe and terminations that oscillate.

    On this circle ``|Γin|`` (or ``|Γout|``) is **exactly 1** — that is what the circle is,
    and the tests check it by evaluating the reflection coefficient at 500 points around it
    rather than by re-deriving the formula.

    The circle alone is not the answer: you also need to know **which side of it is safe**,
    and that is not always the outside. :attr:`stable_region` says.
    """

    #: Which termination plane this constrains: ``"source"`` (Γs) or ``"load"`` (ΓL).
    plane: str
    center: complex
    radius: float
    #: ``"inside"`` or ``"outside"`` — where the *stable* terminations are.
    stable_region: str
    #: True when every passive termination is safe: the circle misses the unit disk entirely.
    excludes_passive: bool

    def contains(self, gamma: complex) -> bool:
        """Is this termination inside the circle?"""
        return abs(gamma - self.center) < self.radius

    def is_stable(self, gamma: complex) -> bool:
        """Is this termination on the safe side?"""
        inside = self.contains(gamma)
        return inside if self.stable_region == "inside" else not inside

    def summary(self) -> str:
        where = (
            "excludes every passive termination"
            if self.excludes_passive
            else "cuts the Smith chart"
        )
        return (
            f"{self.plane} stability circle: centre {abs(self.center):.3f}"
            f"∠{math.degrees(cmath.phase(self.center)):+.1f}°, radius {self.radius:.3f}; "
            f"stable {self.stable_region}, {where}"
        )


def _stability_circle(s: np.ndarray, plane: str) -> StabilityCircle:
    delta = determinant(s)
    # The load circle constrains ΓL and is written in S22; the source circle mirrors it.
    if plane == "load":
        primary, other = s[1, 1], s[0, 0]
    else:
        primary, other = s[0, 0], s[1, 1]
    denominator = abs(primary) ** 2 - abs(delta) ** 2
    if abs(denominator) < UNILATERAL_FLOOR:
        raise ValueError(
            f"the {plane} stability circle is degenerate for this device (|S| = |Δ|), so the "
            "boundary is a line rather than a circle. Nothing here is wrong with the device; "
            "this function simply cannot express it."
        )
    center = complex(np.conj(primary - delta * np.conj(other)) / denominator)
    radius = float(abs(s[0, 1] * s[1, 0] / denominator))

    # Which side is safe? Decide it from a termination whose answer is already known rather
    # than from a rule of thumb: with Γ = 0 the input sees exactly S11, so if |S11| < 1 the
    # centre of the Smith chart is stable, and the stable region is whichever side holds it.
    origin_is_stable = abs(other) < 1
    origin_inside = abs(center) < radius
    stable_region = "inside" if origin_is_stable == origin_inside else "outside"

    # The passive region is safe in its entirety when the circle and the unit disk do not
    # overlap -- and, if "inside" is the stable side, when the unit disk sits within it.
    if stable_region == "outside":
        excludes_passive = abs(center) > radius + 1
    else:
        excludes_passive = radius > abs(center) + 1
    return StabilityCircle(plane, center, radius, stable_region, excludes_passive)


def load_stability_circle(s: np.ndarray) -> StabilityCircle:
    """Loads that make ``|Γin| = 1``. Anchored on Pozar Ex 12.1: C = 1.36∠47°, R = 0.50."""
    return _stability_circle(s, "load")


def source_stability_circle(s: np.ndarray) -> StabilityCircle:
    """Sources that make ``|Γout| = 1``. Anchored on Pozar Ex 12.1: C = 1.13∠68.5°, R = 0.199."""
    return _stability_circle(s, "source")


def max_stable_gain_db(s: np.ndarray) -> float:
    """MSG = |S21/S12|, in dB. The ceiling for a *potentially unstable* device.

    Meaningful only once the device has been stabilised (resistive loading, feedback), which
    is why it is quoted for K < 1 parts. It ignores the match entirely, so treat it as an
    upper bound you will not reach rather than a design target.
    """
    if abs(s[1, 0]) == 0.0:
        return -math.inf  # no forward transmission: no gain, stable or otherwise
    if abs(s[0, 1]) < UNILATERAL_FLOOR:
        return math.inf
    return float(10 * math.log10(abs(s[1, 0] / s[0, 1])))


def max_available_gain_db(s: np.ndarray) -> float:
    """MAG = |S21/S12|·(K − √(K²−1)), in dB. **Only exists when K > 1.**

    The most gain a simultaneously conjugate-matched, unconditionally stable device can give.
    Asking for it on a potentially unstable part is asking for a number that does not exist,
    so this raises rather than returning MSG under a different name — quietly substituting one
    for the other is how a K < 1 device ends up quoted at its MSG in a link budget.
    """
    if not is_unconditionally_stable(s):
        k = rollett_k(s)
        raise ValueError(
            f"this device is not unconditionally stable (K = {k:.3f}, |Δ| = "
            f"{abs(determinant(s)):.3f}, μ = {mu_load(s):.3f}), so it has no maximum available "
            "gain — there are passive loads for which the gain is unbounded. MSG "
            "(max_stable_gain_db) is the relevant ceiling, and it applies only after the "
            "device has been stabilised. Note that K > 1 alone is NOT enough: |Δ| < 1 is the "
            "other half, and a device can satisfy one without the other."
        )
    if math.isinf(rollett_k(s)):
        # Unilateral. MAG is finite — it is the S12 → 0 limit of MSG·(K − √(K²−1)), which is
        # the unilateral transducer gain with both ports conjugate-matched. Returning MSG
        # (infinite) would claim a unilateral amplifier can deliver unlimited power gain.
        return float(
            10 * math.log10(abs(s[1, 0]) ** 2 / ((1 - abs(s[0, 0]) ** 2) * (1 - abs(s[1, 1]) ** 2)))
        )
    k = rollett_k(s)
    # Algebraically identical to MSG + 10·log10(K − √(K²−1)), and numerically stable. The
    # subtractive form cancels catastrophically for large K: at K = 1.3e8 it is 5.8 dB high,
    # and by K = 3.8e8 it underflows to log10(0).
    return float(max_stable_gain_db(s) - 10 * math.log10(k + math.sqrt(k * k - 1)))


@dataclass(frozen=True)
class Stability:
    """The stability of one device at one frequency."""

    freq_hz: float
    k: float
    delta: complex
    mu: float
    mu_source: float
    is_unconditional: bool

    @property
    def margin(self) -> float:
        """How much room there is: the **tighter** of the two μ factors.

        μ and μ′ cross 1 together, so the verdict never depends on which you use — but the
        *margin* does, and μ′ is the smaller one about half the time. Reporting μ alone would
        name the wrong frequency as "where it will oscillate first" whenever the source plane
        is the binding one.
        """
        return min(self.mu, self.mu_source)

    def summary(self) -> str:
        verdict = "unconditionally stable" if self.is_unconditional else "POTENTIALLY UNSTABLE"
        return (
            f"{self.freq_hz / 1e6:9.3f} MHz  K = {self.k:6.3f}  |Δ| = {abs(self.delta):5.3f}  "
            f"μ = {self.mu:6.3f}  {verdict}"
        )


@dataclass(frozen=True)
class StabilityReport:
    """A device's stability across its whole measured range.

    The per-frequency verdicts matter less than the two summary facts: whether it is safe
    everywhere, and **where the worst point is**. An amplifier that is comfortable in band and
    marginal at 4 GHz is a normal amplifier and a real hazard, because the oscillation does
    not care that you were not using that frequency.
    """

    points: tuple[Stability, ...]
    source: str = ""
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_unconditional(self) -> bool:
        """Safe into any passive termination, at **every** measured frequency."""
        return all(point.is_unconditional for point in self.points)

    @property
    def worst(self) -> Stability:
        """The frequency with the least margin — where it will oscillate first."""
        return min(self.points, key=lambda point: point.margin)

    @property
    def unstable_points(self) -> tuple[Stability, ...]:
        return tuple(point for point in self.points if not point.is_unconditional)

    def summary(self) -> str:
        if self.is_unconditional:
            worst = self.worst
            return (
                f"unconditionally stable across all {len(self.points)} points; tightest "
                f"margin μ = {worst.mu:.3f} at {worst.freq_hz / 1e6:.3f} MHz"
            )
        unstable = self.unstable_points
        worst = self.worst
        if len(unstable) == 1:
            span = f"{unstable[0].freq_hz / 1e6:.3f} MHz"
        else:
            # "1.9-2.1 GHz" reads as a band. Only say it when the unstable points really are
            # consecutive; otherwise say they are scattered, because which frequencies are
            # safe in between is the actionable part.
            indices = [i for i, point in enumerate(self.points) if not point.is_unconditional]
            contiguous = indices == list(range(indices[0], indices[-1] + 1))
            joiner = "-" if contiguous else " and "
            span = (
                f"{unstable[0].freq_hz / 1e6:.3f}{joiner}{unstable[-1].freq_hz / 1e6:.3f} MHz"
                + ("" if contiguous else ", not contiguous")
            )
        return (
            f"POTENTIALLY UNSTABLE at {len(unstable)} of {len(self.points)} points ({span}); "
            f"worst μ = {worst.mu:.3f} at {worst.freq_hz / 1e6:.3f} MHz"
        )


def analyse(network: TwoPort) -> StabilityReport:
    """Stability at every frequency in the file.

    Checking only the design frequency is the mistake this signature exists to prevent. A
    transistor's own gain is what makes it dangerous, and it has the most gain **below** the
    band you want to use it in — so the frequency where an amplifier oscillates is usually one
    you were not thinking about.
    """
    points = tuple(
        Stability(
            freq_hz=float(freq),
            k=rollett_k(network.s[index]),
            delta=determinant(network.s[index]),
            mu=mu_load(network.s[index]),
            mu_source=mu_source(network.s[index]),
            is_unconditional=is_unconditionally_stable(network.s[index]),
        )
        for index, freq in enumerate(network.freq_hz)
    )
    notes: list[str] = []
    unstable = [point for point in points if not point.is_unconditional]
    if unstable:
        notes.append(
            f"potentially unstable at {len(unstable)} of {len(points)} measured frequencies. "
            "This is normal for a low-noise transistor and does not mean the part is faulty — "
            "it means the source and load matches are not free choices. The stability circles "
            "say which terminations to avoid."
        )
        notes.append(
            "Stability is only assured across the frequencies in this file. A device is "
            "usually most dangerous below its intended band, where it has more gain, and a "
            "vendor's sweep often does not go there."
        )
    else:
        notes.append(
            "unconditionally stable across the measured range: no passive source or load can "
            "make it oscillate. Outside that range, this file says nothing."
        )
    return StabilityReport(points=points, source=network.source, notes=tuple(notes))


def stability_notes(network: TwoPort) -> tuple[str, ...]:
    """The one-line warning to attach to any network the tool touches.

    Empty for a network that is stable everywhere, which is automatically the case for a
    passive one — so no gate is needed and none is applied. An earlier version skipped the
    analysis entirely when ``max|S21| ≤ 1``, on the theory that only amplifiers can
    oscillate. That is false, and it failed in the direction that matters: putting a lossless
    filter in front of an unstable amplifier leaves K, μ and the unstable loads untouched
    while dropping ``|S21|`` below 1, so the warning vanished from exactly the file — a
    filtered LNA module — most likely to be handed to this tool.
    """
    report = analyse(network)
    if report.is_unconditional:
        return ()
    worst = report.worst
    return (
        f"stability: potentially unstable at {len(report.unstable_points)} of "
        f"{len(report.points)} frequencies, worst μ = {worst.mu:.3f} at "
        f"{worst.freq_hz / 1e6:.3f} MHz. Check the stability circles before choosing matches.",
    )
