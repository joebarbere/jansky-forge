# Vendored: SimpleEnglish

This skill is **not ours**. It is copied verbatim from a third-party repository and kept in
git rather than installed globally, because the rule across the jansky repos is that a skill
which is not in git does not exist — a reviewer must be able to see what the agent was told.

| | |
|---|---|
| Upstream | https://github.com/AminBlg/SimpleEnglish |
| Skill version | 1.2.0 |
| Pinned commit | `59bf6702197a5aadc96d197ea17f290d8d50dcd3` |
| Vendored on | 2026-08-08 |
| License | MIT (see `LICENSE` in this directory — Copyright (c) 2026 AminBlg) |
| Standard | ASD-STE100 Issue 9 (2025-01-15), paraphrased. Unofficial and unaffiliated with ASD or STEMG |

Files taken from `skills/simple-english/` upstream: `SKILL.md`, `references/checklist.md`,
`references/use-cases.md`. Nothing was edited; the guidance on *when* we invoke it lives in
this repo's `CLAUDE.md`, not inside the vendored file, so an update can overwrite these
cleanly.

## To update

```bash
gh api repos/AminBlg/SimpleEnglish/contents/skills/simple-english/SKILL.md \
  --jq '.content' | base64 -d > .claude/skills/simple-english/SKILL.md
```

Repeat for the two files under `references/`, then update the pinned commit and version
above. Review the diff before committing: this file becomes agent instructions, so an
unreviewed upstream change is an unreviewed change to how the project writes.

## Why vendored and not `npx skills add`

Upstream offers `npx skills add AminBlg/SimpleEnglish`, which installs into the agent
configuration for whichever tools it detects. That is convenient for a person who wants the
skill everywhere, and it is the right choice for personal use — but it puts the instructions
outside this repository, where a PR reviewer cannot see them and a release does not carry
them. Install it that way as well if you want it in every project; this copy is what governs
work *in this repo*.
