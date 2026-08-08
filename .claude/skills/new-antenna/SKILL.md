---
name: new-antenna
description: Scaffold a new antenna family in jansky-forge — a frozen dataclass implementing the AntennaModel protocol, with validity notes, golden tests, and protocol conformance. Use when adding a dish variant, horn variant, or any wire-antenna family.
---

# Add a new antenna family

Every model in this package is a **frozen dataclass** with two public methods and no I/O. That
uniformity is what lets sweeps, the optimizer, the UI, and the report generator treat any
antenna identically.

## 1. The shape

```python
@dataclass(frozen=True)
class YourAntenna:
    kind: str = "Human-readable family name"
    # design variables, SI units (exception: workshop units like *_mm where a builder
    # measures in them — say so in the docstring)

    def __post_init__(self) -> None:
        # reject impossible geometry here, with a message naming the offending value

    def parameters(self) -> dict[str, float]:
        # flat, JSON-able; this is what a slider drives and a template consumes

    def characterize(self, freq_hz: float) -> Characterization:
        # pure; build the result with characterization_from_gain(...)
```

Use `characterization_from_gain` rather than filling `Characterization` by hand — it derives
effective area from the gain via A_e = Gλ²/4π, so the reported area is always consistent with
the reported gain.

## 2. Non-negotiables

- **Pure.** No file access, no network, no caching, no global state. The interactive tier's
  honesty depends on this.
- **Cite the formula.** A comment or docstring naming the source (Balanis chapter, Kraus,
  a specific paper) for every non-obvious equation. "Where did this constant come from" must
  never be unanswerable.
- **State validity limits in `notes`.** If the model degrades below a few wavelengths, or
  assumes optimum flare, or ignores mutual coupling — the `Characterization` must say so, in
  the conditions where it applies. A model that quietly returns a wrong number outside its
  domain is the failure mode this rule exists to prevent.
- **Units at the boundary.** SI internally. Any degrees/millimetres field is a deliberate
  ergonomic choice and gets a docstring line explaining it.

## 3. Tests (in `tests/test_<family>.py`)

1. **A golden value** computed by hand, with the arithmetic in a comment so the next reader
   can check it rather than trust it.
2. **Scaling properties** — gain versus size, beamwidth versus size, frequency dependence.
   These catch the errors that a single golden value cannot.
3. **Validation** — `pytest.raises` for each rejected geometry.
4. **Protocol conformance** — `assert isinstance(model, AntennaModel)`.
5. **Notes present** where the model is outside its comfort zone (assert the note fires).

## 4. Wire it up

Export it from `__init__.py`, add it to the CLI's reachable set if it needs one, and consider
whether a catalog entry should exist (`/catalog-entry`). Update `plans/jansky_forge.md` if this
completes or changes a milestone.

## 5. Verify

`/verify`, then have `antenna-physics-reviewer` read the diff — it hunts exactly the bugs this
kind of change produces (10 vs 20·log10, mm vs m, degrees vs radians, a missing 4π).
