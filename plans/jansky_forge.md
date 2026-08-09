# jansky-forge — project plan

*Antenna design, build, and characterization for radio astronomy. Drafted 2026-08-08 from the
survey in the vault note `efforts/radio_astronomy/jansky_x_project.md`. Fourth sibling of
[`jansky`](https://github.com/joebarbere/jansky) (course),
[`jansky-research`](https://github.com/joebarbere/jansky-research) (research), and
[`jansky-observe`](https://github.com/joebarbere/jansky-observe) (station).*

## 1. Goal & guiding principles

**Goal.** One tool that takes an amateur radio astronomer from *"I want to see the hydrogen
line"* to *cut metal* to *measured performance next to predicted performance* — with the
design step interactive enough that exploring is fun rather than a batch job.

**Principles.**

- **Instant is a physics choice, not an optimization.** Aperture antennas many wavelengths
  across are exactly the regime where closed-form theory is accurate to tenths of a dB. The
  Tier-1 analytic layer recomputes in microseconds because the equations are algebraic, not
  because anything is cached or approximated behind the user's back. Any feature that would
  force a solver into the interactive path belongs in a slower tier by definition.
- **Nobody starts from a blank sheet.** The catalog of known builds is a headline feature,
  not a convenience: select the Discovery Dish or a published 21 cm horn, then change one
  dimension and watch the numbers move. Learning by perturbation beats learning by tutorial.
- **Provenance or it doesn't ship.** Every catalog number states where it came from; a
  number that could not be verified is recorded as a gap, never as a plausible value.
  Published gains and beamwidths are stored as **cross-checks against our model**, never
  restated as our own output. Enforced mechanically (`catalog.audit`, tests).
- **Predicted and measured never wear the same label.** From M7 the tool ingests real
  measurements; they sit *beside* model output with their own provenance, and a
  disagreement is reported as a disagreement — the same honesty standard as
  `jansky-research` results.
- **Telescope figures of merit, not just antenna ones.** G/T, SEFD, Tsys, time-to-detect,
  beam versus mapping resolution. This is what makes it a radio-astronomy tool rather than
  a ham antenna calculator, and it is the gap nothing else fills.
- **Cross-platform means a localhost app.** Python + a browser UI, exactly the stack
  `jansky-observe` already proved on Linux, macOS, and a Pi. No native toolkits, no build
  step, no Electron.
- **House conventions.** Python 3.12, `uv`, `pytest` (85% floor), `ruff` (line-length 100),
  `mypy`, Makefile, hatchling; CI and the release pipeline exist from M0. MIT licensed.
- **Claude-native.** Repo-versioned skills and agents from M0; an MCP surface at M14.

## 2. The landscape, and the gap (2026-08 survey)

Full survey with the comparison table lives in the vault note. The short version:

| What exists | What it covers | What it misses |
|---|---|---|
| NEC2 lineage (nec2++/PyNEC, xnec2c, 4nec2), AntennaSim (nec2c→WASM, live in a browser) | Wire antennas, method-of-moments, some with genuinely live feedback | **Zero aperture support** — no dishes, no horns |
| HDL_ANT (W1GHZ), dnemec, blog calculators | Horn/dish design equations, even printable templates | 1990s-frozen, informally licensed, or single-shot calculators with no workflow |
| openEMS / MEEP (FDTD), Arcanum (Rust MoM, announced 2026-04) | Full-wave rigor; Arcanum is the plausible NEC2 successor | Minutes-to-hours per run; Arcanum is **design-docs-only today** |
| scikit-rf | S-parameters, VNA/Touchstone, matching — excellent and active | Not a field solver; no design layer |
| PICTOR, OSRT, BHARAT, ezRA, every 21 cm horn guide | The community's actual practice | Runs on **spreadsheets and blog posts** |

**The gap:** nothing connects *design → fabrication artifacts → measured-vs-predicted
characterization*, and nothing speaks radio astronomy. That is the whole product.

## 3. Architecture — three tiers

```
Tier 1  analytic, always on            µs–ms    NumPy closed-form. Drives every slider.
Tier 2  method-of-moments validation   seconds  Wire antennas, on demand, pluggable backend.
Tier 3  full-wave export               offline  Generate openEMS/NEC input; never run it inline.
```

**Tier 1** is the product. Aperture theory for dishes and horns (gain, beamwidth, efficiency
budget, Ruze, blockage, f/D and illumination), textbook models for the wire families.

**Tier 2** validates the wire side against real MoM. Backend pick: **pymininec** (pure
Python, MIT, actively maintained — no C build step on any platform). `necpp`/vendored
`nec2c` stay optional and **subprocess-invoked, never linked**, so their GPL never reaches
our MIT core. The backend is a protocol so **Arcanum** slots in when it grows code.

**Tier 3** never runs a solver; it *writes* one's input deck (openEMS ships a conical-horn
tutorial we can target) so a user who wants full-wave numbers gets a runnable script
without this package owning an FDTD runtime. Interactive FDTD at 1420 MHz is not a
performance problem to solve — it is physically the wrong tool, and the plan says so.

**Repo layout** (grown milestone by milestone):

```
src/jansky_forge/
├── units.py        constants + conversions (one file owns them)
├── core.py         AntennaModel protocol + Characterization
├── bands.py        the frequencies that matter (HI, OH, JOVE, meteor, …)
├── apertures.py    ParabolicDish, PyramidalHorn, ConicalHorn        [M0]
├── catalog.py      known builds + provenance discipline             [M0]
├── cli.py          the command line                                 [M0]
├── horns/          synthesis, phase error, patterns                 [M1]
├── fabricate/      geometry, svg (tiled 1:1), dxf, cutlist, packet   [M2] ✅
├── feeds.py        feed↔dish matching, taper, spillover, probe      [M3] ✅
├── sensitivity/    G/T, SEFD, Tsys, radiometer                      [M4]
├── wires/          dipole, yagi, helix, LPDA, arrays                [M5]
├── mom/            Tier-2 backends behind one protocol              [M6]
├── measure/        VNA/Touchstone, measured-vs-predicted            [M7]
├── onsky/          Y-factor, drift-scan beam maps, transit SEFD     [M8]
├── server/         FastAPI + htmx + canvas, the live UI             [M9]
├── optimize/       sweeps, optimizers, constraint-driven design     [M10]
├── export/         openEMS/NEC decks                                [M11]
├── site/           ground reflection, RFI-aware siting, mechanical  [M12]
├── report/         design reports, spec sheets, provenance bundles  [M13]
└── mcp/            the MCP tool surface                             [M14]
```

## 4. The catalog (headline feature)

Selectable, pre-designed builds — the Discovery Dish first, since it is the station's own
antenna and the reference the whole toolchain validates against. Each entry is geometry +
provenance + source URL + published figures as cross-checks + honest caveats.

**M0 ships the aperture entries** (dishes and horns — "dish/horn to start"). Wire-antenna
templates (Radio JOVE dual dipole, meteor-scatter yagis) are deliberately **held to M5**,
when there is a model that can characterize them: a template the tool cannot evaluate would
be decoration, and a template with invented numbers would be worse.

Catalog integrity is a test, not a habit: `catalog.audit()` must be silent, every entry
needs a source URL, and non-primary provenance requires recorded caveats.

## 5. Milestones, releases & versioning

Pre-1.0 semver, same as `jansky-observe`: **minor = milestone, patch = fixes between
milestones.** Every milestone ends in a tag and a GitHub Release; CI and the release
workflow exist from M0 so that is true from the first tag. Version lives in
`pyproject.toml` + `CITATION.cff`; every PR adds a `CHANGES.md` entry.

| Tag | Milestone | What the release means |
|---|---|---|
| `v0.1.0` | **M0 — Foundation & catalog** ✅ shipped 2026-08-08 | Package, CI, release workflow, the `AntennaModel` protocol, bands, dish + horn analytic models, the catalog with the Discovery Dish and known builds, the CLI, `/verify` + `/release` + the design skills. Useful on day one: `jansky-forge show discovery-dish` |
| `v0.2.0` | **M1 — Horn designer** ✅ shipped 2026-08-08 | Synthesis *both directions* (gain→dimensions and dimensions→performance) for pyramidal and conical horns; Balanis aperture-phase-error correction replacing the optimum-flare assumption; E/H-plane pattern computation; golden tests against W1GHZ tables and published amateur builds |
| `v0.3.0` | **M2 — Fabrication** ✅ shipped 2026-08-08 | The artifacts that turn a design into metal: printable fold-up templates (SVG/PDF, tiled to A4/Letter), DXF export, cut lists with kerf allowance, a bill of materials, and assembly notes. The "build" leg of the name |
| `v0.4.0` | **M3 — Dish & feed system** ✅ shipped 2026-08-08 | f/D ↔ subtended angle ↔ edge taper ↔ illumination/spillover as a solved system rather than assumed constants; feed selection and matching (which horn belongs on which dish); offset geometry; strut blockage; mesh transparency; focal-point placement |
| `v0.5.0` | **M4 — Sensitivity: telescope figures of merit** ✅ shipped 2026-08-09 | G/T, SEFD, Tsys budget (feed + LNA + cable + spillover + sky), the radiometer equation, time-to-detect for a named source, and "how big a dish do I need to see X?" solved backwards. Optional `jansky` dependency lands here for the course's radiometer helpers |
| `v0.6.0` | **M5 — Wire antennas & arrays** | Dipole, folded dipole, ground-plane, Yagi-Uda, Moxon, helical, log-periodic, plus simple arrays and ground-reflection gain. Unlocks the **Radio JOVE dual-dipole and meteor-scatter yagi catalog entries** held back from M0 |
| `v0.7.0` | **M6 — Tier-2 MoM validation** | The `MomBackend` protocol + pymininec backend; analytic-vs-MoM pattern overlay; optional subprocess NEC2; an Arcanum-shaped seam. The button that says "check my closed-form answer against real numerics" |
| `v0.8.0` | **M7 — Measurement ingest** | scikit-rf dependency; NanoVNA/LiteVNA Touchstone import; measured SWR/impedance/S11 versus predicted, on one plot with separate provenance; match networks; cable-loss budgets |
| `v0.9.0` | **M8 — On-sky characterization** | The loop closes: Y-factor Tsys, drift-scan beam maps, aperture efficiency and SEFD from a Sun or Cas A transit — computed from **jansky-observe observation bundles**, so a real antenna's measured beam lands beside the model's predicted beam |
| `v0.10.0` | **M9 — Interactive UI** | FastAPI + htmx + a canvas module (the proven sibling stack): catalog browser, slider-driven design with live recompute, pattern plots, side-by-side design comparison. The moment the tool becomes pleasant rather than merely correct |
| `v0.11.0` | **M10 — Sweeps & optimization** | Parametric sweeps with plots, Nelder-Mead/GA optimizers over any parameter set, constraint-driven design ("maximize G/T subject to D ≤ 1.2 m and it must fit through a door"), Pareto fronts |
| `v0.12.0` | **M11 — Full-wave export** | Generate runnable openEMS Python decks and NEC input cards from any design; import the results back for comparison. Rigor without owning a solver |
| `v0.13.0` | **M12 — Site & environment** | Ground-reflection modelling, horizon/terrain masks, an RFI-aware siting helper fed by `jansky-observe` HackRF sweeps, wind loading and mount stiffness, radome and weather effects, thermal expansion versus surface tolerance |
| `v0.14.0` | **M13 — Reports & provenance** | A design-report PDF (geometry, predicted performance, fabrication packet, measured comparison, full provenance), publishable spec sheets, and a codified design bundle so a build is reproducible by someone else — the `jansky-research` evidence standard applied to hardware |
| `v0.15.0` | **M14 — Claude-native surface** | The MCP tool surface (read + safe design verbs) so Claude is a design peer of the browser UI, plus the analyst/reviewer agents wired to it |
| `v1.0.0` | — | **Not a feature.** Tagged after one antenna has been *designed in this tool, built from its fabrication output, and measured back into it* with predicted-versus-measured agreement reported honestly. 1.0 means the loop closed on real metal |

**Post-1.0 candidates** (not scheduled): interferometer/array layout and uv coverage,
phased arrays and beamforming, rotator/mount integration with `jansky-observe` M9, cryogenic
and LNA noise modelling, a public catalog-contribution flow, mobile/tablet UI.

**Feature parking lot** (recorded so they are decisions, not oversights): 3D geometry
viewer, STL export for printed feeds, waveguide component design, filter/diplexer design,
antenna-range measurement automation, machine-learning surrogates for the MoM tier.

### M1 postscript (2026-08-08)

Two things worth carrying forward:

1. **Self-consistency is not verification.** The first M1 implementation had a 7% error in
   the axial-to-apex-distance conversion (Balanis' ρ_e/ρ_h are *slants*; ρ₁/ρ₂ are *axial*).
   Every internal check stayed green — synthesis round-tripped, efficiency came out at the
   textbook 51%, phase deviations landed exactly on 1/4 and 3/8 — because the error sat in a
   conversion that everything downstream shared. Only checking against Balanis' *published*
   worked examples exposed it. Every future physics milestone needs an external anchor.
2. **Conical patterns are a known gap.** Conical *gain* is exact (Balanis' loss figure, with
   an independent aperture-integration cross-check), but conical beamwidths are still the
   optimum-flare rules of thumb. Computing them properly needs the circular-aperture TE11
   far field; deferred rather than faked, and the model's notes say so. Candidate for M3,
   where feed patterns start to matter for dish illumination.

**Update after M3:** it was needed and deferred again rather than faked. `conical_horn_feed()`
gives a usable path via a cos^2q model fitted to the rule-of-thumb beamwidth, with the
stacked approximation stated. Doing it properly needs the circular-aperture TE11 far field;
it is now a candidate for whichever milestone first has a reason to care about conical
sidelobes rather than just conical beamwidth.

## 6. Testing strategy

- **Analytic golden values.** Every model is checked against hand-computable cases:
  700 mm at 1420 MHz → ~21° beam; a known-gain horn against its published figure.
- **Catalog cross-checks.** Where a build publishes gain or beamwidth, the test compares
  our model's prediction and asserts the documented tolerance — a disagreement must be
  recorded in `caveats`, not tuned away.
- **Catalog audit.** `catalog.audit()` must yield nothing (source URLs, caveats,
  band references).
- **Property tests.** Gain scales as D²; beamwidth as 1/D; Ruze loss increases with
  frequency; efficiency stays in (0, 1].
- **No network, no hardware, ever, in the test suite** — the same rule as the siblings.

## 7. Claude assets (versioned in `.claude/`, shipped with releases)

| Asset | Kind | What it does | Lands |
|---|---|---|---|
| `/verify` | skill | Pre-commit gate: lint → typecheck → coverage → CLI smoke | M0 |
| `/release` | skill | The milestone-close procedure: verify, changelog, version bump in both files, tag, watch the release workflow | M0 |
| `/design-antenna` | skill | The design copilot: from a science goal ("see HI at SNR 5 in an hour from a city rooftop") to a recommended catalog starting point and a modified design, showing the reasoning | M0 |
| `/catalog-entry` | skill | Add a build to the catalog with the provenance discipline enforced: find the primary source, record gaps as gaps, add the published-figure cross-check test | M0 |
| `/new-antenna` | skill | Scaffold a new antenna family: model + protocol conformance + golden tests + docs | M0 |
| `antenna-physics-reviewer` | agent | Read-only review of any diff touching a model: unit bugs (10 vs 20·log10, mm vs m, degrees vs radians), formula provenance against Balanis/Kraus, validity-limit notes present | M0 |
| `/simple-english` | skill (vendored, MIT) | ASD-STE100 Simplified Technical English for reader-facing prose — README, install steps, release notes, and above all M2's fabrication instructions. Explicitly **not** for model notes or catalog caveats, where its modal restrictions would strip calibrated uncertainty | added 2026-08-08 |
| `/fabrication-packet` | skill | Drive the M2 exporters and pre-flight the result (scale check, tiling, kerf, material fit) | ✅ M2 |
| `/validate-model` | skill | Cross-check a design: analytic vs Tier-2 MoM vs any published figure, reporting disagreements | M6 |
| `/characterize` | skill | The measured-vs-predicted workflow over VNA files and jansky-observe bundles | M7 |
| `rf-measurement-analyst` | agent | The measurement persona: VNA calibration pitfalls, Y-factor method, transit-based aperture efficiency | M7 |

## 8. Cross-repo contracts

- **`jansky-observe` → jansky-forge (M8):** consumes the codified observation bundle
  (`jansky-observe.observation-bundle/1`) — station UUID, pointing, LST, SDR settings — to
  derive beam maps and transit-based efficiency. Read-only; no changes needed on that side.
- **`jansky-observe` → jansky-forge (M12):** HackRF `hackrf_sweep` CSV captures feed the
  RFI-aware siting helper.
- **jansky-forge → `jansky-research` (post-1.0):** a measured antenna characterization is
  publishable evidence; the design bundle is built to be citable.
- **`jansky` (M4):** optional dependency for the course's radiometer helpers rather than a
  second implementation.

## 9. Open questions

1. Does the M1 horn designer generate 3D-printable feed geometry, or stay sheet-metal only
   until an STL story exists? (Leaning: sheet metal at M1, STL in the M2 parking lot.)
2. Is the first real build a 21 cm test horn? It is the ideal validate-the-tool-by-building-it
   slice — cheap, publishable comparison points exist, and it would satisfy the v1.0.0 gate.
3. Does the UI (M9) come earlier? It is the difference between "correct" and "fun". The
   argument for holding it: sliders over a thin model teach less than sliders over M3+M4's
   real efficiency and sensitivity system.
4. Catalog contribution flow: PR-only, or a data file others can extend? (Leaning PR-only
   while the provenance discipline is young.)
