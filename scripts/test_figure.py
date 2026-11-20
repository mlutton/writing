"""Test the in-article figure generator without Chromium or any real font.

Layout tests inject text widths and use the public example spec as a neutral
fixture. One Chromium integration test per type is skipped when no browser is
available.
"""

import copy
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import tomllib
import unittest
import xml.etree.ElementTree as ET
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parent))
import writing_figure as wf  # noqa: E402
import writing_render as wr  # noqa: E402


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "writing"
EXAMPLE_SPEC = ROOT / "examples" / "figure-template.example.toml"
EXAMPLES = ROOT / "examples" / "figures"
GOLD = None  # set in load_spec below


def spec_data():
    return tomllib.loads(EXAMPLE_SPEC.read_text(encoding="utf-8"))


def make_spec(data=None, root=Path("/nowhere")):
    data = data or spec_data()
    return wf.FigureSpec(data, "spec-sha", root)


def fake_measure(per_pixel=0.5):
    def measure(jobs):
        return [len(j["text"]) * j["size"] * per_pixel + j["tracking"] * (len(j["text"]) - 1)
                for j in jobs]
    return measure


def make_png(width, height):
    def chunk(kind, data):
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))
    row = b"\x00" + b"\x00\x00\x00" * width
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(row * height)) + chunk(b"IEND", b""))


def common(kind, **extra):
    data = {"type": kind, "title": "A title", "deck": "A deck line.",
            "alt": "Alt text that says what the figure shows."}
    data.update(extra)
    return data


def bars_data(**extra):
    data = common("bars", numbers="Invented counts.", alt="Bars: alpha 30, beta 10.",
                  bar=[{"label": "Alpha", "value": 30}, {"label": "Beta", "value": 10}])
    data.update(extra)
    return data


def flow_data(**extra):
    data = common("flow",
                  box=[{"id": "a", "row": 0, "col": 0, "label": "A", "sub": "first"},
                       {"id": "b", "row": 0, "col": 1, "label": "B"},
                       {"id": "c", "row": 1, "col": 2, "label": "C"}],
                  edge=[{"from": "a", "to": "b", "style": "flow"},
                        {"from": "b", "to": "c", "style": "signal"}])
    data.update(extra)
    return data


def table_data(**extra):
    data = common("table", columns=["One", "Two", "Three"],
                  row=[{"cells": ["a", "b", "c"]}, {"cells": ["d", "e", "f"], "focal": True}])
    data.update(extra)
    return data


def stats_data(**extra):
    data = common("stats", numbers="Invented.", alt="Stats: 40% and 12 and 8%.",
                  column=[{"header": "Before", "item": [
                              {"value": "40%", "label": "late", "hero": True},
                              {"value": "12", "label": ["two", "lines"], "source": "src"}]},
                          {"header": "After", "item": [{"value": "8%", "label": "late"}]}])
    data.update(extra)
    return data


def run_layout(data, spec=None, measure=None, draw=None):
    return wf.layout_figure(spec or make_spec(), data, measure or fake_measure(), draw)


def parts(ctx):
    """Parsed (tag, attributes, text) for every drawn element."""
    out = []
    for item in ctx.items:
        element = ET.fromstring(item)
        out.append((element.tag, element.attrib, "".join(element.itertext())))
    return out


def texts(ctx):
    return {t: a for tag, a, t in parts(ctx) if tag == "text"}


def build_svg(spec, data, measure=None, draw=None, name="fig"):
    ctx = run_layout(data, spec, measure, draw)
    return ctx, wf.render_svg(spec, ctx, data, name, "input-sha")


class SpecTests(unittest.TestCase):
    def test_example_spec_is_valid(self):
        self.assertEqual(wf.validate_spec(spec_data()), [])

    def test_missing_and_mistyped_values_are_reported(self):
        data = spec_data()
        del data["frame"]["plot_top"]
        data["palette"]["focal"] = "gold"
        problems = wf.validate_spec(data)
        self.assertIn("spec is missing frame.plot_top", problems)
        self.assertIn("spec palette.focal must be a # colour", problems)
        data = spec_data()
        data["text"]["title"]["fill"] = "nonsense"
        self.assertTrue(any("text.title.fill" in p for p in wf.validate_spec(data)))

    def test_plot_area_must_clear_the_takeaway(self):
        data = spec_data()
        data["frame"]["plot_bottom"] = data["frame"]["takeaway_y"]
        self.assertTrue(any("clear the takeaway" in p for p in wf.validate_spec(data)))

    def test_font_block_is_checked_like_the_header_spec(self):
        data = spec_data()
        data["font"]["file"] = "/abs/font.ttf"
        problems = wf.validate_spec(data)
        self.assertTrue(any("relative to the private root" in p for p in problems))
        self.assertTrue(any("sha256 is required" in p for p in problems))

    def test_load_spec_records_the_hash(self):
        spec = wf.load_spec(EXAMPLE_SPEC, "/nowhere")
        self.assertEqual(spec.sha256, wr.sha256_file(EXAMPLE_SPEC))

    def test_load_spec_rejects_missing_and_invalid_files(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(wf.FigureError, "missing figure template"):
                wf.load_spec(Path(folder) / "none.toml", folder)
            bad = Path(folder) / "bad.toml"
            bad.write_text("canvas = [", encoding="utf-8")
            with self.assertRaisesRegex(wf.FigureError, "invalid figure template"):
                wf.load_spec(bad, folder)


class InputTests(unittest.TestCase):
    limits = spec_data()["limits"]

    def problems(self, data):
        return wf.input_problems(data, self.limits)

    def test_valid_inputs_of_every_type_pass(self):
        for data in (bars_data(), flow_data(), table_data(), stats_data(),
                     common("custom", script="draw.py")):
            with self.subTest(type=data["type"]):
                self.assertEqual(self.problems(data), [])

    def test_unknown_type_and_unknown_keys(self):
        self.assertTrue(any("type must be" in p for p in self.problems({"type": "pie"})))
        self.assertIn("figure: unknown key colour", self.problems(bars_data(colour="red")))
        self.assertIn("bar 1: unknown key size",
                      self.problems(bars_data(bar=[{"label": "A", "value": 1, "size": 2}])))

    def test_common_keys(self):
        self.assertIn("alt is required and must not be empty", self.problems(bars_data(alt=" ")))
        data = bars_data()
        del data["title"]
        self.assertIn("title is required and must not be empty", self.problems(data))
        self.assertIn("sources has 3 lines, over the 2 allowed",
                      self.problems(bars_data(sources=["a", "b", "c"])))
        self.assertIn("eyebrow must be a non-empty string when given",
                      self.problems(bars_data(eyebrow="")))

    def test_numbers_are_required_when_values_are_plotted(self):
        data = bars_data()
        del data["numbers"]
        self.assertTrue(any(p.startswith("numbers is required") for p in self.problems(data)))
        data = stats_data()
        del data["numbers"]
        self.assertTrue(any(p.startswith("numbers is required") for p in self.problems(data)))
        # a flow with digits in its text needs numbers; one without does not
        self.assertEqual(self.problems(flow_data()), [])
        data = flow_data()
        data["box"][0]["sub"] = "takes 3 days"
        self.assertTrue(any(p.startswith("numbers is required") for p in self.problems(data)))
        data["numbers"] = "Invented."
        self.assertEqual(self.problems(data), [])

    def test_bars_alt_must_mention_every_value(self):
        data = bars_data(alt="Bars: alpha 30 only.")
        self.assertTrue(any("does not mention the plotted value 10" in p
                            for p in self.problems(data)))

    def test_bars_alt_accepts_the_display_string_or_the_number(self):
        data = bars_data(bar=[{"label": "A", "value": 4129, "display": "4,129"},
                              {"label": "B", "value": 2.5}], alt="A is 4129 and B is 2.5.")
        self.assertEqual(self.problems(data), [])
        data["alt"] = "A is 4,129 and B is 2.5."
        self.assertEqual(self.problems(data), [])
        data["alt"] = "A is large and B is 2.5."
        self.assertTrue(any("4,129" in p for p in self.problems(data)))

    def test_stats_alt_must_mention_every_value(self):
        data = stats_data(alt="Stats: 40% and 12.")
        self.assertTrue(any("plotted value 8%" in p for p in self.problems(data)))

    def test_bars_rules(self):
        self.assertTrue(any("value must be a number" in p for p in self.problems(
            bars_data(bar=[{"label": "A", "value": -1}]))))
        self.assertTrue(any("value must be a number" in p for p in self.problems(
            bars_data(bar=[{"label": "A", "value": "3"}]))))
        self.assertTrue(any("label_position" in p for p in self.problems(
            bars_data(label_position="right"))))
        many = [{"label": f"B{i}", "value": i + 1} for i in range(9)]
        alt = " ".join(str(i + 1) for i in range(9))
        self.assertIn("9 bars, over the limit of 8", self.problems(bars_data(bar=many, alt=alt)))

    def test_one_signal_rule_on_the_input(self):
        bar = [{"label": "A", "value": 1, "focal": True}, {"label": "B", "value": 2, "focal": True}]
        self.assertTrue(any("over the One Signal limit" in p for p in self.problems(
            bars_data(bar=bar, alt="1 2"))))
        data = flow_data()
        for box in data["box"]:
            box["focal"] = True
        self.assertTrue(any("over the One Signal limit" in p for p in self.problems(data)))

    def test_flow_rules(self):
        data = flow_data()
        data["edge"][0]["to"] = "nowhere"
        self.assertTrue(any("edge 1 to names no box" in p for p in self.problems(data)))
        data = flow_data()
        data["edge"][0]["style"] = "dotted"
        self.assertTrue(any('style must be "flow" or "signal"' in p for p in self.problems(data)))
        data = flow_data()
        data["box"][1].update(row=0, col=0)
        self.assertTrue(any("share row 0, col 0" in p for p in self.problems(data)))
        data = flow_data()
        data["box"][1]["id"] = "a"
        self.assertTrue(any("used twice" in p for p in self.problems(data)))
        data = flow_data()
        data["edge"][0]["to"] = "a"
        self.assertTrue(any("joins a box to itself" in p for p in self.problems(data)))

    def test_table_rules(self):
        data = table_data()
        data["row"][0]["cells"] = ["a", "b"]
        self.assertTrue(any("2 cells for 3 columns" in p for p in self.problems(data)))
        self.assertTrue(any("arrow_after" in p for p in self.problems(table_data(arrow_after=2))))
        self.assertEqual(self.problems(table_data(arrow_after=1)), [])
        too_many = table_data(row=[{"cells": ["a", "b", "c"]}] * 7)
        self.assertIn("7 rows, over the limit of 6", self.problems(too_many))

    def test_stats_rules(self):
        items = [{"value": str(i), "label": "x"} for i in range(4)]
        data = stats_data(column=[{"header": "H", "item": items}], alt="0 1 2 3")
        self.assertTrue(any("4 items, over the limit of 3" in p for p in self.problems(data)))
        data = stats_data(column=[{"header": "H", "item": [{"value": "1", "label": ["a", "b", "c"]}]}],
                          alt="1")
        self.assertTrue(any("up to two lines" in p for p in self.problems(data)))

    def test_custom_script_name_is_a_plain_file_name(self):
        for bad in ("../x.py", "dir/x.py", "x.txt", ""):
            with self.subTest(script=bad):
                self.assertTrue(any("script must name" in p
                                    for p in self.problems(common("custom", script=bad))))

    def test_parse_input_reports_toml_errors(self):
        with self.assertRaisesRegex(wf.FigureError, "invalid figure input"):
            wf.parse_input(b"type = ")


class BarLayoutTests(unittest.TestCase):
    def setUp(self):
        self.spec = make_spec()
        self.s = self.spec.data["bars"]
        self.frame = self.spec.data["frame"]

    def bar_rects(self, ctx):
        return [a for tag, a, _ in parts(ctx) if tag == "rect" and a.get("fill") == self.spec.palette("bar")]

    def test_the_largest_bar_takes_the_full_width_and_others_scale(self):
        ctx = run_layout(bars_data())
        widths = [float(a["width"]) for a in self.bar_rects(ctx)]
        self.assertEqual(widths[0], self.s["max_width"])
        self.assertAlmostEqual(widths[1], self.s["max_width"] / 3, places=1)

    def test_left_labels_are_right_aligned_in_the_gutter(self):
        ctx = run_layout(bars_data())
        label = texts(ctx)["Alpha"]
        self.assertEqual(label["text-anchor"], "end")
        self.assertEqual(float(label["x"]), self.s["axis_x"] - self.s["label_gap"])
        self.assertEqual(float(label["y"]), self.frame["plot_top"] + self.s["label_dy"])

    def test_above_labels_sit_over_each_bar_and_use_the_wider_axis(self):
        ctx = run_layout(bars_data(label_position="above"))
        label = texts(ctx)["Alpha"]
        self.assertNotIn("text-anchor", label)
        self.assertEqual(float(label["x"]), self.s["above_axis_x"])
        widths = [float(a["width"]) for a in self.bar_rects(ctx)]
        self.assertEqual(widths[0], self.s["above_max_width"])
        second = texts(ctx)["Beta"]
        self.assertEqual(float(second["y"]) - float(label["y"]), self.s["above_pitch"])

    def test_value_text_follows_the_bar_end_and_defaults_to_the_value(self):
        data = bars_data(bar=[{"label": "A", "value": 30, "display": "thirty"},
                              {"label": "B", "value": 15}], alt="thirty 15")
        ctx = run_layout(data)
        shown = texts(ctx)
        self.assertEqual(float(shown["thirty"]["x"]),
                         self.s["axis_x"] + self.s["max_width"] + self.s["value_gap"])
        self.assertIn("15", shown)

    def test_focal_bar_is_gold_with_a_gold_value_and_plain_label(self):
        data = bars_data()
        data["bar"][1]["focal"] = True
        ctx, svg = build_svg(self.spec, data)
        gold = self.spec.palette("focal").lower()
        coloured = [e for e in ET.fromstring(svg).iter()
                    if gold in ((e.get("fill") or "").lower(), (e.get("stroke") or "").lower())]
        self.assertEqual(len(coloured), 2)
        self.assertEqual(wf.svg_findings(self.spec, svg), [])

    def test_a_zero_bar_has_no_width_and_a_tiny_one_stays_visible(self):
        data = bars_data(bar=[{"label": "A", "value": 1000}, {"label": "B", "value": 0},
                              {"label": "C", "value": 1}], alt="1000 0 1")
        widths = [float(a["width"]) for a in self.bar_rects(run_layout(data))]
        self.assertEqual(widths[1], 0)
        self.assertEqual(widths[2], self.s["min_width"])

    def test_axis_label_is_drawn_in_caps_at_the_axis(self):
        ctx = run_layout(bars_data(axis_label="count"))
        self.assertEqual(float(texts(ctx)["COUNT"]["x"]), self.s["axis_x"])

    def test_eyebrow_and_axis_label_must_not_collide(self):
        ctx = run_layout(bars_data(axis_label="count", eyebrow="x" * 80, label_position="above"))
        self.assertTrue(any("overlap" in p for p in ctx.problems))


class FlowLayoutTests(unittest.TestCase):
    def setUp(self):
        self.spec = make_spec()
        self.s = self.spec.data["flow"]
        self.frame = self.spec.data["frame"]

    def boxes(self, ctx):
        return [a for tag, a, _ in parts(ctx)
                if tag == "rect" and a.get("fill") == "none" and "stroke" in a]

    def paths(self, ctx, kind):
        return [a for tag, a, _ in parts(ctx)
                if tag == "path" and (a.get("class") == "chevron") == (kind == "chevron")]

    def test_boxes_fill_the_width_on_a_grid(self):
        ctx = run_layout(flow_data())
        boxes = self.boxes(ctx)
        self.assertEqual(len(boxes), 3)
        xs = [float(b["x"]) for b in boxes]
        self.assertEqual(xs[0], self.frame["x"])
        right = float(boxes[2]["x"]) + float(boxes[2]["width"])
        self.assertAlmostEqual(right, self.frame["right"], places=1)
        self.assertEqual(float(boxes[0]["width"]), float(boxes[1]["width"]))
        pitch_y = float(boxes[2]["y"]) - float(boxes[0]["y"])
        self.assertEqual(pitch_y, self.s["box_height"] + self.s["row_gap"])

    def test_box_width_is_capped_for_few_columns(self):
        data = flow_data(box=[{"id": "a", "row": 0, "col": 0, "label": "A"},
                              {"id": "b", "row": 0, "col": 1, "label": "B"}],
                         edge=[{"from": "a", "to": "b", "style": "flow"}])
        boxes = self.boxes(run_layout(data))
        self.assertEqual(float(boxes[0]["width"]), self.s["box_width_max"])

    def test_the_grid_is_centred_in_the_plot_area(self):
        ctx = run_layout(flow_data(takeaway="Take."))
        boxes = self.boxes(ctx)
        top = float(boxes[0]["y"])
        bottom = float(boxes[2]["y"]) + float(boxes[2]["height"])
        space_above = top - self.frame["plot_top"]
        space_below = self.frame["plot_bottom"] - bottom
        self.assertLessEqual(abs(space_above - space_below), 1)

    def test_a_straight_edge_in_one_row_has_one_line_and_one_head(self):
        data = flow_data(box=flow_data()["box"][:2], edge=[flow_data()["edge"][0]])
        ctx = run_layout(data)
        self.assertEqual(len(self.paths(ctx, "line")), 1)
        self.assertEqual(len(self.paths(ctx, "chevron")), 1)

    def test_an_elbow_edge_runs_out_across_down_and_in(self):
        ctx = run_layout(flow_data())
        signal = [p for p in self.paths(ctx, "line") if "stroke-dasharray" in p]
        self.assertEqual(len(signal), 3)  # horizontal out, vertical, horizontal in
        for path in signal:
            self.assertEqual(path["stroke"], self.spec.palette("signal"))
            self.assertEqual(path["stroke-dasharray"], self.spec.data["arrow"]["dash"])
        head = [p for p in self.paths(ctx, "chevron") if p["stroke"] == self.spec.palette("signal")]
        self.assertNotIn("stroke-dasharray", head[0])

    def verticals(self, ctx):
        found = []
        for p in self.paths(ctx, "line"):
            start, end = p["d"].replace("M", "").split(" L")
            if start.split(",")[0] == end.split(",")[0]:
                found.append(p)
        return found

    def fan(self, outwards):
        boxes = [{"id": "hub", "row": 1, "col": 0 if outwards else 1, "label": "Hub"}]
        for index in range(3):
            boxes.append({"id": f"s{index}", "row": index, "col": 1 if outwards else 0,
                          "label": f"S{index}"})
        edges = [{"from": "hub", "to": f"s{i}", "style": "flow"} if outwards else
                 {"from": f"s{i}", "to": "hub", "style": "flow"} for i in range(3)]
        return flow_data(box=boxes, edge=edges)

    def test_fan_out_shares_one_trunk_and_has_a_head_per_target(self):
        ctx = run_layout(self.fan(True))
        self.assertEqual(ctx.problems, [])
        lines = self.paths(ctx, "line")
        heads = self.paths(ctx, "chevron")
        self.assertEqual(len(heads), 3)
        verticals = self.verticals(ctx)
        self.assertEqual(len(verticals), 1)  # one shared vertical trunk
        # shared segments are drawn once: a naive route would need seven lines
        self.assertEqual(len(lines), 4)

    def test_fan_in_shares_one_trunk_and_one_head(self):
        ctx = run_layout(self.fan(False))
        self.assertEqual(ctx.problems, [])
        self.assertEqual(len(self.paths(ctx, "chevron")), 1)
        self.assertEqual(len(self.verticals(ctx)), 1)
        self.assertEqual(len(self.paths(ctx, "line")), 4)

    def test_an_edge_that_crosses_a_box_is_refused(self):
        data = flow_data(box=[{"id": "a", "row": 0, "col": 0, "label": "A"},
                              {"id": "m", "row": 0, "col": 1, "label": "M"},
                              {"id": "c", "row": 0, "col": 2, "label": "C"}],
                         edge=[{"from": "a", "to": "c", "style": "flow"}])
        ctx = run_layout(data)
        self.assertTrue(any('crosses box "M"' in p for p in ctx.problems))

    def test_right_to_left_edges_are_refused(self):
        data = flow_data(edge=[{"from": "b", "to": "a", "style": "flow"}])
        self.assertTrue(any("right to left" in p for p in run_layout(data).problems))

    def test_vertical_edges_within_a_column(self):
        data = flow_data(box=[{"id": "a", "row": 0, "col": 0, "label": "A"},
                              {"id": "b", "row": 1, "col": 0, "label": "B"}],
                         edge=[{"from": "a", "to": "b", "style": "flow"}])
        ctx = run_layout(data)
        self.assertEqual(ctx.problems, [])
        self.assertEqual(len(self.paths(ctx, "line")), 1)

    def test_flow_and_signal_edges_may_not_share_a_segment(self):
        data = flow_data(box=[{"id": "a", "row": 0, "col": 0, "label": "A"},
                              {"id": "b", "row": 1, "col": 1, "label": "B"},
                              {"id": "c", "row": 2, "col": 1, "label": "C"}],
                         edge=[{"from": "a", "to": "b", "style": "flow"},
                               {"from": "a", "to": "c", "style": "signal"}])
        self.assertTrue(any("overlap" in p for p in run_layout(data).problems))

    def test_row_labels_are_drawn_in_caps_with_a_rule(self):
        data = flow_data(row_label=[{"row": 0, "text": "first row"}])
        ctx = run_layout(data)
        self.assertIn("FIRST ROW", texts(ctx))
        rules = [a for tag, a, _ in parts(ctx) if tag == "rect" and
                 float(a["width"]) == self.spec.data["zone_label"]["rule_width"]]
        self.assertEqual(len(rules), 1)
        boxes = self.boxes(ctx)
        label_y = float(texts(ctx)["FIRST ROW"]["y"])
        self.assertEqual(float(boxes[0]["y"]) - label_y, self.s["row_label_dy"])
        self.assertEqual(float(boxes[2]["y"]) - float(boxes[0]["y"]),
                         self.s["box_height"] + self.s["row_gap_labelled"])

    def test_box_text_must_fit_the_box(self):
        data = flow_data()
        data["box"][0]["label"] = "A very long box label that cannot fit in a box"
        problems = run_layout(data).problems
        self.assertTrue(any("A very long box label" in p and "box width" in p for p in problems))


class TableLayoutTests(unittest.TestCase):
    def setUp(self):
        self.spec = make_spec()
        self.s = self.spec.data["table"]
        self.frame = self.spec.data["frame"]

    def test_columns_start_on_rails_left_to_right(self):
        ctx = run_layout(table_data())
        xs = [float(a["x"]) for tag, a, t in parts(ctx) if tag == "text" and t in ("ONE", "TWO",
                                                                                 "THREE")]
        self.assertEqual(xs[0], self.frame["x"] + self.s["indent"])
        self.assertEqual(xs, sorted(xs))
        # cells sit on the same rails as the headers
        cells = {t: float(a["x"]) for tag, a, t in parts(ctx) if tag == "text"}
        self.assertEqual(cells["a"], xs[0])
        self.assertEqual(cells["e"], xs[1])
        self.assertEqual(cells["f"], xs[2])

    def test_row_pitch_and_rules(self):
        ctx = run_layout(table_data())
        cells = {t: float(a["y"]) for tag, a, t in parts(ctx) if tag == "text"}
        self.assertEqual(cells["d"] - cells["a"], self.s["row_height"])
        self.assertEqual(cells["a"], self.frame["plot_top"] + self.s["header_height"]
                         + self.s["cell_dy"])

    def test_arrow_after_draws_one_arrow_per_row_in_the_gap(self):
        ctx = run_layout(table_data(arrow_after=0))
        heads = [a for tag, a, _ in parts(ctx) if a.get("class") == "chevron"]
        self.assertEqual(len(heads), 2)
        rails = {t: float(a["x"]) for tag, a, t in parts(ctx) if tag == "text"}
        lines = [a for tag, a, _ in parts(ctx) if tag == "path" and a.get("class") != "chevron"]
        for line in lines:
            start, end = line["d"].replace("M", "").split(" L")
            self.assertGreater(float(start.split(",")[0]), rails["a"])
            self.assertLess(float(end.split(",")[0]), rails["b"])

    def test_the_arrow_gap_is_at_least_the_spec_minimum(self):
        ctx = run_layout(table_data(arrow_after=1))
        rails = {t: float(a["x"]) for tag, a, t in parts(ctx) if tag == "text"}
        width_e = fake_measure()([{"text": "Two".upper(), "size": 12, "weight": 700,
                                   "tracking": 2}])[0]
        self.assertGreaterEqual(rails["c"] - rails["b"] - width_e, self.s["arrow_gap_min"] - 1)

    def test_a_focal_row_gets_a_marker_tint_and_a_gold_first_cell(self):
        ctx, svg = build_svg(self.spec, table_data())
        gold = self.spec.palette("focal").lower()
        hits = [e for e in ET.fromstring(svg).iter() if (e.get("fill") or "").lower() == gold]
        self.assertEqual(len(hits), 2)
        tint = [e for e in ET.fromstring(svg).iter()
                if (e.get("fill") or "").lower() == self.spec.palette("focal_tint").lower()]
        self.assertEqual(len(tint), 1)

    def test_a_table_wider_than_the_frame_is_refused(self):
        data = table_data()
        data["row"][0]["cells"][0] = "x" * 120
        self.assertTrue(any("of width" in p for p in run_layout(data).problems))

    def test_too_tall_a_table_is_refused(self):
        data = table_data(row=[{"cells": ["a", "b", "c"]}] * 6, takeaway="Take.")
        spec = make_spec()
        spec.data["table"]["row_height"] = 80
        self.assertTrue(any("of height" in p for p in run_layout(data, spec).problems))


class StatsLayoutTests(unittest.TestCase):
    def setUp(self):
        self.spec = make_spec()
        self.s = self.spec.data["stats"]

    def test_two_columns_use_the_spec_rails_and_a_separator(self):
        ctx = run_layout(stats_data())
        shown = texts(ctx)
        self.assertEqual(float(shown["BEFORE"]["x"]), self.s["column_x"][0])
        self.assertEqual(float(shown["AFTER"]["x"]), self.s["column_x"][1])
        separators = [a for tag, a, _ in parts(ctx) if tag == "rect" and
                      float(a["x"]) == self.s["separator_x"]]
        self.assertEqual(len(separators), 1)

    def test_one_column_uses_the_frame_rail_and_no_separator(self):
        data = stats_data(column=[stats_data()["column"][0]])
        ctx = run_layout(data)
        self.assertEqual(float(texts(ctx)["BEFORE"]["x"]), self.spec.data["frame"]["x"])
        separators = [a for tag, a, _ in parts(ctx) if tag == "rect" and
                      float(a["x"]) == self.s["separator_x"]]
        self.assertEqual(separators, [])

    def test_percent_sign_is_a_superscript_tspan(self):
        ctx, svg = build_svg(self.spec, stats_data())
        self.assertIn(f'<tspan font-size="{self.s["hero_percent_size"]}"', svg)
        self.assertIn(f'dy="{self.s["hero_percent_dy"]}"', svg)

    def test_hero_uses_the_hero_role_and_counts_as_focal(self):
        ctx, svg = build_svg(self.spec, stats_data())
        gold = self.spec.palette("focal").lower()
        hits = [e for e in ET.fromstring(svg).iter() if (e.get("fill") or "").lower() == gold]
        self.assertEqual(len(hits), 1)
        self.assertEqual(float(texts(ctx)["40%"]["font-size"]),
                         self.spec.text("hero_value")["size"])

    def test_items_stack_and_two_line_labels_push_the_next_item_down(self):
        ctx = run_layout(stats_data())
        shown = texts(ctx)
        self.assertEqual(float(shown["lines"]["y"]) - float(shown["two"]["y"]),
                         self.s["label_line"])
        self.assertGreater(float(shown["12"]["y"]), float(shown["40%"]["y"]))

    def test_a_label_too_wide_for_its_column_fails(self):
        data = stats_data()
        data["column"][1]["item"][0]["label"] = "x" * 120
        self.assertTrue(any("column width" in p for p in run_layout(data).problems))

    def test_too_many_lines_for_the_plot_area_fail(self):
        item = {"value": "1", "label": ["a", "b"], "source": "s"}
        data = stats_data(column=[{"header": "H", "item": [item, item, item]}], takeaway="T",
                          alt="1")
        self.assertTrue(any("below the plot area bottom" in p for p in run_layout(data).problems))


class FrameTests(unittest.TestCase):
    def setUp(self):
        self.spec = make_spec()
        self.frame = self.spec.data["frame"]

    def test_frame_text_sits_where_the_spec_says(self):
        data = bars_data(eyebrow="what", takeaway="Take it.", sources=["Source one", "Source two"])
        ctx = run_layout(data)
        shown = texts(ctx)
        self.assertEqual(float(shown["A title"]["y"]), self.frame["title_y"])
        self.assertEqual(float(shown["A deck line."]["y"]), self.frame["deck_y"])
        self.assertEqual(float(shown["WHAT"]["y"]), self.frame["eyebrow_y"])
        self.assertEqual(float(shown["Take it."]["y"]), self.frame["takeaway_y"])
        self.assertEqual(float(shown["Source one"]["y"]), self.frame["source_ys"][0])
        self.assertEqual(float(shown["Source two"]["y"]), self.frame["source_ys"][1])
        for text in ("A title", "A deck line.", "WHAT", "Take it.", "Source one"):
            self.assertEqual(float(shown[text]["x"]), self.frame["x"])

    def test_svg_has_canvas_rules_divider_and_record(self):
        ctx, svg = build_svg(self.spec, bars_data())
        root = ET.fromstring(svg)
        self.assertEqual(root.get("width"), str(self.spec.data["canvas"]["width"]))
        rects = [e.attrib for e in root.iter("{http://www.w3.org/2000/svg}rect")]
        self.assertEqual(sum(1 for r in rects if r.get("opacity")), 2)
        self.assertTrue(any(r.get("y") == str(self.frame["divider_y"]) for r in rects))

    def test_over_wide_frame_text_fails_naming_the_text_and_the_limit(self):
        width = self.frame["right"] - self.frame["x"]
        for key in ("title", "deck", "takeaway"):
            with self.subTest(key=key):
                data = bars_data(takeaway="ok")
                data[key] = "w" * 200
                problems = run_layout(data).problems
                self.assertTrue(any("wwww" in p and f"over the {width:g}px frame width" in p
                                    for p in problems), problems)
        problems = run_layout(bars_data(sources=["s" * 300])).problems
        self.assertTrue(any("sss" in p and "frame width" in p for p in problems))
        problems = run_layout(bars_data(eyebrow="e" * 300)).problems
        self.assertTrue(any("EEE" in p and "frame width" in p for p in problems))

    def test_bar_label_too_wide_for_the_gutter_fails(self):
        data = bars_data()
        data["bar"][0]["label"] = "L" * 90
        problems = run_layout(data).problems
        gutter = self.spec.data["bars"]["axis_x"] - self.spec.data["bars"]["label_gap"] \
            - self.frame["x"]
        self.assertTrue(any("LLLL" in p and f"over the {gutter:g}px label gutter" in p
                            for p in problems), problems)

    def test_value_text_too_wide_for_the_room_right_of_the_bar_fails(self):
        data = bars_data()
        data["bar"][0]["display"] = "9" * 80
        data["alt"] = "9" * 80 + " 10"
        self.assertTrue(any("room right of the bar" in p for p in run_layout(data).problems))

    def test_no_silent_shrinking_the_text_size_never_changes(self):
        data = bars_data()
        data["title"] = "w" * 200
        ctx = run_layout(data)
        self.assertEqual(float(texts(ctx)["w" * 200]["font-size"]),
                         self.spec.text("title")["size"])
        self.assertTrue(ctx.problems)

    def test_plot_must_not_overlap_the_takeaway(self):
        many = [{"label": f"B{i}", "value": i + 1} for i in range(8)]
        data = bars_data(bar=many, alt=" ".join(str(i + 1) for i in range(8)),
                         label_position="above", takeaway="Take it.")
        problems = run_layout(data).problems
        self.assertTrue(any("below the plot area bottom" in p for p in problems), problems)
        self.assertTrue(any("overlaps the takeaway" in p for p in problems), problems)

    def test_without_a_takeaway_the_plot_may_use_the_lower_space(self):
        many = [{"label": f"B{i}", "value": i + 1} for i in range(6)]
        data = bars_data(bar=many, alt=" ".join(str(i + 1) for i in range(6)),
                         label_position="above")
        self.assertEqual(run_layout(data).problems, [])
        data["takeaway"] = "Take it."
        self.assertTrue(run_layout(data).problems)

    def test_content_outside_the_frame_is_refused(self):
        def draw(fig):
            fig.rect(fig.frame["right"] - 10, fig.frame["plot_top"] + 5, 50, 10, fill="structure")
        problems = run_layout(common("custom", script="x.py"), draw=draw).problems
        self.assertTrue(any("runs outside the frame" in p for p in problems))


class SvgCheckTests(unittest.TestCase):
    def setUp(self):
        self.spec = make_spec()
        self.palette = self.spec.data["palette"]

    def findings(self, extra):
        svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">' + extra
               + "</svg>")
        return [f.message for f in wf.svg_findings(self.spec, svg)]

    def test_clean_svg_passes(self):
        ctx, svg = build_svg(self.spec, flow_data())
        self.assertEqual(wf.svg_findings(self.spec, svg), [])

    def test_one_signal_rule_counts_gold_fills_and_strokes(self):
        gold = self.palette["focal"]
        three = (f'<rect fill="{gold}" width="1" height="1"/>'
                 f'<rect fill="none" stroke="{gold}" width="1" height="1"/>'
                 f'<text fill="{gold.upper()}">x</text>')
        self.assertTrue(any("3 elements use the focal colour" in m for m in self.findings(three)))
        two = f'<rect fill="{gold}"/><text fill="{gold}">x</text>'
        self.assertEqual(self.findings(two), [])

    def test_one_signal_rule_applies_to_custom_figures(self):
        def draw(fig):
            for index in range(3):
                fig.marker(fig.frame["x"] + 50 * (index + 1), 300, 20, "focal")
        with self.assertRaisesRegex(wf.FigureError, "3 elements use the focal colour"):
            with tempfile.TemporaryDirectory() as folder:
                self.build_custom(folder, draw)

    def build_custom(self, folder, draw):
        folder = Path(folder)
        (folder / "fig.toml").write_text(
            'type = "custom"\ntitle = "T"\ndeck = "D"\nalt = "Alt."\nscript = "fig.py"\n',
            encoding="utf-8")
        (folder / "fig.py").write_text(draw if isinstance(draw, str) else CUSTOM_GOLD,
                                       encoding="utf-8")
        return wf.build(self.spec, "fig", folder, None, fake_measure(), render_png=False)

    def test_dashed_lines_must_use_the_signal_colour(self):
        flow, signal, dash = self.palette["flow"], self.palette["signal"], self.spec.data["arrow"]["dash"]
        bad = f'<path d="M0,0 L9,0" stroke="{flow}" stroke-dasharray="{dash}"/>'
        messages = self.findings(bad)
        self.assertTrue(any("must use the signal colour" in m for m in messages))
        self.assertTrue(any("flow (solid) connector is dashed" in m for m in messages))
        other = '<path d="M0,0 L9,0" stroke="#123456" stroke-dasharray="2 2"/>'
        self.assertTrue(any("must use the signal colour" in m for m in self.findings(other)))
        good = f'<path d="M0,0 L9,0" stroke="{signal}" stroke-dasharray="{dash}"/>'
        self.assertEqual(self.findings(good), [])

    def test_solid_lines_must_use_the_flow_colour(self):
        signal = self.palette["signal"]
        messages = self.findings(f'<path d="M0,0 L9,0" stroke="{signal}"/>')
        self.assertTrue(any("signal-colour line is solid" in m for m in messages))
        chevron = f'<path class="chevron" d="M0,0 L9,0" stroke="{signal}"/>'
        self.assertEqual(self.findings(chevron), [])

    def test_arrow_colours_are_for_connector_paths_only(self):
        flow = self.palette["flow"]
        self.assertTrue(any("only be used on connector paths" in m for m in self.findings(
            f'<rect width="1" height="1" fill="none" stroke="{flow}"/>')))

    def test_forbidden_svg_features(self):
        cases = {
            "rx attribute": '<rect width="1" height="1" rx="4"/>',
            "ry attribute": '<rect width="1" height="1" ry="4"/>',
            "filter attribute": '<rect width="1" height="1" filter="url(#f)"/>',
            "<filter>": '<filter id="f"/>',
            "<linearGradient>": '<linearGradient id="g"/>',
            "<radialGradient>": '<radialGradient id="g"/>',
            "<image>": '<image href="x.png"/>',
        }
        for name, svg in cases.items():
            with self.subTest(name=name):
                self.assertIn(f"forbidden SVG feature: {name}", self.findings(svg))

    def test_a_malformed_svg_is_a_failure(self):
        found = wf.svg_findings(self.spec, "<svg")
        self.assertEqual(found[0].level, "fail")

    def test_custom_raw_elements_cannot_slip_past_the_checks(self):
        def draw(fig):
            fig.raw('<rect x="120" y="200" width="10" height="10" rx="3" fill="none" '
                    'stroke="#ffffff"/>', (120, 200, 130, 210))
        ctx, svg = build_svg(self.spec, common("custom", script="x.py"), draw=draw)
        self.assertTrue(any("rx attribute" in f.message for f in wf.svg_findings(self.spec, svg)))

    def test_connector_style_is_limited_to_flow_and_signal(self):
        ctx = wf.Ctx(self.spec, {})
        with self.assertRaisesRegex(wf.FigureError, "flow.*signal"):
            ctx.connector([(0, 0), (5, 0)], "dotted")


CUSTOM_GOLD = '''def draw(fig):
    for index in range(3):
        fig.marker(fig.frame["x"] + 50 * (index + 1), 300, 20, "focal")
'''

CUSTOM_OK = '''def draw(fig):
    f = fig.frame
    fig.zone_label(f["x"], 220, "steps")
    fig.marker(f["x"] + 30, 300, 20, "structure")
    fig.marker(f["x"] + 230, 300, 20, "focal")
    fig.connector([(f["x"] + 45, 300), (f["x"] + 215, 300)], "flow")
    fig.text(f["x"] + 230, 350, "Done", "box_label", anchor="middle", max_width=200)
    fig.avoid(f["x"] + 1000, 400, 10, 10, "nothing")
'''


class CustomTests(unittest.TestCase):
    def setUp(self):
        self.spec = make_spec()
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)

    def write(self, source, extra=""):
        (self.folder / "fig.toml").write_text(
            'type = "custom"\ntitle = "T"\ndeck = "D"\nalt = "Alt text."\nscript = "fig.py"\n'
            + extra, encoding="utf-8")
        (self.folder / "fig.py").write_text(source, encoding="utf-8")

    def test_the_hook_draws_in_the_plot_area_on_the_shared_frame(self):
        self.write(CUSTOM_OK)
        wf.build(self.spec, "fig", self.folder, None, fake_measure(), render_png=False)
        svg = (self.folder / "fig.svg").read_text(encoding="utf-8")
        self.assertIn(">STEPS<", svg)
        self.assertIn(">Done<", svg)
        self.assertIn(">T<", svg)  # the frame title is drawn by the generator
        record = wr.read_build_record(self.folder / "fig.svg", wf.METADATA_ID)
        self.assertEqual(record["script_sha256"], wr.sha256_file(self.folder / "fig.py"))

    def test_the_script_must_define_draw(self):
        self.write("x = 1\n")
        with self.assertRaisesRegex(wf.FigureError, "must define draw"):
            wf.build(self.spec, "fig", self.folder, None, fake_measure(), render_png=False)

    def test_a_missing_script_is_reported(self):
        self.write(CUSTOM_OK)
        (self.folder / "fig.py").unlink()
        with self.assertRaisesRegex(wf.FigureError, "custom script is missing"):
            wf.build(self.spec, "fig", self.folder, None, fake_measure(), render_png=False)

    def test_errors_in_the_script_become_figure_errors(self):
        self.write("def draw(fig):\n    raise RuntimeError('boom')\n")
        with self.assertRaisesRegex(wf.FigureError, "draw.fig. failed: boom"):
            wf.build(self.spec, "fig", self.folder, None, fake_measure(), render_png=False)
        self.write("raise RuntimeError('at import')\n")
        with self.assertRaisesRegex(wf.FigureError, "failed to load"):
            wf.build(self.spec, "fig", self.folder, None, fake_measure(), render_png=False)

    def test_text_in_a_custom_figure_is_fit_checked(self):
        self.write('def draw(fig):\n    fig.text(fig.frame["x"], 300, "x" * 200, "label", '
                   'max_width=100, what="column")\n')
        with self.assertRaisesRegex(wf.FigureError, "over the 100px column"):
            wf.build(self.spec, "fig", self.folder, None, fake_measure(), render_png=False)

    def test_width_of_uses_the_measured_width(self):
        seen = []

        def draw(fig):
            seen.append(fig.width_of("abcd", "label"))
        run_layout(common("custom", script="x.py"), draw=draw)
        size = self.spec.text("label")["size"]
        self.assertEqual(seen[-1], 4 * size * 0.5)

    def test_unknown_roles_are_errors(self):
        def draw(fig):
            fig.text(100, 300, "x", "no-such-role")
        with self.assertRaisesRegex(wf.FigureError, "unknown text role"):
            run_layout(common("custom", script="x.py"), draw=draw)


class BuildAndCheckTests(unittest.TestCase):
    def setUp(self):
        self.spec = make_spec()
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        self.wanted = (self.spec.data["canvas"]["width"], self.spec.data["canvas"]["height"])

    def toml(self, name, text):
        (self.folder / f"{name}.toml").write_text(text, encoding="utf-8")

    def built(self, name="one", text=None):
        self.toml(name, text or BARS_TOML)
        wf.build(self.spec, name, self.folder, None, fake_measure(), render_png=False)
        (self.folder / f"{name}.png").write_bytes(make_png(*self.wanted))

    def failures(self, name="one"):
        return [f.message for f in wf.check_figure(self.spec, self.folder, name)
                if f.level == "fail"]

    def test_a_built_figure_passes_every_check(self):
        self.built()
        self.assertEqual(self.failures(), [])
        results, extra = wf.check_folder(self.spec, self.folder)
        self.assertEqual(extra, [])
        self.assertEqual(list(results), ["one"])

    def test_build_writes_nothing_when_a_check_fails(self):
        self.toml("bad", BARS_TOML.replace("Invented.", "").replace('numbers = ""\n', ""))
        with self.assertRaisesRegex(wf.FigureError, "numbers is required"):
            wf.build(self.spec, "bad", self.folder, None, fake_measure(), render_png=False)
        self.assertFalse((self.folder / "bad.svg").exists())
        self.assertFalse((self.folder / wf.ALT_NAME).exists())

    def test_build_refuses_text_that_does_not_fit(self):
        self.toml("long", BARS_TOML.replace("A title", "w" * 200))
        with self.assertRaisesRegex(wf.FigureError, "frame width"):
            wf.build(self.spec, "long", self.folder, None, fake_measure(), render_png=False)
        self.assertFalse((self.folder / "long.svg").exists())

    def test_build_verifies_the_font_file(self):
        data = spec_data()
        data["font"]["file"] = "missing/font.ttf"
        data["font"]["sha256"] = "0" * 64
        spec = make_spec(data, self.folder)
        self.toml("one", BARS_TOML)
        with self.assertRaisesRegex(wf.FigureError, "font file is missing"):
            wf.build(spec, "one", self.folder, None, fake_measure(), render_png=False)

    def test_font_loading_uses_the_shared_report_checks(self):
        spec = make_spec()
        problems = wr.font_report_problems(spec, {"error": "boom", "faces": [], "probe": None})
        self.assertEqual(problems, ["font loading raised an error: boom"])

    def test_stale_input(self):
        self.built()
        with (self.folder / "one.toml").open("a", encoding="utf-8") as file:
            file.write("# edited\n")
        self.assertIn("figure is stale: one.toml changed", self.failures())

    def test_stale_spec(self):
        self.built()
        other = wf.FigureSpec(spec_data(), "a-different-sha", Path("/nowhere"))
        found = [f.message for f in wf.check_figure(other, self.folder, "one")]
        self.assertIn("figure is stale: template spec changed", found)

    def test_stale_custom_script(self):
        (self.folder / "fig.py").write_text(CUSTOM_OK, encoding="utf-8")
        self.built("c", CUSTOM_TOML)
        (self.folder / "fig.py").write_text(CUSTOM_OK + "\n# changed\n", encoding="utf-8")
        self.assertIn("figure is stale: fig.py changed", self.failures("c"))

    def test_missing_files_and_bad_png(self):
        self.built()
        (self.folder / "one.png").unlink()
        self.assertIn("one.png is missing; run figure build", self.failures())
        (self.folder / "one.png").write_bytes(make_png(100, 100))
        self.assertIn(f"one.png is 100x100, not {self.wanted[0]}x{self.wanted[1]}",
                      self.failures())
        (self.folder / "one.png").write_bytes(b"not a png")
        self.assertIn("one.png is not a PNG file", self.failures())
        (self.folder / "one.svg").unlink()
        self.assertIn("one.svg is missing; run figure build", self.failures())

    def test_a_hand_edited_svg_is_caught(self):
        self.built()
        svg = (self.folder / "one.svg").read_text(encoding="utf-8")
        (self.folder / "one.svg").write_text(
            svg.replace("</svg>", '<rect width="1" height="1" rx="2"/></svg>'), encoding="utf-8")
        self.assertIn("forbidden SVG feature: rx attribute", self.failures())

    def test_an_svg_without_a_record_fails(self):
        self.built()
        (self.folder / "one.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg"/>',
                                             encoding="utf-8")
        self.assertIn("one.svg has no build record; run figure build", self.failures())

    def test_alt_text_checks_run_on_the_input(self):
        self.built()
        text = BARS_TOML.replace("beta 10", "beta ten")
        self.toml("one", text)
        self.assertTrue(any("does not mention the plotted value 10" in m for m in self.failures()))
        self.toml("one", BARS_TOML.replace('alt = "Bars: alpha 30, beta 10."', 'alt = ""'))
        self.assertTrue(any("alt is required" in m for m in self.failures()))

    def test_alt_text_document_follows_the_convention(self):
        self.toml("b-fig", BARS_TOML.replace('title = "A title"',
                                              'title = "A title"\nplace = "After the intro."\n'
                                              'caption = "A caption."'))
        self.toml("a-fig", FLOW_TOML)
        text = wf.alt_text_document(self.folder)
        self.assertLess(text.index("## a-fig.png (a-fig.svg)"), text.index("## b-fig.png"))
        self.assertIn("Place: After the intro.", text)
        self.assertIn('Alt text: "Bars: alpha 30, beta 10."', text)
        self.assertIn("Caption: A caption.", text)
        self.assertIn("Numbers: Invented.", text)
        self.assertIn("Numbers: none", text)
        self.assertIn("Place: not set", text)
        self.assertIn("Source: Source: invented. Source: more.", text)

    def test_alt_text_file_is_generated_and_checked_for_freshness(self):
        self.built()
        self.assertEqual((self.folder / wf.ALT_NAME).read_text(encoding="utf-8"),
                         wf.alt_text_document(self.folder))
        (self.folder / wf.ALT_NAME).write_text("old", encoding="utf-8")
        _, extra = wf.check_folder(self.spec, self.folder)
        self.assertEqual([f.message for f in extra], [f"{wf.ALT_NAME} is out of date; run figure build"])
        (self.folder / wf.ALT_NAME).unlink()
        _, extra = wf.check_folder(self.spec, self.folder)
        self.assertEqual([f.message for f in extra], [f"{wf.ALT_NAME} is missing; run figure build"])

    def test_every_type_builds_and_passes_check(self):
        for name, text in (("bars", BARS_TOML), ("flow", FLOW_TOML), ("table", TABLE_TOML),
                           ("stats", STATS_TOML), ("custom", CUSTOM_TOML)):
            with self.subTest(type=name):
                if name == "custom":
                    (self.folder / "fig.py").write_text(CUSTOM_OK, encoding="utf-8")
                self.built(name, text)
                self.assertEqual(self.failures(name), [])


BARS_TOML = '''type = "bars"
title = "A title"
deck = "A deck line."
alt = "Bars: alpha 30, beta 10."
numbers = "Invented."
[[bar]]
label = "Alpha"
value = 30
[[bar]]
label = "Beta"
value = 10
'''
FLOW_TOML = '''type = "flow"
title = "A flow"
deck = "Deck."
alt = "A to B."
sources = ["Source: invented.", "Source: more."]
[[box]]
id = "a"
row = 0
col = 0
label = "A"
[[box]]
id = "b"
row = 0
col = 1
label = "B"
[[edge]]
from = "a"
to = "b"
style = "flow"
'''
TABLE_TOML = '''type = "table"
title = "A table"
deck = "Deck."
alt = "A table."
columns = ["One", "Two"]
arrow_after = 0
[[row]]
cells = ["a", "b"]
'''
STATS_TOML = '''type = "stats"
title = "Stats"
deck = "Deck."
alt = "Stat 40%."
numbers = "Invented."
[[column]]
header = "Now"
[[column.item]]
value = "40%"
label = "late"
hero = true
'''
CUSTOM_TOML = '''type = "custom"
title = "Custom"
deck = "Deck."
alt = "Custom."
script = "fig.py"
'''


class ExampleTests(unittest.TestCase):
    """Every public example input is valid and lays out cleanly on the example spec."""

    def test_examples_exist_for_every_type(self):
        kinds = {tomllib.loads(p.read_text(encoding="utf-8"))["type"]
                 for p in EXAMPLES.glob("*.toml")}
        self.assertEqual(kinds, set(wf.TYPES))

    def test_examples_lay_out_without_problems(self):
        spec = wf.load_spec(EXAMPLE_SPEC, "/nowhere")
        for path in sorted(EXAMPLES.glob("*.toml")):
            with self.subTest(example=path.name):
                data = wf.load_input(path, spec.data["limits"])
                draw = wf.load_script(EXAMPLES / data["script"]).draw \
                    if data["type"] == "custom" else None
                ctx = wf.layout_figure(spec, data, fake_measure(0.5), draw)
                self.assertEqual(ctx.problems, [])
                svg = wf.render_svg(spec, ctx, data, path.stem, "x")
                self.assertEqual(wf.svg_findings(spec, svg), [])


class InitTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.private = Path(temporary.name) / "private"
        self.folder = "2026-02-03-demo-article"
        self.directory = self.private / "articles" / self.folder
        self.directory.mkdir(parents=True)
        (self.directory / "article.md").write_text('---\ntitle: "Demo"\nstatus: draft\n---\n\nBody\n',
                                                   encoding="utf-8")
        (self.private / "guides").mkdir()
        shutil.copy(EXAMPLE_SPEC, self.private / "guides" / "figure-template.toml")
        self.env = {**os.environ, "WRITING_PRIVATE": str(self.private)}

    def run_cli(self, *args):
        return subprocess.run([str(SCRIPT), "figure", *args], env=self.env, capture_output=True,
                              text=True)

    def test_init_writes_a_starter_for_every_type_that_build_refuses(self):
        for kind in wf.TYPES:
            with self.subTest(type=kind):
                result = self.run_cli("init", self.folder, f"fig-{kind}", "--type", kind)
                self.assertEqual(result.returncode, 0, result.stderr)
                path = self.directory / "figures" / f"fig-{kind}.toml"
                data = tomllib.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(data["type"], kind)
                self.assertTrue(wf.input_problems(data, spec_data()["limits"]))

    def test_init_refuses_to_overwrite(self):
        self.assertEqual(self.run_cli("init", self.folder, "one", "--type", "bars").returncode, 0)
        path = self.directory / "figures" / "one.toml"
        before = path.read_bytes()
        result = self.run_cli("init", self.folder, "one", "--type", "flow")
        self.assertEqual(result.returncode, 2)
        self.assertIn("already exists", result.stderr)
        self.assertEqual(path.read_bytes(), before)

    def test_init_rejects_a_bad_name_type_and_article(self):
        self.assertNotEqual(self.run_cli("init", self.folder, "Bad Name", "--type", "bars").returncode, 0)
        self.assertNotEqual(self.run_cli("init", self.folder, "one", "--type", "pie").returncode, 0)
        result = self.run_cli("init", "2026-09-09-missing", "one", "--type", "bars")
        self.assertEqual(result.returncode, 2)

    def test_check_all_lists_articles_without_figures_as_information(self):
        result = self.run_cli("check", "--all")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("no figures", result.stdout)
        self.assertIn(self.folder, result.stdout)

    def test_check_for_one_article_without_figures_is_an_error(self):
        result = self.run_cli("check", self.folder)
        self.assertEqual(result.returncode, 2)
        self.assertIn("figure init", result.stderr)

    def test_check_fails_for_an_unbuilt_figure_and_for_bad_arguments(self):
        self.assertEqual(self.run_cli("init", self.folder, "one", "--type", "bars").returncode, 0)
        result = self.run_cli("check", "--all")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("FAIL", result.stdout)
        self.assertEqual(self.run_cli("check").returncode, 2)
        self.assertEqual(self.run_cli("check", self.folder, "--all").returncode, 2)
        self.assertEqual(self.run_cli("build", self.folder).returncode, 2)

    def test_check_passes_for_a_built_figure(self):
        spec = wf.load_spec(self.private / "guides" / "figure-template.toml", self.private)
        figures = self.directory / "figures"
        figures.mkdir()
        (figures / "one.toml").write_text(BARS_TOML, encoding="utf-8")
        wf.build(spec, "one", figures, None, fake_measure(), render_png=False)
        (figures / "one.png").write_bytes(make_png(1200, 675))
        result = self.run_cli("check", "--all")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("ok", result.stdout)
        (figures / "one.toml").write_text(BARS_TOML + "\n# edit\n", encoding="utf-8")
        result = self.run_cli("check", self.folder)
        self.assertEqual(result.returncode, 1)
        self.assertIn("stale", result.stdout)


@unittest.skipUnless(wr.chromium_available(), "Chromium is not available")
class IntegrationTests(unittest.TestCase):
    """Render each example type in Chromium with the example spec (a system font)."""

    def build_example(self, filename):
        spec = wf.load_spec(EXAMPLE_SPEC, "/nowhere")
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            for item in EXAMPLES.iterdir():
                shutil.copy(item, folder / item.name)
            name = Path(filename).stem
            data = wf.build(spec, name, folder, wr.find_chromium())
            self.assertEqual(wr.png_size(folder / f"{name}.png"), (1200, 675))
            self.assertEqual(wf.check_figure(spec, folder, name), [])
            self.assertIn(data["title"], (folder / f"{name}.svg").read_text(encoding="utf-8"))
            self.assertTrue((folder / wf.ALT_NAME).is_file())

    def test_bars(self):
        self.build_example("example-bars.toml")

    def test_flow(self):
        self.build_example("example-flow.toml")

    def test_table(self):
        self.build_example("example-table.toml")

    def test_stats(self):
        self.build_example("example-stats.toml")

    def test_custom(self):
        self.build_example("example-custom.toml")

    def test_a_missing_font_file_fails_before_rendering(self):
        data = spec_data()
        data["font"]["file"] = "missing.ttf"
        data["font"]["sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            shutil.copy(EXAMPLES / "example-bars.toml", folder / "example-bars.toml")
            spec = make_spec(data, folder)
            with self.assertRaisesRegex(wf.FigureError, "font file is missing"):
                wf.build(spec, "example-bars", folder, wr.find_chromium())


if __name__ == "__main__":
    unittest.main()
