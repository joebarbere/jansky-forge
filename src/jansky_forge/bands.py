"""The frequencies amateur radio astronomy actually cares about.

A design is only meaningful at a frequency, and in this field the interesting
frequencies are a short, physically-motivated list rather than a continuum: spectral
lines fixed by atomic physics, and a handful of bands fixed by what is observable with
modest hardware. Catalog templates declare which of these they target, and every
characterization defaults to its template's design band.

Rest frequencies are laboratory values; observed frequencies are Doppler-shifted from
them (jansky-observe owns that correction for real spectra — this package only ever
designs *for* the rest frequency plus a stated bandwidth).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Band:
    """A named frequency of interest, with the reason it matters."""

    slug: str
    name: str
    freq_hz: float
    why: str
    #: Useful design bandwidth around ``freq_hz`` (Hz); 0 where "a band", not a line.
    bandwidth_hz: float = 0.0

    @property
    def freq_mhz(self) -> float:
        return self.freq_hz / 1e6


#: Neutral hydrogen — the line every amateur radio telescope is ultimately built for.
HI_21CM = Band(
    slug="hi",
    name="Neutral hydrogen (HI) 21 cm",
    freq_hz=1_420_405_751.768,
    why="Galactic HI: rotation curves, spiral structure, the first-light target of nearly every amateur dish.",
    bandwidth_hz=4e6,
)

#: The four ground-state OH lines — the second-easiest spectral target after HI.
OH_1612 = Band(
    "oh1612", "Hydroxyl (OH) 1612 MHz", 1_612_231_000.0, "OH satellite line; evolved-star masers."
)
OH_1665 = Band(
    "oh1665", "Hydroxyl (OH) 1665 MHz", 1_665_402_000.0, "OH main line; star-forming-region masers."
)
OH_1667 = Band(
    "oh1667",
    "Hydroxyl (OH) 1667 MHz",
    1_667_359_000.0,
    "OH main line, usually the strongest of the four.",
)
OH_1720 = Band(
    "oh1720",
    "Hydroxyl (OH) 1720 MHz",
    1_720_530_000.0,
    "OH satellite line; supernova-remnant shock tracer.",
)

#: Methanol class II maser — a stretch target needing a real dish, listed so the tool
#: can say honestly how big an aperture it would take.
METHANOL_6668 = Band(
    "methanol",
    "Methanol maser 6.7 GHz",
    6_668_519_200.0,
    "Class II methanol masers in high-mass star formation.",
)

#: Deuterium — famously hard; included because 'how big a dish would I need?' is a
#: legitimate question this tool should answer rather than dodge.
DEUTERIUM_327 = Band(
    "deuterium",
    "Deuterium 92 cm",
    327_384_400.0,
    "The D I hyperfine line; a well-known very-hard amateur target.",
)

#: Decametric Jupiter/solar bursts — the Radio JOVE band.
JOVE_20M = Band(
    "jove",
    "Radio JOVE decametric (20.1 MHz)",
    20_100_000.0,
    "Jupiter decametric storms and solar bursts; NASA Radio JOVE's standard receive frequency.",
    bandwidth_hz=1e5,
)

#: Meteor forward-scatter: the two beacons amateurs in Europe/US actually use.
GRAVES_143 = Band(
    "graves",
    "GRAVES radar 143.05 MHz",
    143_050_000.0,
    "French space-surveillance radar used as a forward-scatter meteor beacon (Europe).",
    bandwidth_hz=1e4,
)
BRAMS_49 = Band(
    "brams",
    "BRAMS beacon 49.97 MHz",
    49_970_000.0,
    "Belgian dedicated meteor forward-scatter beacon.",
    bandwidth_hz=1e4,
)

#: Solar/continuum work at L band and Ku band (the satellite-TV-dish demo band).
L_BAND_CONTINUUM = Band(
    "lband",
    "L-band continuum (1.4 GHz)",
    1_400_000_000.0,
    "Continuum sources: Sun, Cas A, Cyg A, Tau A.",
    1e8,
)
KU_BAND_SUN = Band(
    "ku",
    "Ku-band satellite-TV (11.7–12.7 GHz)",
    12_200_000_000.0,
    "The Itty Bitty Telescope band: solar detection with a surplus offset dish and an LNB.",
    1e9,
)

#: Every band, keyed by slug.
BANDS: dict[str, Band] = {
    b.slug: b
    for b in (
        HI_21CM,
        OH_1612,
        OH_1665,
        OH_1667,
        OH_1720,
        METHANOL_6668,
        DEUTERIUM_327,
        JOVE_20M,
        GRAVES_143,
        BRAMS_49,
        L_BAND_CONTINUUM,
        KU_BAND_SUN,
    )
}


def get_band(slug: str) -> Band:
    """Look a band up by slug, with a helpful error listing the alternatives."""
    try:
        return BANDS[slug]
    except KeyError:
        raise KeyError(f"unknown band {slug!r}; known bands: {', '.join(sorted(BANDS))}") from None
