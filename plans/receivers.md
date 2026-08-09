# The receiver track (N0–N5) — project plan

*Drafted 2026-08-09, after the antenna track (M0–M9) shipped. A companion to
[`jansky_forge.md`](jansky_forge.md), not a replacement: same repo, same conventions, same
honesty invariants.*

## 1. Why this belongs in jansky-forge

M4 taught the tool to say "your system is receiver-limited". It then had nothing to offer.
That is an unsatisfying place to stop, and it is a gap only this tool can close well —
because **it already knows the antenna**.

The question an amateur actually has is not "design me an LNA from a bare transistor". It is:

> Given my dish, my feed, my cable run and my sky — would a better amplifier help, or is
> spillover my problem? And if I buy this part rather than that one, what does Tsys become?

Nothing else can answer that, because nothing else has the feed pattern, the spillover
efficiency and the noise budget in the same head. **That is the differentiated value of this
track, and it is milestone N4.** Everything before N4 exists to make N4 trustworthy.

### The name stays

"Forge" is about making things, and a feed and its LNA are one physical assembly — the
Discovery Dish literally integrates them. Splitting the receiver into a sibling repo would
put the antenna and the amplifier in different heads, which is precisely what N4 needs them
not to be.

## 2. Scope, and the honest boundary

**In scope: choose, verify, and integrate.** Read a vendor's data, tell you whether an
amplifier is stable, work out what it costs you in system temperature, and compare a measured
noise figure against a predicted one.

**Out of scope, permanently:** bias network design, PCB layout, thermal design, EM
co-simulation, and anything implying you can go from this tool to a working board without a
VNA. Those are a different discipline with their own depth. Saying so now is cheaper than
discovering it at N3.

**Synthesis (N2/N3) is optional territory.** It earns its place only if someone genuinely
wants to build an amplifier from a transistor. The practical value is N0 + N1 + N4.

### Three constraints that shape everything

1. **We ship no transistor data.** Fmin, Γopt and Rn come from vendor `.s2p` files. Under
   [honesty invariant 2](../docs/honesty-invariants.md) we do not invent them, exactly as we
   refused a built-in cable-loss table. The tool analyses any part you have data for and
   designs nothing for one you do not.
2. **Ideal component values do not make a working 1.4 GHz amplifier.** Layout parasitics,
   ground vias and package effects dominate. Any matching result must say so as loudly as the
   fabrication templates say "print at 100%".
3. **`scikit-rf` already provides the numerics** — `nfmin`, `z_opt`, `rn`, `g_opt`,
   `stability`, `stability_circle`, `max_stable_gain`, and Touchstone noise parsing. It is
   already an optional extra here. We add the *design reasoning*, and cross-check against it
   rather than reimplementing it blind.

## 3. Milestones

Pre-1.0 semver continues: minor = milestone. The receiver track shares the version line with
the antenna track — this is one package.

| Tag | Milestone | What the release means |
|---|---|---|
| `v0.11.0` ✅ | **N0 — Two-port foundations** | `.s2p` reading with noise data, S↔Z↔Y↔ABCD, the three gain definitions, two-port cascade. The vocabulary everything else is written in |
| `v0.12.0` ✅ | **N1 — Stability** | Rollett K and Δ, the μ-factor, stability circles, unconditional vs conditional. **The highest-value single milestone** |
| `v0.13.0` | **N2 — Noise** | The noise-parameter model, noise circles, and the noise-versus-gain match tradeoff that *is* LNA design |
| `v0.14.0` | **N3 — Matching and the design loop** | Input matched toward Γopt, output conjugate; resulting F, gain and stability reported together |
| `v0.15.0` | **N4 — System integration** | **The point of the track.** This LNA + this feed + this cable → Tsys. "Would a better LNA help?" answered against a real antenna |
| `v0.16.0` | **N5 — Measurement** | Y-factor noise figure, gain measurement, measured-versus-predicted NF |

### N0 — Two-port foundations

Everything else is written in this vocabulary, so it has to be right.

- `TwoPort`: frequency, a 2×2 S-matrix per frequency, reference impedance, provenance.
- **Touchstone `.s2p` reading**, including the optional noise block. Native, like M7's
  one-port reader — this is a file a vendor ships and reading it should not require a
  network-analysis library.
- Conversions: S ↔ Z ↔ Y ↔ ABCD.
- The three gain definitions — **transducer**, **available**, **operating** — which are
  different numbers and are routinely confused.
- Cascade, via ABCD.
- The link back to M4: a passive network's noise figure equals its loss, and the two-port
  cascade must agree with `sensitivity.cascade_noise_temperature_k`.

**Anchors.** A matched attenuator is exactly analysable: `S11 = S22 = 0`,
`|S21| = 10^(−L/20)`, available gain `= −L` dB, noise figure `= L` dB. Two in series sum in
dB. With `Γs = ΓL = 0` all three gain definitions collapse to `|S21|²`. Plus a `scikit-rf`
cross-check on a real `.s2p`, run in CI as with M6 and M7.

**The trap to encode:** Touchstone two-port data is ordered `S11 S21 S12 S22` — **S21 before
S12**, unlike every other port count. Getting it wrong transposes the device, which for a
non-reciprocal amplifier means reading its reverse isolation as its gain.

### N1 — Stability

An unstable amplifier oscillates, and the symptom is a weekend of confusion: strange noise
floors, spurs, behaviour that changes when you touch the case. Cheap to implement, clean
anchor, prevents the most expensive failure mode. It goes second for that reason and not
because it is harder than noise.

- Rollett's K and Δ; the μ-factor (a single-number test, unlike K/Δ's two).
- Source and load stability circles.
- Unconditional versus conditional stability, stated in those words.
- **A stability check should run automatically on any amplifier the tool touches**, the way
  realizability runs on any pyramidal horn.

**Anchor:** Pozar, *Microwave Engineering*, ch. 12 worked example.

**Shipped as `v0.12.0`**, all of the above, plus MSG/MAG and a `StabilityReport` that names
the worst frequency rather than the design one. Two things learned: verification against the
*definition* (brute-force sweep of the passive disk) is stronger than the textbook anchor and
caught more; and a sweep **can miss a small unstable region entirely**, which is the concrete
argument for the closed-form circles.

### N2 — Noise

- `F = Fmin + (Rn/Gs)·|Ys − Yopt|²`.
- Constant-noise-figure circles.
- **The tradeoff.** Minimum noise and maximum gain want different source impedances. You
  cannot have both, and choosing between them is what LNA design *is*. A tool that silently
  optimises one is hiding the decision.

**Anchor:** a published transistor's datasheet noise parameters, plus the textbook example.

### N3 — Matching and the design loop

- Reuse M7's L-network; extend to stub and two-element matching.
- Input matched toward Γopt (not toward conjugate match — that is the tradeoff made concrete).
- Output conjugate-matched.
- Report F, gain **and** stability together, because a design that improves two and breaks the
  third is not a design.

**Anchor:** reproduce a published LNA design end to end.

**Mandatory caveat on every output:** these are ideal component values. At 1.4 GHz, layout
decides whether you get them.

### N4 — System integration

The milestone the track exists for.

- An `Amplifier` becomes a `sensitivity.Stage`, so the Friis cascade already written in M4
  consumes it directly.
- "Which of these parts should I buy?" — compare candidates against *your* antenna.
- **"Would a better LNA actually help?"** — the sensitivity analysis M4 can already almost
  do: if spillover is 21 K and the receiver is 36 K, halving the receiver's noise is worth
  less than fixing the feed, and the tool should say so with numbers.
- Cable-position analysis: M7 already prices a cable ahead of the LNA versus behind it.

**Anchor:** the station itself. Discovery Dish + QPL9547 + real cable, predicted against M8's
measured Y-factor.

### N5 — Measurement

- Y-factor noise figure — M8 already has the arithmetic **and** its ill-conditioning warning,
  which applies identically here.
- Gain measurement.
- Measured versus predicted NF, in separate fields with nothing combining them
  ([invariant 5](../docs/honesty-invariants.md)).

**Anchor:** a bench measurement on a real amplifier.

## 4. Recommended stopping point

**N0 + N1 + N4 is the whole practical value at roughly a third of the work.** Read any
vendor `.s2p`, know whether the part is stable, and answer "does a better LNA help my actual
system?". N2 and N3 are for building an amplifier from a bare transistor, which most people
should not do; N5 follows naturally once one exists on the bench.

If the track stops after N4, that is a success, not an abandonment — and it should be
recorded as a decision in the plan rather than left looking unfinished.

## 5. Open questions

1. ~~Should `TwoPort` and M7's one-port `MeasuredSweep` share a base type?~~ **Settled at N0:
   no.** They share `measure.parse_option_line` — the `#` line is identical for every port
   count — and nothing else. A common base type would have had to be generic over port count
   to hold anything real, which buys nothing when there are exactly two cases.
2. Does N2's noise-circle work want plotting in the M9 UI, or is a table enough? (Circles are
   one of the few genuinely visual results in this project.)
3. Is `scikit-rf` promoted from optional to required for this track, or does the native
   reader stay the default with scikit-rf as the cross-check? *(Leaning: native default, same
   as M7 — a vendor `.s2p` should be readable with numpy alone.)*
