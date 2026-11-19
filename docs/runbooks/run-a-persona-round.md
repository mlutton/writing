# Run a persona round

1. The author identifies the draft to review. The agent runs
   `scripts/writing article hash <folder-name>` against the exact article file.
2. The agent runs `draft-persona-fanout` on that draft with the supplied personas
   or the reader personas in the private repo. The agent saves the round under
   `reviews/round-N/` in the article folder and records the hash at the top.
3. The author reviews the findings and chooses any changes. For a new round,
   the agent runs `scripts/writing article hash` again and records the new round
   with `draft-persona-fanout`.
