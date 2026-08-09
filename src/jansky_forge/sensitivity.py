"""Telescope figures of merit: will this antenna actually see anything? (M4)

Everything before this milestone described an *antenna*. This module turns those numbers
into *telescope* numbers — the ones that answer the only question that really matters, which
is whether you will see the thing and how long you must stare at it.

**The central point, and the one most often got wrong.** Gain is not sensitivity. A bigger
dish collects more from a *point* source, so its antenna temperature rises with collecting
area. But galactic HI fills the beam completely, and for a source that fills the beam the
antenna temperature equals the source brightness temperature **regardless of aperture**. A
0.9 m horn and a 30 m dish see the same ~100 K of hydrogen along the galactic plane. The big
dish buys angular resolution and point-source sensitivity; it does not buy a stronger line.
:func:`antenna_temperature_extended` says so, and the "will I see it" helpers route to the
right formula rather than letting the wrong one flatter a design.

**Where the terms come from.** System temperature is a budget, and this module builds it
from parts you can act on: the sky you are pointed at, the ground your feed spills onto (the
M3 spillover efficiency lands here directly — the power that misses the dish sees ~290 K of
warm earth), losses ahead of the first amplifier, and the receiver itself through the Friis
cascade. Naming the terms is the point: it tells you which one to fix.

**Verification.** :func:`sensitivity_k_per_jy` reproduces the BHARAT paper's published
1.47e-4 K/Jy from its published effective area, to 0.3%.

References
----------
Kraus, *Radio Astronomy*, 2nd ed. — antenna temperature, SEFD, the radiometer equation.
Friis (1944) — the cascade noise formula.
The radiometer equation is also implemented in the sibling ``jansky`` course
(:func:`jansky.signals.radiometer_sensitivity`); the test suite cross-checks the two agree
rather than letting a second implementation drift.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from jansky_forge.units import JANSKY_W_M2_HZ, K_B, to_db

#: Cosmic microwave background temperature (K).
T_CMB_K = 2.725

#: Physical temperature of the ground a spilling feed sees (K). The earth is not at
#: absolute zero and this is the single most under-appreciated term in an amateur budget.
T_GROUND_K = 290.0

#: Reference for the galactic synchrotron scaling: the all-sky minimum brightness at
#: 408 MHz (Haslam survey), in kelvin, and the spectral index it scales with.
T_GALACTIC_408_MIN_K = 20.0
GALACTIC_SPECTRAL_INDEX = -2.7

#: Zenith atmospheric contribution at L band (K), dominated by well-mixed oxygen.
#: 2.0 K per Peng et al. (2013)'s radiosonde-validated model for 1400-1427 MHz, as quoted by
#: the L-BASS survey (Zerafa et al. 2025). Amateurs routinely forget this term, and it is
#: comparable to the entire galactic contribution.
T_ATMOSPHERE_ZENITH_K = 2.0

#: MEASURED cold-sky brightness at 1.4 GHz (K), including CMB, galactic and extragalactic
#: emission but not the atmosphere: 3.58 K at the South Celestial Pole, from three
#: independent RA strips (Testori et al. 2001, A&A 376, 861), cross-checked against absolute
#: sky-horn measurements. This is a measurement, and it beats the model below — see
#: :func:`sky_temperature_k` for what the model gives and why the difference is tolerable.
COLD_SKY_MEASURED_1420_K = 3.58

#: Effective area corresponding to a sensitivity of exactly 1 K/Jy: 2*k/1e-26 = 2761 m^2.
#: Condon & Ransom, *Essential Radio Astronomy*, eq. 3.49. A useful sanity check on any
#: sensitivity figure — if a 3 m dish claims 1 K/Jy, something is wrong by two orders.
AREA_FOR_ONE_K_PER_JY_M2 = 2761.0


# --------------------------------------------------------------------------------------
# Sky
# --------------------------------------------------------------------------------------


def galactic_sky_temperature_k(
    freq_hz: float, *, brightness_408_k: float = T_GALACTIC_408_MIN_K
) -> float:
    """Galactic synchrotron brightness, scaled from 408 MHz as ``T ~ nu^-2.7``.

    ``brightness_408_k`` defaults to the all-sky *minimum* (~20 K), i.e. a cold patch well
    away from the galactic plane. Toward the plane the 408 MHz brightness is hundreds of
    kelvin, so pass a larger value — this function scales whatever you give it and does not
    know where you are pointing.
    """
    if freq_hz <= 0 or brightness_408_k < 0:
        raise ValueError("frequency must be positive and brightness non-negative")
    return brightness_408_k * (freq_hz / 408e6) ** GALACTIC_SPECTRAL_INDEX


def sky_temperature_k(
    freq_hz: float,
    *,
    brightness_408_k: float = T_GALACTIC_408_MIN_K,
    include_atmosphere: bool = True,
) -> float:
    """Total sky brightness: CMB + galactic synchrotron + (optionally) atmosphere.

    At 1.4 GHz away from the plane the model gives about 3.4 K against a *measured*
    3.58 K (:data:`COLD_SKY_MEASURED_1420_K`). The 0.2 K shortfall is real and is left in
    place rather than tuned away: it sits inside the zero-level uncertainty the 408 MHz
    surveys themselves quote (0.1-0.5 K), and part of it is the unresolved extragalactic
    background that a single galactic power law does not represent. Where a measurement
    exists, prefer the measurement.

    This is an estimate of a *model* sky. It does not know where you are pointing — toward
    the galactic plane the 408 MHz brightness is hundreds of kelvin, so pass a larger
    ``brightness_408_k`` — and it knows nothing at all about your RFI.
    """
    total = T_CMB_K + galactic_sky_temperature_k(freq_hz, brightness_408_k=brightness_408_k)
    if include_atmosphere:
        total += T_ATMOSPHERE_ZENITH_K
    return total


# --------------------------------------------------------------------------------------
# Receiver chain
# --------------------------------------------------------------------------------------


def noise_figure_to_temperature_k(noise_figure_db: float, *, reference_k: float = 290.0) -> float:
    """Noise figure (dB) to equivalent noise temperature: T = T0 (10^(NF/10) - 1).

    A 0.3 dB LNA is about 21 K; a 3 dB one is 289 K. That range is the difference between a
    telescope and a disappointment, which is why the first amplifier dominates everything.
    """
    if noise_figure_db < 0:
        raise ValueError(f"noise figure cannot be negative, got {noise_figure_db}")
    return reference_k * (10.0 ** (noise_figure_db / 10.0) - 1.0)


def loss_to_temperature_k(loss_db: float, *, physical_k: float = 290.0) -> float:
    """Noise a lossy component adds, referred to its input: T = (L - 1) * T_physical.

    Cable and connector loss *before* the LNA is charged at nearly the full rate, which is
    why every dB of coax between the feed and the first amplifier is expensive and why a
    mast-head LNA is worth the trouble.
    """
    if loss_db < 0:
        raise ValueError(f"loss cannot be negative, got {loss_db}")
    return (10.0 ** (loss_db / 10.0) - 1.0) * physical_k


@dataclass(frozen=True)
class Stage:
    """One element of the receive chain, in signal order from the feed."""

    name: str
    #: Power gain in dB. Negative for a lossy element (cable, connector, filter).
    gain_db: float
    #: Equivalent input noise temperature (K). For a passive loss use
    #: :func:`loss_to_temperature_k`; for an amplifier, :func:`noise_figure_to_temperature_k`.
    noise_temp_k: float

    @classmethod
    def amplifier(cls, name: str, *, gain_db: float, noise_figure_db: float) -> Stage:
        return cls(name, gain_db, noise_figure_to_temperature_k(noise_figure_db))

    @classmethod
    def loss(cls, name: str, *, loss_db: float, physical_k: float = 290.0) -> Stage:
        return cls(name, -abs(loss_db), loss_to_temperature_k(abs(loss_db), physical_k=physical_k))


def cascade_noise_temperature_k(stages: list[Stage]) -> float:
    """Friis cascade: T = T1 + T2/G1 + T3/(G1 G2) + ...

    Referred to the input of the first stage. The formula is why order matters so much: a
    lossy cable ahead of the LNA contributes at full weight, while the same cable after
    30 dB of gain contributes a thousandth as much.
    """
    if not stages:
        raise ValueError("a receive chain needs at least one stage")
    total = 0.0
    gain = 1.0
    for stage in stages:
        total += stage.noise_temp_k / gain
        gain *= 10.0 ** (stage.gain_db / 10.0)
    return total


# --------------------------------------------------------------------------------------
# System temperature
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class SystemTemperature:
    """A system temperature with its terms kept separate, because that is the actionable part."""

    total_k: float
    sky_k: float
    spillover_k: float
    receiver_k: float
    other_k: float = 0.0
    notes: tuple[str, ...] = ()

    @property
    def dominant_term(self) -> str:
        terms = {
            "sky": self.sky_k,
            "spillover (ground)": self.spillover_k,
            "receiver": self.receiver_k,
            "other": self.other_k,
        }
        return max(terms, key=lambda k: terms[k])

    def summary(self) -> str:
        return (
            f"Tsys {self.total_k:.1f} K = sky {self.sky_k:.1f} + spillover "
            f"{self.spillover_k:.1f} + receiver {self.receiver_k:.1f}"
            + (f" + other {self.other_k:.1f}" if self.other_k else "")
            + f"; dominated by {self.dominant_term}"
        )


def system_temperature(
    *,
    freq_hz: float,
    receiver_k: float,
    spillover_efficiency: float = 1.0,
    brightness_408_k: float = T_GALACTIC_408_MIN_K,
    ground_k: float = T_GROUND_K,
    other_k: float = 0.0,
    include_atmosphere: bool = True,
) -> SystemTemperature:
    """Build a system temperature from its parts.

    ``spillover_efficiency`` comes straight from M3
    (:func:`jansky_forge.feeds.spillover_efficiency`): the fraction of feed power that lands
    on the dish. What misses looks at the ground, so it contributes
    ``(1 - eta_spill) * T_ground`` — which is how a feed-choice decision made in M3 turns
    into kelvins of system temperature here.
    """
    if not 0.0 < spillover_efficiency <= 1.0:
        raise ValueError(f"spillover efficiency must be in (0, 1], got {spillover_efficiency}")
    if receiver_k < 0 or other_k < 0:
        raise ValueError("noise temperatures cannot be negative")

    sky = sky_temperature_k(
        freq_hz, brightness_408_k=brightness_408_k, include_atmosphere=include_atmosphere
    )
    spill = (1.0 - spillover_efficiency) * ground_k
    total = sky + spill + receiver_k + other_k

    notes = []
    if spill > receiver_k:
        notes.append(
            f"Spillover contributes {spill:.0f} K — more than the receiver's "
            f"{receiver_k:.0f} K. A better-matched feed is worth more here than a better "
            "LNA, and it is usually cheaper."
        )
    if spillover_efficiency < 0.85:
        notes.append(
            f"Only {spillover_efficiency * 100:.0f}% of feed power lands on the dish; the "
            "rest sees warm ground. Check the feed pattern against the rim angle (M3)."
        )
    notes.append(
        "This is an estimate from a model sky and a nominal ground temperature, not a "
        "measurement. A Y-factor measurement on the real system supersedes it (M8)."
    )
    return SystemTemperature(
        total_k=total,
        sky_k=sky,
        spillover_k=spill,
        receiver_k=receiver_k,
        other_k=other_k,
        notes=tuple(notes),
    )


# --------------------------------------------------------------------------------------
# Figures of merit
# --------------------------------------------------------------------------------------


def sensitivity_k_per_jy(effective_area_m2: float) -> float:
    """Antenna temperature per unit point-source flux: A_e / 2k, in K/Jy.

    Also called DPFU (degrees per flux unit) in the VLBI literature — the same quantity,
    despite the name, measured in kelvin per jansky.

    **The factor of two is a polarization factor, and it is conditional.** A single antenna
    responds to one polarization, so it collects all of a fully-polarized matched source's
    power but only half of an *unpolarized* source's (Condon & Ransom, *Essential Radio
    Astronomy* §3.1.6). Nearly every astronomical continuum source is effectively
    unpolarized, so the 2 belongs — but it is the most common factor-of-two error in the
    amateur literature, and it would not belong for a matched polarized transmitter.

    Verified two ways: against the BHARAT 21 cm horn, which publishes both A_e = 0.407 m^2
    and 1.47e-4 K/Jy (this returns 1.474e-4); and against the identity that 1 K/Jy
    corresponds to 2761 m^2 of collecting area.
    """
    if effective_area_m2 <= 0:
        raise ValueError("effective area must be positive")
    return effective_area_m2 / (2.0 * K_B) * JANSKY_W_M2_HZ


def antenna_temperature_point_k(flux_jy: float, effective_area_m2: float) -> float:
    """Antenna temperature from an unresolved source of the given flux density."""
    if flux_jy < 0:
        raise ValueError("flux cannot be negative")
    return flux_jy * sensitivity_k_per_jy(effective_area_m2)


def antenna_temperature_extended_k(
    brightness_temp_k: float,
    *,
    source_solid_angle_sr: float | None = None,
    beam_solid_angle_sr: float | None = None,
) -> float:
    """Antenna temperature from an extended source.

    If the source fills the beam — galactic HI does, comprehensively — the antenna
    temperature simply *is* the brightness temperature, with **no dependence on aperture at
    all**. This is the single most important asymmetry in the module: collecting area buys
    point-source sensitivity and angular resolution, and buys nothing for a source that
    already fills your beam.

    Give both solid angles for a source smaller than the beam, and the result is diluted by
    the filling factor.
    """
    if brightness_temp_k < 0:
        raise ValueError("brightness temperature cannot be negative")
    if source_solid_angle_sr is None or beam_solid_angle_sr is None:
        return brightness_temp_k
    if source_solid_angle_sr <= 0 or beam_solid_angle_sr <= 0:
        raise ValueError("solid angles must be positive")
    return brightness_temp_k * min(1.0, source_solid_angle_sr / beam_solid_angle_sr)


def sefd_jy(tsys_k: float, effective_area_m2: float) -> float:
    """System equivalent flux density: SEFD = 2k*Tsys/A_e, in janskys.

    The flux of a source that would double the system power — one number combining how much
    you collect and how quietly you listen, and the fairest way to compare two telescopes.
    """
    if tsys_k <= 0:
        raise ValueError("system temperature must be positive")
    return tsys_k / sensitivity_k_per_jy(effective_area_m2)


def g_over_t_db(gain_dbi: float, tsys_k: float) -> float:
    """G/T in dB/K — gain minus system temperature in dB. The satellite world's SEFD."""
    if tsys_k <= 0:
        raise ValueError("system temperature must be positive")
    return gain_dbi - to_db(tsys_k)


# --------------------------------------------------------------------------------------
# The radiometer equation
# --------------------------------------------------------------------------------------


def radiometer_sensitivity_k(
    tsys_k: float,
    bandwidth_hz: float,
    integration_s: float,
    *,
    n_pol: int = 1,
    switched: bool = False,
) -> float:
    """RMS temperature noise: dT = Tsys / sqrt(n_pol * B * tau).

    ``switched=True`` applies the factor 2 for a Dicke/position-switched measurement, which
    halves your on-source time and differences two noisy samples. You pay that factor for
    immunity to gain drift, and on a real amateur system that trade is usually worth it —
    but the cost should be visible rather than hidden.

    Sensitivity improves only as the square root of time: a detection twice as good costs
    four times the integration. That is why "just integrate longer" stops being an answer.
    """
    if tsys_k <= 0 or bandwidth_hz <= 0 or integration_s <= 0:
        raise ValueError("Tsys, bandwidth, and integration time must all be positive")
    if n_pol < 1:
        raise ValueError("n_pol must be at least 1")
    noise = tsys_k / math.sqrt(n_pol * bandwidth_hz * integration_s)
    return 2.0 * noise if switched else noise


def snr(
    signal_k: float,
    tsys_k: float,
    bandwidth_hz: float,
    integration_s: float,
    *,
    n_pol: int = 1,
    switched: bool = False,
) -> float:
    """Signal-to-noise ratio of a signal of ``signal_k`` antenna temperature."""
    return signal_k / radiometer_sensitivity_k(
        tsys_k, bandwidth_hz, integration_s, n_pol=n_pol, switched=switched
    )


def time_to_detect_s(
    *,
    signal_k: float,
    tsys_k: float,
    bandwidth_hz: float,
    target_snr: float = 5.0,
    n_pol: int = 1,
    switched: bool = False,
) -> float:
    """Integration time for a given SNR: tau = (SNR * Tsys / T_signal)^2 / (n_pol * B).

    Inverting the radiometer equation. The square is the whole story — halving your signal
    quadruples the time, so a marginal design is not marginally worse, it is hopeless.
    """
    if signal_k <= 0:
        raise ValueError("signal temperature must be positive to be detectable at all")
    if tsys_k <= 0 or bandwidth_hz <= 0 or target_snr <= 0:
        raise ValueError("Tsys, bandwidth, and target SNR must be positive")
    if n_pol < 1:
        raise ValueError("n_pol must be at least 1")
    factor = 2.0 if switched else 1.0
    return (factor * target_snr * tsys_k / signal_k) ** 2 / (n_pol * bandwidth_hz)


def required_effective_area_m2(
    *,
    flux_jy: float,
    tsys_k: float,
    bandwidth_hz: float,
    integration_s: float,
    target_snr: float = 5.0,
    n_pol: int = 1,
    switched: bool = False,
) -> float:
    """Collecting area needed to reach ``target_snr`` on a point source. Solved backwards.

    Only meaningful for a *point* source: an extended source that fills the beam gives the
    same antenna temperature at any aperture, so no amount of area will help, and
    :func:`antenna_temperature_extended_k` explains why.
    """
    if flux_jy <= 0:
        raise ValueError("flux must be positive")
    noise = radiometer_sensitivity_k(
        tsys_k, bandwidth_hz, integration_s, n_pol=n_pol, switched=switched
    )
    required_k = target_snr * noise
    return required_k * 2.0 * K_B / (flux_jy * JANSKY_W_M2_HZ)


def required_diameter_m(
    *,
    flux_jy: float,
    tsys_k: float,
    bandwidth_hz: float,
    integration_s: float,
    aperture_efficiency: float = 0.6,
    target_snr: float = 5.0,
    n_pol: int = 1,
    switched: bool = False,
) -> float:
    """Dish diameter needed for a point-source detection — "how big a dish do I need?"."""
    if not 0.0 < aperture_efficiency <= 1.0:
        raise ValueError("aperture efficiency must be in (0, 1]")
    area = required_effective_area_m2(
        flux_jy=flux_jy,
        tsys_k=tsys_k,
        bandwidth_hz=bandwidth_hz,
        integration_s=integration_s,
        target_snr=target_snr,
        n_pol=n_pol,
        switched=switched,
    )
    return 2.0 * math.sqrt(area / aperture_efficiency / math.pi)


# --------------------------------------------------------------------------------------
# What there is to look at
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class RadioSource:
    """A target, with the provenance of its flux and an honest note on its behaviour."""

    slug: str
    name: str
    #: Flux density at :attr:`reference_freq_hz`, in janskys. None for extended sources
    #: described by brightness temperature instead.
    flux_jy: float | None
    reference_freq_hz: float
    #: Brightness temperature for extended emission (K). None for point sources.
    brightness_temp_k: float | None = None
    #: Approximate angular size, for judging whether a small antenna resolves it.
    angular_size_deg: float | None = None
    source: str = ""
    caveats: tuple[str, ...] = ()

    @property
    def is_extended(self) -> bool:
        return self.brightness_temp_k is not None


@dataclass(frozen=True)
class DetectionEstimate:
    """Whether a given telescope sees a given source, and how long it takes."""

    source: RadioSource
    signal_k: float
    tsys_k: float
    noise_k: float
    snr: float
    time_to_snr5_s: float | None
    notes: tuple[str, ...] = field(default_factory=tuple)

    def summary(self) -> str:
        detectable = "detectable" if self.snr >= 5 else "NOT detected"
        return (
            f"{self.source.name}: T_A {self.signal_k:.4f} K against noise "
            f"{self.noise_k:.4f} K -> SNR {self.snr:.1f} ({detectable})"
        )


def detect(
    source: RadioSource,
    *,
    effective_area_m2: float,
    tsys_k: float,
    bandwidth_hz: float,
    integration_s: float,
    beam_solid_angle_sr: float | None = None,
    n_pol: int = 1,
    switched: bool = False,
) -> DetectionEstimate:
    """Will this telescope see this source, and how long would SNR 5 take?

    Routes to the point-source or extended-source formula according to what the source
    actually is, because using the wrong one is the most flattering mistake available: apply
    ``T_A = S A_e / 2k`` to galactic HI and a bigger dish appears to help, which it does not.
    """
    notes: list[str] = []
    if source.is_extended:
        assert source.brightness_temp_k is not None
        signal = antenna_temperature_extended_k(
            source.brightness_temp_k,
            source_solid_angle_sr=None,
            beam_solid_angle_sr=beam_solid_angle_sr,
        )
        notes.append(
            "Extended source: the antenna temperature equals the brightness temperature and "
            "does NOT improve with a bigger aperture. More collecting area buys angular "
            "resolution here, not signal."
        )
        notes.append(
            "For line work the radiometer equation flatters you badly. The real floor is "
            "baseline stability — standing waves between feed and dish, gain drift, and RFI "
            "— not thermal noise, so treat a huge predicted SNR as 'thermal noise will not "
            "be your problem' rather than as a promise."
        )
        notes.append(
            "Catalogued brightness temperatures come from surveys with 16-36 arcmin beams. "
            "An amateur beam is degrees wide and reads the AVERAGE over that patch, which is "
            "lower than the survey peak wherever the emission is structured. Expect to "
            "measure less than the catalogue number, and convolve a survey map with your own "
            "beam if you need the honest expectation."
        )
    else:
        assert source.flux_jy is not None
        signal = antenna_temperature_point_k(source.flux_jy, effective_area_m2)
        if source.angular_size_deg is not None and beam_solid_angle_sr is not None:
            beam_deg = math.degrees(math.sqrt(beam_solid_angle_sr))
            if source.angular_size_deg > beam_deg:
                notes.append(
                    f"{source.name} is about {source.angular_size_deg:g} deg across, larger "
                    f"than this ~{beam_deg:.1f} deg beam, so it is resolved: the point-source "
                    "flux overstates what you collect at any one pointing."
                )

    noise = radiometer_sensitivity_k(
        tsys_k, bandwidth_hz, integration_s, n_pol=n_pol, switched=switched
    )
    ratio = signal / noise
    try:
        seconds = time_to_detect_s(
            signal_k=signal,
            tsys_k=tsys_k,
            bandwidth_hz=bandwidth_hz,
            target_snr=5.0,
            n_pol=n_pol,
            switched=switched,
        )
    except ValueError:  # pragma: no cover - only for a zero-signal source
        seconds = None
    notes.extend(source.caveats)
    return DetectionEstimate(
        source=source,
        signal_k=signal,
        tsys_k=tsys_k,
        noise_k=noise,
        snr=ratio,
        time_to_snr5_s=seconds,
        notes=tuple(notes),
    )


# --------------------------------------------------------------------------------------
# The source catalogue
#
# Held back from the first M4 release until the numbers could be verified, because a flux
# without an epoch or a provenance is not a number this project prints. Everything here is
# from Perley & Butler (2017, ApJS 230, 7) unless stated, cross-checked against the
# independent Trotter et al. (2017, MNRAS 469, 1299) scale — the two agree to about 2%.
#
# The point-source fluxes are for EPOCH 2016.0. Two of these four sources fade measurably,
# so an undated flux is a half-truth; :func:`flux_at_epoch` extrapolates and flags it.
# --------------------------------------------------------------------------------------

#: Reference epoch of the catalogued point-source fluxes (decimal year).
CATALOG_EPOCH_YEAR = 2016.0

_PERLEY_BUTLER = "Perley & Butler 2017, ApJS 230, 7 (arXiv:1609.05940)"

SOURCES: dict[str, RadioSource] = {
    source.slug: source
    for source in (
        RadioSource(
            slug="cas-a",
            name="Cassiopeia A",
            flux_jy=1768.0,
            reference_freq_hz=1.4e9,
            angular_size_deg=8.0 / 60.0,
            source=_PERLEY_BUTLER,
            caveats=(
                "FLUX IS EPOCH-DEPENDENT: 1768 Jy is for epoch 2016.0. Cas A fades, so an "
                "undated Cas A flux is meaningless. Use flux_at_epoch() for another year.",
                "Fading is NOT at a constant rate. Trotter et al. (2017) find at 6.3 sigma "
                "that it faded fast into the late 1960s, slowed, then resumed fast fading by "
                "the late 1990s. The long-term L-band average is 0.670 +/- 0.019 %/yr; the "
                "recent segment is nearer 0.8 %/yr. Any single rate is a fiction over a long "
                "baseline.",
                "The older Baars et al. (1977) fading law (0.93 %/yr at 1.4 GHz) is now known "
                "to overpredict the decline.",
            ),
        ),
        RadioSource(
            slug="cyg-a",
            name="Cygnus A",
            flux_jy=1580.0,
            reference_freq_hz=1.4e9,
            angular_size_deg=2.2 / 60.0,
            source=_PERLEY_BUTLER,
            caveats=(
                "Stable: only the ~1 Jy nucleus can vary, and it is under 0.1% of the total, "
                "so decadal changes are negligible. This is the best L-band standard for an "
                "amateur — brightest of the stable sources, and the smallest of these four.",
            ),
        ),
        RadioSource(
            slug="tau-a",
            name="Taurus A (Crab Nebula)",
            flux_jy=829.0,
            reference_freq_hz=1.4e9,
            angular_size_deg=8.0 / 60.0,
            source=_PERLEY_BUTLER,
            caveats=(
                "Fades slowly: 0.102 (+0.042/-0.043) %/yr in L band, measured by Trotter et "
                "al. (2017). Perley & Butler instead INFER ~0.25 %/yr from an offset against "
                "the 1977 scale while noting they found little direct information; the "
                "measured value is the one used here, and the factor ~2.5 disagreement "
                "between the two methods is unresolved.",
                "Strongly linearly polarized, unlike the others — the factor of 2 in "
                "sensitivity_k_per_jy assumes an unpolarized source.",
            ),
        ),
        RadioSource(
            slug="vir-a",
            name="Virgo A (M87)",
            flux_jy=212.0,
            reference_freq_hz=1.4e9,
            angular_size_deg=15.0 / 60.0,
            source=_PERLEY_BUTLER,
            caveats=(
                "Stable: within 1% of its 1977 value after four decades.",
                "The largest of these four at 14-16 arcmin, with a diffuse halo, so "
                "single-dish and interferometer flux scales differ. Unresolved by any "
                "amateur beam, which makes it easier here than for the professionals.",
            ),
        ),
        RadioSource(
            slug="sun-quiet",
            name="Quiet Sun",
            flux_jy=5.5e5,
            reference_freq_hz=1.415e9,
            angular_size_deg=35.0 / 60.0,
            source="Tan et al. 2015, ApJ 808, 61 (arXiv:1507.04866) — 55 SFU at 1415 MHz",
            caveats=(
                "55 SFU (1 SFU = 1e4 Jy) at solar MINIMUM, from two independent instruments. "
                "Other estimates in the same paper span 47-61 SFU; treat this as +/- 15%.",
                "Varies with the solar cycle by roughly 2-4x. That ratio is INFERRED from "
                "1 GHz multi-cycle data (Nobeyama/Toyokawa), not measured at 1.4 GHz.",
                "Do NOT use the F10.7 index for this: it is 2800 MHz, a different frequency "
                "with a different absolute level. Conflating them is the standard error.",
                "By far the strongest thing an amateur dish will ever see, and a good first "
                "target for proving a chain works before hunting hydrogen.",
            ),
        ),
        RadioSource(
            slug="hi-inner-plane",
            name="Galactic HI, inner-plane (b=0)",
            flux_jy=None,
            reference_freq_hz=1_420_405_751.768,
            brightness_temp_k=113.0,
            source="LAB/GASS/EBHIS via the Bonn AIfA HI profile server, 0.2 deg beam",
            caveats=(
                "Median of directly-queried inner-plane profiles; the range across the inner "
                "plane is 96-136 K.",
                "This is a survey brightness at 16-36 arcmin resolution. A degrees-wide "
                "amateur beam reads a lower average — see the extended-source note.",
                "Physically capped near the spin temperature: saturated 21 cm brightness "
                "gives T_s = 146 K (Sofue 2017), so ~100-150 K is the ceiling, not a floor.",
            ),
        ),
        RadioSource(
            slug="hi-high-latitude",
            name="Galactic HI, high latitude",
            flux_jy=None,
            reference_freq_hz=1_420_405_751.768,
            brightness_temp_k=1.0,
            source="LAB/GASS/EBHIS via the Bonn AIfA HI profile server, 0.2 deg beam",
            caveats=(
                "About 0.8-1.0 K toward the Lockman Hole, 1.4 K at the north galactic pole. "
                "Mid-latitudes (|b| ~ 20-40 deg) run 23-40 K, so this is the hard case, not "
                "the typical one.",
                "Two orders of magnitude below the plane — point a first-light attempt at the "
                "plane, not at a pole.",
            ),
        ),
    )
}


def get_source(slug: str) -> RadioSource:
    """Look a catalogued source up by slug."""
    try:
        return SOURCES[slug]
    except KeyError:
        raise KeyError(f"unknown source {slug!r}; known: {', '.join(sorted(SOURCES))}") from None


#: Measured L-band fading rates, %/yr, for the sources that fade. Values and their
#: uncertainties from Trotter et al. (2017); see each source's caveats for why a single
#: rate is an approximation.
FADE_RATE_PERCENT_PER_YEAR: dict[str, float] = {
    "cas-a": 0.670,
    "tau-a": 0.102,
}


def flux_at_epoch(source: RadioSource, year: float) -> tuple[float, tuple[str, ...]]:
    """A fading source's flux at another epoch, with the extrapolation flagged.

    Returns ``(flux_jy, notes)``. For a stable source this is the catalogue value and a note
    saying so. For a fading one it applies the measured long-term rate from the catalogue
    epoch — and says plainly that the rate is an average over a period during which the
    fading demonstrably was not constant, so a long extrapolation is a guess with arithmetic
    attached.
    """
    if source.flux_jy is None:
        raise ValueError(f"{source.name} is an extended source and has no flux density")
    rate = FADE_RATE_PERCENT_PER_YEAR.get(source.slug)
    if rate is None:
        return source.flux_jy, (
            f"{source.name} is stable; the epoch {year:g} makes no difference.",
        )
    elapsed = year - CATALOG_EPOCH_YEAR
    flux = source.flux_jy * (1.0 - rate / 100.0) ** elapsed
    notes = [
        f"Extrapolated {elapsed:+.1f} yr from epoch {CATALOG_EPOCH_YEAR:g} at "
        f"{rate:g} %/yr: {source.flux_jy:.0f} Jy -> {flux:.0f} Jy.",
        "That rate is a long-term average over an interval in which the fading measurably "
        "was NOT constant. Treat this as an estimate with arithmetic attached, not a "
        "prediction, and prefer a recent published measurement if you have one.",
    ]
    if abs(elapsed) > 15:
        notes.append(
            f"{abs(elapsed):.0f} years is a long extrapolation past the data the rate was "
            "fitted to. The uncertainty here is larger than the number's precision suggests."
        )
    return flux, tuple(notes)
