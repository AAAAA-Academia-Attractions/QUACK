# QUACK Heterogeneous Run Notes

Condition:

- Geese model: `gpt5.5`
- Duck model: `claude_opus4.7`

Clean seed coverage:

- The intended seed `1`-`30` set is now complete in the top-level result directory.
- Previously missing seeds have been filled:
  - `seed26`: `20260522_200127_seed26`
  - `seed27`: `20260522_201449_seed27`
  - `seed30`: `20260522_210627_seed30`

Notes:

- Problematic or incomplete attempts were moved under `api_error_runs/` and should not be treated as clean experiment outputs.
- The top-level result directory contains one clean run for each seed `1`-`30`; `seed1` has an extra earlier duplicate directory.
