---
name: interview-to-draft
description: Interviews the author in question rounds and turns their answers and cited evidence into a first article draft. Use when the author wants to start an article, turn a topic into a draft, be interviewed for a piece, or get a first draft written. Use article-refiner for polishing an existing draft, draft-persona-fanout for persona review, and visual-asset-proposal for visuals.
---

# Interview to Draft

## Locations

Run once:

    python3 "<this skill's directory>/../../scripts/writing" paths --require-private

Resolve the symlink to the SKILL.md you are reading and use its containing directory for
`<this skill's directory>`; `../../scripts/writing` is the tooling repo's script.
Use the `public_root` and `private_root` from its output.

Before starting, read `AGENTS.md` at `public_root` and follow it.

Write only to the private repo. Never write to the public repo.

## 1. Set up

Identify the piece from a note in `topics/` or the author's description. Read
`guides/voice.md` and `guides/positioning.md`. If the piece belongs to a series, read
earlier entries under `articles/` with the same `series` value. Resolve these paths
relative to `private_root`.

Run `scripts/writing article new --title "<working title>"` from `public_root`. Pass
`--topic` and `--series` when they apply. Use the resulting folder under
`private_root/articles/` for `questions.md`, `article.md`, and `notes.md`.

Done when the folder exists and you can state in two sentences what the piece is
and where it sits in any series.

## 2. Ask a question round

Under `## Round N` in `questions.md`, use these three lettered sections. Number each
section's questions with its letter, such as A1, A2, and B1. Show the author the
questions in the same form.

- **A. Argument and reader** — Settle the claim in one sentence, who the piece is
  for, what the reader should do or think differently, and which claims are
  outside its argument.
- **B. Evidence and experience** — Ask what happened, which examples show it,
  where every figure comes from, and what may be named. Ask about any potential
  employer mention, flag it for the author, and leave the wording to them.
- **C. Design and business questions** — Settle scope and length, fit with the
  series, working title direction, deliberate omissions, visuals worth planning,
  and any other decision that would change the piece if made later.

Ask only questions the topic note, guides, and earlier entries leave unanswered.
Have the author answer by number and record each answer or waiver under its question.

Done when every question is answered or waived and section C has no open question.

## 3. Ask further rounds for gaps

Use the same round format for gaps that would otherwise require inventing a fact,
example, or position. Resolve each gap with the author or identify it explicitly
as unverified if the author has waived it and wants it kept visible.

Done when you can write the draft using only the author's answers and cited evidence.

## 4. Check the outline

Give the author a working title and an outline of five to eight lines. Revise
them based on the author's feedback.

Done when the author has accepted the outline.

## 5. Draft

Write `article.md` in the author's voice as described in the voice guide. Use
only facts from the author's answers and the topic's evidence. Draw anecdotes,
quotes, and numbers from those materials.

Record a source for every figure and factual claim under `## Sources` in `notes.md`.
Mark each unsourced item `[unverified]` in the draft and list it under
`## Open questions`. List every employer mention under `## Flagged for the author`
and leave additions or changes to the author.

Done when every figure has a Sources entry or an `[unverified]` mark.

## 6. Read for claims

Reread the draft and list each factual claim with its source or `[unverified]`
mark. Give the list to the author with the full draft, the flagged mentions,
and the open questions.

Done when the author has all four.

## 7. Hand back

State the stages that follow. The author refines the draft, then a refining pass
polishes the prose. Persona review rounds follow, with the exact draft hashed
before each round. A visuals proposal follows. The author publishes by hand
and then runs `scripts/writing publish` to record the published entry.

Done when the author has the handoff. End the skill here.
