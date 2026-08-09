# Rules of thumb

Numbers worth carrying in your head, with the conditions under which they hold. Where a rule
has a validity limit, it is stated — a rule of thumb applied outside its range is just a
wrong number said confidently.

---

## Apertures (dishes and horns)

| Quantity | Rule | Conditions |
|---|---|---|
| Dish gain | `G = η(πD/λ)²` | Aperture ≳ 5λ across; below ~3λ it overstates |
| Dish beamwidth | `HPBW ≈ 70·λ/D` degrees | Textbook range is 58 (uniform) to 72 (heavy taper) |
| Effective area | `A_e = Gλ²/4π` | Always — this is the reciprocity identity, not an approximation |
| Gain scaling | Double the diameter = **+6 dB**, half the beamwidth | |
| Ruze surface loss | `η_s = exp(−(4πσ/λ)²)` | σ = RMS surface error |
| Focal geometry | `θ₀ = 2·arctan(1/(4·f/D))` | Rim half-angle seen from the feed |

**Ruze in practice:** 2 mm RMS costs 0.06 dB at 21 cm and **3.0 dB at 10 GHz**. This is why
mesh is fine for hydrogen and useless for Ku band.

### Optimum horn flare

| Plane | Condition | Phase deviation |
|---|---|---|
| E-plane | `b₁ = √(2λρ₁)` | s = 1/4 |
| H-plane | `a₁ = √(3λρ₂)` | t = 3/8 |
| Conical | `d = √(3λl)` (l = **slant**) | s = 3/8 |

**Aperture efficiency at optimum: 51%** (0.5144 computed exactly for pyramidal, 0.51 for
conical). Beyond the optimum, gain *falls* — aperture phase error grows faster than area.

### Optimum-horn beamwidths

| Plane | Approximation |
|---|---|
| Pyramidal E | `54·λ/b₁` degrees |
| Pyramidal H | `78·λ/a₁` degrees |
| Conical E / H | `60·λ/d` / `70·λ/d` degrees |

Valid at optimum flare only. Agreement with the exact pattern integration is 1–3%.

---

## Feeds and illumination

| Quantity | Rule |
|---|---|
| **Optimum edge taper** | **−10.9 dB**, near-independent of feed shape |
| Peak aperture efficiency | 0.82–0.85 (illumination × spillover) |
| Space attenuation | `40·log₁₀(cos(θ₀/2))` dB — the rim is further than the vertex |
| Central blockage | `η = (1 − (d/D)²)²` — loss goes as the **square** of blocked area |
| Mesh reflector | Openings below **λ/10** leak negligibly |

The invariance of the −10.9 dB optimum across an eightfold range of feed directivity is
exactly why the rule of thumb deserves trust.

**Deep dishes want wide feeds.** f/D 0.35 wants ~108° beamwidth; f/D 0.7 wants ~45°.

---

## Waveguide and probes

| Quantity | Formula |
|---|---|
| TE10 cutoff | `λ_c = 2a` |
| Guide wavelength | `λ_g = λ₀/√(1 − (λ₀/λ_c)²)` |
| Probe length | `λ₀/4` (free space) |
| Backshort distance | `λ_g/4` (**guide**, not free space) |
| Single-mode range | `a < λ₀ < 2a` |

**WR-650 at 1420 MHz:** cutoff 908 MHz, λ_g = 274 mm, probe 52.8 mm, backshort 68.6 mm.

---

## Wire antennas

| Quantity | Value |
|---|---|
| Half-wave dipole directivity | **2.15 dBi** (1.64) |
| Radiation resistance | 73 Ω |
| Physical length | ~0.95 × λ/2 (end effects) |
| Folded dipole | Same pattern, **4×** the impedance (≈292 Ω) |
| Ground reflection ceiling | **+6.02 dB** (perfect conductor) |
| Ideal broadside array | `10·log₁₀(n)` — a ceiling; coupling always costs |

### Ground types at HF

| Ground | εr | σ (S/m) |
|---|---|---|
| Seawater | 81 | 5.0 |
| Average soil | 13 | 0.005 |
| Poor / dry sandy | 5 | 0.001 |

**Height steers the beam.** A horizontal dipole works with its own *inverted* image: low puts
the lobe overhead, higher drops it toward the horizon. At 20 MHz over average ground —
10 ft → zenith, 15 ft → 48°, 20 ft → 35°.

### Yagi

`D ≈ 1.789 × 4L/λ` (Hansen-Woodyard endfire) × 1.64 for dipole elements. **Assumes a long
array** — good to 0.4 dB at 1.1λ boom, ~2.3 dB low at 0.24λ. For sizing a mast, not cutting
elements; that needs a method-of-moments solve.

---

## Sensitivity

| Quantity | Formula |
|---|---|
| Sensitivity | `A_e/(2k)` K/Jy — also called DPFU |
| **1 K/Jy** | **2761 m²** of collecting area |
| SEFD | `2k·Tsys/A_e` |
| G/T | `gain_dBi − 10·log₁₀(Tsys)` |
| Radiometer | `ΔT = Tsys/√(n_pol·B·τ)` |
| Time to detect | `τ = (SNR·Tsys/T_signal)²/(n_pol·B)` |

**Sensitivity improves as √t.** Twice as good costs four times the integration — which is
why "just integrate longer" eventually stops being an answer.

**Switched/Dicke measurement costs a factor of 2** in sensitivity, bought for immunity to
gain drift. On an amateur system that trade is usually worth it.

### Sky and noise

| Term | L band (1.4 GHz) |
|---|---|
| CMB | 2.725 K |
| Galactic (cold patch) | ~0.85 K |
| **Measured cold sky** | **3.58 K** (Testori et al. 2001) |
| Zenith atmosphere | ~2.0 K |
| Ground (spillover sees this) | 290 K |

Galactic synchrotron scales as **ν^−2.7** — which is why 21 cm is quiet and the Radio JOVE
band at 20 MHz is not (>1000 K).

**Noise figure to temperature:** `T = 290·(10^(NF/10) − 1)`. A 0.3 dB LNA is 21 K; a 3 dB one
is 290 K.

---

## Two-port networks and receivers

| Quantity | Formula |
|---|---|
| Transducer gain, matched terminations | `\|S21\|²` |
| Available gain, `Γs = 0` | `\|S21\|²/(1 − \|S22\|²)` |
| Operating gain, `ΓL = 0` | `\|S21\|²/(1 − \|S11\|²)` |
| Passive network noise temperature | `T = (L − 1)·290 K`, `L = 1/G_A` the **available** loss |
| Noise figure vs source match | `F = Fmin + (4·Rn/Z0)·\|Γs − Γopt\|²/((1 − \|Γs\|²)·\|1 + Γopt\|²)` |
| SWR from reflection coefficient | `(1 + \|Γ\|)/(1 − \|Γ\|)` |

**A passive network's noise figure equals its loss**, in dB — 3 dB of loss is a 3 dB noise
figure and 288.6 K. That single fact is why loss ahead of the LNA is ruinous.

**But "its loss" means available loss, `1/G_A`, not `|S21|²`.** Those agree only for a
matched network. On a mismatched one the difference is a factor of two in the wrong
direction. → [Traps](traps.md)

**Ask for the gain you mean.** Noise-figure work wants **available** gain specifically.

**The best noise match is not the best power match.** Γopt is generally not the conjugate
match, so minimum noise figure and maximum gain want different source impedances. Choosing
between them is what LNA design *is*; a tool that silently optimises one is hiding the
decision.

**A quiet rule of thumb for whether to bother:** halving a 36 K receiver saves 18 K. If
spillover is costing you 21 K, fix the feed first. Compare terms before buying parts.

---

## On-sky

| Quantity | Rule |
|---|---|
| Y-factor | `Tsys = (T_hot − Y·T_cold)/(Y − 1)` |
| Sidereal drift rate | `15·cos(dec)` degrees/hour |
| Transit area | `A_e = 2k·ΔT/S` |

**Drift-scan duration:** a 21° beam takes 1.4 h at the equator, 2.8 h at dec +60, and **8 h**
at dec +80 — and the receiver must be gain-stable for all of it.

---

## Fabrication

| Quantity | Value |
|---|---|
| Pyramidal panel height (E) | `√(L² + ((b₁−b)/2)²)` |
| Pyramidal panel height (H) | `√(L² + ((a₁−a)/2)²)` |
| Corner edge | `√(L² + ((a₁−a)/2)² + ((b₁−b)/2)²)` — **must match on both panels** |
| Cone sector angle | `2π·R/slant` radians |
| Seam allowance offset | `s/cos α` horizontally, for a slope at α from vertical |
| Nesting waste | Budget 1.5–2× part area in stock for trapezoids |

**Typical kerf:** shears 0 mm (displaces), laser 0.2 mm, waterjet 0.8 mm, bandsaw 1.0 mm,
jigsaw/plasma 1.5 mm, **nibbler 5 mm**.

**Material thickness** matters when it exceeds ~1% of a wavelength. At 21 cm, 1 mm sheet is
0.5% — negligible. At 10 GHz the same sheet is 3.3% — compensate.

---

## Method of moments

| Guidance | Value |
|---|---|
| Segments per wavelength | **≥ 10**, 20 is comfortable |
| Segment length vs radius | Segment must be longer than the wire radius |
| Feed segment | Use an **odd** segment count so a centre lands on the feed |

Matrix solve cost grows as the **cube** of segment count. More is not free.
