---
name: design-antenna
description: The design copilot — turn a science goal ("I want to see the hydrogen line from a city rooftop") into a concrete antenna design, starting from a catalog template and showing the reasoning at every step. Use whenever someone asks what antenna they should build or whether a design will work.
---

# Design an antenna for a science goal

The job is not to print a number. It is to get from *what the person wants to observe* to *a
design they could build*, with the reasoning visible so they can disagree with it.

## 1. Pin the science goal first

Before touching geometry, establish — asking only if it is genuinely unknowable from context:

- **What signal?** A spectral line (which one — `jansky-forge bands` lists them), continuum
  (which sources), or a beacon (JOVE, meteor scatter)?
- **What outcome counts as success?** "See the HI peak at SNR 5" is a design constraint;
  "do radio astronomy" is not. Push gently for the former.
- **What constraints are real?** Physical size, portability, budget, HOA/roof/landlord, whether
  it has to survive weather, what tools and materials they have.
- **What do they already own?** The Discovery Dish, an LNB, surplus mesh — an existing part is
  usually the strongest constraint and the best starting point.

## 2. Start from the catalog, always

```bash
uv run jansky-forge list --band hi
uv run jansky-forge show <slug>
```

Pick the closest existing build and say *why* it is the closest. Starting from a known,
sourced design and perturbing it is more honest and more instructive than synthesizing from
scratch — and the catalog entry's caveats are inherited context the user should see.

If nothing in the catalog is close, say so explicitly rather than forcing a bad fit.

## 3. Perturb, and show the physics

Change one dimension at a time and show what moved:

```bash
uv run jansky-forge characterize <slug> --band hi --freq-mhz 1612
```

For custom geometry, work in Python against the library (`ParabolicDish`, `PyramidalHorn`,
`ConicalHorn`) rather than inventing CLI flags. Explain the trade in physical terms:

- **Gain scales as D²; beamwidth as 1/D.** Doubling a dish is +6 dB and halves the beam.
- **A narrower beam is not free** — it needs better pointing, and for extended emission like
  galactic HI it changes what you are even measuring.
- **Surface accuracy matters as σ/λ.** Ruze loss is why mesh is fine at 21 cm and useless at
  10 GHz. Quote the model's own `ruze_loss_db`.
- **Efficiency is a budget, not a constant.** Illumination, spillover, blockage, surface —
  name which term dominates, because that is the one worth fixing.

## 4. State what the model cannot tell them

Every `Characterization` carries `notes` — **print them**. Beyond those, be explicit that
until M4 this tool reports antenna performance, not system sensitivity: gain is not SNR, and
whether they will actually see the line depends on Tsys, bandwidth, integration time, and the
local RFI environment. Point at `jansky-observe` for the observing side.

Never let an enthusiastic design conversation imply a detection that the numbers do not
support. Underpromising here is the house standard.

## 5. Land somewhere concrete

End with: the recommended design's dimensions, its predicted gain/beamwidth/efficiency, the
catalog entry it descends from, the one thing most likely to go wrong in the build, and the
honest next step. If the honest next step is "measure your RFI environment before buying
anything", say that.
