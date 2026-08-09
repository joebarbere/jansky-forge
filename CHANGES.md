# Changelog

All notable changes to jansky-forge. Pre-1.0 semver: **minor = milestone, patch = fixes
between milestones** (see `plans/jansky_forge.md` §5).

## [Unreleased]

## [0.10.0] — M9, Interactive UI, and the documentation

Everything before this was correct. This is the milestone that makes it *pleasant*, which
matters more than it sounds: a design tool you enjoy poking is a design tool you learn from.

### Added
- **A web UI** (`jansky-forge serve`, optional extra `[ui]`): catalogue browser with full
  provenance, a slider-driven horn designer that recomputes live, server-rendered SVG
  patterns, and feed matching.
- **`docs/`** — everything learned across nine milestones, organised so it is findable:
  traps, rules of thumb, workflows, lessons learned, known limits, the verification log, and
  the honesty invariants.

### Three deliberate departures from the plan's sketch
The plan said "FastAPI + htmx + a canvas module". What shipped is FastAPI, about thirty lines
of inline vanilla JavaScript, and server-rendered SVG:

- **No htmx and no charting library.** Synthesis takes 0.12 ms, so an HTTP round trip is
  dominated by the network — there is nothing for a client-side renderer to accelerate.
- **No CDN, no build step.** The tool works on a laptop in a field with no signal, which is
  where antennas get built. A test asserts no page references anything external.
- **SVG, not matplotlib.** M2 already writes SVG; adding a rendering dependency for a line
  and an axis would be a poor trade.

### The rule the UI inherits
**A model's caveats are displayed, not hidden for tidiness.** A polished interface is the most
tempting place to drop them, precisely because a designed-looking number is more readily
believed. Tests assert that the Discovery Dish page shows both the vendor's missing-gain
caveat and the model's electrically-small warning, and that the JSON API carries them too.

### Found while building the UI
Asking for 30 dBi at the Radio JOVE band returns a **205-metre aperture** — geometrically
valid, practically absurd. Synthesis is bounded by physics, which is a long way past bounded
by sense. Both design types now carry buildability notes, and because the *model* carries
them rather than the presenter, the CLI gained the warning too.


## [0.9.0] — M8, On-sky characterization

M7 read a vector network analyser, which tells you whether the antenna is *matched*. A
matched antenna can still be pointing at your neighbour's shed. M8 reads what the sky put
through it — and it is the first milestone whose numbers are not derived from geometry at all.

### The cross-repo contract, honoured
`read_bundle()` consumes `jansky-observe`'s codified observation bundle
(`jansky-observe.observation-bundle/1`) — zip or unpacked. The manifest keys and npz array
names are copied from that repo's exporter, and the schema identifier is **checked, not
assumed**: an upstream format change breaks loudly here rather than silently mis-reading.
That contract was written into this project's plan at M0 and is now real.

### Three measurements
- **Y-factor system temperature**, straight from a bundle's `cold_sky` and `hot_ground`
  captures — the station already labels them, so this needs no configuration.
- **Drift-scan beamwidth**: stop the dish, let the sky rotate a source through the beam, and
  the power-versus-time trace *is* the beam once time becomes angle at 15·cos(dec) deg/hour.
  It is the only beam measurement an amateur can make without a rotator or a test range.
- **Transit aperture efficiency**: M4's sensitivity relation run backwards, turning a
  temperature rise against a known flux into collecting area. **This is the efficiency every
  earlier milestone could only assume, computed, or bound.**

### The traps it flags, with numbers
- **Y-factor is ill-conditioned near unity.** Tsys comes from a difference of nearly-equal
  quantities, so at a 1 dB ratio a tenth of a decibel moves the answer by over a hundred
  kelvin, while at 6 dB it is worth a few. Every result reports that sensitivity, and a weak
  Y-factor is labelled an upper bound rather than a number.
- **A drift scan needs linear power, not dB.** Half of a dB value is not the half-power
  point, and the mistake makes a beam look far narrower than it is — so dB input is rejected
  outright rather than quietly accepted.
- **Averaging spectra in dB is wrong**, and wrong in a direction that flatters quiet data, so
  band averaging converts to linear first.
- An aperture efficiency above 1 is reported as impossible rather than printed.

### Measured still never merges with predicted
`BeamComparison` keeps the model's beamwidth and the sky's in separate fields with nothing
combining them, and a test asserts no merged field can be added — the same structural rule
M7 established. It also diagnoses: a measured beam much wider than predicted is usually
pointing drift or a resolved source, and one much narrower usually means the baseline was
taken on-source.


## [0.8.0] — M7, Measurement ingest

Every milestone so far produced a *prediction*. This one reads what a vector network
analyser says about metal you actually built.

### The invariant, made structural
"Predicted and measured never wear the same label" has been honesty invariant 5 since M0.
Here it stops being a slogan: `Comparison` has a `predicted_impedance_ohm` field and a
`measured_impedance_ohm` field **and no third field combining them**. No corrected value, no
blended estimate, no efficiency fitted to close the gap. A test asserts that no such field
exists, so adding one later fails the suite — which is the point. If you want a single
number you must choose which, and defend the choice.

### Added
- **Native Touchstone reading.** A `.s1p` is a header and three columns, and every NanoVNA
  and LiteVNA writes one, so parsing it needs no dependency. All three data formats (RI, MA,
  DB) and all four frequency units. Where `scikit-rf` is installed the test suite checks the
  two readers agree — CI installs it so that runs rather than skipping.
- **Reference-plane shifting**, which is the gotcha this module exists for. A VNA measures at
  *its* port, and at VHF half a metre of coax rotates S11 most of the way round the Smith
  chart. Ignoring it is the commonest reason a measurement "disagrees" with a model that was
  in fact right.
- **Diagnosis, not just numbers.** Reactance off while resistance agrees is a length error or
  an un-de-embedded cable; resistance off is loss, ground, or something nearby the model does
  not know about. `resonance_offset()` turns "resonant 2% low" into "shorten it by 2%", which
  is the most actionable single number a VNA gives an antenna builder.
- **L-network matching**, verified by *applying* the network to the load and checking a VNA
  would see 50 ohms — re-deriving the design algebra would prove nothing. Loaded Q is
  reported, and a sharp match says so.
- **Cable loss** scaled from one datasheet figure by the square root of frequency, joined
  back to M4: loss ahead of the LNA becomes kelvins of system temperature, loss after it is
  nearly free.

### Why no built-in cable table
Coax specifications vary between manufacturers, and between the drum's label and the cable on
it. A table of invented losses inside a noise budget would be an invented noise budget, so
you supply the number from your own datasheet.

### The toolchain now closes
M6 predicts a feed impedance; M7 reads a measured one; the comparison says which is which and
what the difference means. An end-to-end test synthesizes an antenna cut 2% long seen through
half a metre of coax — the two commonest real discrepancies at once — and the tool separates
them: de-embed the cable, then be told to shorten the element by 2%.


## [0.7.0] — M6, Tier-2 method-of-moments validation

The button that says *check that*. Everything before this is closed form; this solves the
same antenna numerically, with a code that does not assume the flare is optimum, does not
assume elements are uncoupled, and does not care what a textbook approximation was fitted to.

### It closed both tickets M5 wrote
- **The short-boom Yagi.** M5's endfire bound read **4.47 dBi** against a published 6.75 and
  said plainly it would understate a short array. Tier 2 gives **6.49 dBi** — within 0.26 dB
  of the published figure. That gap is the entire justification for having a second tier, and
  it is now closed.
- **The JOVE mutual coupling.** M5 overshot because pattern multiplication treats array
  elements as independent. Tier 2 shows two dipoles stacking by **2.75 dB rather than the
  ideal 3.01**, with the feed impedance shifting 17 ohms when the neighbour appears — the
  coupling made directly visible rather than inferred. This is an *honest partial*
  resolution: NASA's published pair implies about 2.0 dB, so the numerics recover roughly a
  quarter of the discrepancy and the rest, probably ground interaction, is still open.

### Added
- `jansky_forge.mom`: a backend-neutral `WireModel`, the `MomBackend` protocol, and a
  `pymininec` backend — pure Python, MIT, installs with no compiler on every platform.
- **Feed impedance**, which Tier 1 structurally cannot produce. The 7-element GRAVES Yagi
  comes out at 20 − 25j ohms, which is precisely why the published design uses a *folded*
  driven element: four times that lands near 50.
- Model builders for dipoles, arrays and Yagis **from real element geometry** — the tables
  M5 recorded and could not use are now in `GRAVES_3EL_ELEMENTS` / `GRAVES_7EL_ELEMENTS`.
- `to_nec_deck()`: NEC2 input as an **export**, not a linked solver. Same reasoning as M2
  generating openEMS scripts — rigor without the GPL entanglement.
- `check_segmentation()`, because too few segments per wavelength is the MoM mistake that
  quietly produces a confident wrong answer.

### Verified against
- A half-wave dipole: **2.12 dBi and 69 ohms** against the textbook 2.15 and 73.
- Reactance sign versus element length — short is capacitive, long is inductive — which is
  the check that the solver is really solving rather than returning a plausible constant.
- The 7-element GRAVES Yagi: **11.51 dBi** against a published 11.6.

### Optional, and genuinely tested
Tier 2 is `pip install jansky-forge[mom]`. Tier 1 is unchanged without it. The tests skip
when the backend is absent — and **CI installs it so they run for real**, because a guard
that only ever skips is not a guard.

### Two bugs worth recording
Reading `gain[..., 0]` from the solver returned a single polarization component rather than
the total, which showed up as a *physically impossible negative peak gain* on a Yagi. And a
test compared `|Z − 50|` when mismatch is a ratio: 20 and 80 ohms are nearly equidistant from
50 by difference, but their SWRs are 2.5 and 1.6. Both are now commented where they happened.


## [0.6.0] — M5, Wire antennas & arrays

Apertures were the easy half. Wire antennas are where the amateur bands live — Radio JOVE at
20 MHz, meteor scatter at 143 MHz — and where the dominant effect is one an aperture model
never has to consider: **the ground**.

### The catalogue entries that waited five milestones
`radio-jove`, `graves-yagi-7el`, and `graves-yagi-3el` were held back from M0 because the
tool could not evaluate them. Their geometry was verified long ago; it simply waited for a
model. A template the tool cannot characterize is decoration, and one with invented numbers
is worse.

### Added
- **`jansky_forge.wires`**: half-wave and folded dipoles, the exact array factor, Fresnel
  ground reflection over four soil types, and dipole-over-ground with height as a first-class
  design variable.
- **Height as a beam-steering control, not a mounting detail.** A horizontal dipole works
  with its own inverted image in the earth: low, and the lobe is overhead; raise it, and the
  lobe drops toward the horizon. Radio JOVE's manual treats height as one of its two
  steering mechanisms, and the model reproduces that — zenith at 10 ft, 35 degrees elevation
  at 20 ft.
- Soil quality as a real number: at 20 MHz a dipole gains 6.0 dB over seawater and 2.7 dB
  over dry sand, which is most of the difference between hearing Jupiter and not.

### Verified against
- **NASA's published 5.8 dBi** for a single JOVE dipole. Over *average* ground at their 10 ft
  height we compute **5.89 dBi**. That agreement is what identifies the manual's figure as an
  average-ground number: perfect ground would give 8.17 dBi, so the 2.4 dB difference is real
  soil loss rather than a modelling error.
- **NASA's published 23.28 ft** element length: we compute 23.24 ft from a 0.95 velocity
  factor — 1 cm apart, which validates the factor rather than merely agreeing with it.
- **The half-wave dipole's 2.15 dBi**, obtained by integrating its own pattern rather than
  asserting the constant.
- **A published 7-element Yagi** at 143 MHz: 11.24 dBi estimated against 11.6 dBi modelled.

### Two disagreements kept rather than tuned away
- **The JOVE dual dipole overshoots.** We predict 8.90 dBi against NASA's published 7.8. The
  gap is our ideal-array assumption: two real dipoles couple to each other and fall about
  1 dB short of textbook stacking gain. Pattern multiplication cannot represent that, and
  fudging the array factor to match would destroy the model's independence. M6's
  method-of-moments tier is the right place to fix it.
- **The 3-element Yagi estimate is 2.3 dB low** (4.47 against a published 6.75). The
  Hansen-Woodyard endfire bound behind it assumes a *long* array, and this boom is 0.24
  wavelengths. The model warns about exactly this case, and the test asserts the shortfall —
  a model that quietly returned a plausible number here would be worse than one visibly
  wrong for a stated reason.

### Deliberately thin, and deliberately said so
Yagis are modelled **by boom length only**. Element lengths and spacings are precisely what a
method-of-moments solver is for, and that is Tier 2 (M6) — so `yagi_gain_estimate` is for
sizing a mast, not for cutting elements, and says so in its docstring, its notes, and a test.
Both GRAVES catalogue entries carry their full published element geometry in their caveats,
ready to feed M6.

Helical, log-periodic, and Moxon antennas are **not** modelled. The plan listed them; they
are not here, and pretending otherwise would be worse than the gap.


## [0.5.1] — verified source catalogue, and three corrections

M4 shipped without a source catalogue because the fluxes were not yet verified. They now
are — against **Perley & Butler (2017)** cross-checked with the independent **Trotter et al.
(2017)** scale, which agree to about 2%. Verification found three things wrong with what
would otherwise have been shipped, one of them already released.

### Fixed
- **The zenith atmosphere term was 2.5 K; it is 2.0 K** (Peng et al. 2013's
  radiosonde-validated 1400-1427 MHz model, via L-BASS). This was in the released v0.5.0 and
  made every system temperature half a kelvin pessimistic.
- **Cas A is not "~1900-2000 Jy".** That is an early-2000s value. It is **1768 Jy at epoch
  2016.0**, and an undated Cas A flux is meaningless because it fades.
- **Tau A is 829 Jy, not 875**, and its measured decline is **0.10 +/- 0.04 %/yr**, not the
  0.15 %/yr often repeated.

### Added
- Seven catalogued sources with full provenance: Cas A, Cyg A, Tau A, Vir A, the quiet Sun,
  and galactic HI at the plane and at high latitude. `jansky-forge sources` prints them with
  every caveat attached.
- **`flux_at_epoch()`** for the two sources that fade, which states that the rate it applies
  is a long-term average over an interval in which the fading demonstrably was *not*
  constant — Trotter et al. detect that at 6.3 sigma — and flags long extrapolations as
  guesses with arithmetic attached.
- Two universal constants as cheap, decisive checks on the whole chain: **1 K/Jy is 2761 m²**
  of collecting area (Condon & Ransom eq. 3.49), and our SEFD reproduces **NRAO's
  `5.62·Tsys/eta_A`** form for the VLA's 25 m dishes.
- The factor of two in `sensitivity_k_per_jy` is now explained as what it is — a
  *polarization* factor that applies because the source is unpolarized, the most common
  factor-of-two error in the amateur literature.

### The correction that matters most for expectations
Catalogued HI brightness temperatures come from surveys with **16-36 arcmin beams**. An
amateur beam is *degrees* wide and reads the average over that patch, which is lower than the
survey peak wherever emission is structured. The aperture-independence point from M4 is
still exactly right — but the number an amateur measures is not the catalogue peak, and
`detect()` now says so.

### Not tuned away
The sky model gives 3.41 K at 1.4 GHz against Testori et al.'s **measured** 3.58 K. That
0.17 K shortfall is left in place: it sits inside the 0.1-0.5 K zero-level uncertainty the
408 MHz surveys quote, and part of it is an extragalactic background a single galactic power
law cannot represent. The measured value is recorded alongside as
`COLD_SKY_MEASURED_1420_K`, and the test asserts closeness rather than equality — a test
demanding exact agreement would be an invitation to fudge the constant.

### Could not verify, so not shipped
The Baars et al. (1977) polynomial coefficients (the ADS scan is image-only and would not
OCR); the quiet-Sun solar-cycle amplitude *at 1.4 GHz specifically* (only 1 GHz multi-cycle
data exists, so the 2-4x range is flagged as inferred); and a galactic-centre continuum peak,
for which only a lower bound was obtainable.


## [0.5.0] — M4, Sensitivity: telescope figures of merit

Everything before this described an *antenna*. This turns those numbers into *telescope*
numbers — the ones that answer whether you will see the thing, and how long you must stare.

### Added
- **`jansky_forge.sensitivity`**: system temperature built from parts you can act on (sky,
  spillover onto warm ground, pre-amplifier losses, the receiver via the Friis cascade),
  SEFD, G/T, K/Jy sensitivity, the radiometer equation, time-to-detect, and
  "how big a dish do I need?" solved backwards.
- **The M3-to-M4 join**: spillover efficiency becomes kelvins. Feed power that misses the
  dish sees ~290 K of ground, so a feed-choice made in M3 shows up directly in the noise
  budget — and when spillover beats the receiver, the system says so and tells you a better
  feed is cheaper than a better LNA.
- **`Stage` / Friis cascade**, which makes the mast-head-LNA argument quantitative: the same
  chain with 3 dB of coax moved from after the LNA to before it goes from 45 K to 334 K.
- `jansky-forge sensitivity --template discovery-dish --brightness-k 100`.

### The asymmetry this milestone exists to get right
**Gain is not sensitivity.** A bigger dish collects more from a *point* source. But galactic
HI fills the beam, and for a beam-filling source the antenna temperature equals the source
brightness temperature **regardless of aperture** — a 0.9 m horn and a 30 m dish see the
same ~100 K line. Applying the point-source formula to HI is the most flattering mistake
available, because it makes a bigger dish look like more signal. `detect()` routes to the
right formula by source type and says which one it used.

It also refuses to let a large thermal SNR read as a promise: for line work the real floor
is baseline stability — standing waves, gain drift, RFI — not thermal noise, so a predicted
SNR of ten thousand is reported as "thermal noise will not be your problem", not as success.

### Verified against
- **BHARAT's published sensitivity.** The paper gives A_e = 0.407 m² *and* 1.47e-4 K/Jy; we
  compute 1.474e-4 from the area alone, agreeing to 0.3%.
- **The standard cold sky.** CMB plus galactic synchrotron scaled from 408 MHz gives 3.41 K
  at 1.4 GHz, the familiar L-band figure.
- **The sibling course.** `jansky.signals.radiometer_sensitivity` and
  `jansky.observing.noise_figure_to_temperature` are independent implementations of two
  formulas here. Rather than take a hard dependency (this package stays installable on its
  own) or let a skipped test pretend to guard, **CI checks the course out and runs the
  cross-check for real**.

### Known limits, stated
- The sky model is a smooth galactic scaling, not a map: it does not know where you are
  pointing, and toward the plane you must pass a larger 408 MHz brightness yourself.
- A curated catalogue of named calibrator sources (Cas A, Cyg A, Tau A) is **not** included:
  their fluxes are epoch-dependent — Cas A declines measurably every year — and shipping
  unverified numbers would violate the catalog's own provenance rules. `--flux-jy` and
  `--brightness-k` take whatever value you can source.


## [0.4.0] — M3, Dish & feed system

Efficiency stops being a number you type in.

M0 asked you to supply illumination and spillover as constants. Those constants are exactly
what changes when you pick a different feed or a different f/D, so a tool that takes them as
input cannot answer the question anyone actually has. M3 computes them.

### Added
- **`jansky_forge.feeds`** — the standard front-fed paraboloid integrals. Give a dish a
  feed pattern and it reports illumination efficiency, spillover efficiency, edge taper, and
  the resulting aperture efficiency, with every term exposed so you can see which one is
  hurting you.
- **`CosQFeed`**, the classic model (and `from_beamwidth`, since beamwidth is what you know
  about a feed you own), and **`HornFeed`**, which uses a real M1 horn's *computed* patterns —
  the join between designing a horn and putting it on a dish.
- **Feed matching in both directions**: `best_f_over_d(feed)` for "I have this feed, what
  dish shape do I want", and `best_feed_for_dish(f_over_d=...)` for "I have this dish, what
  feed should I build" — which answers with a beamwidth you can then synthesize a horn to.
- **Blockage** computed from physical parts: a central feed obstruction costs
  `(1 - (d/D)^2)^2`, so the loss goes as the *square* of the blocked area fraction — worse
  than the area suggests, and the reason offset dishes exist. Struts too.
- **Mesh check** against the lambda/10 rule, deliberately advisory: it changes no number,
  because a real transmission coefficient needs wire diameter and weave, and quoting one
  from the opening size alone would be false precision.
- **The waveguide probe and backshort** — the gap M2 named when it said a horn with no feed
  design is a nicely-shaped piece of metal. Probe length is the free-space quarter wave;
  the backshort sits a quarter *guide* wavelength away, and those are different numbers.
- CLI: `jansky-forge feed --f-over-d 0.35` and `jansky-forge probe --waveguide wr650`.

### Verified against
- **The optimum edge taper emerges rather than being assumed.** Maximizing aperture
  efficiency over rim angle lands at **-10.9 dB** for every feed shape tried (cos^2q with q
  from 0.5 to 4, an eightfold range of directivity), with peak efficiency 0.82-0.85. That is
  the textbook "-10 to -11 dB optimum edge illumination", and its near-invariance with feed
  shape is exactly why the rule of thumb is trustworthy. Nothing in the optimizer targets a
  taper — it maximizes efficiency and the taper falls out.
- **The probe design reproduces a published, built antenna.** PhysicsOpenLab's 21 cm
  oil-can horn uses a 52.5 mm probe 76.4 mm from the backshort; we compute 52.8 mm and
  76.4 mm from its waveguide dimensions alone.

### Known gaps, stated rather than papered over
- **Conical horn patterns are still rules of thumb.** M1 computed conical *gain* exactly and
  deferred the pattern; M3 needed it and deferred it again rather than inventing one.
  `conical_horn_feed()` gives a usable path — a `cos^2q` model fitted to the rule-of-thumb
  beamwidth — and its docstring says plainly that this is two approximations stacked. A
  pyramidal horn through `HornFeed` uses its real pattern and is the better route where
  either will do.
- **A horn is not rotationally symmetric** and the reflector integrals assume it is.
  `HornFeed` uses the geometric mean of the two principal planes, and says so in the notes of
  every result it touches.
- Offset-fed geometry is not modelled; only the blockage advantage is mentioned.

### Performance
Feed evaluation is 0.5 ms. Horn patterns are tabulated once per geometry and interpolated
(accurate to under 0.01 dB), and the reflector integrals use fixed vectorized quadrature
instead of an adaptive rule — together a 28x speedup over the first working version, which
took 683 ms per optimization and would have broken the interactivity promise.


## [0.3.0] — M2, Fabrication

The "build" leg. A design stops being a number and becomes shapes you can cut.

### Added
- **`jansky_forge.fabricate`** — exact flat developments of both horn types. A pyramidal
  horn unrolls into four trapezoidal panels; a conical horn into an annular sector. Both are
  derived, not approximated: a horn's surface is developable, so the unrolling is exact.
- **1:1 printable SVG templates**, tiled across ordinary paper with registration marks and
  overlap guides, **one template set per panel** rather than one giant composite — you print
  the piece you are about to cut.
- **A 100 mm ruler on every single sheet**, with the instruction to measure it before
  cutting. A printer set to "fit to page" shrinks a drawing a few percent; that is invisible
  on screen, invisible on paper, and ruinous after the metal is cut. This is the cheapest
  guard against the most expensive mistake in the whole project.
- **DXF R12** output with cut and fold on separate layers, `$INSUNITS` declared as
  millimetres, and true `ARC` entities for cone developments. No dependencies added.
- **Cut list** with per-panel stock sizes, material and kerf budget, and a **bill of
  materials that states why each item is there** — including that a horn seam must be
  electrically continuous, because a gap in a horn wall is a slot, and slots radiate.
- **Assembly steps** as a checklist, ending with the reminders that the gain is a prediction
  rather than a measurement, and that a horn which looks right can still be badly matched.
- **`design.json`** in every packet: the provenance record tying the shapes back to the
  design that produced them, so a measured antenna can later be compared against what it was
  meant to be (M7/M8).
- `jansky-forge fabricate --gain-dbi 18 --out ./horn` writes the whole packet, reports the
  sheet count per template, and warns when a template needs an unreasonable amount of taping.
- The `/fabrication-packet` skill, with a pre-flight that checks sheet count, stock fit,
  kerf double-compensation, and realizability before anyone prints.

### Details worth knowing
- **Seam allowance is applied perpendicular to the sloped edges**, not as a horizontal
  offset. On a steeply flared horn the two differ, and the naive version leaves the flange
  narrow — the kind of error that only appears once the metal is cut.
- **Kerf is reported, never silently applied.** Hand tools are guided to one side of the
  line; lasers and waterjets compensate in software. Applying it twice is a real and common
  error, so the cut list says so instead of adjusting anybody's dimensions.
- Cone developments are checked by a property we did not impose: the sector angle is chosen
  so the *outer* arc equals the aperture circumference, and the inner arc then equals the
  throat circumference by similar triangles.
- The panel corner edge is verified to be the same length measured on either adjoining
  panel. That equality is the difference between four shapes that assemble and four that do
  not.


### Added
- Vendored the third-party `simple-english` skill (ASD-STE100 Simplified Technical English;
  MIT, AminBlg/SimpleEnglish, pinned commit). Kept in git rather than installed globally so
  a reviewer can see what the agent was told. `CLAUDE.md` records where it applies —
  reader-facing prose, and especially M2's fabrication instructions — and where it must not:
  model notes and catalog caveats, because STE's restrictions on "should"/"may"/"might"
  would strip the calibrated uncertainty the honesty invariants exist to protect.

## [0.2.0] — M1, Horn designer

Horns stop being an assumption and become physics. M0 modelled every horn as if its flare
were near-optimum (a flat 51% aperture efficiency), which is true of published designs and
useless the moment you change a dimension — the whole point of the tool.

### Added
- **Exact aperture-phase-error gain** (`horns.py`): E- and H-plane sectoral gains in
  Fresnel-integral form and the pyramidal product form, per Balanis ch. 13. The model now
  correctly reports that an **over-flared horn loses gain** — a fixed-length horn's gain
  peaks at the optimum flare and falls beyond it, which no efficiency constant can express.
- **Synthesis — the headline.** `design_pyramidal_horn(gain_dbi=…)` and
  `design_conical_horn(…)` go the other way: target gain in, buildable dimensions out.
  Reachable from the CLI as `jansky-forge design --gain-dbi 18`.
- **Realizability checking.** A pyramidal horn is one frustum, so both flares share one
  axial length. `realizability()` catches designs that optimize the E- and H-plane sectoral
  horns independently — including one in this package's own catalog (below).
- **Radiation patterns** computed by integrating the aperture field (cosine taper in H,
  uniform in E, plus the flare's quadratic phase), so beamwidths follow the geometry instead
  of assuming optimum flare. Half-power widths are found by root-finding rather than by
  rendering a pattern — 1.4 ms instead of 400 ms, which is what keeps the interactivity
  promise honest.
- **Conical horns** via Balanis' loss-figure treatment (13-59), with an independent
  aperture-integration cross-check available for validation.
- `scipy` dependency (Fresnel and Bessel functions); still microseconds per evaluation.

### Fixed
- **A real 7% geometry bug, found by verifying against the primary source.** The axial-to-
  apex-distance conversion used Balanis' slant relation where the axial one was needed —
  his ρ_e/ρ_h are *slants*, ρ₁/ρ₂ are *axial*, and p_e/p_h are the axial flare lengths. No
  test of internal consistency catches this, because everything downstream stays
  self-consistent; only checking against published numbers does. The module's notation table
  now spells the distinction out.
- Patterns were normalized to the largest *sampled* value, so a sweep that excluded
  boresight was silently rescaled. They are now referenced to boresight, making any two
  sweeps comparable and letting a genuinely split beam show as a positive value.

### Changed
- `PyramidalHorn` and `ConicalHorn` use the exact models when the geometry allows, and fall
  back to M0's estimate — saying so in the notes — when a source never published its throat.
- **BHARAT's catalog caveat was wrong and is corrected on the record.** M0 predicted 19.46
  dBi against the paper's measured 20.6 and blamed the 1.1 dB gap on the horn's Potter
  dual-mode design. With the phase error properly modelled the prediction is ~20.25 dBi and
  the gap is ~0.35 dB: most of the supposed dual-mode advantage was phase error being
  mismodelled. The earlier explanation is kept visible rather than quietly overwritten.
- **The catalog's own worked example is now flagged as not buildable.** Its source quotes
  two different axial flare lengths (682 and 578 mm, a 15% disagreement). The precise
  diagnosis is visible in the output: its two *slants* are equal to four figures, so the
  source equalized ρ_e and ρ_h where realizability requires equal p_e and p_h. Both lengths
  are entered deliberately so the model reports the defect.

### Verified against
Balanis Example 13.5 (analysis): our ρ_e = 6.1555, ρ_h = 6.6002, p_e = p_h = 5.4545,
s = 0.1576, t = 0.6302 against the book's 6.1555, 6.6000, 5.454, 0.1575, 0.63; D_p = 18.83 dB
against 18.78 dB. Example 13.6 (design): a1 = 5.974λ, b1 = 4.712λ against 6.002λ, 4.715λ.
Optimum designs reproduce the textbook ~51% aperture efficiency as an *output*; the conical
loss figure gives 2.91 dB at s = 3/8 against Balanis' ~2.9 dB; and the independent
aperture-integration route reproduces the Fresnel gain to 0.000 dB.


### Fixed
- The release workflow uploaded `uv build`'s `dist/.gitignore` as a release asset (a `dist/*`
  glob catches it). It now names `*.whl` and `*.tar.gz` explicitly; the stray asset was
  removed from the `v0.1.0` release.

## [0.1.0] — M0, Foundation & catalog

First release. Useful on day one: `jansky-forge show discovery-dish`.

### Added
- **The model layer.** `AntennaModel` protocol (`parameters()` + `characterize(freq_hz)`, both
  pure) and the `Characterization` result type, which carries the model's own validity notes
  alongside its numbers.
- **Aperture models** (`apertures.py`): `ParabolicDish` with a *named-factor* efficiency budget
  (illumination, spillover, blockage, other) plus Ruze surface loss; `PyramidalHorn` and
  `ConicalHorn` on the optimum-flare aperture relations. Formulas cited to Balanis and Kraus.
- **Bands** (`bands.py`): HI 21 cm, the four ground-state OH lines, methanol 6.7 GHz, deuterium
  92 cm, Radio JOVE 20.1 MHz, GRAVES and BRAMS meteor beacons, L-band continuum, Ku band —
  each with the reason it matters.
- **The catalog** (`catalog.py`): known telescope builds as selectable templates, each with
  provenance, a source URL, published figures kept as cross-checks, and honest caveats.
  `catalog.audit()` makes the provenance rules executable; CI fails on any output.
- **CLI**: `bands`, `list` (filter by band/kind), `show` (human or `--json`), `characterize`
  (multiple bands/frequencies). Model caveats are always printed, never suppressed.
- **Pipeline from day one**: three-OS CI matrix (Linux/macOS/Windows — cross-platform is a
  promise, so it is a matrix), a release workflow whose gate blocks publication and which
  verifies tag == package version == `CITATION.cff`.
- **Claude assets**: `/verify`, `/release`, `/design-antenna`, `/catalog-entry`,
  `/new-antenna`, and the `antenna-physics-reviewer` agent.
- **The plan** (`plans/jansky_forge.md`): landscape survey, the three-tier architecture, all
  fifteen milestones through M14, testing strategy, cross-repo contracts, open questions.

### Notes
- The CLI reconfigures stdout to UTF-8 at startup. Windows consoles default to cp1252 and
  cannot encode λ, ° or ² — the characters this output is genuinely made of. The three-OS CI
  matrix caught this before the first tag; spelling the symbols out for everyone would have
  been the wrong fix.
- Dependency-light on purpose: the interactive tier is pure NumPy. Heavier tiers (matplotlib,
  scikit-rf, pymininec, FastAPI, `jansky`) arrive as optional extras with the milestones that
  need them.
- Wire-antenna catalog entries (Radio JOVE dual dipole, meteor-scatter yagis) are deliberately
  held to M5, when a model exists that can characterize them. A template the tool cannot
  evaluate would be decoration; one with invented numbers would be worse.
