"""The interactive UI (M9): drag a number, watch the antenna change.

Everything before this was correct. This is the milestone that makes it *pleasant* — which
matters more than it sounds, because a design tool you enjoy poking is a design tool you
learn from. Tier-1 physics recomputes in microseconds, so a slider genuinely is live.

**Three deliberate departures from the plan's sketch**, each because the thing it replaced
would have been worse:

*No htmx, no charting library, no CDN.* The plan said "FastAPI + htmx + a canvas module".
What shipped is FastAPI + about thirty lines of inline vanilla JavaScript + server-rendered
SVG. A synthesis takes 0.12 ms, so an HTTP round trip is dominated by the network and there
is nothing for a client-side renderer to accelerate. Avoiding a CDN keeps the tool working on
a laptop in a field with no signal, which is where antennas get built.

*Server-rendered plots.* Same reasoning as M2's fabrication templates: SVG is text, this
package already writes it, and matplotlib is a heavy dependency to add for a line and an axis.

**The rule this UI inherits and must never break:** a model's own caveats are displayed, not
hidden for tidiness. Every ``Characterization`` carries notes about where it stops being
trustworthy, and the CLI has printed them since M0. A prettier interface is not a licence to
drop them — if anything the opposite, because a polished number is more readily believed.

Optional extra: ``pip install 'jansky-forge[ui]'``. The library and CLI are unchanged
without it.
"""

from __future__ import annotations

import math
from typing import Any

from jansky_forge import catalog, feeds, horns
from jansky_forge._version import __version__
from jansky_forge.apertures import ParabolicDish
from jansky_forge.bands import BANDS, get_band
from jansky_forge.server import plots
from jansky_forge.server.templates import (
    CATALOG_PAGE,
    DESIGN_PAGE,
    DESIGN_RESULT,
    page,
)

#: Named waveguides the design form offers, mirroring the CLI's set.
WAVEGUIDES: dict[str, tuple[float, float]] = {
    "wr650": (0.16510, 0.08255),
    "wr430": (0.10922, 0.05461),
    "wr340": (0.08636, 0.04318),
    "wr284": (0.07214, 0.03404),
    "wr90": (0.02286, 0.01016),
}


def _escape(text: object) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _notes_html(
    notes: tuple[str, ...], *, heading: str = "What the model wants you to know"
) -> str:
    """Render a model's caveats.

    Never returns empty when there are notes, and is never optional at a call site. See the
    module docstring: a prettier interface is not a licence to drop the warnings.
    """
    if not notes:
        return ""
    items = "".join(f"<li>{_escape(note)}</li>" for note in notes)
    return f'<div class="notes"><h3>{heading}</h3><ul>{items}</ul></div>'


def _design_result_html(
    *,
    gain_dbi: float,
    band_slug: str,
    waveguide: str,
    shape: str,
) -> str:
    """Synthesize, characterize and render — the payload a slider change swaps in."""
    freq_hz = get_band(band_slug).freq_hz
    rows: list[tuple[str, str]] = []
    notes: tuple[str, ...] = ()
    plot = ""
    # Separate names per branch: the two design types are unrelated dataclasses, and reusing
    # one variable makes every later attribute access ambiguous. Third time this pattern has
    # come up in this codebase — see the same shape in cli.py.
    summary = ""

    if shape == "conical":
        cone = horns.design_conical_horn(gain_dbi=gain_dbi, freq_hz=freq_hz)
        summary = cone.summary()
        rows = [
            ("Aperture diameter", f"{cone.aperture_diameter_m * 1000:.1f} mm"),
            ("Axial length", f"{cone.axial_length_m * 1000:.1f} mm"),
            ("Slant (apex to rim)", f"{cone.slant_m * 1000:.1f} mm"),
        ]
        notes = (
            *cone.notes,
            "Conical gain uses Balanis' empirical loss figure. Conical *patterns* are still "
            "rules of thumb, so no pattern is plotted here — see the M3 notes.",
        )
    else:
        wg_a, wg_b = WAVEGUIDES[waveguide]
        horn = horns.design_pyramidal_horn(
            gain_dbi=gain_dbi, freq_hz=freq_hz, waveguide_a_m=wg_a, waveguide_b_m=wg_b
        )
        e_hpbw, h_hpbw = horns.pattern_beamwidths(
            aperture_a1_m=horn.aperture_a1_m,
            aperture_b1_m=horn.aperture_b1_m,
            rho1_m=horn.rho1_m,
            rho2_m=horn.rho2_m,
            freq_hz=freq_hz,
        )
        rows = [
            ("Aperture (H-plane, wide)", f"{horn.aperture_a1_m * 1000:.1f} mm"),
            ("Aperture (E-plane, tall)", f"{horn.aperture_b1_m * 1000:.1f} mm"),
            ("Axial length", f"{horn.axial_length_m * 1000:.1f} mm"),
            ("Beamwidth (E × H)", f"{e_hpbw:.1f}° × {h_hpbw:.1f}°"),
            (
                "Phase deviation s / t",
                f"{horn.phase_deviation_e:.3f} / {horn.phase_deviation_h:.3f} "
                f"(optima {horns.OPTIMUM_PHASE_DEVIATION_E:g} / "
                f"{horns.OPTIMUM_PHASE_DEVIATION_H:g})",
            ),
        ]
        plot = plots.horn_pattern_plot(
            aperture_a1_m=horn.aperture_a1_m,
            aperture_b1_m=horn.aperture_b1_m,
            rho1_m=horn.rho1_m,
            rho2_m=horn.rho2_m,
            freq_hz=freq_hz,
        )
        notes = (
            *horn.notes,
            "Both flares share one axial length, so this is buildable as a single horn.",
            "Gain comes from the exact aperture-phase-error model, not an assumed efficiency.",
        )

    table = "".join(f"<tr><th>{_escape(k)}</th><td>{_escape(v)}</td></tr>" for k, v in rows)
    return DESIGN_RESULT.format(
        summary=_escape(summary or horn.summary()),
        table=table,
        plot=plot,
        notes=_notes_html(notes),
    )


def create_app() -> Any:
    """Build the FastAPI application.

    Imported lazily inside the function so the package still imports when the ``ui`` extra
    is not installed — the library and CLI must not depend on a web framework.
    """
    try:
        from fastapi import FastAPI, Query
        from fastapi.responses import HTMLResponse, JSONResponse
    except ImportError as exc:  # pragma: no cover - exercised by the availability test
        raise RuntimeError(
            "the UI needs the optional extra: pip install 'jansky-forge[ui]'"
        ) from exc

    app = FastAPI(title="jansky-forge", version=__version__, docs_url="/api-docs")

    @app.get("/healthz")
    def healthz() -> JSONResponse:
        return JSONResponse({"ok": True, "version": __version__})

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        rows = []
        for template in catalog.all_templates():
            char = template.characterize()
            rows.append(
                "<tr>"
                f"<td><code>{_escape(template.slug)}</code></td>"
                f"<td>{_escape(template.name)}</td>"
                f"<td>{_escape(template.kind)}</td>"
                f"<td>{char.gain_dbi:.2f} dBi</td>"
                f"<td>{char.hpbw_e_deg:.1f}° × {char.hpbw_h_deg:.1f}°</td>"
                f'<td><a href="/catalog/{_escape(template.slug)}">details</a></td>'
                "</tr>"
            )
        return page("Catalog", CATALOG_PAGE.format(rows="".join(rows)))

    @app.get("/catalog/{slug}", response_class=HTMLResponse)
    def catalog_detail(slug: str) -> str:
        try:
            template = catalog.get(slug)
        except KeyError:
            return page("Not found", f"<p>No template called <code>{_escape(slug)}</code>.</p>")
        char = template.characterize()
        geometry = "".join(
            f"<tr><th>{_escape(k)}</th><td>{v:g}</td></tr>"
            for k, v in template.model.parameters().items()
        )
        detail = "".join(
            f"<tr><th>{_escape(k)}</th><td>{v:g}</td></tr>" for k, v in char.detail.items()
        )
        published = (
            "".join(
                f"<tr><th>{_escape(k)}</th><td>{v:g}</td></tr>"
                for k, v in template.published.items()
            )
            if template.published
            else ""
        )
        body = [
            f"<h1>{_escape(template.name)}</h1>",
            f"<p class='lede'>{_escape(template.summary)}</p>",
            f"<p class='provenance'>Provenance: <strong>{_escape(template.provenance)}</strong> — "
            f'<a href="{_escape(template.source_url)}">source</a></p>',
            f"<h2>Predicted performance</h2><p><code>{_escape(char.summary())}</code></p>",
            f"<h2>Geometry</h2><table>{geometry}</table>",
            f"<h2>Detail</h2><table>{detail}</table>",
        ]
        if published:
            body.append(
                "<h2>Published figures</h2>"
                "<p class='lede'>Cross-checks against our model — never restated as our own "
                "output.</p>"
                f"<table>{published}</table>"
            )
        body.append(_notes_html(template.caveats, heading="Caveats"))
        body.append(_notes_html(char.notes))
        return page(template.name, "".join(body))

    @app.get("/design", response_class=HTMLResponse)
    def design_page() -> str:
        bands = "".join(
            f'<option value="{_escape(slug)}"{" selected" if slug == "hi" else ""}>'
            f"{_escape(BANDS[slug].name)}</option>"
            for slug in sorted(BANDS, key=lambda s: BANDS[s].freq_hz)
        )
        guides = "".join(
            f'<option value="{_escape(name)}"{" selected" if name == "wr650" else ""}>'
            f"{_escape(name.upper())}</option>"
            for name in WAVEGUIDES
        )
        return page(
            "Design",
            DESIGN_PAGE.format(
                bands=bands,
                waveguides=guides,
                initial=_design_result_html(
                    gain_dbi=18.0, band_slug="hi", waveguide="wr650", shape="pyramidal"
                ),
            ),
        )

    @app.get("/design/compute", response_class=HTMLResponse)
    def design_compute(
        gain_dbi: float = Query(18.0, ge=5.0, le=30.0),
        band: str = Query("hi"),
        waveguide: str = Query("wr650"),
        shape: str = Query("pyramidal"),
    ) -> str:
        if band not in BANDS:
            return "<p class='error'>Unknown band.</p>"
        if waveguide not in WAVEGUIDES:
            return "<p class='error'>Unknown waveguide.</p>"
        if shape not in ("pyramidal", "conical"):
            return "<p class='error'>Unknown shape.</p>"
        try:
            return _design_result_html(
                gain_dbi=gain_dbi, band_slug=band, waveguide=waveguide, shape=shape
            )
        except ValueError as exc:
            # A refused design is information, not a server error — say what it said.
            return f"<p class='error'>{_escape(exc)}</p>"

    @app.get("/api/characterize")
    def api_characterize(slug: str, freq_mhz: float | None = None) -> JSONResponse:
        try:
            template = catalog.get(slug)
        except KeyError as exc:
            return JSONResponse({"error": str(exc)}, status_code=404)
        char = template.characterize(freq_mhz * 1e6 if freq_mhz else None)
        return JSONResponse(
            {
                "slug": template.slug,
                "freq_hz": char.freq_hz,
                "gain_dbi": char.gain_dbi,
                "hpbw_e_deg": char.hpbw_e_deg,
                "hpbw_h_deg": char.hpbw_h_deg,
                "aperture_efficiency": char.aperture_efficiency,
                "effective_area_m2": char.effective_area_m2,
                # Caveats ride the API too. A machine consumer that drops them is choosing
                # to; one that never receives them cannot.
                "notes": list(char.notes),
                "caveats": list(template.caveats),
                "provenance": str(template.provenance),
                "source_url": template.source_url,
            }
        )

    @app.get("/feed", response_class=HTMLResponse)
    def feed_page(f_over_d: float = Query(0.35, gt=0.05, le=2.0)) -> str:
        wanted = feeds.best_feed_for_dish(f_over_d=f_over_d)
        dish = ParabolicDish(diameter_m=0.7, f_over_d=f_over_d)
        theta0 = math.degrees(2 * math.atan(1 / (4 * f_over_d)))
        body = [
            "<h1>Feed matching</h1>",
            "<form method='get' action='/feed'>",
            "<label>Dish f/D <input type='number' name='f_over_d' step='0.01' "
            f"min='0.1' max='2' value='{f_over_d:g}'></label> "
            "<button type='submit'>Recompute</button></form>",
            f"<p>The rim sits <strong>{theta0:.1f}°</strong> off the feed axis.</p>",
            f"<p><code>{_escape(wanted.summary())}</code></p>",
            _notes_html(wanted.notes, heading="What feed this dish wants"),
            _notes_html(dish.characterize(get_band("hi").freq_hz).notes),
        ]
        return page("Feed matching", "".join(body))

    return app
