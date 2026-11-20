"""In-article figure generator: validate, measure, lay out, render and check.

A figure is a small declarative TOML input drawn on a shared titled frame. The
canvas, colours, font, text roles and geometry come entirely from a spec file in
the private repo; this module holds no brand values. Four built-in types (bars,
flow, table, stats) cover the common figures and a custom type runs the
author's own drawing script on the same frame. Standard library only; Chromium
is needed just to measure text and to rasterise.
"""

import html
import importlib.util
from pathlib import Path
import re
import tomllib

import writing_render as render
from writing_render import (Finding, NUMBER, Spec, is_kind, num, png_size, sha256_bytes,
                            sha256_file)
import xml.etree.ElementTree as ET


FigureError = render.RenderError

SPEC_RELATIVE = ("guides", "figure-template.toml")
FIGURES_DIR = "figures"
ALT_NAME = "ALT-TEXT.md"
METADATA_ID = "figure-build"
TYPES = ("bars", "flow", "table", "stats", "custom")
NAME = re.compile(r"[a-z0-9][a-z0-9-]*")
SCRIPT_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*\.py")
DIGIT = re.compile(r"[0-9]")
EPS = 0.01
ASCENT, DESCENT = 0.8, 0.25  # text bounding box, as fractions of the font size

PALETTE_ROLES = ("primary", "descriptor", "body", "source", "focal", "structure", "divider",
                 "focal_tint", "bar", "flow", "signal", "watermark")
TEXT_ROLES = ("title", "deck", "eyebrow", "takeaway", "source", "label", "label_focal", "value",
              "value_focal", "box_label", "box_sub", "row_label", "column_header", "table_header",
              "cell", "cell_focal", "stat_value", "hero_value", "stat_label", "hero_label",
              "stat_source")
GEOMETRY = {
    "frame": ("x", "right", "title_y", "deck_y", "eyebrow_y", "takeaway_y", "plot_top",
              "plot_bottom", "plot_bottom_open", "divider_y", "divider_width", "divider_height"),
    "arrow": ("flow_width", "signal_width", "head_length", "head_half", "line_inset"),
    "zone_label": ("rule_width", "rule_height", "rule_dy"),
    "limits": ("max_focal", "max_bars", "max_boxes", "max_rows", "max_table_columns",
               "max_stat_items", "max_sources"),
    "bars": ("axis_x", "max_width", "thickness", "pitch", "bar_dy", "label_dy", "value_dy",
             "label_gap", "value_gap", "min_width", "axis_width", "above_axis_x",
             "above_max_width", "above_pitch", "above_label_dy", "above_bar_dy",
             "above_value_dy"),
    "flow": ("box_width_max", "box_height", "col_gap_min", "row_gap", "row_gap_labelled",
             "label_room", "pad_x", "label_dy", "sub_dy", "stroke_width", "row_label_dy"),
    "table": ("indent", "header_height", "header_dy", "row_height", "cell_dy", "col_gap_min",
              "col_gap_extra_max", "arrow_gap_min", "arrow_pad", "marker_width", "marker_inset",
              "rule_height"),
    "stats": ("column_width", "one_column_width", "separator_x", "separator_width", "header_dy",
              "items_top", "value_dy", "hero_value_dy", "label_gap", "label_line", "source_gap",
              "item_gap", "percent_size", "percent_dy", "percent_dx", "hero_percent_size",
              "hero_percent_dy", "hero_percent_dx"),
}
TEXT_KEYS = {"size": NUMBER, "weight": int, "fill": str, "letter_spacing": NUMBER}
FORBIDDEN_TAGS = {"filter", "linearGradient", "radialGradient", "image", "feDropShadow",
                  "feGaussianBlur", "feOffset", "pattern", "mask"}
FORBIDDEN_ATTRS = {"rx", "ry", "filter"}


# ---------------------------------------------------------------- the spec

def validate_spec(spec):
    """Return a list of problems with a figure spec dictionary."""
    problems = []

    def need(dotted, kind):
        value, present = render.lookup(spec, dotted)
        if not present:
            problems.append(f"spec is missing {dotted}")
        elif not is_kind(value, kind):
            problems.append(f"spec {dotted} has the wrong type")
        return value if present and is_kind(value, kind) else None

    for dotted, kind in (("canvas.width", int), ("canvas.height", int), ("canvas.background", str),
                         ("font.family", str), ("font.weight_min", int),
                         ("font.weight_max", int)):
        need(dotted, kind)
    for section, keys in GEOMETRY.items():
        for key in keys:
            need(f"{section}.{key}", NUMBER)
    for dotted in ("frame.source_ys", "stats.column_x"):
        need(dotted, list)
    need("arrow.dash", str)
    for role in PALETTE_ROLES:
        value = need(f"palette.{role}", str)
        if value is not None and not render.COLOUR.fullmatch(value):
            problems.append(f"spec palette.{role} must be a # colour")
    for role in TEXT_ROLES:
        for key, kind in TEXT_KEYS.items():
            need(f"text.{role}.{key}", kind)
    if problems:
        return problems
    if not render.COLOUR.fullmatch(spec["canvas"]["background"]):
        problems.append("spec canvas.background must be a # colour")
    problems.extend(render.font_problems(spec["font"]))
    for role in TEXT_ROLES:
        if spec["text"][role]["fill"] not in PALETTE_ROLES:
            problems.append(f"spec text.{role}.fill must name a palette role")
        if spec["text"][role]["size"] <= 0:
            problems.append(f"spec text.{role}.size must be positive")
    for name in ("frame.source_ys", "stats.column_x"):
        value = render.lookup(spec, name)[0]
        if not all(is_kind(v, NUMBER) for v in value) or not value:
            problems.append(f"spec {name} must be a list of numbers")
    rules = spec.get("rule", [])
    if not isinstance(rules, list):
        problems.append("spec rule must be a list of tables")
    else:
        for index, rule in enumerate(rules, 1):
            for key, kind in (("y", NUMBER), ("height", NUMBER), ("fill", str), ("opacity", NUMBER)):
                if not isinstance(rule, dict) or not is_kind(rule.get(key), kind):
                    problems.append(f"spec rule {index} needs a valid {key}")
    frame, text = spec["frame"], spec["text"]
    if not frame["plot_top"] < frame["plot_bottom"] <= frame["plot_bottom_open"]:
        problems.append("spec frame plot bounds must satisfy plot_top < plot_bottom <= "
                        "plot_bottom_open")
    if frame["plot_bottom"] > frame["takeaway_y"] - text["takeaway"]["size"]:
        problems.append("spec frame.plot_bottom must clear the takeaway line")
    if frame["plot_bottom_open"] > frame["divider_y"]:
        problems.append("spec frame.plot_bottom_open must stay above the divider")
    if len(frame["source_ys"]) < spec["limits"]["max_sources"]:
        problems.append("spec frame.source_ys needs a line for every allowed source")
    if frame["right"] <= frame["x"]:
        problems.append("spec frame.right must be right of frame.x")
    if spec["limits"]["max_focal"] < 0:
        problems.append("spec limits.max_focal must not be negative")
    if len(spec["stats"]["column_x"]) < 2:
        problems.append("spec stats.column_x needs two columns")
    return problems


class FigureSpec(Spec):
    def palette(self, role):
        return self.data["palette"][role]

    def text(self, role):
        return self.data["text"][role]

    @property
    def base_weights(self):
        return sorted({v["weight"] for v in self.data["text"].values()})


def load_spec(path, root):
    path = Path(path)
    try:
        raw = path.read_bytes()
    except OSError:
        raise FigureError(f"missing figure template spec: {path.name}") from None
    try:
        data = tomllib.loads(raw.decode("utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as error:
        raise FigureError(f"invalid figure template spec: {error}") from None
    problems = validate_spec(data)
    if problems:
        raise FigureError("invalid figure template spec: " + "; ".join(problems))
    return FigureSpec(data, sha256_bytes(raw), Path(root))


# --------------------------------------------------------- per-figure input

COMMON_KEYS = {"type", "title", "deck", "eyebrow", "takeaway", "sources", "alt", "place",
               "caption", "numbers"}
TYPE_KEYS = {
    "bars": {"label_position", "axis_label", "bar"},
    "flow": {"box", "edge", "row_label"},
    "table": {"columns", "row", "arrow_after"},
    "stats": {"column"},
    "custom": {"script"},
}


def fmt_number(value):
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _text_ok(value):
    return isinstance(value, str) and value.strip() != ""


def _table_list(data, key, problems, minimum=0):
    items = data.get(key, [])
    if not isinstance(items, list) or not all(isinstance(v, dict) for v in items):
        problems.append(f"{key} must be a list of tables")
        return []
    if len(items) < minimum:
        problems.append(f"{key} needs at least {minimum} entry" + ("" if minimum == 1 else "s"))
    return items


def _unknown(table, allowed, where, problems):
    for key in sorted(set(table) - allowed):
        problems.append(f"{where}: unknown key {key}")


def plotted_values(data):
    """[(label, strings that may stand for the value)] for bars and stats."""
    found = []
    if data.get("type") == "bars":
        for bar in data.get("bar", []):
            value = bar.get("value")
            options = [fmt_number(value)] if is_kind(value, NUMBER) else []
            if isinstance(bar.get("display"), str) and bar["display"].strip():
                options.append(bar["display"])
            found.append((bar.get("label", "?"), options))
    elif data.get("type") == "stats":
        for column in data.get("column", []):
            for item in column.get("item", []):
                found.append((item.get("label", "?"), [item["value"]]
                              if isinstance(item.get("value"), str) else []))
    return found


def _norm(text):
    return re.sub(r"\s+", " ", text.replace(",", "")).strip().lower()


def figure_text(data):
    """Every piece of text the figure's content states, for the digit heuristic."""
    out = [data.get("title"), data.get("deck"), data.get("takeaway"), data.get("eyebrow")]
    out += list(data.get("sources", [])) + list(data.get("columns", []))
    for key in ("bar", "box"):
        for item in data.get(key, []):
            out += [v for v in item.values() if isinstance(v, str)]
    for row in data.get("row", []):
        out += list(row.get("cells", []))
    for column in data.get("column", []):
        out.append(column.get("header"))
        for item in column.get("item", []):
            for value in item.values():
                out += value if isinstance(value, list) else [value]
    return [v for v in out if isinstance(v, str) and v]


def input_problems(data, limits=None):
    """Problems in a parsed figure input; `limits` is the spec's [limits] table, if known."""
    problems = []
    kind = data.get("type")
    if kind not in TYPES:
        problems.append(f"type must be one of {', '.join(TYPES)}")
        return problems
    _unknown(data, COMMON_KEYS | TYPE_KEYS[kind], "figure", problems)
    for key in ("title", "deck", "alt"):
        if not _text_ok(data.get(key)):
            problems.append(f"{key} is required and must not be empty")
    for key in ("eyebrow", "takeaway", "place", "caption", "numbers"):
        if key in data and not _text_ok(data[key]):
            problems.append(f"{key} must be a non-empty string when given")
    sources = data.get("sources", [])
    most = (limits or {}).get("max_sources", 2)
    if not isinstance(sources, list) or not all(_text_ok(s) for s in sources):
        problems.append("sources must be a list of non-empty strings")
    elif len(sources) > most:
        problems.append(f"sources has {len(sources)} lines, over the {most} allowed")
    builder = {"bars": _bars_problems, "flow": _flow_problems, "table": _table_problems,
               "stats": _stats_problems, "custom": _custom_problems}[kind]
    builder(data, limits or {}, problems)
    values = plotted_values(data)
    alt = _norm(data.get("alt", "")) if isinstance(data.get("alt"), str) else ""
    for label, options in values:
        if alt and options and not any(_norm(option) in alt for option in options):
            problems.append(f"alt text does not mention the plotted value {options[-1]} "
                            f"(for {label})")
    numeric = kind in ("bars", "stats") or any(DIGIT.search(t) for t in figure_text(data))
    if kind == "custom" and DIGIT.search(data.get("alt", "") or ""):
        numeric = True
    if numeric and not _text_ok(data.get("numbers")):
        problems.append("numbers is required when the figure shows numeric values: say where "
                        "each number comes from")
    focal = focal_elements(data)
    most_focal = (limits or {}).get("max_focal")
    if most_focal is not None and focal > most_focal:
        problems.append(f"{focal} focal elements, over the One Signal limit of {most_focal}")
    return problems


def focal_elements(data):
    """Gold elements the input will produce (the SVG count is the final authority)."""
    kind = data.get("type")
    items = lambda key: [i for i in data.get(key, []) if isinstance(i, dict)]  # noqa: E731
    if kind == "bars":
        return 2 * sum(1 for b in items("bar") if b.get("focal") is True)
    if kind == "flow":
        return sum(1 for b in items("box") if b.get("focal") is True)
    if kind == "table":
        return 2 * sum(1 for r in items("row") if r.get("focal") is True)
    if kind == "stats":
        return sum(1 for c in items("column") for i in c.get("item", [])
                   if isinstance(i, dict) and i.get("hero") is True)
    return 0


def _bars_problems(data, limits, problems):
    if data.get("label_position", "left") not in ("left", "above"):
        problems.append('label_position must be "left" or "above"')
    if "axis_label" in data and not _text_ok(data["axis_label"]):
        problems.append("axis_label must be a non-empty string when given")
    bars = _table_list(data, "bar", problems, 1)
    most = limits.get("max_bars")
    if most is not None and len(bars) > most:
        problems.append(f"{len(bars)} bars, over the limit of {most}")
    for index, bar in enumerate(bars, 1):
        _unknown(bar, {"label", "value", "display", "focal"}, f"bar {index}", problems)
        if not _text_ok(bar.get("label")):
            problems.append(f"bar {index} needs a label")
        if not is_kind(bar.get("value"), NUMBER) or bar["value"] < 0:
            problems.append(f"bar {index} value must be a number, zero or more")
        if "display" in bar and not _text_ok(bar["display"]):
            problems.append(f"bar {index} display must be a non-empty string")
        if "focal" in bar and not isinstance(bar["focal"], bool):
            problems.append(f"bar {index} focal must be true or false")
    if bars and all(is_kind(b.get("value"), NUMBER) and b["value"] == 0 for b in bars):
        problems.append("at least one bar value must be above zero")


def _flow_problems(data, limits, problems):
    boxes = _table_list(data, "box", problems, 1)
    edges = _table_list(data, "edge", problems)
    labels = _table_list(data, "row_label", problems)
    most = limits.get("max_boxes")
    if most is not None and len(boxes) > most:
        problems.append(f"{len(boxes)} boxes, over the limit of {most}")
    ids, cells = set(), {}
    for index, box in enumerate(boxes, 1):
        _unknown(box, {"id", "row", "col", "label", "sub", "focal"}, f"box {index}", problems)
        ident = box.get("id")
        if not isinstance(ident, str) or not NAME.fullmatch(ident):
            problems.append(f"box {index} needs an id of lowercase letters, digits and hyphens")
        elif ident in ids:
            problems.append(f"box id {ident} is used twice")
        else:
            ids.add(ident)
        for key in ("row", "col"):
            if not is_kind(box.get(key), NUMBER) or box[key] < 0:
                problems.append(f"box {index} {key} must be a number, zero or more")
        if not _text_ok(box.get("label")):
            problems.append(f"box {index} needs a label")
        if "sub" in box and not _text_ok(box["sub"]):
            problems.append(f"box {index} sub must be a non-empty string")
        if "focal" in box and not isinstance(box["focal"], bool):
            problems.append(f"box {index} focal must be true or false")
        if is_kind(box.get("row"), NUMBER) and is_kind(box.get("col"), NUMBER):
            cell = (box["row"], box["col"])
            if cell in cells:
                problems.append(f"boxes {cells[cell]} and {ident} share row {cell[0]:g}, "
                                f"col {cell[1]:g}")
            cells[cell] = ident
    for index, edge in enumerate(edges, 1):
        _unknown(edge, {"from", "to", "style"}, f"edge {index}", problems)
        for key in ("from", "to"):
            if edge.get(key) not in ids:
                problems.append(f"edge {index} {key} names no box")
        if edge.get("from") == edge.get("to") and edge.get("from") is not None:
            problems.append(f"edge {index} joins a box to itself")
        if edge.get("style") not in ("flow", "signal"):
            problems.append(f'edge {index} style must be "flow" or "signal"')
    for index, label in enumerate(labels, 1):
        _unknown(label, {"row", "text"}, f"row_label {index}", problems)
        if not is_kind(label.get("row"), NUMBER):
            problems.append(f"row_label {index} needs a row number")
        if not _text_ok(label.get("text")):
            problems.append(f"row_label {index} needs text")


def _table_problems(data, limits, problems):
    columns = data.get("columns")
    if not isinstance(columns, list) or not columns or not all(_text_ok(c) for c in columns):
        problems.append("columns must be a list of non-empty header strings")
        columns = []
    most = limits.get("max_table_columns")
    if most is not None and len(columns) > most:
        problems.append(f"{len(columns)} columns, over the limit of {most}")
    rows = _table_list(data, "row", problems, 1)
    most = limits.get("max_rows")
    if most is not None and len(rows) > most:
        problems.append(f"{len(rows)} rows, over the limit of {most}")
    for index, row in enumerate(rows, 1):
        _unknown(row, {"cells", "focal"}, f"row {index}", problems)
        cells = row.get("cells")
        if not isinstance(cells, list) or not all(isinstance(c, str) for c in cells):
            problems.append(f"row {index} cells must be a list of strings")
        elif columns and len(cells) != len(columns):
            problems.append(f"row {index} has {len(cells)} cells for {len(columns)} columns")
        if "focal" in row and not isinstance(row["focal"], bool):
            problems.append(f"row {index} focal must be true or false")
    if "arrow_after" in data:
        after = data["arrow_after"]
        if not is_kind(after, int) or not 0 <= after < max(len(columns) - 1, 0):
            problems.append("arrow_after must be a column index with a column after it "
                            "(0 draws the arrow between the first and second column)")


def _stats_problems(data, limits, problems):
    columns = _table_list(data, "column", problems, 1)
    if len(columns) > 2:
        problems.append(f"{len(columns)} columns, over the limit of 2")
    most = limits.get("max_stat_items")
    for index, column in enumerate(columns, 1):
        _unknown(column, {"header", "item"}, f"column {index}", problems)
        if not _text_ok(column.get("header")):
            problems.append(f"column {index} needs a header")
        items = column.get("item", [])
        if not isinstance(items, list) or not items or not all(isinstance(i, dict) for i in items):
            problems.append(f"column {index} needs at least one item")
            continue
        if most is not None and len(items) > most:
            problems.append(f"column {index} has {len(items)} items, over the limit of {most}")
        for number, item in enumerate(items, 1):
            where = f"column {index} item {number}"
            _unknown(item, {"value", "label", "source", "hero"}, where, problems)
            if not _text_ok(item.get("value")):
                problems.append(f"{where} needs a value string")
            label = item.get("label")
            lines = label if isinstance(label, list) else [label]
            if not 1 <= len(lines) <= 2 or not all(_text_ok(v) for v in lines):
                problems.append(f"{where} label must be a string or a list of up to two lines")
            if "source" in item and not _text_ok(item["source"]):
                problems.append(f"{where} source must be a non-empty string")
            if "hero" in item and not isinstance(item["hero"], bool):
                problems.append(f"{where} hero must be true or false")


def _custom_problems(data, limits, problems):
    script = data.get("script")
    if not isinstance(script, str) or not SCRIPT_NAME.fullmatch(script):
        problems.append("script must name a .py file in the figures folder (no directories)")


def parse_input(raw):
    """Parse figure TOML bytes into a dictionary, or raise FigureError."""
    try:
        return tomllib.loads(raw.decode("utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as error:
        raise FigureError(f"invalid figure input: {error}") from None


def load_input(path, limits=None):
    try:
        raw = Path(path).read_bytes()
    except OSError:
        raise FigureError(f"missing {Path(path).name}; run figure init first") from None
    data = parse_input(raw)
    problems = input_problems(data, limits)
    if problems:
        raise FigureError(f"invalid {Path(path).name}: " + "; ".join(problems))
    return data


STARTERS = {
    "bars": '''type = "bars"
title = ""      # the claim, as a headline
deck = ""       # one line of context
# eyebrow = "WHAT THE BARS COUNT"   # optional caps line above the plot
# takeaway = ""                     # optional one-line conclusion
sources = []    # up to two source lines
alt = ""        # required: read out every plotted value
# place = ""    # where in the article the figure goes
# caption = ""
numbers = ""    # required: where each number comes from
label_position = "left"   # "left" or "above"
# axis_label = "COUNT"

[[bar]]
label = ""
value = 0
# display = ""   # text shown at the bar end; defaults to the value
# focal = true   # at most one focal bar (gold bar and gold value)
''',
    "flow": '''type = "flow"
title = ""
deck = ""
# eyebrow = ""
# takeaway = ""
sources = []
alt = ""
# place = ""
# caption = ""
# numbers = ""   # required when any box shows a number
# [[row_label]]  # optional caps label above a row
# row = 0
# text = ""

[[box]]
id = "first"
row = 0
col = 0
label = ""
# sub = ""
# focal = true   # at most two focal boxes

[[box]]
id = "second"
row = 0
col = 1
label = ""

[[edge]]
from = "first"
to = "second"
style = "flow"   # "flow" (mechanism, solid) or "signal" (dashed)
''',
    "table": '''type = "table"
title = ""
deck = ""
# eyebrow = ""
# takeaway = ""
sources = []
alt = ""
# place = ""
# caption = ""
# numbers = ""   # required when any cell shows a number
columns = ["", ""]
# arrow_after = 0   # draw an arrow between this column (0-based) and the next

[[row]]
cells = ["", ""]
# focal = true
''',
    "stats": '''type = "stats"
title = ""
deck = ""
# eyebrow = ""
# takeaway = ""
sources = []
alt = ""        # required: say every value shown
# place = ""
# caption = ""
numbers = ""    # required: where each number comes from

[[column]]
header = ""

[[column.item]]
value = ""      # for example "40%"
label = ""      # a string, or a list of up to two lines
# source = ""
# hero = true   # gold display number; at most two per figure
''',
    "custom": '''type = "custom"
title = ""
deck = ""
# eyebrow = ""
# takeaway = ""
sources = []
alt = ""
# place = ""
# caption = ""
# numbers = ""   # required when the alt text or content shows numbers
script = "NAME.py"   # defines draw(fig) in this folder; it runs your own code
''',
}


def starter_input(kind):
    if kind not in STARTERS:
        raise FigureError(f"unknown figure type {kind}")
    return (f"# Figure input ({kind}). Fill every field, then run figure build.\n"
            + STARTERS[kind])


# ------------------------------------------------------------------- layout

class Ctx:
    """Drawing context: the frame, palette and text roles plus the SVG primitives.

    Text widths come from a cache filled by `measure`; a first pass collects the
    missing ones and the second pass draws with real widths, so `draw` functions
    must be pure functions of what they are given.
    """

    def __init__(self, spec, cache):
        self.spec = spec
        self.data = spec.data
        self.cache = cache
        self.misses = {}
        self.problems = []
        self.items = []        # (svg, in_plot)
        self.boxes = []        # bounding boxes of plot elements (x0, y0, x1, y1, label)
        self.connectors = []
        self.obstacles = []
        self.frame = dict(spec.data["frame"], width=spec.data["canvas"]["width"],
                          height=spec.data["canvas"]["height"])
        self.palette = dict(spec.data["palette"])
        self.family = html.escape(render.svg_family(spec.family), quote=True)

    # -- measurement
    def role(self, name):
        try:
            return self.data["text"][name]
        except KeyError:
            raise FigureError(f"unknown text role {name}") from None

    def width(self, text, role):
        style = self.role(role)
        key = (text, style["size"], style["weight"], style["letter_spacing"])
        if key not in self.cache:
            self.misses[key] = {"text": text, "size": style["size"], "weight": style["weight"],
                                "tracking": style["letter_spacing"]}
            return 0.0
        return self.cache[key]

    width_of = width

    def colour(self, role):
        if role is None:
            return None
        if role not in self.palette:
            raise FigureError(f"unknown palette role {role}")
        return self.palette[role]

    def problem(self, message):
        if message not in self.problems:
            self.problems.append(message)

    # -- primitives
    def _add(self, svg, box=None, plot=True, label=""):
        self.items.append(svg)
        if box is not None and plot:
            self.boxes.append((*box, label))

    def text(self, x, y, text, role, anchor="start", fill=None, max_width=None, what="width",
             plot=True, percent=None):
        """A text element. `percent`: (size, dy, dx) sets a trailing % as a superscript tspan."""
        style = self.role(role)
        width = self.width(text, role)
        if max_width is not None and width > max_width + render.TOLERANCE:
            self.problem(f'"{text}" is {width:g}px wide, over the {max_width:g}px {what}')
        left = {"start": x, "middle": x - width / 2, "end": x - width}[anchor]
        box = (left, y - ASCENT * style["size"], left + width, y + DESCENT * style["size"])
        colour = self.colour(fill or style["fill"])
        attrs = (f'x="{num(x)}" y="{num(y)}" font-family="{self.family}" '
                 f'font-weight="{style["weight"]}" font-size="{num(style["size"])}" '
                 f'letter-spacing="{num(style["letter_spacing"])}" fill="{colour}"')
        if anchor != "start":
            attrs += f' text-anchor="{anchor}"'
        if percent and text.endswith("%"):
            size, dy, dx = percent
            body = (f'{html.escape(text[:-1], quote=False)}<tspan font-size="{num(size)}" '
                    f'dy="{num(dy)}" dx="{num(dx)}">%</tspan>')
        else:
            body = html.escape(text, quote=False)
        self._add(f"<text {attrs}>{body}</text>", box, plot, text)

    def rect(self, x, y, w, h, fill=None, stroke=None, stroke_width=None, opacity=None,
             plot=True, label=""):
        attrs = f'x="{num(x)}" y="{num(y)}" width="{num(w)}" height="{num(h)}"'
        attrs += f' fill="{self.colour(fill)}"' if fill else ' fill="none"'
        if stroke:
            attrs += f' stroke="{self.colour(stroke)}" stroke-width="{num(stroke_width or 1)}"'
        if opacity is not None:
            attrs += f' opacity="{num(opacity)}"'
        self._add(f"<rect {attrs}/>", (x, y, x + w, y + h), plot, label or "rectangle")

    def line(self, x1, y1, x2, y2, tone="divider", width=1):
        """A straight horizontal or vertical hairline, drawn as a thin rectangle."""
        if x1 != x2 and y1 != y2:
            self.problem("lines must be horizontal or vertical")
            return
        self.rect(min(x1, x2), min(y1, y2), max(abs(x2 - x1), width if x1 == x2 else 0),
                  max(abs(y2 - y1), width if y1 == y2 else 0), fill=tone, label="line")

    def divider(self, x, y, width, plot=True):
        self.rect(x, y, width, self.data["frame"]["divider_height"], fill="divider", plot=plot,
                  label="divider")

    def marker(self, x, y, size, tone="structure"):
        """A filled square marker centred on (x, y)."""
        self.rect(x - size / 2, y - size / 2, size, size, fill=tone, label="marker")

    def zone_label(self, x, y, text, tone="structure", role="row_label", max_width=None):
        """A caps label with the short accent rule beneath it, in the label's own colour."""
        zone = self.data["zone_label"]
        self.text(x, y, text.upper(), role, fill=tone, max_width=max_width, what="label width")
        self.rect(x, y + zone["rule_dy"], zone["rule_width"], zone["rule_height"], fill=tone,
                  label="label rule")

    def avoid(self, x, y, w, h, name="box"):
        """Mark a rectangle connectors must not cross."""
        self.obstacles.append((x, y, x + w, y + h, name))

    def connector(self, points, style="flow", head=True):
        """An orthogonal connector through `points` with an optional open chevron head."""
        if style not in ("flow", "signal"):
            raise FigureError('connector style must be "flow" or "signal"')
        if len(points) < 2:
            raise FigureError("a connector needs at least two points")
        for a, b in zip(points, points[1:]):
            if a[0] != b[0] and a[1] != b[1]:
                self.problem("connectors must be orthogonal: every segment horizontal or vertical")
                return
        self.connectors.append((style, [tuple(p) for p in points], head))

    def raw(self, svg, box=None, label="raw element"):
        """Escape hatch: add an SVG element as written. The SVG checks still apply."""
        self._add(svg, box, True, label)

    # -- connectors, merged so shared trunks are drawn once
    def _flush_connectors(self):
        arrow = self.data["arrow"]
        segments, heads = {}, {}
        for style, points, head in self.connectors:
            points = list(points)
            if head:
                (x0, y0), (x1, y1) = points[-2], points[-1]
                length = abs(x1 - x0) + abs(y1 - y0)
                dx, dy = ((x1 > x0) - (x1 < x0), (y1 > y0) - (y1 < y0))
                heads[(style, x1, y1, dx, dy)] = True
                inset = min(arrow["line_inset"], length)
                points[-1] = (x1 - dx * inset, y1 - dy * inset)
            for a, b in zip(points, points[1:]):
                if a == b:
                    continue
                if a[1] == b[1]:
                    key = (style, "h", a[1])
                    segments.setdefault(key, []).append(sorted((a[0], b[0])))
                else:
                    key = (style, "v", a[0])
                    segments.setdefault(key, []).append(sorted((a[1], b[1])))
        merged = {}
        for key, spans in segments.items():
            out = []
            for lo, hi in sorted(spans):
                if out and lo <= out[-1][1] + EPS:
                    out[-1][1] = max(out[-1][1], hi)
                else:
                    out.append([lo, hi])
            merged[key] = out
        for (style, orient, fixed), spans in merged.items():
            for other in ("flow", "signal"):
                if other == style:
                    continue
                for lo, hi in spans:
                    for olo, ohi in merged.get((other, orient, fixed), []):
                        if min(hi, ohi) - max(lo, olo) > EPS:
                            self.problem("a flow connector and a signal connector overlap; "
                                         "route them apart")
        for (style, orient, fixed), spans in sorted(merged.items()):
            colour = self.palette["flow" if style == "flow" else "signal"]
            width = arrow["flow_width"] if style == "flow" else arrow["signal_width"]
            extra = f' stroke-dasharray="{arrow["dash"]}"' if style == "signal" else ""
            for lo, hi in spans:
                a, b = ((lo, fixed), (hi, fixed)) if orient == "h" else ((fixed, lo), (fixed, hi))
                self._add(f'<path d="M{num(a[0])},{num(a[1])} L{num(b[0])},{num(b[1])}" '
                          f'fill="none" stroke="{colour}" stroke-width="{num(width)}"{extra}/>',
                          (min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1])),
                          True, "connector")
                for name, ox0, oy0, ox1, oy1 in ((o[4], *o[:4]) for o in self.obstacles):
                    if orient == "h" and oy0 + EPS < fixed < oy1 - EPS \
                            and min(b[0], ox1) - max(a[0], ox0) > EPS * 2:
                        self.problem(f"a connector crosses {name}; move the boxes or the edge")
                    if orient == "v" and ox0 + EPS < fixed < ox1 - EPS \
                            and min(b[1], oy1) - max(a[1], oy0) > EPS * 2:
                        self.problem(f"a connector crosses {name}; move the boxes or the edge")
        for (style, tx, ty, dx, dy) in sorted(heads):
            colour = self.palette["flow" if style == "flow" else "signal"]
            width = arrow["flow_width"] if style == "flow" else arrow["signal_width"]
            length, half = arrow["head_length"], arrow["head_half"]
            px, py = -dy, dx
            a = (tx - dx * length + px * half, ty - dy * length + py * half)
            b = (tx - dx * length - px * half, ty - dy * length - py * half)
            self._add(f'<path class="chevron" d="M{num(a[0])},{num(a[1])} L{num(tx)},{num(ty)} '
                      f'L{num(b[0])},{num(b[1])}" fill="none" stroke="{colour}" '
                      f'stroke-width="{num(width)}" stroke-linecap="round" '
                      f'stroke-linejoin="round"/>',
                      (min(a[0], b[0], tx), min(a[1], b[1], ty), max(a[0], b[0], tx),
                       max(a[1], b[1], ty)), True, "arrow head")
        self.connectors = []


def frame_width(spec):
    return spec["frame"]["right"] - spec["frame"]["x"]


def draw_frame_top(ctx, data):
    frame = ctx.data["frame"]
    width = frame_width(ctx.data)
    ctx.text(frame["x"], frame["title_y"], data["title"], "title", max_width=width,
             what="frame width", plot=False)
    ctx.text(frame["x"], frame["deck_y"], data["deck"], "deck", max_width=width,
             what="frame width", plot=False)
    if data.get("eyebrow"):
        ctx.text(frame["x"], frame["eyebrow_y"], data["eyebrow"].upper(), "eyebrow",
                 max_width=width, what="frame width", plot=False)


def draw_frame_bottom(ctx, data):
    frame = ctx.data["frame"]
    width = frame_width(ctx.data)
    if data.get("takeaway"):
        ctx.text(frame["x"], frame["takeaway_y"], data["takeaway"], "takeaway", max_width=width,
                 what="frame width", plot=False)
    ctx.divider(frame["x"], frame["divider_y"], frame["divider_width"], plot=False)
    for text, y in zip(data.get("sources", []), frame["source_ys"]):
        ctx.text(frame["x"], y, text, "source", max_width=width, what="frame width", plot=False)


def plot_problems(ctx, data):
    """Bounds checks over everything drawn in the plot area."""
    frame = ctx.data["frame"]
    bottom = frame["plot_bottom"] if data.get("takeaway") else frame["plot_bottom_open"]
    for x0, y0, x1, y1, label in ctx.boxes:
        if x0 < frame["x"] - 1 or x1 > frame["right"] + 1:
            ctx.problem(f'"{label}" runs outside the frame '
                        f'({x0:g}-{x1:g}px, allowed {frame["x"]:g}-{frame["right"]:g}px)')
        if y0 < frame["plot_top"] - 1:
            ctx.problem(f'"{label}" starts above the plot area ({y0:g}px, top is '
                        f'{frame["plot_top"]:g}px)')
        if y1 > bottom + 1:
            what = "the takeaway line" if data.get("takeaway") else "the source lines"
            ctx.problem(f'"{label}" ends at {y1:g}px, below the plot area bottom of {bottom:g}px; '
                        f"it would crowd {what}")
    if data.get("takeaway") and ctx.boxes:
        top = frame["takeaway_y"] - ASCENT * ctx.role("takeaway")["size"]
        if max(b[3] for b in ctx.boxes) > top:
            ctx.problem("the plot overlaps the takeaway line")


def layout_bars(ctx, data):
    spec = ctx.data
    s, frame = spec["bars"], spec["frame"]
    left = data.get("label_position", "left") == "left"
    axis_x = s["axis_x"] if left else s["above_axis_x"]
    max_width = s["max_width"] if left else s["above_max_width"]
    pitch = s["pitch"] if left else s["above_pitch"]
    bar_dy = s["bar_dy"] if left else s["above_bar_dy"]
    bars = data["bar"]
    top = frame["plot_top"]
    biggest = max(b["value"] for b in bars)
    if data.get("axis_label"):
        label = data["axis_label"].upper()
        ctx.text(axis_x, frame["eyebrow_y"], label, "eyebrow", max_width=frame["right"] - axis_x,
                 what="frame width", plot=False)
        if data.get("eyebrow"):
            eyebrow_end = frame["x"] + ctx.width(data["eyebrow"].upper(), "eyebrow")
            if eyebrow_end + 20 > axis_x:
                ctx.problem("the eyebrow and axis_label overlap; use one of them or switch to "
                            "label_position left")
    for index, bar in enumerate(bars):
        y = top + index * pitch
        focal = bar.get("focal") is True
        width = bar["value"] / biggest * max_width if biggest else 0
        if bar["value"] > 0:
            width = max(width, s["min_width"])
        shown = bar.get("display") or fmt_number(bar["value"])
        if left:
            ctx.text(axis_x - s["label_gap"], y + s["label_dy"], bar["label"],
                     "label_focal" if focal else "label", anchor="end",
                     max_width=axis_x - s["label_gap"] - frame["x"], what="label gutter")
        else:
            ctx.text(axis_x, y + s["above_label_dy"], bar["label"],
                     "label_focal" if focal else "label",
                     max_width=frame["right"] - axis_x, what="label width")
        ctx.rect(axis_x, y + bar_dy, round(width, 1), s["thickness"],
                 fill="focal" if focal else "bar", label=bar["label"])
        value_x = axis_x + round(width, 1) + s["value_gap"]
        ctx.text(value_x, y + (s["value_dy"] if left else s["above_value_dy"]), shown,
                 "value_focal" if focal else "value", fill="focal" if focal else None,
                 max_width=frame["right"] - value_x, what="room right of the bar")
    height = (len(bars) - 1) * pitch + bar_dy + s["thickness"]
    ctx.rect(axis_x - s["axis_width"], top, s["axis_width"], height, fill="source", label="axis")


def layout_flow(ctx, data):
    spec = ctx.data
    s, frame = spec["flow"], spec["frame"]
    boxes = data["box"]
    labels = {l["row"]: l["text"] for l in data.get("row_label", [])}
    rows = [b["row"] for b in boxes]
    cols = [b["col"] for b in boxes]
    rmin, rmax, cmin, cmax = min(rows), max(rows), min(cols), max(cols)
    span = cmax - cmin
    count = span + 1
    width = frame["right"] - frame["x"]
    box_w = s["box_width_max"]
    if count > 1:
        box_w = min(box_w, int((width - span * s["col_gap_min"]) // count))
        pitch_x = (width - box_w) / span
    else:
        pitch_x = 0
    pitch_y = s["box_height"] + (s["row_gap_labelled"] if labels else s["row_gap"])
    room = s["label_room"] if labels else 0
    bottom = frame["plot_bottom"] if data.get("takeaway") else frame["plot_bottom_open"]
    avail = bottom - (frame["plot_top"] + room)
    height = (rmax - rmin) * pitch_y + s["box_height"]
    if height > avail:
        ctx.problem(f"the grid needs {height:g}px of height, the plot area has {avail:g}px; "
                    "use fewer rows")
    top = frame["plot_top"] + room + max(0, int((avail - height) // 2))

    def where(box):
        x = frame["x"] + (box["col"] - cmin) * pitch_x
        y = top + (box["row"] - rmin) * pitch_y
        return round(x, 2), round(y, 2)

    place = {}
    for box in boxes:
        x, y = where(box)
        place[box["id"]] = (x, y)
        focal = box.get("focal") is True
        ctx.rect(x, y, box_w, s["box_height"], stroke="focal" if focal else "structure",
                 stroke_width=s["stroke_width"], label=box["label"])
        ctx.avoid(x, y, box_w, s["box_height"], f'box "{box["label"]}"')
        inner = box_w - 2 * s["pad_x"]
        ctx.text(x + s["pad_x"], y + s["label_dy"], box["label"], "box_label", max_width=inner,
                 what="box width")
        if box.get("sub"):
            ctx.text(x + s["pad_x"], y + s["sub_dy"], box["sub"], "box_sub", max_width=inner,
                     what="box width")
    for row, text in sorted(labels.items()):
        y = top + (row - rmin) * pitch_y
        ctx.zone_label(frame["x"], y - s["row_label_dy"], text, max_width=width)
    gap = pitch_x - box_w
    lookup = {b["id"]: b for b in boxes}
    for edge in data.get("edge", []):
        a, b = lookup[edge["from"]], lookup[edge["to"]]
        ax, ay = place[a["id"]]
        bx, by = place[b["id"]]
        acy, bcy = ay + s["box_height"] / 2, by + s["box_height"] / 2
        if b["col"] > a["col"]:
            if abs(acy - bcy) < EPS:
                points = [(ax + box_w, acy), (bx, bcy)]
            else:
                trunk = round(bx - gap / 2, 2)
                points = [(ax + box_w, acy), (trunk, acy), (trunk, bcy), (bx, bcy)]
        elif b["col"] == a["col"]:
            cx = ax + box_w / 2
            if by > ay:
                points = [(cx, ay + s["box_height"]), (cx, by)]
            else:
                points = [(cx, ay), (cx, by + s["box_height"])]
        else:
            ctx.problem(f'edge from "{a["label"]}" to "{b["label"]}" runs right to left; '
                        "edges must run left to right or within one column")
            continue
        ctx.connector(points, edge["style"])


def layout_table(ctx, data):
    spec = ctx.data
    s, frame = spec["table"], spec["frame"]
    columns, rows = data["columns"], data["row"]
    count = len(columns)
    x0 = frame["x"] + s["indent"]
    avail_w = frame["right"] - x0
    widths = [max([ctx.width(columns[i].upper(), "table_header")] +
                  [ctx.width(r["cells"][i], "cell_focal" if r.get("focal") and i == 0 else "cell")
                   for r in rows]) for i in range(count)]
    arrow_after = data.get("arrow_after")
    gaps = [s["arrow_gap_min"] if i == arrow_after else s["col_gap_min"] for i in range(count - 1)]
    slack = avail_w - sum(widths) - sum(gaps)
    if count > 1 and slack < -render.TOLERANCE:
        ctx.problem(f"the table needs {sum(widths) + sum(gaps):g}px of width, the frame has "
                    f"{avail_w:g}px; shorten the cells or drop a column")
    extra = min(max(slack, 0) / max(count - 1, 1), s["col_gap_extra_max"]) if count > 1 else 0
    gaps = [g + extra for g in gaps]
    rails = [x0]
    for i in range(count - 1):
        rails.append(rails[-1] + widths[i] + gaps[i])
    bottom = frame["plot_bottom"] if data.get("takeaway") else frame["plot_bottom_open"]
    height = s["header_height"] + len(rows) * s["row_height"]
    if frame["plot_top"] + height > bottom:
        ctx.problem(f"the table needs {height:g}px of height, the plot area has "
                    f"{bottom - frame['plot_top']:g}px; use fewer rows")
    top = frame["plot_top"]
    for i, name in enumerate(columns):
        ctx.text(rails[i], top + s["header_dy"], name.upper(), "table_header",
                 max_width=widths[i] + (gaps[i] if i < count - 1 else 0), what="column width")
    ctx.rect(frame["x"], top + s["header_height"] - s["rule_height"],
             frame["right"] - frame["x"], s["rule_height"], fill="divider", label="header rule")
    for index, row in enumerate(rows):
        y = top + s["header_height"] + index * s["row_height"]
        focal = row.get("focal") is True
        if focal:
            ctx.rect(frame["x"], y, frame["right"] - frame["x"], s["row_height"] - s["rule_height"],
                     fill="focal_tint", label="focal row")
            ctx.rect(frame["x"], y + s["marker_inset"], s["marker_width"],
                     s["row_height"] - 2 * s["marker_inset"], fill="focal", label="focal marker")
        for i, cell in enumerate(row["cells"]):
            role = "cell_focal" if focal and i == 0 else "cell"
            limit = widths[i] + (gaps[i] if i < count - 1 else 0)
            ctx.text(rails[i], y + s["cell_dy"], cell, role, max_width=limit, what="column width")
        ctx.rect(frame["x"], y + s["row_height"] - s["rule_height"],
                 frame["right"] - frame["x"], s["rule_height"], fill="divider", label="row rule")
        if arrow_after is not None:
            start = rails[arrow_after] + widths[arrow_after] + s["arrow_pad"]
            end = rails[arrow_after + 1] - s["arrow_pad"]
            ctx.connector([(start, y + s["row_height"] / 2), (end, y + s["row_height"] / 2)],
                          "flow")


def layout_stats(ctx, data):
    spec = ctx.data
    s, frame = spec["stats"], spec["frame"]
    columns = data["column"]
    two = len(columns) == 2
    bottom = frame["plot_bottom"] if data.get("takeaway") else frame["plot_bottom_open"]
    for index, column in enumerate(columns):
        x = spec["stats"]["column_x"][index] if two else frame["x"]
        width = s["column_width"] if two else s["one_column_width"]
        ctx.zone_label(x, frame["plot_top"] + s["header_dy"], column["header"],
                       role="column_header", max_width=width)
        y = frame["plot_top"] + s["items_top"]
        for item in column["item"]:
            hero = item.get("hero") is True
            percent = ((s["hero_percent_size"], s["hero_percent_dy"], s["hero_percent_dx"])
                       if hero else (s["percent_size"], s["percent_dy"], s["percent_dx"]))
            baseline = y + (s["hero_value_dy"] if hero else s["value_dy"])
            ctx.text(x, baseline, item["value"], "hero_value" if hero else "stat_value",
                     max_width=width, what="column width", percent=percent)
            label = item["label"] if isinstance(item["label"], list) else [item["label"]]
            baseline += s["label_gap"]
            for number, line in enumerate(label):
                ctx.text(x, baseline, line, "hero_label" if hero else "stat_label",
                         max_width=width, what="column width")
                if number < len(label) - 1:
                    baseline += s["label_line"]
            if item.get("source"):
                baseline += s["source_gap"]
                ctx.text(x, baseline, item["source"], "stat_source", max_width=width,
                         what="column width")
            y = baseline + s["item_gap"]
        if y - s["item_gap"] > bottom:
            ctx.problem(f"column {index + 1} ends at {y - s['item_gap']:g}px, below the plot "
                        f"area bottom of {bottom:g}px; use fewer or shorter items")
    if two:
        ctx.rect(s["separator_x"], frame["plot_top"], s["separator_width"],
                 bottom - frame["plot_top"], fill="divider", label="column separator")


LAYOUTS = {"bars": layout_bars, "flow": layout_flow, "table": layout_table,
           "stats": layout_stats}


def load_script(path):
    """Import the author's drawing script. This runs the author's own code."""
    path = Path(path)
    if not path.is_file():
        raise FigureError(f"custom script is missing: {path.name}")
    module_spec = importlib.util.spec_from_file_location("figure_script_" + path.stem, path)
    module = importlib.util.module_from_spec(module_spec)
    try:
        module_spec.loader.exec_module(module)
    except Exception as error:  # the author's code can fail in any way
        raise FigureError(f"custom script {path.name} failed to load: {error}") from None
    if not callable(getattr(module, "draw", None)):
        raise FigureError(f"custom script {path.name} must define draw(fig)")
    return module


def layout_custom(ctx, data, draw):
    try:
        draw(ctx)
    except FigureError:
        raise
    except Exception as error:  # the author's code can fail in any way
        raise FigureError(f"custom draw(fig) failed: {error}") from None


def layout_figure(spec, data, measure, draw=None):
    """Lay out a figure with real text widths; returns the finished context.

    `measure(jobs)` takes dicts with text, size, weight and tracking and returns
    one width in pixels per job. Pass 1 collects every text the figure needs,
    pass 2 draws with the measured widths.
    """
    cache = {}
    for _ in range(4):
        ctx = Ctx(spec, cache)
        draw_frame_top(ctx, data)
        if data["type"] == "custom":
            layout_custom(ctx, data, draw)
        else:
            LAYOUTS[data["type"]](ctx, data)
        ctx._flush_connectors()
        draw_frame_bottom(ctx, data)
        if not ctx.misses:
            plot_problems(ctx, data)
            return ctx
        keys = list(ctx.misses)
        widths = list(measure([ctx.misses[k] for k in keys]))
        if len(widths) != len(keys):
            raise FigureError("text measurement returned the wrong number of widths")
        cache.update(zip(keys, widths))
    raise FigureError("layout did not settle: text keeps changing between passes")


# ---------------------------------------------------------------------- SVG

def render_svg(spec, ctx, data, name, input_sha256, script_sha256=None):
    canvas = spec.data["canvas"]
    width, height = canvas["width"], canvas["height"]
    record = {"type": data["type"], "input_sha256": input_sha256, "spec_sha256": spec.sha256,
              "overflow": [p for p in ctx.problems if "wide, over" in p]}
    if script_sha256:
        record["script_sha256"] = script_sha256
    out = [
        f"<!-- Render this file with the template font ({html.escape(spec.family, quote=False)}); "
        "without it text falls back to a default font. "
        f"Rebuild with: scripts/writing figure build <article-folder> {name} -->",
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img">',
        render.metadata_element(METADATA_ID, record),
        f'<rect width="{width}" height="{height}" fill="{canvas["background"]}"/>',
    ]
    for rule in spec.data.get("rule", []):
        out.append(f'<rect x="0" y="{num(rule["y"])}" width="{width}" '
                   f'height="{num(rule["height"])}" fill="{rule["fill"]}" '
                   f'opacity="{num(rule["opacity"])}"/>')
    out.extend(ctx.items)
    out.append("</svg>")
    return "\n".join(out) + "\n"


# ------------------------------------------------------------------- checks

def _tag(element):
    return element.tag.rsplit("}", 1)[-1]


def svg_findings(spec, svg_text):
    """Checks that read the produced SVG: focal count, arrow styles, forbidden features."""
    try:
        root = ET.fromstring(svg_text)
    except ET.ParseError as error:
        return [Finding("fail", f"the SVG is not well-formed: {error}")]
    findings = []
    palette = {k: v.lower() for k, v in spec.data["palette"].items()}
    focal, flow, signal = palette["focal"], palette["flow"], palette["signal"]
    dash = spec.data["arrow"]["dash"]
    gold = 0
    banned = set()
    for element in root.iter():
        tag = _tag(element)
        if tag == "metadata":
            continue
        if tag in FORBIDDEN_TAGS:
            banned.add(f"<{tag}>")
        for attr in FORBIDDEN_ATTRS & set(element.attrib):
            banned.add(f"{attr} attribute")
        fill = (element.get("fill") or "").lower()
        stroke = (element.get("stroke") or "").lower()
        if focal in (fill, stroke):
            gold += 1
        dashed = element.get("stroke-dasharray")
        chevron = element.get("class") == "chevron"
        if dashed is not None:
            if stroke != signal or dashed.split() != dash.split():
                findings.append(Finding("fail", "a dashed line must use the signal colour and "
                                                "the template dash pattern"))
        if stroke == flow and dashed is not None:
            findings.append(Finding("fail", "a flow (solid) connector is dashed"))
        if stroke == signal and dashed is None and not chevron:
            findings.append(Finding("fail", "a signal-colour line is solid; signal connectors "
                                            "are dashed"))
        if stroke in (flow, signal) and tag not in ("path",):
            findings.append(Finding("fail", "arrow colours may only be used on connector paths"))
    for item in sorted(banned):
        findings.append(Finding("fail", f"forbidden SVG feature: {item}"))
    most = spec.data["limits"]["max_focal"]
    if gold > most:
        findings.append(Finding("fail", f"{gold} elements use the focal colour, over the One "
                                        f"Signal limit of {most}"))
    seen, unique = set(), []
    for finding in findings:
        if finding.message not in seen:
            seen.add(finding.message)
            unique.append(finding)
    return unique


def figure_paths(folder, name):
    return (folder / f"{name}.toml", folder / f"{name}.svg", folder / f"{name}.png")


def script_path(folder, data):
    return folder / data["script"]


def check_figure(spec, folder, name):
    """Checks that need no browser, for one figure. Returns a list of Findings."""
    findings = []

    def fail(message):
        findings.append(Finding("fail", message))

    toml_path, svg_path, png_path = figure_paths(folder, name)
    try:
        spec.verify_font_file()
    except FigureError as error:
        fail(str(error))
    try:
        data = load_input(toml_path, spec.data["limits"])
    except FigureError as error:
        fail(str(error))
        return findings
    script_hash = None
    if data["type"] == "custom":
        try:
            script_hash = sha256_file(script_path(folder, data))
        except OSError:
            fail(f"custom script {data['script']} is missing")
    if not svg_path.is_file():
        fail(f"{name}.svg is missing; run figure build")
        return findings
    record = render.read_build_record(svg_path, METADATA_ID)
    if record is None:
        fail(f"{name}.svg has no build record; run figure build")
    else:
        if record.get("input_sha256") != sha256_file(toml_path):
            fail(f"figure is stale: {name}.toml changed")
        if record.get("spec_sha256") != spec.sha256:
            fail("figure is stale: template spec changed")
        if script_hash is not None and record.get("script_sha256") != script_hash:
            fail(f"figure is stale: {data['script']} changed")
        if record.get("overflow"):
            fail("the figure was built with text over its limit: " + "; ".join(record["overflow"]))
    findings.extend(svg_findings(spec, svg_path.read_text(encoding="utf-8")))
    size = png_size(png_path)
    wanted = (spec.data["canvas"]["width"], spec.data["canvas"]["height"])
    if not png_path.is_file():
        fail(f"{name}.png is missing; run figure build")
    elif size is None:
        fail(f"{name}.png is not a PNG file")
    elif size != wanted:
        fail(f"{name}.png is {size[0]}x{size[1]}, not {wanted[0]}x{wanted[1]}")
    return findings


def figure_names(folder):
    if not folder.is_dir():
        return []
    return sorted(p.stem for p in folder.glob("*.toml") if NAME.fullmatch(p.stem))


def alt_text_document(folder):
    """The text of ALT-TEXT.md for every valid figure input in the folder."""
    parts = ["# Figure alt text and number sources",
             "",
             "Generated by `scripts/writing figure build`; edit the figure inputs, not this file.",
             ""]
    for name in figure_names(folder):
        try:
            data = parse_input((folder / f"{name}.toml").read_bytes())
        except (FigureError, OSError):
            continue
        if not isinstance(data.get("alt"), str):
            continue
        parts.append(f"## {name}.png ({name}.svg)")
        parts.append(f"Place: {data.get('place') or 'not set'}")
        parts.append(f'Alt text: "{data["alt"].strip()}"')
        if data.get("caption"):
            parts.append(f"Caption: {data['caption'].strip()}")
        parts.append(f"Numbers: {(data.get('numbers') or 'none').strip()}")
        sources = data.get("sources") or []
        parts.append("Source: " + (" ".join(s.strip() for s in sources) if sources else "none"))
        parts.append("")
    return "\n".join(parts)


def check_folder(spec, folder):
    """Findings for every figure in the folder plus the ALT-TEXT.md freshness check."""
    results = {}
    for name in figure_names(folder):
        results[name] = check_figure(spec, folder, name)
    alt = folder / ALT_NAME
    wanted = alt_text_document(folder)
    extra = []
    if not alt.is_file():
        extra.append(Finding("fail", f"{ALT_NAME} is missing; run figure build"))
    elif alt.read_text(encoding="utf-8") != wanted:
        extra.append(Finding("fail", f"{ALT_NAME} is out of date; run figure build"))
    return results, extra


# -------------------------------------------------------------------- build

def build(spec, name, folder, browser, measure=None, render_png=True):
    """Validate, measure, lay out and render one figure; write svg, png and ALT-TEXT.md.

    Nothing is written unless every check passes. `measure` is injectable for
    tests; the default measures in Chromium and verifies the font loaded.
    """
    toml_path, svg_path, png_path = figure_paths(folder, name)
    data = load_input(toml_path, spec.data["limits"])
    draw = None
    script_hash = None
    if data["type"] == "custom":
        path = script_path(folder, data)
        script_hash = sha256_file(path) if path.is_file() else None
        draw = load_script(path).draw
    spec.verify_font_file()
    if measure is None:
        def measure(jobs):
            return render.measure_with_browser(spec, jobs, browser, spec.base_weights)
    ctx = layout_figure(spec, data, measure, draw)
    if ctx.problems:
        raise FigureError("; ".join(ctx.problems))
    svg = render_svg(spec, ctx, data, name, sha256_file(toml_path), script_hash)
    bad = [f.message for f in svg_findings(spec, svg)]
    if bad:
        raise FigureError("; ".join(bad))
    render.replace_file(svg_path, svg.encode("utf-8"))
    if render_png:
        render.rasterise(spec, svg, png_path, browser, spec.base_weights)
        size = png_size(png_path)
        wanted = (spec.data["canvas"]["width"], spec.data["canvas"]["height"])
        if size != wanted:
            raise FigureError(f"{name}.png came out {size}, not {wanted}")
    render.replace_file(folder / ALT_NAME, alt_text_document(folder).encode("utf-8"))
    return data

