# Repository Instructions

## Type Checking

- After making code changes, run `just type-check`.
- Check and fix all type errors reported after the changes before considering the
  task complete.
- Do not suppress or ignore type errors merely to make the type checker pass.
- Avoid `Any`.
- BasedPyright unknown-type and explicit-`Any` diagnostics are configured as
  errors in `pyrightconfig.json`.
- `pyrightconfig.json` checks `app`, `eval`, and `tests`.
