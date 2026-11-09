---
name: Feature request
about: Suggest a new tool or a new capability for an existing one
title: "[feature] "
labels: enhancement
assignees: ''
---

**The admin task you're trying to do from an agent**

<!-- e.g. "find the service holding a port", "read the last 50 application errors". -->

**Proposed tool / change**

**Access level**

- Read (safe by default) / Write (requires `--allow-write`)

**Why the current tools don't cover it**

**Notes**

New tools default to read-only, take validated inputs, and return
`[stderr]`/`[exit N]` so failures are visible to the model. Requests that fit
that shape are easiest to act on.
