<!-- Thanks for the PR. Please fill in what you can — the "why" matters most. -->

## What does this change?

<!-- One or two sentences. Link the issue with "Fixes #N" if there is one. -->

## Why is this the right change?

## Access model

<!-- Required for anything touching tools: read (safe by default) or write (gated on --allow-write)? -->

- [ ] No new tool, or the new tool is read-only
- [ ] New write capability, gated on `--allow-write` with validated inputs
- [ ] Not applicable

## How was it checked?

```
pip install -e ".[dev]"
pytest
```

## Notes for the reviewer
