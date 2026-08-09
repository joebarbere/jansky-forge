"""jansky-forge — design, build, and characterize radio-astronomy antennas.

Three legs, one package:

**Create** — closed-form models (:mod:`jansky_forge.apertures` and, from M5, the wire
families) that recompute in microseconds, so exploring a design is interactive by
construction rather than by optimization. From M1, :mod:`jansky_forge.horns` also runs the
other way: give it a target gain and it synthesizes a buildable horn.

**Build** — a :mod:`jansky_forge.catalog` of known telescope builds to start from, and
:mod:`jansky_forge.fabricate`, which turns a design into cut metal: 1:1 printable templates
tiled across ordinary paper, DXF for a laser, a cut list with an honest kerf and material
budget, assembly steps, and a ``design.json`` tying the shapes back to the prediction that
produced them.

**Characterize** — (from M7/M8) measured-versus-predicted: VNA sweeps, Y-factor system
temperature, and beam maps from drift scans, ingested from the sibling ``jansky-observe``
station software so a real antenna's numbers land next to the model's.

Sibling of `jansky <https://github.com/joebarbere/jansky>`_ (the course),
`jansky-research <https://github.com/joebarbere/jansky-research>`_ (the research), and
`jansky-observe <https://github.com/joebarbere/jansky-observe>`_ (the station).
"""

from __future__ import annotations

from jansky_forge._version import __version__
from jansky_forge.apertures import ConicalHorn, ParabolicDish, PyramidalHorn
from jansky_forge.bands import BANDS, Band, get_band
from jansky_forge.core import AntennaModel, Characterization
from jansky_forge.fabricate import Development, Packet, write_packet
from jansky_forge.horns import (
    ConicalDesign,
    PyramidalDesign,
    design_conical_horn,
    design_pyramidal_horn,
    realizability,
)
from jansky_forge.units import wavelength_m

__all__ = [
    "BANDS",
    "AntennaModel",
    "Band",
    "Characterization",
    "Development",
    "ConicalDesign",
    "ConicalHorn",
    "ParabolicDish",
    "PyramidalDesign",
    "Packet",
    "PyramidalHorn",
    "__version__",
    "design_conical_horn",
    "design_pyramidal_horn",
    "get_band",
    "realizability",
    "wavelength_m",
    "write_packet",
]
