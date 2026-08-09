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

### "I swept it and it looked fine" is not a stability proof

Some devices have an unstable region a few **thousandths** of a Smith chart across, sitting
well inside the passive disk. A uniform 600 × 600 sweep — 360 000 terminations — steps
straight over it and reports the device safe, while `|Γin|` on that tiny circle is exactly 1.

Use the closed-form stability circles. Sampling can only miss an unstable region; it can
never invent one, so a clean sweep is weak evidence and a dirty one is proof.

### K > 1 is not the stability criterion

`K > 1` **and** `|Δ| < 1`, together. K alone is the classic misuse. Better still, use `μ`:
one number, `μ > 1` is exactly unconditional stability, and unlike K it is **comparable** —
of two devices the larger μ is more stable, and μ is literally the distance into the Smith
chart before you find a load that oscillates.

### MAG does not exist below K = 1

Maximum available gain is defined only for an unconditionally stable device. For `K < 1` the
relevant ceiling is MSG = `|S21/S12|`, and it applies only *after* the part has been
stabilised. Quoting MSG as if it were MAG is how a potentially unstable part gets a link
budget it cannot hold. `max_available_gain_db` raises rather than substituting.

### Check stability across the whole file, not at your frequency

A transistor has the most gain **below** the band you want to use it in, so the frequency
where it oscillates is usually one you were not thinking about. Worse, the vendor's sweep
often does not extend there at all — in which case the tool's silence is not reassurance.

### Friis wants **available** gain, not insertion loss

A passive network at 290 K has `F = 1/G_A`. `G_A` is the **available** gain, which is
`|S21|²/(1 − |S22|²)` for a matched source — not `|S21|²`. They coincide only when the
network is matched, and measured data never is.

A bare series 200 Ω in a 50 Ω system: `|S21|² = −9.54 dB`, `G_A = −6.99 dB`. Taking the first
gives **2320 K where the truth is 1160 K** — a factor of two, in the direction that makes
your receiver look worse than it is. And the gain is wrong too, so it does not cancel in the
cascade.

Sanity check with no S-parameters at all: Thévenin says a series 200 Ω fed from 50 Ω leaves
Voc unchanged and presents 250 Ω, so available gain is 50/250 = 1/5, `F = 5`, `Te = 1160 K`.

### Available gain depends on the source, so a chain must thread it

Evaluating every stage of a receiver at Γs = 0 and multiplying is **not** the chain's
available gain unless every interface is matched. The error is optimistic — it reports a
*lower* Tsys than the truth:

| Interface VSWR | Reported | True |
|---|---|---|
| 1.5 | 1160 K | 1740 K |
| 3.0 | 1160 K | 3480 K |

Use `twoport.as_stages()`, which threads each stage's Γout into the next. → `as_stage` alone
is for a single part on the bench.

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
