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
  - `apertures.py` — `ParabolicDish`, `PyramidalHorn`, `ConicalHorn`, plus `ruze_efficiency`
    and `subtended_half_angle_deg`.
  - `catalog.py` — `Template`, `Provenance`, `register`/`get`/`find`/`all_templates`, and
    `audit()` (the executable form of honesty invariant 3).
  - `cli.py` — `bands`, `list`, `show`, `characterize`.
- `tests/` — pure, offline, no hardware and no network, ever. Golden values carry their
  arithmetic in a comment so a reader can check rather than trust.
- `plans/jansky_forge.md` — the full plan: survey, tiers, all fifteen milestones, testing
  strategy, cross-repo contracts, open questions.
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
| `v0.11.0` | M10 — Sweeps & optimization |
| `v0.12.0` | M11 — Full-wave export (openEMS/NEC decks) |
| `v0.13.0` | M12 — Site & environment (ground, terrain, RFI-aware siting, wind) |
| `v0.14.0` | M13 — Reports & provenance bundles |
| `v0.15.0` | M14 — MCP surface (Claude as a design peer) |
| `v1.0.0` | **Not a feature** — tagged after one antenna is designed here, built from this tool's fabrication output, and measured back in |

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

Later milestones add `/fabrication-packet` (M2), `/validate-model` (M6), `/characterize` and
`rf-measurement-analyst` (M7) — see plan §7.

## Current status

**M0 is being built (targeting `v0.1.0`).** Shipped so far: `units`, `core`, `bands`,
`apertures`, `catalog` with the audit, the CLI, the M0 skills and the physics-reviewer agent,
CI + release workflows. The 700 mm dish golden test reproduces the station's own ~18 dBi / ~21°
figures at 1420 MHz, which is the package's first end-to-end sanity anchor.

Nothing is published to GitHub yet — the repo is local, on a scaffold branch.
