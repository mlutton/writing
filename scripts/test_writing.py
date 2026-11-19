"""Test repository discovery independently of the invoking directory."""

from datetime import date
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().with_name("writing")


class WritingPathsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=SCRIPT.parent.parent)
        self.addCleanup(temporary.cleanup)
        self.workspace = Path(temporary.name)
        self.public = self.workspace / "public"
        self.private = self.workspace / "private"
        self.script = self.public / "scripts" / "writing"
        self.script.parent.mkdir(parents=True)
        self.private.mkdir()
        shutil.copy2(SCRIPT, self.script)
        self.env = os.environ.copy()
        self.env.pop("WRITING_PRIVATE", None)

    def configure_settings(self, location="../private"):
        settings = self.public / "settings.local.toml"
        settings.write_text(f"private_root = {json.dumps(location)}\n", encoding="utf-8")

    def run_paths(self, *args, script=None):
        return subprocess.run(
            [str(script or self.script), "paths", *args], cwd=self.workspace,
            env=self.env, capture_output=True, text=True,
        )

    def assert_paths(self, result, private_root, source):
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {
            "public_root": str(self.public),
            "private_root": str(private_root) if private_root is not None else None,
            "private_source": source,
        })

    def test_environment_wins(self):
        self.configure_settings("../different")
        self.env["WRITING_PRIVATE"] = str(self.private)
        self.assert_paths(self.run_paths("--require-private"), self.private, "env")

    def test_settings_when_environment_unset(self):
        self.configure_settings()
        self.assert_paths(self.run_paths("--require-private"), self.private, "settings")

    def test_unconfigured_paths_are_null(self):
        self.assert_paths(self.run_paths(), None, None)

    def test_require_private_rejects_missing_directory(self):
        for location in (None, str(self.workspace / "missing"), str(self.script)):
            with self.subTest(location=location):
                if location is not None:
                    self.env["WRITING_PRIVATE"] = location
                result = self.run_paths("--require-private")
                self.assertEqual(result.returncode, 3)
                self.assertEqual(result.stdout, "")
                self.assertEqual(len(result.stderr.splitlines()), 1)

    def test_symlink_resolves_to_public_root(self):
        self.configure_settings()
        linked_script = self.workspace / "linked-writing"
        linked_script.symlink_to(self.script)
        self.assert_paths(self.run_paths(script=linked_script), self.private, "settings")


class WritingCommandTests(unittest.TestCase):
    SUMMARY = (
        "This fictional article explains how clear labels help volunteers find shared materials "
        "and put them back where the next person will look."
    )

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=SCRIPT.parent.parent)
        self.addCleanup(temporary.cleanup)
        workspace = Path(temporary.name)
        self.public = workspace / "public"
        self.private = workspace / "private"
        self.script = self.public / "scripts" / "writing"
        self.script.parent.mkdir(parents=True)
        shutil.copy2(SCRIPT, self.script)
        shutil.copy2(SCRIPT.with_name("guard"), self.script.with_name("guard"))
        self.published = self.public / "published"
        self.published.mkdir()
        self.topics = self.private / "topics"
        self.topics.mkdir(parents=True)
        self.articles = self.private / "articles"
        self.articles.mkdir()
        settings = self.private / "settings"
        settings.mkdir()
        (settings / "guard-denylist.txt").touch()
        self.env = {**os.environ, "WRITING_PRIVATE": str(self.private)}
        subprocess.run(["git", "init", "-q"], cwd=self.public, env=self.env, check=True)

    def command(self, *args, code=0):
        result = subprocess.run([str(self.script), *args], cwd=self.public, env=self.env,
                                text=True, capture_output=True)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        return result

    def new_article(self, *options):
        self.command("article", "new", "--title", "Label the shelves", "--date", "2026-01-10",
                     *options)
        return self.articles / "2026-01-10-label-the-shelves"

    def record(self, folder, *options, code=0):
        return self.command("publish", folder.name, "--url", "https://example.org/shelves",
                            "--date", "2026-01-11", *options, code=code)

    def test_topic_add_writes_requested_fields_and_derives_slug(self):
        result = self.command("topic", "add", "--title", "A shelf: labels and bins",
                              "--lane", "workshop", "--origin", "clipped", "--why", "Find tools.",
                              "--evidence", 'A note with "quotes"', "--json")
        path = self.topics / "a-shelf-labels-and-bins.md"
        self.assertEqual(json.loads(result.stdout), [
            {"action": "created", "path": f"topics/{path.name}"},
        ])
        self.assertEqual(path.read_text(), (
            "---\nstatus: proposed\norigin: clipped\n"
            f"first_seen: {date.today().isoformat()}\nlane: \"workshop\"\n"
            'evidence:\n  - "A note with \\"quotes\\""\n---\n\n'
            "# A shelf: labels and bins\n\n## Why this might be worth writing about\n\nFind tools.\n"
        ))

    def test_topic_add_merges_only_new_evidence(self):
        path = self.topics / "shelves.md"
        before = (b'---\r\nstatus: queued\r\nevidence:\r\n  - "note one"\r\n'
                  b"custom: keep # annotation\r\n---\r\n\r\n# Original\r\nbody\r\n")
        path.write_bytes(before)
        result = self.command("topic", "add", "--title", "New title", "--slug", "shelves",
                              "--why", "New reason", "--evidence", "note one",
                              "--evidence", "note two", "--evidence", "note two")
        self.assertEqual(result.stdout, "updated topics/shelves.md\n")
        self.assertEqual(path.read_bytes(), before.replace(
            b'  - "note one"\r\n', b'  - "note one"\r\n  - "note two"\r\n',
        ))

    def test_topic_add_merges_into_empty_list(self):
        self.command("topic", "add", "--title", "Shelves")
        path = self.topics / "shelves.md"
        self.assertIn("origin: proposed\n", path.read_text())
        self.assertNotIn("lane:", path.read_text())
        self.command("topic", "add", "--title", "Shelves", "--evidence", "first note")
        self.assertIn('evidence:\n  - "first note"\n', path.read_text())

    def test_topic_list_is_sorted_and_can_filter(self):
        for title in ("Shelves", "Bins"):
            self.command("topic", "add", "--title", title)
        self.command("topic", "set-status", "shelves", "queued")
        self.assertEqual(self.command("topic", "list").stdout,
                         "bins\tproposed\tBins\nshelves\tqueued\tShelves\n")
        self.assertEqual(json.loads(self.command("topic", "list", "--status", "queued",
                                                "--json").stdout), [
            {"slug": "shelves", "status": "queued", "title": "Shelves"},
        ])

    def test_topic_set_status_preserves_other_bytes(self):
        path = self.topics / "shelves.md"
        before = b"---\r\nstatus: proposed\r\ncustom:\r\n  - x\r\n---\r\n\r\n# Shelves"
        path.write_bytes(before)
        self.command("topic", "set-status", "shelves", "researching")
        self.assertEqual(path.read_bytes(), before.replace(b"proposed", b"researching"))

    def test_topic_set_status_refuses_unknown_topic_or_status(self):
        self.command("topic", "set-status", "missing", "queued", code=2)
        self.command("topic", "set-status", "missing", "done", code=2)
        self.assertEqual(list(self.topics.iterdir()), [])

    def test_article_new_creates_files_and_advances_topic(self):
        self.command("topic", "add", "--title", "Shelves")
        folder = self.new_article("--topic", "shelves", "--series", "Workshop notes")
        self.assertEqual({path.name for path in folder.iterdir()},
                         {"article.md", "notes.md", "questions.md"})
        self.assertEqual((folder / "article.md").read_text(), (
            '---\ntitle: "Label the shelves"\nstatus: draft\ncreated: 2026-01-10\n'
            'series: "Workshop notes"\ntopic: shelves\n---\n\n# Label the shelves\n\n'
        ))
        self.assertEqual((folder / "questions.md").read_text(), "# Question rounds\n")
        notes = (folder / "notes.md").read_text()
        for heading in ("Sources", "Flagged for the author", "Open questions"):
            self.assertIn(f"## {heading}\n", notes)
        self.assertIn("status: drafting", (self.topics / "shelves.md").read_text())

    def test_article_new_refuses_existing_folder(self):
        folder = self.new_article()
        article = folder / "article.md"
        article.write_bytes(b"Existing text")
        result = self.command("article", "new", "--title", "Label the shelves", "--date",
                              "2026-01-10", code=2)
        self.assertIn("already exists", result.stderr)
        self.assertEqual(article.read_bytes(), b"Existing text")

    def test_article_new_refuses_missing_topic(self):
        result = self.command("article", "new", "--title", "Label the shelves", "--topic",
                              "missing", code=2)
        self.assertIn("topic does not exist", result.stderr)
        self.assertEqual(list(self.articles.iterdir()), [])

    def test_article_hash_uses_exact_bytes(self):
        folder = self.new_article()
        data = b"first\r\nlast\xff"
        (folder / "article.md").write_bytes(data)
        digest = hashlib.sha256(data).hexdigest()
        self.assertEqual(self.command("article", "hash", folder.name).stdout, digest + "\n")
        self.assertEqual(json.loads(self.command("article", "hash", folder.name,
                                                "--json").stdout), {"sha256": digest})

    def test_article_list_and_filter(self):
        folder = self.new_article()
        self.assertEqual(self.command("article", "list", "--status", "published").stdout, "")
        self.assertEqual(self.command("article", "list", "--status", "draft").stdout,
                         f"{folder.name}\tdraft\tLabel the shelves\n")

    def test_publish_preview_writes_nothing(self):
        self.command("topic", "add", "--title", "Shelves")
        folder = self.new_article("--topic", "shelves")
        article, topic = folder / "article.md", self.topics / "shelves.md"
        before = [article.read_bytes(), topic.read_bytes()]
        preview = json.loads(self.record(folder, "--summary", self.SUMMARY,
                                         "--json", code=4).stdout)
        self.assertEqual(len(preview), 3)
        self.assertIn(self.SUMMARY, preview[0]["content"])
        for entry in preview:
            self.assertIn("status: published", entry["content"])
        self.assertEqual([article.read_bytes(), topic.read_bytes()], before)
        self.assertEqual(list(self.published.iterdir()), [])

    def test_publish_summary_limits(self):
        folder = self.new_article()
        for count in (19, 121):
            with self.subTest(count=count):
                result = self.record(folder, "--summary", " ".join(["word"] * count),
                                     "--yes", code=2)
                self.assertIn("20 to 120 words", result.stderr)
        for count in (20, 120):
            with self.subTest(count=count):
                self.record(folder, "--summary", " ".join(["word"] * count), code=4)
        self.assertEqual(list(self.published.iterdir()), [])
        self.assertIn("status: draft", (folder / "article.md").read_text())

    def test_publish_refuses_existing_entry(self):
        folder = self.new_article()
        entry = self.published / f"{folder.name}.md"
        entry.write_bytes(b"Existing summary")
        result = self.record(folder, "--summary", self.SUMMARY, "--yes", code=2)
        self.assertIn("already exists", result.stderr)
        self.assertEqual(entry.read_bytes(), b"Existing summary")
        self.assertIn("status: draft", (folder / "article.md").read_text())

    def test_publish_guard_rejection_leaves_private_files_intact(self):
        self.command("topic", "add", "--title", "Shelves")
        folder = self.new_article("--topic", "shelves")
        article, topic = folder / "article.md", self.topics / "shelves.md"
        before = [article.read_bytes(), topic.read_bytes()]
        summary = self.SUMMARY + " Contact " + "reader" + "@sample.invalid"
        result = self.record(folder, "--summary", summary, "--yes", code=1)
        self.assertIn(": email: ", result.stderr)
        self.assertEqual([article.read_bytes(), topic.read_bytes()], before)
        self.assertEqual(list(self.published.iterdir()), [])

    def test_publish_success_preserves_article_body_and_updates_statuses(self):
        self.command("topic", "add", "--title", "Shelves")
        folder = self.new_article("--topic", "shelves", "--series", "Workshop notes")
        article = folder / "article.md"
        before = article.read_bytes().replace(b"---\n\n# ", b"custom: keep\n---\n\n# ")
        before += b"Private article prose.\r\n"
        article.write_bytes(before)
        summary = self.private / "summary.md"
        summary.write_text(self.SUMMARY + "\n", encoding="utf-8")
        files = json.loads(self.record(folder, "--summary-file", str(summary),
                                       "--yes", "--json").stdout)
        self.assertEqual([item["action"] for item in files], ["created", "updated", "updated"])
        entry = self.published / f"{folder.name}.md"
        self.assertEqual(entry.read_text(), (
            '---\ntitle: "Label the shelves"\nstatus: published\npublished_date: 2026-01-11\n'
            'url: "https://example.org/shelves"\nseries: "Workshop notes"\n---\n\n'
            + self.SUMMARY + "\n"
        ))
        self.assertEqual(article.read_bytes(), before.replace(
            b"status: draft", b"status: published",
        ).replace(
            b"custom: keep\n", b'custom: keep\npublished_date: 2026-01-11\n'
            b'url: "https://example.org/shelves"\n',
        ))
        self.assertIn("status: published", (self.topics / "shelves.md").read_text())
        subprocess.run([str(self.script.with_name("guard")), str(entry.relative_to(self.public))],
                       cwd=self.public, env=self.env, check=True, capture_output=True)

    def test_commands_require_a_private_root(self):
        self.env["WRITING_PRIVATE"] = str(self.private / "missing")
        for args in [
            ("topic", "add", "--title", "Shelves"), ("topic", "list"),
            ("topic", "set-status", "shelves", "queued"),
            ("article", "new", "--title", "Shelves"), ("article", "list"),
            ("article", "hash", "2026-01-10-shelves"),
            ("publish", "2026-01-10-shelves", "--url", "https://example.org/shelves",
             "--date", "2026-01-11", "--summary", self.SUMMARY),
        ]:
            with self.subTest(args=args):
                self.assertIn("configure an existing private repo",
                              self.command(*args, code=3).stderr)

    def test_invalid_slug_date_and_folder_are_rejected(self):
        self.command("topic", "add", "--title", "Shelves", "--slug", "../bad", code=2)
        self.command("article", "new", "--title", "Shelves", "--date", "2026-02-30", code=2)
        self.command("article", "hash", "../missing", code=2)


if __name__ == "__main__":
    unittest.main()
