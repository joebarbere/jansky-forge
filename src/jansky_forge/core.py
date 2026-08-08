"""The antenna-model protocol and its result type.

Every antenna in this package — dish, horn, and from M5 the wire families — is a frozen
dataclass implementing :class:`AntennaModel`. Two methods, deliberately:

``parameters()``
    The design variables, as a flat mapping. This is what a slider drives, what a sweep
    varies, and what a fabrication template consumes. Flat and JSON-able on purpose.

``characterize(freq_hz)``
    The performance at one frequency, as a :class:`Characterization`.

Both are **pure**: no I/O, no caching, no global state. That is what makes the
interactive tier honest — recomputation is free because the physics is closed-form, not
because anything is memoized behind your back.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from jansky_forge.units import (
    effective_area_m2,
    from_db,
    gaussian_beam_solid_angle_sr,
    to_db,
    wavelength_m,
)


@dataclass(frozen=True)
class Characterization:
    """What an antenna does at one frequency.

    Every field is a *predicted* quantity from the analytic (Tier-1) model. Measured
    counterparts arrive at M7/M8 and are always reported alongside, never merged into,
    these predictions — the house rule that a model result and a measurement never wear
    the same label.
    """

    freq_hz: float
    gain_dbi: float
    hpbw_e_deg: float
    hpbw_h_deg: float
    aperture_efficiency: float
    effective_area_m2: float
    beam_solid_angle_sr: float
    #: Free-form, model-specific extras (focal length, edge taper, Ruze loss, …).
    detail: dict[str, float] = field(default_factory=dict)
    #: Honest caveats the model wants the reader to see (validity limits, assumptions).
    notes: tuple[str, ...] = ()

    @property
    def wavelength_m(self) -> float:
        return wavelength_m(self.freq_hz)

    @property
    def gain_linear(self) -> float:
        return from_db(self.gain_dbi)

    @property
    def hpbw_geometric_mean_deg(self) -> float:
        """One number for a two-plane beam — the geometric mean of the E/H widths."""
        return math.sqrt(self.hpbw_e_deg * self.hpbw_h_deg)

    def summary(self) -> str:
        """One-line human summary, the format the CLI and future UI both print."""
        return (
            f"{self.freq_hz / 1e6:.3f} MHz: {self.gain_dbi:.2f} dBi, "
            f"HPBW {self.hpbw_e_deg:.2f}° × {self.hpbw_h_deg:.2f}°, "
            f"eta_a {self.aperture_efficiency:.3f}, A_e {self.effective_area_m2:.4f} m²"
        )


@runtime_checkable
class AntennaModel(Protocol):
    """Structural type every antenna model satisfies."""

    @property
    def kind(self) -> str:
        """Short human name for the family ("Parabolic dish").

        Read-only and per-family, not per-instance: models declare it as a ``ClassVar`` so
        it can never be passed to a constructor and mistaken for a design variable.
        """
        ...

    def parameters(self) -> dict[str, float]:
        """The design variables, flat and JSON-able."""
        ...

    def characterize(self, freq_hz: float) -> Characterization:
        """Predicted performance at ``freq_hz``."""
        ...


def characterization_from_gain(
    *,
    freq_hz: float,
    gain_linear: float,
    hpbw_e_deg: float,
    hpbw_h_deg: float,
    aperture_efficiency: float,
    detail: dict[str, float] | None = None,
    notes: tuple[str, ...] = (),
) -> Characterization:
    """Assemble a :class:`Characterization` from a linear gain, filling the derived fields.

    Effective area comes from the reciprocity identity A_e = Gλ²/4π rather than from
    ``eta × physical_area`` — so for models where the two disagree (a horn whose
    efficiency assumption is nominal, say), the number reported is the one consistent
    with the gain actually quoted.
    """
    if gain_linear <= 0:
        raise ValueError(f"gain must be positive, got {gain_linear}")
    return Characterization(
        freq_hz=freq_hz,
        gain_dbi=to_db(gain_linear),
        hpbw_e_deg=hpbw_e_deg,
        hpbw_h_deg=hpbw_h_deg,
        aperture_efficiency=aperture_efficiency,
        effective_area_m2=effective_area_m2(gain_linear, freq_hz),
        beam_solid_angle_sr=gaussian_beam_solid_angle_sr(hpbw_e_deg, hpbw_h_deg),
        detail=detail or {},
        notes=notes,
    )
