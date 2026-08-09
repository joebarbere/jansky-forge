# Verification log

Every number in this project that was checked against something outside it. This is the
evidence behind "self-consistency is not verification" — and the first place to look when
you doubt a result.

**Reading the table:** "ours" is what the code computes; "reference" is the external number.
Where they disagree, the disagreement is deliberate and explained.

---

## Anchors that agree

| Quantity | Ours | Reference | Source |
|---|---|---|---|
| Half-wave dipole directivity | 2.1509 dBi | 2.15 dBi | Textbook; obtained by integrating our own pattern |
| Optimum pyramidal efficiency | 0.5144 | ~51% (Balanis uses 50%) | Balanis ch. 13 |
| Balanis Ex 13.5 — ρ_e / ρ_h | 6.1555 / 6.6002 | 6.1555 / 6.6000 | Balanis 3rd ed. p. 779 |
| Balanis Ex 13.5 — p_e = p_h | 5.4545 | 5.454 | " |
| Balanis Ex 13.5 — s / t | 0.1576 / 0.6302 | 0.1575 / 0.63 | " |
| Quantum limit at 21 cm (N4) | 0.0682 K | `hf/k` | Closed form |
| SAWbird+ H1 (N4) | 58.7 K | 0.8 dB NF | [Nooelec datasheet](https://www.nooelec.com/store/downloads/dl/file/id/97/product/322/sawbird_h1_datasheet_revision_1.pdf) |
| QPL9547 (N4) | 20.7 K | 0.3 dB NF @ 1.9 GHz | [Qorvo datasheet](https://www.mouser.com/datasheet/2/412/QPL9547_Data_Sheet-1854301.pdf) |
| Cryogenic InP HEMT (N4) | **3.5 K avg** over 0.3-14 GHz at 4 K | 3.5 K avg (2.2 K min, at 6 GHz) | [Chalmers 2018](https://research.chalmers.se/en/publication/520245) |
| NRAO 1980 / 2003 (N4) | 25 K @ 4.5 GHz / 2 K @ 4 GHz | as published | [NRAO CDL](https://science.nrao.edu/facilities/cdl/low-noise-amplifiers) |
| Pozar Ex 12.1 — K (N1) | 0.6071 | 0.607 | Pozar ch. 12 |
| Pozar Ex 12.1 — \|Δ\| (N1) | 0.6964 | 0.696 | " |
| Pozar Ex 12.1 — source circle (N1) | 1.132∠68.5°, R 0.199 | 1.132∠68.5°, R 0.199 | " |
| Pozar Ex 12.1 — load circle (N1) | 1.363∠46.7°, R 0.500 | 1.361∠47.0°, R 0.50 | " |
| \|Γin\| on the stability circle (N1) | 1.000000000 | 1 exactly | The definition, at 500 points |
| μ vs \|C_L\| − R_L (N1) | agree to 1e-9 | identity | Ties μ to the circles |
| K/Δ vs μ vs brute force (N1) | agree 4000/4000 | equivalent criteria | The definition, swept |
| Matched pad, all three gains (N0) | −3.0000 dB | −L exactly | Closed form |
| 3 dB + 2 dB cascaded (N0) | −5.0000 dB | −5 exactly | Closed form |
| S → ABCD → S round trip (N0) | 1.11e-16 | 0 | Machine precision |
| 3 dB passive loss → noise temp (N0) | 288.63 K | 288.63 K | M4's `loss_to_temperature_k`, independently |
| Balanis Ex 13.5 — D_p | 18.83 dB | 18.78 dB | " (book reads Fresnel tables by hand; ~0.1 dB is honest) |
| Balanis Ex 13.6 — a₁ / b₁ | 5.974 / 4.712 λ | 6.002 / 4.715 λ | Balanis p. 782 |
| Conical loss figure at s=3/8 | 2.912 dB | ~2.9 dB | Balanis (13-59b) |
| TE11 circular aperture efficiency | 0.8368 | 0.836 | Textbook, via independent integration |
| Optimum conical efficiency | 0.5176 | ~51% | Balanis p. 785 |
| **Optimum edge taper** | **−10.9 dB** | −10 to −11 dB | Reflector literature; *emerged*, never an input |
| Peak aperture efficiency | 0.82–0.85 | ~82–83% | " |
| Probe length (PhysicsOpenLab horn) | 52.8 mm | 52.5 mm | Published, built 21 cm horn |
| Backshort distance (same) | 76.4 mm | 76.4 mm | " |
| BHARAT sensitivity | 1.474e-4 K/Jy | 1.47e-4 K/Jy | arXiv:2208.06070, from its A_e alone |
| Cold sky at 1.4 GHz (model) | 3.41 K | 3.58 K measured | Testori et al. 2001 — gap kept, see below |
| 1 K/Jy collecting area | 2761.3 m² | 2761 m² | Condon & Ransom eq. 3.49 |
| SEFD, VLA 25 m form | 5.625 | 5.62 | NRAO VLA documentation |
| Radiometer equation | exact match | — | `jansky.signals`, independent implementation |
| Noise-figure conversion | exact match | — | `jansky.observing` |
| JOVE dipole gain (average ground, 10 ft) | 5.89 dBi | 5.8 dBi | NASA Radio JOVE manual v2.1 |
| JOVE element length | 23.24 ft | 23.28 ft | " |
| MoM half-wave dipole | 2.12 dBi, 69 Ω | 2.15 dBi, 73 Ω | pymininec vs textbook |
| W7ZOI 7-element Yagi (MoM) | 11.51 dBi | 11.6 dBi | BAA RAG published design |
| G4CQM 3-element Yagi (MoM) | 6.49 dBi | 6.75 dBi | " |
| Touchstone reader | exact match | — | scikit-rf reading the same file |
| Observation bundle schema | parsed | — | jansky-observe exporter, keys copied not invented |

---

## Disagreements kept on purpose

| Case | Ours | Published | Why it differs |
|---|---|---|---|
| PICTOR beamwidth | 9.85° | 8.95° | Illumination taper: implied beam constant ~63.6 vs our generic 70. Both inside the textbook 58–72 range |
| BHARAT gain (M0) | 19.46 dBi | 20.6 dBi | *Superseded* — M1's phase-error model gives 20.25, so most of the gap was M0's mismodelling, not dual-mode advantage |
| BHARAT gain (M1) | 20.25 dBi | 20.6 dBi | Residual ~0.35 dB is the genuine Potter dual-mode effect, which the single-mode model cannot represent |
| Itty Bitty beamwidth | 3.76° | 3.0° | An offset ellipse modelled as a circle of its quoted long axis |
| JOVE dual dipole (Tier 1) | 8.90 dBi | 7.8 dBi | Mutual coupling — invisible to pattern multiplication |
| JOVE dual dipole (Tier 2) | 2.75 dB stacking | ~2.0 dB implied | MoM recovers ~¼ of the gap; the rest, likely ground, is **still open** |
| 3-element Yagi (Tier 1) | 4.47 dBi | 6.75 dBi | Hansen-Woodyard assumes a *long* array; boom is 0.24λ. A test asserts the shortfall |
| Cold sky model | 3.41 K | 3.58 K measured | Inside the 408 MHz surveys' own 0.1–0.5 K zero-level uncertainty, plus an extragalactic term a single power law cannot carry. **Not tuned** |

---

## Errors that verification caught

| What | Wrong | Right | Consequence if unfound |
|---|---|---|---|
| Axial vs slant conversion (M1) | Used ρ_e where ρ₁ was meant | Similar-triangles form | **7% error** in every horn's phase-error denominator, invisible to all internal tests |
| Zenith atmosphere (v0.5.0) | 2.5 K | **2.0 K** | Every published Tsys half a kelvin pessimistic — *already released* |
| Cas A flux | ~1900 Jy | **1768 Jy @ 2016.0** | An early-2000s value quoted as current, on a source that fades |
| Tau A flux | 875 Jy, 0.15 %/yr | **829 Jy, 0.10 %/yr** | 5% flux error, 50% decline-rate error |
| Gain array index (M6) | `gain[...,0]` | `gain[...,2]` | Read one polarization; produced *impossible negative* Yagi gain |
| SWR by difference (M6 test) | `\|Z−50\|` | SWR ratio | 20 Ω and 80 Ω look equidistant; SWRs are 2.5 and 1.6 |
| Windows encoding (M0 CI) | cp1252 default | UTF-8 reconfigure | CLI crashed mid-output for every Windows user |
| Gain-collapse claim (N0 CLI) | "equal because the terminations are matched" | Equal only when the *device* is matched too | Printed three different numbers under a sentence saying they were equal |
| Upgrade ranking (N4) | Ceiling ranked against an achievable action | Rank actions only | Advised buying an impossible 0 K amplifier over replacing 0.5 dB of cable |
| `mu_load` docstring (N1) | "infinity for a unilateral device" | `1/\|S22\|`, finite | A test written from the docstring asserted the wrong value — the code was right |
| **`as_stage` loss definition (N0)** | Insertion loss, `\|S21\|²` | **Available loss, `1/G_A`** | **Factor of two** in the noise temperature of any mismatched passive network — 2320 K where 1160 K is right — and the gain wrong too, so it did not cancel |
| Noise-parameter Z0 (N0) | Assumed 50 Ω | The file's own Z0 | Rn is stored normalized, so every 75 Ω file's noise figure was mis-scaled |
| Unstable-device gain (N0) | Negative power ratio | Raise with the diagnosis | `math domain error` from the CLI, or a negative "gain" believed |
| `s_to_y` route (N0) | `inv(s_to_z(...))` | Direct `(I−S)(I+S)⁻¹/Z0` | LinAlgError on a series element, whose Y matrix exists |
| `is_reciprocal` tolerance (N0) | absolute 1e-9 | relative | Every *measured* cable labelled "non-reciprocal (active)" |
| Cascade grid check (N0) | `np.allclose` alone | Shape check first | `np.allclose` raises on mismatched shapes, so a NumPy broadcast error escaped ahead of the message explaining it |

---

## Corrections to widely-repeated claims

Things found to be wrong *in the literature or the community*, not in this code:

- **The Discovery Dish "65 cm / 1.69 GHz" spec** circulating online traces to no primary
  source and contradicts the vendor wiki. It is 700 mm, f/D 0.35.
- **KrakenRF publishes no gain, beamwidth, or surface-accuracy figure at all.**
- **BHARAT is a *conical* Potter horn**, not pyramidal — a pyramidal alternative appears only
  in its Appendix B.
- **The Haystack SRT has no canonical diameter.** Published tables say 2.1 m and 2.3 m with
  otherwise identical specs.
- **There is no "DSES horn" and no "ezRA horn."** ezRA is software. The real dimensioned
  community source is WVU RAIL/DSPIRA's foam-board mini horn.
- **The astronomy.me.uk "18 dBi horn" was never built** — it is calculator output, and as
  specified it is **not a realizable single horn** (its two axial flare lengths differ by 15%
  because the source equalized the *slants* instead).
- **The BAA meteor-antenna note contradicts itself**, quoting the same designs with two
  different gain/beamwidth pairs.
- **The Radio JOVE manual's beamwidth changed** between revisions (≈70° in 2025 v2.1, ≈60° in
  2022 v2.0 and 2012) for an identical configuration, unexplained.
- **Baars et al.'s 1977 fading law** (0.93 %/yr for Cas A at 1.4 GHz) is now known to
  overpredict the decline.

---

## Sources opened, not just cited (N4)

After the cryogenic entry turned out to be misattributed, every load-bearing catalogue figure
was checked by **opening its source** rather than trusting a search summary:

| Entry | Source opened | Agrees? |
|---|---|---|
| SAWbird+ H1 | [Nooelec product page](https://www.nooelec.com/store/sawbird-h1.html) | ✅ 0.8 dB standard / 1.05 dB Barebones, ≥40 dB, 65 MHz at 1.42 GHz |
| QPL9547 | [datasheet listing](https://www.rfglobalnet.com/doc/ghz-ultra-low-noise-lna-qpl9547-datasheet-0001) | ✅ 0.3 dB NF, 19.5 dB gain **at 1.9 GHz**, 0.1-6.0 GHz |
| Cryogenic InP HEMT | [Chalmers 2018](https://research.chalmers.se/en/publication/520245) | ✅ 3.5 K average, 0.3-14 GHz — after correcting a wrong citation |
| NRAO 1980 / 2003 | [NRAO CDL](https://science.nrao.edu/facilities/cdl/low-noise-amplifiers) | ✅ 25 K at 4.5 GHz, 2 K at 4 GHz |

**Not opened, and labelled accordingly:** the clock entries are order-of-magnitude figures for
a *technology class*, not a specific product, and every one of them now says so in its own
caveats. Digitizer entries carry vendor headline specs; their bit depths and tuning ranges are
uncontroversial and their noise figures are deliberately absent rather than guessed.

The datasheet PDFs for the SAWbird and the QPL9547 would not render as text, which is why the
catalogue links the readable product/listing pages instead — a source a reader cannot open is
not doing its job.

---

## Verification that runs in CI

Not a one-off check — these execute on every push, with the optional dependency installed so
they cannot silently skip:

- `jansky.signals` / `jansky.observing` cross-check (M4)
- `pymininec` Tier-2 validation, including both Yagi anchors (M6)
- `scikit-rf` Touchstone reader cross-check (M7 one-port, and N0 two-port including which
  index S21 lands in)
- N0's `as_stage` against a Thévenin analysis of a series resistor — first principles, no
  S-parameters involved
- N1's stability criteria against a brute-force sweep of the passive termination disk — the
  definition, not another formula
- `scikit-rf` on K and MSG (N1)
- `catalog.audit()` provenance check (M0), which fails the build on any output
