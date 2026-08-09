# jansky-forge

**Design, build, and characterize radio-astronomy antennas.** Pick a known telescope build,
change a dimension, watch the numbers move — then get the fabrication drawings, and later put
your measured performance next to the prediction.

Fourth sibling of [`jansky`](https://github.com/joebarbere/jansky) (the course),
[`jansky-research`](https://github.com/joebarbere/jansky-research) (original research), and
[`jansky-observe`](https://github.com/joebarbere/jansky-observe) (station software).

```console
$ jansky-forge show discovery-dish          # what does this antenna do?
$ jansky-forge design --gain-dbi 18         # what should I build for 18 dBi?
$ jansky-forge fabricate --gain-dbi 18 --out ./horn   # ...and how do I cut it?
$ jansky-forge feed --f-over-d 0.35         # what feed does my dish want?
$ jansky-forge probe --waveguide wr650      # where does the probe go?
$ jansky-forge sensitivity --template discovery-dish --brightness-k 100   # will I see it?
```

## Why this exists

The open-source antenna world has excellent tools for *wire* antennas — NEC2 and its
descendants, some with genuinely live feedback. It has almost nothing for the antennas radio
astronomers actually build: dishes and horns. What exists for those is 1990s-frozen software,
one-shot web calculators, or a spreadsheet in a forum post. And nothing anywhere connects the
three things that matter:

**design → fabrication → measurement**, in radio-astronomy units (G/T, SEFD, system
temperature, time-to-detect) rather than ham-radio ones.

That is the gap. See [`plans/jansky_forge.md`](plans/jansky_forge.md) for the full survey and
roadmap.

## How it stays fast

Every design change recomputes in microseconds because the physics is closed-form, not because
anything is cached. A 21 cm dish or horn is many wavelengths across — precisely the regime where
textbook aperture theory is good to a few tenths of a dB and a full-wave solver would spend
minutes to agree with it. Three tiers, and only the first one is ever in the interactive path:

| Tier | Method | Speed | For |
|---|---|---|---|
| 1 | Closed-form analytic (NumPy) | µs–ms | Everything interactive. Dishes, horns, wire families |
| 2 | Method of moments (pymininec; NEC2 optional) | seconds | On-demand validation of wire designs |
| 3 | Full-wave *export* (openEMS/NEC decks) | offline | Rigor without owning a solver — we generate the input, we never run it inline |

## The catalog

Nobody should start from a blank sheet. `jansky-forge list` shows known builds — the KrakenRF
Discovery Dish, published teaching horns, observatory student telescopes — each with its
geometry, where that geometry came from, and honest caveats where a source did not state a
number.

Two rules make the catalog trustworthy:

- **A number without a source is not printed.** Unverified dimensions are recorded as gaps, not
  filled with plausible values. `make audit` enforces it; CI fails on any output.
- **Published gains are cross-checks, not our claims.** Where a build publishes performance
  figures, the test suite compares them against what our model computes from the geometry. A
  disagreement gets recorded as a disagreement — never tuned away by adjusting an efficiency
  until the numbers match.

## Install

```bash
git clone https://github.com/joebarbere/jansky-forge
cd jansky-forge
make setup      # uv sync — pinned Python 3.12
make test
```

## Use

```bash
jansky-forge bands                                  # the frequencies that matter, and why
jansky-forge list --band hi                         # builds designed for the hydrogen line
jansky-forge list --kind horn
jansky-forge show discovery-dish                    # geometry, provenance, predicted performance
jansky-forge show discovery-dish --json             # machine-readable
jansky-forge characterize discovery-dish --band hi --band oh1667 --freq-mhz 1200
```

As a library:

```python
from jansky_forge import ParabolicDish, catalog

# Start from a known build...
dish = catalog.get("discovery-dish").model
print(catalog.get("discovery-dish").characterize().summary())

# ...or design your own. Every model is a frozen dataclass; characterize() is pure.
mine = ParabolicDish(diameter_m=1.2, f_over_d=0.45, surface_rms_mm=3.0)
char = mine.characterize(1_420_405_751.768)
print(f"{char.gain_dbi:.1f} dBi, {char.hpbw_e_deg:.1f}° beam, A_e = {char.effective_area_m2:.2f} m²")
for note in char.notes:
    print("note:", note)      # models state their own validity limits
```

## Honesty rules

The same standard as the sibling repos, applied to hardware:

- **Predicted and measured never wear the same label.** From M8, real measurements sit beside
  model output with separate provenance; a disagreement is reported, not reconciled.
- **Models state their own limits.** Every `Characterization` carries `notes` — where the model
  stops being trustworthy, which assumption is doing the work. The CLI prints them; a UI must
  too.
- **Efficiency is a budget, not a fudge factor.** Illumination, spillover, blockage, and surface
  error are separate named terms because each is a different thing to *fix* in a real build.

## Status

**M8 (`v0.9.0`) — on-sky characterization.** The first numbers in this package that are not
derived from geometry at all. Y-factor system temperature, drift-scan beamwidth, and transit
aperture efficiency — **the efficiency every earlier milestone could only assume** — read
directly from `jansky-observe` observation bundles.

**M7 (`v0.8.0`) — measurement ingest.** Reads what a VNA says about the metal you built.
Native Touchstone (`.s1p`) parsing, reference-plane de-embedding, L-network matching, and a
comparison that **keeps prediction and measurement in separate fields with nothing combining
them** — a test asserts no merged field exists, which is honesty invariant 5 made structural.

It diagnoses rather than just reporting: reactance off while resistance agrees is a length
error or a stray cable; "resonant 2% low" becomes "shorten it by 2%".

**M6 (`v0.7.0`) — Tier-2 validation.** The button that says *check that*. A `pymininec`
backend solves the same antenna numerically, and it closed both disagreements M5 shipped: the
short-boom Yagi (Tier 1 read 4.47 dBi, Tier 2 gives 6.49, published 6.75) and the JOVE array's
mutual coupling (2.75 dB stacking rather than the ideal 3.01). It also produces **feed
impedance**, which Tier 1 structurally cannot — and which explains why the published
7-element Yagi uses a folded driven element.

Optional: `pip install jansky-forge[mom]`. Tier 1 is unchanged without it.

**M5 (`v0.6.0`) — wire antennas and arrays.** Dipoles, folded dipoles, arrays, and the thing
that dominates every HF antenna: **the ground**. A horizontal dipole works with its own
inverted image in the earth, so height is a beam-steering control rather than a mounting
detail — low and the lobe is overhead, high and it drops toward the horizon.

Validated against NASA's Radio JOVE manual: their published 5.8 dBi single-dipole gain
(we compute 5.89 over average ground) and their 23.28 ft element length (we compute 23.24).
This finally unlocks the `radio-jove` and meteor-scatter Yagi catalogue entries, which waited
from M0 for a model that could evaluate them.

Yagis are modelled by **boom length only** — element design is what M6's method-of-moments
tier is for, and a plausible-looking analytic element model would be worse than none.

**M4 (`v0.5.0`) — sensitivity.** Antenna numbers become telescope numbers: system
temperature as a budget you can act on, SEFD, G/T, the radiometer equation, time-to-detect,
and "how big a dish do I need?" solved backwards.

The asymmetry it exists to get right: **gain is not sensitivity**. A bigger dish collects
more from a point source, but galactic HI fills the beam, and a beam-filling source gives
the same antenna temperature at *any* aperture. A 0.9 m horn and a 30 m dish see the same
~100 K line. Applying the point-source formula to HI is the most flattering mistake
available, so the tool routes by source type and says which formula it used.

**M3 (`v0.4.0`) — dish and feed system.** Efficiency stops being a number you type in. Give
a dish a feed and it computes illumination, spillover, and edge taper, and tells you which
term is hurting you. Feeds match to dishes in both directions, blockage comes from the
physical feed and struts, and the waveguide probe and backshort are designed properly — the
gap M2 named when it observed that a horn with no feed design is a nicely-shaped piece of
metal.

Two external anchors: the **−10.9 dB optimum edge taper emerges** from maximizing efficiency
rather than being assumed, for every feed shape tried; and the probe design **reproduces a
published, built 21 cm horn** to a third of a millimetre.

**M2 (`v0.3.0`) — fabrication.** A design becomes shapes you can cut: exact flat
developments, 1:1 printable templates tiled across ordinary paper, DXF for a laser, a cut
list with an honest kerf and material budget, assembly steps, and a `design.json` that ties
the shapes back to the prediction that produced them.

Every printed sheet carries a **100 mm ruler** and the instruction to measure it first. A
printer set to "fit to page" shrinks the drawing a few percent — invisible on screen,
invisible on paper, and ruinous once the metal is cut.

**M1 (`v0.2.0`) — the horn designer.** Horns are now real physics rather than an assumed
efficiency: exact aperture phase error (so the model correctly says an *over-flared horn
loses gain*), synthesis in both directions, realizability checking, and radiation patterns
computed by integrating the aperture field. Verified against Balanis' published worked
examples — which caught a 7% geometry bug in our own first attempt that every internal
consistency check had happily passed.

It also found that one of our own catalog entries is not a buildable horn: its source quotes
two different axial flare lengths because it optimized the E- and H-plane sectoral horns
independently. `jansky-forge show horn-18dbi-worked` reports it.

M0 (`v0.1.0`) laid the foundation and the catalog. Roadmap through M14 in
[`plans/jansky_forge.md`](plans/jansky_forge.md); `v1.0.0` is tagged only once an antenna has
been designed here, built from this tool's output, and measured back into it.

## License

MIT — see [LICENSE](LICENSE).

## AI use disclosure

This project is developed with [Claude Code](https://claude.com/claude-code) as a working
collaborator, under the same review standards as the sibling repos: every formula names its
source, every model states its validity limits, and the `antenna-physics-reviewer` agent reviews
diffs that touch the physics.
