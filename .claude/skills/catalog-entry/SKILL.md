---
name: catalog-entry
description: Add a known antenna build to the jansky-forge catalog with the provenance discipline enforced — find the primary source, record gaps as gaps, and add the published-figure cross-check. Use when adding any new template.
---

# Add a catalog entry

The catalog's value is that its numbers are trustworthy *and say how trustworthy they are*. A
convincing entry with an invented dimension is worse than no entry, because someone will cut
metal to it. This skill exists to make that failure hard.

## 1. Find the primary source — not a summary of it

Preference order: manufacturer datasheet or shop page → the instrument's own documentation or
paper → a detailed community build guide with dimensions. A forum post repeating a number is
not a source. Record the URL you actually read.

Set `provenance` honestly:

| Value | Means |
|---|---|
| `MANUFACTURER` | Datasheet/shop page for a product you can buy |
| `PUBLISHED` | Peer-reviewed paper or observatory instrument documentation |
| `COMMUNITY` | A well-documented amateur build guide |
| `WORKED_EXAMPLE` | Geometry *we* chose as a teaching example — not copied from any build |

`COMMUNITY` and `WORKED_EXAMPLE` entries **must** carry `caveats`; the audit enforces it.

## 2. Record gaps as gaps

If the source gives a diameter but not f/D, do **not** fill in 0.4 silently. Either:

- omit it and use the model default, **and** add a caveat naming the assumption, or
- say in `caveats` that the number is unverified and must be measured before building.

The phrase to reach for is "*not stated by the source; the model's default is used*". Never
write a plausible number as if it were sourced. If two sources disagree, record both in a
caveat — a disagreement is information.

## 3. Published figures are cross-checks, never our output

Any gain or beamwidth the source publishes goes in `published`, and stays there. Then add a
test in `tests/test_catalog.py` comparing our model's prediction against it with a stated
tolerance.

**When the model disagrees with the published figure, that is a finding, not a bug to tune
away.** Record the disagreement in `caveats` with both numbers. Adjusting an efficiency factor
until the output matches a published gain destroys the model's independence and is explicitly
forbidden.

## 4. Write the entry

Add it in `src/jansky_forge/catalog.py` via `register(Template(...))`, keeping entries grouped
by antenna family and alphabetical within the family. Required: `slug` (kebab-case, stable —
it is a user-facing identifier), `name`, `model`, `design_band`, `summary` (one sentence on
what this build is *for*), `provenance`, `source_url`.

## 5. Verify

```bash
make audit          # must print nothing
uv run jansky-forge show <new-slug>
make cov
```

Read the `show` output critically: does the predicted beamwidth match what the source claims?
Does the efficiency look plausible for this construction? An entry that computes something
absurd usually means a unit error in the geometry (millimetres entered as metres is the
classic).

Then `/verify` and open the PR.
