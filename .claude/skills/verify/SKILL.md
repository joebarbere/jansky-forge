---
name: verify
description: The pre-commit gate for jansky-forge — lint, format check, typecheck, coverage (85% floor), the catalog provenance audit, and the CLI smoke. Use before every commit, and whenever asked whether the package still works end to end.
---

# Verify: is jansky-forge still honest and still working?

Run the steps **in order, stopping at the first failure**, and report pass/fail per step at the
end. Everything goes through `uv`; nothing here needs network or hardware.

## 1. Lint

```bash
make lint
```

## 2. Format check

```bash
uv run ruff format --check src/ tests/
```

## 3. Typecheck

```bash
make typecheck
```

## 4. Tests + coverage (85% floor)

```bash
make cov
```

The floor is `fail_under = 85` in `pyproject.toml` — a pass here means coverage held.

## 5. Catalog provenance audit

```bash
make audit
```

**This must print nothing.** Any output is a catalog entry missing a source URL, missing
caveats where its provenance is not a primary source, or referencing an unknown band. These are
honesty failures, not style failures — do not commit past them, and never fix one by deleting
the check.

## 6. CLI smoke

Proves the package installs, the catalog imports, and a model computes:

```bash
uv run jansky-forge bands
uv run jansky-forge list
uv run jansky-forge show discovery-dish
uv run jansky-forge characterize discovery-dish --band hi --band oh1667
```

Sanity-read the Discovery Dish output rather than just checking exit status: at 1420 MHz a
700 mm dish should show a beamwidth near 21° and gain in the high teens of dBi. A number far
from that means a model regression that the tests missed — say so.

## Report

One line per step (`lint: PASS`, …). On any failure: stop, show the failing output, and state
plainly that this must not be committed.
