"""Tier 2: check the closed-form answer against real numerics (M6).

Everything up to here is Tier 1 — closed form, microseconds, and honest about where it
stops. This module is the button that says *check that*. It solves the same antenna with a
method-of-moments code, which does not assume the flare is optimum, does not assume elements
are uncoupled, and does not care what a textbook approximation was fitted to.

**What Tier 2 buys that Tier 1 cannot.** Three things Tier 1 structurally cannot know:

* **Mutual coupling.** Pattern multiplication treats array elements as independent. Real
  ones are not, which is exactly why M5's Radio JOVE dual dipole overshoots its published
  gain by about a dB.
* **Element-level design.** A Yagi's gain depends on element lengths and spacings, not just
  boom length. M5 refused to model that and pointed here; this is where the promise is kept.
* **Feed impedance.** Tier 1 has no idea what your antenna will look like to a transmitter
  or an LNA. A MoM solve gives a complex feed impedance, which is what M7's VNA measurements
  will be compared against.

**Backends are pluggable, and the default is deliberate.** ``pymininec`` is pure Python and
MIT-licensed, so it installs everywhere with no compiler and no licence entanglement. The
NEC2 lineage is more capable but GPL, so where it is used at all it is used at arm's length —
:func:`to_nec_deck` writes an input file for someone else's solver rather than linking one.
:class:`MomBackend` is the seam a future backend (a maintained NEC2 wrapper, ORI's Arcanum
when it grows code) slots into without anything above it changing.

**This is an optional extra.** ``pip install jansky-forge[mom]``. Without it the package is
unchanged and Tier 1 still works; :func:`available_backends` reports what you have.

**Verification.** The backend reproduces a half-wave dipole's 2.15 dBi to 0.03 dB, and
returns a feed impedance near 73 ohms that goes correctly capacitive when the element is cut
short — which is the behaviour Tier 1 cannot represent at all.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

import numpy as np

from jansky_forge.units import wavelength_m
from jansky_forge.wires import GroundType

Point3 = tuple[float, float, float]


@dataclass(frozen=True)
class WireSpec:
    """One straight conductor, in metres, in a right-handed frame with z up."""

    start_m: Point3
    end_m: Point3
    radius_m: float
    segments: int

    def __post_init__(self) -> None:
        if self.radius_m <= 0:
            raise ValueError("wire radius must be positive")
        if self.segments < 1:
            raise ValueError("a wire needs at least one segment")
        if self.length_m <= 0:
            raise ValueError("a wire needs non-zero length")

    @property
    def length_m(self) -> float:
        return math.dist(self.start_m, self.end_m)


@dataclass(frozen=True)
class WireModel:
    """A wire antenna, described in a way no particular solver owns.

    Segmentation is the one thing a user of a MoM code must get right and is most likely to
    get wrong: too few segments and the answer is wrong, too many and the matrix solve grows
    as the cube. :func:`check_segmentation` states the rule rather than leaving it folklore.
    """

    name: str
    wires: tuple[WireSpec, ...]
    #: Index into ``wires`` of the driven element, and which of its segments is fed.
    feed_wire: int = 0
    feed_segment: int | None = None
    #: Drive every wire instead of just ``feed_wire``. Real arrays are often fed in
    #: parallel, and whether the neighbours are driven or parasitic is a different antenna
    #: with a different answer — so it is explicit rather than assumed.
    drive_all: bool = False
    ground: GroundType | None = None
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.wires:
            raise ValueError("a model needs at least one wire")
        if not 0 <= self.feed_wire < len(self.wires):
            raise ValueError(f"feed_wire {self.feed_wire} is not one of {len(self.wires)} wires")

    @property
    def driven(self) -> WireSpec:
        return self.wires[self.feed_wire]

    @property
    def feed_pulse(self) -> int:
        """Which segment carries the source: the middle of the driven element by default."""
        return self.feed_segment if self.feed_segment is not None else self.driven.segments // 2


#: Segments per wavelength below which a MoM result should not be trusted. The usual
#: guidance for thin-wire codes is at least 10 per wavelength; 20 is comfortable.
MIN_SEGMENTS_PER_WAVELENGTH = 10


def check_segmentation(model: WireModel, freq_hz: float) -> tuple[str, ...]:
    """Warnings about a model's segmentation. Empty means it looks sound."""
    lam = wavelength_m(freq_hz)
    warnings = []
    for index, wire in enumerate(model.wires):
        per_wavelength = wire.segments / (wire.length_m / lam)
        if per_wavelength < MIN_SEGMENTS_PER_WAVELENGTH:
            warnings.append(
                f"Wire {index} has only {per_wavelength:.1f} segments per wavelength; below "
                f"{MIN_SEGMENTS_PER_WAVELENGTH} the solution is unreliable. Increase segments."
            )
        if wire.radius_m > wire.length_m / wire.segments:
            warnings.append(
                f"Wire {index}'s radius exceeds its segment length. Thin-wire theory assumes "
                "the opposite, so this result is outside the method's assumptions."
            )
    return tuple(warnings)


@dataclass(frozen=True)
class MomResult:
    """What a solver returned."""

    backend: str
    freq_hz: float
    gain_dbi: float
    peak_elevation_deg: float
    feed_impedance_ohm: complex | None = None
    notes: tuple[str, ...] = ()

    @property
    def swr(self) -> float | None:
        """SWR against 50 ohms — the number that decides whether it will even load up."""
        if self.feed_impedance_ohm is None:
            return None
        reflection = abs((self.feed_impedance_ohm - 50.0) / (self.feed_impedance_ohm + 50.0))
        if reflection >= 1.0:  # pragma: no cover - only for a non-physical impedance
            return math.inf
        return (1 + reflection) / (1 - reflection)

    def summary(self) -> str:
        text = f"{self.backend}: {self.gain_dbi:.2f} dBi"
        if self.feed_impedance_ohm is not None:
            z = self.feed_impedance_ohm
            text += f", Z = {z.real:.1f}{z.imag:+.1f}j ohm"
            if self.swr is not None:
                text += f" (SWR {self.swr:.2f}:1 vs 50 ohm)"
        return text


@runtime_checkable
class MomBackend(Protocol):
    """A method-of-moments solver this package can drive."""

    name: str

    def available(self) -> bool:
        """Is this backend usable in the current environment?"""
        ...

    def solve(self, model: WireModel, freq_hz: float) -> MomResult:
        """Solve ``model`` at ``freq_hz``."""
        ...


def _feed_pulse_index(solver, driven_wire, model: WireModel) -> int:
    """Global pulse index of the driven element's feed point.

    The solver numbers pulses sequentially across every wire, so "segment 10 of wire 2" is
    not something it accepts directly. Pulses carry a back-reference to the wire that owns
    them, which is the reliable way to find the right one — counting segments by hand breaks
    the moment a model gains a wire or a junction removes a pulse.
    """
    owned = [pulse.idx for pulse in solver.pulses if pulse.geobj is driven_wire]
    if not owned:  # pragma: no cover - only if the solver drops a whole wire
        raise RuntimeError(
            f"the solver produced no pulses on the driven element of {model.name!r}; "
            "the geometry may be degenerate"
        )
    if model.feed_segment is not None:
        if not 0 <= model.feed_segment < len(owned):
            raise ValueError(
                f"feed_segment {model.feed_segment} is out of range for a driven element "
                f"with {len(owned)} feedable pulses"
            )
        return owned[model.feed_segment]
    return owned[len(owned) // 2]


class PyMininecBackend:
    """The default Tier-2 backend: ``pymininec``, pure Python and MIT-licensed.

    Chosen over the NEC2 lineage on purpose. NEC2-derived codes are more capable, but the
    maintained wrappers are GPL and frozen since 2019, while this installs with no compiler
    on every platform this package supports. MININEC's known weakness is its ground model,
    so ground-mounted results here deserve more caution than free-space ones — which is
    stated in the results rather than left to folklore.
    """

    name = "pymininec"

    def available(self) -> bool:
        try:
            import mininec.mininec  # noqa: F401
        except ImportError:
            return False
        return True

    def solve(self, model: WireModel, freq_hz: float) -> MomResult:
        try:
            from mininec.mininec import (
                Angle,
                Excitation,
                Geo_Container,
                Medium,
                Mininec,
                Wire,
            )
        except ImportError as exc:  # pragma: no cover - exercised by the availability test
            raise RuntimeError(
                "pymininec is not installed. It is an optional extra: "
                "pip install 'jansky-forge[mom]'. Note the distribution is named "
                "'pymininec' but the import is 'mininec'."
            ) from exc

        wires = [Wire(w.segments, *w.start_m, *w.end_m, w.radius_m) for w in model.wires]
        media = None
        if model.ground is not None:
            conductivity = (
                1e9
                if math.isinf(model.ground.conductivity_s_per_m)
                else model.ground.conductivity_s_per_m
            )
            media = [Medium(model.ground.relative_permittivity, conductivity)]
        solver = Mininec(freq_hz / 1e6, Geo_Container(geo=wires), media=media)
        driven = range(len(wires)) if model.drive_all else (model.feed_wire,)
        sources = []
        for index in driven:
            source = Excitation(1.0)
            solver.register_source(source, _feed_pulse_index(solver, wires[index], model))
            sources.append(source)
        solver.compute()

        # Zenith angle 0..180, azimuth 0..360, 5 degree steps.
        zenith, azimuth = Angle(0, 5, 37), Angle(0, 5, 73)
        solver.compute_far_field(zenith, azimuth)
        gain = np.asarray(solver.far_field.gain)
        # The last axis holds [component_1, component_2, total] in dBi, where the total is
        # the sum of the two polarization components. Reading index 0 gives one polarization
        # only — which for a horizontally-polarized Yagi is nearly the whole answer missing,
        # and shows up as a physically impossible negative peak gain.
        total = gain[..., 2] if gain.ndim == 3 else gain
        peak_index = np.unravel_index(int(np.argmax(total)), total.shape)
        zenith_deg = float(peak_index[0]) * 5.0

        notes = list(check_segmentation(model, freq_hz))
        notes.extend(model.notes)
        if model.ground is not None:
            notes.append(
                "Over ground: MININEC's ground model is its known weak point, so treat this "
                "as less trustworthy than the same model solved in free space."
            )
        return MomResult(
            backend=self.name,
            freq_hz=freq_hz,
            gain_dbi=float(total.max()),
            peak_elevation_deg=90.0 - zenith_deg,
            feed_impedance_ohm=complex(sources[0].impedance),
            notes=tuple(notes),
        )


#: Backends in preference order. Adding one — a maintained NEC2 wrapper, or ORI's Arcanum
#: once it has production code — means appending here and implementing two methods.
BACKENDS: tuple[MomBackend, ...] = (PyMininecBackend(),)


def available_backends() -> list[MomBackend]:
    return [backend for backend in BACKENDS if backend.available()]


def default_backend() -> MomBackend:
    """The first usable backend, or a clear explanation of how to get one."""
    usable = available_backends()
    if not usable:
        raise RuntimeError(
            "No method-of-moments backend is installed. Tier 2 is an optional extra: "
            "pip install 'jansky-forge[mom]'. Tier 1 works without it."
        )
    return usable[0]


# --------------------------------------------------------------------------------------
# Model builders
# --------------------------------------------------------------------------------------


def dipole_model(
    *,
    freq_hz: float,
    length_m: float,
    radius_m: float = 0.001,
    segments: int = 21,
    height_m: float | None = None,
    ground: GroundType | None = None,
) -> WireModel:
    """A centre-fed straight dipole, along x, optionally raised over ground.

    An odd segment count puts a segment centre exactly at the feed point, which is what the
    source needs; even counts straddle it and shift the effective feed position.
    """
    if segments % 2 == 0:
        segments += 1
    z = height_m if height_m is not None else 0.0
    return WireModel(
        name="dipole",
        wires=(WireSpec((-length_m / 2, 0.0, z), (length_m / 2, 0.0, z), radius_m, segments),),
        ground=ground,
        notes=(("Free space." if ground is None else f"Over {ground.name} at {z:g} m."),),
    )


def yagi_model(
    *,
    freq_hz: float,
    elements_m: list[tuple[float, float]],
    radius_m: float,
    driven_index: int = 1,
    segments_per_element: int = 21,
) -> WireModel:
    """A Yagi from real element lengths and positions — what M5 refused to model.

    ``elements_m`` is ``[(length, boom_position), ...]`` in metres, in boom order starting
    at the reflector. Elements lie along x; the boom runs along y.

    ``radius_m`` is required and has no default on purpose: element diameter measurably
    changes a Yagi's bandwidth and tuning, and published designs frequently omit it. Guessing
    it silently would put an invented number inside a result that looks authoritative.
    """
    if len(elements_m) < 2:
        raise ValueError("a Yagi needs at least a driven element and one parasitic")
    if not 0 <= driven_index < len(elements_m):
        raise ValueError("driven_index is not one of the elements")
    if segments_per_element % 2 == 0:
        segments_per_element += 1
    wires = tuple(
        WireSpec(
            (-length / 2, position, 0.0),
            (length / 2, position, 0.0),
            radius_m,
            segments_per_element,
        )
        for length, position in elements_m
    )
    return WireModel(
        name=f"{len(elements_m)}-element Yagi",
        wires=wires,
        feed_wire=driven_index,
        notes=(
            f"Element radius {radius_m * 1000:.1f} mm. If the source did not publish a "
            "diameter, this is an assumption and it affects the answer.",
        ),
    )


def dipole_array_model(
    *,
    freq_hz: float,
    length_m: float,
    spacing_m: float,
    n_elements: int = 2,
    radius_m: float = 0.001,
    segments: int = 21,
    height_m: float = 0.0,
    ground: GroundType | None = None,
    drive_all: bool = True,
) -> WireModel:
    """Parallel dipoles side by side — the geometry whose coupling Tier 1 cannot see.

    ``drive_all`` defaults to True because that is what "an array" usually means and what
    Radio JOVE's unphased pair actually is. Set it False to make the neighbours parasitic —
    a genuinely different antenna with a genuinely different answer, which is why the choice
    is explicit rather than buried.
    """
    if n_elements < 2:
        raise ValueError("an array needs at least two elements")
    if segments % 2 == 0:
        segments += 1
    offset = (n_elements - 1) * spacing_m / 2.0
    wires = tuple(
        WireSpec(
            (-length_m / 2, index * spacing_m - offset, height_m),
            (length_m / 2, index * spacing_m - offset, height_m),
            radius_m,
            segments,
        )
        for index in range(n_elements)
    )
    return WireModel(
        name=f"{n_elements}-dipole array",
        wires=wires,
        ground=ground,
        drive_all=drive_all,
        notes=(
            (
                "All elements driven in parallel."
                if drive_all
                else "Only the first element is driven; the rest are parasitic."
            )
            + " Mutual coupling is represented either way, which is the entire point of "
            "solving this in Tier 2 rather than multiplying patterns.",
        ),
    )


# --------------------------------------------------------------------------------------
# Published element geometry, waiting since M5
# --------------------------------------------------------------------------------------

#: G4CQM 3-element 143.05 MHz Yagi: (element length, boom position) in metres.
#: Published in the BAA Radio Astronomy Group's meteor-antenna note.
GRAVES_3EL_ELEMENTS: list[tuple[float, float]] = [
    (1.076, 0.000),  # reflector
    (0.973, 0.265),  # driven
    (0.836, 0.500),  # director
]

#: W7ZOI 7-element 143.05 MHz Yagi, same source. The driven element is folded in the
#: original; modelled here as a straight dipole, which changes the feed impedance by about
#: four but leaves the pattern essentially alone.
GRAVES_7EL_ELEMENTS: list[tuple[float, float]] = [
    (1.028, 0.000),
    (0.960, 0.248),
    (0.930, 0.565),
    (0.926, 0.945),
    (0.906, 1.331),
    (0.884, 1.802),
    (0.834, 2.377),
]


# --------------------------------------------------------------------------------------
# The comparison
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Comparison:
    """Tier 1 against Tier 2, with a verdict that does not flatter either."""

    analytic_dbi: float
    mom: MomResult
    published_dbi: float | None = None
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def difference_db(self) -> float:
        """MoM minus analytic. Positive means the closed form was pessimistic."""
        return self.mom.gain_dbi - self.analytic_dbi

    @property
    def agrees(self) -> bool:
        """Within 1 dB — about as well as two different methods should be expected to."""
        return abs(self.difference_db) <= 1.0

    def summary(self) -> str:
        verdict = "agree" if self.agrees else "DISAGREE"
        text = (
            f"analytic {self.analytic_dbi:.2f} dBi vs {self.mom.backend} "
            f"{self.mom.gain_dbi:.2f} dBi ({self.difference_db:+.2f} dB) — {verdict}"
        )
        if self.published_dbi is not None:
            text += f"; published {self.published_dbi:.2f} dBi"
        return text


def compare_with_analytic(
    model: WireModel,
    *,
    freq_hz: float,
    analytic_dbi: float,
    published_dbi: float | None = None,
    backend: MomBackend | None = None,
) -> Comparison:
    """Solve a model numerically and set the result beside the closed-form answer.

    Neither number is privileged. A disagreement is information about which assumption
    broke, and the notes say which one to suspect — a Tier-1 model that ignores coupling
    will read high on an array, and an endfire bound will read low on a short boom.
    """
    solver = backend or default_backend()
    result = solver.solve(model, freq_hz)
    notes = []
    difference = result.gain_dbi - analytic_dbi
    if abs(difference) > 1.0:
        notes.append(
            f"The two methods differ by {difference:+.2f} dB, which is more than modelling "
            "noise. Suspect an assumption: Tier 1 ignores mutual coupling (so it reads high "
            "on arrays) and bounds endfire gain assuming a long array (so it reads low on "
            "short booms)."
        )
    if published_dbi is not None:
        notes.append(
            f"Against the published {published_dbi:.2f} dBi: analytic is "
            f"{analytic_dbi - published_dbi:+.2f} dB, MoM is "
            f"{result.gain_dbi - published_dbi:+.2f} dB."
        )
    return Comparison(
        analytic_dbi=analytic_dbi,
        mom=result,
        published_dbi=published_dbi,
        notes=tuple(notes),
    )


# --------------------------------------------------------------------------------------
# NEC deck export — Tier 2 at arm's length
# --------------------------------------------------------------------------------------


def to_nec_deck(model: WireModel, freq_hz: float, *, comment: str | None = None) -> str:
    """Write a NEC2 input deck for this model.

    Deliberately an *export*, not a driver. NEC2's maintained wrappers are GPL and frozen
    since 2019, so rather than link one, this hands you a deck to run in whatever you
    already trust — xnec2c, 4nec2, nec2c. Same reasoning as M2 generating openEMS scripts
    instead of owning an FDTD runtime: rigor without the entanglement.

    Cards emitted: CM/CE comments, GW geometry, GE ground flag, GN ground medium, EX
    voltage source, FR frequency, RP radiation pattern, EN.
    """
    lines = [f"CM {comment or model.name}", "CM generated by jansky-forge", "CE"]
    for index, wire in enumerate(model.wires, start=1):
        x1, y1, z1 = wire.start_m
        x2, y2, z2 = wire.end_m
        lines.append(
            f"GW {index} {wire.segments} {x1:.6f} {y1:.6f} {z1:.6f} "
            f"{x2:.6f} {y2:.6f} {z2:.6f} {wire.radius_m:.6f}"
        )
    lines.append(f"GE {1 if model.ground is not None else 0}")
    if model.ground is not None:
        if math.isinf(model.ground.conductivity_s_per_m):
            lines.append("GN 1")  # perfectly conducting ground
        else:
            lines.append(
                f"GN 2 0 0 0 {model.ground.relative_permittivity:.3f} "
                f"{model.ground.conductivity_s_per_m:.6f}"
            )
    lines.append(f"EX 0 {model.feed_wire + 1} {model.feed_pulse + 1} 0 1.0 0.0")
    lines.append(f"FR 0 1 0 0 {freq_hz / 1e6:.6f} 0")
    lines.append("RP 0 37 73 1000 0.0 0.0 5.0 5.0")
    lines.append("EN")
    return "\n".join(lines) + "\n"
