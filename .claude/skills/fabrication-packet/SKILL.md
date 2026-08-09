---
name: fabrication-packet
description: Produce and pre-flight a jansky-forge fabrication packet — 1:1 templates, DXF, cut list, assembly steps. Use when someone is about to build an antenna, or asks for drawings, templates, cut lists, or "how do I actually make this".
---

# Produce a fabrication packet

The output of this skill gets cut into metal. A mistake here is not a wrong plot — it is a
ruined sheet, an afternoon, and possibly a finger. Slow down at the pre-flight.

## 1. Establish what is being built, and out of what

Before generating anything, get these settled. Ask only what you genuinely cannot infer:

- **The design.** An existing one, or synthesize with `/design-antenna` first. A packet
  built from a design nobody has sanity-checked just industrializes an error.
- **Material and thickness.** Aluminium sheet, tinplate, foil-faced foam board. Thickness
  drives the `--thickness-mm` note and whether the inner/outer distinction matters.
- **Cutting tool.** This sets the kerf: `shears`, `nibbler`, `jigsaw`, `bandsaw`, `laser`,
  `waterjet`, `plasma`. Guessing is worse than asking — nibbler kerf is 5 mm.
- **Joining method.** Rivets, screws, or conductive tape. This decides whether a seam
  allowance is wanted (`--seam-mm`), and how much.
- **Paper.** A4 or Letter is the default; a large horn is far better on A3 or from a print
  shop. Every taped joint is a chance to add error.

## 2. Generate

```bash
uv run jansky-forge fabricate --gain-dbi 18 --out ./horn-18dbi \
    --tool jigsaw --seam-mm 10 --thickness-mm 1.0 --page a4
```

Add `--shape conical`, `--band`/`--freq-mhz`, `--waveguide`, `--landscape` as needed.

## 3. Pre-flight — do not skip this

Read the generated files and check, reporting each:

1. **Sheet count.** If a template needs more than ~15 sheets, say so and suggest A3 or a
   print shop before the user prints 40 pages of A4.
2. **Stock size versus material.** Compare each `needs stock at least W x H mm` line against
   what the user actually has. A panel that does not fit the sheet is better found now.
3. **Material budget.** The cut list reports part area; real stock needs 1.5-2x for nesting
   waste on trapezoids. Check the BOM quantity is not being read as "buy exactly this".
4. **Corner-edge consistency.** `cutlist.md` states the corner edge. It must be the same on
   both panel types — the package computes it that way, but if a user hand-edits dimensions
   this is the check that catches an unbuildable set.
5. **Kerf double-compensation.** If the tool is a laser or waterjet, remind the user that
   the machine usually compensates in software. Applying kerf twice is a real and common
   error.
6. **Realizability.** If the design came from a published source rather than
   `design_pyramidal_horn`, check `jansky-forge show <slug>` for a "NOT a single buildable
   pyramidal horn" note. Do not generate a packet for a geometry the model has flagged
   without telling the user plainly.

## 4. Hand it over honestly

Tell the user, in this order:

- What to print and at what setting: **100% / "Actual size", never "Fit to page"** — and
  that they must measure the 100 mm ruler on the sheet before cutting anything. This is the
  single highest-value sentence in the whole handover.
- The predicted gain, labelled as a prediction. `design.json` records it with that caveat;
  keep the caveat when you repeat the number. A built horn is not a modelled horn until it
  has been measured.
- What is *not* designed yet: the probe, its position, and the backshort come at M3. A horn
  with no feed design is a beautifully-shaped piece of metal.

## What this skill must not do

Do not adjust dimensions to make a panel fit a sheet, round numbers to look tidy, or
"simplify" the geometry. The dimensions are the electrical design. If the parts do not fit
the stock, the answer is different stock or a different design — say so, and let the user
decide.
