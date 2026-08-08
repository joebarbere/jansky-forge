"""Physical constants and unit conversions shared by every antenna model.

One module owns the constants so a unit bug is a single-file bug. Everything internal is
SI (metres, hertz, watts, kelvin, steradians); millimetres and degrees appear only at the
edges — in user-facing dataclass fields where they are the natural workshop unit
(``surface_rms_mm``) and in :class:`~jansky_forge.core.Characterization` outputs where
degrees are how beamwidths are read.
"""

from __future__ import annotations

import math

#: Speed of light in vacuum (m/s), CODATA exact.
C_M_S = 299_792_458.0

#: Boltzmann constant (J/K), CODATA exact — used from M4 (G/T, SEFD, radiometer).
K_B = 1.380_649e-23

#: Jansky (W m^-2 Hz^-1). Flux densities in radio astronomy are quoted in these.
JANSKY_W_M2_HZ = 1e-26


def wavelength_m(freq_hz: float) -> float:
    """Free-space wavelength in metres for ``freq_hz``.

    >>> round(wavelength_m(1_420_405_751.768), 4)
    0.2111
    """
    if freq_hz <= 0:
        raise ValueError(f"frequency must be positive, got {freq_hz}")
    return C_M_S / freq_hz


def frequency_hz(wavelength_metres: float) -> float:
    """Inverse of :func:`wavelength_m`."""
    if wavelength_metres <= 0:
        raise ValueError(f"wavelength must be positive, got {wavelength_metres}")
    return C_M_S / wavelength_metres


def to_db(linear: float) -> float:
    """Power ratio → decibels (10·log10). Not amplitude — this is the 10, not 20, form."""
    if linear <= 0:
        raise ValueError(f"cannot express a non-positive power ratio in dB: {linear}")
    return 10.0 * math.log10(linear)


def from_db(db: float) -> float:
    """Decibels → power ratio."""
    return 10.0 ** (db / 10.0)


def gaussian_beam_solid_angle_sr(hpbw_e_deg: float, hpbw_h_deg: float) -> float:
    """Beam solid angle (sr) for a Gaussian main beam with the given half-power widths.

    Ω_A ≈ 1.133 · θ_E · θ_H for a Gaussian beam (the standard radio-astronomy
    approximation; Kraus, *Radio Astronomy*). Inputs in degrees, result in steradians.
    """
    theta_e = math.radians(hpbw_e_deg)
    theta_h = math.radians(hpbw_h_deg)
    return 1.133 * theta_e * theta_h


def effective_area_m2(gain_linear: float, freq_hz: float) -> float:
    """Effective aperture from gain: A_e = G·λ²/(4π).

    The reciprocity identity that turns any gain figure into collecting area — the bridge
    from "antenna" to "telescope", and the basis of every sensitivity number this package
    reports from M4 onward.
    """
    lam = wavelength_m(freq_hz)
    return gain_linear * lam * lam / (4.0 * math.pi)
