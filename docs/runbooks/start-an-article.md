# Start an article

1. The author selects a topic note or describes the piece. The agent can use
   `scripts/writing topic list` to find a note or `scripts/writing topic add` to
   record a new one at the author's request.
2. The agent starts `interview-to-draft`, reads the guides and any earlier series
   entries, and runs `scripts/writing article new` as directed by the skill.
3. The agent uses `interview-to-draft` to record and present question rounds.
   The author answers by number or waives individual questions. The agent
   records the answers and resolves the remaining design and business questions.
4. The agent proposes a working title and outline through `interview-to-draft`.
   The author accepts the outline before the agent writes the first draft.
5. The agent delivers the draft, claims list, flagged mentions, and open
   questions through `interview-to-draft`. The author takes over refinement.
