"""jansky-forge — design, build, and characterize radio-astronomy antennas.

Three legs, one package:

**Create** — closed-form models (:mod:`jansky_forge.apertures` for dishes and horns,
:mod:`jansky_forge.wires` for dipoles, arrays and the ground beneath them) that recompute in microseconds, so exploring a design is interactive by
construction rather than by optimization. From M1, :mod:`jansky_forge.horns` also runs the
other way: give it a target gain and it synthesizes a buildable horn.

**Build** — a :mod:`jansky_forge.catalog` of known telescope builds to start from, and
:mod:`jansky_forge.fabricate`, which turns a design into cut metal: 1:1 printable templates
tiled across ordinary paper, DXF for a laser, a cut list with an honest kerf and material
budget, assembly steps, and a ``design.json`` tying the shapes back to the prediction that
produced them.

**Sensitivity** — :mod:`jansky_forge.sensitivity` turns antenna numbers into telescope
numbers: system temperature as a budget you can act on, SEFD, G/T, the radiometer equation,
and whether you will actually see a given source in a given time.

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
from jansky_forge.feeds import CosQFeed, HornFeed, best_f_over_d, design_probe, evaluate_feed
from jansky_forge.horns import (
    ConicalDesign,
    PyramidalDesign,
    design_conical_horn,
    design_pyramidal_horn,
    realizability,
)
from jansky_forge.sensitivity import (
    radiometer_sensitivity_k,
    sefd_jy,
    sensitivity_k_per_jy,
    system_temperature,
    time_to_detect_s,
)
from jansky_forge.units import wavelength_m
from jansky_forge.wires import (
    AVERAGE_GROUND,
    DipoleOverGround,
    GroundType,
    HalfWaveDipole,
    YagiUda,
    ground_gain_db,
)

__all__ = [
    "BANDS",
    "AntennaModel",
    "Band",
    "Characterization",
    "Development",
    "DipoleOverGround",
    "GroundType",
    "HalfWaveDipole",
    "ConicalDesign",
    "AVERAGE_GROUND",
    "ConicalHorn",
    "CosQFeed",
    "ParabolicDish",
    "PyramidalDesign",
    "HornFeed",
    "Packet",
    "PyramidalHorn",
    "YagiUda",
    "__version__",
    "best_f_over_d",
    "design_conical_horn",
    "design_pyramidal_horn",
    "design_probe",
    "evaluate_feed",
    "radiometer_sensitivity_k",
    "sefd_jy",
    "sensitivity_k_per_jy",
    "system_temperature",
    "time_to_detect_s",
    "get_band",
    "ground_gain_db",
    "realizability",
    "wavelength_m",
    "write_packet",
]
