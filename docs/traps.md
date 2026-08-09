# Traps

Mistakes that produce a **confident, plausible, wrong** answer. Every one of these was hit
or guarded against while building this tool. They are ordered by how expensive they are.

---

## Physics traps

### Gain is not sensitivity

**The trap.** Applying the point-source formula `T_A = S·A_e/2k` to extended emission. It
makes a bigger dish look like more signal, which is the most flattering possible error.

**The truth.** Galactic HI *fills the beam*. For a beam-filling source the antenna
temperature equals the source brightness temperature **regardless of aperture** — a 0.9 m
horn and a 30 m dish see the same ~100 K line. The big dish buys angular resolution and
point-source sensitivity; it does not buy a stronger line.

**Guard.** `sensitivity.detect()` routes by source type and states which formula it used.

---

### The catalogue brightness is not what you will measure

**The trap.** Reading "inner galactic plane: 113 K" off a survey and expecting to measure it.

**The truth.** Survey brightness temperatures come from **16–36 arcmin beams**. An amateur
beam is *degrees* wide and reads the **average** over that patch, which is lower wherever
the emission is structured. The aperture-independence above still holds; the number does not.

**Fix.** Convolve a survey map (HI4PI, LAB) with your own beam for an honest expectation.

---

### A flux without an epoch is a half-truth

**The trap.** Quoting Cas A at "about 1900 Jy" — a value from the early 2000s, still widely
repeated.

**The truth.** Cas A is **1768 Jy at epoch 2016.0**, and it fades. Worse, it fades
*non-uniformly*: 0.67 %/yr long-term average, ~0.8 %/yr recently, with the rate change
detected at 6.3σ. Any single rate is a fiction over a long baseline.

| Source | 1.4 GHz | Behaviour |
|---|---|---|
| Cas A | 1768 Jy @ 2016.0 | Fades ~0.67 %/yr, non-uniformly |
| Cyg A | 1580 Jy | **Stable** — the best amateur L-band standard |
| Tau A | 829 Jy @ 2016.0 | Fades 0.10 ± 0.04 %/yr; strongly polarized |
| Vir A | 212 Jy | Stable; largest at 14–16′ |
| Quiet Sun | ~5.5×10⁵ Jy | ±15%, varies 2–4× over the cycle |

---

### The factor of two is a *polarization* factor, and it is conditional

`T_A = S·A_e/(2k)` — the 2 is there because a single antenna responds to one polarization and
an unpolarized source splits its power evenly. It **would not belong** for a matched
polarized transmitter. The commonest factor-of-two error in the amateur literature.

---

### Y-factor is ill-conditioned near unity

**The trap.** Trusting a 1 dB Y-factor.

**The truth.** Tsys comes from a *difference of nearly-equal quantities*, so sensitivity to
error explodes as the ratio approaches 1.

| Y-factor | Tsys (290 K / 6 K) | Error per 0.1 dB |
|---|---|---|
| 1 dB | 1091 K | > 100 K |
| 3 dB | 279 K | ~20 K |
| 6 dB | ~110 K | a few K |

**Fix.** Make the hot and cold pointings as different as you can. `onsky.y_factor_tsys()`
reports the sensitivity and labels a weak result an *upper bound*.

---

### Loss before the LNA is ruinous; after it is nearly free

The Friis cascade divides each stage's noise by the gain ahead of it. Same chain, one change:

| Configuration | Receiver noise |
|---|---|
| LNA → 3 dB coax → backend | **45 K** |
| 3 dB coax → LNA → backend | **334 K** |

This is the entire argument for a mast-head amplifier, in one table.

---

### Spillover sees 290 K of warm ground

Feed power that misses the dish does not merely vanish — it looks at the earth. On a
prime-focus feed that is the difference between a receiver-limited system and a
spillover-limited one, and a better-matched feed is usually cheaper than a better LNA.

---

### Perfect ground is not a place

A horizontal dipole over a **perfect** conductor gains +6.02 dB. Over real earth at 20 MHz:

| Ground | Gain at 10 ft |
|---|---|
| Perfect conductor | +6.02 dB |
| Seawater | +5.6 dB |
| Average soil | **+3.7 dB** |
| Dry sand | +2.7 dB |

Assuming perfect ground overstates a JOVE dipole by 2.4 dB. That gap is soil, not a bug.

---

## Arithmetic and convention traps

### Mismatch is a **ratio**, not a difference

20 Ω and 80 Ω are nearly equidistant from 50 Ω *by subtraction*, and have SWRs of **2.5 and
1.6**. Judging a match by `|Z − 50|` is wrong. (Caught in this project's own test.)

### Half of a dB value is not the half-power point

A drift scan needs **linear** power. Taking half of a dB trace makes the beam look far
narrower than it is. `onsky.drift_scan_beamwidth()` rejects dB input outright.

### Averaging spectra in dB is wrong

And wrong in the direction that makes quiet data look *better*. Convert to linear, average,
convert back.

### Axial is not slant

Balanis's `ρ_e`/`ρ_h` are **slant** distances; `ρ₁`/`ρ₂` are **axial**; `p_e`/`p_h` are the
axial flare lengths a builder measures. Reading one where another is meant is a **7% error**
that no internal consistency check catches. → [Lessons learned](lessons-learned.md)

### Probe length and backshort distance are different quarter-waves

- Probe = **free-space** λ/4
- Backshort = **guide** λ/4, where `λ_g = λ₀/√(1 − (λ₀/2a)²)`

At 21 cm in WR-650 they differ by **16 mm** — enough to ruin a match.

### Touchstone two-port data is ordered `S11 S21 S12 S22`

**S21 comes before S12** — the historical exception to row-major ordering, and it applies to
two-port files only. Reading a `.s2p` the obvious way transposes the device:

- For a **reciprocal** network (any passive one) `S12 = S21`, so the bug is *invisible*.
- For an **amplifier** it reports the reverse isolation as the gain. In this project's test
  file that is a **60 dB error** that still looks like a number you might believe.

Smoke alarm: `TwoPort.is_reciprocal`. An amplifier that reads reciprocal has almost certainly
been read wrong.

### Matched terminations are not enough for the three gains to agree

Transducer, available and operating gain are three different numbers. With `Γs = ΓL = 0`:

    G_T = |S21|²        G_A = |S21|²/(1 − |S22|²)        G_P = |S21|²/(1 − |S11|²)

They collapse to `|S21|²` only when the **device** is matched too — true of an ideal
attenuator, false of every real amplifier. Say which gain you mean. Noise-figure calculations
want **available** gain specifically.

### Polarization components are not the total

A solver's gain array may hold `[component_1, component_2, total]`. Reading index 0 returns
one polarization. On a horizontally-polarized Yagi this showed up as a physically
**impossible negative peak gain**.

---

## Fabrication and bench traps

### "Fit to page" silently ruins a template

A printer set to fit shrinks the drawing a few percent. Invisible on screen, invisible on
paper, ruinous once the metal is cut. **Every sheet this tool prints carries a 100 mm ruler.
Measure it before cutting anything.**

### The VNA measures at *its* port, not at your antenna

At VHF half a metre of coax rotates S11 most of the way round the Smith chart. Most
"the model disagrees with reality" reports are an un-de-embedded cable.
→ `measure.shift_reference_plane()`

### Kerf applied twice

Hand tools are guided to one side of the line; lasers and waterjets compensate in software.
Doing both offsets the part twice. This tool **reports** kerf and never silently applies it.

### Seam allowance is perpendicular, not horizontal

Offsetting a sloped edge by `s` moves it horizontally by `s/cos α`. On a steeply flared horn
the naive version leaves the flange narrow — and you find out after cutting.

### Two axial lengths means it is not one horn

A pyramidal horn is a single frustum, so `p_e = p_h`. A published design quoting two
different axial flare lengths cannot be built as specified. **This tool's own catalogue
contains such an entry** (`horn-18dbi-worked`, 15% mismatch) — its source equalized the
*slants* instead of the *axial lengths*.

---

## Diagnosing a disagreement

| Symptom | Usual cause |
|---|---|
| Reactance off, resistance agrees | Length error, or un-de-embedded cable |
| Resistance off | Loss, ground proximity, nearby metal the model doesn't know about |
| Resonance low | Element too long — shorten by the same fractional amount |
| Measured beam much **wider** | Pointing drift during the scan, or a resolved source |
| Measured beam much **narrower** | Baseline taken on-source (beams are rarely better than modelled) |
| Aperture efficiency > 1 | Calibration wrong, or source resolved. Not a magic dish |
| Array gain below ideal | Mutual coupling — real, and invisible to pattern multiplication |
