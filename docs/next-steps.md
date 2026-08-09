# Next steps

Where this project goes from here, and what "done" means. All ten planned milestones (M0–M9)
have shipped; **what remains before 1.0 is not code.**

---

## The v1.0.0 gate

> **v1.0.0 is not a feature.** It is tagged once **one antenna has been designed in this
> tool, built from its fabrication output, and measured back into it.**

That was written into the plan at M0, before any of the machinery existed. Every piece of the
loop now does:

| Step | Exists since | Command |
|---|---|---|
| Design it | M1 | `jansky-forge design --gain-dbi 18` |
| Cut it | M2 | `jansky-forge fabricate --gain-dbi 18 --out ./horn` |
| Feed it | M3 | `jansky-forge probe --waveguide wr650` |
| Predict what it will hear | M4 | `jansky-forge sensitivity --diameter-m …` |
| Check the model with numerics | M6 | `mom.compare_with_analytic(...)` |
| Measure it on the bench | M7 | `measure.read_touchstone("bench.s1p")` |
| Measure it on the sky | M8 | `onsky.read_bundle(...)` |

**Nothing is blocking except the build.**

### The obvious candidate: a 21 cm test horn

It is the right first build for four reasons:

1. **Cheap and quick** — aluminium sheet, an afternoon.
2. **Published comparison points exist** — BHARAT (a peer-reviewed, fully characterized
   21 cm horn) and the DSPIRA classroom build.
3. **It exercises the whole chain**, including the parts that are hardest to trust: the
   fabrication templates, the probe design, and both measurement paths.
4. **It is useful afterwards** — a horn is a dish feed, so M3's feed matching has something
   real to work with.

Suggested sequence:

```bash
jansky-forge design --gain-dbi 18                        # or 15 for something smaller
jansky-forge fabricate --gain-dbi 18 --out ./horn --tool jigsaw --seam-mm 8 --page a3
jansky-forge probe --waveguide wr650
```

Then: **print at 100%, measure the ruler**, cut, assemble, and take it to the VNA before it
ever sees sky. Read the [build workflow](workflows.md#design-and-build-a-horn) in full.

### What "measured back in" should produce

- A `.s1p` from the VNA → `measure.compare()` against the predicted feed impedance.
- A sky/ground pair from `jansky-observe` → `onsky.bundle_y_factor()` for a measured Tsys.
- Ideally a drift scan → `onsky.compare_beam()` for a measured beamwidth beside the
  predicted one.

If any of those disagree, **that is the interesting result**, and it belongs in
[verification-log.md](verification-log.md) alongside everything else.

---

## The receiver track, running in parallel

Since this document was written, a second track started: **N0–N5**, planned in
[`plans/receivers.md`](../plans/receivers.md). It closes the gap M4 opened — the tool could
say *"your system is receiver-limited"* and had nothing to offer next.

**N0 has shipped** (`v0.11.0`): two-port Touchstone, S↔Z↔Y↔ABCD, the three gain definitions,
cascade, and the seam back to M4's noise budget.

**N1 has shipped** (`v0.12.0`): K, Δ, μ, stability circles, MSG/MAG, and an automatic check
on any active device the tool reads. Anchored on Pozar Ex 12.1 and verified against the
definition of stability rather than another formula.

**N4 is now the next one worth doing** — it is the milestone the track exists for, and N0+N1
are its prerequisites. N2 and N3 (noise circles, matching synthesis) sit between them in the
plan's numbering but not in value: they are for building an amplifier from a bare transistor,
which most people should not do. Skipping to N4 is the recommended path.

**The track's recommended stopping point is N0 + N1 + N4** — read any vendor `.s2p`, know
whether the part is stable, and answer *"does a better LNA help my actual system?"* against
your own antenna. N2 and N3 (noise circles, matching synthesis) are for building an amplifier
from a bare transistor, which most people should not do. Stopping after N4 is a decision, not
an abandonment.

**It does not move the v1.0.0 gate.** That is still a build.

Cryogenic and detailed LNA noise modelling, listed in the post-1.0 roadmap below, is
superseded by this track.

---

## Gaps worth closing next

Ordered by how much each would improve the tool, not by effort. These are all **antenna**
track; the receiver track has its own ordering above.

### 1. Conical horn patterns — deferred twice

Conical *gain* is exact; conical *beamwidths* are still optimum-flare rules of thumb, so they
do not track a badly-flared design. M1 deferred it, M3 needed it and deferred it again with
`feeds.conical_horn_feed()` as a labelled stopgap.

**What it needs:** the circular-aperture TE11 far field. The aperture-integration method
already in `horns.conical_gain_by_aperture_integration` is the natural starting point — it
reproduces the Fresnel gain to 0.000 dB on the pyramidal case, so it is a trustworthy
instrument. Extending it to off-axis angles is the work.

**Why it matters:** a conical horn is the natural prime-focus dish feed, so this is the gap
most likely to be hit in real use.

### 2. The rest of the JOVE coupling gap

M6 recovered about a quarter of the ~1 dB shortfall between our dual-dipole prediction and
NASA's published figure. The remainder is probably ground interaction — where MININEC is
weakest — so this may need a better Tier-2 backend rather than more modelling.

### 3. Yagi element design

M5 models Yagis by boom length; M6 can solve real element geometry. What is missing is the
join: an *optimizer* that designs element lengths and spacings rather than just evaluating
someone else's. That is genuinely M10 territory (see below).

### 4. Wire families that were never modelled

Helical, log-periodic, Moxon. The plan listed them at M5 and they did not ship. A helix is the
most useful of the three — it is the SRT's feed, and circular polarization matters for some
work.

---

## The post-1.0 roadmap (from the plan, not scheduled)

| Idea | Note |
|---|---|
| **M10 — sweeps and optimization** (unnumbered now; see `CLAUDE.md` on tag allocation) | Parametric sweeps, Nelder-Mead/GA over any parameter set, constraint-driven design ("maximize G/T subject to D ≤ 1.2 m and it must fit through a door"), Pareto fronts |
| **M11 — full-wave export** | Generate runnable openEMS decks; import results back for comparison |
| **M12 — site and environment** | Terrain and horizon masks, RFI-aware siting fed by `jansky-observe` HackRF sweeps, wind loading, radome effects |
| **M13 — reports and provenance** | A design-report PDF and a citable design bundle: the `jansky-research` evidence standard applied to hardware |
| **M14 — MCP surface** | Claude as a design peer of the browser UI |
| Interferometry | Array layout and uv coverage |
| Phased arrays | Beamforming |
| Rotator integration | With `jansky-observe`'s M9 rotator control |
| ~~Cryogenic / LNA noise~~ | Superseded — this became the receiver track (N0–N5) |
| Public catalogue contributions | Currently PR-only while the provenance discipline is young |

**Parking lot** (decisions, not oversights): 3D geometry viewer, STL export for printed feeds,
waveguide component design, filter and diplexer design, antenna-range automation, ML
surrogates for the MoM tier.

---

## Open questions carried in the plan

1. Should the horn designer generate 3D-printable feed geometry, or stay sheet-metal only?
   *(Leaning: sheet metal, with STL in the parking lot.)*
2. Is the first real build a 21 cm test horn? *(Strongly suggested above.)*
3. Catalogue contribution flow: PR-only, or a data file others can extend? *(Leaning PR-only
   while the provenance rules are young.)*

---

## If you are picking this up cold

1. Read [getting-started.md](getting-started.md) for the mental model.
2. Read [traps.md](traps.md) before touching any physics. It is ordered by cost.
3. Read [honesty-invariants.md](honesty-invariants.md) before adding a catalogue entry or a
   model — those rules are what make the numbers worth anything.
4. `plans/jansky_forge.md` has the full milestone table and the per-milestone postscripts
   explaining where reality diverged from the plan.
5. Run `/verify` before every commit.

### Adding a milestone, the pattern that worked

Every successful milestone here followed the same shape:

1. **Find an external anchor first** — a published number from a source that has never seen
   this code. Before writing anything.
2. Verify the formulas against it, numerically, in a throwaway script.
3. *Then* write the module, with validity limits in `notes`.
4. Write tests that assert the anchor **and** assert any disagreement you chose to keep.
5. Ship less than planned rather than faking the remainder, and record what you dropped.

→ [Lessons learned](lessons-learned.md) for why each of those steps is there.
