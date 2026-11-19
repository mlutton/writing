# Writing tooling

This repository holds tooling for an author’s article workflow with coding agents. The author works through question rounds, refines a first draft, runs persona review rounds, publishes the article by hand, and adds a published entry.

Tooling and published entries are public. The private repo holds guides, personas, topics, drafts, and full article text. Keeping that material in a separate tree reduces the risk of including it when copying or sharing this repository.

- `skills/` holds `article-refiner`, `draft-persona-fanout`, `visual-asset-proposal`, and `humanizer`.
- `agents/` is reserved for agent definitions.
- `scripts/`, `.githooks/`, and `.github/workflows/` hold local and continuous integration checks.
- `docs/` holds decisions and the runbook index.
- `examples/` shows the formats for guides, personas, and local settings.
- `published/` holds summaries and links to published articles.

Run `scripts/install-hooks` from the repo root. Copy `examples/settings.example.toml` to `settings.local.toml` and set `private_root` to the private repo’s location. The `WRITING_PRIVATE` environment variable takes precedence. The guard requires Python 3.11 or newer.

The four skills are present and `scripts/writing paths` locates both repositories. The interview-to-draft skill and the `topic` and `publish` commands are still to come.
