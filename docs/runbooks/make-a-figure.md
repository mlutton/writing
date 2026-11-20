# Make a figure

An in-article figure is a small TOML input drawn on a shared titled frame. The generator reads the template spec in the private repo (`guides/figure-template.toml`; see `examples/figure-template.example.toml` for the format) and needs Chromium, found the same way as for headers (`WRITING_CHROMIUM`, then `chromium`, `chromium-browser`, `google-chrome`, `google-chrome-stable`). See `examples/figures/` for one invented input per type.

Figures live in the article's private folder: `articles/<folder>/figures/<name>.toml` produces `<name>.svg`, `<name>.png`, and a regenerated `figures/ALT-TEXT.md` that covers every figure in the folder. Names are lowercase letters, digits and hyphens.

## Commands

- `scripts/writing figure init <article-folder> <name> --type bars|flow|table|stats|custom` writes a starter input with commented fields. It will not overwrite an existing file.
- `scripts/writing figure build <article-folder> <name>` (or `--all`) validates, measures text in Chromium, lays out, checks, and writes the SVG, the PNG and `ALT-TEXT.md`. Nothing is written when a check fails.
- `scripts/writing figure check <article-folder>` (or `--all`) runs every check that needs no rendering and exits non-zero on a failure. `--all` lists articles without figures as information, not a failure.

## The frame

Every type shares the frame. Keys common to all inputs: `type`, `title`, `deck` (both required), `eyebrow` (caps line above the plot, optional), `takeaway` (one line below the plot, optional), `sources` (0 to 2 lines), `alt` (required), `place` and `caption` (optional, copied to `ALT-TEXT.md`), and `numbers`. Eyebrow, row labels and table headers are set in capitals by the generator.

`numbers` says where each number comes from. It is required for `bars` and `stats`, and for any other type whose content contains a digit (for `custom`, a digit in the alt text counts). `ALT-TEXT.md` prints it as "Numbers", or "none" when absent.

## Types

- `bars`: `[[bar]]` with `label`, `value` (a number, zero or more), optional `display` (the text shown at the bar end; defaults to the value) and optional `focal = true`. Options: `label_position = "left"` (labels right-aligned in a gutter) or `"above"`, and optional `axis_label` (a caps label over the axis). Bars scale to the largest value. A focal bar is gold with a gold value, which counts as two gold elements.
- `flow`: `[[box]]` with `id`, `row`, `col`, `label`, optional `sub`, optional `focal`; `[[edge]]` with `from`, `to`, `style = "flow"` (solid, the mechanism) or `"signal"` (dashed); optional `[[row_label]]` with `row` and `text`. Boxes sit on a grid: `row` and `col` are numbers, and halves (`row = 0.5`) place a box between rows. Edges run left to right, or up and down within a column; connectors are orthogonal. Edges that share a source or a target share a trunk, so fan-out and fan-in work. A connector that would cross a box, or a flow edge that would overlap a signal edge, fails the build. Labelled rows are spaced further apart, so they fit fewer rows.
- `table`: `columns = [...]` and `[[row]]` with `cells = [...]` (same length as `columns`), optional `focal = true` on a row, and optional `arrow_after = <column index>` (0-based) to draw an arrow between that column and the next in every row. Columns sit on rails sized to the widest cell. A focal row has a gold marker and a gold first cell.
- `stats`: one or two `[[column]]`, each with `header` and `[[column.item]]` of `value` (a string such as "40%", with a trailing % set as a superscript), `label` (a string or a list of up to two lines), optional `source`, and optional `hero = true` (display size, gold; counts as one gold element).
- `custom`: `script = "<name>.py"`, a file in the same `figures/` folder that defines `draw(fig)`. See below.

## Custom figures run your own code

A `custom` figure imports the named script and calls its `draw(fig)` when you build it. That is the author's own Python from the private repo running with the author's permissions, so build a custom figure only from a script you wrote or have read. Nothing sandboxes it. The script's hash is recorded so a change makes the figure stale.

`draw(fig)` must be a pure function of `fig`: it runs more than once while text widths are measured. `fig` gives you:

- `fig.frame`: a dict with `x`, `right`, `plot_top`, `plot_bottom`, `plot_bottom_open`, `width`, `height`.
- `fig.palette`: role name to colour, for reading. Primitives take role names, never hex values.
- Primitives: `text(x, y, text, role, anchor="start", fill=None, max_width=None, what="width")`, `rect(x, y, w, h, fill=None, stroke=None, stroke_width=None)`, `line(x1, y1, x2, y2, tone)`, `connector(points, style="flow"|"signal", head=True)`, `zone_label(x, y, text, tone)`, `marker(x, y, size, tone)`, `divider(x, y, width)`, `avoid(x, y, w, h, name)` (a rectangle connectors must not cross), `width_of(text, role)` (measures; each new text costs one browser run, so use it sparingly), and `raw(svg, bbox)` (an element as written; the SVG checks still apply).

The generator draws the title, deck, eyebrow, takeaway, sources, rules and divider, and runs every generic check on the result.

## What the checks mean

- Input shape: required keys, per-type rules, the spec's limits (bars, boxes, rows, columns, stat items, source lines, gold elements).
- Font loaded: the build declares the vendored font in a wrapper page and fails if a face did not load or text measures the same as in a fallback font. A missing font never falls back silently. The font file's sha256 must match the spec.
- Text fits: every text must fit its allotted width (frame, bar gutter, box, column) using measured widths. The failure names the text and the limit. Nothing is shrunk silently, and the plot must stay inside the plot area and clear of the takeaway line.
- One Signal Rule: the produced SVG may use the focal colour on at most the spec's limit of elements (two in the example). This runs for every type, including `custom`.
- Arrow styles: only solid flow and dashed signal connectors; dashed only in the signal colour, solid only in the flow colour.
- No forbidden SVG features: `rx`/`ry`, filters, gradients, embedded images.
- PNG size: exactly the canvas size.
- Alt text: not empty; for `bars` and `stats` it mentions every plotted value (the number or its `display` text, commas ignored); `numbers` is present when numbers are shown.
- Stale: the SVG records the input's sha256 and the spec's sha256 (and the script's for `custom`). `check` fails with "figure is stale" and says which one changed. `check` also fails when `ALT-TEXT.md` is missing or out of date.

## Fix a stale figure

Read which part changed. If the input or script changed on purpose, run `figure build` again. If the spec changed, rebuild every figure you still intend to use. Commit nothing to the public repo; figures live in the private repo.
