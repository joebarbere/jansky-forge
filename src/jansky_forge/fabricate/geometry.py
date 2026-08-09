"""Flat developments: turning a horn into shapes you can cut from sheet.

A horn's lateral surface is *developable* — every face is planar (pyramidal) or a cone
frustum (conical), so it can be unrolled onto flat stock with no stretching. This module
does that unrolling exactly, in millimetres, because millimetres are what a ruler reads.

**The dimensions here are the electrical ones.** They describe the inner surface the wave
sees. For thin sheet at 21 cm the difference between inner and outer is a fraction of a
percent, but it is stated rather than assumed away — see :func:`thickness_note`.

Everything returns plain geometry. Rendering (:mod:`~jansky_forge.fabricate.svg`,
:mod:`~jansky_forge.fabricate.dxf`) and paperwork (:mod:`~jansky_forge.fabricate.cutlist`)
are separate, so a new output format never has to re-derive a shape.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

Point = tuple[float, float]


@dataclass(frozen=True)
class Panel:
    """One flat piece to cut, as a closed polygon in millimetres.

    ``polygon`` is the **cut line** — the outline including any seam allowance.
    ``fold_polygon`` is the electrical outline: where the metal actually bends, and what
    the physics in :mod:`jansky_forge.horns` was computed for. With no seam allowance the
    two are identical.
    """

    label: str
    polygon: tuple[Point, ...]
    quantity: int
    fold_polygon: tuple[Point, ...] = ()
    note: str = ""

    def __post_init__(self) -> None:
        if len(self.polygon) < 3:
            raise ValueError(f"{self.label}: a panel needs at least 3 points")
        if self.quantity < 1:
            raise ValueError(f"{self.label}: quantity must be at least 1")

    @property
    def bounds_mm(self) -> tuple[float, float, float, float]:
        """(min_x, min_y, max_x, max_y) of the cut line."""
        xs = [p[0] for p in self.polygon]
        ys = [p[1] for p in self.polygon]
        return min(xs), min(ys), max(xs), max(ys)

    @property
    def size_mm(self) -> tuple[float, float]:
        """Stock footprint: what size offcut this panel needs."""
        x0, y0, x1, y1 = self.bounds_mm
        return x1 - x0, y1 - y0

    @property
    def area_mm2(self) -> float:
        """Shoelace area of the cut line."""
        pts = self.polygon
        total = 0.0
        for i in range(len(pts)):
            x0, y0 = pts[i]
            x1, y1 = pts[(i + 1) % len(pts)]
            total += x0 * y1 - x1 * y0
        return abs(total) / 2.0

    @property
    def perimeter_mm(self) -> float:
        """Cut length — what sets blade wear, and the kerf total."""
        pts = self.polygon
        return sum(math.dist(pts[i], pts[(i + 1) % len(pts)]) for i in range(len(pts)))


@dataclass(frozen=True)
class AnnularSector:
    """A cone frustum's development: a sector of an annulus, in millimetres.

    Kept as radii and an angle rather than flattened to a polygon so DXF can emit true
    arcs. :meth:`polygon` approximates it when a renderer needs points.
    """

    label: str
    inner_radius_mm: float
    outer_radius_mm: float
    angle_deg: float
    quantity: int = 1
    note: str = ""

    def __post_init__(self) -> None:
        if not 0.0 <= self.inner_radius_mm < self.outer_radius_mm:
            raise ValueError(f"{self.label}: need 0 <= inner radius < outer radius")
        if not 0.0 < self.angle_deg < 360.0:
            raise ValueError(
                f"{self.label}: sector angle must be in (0, 360) deg, got {self.angle_deg}"
            )

    def polygon(self, segments: int = 180) -> tuple[Point, ...]:
        """Approximate the sector as a closed polygon, centred on the apex at (0, 0)."""
        half = math.radians(self.angle_deg) / 2.0
        angles = [(-half + i * 2 * half / segments) for i in range(segments + 1)]
        outer = [
            (self.outer_radius_mm * math.sin(a), self.outer_radius_mm * math.cos(a)) for a in angles
        ]
        if self.inner_radius_mm <= 0:
            return (*outer, (0.0, 0.0))
        inner = [
            (self.inner_radius_mm * math.sin(a), self.inner_radius_mm * math.cos(a))
            for a in reversed(angles)
        ]
        return (*outer, *inner)

    @property
    def bounds_mm(self) -> tuple[float, float, float, float]:
        pts = self.polygon()
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        return min(xs), min(ys), max(xs), max(ys)

    @property
    def size_mm(self) -> tuple[float, float]:
        x0, y0, x1, y1 = self.bounds_mm
        return x1 - x0, y1 - y0

    @property
    def area_mm2(self) -> float:
        """Exact: the annulus fraction, not the polygon approximation."""
        fraction = self.angle_deg / 360.0
        return fraction * math.pi * (self.outer_radius_mm**2 - self.inner_radius_mm**2)


@dataclass(frozen=True)
class Development:
    """Everything to cut for one antenna, plus how it goes together."""

    title: str
    panels: tuple[Panel, ...] = ()
    sectors: tuple[AnnularSector, ...] = ()
    #: Facts a builder needs that are not visible in the geometry.
    notes: tuple[str, ...] = ()
    #: Key dimensions to state in the cut list, in millimetres.
    key_dimensions: dict[str, float] = field(default_factory=dict)

    @property
    def total_area_mm2(self) -> float:
        return sum(p.area_mm2 * p.quantity for p in self.panels) + sum(
            s.area_mm2 * s.quantity for s in self.sectors
        )

    @property
    def total_cut_length_mm(self) -> float:
        panel_cut = sum(p.perimeter_mm * p.quantity for p in self.panels)
        sector_cut = sum(
            (
                math.radians(s.angle_deg) * (s.outer_radius_mm + s.inner_radius_mm)
                + 2.0 * (s.outer_radius_mm - s.inner_radius_mm)
            )
            * s.quantity
            for s in self.sectors
        )
        return panel_cut + sector_cut


def _trapezoid(width_throat: float, width_aperture: float, height: float) -> tuple[Point, ...]:
    """Isosceles trapezoid, throat edge on y = 0, centred on x = 0."""
    return (
        (-width_throat / 2.0, 0.0),
        (width_throat / 2.0, 0.0),
        (width_aperture / 2.0, height),
        (-width_aperture / 2.0, height),
    )


def _widen_for_seam(
    width_throat: float, width_aperture: float, height: float, seam_mm: float
) -> tuple[float, float]:
    """Widen a trapezoid so its sloped edges sit ``seam_mm`` outside the fold line.

    Offsetting a sloped edge perpendicular by s moves it horizontally by s/cos(alpha),
    where alpha is the edge's tilt from vertical. Adding s to each half-width would leave
    the flange too narrow on a steeply flared horn, which is the kind of small error that
    only shows up once the metal is cut.
    """
    if seam_mm <= 0:
        return width_throat, width_aperture
    half_flare = (width_aperture - width_throat) / 2.0
    horizontal = seam_mm * math.hypot(height, half_flare) / height
    return width_throat + 2.0 * horizontal, width_aperture + 2.0 * horizontal


def pyramidal_development(
    *,
    waveguide_a_m: float,
    waveguide_b_m: float,
    aperture_a1_m: float,
    aperture_b1_m: float,
    axial_length_m: float,
    seam_allowance_mm: float = 0.0,
    title: str = "Pyramidal horn",
) -> Development:
    """Unroll a pyramidal horn into four trapezoidal panels.

    The horn is a rectangular frustum, so each wall is a planar isosceles trapezoid:

    * **E-flare panels** (top and bottom) span the H-plane width, so their parallel sides
      are ``a`` and ``a1``. Their height is the frustum slant taken in the E-plane,
      sqrt(L^2 + ((b1-b)/2)^2).
    * **H-flare panels** (the two sides) have parallel sides ``b`` and ``b1`` and height
      sqrt(L^2 + ((a1-a)/2)^2).

    The corner edge where adjacent panels meet must come out the same length measured on
    either panel — it does, and the test suite checks it, because that equality is the
    difference between four shapes that assemble and four that do not.
    """
    a, b = waveguide_a_m * 1000.0, waveguide_b_m * 1000.0
    a1, b1 = aperture_a1_m * 1000.0, aperture_b1_m * 1000.0
    length = axial_length_m * 1000.0
    if a1 <= a or b1 <= b:
        raise ValueError("aperture must exceed the waveguide in both planes — horns flare out")
    if length <= 0:
        raise ValueError("axial length must be positive")

    height_e = math.hypot(length, (b1 - b) / 2.0)
    height_h = math.hypot(length, (a1 - a) / 2.0)
    corner = math.sqrt(length**2 + ((a1 - a) / 2.0) ** 2 + ((b1 - b) / 2.0) ** 2)

    cut_e = _widen_for_seam(a, a1, height_e, seam_allowance_mm)
    cut_h = _widen_for_seam(b, b1, height_h, seam_allowance_mm)

    panels = (
        Panel(
            label="E-flare panel (top / bottom)",
            polygon=_trapezoid(*cut_e, height_e),
            fold_polygon=_trapezoid(a, a1, height_e),
            quantity=2,
            note=(
                f"Throat edge {a:.1f} mm, aperture edge {a1:.1f} mm, "
                f"{height_e:.1f} mm between them."
            ),
        ),
        Panel(
            label="H-flare panel (left / right)",
            polygon=_trapezoid(*cut_h, height_h),
            fold_polygon=_trapezoid(b, b1, height_h),
            quantity=2,
            note=(
                f"Throat edge {b:.1f} mm, aperture edge {b1:.1f} mm, "
                f"{height_h:.1f} mm between them."
            ),
        ),
    )

    notes = [
        "Dimensions are the ELECTRICAL (inner) surface. Cut lines include any seam "
        "allowance; the dashed fold line is the electrical edge.",
        f"The corner edge shared by adjacent panels is {corner:.1f} mm. Measure it on both "
        "panels before joining — if they disagree, something was cut or printed wrong.",
        "Panels meet at the four corners. Join with rivets, self-tapping screws, or "
        "conductive tape; the joint must be electrically continuous along its whole length, "
        "because a slot in a horn wall radiates.",
        "The throat edges (the short parallel sides) form the waveguide mouth and must all "
        "sit in one plane. Assemble against a flat surface.",
    ]
    if seam_allowance_mm > 0:
        notes.append(
            f"Seam allowance {seam_allowance_mm:g} mm is added on the two sloped edges of "
            "each panel only — the throat and aperture edges are cut to size."
        )

    return Development(
        title=title,
        panels=panels,
        notes=tuple(notes),
        key_dimensions={
            "waveguide_a_mm": a,
            "waveguide_b_mm": b,
            "aperture_a1_mm": a1,
            "aperture_b1_mm": b1,
            "axial_length_mm": length,
            "panel_height_e_mm": height_e,
            "panel_height_h_mm": height_h,
            "corner_edge_mm": corner,
        },
    )


def conical_development(
    *,
    aperture_diameter_m: float,
    slant_m: float,
    throat_diameter_m: float = 0.0,
    seam_allowance_mm: float = 0.0,
    title: str = "Conical horn",
) -> Development:
    """Unroll a conical horn into an annular sector.

    A cone frustum develops exactly into a sector of an annulus. The outer radius is the
    apex-to-rim slant; the sector's included angle is chosen so the outer arc length equals
    the aperture circumference:

        angle = 2*pi*R_aperture / slant

    The inner arc then automatically equals the throat circumference, by similar triangles
    — a good check that the development is right rather than merely plausible.
    """
    radius = aperture_diameter_m * 1000.0 / 2.0
    outer = slant_m * 1000.0
    if radius <= 0 or outer <= 0:
        raise ValueError("aperture diameter and slant must be positive")
    if radius >= outer:
        raise ValueError(
            "slant must exceed the aperture radius — a cone's apex is not in its rim plane"
        )
    inner = outer * (throat_diameter_m * 1000.0 / 2.0) / radius if throat_diameter_m > 0 else 0.0
    angle_deg = math.degrees(2.0 * math.pi * radius / outer)

    sector = AnnularSector(
        label="Cone wall (roll and join along the radial edges)",
        inner_radius_mm=inner,
        outer_radius_mm=outer + seam_allowance_mm,
        angle_deg=angle_deg,
        note=(
            f"Outer arc {2 * math.pi * radius:.1f} mm long = the aperture circumference. "
            f"Sector angle {angle_deg:.2f} deg."
        ),
    )
    notes = [
        "Roll the sector into a cone and join the two straight radial edges. The seam must "
        "be electrically continuous along its whole length.",
        f"Check before rolling: the outer arc should measure {2 * math.pi * radius:.1f} mm "
        f"and the finished rim {aperture_diameter_m * 1000:.1f} mm across.",
        "Scribe the sector with a beam compass or a string pinned at the apex point; at "
        f"{outer:.0f} mm radius a small angular error becomes a large arc error.",
    ]
    if throat_diameter_m <= 0:
        notes.append(
            "No throat diameter was given, so this develops as a full cone to a point. A "
            "real horn needs a throat opening for the waveguide — cut the inner radius to "
            "suit your feed and re-check the electrical model with the throat included."
        )
    if seam_allowance_mm > 0:
        notes.append(f"Seam allowance {seam_allowance_mm:g} mm is added at the outer radius only.")

    return Development(
        title=title,
        sectors=(sector,),
        notes=tuple(notes),
        key_dimensions={
            "aperture_diameter_mm": aperture_diameter_m * 1000.0,
            "throat_diameter_mm": throat_diameter_m * 1000.0,
            "slant_mm": outer,
            "sector_angle_deg": angle_deg,
            "outer_arc_mm": 2.0 * math.pi * radius,
        },
    )


def thickness_note(material_thickness_mm: float, wavelength_mm: float) -> str:
    """State how much the sheet thickness matters at this wavelength, instead of guessing.

    The model's dimensions are the inner surface. Butt-jointed panels cut to those
    dimensions give an inner opening about one thickness small in each axis.
    """
    fraction = material_thickness_mm / wavelength_mm
    verdict = (
        "negligible at this wavelength"
        if fraction < 0.01
        else "worth compensating: add one material thickness to each aperture dimension"
    )
    return (
        f"Material thickness {material_thickness_mm:g} mm is {fraction * 100:.2f}% of a "
        f"{wavelength_mm:.1f} mm wavelength — {verdict}."
    )
