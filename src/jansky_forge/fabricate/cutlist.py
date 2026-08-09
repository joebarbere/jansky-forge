"""Cut list, kerf budget, and bill of materials — the paperwork half of fabrication.

Kerf is the width of material a cutting tool removes. It matters here in two different
ways, and conflating them is the classic error:

* **Stock**: kerf eats material, so a sheet must be slightly bigger than the sum of the
  parts. This module reports the total kerf volume as an area allowance.
* **Dimension**: a cut made *on* the line leaves the part half a kerf small on that edge.
  For hand tools (shears, nibbler) the tool is guided to one side and this does not apply;
  for a laser or waterjet the machine normally compensates automatically. So this module
  reports the number and states plainly when it does and does not need acting on, rather
  than silently shrinking or growing anybody's part.

The bill of materials is a **starting point, not a specification**: the geometry-derived
quantities (sheet area, seam length) are computed, and the hardware lines are named with
the reason they are there so a builder can substitute knowingly.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from jansky_forge.fabricate.geometry import Development

#: Typical hand-tool and machine kerf widths, millimetres. Indicative — measure yours.
TYPICAL_KERF_MM: dict[str, float] = {
    "shears": 0.0,  # displaces rather than removes material
    "nibbler": 5.0,
    "jigsaw": 1.5,
    "bandsaw": 1.0,
    "laser": 0.2,
    "waterjet": 0.8,
    "plasma": 1.5,
}


@dataclass(frozen=True)
class CutItem:
    """One line of the cut list."""

    label: str
    quantity: int
    size_mm: tuple[float, float]
    area_mm2: float
    perimeter_mm: float
    note: str = ""

    @property
    def stock_note(self) -> str:
        w, h = self.size_mm
        return f"needs stock at least {w:.0f} x {h:.0f} mm"


@dataclass(frozen=True)
class BomItem:
    """One line of the bill of materials, with why it is there."""

    item: str
    quantity: str
    why: str


@dataclass(frozen=True)
class CutList:
    """Everything a builder needs on paper."""

    title: str
    items: tuple[CutItem, ...]
    bom: tuple[BomItem, ...]
    total_area_mm2: float
    total_cut_length_mm: float
    kerf_mm: float
    kerf_area_mm2: float
    key_dimensions: dict[str, float]
    notes: tuple[str, ...]

    @property
    def total_area_m2(self) -> float:
        return self.total_area_mm2 / 1e6

    def to_markdown(self) -> str:
        """The cut list as a printable checklist.

        Every row gets a checkbox: a fabrication document that cannot be ticked off is a
        document that gets read once and then guessed at.
        """
        lines = [f"# {self.title} — cut list", ""]
        lines += ["## Key dimensions", "", "| Dimension | mm |", "|---|---|"]
        for name, value in self.key_dimensions.items():
            lines.append(f"| {name.replace('_', ' ')} | {value:.1f} |")
        lines += ["", "## Cut these", ""]
        for item in self.items:
            lines.append(f"- [ ] **{item.quantity} x {item.label}** — {item.stock_note}")
            if item.note:
                lines.append(f"      {item.note}")
        lines += [
            "",
            "## Material budget",
            "",
            f"- Part area: **{self.total_area_m2:.4f} m²** (all pieces, excluding waste)",
            f"- Total cut length: {self.total_cut_length_mm / 1000:.2f} m",
            f"- Kerf allowance at {self.kerf_mm:g} mm: {self.kerf_area_mm2 / 1e6:.4f} m²",
            "- Buy more than the part area. Nesting waste on a rectangular sheet is "
            "typically 30-60% for trapezoids, and a mistake costs a whole sheet.",
            "",
            "## Bill of materials",
            "",
            "| Item | Quantity | Why |",
            "|---|---|---|",
        ]
        for bom in self.bom:
            lines.append(f"| {bom.item} | {bom.quantity} | {bom.why} |")
        lines += ["", "## Before you cut", ""]
        for note in self.notes:
            lines.append(f"- [ ] {note}")
        return "\n".join(lines) + "\n"


def _default_bom(development: Development, material_thickness_mm: float) -> tuple[BomItem, ...]:
    area_m2 = development.total_area_mm2 / 1e6
    seam_m = development.total_cut_length_mm / 1000.0
    return (
        BomItem(
            "Aluminium sheet (or tinplate, or foil-faced foam board)",
            f"~{area_m2 * 1.6:.2f} m² of stock for {area_m2:.3f} m² of parts",
            f"The horn walls. {material_thickness_mm:g} mm assumed; anything conductive and "
            "rigid works, since the wave only sees the surface.",
        ),
        BomItem(
            "Rivets, self-tapping screws, or conductive tape",
            f"enough for ~{seam_m:.1f} m of seam",
            "Joining the walls. The joint must be electrically continuous — a gap in a horn "
            "wall is a slot, and slots radiate.",
        ),
        BomItem(
            "Waveguide section or throat box",
            "1",
            "Feeds the horn. Its internal dimensions are what the electrical model used, so "
            "measure the real part before cutting panels to match it.",
        ),
        BomItem(
            "Coaxial connector (N-type or SMA) + probe wire",
            "1",
            "Launches into the waveguide. Probe length and its distance from the back wall "
            "set the match; jansky-forge does not yet design these (M3).",
        ),
        BomItem(
            "Backshort plate",
            "1",
            "Closes the waveguide behind the probe. Usually a quarter guide-wavelength "
            "behind it — check your feed design.",
        ),
    )


def build_cutlist(
    development: Development,
    *,
    kerf_mm: float = 0.0,
    tool: str | None = None,
    material_thickness_mm: float = 1.0,
    extra_notes: tuple[str, ...] = (),
) -> CutList:
    """Assemble the cut list, kerf budget, and BOM for a development."""
    if tool is not None:
        try:
            kerf_mm = TYPICAL_KERF_MM[tool.lower()]
        except KeyError:
            raise KeyError(
                f"unknown tool {tool!r}; known: {', '.join(sorted(TYPICAL_KERF_MM))}"
            ) from None
    if kerf_mm < 0:
        raise ValueError(f"kerf cannot be negative, got {kerf_mm}")

    items = [
        CutItem(
            label=panel.label,
            quantity=panel.quantity,
            size_mm=panel.size_mm,
            area_mm2=panel.area_mm2,
            perimeter_mm=panel.perimeter_mm,
            note=panel.note,
        )
        for panel in development.panels
    ]
    items += [
        CutItem(
            label=sector.label,
            quantity=sector.quantity,
            size_mm=sector.size_mm,
            area_mm2=sector.area_mm2,
            perimeter_mm=math.radians(sector.angle_deg)
            * (sector.outer_radius_mm + sector.inner_radius_mm)
            + 2.0 * (sector.outer_radius_mm - sector.inner_radius_mm),
            note=sector.note,
        )
        for sector in development.sectors
    ]

    kerf_area = development.total_cut_length_mm * kerf_mm
    notes = [
        "Print at 100% / 'Actual size'. Measure the 100 mm ruler on the sheet before "
        "cutting anything — a 'fit to page' print is a few percent small and looks fine.",
        "Check the corner-edge length on adjacent panels; they must agree.",
        "Deburr every edge. A burr inside the horn is a scattering feature, and outside it "
        "is a cut finger.",
    ]
    if kerf_mm > 0:
        notes.append(
            f"Kerf {kerf_mm:g} mm: cut on the WASTE side of the line so the part keeps its "
            "dimension. A laser or waterjet usually compensates in software — if yours "
            "does, do not also offset by hand, or you will apply it twice."
        )
    else:
        notes.append(
            "Kerf 0 mm assumed (shears or similar displace rather than remove material). "
            "If you use a saw or nibbler, re-run with the right tool so the material "
            "budget is honest."
        )
    notes.extend(extra_notes)

    return CutList(
        title=development.title,
        items=tuple(items),
        bom=_default_bom(development, material_thickness_mm),
        total_area_mm2=development.total_area_mm2,
        total_cut_length_mm=development.total_cut_length_mm,
        kerf_mm=kerf_mm,
        kerf_area_mm2=kerf_area,
        key_dimensions=dict(development.key_dimensions),
        notes=tuple(notes),
    )
