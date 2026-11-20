# Writing tooling

This repository holds tooling for an author’s article workflow with coding agents. The author works through question rounds, refines a first draft, runs persona review rounds, publishes the article by hand, and adds a published entry.

Tooling and published entries are public. The private repo holds guides, personas, topics, drafts, and full article text. Keeping that material in a separate tree reduces the risk of including it when copying or sharing this repository.

- `skills/` holds `interview-to-draft`, `article-refiner`, `draft-persona-fanout`, `visual-asset-proposal`, and `humanizer`.
- `agents/` is reserved for agent definitions.
- `scripts/` holds the writing commands and guard.
- `.githooks/` and `.github/workflows/` run local and continuous integration checks.
- `docs/` holds decisions and the runbook index.
- `examples/` shows the formats for guides, personas, and local settings.
- `published/` holds summaries and links to published articles.

Run `scripts/install-hooks` from the repo root. Copy `examples/settings.example.toml` to `settings.local.toml` and set `private_root` to the private repo’s location. The `WRITING_PRIVATE` environment variable takes precedence. The guard requires Python 3.11 or newer.

## Commands

- `scripts/writing paths` — locate the public and private repos.
- `scripts/writing topic add` — create a topic note or merge evidence into one.
- `scripts/writing topic list` — list topics, optionally filtered by status.
- `scripts/writing topic set-status` — update a topic's status.
- `scripts/writing article new` — create the working files for an article.
- `scripts/writing article hash` — compute the SHA-256 of the exact article bytes.
- `scripts/writing article list` — list articles, optionally filtered by status.
- `scripts/writing header init`, `build` and `check` — make and check an article's header image (needs Chromium; see the runbook).
- `scripts/writing figure init`, `build` and `check` — make and check an article's in-article figures from small TOML inputs (needs Chromium; see the runbook).
- `scripts/writing publish` — preview a published entry or record it with the author's `--yes`.

Use `--help` on any command for its options. Topic, article, and publish commands
accept `--json`.

The five skills, writing commands, and runbooks for drafting, reviewing, and
publishing are available. Seeding legacy material is still to come.
