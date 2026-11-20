"""Test the article header generator without Chromium or any real font."""

import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import tomllib
import unittest
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parent))
import writing_header as wh  # noqa: E402


SCRIPT = Path(__file__).resolve().with_name("writing")
EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "header-template.example.toml"

SPEC_TOML = """
[canvas]
width = 400
height = 300
background = "#111111"
[font]
family = "Test Sans"
weight_min = 100
weight_max = 900
[[rule]]
y = 0
height = 2
fill = "#2255AA"
opacity = 0.5
[title]
x = 20
last_baseline = 200
max_width = 300
min_size = 20
advance_prev = 0.3
advance_next = 0.8
[title.standard]
size = 40
weight = 700
letter_spacing = -1
fill = "#EEEEEE"
[title.emphasis]
size = 60
weight = 700
letter_spacing = -2
fill = "#CCAA44"
[separator]
x = 20
y = 220
width = 100
height = 1
fill = "#333333"
[deck]
x = 20
size = 12
weight = 400
baselines = [240, 258]
fills = ["#999999", "#777777"]
[watermark]
size = 150
weight = 800
letter_spacing = -4
fill = "#222222"
x = 380
baseline = 260
anchor = "end"
"""


def make_png(width, height):
    def chunk(kind, data):
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))
    row = b"\x00" + b"\x00\x00\x00" * width
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(row * height)) + chunk(b"IEND", b""))


def fixed_widths(per_pixel=10.0):
    """A measure function: width is proportional to size and text length."""
    def measure(jobs):
        return [len(j["text"]) * j["size"] * per_pixel / 40 for j in jobs]
    return measure


def spec_data():
    return tomllib.loads(SPEC_TOML)


def make_input(**overrides):
    data = {"lines": ["One", "Two"], "gold": 2, "deck": ["a", "b"], "number": "01",
            "alt": "An alt text."}
    data.update(overrides)
    return wh.HeaderInput(data["lines"], data["gold"], data["deck"], data.get("number", ""),
                          data["alt"])


class LayoutTests(unittest.TestCase):
    def setUp(self):
        self.spec = spec_data()

    def run_layout(self, lines, gold, per_pixel=1.0):
        return wh.layout(self.spec, make_input(lines=lines, gold=gold), fixed_widths(per_pixel))

    def test_last_baseline_is_anchored_for_two_three_and_four_lines(self):
        for count in (2, 3, 4):
            with self.subTest(lines=count):
                lay = self.run_layout(["ab"] * count, count)
                self.assertEqual(lay.baselines[-1], 200)
                self.assertEqual(len(lay.baselines), count)

    def test_baseline_advance_formula(self):
        lay = self.run_layout(["ab", "cd"], 2)
        # standard 40 then emphasis 60: round(0.3 * 40 + 0.8 * 60) = 60
        self.assertEqual(lay.sizes, [40, 60])
        self.assertEqual(lay.baselines, [140, 200])
        lay = self.run_layout(["ab", "cd"], 1)
        # emphasis 60 then standard 40: round(0.3 * 60 + 0.8 * 40) = 50
        self.assertEqual(lay.baselines, [150, 200])

    def test_equal_sizes_use_both_coefficients(self):
        self.assertEqual(wh.advance(self.spec, 40, 40), 44)

    def test_three_lines_accumulate_upward(self):
        lay = self.run_layout(["a", "b", "c"], 2)
        self.assertEqual(lay.sizes, [40, 60, 40])
        self.assertEqual(lay.baselines[2], 200)
        self.assertEqual(lay.baselines[1], 200 - round(0.3 * 60 + 0.8 * 40))
        self.assertEqual(lay.baselines[0], lay.baselines[1] - round(0.3 * 40 + 0.8 * 60))

    def test_no_scaling_when_lines_fit(self):
        lay = self.run_layout(["ab", "cd"], 2)
        self.assertEqual(lay.scale, 1.0)
        self.assertEqual(lay.problems, [])

    def test_whole_block_scales_uniformly(self):
        # width = len * size / 40: the emphasis line "abcdefgh" is 8 * 60 / 40 = 12 (per_pixel 1)
        # so use per_pixel 40 to make it 8 * 60 = 480 wide, over the 300 maximum.
        lay = self.run_layout(["abcd", "abcdefgh"], 2, per_pixel=40.0)
        self.assertLess(lay.scale, 1.0)
        self.assertLessEqual(max(lay.widths), 300 + wh.TOLERANCE)
        # The size ratio of the block is preserved up to rounding.
        self.assertAlmostEqual(lay.sizes[1] / lay.sizes[0], 1.5, delta=0.1)
        self.assertEqual(lay.problems, [])

    def test_minimum_size_is_enforced(self):
        lay = self.run_layout(["abcd", "abcdefgh"], 2, per_pixel=400.0)
        self.assertTrue(any("below" in p for p in lay.problems), lay.problems)

    def test_rounding_over_limit_is_tightened(self):
        # Width does not scale exactly with size (fixed tracking), so one pass can still overflow.
        def measure(jobs):
            return [len(j["text"]) * j["size"] * 0.5 + 40 for j in jobs]
        lay = wh.layout(self.spec, make_input(lines=["abcdefghij", "abcdefghij"], gold=2), measure)
        self.assertLessEqual(max(lay.widths), 300 + wh.TOLERANCE)
        self.assertEqual(lay.problems, [])


class SpecTests(unittest.TestCase):
    def test_fixture_and_example_are_valid(self):
        self.assertEqual(wh.validate_spec(spec_data()), [])
        self.assertEqual(wh.validate_spec(tomllib.loads(EXAMPLE.read_text(encoding="utf-8"))), [])

    def test_missing_and_wrong_type_values_are_reported(self):
        data = spec_data()
        del data["title"]["max_width"]
        data["canvas"]["width"] = "wide"
        problems = wh.validate_spec(data)
        self.assertIn("spec is missing title.max_width", problems)
        self.assertIn("spec canvas.width has the wrong type", problems)

    def test_font_file_needs_a_hash_and_a_relative_path(self):
        data = spec_data()
        data["font"]["file"] = "/abs/font.ttf"
        problems = wh.validate_spec(data)
        self.assertTrue(any("relative" in p for p in problems))
        self.assertTrue(any("sha256" in p for p in problems))

    def test_font_hash_is_verified(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "f.ttf").write_bytes(b"not really a font")
            data = spec_data()
            data["font"]["file"] = "f.ttf"
            data["font"]["sha256"] = wh.sha256_bytes(b"not really a font")
            spec = wh.Spec(data, "x", root)
            spec.verify_font_file()
            data["font"]["sha256"] = "0" * 64
            with self.assertRaisesRegex(wh.HeaderError, "does not match"):
                spec.verify_font_file()
            (root / "f.ttf").unlink()
            with self.assertRaisesRegex(wh.HeaderError, "missing"):
                spec.verify_font_file()


class ValidationTests(unittest.TestCase):
    GOOD = {"lines": ["A", "B"], "gold": 2, "deck": ["x", "y"], "number": "07", "alt": "Alt"}

    def problems(self, **changes):
        data = dict(self.GOOD)
        data.update(changes)
        for key in [k for k, v in data.items() if v is None]:
            del data[key]
        return wh.input_problems(data)

    def test_good_input_passes(self):
        self.assertEqual(self.problems(), [])
        self.assertEqual(self.problems(number=None), [])

    def test_line_count_limits(self):
        self.assertTrue(self.problems(lines=["A"], gold=1))
        self.assertTrue(self.problems(lines=["A"] * 5, gold=1))
        for count in (2, 3, 4):
            self.assertEqual(self.problems(lines=["A"] * count), [])

    def test_gold_must_be_one_valid_line(self):
        self.assertTrue(any("not set" in p for p in self.problems(gold=None)))
        self.assertTrue(any("single" in p for p in self.problems(gold=[1, 2])))
        self.assertTrue(self.problems(gold=3))
        self.assertTrue(self.problems(gold=0))
        self.assertTrue(self.problems(gold=True))

    def test_deck_must_be_exactly_two_lines(self):
        self.assertTrue(self.problems(deck=["only"]))
        self.assertTrue(self.problems(deck=["a", "b", "c"]))
        self.assertTrue(self.problems(deck=["a", ""]))

    def test_number_is_digits_only(self):
        for bad in ("1a", "", "-1", "one", 1):
            with self.subTest(number=bad):
                self.assertTrue(self.problems(number=bad))

    def test_alt_is_required(self):
        self.assertTrue(self.problems(alt=""))
        self.assertTrue(self.problems(alt="   "))
        self.assertTrue(self.problems(alt=None))

    def test_unknown_keys_are_rejected(self):
        self.assertTrue(self.problems(colour="red"))

    def test_parse_input_reports_toml_errors(self):
        with self.assertRaises(wh.HeaderError):
            wh.parse_input(b"lines = [")


class PngTests(unittest.TestCase):
    def test_reads_dimensions(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "a.png"
            path.write_bytes(make_png(1200, 675))
            self.assertEqual(wh.png_size(path), (1200, 675))

    def test_rejects_non_png_and_missing(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "a.png"
            path.write_bytes(b"GIF89a" + b"\0" * 40)
            self.assertIsNone(wh.png_size(path))
            self.assertIsNone(wh.png_size(Path(folder) / "missing.png"))
            path.write_bytes(b"\x89PNG")
            self.assertIsNone(wh.png_size(path))


class WorkspaceTestCase(unittest.TestCase):
    """A private-root-shaped temporary directory with articles and a spec."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / "articles").mkdir()
        self.spec = wh.Spec(spec_data(), wh.sha256_bytes(SPEC_TOML.encode()), self.root)

    def article(self, folder, title="A Title", series=None, header=None, number="01"):
        directory = self.root / "articles" / folder
        directory.mkdir()
        lines = ["---", f'title: "{title}"']
        if series:
            lines.append(f'series: "{series}"')
        lines += ["---", "", "Body", ""]
        (directory / "article.md").write_text("\n".join(lines), encoding="utf-8")
        if header is not False:
            data = {"lines": ["One", "Two"], "gold": 2, "deck": ["a", "b"], "alt": "Alt"}
            if number:
                data["number"] = number
            data.update(header or {})
            body = "".join(f"{key} = {json.dumps(value, ensure_ascii=False)}\n"
                           for key, value in data.items())
            (directory / "header.toml").write_text(body, encoding="utf-8")
        return directory

    def build(self, directory, title="A Title", siblings=()):
        return wh.build(self.spec, directory.name, directory, title, list(siblings), None,
                        measure=fixed_widths(), render=False)

    def finish(self, directory, size=(400, 300)):
        (directory / "header.png").write_bytes(make_png(*size))

    def check(self, directory, title="A Title", siblings=()):
        return wh.check_files(self.spec, directory.name, directory, title, list(siblings))

    def failures(self, findings):
        return [f.message for f in findings if f.level == "fail"]


class BuildAndStalenessTests(WorkspaceTestCase):
    def test_build_writes_svg_with_record_and_comment(self):
        directory = self.article("2026-01-01-a")
        result = self.build(directory)
        self.assertEqual(result.sizes, [40, 60])
        svg = (directory / "header.svg").read_text(encoding="utf-8")
        self.assertTrue(svg.startswith("<!--"))
        self.assertIn("header build 2026-01-01-a", svg)
        self.assertIn('font-family="Test Sans"', svg)
        self.assertNotIn("@font-face", svg)
        record = wh.read_build_record(directory / "header.svg")
        self.assertEqual(record["title"], "A Title")
        self.assertEqual(record["spec_sha256"], self.spec.sha256)

    def test_svg_has_one_gold_line_and_bottom_baseline(self):
        directory = self.article("2026-01-01-a")
        self.build(directory)
        svg = (directory / "header.svg").read_text(encoding="utf-8")
        self.assertEqual(svg.count('fill="#CCAA44"'), 1)
        self.assertIn('y="200"', svg)
        self.assertIn(">01</text>", svg)

    def test_no_number_means_no_watermark(self):
        directory = self.article("2026-01-01-a", number="")
        self.build(directory)
        svg = (directory / "header.svg").read_text(encoding="utf-8")
        self.assertNotIn('font-size="150"', svg)

    def test_special_characters_are_escaped(self):
        directory = self.article("2026-01-01-a", title='Fish & "Chips" <now>',
                                 header={"lines": ["A & B", "<C>"]})
        self.build(directory, title='Fish & "Chips" <now>')
        record = wh.read_build_record(directory / "header.svg")
        self.assertEqual(record["title"], 'Fish & "Chips" <now>')
        self.finish(directory)
        self.assertEqual(self.failures(self.check(directory, 'Fish & "Chips" <now>')), [])

    def test_build_refuses_without_gold(self):
        directory = self.article("2026-01-01-a")
        text = (directory / "header.toml").read_text().replace("gold = 2\n", "")
        (directory / "header.toml").write_text(text)
        with self.assertRaisesRegex(wh.HeaderError, "gold is not set"):
            self.build(directory)
        self.assertFalse((directory / "header.svg").exists())

    def test_build_refuses_when_lines_cannot_fit(self):
        directory = self.article("2026-01-01-a", header={"lines": ["x" * 40, "y" * 40]})
        with self.assertRaisesRegex(wh.HeaderError, "below the"):
            wh.build(self.spec, directory.name, directory, "A Title", [], None,
                     measure=fixed_widths(500.0), render=False)
        self.assertFalse((directory / "header.svg").exists())

    def test_fresh_header_passes(self):
        directory = self.article("2026-01-01-a")
        self.build(directory)
        self.finish(directory)
        self.assertEqual(self.failures(self.check(directory)), [])

    def test_title_change_makes_header_stale(self):
        directory = self.article("2026-01-01-a")
        self.build(directory)
        self.finish(directory)
        self.assertEqual(self.failures(self.check(directory, title="A New Title")),
                         ["header is stale: title changed"])

    def test_spec_change_makes_header_stale(self):
        directory = self.article("2026-01-01-a")
        self.build(directory)
        self.finish(directory)
        self.spec.sha256 = "f" * 64
        self.assertEqual(self.failures(self.check(directory)),
                         ["header is stale: template spec changed"])

    def test_input_change_makes_header_stale(self):
        directory = self.article("2026-01-01-a")
        self.build(directory)
        self.finish(directory)
        with (directory / "header.toml").open("a") as file:
            file.write("# edited\n")
        self.assertEqual(self.failures(self.check(directory)),
                         ["header is stale: header.toml changed"])

    def test_missing_outputs_and_wrong_png_size(self):
        directory = self.article("2026-01-01-a")
        self.assertTrue(any("header.svg is missing" in m
                            for m in self.failures(self.check(directory))))
        self.build(directory)
        self.assertTrue(any("header.png is missing" in m
                            for m in self.failures(self.check(directory))))
        self.finish(directory, size=(1200, 675))
        self.assertTrue(any("1200x675, not 400x300" in m
                            for m in self.failures(self.check(directory))))

    def test_recorded_overflow_fails_the_check(self):
        directory = self.article("2026-01-01-a")
        self.build(directory)
        self.finish(directory)
        svg = directory / "header.svg"
        record = wh.read_build_record(svg)
        text = svg.read_text(encoding="utf-8").replace(
            f'"max_width": {record["max_width"]}', '"max_width": 999', 1)
        svg.write_text(text, encoding="utf-8")
        self.assertTrue(any("over the 300px" in m for m in self.failures(self.check(directory))))

    def test_invalid_input_fails_the_check(self):
        directory = self.article("2026-01-01-a", header={"alt": ""})
        self.assertTrue(any("alt text is required" in m
                            for m in self.failures(self.check(directory))))

    def test_deck_part_n_of_m_warns_without_failing(self):
        directory = self.article("2026-01-01-a", header={"deck": ["Series · Part 2 of 5", "b"]})
        self.build(directory)
        self.finish(directory)
        findings = self.check(directory)
        self.assertEqual(self.failures(findings), [])
        warnings = [f.message for f in findings if f.level == "warn"]
        self.assertEqual(len(warnings), 1)
        self.assertIn('house form is "Part N"', warnings[0])


class DuplicateNumberTests(WorkspaceTestCase):
    def test_same_series_same_number_fails(self):
        first = self.article("2026-01-01-a", series="s", number="02")
        self.article("2026-01-02-b", series="s", number="2")
        siblings = [("2026-01-01-a", "s"), ("2026-01-02-b", "s")]
        findings = self.check(first, siblings=siblings)
        self.assertTrue(any("already used by 2026-01-02-b" in m for m in self.failures(findings)))

    def test_different_series_or_number_passes(self):
        first = self.article("2026-01-01-a", series="s", number="02")
        self.article("2026-01-02-b", series="other", number="02")
        self.article("2026-01-03-c", series="s", number="03")
        self.article("2026-01-04-d", series="s", number="")
        siblings = [("2026-01-01-a", "s"), ("2026-01-02-b", "other"), ("2026-01-03-c", "s"),
                    ("2026-01-04-d", "s")]
        findings = self.check(first, siblings=siblings)
        self.assertFalse(any("already used" in m for m in self.failures(findings)))

    def test_build_refuses_a_duplicate(self):
        first = self.article("2026-01-01-a", series="s", number="02")
        self.article("2026-01-02-b", series="s", number="02")
        siblings = [("2026-01-01-a", "s"), ("2026-01-02-b", "s")]
        with self.assertRaisesRegex(wh.HeaderError, "already used"):
            self.build(first, siblings=siblings)


class FontReportTests(unittest.TestCase):
    def setUp(self):
        data = spec_data()
        data["font"]["file"] = "f.ttf"
        data["font"]["sha256"] = "0" * 64
        self.spec = wh.Spec(data, "x", Path("/nowhere"))
        self.good = {"faces": [{"family": "Test Sans", "weight": "100 900", "status": "loaded"}],
                     "probe": {"font": 400.0, "monospace": 500.0, "serif": 450.0}}

    def test_loaded_font_passes(self):
        self.assertEqual(wh.font_report_problems(self.spec, self.good), [])

    def test_unloaded_face_fails(self):
        self.good["faces"][0]["status"] = "error"
        self.assertTrue(wh.font_report_problems(self.spec, self.good))

    def test_undeclared_face_fails(self):
        self.good["faces"] = []
        self.assertTrue(wh.font_report_problems(self.spec, self.good))

    def test_probe_equal_to_fallback_fails(self):
        self.good["probe"]["font"] = 500.0
        self.assertTrue(any("fallback" in p for p in wh.font_report_problems(self.spec, self.good)))

    def test_generic_family_skips_probe_and_face_checks(self):
        spec = wh.Spec(spec_data(), "x", Path("/nowhere"))
        spec.data["font"]["family"] = "sans-serif"
        self.assertEqual(wh.font_report_problems(spec, {"faces": [], "probe": None}), [])

    def test_script_error_fails(self):
        self.good["error"] = "boom"
        self.assertTrue(wh.font_report_problems(self.spec, self.good))


class ChromiumDiscoveryTests(unittest.TestCase):
    def test_environment_variable_wins(self):
        with tempfile.NamedTemporaryFile() as binary:
            found = wh.find_chromium({"WRITING_CHROMIUM": binary.name}, which=lambda name: "/x")
            self.assertEqual(found, binary.name)

    def test_first_name_on_the_path(self):
        available = {"google-chrome": "/bin/google-chrome", "google-chrome-stable": "/bin/stable"}
        self.assertEqual(wh.find_chromium({}, which=available.get), "/bin/google-chrome")

    def test_clear_error_when_missing(self):
        with self.assertRaisesRegex(wh.HeaderError, "Chromium not found"):
            wh.find_chromium({}, which=lambda name: None)

    def test_bad_environment_path_is_an_error(self):
        with self.assertRaisesRegex(wh.HeaderError, "WRITING_CHROMIUM"):
            wh.find_chromium({"WRITING_CHROMIUM": "/no/such/file"}, which=lambda name: "/x")


class InitTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        workspace = Path(temporary.name)
        self.private = workspace / "private"
        self.folder = "2026-02-03-fix-one-constraint"
        directory = self.private / "articles" / self.folder
        directory.mkdir(parents=True)
        (directory / "article.md").write_text(
            '---\ntitle: "Fix One Constraint, Find the Next"\nstatus: draft\n---\n\nBody\n',
            encoding="utf-8")
        self.directory = directory
        self.env = {**os.environ, "WRITING_PRIVATE": str(self.private)}

    def run_cli(self, *args):
        return subprocess.run([str(SCRIPT), "header", *args], env=self.env,
                              capture_output=True, text=True)

    def test_init_writes_a_starter_that_build_refuses(self):
        result = self.run_cli("init", self.folder)
        self.assertEqual(result.returncode, 0, result.stderr)
        data = tomllib.loads((self.directory / "header.toml").read_text(encoding="utf-8"))
        self.assertEqual(data["lines"], ["Fix One Constraint,", "Find the Next"])
        self.assertNotIn("gold", data)
        problems = wh.input_problems(data)
        self.assertTrue(any("gold is not set" in p for p in problems))

    def test_init_refuses_to_overwrite(self):
        self.assertEqual(self.run_cli("init", self.folder).returncode, 0)
        before = (self.directory / "header.toml").read_bytes()
        result = self.run_cli("init", self.folder)
        self.assertEqual(result.returncode, 2)
        self.assertIn("already exists", result.stderr)
        self.assertEqual((self.directory / "header.toml").read_bytes(), before)

    def test_split_title(self):
        self.assertEqual(wh.split_title("Fix One Constraint, Find the Next"),
                         ["Fix One Constraint,", "Find the Next"])
        self.assertEqual(wh.split_title("Four words in title"), ["Four words", "in title"])
        self.assertEqual(wh.split_title("Single"), ["Single", ""])

    def test_check_all_lists_missing_headers_without_failing(self):
        guides = self.private / "guides"
        guides.mkdir()
        (guides / "header-template.toml").write_text(SPEC_TOML, encoding="utf-8")
        result = self.run_cli("check", "--all")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("no header", result.stdout)
        self.assertIn(self.folder, result.stdout)

    def test_check_fails_for_an_unbuilt_header(self):
        guides = self.private / "guides"
        guides.mkdir()
        (guides / "header-template.toml").write_text(SPEC_TOML, encoding="utf-8")
        self.assertEqual(self.run_cli("init", self.folder).returncode, 0)
        result = self.run_cli("check", "--all")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("FAIL", result.stdout)


@unittest.skipUnless(
    (lambda: (os.environ.get("WRITING_CHROMIUM") and Path(os.environ["WRITING_CHROMIUM"]).is_file())
     or any(shutil.which(name) for name in wh.BROWSERS))(),
    "Chromium is not available")
class IntegrationTests(unittest.TestCase):
    def test_renders_with_the_example_spec(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "articles" / "2026-01-01-demo").mkdir(parents=True)
            directory = root / "articles" / "2026-01-01-demo"
            (directory / "header.toml").write_text(
                'lines = ["A Plain Title,", "With Emphasis"]\ngold = 2\n'
                'deck = ["First deck line", "Second deck line"]\nnumber = "03"\n'
                'alt = "A plain test header."\n', encoding="utf-8")
            spec = wh.load_spec(EXAMPLE, root)
            result = wh.build(spec, directory.name, directory, "A Plain Title", [],
                              wh.find_chromium())
            self.assertEqual(wh.png_size(directory / "header.png"), (1200, 675))
            self.assertEqual(result.sizes, [68, 96])
            findings = wh.check_files(spec, directory.name, directory, "A Plain Title", [])
            self.assertEqual([f for f in findings if f.level == "fail"], [])


if __name__ == "__main__":
    unittest.main()
