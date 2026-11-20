# Draw article headers as SVG from a private spec

Article headers are drawn, not generated. A generator reads a spec file in the private repo (canvas, colours, font, geometry) and a small per-article input, lays the title out with measured text widths, writes an SVG, and rasterises it with headless Chromium to a PNG. The font is vendored in the private repo and loaded from a file, never installed system-wide, and the build fails if it did not load.

Image models are not used. A trial garbled the numerals and the canvas colour, and a header must be the same every time it is built.

The tooling in this public repo contains no brand values. The spec, the font and the articles stay in the private repo, so the public example spec uses neutral placeholders. The tooling records the article title and the spec hash in each SVG, so a header made before a title or template change is reported as stale.
