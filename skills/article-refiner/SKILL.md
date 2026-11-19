---
name: article-refiner
description: Refines a rough or in-progress newsletter/article draft (software engineering, fintech, or general tech topics) into a polished, publish-ready version — sharpening structure, clarity, flow, the opening hook, and the closing, while preserving the author's voice and argument. Use this whenever the user asks to "refine," "polish," "tighten," "clean up," or "edit" an article, post, essay, or draft — whether they paste the text directly or point to a markdown file. Also trigger on requests like "make this flow better," "fix the opening," "this draft feels rough, can you improve it," or "give this a final pass before I publish." Produces actual rewritten prose (not just critique), and explicitly flags anything — missing numbers, unverified claims, vague attributions — that needs the author's input rather than inventing it. Do NOT use for suggesting images/visuals (that's visual-asset-proposal) or for checking how a draft lands with specific reader personas/audiences (that's draft-persona-fanout) — this skill is prose-only.
---

# Article Refiner

## Locations

Run once:

    python3 "<this skill's directory>/../../scripts/writing" paths --require-private

Resolve the symlink to the SKILL.md you are reading and use its containing directory for
`<this skill's directory>`; `../../scripts/writing` is the tooling repo's script.
Use the `public_root` and `private_root` from its output.

Before starting, read `AGENTS.md` at `public_root` and follow it.

Write only to the private repo when writing is requested, or return text without writing. Never write to the public repo.

The article folder relative to `private_root` is `articles/<YYYY-MM-DD-slug>/`, with
`article.md`, `notes.md`, and `reviews/round-N/`.
The voice and positioning guides are `guides/voice.md` and `guides/positioning.md` relative to `private_root`.

## Purpose

Turn a rough draft into a polished, Substack-ready piece of writing. The author
writes about software engineering, fintech, and tech topics. By the time this skill is invoked, a draft already exists
— rough, uneven, maybe missing a strong open or close — and the job is to
elevate it into something ready to hit "publish," without changing what it's
actually arguing.

This is a writing/editing skill, not a fact-checking or research skill, and
not a strategy skill. Stay inside prose: structure, clarity, flow, voice,
opening, closing. Two adjacent concerns are explicitly out of scope and
handled by other skills — don't drift into them even if it would be easy to:

- **Visual suggestions** (images, diagrams, charts to accompany the piece) →
  `visual-asset-proposal`
- **Audience/persona fit** (how different reader segments will react) →
  `draft-persona-fanout`

If the user asks for either of those alongside a refine request, do the prose
refinement and note that the other concern is handled by its own skill rather
than attempting it yourself.

## Getting the draft

The input is either:
- Pasted text in the conversation, or
- A path to a markdown (or plain text) file — read it with the Read tool.

If neither is present (the user just says "refine my article" with nothing
attached), ask them to paste the draft or point you to the file. Don't guess
at content that hasn't been provided.

## The core discipline: refine, don't reinvent

The single most important rule here is that this is *editing*, not
*ghostwriting*. The author's argument, opinions, and voice are the point of
the piece — your job is to make them land better, not to replace them with
your own take or a generically "smoother" version that sounds like anyone
else. Concretely:

- **Preserve the argument.** If the draft claims X and supports it with Y,
  the refined version should still claim X and support it with Y — just more
  clearly and persuasively. Don't soften, hedge, or swap in a different
  thesis because it seems more defensible.
- **Preserve the voice.** Keep the author's characteristic word choices,
  sentence rhythm, level of formality, and any recurring turns of phrase.
  Read a paragraph or two before editing to calibrate to their voice, and
  edit *within* it rather than overwriting it with a generic "polished
  newsletter" register.
- **Never invent specifics.** Do not add statistics, dates, company names,
  quotes, benchmark numbers, or sources that aren't in the draft. It is very
  tempting to fill a vague sentence ("adoption has grown a lot") with a
  plausible-sounding number to make it punchier — resist this completely.
  A fabricated stat that reads well is worse than an honest gap, because the
  author will publish it without noticing. When a passage would clearly
  benefit from a concrete detail that isn't there, flag it instead (see
  below) and leave the language honestly vague in the meantime, or rewrite it
  to make the *shape* of the claim clear without asserting false specifics.
- **Reasonable inference is fine, invention is not.** You can tighten a
  sentence, reorder for clarity, or make an implicit connection explicit if
  it's clearly what the author meant. That's normal editing. The line is
  factual content: don't add anything a fact-checker would need to verify
  against a source the draft doesn't cite.

## What "refined" means

Work through these dimensions. Not every draft needs work on all of them —
use judgment about where the draft is actually weak.

1. **Hook / opening.** The first few sentences should earn the reader's next
   thirty seconds — a concrete scene, a sharp claim, a real question, or
   tension, rather than throat-clearing ("In today's fast-moving tech
   landscape..."). If the draft's real opening idea is buried in paragraph
   three, it's fine to move it up. Choose the approach deliberately rather
   than defaulting to whatever comes first — see "Hook and subtitle
   options" below.
2. **Structure.** Does the piece build in a sensible order — does each
   section earn the next? Look for: a thesis that shows up too late, sections
   that could be merged or reordered, tangents that break the through-line,
   or a "wall of paragraphs" that would read better with subheads or a list.
3. **Clarity and flow.** Cut redundancy, tighten sentences, fix awkward
   transitions, replace vague abstractions with the concrete version the
   author clearly meant. Read for a smart reader who is skimming a Sunday
   newsletter feed, not a captive audience.
4. **Closing.** Endings that just stop ("anyway, that's my take") waste the
   piece's momentum. A strong close does one of: crystallizes the takeaway,
   answers "so what does this mean for the reader," or leaves a genuine open
   question worth sitting with. Match the tone the piece has earned — don't
   bolt on a generic motivational wrap-up if the piece was skeptical or dry.
5. **Voice consistency.** Check that your own edits haven't drifted into a
   different register than the rest of the piece (this is the most common
   way an editing pass quietly erases someone's voice — watch for it in your
   own output, not just the original draft).

## Doing the edit, not just describing it

Deliver actual rewritten prose. A list of notes like "the opening is weak,
consider punching it up" is not a completed job — write the punched-up
opening. The output should be something the author could paste directly into
Substack with minimal further work, not a to-do list for them to execute.

That said, don't rewrite what already works. If three paragraphs in the
middle are already tight and voiced well, leave them close to as-is rather
than rewriting for the sake of rewriting — unnecessary churn makes it harder
for the author to spot what actually changed and forces them to re-read
material that didn't need it.

## Flagging what needs the author

Whenever the piece would benefit from a specific fact, number, quote, or
source that isn't in the draft, don't invent it — flag it. Use inline markers
in the refined draft itself, right where the gap is:

`[NEEDS INPUT: what's the actual latency number here?]`

Then also collect these in a short list at the end of your response, titled
**Flagged for your input**, so the author can scan them without hunting
through the piece. Also use this section for anything you weren't confident
enough to touch — e.g. a claim that reads like it might be outdated, or a
paragraph whose argument was unclear enough that you preserved it nearly
verbatim rather than risk changing its meaning.

If the draft has no such gaps, it's fine to say so briefly rather than
padding the response with a section that has nothing in it.

## Linking sources

When the refined draft references a specific person's quote, a named source,
or a statistic, and that source's URL is unambiguous — it's the only
candidate source provided for that specific claim — hyperlink it inline
using standard markdown: `[quoted source](https://example.org/source)`.
This makes the draft's claims traceable without the author having to hunt
back through their own notes to find where something came from.

Don't guess when it's ambiguous. If two or more possible sources could back
the same claim and it isn't clear which one actually does, don't pick one
and link it — flag the attribution with `[NEEDS INPUT: ...]` instead, the
same as a missing fact. A confidently-wrong link is worse than an honest
gap, for the same reason a fabricated stat is: the author won't notice it's
wrong until someone else does.

## Hook and subtitle options

Every draft needs a deliberate opening, not a default one. Generate 2-3
distinct hook options for the piece's first paragraph, each paired with a
matching subtitle — draw from patterns already validated in this author's
own published work: a direct-address conditional ("If you're experiencing
X, this is for you"), a sharp claim/thesis-first opening, a concrete scene
or anecdote, or a real open question. Each option should be a genuinely
different approach, not a reworded variant of the same one.

Use whichever fits the piece best as the actual opening of the refined
draft — don't leave the draft with a placeholder opening. Present all the
options (including the one you used) in your reply per the output format
below, and let the author choose which subtitle, if any, to use — you're
never setting it yourself, since this isn't a file-writing skill.

## Output format

Structure your reply as:

```
## Refined draft

[the full rewritten article, in markdown, ready to paste into Substack]

## Hook options considered

[each hook option's label, its opening paragraph, and its paired subtitle
— mark which one was used in the Refined draft above]

## What changed and why

[a short paragraph or a few bullets — the headline edits: what you did to
the opening, structure, or closing, and the reasoning. Keep this tight;
it's context for the author, not a second draft.]

## Flagged for your input

[bullet list of specifics that need the author to fill in, or "None — the
draft didn't lean on any facts/figures I couldn't verify from the text."]
```

Always output the full refined draft (not just a diff or excerpted
passages) so the author has one clean piece to work from, unless the draft is
long enough that reproducing it in full would be unwieldy — in that case, say
so and ask whether they'd prefer the full text or a section-by-section pass.
