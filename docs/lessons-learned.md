# Lessons learned

Why the code is shaped the way it is. Each of these was paid for.

---

## Self-consistency is not verification

**What happened.** M1's first implementation had a 7% error in the axial-to-apex-distance
conversion — Balanis's `ρ_e`/`ρ_h` are *slant* distances and `ρ₁`/`ρ₂` are *axial*, and the
wrong one was used.

**Why it was dangerous.** Every internal check stayed green. Synthesis round-tripped exactly.
Efficiency came out at the textbook 51%. Phase deviations landed precisely on 1/4 and 3/8.
The error sat in a conversion that *everything downstream shared*, so the whole system was
consistently wrong.

Only checking against Balanis's **published worked examples** exposed it.

**The rule.** Every physics milestone needs an *external* anchor — a published number from a
source that has never seen your code. Tests that agree with each other prove only that they
agree with each other.

**How it shows up in this project.** Every milestone since M1 opens by finding an external
anchor before writing code:

| Milestone | Anchor |
|---|---|
| M1 | Balanis Examples 13.5 and 13.6 |
| M3 | The −10.9 dB optimum edge taper; PhysicsOpenLab's published probe geometry |
| M4 | BHARAT's published K/Jy; the standard 3.4 K cold sky; the sibling course |
| M5 | NASA's published JOVE gain and element length |
| M6 | Two published GRAVES Yagi designs |
| M7 | scikit-rf reading the same file |
| M8 | The real jansky-observe bundle schema |

---

## A guard that only ever skips is not a guard

Optional dependencies invite `importorskip`, and a skipped test protects nothing. Every
optional path in this project is **installed in CI so its tests actually run**:

- the `jansky` course, for the radiometer cross-check (M4)
- `pymininec`, for Tier-2 validation (M6)
- `scikit-rf`, for the Touchstone reader cross-check (M7 one-port, N0 two-port)

Verify in the CI log that they *passed* rather than skipped. It has been checked each time.

**And the lesson caught itself at N0.** The CI step installs the extras and then names the
test files explicitly. A new module's tests are not in that list, so N0's scikit-rf
cross-check — written specifically to run in CI — skipped on the first push, while the job
went green. Checking the log is what found it.

The naming is the flaw: an allow-list has to be extended by whoever adds a test, and nothing
reminds them. It stays for now because the alternative (run the whole suite again with extras
installed) doubles a step that already takes most of the job, but **adding a milestone means
adding its test file to that line** — and then reading the log to confirm the count went up.

---

## An exactly-analysable anchor can be exactly the wrong anchor

N0's anchors were a matched attenuator: three gains equal to −L dB, cascades summing in dB,
round trips at machine precision. All exact, all externally checkable, all green — and a
matched network is precisely the case where insertion loss and available loss are the same
number, so the one real physics error in the module was invisible to every one of them.

An anchor has to be **exact and representative**. The fix was a bare series resistor: still
exactly analysable, but badly mismatched, so the two definitions separate by a factor of two.

The pattern generalizes. Ask of any clean anchor: *what does its cleanliness make degenerate?*
An ideal component is usually clean because several distinct quantities have collapsed into
one, and each collapse is a bug that cannot be seen.

---

## Disagreements are information; tuning them away destroys it

Published figures live in `Template.published` as **cross-checks**, never restated as our
output. When the model disagrees, the disagreement is recorded — and often turns out to be
the most useful thing on the page.

Kept disagreements and what each taught:

| Case | Gap | What it meant |
|---|---|---|
| PICTOR beamwidth | 9.85 vs 8.95° | Illumination taper differs; both inside the textbook range |
| Itty Bitty beamwidth | 3.8 vs 3.0° | An offset ellipse modelled as a circle |
| JOVE dual dipole | 8.90 vs 7.8 dBi | Mutual coupling — invisible to pattern multiplication |
| 3-element Yagi | 4.47 vs 6.75 dBi | The endfire bound assumes a *long* array |

**Adjusting an efficiency until the numbers match destroys the model's independence**, which
was the only thing that made the cross-check worth having.

---

## When a later milestone proves an earlier claim wrong, correct it visibly

M0 predicted 19.46 dBi for the BHARAT horn against a published 20.6 and attributed the gap to
its Potter dual-mode design. M1 modelled the actual phase error, got 20.25, and the gap fell
to 0.35 dB — so **most of the "dual-mode advantage" had been M0's own mismodelling**.

The fix records both the old explanation and why it was superseded. Silently overwriting a
stale claim destroys the reader's ability to trust any of the others.

---

## Ship less than the plan, and say so

Three times a milestone deliberately shipped less than its plan row promised:

- **M5** modelled Yagis by boom length only, and shipped no helical, log-periodic or Moxon
  models at all. Element design is what a method-of-moments solver is for.
- **M1 and M3** both deferred conical *patterns* — twice — rather than invent one.
- **M4** shipped without a calibrator catalogue until the fluxes could be verified.

Each was recorded in the plan and the changelog. **A roadmap that quietly ships less than it
says becomes fiction**, and a plausible-looking model is worse than an admitted gap.

---

## A model with a known failure mode beats one that hides it

M5's Yagi estimate is 2.3 dB low on a short boom — and a test **asserts** the shortfall,
because the Hansen-Woodyard bound's own validity condition predicts it. A model that quietly
returned a plausible number there would be worse than one visibly wrong for a stated reason.

---

## Verification catches errors in what you were *about* to ship

The M4 flux verification found three wrong numbers, **one already released** (the zenith
atmosphere term, 2.5 K → 2.0 K, which made every published Tsys half a kelvin pessimistic).

Verify before shipping, not after — and when you find something already out, say so plainly
in the changelog rather than fixing it quietly.

---

## Do not tune a model to match a measurement, even a good one

The sky model gives 3.41 K against a *measured* 3.58 K. That gap was left in place: it sits
inside the surveys' own zero-level uncertainty, and part of it is an extragalactic background
a single power law cannot represent.

The test asserts **closeness, not equality**. A test demanding exact agreement is an
invitation for someone later to fudge the constant.

---

## Provenance is a field, not a convention

Catalogue entries carry a source URL, and `catalog.audit()` makes that executable — CI fails
on any output. Non-primary provenance *requires* recorded caveats.

Consequences that fell out of enforcing it: KrakenRF publishes **no** gain figure for the
Discovery Dish; there is no "DSES horn" and no "ezRA horn"; the Haystack SRT has no canonical
diameter; and one widely-repeated Discovery Dish spec traces to no primary source at all.

---

## Performance is a design choice, not an optimization pass

Three times a first working version was too slow, and each fix was structural:

| What | Before | After | How |
|---|---|---|---|
| Beamwidth (M1) | 400 ms | 1.4 ms | Root-find the −3 dB crossing instead of rendering a pattern |
| Feed evaluation (M3) | 683 ms | 24 ms | Tabulate the pattern once; vectorized fixed quadrature |
| — | | 0.5 ms | per single evaluation |

The interactivity promise is kept by *choosing tractable physics*, not by caching. Any
proposal that would put a solver in the interactive path is answered by moving the feature to
a slower tier.

---

## Export, don't link

Three times the right answer was to generate someone else's input file rather than depend on
their code:

- **openEMS** decks (M2 planning) instead of owning an FDTD runtime
- **DXF** instead of a CAD library
- **NEC2** decks (M6) instead of linking a GPL solver into an MIT package

Rigor without the entanglement, and the output is inspectable.

---

## The same bug three times means the shape is wrong

Assigning two unrelated dataclasses to one variable across `if/else` branches broke mypy in
`cli.py` twice and `server/app.py` once. Recorded in the code where it happened, with the
count — a mistake made three times is a signal about the design, not about carelessness.

---

## Write the cross-repo contract down before you need it

M8 consumes `jansky-observe`'s observation bundle. The contract was written into this
project's plan at **M0**, eight milestones earlier — and when the time came, **no changes were
needed on the other side**. The schema identifier is checked, not assumed, so an upstream
change breaks loudly instead of mis-reading.

---

## Build the pipeline before the features

CI, the release workflow, and the version-consistency gate existed at M0, before there was
anything to release. Every milestone since has been a tag and a release with no ceremony.

The three-OS matrix earned itself on **the very first run**: Windows consoles are cp1252 and
could not encode `λ`, `°`, `²`, so the CLI crashed mid-output. Fixed in code rather than by
setting `PYTHONIOENCODING` in CI — the env-var route would have greened the job and left
every real Windows user broken.
