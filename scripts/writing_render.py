"""Shared rendering helpers for the header and figure generators.

Chromium discovery, font verification (sha256, FontFace loaded, probe-width
check), in-browser text measurement, screenshots, the PNG size reader and the
recorded-metadata helpers. This module holds no brand values: every number,
colour and font comes from a spec file in the private repo. Standard library
only; Chromium is needed just to measure text and to rasterise.
"""

from dataclasses import dataclass
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
import xml.etree.ElementTree as ET


BROWSERS = ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable")
GENERIC_FAMILIES = {"serif", "sans-serif", "monospace", "cursive", "fantasy", "system-ui",
                    "ui-serif", "ui-sans-serif", "ui-monospace", "ui-rounded"}
PROBE_TEXT = "Hamburgefonstiv 0123456789"
SHA256 = re.compile(r"[0-9a-f]{64}")
COLOUR = re.compile(r"#[0-9a-fA-F]{3,8}")
NUMBER = (int, float)
TOLERANCE = 0.01


class RenderError(ValueError):
    """A render, measurement or font step failed; the message says why."""


@dataclass
class Finding:
    level: str  # "fail" or "warn"
    message: str


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    return sha256_bytes(Path(path).read_bytes())


def is_kind(value, kind):
    """isinstance that does not treat a bool as a number."""
    if isinstance(value, bool):
        return False
    return isinstance(value, kind)


def lookup(data, dotted):
    """(value, present) for a dotted key path in nested dictionaries."""
    for part in dotted.split("."):
        if not isinstance(data, dict) or part not in data:
            return None, False
        data = data[part]
    return data, True


def num(value):
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return repr(value) if isinstance(value, float) else str(value)


def font_problems(font):
    """Problems in a spec's [font] table: family, weight range, optional vendored file."""
    problems = []
    if not isinstance(font.get("family"), str) or not font["family"].strip():
        problems.append("spec font.family must not be empty")
    low, high = font.get("weight_min"), font.get("weight_max")
    if is_kind(low, int) and is_kind(high, int) and low > high:
        problems.append("spec font weight_min exceeds weight_max")
    if "file" in font:
        if not isinstance(font["file"], str) or not font["file"]:
            problems.append("spec font.file must be a path")
        elif Path(font["file"]).is_absolute() or ".." in Path(font["file"]).parts:
            problems.append("spec font.file must be relative to the private root")
        if not isinstance(font.get("sha256"), str) or not SHA256.fullmatch(font["sha256"]):
            problems.append("spec font.sha256 is required with font.file")
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
            raise RenderError(f"template font file is missing: {self.data['font']['file']}")
        if sha256_file(path) != self.data["font"]["sha256"]:
            raise RenderError("template font file does not match the sha256 in the spec")


def css_family(family):
    if family.lower() in GENERIC_FAMILIES:
        return family
    return '"' + family.replace("\\", "\\\\").replace('"', '\\"') + '"'


def svg_family(family):
    return family if family.lower() in GENERIC_FAMILIES else family.replace('"', "")


# --------------------------------------------------------- recorded metadata

def metadata_element(metadata_id, record):
    """A <metadata> element holding the build record as JSON."""
    return (f'<metadata id="{metadata_id}">'
            f'{html.escape(json.dumps(record, ensure_ascii=False, sort_keys=True), quote=False)}'
            "</metadata>")


def read_build_record(svg_path, metadata_id):
    """The record stored in <metadata>, or None when absent or unreadable."""
    try:
        root = ET.parse(svg_path).getroot()
    except (OSError, ET.ParseError):
        return None
    for element in root.iter("{http://www.w3.org/2000/svg}metadata"):
        if element.get("id") == metadata_id:
            try:
                record = json.loads(element.text or "")
            except ValueError:
                return None
            return record if isinstance(record, dict) else None
    return None


def stale_findings(record, expected, label):
    """Failure messages for each recorded value that differs from what is current.

    `expected` maps a record key to (current value, what changed). A missing record
    is the caller's problem; here every key in `expected` is compared.
    """
    found = []
    for key, (current, what) in expected.items():
        if record.get(key) != current:
            found.append(Finding("fail", f"{label} is stale: {what} changed"))
    return found


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


def replace_file(path, data):
    path = Path(path)
    temp = path.with_name("." + path.name + ".tmp")
    try:
        temp.write_bytes(data)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


# ---------------------------------------------------------------- Chromium

def find_chromium(environ=None, which=shutil.which):
    environ = os.environ if environ is None else environ
    configured = environ.get("WRITING_CHROMIUM")
    if configured:
        if not Path(configured).is_file():
            raise RenderError("WRITING_CHROMIUM does not point to a file")
        return configured
    for name in BROWSERS:
        found = which(name)
        if found:
            return found
    raise RenderError("Chromium not found: install chromium or google-chrome, "
                      "or set WRITING_CHROMIUM to the binary")


def chromium_available():
    try:
        find_chromium()
    except RenderError:
        return False
    return True


def font_face_css(spec):
    path = spec.font_path
    if path is None:
        return ""
    low, high = spec.data["font"]["weight_min"], spec.data["font"]["weight_max"]
    return (f'@font-face {{ font-family: {css_family(spec.family)}; '
            f'src: url("{path.resolve().as_uri()}"); font-weight: {low} {high}; }}\n')


def run_browser(browser, args, timeout=90):
    with tempfile.TemporaryDirectory(prefix="writing-render-profile-") as profile:
        command = [browser, "--headless=new", "--disable-gpu", "--no-sandbox", "--hide-scrollbars",
                   "--allow-file-access-from-files", "--no-first-run",
                   f"--user-data-dir={profile}", *args]
        try:
            return subprocess.run(command, capture_output=True, text=True, timeout=timeout,
                                  check=False)
        except subprocess.TimeoutExpired:
            raise RenderError("Chromium timed out") from None
        except OSError as error:
            raise RenderError(f"could not start Chromium: {error}") from None


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


def measure_page(spec, jobs, base_weights):
    family = css_family(spec.family)
    weights = sorted({*base_weights, *(j["weight"] for j in jobs)})
    data = {"family": family, "jobs": jobs, "weights": weights,
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


def measure_with_browser(spec, jobs, browser, base_weights, timeout=90):
    """Measure text jobs in the browser; also verify the template font loaded.

    Each job is a dict with text, size, weight and tracking; the result is one
    width in pixels per job.
    """
    spec.verify_font_file()
    with tempfile.TemporaryDirectory(prefix="writing-render-measure-") as folder:
        page = Path(folder) / "measure.html"
        page.write_text(measure_page(spec, jobs, base_weights), encoding="utf-8")
        result = run_browser(browser, ["--virtual-time-budget=10000", "--dump-dom",
                                       page.resolve().as_uri()], timeout)
    found = re.search(r"@@(.*?)@@", result.stdout, re.S)
    if not found:
        raise RenderError("text measurement failed: Chromium returned no result")
    report = json.loads(html.unescape(found[1]))
    problems = font_report_problems(spec, report)
    if problems:
        raise RenderError("; ".join(problems))
    if len(report["widths"]) != len(jobs):
        raise RenderError("text measurement failed: wrong number of widths")
    return report["widths"]


def screenshot_page(spec, svg, base_weights):
    """An HTML wrapper declaring the template font around the inline SVG."""
    data = spec.data["canvas"]
    families = css_family(spec.family)
    loads = [f"{w} 16px {families}" for w in sorted(set(base_weights))]
    script = ("<script>Promise.all(" + json.dumps(loads).replace("</", "<\\/") +
              ".map(f => document.fonts.load(f, 'Aa0'))).then(() => document.fonts.ready);</script>")
    return (f'<!doctype html><meta charset="utf-8"><style>{font_face_css(spec)}'
            f'html, body {{ margin: 0; padding: 0; background: {data["background"]}; }}'
            f'svg {{ display: block; }}</style><body>{svg}{script}</body>')


def rasterise(spec, svg, destination, browser, base_weights, timeout=90):
    """Screenshot the SVG at exactly the canvas size, scale factor 1, to `destination`."""
    spec.verify_font_file()
    width, height = spec.data["canvas"]["width"], spec.data["canvas"]["height"]
    with tempfile.TemporaryDirectory(prefix="writing-render-shot-") as folder:
        page = Path(folder) / "page.html"
        page.write_text(screenshot_page(spec, svg, base_weights), encoding="utf-8")
        shot = Path(folder) / "shot.png"
        run_browser(browser, ["--virtual-time-budget=10000", "--force-device-scale-factor=1",
                              f"--window-size={width},{height}", f"--screenshot={shot}",
                              page.resolve().as_uri()], timeout)
        if not shot.is_file():
            raise RenderError("Chromium produced no screenshot")
        replace_file(destination, shot.read_bytes())
