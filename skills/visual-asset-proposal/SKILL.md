---
name: visual-asset-proposal
description: Generates a structured brief of suggested key visuals (hero/cover image plus supporting diagrams, charts, or illustrations) for a near-final newsletter or blog article. Use this whenever the user asks what images, visuals, diagrams, charts, or illustrations should accompany a draft — e.g. "suggest visuals for this piece," "visual concepts for this article," "what images should go with this," "give me hero image ideas," "what should the cover image be," or "does this need a diagram." Scoped ONLY to visual creative direction: it does not edit or polish the prose (that's a separate step) and does not judge audience fit or generate actual image files — it produces a concept spec a designer or image-generation tool could work from. Trigger this proactively any time the user shares or references a near-final article draft and asks about accompanying images or graphics, even if they don't use the word "brief."
---

# Visual Concept Brief

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

Read a near-final article draft and produce a concept brief for the visuals that should
accompany it: a hero/cover image plus a small number of supporting visuals (diagrams,
charts, illustrations) as warranted by the article's length and content.

This is a **creative-direction** deliverable, not an image-generation step. The output is
text: placement, concept, and rationale for each visual. Nothing here produces an actual
image file, and nothing here touches the article's prose or evaluates who it's for — those
are separate concerns handled elsewhere in the writer's workflow. Stay in your lane: visuals
only.

## When this applies

Use this whenever someone shares (pastes or points to a file) a draft that's far enough
along that the words aren't going to change much, and asks about images, visuals, hero art,
diagrams, or charts for it. If the draft is clearly an early outline or is still being
rewritten, it's fine to proceed anyway — just note in the brief that placements may shift
if the structure changes.

## Step 1: Get the article

- If the user pasted the article text directly, use it as-is.
- If they gave a file path, read that file.
- If neither is available, ask for the draft — this skill can't produce a grounded brief
  without the actual text. Don't invent visuals for an article you haven't read.

## Step 2: Check for a locked design system

Before proposing any style, mood, or color, look for a design system governing this
content. Check `guides/design.md` (tokens in frontmatter) and `guides/design-system.md`
(rationale, rules, and templates), both relative to `private_root`, before drafting
a Concept section. The visual gaps guide is `guides/visual-gaps.md` relative to
`private_root`.

If a design system exists:

- Its palette, canvas color, typeface, and named templates (as defined in the design system) are locked. Don't invent a
  new accent color, canvas tone, or illustration style because it seems to fit this
  article's mood better — that instinct is drift, not creative direction. Every Concept
  you write in Step 5 must fit within it.
- Where a proposed visual matches one of its named templates, say so by name in the
  Concept so whoever builds it knows which
  grammar to follow.
- Its Do's/Don'ts constrain every Concept below — read them, not just the palette.

If no design system governs this content, style is free — fall back to the audience
defaults in "Style notes for this audience" below.

## Step 3: Read for visual opportunities, not just topic

Read the whole piece before proposing anything. You're looking for:

- **The core tension or hook** — the idea that would make a good cover image, because it's
  usually the most visual (and most ownable) idea in the piece. This is often stated in the
  title or opening paragraphs, but sometimes it's a metaphor buried in the middle that's
  actually stronger than what's up top.
- **Places where the prose is doing the work a diagram would do better** — a paragraph
  listing steps in a process, a sequence of before/after states, a system with multiple
  interacting parts, a comparison. If a reader would benefit from seeing the structure
  rather than parsing it out of sentences, that's a supporting-visual candidate.
- **Any actual numbers or comparisons** — even informal ones ("three out of four teams,"
  "went from 200ms to 20ms"). These are chart candidates. Don't invent data that isn't in
  the article; if the article only gestures at a trend without numbers, that's an
  illustration/diagram candidate instead of a chart. If the number is attributed to someone
  else's research, report, or study rather than the author's own data, note that source —
  see Step 5, it needs to be credited on the visual itself, not just in the article's prose.
- **Sections that are purely argumentative or reflective**, with no structure or data to
  visualize. Not every section needs or benefits from a visual — resist the urge to pad the
  brief just to hit a round number.

## Step 4: Decide how many visuals to propose

Let the article's own length and content set the count — don't default to a fixed number.

- Every brief gets **one hero/cover image concept.** This is non-negotiable structurally
  (Substack and most blog platforms show it as the lead/social-preview image), but its
  *content* should come from the piece's actual hook.
- Add **supporting visuals only where Step 3 found real candidates** — typically 1 to 3.
  A short, single-argument piece (a few hundred words, one idea, no data) may genuinely
  only need the hero. A longer piece with a multi-step process, a system with moving parts,
  or real numbers can support two or three.
- If you're unsure whether a candidate earns its place, ask: would a reader who skims only
  the images understand something true about this section? If not, cut it.

## Step 5: Write each visual as a three-part entry

For every visual, hero included, write:

**Placement** — where it goes, anchored to the article's actual structure (e.g. "Hero /
cover image," "After the section on database migrations," "Replacing the bulleted list of
failure modes"). Be specific enough that someone laying out the post wouldn't have to guess.

**Concept** — a description detailed enough to hand directly to a designer or an
image-generation tool. Cover:
- *Subject/composition*: what's actually depicted, and how it's framed (close-up, wide,
  isometric, single object vs. scene).
- *Mood/style*: the visual register — e.g. flat vector illustration, technical
  diagram/schematic, moody photographic, minimal line art. If Step 2 found a design system,
  the register, palette, and canvas here are that system's, not a free choice — name the
  specific colors and template by their tokens, never a generic placeholder like "an accent color." Otherwise, pick
  something that fits a software-engineering/fintech newsletter (see the style notes below)
  rather than defaulting to generic stock-photo tropes.
- *Data/diagram content*, only if applicable: for a chart, name the chart type, axes, and
  what data or trend it plots (using only numbers/comparisons actually present in the
  article — don't fabricate precision the article doesn't have). If that data is credited to
  a specific source in the article (a named study, report, organization, or person), carry
  that attribution into the concept as a caption line or axis footnote — e.g. "Source: DORA
  2024 Report" — so credit doesn't get lost between the article's prose and the finished
  visual. For a process/system diagram, name the nodes and how they connect.

**Rationale** — one or two sentences on why this visual belongs at this spot: what it
clarifies, reinforces, or gives a skimming reader that the prose alone doesn't.

## Style notes for this audience

These are fallback defaults for content with no governing design system (Step 2). Where a
design system exists, its palette, canvas, typography, and Do's/Don'ts override everything
below — don't blend the two.

The writer's newsletter covers software engineering, fintech, and tech topics for a
newsletter readership. A few defaults that tend to serve that audience well — treat them as
a starting point, not a rule, and deviate when the article calls for it:

- Prefer diagrams, schematics, abstract/geometric illustration, or metaphor-driven imagery
  over literal stock photos of people in offices pointing at monitors — that genre reads as
  filler to this audience.
- Charts should look like something an engineer would actually plot: honest axes, no
  invented precision, simple chart types (line, bar) over cute infographic treatments.
- It's fine for the hero image to be conceptual/metaphorical rather than literal, as long as
  the concept description grounds it in something concrete enough to actually produce (an
  abstract idea like "the illusion of stability" needs a concrete visual referent — a house
  of cards, for example).

## Output format

Present the brief as Markdown, structured like this:

```markdown
# Visual Brief: [Article title or working title]

[1-2 sentence read on the article's core idea/hook, used to justify the hero concept.]

## 1. Hero / Cover Image
**Placement:** Hero / cover image
**Concept:** ...
**Rationale:** ...

## 2. [Short descriptive name for this visual]
**Placement:** ...
**Concept:** ...
**Rationale:** ...

[... additional supporting visuals as warranted ...]
```

Use a short, descriptive name in each supporting visual's heading (e.g. "The Observability
Gap Diagram," "Deploy vs. Working Comparison Chart") rather than just "Visual 2" — it makes
the brief easier to discuss and hand off.

Close with a one-line note only if something is worth flagging — e.g. "This piece is
argument-driven with no hard data, so no chart is proposed; all visuals below are
conceptual/diagrammatic." If two or more of the proposed visuals naturally share a visual
motif (the same "gap/disconnect" device, the same diagram register, a recurring color or
icon), say so in a line like this too — it tells whoever builds these that the visuals are
meant to read as one coherent set rather than unrelated one-offs. Skip the note entirely if
there's nothing worth saying.
