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

#: Rough zenith atmospheric contribution at L band (K). Weakly frequency-dependent below a
#: few GHz; stated as a constant with that limitation named.
T_ATMOSPHERE_ZENITH_K = 2.5


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

    At 1.4 GHz away from the plane this gives about 3.4 K, which is the usual cold-sky
    figure. It is an estimate, not a measurement of your sky — a real site has RFI, and a
    real pointing has a galactic latitude.
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

    The factor of two is the standard convention: an unpolarized source splits its power
    evenly between two orthogonal polarizations, and a single-polarization receiver collects
    one of them.

    Verified against the BHARAT 21 cm horn, which publishes both A_e = 0.407 m^2 and
    1.47e-4 K/Jy; this returns 1.474e-4.
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
