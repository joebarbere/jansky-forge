"""The parts catalogue: amplifiers, digitizers and clocks, from hobby to state of the art (N4).

M4 could say *"your system is receiver-limited"*. N0 and N1 taught the tool to read a part's
data and decide whether it will oscillate. This is the milestone that answers the question
people actually have with a shopping page open: **which of these should I buy, what did the
previous generation manage, and what is the best anyone can do?**

**Why the unbuyable entries are here.** A 3.5 K cryogenic InP HEMT is not a thing you can
order, and listing it is not aspiration — it is calibration. Knowing that the floor is a few
kelvin and the sky at 21 cm is already ~5 K tells you something a catalogue of hobby parts
cannot:
**how much of your system temperature is actually yours to fix.** For most amateur stations
the answer is "a lot", and for a few it is "almost none, stop shopping".

The historical entries do the same job pointing backwards. NRAO managed 25 K at 4.5 GHz in
1980 and 2 K at 4 GHz by 2003. A hobbyist's room-temperature 58.7 K module today is worse
than a 1980 observatory's — and that is the interesting fact, not an insult. It is also why
the amateur hydrogen line is *possible*: the sky is bright, and the bar was never 2 K.

**The line invariant 2 draws, precisely.**

A datasheet's *headline* noise figure, cited with its URL, is a published fact of the same
standing as "Cas A is 1768 Jy at epoch 2016" — the source catalogue has done exactly this
since M4. What remains forbidden is **measurement-grade design data**: Fmin, Γopt, Rn and
S-parameters are never shipped, never invented, and never inferred from a headline number.

So this module does *system budgets* and does not do *amplifier design*. There is
deliberately no path from a catalogue entry to a :class:`~jansky_forge.twoport.TwoPort`. If
you want to know whether a part is stable, you need its real S-parameters, and the tool will
keep saying so.

**Every figure here is a manufacturer or literature claim, not a measurement.** They are
labelled that way and they never share a field with anything from M7 or M8 (invariant 5).
A vendor's noise figure is measured under conditions you will not reproduce, on a board you
do not have, at a frequency that may not be yours.

Sources
-------
NRAO Central Development Lab, *Low Noise Amplifiers* — the historical progression.
Chalmers, *0.3-14 and 16-28 GHz Wide-Bandwidth Cryogenic MMIC Low-Noise Amplifiers* (2018)
<https://research.chalmers.se/en/publication/520245> — cryogenic InP HEMT state of the art.
Manufacturer datasheets, each linked from its own entry.
"""

from __future__ import annotations

import math
from collections.abc import Iterator
from dataclasses import dataclass, field
from enum import StrEnum

from jansky_forge.sensitivity import (
    Stage,
    cascade_noise_temperature_k,
    g_over_t_db,
    noise_figure_to_temperature_k,
    sefd_jy,
    system_temperature,
)
from jansky_forge.units import K_B

#: Planck's constant, J·s. Only needed here, for the quantum noise floor.
PLANCK_J_S = 6.626_070_15e-34

#: Standard reference temperature for noise figure, K. Noise figure is *defined* against it,
#: which is why a 0.3 dB part is 20.7 K and not 0.3 of anything.
REFERENCE_K = 290.0


def quantum_noise_limit_k(freq_hz: float) -> float:
    """``hf/k`` — the noise temperature no amplifier of any budget can go below.

    0.0682 K at the hydrogen line. Every entry in this catalogue is compared against it, which
    is the honest way to read the cryogenic numbers: a 3.5 K band average is superb
    engineering and still **51× the quantum limit**, so the story is not over.

    (A phase-insensitive linear amplifier is bound by this. Phase-sensitive and
    photon-counting schemes evade it by giving up something else, and none of them are
    relevant to a 21 cm total-power receiver.)
    """
    if freq_hz <= 0:
        raise ValueError("frequency must be positive")
    return PLANCK_J_S * freq_hz / K_B


class Availability(StrEnum):
    """Can you actually get one? The most important field in the catalogue.

    Comparing a hobby module against a cryogenic front end is useful *because* the tiers are
    labelled. Without this field it would be a fantasy shopping list.
    """

    #: Buy it today, hobby budget, works on a bench with no infrastructure.
    AMATEUR = "amateur"
    #: Purchasable, but institutional money and often lead times.
    PROFESSIONAL = "professional"
    #: Built in a lab or an observatory. Not a product; here to mark the ceiling.
    RESEARCH = "research"
    #: Superseded. Here for the historical comparison, not to be bought.
    HISTORICAL = "historical"


class Claim(StrEnum):
    """Where a figure came from — the reader's guide to how far to trust it."""

    #: Manufacturer datasheet for a product you can buy.
    DATASHEET = "datasheet"
    #: Peer-reviewed paper, observatory documentation, or a lab's published result.
    LITERATURE = "literature"
    #: A community measurement or well-documented amateur write-up.
    COMMUNITY = "community"


@dataclass(frozen=True)
class Amplifier:
    """A low-noise amplifier, as its source describes it.

    Noise is stored as a **temperature**, because that is what adds in a system budget and
    what the cryogenic literature quotes. Noise figure is derived, so the two can never drift
    apart — and both are printed, since datasheets speak dB and observatories speak kelvin.
    """

    slug: str
    name: str
    #: The device technology, in the words its source uses.
    technology: str
    #: Equivalent input noise temperature, K. The canonical field.
    noise_temp_k: float
    gain_db: float
    freq_min_hz: float
    freq_max_hz: float
    availability: Availability
    claim: Claim
    #: Primary source. Required — the catalogue audit fails without it.
    source_url: str
    #: The frequency the source quoted the noise figure at. ``None`` when it quotes a band.
    quoted_at_hz: float | None = None
    #: Physical temperature it must be held at. 290 K unless it needs a dewar.
    physical_temp_k: float = 290.0
    #: Year of the figure, for the historical axis.
    year: int | None = None
    caveats: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.noise_temp_k < 0:
            raise ValueError(f"{self.slug}: noise temperature cannot be negative")
        if not self.source_url:
            raise ValueError(f"{self.slug}: every entry needs a source URL")
        if self.freq_min_hz >= self.freq_max_hz:
            raise ValueError(f"{self.slug}: frequency range is inverted")

    @classmethod
    def from_noise_figure(
        cls,
        *,
        slug: str,
        name: str,
        technology: str,
        noise_figure_db: float,
        gain_db: float,
        freq_min_hz: float,
        freq_max_hz: float,
        availability: Availability,
        claim: Claim,
        source_url: str,
        quoted_at_hz: float | None = None,
        physical_temp_k: float = 290.0,
        year: int | None = None,
        caveats: tuple[str, ...] = (),
    ) -> Amplifier:
        """Build from a datasheet noise figure in dB, converting once at the boundary.

        Datasheets speak dB and the catalogue speaks kelvin; doing the conversion here means
        it happens exactly once, where the source is, instead of at every use.
        """
        return cls(
            slug=slug,
            name=name,
            technology=technology,
            noise_temp_k=noise_figure_to_temperature_k(noise_figure_db),
            gain_db=gain_db,
            freq_min_hz=freq_min_hz,
            freq_max_hz=freq_max_hz,
            availability=availability,
            claim=claim,
            source_url=source_url,
            quoted_at_hz=quoted_at_hz,
            physical_temp_k=physical_temp_k,
            year=year,
            caveats=caveats,
        )

    @property
    def noise_figure_db(self) -> float:
        """Derived, never stored — so it cannot disagree with the temperature."""
        return 10.0 * math.log10(1.0 + self.noise_temp_k / REFERENCE_K)

    @property
    def needs_cryogenics(self) -> bool:
        return self.physical_temp_k < 273.0

    def covers(self, freq_hz: float) -> bool:
        return self.freq_min_hz <= freq_hz <= self.freq_max_hz

    def times_quantum_limit(self, freq_hz: float) -> float:
        """How far above the floor this part sits. Nothing can reach 1."""
        return self.noise_temp_k / quantum_noise_limit_k(freq_hz)

    def as_stage(self) -> Stage:
        """Hand it to M4's Friis cascade.

        Note what this does *not* do: it makes no claim about matching, stability or
        S-parameters. It is a headline number in a budget, which is all a catalogue entry
        can honestly be.
        """
        return Stage(self.name, self.gain_db, self.noise_temp_k)

    def summary(self) -> str:
        band = f"{self.freq_min_hz / 1e6:.0f}-{self.freq_max_hz / 1e6:.0f} MHz"
        cryo = f", needs {self.physical_temp_k:g} K cooling" if self.needs_cryogenics else ""
        year = f" ({self.year})" if self.year else ""
        return (
            f"{self.name}{year}: {self.noise_temp_k:.1f} K "
            f"({self.noise_figure_db:.2f} dB NF), {self.gain_db:+.0f} dB gain, {band}"
            f"{cryo} [{self.availability}]"
        )


@dataclass(frozen=True)
class Digitizer:
    """An SDR or backend — the thing that turns volts into numbers.

    **Its noise figure is usually the least interesting thing about it**, and that is the
    single most useful fact in this class. Put 40 dB of LNA in front and Friis divides the
    backend's contribution by ten thousand: a 6 dB SDR and a 3 dB SDR differ by under a
    kelvin at the system level. What actually decides whether you get data is **dynamic
    range** — bit depth and how the front end behaves when a pager transmitter comes up — and
    how much instantaneous bandwidth you can afford to record.

    :func:`backend_matters_below_gain_db` puts a number on when that stops being true.
    """

    slug: str
    name: str
    bits: int
    #: Maximum usable sample rate, complex samples per second.
    max_sample_rate_hz: float
    freq_min_hz: float
    freq_max_hz: float
    availability: Availability
    claim: Claim
    source_url: str
    #: Noise figure where the source states one. Often it does not, honestly.
    noise_figure_db: float | None = None
    #: Reference clock fitted as standard, as a catalogue slug.
    clock: str | None = None
    year: int | None = None
    caveats: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.source_url:
            raise ValueError(f"{self.slug}: every entry needs a source URL")
        if self.bits <= 0:
            raise ValueError(f"{self.slug}: bit depth must be positive")

    @property
    def dynamic_range_db(self) -> float:
        """The theoretical ceiling, ``6.02·bits + 1.76`` dB.

        A ceiling and not a measurement: real converters fall short, and a front end that
        overloads before the ADC does makes the number irrelevant. It is here to compare
        parts on the axis that actually separates them.
        """
        return 6.02 * self.bits + 1.76

    def as_stage(self) -> Stage:
        if self.noise_figure_db is None:
            raise ValueError(
                f"{self.slug} has no published noise figure, so it cannot be put in a noise "
                "budget. Measure it (M8's Y-factor) or pick a part that publishes one — "
                "a plausible guess in a Tsys number is an invented Tsys number."
            )
        return Stage(self.name, 0.0, noise_figure_to_temperature_k(self.noise_figure_db))

    def summary(self) -> str:
        band = f"{self.freq_min_hz / 1e6:.0f}-{self.freq_max_hz / 1e6:.0f} MHz"
        noise = f", NF {self.noise_figure_db:.1f} dB" if self.noise_figure_db else ""
        return (
            f"{self.name}: {self.bits}-bit ({self.dynamic_range_db:.0f} dB), "
            f"{self.max_sample_rate_hz / 1e6:g} MS/s, {band}{noise} [{self.availability}]"
        )


@dataclass(frozen=True)
class Clock:
    """A frequency reference, and — the part that matters — what it lets you do.

    Stability and accuracy are different questions and amateurs are routinely sold the wrong
    one. See :func:`velocity_error_km_s` and :func:`clock_verdict`.
    """

    slug: str
    name: str
    #: Allan deviation at 1 s averaging, dimensionless.
    adev_1s: float
    #: Allan deviation at 1000 s, where the technologies re-order themselves.
    adev_1000s: float
    #: Fractional frequency *accuracy* — the systematic offset, which is a different thing.
    accuracy: float
    availability: Availability
    claim: Claim
    source_url: str
    caveats: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.source_url:
            raise ValueError(f"{self.slug}: every entry needs a source URL")

    def summary(self) -> str:
        return (
            f"{self.name}: σy(1s) = {self.adev_1s:.0e}, σy(1000s) = {self.adev_1000s:.0e}, "
            f"accuracy {self.accuracy:.0e} [{self.availability}]"
        )


# --------------------------------------------------------------------------------------
# The catalogue. Every entry carries a real URL; `audit()` fails the build otherwise.
# --------------------------------------------------------------------------------------

_AMPLIFIERS: dict[str, Amplifier] = {}
_DIGITIZERS: dict[str, Digitizer] = {}
_CLOCKS: dict[str, Clock] = {}


def _register(entry: Amplifier | Digitizer | Clock) -> None:
    # Three tables rather than one, because assigning two unrelated dataclasses to a single
    # variable is the mypy shape this project has now hit four times (cli.py twice,
    # server/app.py once, here). Branch and return instead of merging.
    if isinstance(entry, Amplifier):
        if entry.slug in _AMPLIFIERS:
            raise ValueError(f"duplicate catalogue slug {entry.slug!r}")
        _AMPLIFIERS[entry.slug] = entry
    elif isinstance(entry, Digitizer):
        if entry.slug in _DIGITIZERS:
            raise ValueError(f"duplicate catalogue slug {entry.slug!r}")
        _DIGITIZERS[entry.slug] = entry
    else:
        if entry.slug in _CLOCKS:
            raise ValueError(f"duplicate catalogue slug {entry.slug!r}")
        _CLOCKS[entry.slug] = entry


# -- Amplifiers: amateur ----------------------------------------------------------------

_register(
    Amplifier.from_noise_figure(
        slug="sawbird-h1",
        name="Nooelec SAWbird+ H1",
        technology="cascaded MMIC LNA with SAW filter",
        noise_figure_db=0.8,
        gain_db=40.0,
        freq_min_hz=1_387e6,
        freq_max_hz=1_452e6,
        quoted_at_hz=1_420e6,
        availability=Availability.AMATEUR,
        claim=Claim.DATASHEET,
        source_url="https://www.nooelec.com/store/downloads/dl/file/id/97/product/322/sawbird_h1_datasheet_revision_1.pdf",
        year=2019,
        caveats=(
            "The 65 MHz 3 dB bandwidth is the SAW filter, and it is the reason to buy this "
            "part rather than a bare LNA: it rejects the strong out-of-band signals that "
            "would otherwise compress everything downstream. It also means the module is "
            "useless for any other line.",
            "The Barebones variant is 1.05 dB, not 0.8 dB — an RF switch terminated in 50 Ω "
            "sits ahead of the first stage. That is 20 K of difference at the front of the "
            "chain, where it counts fully.",
        ),
    )
)

_register(
    Amplifier.from_noise_figure(
        slug="qpl9547",
        name="Qorvo QPL9547",
        technology="pHEMT MMIC",
        noise_figure_db=0.3,
        gain_db=19.5,
        freq_min_hz=100e6,
        freq_max_hz=6_000e6,
        quoted_at_hz=1_900e6,
        availability=Availability.AMATEUR,
        claim=Claim.DATASHEET,
        source_url="https://www.mouser.com/datasheet/2/412/QPL9547_Data_Sheet-1854301.pdf",
        year=2019,
        caveats=(
            "The 0.3 dB figure is quoted at 1.9 GHz, not at 1420 MHz. It is not interpolated "
            "here and should not be assumed identical — read the datasheet curve for your "
            "frequency.",
            "A bare MMIC is not a module. The quoted figure assumes the manufacturer's "
            "evaluation board; your layout, connectors and bias network will not match it.",
            "This is the amplifier integrated into the Discovery Dish, which is why it is in "
            "the catalogue.",
        ),
    )
)

# -- Amplifiers: research and historical, for calibration -------------------------------

_register(
    Amplifier(
        slug="cryo-inp-hemt",
        name="Cryogenic InP HEMT MMIC (0.3-14 GHz)",
        technology="InP HEMT MMIC at 4 K physical",
        noise_temp_k=3.5,
        gain_db=41.6,
        freq_min_hz=300e6,
        freq_max_hz=14_000e6,
        physical_temp_k=4.0,
        availability=Availability.RESEARCH,
        claim=Claim.LITERATURE,
        source_url="https://research.chalmers.se/en/publication/520245",
        year=2018,
        caveats=(
            "3.5 K is the **average** over 0.3-14 GHz, and that is the figure used here. The "
            "widely-quoted 2.2 K is the *minimum*, reported at 6 GHz — five times away from "
            "the hydrogen line. Quoting a band minimum as though it were the band figure is "
            "the usual way this number gets exaggerated, and this catalogue entry was itself "
            "written that way in its first draft.",
            "The source does not state a value at 1.42 GHz. This entry marks the ceiling for "
            "the technology; it is not a prediction of what this part would do at 21 cm.",
            "It needs a closed-cycle cryostat. The dewar, compressor and vacuum plumbing cost "
            "and weigh far more than the amplifier, and the thermal design is the hard part.",
            "Loss ahead of a 2 K amplifier is catastrophic in a way it is not ahead of a 60 K "
            "one: a 0.2 dB connector at 290 K adds 13.7 K, which is six times the "
            "amplifier's own noise.",
        ),
    )
)

_register(
    Amplifier(
        slug="nrao-2003-4ghz",
        name="NRAO broadband cryogenic HEMT, 4 GHz",
        technology="InP HEMT at ~15 K physical",
        noise_temp_k=2.0,
        gain_db=30.0,
        freq_min_hz=3_000e6,
        freq_max_hz=5_000e6,
        physical_temp_k=15.0,
        availability=Availability.RESEARCH,
        claim=Claim.LITERATURE,
        source_url="https://science.nrao.edu/facilities/cdl/low-noise-amplifiers",
        year=2003,
        caveats=(
            "Quoted at 4 GHz, not at 21 cm. Included as the historical marker it is: this is "
            "what an observatory achieved in 2003, and it is roughly where the technology "
            "still sits.",
            "Cryogenic: held near 15 K physical. The 2 K figure exists because of the "
            "refrigerator, not instead of one.",
        ),
    )
)

_register(
    Amplifier(
        slug="nrao-1980-4.5ghz",
        name="NRAO narrow-band cooled amplifier, 4.5 GHz",
        technology="cooled FET, 1980",
        noise_temp_k=25.0,
        gain_db=25.0,
        freq_min_hz=4_400e6,
        freq_max_hz=4_600e6,
        physical_temp_k=20.0,
        availability=Availability.HISTORICAL,
        claim=Claim.LITERATURE,
        source_url="https://science.nrao.edu/facilities/cdl/low-noise-amplifiers",
        year=1980,
        caveats=(
            "The historical anchor: a cooled observatory front end in 1980 managed 25 K. Two "
            "decades of HEMT development took that to 2 K.",
            "Cryogenic: cooled to roughly 20 K physical. Observatories were already paying "
            "for refrigeration in 1980; what changed since is the device, not the dewar.",
            "Its gain is an assumption of this catalogue, not a figure from the source — "
            "which is why it must not be used in a budget where gain matters. The noise "
            "temperature is the sourced number and the reason the entry exists.",
        ),
    )
)


# -- Digitizers --------------------------------------------------------------------------

_register(
    Digitizer(
        slug="rtl-sdr-v4",
        name="RTL-SDR Blog V4",
        bits=8,
        max_sample_rate_hz=2.4e6,
        freq_min_hz=500e3,
        freq_max_hz=1_766e6,
        availability=Availability.AMATEUR,
        claim=Claim.DATASHEET,
        source_url="https://www.rtl-sdr.com/about-rtl-sdr/",
        year=2023,
        caveats=(
            "8 bits is about 50 dB of theoretical dynamic range, and that — not noise figure "
            "— is what limits it. A strong nearby transmitter compresses the front end and "
            "your hydrogen line disappears into the intermodulation.",
            "It has no published noise figure suitable for a budget, which is honest of it: "
            "the figure depends strongly on gain setting and tuner AGC state.",
            "It reaches 1766 MHz, so the hydrogen line is comfortably inside its range. This "
            "is the part that made amateur 21 cm astronomy ordinary.",
        ),
    )
)

_register(
    Digitizer(
        slug="airspy-r2",
        name="Airspy R2",
        bits=12,
        max_sample_rate_hz=10e6,
        freq_min_hz=24e6,
        freq_max_hz=1_800e6,
        availability=Availability.AMATEUR,
        claim=Claim.DATASHEET,
        source_url="https://airspy.com/airspy-r2/",
        year=2016,
        caveats=(
            "12 bits buys about 24 dB more dynamic range than an 8-bit stick. In an RFI-heavy "
            "suburban site that is worth far more than any plausible noise-figure difference.",
            "10 MS/s is a real advantage for continuum and pulsar work, and irrelevant for a "
            "narrow spectral line.",
        ),
    )
)


# -- Clocks -------------------------------------------------------------------------------

_register(
    Clock(
        slug="tcxo",
        name="TCXO (typical SDR reference)",
        adev_1s=1e-9,
        adev_1000s=1e-9,
        accuracy=1e-6,
        availability=Availability.AMATEUR,
        claim=Claim.COMMUNITY,
        source_url="https://rfessentials.com/rf-knowledge-base/what-is-the-allan-deviation-and-how-does-it-relate-to-phase-noise-and-frequency-/",
        caveats=(
            "Its accuracy (~1 ppm) is far worse than its stability, and accuracy is what "
            "sets a spectral line's apparent velocity. 1 ppm at 1420 MHz is 1.4 kHz, about "
            "0.3 km/s — real, and small next to a 20 km/s HI linewidth.",
        ),
    )
)

_register(
    Clock(
        slug="ocxo",
        name="OCXO",
        adev_1s=1e-12,
        adev_1000s=1e-11,
        accuracy=1e-8,
        availability=Availability.AMATEUR,
        claim=Claim.COMMUNITY,
        source_url="https://rfessentials.com/rf-knowledge-base/what-is-the-allan-deviation-and-how-does-it-relate-to-phase-noise-and-frequency-/",
        caveats=(
            "Better short-term stability than a rubidium standard, and worse long-term. That "
            "inversion surprises people who assume 'atomic' means better everywhere.",
        ),
    )
)

_register(
    Clock(
        slug="gpsdo",
        name="GPS-disciplined oscillator",
        adev_1s=1e-12,
        adev_1000s=1e-12,
        accuracy=1e-12,
        availability=Availability.AMATEUR,
        claim=Claim.COMMUNITY,
        source_url="https://dantalion.nl/2024/02/09/gps-disciplined-oscillator.html",
        caveats=(
            "Short-term stability is its OCXO's, not GPS's — the discipline loop is slow on "
            "purpose. What GPS buys is long-term accuracy and the absence of drift.",
            "It needs sky view. A GPSDO in a basement is an undisciplined OCXO with a warning "
            "light.",
        ),
    )
)

_register(
    Clock(
        slug="rubidium",
        name="Rubidium frequency standard",
        adev_1s=1e-11,
        adev_1000s=1e-12,
        accuracy=1e-11,
        availability=Availability.AMATEUR,
        claim=Claim.COMMUNITY,
        source_url="http://www.ke5fx.com/rb.htm",
        caveats=(
            "Surplus telecom rubidiums are cheap and genuinely good, which is why they are "
            "common in amateur shacks. Check the lamp hours.",
        ),
    )
)

_register(
    Clock(
        slug="h-maser",
        name="Hydrogen maser",
        adev_1s=1e-13,
        adev_1000s=1e-15,
        accuracy=1e-13,
        availability=Availability.PROFESSIONAL,
        claim=Claim.COMMUNITY,
        source_url="https://www.xtaltq.com/ocxo-vs-rubidium-oscillator-vs-gps-disciplined-oscillator-vs-hydrogen-maser-complete-comparison-guide.html",
        caveats=(
            "The VLBI standard, and the reason VLBI is expensive. Each station needs one, "
            "because coherence across a baseline is limited by the worse of the two.",
        ),
    )
)


# --------------------------------------------------------------------------------------
# Lookup
# --------------------------------------------------------------------------------------


def amplifiers(
    *, availability: Availability | str | None = None, covering_hz: float | None = None
) -> list[Amplifier]:
    """Catalogue amplifiers, newest-quietest first, optionally filtered."""
    found = list(_AMPLIFIERS.values())
    if availability is not None:
        found = [a for a in found if a.availability == availability]
    if covering_hz is not None:
        found = [a for a in found if a.covers(covering_hz)]
    return sorted(found, key=lambda a: a.noise_temp_k)


def digitizers() -> list[Digitizer]:
    return sorted(_DIGITIZERS.values(), key=lambda d: -d.bits)


def clocks() -> list[Clock]:
    """Best short-term stability first, matching the amplifier listing's best-first order."""
    return sorted(_CLOCKS.values(), key=lambda c: c.adev_1s)


def get_amplifier(slug: str) -> Amplifier:
    if slug not in _AMPLIFIERS:
        raise KeyError(f"unknown amplifier {slug!r}; known: {', '.join(sorted(_AMPLIFIERS))}")
    return _AMPLIFIERS[slug]


def get_digitizer(slug: str) -> Digitizer:
    if slug not in _DIGITIZERS:
        raise KeyError(f"unknown digitizer {slug!r}; known: {', '.join(sorted(_DIGITIZERS))}")
    return _DIGITIZERS[slug]


def get_clock(slug: str) -> Clock:
    if slug not in _CLOCKS:
        raise KeyError(f"unknown clock {slug!r}; known: {', '.join(sorted(_CLOCKS))}")
    return _CLOCKS[slug]


def audit() -> Iterator[str]:
    """Yield a complaint for every entry that fails the provenance rules.

    Mechanical enforcement, same as the antenna catalogue's. ``make audit`` must print
    nothing.
    """
    entries: list[Amplifier | Digitizer | Clock] = [
        *_AMPLIFIERS.values(),
        *_DIGITIZERS.values(),
        *_CLOCKS.values(),
    ]
    for entry in entries:
        if not entry.source_url.startswith("http"):
            yield f"{entry.slug}: source_url is not a URL"
        if entry.claim is Claim.COMMUNITY and not entry.caveats:
            yield f"{entry.slug}: a community-sourced figure must carry caveats"
        if isinstance(entry, Amplifier):
            cooling_words = ("cryogenic", "cryostat", "dewar", "refrigerat", "cooled")
            if entry.needs_cryogenics and not any(
                word in caveat.lower() for caveat in entry.caveats for word in cooling_words
            ):
                yield (
                    f"{entry.slug}: a part needing {entry.physical_temp_k:g} K must carry a "
                    "caveat saying so — the cooling is the hard part, not the amplifier"
                )
            if entry.availability is Availability.AMATEUR and entry.quoted_at_hz is None:
                yield f"{entry.slug}: an amateur part should say what frequency its figure is for"


# --------------------------------------------------------------------------------------
# Comparison — the point of the milestone
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Candidate:
    """One amplifier evaluated against one antenna. Never a number on its own."""

    amplifier: Amplifier
    receiver_k: float
    tsys_k: float
    sefd_jy: float
    g_over_t_db: float
    #: What this choice costs relative to the best candidate, in kelvin of Tsys.
    penalty_k: float
    notes: tuple[str, ...] = field(default_factory=tuple)

    def summary(self) -> str:
        penalty = "best" if self.penalty_k <= 0.05 else f"+{self.penalty_k:.1f} K"
        return (
            f"{self.amplifier.name:44s} Tsys {self.tsys_k:6.1f} K   "
            f"SEFD {self.sefd_jy:9,.0f} Jy   G/T {self.g_over_t_db:+6.2f} dB/K   {penalty}"
        )


def compare_amplifiers(
    candidates: list[Amplifier],
    *,
    freq_hz: float,
    gain_dbi: float,
    effective_area_m2: float,
    spillover_efficiency: float = 1.0,
    pre_lna_loss_db: float = 0.0,
    backend_noise_figure_db: float = 6.0,
    backend_gain_db: float = 20.0,
) -> list[Candidate]:
    """Rank amplifiers **against a specific antenna**, because that is the only honest way.

    A noise figure alone answers nothing. The same 0.5 dB difference between two parts is
    decisive on a cold, well-fed dish and invisible on one with 60 K of spillover — so the
    comparison takes the antenna's numbers and returns system temperatures.

    ``pre_lna_loss_db`` is the most important argument here and the one people leave at zero.
    Loss ahead of the amplifier adds its full noise temperature to the front of the chain,
    and 0.5 dB of it can wipe out the entire difference between the parts you are comparing.
    """
    if not candidates:
        raise ValueError("nothing to compare")

    results: list[Candidate] = []
    for amplifier in candidates:
        stages = []
        if pre_lna_loss_db:
            stages.append(Stage.loss("pre-LNA loss", loss_db=pre_lna_loss_db))
        stages.append(amplifier.as_stage())
        stages.append(
            Stage.amplifier(
                "backend", gain_db=backend_gain_db, noise_figure_db=backend_noise_figure_db
            )
        )
        receiver_k = cascade_noise_temperature_k(stages)
        tsys = system_temperature(
            freq_hz=freq_hz, receiver_k=receiver_k, spillover_efficiency=spillover_efficiency
        )
        notes: list[str] = []
        if not amplifier.covers(freq_hz):
            notes.append(
                f"{amplifier.name} is not specified at {freq_hz / 1e6:.0f} MHz "
                f"({amplifier.freq_min_hz / 1e6:.0f}-{amplifier.freq_max_hz / 1e6:.0f} MHz). "
                "This row is an extrapolation and should not be trusted."
            )
        if amplifier.quoted_at_hz and abs(amplifier.quoted_at_hz - freq_hz) > 0.1 * freq_hz:
            notes.append(
                f"its figure is quoted at {amplifier.quoted_at_hz / 1e6:.0f} MHz, not "
                f"{freq_hz / 1e6:.0f} MHz; noise figure varies across a band and this is not "
                "interpolated."
            )
        if amplifier.needs_cryogenics:
            notes.append(
                f"requires {amplifier.physical_temp_k:g} K cooling — the dewar is the project, "
                "not the amplifier."
            )
        results.append(
            Candidate(
                amplifier=amplifier,
                receiver_k=receiver_k,
                tsys_k=tsys.total_k,
                sefd_jy=sefd_jy(tsys.total_k, effective_area_m2),
                g_over_t_db=g_over_t_db(gain_dbi, tsys.total_k),
                penalty_k=0.0,
                notes=tuple(notes),
            )
        )

    best = min(result.tsys_k for result in results)
    ranked = [
        Candidate(
            amplifier=r.amplifier,
            receiver_k=r.receiver_k,
            tsys_k=r.tsys_k,
            sefd_jy=r.sefd_jy,
            g_over_t_db=r.g_over_t_db,
            penalty_k=r.tsys_k - best,
            notes=r.notes,
        )
        for r in results
    ]
    return sorted(ranked, key=lambda r: r.tsys_k)


@dataclass(frozen=True)
class UpgradeAdvice:
    """What is actually worth fixing, with the arithmetic that says so."""

    tsys_now_k: float
    #: Tsys with a hypothetical noiseless receiver. The ceiling on any amplifier upgrade.
    tsys_perfect_receiver_k: float
    #: Tsys with perfect spillover, everything else unchanged.
    tsys_perfect_spillover_k: float
    #: Tsys with the pre-LNA loss removed.
    tsys_no_pre_loss_k: float
    #: Tsys with the best amplifier you can actually buy at this tier. The actionable number.
    tsys_best_available_k: float
    #: Which part that is, or ``None`` if nothing in the catalogue beats what you have.
    best_available: Amplifier | None
    verdict: str
    notes: tuple[str, ...]

    @property
    def best_possible_lna_gain_k(self) -> float:
        """The most a better amplifier could ever buy — even a free, perfect, 0 K one."""
        return self.tsys_now_k - self.tsys_perfect_receiver_k

    @property
    def achievable_lna_gain_k(self) -> float:
        """What a part you can actually order would buy. Usually much less."""
        return self.tsys_now_k - self.tsys_best_available_k

    def summary(self) -> str:
        available = (
            f"The best amplifier you can actually buy ({self.best_available.name}) would give "
            f"{self.tsys_best_available_k:.1f} K — {self.achievable_lna_gain_k:.1f} K."
            if self.best_available
            else "Nothing purchasable in the catalogue improves on what you have."
        )
        return (
            f"Tsys {self.tsys_now_k:.1f} K. Deleting the receiver entirely would give "
            f"{self.tsys_perfect_receiver_k:.1f} K, so {self.best_possible_lna_gain_k:.1f} K is "
            f"the ceiling on any amplifier upgrade — impossible, not a target. {available} "
            f"{self.verdict}"
        )


def would_a_better_lna_help(
    *,
    freq_hz: float,
    amplifier: Amplifier,
    spillover_efficiency: float = 1.0,
    pre_lna_loss_db: float = 0.0,
    backend_noise_figure_db: float = 6.0,
    backend_gain_db: float = 20.0,
) -> UpgradeAdvice:
    """The question the whole receiver track exists to answer.

    Rather than ranking parts, this prices the *ceiling*: it replaces the receiver with a
    physically impossible 0 K one and reports what that would buy. If the answer is 4 K on a
    70 K system, no amplifier on earth — cryogenic, unbuyable, priced like a car — will fix
    your telescope, and the honest advice is to stop reading datasheets and go look at the
    feed.

    It prices the same way for spillover and for the loss ahead of the amplifier, so the
    three candidate upgrades are compared on one scale instead of argued about.

    **Those three are all ceilings**, and ceilings are comparable to each other but not to a
    real decision. So it also prices the best amplifier you could actually order at your tier,
    which is usually a much smaller number and the only one you can act on.
    """

    def tsys(receiver_k: float, efficiency: float) -> float:
        return system_temperature(
            freq_hz=freq_hz, receiver_k=receiver_k, spillover_efficiency=efficiency
        ).total_k

    def receiver(loss_db: float, amp_noise_k: float) -> float:
        stages = []
        if loss_db:
            stages.append(Stage.loss("pre-LNA loss", loss_db=loss_db))
        stages.append(Stage(amplifier.name, amplifier.gain_db, amp_noise_k))
        stages.append(
            Stage.amplifier(
                "backend", gain_db=backend_gain_db, noise_figure_db=backend_noise_figure_db
            )
        )
        return cascade_noise_temperature_k(stages)

    now = tsys(receiver(pre_lna_loss_db, amplifier.noise_temp_k), spillover_efficiency)

    # The ceilings below are all physically unreachable, which makes them comparable to each
    # other but NOT to a real decision. So price the real decision too: the best part you
    # could actually order, at the tier you are already shopping in. Otherwise the advice
    # ranks "buy a perfect amplifier" above "replace 0.5 dB of cable", and only one of those
    # is a Saturday afternoon.
    purchasable = [
        candidate
        for candidate in amplifiers(availability=amplifier.availability, covering_hz=freq_hz)
        if candidate.noise_temp_k < amplifier.noise_temp_k
    ]
    best_available = purchasable[0] if purchasable else None
    best_available_tsys = (
        tsys(receiver(pre_lna_loss_db, best_available.noise_temp_k), spillover_efficiency)
        if best_available
        else now
    )
    # A 0 K amplifier still has the pre-LNA loss and the backend behind it, which is the
    # point: those are not fixed by buying a better amplifier.
    perfect_rx = tsys(receiver(pre_lna_loss_db, 0.0), spillover_efficiency)
    perfect_spill = tsys(receiver(pre_lna_loss_db, amplifier.noise_temp_k), 1.0)
    no_loss = tsys(receiver(0.0, amplifier.noise_temp_k), spillover_efficiency)

    ceiling = now - perfect_rx
    # Rank what you can DO. A 0 K amplifier is a ceiling, not an option, and putting it in the
    # same list as "use better cable" would make the impossible win every time.
    actions = {
        "removing the loss ahead of it": now - no_loss,
        "fixing spillover": now - perfect_spill,
    }
    if best_available:
        actions[f"buying a {best_available.name}"] = now - best_available_tsys
    best_action = max(actions, key=lambda key: actions[key])
    notes: list[str] = []

    if ceiling < 0.1 * now:
        verdict = (
            f"Your receiver is not the problem — even deleting it entirely saves only "
            f"{ceiling:.1f} K, under 10% of Tsys. Stop reading amplifier datasheets. The "
            f"biggest win here is {best_action} ({actions[best_action]:.1f} K)."
        )
    elif actions[best_action] < 0.5:
        verdict = "Nothing on this list is worth more than half a kelvin. You are done."
    else:
        verdict = (
            f"The biggest thing you can actually do is {best_action}, worth "
            f"{actions[best_action]:.1f} K."
        )
        runner_up = sorted(actions.items(), key=lambda item: -item[1])[1:2]
        if runner_up and runner_up[0][1] > 0.5:
            verdict += f" Then {runner_up[0][0]} ({runner_up[0][1]:.1f} K)."

    if best_available and actions["removing the loss ahead of it"] > actions.get(
        f"buying a {best_available.name}", 0.0
    ):
        notes.append(
            "Note the ordering: the amplifier ceiling above is a 0 K part that does not "
            "exist, while removing the loss is something you can do this afternoon with "
            "better cable and a shorter run. Compare achievable against achievable."
        )
    if pre_lna_loss_db:
        notes.append(
            f"{pre_lna_loss_db:g} dB ahead of the amplifier is worth "
            f"{actions['removing the loss ahead of it']:.1f} K. Loss in front of the LNA is "
            "counted at full weight; the same loss behind it is nearly free."
        )
    floor = quantum_noise_limit_k(freq_hz)
    notes.append(
        f"The quantum limit at this frequency is {floor:.4f} K, and this part is "
        f"{amplifier.times_quantum_limit(freq_hz):.0f}x it. Even the best cryogenic amplifiers "
        f"are ~30x, so 'better amplifiers exist' is always true and rarely the answer."
    )
    return UpgradeAdvice(
        tsys_now_k=now,
        tsys_perfect_receiver_k=perfect_rx,
        tsys_perfect_spillover_k=perfect_spill,
        tsys_no_pre_loss_k=no_loss,
        tsys_best_available_k=best_available_tsys,
        best_available=best_available,
        verdict=verdict,
        notes=tuple(notes),
    )


# --------------------------------------------------------------------------------------
# Backends and clocks: two questions people get sold the wrong answer to
# --------------------------------------------------------------------------------------


def backend_matters_below_gain_db(
    backend_noise_figure_db: float, amplifier_noise_temp_k: float, tolerance_k: float = 1.0
) -> float:
    """How little front-end gain it takes before the backend's noise figure stops mattering.

    Friis divides the backend's contribution by everything ahead of it, so the answer is
    usually "about 20 dB" — which is why arguing about SDR noise figures behind a 40 dB LNA
    is arguing about a fraction of a kelvin.

    Returns the gain in dB at which the backend contributes ``tolerance_k`` to the system.
    """
    backend_k = noise_figure_to_temperature_k(backend_noise_figure_db)
    if backend_k <= tolerance_k:
        return -math.inf  # it never mattered
    _ = amplifier_noise_temp_k  # not needed for the threshold, kept for call-site clarity
    return 10.0 * math.log10(backend_k / tolerance_k)


def velocity_error_km_s(fractional_error: float) -> float:
    """A fractional frequency error, as the radial velocity error it looks like.

    The conversion that makes a clock specification mean something: a spectral line's velocity
    *is* a frequency ratio, so a clock error is indistinguishable from the source moving.
    """
    return fractional_error * 299_792.458


def clock_verdict(clock: Clock, *, freq_hz: float, integration_s: float = 600.0) -> tuple[str, ...]:
    """What this clock is and is not good enough for.

    **Accuracy and stability answer different questions, and amateurs are routinely sold the
    wrong one.** For a spectral line, what matters is *accuracy* — a systematic frequency
    offset moves your line and looks exactly like radial velocity. For pulsar timing and VLBI
    what matters is *stability* over the coherence time; an offset you can calibrate away.

    The arithmetic is unkind to the usual advice: a 1 ppm TCXO puts a 21 cm line 0.3 km/s
    wrong, against HI linewidths of tens of km/s. **For hydrogen-line spectroscopy the clock
    is almost never the limiting factor** — and a GPSDO bought to fix a spectroscopy problem
    is a GPSDO bought to fix the wrong problem.
    """
    accuracy_kms = velocity_error_km_s(clock.accuracy)
    drift = clock.adev_1000s if integration_s > 100 else clock.adev_1s
    notes = [
        f"frequency accuracy {clock.accuracy:.0e} puts a line at {freq_hz / 1e6:.0f} MHz "
        f"{velocity_error_km_s(clock.accuracy) * 1000:.1f} m/s wrong "
        f"({clock.accuracy * freq_hz:.1f} Hz)",
    ]
    if accuracy_kms < 1.0:
        notes.append(
            "Comfortably enough for HI spectroscopy: galactic linewidths are tens of km/s, so "
            "this contributes nothing you could measure."
        )
    else:
        notes.append(
            f"{accuracy_kms:.1f} km/s of systematic velocity error is significant for a "
            "spectral line. Calibrate against a known source, or improve the reference."
        )
    coherent = drift * freq_hz * integration_s
    notes.append(
        f"over {integration_s:g} s the reference drifts about {coherent:.2g} cycles at this "
        f"frequency — {'fine' if coherent < 1 else 'too much'} for *coherent* integration "
        "(VLBI, pulsar folding). Total-power spectroscopy adds powers, not phases, so it does "
        "not care: this line and the one above answer different questions, and only one of "
        "them is yours."
    )
    if clock.availability is not Availability.AMATEUR:
        notes.append(f"{clock.name} is {clock.availability}, not something to buy for a rooftop.")
    return tuple(notes)
