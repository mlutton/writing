"""Article header generator: validate, measure, lay out, render and check.

The template (canvas, colours, font, geometry) comes entirely from a spec file
in the private repo; this module holds no brand values. Everything here is
standard library. Chromium is needed only to measure text and to rasterise.
"""

from dataclasses import dataclass, field
import hashlib
import html
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile
import tomllib
import xml.etree.ElementTree as ET


SPEC_RELATIVE = ("guides", "header-template.toml")
INPUT_NAME = "header.toml"
SVG_NAME = "header.svg"
PNG_NAME = "header.png"
BROWSERS = ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable")
GENERIC_FAMILIES = {"serif", "sans-serif", "monospace", "cursive", "fantasy", "system-ui",
                    "ui-serif", "ui-sans-serif", "ui-monospace", "ui-rounded"}
PROBE_TEXT = "Hamburgefonstiv 0123456789"
PART_OF = re.compile(r"\bpart\s+\d+\s+of\s+\d+\b", re.I)
DIGITS = re.compile(r"[0-9]+")
SHA256 = re.compile(r"[0-9a-f]{64}")
COLOUR = re.compile(r"#[0-9a-fA-F]{3,8}")
METADATA_ID = "header-build"
TOLERANCE = 0.01


class HeaderError(ValueError):
    """The header cannot be built or checked; the message says why."""


@dataclass
class Finding:
    level: str  # "fail" or "warn"
    message: str


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    return sha256_bytes(Path(path).read_bytes())


# ---------------------------------------------------------------- the spec

NUMBER = (int, float)
SCHEMA = {
    "canvas.width": int, "canvas.height": int, "canvas.background": str,
    "font.family": str, "font.weight_min": int, "font.weight_max": int,
    "title.x": NUMBER, "title.last_baseline": NUMBER, "title.max_width": NUMBER,
    "title.min_size": NUMBER, "title.advance_prev": NUMBER, "title.advance_next": NUMBER,
    "title.standard.size": NUMBER, "title.standard.weight": int,
    "title.standard.letter_spacing": NUMBER, "title.standard.fill": str,
    "title.emphasis.size": NUMBER, "title.emphasis.weight": int,
    "title.emphasis.letter_spacing": NUMBER, "title.emphasis.fill": str,
    "separator.x": NUMBER, "separator.y": NUMBER, "separator.width": NUMBER,
    "separator.height": NUMBER, "separator.fill": str,
    "deck.x": NUMBER, "deck.size": NUMBER, "deck.weight": int,
    "deck.baselines": list, "deck.fills": list,
    "watermark.size": NUMBER, "watermark.weight": int, "watermark.letter_spacing": NUMBER,
    "watermark.fill": str, "watermark.x": NUMBER, "watermark.baseline": NUMBER,
    "watermark.anchor": str,
}
RULE_SCHEMA = {"y": NUMBER, "height": NUMBER, "fill": str, "opacity": NUMBER}


def _is(value, kind):
    if isinstance(value, bool):
        return False
    return isinstance(value, kind)


def _lookup(data, dotted):
    for part in dotted.split("."):
        if not isinstance(data, dict) or part not in data:
            return None, False
        data = data[part]
    return data, True


def validate_spec(spec):
    """Return a list of problems with a spec dictionary."""
    problems = []
    for dotted, kind in SCHEMA.items():
        value, present = _lookup(spec, dotted)
        if not present:
            problems.append(f"spec is missing {dotted}")
        elif not _is(value, kind):
            problems.append(f"spec {dotted} has the wrong type")
    if problems:
        return problems
    for dotted in ("canvas.background", "title.standard.fill", "title.emphasis.fill",
                   "separator.fill", "watermark.fill"):
        if not COLOUR.fullmatch(_lookup(spec, dotted)[0]):
            problems.append(f"spec {dotted} must be a # colour")
    if not spec["font"]["family"].strip():
        problems.append("spec font.family must not be empty")
    if spec["font"]["weight_min"] > spec["font"]["weight_max"]:
        problems.append("spec font weight_min exceeds weight_max")
    deck = spec["deck"]
    if len(deck["baselines"]) != 2 or not all(_is(v, NUMBER) for v in deck["baselines"]):
        problems.append("spec deck.baselines must be two numbers")
    if len(deck["fills"]) != 2 or not all(isinstance(v, str) and COLOUR.fullmatch(v)
                                           for v in deck["fills"]):
        problems.append("spec deck.fills must be two # colours")
    if spec["watermark"]["anchor"] not in ("start", "middle", "end"):
        problems.append("spec watermark.anchor must be start, middle or end")
    rules = spec.get("rule", [])
    if not isinstance(rules, list):
        problems.append("spec rule must be a list of tables")
    else:
        for index, rule in enumerate(rules, 1):
            for key, kind in RULE_SCHEMA.items():
                if not isinstance(rule, dict) or not _is(rule.get(key), kind):
                    problems.append(f"spec rule {index} needs a valid {key}")
    font = spec["font"]
    if "file" in font:
        if not isinstance(font["file"], str) or not font["file"]:
            problems.append("spec font.file must be a path")
        elif Path(font["file"]).is_absolute() or ".." in Path(font["file"]).parts:
            problems.append("spec font.file must be relative to the private root")
        if not isinstance(font.get("sha256"), str) or not SHA256.fullmatch(font["sha256"]):
            problems.append("spec font.sha256 is required with font.file")
    if spec["title"]["standard"]["size"] <= 0 or spec["title"]["emphasis"]["size"] <= 0:
        problems.append("spec title sizes must be positive")
    if not 0 < spec["title"]["min_size"] <= spec["title"]["standard"]["size"]:
        problems.append("spec title.min_size must be between 0 and the standard size")
    return problems


@dataclass
class Spec:
    data: dict
    sha256: str
    root: Path  # the private root font paths are relative to

    @property
    def family(self):
        return self.data["font"]["family"]

    @property
    def font_path(self):
        name = self.data["font"].get("file")
        return self.root / name if name else None

    def verify_font_file(self):
        """Fail unless the vendored font is present and matches the recorded hash."""
        path = self.font_path
        if path is None:
            return
        if not path.is_file():
            raise HeaderError(f"template font file is missing: {self.data['font']['file']}")
        if sha256_file(path) != self.data["font"]["sha256"]:
            raise HeaderError("template font file does not match the sha256 in the spec")


def load_spec(path, root):
    path = Path(path)
    try:
        raw = path.read_bytes()
    except OSError:
        raise HeaderError(f"missing header template spec: {path.name}") from None
    try:
        data = tomllib.loads(raw.decode("utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as error:
        raise HeaderError(f"invalid header template spec: {error}") from None
    problems = validate_spec(data)
    if problems:
        raise HeaderError("invalid header template spec: " + "; ".join(problems))
    return Spec(data, sha256_bytes(raw), Path(root))


# --------------------------------------------------------- per-article input

INPUT_KEYS = {"lines", "gold", "deck", "number", "alt"}


@dataclass
class HeaderInput:
    lines: list
    gold: int
    deck: list
    number: str
    alt: str


def input_problems(data):
    problems = []
    for key in sorted(set(data) - INPUT_KEYS):
        problems.append(f"unknown key {key}")
    lines = data.get("lines")
    if not isinstance(lines, list) or not all(isinstance(v, str) for v in lines):
        problems.append("lines must be a list of 2 to 4 strings")
    elif not 2 <= len(lines) <= 4:
        problems.append(f"lines must have 2 to 4 entries, found {len(lines)}")
    elif not all(v.strip() for v in lines):
        problems.append("lines must not be empty")
    gold = data.get("gold")
    if gold is None:
        problems.append("gold is not set: choose the one emphasis line (1-based)")
    elif isinstance(gold, list):
        problems.append("exactly one line may be gold: gold must be a single number")
    elif not _is(gold, int):
        problems.append("gold must be a whole number")
    elif isinstance(lines, list) and not 1 <= gold <= len(lines):
        problems.append(f"gold must be between 1 and {len(lines)}")
    deck = data.get("deck")
    if not isinstance(deck, list) or len(deck) != 2 or not all(isinstance(v, str) for v in deck):
        problems.append("deck must be exactly two lines")
    elif not all(v.strip() for v in deck):
        problems.append("deck lines must not be empty")
    if "number" in data:
        number = data["number"]
        if not isinstance(number, str) or not DIGITS.fullmatch(number):
            problems.append("number must be digits only")
    alt = data.get("alt")
    if not isinstance(alt, str) or not alt.strip():
        problems.append("alt text is required and must not be empty")
    return problems


def parse_input(raw):
    """Parse header.toml bytes into a HeaderInput, or raise HeaderError."""
    try:
        data = tomllib.loads(raw.decode("utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as error:
        raise HeaderError(f"invalid {INPUT_NAME}: {error}") from None
    problems = input_problems(data)
    if problems:
        raise HeaderError(f"invalid {INPUT_NAME}: " + "; ".join(problems))
    return HeaderInput(list(data["lines"]), data["gold"], list(data["deck"]),
                       data.get("number", ""), data["alt"])


def load_input(path):
    try:
        return parse_input(Path(path).read_bytes())
    except OSError:
        raise HeaderError(f"missing {INPUT_NAME}; run header init first") from None


def split_title(title):
    """Naive two-line split: after punctuation near the middle, else at the middle word."""
    words = title.split()
    if len(words) < 2:
        return [title.strip(), ""]
    best, best_score = 1, None
    total = len(title)
    for i in range(1, len(words)):
        head = " ".join(words[:i])
        score = abs(len(head) - total / 2) - (total if head[-1] in ",:;" else 0) * 0.15
        if best_score is None or score < best_score:
            best, best_score = i, score
    return [" ".join(words[:best]), " ".join(words[best:])]


def starter_input(title):
    lines = split_title(title)
    return (
        f"# Header input for the article titled: {title}\n"
        "# Edit the lines (2 to 4), choose the one emphasis line, then run header build.\n"
        f"lines = {json.dumps(lines, ensure_ascii=False)}\n"
        "# gold = 1   # 1-based index of the single emphasis line; build refuses until set\n"
        'deck = ["", ""]   # exactly two lines\n'
        '# number = "01"  # series post number, digits only; omit for a standalone article\n'
        'alt = ""   # required: describe the image for readers who cannot see it\n'
    )


# ------------------------------------------------------------------- layout

@dataclass
class Layout:
    sizes: list
    baselines: list
    widths: list
    scale: float
    tracking: list
    fills: list
    problems: list = field(default_factory=list)


def advance(spec, prev_size, next_size):
    title = spec["title"]
    return round(title["advance_prev"] * prev_size + title["advance_next"] * next_size)


def baselines_for(spec, sizes):
    """Bottom-anchored baselines: the last line sits at last_baseline."""
    result = [0] * len(sizes)
    result[-1] = spec["title"]["last_baseline"]
    for i in range(len(sizes) - 2, -1, -1):
        result[i] = result[i + 1] - advance(spec, sizes[i], sizes[i + 1])
    return result


def layout(spec, inp, measure):
    """Lay out the title block.

    `measure(jobs)` takes dicts with text, size, weight and tracking and returns a
    list of widths in pixels. The first measurement uses the template sizes; if any
    line is over the maximum width the whole block is scaled uniformly, then
    re-measured at the new (rounded) sizes and tightened until every line fits or
    the standard size reaches the spec minimum.
    """
    title = spec["title"]
    base = []
    for index, text in enumerate(inp.lines, 1):
        style = title["emphasis" if index == inp.gold else "standard"]
        base.append((text, style))

    def widths_at(sizes):
        jobs = [{"text": text, "size": size, "weight": style["weight"],
                 "tracking": style["letter_spacing"]}
                for (text, style), size in zip(base, sizes)]
        return list(measure(jobs))

    def sizes_for(scale):
        if scale >= 1:
            return [style["size"] for _, style in base]
        return [int(round(style["size"] * scale)) for _, style in base]

    limit = title["max_width"]
    scale = 1.0
    sizes = sizes_for(scale)
    widths = widths_at(sizes)
    for _ in range(8):
        widest = max(widths)
        if widest <= limit + TOLERANCE:
            break
        scale *= limit / widest * (0.999 if scale < 1 else 1.0)
        sizes = sizes_for(scale)
        if sizes[inp.gold - 1] <= 0 or min(sizes) <= 0:
            break
        widths = widths_at(sizes)
        standard = title["standard"]["size"]
        if round(standard * scale) < title["min_size"]:
            break
    result = Layout(sizes, baselines_for(spec, sizes), widths, scale,
                    [style["letter_spacing"] for _, style in base],
                    [style["fill"] for _, style in base])
    result.problems = layout_problems(spec, result)
    return result


def standard_size_used(spec, lay):
    return round(spec["title"]["standard"]["size"] * lay.scale) if lay.scale < 1 \
        else spec["title"]["standard"]["size"]


def layout_problems(spec, lay):
    problems = []
    limit = spec["title"]["max_width"]
    if max(lay.widths) > limit + TOLERANCE:
        problems.append(f"a title line is {max(lay.widths):g}px wide, over the {limit:g}px maximum")
    smallest = spec["title"]["min_size"]
    if standard_size_used(spec, lay) < smallest:
        problems.append(
            f"title scaled to {standard_size_used(spec, lay)}px, below the {smallest:g}px minimum;"
            " shorten the lines")
    return problems


# ---------------------------------------------------------------------- SVG

def num(value):
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return repr(value) if isinstance(value, float) else str(value)


def css_family(family):
    if family.lower() in GENERIC_FAMILIES:
        return family
    return '"' + family.replace("\\", "\\\\").replace('"', '\\"') + '"'


def svg_family(family):
    return family if family.lower() in GENERIC_FAMILIES else family.replace('"', "")


def render_svg(spec, inp, lay, folder, title, input_sha256):
    """The header as SVG text, with the build record in <metadata>."""
    data = spec.data
    width, height = data["canvas"]["width"], data["canvas"]["height"]
    family = html.escape(svg_family(spec.family), quote=True)
    title_x = num(data["title"]["x"])
    record = {
        "title": title, "spec_sha256": spec.sha256, "input_sha256": input_sha256,
        "sizes": lay.sizes, "scale": round(lay.scale, 6),
        "max_width": max(lay.widths), "width_limit": data["title"]["max_width"],
        "standard_size": standard_size_used(data, lay),
    }
    out = [
        f"<!-- Render this file with the template font ({html.escape(spec.family, quote=False)}); "
        "without it text falls back to a default font. "
        f"Rebuild with: scripts/writing header build {folder} -->",
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img">',
        f'<metadata id="{METADATA_ID}">'
        f'{html.escape(json.dumps(record, ensure_ascii=False, sort_keys=True), quote=False)}'
        "</metadata>",
        f'<rect width="{width}" height="{height}" fill="{data["canvas"]["background"]}"/>',
    ]
    mark = data["watermark"]
    if inp.number:
        out.append(
            f'<text x="{num(mark["x"])}" y="{num(mark["baseline"])}" text-anchor="{mark["anchor"]}" '
            f'font-family="{family}" font-weight="{mark["weight"]}" font-size="{num(mark["size"])}" '
            f'letter-spacing="{num(mark["letter_spacing"])}" fill="{mark["fill"]}">'
            f"{html.escape(inp.number, quote=False)}</text>")
    for rule in data.get("rule", []):
        out.append(f'<rect x="0" y="{num(rule["y"])}" width="{width}" '
                   f'height="{num(rule["height"])}" fill="{rule["fill"]}" '
                   f'opacity="{num(rule["opacity"])}"/>')
    for index, text in enumerate(inp.lines):
        style = data["title"]["emphasis" if index + 1 == inp.gold else "standard"]
        out.append(
            f'<text x="{title_x}" y="{lay.baselines[index]}" font-family="{family}" '
            f'font-weight="{style["weight"]}" font-size="{lay.sizes[index]}" '
            f'letter-spacing="{num(style["letter_spacing"])}" fill="{style["fill"]}">'
            f"{html.escape(text, quote=False)}</text>")
    sep = data["separator"]
    out.append(f'<rect x="{num(sep["x"])}" y="{num(sep["y"])}" width="{num(sep["width"])}" '
               f'height="{num(sep["height"])}" fill="{sep["fill"]}"/>')
    deck = data["deck"]
    for index, text in enumerate(inp.deck):
        out.append(
            f'<text x="{num(deck["x"])}" y="{num(deck["baselines"][index])}" '
            f'font-family="{family}" font-weight="{deck["weight"]}" '
            f'font-size="{num(deck["size"])}" fill="{deck["fills"][index]}">'
            f"{html.escape(text, quote=False)}</text>")
    out.append("</svg>")
    return "\n".join(out) + "\n"


def read_build_record(svg_path):
    """The record render_svg stored in <metadata>, or None when absent or unreadable."""
    try:
        root = ET.parse(svg_path).getroot()
    except (OSError, ET.ParseError):
        return None
    for element in root.iter("{http://www.w3.org/2000/svg}metadata"):
        if element.get("id") == METADATA_ID:
            try:
                record = json.loads(element.text or "")
            except ValueError:
                return None
            return record if isinstance(record, dict) else None
    return None


# ---------------------------------------------------------------------- PNG

def png_size(path):
    """Width and height from the IHDR chunk, or None when the file is not a PNG."""
    try:
        with open(path, "rb") as file:
            head = file.read(24)
    except OSError:
        return None
    if len(head) < 24 or head[:8] != b"\x89PNG\r\n\x1a\n" or head[12:16] != b"IHDR":
        return None
    return struct.unpack(">II", head[16:24])


# ---------------------------------------------------------------- Chromium

def find_chromium(environ=None, which=shutil.which):
    environ = os.environ if environ is None else environ
    configured = environ.get("WRITING_CHROMIUM")
    if configured:
        if not Path(configured).is_file():
            raise HeaderError("WRITING_CHROMIUM does not point to a file")
        return configured
    for name in BROWSERS:
        found = which(name)
        if found:
            return found
    raise HeaderError("Chromium not found: install chromium or google-chrome, "
                      "or set WRITING_CHROMIUM to the binary")


def font_face_css(spec):
    path = spec.font_path
    if path is None:
        return ""
    low, high = spec.data["font"]["weight_min"], spec.data["font"]["weight_max"]
    return (f'@font-face {{ font-family: {css_family(spec.family)}; '
            f'src: url("{path.resolve().as_uri()}"); font-weight: {low} {high}; }}\n')


def used_weights(spec, weights=()):
    data = spec.data
    found = {data["title"]["standard"]["weight"], data["title"]["emphasis"]["weight"],
             data["deck"]["weight"], data["watermark"]["weight"], *weights}
    return sorted(found)


def run_browser(browser, args, timeout=90):
    with tempfile.TemporaryDirectory(prefix="writing-header-profile-") as profile:
        command = [browser, "--headless=new", "--disable-gpu", "--no-sandbox", "--hide-scrollbars",
                   "--allow-file-access-from-files", "--no-first-run",
                   f"--user-data-dir={profile}", *args]
        try:
            return subprocess.run(command, capture_output=True, text=True, timeout=timeout,
                                  check=False)
        except subprocess.TimeoutExpired:
            raise HeaderError("Chromium timed out") from None
        except OSError as error:
            raise HeaderError(f"could not start Chromium: {error}") from None


MEASURE_PAGE = """<!doctype html><meta charset="utf-8">
<style>%(face)s</style><body><pre id="o"></pre><script>
(async () => {
  const D = %(data)s;
  const out = {widths: [], faces: [], probe: null, error: null};
  try {
    for (const w of D.weights) { await document.fonts.load(`${w} 48px ${D.family}`, D.probe); }
    for (const j of D.jobs) { await document.fonts.load(`${j.weight} ${j.size}px ${D.family}`, j.text); }
    await document.fonts.ready;
    const c = document.createElement('canvas').getContext('2d');
    out.widths = D.jobs.map(j => {
      c.font = `${j.weight} ${j.size}px ${D.family}, monospace`;
      const n = Array.from(j.text).length;
      return Math.round((c.measureText(j.text).width + j.tracking * (n - 1)) * 100) / 100;
    });
    out.faces = Array.from(document.fonts).map(f => ({family: f.family, weight: f.weight, status: f.status}));
    if (D.probeFamily) {
      const w = D.weights[D.weights.length - 1];
      const m = f => { c.font = `${w} 48px ${f}`; return c.measureText(D.probe).width; };
      out.probe = {font: m(`${D.family}, monospace`), monospace: m('monospace'), serif: m('serif')};
    }
  } catch (e) { out.error = String(e); }
  document.getElementById('o').textContent = '@@' + JSON.stringify(out) + '@@';
})();
</script></body>"""


def measure_page(spec, jobs):
    family = css_family(spec.family)
    data = {"family": family, "jobs": jobs, "weights": used_weights(spec, [j["weight"] for j in jobs]),
            "probe": PROBE_TEXT, "probeFamily": family.lower().strip('"') not in GENERIC_FAMILIES}
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return MEASURE_PAGE % {"face": font_face_css(spec), "data": payload}


def font_report_problems(spec, report):
    """Problems in the page's font report; a missing font must never fall back silently."""
    problems = []
    if report.get("error"):
        problems.append(f"font loading raised an error: {report['error']}")
    if spec.font_path is not None:
        faces = [f for f in report.get("faces", []) if f.get("family", "").strip('"') == spec.family]
        if not faces:
            problems.append("the template font was never declared in the page")
        for face in faces:
            if face.get("status") != "loaded":
                problems.append(f"template font face status is {face.get('status')}, not loaded")
    probe = report.get("probe")
    if probe is not None:
        if probe["font"] == probe["monospace"] or probe["font"] == probe["serif"]:
            problems.append("the template font did not load: text measured the same as a "
                            "fallback font")
    return problems


def measure_with_browser(spec, jobs, browser, timeout=90):
    """Measure title lines in the browser; also verify the template font loaded."""
    spec.verify_font_file()
    with tempfile.TemporaryDirectory(prefix="writing-header-measure-") as folder:
        page = Path(folder) / "measure.html"
        page.write_text(measure_page(spec, jobs), encoding="utf-8")
        result = run_browser(browser, ["--virtual-time-budget=10000", "--dump-dom",
                                       page.resolve().as_uri()], timeout)
    found = re.search(r"@@(.*?)@@", result.stdout, re.S)
    if not found:
        raise HeaderError("text measurement failed: Chromium returned no result")
    report = json.loads(html.unescape(found[1]))
    problems = font_report_problems(spec, report)
    if problems:
        raise HeaderError("; ".join(problems))
    if len(report["widths"]) != len(jobs):
        raise HeaderError("text measurement failed: wrong number of widths")
    return report["widths"]


def screenshot_page(spec, svg):
    """An HTML wrapper declaring the template font around the inline SVG."""
    data = spec.data["canvas"]
    families = css_family(spec.family)
    loads = [f"{w} 16px {families}" for w in used_weights(spec)]
    script = ("<script>Promise.all(" + json.dumps(loads).replace("</", "<\\/") +
              ".map(f => document.fonts.load(f, 'Aa0'))).then(() => document.fonts.ready);</script>")
    return (f'<!doctype html><meta charset="utf-8"><style>{font_face_css(spec)}'
            f'html, body {{ margin: 0; padding: 0; background: {data["background"]}; }}'
            f'svg {{ display: block; }}</style><body>{svg}{script}</body>')


def rasterise(spec, svg, destination, browser, timeout=90):
    """Screenshot the SVG at exactly the canvas size, scale factor 1, to `destination`."""
    spec.verify_font_file()
    width, height = spec.data["canvas"]["width"], spec.data["canvas"]["height"]
    with tempfile.TemporaryDirectory(prefix="writing-header-shot-") as folder:
        page = Path(folder) / "header.html"
        page.write_text(screenshot_page(spec, svg), encoding="utf-8")
        shot = Path(folder) / "header.png"
        run_browser(browser, ["--virtual-time-budget=10000", "--force-device-scale-factor=1",
                              f"--window-size={width},{height}", f"--screenshot={shot}",
                              page.resolve().as_uri()], timeout)
        if not shot.is_file():
            raise HeaderError("Chromium produced no screenshot")
        replace_file(destination, shot.read_bytes())


def replace_file(path, data):
    path = Path(path)
    temp = path.with_name("." + path.name + ".tmp")
    try:
        temp.write_bytes(data)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


# ------------------------------------------------------------------- checks

def check_files(spec, folder_name, article_dir, title, siblings):
    """Checks that need no browser. `siblings` is [(folder, series)] for every article.

    Returns a list of Findings; the article's own series comes from `siblings`.
    """
    findings = []

    def fail(message):
        findings.append(Finding("fail", message))

    try:
        spec.verify_font_file()
    except HeaderError as error:
        fail(str(error))
    try:
        inp = load_input(article_dir / INPUT_NAME)
    except HeaderError as error:
        fail(str(error))
        return findings
    for line in inp.deck:
        if PART_OF.search(line):
            findings.append(Finding("warn", f'deck line "{line}" uses "Part N of M"; '
                                            'the house form is "Part N"'))
    findings.extend(duplicate_number_findings(article_dir.parent, folder_name, inp, siblings))

    svg_path, png_path = article_dir / SVG_NAME, article_dir / PNG_NAME
    if not svg_path.is_file():
        fail(f"{SVG_NAME} is missing; run header build")
        return findings
    record = read_build_record(svg_path)
    if record is None:
        fail(f"{SVG_NAME} has no build record; run header build")
    else:
        if record.get("title") != title:
            fail("header is stale: title changed")
        if record.get("spec_sha256") != spec.sha256:
            fail("header is stale: template spec changed")
        if record.get("input_sha256") != sha256_file(article_dir / INPUT_NAME):
            fail(f"header is stale: {INPUT_NAME} changed")
        limit = spec.data["title"]["max_width"]
        if _is(record.get("max_width"), NUMBER) and record["max_width"] > limit + TOLERANCE:
            fail(f"a title line was {record['max_width']:g}px wide, over the {limit:g}px maximum")
        smallest = spec.data["title"]["min_size"]
        if _is(record.get("standard_size"), NUMBER) and record["standard_size"] < smallest:
            fail(f"title was scaled to {record['standard_size']}px, below the {smallest:g}px minimum")
    size = png_size(png_path)
    wanted = (spec.data["canvas"]["width"], spec.data["canvas"]["height"])
    if not png_path.is_file():
        fail(f"{PNG_NAME} is missing; run header build")
    elif size is None:
        fail(f"{PNG_NAME} is not a PNG file")
    elif size != wanted:
        fail(f"{PNG_NAME} is {size[0]}x{size[1]}, not {wanted[0]}x{wanted[1]}")
    return findings


def duplicate_number_findings(articles_dir, folder_name, inp, siblings):
    if not inp.number:
        return []
    series = dict(siblings).get(folder_name)
    if not series:
        return []
    findings = []
    for other, other_series in siblings:
        if other == folder_name or other_series != series:
            continue
        other_input = articles_dir / other / INPUT_NAME
        try:
            number = parse_input(other_input.read_bytes()).number
        except (OSError, HeaderError):
            continue
        if number and int(number) == int(inp.number):
            findings.append(Finding(
                "fail", f"series number {inp.number} is already used by {other} in series {series}"))
    return findings


# -------------------------------------------------------------------- build

@dataclass
class BuildResult:
    sizes: list
    scale: float
    alt: str
    widths: list


def build(spec, folder_name, article_dir, title, siblings, browser, measure=None, render=True):
    """Validate, measure, lay out and render. Writes header.svg and header.png.

    `measure` and `browser` are injectable for tests; the default measures in Chromium.
    """
    raw = (article_dir / INPUT_NAME)
    inp = load_input(raw)
    findings = [f for f in duplicate_number_findings(article_dir.parent, folder_name, inp, siblings)]
    if findings:
        raise HeaderError("; ".join(f.message for f in findings))
    spec.verify_font_file()
    if measure is None:
        def measure(jobs):
            return measure_with_browser(spec, jobs, browser)
    lay = layout(spec.data, inp, measure)
    if lay.problems:
        raise HeaderError("; ".join(lay.problems))
    svg = render_svg(spec, inp, lay, folder_name, title, sha256_file(raw))
    replace_file(article_dir / SVG_NAME, svg.encode("utf-8"))
    if render:
        rasterise(spec, svg, article_dir / PNG_NAME, browser)
        size = png_size(article_dir / PNG_NAME)
        wanted = (spec.data["canvas"]["width"], spec.data["canvas"]["height"])
        if size != wanted:
            raise HeaderError(f"{PNG_NAME} came out {size}, not {wanted}")
    return BuildResult(lay.sizes, lay.scale, inp.alt, lay.widths)
