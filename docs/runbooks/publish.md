# Publish

1. The author publishes the final article by hand and provides the public link
   and publication date. The agent prepares a 20–120 word summary for approval.
2. The agent previews the entry and status updates with
   `scripts/writing publish <folder-name> --url URL --date YYYY-MM-DD --summary TEXT`.
   The author checks the exact preview.
3. The author repeats `scripts/writing publish` with `--yes` after approving the
   wording. The command runs the guard and records the entry and private statuses.
4. The author resolves any reported findings and reruns the command. Before
   committing the entry, the author runs `scripts/guard --all`.
5. Before uploading, the author runs `scripts/writing header check <folder-name>`,
   which must pass, and pastes the header's `alt` text from `header.toml` into the
   image's alt field when uploading it.
6. Before uploading, the author runs `scripts/writing figure check <folder-name>`
   for an article with figures, which must pass, and pastes each figure's alt text
   from `figures/ALT-TEXT.md` into the image's alt field when uploading it.
