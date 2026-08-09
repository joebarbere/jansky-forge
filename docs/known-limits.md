# Known limits

What this tool does **not** do, and where its numbers stop being trustworthy. Kept here so a
gap is a documented decision rather than a surprise.

---

## Not modelled at all

| Thing | Status |
|---|---|
| Helical antennas | Not modelled. M5's plan row listed them; they did not ship |
| Log-periodic (LPDA) | Not modelled |
| Moxon | Not modelled |
| Offset-fed dish geometry | Only the blockage advantage is mentioned; the geometry is not modelled |
| Waveguide components, filters, diplexers | Out of scope |
| Interferometers, arrays with uv coverage | Post-1.0 candidate |
| Phased arrays and beamforming | Post-1.0 candidate |
| Cryogenic / detailed LNA noise modelling | Post-1.0 candidate |

---

## Modelled, with a stated gap

### Receiver design stops at "choose and verify"

The receiver track (N0–N5) reads a part's data, checks it, and integrates it into the system
budget. It does **not** do bias-network design, PCB layout, thermal design, or EM
co-simulation, and it never will — those are a different discipline with their own depth.

Nothing here gets you from this tool to a working 1.4 GHz board without a VNA. Ideal
component values are not a design at that frequency: layout parasitics, ground vias and
package effects decide whether you get them.

### Conical horn patterns — deferred twice

Conical **gain** is exact (Balanis's loss figure, cross-checked against an independent
aperture integration that reproduces the Fresnel result to 0.000 dB). Conical **beamwidths**
are still the optimum-flare rules of thumb, so they do not track a badly-flared design.

`feeds.conical_horn_feed()` is the usable stopgap and its docstring says plainly that it
stacks two approximations. Doing it properly needs the circular-aperture TE11 far field.

### Yagi elements — boom length only

`wires.YagiUda` models what boom length buys. Element lengths and spacings are what a
method-of-moments solver is for → use `mom` (M6). The estimate is **±2 dB** and known to
understate short booms (2.3 dB low at 0.24λ).

### Horn feeds on dishes assume rotational symmetry

A horn's pattern is not rotationally symmetric; the reflector integrals assume it is.
`feeds.HornFeed` uses the **geometric mean** of the two principal planes, which is exact only
where they agree. Surfaced in the notes of every result it touches.

### Array gain assumes ideal elements

`wires.DipoleOverGround` with `n_elements > 1` applies `10·log₁₀(n)`, which is a **ceiling**.
Real elements couple: NASA's JOVE figures show ~1 dB of shortfall for two, and Tier-2 MoM
recovers about a quarter of it. Use `mom.dipole_array_model()` when coupling matters.

### Ground model assumes radiated power is unchanged

`wires.ground_gain_db()` is exact for a perfect conductor and slightly **optimistic** over
lossy earth, where some power is absorbed rather than reflected. It is the approximation that
reproduces NASA's published figure, and the residual is smaller than anyone's uncertainty in
their own soil.

### MININEC's ground model is its weak point

Tier-2 results over ground deserve more caution than free-space ones. Stated in the result
notes rather than left to folklore.

---

## Validity limits by regime

| Model | Breaks down when |
|---|---|
| Dish aperture theory | Below ~5λ diameter (the 700 mm Discovery Dish is 3.3λ at 21 cm — the warning fires, correctly) |
| Horn aperture relations | Smallest aperture dimension below ~1λ |
| Conical loss-figure fit | Phase deviation above ~0.8 (the cubic misbehaves; beyond ~1.4 it returns negative loss) |
| Hansen-Woodyard endfire | Boom below ~0.75λ |
| Thin-wire MoM | Wire radius exceeding segment length; fewer than 10 segments per wavelength |
| Waveguide single-mode | Outside `a < λ₀ < 2a` |

---

## Data the tool deliberately does not ship

**Transistor and amplifier data.** No Fmin, Γopt, Rn or S-parameters for any real part.
These come from a vendor's `.s2p` or they are absent — the same judgement as the cable-loss
table below, and for the same reason: an invented noise parameter inside a noise budget is an
invented noise budget. `twoport` reads any part you have data for and knows nothing about one
you do not.

**A cable-loss table.** Coax specifications vary between manufacturers, and between the
drum's label and the cable on it. A table of invented losses inside a noise budget would be
an invented noise budget. Supply your own datasheet figure.

**A galactic-centre continuum temperature.** Only a lower bound (>50 K at 1.4 GHz) could be
obtained from a citable source.

**Baars et al. (1977) polynomial coefficients.** The ADS scan is image-only and would not
OCR. Perley & Butler (2017) and Trotter (2017) supersede it for these sources anyway.

**Quiet-Sun solar-cycle amplitude at 1.4 GHz specifically.** Only 1 GHz multi-cycle data
exists, so the quoted 2–4× range is flagged as inferred.

---

## Things that are model output, not measurement

Everything from M0–M6 is **predicted**. It is only a measurement once it has been through
`measure` (VNA) or `onsky` (sky), and those keep prediction and measurement in separate
fields with nothing combining them.

In particular: **every efficiency before M8 is assumed, computed, or bounded.** Only a
transit measurement observes one.

---

## Open questions carried in the plan

1. Does the horn designer generate 3D-printable feed geometry, or stay sheet-metal only?
2. Is the first real build a 21 cm test horn? (It is the natural v1.0.0 gate.)
3. Catalogue contribution flow: PR-only, or a data file others can extend?
