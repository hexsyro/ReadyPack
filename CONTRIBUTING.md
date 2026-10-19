# Contributing

Thanks for considering a contribution. ReadyPack is a packaging tool, and its
whole value rests on doing exactly what it says and no more.

## Ground rules

- **Keep it stdlib-only at runtime.** No third-party dependencies in
  `src/readypack/`.
- **Never delete rows implicitly.** A change that removes data without an
  explicit reviewed id will be rejected. Every removal is a changelog event.
- **Keep packaging deterministic.** The Croissant metadata carries a
  publication date, but scores, summaries, and the cleaned CSV must be a pure
  function of the inputs. No randomness, no network.
- **Neutralize spreadsheet formulas.** Any new CSV path must route cells
  through `safe_cell` in `common.py`.
- **No silent behavior changes.** If the score weights, grade bands, or pack
  contents change, that goes in the changelog.

## Workflow

1. Open an issue describing the problem before starting work on anything
   bigger than a typo fix.
2. Fork, branch, make the change, add tests.
3. Run `python -m pytest` and make sure it's green.
4. Open a pull request that says what changed and why, in plain language.
