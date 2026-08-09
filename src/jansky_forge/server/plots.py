"""Server-rendered SVG plots — no charting library, no CDN, no build step.

M2 already writes SVG for fabrication templates, so the idioms exist and there is no reason
to add matplotlib (heavy, and a rendering dependency for a web page) or a JavaScript charting
library (a CDN request, which makes the tool useless on a laptop in a field).

Everything here draws directly into an SVG string. The plots are deliberately plain: an axis,
a curve, a label. A design tool's plot has one job, which is to show you the shape changing
as you drag a number.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

_STYLE = """
.axis { stroke: currentColor; stroke-width: 1; fill: none; opacity: 0.5; }
.grid { stroke: currentColor; stroke-width: 0.5; fill: none; opacity: 0.15; }
.trace { fill: none; stroke-width: 2; }
.e-plane { stroke: #2563eb; }
.h-plane { stroke: #dc2626; }
.marker { stroke: currentColor; stroke-width: 1; stroke-dasharray: 4 3; opacity: 0.5; }
text { font-family: system-ui, sans-serif; fill: currentColor; }
.tick { font-size: 10px; opacity: 0.7; }
.key { font-size: 11px; }
.title { font-size: 12px; font-weight: 600; }
"""


@dataclass(frozen=True)
class Trace:
    """One curve to draw."""

    label: str
    x: np.ndarray
    y: np.ndarray
    css_class: str = "e-plane"


def line_plot(
    traces: list[Trace],
    *,
    title: str = "",
    x_label: str = "",
    y_label: str = "",
    width: int = 640,
    height: int = 320,
    y_min: float | None = None,
    y_max: float | None = None,
    marker_y: float | None = None,
) -> str:
    """Draw traces as an SVG line plot.

    Uses ``currentColor`` for axes and text so the plot inherits the page's colour scheme
    and works in both light and dark themes without a second stylesheet.
    """
    if not traces:
        raise ValueError("nothing to plot")
    left, right, top, bottom = 52, 16, 28, 40
    plot_w = width - left - right
    plot_h = height - top - bottom

    all_x = np.concatenate([t.x for t in traces])
    all_y = np.concatenate([t.y for t in traces])
    x0, x1 = float(all_x.min()), float(all_x.max())
    lo = float(all_y.min()) if y_min is None else y_min
    hi = float(all_y.max()) if y_max is None else y_max
    if math.isclose(x0, x1):
        x1 = x0 + 1.0
    if math.isclose(lo, hi):
        hi = lo + 1.0

    def sx(value: float) -> float:
        return left + (value - x0) / (x1 - x0) * plot_w

    def sy(value: float) -> float:
        return top + (hi - value) / (hi - lo) * plot_h

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="100%" role="img" aria-label="{title or "plot"}"><style>{_STYLE}</style>'
    ]
    # Grid and ticks.
    for fraction in (0.0, 0.25, 0.5, 0.75, 1.0):
        value = lo + fraction * (hi - lo)
        y = sy(value)
        parts.append(f'<path class="grid" d="M {left} {y:.1f} L {left + plot_w} {y:.1f}"/>')
        parts.append(
            f'<text class="tick" x="{left - 6}" y="{y + 3:.1f}" text-anchor="end">{value:.0f}</text>'
        )
        xv = x0 + fraction * (x1 - x0)
        x = sx(xv)
        parts.append(f'<path class="grid" d="M {x:.1f} {top} L {x:.1f} {top + plot_h}"/>')
        parts.append(
            f'<text class="tick" x="{x:.1f}" y="{top + plot_h + 14}" text-anchor="middle">{xv:.4g}</text>'
        )
    parts.append(
        f'<path class="axis" d="M {left} {top} L {left} {top + plot_h} L {left + plot_w} {top + plot_h}"/>'
    )
    if marker_y is not None and lo <= marker_y <= hi:
        y = sy(marker_y)
        parts.append(f'<path class="marker" d="M {left} {y:.1f} L {left + plot_w} {y:.1f}"/>')

    for index, trace in enumerate(traces):
        clipped = np.clip(trace.y, lo, hi)
        points = " ".join(
            f"{'M' if i == 0 else 'L'} {sx(float(xv)):.2f} {sy(float(yv)):.2f}"
            for i, (xv, yv) in enumerate(zip(trace.x, clipped, strict=True))
        )
        parts.append(f'<path class="trace {trace.css_class}" d="{points}"/>')
        parts.append(
            f'<text class="key {trace.css_class}" x="{left + 8}" y="{top + 14 + index * 14}" '
            f'fill="currentColor">{trace.label}</text>'
        )

    if title:
        parts.append(f'<text class="title" x="{left}" y="{top - 10}">{title}</text>')
    if x_label:
        parts.append(
            f'<text class="tick" x="{left + plot_w / 2}" y="{height - 6}" '
            f'text-anchor="middle">{x_label}</text>'
        )
    if y_label:
        parts.append(
            f'<text class="tick" transform="rotate(-90 12 {top + plot_h / 2})" x="12" '
            f'y="{top + plot_h / 2}" text-anchor="middle">{y_label}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


def horn_pattern_plot(
    *,
    aperture_a1_m: float,
    aperture_b1_m: float,
    rho1_m: float,
    rho2_m: float,
    freq_hz: float,
    max_theta_deg: float = 90.0,
) -> str:
    """E- and H-plane patterns of a pyramidal horn, as an SVG.

    Floors the display at -40 dB. Below that the aperture model is not describing anything
    real anyway (see M1's validity notes), so plotting it would be drawing noise with a
    confident line.
    """
    from jansky_forge.horns import e_plane_pattern, h_plane_pattern

    theta = np.linspace(-max_theta_deg, max_theta_deg, 361)
    e_db = e_plane_pattern(
        aperture_b1_m=aperture_b1_m, rho1_m=rho1_m, freq_hz=freq_hz, theta_deg=theta
    )
    h_db = h_plane_pattern(
        aperture_a1_m=aperture_a1_m, rho2_m=rho2_m, freq_hz=freq_hz, theta_deg=theta
    )
    return line_plot(
        [
            Trace("E-plane", theta, e_db, "e-plane"),
            Trace("H-plane", theta, h_db, "h-plane"),
        ],
        title="Radiation pattern",
        x_label="angle from boresight (degrees)",
        y_label="dB",
        y_min=-40.0,
        y_max=1.0,
        marker_y=-3.0,
    )


def sweep_plot(freq_hz: np.ndarray, values: np.ndarray, *, label: str, y_label: str) -> str:
    """A quantity against frequency — SWR from a measured sweep, gain across a band."""
    return line_plot(
        [Trace(label, np.asarray(freq_hz) / 1e6, np.asarray(values), "e-plane")],
        title=label,
        x_label="frequency (MHz)",
        y_label=y_label,
    )
