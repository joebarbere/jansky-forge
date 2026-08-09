# jansky-forge documentation

Everything learned building this tool, organised so you can find it when you need it rather
than when you happen to read it.

## Start here

| If you want to… | Read |
|---|---|
| Avoid the mistakes that cost people antennas | **[Traps](traps.md)** |
| Look up a number from memory | **[Rules of thumb](rules-of-thumb.md)** |
| Actually build something, start to finish | **[Workflows](workflows.md)** |
| Understand *why* the code is shaped this way | **[Lessons learned](lessons-learned.md)** |
| Know what the tool can't do | **[Known limits](known-limits.md)** |
| Check a number against its source | **[Verification log](verification-log.md)** |
| Contribute without breaking the honesty rules | **[Honesty invariants](honesty-invariants.md)** |

## The five-minute version

Four facts that recur everywhere in this project:

1. **Interactivity is a physics choice.** Aperture antennas many wavelengths across are
   exactly where closed-form theory is accurate, so a slider is live because the equations
   are algebraic — not because anything is cached.
2. **Gain is not sensitivity.** A bigger dish collects more from a *point* source. Galactic
   HI fills the beam, and a beam-filling source gives the same antenna temperature at *any*
   aperture. → [Traps](traps.md#gain-is-not-sensitivity)
3. **Self-consistency is not verification.** Every internal check can pass while the whole
   system is consistently wrong. Only an external anchor catches that.
   → [Lessons learned](lessons-learned.md#self-consistency-is-not-verification)
4. **A prediction and a measurement are different kinds of claim** and must never be merged
   into one number. → [Honesty invariants](honesty-invariants.md)

## Reference by module

| Module | Milestone | What it owns |
|---|---|---|
| `units` | M0 | Constants and conversions. One file, so a unit bug is a one-file bug |
| `core` | M0 | The `AntennaModel` protocol and `Characterization` |
| `bands` | M0 | The frequencies that matter, and why |
| `apertures` | M0 | Parabolic dish, pyramidal and conical horn models |
| `catalog` | M0 | Known builds, with enforced provenance |
| `horns` | M1 | Exact phase-error gain, synthesis, patterns, realizability |
| `fabricate/` | M2 | Flat developments, 1:1 SVG templates, DXF, cut lists |
| `feeds` | M3 | Illumination, spillover, feed matching, waveguide probes |
| `sensitivity` | M4 | Tsys, SEFD, G/T, radiometer, source catalogue |
| `wires` | M5 | Dipoles, ground reflection, arrays, Yagi estimate |
| `mom` | M6 | Tier-2 method-of-moments validation |
| `measure` | M7 | Touchstone, reference plane, matching, comparison |
| `onsky` | M8 | Y-factor, drift scans, transit efficiency, bundle ingest |
| `server/` | M9 | The web UI |
