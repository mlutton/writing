# Make a header

Every article gets a header image. The generator draws it from the template spec in the private repo (`guides/header-template.toml`; see `examples/header-template.example.toml` for the format) and needs Chromium. It looks for `WRITING_CHROMIUM`, then `chromium`, `chromium-browser`, `google-chrome`, `google-chrome-stable` on the path.

## Inputs

`scripts/writing header init <article-folder>` writes `header.toml` in the article's folder from the article's title. It will not overwrite an existing file. Edit it:

- `lines`: the title split into 2 to 4 lines. A line may be a shortened form of the title that stays faithful to the claim.
- `gold`: the 1-based number of the single emphasis line. Unset until the author chooses; the build refuses without it.
- `deck`: exactly two lines. The house series form is "Part N", not "Part N of M".
- `number`: optional series post number, digits only. Leave it out for a standalone article.
- `alt`: required text describing the image.

## Commands

- `scripts/writing header build <article-folder>` validates the input, measures the title in Chromium, lays it out, writes `header.svg` and `header.png`, and prints the title sizes used and the alt text. A size below the template's standard size means the block was scaled to fit; shorten a line if that is not wanted.
- `scripts/writing header check <article-folder>` runs the checks without rendering. `--all` checks every article with a `header.toml` and lists the articles without one separately; that list is information, not a failure.

Both exit non-zero when a check fails.

## What the checks mean

- Input shape: 2 to 4 lines, one gold line, two deck lines, digit-only number, non-empty alt text.
- Font loaded: the build declares the vendored font in a wrapper page and fails if any face did not load or if text measures the same as in a fallback font. A missing font never falls back silently. The font file's sha256 must match the spec.
- Width and scale: no title line is wider than the spec's maximum after scaling, and the scaled standard size is not below the spec's minimum. `check` reads the result recorded at build time.
- PNG size: the PNG is exactly the canvas size.
- Stale: the SVG records the article title, the spec's sha256 and `header.toml`'s sha256 at build time. `check` fails with "header is stale" and says which one changed.
- Series number: no other article in the same series uses the same number.
- Deck wording (warning only): a deck line in the form "Part N of M" gets a warning that the house form is "Part N".

## Fix a stale header

Read which part changed. If the title or `header.toml` changed on purpose, run `header build` again. If the spec changed, rebuild every header you still intend to use. Commit nothing to the public repo; headers live in the private repo.
