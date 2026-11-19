# UPSTREAM: blader/humanizer

**Source:** https://github.com/blader/humanizer
**Pinned commit:** `225a6f39ac85f76ee48dbad772ea4abe4ed6c9d8` (SKILL.md metadata version 3.1.0), tree `8ed37b6d1d98a0bbdb599d0399a4a2185eb8fa03`
**Licence:** MIT, copyright (c) 2025 Siqi Chen. The full text is in `LICENSE` in this folder.
**Credit line:** on the line after the frontmatter of `SKILL.md`:
`<!-- Credit: author Siqi Chen (blader). Upstream blader/humanizer v3.1.0 at 225a6f3, MIT (see LICENSE and UPSTREAM-blader-humanizer.md in this folder). -->`

## What we took
`SKILL.md` only, copied whole from the upstream repo root at the pinned commit. Not taken: `scripts/validate-package.py`, `agents/`, the plugin manifests and `AGENTS.md`.

## What we changed locally, and why
1. **Credit line added** (Owner rule, credit third-party skills). The writing toolkit also adds its location, rules, and write-target instructions.
2. **No guide-specific adaptation**: the skill runs as upstream wrote it. Its own Voice section applies (a writing sample, if one is given, overrides the dash rule).

## How it is used
Use file mode after the persona round and before the author reads the draft. It is a prose pass only: code, paths, YAML frontmatter and link targets stay unchanged, and no fact may be added or dropped.

## Refresh checklist (on a new upstream pin)
1. Fetch the new commit's `SKILL.md` and `LICENSE` (`gh api repos/blader/humanizer/contents/...?ref=<sha>`); record the commit and tree.
2. Read the whole new `SKILL.md` before installing (it is instructions to an agent); diff it against this pin.
3. Re-apply the credit line; update this file's pin, tree and version.
