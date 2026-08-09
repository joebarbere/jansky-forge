"""The fabrication packet: everything for one build, written to one directory.

A packet is deliberately self-contained and self-describing. Someone who finds the folder
a year later — or someone the design was sent to — must be able to build from it without
the tool, the conversation, or the person who made it. That means the packet carries the
*design* that produced it, not just its shapes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from jansky_forge._version import __version__
from jansky_forge.fabricate import dxf, svg
from jansky_forge.fabricate.cutlist import CutList, build_cutlist
from jansky_forge.fabricate.geometry import (
    Development,
    conical_development,
    pyramidal_development,
    thickness_note,
)
from jansky_forge.horns import ConicalDesign, PyramidalDesign
from jansky_forge.units import wavelength_m


@dataclass(frozen=True)
class Packet:
    """What was written, and where."""

    directory: Path
    files: tuple[str, ...]
    cutlist: CutList
    development: Development
    sheets: int
    #: (label, sheet count, width mm, height mm) per template, so a caller can warn about
    #: a template that needs an unreasonable amount of paper before it is printed.
    templates: tuple[tuple[str, int, float, float], ...] = ()

    def summary(self) -> str:
        return (
            f"{len(self.files)} files in {self.directory} — {self.sheets} template "
            f"sheet(s) across {len(self.templates)} template(s), cut list, DXF, "
            "assembly steps, and design.json"
        )


def development_for(
    design: PyramidalDesign | ConicalDesign, *, seam_allowance_mm: float = 0.0
) -> Development:
    """Unroll whichever kind of horn this is."""
    if isinstance(design, PyramidalDesign):
        return pyramidal_development(
            waveguide_a_m=design.waveguide_a_m,
            waveguide_b_m=design.waveguide_b_m,
            aperture_a1_m=design.aperture_a1_m,
            aperture_b1_m=design.aperture_b1_m,
            axial_length_m=design.axial_length_m,
            seam_allowance_mm=seam_allowance_mm,
            title=f"Pyramidal horn, {design.gain_dbi:.1f} dBi at {design.freq_hz / 1e6:.1f} MHz",
        )
    return conical_development(
        aperture_diameter_m=design.aperture_diameter_m,
        slant_m=design.slant_m,
        seam_allowance_mm=seam_allowance_mm,
        title=f"Conical horn, {design.gain_dbi:.1f} dBi at {design.freq_hz / 1e6:.1f} MHz",
    )


def _design_json(design: PyramidalDesign | ConicalDesign, development: Development) -> str:
    """The provenance record: what was designed, by what, and what it should do.

    Without this a packet is a set of anonymous shapes. With it, a measured antenna can be
    compared against the prediction that produced it — which is the whole point of M7/M8.
    """
    common = {
        "schema": "jansky-forge.fabrication-packet/1",
        "generated_by": f"jansky-forge {__version__}",
        "freq_hz": design.freq_hz,
        "wavelength_mm": wavelength_m(design.freq_hz) * 1000.0,
        "predicted_gain_dbi": design.gain_dbi,
        "key_dimensions_mm": development.key_dimensions,
        "caution": (
            "Predicted values are model output, not measurements. Measure the built "
            "antenna before quoting any of these numbers."
        ),
    }
    if isinstance(design, PyramidalDesign):
        common |= {
            "shape": "pyramidal",
            "waveguide_a_m": design.waveguide_a_m,
            "waveguide_b_m": design.waveguide_b_m,
            "aperture_a1_m": design.aperture_a1_m,
            "aperture_b1_m": design.aperture_b1_m,
            "axial_length_m": design.axial_length_m,
            "rho1_m": design.rho1_m,
            "rho2_m": design.rho2_m,
            "phase_deviation_e": design.phase_deviation_e,
            "phase_deviation_h": design.phase_deviation_h,
        }
    else:
        common |= {
            "shape": "conical",
            "aperture_diameter_m": design.aperture_diameter_m,
            "slant_m": design.slant_m,
            "axial_length_m": design.axial_length_m,
        }
    return json.dumps(common, indent=2) + "\n"


def _assembly_markdown(development: Development, design_gain_dbi: float) -> str:
    lines = [
        f"# {development.title} — assembly",
        "",
        "Work through this in order. Every step has a checkbox because a step that cannot "
        "be ticked is a step that gets skipped.",
        "",
        "## Before cutting",
        "",
        "- [ ] Print every sheet at 100% / 'Actual size'.",
        "- [ ] Measure the 100 mm ruler printed on each sheet. It must be exactly 100 mm.",
        "- [ ] Tape multi-sheet templates together on the overlap guides, aligning the "
        "corner registration marks.",
        "- [ ] Check the printed panel dimensions against the cut list before committing.",
        "",
        "## Cut and form",
        "",
        "- [ ] Transfer the outlines to the sheet. Mark, do not cut, the dashed fold lines.",
        "- [ ] Cut on the solid lines, on the waste side.",
        "- [ ] Deburr every edge.",
        "",
        "## Assemble",
        "",
    ]
    for note in development.notes:
        lines.append(f"- [ ] {note}")
    lines += [
        "",
        "## Before you trust it",
        "",
        f"- [ ] The model predicts **{design_gain_dbi:.2f} dBi**. That is a prediction from "
        "geometry, not a measurement of your horn.",
        "- [ ] Check the aperture is square (equal diagonals) and the throat sits flat.",
        "- [ ] Measure return loss with a VNA before putting it on the sky. A horn that "
        "looks right can still be badly matched.",
        "- [ ] Record what you actually built, including anything that came out different "
        "from the drawing. Those deviations are what explain a measurement later.",
    ]
    return "\n".join(lines) + "\n"


def write_packet(
    design: PyramidalDesign | ConicalDesign,
    directory: str | Path,
    *,
    seam_allowance_mm: float = 0.0,
    kerf_mm: float = 0.0,
    tool: str | None = None,
    material_thickness_mm: float = 1.0,
    page: str = "a4",
    landscape: bool = False,
) -> Packet:
    """Write a complete fabrication packet for ``design`` into ``directory``."""
    out = Path(directory)
    out.mkdir(parents=True, exist_ok=True)

    development = development_for(design, seam_allowance_mm=seam_allowance_mm)
    lam_mm = wavelength_m(design.freq_hz) * 1000.0
    cut = build_cutlist(
        development,
        kerf_mm=kerf_mm,
        tool=tool,
        material_thickness_mm=material_thickness_mm,
        extra_notes=(thickness_note(material_thickness_mm, lam_mm),),
    )
    rendered = svg.render_pages(development, page=page, landscape=landscape)

    written: list[str] = []
    for shape in rendered:
        for name, content in shape.files:
            (out / name).write_text(content)
            written.append(name)
    (out / "cutlist.md").write_text(cut.to_markdown())
    (out / "assembly.md").write_text(_assembly_markdown(development, design.gain_dbi))
    (out / "template.dxf").write_text(dxf.development_dxf(development))
    (out / "design.json").write_text(_design_json(design, development))
    written += ["cutlist.md", "assembly.md", "template.dxf", "design.json"]

    return Packet(
        directory=out,
        files=tuple(written),
        cutlist=cut,
        development=development,
        sheets=sum(s.tiling.pages for s in rendered),
        templates=tuple((s.label, s.tiling.pages, s.width_mm, s.height_mm) for s in rendered),
    )
