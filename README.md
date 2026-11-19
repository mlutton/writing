# Writing tooling

This repository holds tooling for an author’s article workflow with coding agents. The author works through question rounds, refines a first draft, runs persona review rounds, publishes the article by hand, and adds a published entry.

Tooling and published entries are public. The private repo holds guides, personas, topics, drafts, and full article text. Keeping that material in a separate tree reduces the risk of including it when copying or sharing this repository.

- `skills/` and `agents/` will hold workflow skills and agent definitions.
- `scripts/`, `.githooks/`, and `.github/workflows/` hold local and continuous integration checks.
- `docs/` holds decisions and the runbook index.
- `examples/` shows the formats for guides, personas, and local settings.
- `published/` holds summaries and links to published articles.

Run `scripts/install-hooks` from the repo root. Copy `examples/settings.example.toml` to `settings.local.toml` and set `private_root` to the private repo’s location. The `WRITING_PRIVATE` environment variable takes precedence. The guard requires Python 3.11 or newer.

This is the initial skeleton. Skills have yet to be added.
