"""The catalog: known radio-astronomy antenna builds, ready to select and modify.

The point of this module is that nobody should start from a blank sheet. Pick the dish
you own or the horn from the paper you read, see what the model says it does, then change
one dimension and watch the numbers move. Templates are starting points, not gospel.

**Provenance discipline.** Every entry carries where its geometry came from, a source
URL, and — where a number could not be verified from a primary source — an explicit
gap in ``caveats`` rather than a plausible-looking value. This is the same honesty rule
the sibling repos apply to results: a number whose origin is not stated is not a number
this project will print. :func:`~jansky_forge.catalog.audit` and the catalog tests
enforce it mechanically.

**Published figures are checks, not claims.** Where a build publishes a gain or
beamwidth, it goes in ``published`` and the test suite compares it against what our model
computes from the geometry. A disagreement is information — recorded in ``caveats``, not
smoothed over by tuning an efficiency until the numbers match.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from enum import StrEnum

from jansky_forge.apertures import ConicalHorn, ParabolicDish, PyramidalHorn
from jansky_forge.bands import BANDS, Band, get_band
from jansky_forge.core import AntennaModel, Characterization


class Provenance(StrEnum):
    """Where a template's geometry came from — the reader's guide to how far to trust it."""

    #: Manufacturer datasheet or shop listing for a product you can buy.
    MANUFACTURER = "manufacturer"
    #: A peer-reviewed paper or an observatory's own instrument documentation.
    PUBLISHED = "published"
    #: A well-documented community/amateur build guide.
    COMMUNITY = "community"
    #: Geometry chosen by this project as a worked teaching example, not copied from a build.
    WORKED_EXAMPLE = "worked_example"


@dataclass(frozen=True)
class Template:
    """A named, pre-designed antenna: a model plus the story of where it came from."""

    slug: str
    name: str
    model: AntennaModel
    #: Band this build was designed for; characterization defaults to its frequency.
    design_band: Band
    summary: str
    provenance: Provenance
    #: Primary source for the geometry. Required — see the module docstring.
    source_url: str
    #: Other bands the same hardware is usefully pointed at.
    also_useful_at: tuple[str, ...] = ()
    #: Figures the source publishes, for cross-checking our model (never for display as ours).
    published: dict[str, float] = field(default_factory=dict)
    #: Honest gaps, disagreements, and "verify this before cutting metal" warnings.
    caveats: tuple[str, ...] = ()

    def characterize(self, freq_hz: float | None = None) -> Characterization:
        """Characterize at ``freq_hz``, defaulting to the band this build was designed for."""
        return self.model.characterize(freq_hz if freq_hz is not None else self.design_band.freq_hz)

    @property
    def kind(self) -> str:
        return self.model.kind


# --------------------------------------------------------------------------------------
# The catalog itself. Entries are registered at import; see `docs` in the plan for how a
# new one is added (the /catalog-entry skill walks the provenance requirements).
# --------------------------------------------------------------------------------------

_TEMPLATES: dict[str, Template] = {}


def register(template: Template) -> Template:
    """Add a template to the catalog, rejecting duplicate slugs."""
    if template.slug in _TEMPLATES:
        raise ValueError(f"duplicate catalog slug {template.slug!r}")
    _TEMPLATES[template.slug] = template
    return template


def get(slug: str) -> Template:
    """Look up one template by slug."""
    try:
        return _TEMPLATES[slug]
    except KeyError:
        raise KeyError(
            f"unknown template {slug!r}; known templates: {', '.join(sorted(_TEMPLATES))}"
        ) from None


def all_templates() -> list[Template]:
    """Every template, slug-sorted."""
    return [_TEMPLATES[slug] for slug in sorted(_TEMPLATES)]


def find(*, band: str | None = None, kind: str | None = None) -> list[Template]:
    """Filter the catalog by design band slug and/or antenna kind (case-insensitive substring)."""
    if band is not None and band not in BANDS:
        raise KeyError(f"unknown band {band!r}; known bands: {', '.join(sorted(BANDS))}")
    results = []
    for template in all_templates():
        if (
            band is not None
            and band != template.design_band.slug
            and band not in template.also_useful_at
        ):
            continue
        if kind is not None and kind.lower() not in template.kind.lower():
            continue
        results.append(template)
    return results


def audit() -> Iterator[str]:
    """Yield one message per catalog-integrity problem; silence means the catalog is honest.

    Checked: a source URL on every entry, a caveat on every entry whose provenance is not
    a manufacturer/published primary source, and that every declared extra band exists.
    The test suite fails on any output.
    """
    for template in all_templates():
        if not template.source_url.startswith(("http://", "https://")):
            yield f"{template.slug}: source_url is not a URL ({template.source_url!r})"
        if (
            template.provenance in (Provenance.COMMUNITY, Provenance.WORKED_EXAMPLE)
            and not template.caveats
        ):
            yield (
                f"{template.slug}: provenance is {template.provenance} but no caveats are "
                "recorded — say what is uncertain"
            )
        for band_slug in template.also_useful_at:
            if band_slug not in BANDS:
                yield f"{template.slug}: also_useful_at references unknown band {band_slug!r}"


def _b(slug: str) -> Band:
    return get_band(slug)


# --------------------------------------------------------------------------------------
# Dishes
#
# Wire-antenna builds (the Radio JOVE dual dipole, meteor-scatter yagis) are deliberately
# absent until M5 gives them a model that can characterize them. A template the tool
# cannot evaluate would be decoration; one with invented numbers would be worse.
# --------------------------------------------------------------------------------------

register(
    Template(
        slug="discovery-dish",
        name="KrakenRF Discovery Dish (700 mm, H-line feed)",
        model=ParabolicDish(
            diameter_m=0.700,
            f_over_d=0.35,
            surface_rms_mm=1.0,
        ),
        design_band=_b("hi"),
        summary=(
            "Three-petal solid aluminium prime-focus dish with an integrated dipole feed and "
            "two-stage LNA — the turnkey starting point for amateur 21 cm work, and the "
            "reference antenna of the jansky station."
        ),
        provenance=Provenance.MANUFACTURER,
        source_url="https://github.com/krakenrf/discoverydish_docs/wiki",
        also_useful_at=("lband",),
        caveats=(
            "The vendor publishes NO gain, beamwidth, or surface-accuracy figure. Everything "
            "this tool reports for it is our model's prediction from the 700 mm diameter, not "
            "a manufacturer claim.",
            "Surface RMS is not stated; 1 mm is assumed. For a machined solid petal at 21 cm "
            "this is generous either way — Ruze loss is under 0.02 dB — so the assumption "
            "barely matters here. It would matter enormously if the same dish were used above "
            "~5 GHz.",
            "Efficiency factors are the model's generic defaults, not measured for this dish. "
            "The integrated feed's actual illumination taper is not published.",
            "The H-line feed is SAW-filtered to roughly 1380-1460 MHz; characterizing this "
            "template far outside that range describes the reflector alone, not the product.",
            "A widely-mirrored '65 cm / 1.69 GHz' spec circulates online; it traces to no "
            "primary source and contradicts the vendor wiki. 700 mm is the documented figure.",
            "At 21 cm this dish is only 3.3 wavelengths across, so the model emits its "
            "electrically-small warning. That is not a defect in the product — it is a real "
            "caution that aperture theory is least reliable at this size, where edge "
            "diffraction and feed-versus-dish scale matter. Expect the true gain to sit at or "
            "below our prediction, and treat measurement (M7/M8) as the arbiter.",
        ),
    )
)

register(
    Template(
        slug="pictor",
        name="PICTOR (1.5 m open-source radio telescope)",
        model=ParabolicDish(diameter_m=1.5, f_over_d=0.411),
        design_band=_b("hi"),
        summary=(
            "The open-source 1.5 m prime-focus telescope in Greece that anyone can queue "
            "observations on — the reference design most amateur HI dishes are compared against."
        ),
        provenance=Provenance.PUBLISHED,
        source_url="https://github.com/0xCoto/PICTOR",
        also_useful_at=("lband", "oh1612", "oh1665", "oh1667"),
        published={"hpbw_deg": 8.95},
        caveats=(
            "PICTOR publishes a beamwidth of 8.95 deg at 1420 MHz; our model's default "
            "HPBW = 70*lambda/D predicts 9.85 deg. The published figure implies a beam "
            "constant near 63.6, which is inside the textbook 58-72 range — so this is a "
            "difference in illumination taper, not an error in either number. We deliberately "
            "do NOT retune our constant to match: the disagreement is the useful information.",
            "Antenna gain is not published (the quoted 30 dB is the LNA, not the antenna).",
            "Secondary sources mention a 3.2 m upgrade; it does not appear in the project's own "
            "documentation and is treated here as unverified.",
        ),
    )
)

register(
    Template(
        slug="salsa",
        name="SALSA (Onsala 2.3 m student telescope)",
        model=ParabolicDish(diameter_m=2.3),
        design_band=_b("hi"),
        summary=(
            "Onsala Space Observatory's remotely-operable 2.3 m student telescopes — a "
            "professional observatory's answer to 'what is the smallest real HI instrument?'"
        ),
        provenance=Provenance.PUBLISHED,
        source_url="https://salsa.oso.chalmers.se/technical",
        also_useful_at=("lband", "oh1612"),
        published={"hpbw_deg": 6.0},
        caveats=(
            "f/D is not published; the model default (0.4) is used, so the subtended-angle and "
            "feed-matching numbers this tool reports for SALSA are illustrative only.",
            "Gain and effective area are not published — the observatory states its main-beam "
            "efficiency is itself poorly known, which is an unusually honest thing for an "
            "instrument page to say and worth respecting rather than papering over.",
            "There are three near-identical telescopes (Torre, Vale, Brage) differing in cable "
            "runs; this template represents the common design.",
        ),
    )
)

register(
    Template(
        slug="srt-haystack",
        name="MIT Haystack Small Radio Telescope (SRT)",
        model=ParabolicDish(diameter_m=2.3),
        design_band=_b("hi"),
        summary=(
            "The educational telescope that taught a generation of undergraduates 21 cm "
            "observing: a small dish with a helical feed and a documented, copyable design."
        ),
        provenance=Provenance.PUBLISHED,
        source_url="https://www.haystack.mit.edu/wp-content/uploads/2020/07/srt_SRT_Hardware_Manual.pdf",
        also_useful_at=("lband",),
        caveats=(
            "The SRT has no single canonical diameter — the hardware manual presents the dish "
            "as the institution's choice (a 2.3 m Kaul-Tronics prototype, a 1.8 m Sadoun, or "
            "mesh alternatives), and published spec tables disagree: some state 2.1 m, others "
            "2.3 m with otherwise identical numbers. We model the 2.3 m Haystack prototype and "
            "flag the conflict rather than resolving it by preference.",
            "f/D and surface accuracy are not published; model defaults are used.",
            "The feed is a 2-turn LCP helix (63.5 mm diameter, 30.0 mm spacing, 8.61 deg pitch) "
            "centred at 1420 MHz. Helical feeds are not modelled until M5, so no feed/dish "
            "matching is available for this template yet.",
            "A separate dish-less 'SRT' pyramidal horn exists in the Haystack memo series with "
            "its own published figures (17.25 dBi, 16.5 x 24.1 deg). It is a different "
            "instrument and is not merged into this entry.",
            "The kit is no longer commercially available; this is a design to copy, not to buy.",
        ),
    )
)

register(
    Template(
        slug="itty-bitty",
        name="Itty Bitty Telescope (18-inch DBS dish, Ku band)",
        model=ParabolicDish(
            diameter_m=0.4572,
            surface_rms_mm=0.5,
            blockage_efficiency=1.0,  # offset feed: nothing blocks the aperture
        ),
        design_band=_b("ku"),
        summary=(
            "The classic outreach telescope: a surplus 18-inch satellite-TV dish and an LNB "
            "that detects the Sun, warm buildings and trees against cold sky, and the "
            "Clarke-belt satellites — radio astronomy for the price of a yard-sale dish."
        ),
        provenance=Provenance.PUBLISHED,
        source_url="https://www.aoc.nrao.edu/epo/teachers/ittybitty/procedure.html",
        published={"hpbw_deg": 3.0},
        caveats=(
            "NRAO publishes a 3 deg beamwidth; our model predicts about 3.8 deg from the "
            "18-inch figure. A DBS dish is an offset ellipse whose quoted size is its physical "
            "long axis, while the electrically-relevant projected aperture differs — this "
            "template models it as a circular dish of the quoted diameter, which is an "
            "approximation, and the disagreement is where that approximation shows.",
            "f/D, gain, surface accuracy and the LNB model are not published; defaults are "
            "used, and blockage is set to 1.0 because an offset feed does not shadow the "
            "aperture.",
            "The band is quoted as 12.2-12.7 GHz; the often-repeated '12,000 MHz' is a rounding.",
        ),
    )
)


# --------------------------------------------------------------------------------------
# Horns
# --------------------------------------------------------------------------------------

register(
    Template(
        slug="bharat-horn",
        name="BHARAT dual-mode conical horn (21 cm teaching telescope)",
        model=ConicalHorn(aperture_diameter_m=0.884, axial_length_m=1.500),
        design_band=_b("hi"),
        summary=(
            "A peer-reviewed, fully-characterized 21 cm teaching horn — the best-documented "
            "amateur-scale HI antenna in the literature, and the natural comparison point for "
            "any horn this tool designs."
        ),
        provenance=Provenance.PUBLISHED,
        source_url="https://arxiv.org/abs/2208.06070",
        also_useful_at=("lband",),
        published={
            "gain_dbi": 20.6,
            "fwhm_deg": 16.5,
            "effective_area_m2": 0.407,
            "aperture_efficiency": 0.663,
        },
        caveats=(
            "CORRECTED AT M1. The M0 model assumed a flat 51% aperture efficiency, predicted "
            "19.46 dBi against the paper's measured 20.6, and attributed the 1.1 dB gap to "
            "this horn's dual-mode (Potter) design. That explanation was mostly wrong: once "
            "M1 computed the actual aperture phase error, the prediction rose to ~20.25 dBi "
            "and the gap fell to ~0.35 dB. Most of what looked like a dual-mode advantage was "
            "simply phase error being mismodelled. The lesson is kept on the record rather "
            "than quietly overwritten.",
            "It IS a dual-mode (Potter) horn — a step discontinuity excites TM11 to clean up "
            "the pattern, and the paper reports 66.3% aperture efficiency against our ~63.8%. "
            "That residual is a real effect our single-mode model does not represent, and it "
            "is left in place rather than erased by adopting the paper's efficiency.",
            "The throat diameter is not published, so the apex is taken at the throat: this "
            "understates the slant, overstates the phase error, and makes our gain a "
            "conservative floor. A known throat would close the remaining gap further.",
            "The published 16.5 deg FWHM was measurable in the E-plane only; separate E- and "
            "H-plane widths are not published, so only one of our two predicted widths can be "
            "checked.",
            "The paper's dimensioned drawing carries throat and step dimensions without part "
            "labels; which dimension is which cannot be determined from it, so none are "
            "assigned here. Aperture (884 mm) and overall axial length (1500 mm) are "
            "unambiguous and are what this template uses.",
            "Appendix B of the same paper offers a cheaper pyramidal alternative (17 dBi, "
            "~26 deg) for builders without the tooling for a dual-mode cone.",
        ),
    )
)

register(
    Template(
        slug="physicsopenlab-horn",
        name="PhysicsOpenLab 21 cm pyramidal horn (oil-can waveguide)",
        model=PyramidalHorn(
            aperture_a_m=0.750,
            aperture_b_m=0.600,
            axial_length_m=0.700,
            waveguide_a_m=0.146,
            waveguide_b_m=0.117,
        ),
        design_band=_b("hi"),
        summary=(
            "The build that proves a hydrogen-line horn is a weekend of aluminium sheet and a "
            "five-litre oil can: full dimensions, a quarter-wave probe, and a documented "
            "detection."
        ),
        provenance=Provenance.COMMUNITY,
        source_url="https://physicsopenlab.org/2020/07/20/horn-antenna-for-the-21cm-neutral-hydrogen-line/",
        published={"gain_dbi": 18.16, "hpbw_h_deg": 20.0, "hpbw_e_deg": 24.0},
        caveats=(
            "The quoted 18.16 dBi comes from an unnamed online calculator, not a measurement. "
            "Our independent model agrees closely (about 18.1 dBi), which is reassuring about "
            "both — but neither is measured data.",
            "The quoted beamwidths are explicitly borrowed by the author from 'antennas built "
            "with similar geometries', and they put the wider beam in the E-plane while our "
            "model puts it in the H-plane. Treat the published widths as indicative only.",
            "The waveguide is a 5-litre oblong oil can cut to 23 cm, with a 5.25 cm brass probe "
            "7.64 cm from the backshort. Real cans vary; measure yours.",
            "The author states the aperture and length were adopted from other projects rather "
            "than derived, so this geometry is not optimized for anything in particular.",
        ),
    )
)

register(
    Template(
        slug="dspira-mini-horn",
        name="DSPIRA mini horn (foam-board 21 cm classroom build)",
        model=PyramidalHorn(
            aperture_a_m=0.3778,
            aperture_b_m=0.3016,
            axial_length_m=0.368,
            waveguide_a_m=0.168,
            waveguide_b_m=0.105,
        ),
        design_band=_b("hi"),
        summary=(
            "Four foam panels, foil tape, and a paint can: the cheapest documented 21 cm horn, "
            "used in the WVU RAIL/DSPIRA classroom programme."
        ),
        provenance=Provenance.COMMUNITY,
        source_url="https://wvurail.org/dspira-lessons/FilesUploaded/MiniHorn_construction.pdf",
        caveats=(
            "The source is a cutting plan, not a characterization: NO gain or beamwidth is "
            "published, so every performance number here is purely our model's prediction.",
            "The plan gives a 14.5 inch SLANT height; this template enters it as the axial "
            "length, which slightly overstates the true axial dimension. Axial length does not "
            "affect the M0 gain model, but it will matter once M1 adds the phase-error "
            "correction — revisit this number then.",
            "Waveguide dimensions are those of a one-gallon oblong paint can and vary by "
            "manufacturer. The probe hole is specified 5.25 cm from the top.",
            "At roughly 12 dBi predicted this is a genuinely small horn — capable of the HI "
            "line with patience and a good LNA, but it is a teaching instrument first.",
        ),
    )
)

register(
    Template(
        slug="horn-18dbi-worked",
        name="Worked example: 18 dBi pyramidal horn at 1420 MHz",
        model=PyramidalHorn(
            aperture_a_m=0.73219,
            aperture_b_m=0.59786,
            axial_length_m=0.68185,
            axial_length_h_m=0.57836,
            waveguide_a_m=0.177034,
            waveguide_b_m=0.082899,
        ),
        design_band=_b("hi"),
        summary=(
            "A standard optimum-pyramidal-horn synthesis for 18 dBi at the hydrogen line — the "
            "reference point for 'what size does the textbook say', and a cross-check on our "
            "own arithmetic."
        ),
        provenance=Provenance.WORKED_EXAMPLE,
        source_url="https://www.astronomy.me.uk/pyramidal-horn-calculator-with-examples-for-1420-mhz-hydrogen-line-pyramidal-horn-build",
        published={"gain_dbi": 18.0},
        caveats=(
            "This is CALCULATOR OUTPUT, not a build. Nobody is documented as having cut metal "
            "to these dimensions, and there is no measured performance behind it.",
            "It earns its place as an independent check on our model: fed the same geometry, we "
            "predict about 18.0 dBi against the calculator's 18 dBi target. Two independent "
            "implementations of the same textbook equations agreeing is worth something — but "
            "it is agreement about theory, not about reality.",
            "NOT A BUILDABLE HORN AS SPECIFIED — found by M1. The source quotes different "
            "E- and H-plane axial lengths (682 and 578 mm), a 15% disagreement, because it "
            "optimizes the two sectoral horns independently. A pyramidal horn is one frustum "
            "with ONE axial length, so these two flares would have to start at different "
            "points on the waveguide. Both lengths are entered here deliberately so the model "
            "reports the problem; jansky-forge's own synthesis enforces realizability.",
            "The precise diagnosis, visible in the model output: this geometry has "
            "slant_e = 846.18 mm and slant_h = 846.10 mm — equal to four figures. The source "
            "equalized the two SLANT lengths (Balanis' rho_e, rho_h) where realizability "
            "requires equal AXIAL lengths (p_e, p_h). It is a subtle and very plausible "
            "confusion of two similar symbols, and it is why the same mistake is guarded "
            "against in this package's own notation table.",
            "The quoted throat (177.0 x 82.9 mm) is close to but not equal to standard WR-650 "
            "(165.1 x 82.55 mm) — check what waveguide you actually have before cutting.",
        ),
    )
)
