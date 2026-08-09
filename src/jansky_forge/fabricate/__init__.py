"""Fabrication: turn a design into shapes you can cut, and paperwork you can follow.

The "build" leg of create-build-characterize. A horn's surface is developable, so this
package unrolls it exactly onto flat stock and emits:

* **1:1 printable templates** (SVG), tiled across ordinary paper, every sheet carrying a
  100 mm ruler so a mis-scaled print is caught before the metal is;
* **DXF** for a laser or waterjet, with cut and fold on separate layers;
* **a cut list** with an honest kerf and material budget, and a bill of materials that says
  *why* each item is there;
* **assembly steps** as a checklist;
* **``design.json``**, the provenance record tying the shapes back to the prediction that
  produced them — so a measured antenna can later be compared against what it was meant
  to be.

Nothing here re-derives geometry: :mod:`~jansky_forge.fabricate.geometry` owns the shapes
and every output format consumes them.
"""

from __future__ import annotations

from jansky_forge.fabricate.cutlist import (
    TYPICAL_KERF_MM,
    BomItem,
    CutItem,
    CutList,
    build_cutlist,
)
from jansky_forge.fabricate.dxf import development_dxf
from jansky_forge.fabricate.geometry import (
    AnnularSector,
    Development,
    Panel,
    conical_development,
    pyramidal_development,
    thickness_note,
)
from jansky_forge.fabricate.packet import Packet, development_for, write_packet
from jansky_forge.fabricate.svg import PAGE_SIZES, Tiling, plan_tiling, render_pages

__all__ = [
    "PAGE_SIZES",
    "TYPICAL_KERF_MM",
    "AnnularSector",
    "BomItem",
    "CutItem",
    "CutList",
    "Development",
    "Packet",
    "Panel",
    "Tiling",
    "build_cutlist",
    "conical_development",
    "development_dxf",
    "development_for",
    "plan_tiling",
    "pyramidal_development",
    "render_pages",
    "thickness_note",
    "write_packet",
]
