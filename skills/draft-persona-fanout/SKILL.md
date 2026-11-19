---
name: draft-persona-fanout
description: Reviews a finished or near-final newsletter/article draft (software engineering, fintech, or general tech topics) against a set of target reader personas, and reports back per-persona whether the piece lands, what resonates, what's missing or confusing from that reader's point of view, and concrete adjustments. Use this whenever the user asks to "run a persona check," "persona fanout review," "check this against my reader personas," "how will my readers react to this," "does this land for [audience]," or asks how different segments of their audience would each respond to a draft. Trigger this proactively any time someone asks about audience fit or reader reaction for an article, even without the words "persona" or "fanout." Scoped ONLY to persona/audience-fit analysis on the article's own prose: it does not rewrite or polish prose (that's article-refiner) and does not suggest images or diagrams (that's visual-asset-proposal) — stay in your lane. If no personas are supplied, look for the reader personas in the private repo and ask the author if none are available.
---

# Draft Persona Fanout

## Locations

Run once:

    python3 "<this skill's directory>/../../scripts/writing" paths --require-private

Resolve the symlink to the SKILL.md you are reading and use its containing directory for
`<this skill's directory>`; `../../scripts/writing` is the tooling repo's script.
Use the `public_root` and `private_root` from its output.

Before starting, read `AGENTS.md` at `public_root` and follow it.

Write only to the private repo. Never write to the public repo.

The article folder relative to `private_root` is `articles/<YYYY-MM-DD-slug>/`, with
`article.md`, `notes.md`, and `reviews/round-N/`.

## Purpose

Take a finished or near-final article draft and a set of target reader personas, and
"fan out" a review across each persona: read the piece as if you were that specific reader,
and report honestly on whether it lands for them, what works, what's missing or unclear from
their vantage point, and what to change. Close with a synthesis that reconciles the personas'
feedback when it conflicts, since a single draft can't fully satisfy every reader and the
author needs help deciding what to prioritize.

This is an **audience-fit** review, not a writing or design pass. Two adjacent concerns are
explicitly out of scope, handled by other skills in this workflow — don't drift into them even
if it would be easy to:

- **Prose polishing** (structure, clarity, hook, closing, voice) → `article-refiner`
- **Visual suggestions** (hero image, diagrams, charts) → `visual-asset-proposal`

If the user asks for either alongside a persona review, do the persona analysis and note that
the other concern is handled by its own skill rather than attempting it yourself.

## Step 1: Get the article draft

The input is either:
- Pasted text in the conversation, or
- A path to a markdown (or plain text) file — read it with the Read tool.

If neither is present, ask the user to paste the draft or point you to the file. Don't guess
at content you haven't actually read — the whole point of this skill is grounding feedback in
the real text, not a vague impression of what the piece is probably about.

## Step 2: Get the personas — do not invent them

This is the part of the workflow most likely to go wrong, so read this carefully. The author
may not have a settled, written-down persona list yet. Inventing plausible-sounding personas
on the fly would feel helpful in the moment but is actively harmful here: the whole value of a
persona review is that it's grounded in *this specific author's actual readers*, not in
generic archetypes an LLM associates with "tech newsletter audience." A fabricated persona
that goes unnoticed can quietly steer editorial decisions around a reader who doesn't exist.

Resolve personas in this order, stopping at the first one that succeeds:

1. **Supplied in the request.** If the author pastes, describes, or points to persona
   files, use those. A terse description is enough.
2. **Reader personas in the private repo.** Check `personas/*.md` relative to
   `private_root`. Treat each file as a persona and state which source you used.
3. **Neither exists.** Stop and ask the author to provide or point to the personas.
   A couple of sentences per persona is enough.

If the author supplies some personas in the request and files also exist in the
private repo, prefer the supplied personas and mention that the files are available.

## Step 3: Read the draft once as each persona

Before the round, compute the SHA-256 of the exact draft text. Hash pasted text as
UTF-8 and hash file input as read, preserving line endings and trailing newlines.
Record the hash at the top of the round output. If saving the round, write its output
under the article’s `reviews/round-N/`.

For each persona, actually inhabit their point of view rather than writing generic feedback
with a persona's name stapled on. Consider:

- What is this reader looking for when they open a newsletter — do they want a quick
  actionable takeaway, a deep technical mechanism, validation of a strategic instinct, or something else?
- What do they already know? A passage that's a clear, useful refresher for one persona might
  be condescending filler to another, or an unexplained leap that loses a third.
- Where would *this* reader's attention actually drop, get confused, or get annoyed — not
  where a generic reader might.
- What would make them forward this to someone, subscribe, or come back next week — versus
  what would make them bounce.

Ground every claim in the actual text. If you say something is "missing," be able to point to
where it should have appeared and didn't, not just gesture at a vague absence.

## Step 4: Write the per-persona assessment

For each persona, cover:

- **Does this land?** A direct, one- or two-sentence verdict — not hedged into
  meaninglessness. It's fine (and often more useful) to say a piece doesn't land well for a
  given persona than to soften every review into "mostly works, some room to grow."
- **What resonates** — the specific parts of the draft that work for this reader and why.
- **What's missing or unclear from their POV** — gaps, unexplained jargon or over-explained basics, unanswered "so what does this mean for me" questions,
  places where the piece assumes context this reader doesn't have (or over-explains context
  they already have).
- **1-3 concrete suggested adjustments** — specific and actionable, not "make it more
  engaging." E.g. "add one sentence explaining the cost and risk in the example" rather than "consider the business angle more."
  Cap it at 3 — a longer list stops being prioritized and starts being a wish list.

## Step 5: Synthesize across personas

After the individual assessments, add a short **Overall synthesis** section. This is the part
that turns several isolated reviews into something the author can actually act on:

- Note where personas agree — shared strengths or shared gaps are the highest-confidence
  signal, and worth fixing regardless of who you optimize for.
- Note where personas genuinely conflict — e.g. one wants more technical depth and another
  wants less, or one wants a stronger business framing and another finds that framing
  distracting. Don't paper over the tension by suggesting a mushy middle that would satisfy no
  one; name the tradeoff plainly.
- Give a recommendation on what to prioritize, reasoning from the piece's own apparent primary
  audience (if the draft or the author's framing makes that clear) or from which fix has the
  best cost/benefit — e.g. "the missing-context gap for [persona] is a two-sentence fix and
  would help everyone; the depth-vs-brevity tension is real and probably comes down to who you
  consider your primary reader for this piece."

## Output format

```markdown
# Draft Persona Fanout: [article title or working title]

*Review hash: [SHA-256]*

*Personas used: [private repo or supplied in the request]*

## [Persona name/role]
**Does this land?** ...
**What resonates:** ...
**What's missing or unclear:** ...
**Suggested adjustments:**
- ...
- ...

## [Next persona]
...

## Overall synthesis
[Agreement, conflicts, and a prioritized recommendation.]
```

If only one persona is supplied, it's fine to skip the synthesis section (there's nothing to
reconcile) — just note that a single-persona review doesn't need prioritization across
readers.
