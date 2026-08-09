# Changelog

All notable changes to jansky-forge. Pre-1.0 semver: **minor = milestone, patch = fixes
between milestones** (see `plans/jansky_forge.md` §5).

## [Unreleased]

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
