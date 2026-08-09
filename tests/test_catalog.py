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


def test_bharat_gain_gap_shrank_when_m1_modelled_the_phase_error():
    """M0 predicted 19.46 dBi and blamed the 1.1 dB shortfall on the Potter dual-mode design.

    M1 computes the actual aperture phase error and predicts ~20.25 dBi against the paper's
    measured 20.6 — so most of that "dual-mode advantage" was really phase error being
    mismodelled. This test pins the corrected number AND asserts the record of the earlier
    wrong explanation survives in the caveats, because quietly overwriting a superseded
    claim is how a project stops being trustworthy.
    """
    template = catalog.get("bharat-horn")
    predicted = template.characterize().gain_dbi
    published = template.published["gain_dbi"]
    assert predicted == pytest.approx(20.25, abs=0.1)
    assert 0.2 < published - predicted < 0.5
    assert any("CORRECTED AT M1" in c for c in template.caveats)
    # The residual really is the dual-mode effect, and it is still not tuned away.
    assert any("dual-mode" in c or "Potter" in c for c in template.caveats)


def test_physicsopenlab_horn_gain_agrees_with_its_published_figure():
    template = catalog.get("physicsopenlab-horn")
    predicted = template.characterize().gain_dbi
    assert predicted == pytest.approx(template.published["gain_dbi"], abs=0.2)


def test_worked_example_horn_is_reported_as_not_buildable():
    """M1 found the catalog's own worked example is not a realizable single horn.

    Its source quotes two different axial flare lengths (682 and 578 mm) because it
    optimized the E- and H-plane sectoral horns independently. Both are entered on purpose
    so the model reports the defect rather than hiding it behind a plausible gain figure.
    """
    template = catalog.get("horn-18dbi-worked")
    char = template.characterize()
    assert any("NOT a single buildable pyramidal horn" in n for n in char.notes)
    assert any("NOT A BUILDABLE HORN AS SPECIFIED" in c for c in template.caveats)
    # The precise diagnosis: the source equalized the slants, not the axial lengths.
    assert char.detail["slant_e_m"] == pytest.approx(char.detail["slant_h_m"], rel=1e-3)
    # And because it is over-flared in H, it falls short of its own 18 dBi target.
    assert char.gain_dbi < template.published["gain_dbi"]


def test_worked_example_geometry_would_hit_18_dbi_if_it_were_realizable():
    """Sanity: the E-plane half of that design is sound; only the mismatch spoils it.

    Rebuilding it with one consistent axial length recovers essentially the target gain,
    which is what tells us the source's equations were right and only its realizability
    constraint was missing.
    """
    from jansky_forge.apertures import PyramidalHorn

    fixed = PyramidalHorn(
        aperture_a_m=0.73219,
        aperture_b_m=0.59786,
        axial_length_m=0.68185,
        waveguide_a_m=0.177034,
        waveguide_b_m=0.082899,
    )
    assert fixed.characterize(BANDS["hi"].freq_hz).gain_dbi == pytest.approx(18.0, abs=0.4)


def test_itty_bitty_beamwidth_disagreement_is_recorded():
    template = catalog.get("itty-bitty")
    predicted = template.characterize().hpbw_e_deg
    assert predicted == pytest.approx(3.76, abs=0.05)
    assert predicted > template.published["hpbw_deg"]
    assert any("offset" in c for c in template.caveats)
