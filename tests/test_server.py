"""Tests for M9: the interactive UI.

The important test in this file is not that a page returns 200. It is that **a model's own
caveats reach the browser**. Every layer of this project prints them — the CLI has since M0 —
and a polished interface is the most tempting place to drop them for tidiness, precisely
because a number that looks designed is more readily believed.
"""

from __future__ import annotations

import re

import pytest

pytest.importorskip("fastapi", reason="the UI is an optional extra")

# Starlette's test client needs an HTTP client library and raises RuntimeError — not
# ImportError — when it is absent, so importorskip cannot guard it. Catch broadly and skip
# the module, otherwise a machine with fastapi but no httpx errors at collection time.
try:
    from fastapi.testclient import TestClient  # noqa: E402
except Exception as exc:  # pragma: no cover - environment-dependent
    pytest.skip(f"fastapi's test client is unusable here: {exc}", allow_module_level=True)

from jansky_forge import catalog  # noqa: E402
from jansky_forge.server import create_app, plots  # noqa: E402


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


# --------------------------------------------------------------------------------------
# The rule this UI inherits
# --------------------------------------------------------------------------------------


def test_catalog_detail_shows_the_models_caveats_and_the_entrys_own(client):
    """The Discovery Dish has both, and the page must show both.

    Its caveats include that the vendor publishes no gain figure at all, and its model notes
    include the electrically-small warning. A user who sees the number without those is being
    misled by omission.
    """
    body = client.get("/catalog/discovery-dish").text
    assert "vendor publishes NO gain" in body
    assert "aperture theory degrades" in body  # the model's own note
    assert "Caveats" in body and "What the model wants you to know" in body


def test_published_figures_are_labelled_as_cross_checks_not_our_output(client):
    body = client.get("/catalog/pictor").text
    assert "Published figures" in body
    assert "never restated as our own" in body
    assert "8.95" in body  # PICTOR's published beamwidth


def test_provenance_and_source_link_are_on_every_detail_page(client):
    for slug in ("discovery-dish", "bharat-horn", "radio-jove"):
        body = client.get(f"/catalog/{slug}").text
        template = catalog.get(slug)
        assert "Provenance" in body
        assert template.source_url in body


def test_the_design_page_shows_notes_with_every_result(client):
    body = client.get(
        "/design/compute",
        params={"gain_dbi": 18, "band": "hi", "waveguide": "wr650", "shape": "pyramidal"},
    ).text
    assert "buildable as a single horn" in body
    assert "not an assumed efficiency" in body


def test_the_conical_result_admits_its_pattern_gap(client):
    """M1 and M3 both deferred conical patterns. The UI must not quietly imply otherwise."""
    body = client.get(
        "/design/compute",
        params={"gain_dbi": 18, "band": "hi", "waveguide": "wr650", "shape": "conical"},
    ).text
    assert "rules of thumb" in body
    assert "<svg" not in body  # and it plots nothing rather than plotting a guess


def test_the_api_carries_caveats_too(client):
    """A machine consumer that drops them is choosing to; one that never gets them cannot."""
    payload = client.get("/api/characterize", params={"slug": "discovery-dish"}).json()
    assert payload["notes"] and payload["caveats"]
    assert payload["provenance"] and payload["source_url"]
    assert payload["gain_dbi"] == pytest.approx(18.44, abs=0.1)


def test_the_footer_states_the_predicted_versus_measured_rule(client):
    # The template wraps, so compare on normalized whitespace rather than exact spacing.
    body = " ".join(client.get("/").text.split())
    assert "never let a prediction and a measurement wear the same label" in body


# --------------------------------------------------------------------------------------
# Pages
# --------------------------------------------------------------------------------------


def test_health_and_version(client):
    payload = client.get("/healthz").json()
    assert payload["ok"] is True
    from jansky_forge import __version__

    assert payload["version"] == __version__


def test_catalog_index_lists_every_template(client):
    body = client.get("/").text
    for template in catalog.all_templates():
        assert template.slug in body


def test_unknown_template_is_a_polite_page_not_a_traceback(client):
    response = client.get("/catalog/not-a-real-antenna")
    assert response.status_code == 200
    assert "No template called" in response.text


def test_unknown_slug_on_the_api_is_a_404(client):
    response = client.get("/api/characterize", params={"slug": "nope"})
    assert response.status_code == 404
    assert "known templates" in response.json()["error"]


def test_design_page_offers_the_bands_and_waveguides(client):
    body = client.get("/design").text
    assert "Neutral hydrogen" in body and "WR650" in body
    assert 'type="range"' in body  # the slider the milestone is about
    assert "genuinely live" in body


def test_feed_page_recomputes_for_a_given_focal_ratio(client):
    body = client.get("/feed", params={"f_over_d": 0.35}).text
    assert "rim sits" in body
    assert "71.1" in body  # the Discovery Dish's rim angle
    assert "half-power beamwidth near" in body


# --------------------------------------------------------------------------------------
# Live recompute
# --------------------------------------------------------------------------------------


def test_changing_the_gain_changes_the_dimensions(client):
    """The whole point of a slider: the metal must move when the number does."""

    def aperture_of(gain: float) -> float:
        body = client.get(
            "/design/compute",
            params={"gain_dbi": gain, "band": "hi", "waveguide": "wr650", "shape": "pyramidal"},
        ).text
        match = re.search(r"Aperture \(H-plane, wide\)</th><td>([\d.]+) mm", body)
        assert match, "the H-plane aperture should be in the result table"
        return float(match.group(1))

    assert aperture_of(20.0) > aperture_of(15.0) > aperture_of(12.0)


def test_an_absurd_but_valid_design_is_flagged_rather_than_presented_straight(client):
    """30 dBi at 20 MHz is geometrically fine and 205 metres across.

    Found while building this UI: the synthesis is bounded by physics, which is a long way
    past bounded by sense. It is a correct answer to the question asked and useless as
    advice, so the design now says so — in the UI and in the CLI, because the model carries
    the note rather than the presenter.
    """
    body = client.get(
        "/design/compute",
        params={"gain_dbi": 30, "band": "jove", "waveguide": "wr650", "shape": "pyramidal"},
    ).text
    assert "not a sensible antenna to build" in body
    assert "a reflector is the right antenna" in body


@pytest.mark.parametrize(
    "params",
    [
        {"band": "nonsense"},
        {"waveguide": "banana"},
        {"shape": "triangular"},
    ],
)
def test_bad_parameters_are_rejected_without_a_traceback(client, params):
    base = {"gain_dbi": 18, "band": "hi", "waveguide": "wr650", "shape": "pyramidal"}
    response = client.get("/design/compute", params={**base, **params})
    assert response.status_code == 200
    assert "Unknown" in response.text


def test_gain_is_bounded_by_the_api_not_just_the_slider(client):
    """A slider's min/max is a suggestion; the server must enforce its own range."""
    assert client.get("/design/compute", params={"gain_dbi": 500}).status_code == 422


# --------------------------------------------------------------------------------------
# Self-contained: no CDN, no build step
# --------------------------------------------------------------------------------------


def test_no_page_requests_anything_from_the_internet(client):
    """The tool must work on a laptop in a field with no signal.

    Antennas get built outdoors. A CDN reference would make the UI silently useless exactly
    where it is most wanted, so there are no external script or stylesheet references at all.
    """
    for path in ("/", "/design", "/feed", "/catalog/discovery-dish"):
        body = client.get(path).text
        assert "http://" not in body.replace("http://www.w3.org/2000/svg", "")
        assert "cdn." not in body
        assert "<script src=" not in body
        assert '<link rel="stylesheet"' not in body


def test_pages_are_theme_aware_without_a_toggle(client):
    body = client.get("/").text
    assert "prefers-color-scheme: dark" in body
    assert "color-scheme: light dark" in body


def test_html_is_escaped(client):
    """Catalog text is ours, but escaping is not optional just because the input is trusted."""
    from jansky_forge.server.app import _escape

    assert _escape("<script>alert(1)</script>") == "&lt;script&gt;alert(1)&lt;/script&gt;"
    assert _escape('a "quoted" & thing') == "a &quot;quoted&quot; &amp; thing"


# --------------------------------------------------------------------------------------
# Plots
# --------------------------------------------------------------------------------------


def test_pattern_plot_draws_both_planes_and_a_half_power_marker():
    from jansky_forge.horns import design_pyramidal_horn

    design = design_pyramidal_horn(
        gain_dbi=18.0, freq_hz=1_420_405_751.768, waveguide_a_m=0.1651, waveguide_b_m=0.08255
    )
    svg = plots.horn_pattern_plot(
        aperture_a1_m=design.aperture_a1_m,
        aperture_b1_m=design.aperture_b1_m,
        rho1_m=design.rho1_m,
        rho2_m=design.rho2_m,
        freq_hz=1_420_405_751.768,
    )
    assert svg.startswith("<svg")
    assert "E-plane" in svg and "H-plane" in svg
    assert 'class="marker"' in svg  # the -3 dB line
    assert "currentColor" in svg  # inherits the page theme


def test_plots_reject_nothing_to_draw():
    with pytest.raises(ValueError, match="nothing to plot"):
        plots.line_plot([])


def test_plot_handles_a_flat_trace_without_dividing_by_zero():
    import numpy as np

    svg = plots.line_plot([plots.Trace("flat", np.arange(5.0), np.ones(5))])
    assert "<svg" in svg


def test_sweep_plot_labels_frequency_in_megahertz():
    import numpy as np

    svg = plots.sweep_plot(
        np.linspace(1.4e9, 1.44e9, 5), np.linspace(1.1, 2.0, 5), label="SWR", y_label="SWR"
    )
    assert "frequency (MHz)" in svg
    assert "1400" in svg  # scaled to MHz, not left in hertz
