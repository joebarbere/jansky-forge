"""Tests for the catalog — mostly tests of *honesty*, not of arithmetic.

The catalog's value is that its numbers can be trusted and say how far. These tests are the
mechanism that keeps that true as entries are added: provenance rules are executable, and every
published figure is compared against what our model independently computes.

**When a published-figure check fails, the fix is a caveat, not a tuned efficiency.** See
`CLAUDE.md` honesty invariant 1.
"""

from __future__ import annotations

import pytest

from jansky_forge import catalog
from jansky_forge.bands import BANDS
from jansky_forge.core import AntennaModel


def test_the_catalog_is_not_empty_and_includes_the_station_dish():
    slugs = {t.slug for t in catalog.all_templates()}
    assert "discovery-dish" in slugs
    assert len(slugs) >= 8


def test_audit_is_silent():
    """The executable form of the provenance rules. Any output is an honesty failure."""
    assert list(catalog.audit()) == []


def test_every_template_has_a_source_and_a_meaningful_summary():
    for t in catalog.all_templates():
        assert t.source_url.startswith("https://"), t.slug
        assert len(t.summary) > 40, f"{t.slug}: summary should say what the build is FOR"
        assert isinstance(t.model, AntennaModel), t.slug
        assert t.design_band.slug in BANDS, t.slug


def test_every_template_characterizes_at_its_design_band():
    for t in catalog.all_templates():
        char = t.characterize()
        assert char.freq_hz == t.design_band.freq_hz
        assert char.gain_dbi > 0, t.slug
        assert 0.0 < char.aperture_efficiency <= 1.0, t.slug
        assert char.hpbw_e_deg > 0 and char.hpbw_h_deg > 0, t.slug


def test_templates_can_be_characterized_off_their_design_band():
    dish = catalog.get("discovery-dish")
    at_hi = dish.characterize()
    at_oh = dish.characterize(BANDS["oh1667"].freq_hz)
    # Higher frequency, same dish: more gain, narrower beam.
    assert at_oh.gain_dbi > at_hi.gain_dbi
    assert at_oh.hpbw_e_deg < at_hi.hpbw_e_deg


def test_lookup_and_filtering():
    assert catalog.get("pictor").design_band.slug == "hi"
    hi_builds = catalog.find(band="hi")
    assert len(hi_builds) >= 7
    horns = catalog.find(kind="horn")
    assert {t.slug for t in horns} >= {"bharat-horn", "physicsopenlab-horn"}
    # Band filter also matches templates that merely declare the band as useful.
    assert any(t.slug == "discovery-dish" for t in catalog.find(band="lband"))
    # Filters compose.
    assert all("dish" in t.kind.lower() for t in catalog.find(band="hi", kind="dish"))


def test_unknown_lookups_fail_loudly_with_the_alternatives():
    with pytest.raises(KeyError, match="known templates"):
        catalog.get("no-such-antenna")
    with pytest.raises(KeyError, match="known bands"):
        catalog.find(band="no-such-band")


def test_duplicate_slugs_are_rejected():
    existing = catalog.get("pictor")
    with pytest.raises(ValueError, match="duplicate"):
        catalog.register(existing)


def test_the_audit_actually_catches_dishonest_entries():
    """The audit is the enforcement mechanism, so prove it fires rather than trusting it.

    A silent audit over a good catalog proves nothing on its own — an audit that never
    complains would pass that test too.
    """
    from jansky_forge.apertures import ParabolicDish

    bad = catalog.Template(
        slug="bad-entry",
        name="Entry with no real source",
        model=ParabolicDish(diameter_m=1.0),
        design_band=BANDS["hi"],
        summary="A template that breaks every provenance rule at once, for testing.",
        provenance=catalog.Provenance.COMMUNITY,
        source_url="ask me on a forum",
        also_useful_at=("not-a-band",),
        caveats=(),
    )
    catalog.register(bad)
    try:
        messages = list(catalog.audit())
        assert any("source_url is not a URL" in m for m in messages)
        assert any("no caveats are recorded" in m for m in messages)
        assert any("unknown band" in m for m in messages)
    finally:
        catalog._TEMPLATES.pop("bad-entry")
    # And the real catalog is clean again.
    assert list(catalog.audit()) == []


def test_non_primary_provenance_always_carries_caveats():
    for t in catalog.all_templates():
        if t.provenance in (catalog.Provenance.COMMUNITY, catalog.Provenance.WORKED_EXAMPLE):
            assert t.caveats, (
                f"{t.slug}: community/worked-example entries must say what is uncertain"
            )


# --------------------------------------------------------------------------------------
# Published-figure cross-checks.
#
# These compare OUR model against what a source published. Agreement is reassurance;
# disagreement is information, and the tolerance encodes which we found. Every loose
# tolerance below is explained in the corresponding template's caveats.
# --------------------------------------------------------------------------------------


def test_pictor_beamwidth_disagreement_is_the_documented_size():
    """PICTOR publishes 8.95 deg; our default beam constant predicts ~9.85 deg.

    The disagreement is real and deliberately preserved — it reflects PICTOR's illumination
    taper (an implied beam constant of ~63.6 versus our generic 70), both inside the textbook
    range. If this test starts passing tightly, someone has retuned the constant to match, and
    the cross-check has been destroyed rather than satisfied.
    """
    template = catalog.get("pictor")
    predicted = template.characterize().hpbw_e_deg
    published = template.published["hpbw_deg"]
    assert predicted == pytest.approx(9.85, abs=0.05)
    assert 0.05 < (predicted - published) / published < 0.15
    assert any("63.6" in c for c in template.caveats)


def test_salsa_beamwidth_agrees_with_the_observatory():
    template = catalog.get("salsa")
    predicted = template.characterize().hpbw_e_deg
    assert predicted == pytest.approx(template.published["hpbw_deg"], rel=0.10)


def test_bharat_gain_falls_short_by_the_dual_mode_advantage():
    """The paper measures 20.6 dBi; a generic 51%-efficient cone predicts ~19.5 dBi.

    The ~1.1 dB gap is the Potter dual-mode design outperforming a simple conical horn — real
    physics our M0 model does not represent. Recorded, not erased.
    """
    template = catalog.get("bharat-horn")
    predicted = template.characterize().gain_dbi
    published = template.published["gain_dbi"]
    assert predicted == pytest.approx(19.46, abs=0.1)
    assert 0.7 < published - predicted < 1.5
    # And the reason is stated where a reader will find it.
    assert any("dual-mode" in c or "Potter" in c for c in template.caveats)


def test_physicsopenlab_horn_gain_agrees_with_its_published_figure():
    template = catalog.get("physicsopenlab-horn")
    predicted = template.characterize().gain_dbi
    assert predicted == pytest.approx(template.published["gain_dbi"], abs=0.2)


def test_worked_example_horn_hits_its_design_gain():
    """Our model versus an independent implementation of the same textbook synthesis.

    Two independent codes agreeing on 18 dBi from identical geometry is a genuine check on our
    arithmetic — though it is agreement about theory, which the template's caveats say plainly.
    """
    template = catalog.get("horn-18dbi-worked")
    assert template.characterize().gain_dbi == pytest.approx(18.0, abs=0.15)


def test_itty_bitty_beamwidth_disagreement_is_recorded():
    template = catalog.get("itty-bitty")
    predicted = template.characterize().hpbw_e_deg
    assert predicted == pytest.approx(3.76, abs=0.05)
    assert predicted > template.published["hpbw_deg"]
    assert any("offset" in c for c in template.caveats)
