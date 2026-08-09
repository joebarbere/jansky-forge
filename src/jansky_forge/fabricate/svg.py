"""Printable templates: 1:1 SVG, tiled across ordinary paper.

Two decisions carry this module.

**Everything is in millimetres, at 1:1.** The SVG declares its size in ``mm`` and uses a
``viewBox`` where one user unit is one millimetre, so a correctly-configured printer puts a
100 mm line 100 mm across the paper. No scale factors anywhere.

**Every page carries a scale check.** A printer set to "fit to page" silently shrinks the
drawing by a few percent, which is invisible on screen, invisible on paper, and ruinous
after you cut. Each page therefore prints a 100 mm ruler with the instruction to measure it
first. This is the cheapest possible guard against the most expensive mistake, and it is not
optional — see :func:`page_svg`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from jansky_forge.fabricate.geometry import AnnularSector, Development, Panel, Point

#: Printable page sizes in millimetres.
PAGE_SIZES: dict[str, tuple[float, float]] = {
    "a4": (210.0, 297.0),
    "letter": (215.9, 279.4),
    "a3": (297.0, 420.0),
    "tabloid": (279.4, 431.8),
}

#: Unprintable border most consumer printers enforce, plus a little.
DEFAULT_MARGIN_MM = 10.0

#: How much adjacent tiles share. Enough to line up by eye without wasting paper.
DEFAULT_OVERLAP_MM = 15.0

_STYLE = """
.cut { fill: none; stroke: #000; stroke-width: 0.4; }
.fold { fill: none; stroke: #444; stroke-width: 0.3; stroke-dasharray: 4 2; }
.reg { fill: none; stroke: #000; stroke-width: 0.25; }
.overlap { fill: none; stroke: #999; stroke-width: 0.25; stroke-dasharray: 2 2; }
.ruler { fill: none; stroke: #000; stroke-width: 0.5; }
text { font-family: sans-serif; fill: #000; }
.label { font-size: 4px; }
.small { font-size: 2.6px; fill: #333; }
.warn { font-size: 3.2px; font-weight: bold; }
"""


@dataclass(frozen=True)
class Tiling:
    """How a drawing was split across pages."""

    columns: int
    rows: int
    page: str
    page_width_mm: float
    page_height_mm: float
    margin_mm: float
    overlap_mm: float

    @property
    def pages(self) -> int:
        return self.columns * self.rows

    @property
    def usable_mm(self) -> tuple[float, float]:
        return (
            self.page_width_mm - 2 * self.margin_mm,
            self.page_height_mm - 2 * self.margin_mm,
        )


def plan_tiling(
    width_mm: float,
    height_mm: float,
    *,
    page: str = "a4",
    landscape: bool = False,
    margin_mm: float = DEFAULT_MARGIN_MM,
    overlap_mm: float = DEFAULT_OVERLAP_MM,
) -> Tiling:
    """Work out how many sheets a drawing needs."""
    try:
        pw, ph = PAGE_SIZES[page.lower()]
    except KeyError:
        raise KeyError(
            f"unknown page size {page!r}; known: {', '.join(sorted(PAGE_SIZES))}"
        ) from None
    if landscape:
        pw, ph = ph, pw
    usable_w, usable_h = pw - 2 * margin_mm, ph - 2 * margin_mm
    if usable_w <= overlap_mm or usable_h <= overlap_mm:
        raise ValueError("margin and overlap leave no usable area on the page")
    # Each page after the first advances by (usable - overlap).
    columns = max(1, math.ceil((width_mm - overlap_mm) / (usable_w - overlap_mm)))
    rows = max(1, math.ceil((height_mm - overlap_mm) / (usable_h - overlap_mm)))
    return Tiling(columns, rows, page, pw, ph, margin_mm, overlap_mm)


def _polygon_path(points: tuple[Point, ...]) -> str:
    head = f"M {points[0][0]:.3f} {points[0][1]:.3f}"
    rest = " ".join(f"L {x:.3f} {y:.3f}" for x, y in points[1:])
    return f"{head} {rest} Z"


def _ruler(x: float, y: float) -> str:
    """A 100 mm scale check with 10 mm ticks, plus the instruction to use it."""
    ticks = "".join(
        f'<path class="ruler" d="M {x + i * 10:.1f} {y:.1f} L {x + i * 10:.1f} '
        f'{y - (3.5 if i % 5 == 0 else 2):.1f}"/>'
        for i in range(11)
    )
    return (
        f'<path class="ruler" d="M {x:.1f} {y:.1f} L {x + 100:.1f} {y:.1f}"/>{ticks}'
        f'<text class="warn" x="{x:.1f}" y="{y + 5:.1f}">'
        "MEASURE THIS LINE: it must be exactly 100 mm.</text>"
        f'<text class="small" x="{x:.1f}" y="{y + 9:.1f}">'
        'If it is not, print again at 100% / "Actual size" — never "Fit to page". '
        "A wrong scale here wastes the whole sheet.</text>"
    )


def _registration(tiling: Tiling) -> str:
    """Corner crop marks at the usable-area corners, for aligning adjacent sheets."""
    m, pw, ph = tiling.margin_mm, tiling.page_width_mm, tiling.page_height_mm
    arm = 5.0
    marks = []
    for cx, cy in ((m, m), (pw - m, m), (m, ph - m), (pw - m, ph - m)):
        sx = arm if cx < pw / 2 else -arm
        sy = arm if cy < ph / 2 else -arm
        marks.append(f'<path class="reg" d="M {cx:.1f} {cy:.1f} l {sx:.1f} 0"/>')
        marks.append(f'<path class="reg" d="M {cx:.1f} {cy:.1f} l 0 {sy:.1f}"/>')
    return "".join(marks)


def page_svg(
    shapes: list[tuple[str, str]],
    *,
    tiling: Tiling,
    column: int,
    row: int,
    title: str,
    subtitle: str = "",
) -> str:
    """Render one tile.

    ``shapes`` are ``(css_class, path_d)`` pairs in drawing millimetres; this function
    translates them so the requested tile lands inside the page margins.
    """
    usable_w, usable_h = tiling.usable_mm
    step_x = usable_w - tiling.overlap_mm
    step_y = usable_h - tiling.overlap_mm
    off_x = tiling.margin_mm - column * step_x
    off_y = tiling.margin_mm - row * step_y

    body = "".join(f'<path class="{cls}" d="{d}"/>' for cls, d in shapes)
    sheet = row * tiling.columns + column + 1
    label = f"{title} — sheet {sheet} of {tiling.pages} (column {column + 1}, row {row + 1})"
    overlap_guides = ""
    if tiling.columns > 1 and column < tiling.columns - 1:
        gx = tiling.margin_mm + step_x
        overlap_guides += (
            f'<path class="overlap" d="M {gx:.1f} {tiling.margin_mm:.1f} '
            f'L {gx:.1f} {tiling.page_height_mm - tiling.margin_mm:.1f}"/>'
        )
    if tiling.rows > 1 and row < tiling.rows - 1:
        gy = tiling.margin_mm + step_y
        overlap_guides += (
            f'<path class="overlap" d="M {tiling.margin_mm:.1f} {gy:.1f} '
            f'L {tiling.page_width_mm - tiling.margin_mm:.1f} {gy:.1f}"/>'
        )

    ruler_y = tiling.page_height_mm - tiling.margin_mm - 2.0
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="{tiling.page_width_mm}mm" \
height="{tiling.page_height_mm}mm" \
viewBox="0 0 {tiling.page_width_mm} {tiling.page_height_mm}">
<style>{_STYLE}</style>
<clipPath id="page"><rect x="{tiling.margin_mm}" y="{tiling.margin_mm}" \
width="{usable_w}" height="{usable_h}"/></clipPath>
<g clip-path="url(#page)"><g transform="translate({off_x:.3f} {off_y:.3f})">{body}</g></g>
{overlap_guides}
{_registration(tiling)}
<text class="label" x="{tiling.margin_mm}" y="{tiling.margin_mm - 3:.1f}">{label}</text>
<text class="small" x="{tiling.margin_mm}" y="{tiling.margin_mm - 0.5:.1f}">{subtitle}</text>
{_ruler(tiling.margin_mm, ruler_y)}
</svg>
"""


def _slug(label: str) -> str:
    keep = [c.lower() if c.isalnum() else "-" for c in label]
    slug = "".join(keep)
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-")[:40]


def _shift(points: tuple[Point, ...], dx: float, dy: float) -> tuple[Point, ...]:
    return tuple((x + dx, y + dy) for x, y in points)


def shape_shapes(shape: Panel | AnnularSector) -> tuple[list[tuple[str, str]], float, float]:
    """Paths for one shape, moved so its bounding box starts at the origin."""
    if isinstance(shape, Panel):
        x0, y0, _, _ = shape.bounds_mm
        paths = [("cut", _polygon_path(_shift(shape.polygon, -x0, -y0)))]
        if shape.fold_polygon and shape.fold_polygon != shape.polygon:
            paths.append(("fold", _polygon_path(_shift(shape.fold_polygon, -x0, -y0))))
        return paths, *shape.size_mm
    pts = shape.polygon()
    x0 = min(p[0] for p in pts)
    y0 = min(p[1] for p in pts)
    return [("cut", _polygon_path(_shift(pts, -x0, -y0)))], *shape.size_mm


@dataclass(frozen=True)
class RenderedShape:
    """One shape's printable template set."""

    label: str
    slug: str
    tiling: Tiling
    files: tuple[tuple[str, str], ...]
    width_mm: float
    height_mm: float
    quantity: int


def render_pages(
    development: Development,
    *,
    page: str = "a4",
    landscape: bool = False,
    margin_mm: float = DEFAULT_MARGIN_MM,
    overlap_mm: float = DEFAULT_OVERLAP_MM,
) -> list[RenderedShape]:
    """Render each shape in a development to its own tiled template set.

    One template per distinct shape, not one giant composite: a builder prints the
    E-flare template, cuts two panels from it, then moves on. A composite drawing of every
    panel side by side wastes paper on the gaps between them and forces printing the lot to
    get at any one part.
    """
    rendered: list[RenderedShape] = []
    shapes: list[Panel | AnnularSector] = [*development.panels, *development.sectors]
    for shape in shapes:
        paths, width, height = shape_shapes(shape)
        tiling = plan_tiling(
            width,
            height,
            page=page,
            landscape=landscape,
            margin_mm=margin_mm,
            overlap_mm=overlap_mm,
        )
        slug = _slug(shape.label)
        subtitle = (
            f"Cut {shape.quantity}. Solid = cut line, dashed = fold / electrical edge. "
            f"Piece is {width:.0f} x {height:.0f} mm."
        )
        files = []
        for row in range(tiling.rows):
            for column in range(tiling.columns):
                index = row * tiling.columns + column + 1
                name = f"{slug}-sheet-{index:02d}.svg" if tiling.pages > 1 else f"{slug}.svg"
                files.append(
                    (
                        name,
                        page_svg(
                            paths,
                            tiling=tiling,
                            column=column,
                            row=row,
                            title=f"{development.title} — {shape.label}",
                            subtitle=subtitle,
                        ),
                    )
                )
        rendered.append(
            RenderedShape(
                label=shape.label,
                slug=slug,
                tiling=tiling,
                files=tuple(files),
                width_mm=width,
                height_mm=height,
                quantity=shape.quantity,
            )
        )
    return rendered
