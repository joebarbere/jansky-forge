"""Minimal DXF R12 output, for anyone taking a template to a laser or waterjet.

DXF R12 ASCII is a flat list of group-code/value line pairs. Writing it by hand keeps this
package dependency-free, and R12 is the dialect every CAM program still reads.

Units are millimetres, matching :mod:`~jansky_forge.fabricate.geometry`. ``$INSUNITS`` is
set to 4 (millimetres) so a receiving program does not have to guess — a DXF that does not
declare its units is how a part arrives at ten times its intended size.

Arcs are emitted as true ``ARC`` entities rather than polygon approximations, so a cone
development cuts as a smooth curve.
"""

from __future__ import annotations

import math

from jansky_forge.fabricate.geometry import AnnularSector, Development, Point


def _pair(code: int, value: object) -> str:
    return f"{code}\n{value}\n"


def _header() -> str:
    return (
        _pair(0, "SECTION")
        + _pair(2, "HEADER")
        + _pair(9, "$INSUNITS")
        + _pair(70, 4)  # millimetres
        + _pair(9, "$MEASUREMENT")
        + _pair(70, 1)  # metric
        + _pair(0, "ENDSEC")
    )


def _line(p0: Point, p1: Point, layer: str) -> str:
    return (
        _pair(0, "LINE")
        + _pair(8, layer)
        + _pair(10, f"{p0[0]:.4f}")
        + _pair(20, f"{p0[1]:.4f}")
        + _pair(30, "0.0")
        + _pair(11, f"{p1[0]:.4f}")
        + _pair(21, f"{p1[1]:.4f}")
        + _pair(31, "0.0")
    )


def _arc(center: Point, radius: float, start_deg: float, end_deg: float, layer: str) -> str:
    return (
        _pair(0, "ARC")
        + _pair(8, layer)
        + _pair(10, f"{center[0]:.4f}")
        + _pair(20, f"{center[1]:.4f}")
        + _pair(30, "0.0")
        + _pair(40, f"{radius:.4f}")
        + _pair(50, f"{start_deg:.4f}")
        + _pair(51, f"{end_deg:.4f}")
    )


def _polygon(points: tuple[Point, ...], layer: str) -> str:
    return "".join(
        _line(points[i], points[(i + 1) % len(points)], layer) for i in range(len(points))
    )


def _sector_entities(sector: AnnularSector, dx: float, dy: float) -> str:
    """A sector as two arcs and two radial lines, about an apex at (dx, dy).

    :class:`~jansky_forge.fabricate.geometry.AnnularSector` measures its angle symmetrically
    about the +y axis, so the arcs run from 90 - half to 90 + half in DXF's convention
    (degrees counter-clockwise from +x).
    """
    half = sector.angle_deg / 2.0
    start, end = 90.0 - half, 90.0 + half
    center = (dx, dy)
    out = _arc(center, sector.outer_radius_mm, start, end, "CUT")
    a0, a1 = math.radians(start), math.radians(end)

    def at(radius: float, angle: float) -> Point:
        return (dx + radius * math.cos(angle), dy + radius * math.sin(angle))

    if sector.inner_radius_mm > 0:
        out += _arc(center, sector.inner_radius_mm, start, end, "CUT")
        out += _line(at(sector.inner_radius_mm, a0), at(sector.outer_radius_mm, a0), "CUT")
        out += _line(at(sector.inner_radius_mm, a1), at(sector.outer_radius_mm, a1), "CUT")
    else:
        out += _line(center, at(sector.outer_radius_mm, a0), "CUT")
        out += _line(center, at(sector.outer_radius_mm, a1), "CUT")
    return out


def development_dxf(development: Development, *, gap_mm: float = 20.0) -> str:
    """Render a whole development to one DXF string.

    Cut lines land on layer ``CUT``; fold lines on ``FOLD``, so a laser operator can ignore
    or score them deliberately rather than cutting the horn in half.
    """
    entities = ""
    cursor = 0.0
    for panel in development.panels:
        x0, y0, _, _ = panel.bounds_mm
        dx, dy = cursor - x0, -y0
        shifted = tuple((x + dx, y + dy) for x, y in panel.polygon)
        entities += _polygon(shifted, "CUT")
        if panel.fold_polygon and panel.fold_polygon != panel.polygon:
            entities += _polygon(tuple((x + dx, y + dy) for x, y in panel.fold_polygon), "FOLD")
        cursor += panel.size_mm[0] + gap_mm
    for sector in development.sectors:
        pts = sector.polygon()
        x0 = min(p[0] for p in pts)
        y0 = min(p[1] for p in pts)
        # The apex sits at the polygon's origin; shift so the shape starts at the cursor.
        entities += _sector_entities(sector, cursor - x0, -y0)
        cursor += sector.size_mm[0] + gap_mm

    return (
        _header()
        + _pair(0, "SECTION")
        + _pair(2, "ENTITIES")
        + entities
        + _pair(0, "ENDSEC")
        + _pair(0, "EOF")
    )
