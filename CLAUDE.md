# jansky-forge — guide for Claude

**What this is.** Antenna design, build, and characterization software for radio astronomy:
closed-form models that recompute instantly, a catalog of known telescope builds to start from,
fabrication artifacts that turn a design into cut metal, and (later) measured-versus-predicted
comparison fed by real observations. Fourth sibling of
[`jansky`](https://github.com/joebarbere/jansky) (the course),
[`jansky-research`](https://github.com/joebarbere/jansky-research) (the research), and
[`jansky-observe`](https://github.com/joebarbere/jansky-observe) (the station). A new session:
read `plans/jansky_forge.md` before any feature work, and the siblings' `CLAUDE.md` for the
shared conventions.

## ⚠️ Honesty invariants

These are the equivalent of jansky-observe's bias-tee rule: violating one does not break a test,
it breaks the project's reason to exist. Numbers here get used to cut metal and to decide
whether a telescope will work.

1. **Never tune a model to match a published figure.** Published gains and beamwidths live in
   `Template.published` as *cross-checks*. If our model disagrees, record the disagreement in
   `caveats` — adjusting an efficiency factor until the numbers agree destroys the model's
   independence, which is the only thing that made the cross-check worth having.
2. **Never invent a dimension.** If a source does not state f/D, say so in `caveats` and use the
   model default explicitly. A plausible fabricated number is the most dangerous output this
   package can produce, because someone will build to it.
3. **Every catalog entry carries a real source URL.** `catalog.audit()` enforces this and CI
   fails on any output. Never "fix" an audit failure by weakening the audit.
4. **Models state their own validity limits.** Every `Characterization` carries `notes`; a model
   used outside its domain must say so in the conditions where that applies. Any presenter (CLI,
   future UI, reports) prints them — suppressing a model's warnings to tidy output is not a
   trade this project makes.
5. **Predicted and measured never wear the same label.** From M8 real measurements arrive; they
   sit beside model output with separate provenance, always.
6. **When a later milestone proves an earlier claim wrong, correct it visibly.** M1's physics
   showed M0's BHARAT caveat had blamed the right gap on the wrong cause. The fix records
   both the old explanation and why it was superseded. Silently overwriting a stale claim
   destroys the reader's ability to trust any of the others.
7. **Never apply the point-source formula to extended emission.** `T_A = S·A_e/2k` makes a
   bigger dish look like more signal; for a source that fills the beam — which galactic HI
   comprehensively does — the antenna temperature is the brightness temperature and aperture
   does not enter. Getting this wrong flatters every design, so `detect()` routes by source
   type and states which formula it used. Related: a huge predicted line SNR must always be
   reported as "thermal noise is not your limitation", never as a promise, because the real
   floor is baseline stability.
8. **Self-consistency is not verification.** The M1 geometry bug kept every internal check
   green — round-trips, efficiency, phase deviations — because the error was in a conversion
   everything downstream shared. Only Balanis' published worked examples caught it. Any new
   physics needs an *external* anchor, not just tests that agree with each other.

If a change seems to require breaking one of these, it is wrong — stop and say so.

## Working rules

- **uv for everything.** `make setup` / `test` / `cov` / `lint` / `fmt` / `typecheck` / `audit`
  (see `make help`). Never call pip or a bare `python`.
- **85% coverage floor** (`make cov`), `ruff` (line-length 100) + `mypy` clean before every PR.
- **Branch before committing — never commit on `main`.** Open a PR, squash-merge, delete the
  branch.
- Run `/verify` before any commit — it includes the catalog audit and the CLI smoke, not just
  the static checks.
- Every PR adds a `CHANGES.md` entry under `Unreleased`.
- Commit footer: `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
  PR footer: `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.

## Architecture: three tiers, only one interactive

```
Tier 1  analytic, always on            µs–ms    NumPy closed-form. Drives every slider.
Tier 2  method-of-moments validation   seconds  Wire antennas, on demand, pluggable backend.
Tier 3  full-wave export               offline  Generate openEMS/NEC input; never run it inline.
```

The interactivity promise is a **physics choice**: aperture antennas many wavelengths across are
exactly where closed-form theory is accurate. Any proposal that would put a solver in the
interactive path is answered by moving the feature to a slower tier, not by optimizing.

Tier 2's GPL backends (`necpp`, `nec2c`) may only ever be **subprocess-invoked, never linked** —
this package is MIT and stays that way. pymininec (MIT, pure Python) is the default backend.

## Layout

- `src/jansky_forge/`
  - `units.py` — constants and conversions; **one file owns them** so a unit bug is a
    single-file bug. SI internally; `surface_rms_mm` is the one deliberate workshop unit.
  - `core.py` — the `AntennaModel` protocol (`parameters()` + `characterize(freq_hz)`, both
    pure) and the `Characterization` result type. Build results with
    `characterization_from_gain` so effective area stays consistent with reported gain.
  - `bands.py` — the frequencies that matter (HI, the four OH lines, methanol, deuterium, JOVE,
    GRAVES/BRAMS meteor beacons, L-band continuum, Ku).
  - `apertures.py` — the antenna *models*: `ParabolicDish`, `PyramidalHorn`, `ConicalHorn`,
    plus `ruze_efficiency` and `subtended_half_angle_deg`. The horns delegate their physics
    to `horns.py`.
  - `horns.py` — the M1 horn engine: exact aperture-phase-error gain (Fresnel-integral form),
    synthesis (`design_pyramidal_horn` / `design_conical_horn`), realizability, and patterns
    computed by aperture integration. **Read its notation table before touching it** — the
    axial/slant symbol distinction caused a real 7% bug.
  - `catalog.py` — `Template`, `Provenance`, `register`/`get`/`find`/`all_templates`, and
    `audit()` (the executable form of honesty invariant 3).
  - `fabricate/` — M2, the build leg: `geometry.py` (exact flat developments — the panel
    and sector shapes every other module consumes), `svg.py` (tiled 1:1 templates; **every
    sheet carries a 100 mm ruler and that is not optional**), `dxf.py` (R12, cut/fold
    layers, true arcs), `cutlist.py` (kerf, material budget, BOM with reasons),
    `packet.py` (writes the whole folder, including `design.json` provenance).
  - `feeds.py` — M3: the front-fed paraboloid integrals (illumination, spillover, edge
    taper), feed models (`CosQFeed`, `HornFeed` using real M1 patterns), matching in both
    directions, blockage, the mesh check, and the waveguide probe/backshort design.
  - `sensitivity.py` — M4: system temperature as a budget (sky + spillover + Friis
    cascade), SEFD, G/T, the radiometer equation, time-to-detect, and `detect()`, which
    **routes point vs extended sources to different formulas**. See the invariant below.
  - `wires.py` — M5: dipoles, folded dipoles, the exact array factor, Fresnel ground
    reflection, and dipole-over-ground. **Yagis are boom-length only by design** — element
    modelling belongs to M6's MoM tier, and the docstring, the notes and a test all say so.
  - `mom.py` — M6, Tier 2: backend-neutral `WireModel`, the `MomBackend` protocol, the
    `pymininec` backend, and `to_nec_deck()` (an export, never a linked GPL solver).
    **Optional extra**; CI installs it so the validation runs rather than skipping.
  - `measure.py` — M7: native Touchstone reading, reference-plane shifting, L-network
    matching, cable loss, and `Comparison`. **`Comparison` must never gain a field that
    merges prediction and measurement** — a test enforces it, and that test is the
    structural form of honesty invariant 5.
  - `onsky.py` — M8: Y-factor Tsys, drift-scan beamwidth, transit aperture efficiency, and
    `read_bundle()` for `jansky-observe` observation bundles. The schema identifier is
    **checked**, so an upstream format change breaks loudly instead of mis-reading.
  - `server/` — M9, the optional web UI: `app.py` (routes), `templates.py` (markup as
    strings — no Jinja2, no CDN), `plots.py` (server-rendered SVG). **The UI must display a
    model's caveats**; tests enforce it.
  - `receivers.py` — N4, the parts catalogue: amplifiers, digitizers and clocks with the
    same provenance discipline as the antenna catalogue (`make audit` covers both and must
    print nothing). Four availability tiers, so an unbuyable 2.2 K cryogenic part can sit
    next to a hobby module honestly. **`compare_amplifiers` ranks against a real antenna**;
    `would_a_better_lna_help` prices the ceiling *and* the achievable upgrade, and ranks only
    actions. **There is deliberately no path from a catalogue entry to a `TwoPort`** — a test
    asserts the absence of one, because a headline noise figure is a budget number and
    Fmin/Γopt/Rn are design data (invariant 2).
  - `stability.py` — N1: Rollett K and Δ, the μ factors, source/load stability circles with
    **which side is safe**, MSG and MAG. `stability_notes()` is wired into
    `parse_touchstone_2port`, so **the check runs on any active device the tool reads** — the
    analogue of realizability on a pyramidal horn, and there is no flag to disable it.
    `max_available_gain_db` **raises** for K ≤ 1 rather than falling back to MSG.
  - `twoport.py` — N0, the receiver track's vocabulary: `TwoPort`, native `.s2p` reading
    **including the noise block**, S↔Z↔Y↔ABCD, the three gain definitions, and `cascade`.
    `as_stage()` hands a network to M4's Friis chain. **Touchstone two-port ordering is
    `S11 S21 S12 S22`** — S21 before S12; reading it row-major transposes the device and
    reports an amplifier's isolation as its gain. We ship **no** transistor data (invariant
    2): Fmin, Γopt and Rn are read from a vendor's file or absent.
  - `cli.py` — `bands`, `list`, `show`, `characterize`, `design`, `fabricate`, `feed`,
    `probe`, `sensitivity`, `sources`, `serve`, `network`.
- `docs/` — eleven milestones of accumulated knowledge: getting-started, traps, rules of thumb,
  workflows, lessons learned, known limits, the verification log, honesty invariants, and
  next steps. **Read `docs/traps.md` before touching the physics**, and add to it whenever
  something bites. `docs/next-steps.md` is the handover document — start there after a gap.
  Every example in `getting-started.md` is executed before it is committed.
- `tests/` — pure, offline, no hardware and no network, ever. Golden values carry their
  arithmetic in a comment so a reader can check rather than trust.
- `plans/receivers.md` — the receiver track (N0–N5): scope, the permanent out-of-scope list,
  and the recommended N0+N1+N4 stopping point. Read it before adding anything about
  amplifiers.
- `plans/jansky_forge.md` — the full plan: survey, tiers, all fifteen milestones, testing
  strategy, cross-repo contracts, open questions.
- `.claude/skills/` — our own skills, plus `simple-english/`, which is vendored from a third
  party and pinned to a commit (`VENDORED.md` records the provenance and how to update).
  Vendored rather than installed with `npx skills add` so a reviewer can see what the agent
  was told; install it globally too if you want it outside this repo.
- `.github/workflows/` — `ci.yml` (three-OS matrix: cross-platform is a promise, so it is a
  matrix), `release.yml` (the release gate + tag/version consistency check).

## Releases

Pre-1.0 semver: **minor = milestone, patch = fixes between milestones.** Version lives in
`pyproject.toml`, `CITATION.cff`, and `__init__.__version__`; the release workflow refuses to
publish when the tag disagrees with any of them.

| Tag | Milestone |
|---|---|
| `v0.1.0` | M0 — Foundation & catalog |
| `v0.2.0` | M1 — Horn designer (synthesis both directions, phase error, patterns) |
| `v0.3.0` | M2 — Fabrication (fold-up templates, DXF, cut lists, BOM) |
| `v0.4.0` | M3 — Dish & feed system (f/D ↔ taper ↔ spillover solved, feed matching) |
| `v0.5.0` | M4 — Sensitivity (G/T, SEFD, Tsys, radiometer, time-to-detect) |
| `v0.6.0` | M5 — Wire antennas & arrays (unlocks the JOVE/meteor catalog entries) |
| `v0.7.0` | M6 — Tier-2 MoM validation (pymininec backend) |
| `v0.8.0` | M7 — Measurement ingest (scikit-rf, NanoVNA Touchstone) |
| `v0.9.0` | M8 — On-sky characterization (Y-factor, beam maps, transit SEFD) |
| `v0.10.0` | M9 — Interactive UI (FastAPI + htmx + canvas) |
| `v0.11.0` | **N0 — Two-port foundations** (receiver track) |
| `v0.12.0` | **N1 — Stability** (receiver track) |
| `v0.13.0` | **N4 — Receiver selection** (receiver track; N2/N3 skipped, not cancelled) |
| `v1.0.0` | **Not a feature** — tagged after one antenna is designed here, built from this tool's fabrication output, and measured back in |

**Tags are allocated in the order milestones actually ship, not reserved in advance.** The
original plan pre-assigned `v0.11.0`–`v0.15.0` to M10–M14; the receiver track then shipped
first and took `v0.11.0`. Since both tracks share one version line — this is one package —
pre-assignment cannot survive two tracks, so it has been dropped rather than fudged. The
antenna track's remaining ideas (sweeps and optimization, full-wave export, site and
environment, reports, an MCP surface) are unshipped and unnumbered; see
`plans/jansky_forge.md` for what they contain and `docs/next-steps.md` for their priority.

### The two tracks

| Track | Plan | State |
|---|---|---|
| Antenna (M0–M9) | `plans/jansky_forge.md` | Complete. Remaining ideas are unnumbered |
| Receiver (N0–N7) | `plans/receivers.md` | N0, N1, N4 shipped. N2/N3 skipped; **N5–N7 deferred, see plan §6** |

Neither track moves the `v1.0.0` gate, which is a build.

Use `/release`; never tag by hand.

## Skills & agents

- `/verify` — the pre-commit gate: lint → format → typecheck → coverage → **catalog audit** →
  CLI smoke (with a sanity read of the Discovery Dish numbers, not just an exit code).
- `/release` — the milestone-close procedure: confirm the milestone's plan row actually shipped,
  verify, changelog, bump both version files, branch/PR, tag, watch the gate.
- `/design-antenna` — the design copilot: science goal → catalog starting point → perturbation,
  with the physics trades explained and the model's own caveats printed. Ends somewhere
  concrete, and never lets enthusiasm imply a detection the numbers don't support.
- `/catalog-entry` — add a build with the provenance discipline enforced: primary source, gaps
  recorded as gaps, published figures as cross-check tests.
- `/new-antenna` — scaffold a new antenna family: frozen dataclass, cited formulas, validity
  notes, golden + scaling + validation + conformance tests.
- `antenna-physics-reviewer` (agent) — read-only review of any diff touching the physics: the
  classic unit bugs (10 vs 20·log10, mm vs m, degrees vs radians, the 4π, diameter vs radius),
  formula provenance, whether validity notes actually fire, and whether any efficiency was
  tuned to match a published figure.
- `/fabrication-packet` — produce and **pre-flight** a fabrication packet: sheet count,
  stock fit, kerf double-compensation, and realizability, before anyone prints 40 pages.
  It is explicitly forbidden from adjusting dimensions to make parts fit stock.
- `/simple-english` — **vendored third party** (MIT, AminBlg/SimpleEnglish, pinned commit in
  `.claude/skills/simple-english/VENDORED.md`). Writes or checks prose against ASD-STE100
  Simplified Technical English: 20-word procedural / 25-word descriptive sentences, one word
  one meaning, active voice, condition before command. Use it for **reader-facing prose** —
  README, install and build instructions, guide text, release notes, error messages, and
  future M2 fabrication instructions, where a builder with a sheet of aluminium and a saw
  should not have to read a sentence twice.

  **Where it does not apply, and why.** Do not run it over model `notes`, catalog `caveats`,
  docstrings that state validity limits, or anything covered by the honesty invariants above.
  STE restricts exactly the words that carry calibrated uncertainty — "should", "may",
  "might", "could" are unapproved modals — and a caveat reading "this gain is probably
  optimistic" must never become "this gain is optimistic". That is a change of claim wearing
  the costume of a style fix, and it is the single most likely way this skill could damage
  the project. **Clarity is a style question; certainty is a truth question. STE gets a vote
  on the first and none on the second.**

  Fabrication instructions (M2) are the strongest case for it: procedural text, a distracted
  reader, and an irreversible cut.

Later milestones add `/fabrication-packet` (M2), `/validate-model` (M6), `/characterize` and
`rf-measurement-analyst` (M7) — see plan §7.

## Current status

**N4 shipped — `v0.13.0` is released** (2026-08-09). The receiver track's point: a parts
catalogue spanning hobby modules to a 2.2 K cryogenic InP HEMT, and "which should I buy?"
answered against a real antenna.

**The rule this milestone had to get right** is where invariant 2 actually falls. A
datasheet's *headline* noise figure with a URL is a published fact, the same standing as a
source flux with an epoch. Fmin, Γopt, Rn and S-parameters are *measurement-grade design
data* and are still never shipped or inferred. So `receivers` does system budgets and does
not do amplifier design, there is no path from a catalogue entry to a `TwoPort`, and a test
asserts the absence of one. **If you are asked to add "just enough" noise parameters to a
catalogue entry so it can be matched or checked for stability, that is the line.**

**An honesty bug caught in its own first draft, worth remembering:** the advice ranked "a
perfect 0 K amplifier" against "use better cable" and let the impossible option win. A
ceiling is not an option. The verdict now ranks only actions and labels the 0 K figure
*"impossible, not a target"*.

**N6 (whole-system comparison) and N7 (algorithms) are deferred deliberately**, written up in
`plans/receivers.md` §6 rather than half-built — a system-level verdict is exactly the kind
of output people quote.

**N1 shipped — `v0.12.0` is released** (2026-08-09). Stability, and the check now runs
automatically on any active device the tool reads.

The milestone's method is worth copying: the textbook anchor (Pozar Ex 12.1) confirmed the
numbers, but the *stronger* verification was against the **definition** — unconditional
stability means `|Γin| < 1` for every passive load, which is checkable by brute force. K, μ
and that sweep agree on 4000 random networks, and `|Γin|` is exactly 1.000000000 at 500
points around the stability circle. When a quantity has a definition you can evaluate, check
against that rather than against another formula.

Writing those tests found a trap worth keeping: **a Smith-chart sweep can step straight over
an unstable region.** Some devices have an unstable patch a few thousandths across, well
inside the passive disk; a 600 × 600 grid misses it and declares the part safe. Sampling can
only miss an unstable region, never invent one — so a clean sweep is weak evidence.

**N4 is the next one worth doing**, not N2. N4 is the milestone the track exists for
("would a better LNA help, or is spillover my problem?"), N0+N1 are its prerequisites, and
N2/N3 are for building an amplifier from a bare transistor — which most people should not do.
The plan's numbering is not its value ordering, and `plans/receivers.md` says so.

**N0 shipped — `v0.11.0` is released** (2026-08-09). The receiver track has started, and the
tool can now read a vendor's `.s2p` with NumPy alone, name the three gains separately instead
of conflating them, and hand a network straight to M4's noise budget.

**The N0 review found one real physics error**, and it is the most instructive thing in the
milestone: `as_stage` used **insertion loss** (`|S21|²`) where Friis needs **available loss**
(`1/G_A`). Those agree only for a matched network, and a measured `.s2p` never is — a bare
series 200 Ω gave 2320 K where the truth is 1160 K. Every test was green, because every
anchor was a matched attenuator, the one case where the two definitions coincide.

**The lesson, now in `docs/lessons-learned.md`: an exactly-analysable anchor can be exactly
the wrong anchor.** Ask of any clean anchor what its cleanliness makes degenerate. An ideal
component is usually clean because several distinct quantities have collapsed into one, and
each collapse is a bug you cannot see. The replacement anchor is a bare series resistor —
still exact, but mismatched.

The same review also fixed: `NoiseParameters` not carrying the file's Z0 (Rn is stored
normalized); unstable devices returning negative power ratios instead of raising; silent
extrapolation of noise data; the reader accepting 3-port and Y-parameter files; `s_to_y`
routing through a Z matrix that need not exist; and `is_reciprocal` using a tolerance no
measured cable could meet.

Two more, worth remembering because both were caught by something other than the code under
test:

- The CLI printed *"these are equal because both terminations are matched"* above three
  visibly different numbers. Matched terminations are not enough — the gains collapse to
  `|S21|²` only when the **device** is matched too. It would have taught exactly the
  confusion the module exists to prevent.
- `cascade`'s frequency-grid guard never fired, because `np.allclose` **raises** on mismatched
  shapes rather than returning `False`. The check has to compare shapes first. Found by the
  test written for the error message, not by the error.

**N1 (stability) is next**, and is the highest-value single milestone in the track: Rollett's
K and Δ, the μ-factor, and stability circles. An unstable amplifier costs someone a weekend of
confusion, and the check is cheap. The stability test should then run automatically on any
amplifier the tool touches, the way realizability runs on any pyramidal horn.

**M9 shipped — `v0.10.0` was released** (2026-08-09), together with `docs/`. The UI ships
without htmx, without a charting library and without a CDN — 0.12 ms synthesis means an HTTP
round trip is network-bound, so inline JavaScript plus server-rendered SVG is enough, and it
works offline where antennas actually get built.

Building it surfaced that synthesis returns a **205 m aperture** for 30 dBi at 20 MHz:
bounded by physics, a long way past bounded by sense. Both design types now carry
buildability notes, in the model rather than the presenter, so the CLI gained them too.

**Everything the `v1.0.0` gate needs now exists.** It is not a feature: it is tagged once one
antenna has been designed here, built from this tool's fabrication output, and measured back
in through M7 (VNA) and M8 (sky). A 21 cm test horn would close it.

**M8 shipped — `v0.9.0` was released** (2026-08-09). On-sky characterization, and the
cross-repo contract with `jansky-observe` honoured exactly as written at M0 — no changes were
needed on that side.

Three traps this milestone encodes, all of which flatter a careless measurement: the
**Y-factor is ill-conditioned near unity** (0.1 dB moves Tsys by >100 K at a 1 dB ratio, so
weak results are labelled upper bounds); a **drift scan needs linear power, not dB** (half a
dB value is not the half-power point, and the error narrows the beam); and **averaging
spectra in dB** is wrong in the direction that makes quiet data look better.

**M9 (the interactive UI — FastAPI + htmx + canvas) is next**, and it is the last milestone
before the `v1.0.0` gate, which is not a feature but a real antenna designed here, built from
this tool's fabrication output, and measured back in through M7 and M8.

**M7 shipped — `v0.8.0` was released** (2026-08-09). Measurement ingest, and the milestone
where invariant 5 became structural rather than aspirational: `Comparison` keeps prediction
and measurement in separate fields with nothing combining them, and a test asserts no such
field exists.

The reference plane is the thing to remember here: a VNA measures at its own port, and at
VHF half a metre of coax rotates S11 most of the way round the Smith chart. Most
"model disagrees with reality" reports are an un-de-embedded cable.

**M8 (on-sky characterization — Y-factor Tsys, drift-scan beam maps, transit SEFD from
jansky-observe bundles) is next**, and it is the last one before the UI.

**M6 shipped — `v0.7.0` was released** (2026-08-09). Tier 2 exists, and it closed both
tickets M5 wrote: the short-boom Yagi gap (4.47 analytic vs 6.49 MoM vs 6.75 published) and
the JOVE mutual coupling (2.75 dB stacking rather than the ideal 3.01, with feed impedance
shifting 17 ohms when the neighbour appears). The JOVE one is an **honest partial** — NASA's
pair implies ~2.0 dB, so about a quarter of the gap is recovered and the rest is still open.

Watch for two traps this milestone hit: the solver's gain array holds
`[component_1, component_2, total]`, so reading index 0 silently returns one polarization
(it surfaced as impossible negative Yagi gain); and mismatch is a **ratio**, so judging a
match by `|Z - 50|` is wrong — 20 and 80 ohms are equidistant by difference and have SWRs of
2.5 and 1.6.

**M7 (measurement ingest — scikit-rf, NanoVNA Touchstone, measured vs predicted) is next**,
and M6 hands it the predicted feed impedances to compare against.

**M5 shipped — `v0.6.0` was released** (2026-08-09). Wire antennas, and with them the
`radio-jove` and two `graves-yagi-*` catalogue entries that waited from M0 for a model that
could evaluate them. Anchors: NASA's published 5.8 dBi single-dipole gain (we get 5.89 over
average ground) and their 23.28 ft element length (we get 23.24).

Two disagreements kept rather than tuned: the JOVE dual dipole overshoots by ~1 dB (mutual
coupling, which pattern multiplication cannot represent) and the 3-element Yagi estimate runs
2.3 dB low (the endfire bound assumes a long array, and the model warns about exactly that).
Both are M6 entry tickets.

M5 shipped **less than its plan row promised, on purpose**: no helical, log-periodic or Moxon
models, and Yagis by boom length only.

**M6 (Tier-2 MoM validation, pymininec backend) is next** — and it has a ready-made first
job, since both GRAVES entries carry full published element geometry in their caveats,
waiting for a solver that can consume it.

**M4 shipped — `v0.5.0` was released** (2026-08-09). Antenna numbers became telescope
numbers: Tsys as an actionable budget, SEFD, G/T, the radiometer equation, time-to-detect,
and "how big a dish do I need" solved backwards. Anchors: BHARAT's published K/Jy to 0.3%,
the standard 3.41 K cold sky, and a **real** cross-check against the sibling course's
radiometer equation (CI checks `jansky` out rather than letting the test skip).

**`v0.5.1`** then landed the catalogue once verified (Perley & Butler 2017 cross-checked
against Trotter 2017). Verification found three errors, one already released: the zenith
atmosphere term was 2.5 K and is 2.0 K; Cas A is 1768 Jy at **epoch 2016**, not the
~1900-2000 Jy often repeated; and Tau A is 829 Jy fading at 0.10 %/yr, not 875 at 0.15 %/yr.
Two lessons stuck: **a flux without an epoch is a half-truth** (Cas A fades, non-uniformly),
and **catalogued HI brightness is a 16-36 arcmin survey peak while an amateur beam reads a
degrees-wide average** — lower wherever emission is structured.

**M5 (wire antennas & arrays) is next** — and it unlocks the Radio JOVE dual-dipole and
meteor-scatter yagi catalog entries that have been held back since M0.

**M3 shipped — `v0.4.0` was released** (2026-08-08). Dish efficiency is now *computed* from a
feed pattern rather than typed in, feeds match to dishes in both directions, blockage comes
from physical parts, and the waveguide probe/backshort design fills the gap M2 named.

Its anchors, both external: the **-10.9 dB optimum edge taper emerges** from maximizing
efficiency (it is never an input) for every feed shape tried, and the **probe design
reproduces PhysicsOpenLab's published, built 21 cm horn** to a third of a millimetre.

Carried gap, now deferred twice and worth being honest about: **conical horn patterns are
still rules of thumb**. `conical_horn_feed()` is the usable stopgap and says so.

**M4 (sensitivity — G/T, SEFD, Tsys, radiometer, time-to-detect) is next**, and it is the
milestone that turns antenna numbers into telescope numbers.

**M2 shipped — `v0.3.0` was released** (2026-08-08). A design now becomes cut metal:
exact flat developments for both horn types, 1:1 tiled SVG templates, DXF, cut list with an
honest kerf budget, assembly checklist, and `design.json` provenance.
`jansky-forge fabricate --gain-dbi 18 --out ./horn` writes the lot.

Two M2 rules that must survive future edits: **the 100 mm ruler on every sheet is not
decoration** (it is the only defence against a "fit to page" print, which is invisible until
the metal is cut and wrong), and **kerf is reported, never silently applied** to anybody's
dimensions. `/fabrication-packet` carries the pre-flight.

**M3 (dish and feed system) is next** — f/D, edge taper, spillover, and feed selection as a
solved system rather than assumed constants. It also picks up the two gaps M1 and M2 leave:
conical *patterns* (still rules of thumb), and the probe/backshort design a horn needs
before it is an antenna rather than a shaped piece of metal.

**M1 shipped — `v0.2.0` was released** (2026-08-08). Horns became physics: exact aperture
phase error, synthesis in both directions, realizability, and aperture-integrated patterns.
Verified against Balanis Examples 13.5 and 13.6. It found two real things — a 7% geometry
bug in our own first attempt (see invariant 7), and that the catalog's worked example is not
a buildable horn. `jansky-forge design --gain-dbi 18` now turns a target into dimensions.
**M2 (fabrication: fold-up templates, DXF, cut lists, BOM) is next** — the cut-panel slants
it needs are already computed. Known gap carried forward: conical *patterns* are still the
optimum-flare rules of thumb (the gain is exact); the notes say so.

**M0 shipped — `v0.1.0` was released** (2026-08-08,
[release](https://github.com/joebarbere/jansky-forge/releases/tag/v0.1.0)). `units`, `core`,
`bands`, `apertures`, `catalog` with the audit, the CLI, the M0 skills and the
physics-reviewer agent, CI + release workflows. 66 tests, 99% coverage, green on all three
OSes. The 700 mm dish golden test reproduces the station's own ~18 dBi / ~21° figures at
1420 MHz, which is the package's first end-to-end sanity anchor.

Two things the first CI run taught us, both fixed and worth not re-learning:

- **Windows consoles are cp1252** and cannot encode λ, °, or ² — the CLI crashed mid-output
  until `cli._ensure_utf8_stdout()` reconfigured the stream. Setting `PYTHONIOENCODING` in CI
  would have greened the job and left every real Windows user broken. A test now asserts those
  characters are still present so nobody "fixes" a future report by removing them.
- **`uv build` writes a `dist/.gitignore`**, which a `files: dist/*` glob happily uploaded to
  the release as junk. The workflow now names `*.whl` and `*.tar.gz` explicitly.

**M1 (horn designer) is next**: gain→dimensions synthesis in both directions, the Balanis
aperture-phase-error correction that replaces the current optimum-flare assumption, and E/H
pattern computation. See plan §5.
