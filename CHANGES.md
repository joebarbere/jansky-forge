# Changelog

All notable changes to jansky-forge. Pre-1.0 semver: **minor = milestone, patch = fixes
between milestones** (see `plans/jansky_forge.md` §5).

## [Unreleased]

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
