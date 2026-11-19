"""Test repository discovery independently of the invoking directory."""

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


if __name__ == "__main__":
    unittest.main()
