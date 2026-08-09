# Honesty invariants

The rules that make this project's numbers worth trusting. Violating one does not break a
test — it breaks the reason the tool exists. They are reproduced from `CLAUDE.md` with the
history that produced each.

Numbers here get used to cut metal and to decide whether a telescope will work. **A plausible
wrong number is worse than an obviously wrong one.**

---

### 1. Never tune a model to match a published figure

Published gains and beamwidths live in `Template.published` as *cross-checks*. If the model
disagrees, record the disagreement in `caveats`. Adjusting an efficiency until they agree
destroys the model's independence, which was the only thing that made the cross-check worth
having.

*History:* four disagreements are deliberately preserved — PICTOR, BHARAT, Itty Bitty, and
the 3-element Yagi. Each turned out to be informative.

### 2. Never invent a dimension

If a source does not state f/D, say so in `caveats` and use the model default *explicitly*.
The phrase to reach for is "*not stated by the source; the model's default is used*".

*Why it matters most:* someone will build to it.

### 3. Every catalogue entry carries a real source URL

`catalog.audit()` enforces this and CI fails on any output. Never "fix" an audit failure by
weakening the audit.

### 4. Models state their own validity limits

Every `Characterization` carries `notes` describing where it stops being trustworthy, and
those notes must actually *fire* in the conditions they describe. Every presenter — CLI, UI,
reports, API — prints them. **Suppressing a model's warnings to tidy output is not a trade
this project makes**, and a polished interface is the most tempting place to break this,
because a designed-looking number is more readily believed.

### 5. Predicted and measured never wear the same label

Structural since M7: `measure.Comparison` and `onsky.BeamComparison` each have a predicted
field and a measured field and **no third field combining them**. Tests assert no merged
field exists, so adding one later fails the suite.

If you want a single number, you must choose which — and defend the choice.

### 6. Never apply the point-source formula to extended emission

`T_A = S·A_e/2k` makes a bigger dish look like more signal. For a beam-filling source the
antenna temperature *is* the brightness temperature and aperture does not enter. `detect()`
routes by source type and states which formula it used.

Corollary: a huge predicted line SNR is reported as "thermal noise is not your limitation",
never as a promise — the real floor is baseline stability.

### 7. When a later milestone proves an earlier claim wrong, correct it visibly

Record both the old explanation and why it was superseded. Silently overwriting a stale claim
destroys the reader's ability to trust any of the others.

*History:* M1 corrected M0's account of the BHARAT gap; v0.5.1 corrected an atmosphere term
that had already shipped.

### 8. Self-consistency is not verification

Every internal check can pass while the whole system is consistently wrong. New physics needs
an **external** anchor — a published number from a source that has never seen the code.

→ [Lessons learned](lessons-learned.md#self-consistency-is-not-verification)

---

## Enforcement

| Rule | Enforced by |
|---|---|
| 1 | Cross-check tests with tolerances that encode the *disagreement* |
| 2, 3 | `catalog.audit()`, run in CI |
| 4 | Tests asserting notes fire; presenter tests asserting they are displayed |
| 5 | Tests asserting no merged field exists on the comparison dataclasses |
| 6 | `detect()` routing tests |
| 7, 8 | Review, and the `antenna-physics-reviewer` agent |

The `antenna-physics-reviewer` agent explicitly hunts for "any efficiency tuned to match a
published figure" — the cardinal sin.
