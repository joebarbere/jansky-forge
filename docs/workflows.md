# Workflows

Task-first recipes. Each is the shortest honest path from a question to an answer.

---

## "I want to see the hydrogen line. What do I build?"

```bash
jansky-forge bands                     # confirm what you are chasing
jansky-forge list --band hi            # what exists already
jansky-forge show discovery-dish       # what a known build actually does
```

Start from a catalogue entry rather than a blank sheet, and read its caveats — they are
inherited context you would otherwise have to discover.

**Reality check before buying anything:** a beam-filling source like galactic HI gives the
same antenna temperature at *any* aperture. A bigger dish buys angular resolution and
point-source sensitivity, not a stronger line. → [Traps](traps.md#gain-is-not-sensitivity)

---

## "Design and build a horn"

```bash
jansky-forge design --gain-dbi 18                        # gain in, dimensions out
jansky-forge fabricate --gain-dbi 18 --out ./horn \
    --tool jigsaw --seam-mm 8 --page a3                  # templates, DXF, cut list
jansky-forge probe --waveguide wr650                     # where the probe goes
```

Then, in order:

1. **Print at 100% / "Actual size", never "Fit to page".**
2. **Measure the 100 mm ruler on each sheet** before cutting anything.
3. Check the corner-edge length agrees on both panel types.
4. Cut on the waste side of the line. Deburr everything.
5. Join with an electrically continuous seam — a gap in a horn wall is a slot, and slots
   radiate.

`cutlist.md` and `assembly.md` in the packet are checklists; work through them.

---

## "What feed does my dish want?"

```bash
jansky-forge feed --f-over-d 0.35                  # what it wants
jansky-forge feed --f-over-d 0.35 --horn-gain-dbi 12   # how a real horn does on it
```

Aim for **−10.9 dB edge taper**. Too shallow and power spills onto 290 K of ground; too deep
and the outer dish is metal that is not working.

---

## "Will I actually see it, and in how long?"

```bash
jansky-forge sources                                          # what is up there
jansky-forge sensitivity --template discovery-dish --source cas-a --epoch-year 2026.5
jansky-forge sensitivity --template discovery-dish --source hi-inner-plane
```

Read the **Tsys breakdown**, not just the total — it tells you which term to fix. If
spillover beats the receiver, a better feed is cheaper than a better LNA.

---

## "Check my closed-form answer against real numerics"

```bash
pip install 'jansky-forge[mom]'
```

```python
from jansky_forge import mom

model = mom.yagi_model(freq_hz=143.05e6, elements_m=mom.GRAVES_7EL_ELEMENTS, radius_m=0.003)
print(mom.compare_with_analytic(model, freq_hz=143.05e6, analytic_dbi=11.24).summary())
print(mom.to_nec_deck(model, 143.05e6))   # or hand it to xnec2c / 4nec2
```

Worth doing when: elements matter (Yagis), elements couple (arrays), or you need **feed
impedance** — none of which Tier 1 can produce.

---

## "I built it. Is it right?" — the VNA

```python
from jansky_forge import measure

sweep = measure.read_touchstone("bench.s1p")
print(sweep.summary())

# Almost always needed first: the VNA measured through your cable, not at the antenna.
at_antenna = measure.shift_reference_plane(sweep, length_m=0.5, velocity_factor=0.66)

fraction, advice = measure.resonance_offset(at_antenna, design_freq_hz=1.4204e9)
print(advice)     # e.g. "2.06% low — shorten it by about 2.06%, then re-measure"
```

Then compare against the prediction:

```python
print(measure.compare(freq_hz=1.4204e9,
                      predicted_impedance_ohm=complex(70, -2),
                      measured=at_antenna).summary())
```

**Diagnose before you cut:** reactance off with resistance agreeing is a length error or a
stray cable; resistance off is loss, ground, or nearby metal.

---

## "I built it. Is it right?" — the sky

```python
from jansky_forge import onsky

bundle = onsky.read_bundle("observation-12-bundle.zip")   # from jansky-observe
print(onsky.bundle_y_factor(bundle).summary())            # measured Tsys
```

Beam, from a drift scan (linear power, not dB):

```python
result = onsky.drift_scan_beamwidth(time_s=t, power=p, declination_deg=58.0)
print(onsky.compare_beam(predicted_hpbw_deg=21.1, measured=result).summary())
```

Efficiency, from a transit of known flux:

```python
print(onsky.transit_effective_area(delta_t_k=0.195, flux_jy=1768.0,
                                   physical_area_m2=0.385, source_name="Cas A").summary())
```

**Order of operations:** Y-factor first (it calibrates the receiver in kelvin), then transit
efficiency (which needs that calibration to mean anything).

---

## "My vendor sent me an .s2p. What is this part?"

```bash
jansky-forge network lna.s2p --freq-mhz 1420
```

Read the output in this order:

1. **Is it reciprocal?** An amplifier that reads reciprocal has almost certainly been read
   wrong — two-port Touchstone is ordered `S11 S21 S12 S22`, S21 *before* S12.
2. **Which gain?** Three numbers are printed because they are three different quantities.
   Noise-figure work wants **available** gain.
3. **Is there a noise block?** Without one, no noise figure can be stated — and none will be
   invented.

Then put it in the system, where the question is actually answerable:

```python
from jansky_forge import twoport, sensitivity as sens

amp = twoport.read_touchstone_2port("lna.s2p")
pigtail = twoport.attenuator(loss_db=0.2, freq_hz=amp.freq_hz)
# as_stages threads each stage's real source match. Doing it stage by stage is optimistic.
receiver_k = sens.cascade_noise_temperature_k(
    twoport.as_stages([pigtail, amp], 1.4204e9, names=("pigtail", "LNA")),
)
tsys = sens.system_temperature(freq_hz=1.4204e9, receiver_k=receiver_k,
                               spillover_efficiency=0.93)
print(tsys.summary())      # says which term dominates -- that is the one to fix
```

**The point is the last line.** If spillover dominates, a better amplifier is the wrong
purchase. `receiver_k` is the receiver alone and is not Tsys; confusing the two flatters the
answer, because the terms left out are the warm ones.

---

## "Add a build to the catalogue"

1. Find the **primary** source. A forum post repeating a number is not a source.
2. Record `provenance`, `source_url`, and honest `caveats`. Community and worked-example
   entries *require* caveats.
3. Put any published performance figure in `published` — a **cross-check**, never restated
   as our output — and add a test comparing it against the model.
4. **When they disagree, record the disagreement.** Never tune an efficiency to close it.
5. `make audit` must print nothing.

The `/catalog-entry` skill walks this.

---

## "Run the UI"

```bash
pip install 'jansky-forge[ui]'
jansky-forge serve                     # http://127.0.0.1:8000
```

No CDN, no build step — it works offline, which is where antennas get built.

---

## Before every commit

```bash
/verify        # lint → format → typecheck → coverage → catalog audit → CLI smoke
```

Or by hand: `make lint typecheck cov audit`.
