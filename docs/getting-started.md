# Getting started

How to install and use jansky-forge. If you already know what you want to do, jump to
[Workflows](workflows.md) — this page is the foundation underneath it.

---

## Install

```bash
git clone https://github.com/joebarbere/jansky-forge
cd jansky-forge
make setup          # uv sync, pinned Python 3.12
make test
```

The core needs **only NumPy and SciPy**. That is deliberate: the interactive tier is
closed-form maths, so someone who wants dish numbers installs almost nothing.

### Optional extras

Each unlocks one tier and nothing else. The library and CLI work unchanged without them.

| Extra | Command | Unlocks |
|---|---|---|
| `mom` | `pip install 'jansky-forge[mom]'` | Tier-2 method-of-moments validation (`pymininec`) |
| `measure` | `pip install 'jansky-forge[measure]'` | Richer network math and the `scikit-rf` cross-check |
| `ui` | `pip install 'jansky-forge[ui]'` | The web UI (`jansky-forge serve`) |
| `plot` | `pip install 'jansky-forge[plot]'` | matplotlib, for your own plotting |

Touchstone reading is **native** — you do not need the `measure` extra just to read a `.s1p`
from your VNA.

---

## The mental model

### Three tiers, and only one is interactive

| Tier | Method | Speed | Use for |
|---|---|---|---|
| **1** | Closed-form analytic | µs–ms | Everything interactive: dishes, horns, wires |
| **2** | Method of moments | seconds | On-demand validation; anything where elements couple |
| **3** | Full-wave *export* | offline | Rigor without owning a solver — we write the input deck |

The speed of Tier 1 is a **physics choice**, not an optimization. Aperture antennas many
wavelengths across are exactly the regime where textbook theory is accurate to tenths of a
dB, and a full-wave solver would spend minutes agreeing with it.

### Every model tells you where it stops being trustworthy

A `Characterization` carries `notes` — the conditions under which its own numbers stop
meaning anything. Every interface prints them: CLI, UI, JSON API. **If you find yourself
wanting to suppress them for tidiness, that is the moment they matter most.**

### Predicted is not measured

Everything from the design side is a *prediction*. It only becomes a measurement once it has
been through `measure` (VNA) or `onsky` (sky) — and those keep the two in separate fields
with nothing combining them. → [Honesty invariants](honesty-invariants.md)

---

## Command reference

```bash
jansky-forge <command> --help      # every command has real help
```

### Looking things up

| Command | Does |
|---|---|
| `bands` | The frequencies this tool knows, and *why each matters* |
| `list [--band hi] [--kind horn]` | Catalogue templates, filterable |
| `show <slug> [--freq-mhz N] [--json]` | One template: geometry, provenance, caveats, predicted performance |
| `characterize <slug> [--band X] [--freq-mhz N]` | One template across several frequencies |
| `sources` | Catalogued radio sources with provenance and epochs |

### Designing

| Command | Does |
|---|---|
| `design --gain-dbi 18` | Synthesize a horn: **gain in, dimensions out** |
| `feed --f-over-d 0.35` | What feed a dish wants, or how a given feed does on it |
| `probe --waveguide wr650` | Waveguide probe length and backshort distance |
| `sensitivity --template discovery-dish` | Tsys, SEFD, G/T — and whether you will see a source |

### Building and serving

| Command | Does |
|---|---|
| `fabricate --gain-dbi 18 --out ./horn` | Full packet: 1:1 templates, DXF, cut list, assembly steps |
| `serve` | The web UI on `http://127.0.0.1:8000` |

### Useful flag combinations

```bash
# What does a known build actually do, at another frequency?
jansky-forge show discovery-dish --freq-mhz 1667

# Machine-readable, caveats included
jansky-forge show pictor --json

# Design for a different band and waveguide
jansky-forge design --gain-dbi 15 --band oh1667 --waveguide wr430

# A conical horn instead
jansky-forge design --gain-dbi 20 --shape conical

# Fabrication tuned to your tools and paper
jansky-forge fabricate --gain-dbi 18 --out ./horn \
    --tool jigsaw --seam-mm 8 --thickness-mm 1.0 --page a3

# Will this dish see Cas A this year?
jansky-forge sensitivity --template discovery-dish --source cas-a --epoch-year 2026.5

# ...and galactic HI? (a different formula — see traps.md)
jansky-forge sensitivity --template discovery-dish --source hi-inner-plane
```

---

## Library quickstart

### Characterize something

```python
from jansky_forge import ParabolicDish, catalog

# From the catalogue, with its provenance and caveats
template = catalog.get("discovery-dish")
print(template.characterize().summary())
for caveat in template.caveats:
    print("caveat:", caveat)

# Or your own geometry
dish = ParabolicDish(diameter_m=1.2, f_over_d=0.45, surface_rms_mm=3.0)
char = dish.characterize(1_420_405_751.768)
print(f"{char.gain_dbi:.1f} dBi, {char.hpbw_e_deg:.1f}° beam, A_e = {char.effective_area_m2:.2f} m²")
for note in char.notes:          # always read these
    print("note:", note)
```

### Design a horn, then unroll it

```python
from jansky_forge import design_pyramidal_horn, write_packet

design = design_pyramidal_horn(
    gain_dbi=18.0, freq_hz=1_420_405_751.768,
    waveguide_a_m=0.1651, waveguide_b_m=0.08255,   # WR-650
)
print(design.summary())

packet = write_packet(design, "./horn", tool="jigsaw", seam_allowance_mm=8.0)
print(packet.summary())
```

### Feed a dish properly

```python
from jansky_forge import feeds

wanted = feeds.best_feed_for_dish(f_over_d=0.35)
print(wanted.summary())
for note in wanted.notes:
    print(note)          # tells you the beamwidth to aim for
```

### Will it see anything?

```python
from jansky_forge import sensitivity as sens

receiver = sens.cascade_noise_temperature_k([
    sens.Stage.loss("pigtail", loss_db=0.2),
    sens.Stage.amplifier("LNA", gain_db=30, noise_figure_db=0.3),
    sens.Stage.amplifier("SDR", gain_db=20, noise_figure_db=6.0),
])
tsys = sens.system_temperature(freq_hz=1.4204e9, receiver_k=receiver, spillover_efficiency=0.93)
print(tsys.summary())        # reports which term dominates — that is the one to fix
```

### Check the closed form against numerics

```python
from jansky_forge import mom       # needs the [mom] extra

model = mom.yagi_model(freq_hz=143.05e6, elements_m=mom.GRAVES_7EL_ELEMENTS, radius_m=0.003)
print(mom.compare_with_analytic(model, freq_hz=143.05e6, analytic_dbi=11.24).summary())
```

### Read your VNA

```python
from jansky_forge import measure

sweep = measure.read_touchstone("bench.s1p")
at_antenna = measure.shift_reference_plane(sweep, length_m=0.5)   # de-embed the cable!
fraction, advice = measure.resonance_offset(at_antenna, design_freq_hz=1.4204e9)
print(advice)
```

---

## Where things live

| Module | Owns |
|---|---|
| `units` | Constants and conversions. One file, so a unit bug is a one-file bug |
| `core` | The `AntennaModel` protocol and `Characterization` |
| `bands` | Frequencies that matter, and why |
| `apertures` | `ParabolicDish`, `PyramidalHorn`, `ConicalHorn` |
| `catalog` | Known builds, with enforced provenance |
| `horns` | Phase-error gain, synthesis, patterns, realizability |
| `fabricate/` | Developments, SVG templates, DXF, cut lists, packets |
| `feeds` | Illumination, spillover, matching, waveguide probes |
| `sensitivity` | Tsys, SEFD, G/T, radiometer, sources |
| `wires` | Dipoles, ground, arrays, Yagi estimate |
| `mom` | Tier-2 backends, NEC export |
| `measure` | Touchstone, reference plane, matching, comparison |
| `onsky` | Y-factor, drift scans, transit, bundle ingest |
| `server/` | The web UI |

---

## Working on the code

```bash
make lint typecheck cov audit     # or run the /verify skill, which does all of it
```

Non-negotiables: **85% coverage floor**, ruff (line length 100) and mypy clean, branch before
committing, every PR adds a `CHANGES.md` entry. `make audit` must print **nothing** — it is
the catalogue's provenance rules made executable.

Before touching the physics, read [traps.md](traps.md) and
[honesty-invariants.md](honesty-invariants.md).

---

## The sibling repos

| Repo | Is |
|---|---|
| [`jansky`](https://github.com/joebarbere/jansky) | The teaching course. We cross-check our radiometer equation against it |
| [`jansky-research`](https://github.com/joebarbere/jansky-research) | Original research slices |
| [`jansky-observe`](https://github.com/joebarbere/jansky-observe) | Station software. `onsky` reads its observation bundles |
