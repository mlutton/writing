"""Exercise the guard in isolated repositories."""

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


GUARD = Path(__file__).resolve().with_name("guard")


class GuardTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=GUARD.parent.parent)
        self.addCleanup(temporary.cleanup)
        self.workspace = Path(temporary.name)
        self.repo = self.workspace / "public"
        self.repo.mkdir()
        self.env = os.environ.copy()
        self.env.pop("WRITING_PRIVATE", None)
        self.git("init", "-q")
        self.write("scripts/guard", GUARD.read_text(encoding="utf-8"))
        self.write("README.md", "# Sample repository\n")
        self.write(".gitignore", "settings.local.toml\n")

    def git(self, *args):
        subprocess.run(["git", *args], cwd=self.repo, env=self.env, check=True,
                       capture_output=True)

    def write(self, name, content):
        path = self.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding="utf-8")

    def run_guard(self, *args):
        return subprocess.run(
            [sys.executable, "scripts/guard", *args], cwd=self.repo, env=self.env,
            capture_output=True, text=True,
        )

    def assert_finding(self, result, path, rule, line=1):
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn(f"{path}:{line}: {rule}: ", result.stdout)

    def test_clean_tree(self):
        self.write("published/sample.md", "---\nstatus: published\n---\nSummary.\n")
        self.write("examples/image.bin", b"\0\xff")
        self.write("docs/example.md", "person" + "@example.com\nhttp://localhost:8080\n")
        result = self.run_guard("--all")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(result.stdout, "")
        self.assertIn("using built-in rules only", result.stderr)

    def test_home_paths(self):
        for value in ("/" + "home/sample/note", "/" + "Users/sample/note", "C:" + r"\Users\sample"):
            with self.subTest(value=value):
                self.write("README.md", value)
                self.assert_finding(self.run_guard("--all"), "README.md", "home-path")

    def test_private_ip_addresses(self):
        for value in ("10" + ".0.0.1", "172" + ".16.0.1", "172" + ".31.255.255",
                      "192" + ".168.0.1"):
            with self.subTest(value=value):
                self.write("README.md", f"http://{value}:8080")
                self.assert_finding(self.run_guard("--all"), "README.md", "private-ip")

    def test_email_addresses(self):
        value = "person" + "@sample.invalid"
        self.write("README.md", value)
        result = self.run_guard("README.md")
        self.assert_finding(result, "README.md", "email")
        self.assertNotIn(value, result.stdout)

    def test_credentials(self):
        for value in ("BEGIN RSA " + "PRIVATE KEY", "gh" + "p_" + "a" * 36,
                      "github" + "_pat_" + "b" * 36, "s" + "k-" + "c" * 20,
                      "AK" + "IA" + "D" * 16):
            with self.subTest(value=value):
                self.write("README.md", value)
                result = self.run_guard("--all")
                self.assert_finding(result, "README.md", "credential")
                self.assertNotIn(value, result.stdout)

    def test_unpublished_frontmatter_statuses(self):
        for value in ("draft", "drafting", "proposed", "queued", "ready"):
            with self.subTest(value=value):
                self.write("README.md", "---\n" + f"status: '{value}' # note\n---\n")
                self.assert_finding(self.run_guard("--all"), "README.md", "draft-status", 2)

    def test_published_entry_requires_status(self):
        path = "published/sample.md"
        self.write(path, "Summary.\n")
        self.assert_finding(self.run_guard("--all"), path, "published-status")
        self.write(path, "---\n" + "status: archived\n---\n")
        self.assert_finding(self.run_guard("--all"), path, "published-status", 2)

    def test_binary_outside_examples_and_docs(self):
        self.write("skills/sample.bin", b"\0\xff")
        self.assert_finding(self.run_guard("--all"), "skills/sample.bin", "binary")

    def test_path_allowlist(self):
        for path in ("unknown.md", "personas/sample.md", "docs/personas/sample.md"):
            with self.subTest(path=path):
                self.write(path, "Sample.\n")
                self.assert_finding(self.run_guard("--all"), path, "path")

    def test_local_settings_path_is_rejected(self):
        path = "settings.local.toml"
        self.write(path, "# Local settings.\n")
        self.assert_finding(self.run_guard(path), path, "path")
        self.git("add", "-f", path)
        self.assert_finding(self.run_guard("--staged"), path, "path")

    def test_builtin_denylist_term(self):
        self.write("README.md", "INTERNAL" + " ONLY")
        self.assert_finding(self.run_guard("--all"), "README.md", "denylist")

    def test_private_denylist_from_env_or_settings(self):
        private_root = self.workspace / "private"
        settings = private_root / "settings"
        settings.mkdir(parents=True)
        term = "A confidential sample term"
        (settings / "guard-denylist.txt").write_text(
            f"# Comment\n\n{term}\nre:sample-[0-9]+\n", encoding="utf-8",
        )
        self.write("settings.local.toml", 'private_root = "../private"\n')
        self.write("README.md", term.upper() + "\nsample-42\n")
        for location in (None, str(private_root)):
            with self.subTest(location=location):
                if location is not None:
                    self.env["WRITING_PRIVATE"] = location
                    self.write("settings.local.toml", 'private_root = "../missing"\n')
                result = self.run_guard("--all")
                self.assert_finding(result, "README.md", "denylist")
                self.assert_finding(result, "README.md", "denylist", 2)
                self.assertEqual(result.stderr, "")
                self.assertNotIn(term.lower(), result.stdout.lower())

    def test_inline_exemption_applies_to_one_rule_and_line(self):
        email = "person" + "@sample.invalid"
        self.write("README.md", f"{email} guard: allow email\n")
        self.assertEqual(self.run_guard("--all").returncode, 0)
        private_ip = "192" + ".168.0.1"
        self.write("README.md", f"{email} {private_ip} guard: allow email\n{email}\n")
        result = self.run_guard("--all")
        self.assert_finding(result, "README.md", "private-ip")
        self.assert_finding(result, "README.md", "email", 2)
        self.assertNotIn("README.md:1: email:", result.stdout)

    def test_staged_checks_only_index_contents(self):
        email = "person" + "@sample.invalid"
        self.git("add", "README.md")
        self.write("README.md", email)
        self.write("docs/untracked.md", email)
        self.assertEqual(self.run_guard("--staged").returncode, 0)
        self.git("add", "README.md")
        self.write("README.md", "Clean working copy.\n")
        result = self.run_guard("--staged")
        self.assert_finding(result, "README.md", "email")
        self.assertNotIn("docs/untracked.md", result.stdout)


if __name__ == "__main__":
    unittest.main()
