---
name: release
description: The milestone-close procedure for jansky-forge — verify, changelog, version bump in both files, tag, and watch the release gate. Use when closing a milestone or cutting a patch release; never tag by hand.
---

# Release: close a milestone

Pre-1.0 semver, per `plans/jansky_forge.md` §5: **minor = milestone, patch = fixes between
milestones.** `v1.0.0` is not a feature — it is tagged only after one antenna has been designed
here, built from this tool's fabrication output, and measured back in.

## 1. Confirm the milestone is actually done

Read the milestone's row in the plan's table and check every promise in it shipped. If
something slipped, either finish it or move it explicitly (edit the plan, say so in the release
notes) — a milestone that quietly ships less than its table row is how a roadmap becomes
fiction.

## 2. `/verify`

Run the full gate. A red step ends the release.

## 3. Changelog

`CHANGES.md` gets a new section for this version: what shipped, what changed for users, and any
honest limitations discovered along the way. Every PR should already have added an `Unreleased`
entry — promote them.

## 4. Bump the version in **both** files

- `pyproject.toml` → `version = "X.Y.Z"`
- `CITATION.cff` → `version: "X.Y.Z"` **and** `date-released: "YYYY-MM-DD"`

`src/jansky_forge/__init__.py` carries `__version__` — keep it in step. The release workflow
checks tag == package version == `CITATION.cff` and refuses to publish a mismatch, so a missed
file fails the release rather than shipping a lie.

## 5. Branch, PR, squash-merge

Never commit on `main`. The release commit is a normal PR (`Release vX.Y.Z`), squash-merged,
branch deleted.

Commit footer:

```
Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
```

PR footer:

```
🤖 Generated with [Claude Code](https://claude.com/claude-code)
```

## 6. Tag and watch the gate

```bash
git checkout main && git pull
git tag -a vX.Y.Z -m "vX.Y.Z — <milestone name>"
git push origin vX.Y.Z
gh run watch
```

`release.yml` runs the full three-OS gate (tests, catalog audit, CLI smoke, version
consistency) before publishing. **A tag whose gate fails publishes nothing** — that is
deliberate. If it fails: fix on a branch, delete the tag, re-tag from the merged fix.

## 7. Confirm

```bash
gh release view vX.Y.Z
```

Check the assets (sdist + wheel) are attached and the notes read honestly. Then update the
"Current status" section of `CLAUDE.md` so the next session knows where the project stands.
